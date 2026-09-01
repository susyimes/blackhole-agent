"""Refresh tools/list after notifications/tools/list_changed so dynamic catalogs stay live.

Handshake snapshots ``tools/list`` once. Progress, subscribe, and roots
notifications already have first-class planes. A plugin that publishes a
gated tool only after ``notifications/tools/list_changed`` is still treated
as tools-only: Unbound never re-lists, the plane keeps the handshake
snapshot, and a catalog-gated tool stays invisible.

This module closes that hole:

- consume inbound ``notifications/tools/list_changed``
- re-list and replace the handshake snapshot
- keep a skip-refresh path so the stale snapshot stays falsifiable
- let a catalog-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after progress
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
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_tools_list_changed,
)
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_progress import MCP_PROGRESS_GOAL, MCP_PROGRESS_ID
from blackhole_agent.mcp_roots_list_changed import (
    MCP_ROOTS_CHANGED_GOAL,
    MCP_ROOTS_CHANGED_ID,
)

SCHEMA_VERSION = 1
MCP_TOOLS_CHANGED_ID = "capability.mcp-tools-list-changed"
REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_TOOL_NAME = "bootstrap"
GATED_TOOL_NAME = "echo"
UNLOCK_TOKEN = "BH-TOOLS-CHANGED-OK"
STALE_ERROR = "catalog snapshot stale"

MCP_TOOLS_CHANGED_DONE_WHEN = (
    f"capability_exists:{MCP_TOOLS_CHANGED_ID};"
    f"capability_proved:{MCP_TOOLS_CHANGED_ID};"
    "no_skill_route"
)
MCP_TOOLS_CHANGED_GOAL = (
    "Repair MCP dynamic tool catalog refresh: a hosted plugin that emits "
    "notifications/tools/list_changed after the first tools/list never "
    "triggers a re-list, so a dynamically published tool stays invisible and "
    "returns an error instead of the sealed payload. Sessions that skip the "
    "refresh keep the stale snapshot falsifiable."
)

_BOOTSTRAP_TOOL = {
    "name": BOOTSTRAP_TOOL_NAME,
    "description": "Always-present bootstrap tool on the pre-refresh catalog.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}
_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after a catalog refresh.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays hidden until tools/list is refreshed."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_tools_list_changed", "gated"]


def mcp_tools_list_changed_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_tools_list_changed import "
        "builtin_mcp_tools_list_changed_proof; r=builtin_mcp_tools_list_changed_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_tools_list_changed' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_tools_list_changed_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_TOOLS_CHANGED_ID,
        name="MCP dynamic tool catalog refresh",
        description=(
            "An MCP session consumes notifications/tools/list_changed and "
            "re-lists tools so a plugin that publishes a tool after the "
            "handshake snapshot can return its result. Sessions "
            "that skip the refresh stay fail-closed on the stale snapshot."
        ),
        kind="python",
        entry="blackhole_agent.mcp_tools_list_changed:builtin_mcp_tools_list_changed_proof",
        proof_command=mcp_tools_list_changed_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-progress",
            "capability.mcp-roots-list-changed",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_tools_list_changed.py",
            "src/blackhole_agent/mcp_echo_server.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that publishes a gated tool only after "
            "notifications/tools/list_changed is first-class: Unbound "
            "consumes the catalog notification, re-lists, replaces the "
            "handshake snapshot, and the dynamically published tool returns the "
            "sealed payload, while skip-refresh sessions stay fail-closed "
            "and siblings keep serving."
        ),
        tags=("mcp", "tools", "listChanged", "catalog", "jsonrpc", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T052359Z-a7d2d7d3",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _gated_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def builtin_mcp_tools_list_changed_proof() -> dict[str, Any]:
    """Hermetic proof: a tools/list_changed refresh unlocks a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mission_selection import (
        capability_family,
        semantic_signature,
        semantic_similarity,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_TOOLS_CHANGED_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL) == (
        MCP_TOOLS_CHANGED_ID,
    )
    checks["progress_goal_is_not_tools_changed"] = leftover_marker_ids(
        MCP_PROGRESS_GOAL
    ) == (MCP_PROGRESS_ID,)
    checks["roots_goal_is_not_tools_changed"] = leftover_marker_ids(
        MCP_ROOTS_CHANGED_GOAL
    ) == (MCP_ROOTS_CHANGED_ID,)
    checks["tools_changed_goal_is_not_progress"] = (
        MCP_PROGRESS_ID not in leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL)
    )
    checks["tools_changed_goal_is_not_roots"] = (
        MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL)
    )
    checks["progress_marker_stays_progress"] = (
        MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(MCP_PROGRESS_GOAL)
    )
    checks["roots_marker_stays_roots"] = MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(
        MCP_ROOTS_CHANGED_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_tools_changed"] = (
        len(catalog) > 28
        and catalog[28]["id"] == MCP_TOOLS_CHANGED_ID
        and catalog[27]["id"] == MCP_PROGRESS_ID
    )
    family = capability_family(MCP_TOOLS_CHANGED_GOAL)
    checks["family_is_catalog"] = "catalog" in family
    checks["family_is_not_progress"] = "progress" not in family
    checks["family_is_not_webhook"] = "webhook" not in family
    checks["family_is_not_worktree"] = "worktree" not in family
    checks["family_is_not_browser"] = "browser" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["not_a_progress_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
            semantic_signature(MCP_PROGRESS_GOAL),
        )
        < 0.82
    )
    checks["not_a_roots_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
            semantic_signature(MCP_ROOTS_CHANGED_GOAL),
        )
        < 0.82
    )

    with McpStdioSession(echo_server_command()) as echo:
        advertised = echo.server_capabilities.get("tools")
        first = echo.list_tools()
        names = tuple(
            str(item.get("name") or "")
            for item in (first.get("tools") or [])
            if isinstance(item, Mapping)
        )
        echoed = _extract_text(echo.call_tool(GATED_TOOL_NAME, {"text": "plain"}))
        checks["echo_advertises_list_changed"] = (
            isinstance(advertised, Mapping) and advertised.get("listChanged") is True
        )
        checks["echo_lists_static_catalog"] = "echo" in names and "sha256" in names
        checks["echo_without_refresh_still_serves"] = echoed == "plain"
        checks["echo_emits_no_list_changed"] = (
            extract_tools_list_changed(echo.server_notifications) == ()
        )

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        advertised = naive.server_capabilities.get("tools")
        first = naive.list_tools()
        first_names = tuple(
            str(item.get("name") or "")
            for item in (first.get("tools") or [])
            if isinstance(item, Mapping)
        )
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_advertises_list_changed"] = (
            isinstance(advertised, Mapping) and advertised.get("listChanged") is True
        )
        checks["naive_first_list_hides_echo"] = (
            BOOTSTRAP_TOOL_NAME in first_names and GATED_TOOL_NAME not in first_names
        )
        checks["naive_skip_refresh_is_error"] = (
            unread.get("isError") is True and STALE_ERROR in _extract_text(unread)
        )
        checks["naive_snapshot_stays_bootstrap"] = naive.tool_names == [BOOTSTRAP_TOOL_NAME]
        checks["naive_saw_list_changed"] = (
            extract_tools_list_changed(naive.server_notifications) != ()
        )
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        first = live.list_tools()
        first_names = tuple(
            str(item.get("name") or "")
            for item in (first.get("tools") or [])
            if isinstance(item, Mapping)
        )
        refreshed = live.refresh_tools()
        refresh_names = tuple(
            str(item.get("name") or "")
            for item in (refreshed.get("tools") or [])
            if isinstance(item, Mapping)
        )
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["live_first_list_hides_echo"] = (
            BOOTSTRAP_TOOL_NAME in first_names and GATED_TOOL_NAME not in first_names
        )
        checks["live_refresh_publishes_echo"] = GATED_TOOL_NAME in refresh_names
        checks["live_snapshot_includes_echo"] = GATED_TOOL_NAME in live.tool_names
        checks["published_tool_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
        checks["live_consumed_list_changed"] = (
            extract_tools_list_changed(live.server_notifications) != ()
            and live.tool_list_count >= 2
        )
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        before = mixed.advertised_tools("gated")
        mixed.refresh_tools("gated")
        gated_text = _gated_text(mixed, "gated", "from-gated")
        echoed = _extract_text(mixed.call_tool("live", GATED_TOOL_NAME, {"text": "from-echo"}))
        checks["handshake_snapshot_hides_echo"] = (
            BOOTSTRAP_TOOL_NAME in before and GATED_TOOL_NAME not in before
        )
        checks["plane_refresh_publishes_echo"] = GATED_TOOL_NAME in mixed.advertised_tools(
            "gated"
        )
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
        unread = skipped.call_tool("gated", GATED_TOOL_NAME, {"text": "nope"})
        sibling = _extract_text(
            skipped.call_tool("live", GATED_TOOL_NAME, {"text": "still-here"})
        )
        checks["skip_refresh_stays_on_plane"] = (
            unread.get("isError") is True
            and STALE_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
            and GATED_TOOL_NAME not in skipped.advertised_tools("gated")
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-tools-changed-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_TOOLS_CHANGED_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_tools_changed"] = (
        live_goal == MCP_TOOLS_CHANGED_GOAL
        and MCP_TOOLS_CHANGED_ID in live_done
        and live_source == "genesis_bind_tools_list_changed"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_tools_list_changed_capability()
    return {
        "ok": ok,
        "action": "mcp_tools_list_changed",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_TOOLS_CHANGED_GOAL,
        "done_when": MCP_TOOLS_CHANGED_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _ok(request_id: Any, text: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        },
    }


def run_stub_server() -> int:
    """Plugin whose echo tool stays hidden until tools/list is refreshed."""

    list_count = 0
    published = False
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
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {
                            "name": "blackhole-tools-list-changed-gated",
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
            list_count += 1
            tools = [_BOOTSTRAP_TOOL]
            if list_count >= 2:
                tools.append(_ECHO_TOOL)
                published = True
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": tools},
                }
            )
            if list_count == 1:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/tools/list_changed",
                    }
                )
            continue
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = (
                params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            )
            user_text = str(arguments.get("text") or "")
            if name == BOOTSTRAP_TOOL_NAME:
                _write(_ok(request_id, user_text or BOOTSTRAP_TOOL_NAME))
                continue
            if name == GATED_TOOL_NAME:
                if not published:
                    _write(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "content": [{"type": "text", "text": STALE_ERROR}],
                                "isError": True,
                            },
                        }
                    )
                    continue
                _write(_ok(request_id, f"{user_text}|{UNLOCK_TOKEN}"))
                continue
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": f"unknown tool: {name}"},
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
        raise SystemExit(f"unknown MCP tools list-changed stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
