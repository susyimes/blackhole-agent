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
from blackhole_agent.proposal_synthesis import build_proposal_evidence_package, review_llm_proposal_response


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
        "agent-codex-workflow-local-validation",
        "benign-agent-harness",
        "current-wake-agent-harness-validation",
        "fastcontext-budget-memory-pressure",
        "omnigent-route-contract",
        "public-agent-trend-validation-harness",
        "security-adjacent-context-pressure",
        "skill-workflow-route-discovery",
    }


def test_proposal_benchmark_suite_summarizes_frozen_harness_cases():
    report = run_proposal_benchmark_suite(CASE_PATHS)

    assert report.passed is True
    assert report.case_count == 8
    assert report.passed_count == 8
    assert report.failed_count == 0
    assert report.accepted_count == 11
    assert report.rejected_count == 7
    assert report.failure_counts == {
        "schema_validity": 0,
        "evidence_ref_constraints": 0,
        "action_lane_classification": 0,
        "validation_gate_metadata": 0,
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
    current = results_by_name["current-wake-agent-harness-validation"]
    assert current.proposal_validation_preflights["p1-local-agent-harness-validation"]["status"] == "ready"
    assert (
        current.proposal_validation_preflights["p3-benchmark-style-regression-suite"]["status"]
        == "blocked_by_safety_boundary"
    )
    assert report.to_dict()["suite_name"] == "proposal-replay-benchmark"


def test_proposal_replay_manifest_validates_fixture_sources_and_cases():
    report = validate_proposal_replay_manifest(MANIFEST_PATH)

    assert report.passed is True
    assert report.case_count == 8
    assert report.fixture_names == [
        "benign-agent-harness",
        "security-adjacent-context-pressure",
        "fastcontext-budget-memory-pressure",
        "omnigent-route-contract",
        "public-agent-trend-validation-harness",
        "current-wake-agent-harness-validation",
        "agent-codex-workflow-local-validation",
        "skill-workflow-route-discovery",
    ]
    assert report.evidence_urls == [
        "https://github.com/ApodexAI/AgentHarness",
        "https://github.com/NotPBShaw/burner-agents",
        "https://github.com/baskduf/FableCodex",
        "https://github.com/dongshuyan/compass-skills",
        "https://github.com/microsoft/fastcontext",
        "https://github.com/omnigent-ai/omnigent",
        "https://github.com/samarailly51-pixel/opencode-harness",
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


def test_proposal_replay_case_rejects_candidate_supplied_evidence_urls():
    case = load_proposal_replay_case(FIXTURE_DIR / "public_agent_trend_validation_harness.json")
    case["raw_response"]["proposals"][0]["evidence_urls"] = ["https://github.com/example/extra"]
    case["expected"] = {
        "status": "accepted",
        "accepted_count": 1,
        "rejected_count": 2,
        "rejected_error_substrings": [
            "evidence_urls must be derived from frozen evidence_refs",
            "uncertainty must record context_budget missing_detail_risk",
        ],
    }

    result = run_proposal_replay_case(case)

    assert result.passed is True
    assert "https://github.com/example/extra" not in {
        url
        for controls in result.proposal_controls.values()
        for url in controls.get("evidence_urls", [])
    }


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


def test_proposal_benchmark_report_classifies_validation_gate_metadata_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "current_wake_agent_harness_validation.json")
    case["expected"]["proposal_validation_preflights"]["p1-local-agent-harness-validation"]["status"] = (
        "validation_gap"
    )

    report = build_proposal_benchmark_report([case])

    assert report.passed is False
    assert report.failure_counts["validation_gate_metadata"] == 1


def test_omnigent_replay_marks_missing_test_coverage_validation_as_gap_not_safety_block():
    case = load_proposal_replay_case(FIXTURE_DIR / "omnigent_route_contract.json")
    case["raw_response"]["proposals"][0]["validation_task"] = (
        "Validate locally that the metadata remains replayable before implementation."
    )
    case["expected"]["proposal_validation_preflights"] = {
        "validation-route-contract": {
            "status": "validation_gap",
            "requires_unit_test_or_coverage": True,
            "has_unit_test_signal": False,
            "has_coverage_signal": False,
            "validation_gaps": ["missing_unit_test_or_coverage_validation"],
            "safety_block": False,
            "blocks_autonomous_apply": False,
        }
    }

    result = run_proposal_replay_case(case)

    assert result.passed is True
    assert result.proposal_controls["validation-route-contract"]["implementation_scope"] == (
        "local_validation_candidate"
    )
    assert result.proposal_validation_preflights["validation-route-contract"]["status"] == "validation_gap"


def test_omnigent_growth_interpretation_review_has_stable_json_contract():
    case = load_proposal_replay_case(FIXTURE_DIR / "omnigent_route_contract.json")
    evidence_package = build_proposal_evidence_package(
        case["digest"],
        max_items=case["options"]["max_items"],
        max_item_text_chars=case["options"]["max_item_text_chars"],
    )

    review = review_llm_proposal_response(
        json.dumps(case["raw_response"]),
        evidence_package,
        mode=case["mode"],
    )
    payload = review.to_dict()

    assert list(payload) == [
        "schema_version",
        "mode",
        "status",
        "reason",
        "input_digest_id",
        "input_hash",
        "output_hash",
        "accepted_count",
        "rejected_count",
        "accepted_candidates",
        "rejected_candidates",
        "interpretation",
        "self_model_reading",
    ]
    assert payload["schema_version"] == 1
    assert payload["mode"] == "hybrid"
    assert payload["status"] == "accepted"
    assert payload["accepted_count"] == 1
    assert payload["rejected_count"] == 1
    assert payload["interpretation"] == {
        "run_interpretation": case["raw_response"]["run_interpretation"],
        "rejected_items": [],
    }
    assert payload["self_model_reading"] == {"status": "unchanged"}

    accepted = payload["accepted_candidates"][0]
    assert list(accepted) == [
        "proposal_id",
        "kind",
        "summary",
        "evidence_refs",
        "evidence_urls",
        "rule_risk_flags",
        "added_risk_flags",
        "validation_task",
        "rationale",
        "uncertainty",
        "self_effect",
        "action_lane",
    ]
    assert accepted["proposal_id"] == "validation-route-contract"
    assert accepted["evidence_refs"] == case["expected"]["accepted_evidence_refs"]["validation-route-contract"]

    selected_items_by_id = {str(item["item_id"]): item for item in evidence_package["items"]}
    assert set(accepted["evidence_refs"]) <= set(selected_items_by_id)
    assert accepted["evidence_urls"] == sorted(
        {
            selected_items_by_id[item_id]["source_url"]
            for item_id in accepted["evidence_refs"]
        }
    )

    missing_detail = evidence_package["context_budget"]["evidence_truncation_uncertainty"]
    assert missing_detail["missing_detail_risk"] is True
    assert "generic" in accepted["uncertainty"].lower()
    assert "specific upstream implementation" in accepted["uncertainty"].lower()

    rejected = payload["rejected_candidates"][0]
    assert rejected["candidate"]["proposal_id"] == "underspecified-growth-route"
    assert "rationale must not be empty" in rejected["errors"]
    assert "uncertainty must not be empty" in rejected["errors"]
