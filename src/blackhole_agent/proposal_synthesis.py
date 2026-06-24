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
ROUTE_HINT_PROPOSAL_LANES = ["documentation", "config", "test", "code_patch"]
SKILL_WORKFLOW_ROUTE_TERMS = (
    "agent skill",
    "agent skills",
    "codex skill",
    "codex skills",
    "skill",
    "skill-route",
    "skill routing",
    "skills",
    "workflow skill",
    "workflow skills",
)
SKILL_WORKFLOW_CONTEXT_TERMS = (
    "director",
    "gate",
    "gates",
    "mcp",
    "plugin",
    "plugins",
    "tool integration",
    "tool integrations",
    "workflow gate",
    "workflow gates",
    "workflow routing",
)
NEGATED_SKILL_WORKFLOW_TERMS = (
    "lacks skill",
    "no skill",
    "not a skill",
    "not skill",
    "without skill",
)
CONCRETE_SKILL_WORKFLOW_TERMS = (
    "agent skill",
    "agent skills",
    "codex skill",
    "codex skills",
    "director skill",
    "skill package",
    "skill pack",
    "skill repository",
    "skill.md",
    "skills/",
    "workflow skill",
    "workflow skills",
)
SKILL_ROUTE_ACTIVITY_EVENT_KINDS = {
    "ForkEvent",
    "PushEvent",
    "RepositoryTrend",
}
GENERAL_AGENT_PROJECT_ROUTE_TERMS = (
    "agent",
    "agents",
    "ai agent",
    "llm agent",
    "multi-agent",
    "runtime",
)
GENERAL_AGENT_PROJECT_EVAL_LANES = ["documentation", "test", "code_patch"]
GENERAL_AGENT_PROJECT_EVAL_COMMANDS = [
    "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
    "pytest tests/test_proposal_eval.py -q -k omnigent",
]
MIXED_SKILL_ROUTE_PROBE_COMMANDS = [
    "pytest tests/test_github_growth.py -q -k mixed_skill_workflow",
    "pytest tests/test_proposal_eval.py -q -k route_hint_lane_map",
]
SKILL_ROUTE_LOCAL_LANE_COMMANDS = [
    "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
    "pytest tests/test_proposal_eval.py -q -k skill_route_discovery",
]
MIXED_SKILL_ROUTE_PROBE_LANE_ORDER = ["test", "documentation", "config", "code_patch"]
SKILL_ROUTE_PROFILE_KEYWORDS = {
    "codex_workflow_gate": (
        "codex",
        "evidence gate",
        "fablecodex",
        "plugin",
        "review gate",
        "review ledger",
        "verification habit",
        "workflow gate",
    ),
    "game_frontend_workflow": (
        "3d",
        "browser game",
        "game engine",
        "gameplay",
        "graphics",
        "phaser",
        "three.js",
        "threejs",
        "vite",
    ),
    "skill_ecosystem_state_handoff": (
        "collaboration profile",
        "compass",
        "handoff",
        "local memory",
        "profile",
        "skill ecosystem",
        "task forest",
    ),
}
MIXED_SKILL_ROUTE_PROBE_DENIED_ACTIONS = [
    "install",
    "enable",
    "run",
    "execute",
    "clone_and_run",
    "profile_write",
    "memory_write",
    "provider_launch",
    "remote_execution",
    "raw_source_url_export",
    "upstream_body_export",
]
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
                **route_metadata_for_digest_item(
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

    lane_map = build_route_hint_lane_map(evidence_package)
    diagnostics = list(lane_map["diagnostics"])
    skill_lanes = lane_map["validation_lanes"].get("skill_route_discovery", [])
    governance_lanes = lane_map["validation_lanes"].get("governance_policy", [])
    skill_route_implementation_preflight = lane_map["skill_route_implementation_preflight"]
    return {
        "ok": not diagnostics,
        "route_hint_count": len(lane_map["selected_route_hints"]),
        "selected_route_hints": lane_map["selected_route_hints"],
        "configured_route_hints": lane_map["configured_route_hints"],
        "skill_route_discovery_lanes": skill_lanes,
        "allowed_skill_route_discovery_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
        "skill_route_implementation_preflight": skill_route_implementation_preflight,
        "governance_policy_lanes": governance_lanes,
        "allowed_governance_policy_lanes": list(ROUTE_HINT_VALIDATION_LANES["governance_policy"]),
        "diagnostics": diagnostics,
    }


def build_route_hint_lane_map(evidence_package: dict[str, Any]) -> dict[str, Any]:
    """Map known route hints to bounded local proposal lanes.

    The map is metadata-only. It does not add evidence URLs, permissions, or
    runtime actions; it only exposes the documentation/config/test/code_patch
    lanes that deterministic proposal review already knows how to validate.
    """

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
    route_class_counts: dict[str, int] = {}
    route_classifier_rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    package_items = evidence_package.get("items", [])
    package_items = package_items if isinstance(package_items, list) else []
    skill_route_activity_counts = digest_skill_route_activity_counts(package_items)
    for item in package_items:
        if not isinstance(item, dict):
            continue
        classification = item.get("route_classification")
        if not isinstance(classification, dict):
            classification = route_metadata_for_digest_item(item)["route_classification"]
        route_class = str(classification.get("route_class") or "unclassified")
        activity_key = digest_skill_route_project_key(item)
        repeated_activity_count = (
            skill_route_activity_counts.get(activity_key, 0)
            if route_class == "skill_workflow"
            else 0
        )
        route_class_counts[route_class] = route_class_counts.get(route_class, 0) + 1
        classification_allowed_lanes = [
            str(lane) for lane in classification.get("allowed_lanes", []) if str(lane).strip()
        ]
        classification_unsupported_lanes = _unsupported_skill_route_classification_lanes(classification)
        if classification_unsupported_lanes:
            diagnostics.append(
                f"{str(item.get('item_id') or '')} skill_route_discovery item has unsupported lanes: "
                + ", ".join(classification_unsupported_lanes)
            )
        route_classifier_rows.append(
            {
                "item_id": str(item.get("item_id") or ""),
                "route_class": route_class,
                "route_hints": [str(route_hint) for route_hint in classification.get("route_hints", [])],
                "allowed_lanes": classification_allowed_lanes,
                "unsupported_lanes": classification_unsupported_lanes,
                "evaluation_lane": str(classification.get("evaluation_lane") or ""),
                "route_probe_decision": str(classification.get("route_probe_decision") or ""),
                "route_profiles": [str(profile) for profile in classification.get("route_profiles", [])],
                "reasons": [str(reason) for reason in classification.get("reasons", [])],
                "repeated_skill_activity_count": repeated_activity_count,
                "repeated_skill_activity_signal": repeated_activity_count >= 2,
            }
        )

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

    route_hint_entries: list[dict[str, Any]] = []
    for route_hint in sorted(expected_policy_lanes):
        configured = configured_hints.get(route_hint, [])
        expected_lanes = expected_policy_lanes[route_hint]
        route_hint_entries.append(
            {
                "route_hint": route_hint,
                "validation_lanes": list(configured),
                "allowed_lanes": list(expected_lanes),
                "proposal_lanes": [
                    {
                        "route_hint": route_hint,
                        "proposal_kind": lane,
                        "runtime_action": "none",
                        "local_validation_required": True,
                    }
                    for lane in configured
                    if lane in expected_lanes and lane in ROUTE_HINT_PROPOSAL_LANES
                ],
                "unsupported_lanes": unsupported_lanes_by_hint.get(route_hint, []),
                "status": "valid" if configured == expected_lanes else "invalid",
            }
        )

    return {
        "schema_version": PROPOSAL_SYNTHESIS_SCHEMA_VERSION,
        "ok": not diagnostics,
        "route_hint_count": len(selected_route_hints),
        "selected_route_hints": selected_route_hints,
        "configured_route_hints": sorted(configured_hints),
        "route_class_counts": dict(sorted(route_class_counts.items())),
        "route_classifier": route_classifier_rows,
        "route_activity_pressure": build_skill_route_activity_pressure(package_items),
        "skill_route_local_lane_candidates": build_skill_route_local_lane_candidates(package_items),
        "skill_route_implementation_preflight": build_skill_route_implementation_preflight(
            package_items,
            context_budget=evidence_package.get("context_budget"),
        ),
        "mixed_skill_workflow_probe": build_mixed_skill_workflow_probe(package_items),
        "general_agent_project_eval": build_general_agent_project_eval_lane(package_items),
        "skill_route_boundary_report": build_skill_route_boundary_report(package_items),
        "route_activation_preflight": build_route_activation_preflight(package_items),
        "skill_route_pass3_handoff": build_skill_route_pass3_handoff(
            package_items,
            context_budget=evidence_package.get("context_budget"),
        ),
        "allowed_proposal_lanes": list(ROUTE_HINT_PROPOSAL_LANES),
        "validation_lanes": {hint: list(lanes) for hint, lanes in configured_hints.items()},
        "route_hint_entries": route_hint_entries,
        "permission_effect": "none",
        "evidence_url_effect": "none",
        "runtime_action": "none",
        "diagnostics": diagnostics,
    }


def build_skill_route_implementation_preflight(
    items: list[Any],
    *,
    context_budget: Any = None,
) -> dict[str, Any]:
    """Require bounded local lane selection before skill-route implementation."""

    candidate_panel = build_skill_route_local_lane_candidates(items)
    selected_item_ids = {
        str(item_id)
        for item_id in (
            context_budget.get("selected_item_ids", [])
            if isinstance(context_budget, dict)
            else []
        )
        if str(item_id).strip()
    }
    truncated_item_ids = sorted(
        {
            str(item_id)
            for item_id in (
                context_budget.get("truncated_item_ids", [])
                if isinstance(context_budget, dict)
                else []
            )
            if str(item_id).strip()
        }
    )
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []

    for row in candidate_panel.get("rows", []):
        if not isinstance(row, dict):
            continue
        item_id = str(row.get("item_id") or "")
        local_lanes = [str(lane) for lane in row.get("local_lanes", []) if str(lane).strip()]
        route_profiles = [str(profile) for profile in row.get("route_profiles", []) if str(profile).strip()]
        selected_lane = select_skill_route_implementation_lane(local_lanes, route_profiles)
        queued_lanes = [lane for lane in local_lanes if lane != selected_lane]
        unsupported_lanes = [str(lane) for lane in row.get("unsupported_lanes", []) if str(lane).strip()]
        selected_item_known = not selected_item_ids or item_id in selected_item_ids
        lane_selection_ready = (
            bool(selected_lane)
            and selected_lane in ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]
            and selected_lane in local_lanes
            and not unsupported_lanes
            and selected_item_known
        )
        row_blockers: list[str] = []
        if not selected_lane:
            row_blockers.append("missing_bounded_local_lane_selection")
        if unsupported_lanes:
            row_blockers.append("unsupported_skill_route_lanes")
        if not selected_item_known:
            row_blockers.append("item_not_in_selected_context_budget")
        if row_blockers:
            blockers.extend(f"{item_id}:{blocker}" for blocker in row_blockers if item_id)

        rows.append(
            {
                "item_id": item_id,
                "source_url_hash": str(row.get("source_url_hash") or ""),
                "route_profiles": route_profiles,
                "allowed_local_lanes": local_lanes,
                "selected_local_lane": selected_lane,
                "queued_local_lanes": queued_lanes,
                "unsupported_lanes": unsupported_lanes,
                "lane_selection_status": "ready" if lane_selection_ready else "blocked",
                "implementation_route_allowed": lane_selection_ready,
                "evidence_ref_scope": "selected_item_ids_only",
                "truncated_item_id_ref_allowed": False,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_export_allowed": False,
                "upstream_body_export_allowed": False,
            }
        )

    status = "not_applicable" if not rows else "ready" if not blockers else "blocked"
    return {
        "controller_surface": "skill_route_implementation_preflight",
        "status": status,
        "decision": (
            "select_bounded_local_lane_before_implementation"
            if status == "ready"
            else "no_skill_route_candidates_selected"
            if status == "not_applicable"
            else "block_skill_route_implementation_until_lanes_are_bounded"
        ),
        "candidate_count": len(rows),
        "ready_candidate_count": sum(1 for row in rows if row["lane_selection_status"] == "ready"),
        "blocked_candidate_count": sum(1 for row in rows if row["lane_selection_status"] != "ready"),
        "allowed_local_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
        "selected_item_ids": sorted(selected_item_ids),
        "truncated_item_ids": truncated_item_ids,
        "truncated_item_ids_blocked_as_evidence_refs": True,
        "activation_blockers": sorted(dict.fromkeys(blockers)),
        "rows": rows,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_export_allowed": False,
        "upstream_body_export_allowed": False,
    }


