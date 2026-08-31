"""Speak MCP completion/complete so argument-gated plugins stay live.

Prompts/get and resources/read are first-class, but a plugin that exposes
argument autocompletion is still treated as catalog-only: Unbound never
calls ``completion/complete``, a completion-gated tool cannot resolve its
unlock argument, and the call returns an error instead of a sealed payload.

This module closes that hole:

- advertise and answer ``completion/complete`` on the live stdio (and HTTP)
  session for prompt arguments and resource templates
- keep a skip-complete path so the unresolved hole stays falsifiable
- let a completion-gated plugin and a tools-only sibling serve together
- bind this family as the next diversity-catalog successor after prompts
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
    extract_completion_values,
)
from blackhole_agent.mcp_echo_server import NOTE_COMPLETION_IDS, NOTE_PROMPT, NOTE_TEMPLATE
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)
from blackhole_agent.mcp_prompts import MCP_PROMPTS_GOAL, MCP_PROMPTS_ID

SCHEMA_VERSION = 1
MCP_COMPLETIONS_ID = "capability.mcp-completions"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
UNLOCK_PROMPT = "unlock"
UNLOCK_ARGUMENT = "token"
UNLOCK_TOKEN = "BH-COMPLETE-OK"
UNLOCK_ALT = "BH-COMPLETE-ALT"
UNCOMPLETE_ERROR = "unlock argument unresolved"
NOTE_PROMPT_REF = {"type": "ref/prompt", "name": NOTE_PROMPT}
NOTE_RESOURCE_REF = {"type": "ref/resource", "uri": NOTE_TEMPLATE}
UNLOCK_PROMPT_REF = {"type": "ref/prompt", "name": UNLOCK_PROMPT}

MCP_COMPLETIONS_DONE_WHEN = (
    f"capability_exists:{MCP_COMPLETIONS_ID};"
    f"capability_proved:{MCP_COMPLETIONS_ID};"
    "no_skill_route"
)
MCP_COMPLETIONS_GOAL = (
    "Repair MCP argument completion: a hosted plugin that exposes "
    "completion/complete is never queried, so a completion-gated tool cannot "
    "resolve its unlock argument and returns an error instead of the sealed "
    "payload. Fail-closed sessions that skip the completion stay forbidden."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return the supplied text plus the unlock token after the argument is completed.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "annotations": {"readOnlyHint": True},
}

_UNLOCK_PROMPT = {
    "name": UNLOCK_PROMPT,
    "description": "Session unlock argument for the completion-gated echo tool.",
    "arguments": [
        {
            "name": UNLOCK_ARGUMENT,
            "description": "Unlock token prefix",
            "required": True,
        }
    ],
}


def gated_command() -> list[str]:
    """Plugin whose echo tool stays forbidden until completion/complete resolves it."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_completions", "gated"]


