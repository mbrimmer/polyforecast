# sizer/

Deterministic position sizing. **No LLM.**

## Responsibilities

1. Given a forecast `p` (post-critic) and market price `m`, decide:
   - Should we trade?
   - If yes, which side (YES or NO)?
   - If yes, how large?
2. Apply portfolio-level constraints (max exposure per market, per category, per correlated cluster)
3. Apply absolute constraints (max position as % of bankroll, min trade size to avoid dust)

## Core formula (Kelly fraction)

For buying YES at price `m` with forecast probability `p` (where `p > m`):

```
edge = p - m
kelly_full = edge / (1 - m)       # full Kelly as fraction of bankroll
kelly_fraction = kelly_full * kelly_multiplier   # typically 0.25
position_size_usd = bankroll * kelly_fraction
```

For buying NO at price `1 - m` with forecast probability `1 - p` (where `p < m`):

```
edge = (1 - p) - (1 - m) = m - p
kelly_full = edge / m
kelly_fraction = kelly_full * kelly_multiplier
position_size_usd = bankroll * kelly_fraction
```

## Thresholds

Don't trade unless:
- `|p - m| > edge_threshold_points` (default: 0.05 = 5 points)
- `|p - m| > 2 * (fee_bps + slippage_bps) / 10000` (so edge exceeds round-trip costs with margin)
- Forecast confidence interval isn't so wide that the edge is within the error bars (i.e., `|p - m| > 0.5 * CI_width`)

## Portfolio constraints

- Max single-trade size: 5% of bankroll
- Max exposure to one market: 10% of bankroll (in case we layer multiple trades)
- Max exposure to one category (politics, macro, etc.): 40% of bankroll
- **Correlated-cluster flagging**: if a new trade would be in a cluster (e.g., "Trump wins FL" and "Trump wins OH" are obviously correlated), flag for manual review in v0. We'll get smarter about this after we have data.

## What NOT to do

- **Do not full-Kelly.** Our probability estimates are uncertain; full Kelly assumes they're exact. Fractional Kelly (1/4) is the default and the right default.
- **Do not skip the edge threshold.** Tiny edges are almost always noise. Trading them is how you pay a thousand small costs for no expected gain.
- **Do not use LLM here.** This is math. If you feel the pull to ask the LLM "should I trade this?", you're doing it wrong — encode the logic as rules so we can reason about them.

## Testing

- Unit tests for the Kelly math with known inputs/outputs
- Property tests: Kelly size is monotonic in edge, position size is 0 when below threshold, etc.
- Integration test: feed in a synthetic set of forecasts and assert the trade list matches expectations
