"""Scanner stage — find candidate markets worth researching.

Pure deterministic filtering; no LLM. Pulls every market the CLOB exposes,
filters by activity flags, resolution horizon, and liquidity, then upserts
the survivors into `markets` and writes a fresh `market_snapshots` row per
market with its current orderbook depth.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from polyforecast.clients import Market as PMMarket
from polyforecast.clients import Orderbook, PolymarketClient
from polyforecast.config import settings
from polyforecast.storage.base import session_scope
from polyforecast.storage.models import Market, MarketSnapshot

log = structlog.get_logger()


# Liquidity proxy from scanner/CLAUDE.md: sum(price * size) for orders within
# 5% of the midpoint, both sides.
_DEPTH_BAND = 0.05


@dataclass(frozen=True)
class ScanFilters:
    min_days_to_resolution: int
    max_days_to_resolution: int
    liquidity_threshold_usd: float

    @classmethod
    def from_settings(cls) -> ScanFilters:
        return cls(
            min_days_to_resolution=settings.scanner_min_days_to_resolution,
            max_days_to_resolution=settings.scanner_max_days_to_resolution,
            liquidity_threshold_usd=settings.scanner_liquidity_threshold_usd,
        )


@dataclass
class ScanResult:
    total_markets_seen: int
    passed_activity: int
    passed_date_window: int
    passed_liquidity: int
    persisted: int


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_active(m: PMMarket) -> bool:
    return m.active and not m.closed and not m.archived


def _days_to_resolution(m: PMMarket, now: datetime) -> float | None:
    end = _parse_iso(m.end_date_iso)
    if end is None:
        return None
    return (end - now).total_seconds() / 86400.0


def _depth_usd(orderbook: Orderbook) -> float:
    """Sum of price*size on both sides within ±5% of midpoint.

    Proxy for "could I actually fill at size?". Returns 0 if midpoint is
    undefined (one-sided book).
    """
    mid = orderbook.midpoint
    if mid is None:
        return 0.0
    bid_floor = mid * (1 - _DEPTH_BAND)
    ask_ceil = mid * (1 + _DEPTH_BAND)
    bid_depth = sum(b.price * b.size for b in orderbook.bids if b.price >= bid_floor)
    ask_depth = sum(a.price * a.size for a in orderbook.asks if a.price <= ask_ceil)
    return bid_depth + ask_depth


async def _fetch_orderbook(
    client: PolymarketClient, market: PMMarket
) -> Orderbook | None:
    """Best-effort orderbook fetch. 404 (closed/missing book) returns None."""
    token = market.yes_token
    if token is None:
        return None
    try:
        return await client.get_orderbook(token.token_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise


def _upsert_market(session: Session, m: PMMarket) -> Market:
    existing = session.scalar(
        select(Market).where(Market.condition_id == m.condition_id)
    )
    end_date = _parse_iso(m.end_date_iso)
    if existing is not None:
        existing.question = m.question
        existing.description = m.description
        existing.category = m.category
        existing.end_date = end_date
        existing.active = m.active
        existing.closed = m.closed
        existing.raw_payload = m.raw_payload
        return existing
    row = Market(
        condition_id=m.condition_id,
        question=m.question,
        description=m.description,
        category=m.category,
        end_date=end_date,
        active=m.active,
        closed=m.closed,
        raw_payload=m.raw_payload,
    )
    session.add(row)
    session.flush()  # populate row.id for the FK on MarketSnapshot
    return row


def _insert_snapshot(
    session: Session, market_row: Market, ob: Orderbook, depth_usd: float
) -> MarketSnapshot:
    spread = (
        (ob.best_ask - ob.best_bid)
        if ob.best_bid is not None and ob.best_ask is not None
        else None
    )
    snap = MarketSnapshot(
        market_id=market_row.id,
        captured_at=datetime.now(UTC),
        midpoint=ob.midpoint,
        best_bid=ob.best_bid,
        best_ask=ob.best_ask,
        spread=spread,
        depth_bid_usd=sum(
            b.price * b.size
            for b in ob.bids
            if ob.midpoint and b.price >= ob.midpoint * (1 - _DEPTH_BAND)
        )
        or None,
        depth_ask_usd=sum(
            a.price * a.size
            for a in ob.asks
            if ob.midpoint and a.price <= ob.midpoint * (1 + _DEPTH_BAND)
        )
        or None,
        volume_24h_usd=None,
        raw_orderbook=ob.raw_payload,
    )
    session.add(snap)
    return snap


async def scan(
    *,
    dry_run: bool = False,
    market_limit: int | None = None,
    filters: ScanFilters | None = None,
) -> ScanResult:
    """Run one scanner pass.

    Args:
        dry_run: Walk the pipeline but don't persist anything.
        market_limit: Stop pagination after this many raw markets (testing).
        filters: Override default thresholds.
    """
    fil = filters or ScanFilters.from_settings()
    now = datetime.now(UTC)
    log.info(
        "scanner.start",
        dry_run=dry_run,
        market_limit=market_limit,
        min_days=fil.min_days_to_resolution,
        max_days=fil.max_days_to_resolution,
        liquidity_threshold_usd=fil.liquidity_threshold_usd,
    )

    end_min = now + timedelta(days=fil.min_days_to_resolution)
    end_max = now + timedelta(days=fil.max_days_to_resolution)

    total_seen = 0
    activity_survivors: list[PMMarket] = []
    cheap_liquidity_survivors: list[PMMarket] = []

    async with PolymarketClient() as client:
        async for market in client.iter_active_markets(
            end_date_min=end_min, end_date_max=end_max
        ):
            total_seen += 1
            if market_limit is not None and total_seen >= market_limit:
                break
            # Gamma already filtered active/closed/archived and the date range,
            # but defend against drift in case the API ships subtle changes.
            if not _is_active(market):
                continue
            days = _days_to_resolution(market, now)
            if days is None:
                continue
            if not (fil.min_days_to_resolution <= days <= fil.max_days_to_resolution):
                continue
            activity_survivors.append(market)
            # Cheap pre-filter: skip the CLOB orderbook fetch for markets
            # whose Gamma liquidity is already obviously below threshold.
            # We accept gamma >= 0.5 * threshold to allow for slack between
            # Gamma's number and our depth-within-5%-of-mid calculation.
            gl = market.gamma_liquidity_usd
            if gl is None or gl >= fil.liquidity_threshold_usd * 0.5:
                cheap_liquidity_survivors.append(market)

        log.info(
            "scanner.activity_filtered",
            total_seen=total_seen,
            activity_survivors=len(activity_survivors),
            cheap_liquidity_survivors=len(cheap_liquidity_survivors),
        )

        # Now hit CLOB only for the markets that survived the cheap filter.
        orderbooks = await asyncio.gather(
            *(_fetch_orderbook(client, m) for m in cheap_liquidity_survivors),
            return_exceptions=False,
        )

    liquid_pairs: list[tuple[PMMarket, Orderbook, float]] = []
    for m, ob in zip(cheap_liquidity_survivors, orderbooks, strict=True):
        if ob is None:
            continue
        depth = _depth_usd(ob)
        if depth >= fil.liquidity_threshold_usd:
            liquid_pairs.append((m, ob, depth))

    log.info(
        "scanner.liquidity_filtered",
        survivors=len(liquid_pairs),
        threshold_usd=fil.liquidity_threshold_usd,
    )

    if dry_run:
        for m, _ob, depth in liquid_pairs[:20]:
            log.info(
                "scanner.candidate",
                condition_id=m.condition_id,
                question=m.question[:80],
                depth_usd=round(depth, 2),
                end_date_iso=m.end_date_iso,
            )
        return ScanResult(
            total_markets_seen=total_seen,
            passed_activity=len(activity_survivors),
            passed_date_window=len(activity_survivors),
            passed_liquidity=len(liquid_pairs),
            persisted=0,
        )

    persisted = 0
    with session_scope() as session:
        for m, ob, depth in liquid_pairs:
            row = _upsert_market(session, m)
            _insert_snapshot(session, row, ob, depth)
            persisted += 1

    log.info("scanner.done", persisted=persisted)
    return ScanResult(
        total_markets_seen=total_seen,
        passed_activity=len(activity_survivors),
        passed_date_window=len(activity_survivors),
        passed_liquidity=len(liquid_pairs),
        persisted=persisted,
    )
