# scanner/

Finds candidate markets on Polymarket worth researching. **No LLM.**

## Responsibilities

1. Pull open markets from Polymarket CLOB API
2. Filter by criteria:
   - Liquidity (orderbook depth) above threshold (default: $50K within 5% of mid)
   - Resolution date within horizon (default: 14 days ≤ resolution ≤ 180 days)
   - Not already researched in last 72h (unless flagged as high-news-velocity)
   - Not in excluded categories (sports games resolving in <24h are too fast-moving for our flow)
3. Write filtered shortlist to a daily `scan_results` record
4. Also: daily snapshot of midpoint + depth for every tracked market (for later regression analysis)

## Polymarket API notes

- CLOB base: `https://clob.polymarket.com`
- Markets endpoint: `/markets` — paginated, paginate all the way through
- Orderbook: `/book?token_id=...` — note Polymarket markets often have two tokens (YES and NO). Both orderbooks can be useful.
- Rate limits: be polite. 5 req/sec ceiling with retry on 429.
- `condition_id` is the stable market identifier. Always key on that.

## Filtering heuristics (start here, refine with data)

- Liquidity: `sum(bid_size * bid_price for bids within 5% of mid) + same for asks` — a proxy for "can I actually get filled at size?"
- Resolution window: shorter than 14 days is too noisy (weekend can flip things), longer than 6 months ties up capital without learning signal
- Category priors: politics and macro tend to have more LLM-tractable signals than sports or crypto in our initial thesis. Track win rate by category.

## What NOT to do

- **Do not call LLMs here.** If you find yourself wanting to, the logic belongs in the research stage.
- **Do not mutate existing markets rows.** If a market's metadata changes, insert a new `market_snapshots` row.
- **Do not skip markets because they "seem dumb."** Our job here is to cast a reasonable net; the research+forecaster+critic stages decide what's tradeable.

## Testing

- Mock the CLOB client with recorded fixtures (saved real responses in `tests/integration/fixtures/polymarket/`)
- Unit tests for filter logic with synthetic market objects
- Integration test that runs the scanner end-to-end against fixtures and asserts the shortlist is deterministic
