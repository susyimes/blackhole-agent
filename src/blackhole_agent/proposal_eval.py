"""Replay-style local checks for frozen proposal evidence packages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blackhole_agent.github_growth import GrowthSignal, clamp_llm_candidates_to_proposals
from blackhole_agent.proposal_synthesis import (
    HIGH_RISK_FLAGS,
    build_proposal_evidence_package,
    review_llm_proposal_response,
)


@dataclass(frozen=True)
class ProposalReplayResult:
    """Result of replaying one frozen proposal interpretation case."""

    name: str
    passed: bool
    failures: list[str]
    review_status: str
    accepted_count: int
    rejected_count: int
    selected_item_ids: list[str]
    truncated_item_ids: list[str]
    proposal_controls: dict[str, dict[str, Any]]
    rejected_errors: list[str]


@dataclass(frozen=True)
class ProposalBenchmarkReport:
    """Benchmark-style aggregate over frozen proposal replay scenarios."""

    suite_name: str
    passed: bool
    case_count: int
    passed_count: int
    failed_count: int
    accepted_count: int
    rejected_count: int
    failure_counts: dict[str, int]
    case_results: list[ProposalReplayResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "case_count": self.case_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "failure_counts": self.failure_counts,
            "case_results": [
                {
                    "name": result.name,
                    "passed": result.passed,
                    "failures": result.failures,
                    "review_status": result.review_status,
                    "accepted_count": result.accepted_count,
                    "rejected_count": result.rejected_count,
                    "selected_item_ids": result.selected_item_ids,
                    "truncated_item_ids": result.truncated_item_ids,
                    "proposal_controls": result.proposal_controls,
                    "rejected_errors": result.rejected_errors,
                }
                for result in self.case_results
            ],
        }


@dataclass(frozen=True)
class ProposalReplayManifestReport:
    """Manifest-level checks over a frozen proposal replay suite."""

    suite_name: str
    passed: bool
    case_count: int
    fixture_names: list[str]
    evidence_urls: list[str]
    failures: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "case_count": self.case_count,
            "fixture_names": self.fixture_names,
            "evidence_urls": self.evidence_urls,
            "failures": self.failures,
        }


def load_proposal_replay_case(path: Path) -> dict[str, Any]:
    """Load a replay case from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    payload.setdefault("name", path.stem)
    return payload


