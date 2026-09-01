"""Push MCP workspace root changes so a worktree-gated plugin stays live.

Ping and roots/list already answer a probing plugin. After Unbound switches
to a sibling worktree the client still never sends
``notifications/roots/list_changed``: hosted plugins keep the controller
checkout, and a worktree-gated tool returns an error even when local roots
already point at the mission tree.

This module closes that hole:

- advertise ``roots.listChanged`` on initialize
- speak ``notifications/roots/list_changed`` after a worktree switch
- keep a replace-roots-without-notify path so the stale-checkout hole stays
  falsifiable
- let a worktree-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after subscribe
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    DEFAULT_MCP_ROOTS,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_root_uris,
)
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_resource_subscribe import MCP_SUBSCRIBE_GOAL, MCP_SUBSCRIBE_ID
from blackhole_agent.mcp_reverse_channel import MCP_REVERSE_GOAL, MCP_REVERSE_ID

SCHEMA_VERSION = 1
MCP_ROOTS_CHANGED_ID = "capability.mcp-roots-list-changed"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
CHECKOUT_URI = "file:///workspace"
WORKTREE_URI = "file:///mission-worktree"
WORKTREE_ROOTS: tuple[dict[str, str], ...] = (
    {"uri": WORKTREE_URI, "name": "mission-worktree"},
)
MISSING_ERROR = "workspace root change missing"
UNLOCK_TOKEN = WORKTREE_URI
ROOTS_REQUERY_ID = 91

MCP_ROOTS_CHANGED_DONE_WHEN = (
    f"capability_exists:{MCP_ROOTS_CHANGED_ID};"
    f"capability_proved:{MCP_ROOTS_CHANGED_ID};"
    "no_skill_route"
)
MCP_ROOTS_CHANGED_GOAL = (
    "Repair worktree-scoped MCP root notification: after Unbound switches to "
    "a sibling worktree, hosted plugins still list files from the controller "
    "checkout because notifications/roots/list_changed is never sent, so a "
    "worktree-gated tool cannot see the mission tree and returns an error. "
    "Sessions that skip the root-change notification stay on the stale checkout."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the worktree URI after roots change.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays locked until roots/list_changed retargets it."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_roots_list_changed", "gated"]


def mcp_roots_list_changed_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_roots_list_changed import "
        "builtin_mcp_roots_list_changed_proof; r=builtin_mcp_roots_list_changed_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_roots_list_changed' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_roots_list_changed_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_ROOTS_CHANGED_ID,
        name="MCP worktree roots listChanged plane",
        description=(
            "An MCP stdio session advertises roots.listChanged and pushes "
            "notifications/roots/list_changed after a worktree switch so a "
            "worktree-gated tool can re-query roots/list. Replacing local roots "
            "without the notification keeps the plugin on the stale checkout."
        ),
        kind="python",
        entry="blackhole_agent.mcp_roots_list_changed:builtin_mcp_roots_list_changed_proof",
        proof_command=mcp_roots_list_changed_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-reverse-channel",
            "capability.mcp-resource-subscribe",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_roots_list_changed.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that unlocks only after notifications/roots/"
            "list_changed plus a fresh roots/list is first-class: Unbound "
            "advertises listChanged, pushes the worktree switch, and the "
            "worktree-gated tool returns the sealed payload, while skip-notify "
            "sessions stay on the stale checkout and siblings keep serving."
        ),
        tags=("mcp", "roots", "worktree", "listChanged", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T021329Z-0177c9c2",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def _finish_gated_call(
    message: Mapping[str, Any],
    current_uris: Sequence[str],
    saw_change: bool,
) -> None:
    arguments = (message.get("params") or {}).get("arguments") or {}
    if not isinstance(arguments, Mapping):
        arguments = {}
    user_text = str(arguments.get("text") or "")
    if (not saw_change) or WORKTREE_URI not in current_uris:
        _write(
            {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "result": {
                    "content": [{"type": "text", "text": MISSING_ERROR}],
                    "isError": True,
                },
            }
        )
        return
    _write(
        {
            "jsonrpc": "2.0",
            "id": message.get("id"),
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


def builtin_mcp_roots_list_changed_proof() -> dict[str, Any]:
    """Hermetic proof: roots/list_changed plus a re-query unlocks a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_ROOTS_CHANGED_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL) == (
        MCP_ROOTS_CHANGED_ID,
    )
    checks["reverse_goal_is_not_roots_changed"] = leftover_marker_ids(
        MCP_REVERSE_GOAL
    ) == (MCP_REVERSE_ID,)
    checks["subscribe_goal_is_not_roots_changed"] = leftover_marker_ids(
        MCP_SUBSCRIBE_GOAL
    ) == (MCP_SUBSCRIBE_ID,)
    checks["reverse_marker_stays_reverse"] = (
        MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(MCP_REVERSE_GOAL)
    )
    checks["subscribe_marker_stays_subscribe"] = (
        MCP_ROOTS_CHANGED_ID not in leftover_marker_ids(MCP_SUBSCRIBE_GOAL)
    )
    checks["roots_changed_goal_is_not_reverse"] = MCP_REVERSE_ID not in leftover_marker_ids(
        MCP_ROOTS_CHANGED_GOAL
    )
    checks["roots_changed_goal_is_not_subscribe"] = (
        MCP_SUBSCRIBE_ID not in leftover_marker_ids(MCP_ROOTS_CHANGED_GOAL)
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_roots_changed"] = (
        len(catalog) > 22
        and catalog[22]["id"] == MCP_ROOTS_CHANGED_ID
        and catalog[21]["id"] == MCP_SUBSCRIBE_ID
    )

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        advertised = naive.client_capabilities.get("roots")
        naive.replace_roots(WORKTREE_ROOTS)
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_advertises_list_changed"] = (
            isinstance(advertised, Mapping) and advertised.get("listChanged") is True
        )
        checks["naive_local_roots_are_worktree"] = WORKTREE_URI in extract_root_uris(
            naive.roots
        )
        checks["naive_skip_notify_is_error"] = (
            unread.get("isError") is True and MISSING_ERROR in _extract_text(unread)
        )
        checks["naive_did_not_notify"] = naive.roots_list_changed_sent == []
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        checks["live_starts_on_checkout"] = CHECKOUT_URI in extract_root_uris(live.roots)
        live.notify_roots_list_changed(WORKTREE_ROOTS)
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["notify_records_worktree"] = (
            WORKTREE_URI in extract_root_uris(live.roots)
            and live.roots_list_changed_sent == [(WORKTREE_URI,)]
        )
        checks["worktree_gated_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
        live.notify_roots_list_changed(DEFAULT_MCP_ROOTS)
        relocked = live.call_tool(GATED_TOOL_NAME, {"text": "after-checkout"})
        checks["checkout_re_locks_tool"] = (
            CHECKOUT_URI in extract_root_uris(live.roots)
            and relocked.get("isError") is True
            and MISSING_ERROR in _extract_text(relocked)
        )
    finally:
        live.kill()

    empty = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        empty.start()
        empty.notify_roots_list_changed(())
        missing = empty.call_tool(GATED_TOOL_NAME, {"text": "empty-roots"})
        checks["empty_roots_fail_closed"] = (
            missing.get("isError") is True and MISSING_ERROR in _extract_text(missing)
        )
    finally:
        empty.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        mixed.notify_roots_list_changed("gated", WORKTREE_ROOTS)
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
        skipped.replace_roots("gated", WORKTREE_ROOTS)
        unread = skipped.call_tool("gated", GATED_TOOL_NAME, {"text": "nope"})
        sibling = _echo_text(skipped, "live", "still-here")
        checks["skip_notify_stays_on_plane"] = (
            unread.get("isError") is True
            and MISSING_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-roots-changed-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_ROOTS_CHANGED_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_roots_changed"] = (
        live_goal == MCP_ROOTS_CHANGED_GOAL
        and MCP_ROOTS_CHANGED_ID in live_done
        and live_source == "genesis_bind_roots_list_changed"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_roots_list_changed_capability()
    return {
        "ok": ok,
        "action": "mcp_roots_list_changed",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_ROOTS_CHANGED_GOAL,
        "done_when": MCP_ROOTS_CHANGED_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def run_stub_server() -> int:
    """Plugin whose echo tool stays locked until a roots listChanged retargets it."""

    dirty = False
    saw_change = False
    current_uris: list[str] = []
    pending_call: dict[str, Any] | None = None
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
        if method == "notifications/roots/list_changed":
            dirty = True
            saw_change = True
            continue
        if method == "notifications/initialized" or (
            "id" not in message and method is not None
        ):
            continue
        request_id = message.get("id")
        if pending_call is not None and request_id == ROOTS_REQUERY_ID and method is None:
            if "error" in message:
                current_uris = []
            else:
                result = message.get("result") if isinstance(message.get("result"), dict) else {}
                roots = result.get("roots") if isinstance(result.get("roots"), list) else []
                current_uris = [
                    str(item.get("uri") or "")
                    for item in roots
                    if isinstance(item, dict)
                ]
            dirty = False
            _finish_gated_call(pending_call, current_uris, saw_change)
            pending_call = None
            continue
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "blackhole-roots-list-changed-gated",
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
        if method == "tools/call":
            if dirty:
                pending_call = message
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": ROOTS_REQUERY_ID,
                        "method": "roots/list",
                        "params": {},
                    }
                )
                continue
            _finish_gated_call(message, current_uris, saw_change)
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
        raise SystemExit(f"unknown MCP roots-list-changed stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
