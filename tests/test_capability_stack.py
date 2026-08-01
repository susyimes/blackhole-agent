"""Tests for the goal-stack composite health capability."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_stack import (
    builtin_stack_health,
    compute_stack_health,
    run_stack_health,
    verify_stack_report,
    write_stack_report,
)


def test_stack_is_healthy_live() -> None:
    report = run_stack_health()
    assert report["ok"] is True
    assert report["health"]["healthy"] is True
    assert report["health"]["green_count"] == report["health"]["plane_count"] == 4
    assert report["headlines"]["application"]["application_score"] == 1.0
    assert report["headlines"]["watchdog"]["drifted_goals"] == []
    assert report["headlines"]["recovery"]["repair_count"] == 0


def test_compute_stack_health_is_pure() -> None:
    report = run_stack_health()
    headlines = report["headlines"]
    graded = compute_stack_health(headlines)
    assert compute_stack_health(headlines) == graded

    degraded_headlines = json.loads(json.dumps(headlines))
    degraded_headlines["watchdog"]["drifted_goals"] = ["routed-triage-record"]
    degraded_headlines["watchdog"]["ok"] = False
    degraded = compute_stack_health(degraded_headlines)
    assert degraded["healthy"] is False
    assert degraded["planes_green"]["watchdog"] is False
    assert degraded["planes_green"]["application"] is True


def test_sealed_report_verifies_and_tamper_fails(tmp_path: Path) -> None:
    report = run_stack_health()
    out = tmp_path / "report"
    summary = write_stack_report(report, out)
    assert summary["ok"] is True
    verified = verify_stack_report(out)
    assert verified["ok"] is True, verified

    tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
    tampered["headlines"]["watchdog"]["drifted_goals"] = ["routed-triage-record"]
    (out / "report.json").write_text(json.dumps(tampered), encoding="utf-8")
    assert verify_stack_report(out)["ok"] is False


def test_builtin_stack_health_proof() -> None:
    result = builtin_stack_health()
    assert result["ok"] is True, result
    assert result["health"]["healthy"] is True
    assert result["health"]["green_count"] == 4
    assert result["tamper_detected"] is True
    assert result["misgrade_detected"] is True
    assert result["used_skill_route_discovery"] is False
