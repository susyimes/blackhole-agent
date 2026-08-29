"""A healable red MCP hop must restore mixed stack health."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_mcp_application import MCP_APPLICATION_BRIDGE_ID, MCP_SHA256_ID
from blackhole_agent.capability_mcp_fragility import MCP_FRAGILITY_ID
from blackhole_agent.capability_mcp_recovery import MCP_RECOVERY_ID
from blackhole_agent.capability_mcp_reliability import MCP_RELIABILITY_ID
from blackhole_agent.capability_mcp_stack import MCP_STACK_ID
from blackhole_agent.capability_mcp_stack_repair import (
    MCP_STACK_REPAIR_ID,
    builtin_mcp_stack_repair_proof,
    compute_repair_verdicts,
    run_mcp_stack_repair_plane,
    verify_mcp_stack_repair_report,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_healable_hop_restores_mixed_stack_health() -> None:
    honesty = compute_repair_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_mcp_stack_healthy"]
    assert honesty["verdicts"]["red_hop_fails_stack"]
    assert honesty["verdicts"]["healable_hop_restores_stack"]
    assert honesty["verdicts"]["unrepairable_hop_leaves_stack_unhealthy"]
    assert honesty["mcp_id"] == MCP_SHA256_ID
    assert honesty["composition_id"] == "mcp-compose-text-reverser-echo-sha256"
    assert honesty["live"]["health"]["healthy"] is True
    assert honesty["red"]["health"]["healthy"] is False
    assert "mcp-compose-text-reverser-echo-sha256" in honesty["red"]["drifted_goals"]
    assert honesty["healed"]["repair"]["verdict"] == "repaired"
    assert honesty["healed"]["health"]["healthy"] is True
    assert honesty["healed"]["health"]["green_count"] == 4
    assert honesty["healed"]["drifted_goals"] == []
    assert honesty["unrepairable"]["repair"]["verdict"] == "unrepairable"
    assert honesty["unrepairable"]["health"]["healthy"] is False
    assert "mcp-compose-text-reverser-echo-sha256" in honesty["unrepairable"]["drifted_goals"]


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_mcp_stack_repair_plane(report_dir)
    assert result["ok"], result
    verification = verify_mcp_stack_repair_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["healable_hop_restores_stack"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_mcp_stack_repair_report(report_dir)["ok"] is False


def test_leftover_binds_mcp_stack_repair_plane() -> None:
    leftover = (
        "Optional later work is mixed stack repair so a healable hop "
        "restores mixed stack health."
    )
    assert leftover_marker_ids(leftover) == (MCP_STACK_REPAIR_ID,)
    assert MCP_STACK_ID not in leftover_marker_ids(leftover)
    assert MCP_RECOVERY_ID not in leftover_marker_ids(leftover)
    assert MCP_FRAGILITY_ID not in leftover_marker_ids(leftover)
    assert MCP_RELIABILITY_ID not in leftover_marker_ids(leftover)
    assert MCP_APPLICATION_BRIDGE_ID not in leftover_marker_ids(leftover)


def test_recovery_leftover_stays_on_the_heal_plane() -> None:
    leftover = (
        "Optional later work is watching mixed MCP+absorbed goals in the "
        "recovery plane so a red MCP hop is healed."
    )
    assert leftover_marker_ids(leftover) == (MCP_RECOVERY_ID,)
    assert MCP_STACK_REPAIR_ID not in leftover_marker_ids(leftover)


def test_stack_health_leftover_stays_on_the_grade_plane() -> None:
    leftover = (
        "Optional later work is folding mixed Python-to-MCP pipelines into "
        "goal-stack health so a red hop fails the stack grade."
    )
    assert leftover_marker_ids(leftover) == (MCP_STACK_ID,)
    assert MCP_STACK_REPAIR_ID not in leftover_marker_ids(leftover)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_mcp_stack_repair_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_STACK_REPAIR_ID]
    assert capability.last_proof_exit_code == 0
    assert "repair" in capability.tags
    assert "mcp" in capability.tags
