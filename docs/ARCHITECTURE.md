# Architecture

## Dataflow

```
                        ┌──────────────┐
                        │  Polymarket  │
                        │   CLOB API   │
                        └──────┬───────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  Scanner  →  market_snapshots, markets (SQLite)          │
└──────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  Research (LLM + web search)  →  research_dossiers       │
└──────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  Forecaster (LLM, blind to price)  →  forecasts          │
└──────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  Critic (LLM)  →  forecasts (adjusted_probability)       │
└──────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  Sizer (deterministic)  →  trades (status=proposed)      │
└──────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  Executor (paper)  →  trades (status=filled_paper)       │
└──────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  Tracker (daily)  →  trade_marks, resolutions,           │
│                      calibration_metrics                  │
└──────────────────────────────────────────────────────────┘
```

## Why stages read/write to SQLite rather than pass objects

Re-runnability. You want to be able to say "re-run the critic on yesterday's forecasts with the new prompt" without re-running scanner/research/forecaster. SQLite as the bus makes this trivial.

## Why the forecaster is blind to price

If the forecaster sees the market is at 0.30, it will anchor to 0.30. This is the single biggest failure mode in LLM forecasting. The whole point is to produce an *independent* estimate that we can compare against market price.

The critic IS allowed to see the market price, because at that stage we want someone to ask "is the market pricing this very differently, and if so, is there something the forecaster missed?" That's useful signal, not anchoring.

## Kelly sizing, fractional

For a binary bet with estimated win probability `p` on a YES share priced at `m`:
- Edge if buying YES: `p - m` (expected profit per $1 at risk, ignoring fees)
- Full Kelly fraction of bankroll: `(p - m) / (1 - m)` if buying YES above price
- We use 1/4 Kelly by default because:
  - Our `p` is itself uncertain
  - Kelly is optimal only if you believe your edge estimate exactly
  - 1/4 Kelly gives up ~6% of expected growth vs. full Kelly but cuts drawdown volatility dramatically
  - See: Thorp, "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"

## Calibration is the north star metric

We measure three things:

1. **Brier score**: mean squared error of probability forecasts against outcomes. Lower is better.
2. **Calibration curve**: bin forecasts by predicted probability (e.g., 0–10%, 10–20%, ...), measure actual frequency in each bin. Ideal is y=x.
3. **Resolution** (aka discrimination): how much better are we than just predicting the base rate? A forecaster that always says "50%" has perfect calibration but zero resolution.

The baseline to beat: "always predict the market's mid-price." If we can't beat that, we have no edge.

## Why we cache LLM calls so aggressively

During development you will re-run the pipeline dozens of times. Every run is $$. The cache is keyed on `(model, prompt_hash, params_hash)` and lives in SQLite. In production we still cache research dossiers for 72 hours unless news has broken.

## Failure modes to watch for

- **Resolution drift**: market resolves on criteria the forecaster didn't account for. Mitigation: researcher must quote resolution criteria verbatim; critic checks the forecast addressed those criteria.
- **Correlated bets**: 10 positions on related markets are 1 bet. Mitigation: manual flagging in v0, cluster detection later.
- **Regime change**: a model calibrated on H1 2026 markets may be poorly calibrated on H2. Mitigation: track calibration over rolling windows, not just cumulatively.
- **Ambiguous resolutions**: some markets resolve in contested ways (UMA oracle disputes). Mitigation: tag these explicitly and exclude from clean calibration metrics, report them separately.