def select_skill_route_implementation_lane(local_lanes: list[str], route_profiles: list[str]) -> str:
    """Choose the first local implementation lane to validate for a skill route."""

    lanes = [lane for lane in local_lanes if lane in ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]]
    profiles = set(route_profiles)
    preferred_lanes: list[str]
    if "skill_ecosystem_state_handoff" in profiles:
        preferred_lanes = ["config", "test", "documentation", "code_patch"]
    elif "codex_workflow_gate" in profiles or "game_frontend_workflow" in profiles:
        preferred_lanes = ["test", "documentation", "config", "code_patch"]
    else:
        preferred_lanes = list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"])
    for lane in preferred_lanes:
        if lane in lanes:
            return lane
    return lanes[0] if lanes else ""


def build_route_activation_preflight(items: list[Any]) -> dict[str, Any]:
    """Render the route split as an operator-visible pre-activation gate."""

    candidate_panel = build_skill_route_local_lane_candidates(items)
    general_eval = build_general_agent_project_eval_lane(items)
    boundary = build_skill_route_boundary_report(items)
    mixed_probe = build_mixed_skill_workflow_probe(items)

    skill_rows = [
        {
            "item_id": str(row.get("item_id") or ""),
            "route_class": "skill_workflow",
            "primary_route": "skill_route_discovery",
            "local_lanes": [str(lane) for lane in row.get("local_lanes", [])],
            "lane_status": str(row.get("lane_status") or ""),
            "activation_gate": str(row.get("activation_gate") or ""),
            "secondary_lane_status": str(row.get("secondary_lane_status") or ""),
            "local_validation_required": True,
            "runtime_action": "none",
        }
        for row in candidate_panel.get("rows", [])
        if isinstance(row, dict)
    ]
    general_rows = [
        {
            "item_id": str(row.get("item_id") or ""),
            "route_class": "general_agent_project",
            "primary_route": "agent_harness_eval_required",
            "allowed_local_lanes": [str(lane) for lane in row.get("allowed_local_lanes", [])],
            "skill_route_discovery_inherited": False,
            "local_validation_required": True,
            "runtime_action": "none",
        }
        for row in general_eval.get("candidates", [])
        if isinstance(row, dict)
    ]
    activation_blockers = list(boundary.get("diagnostics", []))
    activation_blockers.extend(
        f"{row['item_id']}:unsupported_skill_route_lanes"
        for row in skill_rows
        if row["lane_status"] != "bounded"
    )
    activation_blockers = sorted(dict.fromkeys(str(blocker) for blocker in activation_blockers if str(blocker)))
    mixed_count = int(mixed_probe.get("candidate_count") or 0)
    validation_commands = list(SKILL_ROUTE_LOCAL_LANE_COMMANDS)
    if general_rows:
        validation_commands.extend(GENERAL_AGENT_PROJECT_EVAL_COMMANDS)
    if mixed_count:
        validation_commands.extend(MIXED_SKILL_ROUTE_PROBE_COMMANDS)

    status = "ready" if not activation_blockers and boundary.get("status") == "ready" else "review"
    return {
        "controller_surface": "route_activation_preflight",
        "status": status,
        "decision": (
            "bounded_routes_ready_for_local_validation_selection"
            if status == "ready"
            else "review_route_boundary_before_activation"
        ),
        "skill_workflow_count": len(skill_rows),
        "general_agent_project_count": len(general_rows),
        "mixed_skill_workflow_count": mixed_count,
        "skill_route_rows": skill_rows,
        "general_agent_rows": general_rows,
        "allowed_skill_route_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
        "allowed_general_agent_lanes": list(GENERAL_AGENT_PROJECT_EVAL_LANES),
        "activation_blockers": activation_blockers,
        "required_local_validation": sorted(dict.fromkeys(validation_commands)),
        "local_validation_required": True,
        "body_free": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_export_allowed": False,
        "upstream_body_export_allowed": False,
    }


