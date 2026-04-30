# llm/

Thin wrapper around the Anthropic SDK. All LLM calls in the project go through here.

## Responsibilities

1. **Caching** — key on `(model, prompt_hash, params_hash, tools_hash)`. Store in `llm_calls` table. Default TTL: infinite for deterministic calls (temperature=0), finite for sampled calls. **Critical for dev cost control.**
2. **Retry** — exponential backoff on 429s and 5xx. Give up after 5 attempts.
3. **Cost logging** — every call logs input tokens, output tokens, cache read/write tokens, model, estimated cost in USD. Never skip this.
4. **Structured output** — use Anthropic tool use for structured outputs. Pydantic model in, Pydantic model out. Don't JSON-parse freetext responses.
5. **Prompt caching** — use Anthropic's prompt caching for research and forecasting prompts where the system prompt is stable across many market calls. This is a huge cost saver.

## API shape

```python
async def call(
    *,
    model: str,
    system: str,
    messages: list[Message],
    tools: list[Tool] | None = None,
    output_model: type[BaseModel] | None = None,  # if set, uses tool use for structured output
    max_tokens: int = 4096,
    temperature: float = 0.0,
    prompt_version: str,  # required, for tracking
    cache_control: CachePolicy = CachePolicy.DEFAULT,
    purpose: str,  # e.g., "research", "forecast", "critic" — used for cost reporting
) -> LLMResponse[T]:
    ...
```

## What NOT to do

- **Do not import `anthropic` directly outside this module.** One import site, one place to change.
- **Do not skip the `purpose` parameter.** We need it to aggregate costs per pipeline stage.
- **Do not cache responses from the web-search-enabled research calls with infinite TTL.** News changes. Use a short TTL (e.g., 24h) or key on a news-freshness hash.
- **Do not increase temperature to "get more creative forecasts."** Forecaster is deterministic; variance comes from research variance, not decoding variance.

## Model choices (as of v0)

- Scanner: no LLM
- Research: Claude Sonnet with web search enabled — balance of quality and cost
- Forecaster: Claude Opus — highest quality reasoning, worth the cost since we make far fewer forecaster calls than research calls
- Critic: Claude Opus, different prompt and ideally a different system persona from the forecaster

Revisit these choices after M5 with actual calibration data per model.

## Cost budgeting

- Log cost per call, per market, per pipeline run, per day
- Hard ceiling in config (`max_daily_llm_cost_usd`) — if exceeded, pipeline halts and alerts
- Expect ~$0.10–$0.50 per market for a full pipeline run in v0
