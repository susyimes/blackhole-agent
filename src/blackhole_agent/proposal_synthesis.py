"""LLM-assisted proposal synthesis with deterministic review gates."""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PROPOSAL_SYNTHESIS_SCHEMA_VERSION = 1
PROPOSAL_MODES = {"heuristic", "llm", "hybrid"}
DEFAULT_PROPOSAL_MODE = "hybrid"
DEFAULT_MAX_ITEM_TEXT_CHARS = 1200
REVIEW_ACTIVITY_EVENT_KINDS = {
    "PullRequestReviewCommentEvent",
    "PullRequestReviewEvent",
}
PR_ACTIVITY_EVENT_KINDS = REVIEW_ACTIVITY_EVENT_KINDS | {"PullRequestEvent"}
CODEX_GATEWAY_MARKER = "/ai-gateway/codex"
SERVING_ENDPOINTS_MARKER = "/serving-endpoints"
ALLOWED_PROPOSAL_KINDS = {"documentation", "test", "code_patch", "config", "follow_up_issue", "no_action"}
ALLOWED_IMPLEMENTATION_SCOPES = {
    "local_validation_candidate",
    "risk_review_before_local_change",
    "reviewable_proposal_only",
}
ROUTE_HINT_VALIDATION_LANES = {
    "skill_route_discovery": ["documentation", "config", "test", "code_patch"],
    "provider_config_preflight": ["documentation", "config", "test"],
    "agent_harness_eval": ["documentation", "test", "code_patch"],
    "governance_policy": ["documentation", "config", "test", "code_patch"],
}
SKILL_WORKFLOW_ROUTE_TERMS = (
    "agent skill",
    "agent skills",
    "codex skill",
    "codex skills",
    "mcp",
    "plugin",
    "plugins",
    "skill",
    "skill-route",
    "skill routing",
    "skills",
    "tool integration",
    "tool integrations",
    "workflow",
    "workflow gate",
    "workflow gates",
    "workflow routing",
)
PROVIDER_CONFIG_ROUTE_TERMS = (
    "api key",
    "api keys",
    "config",
    "configuration",
    "provider",
    "providers",
    "token",
    "tokens",
)
HARNESS_EVAL_ROUTE_TERMS = (
    "agent harness",
    "benchmark",
    "eval",
    "eval suite",
    "evaluation",
    "harness",
    "replay",
    "replayable",
    "validation harness",
)
GOVERNANCE_POLICY_ROUTE_TERMS = (
    "approval",
    "approval gate",
    "approval gates",
    "cap spend",
    "govern",
    "governance",
    "limit tools",
    "permission",
    "permissions",
    "policies",
    "policy",
    "sandbox",
    "sandboxing",
    "spend cap",
    "spend caps",
    "tool limit",
    "tool limits",
)
HIGH_RISK_FLAGS = {
    "offensive-behavior",
    "privacy-leakage",
}
FORBIDDEN_ACTION_TERMS = (
    "attack",
    "backdoor",
    "credential stuffing",
    "ddos",
    "denial of service",
    "dump api key",
    "dump credentials",
    "dump private key",
    "dump secret",
    "dump token",
    "expose api key",
    "expose credentials",
    "expose private key",
    "expose secret",
    "expose token",
    "exfiltrate",
    "exploit",
    "log api key",
    "log credentials",
    "log private key",
    "log secret",
    "log token",
    "leak token",
    "malware",
    "phishing",
    "print api key",
    "print credentials",
    "print private key",
    "print secret",
    "print token",
    "publish api key",
    "publish credentials",
    "publish private key",
    "publish secret",
    "publish token",
    "ransomware",
    "share api key",
    "share credentials",
    "share private key",
    "share secret",
    "share token",
    "upload api key",
    "upload credentials",
    "upload private key",
    "upload secret",
    "upload token",
)


@dataclass(frozen=True)
class ProposalSynthesisReview:
    """Review outcome for an LLM proposal synthesis attempt."""

    schema_version: int
    mode: str
    status: str
    reason: str
    input_digest_id: str
    input_hash: str
    output_hash: str
    accepted_count: int
    rejected_count: int
    accepted_candidates: list[dict[str, Any]]
    rejected_candidates: list[dict[str, Any]]
    interpretation: dict[str, Any]
    self_model_reading: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "status": self.status,
            "reason": self.reason,
            "input_digest_id": self.input_digest_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "accepted_candidates": self.accepted_candidates,
            "rejected_candidates": self.rejected_candidates,
            "interpretation": self.interpretation,
            "self_model_reading": self.self_model_reading,
        }


def validate_proposal_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in PROPOSAL_MODES:
        raise ValueError("proposal_mode must be one of: heuristic, llm, hybrid")
    return normalized


