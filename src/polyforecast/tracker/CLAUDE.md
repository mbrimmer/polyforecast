# tracker/

Daily mark-to-market, resolution handling, calibration metrics. **This is the actual product of v0.**

## Responsibilities

1. **Daily mark-to-market**: for every open paper trade, fetch current Polymarket price and record unrealized P&L to `trade_marks`.
2. **Resolution handling**: when a market resolves on Polymarket, fetch the outcome, close all paper trades in that market, compute realized P&L, mark the associated forecasts as resolved.
3. **Calibration metrics**: compute and store — daily, weekly, by-category, by-prompt-version:
   - Brier score (overall, by category, by confidence bucket)
   - Calibration curve (10 bins of predicted probability vs. actual frequency)
   - Log loss
   - Resolution / discrimination (improvement over base rate)
   - Vs-market baseline: how does our Brier score compare to "forecast = market mid at time of research"?
4. **Regret analysis**: for every market where we ran the pipeline but didn't trade (below edge threshold, or untradeable flag), record what would have happened if we did.

## The metrics that matter

Rank of importance:

1. **Calibration curve.** Are our 70% forecasts actually happening 70% of the time? This is the primary honesty check.
2. **Brier score vs. market baseline.** Are we better than "just use the market price"? If not, we have no edge.
3. **Brier score by category.** Maybe we're great at politics and terrible at crypto. That tells us what to trade.
4. **Paper P&L.** Matters, but is high-variance. Don't over-index on this with <100 resolutions.
5. **Sharpe-ish metrics.** P&L / std(P&L). Nice to have.

## Baselines to always compute

- **Market baseline**: forecast = market mid at time of research. This is the "are we adding value" test.
- **Naive base-rate baseline**: forecast = historical base rate of YES resolution in this category. Tests whether the model adds anything over "ask a dumb base-rate estimator".
- **Forecaster-alone vs. forecaster+critic**: does the critic help?

## Resolution edge cases

- **UMA disputes / contested resolutions**: flag these, exclude from "clean" calibration, report separately. Don't let a few contentious outcomes poison the headline metrics.
- **Markets that never resolve in window**: have a policy. Mine suggestion: if a market hasn't resolved within 30 days of its stated resolution date, mark it "resolution_pending_long" and exclude from rolling metrics.
- **Partial resolutions / multi-outcome markets**: v0 only handles binary YES/NO. If we accidentally scan a multi-outcome market, the scanner should have filtered it; if one sneaks through, the tracker should flag and skip.

## Reporting

- Weekly report CLI: `polyforecast report --weeks 1` dumps a markdown summary with calibration curve (ASCII plot or matplotlib PNG), Brier scores, P&L, biggest wins/losses, notable flags.
- Jupyter notebook in `notebooks/calibration.ipynb` for deeper exploration.
- No fancy dashboard until we have signal.

## What NOT to do

- **Do not tune prompts on the trades that informed the tuning.** You will overfit. Maintain a proper holdout: e.g., prompts are frozen for 4 weeks at a time, and the trades from those 4 weeks are the clean evaluation set for that prompt version.
- **Do not report cumulative P&L as the headline metric early on.** Variance is high; you can look like a genius or an idiot for reasons unrelated to skill. Calibration curve first, P&L later.
- **Do not silently drop resolved markets** from calibration analysis even if the outcome was "surprising." Surprises are information.
