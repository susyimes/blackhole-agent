import json
from pathlib import Path

from blackhole_agent.harness_eval import (
    build_harness_comparison_report,
    evaluate_harness_behavior,
    run_local_harness_eval,
    stable_text_hash,
    skill_route_discovery_inspection_requirements,
    skill_route_discovery_provider_runtime_control,
    skill_route_discovery_provider_runtime_preflight_contract,
    skill_route_discovery_preactivation_trust_boundary,
    skill_route_discovery_preactivation_validation_commands,
)


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
    assert payload["fixture_count"] == 46
    assert payload["pass_count"] == 45
    assert payload["fail_count"] == 1
    assert payload["privacy"]["fixture_inputs_exported"] is False
    assert payload["privacy"]["supported_behaviors"] == [
        "agent_harness_eval_lane",
        "agent_harness_provider_registration",
        "agent_workflow_route",
        "harness_run_summary",
        "headless_tool_roundtrip",
        "mock_e2e_runner_tier",
        "mock_llm_workflow_route",
        "native_skill_session_title",
        "native_tool_call_policy",
        "push_delivery_path",
        "provider_runtime_preflight",
        "provider_runtime_recovery_summary",
        "proposal_interpretation",
        "rendered_html_artifact_validation",
        "skill_route_discovery_lane",
        "workspace_changes_panel",
    ]
    assert "PRIVATE_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_FAIL_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_FAIL_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_ONESHOT_MARKER_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HEADLESS_TEXT_EVENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_FUNCTION_ARGUMENT_DO_NOT_EXPORT" not in serialized

    results = {result["name"]: result for result in payload["results"]}
    assert results["agent-workflow-route-success"]["passed"] is True
    assert results["agent-workflow-route-orchestrator-inbox-delivery"]["passed"] is True
    assert results["agent-harness-eval-lane-general-agent-projects"]["passed"] is True
    assert results["agent-harness-eval-lane-visa-current-wake"]["passed"] is True
    assert results["agent-workflow-route-oneshot-marker-absent"]["passed"] is True
    assert results["agent-workflow-route-control-plane-replay"]["passed"] is True
    assert results["agent-workflow-route-streamed-tool-boundary"]["passed"] is True
    assert results["agent-workflow-route-report-sections-missing"]["passed"] is True
    assert results["agent-harness-provider-registration-qwencode-missing-config"]["passed"] is True
    assert results["agent-harness-provider-registration-host-owner-mismatch"]["passed"] is True
    assert results["agent-workflow-route-recoverable-failure"]["passed"] is True
    assert results["agent-workflow-route-lifecycle-trace"]["passed"] is True
    assert results["headless-tool-roundtrip-function-call"]["passed"] is True
    assert results["mock-e2e-runner-tier-host-native-misc"]["passed"] is True
    assert results["mock-e2e-runner-tier-host-native-ask-boundary"]["passed"] is True
    assert results["mock-e2e-runner-tier-ci-roundtrip-hang"]["passed"] is True
    assert results["mock-e2e-runner-tier-compaction-known-failure-repoint"]["passed"] is True
    assert results["mock-e2e-runner-tier-yaml-agent-route"]["passed"] is True
    assert results["mock-llm-chat-completions-contract"]["passed"] is True
    assert results["mock-llm-workflow-route-provider-disabled"]["passed"] is True
    assert results["mock-llm-multimodal-missing-image-input"]["passed"] is True
    assert results["mock-llm-multimodal-text-encoded-blocks"]["passed"] is True
    assert results["mock-llm-interrupt-rebuild-replay"]["passed"] is True
    assert results["mock-llm-named-subagent-policy-route"]["passed"] is True
    assert results["mock-llm-repl-approval-output-poll"]["passed"] is True
    assert results["mock-llm-session-file-tool-route"]["passed"] is True
    assert results["native-skill-session-title-slash-command"]["passed"] is True
    assert results["native-tool-call-policy-fail-closed"]["passed"] is True
    assert results["native-tool-call-policy-slow-ask-timeout"]["passed"] is True
    assert results["push-delivery-path-mock-success"]["passed"] is True
    assert results["provider-runtime-preflight-apple-silicon-brew-jiter-linkage"]["passed"] is True
    assert results["provider-runtime-preflight-claude-sandbox-override"]["passed"] is True
    assert results["provider-runtime-preflight-claude-long-status-prompt-scan"]["passed"] is True
    assert results["provider-runtime-preflight-native-claude-iterm2-tmux-timeout-risk"]["passed"] is True
    assert results["provider-runtime-preflight-openai-agents-mock-auth"]["passed"] is True
    assert results["provider-runtime-preflight-openai-agents-no-worker-env-skip"]["passed"] is True
    assert results["provider-runtime-preflight-omnigent-model-command-missing"]["passed"] is True
    assert results["provider-runtime-preflight-review-model-unavailable"]["passed"] is True
    assert results["provider-runtime-preflight-usage-limit-429"]["passed"] is True
    assert results["provider-runtime-recovery-summary-blocked-and-degraded"]["passed"] is True
    assert results["rendered-html-artifact-js-and-links"]["passed"] is True
    assert results["skill-route-discovery-lane-fablecodex"]["passed"] is True
    assert results["skill-route-discovery-lane-fork-lineage"]["passed"] is True
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
    assert "PRIVATE_REPL_APPROVAL_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REPL_APPROVAL_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REPL_OUTPUT_STALE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REPL_OUTPUT approval required DO_NOT_EXPORT" not in serialized
    assert "native-ask-session-fixture-do-not-export" not in serialized
    assert "PRIVATE_ASK_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NATIVE_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NATIVE_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXTERNAL_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXTERNAL_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REST_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REST_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HOST_NATIVE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HOST_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXISTING_OWNER_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_AUTHENTICATED_OWNER_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HOST_NATIVE_ASK_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_E2E_POLICY_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_E2E_ASK_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_YAML_AGENT_PROMPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_YAML_PARSE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_YAML_AGENT_PATH_DO_NOT_EXPORT" not in serialized
    assert "local_fixture.tools.retain" not in serialized
    assert "PRIVATE_BOOT_PROBE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CI_ROUNDTRIP_FAILURE_TEXT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CI_ROUNDTRIP_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "Pattern 'sleeping' not found" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "QWENCODE_API_KEY" not in serialized
    assert "127.0.0.1" not in serialized
    assert "PRIVATE_CHAT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_STREAMING_CHAT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_STREAMED_TOOL_ARGUMENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_STREAMED_TOOL_RESULT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_STREAMED_TOOL_CALL_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_ASSISTANT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REVIEW_MODEL_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REVIEW_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REVIEW_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_PROVIDER_429_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HOMEBREW_PREFIX_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_DYLIB_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_RELINK_ERROR_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CREDENTIAL_LABEL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_5H_RESET_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_WEEKLY_RESET_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RETRY_AFTER_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RENDERED_HTML_BODY_DO_NOT_EXPORT" not in serialized
    assert "private-link-do-not-export" not in serialized
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/visa/visa-vulnerability-agentic-harness" not in serialized
    assert "https://github.com/omnigent-ai/omnigent" not in serialized

    failing_assertions = results["fail-harness-summary"]["assertions"]
    assert failing_assertions[0]["passed"] is True
    assert failing_assertions[1] == {
        "path": "failure_mode",
        "expected": "none",
        "actual": "nonzero_exit",
        "passed": False,
        "failure_mode": "equals_mismatch",
    }


