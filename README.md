# polyforecast

LLM-powered forecasting and paper-trading system for Polymarket prediction markets.

**Not for real-money trading in v0.** See `CLAUDE.md` for why.

## Quick start

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Copy env template and add your Anthropic API key
cp .env.example .env
# edit .env

# Initialize the database
uv run alembic upgrade head

# Run the scanner
uv run polyforecast scan

# Run the full pipeline for one market (dry run, no trades)
uv run polyforecast pipeline --market-id <condition_id> --dry-run
```

## Reading this codebase

1. `CLAUDE.md` — project philosophy and top-level conventions
2. `docs/PLAN.md` — the v0 buildout milestones
3. `docs/ARCHITECTURE.md` — how the stages fit together
4. `src/polyforecast/<stage>/CLAUDE.md` — stage-specific rules

## Development loop

```bash
# Lint + format
uv run ruff check --fix .
uv run ruff format .

# Type check
uv run mypy src/

# Run tests
uv run pytest

# All of the above
uv run make check   # if you add a Makefile
```

## What this project is NOT trying to do in v0

- Make money
- Execute real trades
- Support markets beyond Polymarket
- Be a pretty dashboard

It's trying to answer one question: *can an LLM-driven forecasting pipeline produce calibrated, edge-generating probability estimates on a prediction market?*

Ask that question honestly. Build the machinery to answer it rigorously. Then decide what's next.
