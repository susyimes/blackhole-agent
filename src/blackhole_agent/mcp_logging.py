"""Speak MCP logging/setLevel so log-gated plugins stay live.

Completion/complete, prompts, and resources are first-class. A plugin that
emits ``notifications/message`` and requires ``logging/setLevel`` is still
treated as catalog-only: Unbound never applies a severity floor, inbound log
notifications are dropped, a log-gated tool stays silent, and the call
returns an error instead of a sealed payload.

This module closes that hole:

- advertise and answer ``logging/setLevel`` on the live stdio (and HTTP)
  session
- capture inbound ``notifications/message`` instead of dropping them
- keep a skip-setLevel path so the unset hole stays falsifiable
- let a log-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after completions
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
    LOG_LEVEL_SET,
    McpProtocolError,
    McpStdioSession,
    _extract_text,
    echo_server_command,
    extract_log_messages,
)
from blackhole_agent.mcp_completions import MCP_COMPLETIONS_GOAL, MCP_COMPLETIONS_ID
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)

SCHEMA_VERSION = 1
MCP_LOGGING_ID = "capability.mcp-logging"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
UNLOCK_LEVEL = "info"
UNLOCK_TOKEN = "BH-LOG-OK"
UNSET_ERROR = "severity floor unset"
UNKNOWN_LEVEL_ERROR = "unknown log level"

MCP_LOGGING_DONE_WHEN = (
    f"capability_exists:{MCP_LOGGING_ID};"
    f"capability_proved:{MCP_LOGGING_ID};"
    "no_skill_route"
)
MCP_LOGGING_GOAL = (
    "Repair MCP log stream consumption: a hosted plugin that emits "
    "notifications/message and requires logging/setLevel never has its "
    "severity floor applied, so a log-gated tool stays silent and returns "
    "an error instead of the sealed payload. Fail-closed sessions that skip "
    "setLevel stay forbidden."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after the log floor is set.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays forbidden until logging/setLevel unlocks it."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_logging", "gated"]


def mcp_logging_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_logging import "
        "builtin_mcp_logging_proof; r=builtin_mcp_logging_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_logging' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_logging_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_LOGGING_ID,
        name="MCP log stream consumption",
        description=(
            "An MCP session applies logging/setLevel and consumes "
            "notifications/message so a log-gated plugin unlocks and returns "
            "its tool result instead of a silent error. Skip-setLevel sessions "
            "stay fail-closed."
        ),
        kind="python",
        entry="blackhole_agent.mcp_logging:builtin_mcp_logging_proof",
        proof_command=mcp_logging_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-completions",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_logging.py",
            "src/blackhole_agent/mcp_echo_server.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that emits notifications/message is first-class: "
            "Unbound applies logging/setLevel, captures the inbound log stream, "
            "and a log-gated tool returns the sealed payload instead of a silent "
            "error, while skip-setLevel sessions stay fail-closed and siblings "
            "keep serving."
        ),
        tags=("mcp", "logging", "notifications", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T065530Z-a1e43902",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def _log_data(session: Any) -> tuple[Any, ...]:
    notifications = getattr(session, "server_notifications", ())
    return tuple(item.get("data") for item in extract_log_messages(notifications))


def builtin_mcp_logging_proof() -> dict[str, Any]:
    """Hermetic proof: logging/setLevel unlocks a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_LOGGING_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_LOGGING_GOAL) == (MCP_LOGGING_ID,)
    checks["completions_goal_is_not_logging"] = leftover_marker_ids(MCP_COMPLETIONS_GOAL) == (
        MCP_COMPLETIONS_ID,
    )
    checks["completions_marker_stays_completions"] = MCP_LOGGING_ID not in leftover_marker_ids(
        MCP_COMPLETIONS_GOAL
    )
    checks["call_goal_is_not_logging"] = leftover_marker_ids(MCP_CALL_GOAL) != (MCP_LOGGING_ID,)
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_logging"] = (
        len(catalog) > 18
        and catalog[18]["id"] == MCP_LOGGING_ID
        and catalog[17]["id"] == MCP_COMPLETIONS_ID
    )

    with McpStdioSession(echo_server_command()) as echo:
        advertised = echo.server_capabilities.get("logging")
        echo.set_log_level(UNLOCK_LEVEL)
        logs = extract_log_messages(echo.server_notifications)
        missing = False
        try:
            echo.set_log_level("not-a-level")
        except McpProtocolError as exc:
            missing = "unknown log level" in str(exc).lower()
        checks["echo_advertises_logging"] = isinstance(advertised, Mapping)
        checks["echo_emits_log_after_set_level"] = any(
            item.get("level") == UNLOCK_LEVEL and item.get("data") == f"level:{UNLOCK_LEVEL}"
            for item in logs
        )
        checks["echo_unknown_level_fail_closed"] = missing

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_skip_set_level_is_error"] = (
            unread.get("isError") is True and UNSET_ERROR in _extract_text(unread)
        )
        checks["naive_skip_set_level_has_no_logs"] = extract_log_messages(naive.server_notifications) == ()
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        live.set_log_level(UNLOCK_LEVEL)
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["gated_emits_unlock_log"] = UNLOCK_TOKEN in _log_data(live)
        checks["log_gated_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        mixed.set_log_level("gated", UNLOCK_LEVEL)
        gated_text = _echo_text(mixed, "gated", "from-gated")
        echoed = _echo_text(mixed, "live", "from-echo")
        mixed.set_log_level("live", UNLOCK_LEVEL)
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
        sibling = _echo_text(skipped, "live", "still-here")
        checks["skip_set_level_stays_on_plane"] = (
            unread.get("isError") is True
            and UNSET_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-logging-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_LOGGING_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_logging"] = (
        live_goal == MCP_LOGGING_GOAL
        and MCP_LOGGING_ID in live_done
        and live_source == "genesis_bind_logging"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_logging_capability()
    return {
        "ok": ok,
        "action": "mcp_logging",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_LOGGING_GOAL,
        "done_when": MCP_LOGGING_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def run_stub_server() -> int:
    """Plugin whose echo tool stays forbidden until logging/setLevel unlocks it."""

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
                        "capabilities": {"tools": {}, "logging": {}},
                        "serverInfo": {"name": "blackhole-log-gated", "version": "0"},
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
        if method == "logging/setLevel":
            level = str(params.get("level") or "")
            if level not in LOG_LEVEL_SET:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": f"{UNKNOWN_LEVEL_ERROR}: {level}",
                        },
                    }
                )
                continue
            unlocked = True
            _write(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {
                        "level": level,
                        "logger": "blackhole-log-gated",
                        "data": UNLOCK_TOKEN,
                    },
                }
            )
            _write({"jsonrpc": "2.0", "id": request_id, "result": {}})
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
                            "content": [{"type": "text", "text": UNSET_ERROR}],
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
        raise SystemExit(f"unknown MCP logging stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
