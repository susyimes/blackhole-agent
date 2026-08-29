"""Mixed MCP+absorbed goals must be reliability-visible."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import APPLICATION_TASKS
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_mcp_application import MCP_APPLICATION_BRIDGE_ID, MCP_SHA256_ID
from blackhole_agent.capability_mcp_reliability import (
    MCP_RELIABILITY_ID,
    builtin_mcp_reliability_proof,
    compute_reliability_verdicts,
    load_mcp_composition_tasks,
    run_mcp_reliability_plane,
    verify_mcp_reliability_report,
)
from blackhole_agent.capability_watchdog import run_goal_watchdog
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_default_watchdog_ignores_mcp_composition_goals() -> None:
    tasks = load_mcp_composition_tasks()
    assert tasks, "persisted mixed MCP+absorbed bridge must yield a composition goal"
    mcp_ids = {task.id for task in tasks}
    report = run_goal_watchdog()
    watched = {record["id"] for record in report["goal_results"]}
    assert mcp_ids.isdisjoint(watched)
    assert {task.id for task in APPLICATION_TASKS} == watched


def test_mcp_watchdog_solves_composition_and_names_mcp_hop_drift() -> None:
    honesty = compute_reliability_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_mcp_healthy"]
    assert honesty["verdicts"]["mcp_hide_named_drift"]
    assert honesty["verdicts"]["producer_red_named_drift"]
    assert honesty["verdicts"]["mcp_hop_is_spof"]
    assert honesty["verdicts"]["base_unaffected_by_mcp_hide"]
    assert honesty["verdicts"]["absorbed_unaffected_by_mcp_hide"]
    assert "mcp-compose-text-reverser-echo-sha256" in honesty["mcp_ids"]
    plans = honesty["live"]["plans"]["mcp-compose-text-reverser-echo-sha256"]
    assert MCP_SHA256_ID in plans
    assert "capability.mcp-bridge-text-reverser-echo-sha256" in plans
    assert MCP_SHA256_ID in honesty["drift_by_mcp"]
    assert honesty["drift_by_mcp"][MCP_SHA256_ID] == ["mcp-compose-text-reverser-echo-sha256"]


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_mcp_reliability_plane(report_dir)
    assert result["ok"], result
    verification = verify_mcp_reliability_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["mcp_hide_named_drift"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_mcp_reliability_report(report_dir)["ok"] is False


def test_leftover_binds_mcp_reliability_plane() -> None:
    leftover = (
        "Optional later work is watching mixed MCP+absorbed goals in the "
        "reliability plane so a hidden MCP hop is named drift."
    )
    assert leftover_marker_ids(leftover) == (MCP_RELIABILITY_ID,)
    assert MCP_APPLICATION_BRIDGE_ID not in leftover_marker_ids(leftover)


def test_mcp_application_leftover_stays_on_the_bridge() -> None:
    leftover = (
        "Repair planner isolation of live MCP tools: import a live MCP tool as "
        "an application step and compose it with an independently absorbed "
        "Python tool so a mixed MCP+absorbed goal is planner-derived and "
        "solvable, and hiding either member or the bridge fails the outcome."
    )
    assert leftover_marker_ids(leftover) == (MCP_APPLICATION_BRIDGE_ID,)
    assert MCP_RELIABILITY_ID not in leftover_marker_ids(leftover)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_mcp_reliability_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert result["drift_hiding_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_RELIABILITY_ID]
    assert capability.last_proof_exit_code == 0
    assert "reliability" in capability.tags
    assert "mcp" in capability.tags
