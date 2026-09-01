"""Attach MCP progressToken so a progress-gated plugin can stay live.

Cancellation already aborts a hung ``tools/call``. Logging already consumes
``notifications/message``. A plugin that unlocks only after reporting
monotonic ``notifications/progress`` still stalls: Unbound never puts a
``progressToken`` on the request ``_meta``, inbound progress events are
never associated with the call, and isolation treats a live long job as a
hung stdio session.

This module closes that hole:

- attach ``_meta.progressToken`` on ``tools/call``
- consume inbound ``notifications/progress`` bound to that token
- keep a skip-token path so the stall stays falsifiable
- let a progress-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after webhook
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
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_progress_notifications,
    progress_is_monotonic,
)
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_logging import MCP_LOGGING_GOAL, MCP_LOGGING_ID
from blackhole_agent.webhook_actuation import WEBHOOK_ACTUATION_GOAL, WEBHOOK_ACTUATION_ID

SCHEMA_VERSION = 1
MCP_PROGRESS_ID = "capability.mcp-progress"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
UNLOCK_TOKEN = "BH-PROGRESS-OK"
DEFAULT_TOKEN = "bh-progress-1"
MISSING_ERROR = "progress token missing"
PROGRESS_TOTAL = 2

MCP_PROGRESS_DONE_WHEN = (
    f"capability_exists:{MCP_PROGRESS_ID};"
    f"capability_proved:{MCP_PROGRESS_ID};"
    "no_skill_route"
)
MCP_PROGRESS_GOAL = (
    "Repair MCP progress-token liveness: Unbound's tools/call never attaches a "
    "progressToken and never consumes notifications/progress, so a plugin that "
    "unlocks only after reporting monotonic completion is indistinguishable from "
    "a hung stdio session and isolation kills live work. Requests that omit the "
    "token keep the stall falsifiable."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after monotonic progress.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays locked until a progressToken is attached."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_progress", "gated"]


def mcp_progress_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_progress import "
        "builtin_mcp_progress_proof; r=builtin_mcp_progress_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_progress' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_progress_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_PROGRESS_ID,
        name="MCP progress-token liveness",
        description=(
            "An MCP session attaches _meta.progressToken on tools/call and "
            "consumes notifications/progress so a progress-gated plugin can "
            "report monotonic completion and return its tool result. Requests "
            "that omit the token stay fail-closed."
        ),
        kind="python",
        entry="blackhole_agent.mcp_progress:builtin_mcp_progress_proof",
        proof_command=mcp_progress_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-cancellation",
            "capability.webhook-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_progress.py",
            "src/blackhole_agent/mcp_echo_server.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that unlocks only after monotonic "
            "notifications/progress is first-class: Unbound attaches a "
            "progressToken, consumes the inbound progress stream, and the "
            "progress-gated tool returns the sealed payload, while skip-token "
            "sessions stay fail-closed and siblings keep serving."
        ),
        tags=("mcp", "progress", "progressToken", "jsonrpc", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T045301Z-b674e00c",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _gated_text(plane: Any, server: str, text: str, token: str = DEFAULT_TOKEN) -> str:
    return _extract_text(
        plane.call_tool(
            server,
            GATED_TOOL_NAME,
            {"text": text},
            progress_token=token,
        )
    )


def builtin_mcp_progress_proof() -> dict[str, Any]:
    """Hermetic proof: a progressToken unlocks a gated plugin."""

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
    checks["denylists_self"] = MCP_PROGRESS_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_PROGRESS_GOAL) == (
        MCP_PROGRESS_ID,
    )
    checks["webhook_goal_is_not_progress"] = leftover_marker_ids(
        WEBHOOK_ACTUATION_GOAL
    ) == (WEBHOOK_ACTUATION_ID,)
    checks["cancellation_goal_is_not_progress"] = leftover_marker_ids(
        MCP_CANCELLATION_GOAL
    ) == (MCP_CANCELLATION_ID,)
    checks["logging_goal_is_not_progress"] = leftover_marker_ids(MCP_LOGGING_GOAL) == (
        MCP_LOGGING_ID,
    )
    checks["progress_goal_is_not_webhook"] = WEBHOOK_ACTUATION_ID not in leftover_marker_ids(
        MCP_PROGRESS_GOAL
    )
    checks["progress_goal_is_not_cancellation"] = (
        MCP_CANCELLATION_ID not in leftover_marker_ids(MCP_PROGRESS_GOAL)
    )
    checks["progress_goal_is_not_logging"] = MCP_LOGGING_ID not in leftover_marker_ids(
        MCP_PROGRESS_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_progress"] = (
        len(catalog) > 27
        and catalog[27]["id"] == MCP_PROGRESS_ID
        and catalog[26]["id"] == WEBHOOK_ACTUATION_ID
    )
    family = capability_family(MCP_PROGRESS_GOAL)
    checks["family_is_progress"] = "progress" in family
    checks["family_is_not_webhook"] = "webhook" not in family
    checks["family_is_not_timeout"] = "timeout" not in family
    checks["family_is_not_browser"] = "browser" not in family
    checks["family_is_not_worktree"] = "worktree" not in family
    checks["not_a_webhook_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_PROGRESS_GOAL),
            semantic_signature(WEBHOOK_ACTUATION_GOAL),
        )
        < 0.82
    )
    checks["not_a_cancellation_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_PROGRESS_GOAL),
            semantic_signature(MCP_CANCELLATION_GOAL),
        )
        < 0.82
    )

    with McpStdioSession(echo_server_command()) as echo:
        plain = echo.call_tool(GATED_TOOL_NAME, {"text": "plain"})
        plain_progress = extract_progress_notifications(echo.server_notifications)
        tokened = echo.call_tool(
            GATED_TOOL_NAME, {"text": "tokened"}, progress_token=DEFAULT_TOKEN
        )
        echo_progress = extract_progress_notifications(
            echo.server_notifications, token=DEFAULT_TOKEN
        )
        checks["echo_without_token_still_serves"] = (
            plain.get("isError") is not True and _extract_text(plain) == "plain"
        )
        checks["echo_without_token_has_no_progress"] = plain_progress == ()
        checks["echo_with_token_still_serves"] = (
            tokened.get("isError") is not True and _extract_text(tokened) == "tokened"
        )
        checks["echo_with_token_emits_monotonic_progress"] = (
            progress_is_monotonic(echo_progress)
            and echo_progress[0]["progressToken"] == DEFAULT_TOKEN
            and echo_progress[-1]["progress"] == echo_progress[-1]["total"]
        )

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_skip_token_is_error"] = (
            unread.get("isError") is True and MISSING_ERROR in _extract_text(unread)
        )
        checks["naive_skip_token_has_no_progress"] = (
            extract_progress_notifications(naive.server_notifications) == ()
        )
    finally:
        naive.kill()

    empty = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        empty.start()
        blank = empty.call_tool(GATED_TOOL_NAME, {"text": "blank"}, progress_token="")
        checks["empty_token_is_forbidden"] = (
            blank.get("isError") is True and MISSING_ERROR in _extract_text(blank)
        )
    finally:
        empty.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        served = _extract_text(
            live.call_tool(
                GATED_TOOL_NAME,
                {"text": "gate-me"},
                progress_token=DEFAULT_TOKEN,
            )
        )
        events = extract_progress_notifications(
            live.server_notifications, token=DEFAULT_TOKEN
        )
        checks["progress_gated_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
        checks["live_progress_is_monotonic"] = (
            progress_is_monotonic(events)
            and len(events) >= PROGRESS_TOTAL
            and events[0]["progressToken"] == DEFAULT_TOKEN
            and events[-1]["progress"] == events[-1]["total"]
        )
        checks["live_recorded_progress_token"] = DEFAULT_TOKEN in live.progress_tokens
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        gated_text = _gated_text(mixed, "gated", "from-gated")
        echoed = _extract_text(mixed.call_tool("live", GATED_TOOL_NAME, {"text": "from-echo"}))
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
        checks["skip_token_stays_on_plane"] = (
            unread.get("isError") is True
            and MISSING_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-progress-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_PROGRESS_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_progress"] = (
        live_goal == MCP_PROGRESS_GOAL
        and MCP_PROGRESS_ID in live_done
        and live_source == "genesis_bind_progress"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_progress_capability()
    return {
        "ok": ok,
        "action": "mcp_progress",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_PROGRESS_GOAL,
        "done_when": MCP_PROGRESS_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _progress_token(params: Mapping[str, Any]) -> str:
    meta = params.get("_meta") if isinstance(params.get("_meta"), Mapping) else {}
    token = meta.get("progressToken")
    if token is None:
        return ""
    return str(token)


def _emit_progress(token: str) -> None:
    for step in range(1, PROGRESS_TOTAL + 1):
        _write(
            {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": token,
                    "progress": step,
                    "total": PROGRESS_TOTAL,
                    "message": "working" if step < PROGRESS_TOTAL else "done",
                },
            }
        )


def run_stub_server() -> int:
    """Plugin whose echo tool stays forbidden until a progressToken is attached."""

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
                        "serverInfo": {"name": "blackhole-progress-gated", "version": "0"},
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
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            user_text = str(arguments.get("text") or "")
            token = _progress_token(params)
            if not token:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [{"type": "text", "text": MISSING_ERROR}],
                            "isError": True,
                        },
                    }
                )
                continue
            _emit_progress(token)
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
        raise SystemExit(f"unknown MCP progress stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
