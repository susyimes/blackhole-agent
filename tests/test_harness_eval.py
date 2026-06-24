import json
from pathlib import Path

from blackhole_agent.harness_eval import (
    build_harness_comparison_report,
    evaluate_harness_behavior,
    run_local_harness_eval,
    stable_json_hash,
    stable_text_hash,
    skill_route_discovery_inspection_requirements,
    skill_route_discovery_provider_runtime_control,
    skill_route_discovery_provider_runtime_preflight_contract,
    skill_route_discovery_completion_consistency_guard,
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
    assert payload["fixture_count"] == 69
    assert payload["pass_count"] == 68
    assert payload["fail_count"] == 1
    assert payload["privacy"]["fixture_inputs_exported"] is False
    assert payload["privacy"]["supported_behaviors"] == [
        "external_harness_adapter_contract",
        "agent_harness_eval_lane",
        "agent_harness_provider_registration",
        "agent_workflow_route",
        "harness_run_summary",
        "headless_tool_roundtrip",
        "known_failure_metadata_preflight",
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
    assert results["external-harness-adapter-contract-databricks-genie"]["passed"] is True
    assert results["agent-workflow-route-orchestrator-inbox-delivery"]["passed"] is True
    assert results["agent-harness-eval-lane-general-agent-projects"]["passed"] is True
    assert results["agent-harness-eval-lane-visa-current-wake"]["passed"] is True
    assert results["agent-workflow-route-oneshot-marker-absent"]["passed"] is True
    assert results["agent-workflow-route-control-plane-replay"]["passed"] is True
    assert results["agent-workflow-route-control-plane-pass2-intake"]["passed"] is True
    assert results["agent-workflow-route-pr-migration-intake"]["passed"] is True
    assert results["agent-workflow-route-streamed-tool-boundary"]["passed"] is True
    assert results["agent-workflow-route-report-sections-missing"]["passed"] is True
    assert results["agent-harness-provider-registration-qwencode-missing-config"]["passed"] is True
    assert results["agent-harness-provider-registration-host-owner-mismatch"]["passed"] is True
    assert results["agent-workflow-route-recoverable-failure"]["passed"] is True
    assert results["agent-workflow-route-lifecycle-trace"]["passed"] is True
    assert results["agent-workflow-route-harness-owned-compaction"]["passed"] is True
    assert results["headless-tool-roundtrip-function-call"]["passed"] is True
    assert results["known-failure-metadata-preflight-removed"]["passed"] is True
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
    assert results["provider-runtime-preflight-claude-sdk-errno8-startup"]["passed"] is True
    assert results["provider-runtime-preflight-claude-long-status-prompt-scan"]["passed"] is True
    assert results["provider-runtime-preflight-native-claude-iterm2-tmux-timeout-risk"]["passed"] is True
    assert results["provider-runtime-preflight-approval-repark-pending"]["passed"] is True
    assert results["provider-runtime-preflight-codex-turn-auth-failure"]["passed"] is True
    assert results["provider-runtime-preflight-openai-agents-mock-auth"]["passed"] is True
    assert results["provider-runtime-preflight-openai-agents-no-worker-env-skip"]["passed"] is True
    assert results["provider-runtime-preflight-openrouter-harness-base-url-mismatch"]["passed"] is True
    assert results["provider-runtime-preflight-omnigent-model-command-missing"]["passed"] is True
    assert results["provider-runtime-preflight-omnigent-turn-context-desync"]["passed"] is True
    assert results["provider-runtime-preflight-runner-compat-bridge-missing"]["passed"] is True
    assert results["provider-runtime-preflight-non-openai-web-search-dispatch-missing"]["passed"] is True
    assert results["provider-runtime-preflight-wire-api-chat"]["passed"] is True
    assert results["provider-runtime-preflight-review-model-unavailable"]["passed"] is True
    assert results["provider-runtime-preflight-usage-limit-429"]["passed"] is True
    assert results["provider-runtime-recovery-summary-blocked-and-degraded"]["passed"] is True
    assert results["rendered-html-artifact-js-and-links"]["passed"] is True
    assert results["skill-route-discovery-lane-fablecodex"]["passed"] is True
    assert results["skill-route-discovery-lane-fork-lineage"]["passed"] is True
    assert results["skill-route-discovery-lane-pass4-closure"]["passed"] is True
    assert results["skill-route-discovery-lane-pass1-current-action"]["passed"] is True
    assert results["skill-route-discovery-lane-current-window-pass1"]["passed"] is True
    assert results["skill-route-discovery-current-pass-skill-shapes"]["passed"] is True
    assert results["skill-route-discovery-lane-pass2-window"]["passed"] is True
    assert results["skill-route-discovery-domain-threejs-probe"]["passed"] is True
    assert results["skill-route-discovery-provider-runtime-degraded-sample"]["passed"] is True
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
    assert "PRIVATE_ELICITATION_ID_DO_NOT_EXPORT" not in serialized
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
    assert "PRIVATE_PASS2_ROUTE_INTAKE_OBSERVATION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_COMPACTION_SUMMARY_REF_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_ASSISTANT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REVIEW_MODEL_ID_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REVIEW_PROMPT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_REVIEW_OUTPUT_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_PROVIDER_429_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_PROVIDER_401_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_PROVIDER_TOKEN_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_HOMEBREW_PREFIX_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_DYLIB_PATH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_JITER_RELINK_ERROR_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CLAUDE_SDK_EXECUTABLE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_ERRNO8_STARTUP_BODY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OMNIGENT_SESSION_REF_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OMNIGENT_RUNNER_LOG_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CREDENTIAL_LABEL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_5H_RESET_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_WEEKLY_RESET_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RETRY_AFTER_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RENDERED_HTML_BODY_DO_NOT_EXPORT" not in serialized
    assert "private-link-do-not-export" not in serialized
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/lyra81604/zhengxi-views" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized
    assert "https://github.com/visa/visa-vulnerability-agentic-harness" not in serialized
    assert "https://github.com/omnigent-ai/omnigent" not in serialized
    assert "https://openrouter.ai" not in serialized

    failing_assertions = results["fail-harness-summary"]["assertions"]
    assert failing_assertions[0]["passed"] is True
    assert failing_assertions[1] == {
        "path": "failure_mode",
        "expected": "none",
        "actual": "nonzero_exit",
        "passed": False,
        "failure_mode": "equals_mismatch",
    }


def test_agent_workflow_route_pr_migration_intake_deduplicates_and_recomputes_scope():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_pr_migration_intake.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    pr_intake = output["control_plane"]["intake"]["pull_request_events"]
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert pr_intake["event_count"] == 3
    assert pr_intake["duplicate_event_count"] == 1
    assert pr_intake["generic_or_untitled_event_count"] == 1
    assert pr_intake["usable_event_count"] == 1
    assert pr_intake["recomputed_scope_matches_unique_pr_events"] is True
    assert pr_intake["recomputed_gates_match_unique_pr_events"] is True
    assert pr_intake["recomputed_proposals_match_unique_pr_events"] is True
    assert pr_intake["raw_titles_exported"] is False
    assert pr_intake["raw_event_urls_exported"] is False
    assert "untitled pull request" not in serialized
    assert "https://github.com/omnigent-ai/omnigent/pull/1082" not in serialized


def test_provider_runtime_preflight_requires_chat_wire_api_route_evidence_before_launch():
    exercised = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-wire-api-chat-exercised",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "wire_api": "chat",
                "supported_wire_apis": ["chat", "responses"],
                "exercised_wire_apis": ["chat"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_wire_api_chat_exercised_inline.json",
    )
    unexercised = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-wire-api-chat-unexercised",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "wire_api": "chat",
                "supported_wire_apis": ["chat", "responses"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_wire_api_chat_unexercised_inline.json",
    )
    unsupported = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-wire-api-chat-unsupported",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "wire_api": "chat",
                "supported_wire_apis": ["responses"],
                "exercised_wire_apis": ["chat"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_wire_api_chat_unsupported_inline.json",
    )
    serialized = json.dumps(
        {"exercised": exercised, "unexercised": unexercised, "unsupported": unsupported},
        sort_keys=True,
    )

    assert exercised["route_status"] == "passed"
    assert exercised["wire_api"]["selected"] == "chat"
    assert exercised["wire_api"]["exercised"] is True
    assert exercised["wire_api"]["raw_value_exported"] is False
    assert exercised["runtime"]["runner_invoked"] is True

    assert unexercised["route_status"] == "blocked"
    assert unexercised["failure_mode"] == "provider_wire_api_unexercised"
    assert unexercised["runtime"]["runner_invoked"] is False
    assert unexercised["wire_api"]["exercise_required"] is True
    assert unexercised["wire_api"]["exercised"] is False
    assert unexercised["preflight"]["diagnostics"] == [
        "provider wire API was configured but not exercised by local route evidence"
    ]
    assert unexercised["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_wire_api_unexercised",
            "scope": "provider_wire_api",
            "severity": "blocker",
            "action": "configure a supported provider wire API and replay local route evidence before launching the harness",
            "wire_api_required": False,
            "wire_api_configured": True,
            "wire_api_selected": "chat",
            "wire_api_supported": True,
            "wire_api_exercise_required": True,
            "wire_api_exercised": False,
            "supported_wire_api_count": 2,
            "exercised_wire_api_count": 0,
            "runner_wire_api_configured": False,
            "runner_wire_api_selected": "unknown",
            "runner_wire_api_matches_config": True,
            "raw_value_exported": False,
            "runner_raw_value_exported": False,
        }
    ]
    assert unexercised["supervisor_replay"]["ready_for_provider_launch"] is False
    assert unexercised["supervisor_replay"]["recovery_hint_codes"] == ["provider_wire_api_unexercised"]

    assert unsupported["route_status"] == "blocked"
    assert unsupported["failure_mode"] == "provider_wire_api_unsupported"
    assert unsupported["wire_api"]["supported"] is False
    assert unsupported["wire_api"]["exercised"] is True

    assert "PRIVATE" not in serialized


def test_provider_runtime_preflight_blocks_non_openai_web_search_without_dispatch_handler():
    blocked = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-non-openai-web-search-missing",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "model_provider": "google",
                "tools": {
                    "builtins": [
                        {
                            "name": "web_search",
                            "arguments": "PRIVATE_WEB_SEARCH_ARGUMENTS_DO_NOT_EXPORT",
                        }
                    ]
                },
                "local_dispatch_tools": ["web_fetch"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR
        / "provider_runtime_preflight_non_openai_web_search_missing_inline.json",
    )
    ready = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-non-openai-web-search-ready",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "model_provider": "perplexity",
                "tools": {"builtins": ["web_search"]},
                "local_dispatch_tools": ["web_fetch", "web_search"],
                "dispatched_tools": ["web_search"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR
        / "provider_runtime_preflight_non_openai_web_search_ready_inline.json",
    )
    openai_passthrough = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-openai-web-search-native",
            "provider": {
                "name": "openai",
                "harness": "openai-agents",
                "model_provider": "openai",
                "tools": {"builtins": ["web_search"]},
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR
        / "provider_runtime_preflight_openai_web_search_native_inline.json",
    )
    serialized = json.dumps(
        {"blocked": blocked, "ready": ready, "openai": openai_passthrough},
        sort_keys=True,
    )

    assert blocked["route_status"] == "blocked"
    assert blocked["failure_mode"] == "provider_tool_dispatch_missing"
    assert blocked["runtime"]["runner_invoked"] is False
    assert blocked["tool_dispatch"]["provider_family"] == "google"
    assert blocked["tool_dispatch"]["web_search_enabled"] is True
    assert blocked["tool_dispatch"]["web_search_dispatch_required"] is True
    assert blocked["tool_dispatch"]["web_search_handler_registered"] is False
    assert blocked["tool_dispatch"]["web_search_dispatch_exercised"] is False
    assert blocked["tool_dispatch"]["raw_tool_config_exported"] is False
    assert blocked["tool_dispatch"]["tool_arguments_exported"] is False
    assert blocked["preflight"]["diagnostics"] == [
        "non-OpenAI web_search builtin has no local runner dispatch handler evidence"
    ]
    assert blocked["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_tool_dispatch_missing",
            "scope": "provider_tool_dispatch",
            "severity": "blocker",
            "action": (
                "register and locally replay a runner dispatch handler for non-OpenAI web_search "
                "before launching the harness"
            ),
            "provider_family": "google",
            "openai_native_passthrough": False,
            "web_search_enabled": True,
            "web_search_dispatch_required": True,
            "web_search_handler_registered": False,
            "web_search_dispatch_exercised": False,
            "enabled_tool_count": 1,
            "local_dispatch_tool_count": 1,
            "dispatched_tool_count": 0,
            "raw_tool_config_exported": False,
            "tool_arguments_exported": False,
        }
    ]
    assert blocked["supervisor_replay"]["recovery_hint_codes"] == ["provider_tool_dispatch_missing"]

    assert ready["route_status"] == "passed"
    assert ready["tool_dispatch"]["provider_family"] == "perplexity"
    assert ready["tool_dispatch"]["web_search_handler_registered"] is True
    assert ready["tool_dispatch"]["web_search_dispatch_exercised"] is True
    assert ready["runtime"]["runner_invoked"] is True

    assert openai_passthrough["route_status"] == "passed"
    assert openai_passthrough["tool_dispatch"]["openai_native_passthrough"] is True
    assert openai_passthrough["tool_dispatch"]["web_search_dispatch_required"] is False

    assert "PRIVATE_WEB_SEARCH_ARGUMENTS_DO_NOT_EXPORT" not in serialized


def test_provider_runtime_preflight_blocks_gateway_base_url_harness_mismatch_without_url_export():
    claude_mismatch = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-openrouter-claude-mismatch",
            "provider": {
                "name": "omnigent-claude-openrouter",
                "harness": "claude-code",
                "gateway": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_gateway_base_url_claude_mismatch_inline.json",
    )
    codex_match = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-openrouter-codex-match",
            "provider": {
                "name": "omnigent-codex-openrouter",
                "harness": "codex",
                "gateway": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_gateway_base_url_codex_match_inline.json",
    )
    serialized = json.dumps({"claude_mismatch": claude_mismatch, "codex_match": codex_match}, sort_keys=True)

    assert claude_mismatch["route_status"] == "blocked"
    assert claude_mismatch["failure_mode"] == "provider_gateway_base_url_harness_mismatch"
    assert claude_mismatch["gateway_base_url"]["gateway"] == "openrouter"
    assert claude_mismatch["gateway_base_url"]["harness_family"] == "claude"
    assert claude_mismatch["gateway_base_url"]["expected_endpoint"] == "anthropic_compatible_api"
    assert claude_mismatch["gateway_base_url"]["selected_endpoint"] == "openai_compatible_v1"
    assert claude_mismatch["gateway_base_url"]["endpoint_matches_harness"] is False
    assert claude_mismatch["gateway_base_url"]["raw_base_url_exported"] is False
    assert claude_mismatch["runtime"]["runner_invoked"] is False
    assert claude_mismatch["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["claude-code"],
            "value_recorded": False,
            "code": "provider_gateway_base_url_harness_mismatch",
            "scope": "provider_gateway_base_url",
            "severity": "blocker",
            "action": "configure the gateway base URL shape expected by the selected provider harness before launch",
            "gateway": "openrouter",
            "harness_family": "claude",
            "expected_endpoint": "anthropic_compatible_api",
            "selected_endpoint": "openai_compatible_v1",
            "endpoint_matches_harness": False,
            "base_url_configured": True,
            "base_url_recorded": False,
            "raw_base_url_exported": False,
        }
    ]

    assert codex_match["route_status"] == "passed"
    assert codex_match["gateway_base_url"]["harness_family"] == "codex"
    assert codex_match["gateway_base_url"]["expected_endpoint"] == "openai_compatible_v1"
    assert codex_match["gateway_base_url"]["selected_endpoint"] == "openai_compatible_v1"
    assert codex_match["gateway_base_url"]["endpoint_matches_harness"] is True
    assert codex_match["runtime"]["runner_invoked"] is True

    assert "https://openrouter.ai" not in serialized
    assert "api/v1" not in serialized


def test_provider_runtime_preflight_blocks_chat_config_that_resolves_to_responses_runner_route():
    mismatch = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-wire-api-chat-runner-mismatch",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "wire_api": "chat",
                "supported_wire_apis": ["chat", "responses"],
                "exercised_wire_apis": ["chat"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "generated_model_api": "openai-responses",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_wire_api_chat_runner_mismatch_inline.json",
    )
    ready = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-wire-api-chat-runner-ready",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "wire_api": "chat",
                "supported_wire_apis": ["chat", "responses"],
                "exercised_wire_apis": ["chat"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "generated_model_api": "openai-completions",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_wire_api_chat_runner_ready_inline.json",
    )
    serialized = json.dumps({"mismatch": mismatch, "ready": ready}, sort_keys=True)

    assert mismatch["route_status"] == "blocked"
    assert mismatch["failure_mode"] == "provider_wire_api_runner_mismatch"
    assert mismatch["runtime"]["runner_invoked"] is False
    assert mismatch["wire_api"]["selected"] == "chat"
    assert mismatch["wire_api"]["runner_selected"] == "responses"
    assert mismatch["wire_api"]["runner_matches_config"] is False
    assert mismatch["wire_api"]["runner_raw_value_exported"] is False
    assert mismatch["preflight"]["diagnostics"] == [
        "provider wire API was configured but resolved to a different runner route"
    ]
    assert mismatch["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_wire_api_runner_mismatch",
            "scope": "provider_wire_api",
            "severity": "blocker",
            "action": "configure a supported provider wire API and replay local route evidence before launching the harness",
            "wire_api_required": False,
            "wire_api_configured": True,
            "wire_api_selected": "chat",
            "wire_api_supported": True,
            "wire_api_exercise_required": True,
            "wire_api_exercised": True,
            "supported_wire_api_count": 2,
            "exercised_wire_api_count": 1,
            "runner_wire_api_configured": True,
            "runner_wire_api_selected": "responses",
            "runner_wire_api_matches_config": False,
            "raw_value_exported": False,
            "runner_raw_value_exported": False,
        }
    ]
    assert mismatch["supervisor_replay"]["recovery_hint_codes"] == ["provider_wire_api_runner_mismatch"]

    assert ready["route_status"] == "passed"
    assert ready["wire_api"]["selected"] == "chat"
    assert ready["wire_api"]["runner_selected"] == "chat"
    assert ready["wire_api"]["runner_matches_config"] is True
    assert ready["runtime"]["runner_invoked"] is True

    assert "openai-responses" not in serialized
    assert "openai-completions" not in serialized
    assert "PRIVATE" not in serialized


def test_provider_runtime_preflight_preserves_nested_chat_wire_api_shapes():
    old_shape = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-openai-nested-wire-api",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "openai": {
                    "wire_api": "chat",
                    "base_url": "PRIVATE_BASE_URL_DO_NOT_EXPORT",
                    "models": {"default": "PRIVATE_MODEL_DO_NOT_EXPORT"},
                },
                "supported_wire_apis": ["chat", "responses"],
                "exercised_wire_apis": ["chat"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "generated_model_api": "openai-completions",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_openai_nested_wire_api_inline.json",
    )
    new_shape = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-provider-config-openai-nested-wire-api",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "provider_config": {
                    "openai": {
                        "wire_api": "openai-chat-completions",
                        "base_url": "PRIVATE_BASE_URL_DO_NOT_EXPORT",
                        "models": {"default": "PRIVATE_MODEL_DO_NOT_EXPORT"},
                    }
                },
                "supported_wire_apis": ["chat", "responses"],
                "exercised_wire_apis": ["chat"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "generated_model_api": "openai-completions",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR
        / "provider_runtime_preflight_provider_config_openai_nested_wire_api_inline.json",
    )
    serialized = json.dumps({"old_shape": old_shape, "new_shape": new_shape}, sort_keys=True)

    for output in (old_shape, new_shape):
        assert output["route_status"] == "passed"
        assert output["failure_mode"] == "none"
        assert output["wire_api"]["configured"] is True
        assert output["wire_api"]["selected"] == "chat"
        assert output["wire_api"]["runner_selected"] == "chat"
        assert output["wire_api"]["runner_matches_config"] is True
        assert output["wire_api"]["raw_value_exported"] is False
        assert output["wire_api"]["runner_raw_value_exported"] is False

    assert "PRIVATE_BASE_URL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_MODEL_DO_NOT_EXPORT" not in serialized
    assert "openai-chat-completions" not in serialized
    assert "openai-completions" not in serialized


def test_provider_runtime_preflight_reports_missing_or_incompatible_nested_chat_wire_api():
    missing = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-nested-wire-api-missing",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "wire_api_required": True,
                "openai": {
                    "base_url": "PRIVATE_BASE_URL_DO_NOT_EXPORT",
                    "models": {"default": "PRIVATE_MODEL_DO_NOT_EXPORT"},
                },
                "supported_wire_apis": ["chat", "responses"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_nested_wire_api_missing_inline.json",
    )
    incompatible = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-nested-wire-api-runner-mismatch",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
                "openai": {
                    "wire_api": "chat",
                    "base_url": "PRIVATE_BASE_URL_DO_NOT_EXPORT",
                    "models": {"default": "PRIVATE_MODEL_DO_NOT_EXPORT"},
                },
                "supported_wire_apis": ["chat", "responses"],
                "exercised_wire_apis": ["chat"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "generated_model_api": "openai-responses",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR
        / "provider_runtime_preflight_nested_wire_api_runner_mismatch_inline.json",
    )
    serialized = json.dumps({"missing": missing, "incompatible": incompatible}, sort_keys=True)

    assert missing["route_status"] == "blocked"
    assert missing["failure_mode"] == "provider_wire_api_missing"
    assert missing["runtime"]["runner_invoked"] is False
    assert missing["preflight"]["diagnostics"] == ["provider wire API is required but was not configured"]
    assert missing["recovery_hints"][0]["code"] == "provider_wire_api_missing"
    assert missing["recovery_hints"][0]["wire_api_configured"] is False
    assert missing["recovery_hints"][0]["wire_api_selected"] == "unknown"

    assert incompatible["route_status"] == "blocked"
    assert incompatible["failure_mode"] == "provider_wire_api_runner_mismatch"
    assert incompatible["runtime"]["runner_invoked"] is False
    assert incompatible["wire_api"]["selected"] == "chat"
    assert incompatible["wire_api"]["runner_selected"] == "responses"
    assert incompatible["preflight"]["diagnostics"] == [
        "provider wire API was configured but resolved to a different runner route"
    ]
    assert incompatible["recovery_hints"][0]["code"] == "provider_wire_api_runner_mismatch"
    assert incompatible["recovery_hints"][0]["runner_wire_api_selected"] == "responses"

    assert "PRIVATE_BASE_URL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_MODEL_DO_NOT_EXPORT" not in serialized
    assert "openai-responses" not in serialized