def build_proposal_evidence_package(
    digest: dict[str, Any],
    *,
    self_model_snapshot: dict[str, Any] | None = None,
    max_items: int = 20,
    max_item_text_chars: int = DEFAULT_MAX_ITEM_TEXT_CHARS,
    max_self_model_chars: int = 4000,
) -> dict[str, Any]:
    """Build the frozen input package an LLM may interpret."""

    items: list[dict[str, Any]] = []
    allowed_urls: list[str] = []
    all_digest_items = digest.get("items", [])
    valid_digest_items = [item for item in all_digest_items if isinstance(item, dict)] if isinstance(all_digest_items, list) else []
    input_text_chars = sum(
        len(str(item.get("summary") or "")) + len(str(item.get("relevance_reason") or ""))
        for item in valid_digest_items
    )
    ranked_digest_item_entries = rank_digest_item_entries_for_context_budget(all_digest_items)
    item_ids_by_original_index = build_context_budget_item_ids(ranked_digest_item_entries)
    ranked_digest_items = [item for _, item in ranked_digest_item_entries]
    selected_digest_item_entries = ranked_digest_item_entries[:max_items]
    item_truncation: list[dict[str, Any]] = []
    selected_item_ids: list[str] = []
    selected_text_chars = 0
    selected_text_original_chars = 0
    field_truncated_text_chars = 0
    for ranked_index, item in selected_digest_item_entries:
        item_id = item_ids_by_original_index[ranked_index]
        selected_item_ids.append(item_id)
        source_url = str(item.get("source_url") or "")
        if source_url:
            allowed_urls.append(source_url)
        summary, summary_meta = truncate_text(str(item.get("summary") or ""), max_item_text_chars)
        relevance_reason, relevance_meta = truncate_text(
            str(item.get("relevance_reason") or ""),
            max_item_text_chars,
        )
        truncated_fields = []
        if summary_meta["truncated"]:
            truncated_fields.append({"field": "summary", **summary_meta})
        if relevance_meta["truncated"]:
            truncated_fields.append({"field": "relevance_reason", **relevance_meta})
        selected_text_chars += int(summary_meta["kept_chars"]) + int(relevance_meta["kept_chars"])
        selected_text_original_chars += int(summary_meta["original_chars"]) + int(relevance_meta["original_chars"])
        field_truncated_text_chars += (
            int(summary_meta["original_chars"])
            - int(summary_meta["kept_chars"])
            + int(relevance_meta["original_chars"])
            - int(relevance_meta["kept_chars"])
        )
        if truncated_fields:
            item_truncation.append({"item_id": item_id, "fields": truncated_fields})
        items.append(
            {
                "item_id": item_id,
                "source_url": source_url,
                "event_kind": str(item.get("event_kind") or ""),
                "summary": summary,
                "relevance_reason": relevance_reason,
                "rule_risk_flags": [str(flag) for flag in item.get("risk_flags", [])],
                "rule_confidence": float(item.get("confidence") or 0.0),
                "route_hints": route_hints_for_digest_item(
                    {
                        **item,
                        "summary": summary,
                        "relevance_reason": relevance_reason,
                    }
                ),
            }
        )
    truncated_item_ids = [
        item_ids_by_original_index[ranked_index] for ranked_index, _ in ranked_digest_item_entries[max_items:]
    ]
    snapshot = self_model_snapshot or {}
    self_model_content, self_model_truncation = truncate_text(
        str(snapshot.get("content") or ""),
        max_self_model_chars,
    )
    return {
        "schema_version": PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        "digest_id": str(digest.get("digest_id") or ""),
        "generated_at": str(digest.get("generated_at") or ""),
        "allowed_evidence_urls": sorted(set(allowed_urls)),
        "items": items,
        "context_budget": {
            "max_items": max_items,
            "input_item_count": len(all_digest_items) if isinstance(all_digest_items, list) else 0,
            "items_truncated": len(ranked_digest_items) > max_items,
            "item_selection_strategy": (
                "risk_flags_then_direct_detail_then_confidence_with_review_activity_and_generic_pr_dedup_then_original_order"
            ),
            "selected_item_ids": selected_item_ids,
            "truncated_item_ids": truncated_item_ids,
            "max_item_text_chars": max_item_text_chars,
            "input_text_chars": input_text_chars,
            "selected_text_original_chars": selected_text_original_chars,
            "selected_text_chars": selected_text_chars,
            "field_truncated_text_chars": field_truncated_text_chars,
            "whole_item_truncated_count": len(truncated_item_ids),
            "text_truncated_item_count": len(item_truncation),
            "item_text_truncation": item_truncation,
            "item_selection_diagnostics": build_item_selection_diagnostics(
                all_digest_items,
                ranked_digest_item_entries,
                item_ids_by_original_index=item_ids_by_original_index,
                selected_item_ids=set(selected_item_ids),
                truncated_item_ids=set(truncated_item_ids),
                item_text_truncation=item_truncation,
            ),
            "evidence_truncation_uncertainty": build_evidence_truncation_uncertainty(
                all_digest_items,
                item_ids_by_original_index=item_ids_by_original_index,
                selected_item_ids=set(selected_item_ids),
                truncated_item_ids=set(truncated_item_ids),
            ),
        },
        "self_model": {
            "path": str(snapshot.get("path") or ""),
            "sha256": str(snapshot.get("sha256") or ""),
            "content": self_model_content,
            "truncated": bool(snapshot.get("truncated") or False) or self_model_truncation["truncated"],
            "content_original_chars": self_model_truncation["original_chars"],
            "content_kept_chars": self_model_truncation["kept_chars"],
        },
        "policy": {
            "allowed_kinds": sorted(ALLOWED_PROPOSAL_KINDS),
            "allowed_scopes": sorted(ALLOWED_IMPLEMENTATION_SCOPES),
            "max_proposals": 5,
            "evidence_refs_must_point_to_items": True,
            "final_scope_and_gate_are_recomputed_by_controller": True,
            "allowed_route_hints": [
                "agent_harness_eval",
                "governance_policy",
                "provider_config_preflight",
                "skill_route_discovery",
            ],
            "route_hint_validation_lanes": {
                key: list(value) for key, value in ROUTE_HINT_VALIDATION_LANES.items()
            },
            "safety_boundary": {
                "review_only": ["offensive-behavior", "privacy-leakage"],
                "allowed_when_locally_validated": [
                    "controller internals",
                    "runtime behavior",
                    "provider/config preflight",
                    "runner and remote-execution plumbing",
                    "tool routing",
                    "scheduling",
                    "memory",
                    "skill/workflow routing",
                    "tests",
                    "documentation",
                ],
            },
        },
    }


