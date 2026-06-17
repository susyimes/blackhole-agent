import json
from pathlib import Path

from blackhole_agent.harness_eval import build_harness_comparison_report, evaluate_harness_behavior, run_local_harness_eval


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness_comparison"
LOCAL_EVAL_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "local_harness_eval"
HARNESS_ADAPTER_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "harness_adapter"


def test_harness_comparison_report_omits_private_bodies_by_default():
    report = build_harness_comparison_report(
        sorted(FIXTURE_DIR.glob("*.json")),
        suite_name="fixture-harness-comparison",
    )

    payload = report.to_dict()
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["suite_name"] == "fixture-harness-comparison"
    assert payload["run_count"] == 3
    assert payload["privacy"]["body_fields_exported"] is False
    assert payload["privacy"]["privacy_review_gate"] == "privacy-leakage-human-review"
    assert "PRIVATE_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_TOKEN_BODY_DO_NOT_HASH_OR_EXPORT" not in serialized
    assert "PRIVATE_CHAT_BODY_DO_NOT_HASH_OR_EXPORT" not in serialized

    summaries = {summary["run_id"]: summary for summary in payload["summaries"]}
    assert summaries["fixture-codex-1"]["task_hash"].startswith("sha256:")
    assert summaries["fixture-codex-1"]["output_hash"].startswith("sha256:")
    assert summaries["fixture-codex-1"]["failure_mode"] == "none"
    assert summaries["fixture-codex-1"]["validation_gate"] == "local-harness-summary"
    assert summaries["fixture-codex-1"]["gate_outcome"] == "passed"
    assert summaries["fixture-other-1"]["failure_mode"] == "timeout"
    assert summaries["fixture-other-1"]["tool_calls"] == 1
    assert summaries["fixture-other-1"]["total_tokens"] == 1020
    assert summaries["fixture-private-1"]["task_hash"] is None
    assert summaries["fixture-private-1"]["output_hash"] is None
    assert summaries["fixture-private-1"]["failure_mode"] == "privacy_review_required"
    assert summaries["fixture-private-1"]["validation_gate"] == "privacy-leakage-human-review"
    assert summaries["fixture-private-1"]["gate_outcome"] == "review_required"


def test_harness_comparison_report_aggregates_quality_cost_elapsed_and_failures():
    report = build_harness_comparison_report(sorted(FIXTURE_DIR.glob("*.json")))
    aggregates = {entry["variant"]: entry for entry in report.to_dict()["aggregate_by_variant"]}

    assert aggregates["codex-gpt"] == {
        "harness": "codex",
        "variant": "codex-gpt",
        "run_count": 1,
        "success_count": 1,
        "failure_modes": [],
        "avg_quality_score": 0.9,
        "avg_cost_usd": 0.12,
        "avg_elapsed_seconds": 18.5,
        "avg_tool_calls": 3.0,
        "avg_total_tokens": 1500.0,
    }
    assert aggregates["other-fast"]["success_count"] == 0
    assert aggregates["other-fast"]["failure_modes"] == ["timeout"]
    assert aggregates["other-fast"]["avg_cost_usd"] == 0.04
    assert aggregates["codex-private-review"]["success_count"] == 0
    assert aggregates["codex-private-review"]["failure_modes"] == ["privacy_review_required"]


def test_local_harness_eval_runs_pass_and_fail_fixtures_without_exporting_inputs():
    report = run_local_harness_eval(
        sorted(LOCAL_EVAL_FIXTURE_DIR.glob("*.json")),
        suite_name="fixture-local-harness-eval",
    )

    payload = report.to_dict()
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["suite_name"] == "fixture-local-harness-eval"
    assert payload["fixture_count"] == 5
    assert payload["pass_count"] == 4
    assert payload["fail_count"] == 1
    assert payload["privacy"]["fixture_inputs_exported"] is False
    assert payload["privacy"]["supported_behaviors"] == [
        "agent_workflow_route",
        "harness_run_summary",
        "mock_llm_workflow_route",
        "proposal_interpretation",
    ]
    assert "PRIVATE_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_FAIL_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_FAIL_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized

    results = {result["name"]: result for result in payload["results"]}
    assert results["agent-workflow-route-success"]["passed"] is True
    assert results["agent-workflow-route-recoverable-failure"]["passed"] is True
    assert results["mock-llm-workflow-route-provider-disabled"]["passed"] is True
    assert results["pass-harness-summary"]["passed"] is True
    assert results["pass-harness-summary"]["failure_mode"] == "none"
    assert results["pass-harness-summary"]["input_hash"].startswith("sha256:")
    assert results["fail-harness-summary"]["passed"] is False
    assert results["fail-harness-summary"]["failure_mode"] == "assertion_failed"

    failing_assertions = results["fail-harness-summary"]["assertions"]
    assert failing_assertions[0]["passed"] is True
    assert failing_assertions[1] == {
        "path": "failure_mode",
        "expected": "none",
        "actual": "nonzero_exit",
        "passed": False,
        "failure_mode": "equals_mismatch",
    }


