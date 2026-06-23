"""Deterministic local skill routing helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


EXACT_TRIGGER_MATCH = "exact_trigger"
TOPICAL_MATCH = "topical_match"
NO_SKILL_MATCH = "no_match"
AMBIGUOUS_SKILL_MATCH = "ambiguous_match"
SKILL_ROUTE_DISCOVERY_HINT = "skill_route_discovery"
SKILL_ROUTE_DISCOVERY_ALLOWED_LANES = ("documentation", "config", "test", "code_patch")
SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS: Mapping[str, tuple[str, ...]] = {
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
SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS = ("github.com", "www.github.com")
SKILL_ROUTE_DISCOVERY_ALLOWED_EVENTS = (
    "pull_request",
    "repository_created",
    "repository_updated",
    "repository_deleted",
    "push",
    "release",
    "unknown",
)
SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS = (
    "clone_and_run",
    "delete_local_skill",
    "enable",
    "execute",
    "install",
    "run",
)
SKILL_ROUTE_DISCOVERY_TRIGGER_TERMS = ("agent", "agents", "codex", "skill", "skills", "workflow")
SKILL_ROUTE_DISCOVERY_MIXED_REQUIRED_TERMS = ("codex", "workflow")
SKILL_ROUTE_DISCOVERY_MIXED_SKILL_TERMS = ("skill", "skills")
SKILL_ROUTE_DISCOVERY_MIXED_AGENT_TERMS = ("agent", "agents")
SKILL_ROUTE_DISCOVERY_MIXED_LANE_ORDER = ("test", "documentation", "config", "code_patch")
SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES = (
    "skill_term",
    "mixed_skill_workflow_probe",
    "generic_skill_workflow",
    "skill_ecosystem_state_handoff",
    "game_frontend_workflow",
    "codex_workflow_gate",
)
SKILL_ROUTE_DISCOVERY_DISABLED = "candidate_disabled"
SKILL_ROUTE_DISCOVERY_INVALID = "invalid_candidate"
SKILL_ROUTE_DISCOVERY_PROPOSAL_LANE = "proposal_lane"
SKILL_ROUTE_DISCOVERY_REJECTED = "rejected_candidate"
SKILL_ROUTE_DISCOVERY_DOWNGRADED = "downgraded_candidate"
SKILL_ROUTE_DISCOVERY_LANE_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "documentation": (
        "agent",
        "director",
        "guide",
        "markdown",
        "prompt",
        "readme",
        "skill",
        "workflow",
    ),
    "config": (
        "config",
        "ecosystem",
        "frontmatter",
        "metadata",
        "profile",
        "route",
        "routing",
        "skill.md",
        "skills.sh.json",
    ),
    "test": (
        "audit",
        "evidence",
        "gate",
        "qa",
        "review",
        "test",
        "validation",
        "verification",
        "verify",
    ),
    "code_patch": (
        "codex",
        "debug",
        "helper",
        "plugin",
        "scaffold",
        "script",
        "tool",
        "workflow",
    ),
}
SKILL_ROUTE_DISCOVERY_LAYOUT_SIGNAL_LANES: Mapping[str, tuple[str, ...]] = {
    "skill_markdown": ("documentation", "config"),
    "skill_directory": ("documentation", "config"),
    "agent_metadata": ("config",),
    "skill_registry_metadata": ("config",),
    "validation_script": ("test", "code_patch"),
    "test_file": ("test",),
    "scaffold_asset": ("code_patch",),
    "template_or_prompt": ("documentation", "code_patch"),
    "qa_checklist": ("documentation", "test"),
}
SKILL_ROUTE_DISCOVERY_ROUTE_PROFILE_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "codex_workflow_gate": (
        "codex",
        "evidence gate",
        "fablecodex",
        "plugin",
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
    "source_cited_domain_research": (
        "advice",
        "advisory",
        "citation",
        "cited",
        "domain research",
        "fund",
        "investment",
        "research",
        "source-cited",
        "sourced",
        "traceable",
        "views",
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
SKILL_ROUTE_DISCOVERY_ROUTE_PROFILE_VALIDATION_CONTRACTS: Mapping[str, Mapping[str, Any]] = {
    "codex_workflow_gate": {
        "validation_gate": "skill_route_discovery_first_before_workflow_gate",
        "preferred_lanes": ("test", "documentation", "config", "code_patch"),
        "required_metadata": (
            "skill_route_discovery_first",
            "body_free_workflow_summary",
            "local_gate_or_test_target",
        ),
        "blocked_activation_reason": "secondary_workflow_gate_blocked_until_local_corroboration",
    },
    "game_frontend_workflow": {
        "validation_gate": "local_frontend_validation_before_game_skill_activation",
        "preferred_lanes": ("test", "documentation", "code_patch", "config"),
        "required_metadata": (
            "body_free_game_skill_summary",
            "local_frontend_validation_target",
            "asset_or_provider_boundary_note",
        ),
        "blocked_activation_reason": "upstream_scaffold_or_provider_boundary_not_validated",
    },
    "skill_ecosystem_state_handoff": {
        "validation_gate": "state_handoff_boundary_before_profile_or_memory_write",
        "preferred_lanes": ("config", "test", "documentation", "code_patch"),
        "required_metadata": (
            "state_retention_boundary",
            "privacy_boundary",
            "local_target_metadata_only",
        ),
        "blocked_activation_reason": "profile_or_memory_write_blocked_until_local_boundary_validation",
    },
    "source_cited_domain_research": {
        "validation_gate": "source_citation_and_advice_boundary_before_domain_skill_activation",
        "preferred_lanes": ("test", "documentation", "config", "code_patch"),
        "required_metadata": (
            "body_free_domain_research_summary",
            "source_citation_boundary",
            "advice_disclaimer_boundary",
            "local_evidence_replay_target",
        ),
        "blocked_activation_reason": "domain_research_skill_blocked_until_citation_and_advice_boundaries_are_validated",
    },
    "generic_skill_workflow": {
        "validation_gate": "generic_skill_workflow_local_validation_before_activation",
        "preferred_lanes": ("documentation", "test", "config", "code_patch"),
        "required_metadata": (
            "selected_digest_item_ids_or_frozen_digest_evidence",
            "body_free_repository_summary",
            "local_artifact_target",
        ),
        "blocked_activation_reason": "generic_skill_evidence_requires_local_corroboration",
    },
}

VALIDATION_WEIGHTS: Mapping[str, int] = {
    "validated": 12,
    "tested": 10,
    "documented": 6,
    "experimental": 3,
    "unknown": 0,
    "unvalidated": 0,
    "review_only": -20,
    "blocked": -50,
}


@dataclass(frozen=True)
class SkillDescriptor:
    """Inspectable metadata for a locally available agent skill."""

    name: str
    description: str = ""
    trigger_terms: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    validation_status: str = "unknown"
    enabled: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SkillDescriptor":
        """Load a descriptor from runtime metadata without accepting ambiguous shapes."""

        name = str(value.get("name") or "").strip()
        if not name:
            raise ValueError("skill metadata requires a non-empty name")
        return cls(
            name=name,
            description=str(value.get("description") or ""),
            trigger_terms=_string_tuple(value.get("trigger_terms")),
            domains=_string_tuple(value.get("domains")),
            validation_status=str(value.get("validation_status") or "unknown").strip().lower(),
            enabled=bool(value.get("enabled", True)),
        )


@dataclass(frozen=True)
class ExternalSkillRouteCandidate:
    """Metadata for an observed external skill package before local enablement.

    These candidates are discovery records only. They preserve enough public
    evidence for proposal routing without turning an external repository into an
    executable local skill.
    """

    name: str
    source_url: str
    evidence_summary: str = ""
    discovery_event_kind: str = "unknown"
    route_hints: tuple[str, ...] = (SKILL_ROUTE_DISCOVERY_HINT,)
    candidate_lanes: tuple[str, ...] = SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    evidence_item_ids: tuple[str, ...] = ()
    evidence_urls: tuple[str, ...] = ()
    evidence_item_urls: tuple[str, ...] = ()
    related_source_urls: tuple[str, ...] = ()
    source_layout_signals: tuple[str, ...] = ()
    source_metadata_signals: tuple[str, ...] = ()
    requested_actions: tuple[str, ...] = ()
    validation_status: str = "unvalidated"
    enabled: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExternalSkillRouteCandidate":
        name = str(value.get("name") or "").strip()
        source_url = str(value.get("source_url") or "").strip()
        if not name:
            raise ValueError("external skill route candidate requires a non-empty name")
        if not source_url:
            raise ValueError("external skill route candidate requires a non-empty source_url")
        return cls(
            name=name,
            source_url=source_url,
            evidence_summary=str(value.get("evidence_summary") or ""),
            discovery_event_kind=_normalize_discovery_event(value.get("discovery_event_kind")),
            route_hints=_string_tuple(value.get("route_hints")) or (SKILL_ROUTE_DISCOVERY_HINT,),
            candidate_lanes=_string_tuple(value.get("candidate_lanes")) or SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
            evidence_item_ids=_string_tuple(value.get("evidence_item_ids")),
            evidence_urls=_string_tuple(value.get("evidence_urls")),
            evidence_item_urls=_string_tuple(value.get("evidence_item_urls")),
            related_source_urls=_string_tuple(value.get("related_source_urls")),
            source_layout_signals=_string_tuple(
                value.get("source_layout_signals")
                or value.get("layout_signals")
                or value.get("file_layout_signals")
            ),
            source_metadata_signals=_string_tuple(
                value.get("source_metadata_signals")
                or value.get("metadata_signals")
                or value.get("repository_metadata_signals")
            ),
            requested_actions=_string_tuple(value.get("requested_actions")),
            validation_status=str(value.get("validation_status") or "unvalidated").strip().lower(),
            enabled=bool(value.get("enabled", False)),
        )

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        source_error = _validate_public_github_source_url(self.source_url)
        if source_error:
            errors.append(source_error)
        if self.enabled:
            errors.append("external_skill_route_candidates_must_start_disabled")
        if SKILL_ROUTE_DISCOVERY_HINT not in self.route_hints:
            errors.append(f"route_hints must include {SKILL_ROUTE_DISCOVERY_HINT}")
        if self.discovery_event_kind not in SKILL_ROUTE_DISCOVERY_ALLOWED_EVENTS:
            errors.append(f"unsupported_discovery_event_kind:{self.discovery_event_kind}")
        for related_source_url in self.related_source_urls:
            related_source_error = _validate_public_github_source_url(related_source_url)
            if related_source_error:
                errors.append(f"related_source_url:{related_source_error}")
        unsupported_lanes = sorted(set(self.candidate_lanes) - set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES))
        if unsupported_lanes:
            errors.append("unsupported_candidate_lanes:" + ",".join(unsupported_lanes))
        blocked_actions = sorted(set(self.requested_actions) & set(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS))
        if blocked_actions:
            errors.append("blocked_discovery_actions:" + ",".join(blocked_actions))
        return tuple(errors)

    def to_registry_entry(self) -> dict[str, Any]:
        errors = self.validation_errors()
        candidate_lanes = tuple(lane for lane in self.candidate_lanes if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        uncertainty_reasons = _candidate_uncertainty_reasons(self)
        return {
            "candidate_lanes": list(candidate_lanes),
            "discovery_event_kind": self.discovery_event_kind,
            "discovery_event_effect": _discovery_event_effect(self.discovery_event_kind),
            "enabled": self.enabled,
            "evidence_item_ids": list(dict.fromkeys(self.evidence_item_ids)),
            "evidence_item_urls": list(dict.fromkeys(self.evidence_item_urls)),
            "evidence_urls": list(dict.fromkeys(self.evidence_urls or (self.source_url,))),
            "evidence_summary": self.evidence_summary,
            "name": self.name,
            "related_source_urls": list(dict.fromkeys(self.related_source_urls)),
            "requested_actions": list(self.requested_actions),
            "route_profiles": list(_skill_route_discovery_route_profiles(self)),
            "route_hints": list(self.route_hints),
            "matched_route_terms": list(
                _skill_route_discovery_matched_terms(
                    self.name,
                    self.evidence_summary,
                    " ".join(self.candidate_lanes),
                    " ".join(self.source_layout_signals),
                    " ".join(self.source_metadata_signals),
                )
            ),
            "route_status": SKILL_ROUTE_DISCOVERY_INVALID if errors else SKILL_ROUTE_DISCOVERY_DISABLED,
            "source_url": self.source_url,
            "uncertainty": _candidate_uncertainty_message(uncertainty_reasons),
            "uncertainty_reasons": list(uncertainty_reasons),
            "validation_errors": list(errors),
            "validation_status": self.validation_status,
            **_optional_list_field("source_layout_signals", self.source_layout_signals),
            **_optional_list_field("source_metadata_signals", self.source_metadata_signals),
        }


@dataclass(frozen=True)
class ExternalSkillRepositorySummary:
    """Body-free public repository summary used to classify skill-route evidence."""

    name: str
    source_url: str
    summary: str
    discovery_event_kind: str = "unknown"
    topics: tuple[str, ...] = ()
    suggested_lanes: tuple[str, ...] = ()
    observed_paths: tuple[str, ...] = ()
    metadata_files: tuple[str, ...] = ()
    upstream_source_url: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExternalSkillRepositorySummary":
        source_url = str(value.get("source_url") or "").strip()
        name = str(value.get("name") or "").strip() or _repository_name_from_url(source_url)
        summary = str(value.get("summary") or value.get("evidence_summary") or "").strip()
        if not name:
            raise ValueError("external skill repository summary requires a non-empty name or source_url")
        if not source_url:
            raise ValueError("external skill repository summary requires a non-empty source_url")
        if not summary:
            raise ValueError("external skill repository summary requires a non-empty summary")
        return cls(
            name=name,
            source_url=source_url,
            summary=summary,
            discovery_event_kind=_normalize_discovery_event(value.get("discovery_event_kind")),
            topics=_string_tuple(value.get("topics")),
            suggested_lanes=_string_tuple(value.get("suggested_lanes")),
            observed_paths=_string_tuple(
                value.get("observed_paths")
                or value.get("file_paths")
                or value.get("paths")
            ),
            metadata_files=_string_tuple(
                value.get("metadata_files")
                or value.get("manifest_files")
                or value.get("repository_metadata_files")
            ),
            upstream_source_url=str(
                value.get("upstream_source_url")
                or value.get("forked_from_url")
                or value.get("parent_source_url")
                or ""
            ).strip(),
        )

    def to_candidate(self) -> ExternalSkillRouteCandidate | None:
        if not _looks_like_skill_repository_summary(self):
            return None
        return ExternalSkillRouteCandidate(
            name=self.name,
            source_url=self.source_url,
            evidence_summary=self.summary,
            discovery_event_kind=self.discovery_event_kind,
            candidate_lanes=_bounded_skill_discovery_lanes(self),
            related_source_urls=_summary_related_source_urls(self),
            source_layout_signals=_skill_repository_layout_signals(self),
            source_metadata_signals=_skill_repository_metadata_signals(self),
            validation_status="unvalidated",
            enabled=False,
        )


@dataclass(frozen=True)
class ExternalSkillEvidenceItem:
    """Body-free repository or issue signal used for skill-route discovery.

    Issue signals are folded into their repository candidate because one issue
    should refine the local lane choice, not create an executable skill route.
    """

    source_url: str
    item_id: str = ""
    title: str = ""
    summary: str = ""
    item_kind: str = "repository"
    name: str = ""
    discovery_event_kind: str = "unknown"
    route_hints: tuple[str, ...] = (SKILL_ROUTE_DISCOVERY_HINT,)
    topics: tuple[str, ...] = ()
    suggested_lanes: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExternalSkillEvidenceItem":
        source_url = str(value.get("source_url") or value.get("url") or "").strip()
        if not source_url:
            raise ValueError("external skill evidence item requires a non-empty source_url")
        return cls(
            source_url=source_url,
            item_id=str(value.get("item_id") or "").strip(),
            title=str(value.get("title") or "").strip(),
            summary=str(value.get("summary") or value.get("evidence_summary") or "").strip(),
            item_kind=_normalize_evidence_item_kind(value.get("item_kind") or value.get("kind")),
            name=str(value.get("name") or "").strip(),
            discovery_event_kind=_normalize_discovery_event(value.get("discovery_event_kind")),
            route_hints=_string_tuple(value.get("route_hints")) or (SKILL_ROUTE_DISCOVERY_HINT,),
            topics=_string_tuple(value.get("topics")),
            suggested_lanes=_string_tuple(value.get("suggested_lanes")),
        )

    def canonical_repository_url(self) -> str:
        return _canonical_public_github_repository_url(self.source_url)

    def evidence_url(self) -> str:
        return _canonical_public_github_evidence_url(self.source_url)

    def to_summary(self) -> ExternalSkillRepositorySummary | None:
        if SKILL_ROUTE_DISCOVERY_HINT not in self.route_hints:
            return None
        text = " ".join(part for part in (self.title, self.summary) if part).strip()
        if not text:
            raise ValueError("external skill evidence item requires a title or summary")
        repository_url = self.canonical_repository_url()
        return ExternalSkillRepositorySummary(
            name=self.name or _repository_name_from_url(repository_url),
            source_url=repository_url,
            summary=text,
            discovery_event_kind=self.discovery_event_kind,
            topics=self.topics,
            suggested_lanes=self.suggested_lanes,
        )


@dataclass(frozen=True)
class SkillRouteDecision:
    """Ranking result for one skill against one task prompt."""

    descriptor: SkillDescriptor
    route: str
    score: int
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": list(self.descriptor.domains),
            "name": self.descriptor.name,
            "reasons": list(self.reasons),
            "route": self.route,
            "score": self.score,
            "validation_status": self.descriptor.validation_status,
        }


@dataclass(frozen=True)
class SkillRouteSelection:
    """Controller-facing skill choice that keeps ambiguity inspectable."""

    selected: SkillRouteDecision | None
    route: str
    ranked: tuple[SkillRouteDecision, ...] = ()
    ambiguous_candidates: tuple[SkillRouteDecision, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ambiguous_candidates": [decision.to_dict() for decision in self.ambiguous_candidates],
            "diagnostics": list(self.diagnostics),
            "ranked": [decision.to_dict() for decision in self.ranked],
            "route": self.route,
            "selected": self.selected.to_dict() if self.selected else None,
        }


def rank_skills_for_task(
    task: str,
    skills: Sequence[SkillDescriptor | Mapping[str, Any]],
    *,
    include_no_match: bool = True,
) -> tuple[SkillRouteDecision, ...]:
    """Rank skill metadata by explicit triggers, task domains, and validation status.

    Explicit trigger or skill-name matches intentionally dominate topical matches.
    Validation status is a tie-breaker within a match class so an unvalidated topical
    skill cannot outrank an explicitly requested skill.
    """

    descriptors = tuple(_coerce_skill_descriptor(skill) for skill in skills)
    decisions = tuple(_rank_skill_for_task(task, descriptor) for descriptor in descriptors)
    if not include_no_match:
        decisions = tuple(decision for decision in decisions if decision.route != NO_SKILL_MATCH)
    return tuple(
        sorted(
            decisions,
            key=lambda decision: (
                -_route_weight(decision.route),
                -decision.score,
                decision.descriptor.name.casefold(),
            ),
        )
    )


def select_skill_for_task(
    task: str,
    skills: Sequence[SkillDescriptor | Mapping[str, Any]],
) -> SkillRouteSelection:
    """Select one clear skill route, or return an explicit no-match/ambiguous result.

    The ranked list remains available for audit, but tied top matches are not
    silently resolved by alphabetical order because that would hide an invocation
    that should be reviewed or clarified by the caller.
    """

    ranked = rank_skills_for_task(task, skills, include_no_match=False)
    if not ranked:
        return SkillRouteSelection(
            selected=None,
            route=NO_SKILL_MATCH,
            diagnostics=("no_skills_matched",),
        )

    top = ranked[0]
    ambiguous_candidates = tuple(
        decision
        for decision in ranked
        if _route_weight(decision.route) == _route_weight(top.route) and decision.score == top.score
    )
    if len(ambiguous_candidates) > 1:
        names = ",".join(decision.descriptor.name for decision in ambiguous_candidates)
        return SkillRouteSelection(
            selected=None,
            route=AMBIGUOUS_SKILL_MATCH,
            ranked=ranked,
            ambiguous_candidates=ambiguous_candidates,
            diagnostics=(f"ambiguous_top_skill_match:{names}",),
        )

    return SkillRouteSelection(
        selected=top,
        route=top.route,
        ranked=ranked,
    )


def build_skill_routing_index(
    skills: Sequence[SkillDescriptor | Mapping[str, Any]],
) -> dict[str, Any]:
    """Return stable metadata for auditing the local skill routing surface."""

    descriptors = tuple(_coerce_skill_descriptor(skill) for skill in skills)
    return {
        "schema_version": 1,
        "skill_count": len(descriptors),
        "skills": [
            {
                "domains": list(descriptor.domains),
                "enabled": descriptor.enabled,
                "name": descriptor.name,
                "trigger_terms": list(descriptor.trigger_terms),
                "validation_status": descriptor.validation_status,
            }
            for descriptor in sorted(descriptors, key=lambda item: item.name.casefold())
        ],
    }


def build_skill_route_discovery_registry(
    candidates: Sequence[ExternalSkillRouteCandidate | Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a disabled-by-default registry for external skill discovery signals."""

    descriptors = tuple(_coerce_external_skill_route_candidate(candidate) for candidate in candidates)
    entries = [candidate.to_registry_entry() for candidate in sorted(descriptors, key=lambda item: item.name.casefold())]
    invalid_count = sum(1 for entry in entries if entry["route_status"] == SKILL_ROUTE_DISCOVERY_INVALID)
    return {
        "schema_version": 1,
        "allowed_candidate_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "allowed_source_hosts": list(SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS),
        "blocked_discovery_actions": list(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS),
        "candidate_count": len(entries),
        "enabled_candidate_count": sum(1 for entry in entries if entry["enabled"]),
        "executable_skill_count": 0,
        "invalid_candidate_count": invalid_count,
        "registry_status": "invalid_candidates_present" if invalid_count else "classification_only",
        "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
        "candidates": entries,
    }


