"""Reconnect an MCP plugin whose initialize connection closed.

Handshake isolation keeps sibling servers serving when a plugin's process
exits before initialize completes. The crashed plugin itself stays absent
for the rest of the session: a required tool never returns, and the only
recovery is restarting the whole plane.

This module closes that hole:

- reconnect an isolated plugin on a bounded backoff
- restore it to the live plane when a later handshake succeeds
- leave a permanently dead plugin isolated after the attempt budget
- never restart sibling sessions
- leave the no-reconnect path so the hole stays falsifiable
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

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
    _extract_text,
    echo_server_command,
)
from blackhole_agent.godot_actuation import GODOT_ACTUATION_GOAL, GODOT_ACTUATION_ID
from blackhole_agent.mcp_handshake_isolation import (
    DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    LIVE_HANDSHAKE_TIMEOUT_SECONDS,
    MCP_HANDSHAKE_GOAL,
    MCP_HANDSHAKE_ID,
    McpPluginPlane,
    McpPluginSpec,
    closed_initialize_command,
    connect_mcp_plane,
)

SCHEMA_VERSION = 1
MCP_RECONNECT_ID = "capability.mcp-plugin-reconnect"
REPO_ROOT = Path(__file__).resolve().parents[2]

MCP_RECONNECT_DONE_WHEN = (
    f"capability_exists:{MCP_RECONNECT_ID};"
    f"capability_proved:{MCP_RECONNECT_ID};"
    "no_skill_route"
)
MCP_RECONNECT_GOAL = (
    "Repair MCP plugin reconnect recovery after a closed initialize: a hosted "
    "plugin whose process exits before initialize completes stays absent for "
    "the rest of the session, so a required tool never returns even while "
    "sibling plugins keep serving. Reconnect the crashed plugin on a bounded "
    "backoff without restarting the live plane."
)


def flaky_initialize_command(state_path: Path, *, fail_count: int = 1) -> list[str]:
    """Plugin that exits on the first ``fail_count`` starts, then speaks echo MCP."""

    return [
        sys.executable,
        "-u",
        "-m",
        "blackhole_agent.mcp_plugin_reconnect",
        "flaky",
        str(state_path),
        str(int(fail_count)),
    ]


def mcp_plugin_reconnect_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.mcp_plugin_reconnect import "
        "builtin_mcp_plugin_reconnect_proof; r=builtin_mcp_plugin_reconnect_proof(); "
        "assert r['ok'] and r.get('action')=='mcp_plugin_reconnect' "
        "and r.get('passed_count',0) >= 12 "
        "and not r.get('used_skill_route_discovery')\""
    )


def ensure_mcp_plugin_reconnect_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=MCP_RECONNECT_ID,
        name="MCP plugin reconnect after closed initialize",
        description=(
            "A multi-plugin MCP plane reconnects a plugin whose process exited "
            "before initialize completed, restoring the crashed tool on a "
            "bounded backoff without restarting sibling servers."
        ),
        kind="python",
        entry="blackhole_agent.mcp_plugin_reconnect:builtin_mcp_plugin_reconnect_proof",
        proof_command=mcp_plugin_reconnect_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
            "capability.mcp-handshake-isolation",
            "capability.godot-actuation",
        ),
        behavior_paths=(
            "src/blackhole_agent/mcp_handshake_isolation.py",
            "src/blackhole_agent/mcp_plugin_reconnect.py",
            "src/blackhole_agent/local_capability_kernel.py",
            "src/blackhole_agent/kernel_leftover.py",
            "src/blackhole_agent/kernel_genesis_diversify.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "A hosted plugin whose initialize connection closed is no longer "
            "absent for the rest of the session: Unbound reconnects it on a "
            "bounded backoff, restores the crashed tool beside live siblings, "
            "and leaves a permanently dead plugin isolated after the attempt "
            "budget without restarting the plane."
        ),
        tags=("mcp", "reconnect", "recovery", "handshake", "resilience"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
        source_mission_id="20260831T034021Z-9b8e8015",
        source_milestone=1,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _echo_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(name, echo_server_command(), timeout_seconds=LIVE_HANDSHAKE_TIMEOUT_SECONDS)


def _closed_spec(name: str) -> McpPluginSpec:
    return McpPluginSpec(
        name,
        closed_initialize_command(),
        timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    )


def _flaky_spec(name: str, state_path: Path, *, fail_count: int = 1) -> McpPluginSpec:
    return McpPluginSpec(
        name,
        flaky_initialize_command(state_path, fail_count=fail_count),
        timeout_seconds=DEAD_HANDSHAKE_TIMEOUT_SECONDS,
    )


def _echo_text(plane: McpPluginPlane, server: str, text: str) -> str:
    return _extract_text(plane.call_tool(server, "echo", {"text": text}))


def builtin_mcp_plugin_reconnect_proof() -> dict[str, Any]:
    """Hermetic proof: a closed initialize reconnects without restarting siblings."""

    from blackhole_agent.kernel_genesis_bind import _register_proved as register_catalog_proved
    from blackhole_agent.kernel_genesis_diversify import (
        DIVERSITY_CATALOG,
        _prepare_exhausted_catalog,
        bind_gate_passing_successor,
    )

    catalog = DIVERSITY_CATALOG
    checks: dict[str, bool] = {}
    checks["denylists_self"] = MCP_RECONNECT_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(MCP_RECONNECT_GOAL) == (
        MCP_RECONNECT_ID,
    )
    checks["handshake_goal_is_not_reconnect"] = leftover_marker_ids(MCP_HANDSHAKE_GOAL) == (
        MCP_HANDSHAKE_ID,
    )
    checks["godot_goal_is_not_reconnect"] = leftover_marker_ids(GODOT_ACTUATION_GOAL) == (
        GODOT_ACTUATION_ID,
    )
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["catalog_names_reconnect"] = (
        len(catalog) > 12
        and catalog[12]["id"] == MCP_RECONNECT_ID
        and catalog[11]["id"] == GODOT_ACTUATION_ID
    )

    naive = connect_mcp_plane(
        [_closed_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
    )
    try:
        dead_raised = False
        try:
            naive.call_tool("dead", "echo", {"text": "nope"})
        except McpProtocolError:
            dead_raised = True
        sibling = _echo_text(naive, "live", "still-here")
        checks["isolated_closed_stays_dead_without_reconnect"] = (
            naive.plane_failed is False
            and naive.live_names == ("live",)
            and naive.isolated_names == ("dead",)
            and dead_raised
        )
        checks["sibling_serves_without_reconnect"] = sibling == "still-here"
    finally:
        naive.close()

    always_dead = connect_mcp_plane(
        [_closed_spec("dead"), _echo_spec("live")],
        isolate_dead=True,
    )
    try:
        token_before = always_dead.session_token("live")
        report = always_dead.reconnect_plugin("dead", max_attempts=2, backoff_seconds=0.0)
        sibling = _echo_text(always_dead, "live", "budget-ok")
        token_after = always_dead.session_token("live")
        still_dead = False
        try:
            always_dead.call_tool("dead", "echo", {"text": "nope"})
        except McpProtocolError:
            still_dead = True
        checks["always_dead_reconnect_stays_isolated"] = (
            report.get("ok") is False
            and still_dead
            and always_dead.isolated_names == ("dead",)
            and always_dead.live_names == ("live",)
        )
        checks["bounded_attempts"] = int(report.get("attempts") or 0) == 2
        checks["dead_reconnect_keeps_sibling_token"] = (
            token_before != 0 and token_before == token_after and sibling == "budget-ok"
        )
    finally:
        always_dead.close()

    with tempfile.TemporaryDirectory(prefix="mcp-reconnect-flaky-") as tmp:
        state = Path(tmp) / "starts"
        restored = connect_mcp_plane(
            [_flaky_spec("flaky", state, fail_count=1), _echo_spec("live")],
            isolate_dead=True,
        )
        try:
            token_before = restored.session_token("live")
            checks["flaky_starts_isolated"] = (
                restored.live_names == ("live",)
                and restored.isolated_names == ("flaky",)
            )
            report = restored.reconnect_plugin("flaky", max_attempts=3, backoff_seconds=0.0)
            sibling = _echo_text(restored, "live", "sibling")
            recovered = _echo_text(restored, "flaky", "restored")
            token_after = restored.session_token("live")
            live_noop = restored.reconnect_plugin("live")
            unknown = restored.reconnect_plugin("ghost")
            checks["flaky_reconnect_restores_plugin"] = (
                report.get("ok") is True
                and report.get("already_live") is False
                and int(report.get("attempts") or 0) >= 1
                and restored.live_names == ("flaky", "live")
                and restored.isolated_names == ()
            )
            checks["flaky_reconnect_serves_echo"] = recovered == "restored"
            checks["sibling_session_token_unchanged"] = (
                token_before != 0 and token_before == token_after and sibling == "sibling"
            )
            checks["already_live_reconnect_is_noop"] = (
                live_noop.get("ok") is True
                and live_noop.get("already_live") is True
                and int(live_noop.get("attempts") or 0) == 0
            )
            checks["unknown_plugin_reconnect_fails"] = (
                unknown.get("ok") is False and unknown.get("error") == "unknown plugin"
            )
        finally:
            restored.close()

    with tempfile.TemporaryDirectory(prefix="mcp-reconnect-bind-") as tmp:
        root = Path(tmp)
        _prepare_exhausted_catalog(root)
        for item in catalog:
            if item["id"] != MCP_RECONNECT_ID:
                register_catalog_proved(root, item["id"])
        live_goal, live_done, live_source = bind_gate_passing_successor(root)
    checks["exhausted_catalog_binds_reconnect"] = (
        live_goal == MCP_RECONNECT_GOAL
        and MCP_RECONNECT_ID in live_done
        and live_source == "genesis_bind_reconnect"
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_mcp_plugin_reconnect_capability()
    return {
        "ok": ok,
        "action": "mcp_plugin_reconnect",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MCP_RECONNECT_GOAL,
        "done_when": MCP_RECONNECT_DONE_WHEN,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "flaky":
        raise SystemExit(f"unknown MCP reconnect stub mode: {args[:1]}")
    if len(args) < 3:
        raise SystemExit("flaky mode requires a state path and fail count")
    state = Path(args[1])
    fail_count = int(args[2])
    n = int(state.read_text(encoding="utf-8")) if state.is_file() else 0
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(str(n + 1), encoding="utf-8")
    if n < fail_count:
        return 0
    from blackhole_agent.mcp_echo_server import main as echo_main

    return echo_main()


if __name__ == "__main__":
    raise SystemExit(main())
