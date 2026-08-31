"""Subscribe to MCP resource updates so a watch-gated plugin stays live.

Resources/list and resources/read already snapshot a URI. A plugin that
unlocks only after ``resources/subscribe`` plus ``notifications/resources/updated``
is still treated as read-once: Unbound never subscribes, the resource stays
stale, and an update-gated tool returns an error even when the snapshot read
succeeds.

This module closes that hole:

- speak ``resources/subscribe`` and ``resources/unsubscribe`` on the live session
- consume ``notifications/resources/updated`` after a subscription
- keep a skip-subscribe path so the stale-snapshot hole stays falsifiable
- let an update-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after cancellation
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.mcp_cancellation import MCP_CANCELLATION_GOAL, MCP_CANCELLATION_ID
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_resource_text,
    extract_resource_updated,
)
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_resources import MCP_RESOURCES_GOAL, MCP_RESOURCES_ID

SCHEMA_VERSION = 1
MCP_SUBSCRIBE_ID = "capability.mcp-resource-subscribe"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
WATCH_URI = "resource://blackhole/watch/unlock"
UNLOCK_TOKEN = "BH-WATCH-OK"
LOCKED_TOKEN = "locked"
UNSUBSCRIBED_ERROR = "resource subscription missing"

MCP_SUBSCRIBE_DONE_WHEN = (
    f"capability_exists:{MCP_SUBSCRIBE_ID};"
    f"capability_proved:{MCP_SUBSCRIBE_ID};"
    "no_skill_route"
)
MCP_SUBSCRIBE_GOAL = (
    "Repair MCP resource subscription watch plane: a hosted plugin that "
    "unlocks a resource only after resources/subscribe and "
    "notifications/resources/updated never receives a subscription, so an "
    "update-gated tool cannot see the changed URI and returns an error. "
    "Sessions that skip subscribe stay stale."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after the watch fires.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}

_WATCH_RESOURCE = {
    "uri": WATCH_URI,
    "name": "watch-unlock",
    "description": "Unlock token that changes only after a resource subscription.",
    "mimeType": "text/plain",
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays stale until resources/subscribe updates it."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_resource_subscribe", "gated"]


def mcp_subscribe_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_resource_subscribe import "
        "builtin_mcp_resource_subscribe_proof; r=builtin_mcp_resource_subscribe_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_resource_subscribe' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_resource_subscribe_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_SUBSCRIBE_ID,
        name="MCP resource subscription watch plane",
        description=(
            "An MCP stdio session subscribes to a resource URI so "
            "notifications/resources/updated can unlock an update-gated tool. "
            "Skip-subscribe sessions stay on the stale snapshot even when "
            "resources/read already works."
        ),
        kind="python",
        entry="blackhole_agent.mcp_resource_subscribe:builtin_mcp_resource_subscribe_proof",
        proof_command=mcp_subscribe_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-resources",
            "capability.mcp-cancellation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_resource_subscribe.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that unlocks only after resources/subscribe and "
            "notifications/resources/updated is first-class: Unbound subscribes, "
            "consumes the update, and the update-gated tool returns the sealed "
            "payload, while skip-subscribe sessions stay stale and siblings keep "
            "serving."
        ),
        tags=("mcp", "resources", "subscribe", "watch", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T084342Z-2b73817f",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def builtin_mcp_resource_subscribe_proof() -> dict[str, Any]:
    """Hermetic proof: resources/subscribe plus updated unlocks a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_SUBSCRIBE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_SUBSCRIBE_GOAL) == (
        MCP_SUBSCRIBE_ID,
    )
    checks["resources_goal_is_not_subscribe"] = leftover_marker_ids(
        MCP_RESOURCES_GOAL
    ) == (MCP_RESOURCES_ID,)
    checks["cancellation_goal_is_not_subscribe"] = leftover_marker_ids(
        MCP_CANCELLATION_GOAL
    ) == (MCP_CANCELLATION_ID,)
    checks["resources_marker_stays_resources"] = (
        MCP_SUBSCRIBE_ID not in leftover_marker_ids(MCP_RESOURCES_GOAL)
    )
    checks["cancellation_marker_stays_cancellation"] = (
        MCP_SUBSCRIBE_ID not in leftover_marker_ids(MCP_CANCELLATION_GOAL)
    )
    checks["subscribe_goal_is_not_resources"] = MCP_RESOURCES_ID not in leftover_marker_ids(
        MCP_SUBSCRIBE_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_subscribe"] = (
        len(catalog) > 21
        and catalog[21]["id"] == MCP_SUBSCRIBE_ID
        and catalog[20]["id"] == MCP_CANCELLATION_ID
    )

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        listed = naive.list_resources()
        uris = {
            str(item.get("uri") or "")
            for item in listed.get("resources") or []
            if isinstance(item, Mapping)
        }
        snapshot = extract_resource_text(naive.read_resource(WATCH_URI))
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["gated_lists_watch_uri"] = WATCH_URI in uris
        checks["naive_read_stays_locked"] = snapshot == LOCKED_TOKEN
        checks["naive_skip_subscribe_is_error"] = (
            unread.get("isError") is True and UNSUBSCRIBED_ERROR in _extract_text(unread)
        )
        checks["naive_did_not_subscribe"] = naive.subscribed_uris == []
        checks["naive_got_no_updated_notification"] = (
            WATCH_URI not in extract_resource_updated(naive.server_notifications)
        )
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        advertised = live.server_capabilities.get("resources")
        live.subscribe_resource(WATCH_URI)
        updated = extract_resource_updated(live.server_notifications)
        token = extract_resource_text(live.read_resource(WATCH_URI))
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["gated_advertises_subscribe"] = (
            isinstance(advertised, Mapping) and advertised.get("subscribe") is True
        )
        checks["subscribe_records_uri"] = WATCH_URI in live.subscribed_uris
        checks["updated_notification_was_received"] = WATCH_URI in updated
        checks["subscribed_read_is_unlocked"] = token == UNLOCK_TOKEN
        checks["update_gated_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
        live.unsubscribe_resource(WATCH_URI)
        relocked = live.call_tool(GATED_TOOL_NAME, {"text": "after-unsub"})
        checks["unsubscribe_re_locks_tool"] = (
            WATCH_URI not in live.subscribed_uris
            and relocked.get("isError") is True
            and UNSUBSCRIBED_ERROR in _extract_text(relocked)
        )
    finally:
        live.kill()

    unknown = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        unknown.start()
        missing = False
        try:
            unknown.subscribe_resource("resource://blackhole/watch/missing")
        except McpProtocolError as exc:
            missing = "unknown resource" in str(exc).lower()
        checks["unknown_subscribe_fail_closed"] = missing
    finally:
        unknown.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        mixed.subscribe_resource("gated", WATCH_URI)
        gated_text = _echo_text(mixed, "gated", "from-gated")
        echoed = _echo_text(mixed, "live", "from-echo")
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("gated", "live")
            and gated_text == f"from-gated|{UNLOCK_TOKEN}"
            and echoed == "from-echo"
        )
    finally:
        mixed.close()

    skipped = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        skipped.list_resources("gated")
        skipped.read_resource("gated", WATCH_URI)
        unread = skipped.call_tool("gated", GATED_TOOL_NAME, {"text": "nope"})
        sibling = _echo_text(skipped, "live", "still-here")
        checks["skip_subscribe_stays_on_plane"] = (
            unread.get("isError") is True
            and UNSUBSCRIBED_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-subscribe-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_SUBSCRIBE_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_subscribe"] = (
        live_goal == MCP_SUBSCRIBE_GOAL
        and MCP_SUBSCRIBE_ID in live_done
        and live_source == "genesis_bind_resource_subscribe"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_resource_subscribe_capability()
    return {
        "ok": ok,
        "action": "mcp_resource_subscribe",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_SUBSCRIBE_GOAL,
        "done_when": MCP_SUBSCRIBE_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _resource_contents(text: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "uri": WATCH_URI,
                "mimeType": "text/plain",
                "text": text,
            }
        ]
    }


