# executor/

Paper-trading executor. In v0 this writes intended trades to the DB. **No real orders.**

## v0 contract

```python
def execute_paper(trade: ProposedTrade) -> FilledPaperTrade:
    """
    Simulates a fill at the current market midpoint (or better).
    Writes to trades table with status='filled_paper'.
    Returns the filled trade record.
    """
```

Fill model for v0:
- Assume fill at mid price plus a realistic slippage assumption (5 bps? Configurable)
- Assume fee of X bps per side (check Polymarket current fee schedule)
- Log intended price, assumed fill price, assumed fees separately so we can refine later

## Why we're deliberately NOT building real execution in v0

1. We don't know if the forecaster has edge yet. Running real trades before measuring calibration is guaranteed negative EV.
2. Real execution has many failure modes (API auth, key management, order types, partial fills, cancels) that distract from the main question.
3. Once we decide the system has edge (or doesn't), real execution is 1–2 days of careful work. It's not the critical path.

## What would v1 real execution look like (later)

- `py-clob-client` for Polymarket order placement
- Hot wallet with capped funds (never more than we'd lose willingly)
- Order types: limit orders, not market orders (give the book a chance to fill at our price)
- Circuit breakers: max daily trade count, max daily loss, halt on anomalies
- A killswitch command that cancels all open orders and halts the scheduler
- Alerts on: fills, rejections, unexpected states

## What NOT to do now

- **Do not add a real-execution path "just behind a flag".** Flags get flipped. This is how people lose money. v0 has one execution path: paper.
- **Do not fake fills at prices better than what was actually available in the book.** If we assume unrealistic fills now, our paper P&L will be systematically better than real P&L would have been, and we'll make a bad real-money decision later. Model fills conservatively.
