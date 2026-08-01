"""Tests for the goal-stack portability proof."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_portability import (
    _stamp_capability_red,
    _watchdog_summary,
    builtin_portability_plane,
    checkout_pristine_source,
    run_portability_plane,
    verify_portability_report,
    write_portability_report,
)


def test_pristine_checkout_contains_tracked_source(tmp_path: Path) -> None:
    result = checkout_pristine_source(tmp_path / "checkout")
    assert (tmp_path / "checkout" / "src" / "blackhole_agent" / "capability_application.py").exists()
    assert (tmp_path / "checkout" / "capabilities" / "ledger.json").exists()
    assert (tmp_path / "checkout" / "tests" / "fixtures").is_dir()
    assert result["file_count"] > 100


def test_watchdog_runs_green_in_pristine_checkout(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout_pristine_source(checkout)
    summary = _watchdog_summary(checkout)
    assert summary["ok"] is True
    assert summary["healthy_count"] == summary["goal_count"]
    assert summary["drifted_goals"] == []


def test_corrupted_checkout_flags_drift(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    checkout_pristine_source(checkout)
    _stamp_capability_red(checkout, "domain.tool-routing")
    summary = _watchdog_summary(checkout)
    assert summary["ok"] is False
    assert summary["exit_code"] != 0
    assert summary["drifted_goals"] == ["routed-triage-record"]


def test_run_portability_plane_end_to_end() -> None:
    report = run_portability_plane()
    assert report["ok"] is True, report["portability"]
    assert report["portability"]["pristine_ok"] is True
    assert report["portability"]["cross_checkout_determinism"] is True
    assert report["portability"]["corruption_detected"] is True
    assert report["portability"]["application_score"] == 1.0


def test_sealed_report_verifies_and_tamper_fails(tmp_path: Path) -> None:
    report = run_portability_plane()
    out = tmp_path / "report"
    summary = write_portability_report(report, out)
    assert summary["ok"] is True
    verified = verify_portability_report(out)
    assert verified["ok"] is True, verified

    tampered = json.loads((out / "report.json").read_text(encoding="utf-8"))
    tampered["checkouts"]["corrupted"]["watchdog"]["drifted_goals"] = []
    (out / "report.json").write_text(json.dumps(tampered), encoding="utf-8")
    assert verify_portability_report(out)["ok"] is False


def test_builtin_portability_plane_proof() -> None:
    result = builtin_portability_plane()
    assert result["ok"] is True, result
    assert result["portability"]["pristine_ok"] is True
    assert result["portability"]["corruption_detected"] is True
    assert result["tamper_detected"] is True
    assert result["misgrade_detected"] is True
    assert result["used_skill_route_discovery"] is False