def build_skill_route_discovery_registry_from_summaries(
    summaries: Sequence[ExternalSkillRepositorySummary | Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify public repository summaries into disabled skill-route candidates.

    The classifier is intentionally body-free: repository summaries may influence
    only the bounded local work lanes, never installation, execution, deletion,
    or enablement.
    """

    candidates_by_lineage: dict[str, ExternalSkillRouteCandidate] = {}
    duplicate_summary_count = 0
    for summary in summaries:
        descriptor = _coerce_external_skill_repository_summary(summary)
        candidate = descriptor.to_candidate()
        if candidate is not None:
            lineage_key = _summary_lineage_key(descriptor)
            existing = candidates_by_lineage.get(lineage_key)
            if existing is None:
                candidates_by_lineage[lineage_key] = candidate
                continue
            duplicate_summary_count += 1
            candidates_by_lineage[lineage_key] = _merge_external_skill_route_candidates(existing, candidate)
    registry = build_skill_route_discovery_registry(tuple(candidates_by_lineage.values()))
    registry["summary_count"] = len(summaries)
    registry["ignored_summary_count"] = len(summaries) - len(candidates_by_lineage) - duplicate_summary_count
    registry["duplicate_summary_count"] = duplicate_summary_count
    return registry


def build_skill_route_discovery_registry_from_evidence_items(
    items: Sequence[ExternalSkillEvidenceItem | Mapping[str, Any]],
) -> dict[str, Any]:
    """Classify repository or issue evidence into deduplicated disabled candidates."""

    grouped: dict[str, dict[str, Any]] = {}
    ignored_count = 0
    duplicate_count = 0
    seen_evidence_urls: set[str] = set()

    for item in items:
        evidence_item = _coerce_external_skill_evidence_item(item)
        summary = evidence_item.to_summary()
        if summary is None or not _looks_like_skill_repository_summary(summary):
            ignored_count += 1
            continue

        repository_url = summary.source_url
        bucket = grouped.setdefault(
            repository_url,
            {
                "discovery_event_kind": summary.discovery_event_kind,
                "evidence_urls": [],
                "item_ids": [],
                "lanes": [],
                "name": summary.name,
                "summaries": [],
            },
        )
        if evidence_item.item_id:
            bucket["item_ids"].append(evidence_item.item_id)

        evidence_url = evidence_item.evidence_url()
        if evidence_url in seen_evidence_urls:
            duplicate_count += 1
            continue
        seen_evidence_urls.add(evidence_url)

        bucket["evidence_urls"].append(evidence_url)
        bucket["lanes"].extend(_bounded_skill_discovery_lanes(summary))
        bucket["summaries"].append(summary.summary)

    candidates = [
        ExternalSkillRouteCandidate(
            name=str(bucket["name"]),
            source_url=repository_url,
            evidence_summary=" ".join(dict.fromkeys(bucket["summaries"])),
            discovery_event_kind=str(bucket["discovery_event_kind"]),
            candidate_lanes=tuple(dict.fromkeys(bucket["lanes"])) or ("documentation",),
            evidence_item_ids=tuple(dict.fromkeys(bucket["item_ids"])),
            evidence_item_urls=tuple(bucket["evidence_urls"]),
            evidence_urls=tuple(bucket["evidence_urls"]),
            validation_status="unvalidated",
            enabled=False,
        )
        for repository_url, bucket in grouped.items()
    ]
    registry = build_skill_route_discovery_registry(candidates)
    registry["evidence_item_count"] = len(items)
    registry["ignored_evidence_item_count"] = ignored_count
    registry["duplicate_evidence_item_count"] = duplicate_count
    return registry


def build_skill_route_discovery_proposal_lane_map(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a disabled discovery registry into bounded local proposal lanes.

    This is the controller-facing view of external skill evidence. It never
    enables, installs, executes, or deletes a skill; it only exposes local work
    lanes that can become documentation, config, test, or code_patch proposals.
    """

    candidates = registry.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ValueError("skill route discovery registry requires a candidates sequence")

    proposal_lanes: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    downgraded_candidates: list[dict[str, Any]] = []
    candidate_lane_inventory: list[dict[str, Any]] = []
    for raw_candidate in candidates:
        if not isinstance(raw_candidate, Mapping):
            rejected_candidates.append(
                {
                    "name": "",
                    "source_url": "",
                    "status": SKILL_ROUTE_DISCOVERY_REJECTED,
                    "reason": "candidate_entry_must_be_an_object",
                    "validation_errors": ["candidate_entry_must_be_an_object"],
                }
            )
            continue

        candidate = dict(raw_candidate)
        name = str(candidate.get("name") or "")
        source_url = str(candidate.get("source_url") or "")
        validation_errors = [str(error) for error in candidate.get("validation_errors", []) if str(error).strip()]
        allowed_lanes = [
            str(lane)
            for lane in candidate.get("candidate_lanes", [])
            if str(lane) in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        unsupported_lanes = _unsupported_lanes_from_validation_errors(validation_errors)
        hard_errors = [
            error
            for error in validation_errors
            if not error.startswith("unsupported_candidate_lanes:")
        ]

        if hard_errors:
            rejected_candidates.append(
                {
                    "name": name,
                    "source_url": source_url,
                    "status": SKILL_ROUTE_DISCOVERY_REJECTED,
                    "reason": "candidate_has_non_lane_validation_errors",
                    "validation_errors": validation_errors,
                }
            )
            continue

        if unsupported_lanes:
            downgraded_candidates.append(
                {
                    "name": name,
                    "source_url": source_url,
                    "status": SKILL_ROUTE_DISCOVERY_DOWNGRADED,
                    "allowed_lanes": allowed_lanes,
                    "rejected_lanes": unsupported_lanes,
                    "reason": "unsupported_candidate_lanes_removed",
                    "validation_errors": validation_errors,
                }
            )

        if not allowed_lanes:
            rejected_candidates.append(
                {
                    "name": name,
                    "source_url": source_url,
                    "status": SKILL_ROUTE_DISCOVERY_REJECTED,
                    "reason": "candidate_has_no_allowed_proposal_lanes",
                    "validation_errors": validation_errors,
                }
            )
            continue

        uncertainty_reasons = _string_list(candidate.get("uncertainty_reasons"))
        probe_metadata = _skill_route_discovery_mixed_probe_metadata(candidate, allowed_lanes)
        state_boundary_metadata = _skill_route_discovery_state_boundary_metadata(candidate)
        domain_research_boundary_metadata = _skill_route_discovery_domain_research_boundary_metadata(candidate)
        route_profiles = _string_list(candidate.get("route_profiles"))
        validation_contract = _skill_route_discovery_validation_contract(route_profiles, allowed_lanes)
        handoff_metadata = _skill_route_discovery_handoff_metadata(
            route_profiles,
            allowed_lanes,
            handoff_scope="candidate_inventory",
        )
        candidate_lane_inventory.append(
            {
                "candidate_name": name,
                "source_url": source_url,
                "proposal_kinds": list(dict.fromkeys(allowed_lanes)),
                "route_profiles": route_profiles,
                "matched_route_terms": _string_list(candidate.get("matched_route_terms")),
                "discovery_event_kind": str(candidate.get("discovery_event_kind") or "unknown"),
                "discovery_event_effect": str(candidate.get("discovery_event_effect") or "record_only"),
                "evidence_item_ids": _proposal_lane_evidence_item_ids(candidate),
                "evidence_urls": _proposal_lane_evidence_urls(candidate, source_url),
                "route_validation_contract": validation_contract,
                "handoff_metadata": handoff_metadata,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "activation_gate": "local_validation_before_activation",
                "uncertainty": _candidate_uncertainty_message(uncertainty_reasons),
                "uncertainty_reasons": uncertainty_reasons,
                **_optional_list_field("source_layout_signals", _string_list(candidate.get("source_layout_signals"))),
                **_optional_list_field(
                    "source_metadata_signals",
                    _string_list(candidate.get("source_metadata_signals")),
                ),
                **probe_metadata,
                **state_boundary_metadata,
                **domain_research_boundary_metadata,
            }
        )

        for lane in allowed_lanes:
            lane_validation_contract = _skill_route_discovery_validation_contract(route_profiles, (lane,))
            lane_handoff_metadata = _skill_route_discovery_handoff_metadata(
                route_profiles,
                (lane,),
                handoff_scope="proposal_lane",
            )
            proposal_lanes.append(
                {
                    "candidate_name": name,
                    "discovery_event_effect": str(candidate.get("discovery_event_effect") or "record_only"),
                    "discovery_event_kind": str(candidate.get("discovery_event_kind") or "unknown"),
                    "source_url": source_url,
                    "proposal_kind": lane,
                    "route_profiles": route_profiles,
                    "matched_route_terms": _string_list(candidate.get("matched_route_terms")),
                    "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                    "status": SKILL_ROUTE_DISCOVERY_PROPOSAL_LANE,
                    "evidence_urls": _proposal_lane_evidence_urls(candidate, source_url),
                    "evidence_item_ids": _proposal_lane_evidence_item_ids(candidate),
                    "route_validation_contract": lane_validation_contract,
                    "handoff_metadata": lane_handoff_metadata,
                    "local_validation_required": True,
                    "runtime_action": "none",
                    "external_skill_activation_allowed": False,
                    "provider_runtime_launch_allowed": False,
                    "uncertainty": _candidate_uncertainty_message(uncertainty_reasons),
                    "uncertainty_reasons": uncertainty_reasons,
                    "reason": "recognized_skill_project_evidence",
                    **_optional_list_field(
                        "source_layout_signals",
                        _string_list(candidate.get("source_layout_signals")),
                    ),
                    **_optional_list_field(
                        "source_metadata_signals",
                        _string_list(candidate.get("source_metadata_signals")),
                    ),
                    **probe_metadata,
                    **state_boundary_metadata,
                    **domain_research_boundary_metadata,
                }
            )

    local_activation_targets = _skill_route_discovery_local_activation_targets(candidate_lane_inventory)
    route_profile_handoff_queue = _skill_route_discovery_route_profile_handoff_queue(local_activation_targets)
    adoption_manifest = _skill_route_discovery_adoption_manifest(
        candidate_lane_inventory,
        proposal_lanes,
        rejected_candidates,
        downgraded_candidates,
    )

    return {
        "schema_version": 1,
        "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
        "allowed_proposal_kinds": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "source_registry_status": str(registry.get("registry_status") or ""),
        "candidate_count": len(candidates),
        "proposal_lane_count": len(proposal_lanes),
        "rejected_candidate_count": len(rejected_candidates),
        "downgraded_candidate_count": len(downgraded_candidates),
        "route_profile_catalog": _skill_route_discovery_route_profile_catalog(proposal_lanes),
        "local_lane_matrix": _skill_route_discovery_local_lane_matrix(candidate_lane_inventory),
        "validation_profile_coverage": _skill_route_discovery_validation_profile_coverage(
            candidate_lane_inventory
        ),
        "local_activation_targets": local_activation_targets,
        "route_profile_handoff_queue": route_profile_handoff_queue,
        "adoption_manifest": adoption_manifest,
        "next_validation_step": _skill_route_discovery_next_validation_step(local_activation_targets),
        "candidate_lane_inventory": candidate_lane_inventory,
        "proposal_lanes": proposal_lanes,
        "rejected_candidates": rejected_candidates,
        "downgraded_candidates": downgraded_candidates,
    }


def _rank_skill_for_task(task: str, descriptor: SkillDescriptor) -> SkillRouteDecision:
    if not descriptor.enabled:
        return SkillRouteDecision(
            descriptor=descriptor,
            route=NO_SKILL_MATCH,
            score=0,
            reasons=("disabled_skill",),
        )

    task_text = task.casefold()
    validation_bonus = VALIDATION_WEIGHTS.get(descriptor.validation_status, VALIDATION_WEIGHTS["unknown"])
    trigger_matches = tuple(term for term in descriptor.trigger_terms if _contains_term(task_text, term))
    if trigger_matches:
        score = 100 + validation_bonus + min(len(trigger_matches), 5)
        return SkillRouteDecision(
            descriptor=descriptor,
            route=EXACT_TRIGGER_MATCH,
            score=score,
            reasons=tuple(f"trigger:{term}" for term in trigger_matches)
            + (f"validation:{descriptor.validation_status}",),
        )

    if _contains_explicit_skill_name(task_text, descriptor.name):
        score = 100 + validation_bonus + 1
        return SkillRouteDecision(
            descriptor=descriptor,
            route=EXACT_TRIGGER_MATCH,
            score=score,
            reasons=(f"skill_name:{descriptor.name}", f"validation:{descriptor.validation_status}"),
        )

    domain_matches = tuple(domain for domain in descriptor.domains if _contains_term(task_text, domain))
    if domain_matches:
        score = 30 + validation_bonus + min(len(domain_matches), 5)
        return SkillRouteDecision(
            descriptor=descriptor,
            route=TOPICAL_MATCH,
            score=score,
            reasons=tuple(f"domain:{domain}" for domain in domain_matches)
            + (f"validation:{descriptor.validation_status}",),
        )

    return SkillRouteDecision(
        descriptor=descriptor,
        route=NO_SKILL_MATCH,
        score=max(validation_bonus, 0),
        reasons=("no_trigger_or_domain_match",),
    )


def _coerce_skill_descriptor(value: SkillDescriptor | Mapping[str, Any]) -> SkillDescriptor:
    if isinstance(value, SkillDescriptor):
        return value
    return SkillDescriptor.from_mapping(value)


def _coerce_external_skill_route_candidate(
    value: ExternalSkillRouteCandidate | Mapping[str, Any],
) -> ExternalSkillRouteCandidate:
    if isinstance(value, ExternalSkillRouteCandidate):
        return value
    return ExternalSkillRouteCandidate.from_mapping(value)


def _coerce_external_skill_repository_summary(
    value: ExternalSkillRepositorySummary | Mapping[str, Any],
) -> ExternalSkillRepositorySummary:
    if isinstance(value, ExternalSkillRepositorySummary):
        return value
    return ExternalSkillRepositorySummary.from_mapping(value)


def _coerce_external_skill_evidence_item(
    value: ExternalSkillEvidenceItem | Mapping[str, Any],
) -> ExternalSkillEvidenceItem:
    if isinstance(value, ExternalSkillEvidenceItem):
        return value
    return ExternalSkillEvidenceItem.from_mapping(value)


def _looks_like_skill_repository_summary(summary: ExternalSkillRepositorySummary) -> bool:
    text = _summary_text(summary)
    layout_signals = _skill_repository_layout_signals(summary)
    metadata_signals = _skill_repository_metadata_signals(summary)
    has_skill_text = any(
        marker in text
        for marker in (
            "agent skill",
            "agent skills",
            "codex skill",
            "claude skill",
            "director skill",
            "fablecodex",
            "skill ecosystem",
            "skill bundle",
            "skill.md",
            "skills/",
            "workflow skill",
            "workflow skills",
        )
    )
    has_skill_layout = bool(
        set(layout_signals) & {"skill_markdown", "skill_directory"}
        or set(metadata_signals) & {"skill_registry_metadata"}
    )
    return has_skill_text or has_skill_layout


def _bounded_skill_discovery_lanes(summary: ExternalSkillRepositorySummary) -> tuple[str, ...]:
    text = _summary_text(summary)
    suggested = tuple(lane for lane in summary.suggested_lanes if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    keyword_lanes = tuple(
        lane
        for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        if any(keyword in text for keyword in SKILL_ROUTE_DISCOVERY_LANE_KEYWORDS[lane])
    )
    layout_lanes = tuple(
        lane
        for signal in (*_skill_repository_layout_signals(summary), *_skill_repository_metadata_signals(summary))
        for lane in SKILL_ROUTE_DISCOVERY_LAYOUT_SIGNAL_LANES.get(signal, ())
    )
    lanes = tuple(dict.fromkeys((*suggested, *keyword_lanes)))
    lanes = tuple(dict.fromkeys((*lanes, *layout_lanes)))
    return lanes or ("documentation",)


def _skill_route_discovery_route_profiles(candidate: ExternalSkillRouteCandidate) -> tuple[str, ...]:
    """Classify the shape of external skill evidence without enabling it."""

    text = " ".join(
        part
        for part in (
            candidate.name,
            candidate.evidence_summary,
            " ".join(candidate.candidate_lanes),
            " ".join(candidate.source_layout_signals),
            " ".join(candidate.source_metadata_signals),
        )
        if part
    ).casefold()
    profiles = [
        profile
        for profile, keywords in SKILL_ROUTE_DISCOVERY_ROUTE_PROFILE_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    return tuple(dict.fromkeys(profiles or ["generic_skill_workflow"]))


def _skill_route_discovery_mixed_probe_metadata(
    candidate: Mapping[str, Any],
    allowed_lanes: Sequence[str],
) -> dict[str, Any]:
    """Route mixed Codex/skill/workflow signals through skill discovery first."""

    matched_terms = set(_string_list(candidate.get("matched_route_terms")))
    if not _has_mixed_skill_workflow_terms(matched_terms):
        return {}

    allowed = list(
        dict.fromkeys(str(lane) for lane in allowed_lanes if str(lane) in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    )
    recommended_order = [lane for lane in SKILL_ROUTE_DISCOVERY_MIXED_LANE_ORDER if lane in allowed]
    return {
        "route_probe_decision": "skill_route_discovery_first",
        "primary_route": SKILL_ROUTE_DISCOVERY_HINT,
        "secondary_lane": "agent_harness_eval_after_local_corroboration",
        "secondary_lane_status": "blocked_until_local_corroboration",
        "agent_harness_eval_allowed_after": "local_corroboration_or_general_agent_project_claim",
        "full_mixed_signal": bool(matched_terms & set(SKILL_ROUTE_DISCOVERY_MIXED_AGENT_TERMS)),
        "recommended_local_lane_order": recommended_order,
    }


def _skill_route_discovery_state_boundary_metadata(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Expose COMPASS-style state/profile routes as bounded metadata only."""

    route_profiles = set(_string_list(candidate.get("route_profiles")))
    if "skill_ecosystem_state_handoff" not in route_profiles:
        return {}

    return {
        "state_profile_boundary": {
            "boundary_required_before_activation": True,
            "retention_policy_required": True,
            "privacy_boundary_required": True,
            "local_target_metadata_only": True,
            "profile_write_allowed": False,
            "memory_write_allowed": False,
            "global_config_write_allowed": False,
            "private_context_export_allowed": False,
            "upstream_presence_grants_write": False,
            "review_surface": "skill_route_discovery_state_handoff_preflight",
        }
    }


def _skill_route_discovery_domain_research_boundary_metadata(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Expose source-cited domain skill routes as local evidence checks only."""

    route_profiles = set(_string_list(candidate.get("route_profiles")))
    if "source_cited_domain_research" not in route_profiles:
        return {}

    return {
        "domain_research_boundary": {
            "boundary_required_before_activation": True,
            "source_citation_required": True,
            "advice_disclaimer_required": True,
            "local_evidence_replay_required": True,
            "upstream_dataset_import_allowed": False,
            "upstream_advice_generation_allowed": False,
            "financial_or_medical_advice_allowed": False,
            "provider_runtime_launch_allowed": False,
            "private_context_export_allowed": False,
            "review_surface": "skill_route_discovery_domain_research_preflight",
        }
    }


def _skill_route_discovery_validation_contract(
    route_profiles: Sequence[str],
    allowed_lanes: Sequence[str],
) -> dict[str, Any]:
    """Return profile-specific local validation gates before activation.

    The contract is derived only from local route profile names and already
    bounded lanes. It does not add lanes or imply upstream skill activation.
    """

    bounded_lanes = list(
        dict.fromkeys(str(lane) for lane in allowed_lanes if str(lane) in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    )
    profiles = list(dict.fromkeys(str(profile) for profile in route_profiles if str(profile).strip()))
    if not profiles:
        profiles = ["generic_skill_workflow"]

    rows: list[dict[str, Any]] = []
    for profile in profiles:
        contract = SKILL_ROUTE_DISCOVERY_ROUTE_PROFILE_VALIDATION_CONTRACTS.get(
            profile,
            SKILL_ROUTE_DISCOVERY_ROUTE_PROFILE_VALIDATION_CONTRACTS["generic_skill_workflow"],
        )
        preferred_lanes = [
            lane
            for lane in contract["preferred_lanes"]
            if lane in bounded_lanes
        ]
        rows.append(
            {
                "route_profile": profile,
                "validation_gate": contract["validation_gate"],
                "allowed_local_lanes": bounded_lanes,
                "preferred_local_lanes": preferred_lanes,
                "required_metadata": list(contract["required_metadata"]),
                "blocked_activation_reason": contract["blocked_activation_reason"],
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "raw_upstream_body_exported": False,
            }
        )

    return {
        "controller_surface": "skill_route_discovery_route_validation_contract",
        "status": "ready" if bounded_lanes else "blocked_no_allowed_lanes",
        "route_profiles": profiles,
        "allowed_local_lanes": bounded_lanes,
        "row_count": len(rows),
        "rows": rows,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_activation_allowed": False,
        "provider_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_upstream_body_exported": False,
    }


def _skill_route_discovery_handoff_metadata(
    route_profiles: Sequence[str],
    allowed_lanes: Sequence[str],
    *,
    handoff_scope: str,
) -> dict[str, Any]:
    """Expose one bounded local lane handoff without adding activation authority."""

    contract = _skill_route_discovery_validation_contract(route_profiles, allowed_lanes)
    bounded_lanes = _string_list(contract.get("allowed_local_lanes"))
    preferred_lanes: list[str] = []
    validation_gates: list[str] = []
    required_metadata: list[str] = []
    rows = contract.get("rows")
    rows = rows if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)) else []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        preferred_lanes.extend(_string_list(row.get("preferred_local_lanes")))
        gate = str(row.get("validation_gate") or "").strip()
        if gate:
            validation_gates.append(gate)
        required_metadata.extend(_string_list(row.get("required_metadata")))

    ordered_lanes = [lane for lane in dict.fromkeys((*preferred_lanes, *bounded_lanes)) if lane in bounded_lanes]
    selected_lane = ordered_lanes[0] if ordered_lanes else ""
    queued_lanes = [lane for lane in ordered_lanes if lane != selected_lane]
    return {
        "controller_surface": "skill_route_discovery_lane_handoff_metadata",
        "handoff_scope": handoff_scope,
        "status": "ready" if selected_lane else "blocked",
        "decision": "handoff_bounded_local_lane_for_validation" if selected_lane else "blocked_no_bounded_local_lane",
        "route_profiles": _string_list(contract.get("route_profiles")),
        "allowed_local_lanes": bounded_lanes,
        "selected_local_lane": selected_lane,
        "queued_local_lanes": queued_lanes,
        "validation_gates": list(dict.fromkeys(validation_gates)),
        "required_metadata": list(dict.fromkeys(required_metadata)),
        "activation_gate": "local_validation_before_activation",
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


def _has_mixed_skill_workflow_terms(matched_terms: set[str]) -> bool:
    return (
        all(term in matched_terms for term in SKILL_ROUTE_DISCOVERY_MIXED_REQUIRED_TERMS)
        and bool(matched_terms & set(SKILL_ROUTE_DISCOVERY_MIXED_SKILL_TERMS))
    )


def _skill_route_discovery_matched_terms(*parts: str) -> tuple[str, ...]:
    """Return route-trigger terms found in public, body-free candidate metadata."""

    text = " ".join(part for part in parts if part).casefold()
    text = re.sub(r"[-_/]+", " ", text)
    return tuple(term for term in SKILL_ROUTE_DISCOVERY_TRIGGER_TERMS if _contains_term(text, term))


def _skill_route_discovery_route_profile_catalog(proposal_lanes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    profile_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {}
    for lane in proposal_lanes:
        proposal_kind = str(lane.get("proposal_kind") or "")
        for profile in _string_list(lane.get("route_profiles")):
            profile_counts[profile] = profile_counts.get(profile, 0) + 1
            if proposal_kind:
                key = f"{profile}:{proposal_kind}"
                lane_counts[key] = lane_counts.get(key, 0) + 1
    return {
        "body_free": True,
        "profile_counts": dict(sorted(profile_counts.items())),
        "profile_lane_counts": dict(sorted(lane_counts.items())),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
    }


def _skill_route_discovery_local_lane_matrix(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize bounded local lanes before expanding proposal rows.

    This is an operator-facing matrix derived from candidate inventory rows.
    It does not add lanes; it only makes profile gates and first-route proof
    visible before a controller selects a local validation lane.
    """

    rows: list[dict[str, Any]] = []
    blocked_rows: list[str] = []
    observed_profiles: list[str] = []
    observed_lanes: list[str] = []

    for candidate in candidate_lane_inventory:
        candidate_name = str(candidate.get("candidate_name") or "")
        proposal_kinds = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        observed_profiles.extend(route_profiles)
        observed_lanes.extend(proposal_kinds)

        route_probe_decision = str(candidate.get("route_probe_decision") or "skill_route_discovery")
        first_route_required = "codex_workflow_gate" in route_profiles
        first_route_confirmed = not first_route_required or route_probe_decision == "skill_route_discovery_first"
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        validation_contract = candidate.get("route_validation_contract")
        validation_contract = validation_contract if isinstance(validation_contract, Mapping) else {}
        contract_rows = validation_contract.get("rows")
        contract_rows = (
            contract_rows
            if isinstance(contract_rows, Sequence) and not isinstance(contract_rows, (str, bytes))
            else []
        )
        validation_gates = [
            str(row.get("validation_gate") or "")
            for row in contract_rows
            if isinstance(row, Mapping) and str(row.get("validation_gate") or "").strip()
        ]
        if not first_route_confirmed or not proposal_kinds:
            blocked_rows.append(candidate_name)

        rows.append(
            {
                "candidate_name": candidate_name,
                "route_profiles": route_profiles,
                "allowed_local_lanes": proposal_kinds,
                "selected_local_lane": str(handoff_metadata.get("selected_local_lane") or ""),
                "queued_local_lanes": _string_list(handoff_metadata.get("queued_local_lanes")),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "route_probe_decision": route_probe_decision,
                "first_route_required": first_route_required,
                "first_route_confirmed": first_route_confirmed,
                "activation_gate": str(candidate.get("activation_gate") or "local_validation_before_activation"),
                "local_validation_required": candidate.get("local_validation_required") is True,
                "runtime_action": str(candidate.get("runtime_action") or "none"),
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    return {
        "controller_surface": "skill_route_discovery_local_lane_matrix",
        "status": "ready" if rows and not blocked_rows else "blocked",
        "row_count": len(rows),
        "observed_route_profiles": list(dict.fromkeys(observed_profiles)),
        "observed_local_lanes": list(
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_lanes)
        ),
        "blocked_candidate_names": [name for name in blocked_rows if name],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_validation_profile_coverage(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose coverage for the pass-3 skill-route validation profiles.

    Some proposal terms, such as a plain skill term or a mixed workflow probe,
    are evidence shapes rather than route profiles. This report normalizes both
    kinds of signal into one bounded, body-free operator surface.
    """

    profile_rows: dict[str, dict[str, Any]] = {
        profile: {
            "validation_profile": profile,
            "status": "not_observed",
            "candidate_names": [],
            "candidate_source_hashes": [],
            "allowed_local_lanes": [],
            "selected_local_lanes": [],
            "route_profiles": [],
            "signal_basis": [],
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_upstream_body_exported": False,
        }
        for profile in SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES
    }

    for candidate in candidate_lane_inventory:
        candidate_name = str(candidate.get("candidate_name") or "")
        source_hash = _stable_hash(str(candidate.get("source_url") or candidate_name))
        local_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        if not local_lanes:
            continue

        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        selected_lanes = [selected_lane] if selected_lane in local_lanes else [local_lanes[0]]
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        matched_terms = set(_string_list(candidate.get("matched_route_terms")))

        observed_profiles = [profile for profile in route_profiles if profile in profile_rows]
        if matched_terms & set(SKILL_ROUTE_DISCOVERY_MIXED_SKILL_TERMS):
            observed_profiles.append("skill_term")
        if str(candidate.get("route_probe_decision") or "") == "skill_route_discovery_first":
            observed_profiles.append("mixed_skill_workflow_probe")

        for profile in dict.fromkeys(observed_profiles):
            row = profile_rows[profile]
            row["status"] = "ready"
            row["candidate_names"] = list(
                dict.fromkeys((*_string_list(row.get("candidate_names")), candidate_name))
            )
            row["candidate_source_hashes"] = list(
                dict.fromkeys((*_string_list(row.get("candidate_source_hashes")), source_hash))
            )
            row["allowed_local_lanes"] = [
                lane
                for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                if lane in {*_string_list(row.get("allowed_local_lanes")), *local_lanes}
            ]
            row["selected_local_lanes"] = list(
                dict.fromkeys((*_string_list(row.get("selected_local_lanes")), *selected_lanes))
            )
            row["route_profiles"] = list(
                dict.fromkeys((*_string_list(row.get("route_profiles")), *route_profiles))
            )
            signal_basis = {
                "skill_term": ("matched_skill_term",),
                "mixed_skill_workflow_probe": ("route_probe_decision",),
            }.get(profile, ("route_profile",))
            row["signal_basis"] = list(
                dict.fromkeys(
                    (
                        *_string_list(row.get("signal_basis")),
                        *signal_basis,
                    )
                )
            )

    rows = [profile_rows[profile] for profile in SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES]
    ready_profiles = [
        row["validation_profile"]
        for row in rows
        if row["status"] == "ready"
    ]
    blocked_profiles = [
        row["validation_profile"]
        for row in rows
        if row["status"] != "ready"
    ]

    return {
        "controller_surface": "skill_route_discovery_validation_profile_coverage",
        "status": "ready" if rows and not blocked_profiles else "blocked",
        "decision": (
            "validation_profiles_have_bounded_local_lanes"
            if rows and not blocked_profiles
            else "collect_or_repair_skill_route_validation_profiles"
        ),
        "required_validation_profiles": list(SKILL_ROUTE_DISCOVERY_VALIDATION_PROFILES),
        "ready_validation_profiles": ready_profiles,
        "blocked_validation_profiles": blocked_profiles,
        "ready_profile_count": len(ready_profiles),
        "blocked_profile_count": len(blocked_profiles),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_local_activation_targets(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a supervisor-facing validation target list for bounded lanes."""

    rows: list[dict[str, Any]] = []
    blocked_rows: list[str] = []

    for candidate in candidate_lane_inventory:
        candidate_name = str(candidate.get("candidate_name") or "")
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        proposal_kinds = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        if selected_lane not in proposal_kinds:
            selected_lane = proposal_kinds[0] if proposal_kinds else ""
        route_probe_decision = str(candidate.get("route_probe_decision") or "skill_route_discovery")
        first_route_required = "codex_workflow_gate" in route_profiles
        first_route_confirmed = not first_route_required or route_probe_decision == "skill_route_discovery_first"
        validation_contract = candidate.get("route_validation_contract")
        validation_contract = validation_contract if isinstance(validation_contract, Mapping) else {}
        contract_rows = validation_contract.get("rows")
        contract_rows = (
            contract_rows
            if isinstance(contract_rows, Sequence) and not isinstance(contract_rows, (str, bytes))
            else []
        )
        validation_gates = [
            str(row.get("validation_gate") or "")
            for row in contract_rows
            if isinstance(row, Mapping) and str(row.get("validation_gate") or "").strip()
        ]
        item_ids = _string_list(candidate.get("evidence_item_ids"))
        source_hash = _stable_hash(str(candidate.get("source_url") or candidate_name))
        profile_names = ",".join(route_profiles)
        ready = bool(selected_lane and first_route_confirmed)
        if not ready and candidate_name:
            blocked_rows.append(candidate_name)

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": source_hash,
                "route_profiles": route_profiles,
                "selected_local_lane": selected_lane,
                "queued_local_lanes": [lane for lane in proposal_kinds if lane != selected_lane],
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": _skill_route_discovery_validation_target(selected_lane, route_profiles),
                "replay_command": _skill_route_discovery_replay_command(selected_lane, route_profiles),
                "promotion_proof": _skill_route_discovery_promotion_proof(selected_lane),
                "selected_evidence_item_ids": item_ids,
                "first_route_required": first_route_required,
                "first_route_confirmed": first_route_confirmed,
                "activation_ready": ready,
                "activation_blockers": (
                    [] if ready else ["missing_skill_route_discovery_first" if first_route_required else "missing_bounded_lane"]
                ),
                "operator_note": (
                    f"Validate {selected_lane or 'bounded local'} lane for {profile_names} before activation."
                ),
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    return {
        "controller_surface": "skill_route_discovery_local_activation_targets",
        "status": "ready" if rows and not blocked_rows else "blocked",
        "row_count": len(rows),
        "blocked_candidate_names": [name for name in blocked_rows if name],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_next_validation_step(
    local_activation_targets: Mapping[str, Any],
) -> dict[str, Any]:
    """Select the next bounded replay target without granting activation."""

    raw_rows = local_activation_targets.get("rows")
    target_rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    rows = [row for row in target_rows if isinstance(row, Mapping)]
    ready_rows = [row for row in rows if row.get("activation_ready") is True]
    blocked_rows = [row for row in rows if row.get("activation_ready") is not True]

    selected = min(ready_rows, key=_skill_route_discovery_next_step_sort_key) if ready_rows else None
    selected_lane = str(selected.get("selected_local_lane") or "") if selected is not None else ""
    selected_profiles = _string_list(selected.get("route_profiles")) if selected is not None else []
    selected_target = str(selected.get("validation_target") or "") if selected is not None else ""
    replay_command = str(selected.get("replay_command") or "") if selected is not None else ""
    promotion_proof = (
        selected.get("promotion_proof")
        if selected is not None and isinstance(selected.get("promotion_proof"), Mapping)
        else _skill_route_discovery_promotion_proof(selected_lane)
    )

    return {
        "controller_surface": "skill_route_discovery_next_validation_step",
        "status": "ready" if selected is not None and not blocked_rows else "blocked",
        "decision": (
            "run_selected_local_validation_before_activation"
            if selected is not None and not blocked_rows
            else "resolve_blocked_skill_route_targets_before_activation"
        ),
        "selected_candidate_name": str(selected.get("candidate_name") or "") if selected is not None else "",
        "selected_local_lane": selected_lane,
        "selected_route_profiles": selected_profiles,
        "validation_target": selected_target,
        "replay_command": replay_command,
        "promotion_proof": promotion_proof,
        "ready_candidate_names": [
            str(row.get("candidate_name") or "")
            for row in ready_rows
            if str(row.get("candidate_name") or "").strip()
        ],
        "blocked_candidate_names": [
            str(row.get("candidate_name") or "")
            for row in blocked_rows
            if str(row.get("candidate_name") or "").strip()
        ],
        "next_step_basis": "ready_targets_prioritize_first_route_probe_then_frontend_test_then_state_boundary",
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def _skill_route_discovery_route_profile_handoff_queue(
    local_activation_targets: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize selected local validation lanes by route profile.

    The queue is derived from already-bounded activation targets. It gives an
    operator one route-profile row per observed profile without adding lanes or
    changing the selected validation target.
    """

    raw_rows = local_activation_targets.get("rows")
    target_rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    profile_rows: dict[str, dict[str, Any]] = {}
    blocked_profiles: list[str] = []

    for row in target_rows:
        if not isinstance(row, Mapping):
            continue
        route_profiles = _string_list(row.get("route_profiles")) or ["generic_skill_workflow"]
        selected_lane = str(row.get("selected_local_lane") or "")
        activation_ready = row.get("activation_ready") is True
        validation_gates = _string_list(row.get("validation_gates"))
        activation_blockers = _string_list(row.get("activation_blockers"))
        selected_item_ids = _string_list(row.get("selected_evidence_item_ids"))
        candidate_name = str(row.get("candidate_name") or "")
        source_hash = str(row.get("candidate_source_hash") or "")

        for profile in route_profiles:
            existing = profile_rows.get(profile)
            if existing is None:
                profile_rows[profile] = {
                    "route_profile": profile,
                    "selected_local_lane": selected_lane,
                    "validation_target": str(row.get("validation_target") or ""),
                    "replay_command": str(row.get("replay_command") or ""),
                    "validation_gates": validation_gates,
                    "candidate_names": [candidate_name] if candidate_name else [],
                    "candidate_source_hashes": [source_hash] if source_hash else [],
                    "selected_evidence_item_ids": selected_item_ids,
                    "first_route_required": row.get("first_route_required") is True,
                    "first_route_confirmed": row.get("first_route_confirmed") is True,
                    "queue_status": "ready" if activation_ready else "blocked",
                    "activation_blockers": activation_blockers,
                    "local_validation_required": True,
                    "runtime_action": "none",
                    "external_skill_activation_allowed": False,
                    "external_harness_execution_allowed": False,
                    "provider_runtime_launch_allowed": False,
                    "remote_execution_allowed": False,
                    "raw_source_url_exported": False,
                    "raw_evidence_urls_exported": False,
                    "raw_target_paths_exported": False,
                    "raw_upstream_body_exported": False,
                }
            else:
                existing["candidate_names"] = list(
                    dict.fromkeys((*_string_list(existing.get("candidate_names")), candidate_name))
                )
                existing["candidate_source_hashes"] = list(
                    dict.fromkeys((*_string_list(existing.get("candidate_source_hashes")), source_hash))
                )
                existing["selected_evidence_item_ids"] = list(
                    dict.fromkeys((*_string_list(existing.get("selected_evidence_item_ids")), *selected_item_ids))
                )
                existing["validation_gates"] = list(
                    dict.fromkeys((*_string_list(existing.get("validation_gates")), *validation_gates))
                )
                existing["first_route_required"] = (
                    existing.get("first_route_required") is True or row.get("first_route_required") is True
                )
                existing["first_route_confirmed"] = (
                    existing.get("first_route_confirmed") is True and row.get("first_route_confirmed") is True
                )
                existing["activation_blockers"] = list(
                    dict.fromkeys((*_string_list(existing.get("activation_blockers")), *activation_blockers))
                )
                if not activation_ready:
                    existing["queue_status"] = "blocked"

    rows = [profile_rows[profile] for profile in sorted(profile_rows)]
    for row in rows:
        if row["queue_status"] != "ready":
            blocked_profiles.append(row["route_profile"])

    return {
        "controller_surface": "skill_route_discovery_route_profile_handoff_queue",
        "status": "ready" if rows and not blocked_profiles else "blocked",
        "decision": (
            "handoff_route_profiles_to_bounded_local_validation"
            if rows and not blocked_profiles
            else "repair_route_profile_handoff_before_activation"
        ),
        "route_profile_count": len(rows),
        "blocked_route_profiles": blocked_profiles,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_adoption_manifest(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    proposal_lanes: Sequence[Mapping[str, Any]],
    rejected_candidates: Sequence[Mapping[str, Any]],
    downgraded_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose the whole skill-route adoption boundary as one operator manifest."""

    proposal_counts_by_candidate: dict[str, int] = {}
    for lane in proposal_lanes:
        candidate_name = str(lane.get("candidate_name") or "")
        if candidate_name:
            proposal_counts_by_candidate[candidate_name] = proposal_counts_by_candidate.get(candidate_name, 0) + 1

    rows: list[dict[str, Any]] = []
    blocked_candidates: list[str] = []
    observed_profiles: list[str] = []
    observed_lanes: list[str] = []

    for candidate in candidate_lane_inventory:
        candidate_name = str(candidate.get("candidate_name") or "")
        source_hash = _stable_hash(str(candidate.get("source_url") or candidate_name))
        local_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        observed_profiles.extend(route_profiles)
        observed_lanes.extend(local_lanes)

        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        if selected_lane not in local_lanes:
            selected_lane = local_lanes[0] if local_lanes else ""

        validation_contract = candidate.get("route_validation_contract")
        validation_contract = validation_contract if isinstance(validation_contract, Mapping) else {}
        contract_rows = validation_contract.get("rows")
        contract_rows = (
            contract_rows
            if isinstance(contract_rows, Sequence) and not isinstance(contract_rows, (str, bytes))
            else []
        )
        validation_gates = [
            str(row.get("validation_gate") or "")
            for row in contract_rows
            if isinstance(row, Mapping) and str(row.get("validation_gate") or "").strip()
        ]

        route_probe_decision = str(candidate.get("route_probe_decision") or "skill_route_discovery")
        first_route_required = "codex_workflow_gate" in route_profiles
        first_route_confirmed = not first_route_required or route_probe_decision == "skill_route_discovery_first"
        ready = bool(local_lanes and selected_lane and first_route_confirmed)
        blockers = []
        if not local_lanes:
            blockers.append("missing_bounded_local_lane")
        if first_route_required and not first_route_confirmed:
            blockers.append("missing_skill_route_discovery_first")
        if not ready and candidate_name:
            blocked_candidates.append(candidate_name)

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": source_hash,
                "route_profiles": route_profiles,
                "allowed_local_lanes": local_lanes,
                "selected_local_lane": selected_lane,
                "queued_local_lanes": [lane for lane in local_lanes if lane != selected_lane],
                "proposal_lane_count": proposal_counts_by_candidate.get(candidate_name, 0),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": _skill_route_discovery_validation_target(selected_lane, route_profiles),
                "replay_command": _skill_route_discovery_replay_command(selected_lane, route_profiles),
                "promotion_proof": _skill_route_discovery_promotion_proof(selected_lane),
                "selected_evidence_item_ids": _string_list(candidate.get("evidence_item_ids")),
                "route_probe_decision": route_probe_decision,
                "first_route_required": first_route_required,
                "first_route_confirmed": first_route_confirmed,
                "manifest_status": "ready_for_local_validation" if ready else "blocked_before_activation",
                "activation_blockers": blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    ready = bool(rows) and not blocked_candidates and not rejected_candidates and not downgraded_candidates
    return {
        "controller_surface": "skill_route_discovery_adoption_manifest",
        "status": "ready" if ready else "blocked",
        "decision": (
            "bounded_local_validation_only"
            if ready
            else "repair_skill_route_manifest_before_activation"
        ),
        "candidate_count": len(candidate_lane_inventory),
        "proposal_lane_count": len(proposal_lanes),
        "rejected_candidate_count": len(rejected_candidates),
        "downgraded_candidate_count": len(downgraded_candidates),
        "blocked_candidate_names": [name for name in blocked_candidates if name],
        "observed_route_profiles": list(dict.fromkeys(observed_profiles)),
        "observed_local_lanes": list(
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_lanes)
        ),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "blocked_external_actions": list(SKILL_ROUTE_DISCOVERY_BLOCKED_ACTIONS)
        + [
            "activate_upstream_skill_code",
            "external_harness_execution",
            "provider_runtime_launch",
            "remote_execution",
            "raw_source_url_export",
            "raw_upstream_body_export",
        ],
        "activation_gate": "local_validation_before_activation",
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "promotion_readiness": _skill_route_discovery_promotion_readiness(rows, ready=ready),
        "rows": rows,
    }


def _skill_route_discovery_promotion_readiness(
    manifest_rows: Sequence[Mapping[str, Any]],
    *,
    ready: bool,
) -> dict[str, Any]:
    """Aggregate manifest rows into a rollback-backed supervisor handoff checklist."""

    rows = [row for row in manifest_rows if isinstance(row, Mapping)]
    ready_rows = [
        row
        for row in rows
        if str(row.get("manifest_status") or "") == "ready_for_local_validation"
        and row.get("local_validation_required") is True
        and str(row.get("runtime_action") or "none") == "none"
    ]
    blocked_rows = [row for row in rows if row not in ready_rows]
    replay_commands = [
        str(row.get("replay_command") or "")
        for row in ready_rows
        if str(row.get("replay_command") or "").strip()
    ]
    selected_lanes = [
        str(row.get("selected_local_lane") or "")
        for row in ready_rows
        if str(row.get("selected_local_lane") or "") in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    target_path_hashes: list[str] = []
    for row in ready_rows:
        promotion_proof = row.get("promotion_proof")
        if not isinstance(promotion_proof, Mapping):
            continue
        target_path_hashes.extend(_string_list(promotion_proof.get("target_path_hashes")))

    status = "ready" if ready and rows and not blocked_rows else "blocked"
    return {
        "controller_surface": "skill_route_discovery_promotion_readiness",
        "status": status,
        "decision": (
            "replay_bounded_lanes_then_external_supervisor_handoff"
            if status == "ready"
            else "repair_manifest_rows_before_promotion"
        ),
        "row_count": len(rows),
        "ready_row_count": len(ready_rows),
        "blocked_row_count": len(blocked_rows),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "rollback_ref",
            "rollback_artifact",
            "changed_file_review",
            "focused_local_validation",
            "review_note",
        ],
        "target_path_hashes": list(dict.fromkeys(target_path_hashes)),
        "target_path_count": len(dict.fromkeys(target_path_hashes)),
        "supervisor_handoff": "external_supervisor_only",
        "kernel_restart_allowed": False,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def _skill_route_discovery_next_step_sort_key(row: Mapping[str, Any]) -> tuple[int, int, str]:
    selected_lane = str(row.get("selected_local_lane") or "")
    profiles = set(_string_list(row.get("route_profiles")))
    if selected_lane == "test" and "codex_workflow_gate" in profiles:
        profile_rank = 0
    elif selected_lane == "test" and "game_frontend_workflow" in profiles:
        profile_rank = 1
    elif selected_lane == "config" and "skill_ecosystem_state_handoff" in profiles:
        profile_rank = 2
    else:
        profile_rank = 3
    lane_rank = (
        list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES).index(selected_lane)
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        else 99
    )
    return (profile_rank, lane_rank, str(row.get("candidate_name") or "").casefold())


def _skill_route_discovery_validation_target(lane: str, route_profiles: Sequence[str]) -> str:
    profiles = set(route_profiles)
    if lane == "config" or "skill_ecosystem_state_handoff" in profiles:
        return "state_or_profile_boundary_metadata"
    if lane == "test" and "source_cited_domain_research" in profiles:
        return "source_citation_and_advice_boundary_check"
    if lane == "test" and "game_frontend_workflow" in profiles:
        return "local_frontend_render_or_workflow_check"
    if lane == "test" and "codex_workflow_gate" in profiles:
        return "skill_route_first_probe_regression"
    if lane == "documentation":
        return "body_free_route_profile_note"
    if lane == "code_patch":
        return "bounded_local_controller_patch"
    if lane == "test":
        return "focused_local_regression"
    return "bounded_local_lane_review"


def _skill_route_discovery_replay_command(lane: str, route_profiles: Sequence[str]) -> str:
    profiles = set(route_profiles)
    if lane == "test" and "game_frontend_workflow" in profiles:
        return "python -m pytest tests/test_skill_routing.py -q -k game_frontend"
    if lane == "test" and "source_cited_domain_research" in profiles:
        return "python -m pytest tests/test_skill_routing.py -q -k source_cited_domain_research"
    if lane == "test" and "codex_workflow_gate" in profiles:
        return "python -m pytest tests/test_skill_routing.py -q -k mixed_codex_agent_workflow"
    if lane == "config" and "skill_ecosystem_state_handoff" in profiles:
        return "python -m pytest tests/test_skill_routing.py -q -k state_handoff"
    return "python -m pytest tests/test_skill_routing.py -q -k skill_route_discovery"


def _skill_route_discovery_promotion_proof(lane: str) -> dict[str, Any]:
    target_paths = SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS.get(lane, ())
    return {
        "controller_surface": "skill_route_discovery_promotion_proof",
        "selected_local_lane": lane if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES else "",
        "target_path_hashes": [_stable_hash(path) for path in target_paths],
        "target_path_count": len(target_paths),
        "required_evidence": [
            "changed_file_review",
            "focused_local_validation",
            "rollback_artifact",
            "review_note",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def _stable_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _summary_lineage_key(summary: ExternalSkillRepositorySummary) -> str:
    source_url = summary.upstream_source_url or summary.source_url
    try:
        return _canonical_public_github_repository_url(source_url)
    except ValueError:
        return source_url


def _summary_related_source_urls(summary: ExternalSkillRepositorySummary) -> tuple[str, ...]:
    source_urls = [summary.source_url]
    if summary.upstream_source_url:
        source_urls.append(summary.upstream_source_url)
    related_source_urls: list[str] = []
    for source_url in source_urls:
        try:
            related_source_urls.append(_canonical_public_github_repository_url(source_url))
        except ValueError:
            related_source_urls.append(source_url)
    return tuple(dict.fromkeys(related_source_urls))


def _skill_repository_layout_signals(summary: ExternalSkillRepositorySummary) -> tuple[str, ...]:
    """Classify body-free repository file paths into local route signals."""

    paths = tuple(path.replace("\\", "/").strip().casefold() for path in summary.observed_paths if path.strip())
    signals: list[str] = []
    for path in paths:
        parts = tuple(part for part in path.split("/") if part)
        basename = parts[-1] if parts else path
        if basename == "skill.md":
            signals.append("skill_markdown")
        if "skills" in parts:
            signals.append("skill_directory")
        if basename in {"agents.md", ".agents.md"} or "agents" in parts:
            signals.append("agent_metadata")
        if basename.startswith("test_") or basename.endswith("_test.py") or "/tests/" in f"/{path}/":
            signals.append("test_file")
        if basename.endswith((".sh", ".ps1", ".mjs", ".js", ".ts", ".py")) and (
            "script" in parts or "scripts" in parts
        ):
            signals.append("validation_script")
        if "scaffold" in parts or "template" in parts or "assets" in parts:
            signals.append("scaffold_asset")
        if "prompt" in path or "template" in path:
            signals.append("template_or_prompt")
        if "checklist" in path or "qa" in parts:
            signals.append("qa_checklist")
    return tuple(dict.fromkeys(signals))


def _skill_repository_metadata_signals(summary: ExternalSkillRepositorySummary) -> tuple[str, ...]:
    """Classify body-free metadata filenames without reading upstream bodies."""

    files = tuple(
        path.replace("\\", "/").strip().casefold()
        for path in (*summary.metadata_files, *summary.observed_paths)
        if path.strip()
    )
    signals: list[str] = []
    for path in files:
        basename = path.rsplit("/", 1)[-1]
        if basename in {"skills.sh.json", "skill.json", "plugin.json", "manifest.json"}:
            signals.append("skill_registry_metadata")
        if basename in {"agents.md", ".agents.md"} or ".codex-plugin/" in path or "/plugins/" in f"/{path}":
            signals.append("agent_metadata")
        if basename in {"publication_audit.md", "security.md"} or "audit" in basename:
            signals.append("qa_checklist")
    return tuple(dict.fromkeys(signals))


def _merge_external_skill_route_candidates(
    left: ExternalSkillRouteCandidate,
    right: ExternalSkillRouteCandidate,
) -> ExternalSkillRouteCandidate:
    """Merge fork-related discovery summaries without increasing activation count."""

    return ExternalSkillRouteCandidate(
        name=left.name,
        source_url=left.source_url,
        evidence_summary=" ".join(dict.fromkeys((left.evidence_summary, right.evidence_summary))),
        discovery_event_kind=left.discovery_event_kind,
        route_hints=tuple(dict.fromkeys((*left.route_hints, *right.route_hints))),
        candidate_lanes=tuple(dict.fromkeys((*left.candidate_lanes, *right.candidate_lanes))),
        evidence_item_ids=tuple(dict.fromkeys((*left.evidence_item_ids, *right.evidence_item_ids))),
        evidence_urls=tuple(dict.fromkeys((*left.evidence_urls, *right.evidence_urls))),
        evidence_item_urls=tuple(dict.fromkeys((*left.evidence_item_urls, *right.evidence_item_urls))),
        related_source_urls=tuple(dict.fromkeys((*left.related_source_urls, *right.related_source_urls))),
        source_layout_signals=tuple(dict.fromkeys((*left.source_layout_signals, *right.source_layout_signals))),
        source_metadata_signals=tuple(
            dict.fromkeys((*left.source_metadata_signals, *right.source_metadata_signals))
        ),
        requested_actions=tuple(dict.fromkeys((*left.requested_actions, *right.requested_actions))),
        validation_status=left.validation_status,
        enabled=left.enabled or right.enabled,
    )


def _candidate_uncertainty_reasons(candidate: ExternalSkillRouteCandidate) -> tuple[str, ...]:
    """Return bounded uncertainty tags without inspecting upstream skill bodies."""

    reasons: list[str] = []
    text = candidate.evidence_summary.casefold()
    evidence_count = len(set(candidate.evidence_urls or candidate.evidence_item_urls or (candidate.source_url,)))

    if candidate.validation_status in {"", "unknown", "unvalidated", "experimental"}:
        reasons.append("unvalidated_external_skill_evidence")
    if evidence_count <= 1:
        reasons.append("single_repository_level_source")
    if not candidate.evidence_item_ids:
        reasons.append("no_selected_digest_item_ids")
    if candidate.related_source_urls and len(set(candidate.related_source_urls)) > 1:
        reasons.append("fork_or_mirror_lineage_collapsed")
    if any(marker in text for marker in ("readme", "repository-level", "summary", "missing detail", "generic")):
        reasons.append("missing_detail_risk")

    return tuple(dict.fromkeys(reasons))


def _candidate_uncertainty_message(reasons: Sequence[str]) -> str:
    if not reasons:
        return "External skill evidence is bounded to local validation lanes and does not imply upstream implementation parity."
    if "missing_detail_risk" in reasons:
        return (
            "External skill evidence has missing_detail_risk; proposal lanes are local validation candidates, "
            "not upstream implementation parity or activation approval."
        )
    if "fork_or_mirror_lineage_collapsed" in reasons:
        return (
            "Fork or mirror evidence was collapsed into one lineage; repeated repository presence does not increase "
            "activation readiness."
        )
    return (
        "External skill evidence is unvalidated repository-level routing evidence; keep proposals local, bounded, "
        "and separately validated."
    )


def _summary_text(summary: ExternalSkillRepositorySummary) -> str:
    return " ".join((summary.name, summary.summary, *summary.topics)).casefold()


def _contains_term(text: str, term: str) -> bool:
    normalized = term.strip().casefold()
    if not normalized:
        return False
    if re.search(r"\s", normalized):
        return normalized in text
    return re.search(rf"(?<![\w-]){re.escape(normalized)}(?![\w-])", text) is not None


def _contains_explicit_skill_name(text: str, name: str) -> bool:
    normalized = name.strip().casefold()
    if not normalized:
        return False
    return any(_contains_term(text, marker + normalized) for marker in ("", "$", "@"))


def _normalize_discovery_event(value: Any) -> str:
    event_kind = str(value or "unknown").strip().lower().replace("-", "_")
    if event_kind in {"pullrequestevent", "pull_request_event", "pullrequest", "pull_request", "pr"}:
        return "pull_request"
    if event_kind in {"pushevent", "push_event", "push"}:
        return "push"
    if event_kind in {"releaseevent", "release_event", "release"}:
        return "release"
    if event_kind in {"create", "created", "repository_create", "repositorycreated"}:
        return "repository_created"
    if event_kind in {"delete", "deleted", "repository_delete", "repositorydeleted"}:
        return "repository_deleted"
    if event_kind in {"update", "updated", "repository_update", "repositoryupdated"}:
        return "repository_updated"
    return event_kind or "unknown"


def _normalize_evidence_item_kind(value: Any) -> str:
    item_kind = str(value or "repository").strip().lower().replace("-", "_")
    if item_kind in {"repo", "repository"}:
        return "repository"
    if item_kind in {"issue", "github_issue"}:
        return "issue"
    return item_kind or "repository"


def _validate_public_github_source_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").casefold()
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https":
        return "source_url_must_use_https"
    if host not in SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS:
        return "source_url_must_be_public_github_repository"
    if len(path_parts) != 2:
        return "source_url_must_include_repository_owner_and_name"
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        return "source_url_must_be_plain_repository_url"
    return None


def _canonical_public_github_repository_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").casefold()
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or host not in SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS or len(path_parts) < 2:
        raise ValueError("source_url_must_be_public_github_repository")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("source_url_must_be_plain_github_url")
    return f"https://github.com/{path_parts[0]}/{path_parts[1]}"


def _canonical_public_github_evidence_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").casefold()
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or host not in SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS or len(path_parts) < 2:
        raise ValueError("source_url_must_be_public_github_repository")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("source_url_must_be_plain_github_url")
    return f"https://github.com/{'/'.join(path_parts)}"


def _repository_name_from_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2:
        return ""
    return path_parts[1]


def _discovery_event_effect(event_kind: str) -> str:
    if event_kind == "repository_created":
        return "record_only_no_install"
    if event_kind == "repository_deleted":
        return "record_only_no_local_deletion"
    return "record_only"


def _unsupported_lanes_from_validation_errors(errors: Sequence[str]) -> list[str]:
    lanes: list[str] = []
    for error in errors:
        if not error.startswith("unsupported_candidate_lanes:"):
            continue
        raw_lanes = error.split(":", 1)[1]
        lanes.extend(lane for lane in raw_lanes.split(",") if lane)
    return sorted(dict.fromkeys(lanes))


def _proposal_lane_evidence_urls(candidate: Mapping[str, Any], source_url: str) -> list[str]:
    """Return lane evidence URLs without expanding beyond item-derived evidence.

    Registries built from frozen evidence items carry ``evidence_item_urls``.
    When present, proposal lanes cite only those item URLs even if broader
    candidate metadata contains extra repository, issue, or user-supplied URLs.
    Older summary/candidate registries do not have item provenance, so they keep
    the existing repository-level fallback.
    """

    item_urls = _string_list(candidate.get("evidence_item_urls"))
    if item_urls:
        return list(dict.fromkeys(item_urls))
    evidence_urls = _string_list(candidate.get("evidence_urls"))
    if evidence_urls:
        return list(dict.fromkeys(evidence_urls))
    return [source_url] if source_url else []


def _proposal_lane_evidence_item_ids(candidate: Mapping[str, Any]) -> list[str]:
    """Return frozen digest item ids carried by item-derived discovery records."""

    return list(dict.fromkeys(_string_list(candidate.get("evidence_item_ids"))))


def _route_weight(route: str) -> int:
    if route == EXACT_TRIGGER_MATCH:
        return 3
    if route == TOPICAL_MATCH:
        return 2
    return 1


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError("skill metadata fields must be strings or sequences of strings")


def _optional_list_field(name: str, values: Sequence[str]) -> dict[str, list[str]]:
    items = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    return {name: items} if items else {}
