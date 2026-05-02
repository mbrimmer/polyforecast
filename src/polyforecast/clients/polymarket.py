"""Polymarket read-only client.

Uses two endpoints:
- Gamma API (`gamma-api.polymarket.com`) for the market catalog. Supports
  server-side filters by date range and activity flags, so the scanner
  doesn't have to paginate the full historical universe.
- CLOB API (`clob.polymarket.com`) for the orderbook. Gamma has price
  summaries but no full book.

No auth in v0 — public read endpoints only.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Self

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from polyforecast.config import settings

log = structlog.get_logger()


class Token(BaseModel):
    """One outcome of a Polymarket market (typically YES or NO)."""

    model_config = ConfigDict(extra="ignore")

    token_id: str
    outcome: str
    price: float | None = None
    winner: bool = False


class Market(BaseModel):
    """A Polymarket market. `raw_payload` preserves the upstream object so
    the scanner persists everything we didn't model explicitly."""

    model_config = ConfigDict(extra="ignore")

    condition_id: str
    question: str
    description: str | None = None
    market_slug: str | None = None
    category: str | None = None
    end_date_iso: str | None = None
    active: bool = True
    closed: bool = False
    archived: bool = False
    tokens: list[Token] = Field(default_factory=list)
    # Gamma's own liquidity proxy (USD). Useful as a cheap pre-filter so we
    # don't have to hit the CLOB orderbook for tens of thousands of markets.
    gamma_liquidity_usd: float | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def yes_token(self) -> Token | None:
        for t in self.tokens:
            if t.outcome.upper() == "YES":
                return t
        return self.tokens[0] if self.tokens else None


class OrderLevel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price: float
    size: float


class Orderbook(BaseModel):
    """Orderbook snapshot for a single Polymarket token."""

    model_config = ConfigDict(extra="ignore")

    market: str | None = None
    asset_id: str
    bids: list[OrderLevel] = Field(default_factory=list)
    asks: list[OrderLevel] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def best_bid(self) -> float | None:
        return max((b.price for b in self.bids), default=None)

    @property
    def best_ask(self) -> float | None:
        return min((a.price for a in self.asks), default=None)

    @property
    def midpoint(self) -> float | None:
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2.0


def _is_retryable(exc: BaseException) -> bool:
    """Retry on 429, 5xx, and network errors. Don't retry other 4xx."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return isinstance(exc, httpx.TransportError | httpx.TimeoutException)


def _maybe_json_list(v: Any) -> list[Any]:
    """Gamma encodes some array fields as JSON strings (e.g. clobTokenIds)."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _coerce_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _market_from_gamma(raw: dict[str, Any]) -> Market:
    token_ids = [str(t) for t in _maybe_json_list(raw.get("clobTokenIds"))]
    outcomes = [str(o) for o in _maybe_json_list(raw.get("outcomes"))]
    prices_raw = _maybe_json_list(raw.get("outcomePrices"))
    tokens: list[Token] = []
    for i, tid in enumerate(token_ids):
        outcome = outcomes[i] if i < len(outcomes) else f"outcome_{i}"
        price: float | None = None
        if i < len(prices_raw) and prices_raw[i] not in (None, ""):
            try:
                price = float(prices_raw[i])
            except (TypeError, ValueError):
                price = None
        tokens.append(Token(token_id=tid, outcome=outcome, price=price))
    return Market(
        condition_id=raw.get("conditionId") or "",
        question=raw.get("question") or "",
        description=raw.get("description"),
        market_slug=raw.get("slug"),
        category=raw.get("category"),
        end_date_iso=raw.get("endDate") or raw.get("endDateIso"),
        active=bool(raw.get("active", True)),
        closed=bool(raw.get("closed", False)),
        archived=bool(raw.get("archived", False)),
        tokens=tokens,
        gamma_liquidity_usd=_coerce_float(raw.get("liquidity")),
        raw_payload=raw,
    )


class PolymarketClient:
    """Async read-only Polymarket client.

    Use as an async context manager:

        async with PolymarketClient() as client:
            async for m in client.iter_active_markets(now, now + 180d):
                ...
    """

    def __init__(
        self,
        gamma_base_url: str | None = None,
        clob_base_url: str | None = None,
        timeout_s: float = 15.0,
        max_concurrency: int | None = None,
    ) -> None:
        self._gamma_url = gamma_base_url or settings.polymarket_gamma_base_url
        self._clob_url = clob_base_url or settings.polymarket_clob_base_url
        self._timeout_s = timeout_s
        self._semaphore = asyncio.Semaphore(
            max_concurrency or settings.polymarket_max_concurrency
        )
        self._gamma: httpx.AsyncClient | None = None
        self._clob: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        self._gamma = httpx.AsyncClient(
            base_url=self._gamma_url,
            timeout=self._timeout_s,
            headers={"accept": "application/json"},
        )
        self._clob = httpx.AsyncClient(
            base_url=self._clob_url,
            timeout=self._timeout_s,
            headers={"accept": "application/json"},
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._gamma is not None:
            await self._gamma.aclose()
            self._gamma = None
        if self._clob is not None:
            await self._clob.aclose()
            self._clob = None

    async def _get_json(
        self, http: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_random_exponential(min=0.5, max=8.0),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                async with self._semaphore:
                    resp = await http.get(path, params=params)
                resp.raise_for_status()
                return resp.json()

    async def iter_active_markets(
        self,
        end_date_min: datetime,
        end_date_max: datetime,
        page_size: int = 500,
    ) -> AsyncIterator[Market]:
        """Stream Gamma's active+open markets resolving in [min, max].

        Gamma supports up to limit=500 per page and offset-based pagination.
        We stop when a page returns fewer than `page_size` items.
        """
        assert self._gamma is not None, "use 'async with PolymarketClient()'"
        offset = 0
        while True:
            params: dict[str, Any] = {
                "active": "true",
                "closed": "false",
                "archived": "false",
                "limit": page_size,
                "offset": offset,
                "order": "endDate",
                "ascending": "true",
                "end_date_min": end_date_min.isoformat(),
                "end_date_max": end_date_max.isoformat(),
            }
            data = await self._get_json(self._gamma, "/markets", params=params)
            items: list[dict[str, Any]] = data if isinstance(data, list) else []
            for raw in items:
                yield _market_from_gamma(raw)
            log.debug(
                "polymarket.gamma.page",
                offset=offset,
                returned=len(items),
            )
            if len(items) < page_size:
                return
            offset += page_size

    async def get_orderbook(self, token_id: str) -> Orderbook:
        assert self._clob is not None, "use 'async with PolymarketClient()'"
        data = await self._get_json(
            self._clob, "/book", params={"token_id": token_id}
        )
        return Orderbook.model_validate({**data, "raw_payload": data})
