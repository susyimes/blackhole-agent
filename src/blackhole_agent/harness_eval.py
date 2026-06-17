"""Privacy-preserving comparison reports and local eval fixtures for agent harness runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    "agent_workflow_route",
    "harness_run_summary",
    "mock_llm_workflow_route",
    "provider_runtime_preflight",
    "proposal_interpretation",
]


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
    if behavior == "agent_workflow_route":
        return evaluate_agent_workflow_route(raw_input, source_path=source_path)
    if behavior == "harness_run_summary":
        return summarize_harness_run(raw_input, source_path=source_path).to_dict()
    if behavior == "mock_llm_workflow_route":
        return evaluate_mock_llm_workflow_route(raw_input, source_path=source_path)
    if behavior == "provider_runtime_preflight":
        return evaluate_provider_runtime_preflight(raw_input, source_path=source_path)
    if behavior == "proposal_interpretation":
        return adapt_proposal_interpretation_fixture(raw_input, source_path=source_path)
    raise ValueError(f"{source_path} has unsupported local harness behavior: {behavior}")


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
    file_tools = raw_input.get("file_tools") if isinstance(raw_input.get("file_tools"), dict) else {}
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
    enough_responses = len(response_results) >= len(steps)
    expectations_passed = bool(response_results) and all(result["expectation_passed"] for result in response_results)
    session_result = evaluate_mock_session_route(session)
    file_tool_result = evaluate_mock_file_tools_route(file_tools)
    usage = aggregate_mock_llm_usage(response_results)
    failure_mode = mock_llm_workflow_failure_mode(
        step_count=len(steps),
        external_calls_attempted=external_calls_attempted,
        multimodal_preflight_ok=multimodal_preflight["ok"],
        multimodal_failure_mode=optional_string(multimodal_preflight["failure_mode"]) or "multimodal_preflight_failed",
        mock_enabled=mock_enabled,
        enough_responses=enough_responses,
        expectations_passed=expectations_passed,
        session_passed=session_result["isolation_passed"],
        file_tools_passed=file_tool_result["all_operations_mocked"]
        and file_tool_result["all_expectations_passed"],
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
            "queue_keys": sorted(response_queues),
            "exhausted": mock_enabled and not enough_responses,
            "usage": usage,
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
        "file_tools": file_tool_result,
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
        results.append(
            {
                "step_id": optional_string(step_data.get("id")) or f"step-{index + 1}",
                "request_key": mock_llm_request_key(step_data, mock_llm=mock_llm),
                "response_key": queue_key,
                "fallback_used": fallback_used,
                "response_hash": stable_text_hash(content),
                "expectation_passed": expect_contains is None or expect_contains in content,
                "tool_call_count": len(response_data.get("tool_calls"))
                if isinstance(response_data.get("tool_calls"), list)
                else 0,
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


def mock_llm_workflow_failure_mode(
    *,
    step_count: int,
    external_calls_attempted: bool,
    multimodal_preflight_ok: bool,
    multimodal_failure_mode: str,
    mock_enabled: bool,
    enough_responses: bool,
    expectations_passed: bool,
    session_passed: bool,
    file_tools_passed: bool,
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
    if not expectations_passed:
        return "expectation_failed"
    if not session_passed:
        return "session_isolation_failed"
    if not file_tools_passed:
        return "file_tool_mock_failed"
    return "none"


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

    provider_name = optional_string(provider.get("name")) or "external-sdk-provider"
    harness = optional_string(provider.get("harness")) or provider_name
    platform_system = (optional_string(runtime.get("platform")) or "").lower()
    cli_path = optional_string(runtime.get("cli_path")) or ""
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

    incompatible_sandbox = (
        sandbox_active
        and platform_system == "darwin"
        and "claude" in provider_name.lower()
        and cli_path.startswith("~/")
        and not install_tree_readable
    )
    degraded = incompatible_sandbox and (override_propagated or auto_degrade)
    blocked = incompatible_sandbox and not degraded
    runner_invoked = not blocked
    diagnostics = build_provider_runtime_diagnostics(
        incompatible_sandbox=incompatible_sandbox,
        degraded=degraded,
        blocked=blocked,
        override_flag=override_flag,
        override_requested=override_requested,
        override_propagated=override_propagated,
        auto_degrade=auto_degrade,
    )

    if blocked:
        route_status = "blocked"
        failure_mode = "sandbox_runtime_preflight_failed"
    elif degraded:
        route_status = "degraded"
        failure_mode = "none"
    else:
        route_status = "passed"
        failure_mode = "none"

    return {
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
            "env_values_recorded": False,
        },
        "runtime": {
            "platform": platform_system or "unknown",
            "cli_path_recorded": False,
            "install_tree_readable": install_tree_readable,
            "supervisor_unwrapped": degraded,
            "native_file_shell_tools_disabled": degraded,
            "runner_invoked": runner_invoked,
        },
        "preflight": {
            "ok": not blocked,
            "degraded": degraded,
            "blocked_before_launch": blocked,
            "diagnostics": diagnostics,
            "diagnostic_count": len(diagnostics),
        },
    }


def build_provider_runtime_diagnostics(
    *,
    incompatible_sandbox: bool,
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
            diagnostics.append(f"{override_flag} reached the provider harness; using degraded unwrapped supervisor mode")
        elif auto_degrade:
            diagnostics.append("provider runtime sandbox is incompatible; using degraded unwrapped supervisor mode")
        diagnostics.append("native provider file and shell tools must remain disabled while outer sandbox tools stay active")
    if blocked:
        diagnostics.append("provider runtime sandbox is incompatible and no degraded startup path was available")
        diagnostics.append(f"add {override_flag} to the runner environment allowlist or enable provider auto-degrade")
    if incompatible_sandbox and not degraded and not blocked:
        diagnostics.append("provider runtime sandbox compatibility could not be classified")
    return diagnostics


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

    runner_invoked = truthy(runner.get("invoked"))
    runner_returncode = optional_int(runner.get("returncode")) if runner_invoked else None
    runner_timed_out = truthy(runner.get("timed_out"))
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

    failure_mode = agent_workflow_failure_mode(
        runner_invoked=runner_invoked,
        runner_returncode=runner_returncode,
        runner_timed_out=runner_timed_out,
        validation_passed=validation_passed,
    )
    route_status = "passed" if failure_mode == "none" else "failed_recoverable" if rollback_available else "failed_unrecoverable"
    state_transitions = build_agent_workflow_state_transitions(
        plan_steps=plan_steps,
        runner_invoked=runner_invoked,
        validation_checks=validation_checks,
        failure_mode=failure_mode,
        rollback_available=rollback_available,
    )

    return {
        "schema_version": 1,
        "behavior": "agent_workflow_route",
        "task_id": task_id,
        "route_status": route_status,
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
        "failure_mode": failure_mode,
    }


def agent_workflow_failure_mode(
    *,
    runner_invoked: bool,
    runner_returncode: int | None,
    runner_timed_out: bool,
    validation_passed: bool,
) -> str:
    if not runner_invoked:
        return "runner_not_invoked"
    if runner_timed_out:
        return "timeout"
    if runner_returncode not in (None, 0):
        return "nonzero_exit"
    if not validation_passed:
        return "validation_failed"
    return "none"


def build_agent_workflow_state_transitions(
    *,
    plan_steps: list[Any],
    runner_invoked: bool,
    validation_checks: list[dict[str, Any]],
    failure_mode: str,
    rollback_available: bool,
) -> list[dict[str, Any]]:
    transitions = [
        {"state": "planned", "outcome": "passed" if plan_steps else "failed"},
        {"state": "runner_invoked", "outcome": "passed" if runner_invoked else "failed"},
    ]
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
            "outcome": "passed" if validation_checks and failure_mode in {"none", "timeout", "nonzero_exit"} else "failed",
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
        "safety_boundary": summarize_proposal_safety_boundary(result.proposal_controls),
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
        input_tokens=optional_int(payload.get("input_tokens") or usage.get("input_tokens") or usage.get("prompt_tokens")),
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