def test_provider_runtime_preflight_blocks_unreplayed_old_runner_host_compat_bridge():
    blocked = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-runner-compat-bridge-missing-inline",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "runner_compat": {
                    "required": True,
                    "direction": "Config 2",
                    "runner_python": "PRIVATE_OLD_RUNNER_PYTHON_DO_NOT_EXPORT",
                    "runner_version": "PRIVATE_OLD_RUNNER_VERSION_DO_NOT_EXPORT",
                    "host_runner_colocated": True,
                    "spawn_site_count": 5,
                },
            },
            "runner_env": {
                "parent_env_keys": ["PATH", "PYTHONPATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_runner_compat_missing_inline.json",
    )
    ready = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-runner-compat-bridge-ready-inline",
            "provider": {
                "name": "omnigent-openai-compatible",
                "harness": "omnigent",
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "runner_compat": {
                    "required": True,
                    "direction": "old-runner-host-to-new-server",
                    "runner_python_configured": True,
                    "runner_version_configured": True,
                    "host_runner_colocated": True,
                    "worktree_pythonpath_dropped": True,
                    "neutral_cwd": True,
                    "local_route_evidence_replayed": True,
                    "spawn_site_count": 5,
                },
            },
            "runner_env": {
                "parent_env_keys": ["PATH", "PYTHONPATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_runner_compat_ready_inline.json",
    )
    serialized = json.dumps({"blocked": blocked, "ready": ready}, sort_keys=True)

    assert blocked["route_status"] == "blocked"
    assert blocked["failure_mode"] == "provider_runner_compat_env_not_neutralized"
    assert blocked["runtime"]["runner_invoked"] is False
    assert blocked["runner_compat"]["direction"] == "old_runner_host_to_current_server"
    assert blocked["runner_compat"]["runner_python_configured"] is True
    assert blocked["runner_compat"]["runner_version_configured"] is True
    assert blocked["runner_compat"]["host_runner_colocated"] is True
    assert blocked["runner_compat"]["worktree_pythonpath_dropped"] is False
    assert blocked["runner_compat"]["neutral_cwd"] is False
    assert blocked["runner_compat"]["local_route_evidence_replayed"] is False
    assert blocked["runner_compat"]["spawn_site_count"] == 5
    assert blocked["preflight"]["diagnostics"] == [
        "compat runner environment must drop worktree PYTHONPATH and use a neutral cwd",
        "compat runner resolution proof must be replayed before provider launch",
    ]
    assert blocked["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_runner_compat_env_not_neutralized",
            "scope": "provider_runner_compat",
            "severity": "blocker",
            "action": "configure the old runner/host compatibility bridge and replay local resolution proof before provider launch",
            "direction": "old_runner_host_to_current_server",
            "runner_python_configured": True,
            "runner_version_configured": True,
            "host_runner_colocated": True,
            "worktree_pythonpath_dropped": False,
            "neutral_cwd": False,
            "local_route_evidence_replayed": False,
            "spawn_site_count": 5,
            "pinned_component_count": 3,
            "neutralization_count": 0,
            "version_value_recorded": False,
            "python_path_recorded": False,
            "cwd_recorded": False,
            "env_values_recorded": False,
            "raw_config_exported": False,
        }
    ]
    assert blocked["supervisor_replay"]["ready_for_provider_launch"] is False
    assert blocked["supervisor_replay"]["recovery_hint_codes"] == [
        "provider_runner_compat_env_not_neutralized"
    ]

    assert ready["route_status"] == "passed"
    assert ready["failure_mode"] == "none"
    assert ready["runner_compat"]["ok"] is True
    assert ready["runner_compat"]["direction"] == "old_runner_host_to_current_server"
    assert ready["runner_compat"]["neutralization_count"] == 2
    assert ready["runtime"]["runner_invoked"] is True

    assert "PRIVATE_OLD_RUNNER_PYTHON_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OLD_RUNNER_VERSION_DO_NOT_EXPORT" not in serialized
    assert "Config 2" not in serialized


def test_provider_runtime_preflight_blocks_malformed_kubernetes_sandbox_without_cluster_access():
    base_input = {
        "provider": {
            "name": "omnigent-kubernetes-provider",
            "harness": "omnigent",
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
    missing = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            **base_input,
            "task_id": "fixture-provider-runtime-preflight-kubernetes-missing-inline",
            "sandbox": {
                "provider": "kubernetes",
                "kubernetes": {
                    "namespace": "omnigent-sandboxes",
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_kubernetes_missing_inline.json",
    )
    malformed = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            **base_input,
            "task_id": "fixture-provider-runtime-preflight-kubernetes-malformed-inline",
            "sandbox": {
                "provider": "kubernetes",
                "kubernetes": {
                    "namespace": "Omnigent Sandboxes",
                    "image": "registry.example/runner:latest; PRIVATE_SHELL_DO_NOT_EXPORT",
                    "service_account": "runner_sa",
                    "secret_name": "runner-creds",
                    "node_selector": {
                        "omnigent.ai/runner ready": "true",
                    },
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_kubernetes_malformed_inline.json",
    )
    credential = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            **base_input,
            "task_id": "fixture-provider-runtime-preflight-kubernetes-credential-inline",
            "sandbox": {
                "provider": "kubernetes",
                "kubernetes": {
                    "namespace": "omnigent-sandboxes",
                    "image": "registry.example/omnigent-runner:latest",
                    "service_account": "omnigent-runner",
                    "env": {
                        "PRIVATE_API_TOKEN_DO_NOT_EXPORT": "PRIVATE_TOKEN_VALUE_DO_NOT_EXPORT",
                    },
                    "requires_launch_token": True,
                    "server_minted_launch_token": True,
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_kubernetes_credential_inline.json",
    )
    token = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            **base_input,
            "task_id": "fixture-provider-runtime-preflight-kubernetes-token-inline",
            "sandbox": {
                "provider": "kubernetes",
                "kubernetes": {
                    "namespace": "omnigent-sandboxes",
                    "image": "registry.example/omnigent-runner:latest",
                    "service_account": "omnigent-runner",
                    "requires_launch_token": True,
                    "server_minted_launch_token": False,
                    "launch_token_value_configured": True,
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_kubernetes_token_inline.json",
    )
    ready = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            **base_input,
            "task_id": "fixture-provider-runtime-preflight-kubernetes-ready-inline",
            "sandbox": {
                "provider": "kubernetes",
                "kubernetes": {
                    "namespace": "omnigent-sandboxes",
                    "image": "registry.example/omnigent-runner:latest",
                    "service_account": "omnigent-runner",
                    "secret_name": "omnigent-creds",
                    "node_selector": {
                        "omnigent.ai/runner-ready": "true",
                        "kubernetes.io/arch": "amd64",
                    },
                    "requires_launch_token": True,
                    "server_minted_launch_token": True,
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_kubernetes_ready_inline.json",
    )
    serialized = json.dumps(
        {
            "missing": missing,
            "malformed": malformed,
            "credential": credential,
            "token": token,
            "ready": ready,
        },
        sort_keys=True,
    )

    assert missing["route_status"] == "blocked"
    assert missing["failure_mode"] == "provider_kubernetes_sandbox_config_missing"
    assert missing["kubernetes_sandbox"]["namespace_configured"] is True
    assert missing["kubernetes_sandbox"]["image_configured"] is False
    assert missing["kubernetes_sandbox"]["service_account_configured"] is False
    assert missing["kubernetes_sandbox"]["cluster_access_attempted"] is False
    assert missing["recovery_hints"][0]["scope"] == "provider_kubernetes_sandbox"
    assert missing["runtime"]["runner_invoked"] is False

    assert malformed["route_status"] == "blocked"
    assert malformed["failure_mode"] == "provider_kubernetes_sandbox_config_malformed"
    assert malformed["kubernetes_sandbox"]["malformed_name_count"] == 2
    assert malformed["kubernetes_sandbox"]["malformed_selector_count"] == 1
    assert malformed["kubernetes_sandbox"]["raw_image_exported"] is False

    assert credential["route_status"] == "blocked"
    assert credential["failure_mode"] == "provider_kubernetes_sandbox_credential_env_inline"
    assert credential["kubernetes_sandbox"]["credential_env_key_count"] == 1
    assert credential["recovery_hints"][0]["credential_values_exported"] is False

    assert token["route_status"] == "blocked"
    assert token["failure_mode"] == "provider_kubernetes_sandbox_token_value_configured"
    assert token["kubernetes_sandbox"]["requires_launch_token"] is True
    assert token["kubernetes_sandbox"]["server_minted_launch_token"] is False
    assert token["kubernetes_sandbox"]["launch_token_value_configured"] is True

    assert ready["route_status"] == "passed"
    assert ready["failure_mode"] == "none"
    assert ready["kubernetes_sandbox"]["provider_runtime_launch_allowed"] is True
    assert ready["kubernetes_sandbox"]["node_selector_count"] == 2
    assert ready["runtime"]["runner_invoked"] is True

    assert "PRIVATE_SHELL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_API_TOKEN_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_TOKEN_VALUE_DO_NOT_EXPORT" not in serialized
    assert "registry.example" not in serialized
    assert "omnigent-sandboxes" not in serialized
    assert "omnigent-runner" not in serialized
    assert "omnigent-creds" not in serialized
    assert "runner-ready" not in serialized


def test_provider_runtime_preflight_blocks_malformed_windows_runner_before_launch():
    blocked = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-windows-runner-malformed-inline",
            "provider": {
                "name": "omnigent-windows-provider",
                "harness": "omnigent",
            },
            "runtime": {
                "platform": "windows",
                "launch_transport": "subprocess",
                "windows_runner": {
                    "required": True,
                    "shell": "cmd.exe",
                    "command": "python PRIVATE_SCRIPT_DO_NOT_EXPORT --workspace C:\\PRIVATE WORKSPACE\\agent",
                    "workspace": "C:\\PRIVATE WORKSPACE\\agent",
                    "workspace_resolved": True,
                    "workspace_inside_repo": False,
                    "path_arg_count": 2,
                    "quoted_path_arg_count": 0,
                },
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_windows_runner_malformed_inline.json",
    )
    ready = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-windows-runner-ready-inline",
            "provider": {
                "name": "omnigent-windows-provider",
                "harness": "omnigent",
            },
            "runtime": {
                "platform": "windows",
                "launch_transport": "subprocess",
                "windows_runner": {
                    "required": True,
                    "shell": "pwsh.exe",
                    "command": [
                        "python",
                        "C:\\PRIVATE WORKSPACE\\agent\\runner.py",
                        "--workspace",
                        "C:\\PRIVATE WORKSPACE\\agent",
                    ],
                    "workspace": "C:\\PRIVATE WORKSPACE\\agent",
                    "workspace_resolved": True,
                    "workspace_inside_repo": True,
                    "path_arg_count": 2,
                    "quoted_path_arg_count": 2,
                    "path_args_quoted": True,
                    "local_replay_evidence": True,
                },
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_windows_runner_ready_inline.json",
    )
    serialized = json.dumps({"blocked": blocked, "ready": ready}, sort_keys=True)

    assert blocked["route_status"] == "blocked"
    assert blocked["failure_mode"] == "provider_windows_runner_shell_unsupported"
    assert blocked["runtime"]["runner_invoked"] is False
    assert blocked["windows_runner"]["shell_family"] == "cmd"
    assert blocked["windows_runner"]["powershell_family"] is False
    assert blocked["windows_runner"]["command_shape"] == "string"
    assert blocked["windows_runner"]["command_shape_valid"] is False
    assert blocked["windows_runner"]["path_arg_count"] == 2
    assert blocked["windows_runner"]["quoted_path_arg_count"] == 0
    assert blocked["windows_runner"]["workspace_inside_repo"] is False
    assert blocked["windows_runner"]["raw_command_exported"] is False
    assert blocked["windows_runner"]["raw_paths_exported"] is False
    assert blocked["windows_runner"]["raw_workspace_exported"] is False
    assert blocked["windows_runner"]["shell_body_exported"] is False
    assert blocked["preflight"]["diagnostics"] == [
        "Windows provider runner must declare PowerShell or pwsh shell metadata before launch",
        "Windows provider runner command must be represented as an argv list, not a shell body",
        "Windows provider runner path arguments must be quoted or passed as argv elements",
        "Windows provider runner workspace must resolve inside the current repository",
        "Windows provider runner local replay proof must be recorded before launch",
    ]
    assert blocked["recovery_hints"][0]["code"] == "provider_windows_runner_shell_unsupported"
    assert blocked["recovery_hints"][0]["scope"] == "provider_windows_runner"
    assert blocked["supervisor_replay"]["ready_for_provider_launch"] is False

    assert ready["route_status"] == "passed"
    assert ready["failure_mode"] == "none"
    assert ready["windows_runner"]["shell_family"] == "pwsh"
    assert ready["windows_runner"]["command_arg_count"] == 4
    assert ready["windows_runner"]["workspace_inside_repo"] is True
    assert ready["windows_runner"]["local_replay_evidence"] is True
    assert ready["runtime"]["runner_invoked"] is True

    assert "PRIVATE_SCRIPT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE WORKSPACE" not in serialized
    assert "C:\\\\" not in serialized
    assert "cmd.exe" not in serialized
    assert "pwsh.exe" not in serialized


def test_provider_runtime_preflight_windows_degraded_mode_is_local_replay_only():
    degraded = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-windows-degraded-inline",
            "provider": {
                "name": "omnigent-windows-provider",
                "harness": "omnigent",
            },
            "runtime": {
                "platform": "windows",
                "launch_transport": "subprocess",
                "windows_runner": {
                    "required": True,
                    "allow_degraded_mode": True,
                    "shell": "cmd.exe",
                    "command": [
                        "python",
                        "C:\\PRIVATE WORKSPACE\\agent\\runner.py",
                        "--workspace",
                        "C:\\PRIVATE WORKSPACE\\agent",
                    ],
                    "workspace": "C:\\PRIVATE WORKSPACE\\agent",
                    "workspace_resolved": True,
                    "workspace_inside_repo": True,
                    "path_arg_count": 2,
                    "quoted_path_arg_count": 2,
                    "path_args_quoted": True,
                    "local_replay_evidence": True,
                    "required_dependencies": ["PRIVATE_SYSTEMROOT_DO_NOT_EXPORT", "PRIVATE_USERPROFILE_DO_NOT_EXPORT"],
                    "missing_dependencies": ["PRIVATE_USERPROFILE_DO_NOT_EXPORT"],
                    "required_capabilities": ["PRIVATE_CONPTY_DO_NOT_EXPORT", "PRIVATE_EGRESS_PROXY_DO_NOT_EXPORT"],
                    "unsupported_capabilities": ["PRIVATE_EGRESS_PROXY_DO_NOT_EXPORT"],
                },
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_windows_degraded_inline.json",
    )
    blocked = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-windows-capability-blocked-inline",
            "provider": {
                "name": "omnigent-windows-provider",
                "harness": "omnigent",
            },
            "runtime": {
                "platform": "windows",
                "launch_transport": "subprocess",
                "windows_runner": {
                    "required": True,
                    "shell": "pwsh.exe",
                    "command": ["python", "runner.py"],
                    "workspace": "C:\\PRIVATE WORKSPACE\\agent",
                    "workspace_resolved": True,
                    "workspace_inside_repo": True,
                    "local_replay_evidence": True,
                    "required_capabilities": ["PRIVATE_EGRESS_PROXY_DO_NOT_EXPORT"],
                    "unsupported_capabilities": ["PRIVATE_EGRESS_PROXY_DO_NOT_EXPORT"],
                },
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_windows_capability_blocked_inline.json",
    )
    serialized = json.dumps({"degraded": degraded, "blocked": blocked}, sort_keys=True)

    assert degraded["route_status"] == "degraded"
    assert degraded["failure_mode"] == "none"
    assert degraded["runtime"]["runner_invoked"] is False
    assert degraded["runtime"]["native_file_shell_tools_disabled"] is True
    assert degraded["windows_runner"]["degraded"] is True
    assert degraded["windows_runner"]["allow_degraded_mode"] is True
    assert degraded["windows_runner"]["local_replay_only"] is True
    assert degraded["windows_runner"]["provider_runtime_launch_allowed"] is False
    assert degraded["windows_runner"]["missing_dependency_count"] == 1
    assert degraded["windows_runner"]["unsupported_capability_count"] == 1
    assert degraded["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_windows_runner_degraded_mode",
            "scope": "provider_windows_runner",
            "severity": "notice",
            "action": "keep Windows-native provider startup in local replay mode until missing shell, dependency, or capability evidence is repaired",
            "platform": "windows",
            "shell_family": "cmd",
            "allow_degraded_mode": True,
            "local_replay_only": True,
            "provider_runtime_launch_allowed": False,
            "required_dependency_count": 2,
            "missing_dependency_count": 1,
            "required_capability_count": 2,
            "unsupported_capability_count": 1,
            "raw_command_exported": False,
            "raw_paths_exported": False,
            "raw_workspace_exported": False,
            "shell_body_exported": False,
            "raw_dependency_names_exported": False,
            "raw_capability_names_exported": False,
        }
    ]
    assert degraded["operator_recovery_plan"]["decision"] == "degraded_local_replay_only"
    assert degraded["supervisor_replay"]["ready_for_provider_launch"] is False
    assert degraded["supervisor_replay"]["recovery_hint_codes"] == ["provider_windows_runner_degraded_mode"]

    assert blocked["route_status"] == "blocked"
    assert blocked["failure_mode"] == "provider_windows_runner_capability_unavailable"
    assert blocked["windows_runner"]["degraded"] is False
    assert blocked["recovery_hints"][0]["code"] == "provider_windows_runner_capability_unavailable"
    assert blocked["recovery_hints"][0]["missing_dependency_count"] == 0
    assert blocked["recovery_hints"][0]["unsupported_capability_count"] == 1

    assert "PRIVATE_SYSTEMROOT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_USERPROFILE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CONPTY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_EGRESS_PROXY_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE WORKSPACE" not in serialized
    assert "cmd.exe" not in serialized


def test_provider_runtime_preflight_clears_stale_approval_verdict_on_repark():
    output = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-approval-repark-inline",
            "provider": {
                "name": "omnigent-inbox-provider",
                "harness": "omnigent",
                "approval_repark": {
                    "required": True,
                    "elicitation_id": "PRIVATE_ELICITATION_ID_DO_NOT_EXPORT",
                    "local_verdict": "approved",
                    "snapshot_data_updated_at": "2026-06-22T16:00:00Z",
                    "pending_elicitation_ids": ["PRIVATE_ELICITATION_ID_DO_NOT_EXPORT"],
                },
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_approval_repark_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_approval_repark_pending"
    assert output["approval_repark"]["stale_verdict_detected"] is True
    assert output["approval_repark"]["local_verdict_cleared"] is True
    assert output["approval_repark"]["same_elicitation_pending"] is True
    assert output["approval_repark"]["raw_elicitation_id_exported"] is False
    assert output["approval_repark"]["raw_snapshot_exported"] is False
    assert output["approval_repark"]["raw_verdict_exported"] is False
    assert output["runtime"]["runner_invoked"] is False
    assert output["preflight"]["diagnostics"] == [
        "stale approval verdict cleared because fresh provider snapshot still shows elicitation pending"
    ]
    assert output["recovery_hints"][0]["code"] == "provider_approval_repark_pending"
    assert output["supervisor_replay"]["ready_for_provider_launch"] is False
    assert "PRIVATE_ELICITATION_ID_DO_NOT_EXPORT" not in serialized
    assert "approved" not in serialized


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


def test_mock_llm_approval_expected_without_ask_path_fails_closed():
    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        {
            "task_id": "fixture-mock-llm-approval-missing-inline",
            "provider": {"enabled": False},
            "native_tool_policy": {
                "approval_expected": True,
                "policy_hook": {
                    "governed": True,
                    "session_id": "PRIVATE_APPROVAL_MISSING_SESSION_DO_NOT_EXPORT",
                    "server_url_configured": True,
                    "event_phase": "TOOL_CALL",
                    "failure_mode": "none",
                },
                "tool_call": {
                    "name": "Bash",
                    "transport": "native",
                    "arguments": {"command": "PRIVATE_APPROVAL_MISSING_COMMAND_DO_NOT_EXPORT"},
                },
            },
            "mock_llm": {
                "enabled": True,
                "responses": [
                    {
                        "content": "mock route reached governed tool boundary",
                        "tool_calls": [{"name": "Bash"}],
                    }
                ],
            },
            "workflow": {"steps": [{"id": "approval-turn", "expect_contains": "governed tool boundary"}]},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_approval_missing_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "native_policy_route_failed"
    assert output["native_tool_policy"]["failure_mode"] == "approval_path_missing"
    assert output["native_tool_policy"]["approval_path"] == {
        "expected": True,
        "declared": False,
        "route_status": "missing",
        "passive": False,
        "tool_executed": False,
        "arguments_exported": False,
    }
    assert output["native_tool_policy"]["tool_executed"] is False
    assert "PRIVATE_APPROVAL_MISSING_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_APPROVAL_MISSING_COMMAND_DO_NOT_EXPORT" not in serialized


def test_mock_llm_explicit_approval_denial_is_declared_without_execution():
    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        {
            "task_id": "fixture-mock-llm-approval-denied-inline",
            "provider": {"enabled": False},
            "native_tool_policy": {
                "approval_expected": True,
                "policy_hook": {
                    "governed": True,
                    "session_id": "PRIVATE_APPROVAL_DENIED_SESSION_DO_NOT_EXPORT",
                    "server_url_configured": True,
                    "event_phase": "TOOL_CALL",
                    "failure_mode": "none",
                    "approval_resolution": "denied",
                    "verdict": {
                        "review_required": True,
                        "reason": "operator_ask",
                    },
                },
                "tool_call": {
                    "name": "Bash",
                    "transport": "native",
                    "arguments": {"command": "PRIVATE_APPROVAL_DENIED_COMMAND_DO_NOT_EXPORT"},
                },
            },
            "mock_llm": {
                "enabled": True,
                "responses": [
                    {
                        "content": "mock route reached governed denial boundary",
                        "tool_calls": [{"name": "Bash"}],
                    }
                ],
            },
            "workflow": {"steps": [{"id": "approval-turn", "expect_contains": "denial boundary"}]},
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_approval_denied_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["native_tool_policy"]["route_status"] == "denied"
    assert output["native_tool_policy"]["failure_mode"] == "policy_approval_denied"
    assert output["native_tool_policy"]["permission_decision"] == "deny"
    assert output["native_tool_policy"]["approval_path"] == {
        "expected": True,
        "declared": True,
        "route_status": "resolved",
        "passive": False,
        "tool_executed": False,
        "arguments_exported": False,
    }
    assert output["native_tool_policy"]["passive_or_denied"] is True
    assert output["native_tool_policy"]["tool_executed"] is False
    assert "PRIVATE_APPROVAL_DENIED_SESSION_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_APPROVAL_DENIED_COMMAND_DO_NOT_EXPORT" not in serialized


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


def test_known_failure_metadata_preflight_blocks_absent_metadata_without_exporting_ids():
    output = evaluate_harness_behavior(
        "known_failure_metadata_preflight",
        {
            "task_id": "fixture-known-failure-metadata-absent-inline",
            "known_failure_metadata": {
                "present": False,
                "expected_failure_ids": ["PRIVATE_KNOWN_FAILURE_ID_DO_NOT_EXPORT"],
                "current_failure_ids": [],
                "change_evidence": {
                    "known_failure_removal_explained": False,
                    "local_test_evidence_present": False,
                    "gating_refresh_recorded": False,
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "known_failure_metadata_absent_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "known_failure_metadata_stale"
    assert output["preflight"]["metadata_present"] is False
    assert output["preflight"]["known_failure_metadata_absent"] is True
    assert output["preflight"]["test_gating_should_refresh"] is True
    assert output["supervisor_handoff"]["recovery_hint_codes"] == [
        "refresh_expected_failure_assumptions",
        "restore_or_confirm_known_failure_metadata",
    ]
    assert output["privacy"]["raw_test_names_exported"] is False
    assert "PRIVATE_KNOWN_FAILURE_ID_DO_NOT_EXPORT" not in serialized


def test_known_failure_metadata_preflight_accepts_current_metadata_without_refresh():
    output = evaluate_harness_behavior(
        "known_failure_metadata_preflight",
        {
            "task_id": "fixture-known-failure-metadata-current-inline",
            "known_failure_metadata": {
                "present": True,
                "expected_failure_ids": ["approval-output-phase-ask"],
                "current_failure_ids": ["approval-output-phase-ask"],
                "change_evidence": {
                    "known_failure_removal_explained": True,
                    "local_test_evidence_present": True,
                    "gating_refresh_recorded": True,
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "known_failure_metadata_current_inline.json",
    )

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["preflight"]["status"] == "current"
    assert output["preflight"]["test_gating_should_refresh"] is False
    assert output["preflight"]["diagnostics"] == []
    assert output["supervisor_handoff"]["decision"] == "test_gating_current"


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
    assert output["activation_review"] == {
        "controller_surface": "agent_harness_activation_review",
        "status": "ready",
        "decision": "mapped_meta_harness_claims_ready_for_local_eval",
        "activation_scope": "local_eval_only",
        "activation_gate_decision": "ready_for_local_eval_activation",
        "activation_blockers": [],
        "bounded_activation_lane_count": 2,
        "claim_count": 0,
        "mapped_claim_count": 0,
        "unmapped_claim_count": 0,
        "claim_mapping_status": "empty",
        "project_intake_probe_status": "incomplete",
        "specific_detail_count": 1,
        "weak_or_generic_evidence_requires_review": False,
        "safety_review_note_count": 1,
        "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
        "local_eval_activation_allowed": True,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_urls_exported": False,
        "raw_evidence_bodies_exported": False,
        "raw_claim_bodies_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert output["general_agent_route_review_queue"] == {
        "controller_surface": "general_agent_route_review_queue",
        "status": "empty",
        "decision": "collect_general_agent_claims_before_local_eval",
        "activation_scope": "local_eval_only",
        "activation_gate_decision": "ready_for_local_eval_activation",
        "claim_count": 0,
        "mapped_claim_count": 0,
        "unmapped_claim_count": 0,
        "ready_claim_count": 0,
        "blocked_claim_count": 0,
        "project_intake_probe_status": "incomplete",
        "allowed_local_lanes": ["documentation", "test", "code_patch"],
        "selected_local_lanes": [],
        "required_validation": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
        "local_validation_required": True,
        "local_eval_activation_allowed": False,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_urls_exported": False,
        "raw_claim_bodies_exported": False,
        "raw_upstream_body_exported": False,
        "rows": [],
    }
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
        "raw_install_commands_exported": False,
        "upstream_project_imported": False,
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

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "unmapped_agent_claims"
    assert output["activation_gate"]["decision"] == "map_agent_claims_before_activation"
    assert output["activation_gate"]["local_eval_activation_allowed"] is False
    assert output["activation_gate"]["external_harness_execution_allowed"] is False
    assert output["activation_review"]["controller_surface"] == "agent_harness_activation_review"
    assert output["activation_review"]["status"] == "blocked"
    assert output["activation_review"]["decision"] == "resolve_activation_review_blockers_before_local_eval"
    assert output["activation_review"]["activation_gate_decision"] == "map_agent_claims_before_activation"
    assert output["activation_review"]["activation_blockers"] == ["unmapped_agent_claims"]
    assert output["activation_review"]["bounded_activation_lane_count"] == 3
    assert output["activation_review"]["claim_count"] == 7
    assert output["activation_review"]["mapped_claim_count"] == 6
    assert output["activation_review"]["unmapped_claim_count"] == 1
    assert output["activation_review"]["claim_mapping_status"] == "partial"
    assert output["activation_review"]["project_intake_probe_status"] == "ready"
    assert output["activation_review"]["weak_or_generic_evidence_requires_review"] is False
    assert output["activation_review"]["local_eval_activation_allowed"] is False
    assert output["activation_review"]["runtime_action"] == "none"
    assert output["activation_review"]["external_agent_activation_allowed"] is False
    assert output["activation_review"]["external_harness_execution_allowed"] is False
    assert output["activation_review"]["provider_launch_allowed"] is False
    assert output["activation_review"]["remote_execution_allowed"] is False
    assert output["activation_review"]["raw_source_urls_exported"] is False
    assert output["activation_review"]["raw_claim_bodies_exported"] is False
    queue = output["general_agent_route_review_queue"]
    assert queue["controller_surface"] == "general_agent_route_review_queue"
    assert queue["status"] == "blocked"
    assert queue["decision"] == "review_general_agent_claim_lanes_before_local_eval"
    assert queue["activation_gate_decision"] == "map_agent_claims_before_activation"
    assert queue["claim_count"] == 7
    assert queue["mapped_claim_count"] == 6
    assert queue["unmapped_claim_count"] == 1
    assert queue["ready_claim_count"] == 0
    assert queue["blocked_claim_count"] == 7
    assert queue["project_intake_probe_status"] == "ready"
    assert queue["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert queue["selected_local_lanes"] == ["documentation", "test"]
    assert queue["required_validation"] == ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"]
    assert queue["local_eval_activation_allowed"] is False
    assert queue["runtime_action"] == "none"
    assert queue["external_agent_activation_allowed"] is False
    assert queue["external_harness_execution_allowed"] is False
    assert queue["provider_launch_allowed"] is False
    assert queue["remote_execution_allowed"] is False
    assert queue["raw_source_urls_exported"] is False
    assert queue["raw_claim_bodies_exported"] is False
    assert queue["raw_upstream_body_exported"] is False
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
    assert output["claim_remediation_plan"]["controller_surface"] == "agent_harness_claim_remediation_plan"
    assert output["claim_remediation_plan"]["status"] == "blocked"
    assert output["claim_remediation_plan"]["decision"] == "map_unmapped_claims_before_activation"
    assert output["claim_remediation_plan"]["unmapped_claim_ids"] == ["local_data_grounding"]
    assert output["claim_remediation_plan"]["recommended_first_lanes"] == ["documentation", "test"]
    assert output["claim_remediation_plan"]["local_eval_activation_allowed"] is False
    assert output["claim_remediation_plan"]["runtime_action"] == "none"
    assert output["claim_remediation_plan"]["external_agent_activation_allowed"] is False
    assert output["claim_remediation_plan"]["external_harness_execution_allowed"] is False
    assert output["claim_remediation_plan"]["provider_launch_allowed"] is False
    assert output["claim_remediation_plan"]["remote_execution_allowed"] is False
    assert output["claim_remediation_plan"]["raw_claim_bodies_exported"] is False
    assert output["claim_remediation_plan"]["rows"] == [
        {
            "claim_id": "local_data_grounding",
            "status": "needs_local_mapping",
            "recommended_lanes": ["documentation", "test"],
            "required_local_validation": [
                "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
            ],
            "activation_blocker": "unmapped_agent_claims",
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_claim_body_exported": False,
        }
    ]
    assert output["project_intake_probe"]["controller_surface"] == "agent_harness_project_intake_probe"
    assert output["project_intake_probe"]["status"] == "ready"
    assert output["project_intake_probe"]["decision"] == "project_shape_recorded_before_local_eval"
    assert output["project_intake_probe"]["record_count"] == 2
    assert output["project_intake_probe"]["complete_record_count"] == 2
    assert output["project_intake_probe"]["missing_fields"] == []
    assert output["project_intake_probe"]["required_fields"] == [
        "install_shape",
        "entrypoints",
        "dependency_boundaries",
        "task_loop_assumptions",
        "observable_behaviors",
    ]
    assert output["project_intake_probe"]["runtime_action"] == "none"
    assert output["project_intake_probe"]["install_allowed"] is False
    assert output["project_intake_probe"]["external_agent_activation_allowed"] is False
    assert output["project_intake_probe"]["external_harness_execution_allowed"] is False
    assert output["project_intake_probe"]["provider_launch_allowed"] is False
    assert output["project_intake_probe"]["remote_execution_allowed"] is False
    assert output["project_intake_probe"]["raw_install_commands_exported"] is False
    assert all(lane["activation_ready"] is False for lane in output["activation_lanes"])
    assert all(lane["activation_blockers"] == ["unmapped_agent_claims"] for lane in output["activation_lanes"])
    assert all(lane["runtime_action"] == "none" for lane in output["activation_lanes"])

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
    queue_rows_by_claim = {
        (row["item_id"], row["claim_id"]): row
        for row in queue["rows"]
    }
    assert queue_rows_by_claim[
        ("omnigent-general-agent-framework", "multi_agent_orchestration")
    ]["selected_local_lane"] == "test"
    assert queue_rows_by_claim[
        ("omnigent-general-agent-framework", "multi_agent_orchestration")
    ]["required_validation"] == ["pytest tests/test_harness_eval.py -q -k agent_workflow_route"]
    assert queue_rows_by_claim[
        ("xuefeng-agent-domain-advisor", "local_data_grounding")
    ]["selected_local_lane"] == "documentation"
    assert queue_rows_by_claim[
        ("xuefeng-agent-domain-advisor", "local_data_grounding")
    ]["queued_local_lanes"] == ["documentation", "test"]
    assert queue_rows_by_claim[
        ("xuefeng-agent-domain-advisor", "local_data_grounding")
    ]["activation_blockers"] == ["unmapped_agent_claims"]
    assert all(row["runtime_action"] == "none" for row in queue["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in queue["rows"])
    probe_rows = {
        row["item_id"]: row
        for row in output["project_intake_probe"]["rows"]
    }
    assert probe_rows["omnigent-general-agent-framework"]["install_shape"] == [
        "python_package",
        "script_installer",
        "repo_tool_install",
    ]
    assert probe_rows["omnigent-general-agent-framework"]["entrypoints"] == ["cli", "server", "yaml_agent"]
    assert probe_rows["omnigent-general-agent-framework"]["dependency_boundaries"] == [
        "provider_api_key",
        "sandbox_runtime",
        "cloud_sandbox",
    ]
    assert probe_rows["omnigent-general-agent-framework"]["task_loop_assumptions"] == [
        "orchestrated_multi_agent",
        "session_supervision",
        "policy_gate",
    ]
    assert probe_rows["omnigent-general-agent-framework"]["observable_behaviors"] == [
        "multi_agent_supervision",
        "policy_control",
        "session_sync",
        "sandboxing",
    ]
    assert probe_rows["xuefeng-agent-domain-advisor"]["install_shape"] == ["web_app"]
    assert probe_rows["xuefeng-agent-domain-advisor"]["entrypoints"] == ["browser_app", "api"]
    assert probe_rows["xuefeng-agent-domain-advisor"]["dependency_boundaries"] == [
        "database",
        "provider_api_key",
        "browser_session",
    ]
    assert all(row["probe_complete"] is True for row in probe_rows.values())
    assert all(row["runtime_action"] == "none" for row in probe_rows.values())
    assert all(row["source_url_hash"].startswith("sha256:") for row in probe_rows.values())
    assert "https://github.com/omnigent-ai/omnigent" not in serialized
    assert "https://github.com/ziqihe10-droid/xuefeng-agent" not in serialized


def test_skill_route_discovery_current_pass_skill_shapes_stay_bounded_without_url_expansion():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_current_pass_skill_shapes.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["registry"]["candidate_count"] == 3
    assert output["registry"]["ignored_evidence_item_count"] == 0
    assert output["lane_map"]["lanes_bounded"] is True
    assert set(output["lane_map"]["proposal_kinds"]) == {"documentation", "config", "test", "code_patch"}
    assert output["route_hint_lane_policy"]["allowed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert output["route_hint_lane_policy"]["runtime_action_allowed"] is False
    assert output["activation_gate"]["external_skill_activation_allowed"] is False

    expansion_policy = output["evidence_url_expansion_policy"]
    assert expansion_policy["controller_surface"] == "skill_route_discovery_evidence_url_expansion_policy"
    assert expansion_policy["status"] == "ready"
    assert expansion_policy["decision"] == "proposal_lanes_reuse_selected_evidence_urls_only"
    assert expansion_policy["candidate_count"] == 3
    assert expansion_policy["evidence_url_expansion_allowed"] is False
    assert expansion_policy["evidence_url_expansion_count"] == 0
    assert expansion_policy["runtime_action_allowed"] is False
    assert expansion_policy["external_skill_activation_allowed"] is False
    assert expansion_policy["raw_evidence_urls_exported"] is False
    assert expansion_policy["raw_source_urls_exported"] is False
    assert [row["candidate_name"] for row in expansion_policy["rows"]] == [
        "compass-skills",
        "threejs-game-skills",
        "zhengxi-views",
    ]
    assert all(row["inventory_evidence_url_count"] == 1 for row in expansion_policy["rows"])
    assert all(row["lane_evidence_url_count"] == 1 for row in expansion_policy["rows"])
    assert all(row["evidence_url_expansion_detected"] is False for row in expansion_policy["rows"])
    assert all(lane["runtime_action"] == "none" for lane in output["proposal_lanes"])
    assert all(lane["local_validation_required"] is True for lane in output["proposal_lanes"])
    assert all(lane["evidence_url_count"] == 1 for lane in output["proposal_lanes"])
    assert "https://github.com/" not in serialized


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
    assert weak["activation_review"]["status"] == "blocked"
    assert weak["activation_review"]["activation_blockers"] == ["weak_harness_evidence"]
    assert weak["activation_review"]["weak_or_generic_evidence_requires_review"] is True
    assert weak["activation_review"]["local_eval_activation_allowed"] is False


def test_external_harness_adapter_contract_blocks_actionful_or_incomplete_adapters():
    output = evaluate_harness_behavior(
        "external_harness_adapter_contract",
        {
            "task_id": "fixture-external-harness-adapter-contract-blocked",
            "evidence": {
                "source_kind": "github_issue",
                "source_url": "https://github.com/omnigent-ai/omnigent/issues/905",
            },
            "adapter": {
                "enabled_by_default": True,
                "remote_execution_requested": True,
                "config": {
                    "adapter_name": "databricks-genie-spaces",
                    "harness_kind": "external_agent_harness",
                    "provider": "databricks",
                    "auth": {"kind": "env_or_profile_ref"},
                    "capabilities": ["space_conversation"],
                },
                "runner": {
                    "type": "remote_service",
                    "invoked": True,
                    "remote_execution_requested": True,
                },
                "input_envelope": {"fields": ["task_id"]},
                "output_envelope": {"fields": ["status"]},
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "external_harness_adapter_contract_blocked_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "adapter_config_contract_incomplete"
    assert output["config_contract"]["missing_fields"] == ["runner"]
    assert output["config_contract"]["credential_ref_present"] is False
    assert output["runner_selection"]["status"] == "blocked"
    assert output["runner_selection"]["allowed_type"] is False
    assert output["input_envelope"]["missing_fields"] == ["prompt_ref", "workspace_ref"]
    assert output["output_envelope"]["missing_fields"] == ["run_id", "artifact_refs"]
    assert output["disabled_by_default"]["enabled_by_default"] is True
    assert output["disabled_by_default"]["remote_execution_requested"] is True
    assert output["disabled_by_default"]["local_only_contract"] is False
    assert output["activation_gate"] == {
        "controller_surface": "external_harness_adapter_contract",
        "activation_scope": "local_contract_probe_only",
        "decision": "blocked_before_replay",
        "reason": "adapter_config_contract_incomplete",
        "local_contract_replay_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }
    assert [hint["code"] for hint in output["recovery_hints"]] == [
        "adapter_config_contract_incomplete",
        "runner_selection_contract_incomplete",
        "input_envelope_contract_incomplete",
        "output_envelope_contract_incomplete",
        "adapter_enabled_by_default",
        "remote_execution_requested",
    ]
    assert output["privacy"]["external_harness_launched"] is False
    assert "https://github.com/omnigent-ai/omnigent/issues/905" not in serialized


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
        "evidence_item_count": 3,
        "ignored_evidence_item_count": 0,
        "duplicate_evidence_item_count": 0,
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
    assert output["route_hint_lane_policy"] == {
        "controller_surface": "skill_route_discovery_route_hint_lane_policy",
        "status": "ready",
        "decision": "route_hints_bound_to_local_lanes",
        "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
        "selected_local_lanes": ["code_patch", "config", "documentation", "test"],
        "lanes_bounded": True,
        "rejected_lane_count": 0,
        "rejected_lanes": [],
        "rejected_candidate_count": 0,
        "downgraded_candidate_count": 0,
        "rejected_reasons": [],
        "review_required": False,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }
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
    assert output["validation_lane_gate"] == {
        "controller_surface": "skill_route_discovery_validation_lane_gate",
        "status": "ready",
        "decision": "validated_local_lanes_ready_for_supervisor_promotion",
        "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
        "selected_local_lanes": ["documentation", "config", "test", "code_patch"],
        "unsupported_lanes": [],
        "activation_lane_count": 4,
        "ready_lane_count": 4,
        "blocked_lane_count": 0,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "validation_present": True,
        "local_validation_required": True,
        "local_artifact_proof_ready": True,
        "trust_boundary_passed": True,
        "supervisor_decision": "ready_for_supervisor_promotion",
        "diagnostics": [],
        "runtime_action": "none",
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_urls_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
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
    assert output["activation_manifest"]["activation_sequence"]["controller_surface"] == (
        "skill_route_discovery_activation_sequence"
    )
    assert output["activation_manifest"]["activation_sequence"]["status"] == "ready"
    assert output["activation_manifest"]["activation_sequence"]["decision"] == "sequence_ready_for_supervisor_replay"
    assert output["activation_manifest"]["activation_sequence"]["step_count"] == 6
    assert [step["step"] for step in output["activation_manifest"]["activation_sequence"]["steps"]] == [
        "inspect_body_free_source_lineage",
        "verify_bounded_local_lanes",
        "prove_local_artifacts",
        "run_required_local_validation",
        "replay_provider_runtime_preflight",
        "handoff_to_supervisor",
    ]
    assert {step["status"] for step in output["activation_manifest"]["activation_sequence"]["steps"]} == {"ready"}
    assert all(
        step["runtime_action_allowed"] is False
        and step["external_skill_activation_allowed"] is False
        and step["external_harness_execution_allowed"] is False
        and step["provider_runtime_launch_allowed"] is False
        and step["remote_execution_allowed"] is False
        and step["raw_evidence_exported"] is False
        and step["raw_source_urls_exported"] is False
        and step["raw_target_paths_exported"] is False
        and step["raw_upstream_body_exported"] is False
        for step in output["activation_manifest"]["activation_sequence"]["steps"]
    )
    assert output["activation_manifest"]["activation_sequence"]["required_validation"] == (
        skill_route_discovery_preactivation_validation_commands()
    )
    assert output["activation_manifest"]["activation_sequence"]["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert output["activation_manifest"]["activation_sequence"]["body_free"] is True
    assert output["activation_manifest"]["activation_sequence"]["runtime_action_allowed"] is False
    assert output["activation_manifest"]["activation_sequence"]["external_skill_activation_allowed"] is False
    assert output["activation_manifest"]["activation_sequence"]["external_harness_execution_allowed"] is False
    assert output["activation_manifest"]["activation_sequence"]["provider_runtime_launch_allowed"] is False
    assert output["activation_manifest"]["activation_sequence"]["remote_execution_allowed"] is False
    assert output["activation_manifest"]["activation_sequence"]["raw_evidence_exported"] is False
    assert output["activation_manifest"]["activation_sequence"]["raw_source_urls_exported"] is False
    assert output["activation_manifest"]["activation_sequence"]["raw_target_paths_exported"] is False
    assert output["activation_manifest"]["activation_sequence"]["raw_upstream_body_exported"] is False
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
    next_validation_target = {
        "controller_surface": "skill_route_discovery_next_validation_target",
        "status": "ready",
        "decision": "validate_selected_final_bounded_target",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "selected_local_lane": "test",
        "validation_scope": "local_test_lane_only",
        "route_profiles": ["codex_workflow_gate"],
        "route_profile_count": 1,
        "evidence_item_ids": [
            "fablecodex-issue-15",
            "fablecodex-issue-18",
            "fablecodex-repo",
        ],
        "evidence_item_id_count": 3,
        "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
        "candidate_source_count": 1,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "plan_basis": "highest_priority_grouped_validation_target",
        "local_validation_required": True,
        "body_free": True,
        "runtime_action": "none",
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    next_pass_replay_packet = {
        "controller_surface": "skill_route_discovery_next_pass_replay_packet",
        "status": "complete",
        "decision": "no_next_pass_required",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "current_pass": 4,
        "next_pass": 4,
        "total_passes": 4,
        "remaining_pass_count": 0,
        "selected_target_ready": True,
        "selected_local_lane": "test",
        "validation_scope": "local_test_lane_only",
        "route_profiles": ["codex_workflow_gate"],
        "route_profile_count": 1,
        "evidence_ref_mode": "selected_item_ids_only",
        "evidence_item_ids": [
            "fablecodex-issue-15",
            "fablecodex-issue-18",
            "fablecodex-repo",
        ],
        "evidence_item_id_count": 3,
        "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
        "candidate_source_count": 1,
        "queued_validation_targets": [],
        "queued_validation_target_count": 0,
        "queued_local_lanes": [],
        "completion_blockers": [],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "packet_basis": "next_validation_target_plus_queued_bounded_lanes",
        "local_validation_required": True,
        "body_free": True,
        "runtime_action": "none",
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    next_pass_handoff = {
        "controller_surface": "skill_route_discovery_next_pass_handoff",
        "status": "complete",
        "decision": "no_next_pass_required",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "current_pass": 4,
        "next_pass": 4,
        "total_passes": 4,
        "remaining_pass_count": 0,
        "candidate_count": 1,
        "candidate_name_hashes": [stable_text_hash("codex-fable5")],
        "source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
        "recommended_local_lane_order": ["test", "documentation", "code_patch", "config"],
        "next_validation_target": next_validation_target,
        "proposal_kinds": ["code_patch", "config", "documentation", "test"],
        "route_profiles": ["codex_workflow_gate"],
        "selected_evidence_ref_count": 3,
        "selected_evidence_refs": [
            "fablecodex-issue-15",
            "fablecodex-issue-18",
            "fablecodex-repo",
        ],
        "completion_blockers": [],
        "next_pass_replay_packet": next_pass_replay_packet,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
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
    completion_recovery = {
        "controller_surface": "skill_route_discovery_completion_recovery",
        "status": "ready",
        "decision": "no_recovery_required",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "primary_recovery_lane": "none",
        "recommended_local_lane_order": ["test", "documentation", "code_patch", "config"],
        "missing_route_profiles": [],
        "completion_blocker_count": 0,
        "completion_blocker_hashes": [],
        "recovery_hint_codes": [],
        "recovery_hint_code_hashes": [],
        "replay_commands": [],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    provider_runtime_sample_gate = {
        "controller_surface": "provider_runtime_sample_gate",
        "status": "ready",
        "decision": "sample_optional_for_this_window",
        "diagnostic": "none",
        "next_action": "continue_skill_route_discovery_window",
        "required": False,
        "provided": False,
        "ready_for_local_replay": False,
        "ready_for_supervisor_promotion": False,
        "degraded_replay_only": False,
        "success_claim_allowed": False,
        "success_status_label": "",
        "sample_failure_mode": "none",
        "sample_recovery_hint_count": 0,
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "body_free": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_provider_values_exported": False,
    }
    validation_target_handoff = {
        "controller_surface": "skill_route_discovery_validation_target_handoff",
        "status": "ready",
        "decision": "continue_with_bounded_validation_targets",
        "validation_plan_status": "ready",
        "validation_plan_decision": "validate_final_bounded_local_lane_before_handoff",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "next_validation_target": next_validation_target,
        "target_count": 1,
        "selected_local_lanes": ["test"],
        "route_profiles": ["codex_workflow_gate"],
        "targets": [
            {
                "selected_local_lane": "test",
                "validation_scope": "local_test_lane_only",
                "route_profiles": ["codex_workflow_gate"],
                "route_profile_count": 1,
                "evidence_item_ids": [
                    "fablecodex-issue-15",
                    "fablecodex-issue-18",
                    "fablecodex-repo",
                ],
                "evidence_item_id_count": 3,
                "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
                "candidate_source_count": 1,
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
                ],
                "plan_basis": "completion_handoff_from_grouped_validation_targets",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        ],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    profile_validation_replay = {
        "controller_surface": "skill_route_discovery_profile_validation_replay",
        "status": "ready",
        "decision": "replay_selected_profile_validation_lanes",
        "validation_plan_status": "ready",
        "validation_plan_decision": "validate_final_bounded_local_lane_before_handoff",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "next_validation_target": next_validation_target,
        "profile_count": 1,
        "selected_local_lanes": ["test"],
        "rows": [
            {
                "route_profile": "codex_workflow_gate",
                "selected_local_lane": "test",
                "validation_scope": "local_test_lane_only",
                "operator_replay_step": "replay_local_test_lane_for_workflow_or_game_route",
                "recommended_local_lane_order": ["test", "documentation", "code_patch", "config"],
                "evidence_item_ids": [
                    "fablecodex-issue-15",
                    "fablecodex-issue-18",
                    "fablecodex-repo",
                ],
                "evidence_item_id_count": 3,
                "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
                "candidate_source_count": 1,
                "candidate_count": 1,
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
                ],
                "plan_basis": "selected_profile_item_ids_and_hashed_candidate_sources",
                "diagnostics": [],
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        ],
        "diagnostics": [],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    activation_packet = output["capability_window_completion"]["activation_packet"]
    final_slice_closure = {
        "controller_surface": "skill_route_discovery_final_slice_closure",
        "status": "ready",
        "decision": "close_skill_route_discovery_slice",
        "completion_decision": "complete_slice_for_supervisor_handoff",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "theme": "skill-route-discovery",
        "current_pass": 4,
        "total_passes": 4,
        "planned_window_complete": True,
        "final_pass_required": True,
        "final_pass_observed": True,
        "proposal_kinds": ["code_patch", "config", "documentation", "test"],
        "route_profiles": ["codex_workflow_gate"],
        "required_route_profiles": [],
        "missing_route_profiles": [],
        "selected_evidence_ref_count": 3,
        "selected_evidence_refs": [
            "fablecodex-issue-15",
            "fablecodex-issue-18",
            "fablecodex-repo",
        ],
        "selected_local_lanes": ["test"],
        "validation_target_count": 1,
        "profile_replay_status": "ready",
        "profile_rows": [
            {
                "route_profile": "codex_workflow_gate",
                "selected_local_lane": "test",
                "validation_scope": "local_test_lane_only",
                "operator_replay_step": "replay_local_test_lane_for_workflow_or_game_route",
                "evidence_item_ids": [
                    "fablecodex-issue-15",
                    "fablecodex-issue-18",
                    "fablecodex-repo",
                ],
                "evidence_item_id_count": 3,
                "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
                "candidate_source_count": 1,
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                    "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
                ],
                "diagnostics": [],
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        ],
        "activation_manifest_status": "ready",
        "activation_sequence_status": "ready",
        "activation_packet_status": "ready",
        "activation_packet_decision": "packet_ready_for_supervisor_replay",
        "completion_recovery_status": "ready",
        "completion_recovery_decision": "no_recovery_required",
        "completion_blocker_count": 0,
        "completion_blocker_hashes": [],
        "recovery_hint_codes": [],
        "replay_commands": [],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "supervisor_handoff_ready": True,
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    provider_runtime_completion_handoff = {
        "controller_surface": "provider_runtime_completion_handoff",
        "status": "not_applicable",
        "decision": "provider_runtime_completion_handoff_not_required_for_theme",
        "completion_status": "ready",
        "completion_decision": "complete_slice_for_supervisor_handoff",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "theme": "skill-route-discovery",
        "current_pass": 4,
        "total_passes": 4,
        "final_pass_required": True,
        "final_pass_observed": True,
        "provider_runtime_sample_gate_status": "ready",
        "provider_runtime_sample_gate_decision": "sample_optional_for_this_window",
        "provider_runtime_sample_required": False,
        "provider_runtime_sample_provided": False,
        "provider_runtime_sample_route_status": "missing",
        "provider_runtime_sample_ready_for_local_replay": False,
        "provider_runtime_sample_ready_for_supervisor_promotion": False,
        "provider_runtime_degraded_replay_only": False,
        "success_claim_allowed": False,
        "activation_packet_status": "ready",
        "activation_packet_ready": True,
        "final_slice_closure_status": "ready",
        "final_slice_closure_ready": True,
        "completion_blocker_count": 0,
        "completion_blocker_hashes": [],
        "recovery_hint_codes": [],
        "recovery_hint_code_hashes": [],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "body_free": True,
        "body_free_diagnostics_only": True,
        "runtime_action": "none",
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_provider_values_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    local_lane_closure = output["capability_window_completion"]["completion_report"]["local_lane_closure"]
    profile_validation_gate = output["capability_window_completion"]["completion_report"]["profile_validation_gate"]
    activation_handoff = output["capability_window_completion"]["completion_report"]["activation_handoff"]
    completion_audit = output["capability_window_completion"]["completion_report"]["completion_audit"]
    completion_replay_checklist = output["capability_window_completion"]["completion_report"][
        "completion_replay_checklist"
    ]
    final_route_handoff_manifest = output["capability_window_completion"]["completion_report"][
        "final_route_handoff_manifest"
    ]
    route_validation_lane_queue = output["capability_window_completion"]["completion_report"][
        "route_validation_lane_queue"
    ]
    secondary_harness_bridge = output["capability_window_completion"]["completion_report"][
        "secondary_harness_bridge"
    ]
    provider_runtime_interpretation_panel = output["capability_window_completion"]["completion_report"][
        "provider_runtime_interpretation_panel"
    ]
    completion_consistency_guard = output["capability_window_completion"]["completion_report"][
        "completion_consistency_guard"
    ]
    current_window_evidence_gate = output["capability_window_completion"]["completion_report"][
        "current_window_evidence_gate"
    ]
    runner_harness_control_plane = output["capability_window_completion"]["completion_report"][
        "runner_harness_control_plane"
    ]
    completion_report = {
        "controller_surface": "skill_route_discovery_completion_report",
        "status": "ready",
        "decision": "operator_report_ready_for_supervisor_handoff",
        "completion_status": "ready",
        "completion_decision": "complete_slice_for_supervisor_handoff",
        "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
        "theme": "skill-route-discovery",
        "current_pass": 4,
        "total_passes": 4,
        "planned_window_complete": True,
        "final_pass_required": True,
        "final_pass_observed": True,
        "proposal_kinds": ["code_patch", "config", "documentation", "test"],
        "route_profiles": ["codex_workflow_gate"],
        "selected_local_lanes": ["test"],
        "selected_evidence_ref_count": 3,
        "selected_evidence_ref_hashes": [
            stable_text_hash("fablecodex-issue-15"),
            stable_text_hash("fablecodex-issue-18"),
            stable_text_hash("fablecodex-repo"),
        ],
        "local_lane_closure": local_lane_closure,
        "profile_validation_gate": profile_validation_gate,
        "current_window_evidence_gate": current_window_evidence_gate,
        "activation_handoff": activation_handoff,
        "completion_audit": completion_audit,
        "completion_replay_checklist": completion_replay_checklist,
        "final_route_handoff_manifest": final_route_handoff_manifest,
        "route_validation_lane_queue": route_validation_lane_queue,
        "secondary_harness_bridge": secondary_harness_bridge,
        "provider_runtime_interpretation_panel": provider_runtime_interpretation_panel,
        "completion_consistency_guard": completion_consistency_guard,
        "runner_harness_control_plane": runner_harness_control_plane,
        "missing_route_profiles": [],
        "activation_packet_status": "ready",
        "final_slice_closure_status": "ready",
        "provider_runtime_completion_status": "not_applicable",
        "completion_blocker_count": 0,
        "completion_blocker_hashes": [],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
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
        "provider_runtime_sample_gate": provider_runtime_sample_gate,
        "validation_target_handoff": validation_target_handoff,
        "profile_validation_replay": profile_validation_replay,
        "profile_completion_check": {
            "controller_surface": "skill_route_discovery_profile_completion_check",
            "status": "ready",
            "decision": "profile_requirements_satisfied",
            "required_route_profiles": [],
            "observed_route_profiles": ["codex_workflow_gate"],
            "missing_route_profiles": [],
            "required_profile_count": 0,
            "observed_profile_count": 1,
            "planned_window_complete": True,
            "enforced": False,
            "body_free": True,
            "runtime_action_allowed": False,
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_evidence_urls_exported": False,
            "raw_source_urls_exported": False,
            "raw_upstream_body_exported": False,
        },
        "completion_handoff": {
            "status": "ready",
            "decision": "complete_slice_for_supervisor_handoff",
            "supervisor_next_action": "handoff_completed_skill_route_slice_to_supervisor",
            "activation_sequence_status": "ready",
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
            "provider_runtime_sample_gate": provider_runtime_sample_gate,
            "validation_target_handoff": validation_target_handoff,
            "profile_validation_replay": profile_validation_replay,
            "profile_completion_check": {
                "controller_surface": "skill_route_discovery_profile_completion_check",
                "status": "ready",
                "decision": "profile_requirements_satisfied",
                "required_route_profiles": [],
                "observed_route_profiles": ["codex_workflow_gate"],
                "missing_route_profiles": [],
                "required_profile_count": 0,
                "observed_profile_count": 1,
                "planned_window_complete": True,
                "enforced": False,
                "body_free": True,
                "runtime_action_allowed": False,
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_urls_exported": False,
                "raw_source_urls_exported": False,
                "raw_upstream_body_exported": False,
            },
            "completion_recovery": completion_recovery,
            "provider_runtime_completion_handoff": provider_runtime_completion_handoff,
            "next_pass_handoff": next_pass_handoff,
            "activation_packet": activation_packet,
            "final_slice_closure": final_slice_closure,
            "completion_report": completion_report,
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
        "next_pass_handoff": next_pass_handoff,
        "completion_recovery": completion_recovery,
        "activation_packet": activation_packet,
        "final_slice_closure": final_slice_closure,
        "provider_runtime_completion_handoff": provider_runtime_completion_handoff,
        "completion_report": completion_report,
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
    assert activation_packet["controller_surface"] == "skill_route_discovery_validated_activation_packet"
    assert activation_packet["status"] == "ready"
    assert activation_packet["decision"] == "packet_ready_for_supervisor_replay"
    assert activation_packet["row_count"] == 4
    assert activation_packet["proposal_kinds"] == ["code_patch", "config", "documentation", "test"]
    assert activation_packet["selected_evidence_refs"] == [
        "fablecodex-issue-15",
        "fablecodex-issue-18",
        "fablecodex-repo",
    ]
    assert {row["supervisor_replay_step"] for row in activation_packet["rows"]} == {
        "review_and_replay_bounded_local_lane"
    }
    assert all(row["runtime_action_allowed"] is False for row in activation_packet["rows"])
    assert activation_packet["external_skill_activation_allowed"] is False
    assert output["capability_window_completion"]["completion_report"] == completion_report
    assert current_window_evidence_gate == {
        "controller_surface": "skill_route_discovery_current_window_evidence_gate",
        "status": "ready",
        "decision": "current_window_evidence_ready_for_completion",
        "planned_window_complete": True,
        "enforced": False,
        "required_route_profiles": [],
        "observed_route_profiles": ["codex_workflow_gate"],
        "missing_route_profiles": [],
        "required_profile_count": 0,
        "observed_profile_count": 1,
        "selected_evidence_ref_count": 3,
        "selected_evidence_ref_hashes": [
            stable_text_hash("fablecodex-issue-15"),
            stable_text_hash("fablecodex-issue-18"),
            stable_text_hash("fablecodex-repo"),
        ],
        "evidence_url_hash_count": 3,
        "evidence_url_hashes": sorted([
            stable_text_hash("https://github.com/baskduf/FableCodex"),
            stable_text_hash("https://github.com/dongshuyan/compass-skills"),
            stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
        ]),
        "diagnostics": [],
        "diagnostic_count": 0,
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
    assert output["capability_window_completion"]["completion_report"]["runtime_action_allowed"] is False
    assert output["capability_window_completion"]["completion_report"]["raw_evidence_urls_exported"] is False
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
                    "Agent director skill package for Three.js games with gameplay, graphics, "
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

    intake = output["candidate_lane_intake"]
    assert intake["controller_surface"] == "skill_route_discovery_candidate_lane_intake"
    assert intake["status"] == "review"
    assert intake["decision"] == "review_candidate_inventory_before_lane_selection"
    assert intake["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert intake["candidate_count"] == 3
    assert intake["proposal_kind_count"] == 6
    assert intake["downgraded_candidate_count"] == 3
    assert intake["rejected_candidate_count"] == 0
    assert intake["inventory_bounded"] is True
    assert intake["activation_decision"] == "review_degraded_lane_before_activation"
    assert intake["runtime_action_allowed"] is False
    assert intake["external_skill_activation_allowed"] is False
    assert intake["external_skill_code_allowed"] is False
    assert intake["raw_source_urls_exported"] is False
    assert intake["raw_evidence_urls_exported"] is False
    assert intake["raw_upstream_body_exported"] is False

    intake_rows_by_source = {row["source_hash"]: row for row in intake["rows"]}
    assert intake_rows_by_source[stable_text_hash("https://github.com/baskduf/FableCodex")][
        "proposal_kinds"
    ] == ["documentation", "test"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/baskduf/FableCodex")][
        "matched_route_terms"
    ] == ["codex", "skill", "workflow"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/baskduf/FableCodex")][
        "recommended_local_lane_order"
    ] == ["test", "documentation"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/baskduf/FableCodex")][
        "lane_selection_reason"
    ] == "workflow_gate_routes_start_with_replay_or_documented_gate_review"
    assert intake_rows_by_source[stable_text_hash("https://github.com/baskduf/FableCodex")][
        "downgraded_lanes"
    ] == ["runtime_execution"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/dongshuyan/compass-skills")][
        "route_profiles"
    ] == ["skill_ecosystem_state_handoff"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/dongshuyan/compass-skills")][
        "matched_route_terms"
    ] == ["agents", "skill", "skills"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/dongshuyan/compass-skills")][
        "recommended_local_lane_order"
    ] == ["config", "test"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/dongshuyan/compass-skills")][
        "lane_selection_reason"
    ] == "state_handoff_routes_start_with_metadata_and_boundary_review"
    assert intake_rows_by_source[stable_text_hash("https://github.com/dongshuyan/compass-skills")][
        "downgraded_lanes"
    ] == ["install"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")][
        "route_profiles"
    ] == ["game_frontend_workflow"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")][
        "matched_route_terms"
    ] == ["agent", "skill", "skills"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")][
        "recommended_local_lane_order"
    ] == ["documentation", "code_patch"]
    assert intake_rows_by_source[stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")][
        "lane_selection_reason"
    ] == "game_skill_routes_start_with_validation_and_boundary_review"
    assert intake_rows_by_source[stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")][
        "downgraded_lanes"
    ] == ["execute"]
    for row in intake["rows"]:
        assert row["lane_selection_review_required"] is True
        assert row["lanes_bounded"] is True
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    term_review = output["term_route_review"]
    assert term_review["controller_surface"] == "skill_route_discovery_term_route_review"
    assert term_review["status"] == "review"
    assert term_review["decision"] == "review_term_triggered_routes_before_activation"
    assert term_review["trigger_terms"] == ["agent", "agents", "codex", "skill", "skills", "workflow"]
    assert term_review["matched_term_counts"] == {
        "agent": 1,
        "agents": 1,
        "codex": 1,
        "skill": 3,
        "skills": 2,
        "workflow": 1,
    }
    assert term_review["candidate_count"] == 3
    assert term_review["diagnostics"] == []
    assert term_review["activation_decision"] == "review_degraded_lane_before_activation"
    assert term_review["runtime_action_allowed"] is False
    assert term_review["external_skill_activation_allowed"] is False
    assert term_review["raw_source_urls_exported"] is False
    assert term_review["raw_evidence_urls_exported"] is False
    rows_by_source = {row["source_hash"]: row for row in term_review["rows"]}
    assert rows_by_source[stable_text_hash("https://github.com/baskduf/FableCodex")][
        "proposal_kinds"
    ] == ["documentation", "test"]
    assert rows_by_source[stable_text_hash("https://github.com/dongshuyan/compass-skills")][
        "proposal_kinds"
    ] == ["config", "test"]
    assert rows_by_source[stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")][
        "proposal_kinds"
    ] == ["documentation", "code_patch"]
    for row in term_review["rows"]:
        assert row["matched_route_terms"]
        assert row["lanes_bounded"] is True
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["raw_source_url_exported"] is False
        assert row["raw_evidence_urls_exported"] is False

        assert row["raw_upstream_body_exported"] is False

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


def test_skill_route_discovery_mixed_local_lane_probe_prefers_skill_route_first():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "skill-route-discovery-mixed-local-lane-probe",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "codex-agent-skills-workflow",
                    "source_url": "https://github.com/baskduf/FableCodex",
                    "evidence_summary": (
                        "Agent Codex skill and skills workflow package with verification gates, "
                        "routing docs, examples, tests, and local replay habits."
                    ),
                    "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                    "evidence_item_ids": ["p3-mixed-skill-workflow-routing"],
                    "evidence_urls": ["https://github.com/baskduf/FableCodex"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_mixed_local_lane_probe_inline.json",
    )
    serialized = json.dumps(output["mixed_local_lane_probe"], sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"

    probe = output["mixed_local_lane_probe"]
    assert probe["controller_surface"] == "skill_route_discovery_mixed_local_lane_probe"
    assert probe["status"] == "ready"
    assert probe["decision"] == "mixed_skill_workflow_routes_skill_discovery_first"
    assert probe["candidate_count"] == 1
    assert probe["full_mixed_signal_count"] == 1
    assert probe["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert probe["primary_route"] == "skill_route_discovery"
    assert probe["secondary_lane"] == "agent_harness_eval_after_local_corroboration"
    assert probe["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert probe["diagnostics"] == []
    assert probe["runtime_action_allowed"] is False
    assert probe["external_skill_activation_allowed"] is False
    assert probe["external_agent_activation_allowed"] is False
    assert probe["external_harness_execution_allowed"] is False
    assert probe["provider_runtime_launch_allowed"] is False
    assert probe["raw_source_urls_exported"] is False
    assert probe["raw_evidence_urls_exported"] is False
    assert probe["raw_upstream_body_exported"] is False

    row = probe["rows"][0]
    assert row["source_hash"] == stable_text_hash("https://github.com/baskduf/FableCodex")
    assert row["route_hint"] == "skill_route_discovery"
    assert row["route_probe_decision"] == "skill_route_discovery_first"
    assert row["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert row["matched_route_terms"] == ["agent", "codex", "skill", "skills", "workflow"]
    assert row["proposal_kinds"] == ["documentation", "config", "test", "code_patch"]
    assert row["recommended_local_lane_order"] == ["test", "documentation", "code_patch", "config"]
    assert row["evidence_item_ids"] == ["p3-mixed-skill-workflow-routing"]
    assert row["local_validation_required"] is True
    assert row["runtime_action"] == "none"
    assert row["external_skill_activation_allowed"] is False
    assert row["external_agent_activation_allowed"] is False
    assert row["raw_source_url_exported"] is False
    assert row["raw_evidence_urls_exported"] is False
    assert row["raw_upstream_body_exported"] is False
    assert "https://github.com/baskduf/FableCodex" not in serialized


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
    next_validation_target = {
        "controller_surface": "skill_route_discovery_next_validation_target",
        "status": "ready",
        "decision": "continue_with_selected_bounded_validation_target",
        "supervisor_next_action": "continue_skill_route_discovery_window",
        "selected_local_lane": "test",
        "validation_scope": "local_test_lane_only",
        "route_profiles": ["codex_workflow_gate"],
        "route_profile_count": 1,
        "evidence_item_ids": [
            "fablecodex-issue-15",
            "fablecodex-issue-18",
            "fablecodex-repo",
        ],
        "evidence_item_id_count": 3,
        "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
        "candidate_source_count": 1,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "plan_basis": "highest_priority_grouped_validation_target",
        "local_validation_required": True,
        "body_free": True,
        "runtime_action": "none",
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert completion["next_pass_handoff"] == {
        "controller_surface": "skill_route_discovery_next_pass_handoff",
        "status": "ready",
        "decision": "continue_bounded_lane_validation_next_pass",
        "supervisor_next_action": "continue_skill_route_discovery_window",
        "current_pass": 3,
        "next_pass": 4,
        "total_passes": 4,
        "remaining_pass_count": 1,
        "candidate_count": 1,
        "candidate_name_hashes": [stable_text_hash("codex-fable5")],
        "source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
        "recommended_local_lane_order": ["test", "documentation", "code_patch", "config"],
        "next_validation_target": next_validation_target,
        "proposal_kinds": ["code_patch", "config", "documentation", "test"],
        "route_profiles": ["codex_workflow_gate"],
        "selected_evidence_ref_count": 3,
        "selected_evidence_refs": [
            "fablecodex-issue-15",
            "fablecodex-issue-18",
            "fablecodex-repo",
        ],
        "completion_blockers": ["capability_window_not_at_final_pass"],
        "next_pass_replay_packet": {
            "controller_surface": "skill_route_discovery_next_pass_replay_packet",
            "status": "ready",
            "decision": "continue_bounded_lane_validation_next_pass",
            "supervisor_next_action": "continue_skill_route_discovery_window",
            "current_pass": 3,
            "next_pass": 4,
            "total_passes": 4,
            "remaining_pass_count": 1,
            "selected_target_ready": True,
            "selected_local_lane": "test",
            "validation_scope": "local_test_lane_only",
            "route_profiles": ["codex_workflow_gate"],
            "route_profile_count": 1,
            "evidence_ref_mode": "selected_item_ids_only",
            "evidence_item_ids": [
                "fablecodex-issue-15",
                "fablecodex-issue-18",
                "fablecodex-repo",
            ],
            "evidence_item_id_count": 3,
            "candidate_source_hashes": [stable_text_hash("https://github.com/baskduf/FableCodex")],
            "candidate_source_count": 1,
            "queued_validation_targets": [],
            "queued_validation_target_count": 0,
            "queued_local_lanes": [],
            "completion_blockers": ["capability_window_not_at_final_pass"],
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "provider_runtime_replay_commands": [
                "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
            ],
            "packet_basis": "next_validation_target_plus_queued_bounded_lanes",
            "local_validation_required": True,
            "body_free": True,
            "runtime_action": "none",
            "runtime_action_allowed": False,
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_evidence_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_source_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        },
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
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
    assert completion["completion_handoff"]["next_pass_handoff"] == completion["next_pass_handoff"]
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


def test_skill_route_discovery_pass2_fixture_covers_required_profiles_and_next_handoff():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass2_window.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)
    completion = output["capability_window_completion"]
    validation_plan = output["validation_lane_plan"]

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["registry"]["candidate_count"] == 4
    assert output["lane_map"]["proposal_lane_count"] == 16
    assert output["route_profile_review"]["profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    bounded_matrix = output["bounded_profile_lane_matrix"]
    assert bounded_matrix["controller_surface"] == "skill_route_discovery_bounded_profile_lane_matrix"
    assert bounded_matrix["status"] == "ready"
    assert bounded_matrix["decision"] == "profile_lanes_bounded_for_local_validation"
    assert bounded_matrix["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert bounded_matrix["required_route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert bounded_matrix["observed_route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert bounded_matrix["missing_route_profiles"] == []
    assert bounded_matrix["diagnostics"] == []
    matrix_rows = {row["route_profile"]: row for row in bounded_matrix["rows"]}
    assert set(matrix_rows) == {
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    }
    assert matrix_rows["codex_workflow_gate"]["selected_local_lanes"] == ["test"]
    assert matrix_rows["game_frontend_workflow"]["selected_local_lanes"] == ["test"]
    assert matrix_rows["skill_ecosystem_state_handoff"]["selected_local_lanes"] == ["config"]
    assert matrix_rows["source_cited_domain_research"]["selected_local_lanes"] == ["test"]
    for row in matrix_rows.values():
        assert row["present"] is True
        assert row["available_local_lanes"] == ["documentation", "config", "test", "code_patch"]
        assert row["lanes_bounded"] is True
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_source_urls_exported"] is False
        assert row["raw_upstream_body_exported"] is False
    proposal_catalog = output["proposal_validation_lane_catalog"]
    assert proposal_catalog["controller_surface"] == "skill_route_discovery_proposal_validation_lane_catalog"
    assert proposal_catalog["status"] == "ready"
    assert proposal_catalog["decision"] == "validate_grouped_bounded_local_lanes"
    assert proposal_catalog["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert proposal_catalog["lane_count"] == 4
    assert proposal_catalog["candidate_count"] == 4
    assert proposal_catalog["rows_bounded"] is True
    assert proposal_catalog["rows_runtime_safe"] is True
    assert proposal_catalog["all_rows_require_local_validation"] is True
    assert proposal_catalog["unsupported_lane_count"] == 0
    assert proposal_catalog["blocked_requested_action_count"] == 0
    assert proposal_catalog["diagnostics"] == []
    assert proposal_catalog["source_lineage"] == {
        "body_free": True,
        "lineage_mode": "single_or_independent_sources",
        "candidate_source_count": 4,
        "related_source_count": 0,
        "fork_or_mirror_lineage_collapsed": False,
    }
    assert proposal_catalog["blocked_discovery_actions"] == [
        "clone_and_run",
        "delete_local_skill",
        "enable",
        "execute",
        "install",
        "run",
    ]
    assert proposal_catalog["runtime_action_allowed"] is False
    assert proposal_catalog["external_skill_activation_allowed"] is False
    assert proposal_catalog["external_harness_execution_allowed"] is False
    assert proposal_catalog["provider_runtime_launch_allowed"] is False
    assert proposal_catalog["remote_execution_allowed"] is False
    assert proposal_catalog["raw_evidence_exported"] is False
    assert proposal_catalog["raw_source_urls_exported"] is False
    assert proposal_catalog["raw_evidence_urls_exported"] is False
    assert proposal_catalog["raw_upstream_body_exported"] is False
    assert [row["proposal_kind"] for row in proposal_catalog["rows"]] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    expected_profile_set = {
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    }
    expected_item_ids = [
        "p1-skill-route-discovery-compass",
        "p2-skill-route-discovery-threejs",
        "p2-skill-route-discovery-zhengxi-views",
        "p3-mixed-codex-skill-workflow-probe",
    ]
    expected_source_hashes = [
        stable_text_hash("https://github.com/baskduf/FableCodex"),
        stable_text_hash("https://github.com/dongshuyan/compass-skills"),
        stable_text_hash("https://github.com/lyra81604/zhengxi-views"),
        stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
    ]
    for row in proposal_catalog["rows"]:
        assert row["candidate_count"] == 4
        assert set(row["route_profiles"]) == expected_profile_set
        assert row["evidence_item_ids"] == expected_item_ids
        assert row["source_hashes"] == expected_source_hashes
        assert row["evidence_item_id_count"] == 4
        assert row["unsupported_lane_count"] == 0
        assert row["blocked_requested_action_count"] == 0
        assert row["validation_error_count"] == 0
        assert row["lanes_bounded"] is True
        assert row["activation_ready"] is True
        assert row["activation_blockers"] == []
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_source_urls_exported"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_upstream_body_exported"] is False
    intake_rows = {
        tuple(row["route_profiles"]): row
        for row in output["candidate_lane_intake"]["rows"]
    }
    compass_handoff = intake_rows[("skill_ecosystem_state_handoff",)]["handoff_metadata"]
    assert compass_handoff["controller_surface"] == "skill_route_discovery_lane_handoff_metadata"
    assert compass_handoff["handoff_scope"] == "candidate_inventory"
    assert compass_handoff["status"] == "ready"
    assert compass_handoff["selected_local_lane"] == "config"
    assert compass_handoff["queued_local_lanes"] == ["test", "documentation", "code_patch"]
    assert compass_handoff["validation_gates"] == ["state_handoff_boundary_before_profile_or_memory_write"]
    assert compass_handoff["local_validation_required"] is True
    assert compass_handoff["runtime_action"] == "none"
    assert compass_handoff["external_skill_activation_allowed"] is False
    assert compass_handoff["external_harness_execution_allowed"] is False
    assert compass_handoff["provider_runtime_launch_allowed"] is False
    assert compass_handoff["remote_execution_allowed"] is False
    assert compass_handoff["raw_source_url_exported"] is False
    assert compass_handoff["raw_evidence_urls_exported"] is False
    assert compass_handoff["raw_upstream_body_exported"] is False
    profile_contract = output["profile_lane_acceptance_contract"]
    assert profile_contract["controller_surface"] == "skill_route_discovery_profile_lane_acceptance_contract"
    assert profile_contract["status"] == "ready"
    assert profile_contract["decision"] == "profile_lanes_ready_for_bounded_local_validation"
    assert profile_contract["profile_count"] == 4
    assert profile_contract["ready_profile_count"] == 4
    assert profile_contract["blocked_profile_count"] == 0
    assert profile_contract["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert profile_contract["selected_first_local_lanes"] == ["config", "test"]
    assert profile_contract["evidence_ref_mode"] == "selected_item_ids_only"
    profile_rows = {row["route_profile"]: row for row in profile_contract["rows"]}
    assert profile_rows["codex_workflow_gate"]["validation_gate"] == (
        "skill_route_discovery_first_before_workflow_gate"
    )
    assert profile_rows["codex_workflow_gate"]["selected_first_local_lane"] == "test"
    assert profile_rows["codex_workflow_gate"]["validation_scope"] == "local_test_lane_only"
    assert profile_rows["codex_workflow_gate"]["acceptance_gates"]["first_route_confirmed"] is True
    assert profile_rows["game_frontend_workflow"]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert profile_rows["game_frontend_workflow"]["selected_first_local_lane"] == "test"
    assert profile_rows["game_frontend_workflow"]["validation_scope"] == "local_test_lane_only"
    assert profile_rows["skill_ecosystem_state_handoff"]["validation_gate"] == (
        "state_handoff_boundary_before_profile_or_memory_write"
    )
    assert profile_rows["skill_ecosystem_state_handoff"]["selected_first_local_lane"] == "config"
    assert profile_rows["skill_ecosystem_state_handoff"]["validation_scope"] == "local_config_lane_only"
    assert profile_rows["source_cited_domain_research"]["validation_gate"] == (
        "source_citation_and_advice_boundary_before_domain_skill_activation"
    )
    assert profile_rows["source_cited_domain_research"]["selected_first_local_lane"] == "test"
    assert profile_rows["source_cited_domain_research"]["validation_scope"] == "local_test_lane_only"
    assert all(row["local_validation_required"] is True for row in profile_contract["rows"])
    assert all(row["runtime_action"] == "none" for row in profile_contract["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in profile_contract["rows"])
    assert profile_contract["runtime_action_allowed"] is False
    assert profile_contract["external_skill_activation_allowed"] is False
    assert profile_contract["provider_runtime_launch_allowed"] is False
    assert profile_contract["remote_execution_allowed"] is False
    assert profile_contract["raw_evidence_urls_exported"] is False
    assert profile_contract["raw_source_urls_exported"] is False
    assert profile_contract["raw_upstream_body_exported"] is False
    assert completion["status"] == "in_progress"
    assert completion["decision"] == "continue_capability_window_before_completion"
    assert completion["current_pass"] == 2
    assert completion["total_passes"] == 4
    assert completion["profile_completion_check"]["status"] == "ready"
    assert completion["next_pass_handoff"]["status"] == "ready"
    assert completion["next_pass_handoff"]["next_pass"] == 3
    assert completion["next_pass_handoff"]["remaining_pass_count"] == 2
    assert completion["next_pass_handoff"]["supervisor_next_action"] == "continue_skill_route_discovery_window"
    assert set(completion["next_pass_handoff"]["recommended_local_lane_order"]) == {
        "documentation",
        "config",
        "test",
        "code_patch",
    }
    assert completion["validation_target_handoff"]["controller_surface"] == (
        "skill_route_discovery_validation_target_handoff"
    )
    assert completion["validation_target_handoff"]["status"] == "ready"
    assert completion["validation_target_handoff"]["decision"] == (
        "continue_with_bounded_validation_targets"
    )
    assert completion["validation_target_handoff"]["selected_local_lanes"] == ["config", "test"]
    assert completion["validation_target_handoff"]["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert [
        (target["selected_local_lane"], target["route_profiles"], target["validation_scope"])
        for target in completion["validation_target_handoff"]["targets"]
    ] == [
        ("config", ["skill_ecosystem_state_handoff"], "local_config_lane_only"),
        (
            "test",
            ["codex_workflow_gate", "game_frontend_workflow", "source_cited_domain_research"],
            "local_test_lane_only",
        ),
    ]
    assert completion["completion_handoff"]["validation_target_handoff"] == (
        completion["validation_target_handoff"]
    )
    assert validation_plan["controller_surface"] == "skill_route_discovery_validation_lane_plan"
    assert validation_plan["status"] == "ready"
    assert validation_plan["decision"] == "continue_bounded_local_validation_lane"
    assert validation_plan["current_pass"] == 2
    assert validation_plan["next_pass"] == 3
    assert validation_plan["remaining_pass_count"] == 2
    assert validation_plan["catalog_status"] == "ready"
    assert validation_plan["route_profile_count"] == 4
    assert [
        (row["route_profile"], row["selected_local_lane"], row["validation_scope"])
        for row in validation_plan["rows"]
    ] == [
        ("codex_workflow_gate", "test", "local_test_lane_only"),
        ("game_frontend_workflow", "test", "local_test_lane_only"),
        ("skill_ecosystem_state_handoff", "config", "local_config_lane_only"),
        ("source_cited_domain_research", "test", "local_test_lane_only"),
    ]
    assert validation_plan["lane_validation_target_count"] == 2
    assert validation_plan["next_validation_target"] == {
        "controller_surface": "skill_route_discovery_next_validation_target",
        "status": "ready",
        "decision": "continue_with_selected_bounded_validation_target",
        "supervisor_next_action": "continue_skill_route_discovery_window",
        "selected_local_lane": "test",
        "validation_scope": "local_test_lane_only",
        "route_profiles": ["codex_workflow_gate", "game_frontend_workflow", "source_cited_domain_research"],
        "route_profile_count": 3,
        "evidence_item_ids": [
            "p2-skill-route-discovery-threejs",
            "p2-skill-route-discovery-zhengxi-views",
            "p3-mixed-codex-skill-workflow-probe",
        ],
        "evidence_item_id_count": 3,
        "candidate_source_hashes": [
            stable_text_hash("https://github.com/baskduf/FableCodex"),
            stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
            stable_text_hash("https://github.com/lyra81604/zhengxi-views"),
        ],
        "candidate_source_count": 3,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "plan_basis": "highest_priority_grouped_validation_target",
        "local_validation_required": True,
        "body_free": True,
        "runtime_action": "none",
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert completion["next_pass_handoff"]["next_validation_target"] == (
        validation_plan["next_validation_target"]
    )
    pass2_packet = output["pass2_handoff_packet"]
    assert pass2_packet["controller_surface"] == "skill_route_discovery_pass2_handoff_packet"
    assert pass2_packet["status"] == "ready"
    assert pass2_packet["decision"] == "continue_pass2_selected_lane_with_queued_bounded_handoff"
    assert pass2_packet["current_pass"] == 2
    assert pass2_packet["next_pass"] == 3
    assert pass2_packet["selected_local_lanes"] == ["test"]
    assert pass2_packet["queued_local_lanes"] == ["config"]
    assert pass2_packet["local_artifact_review_count"] == 2
    assert pass2_packet["local_artifact_review_ready_count"] == 2
    assert set(pass2_packet["target_path_hashes"]) == {
        stable_text_hash("src/blackhole_agent/proposal_synthesis.py"),
        stable_text_hash("tests/test_harness_eval.py"),
        stable_text_hash("tests/test_skill_routing.py"),
    }
    assert pass2_packet["mixed_skill_workflow_candidate_count"] == 1
    assert pass2_packet["mixed_skill_workflow_primary_route"] == "skill_route_discovery"
    assert pass2_packet["mixed_skill_workflow_probe_status"] == "ready"
    assert pass2_packet["secondary_lane"] == "agent_harness_eval_after_local_corroboration"
    assert pass2_packet["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert pass2_packet["secondary_harness_eval_allowed"] is False
    assert pass2_packet["profile_lane_acceptance_contract"] == profile_contract
    checkpoints = pass2_packet["operator_checkpoint_list"]
    assert checkpoints["controller_surface"] == "skill_route_discovery_pass2_operator_checkpoint_list"
    assert checkpoints["status"] == "ready"
    assert checkpoints["decision"] == "operator_can_replay_pass2_checkpoints"
    assert checkpoints["checkpoint_count"] == 2
    assert checkpoints["selected_checkpoint_count"] == 1
    assert checkpoints["queued_checkpoint_count"] == 1
    assert [row["checkpoint"] for row in checkpoints["rows"]] == [
        "replay_selected_current_pass_lane",
        "carry_queued_bounded_lane_to_next_pass",
    ]
    assert [row["selected_local_lane"] for row in checkpoints["rows"]] == ["test", "config"]
    assert {row["status"] for row in checkpoints["rows"]} == {"ready"}
    assert all(row["evidence_ref_mode"] == "selected_item_ids_only" for row in checkpoints["rows"])
    assert all(row["queue_fingerprint"] for row in checkpoints["rows"])
    assert all(row["blockers"] == [] for row in checkpoints["rows"])
    assert [row["artifact_contract_kind"] for row in checkpoints["rows"]] == ["test", "config"]
    assert [row["target_path_count"] for row in checkpoints["rows"]] == [2, 1]
    assert all(row["local_artifact_review"]["status"] == "ready" for row in checkpoints["rows"])
    assert all(
        row["operator_review_requirements"]
        == ["changed_file_review", "focused_local_validation", "rollback_artifact", "review_note"]
        for row in checkpoints["rows"]
    )
    assert all(row["runtime_action_allowed"] is False for row in checkpoints["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in checkpoints["rows"])
    assert all(row["external_agent_activation_allowed"] is False for row in checkpoints["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in checkpoints["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in checkpoints["rows"])
    assert all(row["raw_source_urls_exported"] is False for row in checkpoints["rows"])
    assert checkpoints["runtime_action_allowed"] is False
    assert checkpoints["external_skill_activation_allowed"] is False
    assert checkpoints["external_harness_execution_allowed"] is False
    assert checkpoints["raw_evidence_urls_exported"] is False
    contract = pass2_packet["local_lane_acceptance_contract"]
    assert contract["controller_surface"] == "skill_route_discovery_pass2_local_lane_acceptance_contract"
    assert contract["status"] == "ready"
    assert contract["decision"] == "pass2_lanes_accepted_for_bounded_local_replay"
    assert contract["contract_scope"] == "selected_and_queued_pass2_bounded_lanes"
    assert contract["checkpoint_count"] == 2
    assert contract["selected_checkpoint_count"] == 1
    assert contract["queued_checkpoint_count"] == 1
    assert contract["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert contract["selected_local_lanes"] == ["test"]
    assert contract["queued_local_lanes"] == ["config"]
    assert contract["local_artifact_review_count"] == 2
    assert contract["local_artifact_review_ready_count"] == 2
    assert contract["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert contract["secondary_route_gates"] == {
        "mixed_skill_workflow_primary_route_preserved": True,
        "secondary_harness_lane_blocked": True,
        "secondary_harness_eval_denied": True,
    }
    assert [row["selected_local_lane"] for row in contract["rows"]] == ["test", "config"]
    assert [row["route_profiles"] for row in contract["rows"]] == [
        ["codex_workflow_gate", "game_frontend_workflow", "source_cited_domain_research"],
        ["skill_ecosystem_state_handoff"],
    ]
    assert all(row["accepted"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["bounded_lane"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["local_validation_required"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["runtime_action_none"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["external_skill_activation_denied"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["external_harness_execution_denied"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["provider_runtime_launch_denied"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["remote_execution_denied"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["raw_evidence_urls_not_exported"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["raw_source_urls_not_exported"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["raw_target_paths_not_exported"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["raw_upstream_body_not_exported"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["local_artifact_review_ready"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["target_paths_hashed"] is True for row in contract["rows"])
    assert all(row["acceptance_gates"]["checkpoint_ready"] is True for row in contract["rows"])
    assert contract["secondary_harness_eval_allowed"] is False
    assert contract["runtime_action_allowed"] is False
    assert contract["external_skill_activation_allowed"] is False
    assert contract["external_agent_activation_allowed"] is False
    assert contract["external_harness_execution_allowed"] is False
    assert contract["raw_evidence_urls_exported"] is False
    preview = pass2_packet["bounded_activation_preview"]
    assert preview["controller_surface"] == "skill_route_discovery_pass2_bounded_activation_preview"
    assert preview["status"] == "ready"
    assert preview["decision"] == "replay_selected_lane_and_carry_queued_lanes"
    assert preview["preview_row_count"] == 2
    assert preview["selected_preview_count"] == 1
    assert preview["queued_preview_count"] == 1
    assert preview["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert preview["selected_local_lanes"] == ["test"]
    assert preview["queued_local_lanes"] == ["config"]
    assert preview["evidence_ref_mode"] == "selected_item_ids_only"
    assert preview["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    ]
    assert [row["activation_preview_step"] for row in preview["rows"]] == [
        "replay_selected_current_pass_lane",
        "carry_queued_bounded_lane_to_next_pass",
    ]
    assert {row["activation_preview_status"] for row in preview["rows"]} == {"ready"}
    assert {row["runtime_action"] for row in preview["rows"]} == {"none"}
    assert all(row["activation_blockers"] == [] for row in preview["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in preview["rows"])
    assert all(row["external_agent_activation_allowed"] is False for row in preview["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in preview["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in preview["rows"])
    assert preview["runtime_action_allowed"] is False
    assert preview["external_skill_activation_allowed"] is False
    assert preview["external_agent_activation_allowed"] is False
    assert preview["external_harness_execution_allowed"] is False
    assert preview["raw_evidence_urls_exported"] is False
    assert preview["raw_source_urls_exported"] is False
    assert preview["raw_upstream_body_exported"] is False
    assert pass2_packet["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass",
        "p2-skill-route-discovery-threejs",
        "p2-skill-route-discovery-zhengxi-views",
        "p3-mixed-codex-skill-workflow-probe",
    ]
    assert pass2_packet["runtime_action_allowed"] is False
    assert pass2_packet["external_skill_activation_allowed"] is False
    assert pass2_packet["external_agent_activation_allowed"] is False
    assert pass2_packet["external_harness_execution_allowed"] is False
    assert pass2_packet["raw_evidence_urls_exported"] is False
    assert pass2_packet["raw_source_urls_exported"] is False
    assert pass2_packet["raw_upstream_body_exported"] is False
    replay_packet = completion["next_pass_handoff"]["next_pass_replay_packet"]
    assert replay_packet["controller_surface"] == "skill_route_discovery_next_pass_replay_packet"
    assert replay_packet["status"] == "ready"
    assert replay_packet["decision"] == "continue_bounded_lane_validation_next_pass"
    assert replay_packet["current_pass"] == 2
    assert replay_packet["next_pass"] == 3
    assert replay_packet["remaining_pass_count"] == 2
    assert replay_packet["selected_target_ready"] is True
    assert replay_packet["selected_local_lane"] == "test"
    assert replay_packet["validation_scope"] == "local_test_lane_only"
    assert replay_packet["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "source_cited_domain_research",
    ]
    assert replay_packet["evidence_ref_mode"] == "selected_item_ids_only"
    assert replay_packet["evidence_item_ids"] == [
        "p2-skill-route-discovery-threejs",
        "p2-skill-route-discovery-zhengxi-views",
        "p3-mixed-codex-skill-workflow-probe",
    ]
    assert replay_packet["candidate_source_hashes"] == [
        stable_text_hash("https://github.com/baskduf/FableCodex"),
        stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
        stable_text_hash("https://github.com/lyra81604/zhengxi-views"),
    ]
    assert replay_packet["queued_local_lanes"] == ["config"]
    assert replay_packet["queued_validation_target_count"] == 1
    assert replay_packet["queued_validation_targets"][0]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert replay_packet["queued_validation_targets"][0]["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass"
    ]
    assert replay_packet["runtime_action"] == "none"
    assert replay_packet["external_skill_activation_allowed"] is False
    assert replay_packet["external_skill_code_allowed"] is False
    assert replay_packet["raw_evidence_urls_exported"] is False
    assert replay_packet["raw_source_urls_exported"] is False
    assert completion["completion_handoff"]["next_pass_handoff"]["next_pass_replay_packet"] == replay_packet
    assert completion["validation_target_handoff"]["next_validation_target"] == (
        validation_plan["next_validation_target"]
    )
    assert output["profile_validation_replay"]["next_validation_target"] == (
        validation_plan["next_validation_target"]
    )
    assert [
        (target["selected_local_lane"], target["route_profiles"], target["validation_scope"])
        for target in validation_plan["lane_validation_targets"]
    ] == [
        ("config", ["skill_ecosystem_state_handoff"], "local_config_lane_only"),
        (
            "test",
            ["codex_workflow_gate", "game_frontend_workflow", "source_cited_domain_research"],
            "local_test_lane_only",
        ),
    ]
    assert all(
        target["plan_basis"] == "selected_lane_grouped_route_profiles_and_hashed_candidate_sources"
        for target in validation_plan["lane_validation_targets"]
    )
    assert all(target["runtime_action"] == "none" for target in validation_plan["lane_validation_targets"])
    assert all(
        target["external_skill_activation_allowed"] is False
        for target in validation_plan["lane_validation_targets"]
    )
    assert [row["evidence_item_ids"] for row in validation_plan["rows"]] == [
        ["p3-mixed-codex-skill-workflow-probe"],
        ["p2-skill-route-discovery-threejs"],
        ["p1-skill-route-discovery-compass"],
        ["p2-skill-route-discovery-zhengxi-views"],
    ]
    assert all(row["candidate_source_hashes"] for row in validation_plan["rows"])
    assert all(
        row["plan_basis"] == "route_profile_selected_item_ids_and_hashed_candidate_sources"
        for row in validation_plan["rows"]
    )
    assert all(
        row["required_validation"] == skill_route_discovery_preactivation_validation_commands()
        for row in validation_plan["rows"]
    )
    assert validation_plan["runtime_action_allowed"] is False
    assert validation_plan["external_skill_activation_allowed"] is False
    assert validation_plan["external_harness_execution_allowed"] is False
    assert validation_plan["provider_runtime_launch_allowed"] is False
    assert validation_plan["remote_execution_allowed"] is False
    assert validation_plan["raw_evidence_urls_exported"] is False
    assert validation_plan["raw_source_urls_exported"] is False
    assert validation_plan["raw_target_paths_exported"] is False
    assert completion["runtime_action_allowed"] is False
    assert completion["external_skill_activation_allowed"] is False
    assert completion["provider_runtime_launch_allowed"] is False
    assert completion["remote_execution_allowed"] is False
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized
    assert "https://github.com/omnigent-ai/omnigent" not in serialized


def test_skill_route_discovery_bounded_profile_lane_matrix_preserves_generic_profile():
    commands = skill_route_discovery_preactivation_validation_commands()
    input_payload = {
        "task_id": "fixture-skill-route-discovery-generic-profile-matrix",
        "capability_window": {
            "theme": "skill-route-discovery",
            "current_pass": 2,
            "total_passes": 4,
            "required_route_profiles": ["generic_skill_workflow"],
        },
        "source_kind": "candidates",
        "candidates": [
            {
                "name": "generic-agent-skill",
                "source_url": "https://github.com/example/generic-agent-skill",
                "evidence_summary": (
                    "Agent skill workflow with prompts, route metadata, validation notes, "
                    "and local documentation boundaries."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                "route_hints": ["skill_route_discovery"],
                "evidence_item_ids": ["generic-skill-workflow"],
                "evidence_urls": ["https://github.com/example/generic-agent-skill"],
            }
        ],
        "local_artifact_proofs": [
            {
                "proposal_kind": proposal_kind,
                "changed_files": ["tests/test_harness_eval.py"],
                "validation_commands": commands,
                "rollback_artifact": "artifacts/rollback/generic-profile-matrix.md",
                "review_note": "Generic profile matrix remains bounded to local validation lanes.",
            }
            for proposal_kind in ["documentation", "config", "test", "code_patch"]
        ],
    }

    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        input_payload,
        source_path=None,
    )
    matrix = output["bounded_profile_lane_matrix"]
    rows = {row["route_profile"]: row for row in matrix["rows"]}

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert matrix["status"] == "ready"
    assert matrix["required_route_profiles"] == ["generic_skill_workflow"]
    assert matrix["observed_route_profiles"] == ["generic_skill_workflow"]
    assert matrix["missing_route_profiles"] == []
    assert rows["generic_skill_workflow"]["present"] is True
    assert rows["generic_skill_workflow"]["available_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert rows["generic_skill_workflow"]["selected_local_lanes"] == ["test"]
    assert rows["generic_skill_workflow"]["lanes_bounded"] is True
    assert rows["generic_skill_workflow"]["runtime_action"] == "none"
    assert rows["generic_skill_workflow"]["external_skill_activation_allowed"] is False
    assert rows["generic_skill_workflow"]["provider_runtime_launch_allowed"] is False
    assert rows["generic_skill_workflow"]["raw_evidence_urls_exported"] is False
    assert matrix["runtime_action_allowed"] is False
    assert matrix["external_skill_activation_allowed"] is False


def test_skill_route_discovery_summary_signal_audit_bounds_compass_summary_intake():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_summary_compass_signal.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    audit = output["summary_signal_audit"]
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["source_kind"] == "summaries"
    assert output["registry"]["candidate_count"] == 1
    assert output["lane_map"]["proposal_lane_count"] == 4
    assert audit["controller_surface"] == "skill_route_discovery_summary_signal_audit"
    assert audit["status"] == "ready"
    assert audit["decision"] == "summary_signals_bound_to_local_lanes"
    assert audit["summary_count"] == 2
    assert audit["accepted_summary_count"] == 1
    assert audit["ignored_summary_count"] == 1
    assert audit["duplicate_summary_count"] == 0
    assert audit["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert audit["diagnostics"] == []
    assert audit["runtime_action_allowed"] is False
    assert audit["external_skill_activation_allowed"] is False
    assert audit["external_skill_code_allowed"] is False
    assert audit["external_harness_execution_allowed"] is False
    assert audit["provider_runtime_launch_allowed"] is False
    assert audit["remote_execution_allowed"] is False
    assert audit["raw_source_urls_exported"] is False
    assert audit["raw_upstream_body_exported"] is False

    assert audit["rows"] == [
        {
            "candidate_name_hash": stable_text_hash("compass-skills"),
            "candidate_source_hash": stable_text_hash("https://github.com/dongshuyan/compass-skills"),
            "proposal_kinds": ["documentation", "config", "test", "code_patch"],
            "route_profiles": ["skill_ecosystem_state_handoff"],
            "matched_route_terms": ["agent", "skill", "skills", "workflow"],
            "discovery_event_kind": "repository_updated",
            "discovery_event_effect": "record_only",
            "evidence_item_id_count": 0,
            "evidence_url_hashes": [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "raw_source_url_exported": False,
            "raw_upstream_body_exported": False,
            "diagnostics": [],
        }
    ]
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/omnigent-ai/omnigent" not in serialized
    assert "COMPASS Skills" not in serialized


def test_skill_route_discovery_provider_runtime_control_pass_requires_replay_sample():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass2_window.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["capability_window"]["theme"] = "provider-runtime-control"
    input_payload["capability_window"]["capability_slice"] = (
        "Turn provider and runtime configuration problems into body-free diagnostics, "
        "recovery hints, and locally replayable validation."
    )

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )
    completion = output["capability_window_completion"]
    sample_gate = completion["provider_runtime_sample_gate"]
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert completion["status"] == "blocked"
    assert completion["decision"] == "continue_or_replay_before_completion"
    assert "provider_runtime_preflight_sample_missing" in completion["diagnostics"]
    assert sample_gate == {
        "controller_surface": "provider_runtime_sample_gate",
        "status": "blocked",
        "decision": "provider_runtime_preflight_sample_required",
        "diagnostic": "provider_runtime_preflight_sample_missing",
        "next_action": "add_body_free_provider_runtime_preflight_sample_then_replay",
        "required": True,
        "provided": False,
        "ready_for_local_replay": False,
        "ready_for_supervisor_promotion": False,
        "degraded_replay_only": False,
        "success_claim_allowed": False,
        "success_status_label": "",
        "sample_failure_mode": "none",
        "sample_recovery_hint_count": 0,
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "body_free": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_provider_values_exported": False,
    }
    current_preflight = output["current_action_provider_runtime_preflight"]
    assert current_preflight["controller_surface"] == "current_action_provider_runtime_preflight"
    assert current_preflight["status"] == "blocked"
    assert current_preflight["decision"] == "provider_runtime_preflight_sample_required"
    assert current_preflight["next_action"] == "add_body_free_provider_runtime_preflight_sample_then_replay"
    assert current_preflight["theme"] == "provider-runtime-control"
    assert current_preflight["selected_local_lane"] == "test"
    assert current_preflight["provider_runtime_sample_provided"] is False
    assert current_preflight["provider_runtime_sample_route_status"] == "missing"
    assert current_preflight["provider_runtime_sample_ready_for_local_replay"] is False
    assert current_preflight["provider_runtime_sample_ready_for_supervisor_promotion"] is False
    assert current_preflight["success_claim_allowed"] is False
    assert current_preflight["recovery_hint_codes"] == ["provider_runtime_preflight_sample_missing"]
    assert current_preflight["diagnostics"] == ["provider_runtime_preflight_sample_missing"]
    recovery_packet = current_preflight["recovery_replay_packet"]
    assert recovery_packet["controller_surface"] == "provider_runtime_recovery_replay_packet"
    assert recovery_packet["status"] == "blocked"
    assert recovery_packet["decision"] == "repair_then_replay_provider_runtime_preflight"
    assert recovery_packet["provider_runtime_sample"]["provided"] is False
    assert recovery_packet["provider_runtime_sample"]["route_status"] == "missing"
    assert recovery_packet["recovery_steps"] == [
        {
            "code": "provider_runtime_preflight_sample_missing",
            "code_hash": stable_text_hash("provider_runtime_preflight_sample_missing"),
            "scope": "provider_runtime_control",
            "severity": "blocker",
            "replay_step": "add_body_free_sample",
            "value_recorded": False,
            "raw_provider_value_exported": False,
        }
    ]
    assert recovery_packet["provider_runtime_launch_allowed"] is False
    assert recovery_packet["raw_preflight_inputs_exported"] is False
    assert recovery_packet["raw_provider_values_exported"] is False
    assert current_preflight["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert current_preflight["body_free_diagnostics_only"] is True
    assert current_preflight["provider_runtime_launch_allowed"] is False
    assert current_preflight["remote_execution_allowed"] is False
    assert current_preflight["raw_preflight_inputs_exported"] is False
    assert current_preflight["raw_provider_values_exported"] is False
    readiness = output["validation_readiness_summary"]
    readiness_preflight = readiness["provider_runtime_preflight"]
    assert readiness["status"] == "blocked"
    assert readiness["decision"] == "resolve_provider_runtime_preflight_before_replay"
    assert readiness_preflight["status"] == "blocked"
    assert readiness_preflight["decision"] == "provider_runtime_preflight_sample_required"
    assert readiness_preflight["next_action"] == "add_body_free_provider_runtime_preflight_sample_then_replay"
    assert readiness_preflight["sample_provided"] is False
    assert readiness_preflight["sample_ready_for_local_replay"] is False
    assert readiness_preflight["success_claim_allowed"] is False
    assert readiness_preflight["recovery_hint_codes"] == ["provider_runtime_preflight_sample_missing"]
    assert readiness_preflight["diagnostics"] == ["provider_runtime_preflight_sample_missing"]
    assert readiness_preflight["recovery_replay_packet"] == recovery_packet
    assert readiness_preflight["body_free_diagnostics_only"] is True
    assert readiness_preflight["provider_runtime_launch_allowed"] is False
    assert readiness_preflight["raw_preflight_inputs_exported"] is False
    assert readiness_preflight["raw_provider_values_exported"] is False
    assert completion["completion_recovery"]["decision"] == "replay_provider_runtime_preflight"
    assert completion["completion_recovery"]["recovery_hint_codes"] == [
        "provider_runtime_preflight_sample_missing"
    ]
    final_diagnostics = completion["provider_runtime_final_diagnostics"]
    replay_workflow = final_diagnostics["operator_replay_workflow"]
    assert final_diagnostics["status"] == "blocked"
    assert final_diagnostics["decision"] == "repair_provider_runtime_sample_before_supervisor_replay"
    assert replay_workflow["controller_surface"] == "provider_runtime_operator_replay_workflow"
    assert replay_workflow["status"] == "blocked"
    assert replay_workflow["decision"] == "repair_provider_runtime_sample_before_supervisor_replay"
    assert replay_workflow["provider_runtime_theme"] is True
    assert replay_workflow["step_count"] == 4
    assert replay_workflow["ready_step_count"] == 1
    assert replay_workflow["blocked_step_count"] == 3
    assert replay_workflow["completion_blocker_count"] == 2
    assert replay_workflow["recovery_hint_codes"] == ["provider_runtime_preflight_sample_missing"]
    assert replay_workflow["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert replay_workflow["skill_route_validation_commands"] == (
        skill_route_discovery_preactivation_validation_commands()
    )
    assert replay_workflow["body_free_diagnostics_only"] is True
    assert replay_workflow["provider_runtime_launch_allowed"] is False
    assert replay_workflow["remote_execution_allowed"] is False
    assert replay_workflow["raw_preflight_inputs_exported"] is False
    assert replay_workflow["raw_provider_values_exported"] is False
    workflow_rows = {row["step"]: row for row in replay_workflow["steps"]}
    assert workflow_rows["provider_runtime_sample_gate"]["status"] == "blocked"
    assert workflow_rows["provider_runtime_sample_gate"]["ready"] is False
    assert workflow_rows["provider_runtime_recovery_summary"]["status"] == "missing"
    assert workflow_rows["provider_runtime_recovery_summary"]["sample_provided"] is False
    assert workflow_rows["provider_runtime_recovery_summary"]["success_claim_allowed"] is False
    assert workflow_rows["provider_runtime_diagnostic_panel"]["status"] == "ready"
    assert workflow_rows["provider_runtime_diagnostic_panel"]["ready"] is True
    assert workflow_rows["completion_handoff"]["status"] == "blocked"
    assert "OPENAI_API_KEY" not in serialized
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized


def test_skill_route_discovery_provider_runtime_control_pass_continues_with_ready_sample():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass2_window.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["capability_window"]["theme"] = "provider-runtime-control"
    input_payload["provider_runtime_preflight_samples"] = [
        {
            "provider": {
                "name": "local-dry-run-provider",
                "harness": "local-dry-run-provider",
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
    ]

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )
    completion = output["capability_window_completion"]
    sample_gate = completion["provider_runtime_sample_gate"]
    current_preflight = output["current_action_provider_runtime_preflight"]

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["provider_runtime_replay_sample"]["route_status"] == "passed"
    assert sample_gate["required"] is True
    assert sample_gate["provided"] is True
    assert sample_gate["status"] == "ready"
    assert sample_gate["decision"] == "provider_runtime_preflight_sample_ready"
    assert sample_gate["provider_runtime_launch_allowed"] is False
    assert sample_gate["remote_execution_allowed"] is False
    assert current_preflight["status"] == "ready"
    assert current_preflight["decision"] == "provider_runtime_preflight_ready_for_current_action"
    assert current_preflight["next_action"] == "continue_selected_bounded_lane_after_provider_runtime_replay"
    assert current_preflight["theme"] == "provider-runtime-control"
    assert current_preflight["selected_local_lane"] == "test"
    assert current_preflight["provider_runtime_sample_provided"] is True
    assert current_preflight["provider_runtime_sample_route_status"] == "passed"
    assert current_preflight["provider_runtime_sample_ready_for_local_replay"] is True
    assert current_preflight["provider_runtime_sample_ready_for_supervisor_promotion"] is True
    assert current_preflight["success_claim_allowed"] is True
    assert current_preflight["recovery_hint_codes"] == []
    assert current_preflight["diagnostics"] == []
    assert current_preflight["recovery_replay_packet"]["status"] == "ready"
    assert current_preflight["recovery_replay_packet"]["decision"] == (
        "replay_commands_available_for_operator_handoff"
    )
    assert current_preflight["recovery_replay_packet"]["recovery_steps"] == []
    assert current_preflight["recovery_replay_packet"]["provider_runtime_sample"]["route_status"] == "passed"
    assert current_preflight["recovery_replay_packet"]["provider_runtime_launch_allowed"] is False
    assert current_preflight["body_free_diagnostics_only"] is True
    assert current_preflight["provider_runtime_launch_allowed"] is False
    assert current_preflight["remote_execution_allowed"] is False
    readiness = output["validation_readiness_summary"]
    readiness_preflight = readiness["provider_runtime_preflight"]
    assert readiness["status"] == "ready"
    assert readiness["decision"] == "operator_can_replay_selected_bounded_validation_lane"
    assert readiness_preflight["status"] == "ready"
    assert readiness_preflight["decision"] == "provider_runtime_preflight_ready_for_current_action"
    assert readiness_preflight["next_action"] == "continue_selected_bounded_lane_after_provider_runtime_replay"
    assert readiness_preflight["sample_provided"] is True
    assert readiness_preflight["sample_ready_for_local_replay"] is True
    assert readiness_preflight["sample_ready_for_supervisor_promotion"] is True
    assert readiness_preflight["success_claim_allowed"] is True
    assert readiness_preflight["recovery_hint_codes"] == []
    assert readiness_preflight["provider_runtime_launch_allowed"] is False
    assert readiness_preflight["raw_preflight_inputs_exported"] is False
    assert readiness_preflight["raw_provider_values_exported"] is False
    assert completion["status"] == "in_progress"
    assert completion["decision"] == "continue_capability_window_before_completion"
    assert completion["diagnostics"] == ["capability_window_not_at_final_pass"]


def test_skill_route_discovery_provider_runtime_control_pass4_surfaces_completion_handoff():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass4_closure.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["capability_window"]["theme"] = "provider-runtime-control"
    input_payload["capability_window"]["capability_slice"] = (
        "Turn provider and runtime configuration problems into body-free diagnostics, "
        "recovery hints, and locally replayable validation."
    )
    input_payload["provider_runtime_preflight_samples"] = [
        {
            "provider": {
                "name": "local-dry-run-provider",
                "harness": "local-dry-run-provider",
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
    ]

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)
    completion = output["capability_window_completion"]
    provider_handoff = completion["provider_runtime_completion_handoff"]
    final_diagnostics = completion["provider_runtime_final_diagnostics"]
    interpretation = completion["completion_report"]["provider_runtime_interpretation_panel"]

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert completion["status"] == "ready"
    assert completion["decision"] == "complete_slice_for_supervisor_handoff"
    assert completion["planned_window_complete"] is True
    assert provider_handoff["controller_surface"] == "provider_runtime_completion_handoff"
    assert provider_handoff["status"] == "ready"
    assert provider_handoff["decision"] == "provider_runtime_control_slice_ready_for_supervisor_handoff"
    assert provider_handoff["supervisor_next_action"] == (
        "handoff_provider_runtime_control_slice_to_supervisor"
    )
    assert provider_handoff["theme"] == "provider-runtime-control"
    assert provider_handoff["current_pass"] == 4
    assert provider_handoff["total_passes"] == 4
    assert provider_handoff["final_pass_observed"] is True
    assert provider_handoff["provider_runtime_sample_gate_status"] == "ready"
    assert provider_handoff["provider_runtime_sample_required"] is True
    assert provider_handoff["provider_runtime_sample_provided"] is True
    assert provider_handoff["provider_runtime_sample_route_status"] == "passed"
    assert provider_handoff["provider_runtime_sample_ready_for_local_replay"] is True
    assert provider_handoff["provider_runtime_sample_ready_for_supervisor_promotion"] is True
    assert provider_handoff["success_claim_allowed"] is True
    assert provider_handoff["activation_packet_ready"] is True
    assert provider_handoff["final_slice_closure_ready"] is True
    assert provider_handoff["completion_blocker_count"] == 0
    assert provider_handoff["recovery_hint_codes"] == []
    assert provider_handoff["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert completion["completion_handoff"]["provider_runtime_completion_handoff"] == provider_handoff
    assert provider_handoff["runtime_action_allowed"] is False
    assert provider_handoff["external_skill_activation_allowed"] is False
    assert provider_handoff["external_skill_code_allowed"] is False
    assert provider_handoff["provider_runtime_launch_allowed"] is False
    assert provider_handoff["remote_execution_allowed"] is False
    assert provider_handoff["raw_preflight_inputs_exported"] is False
    assert provider_handoff["raw_diagnostics_exported"] is False
    assert provider_handoff["raw_provider_values_exported"] is False
    assert final_diagnostics["controller_surface"] == "provider_runtime_final_diagnostics"
    assert final_diagnostics["status"] == "ready"
    assert final_diagnostics["decision"] == "provider_runtime_final_diagnostics_ready_for_supervisor_replay"
    assert final_diagnostics["supervisor_next_action"] == (
        "supervisor_replay_provider_runtime_preflight_then_promote"
    )
    assert final_diagnostics["theme"] == "provider-runtime-control"
    assert final_diagnostics["provider_runtime_theme"] is True
    assert final_diagnostics["provider_runtime_diagnostic_panel_status"] == "ready"
    assert final_diagnostics["provider_runtime_sample_gate_status"] == "ready"
    assert final_diagnostics["provider_runtime_completion_handoff_status"] == "ready"
    assert final_diagnostics["provider_runtime_sample_route_status"] == "passed"
    assert final_diagnostics["provider_runtime_sample_ready_for_local_replay"] is True
    assert final_diagnostics["provider_runtime_sample_ready_for_supervisor_promotion"] is True
    assert final_diagnostics["success_claim_allowed"] is True
    assert final_diagnostics["completion_blocker_count"] == 0
    assert final_diagnostics["recovery_hint_count"] == 0
    assert final_diagnostics["recovery_hint_codes"] == []
    assert final_diagnostics["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    replay_workflow = final_diagnostics["operator_replay_workflow"]
    assert replay_workflow["controller_surface"] == "provider_runtime_operator_replay_workflow"
    assert replay_workflow["status"] == "ready"
    assert replay_workflow["decision"] == "provider_runtime_final_diagnostics_ready_for_supervisor_replay"
    assert replay_workflow["supervisor_next_action"] == (
        "supervisor_replay_provider_runtime_preflight_then_promote"
    )
    assert replay_workflow["provider_runtime_theme"] is True
    assert replay_workflow["planned_window_complete"] is True
    assert replay_workflow["proposal_kind_count"] == 4
    assert replay_workflow["route_profile_count"] == 3
    assert replay_workflow["step_count"] == 4
    assert replay_workflow["ready_step_count"] == 4
    assert replay_workflow["blocked_step_count"] == 0
    assert replay_workflow["completion_blocker_count"] == 0
    assert replay_workflow["recovery_hint_count"] == 0
    assert replay_workflow["recovery_hint_codes"] == []
    assert replay_workflow["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert replay_workflow["skill_route_validation_commands"] == (
        skill_route_discovery_preactivation_validation_commands()
    )
    assert [row["step"] for row in replay_workflow["steps"]] == [
        "provider_runtime_sample_gate",
        "provider_runtime_recovery_summary",
        "provider_runtime_diagnostic_panel",
        "completion_handoff",
    ]
    assert all(row["ready"] is True for row in replay_workflow["steps"])
    assert replay_workflow["body_free_diagnostics_only"] is True
    assert replay_workflow["runtime_action_allowed"] is False
    assert replay_workflow["external_skill_activation_allowed"] is False
    assert replay_workflow["provider_runtime_launch_allowed"] is False
    assert replay_workflow["remote_execution_allowed"] is False
    assert replay_workflow["raw_preflight_inputs_exported"] is False
    assert replay_workflow["raw_diagnostics_exported"] is False
    assert replay_workflow["raw_provider_values_exported"] is False
    assert interpretation["controller_surface"] == "provider_runtime_interpretation_panel"
    assert interpretation["status"] == "ready"
    assert interpretation["decision"] == "interpret_provider_runtime_evidence_as_body_free_replay_gate"
    assert interpretation["supervisor_next_action"] == (
        "supervisor_replay_provider_runtime_preflight_then_bounded_lane_validation"
    )
    assert interpretation["provider_runtime_theme"] is True
    assert interpretation["diagnostic_panel_status"] == "ready"
    assert interpretation["sample_gate_status"] == "ready"
    assert interpretation["completion_handoff_status"] == "ready"
    assert interpretation["sample_route_status"] == "passed"
    assert interpretation["sample_ready_for_local_replay"] is True
    assert interpretation["sample_ready_for_supervisor_promotion"] is True
    assert interpretation["degraded_replay_only"] is False
    assert interpretation["success_claim_allowed"] is True
    assert interpretation["row_count"] == 3
    assert [row["signal"] for row in interpretation["rows"]] == [
        "skill_route_provider_runtime_wording",
        "provider_runtime_preflight_replay",
        "provider_runtime_recovery_summary",
    ]
    assert interpretation["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert interpretation["body_free_diagnostics_only"] is True
    assert interpretation["runtime_action_allowed"] is False
    assert interpretation["external_skill_activation_allowed"] is False
    assert interpretation["external_harness_execution_allowed"] is False
    assert interpretation["provider_runtime_launch_allowed"] is False
    assert interpretation["remote_execution_allowed"] is False
    assert interpretation["raw_evidence_urls_exported"] is False
    assert interpretation["raw_source_urls_exported"] is False
    assert interpretation["raw_preflight_inputs_exported"] is False
    assert interpretation["raw_diagnostics_exported"] is False
    assert interpretation["raw_provider_values_exported"] is False
    assert completion["completion_handoff"]["provider_runtime_final_diagnostics"] == final_diagnostics
    assert final_diagnostics["body_free_diagnostics_only"] is True
    assert final_diagnostics["runtime_action_allowed"] is False
    assert final_diagnostics["provider_runtime_launch_allowed"] is False
    assert final_diagnostics["remote_execution_allowed"] is False
    assert final_diagnostics["raw_preflight_inputs_exported"] is False
    assert final_diagnostics["raw_diagnostics_exported"] is False
    assert final_diagnostics["raw_provider_values_exported"] is False
    assert "OPENAI_API_KEY" not in serialized
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized


def test_skill_route_discovery_pass4_lane_map_exposes_local_lane_matrix():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass4_closure.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    matrix = output["lane_map"]["local_lane_matrix"]
    serialized = json.dumps(matrix, sort_keys=True)

    assert output["route_status"] == "passed"
    assert matrix["controller_surface"] == "skill_route_discovery_local_lane_matrix"
    assert matrix["status"] == "ready"
    assert matrix["row_count"] == 3
    assert matrix["observed_route_profiles"] == [
        "codex_workflow_gate",
        "skill_ecosystem_state_handoff",
        "game_frontend_workflow",
    ]
    assert matrix["observed_local_lanes"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert matrix["blocked_candidate_names"] == []
    assert matrix["runtime_action"] == "none"
    assert matrix["external_skill_activation_allowed"] is False
    assert matrix["external_harness_execution_allowed"] is False
    assert matrix["provider_runtime_launch_allowed"] is False
    assert matrix["remote_execution_allowed"] is False
    assert matrix["raw_source_url_exported"] is False
    assert matrix["raw_upstream_body_exported"] is False

    rows = {row["candidate_name"]: row for row in matrix["rows"]}
    assert rows["codex-fable5"]["selected_local_lane"] == "test"
    assert rows["codex-fable5"]["route_probe_decision"] == "skill_route_discovery_first"
    assert rows["codex-fable5"]["first_route_required"] is True
    assert rows["codex-fable5"]["first_route_confirmed"] is True
    assert rows["codex-fable5"]["validation_gates"] == [
        "skill_route_discovery_first_before_workflow_gate"
    ]
    assert rows["compass-skills"]["selected_local_lane"] == "config"
    assert rows["compass-skills"]["validation_gates"] == [
        "state_handoff_boundary_before_profile_or_memory_write"
    ]
    assert rows["threejs-game-skills"]["selected_local_lane"] == "test"
    assert rows["threejs-game-skills"]["validation_gates"] == [
        "local_frontend_validation_before_game_skill_activation"
    ]
    assert all(row["runtime_action"] == "none" for row in matrix["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in matrix["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in matrix["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in matrix["rows"])
    assert all(row["remote_execution_allowed"] is False for row in matrix["rows"])
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_completion_report_surfaces_local_lane_closure():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass4_closure.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output["capability_window_completion"]["completion_report"], sort_keys=True)
    closure = output["capability_window_completion"]["completion_report"]["local_lane_closure"]

    assert closure["controller_surface"] == "skill_route_discovery_completion_local_lane_closure"
    assert closure["status"] == "ready"
    assert closure["decision"] == "bounded_local_lanes_ready_for_supervisor_replay"
    assert closure["activation_packet_status"] == "ready"
    assert closure["operator_activation_lane_status"] == "ready"
    assert closure["lane_count"] == 4
    assert closure["ready_lane_count"] == 4
    assert closure["blocked_lane_count"] == 0
    assert closure["selected_local_lanes"] == ["config", "test"]
    assert closure["proposal_kinds"] == ["code_patch", "config", "documentation", "test"]
    assert {row["proposal_kind"] for row in closure["rows"]} == {
        "code_patch",
        "config",
        "documentation",
        "test",
    }
    assert {
        row["proposal_kind"]
        for row in closure["rows"]
        if row["selected_for_profile_validation"]
    } == {"config", "test"}
    assert all(row["operator_lane_ready"] is True for row in closure["rows"])
    assert all(row["local_artifact_proof_ready"] is True for row in closure["rows"])
    assert all(row["activation_ready"] is True for row in closure["rows"])
    assert all(row["activation_blocker_count"] == 0 for row in closure["rows"])
    assert all(row["runtime_action"] == "none" for row in closure["rows"])
    assert closure["runtime_action_allowed"] is False
    assert closure["external_skill_activation_allowed"] is False
    assert closure["external_skill_code_allowed"] is False
    assert closure["external_harness_execution_allowed"] is False
    assert closure["provider_runtime_launch_allowed"] is False
    assert closure["remote_execution_allowed"] is False
    assert closure["raw_evidence_urls_exported"] is False
    assert closure["raw_source_urls_exported"] is False
    assert closure["raw_target_paths_exported"] is False
    assert closure["raw_upstream_body_exported"] is False
    handoff = output["capability_window_completion"]["completion_report"]["activation_handoff"]
    assert handoff["controller_surface"] == "skill_route_discovery_completion_activation_handoff"
    assert handoff["status"] == "ready"
    assert handoff["decision"] == "supervisor_may_replay_bounded_local_lanes_after_validation"
    assert handoff["supervisor_next_action"] == "external_supervisor_replay_bounded_local_lanes"
    assert handoff["planned_window_complete"] is True
    assert handoff["activation_packet_status"] == "ready"
    assert handoff["final_slice_closure_status"] == "ready"
    assert handoff["local_lane_closure_status"] == "ready"
    assert handoff["provider_runtime_completion_status"] == "not_applicable"
    assert handoff["selected_local_lanes"] == ["config", "test"]
    assert handoff["lane_count"] == 4
    assert handoff["ready_lane_count"] == 4
    assert handoff["blocked_lane_count"] == 0
    assert handoff["replay_step_count"] == 1
    assert len(handoff["replay_step_hashes"]) == 1
    assert handoff["completion_blocker_count"] == 0
    assert handoff["local_validation_required"] is True
    assert handoff["external_supervisor_required"] is True
    assert handoff["restart_required_by_kernel"] is False
    assert handoff["runtime_action_allowed"] is False
    assert handoff["external_skill_activation_allowed"] is False
    assert handoff["external_skill_code_allowed"] is False
    assert handoff["external_harness_execution_allowed"] is False
    assert handoff["provider_runtime_launch_allowed"] is False
    assert handoff["remote_execution_allowed"] is False
    assert handoff["raw_evidence_urls_exported"] is False
    assert handoff["raw_source_urls_exported"] is False
    assert handoff["raw_target_paths_exported"] is False
    assert handoff["raw_upstream_body_exported"] is False
    profile_gate = output["capability_window_completion"]["completion_report"]["profile_validation_gate"]
    assert profile_gate["controller_surface"] == "skill_route_discovery_completion_profile_validation_gate"
    assert profile_gate["status"] == "ready"
    assert profile_gate["decision"] == "profile_validation_gates_ready_for_completion_handoff"
    assert profile_gate["profile_count"] == 3
    assert profile_gate["ready_profile_count"] == 3
    assert profile_gate["blocked_profile_count"] == 0
    assert profile_gate["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    gate_rows = {row["route_profile"]: row for row in profile_gate["rows"]}
    assert gate_rows["codex_workflow_gate"]["local_gate"] == (
        "codex_workflow_gate_requires_skill_route_discovery_first"
    )
    assert gate_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert gate_rows["codex_workflow_gate"]["first_route_confirmed"] is True
    assert gate_rows["codex_workflow_gate"]["required_first_route_decision"] == "skill_route_discovery_first"
    assert gate_rows["game_frontend_workflow"]["local_gate"] == (
        "game_frontend_workflow_requires_local_test_or_frontend_validation"
    )
    assert gate_rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert gate_rows["skill_ecosystem_state_handoff"]["local_gate"] == (
        "state_handoff_requires_config_boundary_review"
    )
    assert gate_rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert all(row["metadata_complete"] is True for row in profile_gate["rows"])
    assert all(row["local_artifact_proof_ready"] is True for row in profile_gate["rows"])
    assert all(row["operator_lane_ready"] is True for row in profile_gate["rows"])
    assert all(row["diagnostics"] == [] for row in profile_gate["rows"])
    assert profile_gate["runtime_action_allowed"] is False
    assert profile_gate["external_skill_activation_allowed"] is False
    assert profile_gate["provider_runtime_launch_allowed"] is False
    assert profile_gate["raw_evidence_urls_exported"] is False
    assert profile_gate["raw_source_urls_exported"] is False
    current_window_gate = output["capability_window_completion"]["completion_report"][
        "current_window_evidence_gate"
    ]
    assert current_window_gate["controller_surface"] == "skill_route_discovery_current_window_evidence_gate"
    assert current_window_gate["status"] == "ready"
    assert current_window_gate["decision"] == "current_window_evidence_ready_for_completion"
    assert current_window_gate["planned_window_complete"] is True
    assert current_window_gate["enforced"] is True
    assert current_window_gate["required_route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert current_window_gate["observed_route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert current_window_gate["missing_route_profiles"] == []
    assert current_window_gate["selected_evidence_ref_count"] == 3
    assert current_window_gate["evidence_url_hash_count"] == 3
    assert current_window_gate["evidence_url_hashes"] == sorted(
        [
            stable_text_hash("https://github.com/baskduf/FableCodex"),
            stable_text_hash("https://github.com/dongshuyan/compass-skills"),
            stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
        ]
    )
    assert current_window_gate["diagnostics"] == []
    assert current_window_gate["runtime_action_allowed"] is False
    assert current_window_gate["external_skill_activation_allowed"] is False
    assert current_window_gate["raw_evidence_urls_exported"] is False
    assert "https://github.com/" not in json.dumps(current_window_gate, sort_keys=True)
    audit = output["capability_window_completion"]["completion_report"]["completion_audit"]
    assert audit["controller_surface"] == "skill_route_discovery_completion_audit"
    assert audit["status"] == "ready"
    assert audit["decision"] == "completion_fingerprint_ready_for_replay_compare"
    assert audit["fingerprint"].startswith("sha256:")
    assert audit["basis_field_count"] == 18
    assert audit["lane_row_count"] == 4
    assert audit["selected_local_lanes"] == ["config", "test"]
    assert audit["proposal_kinds"] == ["code_patch", "config", "documentation", "test"]
    assert audit["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert audit["replay_step_hashes"] == handoff["replay_step_hashes"]
    assert audit["completion_blocker_hashes"] == []
    assert audit["runtime_action_allowed"] is False
    assert audit["external_skill_activation_allowed"] is False
    assert audit["external_skill_code_allowed"] is False
    assert audit["external_harness_execution_allowed"] is False
    assert audit["provider_runtime_launch_allowed"] is False
    assert audit["remote_execution_allowed"] is False
    assert audit["raw_evidence_urls_exported"] is False
    assert audit["raw_source_urls_exported"] is False
    assert audit["raw_target_paths_exported"] is False
    assert audit["raw_upstream_body_exported"] is False
    checklist = output["capability_window_completion"]["completion_report"]["completion_replay_checklist"]
    assert checklist["controller_surface"] == "skill_route_discovery_completion_replay_checklist"
    assert checklist["status"] == "ready"
    assert checklist["decision"] == "final_replay_checklist_ready_for_supervisor"
    assert checklist["selected_local_lanes"] == ["config", "test"]
    assert checklist["step_count"] == 6
    assert checklist["ready_step_count"] == 6
    assert checklist["blocked_step_count"] == 0
    assert checklist["incomplete_step_hashes"] == []
    assert checklist["completion_blocker_count"] == 0
    assert checklist["completion_blocker_hashes"] == []
    assert checklist["recovery_hint_codes"] == ["no_recovery_required"]
    assert checklist["profile_lane_contract_status"] == "ready"
    assert checklist["profile_lane_contract_count"] == 3
    assert checklist["ready_profile_lane_contract_count"] == 3
    contract_rows = {row["route_profile"]: row for row in checklist["profile_lane_contracts"]}
    assert contract_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert contract_rows["codex_workflow_gate"]["required_first_route_decision"] == (
        "skill_route_discovery_first"
    )
    assert contract_rows["codex_workflow_gate"]["first_route_confirmed"] is True
    assert contract_rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert contract_rows["game_frontend_workflow"]["local_gate"] == (
        "game_frontend_workflow_requires_local_test_or_frontend_validation"
    )
    assert contract_rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert contract_rows["skill_ecosystem_state_handoff"]["local_gate"] == (
        "state_handoff_requires_config_boundary_review"
    )
    assert all(row["local_validation_required"] is True for row in checklist["profile_lane_contracts"])
    assert all(row["runtime_action"] == "none" for row in checklist["profile_lane_contracts"])
    assert all(row["external_skill_activation_allowed"] is False for row in checklist["profile_lane_contracts"])
    assert all(row["raw_evidence_urls_exported"] is False for row in checklist["profile_lane_contracts"])
    assert checklist["replay_commands"] == skill_route_discovery_preactivation_validation_commands()
    assert checklist["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert [step["step"] for step in checklist["steps"]] == [
        "profile_validation_gate",
        "local_lane_closure",
        "activation_packet",
        "provider_runtime_completion_handoff",
        "completion_audit",
        "supervisor_handoff",
    ]
    assert all(step["status"] in {"ready", "not_applicable"} for step in checklist["steps"])
    assert checklist["external_supervisor_required"] is True
    assert checklist["restart_required_by_kernel"] is False
    assert checklist["runtime_action_allowed"] is False
    assert checklist["external_skill_activation_allowed"] is False
    assert checklist["external_skill_code_allowed"] is False
    assert checklist["external_harness_execution_allowed"] is False
    assert checklist["provider_runtime_launch_allowed"] is False
    assert checklist["remote_execution_allowed"] is False
    assert checklist["raw_evidence_urls_exported"] is False
    assert checklist["raw_source_urls_exported"] is False
    assert checklist["raw_target_paths_exported"] is False
    assert checklist["raw_upstream_body_exported"] is False
    manifest = output["capability_window_completion"]["completion_report"]["final_route_handoff_manifest"]
    assert manifest["controller_surface"] == "skill_route_discovery_final_route_handoff_manifest"
    assert manifest["status"] == "ready"
    assert manifest["decision"] == "route_profile_handoff_ready_for_external_supervisor"
    assert manifest["profile_count"] == 3
    assert manifest["ready_profile_count"] == 3
    assert manifest["blocked_profile_count"] == 0
    assert manifest["selected_local_lanes"] == ["config", "test"]
    assert manifest["selected_local_lane_count"] == 2
    assert manifest["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert manifest["completion_blocker_count"] == 0
    assert manifest["activation_handoff_status"] == "ready"
    assert manifest["supervisor_next_action"] == "external_supervisor_replay_bounded_local_lanes"
    manifest_rows = {row["route_profile"]: row for row in manifest["rows"]}
    assert manifest_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert manifest_rows["codex_workflow_gate"]["operator_replay_step"] == (
        "replay_local_test_lane_for_workflow_or_game_route"
    )
    assert manifest_rows["codex_workflow_gate"]["required_first_route_decision"] == (
        "skill_route_discovery_first"
    )
    assert manifest_rows["codex_workflow_gate"]["first_route_confirmed"] is True
    assert manifest_rows["codex_workflow_gate"]["evidence_item_ids"] == [
        "p3-skill-workflow-first-fablecodex"
    ]
    assert manifest_rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert manifest_rows["game_frontend_workflow"]["operator_replay_step"] == (
        "replay_local_test_lane_for_workflow_or_game_route"
    )
    assert manifest_rows["game_frontend_workflow"]["evidence_item_ids"] == [
        "p2-skill-route-discovery-threejs-game"
    ]
    assert manifest_rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert manifest_rows["skill_ecosystem_state_handoff"]["operator_replay_step"] == (
        "review_local_config_lane_for_state_handoff"
    )
    assert manifest_rows["skill_ecosystem_state_handoff"]["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass"
    ]
    assert all(row["status"] == "ready" for row in manifest["rows"])
    assert all(row["closure_lane_ready"] is True for row in manifest["rows"])
    assert all(row["diagnostic_count"] == 0 for row in manifest["rows"])
    assert all(row["candidate_source_hashes"] for row in manifest["rows"])
    assert all(row["runtime_action"] == "none" for row in manifest["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in manifest["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in manifest["rows"])
    lane_queue = output["capability_window_completion"]["completion_report"]["route_validation_lane_queue"]
    serialized = json.dumps(lane_queue, sort_keys=True)
    assert lane_queue["controller_surface"] == "skill_route_discovery_route_validation_lane_queue"
    assert lane_queue["status"] == "ready"
    assert lane_queue["decision"] == "bounded_route_validation_lanes_ready_for_supervisor_replay"
    assert lane_queue["lane_count"] == 3
    assert lane_queue["ready_lane_count"] == 3
    assert lane_queue["blocked_lane_count"] == 0
    assert lane_queue["selected_local_lanes"] == ["config", "test"]
    assert lane_queue["activity_event_kinds"] == ["push", "unknown"]
    assert lane_queue["push_signal_count"] == 4
    assert lane_queue["push_event_freshness_signal"] is True
    assert lane_queue["push_event_authoritative"] is False
    assert lane_queue["activity_freshness"] == "push_movement_present_non_authoritative"
    assert lane_queue["completion_blocker_count"] == 0
    queue_rows = {row["route_profile"]: row for row in lane_queue["rows"]}
    assert queue_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert queue_rows["codex_workflow_gate"]["workflow_gate"] == {
        "controller_surface": "skill_route_discovery_queue_workflow_gate",
        "status": "ready",
        "decision": "skill_route_discovery_first_confirmed_before_workflow_gate",
        "required_first_route_decision": "skill_route_discovery_first",
        "first_route_confirmed": True,
        "primary_route": "skill_route_discovery",
        "secondary_workflow_action_allowed": False,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert queue_rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert queue_rows["game_frontend_workflow"]["workflow_gate"]["required_first_route_decision"] == ""
    assert queue_rows["game_frontend_workflow"]["workflow_gate"]["secondary_workflow_action_allowed"] is False
    assert queue_rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert all(row["runtime_action"] == "none" for row in lane_queue["rows"])
    assert all(row["local_validation_required"] is True for row in lane_queue["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in lane_queue["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in lane_queue["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in lane_queue["rows"])
    assert all(row["remote_execution_allowed"] is False for row in lane_queue["rows"])
    assert all(row["push_event_authoritative"] is False for row in lane_queue["rows"])
    assert all(row["push_event_install_or_activation_allowed"] is False for row in lane_queue["rows"])
    assert "https://github.com/" not in serialized
    secondary_bridge = output["capability_window_completion"]["completion_report"]["secondary_harness_bridge"]
    serialized = json.dumps(secondary_bridge, sort_keys=True)
    assert secondary_bridge["controller_surface"] == "skill_route_discovery_secondary_harness_bridge"
    assert secondary_bridge["status"] == "ready"
    assert secondary_bridge["decision"] == "secondary_agent_harness_gated_after_skill_route_completion"
    assert secondary_bridge["bridge_scope"] == "skill_route_discovery_to_agent_harness_eval"
    assert secondary_bridge["row_count"] == 3
    assert secondary_bridge["ready_row_count"] == 3
    assert secondary_bridge["blocked_row_count"] == 0
    assert secondary_bridge["agent_harness_eval_required_count"] == 1
    assert secondary_bridge["agent_harness_eval_blocked_count"] == 1
    assert secondary_bridge["selected_local_lanes"] == ["config", "test"]
    assert secondary_bridge["required_validation"] == [
        "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
        "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
    ]
    bridge_rows = {row["route_profile"]: row for row in secondary_bridge["rows"]}
    assert bridge_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert bridge_rows["codex_workflow_gate"]["primary_route"] == "skill_route_discovery"
    assert bridge_rows["codex_workflow_gate"]["secondary_lane"] == (
        "agent_harness_eval_after_local_corroboration"
    )
    assert bridge_rows["codex_workflow_gate"]["secondary_lane_status"] == (
        "blocked_until_local_corroboration"
    )
    assert bridge_rows["codex_workflow_gate"]["agent_harness_eval_behavior"] == (
        "agent_harness_eval_lane"
    )
    assert bridge_rows["codex_workflow_gate"]["agent_harness_eval_required"] is True
    assert bridge_rows["codex_workflow_gate"]["activation_ready"] is False
    assert bridge_rows["codex_workflow_gate"]["activation_blockers"] == [
        "local_corroboration_required_before_agent_harness_eval"
    ]
    assert bridge_rows["game_frontend_workflow"]["secondary_lane_status"] == "not_applicable"
    assert bridge_rows["skill_ecosystem_state_handoff"]["secondary_lane_status"] == "not_applicable"
    assert all(row["runtime_action"] == "none" for row in secondary_bridge["rows"])
    assert all(row["local_eval_activation_allowed"] is False for row in secondary_bridge["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in secondary_bridge["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in secondary_bridge["rows"])
    assert secondary_bridge["runtime_action_allowed"] is False
    assert secondary_bridge["local_eval_activation_allowed"] is False
    assert secondary_bridge["external_harness_execution_allowed"] is False
    assert secondary_bridge["provider_runtime_launch_allowed"] is False
    assert secondary_bridge["remote_execution_allowed"] is False
    assert secondary_bridge["raw_source_urls_exported"] is False
    assert "https://github.com/" not in serialized
    consistency_guard = output["capability_window_completion"]["completion_report"]["completion_consistency_guard"]
    serialized = json.dumps(consistency_guard, sort_keys=True)
    assert consistency_guard["controller_surface"] == (
        "skill_route_discovery_completion_consistency_guard"
    )
    assert consistency_guard["status"] == "ready"
    assert consistency_guard["decision"] == "completion_surfaces_consistent_for_supervisor_handoff"
    assert consistency_guard["selected_local_lanes"] == ["config", "test"]
    assert consistency_guard["manifest_selected_local_lanes"] == ["config", "test"]
    assert consistency_guard["queue_selected_local_lanes"] == ["config", "test"]
    assert consistency_guard["checklist_selected_local_lanes"] == ["config", "test"]
    assert consistency_guard["panel_statuses"] == {
        "activation_handoff": "ready",
        "completion_replay_checklist": "ready",
        "final_route_handoff_manifest": "ready",
        "route_validation_lane_queue": "ready",
        "secondary_harness_bridge": "ready",
    }
    assert consistency_guard["ready_profile_count"] == consistency_guard["ready_lane_count"] == 3
    assert consistency_guard["blocked_profile_count"] == consistency_guard["blocked_lane_count"] == 0
    replay_contract = consistency_guard["replay_contract"]
    assert replay_contract["controller_surface"] == "skill_route_discovery_completion_replay_contract"
    assert replay_contract["status"] == "ready"
    assert replay_contract["panels"] == [
        "activation_handoff",
        "completion_replay_checklist",
        "final_route_handoff_manifest",
        "route_validation_lane_queue",
        "secondary_harness_bridge",
    ]
    assert replay_contract["skill_route_validation_command_hashes"] == [
        stable_text_hash(command)
        for command in skill_route_discovery_preactivation_validation_commands()
    ]
    assert replay_contract["secondary_bridge_validation_command_hashes"] == [
        stable_text_hash("pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane"),
        stable_text_hash("pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"),
    ]
    assert set(replay_contract["panel_command_hashes"]) == set(replay_contract["panels"])
    assert replay_contract["raw_commands_exported"] is False
    assert replay_contract["runtime_action_allowed"] is False
    assert replay_contract["external_harness_execution_allowed"] is False
    assert consistency_guard["completion_blocker_count"] == 0
    assert consistency_guard["diagnostic_count"] == 0
    assert consistency_guard["diagnostic_hashes"] == []
    assert consistency_guard["external_supervisor_required"] is True
    assert consistency_guard["restart_required_by_kernel"] is False
    assert consistency_guard["runtime_action_allowed"] is False
    assert consistency_guard["external_skill_activation_allowed"] is False
    assert consistency_guard["external_harness_execution_allowed"] is False
    assert consistency_guard["provider_runtime_launch_allowed"] is False
    assert consistency_guard["remote_execution_allowed"] is False
    assert consistency_guard["raw_evidence_urls_exported"] is False
    assert consistency_guard["raw_source_urls_exported"] is False
    assert consistency_guard["raw_target_paths_exported"] is False
    assert consistency_guard["raw_upstream_body_exported"] is False
    assert "https://github.com/" not in serialized
    assert all(row["raw_evidence_urls_exported"] is False for row in manifest["rows"])
    assert manifest["runtime_action_allowed"] is False
    assert manifest["external_skill_activation_allowed"] is False
    assert manifest["external_harness_execution_allowed"] is False
    assert manifest["provider_runtime_launch_allowed"] is False
    assert manifest["remote_execution_allowed"] is False
    assert manifest["raw_evidence_urls_exported"] is False
    assert manifest["raw_source_urls_exported"] is False
    assert manifest["raw_target_paths_exported"] is False
    assert manifest["raw_upstream_body_exported"] is False
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized


def test_skill_route_discovery_completion_guard_blocks_missing_replay_contract():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass4_closure.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    report = output["capability_window_completion"]["completion_report"]
    queue_without_replay = json.loads(json.dumps(report["route_validation_lane_queue"]))
    queue_without_replay["required_validation"] = []

    guard = skill_route_discovery_completion_consistency_guard(
        ready=True,
        selected_local_lanes=report["selected_local_lanes"],
        activation_handoff=report["activation_handoff"],
        completion_replay_checklist=report["completion_replay_checklist"],
        final_route_handoff_manifest=report["final_route_handoff_manifest"],
        route_validation_lane_queue=queue_without_replay,
        secondary_harness_bridge=report["secondary_harness_bridge"],
        blocked_reasons=[],
    )

    assert guard["status"] == "blocked"
    assert guard["replay_contract"]["status"] == "blocked"
    assert guard["diagnostic_count"] == 1
    assert stable_text_hash("route_validation_lane_queue_missing_replay_commands") in guard[
        "diagnostic_hashes"
    ]
    assert guard["replay_contract"]["raw_commands_exported"] is False
    assert guard["runtime_action_allowed"] is False
    assert guard["external_harness_execution_allowed"] is False


def test_skill_route_discovery_provider_runtime_control_pass_surfaces_degraded_recovery_packet():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_provider_runtime_degraded_sample.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)
    current_preflight = output["current_action_provider_runtime_preflight"]
    recovery_packet = current_preflight["recovery_replay_packet"]
    readiness_preflight = output["validation_readiness_summary"]["provider_runtime_preflight"]

    assert current_preflight["status"] == "review"
    assert current_preflight["decision"] == "provider_runtime_degraded_replay_available_without_success_claim"
    assert current_preflight["next_action"] == "operator_review_degraded_provider_runtime_replay_before_promotion"
    assert current_preflight["provider_runtime_degraded_replay_only"] is True
    assert current_preflight["success_claim_allowed"] is False
    assert current_preflight["recovery_hint_codes"] == ["mock_auth_placeholder_used"]
    assert recovery_packet["status"] == "review"
    assert recovery_packet["decision"] == "review_degraded_replay_before_success_claim"
    assert recovery_packet["provider_runtime_sample"]["route_status"] == "degraded"
    assert recovery_packet["provider_runtime_sample"]["ready_for_local_replay"] is True
    assert recovery_packet["provider_runtime_sample"]["ready_for_supervisor_promotion"] is False
    assert recovery_packet["provider_runtime_sample"]["degraded_replay_only"] is True
    assert recovery_packet["provider_runtime_sample"]["success_claim_allowed"] is False
    assert recovery_packet["recovery_steps"] == [
        {
            "code": "mock_auth_placeholder_used",
            "code_hash": stable_text_hash("mock_auth_placeholder_used"),
            "scope": "provider_runtime_auth",
            "severity": "notice",
            "replay_step": "review_mock_auth_placeholder",
            "value_recorded": False,
            "raw_provider_value_exported": False,
        }
    ]
    assert recovery_packet["provider_runtime_launch_allowed"] is False
    assert recovery_packet["remote_execution_allowed"] is False
    assert recovery_packet["raw_preflight_inputs_exported"] is False
    assert recovery_packet["raw_provider_values_exported"] is False
    assert readiness_preflight["recovery_replay_packet"] == recovery_packet
    assert "OPENAI_API_KEY" not in serialized
    assert "https://github.com/baskduf/FableCodex" not in serialized


def test_skill_route_discovery_pass1_exposes_current_action_for_mixed_skill_routes():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass1_current_action.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    current_action = output["current_action"]
    handoff_packet = output["pass1_handoff_packet"]
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["capability_window_completion"]["status"] == "blocked"
    assert "capability_window_not_at_final_pass" in output["capability_window_completion"]["diagnostics"]
    assert output["validation_lane_plan"]["next_validation_target"]["selected_local_lane"] == "test"
    assert current_action["status"] == "ready"
    assert current_action["decision"] == "continue_selected_bounded_lane_next_pass"
    assert current_action["current_pass"] == 1
    assert current_action["next_pass"] == 2
    assert current_action["remaining_pass_count"] == 3
    assert current_action["selected_local_lane"] == "test"
    assert current_action["validation_scope"] == "local_test_lane_only"
    assert current_action["route_profiles"] == ["codex_workflow_gate", "game_frontend_workflow"]
    assert current_action["queued_local_lanes"] == ["documentation"]
    assert current_action["queued_validation_target_count"] == 1
    assert current_action["queued_validation_targets"][0]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert current_action["queued_validation_targets"][0]["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass"
    ]
    assert current_action["queued_validation_targets"][0]["runtime_action"] == "none"
    assert current_action["queued_validation_targets"][0]["external_skill_activation_allowed"] is False
    assert current_action["queued_validation_targets"][0]["raw_evidence_urls_exported"] is False
    assert current_action["evidence_item_ids"] == [
        "p2-skill-route-discovery-threejs",
        "p3-mixed-skill-workflow-routing",
    ]
    assert current_action["runtime_action"] == "none"
    assert current_action["external_skill_activation_allowed"] is False
    assert current_action["external_skill_code_allowed"] is False
    assert current_action["raw_evidence_urls_exported"] is False
    assert handoff_packet["controller_surface"] == "skill_route_discovery_pass1_handoff_packet"
    assert handoff_packet["status"] == "ready"
    assert handoff_packet["decision"] == (
        "continue_bounded_skill_route_lane_before_secondary_agent_harness_eval"
    )
    assert handoff_packet["current_pass"] == 1
    assert handoff_packet["next_pass"] == 2
    assert handoff_packet["selected_local_lane"] == "test"
    assert handoff_packet["queued_local_lanes"] == ["documentation"]
    assert handoff_packet["bounded_local_lanes"] == ["documentation", "test"]
    assert handoff_packet["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass",
        "p2-skill-route-discovery-threejs",
        "p3-mixed-skill-workflow-routing",
    ]
    assert handoff_packet["replay_commands"] == skill_route_discovery_preactivation_validation_commands()
    assert handoff_packet["adjacent_general_agent_project_eval"] == {
        "status": "gated",
        "agent_harness_eval_required": True,
        "skill_route_discovery_inherited": False,
        "allowed_local_lanes": ["documentation", "test", "code_patch"],
        "replay_commands": ["pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"],
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert handoff_packet["runtime_action_allowed"] is False
    assert handoff_packet["external_skill_activation_allowed"] is False
    assert handoff_packet["external_harness_execution_allowed"] is False
    assert handoff_packet["raw_evidence_urls_exported"] is False
    assert "codex" in output["term_route_review"]["rows"][0]["matched_route_terms"]
    assert output["term_route_review"]["runtime_action_allowed"] is False
    assert output["term_route_review"]["external_skill_activation_allowed"] is False
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized
    assert "https://github.com/omnigent-ai/omnigent" not in serialized


def test_skill_route_discovery_current_window_pass1_keeps_skill_probe_before_harness_eval():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_current_window_pass1.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    current_action = output["current_action"]
    handoff_packet = output["pass1_handoff_packet"]
    pass1_queue = output["pass1_validation_queue"]
    pass1_replay_plan = pass1_queue["pass1_replay_lane_plan"]
    mixed_probe = output["mixed_local_lane_probe"]
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["registry"]["candidate_count"] == 3
    assert output["source_lineage"]["related_source_count"] == 2
    assert output["source_lineage"]["fork_or_mirror_lineage_collapsed"] is True
    assert output["activation_gate"]["external_skill_activation_allowed"] is False
    assert current_action["status"] == "ready"
    assert current_action["selected_local_lane"] == "test"
    assert current_action["route_profiles"] == ["codex_workflow_gate", "game_frontend_workflow"]
    assert current_action["evidence_item_ids"] == [
        "p2-threejs-game-skill-docs",
        "p3-codex-workflow-gate-config",
    ]
    assert current_action["queued_validation_targets"][0]["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass"
    ]
    assert mixed_probe["primary_route"] == "skill_route_discovery"
    assert mixed_probe["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert mixed_probe["external_harness_execution_allowed"] is False
    assert handoff_packet["status"] == "ready"
    assert handoff_packet["evidence_ref_mode"] == "selected_item_ids_only"
    assert handoff_packet["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass",
        "p2-threejs-game-skill-docs",
        "p3-codex-workflow-gate-config",
    ]
    assert handoff_packet["external_skill_activation_allowed"] is False
    assert pass1_queue["controller_surface"] == "skill_route_discovery_pass1_validation_queue"
    assert pass1_queue["status"] == "ready"
    assert pass1_queue["decision"] == "pass1_skill_route_validation_queue_ready"
    assert pass1_queue["anchoring_proposal_count"] == 5
    assert pass1_queue["skill_route_row_count"] == 3
    assert pass1_queue["adjacent_general_agent_row_count"] == 2
    assert pass1_queue["ready_skill_route_row_count"] == 3
    assert pass1_queue["selected_local_lanes"] == ["documentation", "test"]
    assert pass1_queue["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert pass1_queue["profile_contract_status"] == "ready"
    assert pass1_queue["profile_contract_count"] == 3
    assert pass1_queue["ready_profile_contract_count"] == 3
    assert pass1_queue["profile_validation_lane_count"] == 3
    assert pass1_queue["ready_profile_validation_lane_count"] == 3
    assert pass1_queue["mixed_skill_workflow_secondary_lane_status"] == "blocked_until_local_corroboration"
    assert pass1_replay_plan["controller_surface"] == "skill_route_discovery_pass1_replay_lane_plan"
    assert pass1_replay_plan["status"] == "ready"
    assert pass1_replay_plan["decision"] == "replay_pass1_current_lane_then_queued_profile_lanes"
    assert pass1_replay_plan["replay_step_count"] == 2
    assert pass1_replay_plan["selected_current_pass_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
    ]
    assert pass1_replay_plan["queued_profiles"] == ["skill_ecosystem_state_handoff"]
    assert pass1_replay_plan["selected_local_lanes"] == ["documentation", "test"]
    assert pass1_replay_plan["evidence_ref_mode"] == "selected_item_ids_only"
    assert pass1_replay_plan["diagnostics"] == []
    queue_rows_by_id = {row["proposal_id"]: row for row in pass1_queue["rows"]}
    validation_lanes_by_profile = {
        row["route_profile"]: row for row in pass1_queue["profile_validation_lanes"]
    }
    replay_rows = pass1_replay_plan["rows"]
    assert replay_rows[0]["queue_role"] == "selected_current_pass_lane"
    assert replay_rows[0]["route_profiles"] == ["codex_workflow_gate", "game_frontend_workflow"]
    assert replay_rows[0]["selected_local_lane"] == "test"
    assert replay_rows[0]["validation_gates"] == [
        "local_frontend_validation_before_game_skill_activation",
        "skill_route_discovery_first_before_workflow_gate",
    ]
    assert replay_rows[0]["evidence_item_ids"] == [
        "p2-threejs-game-skill-docs",
        "p3-codex-workflow-gate-config",
    ]
    assert replay_rows[0]["first_route_required"] is True
    assert replay_rows[0]["first_route_confirmed"] is True
    assert replay_rows[1]["queue_role"] == "queued_bounded_lane"
    assert replay_rows[1]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert replay_rows[1]["selected_local_lane"] == "documentation"
    assert replay_rows[1]["validation_gates"] == [
        "state_handoff_boundary_before_profile_or_memory_write"
    ]
    assert replay_rows[1]["evidence_item_ids"] == ["p1-skill-route-discovery-compass"]
    assert validation_lanes_by_profile["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert validation_lanes_by_profile["skill_ecosystem_state_handoff"]["validation_gate"] == (
        "state_handoff_boundary_before_profile_or_memory_write"
    )
    assert validation_lanes_by_profile["skill_ecosystem_state_handoff"]["proposal_ids"] == [
        "p1-skill-route-discovery-compass"
    ]
    assert validation_lanes_by_profile["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert validation_lanes_by_profile["game_frontend_workflow"]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert validation_lanes_by_profile["game_frontend_workflow"]["proposal_ids"] == [
        "p2-threejs-game-skill-docs"
    ]
    assert validation_lanes_by_profile["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert validation_lanes_by_profile["codex_workflow_gate"]["first_route_required"] is True
    assert validation_lanes_by_profile["codex_workflow_gate"]["first_route_confirmed"] is True
    assert validation_lanes_by_profile["codex_workflow_gate"]["proposal_ids"] == [
        "p3-codex-workflow-gate-config"
    ]
    assert all(
        row["runtime_action"] == "none"
        and row["external_skill_activation_allowed"] is False
        and row["external_harness_execution_allowed"] is False
        and row["raw_source_urls_exported"] is False
        for row in pass1_queue["profile_validation_lanes"]
    )
    assert queue_rows_by_id["p1-skill-route-discovery-compass"]["selected_local_lane"] == "documentation"
    assert queue_rows_by_id["p1-skill-route-discovery-compass"]["profile_contracts"][0]["validation_gate"] == (
        "state_handoff_boundary_before_profile_or_memory_write"
    )
    assert queue_rows_by_id["p2-threejs-game-skill-docs"]["route_profiles"] == ["game_frontend_workflow"]
    assert queue_rows_by_id["p2-threejs-game-skill-docs"]["profile_contracts"][0]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert queue_rows_by_id["p2-threejs-game-skill-docs"]["profile_contracts"][0]["selected_first_local_lane"] == "test"
    assert queue_rows_by_id["p3-codex-workflow-gate-config"]["selected_local_lane"] == "test"
    assert queue_rows_by_id["p3-codex-workflow-gate-config"]["profile_contracts"][0]["acceptance_gates"][
        "first_route_confirmed"
    ] is True
    assert queue_rows_by_id["p4-general-agent-harness-eval"]["route"] == "agent_harness_eval_required"
    assert queue_rows_by_id["trend:omnigent-ai/omnigent"]["skill_route_discovery_inherited"] is False
    assert all(row["runtime_action"] == "none" for row in pass1_queue["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in pass1_queue["rows"])
    assert all(row["runtime_action"] == "none" for row in pass1_replay_plan["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in pass1_replay_plan["rows"])
    assert pass1_queue["runtime_action_allowed"] is False
    assert pass1_queue["external_skill_activation_allowed"] is False
    assert pass1_replay_plan["runtime_action_allowed"] is False
    assert pass1_replay_plan["external_skill_activation_allowed"] is False
    assert pass1_replay_plan["raw_source_urls_exported"] is False
    assert pass1_queue["raw_source_urls_exported"] is False
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_pass3_selects_bounded_lane_per_profile():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass3_selection.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    selection = output["preactivation_lane_selection"]
    validation_plan = output["validation_lane_plan"]
    validation_work_queue = output["validation_work_queue"]
    current_action = output["current_action"]
    profile_replay = output["profile_validation_replay"]
    replay_queue = output["pass_validation_replay_queue"]
    pass3_handoff = output["pass3_handoff_packet"]
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["route_profile_review"]["status"] == "ready"
    assert output["activation_manifest"]["status"] == "ready"
    assert selection["status"] == "ready"
    assert selection["decision"] == "select_bounded_local_lane_per_profile"
    assert selection["profile_count"] == 3
    assert selection["selected_lanes"] == [
        {"route_profile": "codex_workflow_gate", "selected_local_lane": "test"},
        {"route_profile": "game_frontend_workflow", "selected_local_lane": "test"},
        {"route_profile": "skill_ecosystem_state_handoff", "selected_local_lane": "config"},
    ]
    assert [row["selection_status"] for row in selection["rows"]] == ["ready", "ready", "ready"]
    assert all(row["runtime_action"] == "none" for row in selection["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in selection["rows"])
    assert validation_plan["lane_validation_targets"] == [
        {
            "selected_local_lane": "config",
            "validation_scope": "local_config_lane_only",
            "route_profiles": ["skill_ecosystem_state_handoff"],
            "route_profile_count": 1,
            "evidence_item_ids": ["p1-skill-route-discovery-compass"],
            "evidence_item_id_count": 1,
            "candidate_source_hashes": [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
            "candidate_source_count": 1,
            "candidate_count": 1,
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "provider_runtime_replay_commands": [
                "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
            ],
            "plan_basis": "selected_lane_grouped_route_profiles_and_hashed_candidate_sources",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_evidence_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_source_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        },
        {
            "selected_local_lane": "test",
            "validation_scope": "local_test_lane_only",
            "route_profiles": ["codex_workflow_gate", "game_frontend_workflow"],
            "route_profile_count": 2,
            "evidence_item_ids": [
                "p2-skill-route-discovery-threejs-game",
                "p3-skill-route-discovery-fablecodex",
            ],
            "evidence_item_id_count": 2,
            "candidate_source_hashes": [
                stable_text_hash("https://github.com/baskduf/FableCodex"),
                stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
            ],
            "candidate_source_count": 2,
            "candidate_count": 2,
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "provider_runtime_replay_commands": [
                "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
            ],
            "plan_basis": "selected_lane_grouped_route_profiles_and_hashed_candidate_sources",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_evidence_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_source_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        },
    ]
    assert validation_work_queue["controller_surface"] == "skill_route_discovery_validation_work_queue"
    assert validation_work_queue["status"] == "ready"
    assert validation_work_queue["decision"] == "bounded_validation_work_queue_ready_for_local_replay"
    assert validation_work_queue["validation_plan_status"] == "ready"
    assert validation_work_queue["candidate_intake_status"] == "ready"
    assert validation_work_queue["work_item_count"] == 3
    assert validation_work_queue["ready_work_item_count"] == 3
    assert validation_work_queue["blocked_work_item_count"] == 0
    assert validation_work_queue["selected_local_lanes"] == ["config", "test"]
    assert validation_work_queue["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert validation_work_queue["diagnostics"] == []
    assert validation_work_queue["runtime_action_allowed"] is False
    assert validation_work_queue["external_skill_activation_allowed"] is False
    assert validation_work_queue["external_harness_execution_allowed"] is False
    assert validation_work_queue["provider_runtime_launch_allowed"] is False
    assert validation_work_queue["raw_evidence_urls_exported"] is False
    assert validation_work_queue["raw_source_urls_exported"] is False
    assert validation_work_queue["raw_target_paths_exported"] is False
    assert validation_work_queue["raw_upstream_body_exported"] is False

    work_rows_by_profile = {row["route_profile"]: row for row in validation_work_queue["rows"]}
    assert work_rows_by_profile["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert work_rows_by_profile["codex_workflow_gate"]["supervisor_replay_step"] == (
        "run_focused_local_test_lane_then_replay_skill_route_lane"
    )
    assert work_rows_by_profile["codex_workflow_gate"]["candidate_hashes"] == [
        stable_text_hash("codex-fable5")
    ]
    assert work_rows_by_profile["codex_workflow_gate"]["candidate_source_hashes"] == [
        stable_text_hash("https://github.com/baskduf/FableCodex")
    ]
    assert work_rows_by_profile["codex_workflow_gate"]["target_path_hashes"] == [
        stable_text_hash("tests/test_harness_eval.py"),
        stable_text_hash("tests/test_skill_routing.py"),
    ]
    assert work_rows_by_profile["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert work_rows_by_profile["game_frontend_workflow"]["candidate_hashes"] == [
        stable_text_hash("threejs-game-skills")
    ]
    assert work_rows_by_profile["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert work_rows_by_profile["skill_ecosystem_state_handoff"]["supervisor_replay_step"] == (
        "review_local_config_boundary_then_replay_skill_route_lane"
    )
    assert work_rows_by_profile["skill_ecosystem_state_handoff"]["target_path_hashes"] == [
        stable_text_hash("src/blackhole_agent/proposal_synthesis.py")
    ]
    assert [row["evidence_item_ids"] for row in validation_work_queue["rows"]] == [
        ["p3-skill-route-discovery-fablecodex"],
        ["p2-skill-route-discovery-threejs-game"],
        ["p1-skill-route-discovery-compass"],
    ]
    assert all(row["ready_for_local_replay"] is True for row in validation_work_queue["rows"])
    assert all(row["runtime_action"] == "none" for row in validation_work_queue["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in validation_work_queue["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in validation_work_queue["rows"])
    assert all(row["raw_source_urls_exported"] is False for row in validation_work_queue["rows"])
    assert all(row["raw_target_paths_exported"] is False for row in validation_work_queue["rows"])
    assert current_action == {
        "controller_surface": "skill_route_discovery_current_action",
        "status": "ready",
        "decision": "continue_selected_bounded_lane_next_pass",
        "supervisor_next_action": "continue_skill_route_discovery_window",
        "theme": "skill-route-discovery",
        "current_pass": 3,
        "next_pass": 4,
        "total_passes": 4,
        "remaining_pass_count": 1,
        "selected_local_lane": "test",
        "validation_scope": "local_test_lane_only",
        "route_profiles": ["codex_workflow_gate", "game_frontend_workflow"],
        "route_profile_count": 2,
        "evidence_ref_mode": "selected_item_ids_only",
        "evidence_item_ids": [
            "p2-skill-route-discovery-threejs-game",
            "p3-skill-route-discovery-fablecodex",
        ],
        "evidence_item_id_count": 2,
        "candidate_source_hashes": [
            stable_text_hash("https://github.com/baskduf/FableCodex"),
            stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
        ],
        "candidate_source_count": 2,
        "queued_validation_targets": [
            {
                "selected_local_lane": "config",
                "validation_scope": "local_config_lane_only",
                "route_profiles": ["skill_ecosystem_state_handoff"],
                "route_profile_count": 1,
                "evidence_item_ids": ["p1-skill-route-discovery-compass"],
                "evidence_item_id_count": 1,
                "candidate_source_hashes": [
                    stable_text_hash("https://github.com/dongshuyan/compass-skills")
                ],
                "candidate_source_count": 1,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        ],
        "queued_validation_target_count": 1,
        "queued_local_lanes": ["config"],
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "plan_basis": "validation_lane_plan_next_validation_target",
        "diagnostics": [],
        "local_validation_required": True,
        "body_free": True,
        "runtime_action": "none",
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    assert profile_replay["controller_surface"] == "skill_route_discovery_profile_validation_replay"
    assert profile_replay["status"] == "ready"
    assert profile_replay["decision"] == "replay_selected_profile_validation_lanes"
    assert profile_replay["profile_count"] == 3
    assert profile_replay["selected_local_lanes"] == ["config", "test"]
    assert [
        (row["route_profile"], row["selected_local_lane"], row["operator_replay_step"])
        for row in profile_replay["rows"]
    ] == [
        ("codex_workflow_gate", "test", "replay_local_test_lane_for_workflow_or_game_route"),
        ("game_frontend_workflow", "test", "replay_local_test_lane_for_workflow_or_game_route"),
        ("skill_ecosystem_state_handoff", "config", "review_local_config_lane_for_state_handoff"),
    ]
    assert [row["evidence_item_ids"] for row in profile_replay["rows"]] == [
        ["p3-skill-route-discovery-fablecodex"],
        ["p2-skill-route-discovery-threejs-game"],
        ["p1-skill-route-discovery-compass"],
    ]
    assert [row["candidate_source_hashes"] for row in profile_replay["rows"]] == [
        [stable_text_hash("https://github.com/baskduf/FableCodex")],
        [stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")],
        [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
    ]
    assert all(row["runtime_action"] == "none" for row in profile_replay["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in profile_replay["rows"])
    assert profile_replay["raw_evidence_urls_exported"] is False
    assert profile_replay["raw_source_urls_exported"] is False
    assert profile_replay["raw_upstream_body_exported"] is False
    assert replay_queue["controller_surface"] == "skill_route_discovery_pass_validation_replay_queue"
    assert replay_queue["status"] == "ready"
    assert replay_queue["decision"] == "replay_selected_pass_lane_then_queued_bounded_lanes"
    assert replay_queue["current_pass"] == 3
    assert replay_queue["next_pass"] == 4
    assert replay_queue["selected_local_lane"] == "test"
    assert replay_queue["queued_local_lanes"] == ["config"]
    assert replay_queue["queue_count"] == 2
    assert replay_queue["selected_queue_count"] == 1
    assert replay_queue["queued_queue_count"] == 1
    assert replay_queue["local_artifact_review_count"] == 2
    assert replay_queue["local_artifact_review_ready_count"] == 2
    assert set(replay_queue["target_path_hashes"]) == {
        stable_text_hash("src/blackhole_agent/proposal_synthesis.py"),
        stable_text_hash("tests/test_harness_eval.py"),
        stable_text_hash("tests/test_skill_routing.py"),
    }
    assert replay_queue["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert replay_queue["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass",
        "p2-skill-route-discovery-threejs-game",
        "p3-skill-route-discovery-fablecodex",
    ]
    assert replay_queue["rows"][0]["queue_role"] == "selected_current_pass_lane"
    assert replay_queue["rows"][0]["selected_local_lane"] == "test"
    assert replay_queue["rows"][0]["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
    ]
    assert replay_queue["rows"][0]["evidence_item_ids"] == [
        "p2-skill-route-discovery-threejs-game",
        "p3-skill-route-discovery-fablecodex",
    ]
    assert replay_queue["rows"][1]["queue_role"] == "queued_bounded_lane"
    assert replay_queue["rows"][1]["selected_local_lane"] == "config"
    assert replay_queue["rows"][1]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert replay_queue["rows"][1]["evidence_item_ids"] == ["p1-skill-route-discovery-compass"]
    assert [row["artifact_contract_kind"] for row in replay_queue["rows"]] == ["test", "config"]
    assert [row["target_path_count"] for row in replay_queue["rows"]] == [2, 1]
    assert all(row["local_artifact_review"]["status"] == "ready" for row in replay_queue["rows"])
    assert all(row["raw_target_paths_exported"] is False for row in replay_queue["rows"])
    expected_queue_fingerprints = [
        stable_json_hash(
            {
                "queue_position": 1,
                "queue_role": "selected_current_pass_lane",
                "selected_local_lane": "test",
                "validation_scope": "local_test_lane_only",
                "route_profiles": ["codex_workflow_gate", "game_frontend_workflow"],
                "evidence_item_ids": [
                    "p2-skill-route-discovery-threejs-game",
                    "p3-skill-route-discovery-fablecodex",
                ],
                "candidate_source_hashes": [
                    stable_text_hash("https://github.com/baskduf/FableCodex"),
                    stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
                ],
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
            }
        ),
        stable_json_hash(
            {
                "queue_position": 2,
                "queue_role": "queued_bounded_lane",
                "selected_local_lane": "config",
                "validation_scope": "local_config_lane_only",
                "route_profiles": ["skill_ecosystem_state_handoff"],
                "evidence_item_ids": ["p1-skill-route-discovery-compass"],
                "candidate_source_hashes": [
                    stable_text_hash("https://github.com/dongshuyan/compass-skills")
                ],
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
            }
        ),
    ]
    assert replay_queue["queue_fingerprints"] == expected_queue_fingerprints
    assert [row["queue_fingerprint"] for row in replay_queue["rows"]] == expected_queue_fingerprints
    assert {row["fingerprint_basis"] for row in replay_queue["rows"]} == {
        "queue_role_lane_profiles_evidence_hashes"
    }
    assert all(row["runtime_action"] == "none" for row in replay_queue["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in replay_queue["rows"])
    assert replay_queue["required_validation"] == skill_route_discovery_preactivation_validation_commands()
    assert replay_queue["raw_evidence_urls_exported"] is False
    assert replay_queue["raw_source_urls_exported"] is False
    assert replay_queue["raw_upstream_body_exported"] is False
    assert pass3_handoff["controller_surface"] == "skill_route_discovery_pass3_handoff_packet"
    assert pass3_handoff["status"] == "ready"
    assert pass3_handoff["decision"] == "continue_active_and_queued_bounded_lanes_to_final_pass"
    assert pass3_handoff["current_pass"] == 3
    assert pass3_handoff["next_pass"] == 4
    assert pass3_handoff["selected_local_lanes"] == ["test"]
    assert pass3_handoff["queued_local_lanes"] == ["config"]
    assert pass3_handoff["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert pass3_handoff["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass",
        "p2-skill-route-discovery-threejs-game",
        "p3-skill-route-discovery-fablecodex",
    ]
    assert pass3_handoff["candidate_source_hashes"] == sorted([
        stable_text_hash("https://github.com/baskduf/FableCodex"),
        stable_text_hash("https://github.com/dongshuyan/compass-skills"),
        stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
    ])
    assert pass3_handoff["queue_fingerprints"] == expected_queue_fingerprints
    assert pass3_handoff["mixed_skill_workflow_primary_route"] == "skill_route_discovery"
    assert pass3_handoff["secondary_lane"] == "agent_harness_eval_after_local_corroboration"
    assert pass3_handoff["secondary_lane_status"] == "blocked_until_local_corroboration"
    checklist = pass3_handoff["final_pass_replay_checklist"]
    assert checklist["controller_surface"] == "skill_route_discovery_pass3_final_pass_replay_checklist"
    assert checklist["status"] == "ready"
    assert checklist["decision"] == "ready_for_final_pass_replay"
    assert checklist["step_count"] == 4
    assert [step["step"] for step in checklist["steps"]] == [
        "replay_selected_current_pass_lane",
        "carry_queued_bounded_lanes",
        "preserve_secondary_harness_block",
        "verify_body_free_final_handoff",
    ]
    assert {step["status"] for step in checklist["steps"]} == {"ready"}
    assert checklist["steps"][0]["selected_local_lanes"] == ["test"]
    assert checklist["steps"][0]["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
    ]
    assert checklist["steps"][0]["evidence_item_id_count"] == 2
    assert checklist["steps"][1]["queued_local_lanes"] == ["config"]
    assert checklist["steps"][1]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert checklist["steps"][1]["evidence_item_id_count"] == 1
    assert checklist["steps"][2]["primary_route"] == "skill_route_discovery"
    assert checklist["steps"][2]["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert checklist["steps"][2]["secondary_harness_eval_allowed"] is False
    assert checklist["steps"][3]["raw_evidence_urls_exported"] is False
    assert checklist["steps"][3]["raw_source_urls_exported"] is False
    assert checklist["steps"][3]["raw_upstream_body_exported"] is False
    assert checklist["required_validation"] == skill_route_discovery_preactivation_validation_commands()
    assert checklist["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert checklist["runtime_action_allowed"] is False
    assert checklist["external_skill_activation_allowed"] is False
    assert checklist["external_harness_execution_allowed"] is False
    assert checklist["provider_runtime_launch_allowed"] is False
    assert checklist["raw_evidence_urls_exported"] is False
    assert checklist["raw_source_urls_exported"] is False
    assert checklist["raw_upstream_body_exported"] is False
    profile_gates = pass3_handoff["profile_activation_gates"]
    assert profile_gates["controller_surface"] == "skill_route_discovery_pass3_profile_activation_gates"
    assert profile_gates["status"] == "ready"
    assert profile_gates["decision"] == "profile_lanes_ready_for_final_pass_validation"
    assert profile_gates["profile_count"] == 3
    assert profile_gates["ready_profile_count"] == 3
    assert profile_gates["blocked_profile_count"] == 0
    assert profile_gates["acceptance_contract_status"] == "ready"
    assert profile_gates["acceptance_contract_ready"] is True
    assert profile_gates["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert profile_gates["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    gate_rows = {row["route_profile"]: row for row in profile_gates["rows"]}
    assert gate_rows["codex_workflow_gate"]["route_probe_decision"] == "skill_route_discovery_first"
    assert gate_rows["codex_workflow_gate"]["validation_gate"] == (
        "skill_route_discovery_first_before_workflow_gate"
    )
    assert gate_rows["codex_workflow_gate"]["selected_first_local_lane"] == "test"
    assert gate_rows["codex_workflow_gate"]["acceptance_contract_status"] == "ready"
    assert gate_rows["codex_workflow_gate"]["acceptance_contract_ready"] is True
    assert gate_rows["codex_workflow_gate"]["acceptance_gates"]["first_route_confirmed"] is True
    assert gate_rows["codex_workflow_gate"]["selected_local_lanes"] == ["test"]
    assert gate_rows["codex_workflow_gate"]["queue_roles"] == ["selected_current_pass_lane"]
    assert gate_rows["codex_workflow_gate"]["evidence_item_ids"] == [
        "p2-skill-route-discovery-threejs-game",
        "p3-skill-route-discovery-fablecodex",
    ]
    assert gate_rows["game_frontend_workflow"]["route_probe_decision"] == "skill_route_discovery"
    assert gate_rows["game_frontend_workflow"]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert gate_rows["game_frontend_workflow"]["selected_first_local_lane"] == "test"
    assert gate_rows["game_frontend_workflow"]["required_metadata"] == [
        "body_free_game_skill_summary",
        "local_frontend_validation_target",
        "asset_or_provider_boundary_note",
    ]
    assert gate_rows["game_frontend_workflow"]["selected_local_lanes"] == ["test"]
    assert gate_rows["skill_ecosystem_state_handoff"]["route_probe_decision"] == "skill_route_discovery"
    assert gate_rows["skill_ecosystem_state_handoff"]["validation_gate"] == (
        "state_handoff_boundary_before_profile_or_memory_write"
    )
    assert gate_rows["skill_ecosystem_state_handoff"]["selected_first_local_lane"] == "config"
    assert gate_rows["skill_ecosystem_state_handoff"]["required_metadata"] == [
        "state_retention_boundary",
        "privacy_boundary",
        "local_target_metadata_only",
    ]
    assert gate_rows["skill_ecosystem_state_handoff"]["selected_local_lanes"] == ["config"]
    assert gate_rows["skill_ecosystem_state_handoff"]["queue_roles"] == ["queued_bounded_lane"]
    assert gate_rows["skill_ecosystem_state_handoff"]["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass"
    ]
    assert all(row["activation_blockers"] == [] for row in profile_gates["rows"])
    assert all(row["local_validation_required"] is True for row in profile_gates["rows"])
    assert all(row["runtime_action_allowed"] is False for row in profile_gates["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in profile_gates["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in profile_gates["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in profile_gates["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in profile_gates["rows"])
    assert all(row["raw_source_urls_exported"] is False for row in profile_gates["rows"])
    assert all(row["raw_upstream_body_exported"] is False for row in profile_gates["rows"])
    assert profile_gates["runtime_action_allowed"] is False
    assert profile_gates["external_skill_activation_allowed"] is False
    assert profile_gates["external_harness_execution_allowed"] is False
    assert profile_gates["provider_runtime_launch_allowed"] is False
    assert profile_gates["raw_evidence_urls_exported"] is False
    assert profile_gates["raw_source_urls_exported"] is False
    assert profile_gates["raw_upstream_body_exported"] is False
    validation_proof = pass3_handoff["profile_validation_proof"]
    assert validation_proof["controller_surface"] == "skill_route_discovery_pass3_profile_validation_proof"
    assert validation_proof["status"] == "ready"
    assert validation_proof["decision"] == "profiles_have_bounded_local_validation_proof"
    assert validation_proof["validation_gate"] == "focused-evidence-review"
    assert validation_proof["profile_count"] == 3
    assert validation_proof["ready_profile_count"] == 3
    assert validation_proof["blocked_profile_count"] == 0
    assert validation_proof["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert validation_proof["local_artifact_proof_lanes"] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    proof_rows = {row["route_profile"]: row for row in validation_proof["rows"]}
    assert proof_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert proof_rows["codex_workflow_gate"]["validation_gate"] == (
        "skill_route_discovery_first_before_workflow_gate"
    )
    assert proof_rows["codex_workflow_gate"]["local_artifact_proof_present"] is True
    assert proof_rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert proof_rows["game_frontend_workflow"]["validation_gate"] == (
        "local_frontend_validation_before_game_skill_activation"
    )
    assert proof_rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert proof_rows["skill_ecosystem_state_handoff"]["validation_gate"] == (
        "state_handoff_boundary_before_profile_or_memory_write"
    )
    assert proof_rows["skill_ecosystem_state_handoff"]["evidence_item_ids"] == [
        "p1-skill-route-discovery-compass"
    ]
    assert all(row["status"] == "ready" for row in validation_proof["rows"])
    assert all(row["blockers"] == [] for row in validation_proof["rows"])
    assert all(row["local_artifact_proof_present"] is True for row in validation_proof["rows"])
    assert all(row["acceptance_contract_ready"] is True for row in validation_proof["rows"])
    assert all(row["runtime_action_allowed"] is False for row in validation_proof["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in validation_proof["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in validation_proof["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in validation_proof["rows"])
    assert validation_proof["runtime_action_allowed"] is False
    assert validation_proof["external_skill_activation_allowed"] is False
    assert validation_proof["external_harness_execution_allowed"] is False
    assert validation_proof["provider_runtime_launch_allowed"] is False
    assert validation_proof["raw_evidence_urls_exported"] is False
    assert validation_proof["raw_source_urls_exported"] is False
    assert validation_proof["raw_upstream_body_exported"] is False
    activation_summary = pass3_handoff["activation_proof_summary"]
    assert activation_summary["controller_surface"] == (
        "skill_route_discovery_pass3_activation_proof_summary"
    )
    assert activation_summary["status"] == "ready"
    assert activation_summary["decision"] == "operator_can_promote_after_focused_replay"
    assert activation_summary["validation_gate"] == "focused-evidence-review"
    assert activation_summary["profile_count"] == 3
    assert activation_summary["ready_profile_count"] == 3
    assert activation_summary["blocked_profile_count"] == 0
    assert activation_summary["blocked_profiles"] == []
    assert activation_summary["selected_local_lanes"] == ["config", "test"]
    assert activation_summary["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert activation_summary["required_validation_command_count"] == 3
    assert activation_summary["required_validation_command_hashes"] == sorted(
        stable_text_hash(command)
        for command in [
            "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
            "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
            "pytest tests/test_harness_eval.py -q -k proposal_interpretation",
        ]
    )
    assert activation_summary["local_artifact_proof_lanes"] == [
        "code_patch",
        "config",
        "documentation",
        "test",
    ]
    assert {
        row["route_profile"]: (
            row["status"],
            row["selected_local_lane"],
            row["blocker_count"],
            row["required_validation_count"],
            row["local_artifact_proof_present"],
            row["acceptance_contract_ready"],
        )
        for row in activation_summary["rows"]
    } == {
        "codex_workflow_gate": ("ready", "test", 0, 3, True, True),
        "game_frontend_workflow": ("ready", "test", 0, 3, True, True),
        "skill_ecosystem_state_handoff": ("ready", "config", 0, 3, True, True),
    }
    assert activation_summary["runtime_action_allowed"] is False
    assert activation_summary["external_skill_activation_allowed"] is False
    assert activation_summary["external_harness_execution_allowed"] is False
    assert activation_summary["provider_runtime_launch_allowed"] is False
    assert activation_summary["raw_evidence_urls_exported"] is False
    assert activation_summary["raw_source_urls_exported"] is False
    assert activation_summary["raw_target_paths_exported"] is False
    assert activation_summary["raw_upstream_body_exported"] is False
    runbook = pass3_handoff["promotion_runbook"]
    assert runbook["controller_surface"] == "skill_route_discovery_pass3_promotion_runbook"
    assert runbook["status"] == "ready"
    assert runbook["decision"] == "supervisor_can_replay_ordered_pass3_runbook"
    assert runbook["validation_gate"] == "focused-evidence-review"
    assert runbook["activation_proof_status"] == "ready"
    assert runbook["operator_checkpoint_status"] == "ready"
    assert runbook["profile_validation_proof_status"] == "ready"
    assert runbook["step_count"] == 2
    assert runbook["ready_step_count"] == 2
    assert runbook["blocked_step_count"] == 0
    assert runbook["selected_local_lanes"] == ["config", "test"]
    assert runbook["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert runbook["required_validation_command_hashes"] == sorted(
        stable_text_hash(command)
        for command in [
            "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
            "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
            "pytest tests/test_harness_eval.py -q -k proposal_interpretation",
        ]
    )
    assert runbook["blockers"] == []
    assert runbook["diagnostics"] == []
    assert [
        (
            row["step"],
            row["queue_role"],
            row["selected_local_lane"],
            row["route_profiles"],
            row["profile_validation_gates"],
            row["status"],
            row["queue_fingerprint"],
        )
        for row in runbook["rows"]
    ] == [
        (
            "replay_selected_current_pass_lane",
            "selected_current_pass_lane",
            "test",
            ["codex_workflow_gate", "game_frontend_workflow"],
            [
                "skill_route_discovery_first_before_workflow_gate",
                "local_frontend_validation_before_game_skill_activation",
            ],
            "ready",
            expected_queue_fingerprints[0],
        ),
        (
            "carry_queued_bounded_lane_to_final_pass",
            "queued_bounded_lane",
            "config",
            ["skill_ecosystem_state_handoff"],
            ["state_handoff_boundary_before_profile_or_memory_write"],
            "ready",
            expected_queue_fingerprints[1],
        ),
    ]
    assert all(row["required_validation_hashes"] == [
        stable_text_hash(command)
        for command in skill_route_discovery_preactivation_validation_commands()
    ] for row in runbook["rows"])
    assert all(row["runtime_action_allowed"] is False for row in runbook["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in runbook["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in runbook["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in runbook["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in runbook["rows"])
    assert runbook["runtime_action_allowed"] is False
    assert runbook["external_skill_activation_allowed"] is False
    assert runbook["external_harness_execution_allowed"] is False
    assert runbook["provider_runtime_launch_allowed"] is False
    assert runbook["raw_evidence_urls_exported"] is False
    assert runbook["raw_source_urls_exported"] is False
    assert runbook["raw_target_paths_exported"] is False
    assert runbook["raw_upstream_body_exported"] is False
    local_probe = pass3_handoff["local_validation_probe"]
    assert local_probe["controller_surface"] == "skill_route_discovery_pass3_local_validation_probe"
    assert local_probe["status"] == "ready"
    assert local_probe["decision"] == "local_validation_probe_ready_for_activation_review"
    assert local_probe["validation_gate"] == "focused-evidence-review"
    assert local_probe["profile_count"] == 3
    assert local_probe["ready_profile_count"] == 3
    assert local_probe["blocked_profile_count"] == 0
    assert local_probe["selected_local_lanes"] == ["config", "test"]
    assert local_probe["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert local_probe["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    probe_rows = {row["route_profile"]: row for row in local_probe["rows"]}
    assert {
        profile: (
            row["status"],
            row["selected_local_lane"],
            row["validation_gate"],
            row["route_probe_decision"],
            row["acceptance_contract_ready"],
            row["local_artifact_proof_present"],
            row["promotion_runbook_step_ready"],
        )
        for profile, row in probe_rows.items()
    } == {
        "codex_workflow_gate": (
            "ready",
            "test",
            "skill_route_discovery_first_before_workflow_gate",
            "skill_route_discovery_first",
            True,
            True,
            True,
        ),
        "game_frontend_workflow": (
            "ready",
            "test",
            "local_frontend_validation_before_game_skill_activation",
            "skill_route_discovery",
            True,
            True,
            True,
        ),
        "skill_ecosystem_state_handoff": (
            "ready",
            "config",
            "state_handoff_boundary_before_profile_or_memory_write",
            "skill_route_discovery",
            True,
            True,
            True,
        ),
    }
    assert probe_rows["codex_workflow_gate"]["candidate_source_hashes"] == [
        stable_text_hash("https://github.com/baskduf/FableCodex"),
        stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
    ]
    assert probe_rows["game_frontend_workflow"]["candidate_source_hashes"] == [
        stable_text_hash("https://github.com/baskduf/FableCodex"),
        stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills"),
    ]
    assert probe_rows["skill_ecosystem_state_handoff"]["candidate_source_hashes"] == [
        stable_text_hash("https://github.com/dongshuyan/compass-skills")
    ]
    assert probe_rows["codex_workflow_gate"]["queue_fingerprint"] == expected_queue_fingerprints[0]
    assert probe_rows["game_frontend_workflow"]["queue_fingerprint"] == expected_queue_fingerprints[0]
    assert probe_rows["skill_ecosystem_state_handoff"]["queue_fingerprint"] == expected_queue_fingerprints[1]
    assert all(row["blockers"] == [] for row in local_probe["rows"])
    assert all(row["runtime_action"] == "none" for row in local_probe["rows"])
    assert all(row["runtime_action_allowed"] is False for row in local_probe["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in local_probe["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in local_probe["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in local_probe["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in local_probe["rows"])
    assert all(row["raw_source_urls_exported"] is False for row in local_probe["rows"])
    assert all(row["raw_upstream_body_exported"] is False for row in local_probe["rows"])
    assert local_probe["diagnostics"] == []
    assert local_probe["runtime_action_allowed"] is False
    assert local_probe["external_skill_activation_allowed"] is False
    assert local_probe["external_harness_execution_allowed"] is False
    assert local_probe["provider_runtime_launch_allowed"] is False
    assert local_probe["raw_evidence_urls_exported"] is False
    assert local_probe["raw_source_urls_exported"] is False
    assert local_probe["raw_upstream_body_exported"] is False
    control_plane = pass3_handoff["runner_harness_control_plane"]
    assert control_plane["controller_surface"] == "skill_route_discovery_pass3_runner_harness_control_plane"
    assert control_plane["status"] == "ready"
    assert control_plane["decision"] == "pass3_runner_workflow_ready_for_supervisor_replay"
    assert control_plane["stage_order"] == ["intake", "midflight", "recovery", "replay", "report"]
    assert control_plane["stage_count"] == 5
    assert control_plane["ready_stage_count"] == 5
    assert control_plane["blocked_stage_count"] == 0
    assert control_plane["missing_stages"] == []
    assert [(stage["stage"], stage["status"], stage["artifact"]) for stage in control_plane["stages"]] == [
        ("intake", "ready", "pass_validation_replay_queue"),
        ("midflight", "ready", "current_action_and_operator_checkpoints"),
        ("recovery", "ready", "profile_validation_proof"),
        ("replay", "ready", "promotion_runbook"),
        ("report", "ready", "activation_proof_summary"),
    ]
    assert all(stage["operator_visible"] is True for stage in control_plane["stages"])
    assert all(stage["raw_artifact_paths_exported"] is False for stage in control_plane["stages"])
    assert control_plane["queue_count"] == 2
    assert control_plane["checkpoint_count"] == 2
    assert control_plane["profile_count"] == 3
    assert control_plane["runbook_step_count"] == 2
    assert control_plane["report_profile_count"] == 3
    assert control_plane["replay_command_hashes"] == sorted(
        stable_text_hash(command) for command in skill_route_discovery_preactivation_validation_commands()
    )
    assert control_plane["provider_runtime_replay_command_hashes"] == sorted(
        stable_text_hash(command)
        for command in [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ]
    )
    assert control_plane["diagnostics"] == []
    assert control_plane["runtime_action_allowed"] is False
    assert control_plane["external_skill_activation_allowed"] is False
    assert control_plane["external_harness_execution_allowed"] is False
    assert control_plane["provider_runtime_launch_allowed"] is False
    assert control_plane["remote_execution_allowed"] is False
    assert control_plane["raw_evidence_urls_exported"] is False
    assert control_plane["raw_source_urls_exported"] is False
    assert control_plane["raw_target_paths_exported"] is False
    assert control_plane["raw_upstream_body_exported"] is False
    assert control_plane["raw_artifact_paths_exported"] is False
    checkpoints = pass3_handoff["operator_checkpoint_list"]
    assert checkpoints["controller_surface"] == "skill_route_discovery_pass3_operator_checkpoint_list"
    assert checkpoints["status"] == "ready"
    assert checkpoints["decision"] == "operator_can_replay_pass3_checkpoints"
    assert checkpoints["checkpoint_count"] == 2
    assert checkpoints["selected_checkpoint_count"] == 1
    assert checkpoints["queued_checkpoint_count"] == 1
    assert checkpoints["evidence_ref_mode"] == "selected_item_ids_only"
    assert checkpoints["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert checkpoints["diagnostics"] == []
    assert checkpoints["runtime_action_allowed"] is False
    assert checkpoints["external_skill_activation_allowed"] is False
    assert checkpoints["external_harness_execution_allowed"] is False
    assert checkpoints["provider_runtime_launch_allowed"] is False
    assert checkpoints["raw_evidence_urls_exported"] is False
    assert checkpoints["raw_source_urls_exported"] is False
    assert checkpoints["raw_upstream_body_exported"] is False
    assert [
        (
            row["checkpoint"],
            row["queue_role"],
            row["selected_local_lane"],
            row["route_profiles"],
            row["evidence_item_id_count"],
            row["candidate_source_count"],
            row["queue_fingerprint"],
            row["status"],
        )
        for row in checkpoints["rows"]
    ] == [
        (
            "replay_selected_current_pass_lane",
            "selected_current_pass_lane",
            "test",
            ["codex_workflow_gate", "game_frontend_workflow"],
            2,
            2,
            expected_queue_fingerprints[0],
            "ready",
        ),
        (
            "carry_queued_bounded_lane_to_final_pass",
            "queued_bounded_lane",
            "config",
            ["skill_ecosystem_state_handoff"],
            1,
            1,
            expected_queue_fingerprints[1],
            "ready",
        ),
    ]
    assert all(row["blockers"] == [] for row in checkpoints["rows"])
    assert all(row["runtime_action_allowed"] is False for row in checkpoints["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in checkpoints["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in checkpoints["rows"])
    assert all(row["raw_evidence_urls_exported"] is False for row in checkpoints["rows"])
    assert all(row["raw_source_urls_exported"] is False for row in checkpoints["rows"])
    assert all(row["raw_upstream_body_exported"] is False for row in checkpoints["rows"])
    assert pass3_handoff["queue_count"] == 2
    assert pass3_handoff["rows"][0]["queue_role"] == "selected_current_pass_lane"
    assert pass3_handoff["rows"][0]["selected_local_lane"] == "test"
    assert pass3_handoff["rows"][0]["queue_fingerprint"] == expected_queue_fingerprints[0]
    assert pass3_handoff["rows"][1]["queue_role"] == "queued_bounded_lane"
    assert pass3_handoff["rows"][1]["selected_local_lane"] == "config"
    assert pass3_handoff["rows"][1]["queue_fingerprint"] == expected_queue_fingerprints[1]
    assert pass3_handoff["diagnostics"] == []
    assert pass3_handoff["runtime_action_allowed"] is False
    assert pass3_handoff["external_skill_activation_allowed"] is False
    assert pass3_handoff["external_harness_execution_allowed"] is False
    assert pass3_handoff["provider_runtime_launch_allowed"] is False
    assert pass3_handoff["raw_evidence_urls_exported"] is False
    assert pass3_handoff["raw_source_urls_exported"] is False
    assert pass3_handoff["raw_upstream_body_exported"] is False
    assert selection["runtime_action_allowed"] is False
    assert selection["external_skill_activation_allowed"] is False
    assert selection["provider_runtime_launch_allowed"] is False
    assert selection["remote_execution_allowed"] is False
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized
    assert "https://github.com/omnigent-ai/omnigent" not in serialized


def test_skill_route_discovery_pass3_blocks_when_profile_contract_is_not_ready():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass3_selection.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["state_handoff_boundary"]["privacy_boundary_documented"] = False

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )
    pass3_handoff = output["pass3_handoff_packet"]
    profile_gates = pass3_handoff["profile_activation_gates"]
    gate_rows = {row["route_profile"]: row for row in profile_gates["rows"]}

    assert pass3_handoff["status"] == "blocked"
    assert "profile_lane_acceptance_contract_not_ready" in pass3_handoff["diagnostics"]
    assert profile_gates["status"] == "blocked"
    assert profile_gates["acceptance_contract_status"] == "blocked"
    assert profile_gates["acceptance_contract_ready"] is False
    validation_proof = pass3_handoff["profile_validation_proof"]
    proof_rows = {row["route_profile"]: row for row in validation_proof["rows"]}
    activation_summary = pass3_handoff["activation_proof_summary"]
    summary_rows = {row["route_profile"]: row for row in activation_summary["rows"]}
    assert validation_proof["status"] == "blocked"
    assert validation_proof["validation_gate"] == "focused-evidence-review"
    assert "skill_ecosystem_state_handoff" in validation_proof["blocked_profiles"]
    assert activation_summary["status"] == "blocked"
    assert activation_summary["decision"] == "repair_profile_validation_proof_before_promotion"
    assert activation_summary["blocked_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert activation_summary["blocked_profile_count"] == 3
    assert activation_summary["ready_profile_count"] == 0
    assert summary_rows["codex_workflow_gate"]["blockers"] == [
        "profile_acceptance_contract_not_ready"
    ]
    assert summary_rows["game_frontend_workflow"]["blockers"] == [
        "profile_acceptance_contract_not_ready"
    ]
    assert summary_rows["skill_ecosystem_state_handoff"]["status"] == "blocked"
    assert "profile_acceptance_contract_not_ready" in summary_rows["skill_ecosystem_state_handoff"]["blockers"]
    assert summary_rows["skill_ecosystem_state_handoff"]["runtime_action_allowed"] is False
    assert summary_rows["skill_ecosystem_state_handoff"]["external_skill_activation_allowed"] is False
    assert activation_summary["runtime_action_allowed"] is False
    assert activation_summary["external_skill_activation_allowed"] is False
    assert activation_summary["provider_runtime_launch_allowed"] is False
    assert activation_summary["raw_evidence_urls_exported"] is False
    assert activation_summary["raw_source_urls_exported"] is False
    assert activation_summary["raw_target_paths_exported"] is False
    runbook = pass3_handoff["promotion_runbook"]
    assert runbook["status"] == "blocked"
    assert runbook["decision"] == "repair_pass3_promotion_runbook_before_final_pass"
    assert runbook["activation_proof_status"] == "blocked"
    assert runbook["operator_checkpoint_status"] == "blocked"
    assert runbook["profile_validation_proof_status"] == "blocked"
    assert runbook["ready_step_count"] == 0
    assert runbook["blocked_step_count"] == 1
    assert runbook["step_count"] == 1
    assert "profile_lane_acceptance_contract_not_ready" in runbook["blockers"]
    assert all(row["status"] == "blocked" for row in runbook["rows"])
    assert all(row["runtime_action_allowed"] is False for row in runbook["rows"])
    assert runbook["external_skill_activation_allowed"] is False
    assert runbook["provider_runtime_launch_allowed"] is False
    assert runbook["raw_evidence_urls_exported"] is False
    local_probe = pass3_handoff["local_validation_probe"]
    probe_rows = {row["route_profile"]: row for row in local_probe["rows"]}
    assert local_probe["status"] == "blocked"
    assert local_probe["decision"] == "repair_local_validation_probe_before_activation_review"
    assert local_probe["blocked_profile_count"] == 3
    assert local_probe["ready_profile_count"] == 0
    assert local_probe["blocked_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert "skill_ecosystem_state_handoff:acceptance_contract_not_ready" in local_probe["diagnostics"]
    assert probe_rows["skill_ecosystem_state_handoff"]["status"] == "blocked"
    assert "acceptance_contract_not_ready" in probe_rows["skill_ecosystem_state_handoff"]["blockers"]
    assert probe_rows["skill_ecosystem_state_handoff"]["runtime_action_allowed"] is False
    assert probe_rows["skill_ecosystem_state_handoff"]["external_skill_activation_allowed"] is False
    assert probe_rows["skill_ecosystem_state_handoff"]["provider_runtime_launch_allowed"] is False
    assert local_probe["runtime_action_allowed"] is False
    assert local_probe["external_skill_activation_allowed"] is False
    assert local_probe["provider_runtime_launch_allowed"] is False
    assert local_probe["raw_evidence_urls_exported"] is False
    control_plane = pass3_handoff["runner_harness_control_plane"]
    assert control_plane["status"] == "blocked"
    assert control_plane["decision"] == "repair_pass3_runner_workflow_before_replay"
    assert control_plane["stage_order"] == ["intake", "midflight", "recovery", "replay", "report"]
    assert control_plane["ready_stage_count"] == 0
    assert control_plane["blocked_stage_count"] == 5
    assert control_plane["missing_stages"] == ["intake", "midflight", "recovery", "replay", "report"]
    assert {
        stage["stage"]: stage["status"]
        for stage in control_plane["stages"]
    } == {
        "intake": "blocked",
        "midflight": "blocked",
        "recovery": "blocked",
        "replay": "blocked",
        "report": "blocked",
    }
    assert "profile_lane_acceptance_contract_not_ready" in control_plane["diagnostics"]
    assert control_plane["runtime_action_allowed"] is False
    assert control_plane["external_skill_activation_allowed"] is False
    assert control_plane["external_harness_execution_allowed"] is False
    assert control_plane["provider_runtime_launch_allowed"] is False
    assert control_plane["raw_evidence_urls_exported"] is False
    assert control_plane["raw_artifact_paths_exported"] is False
    assert proof_rows["skill_ecosystem_state_handoff"]["status"] == "blocked"
    assert "profile_acceptance_contract_not_ready" in proof_rows["skill_ecosystem_state_handoff"]["blockers"]
    assert proof_rows["skill_ecosystem_state_handoff"]["runtime_action_allowed"] is False
    assert proof_rows["skill_ecosystem_state_handoff"]["external_skill_activation_allowed"] is False
    assert proof_rows["skill_ecosystem_state_handoff"]["provider_runtime_launch_allowed"] is False
    assert gate_rows["skill_ecosystem_state_handoff"]["status"] == "blocked"
    assert gate_rows["skill_ecosystem_state_handoff"]["acceptance_contract_status"] == "blocked"
    assert "profile_lane_acceptance_contract_not_ready" in (
        gate_rows["skill_ecosystem_state_handoff"]["activation_blockers"]
    )
    assert gate_rows["skill_ecosystem_state_handoff"]["runtime_action_allowed"] is False
    assert gate_rows["skill_ecosystem_state_handoff"]["external_skill_activation_allowed"] is False
    assert gate_rows["skill_ecosystem_state_handoff"]["provider_runtime_launch_allowed"] is False


def test_skill_route_discovery_catalog_links_profiles_to_provider_runtime_replay():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass3_selection.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["capability_window"]["theme"] = "provider-runtime-control"
    input_payload["capability_window"]["capability_slice"] = (
        "Turn provider and runtime configuration problems into body-free diagnostics, "
        "recovery hints, and locally replayable validation."
    )
    input_payload["provider_runtime_preflight_samples"] = [
        {
            "provider": {
                "name": "local-dry-run-provider",
                "harness": "local-dry-run-provider",
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
    ]

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )
    catalog = output["route_discovery_catalog"]
    serialized = json.dumps(output, sort_keys=True)

    assert catalog["status"] == "ready"
    assert catalog["decision"] == "catalog_ready_for_bounded_local_replay"
    assert catalog["theme"] == "provider-runtime-control"
    assert catalog["provider_runtime_preflight_required"] is True
    assert catalog["provider_runtime_sample_gate"]["status"] == "ready"
    assert catalog["provider_runtime_replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    assert catalog["selected_lane_count"] == 3
    assert [
        (row["route_profile"], row["selected_local_lane"], row["provider_runtime_preflight_required"])
        for row in catalog["rows"]
    ] == [
        ("codex_workflow_gate", "test", True),
        ("game_frontend_workflow", "test", True),
        ("skill_ecosystem_state_handoff", "config", True),
    ]
    assert [row["allowed_local_lanes"] for row in catalog["rows"]] == [
        ["code_patch", "config", "documentation", "test"],
        ["code_patch", "config", "documentation", "test"],
        ["code_patch", "config", "documentation", "test"],
    ]
    assert [row["evidence_item_ids"] for row in catalog["rows"]] == [
        ["p3-skill-route-discovery-fablecodex"],
        ["p2-skill-route-discovery-threejs-game"],
        ["p1-skill-route-discovery-compass"],
    ]
    assert [row["candidate_source_hashes"] for row in catalog["rows"]] == [
        [stable_text_hash("https://github.com/baskduf/FableCodex")],
        [stable_text_hash("https://github.com/majidmanzarpour/threejs-game-skills")],
        [stable_text_hash("https://github.com/dongshuyan/compass-skills")],
    ]
    assert all(row["runtime_action"] == "none" for row in catalog["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in catalog["rows"])
    assert all(row["provider_runtime_launch_allowed"] is False for row in catalog["rows"])
    assert catalog["runtime_action_allowed"] is False
    assert catalog["external_skill_activation_allowed"] is False
    assert catalog["provider_runtime_launch_allowed"] is False
    assert catalog["remote_execution_allowed"] is False
    assert "OPENAI_API_KEY" not in serialized
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized


def test_skill_route_discovery_pass4_current_window_includes_source_cited_domain_research_lane():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass4_closure.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["capability_window"]["required_route_profiles"].append("source_cited_domain_research")
    input_payload["capability_window"]["anchoring_proposals"].append("p4-skill-route-discovery-zhengxi-views")
    input_payload["capability_window"]["evidence_urls"].append("https://github.com/lyra81604/zhengxi-views")
    input_payload["candidates"].append(
        {
            "name": "zhengxi-views",
            "source_url": "https://github.com/lyra81604/zhengxi-views",
            "evidence_summary": (
                "Source-cited domain research agent skill with public views, citation checks, "
                "investment research examples, advice disclaimers, and local validation notes."
            ),
            "candidate_lanes": ["documentation", "config", "test", "code_patch"],
            "evidence_item_ids": ["p4-skill-route-discovery-zhengxi-views"],
            "evidence_urls": ["https://github.com/lyra81604/zhengxi-views"],
        }
    )

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )

    completion_report = output["capability_window_completion"]["completion_report"]
    manifest = completion_report["final_route_handoff_manifest"]
    lane_queue = completion_report["route_validation_lane_queue"]
    secondary_bridge = completion_report["secondary_harness_bridge"]
    consistency_guard = completion_report["completion_consistency_guard"]

    assert output["route_status"] == "passed"
    assert completion_report["status"] == "ready"
    assert manifest["profile_count"] == 4
    assert manifest["ready_profile_count"] == 4
    assert manifest["selected_local_lanes"] == ["config", "test"]
    assert "source_cited_domain_research" in manifest["route_profiles"]

    manifest_rows = {row["route_profile"]: row for row in manifest["rows"]}
    source_row = manifest_rows["source_cited_domain_research"]
    assert source_row["selected_local_lane"] == "test"
    assert source_row["validation_scope"] == "local_test_lane_only"
    assert source_row["local_gate"] == (
        "source_cited_domain_research_requires_citation_and_advice_boundary_test"
    )
    assert source_row["evidence_item_ids"] == ["p4-skill-route-discovery-zhengxi-views"]
    assert source_row["runtime_action"] == "none"
    assert source_row["external_skill_activation_allowed"] is False
    assert source_row["provider_runtime_launch_allowed"] is False

    queue_rows = {row["route_profile"]: row for row in lane_queue["rows"]}
    assert lane_queue["lane_count"] == 4
    assert lane_queue["ready_lane_count"] == 4
    assert queue_rows["source_cited_domain_research"]["selected_local_lane"] == "test"
    assert queue_rows["source_cited_domain_research"]["workflow_gate"]["required_first_route_decision"] == ""
    assert queue_rows["source_cited_domain_research"]["external_harness_execution_allowed"] is False
    assert queue_rows["source_cited_domain_research"]["provider_runtime_launch_allowed"] is False

    bridge_rows = {row["route_profile"]: row for row in secondary_bridge["rows"]}
    assert secondary_bridge["row_count"] == 4
    assert secondary_bridge["agent_harness_eval_required_count"] == 1
    assert bridge_rows["source_cited_domain_research"]["secondary_lane_status"] == "not_applicable"
    assert bridge_rows["source_cited_domain_research"]["local_eval_activation_allowed"] is False
    assert consistency_guard["ready_profile_count"] == consistency_guard["ready_lane_count"] == 4
    assert consistency_guard["status"] == "ready"


def test_skill_route_discovery_pass4_exposes_runner_harness_control_plane():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass4_closure.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    completion_report = output["capability_window_completion"]["completion_report"]
    control_plane = completion_report["runner_harness_control_plane"]
    serialized = json.dumps(control_plane, sort_keys=True)

    assert control_plane["controller_surface"] == "skill_route_discovery_pass4_runner_harness_control_plane"
    assert control_plane["status"] == "ready"
    assert control_plane["decision"] == "pass4_runner_workflow_ready_for_supervisor_replay"
    assert control_plane["stage_order"] == ["intake", "midflight", "recovery", "replay", "report"]
    assert control_plane["stage_count"] == 5
    assert control_plane["ready_stage_count"] == 5
    assert control_plane["blocked_stage_count"] == 0
    assert control_plane["missing_stages"] == []
    assert [stage["status"] for stage in control_plane["stages"]] == ["ready"] * 5
    assert all(stage["operator_visible"] is True for stage in control_plane["stages"])
    assert all(stage["raw_artifact_paths_exported"] is False for stage in control_plane["stages"])

    assert control_plane["source_intake"]["required_route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert control_plane["source_intake"]["missing_route_profiles"] == []
    assert control_plane["source_intake"]["selected_evidence_ref_count"] == 3
    assert control_plane["source_intake"]["evidence_url_hash_count"] == 3
    assert control_plane["source_intake"]["raw_evidence_urls_exported"] is False

    assert control_plane["midflight_state"]["selected_local_lanes"] == ["config", "test"]
    assert control_plane["midflight_state"]["ready_lane_count"] == 3
    assert control_plane["midflight_state"]["blocked_lane_count"] == 0
    assert control_plane["midflight_state"]["push_event_freshness_signal"] is True
    assert control_plane["midflight_state"]["push_event_authoritative"] is False

    assert control_plane["recovery"]["recovery_hint_codes"] == ["no_recovery_required"]
    assert control_plane["recovery"]["external_supervisor_required"] is True
    assert control_plane["recovery"]["restart_required_by_kernel"] is False
    assert control_plane["recovery"]["raw_recovery_commands_exported"] is False

    assert len(control_plane["replay"]["replay_command_hashes"]) == 3
    assert len(control_plane["replay"]["provider_runtime_replay_command_hashes"]) == 2
    assert control_plane["replay"]["raw_replay_commands_exported"] is False
    assert control_plane["report"]["consistency_guard_status"] == "ready"
    assert control_plane["report"]["replay_contract_status"] == "ready"
    assert control_plane["report"]["diagnostic_count"] == 0
    assert control_plane["report"]["raw_report_body_exported"] is False
    assert control_plane["runtime_action_allowed"] is False
    assert control_plane["external_skill_activation_allowed"] is False
    assert control_plane["external_harness_execution_allowed"] is False
    assert control_plane["provider_runtime_launch_allowed"] is False
    assert control_plane["remote_execution_allowed"] is False
    assert control_plane["raw_evidence_urls_exported"] is False
    assert control_plane["raw_source_urls_exported"] is False
    assert control_plane["raw_upstream_body_exported"] is False
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_completion_blocks_missing_required_profiles():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_fablecodex.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    input_payload = json.loads(json.dumps(fixture["input"]))
    input_payload["capability_window"]["required_route_profiles"] = [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        input_payload,
        source_path=fixture_path,
    )
    completion = output["capability_window_completion"]
    check = completion["profile_completion_check"]

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert completion["status"] == "blocked"
    assert completion["decision"] == "continue_or_replay_before_completion"
    assert check["status"] == "blocked"
    assert check["decision"] == "replay_missing_route_profiles_before_completion"
    assert check["required_route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert check["observed_route_profiles"] == ["codex_workflow_gate"]
    assert check["missing_route_profiles"] == [
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert check["enforced"] is True
    assert (
        "required_route_profiles_missing:game_frontend_workflow,skill_ecosystem_state_handoff"
        in completion["diagnostics"]
    )
    assert completion["completion_handoff"]["profile_completion_check"] == check
    assert completion["runtime_action_allowed"] is False
    assert completion["external_skill_activation_allowed"] is False
    assert completion["raw_evidence_urls_exported"] is False


def test_skill_route_discovery_completion_accepts_required_profile_coverage():
    input_payload = {
        "task_id": "fixture-skill-route-discovery-profile-completion",
        "capability_window": {
            "theme": "skill-route-discovery",
            "current_pass": 4,
            "total_passes": 4,
            "required_route_profiles": [
                "codex_workflow_gate",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ],
        },
        "source_kind": "candidates",
        "candidates": [
            {
                "name": "codex-fable5",
                "source_url": "https://github.com/baskduf/FableCodex",
                "evidence_summary": (
                    "Codex skill workflow gate with review ledger, verification habit, "
                    "plugin routing docs, and test coverage notes."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                "evidence_item_ids": ["fablecodex-repo"],
            },
            {
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "evidence_summary": (
                    "Skill ecosystem with task clarification, repo-local local memory, handoff prompts, "
                    "collaboration profile, route metadata, validation evidence, and privacy boundary notes."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                "evidence_item_ids": ["compass-repo"],
            },
            {
                "name": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "evidence_summary": (
                    "Three.js browser game director skill bundle with QA validation, screenshot and canvas checks, "
                    "asset/provider boundary notes, credential safeguards, and generation limits."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                "evidence_item_ids": ["threejs-repo"],
            },
        ],
        "state_handoff_boundary": {
            "retention_policy_documented": True,
            "privacy_boundary_documented": True,
            "local_target_metadata_only": True,
            "upstream_presence_grants_write": False,
        },
        "local_artifact_proofs": [
            {
                "proposal_kind": "documentation",
                "changed_files": ["docs/skill-route-discovery.md"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T213351Z-skill-route-discovery-pass4.txt",
                "review_note": "Documented final profile completion coverage for skill-route discovery.",
            },
            {
                "proposal_kind": "config",
                "changed_files": ["src/blackhole_agent/proposal_synthesis.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T213351Z-skill-route-discovery-pass4.txt",
                "review_note": "Config lane remains bounded to local proposal mapping.",
            },
            {
                "proposal_kind": "test",
                "changed_files": ["tests/test_harness_eval.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T213351Z-skill-route-discovery-pass4.txt",
                "review_note": "Tests replay profile completion coverage.",
            },
            {
                "proposal_kind": "code_patch",
                "changed_files": ["src/blackhole_agent/harness_eval.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T213351Z-skill-route-discovery-pass4.txt",
                "review_note": "Harness completion code checks required route profiles.",
            },
        ],
    }

    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        input_payload,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_profile_completion_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)
    completion = output["capability_window_completion"]
    check = completion["profile_completion_check"]

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert completion["status"] == "ready"
    assert completion["decision"] == "complete_slice_for_supervisor_handoff"
    assert completion["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert check["status"] == "ready"
    assert check["required_route_profiles"] == completion["route_profiles"]
    assert check["observed_route_profiles"] == completion["route_profiles"]
    assert check["missing_route_profiles"] == []
    assert check["enforced"] is True
    assert completion["diagnostics"] == []
    assert completion["completion_handoff"]["profile_completion_check"] == check
    assert completion["completion_handoff"]["supervisor_next_action"] == (
        "handoff_completed_skill_route_slice_to_supervisor"
    )
    assert completion["activation_packet"]["status"] == "ready"
    assert completion["activation_packet"]["route_profiles"] == completion["route_profiles"]
    assert completion["completion_handoff"]["activation_packet"] == completion["activation_packet"]
    assert completion["activation_packet"]["selected_evidence_refs"] == [
        "compass-repo",
        "fablecodex-repo",
        "threejs-repo",
    ]
    operator_lane = completion["activation_packet"]["operator_activation_lane"]
    assert operator_lane["controller_surface"] == "skill_route_discovery_operator_activation_lane"
    assert operator_lane["status"] == "ready"
    assert operator_lane["decision"] == "operator_lane_ready_for_supervisor_replay"
    assert operator_lane["supervisor_next_action"] == "replay_validated_local_lanes_then_handoff"
    assert operator_lane["lane_count"] == 4
    assert operator_lane["ready_lane_count"] == 4
    assert operator_lane["blocked_lane_count"] == 0
    assert operator_lane["proposal_kinds"] == ["code_patch", "config", "documentation", "test"]
    assert operator_lane["route_profiles"] == completion["route_profiles"]
    assert operator_lane["diagnostic_count"] == 0
    assert operator_lane["runtime_action_allowed"] is False
    assert operator_lane["external_skill_activation_allowed"] is False
    assert operator_lane["external_skill_code_allowed"] is False
    assert operator_lane["provider_runtime_launch_allowed"] is False
    assert operator_lane["raw_evidence_urls_exported"] is False
    assert operator_lane["raw_source_urls_exported"] is False
    assert operator_lane["raw_target_paths_exported"] is False
    assert operator_lane["raw_upstream_body_exported"] is False
    assert all(row["operator_lane_ready"] is True for row in operator_lane["lanes"])
    assert all(row["runtime_action"] == "none" for row in operator_lane["lanes"])
    assert all(row["local_validation_required"] is True for row in operator_lane["lanes"])
    assert all(row["external_skill_activation_allowed"] is False for row in operator_lane["lanes"])
    assert {row["supervisor_replay_step"] for row in completion["activation_packet"]["rows"]} == {
        "review_and_replay_bounded_local_lane"
    }
    assert completion["runtime_action_allowed"] is False
    assert completion["external_skill_activation_allowed"] is False
    assert "https://github.com/baskduf/FableCodex" not in serialized
    assert "https://github.com/dongshuyan/compass-skills" not in serialized
    assert "https://github.com/majidmanzarpour/threejs-game-skills" not in serialized


def test_skill_route_discovery_completion_blocks_codex_profile_without_first_route_gate():
    input_payload = {
        "task_id": "fixture-skill-route-discovery-codex-profile-first-route-gate",
        "capability_window": {
            "theme": "skill-route-discovery",
            "current_pass": 4,
            "total_passes": 4,
            "required_route_profiles": [
                "codex_workflow_gate",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ],
        },
        "source_kind": "candidates",
        "candidates": [
            {
                "name": "codex-fable5",
                "source_url": "https://github.com/baskduf/FableCodex",
                "evidence_summary": (
                    "Codex workflow gate with review ledger, verification habit, "
                    "plugin routing docs, examples, tests, evals, replay, and local test target notes."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                "evidence_item_ids": ["fablecodex-repo"],
            },
            {
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "evidence_summary": (
                    "Skill ecosystem with task clarification, repo-local local memory, handoff prompts, "
                    "collaboration profile, route metadata, validation evidence, and privacy boundary notes."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                "evidence_item_ids": ["compass-repo"],
            },
            {
                "name": "threejs-game-skills",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "evidence_summary": (
                    "Three.js browser game director skill bundle with QA validation, screenshot and canvas checks, "
                    "asset/provider boundary notes, credential safeguards, and generation limits."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                "evidence_item_ids": ["threejs-repo"],
            },
        ],
        "state_handoff_boundary": {
            "retention_policy_documented": True,
            "privacy_boundary_documented": True,
            "local_target_metadata_only": True,
            "upstream_presence_grants_write": False,
        },
        "local_artifact_proofs": [
            {
                "proposal_kind": "documentation",
                "changed_files": ["docs/skill-route-discovery.md"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260621T093206Z-skill-route-pass4-validation-gate.md",
                "review_note": "Documentation lane records the first-route gate.",
            },
            {
                "proposal_kind": "config",
                "changed_files": ["src/blackhole_agent/proposal_synthesis.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260621T093206Z-skill-route-pass4-validation-gate.md",
                "review_note": "Config lane remains bounded to local proposal mapping.",
            },
            {
                "proposal_kind": "test",
                "changed_files": ["tests/test_harness_eval.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260621T093206Z-skill-route-pass4-validation-gate.md",
                "review_note": "Test lane validates first-route gate failure.",
            },
            {
                "proposal_kind": "code_patch",
                "changed_files": ["src/blackhole_agent/harness_eval.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260621T093206Z-skill-route-pass4-validation-gate.md",
                "review_note": "Harness code blocks Codex profile completion without first-route proof.",
            },
        ],
    }

    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        input_payload,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_codex_first_route_gate_inline.json",
    )
    completion = output["capability_window_completion"]
    profile_gate = completion["completion_report"]["profile_validation_gate"]

    assert output["route_status"] == "passed"
    assert completion["status"] == "blocked"
    assert completion["decision"] == "continue_or_replay_before_completion"
    assert "codex_workflow_gate:skill_route_discovery_first_not_confirmed" in completion["diagnostics"]
    assert completion["completion_report"]["status"] == "blocked"
    assert profile_gate["status"] == "blocked"
    assert profile_gate["blocked_profile_count"] == 1
    codex_gate = next(row for row in profile_gate["rows"] if row["route_profile"] == "codex_workflow_gate")
    assert codex_gate["selected_local_lane"] == "test"
    assert codex_gate["first_route_confirmed"] is False
    assert codex_gate["diagnostics"] == ["skill_route_discovery_first_not_confirmed"]
    lane_queue = completion["completion_report"]["route_validation_lane_queue"]
    queue_codex_gate = next(
        row for row in lane_queue["rows"] if row["route_profile"] == "codex_workflow_gate"
    )
    assert lane_queue["status"] == "blocked"
    assert queue_codex_gate["status"] == "blocked"
    assert queue_codex_gate["workflow_gate"]["status"] == "blocked"
    assert queue_codex_gate["workflow_gate"]["decision"] == (
        "repair_skill_route_discovery_first_before_workflow_gate"
    )
    assert queue_codex_gate["workflow_gate"]["required_first_route_decision"] == (
        "skill_route_discovery_first"
    )
    assert queue_codex_gate["workflow_gate"]["first_route_confirmed"] is False
    assert "codex_workflow_gate:skill_route_discovery_first_not_confirmed_before_workflow_gate" in (
        lane_queue["diagnostics"]
    )
    assert profile_gate["runtime_action_allowed"] is False
    assert profile_gate["external_skill_activation_allowed"] is False
    assert profile_gate["raw_evidence_urls_exported"] is False


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
    assert handoff["completion_recovery"]["status"] == "blocked"
    assert handoff["completion_recovery"]["decision"] == "repair_local_artifact_proof"
    assert handoff["completion_recovery"]["supervisor_next_action"] == (
        "repair_local_artifact_proof_before_supervisor_handoff"
    )
    assert handoff["completion_recovery"]["primary_recovery_lane"] == "test"
    assert handoff["completion_recovery"]["recovery_hint_codes"] == ["local_artifact_proof_not_ready"]
    assert handoff["completion_recovery"]["replay_commands"] == [
        "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane"
    ]
    assert handoff["completion_recovery"]["runtime_action_allowed"] is False
    assert handoff["completion_recovery"]["external_skill_activation_allowed"] is False
    assert handoff["completion_recovery"]["provider_runtime_launch_allowed"] is False
    assert handoff["completion_recovery"]["raw_target_paths_exported"] is False
    assert handoff["activation_packet"]["status"] == "blocked"
    assert handoff["activation_packet"]["decision"] == "hold_packet_for_repair_or_replay"
    operator_lane = handoff["activation_packet"]["operator_activation_lane"]
    assert operator_lane["status"] == "blocked"
    assert operator_lane["decision"] == "operator_lane_waiting_for_local_repair"
    assert operator_lane["supervisor_next_action"] == "repair_local_lane_proof_before_replay"
    assert operator_lane["lane_count"] == 4
    assert operator_lane["ready_lane_count"] == 0
    assert operator_lane["blocked_lane_count"] == 4
    assert operator_lane["diagnostic_count"] >= 1
    assert any(row["operator_lane_ready"] is False for row in operator_lane["lanes"])
    assert any(row["local_artifact_proof_ready"] is False for row in operator_lane["lanes"])
    assert operator_lane["runtime_action_allowed"] is False
    assert operator_lane["external_skill_activation_allowed"] is False
    assert operator_lane["external_skill_code_allowed"] is False
    assert operator_lane["provider_runtime_launch_allowed"] is False
    assert operator_lane["raw_evidence_urls_exported"] is False
    assert operator_lane["raw_source_urls_exported"] is False
    assert operator_lane["raw_target_paths_exported"] is False
    assert operator_lane["raw_upstream_body_exported"] is False
    assert any(
        row["supervisor_replay_step"] == "repair_bounded_local_lane_before_replay"
        for row in handoff["activation_packet"]["rows"]
    )
    assert completion["completion_recovery"] == handoff["completion_recovery"]
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
    assert output["validation_lane_gate"]["status"] == "blocked"
    assert output["validation_lane_gate"]["decision"] == "keep_runtime_action_none_until_local_validation_passes"
    assert output["validation_lane_gate"]["diagnostics"] == ["local_artifact_proof_not_ready"]
    assert output["validation_lane_gate"]["runtime_action_allowed"] is False
    assert output["validation_lane_gate"]["external_skill_activation_allowed"] is False
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


def test_skill_route_discovery_compass_state_handoff_preflight_requires_explicit_boundary():
    base_input = {
        "task_id": "fixture-skill-route-discovery-compass-state-handoff",
        "source_kind": "candidates",
        "candidates": [
            {
                "name": "compass-skills",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "evidence_summary": (
                    "Specific skill ecosystem with task clarification, repo-local task memory, "
                    "handoff prompts, local collaboration profile, privacy boundary notes, "
                    "route metadata, and validation evidence."
                ),
                "candidate_lanes": ["documentation", "config", "test", "code_patch"],
            }
        ],
        "local_artifact_proofs": [
            {
                "proposal_kind": "documentation",
                "changed_files": ["docs/skill-route-discovery.md"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T121207Z-skill-route-discovery-compass-pass4.txt",
                "review_note": "COMPASS state handoff documentation remains metadata-only.",
            },
            {
                "proposal_kind": "config",
                "changed_files": ["src/blackhole_agent/proposal_synthesis.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T121207Z-skill-route-discovery-compass-pass4.txt",
                "review_note": "COMPASS route config keeps upstream profile writes disabled.",
            },
            {
                "proposal_kind": "test",
                "changed_files": ["tests/test_harness_eval.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T121207Z-skill-route-discovery-compass-pass4.txt",
                "review_note": "COMPASS state handoff preflight has local regression coverage.",
            },
            {
                "proposal_kind": "code_patch",
                "changed_files": ["src/blackhole_agent/harness_eval.py"],
                "validation_commands": skill_route_discovery_preactivation_validation_commands(),
                "rollback_artifact": "artifacts/rollback/20260620T121207Z-skill-route-discovery-compass-pass4.txt",
                "review_note": "COMPASS state handoff preflight is local-only harness code.",
            },
        ],
    }

    missing_boundary = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        base_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_compass_state_handoff_inline.json",
    )
    missing_review = missing_boundary["route_profile_review"]
    missing_preflight = missing_review["rows"][0]["state_handoff_preflight"]

    assert missing_review["status"] == "review"
    assert missing_review["diagnostics"] == [
        "skill_ecosystem_state_handoff:state_handoff_preflight:retention_policy_not_documented",
        "skill_ecosystem_state_handoff:state_handoff_preflight:privacy_boundary_not_documented",
        "skill_ecosystem_state_handoff:state_handoff_preflight:local_target_metadata_only_not_confirmed",
    ]
    assert missing_preflight["status"] == "review"
    assert missing_preflight["state_metadata_present"] == {
        "state_retention_and_privacy_boundary": True,
        "local_memory_or_profile_target_if_any": True,
    }
    assert missing_preflight["state_write_allowed"] is False
    assert missing_preflight["profile_write_allowed"] is False
    assert missing_preflight["memory_write_allowed"] is False

    ready_input = json.loads(json.dumps(base_input))
    ready_input["state_handoff_boundary"] = {
        "retention_policy_documented": True,
        "privacy_boundary_documented": True,
        "local_target_metadata_only": True,
        "upstream_presence_grants_write": False,
    }
    ready = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        ready_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_compass_state_handoff_ready_inline.json",
    )
    ready_review = ready["route_profile_review"]
    ready_preflight = ready_review["rows"][0]["state_handoff_preflight"]
    serialized = json.dumps(ready, sort_keys=True)

    assert ready_review["status"] == "ready"
    assert ready_review["diagnostics"] == []
    assert ready_preflight["status"] == "ready"
    assert ready_preflight["decision"] == "state_profile_route_ready_for_local_review"
    assert ready_preflight["explicit_boundary"] == {
        "retention_policy_documented": True,
        "privacy_boundary_documented": True,
        "local_target_metadata_only": True,
        "upstream_presence_grants_write": False,
    }
    assert ready_preflight["runtime_action"] == "none"
    assert ready_preflight["external_skill_activation_allowed"] is False
    assert ready_preflight["raw_source_urls_exported"] is False
    assert ready_preflight["private_context_exported"] is False
    assert "https://github.com/dongshuyan/compass-skills" not in serialized


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
    assert output["provider_runtime_replay_sample"]["operator_recovery_plan"] == {
        "controller_surface": "skill_route_provider_runtime_recovery_plan",
        "decision": "blocked_recovery_required",
        "reason": "provider_runtime_recovery_required",
        "next_action": "resolve_recovery_steps_then_replay",
        "preflight_count": 1,
        "status_counts": {"passed": 0, "degraded": 0, "blocked": 1},
        "recovery_step_count": 1,
        "recovery_hint_codes": ["provider_env_missing"],
        "recovery_hint_code_hashes": [stable_text_hash("provider_env_missing")],
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "body_free_diagnostics_only": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_provider_values_exported": False,
    }
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
        "provider_runtime_replay_sample_present": True,
        "sample_operator_recovery_plan": {
            "controller_surface": "skill_route_provider_runtime_recovery_plan",
            "decision": "blocked_recovery_required",
            "reason": "provider_runtime_recovery_required",
            "next_action": "resolve_recovery_steps_then_replay",
            "preflight_count": 1,
            "status_counts": {"passed": 0, "degraded": 0, "blocked": 1},
            "recovery_step_count": 1,
            "recovery_hint_codes": ["provider_env_missing"],
            "recovery_hint_code_hashes": [stable_text_hash("provider_env_missing")],
            "replay_commands": [
                "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
                "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
            ],
            "local_validation_required": True,
            "body_free_diagnostics_only": True,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_preflight_inputs_exported": False,
            "raw_diagnostics_exported": False,
            "raw_provider_values_exported": False,
        },
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
    assert output["route_hint_lane_policy"] == {
        "controller_surface": "skill_route_discovery_route_hint_lane_policy",
        "status": "review",
        "decision": "review_rejected_route_hints_before_activation",
        "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
        "selected_local_lanes": ["documentation"],
        "lanes_bounded": True,
        "rejected_lane_count": 1,
        "rejected_lanes": ["runtime_execution"],
        "rejected_candidate_count": 0,
        "downgraded_candidate_count": 1,
        "rejected_reasons": ["unsupported_candidate_lanes_removed"],
        "review_required": True,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }
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
    handoff = output["control_plane"]["workflow_handoff"]
    assert handoff["controller_surface"] == "runner_harness_workflow_handoff"
    assert handoff["status"] == "ready"
    assert handoff["decision"] == "ready_for_report_handoff"
    assert handoff["stage_count"] == 5
    assert handoff["ready_stage_count"] == 5
    assert handoff["blocked_stage_count"] == 0
    assert [stage["stage"] for stage in handoff["ordered_stages"]] == [
        "intake",
        "midflight",
        "recovery",
        "replay",
        "report",
    ]
    assert handoff["midflight_state"]["state_transition_count"] == 6
    assert handoff["recovery"]["command_count"] == 2
    assert handoff["replay"]["replay_artifact_recorded"] is True
    assert handoff["report"]["report_artifact_recorded"] is True
    assert handoff["raw_recovery_commands_exported"] is False
    assert handoff["raw_artifact_paths_exported"] is False
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
    assert missing_handoff["control_plane"]["workflow_handoff"]["status"] == "blocked"
    assert missing_handoff["control_plane"]["workflow_handoff"]["blocked_stage_reasons"] == [
        {
            "stage": "recovery",
            "reason": "recovery_handoff_incomplete",
            "action": "record_rollback_ref_artifact_and_recovery_handoff",
        }
    ]
    assert "PRIVATE_RECOVERY_REF_DO_NOT_EXPORT" not in missing_serialized


def test_agent_workflow_route_validates_harness_owned_compaction_boundary():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_harness_owned_compaction.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["compaction"]["passed"] is True
    assert output["compaction"]["policy"] == {
        "owner_required": "harness",
        "runner_compaction_allowed": False,
        "persist_before_mirror_update_required": True,
        "resume_replay_required": True,
        "controller_metadata_required": True,
        "raw_summary_exported": False,
        "raw_context_exported": False,
        "raw_controller_metadata_exported": False,
    }
    assert output["control_plane"]["compaction_contract"]["required"] is True
    assert output["control_plane"]["compaction_contract"]["owner"] == "harness"
    assert output["control_plane"]["compaction_contract"]["persisted"] is True
    assert output["control_plane"]["compaction_contract"]["persist_status_checked"] is True
    assert output["control_plane"]["compaction_contract"]["mirror_update_after_persist"] is True
    assert output["control_plane"]["compaction_contract"]["resume_replay_ready"] is True
    assert output["control_plane"]["compaction_contract"]["controller_metadata"] == {
        "required": True,
        "provided": True,
        "passed": True,
        "failure_mode": "none",
        "field_count": 4,
        "required_fields": [
            "source_digest",
            "controller_branch",
            "controller_head",
            "rollback_ref",
            "recovery_commands",
        ],
        "missing_fields": [],
        "source_digest_hash": stable_text_hash("github-growth-20260624T153904.842598Z"),
        "controller_branch_hash": stable_text_hash("PRIVATE_CONTROLLER_BRANCH_DO_NOT_EXPORT"),
        "controller_head_hash": stable_text_hash("PRIVATE_CONTROLLER_HEAD_DO_NOT_EXPORT"),
        "rollback_ref_hash": stable_text_hash("PRIVATE_ROLLBACK_REF_DO_NOT_EXPORT"),
        "recovery_command_count": 2,
        "recovery_command_hashes": [
            stable_text_hash("PRIVATE_RECOVERY_COMMAND_1_DO_NOT_EXPORT"),
            stable_text_hash("PRIVATE_RECOVERY_COMMAND_2_DO_NOT_EXPORT"),
        ],
        "raw_metadata_exported": False,
        "raw_recovery_commands_exported": False,
    }
    assert output["control_plane"]["operator_replay_checklist"]["status"] == "ready"
    assert "PRIVATE_COMPACTION_SUMMARY_REF_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CONTROLLER_BRANCH_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CONTROLLER_HEAD_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_ROLLBACK_REF_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RECOVERY_COMMAND_1_DO_NOT_EXPORT" not in serialized
    assert "CompactionComplete" not in serialized

    runner_owned = dict(fixture["input"])
    runner_owned["compaction"] = dict(fixture["input"]["compaction"], owner="runner")
    runner_owned_gate = evaluate_harness_behavior(
        "agent_workflow_route",
        runner_owned,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_runner_owned_compaction_inline.json",
    )

    assert runner_owned_gate["route_status"] == "failed_recoverable"
    assert runner_owned_gate["failure_mode"] == "compaction_not_harness_owned"
    assert runner_owned_gate["control_plane"]["complete"] is False
    assert runner_owned_gate["control_plane"]["compaction_contract"]["blockers"] == [
        "compaction_not_harness_owned"
    ]
    assert runner_owned_gate["control_plane"]["operator_replay_checklist"]["status"] == "blocked"
    assert any(
        action["action"] == "compaction_not_harness_owned"
        for action in runner_owned_gate["control_plane"]["operator_replay_checklist"]["actions"]
    )

    split_brain_risk = dict(fixture["input"])
    split_brain_risk["compaction"] = dict(
        fixture["input"]["compaction"],
        persist_status_checked=False,
        mirror_update_after_persist=False,
    )
    split_brain_gate = evaluate_harness_behavior(
        "agent_workflow_route",
        split_brain_risk,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_compaction_split_brain_inline.json",
    )

    assert split_brain_gate["route_status"] == "failed_recoverable"
    assert split_brain_gate["failure_mode"] == "compaction_persist_status_unchecked"
    assert split_brain_gate["control_plane"]["compaction_contract"]["blockers"] == [
        "compaction_persist_status_unchecked",
        "compaction_mirror_updated_before_persist",
    ]
    assert split_brain_gate["control_plane"]["stage_diagnostics"][1]["reason"] == (
        "compaction_persist_status_unchecked"
    )

    missing_metadata = dict(fixture["input"])
    missing_metadata["compaction"] = dict(fixture["input"]["compaction"])
    missing_metadata["compaction"].pop("controller_metadata")
    missing_metadata_gate = evaluate_harness_behavior(
        "agent_workflow_route",
        missing_metadata,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_compaction_metadata_missing_inline.json",
    )

    assert missing_metadata_gate["route_status"] == "failed_recoverable"
    assert missing_metadata_gate["failure_mode"] == "compaction_controller_metadata_missing"
    assert missing_metadata_gate["control_plane"]["compaction_contract"]["controller_metadata"][
        "missing_fields"
    ] == [
        "source_digest",
        "controller_branch",
        "controller_head",
        "rollback_ref",
        "recovery_commands",
    ]
    assert missing_metadata_gate["control_plane"]["operator_replay_checklist"]["status"] == "blocked"


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


def test_provider_runtime_preflight_blocks_ambiguous_omnigent_auth_header_without_name_or_value_export():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_omnigent_auth_header_fallback.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    fallback = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    valid_custom = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-omnigent-auth-header-valid-custom",
            "provider": {
                "name": "omnigent-proxy",
                "harness": "omnigent",
                "auth_header_required": True,
                "auth_header_name": "X-Omnigent-User",
                "auth_header_env_name": "OMNIGENT_AUTH_HEADER",
                "default_auth_header_name": "X-Forwarded-Email",
                "accepted_auth_headers": ["X-Omnigent-User"],
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_auth_header_valid_custom_inline.json",
    )
    malformed = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-omnigent-auth-header-malformed",
            "provider": {
                "name": "omnigent-proxy",
                "harness": "omnigent",
                "auth_header_required": True,
                "auth_header_name": "X Bad Header",
                "auth_header_env_name": "OMNIGENT_AUTH_HEADER",
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_auth_header_malformed_inline.json",
    )
    serialized = json.dumps(
        {"fallback": fallback, "valid_custom": valid_custom, "malformed": malformed},
        sort_keys=True,
    )

    assert fallback["route_status"] == "blocked"
    assert fallback["failure_mode"] == "provider_auth_header_fallback_ambiguous"
    assert fallback["auth_header"]["default_header_still_accepted"] is True
    assert fallback["auth_header"]["single_trusted_input"] is False
    assert fallback["runtime"]["runner_invoked"] is False
    assert fallback["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_auth_header_fallback_ambiguous",
            "scope": "provider_auth_header",
            "severity": "blocker",
            "action": "configure exactly one valid trusted provider auth header before launching the harness",
            "auth_header_required": True,
            "auth_header_configured": True,
            "auth_header_env_name_configured": True,
            "custom_header_configured": True,
            "selected_header_valid": True,
            "accepted_header_count": 2,
            "single_trusted_input": False,
            "default_header_still_accepted": True,
            "raw_header_name_exported": False,
            "raw_header_value_exported": False,
            "env_name_recorded": False,
        }
    ]

    assert valid_custom["route_status"] == "passed"
    assert valid_custom["failure_mode"] == "none"
    assert valid_custom["auth_header"]["custom_header_configured"] is True
    assert valid_custom["auth_header"]["accepted_header_count"] == 1
    assert valid_custom["auth_header"]["single_trusted_input"] is True
    assert valid_custom["auth_header"]["raw_header_name_exported"] is False
    assert valid_custom["runtime"]["runner_invoked"] is True

    assert malformed["route_status"] == "blocked"
    assert malformed["failure_mode"] == "provider_auth_header_malformed"
    assert malformed["auth_header"]["selected_header_valid"] is False
    assert malformed["runtime"]["runner_invoked"] is False

    assert "OMNIGENT_AUTH_HEADER" not in serialized
    assert "X-Omnigent-User" not in serialized
    assert "X-Forwarded-Email" not in serialized
    assert "X Bad Header" not in serialized


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


def test_provider_runtime_preflight_blocks_dispatchable_worker_inventory_with_none_source():
    blocked = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-cursor-native-source-none",
            "provider": {
                "name": "omnigent-yaml-agent",
                "harness": "omnigent",
                "model_inventory_source_required": True,
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "model_inventory": [
                    {
                        "worker": "cursor",
                        "worker_provider": "cursor-native",
                        "dispatchable": True,
                        "source": "none",
                        "models": ["PRIVATE_CURSOR_MODEL_DO_NOT_EXPORT"],
                    }
                ],
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_cursor_native_source_none_inline.json",
    )
    passed = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-cursor-native-source-ready",
            "provider": {
                "name": "omnigent-yaml-agent",
                "harness": "omnigent",
                "model_inventory_source_required": True,
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
                "model_inventory": [
                    {
                        "worker": "cursor",
                        "worker_provider": "cursor-native",
                        "dispatchable": True,
                        "source": "cursor-native",
                        "models": ["PRIVATE_CURSOR_MODEL_DO_NOT_EXPORT"],
                    }
                ],
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_cursor_native_source_ready_inline.json",
    )
    serialized = json.dumps({"blocked": blocked, "passed": passed}, sort_keys=True)
    serialized_inventory = json.dumps(
        {
            "blocked": blocked["model_inventory"],
            "passed": passed["model_inventory"],
            "recovery_hints": blocked["recovery_hints"],
        },
        sort_keys=True,
    )

    assert blocked["route_status"] == "blocked"
    assert blocked["failure_mode"] == "provider_model_source_none"
    assert blocked["runtime"]["runner_invoked"] is False
    assert blocked["model_inventory"]["required"] is True
    assert blocked["model_inventory"]["configured"] is True
    assert blocked["model_inventory"]["row_count"] == 1
    assert blocked["model_inventory"]["dispatchable_row_count"] == 1
    assert blocked["model_inventory"]["missing_source_row_count"] == 1
    assert blocked["model_inventory"]["rows"][0]["dispatchable"] is True
    assert blocked["model_inventory"]["rows"][0]["source_is_none"] is True
    assert blocked["model_inventory"]["raw_inventory_exported"] is False
    assert blocked["model_inventory"]["raw_worker_names_exported"] is False
    assert blocked["model_inventory"]["raw_source_values_exported"] is False
    assert blocked["model_inventory"]["raw_model_ids_exported"] is False
    assert blocked["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_model_source_none",
            "scope": "provider_model_inventory",
            "severity": "blocker",
            "action": "repair provider model inventory source attribution before exposing dispatchable worker rows",
            "inventory_required": True,
            "inventory_configured": True,
            "inventory_row_count": 1,
            "dispatchable_row_count": 1,
            "missing_source_row_count": 1,
            "raw_inventory_exported": False,
            "raw_model_ids_exported": False,
        }
    ]
    assert blocked["supervisor_replay"]["decision"] == "blocked_before_provider_launch"
    assert blocked["supervisor_replay"]["reason"] == "provider_model_source_none"
    assert blocked["supervisor_replay"]["provider_runtime_launch_allowed"] is False

    assert passed["route_status"] == "passed"
    assert passed["failure_mode"] == "none"
    assert passed["runtime"]["runner_invoked"] is True
    assert passed["model_inventory"]["ok"] is True
    assert passed["model_inventory"]["missing_source_row_count"] == 0
    assert passed["model_inventory"]["rows"][0]["source_is_none"] is False

    assert "PRIVATE_CURSOR_MODEL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CURSOR_MODEL_DO_NOT_EXPORT" not in serialized_inventory
    assert "cursor-native" not in serialized_inventory


def test_provider_runtime_preflight_blocks_litellm_bedrock_auth_fallback_before_launch():
    missing_passthrough = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-litellm-bedrock-auth-fallback",
            "provider": {
                "name": "claude-code",
                "harness": "claude-code",
                "required_env_keys": [
                    "ANTHROPIC_BEDROCK_BASE_URL",
                    "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
                    "ANTHROPIC_AUTH_TOKEN",
                ],
                "auth_precedence": {
                    "required": True,
                    "expected_route": "litellm_bedrock",
                    "fallback_route": "native_anthropic",
                    "fallback_disallowed": True,
                    "required_proxy_env_keys": [
                        "ANTHROPIC_BEDROCK_BASE_URL",
                        "CLAUDE_CODE_USE_BEDROCK",
                        "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
                        "ANTHROPIC_AUTH_TOKEN",
                    ],
                },
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": [
                    "PATH",
                    "ANTHROPIC_BEDROCK_BASE_URL",
                    "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
                    "ANTHROPIC_AUTH_TOKEN",
                ],
                "allowlist": ["PATH"],
                "passthrough": [],
                "env_values": {
                    "ANTHROPIC_AUTH_TOKEN": "PRIVATE_BEDROCK_TOKEN_DO_NOT_EXPORT"
                },
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_litellm_bedrock_auth_fallback_inline.json",
    )
    ready = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-litellm-bedrock-auth-ready",
            "provider": {
                "name": "codex",
                "harness": "codex",
                "required_env_keys": [
                    "ANTHROPIC_BEDROCK_BASE_URL",
                    "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
                    "ANTHROPIC_AUTH_TOKEN",
                ],
                "auth_precedence": {
                    "required": True,
                    "expected_route": "bedrock-litellm",
                    "fallback_route": "anthropic-native",
                    "fallback_disallowed": True,
                },
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": [
                    "PATH",
                    "ANTHROPIC_BEDROCK_BASE_URL",
                    "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
                    "ANTHROPIC_AUTH_TOKEN",
                ],
                "allowlist": [
                    "PATH",
                    "ANTHROPIC_BEDROCK_BASE_URL",
                    "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_SKIP_BEDROCK_AUTH",
                    "ANTHROPIC_AUTH_TOKEN",
                ],
                "passthrough": [],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_litellm_bedrock_auth_ready_inline.json",
    )
    serialized = json.dumps({"missing_passthrough": missing_passthrough, "ready": ready}, sort_keys=True)

    assert missing_passthrough["route_status"] == "blocked"
    assert missing_passthrough["failure_mode"] == "provider_auth_precedence_fallback_risk"
    assert missing_passthrough["runtime"]["runner_invoked"] is False
    assert missing_passthrough["auth_precedence"] == {
        "required": True,
        "ok": False,
        "failure_mode": "provider_auth_precedence_fallback_risk",
        "expected_route": "litellm_bedrock",
        "fallback_route": "native_anthropic",
        "fallback_disallowed": True,
        "proxy_env_key_count": 4,
        "proxy_env_key_hashes": missing_passthrough["auth_precedence"]["proxy_env_key_hashes"],
        "proxy_env_ready": False,
        "missing_parent_env_key_count": 0,
        "missing_harness_env_key_count": 4,
        "raw_env_key_names_exported": False,
        "env_values_exported": False,
        "diagnostics": [
            "configured proxy auth environment did not reach the provider harness; block native auth fallback before launch"
        ],
    }
    assert len(missing_passthrough["auth_precedence"]["proxy_env_key_hashes"]) == 4
    assert missing_passthrough["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["claude-code"],
            "value_recorded": False,
            "code": "provider_auth_precedence_fallback_risk",
            "scope": "provider_auth_precedence",
            "severity": "blocker",
            "action": "preserve configured proxy or Bedrock auth environment into the provider harness before allowing native auth fallback",
            "expected_route": "litellm_bedrock",
            "fallback_route": "native_anthropic",
            "fallback_disallowed": True,
            "proxy_env_key_count": 4,
            "missing_parent_env_key_count": 0,
            "missing_harness_env_key_count": 4,
            "raw_env_key_names_exported": False,
            "env_values_exported": False,
        }
    ]
    assert missing_passthrough["supervisor_replay"]["recovery_hint_codes"] == [
        "provider_auth_precedence_fallback_risk"
    ]

    assert ready["route_status"] == "passed"
    assert ready["failure_mode"] == "none"
    assert ready["auth_precedence"]["expected_route"] == "litellm_bedrock"
    assert ready["auth_precedence"]["fallback_route"] == "native_anthropic"
    assert ready["auth_precedence"]["proxy_env_ready"] is True
    assert ready["runtime"]["runner_invoked"] is True

    assert "ANTHROPIC_BEDROCK_BASE_URL" not in serialized
    assert "CLAUDE_CODE_USE_BEDROCK" not in serialized
    assert "CLAUDE_CODE_SKIP_BEDROCK_AUTH" not in serialized
    assert "ANTHROPIC_AUTH_TOKEN" not in serialized
    assert "PRIVATE_BEDROCK_TOKEN_DO_NOT_EXPORT" not in serialized


def test_provider_runtime_preflight_blocks_unwritable_global_npm_prefix_before_cli_install():
    output = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-npm-prefix-unwritable",
            "provider": {
                "name": "claude-cli",
                "harness": "claude",
                "setup_preflight_required": True,
                "setup_preflight": {
                    "npm_global_install_required": True,
                    "npm_prefix": "PRIVATE_NPM_PREFIX_DO_NOT_EXPORT",
                    "npm_prefix_owner": "root",
                    "npm_prefix_writable": False,
                    "install_command": [
                        "npm",
                        "install",
                        "-g",
                        "PRIVATE_CLAUDE_PACKAGE_DO_NOT_EXPORT",
                    ],
                    "npm_package": "PRIVATE_CLAUDE_PACKAGE_DO_NOT_EXPORT",
                },
            },
            "runtime": {
                "platform": "darwin",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_npm_prefix_unwritable_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_setup_npm_prefix_unwritable"
    assert output["runtime"]["runner_invoked"] is False
    assert output["setup_preflight"]["ok"] is False
    assert output["setup_preflight"]["npm_global_install_required"] is True
    assert output["setup_preflight"]["npm_prefix_observed"] is True
    assert output["setup_preflight"]["npm_prefix_user_owned"] is False
    assert output["setup_preflight"]["npm_prefix_writable"] is False
    assert output["setup_preflight"]["npm_prefix_hash"].startswith("sha256:")
    assert output["setup_preflight"]["npm_prefix_exported"] is False
    assert output["setup_preflight"]["npm_prefix_owner_recorded"] is False
    assert output["setup_preflight"]["npm_install_command_arg_count"] == 4
    assert len(output["setup_preflight"]["npm_install_command_hashes"]) == 4
    assert output["setup_preflight"]["npm_install_command_exported"] is False
    assert output["setup_preflight"]["npm_package_hash"].startswith("sha256:")
    assert output["setup_preflight"]["npm_package_exported"] is False
    assert output["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["claude"],
            "value_recorded": False,
            "code": "provider_setup_npm_prefix_unwritable",
            "scope": "provider_setup_preflight",
            "severity": "blocker",
            "action": "repair provider setup metadata before installing CLI tools or activating LiteLLM-backed model routes",
            "npm_global_install_required": True,
            "npm_prefix_observed": True,
            "npm_prefix_user_owned": False,
            "npm_prefix_writable": False,
            "npm_install_command_arg_count": 4,
            "litellm_adapter": False,
            "litellm_model_configured": False,
            "required_model_prefix_count": 0,
            "model_prefix_ready": True,
            "model_discovery_required": False,
            "discovered_model_count": 0,
            "raw_paths_exported": False,
            "raw_commands_exported": False,
            "raw_model_ids_exported": False,
        }
    ]
    assert output["supervisor_replay"]["recovery_hint_codes"] == ["provider_setup_npm_prefix_unwritable"]

    assert "PRIVATE_NPM_PREFIX_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_CLAUDE_PACKAGE_DO_NOT_EXPORT" not in serialized
    assert "npm install" not in serialized
    assert "root" not in serialized


def test_provider_runtime_preflight_blocks_litellm_model_prefix_or_discovery_gap_before_launch():
    missing_prefix = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-litellm-prefix-missing",
            "provider": {
                "name": "litellm-proxy",
                "harness": "omnigent",
                "setup_preflight": {
                    "provider_adapter": "litellm",
                    "model": "PRIVATE_UNPREFIXED_MODEL_DO_NOT_EXPORT",
                    "required_model_prefixes": ["PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT/"],
                    "model_discovery_required": True,
                    "discovered_models": ["PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT/model"],
                },
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_litellm_prefix_inline.json",
    )
    discovery_missing = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-litellm-discovery-missing",
            "provider": {
                "name": "litellm-proxy",
                "harness": "omnigent",
                "setup_preflight": {
                    "provider_adapter": "litellm",
                    "model": "PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT/model",
                    "required_model_prefixes": ["PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT/"],
                    "model_discovery_required": True,
                    "discovered_models": [],
                },
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_litellm_discovery_inline.json",
    )
    ready = evaluate_harness_behavior(
        "provider_runtime_preflight",
        {
            "task_id": "fixture-provider-runtime-preflight-litellm-ready",
            "provider": {
                "name": "litellm-proxy",
                "harness": "omnigent",
                "setup_preflight": {
                    "provider_adapter": "litellm",
                    "model": "PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT/model",
                    "required_model_prefixes": ["PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT/"],
                    "model_discovery_required": True,
                    "discovered_models": ["PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT/model"],
                },
            },
            "runtime": {
                "platform": "linux",
                "launch_transport": "subprocess",
            },
            "runner_env": {
                "parent_env_keys": ["PATH"],
                "allowlist": ["PATH"],
            },
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_litellm_ready_inline.json",
    )
    serialized = json.dumps(
        {"discovery_missing": discovery_missing, "missing_prefix": missing_prefix, "ready": ready},
        sort_keys=True,
    )

    assert missing_prefix["route_status"] == "blocked"
    assert missing_prefix["failure_mode"] == "provider_setup_litellm_model_prefix_missing"
    assert missing_prefix["runtime"]["runner_invoked"] is False
    assert missing_prefix["setup_preflight"]["litellm_adapter"] is True
    assert missing_prefix["setup_preflight"]["litellm_model_configured"] is True
    assert missing_prefix["setup_preflight"]["litellm_model_hash"].startswith("sha256:")
    assert missing_prefix["setup_preflight"]["litellm_model_exported"] is False
    assert missing_prefix["setup_preflight"]["required_model_prefix_count"] == 1
    assert missing_prefix["setup_preflight"]["required_model_prefixes_exported"] is False
    assert missing_prefix["setup_preflight"]["model_prefix_ready"] is False
    assert missing_prefix["setup_preflight"]["model_discovery_required"] is True
    assert missing_prefix["setup_preflight"]["discovered_model_count"] == 1
    assert missing_prefix["setup_preflight"]["discovered_models_exported"] is False
    assert missing_prefix["recovery_hints"][0]["code"] == "provider_setup_litellm_model_prefix_missing"
    assert missing_prefix["recovery_hints"][0]["raw_model_ids_exported"] is False

    assert discovery_missing["route_status"] == "blocked"
    assert discovery_missing["failure_mode"] == "provider_setup_litellm_model_discovery_missing"
    assert discovery_missing["runtime"]["runner_invoked"] is False
    assert discovery_missing["setup_preflight"]["model_prefix_ready"] is True
    assert discovery_missing["setup_preflight"]["model_discovery_required"] is True
    assert discovery_missing["setup_preflight"]["discovered_model_count"] == 0
    assert discovery_missing["recovery_hints"][0]["code"] == "provider_setup_litellm_model_discovery_missing"

    assert ready["route_status"] == "passed"
    assert ready["failure_mode"] == "none"
    assert ready["runtime"]["runner_invoked"] is True
    assert ready["setup_preflight"]["ok"] is True
    assert ready["setup_preflight"]["discovered_model_count"] == 1

    assert "PRIVATE_UNPREFIXED_MODEL_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_MODEL_PREFIX_DO_NOT_EXPORT" not in serialized


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


def test_agent_workflow_route_watchdog_timeout_preserves_transport_root_cause_without_bodies():
    raw_input = {
        "task_id": "fixture-route-watchdog-root-cause",
        "plan": {"steps": [{"id": "inspect"}, {"id": "run"}, {"id": "recover"}]},
        "runner": {"invoked": True, "returncode": None, "timed_out": True},
        "watchdog": {
            "configured": True,
            "timeout_seconds": 240,
            "idle_seconds": 240,
            "recent_transport_errors": [
                {
                    "id": "PRIVATE_EVENT_ID_DO_NOT_EXPORT",
                    "transport": "forwarder",
                    "error": "POST /session PRIVATE_REQUEST_BODY_DO_NOT_EXPORT failed: No route to host",
                    "request": "PRIVATE_REQUEST_BODY_DO_NOT_EXPORT",
                    "age_seconds": 3,
                }
            ],
        },
        "validation": {"gate": "narrow-local-verification", "checks": [{"name": "pytest", "returncode": 0}]},
        "rollback": {
            "created": True,
            "ref": "refs/rollback/fixture-route-watchdog-root-cause",
            "artifact_path": "artifacts/rollback/fixture-route-watchdog-root-cause.txt",
        },
    }

    output = evaluate_harness_behavior(
        "agent_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "agent_workflow_route_watchdog_root_cause_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "failed_recoverable"
    assert output["failure_mode"] == "watchdog_timeout_with_transport_root_cause"
    assert output["watchdog"]["timeout_seconds"] == 240
    assert output["watchdog"]["idle_seconds"] == 240
    assert output["watchdog"]["root_cause_attached"] is True
    assert output["watchdog"]["root_cause_classification"] == "no_route_to_host"
    assert output["control_plane"]["watchdog_contract"]["root_cause_classification"] == "no_route_to_host"
    assert output["watchdog"]["privacy"] == {
        "raw_error_bodies_exported": False,
        "raw_request_bodies_exported": False,
        "raw_urls_exported": False,
        "raw_headers_exported": False,
    }
    assert "PRIVATE_REQUEST_BODY_DO_NOT_EXPORT" not in serialized
    assert "POST /session" not in serialized
    assert "No route to host" not in serialized
    assert "PRIVATE_EVENT_ID_DO_NOT_EXPORT" not in serialized


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


def test_provider_runtime_preflight_blocks_claude_sdk_errno8_startup_without_body_export():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_claude_sdk_errno8_startup.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_startup_errno8"
    assert output["runtime"]["runner_invoked"] is False
    assert output["startup_preflight"] == {
        "required": True,
        "observed": True,
        "ok": False,
        "failure_mode": "provider_startup_errno8",
        "provider_harness_hash": stable_text_hash("claude-sdk"),
        "provider_harness_recorded": False,
        "platform": "linux",
        "supported_platform_count": 2,
        "platform_supported": True,
        "executable_required": True,
        "executable_configured": True,
        "executable_resolved": True,
        "executable_hash": stable_text_hash("PRIVATE_CLAUDE_SDK_EXECUTABLE_DO_NOT_EXPORT"),
        "executable_recorded": False,
        "provider_config_required": True,
        "provider_config_present": True,
        "provider_config_value_recorded": False,
        "startup_failed": True,
        "errno_observed": True,
        "errno": 8,
        "exec_format_failure": True,
        "stderr_body_exported": False,
        "raw_error_body_exported": False,
        "raw_startup_exported": False,
        "diagnostics": [
            "provider harness startup failed with Errno 8-compatible exec format diagnostics",
        ],
    }
    assert output["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["claude-sdk"],
            "value_recorded": False,
            "code": "provider_startup_errno8",
            "scope": "provider_startup_preflight",
            "severity": "blocker",
            "action": "repair executable resolution, platform compatibility, or provider config before launching the harness",
            "platform": "linux",
            "supported_platform_count": 2,
            "platform_supported": True,
            "executable_required": True,
            "executable_configured": True,
            "executable_resolved": True,
            "provider_config_required": True,
            "provider_config_present": True,
            "errno_observed": True,
            "errno": 8,
            "exec_format_failure": True,
            "raw_executable_exported": False,
            "raw_config_exported": False,
            "raw_error_body_exported": False,
        }
    ]
    assert output["supervisor_replay"]["reason"] == "provider_startup_errno8"
    assert output["supervisor_replay"]["provider_runtime_launch_allowed"] is False
    assert output["preflight"]["diagnostics"] == [
        "provider harness startup failed with Errno 8-compatible exec format diagnostics",
    ]
    assert "PRIVATE_CLAUDE_SDK_EXECUTABLE_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_ERRNO8_STARTUP_BODY_DO_NOT_EXPORT" not in serialized


def test_provider_runtime_preflight_blocks_omnigent_turn_context_desync_without_body_export():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "provider_runtime_preflight_omnigent_turn_context_desync.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "provider_runner_turn_context_desync"
    assert output["runtime"]["runner_invoked"] is False
    assert output["runner_state"] == {
        "required": True,
        "observed": True,
        "ok": False,
        "failure_mode": "provider_runner_turn_context_desync",
        "provider_harness_hash": stable_text_hash("omnigent"),
        "provider_harness_recorded": False,
        "session_ref_hash": stable_text_hash("PRIVATE_OMNIGENT_SESSION_REF_DO_NOT_EXPORT"),
        "session_ref_recorded": False,
        "active_turn_context_required": True,
        "active_turn_context_bound": False,
        "tool_callback_count": 24,
        "orphaned_tool_callback_count": 20,
        "consecutive_orphaned_callback_count": 6,
        "buffered_mid_turn_message": True,
        "harness_disconnect_observed": True,
        "policy_default_allow_observed": True,
        "policy_fail_closed_configured": False,
        "self_heal_rebind_configured": False,
        "watchdog_configured": False,
        "restart_required": True,
        "turn_context_desync": True,
        "policy_fail_open_risk": True,
        "raw_callback_bodies_exported": False,
        "raw_policy_bodies_exported": False,
        "raw_session_ref_exported": False,
        "raw_runner_logs_exported": False,
        "diagnostics": [
            "runner active-turn context is required but not bound",
            "runner tool callbacks were observed without active turn context",
            "mid-turn message buffering coincided with harness disconnect",
            "runner policy defaulted allow while turn context was missing",
            "runner turn-context self-heal or watchdog is not configured",
        ],
    }
    assert output["recovery_hints"] == [
        {
            "affected_preflight_count": 1,
            "provider_harnesses": ["omnigent"],
            "value_recorded": False,
            "code": "provider_runner_turn_context_desync",
            "scope": "provider_runner_state",
            "severity": "blocker",
            "action": "rebind active turn context or configure runner self-heal/watchdog and fail-closed policy handling before provider launch",
            "active_turn_context_required": True,
            "active_turn_context_bound": False,
            "tool_callback_count": 24,
            "orphaned_tool_callback_count": 20,
            "consecutive_orphaned_callback_count": 6,
            "buffered_mid_turn_message": True,
            "harness_disconnect_observed": True,
            "policy_default_allow_observed": True,
            "policy_fail_closed_configured": False,
            "self_heal_rebind_configured": False,
            "watchdog_configured": False,
            "restart_required": True,
            "raw_session_ref_exported": False,
            "raw_runner_logs_exported": False,
            "raw_callback_bodies_exported": False,
            "raw_policy_bodies_exported": False,
        }
    ]
    assert output["supervisor_replay"]["reason"] == "provider_runner_turn_context_desync"
    assert output["supervisor_replay"]["provider_runtime_launch_allowed"] is False
    assert output["preflight"]["diagnostics"] == output["runner_state"]["diagnostics"]
    assert "PRIVATE_OMNIGENT_SESSION_REF_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_OMNIGENT_RUNNER_LOG_DO_NOT_EXPORT" not in serialized


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
        "route_status": "missing",
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


def test_mock_llm_workflow_route_reconstructs_web_researcher_from_nested_web_fetch_parent():
    raw_input = {
        "task_id": "fixture-mock-llm-web-researcher-nested-web-fetch",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "sub_agents": {
            "parent_name": "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
            "agents": [
                {
                    "name": "__web_researcher",
                    "expected_response_key": "research-queue",
                    "turn_session_ids": ["PRIVATE_RESEARCH_SESSION_DO_NOT_EXPORT"],
                    "persistence_required": True,
                    "resolution": {
                        "resolver_miss": True,
                        "resolved_agent_name": "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
                        "web_researcher_gate": {
                            "target_name": "__web_researcher",
                            "parent_path": [
                                "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
                                "PRIVATE_INTERMEDIATE_PARENT_DO_NOT_EXPORT",
                                "PRIVATE_NESTED_FETCH_PARENT_DO_NOT_EXPORT",
                            ],
                            "bundle": {
                                "root": {
                                    "name": "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
                                    "tools": {"builtins": []},
                                    "sub_agents": [
                                        {
                                            "name": "PRIVATE_INTERMEDIATE_PARENT_DO_NOT_EXPORT",
                                            "tools": {"builtins": []},
                                            "sub_agents": [
                                                {
                                                    "name": "PRIVATE_NESTED_FETCH_PARENT_DO_NOT_EXPORT",
                                                    "tools": {"builtins": [{"name": "web_fetch"}]},
                                                }
                                            ],
                                        }
                                    ],
                                }
                            },
                        },
                    },
                }
            ],
        },
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "research-queue": [{"content": "nested web fetch research turn"}],
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "research-turn",
                    "agent": "__web_researcher",
                    "response_key": "research-queue",
                    "expect_contains": "research",
                }
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_web_researcher_nested_web_fetch_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)
    resolution = output["sub_agents"]["agents"][0]["resolution"]
    gate = resolution["web_researcher_gate"]

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    assert output["sub_agents"]["resolution_guard_passed"] is True
    assert resolution["resolver_miss"] is True
    assert resolution["reconstructed_on_miss"] is True
    assert resolution["fallback_to_parent_detected"] is False
    assert resolution["guard_passed"] is True
    assert resolution["decision"] == "reconstructed_child_spec"
    assert gate["target_is_web_researcher"] is True
    assert gate["root_has_web_fetch"] is False
    assert gate["parent_path_depth"] == 3
    assert gate["parent_path_found"] is True
    assert gate["matching_parent_depth"] == 2
    assert gate["parent_has_web_fetch"] is True
    assert gate["nested_parent_lookup_passed"] is True
    assert gate["nested_web_fetch_depths"] == [2]
    assert gate["root_only_gate_would_miss"] is True
    assert gate["reconstruction_supported"] is True
    assert gate["decision"] == "nested_web_fetch_parent_accepted"
    assert gate["raw_agent_names_exported"] is False
    assert "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_INTERMEDIATE_PARENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NESTED_FETCH_PARENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RESEARCH_SESSION_DO_NOT_EXPORT" not in serialized


def test_mock_llm_workflow_route_blocks_web_researcher_when_nested_web_fetch_parent_missing():
    raw_input = {
        "task_id": "fixture-mock-llm-web-researcher-parent-missing",
        "provider": {"name": "external-chat-provider", "enabled": False},
        "sub_agents": {
            "parent_name": "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
            "agents": [
                {
                    "name": "__web_researcher",
                    "expected_response_key": "research-queue",
                    "turn_session_ids": ["PRIVATE_RESEARCH_SESSION_DO_NOT_EXPORT"],
                    "persistence_required": True,
                    "resolution": {
                        "resolver_miss": True,
                        "resolved_agent_name": "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
                        "web_researcher_gate": {
                            "target_name": "__web_researcher",
                            "parent_path": [
                                "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
                                "PRIVATE_NESTED_FETCH_PARENT_DO_NOT_EXPORT",
                            ],
                            "bundle": {
                                "root": {
                                    "name": "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT",
                                    "tools": {"builtins": []},
                                    "sub_agents": [
                                        {
                                            "name": "PRIVATE_NESTED_FETCH_PARENT_DO_NOT_EXPORT",
                                            "tools": {"builtins": []},
                                        }
                                    ],
                                }
                            },
                        },
                    },
                }
            ],
        },
        "mock_llm": {
            "enabled": True,
            "response_queues": {
                "research-queue": [{"content": "nested web research turn"}],
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "research-turn",
                    "agent": "__web_researcher",
                    "response_key": "research-queue",
                    "expect_contains": "research",
                }
            ]
        },
    }

    output = evaluate_harness_behavior(
        "mock_llm_workflow_route",
        raw_input,
        source_path=LOCAL_EVAL_FIXTURE_DIR / "mock_llm_web_researcher_parent_missing_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)
    resolution = output["sub_agents"]["agents"][0]["resolution"]
    gate = resolution["web_researcher_gate"]

    assert output["route_status"] == "failed"
    assert output["failure_mode"] == "sub_agent_mock_route_failed"
    assert output["sub_agents"]["resolution_guard_passed"] is False
    assert resolution["resolver_miss"] is True
    assert resolution["fallback_to_parent_detected"] is True
    assert resolution["guard_passed"] is False
    assert resolution["failure_mode"] == "parent_clone_fallback"
    assert gate["parent_path_found"] is True
    assert gate["matching_parent_depth"] == 1
    assert gate["parent_has_web_fetch"] is False
    assert gate["nested_web_fetch_depths"] == []
    assert gate["nested_parent_lookup_passed"] is False
    assert gate["reconstruction_supported"] is False
    assert gate["decision"] == "web_fetch_parent_missing"
    assert gate["failure_mode"] == "web_researcher_parent_resolution_miss"
    assert "PRIVATE_ROOT_COORDINATOR_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_NESTED_FETCH_PARENT_DO_NOT_EXPORT" not in serialized
    assert "PRIVATE_RESEARCH_SESSION_DO_NOT_EXPORT" not in serialized


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


def test_skill_route_discovery_validation_readiness_summary_surfaces_selected_lane_without_urls():
    fixture_path = LOCAL_EVAL_FIXTURE_DIR / "skill_route_discovery_lane_pass2_window.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    output = evaluate_harness_behavior(
        str(fixture["behavior"]),
        fixture["input"],
        source_path=fixture_path,
    )
    serialized = json.dumps(output["validation_readiness_summary"], sort_keys=True)

    summary = output["validation_readiness_summary"]
    assert summary["status"] == "ready"
    assert summary["decision"] == "operator_can_replay_selected_bounded_validation_lane"
    assert summary["selected_local_lane"] == "test"
    assert summary["validation_scope"] == "local_test_lane_only"
    assert summary["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "source_cited_domain_research",
    ]
    assert summary["route_profile_count"] == 3
    assert summary["selected_profile_count"] == 3
    assert summary["lane_validation_target_count"] == 2
    assert summary["activity_lane_count"] == 4
    assert summary["supervisor_decision"] == "ready_for_supervisor_promotion"
    assert summary["generic_prompt_required"] is False
    checklist = summary["profile_validation_checklist"]
    assert checklist["controller_surface"] == "skill_route_discovery_profile_validation_checklist"
    assert checklist["status"] == "ready"
    assert checklist["decision"] == "profile_lanes_ready_for_bounded_local_replay"
    assert checklist["profile_acceptance_contract_status"] == "ready"
    assert checklist["profile_count"] == 4
    assert checklist["selected_current_pass_profile_count"] == 3
    assert checklist["queued_profile_count"] == 1
    assert checklist["accepted_profile_count"] == 4
    assert checklist["evidence_ref_mode"] == "selected_item_ids_only"
    assert checklist["runtime_action_allowed"] is False
    assert checklist["external_skill_activation_allowed"] is False
    assert checklist["external_harness_execution_allowed"] is False
    assert checklist["provider_runtime_launch_allowed"] is False
    assert checklist["raw_source_urls_exported"] is False

    checklist_rows = {row["route_profile"]: row for row in checklist["rows"]}
    assert checklist_rows["codex_workflow_gate"]["pass_role"] == "selected_current_pass_profile"
    assert checklist_rows["codex_workflow_gate"]["expected_first_local_lane"] == "test"
    assert checklist_rows["codex_workflow_gate"]["validation_gate"] == (
        "skill_route_discovery_first_before_workflow_gate"
    )
    assert checklist_rows["game_frontend_workflow"]["pass_role"] == "selected_current_pass_profile"
    assert checklist_rows["game_frontend_workflow"]["expected_first_local_lane"] == "test"
    assert checklist_rows["source_cited_domain_research"]["pass_role"] == "selected_current_pass_profile"
    assert checklist_rows["source_cited_domain_research"]["expected_first_local_lane"] == "test"
    assert checklist_rows["skill_ecosystem_state_handoff"]["pass_role"] == "queued_profile_for_later_pass"
    assert checklist_rows["skill_ecosystem_state_handoff"]["expected_first_local_lane"] == "config"
    for row in checklist["rows"]:
        assert row["accepted_for_local_validation"] is True
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_upstream_body_exported"] is False

    assert summary["runtime_action_allowed"] is False
    assert summary["external_skill_activation_allowed"] is False
    assert summary["external_harness_execution_allowed"] is False
    assert summary["provider_runtime_launch_allowed"] is False
    assert summary["remote_execution_allowed"] is False
    assert summary["raw_source_urls_exported"] is False
    assert summary["provider_runtime_preflight"]["status"] == "not_applicable"
    assert summary["provider_runtime_preflight"]["provider_runtime_launch_allowed"] is False
    assert summary["provider_runtime_preflight"]["raw_preflight_inputs_exported"] is False
    assert "https://github.com/" not in serialized

    pass2_summary = output["pass2_handoff_packet"]["route_profile_acceptance_summary"]
    pass2_serialized = json.dumps(pass2_summary, sort_keys=True)
    assert pass2_summary["controller_surface"] == (
        "skill_route_discovery_pass2_route_profile_acceptance_summary"
    )
    assert pass2_summary["status"] == "ready"
    assert pass2_summary["decision"] == "profile_routes_accepted_for_bounded_local_lanes"
    assert pass2_summary["profile_acceptance_contract_status"] == "ready"
    assert pass2_summary["profile_count"] == 4
    assert pass2_summary["selected_current_pass_profile_count"] == 3
    assert pass2_summary["queued_profile_count"] == 1
    assert pass2_summary["accepted_profile_count"] == 4
    assert pass2_summary["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert pass2_summary["selected_local_lanes"] == ["test"]
    assert pass2_summary["queued_local_lanes"] == ["config"]
    assert pass2_summary["mixed_skill_workflow_primary_route"] == "skill_route_discovery"
    assert pass2_summary["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert pass2_summary["secondary_harness_eval_allowed"] is False

    pass2_matrix = output["pass2_handoff_packet"]["profile_lane_matrix"]
    matrix_serialized = json.dumps(pass2_matrix, sort_keys=True)
    assert pass2_matrix["controller_surface"] == "skill_route_discovery_pass2_profile_lane_matrix"
    assert pass2_matrix["status"] == "ready"
    assert pass2_matrix["decision"] == "profile_lanes_mapped_to_bounded_pass2_lanes"
    assert pass2_matrix["matrix_scope"] == "pass2_profile_acceptance_rows"
    assert pass2_matrix["profile_acceptance_contract_status"] == "ready"
    assert pass2_matrix["profile_count"] == 4
    assert pass2_matrix["selected_current_pass_profile_count"] == 3
    assert pass2_matrix["queued_profile_count"] == 1
    assert pass2_matrix["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert pass2_matrix["selected_local_lanes"] == ["config", "test"]
    matrix_rows = {row["route_profile"]: row for row in pass2_matrix["rows"]}
    assert matrix_rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert matrix_rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert matrix_rows["source_cited_domain_research"]["selected_local_lane"] == "test"
    assert matrix_rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert all(row["lane_bounded"] is True for row in pass2_matrix["rows"])
    assert all(row["accepted_for_local_validation"] is True for row in pass2_matrix["rows"])
    assert all(row["local_validation_required"] is True for row in pass2_matrix["rows"])
    assert all(row["runtime_action"] == "none" for row in pass2_matrix["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in pass2_matrix["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in pass2_matrix["rows"])
    assert pass2_matrix["runtime_action_allowed"] is False
    assert pass2_matrix["external_skill_activation_allowed"] is False
    assert pass2_matrix["external_harness_execution_allowed"] is False
    assert pass2_matrix["provider_runtime_launch_allowed"] is False
    assert pass2_matrix["remote_execution_allowed"] is False
    assert pass2_matrix["raw_evidence_urls_exported"] is False
    assert pass2_matrix["raw_source_urls_exported"] is False
    assert pass2_matrix["raw_target_paths_exported"] is False
    assert pass2_matrix["raw_upstream_body_exported"] is False
    assert "https://github.com/" not in matrix_serialized

    pass2_rows = {row["route_profile"]: row for row in pass2_summary["rows"]}
    assert pass2_rows["codex_workflow_gate"]["pass_role"] == "selected_current_pass_profile"
    assert pass2_rows["codex_workflow_gate"]["expected_first_local_lane"] == "test"
    assert pass2_rows["codex_workflow_gate"]["route_probe_decision"] == "skill_route_discovery_first"
    assert pass2_rows["game_frontend_workflow"]["pass_role"] == "selected_current_pass_profile"
    assert pass2_rows["game_frontend_workflow"]["expected_first_local_lane"] == "test"
    assert pass2_rows["source_cited_domain_research"]["pass_role"] == "selected_current_pass_profile"
    assert pass2_rows["source_cited_domain_research"]["expected_first_local_lane"] == "test"
    assert pass2_rows["source_cited_domain_research"]["validation_gate"] == (
        "source_citation_and_advice_boundary_before_domain_skill_activation"
    )
    assert pass2_rows["skill_ecosystem_state_handoff"]["pass_role"] == "queued_profile_for_later_pass"
    assert pass2_rows["skill_ecosystem_state_handoff"]["expected_first_local_lane"] == "config"
    for row in pass2_summary["rows"]:
        assert row["accepted_for_local_validation"] is True
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_harness_execution_allowed"] is False
        assert row["provider_runtime_launch_allowed"] is False
        assert row["remote_execution_allowed"] is False
        assert row["raw_evidence_urls_exported"] is False
        assert row["raw_source_urls_exported"] is False
        assert row["raw_target_paths_exported"] is False
        assert row["raw_upstream_body_exported"] is False
    assert "https://github.com/" not in pass2_serialized


def test_skill_route_discovery_pass2_profile_lane_matrix_covers_generic_skill_profiles():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-pass2-generic-profile-matrix",
            "capability_window": {
                "theme": "skill-route-discovery",
                "capability_slice": "Convert skill and route evidence into bounded local lanes before activation.",
                "current_pass": 2,
                "total_passes": 4,
                "required_route_profiles": [
                    "generic_skill_workflow",
                    "skill_ecosystem_state_handoff",
                    "game_frontend_workflow",
                    "codex_workflow_gate",
                ],
                "evidence_urls": [
                    "https://github.com/baskduf/FableCodex",
                    "https://github.com/dongshuyan/compass-skills",
                    "https://github.com/majidmanzarpour/threejs-game-skills",
                ],
            },
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "generic-skill-workflow",
                    "source_url": "https://github.com/example/generic-skill-workflow",
                    "evidence_summary": (
                        "Reusable agent skill workflow with selected digest item ids, "
                        "body-free repository summary, local artifact target, and validation notes."
                    ),
                    "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                    "evidence_item_ids": ["p4-skill-route-fixture-tests"],
                    "evidence_urls": ["https://github.com/example/generic-skill-workflow"],
                },
                {
                    "name": "compass-skills",
                    "source_url": "https://github.com/dongshuyan/compass-skills",
                    "evidence_summary": (
                        "Skill ecosystem with task clarification, repo-local local memory, "
                        "handoff prompts, collaboration profile, route metadata, validation evidence, "
                        "and privacy boundary notes."
                    ),
                    "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                    "evidence_item_ids": ["p3-skill-route-discovery-catalog"],
                    "evidence_urls": ["https://github.com/dongshuyan/compass-skills"],
                },
                {
                    "name": "threejs-game-skills",
                    "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                    "evidence_summary": (
                        "Three.js browser game director skill bundle with QA validation, "
                        "screenshot and canvas checks, asset/provider boundary notes, and generation limits."
                    ),
                    "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                    "evidence_item_ids": ["p5-game-frontend-skill-profile-check"],
                    "evidence_urls": ["https://github.com/majidmanzarpour/threejs-game-skills"],
                },
                {
                    "name": "codex-fable5",
                    "source_url": "https://github.com/baskduf/FableCodex",
                    "evidence_summary": (
                        "Codex agent skill workflow gate with review ledger, verification habit, "
                        "plugin routing docs, and local test coverage notes."
                    ),
                    "candidate_lanes": ["documentation", "config", "test", "code_patch"],
                    "evidence_item_ids": ["p1-skill-route-discovery-matrix"],
                    "evidence_urls": ["https://github.com/baskduf/FableCodex"],
                },
            ],
            "state_handoff_boundary": {
                "retention_policy_documented": True,
                "privacy_boundary_documented": True,
                "local_target_metadata_only": True,
                "upstream_presence_grants_write": False,
            },
            "local_artifact_proofs": [
                {
                    "proposal_kind": "documentation",
                    "changed_files": ["docs/skill-route-discovery.md"],
                    "validation_commands": ["pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane"],
                    "rollback_artifact": "artifacts/rollback/20260623T101652Z-skill-route-pass2-profile-lanes.md",
                    "review_note": "Generic skill workflow documentation lane remains bounded.",
                },
                {
                    "proposal_kind": "config",
                    "changed_files": ["src/blackhole_agent/proposal_synthesis.py"],
                    "validation_commands": ["pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane"],
                    "rollback_artifact": "artifacts/rollback/20260623T101652Z-skill-route-pass2-profile-lanes.md",
                    "review_note": "State-handoff config lane remains metadata-only.",
                },
                {
                    "proposal_kind": "test",
                    "changed_files": ["tests/test_harness_eval.py"],
                    "validation_commands": ["pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane"],
                    "rollback_artifact": "artifacts/rollback/20260623T101652Z-skill-route-pass2-profile-lanes.md",
                    "review_note": "Profile fixture lanes replay through local tests.",
                },
                {
                    "proposal_kind": "code_patch",
                    "changed_files": ["src/blackhole_agent/harness_eval.py"],
                    "validation_commands": ["pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane"],
                    "rollback_artifact": "artifacts/rollback/20260623T101652Z-skill-route-pass2-profile-lanes.md",
                    "review_note": "Code-patch lane remains a local harness/controller target.",
                },
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_pass2_generic_profile_matrix_inline.json",
    )
    serialized = json.dumps(output["pass2_handoff_packet"], sort_keys=True)

    assert output["route_status"] == "passed"
    assert output["failure_mode"] == "none"
    matrix = output["pass2_handoff_packet"]["profile_lane_matrix"]
    assert matrix["status"] == "blocked"
    assert matrix["diagnostics"] == [
        "pass_validation_replay_queue_not_ready",
        "validation_readiness_summary_not_ready",
    ]
    assert matrix["route_profiles"] == [
        "codex_workflow_gate",
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    rows = {row["route_profile"]: row for row in matrix["rows"]}
    assert set(rows) == {
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
        "game_frontend_workflow",
        "codex_workflow_gate",
    }
    assert rows["generic_skill_workflow"]["selected_local_lane"] == "documentation"
    assert rows["skill_ecosystem_state_handoff"]["selected_local_lane"] == "config"
    assert rows["game_frontend_workflow"]["selected_local_lane"] == "test"
    assert rows["codex_workflow_gate"]["selected_local_lane"] == "test"
    assert set(matrix["selected_local_lanes"]) <= {
        "documentation",
        "config",
        "test",
        "code_patch",
    }
    assert all(
        set(row["allowed_local_lanes"]) <= {"documentation", "config", "test", "code_patch"}
        for row in matrix["rows"]
    )
    assert all(row["lane_bounded"] is True for row in matrix["rows"])
    assert all(row["accepted_for_local_validation"] is True for row in matrix["rows"])
    assert all(row["runtime_action"] == "none" for row in matrix["rows"])
    assert all(row["external_skill_activation_allowed"] is False for row in matrix["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in matrix["rows"])
    assert matrix["provider_runtime_launch_allowed"] is False
    assert matrix["remote_execution_allowed"] is False
    assert matrix["raw_evidence_urls_exported"] is False
    assert matrix["raw_source_urls_exported"] is False
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_generic_pull_request_prompts_for_local_validation():
    output = evaluate_harness_behavior(
        "skill_route_discovery_lane",
        {
            "task_id": "fixture-skill-route-low-detail-pr-prompt",
            "source_kind": "candidates",
            "candidates": [
                {
                    "name": "omnigent-generic-pr",
                    "source_url": "https://github.com/omnigent-ai/omnigent",
                    "discovery_event_kind": "PullRequestEvent",
                    "evidence_summary": (
                        "Generic untitled pull request lifecycle signal with missing PR detail; "
                        "route hint and test words are insufficient without local corroboration."
                    ),
                    "candidate_lanes": ["test"],
                    "evidence_item_ids": ["omnigent-generic-pr"],
                    "evidence_urls": ["https://github.com/omnigent-ai/omnigent"],
                }
            ],
        },
        source_path=LOCAL_EVAL_FIXTURE_DIR / "skill_route_low_detail_pr_prompt_inline.json",
    )
    serialized = json.dumps(output, sort_keys=True)

    assert output["route_status"] == "blocked"
    assert output["failure_mode"] == "weak_generic_upstream_evidence"
    assert output["lane_map"]["proposal_lane_count"] == 1
    assert output["activity_signal_panel"]["generic_movement_policy"] == (
        "supporting_context_only_until_local_corroboration"
    )
    assert output["activity_signal_panel"]["rows"][0]["event_kind"] == "pull_request"
    assert output["activity_signal_panel"]["rows"][0]["weak_generic_supporting_context_only"] is True
    assert output["generic_validation_prompt"]["status"] == "review"
    assert output["generic_validation_prompt"]["decision"] == "collect_local_corroboration_before_activation"
    assert output["generic_validation_prompt"]["prompt_required"] is True
    assert output["generic_validation_prompt"]["prompt_count"] == 1
    assert output["generic_validation_prompt"]["low_detail_rows"][0]["proposal_kind"] == "test"
    assert output["generic_validation_prompt"]["local_proposal_activation_allowed"] is False
    assert output["generic_validation_prompt"]["runtime_action_allowed"] is False
    assert output["generic_validation_prompt"]["external_skill_activation_allowed"] is False
    assert output["validation_readiness_summary"]["status"] == "review"
    assert output["validation_readiness_summary"]["decision"] == "collect_local_corroboration_before_replay"
    assert output["validation_readiness_summary"]["generic_prompt_required"] is True
    assert output["validation_readiness_summary"]["runtime_action_allowed"] is False
    assert output["validation_readiness_summary"]["external_skill_activation_allowed"] is False
    assert "https://github.com/omnigent-ai/omnigent" not in serialized


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