def build_skill_route_pass3_handoff(
    items: list[Any],
    *,
    context_budget: Any = None,
) -> dict[str, Any]:
    """Summarize pass-3 route evidence as a bounded supervisor handoff."""

    candidate_panel = build_skill_route_local_lane_candidates(items)
    general_eval = build_general_agent_project_eval_lane(items)
    activation_preflight = build_route_activation_preflight(items)
    selected_item_ids = sorted(
        {
            str(item_id)
            for item_id in (
                context_budget.get("selected_item_ids", [])
                if isinstance(context_budget, dict)
                else []
            )
            if str(item_id).strip()
        }
    )
    truncated_item_ids = sorted(
        {
            str(item_id)
            for item_id in (
                context_budget.get("truncated_item_ids", [])
                if isinstance(context_budget, dict)
                else []
            )
            if str(item_id).strip()
        }
    )
    skill_rows = [
        {
            "item_id": str(row.get("item_id") or ""),
            "route_class": "skill_workflow",
            "primary_route": "skill_route_discovery",
            "local_lanes": [str(lane) for lane in row.get("local_lanes", [])],
            "route_profiles": [str(profile) for profile in row.get("route_profiles", [])],
            "lane_status": str(row.get("lane_status") or ""),
            "secondary_lane_status": str(row.get("secondary_lane_status") or ""),
            "local_validation_required": True,
            "runtime_action": "none",
        }
        for row in candidate_panel.get("rows", [])
        if isinstance(row, dict)
    ]
    general_rows = [
        {
            "item_id": str(row.get("item_id") or ""),
            "route_class": "general_agent_project",
            "primary_route": "agent_harness_eval_required",
            "allowed_local_lanes": [str(lane) for lane in row.get("allowed_local_lanes", [])],
            "skill_route_discovery_inherited": False,
            "local_validation_required": True,
            "runtime_action": "none",
        }
        for row in general_eval.get("candidates", [])
        if isinstance(row, dict)
    ]
    skill_lanes_bounded = all(
        row["local_lanes"]
        and set(row["local_lanes"]).issubset(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"])
        and row["lane_status"] == "bounded"
        for row in skill_rows
    )
    general_lanes_bounded = all(
        row["allowed_local_lanes"]
        and set(row["allowed_local_lanes"]).issubset(GENERAL_AGENT_PROJECT_EVAL_LANES)
        and row["skill_route_discovery_inherited"] is False
        for row in general_rows
    )
    status = (
        "ready"
        if activation_preflight.get("status") == "ready"
        and skill_lanes_bounded
        and general_lanes_bounded
        else "review"
    )
    return {
        "controller_surface": "skill_route_discovery_pass3_handoff",
        "status": status,
        "decision": (
            "continue_bounded_skill_route_window_before_activation"
            if status == "ready"
            else "review_skill_route_window_before_activation"
        ),
        "capability_pass": "3_of_4",
        "skill_workflow_count": len(skill_rows),
        "general_agent_project_count": len(general_rows),
        "skill_workflow_item_ids": [row["item_id"] for row in skill_rows],
        "general_agent_project_item_ids": [row["item_id"] for row in general_rows],
        "selected_item_ids": selected_item_ids,
        "truncated_item_ids": truncated_item_ids,
        "evidence_ref_scope": "selected_item_ids_only",
        "skill_route_rows": skill_rows,
        "general_agent_rows": general_rows,
        "allowed_skill_route_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
        "allowed_general_agent_lanes": list(GENERAL_AGENT_PROJECT_EVAL_LANES),
        "required_local_validation": [
            str(command)
            for command in activation_preflight.get("required_local_validation", [])
            if str(command).strip()
        ],
        "local_validation_required": True,
        "skill_route_lane_limit_reaffirmed": skill_lanes_bounded,
        "general_agent_eval_split_reaffirmed": general_lanes_bounded,
        "activation_blockers": [
            str(blocker)
            for blocker in activation_preflight.get("activation_blockers", [])
            if str(blocker).strip()
        ],
        "runtime_action": "none",
        "body_free": True,
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_export_allowed": False,
        "upstream_body_export_allowed": False,
    }


def build_skill_route_local_lane_candidates(items: list[Any]) -> dict[str, Any]:
    """Expose skill/workflow evidence as bounded local lanes before activation."""

    rows: list[dict[str, Any]] = []
    allowed_lanes = ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]
    for item in items:
        if not isinstance(item, dict):
            continue
        classification = item.get("route_classification")
        if not isinstance(classification, dict):
            classification = route_metadata_for_digest_item(item)["route_classification"]
        if classification.get("route_class") != "skill_workflow":
            continue

        item_id = str(item.get("item_id") or "")
        source_url = str(item.get("source_url") or "")
        local_lanes = [
            str(lane)
            for lane in classification.get("allowed_lanes", [])
            if str(lane) in allowed_lanes and str(lane) in ROUTE_HINT_PROPOSAL_LANES
        ]
        unsupported_lanes = _unsupported_skill_route_classification_lanes(classification)
        route_probe_decision = str(classification.get("route_probe_decision") or "")
        mixed_probe = route_probe_decision == "skill_route_discovery_first"
        rows.append(
            {
                "item_id": item_id,
                "source_url_hash": stable_hash({"source_url": source_url}) if source_url else "",
                "route_class": "skill_workflow",
                "route_hints": [str(route_hint) for route_hint in classification.get("route_hints", [])],
                "local_lanes": local_lanes,
                "unsupported_lanes": unsupported_lanes,
                "route_profiles": [str(profile) for profile in classification.get("route_profiles", [])],
                "lanes_bounded": (
                    bool(local_lanes)
                    and not unsupported_lanes
                    and set(local_lanes).issubset(allowed_lanes)
                ),
                "lane_status": "blocked_unsupported_lanes" if unsupported_lanes else "bounded",
                "route_probe_decision": route_probe_decision,
                "secondary_lane_status": (
                    "blocked_until_local_corroboration"
                    if mixed_probe
                    else "not_requested"
                ),
                "activation_gate": (
                    "local_skill_route_validation_before_secondary_harness_eval"
                    if mixed_probe
                    else "local_validation_before_activation"
                ),
                "required_local_validation": (
                    list(MIXED_SKILL_ROUTE_PROBE_COMMANDS)
                    if mixed_probe
                    else list(SKILL_ROUTE_LOCAL_LANE_COMMANDS)
                ),
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "raw_source_url_export_allowed": False,
                "upstream_body_export_allowed": False,
            }
        )

    rows_bounded = all(row["lanes_bounded"] for row in rows)
    unsupported_lane_count = sum(1 for row in rows if row["unsupported_lanes"])
    return {
        "controller_surface": "skill_route_local_lane_candidates",
        "candidate_count": len(rows),
        "rows": rows,
        "allowed_local_lanes": list(allowed_lanes),
        "rows_bounded": rows_bounded,
        "unsupported_lane_count": unsupported_lane_count,
        "local_validation_required": True,
        "activation_gate": (
            "local_validation_before_activation"
            if rows_bounded
            else "blocked_before_activation"
        ),
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "raw_source_url_export_allowed": False,
        "upstream_body_export_allowed": False,
    }


