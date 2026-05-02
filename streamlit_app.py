"""polyforecast — public dashboard.

Read-only view into the Neon Postgres state. No LLM calls happen here.
Runs both locally (env DATABASE_URL via .env) and on Streamlit Community Cloud
(st.secrets["DATABASE_URL"] is promoted to env before polyforecast.* imports).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import streamlit as st

# Streamlit Cloud delivers secrets via st.secrets; pydantic-settings reads from
# os.environ. Promote before the polyforecast package is imported.
try:
    if "DATABASE_URL" in st.secrets:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    pass

from sqlalchemy import func, select  # noqa: E402

from polyforecast.storage.base import session_scope  # noqa: E402
from polyforecast.storage.models import Market, MarketSnapshot, PipelineRun  # noqa: E402


def human_age(delta: timedelta) -> str:
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


st.set_page_config(page_title="polyforecast", layout="wide")

st.title("polyforecast")
st.markdown(
    "**LLM-powered probabilistic forecasting on Polymarket prediction markets.** "
    "Evaluation-first: probabilities are generated blind to market price, "
    "paper-traded at fractional Kelly, and scored against actual resolutions to "
    "measure calibration."
)
st.markdown(
    "[Source on GitHub](https://github.com/mbrimmer/polyforecast) · "
    "[brimmerconsulting.com](https://www.brimmerconsulting.com)"
)

st.divider()

st.header("System health")

with session_scope() as session:
    total_runs = session.scalar(select(func.count()).select_from(PipelineRun)) or 0
    last_run = session.scalars(
        select(PipelineRun).order_by(PipelineRun.id.desc()).limit(1)
    ).first()
    recent = list(
        session.scalars(select(PipelineRun).order_by(PipelineRun.id.desc()).limit(20))
    )

c1, c2, c3 = st.columns(3)
c1.metric("Cron runs to date", total_runs)
if last_run is not None:
    c2.metric("Last run", human_age(datetime.now(UTC) - last_run.started_at))
    c3.metric("Last status", last_run.status.value)
else:
    c2.metric("Last run", "—")
    c3.metric("Last status", "—")

st.subheader("Recent runs")
if recent:
    st.dataframe(
        [
            {
                "id": r.id,
                "started_at": r.started_at,
                "status": r.status.value,
                "git_sha": (r.git_sha or "local")[:8],
                "notes": r.notes,
            }
            for r in recent
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.info("No runs yet.")

st.divider()

st.header("Latest scan — candidate markets")
st.markdown(
    "Markets the scanner pulled from Polymarket and persisted to the database. "
    "Filtered by activity, resolution window (14–180 days), and orderbook depth "
    "($50K within 5% of midpoint). Midpoint shown is from the most recent snapshot."
)

with session_scope() as session:
    market_count = session.scalar(select(func.count()).select_from(Market)) or 0
    snapshot_count = (
        session.scalar(select(func.count()).select_from(MarketSnapshot)) or 0
    )
    latest = (
        select(
            MarketSnapshot.market_id,
            func.max(MarketSnapshot.id).label("latest_id"),
        )
        .group_by(MarketSnapshot.market_id)
        .subquery()
    )
    rows = session.execute(
        select(Market, MarketSnapshot)
        .join(latest, latest.c.market_id == Market.id)
        .join(MarketSnapshot, MarketSnapshot.id == latest.c.latest_id)
        .order_by(Market.end_date)
    ).all()

c1, c2 = st.columns(2)
c1.metric("Markets tracked", market_count)
c2.metric("Snapshots captured", snapshot_count)

if rows:
    st.dataframe(
        [
            {
                "question": m.question,
                "end_date": m.end_date,
                "category": m.category,
                "midpoint": snap.midpoint,
                "best_bid": snap.best_bid,
                "best_ask": snap.best_ask,
                "depth_bid_usd": snap.depth_bid_usd,
                "depth_ask_usd": snap.depth_ask_usd,
                "snapshot_at": snap.captured_at,
            }
            for m, snap in rows
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.info("No markets scanned yet. The daily cron runs at 12:00 UTC.")

st.divider()

st.header("Pipeline")
st.markdown(
    "The forecasting pipeline runs daily and proceeds through seven stages. "
    "Each stage reads from and writes to Postgres so any stage can be re-run "
    "in isolation. Stages currently shown without data are not yet implemented."
)

stages = [
    ("Scanner", "M1", "Pulls open Polymarket markets, filters by liquidity and resolution horizon."),
    ("Research", "M2", "LLM + web search produces a structured dossier per market, quoting resolution criteria verbatim."),
    ("Forecaster", "M3", "LLM produces a probability estimate. Blind to market price by design."),
    ("Critic", "M3", "LLM reviews the forecast and adjusts or flags it untradeable."),
    ("Sizer", "M4", "Deterministic fractional-Kelly position sizing. No LLM."),
    ("Executor", "M4", "Writes intended trades to the paper-trading table. No real orders."),
    ("Tracker", "M5", "Daily mark-to-market, resolution handling, calibration metrics."),
]
for name, milestone, desc in stages:
    st.markdown(f"**{name}** &nbsp;·&nbsp; _{milestone}_ — {desc}")

st.divider()
st.caption(
    "polyforecast is paper-trading only in v0. No real money is being traded. "
    "Built by Matt Brimmer."
)
