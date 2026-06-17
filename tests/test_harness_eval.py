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
    assert payload["fixture_count"] == 9
    assert payload["pass_count"] == 8
    assert payload["fail_count"] == 1
    assert payload["privacy"]["fixture_inputs_exported"] is False
    assert payload["privacy"]["supported_behaviors"] == [
        "agent_workflow_route",
        "harness_run_summary",
        "mock_llm_workflow_route",
        "provider_runtime_preflight",
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
    assert results["mock-llm-multimodal-missing-image-input"]["passed"] is True
    assert results["mock-llm-multimodal-text-encoded-blocks"]["passed"] is True
    assert results["mock-llm-session-file-tool-route"]["passed"] is True
    assert results["provider-runtime-preflight-claude-sandbox-override"]["passed"] is True
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


def test_mock_llm_workflow_route_hard_fails_missing_model_image_input_before_execution():
    raw_input = {
        "task_id": "fixture-mock-llm-multimodal-missing-image-input",
        "provider": {
            "name": "gateway-provider",
            "enabled": False,
            "model": "vision-model",
            "model_input": ["text"],
        },
        "mock_llm": {
            "enabled": True,
            "responses": [{"content": "should not execute"}],
        },
        "workflow": {
            "steps": [
                {
                    "id": "describe-image",
                    "prompt": [
                        {"type": "input_text", "text": "Describe this image."},
                        {"type": "input_image", "image_url": "data:image/png;base64,ZmFrZQ=="},
                    ],
                    "expect_contains": "should not execute",
                }
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_multimodal_missing_image_input_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "missing_model_image_input"
    assert output["mock_llm"]["call_count"] == 0
    assert output["workflow"]["steps_executed"] == 0
    assert output["multimodal_preflight"]["ok"] is False
    assert output["multimodal_preflight"]["image_block_count"] == 1
    assert output["multimodal_preflight"]["model_image_input_declared"] is False
    assert output["multimodal_preflight"]["prompt_bodies_exported"] is False
    assert "ZmFrZQ==" not in serialized


def test_mock_llm_workflow_route_hard_fails_text_encoded_multimodal_blocks_before_execution():
    raw_input = {
        "task_id": "fixture-mock-llm-multimodal-text-encoded-blocks",
        "provider": {
            "name": "gateway-provider",
            "enabled": False,
            "model": "vision-model",
            "model_input": ["text", "image"],
        },
        "mock_llm": {
            "enabled": True,
            "responses": [{"content": "should not execute"}],
        },
        "workflow": {
            "steps": [
                {
                    "id": "describe-image",
                    "prompt": (
                        '[{"type":"input_text","text":"Describe this image."},'
                        '{"type":"input_image","image_url":"data:image/png;base64,ZmFrZQ=="}]'
                    ),
                    "expect_contains": "should not execute",
                }
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_multimodal_text_encoded_blocks_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "text_encoded_multimodal_blocks"
    assert output["mock_llm"]["call_count"] == 0
    assert output["workflow"]["steps_executed"] == 0
    assert output["multimodal_preflight"]["ok"] is False
    assert output["multimodal_preflight"]["text_encoded_multimodal_block_count"] == 1
    assert output["multimodal_preflight"]["model_image_input_declared"] is True
    assert output["multimodal_preflight"]["prompt_bodies_exported"] is False
    assert "ZmFrZQ==" not in serialized


def test_mock_llm_workflow_route_uses_deterministic_keyed_response_queues():
    raw_input = {
        "task_id": "fixture-mock-llm-keyed-queues",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "mock-parent": [
                    {"content": "parent first response"},
                    {"content": "parent second response"},
                ],
                "mock-reviewer": [
                    {"content": "reviewer first response"},
                    {"content": "reviewer second response"},
                ],
            },
        },
        "workflow": {
            "steps": [
                {"id": "reviewer-1", "model": "mock-reviewer", "expect_contains": "reviewer first"},
                {"id": "parent-1", "model": "mock-parent", "expect_contains": "parent first"},
                {"id": "reviewer-2", "model": "mock-reviewer", "expect_contains": "reviewer second"},
                {"id": "parent-2", "model": "mock-parent", "expect_contains": "parent second"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_keyed_queues_inline.json",
    )

    assert output["route_status"] == "passed"
    assert output["mock_llm"]["call_count"] == 4
    assert output["mock_llm"]["response_count"] == 4
    assert output["mock_llm"]["queue_keys"] == ["mock-parent", "mock-reviewer"]
    assert output["workflow"]["response_keys"] == [
        "mock-reviewer",
        "mock-parent",
        "mock-reviewer",
        "mock-parent",
    ]
    assert output["workflow"]["fallback_count"] == 0
    assert output["failure_mode"] == "none"


def test_mock_llm_workflow_route_falls_back_to_default_queue_for_missing_key():
    raw_input = {
        "task_id": "fixture-mock-llm-default-fallback",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "default": [{"content": "default fallback response"}],
            },
        },
        "workflow": {
            "steps": [
                {"id": "unknown-model", "model": "mock-missing", "expect_contains": "fallback"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_default_fallback_inline.json",
    )

    assert output["route_status"] == "passed"
    assert output["mock_llm"]["call_count"] == 1
    assert output["mock_llm"]["queue_keys"] == ["default"]
    assert output["workflow"]["response_keys"] == ["default"]
    assert output["workflow"]["fallback_count"] == 1
    assert output["failure_mode"] == "none"


def test_mock_llm_workflow_route_reports_exhausted_when_key_and_default_are_missing():
    raw_input = {
        "task_id": "fixture-mock-llm-missing-key",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "mock-parent": [{"content": "parent response"}],
            },
        },
        "workflow": {
            "steps": [
                {"id": "unknown-model", "model": "mock-missing", "expect_contains": "unused"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_missing_key_inline.json",
    )

    assert output["route_status"] == "failed"
    assert output["mock_llm"]["call_count"] == 0
    assert output["mock_llm"]["exhausted"] is True
    assert output["workflow"]["response_keys"] == []
    assert output["failure_mode"] == "mock_llm_exhausted"


def test_provider_runtime_preflight_degrades_when_sandbox_override_reaches_harness():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_claude_sandbox_override.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "degraded"
    assert output["failure_mode"] == "none"
    assert output["sandbox"]["incompatible_with_provider_runtime"] is True
    assert output["runner_env"] == {
        "override_requested_in_parent": True,
        "override_propagated_to_harness": True,
        "allowlist_count": 2,
        "passthrough_count": 0,
        "env_values_recorded": False,
    }
    assert output["runtime"]["runner_invoked"] is True
    assert output["runtime"]["supervisor_unwrapped"] is True
    assert output["runtime"]["native_file_shell_tools_disabled"] is True
    assert output["runtime"]["cli_path_recorded"] is False
    assert output["preflight"]["ok"] is True
    assert output["preflight"]["blocked_before_launch"] is False
    assert "CLAUDE_SDK_NO_SANDBOX reached the provider harness" in output["preflight"]["diagnostics"][0]
    assert "~/.local/bin/claude" not in serialized


def test_provider_runtime_preflight_blocks_before_launch_when_override_is_stripped():
    raw_input = {
        "task_id": "fixture-provider-runtime-preflight-stripped-override",
        "provider": {
            "name": "claude-sdk",
            "harness": "claude-sdk",
            "sandbox_override_flag": "CLAUDE_SDK_NO_SANDBOX",
            "degrade_on_incompatible_sandbox": False,
        },
        "sandbox": {"active": True, "type": "macos-sandbox-exec"},
        "runtime": {
            "platform": "darwin",
            "cli_path": "~/.local/bin/claude",
            "install_tree_readable": False,
        },
        "runner_env": {
            "parent_env_keys": ["CLAUDE_SDK_NO_SANDBOX"],
            "allowlist": ["PATH"],
            "passthrough": [],
        },
    }

    output = evaluate_harness_behavior(
        "provider_runtime_preflight",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_stripped_override_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "sandbox_runtime_preflight_failed"
    assert output["runner_env"]["override_requested_in_parent"] is True
    assert output["runner_env"]["override_propagated_to_harness"] is False
    assert output["runtime"]["runner_invoked"] is False
    assert output["preflight"]["ok"] is False
    assert output["preflight"]["blocked_before_launch"] is True
    assert output["preflight"]["diagnostics"] == [
        "CLAUDE_SDK_NO_SANDBOX was set before runner launch but did not reach the provider harness",
        "provider runtime sandbox is incompatible and no degraded startup path was available",
        "add CLAUDE_SDK_NO_SANDBOX to the runner environment allowlist or enable provider auto-degrade",
    ]
    assert "~/.local/bin/claude" not in serialized


def test_provider_runtime_preflight_skips_browser_configure_without_masking_url_safety():
    raw_input = {
        "task_id": "fixture-provider-runtime-preflight-missing-playwright-local-url",
        "provider": {
            "name": "browser-provider",
            "harness": "playwright-e2e",
            "base_url": "http://127.0.0.1:3000",
        },
        "browser_tooling": {
            "configure_checks_required": True,
            "playwright_available": False,
        },
        "url_safety": {
            "refuse_local_targets": True,
        },
    }

    output = evaluate_harness_behavior(
        "provider_runtime_preflight",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_missing_playwright_local_url_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "url_safety_preflight_failed"
    assert output["runtime"]["runner_invoked"] is False
    assert output["browser_tooling"] == {
        "playwright_available": False,
        "configure_checks_required": True,
        "configure_checks_skipped": True,
        "configure_status": "skipped_missing_optional_dependency",
        "diagnostics": ["Playwright is unavailable; browser configure checks were skipped"],
        "optional_dependency_values_recorded": False,
    }
    assert output["url_safety"] == {
        "checked": True,
        "ok": False,
        "base_url_present": True,
        "base_url_recorded": False,
        "refuse_local_targets": True,
        "diagnostics": ["base URL must not target localhost, loopback, private, or link-local networks"],
    }
    assert "127.0.0.1" not in serialized


def test_provider_runtime_preflight_degrades_for_missing_playwright_when_url_is_safe():
    raw_input = {
        "task_id": "fixture-provider-runtime-preflight-missing-playwright-safe-url",
        "provider": {
            "name": "browser-provider",
            "harness": "playwright-e2e",
            "base_url": "https://example.com/app",
        },
        "browser_tooling": {
            "configure_checks_required": True,
            "playwright_available": False,
        },
        "url_safety": {
            "refuse_local_targets": True,
        },
    }

    output = evaluate_harness_behavior(
        "provider_runtime_preflight",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_missing_playwright_safe_url_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "degraded"
    assert output["failure_mode"] == "none"
    assert output["runtime"]["runner_invoked"] is True
    assert output["preflight"]["ok"] is True
    assert output["preflight"]["degraded"] is True
    assert output["browser_tooling"]["configure_checks_skipped"] is True
    assert output["url_safety"]["ok"] is True
    assert output["url_safety"]["base_url_recorded"] is False
    assert "https://example.com/app" not in serialized


def test_mock_llm_workflow_route_covers_session_and_file_tools_without_exporting_bodies():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_llm_session_file_tool_route.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["session"]["id_present"] is True
    assert output["session"]["id_hash"].startswith("sha256:")
    assert output["session"]["previous_id_hash"].startswith("sha256:")
    assert output["session"]["isolation_passed"] is True
    assert output["file_tools"]["operation_count"] == 2
    assert output["file_tools"]["mocked_count"] == 2
    assert output["file_tools"]["unmocked_external_count"] == 0
    assert output["file_tools"]["all_expectations_passed"] is True
    assert all(operation["path_hash"].startswith("sha256:") for operation in output["file_tools"]["operations"])
    assert all(operation["content_hash"].startswith("sha256:") for operation in output["file_tools"]["operations"])
    assert "session-current-fixture" not in serialized
    assert "session-previous-fixture" not in serialized
    assert "fixtures/private-note.md" not in serialized
    assert "mock attachment summary" not in serialized
    assert output["failure_mode"] == "none"


def test_mock_llm_workflow_route_fails_when_session_reuses_previous_id():
    raw_input = {
        "task_id": "fixture-mock-llm-session-reuse",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "session": {
            "id": "same-session-fixture",
            "previous_id": "same-session-fixture",
            "isolation_required": True,
        },
        "mock_llm": {
            "enabled": True,
            "responses": [{"content": "mock response"}],
        },
        "workflow": {
            "steps": [
                {"id": "open-session", "expect_contains": "mock response"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_session_reuse_inline.json",
    )

    assert output["route_status"] == "failed"
    assert output["session"]["reused_previous_session"] is True
    assert output["session"]["isolation_passed"] is False
    assert output["failure_mode"] == "session_isolation_failed"


def test_mock_llm_workflow_route_fails_when_file_tool_is_not_mocked():
    raw_input = {
        "task_id": "fixture-mock-llm-unmocked-file-tool",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "file_tools": {
            "enabled": True,
            "operations": [
                {
                    "name": "download_file",
                    "path": "fixtures/real-download.bin",
                    "mocked": False,
                }
            ],
        },
        "mock_llm": {
            "enabled": True,
            "responses": [{"content": "mock response"}],
        },
        "workflow": {
            "steps": [
                {"id": "download-file", "expect_contains": "mock response"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_unmocked_file_tool_inline.json",
    )

    assert output["route_status"] == "failed"
    assert output["file_tools"]["unmocked_external_count"] == 1
    assert output["failure_mode"] == "file_tool_mock_failed"


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
        "safety_boundary",
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
    assert output["safety_boundary"] == {
        "review_only_risk_flags": ["offensive-behavior", "privacy-leakage"],
        "review_only_proposal_ids": [],
        "review_only_count": 0,
        "unsafe_drift_proposal_ids": [],
        "unsafe_drift_count": 0,
        "offensive_behavior_local_execution": False,
    }
    assert output["evidence_ref_violations"] == []
    supplied_item_ids = set(output["evidence_ref_policy"]["supplied_item_ids"])
    assert supplied_item_ids == {"agent-harness", "opencode-harness"}
    for candidate in output["accepted_candidates"]:
        assert set(candidate["evidence_refs"]) <= supplied_item_ids