def test_agent_workflow_route_fixture_records_state_validation_and_recovery():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_recoverable_failure.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )

    assert output["route_status"] == "failed_recoverable"
    assert output["failure_mode"] == "nonzero_exit"
    assert output["runner"] == {
        "invoked": True,
        "returncode": 7,
        "timed_out": False,
    }
    assert output["validation"]["gate"] == "focused-evidence-review"
    assert output["validation"]["gate_outcome"] == "failed"
    assert output["rollback"] == {
        "available": True,
        "ref_recorded": True,
        "artifact_recorded": True,
        "recovery_mode": "explicit_operator_reset",
    }
    assert [transition["state"] for transition in output["state_transitions"]] == [
        "planned",
        "runner_invoked",
        "runner_completed",
        "validation_recorded",
        "rollback_checked",
        "completed",
    ]
    assert output["state_transitions"][-1] == {"state": "completed", "outcome": "failed"}


def test_mock_llm_workflow_route_exercises_provider_disabled_path_without_external_calls():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_llm_workflow_route_provider_disabled.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )

    assert output["route_status"] == "passed"
    assert output["provider"] == {
        "name": "external-chat-provider",
        "enabled": False,
        "disabled_handled": True,
        "external_calls_attempted": False,
    }
    assert output["mock_llm"]["enabled"] is True
    assert output["mock_llm"]["call_count"] == 2
    assert output["mock_llm"]["usage"] == {
        "input_tokens": 20,
        "output_tokens": 13,
        "total_tokens": 33,
        "tool_calls": 1,
    }
    assert output["workflow"]["all_expectations_passed"] is True
    assert output["workflow"]["response_hashes"][0].startswith("sha256:")
    assert output["failure_mode"] == "none"


def test_mock_llm_workflow_route_fails_instead_of_calling_external_provider():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_llm_workflow_route_provider_disabled.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    raw_input = dict(fixture["input"])
    raw_input["provider"] = {"name": "external-chat-provider", "enabled": True}
    raw_input["mock_llm"] = {"enabled": False, "responses": []}

    output = evaluate_harness_behavior("mock_llm_workflow_route", raw_input, source_path=fixture_path)

    assert output["route_status"] == "failed"
    assert output["provider"]["external_calls_attempted"] is True
    assert output["mock_llm"]["call_count"] == 0
    assert output["failure_mode"] == "external_provider_required"


def test_local_harness_adapter_runs_proposal_interpretation_fixtures_as_strict_json():
    report = run_local_harness_eval(
        sorted(HARNESS_ADAPTER_FIXTURE_DIR.glob("*.json")),
        suite_name="fixture-harness-adapter",
    )

    payload = report.to_dict()
    serialized = json.dumps(payload, sort_keys=True)
    reparsed = json.loads(serialized)

    assert reparsed == payload
    assert payload["suite_name"] == "fixture-harness-adapter"
    assert payload["fixture_count"] == 7
    assert payload["pass_count"] == 7
    assert payload["fail_count"] == 0
    assert payload["privacy"]["fixture_inputs_exported"] is False
    assert "fixture-agent-harness-adapter" not in serialized
    assert "https://github.com/ApodexAI/AgentHarness" not in serialized

    results = {result["name"]: result for result in payload["results"]}
    agent_codex = results["proposal-interpretation-agent-codex-workflow-validation"]
    accepted = results["proposal-interpretation-accepts-item-refs"]
    malformed_json = results["proposal-interpretation-rejects-malformed-json"]
    rejected = results["proposal-interpretation-rejects-url-refs"]
    truncated = results["proposal-interpretation-rejects-truncated-refs"]
    boundary = results["proposal-interpretation-policy-boundary"]
    max_proposals = results["proposal-interpretation-rejects-too-many-proposals"]

    assert agent_codex["passed"] is True
    assert accepted["passed"] is True
    assert malformed_json["passed"] is True
    assert rejected["passed"] is True
    assert truncated["passed"] is True
    assert boundary["passed"] is True
    assert max_proposals["passed"] is True
    assert all(assertion["passed"] for assertion in agent_codex["assertions"])
    assert all(assertion["passed"] for assertion in accepted["assertions"])
    assert all(assertion["passed"] for assertion in malformed_json["assertions"])
    assert all(assertion["passed"] for assertion in rejected["assertions"])
    assert all(assertion["passed"] for assertion in truncated["assertions"])
    assert all(assertion["passed"] for assertion in boundary["assertions"])
    assert all(assertion["passed"] for assertion in max_proposals["assertions"])


def test_proposal_interpretation_adapter_limits_evidence_refs_to_supplied_item_ids():
    from blackhole_agent.harness_eval import evaluate_harness_behavior, load_json_object

    fixture_path = HARNESS_ADAPTER_FIXTURE_DIR / "proposal_interpretation_accepts_item_refs.json"
    fixture = load_json_object(fixture_path)

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )

    assert list(output) == [
        "schema_version",
        "behavior",
        "name",
        "passed",
        "failure_mode",
        "review_status",
        "review_reason",
        "accepted_count",
        "rejected_count",
        "proposal_policy",
        "selected_item_ids",
        "truncated_item_ids",
        "evidence_ref_policy",
        "accepted_candidates",
        "evidence_ref_violations",
        "proposal_controls",
        "proposal_validation_preflights",
        "rejected_errors",
        "failures",
    ]
    assert output["schema_version"] == 1
    assert output["behavior"] == "proposal_interpretation"
    assert output["passed"] is True
    assert output["evidence_ref_violations"] == []
    supplied_item_ids = set(output["evidence_ref_policy"]["supplied_item_ids"])
    assert supplied_item_ids == {"agent-harness", "opencode-harness"}
    for candidate in output["accepted_candidates"]:
        assert set(candidate["evidence_refs"]) <= supplied_item_ids
