# forecaster/

Produces the probability estimate. **Blind to current market price.** This is the most important architectural rule in the project.

## Output (Pydantic model)

```python
class Forecast(BaseModel):
    market_id: str
    dossier_id: int
    prompt_version: str
    model: str

    probability_yes: float  # 0.0 to 1.0
    confidence_interval_low: float  # e.g., 10th percentile
    confidence_interval_high: float  # e.g., 90th percentile

    reasoning: str  # freeform, for later review
    key_drivers: list[str]  # top factors behind the estimate
    scenarios_considered: list[Scenario]  # each with prob and resulting outcome

    # Meta
    self_rated_confidence: Literal["high", "medium", "low"]
    untradeable: bool  # forecaster can refuse if dossier is insufficient
    untradeable_reason: str | None
```

## Prompting principles

- **Decompose first.** Outside view base rate → inside view adjustments → final estimate. Don't let the model jump to a number.
- **Consider scenarios explicitly.** "What's the probability of the 3–5 distinct paths by which this resolves YES? NO?" Makes the reasoning auditable.
- **Reason about confidence.** A forecast of 0.60 can be "definitely between 0.55 and 0.65" or "probably between 0.40 and 0.80". The interval matters for sizing.
- **Permission to refuse.** If the dossier is too thin or the question is fundamentally unforecasatable (e.g., a coin flip), the model should set `untradeable=True`. This is a feature not a bug — not every market deserves a trade.

## Calibration hygiene

- `temperature=0`. We want reproducible forecasts. Variance should come from dossier variance, not decoding noise.
- Never show the model its past forecasts on similar markets (risk of anchoring to its own prior).
- Never show the model the current market price. **This is non-negotiable.**
- Show the model the resolution criteria verbatim (not paraphrased).

## Prompt structure

System prompt: persona (a careful superforecaster, calibrated, willing to say "I don't know"), methodology (outside view first), output format.

User message: the dossier, the question, explicit instruction to reason through decomposition before producing the final probability.

## What NOT to do

- **Do not show the market price.** Did I mention this? Don't do it.
- **Do not pass in a "hint" from the critic or from past forecasts.** Forecaster is independent.
- **Do not let the forecaster tool-use to go search more.** If the dossier is insufficient, return `untradeable=True` and improve the researcher. Keeping roles separate is what makes the pipeline debuggable.
- **Do not aggregate multiple forecaster runs into an ensemble** until you've measured whether the ensemble actually calibrates better on resolved data. Ensembles sound good but add cost and complexity.

## Future: forecast ensembles

Once we have 50+ resolved forecasts, experiment with:
- Running the forecaster 3x with different orderings of the dossier
- Running with two different system prompts (different personas)
- Aggregating via mean or trimmed mean
Only ship this if calibration demonstrably improves on a held-out set.
