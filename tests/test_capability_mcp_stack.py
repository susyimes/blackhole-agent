"""Mixed MCP+absorbed pipelines must fail stack health when the hop is red."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_mcp_application import MCP_APPLICATION_BRIDGE_ID, MCP_SHA256_ID
from blackhole_agent.capability_mcp_fragility import MCP_FRAGILITY_ID
from blackhole_agent.capability_mcp_recovery import MCP_RECOVERY_ID
from blackhole_agent.capability_mcp_reliability import MCP_RELIABILITY_ID, load_mcp_composition_tasks
from blackhole_agent.capability_mcp_stack import (
    MCP_STACK_ID,
    builtin_mcp_stack_health_proof,
    compute_mcp_stack_health,
    compute_stack_verdicts,
    run_mcp_stack_health_plane,
    verify_mcp_stack_health_report,
)
from blackhole_agent.capability_stack import run_stack_health
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_default_stack_health_ignores_mcp_composition() -> None:
    tasks = load_mcp_composition_tasks()
    assert tasks, "persisted mixed MCP+absorbed bridge must yield a composition goal"
    mcp_ids = {task.id for task in tasks}
    report = run_stack_health()
    assert report["ok"] is True
    assert report["health"]["healthy"] is True
    watchdog_ids = set()
    for record in report["headlines"]["watchdog"].get("drifted_goals") or []:
        watchdog_ids.add(record)
    assert mcp_ids.isdisjoint(watchdog_ids)
    assert MCP_SHA256_ID not in json.dumps(report["headlines"]["fragility"])


def test_mcp_stack_health_fails_when_hop_is_red() -> None:
    honesty = compute_stack_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_mcp_stack_healthy"]
    assert honesty["verdicts"]["red_hop_fails_stack"]
    assert honesty["verdicts"]["base_stack_ignores_red_hop"]
    assert honesty["mcp_id"] == MCP_SHA256_ID
    assert honesty["composition_id"] == "mcp-compose-text-reverser-echo-sha256"
    assert honesty["live"]["health"]["healthy"] is True
    assert honesty["live"]["health"]["green_count"] == 4
    assert honesty["red"]["health"]["healthy"] is False
    assert "mcp-compose-text-reverser-echo-sha256" in honesty["red"]["headlines"]["watchdog"]["drifted_goals"]
    assert honesty["red"]["headlines"]["recovery"]["repair_count"] >= 1
    live_grade = compute_mcp_stack_health(honesty["live"]["headlines"])
    red_grade = compute_mcp_stack_health(honesty["red"]["headlines"])
    assert live_grade == honesty["live"]["health"]
    assert red_grade == honesty["red"]["health"]
    assert red_grade["planes_green"]["watchdog"] is False
    assert red_grade["planes_green"]["recovery"] is False


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_mcp_stack_health_plane(report_dir)
    assert result["ok"], result
    verification = verify_mcp_stack_health_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["red_hop_fails_stack"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_mcp_stack_health_report(report_dir)["ok"] is False


def test_leftover_binds_mcp_stack_health_plane() -> None:
    leftover = (
        "Optional later work is folding mixed Python-to-MCP pipelines into "
        "goal-stack health so a red hop fails the stack grade."
    )
    assert leftover_marker_ids(leftover) == (MCP_STACK_ID,)
    assert MCP_RELIABILITY_ID not in leftover_marker_ids(leftover)
    assert MCP_RECOVERY_ID not in leftover_marker_ids(leftover)
    assert MCP_FRAGILITY_ID not in leftover_marker_ids(leftover)
    assert MCP_APPLICATION_BRIDGE_ID not in leftover_marker_ids(leftover)


def test_recovery_leftover_stays_on_the_heal_plane() -> None:
    leftover = (
        "Optional later work is watching mixed MCP+absorbed goals in the "
        "recovery plane so a red MCP hop is healed."
    )
    assert leftover_marker_ids(leftover) == (MCP_RECOVERY_ID,)
    assert MCP_STACK_ID not in leftover_marker_ids(leftover)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_mcp_stack_health_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MCP_STACK_ID]
    assert capability.last_proof_exit_code == 0
    assert "stack-health" in capability.tags
    assert "mcp" in capability.tags
