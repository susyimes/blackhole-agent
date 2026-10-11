# Capability metadata in MCP hosts

The capability server exposes tools, resources, and prompts over both stdio
(`python -m blackhole_agent.mcp_capability_server --root PATH`) and the
invocation plane's Streamable HTTP endpoint (`POST /mcp`). An HTTP client
initializes a session and sends its returned `Mcp-Session-Id` on later
requests. `GET /mcp` with that session and `Accept: text/event-stream`
opens the reverse channel: `notifications/progress` for a `progressToken`
`tools/call` is written as SSE, a concurrent `POST` of
`notifications/cancelled` reaps the in-flight tool tree so the original
POST answers JSON-RPC `-32800`, and a ledger mutation that changes the
invocable set publishes `notifications/tools/list_changed` and
`notifications/resources/list_changed`. GET without a session is 404; GET that
does not accept the event stream is 406. When an operator token is
configured, every MCP request also requires `Authorization: Bearer TOKEN`,
including metadata reads and the GET stream.

Hosts can discover the JSON catalog with `resources/list`, then request:

```json
{"jsonrpc":"2.0","id":2,"method":"resources/read","params":{"uri":"blackhole://capabilities"}}
```

The returned text resource contains `count`, `capabilities`, and a
deterministic `catalog_digest`. Each capability has an `id`, `name`,
`requires`, `provides`, `available`, and `tool` descriptor with the same MCP
input/output schemas returned by `tools/list`. These are the proved absorbed
capabilities recognized by the invocation plane; general ledger proof
programs and the `solve_goal` meta-tool are not capability resources.

Each capability is also readable at
`blackhole://capabilities/{capability_id}`. `resources/templates/list`
advertises this template. `resources/list` paginates at 128 resources; pass
the returned `nextCursor` as the next request's `cursor` until absent. URIs
identify catalog data only and never open local files. The metadata excludes
commands, host paths, proof cases, and quarantine diagnostics.

`prompts/list` advertises `prepare_capability_call`. Its required
`capability_id` and optional `task` arguments are strings:

```json
{"jsonrpc":"2.0","id":3,"method":"prompts/get","params":{"name":"prepare_capability_call","arguments":{"capability_id":"capability.absorbed-text-reverser","task":"Reverse the text hello."}}}
```

The result contains user messages with instructions for supplying tool
arguments, the selected contract as an embedded JSON resource, and the
optional task text. Retrieval performs no tool execution. A host can use
the embedded tool name and input schema to prepare a subsequent `tools/call`.

Metadata refreshes when `capabilities/ledger.json` changes. Quarantined
capabilities remain inspectable with `available: false` and
`unavailable_reason: "resource_quarantined"`; prompt preparation refuses
them. Removed, unproved, or no-longer-invocable entries disappear on refresh.
Resource reads for unknown URIs return JSON-RPC `-32002`; invalid parameters,
cursor values, or prompt arguments return `-32602`. `initialize` advertises
`tools.listChanged` and `resources.listChanged`; connected GET `/mcp` streams
receive `notifications/tools/list_changed` (and resources) when the invocable
set changes so hosts re-list without disconnecting. Tool calls still
revalidate through the governed invocation path.

The wire formats follow MCP's
[resources](https://modelcontextprotocol.io/specification/2025-03-26/server/resources)
and [prompts](https://modelcontextprotocol.io/specification/2025-03-26/server/prompts)
specifications. The standalone acceptance probe
`tests/acceptance/test_mcp_capability_metadata.py` exercises discovery,
prompt preparation, real execution, authentication, and live removal. It
reports an unmet outcome against the prior tools-only metadata surface.
