"""Follow MCP nextCursor so a page-two gated tool becomes visible.

Handshake snapshots ``tools/list`` once. Catalog refresh already re-lists
after ``notifications/tools/list_changed``. A plugin that returns page one
with ``nextCursor`` and hides the gated tool on that page is still treated
as complete: Unbound never sends the cursor, ``refresh_tools`` asks for
page one again, and a page-two tool stays hidden.

This module closes that hole:

- send ``cursor`` on follow-up ``tools/list``
- merge pages until ``nextCursor`` is absent
- keep a skip-cursor path so the truncated page stays falsifiable
- prove ``refresh_tools`` cannot substitute for pagination
- let a cursor-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after watch
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
    extract_next_cursor,
    extract_tools_list_changed,
)
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_tools_list_changed import (
    MCP_TOOLS_CHANGED_GOAL,
    MCP_TOOLS_CHANGED_ID,
)
from blackhole_agent.watch_actuation import WATCH_ACTUATION_GOAL, WATCH_ACTUATION_ID

SCHEMA_VERSION = 1
MCP_CURSOR_ID = "capability.mcp-cursor-pagination"
REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_TOOL_NAME = "bootstrap"
GATED_TOOL_NAME = "echo"
UNLOCK_TOKEN = "BH-CURSOR-OK"
TRUNCATED_ERROR = "catalog page truncated"
PAGE_TWO_CURSOR = "page-2"

MCP_CURSOR_DONE_WHEN = (
    f"capability_exists:{MCP_CURSOR_ID};"
    f"capability_proved:{MCP_CURSOR_ID};"
    "no_skill_route"
)
MCP_CURSOR_GOAL = (
    "Repair MCP cursor-paginated catalog listing: a hosted plugin that returns "
    "nextCursor after the first tools/list never receives a follow-up list with "
    "that cursor, so a later-batch gated tool stays hidden and returns an error "
    "instead of the sealed payload. Sessions that skip the cursor keep the "
    "truncated listing falsifiable."
)

_BOOTSTRAP_TOOL = {
    "name": BOOTSTRAP_TOOL_NAME,
    "description": "Always-present bootstrap tool on the first catalog page.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}
_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after cursor pagination.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays hidden until tools/list follows nextCursor."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_cursor_pagination", "gated"]


def mcp_cursor_pagination_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_cursor_pagination import "
        "builtin_mcp_cursor_pagination_proof; r=builtin_mcp_cursor_pagination_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_cursor_pagination' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_cursor_pagination_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_CURSOR_ID,
        name="MCP cursor-paginated catalog listing",
        description=(
            "An MCP session follows tools/list nextCursor so a plugin that "
            "hides a gated tool on page one can return its result after the "
            "client requests page two. Sessions that skip the cursor stay "
            "fail-closed on the truncated page; refresh_tools cannot substitute."
        ),
        kind="python",
        entry="blackhole_agent.mcp_cursor_pagination:builtin_mcp_cursor_pagination_proof",
        proof_command=mcp_cursor_pagination_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-tools-list-changed",
            "capability.watch-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_cursor_pagination.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that hides a gated tool behind tools/list "
            "nextCursor is first-class: Unbound follows the cursor, merges "
            "pages, replaces the handshake snapshot, and the page-two tool "
            "returns the sealed payload, while skip-cursor sessions stay "
            "fail-closed, refresh_tools cannot substitute, and siblings keep serving."
        ),
        tags=("mcp", "tools", "cursor", "pagination", "nextCursor", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T113148Z-f5998410",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _gated_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def _tool_names(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(item.get("name") or "")
        for item in (payload.get("tools") or [])
        if isinstance(item, Mapping)
    )


def builtin_mcp_cursor_pagination_proof() -> dict[str, Any]:
    """Hermetic proof: following nextCursor unlocks a page-two gated plugin."""

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
    checks["denylists_self"] = MCP_CURSOR_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_CURSOR_GOAL) == (MCP_CURSOR_ID,)
    checks["watch_goal_is_not_cursor"] = leftover_marker_ids(WATCH_ACTUATION_GOAL) == (
        WATCH_ACTUATION_ID,
    )
    checks["tools_changed_goal_is_not_cursor"] = leftover_marker_ids(
        MCP_TOOLS_CHANGED_GOAL
    ) == (MCP_TOOLS_CHANGED_ID,)
    checks["cursor_goal_is_not_watch"] = WATCH_ACTUATION_ID not in leftover_marker_ids(
        MCP_CURSOR_GOAL
    )
    checks["cursor_goal_is_not_tools_changed"] = (
        MCP_TOOLS_CHANGED_ID not in leftover_marker_ids(MCP_CURSOR_GOAL)
    )
    checks["watch_marker_stays_watch"] = MCP_CURSOR_ID not in leftover_marker_ids(
        WATCH_ACTUATION_GOAL
    )
    checks["tools_changed_marker_stays_tools_changed"] = (
        MCP_CURSOR_ID not in leftover_marker_ids(MCP_TOOLS_CHANGED_GOAL)
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_cursor"] = (
        len(catalog) > 39
        and catalog[39]["id"] == MCP_CURSOR_ID
        and catalog[38]["id"] == WATCH_ACTUATION_ID
    )
    family = capability_family(MCP_CURSOR_GOAL)
    checks["family_is_cursor"] = "cursor" in family
    checks["family_is_paginated"] = "paginated" in family
    checks["family_is_catalog"] = "catalog" in family
    checks["family_is_not_watch"] = "watch" not in family
    checks["family_is_not_path"] = "path" not in family
    checks["family_is_not_object"] = "object" not in family
    checks["family_is_not_postgresql"] = "postgresql" not in family
    checks["family_is_not_ldap"] = "ldap" not in family
    checks["family_is_not_nameserver"] = "nameserver" not in family
    checks["family_is_not_mqtt"] = "mqtt" not in family
    checks["family_is_not_progress"] = "progress" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_browser"] = "browser" not in family
    checks["not_a_watch_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_CURSOR_GOAL),
            semantic_signature(WATCH_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_tools_changed_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_CURSOR_GOAL),
            semantic_signature(MCP_TOOLS_CHANGED_GOAL),
        )
        < 0.82
    )

    with McpStdioSession(echo_server_command()) as echo:
        first = echo.list_tools()
        names = _tool_names(first)
        paged = echo.paginate_tools()
        echoed = _extract_text(echo.call_tool(GATED_TOOL_NAME, {"text": "plain"}))
        checks["echo_first_page_has_no_cursor"] = extract_next_cursor(first) == ""
        checks["echo_lists_static_catalog"] = "echo" in names and "sha256" in names
        checks["echo_paginate_is_single_page"] = (
            GATED_TOOL_NAME in _tool_names(paged)
            and extract_next_cursor(paged) == ""
            and echoed == "plain"
        )
        checks["echo_emits_no_list_changed"] = (
            extract_tools_list_changed(echo.server_notifications) == ()
        )

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        first = naive.list_tools()
        first_names = _tool_names(first)
        refreshed = naive.refresh_tools()
        refresh_names = _tool_names(refreshed)
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_first_page_advertises_cursor"] = (
            extract_next_cursor(first) == PAGE_TWO_CURSOR
        )
        checks["naive_first_list_hides_echo"] = (
            BOOTSTRAP_TOOL_NAME in first_names and GATED_TOOL_NAME not in first_names
        )
        checks["refresh_tools_cannot_substitute"] = (
            BOOTSTRAP_TOOL_NAME in refresh_names
            and GATED_TOOL_NAME not in refresh_names
            and extract_next_cursor(refreshed) == PAGE_TWO_CURSOR
        )
        checks["naive_skip_cursor_is_error"] = (
            unread.get("isError") is True and TRUNCATED_ERROR in _extract_text(unread)
        )
        checks["naive_snapshot_stays_bootstrap"] = naive.tool_names == [BOOTSTRAP_TOOL_NAME]
        checks["naive_emits_no_list_changed"] = (
            extract_tools_list_changed(naive.server_notifications) == ()
        )
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        first = live.list_tools()
        first_names = _tool_names(first)
        paged = live.paginate_tools()
        page_names = _tool_names(paged)
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["live_first_list_hides_echo"] = (
            BOOTSTRAP_TOOL_NAME in first_names and GATED_TOOL_NAME not in first_names
        )
        checks["live_paginate_publishes_echo"] = (
            BOOTSTRAP_TOOL_NAME in page_names and GATED_TOOL_NAME in page_names
        )
        checks["live_snapshot_includes_echo"] = GATED_TOOL_NAME in live.tool_names
        checks["published_tool_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
        checks["live_consumed_cursor"] = (
            extract_next_cursor(first) == PAGE_TWO_CURSOR
            and extract_next_cursor(paged) == ""
            and live.tool_list_count >= 3
            and live.last_tools_cursor == ""
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
        mixed.paginate_tools("gated")
        gated_text = _gated_text(mixed, "gated", "from-gated")
        echoed = _extract_text(mixed.call_tool("live", GATED_TOOL_NAME, {"text": "from-echo"}))
        checks["handshake_snapshot_hides_echo"] = (
            BOOTSTRAP_TOOL_NAME in before and GATED_TOOL_NAME not in before
        )
        checks["plane_paginate_publishes_echo"] = GATED_TOOL_NAME in mixed.advertised_tools(
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
        checks["skip_cursor_stays_on_plane"] = (
            unread.get("isError") is True
            and TRUNCATED_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
            and GATED_TOOL_NAME not in skipped.advertised_tools("gated")
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-cursor-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_CURSOR_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_cursor"] = (
        live_goal == MCP_CURSOR_GOAL
        and MCP_CURSOR_ID in live_done
        and live_source == "genesis_bind_cursor_pagination"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_cursor_pagination_capability()
    return {
        "ok": ok,
        "action": "mcp_cursor_pagination",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_CURSOR_GOAL,
        "done_when": MCP_CURSOR_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
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
    """Plugin whose echo tool stays hidden until tools/list follows nextCursor."""

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
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "blackhole-cursor-pagination-gated",
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
            cursor = str(params.get("cursor") or "")
            if cursor == PAGE_TWO_CURSOR:
                published = True
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"tools": [_ECHO_TOOL]},
                    }
                )
                continue
            if cursor:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"tools": []},
                    }
                )
                continue
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [_BOOTSTRAP_TOOL],
                        "nextCursor": PAGE_TWO_CURSOR,
                    },
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
                                "content": [{"type": "text", "text": TRUNCATED_ERROR}],
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
        raise SystemExit(f"unknown MCP cursor pagination stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
