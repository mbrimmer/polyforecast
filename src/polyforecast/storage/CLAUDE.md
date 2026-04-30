# storage/

The data layer. **Postgres in the cloud (Neon), SQLite acceptable for local dev / tests.**
Both via SQLAlchemy 2.x (typed). Alembic for migrations.

## Design principles

- **The database is the bus between stages.** Every stage reads its inputs from the DB and writes its outputs back.
- **Immutability where it matters.** Forecasts, research dossiers, trades are append-only. Never mutate a forecast row; write a new one.
- **UTC everywhere.** All timestamps stored as UTC. Never store local time.
- **Foreign keys enforced.** `PRAGMA foreign_keys = ON` at connection time.

## Core tables

- `markets` — Polymarket market metadata (condition_id, question, resolution_source, category, etc.). Slowly changing.
- `market_snapshots` — point-in-time price/liquidity data. Written by scanner daily, and any time we sample price for a trade decision.
- `research_dossiers` — output of the research stage. Pydantic-serialized JSON in a column, plus structured fields for querying (market_id, created_at, prompt_version).
- `forecasts` — output of forecaster + critic. Includes both the raw forecaster probability and the critic-adjusted probability, plus reasoning and prompt versions.
- `trades` — proposed and filled paper trades. `status` enum: `proposed`, `filled_paper`, `rejected`, `closed`.
- `trade_marks` — daily mark-to-market records per trade.
- `resolutions` — when a market resolves, the outcome and payoff.
- `llm_calls` — every LLM call with token counts, cost, cached flag, prompt hash. Essential for cost tracking.

## Schema rules

- Every table has `id` (primary key), `created_at`, `updated_at` (UTC).
- `updated_at` managed by trigger or in app code — pick one and be consistent.
- Text columns that hold JSON: use `sqlalchemy.JSON` type, not raw TEXT.
- Enums: use Python `StrEnum` + `sqlalchemy.Enum`.

## Migrations

- All schema changes via Alembic. No ad-hoc ALTER.
- Autogenerate is fine for simple changes, but **review the generated migration** — autogen misses things like index rename and constraint reordering.
- Migrations should be reversible where possible.
- Never squash migrations that have been applied to your live DB.

## Connection management

- One `Session` per logical unit of work (e.g., one market's pipeline run).
- Use `with Session(engine) as session:` context managers. Don't leak sessions.
- Bulk inserts use `session.execute(insert(Table).values(...))`, not ORM `session.add_all()` — orders of magnitude faster.
- Driver: `psycopg` v3. Connection strings from Neon arrive as `postgresql://...` and are
  auto-rewritten to `postgresql+psycopg://...` in `polyforecast.config`. Don't hand-edit the URL.

## Testing

- Unit tests use an in-memory SQLite (`sqlite:///:memory:`).
- Integration tests use a temp file DB that's recreated per test.
- Factories (via `factory-boy` or plain functions) for test fixtures.