def test_mock_llm_repl_approval_output_poll_times_out_without_single_sample_pass():
    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        {
            "task_id": "fixture-mock-llm-repl-approval-output-timeout",
            "provider": {"enabled": False},
            "native_tool_policy": {
                "approval_expected": True,
                "policy_hook": {
                    "governed": True,
                    "session_id": "PRIVATE_TIMEOUT_SESSION_DO_NOT_EXPORT",
                    "server_url_configured": True,
                    "event_phase": "TOOL_CALL",
                    "failure_mode": "none",
                    "verdict": {"review_required": True, "reason": "operator_ask"},
                },
                "tool_call": {
                    "name": "Bash",
                    "transport": "native",
                    "arguments": {"command": "PRIVATE_TIMEOUT_COMMAND_DO_NOT_EXPORT"},
                },
                "approval_output_poll": {
                    "required": True,
                    "timeout_ms": 250,
                    "interval_ms": 250,
                    "expected_contains": "approval required",
                    "samples": [
                        {"output": "PRIVATE_TIMEOUT_STALE_OUTPUT_DO_NOT_EXPORT"},
                    ],
                },
            },
            "mock_llm": {
                "enabled": True,
                "responses": [
                    {
                        "content": "mock route reached approval boundary",
                        "tool_calls": [{"name": "Bash"}],
                    }
                ],
            },
            "workflow": {"steps": [{"id": "approval-turn", "expect_contains": "approval boundary"}]},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_repl_approval_output_timeout_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "native_policy_route_failed"
    assert output["native_tool_policy"]["failure_mode"] == "approval_output_poll_timeout"
    assert output["native_tool_policy"]["approval_output_poll"]["passed"] is False
    assert output["native_tool_policy"]["approval_output_poll"]["poll_attempt_count"] == 1
    assert output["native_tool_policy"]["approval_output_poll"]["raw_output_exported"] is False
    assert "PRIVATE_TIMEOUT_STALE_OUTPUT_DO_NOT_EXPORT" not in serialized


def test_native_skill_session_title_blocks_generic_provider_fallback_without_exporting_context():
    output = evaluate_harness_behavior(
        "native_skill_session_title",
        {
            "task_id": "fixture-native-skill-generic-title",
            "provider_label": "Claude Code",
            "launch_context": {
                "command": "/my-plugin:my-skill",
                "skill_name": "my-skill",
                "arguments": "PRIVATE_COMMAND_ARGUMENT_DO_NOT_EXPORT",
                "expected_title": "my-skill ARG-123",
            },
            "transcript": [
                {
                    "type": "slash_command",
                    "command_name": "/my-plugin:my-skill",
                    "arguments": "PRIVATE_COMMAND_ARGUMENT_DO_NOT_EXPORT",
                }
            ],
            "session_metadata": {
                "title": "Claude Code",
                "title_source": "provider",
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "native_skill_session_title_generic_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "generic_provider_title"
    assert output["launch_path"]["skill_or_slash_first"] is True
    assert output["session_title"]["generic_provider_fallback"] is True
    assert output["session_title"]["context_derived"] is False
    assert output["activation_gate"]["decision"] == "blocked_before_activation"
    assert output["privacy"]["provider_launched"] is False
    assert "PRIVATE_COMMAND_ARGUMENT_DO_NOT_EXPORT" not in serialized
    assert "Claude Code" not in serialized


def test_rendered_html_artifact_validation_covers_script_execution_and_link_targets():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "rendered_html_artifact_js_and_links.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["artifact"]["rendered_boundary"] == "rendered_html_artifact"
    assert output["artifact"]["html_hash"].startswith("sha256:")
    assert output["script_execution"] == {
        "expected": True,
        "observed": True,
        "passed": True,
    }
    assert output["link_navigation"]["same_frame_anchor_count"] == 1
    assert output["link_navigation"]["target_blank_anchor_count"] == 1
    assert output["link_navigation"]["all_expected_new_frame"] is True
    assert output["link_navigation"]["passed"] is True
    assert output["snapshot_gate"] == {
        "required": True,
        "state": "empty_landing",
        "baseline_hash_present": True,
        "current_hash_present": True,
        "diff_hash_present": True,
        "diff_status": "clean",
        "empty_state_expected": True,
        "empty_state_observed": True,
        "passed": True,
        "failure_mode": "none",
        "raw_snapshot_paths_exported": False,
        "raw_snapshot_images_exported": False,
    }
    assert all(probe["raw_href_exported"] is False for probe in output["link_navigation"]["probes"])
    assert "PRIVATE_RENDERED_HTML_BODY_DO_NOT_EXPORT" not in serialized
    assert "private-link-do-not-export" not in serialized
    assert "PRIVATE_BASELINE_SNAPSHOT_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CURRENT_SNAPSHOT_PATH_DO_NOT_EXPORT" not in serialized


def test_agent_harness_eval_lane_turns_public_harness_evidence_into_local_eval_lanes():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_harness_eval_lane_visa_current_wake.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["evidence_strength"] == {
        "record_count": 2,
        "recognized_harness_record_count": 2,
        "specific_detail_count": 1,
        "activation_evidence_sufficient": True,
    }
    assert output["lane_map"] == {
        "allowed_proposal_kinds": ["documentation", "test", "code_patch"],
        "proposal_lane_count": 2,
        "proposal_kinds": ["code_patch", "test"],
        "lanes_bounded": True,
        "unsupported_lanes": [],
        "lane_runtime_safe": True,
        "local_validation_required": True,
    }
    assert output["activation_gate"] == {
        "controller_surface": "agent_harness_eval_lane",
        "activation_scope": "local_eval_only",
        "decision": "ready_for_local_eval_activation",
        "reason": "none",
        "local_eval_activation_allowed": True,
        "external_harness_execution_allowed": False,
    }
    assert output["activation_lanes"] == [
        {
            "proposal_kind": "code_patch",
            "item_ids": ["visa-harness-structured-eval"],
            "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
            "activation_ready": True,
            "activation_blockers": [],
            "runtime_action": "none",
            "external_harness_execution_allowed": False,
        },
        {
            "proposal_kind": "test",
            "item_ids": ["visa-harness-structured-eval"],
            "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
            "activation_ready": True,
            "activation_blockers": [],
            "runtime_action": "none",
            "external_harness_execution_allowed": False,
        },
    ]
    assert output["review_notes"] == [
        {
            "item_id": "visa-harness-security-boundary",
            "risk_flags": ["offensive-behavior"],
            "review_gate": "offensive-behavior-human-review",
            "local_eval_activation_allowed": False,
        }
    ]
    assert {lane["runtime_action"] for lane in output["proposal_lanes"]} == {"none"}
    assert all(lane["source_url_hash"].startswith("sha256:") for lane in output["proposal_lanes"])
    assert output["privacy"] == {
        "raw_source_urls_exported": False,
        "raw_evidence_bodies_exported": False,
        "source_urls_hashed": True,
        "runtime_actions_executed": False,
        "offensive_behavior_local_execution": False,
    }
    assert "https://github.com/visa/visa-vulnerability-agentic-harness" not in serialized


def test_agent_harness_eval_lane_maps_general_agent_project_claims_before_activation():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_harness_eval_lane_general_agent_projects.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["activation_gate"]["local_eval_activation_allowed"] is True
    assert output["activation_gate"]["external_harness_execution_allowed"] is False
    assert output["lane_map"]["proposal_kinds"] == ["code_patch", "documentation", "test"]
    assert output["claim_evaluation"]["controller_surface"] == "agent_harness_claim_mapping"
    assert output["claim_evaluation"]["mapping_status"] == "partial"
    assert output["claim_evaluation"]["mapped_claim_ids"] == [
        "conversation_state_or_memory",
        "multi_agent_orchestration",
        "policy_or_sandbox_control",
        "provider_configuration_surface",
    ]
    assert output["claim_evaluation"]["unmapped_claim_ids"] == ["local_data_grounding"]
    assert output["claim_evaluation"]["runtime_action"] == "none"
    assert output["claim_evaluation"]["external_agent_activation_allowed"] is False

    rows_by_claim = {
        (row["item_id"], row["claim_id"]): row
        for row in output["claim_evaluation"]["rows"]
    }
    assert rows_by_claim[
        ("omnigent-general-agent-framework", "multi_agent_orchestration")
    ]["local_capabilities"] == ["agent_workflow_route"]
    assert rows_by_claim[
        ("omnigent-general-agent-framework", "policy_or_sandbox_control")
    ]["required_validation"] == ["pytest tests/test_harness_eval.py -q -k native_tool_call_policy"]
    assert rows_by_claim[
        ("xuefeng-agent-domain-advisor", "local_data_grounding")
    ]["status"] == "unmapped_evidence_only"
    assert "https://github.com/omnigent-ai/omnigent" not in serialized
    assert "https://github.com/ziqihe10-droid/xuefeng-agent" not in serialized


def test_agent_harness_eval_lane_blocks_unbounded_or_weak_routes():
    unbounded = evaluate_harness_behavior(
        "agent_harness_eval_lane",
        {
            "task_id": "fixture-agent-harness-unbounded",
            "evidence_items": [
                {
                    "item_id": "harness-config-drift",
                    "source_url": "https://github.com/example/harness",
                    "route_hints": ["agent_harness_eval"],
                    "summary": "Public harness evaluation evidence with deterministic fixture shape.",
                    "suggested_lanes": ["config", "test"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_harness_eval_lane_unbounded_inline.json",
    )
    weak = evaluate_harness_behavior(
        "agent_harness_eval_lane",
        {
            "task_id": "fixture-agent-harness-weak",
            "evidence_items": [
                {
                    "item_id": "generic-harness-mention",
                    "source_url": "https://github.com/example/harness",
                    "route_hints": ["agent_harness_eval"],
                    "summary": "Generic public movement with no concrete local detail.",
                    "suggested_lanes": ["test"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_harness_eval_lane_weak_inline.json",
    )

    assert unbounded["route_status"] == "blocked"
    assert unbounded["failure_mode"] == "unbounded_agent_harness_eval_lane"
    assert unbounded["lane_map"]["unsupported_lanes"] == ["config"]
    assert unbounded["activation_gate"]["external_harness_execution_allowed"] is False

    assert weak["route_status"] == "blocked"
    assert weak["failure_mode"] == "weak_harness_evidence"
    assert weak["activation_gate"]["decision"] == "review_weak_evidence_before_activation"
    assert weak["activation_lanes"][0]["activation_ready"] is False


def test_agent_workflow_route_blocks_invalid_streamed_tool_boundaries_without_exporting_bodies():
    base = {
        "task_id": "fixture-route-invalid-streamed-tool-boundary",
        "plan": {"steps": [{"id": "intake"}, {"id": "invoke-runner"}]},
        "runner": {"invoked": True, "returncode": 0, "timed_out": False},
        "validation": {
            "gate": "runner-harness-control-plane",
            "checks": [{"name": "stream-boundary", "returncode": 0}],
        },
        "rollback": {
            "created": True,
            "ref": "refs/rollback/fixture-route-invalid-streamed-tool-boundary",
            "artifact_path": "artifacts/rollback/fixture-route-invalid-streamed-tool-boundary.txt",
        },
        "recovery": {
            "required": True,
            "commands": ["git reset --hard PRIVATE_STREAM_ROLLBACK_DO_NOT_EXPORT"],
            "replay_command": "pytest tests/test_harness_eval.py -q -k streamed_tool_boundaries",
        },
        "artifacts": {
            "report_recorded": True,
            "report_sections": ["changed_files", "validation", "rollback", "replay", "review_notes"],
        },
    }
    url_ref = dict(base)
    url_ref["streamed_tool_boundaries"] = {
        "required": True,
        "allowed_item_ids": ["omnigent-inline-tool-streaming"],
        "events": [
            {
                "type": "tool_result",
                "tool_call_id": "PRIVATE_STREAM_CALL_DO_NOT_EXPORT",
                "stream_state": "complete",
                "item_id": "omnigent-inline-tool-streaming",
                "evidence_refs": ["https://github.com/omnigent-ai/omnigent"],
                "result_json": {"status": "ok", "body": "PRIVATE_STREAM_RESULT_DO_NOT_EXPORT"},
            }
        ],
    }
    non_json = dict(base)
    non_json["streamed_tool_boundaries"] = {
        "required": True,
        "events": [
            {
                "type": "tool_result",
                "tool_call_id": "PRIVATE_STREAM_CALL_DO_NOT_EXPORT",
                "stream_state": "complete",
                "result_json": "PRIVATE_NOT_JSON_DO_NOT_EXPORT",
            }
        ],
    }

    url_output = evaluate_harness_behavior(
        "agent_workflow_route",
        url_ref,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_stream_url_ref_inline.json",
    )
    non_json_output = evaluate_harness_behavior(
        "agent_workflow_route",
        non_json,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_stream_non_json_inline.json",
    )
    serialized = json.dumps({"url": url_output, "non_json": non_json_output}, sort_keys=True)

    assert url_output["route_status"] == "failed_recoverable"
    assert url_output["failure_mode"] == "streamed_tool_boundary_url_ref"
    assert url_output["control_plane"]["stream_boundary_contract"]["url_ref_event_count"] == 1
    assert url_output["streamed_tool_boundaries"]["policy"]["url_refs_allowed"] is False

    assert non_json_output["route_status"] == "failed_recoverable"
    assert non_json_output["failure_mode"] == "streamed_tool_boundary_non_json_result"
    assert non_json_output["control_plane"]["stream_boundary_contract"]["invalid_json_event_count"] == 1
    assert non_json_output["rollback"]["available"] is True

    assert "PRIVATE_STREAM_RESULT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NOT_JSON_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_STREAM_CALL_DO_NOT_EXPORT" not in serialized
    assert "https://github.com/omnigent-ai/omnigent" not in serialized


def test_skill_route_discovery_lane_fixture_bounds_evidence_before_activation():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_fablecodex.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["registry"] == {
        "registry_status": "classification_only",
        "candidate_count": 1,
        "enabled_candidate_count": 0,
        "invalid_candidate_count": 0,
        "executable_skill_count": 0,
    }
    assert output["lane_map"]["proposal_kinds"] == ["code_patch", "config", "documentation", "test"]
    assert output["lane_map"]["proposal_lane_count"] == 4
    assert output["lane_map"]["route_profile_catalog"] == {
        "body_free": True,
        "profile_counts": {"codex_workflow_gate": 4},
        "profile_lane_counts": {
            "codex_workflow_gate:code_patch": 1,
            "codex_workflow_gate:config": 1,
            "codex_workflow_gate:documentation": 1,
            "codex_workflow_gate:test": 1,
        },
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
    }
    assert output["lane_map"]["lanes_bounded"] is True
    assert output["lane_map"]["lane_runtime_safe"] is True
    assert output["lane_map"]["local_validation_required"] is True
    assert "unvalidated_external_skill_evidence" in output["lane_map"]["uncertainty_reasons"]
    assert output["uncertainty"] == {
        "body_free": True,
        "missing_detail_risk": True,
        "reasons": ["unvalidated_external_skill_evidence", "missing_detail_risk"],
        "message": (
            "Skill-route evidence has missing_detail_risk; activate only bounded local documentation, "
            "config, test, or code_patch lanes after validation."
        ),
    }
    assert output["evidence_strength"]["tier"] == "specific_route_or_validation_evidence"
    assert output["evidence_strength"]["activation_evidence_sufficient"] is True
    assert output["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "single_or_independent_sources",
        "candidate_source_count": 1,
        "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
        "related_source_count": 0,
        "related_source_hashes": [],
        "duplicate_summary_count": 0,
        "evidence_item_id_count": 3,
        "fork_or_mirror_lineage_collapsed": False,
        "raw_source_urls_exported": False,
        "raw_related_source_urls_exported": False,
    }
    assert output["activation_gate"] == {
        "controller_surface": "skill_route_discovery_lane",
        "activation_scope": "local_proposal_only",
        "decision": "ready_for_local_proposal_activation",
        "reason": "none",
        "local_proposal_activation_allowed": True,
        "external_skill_activation_allowed": False,
    }
    assert output["operator_recovery_plan"] == {
        "controller_surface": "skill_route_discovery_operator_recovery_plan",
        "decision": "ready_for_local_replay",
        "reason": "none",
        "route_status": "passed",
        "activation_decision": "ready_for_local_proposal_activation",
        "trust_boundary_passed": True,
        "recovery_required": False,
        "next_action": "run_skill_route_replay_before_promotion",
        "replay_commands": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "recovery_step_count": 0,
        "recovery_hint_codes": [],
        "recovery_hint_code_hashes": [],
        "recovery_steps": [],
        "local_validation_required": True,
        "body_free_diagnostics_only": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert output["preactivation_trust_boundary"] == {
        "status": "passed",
        "diagnostics": [],
        "static_declaration_rechecked": True,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }
    assert output["implementation_intake_preflight"] == {
        "status": "ready",
        "implementation_allowed": True,
        "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
        "proposal_kinds": ["code_patch", "config", "documentation", "test"],
        "activation_lane_count": 4,
        "target_path_count": 6,
        "target_path_hashes": [
            stable_text_hash("docs/skill-route-discovery.md"),
            stable_text_hash("src/blackhole_agent/harness_eval.py"),
            stable_text_hash("src/blackhole_agent/proposal_synthesis.py"),
            stable_text_hash("src/blackhole_agent/skill_routing.py"),
            stable_text_hash("tests/test_harness_eval.py"),
            stable_text_hash("tests/test_skill_routing.py"),
        ],
        "changed_file_review_required": True,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_upstream_body_allowed": False,
        "raw_target_paths_exported": False,
        "diagnostics": [],
    }
    assert output["supervisor_readiness"] == {
        "decision": "ready_for_supervisor_promotion",
        "reason": "none",
        "activation_lane_count": 4,
        "ready_lane_count": 4,
        "blocked_lane_count": 0,
        "proposal_kinds": ["code_patch", "config", "documentation", "test"],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "replay_commands": skill_route_discovery_preactivation_validation_commands(),
        "validation_present": True,
        "local_artifact_proof_present": True,
        "local_artifact_proof_ready": True,
        "trust_boundary_passed": True,
        "provider_runtime_preflight_present": True,
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "recovery_hint_codes": [],
        "source_lineage": {
            "body_free": True,
            "lineage_mode": "single_or_independent_sources",
            "candidate_source_count": 1,
            "related_source_count": 0,
            "duplicate_summary_count": 0,
            "fork_or_mirror_lineage_collapsed": False,
            "raw_source_urls_exported": False,
            "raw_related_source_urls_exported": False,
        },
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "restart_or_remote_activation_required": False,
    }
    assert output["operator_handoff"]["status"] == "ready"
    assert output["operator_handoff"]["decision"] == "handoff_local_artifact_lanes"
    assert output["operator_handoff"]["ready_lane_count"] == 4
    assert output["operator_handoff"]["blocked_lane_count"] == 0
    assert output["operator_handoff"]["local_artifact_proof_ready"] is True
    assert output["operator_handoff"]["implementation_intake_status"] == "ready"
    assert output["operator_handoff"]["supervisor_decision"] == "ready_for_supervisor_promotion"
    assert (
        output["operator_handoff"]["required_validation"] == skill_route_discovery_preactivation_validation_commands()
    )
    assert output["operator_handoff"]["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert output["operator_handoff"]["provider_runtime_control"] == skill_route_discovery_provider_runtime_control(
        activation_ready=True,
        recovery_hint_codes=[],
    )
    assert output["operator_handoff"]["provider_runtime_control"]["next_action"] == (
        "run_provider_runtime_replay_before_promotion"
    )
    assert output["operator_handoff"]["provider_runtime_control"]["recovery_hint_count"] == 0
    assert output["operator_handoff"]["provider_runtime_control"]["recovery_hint_code_hashes"] == []
    assert output["provider_runtime_diagnostic_panel"] == {
        "controller_surface": "provider_runtime_control",
        "status": "ready",
        "decision": "replay_provider_runtime_preflight_before_promotion",
        "activation_lane_count": 4,
        "ready_lane_count": 4,
        "blocked_lane_count": 0,
        "provider_runtime_preflight_contract_present": True,
        "provider_runtime_preflight_contract_valid": True,
        "provider_runtime_control_present": True,
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "recovery_hint_count": 0,
        "recovery_hint_codes": [],
        "recovery_hint_code_hashes": [],
        "diagnostics": [],
        "local_replay_only": True,
        "body_free_diagnostics_only": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
    }
    assert output["operator_handoff"]["recovery_hint_codes"] == []
    assert output["operator_handoff"]["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "single_or_independent_sources",
        "candidate_source_count": 1,
        "related_source_count": 0,
        "fork_or_mirror_lineage_collapsed": False,
    }
    assert output["operator_handoff"]["raw_evidence_exported"] is False
    assert output["operator_handoff"]["raw_source_urls_exported"] is False
    assert output["operator_handoff"]["raw_target_paths_exported"] is False
    assert output["operator_handoff"]["runtime_action_allowed"] is False
    assert output["operator_handoff"]["external_skill_activation_allowed"] is False
    assert output["operator_handoff"]["external_harness_execution_allowed"] is False
    assert output["operator_handoff"]["provider_runtime_launch_allowed"] is False
    assert output["operator_handoff"]["remote_execution_allowed"] is False
    assert [row["proposal_kind"] for row in output["operator_handoff"]["lane_rows"]] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    assert all(row["activation_ready"] is True for row in output["operator_handoff"]["lane_rows"])
    assert all(row["local_artifact_proof_ready"] is True for row in output["operator_handoff"]["lane_rows"])
    assert all(row["target_path_hashes"] for row in output["operator_handoff"]["lane_rows"])
    assert all(row["runtime_action"] == "none" for row in output["operator_handoff"]["lane_rows"])
    assert all(
        row["external_skill_activation_allowed"] is False
        and row["external_harness_execution_allowed"] is False
        and row["raw_target_paths_exported"] is False
        and row["raw_source_urls_exported"] is False
        for row in output["operator_handoff"]["lane_rows"]
    )
    assert [lane["proposal_kind"] for lane in output["activation_lanes"]] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    for lane in output["activation_lanes"]:
        assert lane["candidate_count"] == 1
        assert lane["candidate_names"] == ["codex-fable5"]
        assert lane["candidate_source_hashes"] == [stable_text_hash("https://github.com/baskduf/FableCodex")]
        assert lane["required_validation"] == skill_route_discovery_preactivation_validation_commands()
        assert lane["local_artifact_contract"]["proposal_kind"] == lane["proposal_kind"]
        assert lane["local_artifact_contract"]["target_paths"]
        assert lane["local_artifact_contract"]["required_review_surface"] == "changed_files_and_validation"
        assert lane["local_artifact_contract"]["local_only"] is True
        assert lane["local_artifact_contract"]["external_skill_code_allowed"] is False
        assert lane["local_artifact_contract"]["raw_upstream_body_allowed"] is False
        assert lane["inspection_requirements"] == skill_route_discovery_inspection_requirements(lane["proposal_kind"])
        assert lane["local_artifact_proof"]["ready"] is True
        assert lane["local_artifact_proof"]["provided"] is True
        assert lane["local_artifact_proof"]["target_paths_matched"] is True
        assert lane["local_artifact_proof"]["validation_matched"] is True
        assert lane["local_artifact_proof"]["rollback_recorded"] is True
        assert lane["local_artifact_proof"]["review_note_recorded"] is True
        assert lane["local_artifact_proof"]["raw_changed_files_exported"] is False
        assert lane["local_artifact_proof"]["raw_rollback_artifact_exported"] is False
        assert lane["preactivation_harness"] == {
            "behavior": "agent_harness_eval_lane",
            "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
            "local_eval_only": True,
            "external_harness_execution_allowed": False,
        }
        assert lane["provider_runtime_preflight"] == skill_route_discovery_provider_runtime_preflight_contract()
        assert lane["provider_runtime_control"] == skill_route_discovery_provider_runtime_control(
            activation_ready=True,
            recovery_hint_codes=[],
        )
        assert lane["activation_ready"] is True
        assert lane["activation_blockers"] == []
        assert lane["recovery_hint_codes"] == []
        assert lane["runtime_action"] == "none"
        assert lane["external_skill_activation_allowed"] is False
        assert lane["raw_source_urls_exported"] is False
    assert len(output["discovery_checklist"]) == 4
    assert {entry["capability"] for entry in output["discovery_checklist"]} == {"skill_route_discovery"}
    assert {entry["allowed_local_lane"] for entry in output["discovery_checklist"]} == {
        "code_patch",
        "config",
        "documentation",
        "test",
    }
    assert all(
        entry["local_artifact_contract"]["proposal_kind"] == entry["allowed_local_lane"]
        for entry in output["discovery_checklist"]
    )
    assert all(entry["required_local_artifact_proof"] for entry in output["discovery_checklist"])
    assert all(entry["local_artifact_contract"]["target_paths"] for entry in output["discovery_checklist"])
    assert all(entry["local_artifact_contract"]["local_only"] is True for entry in output["discovery_checklist"])
    assert all(
        entry["local_artifact_contract"]["external_skill_code_allowed"] is False
        for entry in output["discovery_checklist"]
    )
    assert all(
        entry["inspection_requirements"] == skill_route_discovery_inspection_requirements(entry["allowed_local_lane"])
        for entry in output["discovery_checklist"]
    )
    assert {entry["runtime_action"] for entry in output["discovery_checklist"]} == {"none"}
    assert all(entry["source_url_hash"] for entry in output["discovery_checklist"])
    assert all(entry["external_skill_activation_allowed"] is False for entry in output["discovery_checklist"])
    assert all(
        entry["required_tests"] == skill_route_discovery_preactivation_validation_commands()
        for entry in output["discovery_checklist"]
    )
    assert {entry["preactivation_harness"] for entry in output["discovery_checklist"]} == {"agent_harness_eval_lane"}
    assert all(entry["external_harness_execution_allowed"] is False for entry in output["discovery_checklist"])
    assert all(
        entry["rollback_note"] == "record rollback ref and artifact before applying local source changes"
        for entry in output["discovery_checklist"]
    )
    assert all(entry["raw_source_url_exported"] is False for entry in output["discovery_checklist"])
    assert {lane["runtime_action"] for lane in output["proposal_lanes"]} == {"none"}
    assert {tuple(lane["route_profiles"]) for lane in output["proposal_lanes"]} == {("codex_workflow_gate",)}
    assert {lane["evidence_url_count"] for lane in output["proposal_lanes"]} == {3}
    assert all(lane["evidence_url_hashes"] for lane in output["proposal_lanes"])
    assert output["privacy"] == {
        "raw_source_urls_exported": False,
        "source_urls_hashed": True,
        "raw_evidence_urls_exported": False,
        "evidence_urls_hashed": True,
        "raw_related_source_urls_exported": False,
        "runtime_actions_executed": False,
    }
    assert output["local_lane_intake"]["status"] == "ready"
    assert output["local_lane_intake"]["decision"] == "validate_bounded_local_lanes"
    assert output["local_lane_intake"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert output["local_lane_intake"]["lane_count"] == 4
    assert output["local_lane_intake"]["evidence_tier"] == "specific_route_or_validation_evidence"
    assert output["local_lane_intake"]["activation_decision"] == "ready_for_local_proposal_activation"
    assert output["local_lane_intake"]["blocked_discovery_actions"] == [
        "clone_and_run",
        "delete_local_skill",
        "enable",
        "execute",
        "install",
        "run",
    ]
    assert output["local_lane_intake"]["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "single_or_independent_sources",
        "candidate_source_count": 1,
        "related_source_count": 0,
        "fork_or_mirror_lineage_collapsed": False,
    }
    assert output["local_lane_intake"]["runtime_action_allowed"] is False
    assert output["local_lane_intake"]["external_skill_activation_allowed"] is False
    assert output["local_lane_intake"]["external_skill_code_allowed"] is False
    assert output["local_lane_intake"]["raw_evidence_exported"] is False
    assert output["local_lane_intake"]["raw_source_urls_exported"] is False
    assert output["local_lane_intake"]["raw_target_paths_exported"] is False
    assert [row["proposal_kind"] for row in output["local_lane_intake"]["lane_rows"]] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    for row in output["local_lane_intake"]["lane_rows"]:
        assert row["candidate_count"] == 1
        assert row["candidate_name_hashes"] == [stable_text_hash("codex-fable5")]
        assert row["source_hashes"] == [stable_text_hash("https://github.com/baskduf/FableCodex")]
        assert row["evidence_item_id_count"] == 3
        assert row["target_path_hashes"]
        assert row["inspection_requirements"] == skill_route_discovery_inspection_requirements(row["proposal_kind"])
        assert row["required_validation"] == skill_route_discovery_preactivation_validation_commands()
        assert row["provider_runtime_control"] == skill_route_discovery_provider_runtime_control(
            activation_ready=True,
            recovery_hint_codes=[],
        )
        assert row["local_validation_required"] is True
        assert row["activation_ready"] is True
        assert row["activation_blockers"] == []
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_skill_code_allowed"] is False
        assert row["raw_source_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
    assert output["evidence_lane_matrix"]["controller_surface"] == "skill_route_discovery_evidence_lane_matrix"
    assert output["evidence_lane_matrix"]["status"] == "ready"
    assert output["evidence_lane_matrix"]["decision"] == "map_external_evidence_to_bounded_local_lanes"
    assert output["evidence_lane_matrix"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert output["evidence_lane_matrix"]["candidate_count"] == 1
    assert output["evidence_lane_matrix"]["lane_count"] == 4
    assert output["evidence_lane_matrix"]["evidence_tier"] == "specific_route_or_validation_evidence"
    assert output["evidence_lane_matrix"]["activation_decision"] == "ready_for_local_proposal_activation"
    assert output["evidence_lane_matrix"]["rows_bounded"] is True
    assert output["evidence_lane_matrix"]["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "single_or_independent_sources",
        "candidate_source_count": 1,
        "related_source_count": 0,
        "fork_or_mirror_lineage_collapsed": False,
    }
    assert output["evidence_lane_matrix"]["blocked_discovery_actions"] == [
        "clone_and_run",
        "delete_local_skill",
        "enable",
        "execute",
        "install",
        "run",
    ]
    assert output["evidence_lane_matrix"]["diagnostics"] == []
    matrix_row = output["evidence_lane_matrix"]["rows"][0]
    assert matrix_row["candidate_name_hash"] == stable_text_hash("codex-fable5")
    assert matrix_row["source_hash"] == stable_text_hash("https://github.com/baskduf/FableCodex")
    assert matrix_row["route_profiles"] == ["codex_workflow_gate"]
    assert matrix_row["local_lanes"] == ["code_patch", "config", "documentation", "test"]
    assert matrix_row["lanes_bounded"] is True
    assert matrix_row["evidence_item_ids"] == [
        "fablecodex-issue-15",
        "fablecodex-issue-18",
        "fablecodex-repo",
    ]
    assert matrix_row["evidence_url_count"] == 3
    assert set(matrix_row["evidence_url_hashes"]) == {
        stable_text_hash("https://github.com/baskduf/FableCodex"),
        stable_text_hash("https://github.com/baskduf/FableCodex/issues/15"),
        stable_text_hash("https://github.com/baskduf/FableCodex/issues/18"),
    }
    assert matrix_row["downgraded_lane_count"] == 0
    assert matrix_row["rejected"] is False
    assert matrix_row["blocked_requested_action_count"] == 0
    assert matrix_row["runtime_action"] == "none"
    assert matrix_row["local_validation_required"] is True
    assert matrix_row["external_skill_activation_allowed"] is False
    assert matrix_row["external_skill_code_allowed"] is False
    assert matrix_row["raw_source_url_exported"] is False
    assert matrix_row["raw_evidence_urls_exported"] is False
    assert matrix_row["raw_upstream_body_exported"] is False
    assert output["evidence_lane_matrix"]["local_validation_required"] is True
    assert output["evidence_lane_matrix"]["body_free"] is True
    assert output["evidence_lane_matrix"]["runtime_action_allowed"] is False
    assert output["evidence_lane_matrix"]["external_skill_activation_allowed"] is False
    assert output["evidence_lane_matrix"]["external_skill_code_allowed"] is False
    assert output["evidence_lane_matrix"]["external_harness_execution_allowed"] is False
    assert output["evidence_lane_matrix"]["provider_runtime_launch_allowed"] is False
    assert output["evidence_lane_matrix"]["remote_execution_allowed"] is False
    assert output["evidence_lane_matrix"]["raw_evidence_exported"] is False
    assert output["evidence_lane_matrix"]["raw_source_urls_exported"] is False
    assert output["evidence_lane_matrix"]["raw_evidence_urls_exported"] is False
    assert output["evidence_lane_matrix"]["raw_upstream_body_exported"] is False
    assert output["route_triage_plan"]["controller_surface"] == "skill_route_discovery_route_triage"
    assert output["route_triage_plan"]["status"] == "ready"
    assert output["route_triage_plan"]["decision"] == "triage_bounded_lanes_to_local_artifacts"
    assert output["route_triage_plan"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert output["route_triage_plan"]["lane_count"] == 4
    assert output["route_triage_plan"]["lanes_bounded"] is True
    assert output["route_triage_plan"]["evidence_tier"] == "specific_route_or_validation_evidence"
    assert output["route_triage_plan"]["activation_decision"] == "ready_for_local_proposal_activation"
    assert output["route_triage_plan"]["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "single_or_independent_sources",
        "candidate_source_count": 1,
        "related_source_count": 0,
        "fork_or_mirror_lineage_collapsed": False,
    }
    assert [row["proposal_kind"] for row in output["route_triage_plan"]["rows"]] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    expected_triage_reasons = {
        "code_patch": "change only local classifier, harness, or controller behavior",
        "config": "register bounded route policy or proposal mapping",
        "documentation": "record route lesson and operator acceptance criteria",
        "test": "replay route evidence through local regression coverage",
    }
    for row in output["route_triage_plan"]["rows"]:
        assert row["triage_reason"] == expected_triage_reasons[row["proposal_kind"]]
        assert row["candidate_count"] == 1
        assert row["route_profiles"] == ["codex_workflow_gate"]
        assert row["source_hashes"] == [stable_text_hash("https://github.com/baskduf/FableCodex")]
        assert row["evidence_item_id_count"] == 3
        assert row["target_path_hashes"]
        assert row["local_artifact_contract"]["proposal_kind"] == row["proposal_kind"]
        assert row["local_artifact_contract"]["local_only"] is True
        assert row["inspection_requirements"] == skill_route_discovery_inspection_requirements(row["proposal_kind"])
        assert row["required_validation"] == skill_route_discovery_preactivation_validation_commands()
        assert row["activation_ready"] is True
        assert row["local_artifact_proof_ready"] is True
        assert row["activation_blockers"] == []
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_skill_code_allowed"] is False
        assert row["raw_evidence_exported"] is False
        assert row["raw_source_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
    assert output["route_triage_plan"]["local_validation_required"] is True
    assert output["route_triage_plan"]["body_free"] is True
    assert output["route_triage_plan"]["runtime_action_allowed"] is False
    assert output["route_triage_plan"]["external_skill_activation_allowed"] is False
    assert output["route_triage_plan"]["external_skill_code_allowed"] is False
    assert output["route_triage_plan"]["raw_evidence_exported"] is False
    assert output["route_triage_plan"]["raw_source_urls_exported"] is False
    assert output["route_triage_plan"]["raw_target_paths_exported"] is False
    assert output["route_profile_review"] == {
        "controller_surface": "skill_route_discovery_route_profile_review",
        "status": "ready",
        "decision": "review_profile_contracts_before_local_activation",
        "profile_count": 1,
        "profiles": ["codex_workflow_gate"],
        "rows": [
            {
                "route_profile": "codex_workflow_gate",
                "proposal_kinds": ["code_patch", "config", "documentation", "test"],
                "candidate_count": 1,
                "evidence_item_id_count": 3,
                "recognition_signals": [
                    "codex_or_agent_workflow_language",
                    "evidence_gate_or_review_ledger",
                    "verification_or_coverage_habit",
                ],
                "expected_metadata": [
                    "selected_digest_item_ids",
                    "body_free_workflow_summary",
                    "local_gate_or_test_target",
                ],
                "metadata_coverage": {
                    "profile": "codex_workflow_gate",
                    "expected_count": 3,
                    "satisfied_count": 3,
                    "missing_count": 0,
                    "satisfied_metadata": [
                        "selected_digest_item_ids",
                        "body_free_workflow_summary",
                        "local_gate_or_test_target",
                    ],
                    "missing_metadata": [],
                    "evidence_record_count": 3,
                    "evidence_item_id_count": 3,
                    "local_artifact_proof_count": 4,
                    "source_hashes": [
                        stable_text_hash("https://github.com/baskduf/FableCodex/issues/18"),
                        stable_text_hash("https://github.com/baskduf/FableCodex"),
                        stable_text_hash("https://github.com/baskduf/FableCodex/issues/15"),
                    ],
                    "evidence_text_hashes": [
                        stable_text_hash(
                            "Add user-facing FableCodex workflow examples "
                            "Issue requests workflow examples with prompt text, expected workflow, command evidence "
                            "snippets, README links, and honest limitation notes. documentation workflow examples"
                        ),
                        stable_text_hash(
                            "Strengthen localized README drift checks Issue requests localized README drift checks "
                            "for release tags, limitation warnings, command parity, and exact failing documentation "
                            "evidence. documentation test workflow"
                        ),
                        stable_text_hash(
                            "codex-fable5 FableCodex Codex skill and workflow package with evidence gates, review "
                            "ledgers, verification habits, localized documentation, and plugin routing docs. "
                            "codex agent-skills workflow verification"
                        ),
                    ],
                    "complete": True,
                    "body_free": True,
                    "raw_evidence_exported": False,
                    "raw_source_urls_exported": False,
                    "raw_upstream_body_exported": False,
                },
                "metadata_complete": True,
                "safe_local_tests": [
                    "pytest tests/test_skill_routing.py -q",
                    "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
                    "pytest tests/test_harness_eval.py -q -k proposal_interpretation",
                ],
                "rejection_conditions": [
                    "upstream_workflow_install_requested",
                    "url_or_repository_name_used_as_proposal_evidence_ref",
                    "readme_claim_treated_as_local_gate_parity",
                ],
                "local_lane_contracts": [
                    {
                        "proposal_kind": "code_patch",
                        "target_path_hashes": [
                            stable_text_hash("src/blackhole_agent/skill_routing.py"),
                            stable_text_hash("src/blackhole_agent/harness_eval.py"),
                        ],
                        "target_count": 2,
                        "required_local_artifact_proof": {
                            "changed_file_review": True,
                            "focused_local_validation": True,
                            "rollback_artifact": True,
                            "review_note": True,
                        },
                        "runtime_action": "none",
                        "external_skill_activation_allowed": False,
                        "external_skill_code_allowed": False,
                        "raw_target_paths_exported": False,
                    },
                    {
                        "proposal_kind": "config",
                        "target_path_hashes": [
                            stable_text_hash("src/blackhole_agent/proposal_synthesis.py"),
                        ],
                        "target_count": 1,
                        "required_local_artifact_proof": {
                            "changed_file_review": True,
                            "focused_local_validation": True,
                            "rollback_artifact": True,
                            "review_note": True,
                        },
                        "runtime_action": "none",
                        "external_skill_activation_allowed": False,
                        "external_skill_code_allowed": False,
                        "raw_target_paths_exported": False,
                    },
                    {
                        "proposal_kind": "documentation",
                        "target_path_hashes": [stable_text_hash("docs/skill-route-discovery.md")],
                        "target_count": 1,
                        "required_local_artifact_proof": {
                            "changed_file_review": True,
                            "focused_local_validation": True,
                            "rollback_artifact": True,
                            "review_note": True,
                        },
                        "runtime_action": "none",
                        "external_skill_activation_allowed": False,
                        "external_skill_code_allowed": False,
                        "raw_target_paths_exported": False,
                    },
                    {
                        "proposal_kind": "test",
                        "target_path_hashes": [
                            stable_text_hash("tests/test_skill_routing.py"),
                            stable_text_hash("tests/test_harness_eval.py"),
                        ],
                        "target_count": 2,
                        "required_local_artifact_proof": {
                            "changed_file_review": True,
                            "focused_local_validation": True,
                            "rollback_artifact": True,
                            "review_note": True,
                        },
                        "runtime_action": "none",
                        "external_skill_activation_allowed": False,
                        "external_skill_code_allowed": False,
                        "raw_target_paths_exported": False,
                    },
                ],
                "uncertainty_reasons": [
                    "missing_detail_risk",
                    "unvalidated_external_skill_evidence",
                ],
                "runtime_action": "none",
                "local_validation_required": True,
                "local_artifact_proof_required": True,
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "raw_evidence_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        ],
        "evidence_tier": "specific_route_or_validation_evidence",
        "source_lineage": {
            "body_free": True,
            "lineage_mode": "single_or_independent_sources",
            "candidate_source_count": 1,
            "related_source_count": 0,
            "fork_or_mirror_lineage_collapsed": False,
        },
        "diagnostics": [],
        "body_free": True,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert output["activation_manifest"]["controller_surface"] == "skill_route_discovery_activation_manifest"
    assert output["activation_manifest"]["status"] == "ready"
    assert output["activation_manifest"]["decision"] == "manifest_bounded_local_lanes"
    assert output["activation_manifest"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert output["activation_manifest"]["lane_count"] == 4
    assert (
        output["activation_manifest"]["required_validation"]
        == skill_route_discovery_preactivation_validation_commands()
    )
    assert output["activation_manifest"]["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert output["activation_manifest"]["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "single_or_independent_sources",
        "candidate_source_count": 1,
        "related_source_count": 0,
        "fork_or_mirror_lineage_collapsed": False,
    }
    assert output["activation_manifest"]["recovery_hint_codes"] == []
    assert output["activation_manifest"]["diagnostics"] == []
    assert output["activation_manifest"]["evidence_ref_mode"] == "selected_item_ids_only"
    assert output["activation_manifest"]["local_validation_required"] is True
    assert output["activation_manifest"]["runtime_action_allowed"] is False
    assert output["activation_manifest"]["external_skill_activation_allowed"] is False
    assert output["activation_manifest"]["external_harness_execution_allowed"] is False
    assert output["activation_manifest"]["provider_runtime_launch_allowed"] is False
    assert output["activation_manifest"]["remote_execution_allowed"] is False
    assert output["activation_manifest"]["raw_evidence_urls_exported"] is False
    assert output["activation_manifest"]["raw_source_urls_exported"] is False
    assert output["activation_manifest"]["raw_target_paths_exported"] is False
    assert output["activation_manifest"]["raw_upstream_body_exported"] is False
    assert [row["proposal_kind"] for row in output["activation_manifest"]["manifest_lanes"]] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    for row in output["activation_manifest"]["manifest_lanes"]:
        assert row["route_profiles"] == ["codex_workflow_gate"]
        assert row["evidence_refs"] == [
            "fablecodex-issue-15",
            "fablecodex-issue-18",
            "fablecodex-repo",
        ]
        assert row["candidate_count"] == 1
        assert row["candidate_source_hashes"] == [stable_text_hash("https://github.com/baskduf/FableCodex")]
        assert row["target_path_hashes"]
        assert row["local_artifact_proof_ready"] is True
        assert row["required_validation"] == skill_route_discovery_preactivation_validation_commands()
        assert row["provider_runtime_next_action"] == "run_provider_runtime_replay_before_promotion"
        assert row["activation_ready"] is True
        assert row["activation_blockers"] == []
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["raw_source_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False
    assert output["capability_window_completion"] == {
        "controller_surface": "skill_route_discovery_capability_window_completion",
        "status": "ready",
        "decision": "complete_slice_for_supervisor_handoff",
        "theme": "skill-route-discovery",
        "capability_slice": (
            "Convert skill and route evidence into bounded local lanes that can be validated before activation."
        ),
        "current_pass": 4,
        "total_passes": 4,
        "planned_window_complete": True,
        "anchoring_proposal_count": 4,
        "anchoring_proposal_hashes": [
            stable_text_hash("proposal_skill_route_discovery_compass"),
            stable_text_hash("proposal_skill_route_discovery_threejs_game"),
            stable_text_hash("proposal_skill_route_discovery_fablecodex"),
            stable_text_hash("proposal_unified_skill_route_regression"),
        ],
        "evidence_url_count": 3,
        "evidence_url_hashes": [
            stable_text_hash("https://github.com/dongshuyan/compass-skills"),
            stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
            stable_text_hash("https://github.com/baskduf/FableCodex"),
        ],
        "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
        "proposal_kinds": ["code_patch", "config", "documentation", "test"],
        "route_profiles": ["codex_workflow_gate"],
        "lane_count": 4,
        "route_profile_count": 1,
        "manifest_ready": True,
        "profile_review_ready": True,
        "operator_handoff_ready": True,
        "supervisor_ready": True,
        "provider_runtime_replay_ready": True,
        "completion_handoff": {
            "status": "ready",
            "decision": "complete_slice_for_supervisor_handoff",
            "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
            "final_pass_required": True,
            "final_pass_observed": True,
            "selected_evidence_ref_count": 3,
            "selected_evidence_refs": [
                "fablecodex-issue-15",
                "fablecodex-issue-18",
                "fablecodex-repo",
            ],
            "completion_blockers": [],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "provider_runtime_replay_commands": [
                "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
            ],
            "local_validation_required": True,
            "runtime_action_allowed": False,
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_evidence_urls_exported": False,
            "raw_source_urls_exported": False,
            "raw_upstream_body_exported": False,
        },
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "diagnostics": [],
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert "https://github.com/baskduf/FableCodex" not in serialized


def test_skill_route_discovery_evidence_lane_matrix_bounds_multi_profile_candidates():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_multi_profile_matrix_inline.json"
    input_payload = {
        "task_id": "skill-route-discovery-multi-profile-matrix",
        "source_kind": "candidates",
        "candidates": [
            {
                "name": "codex-fable5",
                "source_url": "https://github.com/baskduf/FableCodex",
                "evidence_summary": (
                    "Codex skill and workflow package with evidence gates, review ledgers, "
                    "verification habits, and plugin routing docs."
                ),
                "candidate_lanes": ["documentation", "test", "runtime_execution"],
            },
            {
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "evidence_summary": (
                    "Personal alignment skill ecosystem for AI agents with task routing, "
                    "profiles, local memory notes, and validation evidence."
                ),
                "candidate_lanes": ["config", "test", "install"],
            },
            {
                "name": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "evidence_summary": (
                    "Director skill package for Three.js games with gameplay, graphics, "
                    "UI, debug, QA, scaffold helpers, and install commands."
                ),
                "candidate_lanes": ["documentation", "code_patch", "execute"],
            },
        ],
    }

    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        input_payload,
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "degraded"
    assert output["failure_mode"] == "unsupported_lanes_downgraded"
    assert output["activation_gate"]["decision"] == "review_degraded_lane_before_activation"
    assert output["lane_map"]["proposal_kinds"] == ["code_patch", "config", "documentation", "test"]

    matrix = output["evidence_lane_matrix"]
    assert matrix["controller_surface"] == "skill_route_discovery_evidence_lane_matrix"
    assert matrix["status"] == "review"
    assert matrix["decision"] == "review_evidence_lane_mapping_before_activation"
    assert matrix["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert matrix["candidate_count"] == 3
    assert matrix["lane_count"] == 6
    assert matrix["rows_bounded"] is True
    assert matrix["activation_decision"] == "review_degraded_lane_before_activation"
    assert matrix["diagnostics"] == []
    assert matrix["runtime_action_allowed"] is False
    assert matrix["external_skill_activation_allowed"] is False
    assert matrix["external_skill_code_allowed"] is False
    assert matrix["raw_source_urls_exported"] is False
    assert matrix["raw_evidence_urls_exported"] is False
    assert matrix["raw_upstream_body_exported"] is False

    rows_by_source = {row["source_hash"]: row for row in matrix["rows"]}
    fable_row = rows_by_source[stable_text_hash("https://github.com/baskduf/FableCodex")]
    compass_row = rows_by_source[stable_text_hash("https://github.com/dongshuyan/compass-skills")]
    threejs_row = rows_by_source[stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")]

    assert fable_row["route_profiles"] == ["codex_workflow_gate"]
    assert fable_row["local_lanes"] == ["documentation", "test"]
    assert fable_row["downgraded_lanes"] == ["runtime_execution"]
    assert compass_row["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert compass_row["local_lanes"] == ["config", "test"]
    assert compass_row["downgraded_lanes"] == ["install"]
    assert threejs_row["route_profiles"] == ["game_frontend_workflow"]
    assert threejs_row["local_lanes"] == ["code_patch", "documentation"]
    assert threejs_row["downgraded_lanes"] == ["execute"]

    for row in matrix["rows"]:
        assert row["lanes_bounded"] is True
        assert row["runtime_action"] == "none"
        assert row["local_validation_required"] is True
        assert row["external_skill_activation_allowed"] is False
        assert row["external_skill_code_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized


def test_skill_route_discovery_capability_window_reports_in_progress_before_final_pass():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_fablecodex.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["capability_window"]["current_pass"] = 3
    input_payload["capability_window"]["total_passes"] = 4

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )

    completion = output["capability_window_completion"]
    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert completion["status"] == "in_progress"
    assert completion["decision"] == "continue_capability_window_before_completion"
    assert completion["current_pass"] == 3
    assert completion["total_passes"] == 4
    assert completion["planned_window_complete"] is False
    assert completion["diagnostics"] == ["capability_window_not_at_final_pass"]
    assert completion["manifest_ready"] is True
    assert completion["profile_review_ready"] is True
    assert completion["operator_handoff_ready"] is True
    assert completion["supervisor_ready"] is True
    assert completion["provider_runtime_replay_ready"] is True
    assert completion["completion_handoff"]["status"] == "in_progress"
    assert (
        completion["completion_handoff"]["supervisor_next_action"]
        == "continue_capability_window_before_completion"
    )
    assert completion["completion_handoff"]["final_pass_required"] is True
    assert completion["completion_handoff"]["final_pass_observed"] is False
    assert completion["completion_handoff"]["completion_blockers"] == [
        "capability_window_not_at_final_pass"
    ]
    assert completion["completion_handoff"]["selected_evidence_refs"] == [
        "fablecodex-issue-15",
        "fablecodex-issue-18",
        "fablecodex-repo",
    ]
    assert completion["completion_handoff"]["runtime_action_allowed"] is False
    assert completion["completion_handoff"]["raw_evidence_urls_exported"] is False
    assert completion["proposal_kinds"] == ["code_patch", "config", "documentation", "test"]
    assert completion["runtime_action_allowed"] is False
    assert completion["external_skill_activation_allowed"] is False
    assert completion["provider_runtime_launch_allowed"] is False
    assert completion["remote_execution_allowed"] is False
    assert completion["raw_evidence_urls_exported"] is False
    assert completion["raw_source_urls_exported"] is False
    assert completion["raw_upstream_body_exported"] is False


def test_skill_route_discovery_capability_window_handoff_reports_final_blockers():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_fablecodex.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["local_artifact_proofs"] = [
        proof for proof in input_payload["local_artifact_proofs"] if proof["proposal_kind"] != "test"
    ]

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )

    completion = output["capability_window_completion"]
    handoff = completion["completion_handoff"]
    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert completion["status"] == "blocked"
    assert completion["decision"] == "continue_or_replay_before_completion"
    assert handoff["status"] == "blocked"
    assert handoff["supervisor_next_action"] == "replay_or_repair_before_supervisor_handoff"
    assert handoff["final_pass_required"] is True
    assert handoff["final_pass_observed"] is True
    assert handoff["selected_evidence_ref_count"] == 3
    assert handoff["selected_evidence_refs"] == [
        "fablecodex-issue-15",
        "fablecodex-issue-18",
        "fablecodex-repo",
    ]
    assert "activation_manifest_not_ready" in handoff["completion_blockers"]
    assert "operator_handoff_not_ready" in handoff["completion_blockers"]
    assert handoff["runtime_action_allowed"] is False
    assert handoff["external_skill_activation_allowed"] is False
    assert handoff["provider_runtime_launch_allowed"] is False
    assert handoff["remote_execution_allowed"] is False
    assert handoff["raw_evidence_urls_exported"] is False
    assert handoff["raw_source_urls_exported"] is False
    assert handoff["raw_upstream_body_exported"] is False


def test_skill_route_discovery_lane_reports_fork_lineage_as_body_free_metadata():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_fork_lineage.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["registry"]["duplicate_summary_count"] == 1
    assert output["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "collapsed_fork_or_mirror",
        "candidate_source_count": 1,
        "candidate_source_hashes": [stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")],
        "related_source_count": 2,
        "related_source_hashes": sorted(
            [
                stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
                stable_text_hash("https://github.com/pretinhuu1-boop/threejs-game-skills"),
            ]
        ),
        "duplicate_summary_count": 1,
        "evidence_item_id_count": 0,
        "fork_or_mirror_lineage_collapsed": True,
        "raw_source_urls_exported": False,
        "raw_related_source_urls_exported": False,
    }
    assert output["supervisor_readiness"]["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "collapsed_fork_or_mirror",
        "candidate_source_count": 1,
        "related_source_count": 2,
        "duplicate_summary_count": 1,
        "fork_or_mirror_lineage_collapsed": True,
        "raw_source_urls_exported": False,
        "raw_related_source_urls_exported": False,
    }
    assert output["route_profile_review"]["status"] == "ready"
    assert output["route_profile_review"]["profiles"] == ["game_frontend_workflow"]
    profile_row = output["route_profile_review"]["rows"][0]
    assert profile_row["recognition_signals"] == [
        "threejs_or_browser_game_language",
        "director_or_specialist_skill_bundle",
        "qa_browser_screenshot_or_canvas_validation_language",
    ]
    assert profile_row["rejection_conditions"] == [
        "upstream_scaffold_or_browser_checker_requested",
        "credential_probe_or_provider_launch_requested",
        "asset_generation_requested_without_local_capability_path",
    ]
    assert [contract["proposal_kind"] for contract in profile_row["local_lane_contracts"]] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    assert all(contract["raw_target_paths_exported"] is False for contract in profile_row["local_lane_contracts"])
    assert profile_row["runtime_action"] == "none"
    assert profile_row["raw_source_urls_exported"] is False
    assert profile_row["raw_target_paths_exported"] is False
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized
    assert "https://github.com/pretinhuu1-boop/threejs-game-skills" not in serialized


def test_skill_route_discovery_profile_review_reports_missing_metadata_before_activation():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-profile-metadata-missing",
            "source_kind": "evidence_items",
            "evidence_items": [
                {
                    "item_kind": "repository",
                    "name": "codex-fable5",
                    "source_url": "https://github.com/baskduf/FableCodex",
                    "title": "FableCodex",
                    "summary": "Plugin package.",
                    "topics": ["codex"],
                    "route_hints": ["skill_route_discovery"],
                    "suggested_lanes": ["documentation"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_profile_metadata_missing_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    review = output["route_profile_review"]
    assert review["status"] == "review"
    assert review["decision"] == "resolve_profile_contract_diagnostics"
    assert review["diagnostics"] == [
        "codex_workflow_gate:metadata_missing:selected_digest_item_ids",
        "codex_workflow_gate:metadata_missing:local_gate_or_test_target",
    ]
    coverage = review["rows"][0]["metadata_coverage"]
    assert coverage["complete"] is False
    assert coverage["satisfied_metadata"] == ["body_free_workflow_summary"]
    assert coverage["missing_metadata"] == [
        "selected_digest_item_ids",
        "local_gate_or_test_target",
    ]
    assert coverage["evidence_record_count"] == 1
    assert coverage["evidence_item_id_count"] == 0
    assert coverage["local_artifact_proof_count"] == 0
    assert coverage["body_free"] is True
    assert coverage["raw_evidence_exported"] is False
    assert coverage["raw_source_urls_exported"] is False
    assert coverage["raw_upstream_body_exported"] is False
    assert review["rows"][0]["metadata_complete"] is False
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "Plugin package" not in serialized


def test_skill_route_discovery_activity_signal_panel_bounds_compass_push_event():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-compass-push",
            "source_kind": "evidence_items",
            "evidence_items": [
                {
                    "item_id": "compass-push",
                    "item_kind": "repository",
                    "name": "compass-skills",
                    "source_url": "https://github.com/dongshuyan/compass-skills",
                    "title": "COMPASS Skills PushEvent",
                    "summary": (
                        "PushEvent movement for a skill ecosystem with task clarification, local memory, "
                        "handoff prompts, collaboration profiles, and validation notes."
                    ),
                    "discovery_event_kind": "PushEvent",
                    "route_hints": ["skill_route_discovery"],
                    "topics": ["agent-skills", "workflow", "validation"],
                    "suggested_lanes": ["documentation", "config", "test", "code_patch", "execute"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_compass_push_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["lane_map"]["proposal_lane_count"] == 4
    assert {lane["discovery_event_kind"] for lane in output["proposal_lanes"]} == {"push"}
    assert {lane["discovery_event_effect"] for lane in output["proposal_lanes"]} == {"record_only"}
    assert {lane["proposal_kind"] for lane in output["proposal_lanes"]} == {
        "documentation",
        "config",
        "test",
        "code_patch",
    }
    assert {lane["runtime_action"] for lane in output["proposal_lanes"]} == {"none"}
    assert output["activity_signal_panel"]["controller_surface"] == "skill_route_discovery_activity_signal_panel"
    assert output["activity_signal_panel"]["status"] == "ready"
    assert output["activity_signal_panel"]["decision"] == "interpret_activity_as_bounded_validation_pressure"
    assert output["activity_signal_panel"]["event_kinds"] == ["push"]
    assert output["activity_signal_panel"]["push_signal_count"] == 4
    assert output["activity_signal_panel"]["lane_count"] == 4
    assert output["activity_signal_panel"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert output["activity_signal_panel"]["diagnostics"] == []
    assert output["activity_signal_panel"]["runtime_action_allowed"] is False
    assert output["activity_signal_panel"]["external_skill_activation_allowed"] is False
    assert output["activity_signal_panel"]["raw_source_urls_exported"] is False
    for row in output["activity_signal_panel"]["rows"]:
        assert row["event_kind"] == "push"
        assert row["proposal_kind"] in {"documentation", "config", "test", "code_patch"}
        assert row["route_profiles"] == ["skill_ecosystem_state_handoff"]
        assert row["event_effects"] == ["record_only"]
        assert row["allowed_local_lane"] is True
        assert row["activity_interpretation"] == "movement_supports_local_validation_lane"
        assert row["required_validation"] == skill_route_discovery_preactivation_validation_commands()
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["raw_source_urls_exported"] is False
        assert row["raw_evidence_exported"] is False
    assert "https://github.com/dongshuyan/compass-skills" not in serialized


def test_skill_route_discovery_lane_requires_local_artifact_proof_for_handoff():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-clean-without-proof",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "compass-skills",
                    "source_url": "https://github.com/dongshuyan/compass-skills",
                    "evidence_summary": (
                        "Specific skill ecosystem with task clarification, local memory, handoff prompts, "
                        "profile state, route metadata, and validation notes."
                    ),
                    "candidate_lanes": ["documentation"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_missing_artifact_proof_inline.json",
    )

    assert output["route_status"] == "passed"
    assert output["activation_gate"]["decision"] == "ready_for_local_proposal_activation"
    assert output["implementation_intake_preflight"]["status"] == "blocked"
    assert output["implementation_intake_preflight"]["diagnostics"] == [
        "activation_lanes[0].local_artifact_proof_not_ready"
    ]
    assert output["supervisor_readiness"]["decision"] == "blocked_before_supervisor_promotion"
    assert output["supervisor_readiness"]["reason"] == "local_artifact_proof_not_ready"
    assert output["supervisor_readiness"]["local_artifact_proof_present"] is False
    assert output["supervisor_readiness"]["local_artifact_proof_ready"] is False
    assert output["operator_handoff"]["status"] == "blocked"
    assert output["operator_handoff"]["local_artifact_proof_ready"] is False
    assert output["route_profile_review"]["profiles"] == ["skill_ecosystem_state_handoff"]
    assert output["route_profile_review"]["rows"][0]["local_lane_contracts"] == [
        {
            "proposal_kind": "documentation",
            "target_path_hashes": [stable_text_hash("docs/skill-route-discovery.md")],
            "target_count": 1,
            "required_local_artifact_proof": {
                "changed_file_review": True,
                "focused_local_validation": True,
                "rollback_artifact": True,
                "review_note": True,
            },
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "raw_target_paths_exported": False,
        }
    ]
    assert output["route_profile_review"]["rows"][0]["local_artifact_proof_required"] is True
    assert output["route_triage_plan"]["status"] == "ready"
    assert output["route_triage_plan"]["decision"] == "triage_bounded_lanes_to_local_artifacts"
    assert output["route_triage_plan"]["rows"] == [
        {
            "proposal_kind": "documentation",
            "triage_reason": "record route lesson and operator acceptance criteria",
            "candidate_count": 1,
            "route_profiles": ["skill_ecosystem_state_handoff"],
            "source_hashes": [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
            "evidence_item_id_count": 0,
            "uncertainty_reasons": [
                "no_selected_digest_item_ids",
                "single_repository_level_source",
                "unvalidated_external_skill_evidence",
            ],
            "target_path_hashes": [stable_text_hash("docs/skill-route-discovery.md")],
            "local_artifact_contract": {
                "proposal_kind": "documentation",
                "target_paths": ["docs/skill-route-discovery.md"],
                "required_review_surface": "changed_files_and_validation",
                "local_only": True,
                "external_skill_code_allowed": False,
                "raw_upstream_body_allowed": False,
            },
            "inspection_requirements": skill_route_discovery_inspection_requirements("documentation"),
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "activation_ready": True,
            "local_artifact_proof_ready": False,
            "activation_blockers": [],
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "raw_evidence_exported": False,
            "raw_source_urls_exported": False,
            "raw_target_paths_exported": False,
        }
    ]
    assert output["operator_handoff"]["lane_rows"] == [
        {
            "proposal_kind": "documentation",
            "candidate_count": 1,
            "activation_ready": True,
            "local_artifact_proof_ready": False,
            "target_path_hashes": [stable_text_hash("docs/skill-route-discovery.md")],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "provider_runtime_replay_commands": [
                "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
            ],
            "provider_runtime_control": skill_route_discovery_provider_runtime_control(
                activation_ready=True,
                recovery_hint_codes=[],
            ),
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "raw_target_paths_exported": False,
            "raw_source_urls_exported": False,
        }
    ]


def test_skill_route_discovery_trust_boundary_requires_inspection_requirements():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-inspection-requirements",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "skill-route-doc",
                    "source_url": "https://github.com/example/skill-route-doc",
                    "candidate_lanes": ["documentation"],
                    "route_hints": ["skill_route_discovery"],
                    "disabled": True,
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_inspection_requirements_inline.json",
    )

    activation_lanes = [dict(output["activation_lanes"][0])]
    activation_lanes[0].pop("inspection_requirements")

    boundary = skill_route_discovery_preactivation_trust_boundary(
        output["proposal_lanes"],
        activation_lanes,
    )

    assert boundary["status"] == "blocked"
    assert boundary["diagnostics"] == ["activation_lanes[0].inspection_requirements_mismatch"]


def test_agent_harness_provider_registration_blocks_qwencode_without_local_config():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_harness_provider_registration_qwencode_missing_config.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "required_provider_config_missing"
    assert output["selected_harness"] == "single-file-function-agent"
    assert output["missing_required_config"] is True
    assert output["missing_config_reasons"] == [
        "missing_dependency:qwencode",
        "missing_env_key_hash:sha256:dfa09d06ce907c1b6e5e72a7dbc053a65677ea79ec00b03a32472f158c5f9cf2",
    ]
    assert output["activation_gate"] == {
        "controller_surface": "agent_harness_provider_registration",
        "activation_scope": "local_harness_provider_only",
        "decision": "blocked_before_activation",
        "reason": "required_provider_config_missing",
        "local_provider_registration_allowed": False,
        "provider_runtime_launch_allowed": False,
    }
    assert output["statuses"][0]["skip_reasons"] == [
        "missing_dependency:qwencode",
        "missing_env_key_hash:sha256:dfa09d06ce907c1b6e5e72a7dbc053a65677ea79ec00b03a32472f158c5f9cf2",
    ]
    assert output["statuses"][0]["required_env_key_hashes"] == [
        "sha256:dfa09d06ce907c1b6e5e72a7dbc053a65677ea79ec00b03a32472f158c5f9cf2"
    ]
    assert output["privacy"] == {
        "env_values_exported": False,
        "env_key_names_exported": False,
        "host_id_exported": False,
        "owner_values_exported": False,
        "provider_launched": False,
    }
    assert "QWENCODE_API_KEY" not in serialized


def test_agent_harness_provider_registration_blocks_host_owner_mismatch_before_success_state():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_harness_provider_registration_host_owner_mismatch.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "host_registration_owner_mismatch"
    assert output["selected_harness"] == "omnigent-host-cli"
    assert output["registration_state"]["owner_mismatch"] is True
    assert output["registration_state"]["registration_completed"] is False
    assert output["registration_state"]["connection_reported_success"] is True
    assert output["registration_state"]["success_state_allowed"] is False
    assert output["activation_gate"]["decision"] == "blocked_before_activation"
    assert output["activation_gate"]["local_provider_registration_allowed"] is False
    assert output["activation_gate"]["provider_runtime_launch_allowed"] is False
    assert output["recovery_hints"][0]["code"] == "host_registration_owner_mismatch"
    assert output["recovery_hints"][0]["value_recorded"] is False
    assert output["privacy"]["host_id_exported"] is False
    assert output["privacy"]["owner_values_exported"] is False
    assert "PRIVATE_HOST_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EXISTING_OWNER_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_AUTHENTICATED_OWNER_DO_NOT_EXPORT" not in serialized


def test_skill_route_discovery_lane_blocks_actionful_candidates():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-actionful",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "actionful-skill",
                    "source_url": "https://github.com/example/actionful-skill",
                    "candidate_lanes": ["documentation", "code_patch"],
                    "requested_actions": ["install"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_actionful_inline.json",
    )

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "rejected_candidates_present"
    assert output["registry"]["registry_status"] == "invalid_candidates_present"
    assert output["registry"]["invalid_candidate_count"] == 1
    assert output["lane_map"]["proposal_lane_count"] == 0
    assert output["discovery_checklist"] == []
    assert output["activation_gate"] == {
        "controller_surface": "skill_route_discovery_lane",
        "activation_scope": "local_proposal_only",
        "decision": "blocked_before_activation",
        "reason": "rejected_candidates_present",
        "local_proposal_activation_allowed": False,
        "external_skill_activation_allowed": False,
    }
    assert output["supervisor_readiness"]["decision"] == "blocked_before_supervisor_promotion"
    assert output["supervisor_readiness"]["reason"] == "rejected_candidates_present"
    assert output["supervisor_readiness"]["activation_lane_count"] == 0
    assert output["supervisor_readiness"]["ready_lane_count"] == 0
    assert output["supervisor_readiness"]["blocked_lane_count"] == 0
    assert output["implementation_intake_preflight"] == {
        "status": "blocked",
        "implementation_allowed": False,
        "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
        "proposal_kinds": [],
        "activation_lane_count": 0,
        "target_path_count": 0,
        "target_path_hashes": [],
        "changed_file_review_required": True,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_upstream_body_allowed": False,
        "raw_target_paths_exported": False,
        "diagnostics": [],
    }
    assert output["supervisor_readiness"]["recovery_hint_codes"] == ["skill_route_rejected_candidates_present"]
    assert output["operator_recovery_plan"]["decision"] == "blocked_recovery_required"
    assert output["operator_recovery_plan"]["reason"] == "rejected_candidates_present"
    assert output["operator_recovery_plan"]["recovery_required"] is True
    assert output["operator_recovery_plan"]["next_action"] == "resolve_recovery_steps_then_replay_skill_route_lane"
    assert (
        output["operator_recovery_plan"]["replay_commands"]
        == skill_route_discovery_preactivation_validation_commands()
    )
    assert output["operator_recovery_plan"]["recovery_hint_codes"] == ["skill_route_rejected_candidates_present"]
    assert output["operator_recovery_plan"]["recovery_hint_code_hashes"] == [
        stable_text_hash("skill_route_rejected_candidates_present")
    ]
    assert output["operator_recovery_plan"]["recovery_steps"][0]["code"] == "skill_route_rejected_candidates_present"
    assert output["operator_recovery_plan"]["recovery_steps"][0]["raw_evidence_exported"] is False
    assert output["operator_recovery_plan"]["recovery_steps"][0]["raw_source_urls_exported"] is False
    assert output["operator_recovery_plan"]["runtime_action_allowed"] is False
    assert output["operator_recovery_plan"]["external_skill_activation_allowed"] is False
    assert output["operator_recovery_plan"]["provider_runtime_launch_allowed"] is False
    assert output["operator_recovery_plan"]["remote_execution_allowed"] is False
    assert output["operator_recovery_plan"]["raw_evidence_exported"] is False
    assert output["operator_recovery_plan"]["raw_source_urls_exported"] is False
    assert output["local_lane_intake"] == {
        "status": "blocked",
        "decision": "no_bounded_local_lanes",
        "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
        "lane_count": 0,
        "lane_rows": [],
        "evidence_tier": "specific_route_or_validation_evidence",
        "activation_decision": "blocked_before_activation",
        "source_lineage": {
            "body_free": True,
            "lineage_mode": "single_or_independent_sources",
            "candidate_source_count": 1,
            "related_source_count": 0,
            "fork_or_mirror_lineage_collapsed": False,
        },
        "blocked_discovery_actions": [
            "clone_and_run",
            "delete_local_skill",
            "enable",
            "execute",
            "install",
            "run",
        ],
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
    }
    assert output["operator_handoff"] == {
        "status": "blocked",
        "decision": "hold_for_review_or_replay",
        "ready_lane_count": 0,
        "blocked_lane_count": 0,
        "local_artifact_proof_ready": False,
        "lane_rows": [],
        "implementation_intake_status": "blocked",
        "supervisor_decision": "blocked_before_supervisor_promotion",
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "provider_runtime_control": skill_route_discovery_provider_runtime_control(
            activation_ready=False,
            recovery_hint_codes=["skill_route_rejected_candidates_present"],
        ),
        "recovery_hint_codes": ["skill_route_rejected_candidates_present"],
        "source_lineage": {
            "body_free": True,
            "lineage_mode": "single_or_independent_sources",
            "candidate_source_count": 1,
            "related_source_count": 0,
            "fork_or_mirror_lineage_collapsed": False,
        },
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }
    assert output["operator_handoff"]["provider_runtime_control"]["next_action"] == (
        "resolve_recovery_hints_then_replay_provider_runtime_preflight"
    )
    assert output["operator_handoff"]["provider_runtime_control"]["recovery_hint_count"] == 1
    assert output["operator_handoff"]["provider_runtime_control"]["recovery_hint_code_hashes"] == [
        stable_text_hash("skill_route_rejected_candidates_present")
    ]
    assert output["supervisor_readiness"]["raw_evidence_exported"] is False
    assert output["privacy"]["runtime_actions_executed"] is False


def test_skill_route_discovery_lane_blocks_on_provider_runtime_replay_sample_without_exporting_bodies():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-provider-runtime-sample",
            "source_kind": "summaries",
            "summaries": [
                {
                    "name": "compass-skills",
                    "source_url": "https://github.com/dongshuyan/compass-skills",
                    "summary": "SKILL.md skill ecosystem with documentation, config metadata, validation, and local workflow helpers.",
                    "topics": ["agent-skills", "workflow", "skill.md"],
                    "suggested_lanes": ["documentation", "config", "test", "code_patch"],
                },
                {
                    "name": "threejs-game-skills",
                    "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                    "summary": "Agent skill director for Three.js game workflow, QA validation, and code helper routing.",
                    "topics": ["agent-skills", "threejs", "qa"],
                    "suggested_lanes": ["documentation", "test", "code_patch"],
                },
                {
                    "name": "FableCodex",
                    "source_url": "https://github.com/baskduf/FableCodex",
                    "summary": "Codex workflow skill package with evidence gates, review ledgers, and verification habits.",
                    "topics": ["codex", "workflow", "verification"],
                    "suggested_lanes": ["documentation", "test", "code_patch"],
                },
            ],
            "provider_runtime_preflight_samples": [
                {
                    "provider": {
                        "name": "openai-agents",
                        "harness": "openai-agents",
                        "auth_env_key": "OPENAI_API_KEY",
                        "required_env_keys": ["OPENAI_API_KEY"],
                    },
                    "runtime": {
                        "platform": "linux",
                        "cli_resolved_in_runner": True,
                        "launch_transport": "subprocess",
                    },
                    "runner_env": {
                        "parent_env_keys": ["PATH"],
                        "allowlist": ["PATH"],
                    },
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_provider_runtime_sample_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_runtime_replay_not_ready"
    assert output["activation_gate"]["decision"] == "blocked_before_activation"
    assert output["provider_runtime_replay_sample"]["route_status"] == "blocked"
    assert output["provider_runtime_replay_sample"]["failure_mode"] == "provider_runtime_recovery_required"
    assert output["provider_runtime_replay_sample"]["recovery_hint_codes"] == ["provider_env_missing"]
    assert output["provider_runtime_replay_sample"]["raw_preflight_inputs_exported"] is False
    assert output["provider_runtime_replay_sample"]["raw_diagnostics_exported"] is False
    assert output["provider_runtime_replay_sample"]["provider_runtime_launch_allowed"] is False
    assert output["provider_runtime_replay_sample"]["remote_execution_allowed"] is False
    assert output["activation_lanes"][0]["provider_runtime_control"]["reason"] == (
        "provider_runtime_replay_not_ready"
    )
    assert output["activation_lanes"][0]["provider_runtime_control"]["next_action"] == (
        "resolve_provider_runtime_replay_hints_then_replay_preflight"
    )
    assert output["activation_lanes"][0]["provider_runtime_control"]["provider_runtime_replay_blocked"] is True
    assert [hint["code"] for hint in output["recovery_hints"]] == [
        "skill_route_provider_runtime_replay_not_ready",
        "provider_runtime_replay_not_ready",
    ]
    assert output["operator_handoff"]["lane_rows"][0]["provider_runtime_replay_sample"]["route_status"] == "blocked"
    assert output["operator_handoff"]["lane_rows"][0]["provider_runtime_control"]["reason"] == (
        "provider_runtime_replay_not_ready"
    )
    assert output["operator_handoff"]["provider_runtime_control"]["reason"] == "provider_runtime_replay_not_ready"
    assert output["operator_handoff"]["provider_runtime_control"]["provider_runtime_replay_blocked"] is True
    assert output["local_lane_intake"]["lane_rows"][0]["provider_runtime_replay_sample"]["route_status"] == "blocked"
    assert output["local_lane_intake"]["lane_rows"][0]["provider_runtime_control"]["provider_runtime_replay_blocked"] is True
    assert output["provider_runtime_diagnostic_panel"] == {
        "controller_surface": "provider_runtime_control",
        "status": "blocked",
        "decision": "resolve_recovery_hints_before_provider_runtime_replay",
        "activation_lane_count": 4,
        "ready_lane_count": 0,
        "blocked_lane_count": 4,
        "provider_runtime_preflight_contract_present": True,
        "provider_runtime_preflight_contract_valid": True,
        "provider_runtime_control_present": True,
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "recovery_hint_count": 2,
        "recovery_hint_codes": [
            "provider_runtime_replay_not_ready",
            "skill_route_provider_runtime_replay_not_ready",
        ],
        "recovery_hint_code_hashes": [
            stable_text_hash("provider_runtime_replay_not_ready"),
            stable_text_hash("skill_route_provider_runtime_replay_not_ready"),
        ],
        "diagnostics": ["recovery_hints_present", "activation_lanes_blocked"],
        "local_replay_only": True,
        "body_free_diagnostics_only": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
    }
    assert output["preactivation_trust_boundary"]["provider_runtime_launch_allowed"] is False
    assert "OPENAI_API_KEY" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized
    assert "https://github.com/baskduf/FableCodex" not in serialized


def test_skill_route_discovery_preactivation_trust_boundary_rejects_tampered_runtime_activation():
    proposal_lanes = [
        {
            "candidate_name": "compass-skills",
            "proposal_kind": "documentation",
            "runtime_action": "none",
            "local_validation_required": True,
        }
    ]
    activation_lanes = [
        {
            "proposal_kind": "documentation",
            "candidate_count": 1,
            "candidate_names": ["compass-skills"],
            "candidate_source_hashes": [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "local_artifact_contract": {
                "proposal_kind": "documentation",
                "target_paths": ["docs/skill-route-discovery.md"],
                "required_review_surface": "changed_files_and_validation",
                "local_only": True,
                "external_skill_code_allowed": False,
                "raw_upstream_body_allowed": False,
            },
            "inspection_requirements": skill_route_discovery_inspection_requirements("documentation"),
            "preactivation_harness": {
                "behavior": "agent_harness_eval_lane",
                "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
                "local_eval_only": True,
                "external_harness_execution_allowed": True,
            },
            "activation_ready": True,
            "activation_blockers": [],
            "runtime_action": "install",
            "external_skill_activation_allowed": True,
            "raw_source_urls_exported": False,
            "provider_runtime_preflight": skill_route_discovery_provider_runtime_preflight_contract(),
            "provider_runtime_control": skill_route_discovery_provider_runtime_control(
                activation_ready=True,
                recovery_hint_codes=[],
            ),
        }
    ]

    preflight = skill_route_discovery_preactivation_trust_boundary(proposal_lanes, activation_lanes)

    assert preflight["status"] == "blocked"
    assert preflight["runtime_action_allowed"] is False
    assert preflight["external_skill_activation_allowed"] is False
    assert preflight["external_harness_execution_allowed"] is False
    assert preflight["diagnostics"] == [
        "activation_lanes[0].runtime_action_must_be_none",
        "activation_lanes[0].external_skill_activation_must_be_false",
        "activation_lanes[0].external_harness_execution_must_be_false",
    ]


def test_skill_route_discovery_preactivation_trust_boundary_rejects_unbounded_artifact_targets():
    proposal_lanes = [
        {
            "candidate_name": "compass-skills",
            "proposal_kind": "documentation",
            "runtime_action": "none",
            "local_validation_required": True,
        }
    ]
    activation_lanes = [
        {
            "proposal_kind": "documentation",
            "candidate_count": 1,
            "candidate_names": ["compass-skills"],
            "candidate_source_hashes": [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "local_artifact_contract": {
                "proposal_kind": "documentation",
                "target_paths": ["https://github.com/example/skill", "../outside.md"],
                "required_review_surface": "upstream_readme",
                "local_only": False,
                "external_skill_code_allowed": True,
                "raw_upstream_body_allowed": True,
            },
            "inspection_requirements": skill_route_discovery_inspection_requirements("documentation"),
            "preactivation_harness": {
                "behavior": "agent_harness_eval_lane",
                "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
                "local_eval_only": True,
                "external_harness_execution_allowed": False,
            },
            "activation_ready": True,
            "activation_blockers": [],
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "raw_source_urls_exported": False,
            "provider_runtime_preflight": skill_route_discovery_provider_runtime_preflight_contract(),
            "provider_runtime_control": skill_route_discovery_provider_runtime_control(
                activation_ready=True,
                recovery_hint_codes=[],
            ),
        }
    ]

    preflight = skill_route_discovery_preactivation_trust_boundary(proposal_lanes, activation_lanes)

    assert preflight["status"] == "blocked"
    assert preflight["diagnostics"] == [
        "activation_lanes[0].local_artifact_contract_review_surface_mismatch",
        "activation_lanes[0].local_artifact_contract_must_be_local_only",
        "activation_lanes[0].external_skill_code_must_be_false",
        "activation_lanes[0].raw_upstream_body_must_be_false",
        "activation_lanes[0].local_artifact_contract_target_unbounded",
    ]


def test_skill_route_discovery_preactivation_trust_boundary_requires_provider_runtime_replay():
    proposal_lanes = [
        {
            "candidate_name": "compass-skills",
            "proposal_kind": "code_patch",
            "runtime_action": "none",
            "local_validation_required": True,
        }
    ]
    activation_lanes = [
        {
            "proposal_kind": "code_patch",
            "candidate_count": 1,
            "candidate_names": ["compass-skills"],
            "candidate_source_hashes": [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "local_artifact_contract": {
                "proposal_kind": "code_patch",
                "target_paths": [
                    "src/blackhole_agent/skill_routing.py",
                    "src/blackhole_agent/harness_eval.py",
                ],
                "required_review_surface": "changed_files_and_validation",
                "local_only": True,
                "external_skill_code_allowed": False,
                "raw_upstream_body_allowed": False,
            },
            "inspection_requirements": skill_route_discovery_inspection_requirements("code_patch"),
            "preactivation_harness": {
                "behavior": "agent_harness_eval_lane",
                "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
                "local_eval_only": True,
                "external_harness_execution_allowed": False,
            },
            "provider_runtime_preflight": {
                "behavior": "provider_runtime_preflight",
                "required_validation": ["pytest tests/test_harness_eval.py -q -k provider_runtime_preflight"],
                "local_replay_only": False,
                "body_free_diagnostics_only": False,
                "provider_runtime_launch_allowed": True,
                "remote_execution_allowed": True,
            },
            "activation_ready": True,
            "activation_blockers": [],
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "raw_source_urls_exported": False,
        }
    ]

    preflight = skill_route_discovery_preactivation_trust_boundary(proposal_lanes, activation_lanes)

    assert preflight["status"] == "blocked"
    assert preflight["provider_runtime_launch_allowed"] is False
    assert preflight["remote_execution_allowed"] is False
    assert preflight["diagnostics"] == [
        "activation_lanes[0].provider_runtime_preflight_behavior_mismatch",
        "activation_lanes[0].provider_runtime_preflight_validation_mismatch",
        "activation_lanes[0].provider_runtime_preflight_must_be_local_replay_only",
        "activation_lanes[0].provider_runtime_preflight_must_be_body_free",
        "activation_lanes[0].provider_runtime_launch_must_be_false",
        "activation_lanes[0].provider_runtime_remote_execution_must_be_false",
        "activation_lanes[0].provider_runtime_control_mismatch",
    ]


def test_skill_route_discovery_lane_keeps_generic_pr_push_clusters_review_only():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-generic-upstream-movement",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "omnigent-generic-movement",
                    "source_url": "https://github.com/omnigent-ai/omnigent",
                    "discovery_event_kind": "push",
                    "evidence_summary": (
                        "Generic PullRequestEvent and push lifecycle cluster with missing PR detail "
                        "and only weak activity metadata."
                    ),
                    "candidate_lanes": ["documentation", "code_patch"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_generic_upstream_inline.json",
    )

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "weak_generic_upstream_evidence"
    assert output["lane_map"]["proposal_lane_count"] == 2
    assert output["lane_map"]["proposal_kinds"] == ["code_patch", "documentation"]
    assert output["diagnostics"] == {
        "failure_mode": "weak_generic_upstream_evidence",
        "evidence_tier": "weak_generic_upstream_movement",
        "candidate_count": 1,
        "proposal_lane_count": 2,
        "rejected_candidate_count": 0,
        "downgraded_candidate_count": 0,
        "uncertainty_reasons": [
            "unvalidated_external_skill_evidence",
            "single_repository_level_source",
            "no_selected_digest_item_ids",
            "missing_detail_risk",
            "generic_upstream_movement_requires_local_corroboration",
        ],
        "body_free": True,
        "source_lineage_mode": "single_or_independent_sources",
    }
    assert output["uncertainty"] == {
        "body_free": True,
        "missing_detail_risk": True,
        "reasons": [
            "unvalidated_external_skill_evidence",
            "single_repository_level_source",
            "no_selected_digest_item_ids",
            "missing_detail_risk",
            "generic_upstream_movement_requires_local_corroboration",
        ],
        "message": (
            "Skill-route evidence has missing_detail_risk; activate only bounded local documentation, "
            "config, test, or code_patch lanes after validation."
        ),
    }
    assert output["recovery_hints"] == [
        {
            "scope": "skill_route_discovery_lane",
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "raw_evidence_exported": False,
            "raw_source_urls_exported": False,
            "value_recorded": False,
            "code": "skill_route_sparse_upstream_movement",
            "safe_action": (
                "Add a focused local corroboration record or fixture before promoting this repository movement "
                "into documentation, config, test, or code_patch work."
            ),
            "evidence_tier": "weak_generic_upstream_movement",
            "local_corroborating_signal_count": 0,
        }
    ]
    assert [entry["allowed_local_lane"] for entry in output["discovery_checklist"]] == [
        "documentation",
        "code_patch",
    ]
    assert output["evidence_strength"] == {
        "tier": "weak_generic_upstream_movement",
        "record_count": 1,
        "weak_generic_movement_count": 1,
        "specific_detail_count": 0,
        "explicit_route_hint_count": 0,
        "local_validation_signal_count": 0,
        "local_corroborating_signal_count": 0,
        "corroboration_required_for_generic_upstream_movement": True,
        "activation_evidence_sufficient": False,
    }
    assert output["activation_gate"] == {
        "controller_surface": "skill_route_discovery_lane",
        "activation_scope": "local_proposal_only",
        "decision": "review_weak_evidence_before_activation",
        "reason": "weak_generic_upstream_evidence",
        "local_proposal_activation_allowed": False,
        "external_skill_activation_allowed": False,
    }
    assert output["activity_signal_panel"]["status"] == "review"
    assert output["activity_signal_panel"]["decision"] == "hold_activity_signal_for_review"
    assert output["activity_signal_panel"]["weak_generic_movement_count"] == 1
    assert output["activity_signal_panel"]["local_corroborating_signal_count"] == 0
    assert (
        output["activity_signal_panel"]["generic_movement_policy"]
        == "supporting_context_only_until_local_corroboration"
    )
    assert output["activity_signal_panel"]["diagnostics"] == [
        "generic_upstream_movement_requires_local_corroboration"
    ]
    assert [lane["proposal_kind"] for lane in output["activation_lanes"]] == ["code_patch", "documentation"]
    for lane in output["activation_lanes"]:
        assert lane["candidate_count"] == 1
        assert lane["candidate_names"] == ["omnigent-generic-movement"]
        assert lane["required_validation"] == skill_route_discovery_preactivation_validation_commands()
        assert lane["local_artifact_contract"]["proposal_kind"] == lane["proposal_kind"]
        assert lane["local_artifact_contract"]["local_only"] is True
        assert lane["local_artifact_contract"]["external_skill_code_allowed"] is False
        assert lane["preactivation_harness"]["behavior"] == "agent_harness_eval_lane"
        assert lane["preactivation_harness"]["external_harness_execution_allowed"] is False
        assert lane["provider_runtime_preflight"] == skill_route_discovery_provider_runtime_preflight_contract()
        assert lane["activation_ready"] is False
        assert lane["activation_blockers"] == ["weak_generic_upstream_evidence"]
        assert lane["recovery_hint_codes"] == ["skill_route_sparse_upstream_movement"]
        assert lane["runtime_action"] == "none"
        assert lane["external_skill_activation_allowed"] is False
    for row in output["activity_signal_panel"]["rows"]:
        assert row["activity_interpretation"] == "low_detail_generic_movement_supporting_context_only"
        assert row["weak_generic_supporting_context_only"] is True
        assert row["local_corroboration_required"] is True
        assert row["local_corroborating_signal_count"] == 0
    assert all("missing_detail_risk" in lane["uncertainty_reasons"] for lane in output["proposal_lanes"])


def test_skill_route_discovery_lane_requires_local_corroboration_for_generic_pr_route_hints():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-generic-route-hint-only",
            "source_kind": "evidence_items",
            "evidence_items": [
                {
                    "item_id": "omnigent-pr-809",
                    "item_kind": "pull_request",
                    "name": "omnigent",
                    "source_url": "https://github.com/omnigent-ai/omnigent/pull/809",
                    "title": "Untitled generic PR movement",
                    "summary": (
                        "Generic PR lifecycle for an agent skill route with route hint and CI wording "
                        "but missing implementation detail."
                    ),
                    "route_hints": ["skill_route_discovery"],
                    "suggested_lanes": ["documentation", "test"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_generic_route_hint_inline.json",
    )

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "weak_generic_upstream_evidence"
    assert output["evidence_strength"] == {
        "tier": "weak_generic_upstream_movement",
        "record_count": 1,
        "weak_generic_movement_count": 1,
        "specific_detail_count": 0,
        "explicit_route_hint_count": 1,
        "local_validation_signal_count": 1,
        "local_corroborating_signal_count": 0,
        "corroboration_required_for_generic_upstream_movement": True,
        "activation_evidence_sufficient": False,
    }
    assert output["activation_gate"]["decision"] == "review_weak_evidence_before_activation"
    assert output["activation_gate"]["local_proposal_activation_allowed"] is False
    assert output["activity_signal_panel"]["generic_movement_policy"] == (
        "supporting_context_only_until_local_corroboration"
    )
    assert output["activity_signal_panel"]["weak_generic_movement_count"] == 1
    assert output["activity_signal_panel"]["local_corroborating_signal_count"] == 0
    for row in output["activity_signal_panel"]["rows"]:
        assert row["activity_interpretation"] == "low_detail_generic_movement_supporting_context_only"
        assert row["weak_generic_supporting_context_only"] is True
        assert row["local_corroboration_required"] is True


def test_skill_route_discovery_lane_allows_generic_pr_only_with_local_corroboration():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-generic-corroborated",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "omnigent-generic-movement",
                    "source_url": "https://github.com/omnigent-ai/omnigent",
                    "discovery_event_kind": "push",
                    "evidence_summary": "Generic upstream PR/push lifecycle cluster with missing detail.",
                    "candidate_lanes": ["documentation"],
                }
            ],
            "local_corroboration": [
                {
                    "signal_kind": "focused_fixture",
                    "validation_command": "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_generic_corroborated_inline.json",
    )

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["evidence_strength"] == {
        "tier": "generic_upstream_movement_with_local_corroboration",
        "record_count": 1,
        "weak_generic_movement_count": 1,
        "specific_detail_count": 0,
        "explicit_route_hint_count": 0,
        "local_validation_signal_count": 0,
        "local_corroborating_signal_count": 1,
        "corroboration_required_for_generic_upstream_movement": True,
        "activation_evidence_sufficient": True,
    }
    assert output["activation_gate"] == {
        "controller_surface": "skill_route_discovery_lane",
        "activation_scope": "local_proposal_only",
        "decision": "ready_for_local_proposal_activation",
        "reason": "none",
        "local_proposal_activation_allowed": True,
        "external_skill_activation_allowed": False,
    }
    assert output["activity_signal_panel"]["generic_movement_policy"] == "locally_corroborated_generic_context"
    assert output["activity_signal_panel"]["weak_generic_movement_count"] == 1
    assert output["activity_signal_panel"]["local_corroborating_signal_count"] == 1
    for row in output["activity_signal_panel"]["rows"]:
        assert row["activity_interpretation"] == "movement_supports_local_validation_lane"
        assert row["weak_generic_supporting_context_only"] is False
        assert row["local_corroboration_required"] is True
        assert row["local_corroborating_signal_count"] == 1


def test_skill_route_discovery_lane_requires_review_for_downgraded_lanes():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-discovery-downgraded",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "overbroad-skill",
                    "source_url": "https://github.com/example/overbroad-skill",
                    "candidate_lanes": ["documentation", "runtime_execution"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_downgraded_inline.json",
    )

    assert output["route_status"] == "degraded"
    assert output["failure_mode"] == "unsupported_lanes_downgraded"
    assert output["lane_map"]["proposal_lane_count"] == 1
    assert output["lane_map"]["downgraded_candidate_count"] == 1
    assert output["activation_gate"] == {
        "controller_surface": "skill_route_discovery_lane",
        "activation_scope": "local_proposal_only",
        "decision": "review_degraded_lane_before_activation",
        "reason": "unsupported_lanes_downgraded",
        "local_proposal_activation_allowed": False,
        "external_skill_activation_allowed": False,
    }
    assert output["activation_lanes"] == [
        {
            "proposal_kind": "documentation",
            "candidate_count": 1,
            "candidate_names": ["overbroad-skill"],
            "candidate_source_hashes": [stable_text_hash("https://github.com/example/overbroad-skill")],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "local_artifact_contract": {
                "proposal_kind": "documentation",
                "target_paths": ["docs/skill-route-discovery.md"],
                "required_review_surface": "changed_files_and_validation",
                "local_only": True,
                "external_skill_code_allowed": False,
                "raw_upstream_body_allowed": False,
            },
            "inspection_requirements": skill_route_discovery_inspection_requirements("documentation"),
            "local_artifact_proof": {
                "provided": False,
                "ready": False,
                "proposal_kind": "documentation",
                "changed_file_count": 0,
                "changed_file_hashes": [],
                "target_paths_matched": False,
                "validation_matched": False,
                "rollback_recorded": False,
                "rollback_artifact_hash": None,
                "review_note_recorded": False,
                "diagnostics": ["local_artifact_proof_missing"],
                "raw_changed_files_exported": False,
                "raw_rollback_artifact_exported": False,
            },
            "preactivation_harness": {
                "behavior": "agent_harness_eval_lane",
                "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
                "local_eval_only": True,
                "external_harness_execution_allowed": False,
            },
            "provider_runtime_preflight": skill_route_discovery_provider_runtime_preflight_contract(),
            "provider_runtime_control": skill_route_discovery_provider_runtime_control(
                activation_ready=False,
                recovery_hint_codes=["skill_route_unsupported_lanes_downgraded"],
            ),
            "activation_ready": False,
            "activation_blockers": ["unsupported_lanes_downgraded"],
            "recovery_hint_codes": ["skill_route_unsupported_lanes_downgraded"],
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "raw_source_urls_exported": False,
        }
    ]
    assert output["supervisor_readiness"]["decision"] == "review_before_supervisor_promotion"
    assert output["supervisor_readiness"]["reason"] == "unsupported_lanes_downgraded"
    assert output["supervisor_readiness"]["activation_lane_count"] == 1
    assert output["supervisor_readiness"]["ready_lane_count"] == 0
    assert output["supervisor_readiness"]["blocked_lane_count"] == 1
    assert output["implementation_intake_preflight"]["status"] == "blocked"
    assert output["implementation_intake_preflight"]["implementation_allowed"] is False
    assert output["implementation_intake_preflight"]["diagnostics"] == [
        "activation_lanes[0].activation_not_ready",
        "activation_lanes[0].local_artifact_proof_not_ready",
    ]
    assert output["supervisor_readiness"]["recovery_hint_codes"] == ["skill_route_unsupported_lanes_downgraded"]
    assert output["operator_handoff"]["status"] == "blocked"
    assert output["operator_handoff"]["decision"] == "hold_for_review_or_replay"
    assert output["operator_handoff"]["ready_lane_count"] == 0
    assert output["operator_handoff"]["blocked_lane_count"] == 1
    assert output["operator_handoff"]["local_artifact_proof_ready"] is False
    assert output["operator_handoff"]["implementation_intake_status"] == "blocked"
    assert output["operator_handoff"]["supervisor_decision"] == "review_before_supervisor_promotion"
    assert output["operator_handoff"]["recovery_hint_codes"] == ["skill_route_unsupported_lanes_downgraded"]
    assert output["operator_handoff"]["lane_rows"] == [
        {
            "proposal_kind": "documentation",
            "candidate_count": 1,
            "activation_ready": False,
            "local_artifact_proof_ready": False,
            "target_path_hashes": [stable_text_hash("docs/skill-route-discovery.md")],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "provider_runtime_replay_commands": [
                "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
            ],
            "provider_runtime_control": skill_route_discovery_provider_runtime_control(
                activation_ready=False,
                recovery_hint_codes=["skill_route_unsupported_lanes_downgraded"],
            ),
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "raw_target_paths_exported": False,
            "raw_source_urls_exported": False,
        }
    ]
    assert output["supervisor_readiness"]["runtime_action_allowed"] is False
    assert output["supervisor_readiness"]["external_skill_activation_allowed"] is False
    assert output["supervisor_readiness"]["external_harness_execution_allowed"] is False


def test_rendered_html_artifact_validation_blocks_when_scripts_do_not_execute():
    raw_input = {
        "task_id": "fixture-rendered-html-script-disabled",
        "artifact": {
            "kind": "html",
            "rendered_boundary": "rendered_html_artifact",
            "html_body": "PRIVATE_RENDERED_HTML_SCRIPT_BODY_DO_NOT_EXPORT",
        },
        "browser": {
            "available": True,
            "sandbox_allows_scripts": False,
        },
        "script_probe": {
            "expected_execution": True,
            "observed_execution": False,
        },
        "link_probes": [
            {
                "label": "plain-external-anchor",
                "href": "https://example.com/private-script-blocked-link",
                "declared_target": "",
                "expected_navigation": "new_frame",
                "observed_navigation": "new_frame",
            },
        ],
    }

    output = evaluate_harness_behavior(
        "rendered_html_artifact_validation",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "rendered_html_script_disabled_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "rendered_html_script_execution_missing"
    assert output["script_execution"]["passed"] is False
    assert "PRIVATE_RENDERED_HTML_SCRIPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "private-script-blocked-link" not in serialized


def test_rendered_html_artifact_validation_blocks_same_frame_link_navigation():
    raw_input = {
        "task_id": "fixture-rendered-html-same-frame-link",
        "artifact": {
            "kind": "html",
            "rendered_boundary": "rendered_html_artifact",
            "html_body": "PRIVATE_RENDERED_HTML_LINK_BODY_DO_NOT_EXPORT",
        },
        "browser": {
            "available": True,
            "sandbox_allows_scripts": True,
        },
        "script_probe": {
            "expected_execution": True,
            "observed_execution": True,
        },
        "link_probes": [
            {
                "label": "plain-external-anchor",
                "href": "https://example.com/private-same-frame-link",
                "declared_target": "",
                "expected_navigation": "new_frame",
                "observed_navigation": "same_frame",
            },
            {
                "label": "target-blank-external-anchor",
                "href": "https://example.com/private-target-blank-link",
                "declared_target": "_blank",
                "expected_navigation": "new_frame",
                "observed_navigation": "new_frame",
            },
        ],
    }

    output = evaluate_harness_behavior(
        "rendered_html_artifact_validation",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "rendered_html_same_frame_link_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "rendered_html_link_navigation_mismatch"
    assert output["link_navigation"]["same_frame_anchor_count"] == 1
    assert output["link_navigation"]["target_blank_anchor_count"] == 1
    assert output["link_navigation"]["passed"] is False
    assert output["link_navigation"]["probes"][0]["observed_navigation"] == "same_frame"
    assert "PRIVATE_RENDERED_HTML_LINK_BODY_DO_NOT_EXPORT" not in serialized
    assert "private-same-frame-link" not in serialized


def test_rendered_html_artifact_validation_blocks_empty_landing_snapshot_without_baseline():
    raw_input = rendered_html_snapshot_gate_input(
        {
            "required": True,
            "state": "empty_landing",
            "current_hash": "sha256:fixture-empty-landing-current",
            "diff_status": "clean",
            "empty_state_expected": True,
            "empty_state_observed": True,
            "baseline_path": "PRIVATE_MISSING_BASELINE_PATH_DO_NOT_EXPORT",
        }
    )

    output = evaluate_harness_behavior(
        "rendered_html_artifact_validation",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "rendered_html_empty_landing_missing_baseline_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "ui_snapshot_baseline_missing"
    assert output["snapshot_gate"]["passed"] is False
    assert output["snapshot_gate"]["baseline_hash_present"] is False
    assert output["snapshot_gate"]["current_hash_present"] is True
    assert output["privacy"]["snapshot_paths_exported"] is False
    assert "PRIVATE_RENDERED_HTML_SNAPSHOT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_MISSING_BASELINE_PATH_DO_NOT_EXPORT" not in serialized
    assert "private-snapshot-link" not in serialized


def test_rendered_html_artifact_validation_distinguishes_snapshot_gate_failures():
    cases = [
        (
            {
                "state": "empty_landing",
                "baseline_hash": "sha256:fixture-empty-landing-baseline",
                "diff_status": "clean",
                "empty_state_observed": True,
            },
            "ui_snapshot_current_missing",
        ),
        (
            {
                "state": "empty_landing",
                "baseline_hash": "sha256:fixture-empty-landing-baseline",
                "current_hash": "sha256:fixture-empty-landing-current",
                "diff_status": "clean",
                "empty_state_observed": False,
            },
            "ui_snapshot_empty_state_missing",
        ),
        (
            {
                "state": "baseline",
                "baseline_hash": "sha256:fixture-baseline",
                "current_hash": "sha256:fixture-current",
                "diff_status": "changed",
                "empty_state_expected": False,
            },
            "ui_snapshot_diff_unapproved",
        ),
    ]

    for snapshot_gate, expected_failure_mode in cases:
        output = evaluate_harness_behavior(
            "rendered_html_artifact_validation",
            rendered_html_snapshot_gate_input(snapshot_gate),
            source_path=LOCAL_EVAL_FIXTURE_DIR / f"rendered_html_{expected_failure_mode}_inline.json",
        )

        assert output["route_status"] == "blocked"
        assert output["failure_mode"] == expected_failure_mode
        assert output["snapshot_gate"]["failure_mode"] == expected_failure_mode
        assert output["snapshot_gate"]["passed"] is False


def rendered_html_snapshot_gate_input(snapshot_gate: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": "fixture-rendered-html-empty-landing-missing-baseline",
        "artifact": {
            "kind": "html",
            "rendered_boundary": "rendered_html_artifact",
            "html_body": "PRIVATE_RENDERED_HTML_SNAPSHOT_BODY_DO_NOT_EXPORT",
        },
        "browser": {
            "available": True,
            "sandbox_allows_scripts": True,
        },
        "script_probe": {
            "expected_execution": True,
            "observed_execution": True,
        },
        "link_probes": [
            {
                "label": "plain-external-anchor",
                "href": "https://example.com/private-snapshot-link",
                "declared_target": "",
                "expected_navigation": "new_frame",
                "observed_navigation": "new_frame",
            },
        ],
        "snapshot_gate": snapshot_gate,
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


def test_agent_workflow_route_control_plane_marks_flaky_teardown_non_load_bearing():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_control_plane_replay.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["control_plane"]["complete"] is True
    assert output["control_plane"]["stages"] == {
        "intake": {"ready": True, "status": "recorded"},
        "midflight": {"ready": True, "status": "recorded"},
        "recovery": {"ready": True, "status": "recorded"},
        "replay": {"ready": True, "status": "recorded"},
        "report": {"ready": True, "status": "recorded"},
    }
    assert output["control_plane"]["observation_contract"] == {
        "load_bearing_count": 1,
        "non_load_bearing_count": 1,
        "unreliable_non_load_bearing_count": 1,
        "failed_load_bearing_count": 0,
        "flaky_observations_allowed_only_when_non_load_bearing": True,
    }
    assert output["control_plane"]["recovery"]["required"] is True
    assert output["control_plane"]["recovery"]["ready"] is True
    assert output["control_plane"]["recovery"]["operator_required"] is True
    assert output["control_plane"]["recovery"]["blockers"] == []
    assert output["control_plane"]["recovery"]["command_count"] == 2
    assert len(output["control_plane"]["recovery"]["command_hashes"]) == 2
    assert output["control_plane"]["recovery"]["replay_ready"] is True
    assert output["control_plane"]["recovery"]["replay_command_hash"].startswith("sha256:")
    assert output["control_plane"]["recovery"]["validation_command_count"] == 1
    assert output["control_plane"]["recovery"]["raw_recovery_commands_exported"] is False
    assert output["control_plane"]["recovery"]["raw_replay_command_exported"] is False
    assert output["control_plane"]["recovery"]["raw_rollback_refs_exported"] is False
    assert output["observations"]["passed"] is True
    assert output["observations"]["items"][1]["phase"] == "teardown"
    assert output["observations"]["items"][1]["load_bearing"] is False
    assert output["observations"]["items"][1]["reliable"] is False
    assert output["observations"]["raw_observation_ids_exported"] is False
    assert output["control_plane"]["report"]["raw_artifact_paths_exported"] is False
    assert output["control_plane"]["report"]["report_artifact_hash"].startswith("sha256:")
    assert output["control_plane"]["report"]["section_contract"] == {
        "required": True,
        "required_sections": ["changed_files", "validation", "rollback", "replay", "review_notes"],
        "recorded_section_count": 5,
        "recorded_sections": ["changed_files", "replay", "review_notes", "rollback", "validation"],
        "missing_sections": [],
        "passed": True,
        "failure_mode": "none",
        "raw_report_body_exported": False,
    }
    assert output["control_plane"]["replay"]["replay_artifact_hash"].startswith("sha256:")
    assert "overview-title-painted" not in serialized
    assert "idle-status-after-teardown" not in serialized
    assert "artifacts/self-evolution/fixture-route-control-plane-report.md" not in serialized
    assert "refs/rollback/fixture-route-control-plane-replay" not in serialized
    assert "git reset --hard fixture-route-control-plane-head" not in serialized
    assert "pytest tests/test_harness_eval.py -q -k agent_workflow_route_control_plane" not in serialized

    stale_gate = evaluate_harness_behavior(
        "agent_workflow_route",
        {
            "task_id": "fixture-route-stale-load-bearing-observation",
            "plan": {"steps": [{"id": "intake", "status": "completed"}]},
            "runner": {"invoked": True, "returncode": 0, "timed_out": False},
            "observations": [
                {
                    "id": "PRIVATE_STALE_OBSERVATION_ID_DO_NOT_EXPORT",
                    "phase": "teardown",
                    "load_bearing": True,
                    "reliable": False,
                    "observed": False,
                }
            ],
            "validation": {
                "gate": "runner-harness-control-plane",
                "checks": [{"name": "pytest-agent-workflow-control-plane", "returncode": 0}],
            },
            "rollback": {
                "created": True,
                "ref": "refs/rollback/fixture-route-stale-load-bearing-observation",
            },
            "artifacts": {
                "report_recorded": True,
                "report_sections": ["changed_files", "validation", "rollback", "replay", "review_notes"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_stale_observation_inline.json",
    )
    stale_serialized = json.dumps(stale_gate, sort_keys=True)

    assert stale_gate["route_status"] == "failed_recoverable"
    assert stale_gate["failure_mode"] == "unreliable_load_bearing_observation"
    assert stale_gate["observations"]["failed_load_bearing_count"] == 1
    assert stale_gate["control_plane"]["complete"] is False
    assert "PRIVATE_STALE_OBSERVATION_ID_DO_NOT_EXPORT" not in stale_serialized

    missing_handoff = evaluate_harness_behavior(
        "agent_workflow_route",
        {
            "task_id": "fixture-route-missing-recovery-handoff",
            "plan": {"steps": [{"id": "intake", "status": "completed"}]},
            "runner": {"invoked": True, "returncode": 0, "timed_out": False},
            "validation": {
                "gate": "runner-harness-control-plane",
                "checks": [{"name": "pytest-agent-workflow-control-plane", "returncode": 0}],
            },
            "rollback": {
                "created": True,
                "ref": "refs/rollback/PRIVATE_RECOVERY_REF_DO_NOT_EXPORT",
            },
            "recovery": {
                "required": True,
                "commands": [],
            },
            "artifacts": {
                "report_recorded": True,
                "report_sections": ["changed_files", "validation", "rollback", "replay", "review_notes"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_missing_recovery_handoff_inline.json",
    )
    missing_serialized = json.dumps(missing_handoff, sort_keys=True)

    assert missing_handoff["route_status"] == "failed_recoverable"
    assert missing_handoff["failure_mode"] == "recovery_handoff_incomplete"
    assert missing_handoff["control_plane"]["complete"] is False
    assert missing_handoff["control_plane"]["missing_stages"] == ["recovery"]
    assert missing_handoff["control_plane"]["recovery"]["ready"] is False
    assert missing_handoff["control_plane"]["recovery"]["blockers"] == ["recovery_commands_missing"]
    assert "PRIVATE_RECOVERY_REF_DO_NOT_EXPORT" not in missing_serialized


def test_agent_workflow_route_orchestrator_inbox_delivery_contract():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_orchestrator_inbox_delivery.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["orchestrator_inbox"]["passed"] is True
    assert output["orchestrator_inbox"]["completion_message_count"] == 1
    assert output["orchestrator_inbox"]["expected_completion_count"] == 1
    assert output["orchestrator_inbox"]["parent_woken"] is True
    assert output["orchestrator_inbox"]["empty_turn_count"] == 0
    assert output["orchestrator_inbox"]["transcript_only_turn_count"] == 0
    assert output["orchestrator_inbox"]["child_lifecycle"] == {
        "sub_agent_name_present": True,
        "send_handle_degraded": False,
        "close_supported": True,
        "degraded": False,
        "raw_agent_names_exported": False,
        "raw_session_ids_exported": False,
    }
    assert output["orchestrator_inbox"]["recovery"] == {
        "transcript_polling_available": False,
        "transcript_polling_required": False,
        "cleanup_required": False,
        "cleanup_supported": True,
        "cleanup_blocked": False,
        "operator_action": "none",
        "raw_transcripts_exported": False,
        "raw_session_ids_exported": False,
    }
    assert output["control_plane"]["inbox_delivery_contract"] == {
        "required": True,
        "passed": True,
        "failure_mode": "none",
        "expected_completion_count": 1,
        "completion_message_count": 1,
        "parent_woken": True,
        "transcript_only_turn_count": 0,
        "empty_turn_count": 0,
        "child_lifecycle_degraded": False,
        "recovery": {
            "transcript_polling_available": False,
            "transcript_polling_required": False,
            "cleanup_required": False,
            "cleanup_blocked": False,
            "operator_action": "none",
        },
    }
    assert "PRIVATE_INBOX_MESSAGE_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_SESSION_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_TURN_ID_DO_NOT_EXPORT" not in serialized

    missing_delivery = evaluate_harness_behavior(
        "agent_workflow_route",
        {
            "task_id": "fixture-route-orchestrator-inbox-missing-delivery",
            "plan": {"steps": [{"id": "intake", "status": "completed"}]},
            "runner": {"invoked": True, "returncode": 0, "timed_out": False},
            "orchestrator_inbox": {
                "required": True,
                "expected_completion_count": 1,
                "parent_woken": False,
                "messages": [],
                "child_turns": [
                    {
                        "id": "PRIVATE_TRANSCRIPT_ONLY_TURN_DO_NOT_EXPORT",
                        "has_output": True,
                        "output_tokens": 72,
                        "transcript_only": True,
                    }
                ],
                "child_lifecycle": {
                    "sub_agent_name_present": False,
                    "send_handle_degraded": True,
                    "close_supported": False,
                },
            },
            "validation": {
                "gate": "runner-harness-control-plane",
                "checks": [{"name": "pytest-agent-workflow-orchestrator-inbox", "returncode": 0}],
            },
            "rollback": {"created": True, "ref": "refs/rollback/fixture-route-orchestrator-inbox"},
            "artifacts": {
                "report_recorded": True,
                "report_sections": ["changed_files", "validation", "rollback", "replay", "review_notes"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_orchestrator_inbox_missing_inline.json",
    )
    missing_serialized = json.dumps(missing_delivery, sort_keys=True)

    assert missing_delivery["route_status"] == "failed_recoverable"
    assert missing_delivery["failure_mode"] == "orchestrator_inbox_completion_missing"
    assert missing_delivery["orchestrator_inbox"]["transcript_only_turn_count"] == 1
    assert missing_delivery["orchestrator_inbox"]["child_lifecycle"]["degraded"] is True
    assert missing_delivery["orchestrator_inbox"]["recovery"] == {
        "transcript_polling_available": True,
        "transcript_polling_required": True,
        "cleanup_required": True,
        "cleanup_supported": False,
        "cleanup_blocked": True,
        "operator_action": "poll_child_transcript_then_manual_session_cleanup",
        "raw_transcripts_exported": False,
        "raw_session_ids_exported": False,
    }
    assert missing_delivery["control_plane"]["inbox_delivery_contract"]["recovery"] == {
        "transcript_polling_available": True,
        "transcript_polling_required": True,
        "cleanup_required": True,
        "cleanup_blocked": True,
        "operator_action": "poll_child_transcript_then_manual_session_cleanup",
    }
    assert "PRIVATE_TRANSCRIPT_ONLY_TURN_DO_NOT_EXPORT" not in missing_serialized

    duplicate_delivery = evaluate_harness_behavior(
        "agent_workflow_route",
        {
            "task_id": "fixture-route-orchestrator-inbox-duplicate",
            "plan": {"steps": [{"id": "intake", "status": "completed"}]},
            "runner": {"invoked": True, "returncode": 0, "timed_out": False},
            "orchestrator_inbox": {
                "required": True,
                "expected_completion_count": 1,
                "parent_woken": True,
                "messages": [{"kind": "completion"}, {"kind": "completion"}],
                "child_lifecycle": {
                    "sub_agent_name_present": True,
                    "send_handle_degraded": False,
                    "close_supported": True,
                },
            },
            "validation": {"checks": [{"name": "pytest-agent-workflow-orchestrator-inbox", "returncode": 0}]},
            "rollback": {"created": True, "ref": "refs/rollback/fixture-route-orchestrator-inbox"},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_orchestrator_inbox_duplicate_inline.json",
    )
    assert duplicate_delivery["failure_mode"] == "orchestrator_inbox_duplicate_completion"
    assert duplicate_delivery["orchestrator_inbox"]["recovery"]["operator_action"] == "inspect_inbox_delivery_route"

    empty_turn = evaluate_harness_behavior(
        "agent_workflow_route",
        {
            "task_id": "fixture-route-orchestrator-inbox-empty-turn",
            "plan": {"steps": [{"id": "intake", "status": "completed"}]},
            "runner": {"invoked": True, "returncode": 0, "timed_out": False},
            "orchestrator_inbox": {
                "required": True,
                "expected_completion_count": 1,
                "parent_woken": True,
                "messages": [{"kind": "completion"}],
                "child_turns": [{"output_tokens": 0}],
                "child_lifecycle": {
                    "sub_agent_name_present": True,
                    "send_handle_degraded": False,
                    "close_supported": True,
                },
            },
            "validation": {"checks": [{"name": "pytest-agent-workflow-orchestrator-inbox", "returncode": 0}]},
            "rollback": {"created": True, "ref": "refs/rollback/fixture-route-orchestrator-inbox"},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_orchestrator_inbox_empty_inline.json",
    )
    assert empty_turn["failure_mode"] == "orchestrator_inbox_empty_turn"
    assert empty_turn["orchestrator_inbox"]["recovery"]["operator_action"] == "rerun_child_turn_with_empty_output_error"

    lifecycle_degraded = evaluate_harness_behavior(
        "agent_workflow_route",
        {
            "task_id": "fixture-route-orchestrator-inbox-lifecycle-degraded",
            "plan": {"steps": [{"id": "intake", "status": "completed"}]},
            "runner": {"invoked": True, "returncode": 0, "timed_out": False},
            "orchestrator_inbox": {
                "required": True,
                "expected_completion_count": 1,
                "parent_woken": True,
                "messages": [{"kind": "completion"}],
                "child_lifecycle": {
                    "sub_agent_name_present": False,
                    "send_handle_degraded": True,
                    "close_supported": False,
                },
            },
            "validation": {"checks": [{"name": "pytest-agent-workflow-orchestrator-inbox", "returncode": 0}]},
            "rollback": {"created": True, "ref": "refs/rollback/fixture-route-orchestrator-inbox"},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_orchestrator_inbox_lifecycle_inline.json",
    )
    assert lifecycle_degraded["failure_mode"] == "orchestrator_inbox_lifecycle_degraded"
    assert lifecycle_degraded["orchestrator_inbox"]["recovery"]["operator_action"] == "manual_session_cleanup_required"


def test_agent_workflow_route_blocks_before_activation_when_oneshot_marker_absent():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_oneshot_marker_absent.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked_before_activation"
    assert output["failure_mode"] == "oneshot_marker_missing"
    assert output["oneshot_marker"]["required"] is True
    assert output["oneshot_marker"]["present"] is False
    assert output["oneshot_marker"]["ready"] is False
    assert output["oneshot_marker"]["path_hash"].startswith("sha256:")
    assert output["oneshot_marker"]["raw_path_exported"] is False
    assert output["runner"]["invoked"] is False
    assert output["validation"]["gate"] == "narrow-local-verification"
    assert output["rollback"]["recovery_mode"] == "explicit_operator_reset"
    assert output["state_transitions"][1] == {
        "state": "oneshot_marker_checked",
        "outcome": "failed",
    }
    assert "PRIVATE_ONESHOT_MARKER_PATH_DO_NOT_EXPORT" not in serialized


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
        "raw_agent_yaml_exported": False,
        "hashes_only": True,
    }
    assert "PRIVATE_HOST_NATIVE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "fixtures/private-input.md" not in serialized
    assert "fixtures/private-output.md" not in serialized
    assert "miscellaneous read result stayed inside local fixture" not in serialized


def test_mock_e2e_runner_tier_parses_yaml_agent_route_without_exporting_yaml():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_e2e_runner_tier_yaml_agent_route.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["agent_config"]["configured"] is True
    assert output["agent_config"]["passed"] is True
    assert output["agent_config"]["parse_error"] is False
    assert output["agent_config"]["yaml_hash"].startswith("sha256:")
    assert output["agent_config"]["executor_harness_hash"].startswith("sha256:")
    assert output["agent_config"]["function_tool_count"] == 1
    assert output["agent_config"]["executable_tool_count"] == 1
    assert output["agent_config"]["non_executable_tool_count"] == 0
    assert output["agent_config"]["route_counts"] == {"executable": 1}
    assert output["agent_config"]["required_tool_count"] == 1
    assert output["agent_config"]["missing_required_tool_count"] == 0
    assert len(output["agent_config"]["tool_name_hashes"]) == 1
    assert output["agent_config"]["raw_yaml_exported"] is False
    assert output["agent_config"]["raw_tool_metadata_exported"] is False
    assert output["provider"]["external_calls_attempted"] is False
    assert output["provider"]["credentials_required"] is False
    assert output["provider"]["network_required"] is False
    assert output["privacy"]["raw_agent_yaml_exported"] is False
    assert output["failure_mode"] == "none"
    assert "PRIVATE_YAML_AGENT_PROMPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_YAML_PARSE_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_YAML_AGENT_PATH_DO_NOT_EXPORT" not in serialized
    assert "local_fixture.tools.retain" not in serialized
    assert "hindsight_retain" not in serialized


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


def test_mock_e2e_runner_tier_classifies_ci_roundtrip_hang_separately_from_auth():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_e2e_runner_tier_ci_roundtrip_hang.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    auth_output = evaluate_harness_behavior(
        "mock_e2e_runner_tier",
        {
            **fixture["input"],
            "task_id": "fixture-mock-e2e-runner-tier-auth-failure",
            "ci_round_trip": {
                "expected_failure_family": "authentication_failure",
                "prompt_observed": False,
                "completion_observed": False,
                "timed_out": False,
                "auth_error": True,
                "failure_text": "PRIVATE_AUTH_FAILURE_TEXT_DO_NOT_EXPORT",
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_e2e_runner_tier_auth_failure_inline.json",
    )
    serialized = json.dumps({"hang": output, "auth": auth_output}, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["ci_round_trip"]["observed_failure_family"] == "ci_round_trip_hang"
    assert output["ci_round_trip"]["round_trip_hang_detected"] is True
    assert output["ci_round_trip"]["auth_failure_detected"] is False

    assert auth_output["route_status"] == "passed"
    assert auth_output["ci_round_trip"]["observed_failure_family"] == "authentication_failure"
    assert auth_output["ci_round_trip"]["auth_failure_detected"] is True
    assert auth_output["ci_round_trip"]["round_trip_hang_detected"] is False
    assert "PRIVATE_CI_ROUNDTRIP_FAILURE_TEXT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_AUTH_FAILURE_TEXT_DO_NOT_EXPORT" not in serialized


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
    assert output["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["openai-agents"],
            "value_recorded": False,
            "code": "mock_auth_placeholder_used",
            "scope": "mock_llm_provider_auth",
            "severity": "notice",
            "action": "keep this route mock-only unless real provider credentials are configured outside fixture output",
            "required_env_key_count": 1,
        }
    ]
    assert output["supervisor_replay"] == {
        "ready_for_provider_launch": False,
        "ready_for_local_replay": True,
        "decision": "ready_for_local_mock_replay",
        "reason": "none",
        "route_status": "degraded",
        "recovery_hint_codes": ["mock_auth_placeholder_used"],
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_input_exported": False,
        "raw_diagnostics_exported": False,
        "degraded_replay_only": True,
    }
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
    assert (
        "skipped worker env inheritance check because the harness declares no worker tool"
        in output["preflight"]["diagnostics"]
    )
    assert "OPENAI_API_KEY" not in serialized


def test_provider_runtime_preflight_blocks_usage_limit_429_without_credential_or_body_export():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_usage_limit_429.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_usage_limit_exhausted"
    assert output["usage_limit"]["response_status"] == 429
    assert output["usage_limit"]["rate_limited"] is True
    assert output["usage_limit"]["window_count"] == 2
    assert output["usage_limit"]["exhausted_window_count"] == 1
    assert output["usage_limit"]["windows"][0] == {
        "name": "5h",
        "limit_recorded": True,
        "remaining": 0,
        "remaining_recorded": True,
        "reset_present": True,
        "reset_hash": output["usage_limit"]["windows"][0]["reset_hash"],
        "exhausted": True,
        "near_limit": True,
        "raw_header_values_exported": False,
    }
    assert output["usage_limit"]["credential_pool_configured"] is True
    assert output["usage_limit"]["credential_count"] == 3
    assert output["usage_limit"]["active_credential_label_hash"].startswith("sha256:")
    assert output["usage_limit"]["active_credential_label_exported"] is False
    assert output["usage_limit"]["credential_values_exported"] is False
    assert output["usage_limit"]["raw_headers_exported"] is False
    assert output["usage_limit"]["raw_response_body_exported"] is False
    assert output["usage_limit"]["failover_review_only"] is True
    assert output["usage_limit"]["failover_executed"] is False
    assert output["usage_limit"]["failover_review_plan"] == {
        "required": True,
        "status": "privacy_review_required",
        "controller_surface": "provider_usage_limit_failover_review",
        "review_gate": "privacy-leakage-human-review",
        "reason": "credential_pool_failover_requires_private_credential_review",
        "credential_count": 3,
        "active_credential_label_present": True,
        "active_credential_label_exported": False,
        "credential_values_exported": False,
        "raw_headers_exported": False,
        "raw_response_body_exported": False,
        "failover_executed": False,
        "provider_runtime_launch_allowed": False,
        "safe_next_actions": [
            "wait_for_usage_window_reset",
            "open_privacy_review_for_credential_pool_failover",
            "replay_provider_runtime_preflight",
        ],
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
    }
    assert output["runtime"]["runner_invoked"] is False
    assert output["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["claude-code"],
            "value_recorded": False,
            "code": "provider_usage_limit_exhausted",
            "scope": "provider_usage_limit",
            "severity": "blocker",
            "action": "wait for the provider usage window reset or route credential-pool failover through privacy review before retry",
            "response_status": 429,
            "rate_limited": True,
            "window_count": 2,
            "exhausted_window_count": 1,
            "credential_pool_configured": True,
            "credential_count": 3,
            "failover_review_only": True,
            "failover_executed": False,
            "failover_review_plan": {
                "required": True,
                "status": "privacy_review_required",
                "controller_surface": "provider_usage_limit_failover_review",
                "review_gate": "privacy-leakage-human-review",
                "reason": "credential_pool_failover_requires_private_credential_review",
                "credential_count": 3,
                "active_credential_label_present": True,
                "active_credential_label_exported": False,
                "credential_values_exported": False,
                "raw_headers_exported": False,
                "raw_response_body_exported": False,
                "failover_executed": False,
                "provider_runtime_launch_allowed": False,
                "safe_next_actions": [
                    "wait_for_usage_window_reset",
                    "open_privacy_review_for_credential_pool_failover",
                    "replay_provider_runtime_preflight",
                ],
                "replay_commands": [
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
                ],
            },
            "raw_headers_exported": False,
            "raw_response_body_exported": False,
        }
    ]
    assert output["supervisor_replay"]["decision"] == "blocked_before_provider_launch"
    assert output["supervisor_replay"]["provider_runtime_launch_allowed"] is False
    assert output["operator_recovery_plan"]["decision"] == "blocked_recovery_required"
    assert output["operator_recovery_plan"]["next_action"] == "resolve_recovery_steps_then_replay"
    assert output["operator_recovery_plan"]["recovery_hint_codes"] == ["provider_usage_limit_exhausted"]
    assert output["operator_recovery_plan"]["recovery_steps"] == [
        {
            "code": "provider_usage_limit_exhausted",
            "scope": "provider_usage_limit",
            "severity": "blocker",
            "affected_preflight_count": 1,
            "provider_harness_count": 1,
            "action": "wait for the provider usage window reset or route credential-pool failover through privacy review before retry",
            "privacy_review_required": True,
            "value_recorded": False,
        }
    ]
    assert output["operator_recovery_plan"]["provider_runtime_launch_allowed"] is False
    assert output["operator_recovery_plan"]["remote_execution_allowed"] is False
    assert output["operator_recovery_plan"]["raw_preflight_inputs_exported"] is False
    assert "PRIVATE_PROVIDER_429_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CREDENTIAL_LABEL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_5H_RESET_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_WEEKLY_RESET_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RETRY_AFTER_DO_NOT_EXPORT" not in serialized


def test_provider_runtime_preflight_blocks_missing_or_malformed_model_command_before_launch():
    missing_fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_omnigent_model_command_missing.json"
    missing_fixture = json.loads(missing_fixture_path.read_text(encoding="utf-8"))

    missing = evaluate_harness_behavior(
        str(missing_fixture["behavior"]),
        missing_fixture["input"],
        source_path=missing_fixture_path,
    )
    malformed = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-omnigent-model-command-malformed",
            "provider": {
                "name": "omnigent-yaml-agent",
                "harness": "omnigent",
                "model_command_required": True,
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "model_command": "PRIVATE_MODEL_COMMAND_DO_NOT_EXPORT",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_model_command_malformed_inline.json",
    )
    configured = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-omnigent-model-command-configured",
            "provider": {
                "name": "omnigent-yaml-agent",
                "harness": "omnigent",
                "model_command_required": True,
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "model_command": ["omnigent", "run", "--agent", "PRIVATE_AGENT_NAME_DO_NOT_EXPORT"],
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_model_command_configured_inline.json",
    )
    serialized = json.dumps({"missing": missing, "malformed": malformed, "configured": configured}, sort_keys=True)

    assert missing["route_status"] == "blocked"
    assert missing["failure_mode"] == "provider_model_command_missing"
    assert missing["runtime"]["runner_invoked"] is False
    assert missing["model_command"] == {
        "required": True,
        "configured": False,
        "ok": False,
        "failure_mode": "provider_model_command_missing",
        "command_shape_valid": False,
        "command_arg_count": 0,
        "command_hashes": [],
        "raw_command_exported": False,
        "diagnostics": ["provider model command is required but was not configured"],
    }
    assert missing["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_model_command_missing",
            "scope": "provider_model_command",
            "severity": "blocker",
            "action": "configure a non-empty provider model command list before launching the harness",
            "command_required": True,
            "command_configured": False,
            "command_arg_count": 0,
        }
    ]
    assert missing["supervisor_replay"] == {
        "ready_for_provider_launch": False,
        "ready_for_local_replay": False,
        "decision": "blocked_before_provider_launch",
        "reason": "provider_model_command_missing",
        "route_status": "blocked",
        "recovery_hint_codes": ["provider_model_command_missing"],
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_input_exported": False,
        "raw_diagnostics_exported": False,
        "degraded_replay_only": False,
    }

    assert malformed["route_status"] == "blocked"
    assert malformed["failure_mode"] == "provider_model_command_malformed"
    assert malformed["runtime"]["runner_invoked"] is False
    assert malformed["model_command"]["configured"] is True
    assert malformed["model_command"]["command_shape_valid"] is False
    assert malformed["model_command"]["command_hashes"] == []
    assert malformed["model_command"]["raw_command_exported"] is False

    assert configured["route_status"] == "passed"
    assert configured["failure_mode"] == "none"
    assert configured["runtime"]["runner_invoked"] is True
    assert configured["model_command"]["ok"] is True
    assert configured["model_command"]["command_arg_count"] == 4
    assert len(configured["model_command"]["command_hashes"]) == 4
    assert all(command_hash.startswith("sha256:") for command_hash in configured["model_command"]["command_hashes"])

    assert "PRIVATE_MODEL_COMMAND_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_AGENT_NAME_DO_NOT_EXPORT" not in serialized
    assert "omnigent run" not in serialized


def test_provider_runtime_preflight_blocks_apple_silicon_brew_linkage_before_launch():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_apple_silicon_brew_jiter_linkage.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_install_linkage_unresolved"
    assert output["runtime"]["runner_invoked"] is False
    assert output["install_linkage"] == {
        "required": True,
        "observed": True,
        "ok": False,
        "failure_mode": "provider_install_linkage_unresolved",
        "package_manager": "brew",
        "platform": "darwin",
        "architecture": "arm64",
        "apple_silicon_homebrew": True,
        "homebrew_prefix_hash": output["install_linkage"]["homebrew_prefix_hash"],
        "homebrew_prefix_exported": False,
        "library_count": 1,
        "unresolved_rpath_count": 1,
        "relink_failure_count": 1,
        "records": output["install_linkage"]["records"],
        "raw_paths_exported": False,
        "raw_install_names_exported": False,
        "diagnostics": [
            "Apple Silicon Homebrew install linkage has unresolved rpath or relink failures; block provider launch until relinked or worked around"
        ],
    }
    assert output["install_linkage"]["homebrew_prefix_hash"].startswith("sha256:")
    assert output["install_linkage"]["records"] == [
        {
            "name": "jiter",
            "path_hash": output["install_linkage"]["records"][0]["path_hash"],
            "path_recorded": False,
            "install_name_hash": output["install_linkage"]["records"][0]["install_name_hash"],
            "install_name_recorded": False,
            "unresolved_rpath": True,
            "relink_failed": True,
            "headerpad_failure": False,
            "relink_error_hash": output["install_linkage"]["records"][0]["relink_error_hash"],
            "relink_error_recorded": False,
        }
    ]
    assert output["install_linkage"]["records"][0]["path_hash"].startswith("sha256:")
    assert output["install_linkage"]["records"][0]["install_name_hash"].startswith("sha256:")
    assert output["install_linkage"]["records"][0]["relink_error_hash"].startswith("sha256:")
    assert output["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_install_linkage_unresolved",
            "scope": "provider_install_linkage",
            "severity": "blocker",
            "action": "repair or relink Apple Silicon Homebrew dynamic libraries before launching the provider runtime",
            "package_manager": "brew",
            "platform": "darwin",
            "architecture": "arm64",
            "apple_silicon_homebrew": True,
            "library_count": 1,
            "unresolved_rpath_count": 1,
            "relink_failure_count": 1,
            "raw_paths_exported": False,
            "raw_install_names_exported": False,
        }
    ]
    assert output["supervisor_replay"]["decision"] == "blocked_before_provider_launch"
    assert output["supervisor_replay"]["recovery_hint_codes"] == ["provider_install_linkage_unresolved"]
    assert "PRIVATE_HOMEBREW_PREFIX_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_DYLIB_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_RELINK_ERROR_DO_NOT_EXPORT" not in serialized
    assert "@rpath/jiter.dylib" not in serialized


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


def test_mock_e2e_runner_tier_fails_when_required_ask_boundary_is_missing():
    output = evaluate_harness_behavior(
        "mock_e2e_runner_tier",
        {
            "task_id": "fixture-mock-e2e-missing-ask-boundary",
            "mock_only": True,
            "provider": {"enabled": False},
            "runner_tiers": [
                {
                    "name": "host-native",
                    "lane": "host_native",
                    "mocked": True,
                    "steps": [{"id": "host", "observed": "host-native mocked journey"}],
                    "operations": [{"name": "shell_command", "mocked": True}],
                },
                {
                    "name": "miscellaneous",
                    "lane": "miscellaneous",
                    "mocked": True,
                    "steps": [{"id": "misc", "observed": "miscellaneous mocked journey"}],
                    "operations": [{"name": "metadata", "mocked": True}],
                },
            ],
            "approval_boundary": {
                "required": True,
                "policy_hook": {
                    "governed": True,
                    "server_url_configured": True,
                    "event_phase": "TOOL_CALL",
                    "verdict": {
                        "review_required": False,
                        "reason": "operator_allow",
                    },
                },
                "tool_call": {
                    "name": "Bash",
                    "transport": "native",
                    "arguments": {"command": "PRIVATE_ALLOWED_COMMAND_DO_NOT_EXPORT"},
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_e2e_missing_ask_boundary_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["approval_boundary"] == {
        "required": True,
        "passed": False,
        "route_status": "passed",
        "failure_mode": "approval_path_missing",
        "ask_preserved": False,
        "controller_surface": "none",
        "tool_executed": False,
        "raw_payload_exported": False,
    }
    assert output["failure_mode"] == "approval_path_missing"
    assert "PRIVATE_ALLOWED_COMMAND_DO_NOT_EXPORT" not in serialized


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


def test_mock_llm_workflow_route_validates_chat_completions_contract_without_bodies():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "mock_llm_chat_completions_contract.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["mock_llm"]["call_count"] == 2
    assert output["mock_llm"]["chat_completions"] == {
        "enabled": True,
        "ok": True,
        "failure_mode": "none",
        "endpoint": "/v1/chat/completions",
        "request_count": 2,
        "streaming_request_count": 1,
        "non_streaming_request_count": 1,
        "json_response_count": 1,
        "sse_response_count": 1,
        "provider_preflight": {
            "ok": True,
            "failure_mode": "none",
            "token_required": True,
            "token_present": False,
            "base_url_present": True,
            "mock_base_url": True,
            "allow_mock_auth": True,
            "diagnostics": [],
            "secret_values_exported": False,
        },
        "model_echoed": True,
        "format_mismatch_count": 0,
        "diagnostics": [],
        "request_bodies_exported": False,
        "response_bodies_exported": False,
    }
    assert "PRIVATE_CHAT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_STREAMING_CHAT_BODY_DO_NOT_EXPORT" not in serialized
    assert "http://127.0.0.1:12345" not in serialized


def test_mock_llm_workflow_route_distinguishes_chat_completions_mock_contract_failure():
    raw_input = {
        "task_id": "fixture-mock-llm-chat-completions-format-drift",
        "provider": {
            "name": "openai-agents",
            "enabled": False,
            "protocol": "chat_completions",
            "base_url": "http://127.0.0.1:12345/v1",
            "mock_base_url": True,
            "token_required": True,
            "allow_mock_auth": True,
        },
        "mock_llm": {
            "enabled": True,
            "model": "mock-chat-model",
            "responses": [
                {
                    "content": "PRIVATE_CHAT_RESPONSE_DO_NOT_EXPORT",
                    "response_format": "sse",
                }
            ],
        },
        "mock_server_contract": {
            "enabled": True,
            "endpoint": "/v1/chat/completions",
            "base_url": "http://127.0.0.1:12345/v1",
            "mock_base_url": True,
            "allow_mock_auth": True,
            "requests": [
                {
                    "model": "mock-chat-model",
                    "stream": False,
                    "messages": "PRIVATE_CHAT_BODY_DO_NOT_EXPORT",
                }
            ],
        },
        "workflow": {
            "steps": [
                {"id": "non-streaming-chat", "model": "mock-chat-model"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_chat_completions_format_drift_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "chat_completions_response_format_mismatch"
    assert output["mock_llm"]["chat_completions"]["provider_preflight"]["ok"] is True
    assert output["mock_llm"]["chat_completions"]["format_mismatch_count"] == 1
    assert output["mock_llm"]["chat_completions"]["diagnostics"] == [
        "chat/completions mock response format must match each stream flag"
    ]
    assert "PRIVATE_CHAT_RESPONSE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHAT_BODY_DO_NOT_EXPORT" not in serialized


def test_mock_llm_workflow_route_distinguishes_chat_completions_provider_preflight_failure():
    raw_input = {
        "task_id": "fixture-mock-llm-chat-completions-provider-preflight",
        "provider": {
            "name": "openai-agents",
            "enabled": False,
            "protocol": "chat_completions",
            "base_url": "http://127.0.0.1:12345/v1",
            "mock_base_url": True,
            "token_required": True,
            "token_present": False,
            "allow_mock_auth": False,
        },
        "mock_llm": {
            "enabled": True,
            "model": "mock-chat-model",
            "responses": [{"content": "PRIVATE_CHAT_RESPONSE_DO_NOT_EXPORT"}],
        },
        "mock_server_contract": {
            "enabled": True,
            "endpoint": "/v1/chat/completions",
            "base_url": "http://127.0.0.1:12345/v1",
            "mock_base_url": True,
            "token_required": True,
            "allow_mock_auth": False,
            "requests": [
                {
                    "model": "mock-chat-model",
                    "stream": False,
                    "messages": "PRIVATE_CHAT_BODY_DO_NOT_EXPORT",
                }
            ],
        },
        "workflow": {
            "steps": [
                {"id": "non-streaming-chat", "model": "mock-chat-model"},
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_chat_completions_provider_preflight_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "provider_token_preflight_failed"
    assert output["mock_llm"]["chat_completions"]["format_mismatch_count"] == 0
    assert output["mock_llm"]["chat_completions"]["provider_preflight"] == {
        "ok": False,
        "failure_mode": "provider_token_preflight_failed",
        "token_required": True,
        "token_present": False,
        "base_url_present": True,
        "mock_base_url": True,
        "allow_mock_auth": False,
        "diagnostics": ["provider token is required unless mock auth is explicitly allowed"],
        "secret_values_exported": False,
    }
    assert "PRIVATE_CHAT_RESPONSE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHAT_BODY_DO_NOT_EXPORT" not in serialized
    assert "OPENAI_API_KEY" not in serialized


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
                        "tool_calls": [{"name": "record_validation", "arguments": '{"ok": true}'}],
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


def test_provider_runtime_recovery_summary_aggregates_body_free_hints():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_recovery_summary_blocked_and_degraded.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_runtime_recovery_required"
    assert output["status_counts"] == {"passed": 0, "degraded": 1, "blocked": 5}
    assert output["runner_invoked_count"] == 1
    assert output["blocked_failure_modes"] == [
        "native_terminal_timeout_risk",
        "provider_install_linkage_unresolved",
        "provider_usage_limit_exhausted",
        "review_model_unavailable",
        "url_safety_preflight_failed",
    ]
    assert [hint["code"] for hint in output["recovery_hints"]] == [
        "browser_configure_checks_skipped",
        "mock_auth_placeholder_used",
        "native_terminal_timeout_risk",
        "provider_install_linkage_unresolved",
        "provider_usage_limit_exhausted",
        "review_model_unavailable",
        "url_safety_preflight_failed",
    ]
    assert all(hint["value_recorded"] is False for hint in output["recovery_hints"])
    assert output["activation_gate"] == {
        "controller_surface": "provider_runtime_recovery_summary",
        "activation_scope": "local_replay_only",
        "decision": "blocked_before_provider_launch",
        "reason": "provider_runtime_recovery_required",
        "provider_runtime_launch_allowed": False,
        "local_validation_required": True,
    }
    assert output["supervisor_readiness"] == {
        "ready_for_supervisor_promotion": False,
        "ready_for_supervisor_local_replay": False,
        "decision": "blocked_before_supervisor_promotion",
        "reason": "provider_runtime_recovery_required",
        "success_status": {
            "misleading_success_guardrail": True,
            "status_label": "provider_runtime_blocked",
            "reason": "provider_runtime_recovery_required",
            "success_claim_allowed": False,
            "operator_action_required": True,
            "local_replay_allowed": False,
            "provider_runtime_launch_allowed": False,
            "body_free_diagnostics_only": True,
        },
        "preflight_count": 6,
        "status_counts": {"passed": 0, "degraded": 1, "blocked": 5},
        "blocked_failure_modes": [
            "native_terminal_timeout_risk",
            "provider_install_linkage_unresolved",
            "provider_usage_limit_exhausted",
            "review_model_unavailable",
            "url_safety_preflight_failed",
        ],
        "degraded_provider_count": 1,
        "recovery_hint_codes": [
            "browser_configure_checks_skipped",
            "mock_auth_placeholder_used",
            "native_terminal_timeout_risk",
            "provider_install_linkage_unresolved",
            "provider_usage_limit_exhausted",
            "review_model_unavailable",
            "url_safety_preflight_failed",
        ],
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
    }
    assert output["operator_recovery_plan"]["decision"] == "blocked_recovery_required"
    assert output["operator_recovery_plan"]["reason"] == "provider_runtime_recovery_required"
    assert output["operator_recovery_plan"]["next_action"] == "resolve_recovery_steps_then_replay"
    assert output["operator_recovery_plan"]["preflight_count"] == 6
    assert output["operator_recovery_plan"]["status_counts"] == {"passed": 0, "degraded": 1, "blocked": 5}
    assert output["operator_recovery_plan"]["recovery_step_count"] == 7
    assert output["operator_recovery_plan"]["recovery_hint_codes"] == [
        "browser_configure_checks_skipped",
        "mock_auth_placeholder_used",
        "native_terminal_timeout_risk",
        "provider_install_linkage_unresolved",
        "provider_usage_limit_exhausted",
        "review_model_unavailable",
        "url_safety_preflight_failed",
    ]
    assert output["operator_recovery_plan"]["recovery_hint_code_hashes"] == [
        stable_text_hash(code) for code in output["operator_recovery_plan"]["recovery_hint_codes"]
    ]
    assert output["operator_recovery_plan"]["recovery_steps"][4]["privacy_review_required"] is True
    assert all(step["value_recorded"] is False for step in output["operator_recovery_plan"]["recovery_steps"])
    assert output["operator_recovery_plan"]["provider_runtime_launch_allowed"] is False
    assert output["operator_recovery_plan"]["remote_execution_allowed"] is False
    assert output["operator_recovery_plan"]["raw_provider_values_exported"] is False
    assert output["privacy"] == {
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_urls_exported": False,
        "raw_paths_exported": False,
        "env_values_exported": False,
        "env_key_names_exported": False,
        "secret_values_exported": False,
    }
    assert "~/.local/bin/claude" not in serialized
    assert "127.0.0.1" not in serialized
    assert "PRIVATE_REVIEW_MODEL_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_PROVIDER_429_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HOMEBREW_PREFIX_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_DYLIB_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_RELINK_ERROR_DO_NOT_EXPORT" not in serialized
    assert "@rpath/jiter.dylib" not in serialized
    assert "PRIVATE_CREDENTIAL_LABEL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_5H_RESET_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RETRY_AFTER_DO_NOT_EXPORT" not in serialized

    command_gap = evaluate_harness_behavior(
        "provider_runtime_recovery_summary",
        {
            "task_id": "fixture-provider-runtime-recovery-summary-model-command",
            "preflights": [
                {
                    "provider": {
                        "name": "omnigent-yaml-agent",
                        "harness": "omnigent",
                        "model_command_required": True,
                    },
                    "runtime": {
                        "platform": "linux",
                        "launch_transport": "subprocess",
                    },
                    "runner_env": {
                        "parent_env_keys": ["PATH"],
                        "allowlist": ["PATH"],
                    },
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_recovery_summary_model_command_inline.json",
    )

    assert command_gap["route_status"] == "blocked"
    assert command_gap["blocked_failure_modes"] == ["provider_model_command_missing"]
    assert command_gap["runner_invoked_count"] == 0
    assert command_gap["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_model_command_missing",
            "scope": "provider_model_command",
            "severity": "blocker",
            "action": "configure a non-empty provider model command list before launching the harness",
            "command_required": True,
            "command_configured": False,
            "command_arg_count": 0,
        }
    ]
    assert "OPENAI_API_KEY" not in serialized

    degraded_only = evaluate_harness_behavior(
        "provider_runtime_recovery_summary",
        {
            "task_id": "fixture-provider-runtime-recovery-summary-degraded-only",
            "preflights": [
                {
                    "provider": {
                        "name": "openai-agents",
                        "harness": "openai-agents",
                        "auth_env_key": "OPENAI_API_KEY",
                        "required_env_keys": ["OPENAI_API_KEY"],
                    },
                    "runtime": {
                        "platform": "linux",
                        "cli_resolved_in_runner": True,
                        "launch_transport": "subprocess",
                    },
                    "runner_env": {
                        "parent_env_keys": ["PATH"],
                        "allowlist": ["PATH"],
                    },
                    "mock_llm": {
                        "enabled": True,
                        "auth_placeholder": True,
                    },
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_recovery_summary_degraded_only_inline.json",
    )

    assert degraded_only["route_status"] == "degraded"
    assert degraded_only["supervisor_readiness"]["ready_for_supervisor_promotion"] is False
    assert degraded_only["supervisor_readiness"]["ready_for_supervisor_local_replay"] is True
    assert degraded_only["supervisor_readiness"]["decision"] == "ready_for_supervisor_degraded_local_replay"
    assert degraded_only["supervisor_readiness"]["reason"] == "degraded_provider_runtime_replay_only"
    assert degraded_only["operator_recovery_plan"]["decision"] == "degraded_local_replay_only"
    assert degraded_only["operator_recovery_plan"]["next_action"] == "review_degraded_steps_then_replay"
    assert degraded_only["operator_recovery_plan"]["provider_runtime_launch_allowed"] is False
    assert degraded_only["operator_recovery_plan"]["remote_execution_allowed"] is False
    assert degraded_only["supervisor_readiness"]["success_status"] == {
        "misleading_success_guardrail": True,
        "status_label": "provider_runtime_degraded_replay_only",
        "reason": "degraded_provider_runtime_replay_only",
        "success_claim_allowed": False,
        "operator_action_required": True,
        "local_replay_allowed": True,
        "provider_runtime_launch_allowed": False,
        "body_free_diagnostics_only": True,
    }
    assert degraded_only["supervisor_readiness"]["provider_runtime_launch_allowed"] is False
    assert degraded_only["supervisor_readiness"]["recovery_hint_codes"] == ["mock_auth_placeholder_used"]


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
    assert output["interrupt"]["async_drain"] == {
        "declared": True,
        "required": True,
        "blocked": True,
        "steering_sent": True,
        "timeout_ms": 500.0,
        "cancelled_timely": True,
        "progressed_timely": False,
        "broke_drain": True,
        "outcome": "cancelled",
        "failure_mode": "none",
        "passed": True,
    }
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


def test_mock_llm_workflow_route_fails_when_steering_cannot_break_blocked_async_drain():
    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        {
            "task_id": "fixture-mock-llm-blocked-async-drain",
            "provider": {"name": "external-chat-provider", "enabled": False},
            "session": {
                "id": "PRIVATE_REBUILT_SESSION_DO_NOT_EXPORT",
                "previous_id": "PRIVATE_INTERRUPTED_SESSION_DO_NOT_EXPORT",
                "isolation_required": True,
            },
            "interrupt": {
                "required": True,
                "previous_session_id": "PRIVATE_INTERRUPTED_SESSION_DO_NOT_EXPORT",
                "rebuilt_session_id": "PRIVATE_REBUILT_SESSION_DO_NOT_EXPORT",
                "previous_agent_id": "PRIVATE_AGENT_BEFORE_INTERRUPT_DO_NOT_EXPORT",
                "rebuilt_agent_id": "PRIVATE_AGENT_AFTER_INTERRUPT_DO_NOT_EXPORT",
                "previous_conversation_id": "PRIVATE_CONVERSATION_BEFORE_INTERRUPT_DO_NOT_EXPORT",
                "rebuilt_conversation_id": "PRIVATE_CONVERSATION_AFTER_INTERRUPT_DO_NOT_EXPORT",
                "pending_idle_message_ids": ["PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT"],
                "replayed_idle_message_ids": ["PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT"],
                "async_drain": {
                    "required": True,
                    "blocked": True,
                    "steering_sent": True,
                    "timeout_ms": 250,
                    "cancelled": False,
                    "progressed": False,
                },
            },
            "mock_llm": {
                "enabled": True,
                "model": "mock-local-llm",
                "response_queues": {"mock-local-llm": [{"content": "interrupted session rebuilt"}]},
            },
            "workflow": {"steps": [{"id": "rebuild-session", "expect_contains": "rebuilt"}]},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_blocked_async_drain_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "interrupt_replay_failed"
    assert output["interrupt"]["async_drain"]["failure_mode"] == "steering_did_not_break_drain"
    assert output["interrupt"]["async_drain"]["broke_drain"] is False
    assert output["interrupt"]["async_drain"]["outcome"] == "blocked"
    assert output["interrupt"]["raw_ids_exported"] is False
    assert "PRIVATE_REBUILT_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_INTERRUPTED_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_AGENT_BEFORE_INTERRUPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CONVERSATION_BEFORE_INTERRUPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_IDLE_MESSAGE_ONE_DO_NOT_EXPORT" not in serialized


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


def test_mock_llm_workflow_route_fails_when_resolver_miss_clones_parent_agent():
    raw_input = {
        "task_id": "fixture-mock-llm-named-subagent-parent-clone",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "sub_agents": {
            "parent_name": "PRIVATE_PARENT_AGENT_DO_NOT_EXPORT",
            "agents": [
                {
                    "name": "PRIVATE_CHILD_AGENT_DO_NOT_EXPORT",
                    "expected_response_key": "child-queue",
                    "turn_session_ids": ["PRIVATE_CHILD_SESSION_DO_NOT_EXPORT"],
                    "persistence_required": True,
                    "resolution": {
                        "persisted_agent_names": ["PRIVATE_PARENT_AGENT_DO_NOT_EXPORT"],
                        "resolved_agent_name": "PRIVATE_PARENT_AGENT_DO_NOT_EXPORT",
                    },
                }
            ],
        },
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "child-queue": [{"content": "child turn"}],
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "child-turn",
                    "agent": "PRIVATE_CHILD_AGENT_DO_NOT_EXPORT",
                    "response_key": "child-queue",
                    "expect_contains": "child",
                }
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_named_subagent_parent_clone_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)
    resolution = output["sub_agents"]["agents"][0]["resolution"]

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "sub_agent_mock_route_failed"
    assert output["sub_agents"]["resolution_guard_passed"] is False
    assert resolution["resolver_miss"] is True
    assert resolution["fallback_to_parent_detected"] is True
    assert resolution["fail_closed_applied"] is False
    assert resolution["guard_passed"] is False
    assert resolution["decision"] == "blocked_required"
    assert resolution["failure_mode"] == "parent_clone_fallback"
    assert resolution["raw_agent_names_exported"] is False
    assert "PRIVATE_PARENT_AGENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_AGENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_SESSION_DO_NOT_EXPORT" not in serialized


def test_mock_llm_workflow_route_allows_resolver_miss_when_blocked_before_spawn():
    raw_input = {
        "task_id": "fixture-mock-llm-named-subagent-resolver-miss-blocked",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "sub_agents": {
            "parent_name": "PRIVATE_PARENT_AGENT_DO_NOT_EXPORT",
            "agents": [
                {
                    "name": "PRIVATE_CHILD_AGENT_DO_NOT_EXPORT",
                    "expected_response_key": "child-queue",
                    "turn_session_ids": ["PRIVATE_CHILD_SESSION_DO_NOT_EXPORT"],
                    "persistence_required": True,
                    "resolution": {
                        "resolver_miss": True,
                        "blocked_before_spawn": True,
                    },
                }
            ],
        },
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "child-queue": [{"content": "child turn"}],
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "child-turn",
                    "agent": "PRIVATE_CHILD_AGENT_DO_NOT_EXPORT",
                    "response_key": "child-queue",
                    "expect_contains": "child",
                }
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_named_subagent_resolver_miss_blocked_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)
    resolution = output["sub_agents"]["agents"][0]["resolution"]

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["sub_agents"]["resolution_guard_passed"] is True
    assert resolution["resolver_miss"] is True
    assert resolution["fallback_to_parent_detected"] is False
    assert resolution["fail_closed_applied"] is True
    assert resolution["guard_passed"] is True
    assert resolution["decision"] == "blocked_before_spawn"
    assert resolution["failure_mode"] == "none"
    assert "PRIVATE_PARENT_AGENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_AGENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CHILD_SESSION_DO_NOT_EXPORT" not in serialized


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
        "runner_workspace_root_hash": None,
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


def test_workspace_changes_panel_fails_changed_file_outside_runner_workspace_without_exporting_paths():
    output = evaluate_harness_behavior(
        "workspace_changes_panel",
        {
            "task_id": "fixture-outside-runner-workspace-change-panel",
            "workspace": {
                "is_git_repo": True,
                "runner_workspace_configured": True,
                "runner_workspace_root": "PRIVATE_RUNNER_WORKSPACE_ROOT_DO_NOT_EXPORT",
            },
            "performed_edits": [
                {
                    "edit_id": "outside-runner-write",
                    "origin": "native_harness",
                    "path": "PRIVATE_OUTSIDE_RUNNER_WORKSPACE_PATH_DO_NOT_EXPORT.md",
                    "content": "PRIVATE_OUTSIDE_RUNNER_WORKSPACE_CONTENT_DO_NOT_EXPORT",
                    "exists_on_disk": True,
                    "record_change_observed": True,
                }
            ],
            "changes_panel": {
                "available": True,
                "entries": [
                    {
                        "edit_id": "outside-runner-write",
                        "kind": "changed_file",
                        "path": "PRIVATE_OUTSIDE_RUNNER_WORKSPACE_PATH_DO_NOT_EXPORT.md",
                        "visible": True,
                    }
                ],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "workspace_changes_panel_outside_runner_workspace_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "edit_outside_runner_workspace"
    assert output["workspace"]["runner_workspace_root_hash"].startswith("sha256:")
    assert output["edits"]["outside_runner_workspace_edit_ids"] == ["outside-runner-write"]
    assert output["edits"]["outside_runner_workspace_panel_ids"] == ["outside-runner-write"]
    assert "PRIVATE_RUNNER_WORKSPACE_ROOT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OUTSIDE_RUNNER_WORKSPACE_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OUTSIDE_RUNNER_WORKSPACE_CONTENT_DO_NOT_EXPORT" not in serialized


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


def test_native_policy_preserves_midflight_ask_for_controller_resolution_without_exporting_bodies():
    cases = [
        ("TOOL_CALL", "TOOL_CALL"),
        ("TOOL_RESULT", "TOOL_RESULT"),
        ("OUTPUT", "OUTPUT"),
        ("SUB_AGENT", "SUB_AGENT"),
    ]

    for event_phase, event_phase_kind in cases:
        output = evaluate_harness_behavior(
            "native_tool_call_policy",
            {
                "task_id": f"fixture-native-policy-ask-{event_phase.lower()}",
                "policy_hook": {
                    "governed": True,
                    "session_id": "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT",
                    "server_url_configured": True,
                    "event_phase": event_phase,
                    "failure_mode": "none",
                    "verdict": {
                        "review_required": True,
                        "reason": "operator_ask",
                    },
                },
                "tool_call": {
                    "name": "Bash",
                    "transport": "native",
                    "arguments": {"command": "PRIVATE_COMMAND_BODY_DO_NOT_EXPORT"},
                },
            },
            source_path=LOCAL_EVAL_FIXTURE_DIR / f"native_policy_ask_{event_phase.lower()}_inline.json",
        )
        serialized = json.dumps(output, sort_keys=True)

        assert output["route_status"] == "review_only"
        assert output["failure_mode"] == "policy_review_required"
        assert output["policy_hook"]["event_phase_kind"] == event_phase_kind
        assert output["policy_hook"]["interactive_ask_supported"] is True
        assert output["policy_hook"]["fail_closed_applied"] is False
        assert output["permission"]["decision"] == "review_required"
        assert output["permission"]["reason"] == "policy_review_required:operator_ask"
        assert output["approval"] == {
            "ask_preserved": True,
            "controller_surface": "interactive_policy_ask",
            "resolution": "pending",
            "resolved_by_explicit_verdict": False,
            "raw_payload_exported": False,
        }
        assert output["safety"]["tool_executed"] is False
        assert "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT" not in serialized
        assert "PRIVATE_COMMAND_BODY_DO_NOT_EXPORT" not in serialized


def test_native_policy_midflight_ask_resolves_only_with_explicit_approval_or_denial():
    approved = evaluate_harness_behavior(
        "native_tool_call_policy",
        {
            "policy_hook": {
                "governed": True,
                "session_id": "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT",
                "server_url_configured": True,
                "event_phase": "TOOL_RESULT",
                "verdict": {
                    "review_required": True,
                    "reason": "operator_ask",
                    "approval_resolution": "approved",
                },
            },
            "tool_call": {
                "name": "Write",
                "arguments": {"content": "PRIVATE_APPROVED_CONTENT_DO_NOT_EXPORT"},
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "native_policy_ask_approved_inline.json",
    )
    denied = evaluate_harness_behavior(
        "native_tool_call_policy",
        {
            "policy_hook": {
                "governed": True,
                "session_id": "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT",
                "server_url_configured": True,
                "event_phase": "OUTPUT",
                "approval_resolution": "denied",
                "verdict": {
                    "review_required": True,
                    "reason": "operator_ask",
                },
            },
            "tool_call": {
                "name": "Bash",
                "arguments": {"command": "PRIVATE_DENIED_COMMAND_DO_NOT_EXPORT"},
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "native_policy_ask_denied_inline.json",
    )
    serialized = json.dumps({"approved": approved, "denied": denied}, sort_keys=True)

    assert approved["route_status"] == "passed"
    assert approved["failure_mode"] == "none"
    assert approved["permission"]["decision"] == "allow"
    assert approved["permission"]["reason"] == "policy_approved:operator_ask"
    assert approved["approval"]["ask_preserved"] is False
    assert approved["approval"]["resolution"] == "approved"
    assert approved["approval"]["resolved_by_explicit_verdict"] is True
    assert approved["safety"]["tool_executed"] is True

    assert denied["route_status"] == "denied"
    assert denied["failure_mode"] == "policy_approval_denied"
    assert denied["permission"]["decision"] == "deny"
    assert denied["permission"]["reason"] == "policy_approval_denied:operator_ask"
    assert denied["approval"]["ask_preserved"] is False
    assert denied["approval"]["resolution"] == "denied"
    assert denied["approval"]["resolved_by_explicit_verdict"] is True
    assert denied["safety"]["tool_executed"] is False
    assert "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_APPROVED_CONTENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_DENIED_COMMAND_DO_NOT_EXPORT" not in serialized


def test_native_policy_ask_for_unknown_phase_keeps_fail_closed_regression():
    output = evaluate_harness_behavior(
        "native_tool_call_policy",
        {
            "policy_hook": {
                "governed": True,
                "session_id": "PRIVATE_POLICY_SESSION_DO_NOT_EXPORT",
                "server_url_configured": True,
                "event_phase": "UNKNOWN_PHASE",
                "verdict": {
                    "review_required": True,
                    "reason": "operator_ask",
                },
            },
            "tool_call": {"name": "Bash"},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "native_policy_ask_unknown_phase_inline.json",
    )

    assert output["route_status"] == "denied"
    assert output["failure_mode"] == "policy_ask_not_supported"
    assert output["permission"]["decision"] == "deny"
    assert output["permission"]["reason"] == "policy_ask_not_supported:operator_ask"
    assert output["policy_hook"]["event_phase_kind"] == "OTHER"
    assert output["policy_hook"]["interactive_ask_supported"] is False
    assert output["policy_hook"]["fail_closed_applied"] is True
    assert output["approval"]["ask_preserved"] is False
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
    assert payload["fixture_count"] == 10
    assert payload["pass_count"] == 10
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
    skill_route = results["proposal-interpretation-skill-route-provider-runtime-control"]
    truncated = results["proposal-interpretation-rejects-truncated-refs"]
    boundary = results["proposal-interpretation-policy-boundary"]
    max_proposals = results["proposal-interpretation-rejects-too-many-proposals"]
    current_wake = results["proposal-interpretation-visa-current-wake-agent-harness-eval"]

    assert agent_codex["passed"] is True
    assert agent_harness["passed"] is True
    assert accepted["passed"] is True
    assert malformed_json["passed"] is True
    assert rejected["passed"] is True
    assert skill_route["passed"] is True
    assert truncated["passed"] is True
    assert boundary["passed"] is True
    assert max_proposals["passed"] is True
    assert current_wake["passed"] is True
    assert all(assertion["passed"] for assertion in agent_codex["assertions"])
    assert all(assertion["passed"] for assertion in agent_harness["assertions"])
    assert all(assertion["passed"] for assertion in accepted["assertions"])
    assert all(assertion["passed"] for assertion in malformed_json["assertions"])
    assert all(assertion["passed"] for assertion in rejected["assertions"])
    assert all(assertion["passed"] for assertion in skill_route["assertions"])
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
        "provider_runtime_control",
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
