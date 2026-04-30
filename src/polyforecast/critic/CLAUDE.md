# critic/

Reviews the forecaster's output and either adjusts the probability or flags the forecast as untradeable. This is the one stage where the LLM IS allowed to see the market price.

## Output (Pydantic model)

```python
class CriticReview(BaseModel):
    forecast_id: int
    prompt_version: str
    model: str

    # Critique
    critique: str  # what's weak about the forecast
    missing_considerations: list[str]
    overconfidence_flags: list[str]

    # Adjustment
    adjusted_probability: float
    adjustment_reasoning: str

    # Kill-switch
    untradeable: bool
    untradeable_reason: str | None
```

## Why the critic CAN see the market price

When the forecaster says 0.65 and the market says 0.35, there are three possibilities:
1. The forecaster has an edge (good, trade it)
2. The market knows something the forecaster missed (find it)
3. The forecaster is miscalibrated (detect it)

Possibility 2 is what the critic is for. Given a large gap, the critic's job is to search for "what would make the market right?" The researcher may have missed an angle, the resolution criteria may have a subtle interpretation, there may be insider information encoded in the price movement.

**But the critic must not blindly shrink toward the market price.** That defeats the purpose. The adjustment should be driven by specific new considerations, not by "the market is usually right" vibes.

## Prompt principles

- Give the critic the dossier + forecast + current market price + recent price history
- Ask it to articulate the market's implied reasoning: "If the market is priced at 0.35, what would the market believe that the forecaster doesn't?"
- Then ask: "Is the market's implied reasoning correct? If yes, what's the adjusted probability? If no, explain."
- Preserve the forecaster's estimate when the critic can't find a concrete reason to adjust

## What NOT to do

- **Do not have the critic just average the forecaster's estimate with the market price.** Write code to do that if you want a baseline (and you should — it's a reasonable sanity baseline). But that's not what the critic is for.
- **Do not let critic adjustments exceed N points without strong reasoning.** Config: `max_critic_adjustment_points = 20`. If the critic wants to swing more than this, flag `untradeable=True` and investigate manually.
- **Do not use the same system prompt as the forecaster.** We want a different mental frame — skeptic, not analyst.

## Testing the critic's value

Log both the forecaster's raw probability AND the critic-adjusted probability on every market. After 50+ resolutions, compute Brier scores for both and compare. If the critic isn't improving calibration, simplify or remove it.
