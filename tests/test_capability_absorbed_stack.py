"""Absorbed composition pipelines must fail stack health when the producer is red."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_absorbed_recovery import ABSORBED_RECOVERY_ID
from blackhole_agent.capability_absorbed_reliability import (
    ABSORBED_RELIABILITY_ID,
    load_absorbed_composition_tasks,
)
from blackhole_agent.capability_absorbed_stack import (
    ABSORBED_STACK_ID,
    builtin_absorbed_stack_health_proof,
    compute_absorbed_stack_health,
    compute_stack_verdicts,
    run_absorbed_stack_health_plane,
    verify_absorbed_stack_health_report,
)
from blackhole_agent.capability_absorbed_stack_repair import ABSORBED_STACK_REPAIR_ID
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_mcp_stack import MCP_STACK_ID
from blackhole_agent.capability_stack import run_stack_health
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_default_stack_health_ignores_absorbed_composition() -> None:
    tasks = load_absorbed_composition_tasks()
    assert tasks, "persisted typed key-bridge must yield a composition goal"
    absorbed_ids = {task.id for task in tasks}
    report = run_stack_health()
    assert report["ok"] is True
    assert report["health"]["healthy"] is True
    watchdog_ids = set(report["headlines"]["watchdog"].get("drifted_goals") or [])
    assert absorbed_ids.isdisjoint(watchdog_ids)
    assert "capability.absorbed-text-reverser" not in json.dumps(report["headlines"]["fragility"])


def test_absorbed_stack_health_fails_when_producer_is_red() -> None:
    honesty = compute_stack_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_absorbed_stack_healthy"]
    assert honesty["verdicts"]["red_producer_fails_stack"]
    assert honesty["verdicts"]["base_stack_ignores_red_producer"]
    assert honesty["producer_id"] == "capability.absorbed-text-reverser"
    assert honesty["composition_id"] == "absorbed-compose-text-reverser-snake-case"
    assert honesty["live"]["health"]["healthy"] is True
    assert honesty["live"]["health"]["green_count"] == 4
    assert honesty["red"]["health"]["healthy"] is False
    assert "absorbed-compose-text-reverser-snake-case" in honesty["red"]["headlines"]["watchdog"]["drifted_goals"]
    assert honesty["red"]["headlines"]["recovery"]["repair_count"] >= 1
    live_grade = compute_absorbed_stack_health(honesty["live"]["headlines"])
    red_grade = compute_absorbed_stack_health(honesty["red"]["headlines"])
    assert live_grade == honesty["live"]["health"]
    assert red_grade == honesty["red"]["health"]
    assert red_grade["planes_green"]["watchdog"] is False
    assert red_grade["planes_green"]["recovery"] is False


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_absorbed_stack_health_plane(report_dir)
    assert result["ok"], result
    verification = verify_absorbed_stack_health_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["red_producer_fails_stack"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_absorbed_stack_health_report(report_dir)["ok"] is False


def test_leftover_binds_absorbed_stack_health_plane() -> None:
    leftover = (
        "Optional later work is folding absorbed composition pipelines into "
        "goal-stack health so a red producer fails the mixed absorbed stack grade."
    )
    assert leftover_marker_ids(leftover) == (ABSORBED_STACK_ID,)
    assert MCP_STACK_ID not in leftover_marker_ids(leftover)
    assert ABSORBED_RELIABILITY_ID not in leftover_marker_ids(leftover)
    assert ABSORBED_RECOVERY_ID not in leftover_marker_ids(leftover)
    assert ABSORBED_STACK_REPAIR_ID not in leftover_marker_ids(leftover)


def test_mcp_stack_leftover_stays_on_the_mcp_plane() -> None:
    leftover = (
        "Optional later work is folding mixed Python-to-MCP pipelines into "
        "goal-stack health so a red hop fails the stack grade."
    )
    assert leftover_marker_ids(leftover) == (MCP_STACK_ID,)
    assert ABSORBED_STACK_ID not in leftover_marker_ids(leftover)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_absorbed_stack_health_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ABSORBED_STACK_ID]
    assert capability.last_proof_exit_code == 0
    assert "stack-health" in capability.tags
    assert "absorbed" in capability.tags
