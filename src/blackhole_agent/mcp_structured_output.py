"""Consume MCP structuredContent so a schema-typed tool result can seal.

Handshake snapshots ``tools/list`` and ``tools/call`` extract
``content[].text``. A plugin that advertises ``outputSchema`` and returns
the sealed payload only in ``structuredContent`` is still treated as
text-only: Unbound never validates the typed object, placeholder text is
all that remains, and the schema-typed result is dropped.

This module closes that hole:

- index ``outputSchema`` from ``tools/list``
- validate and keep ``structuredContent`` on ``tools/call``
- keep a skip-structured path so the untyped hole stays falsifiable
- reject a result whose structured payload misses required schema fields
- let a schema-typed plugin and a text-only sibling serve together
- bind this family as the next diversity-catalog successor after cursor
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
    extract_output_schema,
    extract_structured_content,
    sealed_structured_text,
)
from blackhole_agent.mcp_cursor_pagination import MCP_CURSOR_GOAL, MCP_CURSOR_ID
from blackhole_agent.mcp_handshake_isolation import (
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    McpPluginSpec,
    connect_mcp_plane,
)

SCHEMA_VERSION = 1
MCP_STRUCTURED_ID = "capability.mcp-structured-output"
REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_TOOL_NAME = "echo"
UNLOCK_TOKEN = "BH-STRUCTURED-OK"
PLACEHOLDER_TEXT = "untyped placeholder"
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "token": {"type": "string"},
    },
    "required": ["text", "token"],
    "additionalProperties": False,
}

MCP_STRUCTURED_DONE_WHEN = (
    f"capability_exists:{MCP_STRUCTURED_ID};"
    f"capability_proved:{MCP_STRUCTURED_ID};"
    "no_skill_route"
)
MCP_STRUCTURED_GOAL = (
    "Repair MCP structured tool output: a hosted plugin that advertises "
    "outputSchema and returns structuredContent never has that typed payload "
    "validated or consumed, so the sealed schema-typed result is dropped and "
    "only placeholder text remains. Sessions that skip structured validation "
    "stay fail-closed on the untyped result."
)

_ECHO_TOOL = {
    "name": GATED_TOOL_NAME,
    "description": "Return a schema-typed payload after structuredContent is consumed.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "outputSchema": OUTPUT_SCHEMA,
    "annotations": {"readOnlyHint": True},
}


def gated_command() -> list[str]:
    """Plugin whose echo tool seals the token only in structuredContent."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_structured_output", "gated"]


def invalid_command() -> list[str]:
    """Plugin whose structuredContent misses a required outputSchema field."""

    return [sys.executable, "-u", "-m", "blackhole_agent.mcp_structured_output", "invalid"]


def mcp_structured_output_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_structured_output import "
        "builtin_mcp_structured_output_proof; r=builtin_mcp_structured_output_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_structured_output' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_structured_output_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_STRUCTURED_ID,
        name="MCP structured tool output",
        description=(
            "An MCP session indexes outputSchema from tools/list and validates "
            "structuredContent on tools/call so a schema-typed payload can seal. "
            "Sessions that skip structured validation stay fail-closed on "
            "placeholder text; invalid structuredContent is rejected."
        ),
        kind="python",
        entry="blackhole_agent.mcp_structured_output:builtin_mcp_structured_output_proof",
        proof_command=mcp_structured_output_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.mcp-cursor-pagination",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_client.py",
            "src/blackhole_agent/mcp_structured_output.py",
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_http_transport.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin that advertises outputSchema and returns "
            "structuredContent is first-class: Unbound indexes the schema, "
            "validates the typed payload, and the sealed schema-typed result "
            "is consumed, while skip-structured sessions stay fail-closed on "
            "placeholder text, invalid structuredContent is rejected, and "
            "siblings keep serving."
        ),
        tags=("mcp", "tools", "structuredContent", "outputSchema", "diversity"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260901T131105Z-f2563cc8",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _tool_names(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(item.get("name") or "")
        for item in (payload.get("tools") or [])
        if isinstance(item, Mapping)
    )