def build_route_hint_policy_preflight(evidence_package: dict[str, Any]) -> dict[str, Any]:
    """Validate route-hint lane policy before proposal implementation lanes are chosen."""

    policy = evidence_package.get("policy") if isinstance(evidence_package.get("policy"), dict) else {}
    configured_lanes = policy.get("route_hint_validation_lanes")
    configured_lanes = configured_lanes if isinstance(configured_lanes, dict) else {}
    configured_hints = {
        str(hint): [str(lane) for lane in lanes if str(lane).strip()]
        for hint, lanes in configured_lanes.items()
        if isinstance(lanes, list)
    }
    selected_route_hints = sorted(
        {
            str(route_hint)
            for item in evidence_package.get("items", [])
            if isinstance(item, dict)
            for route_hint in item.get("route_hints", [])
            if str(route_hint).strip()
        }
    )

    diagnostics: list[str] = []
    expected_policy_lanes = {
        hint: lanes
        for hint, lanes in ROUTE_HINT_VALIDATION_LANES.items()
        if hint in selected_route_hints or hint == "skill_route_discovery"
    }
    for route_hint, expected_lanes in expected_policy_lanes.items():
        configured = configured_hints.get(route_hint)
        if configured == expected_lanes:
            continue
        diagnostics.append(
            f"{route_hint} route hint must resolve only to: "
            + ", ".join(expected_lanes)
        )

    unsupported_lanes_by_hint = {
        route_hint: sorted(set(configured_hints.get(route_hint, [])) - set(expected_lanes))
        for route_hint, expected_lanes in expected_policy_lanes.items()
    }
    for route_hint, unsupported_lanes in unsupported_lanes_by_hint.items():
        if unsupported_lanes:
            diagnostics.append(f"{route_hint} has unsupported lanes: " + ", ".join(unsupported_lanes))

    unconfigured_hints = sorted(set(selected_route_hints) - set(configured_hints))
    if unconfigured_hints:
        diagnostics.append("selected route hints lack validation lanes: " + ", ".join(unconfigured_hints))

    skill_lanes = configured_hints.get("skill_route_discovery")
    governance_lanes = configured_hints.get("governance_policy")
    return {
        "ok": not diagnostics,
        "route_hint_count": len(selected_route_hints),
        "selected_route_hints": selected_route_hints,
        "configured_route_hints": sorted(configured_hints),
        "skill_route_discovery_lanes": skill_lanes or [],
        "allowed_skill_route_discovery_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
        "governance_policy_lanes": governance_lanes or [],
        "allowed_governance_policy_lanes": list(ROUTE_HINT_VALIDATION_LANES["governance_policy"]),
        "diagnostics": diagnostics,
    }


def route_hints_for_digest_item(item: dict[str, Any]) -> list[str]:
    """Return deterministic proposal lanes suggested by non-sensitive item text."""

    text = " ".join(
        str(item.get(key) or "")
        for key in ("event_kind", "summary", "relevance_reason", "recommended_action")
    ).lower()
    hints: list[str] = []
    if any(term in text for term in SKILL_WORKFLOW_ROUTE_TERMS):
        hints.append("skill_route_discovery")
    if any(term in text for term in PROVIDER_CONFIG_ROUTE_TERMS):
        hints.append("provider_config_preflight")
    if any(term in text for term in HARNESS_EVAL_ROUTE_TERMS):
        hints.append("agent_harness_eval")
    if any(term in text for term in GOVERNANCE_POLICY_ROUTE_TERMS):
        hints.append("governance_policy")
    return hints


def rank_digest_items_for_context_budget(items: Any) -> list[dict[str, Any]]:
    """Prioritize evidence before context truncation while preserving deterministic tie order."""

    return [item for _, item in rank_digest_item_entries_for_context_budget(items)]