def build_mixed_skill_workflow_probe(items: list[Any]) -> dict[str, Any]:
    """Explain lane order for repositories with both skill/workflow and harness signals."""

    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        classification = item.get("route_classification")
        if not isinstance(classification, dict):
            classification = route_metadata_for_digest_item(item)["route_classification"]
        if classification.get("route_class") != "skill_workflow":
            continue
        if classification.get("route_probe_decision") != "skill_route_discovery_first":
            continue
        item_id = str(item.get("item_id") or "")
        source_url = str(item.get("source_url") or "")
        candidates.append(
            {
                "item_id": item_id,
                "source_url_hash": stable_hash({"source_url": source_url}) if source_url else "",
                "route_class": "skill_workflow",
                "route_probe_decision": "skill_route_discovery_first",
                "route_profiles": [str(profile) for profile in classification.get("route_profiles", [])],
                "primary_lane": "skill_route_discovery",
                "secondary_lane": "agent_harness_eval_after_local_corroboration",
                "secondary_lane_status": "blocked_until_local_corroboration",
                "activation_gate": "local_skill_route_validation_before_secondary_harness_eval",
                "allowed_local_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
                "recommended_local_lane_order": [
                    lane
                    for lane in MIXED_SKILL_ROUTE_PROBE_LANE_ORDER
                    if lane in ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]
                ],
                "required_local_validation": list(MIXED_SKILL_ROUTE_PROBE_COMMANDS),
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "denied_actions": list(MIXED_SKILL_ROUTE_PROBE_DENIED_ACTIONS),
            }
        )

    return {
        "controller_surface": "mixed_skill_workflow_probe",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "decision_policy": "skill_route_discovery_first_for_skill_or_workflow_specific_evidence",
        "agent_harness_eval_allowed_after": "local_corroboration_or_general_agent_project_claim",
        "secondary_lane_status": "blocked_until_local_corroboration",
        "activation_gate": "local_skill_route_validation_before_secondary_harness_eval",
        "allowed_local_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
        "recommended_local_lane_order": [
            lane
            for lane in MIXED_SKILL_ROUTE_PROBE_LANE_ORDER
            if lane in ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]
        ],
        "required_local_validation": list(MIXED_SKILL_ROUTE_PROBE_COMMANDS),
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "raw_source_url_export_allowed": False,
        "denied_actions": list(MIXED_SKILL_ROUTE_PROBE_DENIED_ACTIONS),
    }


