"""Speak MCP prompts/list and prompts/get so prompt-gated plugins stay live.

Tools/list, tools/call, resources/list, and resources/read are first-class.
A plugin that exposes a prompt catalog is still treated as tools-only:
Unbound never calls ``prompts/list`` or ``prompts/get``, a prompt-gated
tool sees its unlock template unread, and the call returns an error
instead of a sealed payload.

This module closes that hole:

- advertise and answer ``prompts/list`` and ``prompts/get`` on the live
  stdio (and HTTP) session
- keep a skip-get path so the unread hole stays falsifiable
- let a prompt-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after resources
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
    extract_prompt_text,
)
from blackhole_agent.mcp_echo_server import ABOUT_PROMPT, NOTE_PROMPT
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_resources import MCP_RESOURCES_GOAL, MCP_RESOURCES_ID

SCHEMA_VERSION = 1
MCP_PROMPTS_ID = "capability.mcp-prompts"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
UNLOCK_PROMPT = "unlock"
UNLOCK_TOKEN = "BH-PROMPT-OK"
UNGET_ERROR = "unlock prompt unread"

MCP_PROMPTS_DONE_WHEN = (
    f"capability_exists:{MCP_PROMPTS_ID};"
    f"capability_proved:{MCP_PROMPTS_ID};"
    "no_skill_route"
)
MCP_PROMPTS_GOAL = (
    "Repair MCP prompt catalog: a hosted plugin that exposes prompts/list "
    "and prompts/get is never queried, so a prompt-gated tool cannot fetch "
    "its unlock template and returns an error instead of the sealed payload. "
    "Fail-closed sessions that skip the prompt get stay forbidden."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after the prompt is fetched.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}

_UNLOCK_PROMPT = {
    "name": UNLOCK_PROMPT,
    "description": "Session unlock template for the prompt-gated echo tool.",
    "arguments": [],
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays forbidden until prompts/get unlocks it."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_prompts", "gated"]


def mcp_prompts_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_prompts import "
        "builtin_mcp_prompts_proof; r=builtin_mcp_prompts_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_prompts' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_prompts_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_PROMPTS_ID,
        name="MCP prompt catalog",
        description=(
            "An MCP session lists and fetches prompts so a prompt-gated "
            "plugin unlocks and returns its tool result instead of an unread "
            "error. Skip-get sessions stay fail-closed."
        ),
        kind="python",
        entry="blackhole_agent.mcp_prompts:builtin_mcp_prompts_proof",
        proof_command=mcp_prompts_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-resources",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_prompts.py",
            "src/blackhole_agent/mcp_echo_server.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that exposes prompts/list and prompts/get is "
            "first-class: Unbound lists and fetches the unlock template so a "
            "prompt-gated tool returns the sealed payload instead of an "
            "unread error, while skip-get sessions stay fail-closed and "
            "siblings keep serving."
        ),
        tags=("mcp", "prompts", "catalog", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T054909Z-730884f1",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def builtin_mcp_prompts_proof() -> dict[str, Any]:
    """Hermetic proof: prompts/list and prompts/get unlock a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_PROMPTS_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_PROMPTS_GOAL) == (MCP_PROMPTS_ID,)
    checks["resources_goal_is_not_prompts"] = leftover_marker_ids(MCP_RESOURCES_GOAL) == (
        MCP_RESOURCES_ID,
    )
    checks["resources_marker_stays_resources"] = MCP_PROMPTS_ID not in leftover_marker_ids(
        MCP_RESOURCES_GOAL
    )
    checks["call_goal_is_not_prompts"] = leftover_marker_ids(MCP_CALL_GOAL) != (
        MCP_PROMPTS_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_prompts"] = (
        len(catalog) > 16
        and catalog[16]["id"] == MCP_PROMPTS_ID
        and catalog[15]["id"] == MCP_RESOURCES_ID
    )

    with McpStdioSession(echo_server_command()) as echo:
        advertised = echo.server_capabilities.get("prompts")
        listed = echo.list_prompts()
        names = {
            str(item.get("name") or "")
            for item in listed.get("prompts") or []
            if isinstance(item, Mapping)
        }
        about = extract_prompt_text(echo.get_prompt(ABOUT_PROMPT))
        note = extract_prompt_text(echo.get_prompt(NOTE_PROMPT, {"id": "sentinel"}))
        missing = False
        try:
            echo.get_prompt("missing-prompt")
        except McpProtocolError as exc:
            missing = "unknown prompt" in str(exc).lower()
        missing_arg = False
        try:
            echo.get_prompt(NOTE_PROMPT, {})
        except McpProtocolError as exc:
            missing_arg = "unknown prompt" in str(exc).lower() or "missing prompt argument" in str(
                exc
            ).lower()
        checks["echo_advertises_prompts"] = isinstance(advertised, Mapping)
        checks["echo_lists_about_prompt"] = ABOUT_PROMPT in names
        checks["echo_gets_about_prompt"] = about == "blackhole-echo-mcp"
        checks["echo_lists_note_prompt"] = NOTE_PROMPT in names
        checks["echo_gets_templated_prompt"] = note == "note:sentinel"
        checks["echo_unknown_prompt_fail_closed"] = missing
        checks["echo_missing_prompt_argument_fail_closed"] = missing_arg

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_skip_get_is_error"] = (
            unread.get("isError") is True and UNGET_ERROR in _extract_text(unread)
        )
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        listed = live.list_prompts()
        names = {
            str(item.get("name") or "")
            for item in listed.get("prompts") or []
            if isinstance(item, Mapping)
        }
        token = extract_prompt_text(live.get_prompt(UNLOCK_PROMPT))
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["gated_lists_unlock_prompt"] = UNLOCK_PROMPT in names
        checks["gated_gets_unlock_token"] = token == UNLOCK_TOKEN
        checks["prompt_gated_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        mixed.get_prompt("gated", UNLOCK_PROMPT)
        gated_text = _echo_text(mixed, "gated", "from-gated")
        echoed = _echo_text(mixed, "live", "from-echo")
        about = extract_prompt_text(mixed.get_prompt("live", ABOUT_PROMPT))
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
        checks["skip_get_stays_on_plane"] = (
            unread.get("isError") is True
            and UNGET_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-prompts-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_PROMPTS_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_prompts"] = (
        live_goal == MCP_PROMPTS_GOAL
        and MCP_PROMPTS_ID in live_done
        and live_source == "genesis_bind_prompts"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_prompts_capability()
    return {
        "ok": ok,
        "action": "mcp_prompts",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_PROMPTS_GOAL,
        "done_when": MCP_PROMPTS_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _prompt_contents() -> dict[str, Any]:
    return {
        "description": "Session unlock template.",
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": UNLOCK_TOKEN},
            }
        ],
    }


def run_stub_server() -> int:
    """Plugin whose echo tool stays forbidden until prompts/get unlocks it."""

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
                        "capabilities": {"tools": {}, "prompts": {}},
                        "serverInfo": {"name": "blackhole-prompt-gated", "version": "0"},
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
        if method == "prompts/list":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"prompts": [_UNLOCK_PROMPT]},
                }
            )
            continue
        if method == "prompts/get":
            name = str(params.get("name") or "")
            if name != UNLOCK_PROMPT:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": f"unknown prompt: {name}",
                        },
                    }
                )
                continue
            unlocked = True
            _write({"jsonrpc": "2.0", "id": request_id, "result": _prompt_contents()})
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
                            "content": [{"type": "text", "text": UNGET_ERROR}],
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
        raise SystemExit(f"unknown MCP prompt stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
