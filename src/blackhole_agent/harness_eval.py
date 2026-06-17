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
SUPPORTED_LOCAL_HARNESS_BEHAVIORS = [
    "agent_workflow_route",
    "harness_run_summary",
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
    if behavior == "proposal_interpretation":
        return adapt_proposal_interpretation_fixture(raw_input, source_path=source_path)
    raise ValueError(f"{source_path} has unsupported local harness behavior: {behavior}")


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