def build_general_agent_project_eval_lane(items: list[Any]) -> dict[str, Any]:
    """Summarize general agent-project evidence without giving it skill lanes."""

    eval_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        classification = item.get("route_classification")
        if not isinstance(classification, dict):
            classification = route_metadata_for_digest_item(item)["route_classification"]
        if classification.get("route_class") != "general_agent_project":
            continue
        item_id = str(item.get("item_id") or "")
        source_url = str(item.get("source_url") or "")
        eval_items.append(
            {
                "item_id": item_id,
                "source_url_hash": stable_hash({"source_url": source_url}) if source_url else "",
                "route_class": "general_agent_project",
                "evaluation_lane": "agent_harness_eval_required",
                "allowed_local_lanes": list(GENERAL_AGENT_PROJECT_EVAL_LANES),
                "required_local_validation": list(GENERAL_AGENT_PROJECT_EVAL_COMMANDS),
                "skill_route_discovery_inherited": False,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_agent_activation_allowed": False,
            }
        )

    return {
        "controller_surface": "general_agent_project_eval",
        "candidate_count": len(eval_items),
        "candidates": eval_items,
        "allowed_local_lanes": list(GENERAL_AGENT_PROJECT_EVAL_LANES),
        "required_local_validation": list(GENERAL_AGENT_PROJECT_EVAL_COMMANDS),
        "skill_route_discovery_inherited": False,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "raw_source_url_export_allowed": False,
    }


