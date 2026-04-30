# polyforecast v0 build plan

## Goal

Build an LLM forecasting system that produces calibrated probability estimates on Polymarket markets, paper-trades against those estimates, and measures performance. **No real money until calibration is demonstrated.**

## Milestones

### M0 — Scaffolding (1–2 days)
- [ ] Repo initialized, `uv` project set up, pre-commit hooks (ruff, mypy)
- [ ] SQLite schema + Alembic migrations for: `markets`, `market_snapshots`, `research_dossiers`, `forecasts`, `trades`, `llm_calls`
- [ ] `llm/client.py` with caching, retry, cost logging
- [ ] CI running tests + lint on every commit

**Exit criteria:** `uv run pytest` passes on a hello-world test; a canned LLM call logs to `llm_calls` table.

### M1 — Scanner + raw data ingestion (2–3 days)
- [ ] Polymarket CLOB client: list markets, fetch orderbook, fetch trades
- [ ] Scanner logic: filter by liquidity, resolution window, category
- [ ] Daily snapshot job: persists current midpoint + orderbook depth for every active market
- [ ] CLI: `polyforecast scan --dry-run`

**Exit criteria:** Running the scanner produces 20–100 candidate markets from live Polymarket data, persisted to SQLite.

### M2 — Research stage (3–5 days)
- [ ] Research agent with web search tool use
- [ ] Structured dossier output (Pydantic model): resolution_criteria_verbatim, key_facts, base_rate_analysis, recent_news, expert_views, uncertainty_sources
- [ ] Per-market caching (re-research only if news changed or >72h old)
- [ ] Prompt version tracking

**Exit criteria:** 10 manually-reviewed dossiers that correctly quote resolution criteria and identify the major factors.

### M3 — Forecaster + Critic (3–5 days)
- [ ] Forecaster: takes dossier, produces `{probability, confidence_interval, reasoning, key_drivers}`. Blind to market price.
- [ ] Critic: takes forecast + dossier, produces `{adjusted_probability, critique, confidence_override}` or flags forecast as untradeable.
- [ ] End-to-end test: scanner → research → forecast → critic for one market, logged to DB.

**Exit criteria:** Full pipeline runs end-to-end on 20 markets. Forecast outputs manually look reasonable.

### M4 — Sizer + paper trading (2 days)
- [ ] Kelly sizer (fractional, configurable; default 1/4 Kelly)
- [ ] Edge threshold filter (don't trade unless |p - m| > threshold_bps + fee_estimate)
- [ ] Portfolio-level exposure tracking (flag correlated trades for manual review in v0)
- [ ] Paper-trade executor: writes intended trade with price, size, timestamp

**Exit criteria:** Running the full pipeline produces a set of paper trades per day, with full audit trail back to the originating forecast.

### M5 — Tracker + calibration (3–5 days)
- [ ] Daily mark-to-market job: fetches current Polymarket prices, updates unrealized P&L
- [ ] Resolution handler: when a market resolves, marks the forecast as resolved with outcome
- [ ] Calibration metrics: Brier score, calibration curve (binned), log loss — by category, by prompt version, by forecast confidence
- [ ] Regret analysis: trades not taken vs. outcomes
- [ ] Simple reporting: CLI command or Jupyter notebook that dumps weekly performance

**Exit criteria:** Can answer "how calibrated are our forecasts in the Politics category over the last 30 days?" with one command.

### M6 — Operationalize (ongoing)
- [ ] Scheduled daily run (cron or GitHub Actions)
- [ ] Cost monitoring + alerts (don't blow the LLM budget)
- [ ] Simple dashboard (Streamlit) showing open positions, recent forecasts, calibration curve

**Exit criteria:** System runs daily without intervention for 2 weeks.

## The evaluation phase (weeks 9+)

Once M0–M6 are complete and running:
- Collect resolved forecasts for 8+ weeks
- Target: 200+ resolved forecasts across categories
- Decision point at week 8:
  - **If Brier score beats the "always predict market price" baseline** and calibration curve is reasonable → consider small real-money allocation
  - **If not** → either iterate on prompts/methodology, or conclude the thesis is wrong and shut it off

## Explicit non-goals for v0

- Real money trading (even small amounts)
- Multiple markets beyond Polymarket
- Fancy UI
- Reinforcement learning / model fine-tuning
- Multi-agent "debate" beyond the single critic
- Anything that doesn't serve the calibration goal

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| LLM costs spiral | Aggressive caching, cheap model for scanner, cost dashboards from day 1 |
| Overfit to recent markets | Hold out time-based test set; don't tune prompts on trades that informed the tuning |
| Resolution ambiguity poisons the dataset | Flag ambiguous resolutions and exclude from calibration metrics |
| We stop being honest with ourselves | Pre-register the decision criteria at M6 and stick to them |
