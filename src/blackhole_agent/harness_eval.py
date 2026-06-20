"""Privacy-preserving comparison reports and local eval fixtures for agent harness runs."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


BODY_KEYS = {
    "input",
    "last_message",
    "output",
    "prompt",
    "prompt_body",
    "response",
    "stderr_tail",
    "stdout_tail",
    "task",
}

PRIVACY_REVIEW_FLAG_KEYS = {
    "contains_personal_data",
    "contains_pii",
    "contains_private_content",
    "contains_secrets",
    "contains_sensitive_content",
    "privacy_review_required",
}

PRIVACY_REVIEW_GATE = "privacy-leakage-human-review"
SAFETY_BOUNDARY_REVIEW_FLAGS = {
    "offensive-behavior",
    "privacy-leakage",
}
SUPPORTED_LOCAL_HARNESS_BEHAVIORS = [
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

NATIVE_TOOL_CALL_PHASES = {"PreToolUse", "PHASE_TOOL_CALL", "TOOL_CALL", "tool_call"}
NATIVE_POLICY_PHASE_KIND_ALIASES = {
    "PreToolUse": "TOOL_CALL",
    "PHASE_TOOL_CALL": "TOOL_CALL",
    "TOOL_CALL": "TOOL_CALL",
    "tool_call": "TOOL_CALL",
    "PostToolUse": "TOOL_RESULT",
    "PHASE_TOOL_RESULT": "TOOL_RESULT",
    "TOOL_RESULT": "TOOL_RESULT",
    "tool_result": "TOOL_RESULT",
    "OUTPUT": "OUTPUT",
    "PHASE_OUTPUT": "OUTPUT",
    "output": "OUTPUT",
    "AgentStart": "SUB_AGENT",
    "SubAgentStart": "SUB_AGENT",
    "SUB_AGENT": "SUB_AGENT",
    "sub_agent": "SUB_AGENT",
    "agent_start": "SUB_AGENT",
}
NATIVE_INTERACTIVE_ASK_PHASE_KINDS = {"TOOL_CALL", "TOOL_RESULT", "OUTPUT", "SUB_AGENT"}
NATIVE_POLICY_HOOK_UNAVAILABLE_FAILURES = {
    "connect_error",
    "empty_body",
    "malformed_json",
    "non_2xx",
    "server_unreachable",
    "timeout",
}
NATIVE_POLICY_HOOK_ASK_TIMEOUT_FAILURES = {
    "ask_timeout",
    "slow_ask_timeout",
}
CI_ROUND_TRIP_AUTH_FAILURE_MARKERS = (
    "401",
    "api key",
    "auth",
    "authentication",
    "credential",
    "login required",
    "unauthorized",
)
CI_ROUND_TRIP_HANG_MARKERS = (
    "ci round-trip",
    "ci round trip",
    "hang",
    "hung",
    "no completion",
    "no response",
    "round-trip",
    "round trip",
    "timed out",
    "timeout",
)
AGENT_HARNESS_EVAL_HINT = "agent_harness_eval"
AGENT_HARNESS_EVAL_ALLOWED_LANES = ("documentation", "test", "code_patch")
AGENT_HARNESS_EVAL_DETAIL_MARKERS = (
    "deterministic",
    "fixture",
    "replay",
    "stage",
    "structured",
    "triage artifact",
    "validation",
)
AGENT_HARNESS_EVAL_CLAIM_PATTERNS: dict[str, dict[str, Any]] = {
    "multi_agent_orchestration": {
        "markers": ("agent framework", "meta-harness", "multiple agents", "orchestrate", "sub-agents"),
        "capabilities": ("agent_workflow_route",),
        "validation": ("pytest tests/test_harness_eval.py -q -k agent_workflow_route",),
    },
    "policy_or_sandbox_control": {
        "markers": ("approval", "govern", "policy", "sandbox", "tool limit"),
        "capabilities": ("native_tool_call_policy",),
        "validation": ("pytest tests/test_harness_eval.py -q -k native_tool_call_policy",),
    },
    "provider_configuration_surface": {
        "markers": ("api setting", "api settings", "base url", "model", "provider"),
        "capabilities": ("provider_runtime_preflight",),
        "validation": ("pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",),
    },
    "conversation_state_or_memory": {
        "markers": ("context memory", "conversation", "local memory", "multi-turn", "session", "state"),
        "capabilities": ("local_memory",),
        "validation": ("pytest tests/test_local_memory.py -q",),
    },
    "local_data_grounding": {
        "markers": ("data source", "database", "local data", "official data", "source citation"),
        "capabilities": (),
        "validation": (),
    },
}
SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND = "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane"
SKILL_ROUTE_DISCOVERY_PREACTIVATION_HARNESS_COMMAND = "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
SKILL_ROUTE_DISCOVERY_PROPOSAL_INTERPRETATION_COMMAND = (
    "pytest tests/test_harness_eval.py -q -k proposal_interpretation"
)
PROVIDER_RUNTIME_PREFLIGHT_COMMAND = "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight"
PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND = "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary"
SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS = {
    "documentation": ("docs/skill-route-discovery.md",),
    "config": ("src/blackhole_agent/proposal_synthesis.py",),
    "test": (
        "tests/test_skill_routing.py",
        "tests/test_harness_eval.py",
    ),
    "code_patch": (
        "src/blackhole_agent/skill_routing.py",
        "src/blackhole_agent/harness_eval.py",
    ),
}
SKILL_ROUTE_DISCOVERY_TRIAGE_REASONS = {
    "documentation": "record route lesson and operator acceptance criteria",
    "config": "register bounded route policy or proposal mapping",
    "test": "replay route evidence through local regression coverage",
    "code_patch": "change only local classifier, harness, or controller behavior",
}
SKILL_ROUTE_DISCOVERY_PROFILE_REVIEW_CONTRACTS = {
    "codex_workflow_gate": {
        "recognition_signals": (
            "codex_or_agent_workflow_language",
            "evidence_gate_or_review_ledger",
            "verification_or_coverage_habit",
        ),
        "expected_metadata": (
            "selected_digest_item_ids",
            "body_free_workflow_summary",
            "local_gate_or_test_target",
        ),
        "safe_local_tests": (
            "pytest tests/test_skill_routing.py -q",
            "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
            "pytest tests/test_harness_eval.py -q -k proposal_interpretation",
        ),
        "rejection_conditions": (
            "upstream_workflow_install_requested",
            "url_or_repository_name_used_as_proposal_evidence_ref",
            "readme_claim_treated_as_local_gate_parity",
        ),
    },
    "game_frontend_workflow": {
        "recognition_signals": (
            "threejs_or_browser_game_language",
            "director_or_specialist_skill_bundle",
            "qa_browser_screenshot_or_canvas_validation_language",
        ),
        "expected_metadata": (
            "body_free_game_skill_summary",
            "local_frontend_validation_target",
            "asset_or_provider_boundary_note",
        ),
        "safe_local_tests": (
            "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
            "pytest tests/test_harness_eval.py -q -k rendered_html_artifact_validation",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        ),
        "rejection_conditions": (
            "upstream_scaffold_or_browser_checker_requested",
            "credential_probe_or_provider_launch_requested",
            "asset_generation_requested_without_local_capability_path",
        ),
    },
    "skill_ecosystem_state_handoff": {
        "recognition_signals": (
            "skill_ecosystem_or_multiple_skills",
            "task_memory_profile_or_handoff_language",
            "clarification_or_alignment_gate",
        ),
        "expected_metadata": (
            "body_free_skill_ecosystem_summary",
            "state_retention_and_privacy_boundary",
            "local_memory_or_profile_target_if_any",
        ),
        "safe_local_tests": (
            "pytest tests/test_skill_routing.py -q",
            "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
            "pytest tests/test_local_memory.py -q",
        ),
        "rejection_conditions": (
            "profile_or_memory_write_from_repository_presence",
            "private_context_or_secret_storage_requested",
            "manual_install_or_enable_requested",
        ),
    },
    "generic_skill_workflow": {
        "recognition_signals": (
            "skill_or_workflow_language",
            "public_repository_summary",
        ),
        "expected_metadata": (
            "selected_digest_item_ids_or_frozen_digest_evidence",
            "body_free_repository_summary",
            "local_artifact_target",
        ),
        "safe_local_tests": (
            "pytest tests/test_skill_routing.py -q",
            "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
        ),
        "rejection_conditions": (
            "missing_route_hint",
            "unbounded_lane_requested",
            "runtime_action_requested",
        ),
    },
}
SKILL_ROUTE_DISCOVERY_INSPECTION_EVIDENCE = (
    "selected_digest_item_ids_or_frozen_digest_evidence",
    "body_free_repository_summary",
    "source_lineage_metadata",
)
SKILL_ROUTE_DISCOVERY_INSPECTION_REVIEW = (
    "local_artifact_contract_target",
    "changed_file_review",
    "focused_local_validation",
    "rollback_artifact",
    "review_note",
)
SKILL_ROUTE_DISCOVERY_INSPECTION_BLOCKED_SHORTCUTS = (
    "install_upstream_skill",
    "run_upstream_skill_code",
    "clone_and_run_repository",
    "trust_readme_as_local_parity",
    "export_raw_upstream_body",
)
AGENT_WORKFLOW_REPORT_REQUIRED_SECTIONS = (
    "changed_files",
    "validation",
    "rollback",
    "replay",
    "review_notes",
)


@dataclass(frozen=True)
class HarnessRunSummary:
    """Comparable, body-free summary of one agent run artifact."""

    run_id: str
    harness: str
    variant: str
    model: str | None
    task_hash: str | None
    output_hash: str | None
    quality_score: float | None
    cost_usd: float | None
    elapsed_seconds: float | None
    tool_calls: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    returncode: int | None
    timed_out: bool
    failure_mode: str
    validation_gate: str
    gate_outcome: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "harness": self.harness,
            "variant": self.variant,
            "model": self.model,
            "task_hash": self.task_hash,
            "output_hash": self.output_hash,
            "quality_score": self.quality_score,
            "cost_usd": self.cost_usd,
            "elapsed_seconds": self.elapsed_seconds,
            "tool_calls": self.tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "failure_mode": self.failure_mode,
            "validation_gate": self.validation_gate,
            "gate_outcome": self.gate_outcome,
        }


@dataclass(frozen=True)
class HarnessComparisonReport:
    """Aggregate comparison across harness/model variants for the same task set."""

    suite_name: str
    run_count: int
    privacy: dict[str, Any]
    summaries: list[HarnessRunSummary]
    aggregate_by_variant: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "run_count": self.run_count,
            "privacy": self.privacy,
            "summaries": [summary.to_dict() for summary in self.summaries],
            "aggregate_by_variant": self.aggregate_by_variant,
        }


@dataclass(frozen=True)
class HarnessEvalAssertionResult:
    """One deterministic fixture assertion outcome."""

    path: str
    expected: Any
    actual: Any
    passed: bool
    failure_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "failure_mode": self.failure_mode,
        }


@dataclass(frozen=True)
class HarnessEvalFixtureResult:
    """Structured result for one local behavior fixture."""

    name: str
    source_path: str
    behavior: str
    input_hash: str
    passed: bool
    failure_mode: str
    assertions: list[HarnessEvalAssertionResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "behavior": self.behavior,
            "input_hash": self.input_hash,
            "passed": self.passed,
            "failure_mode": self.failure_mode,
            "assertions": [assertion.to_dict() for assertion in self.assertions],
        }


@dataclass(frozen=True)
class HarnessEvalReport:
    """Controller-readable local eval report for reproducible harness fixtures."""

    suite_name: str
    fixture_count: int
    pass_count: int
    fail_count: int
    results: list[HarnessEvalFixtureResult]
    privacy: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "fixture_count": self.fixture_count,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "results": [result.to_dict() for result in self.results],
            "privacy": self.privacy,
        }


def build_harness_comparison_report(
    artifact_paths: list[Path],
    *,
    suite_name: str = "local-harness-comparison",
) -> HarnessComparisonReport:
    """Build a body-free comparison report from local run artifact JSON files."""

    summaries = [summarize_harness_run(load_json_object(path), source_path=path) for path in artifact_paths]
    return HarnessComparisonReport(
        suite_name=suite_name,
        run_count=len(summaries),
        privacy={
            "body_fields_exported": False,
            "body_field_policy": "prompt/output/stdout/stderr bodies are hashed when present and omitted by default",
            "omitted_body_keys": sorted(BODY_KEYS),
            "privacy_review_gate": PRIVACY_REVIEW_GATE,
            "privacy_review_behavior": "privacy-flagged harness artifacts are summarized without body hashes",
        },
        summaries=summaries,
        aggregate_by_variant=aggregate_harness_summaries(summaries),
    )


def run_local_harness_eval(
    fixture_paths: list[Path],
    *,
    suite_name: str = "local-harness-eval",
) -> HarnessEvalReport:
    """Run local behavior fixtures and emit deterministic pass/fail results.

    Fixtures are JSON objects with:
    - name: stable fixture name
    - behavior: currently "harness_run_summary"
    - input: behavior input object
    - assertions: list of {"path": "field.or.nested.field", "equals": value}

    The report includes hashes of fixture inputs, but never exports raw inputs.
    """

    results = [run_local_harness_fixture(path) for path in sorted(fixture_paths)]
    pass_count = sum(1 for result in results if result.passed)
    return HarnessEvalReport(
        suite_name=suite_name,
        fixture_count=len(results),
        pass_count=pass_count,
        fail_count=len(results) - pass_count,
        results=results,
        privacy={
            "fixture_inputs_exported": False,
            "input_body_policy": "fixture inputs are hashed for reproducibility and omitted from structured results",
            "supported_behaviors": SUPPORTED_LOCAL_HARNESS_BEHAVIORS,
            "safety_boundary_review_flags": sorted(SAFETY_BOUNDARY_REVIEW_FLAGS),
            "offensive_behavior_local_execution": False,
        },
    )


def run_local_harness_fixture(path: Path) -> HarnessEvalFixtureResult:
    fixture = load_json_object(path)
    name = optional_string(fixture.get("name")) or path.stem
    behavior = optional_string(fixture.get("behavior")) or ""
    raw_input = fixture.get("input")
    if not isinstance(raw_input, dict):
        raise ValueError(f"{path} input must be a JSON object")
    assertions = fixture.get("assertions")
    if not isinstance(assertions, list):
        raise ValueError(f"{path} assertions must be a JSON list")

    output = evaluate_harness_behavior(behavior, raw_input, source_path=path)
    assertion_results = [evaluate_fixture_assertion(assertion, output, source_path=path) for assertion in assertions]
    passed = bool(assertion_results) and all(assertion.passed for assertion in assertion_results)
    failure_mode = "none" if passed else "assertion_failed"

    return HarnessEvalFixtureResult(
        name=name,
        source_path=path.as_posix(),
        behavior=behavior,
        input_hash=stable_json_hash(raw_input),
        passed=passed,
        failure_mode=failure_mode,
        assertions=assertion_results,
    )


def evaluate_harness_behavior(behavior: str, raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    if behavior == "agent_harness_eval_lane":
        return evaluate_agent_harness_eval_lane(raw_input, source_path=source_path)
    if behavior == "agent_harness_provider_registration":
        return evaluate_agent_harness_provider_registration(raw_input, source_path=source_path)
    if behavior == "agent_workflow_route":
        return evaluate_agent_workflow_route(raw_input, source_path=source_path)
    if behavior == "harness_run_summary":
        return summarize_harness_run(raw_input, source_path=source_path).to_dict()
    if behavior == "headless_tool_roundtrip":
        return evaluate_headless_tool_roundtrip(raw_input, source_path=source_path)
    if behavior == "mock_e2e_runner_tier":
        return evaluate_mock_e2e_runner_tier(raw_input, source_path=source_path)
    if behavior == "mock_llm_workflow_route":
        return evaluate_mock_llm_workflow_route(raw_input, source_path=source_path)
    if behavior == "native_skill_session_title":
        return evaluate_native_skill_session_title(raw_input, source_path=source_path)
    if behavior == "native_tool_call_policy":
        return evaluate_native_tool_call_policy(raw_input, source_path=source_path)
    if behavior == "push_delivery_path":
        return evaluate_push_delivery_path(raw_input, source_path=source_path)
    if behavior == "provider_runtime_preflight":
        return evaluate_provider_runtime_preflight(raw_input, source_path=source_path)
    if behavior == "provider_runtime_recovery_summary":
        return evaluate_provider_runtime_recovery_summary(raw_input, source_path=source_path)
    if behavior == "proposal_interpretation":
        return adapt_proposal_interpretation_fixture(raw_input, source_path=source_path)
    if behavior == "rendered_html_artifact_validation":
        return evaluate_rendered_html_artifact_validation(raw_input, source_path=source_path)
    if behavior == "skill_route_discovery_lane":
        return evaluate_skill_route_discovery_lane(raw_input, source_path=source_path)
    if behavior == "workspace_changes_panel":
        return evaluate_workspace_changes_panel(raw_input, source_path=source_path)
    raise ValueError(f"{source_path} has unsupported local harness behavior: {behavior}")


def evaluate_agent_harness_provider_registration(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Validate a proposed agent harness provider route without launching it."""

    from blackhole_agent.tool_routing import discover_provider_harnesses

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    providers = raw_input.get("providers")
    providers = providers if isinstance(providers, list) else []
    runtime = raw_input.get("runtime") if isinstance(raw_input.get("runtime"), dict) else {}
    required_provider = optional_string(raw_input.get("required_provider"))
    expected_harness = optional_string(raw_input.get("expected_harness"))
    registration_state = provider_registration_state(raw_input.get("registration_state"))
    available_commands = set(string_list(runtime.get("available_commands")))
    installed_modules = set(string_list(runtime.get("installed_modules")))
    env_keys_present = set(string_list(runtime.get("env_keys_present")))
    environ = {name: "present" for name in env_keys_present}
    platform = optional_string(runtime.get("platform")) or "linux"

    harnesses = [provider_harness_from_mapping(provider) for provider in providers if isinstance(provider, dict)]
    statuses = discover_provider_harnesses(
        harnesses,
        installed_modules=installed_modules,
        available_commands=available_commands,
        environ=environ,
        platform=platform,
    )
    available_statuses = [status for status in statuses if status.available]
    selected = available_statuses[0].harness.name if available_statuses else None
    required_status = next(
        (
            status
            for status in statuses
            if status.harness.provider == required_provider or status.harness.name == required_provider
        ),
        None,
    )
    missing_config_reasons = sorted(
        {
            redact_provider_registration_skip_reason(reason)
            for status in statuses
            for reason in status.skip_reasons
            if reason.startswith(("missing_env:", "missing_dependency:", "missing_optional_extra:"))
        }
    )
    missing_required_config = bool(required_status and not required_status.available and required_status.skip_reasons)
    registration_ready = bool(
        required_status
        and required_status.available
        and (not expected_harness or required_status.harness.name == expected_harness)
    )
    registration_state_blocked = bool(registration_state["blocked"])

    if not statuses:
        route_status = "blocked"
        failure_mode = "no_provider_harnesses_declared"
    elif registration_state_blocked:
        route_status = "blocked"
        failure_mode = registration_state["failure_mode"]
    elif missing_required_config:
        route_status = "blocked"
        failure_mode = "required_provider_config_missing"
    elif required_provider and required_status is None:
        route_status = "blocked"
        failure_mode = "required_provider_not_declared"
    elif expected_harness and selected != expected_harness:
        route_status = "blocked"
        failure_mode = "expected_harness_not_selected"
    elif registration_ready or (not required_provider and selected):
        route_status = "passed"
        failure_mode = "none"
    else:
        route_status = "blocked"
        failure_mode = "no_available_provider_harness"

    return {
        "schema_version": 1,
        "behavior": "agent_harness_provider_registration",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "provider_count": len(statuses),
        "selected_harness": selected,
        "required_provider": required_provider,
        "expected_harness": expected_harness,
        "missing_required_config": missing_required_config,
        "missing_config_reasons": missing_config_reasons,
        "registration_state": registration_state,
        "recovery_hints": provider_registration_recovery_hints(registration_state),
        "statuses": [
            {
                "name": status.harness.name,
                "provider": status.harness.provider,
                "available": status.available,
                "skip_reasons": [redact_provider_registration_skip_reason(reason) for reason in status.skip_reasons],
                "required_env_key_hashes": [stable_text_hash(name) for name in status.harness.required_env],
                "required_commands": list(status.harness.required_commands),
                "required_modules": list(status.harness.required_modules),
            }
            for status in statuses
        ],
        "activation_gate": {
            "controller_surface": "agent_harness_provider_registration",
            "activation_scope": "local_harness_provider_only",
            "decision": "ready_for_local_provider_registration"
            if failure_mode == "none"
            else "blocked_before_activation",
            "reason": failure_mode,
            "local_provider_registration_allowed": failure_mode == "none",
            "provider_runtime_launch_allowed": False,
        },
        "privacy": {
            "env_values_exported": False,
            "env_key_names_exported": False,
            "host_id_exported": False,
            "owner_values_exported": False,
            "provider_launched": False,
        },
    }


def provider_registration_state(value: Any) -> dict[str, Any]:
    """Normalize host registration metadata without exporting host or owner values."""

    state = value if isinstance(value, dict) else {}
    host_id = optional_string(state.get("host_id"))
    existing_owner = optional_string(state.get("existing_owner"))
    authenticated_owner = optional_string(state.get("authenticated_owner"))
    same_owner = bool(existing_owner and authenticated_owner and existing_owner == authenticated_owner)
    owner_mismatch = bool(existing_owner and authenticated_owner and existing_owner != authenticated_owner)
    already_registered = truthy(state.get("already_registered")) or bool(existing_owner)
    registration_completed = truthy(state.get("registration_completed"))
    connection_reported_success = truthy(state.get("connection_reported_success"))

    if owner_mismatch:
        failure_mode = "host_registration_owner_mismatch"
    elif already_registered and not same_owner and not authenticated_owner:
        failure_mode = "host_registration_owner_unknown"
    elif connection_reported_success and not registration_completed:
        failure_mode = "host_registration_incomplete_success_state"
    else:
        failure_mode = "none"

    blocked = failure_mode != "none"
    return {
        "present": bool(state),
        "host_id_present": bool(host_id),
        "host_id_hash": stable_text_hash(host_id) if host_id else None,
        "existing_owner_hash": stable_text_hash(existing_owner) if existing_owner else None,
        "authenticated_owner_hash": stable_text_hash(authenticated_owner) if authenticated_owner else None,
        "owners_match": same_owner if existing_owner and authenticated_owner else None,
        "owner_mismatch": owner_mismatch,
        "already_registered": already_registered,
        "registration_completed": registration_completed,
        "connection_reported_success": connection_reported_success,
        "success_state_allowed": not blocked,
        "blocked": blocked,
        "failure_mode": failure_mode,
        "diagnostic_class": failure_mode,
        "raw_host_id_exported": False,
        "raw_owner_values_exported": False,
    }


def provider_registration_recovery_hints(registration_state: dict[str, Any]) -> list[dict[str, Any]]:
    failure_mode = optional_string(registration_state.get("failure_mode")) or "none"
    if failure_mode == "none":
        return []
    if failure_mode == "host_registration_owner_mismatch":
        action = "refuse registration before reporting connected; reset the stale host id or remove the old host registration"
    elif failure_mode == "host_registration_incomplete_success_state":
        action = (
            "treat incomplete registration as blocked instead of connected and retry only after registration succeeds"
        )
    else:
        action = "verify host ownership metadata before allowing provider registration"
    return [
        {
            "code": failure_mode,
            "scope": "provider_host_registration",
            "severity": "blocker",
            "action": action,
            "host_id_present": bool(registration_state.get("host_id_present")),
            "owner_mismatch": bool(registration_state.get("owner_mismatch")),
            "value_recorded": False,
        }
    ]


def provider_harness_from_mapping(value: dict[str, Any]) -> Any:
    """Build a ProviderHarness from fixture metadata without env values."""

    from blackhole_agent.tool_routing import ProviderHarness

    return ProviderHarness(
        name=optional_string(value.get("name")) or "unnamed-provider-harness",
        provider=optional_string(value.get("provider")) or "unknown",
        priority=int(value.get("priority") or 100),
        enabled=truthy(value.get("enabled", True)),
        required_modules=tuple(string_list(value.get("required_modules"))),
        optional_extra_modules=tuple(string_list(value.get("optional_extra_modules"))),
        required_commands=tuple(string_list(value.get("required_commands"))),
        required_env=tuple(string_list(value.get("required_env"))),
        supported_platforms=tuple(string_list(value.get("supported_platforms"))),
    )


def redact_provider_registration_skip_reason(reason: str) -> str:
    if not reason.startswith("missing_env:"):
        return reason
    _, env_key = reason.split(":", 1)
    return f"missing_env_key_hash:{stable_text_hash(env_key)}"


def evaluate_agent_harness_eval_lane(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Convert public agent-harness evidence into bounded local eval lanes."""

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    evidence_items = raw_input.get("evidence_items") if isinstance(raw_input.get("evidence_items"), list) else []
    records = [item for item in evidence_items if isinstance(item, dict)]
    lane_records: list[dict[str, Any]] = []
    review_notes: list[dict[str, Any]] = []
    unsupported_lanes: list[str] = []
    claim_rows: list[dict[str, Any]] = []
    recognized_count = 0
    detailed_count = 0

    for index, record in enumerate(records, start=1):
        text = agent_harness_eval_record_text(record)
        route_hints = set(string_list(record.get("route_hints")))
        risk_flags = set(string_list(record.get("risk_flags")))
        recognized = AGENT_HARNESS_EVAL_HINT in route_hints or any(
            marker in text for marker in ("agent harness", "benchmark", "eval", "evaluation", "harness")
        )
        if not recognized:
            continue
        recognized_count += 1
        if any(marker in text for marker in AGENT_HARNESS_EVAL_DETAIL_MARKERS):
            detailed_count += 1
        item_id = optional_string(record.get("item_id")) or f"item-{index}"
        source_url = optional_string(record.get("source_url")) or ""
        claim_rows.extend(agent_harness_eval_claim_rows(item_id=item_id, text=text))
        lanes = string_list(record.get("suggested_lanes")) or ["test"]
        allowed_lanes = [lane for lane in lanes if lane in AGENT_HARNESS_EVAL_ALLOWED_LANES]
        rejected_lanes = sorted(set(lanes) - set(AGENT_HARNESS_EVAL_ALLOWED_LANES))
        unsupported_lanes.extend(rejected_lanes)

        boundary_flags = sorted(risk_flags & SAFETY_BOUNDARY_REVIEW_FLAGS)
        if boundary_flags:
            review_notes.append(
                {
                    "item_id": item_id,
                    "risk_flags": boundary_flags,
                    "review_gate": safety_review_gate_for_flags(boundary_flags),
                    "local_eval_activation_allowed": False,
                }
            )
            continue

        for lane in allowed_lanes:
            lane_records.append(
                {
                    "item_id": item_id,
                    "source_url": source_url,
                    "proposal_kind": lane,
                    "route_hint": AGENT_HARNESS_EVAL_HINT,
                    "local_validation_required": True,
                    "runtime_action": "none",
                }
            )

    lanes_bounded = not unsupported_lanes
    runtime_safe = all(lane["runtime_action"] == "none" for lane in lane_records)
    validation_required = all(lane["local_validation_required"] is True for lane in lane_records)
    failure_mode = agent_harness_eval_lane_failure_mode(
        recognized_count=recognized_count,
        lane_count=len(lane_records),
        review_only_count=len(review_notes),
        detailed_count=detailed_count,
        lanes_bounded=lanes_bounded,
        runtime_safe=runtime_safe,
        validation_required=validation_required,
    )
    route_status = (
        "passed"
        if failure_mode == "none"
        else "review_only"
        if failure_mode == "review_only_safety_boundary"
        else "blocked"
    )
    activation_gate = agent_harness_eval_activation_gate(failure_mode)
    activation_lanes = build_agent_harness_eval_activation_lanes(
        lane_records,
        activation_allowed=activation_gate["local_eval_activation_allowed"] is True,
        failure_mode=failure_mode,
    )

    return {
        "schema_version": 1,
        "behavior": "agent_harness_eval_lane",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "evidence_strength": {
            "record_count": len(records),
            "recognized_harness_record_count": recognized_count,
            "specific_detail_count": detailed_count,
            "activation_evidence_sufficient": detailed_count > 0 and bool(lane_records),
        },
        "lane_map": {
            "allowed_proposal_kinds": list(AGENT_HARNESS_EVAL_ALLOWED_LANES),
            "proposal_lane_count": len(lane_records),
            "proposal_kinds": sorted({lane["proposal_kind"] for lane in lane_records}),
            "lanes_bounded": lanes_bounded,
            "unsupported_lanes": sorted(dict.fromkeys(unsupported_lanes)),
            "lane_runtime_safe": runtime_safe,
            "local_validation_required": validation_required,
        },
        "activation_gate": activation_gate,
        "activation_lanes": activation_lanes,
        "claim_evaluation": build_agent_harness_eval_claim_evaluation(claim_rows),
        "review_notes": review_notes,
        "proposal_lanes": [
            {
                "item_id": lane["item_id"],
                "proposal_kind": lane["proposal_kind"],
                "route_hint": lane["route_hint"],
                "runtime_action": lane["runtime_action"],
                "local_validation_required": lane["local_validation_required"],
                "source_url_hash": stable_text_hash(lane["source_url"]) if lane["source_url"] else None,
            }
            for lane in lane_records
        ],
        "privacy": {
            "raw_source_urls_exported": False,
            "raw_evidence_bodies_exported": False,
            "source_urls_hashed": True,
            "runtime_actions_executed": False,
            "offensive_behavior_local_execution": False,
        },
    }


def agent_harness_eval_record_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("name", "title", "summary", "evidence_summary", "relevance_reason", "recommended_action"):
        value = record.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("topics", "route_hints", "suggested_lanes"):
        value = record.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def agent_harness_eval_claim_rows(*, item_id: str, text: str) -> list[dict[str, Any]]:
    """Extract body-free behavior claims and map them to existing local checks."""

    rows: list[dict[str, Any]] = []
    for claim_id, pattern in AGENT_HARNESS_EVAL_CLAIM_PATTERNS.items():
        markers = tuple(str(marker) for marker in pattern.get("markers", ()))
        if not any(marker in text for marker in markers):
            continue
        capabilities = tuple(str(capability) for capability in pattern.get("capabilities", ()))
        validation = tuple(str(command) for command in pattern.get("validation", ()))
        rows.append(
            {
                "item_id": item_id,
                "claim_id": claim_id,
                "mapped": bool(capabilities),
                "local_capabilities": list(capabilities),
                "required_validation": list(validation),
                "status": "mapped_to_existing_capability" if capabilities else "unmapped_evidence_only",
                "runtime_action": "none",
                "external_agent_activation_allowed": False,
            }
        )
    return rows


def build_agent_harness_eval_claim_evaluation(claim_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize claim mapping without exporting upstream bodies or URLs."""

    mapped_count = sum(1 for row in claim_rows if row["mapped"])
    unmapped_count = len(claim_rows) - mapped_count
    claim_ids = sorted({str(row["claim_id"]) for row in claim_rows})
    mapped_claim_ids = sorted({str(row["claim_id"]) for row in claim_rows if row["mapped"]})
    unmapped_claim_ids = sorted({str(row["claim_id"]) for row in claim_rows if not row["mapped"]})
    return {
        "controller_surface": "agent_harness_claim_mapping",
        "claim_count": len(claim_rows),
        "mapped_claim_count": mapped_count,
        "unmapped_claim_count": unmapped_count,
        "claim_ids": claim_ids,
        "mapped_claim_ids": mapped_claim_ids,
        "unmapped_claim_ids": unmapped_claim_ids,
        "mapping_status": "all_mapped" if claim_rows and not unmapped_count else "partial" if claim_rows else "empty",
        "local_validation_required": mapped_count > 0,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "raw_claim_bodies_exported": False,
        "rows": claim_rows,
    }


def safety_review_gate_for_flags(flags: list[str]) -> str:
    if "offensive-behavior" in flags:
        return "offensive-behavior-human-review"
    if "privacy-leakage" in flags:
        return "privacy-leakage-human-review"
    return "safety-boundary-human-review"


def agent_harness_eval_lane_failure_mode(
    *,
    recognized_count: int,
    lane_count: int,
    review_only_count: int,
    detailed_count: int,
    lanes_bounded: bool,
    runtime_safe: bool,
    validation_required: bool,
) -> str:
    if not runtime_safe:
        return "runtime_action_requested"
    if not validation_required:
        return "local_validation_not_required"
    if not lanes_bounded:
        return "unbounded_agent_harness_eval_lane"
    if lane_count:
        if detailed_count == 0:
            return "weak_harness_evidence"
        return "none"
    if review_only_count:
        return "review_only_safety_boundary"
    if not recognized_count:
        return "no_agent_harness_eval_evidence"
    return "no_agent_harness_eval_lanes"


def agent_harness_eval_activation_gate(failure_mode: str) -> dict[str, Any]:
    if failure_mode == "none":
        decision = "ready_for_local_eval_activation"
        allowed = True
    elif failure_mode == "review_only_safety_boundary":
        decision = "review_safety_boundary_before_activation"
        allowed = False
    elif failure_mode == "weak_harness_evidence":
        decision = "review_weak_evidence_before_activation"
        allowed = False
    else:
        decision = "blocked_before_activation"
        allowed = False
    return {
        "controller_surface": "agent_harness_eval_lane",
        "activation_scope": "local_eval_only",
        "decision": decision,
        "reason": failure_mode,
        "local_eval_activation_allowed": allowed,
        "external_harness_execution_allowed": False,
    }


def build_agent_harness_eval_activation_lanes(
    proposal_lanes: list[dict[str, Any]],
    *,
    activation_allowed: bool,
    failure_mode: str,
) -> list[dict[str, Any]]:
    validation_command = "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
    grouped: dict[str, list[dict[str, Any]]] = {}
    for lane in proposal_lanes:
        grouped.setdefault(str(lane.get("proposal_kind") or ""), []).append(lane)
    blockers = [] if activation_allowed else [failure_mode or "activation_gate_not_ready"]
    return [
        {
            "proposal_kind": proposal_kind,
            "item_ids": sorted({str(lane.get("item_id") or "") for lane in lanes}),
            "required_validation": [validation_command],
            "activation_ready": activation_allowed,
            "activation_blockers": blockers,
            "runtime_action": "none",
            "external_harness_execution_allowed": False,
        }
        for proposal_kind, lanes in sorted(grouped.items())
        if proposal_kind
    ]


def evaluate_headless_tool_roundtrip(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Validate that headless function_call events enter the local tool dispatch lane."""

    from blackhole_agent.tool_routing import build_headless_function_call_dispatch_report

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    raw_events = raw_input.get("events") if isinstance(raw_input.get("events"), list) else []
    events = [event for event in raw_events if isinstance(event, dict)]
    raw_tools = raw_input.get("tools") if isinstance(raw_input.get("tools"), list) else []
    descriptors = [tool_descriptor_from_mapping(tool) for tool in raw_tools if isinstance(tool, dict)]
    dispatch = build_headless_function_call_dispatch_report(events, descriptors)

    if dispatch["function_call_event_count"] == 0:
        failure_mode = "no_function_call_events"
    elif dispatch["missing_handler_count"]:
        failure_mode = "missing_tool_handler"
    elif dispatch["blocked_count"]:
        failure_mode = "tool_route_blocked"
    elif not dispatch["all_function_calls_dispatched"]:
        failure_mode = "function_call_not_dispatched"
    else:
        failure_mode = "none"

    return {
        "schema_version": 1,
        "behavior": "headless_tool_roundtrip",
        "task_id": task_id,
        "route_status": "passed" if failure_mode == "none" else "failed",
        "failure_mode": failure_mode,
        "dispatch": dispatch,
        "activation_gate": {
            "controller_surface": "headless_tool_roundtrip",
            "activation_scope": "local_harness_dispatch_only",
            "decision": "ready_for_headless_tool_roundtrip" if failure_mode == "none" else "blocked_before_activation",
            "reason": failure_mode,
            "local_dispatch_allowed": failure_mode == "none",
            "tool_execution_allowed": False,
        },
        "privacy": {
            "raw_events_exported": False,
            "raw_tool_arguments_exported": False,
            "tools_executed": False,
        },
    }


def tool_descriptor_from_mapping(value: dict[str, Any]) -> Any:
    """Build a ToolDescriptor from fixture metadata without callable execution."""

    from blackhole_agent.tool_routing import ToolDescriptor

    parameters = value.get("parameters") if isinstance(value.get("parameters"), dict) else None
    return ToolDescriptor(
        name=optional_string(value.get("name")) or "unnamed-tool",
        description=optional_string(value.get("description")) or "",
        parameters=parameters,
        provider=optional_string(value.get("provider")) or "function",
        session_id=optional_string(value.get("session_id")),
        tool_type=optional_string(value.get("type") or value.get("tool_type")),
        callable_path=optional_string(value.get("callable") or value.get("callable_path")),
        policy_name=optional_string(value.get("policy_name")),
        risk_flags=tuple(string_list(value.get("risk_flags"))),
    )


def evaluate_skill_route_discovery_lane(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Validate external skill-route evidence as bounded local lanes only."""

    from blackhole_agent.skill_routing import (
        SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
        build_skill_route_discovery_proposal_lane_map,
        build_skill_route_discovery_registry,
        build_skill_route_discovery_registry_from_evidence_items,
        build_skill_route_discovery_registry_from_summaries,
    )

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    source_kind = optional_string(raw_input.get("source_kind")) or "evidence_items"
    if source_kind == "evidence_items":
        evidence_items = raw_input.get("evidence_items")
        evidence_items = evidence_items if isinstance(evidence_items, list) else []
        registry = build_skill_route_discovery_registry_from_evidence_items(evidence_items)
    elif source_kind == "summaries":
        summaries = raw_input.get("summaries")
        summaries = summaries if isinstance(summaries, list) else []
        registry = build_skill_route_discovery_registry_from_summaries(summaries)
    elif source_kind == "candidates":
        candidates = raw_input.get("candidates")
        candidates = candidates if isinstance(candidates, list) else []
        registry = build_skill_route_discovery_registry(candidates)
    else:
        registry = build_skill_route_discovery_registry([])

    lane_map = build_skill_route_discovery_proposal_lane_map(registry)
    proposal_lanes = lane_map["proposal_lanes"]
    summary_signal_audit = skill_route_discovery_summary_signal_audit(
        source_kind=source_kind,
        registry=registry,
        lane_map=lane_map,
    )
    source_lineage = skill_route_discovery_source_lineage_summary(registry)
    lane_runtime_safe = all(lane.get("runtime_action") == "none" for lane in proposal_lanes)
    validation_required = all(lane.get("local_validation_required") is True for lane in proposal_lanes)
    proposal_kinds = sorted({str(lane.get("proposal_kind") or "") for lane in proposal_lanes})
    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    lanes_bounded = set(proposal_kinds) <= allowed_lanes
    evidence_strength = skill_route_discovery_evidence_strength(raw_input, source_kind=source_kind)
    uncertainty = skill_route_discovery_lane_uncertainty(proposal_lanes, evidence_strength=evidence_strength)
    provider_runtime_replay_sample = skill_route_discovery_provider_runtime_replay_sample(
        raw_input,
        source_path=source_path,
    )

    failure_mode = skill_route_discovery_lane_failure_mode(
        proposal_lane_count=int(lane_map["proposal_lane_count"]),
        rejected_candidate_count=int(lane_map["rejected_candidate_count"]),
        downgraded_candidate_count=int(lane_map["downgraded_candidate_count"]),
        lane_runtime_safe=lane_runtime_safe,
        validation_required=validation_required,
        lanes_bounded=lanes_bounded,
        weak_generic_evidence_only=evidence_strength["tier"] == "weak_generic_upstream_movement",
    )
    if (
        failure_mode == "none"
        and provider_runtime_replay_sample.get("provided") is True
        and provider_runtime_replay_sample.get("blocked_before_local_replay") is True
    ):
        failure_mode = "provider_runtime_replay_not_ready"
    route_status = (
        "passed"
        if failure_mode == "none"
        else "degraded"
        if failure_mode == "unsupported_lanes_downgraded"
        else "blocked"
    )
    activation_gate = skill_route_discovery_activation_gate(failure_mode)
    recovery_hints = skill_route_discovery_recovery_hints(
        failure_mode,
        evidence_strength=evidence_strength,
        lane_map=lane_map,
    )
    recovery_hints.extend(skill_route_discovery_provider_runtime_replay_recovery_hints(provider_runtime_replay_sample))
    discovery_checklist = build_skill_route_discovery_checklist(proposal_lanes)
    activation_lanes = build_skill_route_discovery_activation_lanes(
        proposal_lanes,
        activation_allowed=activation_gate["local_proposal_activation_allowed"] is True,
        failure_mode=failure_mode,
        recovery_hints=recovery_hints,
        local_artifact_proofs=skill_route_discovery_local_artifact_proofs(raw_input),
        provider_runtime_replay_sample=provider_runtime_replay_sample,
    )
    preactivation_trust_boundary = skill_route_discovery_preactivation_trust_boundary(
        proposal_lanes,
        activation_lanes,
    )
    if preactivation_trust_boundary["status"] != "passed" and failure_mode == "none":
        failure_mode = "preactivation_trust_boundary_failed"
        route_status = "blocked"
        activation_gate = skill_route_discovery_activation_gate(failure_mode)
        recovery_hints = skill_route_discovery_recovery_hints(
            failure_mode,
            evidence_strength=evidence_strength,
            lane_map=lane_map,
        )
        activation_lanes = build_skill_route_discovery_activation_lanes(
            proposal_lanes,
            activation_allowed=False,
            failure_mode=failure_mode,
            recovery_hints=recovery_hints,
            local_artifact_proofs=skill_route_discovery_local_artifact_proofs(raw_input),
            provider_runtime_replay_sample=provider_runtime_replay_sample,
        )
        preactivation_trust_boundary = skill_route_discovery_preactivation_trust_boundary(
            proposal_lanes,
            activation_lanes,
        )
    supervisor_readiness = skill_route_discovery_supervisor_readiness(
        route_status=route_status,
        failure_mode=failure_mode,
        activation_gate=activation_gate,
        activation_lanes=activation_lanes,
        preactivation_trust_boundary=preactivation_trust_boundary,
        recovery_hints=recovery_hints,
        source_lineage=source_lineage,
    )
    implementation_intake_preflight = skill_route_discovery_implementation_intake_preflight(
        activation_lanes,
        preactivation_trust_boundary=preactivation_trust_boundary,
    )
    operator_handoff = skill_route_discovery_operator_handoff(
        activation_lanes=activation_lanes,
        implementation_intake_preflight=implementation_intake_preflight,
        supervisor_readiness=supervisor_readiness,
        source_lineage=source_lineage,
        recovery_hints=recovery_hints,
    )
    local_lane_intake = skill_route_discovery_local_lane_intake(
        proposal_lanes=proposal_lanes,
        activation_lanes=activation_lanes,
        activation_gate=activation_gate,
        evidence_strength=evidence_strength,
        source_lineage=source_lineage,
    )
    evidence_lane_matrix = skill_route_discovery_evidence_lane_matrix(
        registry=registry,
        lane_map=lane_map,
        activation_gate=activation_gate,
        evidence_strength=evidence_strength,
        source_lineage=source_lineage,
    )
    candidate_lane_intake = skill_route_discovery_candidate_lane_intake(
        lane_map=lane_map,
        activation_gate=activation_gate,
        evidence_strength=evidence_strength,
        source_lineage=source_lineage,
    )
    term_route_review = skill_route_discovery_term_route_review(
        candidate_lane_intake=candidate_lane_intake,
        activation_gate=activation_gate,
    )
    provider_runtime_diagnostic_panel = skill_route_discovery_provider_runtime_diagnostic_panel(
        activation_lanes=activation_lanes,
        recovery_hints=recovery_hints,
        preactivation_trust_boundary=preactivation_trust_boundary,
    )
    route_triage_plan = skill_route_discovery_route_triage_plan(
        proposal_lanes=proposal_lanes,
        activation_lanes=activation_lanes,
        activation_gate=activation_gate,
        evidence_strength=evidence_strength,
        source_lineage=source_lineage,
    )
    route_profile_review = skill_route_discovery_route_profile_review(
        raw_input=raw_input,
        proposal_lanes=proposal_lanes,
        source_lineage=source_lineage,
        evidence_strength=evidence_strength,
    )
    activity_signal_panel = skill_route_discovery_activity_signal_panel(
        proposal_lanes=proposal_lanes,
        activation_gate=activation_gate,
        evidence_strength=evidence_strength,
        source_lineage=source_lineage,
    )
    generic_validation_prompt = skill_route_discovery_generic_validation_prompt(
        activity_signal_panel=activity_signal_panel,
        activation_gate=activation_gate,
        evidence_strength=evidence_strength,
    )
    operator_recovery_plan = skill_route_discovery_operator_recovery_plan(
        route_status=route_status,
        failure_mode=failure_mode,
        activation_gate=activation_gate,
        recovery_hints=recovery_hints,
        preactivation_trust_boundary=preactivation_trust_boundary,
    )
    activation_manifest = skill_route_discovery_activation_manifest(
        proposal_lanes=proposal_lanes,
        activation_lanes=activation_lanes,
        operator_handoff=operator_handoff,
        source_lineage=source_lineage,
        recovery_hints=recovery_hints,
    )
    preactivation_lane_selection = skill_route_discovery_preactivation_lane_selection(
        route_profile_review=route_profile_review,
        activation_manifest=activation_manifest,
        candidate_lane_intake=candidate_lane_intake,
    )
    route_discovery_catalog = skill_route_discovery_route_discovery_catalog(
        raw_input=raw_input,
        candidate_lane_intake=candidate_lane_intake,
        route_profile_review=route_profile_review,
        preactivation_lane_selection=preactivation_lane_selection,
        provider_runtime_replay_sample=provider_runtime_replay_sample,
    )
    validation_lane_plan = skill_route_discovery_validation_lane_plan(
        raw_input=raw_input,
        route_discovery_catalog=route_discovery_catalog,
    )
    current_action = skill_route_discovery_current_action(validation_lane_plan=validation_lane_plan)
    domain_validation_probe = skill_route_discovery_domain_validation_probe(
        validation_lane_plan=validation_lane_plan,
    )
    profile_validation_replay = skill_route_discovery_profile_validation_replay(
        validation_lane_plan=validation_lane_plan,
    )
    capability_window_completion = skill_route_discovery_capability_window_completion(
        raw_input=raw_input,
        route_status=route_status,
        failure_mode=failure_mode,
        route_profile_review=route_profile_review,
        activation_manifest=activation_manifest,
        candidate_lane_intake=candidate_lane_intake,
        operator_handoff=operator_handoff,
        supervisor_readiness=supervisor_readiness,
        validation_lane_plan=validation_lane_plan,
        profile_validation_replay=profile_validation_replay,
        provider_runtime_diagnostic_panel=provider_runtime_diagnostic_panel,
        provider_runtime_replay_sample=provider_runtime_replay_sample,
    )

    registry_summary = {
        "registry_status": registry["registry_status"],
        "candidate_count": registry["candidate_count"],
        "enabled_candidate_count": registry["enabled_candidate_count"],
        "invalid_candidate_count": registry["invalid_candidate_count"],
        "executable_skill_count": registry["executable_skill_count"],
    }
    if int(registry.get("duplicate_summary_count") or 0):
        registry_summary["duplicate_summary_count"] = registry["duplicate_summary_count"]
    for registry_count_key in ("summary_count", "ignored_summary_count", "duplicate_summary_count"):
        if registry_count_key in registry:
            registry_summary[registry_count_key] = int(registry.get(registry_count_key) or 0)

    return {
        "schema_version": 1,
        "behavior": "skill_route_discovery_lane",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "source_kind": source_kind,
        "registry": registry_summary,
        "lane_map": {
            "source_registry_status": lane_map["source_registry_status"],
            "candidate_count": lane_map["candidate_count"],
            "proposal_lane_count": lane_map["proposal_lane_count"],
            "rejected_candidate_count": lane_map["rejected_candidate_count"],
            "downgraded_candidate_count": lane_map["downgraded_candidate_count"],
            "route_profile_catalog": lane_map["route_profile_catalog"],
            "proposal_kinds": proposal_kinds,
            "lanes_bounded": lanes_bounded,
            "lane_runtime_safe": lane_runtime_safe,
            "local_validation_required": validation_required,
            "uncertainty_reasons": uncertainty["reasons"],
        },
        "evidence_strength": evidence_strength,
        "source_lineage": source_lineage,
        "uncertainty": uncertainty,
        "activation_gate": activation_gate,
        "diagnostics": {
            "failure_mode": failure_mode,
            "evidence_tier": evidence_strength["tier"],
            "candidate_count": lane_map["candidate_count"],
            "proposal_lane_count": lane_map["proposal_lane_count"],
            "rejected_candidate_count": lane_map["rejected_candidate_count"],
            "downgraded_candidate_count": lane_map["downgraded_candidate_count"],
            "uncertainty_reasons": uncertainty["reasons"],
            "body_free": True,
            "source_lineage_mode": source_lineage["lineage_mode"],
        },
        "recovery_hints": recovery_hints,
        "operator_recovery_plan": operator_recovery_plan,
        "provider_runtime_replay_sample": provider_runtime_replay_sample,
        "provider_runtime_diagnostic_panel": provider_runtime_diagnostic_panel,
        "preactivation_trust_boundary": preactivation_trust_boundary,
        "implementation_intake_preflight": implementation_intake_preflight,
        "local_lane_intake": local_lane_intake,
        "summary_signal_audit": summary_signal_audit,
        "candidate_lane_intake": candidate_lane_intake,
        "term_route_review": term_route_review,
        "evidence_lane_matrix": evidence_lane_matrix,
        "route_triage_plan": route_triage_plan,
        "route_profile_review": route_profile_review,
        "activity_signal_panel": activity_signal_panel,
        "generic_validation_prompt": generic_validation_prompt,
        "preactivation_lane_selection": preactivation_lane_selection,
        "route_discovery_catalog": route_discovery_catalog,
        "validation_lane_plan": validation_lane_plan,
        "current_action": current_action,
        "domain_validation_probe": domain_validation_probe,
        "profile_validation_replay": profile_validation_replay,
        "activation_manifest": activation_manifest,
        "capability_window_completion": capability_window_completion,
        "supervisor_readiness": supervisor_readiness,
        "operator_handoff": operator_handoff,
        "activation_lanes": activation_lanes,
        "discovery_checklist": discovery_checklist,
        "proposal_lanes": [
            {
                "candidate_name": str(lane.get("candidate_name") or ""),
                "discovery_event_kind": str(lane.get("discovery_event_kind") or "unknown"),
                "discovery_event_effect": str(lane.get("discovery_event_effect") or "record_only"),
                "proposal_kind": str(lane.get("proposal_kind") or ""),
                "route_hint": str(lane.get("route_hint") or ""),
                "status": str(lane.get("status") or ""),
                "runtime_action": str(lane.get("runtime_action") or ""),
                "route_profiles": string_list(lane.get("route_profiles")),
                "matched_route_terms": string_list(lane.get("matched_route_terms")),
                "local_validation_required": lane.get("local_validation_required") is True,
                "evidence_url_count": len(lane.get("evidence_urls") or []),
                "evidence_url_hashes": [stable_text_hash(str(url)) for url in lane.get("evidence_urls") or []],
                "evidence_item_ids": [str(item_id) for item_id in lane.get("evidence_item_ids") or []],
                "uncertainty": str(lane.get("uncertainty") or ""),
                "uncertainty_reasons": [str(reason) for reason in lane.get("uncertainty_reasons") or []],
            }
            for lane in proposal_lanes
        ],
        "privacy": {
            "raw_source_urls_exported": False,
            "source_urls_hashed": True,
            "raw_evidence_urls_exported": False,
            "evidence_urls_hashed": True,
            "raw_related_source_urls_exported": False,
            "runtime_actions_executed": False,
        },
    }


def skill_route_discovery_lane_uncertainty(
    proposal_lanes: list[dict[str, Any]],
    *,
    evidence_strength: dict[str, Any],
) -> dict[str, Any]:
    """Summarize proposal-lane uncertainty without exporting raw evidence."""

    reasons: list[str] = []
    for lane in proposal_lanes:
        lane_reasons = lane.get("uncertainty_reasons")
        if isinstance(lane_reasons, list):
            reasons.extend(str(reason) for reason in lane_reasons if str(reason).strip())

    evidence_tier = str(evidence_strength.get("tier") or "")
    if evidence_tier in {"empty", "weak_generic_upstream_movement"}:
        reasons.append("missing_detail_risk")
    if evidence_strength.get("corroboration_required_for_generic_upstream_movement") is True:
        reasons.append("generic_upstream_movement_requires_local_corroboration")

    reasons = list(dict.fromkeys(reasons))
    missing_detail_risk = "missing_detail_risk" in reasons or evidence_tier in {
        "empty",
        "weak_generic_upstream_movement",
    }
    return {
        "body_free": True,
        "missing_detail_risk": missing_detail_risk,
        "reasons": reasons,
        "message": skill_route_discovery_uncertainty_message(reasons),
    }


def skill_route_discovery_uncertainty_message(reasons: list[str]) -> str:
    if "missing_detail_risk" in reasons:
        return (
            "Skill-route evidence has missing_detail_risk; activate only bounded local documentation, config, "
            "test, or code_patch lanes after validation."
        )
    if "fork_or_mirror_lineage_collapsed" in reasons:
        return "Fork or mirror skill evidence was collapsed and does not add independent activation pressure."
    if reasons:
        return "Skill-route evidence is external and unvalidated; proposal lanes require local validation before activation."
    return "Skill-route evidence is bounded and locally validated before activation."


def skill_route_discovery_summary_signal_audit(
    *,
    source_kind: str,
    registry: dict[str, Any],
    lane_map: dict[str, Any],
) -> dict[str, Any]:
    """Expose summary-derived route signals before local lane activation."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    if source_kind != "summaries":
        return {
            "controller_surface": "skill_route_discovery_summary_signal_audit",
            "status": "not_applicable",
            "source_kind": source_kind,
            "summary_count": 0,
            "accepted_summary_count": 0,
            "ignored_summary_count": 0,
            "duplicate_summary_count": 0,
            "rows": [],
            "diagnostics": [],
            "local_validation_required": True,
            "body_free": True,
            "runtime_action_allowed": False,
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "raw_source_urls_exported": False,
            "raw_upstream_body_exported": False,
        }

    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    inventory = lane_map.get("candidate_lane_inventory")
    inventory = inventory if isinstance(inventory, list) else []
    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for item in inventory:
        if not isinstance(item, dict):
            continue
        proposal_kinds = [
            lane
            for lane in string_list(item.get("proposal_kinds"))
            if lane in allowed_lanes
        ]
        route_profiles = string_list(item.get("route_profiles"))
        matched_route_terms = string_list(item.get("matched_route_terms"))
        row_diagnostics: list[str] = []
        if not proposal_kinds:
            row_diagnostics.append("proposal_kinds_missing")
        if not route_profiles:
            row_diagnostics.append("route_profiles_missing")
        if not matched_route_terms:
            row_diagnostics.append("matched_route_terms_missing")
        if str(item.get("runtime_action") or "none") != "none":
            row_diagnostics.append("runtime_action_requested")
        if item.get("local_validation_required") is not True:
            row_diagnostics.append("local_validation_not_required")
        for diagnostic in row_diagnostics:
            diagnostics.append(f"{stable_text_hash(str(item.get('candidate_name') or ''))}:{diagnostic}")

        rows.append(
            {
                "candidate_name_hash": stable_text_hash(str(item.get("candidate_name") or "")),
                "candidate_source_hash": stable_text_hash(str(item.get("source_url") or "")),
                "proposal_kinds": proposal_kinds,
                "route_profiles": route_profiles,
                "matched_route_terms": matched_route_terms,
                "discovery_event_kind": str(item.get("discovery_event_kind") or "unknown"),
                "discovery_event_effect": str(item.get("discovery_event_effect") or "record_only"),
                "evidence_item_id_count": len(string_list(item.get("evidence_item_ids"))),
                "evidence_url_hashes": [
                    stable_text_hash(url) for url in string_list(item.get("evidence_urls"))
                ],
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "raw_source_url_exported": False,
                "raw_upstream_body_exported": False,
                "diagnostics": row_diagnostics,
            }
        )

    summary_count = int(registry.get("summary_count") or 0)
    ignored_summary_count = int(registry.get("ignored_summary_count") or 0)
    duplicate_summary_count = int(registry.get("duplicate_summary_count") or 0)
    accepted_summary_count = int(lane_map.get("candidate_count") or 0)
    if summary_count and accepted_summary_count + ignored_summary_count + duplicate_summary_count != summary_count:
        diagnostics.append("summary_intake_counts_do_not_reconcile")

    if rows and not diagnostics:
        status = "ready"
        decision = "summary_signals_bound_to_local_lanes"
    elif rows:
        status = "review"
        decision = "repair_summary_signal_audit_before_activation"
    else:
        status = "blocked"
        decision = "no_summary_signals_accepted"

    return {
        "controller_surface": "skill_route_discovery_summary_signal_audit",
        "status": status,
        "decision": decision,
        "source_kind": source_kind,
        "summary_count": summary_count,
        "accepted_summary_count": accepted_summary_count,
        "ignored_summary_count": ignored_summary_count,
        "duplicate_summary_count": duplicate_summary_count,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "rows": rows,
        "diagnostics": sorted(dict.fromkeys(diagnostics)),
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_recovery_hints(
    failure_mode: str,
    *,
    evidence_strength: dict[str, Any],
    lane_map: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return body-free recovery hints for blocked or degraded skill-route evidence."""

    if failure_mode == "none":
        return []

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    common = {
        "scope": "skill_route_discovery_lane",
        "required_validation": validation_commands,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "value_recorded": False,
    }
    if failure_mode == "weak_generic_upstream_evidence":
        return [
            {
                **common,
                "code": "skill_route_sparse_upstream_movement",
                "safe_action": (
                    "Add a focused local corroboration record or fixture before promoting this "
                    "repository movement into documentation, config, test, or code_patch work."
                ),
                "evidence_tier": str(evidence_strength.get("tier") or ""),
                "local_corroborating_signal_count": int(evidence_strength.get("local_corroborating_signal_count") or 0),
            }
        ]
    if failure_mode == "unsupported_lanes_downgraded":
        return [
            {
                **common,
                "code": "skill_route_unsupported_lanes_downgraded",
                "safe_action": (
                    "Review downgraded lanes and keep only documentation, config, test, or code_patch "
                    "before local proposal activation."
                ),
                "downgraded_candidate_count": int(lane_map.get("downgraded_candidate_count") or 0),
            }
        ]
    if failure_mode == "rejected_candidates_present":
        return [
            {
                **common,
                "code": "skill_route_rejected_candidates_present",
                "safe_action": (
                    "Remove actionful, unsafe, private, or malformed candidate metadata and replay "
                    "the local harness before activation."
                ),
                "rejected_candidate_count": int(lane_map.get("rejected_candidate_count") or 0),
            }
        ]
    if failure_mode == "preactivation_trust_boundary_failed":
        return [
            {
                **common,
                "code": "skill_route_preactivation_trust_boundary_failed",
                "safe_action": (
                    "Regenerate activation lanes from the disabled registry and rerun the local "
                    "preactivation harness checks."
                ),
            }
        ]
    return [
        {
            **common,
            "code": f"skill_route_{failure_mode}",
            "safe_action": "Inspect body-free diagnostics, correct the local fixture metadata, and replay validation.",
        }
    ]


def skill_route_discovery_operator_recovery_plan(
    *,
    route_status: str,
    failure_mode: str,
    activation_gate: dict[str, Any],
    recovery_hints: list[dict[str, Any]],
    preactivation_trust_boundary: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact body-free recovery plan for skill-route diagnostics."""

    replay_commands = skill_route_discovery_preactivation_validation_commands()
    recovery_steps = [
        {
            "code": str(hint.get("code") or ""),
            "scope": str(hint.get("scope") or "skill_route_discovery_lane"),
            "safe_action": str(hint.get("safe_action") or ""),
            "required_validation": string_list(hint.get("required_validation")) or replay_commands,
            "raw_evidence_exported": False,
            "raw_source_urls_exported": False,
            "value_recorded": False,
        }
        for hint in recovery_hints
        if isinstance(hint, dict) and str(hint.get("code") or "")
    ]
    recovery_hint_codes = [step["code"] for step in recovery_steps]
    activation_decision = str(activation_gate.get("decision") or "")
    trust_boundary_passed = preactivation_trust_boundary.get("status") == "passed"

    if route_status == "passed" and not recovery_steps and trust_boundary_passed:
        decision = "ready_for_local_replay"
        next_action = "run_skill_route_replay_before_promotion"
        recovery_required = False
    elif route_status == "degraded":
        decision = "review_recovery_before_local_replay"
        next_action = "review_recovery_steps_then_replay_skill_route_lane"
        recovery_required = True
    else:
        decision = "blocked_recovery_required"
        next_action = "resolve_recovery_steps_then_replay_skill_route_lane"
        recovery_required = True

    return {
        "controller_surface": "skill_route_discovery_operator_recovery_plan",
        "decision": decision,
        "reason": "none" if not recovery_required else failure_mode,
        "route_status": route_status,
        "activation_decision": activation_decision,
        "trust_boundary_passed": trust_boundary_passed,
        "recovery_required": recovery_required,
        "next_action": next_action,
        "replay_commands": replay_commands,
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "recovery_step_count": len(recovery_steps),
        "recovery_hint_codes": recovery_hint_codes,
        "recovery_hint_code_hashes": [stable_text_hash(code) for code in recovery_hint_codes],
        "recovery_steps": recovery_steps,
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


def skill_route_discovery_source_lineage_summary(registry: dict[str, Any]) -> dict[str, Any]:
    """Summarize external source lineage without exporting raw URLs."""

    candidates = registry.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    source_url_hashes: list[str] = []
    related_source_url_hashes: list[str] = []
    evidence_item_id_count = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_url = str(candidate.get("source_url") or "")
        if source_url:
            source_url_hashes.append(stable_text_hash(source_url))
        related_source_urls = candidate.get("related_source_urls")
        if isinstance(related_source_urls, list):
            related_source_url_hashes.extend(
                stable_text_hash(str(url)) for url in related_source_urls if str(url).strip()
            )
        evidence_item_ids = candidate.get("evidence_item_ids")
        if isinstance(evidence_item_ids, list):
            evidence_item_id_count += len([item_id for item_id in evidence_item_ids if str(item_id).strip()])

    duplicate_summary_count = int(registry.get("duplicate_summary_count") or 0)
    unique_source_hashes = sorted(dict.fromkeys(source_url_hashes))
    unique_related_hashes = sorted(dict.fromkeys(related_source_url_hashes))
    fork_or_mirror_lineage_collapsed = duplicate_summary_count > 0 or bool(unique_related_hashes)
    return {
        "body_free": True,
        "lineage_mode": "collapsed_fork_or_mirror"
        if fork_or_mirror_lineage_collapsed
        else "single_or_independent_sources",
        "candidate_source_count": len(unique_source_hashes),
        "candidate_source_hashes": unique_source_hashes,
        "related_source_count": len(unique_related_hashes),
        "related_source_hashes": unique_related_hashes,
        "duplicate_summary_count": duplicate_summary_count,
        "evidence_item_id_count": evidence_item_id_count,
        "fork_or_mirror_lineage_collapsed": fork_or_mirror_lineage_collapsed,
        "raw_source_urls_exported": False,
        "raw_related_source_urls_exported": False,
    }


def build_skill_route_discovery_checklist(proposal_lanes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Render proposal lanes as an operator checklist without exporting URLs."""

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    return [
        {
            "source_url_hash": stable_text_hash(str(lane.get("source_url") or "")),
            "capability": "skill_route_discovery",
            "candidate_name": str(lane.get("candidate_name") or ""),
            "allowed_local_lane": str(lane.get("proposal_kind") or ""),
            "local_artifact_contract": skill_route_discovery_local_artifact_contract(
                str(lane.get("proposal_kind") or "")
            ),
            "inspection_requirements": skill_route_discovery_inspection_requirements(
                str(lane.get("proposal_kind") or "")
            ),
            "required_local_artifact_proof": {
                "changed_files": "at least one local contract target for this lane",
                "validation_commands": validation_commands,
                "rollback_artifact": "local rollback artifact recorded before source changes",
                "review_note": "operator-visible note explaining the local artifact evidence",
            },
            "required_tests": validation_commands,
            "preactivation_harness": "agent_harness_eval_lane",
            "rollback_note": "record rollback ref and artifact before applying local source changes",
            "runtime_action": str(lane.get("runtime_action") or ""),
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "raw_source_url_exported": False,
        }
        for lane in proposal_lanes
    ]


def build_skill_route_discovery_activation_lanes(
    proposal_lanes: list[dict[str, Any]],
    *,
    activation_allowed: bool,
    failure_mode: str,
    recovery_hints: list[dict[str, Any]] | None = None,
    local_artifact_proofs: dict[str, dict[str, Any]] | None = None,
    provider_runtime_replay_sample: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group discovered proposal lanes into controller-ready activation checks."""

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    recovery_hints = recovery_hints or []
    local_artifact_proofs = local_artifact_proofs or {}
    provider_runtime_replay_sample = (
        provider_runtime_replay_sample if isinstance(provider_runtime_replay_sample, dict) else {}
    )
    recovery_hint_codes = [str(hint.get("code") or "") for hint in recovery_hints if str(hint.get("code") or "")]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for lane in proposal_lanes:
        proposal_kind = str(lane.get("proposal_kind") or "")
        if not proposal_kind:
            continue
        grouped.setdefault(proposal_kind, []).append(lane)

    activation_blockers = [] if activation_allowed else [failure_mode or "activation_gate_not_ready"]
    activation_lanes: list[dict[str, Any]] = []
    for proposal_kind, lanes in sorted(grouped.items()):
        lane = {
            "proposal_kind": proposal_kind,
            "candidate_count": len(lanes),
            "candidate_names": sorted({str(lane.get("candidate_name") or "") for lane in lanes}),
            "candidate_source_hashes": sorted(
                {
                    stable_text_hash(str(lane.get("source_url") or ""))
                    for lane in lanes
                    if str(lane.get("source_url") or "")
                }
            ),
            "required_validation": validation_commands,
            "local_artifact_contract": skill_route_discovery_local_artifact_contract(proposal_kind),
            "inspection_requirements": skill_route_discovery_inspection_requirements(proposal_kind),
            "local_artifact_proof": skill_route_discovery_local_artifact_proof(
                proposal_kind,
                local_artifact_proofs.get(proposal_kind),
            ),
            "preactivation_harness": {
                "behavior": "agent_harness_eval_lane",
                "required_validation": [SKILL_ROUTE_DISCOVERY_PREACTIVATION_HARNESS_COMMAND],
                "local_eval_only": True,
                "external_harness_execution_allowed": False,
            },
            "provider_runtime_preflight": skill_route_discovery_provider_runtime_preflight_contract(),
            "provider_runtime_control": skill_route_discovery_provider_runtime_control(
                activation_ready=activation_allowed,
                recovery_hint_codes=[] if activation_allowed else recovery_hint_codes,
            ),
            "activation_ready": activation_allowed,
            "activation_blockers": activation_blockers,
            "recovery_hint_codes": [] if activation_allowed else recovery_hint_codes,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "raw_source_urls_exported": False,
        }
        if provider_runtime_replay_sample.get("provided") is True:
            lane["provider_runtime_replay_sample"] = provider_runtime_replay_sample
        activation_lanes.append(lane)
    return activation_lanes


def skill_route_discovery_local_artifact_proofs(raw_input: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize implementation proof records by bounded proposal kind."""

    proofs = raw_input.get("local_artifact_proofs")
    proofs = proofs if isinstance(proofs, list) else []
    normalized: dict[str, dict[str, Any]] = {}
    for proof in proofs:
        if not isinstance(proof, dict):
            continue
        proposal_kind = optional_string(proof.get("proposal_kind"))
        if not proposal_kind:
            continue
        normalized[proposal_kind] = proof
    return normalized


def skill_route_discovery_local_artifact_proof(
    proposal_kind: str,
    proof: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return body-free proof that a lane has a local artifact to review."""

    proof = proof if isinstance(proof, dict) else {}
    changed_files = string_list(proof.get("changed_files"))
    validation_commands = string_list(proof.get("validation_commands"))
    rollback_artifact = optional_string(proof.get("rollback_artifact"))
    review_note = optional_string(proof.get("review_note"))
    expected_validation = skill_route_discovery_preactivation_validation_commands()
    expected_targets = set(SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS.get(proposal_kind, ()))
    changed_file_set = set(changed_files)
    target_paths_matched = bool(expected_targets & changed_file_set)
    validation_matched = validation_commands == expected_validation
    rollback_recorded = bool(rollback_artifact)
    review_note_recorded = bool(review_note)
    ready = bool(proof) and target_paths_matched and validation_matched and rollback_recorded and review_note_recorded
    diagnostics: list[str] = []
    if not proof:
        diagnostics.append("local_artifact_proof_missing")
    if proof and not target_paths_matched:
        diagnostics.append("changed_files_do_not_match_lane_contract")
    if proof and not validation_matched:
        diagnostics.append("validation_commands_mismatch")
    if proof and not rollback_recorded:
        diagnostics.append("rollback_artifact_missing")
    if proof and not review_note_recorded:
        diagnostics.append("review_note_missing")
    return {
        "provided": bool(proof),
        "ready": ready,
        "proposal_kind": proposal_kind,
        "changed_file_count": len(changed_files),
        "changed_file_hashes": [stable_text_hash(path) for path in sorted(dict.fromkeys(changed_files))],
        "target_paths_matched": target_paths_matched,
        "validation_matched": validation_matched,
        "rollback_recorded": rollback_recorded,
        "rollback_artifact_hash": stable_text_hash(rollback_artifact) if rollback_artifact else None,
        "review_note_recorded": review_note_recorded,
        "diagnostics": diagnostics,
        "raw_changed_files_exported": False,
        "raw_rollback_artifact_exported": False,
    }


def skill_route_discovery_inspection_requirements(proposal_kind: str) -> dict[str, Any]:
    """Return the local inspection checklist required before mapping a lane to work."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    return {
        "proposal_kind": proposal_kind,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "required_evidence": list(SKILL_ROUTE_DISCOVERY_INSPECTION_EVIDENCE),
        "required_local_review": list(SKILL_ROUTE_DISCOVERY_INSPECTION_REVIEW),
        "blocked_shortcuts": list(SKILL_ROUTE_DISCOVERY_INSPECTION_BLOCKED_SHORTCUTS),
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "body_free": True,
        "local_only": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_allowed": False,
    }


def skill_route_discovery_provider_runtime_preflight_contract() -> dict[str, Any]:
    """Return local provider-runtime diagnostics required before activation."""

    return {
        "behavior": "provider_runtime_recovery_summary",
        "required_validation": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "local_replay_only": True,
        "body_free_diagnostics_only": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }


def skill_route_discovery_provider_runtime_control(
    *,
    activation_ready: bool,
    recovery_hint_codes: list[str],
) -> dict[str, Any]:
    """Return operator-visible replay control for provider/runtime diagnostics."""

    replay_commands = [
        PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
        PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
    ]
    recovery_hint_codes = sorted(dict.fromkeys(recovery_hint_codes))
    provider_runtime_blocked = "provider_runtime_replay_not_ready" in recovery_hint_codes
    if activation_ready:
        reason = "none"
        next_action = "run_provider_runtime_replay_before_promotion"
    elif provider_runtime_blocked:
        reason = "provider_runtime_replay_not_ready"
        next_action = "resolve_provider_runtime_replay_hints_then_replay_preflight"
    else:
        reason = "skill_route_discovery_activation_not_ready"
        next_action = "resolve_recovery_hints_then_replay_provider_runtime_preflight"

    return {
        "controller_surface": "provider_runtime_control",
        "decision": "ready_for_local_replay" if activation_ready else "blocked_before_local_replay",
        "reason": reason,
        "next_action": next_action,
        "provider_runtime_replay_blocked": provider_runtime_blocked,
        "recovery_hint_count": len(recovery_hint_codes),
        "recovery_hint_codes": recovery_hint_codes,
        "recovery_hint_code_hashes": [stable_text_hash(code) for code in recovery_hint_codes],
        "replay_commands": replay_commands,
        "local_validation_required": True,
        "body_free_diagnostics_only": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
    }


def skill_route_discovery_provider_runtime_diagnostic_panel(
    *,
    activation_lanes: list[dict[str, Any]],
    recovery_hints: list[dict[str, Any]],
    preactivation_trust_boundary: dict[str, Any],
) -> dict[str, Any]:
    """Summarize provider/runtime replay readiness without exporting bodies."""

    replay_commands = [
        PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
        PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
    ]
    recovery_hint_codes = sorted(
        {
            str(hint.get("code") or "")
            for hint in recovery_hints
            if isinstance(hint, dict) and str(hint.get("code") or "")
        }
    )
    lane_controls = [
        lane.get("provider_runtime_control")
        for lane in activation_lanes
        if isinstance(lane.get("provider_runtime_control"), dict)
    ]
    lane_preflights = [
        lane.get("provider_runtime_preflight")
        for lane in activation_lanes
        if isinstance(lane.get("provider_runtime_preflight"), dict)
    ]
    expected_preflight = skill_route_discovery_provider_runtime_preflight_contract()
    ready_lane_count = sum(1 for lane in activation_lanes if lane.get("activation_ready") is True)
    blocked_lane_count = len(activation_lanes) - ready_lane_count
    contract_present = bool(activation_lanes) and len(lane_preflights) == len(activation_lanes)
    contract_valid = contract_present and all(preflight == expected_preflight for preflight in lane_preflights)
    control_present = bool(activation_lanes) and len(lane_controls) == len(activation_lanes)
    local_replay_only = contract_valid and all(
        control.get("local_validation_required") is True for control in lane_controls
    )
    body_free = contract_valid and all(
        control.get("body_free_diagnostics_only") is True
        and control.get("raw_preflight_inputs_exported") is False
        and control.get("raw_diagnostics_exported") is False
        for control in lane_controls
    )
    launch_denied = contract_valid and all(
        control.get("provider_runtime_launch_allowed") is False
        and control.get("remote_execution_allowed") is False
        for control in lane_controls
    )
    diagnostics: list[str] = []
    if not activation_lanes:
        diagnostics.append("no_activation_lanes")
    if not contract_valid:
        diagnostics.append("provider_runtime_preflight_contract_missing_or_mismatched")
    if not control_present:
        diagnostics.append("provider_runtime_control_missing")
    if preactivation_trust_boundary.get("status") != "passed":
        diagnostics.append("preactivation_trust_boundary_not_passed")
    if recovery_hint_codes:
        diagnostics.append("recovery_hints_present")
    if blocked_lane_count:
        diagnostics.append("activation_lanes_blocked")

    ready = (
        bool(activation_lanes)
        and blocked_lane_count == 0
        and contract_valid
        and control_present
        and local_replay_only
        and body_free
        and launch_denied
        and preactivation_trust_boundary.get("status") == "passed"
        and not recovery_hint_codes
    )

    return {
        "controller_surface": "provider_runtime_control",
        "status": "ready" if ready else "blocked",
        "decision": "replay_provider_runtime_preflight_before_promotion"
        if ready
        else "resolve_recovery_hints_before_provider_runtime_replay",
        "activation_lane_count": len(activation_lanes),
        "ready_lane_count": ready_lane_count,
        "blocked_lane_count": blocked_lane_count,
        "provider_runtime_preflight_contract_present": contract_present,
        "provider_runtime_preflight_contract_valid": contract_valid,
        "provider_runtime_control_present": control_present,
        "replay_commands": replay_commands,
        "recovery_hint_count": len(recovery_hint_codes),
        "recovery_hint_codes": recovery_hint_codes,
        "recovery_hint_code_hashes": [stable_text_hash(code) for code in recovery_hint_codes],
        "diagnostics": diagnostics,
        "local_replay_only": local_replay_only,
        "body_free_diagnostics_only": body_free,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
    }


def skill_route_discovery_provider_runtime_replay_sample(
    raw_input: dict[str, Any],
    *,
    source_path: Path,
) -> dict[str, Any]:
    """Summarize optional provider/runtime replay samples without exporting bodies."""

    samples = raw_input.get("provider_runtime_preflight_samples")
    samples = [sample for sample in samples if isinstance(sample, dict)] if isinstance(samples, list) else []
    if not samples:
        return {
            "provided": False,
            "required": True,
            "behavior": "provider_runtime_recovery_summary",
            "replay_commands": [
                PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
            ],
            "body_free_diagnostics_only": True,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_preflight_inputs_exported": False,
            "raw_diagnostics_exported": False,
        }

    summary = evaluate_provider_runtime_recovery_summary(
        {
            "task_id": optional_string(raw_input.get("task_id")) or source_path.stem,
            "preflights": samples,
        },
        source_path=source_path,
    )
    recovery_hint_codes = [
        str(hint.get("code") or "") for hint in summary.get("recovery_hints", []) if str(hint.get("code") or "")
    ]
    supervisor_readiness = (
        summary.get("supervisor_readiness") if isinstance(summary.get("supervisor_readiness"), dict) else {}
    )
    operator_plan = (
        summary.get("operator_recovery_plan") if isinstance(summary.get("operator_recovery_plan"), dict) else {}
    )
    route_status = str(summary.get("route_status") or "blocked")
    sample_blocked = route_status == "blocked"
    degraded_replay_only = route_status == "degraded"
    success_status = (
        supervisor_readiness.get("success_status")
        if isinstance(supervisor_readiness.get("success_status"), dict)
        else {}
    )
    return {
        "provided": True,
        "required": True,
        "behavior": "provider_runtime_recovery_summary",
        "route_status": route_status,
        "ready_for_local_replay": not sample_blocked,
        "blocked_before_local_replay": sample_blocked,
        "ready_for_supervisor_promotion": route_status == "passed",
        "degraded_replay_only": degraded_replay_only,
        "failure_mode": str(summary.get("failure_mode") or "none"),
        "preflight_count": int(summary.get("preflight_count") or 0),
        "status_counts": dict(summary.get("status_counts") or {}),
        "blocked_failure_modes": list(summary.get("blocked_failure_modes") or []),
        "degraded_provider_count": int(summary.get("degraded_provider_count") or 0),
        "runner_invoked_count": int(summary.get("runner_invoked_count") or 0),
        "recovery_hint_codes": recovery_hint_codes,
        "recovery_hint_code_hashes": [stable_text_hash(code) for code in recovery_hint_codes],
        "supervisor_decision": str(supervisor_readiness.get("decision") or ""),
        "success_status_label": str(success_status.get("status_label") or ""),
        "success_claim_allowed": success_status.get("success_claim_allowed") is True,
        "operator_next_action": str(operator_plan.get("next_action") or ""),
        "replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "local_validation_required": True,
        "body_free_diagnostics_only": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_provider_values_exported": False,
    }


def skill_route_discovery_provider_runtime_replay_recovery_hints(
    provider_runtime_replay_sample: dict[str, Any],
) -> list[dict[str, Any]]:
    """Translate sampled provider/runtime replay status into skill-route recovery hints."""

    if provider_runtime_replay_sample.get("provided") is not True:
        return []
    if provider_runtime_replay_sample.get("blocked_before_local_replay") is not True:
        return []
    recovery_hint_codes = string_list(provider_runtime_replay_sample.get("recovery_hint_codes"))
    return [
        {
            "code": "provider_runtime_replay_not_ready",
            "scope": "provider_runtime_control",
            "severity": "blocker",
            "action": "resolve sampled provider-runtime recovery hints, then replay provider_runtime_preflight and provider_runtime_recovery_summary before promoting skill-route lanes",
            "affected_preflight_count": int(provider_runtime_replay_sample.get("preflight_count") or 0),
            "provider_harnesses": [],
            "sample_route_status": str(provider_runtime_replay_sample.get("route_status") or ""),
            "sample_failure_mode": str(provider_runtime_replay_sample.get("failure_mode") or ""),
            "sample_recovery_hint_count": len(recovery_hint_codes),
            "sample_recovery_hint_code_hashes": [stable_text_hash(code) for code in recovery_hint_codes],
            "value_recorded": False,
        }
    ]


def skill_route_discovery_local_artifact_contract(proposal_kind: str) -> dict[str, Any]:
    """Return the bounded local artifact target for a skill-route proposal lane."""

    targets = list(SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS.get(proposal_kind, ()))
    return {
        "proposal_kind": proposal_kind,
        "target_paths": targets,
        "required_review_surface": "changed_files_and_validation",
        "local_only": True,
        "external_skill_code_allowed": False,
        "raw_upstream_body_allowed": False,
    }


def skill_route_discovery_preactivation_trust_boundary(
    proposal_lanes: list[dict[str, Any]],
    activation_lanes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Revalidate controller-visible lanes before local proposal activation.

    The discovery registry is a static declaration. This preflight is the
    runtime-facing guard: activation rows must still be local-only, validation
    backed, and unable to activate external skill or harness execution.
    """

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    expected_validation = skill_route_discovery_preactivation_validation_commands()
    expected_preactivation_validation = [SKILL_ROUTE_DISCOVERY_PREACTIVATION_HARNESS_COMMAND]
    expected_provider_runtime_preflight = skill_route_discovery_provider_runtime_preflight_contract()
    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    diagnostics: list[str] = []

    proposal_kinds = {str(lane.get("proposal_kind") or "") for lane in proposal_lanes}
    unbounded_proposal_kinds = sorted(proposal_kinds - allowed_lanes)
    if unbounded_proposal_kinds:
        diagnostics.append("proposal_lanes_unbounded:" + ",".join(unbounded_proposal_kinds))

    if any(str(lane.get("runtime_action") or "") != "none" for lane in proposal_lanes):
        diagnostics.append("proposal_lane_runtime_action_must_be_none")
    if any(lane.get("local_validation_required") is not True for lane in proposal_lanes):
        diagnostics.append("proposal_lane_local_validation_required")

    for index, lane in enumerate(activation_lanes):
        prefix = f"activation_lanes[{index}]"
        proposal_kind = str(lane.get("proposal_kind") or "")
        if proposal_kind not in allowed_lanes:
            diagnostics.append(f"{prefix}.proposal_kind_unbounded:{proposal_kind}")
        if str(lane.get("runtime_action") or "") != "none":
            diagnostics.append(f"{prefix}.runtime_action_must_be_none")
        if lane.get("external_skill_activation_allowed") is not False:
            diagnostics.append(f"{prefix}.external_skill_activation_must_be_false")
        if lane.get("raw_source_urls_exported") is not False:
            diagnostics.append(f"{prefix}.raw_source_urls_must_be_false")
        if lane.get("required_validation") != expected_validation:
            diagnostics.append(f"{prefix}.required_validation_mismatch")
        candidate_source_hashes = lane.get("candidate_source_hashes")
        candidate_source_hashes = candidate_source_hashes if isinstance(candidate_source_hashes, list) else []
        if not candidate_source_hashes:
            diagnostics.append(f"{prefix}.candidate_source_hashes_missing")
        if any(not str(value).startswith("sha256:") for value in candidate_source_hashes):
            diagnostics.append(f"{prefix}.candidate_source_hashes_must_be_hashes")

        artifact_contract = lane.get("local_artifact_contract")
        artifact_contract = artifact_contract if isinstance(artifact_contract, dict) else {}
        if artifact_contract.get("proposal_kind") != proposal_kind:
            diagnostics.append(f"{prefix}.local_artifact_contract_kind_mismatch")
        if artifact_contract.get("required_review_surface") != "changed_files_and_validation":
            diagnostics.append(f"{prefix}.local_artifact_contract_review_surface_mismatch")
        if artifact_contract.get("local_only") is not True:
            diagnostics.append(f"{prefix}.local_artifact_contract_must_be_local_only")
        if artifact_contract.get("external_skill_code_allowed") is not False:
            diagnostics.append(f"{prefix}.external_skill_code_must_be_false")
        if artifact_contract.get("raw_upstream_body_allowed") is not False:
            diagnostics.append(f"{prefix}.raw_upstream_body_must_be_false")

        inspection_requirements = lane.get("inspection_requirements")
        expected_inspection_requirements = skill_route_discovery_inspection_requirements(proposal_kind)
        if inspection_requirements != expected_inspection_requirements:
            diagnostics.append(f"{prefix}.inspection_requirements_mismatch")

        target_paths = artifact_contract.get("target_paths")
        target_paths = target_paths if isinstance(target_paths, list) else []
        if not target_paths:
            diagnostics.append(f"{prefix}.local_artifact_contract_targets_missing")
        for target_path in target_paths:
            target_text = str(target_path)
            if (
                not target_text
                or target_text.startswith("/")
                or re.match(r"^[A-Za-z]:", target_text)
                or ".." in Path(target_text).parts
                or "://" in target_text
            ):
                diagnostics.append(f"{prefix}.local_artifact_contract_target_unbounded")
                break

        preactivation_harness = lane.get("preactivation_harness")
        preactivation_harness = preactivation_harness if isinstance(preactivation_harness, dict) else {}
        if preactivation_harness.get("behavior") != "agent_harness_eval_lane":
            diagnostics.append(f"{prefix}.preactivation_harness_behavior_mismatch")
        if preactivation_harness.get("required_validation") != expected_preactivation_validation:
            diagnostics.append(f"{prefix}.preactivation_harness_validation_mismatch")
        if preactivation_harness.get("local_eval_only") is not True:
            diagnostics.append(f"{prefix}.preactivation_harness_must_be_local_eval_only")
        if preactivation_harness.get("external_harness_execution_allowed") is not False:
            diagnostics.append(f"{prefix}.external_harness_execution_must_be_false")

        provider_runtime_preflight = lane.get("provider_runtime_preflight")
        provider_runtime_preflight = provider_runtime_preflight if isinstance(provider_runtime_preflight, dict) else {}
        if provider_runtime_preflight.get("behavior") != expected_provider_runtime_preflight["behavior"]:
            diagnostics.append(f"{prefix}.provider_runtime_preflight_behavior_mismatch")
        if (
            provider_runtime_preflight.get("required_validation")
            != expected_provider_runtime_preflight["required_validation"]
        ):
            diagnostics.append(f"{prefix}.provider_runtime_preflight_validation_mismatch")
        if provider_runtime_preflight.get("local_replay_only") is not True:
            diagnostics.append(f"{prefix}.provider_runtime_preflight_must_be_local_replay_only")
        if provider_runtime_preflight.get("body_free_diagnostics_only") is not True:
            diagnostics.append(f"{prefix}.provider_runtime_preflight_must_be_body_free")
        if provider_runtime_preflight.get("provider_runtime_launch_allowed") is not False:
            diagnostics.append(f"{prefix}.provider_runtime_launch_must_be_false")
        if provider_runtime_preflight.get("remote_execution_allowed") is not False:
            diagnostics.append(f"{prefix}.provider_runtime_remote_execution_must_be_false")

        activation_ready = lane.get("activation_ready") is True
        expected_provider_runtime_control = skill_route_discovery_provider_runtime_control(
            activation_ready=activation_ready,
            recovery_hint_codes=string_list(lane.get("recovery_hint_codes")),
        )
        provider_runtime_control = lane.get("provider_runtime_control")
        provider_runtime_control = provider_runtime_control if isinstance(provider_runtime_control, dict) else {}
        if provider_runtime_control != expected_provider_runtime_control:
            diagnostics.append(f"{prefix}.provider_runtime_control_mismatch")

        provider_runtime_replay_sample = lane.get("provider_runtime_replay_sample")
        if isinstance(provider_runtime_replay_sample, dict):
            if provider_runtime_replay_sample.get("behavior") != "provider_runtime_recovery_summary":
                diagnostics.append(f"{prefix}.provider_runtime_replay_sample_behavior_mismatch")
            if provider_runtime_replay_sample.get("body_free_diagnostics_only") is not True:
                diagnostics.append(f"{prefix}.provider_runtime_replay_sample_must_be_body_free")
            if provider_runtime_replay_sample.get("provider_runtime_launch_allowed") is not False:
                diagnostics.append(f"{prefix}.provider_runtime_replay_sample_launch_must_be_false")
            if provider_runtime_replay_sample.get("remote_execution_allowed") is not False:
                diagnostics.append(f"{prefix}.provider_runtime_replay_sample_remote_execution_must_be_false")
            if provider_runtime_replay_sample.get("raw_preflight_inputs_exported") is not False:
                diagnostics.append(f"{prefix}.provider_runtime_replay_sample_raw_inputs_must_be_false")
            if provider_runtime_replay_sample.get("raw_diagnostics_exported") is not False:
                diagnostics.append(f"{prefix}.provider_runtime_replay_sample_raw_diagnostics_must_be_false")
            if provider_runtime_replay_sample.get("replay_commands") != [
                PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
            ]:
                diagnostics.append(f"{prefix}.provider_runtime_replay_sample_commands_mismatch")

        blockers = lane.get("activation_blockers")
        blockers = blockers if isinstance(blockers, list) else []
        if activation_ready and blockers:
            diagnostics.append(f"{prefix}.ready_lane_must_not_have_blockers")

    return {
        "status": "passed" if not diagnostics else "blocked",
        "diagnostics": diagnostics,
        "static_declaration_rechecked": True,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }


def skill_route_discovery_implementation_intake_preflight(
    activation_lanes: list[dict[str, Any]],
    *,
    preactivation_trust_boundary: dict[str, Any],
) -> dict[str, Any]:
    """Summarize whether route-discovery rows may become local implementation work."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    diagnostics: list[str] = []
    target_paths: list[str] = []
    proposal_kinds: list[str] = []

    if preactivation_trust_boundary.get("status") != "passed":
        diagnostics.append("preactivation_trust_boundary_not_passed")

    for index, lane in enumerate(activation_lanes):
        prefix = f"activation_lanes[{index}]"
        proposal_kind = str(lane.get("proposal_kind") or "")
        proposal_kinds.append(proposal_kind)
        if proposal_kind not in allowed_lanes:
            diagnostics.append(f"{prefix}.proposal_kind_unbounded:{proposal_kind}")
        if lane.get("activation_ready") is not True:
            diagnostics.append(f"{prefix}.activation_not_ready")
        if str(lane.get("runtime_action") or "") != "none":
            diagnostics.append(f"{prefix}.runtime_action_must_be_none")
        if lane.get("external_skill_activation_allowed") is not False:
            diagnostics.append(f"{prefix}.external_skill_activation_must_be_false")

        artifact_proof = lane.get("local_artifact_proof")
        artifact_proof = artifact_proof if isinstance(artifact_proof, dict) else {}
        if artifact_proof.get("ready") is not True:
            diagnostics.append(f"{prefix}.local_artifact_proof_not_ready")
        if artifact_proof.get("raw_changed_files_exported") is not False:
            diagnostics.append(f"{prefix}.local_artifact_proof_raw_changed_files_must_be_false")
        if artifact_proof.get("raw_rollback_artifact_exported") is not False:
            diagnostics.append(f"{prefix}.local_artifact_proof_raw_rollback_must_be_false")

        artifact_contract = lane.get("local_artifact_contract")
        artifact_contract = artifact_contract if isinstance(artifact_contract, dict) else {}
        if artifact_contract.get("local_only") is not True:
            diagnostics.append(f"{prefix}.artifact_contract_must_be_local_only")
        if artifact_contract.get("external_skill_code_allowed") is not False:
            diagnostics.append(f"{prefix}.external_skill_code_must_be_false")
        if artifact_contract.get("raw_upstream_body_allowed") is not False:
            diagnostics.append(f"{prefix}.raw_upstream_body_must_be_false")

        contract_targets = artifact_contract.get("target_paths")
        contract_targets = contract_targets if isinstance(contract_targets, list) else []
        target_paths.extend(str(target) for target in contract_targets if str(target).strip())

    target_path_hashes = [stable_text_hash(path) for path in sorted(dict.fromkeys(target_paths))]
    implementation_allowed = bool(activation_lanes) and not diagnostics
    return {
        "status": "ready" if implementation_allowed else "blocked",
        "implementation_allowed": implementation_allowed,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "proposal_kinds": sorted(dict.fromkeys(proposal_kinds)),
        "activation_lane_count": len(activation_lanes),
        "target_path_count": len(target_path_hashes),
        "target_path_hashes": target_path_hashes,
        "changed_file_review_required": True,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_upstream_body_allowed": False,
        "raw_target_paths_exported": False,
        "diagnostics": diagnostics,
    }


def skill_route_discovery_operator_handoff(
    *,
    activation_lanes: list[dict[str, Any]],
    implementation_intake_preflight: dict[str, Any],
    supervisor_readiness: dict[str, Any],
    source_lineage: dict[str, Any],
    recovery_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render the final body-free operator view for local implementation lanes."""

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    provider_runtime_commands = [
        PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
        PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
    ]
    lane_rows: list[dict[str, Any]] = []
    for lane in activation_lanes:
        artifact_contract = lane.get("local_artifact_contract")
        artifact_contract = artifact_contract if isinstance(artifact_contract, dict) else {}
        target_paths = artifact_contract.get("target_paths")
        target_paths = target_paths if isinstance(target_paths, list) else []
        row = {
            "proposal_kind": str(lane.get("proposal_kind") or ""),
            "candidate_count": int(lane.get("candidate_count") or 0),
            "activation_ready": lane.get("activation_ready") is True,
            "local_artifact_proof_ready": isinstance(lane.get("local_artifact_proof"), dict)
            and lane["local_artifact_proof"].get("ready") is True,
            "target_path_hashes": [
                stable_text_hash(str(path)) for path in sorted({str(path) for path in target_paths})
            ],
            "required_validation": validation_commands,
            "provider_runtime_replay_commands": provider_runtime_commands,
            "provider_runtime_control": lane.get("provider_runtime_control")
            if isinstance(lane.get("provider_runtime_control"), dict)
            else skill_route_discovery_provider_runtime_control(
                activation_ready=lane.get("activation_ready") is True,
                recovery_hint_codes=string_list(lane.get("recovery_hint_codes")),
            ),
            "runtime_action": str(lane.get("runtime_action") or ""),
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "raw_target_paths_exported": False,
            "raw_source_urls_exported": False,
        }
        if isinstance(lane.get("provider_runtime_replay_sample"), dict):
            row["provider_runtime_replay_sample"] = lane["provider_runtime_replay_sample"]
        lane_rows.append(row)

    ready_lane_count = sum(1 for row in lane_rows if row["activation_ready"])
    blocked_lane_count = len(lane_rows) - ready_lane_count
    proof_ready = bool(lane_rows) and all(row["local_artifact_proof_ready"] for row in lane_rows)
    recovery_hint_codes = [str(hint.get("code") or "") for hint in recovery_hints if str(hint.get("code") or "")]
    implementation_ready = implementation_intake_preflight.get("status") == "ready"
    supervisor_ready = supervisor_readiness.get("decision") == "ready_for_supervisor_promotion"
    handoff_ready = (
        implementation_ready and supervisor_ready and blocked_lane_count == 0 and proof_ready and bool(lane_rows)
    )
    return {
        "status": "ready" if handoff_ready else "blocked",
        "decision": "handoff_local_artifact_lanes" if handoff_ready else "hold_for_review_or_replay",
        "ready_lane_count": ready_lane_count,
        "blocked_lane_count": blocked_lane_count,
        "local_artifact_proof_ready": proof_ready,
        "lane_rows": lane_rows,
        "implementation_intake_status": str(implementation_intake_preflight.get("status") or ""),
        "supervisor_decision": str(supervisor_readiness.get("decision") or ""),
        "required_validation": validation_commands,
        "provider_runtime_replay_commands": provider_runtime_commands,
        "provider_runtime_control": skill_route_discovery_provider_runtime_control(
            activation_ready=handoff_ready,
            recovery_hint_codes=recovery_hint_codes,
        ),
        "recovery_hint_codes": recovery_hint_codes,
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
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


def skill_route_discovery_activation_manifest(
    *,
    proposal_lanes: list[dict[str, Any]],
    activation_lanes: list[dict[str, Any]],
    operator_handoff: dict[str, Any],
    source_lineage: dict[str, Any],
    recovery_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Render a compact replay manifest for bounded local route activation."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    proposals_by_kind: dict[str, list[dict[str, Any]]] = {}
    for lane in proposal_lanes:
        proposal_kind = str(lane.get("proposal_kind") or "")
        if proposal_kind:
            proposals_by_kind.setdefault(proposal_kind, []).append(lane)

    manifest_lanes: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for activation_lane in activation_lanes:
        proposal_kind = str(activation_lane.get("proposal_kind") or "")
        lane_proposals = proposals_by_kind.get(proposal_kind, [])
        evidence_refs: list[str] = []
        route_profiles: list[str] = []
        for proposal in lane_proposals:
            evidence_refs.extend(string_list(proposal.get("evidence_item_ids")))
            route_profiles.extend(string_list(proposal.get("route_profiles")))

        artifact_contract = activation_lane.get("local_artifact_contract")
        artifact_contract = artifact_contract if isinstance(artifact_contract, dict) else {}
        target_paths = artifact_contract.get("target_paths")
        target_paths = target_paths if isinstance(target_paths, list) else []
        artifact_proof = activation_lane.get("local_artifact_proof")
        artifact_proof = artifact_proof if isinstance(artifact_proof, dict) else {}
        provider_runtime_control = activation_lane.get("provider_runtime_control")
        provider_runtime_control = (
            provider_runtime_control if isinstance(provider_runtime_control, dict) else {}
        )

        if proposal_kind not in allowed_lanes:
            diagnostics.append(f"{proposal_kind}:proposal_kind_unbounded")
        if str(activation_lane.get("runtime_action") or "") != "none":
            diagnostics.append(f"{proposal_kind}:runtime_action_must_be_none")
        if activation_lane.get("external_skill_activation_allowed") is not False:
            diagnostics.append(f"{proposal_kind}:external_skill_activation_must_be_false")
        if artifact_proof.get("ready") is not True:
            diagnostics.append(f"{proposal_kind}:local_artifact_proof_not_ready")
        if not evidence_refs:
            diagnostics.append(f"{proposal_kind}:evidence_refs_missing")

        manifest_lanes.append(
            {
                "proposal_kind": proposal_kind,
                "route_profiles": sorted(dict.fromkeys(route_profiles)),
                "evidence_refs": sorted(dict.fromkeys(evidence_refs)),
                "candidate_count": int(activation_lane.get("candidate_count") or 0),
                "candidate_source_hashes": string_list(activation_lane.get("candidate_source_hashes")),
                "target_path_hashes": [
                    stable_text_hash(str(path)) for path in sorted({str(path) for path in target_paths})
                ],
                "local_artifact_proof_ready": artifact_proof.get("ready") is True,
                "required_validation": validation_commands,
                "provider_runtime_next_action": str(provider_runtime_control.get("next_action") or ""),
                "activation_ready": activation_lane.get("activation_ready") is True,
                "activation_blockers": string_list(activation_lane.get("activation_blockers")),
                "runtime_action": str(activation_lane.get("runtime_action") or "none"),
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    ready = (
        bool(manifest_lanes)
        and not diagnostics
        and operator_handoff.get("status") == "ready"
        and all(lane["activation_ready"] for lane in manifest_lanes)
    )
    recovery_hint_codes = [str(hint.get("code") or "") for hint in recovery_hints if str(hint.get("code") or "")]
    activation_sequence = skill_route_discovery_activation_sequence(
        manifest_lanes=manifest_lanes,
        manifest_ready=ready,
        operator_handoff=operator_handoff,
        source_lineage=source_lineage,
    )
    return {
        "controller_surface": "skill_route_discovery_activation_manifest",
        "status": "ready" if ready else "blocked",
        "decision": "manifest_bounded_local_lanes" if ready else "hold_manifest_for_review",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "lane_count": len(manifest_lanes),
        "manifest_lanes": manifest_lanes,
        "activation_sequence": activation_sequence,
        "required_validation": validation_commands,
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
        },
        "recovery_hint_codes": recovery_hint_codes,
        "diagnostics": diagnostics,
        "evidence_ref_mode": "selected_item_ids_only",
        "local_validation_required": True,
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


def skill_route_discovery_activation_sequence(
    *,
    manifest_lanes: list[dict[str, Any]],
    manifest_ready: bool,
    operator_handoff: dict[str, Any],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    """Render a body-free ordered preactivation sequence for supervisors."""

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    provider_runtime_commands = [
        PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
        PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
    ]
    lane_count = len(manifest_lanes)
    lane_names = [str(lane.get("proposal_kind") or "") for lane in manifest_lanes]
    bounded_lanes_ready = bool(lane_count) and all(
        str(lane.get("runtime_action") or "none") == "none"
        and lane.get("external_skill_activation_allowed") is False
        and not string_list(lane.get("activation_blockers"))
        for lane in manifest_lanes
    )
    artifact_proofs_ready = bool(lane_count) and all(
        lane.get("local_artifact_proof_ready") is True for lane in manifest_lanes
    )
    validation_ready = bool(lane_count) and all(
        lane.get("required_validation") == validation_commands for lane in manifest_lanes
    )
    provider_replay_ready = bool(lane_count) and all(
        str(lane.get("provider_runtime_next_action") or "")
        == "run_provider_runtime_replay_before_promotion"
        for lane in manifest_lanes
    )
    lineage_ready = source_lineage.get("body_free") is True and int(
        source_lineage.get("candidate_source_count") or 0
    ) > 0
    handoff_ready = operator_handoff.get("status") == "ready"

    step_specs = [
        (
            "inspect_body_free_source_lineage",
            lineage_ready,
            "source_lineage",
            [],
            [],
        ),
        (
            "verify_bounded_local_lanes",
            bounded_lanes_ready,
            "manifest_lanes",
            lane_names,
            [],
        ),
        (
            "prove_local_artifacts",
            artifact_proofs_ready,
            "local_artifact_proof",
            lane_names,
            [],
        ),
        (
            "run_required_local_validation",
            validation_ready,
            "required_validation",
            lane_names,
            validation_commands,
        ),
        (
            "replay_provider_runtime_preflight",
            provider_replay_ready,
            "provider_runtime_control",
            lane_names,
            provider_runtime_commands,
        ),
        (
            "handoff_to_supervisor",
            handoff_ready and manifest_ready,
            "operator_handoff",
            lane_names,
            [],
        ),
    ]
    steps = [
        {
            "order": index,
            "step": step,
            "status": "ready" if ready else "blocked",
            "source": source,
            "proposal_kinds": sorted(dict.fromkeys(proposal_kinds)),
            "required_validation": commands,
            "runtime_action_allowed": False,
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_evidence_exported": False,
            "raw_source_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        for index, (step, ready, source, proposal_kinds, commands) in enumerate(step_specs, start=1)
    ]
    sequence_ready = bool(steps) and all(step["status"] == "ready" for step in steps)
    return {
        "controller_surface": "skill_route_discovery_activation_sequence",
        "status": "ready" if sequence_ready else "blocked",
        "decision": "sequence_ready_for_supervisor_replay" if sequence_ready else "hold_sequence_for_replay",
        "step_count": len(steps),
        "steps": steps,
        "required_validation": validation_commands,
        "provider_runtime_replay_commands": provider_runtime_commands,
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_validated_activation_packet(
    *,
    activation_manifest: dict[str, Any],
    status: str,
    diagnostics: list[str],
) -> dict[str, Any]:
    """Render final-pass local replay work without exposing upstream bodies."""

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    manifest_lanes = activation_manifest.get("manifest_lanes")
    manifest_lanes = manifest_lanes if isinstance(manifest_lanes, list) else []
    rows: list[dict[str, Any]] = []
    for lane in manifest_lanes:
        proposal_kind = str(lane.get("proposal_kind") or "")
        route_profiles = string_list(lane.get("route_profiles"))
        evidence_refs = string_list(lane.get("evidence_refs"))
        activation_blockers = string_list(lane.get("activation_blockers"))
        rows.append(
            {
                "proposal_kind": proposal_kind,
                "route_profiles": route_profiles,
                "evidence_ref_count": len(evidence_refs),
                "evidence_refs": evidence_refs,
                "candidate_count": int(lane.get("candidate_count") or 0),
                "candidate_source_hashes": string_list(lane.get("candidate_source_hashes")),
                "target_path_hashes": string_list(lane.get("target_path_hashes")),
                "local_artifact_proof_ready": lane.get("local_artifact_proof_ready") is True,
                "required_validation": validation_commands,
                "provider_runtime_next_action": str(lane.get("provider_runtime_next_action") or ""),
                "activation_ready": lane.get("activation_ready") is True,
                "activation_blockers": activation_blockers,
                "supervisor_replay_step": (
                    "review_and_replay_bounded_local_lane"
                    if status == "ready"
                    and not diagnostics
                    and lane.get("activation_ready") is True
                    and not activation_blockers
                    else "repair_bounded_local_lane_before_replay"
                ),
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
        )

    packet_ready = (
        status == "ready"
        and activation_manifest.get("status") == "ready"
        and bool(rows)
        and all(row["activation_ready"] and row["local_artifact_proof_ready"] for row in rows)
        and not diagnostics
    )
    selected_evidence_refs = sorted(
        {
            ref
            for row in rows
            for ref in string_list(row.get("evidence_refs"))
        }
    )
    operator_activation_lane = skill_route_discovery_operator_activation_lane(
        rows=rows,
        packet_ready=packet_ready,
        diagnostics=diagnostics,
    )
    return {
        "controller_surface": "skill_route_discovery_validated_activation_packet",
        "status": "ready" if packet_ready else "blocked",
        "decision": (
            "packet_ready_for_supervisor_replay"
            if packet_ready
            else "hold_packet_for_repair_or_replay"
        ),
        "row_count": len(rows),
        "rows": rows,
        "proposal_kinds": sorted({row["proposal_kind"] for row in rows if row["proposal_kind"]}),
        "route_profiles": sorted(
            {
                profile
                for row in rows
                for profile in string_list(row.get("route_profiles"))
            }
        ),
        "selected_evidence_ref_count": len(selected_evidence_refs),
        "selected_evidence_refs": selected_evidence_refs,
        "operator_activation_lane": operator_activation_lane,
        "diagnostics": diagnostics,
        "required_validation": validation_commands,
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
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


def skill_route_discovery_preactivation_lane_selection(
    *,
    route_profile_review: dict[str, Any],
    activation_manifest: dict[str, Any],
    candidate_lane_intake: dict[str, Any],
) -> dict[str, Any]:
    """Select one bounded local lane per route profile before activation handoff."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    manifest_lanes = activation_manifest.get("manifest_lanes")
    manifest_lanes = manifest_lanes if isinstance(manifest_lanes, list) else []
    manifest_by_kind = {
        str(lane.get("proposal_kind") or ""): lane
        for lane in manifest_lanes
        if isinstance(lane, dict) and str(lane.get("proposal_kind") or "")
    }
    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    review_rows = route_profile_review.get("rows")
    review_rows = review_rows if isinstance(review_rows, list) else []

    for profile_row in review_rows:
        if not isinstance(profile_row, dict):
            continue
        profile = str(profile_row.get("route_profile") or "generic_skill_workflow")
        proposal_kinds = [
            kind
            for kind in string_list(profile_row.get("proposal_kinds"))
            if kind in allowed_lanes
        ]
        lane_selection = skill_route_discovery_profile_lane_selection(
            proposal_kinds=proposal_kinds,
            route_profiles=[profile],
            downgraded_lanes=[],
            rejected=False,
        )
        recommended_order = string_list(lane_selection.get("recommended_local_lane_order"))
        eligible_lanes = [
            lane
            for lane in recommended_order
            if manifest_by_kind.get(lane, {}).get("activation_ready") is True
            and manifest_by_kind.get(lane, {}).get("local_artifact_proof_ready") is True
            and str(manifest_by_kind.get(lane, {}).get("runtime_action") or "none") == "none"
            and manifest_by_kind.get(lane, {}).get("external_skill_activation_allowed") is False
        ]
        profile_ready = (
            profile_row.get("metadata_complete") is True
            and profile_row.get("local_validation_required") is True
            and str(profile_row.get("runtime_action") or "none") == "none"
        )
        state_handoff_preflight = profile_row.get("state_handoff_preflight")
        if isinstance(state_handoff_preflight, dict) and state_handoff_preflight.get("status") != "ready":
            profile_ready = False

        selected_lane = eligible_lanes[0] if profile_ready and eligible_lanes else ""
        row_diagnostics: list[str] = []
        if not proposal_kinds:
            row_diagnostics.append("no_bounded_profile_lanes")
        if not profile_ready:
            row_diagnostics.append("profile_review_not_ready")
        if not eligible_lanes:
            row_diagnostics.append("local_artifact_proof_not_ready")
        for diagnostic in row_diagnostics:
            diagnostics.append(f"{profile}:{diagnostic}")

        rows.append(
            {
                "route_profile": profile,
                "selected_local_lane": selected_lane,
                "recommended_local_lane_order": recommended_order,
                "eligible_local_lanes": eligible_lanes,
                "proposal_kinds": proposal_kinds,
                "selection_status": "ready" if selected_lane else "review",
                "selection_reason": lane_selection["lane_selection_reason"]
                if selected_lane
                else "resolve_profile_review_or_artifact_proof_before_lane_selection",
                "metadata_complete": profile_row.get("metadata_complete") is True,
                "local_artifact_proof_ready": bool(eligible_lanes),
                "state_handoff_preflight_ready": (
                    state_handoff_preflight.get("status") == "ready"
                    if isinstance(state_handoff_preflight, dict)
                    else True
                ),
                "diagnostics": row_diagnostics,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    ready = (
        bool(rows)
        and not diagnostics
        and route_profile_review.get("status") == "ready"
        and activation_manifest.get("status") == "ready"
        and candidate_lane_intake.get("status") == "ready"
        and all(row["selected_local_lane"] in allowed_lanes for row in rows)
    )
    return {
        "controller_surface": "skill_route_discovery_preactivation_lane_selection",
        "status": "ready" if ready else "review" if rows else "blocked",
        "decision": "select_bounded_local_lane_per_profile"
        if ready
        else "resolve_profile_or_manifest_before_lane_selection",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "profile_count": len(rows),
        "selected_profile_count": sum(1 for row in rows if row["selected_local_lane"]),
        "selected_lanes": [
            {
                "route_profile": row["route_profile"],
                "selected_local_lane": row["selected_local_lane"],
            }
            for row in rows
            if row["selected_local_lane"]
        ],
        "rows": rows,
        "diagnostics": diagnostics,
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_route_discovery_catalog(
    *,
    raw_input: dict[str, Any],
    candidate_lane_intake: dict[str, Any],
    route_profile_review: dict[str, Any],
    preactivation_lane_selection: dict[str, Any],
    provider_runtime_replay_sample: dict[str, Any],
) -> dict[str, Any]:
    """Render an operator catalog from skill-route evidence to bounded local work."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    window = raw_input.get("capability_window")
    window = window if isinstance(window, dict) else {}
    theme = optional_string(window.get("theme")) or "skill-route-discovery"
    capability_slice = optional_string(window.get("capability_slice")) or (
        "Convert skill and route evidence into bounded local lanes that can be validated before activation."
    )
    sample_gate = skill_route_discovery_provider_runtime_sample_gate(
        window=window,
        provider_runtime_replay_sample=provider_runtime_replay_sample,
    )
    selection_rows = preactivation_lane_selection.get("rows")
    selection_rows = selection_rows if isinstance(selection_rows, list) else []
    selection_by_profile = {
        str(row.get("route_profile") or ""): row
        for row in selection_rows
        if isinstance(row, dict) and str(row.get("route_profile") or "")
    }
    candidate_rows = candidate_lane_intake.get("rows")
    candidate_rows = candidate_rows if isinstance(candidate_rows, list) else []
    review_rows = route_profile_review.get("rows")
    review_rows = review_rows if isinstance(review_rows, list) else []

    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for review_row in review_rows:
        if not isinstance(review_row, dict):
            continue
        route_profile = str(review_row.get("route_profile") or "generic_skill_workflow")
        matching_candidates = [
            row
            for row in candidate_rows
            if isinstance(row, dict) and route_profile in string_list(row.get("route_profiles"))
        ]
        proposal_kinds = sorted(
            {
                kind
                for candidate in matching_candidates
                for kind in string_list(candidate.get("proposal_kinds"))
                if kind in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            }
            or {
                kind
                for kind in string_list(review_row.get("proposal_kinds"))
                if kind in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            }
        )
        selection = selection_by_profile.get(route_profile, {})
        selected_lane = optional_string(selection.get("selected_local_lane")) or ""
        recommended_order = [
            lane
            for lane in string_list(selection.get("recommended_local_lane_order"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        if not recommended_order:
            recommended_order = [
                lane
                for lane in string_list(review_row.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            ]
        row_diagnostics: list[str] = []
        if not proposal_kinds:
            row_diagnostics.append("no_bounded_local_lanes")
        if not selected_lane:
            row_diagnostics.append("selected_local_lane_not_ready")
        if review_row.get("metadata_complete") is not True:
            row_diagnostics.append("profile_metadata_not_complete")
        if sample_gate["status"] != "ready":
            row_diagnostics.append(str(sample_gate["diagnostic"]))
        for diagnostic in row_diagnostics:
            diagnostics.append(f"{route_profile}:{diagnostic}")

        source_hashes = sorted(
            {
                str(candidate.get("source_hash") or "")
                for candidate in matching_candidates
                if str(candidate.get("source_hash") or "")
            }
        )
        evidence_item_ids = sorted(
            {
                item_id
                for candidate in matching_candidates
                for item_id in string_list(candidate.get("evidence_item_ids"))
            }
        )
        rows.append(
            {
                "route_profile": route_profile,
                "allowed_local_lanes": proposal_kinds,
                "selected_local_lane": selected_lane,
                "recommended_local_lane_order": recommended_order,
                "selection_status": "ready" if selected_lane and not row_diagnostics else "review",
                "candidate_count": len(matching_candidates),
                "candidate_source_hashes": source_hashes,
                "evidence_item_ids": evidence_item_ids,
                "evidence_item_id_count": len(evidence_item_ids),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_preflight_required": sample_gate["required"],
                "provider_runtime_replay_commands": [
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                    PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
                ],
                "diagnostics": row_diagnostics,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    ready = (
        bool(rows)
        and not diagnostics
        and candidate_lane_intake.get("status") == "ready"
        and route_profile_review.get("status") == "ready"
        and preactivation_lane_selection.get("status") == "ready"
        and sample_gate["status"] == "ready"
    )
    return {
        "controller_surface": "skill_route_discovery_catalog",
        "status": "ready" if ready else "review" if rows else "blocked",
        "decision": "catalog_ready_for_bounded_local_replay"
        if ready
        else "review_catalog_before_bounded_local_replay",
        "theme": theme,
        "capability_slice": capability_slice,
        "current_pass": int(window.get("current_pass") or window.get("planned_pass") or 0),
        "total_passes": int(window.get("total_passes") or 0),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "route_profile_count": len(rows),
        "candidate_count": sum(row["candidate_count"] for row in rows),
        "selected_lane_count": sum(1 for row in rows if row["selected_local_lane"]),
        "provider_runtime_sample_gate": sample_gate,
        "provider_runtime_preflight_required": sample_gate["required"],
        "rows": rows,
        "diagnostics": diagnostics,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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


def skill_route_discovery_validation_lane_plan(
    *,
    raw_input: dict[str, Any],
    route_discovery_catalog: dict[str, Any],
) -> dict[str, Any]:
    """Choose the next bounded local validation lane from cataloged evidence."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    window = raw_input.get("capability_window")
    window = window if isinstance(window, dict) else {}
    current_pass = int(window.get("current_pass") or window.get("planned_pass") or 0)
    total_passes = int(window.get("total_passes") or 0)
    has_next_pass = bool(current_pass and total_passes and current_pass < total_passes)
    catalog_rows = route_discovery_catalog.get("rows")
    catalog_rows = catalog_rows if isinstance(catalog_rows, list) else []
    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)

    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for row in catalog_rows:
        if not isinstance(row, dict):
            continue
        route_profile = optional_string(row.get("route_profile")) or "generic_skill_workflow"
        selected_lane = optional_string(row.get("selected_local_lane")) or ""
        allowed_local_lanes = [
            lane
            for lane in string_list(row.get("allowed_local_lanes"))
            if lane in allowed_lanes
        ]
        row_diagnostics = string_list(row.get("diagnostics"))
        if selected_lane not in allowed_lanes:
            row_diagnostics.append("selected_local_lane_not_bounded")
        if not allowed_local_lanes:
            row_diagnostics.append("allowed_local_lanes_missing")
        if row.get("local_validation_required") is not True:
            row_diagnostics.append("local_validation_not_required")
        if str(row.get("runtime_action") or "none") != "none":
            row_diagnostics.append("runtime_action_requested")
        for diagnostic in row_diagnostics:
            diagnostics.append(f"{route_profile}:{diagnostic}")

        rows.append(
            {
                "route_profile": route_profile,
                "selected_local_lane": selected_lane,
                "allowed_local_lanes": allowed_local_lanes,
                "recommended_local_lane_order": [
                    lane
                    for lane in string_list(row.get("recommended_local_lane_order"))
                    if lane in allowed_lanes
                ],
                "validation_scope": f"local_{selected_lane}_lane_only" if selected_lane else "none",
                "evidence_item_ids": string_list(row.get("evidence_item_ids")),
                "evidence_item_id_count": len(string_list(row.get("evidence_item_ids"))),
                "candidate_source_hashes": string_list(row.get("candidate_source_hashes")),
                "candidate_count": int(row.get("candidate_count") or 0),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                    PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
                ],
                "plan_basis": "route_profile_selected_item_ids_and_hashed_candidate_sources",
                "diagnostics": sorted(dict.fromkeys(row_diagnostics)),
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
        )

    lane_validation_targets: list[dict[str, Any]] = []
    for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
        target_rows = [row for row in rows if row["selected_local_lane"] == lane]
        if not target_rows:
            continue
        evidence_item_ids = sorted(
            {
                item_id
                for row in target_rows
                for item_id in string_list(row.get("evidence_item_ids"))
            }
        )
        candidate_source_hashes = sorted(
            {
                source_hash
                for row in target_rows
                for source_hash in string_list(row.get("candidate_source_hashes"))
            }
        )
        lane_validation_targets.append(
            {
                "selected_local_lane": lane,
                "validation_scope": f"local_{lane}_lane_only",
                "route_profiles": [row["route_profile"] for row in target_rows],
                "route_profile_count": len(target_rows),
                "evidence_item_ids": evidence_item_ids,
                "evidence_item_id_count": len(evidence_item_ids),
                "candidate_source_hashes": candidate_source_hashes,
                "candidate_source_count": len(candidate_source_hashes),
                "candidate_count": sum(int(row.get("candidate_count") or 0) for row in target_rows),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                    PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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
            }
        )

    next_validation_target = skill_route_discovery_next_validation_target(
        lane_validation_targets=lane_validation_targets,
        has_next_pass=has_next_pass,
    )

    catalog_ready = route_discovery_catalog.get("status") == "ready"
    ready = bool(rows) and catalog_ready and not diagnostics
    if ready and has_next_pass:
        status = "ready"
        decision = "continue_bounded_local_validation_lane"
        supervisor_next_action = "continue_skill_route_discovery_window"
    elif ready:
        status = "ready"
        decision = "validate_final_bounded_local_lane_before_handoff"
        supervisor_next_action = "handoff_completed_skill_route_slice_to_supervisor"
    elif rows:
        status = "review"
        decision = "repair_validation_lane_plan_before_activation"
        supervisor_next_action = "replay_or_repair_bounded_lane_plan"
    else:
        status = "blocked"
        decision = "no_bounded_validation_lanes"
        supervisor_next_action = "replay_skill_route_discovery_lane"

    return {
        "controller_surface": "skill_route_discovery_validation_lane_plan",
        "status": status,
        "decision": decision,
        "supervisor_next_action": supervisor_next_action,
        "theme": optional_string(window.get("theme")) or "skill-route-discovery",
        "current_pass": current_pass,
        "next_pass": current_pass + 1 if has_next_pass else current_pass,
        "total_passes": total_passes,
        "remaining_pass_count": max(total_passes - current_pass, 0) if total_passes else 0,
        "catalog_status": str(route_discovery_catalog.get("status") or ""),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_lane_count": sum(1 for row in rows if row["selected_local_lane"]),
        "lane_validation_target_count": len(lane_validation_targets),
        "lane_validation_targets": lane_validation_targets,
        "next_validation_target": next_validation_target,
        "route_profile_count": len(rows),
        "rows": rows,
        "diagnostics": sorted(dict.fromkeys(diagnostics)),
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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


def skill_route_discovery_next_validation_target(
    *,
    lane_validation_targets: list[dict[str, Any]],
    has_next_pass: bool,
) -> dict[str, Any]:
    """Select one grouped local lane for the next scheduled pass."""

    lane_priority = {
        "test": 0,
        "config": 1,
        "documentation": 2,
        "code_patch": 3,
    }
    candidates = [
        target
        for target in lane_validation_targets
        if isinstance(target, dict)
        and optional_string(target.get("selected_local_lane")) in lane_priority
    ]
    candidates.sort(
        key=lambda target: (
            lane_priority[optional_string(target.get("selected_local_lane")) or ""],
            -int(target.get("route_profile_count") or 0),
            optional_string(target.get("selected_local_lane")) or "",
        )
    )

    selected = candidates[0] if candidates else {}
    selected_lane = optional_string(selected.get("selected_local_lane")) or "none"
    route_profiles = string_list(selected.get("route_profiles")) if selected else []
    evidence_item_ids = string_list(selected.get("evidence_item_ids")) if selected else []
    candidate_source_hashes = string_list(selected.get("candidate_source_hashes")) if selected else []
    status = "ready" if selected else "blocked"
    decision = (
        "continue_with_selected_bounded_validation_target"
        if selected and has_next_pass
        else "validate_selected_final_bounded_target"
        if selected
        else "no_bounded_validation_target_available"
    )
    supervisor_next_action = (
        "continue_skill_route_discovery_window"
        if selected and has_next_pass
        else "handoff_completed_skill_route_slice_to_supervisor"
        if selected
        else "replay_skill_route_discovery_lane"
    )

    return {
        "controller_surface": "skill_route_discovery_next_validation_target",
        "status": status,
        "decision": decision,
        "supervisor_next_action": supervisor_next_action,
        "selected_local_lane": selected_lane,
        "validation_scope": optional_string(selected.get("validation_scope"))
        if selected
        else "none",
        "route_profiles": route_profiles,
        "route_profile_count": len(route_profiles),
        "evidence_item_ids": evidence_item_ids,
        "evidence_item_id_count": len(evidence_item_ids),
        "candidate_source_hashes": candidate_source_hashes,
        "candidate_source_count": len(candidate_source_hashes),
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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


def skill_route_discovery_current_action(*, validation_lane_plan: dict[str, Any]) -> dict[str, Any]:
    """Lift the selected bounded lane into a compact supervisor action row."""

    next_target = validation_lane_plan.get("next_validation_target")
    next_target = next_target if isinstance(next_target, dict) else {}
    selected_lane = optional_string(next_target.get("selected_local_lane")) or "none"
    status = "ready" if validation_lane_plan.get("status") == "ready" and selected_lane != "none" else "blocked"
    has_next_pass = int(validation_lane_plan.get("remaining_pass_count") or 0) > 0
    decision = (
        "continue_selected_bounded_lane_next_pass"
        if status == "ready" and has_next_pass
        else "validate_selected_bounded_lane_for_handoff"
        if status == "ready"
        else "no_selected_bounded_lane_available"
    )
    supervisor_next_action = (
        "continue_skill_route_discovery_window"
        if status == "ready" and has_next_pass
        else "handoff_completed_skill_route_slice_to_supervisor"
        if status == "ready"
        else "replay_skill_route_discovery_lane"
    )
    diagnostics = string_list(validation_lane_plan.get("diagnostics"))
    if status != "ready" and not diagnostics:
        diagnostics = ["next_validation_target_not_ready"]

    return {
        "controller_surface": "skill_route_discovery_current_action",
        "status": status,
        "decision": decision,
        "supervisor_next_action": supervisor_next_action,
        "theme": optional_string(validation_lane_plan.get("theme")) or "skill-route-discovery",
        "current_pass": int(validation_lane_plan.get("current_pass") or 0),
        "next_pass": int(validation_lane_plan.get("next_pass") or 0),
        "total_passes": int(validation_lane_plan.get("total_passes") or 0),
        "remaining_pass_count": int(validation_lane_plan.get("remaining_pass_count") or 0),
        "selected_local_lane": selected_lane,
        "validation_scope": optional_string(next_target.get("validation_scope")) or "none",
        "route_profiles": string_list(next_target.get("route_profiles")),
        "route_profile_count": int(next_target.get("route_profile_count") or 0),
        "evidence_ref_mode": "selected_item_ids_only",
        "evidence_item_ids": string_list(next_target.get("evidence_item_ids")),
        "evidence_item_id_count": int(next_target.get("evidence_item_id_count") or 0),
        "candidate_source_hashes": string_list(next_target.get("candidate_source_hashes")),
        "candidate_source_count": int(next_target.get("candidate_source_count") or 0),
        "required_validation": string_list(validation_lane_plan.get("required_validation")),
        "provider_runtime_replay_commands": string_list(
            validation_lane_plan.get("provider_runtime_replay_commands")
        ),
        "plan_basis": "validation_lane_plan_next_validation_target",
        "diagnostics": diagnostics,
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


def skill_route_discovery_domain_validation_probe(
    *,
    validation_lane_plan: dict[str, Any],
) -> dict[str, Any]:
    """Surface domain-specific skill routes as local validation lanes only."""

    plan_rows = validation_lane_plan.get("rows")
    plan_rows = plan_rows if isinstance(plan_rows, list) else []
    domain_profiles = {"game_frontend_workflow"}
    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    for plan_row in plan_rows:
        if not isinstance(plan_row, dict):
            continue
        route_profile = optional_string(plan_row.get("route_profile")) or "generic_skill_workflow"
        if route_profile not in domain_profiles:
            continue

        selected_lane = optional_string(plan_row.get("selected_local_lane")) or ""
        recommended_order = string_list(plan_row.get("recommended_local_lane_order"))
        probe_lane = selected_lane or ("test" if "test" in recommended_order else "")
        row_diagnostics = [
            diagnostic
            for diagnostic in string_list(plan_row.get("diagnostics"))
            if diagnostic not in {"selected_local_lane_not_bounded", "selected_local_lane_not_ready"}
            or not probe_lane
        ]
        if probe_lane != "test":
            row_diagnostics.append("domain_skill_requires_local_test_lane")
        if int(plan_row.get("evidence_item_id_count") or 0) <= 0:
            row_diagnostics.append("selected_digest_item_id_missing")
        if plan_row.get("local_validation_required") is not True:
            row_diagnostics.append("local_validation_not_required")
        if str(plan_row.get("runtime_action") or "none") != "none":
            row_diagnostics.append("runtime_action_requested")
        if plan_row.get("external_skill_activation_allowed") is not False:
            row_diagnostics.append("external_skill_activation_not_denied")
        if plan_row.get("external_skill_code_allowed") is not False:
            row_diagnostics.append("external_skill_code_not_denied")

        row_diagnostics = sorted(dict.fromkeys(row_diagnostics))
        diagnostics.extend(f"{route_profile}:{diagnostic}" for diagnostic in row_diagnostics)
        rows.append(
            {
                "route_profile": route_profile,
                "domain": "threejs_browser_game",
                "selected_local_lane": probe_lane,
                "validation_scope": optional_string(plan_row.get("validation_scope"))
                or (f"local_{probe_lane}_lane_only" if probe_lane else "none"),
                "probe_status": "ready" if not row_diagnostics else "review",
                "candidate_count": int(plan_row.get("candidate_count") or 0),
                "evidence_item_ids": string_list(plan_row.get("evidence_item_ids")),
                "evidence_item_id_count": len(string_list(plan_row.get("evidence_item_ids"))),
                "candidate_source_hashes": string_list(plan_row.get("candidate_source_hashes")),
                "required_validation": [
                    SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND,
                    "pytest tests/test_harness_eval.py -q -k rendered_html_artifact_validation",
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                ],
                "classification_checks": {
                    "domain_profile_matched": True,
                    "local_test_lane_selected": probe_lane == "test",
                    "non_execution_behavior": True,
                    "body_free": True,
                },
                "activation_gate": "local_test_validation_before_domain_skill_activation",
                "diagnostics": row_diagnostics,
                "local_validation_required": True,
                "runtime_action": "none",
                "runtime_action_allowed": False,
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "external_harness_execution_allowed": False,
                "upstream_scaffold_allowed": False,
                "upstream_browser_checker_allowed": False,
                "asset_generation_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_evidence_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    ready = bool(rows) and not diagnostics
    return {
        "controller_surface": "skill_route_discovery_domain_validation_probe",
        "status": "ready" if ready else "review" if rows else "not_applicable",
        "decision": "domain_skill_route_ready_for_local_test_replay"
        if ready
        else "review_domain_skill_route_before_local_replay"
        if rows
        else "no_domain_skill_route_present",
        "domain_profile_count": len(rows),
        "rows": rows,
        "diagnostics": sorted(dict.fromkeys(diagnostics)),
        "local_validation_required": bool(rows),
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "upstream_scaffold_allowed": False,
        "upstream_browser_checker_allowed": False,
        "asset_generation_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_profile_validation_replay(
    *,
    validation_lane_plan: dict[str, Any],
) -> dict[str, Any]:
    """Project selected profile lanes into a bounded local replay checklist."""

    replay_step_by_lane = {
        "documentation": "review_local_documentation_lane_for_route_contract",
        "config": "review_local_config_lane_for_state_handoff",
        "test": "replay_local_test_lane_for_workflow_or_game_route",
        "code_patch": "review_local_code_patch_lane_for_route_behavior",
    }
    plan_rows = validation_lane_plan.get("rows")
    plan_rows = plan_rows if isinstance(plan_rows, list) else []
    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    for plan_row in plan_rows:
        if not isinstance(plan_row, dict):
            continue
        route_profile = optional_string(plan_row.get("route_profile")) or "generic_skill_workflow"
        selected_lane = optional_string(plan_row.get("selected_local_lane")) or ""
        row_diagnostics = string_list(plan_row.get("diagnostics"))
        if not selected_lane:
            row_diagnostics.append("selected_local_lane_missing")
        if plan_row.get("local_validation_required") is not True:
            row_diagnostics.append("local_validation_not_required")
        if str(plan_row.get("runtime_action") or "none") != "none":
            row_diagnostics.append("runtime_action_requested")
        if plan_row.get("raw_evidence_urls_exported") is not False:
            row_diagnostics.append("raw_evidence_urls_exported")
        if plan_row.get("raw_source_urls_exported") is not False:
            row_diagnostics.append("raw_source_urls_exported")
        for diagnostic in row_diagnostics:
            diagnostics.append(f"{route_profile}:{diagnostic}")

        rows.append(
            {
                "route_profile": route_profile,
                "selected_local_lane": selected_lane,
                "validation_scope": optional_string(plan_row.get("validation_scope"))
                or (f"local_{selected_lane}_lane_only" if selected_lane else "none"),
                "operator_replay_step": replay_step_by_lane.get(
                    selected_lane,
                    "repair_selected_profile_lane_before_replay",
                ),
                "recommended_local_lane_order": string_list(plan_row.get("recommended_local_lane_order")),
                "evidence_item_ids": string_list(plan_row.get("evidence_item_ids")),
                "evidence_item_id_count": len(string_list(plan_row.get("evidence_item_ids"))),
                "candidate_source_hashes": string_list(plan_row.get("candidate_source_hashes")),
                "candidate_source_count": len(string_list(plan_row.get("candidate_source_hashes"))),
                "candidate_count": int(plan_row.get("candidate_count") or 0),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                    PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
                ],
                "plan_basis": "selected_profile_item_ids_and_hashed_candidate_sources",
                "diagnostics": sorted(dict.fromkeys(row_diagnostics)),
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
        )

    plan_status = str(validation_lane_plan.get("status") or "")
    if rows and plan_status == "ready" and not diagnostics:
        status = "ready"
        decision = "replay_selected_profile_validation_lanes"
    elif rows:
        status = "review"
        decision = "repair_profile_validation_replay_before_continuing"
    else:
        status = "blocked"
        decision = "no_profile_validation_replay_rows"

    return {
        "controller_surface": "skill_route_discovery_profile_validation_replay",
        "status": status,
        "decision": decision,
        "validation_plan_status": plan_status,
        "validation_plan_decision": str(validation_lane_plan.get("decision") or ""),
        "supervisor_next_action": str(validation_lane_plan.get("supervisor_next_action") or ""),
        "next_validation_target": validation_lane_plan.get("next_validation_target")
        if isinstance(validation_lane_plan.get("next_validation_target"), dict)
        else {},
        "profile_count": len(rows),
        "selected_local_lanes": sorted({row["selected_local_lane"] for row in rows if row["selected_local_lane"]}),
        "rows": rows,
        "diagnostics": sorted(dict.fromkeys(diagnostics)),
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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


def skill_route_discovery_capability_window_completion(
    *,
    raw_input: dict[str, Any],
    route_status: str,
    failure_mode: str,
    route_profile_review: dict[str, Any],
    activation_manifest: dict[str, Any],
    candidate_lane_intake: dict[str, Any],
    operator_handoff: dict[str, Any],
    supervisor_readiness: dict[str, Any],
    validation_lane_plan: dict[str, Any],
    profile_validation_replay: dict[str, Any],
    provider_runtime_diagnostic_panel: dict[str, Any],
    provider_runtime_replay_sample: dict[str, Any],
) -> dict[str, Any]:
    """Summarize completion readiness for a multi-pass skill-route slice."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    window = raw_input.get("capability_window")
    window = window if isinstance(window, dict) else {}
    theme = optional_string(window.get("theme")) or "skill-route-discovery"
    capability_slice = optional_string(window.get("capability_slice")) or (
        "Convert skill and route evidence into bounded local lanes that can be validated before activation."
    )
    current_pass = int(window.get("current_pass") or window.get("planned_pass") or 0)
    total_passes = int(window.get("total_passes") or 0)
    anchoring_proposals = string_list(window.get("anchoring_proposals"))
    required_route_profiles = sorted(dict.fromkeys(string_list(window.get("required_route_profiles"))))
    evidence_url_hashes = [
        stable_text_hash(url) for url in string_list(window.get("evidence_urls"))
    ]

    manifest_lanes = activation_manifest.get("manifest_lanes")
    manifest_lanes = manifest_lanes if isinstance(manifest_lanes, list) else []
    route_profile_rows = route_profile_review.get("rows")
    route_profile_rows = route_profile_rows if isinstance(route_profile_rows, list) else []
    proposal_kinds = sorted({str(lane.get("proposal_kind") or "") for lane in manifest_lanes})
    route_profiles = sorted({str(row.get("route_profile") or "") for row in route_profile_rows})
    selected_evidence_refs = sorted(
        {
            str(ref)
            for lane in manifest_lanes
            for ref in string_list(lane.get("evidence_refs"))
            if str(ref)
        }
    )
    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    lanes_bounded = bool(proposal_kinds) and set(proposal_kinds) <= allowed_lanes
    manifest_ready = activation_manifest.get("status") == "ready"
    profile_review_ready = route_profile_review.get("status") == "ready"
    handoff_ready = operator_handoff.get("status") == "ready"
    supervisor_ready = supervisor_readiness.get("decision") == "ready_for_supervisor_promotion"
    provider_replay_ready = provider_runtime_diagnostic_panel.get("status") == "ready"
    provider_runtime_sample_gate = skill_route_discovery_provider_runtime_sample_gate(
        window=window,
        provider_runtime_replay_sample=provider_runtime_replay_sample,
    )
    validation_target_handoff = skill_route_discovery_validation_target_handoff(
        validation_lane_plan=validation_lane_plan,
    )
    planned_window_complete = bool(current_pass and total_passes and current_pass >= total_passes)
    profile_completion_check = skill_route_discovery_profile_completion_check(
        required_route_profiles=required_route_profiles,
        observed_route_profiles=route_profiles,
        planned_window_complete=planned_window_complete,
    )

    diagnostics: list[str] = []
    if route_status != "passed" or failure_mode != "none":
        diagnostics.append(f"route_not_passed:{failure_mode or route_status}")
    if not lanes_bounded:
        diagnostics.append("manifest_lanes_not_bounded")
    if not profile_review_ready:
        diagnostics.append("route_profile_review_not_ready")
    if not manifest_ready:
        diagnostics.append("activation_manifest_not_ready")
    if not handoff_ready:
        diagnostics.append("operator_handoff_not_ready")
    if not supervisor_ready:
        diagnostics.append("supervisor_readiness_not_ready")
    if not provider_replay_ready:
        diagnostics.append("provider_runtime_replay_not_ready")
    if provider_runtime_sample_gate["status"] != "ready":
        diagnostics.append(str(provider_runtime_sample_gate["diagnostic"]))
    if profile_completion_check["status"] != "ready":
        diagnostics.append(
            "required_route_profiles_missing:"
            + ",".join(profile_completion_check["missing_route_profiles"])
        )
    if total_passes and not planned_window_complete:
        diagnostics.append("capability_window_not_at_final_pass")

    waiting_for_planned_pass = diagnostics == ["capability_window_not_at_final_pass"] and bool(manifest_lanes)
    ready = not diagnostics and bool(manifest_lanes)
    if ready:
        status = "ready"
        decision = "complete_slice_for_supervisor_handoff"
        completion_next_action = "handoff_completed_skill_route_slice_to_supervisor"
    elif waiting_for_planned_pass:
        status = "in_progress"
        decision = "continue_capability_window_before_completion"
        completion_next_action = "continue_capability_window_before_completion"
    else:
        status = "blocked"
        decision = "continue_or_replay_before_completion"
        completion_next_action = "replay_or_repair_before_supervisor_handoff"
    next_pass_handoff = skill_route_discovery_next_pass_handoff(
        status=status,
        decision=decision,
        current_pass=current_pass,
        total_passes=total_passes,
        diagnostics=diagnostics,
        proposal_kinds=proposal_kinds,
        route_profiles=route_profiles,
        selected_evidence_refs=selected_evidence_refs,
        candidate_lane_intake=candidate_lane_intake,
        validation_lane_plan=validation_lane_plan,
    )
    completion_recovery = skill_route_discovery_completion_recovery(
        status=status,
        diagnostics=diagnostics,
        profile_completion_check=profile_completion_check,
        next_pass_handoff=next_pass_handoff,
    )
    activation_packet = skill_route_discovery_validated_activation_packet(
        activation_manifest=activation_manifest,
        status=status,
        diagnostics=diagnostics,
    )
    final_slice_closure = skill_route_discovery_final_slice_closure(
        status=status,
        decision=decision,
        completion_next_action=completion_next_action,
        theme=theme,
        current_pass=current_pass,
        total_passes=total_passes,
        planned_window_complete=planned_window_complete,
        proposal_kinds=proposal_kinds,
        route_profiles=route_profiles,
        selected_evidence_refs=selected_evidence_refs,
        diagnostics=diagnostics,
        profile_completion_check=profile_completion_check,
        validation_target_handoff=validation_target_handoff,
        profile_validation_replay=profile_validation_replay,
        activation_manifest=activation_manifest,
        activation_packet=activation_packet,
        completion_recovery=completion_recovery,
    )
    completion_handoff = {
        "status": status,
        "decision": decision,
        "supervisor_next_action": completion_next_action,
        "activation_sequence_status": str(
            activation_manifest.get("activation_sequence", {}).get("status")
            if isinstance(activation_manifest.get("activation_sequence"), dict)
            else ""
        ),
        "final_pass_required": bool(total_passes),
        "final_pass_observed": planned_window_complete,
        "selected_evidence_ref_count": len(selected_evidence_refs),
        "selected_evidence_refs": selected_evidence_refs,
        "completion_blockers": diagnostics,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "provider_runtime_sample_gate": provider_runtime_sample_gate,
        "validation_target_handoff": validation_target_handoff,
        "profile_validation_replay": profile_validation_replay,
        "profile_completion_check": profile_completion_check,
        "completion_recovery": completion_recovery,
        "next_pass_handoff": next_pass_handoff,
        "activation_packet": activation_packet,
        "final_slice_closure": final_slice_closure,
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }
    return {
        "controller_surface": "skill_route_discovery_capability_window_completion",
        "status": status,
        "decision": decision,
        "theme": theme,
        "capability_slice": capability_slice,
        "current_pass": current_pass,
        "total_passes": total_passes,
        "planned_window_complete": planned_window_complete,
        "anchoring_proposal_count": len(anchoring_proposals),
        "anchoring_proposal_hashes": [stable_text_hash(proposal) for proposal in anchoring_proposals],
        "evidence_url_count": len(evidence_url_hashes),
        "evidence_url_hashes": evidence_url_hashes,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "proposal_kinds": proposal_kinds,
        "route_profiles": route_profiles,
        "lane_count": len(manifest_lanes),
        "route_profile_count": len(route_profiles),
        "manifest_ready": manifest_ready,
        "profile_review_ready": profile_review_ready,
        "operator_handoff_ready": handoff_ready,
        "supervisor_ready": supervisor_ready,
        "provider_runtime_replay_ready": provider_replay_ready,
        "provider_runtime_sample_gate": provider_runtime_sample_gate,
        "validation_target_handoff": validation_target_handoff,
        "profile_validation_replay": profile_validation_replay,
        "profile_completion_check": profile_completion_check,
        "next_pass_handoff": next_pass_handoff,
        "completion_recovery": completion_recovery,
        "activation_packet": activation_packet,
        "final_slice_closure": final_slice_closure,
        "completion_handoff": completion_handoff,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "diagnostics": diagnostics,
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


def skill_route_discovery_operator_activation_lane(
    *,
    rows: list[dict[str, Any]],
    packet_ready: bool,
    diagnostics: list[str],
) -> dict[str, Any]:
    """Summarize validated local lanes as the supervisor's bounded activation queue."""

    ready_rows = [
        row
        for row in rows
        if row.get("activation_ready") is True
        and row.get("local_artifact_proof_ready") is True
        and not string_list(row.get("activation_blockers"))
    ]
    lane_rows: list[dict[str, Any]] = []
    for row in rows:
        activation_blockers = string_list(row.get("activation_blockers"))
        lane_ready = row in ready_rows and packet_ready and not diagnostics
        lane_rows.append(
            {
                "proposal_kind": str(row.get("proposal_kind") or ""),
                "route_profiles": string_list(row.get("route_profiles")),
                "evidence_ref_count": int(row.get("evidence_ref_count") or 0),
                "candidate_count": int(row.get("candidate_count") or 0),
                "candidate_source_count": len(string_list(row.get("candidate_source_hashes"))),
                "target_path_count": len(string_list(row.get("target_path_hashes"))),
                "local_artifact_proof_ready": row.get("local_artifact_proof_ready") is True,
                "activation_ready": row.get("activation_ready") is True,
                "operator_lane_ready": lane_ready,
                "activation_blocker_count": len(activation_blockers),
                "activation_blocker_hashes": [stable_text_hash(blocker) for blocker in activation_blockers],
                "supervisor_replay_step": str(row.get("supervisor_replay_step") or ""),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                    PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
                ],
                "runtime_action": "none",
                "local_validation_required": True,
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
        )

    ready_lane_count = sum(1 for row in lane_rows if row["operator_lane_ready"])
    status = "ready" if packet_ready and ready_lane_count == len(lane_rows) and lane_rows else "blocked"
    decision = (
        "operator_lane_ready_for_supervisor_replay"
        if status == "ready"
        else "operator_lane_waiting_for_local_repair"
    )
    return {
        "controller_surface": "skill_route_discovery_operator_activation_lane",
        "status": status,
        "decision": decision,
        "supervisor_next_action": (
            "replay_validated_local_lanes_then_handoff"
            if status == "ready"
            else "repair_local_lane_proof_before_replay"
        ),
        "lane_count": len(lane_rows),
        "ready_lane_count": ready_lane_count,
        "blocked_lane_count": len(lane_rows) - ready_lane_count,
        "proposal_kinds": sorted({row["proposal_kind"] for row in lane_rows if row["proposal_kind"]}),
        "route_profiles": sorted(
            {
                profile
                for row in lane_rows
                for profile in string_list(row.get("route_profiles"))
            }
        ),
        "diagnostic_count": len(diagnostics),
        "diagnostic_hashes": [stable_text_hash(diagnostic) for diagnostic in diagnostics],
        "lanes": lane_rows,
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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


def skill_route_discovery_final_slice_closure(
    *,
    status: str,
    decision: str,
    completion_next_action: str,
    theme: str,
    current_pass: int,
    total_passes: int,
    planned_window_complete: bool,
    proposal_kinds: list[str],
    route_profiles: list[str],
    selected_evidence_refs: list[str],
    diagnostics: list[str],
    profile_completion_check: dict[str, Any],
    validation_target_handoff: dict[str, Any],
    profile_validation_replay: dict[str, Any],
    activation_manifest: dict[str, Any],
    activation_packet: dict[str, Any],
    completion_recovery: dict[str, Any],
) -> dict[str, Any]:
    """Render final-pass closure as one supervisor-visible route decision."""

    replay_rows = profile_validation_replay.get("rows")
    replay_rows = replay_rows if isinstance(replay_rows, list) else []
    profile_rows: list[dict[str, Any]] = []
    for row in replay_rows:
        if not isinstance(row, dict):
            continue
        profile_rows.append(
            {
                "route_profile": optional_string(row.get("route_profile")) or "generic_skill_workflow",
                "selected_local_lane": optional_string(row.get("selected_local_lane")) or "",
                "validation_scope": optional_string(row.get("validation_scope")) or "none",
                "operator_replay_step": optional_string(row.get("operator_replay_step"))
                or "repair_selected_profile_lane_before_replay",
                "evidence_item_ids": string_list(row.get("evidence_item_ids")),
                "evidence_item_id_count": len(string_list(row.get("evidence_item_ids"))),
                "candidate_source_hashes": string_list(row.get("candidate_source_hashes")),
                "candidate_source_count": len(string_list(row.get("candidate_source_hashes"))),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                    PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
                ],
                "diagnostics": string_list(row.get("diagnostics")),
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
        )

    if status == "ready":
        closure_decision = "close_skill_route_discovery_slice"
    elif status == "in_progress":
        closure_decision = "continue_skill_route_discovery_slice"
    else:
        closure_decision = "repair_skill_route_discovery_slice_before_handoff"

    return {
        "controller_surface": "skill_route_discovery_final_slice_closure",
        "status": status,
        "decision": closure_decision,
        "completion_decision": decision,
        "supervisor_next_action": completion_next_action,
        "theme": theme,
        "current_pass": current_pass,
        "total_passes": total_passes,
        "planned_window_complete": planned_window_complete,
        "final_pass_required": bool(total_passes),
        "final_pass_observed": planned_window_complete,
        "proposal_kinds": proposal_kinds,
        "route_profiles": route_profiles,
        "required_route_profiles": string_list(profile_completion_check.get("required_route_profiles")),
        "missing_route_profiles": string_list(profile_completion_check.get("missing_route_profiles")),
        "selected_evidence_ref_count": len(selected_evidence_refs),
        "selected_evidence_refs": selected_evidence_refs,
        "selected_local_lanes": string_list(validation_target_handoff.get("selected_local_lanes")),
        "validation_target_count": int(validation_target_handoff.get("target_count") or 0),
        "profile_replay_status": str(profile_validation_replay.get("status") or ""),
        "profile_rows": profile_rows,
        "activation_manifest_status": str(activation_manifest.get("status") or ""),
        "activation_sequence_status": str(
            activation_manifest.get("activation_sequence", {}).get("status")
            if isinstance(activation_manifest.get("activation_sequence"), dict)
            else ""
        ),
        "activation_packet_status": str(activation_packet.get("status") or ""),
        "activation_packet_decision": str(activation_packet.get("decision") or ""),
        "completion_recovery_status": str(completion_recovery.get("status") or ""),
        "completion_recovery_decision": str(completion_recovery.get("decision") or ""),
        "completion_blocker_count": len(diagnostics),
        "completion_blocker_hashes": [stable_text_hash(diagnostic) for diagnostic in diagnostics],
        "recovery_hint_codes": string_list(completion_recovery.get("recovery_hint_codes")),
        "replay_commands": string_list(completion_recovery.get("replay_commands")),
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "supervisor_handoff_ready": status == "ready",
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


def skill_route_discovery_validation_target_handoff(
    *,
    validation_lane_plan: dict[str, Any],
) -> dict[str, Any]:
    """Project the pass-to-pass validation plan into completion handoff metadata."""

    targets = validation_lane_plan.get("lane_validation_targets")
    targets = targets if isinstance(targets, list) else []
    rows: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        selected_lane = optional_string(target.get("selected_local_lane")) or ""
        route_profiles = string_list(target.get("route_profiles"))
        rows.append(
            {
                "selected_local_lane": selected_lane,
                "validation_scope": optional_string(target.get("validation_scope"))
                or (f"local_{selected_lane}_lane_only" if selected_lane else "none"),
                "route_profiles": route_profiles,
                "route_profile_count": len(route_profiles),
                "evidence_item_ids": string_list(target.get("evidence_item_ids")),
                "evidence_item_id_count": len(string_list(target.get("evidence_item_ids"))),
                "candidate_source_hashes": string_list(target.get("candidate_source_hashes")),
                "candidate_source_count": len(string_list(target.get("candidate_source_hashes"))),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "provider_runtime_replay_commands": [
                    PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                    PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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
        )

    plan_status = str(validation_lane_plan.get("status") or "")
    if rows and plan_status == "ready":
        status = "ready"
        decision = "continue_with_bounded_validation_targets"
    elif rows:
        status = "review"
        decision = "repair_validation_targets_before_continuing"
    else:
        status = "blocked"
        decision = "no_validation_targets_available"

    return {
        "controller_surface": "skill_route_discovery_validation_target_handoff",
        "status": status,
        "decision": decision,
        "validation_plan_status": plan_status,
        "validation_plan_decision": str(validation_lane_plan.get("decision") or ""),
        "supervisor_next_action": str(validation_lane_plan.get("supervisor_next_action") or ""),
        "target_count": len(rows),
        "selected_local_lanes": sorted({row["selected_local_lane"] for row in rows if row["selected_local_lane"]}),
        "route_profiles": sorted(
            {
                profile
                for row in rows
                for profile in string_list(row.get("route_profiles"))
            }
        ),
        "targets": rows,
        "next_validation_target": validation_lane_plan.get("next_validation_target")
        if isinstance(validation_lane_plan.get("next_validation_target"), dict)
        else {},
        "required_validation": skill_route_discovery_preactivation_validation_commands(),
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
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


def skill_route_discovery_completion_recovery(
    *,
    status: str,
    diagnostics: list[str],
    profile_completion_check: dict[str, Any],
    next_pass_handoff: dict[str, Any],
) -> dict[str, Any]:
    """Choose the next bounded replay lane for completion handoff repair."""

    lane_order = [
        lane
        for lane in string_list(next_pass_handoff.get("recommended_local_lane_order"))
        if lane in {"documentation", "config", "test", "code_patch"}
    ]
    missing_profiles = string_list(profile_completion_check.get("missing_route_profiles"))
    diagnostics = sorted(dict.fromkeys(str(diagnostic) for diagnostic in diagnostics if str(diagnostic)))

    if status == "ready":
        recovery_status = "ready"
        recovery_decision = "no_recovery_required"
        supervisor_next_action = "handoff_completed_skill_route_slice_to_supervisor"
        primary_recovery_lane = "none"
        recovery_hint_codes: list[str] = []
        replay_commands = []
    elif diagnostics == ["capability_window_not_at_final_pass"]:
        recovery_status = "in_progress"
        recovery_decision = "continue_capability_window"
        supervisor_next_action = "continue_skill_route_discovery_window"
        primary_recovery_lane = lane_order[0] if lane_order else "test"
        recovery_hint_codes = ["capability_window_not_at_final_pass"]
        replay_commands = [SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND]
    else:
        recovery_status = "blocked"
        if missing_profiles:
            recovery_decision = "replay_required_route_profiles"
            supervisor_next_action = "repair_missing_route_profiles_before_supervisor_handoff"
            primary_recovery_lane = "test"
            recovery_hint_codes = ["required_route_profiles_missing"]
            replay_commands = [SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND]
        elif "activation_manifest_not_ready" in diagnostics or "operator_handoff_not_ready" in diagnostics:
            recovery_decision = "repair_local_artifact_proof"
            supervisor_next_action = "repair_local_artifact_proof_before_supervisor_handoff"
            primary_recovery_lane = lane_order[0] if lane_order else "test"
            recovery_hint_codes = ["local_artifact_proof_not_ready"]
            replay_commands = [SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND]
        elif (
            "provider_runtime_replay_not_ready" in diagnostics
            or "provider_runtime_preflight_sample_missing" in diagnostics
        ):
            recovery_decision = "replay_provider_runtime_preflight"
            supervisor_next_action = "replay_provider_runtime_before_supervisor_handoff"
            primary_recovery_lane = "test"
            recovery_hint_codes = [
                "provider_runtime_preflight_sample_missing"
                if "provider_runtime_preflight_sample_missing" in diagnostics
                else "provider_runtime_replay_not_ready"
            ]
            replay_commands = [
                PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
                PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
            ]
        elif "route_profile_review_not_ready" in diagnostics:
            recovery_decision = "repair_route_profile_review"
            supervisor_next_action = "repair_profile_metadata_before_supervisor_handoff"
            primary_recovery_lane = "documentation"
            recovery_hint_codes = ["route_profile_review_not_ready"]
            replay_commands = [SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND]
        else:
            recovery_decision = "replay_bounded_skill_route_lane"
            supervisor_next_action = "replay_or_repair_before_supervisor_handoff"
            primary_recovery_lane = lane_order[0] if lane_order else "test"
            recovery_hint_codes = ["skill_route_completion_blocked"]
            replay_commands = [SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND]

    return {
        "controller_surface": "skill_route_discovery_completion_recovery",
        "status": recovery_status,
        "decision": recovery_decision,
        "supervisor_next_action": supervisor_next_action,
        "primary_recovery_lane": primary_recovery_lane,
        "recommended_local_lane_order": lane_order,
        "missing_route_profiles": missing_profiles,
        "completion_blocker_count": len(diagnostics),
        "completion_blocker_hashes": [stable_text_hash(diagnostic) for diagnostic in diagnostics],
        "recovery_hint_codes": recovery_hint_codes,
        "recovery_hint_code_hashes": [stable_text_hash(code) for code in recovery_hint_codes],
        "replay_commands": replay_commands,
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


def skill_route_discovery_provider_runtime_sample_gate(
    *,
    window: dict[str, Any],
    provider_runtime_replay_sample: dict[str, Any],
) -> dict[str, Any]:
    """Require a replayable provider/runtime sample for provider-runtime-control windows."""

    theme = (optional_string(window.get("theme")) or "").lower()
    capability_slice = (optional_string(window.get("capability_slice")) or "").lower()
    required = (
        truthy(window.get("require_provider_runtime_preflight_sample"))
        or theme == "provider-runtime-control"
        or "provider and runtime preflight" in capability_slice
    )
    provided = provider_runtime_replay_sample.get("provided") is True
    sample_ready = provider_runtime_replay_sample.get("ready_for_local_replay") is True
    promotion_ready = provider_runtime_replay_sample.get("ready_for_supervisor_promotion") is True
    degraded_replay_only = provider_runtime_replay_sample.get("degraded_replay_only") is True
    if not required:
        status = "ready"
        decision = "sample_optional_for_this_window"
        diagnostic = "none"
        next_action = "continue_skill_route_discovery_window"
    elif not provided:
        status = "blocked"
        decision = "provider_runtime_preflight_sample_required"
        diagnostic = "provider_runtime_preflight_sample_missing"
        next_action = "add_body_free_provider_runtime_preflight_sample_then_replay"
    elif sample_ready:
        status = "ready"
        decision = "provider_runtime_preflight_sample_ready"
        diagnostic = "none"
        next_action = "continue_skill_route_discovery_window"
    else:
        status = "blocked"
        decision = "provider_runtime_preflight_sample_not_ready"
        diagnostic = "provider_runtime_replay_not_ready"
        next_action = "resolve_sample_recovery_hints_then_replay_preflight"

    return {
        "controller_surface": "provider_runtime_sample_gate",
        "status": status,
        "decision": decision,
        "diagnostic": diagnostic,
        "next_action": next_action,
        "required": required,
        "provided": provided,
        "ready_for_local_replay": sample_ready,
        "ready_for_supervisor_promotion": promotion_ready,
        "degraded_replay_only": degraded_replay_only,
        "success_claim_allowed": provider_runtime_replay_sample.get("success_claim_allowed") is True,
        "success_status_label": str(provider_runtime_replay_sample.get("success_status_label") or ""),
        "sample_failure_mode": str(provider_runtime_replay_sample.get("failure_mode") or "none"),
        "sample_recovery_hint_count": len(string_list(provider_runtime_replay_sample.get("recovery_hint_codes"))),
        "replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "local_validation_required": True,
        "body_free": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_provider_values_exported": False,
    }


def skill_route_discovery_next_pass_handoff(
    *,
    status: str,
    decision: str,
    current_pass: int,
    total_passes: int,
    diagnostics: list[str],
    proposal_kinds: list[str],
    route_profiles: list[str],
    selected_evidence_refs: list[str],
    candidate_lane_intake: dict[str, Any],
    validation_lane_plan: dict[str, Any],
) -> dict[str, Any]:
    """Describe the bounded local work a supervisor can continue on the next pass."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    rows = candidate_lane_intake.get("rows")
    rows = rows if isinstance(rows, list) else []
    lane_order: list[str] = []
    candidate_hashes: list[str] = []
    source_hashes: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_hash = optional_string(row.get("candidate_name_hash"))
        source_hash = optional_string(row.get("source_hash"))
        if candidate_hash:
            candidate_hashes.append(candidate_hash)
        if source_hash:
            source_hashes.append(source_hash)
        for lane in string_list(row.get("recommended_local_lane_order")):
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES and lane not in lane_order:
                lane_order.append(lane)
    for lane in proposal_kinds:
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES and lane not in lane_order:
            lane_order.append(lane)
    next_validation_target = validation_lane_plan.get("next_validation_target")
    next_validation_target = next_validation_target if isinstance(next_validation_target, dict) else {}

    has_next_pass = bool(current_pass and total_passes and current_pass < total_passes)
    blocked = status == "blocked"
    if has_next_pass and not blocked:
        handoff_status = "ready"
        handoff_decision = "continue_bounded_lane_validation_next_pass"
        supervisor_next_action = "continue_skill_route_discovery_window"
    elif has_next_pass:
        handoff_status = "blocked"
        handoff_decision = "repair_current_pass_before_continuing"
        supervisor_next_action = "replay_or_repair_before_next_pass"
    else:
        handoff_status = "complete" if status == "ready" else "blocked"
        handoff_decision = "no_next_pass_required" if status == "ready" else "repair_before_completion"
        supervisor_next_action = "handoff_completed_skill_route_slice_to_supervisor" if status == "ready" else (
            "replay_or_repair_before_supervisor_handoff"
        )

    return {
        "controller_surface": "skill_route_discovery_next_pass_handoff",
        "status": handoff_status,
        "decision": handoff_decision,
        "supervisor_next_action": supervisor_next_action,
        "current_pass": current_pass,
        "next_pass": current_pass + 1 if has_next_pass else current_pass,
        "total_passes": total_passes,
        "remaining_pass_count": max(total_passes - current_pass, 0) if total_passes else 0,
        "candidate_count": len(rows),
        "candidate_name_hashes": sorted(dict.fromkeys(candidate_hashes)),
        "source_hashes": sorted(dict.fromkeys(source_hashes)),
        "recommended_local_lane_order": lane_order,
        "next_validation_target": next_validation_target,
        "proposal_kinds": proposal_kinds,
        "route_profiles": route_profiles,
        "selected_evidence_ref_count": len(selected_evidence_refs),
        "selected_evidence_refs": selected_evidence_refs,
        "completion_blockers": diagnostics,
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


def skill_route_discovery_profile_completion_check(
    *,
    required_route_profiles: list[str],
    observed_route_profiles: list[str],
    planned_window_complete: bool,
) -> dict[str, Any]:
    """Check final-pass route-profile coverage without exporting source evidence."""

    required = sorted(dict.fromkeys(required_route_profiles))
    observed = sorted(dict.fromkeys(observed_route_profiles))
    missing = sorted(set(required) - set(observed))
    enforced = planned_window_complete and bool(required)
    ready = not enforced or not missing
    return {
        "controller_surface": "skill_route_discovery_profile_completion_check",
        "status": "ready" if ready else "blocked",
        "decision": "profile_requirements_satisfied"
        if ready
        else "replay_missing_route_profiles_before_completion",
        "required_route_profiles": required,
        "observed_route_profiles": observed,
        "missing_route_profiles": missing,
        "required_profile_count": len(required),
        "observed_profile_count": len(observed),
        "planned_window_complete": planned_window_complete,
        "enforced": enforced,
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


def skill_route_discovery_local_lane_intake(
    *,
    proposal_lanes: list[dict[str, Any]],
    activation_lanes: list[dict[str, Any]],
    activation_gate: dict[str, Any],
    evidence_strength: dict[str, Any],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    """Render bounded implementation lanes before any supervisor activation.

    This is the operator-visible intake contract for public skill repositories:
    external evidence may name local documentation, config, test, or code_patch
    work, but the handoff exports only hashes and local validation requirements.
    """

    from blackhole_agent.skill_routing import (
        SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
        SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS,
    )

    activation_by_kind = {
        str(lane.get("proposal_kind") or ""): lane for lane in activation_lanes if str(lane.get("proposal_kind") or "")
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for lane in proposal_lanes:
        proposal_kind = str(lane.get("proposal_kind") or "")
        if proposal_kind:
            grouped.setdefault(proposal_kind, []).append(lane)

    lane_rows: list[dict[str, Any]] = []
    for proposal_kind in sorted(grouped):
        lanes = grouped[proposal_kind]
        activation_lane = activation_by_kind.get(proposal_kind, {})
        artifact_contract = activation_lane.get("local_artifact_contract")
        artifact_contract = artifact_contract if isinstance(artifact_contract, dict) else {}
        target_paths = artifact_contract.get("target_paths")
        target_paths = target_paths if isinstance(target_paths, list) else []
        evidence_item_ids: list[str] = []
        for lane in lanes:
            evidence_item_ids.extend(string_list(lane.get("evidence_item_ids")))

        row = {
            "proposal_kind": proposal_kind,
            "candidate_count": len({str(lane.get("candidate_name") or "") for lane in lanes}),
            "candidate_name_hashes": sorted(
                {
                    stable_text_hash(str(lane.get("candidate_name") or ""))
                    for lane in lanes
                    if str(lane.get("candidate_name") or "")
                }
            ),
            "source_hashes": sorted(
                {
                    stable_text_hash(str(lane.get("source_url") or ""))
                    for lane in lanes
                    if str(lane.get("source_url") or "")
                }
            ),
            "evidence_item_id_count": len(set(evidence_item_ids)),
            "target_path_hashes": [
                stable_text_hash(str(path)) for path in sorted({str(path) for path in target_paths})
            ],
            "inspection_requirements": skill_route_discovery_inspection_requirements(proposal_kind),
            "required_validation": skill_route_discovery_preactivation_validation_commands(),
            "local_validation_required": all(lane.get("local_validation_required") is True for lane in lanes),
            "activation_ready": activation_lane.get("activation_ready") is True,
            "activation_blockers": string_list(activation_lane.get("activation_blockers")),
            "provider_runtime_control": activation_lane.get("provider_runtime_control")
            if isinstance(activation_lane.get("provider_runtime_control"), dict)
            else skill_route_discovery_provider_runtime_control(
                activation_ready=activation_lane.get("activation_ready") is True,
                recovery_hint_codes=string_list(activation_lane.get("recovery_hint_codes")),
            ),
            "runtime_action": str(activation_lane.get("runtime_action") or "none"),
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "raw_source_urls_exported": False,
            "raw_target_paths_exported": False,
        }
        if isinstance(activation_lane.get("provider_runtime_replay_sample"), dict):
            row["provider_runtime_replay_sample"] = activation_lane["provider_runtime_replay_sample"]
        lane_rows.append(row)

    lane_kinds = {row["proposal_kind"] for row in lane_rows}
    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    local_activation_allowed = activation_gate.get("local_proposal_activation_allowed") is True
    all_rows_ready = bool(lane_rows) and all(row["activation_ready"] for row in lane_rows)
    all_rows_bounded = lane_kinds <= allowed_lanes
    if local_activation_allowed and all_rows_ready and all_rows_bounded:
        status = "ready"
        decision = "validate_bounded_local_lanes"
    elif lane_rows:
        status = "review"
        decision = "hold_lanes_for_review_or_corroboration"
    else:
        status = "blocked"
        decision = "no_bounded_local_lanes"

    return {
        "status": status,
        "decision": decision,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "lane_count": len(lane_rows),
        "lane_rows": lane_rows,
        "evidence_tier": str(evidence_strength.get("tier") or ""),
        "activation_decision": str(activation_gate.get("decision") or ""),
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
        },
        "blocked_discovery_actions": list(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS),
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
    }


def skill_route_discovery_evidence_lane_matrix(
    *,
    registry: dict[str, Any],
    lane_map: dict[str, Any],
    activation_gate: dict[str, Any],
    evidence_strength: dict[str, Any],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    """Summarize how external evidence sources map into bounded local lanes."""

    from blackhole_agent.skill_routing import (
        SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
        SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS,
    )

    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    candidates = registry.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    proposal_lanes = lane_map.get("proposal_lanes")
    proposal_lanes = proposal_lanes if isinstance(proposal_lanes, list) else []
    rejected_candidates = lane_map.get("rejected_candidates")
    rejected_candidates = rejected_candidates if isinstance(rejected_candidates, list) else []
    downgraded_candidates = lane_map.get("downgraded_candidates")
    downgraded_candidates = downgraded_candidates if isinstance(downgraded_candidates, list) else []

    proposals_by_candidate: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for lane in proposal_lanes:
        key = (str(lane.get("candidate_name") or ""), str(lane.get("source_url") or ""))
        proposals_by_candidate.setdefault(key, []).append(lane)

    rejected_by_candidate: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rejected in rejected_candidates:
        key = (str(rejected.get("name") or ""), str(rejected.get("source_url") or ""))
        rejected_by_candidate.setdefault(key, []).append(rejected)

    downgraded_by_candidate: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for downgraded in downgraded_candidates:
        key = (str(downgraded.get("name") or ""), str(downgraded.get("source_url") or ""))
        downgraded_by_candidate.setdefault(key, []).append(downgraded)

    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_name = str(candidate.get("name") or "")
        source_url = str(candidate.get("source_url") or "")
        key = (candidate_name, source_url)
        candidate_lanes = sorted(
            {
                str(lane.get("proposal_kind") or "")
                for lane in proposals_by_candidate.get(key, [])
                if str(lane.get("proposal_kind") or "")
            }
        )
        route_profiles = sorted(
            {
                profile
                for lane in proposals_by_candidate.get(key, [])
                for profile in string_list(lane.get("route_profiles"))
            }
        )
        evidence_urls = [
            str(url)
            for lane in proposals_by_candidate.get(key, [])
            for url in lane.get("evidence_urls") or []
            if str(url).strip()
        ]
        evidence_item_ids = sorted(
            {
                str(item_id)
                for lane in proposals_by_candidate.get(key, [])
                for item_id in lane.get("evidence_item_ids") or []
                if str(item_id).strip()
            }
        )
        validation_errors = string_list(candidate.get("validation_errors"))
        requested_actions = string_list(candidate.get("requested_actions"))
        blocked_requested_actions = sorted(
            set(requested_actions) & set(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS)
        )
        downgraded = downgraded_by_candidate.get(key, [])
        rejected = rejected_by_candidate.get(key, [])
        downgraded_lanes = sorted(
            {
                rejected_lane
                for entry in downgraded
                for rejected_lane in string_list(entry.get("rejected_lanes"))
            }
        )

        lanes_bounded = bool(candidate_lanes) and set(candidate_lanes) <= allowed_lanes
        runtime_action = "none" if candidate_lanes else "none"
        if not lanes_bounded and candidate_lanes:
            diagnostics.append(f"{stable_text_hash(candidate_name or source_url)}:unbounded_lanes")
        if blocked_requested_actions:
            diagnostics.append(f"{stable_text_hash(candidate_name or source_url)}:blocked_actions_requested")
        if rejected:
            diagnostics.append(f"{stable_text_hash(candidate_name or source_url)}:rejected_candidate")

        rows.append(
            {
                "candidate_name_hash": stable_text_hash(candidate_name),
                "source_hash": stable_text_hash(source_url),
                "route_profiles": route_profiles,
                "local_lanes": candidate_lanes,
                "local_lane_count": len(candidate_lanes),
                "lanes_bounded": lanes_bounded,
                "evidence_item_ids": evidence_item_ids,
                "evidence_item_id_count": len(evidence_item_ids),
                "evidence_url_hashes": sorted({stable_text_hash(url) for url in evidence_urls}),
                "evidence_url_count": len(set(evidence_urls)),
                "downgraded_lane_count": len(downgraded_lanes),
                "downgraded_lanes": downgraded_lanes,
                "rejected": bool(rejected),
                "validation_error_count": len(validation_errors),
                "blocked_requested_action_count": len(blocked_requested_actions),
                "blocked_requested_action_hashes": [
                    stable_text_hash(action) for action in blocked_requested_actions
                ],
                "runtime_action": runtime_action,
                "local_validation_required": bool(candidate_lanes),
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    rows_bounded = bool(rows) and all(row["lanes_bounded"] or row["rejected"] for row in rows)
    ready = (
        bool(rows)
        and rows_bounded
        and not diagnostics
        and activation_gate.get("local_proposal_activation_allowed") is True
    )
    return {
        "controller_surface": "skill_route_discovery_evidence_lane_matrix",
        "status": "ready" if ready else "review" if rows else "blocked",
        "decision": "map_external_evidence_to_bounded_local_lanes"
        if ready
        else "review_evidence_lane_mapping_before_activation",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "candidate_count": len(rows),
        "lane_count": sum(row["local_lane_count"] for row in rows),
        "evidence_tier": str(evidence_strength.get("tier") or ""),
        "activation_decision": str(activation_gate.get("decision") or ""),
        "rows": rows,
        "rows_bounded": rows_bounded,
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
        },
        "blocked_discovery_actions": list(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS),
        "diagnostics": diagnostics,
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_candidate_lane_intake(
    *,
    lane_map: dict[str, Any],
    activation_gate: dict[str, Any],
    evidence_strength: dict[str, Any],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    """Expose candidate-level lane inventory without upstream bodies or raw URLs."""

    from blackhole_agent.skill_routing import (
        SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
        SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS,
    )

    inventory = lane_map.get("candidate_lane_inventory")
    inventory = inventory if isinstance(inventory, list) else []
    downgraded_candidates = lane_map.get("downgraded_candidates")
    downgraded_candidates = downgraded_candidates if isinstance(downgraded_candidates, list) else []
    rejected_candidates = lane_map.get("rejected_candidates")
    rejected_candidates = rejected_candidates if isinstance(rejected_candidates, list) else []
    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)

    downgraded_by_candidate: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for downgraded in downgraded_candidates:
        key = (str(downgraded.get("name") or ""), str(downgraded.get("source_url") or ""))
        downgraded_by_candidate.setdefault(key, []).append(downgraded)

    rejected_by_candidate: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rejected in rejected_candidates:
        key = (str(rejected.get("name") or ""), str(rejected.get("source_url") or ""))
        rejected_by_candidate.setdefault(key, []).append(rejected)

    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for candidate in inventory:
        if not isinstance(candidate, dict):
            continue
        candidate_name = str(candidate.get("candidate_name") or "")
        source_url = str(candidate.get("source_url") or "")
        key = (candidate_name, source_url)
        proposal_kinds = string_list(candidate.get("proposal_kinds"))
        bounded = bool(proposal_kinds) and set(proposal_kinds) <= allowed_lanes
        downgraded = downgraded_by_candidate.get(key, [])
        rejected = rejected_by_candidate.get(key, [])
        downgraded_lanes = sorted(
            {
                lane
                for entry in downgraded
                for lane in string_list(entry.get("rejected_lanes"))
            }
        )
        validation_errors = [
            error
            for entry in (*downgraded, *rejected)
            for error in string_list(entry.get("validation_errors"))
        ]
        blocked_actions = sorted(
            {
                action
                for error in validation_errors
                if error.startswith("blocked_discovery_actions:")
                for action in error.split(":", 1)[1].split(",")
                if action
            }
            | (set(downgraded_lanes) & set(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS))
        )
        if not bounded:
            diagnostics.append(f"{stable_text_hash(candidate_name or source_url)}:candidate_lanes_unbounded")
        if downgraded_lanes:
            diagnostics.append(f"{stable_text_hash(candidate_name or source_url)}:candidate_lanes_downgraded")
        if rejected:
            diagnostics.append(f"{stable_text_hash(candidate_name or source_url)}:candidate_rejected")

        evidence_urls = string_list(candidate.get("evidence_urls"))
        lane_selection = skill_route_discovery_profile_lane_selection(
            proposal_kinds=proposal_kinds,
            route_profiles=string_list(candidate.get("route_profiles")),
            downgraded_lanes=downgraded_lanes,
            rejected=bool(rejected),
        )
        rows.append(
            {
                "candidate_name_hash": stable_text_hash(candidate_name),
                "source_hash": stable_text_hash(source_url),
                "proposal_kinds": proposal_kinds,
                "proposal_kind_count": len(proposal_kinds),
                "route_profiles": string_list(candidate.get("route_profiles")),
                "matched_route_terms": string_list(candidate.get("matched_route_terms")),
                "recommended_local_lane_order": lane_selection["recommended_local_lane_order"],
                "lane_selection_reason": lane_selection["lane_selection_reason"],
                "lane_selection_review_required": lane_selection["lane_selection_review_required"],
                "discovery_event_kind": str(candidate.get("discovery_event_kind") or "unknown"),
                "discovery_event_effect": str(candidate.get("discovery_event_effect") or "record_only"),
                "evidence_item_ids": string_list(candidate.get("evidence_item_ids")),
                "evidence_item_id_count": len(string_list(candidate.get("evidence_item_ids"))),
                "evidence_url_hashes": sorted({stable_text_hash(url) for url in evidence_urls}),
                "evidence_url_count": len(set(evidence_urls)),
                "downgraded_lanes": downgraded_lanes,
                "downgraded_lane_count": len(downgraded_lanes),
                "blocked_requested_action_hashes": [stable_text_hash(action) for action in blocked_actions],
                "blocked_requested_action_count": len(blocked_actions),
                "rejected": bool(rejected),
                "validation_error_count": len(validation_errors),
                "uncertainty_reasons": string_list(candidate.get("uncertainty_reasons")),
                "lanes_bounded": bounded,
                "local_validation_required": candidate.get("local_validation_required") is True,
                "runtime_action": str(candidate.get("runtime_action") or "none"),
                "external_skill_activation_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    inventory_bounded = bool(rows) and all(row["lanes_bounded"] for row in rows)
    downgraded_count = sum(row["downgraded_lane_count"] for row in rows)
    rejected_count = sum(1 for row in rows if row["rejected"])
    clean = inventory_bounded and downgraded_count == 0 and rejected_count == 0 and not diagnostics
    activation_allowed = activation_gate.get("local_proposal_activation_allowed") is True
    return {
        "controller_surface": "skill_route_discovery_candidate_lane_intake",
        "status": "ready" if rows and clean and activation_allowed else "review" if rows else "blocked",
        "decision": "inventory_ready_for_local_lane_selection"
        if rows and clean and activation_allowed
        else "review_candidate_inventory_before_lane_selection",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "candidate_count": len(rows),
        "proposal_kind_count": sum(row["proposal_kind_count"] for row in rows),
        "downgraded_candidate_count": sum(1 for row in rows if row["downgraded_lane_count"]),
        "rejected_candidate_count": rejected_count,
        "evidence_tier": str(evidence_strength.get("tier") or ""),
        "activation_decision": str(activation_gate.get("decision") or ""),
        "rows": rows,
        "inventory_bounded": inventory_bounded,
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
        },
        "blocked_discovery_actions": list(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS),
        "diagnostics": diagnostics,
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_term_route_review(
    *,
    candidate_lane_intake: dict[str, Any],
    activation_gate: dict[str, Any],
) -> dict[str, Any]:
    """Show which skill/workflow route terms produced bounded local lanes."""

    from blackhole_agent.skill_routing import (
        SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
        SKILL_ROUTE_DISCOVERY_TRIGGER_TERMS,
    )

    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    rows_input = candidate_lane_intake.get("rows")
    rows_input = rows_input if isinstance(rows_input, list) else []
    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    term_counts: dict[str, int] = {term: 0 for term in SKILL_ROUTE_DISCOVERY_TRIGGER_TERMS}

    for index, raw_row in enumerate(rows_input):
        row = raw_row if isinstance(raw_row, dict) else {}
        matched_terms = [term for term in string_list(row.get("matched_route_terms")) if term in term_counts]
        proposal_kinds = string_list(row.get("proposal_kinds"))
        lanes_bounded = bool(proposal_kinds) and set(proposal_kinds) <= allowed_lanes
        runtime_action = str(row.get("runtime_action") or "none")
        local_validation_required = row.get("local_validation_required") is True

        if not matched_terms:
            diagnostics.append(f"rows[{index}].matched_route_terms_missing")
        if not lanes_bounded:
            diagnostics.append(f"rows[{index}].proposal_kinds_unbounded")
        if runtime_action != "none":
            diagnostics.append(f"rows[{index}].runtime_action_must_be_none")
        if local_validation_required is not True:
            diagnostics.append(f"rows[{index}].local_validation_required_missing")
        if row.get("external_skill_activation_allowed") is not False:
            diagnostics.append(f"rows[{index}].external_skill_activation_must_be_false")

        for term in matched_terms:
            term_counts[term] += 1

        rows.append(
            {
                "candidate_name_hash": str(row.get("candidate_name_hash") or ""),
                "source_hash": str(row.get("source_hash") or ""),
                "matched_route_terms": matched_terms,
                "proposal_kinds": proposal_kinds,
                "lanes_bounded": lanes_bounded,
                "local_validation_required": local_validation_required,
                "runtime_action": runtime_action,
                "external_skill_activation_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    activation_allowed = activation_gate.get("local_proposal_activation_allowed") is True
    ready = bool(rows) and not diagnostics and activation_allowed
    active_term_counts = {term: count for term, count in term_counts.items() if count}
    return {
        "controller_surface": "skill_route_discovery_term_route_review",
        "status": "ready" if ready else "review" if rows else "blocked",
        "decision": "term_triggered_routes_bounded_for_local_validation"
        if ready
        else "review_term_triggered_routes_before_activation",
        "trigger_terms": list(SKILL_ROUTE_DISCOVERY_TRIGGER_TERMS),
        "matched_term_counts": active_term_counts,
        "candidate_count": len(rows),
        "rows": rows,
        "diagnostics": diagnostics,
        "activation_decision": str(activation_gate.get("decision") or ""),
        "local_validation_required": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_profile_lane_selection(
    *,
    proposal_kinds: list[str],
    route_profiles: list[str],
    downgraded_lanes: list[str],
    rejected: bool,
) -> dict[str, Any]:
    """Recommend a bounded local lane order for operator selection.

    The recommendation never adds lanes. It only sorts lanes already produced by
    the local discovery map so profile evidence can guide the next validation
    artifact without enabling upstream skill packages.
    """

    bounded_kinds = [kind for kind in proposal_kinds if kind in {"documentation", "config", "test", "code_patch"}]
    profiles = set(route_profiles)
    if "skill_ecosystem_state_handoff" in profiles:
        preferred_order = ["config", "documentation", "test", "code_patch"]
        reason = "state_handoff_routes_start_with_metadata_and_boundary_review"
    elif "game_frontend_workflow" in profiles:
        preferred_order = ["test", "documentation", "code_patch", "config"]
        reason = "game_skill_routes_start_with_validation_and_boundary_review"
    elif "codex_workflow_gate" in profiles:
        preferred_order = ["test", "documentation", "code_patch", "config"]
        reason = "workflow_gate_routes_start_with_replay_or_documented_gate_review"
    else:
        preferred_order = ["documentation", "test", "config", "code_patch"]
        reason = "generic_skill_routes_start_with_documented_local_contract"

    ordered = [kind for kind in preferred_order if kind in bounded_kinds]
    ordered.extend(kind for kind in bounded_kinds if kind not in ordered)
    return {
        "recommended_local_lane_order": ordered,
        "lane_selection_reason": reason,
        "lane_selection_review_required": bool(downgraded_lanes or rejected),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
    }


def skill_route_discovery_route_triage_plan(
    *,
    proposal_lanes: list[dict[str, Any]],
    activation_lanes: list[dict[str, Any]],
    activation_gate: dict[str, Any],
    evidence_strength: dict[str, Any],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    """Render lane triage as body-free local work planning metadata."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    activation_by_kind = {
        str(lane.get("proposal_kind") or ""): lane for lane in activation_lanes if str(lane.get("proposal_kind") or "")
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for lane in proposal_lanes:
        proposal_kind = str(lane.get("proposal_kind") or "")
        if proposal_kind:
            grouped.setdefault(proposal_kind, []).append(lane)

    rows: list[dict[str, Any]] = []
    for proposal_kind in sorted(grouped):
        lanes = grouped[proposal_kind]
        activation_lane = activation_by_kind.get(proposal_kind, {})
        artifact_contract = activation_lane.get("local_artifact_contract")
        artifact_contract = artifact_contract if isinstance(artifact_contract, dict) else {}
        target_paths = artifact_contract.get("target_paths")
        target_paths = target_paths if isinstance(target_paths, list) else []
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        uncertainty_reasons: list[str] = []
        for lane in lanes:
            evidence_item_ids.extend(string_list(lane.get("evidence_item_ids")))
            route_profiles.extend(string_list(lane.get("route_profiles")))
            uncertainty_reasons.extend(string_list(lane.get("uncertainty_reasons")))
        artifact_proof = activation_lane.get("local_artifact_proof")
        artifact_proof = artifact_proof if isinstance(artifact_proof, dict) else {}

        rows.append(
            {
                "proposal_kind": proposal_kind,
                "triage_reason": SKILL_ROUTE_DISCOVERY_TRIAGE_REASONS.get(
                    proposal_kind,
                    "review bounded local route before implementation",
                ),
                "candidate_count": len({str(lane.get("candidate_name") or "") for lane in lanes}),
                "route_profiles": sorted(dict.fromkeys(route_profiles)),
                "source_hashes": sorted(
                    {
                        stable_text_hash(str(lane.get("source_url") or ""))
                        for lane in lanes
                        if str(lane.get("source_url") or "")
                    }
                ),
                "evidence_item_id_count": len(set(evidence_item_ids)),
                "uncertainty_reasons": sorted(dict.fromkeys(uncertainty_reasons)),
                "target_path_hashes": [
                    stable_text_hash(str(path)) for path in sorted({str(path) for path in target_paths})
                ],
                "local_artifact_contract": artifact_contract,
                "inspection_requirements": skill_route_discovery_inspection_requirements(proposal_kind),
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "activation_ready": activation_lane.get("activation_ready") is True,
                "local_artifact_proof_ready": artifact_proof.get("ready") is True,
                "activation_blockers": string_list(activation_lane.get("activation_blockers")),
                "runtime_action": str(activation_lane.get("runtime_action") or "none"),
                "external_skill_activation_allowed": False,
                "external_skill_code_allowed": False,
                "raw_evidence_exported": False,
                "raw_source_urls_exported": False,
                "raw_target_paths_exported": False,
            }
        )

    row_kinds = {row["proposal_kind"] for row in rows}
    lanes_bounded = row_kinds <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    all_rows_ready = bool(rows) and all(row["activation_ready"] for row in rows)
    if activation_gate.get("local_proposal_activation_allowed") is True and all_rows_ready and lanes_bounded:
        status = "ready"
        decision = "triage_bounded_lanes_to_local_artifacts"
    elif rows:
        status = "review"
        decision = "hold_triage_for_replay_or_artifact_proof"
    else:
        status = "blocked"
        decision = "no_lanes_to_triage"

    return {
        "controller_surface": "skill_route_discovery_route_triage",
        "status": status,
        "decision": decision,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "lane_count": len(rows),
        "lanes_bounded": lanes_bounded,
        "evidence_tier": str(evidence_strength.get("tier") or ""),
        "activation_decision": str(activation_gate.get("decision") or ""),
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
        },
        "rows": rows,
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_skill_code_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_target_paths_exported": False,
    }


def skill_route_discovery_route_profile_review(
    *,
    raw_input: dict[str, Any],
    proposal_lanes: list[dict[str, Any]],
    source_lineage: dict[str, Any],
    evidence_strength: dict[str, Any],
) -> dict[str, Any]:
    """Render profile-specific inspection lanes before local activation."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for lane in proposal_lanes:
        for profile in string_list(lane.get("route_profiles")) or ["generic_skill_workflow"]:
            grouped.setdefault(profile, []).append(lane)

    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for profile in sorted(grouped):
        lanes = grouped[profile]
        contract = SKILL_ROUTE_DISCOVERY_PROFILE_REVIEW_CONTRACTS.get(
            profile,
            SKILL_ROUTE_DISCOVERY_PROFILE_REVIEW_CONTRACTS["generic_skill_workflow"],
        )
        proposal_kinds = sorted({str(lane.get("proposal_kind") or "") for lane in lanes})
        evidence_item_ids: list[str] = []
        uncertainty_reasons: list[str] = []
        for lane in lanes:
            evidence_item_ids.extend(string_list(lane.get("evidence_item_ids")))
            uncertainty_reasons.extend(string_list(lane.get("uncertainty_reasons")))
        runtime_safe = all(str(lane.get("runtime_action") or "") == "none" for lane in lanes)
        validation_required = all(lane.get("local_validation_required") is True for lane in lanes)
        if not runtime_safe:
            diagnostics.append(f"{profile}:runtime_action_must_be_none")
        if not validation_required:
            diagnostics.append(f"{profile}:local_validation_required")

        local_lane_contracts = [
            skill_route_discovery_route_profile_lane_contract(proposal_kind)
            for proposal_kind in proposal_kinds
        ]
        metadata_coverage = skill_route_discovery_profile_metadata_coverage(
            raw_input=raw_input,
            profile=profile,
            lanes=lanes,
            expected_metadata=contract["expected_metadata"],
        )
        for missing in metadata_coverage["missing_metadata"]:
            diagnostics.append(f"{profile}:metadata_missing:{missing}")
        state_handoff_preflight = (
            skill_route_discovery_state_handoff_preflight(
                raw_input=raw_input,
                metadata_coverage=metadata_coverage,
                lanes=lanes,
            )
            if profile == "skill_ecosystem_state_handoff"
            else None
        )
        if state_handoff_preflight is not None and state_handoff_preflight["status"] != "ready":
            diagnostics.extend(
                f"{profile}:state_handoff_preflight:{diagnostic}"
                for diagnostic in state_handoff_preflight["diagnostics"]
            )

        row = {
            "route_profile": profile,
            "proposal_kinds": proposal_kinds,
            "candidate_count": len({str(lane.get("candidate_name") or "") for lane in lanes}),
            "evidence_item_id_count": len(set(evidence_item_ids)),
            "recognition_signals": list(contract["recognition_signals"]),
            "expected_metadata": list(contract["expected_metadata"]),
            "metadata_coverage": metadata_coverage,
            "metadata_complete": metadata_coverage["complete"],
            "safe_local_tests": list(contract["safe_local_tests"]),
            "rejection_conditions": list(contract["rejection_conditions"]),
            "local_lane_contracts": local_lane_contracts,
            "uncertainty_reasons": sorted(dict.fromkeys(uncertainty_reasons)),
            "runtime_action": "none" if runtime_safe else "review",
            "local_validation_required": validation_required,
            "local_artifact_proof_required": True,
            "external_skill_activation_allowed": False,
            "external_skill_code_allowed": False,
            "raw_evidence_exported": False,
            "raw_source_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        if state_handoff_preflight is not None:
            row["state_handoff_preflight"] = state_handoff_preflight
        rows.append(row)

    if rows and not diagnostics:
        status = "ready"
        decision = "review_profile_contracts_before_local_activation"
    elif rows:
        status = "review"
        decision = "resolve_profile_contract_diagnostics"
    else:
        status = "blocked"
        decision = "no_route_profiles_to_review"

    return {
        "controller_surface": "skill_route_discovery_route_profile_review",
        "status": status,
        "decision": decision,
        "profile_count": len(rows),
        "profiles": [row["route_profile"] for row in rows],
        "rows": rows,
        "evidence_tier": str(evidence_strength.get("tier") or ""),
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
        },
        "diagnostics": diagnostics,
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


def skill_route_discovery_profile_metadata_coverage(
    *,
    raw_input: dict[str, Any],
    profile: str,
    lanes: list[dict[str, Any]],
    expected_metadata: tuple[str, ...],
) -> dict[str, Any]:
    """Check profile-specific evidence shape without exporting evidence bodies."""

    records = skill_route_discovery_profile_evidence_records(raw_input)
    combined_text = " ".join(record["text"] for record in records).casefold()
    proposal_kinds = {str(lane.get("proposal_kind") or "") for lane in lanes}
    evidence_item_ids = {
        evidence_item_id
        for lane in lanes
        for evidence_item_id in string_list(lane.get("evidence_item_ids"))
    }
    local_artifact_proofs = skill_route_discovery_local_artifact_proofs(raw_input)
    proof_kinds = set(local_artifact_proofs)

    checks: dict[str, bool] = {
        "selected_digest_item_ids": bool(evidence_item_ids),
        "selected_digest_item_ids_or_frozen_digest_evidence": bool(evidence_item_ids or records),
        "body_free_workflow_summary": bool(records)
        and any(marker in combined_text for marker in ("codex", "workflow", "gate", "verification", "ledger")),
        "local_gate_or_test_target": bool(proof_kinds & {"test", "code_patch"} or proposal_kinds & {"test", "code_patch"})
        and any(marker in combined_text for marker in ("gate", "test", "verification", "workflow", "coverage")),
        "body_free_game_skill_summary": bool(records)
        and any(marker in combined_text for marker in ("threejs", "three.js", "game", "browser", "director")),
        "local_frontend_validation_target": bool(proposal_kinds & {"test", "code_patch"})
        and any(marker in combined_text for marker in ("qa", "validation", "browser", "screenshot", "canvas")),
        "asset_or_provider_boundary_note": any(
            marker in combined_text
            for marker in ("asset", "provider", "credential", "generation", "helper script", "scaffold")
        ),
        "body_free_skill_ecosystem_summary": bool(records)
        and any(marker in combined_text for marker in ("skill", "ecosystem", "clarification", "handoff")),
        "state_retention_and_privacy_boundary": any(
            marker in combined_text for marker in ("local memory", "repo-local", "profile", "handoff", "privacy", "secret")
        ),
        "local_memory_or_profile_target_if_any": any(
            marker in combined_text for marker in ("memory", "profile", "handoff", "task graph", "task forest")
        ),
        "body_free_repository_summary": bool(records),
        "local_artifact_target": bool(proposal_kinds),
    }

    satisfied = [metadata for metadata in expected_metadata if checks.get(metadata) is True]
    missing = [metadata for metadata in expected_metadata if checks.get(metadata) is not True]
    source_hashes = sorted(
        {
            stable_text_hash(record["source_url"])
            for record in records
            if record["source_url"]
        }
    )
    text_hashes = sorted(
        {
            stable_text_hash(record["text"])
            for record in records
            if record["text"]
        }
    )
    return {
        "profile": profile,
        "expected_count": len(expected_metadata),
        "satisfied_count": len(satisfied),
        "missing_count": len(missing),
        "satisfied_metadata": satisfied,
        "missing_metadata": missing,
        "evidence_record_count": len(records),
        "evidence_item_id_count": len(evidence_item_ids),
        "local_artifact_proof_count": len(proof_kinds),
        "source_hashes": source_hashes,
        "evidence_text_hashes": text_hashes,
        "complete": not missing,
        "body_free": True,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_state_handoff_preflight(
    *,
    raw_input: dict[str, Any],
    metadata_coverage: dict[str, Any],
    lanes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check COMPASS-style state/profile routes before local activation.

    Repository evidence about local memory, profiles, or handoff is useful route
    pressure, but it must not imply local writes or private context retention.
    """

    boundary = raw_input.get("state_handoff_boundary")
    boundary = boundary if isinstance(boundary, dict) else {}
    diagnostics: list[str] = []
    satisfied_metadata = set(string_list(metadata_coverage.get("satisfied_metadata")))
    missing_metadata = set(string_list(metadata_coverage.get("missing_metadata")))
    proposal_kinds = sorted(
        {str(lane.get("proposal_kind") or "") for lane in lanes if str(lane.get("proposal_kind") or "")}
    )

    state_metadata_present = {
        "state_retention_and_privacy_boundary": "state_retention_and_privacy_boundary" in satisfied_metadata,
        "local_memory_or_profile_target_if_any": "local_memory_or_profile_target_if_any" in satisfied_metadata,
    }
    if "state_retention_and_privacy_boundary" in missing_metadata:
        diagnostics.append("state_retention_and_privacy_boundary_missing")
    if "local_memory_or_profile_target_if_any" in missing_metadata:
        diagnostics.append("local_memory_or_profile_target_missing")

    explicit_boundary = {
        "retention_policy_documented": truthy(boundary.get("retention_policy_documented")),
        "privacy_boundary_documented": truthy(boundary.get("privacy_boundary_documented")),
        "local_target_metadata_only": truthy(boundary.get("local_target_metadata_only")),
        "upstream_presence_grants_write": truthy(boundary.get("upstream_presence_grants_write")),
    }
    if not explicit_boundary["retention_policy_documented"]:
        diagnostics.append("retention_policy_not_documented")
    if not explicit_boundary["privacy_boundary_documented"]:
        diagnostics.append("privacy_boundary_not_documented")
    if not explicit_boundary["local_target_metadata_only"]:
        diagnostics.append("local_target_metadata_only_not_confirmed")
    if explicit_boundary["upstream_presence_grants_write"]:
        diagnostics.append("upstream_presence_must_not_grant_state_writes")

    status = "ready" if not diagnostics else "review"
    return {
        "controller_surface": "skill_route_discovery_state_handoff_preflight",
        "status": status,
        "decision": "state_profile_route_ready_for_local_review"
        if status == "ready"
        else "resolve_state_profile_boundary",
        "proposal_kinds": proposal_kinds,
        "state_metadata_present": state_metadata_present,
        "explicit_boundary": explicit_boundary,
        "diagnostics": diagnostics,
        "runtime_action": "none",
        "state_write_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "external_skill_activation_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
        "private_context_exported": False,
    }


def skill_route_discovery_profile_evidence_records(raw_input: dict[str, Any]) -> list[dict[str, str]]:
    """Return local-only profile evidence records used for body-free coverage checks."""

    records: list[dict[str, str]] = []
    for key in ("evidence_items", "summaries", "candidates"):
        values = raw_input.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            source_url = optional_string(value.get("source_url") or value.get("url")) or ""
            text = " ".join(
                part
                for part in (
                    optional_string(value.get("name")),
                    optional_string(value.get("title")),
                    optional_string(value.get("summary") or value.get("evidence_summary")),
                    " ".join(string_list(value.get("topics"))),
                )
                if part
            ).strip()
            if text or source_url:
                records.append({"source_url": source_url, "text": text})
    return records


def skill_route_discovery_activity_signal_panel(
    *,
    proposal_lanes: list[dict[str, Any]],
    activation_gate: dict[str, Any],
    evidence_strength: dict[str, Any],
    source_lineage: dict[str, Any],
) -> dict[str, Any]:
    """Summarize repository activity as bounded validation pressure only."""

    from blackhole_agent.skill_routing import SKILL_ROUTE_DISCOVERY_ALLOWED_LANES

    allowed_lanes = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    diagnostics: list[str] = []
    evidence_tier = str(evidence_strength.get("tier") or "")
    weak_generic_movement = evidence_tier == "weak_generic_upstream_movement"
    generic_with_corroboration = evidence_tier == "generic_upstream_movement_with_local_corroboration"
    weak_generic_count = int(evidence_strength.get("weak_generic_movement_count") or 0)
    local_corroborating_signal_count = int(evidence_strength.get("local_corroborating_signal_count") or 0)
    if weak_generic_movement:
        diagnostics.append("generic_upstream_movement_requires_local_corroboration")
    for lane in proposal_lanes:
        proposal_kind = str(lane.get("proposal_kind") or "")
        event_kind = str(lane.get("discovery_event_kind") or "unknown")
        grouped.setdefault((event_kind, proposal_kind), []).append(lane)
        if proposal_kind not in allowed_lanes:
            diagnostics.append(f"{event_kind}:{proposal_kind}:proposal_kind_unbounded")
        if str(lane.get("runtime_action") or "") != "none":
            diagnostics.append(f"{event_kind}:{proposal_kind}:runtime_action_must_be_none")
        if lane.get("local_validation_required") is not True:
            diagnostics.append(f"{event_kind}:{proposal_kind}:local_validation_required")

    rows: list[dict[str, Any]] = []
    for (event_kind, proposal_kind), lanes in sorted(grouped.items()):
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        candidate_names: set[str] = set()
        source_urls: set[str] = set()
        for lane in lanes:
            evidence_item_ids.extend(string_list(lane.get("evidence_item_ids")))
            route_profiles.extend(string_list(lane.get("route_profiles")))
            if str(lane.get("candidate_name") or ""):
                candidate_names.add(str(lane.get("candidate_name") or ""))
            if str(lane.get("source_url") or ""):
                source_urls.add(str(lane.get("source_url") or ""))
        event_effects = sorted(
            {
                str(lane.get("discovery_event_effect") or "record_only")
                for lane in lanes
            }
        )
        if event_kind == "push" and not weak_generic_movement:
            activity_interpretation = "movement_supports_local_validation_lane"
        elif weak_generic_movement:
            activity_interpretation = "low_detail_generic_movement_supporting_context_only"
        elif generic_with_corroboration:
            activity_interpretation = "generic_movement_locally_corroborated"
        else:
            activity_interpretation = "repository_activity_record_only"
        rows.append(
            {
                "event_kind": event_kind,
                "proposal_kind": proposal_kind,
                "candidate_count": len(candidate_names),
                "candidate_name_hashes": [stable_text_hash(name) for name in sorted(candidate_names)],
                "source_hashes": [stable_text_hash(source_url) for source_url in sorted(source_urls)],
                "route_profiles": sorted(dict.fromkeys(route_profiles)),
                "evidence_item_id_count": len(set(evidence_item_ids)),
                "event_effects": event_effects,
                "allowed_local_lane": proposal_kind in allowed_lanes,
                "activity_interpretation": activity_interpretation,
                "weak_generic_supporting_context_only": weak_generic_movement,
                "local_corroboration_required": weak_generic_count > 0,
                "local_corroborating_signal_count": local_corroborating_signal_count,
                "required_validation": skill_route_discovery_preactivation_validation_commands(),
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "raw_source_urls_exported": False,
                "raw_evidence_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    event_kinds = sorted({row["event_kind"] for row in rows})
    push_signal_count = sum(1 for row in rows if row["event_kind"] == "push")
    rows_bounded = bool(rows) and all(row["allowed_local_lane"] for row in rows)
    ready = (
        bool(rows)
        and not diagnostics
        and rows_bounded
        and activation_gate.get("local_proposal_activation_allowed") is True
    )
    return {
        "controller_surface": "skill_route_discovery_activity_signal_panel",
        "status": "ready" if ready else "blocked" if not rows else "review",
        "decision": "interpret_activity_as_bounded_validation_pressure"
        if ready
        else "hold_activity_signal_for_review",
        "event_kinds": event_kinds,
        "push_signal_count": push_signal_count,
        "weak_generic_movement_count": weak_generic_count,
        "local_corroborating_signal_count": local_corroborating_signal_count,
        "generic_movement_policy": (
            "supporting_context_only_until_local_corroboration"
            if weak_generic_movement
            else "locally_corroborated_generic_context"
            if generic_with_corroboration
            else "not_generic_low_detail_movement"
        ),
        "lane_count": len(rows),
        "rows": rows,
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
        },
        "diagnostics": diagnostics,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "local_validation_required": True,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_generic_validation_prompt(
    *,
    activity_signal_panel: dict[str, Any],
    activation_gate: dict[str, Any],
    evidence_strength: dict[str, Any],
) -> dict[str, Any]:
    """Expose low-detail generic PR movement as local validation work, not proof."""

    weak_generic_count = int(evidence_strength.get("weak_generic_movement_count") or 0)
    local_corroborating_signal_count = int(evidence_strength.get("local_corroborating_signal_count") or 0)
    prompt_required = weak_generic_count > 0 and local_corroborating_signal_count == 0
    locally_corroborated = weak_generic_count > 0 and local_corroborating_signal_count > 0
    rows = activity_signal_panel.get("rows") if isinstance(activity_signal_panel.get("rows"), list) else []
    low_detail_rows = [
        {
            "event_kind": str(row.get("event_kind") or ""),
            "proposal_kind": str(row.get("proposal_kind") or ""),
            "activity_interpretation": str(row.get("activity_interpretation") or ""),
            "required_validation": string_list(row.get("required_validation")),
            "weak_generic_supporting_context_only": row.get("weak_generic_supporting_context_only") is True,
            "local_corroboration_required": row.get("local_corroboration_required") is True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
        }
        for row in rows
        if row.get("local_corroboration_required") is True
    ]
    if prompt_required:
        status = "review"
        decision = "collect_local_corroboration_before_activation"
        supervisor_next_action = "add_focused_fixture_or_operator_review_note"
    elif locally_corroborated:
        status = "ready"
        decision = "generic_movement_locally_corroborated_for_bounded_lane"
        supervisor_next_action = "replay_bounded_local_validation"
    else:
        status = "not_required"
        decision = "no_generic_validation_prompt_required"
        supervisor_next_action = "continue_standard_skill_route_review"

    return {
        "controller_surface": "skill_route_discovery_generic_validation_prompt",
        "status": status,
        "decision": decision,
        "prompt_required": prompt_required,
        "prompt_count": len(low_detail_rows) if prompt_required else 0,
        "weak_generic_movement_count": weak_generic_count,
        "local_corroborating_signal_count": local_corroborating_signal_count,
        "generic_movement_policy": str(activity_signal_panel.get("generic_movement_policy") or ""),
        "activation_decision": str(activation_gate.get("decision") or ""),
        "local_proposal_activation_allowed": activation_gate.get("local_proposal_activation_allowed") is True,
        "accepted_corroboration_signal_kinds": [
            "failing_local_test",
            "focused_fixture",
            "local_validation",
            "operator_review_note",
            "replay_fixture",
        ],
        "supervisor_next_action": supervisor_next_action,
        "replay_commands": skill_route_discovery_preactivation_validation_commands(),
        "low_detail_rows": low_detail_rows,
        "local_validation_required": weak_generic_count > 0,
        "body_free": True,
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "raw_source_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def skill_route_discovery_route_profile_lane_contract(proposal_kind: str) -> dict[str, Any]:
    """Return a body-free artifact target contract for one profile review lane."""

    target_paths = SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS.get(proposal_kind, ())
    return {
        "proposal_kind": proposal_kind,
        "target_path_hashes": [stable_text_hash(path) for path in target_paths],
        "target_count": len(target_paths),
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


def skill_route_discovery_supervisor_readiness(
    *,
    route_status: str,
    failure_mode: str,
    activation_gate: dict[str, Any],
    activation_lanes: list[dict[str, Any]],
    preactivation_trust_boundary: dict[str, Any],
    recovery_hints: list[dict[str, Any]],
    source_lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize whether a supervisor may promote only local route work."""

    validation_commands = skill_route_discovery_preactivation_validation_commands()
    trust_boundary_passed = preactivation_trust_boundary.get("status") == "passed"
    activation_allowed = activation_gate.get("local_proposal_activation_allowed") is True
    ready_lanes = [lane for lane in activation_lanes if lane.get("activation_ready") is True]
    blocked_lanes = [lane for lane in activation_lanes if lane.get("activation_ready") is not True]
    all_lanes_ready = bool(activation_lanes) and len(ready_lanes) == len(activation_lanes)
    runtime_actions = sorted({str(lane.get("runtime_action") or "") for lane in activation_lanes})
    external_skill_allowed = any(
        lane.get("external_skill_activation_allowed") is not False for lane in activation_lanes
    )
    external_harness_allowed = any(
        isinstance(lane.get("preactivation_harness"), dict)
        and lane["preactivation_harness"].get("external_harness_execution_allowed") is not False
        for lane in activation_lanes
    )
    provider_runtime_preflight_present = all(
        lane.get("provider_runtime_preflight") == skill_route_discovery_provider_runtime_preflight_contract()
        for lane in activation_lanes
    )
    validation_present = all(lane.get("required_validation") == validation_commands for lane in activation_lanes)
    local_artifact_proof_present = all(
        isinstance(lane.get("local_artifact_proof"), dict) and lane["local_artifact_proof"].get("provided") is True
        for lane in activation_lanes
    )
    local_artifact_proof_ready = all(
        isinstance(lane.get("local_artifact_proof"), dict) and lane["local_artifact_proof"].get("ready") is True
        for lane in activation_lanes
    )

    if (
        activation_allowed
        and trust_boundary_passed
        and all_lanes_ready
        and validation_present
        and provider_runtime_preflight_present
        and local_artifact_proof_ready
    ):
        decision = "ready_for_supervisor_promotion"
    elif route_status == "degraded":
        decision = "review_before_supervisor_promotion"
    else:
        decision = "blocked_before_supervisor_promotion"

    replay_commands = list(validation_commands)
    readiness_reason = failure_mode
    if decision == "ready_for_supervisor_promotion":
        readiness_reason = "none"
    elif failure_mode == "none" and not local_artifact_proof_ready:
        readiness_reason = "local_artifact_proof_not_ready"
    recovery_hint_codes = [str(hint.get("code") or "") for hint in recovery_hints if str(hint.get("code") or "")]
    source_lineage = source_lineage if isinstance(source_lineage, dict) else {}
    return {
        "decision": decision,
        "reason": readiness_reason,
        "activation_lane_count": len(activation_lanes),
        "ready_lane_count": len(ready_lanes),
        "blocked_lane_count": len(blocked_lanes),
        "proposal_kinds": sorted({str(lane.get("proposal_kind") or "") for lane in activation_lanes}),
        "required_validation": validation_commands,
        "replay_commands": replay_commands,
        "validation_present": validation_present,
        "local_artifact_proof_present": local_artifact_proof_present,
        "local_artifact_proof_ready": local_artifact_proof_ready,
        "trust_boundary_passed": trust_boundary_passed,
        "provider_runtime_preflight_present": provider_runtime_preflight_present,
        "provider_runtime_replay_commands": [
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "recovery_hint_codes": recovery_hint_codes,
        "source_lineage": {
            "body_free": source_lineage.get("body_free") is True,
            "lineage_mode": str(source_lineage.get("lineage_mode") or ""),
            "candidate_source_count": int(source_lineage.get("candidate_source_count") or 0),
            "related_source_count": int(source_lineage.get("related_source_count") or 0),
            "duplicate_summary_count": int(source_lineage.get("duplicate_summary_count") or 0),
            "fork_or_mirror_lineage_collapsed": source_lineage.get("fork_or_mirror_lineage_collapsed") is True,
            "raw_source_urls_exported": False,
            "raw_related_source_urls_exported": False,
        },
        "runtime_action_allowed": runtime_actions != ["none"] if runtime_actions else False,
        "external_skill_activation_allowed": external_skill_allowed,
        "external_harness_execution_allowed": external_harness_allowed,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_evidence_exported": False,
        "restart_or_remote_activation_required": False,
    }


def skill_route_discovery_preactivation_validation_commands() -> list[str]:
    """Return local checks required before promoting a skill-route discovery lane."""

    return [
        SKILL_ROUTE_DISCOVERY_VALIDATION_COMMAND,
        SKILL_ROUTE_DISCOVERY_PREACTIVATION_HARNESS_COMMAND,
        SKILL_ROUTE_DISCOVERY_PROPOSAL_INTERPRETATION_COMMAND,
    ]


def skill_route_discovery_lane_failure_mode(
    *,
    proposal_lane_count: int,
    rejected_candidate_count: int,
    downgraded_candidate_count: int,
    lane_runtime_safe: bool,
    validation_required: bool,
    lanes_bounded: bool,
    weak_generic_evidence_only: bool = False,
) -> str:
    if not lane_runtime_safe:
        return "runtime_action_requested"
    if not validation_required:
        return "local_validation_not_required"
    if not lanes_bounded:
        return "unbounded_proposal_lane"
    if rejected_candidate_count:
        return "rejected_candidates_present"
    if not proposal_lane_count:
        return "no_skill_route_lanes"
    if weak_generic_evidence_only:
        return "weak_generic_upstream_evidence"
    if downgraded_candidate_count:
        return "unsupported_lanes_downgraded"
    return "none"


def skill_route_discovery_activation_gate(failure_mode: str) -> dict[str, Any]:
    """Return the controller-facing activation gate for skill discovery lanes."""

    if failure_mode == "none":
        decision = "ready_for_local_proposal_activation"
        local_proposal_activation_allowed = True
    elif failure_mode == "weak_generic_upstream_evidence":
        decision = "review_weak_evidence_before_activation"
        local_proposal_activation_allowed = False
    elif failure_mode == "unsupported_lanes_downgraded":
        decision = "review_degraded_lane_before_activation"
        local_proposal_activation_allowed = False
    else:
        decision = "blocked_before_activation"
        local_proposal_activation_allowed = False

    return {
        "controller_surface": "skill_route_discovery_lane",
        "activation_scope": "local_proposal_only",
        "decision": decision,
        "reason": failure_mode,
        "local_proposal_activation_allowed": local_proposal_activation_allowed,
        "external_skill_activation_allowed": False,
    }


def skill_route_discovery_evidence_strength(raw_input: dict[str, Any], *, source_kind: str) -> dict[str, Any]:
    """Summarize whether discovery evidence is specific enough for local activation."""

    records = _skill_route_discovery_evidence_records(raw_input, source_kind=source_kind)
    local_corroboration = _skill_route_discovery_local_corroboration(raw_input)
    weak_generic_count = 0
    specific_detail_count = 0
    explicit_route_hint_count = 0
    local_validation_signal_count = 0

    for record in records:
        text = _skill_route_discovery_record_text(record)
        event_kind = str(
            record.get("event_kind")
            or record.get("discovery_event_kind")
            or record.get("item_kind")
            or record.get("kind")
            or ""
        ).casefold()
        is_pr_or_push = any(marker in event_kind for marker in ("pullrequest", "pull_request", "pr", "push"))
        is_generic = any(
            marker in text
            for marker in (
                "generic",
                "missing detail",
                "missing pr detail",
                "missing implementation",
                "untitled",
                "lifecycle",
                "left review comments",
                "found potential problems",
            )
        )
        if is_pr_or_push and is_generic:
            weak_generic_count += 1
        if any(
            marker in text
            for marker in (
                "commit diff",
                "diff",
                "failing local test",
                "inspected pr body",
                "local validation",
                "release note",
                "test evidence",
                "validated",
                "validation evidence",
            )
        ):
            specific_detail_count += 1
        if record.get("route_hints"):
            explicit_route_hint_count += 1
        if any(marker in text for marker in ("ci", "e2e", "pytest", "test", "validated", "validation")):
            local_validation_signal_count += 1

    if not records:
        tier = "empty"
        activation_evidence_sufficient = False
    elif weak_generic_count and not local_corroboration:
        tier = "weak_generic_upstream_movement"
        activation_evidence_sufficient = False
    elif weak_generic_count:
        tier = "generic_upstream_movement_with_local_corroboration"
        activation_evidence_sufficient = True
    else:
        tier = "specific_route_or_validation_evidence"
        activation_evidence_sufficient = True

    return {
        "tier": tier,
        "record_count": len(records),
        "weak_generic_movement_count": weak_generic_count,
        "specific_detail_count": specific_detail_count,
        "explicit_route_hint_count": explicit_route_hint_count,
        "local_validation_signal_count": local_validation_signal_count,
        "local_corroborating_signal_count": len(local_corroboration),
        "corroboration_required_for_generic_upstream_movement": bool(weak_generic_count),
        "activation_evidence_sufficient": activation_evidence_sufficient,
    }


def _skill_route_discovery_evidence_records(raw_input: dict[str, Any], *, source_kind: str) -> list[dict[str, Any]]:
    key = {
        "candidates": "candidates",
        "evidence_items": "evidence_items",
        "summaries": "summaries",
    }.get(source_kind, "")
    values = raw_input.get(key) if key else []
    if not isinstance(values, list):
        return []
    return [record for record in values if isinstance(record, dict)]


def _skill_route_discovery_record_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("name", "title", "summary", "evidence_summary", "relevance_reason"):
        value = record.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("topics", "candidate_lanes", "suggested_lanes"):
        value = record.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def _skill_route_discovery_local_corroboration(raw_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Return body-free local signals that can corroborate generic upstream movement."""

    signals = raw_input.get("local_corroboration")
    if not isinstance(signals, list):
        return []

    accepted: list[dict[str, Any]] = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        signal_kind = optional_string(signal.get("signal_kind")) or ""
        validation_command = optional_string(signal.get("validation_command")) or ""
        local_artifact = optional_string(signal.get("local_artifact")) or ""
        if signal_kind not in {
            "failing_local_test",
            "focused_fixture",
            "local_validation",
            "operator_review_note",
            "replay_fixture",
        }:
            continue
        if not validation_command and not local_artifact:
            continue
        accepted.append(
            {
                "signal_kind": signal_kind,
                "validation_command_present": bool(validation_command),
                "local_artifact_present": bool(local_artifact),
            }
        )
    return accepted


def evaluate_rendered_html_artifact_validation(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Validate browser-observable rendered HTML behavior without exporting HTML or URLs."""

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    artifact = raw_input.get("artifact") if isinstance(raw_input.get("artifact"), dict) else {}
    browser = raw_input.get("browser") if isinstance(raw_input.get("browser"), dict) else {}
    script_probe = raw_input.get("script_probe") if isinstance(raw_input.get("script_probe"), dict) else {}
    link_probes = raw_input.get("link_probes") if isinstance(raw_input.get("link_probes"), list) else []
    snapshot_gate = raw_input.get("snapshot_gate") if isinstance(raw_input.get("snapshot_gate"), dict) else {}

    artifact_kind = optional_string(artifact.get("kind")) or "html"
    rendered_boundary = optional_string(artifact.get("rendered_boundary")) or "rendered_html_artifact"
    html_body = optional_string(artifact.get("html_body")) or ""
    html_hash = optional_string(artifact.get("html_hash")) or (stable_text_hash(html_body) if html_body else None)

    browser_available = browser.get("available") is not False
    sandbox_allows_scripts = truthy(browser.get("sandbox_allows_scripts")) or truthy(
        script_probe.get("sandbox_allows_scripts")
    )
    script_expected = script_probe.get("expected_execution") is not False
    script_observed = truthy(script_probe.get("observed_execution"))
    script_passed = (not script_expected) or (browser_available and sandbox_allows_scripts and script_observed)

    evaluated_links = [evaluate_rendered_html_link_probe(probe) for probe in link_probes]
    same_frame_links = [link for link in evaluated_links if link["declared_target"] in {"", "_self"}]
    new_frame_links = [link for link in evaluated_links if link["declared_target"] == "_blank"]
    links_passed = bool(evaluated_links) and all(link["passed"] for link in evaluated_links)
    evaluated_snapshot_gate = evaluate_rendered_html_snapshot_gate(snapshot_gate)

    failure_mode = rendered_html_validation_failure_mode(
        artifact_kind=artifact_kind,
        browser_available=browser_available,
        script_expected=script_expected,
        script_passed=script_passed,
        links_present=bool(evaluated_links),
        links_passed=links_passed,
        snapshot_gate=evaluated_snapshot_gate,
    )
    route_status = "passed" if failure_mode == "none" else "blocked"

    return {
        "schema_version": 1,
        "behavior": "rendered_html_artifact_validation",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "artifact": {
            "kind": artifact_kind,
            "rendered_boundary": rendered_boundary,
            "html_hash": html_hash,
            "html_body_exported": False,
        },
        "browser": {
            "available": browser_available,
            "sandbox_allows_scripts": sandbox_allows_scripts,
            "raw_url_exported": False,
        },
        "script_execution": {
            "expected": script_expected,
            "observed": script_observed,
            "passed": script_passed,
        },
        "link_navigation": {
            "probe_count": len(evaluated_links),
            "same_frame_anchor_count": len(same_frame_links),
            "target_blank_anchor_count": len(new_frame_links),
            "all_expected_new_frame": all(link["expected_navigation"] == "new_frame" for link in evaluated_links),
            "passed": links_passed,
            "probes": evaluated_links,
        },
        "snapshot_gate": evaluated_snapshot_gate,
        "privacy": {
            "html_body_exported": False,
            "raw_urls_exported": False,
            "hashes_only": True,
            "snapshot_paths_exported": False,
        },
    }


def evaluate_rendered_html_snapshot_gate(snapshot_gate: dict[str, Any]) -> dict[str, Any]:
    """Validate a UI snapshot gate without exporting screenshot paths or image bodies."""

    state = normalize_snapshot_gate_state(snapshot_gate.get("state"))
    required = truthy(snapshot_gate.get("required")) or state in {"empty_landing", "baseline"}
    baseline_hash = optional_string(snapshot_gate.get("baseline_hash"))
    current_hash = optional_string(snapshot_gate.get("current_hash"))
    diff_hash = optional_string(snapshot_gate.get("diff_hash"))
    diff_status = normalize_snapshot_diff_status(snapshot_gate.get("diff_status"))
    empty_state_expected = truthy(snapshot_gate.get("empty_state_expected")) or state == "empty_landing"
    empty_state_observed = truthy(snapshot_gate.get("empty_state_observed"))
    allow_changed = truthy(snapshot_gate.get("allow_changed"))

    if not required:
        failure_mode = "none"
    elif not baseline_hash:
        failure_mode = "ui_snapshot_baseline_missing"
    elif not current_hash:
        failure_mode = "ui_snapshot_current_missing"
    elif empty_state_expected and not empty_state_observed:
        failure_mode = "ui_snapshot_empty_state_missing"
    elif diff_status not in {"clean", "accepted", "approved"} and not allow_changed:
        failure_mode = "ui_snapshot_diff_unapproved"
    else:
        failure_mode = "none"

    return {
        "required": required,
        "state": state,
        "baseline_hash_present": bool(baseline_hash),
        "current_hash_present": bool(current_hash),
        "diff_hash_present": bool(diff_hash),
        "diff_status": diff_status,
        "empty_state_expected": empty_state_expected,
        "empty_state_observed": empty_state_observed,
        "passed": failure_mode == "none",
        "failure_mode": failure_mode,
        "raw_snapshot_paths_exported": False,
        "raw_snapshot_images_exported": False,
    }


def normalize_snapshot_gate_state(value: Any) -> str:
    state = (optional_string(value) or "unspecified").strip().lower().replace("-", "_")
    if state in {"empty_landing", "baseline", "populated", "unspecified"}:
        return state
    return "unspecified"


def normalize_snapshot_diff_status(value: Any) -> str:
    status = (optional_string(value) or "missing").strip().lower().replace("-", "_")
    if status in {"accepted", "approved", "changed", "clean", "missing", "unreviewed"}:
        return status
    return "unreviewed"


def evaluate_rendered_html_link_probe(probe: Any) -> dict[str, Any]:
    probe_data = probe if isinstance(probe, dict) else {}
    label = optional_string(probe_data.get("label")) or "link"
    href = optional_string(probe_data.get("href")) or ""
    declared_target = normalize_link_target(probe_data.get("declared_target") or probe_data.get("target"))
    expected_navigation = normalize_rendered_html_navigation(probe_data.get("expected_navigation"), default="new_frame")
    observed_navigation = normalize_rendered_html_navigation(probe_data.get("observed_navigation"), default="none")
    return {
        "label": label,
        "href_hash": stable_text_hash(href) if href else None,
        "declared_target": declared_target,
        "expected_navigation": expected_navigation,
        "observed_navigation": observed_navigation,
        "passed": observed_navigation == expected_navigation,
        "raw_href_exported": False,
    }


def normalize_link_target(value: Any) -> str:
    target = (optional_string(value) or "").strip().lower()
    if target in {"_blank", "_self", "_parent", "_top"}:
        return target
    return ""


def normalize_rendered_html_navigation(value: Any, *, default: str) -> str:
    navigation = (optional_string(value) or default).strip().lower().replace("-", "_")
    if navigation in {"new_frame", "same_frame", "none", "blocked"}:
        return navigation
    return default


def rendered_html_validation_failure_mode(
    *,
    artifact_kind: str,
    browser_available: bool,
    script_expected: bool,
    script_passed: bool,
    links_present: bool,
    links_passed: bool,
    snapshot_gate: dict[str, Any],
) -> str:
    if artifact_kind != "html":
        return "not_html_artifact"
    if not browser_available:
        return "browser_probe_unavailable"
    if script_expected and not script_passed:
        return "rendered_html_script_execution_missing"
    if not links_present:
        return "rendered_html_link_probe_missing"
    if not links_passed:
        return "rendered_html_link_navigation_mismatch"
    if snapshot_gate.get("required") and not snapshot_gate.get("passed"):
        return optional_string(snapshot_gate.get("failure_mode")) or "ui_snapshot_gate_failed"
    return "none"


def evaluate_push_delivery_path(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Validate a mocked promotion push and activation handoff without remote access."""

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    promotion = raw_input.get("promotion") if isinstance(raw_input.get("promotion"), dict) else {}
    delivery = raw_input.get("delivery") if isinstance(raw_input.get("delivery"), dict) else {}
    runner = raw_input.get("runner") if isinstance(raw_input.get("runner"), dict) else {}
    activation = raw_input.get("activation") if isinstance(raw_input.get("activation"), dict) else {}
    rollback = raw_input.get("rollback") if isinstance(raw_input.get("rollback"), dict) else {}

    promotion_successful = (
        truthy(promotion.get("promoted")) and optional_string(promotion.get("target_head")) is not None
    )
    push_requested = truthy(delivery.get("push_requested"))
    remote_configured = optional_string(delivery.get("remote_name")) is not None
    branch_configured = optional_string(delivery.get("branch")) is not None
    mock_only = truthy(delivery.get("mock_only"))
    credentials_required = truthy(delivery.get("credentials_required"))
    network_required = truthy(delivery.get("network_required"))
    external_calls_attempted = push_requested and not mock_only

    runner_invoked = truthy(runner.get("invoked"))
    runner_mocked = truthy(runner.get("mocked"))
    runner_returncode = optional_int(runner.get("returncode"))
    runner_command = runner.get("command") if isinstance(runner.get("command"), list) else []
    expected_command_shape = [
        "git",
        "push",
        optional_string(delivery.get("remote_name")) or "",
        optional_string(delivery.get("branch")) or "",
    ]
    command_shape_matched = [str(part) for part in runner_command] == expected_command_shape

    activation_recorded = truthy(activation.get("activation_recorded"))
    restart_request_recorded = truthy(activation.get("restart_request_recorded"))
    activation_head_matches = optional_string(activation.get("activated_head")) == optional_string(
        promotion.get("target_head")
    )
    rollback_available = truthy(rollback.get("created")) and optional_string(rollback.get("ref")) is not None
    artifact_recorded = optional_string(rollback.get("artifact_path")) is not None

    failure_mode = push_delivery_failure_mode(
        promotion_successful=promotion_successful,
        push_requested=push_requested,
        remote_configured=remote_configured,
        branch_configured=branch_configured,
        external_calls_attempted=external_calls_attempted,
        credentials_required=credentials_required,
        network_required=network_required,
        runner_invoked=runner_invoked,
        runner_mocked=runner_mocked,
        runner_returncode=runner_returncode,
        command_shape_matched=command_shape_matched,
        activation_recorded=activation_recorded,
        restart_request_recorded=restart_request_recorded,
        activation_head_matches=activation_head_matches,
        rollback_available=rollback_available,
        artifact_recorded=artifact_recorded,
    )

    return {
        "schema_version": 1,
        "behavior": "push_delivery_path",
        "task_id": task_id,
        "route_status": "passed" if failure_mode == "none" else "failed",
        "promotion": {
            "promoted": promotion_successful,
            "target_head_hash": stable_text_hash(optional_string(promotion.get("target_head")) or "")
            if promotion_successful
            else None,
        },
        "delivery": {
            "push_requested": push_requested,
            "remote_configured": remote_configured,
            "branch_configured": branch_configured,
            "mock_only": mock_only,
            "credentials_required": credentials_required,
            "network_required": network_required,
            "external_calls_attempted": external_calls_attempted,
        },
        "runner": {
            "invoked": runner_invoked,
            "mocked": runner_mocked,
            "returncode": runner_returncode,
            "command_shape_matched": command_shape_matched,
            "command_hash": stable_json_hash(runner_command) if runner_command else None,
        },
        "activation": {
            "activation_recorded": activation_recorded,
            "restart_request_recorded": restart_request_recorded,
            "activation_head_matches": activation_head_matches,
        },
        "rollback": {
            "available": rollback_available,
            "artifact_recorded": artifact_recorded,
            "recovery_mode": "explicit_operator_reset",
        },
        "privacy": {
            "raw_commands_exported": False,
            "raw_remote_exported": False,
            "raw_branch_exported": False,
            "hashes_only": True,
        },
        "failure_mode": failure_mode,
    }


def push_delivery_failure_mode(
    *,
    promotion_successful: bool,
    push_requested: bool,
    remote_configured: bool,
    branch_configured: bool,
    external_calls_attempted: bool,
    credentials_required: bool,
    network_required: bool,
    runner_invoked: bool,
    runner_mocked: bool,
    runner_returncode: int | None,
    command_shape_matched: bool,
    activation_recorded: bool,
    restart_request_recorded: bool,
    activation_head_matches: bool,
    rollback_available: bool,
    artifact_recorded: bool,
) -> str:
    if not promotion_successful:
        return "promotion_not_successful"
    if not push_requested:
        return "push_not_requested"
    if not remote_configured:
        return "remote_missing"
    if not branch_configured:
        return "branch_missing"
    if external_calls_attempted:
        return "external_push_attempted"
    if credentials_required:
        return "credentials_required"
    if network_required:
        return "network_required"
    if not runner_invoked:
        return "runner_not_invoked"
    if not runner_mocked:
        return "runner_not_mocked"
    if runner_returncode != 0:
        return "push_failed"
    if not command_shape_matched:
        return "push_command_mismatch"
    if not activation_recorded:
        return "activation_not_recorded"
    if not restart_request_recorded:
        return "restart_request_not_recorded"
    if not activation_head_matches:
        return "activation_head_mismatch"
    if not rollback_available:
        return "rollback_missing"
    if not artifact_recorded:
        return "rollback_artifact_missing"
    return "none"


def evaluate_workspace_changes_panel(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Check that workspace edits have visible changes-panel evidence without exporting paths or file bodies."""

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    workspace = raw_input.get("workspace") if isinstance(raw_input.get("workspace"), dict) else {}
    changes_panel = raw_input.get("changes_panel") if isinstance(raw_input.get("changes_panel"), dict) else {}
    performed_edits = raw_input.get("performed_edits") if isinstance(raw_input.get("performed_edits"), list) else []
    panel_entries = changes_panel.get("entries") if isinstance(changes_panel.get("entries"), list) else []
    runner_workspace_root = optional_string(workspace.get("runner_workspace_root"))

    edit_results = [
        evaluate_workspace_change_edit(edit, runner_workspace_root=runner_workspace_root) for edit in performed_edits
    ]
    panel_results = [
        evaluate_workspace_change_panel_entry(entry, runner_workspace_root=runner_workspace_root)
        for entry in panel_entries
    ]
    visible_entry_ids = {str(result["edit_id"]) for result in panel_results if result["edit_id"] and result["visible"]}
    required_edit_ids = [
        str(result["edit_id"])
        for result in edit_results
        if result["exists_on_disk"] and result["requires_panel_visibility"]
    ]
    missing_visible_edit_ids = sorted(set(required_edit_ids) - visible_entry_ids)
    performed_edit_ids = {str(result["edit_id"]) for result in edit_results if result["exists_on_disk"]}
    unexpected_visible_edit_ids = sorted(
        {
            str(result["edit_id"])
            for result in panel_results
            if result["visible"]
            and result["kind"] == "changed_file"
            and result["edit_id"]
            and str(result["edit_id"]) not in performed_edit_ids
        }
    )
    stale_visible_edit_ids = workspace_changes_stale_visible_edit_ids(
        edit_results=edit_results,
        panel_results=panel_results,
    )
    outside_runner_workspace_edit_ids = workspace_changes_outside_runner_workspace_edit_ids(edit_results)
    outside_runner_workspace_panel_ids = workspace_changes_outside_runner_workspace_panel_ids(panel_results)

    is_git_repo = truthy(workspace.get("is_git_repo"))
    runner_workspace_configured = truthy(workspace.get("runner_workspace_configured"))
    unrecorded_edit_count = sum(
        1 for result in edit_results if result["exists_on_disk"] and not result["record_change_observed"]
    )
    has_tracking_limitation_entry = any(
        result["kind"] == "tracking_limitation" and result["visible"] for result in panel_results
    )
    panel_reason = optional_string(changes_panel.get("reason")) or ""
    non_git_limitation_present = (
        is_git_repo
        or unrecorded_edit_count == 0
        or (has_tracking_limitation_entry and panel_reason == "non_git_workspace_limited_tracking")
    )
    git_metadata_required = bool(changes_panel.get("git_metadata_required"))

    visible_entry_count = sum(1 for result in panel_results if result["visible"])
    failure_mode = workspace_changes_panel_failure_mode(
        runner_workspace_configured=runner_workspace_configured,
        visible_entry_count=visible_entry_count,
        missing_visible_edit_ids=missing_visible_edit_ids,
        unexpected_visible_edit_ids=unexpected_visible_edit_ids,
        stale_visible_edit_ids=stale_visible_edit_ids,
        outside_runner_workspace_edit_ids=outside_runner_workspace_edit_ids,
        outside_runner_workspace_panel_ids=outside_runner_workspace_panel_ids,
        non_git_limitation_present=non_git_limitation_present,
        git_metadata_required=git_metadata_required,
        is_git_repo=is_git_repo,
    )

    return {
        "schema_version": 1,
        "behavior": "workspace_changes_panel",
        "task_id": task_id,
        "route_status": "passed" if failure_mode == "none" else "failed",
        "failure_mode": failure_mode,
        "workspace": {
            "is_git_repo": is_git_repo,
            "runner_workspace_configured": runner_workspace_configured,
            "runner_workspace_root_hash": stable_text_hash(runner_workspace_root) if runner_workspace_root else None,
            "git_metadata_required": git_metadata_required,
            "non_git_without_git_metadata": not is_git_repo and not git_metadata_required,
        },
        "changes_panel": {
            "available": truthy(changes_panel.get("available")),
            "reason": panel_reason,
            "entry_count": len(panel_results),
            "visible_entry_count": visible_entry_count,
            "has_tracking_limitation_entry": has_tracking_limitation_entry,
            "non_git_limitation_present": non_git_limitation_present,
            "empty_panel_silent": visible_entry_count == 0 and bool(required_edit_ids),
        },
        "edits": {
            "performed_count": len(edit_results),
            "required_visible_count": len(required_edit_ids),
            "visible_required_count": len(required_edit_ids) - len(missing_visible_edit_ids),
            "unrecorded_edit_count": unrecorded_edit_count,
            "required_edit_ids": required_edit_ids,
            "missing_visible_edit_ids": missing_visible_edit_ids,
            "unexpected_visible_edit_ids": unexpected_visible_edit_ids,
            "stale_visible_edit_ids": stale_visible_edit_ids,
            "outside_runner_workspace_edit_ids": outside_runner_workspace_edit_ids,
            "outside_runner_workspace_panel_ids": outside_runner_workspace_panel_ids,
            "raw_paths_exported": False,
            "raw_contents_exported": False,
            "items": edit_results,
        },
        "panel_entries": panel_results,
        "privacy": {
            "raw_paths_exported": False,
            "raw_contents_exported": False,
            "path_hashes_only": True,
        },
    }


def evaluate_workspace_change_edit(edit: Any, *, runner_workspace_root: str | None = None) -> dict[str, Any]:
    edit_data = edit if isinstance(edit, dict) else {}
    edit_id = optional_string(edit_data.get("edit_id")) or "workspace-edit"
    origin = optional_string(edit_data.get("origin")) or "unknown"
    path = optional_string(edit_data.get("path"))
    content = optional_string(edit_data.get("content"))
    exists_on_disk = truthy(edit_data.get("exists_on_disk"))
    record_change_observed = truthy(edit_data.get("record_change_observed"))
    requires_panel_visibility = origin in {
        "external_process",
        "filesystem_endpoint",
        "native_harness",
        "native_harness_cli",
        "sys_os_shell",
    }
    return {
        "edit_id": edit_id,
        "origin": origin,
        "exists_on_disk": exists_on_disk,
        "record_change_observed": record_change_observed,
        "requires_panel_visibility": requires_panel_visibility,
        "path_hash": stable_text_hash(path) if path else None,
        "content_hash": stable_text_hash(content) if content else None,
        "inside_runner_workspace": workspace_path_is_inside(path, runner_workspace_root),
    }


def evaluate_workspace_change_panel_entry(entry: Any, *, runner_workspace_root: str | None = None) -> dict[str, Any]:
    entry_data = entry if isinstance(entry, dict) else {}
    path = optional_string(entry_data.get("path"))
    return {
        "edit_id": optional_string(entry_data.get("edit_id")),
        "kind": optional_string(entry_data.get("kind")) or "changed_file",
        "visible": truthy(entry_data.get("visible")),
        "path_hash": stable_text_hash(path) if path else None,
        "inside_runner_workspace": workspace_path_is_inside(path, runner_workspace_root),
    }


def workspace_path_is_inside(path: str | None, runner_workspace_root: str | None) -> bool | None:
    if not path or not runner_workspace_root:
        return None

    normalized_path = normalize_workspace_path(path)
    normalized_root = normalize_workspace_path(runner_workspace_root)
    return normalized_path == normalized_root or normalized_path.startswith(f"{normalized_root}/")


def normalize_workspace_path(path: str) -> str:
    normalized = path.replace("\\", "/").rstrip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized.casefold()


def workspace_changes_stale_visible_edit_ids(
    *,
    edit_results: list[dict[str, Any]],
    panel_results: list[dict[str, Any]],
) -> list[str]:
    edit_path_hashes = {
        str(result["edit_id"]): result["path_hash"]
        for result in edit_results
        if result["exists_on_disk"] and result["path_hash"]
    }
    stale_ids: set[str] = set()
    for result in panel_results:
        edit_id = optional_string(result.get("edit_id"))
        panel_path_hash = result.get("path_hash")
        if (
            result["visible"]
            and result["kind"] == "changed_file"
            and edit_id
            and panel_path_hash
            and edit_path_hashes.get(edit_id)
            and panel_path_hash != edit_path_hashes[edit_id]
        ):
            stale_ids.add(edit_id)
    return sorted(stale_ids)


def workspace_changes_outside_runner_workspace_edit_ids(edit_results: list[dict[str, Any]]) -> list[str]:
    return sorted(
        str(result["edit_id"])
        for result in edit_results
        if result["exists_on_disk"]
        and result["requires_panel_visibility"]
        and result["inside_runner_workspace"] is False
    )


def workspace_changes_outside_runner_workspace_panel_ids(panel_results: list[dict[str, Any]]) -> list[str]:
    return sorted(
        str(result["edit_id"])
        for result in panel_results
        if result["visible"]
        and result["kind"] == "changed_file"
        and result["edit_id"]
        and result["inside_runner_workspace"] is False
    )


def workspace_changes_panel_failure_mode(
    *,
    runner_workspace_configured: bool,
    visible_entry_count: int,
    missing_visible_edit_ids: list[str],
    unexpected_visible_edit_ids: list[str],
    stale_visible_edit_ids: list[str],
    outside_runner_workspace_edit_ids: list[str],
    outside_runner_workspace_panel_ids: list[str],
    non_git_limitation_present: bool,
    git_metadata_required: bool,
    is_git_repo: bool,
) -> str:
    if not runner_workspace_configured:
        return "runner_workspace_missing"
    if visible_entry_count < 1:
        return "changes_panel_empty"
    if missing_visible_edit_ids:
        return "missing_visible_change_entries"
    if stale_visible_edit_ids:
        return "stale_visible_change_entries"
    if unexpected_visible_edit_ids:
        return "unexpected_visible_change_entries"
    if outside_runner_workspace_edit_ids:
        return "edit_outside_runner_workspace"
    if outside_runner_workspace_panel_ids:
        return "panel_entry_outside_runner_workspace"
    if not non_git_limitation_present:
        return "missing_non_git_tracking_limitation"
    if not is_git_repo and git_metadata_required:
        return "git_metadata_required_for_non_git_workspace"
    return "none"


def evaluate_mock_e2e_runner_tier(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Validate tiered mock runner journeys without credentials, network, or real provider calls."""

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    provider = raw_input.get("provider") if isinstance(raw_input.get("provider"), dict) else {}
    agent_config = raw_input.get("agent_config") if isinstance(raw_input.get("agent_config"), dict) else {}
    runner_tiers = raw_input.get("runner_tiers") if isinstance(raw_input.get("runner_tiers"), list) else []
    known_failure = raw_input.get("known_failure") if isinstance(raw_input.get("known_failure"), dict) else {}
    ci_round_trip = raw_input.get("ci_round_trip") if isinstance(raw_input.get("ci_round_trip"), dict) else {}
    approval_boundary_input = (
        raw_input.get("approval_boundary") if isinstance(raw_input.get("approval_boundary"), dict) else {}
    )
    agent_config_route = evaluate_mock_e2e_agent_config_yaml(agent_config)
    tier_results = [evaluate_mock_e2e_runner_tier_item(tier) for tier in runner_tiers]
    known_failure_route = evaluate_mock_e2e_known_failure_route(known_failure)
    ci_round_trip_diagnostic = evaluate_mock_e2e_ci_round_trip(ci_round_trip)
    approval_boundary = evaluate_mock_e2e_approval_boundary(approval_boundary_input, source_path=source_path)

    provider_enabled = truthy(provider.get("enabled"))
    mock_only = truthy(raw_input.get("mock_only")) or truthy(provider.get("mock_only")) or not provider_enabled
    external_calls_attempted = provider_enabled and not mock_only
    credentials_required = truthy(provider.get("credentials_required"))
    network_required = truthy(provider.get("network_required"))

    tier_count = len(tier_results)
    host_native_count = sum(1 for tier in tier_results if tier["lane"] == "host_native")
    miscellaneous_count = sum(1 for tier in tier_results if tier["lane"] == "miscellaneous")
    all_tiers_mocked = bool(tier_results) and all(tier["mocked"] for tier in tier_results)
    all_tiers_passed = bool(tier_results) and all(tier["passed"] for tier in tier_results)
    tool_boundaries_mocked = all(tier["tool_boundary"]["all_operations_mocked"] for tier in tier_results)
    failure_mode = mock_e2e_runner_tier_failure_mode(
        tier_count=tier_count,
        host_native_count=host_native_count,
        miscellaneous_count=miscellaneous_count,
        external_calls_attempted=external_calls_attempted,
        credentials_required=credentials_required,
        network_required=network_required,
        all_tiers_mocked=all_tiers_mocked,
        all_tiers_passed=all_tiers_passed,
        tool_boundaries_mocked=tool_boundaries_mocked,
        known_failure_route_passed=known_failure_route["passed"],
        ci_round_trip_passed=ci_round_trip_diagnostic["passed"],
        approval_boundary_passed=approval_boundary["passed"],
        agent_config_route_passed=agent_config_route["passed"],
        agent_config_configured=agent_config_route["configured"],
        agent_config_parse_error=agent_config_route["parse_error"],
        agent_config_tool_count=int(agent_config_route["function_tool_count"]),
        agent_config_executable_count=int(agent_config_route["executable_tool_count"]),
    )

    return {
        "schema_version": 1,
        "behavior": "mock_e2e_runner_tier",
        "task_id": task_id,
        "route_status": "passed" if failure_mode == "none" else "failed",
        "provider": {
            "name": optional_string(provider.get("name")) or "external-provider",
            "enabled": provider_enabled,
            "mock_only": mock_only,
            "credentials_required": credentials_required,
            "network_required": network_required,
            "external_calls_attempted": external_calls_attempted,
        },
        "agent_config": agent_config_route,
        "runner_tiers": {
            "tier_count": tier_count,
            "host_native_count": host_native_count,
            "miscellaneous_count": miscellaneous_count,
            "all_tiers_mocked": all_tiers_mocked,
            "all_tiers_passed": all_tiers_passed,
            "tool_boundaries_mocked": tool_boundaries_mocked,
            "tiers": tier_results,
        },
        "known_failure_route": known_failure_route,
        "ci_round_trip": ci_round_trip_diagnostic,
        "approval_boundary": approval_boundary,
        "privacy": {
            "raw_commands_exported": False,
            "raw_paths_exported": False,
            "raw_contents_exported": False,
            "raw_agent_yaml_exported": False,
            "hashes_only": True,
        },
        "failure_mode": failure_mode,
    }


def evaluate_mock_e2e_agent_config_yaml(agent_config: dict[str, Any]) -> dict[str, Any]:
    """Parse mocked single-file agent YAML into controller-safe route metadata."""

    yaml_text = optional_string(agent_config.get("yaml") or agent_config.get("content"))
    if not yaml_text:
        return {
            "configured": False,
            "passed": True,
            "parse_error": False,
            "yaml_hash": None,
            "executor_harness_hash": None,
            "function_tool_count": 0,
            "executable_tool_count": 0,
            "non_executable_tool_count": 0,
            "route_counts": {},
            "required_tool_count": 0,
            "missing_required_tool_count": 0,
            "tool_name_hashes": [],
            "raw_yaml_exported": False,
            "raw_tool_metadata_exported": False,
        }

    from blackhole_agent.tool_routing import (
        build_tool_routing_preflight,
        parse_single_file_agent_yaml,
        tool_descriptors_from_agent_config,
    )

    try:
        parsed = parse_single_file_agent_yaml(yaml_text)
        descriptors = tool_descriptors_from_agent_config(parsed, session_id="mock-e2e-agent-config")
        required_tool_names = string_list(agent_config.get("required_tool_names"))
        preflight = build_tool_routing_preflight(descriptors, required_tool_names=required_tool_names)
        executor = parsed.get("executor") if isinstance(parsed.get("executor"), dict) else {}
        executable_count = len(preflight["executable_tool_names"])
        tool_count = int(preflight["tool_count"])
        missing_required_count = len(preflight["missing_required_tool_names"])
        passed = tool_count > 0 and executable_count == tool_count and missing_required_count == 0
        return {
            "configured": True,
            "passed": passed,
            "parse_error": False,
            "yaml_hash": stable_text_hash(yaml_text),
            "executor_harness_hash": stable_text_hash(str(executor.get("harness")))
            if executor.get("harness")
            else None,
            "function_tool_count": tool_count,
            "executable_tool_count": executable_count,
            "non_executable_tool_count": tool_count - executable_count,
            "route_counts": preflight["route_counts"],
            "required_tool_count": len(preflight["required_tool_names"]),
            "missing_required_tool_count": missing_required_count,
            "tool_name_hashes": [stable_text_hash(str(name)) for name in sorted(preflight["executable_tool_names"])],
            "raw_yaml_exported": False,
            "raw_tool_metadata_exported": False,
        }
    except Exception as error:
        return {
            "configured": True,
            "passed": False,
            "parse_error": True,
            "error_type": type(error).__name__,
            "yaml_hash": stable_text_hash(yaml_text),
            "executor_harness_hash": None,
            "function_tool_count": 0,
            "executable_tool_count": 0,
            "non_executable_tool_count": 0,
            "route_counts": {},
            "required_tool_count": 0,
            "missing_required_tool_count": 0,
            "tool_name_hashes": [],
            "raw_yaml_exported": False,
            "raw_tool_metadata_exported": False,
        }


def evaluate_mock_e2e_runner_tier_item(tier: Any) -> dict[str, Any]:
    tier_data = tier if isinstance(tier, dict) else {}
    lane = normalize_mock_e2e_runner_lane(tier_data.get("lane") or tier_data.get("name"))
    steps = tier_data.get("steps") if isinstance(tier_data.get("steps"), list) else []
    operations = tier_data.get("operations") if isinstance(tier_data.get("operations"), list) else []
    step_results = [evaluate_mock_e2e_step(step) for step in steps]
    operation_results = [evaluate_mock_e2e_operation(operation) for operation in operations]
    mocked = truthy(tier_data.get("mocked")) or bool(step_results or operation_results)
    steps_passed = bool(step_results) and all(step["expectation_passed"] for step in step_results)
    all_operations_mocked = all(operation["mocked"] for operation in operation_results)
    operations_passed = all(operation["expectation_passed"] for operation in operation_results)
    return {
        "lane": lane,
        "name_hash": stable_text_hash(optional_string(tier_data.get("name")) or lane),
        "mocked": mocked,
        "step_count": len(step_results),
        "steps_passed": steps_passed,
        "passed": mocked and steps_passed and all_operations_mocked and operations_passed,
        "tool_boundary": {
            "operation_count": len(operation_results),
            "mocked_count": sum(1 for operation in operation_results if operation["mocked"]),
            "all_operations_mocked": all_operations_mocked,
            "all_expectations_passed": operations_passed,
            "operations": operation_results,
        },
    }


def normalize_mock_e2e_runner_lane(value: Any) -> str:
    text = (optional_string(value) or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"host_native", "native", "host"}:
        return "host_native"
    if text in {"miscellaneous", "misc", "misc_mock"}:
        return "miscellaneous"
    return "unknown"


def evaluate_mock_e2e_step(step: Any) -> dict[str, Any]:
    step_data = step if isinstance(step, dict) else {}
    observed = optional_string(step_data.get("observed")) or ""
    expect_contains = optional_string(step_data.get("expect_contains"))
    return {
        "id": optional_string(step_data.get("id")) or "step",
        "observed_hash": stable_text_hash(observed) if observed else None,
        "expectation_passed": expect_contains is None or expect_contains in observed,
    }


def evaluate_mock_e2e_operation(operation: Any) -> dict[str, Any]:
    operation_data = operation if isinstance(operation, dict) else {}
    command = optional_string(operation_data.get("command"))
    path = optional_string(operation_data.get("path"))
    content = optional_string(operation_data.get("mock_content")) or ""
    expect_contains = optional_string(operation_data.get("expect_content_contains"))
    return {
        "name": optional_string(operation_data.get("name")) or "operation",
        "mocked": truthy(operation_data.get("mocked")),
        "command_hash": stable_text_hash(command) if command else None,
        "path_hash": stable_text_hash(path) if path else None,
        "content_hash": stable_text_hash(content) if content else None,
        "expectation_passed": expect_contains is None or expect_contains in content,
    }


def evaluate_mock_e2e_approval_boundary(approval_boundary: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Require a mocked e2e journey to preserve a native ASK/review path when declared."""

    required = truthy(approval_boundary.get("required"))
    if not required:
        return {
            "required": False,
            "passed": True,
            "route_status": "not_required",
            "failure_mode": "none",
            "ask_preserved": False,
            "controller_surface": "none",
            "tool_executed": False,
            "raw_payload_exported": False,
        }

    policy_hook = approval_boundary.get("policy_hook") if isinstance(approval_boundary.get("policy_hook"), dict) else {}
    tool_call = approval_boundary.get("tool_call") if isinstance(approval_boundary.get("tool_call"), dict) else {}
    policy_output = evaluate_native_tool_call_policy(
        {
            "task_id": optional_string(approval_boundary.get("task_id")) or source_path.stem,
            "policy_hook": policy_hook,
            "tool_call": tool_call,
        },
        source_path=source_path,
    )
    ask_preserved = bool(policy_output.get("approval", {}).get("ask_preserved"))
    tool_executed = truthy(policy_output.get("safety", {}).get("tool_executed"))
    passed = policy_output.get("route_status") == "review_only" and ask_preserved and not tool_executed
    return {
        "required": True,
        "passed": passed,
        "route_status": policy_output.get("route_status"),
        "failure_mode": "none" if passed else "approval_path_missing",
        "ask_preserved": ask_preserved,
        "controller_surface": optional_string(policy_output.get("approval", {}).get("controller_surface")) or "none",
        "tool_executed": tool_executed,
        "raw_payload_exported": False,
    }


def mock_e2e_runner_tier_failure_mode(
    *,
    tier_count: int,
    host_native_count: int,
    miscellaneous_count: int,
    external_calls_attempted: bool,
    credentials_required: bool,
    network_required: bool,
    all_tiers_mocked: bool,
    all_tiers_passed: bool,
    tool_boundaries_mocked: bool,
    known_failure_route_passed: bool,
    ci_round_trip_passed: bool,
    approval_boundary_passed: bool,
    agent_config_route_passed: bool,
    agent_config_configured: bool,
    agent_config_parse_error: bool,
    agent_config_tool_count: int,
    agent_config_executable_count: int,
) -> str:
    if tier_count < 1:
        return "no_runner_tiers"
    if external_calls_attempted:
        return "external_provider_required"
    if credentials_required:
        return "credentials_required"
    if network_required:
        return "network_required"
    if host_native_count < 1:
        return "host_native_tier_missing"
    if miscellaneous_count < 1:
        return "miscellaneous_tier_missing"
    if not all_tiers_mocked:
        return "tier_not_mocked"
    if not tool_boundaries_mocked:
        return "unmocked_tool_boundary"
    if not approval_boundary_passed:
        return "approval_path_missing"
    if agent_config_configured and agent_config_parse_error:
        return "agent_config_yaml_parse_failed"
    if agent_config_configured and agent_config_tool_count < 1:
        return "agent_config_no_function_tools"
    if agent_config_configured and agent_config_executable_count < agent_config_tool_count:
        return "agent_config_tool_route_unavailable"
    if not agent_config_route_passed:
        return "agent_config_route_preflight_failed"
    if not all_tiers_passed:
        return "tier_expectation_failed"
    if not known_failure_route_passed:
        return "known_failure_route_mismatch"
    if not ci_round_trip_passed:
        return "ci_round_trip_classification_mismatch"
    return "none"


def evaluate_mock_e2e_known_failure_route(known_failure: dict[str, Any]) -> dict[str, Any]:
    """Check that known e2e failures are routed to the observed failure family."""

    configured = bool(known_failure)
    if not configured:
        return {
            "configured": False,
            "passed": True,
            "mode": "none",
            "observed_signature_matched": True,
            "stale_issue_retained": False,
            "issue_repointed": False,
            "cluster_repointed": False,
            "test_logic_changed": False,
            "raw_failure_text_exported": False,
        }

    observed_signature = optional_string(known_failure.get("observed_signature")) or ""
    expected_signature = optional_string(known_failure.get("expected_signature")) or ""
    previous_issue = optional_string(known_failure.get("previous_issue")) or ""
    issue = optional_string(known_failure.get("issue")) or ""
    previous_cluster = optional_string(known_failure.get("previous_cluster")) or ""
    cluster = optional_string(known_failure.get("cluster")) or ""
    mode = optional_string(known_failure.get("mode")) or "skip"
    test_logic_changed = truthy(known_failure.get("test_logic_changed"))
    observed_signature_matched = bool(expected_signature and expected_signature in observed_signature)
    issue_repointed = bool(previous_issue and issue and previous_issue != issue)
    cluster_repointed = bool(previous_cluster and cluster and previous_cluster != cluster)
    stale_issue_retained = bool(previous_issue and issue == previous_issue)
    passed = (
        observed_signature_matched
        and issue_repointed
        and cluster_repointed
        and mode == "skip"
        and not test_logic_changed
    )

    return {
        "configured": True,
        "passed": passed,
        "mode": mode,
        "observed_signature_matched": observed_signature_matched,
        "stale_issue_retained": stale_issue_retained,
        "issue_repointed": issue_repointed,
        "cluster_repointed": cluster_repointed,
        "test_logic_changed": test_logic_changed,
        "raw_failure_text_exported": False,
    }


def evaluate_mock_e2e_ci_round_trip(ci_round_trip: dict[str, Any]) -> dict[str, Any]:
    """Classify mocked CI round-trip failures without exporting logs or credentials."""

    configured = bool(ci_round_trip)
    if not configured:
        return {
            "configured": False,
            "passed": True,
            "route_status": "not_required",
            "failure_mode": "none",
            "expected_failure_family": "none",
            "observed_failure_family": "none",
            "auth_failure_detected": False,
            "round_trip_hang_detected": False,
            "prompt_observed": False,
            "completion_observed": False,
            "raw_failure_text_exported": False,
            "auth_key_value_exported": False,
        }

    expected_failure_family = normalize_ci_round_trip_failure_family(
        ci_round_trip.get("expected_failure_family") or ci_round_trip.get("expected")
    )
    observed_failure_family = classify_ci_round_trip_failure(ci_round_trip)
    prompt_observed = truthy(ci_round_trip.get("prompt_observed") or ci_round_trip.get("prompt_sent"))
    completion_observed = truthy(ci_round_trip.get("completion_observed") or ci_round_trip.get("response_received"))
    passed = expected_failure_family != "none" and observed_failure_family == expected_failure_family
    return {
        "configured": True,
        "passed": passed,
        "route_status": "passed" if passed else "failed",
        "failure_mode": "none" if passed else "ci_round_trip_classification_mismatch",
        "expected_failure_family": expected_failure_family,
        "observed_failure_family": observed_failure_family,
        "auth_failure_detected": observed_failure_family == "authentication_failure",
        "round_trip_hang_detected": observed_failure_family == "ci_round_trip_hang",
        "prompt_observed": prompt_observed,
        "completion_observed": completion_observed,
        "raw_failure_text_exported": False,
        "auth_key_value_exported": False,
    }


def classify_ci_round_trip_failure(ci_round_trip: dict[str, Any]) -> str:
    failure_text = optional_string(
        ci_round_trip.get("failure_text")
        or ci_round_trip.get("stderr_tail")
        or ci_round_trip.get("stdout_tail")
        or ci_round_trip.get("observed_signature")
    )
    text = (failure_text or "").casefold()
    auth_error = truthy(ci_round_trip.get("auth_error") or ci_round_trip.get("authentication_failed"))
    timed_out = truthy(ci_round_trip.get("timed_out") or ci_round_trip.get("timeout"))
    prompt_observed = truthy(ci_round_trip.get("prompt_observed") or ci_round_trip.get("prompt_sent"))
    completion_observed = truthy(ci_round_trip.get("completion_observed") or ci_round_trip.get("response_received"))

    if auth_error or any(marker in text for marker in CI_ROUND_TRIP_AUTH_FAILURE_MARKERS):
        return "authentication_failure"
    if (timed_out and prompt_observed and not completion_observed) or any(
        marker in text for marker in CI_ROUND_TRIP_HANG_MARKERS
    ):
        return "ci_round_trip_hang"
    return "none"


def normalize_ci_round_trip_failure_family(value: Any) -> str:
    text = (optional_string(value) or "none").strip().casefold().replace("-", "_").replace(" ", "_")
    if text in {"auth", "authentication", "authentication_failure", "credentials", "credential_failure"}:
        return "authentication_failure"
    if text in {"ci_round_trip_hang", "round_trip_hang", "roundtrip_hang", "hang", "timeout"}:
        return "ci_round_trip_hang"
    return "none"


def evaluate_mock_llm_workflow_route(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Evaluate a provider-dependent workflow against deterministic mock LLM responses.

    Optional session and file-tool blocks model e2e smoke paths that otherwise
    require live provider credentials or filesystem side effects. Output keeps
    route-level evidence while hashing session IDs and omitting paths/content.
    """

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    provider = raw_input.get("provider") if isinstance(raw_input.get("provider"), dict) else {}
    mock_llm = raw_input.get("mock_llm") if isinstance(raw_input.get("mock_llm"), dict) else {}
    workflow = raw_input.get("workflow") if isinstance(raw_input.get("workflow"), dict) else {}
    session = raw_input.get("session") if isinstance(raw_input.get("session"), dict) else {}
    interrupt = raw_input.get("interrupt") if isinstance(raw_input.get("interrupt"), dict) else {}
    file_tools = raw_input.get("file_tools") if isinstance(raw_input.get("file_tools"), dict) else {}
    sub_agents = raw_input.get("sub_agents") if isinstance(raw_input.get("sub_agents"), dict) else {}
    native_tool_policy = (
        raw_input.get("native_tool_policy") if isinstance(raw_input.get("native_tool_policy"), dict) else {}
    )
    mock_server_contract = (
        raw_input.get("mock_server_contract") if isinstance(raw_input.get("mock_server_contract"), dict) else {}
    )
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), list) else []
    multimodal_preflight = evaluate_mock_multimodal_preflight(provider, steps)
    response_queues = build_mock_llm_response_queues(mock_llm)

    provider_enabled = truthy(provider.get("enabled"))
    mock_enabled = truthy(mock_llm.get("enabled"))
    external_calls_attempted = provider_enabled and not mock_enabled
    response_count = sum(len(queue) for queue in response_queues.values())
    response_results = (
        build_mock_llm_response_results(steps, response_queues, mock_llm=mock_llm)
        if mock_enabled and multimodal_preflight["ok"]
        else []
    )
    anthropic_messages = evaluate_anthropic_messages_compatibility(
        provider,
        mock_llm,
        response_results=response_results,
    )
    chat_completions = evaluate_chat_completions_mock_contract(
        provider,
        mock_server_contract,
        response_results=response_results,
    )
    enough_responses = len(response_results) >= len(steps)
    expectations_passed = bool(response_results) and all(result["expectation_passed"] for result in response_results)
    session_result = evaluate_mock_session_route(session)
    interrupt_result = evaluate_mock_interrupt_replay(interrupt)
    file_tool_result = evaluate_mock_file_tools_route(file_tools)
    sub_agent_result = evaluate_mock_named_sub_agents_route(sub_agents, response_results=response_results)
    native_policy_result = evaluate_embedded_native_tool_policy(native_tool_policy, source_path=source_path)
    tool_contract = evaluate_mock_tool_call_contract(
        file_tools=file_tools,
        native_tool_policy=native_tool_policy,
        response_results=response_results,
    )
    remaining_response_count = sum(len(queue) for queue in response_queues.values())
    usage = aggregate_mock_llm_usage(response_results)
    failure_mode = mock_llm_workflow_failure_mode(
        step_count=len(steps),
        external_calls_attempted=external_calls_attempted,
        multimodal_preflight_ok=multimodal_preflight["ok"],
        multimodal_failure_mode=optional_string(multimodal_preflight["failure_mode"]) or "multimodal_preflight_failed",
        mock_enabled=mock_enabled,
        enough_responses=enough_responses,
        expectations_passed=expectations_passed,
        anthropic_messages_ok=anthropic_messages["ok"],
        chat_completions_ok=chat_completions["ok"],
        chat_completions_failure_mode=optional_string(chat_completions["failure_mode"])
        or "chat_completions_contract_failed",
        session_passed=session_result["isolation_passed"],
        interrupt_passed=interrupt_result["passed"],
        file_tools_passed=file_tool_result["all_operations_mocked"] and file_tool_result["all_expectations_passed"],
        sub_agents_passed=(
            sub_agent_result["persistence_passed"]
            and not sub_agent_result["queue_desync_detected"]
            and sub_agent_result["resolution_guard_passed"]
        ),
        native_policy_passed=native_policy_result["passive_or_denied"],
        queue_consumed=remaining_response_count == 0,
        tool_contract_passed=tool_contract["all_required_tool_calls_observed"],
    )

    return {
        "schema_version": 1,
        "behavior": "mock_llm_workflow_route",
        "task_id": task_id,
        "route_status": "passed" if failure_mode == "none" else "failed",
        "provider": {
            "name": optional_string(provider.get("name")) or "external-llm",
            "enabled": provider_enabled,
            "disabled_handled": not provider_enabled and mock_enabled,
            "external_calls_attempted": external_calls_attempted,
        },
        "mock_llm": {
            "enabled": mock_enabled,
            "model": optional_string(mock_llm.get("model")) or "mock-llm",
            "call_count": len(response_results),
            "response_count": response_count,
            "remaining_response_count": remaining_response_count,
            "all_responses_consumed": remaining_response_count == 0,
            "queue_keys": sorted(response_queues),
            "exhausted": mock_enabled and not enough_responses,
            "usage": usage,
            "anthropic_messages": anthropic_messages,
            "chat_completions": chat_completions,
        },
        "workflow": {
            "step_count": len(steps),
            "steps_executed": len(response_results),
            "all_expectations_passed": expectations_passed,
            "response_hashes": [result["response_hash"] for result in response_results],
            "response_keys": [result["response_key"] for result in response_results],
            "fallback_count": sum(1 for result in response_results if result["fallback_used"]),
        },
        "multimodal_preflight": multimodal_preflight,
        "session": session_result,
        "interrupt": interrupt_result,
        "file_tools": file_tool_result,
        "sub_agents": sub_agent_result,
        "native_tool_policy": native_policy_result,
        "tool_call_contract": tool_contract,
        "failure_mode": failure_mode,
    }


def evaluate_mock_multimodal_preflight(provider: dict[str, Any], steps: list[Any]) -> dict[str, Any]:
    """Fail before execution when image blocks would be silently dropped or text-flattened."""

    image_block_count = 0
    text_encoded_multimodal_block_count = 0
    malformed_image_block_count = 0
    for step in steps:
        step_data = step if isinstance(step, dict) else {}
        prompt = step_data.get("prompt")
        blocks: list[Any] = prompt if isinstance(prompt, list) else []
        if isinstance(prompt, str) and looks_like_text_encoded_multimodal_blocks(prompt):
            text_encoded_multimodal_block_count += 1
        for block in blocks:
            block_data = block if isinstance(block, dict) else {}
            if str(block_data.get("type") or "") != "input_image":
                continue
            image_block_count += 1
            image_url = optional_string(block_data.get("image_url"))
            if not image_url or not image_url.startswith("data:") or "," not in image_url:
                malformed_image_block_count += 1

    model_input = provider.get("model_input") or provider.get("input")
    model_input_modes = tuple(str(item) for item in model_input) if isinstance(model_input, list) else ()
    declares_image_input = "image" in model_input_modes
    diagnostics: list[str] = []
    if image_block_count and not declares_image_input:
        diagnostics.append("model input capabilities must include image before executing image prompts")
    if text_encoded_multimodal_block_count:
        diagnostics.append("multimodal content blocks must be native blocks, not JSON-encoded text")
    if malformed_image_block_count:
        diagnostics.append("input_image blocks must include a resolved data URI image_url")

    failure_mode = "none"
    if image_block_count and not declares_image_input:
        failure_mode = "missing_model_image_input"
    elif text_encoded_multimodal_block_count:
        failure_mode = "text_encoded_multimodal_blocks"
    elif malformed_image_block_count:
        failure_mode = "malformed_input_image_block"

    return {
        "ok": not diagnostics,
        "failure_mode": failure_mode,
        "diagnostics": diagnostics,
        "image_block_count": image_block_count,
        "text_encoded_multimodal_block_count": text_encoded_multimodal_block_count,
        "malformed_image_block_count": malformed_image_block_count,
        "model_input_modes": list(model_input_modes),
        "model_image_input_declared": declares_image_input,
        "prompt_bodies_exported": False,
    }


def looks_like_text_encoded_multimodal_blocks(value: str) -> bool:
    text = value.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return False
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(decoded, list):
        return False
    return any(isinstance(item, dict) and item.get("type") == "input_image" for item in decoded)


def build_mock_llm_response_queues(mock_llm: dict[str, Any]) -> dict[str, list[Any]]:
    queues: dict[str, list[Any]] = {}
    raw_queues = mock_llm.get("response_queues") if isinstance(mock_llm.get("response_queues"), dict) else {}
    for raw_key, raw_responses in raw_queues.items():
        key = optional_string(raw_key)
        if key and isinstance(raw_responses, list):
            queues[key] = list(raw_responses)

    responses = mock_llm.get("responses") if isinstance(mock_llm.get("responses"), list) else []
    if responses and "default" not in queues:
        queues["default"] = list(responses)
    return queues


def build_mock_llm_response_results(
    steps: list[Any],
    response_queues: dict[str, list[Any]],
    *,
    mock_llm: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        step_data = step if isinstance(step, dict) else {}
        queue_key, fallback_used = resolve_mock_llm_response_key(step_data, response_queues, mock_llm=mock_llm)
        if queue_key is None:
            break
        response = response_queues[queue_key].pop(0)
        response_data = response if isinstance(response, dict) else {}
        content = optional_string(response_data.get("content")) or ""
        expect_contains = optional_string(step_data.get("expect_contains"))
        usage = response_data.get("usage") if isinstance(response_data.get("usage"), dict) else {}
        tool_calls = response_data.get("tool_calls") if isinstance(response_data.get("tool_calls"), list) else []
        request_key = mock_llm_request_key(step_data, mock_llm=mock_llm)
        response_model = optional_string(response_data.get("response_model")) or request_key
        tool_call_names = [
            name
            for name in (
                optional_string(tool_call.get("name")) for tool_call in tool_calls if isinstance(tool_call, dict)
            )
            if name
        ]
        results.append(
            {
                "step_id": optional_string(step_data.get("id")) or f"step-{index + 1}",
                "agent": optional_string(step_data.get("agent")),
                "request_key": request_key,
                "response_key": queue_key,
                "response_model": response_model,
                "response_format": optional_string(response_data.get("response_format")),
                "fallback_used": fallback_used,
                "response_hash": stable_text_hash(content),
                "expectation_passed": expect_contains is None or expect_contains in content,
                "tool_call_count": len(tool_calls),
                "tool_call_names": tool_call_names,
                "input_tokens": optional_int(usage.get("input_tokens") or usage.get("prompt_tokens")) or 0,
                "output_tokens": optional_int(usage.get("output_tokens") or usage.get("completion_tokens")) or 0,
            }
        )
    return results


def resolve_mock_llm_response_key(
    step_data: dict[str, Any],
    response_queues: dict[str, list[Any]],
    *,
    mock_llm: dict[str, Any],
) -> tuple[str | None, bool]:
    request_key = mock_llm_request_key(step_data, mock_llm=mock_llm)
    if request_key in response_queues and response_queues[request_key]:
        return request_key, False
    if "default" in response_queues and response_queues["default"]:
        return "default", request_key != "default"
    return None, False


def mock_llm_request_key(step_data: dict[str, Any], *, mock_llm: dict[str, Any]) -> str:
    return (
        optional_string(step_data.get("model"))
        or optional_string(step_data.get("response_key"))
        or optional_string(mock_llm.get("model"))
        or "default"
    )


def aggregate_mock_llm_usage(response_results: list[dict[str, Any]]) -> dict[str, int]:
    input_tokens = sum(int(result["input_tokens"]) for result in response_results)
    output_tokens = sum(int(result["output_tokens"]) for result in response_results)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "tool_calls": sum(int(result["tool_call_count"]) for result in response_results),
    }


def evaluate_anthropic_messages_compatibility(
    provider: dict[str, Any],
    mock_llm: dict[str, Any],
    *,
    response_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate Anthropic Messages mock protocol shape without exporting bodies."""

    enabled = mock_llm_uses_anthropic_messages(provider, mock_llm)
    if not enabled:
        return {
            "enabled": False,
            "ok": True,
            "endpoint": None,
            "request_count": 0,
            "response_format": None,
            "model_echoed": True,
            "same_keyed_queue_routing": True,
            "text_event_sequence_count": 0,
            "tool_event_sequence_count": 0,
            "diagnostics": [],
        }

    diagnostics: list[str] = []
    missing_request_models = [result["step_id"] for result in response_results if result["request_key"] == "default"]
    if missing_request_models:
        diagnostics.append("Anthropic Messages mock requests must carry an explicit model for keyed queue routing")

    model_mismatches = [
        result["step_id"] for result in response_results if result["response_model"] != result["request_key"]
    ]
    if model_mismatches:
        diagnostics.append("Anthropic Messages mock responses must echo the request model in message_start")

    fallback_count = sum(1 for result in response_results if result["fallback_used"])
    if fallback_count:
        diagnostics.append("Anthropic Messages mock requests must use the same keyed queues as response routes")

    text_sequence_count = sum(1 for result in response_results if int(result["tool_call_count"]) == 0)
    tool_sequence_count = sum(1 for result in response_results if int(result["tool_call_count"]) > 0)
    event_types = [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    tool_event_types = [
        "message_start",
        "content_block_start",
        "input_json_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]

    return {
        "enabled": True,
        "ok": not diagnostics,
        "endpoint": "/v1/messages",
        "request_count": len(response_results),
        "response_format": "anthropic_sse",
        "model_echoed": not model_mismatches,
        "same_keyed_queue_routing": fallback_count == 0,
        "text_event_sequence_count": text_sequence_count,
        "tool_event_sequence_count": tool_sequence_count,
        "event_types": event_types,
        "tool_event_types": tool_event_types if tool_sequence_count else [],
        "diagnostics": diagnostics,
    }


def mock_llm_uses_anthropic_messages(provider: dict[str, Any], mock_llm: dict[str, Any]) -> bool:
    api = optional_string(mock_llm.get("api")) or optional_string(mock_llm.get("protocol"))
    if api in {"anthropic_messages", "messages"}:
        return True
    provider_name = (optional_string(provider.get("name")) or "").lower()
    harness = (optional_string(provider.get("harness")) or "").lower()
    return "claude" in provider_name or "claude" in harness or "anthropic" in provider_name or "anthropic" in harness


def evaluate_chat_completions_mock_contract(
    provider: dict[str, Any],
    contract: dict[str, Any],
    *,
    response_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate OpenAI-compatible chat/completions mock server behavior without bodies."""

    enabled = truthy(contract.get("enabled")) or chat_completions_contract_implied(provider, contract)
    if not enabled:
        return {
            "enabled": False,
            "ok": True,
            "failure_mode": "none",
            "endpoint": None,
            "request_count": 0,
            "streaming_request_count": 0,
            "non_streaming_request_count": 0,
            "json_response_count": 0,
            "sse_response_count": 0,
            "provider_preflight": {
                "ok": True,
                "failure_mode": "none",
                "token_required": False,
                "token_present": False,
                "base_url_present": False,
                "mock_base_url": False,
                "diagnostics": [],
                "secret_values_exported": False,
            },
            "diagnostics": [],
            "request_bodies_exported": False,
            "response_bodies_exported": False,
        }

    endpoint = optional_string(contract.get("endpoint")) or "/v1/chat/completions"
    request_count = len(response_results)
    requests = contract.get("requests") if isinstance(contract.get("requests"), list) else []
    if requests:
        request_count = len(requests)

    stream_flags = chat_completions_stream_flags(contract, request_count=request_count)
    observed_formats = chat_completions_observed_formats(contract, response_results, request_count=request_count)
    expected_formats = ["sse" if stream else "json" for stream in stream_flags]
    format_mismatch_count = sum(
        1 for expected, observed in zip(expected_formats, observed_formats) if expected != observed
    )
    model_echoed = chat_completions_models_echoed(contract, response_results)
    provider_preflight = evaluate_mock_chat_provider_preflight(provider, contract)
    diagnostics = list(provider_preflight["diagnostics"])
    if endpoint != "/v1/chat/completions":
        diagnostics.append("chat/completions mock contract must target /v1/chat/completions")
    if request_count != len(response_results):
        diagnostics.append("chat/completions request count must match consumed mock responses")
    if format_mismatch_count:
        diagnostics.append("chat/completions mock response format must match each stream flag")
    if not model_echoed:
        diagnostics.append("chat/completions mock responses must echo request model choices")

    if not provider_preflight["ok"]:
        failure_mode = str(provider_preflight["failure_mode"])
    elif endpoint != "/v1/chat/completions":
        failure_mode = "chat_completions_endpoint_mismatch"
    elif request_count != len(response_results):
        failure_mode = "chat_completions_request_count_mismatch"
    elif format_mismatch_count:
        failure_mode = "chat_completions_response_format_mismatch"
    elif not model_echoed:
        failure_mode = "chat_completions_model_mismatch"
    else:
        failure_mode = "none"

    return {
        "enabled": True,
        "ok": failure_mode == "none",
        "failure_mode": failure_mode,
        "endpoint": endpoint,
        "request_count": request_count,
        "streaming_request_count": sum(1 for stream in stream_flags if stream),
        "non_streaming_request_count": sum(1 for stream in stream_flags if not stream),
        "json_response_count": sum(1 for value in observed_formats if value == "json"),
        "sse_response_count": sum(1 for value in observed_formats if value == "sse"),
        "provider_preflight": provider_preflight,
        "model_echoed": model_echoed,
        "format_mismatch_count": format_mismatch_count,
        "diagnostics": diagnostics,
        "request_bodies_exported": False,
        "response_bodies_exported": False,
    }


def chat_completions_contract_implied(provider: dict[str, Any], contract: dict[str, Any]) -> bool:
    protocol = optional_string(contract.get("protocol")) or optional_string(provider.get("protocol"))
    api = optional_string(contract.get("api")) or optional_string(provider.get("api"))
    endpoint = optional_string(contract.get("endpoint"))
    provider_name = (optional_string(provider.get("name")) or "").lower()
    harness = (optional_string(provider.get("harness")) or "").lower()
    values = {str(value).lower() for value in (protocol, api, endpoint) if value}
    if values & {"chat_completions", "openai_chat_completions", "/v1/chat/completions"}:
        return True
    return "openai" in provider_name or "openai" in harness


def chat_completions_stream_flags(contract: dict[str, Any], *, request_count: int) -> list[bool]:
    requests = contract.get("requests") if isinstance(contract.get("requests"), list) else []
    flags: list[bool] = []
    for request in requests:
        request_data = request if isinstance(request, dict) else {}
        flags.append(truthy(request_data.get("stream")))
    if flags:
        return flags

    raw_flags = contract.get("stream_flags") if isinstance(contract.get("stream_flags"), list) else []
    flags = [truthy(flag) for flag in raw_flags]
    if flags:
        return flags

    default_stream = truthy(contract.get("stream"))
    return [default_stream for _ in range(request_count)]


def chat_completions_observed_formats(
    contract: dict[str, Any],
    response_results: list[dict[str, Any]],
    *,
    request_count: int,
) -> list[str]:
    raw_formats = (
        contract.get("observed_response_formats") if isinstance(contract.get("observed_response_formats"), list) else []
    )
    formats = [normal_chat_response_format(value) for value in raw_formats]
    if formats:
        return formats

    formats = []
    for result in response_results:
        response_format = normal_chat_response_format(result.get("response_format"))
        formats.append(response_format or "json")
    if formats:
        return formats
    return ["json" for _ in range(request_count)]


def normal_chat_response_format(value: Any) -> str:
    text = (optional_string(value) or "").strip().lower()
    if text in {"json", "application/json", "openai_json"}:
        return "json"
    if text in {"sse", "event_stream", "text/event-stream", "server_sent_events"}:
        return "sse"
    return text


def chat_completions_models_echoed(contract: dict[str, Any], response_results: list[dict[str, Any]]) -> bool:
    if not truthy(contract.get("require_model_echo")):
        return True
    request_models = string_list(contract.get("request_models"))
    if not request_models:
        requests = contract.get("requests") if isinstance(contract.get("requests"), list) else []
        request_models = [
            model
            for model in (optional_string(request.get("model")) for request in requests if isinstance(request, dict))
            if model
        ]
    if not request_models:
        request_models = [str(result["request_key"]) for result in response_results]
    response_models = [str(result["response_model"]) for result in response_results]
    return request_models == response_models


def evaluate_mock_chat_provider_preflight(provider: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    token_required = truthy(provider.get("token_required")) or truthy(contract.get("token_required"))
    token_present = truthy(provider.get("token_present")) or truthy(contract.get("token_present"))
    base_url_present = bool(optional_string(provider.get("base_url")) or optional_string(contract.get("base_url")))
    mock_base_url = truthy(provider.get("mock_base_url")) or truthy(contract.get("mock_base_url"))
    allow_mock_auth = truthy(provider.get("allow_mock_auth")) or truthy(contract.get("allow_mock_auth"))

    diagnostics: list[str] = []
    if token_required and not token_present and not allow_mock_auth:
        diagnostics.append("provider token is required unless mock auth is explicitly allowed")
    if not base_url_present:
        diagnostics.append("mock chat/completions base_url must be configured")
    elif not mock_base_url:
        diagnostics.append("mock chat/completions base_url must point at the local mock server")

    if token_required and not token_present and not allow_mock_auth:
        failure_mode = "provider_token_preflight_failed"
    elif not base_url_present:
        failure_mode = "provider_base_url_preflight_failed"
    elif not mock_base_url:
        failure_mode = "provider_base_url_not_mock"
    else:
        failure_mode = "none"

    return {
        "ok": failure_mode == "none",
        "failure_mode": failure_mode,
        "token_required": token_required,
        "token_present": token_present,
        "base_url_present": base_url_present,
        "mock_base_url": mock_base_url,
        "allow_mock_auth": allow_mock_auth,
        "diagnostics": diagnostics,
        "secret_values_exported": False,
    }


def evaluate_mock_session_route(session: dict[str, Any]) -> dict[str, Any]:
    session_id = optional_string(session.get("id"))
    previous_session_id = optional_string(session.get("previous_id"))
    isolation_required = truthy(session.get("isolation_required")) or bool(session_id or previous_session_id)
    reused_previous_session = bool(session_id and previous_session_id and session_id == previous_session_id)
    isolation_passed = not isolation_required or (bool(session_id) and not reused_previous_session)
    return {
        "declared": bool(session),
        "id_present": bool(session_id),
        "id_hash": stable_text_hash(session_id) if session_id else None,
        "previous_id_hash": stable_text_hash(previous_session_id) if previous_session_id else None,
        "isolation_required": isolation_required,
        "reused_previous_session": reused_previous_session,
        "isolation_passed": isolation_passed,
    }


def evaluate_mock_interrupt_replay(interrupt: dict[str, Any]) -> dict[str, Any]:
    """Validate interrupt rebuild, idle replay, and blocked-drain steering metadata without exporting IDs."""

    previous_session_id = optional_string(interrupt.get("previous_session_id"))
    rebuilt_session_id = optional_string(interrupt.get("rebuilt_session_id"))
    previous_agent_id = optional_string(interrupt.get("previous_agent_id"))
    rebuilt_agent_id = optional_string(interrupt.get("rebuilt_agent_id"))
    previous_conversation_id = optional_string(interrupt.get("previous_conversation_id"))
    rebuilt_conversation_id = optional_string(interrupt.get("rebuilt_conversation_id"))
    pending_idle_message_ids = string_list(interrupt.get("pending_idle_message_ids"))
    replayed_idle_message_ids = string_list(interrupt.get("replayed_idle_message_ids"))
    declared = bool(interrupt)
    required = truthy(interrupt.get("required")) or declared

    session_rebuilt = bool(previous_session_id and rebuilt_session_id and previous_session_id != rebuilt_session_id)
    agent_rebuilt = bool(previous_agent_id and rebuilt_agent_id and previous_agent_id != rebuilt_agent_id)
    conversation_rebuilt = bool(
        previous_conversation_id and rebuilt_conversation_id and previous_conversation_id != rebuilt_conversation_id
    )
    replay_counts_match = count_strings(pending_idle_message_ids) == count_strings(replayed_idle_message_ids)
    lost_idle_message_count = count_missing_strings(pending_idle_message_ids, replayed_idle_message_ids)
    duplicated_idle_message_count = count_missing_strings(replayed_idle_message_ids, pending_idle_message_ids)
    async_drain = evaluate_mock_interrupt_async_drain(interrupt)
    passed = (
        not required
        or session_rebuilt
        and agent_rebuilt
        and conversation_rebuilt
        and replay_counts_match
        and async_drain["passed"]
    )

    return {
        "declared": declared,
        "required": required,
        "session_rebuilt": session_rebuilt,
        "agent_rebuilt": agent_rebuilt,
        "conversation_rebuilt": conversation_rebuilt,
        "pending_idle_message_count": len(pending_idle_message_ids),
        "replayed_idle_message_count": len(replayed_idle_message_ids),
        "idle_replay_counts_match": replay_counts_match,
        "lost_idle_message_count": lost_idle_message_count,
        "duplicated_idle_message_count": duplicated_idle_message_count,
        "previous_session_hash": stable_text_hash(previous_session_id) if previous_session_id else None,
        "rebuilt_session_hash": stable_text_hash(rebuilt_session_id) if rebuilt_session_id else None,
        "previous_agent_hash": stable_text_hash(previous_agent_id) if previous_agent_id else None,
        "rebuilt_agent_hash": stable_text_hash(rebuilt_agent_id) if rebuilt_agent_id else None,
        "previous_conversation_hash": stable_text_hash(previous_conversation_id) if previous_conversation_id else None,
        "rebuilt_conversation_hash": stable_text_hash(rebuilt_conversation_id) if rebuilt_conversation_id else None,
        "pending_idle_message_hashes": [stable_text_hash(message_id) for message_id in pending_idle_message_ids],
        "replayed_idle_message_hashes": [stable_text_hash(message_id) for message_id in replayed_idle_message_ids],
        "async_drain": async_drain,
        "raw_ids_exported": False,
        "passed": passed,
    }


def evaluate_mock_interrupt_async_drain(interrupt: dict[str, Any]) -> dict[str, Any]:
    """Check that steering can break a simulated blocked async drain within a bounded timeout."""

    drain = interrupt.get("async_drain") if isinstance(interrupt.get("async_drain"), dict) else {}
    declared = bool(drain)
    required = truthy(drain.get("required")) or declared
    blocked = truthy(drain.get("blocked"))
    steering_sent = truthy(drain.get("steering_sent"))
    timeout_ms = optional_float(drain.get("timeout_ms")) or 1000.0
    cancelled = truthy(drain.get("cancelled"))
    progressed = truthy(drain.get("progressed"))
    cancelled_after_ms = optional_float(drain.get("cancelled_after_ms"))
    progress_after_ms = optional_float(drain.get("progress_after_ms"))

    cancelled_timely = cancelled and duration_within_timeout(cancelled_after_ms, timeout_ms)
    progressed_timely = progressed and duration_within_timeout(progress_after_ms, timeout_ms)
    broke_drain = cancelled_timely or progressed_timely
    passed = not required or (blocked and steering_sent and broke_drain)

    if not required:
        failure_mode = "none"
    elif not blocked:
        failure_mode = "drain_not_blocked"
    elif not steering_sent:
        failure_mode = "steering_not_sent"
    elif not broke_drain:
        failure_mode = "steering_did_not_break_drain"
    else:
        failure_mode = "none"

    if cancelled_timely:
        outcome = "cancelled"
    elif progressed_timely:
        outcome = "progressed"
    elif required:
        outcome = "blocked"
    else:
        outcome = "not_required"

    return {
        "declared": declared,
        "required": required,
        "blocked": blocked,
        "steering_sent": steering_sent,
        "timeout_ms": timeout_ms,
        "cancelled_timely": cancelled_timely,
        "progressed_timely": progressed_timely,
        "broke_drain": broke_drain,
        "outcome": outcome,
        "failure_mode": failure_mode,
        "passed": passed,
    }


def duration_within_timeout(duration_ms: float | None, timeout_ms: float) -> bool:
    return duration_ms is not None and 0 <= duration_ms <= timeout_ms


def count_strings(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def count_missing_strings(expected: list[str], observed: list[str]) -> int:
    observed_counts = count_strings(observed)
    missing_count = 0
    for value, expected_count in count_strings(expected).items():
        missing_count += max(0, expected_count - observed_counts.get(value, 0))
    return missing_count


def evaluate_mock_file_tools_route(file_tools: dict[str, Any]) -> dict[str, Any]:
    operations = file_tools.get("operations") if isinstance(file_tools.get("operations"), list) else []
    operation_results = [evaluate_mock_file_tool_operation(operation) for operation in operations]
    all_operations_mocked = all(result["mocked"] for result in operation_results)
    all_expectations_passed = all(result["expectation_passed"] for result in operation_results)
    return {
        "declared": bool(file_tools),
        "enabled": truthy(file_tools.get("enabled")) or bool(operation_results),
        "operation_count": len(operation_results),
        "mocked_count": sum(1 for result in operation_results if result["mocked"]),
        "unmocked_external_count": sum(1 for result in operation_results if not result["mocked"]),
        "all_operations_mocked": all_operations_mocked,
        "all_expectations_passed": all_expectations_passed,
        "operations": operation_results,
    }


def evaluate_mock_file_tool_operation(operation: Any) -> dict[str, Any]:
    operation_data = operation if isinstance(operation, dict) else {}
    content = optional_string(operation_data.get("mock_content")) or ""
    expect_contains = optional_string(operation_data.get("expect_content_contains"))
    path = optional_string(operation_data.get("path"))
    return {
        "name": optional_string(operation_data.get("name")) or "file_tool",
        "mocked": truthy(operation_data.get("mocked")),
        "path_hash": stable_text_hash(path) if path else None,
        "content_hash": stable_text_hash(content) if content else None,
        "expectation_passed": expect_contains is None or expect_contains in content,
    }


def evaluate_mock_tool_call_contract(
    *,
    file_tools: dict[str, Any],
    native_tool_policy: dict[str, Any],
    response_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check that mock responses exercised the declared local tool boundary."""

    required_names: list[str] = []
    operations = file_tools.get("operations") if isinstance(file_tools.get("operations"), list) else []
    for operation in operations:
        operation_data = operation if isinstance(operation, dict) else {}
        name = optional_string(operation_data.get("name"))
        if name:
            required_names.append(name)

    tool_call = native_tool_policy.get("tool_call") if isinstance(native_tool_policy.get("tool_call"), dict) else {}
    native_name = optional_string(tool_call.get("name"))
    if native_name:
        required_names.append(native_name)

    observed_names = [
        name
        for result in response_results
        for name in result.get("tool_call_names", [])
        if isinstance(name, str) and name
    ]
    remaining_observed = list(observed_names)
    matched_count = 0
    for name in required_names:
        if name not in remaining_observed:
            continue
        matched_count += 1
        remaining_observed.remove(name)

    return {
        "declared": bool(required_names),
        "required_tool_call_count": len(required_names),
        "observed_tool_call_count": len(observed_names),
        "matched_required_tool_call_count": matched_count,
        "all_required_tool_calls_observed": matched_count == len(required_names),
        "required_tool_call_name_hashes": [stable_text_hash(name) for name in required_names],
        "observed_tool_call_name_hashes": [stable_text_hash(name) for name in observed_names],
        "raw_tool_arguments_exported": False,
    }


def evaluate_mock_named_sub_agents_route(
    sub_agents: dict[str, Any],
    *,
    response_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check named sub-agent mock routing without recording names or message bodies."""

    agents = sub_agents.get("agents") if isinstance(sub_agents.get("agents"), list) else []
    agent_results = [
        evaluate_mock_named_sub_agent(
            agent,
            response_results=response_results,
            parent_name=optional_string(sub_agents.get("parent_name")),
        )
        for agent in agents
        if isinstance(agent, dict)
    ]
    declared = bool(agent_results)
    persistence_passed = all(result["persistence_passed"] for result in agent_results)
    queue_desync_detected = any(result["queue_desync_detected"] for result in agent_results)
    resolution_guard_passed = all(result["resolution"]["guard_passed"] for result in agent_results)
    return {
        "declared": declared,
        "agent_count": len(agent_results),
        "agent_name_hashes": [result["name_hash"] for result in agent_results],
        "all_expected_agents_observed": all(result["turn_count"] > 0 for result in agent_results),
        "persistence_passed": persistence_passed,
        "queue_desync_detected": queue_desync_detected,
        "resolution_guard_passed": resolution_guard_passed,
        "shared_model_key": truthy(sub_agents.get("shared_model_key")),
        "raw_names_exported": False,
        "raw_session_ids_exported": False,
        "agents": agent_results,
    }


def evaluate_mock_named_sub_agent(
    agent: dict[str, Any],
    *,
    response_results: list[dict[str, Any]],
    parent_name: str | None = None,
) -> dict[str, Any]:
    name = optional_string(agent.get("name")) or "named-sub-agent"
    expected_response_key = optional_string(agent.get("expected_response_key"))
    turn_session_ids = string_list(agent.get("turn_session_ids"))
    persistence_required = truthy(agent.get("persistence_required")) or len(turn_session_ids) > 1
    observed_turns = [result for result in response_results if result.get("agent") == name]
    response_keys = [str(result["response_key"]) for result in observed_turns]
    fallback_count = sum(1 for result in observed_turns if result["fallback_used"])
    expected_queue_mismatches = (
        sum(1 for key in response_keys if key != expected_response_key) if expected_response_key else fallback_count
    )
    session_hashes = [stable_text_hash(session_id) for session_id in turn_session_ids]
    unique_session_hash_count = len(set(session_hashes))
    persistence_passed = (
        not persistence_required
        or bool(session_hashes)
        and unique_session_hash_count == 1
        and len(observed_turns) >= len(session_hashes)
    )
    queue_desync_detected = fallback_count > 0 or expected_queue_mismatches > 0
    resolution = evaluate_mock_named_sub_agent_resolution(agent, name=name, parent_name=parent_name)
    return {
        "name_hash": stable_text_hash(name),
        "turn_count": len(observed_turns),
        "expected_response_key_hash": stable_text_hash(expected_response_key) if expected_response_key else None,
        "response_key_hashes": [stable_text_hash(key) for key in response_keys],
        "fallback_count": fallback_count,
        "expected_queue_mismatches": expected_queue_mismatches,
        "queue_desync_detected": queue_desync_detected,
        "persistence_required": persistence_required,
        "turn_session_hashes": session_hashes,
        "unique_session_hash_count": unique_session_hash_count,
        "persistence_passed": persistence_passed,
        "resolution": resolution,
    }


def evaluate_mock_named_sub_agent_resolution(
    agent: dict[str, Any],
    *,
    name: str,
    parent_name: str | None,
) -> dict[str, Any]:
    """Model child-agent resolver misses without exporting raw agent names."""

    resolution = agent.get("resolution") if isinstance(agent.get("resolution"), dict) else {}
    persisted_agent_names = set(string_list(resolution.get("persisted_agent_names")))
    resolved_agent_name = optional_string(resolution.get("resolved_agent_name"))
    resolver_miss = truthy(resolution.get("resolver_miss")) or (
        bool(persisted_agent_names) and name not in persisted_agent_names
    )
    reconstructed_on_miss = truthy(resolution.get("reconstructed_on_miss"))
    blocked_before_spawn = truthy(resolution.get("blocked_before_spawn"))
    fallback_to_parent = bool(
        resolver_miss and parent_name and resolved_agent_name == parent_name and name != parent_name
    )
    fail_closed_required = resolver_miss and not reconstructed_on_miss
    fail_closed_applied = fail_closed_required and blocked_before_spawn and not fallback_to_parent
    guard_passed = (not resolver_miss) or reconstructed_on_miss or fail_closed_applied

    if not resolver_miss:
        failure_mode = "none"
        decision = "resolved_child_spec"
    elif reconstructed_on_miss:
        failure_mode = "none"
        decision = "reconstructed_child_spec"
    elif fail_closed_applied:
        failure_mode = "none"
        decision = "blocked_before_spawn"
    elif fallback_to_parent:
        failure_mode = "parent_clone_fallback"
        decision = "blocked_required"
    else:
        failure_mode = "resolver_miss_not_blocked"
        decision = "blocked_required"

    return {
        "declared": bool(resolution),
        "resolver_miss": resolver_miss,
        "reconstructed_on_miss": reconstructed_on_miss,
        "blocked_before_spawn": blocked_before_spawn,
        "fallback_to_parent_detected": fallback_to_parent,
        "fail_closed_required": fail_closed_required,
        "fail_closed_applied": fail_closed_applied,
        "guard_passed": guard_passed,
        "decision": decision,
        "failure_mode": failure_mode,
        "raw_agent_names_exported": False,
        "agent_name_hash": stable_text_hash(name),
        "parent_name_hash": stable_text_hash(parent_name) if parent_name else None,
        "resolved_agent_name_hash": stable_text_hash(resolved_agent_name) if resolved_agent_name else None,
    }


def evaluate_embedded_native_tool_policy(native_tool_policy: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    if not native_tool_policy:
        return {
            "declared": False,
            "route_status": "not_configured",
            "failure_mode": "none",
            "passive_or_denied": True,
            "tool_executed": False,
            "arguments_exported": False,
            "approval_output_poll": evaluate_approval_output_poll({}),
        }

    policy_result = evaluate_native_tool_call_policy(native_tool_policy, source_path=source_path)
    output_poll = evaluate_approval_output_poll(
        native_tool_policy.get("approval_output_poll")
        if isinstance(native_tool_policy.get("approval_output_poll"), dict)
        else {}
    )
    decision = str(policy_result["permission"]["decision"])
    tool_executed = bool(policy_result["safety"]["tool_executed"])
    approval_expected = truthy(native_tool_policy.get("approval_expected"))
    approval_observed = decision == "review_required"
    approval_contract_passed = not approval_expected or approval_observed
    failure_mode = str(policy_result["failure_mode"])
    if not approval_contract_passed:
        failure_mode = "approval_path_missing"
    elif not output_poll["passed"]:
        failure_mode = str(output_poll["failure_mode"])
    return {
        "declared": True,
        "route_status": policy_result["route_status"],
        "failure_mode": failure_mode,
        "permission_decision": decision,
        "permission_reason": policy_result["permission"]["reason"],
        "approval_required": decision == "review_required",
        "approval_path": {
            "expected": approval_expected,
            "declared": approval_observed,
            "route_status": "review_only" if decision == "review_required" else "not_required",
            "passive": decision == "review_required" and not tool_executed,
            "tool_executed": tool_executed,
            "arguments_exported": False,
        },
        "approval_output_poll": output_poll,
        "fail_closed_applied": policy_result["policy_hook"]["fail_closed_applied"],
        "passive_or_denied": approval_contract_passed
        and output_poll["passed"]
        and decision in {"deny", "review_required", "no_opinion"}
        and not tool_executed,
        "tool_executed": tool_executed,
        "arguments_exported": False,
    }


def evaluate_approval_output_poll(poll: dict[str, Any]) -> dict[str, Any]:
    """Replay bounded approval-output polling without exporting transcript text."""

    required = truthy(poll.get("required"))
    if not required:
        return {
            "required": False,
            "passed": True,
            "failure_mode": "none",
            "expected_output_observed": False,
            "sample_count": 0,
            "poll_attempt_count": 0,
            "matched_sample_index": None,
            "timeout_ms": 0,
            "interval_ms": 0,
            "bounded": True,
            "raw_output_exported": False,
            "sample_hashes": [],
        }

    expected_contains = optional_string(poll.get("expected_contains")) or ""
    samples = poll.get("samples") if isinstance(poll.get("samples"), list) else []
    timeout_ms = max(0, optional_int(poll.get("timeout_ms")) or 0)
    interval_ms = max(1, optional_int(poll.get("interval_ms")) or 1)
    max_attempts = max(1, (timeout_ms // interval_ms) + 1) if timeout_ms else len(samples)
    poll_attempt_count = min(len(samples), max_attempts)
    matched_sample_index: int | None = None
    sample_hashes: list[str] = []

    for index, sample in enumerate(samples[:poll_attempt_count]):
        sample_data = sample if isinstance(sample, dict) else {}
        output = (
            optional_string(sample_data.get("output") or sample_data.get("text") or sample_data.get("content")) or ""
        )
        sample_hashes.append(stable_text_hash(output))
        if expected_contains and expected_contains in output:
            matched_sample_index = index
            break

    expected_output_observed = matched_sample_index is not None
    if not expected_contains:
        failure_mode = "approval_output_expectation_missing"
    elif expected_output_observed:
        failure_mode = "none"
    else:
        failure_mode = "approval_output_poll_timeout"

    return {
        "required": True,
        "passed": failure_mode == "none",
        "failure_mode": failure_mode,
        "expected_output_observed": expected_output_observed,
        "sample_count": len(samples),
        "poll_attempt_count": poll_attempt_count,
        "matched_sample_index": matched_sample_index,
        "timeout_ms": timeout_ms,
        "interval_ms": interval_ms,
        "bounded": timeout_ms > 0 and interval_ms > 0,
        "raw_output_exported": False,
        "sample_hashes": sample_hashes,
    }


def mock_llm_workflow_failure_mode(
    *,
    step_count: int,
    external_calls_attempted: bool,
    multimodal_preflight_ok: bool,
    multimodal_failure_mode: str,
    mock_enabled: bool,
    enough_responses: bool,
    expectations_passed: bool,
    anthropic_messages_ok: bool,
    chat_completions_ok: bool,
    chat_completions_failure_mode: str,
    session_passed: bool,
    interrupt_passed: bool,
    file_tools_passed: bool,
    sub_agents_passed: bool,
    native_policy_passed: bool,
    queue_consumed: bool,
    tool_contract_passed: bool,
) -> str:
    if step_count < 1:
        return "no_workflow_steps"
    if external_calls_attempted:
        return "external_provider_required"
    if not multimodal_preflight_ok:
        return multimodal_failure_mode
    if not mock_enabled:
        return "mock_llm_disabled"
    if not enough_responses:
        return "mock_llm_exhausted"
    if not anthropic_messages_ok:
        return "anthropic_messages_incompatible"
    if not chat_completions_ok:
        return chat_completions_failure_mode
    if not expectations_passed:
        return "expectation_failed"
    if not queue_consumed:
        return "mock_llm_queue_not_consumed"
    if not session_passed:
        return "session_isolation_failed"
    if not interrupt_passed:
        return "interrupt_replay_failed"
    if not file_tools_passed:
        return "file_tool_mock_failed"
    if not sub_agents_passed:
        return "sub_agent_mock_route_failed"
    if not native_policy_passed:
        return "native_policy_route_failed"
    if not tool_contract_passed:
        return "tool_call_contract_failed"
    return "none"


def evaluate_native_tool_call_policy(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Model native policy-hook behavior without executing or exporting tool arguments."""

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    policy_hook = raw_input.get("policy_hook") if isinstance(raw_input.get("policy_hook"), dict) else {}
    tool_call = raw_input.get("tool_call") if isinstance(raw_input.get("tool_call"), dict) else {}
    session_id = optional_string(policy_hook.get("session_id"))
    server_url_configured = truthy(policy_hook.get("server_url_configured")) or bool(
        optional_string(policy_hook.get("ap_server_url"))
    )
    governed = truthy(policy_hook.get("governed")) or bool(session_id and server_url_configured)
    event_phase = optional_string(policy_hook.get("event_phase")) or "PreToolUse"
    is_tool_call_phase = event_phase in NATIVE_TOOL_CALL_PHASES
    event_phase_kind = native_policy_event_phase_kind(event_phase)
    can_surface_interactive_ask = governed and event_phase_kind in NATIVE_INTERACTIVE_ASK_PHASE_KINDS
    hook_failure_mode = optional_string(policy_hook.get("failure_mode")) or "none"
    verdict = policy_hook.get("verdict") if isinstance(policy_hook.get("verdict"), dict) else {}
    approval_resolution = optional_string(policy_hook.get("approval_resolution")) or optional_string(
        verdict.get("approval_resolution")
    )
    verdict_received = bool(verdict) and hook_failure_mode == "none"
    unavailable = governed and not verdict_received and hook_failure_mode in NATIVE_POLICY_HOOK_UNAVAILABLE_FAILURES
    ask_timeout = governed and not verdict_received and hook_failure_mode in NATIVE_POLICY_HOOK_ASK_TIMEOUT_FAILURES
    malformed_verdict = governed and not verdict_received and hook_failure_mode == "malformed_verdict"
    ask_verdict = verdict_received and truthy(verdict.get("review_required"))

    if governed and is_tool_call_phase and ask_timeout:
        decision = "review_required"
        decision_reason = f"policy_hook_ask_timeout:{hook_failure_mode}"
        route_status = "review_only"
        failure_mode = "policy_ask_timeout"
        fail_closed_applied = False
    elif governed and is_tool_call_phase and (unavailable or malformed_verdict):
        decision = "deny"
        decision_reason = f"policy_hook_fail_closed:{hook_failure_mode}"
        route_status = "denied"
        failure_mode = "policy_hook_unavailable"
        fail_closed_applied = True
    elif verdict_received and verdict.get("allowed") is False:
        decision = "deny"
        decision_reason = f"policy_denied:{optional_string(verdict.get('reason')) or 'unspecified'}"
        route_status = "denied"
        failure_mode = "policy_denied"
        fail_closed_applied = False
    elif ask_verdict and approval_resolution == "approved":
        decision = "allow"
        decision_reason = f"policy_approved:{optional_string(verdict.get('reason')) or 'unspecified'}"
        route_status = "passed"
        failure_mode = "none"
        fail_closed_applied = False
    elif ask_verdict and approval_resolution == "denied":
        decision = "deny"
        decision_reason = f"policy_approval_denied:{optional_string(verdict.get('reason')) or 'unspecified'}"
        route_status = "denied"
        failure_mode = "policy_approval_denied"
        fail_closed_applied = False
    elif ask_verdict and can_surface_interactive_ask:
        decision = "review_required"
        decision_reason = f"policy_review_required:{optional_string(verdict.get('reason')) or 'unspecified'}"
        route_status = "review_only"
        failure_mode = "policy_review_required"
        fail_closed_applied = False
    elif ask_verdict:
        decision = "deny"
        decision_reason = f"policy_ask_not_supported:{optional_string(verdict.get('reason')) or 'unspecified'}"
        route_status = "denied"
        failure_mode = "policy_ask_not_supported"
        fail_closed_applied = True
    elif verdict_received and verdict.get("allowed") is True:
        decision = "allow"
        decision_reason = "policy_allowed"
        route_status = "passed"
        failure_mode = "none"
        fail_closed_applied = False
    else:
        decision = "no_opinion"
        decision_reason = native_policy_no_opinion_reason(
            governed=governed,
            is_tool_call_phase=is_tool_call_phase,
            hook_failure_mode=hook_failure_mode,
        )
        route_status = "passed"
        failure_mode = "none"
        fail_closed_applied = False

    tool_name = optional_string(tool_call.get("name")) or "unknown_tool"
    return {
        "schema_version": 1,
        "behavior": "native_tool_call_policy",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "policy_hook": {
            "governed": governed,
            "session_id_present": bool(session_id),
            "session_id_hash": stable_text_hash(session_id) if session_id else None,
            "server_url_configured": server_url_configured,
            "event_phase": event_phase,
            "event_phase_kind": event_phase_kind,
            "is_tool_call_phase": is_tool_call_phase,
            "interactive_ask_supported": can_surface_interactive_ask,
            "failure_mode": hook_failure_mode,
            "verdict_received": verdict_received,
            "fail_closed_applied": fail_closed_applied,
            "raw_payload_exported": False,
        },
        "permission": {
            "decision": decision,
            "reason": decision_reason,
            "arguments_exported": False,
        },
        "approval": {
            "ask_preserved": ask_verdict and decision == "review_required",
            "controller_surface": "interactive_policy_ask" if ask_verdict and decision == "review_required" else "none",
            "resolution": approval_resolution or "pending" if ask_verdict else "not_requested",
            "resolved_by_explicit_verdict": ask_verdict and approval_resolution in {"approved", "denied"},
            "raw_payload_exported": False,
        },
        "tool_call": {
            "name": tool_name,
            "name_hash": stable_text_hash(tool_name),
            "transport": optional_string(tool_call.get("transport")) or "native",
            "arguments_exported": False,
        },
        "safety": {
            "offensive_behavior_local_execution": False,
            "tool_executed": decision == "allow",
        },
    }


def native_policy_event_phase_kind(event_phase: str) -> str:
    return NATIVE_POLICY_PHASE_KIND_ALIASES.get(event_phase, "OTHER")


def native_policy_no_opinion_reason(*, governed: bool, is_tool_call_phase: bool, hook_failure_mode: str) -> str:
    if not governed:
        return "policy_hook_not_governed"
    if not is_tool_call_phase:
        return "policy_hook_advisory_phase_fail_open"
    if hook_failure_mode == "none":
        return "policy_hook_no_verdict"
    return f"policy_hook_fail_open:{hook_failure_mode}"


def evaluate_provider_runtime_preflight(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Model provider startup checks before a sandbox-incompatible SDK harness runs.

    This is a metadata-only fixture path for cases where a provider's supervisor
    process may need to run degraded while file and shell tools remain governed
    by the outer harness sandbox. It never records environment values.
    """

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    provider = raw_input.get("provider") if isinstance(raw_input.get("provider"), dict) else {}
    sandbox = raw_input.get("sandbox") if isinstance(raw_input.get("sandbox"), dict) else {}
    runtime = raw_input.get("runtime") if isinstance(raw_input.get("runtime"), dict) else {}
    runner_env = raw_input.get("runner_env") if isinstance(raw_input.get("runner_env"), dict) else {}
    mock_llm = raw_input.get("mock_llm") if isinstance(raw_input.get("mock_llm"), dict) else {}
    browser_preflight = evaluate_provider_browser_preflight(raw_input, provider=provider)
    prompt_preflight = evaluate_provider_prompt_scan_preflight(raw_input, provider=provider)
    model_command_preflight = evaluate_provider_model_command_preflight(provider=provider, runtime=runtime)
    review_model_preflight = evaluate_provider_review_model_preflight(provider=provider, runtime=runtime)
    usage_limit_preflight = evaluate_provider_usage_limit_preflight(provider=provider, runtime=runtime)
    install_linkage_preflight = evaluate_provider_install_linkage_preflight(provider=provider, runtime=runtime)

    provider_name = optional_string(provider.get("name")) or "external-sdk-provider"
    harness = optional_string(provider.get("harness")) or provider_name
    platform_system = (optional_string(runtime.get("platform")) or "").lower()
    cli_path = optional_string(runtime.get("cli_path")) or ""
    cli_resolved_in_runner = truthy(runtime.get("cli_resolved_in_runner"))
    launch_transport = (optional_string(runtime.get("launch_transport")) or "").lower()
    terminal_integration = normalize_terminal_integration(runtime.get("terminal_integration"))
    sandbox_active = truthy(sandbox.get("active"))
    install_tree_readable = truthy(runtime.get("install_tree_readable"))
    auto_degrade = truthy(provider.get("degrade_on_incompatible_sandbox"))

    override_flag = optional_string(provider.get("sandbox_override_flag")) or "NO_SANDBOX"
    parent_env_keys = string_list(runner_env.get("parent_env_keys"))
    allowlist = string_list(runner_env.get("allowlist"))
    passthrough = string_list(runner_env.get("passthrough"))
    harness_env_keys = sorted(set(allowlist) | set(passthrough))
    override_requested = override_flag in parent_env_keys
    override_propagated = override_requested and override_flag in harness_env_keys
    auth_env_key = optional_string(provider.get("auth_env_key"))
    required_env_keys = sorted(
        set(string_list(provider.get("required_env_keys")) + ([auth_env_key] if auth_env_key else []))
    )
    required_env_scope = optional_string(provider.get("required_env_scope")) or "harness"
    worker_tools = string_list(provider.get("worker_tools"))
    expected_worker_tool = optional_string(provider.get("worker_tool_name")) or default_worker_tool_name(harness)
    worker_tool_available = expected_worker_tool in worker_tools or any(
        tool.endswith("_worker") for tool in worker_tools
    )
    os_env_inherit_to_worker = truthy(runner_env.get("os_env_inherit_to_worker"))
    worker_env_inherit_skipped = bool(
        os_env_inherit_to_worker and required_env_scope == "worker" and not worker_tool_available
    )
    missing_parent_env_keys = sorted(set(required_env_keys) - set(parent_env_keys))
    missing_harness_env_keys = (
        [] if worker_env_inherit_skipped else sorted(set(required_env_keys) - set(harness_env_keys))
    )
    required_env_ready = not missing_parent_env_keys and not missing_harness_env_keys
    mock_auth_placeholder = truthy(mock_llm.get("auth_placeholder")) or truthy(mock_llm.get("mock_auth_placeholder"))
    mock_enabled = truthy(mock_llm.get("enabled"))
    is_openai_agents = (
        "openai" in f"{provider_name} {harness}".lower() and "agent" in f"{provider_name} {harness}".lower()
    )
    mock_auth_substitution = bool(required_env_keys and mock_enabled and mock_auth_placeholder)
    env_preflight_failed = bool(required_env_keys and not required_env_ready and not mock_auth_substitution)

    incompatible_sandbox = (
        sandbox_active
        and platform_system == "darwin"
        and "claude" in provider_name.lower()
        and cli_path.startswith("~/")
        and not install_tree_readable
    )
    native_terminal_timeout_risk = (
        platform_system == "darwin"
        and "claude" in provider_name.lower()
        and cli_path.startswith("~/.local/bin/")
        and launch_transport == "tmux"
        and terminal_integration == "iterm2"
        and not cli_resolved_in_runner
    )
    degraded = incompatible_sandbox and (override_propagated or auto_degrade)
    blocked = (
        (incompatible_sandbox and not degraded)
        or native_terminal_timeout_risk
        or not review_model_preflight["ok"]
        or not usage_limit_preflight["ok"]
        or not install_linkage_preflight["ok"]
        or not model_command_preflight["ok"]
        or env_preflight_failed
        or not prompt_preflight["prompt_scan"]["prompt_detected"]
        or not browser_preflight["url_safety"]["ok"]
    )
    runner_invoked = not blocked
    diagnostics = build_provider_runtime_diagnostics(
        incompatible_sandbox=incompatible_sandbox,
        native_terminal_timeout_risk=native_terminal_timeout_risk,
        degraded=degraded,
        blocked=incompatible_sandbox and not degraded,
        override_flag=override_flag,
        override_requested=override_requested,
        override_propagated=override_propagated,
        auto_degrade=auto_degrade,
    )
    diagnostics.extend(browser_preflight["preflight"]["diagnostics"])
    diagnostics.extend(prompt_preflight["preflight"]["diagnostics"])
    diagnostics.extend(review_model_preflight["diagnostics"])
    diagnostics.extend(usage_limit_preflight["diagnostics"])
    diagnostics.extend(install_linkage_preflight["diagnostics"])
    diagnostics.extend(model_command_preflight["diagnostics"])
    diagnostics.extend(
        build_provider_env_diagnostics(
            required_env_key_count=len(required_env_keys),
            missing_parent_env_key_count=len(missing_parent_env_keys),
            missing_harness_env_key_count=len(missing_harness_env_keys),
            worker_env_inherit_skipped=worker_env_inherit_skipped,
            mock_auth_substitution=mock_auth_substitution,
            env_preflight_failed=env_preflight_failed,
        )
    )

    if blocked:
        route_status = "blocked"
        failure_mode = (
            review_model_preflight["failure_mode"]
            if not review_model_preflight["ok"]
            else usage_limit_preflight["failure_mode"]
            if not usage_limit_preflight["ok"]
            else install_linkage_preflight["failure_mode"]
            if not install_linkage_preflight["ok"]
            else model_command_preflight["failure_mode"]
            if not model_command_preflight["ok"]
            else "provider_env_missing"
            if env_preflight_failed
            else "url_safety_preflight_failed"
            if not browser_preflight["url_safety"]["ok"]
            else "prompt_scan_timeout_risk"
            if not prompt_preflight["prompt_scan"]["prompt_detected"]
            else "native_terminal_timeout_risk"
            if native_terminal_timeout_risk
            else "sandbox_runtime_preflight_failed"
        )
    elif degraded or mock_auth_substitution or browser_preflight["browser_tooling"]["configure_checks_skipped"]:
        route_status = "degraded"
        failure_mode = "none"
    else:
        route_status = "passed"
        failure_mode = "none"

    output = {
        "schema_version": 1,
        "behavior": "provider_runtime_preflight",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "provider": {
            "name": provider_name,
            "harness": harness,
            "sandbox_override_flag": override_flag,
            "degrade_on_incompatible_sandbox": auto_degrade,
            "required_env_key_count": len(required_env_keys),
            "required_env_scope": required_env_scope,
            "required_env_key_names_recorded": True,
            "expected_worker_tool": expected_worker_tool,
            "worker_tool_count": len(worker_tools),
            "worker_tool_available": worker_tool_available,
            "worker_tool_names_recorded": True,
        },
        "sandbox": {
            "active": sandbox_active,
            "type": optional_string(sandbox.get("type")) or "unknown",
            "incompatible_with_provider_runtime": incompatible_sandbox,
        },
        "runner_env": {
            "override_requested_in_parent": override_requested,
            "override_propagated_to_harness": override_propagated,
            "allowlist_count": len(allowlist),
            "passthrough_count": len(passthrough),
            "required_env_ready": required_env_ready,
            "missing_parent_env_key_count": len(missing_parent_env_keys),
            "missing_harness_env_key_count": len(missing_harness_env_keys),
            "os_env_inherit_to_worker": os_env_inherit_to_worker,
            "worker_env_inherit_skipped": worker_env_inherit_skipped,
            "env_values_recorded": False,
        },
        "provider_auth": {
            "openai_agents_key_relevant": is_openai_agents,
            "auth_env_key_configured": bool(auth_env_key),
            "auth_env_key_present_in_parent": bool(auth_env_key and auth_env_key in parent_env_keys),
            "auth_env_key_propagated_to_harness": bool(auth_env_key and auth_env_key in harness_env_keys),
            "auth_env_key_propagated_to_worker": bool(
                auth_env_key and auth_env_key in harness_env_keys and worker_tool_available
            ),
            "mock_auth_placeholder_used": mock_auth_substitution,
            "real_key_required": bool(required_env_keys and not mock_auth_substitution),
            "key_value_recorded": False,
        },
        "runtime": {
            "platform": platform_system or "unknown",
            "cli_path_recorded": False,
            "cli_resolved_in_runner": cli_resolved_in_runner,
            "launch_transport": launch_transport or "unknown",
            "terminal_integration": terminal_integration,
            "native_terminal_timeout_risk": native_terminal_timeout_risk,
            "install_tree_readable": install_tree_readable,
            "supervisor_unwrapped": degraded,
            "native_file_shell_tools_disabled": degraded,
            "runner_invoked": runner_invoked,
        },
        "preflight": {
            "ok": not blocked,
            "degraded": degraded
            or mock_auth_substitution
            or browser_preflight["browser_tooling"]["configure_checks_skipped"],
            "blocked_before_launch": blocked,
            "diagnostics": diagnostics,
            "diagnostic_count": len(diagnostics),
        },
        "browser_tooling": browser_preflight["browser_tooling"],
        "url_safety": browser_preflight["url_safety"],
        "prompt_scan": prompt_preflight["prompt_scan"],
        "review_model": review_model_preflight,
        "usage_limit": usage_limit_preflight,
        "install_linkage": install_linkage_preflight,
        "model_command": model_command_preflight,
    }
    recovery_hints = provider_runtime_recovery_hints_for_preflight(output)
    output["recovery_hints"] = recovery_hints
    output["operator_recovery_plan"] = provider_runtime_operator_recovery_plan(
        route_status=route_status,
        failure_mode=failure_mode,
        preflight_count=1,
        status_counts={
            "passed": int(route_status == "passed"),
            "degraded": int(route_status == "degraded"),
            "blocked": int(route_status == "blocked"),
        },
        recovery_hints=recovery_hints,
    )
    output["supervisor_replay"] = provider_runtime_preflight_supervisor_replay(
        output,
        recovery_hints=recovery_hints,
    )
    return output


def evaluate_provider_install_linkage_preflight(
    *,
    provider: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Detect native library linkage problems before provider runtime launch.

    The check is metadata-only: paths and install names are hashed or counted so
    Homebrew/macOS diagnostics can be replayed without exporting local paths.
    """

    raw_linkage = provider.get("install_linkage", runtime.get("install_linkage"))
    linkage = raw_linkage if isinstance(raw_linkage, dict) else {}
    required = (
        truthy(provider.get("install_linkage_preflight_required"))
        or truthy(runtime.get("install_linkage_preflight_required"))
        or bool(linkage)
    )
    package_manager = (optional_string(linkage.get("package_manager") or runtime.get("package_manager")) or "").lower()
    platform = (optional_string(linkage.get("platform") or runtime.get("platform")) or "").lower()
    architecture = (
        optional_string(linkage.get("architecture") or runtime.get("architecture") or runtime.get("machine")) or ""
    ).lower()
    homebrew_prefix = optional_string(linkage.get("homebrew_prefix") or runtime.get("homebrew_prefix"))
    apple_silicon_homebrew = (
        platform == "darwin"
        and architecture in {"arm64", "aarch64", "apple_silicon", "apple-silicon"}
        and package_manager in {"brew", "homebrew"}
    )
    raw_records = linkage.get("libraries") or linkage.get("dynamic_libraries") or linkage.get("dylibs")
    library_records = [item for item in raw_records if isinstance(item, dict)] if isinstance(raw_records, list) else []
    records = [normalize_install_linkage_record(item) for item in library_records]
    unresolved_records = [record for record in records if record["unresolved_rpath"]]
    relink_failure_records = [record for record in records if record["relink_failed"] or record["headerpad_failure"]]
    fragile = apple_silicon_homebrew and bool(unresolved_records or relink_failure_records)

    diagnostics: list[str] = []
    if fragile:
        diagnostics.append(
            "Apple Silicon Homebrew install linkage has unresolved rpath or relink failures; block provider launch until relinked or worked around"
        )

    return {
        "required": required,
        "observed": bool(linkage),
        "ok": not fragile,
        "failure_mode": "provider_install_linkage_unresolved" if fragile else "none",
        "package_manager": package_manager or "unknown",
        "platform": platform or "unknown",
        "architecture": architecture or "unknown",
        "apple_silicon_homebrew": apple_silicon_homebrew,
        "homebrew_prefix_hash": stable_text_hash(homebrew_prefix) if homebrew_prefix else None,
        "homebrew_prefix_exported": False,
        "library_count": len(records),
        "unresolved_rpath_count": len(unresolved_records),
        "relink_failure_count": len(relink_failure_records),
        "records": records,
        "raw_paths_exported": False,
        "raw_install_names_exported": False,
        "diagnostics": diagnostics,
    }


def normalize_install_linkage_record(value: dict[str, Any]) -> dict[str, Any]:
    library_name = optional_string(value.get("name") or value.get("library") or value.get("module")) or "unknown"
    path = optional_string(value.get("path") or value.get("file") or value.get("module_path"))
    install_name = optional_string(value.get("install_name") or value.get("dylib_id") or value.get("load_command"))
    relink_error = optional_string(value.get("relink_error") or value.get("error") or value.get("linkage_error"))
    unresolved_rpath = truthy(value.get("unresolved_rpath")) or bool(
        install_name and install_name.strip().startswith("@rpath/")
    )
    headerpad_failure = truthy(value.get("headerpad_failure")) or bool(
        relink_error and any(term in relink_error.lower() for term in ("headerpad", "load commands do not fit"))
    )
    relink_failed = truthy(value.get("relink_failed")) or bool(relink_error)
    return {
        "name": library_name,
        "path_hash": stable_text_hash(path) if path else None,
        "path_recorded": False,
        "install_name_hash": stable_text_hash(install_name) if install_name else None,
        "install_name_recorded": False,
        "unresolved_rpath": unresolved_rpath,
        "relink_failed": relink_failed,
        "headerpad_failure": headerpad_failure,
        "relink_error_hash": stable_text_hash(relink_error) if relink_error else None,
        "relink_error_recorded": False,
    }


def evaluate_provider_usage_limit_preflight(
    *,
    provider: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Classify provider usage-limit signals without exporting credentials or bodies."""

    raw_usage = provider.get("usage_limit", runtime.get("usage_limit"))
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    raw_headers = usage.get("headers") or usage.get("response_headers")
    headers = raw_headers if isinstance(raw_headers, dict) else {}
    response_status = optional_int(usage.get("response_status") or usage.get("status_code"))
    pool = usage.get("credential_pool") if isinstance(usage.get("credential_pool"), dict) else {}
    account_label = optional_string(
        usage.get("active_credential_label")
        or usage.get("credential_label")
        or pool.get("active_credential_label")
        or pool.get("credential_label")
    )
    credential_count = optional_int(pool.get("credential_count") or usage.get("credential_count")) or 0
    pool_configured = truthy(pool.get("configured")) or credential_count > 0
    retry_after = optional_string(usage.get("retry_after") or headers.get("retry-after") or headers.get("Retry-After"))
    windows = provider_usage_limit_windows(headers)
    exhausted_windows = [window for window in windows if window["exhausted"]]
    near_limit_windows = [window for window in windows if window["near_limit"]]
    rate_limited = response_status == 429 or truthy(usage.get("rate_limited"))
    exhausted = rate_limited or bool(exhausted_windows)
    observed = bool(usage or headers or response_status)

    diagnostics: list[str] = []
    if rate_limited:
        diagnostics.append("provider returned a rate-limit status; block retry before launching another request")
    if exhausted_windows:
        diagnostics.append("provider usage-limit headers report an exhausted account window")
    if near_limit_windows and not exhausted:
        diagnostics.append("provider usage-limit headers report low remaining headroom")
    if exhausted and pool_configured:
        diagnostics.append(
            "credential-pool failover is review-only because credential labels and tokens are privacy-sensitive"
        )

    return {
        "observed": observed,
        "ok": not exhausted,
        "failure_mode": "provider_usage_limit_exhausted" if exhausted else "none",
        "response_status": response_status,
        "rate_limited": rate_limited,
        "window_count": len(windows),
        "exhausted_window_count": len(exhausted_windows),
        "near_limit_window_count": len(near_limit_windows),
        "windows": windows,
        "retry_after_present": bool(retry_after),
        "retry_after_hash": stable_text_hash(retry_after) if retry_after else None,
        "credential_pool_configured": pool_configured,
        "credential_count": credential_count,
        "active_credential_label_hash": stable_text_hash(account_label) if account_label else None,
        "active_credential_label_exported": False,
        "credential_values_exported": False,
        "raw_headers_exported": False,
        "raw_response_body_exported": False,
        "failover_review_only": exhausted and pool_configured,
        "failover_executed": False,
        "failover_review_plan": provider_usage_limit_failover_review_plan(
            exhausted=exhausted,
            pool_configured=pool_configured,
            credential_count=credential_count,
            account_label_present=bool(account_label),
        ),
        "diagnostics": diagnostics,
    }


def provider_usage_limit_failover_review_plan(
    *,
    exhausted: bool,
    pool_configured: bool,
    credential_count: int,
    account_label_present: bool,
) -> dict[str, Any]:
    """Return a body-free operator plan for credential-pool failover review."""

    review_required = exhausted and pool_configured
    return {
        "required": review_required,
        "status": "privacy_review_required" if review_required else "not_applicable",
        "controller_surface": "provider_usage_limit_failover_review",
        "review_gate": PRIVACY_REVIEW_GATE if review_required else None,
        "reason": "credential_pool_failover_requires_private_credential_review"
        if review_required
        else "no_exhausted_configured_credential_pool",
        "credential_count": credential_count,
        "active_credential_label_present": account_label_present,
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
        ]
        if review_required
        else [],
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ]
        if review_required
        else [],
    }


def provider_usage_limit_windows(headers: dict[Any, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        if not name.startswith("anthropic-ratelimit-unified-"):
            continue
        suffix = name.removeprefix("anthropic-ratelimit-unified-")
        parts = suffix.rsplit("-", 1)
        if len(parts) != 2:
            continue
        window_name, field = parts
        if field not in {"limit", "remaining", "reset"}:
            continue
        record = grouped.setdefault(window_name, {"name": window_name})
        record[field] = raw_value

    windows: list[dict[str, Any]] = []
    for window_name, record in sorted(grouped.items()):
        remaining = optional_int(record.get("remaining"))
        limit = optional_int(record.get("limit"))
        reset = optional_string(record.get("reset"))
        near_limit = remaining is not None and remaining <= 1
        windows.append(
            {
                "name": window_name,
                "limit_recorded": limit is not None,
                "remaining": remaining,
                "remaining_recorded": remaining is not None,
                "reset_present": bool(reset),
                "reset_hash": stable_text_hash(reset) if reset else None,
                "exhausted": remaining is not None and remaining <= 0,
                "near_limit": near_limit,
                "raw_header_values_exported": False,
            }
        )
    return windows


def evaluate_provider_review_model_preflight(
    *,
    provider: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Validate review-model route metadata before review execution.

    This checks opaque model configuration as metadata only. It never exports
    prompt, review, stdout, stderr, token, or credential bodies.
    """

    raw_models = provider.get("review_models", runtime.get("review_models"))
    models = [item for item in raw_models if isinstance(item, dict)] if isinstance(raw_models, list) else []
    required = (
        truthy(provider.get("review_model_preflight_required"))
        or truthy(runtime.get("review_model_preflight_required"))
        or bool(models)
    )
    require_exercised = truthy(provider.get("review_model_exercise_required")) or truthy(
        runtime.get("review_model_exercise_required")
    )
    records = [normalize_review_model_record(item) for item in models]
    required_records = [record for record in records if record["required"]]
    missing = required and not required_records
    missing_model_ids = [record for record in required_records if not record["model_id_configured"]]
    unavailable = [record for record in required_records if record["model_id_configured"] and not record["available"]]
    unsupported = [record for record in required_records if record["model_id_configured"] and not record["supported"]]
    unexercised = [
        record
        for record in required_records
        if require_exercised and record["model_id_configured"] and record["available"] and not record["exercised"]
    ]

    diagnostics: list[str] = []
    if missing:
        diagnostics.append("review model preflight is required but no required review models were configured")
    for record in missing_model_ids:
        diagnostics.append(f"review model id is missing for provider: {record['provider']}")
    for record in unavailable:
        diagnostics.append(f"configured review model is unavailable for provider: {record['provider']}")
    for record in unsupported:
        diagnostics.append(f"configured review model is unsupported for provider: {record['provider']}")
    for record in unexercised:
        diagnostics.append(f"configured review model was not exercised during validation: {record['provider']}")

    if missing:
        failure_mode = "review_model_config_missing"
    elif missing_model_ids:
        failure_mode = "review_model_id_missing"
    elif unavailable:
        failure_mode = "review_model_unavailable"
    elif unsupported:
        failure_mode = "review_model_unsupported"
    elif unexercised:
        failure_mode = "review_model_not_exercised"
    else:
        failure_mode = "none"

    return {
        "required": required,
        "require_exercised": require_exercised,
        "configured": bool(required_records),
        "ok": not diagnostics,
        "failure_mode": failure_mode,
        "review_model_count": len(records),
        "required_review_model_count": len(required_records),
        "available_review_model_count": sum(1 for record in required_records if record["available"]),
        "supported_review_model_count": sum(1 for record in required_records if record["supported"]),
        "exercised_review_model_count": sum(1 for record in required_records if record["exercised"]),
        "unavailable_provider_labels": sorted({record["provider"] for record in unavailable}),
        "unsupported_provider_labels": sorted({record["provider"] for record in unsupported}),
        "unexercised_provider_labels": sorted({record["provider"] for record in unexercised}),
        "records": records,
        "raw_review_bodies_exported": False,
        "raw_model_ids_exported": False,
        "diagnostics": diagnostics,
    }


def normalize_review_model_record(value: dict[str, Any]) -> dict[str, Any]:
    provider_label = optional_string(value.get("provider") or value.get("provider_label")) or "unknown-review-provider"
    model_id = optional_string(value.get("model_id") or value.get("model") or value.get("name"))
    available = truthy(value.get("available", value.get("resolves", False)))
    supported = truthy(value.get("supported", True))
    exercised = truthy(value.get("exercised", value.get("validated", False)))
    required = truthy(value.get("required", True))
    return {
        "provider": provider_label,
        "required": required,
        "model_id_configured": bool(model_id),
        "model_id_hash": stable_text_hash(model_id) if model_id else None,
        "model_id_recorded": False,
        "available": available,
        "supported": supported,
        "exercised": exercised,
    }


def evaluate_provider_model_command_preflight(
    *,
    provider: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    """Validate model command metadata before a provider harness can launch."""

    required = truthy(provider.get("model_command_required")) or truthy(runtime.get("model_command_required"))
    command_value = runtime.get("model_command", provider.get("model_command"))
    command_configured = command_value is not None
    command_parts = command_value if isinstance(command_value, list) else None
    command_shape_valid = bool(
        command_parts and all(isinstance(part, str) and bool(part.strip()) for part in command_parts)
    )
    malformed = command_configured and not command_shape_valid
    missing = required and not command_configured
    ok = not missing and not malformed
    diagnostics: list[str] = []
    if missing:
        diagnostics.append("provider model command is required but was not configured")
    if malformed:
        diagnostics.append("provider model command must be a non-empty list of non-empty strings")

    if missing:
        failure_mode = "provider_model_command_missing"
    elif malformed:
        failure_mode = "provider_model_command_malformed"
    else:
        failure_mode = "none"

    normalized_parts = [str(part).strip() for part in command_parts] if command_shape_valid else []
    return {
        "required": required,
        "configured": command_configured,
        "ok": ok,
        "failure_mode": failure_mode,
        "command_shape_valid": command_shape_valid,
        "command_arg_count": len(normalized_parts),
        "command_hashes": [stable_text_hash(part) for part in normalized_parts],
        "raw_command_exported": False,
        "diagnostics": diagnostics,
    }


def evaluate_provider_runtime_recovery_summary(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Aggregate provider runtime preflight cases into body-free recovery hints."""

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    raw_cases = raw_input.get("preflights")
    cases = raw_cases if isinstance(raw_cases, list) else []
    preflights = [
        evaluate_provider_runtime_preflight(provider_runtime_summary_case_input(case), source_path=source_path)
        for case in cases
        if isinstance(case, dict)
    ]
    status_counts = {
        "passed": sum(1 for preflight in preflights if preflight["route_status"] == "passed"),
        "degraded": sum(1 for preflight in preflights if preflight["route_status"] == "degraded"),
        "blocked": sum(1 for preflight in preflights if preflight["route_status"] == "blocked"),
    }
    recovery_hints = provider_runtime_recovery_hints(preflights)
    route_status = "blocked" if status_counts["blocked"] else "degraded" if status_counts["degraded"] else "passed"
    failure_mode = "provider_runtime_recovery_required" if status_counts["blocked"] else "none"
    supervisor_readiness = provider_runtime_supervisor_readiness(
        preflights,
        status_counts=status_counts,
        recovery_hints=recovery_hints,
    )

    return {
        "schema_version": 1,
        "behavior": "provider_runtime_recovery_summary",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "preflight_count": len(preflights),
        "status_counts": status_counts,
        "blocked_failure_modes": sorted(
            {str(preflight["failure_mode"]) for preflight in preflights if preflight["route_status"] == "blocked"}
        ),
        "degraded_provider_count": status_counts["degraded"],
        "runner_invoked_count": sum(1 for preflight in preflights if preflight["runtime"]["runner_invoked"]),
        "recovery_hints": recovery_hints,
        "operator_recovery_plan": provider_runtime_operator_recovery_plan(
            route_status=route_status,
            failure_mode=failure_mode,
            preflight_count=len(preflights),
            status_counts=status_counts,
            recovery_hints=recovery_hints,
        ),
        "supervisor_readiness": supervisor_readiness,
        "activation_gate": {
            "controller_surface": "provider_runtime_recovery_summary",
            "activation_scope": "local_replay_only",
            "decision": "blocked_before_provider_launch" if status_counts["blocked"] else "ready_for_local_mock_replay",
            "reason": failure_mode,
            "provider_runtime_launch_allowed": False,
            "local_validation_required": True,
        },
        "privacy": {
            "raw_preflight_inputs_exported": False,
            "raw_diagnostics_exported": False,
            "raw_urls_exported": False,
            "raw_paths_exported": False,
            "env_values_exported": False,
            "env_key_names_exported": False,
            "secret_values_exported": False,
        },
    }


def provider_runtime_summary_case_input(case: dict[str, Any]) -> dict[str, Any]:
    nested_input = case.get("input")
    return nested_input if isinstance(nested_input, dict) else case


def provider_runtime_preflight_supervisor_replay(
    preflight: dict[str, Any],
    *,
    recovery_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return body-free commands and decisions for replaying one provider preflight."""

    route_status = optional_string(preflight.get("route_status")) or "unknown"
    failure_mode = optional_string(preflight.get("failure_mode")) or "none"
    blocked = route_status == "blocked"
    degraded = route_status == "degraded"
    recovery_hint_codes = sorted(
        {str(hint.get("code")) for hint in recovery_hints if str(hint.get("code") or "").strip()}
    )
    return {
        "ready_for_provider_launch": False,
        "ready_for_local_replay": not blocked,
        "decision": "blocked_before_provider_launch" if blocked else "ready_for_local_mock_replay",
        "reason": failure_mode if blocked else "none",
        "route_status": route_status,
        "recovery_hint_codes": recovery_hint_codes,
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
            "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
        ],
        "local_validation_required": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_input_exported": False,
        "raw_diagnostics_exported": False,
        "degraded_replay_only": degraded,
    }


def provider_runtime_operator_recovery_plan(
    *,
    route_status: str,
    failure_mode: str,
    preflight_count: int,
    status_counts: dict[str, int],
    recovery_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a compact, body-free recovery plan for provider runtime diagnostics."""

    replay_commands = [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    recovery_steps = [
        {
            "code": str(hint.get("code") or ""),
            "scope": str(hint.get("scope") or "provider_runtime"),
            "severity": str(hint.get("severity") or "notice"),
            "affected_preflight_count": int(hint.get("affected_preflight_count") or 0),
            "provider_harness_count": len(string_list(hint.get("provider_harnesses"))),
            "action": str(hint.get("action") or ""),
            "privacy_review_required": bool(
                hint.get("failover_review_only")
                or (
                    isinstance(hint.get("failover_review_plan"), dict)
                    and str(hint["failover_review_plan"].get("status") or "") == "privacy_review_required"
                )
            ),
            "value_recorded": False,
        }
        for hint in recovery_hints
        if str(hint.get("code") or "").strip()
    ]
    recovery_hint_codes = [step["code"] for step in recovery_steps]
    blocked = route_status == "blocked"
    degraded = route_status == "degraded"
    no_preflights = preflight_count <= 0

    if no_preflights:
        decision = "blocked_no_provider_runtime_preflights"
        next_action = "add_provider_runtime_preflight_fixture_then_replay"
        reason = "no_provider_runtime_preflights"
    elif blocked:
        decision = "blocked_recovery_required"
        next_action = "resolve_recovery_steps_then_replay"
        reason = failure_mode
    elif degraded:
        decision = "degraded_local_replay_only"
        next_action = "review_degraded_steps_then_replay"
        reason = "degraded_provider_runtime_replay_only"
    else:
        decision = "ready_for_local_replay"
        next_action = "replay_provider_runtime_preflight"
        reason = "none"

    return {
        "controller_surface": "provider_runtime_operator_recovery_plan",
        "decision": decision,
        "reason": reason,
        "next_action": next_action,
        "preflight_count": preflight_count,
        "status_counts": dict(status_counts),
        "recovery_step_count": len(recovery_steps),
        "recovery_hint_codes": recovery_hint_codes,
        "recovery_hint_code_hashes": [stable_text_hash(code) for code in recovery_hint_codes],
        "recovery_steps": recovery_steps,
        "replay_commands": replay_commands,
        "local_validation_required": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "body_free_diagnostics_only": True,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
        "raw_provider_values_exported": False,
    }


def provider_runtime_supervisor_readiness(
    preflights: list[dict[str, Any]],
    *,
    status_counts: dict[str, int],
    recovery_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return an operator-facing provider-runtime handoff without raw diagnostics."""

    replay_commands = [
        "pytest tests/test_harness_eval.py -q -k provider_runtime_preflight",
        "pytest tests/test_harness_eval.py -q -k provider_runtime_recovery_summary",
    ]
    blocked_failure_modes = sorted(
        {str(preflight["failure_mode"]) for preflight in preflights if preflight["route_status"] == "blocked"}
    )
    recovery_hint_codes = sorted(
        {str(hint.get("code")) for hint in recovery_hints if str(hint.get("code") or "").strip()}
    )
    no_preflights = not preflights
    blocked = bool(status_counts.get("blocked"))
    degraded = bool(status_counts.get("degraded"))
    success_status = provider_runtime_success_status_guardrail(
        preflight_count=len(preflights),
        blocked=blocked,
        degraded=degraded,
    )

    if no_preflights:
        decision = "blocked_before_supervisor_promotion"
        reason = "no_provider_runtime_preflights"
    elif blocked:
        decision = "blocked_before_supervisor_promotion"
        reason = "provider_runtime_recovery_required"
    elif degraded:
        decision = "ready_for_supervisor_degraded_local_replay"
        reason = "degraded_provider_runtime_replay_only"
    else:
        decision = "ready_for_supervisor_local_replay"
        reason = "none"

    return {
        "ready_for_supervisor_promotion": success_status["success_claim_allowed"],
        "ready_for_supervisor_local_replay": success_status["local_replay_allowed"],
        "decision": decision,
        "reason": reason,
        "success_status": success_status,
        "preflight_count": len(preflights),
        "status_counts": dict(status_counts),
        "blocked_failure_modes": blocked_failure_modes,
        "degraded_provider_count": int(status_counts.get("degraded") or 0),
        "recovery_hint_codes": recovery_hint_codes,
        "replay_commands": replay_commands,
        "local_validation_required": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
    }


def provider_runtime_success_status_guardrail(
    *,
    preflight_count: int,
    blocked: bool,
    degraded: bool,
) -> dict[str, Any]:
    """Classify provider-runtime readiness without turning replay into launch success."""

    if preflight_count <= 0:
        status_label = "no_provider_runtime_preflights"
        reason = "no_provider_runtime_preflights"
    elif blocked:
        status_label = "provider_runtime_blocked"
        reason = "provider_runtime_recovery_required"
    elif degraded:
        status_label = "provider_runtime_degraded_replay_only"
        reason = "degraded_provider_runtime_replay_only"
    else:
        status_label = "provider_runtime_replay_ready"
        reason = "none"

    return {
        "misleading_success_guardrail": True,
        "status_label": status_label,
        "reason": reason,
        "success_claim_allowed": preflight_count > 0 and not blocked and not degraded,
        "operator_action_required": preflight_count <= 0 or blocked or degraded,
        "local_replay_allowed": preflight_count > 0 and not blocked,
        "provider_runtime_launch_allowed": False,
        "body_free_diagnostics_only": True,
    }


def provider_runtime_recovery_hints(preflights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hints: dict[str, dict[str, Any]] = {}
    for preflight in preflights:
        for hint in provider_runtime_recovery_hints_for_preflight(preflight):
            key = str(hint["code"])
            existing = hints.get(key)
            if existing is None:
                hints[key] = hint
                continue
            existing["affected_preflight_count"] += hint["affected_preflight_count"]
            existing["provider_harnesses"] = sorted(
                set(existing["provider_harnesses"]) | set(hint["provider_harnesses"])
            )
    return [hints[key] for key in sorted(hints)]


def provider_runtime_recovery_hints_for_preflight(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    provider = preflight.get("provider") if isinstance(preflight.get("provider"), dict) else {}
    runner_env = preflight.get("runner_env") if isinstance(preflight.get("runner_env"), dict) else {}
    provider_auth = preflight.get("provider_auth") if isinstance(preflight.get("provider_auth"), dict) else {}
    browser_tooling = preflight.get("browser_tooling") if isinstance(preflight.get("browser_tooling"), dict) else {}
    review_model = preflight.get("review_model") if isinstance(preflight.get("review_model"), dict) else {}
    usage_limit = preflight.get("usage_limit") if isinstance(preflight.get("usage_limit"), dict) else {}
    install_linkage = preflight.get("install_linkage") if isinstance(preflight.get("install_linkage"), dict) else {}
    model_command = preflight.get("model_command") if isinstance(preflight.get("model_command"), dict) else {}
    failure_mode = optional_string(preflight.get("failure_mode")) or "none"
    harness = optional_string(provider.get("harness")) or optional_string(provider.get("name")) or "unknown-provider"
    base_hint = {
        "affected_preflight_count": 1,
        "provider_harnesses": [harness],
        "value_recorded": False,
    }
    hints: list[dict[str, Any]] = []

    if failure_mode == "provider_env_missing":
        hints.append(
            {
                **base_hint,
                "code": "provider_env_missing",
                "scope": "provider_runtime_env",
                "severity": "blocker",
                "action": "configure required provider environment in the parent and harness allowlist or use a mock-only auth placeholder for local replay",
                "required_env_key_count": int(provider.get("required_env_key_count") or 0),
                "missing_parent_env_key_count": int(runner_env.get("missing_parent_env_key_count") or 0),
                "missing_harness_env_key_count": int(runner_env.get("missing_harness_env_key_count") or 0),
            }
        )
    elif failure_mode == "sandbox_runtime_preflight_failed":
        hints.append(
            {
                **base_hint,
                "code": "sandbox_runtime_preflight_failed",
                "scope": "provider_runtime_sandbox",
                "severity": "blocker",
                "action": "allow the provider sandbox override through the runner environment or enable provider auto-degrade before launch",
                "override_requested_in_parent": bool(runner_env.get("override_requested_in_parent")),
                "override_propagated_to_harness": bool(runner_env.get("override_propagated_to_harness")),
            }
        )
    elif failure_mode == "native_terminal_timeout_risk":
        hints.append(
            {
                **base_hint,
                "code": "native_terminal_timeout_risk",
                "scope": "provider_runtime_launch",
                "severity": "blocker",
                "action": "ensure the runner PATH resolves the native CLI or configure an explicit provider CLI path before terminal launch",
            }
        )
    elif failure_mode == "prompt_scan_timeout_risk":
        hints.append(
            {
                **base_hint,
                "code": "prompt_scan_timeout_risk",
                "scope": "provider_prompt_scan",
                "severity": "blocker",
                "action": "increase provider prompt scan tail lines before sending a second message",
            }
        )
    elif failure_mode == "url_safety_preflight_failed":
        hints.append(
            {
                **base_hint,
                "code": "url_safety_preflight_failed",
                "scope": "provider_url_safety",
                "severity": "blocker",
                "action": "replace localhost, loopback, private, or link-local provider URLs before browser launch",
            }
        )
    elif failure_mode == "provider_usage_limit_exhausted":
        hints.append(
            {
                **base_hint,
                "code": "provider_usage_limit_exhausted",
                "scope": "provider_usage_limit",
                "severity": "blocker",
                "action": "wait for the provider usage window reset or route credential-pool failover through privacy review before retry",
                "response_status": usage_limit.get("response_status"),
                "rate_limited": bool(usage_limit.get("rate_limited")),
                "window_count": int(usage_limit.get("window_count") or 0),
                "exhausted_window_count": int(usage_limit.get("exhausted_window_count") or 0),
                "credential_pool_configured": bool(usage_limit.get("credential_pool_configured")),
                "credential_count": int(usage_limit.get("credential_count") or 0),
                "failover_review_only": bool(usage_limit.get("failover_review_only")),
                "failover_executed": False,
                "failover_review_plan": usage_limit.get("failover_review_plan")
                if isinstance(usage_limit.get("failover_review_plan"), dict)
                else provider_usage_limit_failover_review_plan(
                    exhausted=True,
                    pool_configured=bool(usage_limit.get("credential_pool_configured")),
                    credential_count=int(usage_limit.get("credential_count") or 0),
                    account_label_present=bool(usage_limit.get("active_credential_label_hash")),
                ),
                "raw_headers_exported": False,
                "raw_response_body_exported": False,
            }
        )
    elif failure_mode in {"provider_model_command_missing", "provider_model_command_malformed"}:
        hints.append(
            {
                **base_hint,
                "code": failure_mode,
                "scope": "provider_model_command",
                "severity": "blocker",
                "action": "configure a non-empty provider model command list before launching the harness",
                "command_required": bool(model_command.get("required")),
                "command_configured": bool(model_command.get("configured")),
                "command_arg_count": int(model_command.get("command_arg_count") or 0),
            }
        )
    elif failure_mode == "provider_install_linkage_unresolved":
        hints.append(
            {
                **base_hint,
                "code": "provider_install_linkage_unresolved",
                "scope": "provider_install_linkage",
                "severity": "blocker",
                "action": "repair or relink Apple Silicon Homebrew dynamic libraries before launching the provider runtime",
                "package_manager": install_linkage.get("package_manager"),
                "platform": install_linkage.get("platform"),
                "architecture": install_linkage.get("architecture"),
                "apple_silicon_homebrew": bool(install_linkage.get("apple_silicon_homebrew")),
                "library_count": int(install_linkage.get("library_count") or 0),
                "unresolved_rpath_count": int(install_linkage.get("unresolved_rpath_count") or 0),
                "relink_failure_count": int(install_linkage.get("relink_failure_count") or 0),
                "raw_paths_exported": False,
                "raw_install_names_exported": False,
            }
        )
    elif failure_mode in {
        "review_model_config_missing",
        "review_model_id_missing",
        "review_model_not_exercised",
        "review_model_unavailable",
        "review_model_unsupported",
    }:
        hints.append(
            {
                **base_hint,
                "code": failure_mode,
                "scope": "provider_review_model",
                "severity": "blocker",
                "action": "validate each configured review model route against its provider before review execution",
                "required_review_model_count": int(review_model.get("required_review_model_count") or 0),
                "available_review_model_count": int(review_model.get("available_review_model_count") or 0),
                "supported_review_model_count": int(review_model.get("supported_review_model_count") or 0),
                "exercised_review_model_count": int(review_model.get("exercised_review_model_count") or 0),
                "raw_model_ids_exported": False,
            }
        )

    if bool(provider_auth.get("mock_auth_placeholder_used")):
        hints.append(
            {
                **base_hint,
                "code": "mock_auth_placeholder_used",
                "scope": "mock_llm_provider_auth",
                "severity": "notice",
                "action": "keep this route mock-only unless real provider credentials are configured outside fixture output",
                "required_env_key_count": int(provider.get("required_env_key_count") or 0),
            }
        )
    if bool(browser_tooling.get("configure_checks_skipped")):
        hints.append(
            {
                **base_hint,
                "code": "browser_configure_checks_skipped",
                "scope": "provider_browser_tooling",
                "severity": "notice",
                "action": "install or expose optional browser tooling before treating browser configure checks as covered",
            }
        )

    return hints


def evaluate_provider_browser_preflight(raw_input: dict[str, Any], *, provider: dict[str, Any]) -> dict[str, Any]:
    """Check URL safety even when optional browser tooling is unavailable."""

    browser_tooling = raw_input.get("browser_tooling") if isinstance(raw_input.get("browser_tooling"), dict) else {}
    url_policy = raw_input.get("url_safety") if isinstance(raw_input.get("url_safety"), dict) else {}
    base_url = optional_string(url_policy.get("base_url")) or optional_string(provider.get("base_url"))
    playwright_available = truthy(browser_tooling.get("playwright_available"))
    configure_checks_required = truthy(browser_tooling.get("configure_checks_required"))
    browser_configure_status = "not_required"
    browser_diagnostics: list[str] = []
    if configure_checks_required and playwright_available:
        browser_configure_status = "ready"
    elif configure_checks_required:
        browser_configure_status = "skipped_missing_optional_dependency"
        browser_diagnostics.append("Playwright is unavailable; browser configure checks were skipped")

    url_diagnostics = build_url_safety_diagnostics(
        base_url,
        require_base_url=truthy(url_policy.get("require_base_url")),
        refuse_local_targets=url_policy.get("refuse_local_targets") is not False,
    )
    url_ok = not url_diagnostics

    return {
        "browser_tooling": {
            "playwright_available": playwright_available,
            "configure_checks_required": configure_checks_required,
            "configure_checks_skipped": configure_checks_required and not playwright_available,
            "configure_status": browser_configure_status,
            "diagnostics": browser_diagnostics,
            "optional_dependency_values_recorded": False,
        },
        "url_safety": {
            "checked": bool(base_url) or truthy(url_policy.get("require_base_url")),
            "ok": url_ok,
            "base_url_present": bool(base_url),
            "base_url_recorded": False,
            "refuse_local_targets": url_policy.get("refuse_local_targets") is not False,
            "diagnostics": url_diagnostics,
        },
        "preflight": {
            "diagnostics": browser_diagnostics + url_diagnostics,
        },
    }


def evaluate_provider_prompt_scan_preflight(raw_input: dict[str, Any], *, provider: dict[str, Any]) -> dict[str, Any]:
    """Simulate prompt readiness scanning without exporting terminal pane text."""

    prompt_scan = raw_input.get("prompt_scan") if isinstance(raw_input.get("prompt_scan"), dict) else {}
    provider_name = (optional_string(provider.get("name")) or "").lower()
    harness = (optional_string(provider.get("harness")) or "").lower()
    is_claude_provider = "claude" in provider_name or "claude" in harness or "anthropic" in provider_name
    configured = bool(prompt_scan)
    if not configured:
        return {
            "prompt_scan": {
                "configured": False,
                "provider_prompt_scan_relevant": is_claude_provider,
                "tail_lines": None,
                "legacy_tail_lines": None,
                "status_footer_non_empty_lines": 0,
                "prompt_distance_from_bottom": None,
                "prompt_glyph_present": False,
                "prompt_detected": True,
                "legacy_timeout_risk": False,
                "second_message_send_would_timeout": False,
                "pane_text_exported": False,
                "timeout_seconds": None,
            },
            "preflight": {"diagnostics": []},
        }

    tail_lines = positive_int(prompt_scan.get("tail_lines"), default=12)
    legacy_tail_lines = positive_int(prompt_scan.get("legacy_tail_lines"), default=5)
    status_footer_lines = nonnegative_int(prompt_scan.get("status_footer_non_empty_lines"), default=0)
    prompt_glyph_present = prompt_scan.get("prompt_glyph_present") is not False
    timeout_seconds = positive_int(prompt_scan.get("timeout_seconds"), default=30)
    prompt_distance = status_footer_lines + 1 if prompt_glyph_present else None
    prompt_detected = bool(prompt_glyph_present and prompt_distance is not None and prompt_distance <= tail_lines)
    legacy_timeout_risk = bool(
        is_claude_provider
        and prompt_glyph_present
        and prompt_distance is not None
        and prompt_distance > legacy_tail_lines
    )
    second_message_send_would_timeout = not prompt_detected
    diagnostics: list[str] = []
    if legacy_timeout_risk and prompt_detected:
        diagnostics.append(
            "Claude prompt sits beyond the legacy scan tail but inside the configured provider prompt scan window"
        )
    if second_message_send_would_timeout:
        diagnostics.append("provider prompt scan window does not reach the prompt above the rendered status footer")
        diagnostics.append("increase provider prompt scan tail lines before sending a second message")

    return {
        "prompt_scan": {
            "configured": configured,
            "provider_prompt_scan_relevant": is_claude_provider,
            "tail_lines": tail_lines,
            "legacy_tail_lines": legacy_tail_lines,
            "status_footer_non_empty_lines": status_footer_lines,
            "prompt_distance_from_bottom": prompt_distance,
            "prompt_glyph_present": prompt_glyph_present,
            "prompt_detected": prompt_detected,
            "legacy_timeout_risk": legacy_timeout_risk,
            "second_message_send_would_timeout": second_message_send_would_timeout,
            "pane_text_exported": False,
            "timeout_seconds": timeout_seconds,
        },
        "preflight": {"diagnostics": diagnostics},
    }


def positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def nonnegative_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def build_url_safety_diagnostics(
    base_url: str | None,
    *,
    require_base_url: bool,
    refuse_local_targets: bool,
) -> list[str]:
    diagnostics: list[str] = []
    if not base_url:
        if require_base_url:
            diagnostics.append("base URL is required before provider browser preflight")
        return diagnostics

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        diagnostics.append("base URL must be an absolute http(s) URL")
        return diagnostics

    host = (parsed.hostname or "").lower()
    if refuse_local_targets and is_local_url_host(host):
        diagnostics.append("base URL must not target localhost, loopback, private, or link-local networks")
    return diagnostics


def is_local_url_host(host: str) -> bool:
    if host in {"localhost", "0.0.0.0"} or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local or address.is_unspecified


def build_provider_runtime_diagnostics(
    *,
    incompatible_sandbox: bool,
    native_terminal_timeout_risk: bool,
    degraded: bool,
    blocked: bool,
    override_flag: str,
    override_requested: bool,
    override_propagated: bool,
    auto_degrade: bool,
) -> list[str]:
    diagnostics: list[str] = []
    if override_requested and not override_propagated:
        diagnostics.append(f"{override_flag} was set before runner launch but did not reach the provider harness")
    if degraded:
        if override_propagated:
            diagnostics.append(
                f"{override_flag} reached the provider harness; using degraded unwrapped supervisor mode"
            )
        elif auto_degrade:
            diagnostics.append("provider runtime sandbox is incompatible; using degraded unwrapped supervisor mode")
        diagnostics.append(
            "native provider file and shell tools must remain disabled while outer sandbox tools stay active"
        )
    if blocked:
        diagnostics.append("provider runtime sandbox is incompatible and no degraded startup path was available")
        diagnostics.append(f"add {override_flag} to the runner environment allowlist or enable provider auto-degrade")
    if native_terminal_timeout_risk:
        diagnostics.append(
            "native Claude CLI is not visible to the tmux-launched provider harness; block before terminal timeout"
        )
        diagnostics.append("ensure the runner PATH resolves the native CLI or configure an explicit provider CLI path")
    if incompatible_sandbox and not degraded and not blocked:
        diagnostics.append("provider runtime sandbox compatibility could not be classified")
    return diagnostics


def build_provider_env_diagnostics(
    *,
    required_env_key_count: int,
    missing_parent_env_key_count: int,
    missing_harness_env_key_count: int,
    worker_env_inherit_skipped: bool,
    mock_auth_substitution: bool,
    env_preflight_failed: bool,
) -> list[str]:
    diagnostics: list[str] = []
    if not required_env_key_count:
        return diagnostics
    if mock_auth_substitution:
        diagnostics.append("mock LLM auth placeholder accepted; real provider key not required for this local fixture")
    if worker_env_inherit_skipped:
        diagnostics.append("skipped worker env inheritance check because the harness declares no worker tool")
    if missing_parent_env_key_count:
        diagnostics.append("required provider environment keys are missing from the parent runner environment")
    if missing_harness_env_key_count:
        diagnostics.append("required provider environment keys are not propagated to the provider harness")
    if env_preflight_failed:
        diagnostics.append("block provider startup before launch because required environment keys are unavailable")
    return diagnostics


def default_worker_tool_name(harness: str) -> str:
    """Return the conventional inline worker-tool name for a provider harness."""

    normalized = re.sub(r"[^A-Za-z0-9]+", "_", harness.strip().lower()).strip("_")
    return f"{normalized or 'provider'}_worker"


def normalize_terminal_integration(value: Any) -> str:
    terminal = (optional_string(value) or "unknown").strip().lower()
    if terminal in {"iterm", "iterm2", "com.googlecode.iterm2"}:
        return "iterm2"
    if terminal in {"apple_terminal", "terminal.app", "terminal"}:
        return "terminal_app"
    if terminal in {"vscode", "visual_studio_code"}:
        return "vscode"
    return terminal or "unknown"


def evaluate_native_skill_session_title(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Validate skill/slash-command native sessions keep descriptive labels.

    The fixture models the Omnigent #851 failure class without launching a
    provider: a native session starts with a slash-command item, so title
    derivation must use launch context instead of falling back to the provider
    label.
    """

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    provider_label = optional_string(raw_input.get("provider_label")) or "Claude Code"
    launch_context = raw_input.get("launch_context") if isinstance(raw_input.get("launch_context"), dict) else {}
    session_metadata = raw_input.get("session_metadata") if isinstance(raw_input.get("session_metadata"), dict) else {}
    transcript = raw_input.get("transcript") if isinstance(raw_input.get("transcript"), list) else []
    allowed_title_sources = set(
        string_list(raw_input.get("allowed_title_sources"))
        or ["command", "skill", "prompt", "launch_context", "llm_summary"]
    )
    generic_provider_labels = {
        normalize_title_label(label)
        for label in (
            string_list(raw_input.get("generic_provider_labels"))
            or ["Claude Code", "Codex", "OpenAI", "Claude", "Gemini"]
        )
    }

    actual_title = optional_string(session_metadata.get("title"))
    title_source = optional_string(session_metadata.get("title_source")) or ""
    expected_title = optional_string(session_metadata.get("expected_title") or launch_context.get("expected_title"))
    first_item_kind = first_transcript_item_kind(transcript)
    launch_context_signals = native_skill_launch_context_signals(launch_context, transcript)
    has_context_signal = bool(launch_context_signals)
    title_present = bool(actual_title)
    title_generic = bool(actual_title and normalize_title_label(actual_title) in generic_provider_labels)
    title_source_allowed = title_source in allowed_title_sources
    expected_title_matched = bool(
        expected_title and actual_title and normalize_title_label(actual_title) == normalize_title_label(expected_title)
    )
    context_derived = has_context_signal and (expected_title_matched or title_source_allowed)

    failure_mode = native_skill_session_title_failure_mode(
        title_present=title_present,
        title_generic=title_generic,
        has_context_signal=has_context_signal,
        title_source_allowed=title_source_allowed,
        expected_title_declared=bool(expected_title),
        expected_title_matched=expected_title_matched,
        context_derived=context_derived,
    )
    route_status = "passed" if failure_mode == "none" else "blocked"

    return {
        "schema_version": 1,
        "behavior": "native_skill_session_title",
        "task_id": task_id,
        "route_status": route_status,
        "failure_mode": failure_mode,
        "launch_path": {
            "first_item_kind": first_item_kind,
            "skill_or_slash_first": first_item_kind in {"slash_command", "skill", "command"},
            "context_signal_count": len(launch_context_signals),
            "context_signal_kinds": launch_context_signals,
            "context_signal_present": has_context_signal,
        },
        "session_title": {
            "present": title_present,
            "generic_provider_fallback": title_generic,
            "title_hash": stable_text_hash(actual_title) if actual_title else None,
            "title_exported": False,
            "provider_label_hash": stable_text_hash(provider_label),
            "provider_label_exported": False,
            "title_source": title_source,
            "title_source_allowed": title_source_allowed,
            "allowed_title_sources": sorted(allowed_title_sources),
            "expected_title_declared": bool(expected_title),
            "expected_title_matched": expected_title_matched,
            "context_derived": context_derived,
        },
        "activation_gate": {
            "controller_surface": "native_skill_session_title",
            "decision": "ready_for_native_session_metadata_validation"
            if failure_mode == "none"
            else "blocked_before_activation",
            "reason": failure_mode,
            "native_session_launch_allowed": False,
            "local_metadata_validation_allowed": failure_mode == "none",
        },
        "privacy": {
            "raw_command_exported": False,
            "raw_prompt_exported": False,
            "raw_title_exported": False,
            "raw_session_id_exported": False,
            "provider_launched": False,
        },
    }


def first_transcript_item_kind(transcript: list[Any]) -> str:
    for item in transcript:
        if isinstance(item, dict):
            return optional_string(item.get("type") or item.get("kind")) or "unknown"
    return "none"


def native_skill_launch_context_signals(launch_context: dict[str, Any], transcript: list[Any]) -> list[str]:
    signals: list[str] = []
    for key, signal in (
        ("command", "command"),
        ("command_name", "command"),
        ("slash_command", "command"),
        ("skill_name", "skill"),
        ("skill", "skill"),
        ("prompt", "prompt"),
        ("arguments", "arguments"),
        ("subject", "subject"),
    ):
        if optional_string(launch_context.get(key)) and signal not in signals:
            signals.append(signal)

    for item in transcript:
        if not isinstance(item, dict):
            continue
        item_kind = optional_string(item.get("type") or item.get("kind")) or ""
        if item_kind in {"slash_command", "skill", "command"} and "transcript_slash_command" not in signals:
            signals.append("transcript_slash_command")
        if item_kind == "message" and optional_string(item.get("role")) == "user" and "user_message" not in signals:
            signals.append("user_message")
    return signals


def native_skill_session_title_failure_mode(
    *,
    title_present: bool,
    title_generic: bool,
    has_context_signal: bool,
    title_source_allowed: bool,
    expected_title_declared: bool,
    expected_title_matched: bool,
    context_derived: bool,
) -> str:
    if not has_context_signal:
        return "missing_skill_launch_context"
    if not title_present:
        return "missing_session_title"
    if title_generic:
        return "generic_provider_title"
    if expected_title_declared and not expected_title_matched:
        return "title_does_not_match_expected_context"
    if not title_source_allowed:
        return "unsupported_title_source"
    if not context_derived:
        return "title_not_context_derived"
    return "none"


def normalize_title_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := optional_string(item))]


def evaluate_agent_workflow_route(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Evaluate a body-free local agent workflow route fixture.

    The fixture models the controller-visible route around an agent run:
    planning metadata, runner invocation, validation gate recording, failure
    classification, and whether rollback information exists for recovery.
    """

    task_id = optional_string(raw_input.get("task_id")) or source_path.stem
    plan = raw_input.get("plan") if isinstance(raw_input.get("plan"), dict) else {}
    plan_steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    runner = raw_input.get("runner") if isinstance(raw_input.get("runner"), dict) else {}
    validation = raw_input.get("validation") if isinstance(raw_input.get("validation"), dict) else {}
    checks = validation.get("checks") if isinstance(validation.get("checks"), list) else []
    rollback = raw_input.get("rollback") if isinstance(raw_input.get("rollback"), dict) else {}
    lifecycle = raw_input.get("lifecycle") if isinstance(raw_input.get("lifecycle"), dict) else {}
    oneshot_marker = raw_input.get("oneshot_marker") if isinstance(raw_input.get("oneshot_marker"), dict) else {}
    observations = raw_input.get("observations") if isinstance(raw_input.get("observations"), list) else []
    report_artifacts = raw_input.get("artifacts") if isinstance(raw_input.get("artifacts"), dict) else {}
    recovery = raw_input.get("recovery") if isinstance(raw_input.get("recovery"), dict) else {}
    stream_boundaries = (
        raw_input.get("streamed_tool_boundaries") if isinstance(raw_input.get("streamed_tool_boundaries"), dict) else {}
    )
    orchestrator_inbox = (
        raw_input.get("orchestrator_inbox") if isinstance(raw_input.get("orchestrator_inbox"), dict) else {}
    )

    runner_invoked = truthy(runner.get("invoked"))
    runner_returncode = optional_int(runner.get("returncode")) if runner_invoked else None
    runner_timed_out = truthy(runner.get("timed_out"))
    marker_result = evaluate_agent_workflow_oneshot_marker(oneshot_marker)
    validation_gate = optional_string(validation.get("gate")) or "local-agent-workflow-route"
    validation_checks = [
        {
            "name": optional_string(check.get("name")) or f"check-{index + 1}",
            "returncode": optional_int(check.get("returncode")),
            "passed": optional_int(check.get("returncode")) == 0,
        }
        for index, check in enumerate(checks)
        if isinstance(check, dict)
    ]
    validation_passed = bool(validation_checks) and all(check["passed"] for check in validation_checks)
    rollback_ref = optional_string(rollback.get("ref"))
    rollback_artifact = optional_string(rollback.get("artifact_path"))
    rollback_available = truthy(rollback.get("created")) and bool(rollback_ref or rollback_artifact)
    recovery_handoff = evaluate_agent_workflow_recovery_handoff(
        recovery,
        rollback_available=rollback_available,
        rollback_ref=rollback_ref,
        rollback_artifact=rollback_artifact,
        validation_checks=validation_checks,
    )
    observation_result = evaluate_agent_workflow_observations(observations)
    stream_boundary_result = evaluate_agent_workflow_stream_boundaries(stream_boundaries)
    inbox_result = evaluate_agent_workflow_orchestrator_inbox(orchestrator_inbox)
    state_transitions = build_agent_workflow_state_transitions(
        plan_steps=plan_steps,
        oneshot_marker_ready=marker_result["ready"],
        oneshot_marker_required=marker_result["required"],
        runner_invoked=runner_invoked,
        validation_checks=validation_checks,
        failure_mode=agent_workflow_failure_mode(
            oneshot_marker_ready=marker_result["ready"],
            runner_invoked=runner_invoked,
            runner_returncode=runner_returncode,
            runner_timed_out=runner_timed_out,
            validation_passed=validation_passed,
            lifecycle_passed=True,
            recovery_handoff_required=bool(recovery_handoff["required"]),
            recovery_handoff_ready=bool(recovery_handoff["ready"]),
            observations_passed=observation_result["passed"],
            observations_failure_mode=observation_result["failure_mode"],
            stream_boundaries_passed=stream_boundary_result["passed"],
            stream_boundaries_failure_mode=stream_boundary_result["failure_mode"],
            inbox_delivery_passed=inbox_result["passed"],
            inbox_delivery_failure_mode=inbox_result["failure_mode"],
        ),
        rollback_available=rollback_available,
    )
    lifecycle_result = evaluate_agent_workflow_lifecycle(lifecycle, state_transitions)

    failure_mode = agent_workflow_failure_mode(
        oneshot_marker_ready=marker_result["ready"],
        runner_invoked=runner_invoked,
        runner_returncode=runner_returncode,
        runner_timed_out=runner_timed_out,
        validation_passed=validation_passed,
        lifecycle_passed=lifecycle_result["passed"],
        recovery_handoff_required=bool(recovery_handoff["required"]),
        recovery_handoff_ready=bool(recovery_handoff["ready"]),
        observations_passed=observation_result["passed"],
        observations_failure_mode=observation_result["failure_mode"],
        stream_boundaries_passed=stream_boundary_result["passed"],
        stream_boundaries_failure_mode=stream_boundary_result["failure_mode"],
        inbox_delivery_passed=inbox_result["passed"],
        inbox_delivery_failure_mode=inbox_result["failure_mode"],
    )
    if failure_mode == "none":
        route_status = "passed"
    elif failure_mode == "oneshot_marker_missing":
        route_status = "blocked_before_activation"
    else:
        route_status = "failed_recoverable" if rollback_available else "failed_unrecoverable"
    state_transitions = build_agent_workflow_state_transitions(
        plan_steps=plan_steps,
        oneshot_marker_ready=marker_result["ready"],
        oneshot_marker_required=marker_result["required"],
        runner_invoked=runner_invoked,
        validation_checks=validation_checks,
        failure_mode=failure_mode,
        rollback_available=rollback_available,
    )
    lifecycle_result = evaluate_agent_workflow_lifecycle(lifecycle, state_transitions)
    control_plane = build_agent_workflow_control_plane(
        task_id=task_id,
        plan_steps=plan_steps,
        runner_invoked=runner_invoked,
        state_transitions=state_transitions,
        validation_gate=validation_gate,
        validation_checks=validation_checks,
        rollback_available=rollback_available,
        recovery_handoff=recovery_handoff,
        observation_result=observation_result,
        stream_boundary_result=stream_boundary_result,
        inbox_result=inbox_result,
        report_artifacts=report_artifacts,
        source_path=source_path,
    )
    if failure_mode == "none" and control_plane["failure_mode"] != "none":
        failure_mode = str(control_plane["failure_mode"])
        route_status = "failed_recoverable" if rollback_available else "failed_unrecoverable"
        state_transitions = build_agent_workflow_state_transitions(
            plan_steps=plan_steps,
            oneshot_marker_ready=marker_result["ready"],
            oneshot_marker_required=marker_result["required"],
            runner_invoked=runner_invoked,
            validation_checks=validation_checks,
            failure_mode=failure_mode,
            rollback_available=rollback_available,
        )
        lifecycle_result = evaluate_agent_workflow_lifecycle(lifecycle, state_transitions)

    return {
        "schema_version": 1,
        "behavior": "agent_workflow_route",
        "task_id": task_id,
        "route_status": route_status,
        "control_plane": control_plane,
        "state_transitions": state_transitions,
        "planning": {
            "step_count": len(plan_steps),
            "planned": bool(plan_steps),
            "all_steps_have_ids": all(
                isinstance(step, dict) and bool(optional_string(step.get("id"))) for step in plan_steps
            ),
        },
        "runner": {
            "invoked": runner_invoked,
            "returncode": runner_returncode,
            "timed_out": runner_timed_out,
        },
        "oneshot_marker": marker_result,
        "lifecycle": lifecycle_result,
        "observations": observation_result,
        "streamed_tool_boundaries": stream_boundary_result,
        "orchestrator_inbox": inbox_result,
        "validation": {
            "gate": validation_gate,
            "gate_recorded": bool(validation_gate),
            "gate_outcome": "passed" if validation_passed else "failed",
            "checks": validation_checks,
        },
        "rollback": {
            "available": rollback_available,
            "ref_recorded": bool(rollback_ref),
            "artifact_recorded": bool(rollback_artifact),
            "recovery_mode": "explicit_operator_reset" if rollback_available else "manual_investigation",
        },
        "recovery_handoff": recovery_handoff,
        "failure_mode": failure_mode,
    }


def agent_workflow_failure_mode(
    *,
    oneshot_marker_ready: bool,
    runner_invoked: bool,
    runner_returncode: int | None,
    runner_timed_out: bool,
    validation_passed: bool,
    lifecycle_passed: bool,
    recovery_handoff_required: bool = False,
    recovery_handoff_ready: bool = True,
    observations_passed: bool = True,
    observations_failure_mode: str = "none",
    stream_boundaries_passed: bool = True,
    stream_boundaries_failure_mode: str = "none",
    inbox_delivery_passed: bool = True,
    inbox_delivery_failure_mode: str = "none",
) -> str:
    if not oneshot_marker_ready:
        return "oneshot_marker_missing"
    if not runner_invoked:
        return "runner_not_invoked"
    if runner_timed_out:
        return "timeout"
    if runner_returncode not in (None, 0):
        return "nonzero_exit"
    if not observations_passed:
        return observations_failure_mode
    if not stream_boundaries_passed:
        return stream_boundaries_failure_mode
    if not inbox_delivery_passed:
        return inbox_delivery_failure_mode
    if recovery_handoff_required and not recovery_handoff_ready:
        return "recovery_handoff_incomplete"
    if not lifecycle_passed:
        return "lifecycle_incomplete"
    if not validation_passed:
        return "validation_failed"
    return "none"


def evaluate_agent_workflow_orchestrator_inbox(inbox: dict[str, Any]) -> dict[str, Any]:
    """Validate sub-agent completion delivery to the parent inbox without bodies."""

    required = truthy(inbox.get("required"))
    expected_count = optional_int(inbox.get("expected_completion_count"))
    if expected_count is None:
        expected_count = 1 if required else 0
    parent_woken = truthy(inbox.get("parent_woken", not required))
    raw_messages = inbox.get("messages") if isinstance(inbox.get("messages"), list) else []
    raw_child_turns = inbox.get("child_turns") if isinstance(inbox.get("child_turns"), list) else []
    messages = [
        normalize_agent_workflow_inbox_message(message, index)
        for index, message in enumerate(raw_messages, start=1)
        if isinstance(message, dict)
    ]
    child_turns = [
        normalize_agent_workflow_child_turn(turn, index)
        for index, turn in enumerate(raw_child_turns, start=1)
        if isinstance(turn, dict)
    ]
    lifecycle = inbox.get("child_lifecycle") if isinstance(inbox.get("child_lifecycle"), dict) else {}
    recovery = inbox.get("recovery") if isinstance(inbox.get("recovery"), dict) else {}
    completion_count = sum(1 for message in messages if message["completion"])
    transcript_only_count = sum(1 for turn in child_turns if turn["transcript_only"])
    empty_turn_count = sum(1 for turn in child_turns if turn["empty"])
    sub_agent_name_present = truthy(lifecycle.get("sub_agent_name_present", not required))
    send_handle_degraded = truthy(lifecycle.get("send_handle_degraded"))
    close_supported = truthy(lifecycle.get("close_supported", not required))
    lifecycle_degraded = required and (not sub_agent_name_present or send_handle_degraded or not close_supported)
    transcript_polling_available = (
        truthy(
            recovery.get("transcript_polling_available"),
        )
        or transcript_only_count > 0
    )
    transcript_polling_required = required and completion_count < expected_count and transcript_polling_available
    cleanup_required = required and lifecycle_degraded
    cleanup_supported = close_supported and not send_handle_degraded
    cleanup_blocked = cleanup_required and not cleanup_supported

    if required and completion_count < expected_count:
        failure_mode = "orchestrator_inbox_completion_missing"
    elif expected_count >= 0 and completion_count > expected_count:
        failure_mode = "orchestrator_inbox_duplicate_completion"
    elif required and empty_turn_count:
        failure_mode = "orchestrator_inbox_empty_turn"
    elif required and transcript_only_count:
        failure_mode = "orchestrator_inbox_transcript_only_completion"
    elif required and not parent_woken:
        failure_mode = "orchestrator_inbox_parent_not_woken"
    elif lifecycle_degraded:
        failure_mode = "orchestrator_inbox_lifecycle_degraded"
    else:
        failure_mode = "none"

    return {
        "required": required,
        "passed": failure_mode == "none",
        "failure_mode": failure_mode,
        "expected_completion_count": expected_count,
        "completion_message_count": completion_count,
        "message_count": len(messages),
        "parent_woken": parent_woken,
        "transcript_only_turn_count": transcript_only_count,
        "empty_turn_count": empty_turn_count,
        "child_turn_count": len(child_turns),
        "recovery": {
            "transcript_polling_available": transcript_polling_available,
            "transcript_polling_required": transcript_polling_required,
            "cleanup_required": cleanup_required,
            "cleanup_supported": cleanup_supported,
            "cleanup_blocked": cleanup_blocked,
            "operator_action": agent_workflow_inbox_recovery_action(
                failure_mode,
                transcript_polling_required=transcript_polling_required,
                cleanup_blocked=cleanup_blocked,
            ),
            "raw_transcripts_exported": False,
            "raw_session_ids_exported": False,
        },
        "messages": messages,
        "child_turns": child_turns,
        "child_lifecycle": {
            "sub_agent_name_present": sub_agent_name_present,
            "send_handle_degraded": send_handle_degraded,
            "close_supported": close_supported,
            "degraded": lifecycle_degraded,
            "raw_agent_names_exported": False,
            "raw_session_ids_exported": False,
        },
        "policy": {
            "exactly_one_completion_by_default": True,
            "parent_wake_required": required,
            "empty_turns_allowed": False,
            "transcript_only_completion_allowed": False,
            "transcript_polling_is_recovery_only": True,
            "uncleanable_child_sessions_block_cleanup": True,
            "raw_message_bodies_exported": False,
            "raw_transcript_bodies_exported": False,
        },
    }


def agent_workflow_inbox_recovery_action(
    failure_mode: str,
    *,
    transcript_polling_required: bool,
    cleanup_blocked: bool,
) -> str:
    if failure_mode == "none":
        return "none"
    if transcript_polling_required and cleanup_blocked:
        return "poll_child_transcript_then_manual_session_cleanup"
    if transcript_polling_required:
        return "poll_child_transcript_for_result"
    if cleanup_blocked:
        return "manual_session_cleanup_required"
    if failure_mode == "orchestrator_inbox_empty_turn":
        return "rerun_child_turn_with_empty_output_error"
    return "inspect_inbox_delivery_route"


def normalize_agent_workflow_inbox_message(message: dict[str, Any], ordinal: int) -> dict[str, Any]:
    kind = normalize_agent_workflow_inbox_message_kind(message.get("kind") or message.get("type"))
    message_id = optional_string(message.get("id") or message.get("message_id"))
    child_session_id = optional_string(message.get("child_session_id") or message.get("session_id"))
    return {
        "ordinal": ordinal,
        "kind": kind,
        "completion": kind == "completion",
        "message_id_hash": stable_text_hash(message_id) if message_id else None,
        "child_session_hash": stable_text_hash(child_session_id) if child_session_id else None,
        "payload_present": truthy(message.get("payload_present", message.get("has_payload", True))),
    }


def normalize_agent_workflow_inbox_message_kind(value: Any) -> str:
    kind = (optional_string(value) or "completion").strip().lower().replace("-", "_")
    aliases = {
        "subagent_completion": "completion",
        "sub_agent_completion": "completion",
        "child_completion": "completion",
        "done": "completion",
        "finished": "completion",
    }
    kind = aliases.get(kind, kind)
    return kind if kind in {"completion", "status", "error", "other"} else "other"


def normalize_agent_workflow_child_turn(turn: dict[str, Any], ordinal: int) -> dict[str, Any]:
    turn_id = optional_string(turn.get("id") or turn.get("turn_id"))
    has_output = truthy(turn.get("has_output", turn.get("output_present", True)))
    output_tokens = optional_int(turn.get("output_tokens"))
    empty = truthy(turn.get("empty")) or (output_tokens == 0 if output_tokens is not None else not has_output)
    return {
        "ordinal": ordinal,
        "turn_id_hash": stable_text_hash(turn_id) if turn_id else None,
        "has_output": has_output,
        "empty": empty,
        "transcript_only": truthy(turn.get("transcript_only")),
    }


def evaluate_agent_workflow_stream_boundaries(boundaries: dict[str, Any]) -> dict[str, Any]:
    """Validate streamed tool-call/result boundaries without exporting event bodies."""

    required = truthy(boundaries.get("required"))
    raw_events = boundaries.get("events") if isinstance(boundaries.get("events"), list) else []
    events = [event for event in raw_events if isinstance(event, dict)]
    allowed_item_ids = set(string_list(boundaries.get("allowed_item_ids")))
    allowed_call_ids = set(string_list(boundaries.get("expected_tool_call_ids")))
    items: list[dict[str, Any]] = []
    completed_call_ids: set[str] = set()
    observed_call_ids: set[str] = set()

    for index, event in enumerate(events, start=1):
        event_id = optional_string(event.get("id") or event.get("event_id"))
        call_id = optional_string(event.get("tool_call_id") or event.get("call_id"))
        item_id = optional_string(event.get("item_id"))
        phase = normalize_streamed_tool_boundary_phase(event.get("phase") or event.get("type"))
        stream_state = normalize_streamed_tool_boundary_state(event.get("stream_state") or event.get("state"))
        refs = string_list(event.get("evidence_refs"))
        has_url_ref = any(is_url_like(ref) for ref in refs)
        unknown_item_ref = bool(item_id and allowed_item_ids and item_id not in allowed_item_ids)
        unknown_evidence_ref_count = sum(1 for ref in refs if allowed_item_ids and ref not in allowed_item_ids)
        result_payload = event.get("result_json", event.get("result"))
        strict_json = stream_state != "complete" or phase != "tool_result" or value_is_strict_json(result_payload)

        if call_id:
            observed_call_ids.add(call_id)
        if phase == "tool_result" and stream_state == "complete" and call_id:
            completed_call_ids.add(call_id)

        if has_url_ref:
            failure_mode = "streamed_tool_boundary_url_ref"
        elif unknown_item_ref or unknown_evidence_ref_count:
            failure_mode = "streamed_tool_boundary_unknown_item_ref"
        elif not strict_json:
            failure_mode = "streamed_tool_boundary_non_json_result"
        else:
            failure_mode = "none"

        items.append(
            {
                "ordinal": index,
                "event_id_hash": stable_text_hash(event_id) if event_id else None,
                "tool_call_id_hash": stable_text_hash(call_id) if call_id else None,
                "item_id": item_id,
                "phase": phase,
                "stream_state": stream_state,
                "strict_json": strict_json,
                "has_url_ref": has_url_ref,
                "unknown_item_ref": unknown_item_ref,
                "unknown_evidence_ref_count": unknown_evidence_ref_count,
                "passed": failure_mode == "none",
                "failure_mode": failure_mode,
            }
        )

    missing_result_count = len(allowed_call_ids - completed_call_ids) if allowed_call_ids else 0
    failed_items = [item for item in items if not item["passed"]]
    if required and not events:
        failure_mode = "streamed_tool_boundaries_missing"
    elif failed_items:
        failure_mode = str(failed_items[0]["failure_mode"])
    elif missing_result_count:
        failure_mode = "streamed_tool_result_missing"
    else:
        failure_mode = "none"

    return {
        "required": required,
        "passed": failure_mode == "none",
        "failure_mode": failure_mode,
        "event_count": len(items),
        "partial_event_count": sum(1 for item in items if item["stream_state"] == "partial"),
        "complete_event_count": sum(1 for item in items if item["stream_state"] == "complete"),
        "tool_call_count": sum(1 for item in items if item["phase"] == "tool_call"),
        "tool_result_count": sum(1 for item in items if item["phase"] == "tool_result"),
        "observed_tool_call_count": len(observed_call_ids),
        "completed_tool_call_count": len(completed_call_ids),
        "expected_tool_call_count": len(allowed_call_ids),
        "missing_result_count": missing_result_count,
        "invalid_json_event_count": sum(1 for item in items if not item["strict_json"]),
        "url_ref_event_count": sum(1 for item in items if item["has_url_ref"]),
        "unknown_ref_event_count": sum(
            1 for item in items if item["unknown_item_ref"] or int(item["unknown_evidence_ref_count"]) > 0
        ),
        "items": items,
        "policy": {
            "complete_tool_results_require_strict_json": True,
            "evidence_refs_must_be_item_ids": True,
            "url_refs_allowed": False,
            "raw_stream_events_exported": False,
            "raw_tool_result_bodies_exported": False,
        },
    }


def normalize_streamed_tool_boundary_phase(value: Any) -> str:
    phase = (optional_string(value) or "message").strip().lower().replace("-", "_")
    aliases = {
        "function_call": "tool_call",
        "function_call_delta": "tool_call",
        "tool_call_delta": "tool_call",
        "tool_result_delta": "tool_result",
        "tool_output": "tool_result",
        "message_delta": "message",
    }
    phase = aliases.get(phase, phase)
    return phase if phase in {"message", "tool_call", "tool_result"} else "other"


def normalize_streamed_tool_boundary_state(value: Any) -> str:
    state = (optional_string(value) or "complete").strip().lower().replace("-", "_")
    if state in {"delta", "partial", "streaming"}:
        return "partial"
    if state in {"complete", "completed", "final"}:
        return "complete"
    return "other"


def value_is_strict_json(value: Any) -> bool:
    if isinstance(value, (dict, list)):
        return True
    if not isinstance(value, str):
        return False
    try:
        json.loads(value)
    except json.JSONDecodeError:
        return False
    return True


def is_url_like(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def evaluate_agent_workflow_observations(observations: list[Any]) -> dict[str, Any]:
    """Classify runner observations without letting flaky probes become silent gates."""

    items: list[dict[str, Any]] = []
    for index, observation in enumerate(observations, start=1):
        if not isinstance(observation, dict):
            continue
        raw_id = optional_string(observation.get("id") or observation.get("name"))
        load_bearing = truthy(observation.get("load_bearing", True))
        reliable = truthy(observation.get("reliable", True))
        observed = truthy(observation.get("observed", observation.get("passed", True)))
        if load_bearing and not reliable:
            failure_mode = "unreliable_load_bearing_observation"
        elif load_bearing and not observed:
            failure_mode = "load_bearing_observation_failed"
        else:
            failure_mode = "none"
        items.append(
            {
                "ordinal": index,
                "id_hash": stable_text_hash(raw_id) if raw_id else None,
                "phase": normalize_agent_workflow_observation_phase(observation.get("phase")),
                "load_bearing": load_bearing,
                "reliable": reliable,
                "observed": observed,
                "passed": failure_mode == "none",
                "failure_mode": failure_mode,
            }
        )

    failed_load_bearing = [item for item in items if item["load_bearing"] and not item["passed"]]
    unreliable_non_load_bearing = [item for item in items if not item["load_bearing"] and not item["reliable"]]
    if not failed_load_bearing:
        failure_mode = "none"
    elif any(item["failure_mode"] == "unreliable_load_bearing_observation" for item in failed_load_bearing):
        failure_mode = "unreliable_load_bearing_observation"
    else:
        failure_mode = "load_bearing_observation_failed"

    return {
        "count": len(items),
        "load_bearing_count": sum(1 for item in items if item["load_bearing"]),
        "non_load_bearing_count": sum(1 for item in items if not item["load_bearing"]),
        "unreliable_non_load_bearing_count": len(unreliable_non_load_bearing),
        "failed_load_bearing_count": len(failed_load_bearing),
        "passed": not failed_load_bearing,
        "failure_mode": failure_mode,
        "items": items,
        "raw_observation_ids_exported": False,
        "raw_observation_bodies_exported": False,
    }


def normalize_agent_workflow_observation_phase(value: Any) -> str:
    phase = (optional_string(value) or "unspecified").strip().lower().replace("-", "_")
    allowed = {
        "intake",
        "midflight",
        "recovery",
        "replay",
        "report",
        "teardown",
        "validation",
        "unspecified",
    }
    return phase if phase in allowed else "other"


def evaluate_agent_workflow_recovery_handoff(
    recovery: dict[str, Any],
    *,
    rollback_available: bool,
    rollback_ref: str | None,
    rollback_artifact: str | None,
    validation_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate operator replay/recovery metadata without exporting command bodies."""

    required = truthy(recovery.get("required"))
    operator_required = truthy(recovery.get("operator_required", True))
    commands = string_list(recovery.get("commands"))
    replay_command = optional_string(recovery.get("replay_command"))
    validation_command_names = [str(check["name"]) for check in validation_checks if optional_string(check.get("name"))]
    command_count = len(commands)
    replay_ready = bool(replay_command or validation_command_names)
    ready = rollback_available and (not required or (command_count > 0 and replay_ready))

    blockers: list[str] = []
    if required and not rollback_available:
        blockers.append("rollback_missing")
    if required and command_count == 0:
        blockers.append("recovery_commands_missing")
    if required and not replay_ready:
        blockers.append("replay_command_missing")

    return {
        "required": required,
        "ready": ready,
        "operator_required": operator_required,
        "blockers": blockers,
        "rollback_ref_hash": stable_text_hash(rollback_ref) if rollback_ref else None,
        "rollback_artifact_hash": stable_text_hash(rollback_artifact) if rollback_artifact else None,
        "command_count": command_count,
        "command_hashes": [stable_text_hash(command) for command in commands],
        "replay_ready": replay_ready,
        "replay_command_hash": stable_text_hash(replay_command) if replay_command else None,
        "validation_command_count": len(validation_command_names),
        "validation_command_hashes": [stable_text_hash(name) for name in validation_command_names],
        "raw_recovery_commands_exported": False,
        "raw_replay_command_exported": False,
        "raw_rollback_refs_exported": False,
    }


def build_agent_workflow_control_plane(
    *,
    task_id: str,
    plan_steps: list[Any],
    runner_invoked: bool,
    state_transitions: list[dict[str, Any]],
    validation_gate: str,
    validation_checks: list[dict[str, Any]],
    rollback_available: bool,
    recovery_handoff: dict[str, Any],
    observation_result: dict[str, Any],
    stream_boundary_result: dict[str, Any],
    inbox_result: dict[str, Any],
    report_artifacts: dict[str, Any],
    source_path: Path,
) -> dict[str, Any]:
    """Summarize intake, mid-flight, recovery, replay, and report readiness."""

    report_path = optional_string(report_artifacts.get("report_path"))
    replay_path = optional_string(report_artifacts.get("replay_path"))
    report_contract = evaluate_agent_workflow_report_contract(
        report_artifacts,
        required=validation_gate == "runner-harness-control-plane",
    )
    intake_ready = bool(task_id and plan_steps)
    midflight_ready = (
        runner_invoked
        and bool(state_transitions)
        and bool(stream_boundary_result["passed"])
        and bool(inbox_result["passed"])
    )
    recovery_ready = rollback_available and bool(recovery_handoff.get("ready", True))
    replay_ready = bool(validation_gate and validation_checks) and bool(recovery_handoff.get("replay_ready", True))
    report_ready = bool(report_contract["passed"])
    stages = {
        "intake": intake_ready,
        "midflight": midflight_ready,
        "recovery": recovery_ready,
        "replay": replay_ready,
        "report": report_ready,
    }
    missing_stages = [stage for stage, ready in stages.items() if not ready]

    if missing_stages:
        failure_mode = "control_plane_stage_missing"
    elif not report_contract["passed"]:
        failure_mode = str(report_contract["failure_mode"])
    elif not observation_result["passed"]:
        failure_mode = str(observation_result["failure_mode"])
    elif not stream_boundary_result["passed"]:
        failure_mode = str(stream_boundary_result["failure_mode"])
    elif not inbox_result["passed"]:
        failure_mode = str(inbox_result["failure_mode"])
    else:
        failure_mode = "none"

    return {
        "surface": "runner_harness_control_plane",
        "stage_count": len(stages),
        "complete": (
            not missing_stages
            and observation_result["passed"]
            and stream_boundary_result["passed"]
            and inbox_result["passed"]
        ),
        "failure_mode": failure_mode,
        "stages": {
            stage: {
                "ready": ready,
                "status": "recorded" if ready else "missing",
            }
            for stage, ready in stages.items()
        },
        "missing_stages": missing_stages,
        "replay": {
            "fixture_source_hash": stable_text_hash(source_path.as_posix()),
            "validation_gate_recorded": bool(validation_gate),
            "validation_check_count": len(validation_checks),
            "replay_artifact_hash": stable_text_hash(replay_path) if replay_path else None,
        },
        "recovery": recovery_handoff,
        "report": {
            "report_recorded": report_ready,
            "report_artifact_hash": stable_text_hash(report_path) if report_path else None,
            "section_contract": report_contract,
            "raw_artifact_paths_exported": False,
        },
        "observation_contract": {
            "load_bearing_count": observation_result["load_bearing_count"],
            "non_load_bearing_count": observation_result["non_load_bearing_count"],
            "unreliable_non_load_bearing_count": observation_result["unreliable_non_load_bearing_count"],
            "failed_load_bearing_count": observation_result["failed_load_bearing_count"],
            "flaky_observations_allowed_only_when_non_load_bearing": (
                observation_result["failed_load_bearing_count"] == 0
            ),
        },
        "stream_boundary_contract": {
            "required": stream_boundary_result["required"],
            "passed": stream_boundary_result["passed"],
            "failure_mode": stream_boundary_result["failure_mode"],
            "event_count": stream_boundary_result["event_count"],
            "partial_event_count": stream_boundary_result["partial_event_count"],
            "complete_event_count": stream_boundary_result["complete_event_count"],
            "missing_result_count": stream_boundary_result["missing_result_count"],
            "invalid_json_event_count": stream_boundary_result["invalid_json_event_count"],
            "url_ref_event_count": stream_boundary_result["url_ref_event_count"],
            "unknown_ref_event_count": stream_boundary_result["unknown_ref_event_count"],
        },
        "inbox_delivery_contract": {
            "required": inbox_result["required"],
            "passed": inbox_result["passed"],
            "failure_mode": inbox_result["failure_mode"],
            "expected_completion_count": inbox_result["expected_completion_count"],
            "completion_message_count": inbox_result["completion_message_count"],
            "parent_woken": inbox_result["parent_woken"],
            "transcript_only_turn_count": inbox_result["transcript_only_turn_count"],
            "empty_turn_count": inbox_result["empty_turn_count"],
            "child_lifecycle_degraded": inbox_result["child_lifecycle"]["degraded"],
            "recovery": {
                "transcript_polling_available": inbox_result["recovery"]["transcript_polling_available"],
                "transcript_polling_required": inbox_result["recovery"]["transcript_polling_required"],
                "cleanup_required": inbox_result["recovery"]["cleanup_required"],
                "cleanup_blocked": inbox_result["recovery"]["cleanup_blocked"],
                "operator_action": inbox_result["recovery"]["operator_action"],
            },
        },
    }


def evaluate_agent_workflow_report_contract(
    report_artifacts: dict[str, Any],
    *,
    required: bool,
) -> dict[str, Any]:
    """Require enough report structure for an operator to audit and replay a run."""

    report_recorded = truthy(report_artifacts.get("report_recorded")) or bool(
        optional_string(report_artifacts.get("report_path"))
    )
    required = required or report_recorded or "report_sections" in report_artifacts
    raw_sections = report_artifacts.get("report_sections")
    sections = (
        sorted({normalize_report_section(section) for section in raw_sections if optional_string(section)})
        if isinstance(raw_sections, list)
        else []
    )
    missing_sections = (
        [section for section in AGENT_WORKFLOW_REPORT_REQUIRED_SECTIONS if section not in sections] if required else []
    )
    passed = (not required) or (report_recorded and not missing_sections)
    if required and not report_recorded:
        failure_mode = "report_artifact_missing"
    elif required and missing_sections:
        failure_mode = "report_sections_missing"
    else:
        failure_mode = "none"

    return {
        "required": required,
        "required_sections": list(AGENT_WORKFLOW_REPORT_REQUIRED_SECTIONS),
        "recorded_section_count": len(sections),
        "recorded_sections": sections,
        "missing_sections": missing_sections,
        "passed": passed,
        "failure_mode": failure_mode,
        "raw_report_body_exported": False,
    }


def normalize_report_section(value: Any) -> str:
    section = (optional_string(value) or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "changed_file": "changed_files",
        "changes": "changed_files",
        "files": "changed_files",
        "replay_command": "replay",
        "review_note": "review_notes",
        "rollback_point": "rollback",
        "tests": "validation",
        "verification": "validation",
    }
    return aliases.get(section, section)


def build_agent_workflow_state_transitions(
    *,
    plan_steps: list[Any],
    oneshot_marker_ready: bool = True,
    oneshot_marker_required: bool = False,
    runner_invoked: bool,
    validation_checks: list[dict[str, Any]],
    failure_mode: str,
    rollback_available: bool,
) -> list[dict[str, Any]]:
    transitions = [
        {"state": "planned", "outcome": "passed" if plan_steps else "failed"},
    ]
    if oneshot_marker_required:
        transitions.append(
            {
                "state": "oneshot_marker_checked",
                "outcome": "passed" if oneshot_marker_ready else "failed",
            }
        )
    transitions.append({"state": "runner_invoked", "outcome": "passed" if runner_invoked else "failed"})
    if runner_invoked:
        transitions.append(
            {
                "state": "runner_completed",
                "outcome": "passed" if failure_mode not in {"timeout", "nonzero_exit"} else "failed",
            }
        )
    transitions.append(
        {
            "state": "validation_recorded",
            "outcome": "passed"
            if validation_checks and failure_mode in {"none", "timeout", "nonzero_exit"}
            else "failed",
        }
    )
    transitions.append(
        {
            "state": "rollback_checked",
            "outcome": "passed" if rollback_available else "failed",
        }
    )
    transitions.append(
        {
            "state": "completed",
            "outcome": "passed" if failure_mode == "none" else "failed",
        }
    )
    return transitions


def evaluate_agent_workflow_oneshot_marker(marker: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the controller-visible one-shot marker without exporting local paths."""

    required = truthy(marker.get("required"))
    present = truthy(marker.get("present"))
    path = optional_string(marker.get("path"))
    stale = truthy(marker.get("stale"))
    ready = (not required) or (present and not stale)
    if not required:
        failure_mode = "not_required"
    elif not present:
        failure_mode = "oneshot_marker_missing"
    elif stale:
        failure_mode = "oneshot_marker_stale"
    else:
        failure_mode = "none"
    return {
        "required": required,
        "present": present,
        "stale": stale,
        "ready": ready,
        "failure_mode": failure_mode,
        "path_hash": stable_text_hash(path) if path else None,
        "raw_path_exported": False,
    }


def evaluate_agent_workflow_lifecycle(
    lifecycle: dict[str, Any],
    state_transitions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check an optional harness-style lifecycle trace against controller states."""

    expected_phases = string_list(lifecycle.get("expected_phases")) or [
        str(transition["state"]) for transition in state_transitions
    ]
    observed_phases = string_list(lifecycle.get("observed_phases")) or [
        str(transition["state"]) for transition in state_transitions
    ]
    missing_phases = [phase for phase in expected_phases if phase not in observed_phases]
    unexpected_phases = [phase for phase in observed_phases if phase not in expected_phases]
    ordered = phases_are_ordered(expected_phases, observed_phases)
    completed = bool(observed_phases) and not missing_phases
    passed = completed and ordered and not unexpected_phases
    if not completed:
        failure_mode = "missing_lifecycle_phase"
    elif not ordered:
        failure_mode = "lifecycle_out_of_order"
    elif unexpected_phases:
        failure_mode = "unexpected_lifecycle_phase"
    else:
        failure_mode = "none"
    return {
        "expected_phases": expected_phases,
        "observed_phases": observed_phases,
        "complete": completed,
        "ordered": ordered,
        "unexpected_phases": unexpected_phases,
        "missing_phases": missing_phases,
        "passed": passed,
        "failure_mode": failure_mode,
    }


def phases_are_ordered(expected_phases: list[str], observed_phases: list[str]) -> bool:
    cursor = -1
    for phase in expected_phases:
        try:
            cursor = observed_phases.index(phase, cursor + 1)
        except ValueError:
            return False
    return True


def adapt_proposal_interpretation_fixture(raw_input: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    """Run proposal interpretation from a local harness fixture and emit strict JSON."""

    from blackhole_agent.proposal_eval import run_proposal_replay_case
    from blackhole_agent.proposal_synthesis import build_proposal_evidence_package, review_llm_proposal_response

    case = dict(raw_input)
    case.setdefault("name", source_path.stem)
    digest = raw_input.get("digest") if isinstance(raw_input.get("digest"), dict) else {}
    raw_response = raw_input.get("raw_response")
    raw_text = json.dumps(raw_response) if isinstance(raw_response, dict) else str(raw_response or "")
    options = raw_input.get("options") if isinstance(raw_input.get("options"), dict) else {}
    evidence_package = build_proposal_evidence_package(
        digest,
        self_model_snapshot=options.get("self_model_snapshot")
        if isinstance(options.get("self_model_snapshot"), dict)
        else None,
        max_items=int(options.get("max_items") or 20),
        max_item_text_chars=int(options.get("max_item_text_chars") or 1200),
        max_self_model_chars=int(options.get("max_self_model_chars") or 4000),
    )
    review = review_llm_proposal_response(
        raw_text,
        evidence_package,
        mode=str(raw_input.get("mode") or "hybrid"),
    )
    result = run_proposal_replay_case(case)
    accepted_candidates = [
        {
            "proposal_id": str(candidate.get("proposal_id") or ""),
            "kind": str(candidate.get("kind") or ""),
            "evidence_refs": [str(ref) for ref in candidate.get("evidence_refs", [])],
            "validation_task": str(candidate.get("validation_task") or ""),
            "uncertainty": str(candidate.get("uncertainty") or ""),
        }
        for candidate in review.accepted_candidates
    ]
    supplied_item_ids = digest_item_ids(digest)
    selected_item_ids = [str(item_id) for item_id in result.selected_item_ids]
    evidence_ref_violations = collect_evidence_ref_violations(
        accepted_candidates,
        supplied_item_ids=supplied_item_ids,
        selected_item_ids=selected_item_ids,
    )
    passed = result.passed and not evidence_ref_violations
    proposals = raw_response.get("proposals") if isinstance(raw_response, dict) else []
    proposal_count = len(proposals) if isinstance(proposals, list) else 0
    max_proposals = int(evidence_package.get("policy", {}).get("max_proposals") or 5)
    selected_route_hints = sorted(
        {
            str(route_hint)
            for item in evidence_package.get("items", [])
            if str(item.get("item_id") or "") in selected_item_ids
            for route_hint in item.get("route_hints", [])
            if str(route_hint).strip()
        }
    )

    return {
        "schema_version": 1,
        "behavior": "proposal_interpretation",
        "name": result.name,
        "passed": passed,
        "failure_mode": "none" if passed else "proposal_interpretation_failed",
        "review_status": result.review_status,
        "review_reason": review.reason,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "proposal_policy": {
            "max_proposals": max_proposals,
            "supplied_proposal_count": proposal_count,
            "within_max_proposals": proposal_count <= max_proposals,
        },
        "selected_item_ids": selected_item_ids,
        "truncated_item_ids": [str(item_id) for item_id in result.truncated_item_ids],
        "evidence_ref_policy": {
            "citation_scope": "selected_item_ids_only",
            "supplied_item_ids": supplied_item_ids,
            "selected_item_ids": selected_item_ids,
            "url_refs_allowed": False,
        },
        "route_hint_policy": {
            "allowed_route_hints": [
                str(route_hint) for route_hint in evidence_package.get("policy", {}).get("allowed_route_hints", [])
            ],
            "validation_lanes": {
                str(route_hint): [str(lane) for lane in lanes]
                for route_hint, lanes in evidence_package.get("policy", {})
                .get("route_hint_validation_lanes", {})
                .items()
            },
            "selected_route_hints": selected_route_hints,
        },
        "safety_boundary": summarize_proposal_safety_boundary(result.proposal_controls),
        "provider_runtime_control": summarize_proposal_provider_runtime_control(
            passed=passed,
            selected_route_hints=selected_route_hints,
            proposal_controls=result.proposal_controls,
            proposal_validation_preflights=result.proposal_validation_preflights,
        ),
        "accepted_candidates": accepted_candidates,
        "evidence_ref_violations": evidence_ref_violations,
        "proposal_controls": result.proposal_controls,
        "proposal_validation_preflights": result.proposal_validation_preflights,
        "rejected_errors": result.rejected_errors,
        "failures": result.failures,
    }


def accepted_candidate_refs(raw_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Return accepted proposal IDs and evidence refs after deterministic review."""

    from blackhole_agent.proposal_synthesis import build_proposal_evidence_package, review_llm_proposal_response

    digest = raw_input.get("digest")
    if not isinstance(digest, dict):
        return []
    raw_response = raw_input.get("raw_response")
    raw_text = json.dumps(raw_response) if isinstance(raw_response, dict) else str(raw_response or "")
    options = raw_input.get("options") if isinstance(raw_input.get("options"), dict) else {}
    evidence_package = build_proposal_evidence_package(
        digest,
        self_model_snapshot=options.get("self_model_snapshot")
        if isinstance(options.get("self_model_snapshot"), dict)
        else None,
        max_items=int(options.get("max_items") or 20),
        max_item_text_chars=int(options.get("max_item_text_chars") or 1200),
        max_self_model_chars=int(options.get("max_self_model_chars") or 4000),
    )
    review = review_llm_proposal_response(
        raw_text,
        evidence_package,
        mode=str(raw_input.get("mode") or "hybrid"),
    )
    return [
        {
            "proposal_id": str(candidate.get("proposal_id") or ""),
            "kind": str(candidate.get("kind") or ""),
            "evidence_refs": [str(ref) for ref in candidate.get("evidence_refs", [])],
            "validation_task": str(candidate.get("validation_task") or ""),
            "uncertainty": str(candidate.get("uncertainty") or ""),
        }
        for candidate in review.accepted_candidates
    ]


def summarize_proposal_safety_boundary(proposal_controls: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize high-risk proposal routing without exposing raw proposal bodies."""

    review_only_ids: list[str] = []
    unsafe_drift_ids: list[str] = []
    for proposal_id, controls in proposal_controls.items():
        risk_flags = {str(flag) for flag in controls.get("risk_flags", []) if str(flag).strip()}
        boundary_flags = risk_flags & SAFETY_BOUNDARY_REVIEW_FLAGS
        if not boundary_flags:
            continue
        implementation_scope = str(controls.get("implementation_scope") or "")
        validation_gate = str(controls.get("validation_gate") or "")
        if implementation_scope == "reviewable_proposal_only" and validation_gate.endswith("-human-review"):
            review_only_ids.append(str(proposal_id))
        else:
            unsafe_drift_ids.append(str(proposal_id))

    return {
        "review_only_risk_flags": sorted(SAFETY_BOUNDARY_REVIEW_FLAGS),
        "review_only_proposal_ids": sorted(review_only_ids),
        "review_only_count": len(review_only_ids),
        "unsafe_drift_proposal_ids": sorted(unsafe_drift_ids),
        "unsafe_drift_count": len(unsafe_drift_ids),
        "offensive_behavior_local_execution": False,
    }


def summarize_proposal_provider_runtime_control(
    *,
    passed: bool,
    selected_route_hints: list[str],
    proposal_controls: dict[str, dict[str, Any]],
    proposal_validation_preflights: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return body-free provider/runtime replay control for accepted proposal lanes."""

    boundary = summarize_proposal_safety_boundary(proposal_controls)
    accepted_local_ids = sorted(
        proposal_id
        for proposal_id, controls in proposal_controls.items()
        if str(controls.get("implementation_scope") or "") == "local_validation_candidate"
    )
    validation_gap_ids = sorted(
        proposal_id
        for proposal_id, preflight in proposal_validation_preflights.items()
        if str(preflight.get("status") or "") != "ready"
    )
    selected_route_hints = sorted(dict.fromkeys(selected_route_hints))
    unsafe_drift = int(boundary["unsafe_drift_count"]) > 0
    ready_for_local_replay = passed and bool(accepted_local_ids) and not validation_gap_ids and not unsafe_drift
    recovery_hint_codes: list[str] = []
    if not passed:
        recovery_hint_codes.append("proposal_interpretation_failed")
    if validation_gap_ids:
        recovery_hint_codes.append("proposal_validation_gap")
    if unsafe_drift:
        recovery_hint_codes.append("proposal_safety_boundary_drift")

    return {
        "controller_surface": "proposal_interpretation_provider_runtime_control",
        "decision": "ready_for_local_replay" if ready_for_local_replay else "blocked_before_local_replay",
        "reason": "none" if ready_for_local_replay else "proposal_interpretation_not_ready",
        "accepted_local_validation_candidate_count": len(accepted_local_ids),
        "accepted_local_validation_candidate_ids": accepted_local_ids,
        "validation_gap_proposal_ids": validation_gap_ids,
        "selected_route_hints": selected_route_hints,
        "provider_runtime_preflight_required": bool(
            accepted_local_ids and set(selected_route_hints) & {"agent_harness_eval", "skill_route_discovery"}
        ),
        "recovery_hint_codes": recovery_hint_codes,
        "replay_commands": [
            "pytest tests/test_harness_eval.py -q -k proposal_interpretation",
            PROVIDER_RUNTIME_PREFLIGHT_COMMAND,
            PROVIDER_RUNTIME_RECOVERY_SUMMARY_COMMAND,
        ],
        "local_validation_required": True,
        "body_free_diagnostics_only": True,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_preflight_inputs_exported": False,
        "raw_diagnostics_exported": False,
    }


def digest_item_ids(digest: Any) -> list[str]:
    if not isinstance(digest, dict) or not isinstance(digest.get("items"), list):
        return []
    return [
        str(item.get("item_id"))
        for item in digest["items"]
        if isinstance(item, dict) and str(item.get("item_id") or "").strip()
    ]


def collect_evidence_ref_violations(
    accepted_candidates: list[dict[str, Any]],
    *,
    supplied_item_ids: list[str],
    selected_item_ids: list[str],
) -> list[dict[str, Any]]:
    supplied = set(supplied_item_ids)
    selected = set(selected_item_ids)
    violations: list[dict[str, Any]] = []
    for candidate in accepted_candidates:
        proposal_id = str(candidate.get("proposal_id") or "")
        refs = [str(ref) for ref in candidate.get("evidence_refs", [])]
        unknown_refs = sorted(set(refs) - supplied)
        non_selected_refs = sorted(set(refs) - selected)
        if unknown_refs or non_selected_refs:
            violations.append(
                {
                    "proposal_id": proposal_id,
                    "unknown_refs": unknown_refs,
                    "non_selected_refs": non_selected_refs,
                }
            )
    return violations


def evaluate_fixture_assertion(
    assertion: Any,
    output: dict[str, Any],
    *,
    source_path: Path,
) -> HarnessEvalAssertionResult:
    if not isinstance(assertion, dict):
        raise ValueError(f"{source_path} assertion must be a JSON object")
    path = optional_string(assertion.get("path"))
    if not path:
        raise ValueError(f"{source_path} assertion path is required")
    if "equals" not in assertion:
        raise ValueError(f"{source_path} assertion for {path} must declare equals")

    expected = assertion["equals"]
    actual = value_at_path(output, path)
    passed = actual == expected
    return HarnessEvalAssertionResult(
        path=path,
        expected=expected,
        actual=actual,
        passed=passed,
        failure_mode="none" if passed else "equals_mismatch",
    )


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def summarize_harness_run(payload: dict[str, Any], *, source_path: Path | None = None) -> HarnessRunSummary:
    """Summarize one run artifact without retaining private task or output bodies."""

    run_id = str(payload.get("run_id") or (source_path.stem if source_path else "unknown-run"))
    harness = str(payload.get("harness") or payload.get("kernel") or infer_harness(payload, source_path))
    model = optional_string(payload.get("model") or payload.get("model_name"))
    variant = str(payload.get("variant") or payload.get("variant_id") or variant_label(harness, model))
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    returncode = optional_int(payload.get("returncode") or payload.get("exit_code"))
    timed_out = bool(payload.get("timed_out") or payload.get("timeout"))
    privacy_review_required = requires_privacy_review(payload)
    failure_mode = (
        "privacy_review_required"
        if privacy_review_required
        else failure_mode_from_payload(payload, returncode=returncode, timed_out=timed_out)
    )
    validation_gate = (
        PRIVACY_REVIEW_GATE
        if privacy_review_required
        else optional_string(payload.get("validation_gate")) or "local-harness-summary"
    )
    gate_outcome = (
        "review_required" if privacy_review_required else optional_string(payload.get("gate_outcome")) or "passed"
    )

    return HarnessRunSummary(
        run_id=run_id,
        harness=harness,
        variant=variant,
        model=model,
        task_hash=None
        if privacy_review_required
        else first_hash(
            payload,
            ("task_hash", "prompt_hash", "input_hash"),
            ("task", "prompt", "prompt_body", "input"),
        ),
        output_hash=None
        if privacy_review_required
        else first_hash(
            payload,
            ("output_hash", "last_message_hash", "response_hash"),
            ("last_message", "output", "response", "stdout_tail", "stderr_tail"),
        ),
        quality_score=optional_float(payload.get("quality_score") or payload.get("score")),
        cost_usd=optional_float(payload.get("cost_usd") or payload.get("cost") or usage.get("cost_usd")),
        elapsed_seconds=optional_float(
            payload.get("elapsed_seconds") or payload.get("duration_seconds") or payload.get("latency_seconds")
        ),
        tool_calls=optional_int(payload.get("tool_calls") or usage.get("tool_calls")),
        input_tokens=optional_int(
            payload.get("input_tokens") or usage.get("input_tokens") or usage.get("prompt_tokens")
        ),
        output_tokens=optional_int(
            payload.get("output_tokens") or usage.get("output_tokens") or usage.get("completion_tokens")
        ),
        total_tokens=optional_int(payload.get("total_tokens") or usage.get("total_tokens")),
        returncode=returncode,
        timed_out=timed_out,
        failure_mode=failure_mode,
        validation_gate=validation_gate,
        gate_outcome=gate_outcome,
    )


def aggregate_harness_summaries(summaries: list[HarnessRunSummary]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[HarnessRunSummary]] = {}
    for summary in summaries:
        grouped.setdefault((summary.harness, summary.variant), []).append(summary)

    aggregates: list[dict[str, Any]] = []
    for (harness, variant), runs in sorted(grouped.items()):
        aggregates.append(
            {
                "harness": harness,
                "variant": variant,
                "run_count": len(runs),
                "success_count": sum(1 for run in runs if run.failure_mode == "none"),
                "failure_modes": sorted({run.failure_mode for run in runs if run.failure_mode != "none"}),
                "avg_quality_score": average(run.quality_score for run in runs),
                "avg_cost_usd": average(run.cost_usd for run in runs),
                "avg_elapsed_seconds": average(run.elapsed_seconds for run in runs),
                "avg_tool_calls": average(run.tool_calls for run in runs),
                "avg_total_tokens": average(run.total_tokens for run in runs),
            }
        )
    return aggregates


def first_hash(payload: dict[str, Any], hash_keys: tuple[str, ...], body_keys: tuple[str, ...]) -> str | None:
    for key in hash_keys:
        value = optional_string(payload.get(key))
        if value:
            return value
    for key in body_keys:
        value = optional_string(payload.get(key))
        if value:
            return stable_text_hash(value)
    return None


def stable_text_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_hash(value: Any) -> str:
    return stable_text_hash(json.dumps(value, sort_keys=True, separators=(",", ":")))


def value_at_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if 0 <= index < len(current):
                current = current[index]
                continue
        return None
    return current


def failure_mode_from_payload(payload: dict[str, Any], *, returncode: int | None, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    explicit_failure = optional_string(payload.get("failure_mode") or payload.get("error_type"))
    if explicit_failure:
        return explicit_failure
    if returncode not in (None, 0):
        return "nonzero_exit"
    if payload.get("error"):
        return "error"
    return "none"


def requires_privacy_review(payload: dict[str, Any]) -> bool:
    """Detect fixtures that must stay review-only without hashing private bodies."""

    for key in PRIVACY_REVIEW_FLAG_KEYS:
        if truthy(payload.get(key)):
            return True
    validation_gate = optional_string(payload.get("validation_gate"))
    if validation_gate == PRIVACY_REVIEW_GATE:
        return True
    validation_task = optional_string(payload.get("validation_task"))
    if validation_task:
        lowered = validation_task.lower()
        return any(
            term in lowered
            for term in ("privacy leakage", "privacy-leakage", "private key", "credential", "pii", "secret")
        )
    return False


def infer_harness(payload: dict[str, Any], source_path: Path | None) -> str:
    command = payload.get("command")
    if isinstance(command, list) and command:
        return str(Path(str(command[0])).name or command[0])
    if source_path:
        return source_path.stem.split("-", 1)[0]
    return "unknown"


def variant_label(harness: str, model: str | None) -> str:
    return f"{harness}:{model}" if model else harness


def average(values: Any) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 6)


def optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)
