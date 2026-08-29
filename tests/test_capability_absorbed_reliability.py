"""Absorbed composition goals must be reliability-visible."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_absorbed_reliability import (
    ABSORBED_RELIABILITY_ID,
    builtin_absorbed_reliability_proof,
    compute_reliability_verdicts,
    load_absorbed_composition_tasks,
    run_absorbed_reliability_plane,
    verify_absorbed_reliability_report,
)
from blackhole_agent.capability_application import APPLICATION_TASKS
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_watchdog import run_goal_watchdog
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_default_watchdog_ignores_absorbed_composition_goals() -> None:
    tasks = load_absorbed_composition_tasks()
    assert tasks, "persisted typed key-bridge must yield a composition goal"
    absorbed_ids = {task.id for task in tasks}
    report = run_goal_watchdog()
    watched = {record["id"] for record in report["goal_results"]}
    assert absorbed_ids.isdisjoint(watched)
    assert {task.id for task in APPLICATION_TASKS} == watched


def test_absorbed_watchdog_solves_composition_and_names_bridge_drift() -> None:
    honesty = compute_reliability_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_absorbed_healthy"]
    assert honesty["verdicts"]["bridge_hide_named_drift"]
    assert honesty["verdicts"]["producer_red_named_drift"]
    assert honesty["verdicts"]["bridge_is_spof"]
    assert honesty["verdicts"]["base_unaffected_by_bridge_hide"]
    assert "absorbed-compose-text-reverser-snake-case" in honesty["absorbed_ids"]
    plans = honesty["live"]["plans"]["absorbed-compose-text-reverser-snake-case"]
    assert "capability.absorbed-bridge-text-reverser-snake-case" in plans


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_absorbed_reliability_plane(report_dir)
    assert result["ok"], result
    verification = verify_absorbed_reliability_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["bridge_hide_named_drift"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_absorbed_reliability_report(report_dir)["ok"] is False


def test_leftover_binds_reliability_plane() -> None:
    leftover = (
        "Repair reliability failure: absorbed composition goals are invisible "
        "to the goal watchdog, so a broken typed key-bridge ships as a healthy "
        "stack. Fold those live absorbed goals into a sealed reliability plane "
        "that reports named drift when the bridge is hidden."
    )
    assert leftover_marker_ids(leftover) == (ABSORBED_RELIABILITY_ID,)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_absorbed_reliability_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert result["drift_hiding_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ABSORBED_RELIABILITY_ID]
    assert capability.last_proof_exit_code == 0
    assert "reliability" in capability.tags