def build_skill_route_boundary_report(items: list[Any]) -> dict[str, Any]:
    """Summarize the split between skill routes and general agent evaluation."""

    skill_rows: list[dict[str, Any]] = []
    general_rows: list[dict[str, Any]] = []
    mixed_rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    skill_lanes = ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]
    general_lanes = GENERAL_AGENT_PROJECT_EVAL_LANES
    for item in items:
        if not isinstance(item, dict):
            continue
        classification = item.get("route_classification")
        if not isinstance(classification, dict):
            classification = route_metadata_for_digest_item(item)["route_classification"]

        item_id = str(item.get("item_id") or "")
        source_url = str(item.get("source_url") or "")
        source_url_hash = stable_hash({"source_url": source_url}) if source_url else ""
        route_class = str(classification.get("route_class") or "unclassified")
        route_probe_decision = str(classification.get("route_probe_decision") or "")

        if route_class == "skill_workflow":
            local_lanes = [
                str(lane)
                for lane in classification.get("allowed_lanes", [])
                if str(lane) in skill_lanes and str(lane) in ROUTE_HINT_PROPOSAL_LANES
            ]
            unsupported_lanes = _unsupported_skill_route_classification_lanes(classification)
            if unsupported_lanes:
                diagnostics.append(f"{item_id}:skill_workflow_unsupported_lanes")
            if not local_lanes:
                diagnostics.append(f"{item_id}:skill_workflow_missing_bounded_lanes")
            row = {
                "item_id": item_id,
                "source_url_hash": source_url_hash,
                "route_class": "skill_workflow",
                "primary_route": "skill_route_discovery",
                "local_lanes": local_lanes,
                "unsupported_lanes": unsupported_lanes,
                "route_profiles": [str(profile) for profile in classification.get("route_profiles", [])],
                "secondary_lane": (
                    "agent_harness_eval_after_local_corroboration"
                    if route_probe_decision == "skill_route_discovery_first"
                    else ""
                ),
                "secondary_lane_status": (
                    "blocked_until_local_corroboration"
                    if route_probe_decision == "skill_route_discovery_first"
                    else "not_requested"
                ),
                "skill_route_discovery_inherited": True,
                "agent_harness_eval_required": False,
                "runtime_action": "none",
                "local_validation_required": True,
            }
            skill_rows.append(row)
            if route_probe_decision == "skill_route_discovery_first":
                mixed_rows.append(row)
            continue

        if route_class == "general_agent_project":
            if "skill_route_discovery" in classification.get("route_hints", []):
                diagnostics.append(f"{item_id}:general_agent_project_inherited_skill_route")
            general_rows.append(
                {
                    "item_id": item_id,
                    "source_url_hash": source_url_hash,
                    "route_class": "general_agent_project",
                    "primary_route": "agent_harness_eval_required",
                    "allowed_local_lanes": list(general_lanes),
                    "skill_route_discovery_inherited": False,
                    "agent_harness_eval_required": True,
                    "runtime_action": "none",
                    "local_validation_required": True,
                }
            )

    status = "ready" if not diagnostics else "review"
    return {
        "controller_surface": "skill_route_boundary_report",
        "status": status,
        "decision": (
            "skill_and_general_agent_routes_split_before_activation"
            if status == "ready"
            else "review_route_boundary_before_activation"
        ),
        "skill_workflow_count": len(skill_rows),
        "general_agent_project_count": len(general_rows),
        "mixed_skill_workflow_count": len(mixed_rows),
        "skill_workflow_rows": skill_rows,
        "general_agent_project_rows": general_rows,
        "allowed_skill_route_lanes": list(skill_lanes),
        "allowed_general_agent_lanes": list(general_lanes),
        "mixed_secondary_lane": "agent_harness_eval_after_local_corroboration",
        "mixed_secondary_lane_status": "blocked_until_local_corroboration",
        "required_local_validation": sorted(
            dict.fromkeys(SKILL_ROUTE_LOCAL_LANE_COMMANDS + GENERAL_AGENT_PROJECT_EVAL_COMMANDS)
        ),
        "diagnostics": diagnostics,
        "local_validation_required": True,
        "body_free": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_export_allowed": False,
        "upstream_body_export_allowed": False,
    }


def build_skill_route_activity_pressure(items: list[Any]) -> dict[str, Any]:
    """Summarize repeated skill repository movement without exporting source URLs."""

    counts = digest_skill_route_activity_counts(items)
    event_kinds_by_key: dict[str, set[str]] = {}
    item_ids_by_key: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        classification = item.get("route_classification")
        if not isinstance(classification, dict):
            classification = route_metadata_for_digest_item(item)["route_classification"]
        if classification.get("route_class") != "skill_workflow":
            continue
        if str(item.get("event_kind") or "") not in SKILL_ROUTE_ACTIVITY_EVENT_KINDS:
            continue
        key = digest_skill_route_project_key(item)
        if not key:
            continue
        event_kinds_by_key.setdefault(key, set()).add(str(item.get("event_kind") or ""))
        item_id = str(item.get("item_id") or "")
        if item_id:
            item_ids_by_key.setdefault(key, []).append(item_id)

    repeated_projects = [
        {
            "project_key_hash": stable_hash({"project_key": key}),
            "activity_count": count,
            "event_kinds": sorted(event_kinds_by_key.get(key, set())),
            "item_ids": list(dict.fromkeys(item_ids_by_key.get(key, []))),
            "allowed_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
            "runtime_action": "none",
            "local_validation_required": True,
        }
        for key, count in sorted(counts.items())
        if count >= 2
    ]
    return {
        "controller_surface": "skill_route_activity_pressure",
        "repeated_project_count": len(repeated_projects),
        "repeated_projects": repeated_projects,
        "allowed_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
    }


def route_metadata_for_digest_item(item: dict[str, Any]) -> dict[str, Any]:
    """Return body-free route metadata for a digest item."""

    classification = classify_digest_item_route(item)
    return {
        "route_hints": list(classification["route_hints"]),
        "route_classification": classification,
    }


