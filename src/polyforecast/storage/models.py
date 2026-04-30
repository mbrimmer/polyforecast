"""ORM models — single source of truth for the schema.

Schema changes must go through Alembic migrations. Do not hand-edit a live DB.
Forecasts, dossiers, trade_marks, and resolutions are append-only: never
update in place; write a new row.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from polyforecast.storage.base import Base, utcnow


class TradeSide(StrEnum):
    YES = "YES"
    NO = "NO"


class TradeStatus(StrEnum):
    PROPOSED = "proposed"
    FILLED_PAPER = "filled_paper"
    REJECTED = "rejected"
    CLOSED = "closed"


class ResolutionOutcome(StrEnum):
    YES = "YES"
    NO = "NO"
    INVALID = "INVALID"


class PipelineRunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Market(TimestampMixin, Base):
    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    condition_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    resolution_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    snapshots: Mapped[list[MarketSnapshot]] = relationship(back_populates="market")
    dossiers: Mapped[list[ResearchDossier]] = relationship(back_populates="market")
    forecasts: Mapped[list[Forecast]] = relationship(back_populates="market")
    trades: Mapped[list[Trade]] = relationship(back_populates="market")
    resolution: Mapped[Resolution | None] = relationship(back_populates="market", uselist=False)


class MarketSnapshot(TimestampMixin, Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    midpoint: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    depth_bid_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    depth_ask_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_24h_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_orderbook: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    market: Mapped[Market] = relationship(back_populates="snapshots")


class LLMCall(TimestampMixin, Base):
    """Every LLM invocation. Doubles as the cache (lookup by prompt_hash)."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cached_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_calls.id", ondelete="SET NULL"), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ResearchDossier(TimestampMixin, Base):
    __tablename__ = "research_dossiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    resolution_criteria_verbatim: Mapped[str] = mapped_column(Text, nullable=False)
    key_facts: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    base_rate_analysis: Mapped[str] = mapped_column(Text, nullable=False)
    recent_news: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    expert_views: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    uncertainty_sources: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    llm_call_id: Mapped[int] = mapped_column(
        ForeignKey("llm_calls.id", ondelete="RESTRICT"), nullable=False
    )

    market: Mapped[Market] = relationship(back_populates="dossiers")


class Forecast(TimestampMixin, Base):
    """Append-only. Never update; write a new row instead."""

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dossier_id: Mapped[int] = mapped_column(
        ForeignKey("research_dossiers.id", ondelete="RESTRICT"), nullable=False
    )

    forecaster_prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    forecaster_probability: Mapped[float] = mapped_column(Float, nullable=False)
    forecaster_confidence_low: Mapped[float] = mapped_column(Float, nullable=False)
    forecaster_confidence_high: Mapped[float] = mapped_column(Float, nullable=False)
    forecaster_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    forecaster_key_drivers: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    forecaster_llm_call_id: Mapped[int] = mapped_column(
        ForeignKey("llm_calls.id", ondelete="RESTRICT"), nullable=False
    )

    critic_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    critic_adjusted_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    critic_critique: Mapped[str | None] = mapped_column(Text, nullable=True)
    critic_flagged_untradeable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    critic_llm_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("llm_calls.id", ondelete="RESTRICT"), nullable=True
    )

    final_probability: Mapped[float] = mapped_column(Float, nullable=False)

    market: Mapped[Market] = relationship(back_populates="forecasts")

    __table_args__ = (
        CheckConstraint(
            "forecaster_probability >= 0.0 AND forecaster_probability <= 1.0",
            name="ck_forecaster_probability_range",
        ),
        CheckConstraint(
            "final_probability >= 0.0 AND final_probability <= 1.0",
            name="ck_final_probability_range",
        ),
    )


class Trade(TimestampMixin, Base):
    """Paper trade. `status` drives the tracker lifecycle."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    forecast_id: Mapped[int] = mapped_column(
        ForeignKey("forecasts.id", ondelete="RESTRICT"), nullable=False
    )
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    side: Mapped[TradeSide] = mapped_column(SAEnum(TradeSide, name="trade_side"), nullable=False)
    intended_price: Mapped[float] = mapped_column(Float, nullable=False)
    intended_size_usd: Mapped[float] = mapped_column(Float, nullable=False)
    kelly_fraction_used: Mapped[float] = mapped_column(Float, nullable=False)
    edge_points: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[TradeStatus] = mapped_column(
        SAEnum(TradeStatus, name="trade_status"),
        nullable=False,
        default=TradeStatus.PROPOSED,
    )
    realized_pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    market: Mapped[Market] = relationship(back_populates="trades")
    marks: Mapped[list[TradeMark]] = relationship(back_populates="trade")


class TradeMark(TimestampMixin, Base):
    """Daily mark-to-market snapshot for an open trade. Append-only."""

    __tablename__ = "trade_marks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trade_id: Mapped[int] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), nullable=False, index=True
    )
    marked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    market_midpoint: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl_usd: Mapped[float] = mapped_column(Float, nullable=False)

    trade: Mapped[Trade] = relationship(back_populates="marks")


class PipelineRun(TimestampMixin, Base):
    """Heartbeat row written by the daily cron. Lets us prove plumbing works
    before any LLM logic exists, and later serves as a run-history audit log."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[PipelineRunStatus] = mapped_column(
        SAEnum(PipelineRunStatus, name="pipeline_run_status"), nullable=False
    )
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Resolution(TimestampMixin, Base):
    """One resolution per market. Append-only: if a resolution is disputed,
    write a new Market row or flag `outcome=INVALID` in a fresh resolution
    rather than mutating."""

    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(
        ForeignKey("markets.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
        index=True,
    )
    outcome: Mapped[ResolutionOutcome] = mapped_column(
        SAEnum(ResolutionOutcome, name="resolution_outcome"), nullable=False
    )
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    market: Mapped[Market] = relationship(back_populates="resolution")
