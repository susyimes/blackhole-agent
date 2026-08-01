"""Tests for the goal watchdog and the milestone goal-regression gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from blackhole_agent.capability_application import REPO_ROOT
from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.capability_repair import _clone_ledger, _replace_capability_fields
from blackhole_agent.capability_watchdog import (
    builtin_goal_watchdog,
    run_goal_watchdog,
    verify_watchdog_report,
    write_watchdog_report,
)


def test_live_workspace_is_healthy() -> None:
    report = run_goal_watchdog()
    assert report["ok"] is True
    assert report["drifted_goals"] == []
    assert report["healthy_count"] == report["goal_count"]
    assert all(record["solvable"] for record in report["goal_results"])


def test_red_stamp_drift_is_flagged_by_goal_name() -> None:
    ledger = _replace_capability_fields(
        _clone_ledger(load_ledger(default_ledger_path(REPO_ROOT))),
        "domain.tool-routing",
        last_proof_exit_code=1,
        last_proved_at="",
    )
    report = run_goal_watchdog(ledger=ledger)
    assert report["ok"] is False
    assert report["drifted_goals"] == ["routed-triage-record"]
    record = next(item for item in report["goal_results"] if item["id"] == "routed-triage-record")
    assert record["solvable"] is False


def test_watchdog_is_deterministic() -> None:
    first = run_goal_watchdog()
    second = run_goal_watchdog()
    assert first["goals_digest"] == second["goals_digest"]
    assert first["report_digest"] == second["report_digest"]


def test_sealed_report_verifies_and_drift_hiding_fails(tmp_path: Path) -> None:
    ledger = _replace_capability_fields(
        _clone_ledger(load_ledger(default_ledger_path(REPO_ROOT))),
        "domain.tool-routing",
        last_proof_exit_code=1,
        last_proved_at="",
    )
    drift = run_goal_watchdog(ledger=ledger)
    out = tmp_path / "report"
    write_watchdog_report(drift, out)
    verified = verify_watchdog_report(out)
    assert verified["ok"] is True, verified

    hidden = json.loads((out / "report.json").read_text(encoding="utf-8"))
    hidden["drifted_goals"] = []
    hidden["ok"] = True
    (out / "report.json").write_text(json.dumps(hidden), encoding="utf-8")
    assert verify_watchdog_report(out)["ok"] is False


def test_builtin_goal_watchdog_proof() -> None:
    result = builtin_goal_watchdog()
    assert result["ok"] is True, result
    assert result["drift_detected"] is True
    assert result["drift_hiding_detected"] is True
    assert result["deterministic"] is True
    assert result["used_skill_route_discovery"] is False


def test_milestone_gate_refuses_goal_regression(monkeypatch) -> None:
    from blackhole_agent import unbound

    decision = unbound.TurnDecision.from_payload(
        {
            "status": "milestone",
            "summary": "s",
            "capability_delta": "d",
            "outcome_evidence": ["e"],
            "validation": [{"command": f'"{sys.executable}" -c "pass"', "exit_code": 0, "summary": "ok"}],
        }
    )
    monkeypatch.setattr(
        unbound,
        "run_workspace_goal_watchdog",
        lambda workspace: {"ok": False, "drifted_goals": ["routed-triage-record"]},
    )
    gate = unbound.evaluate_milestone(
        decision,
        changed_paths=["src/blackhole_agent/unbound.py"],
        workspace=REPO_ROOT,
    )
    assert gate.accepted is False
    assert any("goal regression detected by watchdog" in reason for reason in gate.reasons)


def test_milestone_gate_accepts_healthy_watchdog() -> None:
    from blackhole_agent import unbound

    decision = unbound.TurnDecision.from_payload(
        {
            "status": "milestone",
            "summary": "s",
            "capability_delta": "d",
            "outcome_evidence": ["e"],
            "validation": [{"command": f'"{sys.executable}" -c "pass"', "exit_code": 0, "summary": "ok"}],
        }
    )
    gate = unbound.evaluate_milestone(
        decision,
        changed_paths=["src/blackhole_agent/unbound.py"],
        workspace=REPO_ROOT,
    )
    assert gate.accepted is True, gate.reasons


def test_workspace_watchdog_subprocess_reports_health() -> None:
    from blackhole_agent import unbound

    result = unbound.run_workspace_goal_watchdog(REPO_ROOT)
    assert result is not None
    assert result["ok"] is True
    assert result["drifted_goals"] == []