def _unsupported_skill_route_classification_lanes(classification: Mapping[str, Any]) -> list[str]:
    if classification.get("route_class") != "skill_workflow":
        return []
    allowed = set(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"])
    return sorted(
        {
            str(lane)
            for lane in classification.get("allowed_lanes", [])
            if str(lane).strip() and str(lane) not in allowed
        }
    )


def classify_digest_item_route(item: dict[str, Any]) -> dict[str, Any]:
    """Classify public digest evidence before proposal lanes are chosen.

    Skill/workflow-specific evidence is allowed to expose only the bounded
    skill-route discovery lanes. General agent-project movement remains visible
    as trend evidence but does not inherit the skill-route lane merely because
    it mentions agents or generic workflow activity.
    """

    text = " ".join(
        str(item.get(key) or "")
        for key in ("event_kind", "summary", "relevance_reason", "recommended_action")
    ).lower()
    route_hints = _route_hints_from_text(text)
    if "skill_route_discovery" in route_hints:
        route_probe_decision = (
            "skill_route_discovery_first"
            if _has_mixed_skill_workflow_probe_signal(text)
            else "skill_route_discovery"
        )
        return {
            "route_class": "skill_workflow",
            "route_hints": route_hints,
            "allowed_lanes": list(ROUTE_HINT_VALIDATION_LANES["skill_route_discovery"]),
            "evaluation_lane": route_probe_decision,
            "route_probe_decision": route_probe_decision,
            "route_profiles": _skill_workflow_route_profiles(text),
            "reasons": _skill_workflow_route_reasons(text),
            "runtime_action": "none",
            "local_validation_required": True,
        }
    if any(term in text for term in GENERAL_AGENT_PROJECT_ROUTE_TERMS):
        return {
            "route_class": "general_agent_project",
            "route_hints": route_hints,
            "allowed_lanes": [],
            "evaluation_lane": "agent_harness_eval_required",
            "reasons": ["agent_project_without_skill_workflow_signal"],
            "runtime_action": "none",
            "local_validation_required": True,
        }
    return {
        "route_class": "unclassified",
        "route_hints": route_hints,
        "allowed_lanes": [],
        "reasons": [],
        "runtime_action": "none",
        "local_validation_required": True,
    }


def route_hints_for_digest_item(item: dict[str, Any]) -> list[str]:
    """Return deterministic proposal lanes suggested by non-sensitive item text."""

    text = " ".join(
        str(item.get(key) or "")
        for key in ("event_kind", "summary", "relevance_reason", "recommended_action")
    ).lower()
    return _route_hints_from_text(text)


def _route_hints_from_text(text: str) -> list[str]:
    hints: list[str] = []
    if _has_skill_workflow_route_signal(text):
        hints.append("skill_route_discovery")
    if any(term in text for term in PROVIDER_CONFIG_ROUTE_TERMS):
        hints.append("provider_config_preflight")
    if any(term in text for term in HARNESS_EVAL_ROUTE_TERMS):
        hints.append("agent_harness_eval")
    if any(term in text for term in GOVERNANCE_POLICY_ROUTE_TERMS):
        hints.append("governance_policy")
    return hints


def _has_skill_workflow_route_signal(text: str) -> bool:
    if any(term in text for term in NEGATED_SKILL_WORKFLOW_TERMS) and not any(
        term in text for term in CONCRETE_SKILL_WORKFLOW_TERMS
    ):
        return False
    if any(term in text for term in SKILL_WORKFLOW_ROUTE_TERMS):
        return True
    return "workflow" in text and any(term in text for term in SKILL_WORKFLOW_CONTEXT_TERMS)


def _skill_workflow_route_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    if any(term in text for term in SKILL_WORKFLOW_ROUTE_TERMS):
        reasons.append("skill_term")
    if "workflow" in text and any(term in text for term in SKILL_WORKFLOW_CONTEXT_TERMS):
        reasons.append("workflow_context_term")
    if _has_mixed_skill_workflow_probe_signal(text):
        reasons.append("mixed_skill_workflow_probe")
    return reasons or ["skill_workflow_route_signal"]


def _skill_workflow_route_profiles(text: str) -> list[str]:
    """Classify the local validation profile for skill-route evidence."""

    profiles = [
        profile
        for profile, keywords in SKILL_ROUTE_PROFILE_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    return profiles or ["generic_skill_workflow"]


def _has_mixed_skill_workflow_probe_signal(text: str) -> bool:
    """Detect skill/workflow repos that also look like local harness-eval candidates."""

    if not _has_skill_workflow_route_signal(text):
        return False
    return any(term in text for term in HARNESS_EVAL_ROUTE_TERMS) or any(
        term in text
        for term in (
            "codex",
            "evals",
            "examples",
            "plugin",
            "plugins",
            "test",
            "tests",
        )
    )


def rank_digest_items_for_context_budget(items: Any) -> list[dict[str, Any]]:
    """Prioritize evidence before context truncation while preserving deterministic tie order."""

    return [item for _, item in rank_digest_item_entries_for_context_budget(items)]


def rank_digest_item_entries_for_context_budget(items: Any) -> list[tuple[int, dict[str, Any]]]:
    """Return ranked digest items with their original zero-based index."""

    if not isinstance(items, list):
        return []

    review_activity_by_repo = digest_review_activity_counts(items)
    skill_route_activity_by_project = digest_skill_route_activity_counts(items)
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
        ) + digest_skill_route_activity_confidence_bonus(
            item,
            skill_route_activity_by_project=skill_route_activity_by_project,
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


def digest_skill_route_activity_counts(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("event_kind") or "") not in SKILL_ROUTE_ACTIVITY_EVENT_KINDS:
            continue
        classification = classify_digest_item_route(item)
        if classification.get("route_class") != "skill_workflow":
            continue
        project_key = digest_skill_route_project_key(item)
        if project_key:
            counts[project_key] = counts.get(project_key, 0) + 1
    return counts


def digest_skill_route_activity_confidence_bonus(
    item: dict[str, Any],
    *,
    skill_route_activity_by_project: dict[str, int],
) -> float:
    if str(item.get("event_kind") or "") not in SKILL_ROUTE_ACTIVITY_EVENT_KINDS:
        return 0.0
    classification = classify_digest_item_route(item)
    if classification.get("route_class") != "skill_workflow":
        return 0.0
    activity_count = skill_route_activity_by_project.get(digest_skill_route_project_key(item), 0)
    if activity_count < 2:
        return 0.0
    return min(0.18, 0.06 * (activity_count - 1))


def digest_skill_route_project_key(item: dict[str, Any]) -> str:
    repo = digest_item_repo(item).lower()
    if "/" in repo:
        repo_name = repo.rsplit("/", 1)[-1]
        if repo_name:
            return repo_name
    text = f"{item.get('source_url') or ''} {item.get('summary') or ''}".lower()
    match = re.search(r"github\.com/[^/\s]+/([^/\s#?]+)", text)
    if match:
        return match.group(1)
    name_match = re.search(r"\b([a-z0-9_.-]*skills[a-z0-9_.-]*)\b", text)
    return name_match.group(1) if name_match else repo


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
    selected_generic_push_count = 0
    truncated_generic_push_count = 0
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
            if digest_item_has_generic_push_detail(raw_item):
                selected_generic_push_count += 1
        elif item_id in truncated_item_ids:
            truncated_event_kind_counts[event_kind] = truncated_event_kind_counts.get(event_kind, 0) + 1
            if digest_item_has_generic_pull_request_detail(raw_item):
                truncated_generic_pr_count += 1
                cluster_key = digest_generic_pr_cluster_key(raw_item)
                if cluster_key:
                    truncated_generic_pr_cluster_keys.add(cluster_key)
            if digest_item_has_generic_push_detail(raw_item):
                truncated_generic_push_count += 1

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
    if selected_generic_push_count or truncated_generic_push_count:
        reasons.append("generic_push_items_have_missing_validation_or_route_detail")
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
        "selected_generic_push_count": selected_generic_push_count,
        "truncated_generic_push_count": truncated_generic_push_count,
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


def digest_item_has_generic_push_detail(item: dict[str, Any]) -> bool:
    """Return whether a push item is only activity/freshness evidence."""

    event_kind = str(item.get("event_kind") or "")
    if event_kind != "PushEvent":
        return False
    text = f"{item.get('summary') or ''} {item.get('relevance_reason') or ''}".lower()
    if not text.strip():
        return True
    concrete_validation_terms = (
        "e2e",
        "test(",
        "test:",
        "tests",
        "tested",
        "validation",
        "validate",
        "review finding",
        "reviewed",
        "harness",
        "preflight",
        "fixture",
        "coverage",
    )
    if any(term in text for term in concrete_validation_terms):
        return False
    generic_push_terms = (
        "generic",
        "workflow polish",
        "activity",
        "freshness",
        "missing test evidence",
        "low-detail",
        "low detail",
    )
    if any(term in text for term in generic_push_terms):
        return True
    main_branch_generic_terms = ("chore", "misc", "polish", "sync", "update", "updates")
    return "main" in text and any(term in text for term in main_branch_generic_terms)


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
    errors.extend(candidate_low_detail_movement_evidence_errors(kind, evidence_refs, items_by_id))
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
    elif candidate_requires_missing_detail_uncertainty(
        kind,
        evidence_refs,
        items_by_id,
        evidence_truncation_uncertainty,
    ) and not uncertainty_mentions_missing_detail_risk(uncertainty):
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


def candidate_low_detail_movement_evidence_errors(
    kind: str,
    evidence_refs: list[str],
    items_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Reject behavior proposals supported only by generic activity metadata."""

    if kind in {"follow_up_issue", "no_action"}:
        return []
    known_refs = [ref for ref in evidence_refs if ref in items_by_id]
    if not known_refs:
        return []
    low_detail_refs = [
        ref
        for ref in known_refs
        if (
            digest_item_has_generic_pull_request_detail(items_by_id[ref])
            or digest_item_has_generic_push_detail(items_by_id[ref])
        )
    ]
    if len(low_detail_refs) != len(known_refs):
        return []
    return [
        "generic push or untitled pull request/review evidence requires a non-generic corroborating item "
        "before behavior proposals"
    ]


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
    evidence_refs: list[str],
    items_by_id: dict[str, dict[str, Any]],
    evidence_truncation_uncertainty: dict[str, Any] | None,
) -> bool:
    """Return whether a proposal must explicitly carry context-budget inference limits."""

    if kind in {"follow_up_issue", "no_action"}:
        return False
    if not isinstance(evidence_truncation_uncertainty, dict):
        return False
    if not evidence_truncation_uncertainty.get("missing_detail_risk"):
        return False
    reasons = {
        str(reason)
        for reason in evidence_truncation_uncertainty.get("reasons", [])
        if str(reason).strip()
    }
    generic_selected_reasons = {
        "generic_or_untitled_pull_request_items_have_missing_title_context",
        "generic_push_items_have_missing_validation_or_route_detail",
    }
    if reasons and reasons <= generic_selected_reasons:
        return any(
            ref in items_by_id
            and (
                digest_item_has_generic_pull_request_detail(items_by_id[ref])
                or digest_item_has_generic_push_detail(items_by_id[ref])
            )
            for ref in evidence_refs
        )
    return True


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
