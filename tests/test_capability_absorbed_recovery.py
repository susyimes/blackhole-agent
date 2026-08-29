"""Absorbed composition pipelines must be recoverable."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_absorbed_recovery import (
    ABSORBED_RECOVERY_ID,
    builtin_absorbed_recovery_proof,
    compute_recovery_verdicts,
    run_absorbed_recovery_plane,
    verify_absorbed_recovery_report,
)
from blackhole_agent.capability_absorbed_reliability import load_absorbed_composition_tasks as load_tasks
from blackhole_agent.capability_application import APPLICATION_TASKS
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_recovery import BREAK_STALE_STAMP, run_recovery_loop
from blackhole_agent.kernel_leftover import leftover_marker_ids


def test_default_recovery_ignores_red_absorbed_producer() -> None:
    tasks = load_tasks()
    assert tasks, "persisted typed key-bridge must yield a composition goal"
    absorbed_ids = {task.id for task in tasks}
    report = run_recovery_loop(breaks={"capability.absorbed-text-reverser": BREAK_STALE_STAMP})
    watched = {record["id"] for record in report["task_records"]}
    assert absorbed_ids.isdisjoint(watched)
    assert {task.id for task in APPLICATION_TASKS} == watched
    assert report["ok"] is True
    assert report["recovery"]["repair_count"] == 0
    assert "capability.absorbed-text-reverser" not in report["blocked_capabilities"]


def test_absorbed_recovery_heals_producer_and_fails_honestly() -> None:
    honesty = compute_recovery_verdicts()
    assert honesty["ok"], honesty["verdicts"]
    assert honesty["verdicts"]["base_isolation"]
    assert honesty["verdicts"]["live_absorbed_healthy"]
    assert honesty["verdicts"]["producer_stale_healed"]
    assert honesty["verdicts"]["producer_unrepairable_honest"]
    assert "absorbed-compose-text-reverser-snake-case" in honesty["absorbed_ids"]
    assert honesty["healed"]["repair_verdicts"]["capability.absorbed-text-reverser"] == "repaired"


def test_plane_seals_and_rejects_tamper(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    result = run_absorbed_recovery_plane(report_dir)
    assert result["ok"], result
    verification = verify_absorbed_recovery_report(report_dir)
    assert verification["ok"], verification
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    report["verdicts"]["producer_stale_healed"] = False
    (report_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    assert verify_absorbed_recovery_report(report_dir)["ok"] is False


def test_leftover_binds_recovery_plane() -> None:
    leftover = (
        "Repair recovery failure: a red absorbed producer leaves the typed "
        "composition pipeline unplannable, but the recovery loop never heals it."
    )
    assert leftover_marker_ids(leftover) == (ABSORBED_RECOVERY_ID,)


def test_builtin_proof_registers_and_is_falsifiable() -> None:
    result = builtin_absorbed_recovery_proof()
    assert result["ok"], result
    assert result["verify_ok"]
    assert result["tamper_detected"]
    assert result["misgrade_detected"]
    assert not result["used_skill_route_discovery"]
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[ABSORBED_RECOVERY_ID]
    assert capability.last_proof_exit_code == 0
    assert "recovery" in capability.tags
