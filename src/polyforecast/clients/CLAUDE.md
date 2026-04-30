# clients/

HTTP clients for external services (Polymarket CLOB, news APIs if we add them).

## Design principles

- **One client per external service.** `PolymarketClient`, `NewsClient`, etc.
- **Async by default.** Use `httpx.AsyncClient`. HTTP I/O should never block the event loop.
- **Retry with jittered exponential backoff.** Give up after a reasonable number of attempts; don't retry 4xx errors other than 429.
- **Typed responses.** Every method returns a Pydantic model, not a raw dict.
- **Don't leak the client type into business logic.** Stages should depend on an interface (`Protocol`) defined here, with concrete implementation injected.

## Polymarket client

- Base URL: `https://clob.polymarket.com`
- No auth required for read endpoints in v0 (browsing, orderbook)
- Auth (proxy/signature) required for trading — deferred to v1
- Methods:
  - `list_markets(active=True, category=None) -> list[Market]`
  - `get_market(condition_id: str) -> Market`
  - `get_orderbook(token_id: str) -> Orderbook`
  - `get_trades(condition_id: str, since: datetime) -> list[Trade]`

## Testing

- Record real API responses to `tests/integration/fixtures/polymarket/*.json` with a script (`scripts/record_polymarket_fixtures.py`)
- Unit tests use `respx` or similar to mock HTTP
- Don't hit the real API in unit tests, and be judicious in integration tests — we don't want to burn our rate-limit quota

## What NOT to do

- **Do not bake request rate limits into business logic.** The client handles throttling. Stages should just `await client.do_thing()` and not know about rate limits.
- **Do not cache inside the client.** Caching happens at the stage level, where the semantics of "is this stale?" is known. The client is just a thin RPC layer.
