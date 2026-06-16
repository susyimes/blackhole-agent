"""Replay-style local checks for frozen proposal evidence packages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from blackhole_agent.github_growth import GrowthSignal, clamp_llm_candidates_to_proposals
from blackhole_agent.proposal_synthesis import build_proposal_evidence_package, review_llm_proposal_response


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


def load_proposal_replay_case(path: Path) -> dict[str, Any]:
    """Load a replay case from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    payload.setdefault("name", path.stem)
    return payload


def run_proposal_replay_suite(paths: list[Path]) -> list[ProposalReplayResult]:
    """Replay frozen proposal interpretation cases and return structured results."""

    return [run_proposal_replay_case(load_proposal_replay_case(path)) for path in paths]


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
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    failures = collect_proposal_replay_failures(name, evidence_package, review, digest, expected)
    return ProposalReplayResult(
        name=name,
        passed=not failures,
        failures=failures,
        review_status=review.status,
        accepted_count=review.accepted_count,
        rejected_count=review.rejected_count,
        selected_item_ids=[str(item_id) for item_id in evidence_package["context_budget"]["selected_item_ids"]],
        truncated_item_ids=[str(item_id) for item_id in evidence_package["context_budget"]["truncated_item_ids"]],
    )


def collect_proposal_replay_failures(
    name: str,
    evidence_package: dict[str, Any],
    review: Any,
    digest: dict[str, Any],
    expected: dict[str, Any],
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
    failures.extend(compare_expected_proposal_controls(name, digest, review.accepted_candidates, expected))
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
    digest: dict[str, Any],
    accepted_candidates: list[dict[str, Any]],
    expected: dict[str, Any],
) -> list[str]:
    expected_controls = expected.get("proposal_controls")
    if expected_controls is None:
        return []
    proposals = clamp_llm_candidates_to_proposals(
        accepted_candidates,
        signals_from_digest_items(digest),
        limit=len(accepted_candidates) or 1,
    )
    actual = {
        str(proposal.get("proposal_id") or ""): {
            "kind": str(proposal.get("kind") or ""),
            "risk_flags": [str(flag) for flag in proposal.get("risk_flags", [])],
            "implementation_scope": str(proposal.get("implementation_scope") or ""),
            "validation_gate": str(proposal.get("validation_gate") or ""),
        }
        for proposal in proposals
    }
    if actual != expected_controls:
        return [f"{name}: expected proposal_controls={expected_controls!r}, got {actual!r}"]
    return []


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