def run_stub_server() -> int:
    """Plugin whose echo tool stays stale until a resource subscription updates it."""

    subscribed: set[str] = set()
    body = LOCKED_TOKEN
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        method = message.get("method")
        if method == "notifications/initialized" or (
            "id" not in message and method is not None
        ):
            continue
        request_id = message.get("id")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {
                            "tools": {},
                            "resources": {"subscribe": True},
                        },
                        "serverInfo": {
                            "name": "blackhole-resource-subscribe-gated",
                            "version": "0",
                        },
                    },
                }
            )
            continue
        if method == "ping":
            _write({"jsonrpc": "2.0", "id": request_id, "result": {}})
            continue
        if method == "tools/list":
            _write({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [_ECHO_TOOL]}})
            continue
        if method == "resources/list":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"resources": [_WATCH_RESOURCE]},
                }
            )
            continue
        if method == "resources/templates/list":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"resourceTemplates": []},
                }
            )
            continue
        if method == "resources/read":
            uri = str(params.get("uri") or "")
            if uri != WATCH_URI:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32002,
                            "message": f"unknown resource: {uri}",
                        },
                    }
                )
                continue
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _resource_contents(body),
                }
            )
            continue
        if method == "resources/subscribe":
            uri = str(params.get("uri") or "")
            if uri != WATCH_URI:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32002,
                            "message": f"unknown resource: {uri}",
                        },
                    }
                )
                continue
            subscribed.add(uri)
            body = UNLOCK_TOKEN
            _write(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/resources/updated",
                    "params": {"uri": uri},
                }
            )
            _write({"jsonrpc": "2.0", "id": request_id, "result": {}})
            continue
        if method == "resources/unsubscribe":
            uri = str(params.get("uri") or "")
            if uri != WATCH_URI:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32002,
                            "message": f"unknown resource: {uri}",
                        },
                    }
                )
                continue
            subscribed.discard(uri)
            body = LOCKED_TOKEN
            _write({"jsonrpc": "2.0", "id": request_id, "result": {}})
            continue
        if method == "tools/call":
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            user_text = str(arguments.get("text") or "")
            if WATCH_URI not in subscribed:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [{"type": "text", "text": UNSUBSCRIBED_ERROR}],
                            "isError": True,
                        },
                    }
                )
                continue
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"{user_text}|{UNLOCK_TOKEN}",
                            }
                        ],
                        "isError": False,
                    },
                }
            )
            continue
        if request_id is not None:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "gated":
        raise SystemExit(f"unknown MCP resource-subscribe stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
