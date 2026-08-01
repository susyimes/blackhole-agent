"""Tests for the capability recovery loop."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_recovery import (
    BREAK_FAILING_PROOF,
    BREAK_STALE_INTERPRETER,
    apply_synthetic_break,
    builtin_recovery_loop,
    check_recovery_consistency,
    compute_recovery_grade,
    run_recovery_loop,
    verify_recovery_report,
    write_recovery_report,
)
from blackhole_agent.capability_compounder import (
    default_ledger_path,
    load_ledger,
)
from blackhole_agent.capability_application import REPO_ROOT


def test_baseline_loop_solves_everything_without_repairs() -> None:
    report = run_recovery_loop()
    assert report["ok"] is True
    assert report["recovery"]["repair_count"] == 0
    assert report["recovery"]["task_pass_count"] == report["recovery"]["task_count"]
    assert report["recovery"]["recovered"] == []
    assert report["blocked_capabilities"] == []


def test_stale_interpreter_break_heals_and_recovers_goal() -> None:
    report = run_recovery_loop(breaks={"domain.tool-routing": BREAK_STALE_INTERPRETER})
    assert report["ok"] is True, report["recovery"]
    assert report["recovery"]["recovered"] == ["routed-triage-record"]
    repair = next(item for item in report["repairs"] if item["capability_id"] == "domain.tool-routing")
    assert repair["verdict"] == "repaired"
    assert "regenerate_proof_command" in repair["repair_actions"]
    assert repair["honest"] is True
    record = next(item for item in report["task_records"] if item["id"] == "routed-triage-record")
    assert record["initially_unplannable"] is True
    assert record["ok"] is True
    assert record["plan"] == ["domain.tool-routing", "domain.issue-triage", "domain.local-memory"]


def test_failing_proof_break_is_honestly_unsolved() -> None:
    report = run_recovery_loop(breaks={"capability.ledger-inventory": BREAK_FAILING_PROOF})
    assert report["ok"] is False
    assert report["recovery"]["honest_unsolved"] == ["ledger-gated-proposal"]
    assert report["recovery"]["unrepairable_count"] == 1
    record = next(item for item in report["task_records"] if item["id"] == "ledger-gated-proposal")
    assert record["initially_unplannable"] is True
    assert record["ok"] is False
    repair = next(item for item in report["repairs"] if item["capability_id"] == "capability.ledger-inventory")
    assert repair["verdict"] == "unrepairable"
    assert repair["last_proof_exit_code"] != 0
    assert repair["honest"] is True


def test_synthetic_breaks_never_touch_live_ledger() -> None:
    before = load_ledger(default_ledger_path(REPO_ROOT))
    run_recovery_loop(breaks={"domain.tool-routing": BREAK_STALE_INTERPRETER})
    run_recovery_loop(breaks={"capability.ledger-inventory": BREAK_FAILING_PROOF})
    after = load_ledger(default_ledger_path(REPO_ROOT))
    for capability_id in ("domain.tool-routing", "capability.ledger-inventory"):
        assert after.capabilities[capability_id].last_proof_exit_code == 0
        assert (
            after.capabilities[capability_id].proof_command
            == before.capabilities[capability_id].proof_command
        )


def test_recovery_loop_is_deterministic_under_same_break() -> None:
    first = run_recovery_loop(breaks={"domain.tool-routing": BREAK_STALE_INTERPRETER})
    second = run_recovery_loop(breaks={"domain.tool-routing": BREAK_STALE_INTERPRETER})
    assert first["repairs_digest"] == second["repairs_digest"]
    assert first["tasks_digest"] == second["tasks_digest"]
    assert first["report_digest"] == second["report_digest"]


def test_compute_recovery_grade_is_pure() -> None:
    task_records = [
        {"id": "a", "initially_unplannable": True, "ok": True},
        {"id": "b", "initially_unplannable": False, "ok": True},
    ]
    repairs = [{"capability_id": "x", "verdict": "repaired", "honest": True}]
    graded = compute_recovery_grade(task_records, repairs)
    assert graded["recovered"] == ["a"]
    assert compute_recovery_grade(task_records, repairs) == graded

    task_records[0]["ok"] = False
    degraded = compute_recovery_grade(task_records, repairs)
    assert degraded["recovered"] == []
    # No unrepairable verdict -> not an honest unsolved either.
    assert degraded["honest_unsolved"] == []


def test_consistency_catches_fake_healing() -> None:
    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    task_records = [{"id": "a", "initially_unplannable": True, "ok": False, "plan": None}]
    # Unsolved but no unrepairable verdict backing it -> inconsistent.
    forged = [{"capability_id": "x", "verdict": "repaired", "honest": True}]
    consistency = check_recovery_consistency(task_records, forged, ledger)
    assert consistency["unsolved_backed_by_unrepairable"] is False

    honest = [{"capability_id": "x", "verdict": "unrepairable", "honest": True}]
    consistency = check_recovery_consistency(task_records, honest, ledger)
    assert all(consistency.values()), consistency


def test_sealed_report_verifies_and_tamper_fails(tmp_path: Path) -> None:
    report = run_recovery_loop()
    out = tmp_path / "report"
    summary = write_recovery_report(report, out)
    assert summary["ok"] is True
    verified = verify_recovery_report(out)
    assert verified["ok"] is True, verified

    tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
    tampered["task_records"][0]["ok"] = not tampered["task_records"][0]["ok"]
    (out / "report.json").write_text(json.dumps(tampered), encoding="utf-8")
    assert verify_recovery_report(out)["ok"] is False


def test_apply_synthetic_break_modes() -> None:
    from blackhole_agent.capability_repair import _clone_ledger

    ledger = load_ledger(default_ledger_path(REPO_ROOT))
    scratch = _clone_ledger(ledger)
    broken = apply_synthetic_break(scratch, "domain.tool-routing", BREAK_STALE_INTERPRETER)
    capability = broken.capabilities["domain.tool-routing"]
    assert capability.last_proof_exit_code == 1
    assert "nonexistent" in capability.proof_command
    # The loaded live ledger is untouched: breaks apply to the scratch clone.
    assert ledger.capabilities["domain.tool-routing"].last_proof_exit_code == 0


def test_builtin_recovery_loop_proof() -> None:
    result = builtin_recovery_loop()
    assert result["ok"] is True, result
    assert result["healed"] is True
    assert result["honest_unsolved"] is True
    assert result["deterministic"] is True
    assert result["used_skill_route_discovery"] is False
