import json
import shutil
from pathlib import Path

from blackhole_agent.proposal_eval import (
    build_proposal_benchmark_report,
    load_proposal_replay_case,
    run_proposal_benchmark_suite,
    run_proposal_replay_case,
    run_proposal_replay_suite,
    validate_proposal_replay_manifest,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "proposal_replay"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"
CASE_PATHS = sorted(path for path in FIXTURE_DIR.glob("*.json") if path.name != "manifest.json")


def test_proposal_replay_suite_accepts_frozen_harness_cases():
    results = run_proposal_replay_suite(CASE_PATHS)

    assert results
    assert all(result.passed for result in results), {
        result.name: result.failures for result in results if not result.passed
    }
    assert {result.name for result in results} == {
        "benign-agent-harness",
        "fastcontext-budget-memory-pressure",
        "security-adjacent-context-pressure",
    }


def test_proposal_benchmark_suite_summarizes_frozen_harness_cases():
    report = run_proposal_benchmark_suite(CASE_PATHS)

    assert report.passed is True
    assert report.case_count == 3
    assert report.passed_count == 3
    assert report.failed_count == 0
    assert report.accepted_count == 3
    assert report.rejected_count == 2
    assert report.failure_counts == {
        "schema_validity": 0,
        "evidence_ref_constraints": 0,
        "action_lane_classification": 0,
        "safety_boundary_handling": 0,
        "other": 0,
    }
    results_by_name = {result.name: result for result in report.case_results}
    assert results_by_name["security-adjacent-context-pressure"].proposal_controls["security-boundary-review"] == {
        "kind": "follow_up_issue",
        "risk_flags": ["privacy-leakage"],
        "implementation_scope": "reviewable_proposal_only",
        "validation_gate": "privacy-leakage-human-review",
    }
    assert results_by_name["fastcontext-budget-memory-pressure"].context_budget_preflight["self_model_truncated"] is True
    assert (
        results_by_name["fastcontext-budget-memory-pressure"]
        .context_budget_preflight["evidence_truncation_uncertainty"]["missing_detail_risk"]
        is True
    )
    assert report.to_dict()["suite_name"] == "proposal-replay-benchmark"


def test_proposal_replay_manifest_validates_fixture_sources_and_cases():
    report = validate_proposal_replay_manifest(MANIFEST_PATH)

    assert report.passed is True
    assert report.case_count == 3
    assert report.fixture_names == [
        "benign-agent-harness",
        "security-adjacent-context-pressure",
        "fastcontext-budget-memory-pressure",
    ]
    assert report.evidence_urls == [
        "https://github.com/ApodexAI/AgentHarness",
        "https://github.com/microsoft/fastcontext",
        "https://github.com/omnigent-ai/omnigent",
        "https://github.com/visa/visa-vulnerability-agentic-harness",
    ]
    assert report.to_dict()["failures"] == []


def test_proposal_replay_manifest_detects_evidence_source_drift(tmp_path):
    manifest = load_proposal_replay_case(MANIFEST_PATH)
    manifest["cases"][0]["evidence_urls"] = ["https://github.com/example/not-in-fixture"]
    for case_path in CASE_PATHS:
        shutil.copy(case_path, tmp_path / case_path.name)
    drifted_manifest = tmp_path / "manifest.json"
    drifted_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_proposal_replay_manifest(drifted_manifest)

    assert report.passed is False
    assert any("outside suite evidence" in failure for failure in report.failures)
    assert any("absent from fixture digest" in failure for failure in report.failures)


def test_proposal_replay_case_rejects_url_refs_even_when_url_is_allowed_evidence():
    case = load_proposal_replay_case(FIXTURE_DIR / "benign_agent_harness.json")
    case["raw_response"]["proposals"][0]["evidence_refs"] = ["https://github.com/ApodexAI/AgentHarness"]
    case["expected"] = {
        "status": "rejected",
        "accepted_count": 0,
        "rejected_count": 1,
        "rejected_error_substrings": [
            "evidence_refs contain unknown item ids: https://github.com/ApodexAI/AgentHarness"
        ],
    }

    result = run_proposal_replay_case(case)

    assert result.passed is True
    assert result.accepted_count == 0


def test_proposal_benchmark_report_classifies_schema_and_evidence_ref_drift():
    schema_case = load_proposal_replay_case(FIXTURE_DIR / "benign_agent_harness.json")
    schema_case["raw_response"]["schema_version"] = 2
    schema_case["expected"] = {"status": "accepted", "accepted_count": 1}
    evidence_case = load_proposal_replay_case(FIXTURE_DIR / "benign_agent_harness.json")
    evidence_case["raw_response"]["proposals"][0]["evidence_refs"] = [
        "https://github.com/ApodexAI/AgentHarness"
    ]
    evidence_case["expected"] = {"status": "accepted", "accepted_count": 1}

    report = build_proposal_benchmark_report([schema_case, evidence_case])

    assert report.passed is False
    assert report.failed_count == 2
    assert report.failure_counts["schema_validity"] == 2
    assert report.failure_counts["evidence_ref_constraints"] == 1


def test_proposal_replay_case_detects_control_classification_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "security_adjacent_context_pressure.json")
    case["expected"]["proposal_controls"]["security-boundary-review"]["implementation_scope"] = (
        "local_validation_candidate"
    )

    result = run_proposal_replay_case(case)

    assert result.passed is False
    assert any("expected proposal_controls" in failure for failure in result.failures)


def test_proposal_benchmark_report_classifies_action_lane_and_safety_boundary_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "security_adjacent_context_pressure.json")
    case["expected"]["proposal_controls"]["security-boundary-review"] = {
        "kind": "test",
        "risk_flags": [],
        "implementation_scope": "local_validation_candidate",
        "validation_gate": "focused-evidence-review",
    }

    report = build_proposal_benchmark_report([case])

    assert report.passed is False
    assert report.failure_counts["action_lane_classification"] == 1
    assert report.failure_counts["safety_boundary_handling"] == 1
