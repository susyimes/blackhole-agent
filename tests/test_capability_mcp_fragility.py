"""Mixed MCP+absorbed pipelines must be scored on the fragility plane."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_fragility import run_fragility_audit
from blackhole_agent.capability_mcp_application import MCP_APPLICATION_BRIDGE_ID, MCP_SHA256_ID
from blackhole_agent.capability_mcp_fragility import (
    MCP_FRAGILITY_ID,
    builtin_mcp_fragility_proof,
    compute_fragility_verdicts,
    run_mcp_fragility_plane,
    verify_mcp_fragility_report,
)
from blackhole_agent.capability_mcp_recovery import MCP_RECOVERY_ID
from blackhole_agent.capability_mcp_reliability import MCP_RELIABILITY_ID, load_mcp_composition_tasks
from blackhole_agent.capability_mcp_stack import MCP_STACK_ID
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_default_fragility_ignores_mcp_hop_blast() -> None:
    tasks = load_mcp_composition_tasks()
    assert tasks, "persisted mixed MCP+absorbed bridge must yield a composition goal"
    mcp_ids = {task.id for task in tasks}
    report = run_fragility_audit()
    grade = report["fragility"]
    assert MCP_SHA256_ID not in grade["blast_radius"]
    assert mcp_ids.isdisjoint(grade["spofs_per_goal"])
    assert grade["fragility_score"] == 0.1667
    assert grade["max_blast_radius"] == 2
    assert grade["robust_goals"] == ["ledger-inventory-check"]


def test_mcp_fragility_counts_hop_spof_in_blast_radius() -> None:
    honesty = compute_fragility_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["mcp_hop_blast_named"]
    assert honesty["verdicts"]["mcp_hop_is_spof"]
    assert honesty["verdicts"]["mixed_goal_fragile"]
    assert honesty["mcp_id"] == MCP_SHA256_ID
    assert honesty["composition_id"] == "mcp-compose-text-reverser-echo-sha256"
    assert honesty["mixed"]["blast_radius"][MCP_SHA256_ID] == 1
    assert honesty["mixed"]["impact_matrix"][MCP_SHA256_ID] == [
        "mcp-compose-text-reverser-echo-sha256"
    ]
    assert MCP_SHA256_ID in honesty["mixed"]["spofs_per_goal"]["mcp-compose-text-reverser-echo-sha256"]


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_mcp_fragility_plane(report_dir)
    assert result["ok"], result
    verification = verify_mcp_fragility_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["mcp_hop_blast_named"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_mcp_fragility_report(report_dir)["ok"] is False


def test_leftover_binds_mcp_fragility_plane() -> None:
    leftover = (
        "Optional later work is scoring mixed MCP+absorbed goals on the "
        "fragility plane so an MCP hop SPOF is counted in blast radius."
    )
    assert leftover_marker_ids(leftover) == (MCP_FRAGILITY_ID,)
    assert MCP_RELIABILITY_ID not in leftover_marker_ids(leftover)
    assert MCP_RECOVERY_ID not in leftover_marker_ids(leftover)
    assert MCP_STACK_ID not in leftover_marker_ids(leftover)
    assert MCP_APPLICATION_BRIDGE_ID not in leftover_marker_ids(leftover)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_mcp_fragility_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_FRAGILITY_ID]
    assert capability.last_proof_exit_code == 0
    assert "fragility" in capability.tags
    assert "mcp" in capability.tags
