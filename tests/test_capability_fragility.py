"""Tests for the goal fragility audit."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.capability_application import APPLICATION_TASKS
from blackhole_agent.capability_compounder import (
    default_ledger_path,
    load_ledger,
)
from blackhole_agent.capability_fragility import (
    REPO_ROOT,
    blast_radius_map,
    builtin_fragility_audit,
    compute_fragility_grade,
    compute_impact_matrix,
    repair_priority_order,
    run_fragility_audit,
    verify_fragility_report,
    write_fragility_report,
)


def _live_ledger():
    return load_ledger(default_ledger_path(REPO_ROOT))


def test_impact_matrix_covers_surface_and_finds_shared_structure() -> None:
    matrix = compute_impact_matrix(_live_ledger())
    # Redundancy: neither readiness provider blocks anything alone.
    assert matrix["capability.ledger-inventory"] == []
    assert matrix["capability.ledger-attestation"] == []
    assert matrix["domain.tool-routing"] == ["routed-triage-record"]
    assert matrix["domain.local-memory"] == ["routed-triage-record"]
    assert matrix["domain.ci-security"] == ["blocked-scan-honesty", "scan-gated-activation"]
    assert matrix["domain.harness-activation"] == ["blocked-scan-honesty", "scan-gated-activation"]
    assert matrix["domain.proposal-eval"] == ["ledger-gated-proposal"]
    assert matrix["domain.persona"] == ["persona-stamped-proposal"]
    assert matrix["domain.proposal-synthesis"] == ["persona-stamped-proposal"]


def test_fragility_grade_tracks_redundancy() -> None:
    matrix = compute_impact_matrix(_live_ledger())
    grade = compute_fragility_grade(matrix)
    # The redundant readiness path lifted one goal to zero SPOFs; the
    # widened 6-goal surface scores 1/6.
    assert grade["fragility_score"] == round(1 / 6, 4)
    assert grade["robust_goals"] == ["ledger-inventory-check"]
    assert len(grade["fragile_goals"]) == len(APPLICATION_TASKS) - 1
    assert grade["max_blast_radius"] == 2
    assert grade["critical_capabilities"][0] == "domain.ci-security"
    assert grade["spofs_per_goal"]["ledger-inventory-check"] == []
    assert grade["spofs_per_goal"]["ledger-gated-proposal"] == ["domain.proposal-eval"]
    assert grade["spofs_per_goal"]["persona-stamped-proposal"] == [
        "domain.persona",
        "domain.proposal-synthesis",
    ]


def test_compute_fragility_grade_is_pure() -> None:
    matrix = compute_impact_matrix(_live_ledger())
    graded = compute_fragility_grade(matrix)
    assert compute_fragility_grade(matrix) == graded
    # A matrix where one goal has no SPOFs raises the score.
    reduced = {cid: [g for g in blocked if g != "ledger-inventory-check"] for cid, blocked in matrix.items()}
    degraded = compute_fragility_grade(reduced)
    assert "ledger-inventory-check" in degraded["robust_goals"]
    assert degraded["fragility_score"] > 0.0


def test_repair_priority_orders_by_blast_radius() -> None:
    ledger = _live_ledger()
    order = repair_priority_order(ledger, ["capability.ledger-inventory", "domain.tool-routing"])
    assert order == ["domain.tool-routing", "capability.ledger-inventory"]
    blast = blast_radius_map(ledger)
    assert blast["capability.ledger-inventory"] == 0
    assert blast["domain.tool-routing"] == 1
    assert blast["domain.ci-security"] == 2


def test_run_fragility_audit_is_deterministic() -> None:
    first = run_fragility_audit()
    second = run_fragility_audit()
    assert first["matrix_digest"] == second["matrix_digest"]
    assert first["report_digest"] == second["report_digest"]
    assert first["ok"] is True


def test_sealed_report_verifies_and_forged_cell_fails(tmp_path: Path) -> None:
    report = run_fragility_audit()
    out = tmp_path / "report"
    summary = write_fragility_report(report, out)
    assert summary["ok"] is True
    verified = verify_fragility_report(out)
    assert verified["ok"] is True, verified

    forged = json.loads((out / "report.json").read_text(encoding="utf-8"))
    forged["impact_matrix"]["domain.tool-routing"] = []
    (out / "report.json").write_text(json.dumps(forged), encoding="utf-8")
    result = verify_fragility_report(out)
    assert result["ok"] is False
    assert result["checks"]["matrix_recomputed_matches"] is False


def test_builtin_fragility_audit_proof() -> None:
    result = builtin_fragility_audit()
    assert result["ok"] is True, result
    assert result["fragility"]["fragility_score"] == round(1 / 6, 4)
    assert result["fragility"]["robust_goals"] == ["ledger-inventory-check"]
    assert result["priority_correct"] is True
    assert result["deterministic"] is True
    assert result["used_skill_route_discovery"] is False