def rank_digest_item_entries_for_context_budget(items: Any) -> list[tuple[int, dict[str, Any]]]:
    """Return ranked digest items with their original zero-based index."""

    if not isinstance(items, list):
        return []

    review_activity_by_repo = digest_review_activity_counts(items)
    generic_pr_cluster_counts = digest_generic_pr_cluster_counts(items)
    generic_pr_cluster_seen: dict[str, int] = {}
    ranked: list[tuple[tuple[int, int, float, int], int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        risk_flags = item.get("risk_flags")
        has_risk_flags = isinstance(risk_flags, list) and any(str(flag).strip() for flag in risk_flags)
        try:
            confidence = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        generic_pr_cluster_key = digest_generic_pr_cluster_key(item)
        generic_pr_cluster_seen[generic_pr_cluster_key] = generic_pr_cluster_seen.get(generic_pr_cluster_key, 0) + 1
        generic_pr_duplicate_ordinal = generic_pr_cluster_seen[generic_pr_cluster_key]
        adjusted_confidence = confidence + digest_review_activity_confidence_bonus(
            item,
            review_activity_by_repo=review_activity_by_repo,
        ) - digest_generic_pr_duplicate_penalty(
            item,
            generic_pr_cluster_counts=generic_pr_cluster_counts,
            duplicate_ordinal=generic_pr_duplicate_ordinal,
        )
        ranked.append(
            (
                (
                    0 if has_risk_flags else 1,
                    -digest_item_direct_action_priority(
                        item,
                        generic_pr_cluster_counts=generic_pr_cluster_counts,
                    ),
                    -adjusted_confidence,
                    index,
                ),
                index,
                item,
            )
        )
    return [(index, item) for _, index, item in sorted(ranked, key=lambda entry: entry[0])]


def digest_review_activity_counts(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("event_kind") or "") not in REVIEW_ACTIVITY_EVENT_KINDS:
            continue
        repo = digest_item_repo(item)
        if repo:
            counts[repo] = counts.get(repo, 0) + 1
    return counts


def digest_review_activity_confidence_bonus(
    item: dict[str, Any],
    *,
    review_activity_by_repo: dict[str, int],
) -> float:
    repo = digest_item_repo(item)
    review_activity_count = review_activity_by_repo.get(repo, 0)
    if review_activity_count < 2:
        return 0.0
    if not digest_item_is_review_validation_or_test_route(item):
        return 0.0
    return min(0.24, 0.08 * (review_activity_count - 1))


def digest_generic_pr_cluster_counts(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        cluster_key = digest_generic_pr_cluster_key(item)
        if cluster_key:
            counts[cluster_key] = counts.get(cluster_key, 0) + 1
    return counts


def digest_generic_pr_duplicate_penalty(
    item: dict[str, Any],
    *,
    generic_pr_cluster_counts: dict[str, int],
    duplicate_ordinal: int = 1,
) -> float:
    cluster_key = digest_generic_pr_cluster_key(item)
    duplicate_count = generic_pr_cluster_counts.get(cluster_key, 0) if cluster_key else 0
    if duplicate_count < 2:
        return 0.0
    cluster_penalty = min(0.36, 0.12 * (duplicate_count - 1))
    ordinal_penalty = max(0, duplicate_ordinal - 1) * 0.18
    return min(0.72, cluster_penalty + ordinal_penalty)


def digest_item_repo(item: dict[str, Any]) -> str:
    source_url = str(item.get("source_url") or "")
    match = re.match(r"https://github\.com/([^/\s]+/[^/\s#?]+)", source_url)
    if match:
        return match.group(1)
    summary = str(item.get("summary") or "")
    if ": " in summary:
        return summary.split(": ", 1)[0].strip()
    return ""


def digest_item_is_review_validation_or_test_route(item: dict[str, Any]) -> bool:
    event_kind = str(item.get("event_kind") or "")
    if event_kind in PR_ACTIVITY_EVENT_KINDS:
        return True
    if event_kind != "PushEvent":
        return False
    text = f"{item.get('summary') or ''} {item.get('relevance_reason') or ''}".lower()
    return any(term in text for term in ("review", "validation", "validate", "test", "harness"))


def digest_item_direct_action_priority(
    item: dict[str, Any],
    *,
    generic_pr_cluster_counts: dict[str, int] | None = None,
) -> int:
    event_kind = str(item.get("event_kind") or "")
    if event_kind == "PullRequestEvent":
        cluster_key = digest_generic_pr_cluster_key(item)
        if cluster_key and (generic_pr_cluster_counts or {}).get(cluster_key, 0) > 1:
            return 0
        return 1
    text = f"{item.get('summary') or ''} {item.get('relevance_reason') or ''}".lower()
    if event_kind == "PushEvent" and any(term in text for term in ("validation", "validate", "test", "workflow")):
        return 1
    if event_kind == "ReleaseEvent":
        return 1
    return 0


def digest_generic_pr_cluster_key(item: dict[str, Any]) -> str:
    if not digest_item_has_generic_pull_request_detail(item):
        return ""
    repo = digest_item_repo(item)
    summary = str(item.get("summary") or "").lower()
    action = "updated"
    action_match = re.search(
        r"\b(opened|labeled|unlabeled|closed|reopened|synchronize|synchronized|edited)\b",
        summary,
    )
    if action_match:
        action = action_match.group(1)
    return stable_digest_metadata_key({"repo": repo, "event_kind": str(item.get("event_kind") or ""), "action": action})


def stable_digest_metadata_key(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def digest_item_id(item: dict[str, Any], original_index: int) -> str:
    """Return the stable item id used in proposal evidence packages."""

    return str(item.get("item_id") or f"item-{original_index + 1}")


def build_context_budget_item_ids(ranked_item_entries: list[tuple[int, dict[str, Any]]]) -> dict[int, str]:
    """Return deterministic, unique item ids for context-budget evidence references."""

    base_ids_by_index = {
        original_index: digest_item_id(item, original_index) for original_index, item in ranked_item_entries
    }
    base_id_counts: dict[str, int] = {}
    for base_id in base_ids_by_index.values():
        base_id_counts[base_id] = base_id_counts.get(base_id, 0) + 1

    used_ids: set[str] = set()
    item_ids_by_index: dict[int, str] = {}
    for original_index, _ in sorted(ranked_item_entries, key=lambda entry: entry[0]):
        base_id = base_ids_by_index[original_index]
        candidate = base_id if base_id_counts[base_id] == 1 else f"{base_id}__item_{original_index + 1}"
        suffix = 2
        while candidate in used_ids:
            candidate = f"{base_id}__item_{original_index + 1}_{suffix}"
            suffix += 1
        used_ids.add(candidate)
        item_ids_by_index[original_index] = candidate
    return item_ids_by_index


def build_item_selection_diagnostics(
    raw_items: Any,
    ranked_item_entries: list[tuple[int, dict[str, Any]]],
    *,
    item_ids_by_original_index: dict[int, str],
    selected_item_ids: set[str],
    truncated_item_ids: set[str],
    item_text_truncation: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Explain context-budget item decisions without copying evidence text or URLs."""

    if not isinstance(raw_items, list):
        return []

    truncated_fields_by_id = {
        str(entry.get("item_id") or ""): [
            str(field.get("field") or "")
            for field in entry.get("fields", [])
            if isinstance(field, dict) and str(field.get("field") or "").strip()
        ]
        for entry in item_text_truncation
        if isinstance(entry, dict) and isinstance(entry.get("fields"), list)
    }
    rank_by_index = {original_index: rank for rank, (original_index, _) in enumerate(ranked_item_entries, start=1)}
    generic_pr_cluster_counts = digest_generic_pr_cluster_counts(raw_items)
    generic_pr_cluster_ids = {
        cluster_key: f"generic-pr-cluster-{index}"
        for index, cluster_key in enumerate(sorted(generic_pr_cluster_counts), start=1)
    }
    diagnostics: list[dict[str, Any]] = []
    for original_index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            diagnostics.append(
                {
                    "original_index": original_index,
                    "item_id": "",
                    "decision": "excluded",
                    "reason": "non_object_item",
                }
            )
            continue

        item_id = item_ids_by_original_index.get(original_index, digest_item_id(raw_item, original_index))
        risk_flags = [str(flag) for flag in raw_item.get("risk_flags", []) if str(flag).strip()]
        try:
            confidence = float(raw_item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if item_id in selected_item_ids:
            decision = "selected"
            reason = "risk_flags" if risk_flags else "confidence"
        elif item_id in truncated_item_ids:
            decision = "truncated"
            reason = "max_items_exceeded"
        else:
            decision = "excluded"
            reason = "not_ranked"
        diagnostic = {
            "original_index": original_index,
            "rank": rank_by_index.get(original_index),
            "item_id": item_id,
            "decision": decision,
            "reason": reason,
            "risk_flag_count": len(risk_flags),
            "confidence": confidence,
            "truncated_fields": truncated_fields_by_id.get(item_id, []),
        }
        cluster_key = digest_generic_pr_cluster_key(raw_item)
        if cluster_key:
            cluster_count = generic_pr_cluster_counts.get(cluster_key, 0)
            diagnostic["generic_pr_cluster_id"] = generic_pr_cluster_ids.get(cluster_key, "")
            diagnostic["generic_pr_cluster_count"] = cluster_count
            diagnostic["low_detail_duplicate_pr"] = cluster_count > 1
        diagnostics.append(diagnostic)
    return diagnostics


def build_evidence_truncation_uncertainty(
    raw_items: Any,
    *,
    item_ids_by_original_index: dict[int, str],
    selected_item_ids: set[str],
    truncated_item_ids: set[str],
) -> dict[str, Any]:
    """Describe inference limits introduced by context truncation without copying URLs or text."""

    if not isinstance(raw_items, list):
        return {
            "missing_detail_risk": False,
            "reasons": ["digest_items_not_a_list"],
            "selected_event_kind_counts": {},
            "truncated_event_kind_counts": {},
            "selected_generic_pr_count": 0,
            "truncated_generic_pr_count": 0,
            "selected_generic_pr_cluster_count": 0,
            "truncated_generic_pr_cluster_count": 0,
            "repeated_generic_pr_cluster_count": 0,
            "max_generic_pr_cluster_size": 0,
            "citation_scope": "cite_selected_item_ids_only",
            "url_policy": "do_not_add_urls",
        }

    selected_event_kind_counts: dict[str, int] = {}
    truncated_event_kind_counts: dict[str, int] = {}
    selected_generic_pr_count = 0
    truncated_generic_pr_count = 0
    selected_generic_pr_cluster_keys: set[str] = set()
    truncated_generic_pr_cluster_keys: set[str] = set()
    generic_pr_cluster_counts = digest_generic_pr_cluster_counts(raw_items)

    for original_index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            continue
        item_id = item_ids_by_original_index.get(original_index, digest_item_id(raw_item, original_index))
        event_kind = str(raw_item.get("event_kind") or "unknown")
        if item_id in selected_item_ids:
            selected_event_kind_counts[event_kind] = selected_event_kind_counts.get(event_kind, 0) + 1
            if digest_item_has_generic_pull_request_detail(raw_item):
                selected_generic_pr_count += 1
                cluster_key = digest_generic_pr_cluster_key(raw_item)
                if cluster_key:
                    selected_generic_pr_cluster_keys.add(cluster_key)
        elif item_id in truncated_item_ids:
            truncated_event_kind_counts[event_kind] = truncated_event_kind_counts.get(event_kind, 0) + 1
            if digest_item_has_generic_pull_request_detail(raw_item):
                truncated_generic_pr_count += 1
                cluster_key = digest_generic_pr_cluster_key(raw_item)
                if cluster_key:
                    truncated_generic_pr_cluster_keys.add(cluster_key)

    truncated_pr_activity_count = sum(
        count for kind, count in truncated_event_kind_counts.items() if kind in PR_ACTIVITY_EVENT_KINDS
    )
    reasons: list[str] = []
    if truncated_item_ids:
        reasons.append("max_items_omitted_whole_digest_items")
    if truncated_pr_activity_count:
        reasons.append("truncated_pull_request_activity_may_hide_pr_specific_details")
    if selected_generic_pr_count or truncated_generic_pr_count:
        reasons.append("generic_or_untitled_pull_request_items_have_missing_title_context")
    repeated_generic_pr_cluster_count = sum(1 for count in generic_pr_cluster_counts.values() if count > 1)
    if repeated_generic_pr_cluster_count:
        reasons.append("repeated_generic_pull_request_metadata_clustered_and_downweighted")

    return {
        "missing_detail_risk": bool(reasons),
        "reasons": reasons,
        "selected_event_kind_counts": dict(sorted(selected_event_kind_counts.items())),
        "truncated_event_kind_counts": dict(sorted(truncated_event_kind_counts.items())),
        "selected_generic_pr_count": selected_generic_pr_count,
        "truncated_generic_pr_count": truncated_generic_pr_count,
        "selected_generic_pr_cluster_count": len(selected_generic_pr_cluster_keys),
        "truncated_generic_pr_cluster_count": len(truncated_generic_pr_cluster_keys),
        "repeated_generic_pr_cluster_count": repeated_generic_pr_cluster_count,
        "max_generic_pr_cluster_size": max(generic_pr_cluster_counts.values(), default=0),
        "citation_scope": "cite_selected_item_ids_only",
        "url_policy": "do_not_add_urls",
    }


def digest_item_has_generic_pull_request_detail(item: dict[str, Any]) -> bool:
    event_kind = str(item.get("event_kind") or "")
    if event_kind not in PR_ACTIVITY_EVENT_KINDS:
        return False
    text = f"{item.get('summary') or ''} {item.get('relevance_reason') or ''}".lower()
    return "untitled pull request" in text or "generic" in text or "truncated" in text or not text.strip()


def build_context_budget_preflight(evidence_package: dict[str, Any]) -> dict[str, Any]:
    """Summarize proposal context pressure without exposing evidence content or URLs."""

    context_budget = evidence_package.get("context_budget") if isinstance(evidence_package, dict) else {}
    context_budget = context_budget if isinstance(context_budget, dict) else {}
    items = evidence_package.get("items") if isinstance(evidence_package, dict) else []
    items = items if isinstance(items, list) else []
    item_text_truncation = context_budget.get("item_text_truncation")
    item_text_truncation = item_text_truncation if isinstance(item_text_truncation, list) else []
    item_selection_diagnostics = context_budget.get("item_selection_diagnostics")
    item_selection_diagnostics = item_selection_diagnostics if isinstance(item_selection_diagnostics, list) else []
    truncated_item_ids = [str(item_id) for item_id in context_budget.get("truncated_item_ids", [])]
    evidence_truncation_uncertainty = context_budget.get("evidence_truncation_uncertainty")
    evidence_truncation_uncertainty = (
        evidence_truncation_uncertainty if isinstance(evidence_truncation_uncertainty, dict) else {}
    )
    truncated_field_count = 0
    for entry in item_text_truncation:
        if isinstance(entry, dict) and isinstance(entry.get("fields"), list):
            truncated_field_count += len(entry["fields"])
    self_model = evidence_package.get("self_model") if isinstance(evidence_package, dict) else {}
    self_model = self_model if isinstance(self_model, dict) else {}
    items_truncated = bool(context_budget.get("items_truncated"))
    text_truncated = bool(item_text_truncation)
    return {
        "schema_version": PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        "digest_id": str(evidence_package.get("digest_id") or "") if isinstance(evidence_package, dict) else "",
        "generated_at": str(evidence_package.get("generated_at") or "") if isinstance(evidence_package, dict) else "",
        "input_hash": stable_hash(evidence_package) if isinstance(evidence_package, dict) else "",
        "status": "pressure_detected" if items_truncated or text_truncated else "within_budget",
        "local_metadata_only": True,
        "external_fetch_performed": False,
        "max_items": int(context_budget.get("max_items") or 0),
        "input_item_count": int(context_budget.get("input_item_count") or 0),
        "kept_item_count": len(items),
        "items_truncated": items_truncated,
        "max_item_text_chars": int(context_budget.get("max_item_text_chars") or 0),
        "truncated_item_count": len(truncated_item_ids),
        "whole_item_truncated_count": int(context_budget.get("whole_item_truncated_count") or len(truncated_item_ids)),
        "text_truncated_item_count": int(context_budget.get("text_truncated_item_count") or len(item_text_truncation)),
        "truncated_field_count": truncated_field_count,
        "input_text_chars": int(context_budget.get("input_text_chars") or 0),
        "selected_text_original_chars": int(context_budget.get("selected_text_original_chars") or 0),
        "selected_text_chars": int(context_budget.get("selected_text_chars") or 0),
        "field_truncated_text_chars": int(context_budget.get("field_truncated_text_chars") or 0),
        "item_selection_strategy": str(context_budget.get("item_selection_strategy") or ""),
        "selected_item_ids": [str(item_id) for item_id in context_budget.get("selected_item_ids", [])],
        "truncated_item_ids": truncated_item_ids,
        "excluded_item_count": sum(
            1
            for item in item_selection_diagnostics
            if isinstance(item, dict) and str(item.get("decision") or "") == "excluded"
        ),
        "item_selection_diagnostics": item_selection_diagnostics,
        "evidence_truncation_uncertainty": evidence_truncation_uncertainty,
        "self_model_truncated": bool(self_model.get("truncated")),
    }


def classify_provider_base_url(base_url: str) -> str:
    """Classify a provider base URL by route shape without preserving host or credentials."""

    normalized = base_url.strip().lower()
    if not normalized:
        return "missing"
    if CODEX_GATEWAY_MARKER in normalized:
        return "codex_gateway"
    if SERVING_ENDPOINTS_MARKER in normalized:
        return "serving_endpoint"
    return "generic_chat_compatible"


def build_provider_routing_preflight(
    config: dict[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Detect provider route/config issues without preserving URLs or secret values."""

    provider = str(config.get("provider") or "openai").strip().lower()
    model = str(config.get("model") or "").strip()
    base_url = str(config.get("base_url") or "").strip()
    token_env_names = provider_token_env_names(config)
    environment = os.environ if env is None else env
    token_env_present = {name: bool(str(environment.get(name) or "").strip()) for name in token_env_names}
    requires_token = bool(config.get("requires_api_key")) or bool(token_env_names)
    inline_token_present = any(
        bool(str(config.get(key) or "").strip())
        for key in ("api_key", "api_token", "token", "access_token")
    )
    missing_config_fields = [
        field
        for field, value in (
            ("model", model),
            ("base_url", base_url),
        )
        if not value
    ]
    if requires_token and not inline_token_present and not any(token_env_present.values()):
        missing_config_fields.append("token")

    route_shape = classify_provider_base_url(base_url)
    provider_family = provider
    if "gemini" in model.lower():
        provider_family = "gemini"
    elif "gpt" in model.lower() or provider == "openai":
        provider_family = "gpt"

    applies_to_chat_provider = provider_family in {"gpt", "gemini", "openai"}
    misrouted = applies_to_chat_provider and route_shape == "codex_gateway"
    config_ok = not missing_config_fields
    status = "misrouted_codex_gateway" if misrouted else "missing_required_config" if not config_ok else "route_ok"
    return {
        "schema_version": PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        "status": status,
        "local_metadata_only": True,
        "external_fetch_performed": False,
        "provider_family": provider_family,
        "model_family": "gemini" if "gemini" in model.lower() else "gpt" if "gpt" in model.lower() else "unknown",
        "route_shape": route_shape,
        "config_status": "ok" if config_ok else "missing_required_config",
        "missing_config_fields": missing_config_fields,
        "token_env_names": token_env_names,
        "token_env_present": token_env_present,
        "token_required": requires_token,
        "token_value_recorded": False,
        "inline_token_present": inline_token_present,
        "base_url_recorded": False,
        "host_recorded": False,
        "reason": (
            "chat_completions_provider_points_at_codex_responses_gateway"
            if misrouted
            else "provider_required_config_missing"
            if not config_ok
            else "provider_route_shape_is_chat_compatible_or_not_applicable"
        ),
        "expected_route_shape": "serving_endpoint" if misrouted else route_shape,
    }


def provider_token_env_names(config: dict[str, Any]) -> list[str]:
    """Return configured token environment variable names without reading values."""

    raw_names: list[Any] = []
    for key in ("token_env", "api_key_env", "required_token_env"):
        value = config.get(key)
        if isinstance(value, (list, tuple, set)):
            raw_names.extend(value)
        elif value is not None:
            raw_names.append(value)
    names = sorted({str(name).strip() for name in raw_names if str(name).strip()})
    return names


def truncate_text(value: str, limit: int) -> tuple[str, dict[str, int | bool]]:
    """Return a deterministic character-bounded copy plus replay metadata."""

    normalized_limit = max(0, int(limit))
    truncated = len(value) > normalized_limit
    return value[:normalized_limit], {
        "truncated": truncated,
        "original_chars": len(value),
        "kept_chars": min(len(value), normalized_limit),
    }


def render_proposal_synthesis_prompt(evidence_package: dict[str, Any]) -> str:
    """Render a read-only prompt that asks for route interpretation, not mutation."""

    return "\n".join(
        [
            "You are the read-only proposal interpretation layer for blackhole-agent.",
            "",
            "Your job is to interpret frozen evidence and propose growth routes as strict JSON.",
            "Do not edit files. Do not run broad searches. Do not add evidence URLs.",
            "Cite only item_id values present in items; do not cite truncated_item_ids as evidence_refs.",
            "When context_budget.evidence_truncation_uncertainty.missing_detail_risk is true, record the missing detail risk in proposal uncertainty.",
            "Runtime permissions, final implementation scope, validation gates, and approval are recomputed by code.",
            "The safety boundary is narrow: only offensive behavior, abuse, unauthorized access, or privacy leakage is review-only.",
            "Provider/config/token preflight, runners, tool routing, scheduling, memory, tests, and controller behavior are allowed routes when locally validated.",
            "Use item.route_hints when present to propose bounded local validation lanes; skill_route_discovery may map only to documentation, config, test, or code_patch work.",
            "",
            "Return only a JSON object with:",
            "- schema_version: 1",
            "- input_digest_id",
            "- run_interpretation: string",
            "- self_model_reading: object",
            "- proposals: array of proposal candidates",
            "- rejected_items: array",
            "",
            "Each proposal candidate must include:",
            "proposal_id, kind, summary, evidence_refs, added_risk_flags, validation_task, rationale, uncertainty,",
            "self_effect, and action_lane.",
            "",
            "Frozen evidence package:",
            "```json",
            json.dumps(evidence_package, indent=2, sort_keys=True),
            "```",
        ]
    )


def review_llm_proposal_response(
    raw_text: str,
    evidence_package: dict[str, Any],
    *,
    mode: str,
) -> ProposalSynthesisReview:
    """Validate an LLM response and return accepted candidates plus replay metadata."""

    normalized_mode = validate_proposal_mode(mode)
    input_digest_id = str(evidence_package.get("digest_id") or "")
    input_hash = stable_hash(evidence_package)
    output_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    route_hint_preflight = build_route_hint_policy_preflight(evidence_package)
    if not route_hint_preflight["ok"]:
        return rejected_review(
            mode=normalized_mode,
            reason="route_hint_policy_preflight failed: " + "; ".join(route_hint_preflight["diagnostics"]),
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )
    try:
        payload = extract_json_object(raw_text)
    except ValueError as error:
        return rejected_review(
            mode=normalized_mode,
            reason=str(error),
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )

    if int(payload.get("schema_version") or 0) != PROPOSAL_SYNTHESIS_SCHEMA_VERSION:
        return rejected_review(
            mode=normalized_mode,
            reason="schema_version must be 1",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )
    if str(payload.get("input_digest_id") or "") != input_digest_id:
        return rejected_review(
            mode=normalized_mode,
            reason="input_digest_id does not match evidence package",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )

    items_by_id = {str(item.get("item_id")): item for item in evidence_package.get("items", [])}
    context_budget = evidence_package.get("context_budget")
    context_budget = context_budget if isinstance(context_budget, dict) else {}
    evidence_truncation_uncertainty = context_budget.get("evidence_truncation_uncertainty")
    evidence_truncation_uncertainty = (
        evidence_truncation_uncertainty if isinstance(evidence_truncation_uncertainty, dict) else {}
    )
    max_proposals = int(evidence_package.get("policy", {}).get("max_proposals") or 5)
    candidates = payload.get("proposals")
    if not isinstance(candidates, list):
        return rejected_review(
            mode=normalized_mode,
            reason="proposals must be a list",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )
    if len(candidates) > max_proposals:
        return rejected_review(
            mode=normalized_mode,
            reason=f"proposal count exceeds max_proposals={max_proposals}",
            input_digest_id=input_digest_id,
            input_hash=input_hash,
            output_hash=output_hash,
        )

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_proposal_ids: set[str] = set()
    seen_proposal_shapes: set[tuple[str, tuple[str, ...]]] = set()
    for index, candidate in enumerate(candidates, start=1):
        normalized, errors = normalize_candidate(
            candidate,
            items_by_id,
            index=index,
            evidence_truncation_uncertainty=evidence_truncation_uncertainty,
        )
        raw_candidate = candidate if isinstance(candidate, dict) else {}
        proposal_id = str(normalized.get("proposal_id") or raw_candidate.get("proposal_id") or f"llm-{index}")
        evidence_shape = tuple(sorted(str(ref) for ref in normalized.get("evidence_refs", [])))
        proposal_shape = (str(normalized.get("kind") or raw_candidate.get("kind") or ""), evidence_shape)
        if proposal_id in seen_proposal_ids:
            errors.append("proposal_id must be unique")
        if evidence_shape and proposal_shape in seen_proposal_shapes:
            errors.append("proposal kind and evidence_refs duplicate an earlier candidate")
        if errors:
            rejected.append({"candidate": candidate, "errors": errors})
        else:
            accepted.append(normalized)
            seen_proposal_ids.add(proposal_id)
            seen_proposal_shapes.add(proposal_shape)
    status = "accepted" if accepted else "rejected"
    reason = "accepted" if accepted else "no valid proposals"
    return ProposalSynthesisReview(
        schema_version=PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        mode=normalized_mode,
        status=status,
        reason=reason,
        input_digest_id=input_digest_id,
        input_hash=input_hash,
        output_hash=output_hash,
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        accepted_candidates=accepted,
        rejected_candidates=rejected,
        interpretation={
            "run_interpretation": str(payload.get("run_interpretation") or ""),
            "rejected_items": payload.get("rejected_items") if isinstance(payload.get("rejected_items"), list) else [],
        },
        self_model_reading=payload.get("self_model_reading")
        if isinstance(payload.get("self_model_reading"), dict)
        else {},
    )


def normalize_candidate(
    candidate: Any,
    items_by_id: dict[str, dict[str, Any]],
    *,
    index: int,
    evidence_truncation_uncertainty: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(candidate, dict):
        return {}, ["candidate must be an object"]
    errors: list[str] = []
    kind = str(candidate.get("kind") or "")
    if kind not in ALLOWED_PROPOSAL_KINDS:
        errors.append("kind is not allowed")
    evidence_refs = [str(ref) for ref in candidate.get("evidence_refs", []) if str(ref).strip()]
    if not evidence_refs:
        errors.append("evidence_refs must not be empty")
    supplied_evidence_urls = [str(url) for url in candidate.get("evidence_urls", []) if str(url).strip()]
    if supplied_evidence_urls:
        errors.append("evidence_urls must be derived from frozen evidence_refs, not supplied by candidates")
    missing_refs = [ref for ref in evidence_refs if ref not in items_by_id]
    if missing_refs:
        errors.append("evidence_refs contain unknown item ids: " + ", ".join(missing_refs))
    errors.extend(candidate_route_hint_lane_errors(kind, evidence_refs, items_by_id))
    validation_task = str(candidate.get("validation_task") or "").strip()
    if not validation_task:
        errors.append("validation_task must not be empty")
    rationale = str(candidate.get("rationale") or "").strip()
    if not rationale:
        errors.append("rationale must not be empty")
    uncertainty = str(candidate.get("uncertainty") or "").strip()
    if not uncertainty:
        errors.append("uncertainty must not be empty")
    elif candidate_requires_missing_detail_uncertainty(kind, evidence_truncation_uncertainty) and not (
        uncertainty_mentions_missing_detail_risk(uncertainty)
    ):
        errors.append("uncertainty must record context_budget missing_detail_risk")
    dangerous_text = " ".join(
        str(candidate.get(key) or "") for key in ("summary", "validation_task", "rationale", "self_effect")
    ).lower()
    forbidden = [term for term in FORBIDDEN_ACTION_TERMS if term in dangerous_text]
    validation_lower = validation_task.lower()
    if (
        forbidden
        and "risk_review" not in validation_lower
        and "review" not in validation_lower
        and "validate" not in validation_lower
    ):
        errors.append("dangerous action language must be framed as review or validation")
    added_flags = [str(flag) for flag in candidate.get("added_risk_flags", []) if str(flag).strip()]
    rule_flags = sorted(
        {
            str(flag)
            for ref in evidence_refs
            for flag in items_by_id.get(ref, {}).get("rule_risk_flags", [])
            if str(flag).strip()
        }
    )
    normalized = {
        "proposal_id": str(candidate.get("proposal_id") or f"llm-{index}"),
        "kind": kind,
        "summary": str(candidate.get("summary") or "").strip(),
        "evidence_refs": evidence_refs,
        "evidence_urls": sorted(
            {
                str(items_by_id[ref].get("source_url") or "")
                for ref in evidence_refs
                if ref in items_by_id and str(items_by_id[ref].get("source_url") or "").strip()
            }
        ),
        "rule_risk_flags": rule_flags,
        "added_risk_flags": sorted(set(added_flags)),
        "validation_task": validation_task,
        "rationale": rationale,
        "uncertainty": uncertainty,
        "self_effect": str(candidate.get("self_effect") or "").strip(),
        "action_lane": str(candidate.get("action_lane") or "").strip(),
    }
    return normalized, errors


def candidate_route_hint_lane_errors(
    kind: str,
    evidence_refs: list[str],
    items_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Reject candidates that escape deterministic route-hint lane constraints."""

    rule_risk_flags = {
        str(flag)
        for ref in evidence_refs
        for flag in items_by_id.get(ref, {}).get("rule_risk_flags", [])
        if str(flag).strip()
    }
    if rule_risk_flags & HIGH_RISK_FLAGS:
        return []

    route_hints = sorted(
        {
            str(route_hint)
            for ref in evidence_refs
            for route_hint in items_by_id.get(ref, {}).get("route_hints", [])
            if str(route_hint).strip()
        }
    )
    errors: list[str] = []
    enforced_route_hints = {"agent_harness_eval", "governance_policy", "skill_route_discovery"}
    for route_hint in route_hints:
        if route_hint not in enforced_route_hints:
            continue
        allowed_lanes = ROUTE_HINT_VALIDATION_LANES.get(route_hint)
        if allowed_lanes is None or kind in allowed_lanes:
            continue
        errors.append(f"{route_hint} proposals must use one of: {', '.join(allowed_lanes)}")
    return errors


def candidate_requires_missing_detail_uncertainty(
    kind: str,
    evidence_truncation_uncertainty: dict[str, Any] | None,
) -> bool:
    """Return whether a proposal must explicitly carry context-budget inference limits."""

    if kind == "no_action":
        return False
    if not isinstance(evidence_truncation_uncertainty, dict):
        return False
    return bool(evidence_truncation_uncertainty.get("missing_detail_risk"))


def uncertainty_mentions_missing_detail_risk(uncertainty: str) -> bool:
    """Detect bounded uncertainty language without requiring one exact phrase."""

    text = uncertainty.lower()
    indicators = (
        "missing detail",
        "missing title",
        "generic",
        "untitled",
        "truncated",
        "unknown",
        "not inspect",
        "not claim",
        "unsupported",
        "incomplete",
        "omitted",
        "outside the selected",
    )
    return any(indicator in text for indicator in indicators)


def rejected_review(
    *,
    mode: str,
    reason: str,
    input_digest_id: str,
    input_hash: str,
    output_hash: str,
) -> ProposalSynthesisReview:
    return ProposalSynthesisReview(
        schema_version=PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        mode=mode,
        status="rejected",
        reason=reason,
        input_digest_id=input_digest_id,
        input_hash=input_hash,
        output_hash=output_hash,
        accepted_count=0,
        rejected_count=0,
        accepted_candidates=[],
        rejected_candidates=[],
        interpretation={},
        self_model_reading={},
    )


def extract_json_object(raw_text: str) -> dict[str, Any]:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ValueError(f"LLM proposal response was not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("LLM proposal response must be a JSON object")
    return payload


def write_proposal_synthesis_artifacts(
    output_dir: Path,
    *,
    evidence_package: dict[str, Any],
    review: ProposalSynthesisReview,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_text = json.dumps(evidence_package, indent=2, sort_keys=True) + "\n"
    review_text = json.dumps(review.to_dict(), indent=2, sort_keys=True) + "\n"
    (output_dir / f"proposal-evidence-package-{timestamp}.json").write_text(evidence_text, encoding="utf-8")
    (output_dir / f"llm-proposal-review-{timestamp}.json").write_text(review_text, encoding="utf-8")
    (output_dir / "latest-proposal-evidence-package.json").write_text(evidence_text, encoding="utf-8")
    (output_dir / "latest-llm-proposal-review.json").write_text(review_text, encoding="utf-8")
    interpretation_text = json.dumps(review.interpretation, indent=2, sort_keys=True) + "\n"
    self_model_text = json.dumps(review.self_model_reading, indent=2, sort_keys=True) + "\n"
    (output_dir / "latest-growth-interpretation.json").write_text(interpretation_text, encoding="utf-8")
    (output_dir / "latest-self-model-reading.json").write_text(self_model_text, encoding="utf-8")


def write_context_budget_preflight_artifact(output_dir: Path, *, evidence_package: dict[str, Any]) -> dict[str, Any]:
    """Persist the local context-budget preflight before proposal interpretation runs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    preflight = build_context_budget_preflight(evidence_package)
    preflight_text = json.dumps(preflight, indent=2, sort_keys=True) + "\n"
    (output_dir / f"context-budget-preflight-{timestamp}.json").write_text(preflight_text, encoding="utf-8")
    (output_dir / "latest-context-budget-preflight.json").write_text(preflight_text, encoding="utf-8")
    return preflight


def stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
