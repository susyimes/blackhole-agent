# Retrying capability invocations

Clients can safely repeat a `POST /invoke` by supplying a stable
`Idempotency-Key` for one logical operation. Choose a new key for new work,
and keep the original key when recovering from a connection error.

```http
POST /invoke HTTP/1.1
Content-Type: application/json
Idempotency-Key: report-2026-09-13

{"capability_id":"capability.absorbed-text-reverser","input":{"raw_text":"blackhole"}}
```

The first request executes the existing governed invocation path and saves
its HTTP status and JSON response before sending them. A repeat with the
same capability ID and input replays that response, even after a server
restart or through another server serving the same root. Object key order
does not affect request identity. The response header
`Idempotency-Replayed: true` identifies a saved response; the original has
`false`. Error responses are saved too: a tool can perform a side effect
before returning an error.

`GET /invocations/report-2026-09-13` retrieves the request digest, state,
original `status_code`, and `response`. It requires no resubmission of the
input. A missing key returns 404.

| State or error | Meaning and client action |
| --- | --- |
| `completed` | The saved response is available. A repeat POST replays it. |
| `in_progress` | This server is still executing the request. A repeat POST returns 409; poll the receipt. |
| `outcome_unknown` | A reservation exists, but this server cannot confirm completion. This includes interrupted work and work owned by another server. A repeat POST returns 409. Reconcile the external effect; polling may still reveal completion by the original server. |
| `idempotency_conflict` | The key belongs to a different capability ID or input. POST returns 409 and performs no work. |
| `receipt_store_unavailable` | Persistence failed. HTTP 503 may occur before execution or while recording its result. Keep the same key when checking recovery. |

Keys accept 1–128 ASCII letters, digits, `.`, `_`, `:`, and `-`. Empty,
invalid, or multiple key headers return 400. The header is supported only
on `POST /invoke`; sending it to another POST route returns 400 instead of
implying retry protection. Unkeyed requests retain their existing behavior.

Reservations and results are stored in
`<root>/.blackhole-agent/invocation-receipts.sqlite3`. SQLite transactions
with full synchronization commit each reservation before execution and
each response before delivery. The database lock is released while the
tool runs, so independent keys continue executing. Records contain the
request digest and response, not a second copy of the input. Response data
may itself contain values returned by the tool.

Receipts have no automatic expiration, deletion, or retry. Preserve the
database with the service root: removing it also removes retry protection.
An interrupted reservation cannot guarantee whether the external side
effect happened, so the service never clears it automatically or promises
exactly-once effects inside arbitrary tools. After reconciling an unknown
outcome, an operator may deliberately issue new work with a new key.

Acceptance: `uv run python tests/acceptance/test_durable_invocation.py`
starts independent service processes, executes an actual append tool,
drops a response, and kills a service after an append. It checks effects
and HTTP responses without reading the receipt database. The same probe
fails behaviorally against the pre-change implementation.
