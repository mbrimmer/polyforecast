# research/

Produces a structured research dossier per market. LLM + web search tool use.

## The dossier (Pydantic model)

```python
class ResearchDossier(BaseModel):
    market_id: str
    prompt_version: str

    # The most important field — resolution criteria quoted verbatim from Polymarket
    resolution_criteria_verbatim: str
    resolution_source: str  # what source determines the outcome

    # Decomposition
    key_sub_questions: list[str]
    key_facts: list[FactWithSource]  # each fact has a URL and retrieval date
    base_rate_analysis: str  # "similar events have resolved YES X% of the time because..."
    recent_news: list[NewsItem]
    expert_views: list[ExpertView]

    # Reasoning scaffolding
    arguments_for_yes: list[str]
    arguments_for_no: list[str]
    uncertainty_sources: list[str]  # what would change our mind

    # Meta
    research_quality_self_assessment: Literal["high", "medium", "low"]
    flags: list[str]  # e.g., "ambiguous_resolution", "insufficient_sources"
```

## Prompting principles

- **Quote resolution criteria verbatim.** Do not paraphrase. Models will want to paraphrase; the prompt must push hard against this. The prompt should say something like "copy the resolution criteria from the market page exactly, in quotes, even if it's wordy."
- **Separate outside view from inside view.** Base rates first (what happens in general for similar questions), then inside view (what's specific about this one).
- **Surface uncertainty, don't hide it.** A dossier that says "sources disagree" is more useful than one that papers over the disagreement.
- **Source everything.** Every factual claim should have a URL. Facts without sources should be flagged.

## Caching

- Cache dossiers for 72h keyed on `(market_id, prompt_version)`
- **Invalidate early** if: market's price has moved >10 points since last research, or >5 news items have been indexed about related keywords
- Store the raw web search results alongside the dossier (in `research_dossiers.raw_search_results`) for auditability

## What NOT to do

- **Do not have the research stage produce a probability estimate.** That's the forecaster's job. Research produces evidence; forecasting produces probability.
- **Do not let the researcher see the current market price.** Same anchoring concern as the forecaster. Research is independent evidence-gathering.
- **Do not cap web searches at 1–2.** Research is the place we spend tokens. 5–15 searches per market is reasonable for a thorough dossier.

## Prompt version bumps

Bump `PROMPT_VERSION` in `prompts.py` when you:
- Change any instruction meaningfully
- Change the output schema
- Change the number of worked examples
- Change the set of tools available

Do NOT bump for typo fixes that don't change behavior.

## Evaluation

- Every ~2 weeks, spot-check 10 random dossiers. Does it quote resolution criteria correctly? Are the base rates reasonable? Did it miss obvious sources?
- Correlate dossier quality self-assessment against subsequent forecast calibration. If self-assessed "low" dossiers produce well-calibrated forecasts, the self-assessment is useless. If they produce miscalibrated forecasts, gate on it.
