# polyforecast

An LLM-powered forecasting and paper-trading system for Polymarket prediction markets.

## Project philosophy

**This is an evaluation system first, a trading system second.** For the first 8+ weeks, we do not execute real trades. We generate forecasts, log them, wait for markets to resolve, and measure calibration. The entire point is to find out whether our forecasts actually have edge before risking capital.

Default assumption for any new feature: *does this help us measure calibration, or does it just feel like progress?* If it's the latter, push back.

## Architecture (read before touching anything)

Seven-stage pipeline, each stage is a pure function of its inputs where possible:

1. **Scanner** (`src/polyforecast/scanner/`) — pulls open markets from Polymarket CLOB API, filters by liquidity/horizon/freshness. Pure Python, no LLM.
2. **Research** (`src/polyforecast/research/`) — LLM + web search produces a structured research dossier per market. The dossier must quote resolution criteria verbatim.
3. **Forecaster** (`src/polyforecast/forecaster/`) — LLM produces a probability estimate given the dossier. **Must not see the current market price.**
4. **Critic** (`src/polyforecast/critic/`) — LLM reviews the forecast and adjusts or flags it.
5. **Sizer** (`src/polyforecast/sizer/`) — deterministic Kelly-fraction position sizing. No LLM.
6. **Executor** (`src/polyforecast/executor/`) — in v0, writes intended trades to the paper-trading table. No real orders.
7. **Tracker** (`src/polyforecast/tracker/`) — daily mark-to-market, resolution handling, calibration metrics.

Data flows through the SQLite database (`data/polyforecast.db`). Each stage reads its inputs from the DB and writes its outputs back. This is deliberate: any stage should be re-runnable in isolation, and the DB is the single source of truth.

## Tech stack

- Python 3.11+
- `uv` for package management (use `uv add <pkg>` not `pip install`)
- SQLite for storage (via `sqlalchemy` 2.x, typed)
- `anthropic` SDK for LLM calls
- `httpx` for HTTP (async where it matters)
- `pydantic` v2 for all data models at stage boundaries
- `pytest` for tests
- `ruff` for lint + format, `mypy` for types

## Coding conventions

- **Type everything.** All function signatures have type hints. Pydantic models at every stage boundary. `mypy --strict` on `src/`.
- **No bare `dict` or `Any` crossing module boundaries.** Define a Pydantic model.
- **Functions over classes** where there's no state to manage. Stages are largely functions.
- **Async for I/O, sync for CPU.** LLM calls and HTTP are async; Kelly math is sync.
- **Logging, not printing.** Use `structlog`. Every LLM call gets logged with prompt hash, token counts, and cost estimate.
- **Errors bubble up with context.** Use `raise ... from err`. Don't swallow exceptions.
- **No mutable default arguments.** Ever.
- **Tests for every non-trivial function.** Stages have integration tests that run against recorded fixtures (see `tests/integration/fixtures/`).

## LLM call conventions

Every LLM call goes through `src/polyforecast/llm/client.py`. That module handles:
- Retry with exponential backoff
- Token counting and cost logging
- Caching to SQLite (keyed on prompt hash + model + params) — critical for cost control during development
- Prompt versioning (every prompt has a version string; forecasts log which version produced them)

**Never call the Anthropic SDK directly from a stage module.** Always go through `llm/client.py`.

## Prompt engineering rules

- Prompts live in `src/polyforecast/<stage>/prompts.py` as Python constants, not in text files. Easier to version with code.
- Every prompt has a `VERSION` string. Bump it when you change the prompt materially.
- Forecasts store the prompt version alongside the output, so we can compare calibration across prompt versions.
- Structured output: use Anthropic's tool-use for structured outputs, not JSON-in-freetext. Parse with Pydantic.

## Database conventions

- All schema changes go through Alembic migrations. No ad-hoc `ALTER TABLE`.
- Every table has `created_at` and `updated_at` timestamps (UTC, always UTC).
- Forecast records are immutable once written. New forecasts on the same market create new rows; we never overwrite.
- Foreign keys enforced.

## What NOT to do

- **Do not add a real-money execution path in v0.** Not even behind a feature flag. Not even "just in case." The paper-trading table is the only output.
- **Do not let the forecaster see the current market price.** This is the single most important architectural rule. If you're tempted to pass the price "just as context," stop.
- **Do not optimize before you have calibration data.** No prompt tweaking based on 5 resolved markets. Wait for ~50+ resolutions per category before drawing conclusions.
- **Do not add features that don't feed into calibration measurement.** Fancy dashboards, Slack integrations, etc. come after we know the system works.

## Workflow

- Feature branches off `main`. PRs reviewed by reading `CLAUDE.md` + the stage-specific `CLAUDE.md` before touching code.
- Every PR runs: `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest`.
- Commit messages: conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`).

## Environment

- `.env` for secrets (never committed): `ANTHROPIC_API_KEY`, `POLYMARKET_API_KEY` (if needed later)
- `config.yaml` for tunable parameters (liquidity thresholds, Kelly fraction, edge threshold, etc.)

## Where to start reading

New to the codebase? Read in this order:
1. This file
2. `docs/PLAN.md` — the v0 buildout plan and milestones
3. `docs/ARCHITECTURE.md` — deeper design notes
4. `src/polyforecast/storage/CLAUDE.md` — the data model
5. The stage-specific `CLAUDE.md` for whatever you're working on
