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
    assert payload["fixture_count"] == 22
    assert payload["pass_count"] == 21
    assert payload["fail_count"] == 1
    assert payload["privacy"]["fixture_inputs_exported"] is False
    assert payload["privacy"]["supported_behaviors"] == [
        "agent_workflow_route",
        "harness_run_summary",
        "mock_e2e_runner_tier",
        "mock_llm_workflow_route",
        "native_tool_call_policy",
        "push_delivery_path",
        "provider_runtime_preflight",
        "proposal_interpretation",
        "workspace_changes_panel",
    ]
    assert "PRIVATE_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_FAIL_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_FAIL_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized

    results = {result["name"]: result for result in payload["results"]}
    assert results["agent-workflow-route-success"]["passed"] is True
    assert results["agent-workflow-route-recoverable-failure"]["passed"] is True
    assert results["agent-workflow-route-lifecycle-trace"]["passed"] is True
    assert results["mock-e2e-runner-tier-host-native-misc"]["passed"] is True
    assert results["mock-e2e-runner-tier-compaction-known-failure-repoint"]["passed"] is True
    assert results["mock-llm-workflow-route-provider-disabled"]["passed"] is True
    assert results["mock-llm-multimodal-missing-image-input"]["passed"] is True
    assert results["mock-llm-multimodal-text-encoded-blocks"]["passed"] is True
    assert results["mock-llm-interrupt-rebuild-replay"]["passed"] is True
    assert results["mock-llm-named-subagent-policy-route"]["passed"] is True
    assert results["mock-llm-session-file-tool-route"]["passed"] is True
    assert results["native-tool-call-policy-fail-closed"]["passed"] is True
    assert results["native-tool-call-policy-slow-ask-timeout"]["passed"] is True
    assert results["push-delivery-path-mock-success"]["passed"] is True
    assert results["provider-runtime-preflight-claude-sandbox-override"]["passed"] is True
    assert results["provider-runtime-preflight-claude-long-status-prompt-scan"]["passed"] is True
    assert results["provider-runtime-preflight-native-claude-iterm2-tmux-timeout-risk"]["passed"] is True
    assert results["provider-runtime-preflight-openai-agents-mock-auth"]["passed"] is True
    assert results["provider-runtime-preflight-openai-agents-no-worker-env-skip"]["passed"] is True
    assert results["workspace-changes-panel-non-git-native-external"]["passed"] is True
    assert results["pass-harness-summary"]["passed"] is True
    assert results["pass-harness-summary"]["failure_mode"] == "none"
    assert results["pass-harness-summary"]["input_hash"].startswith("sha256:")
    assert results["fail-harness-summary"]["passed"] is False
    assert results["fail-harness-summary"]["failure_mode"] == "assertion_failed"
    assert "PRIVATE_TOOL_ARGUMENT_DO_NOT_EXPORT" not in serialized
    assert "native-session-fixture-do-not-export" not in serialized
    assert "PRIVATE_NAMED_SUB_AGENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_AGENT_BEFORE_INTERRUPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CONVERSATION_BEFORE_INTERRUPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT" not in serialized
    assert "native-ask-session-fixture-do-not-export" not in serialized
    assert "PRIVATE_ASK_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NATIVE_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NATIVE_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXTERNAL_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXTERNAL_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REST_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REST_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HOST_NATIVE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_BOOT_PROBE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "Pattern 'sleeping' not found" not in serialized
    assert "OPENAI_API_KEY" not in serialized

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


def test_mock_e2e_runner_tier_fixture_exercises_host_native_and_misc_without_external_calls():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_e2e_runner_tier_host_native_misc.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["provider"] == {
        "name": "external-agent-provider",
        "enabled": False,
        "mock_only": True,
        "credentials_required": False,
        "network_required": False,
        "external_calls_attempted": False,
    }
    assert output["runner_tiers"]["host_native_count"] == 1
    assert output["runner_tiers"]["miscellaneous_count"] == 1
    assert output["runner_tiers"]["tool_boundaries_mocked"] is True
    assert output["privacy"] == {
        "raw_commands_exported": False,
        "raw_paths_exported": False,
        "raw_contents_exported": False,
        "hashes_only": True,
    }
    assert "PRIVATE_HOST_NATIVE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "fixtures/private-input.md" not in serialized
    assert "fixtures/private-output.md" not in serialized
    assert "miscellaneous read result stayed inside local fixture" not in serialized


def test_mock_e2e_runner_tier_routes_known_failure_repoints_without_raw_failure_text():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_e2e_runner_tier_compaction_known_failure_repoint.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["known_failure_route"] == {
        "configured": True,
        "passed": True,
        "mode": "skip",
        "observed_signature_matched": True,
        "stale_issue_retained": False,
        "issue_repointed": True,
        "cluster_repointed": True,
        "test_logic_changed": False,
        "raw_failure_text_exported": False,
    }
    assert output["failure_mode"] == "none"
    assert "Pattern 'sleeping' not found" not in serialized
    assert "PRIVATE_BOOT_PROBE_COMMAND_DO_NOT_EXPORT" not in serialized


def test_push_delivery_path_fixture_records_mocked_handoff_without_raw_remote_or_command():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "push_delivery_path_mock_success.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["delivery"] == {
        "push_requested": True,
        "remote_configured": True,
        "branch_configured": True,
        "mock_only": True,
        "credentials_required": False,
        "network_required": False,
        "external_calls_attempted": False,
    }
    assert output["runner"]["invoked"] is True
    assert output["runner"]["mocked"] is True
    assert output["runner"]["returncode"] == 0
    assert output["runner"]["command_shape_matched"] is True
    assert output["activation"] == {
        "activation_recorded": True,
        "restart_request_recorded": True,
        "activation_head_matches": True,
    }
    assert output["privacy"] == {
        "raw_commands_exported": False,
        "raw_remote_exported": False,
        "raw_branch_exported": False,
        "hashes_only": True,
    }
    assert "git push origin main" not in serialized
    assert '"origin"' not in serialized
    assert '"main"' not in serialized
    assert output["failure_mode"] == "none"