def mcp_completions_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_completions import "
        "builtin_mcp_completions_proof; r=builtin_mcp_completions_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_completions' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_completions_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_COMPLETIONS_ID,
        name="MCP argument completion",
        description=(
            "An MCP session completes prompt and resource-template arguments "
            "so a completion-gated plugin unlocks and returns its tool result "
            "instead of an unresolved error. Skip-complete sessions stay "
            "fail-closed."
        ),
        kind="python",
        entry="blackhole_agent.mcp_completions:builtin_mcp_completions_proof",
        proof_command=mcp_completions_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-prompts",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_completions.py",
            "src/blackhole_agent/mcp_echo_server.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that exposes completion/complete is first-class: "
            "Unbound completes prompt and resource-template arguments so a "
            "completion-gated tool returns the sealed payload instead of an "
            "unresolved error, while skip-complete sessions stay fail-closed "
            "and siblings keep serving."
        ),
        tags=("mcp", "completions", "arguments", "jsonrpc"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T062036Z-1b36ac26",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_text(plane: Any, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, GATED_TOOL_NAME, {"text": text}))


def builtin_mcp_completions_proof() -> dict[str, Any]:
    """Hermetic proof: completion/complete unlocks a gated plugin."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )
    from blackhole_agent.mcp_call_isolation import MCP_CALL_GOAL

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_COMPLETIONS_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_COMPLETIONS_GOAL) == (
        MCP_COMPLETIONS_ID,
    )
    checks["prompts_goal_is_not_completions"] = leftover_marker_ids(MCP_PROMPTS_GOAL) == (
        MCP_PROMPTS_ID,
    )
    checks["prompts_marker_stays_prompts"] = MCP_COMPLETIONS_ID not in leftover_marker_ids(
        MCP_PROMPTS_GOAL
    )
    checks["call_goal_is_not_completions"] = leftover_marker_ids(MCP_CALL_GOAL) != (
        MCP_COMPLETIONS_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_completions"] = (
        len(catalog) > 17
        and catalog[17]["id"] == MCP_COMPLETIONS_ID
        and catalog[16]["id"] == MCP_PROMPTS_ID
    )

    with McpStdioSession(echo_server_command()) as echo:
        advertised = echo.server_capabilities.get("completions")
        prefix = echo.complete(NOTE_PROMPT_REF, "id", "sen")
        empty = echo.complete(NOTE_PROMPT_REF, "id", "")
        resource = echo.complete(NOTE_RESOURCE_REF, "id", "a")
        missing = False
        try:
            echo.complete({"type": "ref/prompt", "name": "missing-prompt"}, "id", "")
        except McpProtocolError as exc:
            missing = "unknown completion" in str(exc).lower()
        wrong_arg = False
        try:
            echo.complete(NOTE_PROMPT_REF, "title", "sen")
        except McpProtocolError as exc:
            wrong_arg = "unknown completion" in str(exc).lower()
        checks["echo_advertises_completions"] = isinstance(advertised, Mapping)
        checks["echo_completes_note_prompt_prefix"] = extract_completion_values(prefix) == (
            "sentinel",
            "sensor",
        )
        checks["echo_completes_note_prompt_all"] = (
            extract_completion_values(empty) == NOTE_COMPLETION_IDS
        )
        checks["echo_completes_resource_template"] = extract_completion_values(resource) == (
            "about",
        )
        checks["echo_unknown_completion_fail_closed"] = missing
        checks["echo_unknown_argument_fail_closed"] = wrong_arg

    naive = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        naive.start()
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_skip_complete_is_error"] = (
            unread.get("isError") is True and UNCOMPLETE_ERROR in _extract_text(unread)
        )
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        values = extract_completion_values(
            live.complete(UNLOCK_PROMPT_REF, UNLOCK_ARGUMENT, "BH-COMPLETE-O")
        )
        served = _extract_text(live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"}))
        checks["gated_completes_unlock_token"] = values == (UNLOCK_TOKEN,)
        checks["completion_gated_call_succeeds"] = served == f"gate-me|{UNLOCK_TOKEN}"
    finally:
        live.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        mixed.complete("gated", UNLOCK_PROMPT_REF, UNLOCK_ARGUMENT, "BH-COMPLETE-O")
        gated_text = _echo_text(mixed, "gated", "from-gated")
        echoed = _echo_text(mixed, "live", "from-echo")
        live_values = extract_completion_values(
            mixed.complete("live", NOTE_PROMPT_REF, "id", "sen")
        )
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("gated", "live")
            and gated_text == f"from-gated|{UNLOCK_TOKEN}"
            and echoed == "from-echo"
            and live_values == ("sentinel", "sensor")
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
        checks["skip_complete_stays_on_plane"] = (
            unread.get("isError") is True
            and UNCOMPLETE_ERROR in _extract_text(unread)
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-completions-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_COMPLETIONS_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_completions"] = (
        live_goal == MCP_COMPLETIONS_GOAL
        and MCP_COMPLETIONS_ID in live_done
        and live_source == "genesis_bind_completions"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_completions_capability()
    return {
        "ok": ok,
        "action": "mcp_completions",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_COMPLETIONS_GOAL,
        "done_when": MCP_COMPLETIONS_DONE_WHEN,
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _complete_unlock(prefix: str) -> list[str]:
    return [item for item in (UNLOCK_TOKEN, UNLOCK_ALT) if item.startswith(prefix)]


def run_stub_server() -> int:
    """Plugin whose echo tool stays forbidden until completion/complete unlocks it."""

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
                        "capabilities": {"tools": {}, "prompts": {}, "completions": {}},
                        "serverInfo": {"name": "blackhole-completion-gated", "version": "0"},
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
        if method == "completion/complete":
            ref = params.get("ref") if isinstance(params.get("ref"), dict) else {}
            argument = params.get("argument") if isinstance(params.get("argument"), dict) else {}
            name = str(ref.get("name") or "")
            arg_name = str(argument.get("name") or "")
            prefix = str(argument.get("value") or "")
            if str(ref.get("type") or "") != "ref/prompt" or name != UNLOCK_PROMPT or arg_name != UNLOCK_ARGUMENT:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": "unknown completion ref",
                        },
                    }
                )
                continue
            values = _complete_unlock(prefix)
            if UNLOCK_TOKEN in values:
                unlocked = True
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "completion": {
                            "values": values,
                            "total": len(values),
                            "hasMore": False,
                        }
                    },
                }
            )
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
                            "content": [{"type": "text", "text": UNCOMPLETE_ERROR}],
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
        raise SystemExit(f"unknown MCP completion stub mode: {args[:1]}")
    return run_stub_server()


if __name__ == "__main__":
    raise SystemExit(main())
