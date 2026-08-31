"""Speak MCP resources/list and resources/read so resource-gated plugins stay live.

Tools/list and tools/call are first-class. A plugin that exposes a resource
data plane is still treated as tools-only: Unbound never calls
``resources/list`` or ``resources/read``, a resource-gated tool sees its
unlock URI unread, and the call returns an error instead of a sealed payload.

This module closes that hole:

- advertise and answer ``resources/list``, ``resources/templates/list``,
  and ``resources/read`` on the live stdio (and HTTP) session
- keep a skip-read path so the unread hole stays falsifiable
- let a resource-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after sampling
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
from blackhole_agent.mcp_client import (
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_resource_text,
)
from blackhole_agent.mcp_echo_server import ABOUT_URI, NOTE_PREFIX
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_sampling import MCP_SAMPLING_GOAL, MCP_SAMPLING_ID

SCHEMA_VERSION = 1
MCP_RESOURCES_ID = "capability.mcp-resources"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
UNLOCK_URI = "resource://blackhole/unlock"
UNLOCK_TOKEN = "BH-RESOURCE-OK"
UNREAD_ERROR = "unlock resource unread"

MCP_RESOURCES_DONE_WHEN = (
    f"capability_exists:{MCP_RESOURCES_ID};"
    f"capability_proved:{MCP_RESOURCES_ID};"
    "no_skill_route"
)
MCP_RESOURCES_GOAL = (
    "Repair MCP resource data plane failure: a hosted plugin that exposes "
    "resources/list and resources/read never answers those methods, so a "
    "resource-gated tool cannot read its unlock URI and returns an error "
    "instead of the sealed payload. Fail-closed sessions that skip the "
    "resource read stay forbidden."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after the resource is read.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}

_UNLOCK_RESOURCE = {
    "uri": UNLOCK_URI,
    "name": "unlock",
    "description": "Session unlock token for the resource-gated echo tool.",
    "mimeType": "text/plain",
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays forbidden until resources/read unlocks it."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_resources", "gated"]


def mcp_resources_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_resources import "
        "builtin_mcp_resources_proof; r=builtin_mcp_resources_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_resources' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_resources_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_RESOURCES_ID,
        name="MCP resource data plane",
        description=(
            "An MCP session lists and reads resources so a resource-gated "
            "plugin unlocks and returns its tool result instead of an unread "
            "error. Skip-read sessions stay fail-closed."
        ),
        kind="python",
        entry="blackhole_agent.mcp_resources:builtin_mcp_resources_proof",
        proof_command=mcp_resources_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-sampling",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_resources.py",
            "src/blackhole_agent/mcp_echo_server.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that exposes resources/list and resources/read is "
            "first-class: Unbound lists and reads the unlock URI so a "
            "resource-gated tool returns the sealed payload instead of an "
            "unread error, while skip-read sessions stay fail-closed and "
            "siblings keep serving."
        ),
        tags=("mcp", "resources", "data-plane", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T051852Z-990f731c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def builtin_mcp_resources_proof() -> dict[str, Any]:
    """Hermetic proof: resources/list and resources/read unlock a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_RESOURCES_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_RESOURCES_GOAL) == (MCP_RESOURCES_ID,)
    checks["sampling_goal_is_not_resources"] = leftover_marker_ids(MCP_SAMPLING_GOAL) == (
        MCP_SAMPLING_ID,
    )
    checks["sampling_marker_stays_sampling"] = MCP_RESOURCES_ID not in leftover_marker_ids(
        MCP_SAMPLING_GOAL
    )
    checks["call_goal_is_not_resources"] = leftover_marker_ids(MCP_CALL_GOAL) != (
        MCP_RESOURCES_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_resources"] = (
        len(catalog) > 15
        and catalog[15]["id"] == MCP_RESOURCES_ID
        and catalog[14]["id"] == MCP_SAMPLING_ID
    )

    with McpStdioSession(echo_server_command()) as echo:
        advertised = echo.server_capabilities.get("resources")
        listed = echo.list_resources()
        uris = {
            str(item.get("uri") or "")
            for item in listed.get("resources") or []
            if isinstance(item, Mapping)
        }
        about = extract_resource_text(echo.read_resource(ABOUT_URI))
        templates = echo.list_resource_templates()
        template_uris = {
            str(item.get("uriTemplate") or "")
            for item in templates.get("resourceTemplates") or []
            if isinstance(item, Mapping)
        }
        note_uri = f"{NOTE_PREFIX}sentinel"
        note = extract_resource_text(echo.read_resource(note_uri))
        missing = False
        try:
            echo.read_resource("resource://blackhole/echo/missing")
        except McpProtocolError as exc:
            missing = "unknown resource" in str(exc).lower()
        checks["echo_advertises_resources"] = isinstance(advertised, Mapping)
        checks["echo_lists_about_resource"] = ABOUT_URI in uris
        checks["echo_reads_about_resource"] = about == "blackhole-echo-mcp"
        checks["echo_lists_note_template"] = (
            "resource://blackhole/echo/note/{id}" in template_uris
        )
        checks["echo_reads_template_uri"] = note == "note:sentinel"
        checks["echo_unknown_resource_fail_closed"] = missing

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_skip_read_is_error"] = (
            unread.get("isError") is True and UNREAD_ERROR in _extract_text(unread)
        )
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        listed = live.list_resources()
        uris = {
            str(item.get("uri") or "")
            for item in listed.get("resources") or []
            if isinstance(item, Mapping)
        }
        token = extract_resource_text(live.read_resource(UNLOCK_URI))
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["gated_lists_unlock_uri"] = UNLOCK_URI in uris
        checks["gated_reads_unlock_token"] = token == UNLOCK_TOKEN
        checks["resource_gated_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        mixed.read_resource("gated", UNLOCK_URI)
        gated_text = _echo_text(mixed, "gated", "from-gated")
        echoed = _echo_text(mixed, "live", "from-echo")
        about = extract_resource_text(mixed.read_resource("live", ABOUT_URI))
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("gated", "live")
            and gated_text == f"from-gated|{UNLOCK_TOKEN}"
            and echoed == "from-echo"
            and about == "blackhole-echo-mcp"
        )
    finally:
        mixed.close()

    skipped = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        unread = skipped.call_tool("gated", GATED_TOOL_NAME, {"text": "nope"})
        sibling = _echo_text(skipped, "live", "still-here")
        checks["skip_read_stays_on_plane"] = (
            unread.get("isError") is True
            and UNREAD_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-resources-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_RESOURCES_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_resources"] = (
        live_goal == MCP_RESOURCES_GOAL
        and MCP_RESOURCES_ID in live_done
        and live_source == "genesis_bind_resources"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_resources_capability()
    return {
        "ok": ok,
        "action": "mcp_resources",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_RESOURCES_GOAL,
        "done_when": MCP_RESOURCES_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _resource_contents() -> dict[str, Any]:
    return {
        "contents": [
            {
                "uri": UNLOCK_URI,
                "mimeType": "text/plain",
                "text": UNLOCK_TOKEN,
            }
        ]
    }


def run_stub_server() -> int:
    """Plugin whose echo tool stays forbidden until resources/read unlocks it."""

    unlocked = False
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
                        "capabilities": {"tools": {}, "resources": {}},
                        "serverInfo": {"name": "blackhole-resource-gated", "version": "0"},
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
                    "result": {"resources": [_UNLOCK_RESOURCE]},
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
            if uri != UNLOCK_URI:
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
            unlocked = True
            _write({"jsonrpc": "2.0", "id": request_id, "result": _resource_contents()})
            continue
        if method == "tools/call":
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            user_text = str(arguments.get("text") or "")
            if not unlocked:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [{"type": "text", "text": UNREAD_ERROR}],
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
        raise SystemExit(f"unknown MCP resource stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