def load_proposal_replay_manifest(path: Path) -> dict[str, Any]:
    """Load a replay-suite manifest from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def validate_proposal_replay_manifest(path: Path) -> ProposalReplayManifestReport:
    """Validate frozen replay fixtures and their declared evidence sources."""

    manifest = load_proposal_replay_manifest(path)
    fixture_dir = path.parent
    failures: list[str] = []
    suite_name = str(manifest.get("suite_name") or path.stem)
    evidence_urls = sorted({str(url) for url in manifest.get("evidence_urls", []) if str(url).strip()})
    case_entries = manifest.get("cases")
    if int(manifest.get("schema_version") or 0) != 1:
        failures.append(f"{suite_name}: schema_version must be 1")
    if not evidence_urls:
        failures.append(f"{suite_name}: evidence_urls must not be empty")
    if not isinstance(case_entries, list) or not case_entries:
        failures.append(f"{suite_name}: cases must be a non-empty list")
        case_entries = []

    fixture_names: list[str] = []
    for index, entry in enumerate(case_entries, start=1):
        if not isinstance(entry, dict):
            failures.append(f"{suite_name}: case entry {index} must be an object")
            continue
        failures.extend(validate_proposal_replay_manifest_case(fixture_dir, entry, suite_name, evidence_urls))
        fixture_name = str(entry.get("name") or entry.get("file") or f"case-{index}")
        fixture_names.append(fixture_name)

    return ProposalReplayManifestReport(
        suite_name=suite_name,
        passed=not failures,
        case_count=len(case_entries),
        fixture_names=fixture_names,
        evidence_urls=evidence_urls,
        failures=failures,
    )


def validate_proposal_replay_manifest_case(
    fixture_dir: Path,
    entry: dict[str, Any],
    suite_name: str,
    manifest_evidence_urls: list[str],
) -> list[str]:
    """Validate one manifest-declared replay case without network access."""

    failures: list[str] = []
    fixture_name = str(entry.get("name") or "")
    fixture_file = str(entry.get("file") or "")
    if not fixture_file:
        return [f"{suite_name}: case {fixture_name or '<unnamed>'} missing file"]
    path = fixture_dir / fixture_file
    if not path.exists():
        return [f"{suite_name}: case {fixture_name or fixture_file} fixture does not exist: {fixture_file}"]

    case = load_proposal_replay_case(path)
    actual_name = str(case.get("name") or path.stem)
    if fixture_name and actual_name != fixture_name:
        failures.append(f"{suite_name}: manifest name {fixture_name!r} does not match fixture name {actual_name!r}")

    result = run_proposal_replay_case(case)
    if not result.passed:
        failures.extend(f"{suite_name}: {failure}" for failure in result.failures)

    expected_status = str(entry.get("expected_review_status") or "")
    if expected_status and result.review_status != expected_status:
        failures.append(
            f"{suite_name}: {actual_name} expected review_status={expected_status!r}, got {result.review_status!r}"
        )

    digest_urls = sorted(source_urls_from_digest(case.get("digest")))
    declared_case_urls = sorted({str(url) for url in entry.get("evidence_urls", []) if str(url).strip()})
    manifest_url_set = set(manifest_evidence_urls)
    digest_url_set = set(digest_urls)
    if not declared_case_urls:
        failures.append(f"{suite_name}: {actual_name} evidence_urls must not be empty")
    unknown_manifest_urls = sorted(set(declared_case_urls) - manifest_url_set)
    if unknown_manifest_urls:
        failures.append(f"{suite_name}: {actual_name} declares URLs outside suite evidence {unknown_manifest_urls}")
    missing_digest_urls = sorted(set(declared_case_urls) - digest_url_set)
    if missing_digest_urls:
        failures.append(f"{suite_name}: {actual_name} declares URLs absent from fixture digest {missing_digest_urls}")

    supplied_candidate_urls = candidate_supplied_evidence_urls(case.get("raw_response"))
    if supplied_candidate_urls:
        failures.append(
            f"{suite_name}: {actual_name} candidates supplied evidence_urls instead of evidence_refs "
            f"{supplied_candidate_urls}"
        )
    return failures


def source_urls_from_digest(digest: Any) -> set[str]:
    """Return source URLs present in a frozen digest object."""

    if not isinstance(digest, dict) or not isinstance(digest.get("items"), list):
        return set()
    return {
        str(item.get("source_url") or "")
        for item in digest["items"]
        if isinstance(item, dict) and str(item.get("source_url") or "").strip()
    }


def candidate_supplied_evidence_urls(raw_response: Any) -> list[str]:
    """Return candidate-supplied URLs, which are forbidden in replay fixtures."""

    if not isinstance(raw_response, dict) or not isinstance(raw_response.get("proposals"), list):
        return []
    supplied: list[str] = []
    for candidate in raw_response["proposals"]:
        if not isinstance(candidate, dict) or not candidate.get("evidence_urls"):
            continue
        supplied.extend(str(url) for url in candidate.get("evidence_urls", []) if str(url).strip())
    return sorted(set(supplied))


def run_proposal_replay_suite(paths: list[Path]) -> list[ProposalReplayResult]:
    """Replay frozen proposal interpretation cases and return structured results."""

    return [run_proposal_replay_case(load_proposal_replay_case(path)) for path in paths]


def run_proposal_benchmark_suite(
    paths: list[Path],
    *,
    suite_name: str = "proposal-replay-benchmark",
) -> ProposalBenchmarkReport:
    """Replay frozen proposal cases and summarize controller-invariant coverage."""

    return build_proposal_benchmark_report(
        [load_proposal_replay_case(path) for path in paths],
        suite_name=suite_name,
    )


def build_proposal_benchmark_report(
    cases: list[dict[str, Any]],
    *,
    suite_name: str = "proposal-replay-benchmark",
) -> ProposalBenchmarkReport:
    """Run in-memory replay cases and return benchmark-style failure categories."""

    results = [run_proposal_replay_case(case) for case in cases]
    failure_counts = {
        "schema_validity": 0,
        "evidence_ref_constraints": 0,
        "action_lane_classification": 0,
        "safety_boundary_handling": 0,
        "other": 0,
    }
    for result in results:
        for category in proposal_benchmark_failure_categories(result):
            failure_counts[category] += 1

    failed_count = sum(1 for result in results if not result.passed)
    return ProposalBenchmarkReport(
        suite_name=suite_name,
        passed=failed_count == 0,
        case_count=len(results),
        passed_count=len(results) - failed_count,
        failed_count=failed_count,
        accepted_count=sum(result.accepted_count for result in results),
        rejected_count=sum(result.rejected_count for result in results),
        failure_counts=failure_counts,
        case_results=results,
    )


def run_proposal_replay_case(case: dict[str, Any]) -> ProposalReplayResult:
    """Replay one frozen evidence package and validate expected controller invariants."""

    name = str(case.get("name") or "unnamed")
    digest = case.get("digest")
    if not isinstance(digest, dict):
        raise ValueError(f"{name}: digest must be an object")
    raw_response = case.get("raw_response")
    if isinstance(raw_response, dict):
        raw_text = json.dumps(raw_response)
    else:
        raw_text = str(raw_response or "")
    options = case.get("options") if isinstance(case.get("options"), dict) else {}
    evidence_package = build_proposal_evidence_package(
        digest,
        max_items=int(options.get("max_items") or 20),
        max_item_text_chars=int(options.get("max_item_text_chars") or 1200),
    )
    review = review_llm_proposal_response(
        raw_text,
        evidence_package,
        mode=str(case.get("mode") or "hybrid"),
    )
    proposal_controls = build_proposal_controls(digest, review.accepted_candidates)
    rejected_errors = [
        str(error)
        for rejected in review.rejected_candidates
        for error in rejected.get("errors", [])
    ]
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    failures = collect_proposal_replay_failures(
        name,
        evidence_package,
        review,
        digest,
        expected,
        proposal_controls=proposal_controls,
    )
    failures.extend(collect_safety_boundary_failures(name, proposal_controls))
    return ProposalReplayResult(
        name=name,
        passed=not failures,
        failures=failures,
        review_status=review.status,
        accepted_count=review.accepted_count,
        rejected_count=review.rejected_count,
        selected_item_ids=[str(item_id) for item_id in evidence_package["context_budget"]["selected_item_ids"]],
        truncated_item_ids=[str(item_id) for item_id in evidence_package["context_budget"]["truncated_item_ids"]],
        proposal_controls=proposal_controls,
        rejected_errors=rejected_errors,
    )


def collect_proposal_replay_failures(
    name: str,
    evidence_package: dict[str, Any],
    review: Any,
    digest: dict[str, Any],
    expected: dict[str, Any],
    proposal_controls: dict[str, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    selected_item_ids = {str(item_id) for item_id in evidence_package["context_budget"]["selected_item_ids"]}
    truncated_item_ids = {str(item_id) for item_id in evidence_package["context_budget"]["truncated_item_ids"]}
    max_proposals = int(evidence_package.get("policy", {}).get("max_proposals") or 5)

    if review.accepted_count > max_proposals:
        failures.append(f"{name}: accepted_count exceeds max_proposals={max_proposals}")
    for candidate in review.accepted_candidates:
        candidate_id = str(candidate.get("proposal_id") or "")
        refs = {str(ref) for ref in candidate.get("evidence_refs", [])}
        unknown_refs = sorted(refs - selected_item_ids)
        cited_truncated_refs = sorted(refs & truncated_item_ids)
        if unknown_refs:
            failures.append(f"{name}: accepted proposal {candidate_id} cited non-selected refs {unknown_refs}")
        if cited_truncated_refs:
            failures.append(f"{name}: accepted proposal {candidate_id} cited truncated refs {cited_truncated_refs}")

    failures.extend(compare_expected_scalar(name, "status", review.status, expected))
    failures.extend(compare_expected_scalar(name, "accepted_count", review.accepted_count, expected))
    failures.extend(compare_expected_scalar(name, "rejected_count", review.rejected_count, expected))
    failures.extend(
        compare_expected_sequence(
            name,
            "selected_item_ids",
            list(evidence_package["context_budget"]["selected_item_ids"]),
            expected,
        )
    )
    failures.extend(
        compare_expected_sequence(
            name,
            "truncated_item_ids",
            list(evidence_package["context_budget"]["truncated_item_ids"]),
            expected,
        )
    )
    failures.extend(compare_expected_accepted_refs(name, review.accepted_candidates, expected))
    failures.extend(compare_expected_rejected_errors(name, review.rejected_candidates, expected))
    failures.extend(compare_expected_proposal_controls(name, proposal_controls, expected))
    return failures


def proposal_benchmark_failure_categories(result: ProposalReplayResult) -> set[str]:
    """Classify replay failures into stable benchmark lanes."""

    categories: set[str] = set()
    if result.passed:
        return categories
    failure_text = "\n".join([*result.failures, *result.rejected_errors]).lower()
    if not failure_text:
        return categories
    if any(term in failure_text for term in ("schema_version", "status", "accepted_count", "rejected_count")):
        categories.add("schema_validity")
    if any(term in failure_text for term in ("evidence_refs", "non-selected refs", "truncated refs", "unknown item ids")):
        categories.add("evidence_ref_constraints")
    if "proposal_controls" in failure_text:
        categories.add("action_lane_classification")
    if any(term in failure_text for term in ("privacy-leakage", "offensive-behavior", "safety boundary")):
        categories.add("safety_boundary_handling")
    if not categories:
        categories.add("other")
    return categories


def collect_safety_boundary_failures(name: str, proposal_controls: dict[str, dict[str, Any]]) -> list[str]:
    """Ensure high-risk proposals cannot drift into autonomous local application."""

    failures: list[str] = []
    for proposal_id, controls in proposal_controls.items():
        risk_flags = {str(flag) for flag in controls.get("risk_flags", [])}
        if not risk_flags & HIGH_RISK_FLAGS:
            continue
        implementation_scope = str(controls.get("implementation_scope") or "")
        validation_gate = str(controls.get("validation_gate") or "")
        if implementation_scope != "reviewable_proposal_only":
            failures.append(
                f"{name}: safety boundary proposal {proposal_id} must remain reviewable_proposal_only"
            )
        if not validation_gate.endswith("-human-review"):
            failures.append(f"{name}: safety boundary proposal {proposal_id} must require human review")
    return failures


def compare_expected_scalar(name: str, key: str, actual: Any, expected: dict[str, Any]) -> list[str]:
    if key not in expected:
        return []
    if actual != expected[key]:
        return [f"{name}: expected {key}={expected[key]!r}, got {actual!r}"]
    return []


def compare_expected_sequence(name: str, key: str, actual: list[Any], expected: dict[str, Any]) -> list[str]:
    if key not in expected:
        return []
    expected_value = expected[key]
    if actual != expected_value:
        return [f"{name}: expected {key}={expected_value!r}, got {actual!r}"]
    return []


def compare_expected_accepted_refs(
    name: str,
    accepted_candidates: list[dict[str, Any]],
    expected: dict[str, Any],
) -> list[str]:
    expected_refs = expected.get("accepted_evidence_refs")
    if expected_refs is None:
        return []
    actual = {
        str(candidate.get("proposal_id") or ""): [str(ref) for ref in candidate.get("evidence_refs", [])]
        for candidate in accepted_candidates
    }
    if actual != expected_refs:
        return [f"{name}: expected accepted_evidence_refs={expected_refs!r}, got {actual!r}"]
    return []


def compare_expected_rejected_errors(
    name: str,
    rejected_candidates: list[dict[str, Any]],
    expected: dict[str, Any],
) -> list[str]:
    expected_errors = expected.get("rejected_error_substrings")
    if expected_errors is None:
        return []
    error_text = "\n".join(
        str(error)
        for rejected in rejected_candidates
        for error in rejected.get("errors", [])
    )
    missing = [substring for substring in expected_errors if str(substring) not in error_text]
    if missing:
        return [f"{name}: missing rejected error substrings {missing!r}"]
    return []


def compare_expected_proposal_controls(
    name: str,
    actual: dict[str, dict[str, Any]],
    expected: dict[str, Any],
) -> list[str]:
    expected_controls = expected.get("proposal_controls")
    if expected_controls is None:
        return []
    if actual != expected_controls:
        return [f"{name}: expected proposal_controls={expected_controls!r}, got {actual!r}"]
    return []


def build_proposal_controls(
    digest: dict[str, Any],
    accepted_candidates: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Recompute controller-owned action-lane controls for accepted candidates."""

    proposals = clamp_llm_candidates_to_proposals(
        accepted_candidates,
        signals_from_digest_items(digest),
        limit=len(accepted_candidates) or 1,
    )
    return {
        str(proposal.get("proposal_id") or ""): {
            "kind": str(proposal.get("kind") or ""),
            "risk_flags": [str(flag) for flag in proposal.get("risk_flags", [])],
            "implementation_scope": str(proposal.get("implementation_scope") or ""),
            "validation_gate": str(proposal.get("validation_gate") or ""),
        }
        for proposal in proposals
    }


def signals_from_digest_items(digest: dict[str, Any]) -> list[GrowthSignal]:
    """Build minimal GrowthSignal objects from frozen digest items for control classification."""

    items = digest.get("items") if isinstance(digest.get("items"), list) else []
    signals: list[GrowthSignal] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        source_url = str(item.get("source_url") or "")
        signals.append(
            GrowthSignal(
                event_id=str(item.get("item_id") or f"item-{index + 1}"),
                repo=repo_from_digest_item(item),
                kind=str(item.get("event_kind") or ""),
                title=str(item.get("summary") or ""),
                url=source_url,
                relevance_reason=str(item.get("relevance_reason") or ""),
                risk_flags=[str(flag) for flag in item.get("risk_flags", []) if str(flag).strip()],
                recommended_action="replay frozen proposal case",
                confidence=float(item.get("confidence") or 0.0),
            )
        )
    return signals


def repo_from_digest_item(item: dict[str, Any]) -> str:
    source_url = str(item.get("source_url") or "")
    match = re.match(r"https://github\.com/([^/\s]+/[^/\s#?]+)", source_url)
    if match:
        return match.group(1)
    summary = str(item.get("summary") or "")
    if ": " in summary:
        return summary.split(": ", 1)[0]
    return "unknown/repo"