def _first_schema(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    for item in payload.get("tools") or []:
        if isinstance(item, Mapping) and str(item.get("name") or "") == GATED_TOOL_NAME:
            return extract_output_schema(item)
    return None


def builtin_mcp_structured_output_proof() -> dict[str, Any]:
    """Hermetic proof: validating structuredContent seals a schema-typed plugin."""

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
    checks["denylists_self"] = MCP_STRUCTURED_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_STRUCTURED_GOAL) == (
        MCP_STRUCTURED_ID,
    )
    checks["cursor_goal_is_not_structured"] = leftover_marker_ids(MCP_CURSOR_GOAL) == (
        MCP_CURSOR_ID,
    )
    checks["structured_goal_is_not_cursor"] = MCP_CURSOR_ID not in leftover_marker_ids(
        MCP_STRUCTURED_GOAL
    )
    checks["cursor_marker_stays_cursor"] = MCP_STRUCTURED_ID not in leftover_marker_ids(
        MCP_CURSOR_GOAL
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_structured"] = (
        len(catalog) > 40
        and catalog[40]["id"] == MCP_STRUCTURED_ID
        and catalog[39]["id"] == MCP_CURSOR_ID
    )
    family = capability_family(MCP_STRUCTURED_GOAL)
    checks["family_is_structured"] = "structured" in family
    checks["family_is_output"] = "output" in family
    checks["family_is_hosted"] = "hosted" in family
    checks["family_is_not_cursor"] = "cursor" not in family
    checks["family_is_not_paginated"] = "paginated" not in family
    checks["family_is_not_catalog"] = "catalog" not in family
    checks["family_is_not_watch"] = "watch" not in family
    checks["family_is_not_object"] = "object" not in family
    checks["family_is_not_postgresql"] = "postgresql" not in family
    checks["family_is_not_ldap"] = "ldap" not in family
    checks["family_is_not_nameserver"] = "nameserver" not in family
    checks["not_a_cursor_duplicate"] = (
        semantic_similarity(
            semantic_signature(MCP_STRUCTURED_GOAL),
            semantic_signature(MCP_CURSOR_GOAL),
        )
        < 0.82
    )

    with McpStdioSession(echo_server_command()) as echo:
        listed = echo.list_tools()
        names = _tool_names(listed)
        echoed = _extract_text(echo.call_tool(GATED_TOOL_NAME, {"text": "plain"}))
        checks["echo_lists_static_catalog"] = "echo" in names and "sha256" in names
        checks["echo_has_no_output_schema"] = GATED_TOOL_NAME not in echo.tool_output_schemas
        checks["echo_text_only_still_serves"] = (
            echoed == "plain" and sealed_structured_text(echo.call_tool(GATED_TOOL_NAME, {"text": "plain"})) == ""
        )

    naive = McpStdioSession(
        gated_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
        validate_structured=False,
    )
    try:
        naive.start()
        listed = naive.list_tools()
        unread = naive.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["naive_advertises_output_schema"] = _first_schema(listed) == OUTPUT_SCHEMA
        checks["naive_indexes_output_schema"] = (
            naive.tool_output_schemas.get(GATED_TOOL_NAME) == OUTPUT_SCHEMA
        )
        checks["naive_skip_structured_is_untyped"] = (
            unread.get("isError") is not True
            and _extract_text(unread) == PLACEHOLDER_TEXT
            and UNLOCK_TOKEN not in _extract_text(unread)
            and extract_structured_content(unread) is None
            and sealed_structured_text(unread) == ""
        )
    finally:
        naive.kill()

    live = McpStdioSession(gated_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)
    try:
        live.start()
        listed = live.list_tools()
        served = live.call_tool(GATED_TOOL_NAME, {"text": "gate-me"})
        checks["live_advertises_output_schema"] = _first_schema(listed) == OUTPUT_SCHEMA
        checks["live_indexes_output_schema"] = (
            live.tool_output_schemas.get(GATED_TOOL_NAME) == OUTPUT_SCHEMA
        )
        checks["live_keeps_structured_content"] = extract_structured_content(served) == {
            "text": "gate-me",
            "token": UNLOCK_TOKEN,
        }
        checks["published_structured_call_succeeds"] = (
            served.get("isError") is not True
            and sealed_structured_text(served) == f"gate-me|{UNLOCK_TOKEN}"
        )
        checks["live_placeholder_text_is_not_the_seal"] = (
            _extract_text(served) == PLACEHOLDER_TEXT
        )
    finally:
        live.kill()

    invalid = McpStdioSession(
        invalid_command(),
        timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    )
    try:
        invalid.start()
        invalid.list_tools()
        rejected = invalid.call_tool(GATED_TOOL_NAME, {"text": "nope"})
        checks["invalid_structured_is_rejected"] = (
            rejected.get("isError") is True
            and "missing token" in _extract_text(rejected)
            and sealed_structured_text(rejected) == ""
        )
    finally:
        invalid.kill()

    mixed = connect_mcp_plane(
        [McpPluginSpec("gated", gated_command()), McpPluginSpec("live", echo_server_command())],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        gated_session = mixed._live_session("gated")
        gated_result = mixed.call_tool("gated", GATED_TOOL_NAME, {"text": "from-gated"})
        echoed = _extract_text(mixed.call_tool("live", GATED_TOOL_NAME, {"text": "from-echo"}))
        checks["plane_indexes_output_schema"] = (
            gated_session.tool_output_schemas.get(GATED_TOOL_NAME) == OUTPUT_SCHEMA
        )
        checks["sibling_echo_still_serves"] = (
            mixed.plane_failed is False
            and mixed.live_names == ("gated", "live")
            and sealed_structured_text(gated_result) == f"from-gated|{UNLOCK_TOKEN}"
            and echoed == "from-echo"
        )
    finally:
        mixed.close()

    skipped = connect_mcp_plane(
        [
            McpPluginSpec("gated", gated_command(), validate_structured=False),
            McpPluginSpec("live", echo_server_command()),
        ],
        isolate_dead=True,
        isolate_hung_calls=True,
    )
    try:
        unread = skipped.call_tool("gated", GATED_TOOL_NAME, {"text": "nope"})
        sibling = _extract_text(
            skipped.call_tool("live", GATED_TOOL_NAME, {"text": "still-here"})
        )
        checks["skip_structured_stays_on_plane"] = (
            unread.get("isError") is not True
            and _extract_text(unread) == PLACEHOLDER_TEXT
            and extract_structured_content(unread) is None
            and skipped.plane_failed is False
            and skipped.live_names == ("gated", "live")
            and sibling == "still-here"
        )
    finally:
        skipped.close()

    with tempfile.TemporaryDirectory(prefix="mcp-structured-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_STRUCTURED_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_structured"] = (
        live_goal == MCP_STRUCTURED_GOAL
        and MCP_STRUCTURED_ID in live_done
        and live_source == "genesis_bind_structured_output"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_structured_output_capability()
    return {
        "ok": ok,
        "action": "mcp_structured_output",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_STRUCTURED_GOAL,
        "done_when": MCP_STRUCTURED_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
    }


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _structured_result(
    request_id: Any,
    text: str,
    *,
    valid: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text}
    if valid:
        payload["token"] = UNLOCK_TOKEN
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [{"type": "text", "text": PLACEHOLDER_TEXT}],
            "structuredContent": payload,
            "isError": False,
        },
    }


def run_stub_server(*, valid: bool) -> int:
    """Plugin whose echo tool seals the token only in structuredContent."""

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
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "blackhole-structured-output-gated",
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
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": [_ECHO_TOOL]},
                }
            )
            continue
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = (
                params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            )
            user_text = str(arguments.get("text") or "")
            if name == GATED_TOOL_NAME:
                _write(_structured_result(request_id, user_text, valid=valid))
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
    if not args or args[0] not in {"gated", "invalid"}:
        raise SystemExit(f"unknown MCP structured output stub mode: {args[:1]}")
    return run_stub_server(valid=args[0] == "gated")


if __name__ == "__main__":
    raise SystemExit(main())