def test_push_delivery_path_fails_when_mock_boundary_would_call_remote():
    output = evaluate_harness_behavior(
        "push_delivery_path",
        {
            "task_id": "fixture-push-delivery-path-external-call",
            "promotion": {"promoted": True, "target_head": "fixture-target-head"},
            "delivery": {
                "push_requested": True,
                "remote_name": "origin",
                "branch": "main",
                "mock_only": False,
                "credentials_required": False,
                "network_required": False,
            },
            "runner": {
                "invoked": True,
                "mocked": False,
                "returncode": 0,
                "command": ["git", "push", "origin", "main"],
            },
            "activation": {
                "activation_recorded": True,
                "restart_request_recorded": True,
                "activated_head": "fixture-target-head",
            },
            "rollback": {
                "created": True,
                "ref": "refs/rollback/fixture-push-delivery-path",
                "artifact_path": "artifacts/rollback/fixture-push-delivery-path.txt",
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "push_delivery_path_external_call_inline.json",
    )

    assert output["route_status"] == "failed"
    assert output["delivery"]["external_calls_attempted"] is True
    assert output["failure_mode"] == "external_push_attempted"


def test_provider_runtime_preflight_allows_openai_agents_mock_auth_without_key_value_export():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_openai_agents_mock_auth.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "degraded"
    assert output["failure_mode"] == "none"
    assert output["runner_env"]["required_env_ready"] is False
    assert output["provider_auth"] == {
        "openai_agents_key_relevant": True,
        "auth_env_key_configured": True,
        "auth_env_key_present_in_parent": False,
        "auth_env_key_propagated_to_harness": False,
        "auth_env_key_propagated_to_worker": False,
        "mock_auth_placeholder_used": True,
        "real_key_required": False,
        "key_value_recorded": False,
    }
    assert output["runtime"]["runner_invoked"] is True
    assert output["preflight"]["degraded"] is True
    assert "OPENAI_API_KEY" not in serialized


def test_provider_runtime_preflight_skips_worker_env_inherit_when_worker_tool_missing():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_openai_agents_no_worker_env_skip.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["runner_env"]["required_env_ready"] is True
    assert output["runner_env"]["worker_env_inherit_skipped"] is True
    assert output["provider"]["worker_tool_available"] is False
    assert output["provider_auth"]["auth_env_key_propagated_to_worker"] is False
    assert output["preflight"]["blocked_before_launch"] is False
    assert "skipped worker env inheritance check because the harness declares no worker tool" in output["preflight"][
        "diagnostics"
    ]
    assert "OPENAI_API_KEY" not in serialized


def test_mock_e2e_runner_tier_fails_when_required_tier_is_missing():
    output = evaluate_harness_behavior(
        "mock_e2e_runner_tier",
        {
            "task_id": "fixture-mock-e2e-missing-host-native",
            "mock_only": True,
            "provider": {"enabled": False},
            "runner_tiers": [
                {
                    "name": "miscellaneous",
                    "lane": "miscellaneous",
                    "mocked": True,
                    "steps": [{"id": "misc", "observed": "miscellaneous mocked journey"}],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_e2e_missing_host_native_inline.json",
    )

    assert output["route_status"] == "failed"
    assert output["runner_tiers"]["host_native_count"] == 0
    assert output["runner_tiers"]["miscellaneous_count"] == 1
    assert output["failure_mode"] == "host_native_tier_missing"


def test_agent_workflow_route_fails_when_lifecycle_trace_misses_required_phase():
    raw_input = {
        "task_id": "fixture-route-missing-lifecycle-phase",
        "plan": {"steps": [{"id": "inspect"}, {"id": "run"}, {"id": "verify"}]},
        "runner": {"invoked": True, "returncode": 0, "timed_out": False},
        "lifecycle": {
            "expected_phases": [
                "planned",
                "runner_invoked",
                "runner_completed",
                "validation_recorded",
                "rollback_checked",
                "completed",
            ],
            "observed_phases": [
                "planned",
                "runner_invoked",
                "runner_completed",
                "rollback_checked",
                "completed",
            ],
        },
        "validation": {"gate": "focused-evidence-review", "checks": [{"name": "pytest", "returncode": 0}]},
        "rollback": {
            "created": True,
            "ref": "refs/rollback/fixture-route-missing-lifecycle-phase",
            "artifact_path": "artifacts/rollback/fixture-route-missing-lifecycle-phase.txt",
        },
    }

    output = evaluate_harness_behavior(
        "agent_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_missing_lifecycle_phase_inline.json",
    )

    assert output["route_status"] == "failed_recoverable"
    assert output["failure_mode"] == "lifecycle_incomplete"
    assert output["lifecycle"] == {
        "expected_phases": [
            "planned",
            "runner_invoked",
            "runner_completed",
            "validation_recorded",
            "rollback_checked",
            "completed",
        ],
        "observed_phases": [
            "planned",
            "runner_invoked",
            "runner_completed",
            "rollback_checked",
            "completed",
        ],
        "complete": False,
        "ordered": False,
        "unexpected_phases": [],
        "missing_phases": ["validation_recorded"],
        "passed": False,
        "failure_mode": "missing_lifecycle_phase",
    }
    assert output["validation"]["gate_outcome"] == "passed"
    assert output["rollback"]["recovery_mode"] == "explicit_operator_reset"


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
    assert output["mock_llm"]["remaining_response_count"] == 0
    assert output["mock_llm"]["all_responses_consumed"] is True
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


def test_mock_llm_workflow_route_validates_anthropic_messages_round_trip_without_bodies():
    raw_input = {
        "task_id": "fixture-mock-llm-anthropic-messages",
        "provider": {"name": "anthropic", "harness": "claude-sdk", "enabled": False},
        "mock_llm": {
            "enabled": True,
            "api": "anthropic_messages",
            "response_queues": {
                "claude-3-haiku": [
                    {
                        "content": "PRIVATE_TEXT_BODY_DO_NOT_EXPORT accepted",
                        "usage": {"input_tokens": 8, "output_tokens": 5},
                    },
                    {
                        "content": "tool result accepted",
                        "tool_calls": [{"name": "record_validation", "arguments": "{\"ok\": true}"}],
                        "usage": {"input_tokens": 10, "output_tokens": 7},
                    },
                ]
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "messages-text",
                    "model": "claude-3-haiku",
                    "prompt": "PRIVATE_PROMPT_BODY_DO_NOT_EXPORT",
                    "expect_contains": "accepted",
                },
                {
                    "id": "messages-tool",
                    "model": "claude-3-haiku",
                    "prompt": "PRIVATE_TOOL_PROMPT_BODY_DO_NOT_EXPORT",
                    "expect_contains": "tool result",
                },
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_anthropic_messages_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["workflow"]["response_keys"] == ["claude-3-haiku", "claude-3-haiku"]
    assert output["workflow"]["fallback_count"] == 0
    assert output["mock_llm"]["usage"] == {"input_tokens": 18, "output_tokens": 12, "total_tokens": 30, "tool_calls": 1}
    assert output["mock_llm"]["anthropic_messages"] == {
        "enabled": True,
        "ok": True,
        "endpoint": "/v1/messages",
        "request_count": 2,
        "response_format": "anthropic_sse",
        "model_echoed": True,
        "same_keyed_queue_routing": True,
        "text_event_sequence_count": 1,
        "tool_event_sequence_count": 1,
        "event_types": [
            "message_start",
            "content_block_start",
            "content_block_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
        ],
        "tool_event_types": [
            "message_start",
            "content_block_start",
            "input_json_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
        ],
        "diagnostics": [],
    }
    assert "PRIVATE_TEXT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_TOOL_PROMPT_BODY_DO_NOT_EXPORT" not in serialized


def test_mock_llm_workflow_route_fails_when_anthropic_messages_model_is_not_echoed():
    raw_input = {
        "task_id": "fixture-mock-llm-anthropic-messages-model-mismatch",
        "provider": {"name": "anthropic", "harness": "claude-sdk", "enabled": False},
        "mock_llm": {
            "enabled": True,
            "api": "anthropic_messages",
            "response_queues": {
                "claude-3-haiku": [
                    {
                        "content": "model mismatch response",
                        "response_model": "mock-model",
                    }
                ]
            },
        },
        "workflow": {
            "steps": [
                {"id": "messages-text", "model": "claude-3-haiku", "expect_contains": "mismatch"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_anthropic_messages_model_mismatch_inline.json",
    )

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "anthropic_messages_incompatible"
    assert output["mock_llm"]["anthropic_messages"]["ok"] is False
    assert output["mock_llm"]["anthropic_messages"]["model_echoed"] is False
    assert output["mock_llm"]["anthropic_messages"]["diagnostics"] == [
        "Anthropic Messages mock responses must echo the request model in message_start"
    ]


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
        "required_env_ready": True,
        "missing_parent_env_key_count": 0,
        "missing_harness_env_key_count": 0,
        "os_env_inherit_to_worker": False,
        "worker_env_inherit_skipped": False,
        "env_values_recorded": False,
    }
    assert output["runtime"]["runner_invoked"] is True
    assert output["runtime"]["supervisor_unwrapped"] is True
    assert output["runtime"]["native_file_shell_tools_disabled"] is True
    assert output["runtime"]["cli_path_recorded"] is False
    assert output["runtime"]["native_terminal_timeout_risk"] is False
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


def test_provider_runtime_preflight_blocks_native_claude_iterm2_tmux_timeout_risk():
    raw_input = {
        "task_id": "fixture-provider-runtime-preflight-native-claude-iterm2-tmux-timeout-risk",
        "provider": {
            "name": "claude-code",
            "harness": "claude-code",
        },
        "sandbox": {"active": False, "type": "none"},
        "runtime": {
            "platform": "darwin",
            "cli_path": "~/.local/bin/claude",
            "cli_resolved_in_runner": False,
            "install_tree_readable": True,
            "launch_transport": "tmux",
            "terminal_integration": "com.googlecode.iterm2",
        },
        "runner_env": {
            "parent_env_keys": ["PATH"],
            "allowlist": ["PATH"],
            "passthrough": [],
        },
    }

    output = evaluate_harness_behavior(
        "provider_runtime_preflight",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_native_claude_iterm2_timeout_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "native_terminal_timeout_risk"
    assert output["runtime"]["runner_invoked"] is False
    assert output["runtime"]["cli_resolved_in_runner"] is False
    assert output["runtime"]["launch_transport"] == "tmux"
    assert output["runtime"]["terminal_integration"] == "iterm2"
    assert output["runtime"]["native_terminal_timeout_risk"] is True
    assert output["runtime"]["cli_path_recorded"] is False
    assert output["preflight"]["ok"] is False
    assert output["preflight"]["blocked_before_launch"] is True
    assert output["preflight"]["diagnostics"] == [
        "native Claude CLI is not visible to the tmux-launched provider harness; block before terminal timeout",
        "ensure the runner PATH resolves the native CLI or configure an explicit provider CLI path",
    ]
    assert "~/.local/bin/claude" not in serialized


def test_provider_runtime_preflight_detects_claude_prompt_above_long_status_footer():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_claude_long_status_prompt_scan.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["runtime"]["runner_invoked"] is True
    assert output["prompt_scan"] == {
        "configured": True,
        "provider_prompt_scan_relevant": True,
        "tail_lines": 12,
        "legacy_tail_lines": 5,
        "status_footer_non_empty_lines": 6,
        "prompt_distance_from_bottom": 7,
        "prompt_glyph_present": True,
        "prompt_detected": True,
        "legacy_timeout_risk": True,
        "second_message_send_would_timeout": False,
        "pane_text_exported": False,
        "timeout_seconds": 30,
    }
    assert output["preflight"]["ok"] is True
    assert output["preflight"]["diagnostics"] == [
        "Claude prompt sits beyond the legacy scan tail but inside the configured provider prompt scan window",
    ]
    assert "PRIVATE" not in serialized


def test_provider_runtime_preflight_blocks_when_prompt_scan_window_misses_prompt():
    raw_input = {
        "task_id": "fixture-provider-runtime-preflight-claude-prompt-scan-too-small",
        "provider": {
            "name": "claude-code",
            "harness": "claude-native",
        },
        "sandbox": {"active": False, "type": "none"},
        "runtime": {
            "platform": "darwin",
            "cli_path": "/usr/local/bin/claude",
            "cli_resolved_in_runner": True,
            "install_tree_readable": True,
            "launch_transport": "tmux",
            "terminal_integration": "iTerm2",
        },
        "prompt_scan": {
            "tail_lines": 5,
            "legacy_tail_lines": 5,
            "status_footer_non_empty_lines": 6,
            "prompt_glyph_present": True,
            "timeout_seconds": 30,
        },
    }

    output = evaluate_harness_behavior(
        "provider_runtime_preflight",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_claude_prompt_scan_too_small_inline.json",
    )

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "prompt_scan_timeout_risk"
    assert output["runtime"]["runner_invoked"] is False
    assert output["prompt_scan"]["prompt_detected"] is False
    assert output["prompt_scan"]["second_message_send_would_timeout"] is True
    assert output["preflight"]["diagnostics"] == [
        "provider prompt scan window does not reach the prompt above the rendered status footer",
        "increase provider prompt scan tail lines before sending a second message",
    ]


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
    assert output["mock_llm"]["remaining_response_count"] == 0
    assert output["tool_call_contract"]["declared"] is True
    assert output["tool_call_contract"]["required_tool_call_count"] == 2
    assert output["tool_call_contract"]["observed_tool_call_count"] == 2
    assert output["tool_call_contract"]["matched_required_tool_call_count"] == 2
    assert output["tool_call_contract"]["all_required_tool_calls_observed"] is True
    assert output["tool_call_contract"]["raw_tool_arguments_exported"] is False
    assert all(operation["path_hash"].startswith("sha256:") for operation in output["file_tools"]["operations"])
    assert all(operation["content_hash"].startswith("sha256:") for operation in output["file_tools"]["operations"])
    assert "session-current-fixture" not in serialized
    assert "session-previous-fixture" not in serialized
    assert "fixtures/private-note.md" not in serialized
    assert "mock attachment summary" not in serialized
    assert output["failure_mode"] == "none"


def test_mock_llm_workflow_route_covers_interrupt_rebuild_and_idle_replay_without_exporting_ids():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_llm_interrupt_rebuild_replay.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["interrupt"]["session_rebuilt"] is True
    assert output["interrupt"]["agent_rebuilt"] is True
    assert output["interrupt"]["conversation_rebuilt"] is True
    assert output["interrupt"]["pending_idle_message_count"] == 2
    assert output["interrupt"]["replayed_idle_message_count"] == 2
    assert output["interrupt"]["idle_replay_counts_match"] is True
    assert output["interrupt"]["lost_idle_message_count"] == 0
    assert output["interrupt"]["duplicated_idle_message_count"] == 0
    assert output["interrupt"]["previous_session_hash"].startswith("sha256:")
    assert output["interrupt"]["rebuilt_session_hash"].startswith("sha256:")
    assert all(hash_value.startswith("sha256:") for hash_value in output["interrupt"]["pending_idle_message_hashes"])
    assert all(hash_value.startswith("sha256:") for hash_value in output["interrupt"]["replayed_idle_message_hashes"])
    assert output["interrupt"]["raw_ids_exported"] is False
    assert output["failure_mode"] == "none"
    assert "PRIVATE_REBUILT_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_INTERRUPTED_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_AGENT_BEFORE_INTERRUPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CONVERSATION_BEFORE_INTERRUPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_IDLE_MESSAGE_TWO_DO_NOT_EXPORT" not in serialized


def test_mock_llm_workflow_route_covers_named_subagent_policy_without_exporting_bodies():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_llm_named_subagent_policy_route.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["sub_agents"]["agent_count"] == 1
    assert output["sub_agents"]["all_expected_agents_observed"] is True
    assert output["sub_agents"]["persistence_passed"] is True
    assert output["sub_agents"]["queue_desync_detected"] is False
    agent = output["sub_agents"]["agents"][0]
    assert agent["turn_count"] == 2
    assert agent["unique_session_hash_count"] == 1
    assert agent["expected_queue_mismatches"] == 0
    assert output["native_tool_policy"]["route_status"] == "denied"
    assert output["native_tool_policy"]["permission_decision"] == "deny"
    assert output["native_tool_policy"]["approval_required"] is False
    assert output["native_tool_policy"]["approval_path"] == {
        "expected": False,
        "declared": False,
        "route_status": "not_required",
        "passive": False,
        "tool_executed": False,
        "arguments_exported": False,
    }
    assert output["native_tool_policy"]["fail_closed_applied"] is True
    assert output["native_tool_policy"]["tool_executed"] is False
    assert output["mock_llm"]["remaining_response_count"] == 0
    assert output["tool_call_contract"]["declared"] is True
    assert output["tool_call_contract"]["required_tool_call_count"] == 1
    assert output["tool_call_contract"]["observed_tool_call_count"] == 2
    assert output["tool_call_contract"]["matched_required_tool_call_count"] == 1
    assert output["tool_call_contract"]["all_required_tool_calls_observed"] is True
    assert output["tool_call_contract"]["raw_tool_arguments_exported"] is False
    assert output["failure_mode"] == "none"
    assert "PRIVATE_NAMED_SUB_AGENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_TOOL_ARGUMENT_DO_NOT_EXPORT" not in serialized
    assert "Write" not in serialized


def test_mock_llm_workflow_route_records_review_required_approval_path_without_execution():
    raw_input = {
        "task_id": "fixture-mock-llm-approval-review-required",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "native_tool_policy": {
            "task_id": "fixture-mock-llm-approval-review-required",
            "approval_expected": True,
            "policy_hook": {
                "governed": True,
                "session_id": "PRIVATE_APPROVAL_SESSION_DO_NOT_EXPORT",
                "server_url_configured": True,
                "event_phase": "PreToolUse",
                "failure_mode": "slow_ask_timeout",
            },
            "tool_call": {
                "name": "Write",
                "transport": "native",
                "arguments": {"path": "fixtures/private-output.md"},
            },
        },
        "mock_llm": {
            "enabled": True,
            "responses": [{"content": "approval gate reached", "tool_calls": [{"name": "Write"}]}],
        },
        "workflow": {
            "steps": [
                {"id": "approval-step", "expect_contains": "approval gate"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_approval_review_required_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["native_tool_policy"]["route_status"] == "review_only"
    assert output["native_tool_policy"]["permission_decision"] == "review_required"
    assert output["native_tool_policy"]["approval_required"] is True
    assert output["native_tool_policy"]["approval_path"] == {
        "expected": True,
        "declared": True,
        "route_status": "review_only",
        "passive": True,
        "tool_executed": False,
        "arguments_exported": False,
    }
    assert output["native_tool_policy"]["passive_or_denied"] is True
    assert output["tool_call_contract"]["all_required_tool_calls_observed"] is True
    assert output["failure_mode"] == "none"
    assert "PRIVATE_APPROVAL_SESSION_DO_NOT_EXPORT" not in serialized
    assert "fixtures/private-output.md" not in serialized
    assert "Write" not in serialized


def test_mock_llm_workflow_route_fails_when_expected_approval_path_is_missing():
    raw_input = {
        "task_id": "fixture-mock-llm-approval-stale-green",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "native_tool_policy": {
            "task_id": "fixture-mock-llm-approval-stale-green",
            "approval_expected": True,
            "policy_hook": {
                "governed": True,
                "session_id": "PRIVATE_APPROVAL_SESSION_DO_NOT_EXPORT",
                "server_url_configured": True,
                "event_phase": "PreToolUse",
            },
            "tool_call": {
                "name": "Write",
                "transport": "native",
                "arguments": {"path": "fixtures/private-output.md"},
            },
        },
        "mock_llm": {
            "enabled": True,
            "responses": [{"content": "mock step completed", "tool_calls": [{"name": "Write"}]}],
        },
        "workflow": {
            "steps": [
                {"id": "approval-step", "expect_contains": "mock step"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_approval_stale_green_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["native_tool_policy"]["permission_decision"] == "no_opinion"
    assert output["native_tool_policy"]["approval_required"] is False
    assert output["native_tool_policy"]["approval_path"] == {
        "expected": True,
        "declared": False,
        "route_status": "not_required",
        "passive": False,
        "tool_executed": False,
        "arguments_exported": False,
    }
    assert output["native_tool_policy"]["failure_mode"] == "approval_path_missing"
    assert output["native_tool_policy"]["passive_or_denied"] is False
    assert output["tool_call_contract"]["all_required_tool_calls_observed"] is True
    assert output["failure_mode"] == "native_policy_route_failed"
    assert "PRIVATE_APPROVAL_SESSION_DO_NOT_EXPORT" not in serialized
    assert "fixtures/private-output.md" not in serialized
    assert "Write" not in serialized


def test_mock_llm_workflow_route_fails_when_response_queue_is_not_consumed():
    raw_input = {
        "task_id": "fixture-mock-llm-unconsumed-queue",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "mock_llm": {
            "enabled": True,
            "responses": [
                {"content": "first response"},
                {"content": "unused response"},
            ],
        },
        "workflow": {
            "steps": [
                {"id": "only-step", "expect_contains": "first"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_unconsumed_queue_inline.json",
    )

    assert output["route_status"] == "failed"
    assert output["mock_llm"]["call_count"] == 1
    assert output["mock_llm"]["response_count"] == 2
    assert output["mock_llm"]["remaining_response_count"] == 1
    assert output["mock_llm"]["all_responses_consumed"] is False
    assert output["failure_mode"] == "mock_llm_queue_not_consumed"


def test_mock_llm_workflow_route_fails_when_declared_native_tool_call_is_not_observed():
    raw_input = {
        "task_id": "fixture-mock-llm-native-tool-not-observed",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "native_tool_policy": {
            "task_id": "fixture-mock-llm-native-tool-not-observed",
            "policy_hook": {
                "governed": True,
                "session_id": "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT",
                "server_url_configured": True,
                "event_phase": "PreToolUse",
                "failure_mode": "timeout",
            },
            "tool_call": {
                "name": "Write",
                "transport": "native",
                "arguments": {"path": "fixtures/private-output.md"},
            },
        },
        "mock_llm": {
            "enabled": True,
            "responses": [{"content": "no tool call was emitted"}],
        },
        "workflow": {
            "steps": [
                {"id": "missing-tool-call", "expect_contains": "no tool call"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_native_tool_not_observed_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["native_tool_policy"]["route_status"] == "denied"
    assert output["native_tool_policy"]["tool_executed"] is False
    assert output["tool_call_contract"]["declared"] is True
    assert output["tool_call_contract"]["required_tool_call_count"] == 1
    assert output["tool_call_contract"]["observed_tool_call_count"] == 0
    assert output["tool_call_contract"]["matched_required_tool_call_count"] == 0
    assert output["tool_call_contract"]["all_required_tool_calls_observed"] is False
    assert output["tool_call_contract"]["raw_tool_arguments_exported"] is False
    assert output["failure_mode"] == "tool_call_contract_failed"
    assert "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT" not in serialized
    assert "fixtures/private-output.md" not in serialized
    assert "Write" not in serialized


def test_mock_llm_workflow_route_fails_when_named_subagent_queue_falls_back_to_default():
    raw_input = {
        "task_id": "fixture-mock-llm-named-subagent-queue-desync",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "sub_agents": {
            "shared_model_key": True,
            "agents": [
                {
                    "name": "PRIVATE_CHILD_DO_NOT_EXPORT",
                    "expected_response_key": "queue-a",
                    "turn_session_ids": ["PRIVATE_SESSION_DO_NOT_EXPORT"],
                    "persistence_required": True,
                }
            ],
        },
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "default": [{"content": "fallback response"}],
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "child-turn",
                    "agent": "PRIVATE_CHILD_DO_NOT_EXPORT",
                    "response_key": "queue-a",
                    "expect_contains": "fallback",
                }
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_named_subagent_queue_desync_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["sub_agents"]["queue_desync_detected"] is True
    assert output["sub_agents"]["agents"][0]["fallback_count"] == 1
    assert output["sub_agents"]["agents"][0]["expected_queue_mismatches"] == 1
    assert output["failure_mode"] == "sub_agent_mock_route_failed"
    assert "PRIVATE_CHILD_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_SESSION_DO_NOT_EXPORT" not in serialized


def test_mock_llm_workflow_route_fails_when_named_subagent_session_is_not_persistent():
    raw_input = {
        "task_id": "fixture-mock-llm-named-subagent-session-drift",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "sub_agents": {
            "agents": [
                {
                    "name": "PRIVATE_CHILD_DO_NOT_EXPORT",
                    "expected_response_key": "queue-a",
                    "turn_session_ids": [
                        "PRIVATE_SESSION_ONE_DO_NOT_EXPORT",
                        "PRIVATE_SESSION_TWO_DO_NOT_EXPORT",
                    ],
                    "persistence_required": True,
                }
            ],
        },
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "queue-a": [{"content": "turn one"}, {"content": "turn two"}],
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "child-turn-1",
                    "agent": "PRIVATE_CHILD_DO_NOT_EXPORT",
                    "response_key": "queue-a",
                    "expect_contains": "turn one",
                },
                {
                    "id": "child-turn-2",
                    "agent": "PRIVATE_CHILD_DO_NOT_EXPORT",
                    "response_key": "queue-a",
                    "expect_contains": "turn two",
                },
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_named_subagent_session_drift_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["sub_agents"]["persistence_passed"] is False
    assert output["sub_agents"]["queue_desync_detected"] is False
    assert output["sub_agents"]["agents"][0]["unique_session_hash_count"] == 2
    assert output["failure_mode"] == "sub_agent_mock_route_failed"
    assert "PRIVATE_CHILD_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_SESSION_ONE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_SESSION_TWO_DO_NOT_EXPORT" not in serialized


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


def test_mock_llm_workflow_route_fails_when_interrupt_idle_replay_loses_or_duplicates_messages():
    raw_input = {
        "task_id": "fixture-mock-llm-interrupt-replay-drift",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "interrupt": {
            "required": True,
            "previous_session_id": "PRIVATE_INTERRUPTED_SESSION_DO_NOT_EXPORT",
            "rebuilt_session_id": "PRIVATE_REBUILT_SESSION_DO_NOT_EXPORT",
            "previous_agent_id": "PRIVATE_AGENT_BEFORE_INTERRUPT_DO_NOT_EXPORT",
            "rebuilt_agent_id": "PRIVATE_AGENT_AFTER_INTERRUPT_DO_NOT_EXPORT",
            "previous_conversation_id": "PRIVATE_CONVERSATION_BEFORE_INTERRUPT_DO_NOT_EXPORT",
            "rebuilt_conversation_id": "PRIVATE_CONVERSATION_AFTER_INTERRUPT_DO_NOT_EXPORT",
            "pending_idle_message_ids": [
                "PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT",
                "PRIVATE_IDLE_MESSAGE_TWO_DO_NOT_EXPORT",
            ],
            "replayed_idle_message_ids": [
                "PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT",
                "PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT",
            ],
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
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_interrupt_replay_drift_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["interrupt"]["session_rebuilt"] is True
    assert output["interrupt"]["agent_rebuilt"] is True
    assert output["interrupt"]["conversation_rebuilt"] is True
    assert output["interrupt"]["idle_replay_counts_match"] is False
    assert output["interrupt"]["lost_idle_message_count"] == 1
    assert output["interrupt"]["duplicated_idle_message_count"] == 1
    assert output["interrupt"]["raw_ids_exported"] is False
    assert output["failure_mode"] == "interrupt_replay_failed"
    assert "PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_IDLE_MESSAGE_TWO_DO_NOT_EXPORT" not in serialized


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


def test_native_tool_call_policy_denies_governed_tool_calls_when_hook_is_unavailable():
    raw_input = {
        "task_id": "fixture-native-policy-pretool-fail-closed",
        "policy_hook": {
            "governed": True,
            "session_id": "session-private-fixture",
            "server_url_configured": True,
            "event_phase": "PreToolUse",
            "failure_mode": "non_2xx",
        },
        "tool_call": {
            "name": "Bash",
            "transport": "native",
            "arguments": {"command": "PRIVATE_COMMAND_BODY_DO_NOT_EXPORT"},
        },
    }

    output = evaluate_harness_behavior(
        "native_tool_call_policy",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "native_tool_call_policy_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "denied"
    assert output["failure_mode"] == "policy_hook_unavailable"
    assert output["policy_hook"]["fail_closed_applied"] is True
    assert output["permission"] == {
        "decision": "deny",
        "reason": "policy_hook_fail_closed:non_2xx",
        "arguments_exported": False,
    }
    assert output["safety"] == {
        "offensive_behavior_local_execution": False,
        "tool_executed": False,
    }
    assert "session-private-fixture" not in serialized
    assert "PRIVATE_COMMAND_BODY_DO_NOT_EXPORT" not in serialized


def test_workspace_changes_panel_non_git_requires_visible_external_and_native_entries_without_git_metadata():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "workspace_changes_panel_non_git_native_external.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["workspace"] == {
        "is_git_repo": False,
        "runner_workspace_configured": True,
        "git_metadata_required": False,
        "non_git_without_git_metadata": True,
    }
    assert output["changes_panel"]["visible_entry_count"] == 3
    assert output["changes_panel"]["empty_panel_silent"] is False
    assert output["changes_panel"]["non_git_limitation_present"] is True
    assert output["edits"]["required_visible_count"] == 3
    assert output["edits"]["visible_required_count"] == 3
    assert output["edits"]["unrecorded_edit_count"] == 2
    assert output["edits"]["missing_visible_edit_ids"] == []
    assert output["privacy"] == {
        "raw_paths_exported": False,
        "raw_contents_exported": False,
        "path_hashes_only": True,
    }
    assert "PRIVATE_NATIVE_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NATIVE_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXTERNAL_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXTERNAL_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REST_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REST_CONTENT_DO_NOT_EXPORT" not in serialized


def test_workspace_changes_panel_fails_stale_visible_path_without_exporting_paths():
    output = evaluate_harness_behavior(
        "workspace_changes_panel",
        {
            "task_id": "fixture-stale-workspace-change-panel",
            "workspace": {
                "is_git_repo": True,
                "runner_workspace_configured": True,
            },
            "performed_edits": [
                {
                    "edit_id": "native-cli-write",
                    "origin": "native_harness",
                    "path": "PRIVATE_CURRENT_PATH_DO_NOT_EXPORT.md",
                    "content": "PRIVATE_CURRENT_CONTENT_DO_NOT_EXPORT",
                    "exists_on_disk": True,
                    "record_change_observed": True,
                }
            ],
            "changes_panel": {
                "available": True,
                "entries": [
                    {
                        "edit_id": "native-cli-write",
                        "kind": "changed_file",
                        "path": "PRIVATE_STALE_PATH_DO_NOT_EXPORT.md",
                        "visible": True,
                    }
                ],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "workspace_changes_panel_stale_path_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "stale_visible_change_entries"
    assert output["edits"]["missing_visible_edit_ids"] == []
    assert output["edits"]["stale_visible_edit_ids"] == ["native-cli-write"]
    assert "PRIVATE_CURRENT_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_STALE_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CURRENT_CONTENT_DO_NOT_EXPORT" not in serialized


def test_workspace_changes_panel_fails_unexpected_extra_visible_changed_file():
    output = evaluate_harness_behavior(
        "workspace_changes_panel",
        {
            "task_id": "fixture-overbroad-workspace-change-panel",
            "workspace": {
                "is_git_repo": True,
                "runner_workspace_configured": True,
            },
            "performed_edits": [
                {
                    "edit_id": "expected-write",
                    "origin": "native_harness",
                    "path": "PRIVATE_EXPECTED_PATH_DO_NOT_EXPORT.md",
                    "content": "PRIVATE_EXPECTED_CONTENT_DO_NOT_EXPORT",
                    "exists_on_disk": True,
                    "record_change_observed": True,
                }
            ],
            "changes_panel": {
                "available": True,
                "entries": [
                    {
                        "edit_id": "expected-write",
                        "kind": "changed_file",
                        "path": "PRIVATE_EXPECTED_PATH_DO_NOT_EXPORT.md",
                        "visible": True,
                    },
                    {
                        "edit_id": "stale-unrelated-write",
                        "kind": "changed_file",
                        "path": "PRIVATE_UNRELATED_PATH_DO_NOT_EXPORT.md",
                        "visible": True,
                    },
                ],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "workspace_changes_panel_overbroad_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "unexpected_visible_change_entries"
    assert output["edits"]["missing_visible_edit_ids"] == []
    assert output["edits"]["unexpected_visible_edit_ids"] == ["stale-unrelated-write"]
    assert "PRIVATE_EXPECTED_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_UNRELATED_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXPECTED_CONTENT_DO_NOT_EXPORT" not in serialized


def test_native_tool_call_policy_matrix_does_not_silently_allow_policy_hook_failures():
    cases = [
        ("timeout", "denied", "policy_hook_unavailable", "deny", "policy_hook_fail_closed:timeout"),
        (
            "connect_error",
            "denied",
            "policy_hook_unavailable",
            "deny",
            "policy_hook_fail_closed:connect_error",
        ),
        ("non_2xx", "denied", "policy_hook_unavailable", "deny", "policy_hook_fail_closed:non_2xx"),
        (
            "slow_ask_timeout",
            "review_only",
            "policy_ask_timeout",
            "review_required",
            "policy_hook_ask_timeout:slow_ask_timeout",
        ),
    ]

    for hook_failure_mode, route_status, failure_mode, decision, reason in cases:
        output = evaluate_harness_behavior(
            "native_tool_call_policy",
            {
                "task_id": f"fixture-native-policy-{hook_failure_mode}",
                "policy_hook": {
                    "governed": True,
                    "session_id": "session-private-fixture",
                    "server_url_configured": True,
                    "event_phase": "PreToolUse",
                    "failure_mode": hook_failure_mode,
                },
                "tool_call": {
                    "name": "Bash",
                    "transport": "native",
                    "arguments": {"command": "PRIVATE_COMMAND_BODY_DO_NOT_EXPORT"},
                },
            },
            source_path=LOCAL_EVAL_FIXTURE_DIR / f"native_tool_call_policy_{hook_failure_mode}_inline.json",
        )

        assert output["route_status"] == route_status
        assert output["failure_mode"] == failure_mode
        assert output["permission"]["decision"] == decision
        assert output["permission"]["reason"] == reason
        assert output["permission"]["arguments_exported"] is False
        assert output["safety"]["tool_executed"] is False


def test_native_tool_call_policy_keeps_advisory_and_ungoverned_paths_fail_open():
    advisory_output = evaluate_harness_behavior(
        "native_tool_call_policy",
        {
            "policy_hook": {
                "governed": True,
                "session_id": "session-private-fixture",
                "server_url_configured": True,
                "event_phase": "PostToolUse",
                "failure_mode": "connect_error",
            },
            "tool_call": {"name": "Bash"},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "native_tool_call_policy_advisory_inline.json",
    )
    ungoverned_output = evaluate_harness_behavior(
        "native_tool_call_policy",
        {
            "policy_hook": {
                "governed": False,
                "event_phase": "PreToolUse",
                "failure_mode": "connect_error",
            },
            "tool_call": {"name": "Bash"},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "native_tool_call_policy_ungoverned_inline.json",
    )

    assert advisory_output["route_status"] == "passed"
    assert advisory_output["policy_hook"]["fail_closed_applied"] is False
    assert advisory_output["permission"]["decision"] == "no_opinion"
    assert advisory_output["permission"]["reason"] == "policy_hook_advisory_phase_fail_open"
    assert ungoverned_output["route_status"] == "passed"
    assert ungoverned_output["policy_hook"]["fail_closed_applied"] is False
    assert ungoverned_output["permission"]["decision"] == "no_opinion"
    assert ungoverned_output["permission"]["reason"] == "policy_hook_not_governed"


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
    assert payload["fixture_count"] == 9
    assert payload["pass_count"] == 9
    assert payload["fail_count"] == 0
    assert payload["privacy"]["fixture_inputs_exported"] is False
    assert "fixture-agent-harness-adapter" not in serialized
    assert "https://github.com/ApodexAI/AgentHarness" not in serialized

    results = {result["name"]: result for result in payload["results"]}
    agent_codex = results["proposal-interpretation-agent-codex-workflow-validation"]
    agent_harness = results["proposal-interpretation-agent-harness-eval-lane"]
    accepted = results["proposal-interpretation-accepts-item-refs"]
    malformed_json = results["proposal-interpretation-rejects-malformed-json"]
    rejected = results["proposal-interpretation-rejects-url-refs"]
    truncated = results["proposal-interpretation-rejects-truncated-refs"]
    boundary = results["proposal-interpretation-policy-boundary"]
    max_proposals = results["proposal-interpretation-rejects-too-many-proposals"]
    current_wake = results["proposal-interpretation-visa-current-wake-agent-harness-eval"]

    assert agent_codex["passed"] is True
    assert agent_harness["passed"] is True
    assert accepted["passed"] is True
    assert malformed_json["passed"] is True
    assert rejected["passed"] is True
    assert truncated["passed"] is True
    assert boundary["passed"] is True
    assert max_proposals["passed"] is True
    assert current_wake["passed"] is True
    assert all(assertion["passed"] for assertion in agent_codex["assertions"])
    assert all(assertion["passed"] for assertion in agent_harness["assertions"])
    assert all(assertion["passed"] for assertion in accepted["assertions"])
    assert all(assertion["passed"] for assertion in malformed_json["assertions"])
    assert all(assertion["passed"] for assertion in rejected["assertions"])
    assert all(assertion["passed"] for assertion in truncated["assertions"])
    assert all(assertion["passed"] for assertion in boundary["assertions"])
    assert all(assertion["passed"] for assertion in max_proposals["assertions"])
    assert all(assertion["passed"] for assertion in current_wake["assertions"])


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
        "route_hint_policy",
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
    assert output["route_hint_policy"]["validation_lanes"]["agent_harness_eval"] == [
        "documentation",
        "test",
        "code_patch",
    ]
    supplied_item_ids = set(output["evidence_ref_policy"]["supplied_item_ids"])
    assert supplied_item_ids == {"agent-harness", "opencode-harness"}
    for candidate in output["accepted_candidates"]:
        assert set(candidate["evidence_refs"]) <= supplied_item_ids
