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
SKILL_ROUTE_DISCOVERY_ROUTE_CLASS = "external_skill_route_discovery_classification"
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
SKILL_ROUTE_DISCOVERY_PROPOSAL_INTAKE_HINTS: Mapping[str, Mapping[str, str]] = {
    "generic_skill_workflow": {
        "proposal_id": "p1-skill-route-discovery-generic",
        "proposal_track": "generic_python_skill_repository",
    },
    "source_cited_domain_research": {
        "proposal_id": "p1-skill-route-discovery-generic",
        "proposal_track": "generic_python_skill_repository",
    },
    "game_frontend_workflow": {
        "proposal_id": "p2-game-frontend-skill-profile",
        "proposal_track": "game_frontend_workflow",
    },
    "skill_ecosystem_state_handoff": {
        "proposal_id": "p3-skill-ecosystem-handoff",
        "proposal_track": "skill_ecosystem_state_handoff",
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
    route_profiles: tuple[str, ...] = ()
    source_layout_signals: tuple[str, ...] = ()
    source_metadata_signals: tuple[str, ...] = ()
    public_activity_signals: tuple[str, ...] = ()
    requested_actions: tuple[str, ...] = ()
    validation_status: str = "unvalidated"
    enabled: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExternalSkillRouteCandidate":
        route_classification = _route_classification_mapping(value)
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
            route_hints=_string_tuple(
                value.get("route_hints")
                or route_classification.get("route_hints")
                or route_classification.get("route_hint")
            )
            or (SKILL_ROUTE_DISCOVERY_HINT,),
            candidate_lanes=_string_tuple(
                value.get("candidate_lanes")
                or route_classification.get("candidate_lanes")
                or route_classification.get("allowed_local_lanes")
                or route_classification.get("allowed_lanes")
            )
            or SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
            evidence_item_ids=_string_tuple(value.get("evidence_item_ids")),
            evidence_urls=_string_tuple(value.get("evidence_urls")),
            evidence_item_urls=_string_tuple(value.get("evidence_item_urls")),
            related_source_urls=_string_tuple(value.get("related_source_urls")),
            route_profiles=_string_tuple(
                value.get("route_profiles")
                or route_classification.get("route_profiles")
                or route_classification.get("route_profile")
            ),
            source_layout_signals=_string_tuple(
                value.get("source_layout_signals")
                or value.get("layout_signals")
                or value.get("file_layout_signals")
                or route_classification.get("source_layout_signals")
                or route_classification.get("layout_signals")
            ),
            source_metadata_signals=_string_tuple(
                value.get("source_metadata_signals")
                or value.get("metadata_signals")
                or value.get("repository_metadata_signals")
                or route_classification.get("source_metadata_signals")
                or route_classification.get("metadata_signals")
            ),
            public_activity_signals=_public_activity_signals(value),
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
        unsupported_profiles = sorted(
            set(self.route_profiles) - set(SKILL_ROUTE_DISCOVERY_ROUTE_PROFILE_VALIDATION_CONTRACTS)
        )
        if unsupported_profiles:
            errors.append("unsupported_route_profiles:" + ",".join(unsupported_profiles))
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
            "public_activity_signals": list(self.public_activity_signals),
            "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
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
    ignored_items: list[dict[str, Any]] = []
    ignored_count = 0
    duplicate_count = 0
    seen_evidence_urls: set[str] = set()
    source_digest = ""

    for item in items:
        if isinstance(item, Mapping) and not source_digest:
            source_digest = str(item.get("source_digest") or "").strip()
        evidence_item = _coerce_external_skill_evidence_item(item)
        summary = evidence_item.to_summary()
        route_classification = _route_classification_mapping(item) if isinstance(item, Mapping) else {}
        explicit_route_metadata = bool(
            _string_list(route_classification.get("route_profiles"))
            or _string_list(
                route_classification.get("source_layout_signals")
                or route_classification.get("layout_signals")
            )
            or _string_list(
                route_classification.get("source_metadata_signals")
                or route_classification.get("metadata_signals")
            )
        )
        if summary is None or (
            not _looks_like_skill_repository_summary(summary)
            and not explicit_route_metadata
        ):
            ignored_count += 1
            ignored_items.append(
                _skill_route_discovery_ignored_evidence_item(
                    evidence_item,
                    summary,
                    explicit_route_metadata=explicit_route_metadata,
                )
            )
            continue

        repository_url = summary.source_url
        bucket = grouped.setdefault(
            repository_url,
            {
                "discovery_event_kind": summary.discovery_event_kind,
                "evidence_urls": [],
                "item_ids": [],
                "lanes": [],
                "route_profiles": [],
                "source_layout_signals": [],
                "source_metadata_signals": [],
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
        bucket["route_profiles"].extend(_string_list(route_classification.get("route_profiles")))
        bucket["source_layout_signals"].extend(
            _string_list(
                route_classification.get("source_layout_signals")
                or route_classification.get("layout_signals")
            )
        )
        bucket["source_metadata_signals"].extend(
            _string_list(
                route_classification.get("source_metadata_signals")
                or route_classification.get("metadata_signals")
            )
        )
        bucket["summaries"].append(summary.summary)

    candidates = [
        ExternalSkillRouteCandidate(
            name=str(bucket["name"]),
            source_url=repository_url,
            evidence_summary=" ".join(dict.fromkeys(bucket["summaries"])),
            discovery_event_kind=str(bucket["discovery_event_kind"]),
            candidate_lanes=tuple(dict.fromkeys(bucket["lanes"])) or ("documentation",),
            route_profiles=tuple(dict.fromkeys(bucket["route_profiles"])),
            evidence_item_ids=tuple(dict.fromkeys(bucket["item_ids"])),
            evidence_item_urls=tuple(bucket["evidence_urls"]),
            evidence_urls=tuple(bucket["evidence_urls"]),
            source_layout_signals=tuple(dict.fromkeys(bucket["source_layout_signals"])),
            source_metadata_signals=tuple(dict.fromkeys(bucket["source_metadata_signals"])),
            validation_status="unvalidated",
            enabled=False,
        )
        for repository_url, bucket in grouped.items()
    ]
    registry = build_skill_route_discovery_registry(candidates)
    registry["evidence_item_count"] = len(items)
    registry["ignored_evidence_item_count"] = ignored_count
    registry["ignored_evidence_items"] = ignored_items
    registry["duplicate_evidence_item_count"] = duplicate_count
    if source_digest:
        registry["source_digest"] = source_digest
    return registry


def build_skill_route_discovery_registry_validation_lane(registry: Mapping[str, Any]) -> dict[str, Any]:
    """Validate registry shape and route availability before proposal activation."""

    diagnostics: list[str] = []
    if registry.get("schema_version") != 1:
        diagnostics.append("registry.schema_version_must_be_1")
    if registry.get("route_hint") != SKILL_ROUTE_DISCOVERY_HINT:
        diagnostics.append("registry.route_hint_mismatch")
    if registry.get("allowed_candidate_lanes") != list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES):
        diagnostics.append("registry.allowed_candidate_lanes_mismatch")
    if registry.get("allowed_source_hosts") != list(SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS):
        diagnostics.append("registry.allowed_source_hosts_mismatch")

    raw_candidates = registry.get("candidates")
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
        return {
            "controller_surface": "skill_route_discovery_registry_validation_lane",
            "status": "blocked",
            "decision": "repair_skill_route_registry_before_lane_activation",
            "diagnostics": ["registry.candidates_must_be_a_sequence", *diagnostics],
            "candidate_count": 0,
            "available_route_count": 0,
            "unavailable_route_count": 0,
            "rows": [],
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        }

    candidates = list(raw_candidates)
    declared_candidate_count = registry.get("candidate_count")
    if declared_candidate_count != len(candidates):
        diagnostics.append(f"registry.candidate_count_mismatch:{declared_candidate_count}!={len(candidates)}")

    rows: list[dict[str, Any]] = []
    for index, raw_candidate in enumerate(candidates):
        prefix = f"candidates[{index}]"
        if not isinstance(raw_candidate, Mapping):
            diagnostics.append(f"{prefix}.entry_must_be_an_object")
            rows.append(
                {
                    "candidate_index": index,
                    "candidate_name": "",
                    "route_available": False,
                    "diagnostics": [f"{prefix}.entry_must_be_an_object"],
                }
            )
            continue

        candidate = dict(raw_candidate)
        name = str(candidate.get("name") or "")
        candidate_diagnostics: list[str] = []
        missing_fields: set[str] = set()
        for field_name in (
            "name",
            "source_url",
            "candidate_lanes",
            "route_hints",
            "route_class",
            "route_status",
            "route_profiles",
            "validation_errors",
            "enabled",
        ):
            if field_name not in candidate:
                missing_fields.add(field_name)
                candidate_diagnostics.append(f"{prefix}.{field_name}_missing")

        candidate_lanes = _string_list(candidate.get("candidate_lanes"))
        allowed_lanes = [lane for lane in candidate_lanes if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES]
        unsupported_lanes = sorted(set(candidate_lanes) - set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES))
        route_hints = _string_list(candidate.get("route_hints"))
        route_profiles = _string_list(candidate.get("route_profiles"))
        validation_errors = _string_list(candidate.get("validation_errors"))

        if not name:
            candidate_diagnostics.append(f"{prefix}.name_empty")
        if not str(candidate.get("source_url") or ""):
            candidate_diagnostics.append(f"{prefix}.source_url_empty")
        if not allowed_lanes:
            candidate_diagnostics.append(f"{prefix}.no_allowed_candidate_lanes")
        if unsupported_lanes:
            candidate_diagnostics.append(f"{prefix}.unsupported_candidate_lanes:" + ",".join(unsupported_lanes))
        if SKILL_ROUTE_DISCOVERY_HINT not in route_hints:
            candidate_diagnostics.append(f"{prefix}.route_hints_missing_skill_route_discovery")
        if candidate.get("route_class") != SKILL_ROUTE_DISCOVERY_ROUTE_CLASS:
            candidate_diagnostics.append(f"{prefix}.route_class_mismatch")
        if str(candidate.get("route_status") or "") not in {
            SKILL_ROUTE_DISCOVERY_DISABLED,
            SKILL_ROUTE_DISCOVERY_INVALID,
        }:
            candidate_diagnostics.append(f"{prefix}.route_status_must_be_disabled_or_invalid")
        if validation_errors:
            candidate_diagnostics.append(f"{prefix}.validation_errors:" + ",".join(validation_errors))
        if candidate.get("enabled") is not False:
            candidate_diagnostics.append(f"{prefix}.enabled_must_be_false")
        if "route_profiles" not in missing_fields and not route_profiles:
            candidate_diagnostics.append(f"{prefix}.route_profiles_missing")
        if "validation_errors" not in missing_fields and (
            not isinstance(candidate.get("validation_errors"), Sequence)
            or isinstance(candidate.get("validation_errors"), (str, bytes))
        ):
            candidate_diagnostics.append(f"{prefix}.validation_errors_must_be_a_sequence")

        route_available = not candidate_diagnostics and not validation_errors
        diagnostics.extend(candidate_diagnostics)
        rows.append(
            {
                "candidate_index": index,
                "candidate_name": name,
                "route_available": route_available,
                "route_hint_available": SKILL_ROUTE_DISCOVERY_HINT in route_hints,
                "route_class": str(candidate.get("route_class") or ""),
                "route_status": str(candidate.get("route_status") or ""),
                "route_profiles": route_profiles,
                "allowed_candidate_lanes": allowed_lanes,
                "validation_error_count": len(validation_errors),
                "diagnostics": candidate_diagnostics,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
            }
        )

    available_route_count = sum(1 for row in rows if row["route_available"])
    status = "ready" if rows and not diagnostics else "blocked"
    return {
        "controller_surface": "skill_route_discovery_registry_validation_lane",
        "status": status,
        "decision": (
            "skill_route_registry_ready_for_local_lane_mapping"
            if status == "ready"
            else "repair_skill_route_registry_before_lane_activation"
        ),
        "diagnostics": diagnostics,
        "candidate_count": len(rows),
        "declared_candidate_count": declared_candidate_count,
        "available_route_count": available_route_count,
        "unavailable_route_count": len(rows) - available_route_count,
        "allowed_candidate_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "required_route_hint": SKILL_ROUTE_DISCOVERY_HINT,
        "required_route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
        "validation_gate": "skill_route_discovery_registry_validation_before_activation",
        "rows": rows,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
    }


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
        public_activity_policy = _skill_route_discovery_public_activity_policy_field(candidate)
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
                "downgraded_lane_names": unsupported_lanes,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
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
                **public_activity_policy,
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
                    "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
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
                    **public_activity_policy,
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
    privacy_review_panel = _skill_route_discovery_privacy_review_panel(
        candidate_lane_inventory,
        rejected_candidates,
        downgraded_candidates,
    )
    completion_workflow = _skill_route_discovery_completion_workflow(
        local_activation_targets,
        adoption_manifest,
        privacy_review_panel,
        route_profile_handoff_queue,
    )
    ignored_evidence_items = _mapping_list(registry.get("ignored_evidence_items"))
    pass4_local_lane_validation = _skill_route_discovery_pass4_local_lane_validation(
        candidate_lane_inventory,
        ignored_evidence_items,
    )
    pass4_completion_handoff = _skill_route_discovery_pass4_completion_handoff(
        pass4_local_lane_validation
    )
    pass4_operator_replay_manifest = _skill_route_discovery_pass4_operator_replay_manifest(
        pass4_completion_handoff
    )
    active_pass4_completion_matrix = _skill_route_discovery_active_pass4_completion_matrix(
        pass4_completion_handoff,
        pass4_operator_replay_manifest,
    )
    registry_validation_lane = build_skill_route_discovery_registry_validation_lane(registry)
    pass2_fixture_validation_lane = _skill_route_discovery_pass2_fixture_validation_lane(
        candidate_lane_inventory
    )
    pass2_profile_lane_handoff = _skill_route_discovery_pass2_profile_lane_handoff(
        candidate_lane_inventory
    )
    pass2_validation_handoff = _skill_route_discovery_pass2_validation_handoff(
        local_activation_targets,
        route_profile_handoff_queue,
    )
    growth_route_summary_artifact = _skill_route_discovery_growth_route_summary_artifact(
        pass2_fixture_validation_lane,
        pass2_profile_lane_handoff,
        pass2_validation_handoff,
        downgraded_candidates,
    )
    current_pass2_validation_lane = _skill_route_discovery_current_pass2_validation_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
    )
    current_window_pass2_focused_review = _skill_route_discovery_current_window_pass2_focused_review(
        candidate_lane_inventory,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    pass3_route_discovery_index = _skill_route_discovery_pass3_route_discovery_index(
        candidate_lane_inventory
    )
    pass3_activation_handoff = _skill_route_discovery_pass3_activation_handoff(
        candidate_lane_inventory
    )
    pass3_preflight_queue = _skill_route_discovery_pass3_preflight_queue(
        candidate_lane_inventory
    )
    pass3_local_validation_lane = _skill_route_discovery_pass3_local_validation_lane(
        candidate_lane_inventory
    )

    return {
        "schema_version": 1,
        "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
        "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
        "allowed_proposal_kinds": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "source_registry_status": str(registry.get("registry_status") or ""),
        "candidate_count": len(candidates),
        "proposal_lane_count": len(proposal_lanes),
        "rejected_candidate_count": len(rejected_candidates),
        "downgraded_candidate_count": len(downgraded_candidates),
        "route_profile_catalog": _skill_route_discovery_route_profile_catalog(proposal_lanes),
        "local_lane_matrix": _skill_route_discovery_local_lane_matrix(candidate_lane_inventory),
        "bounded_route_profile_matrix": _skill_route_discovery_bounded_route_profile_matrix(
            candidate_lane_inventory
        ),
        "validation_profile_coverage": _skill_route_discovery_validation_profile_coverage(
            candidate_lane_inventory
        ),
        "proposal_intake_lane": _skill_route_discovery_proposal_intake_lane(candidate_lane_inventory),
        "focused_evidence_review_lane": _skill_route_discovery_focused_evidence_review_lane(
            candidate_lane_inventory
        ),
        "active_pass1_evidence_lane": _skill_route_discovery_active_pass1_evidence_lane(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        ),
        "active_window_pass1_route_lanes": _skill_route_discovery_active_window_pass1_route_lanes(
            candidate_lane_inventory,
            ignored_evidence_items,
        ),
        "current_pass_validation_cases": _skill_route_discovery_current_pass_validation_cases(
            candidate_lane_inventory
        ),
        "pass2_fixture_validation_lane": pass2_fixture_validation_lane,
        "pass2_profile_lane_handoff": pass2_profile_lane_handoff,
        "current_pass2_validation_lane": current_pass2_validation_lane,
        "current_window_pass2_focused_review": current_window_pass2_focused_review,
        "growth_route_summary_artifact": growth_route_summary_artifact,
        "pass3_route_discovery_index": pass3_route_discovery_index,
        "pass3_activation_handoff": pass3_activation_handoff,
        "pass3_preflight_queue": pass3_preflight_queue,
        "pass3_local_validation_lane": pass3_local_validation_lane,
        "pass3_current_wake_acceptance_packet": _skill_route_discovery_pass3_current_wake_acceptance_packet(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        ),
        "pass3_active_window_review_packet": _skill_route_discovery_pass3_active_window_review_packet(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        ),
        "pass3_active_proposal_acceptance_lane": _skill_route_discovery_pass3_active_proposal_acceptance_lane(
            candidate_lane_inventory,
            source_digest=_skill_route_discovery_source_digest(registry),
        ),
        "pass4_local_lane_validation": pass4_local_lane_validation,
        "pass4_completion_handoff": pass4_completion_handoff,
        "pass4_operator_replay_manifest": pass4_operator_replay_manifest,
        "active_pass4_completion_matrix": active_pass4_completion_matrix,
        "local_activation_targets": local_activation_targets,
        "route_profile_handoff_queue": route_profile_handoff_queue,
        "pass1_validation_matrix": _skill_route_discovery_pass1_validation_matrix(local_activation_targets),
        "pass2_validation_handoff": pass2_validation_handoff,
        "adoption_manifest": adoption_manifest,
        "privacy_review_panel": privacy_review_panel,
        "completion_workflow": completion_workflow,
        "next_validation_step": _skill_route_discovery_next_validation_step(local_activation_targets),
        "registry_validation_lane": registry_validation_lane,
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


def _route_classification_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return frozen fixture route metadata without requiring a top-level shape."""

    route_classification = value.get("route_classification")
    if isinstance(route_classification, Mapping):
        return route_classification
    classification = value.get("classification")
    if isinstance(classification, Mapping):
        return classification
    return {}


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

    if candidate.route_profiles:
        return tuple(dict.fromkeys(candidate.route_profiles))

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


def _skill_route_discovery_ignored_evidence_item(
    evidence_item: ExternalSkillEvidenceItem,
    summary: ExternalSkillRepositorySummary | None,
    *,
    explicit_route_metadata: bool,
) -> dict[str, Any]:
    """Keep ignored public evidence body-free and queued behind the right lane."""

    try:
        source_hash = _stable_hash(evidence_item.canonical_repository_url())
    except ValueError:
        source_hash = _stable_hash(evidence_item.source_url)

    if summary is None:
        ignored_reason = "route_hint_not_skill_route_discovery"
    elif explicit_route_metadata:
        ignored_reason = "explicit_route_metadata_without_skill_workflow_signal"
    else:
        ignored_reason = "no_skill_workflow_signal"

    return {
        "item_id": evidence_item.item_id,
        "item_kind": evidence_item.item_kind,
        "name": evidence_item.name or _repository_name_from_url(evidence_item.source_url),
        "source_hash": source_hash,
        "route_hints": list(evidence_item.route_hints),
        "ignored_reason": ignored_reason,
        "evaluation_lane": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "direct_runtime_route_allowed": False,
        "direct_code_patch_route_allowed": False,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_body_exported": False,
    }


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


def _skill_route_discovery_public_activity_policy_field(candidate: Mapping[str, Any]) -> dict[str, Any]:
    signals = _string_list(candidate.get("public_activity_signals"))
    if not signals:
        return {}
    return {"public_activity_policy": _skill_route_discovery_public_activity_policy(signals)}


def _skill_route_discovery_public_activity_policy(signals: Sequence[str]) -> dict[str, Any]:
    """Keep stars, forks, and similar public activity out of activation decisions."""

    return {
        "signals": list(dict.fromkeys(str(signal) for signal in signals if str(signal).strip())),
        "signal_count": len(signals),
        "effect": "supporting_context_only_no_runtime_action",
        "candidate_count_effect": "none",
        "proposal_lane_count_effect": "none",
        "activation_readiness_effect": "none",
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
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


def _skill_route_discovery_bounded_route_profile_matrix(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Map observed skill-route profiles to bounded local validation lanes."""

    rows_by_profile: dict[str, dict[str, Any]] = {}
    observed_lanes: list[str] = []
    required_profiles = (
        "generic_skill_workflow",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    )

    for candidate in candidate_lane_inventory:
        candidate_name = str(candidate.get("candidate_name") or "")
        source_hash = _stable_hash(str(candidate.get("source_url") or candidate_name))
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        proposal_kinds = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        observed_lanes.extend(proposal_kinds)
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        if selected_lane not in proposal_kinds:
            selected_lane = proposal_kinds[0] if proposal_kinds else ""

        for profile in route_profiles:
            row = rows_by_profile.get(profile)
            if row is None:
                row = {
                    "route_profile": profile,
                    "status": "ready" if selected_lane else "blocked",
                    "candidate_names": [],
                    "candidate_source_hashes": [],
                    "allowed_local_lanes": [],
                    "selected_local_lanes": [],
                    "validation_targets": [],
                    "replay_commands": [],
                    "activation_boundary": _skill_route_discovery_profile_activation_boundary(profile),
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
                rows_by_profile[profile] = row
            elif not selected_lane:
                row["status"] = "blocked"

            row["candidate_names"] = list(
                dict.fromkeys((*_string_list(row.get("candidate_names")), candidate_name))
            )
            row["candidate_source_hashes"] = list(
                dict.fromkeys((*_string_list(row.get("candidate_source_hashes")), source_hash))
            )
            row["allowed_local_lanes"] = [
                lane
                for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                if lane in {*_string_list(row.get("allowed_local_lanes")), *proposal_kinds}
            ]
            row["selected_local_lanes"] = list(
                dict.fromkeys((*_string_list(row.get("selected_local_lanes")), selected_lane))
            )
            row["validation_targets"] = list(
                dict.fromkeys(
                    (
                        *_string_list(row.get("validation_targets")),
                        _skill_route_discovery_validation_target(selected_lane, (profile,)),
                    )
                )
            )
            row["replay_commands"] = list(
                dict.fromkeys(
                    (
                        *_string_list(row.get("replay_commands")),
                        _skill_route_discovery_replay_command(selected_lane, (profile,)),
                    )
                )
            )

    rows = [rows_by_profile[profile] for profile in sorted(rows_by_profile)]
    blocked_profiles = [row["route_profile"] for row in rows if row["status"] != "ready"]
    observed_profiles = [row["route_profile"] for row in rows]
    return {
        "controller_surface": "skill_route_discovery_bounded_route_profile_matrix",
        "status": "ready" if rows and not blocked_profiles else "blocked",
        "decision": (
            "route_profiles_mapped_to_bounded_local_lanes"
            if rows and not blocked_profiles
            else "repair_route_profile_lane_mapping_before_activation"
        ),
        "required_profiles": list(required_profiles),
        "observed_route_profiles": observed_profiles,
        "covered_required_profiles": [
            profile for profile in required_profiles if profile in set(observed_profiles)
        ],
        "missing_required_profiles": [
            profile for profile in required_profiles if profile not in set(observed_profiles)
        ],
        "observed_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_lanes)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "blocked_route_profiles": blocked_profiles,
        "row_count": len(rows),
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


def _skill_route_discovery_profile_activation_boundary(profile: str) -> str:
    return {
        "game_frontend_workflow": "validate_local_frontend_or_workflow_check_before_any_scaffold_or_asset_path",
        "skill_ecosystem_state_handoff": "validate_state_privacy_and_metadata_boundary_before_profile_or_memory_write",
        "generic_skill_workflow": "validate_body_free_local_artifact_before_skill_activation",
        "codex_workflow_gate": "prove_skill_route_discovery_first_before_secondary_workflow_handling",
        "source_cited_domain_research": "validate_citation_and_advice_boundary_before_domain_behavior",
    }.get(profile, "validate_bounded_local_lane_before_activation")


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


def _skill_route_discovery_proposal_intake_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Map observed route profiles back to current-window proposal lanes.

    The intake lane is a proposal-review surface, not an activation surface. It
    lets the controller see that carried proposal IDs have local lane coverage
    before deciding which concrete patch, doc, config, or test lane to replay.
    """

    rows_by_proposal: dict[str, dict[str, Any]] = {}

    for candidate in candidate_lane_inventory:
        candidate_name = str(candidate.get("candidate_name") or "")
        source_url = str(candidate.get("source_url") or candidate_name)
        local_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        if not local_lanes:
            continue

        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        if selected_lane not in local_lanes:
            selected_lane = local_lanes[0]
        validation_gates = _string_list(handoff_metadata.get("validation_gates"))
        evidence_item_ids = _string_list(candidate.get("evidence_item_ids"))

        for profile in route_profiles:
            hint = SKILL_ROUTE_DISCOVERY_PROPOSAL_INTAKE_HINTS.get(profile)
            if hint is None:
                continue
            proposal_id = hint["proposal_id"]
            row = rows_by_proposal.setdefault(
                proposal_id,
                {
                    "proposal_id": proposal_id,
                    "proposal_track": hint["proposal_track"],
                    "status": "ready",
                    "candidate_names": [],
                    "candidate_source_hashes": [],
                    "route_profiles": [],
                    "allowed_local_lanes": [],
                    "selected_local_lanes": [],
                    "validation_gates": [],
                    "validation_targets": [],
                    "replay_commands": [],
                    "selected_evidence_item_ids": [],
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
                },
            )
            row["candidate_names"] = list(
                dict.fromkeys((*_string_list(row.get("candidate_names")), candidate_name))
            )
            row["candidate_source_hashes"] = list(
                dict.fromkeys((*_string_list(row.get("candidate_source_hashes")), _stable_hash(source_url)))
            )
            row["route_profiles"] = list(
                dict.fromkeys((*_string_list(row.get("route_profiles")), profile))
            )
            row["allowed_local_lanes"] = [
                lane
                for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                if lane in {*_string_list(row.get("allowed_local_lanes")), *local_lanes}
            ]
            row["selected_local_lanes"] = list(
                dict.fromkeys((*_string_list(row.get("selected_local_lanes")), selected_lane))
            )
            row["validation_gates"] = list(
                dict.fromkeys((*_string_list(row.get("validation_gates")), *validation_gates))
            )
            row["validation_targets"] = list(
                dict.fromkeys(
                    (
                        *_string_list(row.get("validation_targets")),
                        _skill_route_discovery_validation_target(selected_lane, (profile,)),
                    )
                )
            )
            row["replay_commands"] = list(
                dict.fromkeys(
                    (
                        *_string_list(row.get("replay_commands")),
                        _skill_route_discovery_replay_command(selected_lane, (profile,)),
                    )
                )
            )
            row["selected_evidence_item_ids"] = list(
                dict.fromkeys((*_string_list(row.get("selected_evidence_item_ids")), *evidence_item_ids))
            )

    rows = [rows_by_proposal[proposal_id] for proposal_id in sorted(rows_by_proposal)]
    blocked_rows = [
        row["proposal_id"]
        for row in rows
        if not row["allowed_local_lanes"] or not row["selected_local_lanes"]
    ]

    return {
        "controller_surface": "skill_route_discovery_proposal_intake_lane",
        "status": "ready" if rows and not blocked_rows else "blocked",
        "decision": (
            "current_window_proposals_mapped_to_bounded_local_lanes"
            if rows and not blocked_rows
            else "collect_or_repair_current_window_proposal_lanes"
        ),
        "proposal_count": len(rows),
        "ready_proposal_count": len(rows) - len(blocked_rows),
        "blocked_proposal_ids": blocked_rows,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "required_evidence": [
            "body_free_repository_summary",
            "route_hints",
            "focused_local_validation",
            "rollback_artifact",
        ],
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


def _skill_route_discovery_active_pass1_evidence_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Expose the active pass-1 evidence split before any activation route."""

    rows: list[dict[str, Any]] = []
    blocked_candidate_names: list[str] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []

    for candidate in sorted(
        candidate_lane_inventory,
        key=lambda value: str(value.get("candidate_name") or ""),
    ):
        candidate_name = str(candidate.get("candidate_name") or "")
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        allowed_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        if selected_lane not in allowed_lanes:
            selected_lane = allowed_lanes[0] if allowed_lanes else ""
        validation_gates = _string_list(handoff_metadata.get("validation_gates"))
        proposal_id = _skill_route_discovery_pass1_proposal_id(route_profiles)
        row_ready = bool(
            proposal_id
            and selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and allowed_lanes
            and validation_gates
            and candidate.get("local_validation_required") is True
            and str(candidate.get("runtime_action") or "none") == "none"
            and candidate.get("external_skill_activation_allowed") is False
        )
        if not row_ready and candidate_name:
            blocked_candidate_names.append(candidate_name)
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(route_profiles)

        rows.append(
            {
                "proposal_id": proposal_id,
                "candidate_name": candidate_name,
                "candidate_source_hash": _stable_hash(str(candidate.get("source_url") or candidate_name)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": route_profiles,
                "allowed_local_lanes": allowed_lanes,
                "selected_local_lane": selected_lane,
                "selected_evidence_item_ids": _string_list(candidate.get("evidence_item_ids")),
                "validation_gates": validation_gates,
                "validation_target": _skill_route_discovery_validation_target(selected_lane, route_profiles),
                "row_status": "ready" if row_ready else "blocked",
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

    adjacent_rows = [
        {
            "proposal_id": "p3-agent-harness-eval-for-general-agent-projects",
            "item_id": str(item.get("item_id") or ""),
            "item_kind": str(item.get("item_kind") or ""),
            "name": str(item.get("name") or ""),
            "source_hash": str(item.get("source_hash") or ""),
            "ignored_reason": str(item.get("ignored_reason") or ""),
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes": [],
            "direct_runtime_route_allowed": False,
            "direct_code_patch_route_allowed": False,
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "replay_command": "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        for item in ignored_evidence_items
    ]

    required_profiles = [
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    ]
    observed_profile_set = set(observed_profiles)
    missing_profiles = [profile for profile in required_profiles if profile not in observed_profile_set]
    accepted_rows_ready = bool(rows) and not blocked_candidate_names and not missing_profiles
    adjacent_rows_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        for row in adjacent_rows
    )
    ready = accepted_rows_ready and adjacent_rows_ready

    return {
        "controller_surface": "skill_route_discovery_active_pass1_evidence_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass1_skill_route_evidence_ready_for_local_validation"
            if ready
            else "repair_active_pass1_evidence_split_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260627T142310.634775Z",
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-fixtures",
            "p2-game-frontend-skill-profile",
            "p3-agent-harness-eval-for-general-agent-projects",
        ],
        "required_route_profiles": required_profiles,
        "covered_route_profiles": [
            profile for profile in required_profiles if profile in observed_profile_set
        ],
        "missing_route_profiles": missing_profiles,
        "accepted_skill_route_count": len(rows),
        "adjacent_general_agent_count": len(adjacent_rows),
        "blocked_candidate_names": blocked_candidate_names,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_source_digest(registry: Mapping[str, Any]) -> str:
    """Return caller-provided digest metadata without deriving it from URLs."""

    return str(registry.get("source_digest") or "").strip()


def _skill_route_discovery_active_window_pass1_route_lanes(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose this wake's active pass-1 proposal anchors as bounded lanes."""

    route_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-generic",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_gate": "focused-evidence-review",
            "validation_target": "skill_workflow_lanes_stay_bounded",
        },
        {
            "proposal_id": "p2-game-frontend-skill-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_gate": "local_frontend_validation_before_game_skill_activation",
            "validation_target": "document_game_frontend_workflow_boundary",
        },
        {
            "proposal_id": "p3-skill-ecosystem-state-handoff",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_gate": "state_handoff_boundary_before_profile_or_memory_write",
            "validation_target": "state_or_profile_boundary_metadata",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_selected_lanes: list[str] = []
    for spec in route_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        observed_profiles: list[str] = []
        observed_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda value: str(value.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            observed_profiles.extend(candidate_profiles)
            observed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )

        allowed_local_lanes = [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_lanes)
        ]
        selected_lane = str(spec["selected_local_lane"])
        if selected_lane in allowed_local_lanes:
            observed_selected_lanes.append(selected_lane)
        row_ready = bool(
            candidate_names
            and set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES).issubset(set(allowed_local_lanes))
            and selected_lane in allowed_local_lanes
            and selected_evidence_item_ids
        )
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if row_ready else "blocked",
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile for profile in spec["route_profiles"] if profile in set(observed_profiles)
                ],
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_lane if selected_lane in allowed_local_lanes else "",
                "queued_local_lanes": [
                    lane for lane in allowed_local_lanes if lane != selected_lane
                ],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gate": spec["validation_gate"],
                "validation_target": spec["validation_target"],
                "code_patch_approval_gate": "selected_lane_local_validation_before_code_patch",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_general_agent_rows = [
        {
            "item_id": str(item.get("item_id") or ""),
            "name": str(item.get("name") or ""),
            "source_hash": str(item.get("source_hash") or ""),
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_runtime_route_allowed": False,
            "direct_code_patch_route_allowed": False,
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        for item in ignored_evidence_items
    ]
    blocked_proposal_ids = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_proposal_ids and all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        for row in adjacent_general_agent_rows
    )

    return {
        "controller_surface": "skill_route_discovery_active_window_pass1_route_lanes",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_window_pass1_skill_route_lanes_ready_for_local_validation"
            if ready
            else "repair_active_window_pass1_skill_route_lanes_before_activation"
        ),
        "source_digest": "github-growth-20260627T190729.505995Z",
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in route_specs],
        "blocked_proposal_ids": blocked_proposal_ids,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_selected_lanes)
        ],
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_general_agent_rows,
    }


def _skill_route_discovery_focused_evidence_review_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Review active skill-route proposals before any local activation path."""

    review_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-baseline",
            "proposal_kind": "test",
            "proposal_track": "bounded_skill_workflow_lane_classification",
            "route_profiles": (
                "generic_skill_workflow",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
                "source_cited_domain_research",
            ),
            "selected_local_lane": "test",
            "validation_gate": "focused-evidence-review",
            "validation_target": "skill_workflow_lanes_stay_bounded",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k focused_evidence_review",
        },
        {
            "proposal_id": "p2-skill-ecosystem-documentation",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_interpretation_rules",
            "route_profiles": (
                "generic_skill_workflow",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
                "source_cited_domain_research",
            ),
            "selected_local_lane": "documentation",
            "validation_gate": "focused-evidence-review",
            "validation_target": "document_allowed_lanes_and_uncertainty_limits",
            "replay_command": "python -m pytest tests/test_docs_contracts.py tests/test_skill_routing.py -q -k skill_route",
        },
        {
            "proposal_id": "p3-game-frontend-skill-validation",
            "proposal_kind": "code_patch",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_gate": "local_frontend_validation_before_game_skill_activation",
            "validation_target": "local_frontend_render_or_workflow_check",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k game_frontend",
        },
    )

    rows: list[dict[str, Any]] = []
    for spec in review_specs:
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        observed_profiles: list[str] = []
        observed_lanes: list[str] = []
        required_profiles = set(_string_list(spec["route_profiles"]))

        for candidate in candidate_lane_inventory:
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            source_url = str(candidate.get("source_url") or candidate_name)
            candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(source_url))
            evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            observed_profiles.extend(candidate_profiles)
            observed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )

        allowed_local_lanes = [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_lanes)
        ]
        selected_lane = str(spec["selected_local_lane"])
        status = "ready" if candidate_names and selected_lane in allowed_local_lanes else "blocked"
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": status,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_profiles": [
                    profile for profile in spec["route_profiles"] if profile in set(observed_profiles)
                ],
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_lane if selected_lane in allowed_local_lanes else "",
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gate": spec["validation_gate"],
                "validation_target": spec["validation_target"],
                "replay_command": spec["replay_command"],
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

    blocked_rows = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    return {
        "controller_surface": "skill_route_discovery_focused_evidence_review_lane",
        "status": "ready" if rows and not blocked_rows else "blocked",
        "decision": (
            "active_skill_route_proposals_ready_for_bounded_local_validation"
            if rows and not blocked_rows
            else "repair_active_skill_route_proposal_review_before_activation"
        ),
        "review_gate": "focused-evidence-review",
        "proposal_count": len(rows),
        "ready_proposal_count": len(rows) - len(blocked_rows),
        "blocked_proposal_ids": blocked_rows,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
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


def _skill_route_discovery_current_pass_validation_cases(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose this pass's proposal IDs as bounded local validation cases."""

    case_specs = (
        {
            "proposal_id": "p1_skill_route_discovery_generic_views",
            "proposal_kind": "test",
            "proposal_track": "generic_python_skill_repository",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_gate": "focused-evidence-review",
            "validation_target": "skill_workflow_lanes_stay_bounded",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k current_pass_validation_cases",
        },
        {
            "proposal_id": "p2_skill_route_discovery_game_frontend",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_gate": "focused-evidence-review",
            "validation_target": "document_game_frontend_workflow_boundary",
            "replay_command": "python -m pytest tests/test_docs_contracts.py tests/test_skill_routing.py -q -k skill_route_discovery",
        },
        {
            "proposal_id": "p3_skill_ecosystem_state_handoff_config",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_gate": "focused-evidence-review",
            "validation_target": "state_or_profile_boundary_metadata",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k state_handoff",
        },
    )

    rows: list[dict[str, Any]] = []
    for spec in case_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        observed_profiles: list[str] = []
        observed_lanes: list[str] = []
        selected_evidence_item_ids: list[str] = []

        for candidate in candidate_lane_inventory:
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_names.append(str(candidate.get("candidate_name") or ""))
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or "")))
            observed_profiles.extend(candidate_profiles)
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            observed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )

        allowed_local_lanes = [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_lanes)
        ]
        selected_lane = str(spec["selected_local_lane"])
        status = "ready" if candidate_names and selected_lane in allowed_local_lanes else "blocked"
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": status,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_profiles": [
                    profile for profile in spec["route_profiles"] if profile in set(observed_profiles)
                ],
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_lane if selected_lane in allowed_local_lanes else "",
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gate": spec["validation_gate"],
                "validation_target": spec["validation_target"],
                "replay_command": spec["replay_command"],
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

    blocked_rows = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    return {
        "controller_surface": "skill_route_discovery_current_pass_validation_cases",
        "status": "ready" if rows and not blocked_rows else "blocked",
        "decision": (
            "current_pass_skill_route_cases_ready_for_bounded_local_validation"
            if rows and not blocked_rows
            else "repair_current_pass_skill_route_cases_before_activation"
        ),
        "review_gate": "focused-evidence-review",
        "proposal_count": len(rows),
        "ready_proposal_count": len(rows) - len(blocked_rows),
        "blocked_proposal_ids": blocked_rows,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "required_evidence": [
            "body_free_repository_summary",
            "matched_skill_or_agent_topics",
            "focused_local_validation",
            "rollback_artifact",
        ],
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


def _skill_route_discovery_pass2_fixture_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate frozen pass-2 route fixtures before activation handoff."""

    rows: list[dict[str, Any]] = []
    blocked_candidate_names: list[str] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    replay_commands: list[str] = []

    for candidate in sorted(
        candidate_lane_inventory,
        key=lambda item: str(item.get("candidate_name") or "").casefold(),
    ):
        candidate_name = str(candidate.get("candidate_name") or "")
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        allowed_local_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        validation_gates = _string_list(handoff_metadata.get("validation_gates"))
        selected_evidence_item_ids = _string_list(candidate.get("evidence_item_ids"))
        selected_lanes.append(selected_lane)
        observed_profiles.extend(route_profiles)

        blockers: list[str] = []
        if str(candidate.get("route_class") or "") != SKILL_ROUTE_DISCOVERY_ROUTE_CLASS:
            blockers.append("route_class_mismatch")
        if not allowed_local_lanes:
            blockers.append("missing_bounded_local_lanes")
        if set(allowed_local_lanes) - set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES):
            blockers.append("unbounded_local_lane_present")
        if selected_lane not in allowed_local_lanes:
            blockers.append("selected_lane_not_allowed")
        if candidate.get("local_validation_required") is not True:
            blockers.append("local_validation_required_not_preserved")
        if str(candidate.get("runtime_action") or "none") != "none":
            blockers.append("runtime_action_requested")
        if candidate.get("external_skill_activation_allowed") is not False:
            blockers.append("external_skill_activation_not_denied")
        if blockers and candidate_name:
            blocked_candidate_names.append(candidate_name)

        replay_command = _skill_route_discovery_replay_command(selected_lane, route_profiles)
        if replay_command:
            replay_commands.append(replay_command)

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": _stable_hash(str(candidate.get("source_url") or candidate_name)),
                "route_class": str(candidate.get("route_class") or ""),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_profiles": route_profiles,
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_lane if selected_lane in allowed_local_lanes else "",
                "selected_evidence_item_ids": selected_evidence_item_ids,
                "validation_gates": validation_gates,
                "validation_target": _skill_route_discovery_validation_target(selected_lane, route_profiles),
                "replay_command": replay_command,
                "fixture_status": "ready" if not blockers else "blocked",
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

    ready = bool(rows) and not blocked_candidate_names
    return {
        "controller_surface": "skill_route_discovery_pass2_fixture_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "pass2_route_fixtures_ready_for_bounded_local_validation"
            if ready
            else "repair_pass2_route_fixtures_before_activation"
        ),
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "candidate_count": len(rows),
        "ready_candidate_count": len([row for row in rows if row["fixture_status"] == "ready"]),
        "blocked_candidate_names": blocked_candidate_names,
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "route_classification_fixture",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
        ],
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


def _skill_route_discovery_current_pass2_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind the active pass-2 skill-route and adjacent agent-eval evidence."""

    rows: list[dict[str, Any]] = []
    blocked_rows: list[str] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []

    for candidate in sorted(
        candidate_lane_inventory,
        key=lambda item: str(item.get("candidate_name") or "").casefold(),
    ):
        candidate_name = str(candidate.get("candidate_name") or "")
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        profile_set = set(route_profiles)
        allowed_local_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        if selected_lane not in allowed_local_lanes:
            selected_lane = allowed_local_lanes[0] if allowed_local_lanes else ""

        if "game_frontend_workflow" in profile_set:
            proposal_id = "p3-game-frontend-skill-profile"
        elif "skill_ecosystem_state_handoff" in profile_set:
            proposal_id = "p4-skill-ecosystem-state-handoff"
        else:
            proposal_id = "p1-skill-route-discovery-general"

        validation_gates = _string_list(handoff_metadata.get("validation_gates"))
        selected_item_ids = _string_list(candidate.get("evidence_item_ids"))
        blockers: list[str] = []
        if proposal_id == "p1-skill-route-discovery-general" and not (
            profile_set & {"generic_skill_workflow", "source_cited_domain_research"}
        ):
            blockers.append("generic_skill_workflow_profile_missing")
        if str(candidate.get("route_class") or "") != SKILL_ROUTE_DISCOVERY_ROUTE_CLASS:
            blockers.append("route_class_mismatch")
        if not allowed_local_lanes:
            blockers.append("missing_bounded_local_lanes")
        if selected_lane not in allowed_local_lanes:
            blockers.append("selected_lane_not_allowed")
        if not selected_item_ids:
            blockers.append("selected_evidence_item_ids_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if candidate.get("local_validation_required") is not True:
            blockers.append("local_validation_required_not_preserved")
        if str(candidate.get("runtime_action") or "none") != "none":
            blockers.append("runtime_action_requested")
        if candidate.get("external_skill_activation_allowed") is not False:
            blockers.append("external_skill_activation_not_denied")

        if blockers and candidate_name:
            blocked_rows.append(candidate_name)
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(route_profiles)

        rows.append(
            {
                "proposal_id": proposal_id,
                "candidate_name": candidate_name,
                "candidate_source_hash": _stable_hash(str(candidate.get("source_url") or candidate_name)),
                "route_class": str(candidate.get("route_class") or ""),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_profiles": route_profiles,
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_lane,
                "selected_evidence_item_ids": selected_item_ids,
                "validation_gates": validation_gates,
                "validation_target": _skill_route_discovery_validation_target(selected_lane, route_profiles),
                "replay_command": _skill_route_discovery_replay_command(selected_lane, route_profiles),
                "row_status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p2-agent-harness-eval",
    )
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["external_harness_execution_allowed"] is False
        for row in adjacent_rows
    )
    has_generic_skill_route = any(
        row["proposal_id"] == "p1-skill-route-discovery-general" and row["row_status"] == "ready"
        for row in rows
    )
    has_game_skill_route = any(
        row["proposal_id"] == "p3-game-frontend-skill-profile" and row["row_status"] == "ready"
        for row in rows
    )
    ready = bool(rows) and not blocked_rows and has_generic_skill_route and has_game_skill_route and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_pass2_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_pass2_skill_and_agent_evidence_ready_for_local_validation"
            if ready
            else "repair_current_pass2_skill_or_agent_eval_boundary_before_activation"
        ),
        "source_digest": "github-growth-20260627T192729.517144Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-general",
            "p2-agent-harness-eval",
            "p3-game-frontend-skill-profile",
        ],
        "skill_route_candidate_count": len(rows),
        "adjacent_general_agent_count": len(adjacent_rows),
        "ready_skill_route_candidate_count": len([row for row in rows if row["row_status"] == "ready"]),
        "blocked_skill_route_candidate_names": blocked_rows,
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "agent_harness_eval_required": bool(adjacent_rows),
        "agent_harness_required_signals": [
            "install_shape",
            "entrypoints",
            "dependency_boundaries",
            "task_loop_assumptions",
            "observable_behaviors",
            "evaluation_dimensions",
        ],
        "agent_harness_evaluation_dimensions": [
            "format",
            "factuality",
            "consistency",
            "realism",
            "quality",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_window_pass2_focused_review(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose the active pass-2 skill-route proposals as bounded review rows."""

    review_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-generic",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_fixture_keeps_lanes_bounded",
        },
        {
            "proposal_id": "p2-skill-route-discovery-game-frontend-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "document_game_frontend_skill_route_as_local_validation_candidate",
        },
        {
            "proposal_id": "p3-skill-ecosystem-state-handoff",
            "proposal_kind": "test",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "test",
            "validation_target": "compass_style_state_handoff_fixture_denies_runtime_action",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_local_lanes: list[str] = []
    observed_profiles: list[str] = []
    for spec in review_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_url_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        row_profiles: list[str] = []

        for candidate in candidate_lane_inventory:
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            source_url = str(candidate.get("source_url") or candidate.get("candidate_name") or "")
            candidate_names.append(str(candidate.get("candidate_name") or ""))
            candidate_source_hashes.append(_stable_hash(source_url))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            evidence_url_hashes.extend(
                _stable_hash(url)
                for url in _string_list(candidate.get("evidence_urls"))
            )
            row_profiles.extend(candidate_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )

        allowed_local_lanes = [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)
        ]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in allowed_local_lanes:
            blockers.append("selected_local_lane_not_available")
        if not selected_evidence_item_ids:
            blockers.append("selected_evidence_item_ids_missing")
        status = "ready" if not blockers else "blocked"
        if selected_lane in allowed_local_lanes:
            selected_local_lanes.append(selected_lane)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": status,
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "evidence_url_hashes": list(dict.fromkeys(evidence_url_hashes)),
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "route_profiles": [
                    profile for profile in spec["route_profiles"] if profile in set(row_profiles)
                ],
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_lane if selected_lane in allowed_local_lanes else "",
                "validation_gate": "focused-evidence-review",
                "validation_target": spec["validation_target"],
                "replay_command": "python -m pytest tests/test_skill_routing.py -q -k current_window_pass2_focused_review",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_proposal_ids = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_window_pass2_focused_review",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_window_pass2_skill_routes_ready_for_focused_local_validation"
            if ready
            else "repair_current_window_pass2_skill_routes_before_activation"
        ),
        "source_digest": source_digest or "unknown",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in review_specs],
        "proposal_count": len(rows),
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_local_lanes)
        ],
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_digest_evidence",
            "body_free_repository_summary",
            "hashed_evidence_urls",
            "rollback_artifact",
            "focused_local_validation",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass2_profile_lane_handoff(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose pass-2 profile lanes for operator replay before activation.

    The handoff is derived from already-classified candidate inventory. It makes
    profile-specific replay lanes visible without adding runtime authority or
    exporting upstream source bodies.
    """

    specs = (
        {
            "proposal_id": "proposal-skill-route-discovery-generic-zhengxi-views",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "generic_skill_workflow_fixture_stays_bounded",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k pass2_route_classification_fixture",
        },
        {
            "proposal_id": "proposal-game-frontend-skill-profile-doc-test",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_target": "game_frontend_workflow_profile_maps_to_local_validation",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k pass2_route_classification_fixture",
        },
        {
            "proposal_id": "proposal-skill-ecosystem-state-handoff-config-doc",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "skill_ecosystem_state_handoff_maps_to_metadata_only_config",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k pass2_route_classification_fixture",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    downgraded_lane_names: list[str] = []
    replay_commands: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        matched_profiles: list[str] = []
        matched_downgraded_lanes: list[str] = []

        for candidate in candidate_lane_inventory:
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_names.append(str(candidate.get("candidate_name") or ""))
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or "")))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            matched_downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")

        status = "ready" if not blockers else "blocked"
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)
        downgraded_lane_names.extend(matched_downgraded_lanes)
        replay_commands.append(str(spec["replay_command"]))
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": status,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "replay_command": spec["replay_command"],
                "downgraded_lane_names": list(dict.fromkeys(matched_downgraded_lanes)),
                "activation_blockers": blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_rows = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_rows
    return {
        "controller_surface": "skill_route_discovery_pass2_profile_lane_handoff",
        "status": "ready" if ready else "blocked",
        "decision": (
            "pass2_profiles_ready_for_operator_replay"
            if ready
            else "repair_pass2_profile_lane_handoff_before_activation"
        ),
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "operator_handoff": "external_supervisor_replay_before_activation",
        "proposal_count": len(rows),
        "ready_proposal_count": len(rows) - len(blocked_rows),
        "blocked_proposal_ids": blocked_rows,
        "observed_route_profiles": sorted(dict.fromkeys(observed_profiles)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "downgraded_lane_names": sorted(dict.fromkeys(downgraded_lane_names)),
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "route_classification_fixture",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "changed_file_review",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass3_route_discovery_index(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Map the active pass-3 skill proposals to bounded local validation lanes."""

    specs = (
        {
            "proposal_id": "p1_skill_route_discovery_index",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "skill_workflow_item_shapes_preserve_bounded_lanes",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k pass3_route_discovery_index",
        },
        {
            "proposal_id": "p2_skill_workflow_docs",
            "proposal_kind": "documentation",
            "proposal_track": "skill_workflow_documentation",
            "route_profiles": ("game_frontend_workflow", "generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "documentation",
            "validation_target": "document_skill_route_discovery_lane_boundary",
            "replay_command": "python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery",
        },
        {
            "proposal_id": "p3_skill_route_metadata_config",
            "proposal_kind": "config",
            "proposal_track": "route_profile_metadata_config",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "route_profile_metadata_maps_to_bounded_lanes",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k pass3_route_discovery_index",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_local_lanes: list[str] = []
    observed_profiles: list[str] = []
    replay_commands: list[str] = []
    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        matched_profiles: list[str] = []
        validation_gates: list[str] = []
        metadata_signals: list[str] = []
        layout_signals: list[str] = []

        for candidate in candidate_lane_inventory:
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_names.append(str(candidate.get("candidate_name") or ""))
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or "")))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            metadata_signals.extend(_string_list(candidate.get("source_metadata_signals")))
            layout_signals.extend(_string_list(candidate.get("source_layout_signals")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")

        status = "ready" if not blockers else "blocked"
        if selected_lane in bounded_lanes:
            selected_local_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)
        replay_commands.append(str(spec["replay_command"]))
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": status,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "replay_command": spec["replay_command"],
                "source_layout_signals": list(dict.fromkeys(layout_signals)),
                "source_metadata_signals": list(dict.fromkeys(metadata_signals)),
                "activation_blockers": blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_rows = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_rows
    return {
        "controller_surface": "skill_route_discovery_pass3_route_discovery_index",
        "status": "ready" if ready else "blocked",
        "decision": (
            "pass3_skill_route_profiles_indexed_for_bounded_local_validation"
            if ready
            else "repair_pass3_skill_route_profile_index_before_activation"
        ),
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_count": len(rows),
        "ready_proposal_count": len(rows) - len(blocked_rows),
        "blocked_proposal_ids": blocked_rows,
        "observed_route_profiles": sorted(dict.fromkeys(observed_profiles)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_local_lanes)
        ],
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "three_skill_workflow_item_shapes",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "focused_local_validation",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass3_activation_handoff(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Prepare the active skill-route pass for supervisor replay.

    Pass 3 is the review handoff between current validation cases and final
    completion. It does not activate upstream skills; it makes the activation
    blockers and local replay commands visible before a supervisor can promote
    the route.
    """

    proposal_aliases = {
        "p1_skill_route_discovery_generic_views": "p1-skill-route-discovery-zhengxi-views",
        "p2_skill_route_discovery_game_frontend": "p2-game-frontend-skill-route",
        "p3_skill_ecosystem_state_handoff_config": "p3-skill-ecosystem-state-handoff",
    }
    validation_cases = _skill_route_discovery_current_pass_validation_cases(candidate_lane_inventory)
    focused_review = _skill_route_discovery_focused_evidence_review_lane(candidate_lane_inventory)

    rows: list[dict[str, Any]] = []
    for case_row in validation_cases["rows"]:
        if not isinstance(case_row, Mapping):
            continue
        case_proposal_id = str(case_row.get("proposal_id") or "")
        status = str(case_row.get("status") or "blocked")
        activation_blockers = []
        if status != "ready":
            activation_blockers.append("current_pass_validation_case_not_ready")
        if not _string_list(case_row.get("candidate_names")):
            activation_blockers.append("missing_candidate_evidence")
        if not _string_list(case_row.get("selected_local_lane")):
            activation_blockers.append("missing_selected_local_lane")

        rows.append(
            {
                "proposal_id": proposal_aliases.get(case_proposal_id, case_proposal_id),
                "source_case_id": case_proposal_id,
                "status": status,
                "activation_decision": (
                    "ready_for_supervisor_replay"
                    if status == "ready" and not activation_blockers
                    else "blocked_before_activation"
                ),
                "candidate_names": _string_list(case_row.get("candidate_names")),
                "candidate_source_hashes": _string_list(case_row.get("candidate_source_hashes")),
                "route_profiles": _string_list(case_row.get("route_profiles")),
                "allowed_local_lanes": _string_list(case_row.get("allowed_local_lanes")),
                "selected_local_lane": str(case_row.get("selected_local_lane") or ""),
                "selected_evidence_item_ids": _string_list(case_row.get("selected_evidence_item_ids")),
                "validation_gate": str(case_row.get("validation_gate") or ""),
                "validation_target": str(case_row.get("validation_target") or ""),
                "replay_command": str(case_row.get("replay_command") or ""),
                "activation_blockers": activation_blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_rows = [row["proposal_id"] for row in rows if row["activation_decision"] != "ready_for_supervisor_replay"]
    replay_commands = list(dict.fromkeys(row["replay_command"] for row in rows if row["replay_command"]))
    focused_review_ready = focused_review.get("status") == "ready"
    status = "ready" if rows and not blocked_rows and focused_review_ready else "blocked"
    return {
        "controller_surface": "skill_route_discovery_pass3_activation_handoff",
        "status": status,
        "decision": (
            "pass3_skill_route_handoff_ready_for_supervisor_replay"
            if status == "ready"
            else "repair_pass3_skill_route_handoff_before_activation"
        ),
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [row["proposal_id"] for row in rows],
        "ready_proposal_count": len(rows) - len(blocked_rows),
        "blocked_proposal_ids": blocked_rows,
        "focused_review_status": str(focused_review.get("status") or ""),
        "focused_review_blocked_proposal_ids": _string_list(focused_review.get("blocked_proposal_ids")),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": list(
            dict.fromkeys(row["selected_local_lane"] for row in rows if row["selected_local_lane"])
        ),
        "replay_commands": replay_commands,
        "recovery_workflow": (
            "run_replay_commands_then_recheck_pass3_activation_handoff"
            if status == "ready"
            else "repair_blocked_rows_then_rerun_current_pass_validation_cases"
        ),
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass3_preflight_queue(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose pass-3 profile coverage and replay commands before final pass.

    The queue joins the pass-3 route index with activation handoff status so a
    supervisor can see whether each active profile has a bounded local lane
    before any final-pass completion workflow is considered.
    """

    required_route_profiles = (
        "source_cited_domain_research",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    )
    route_index = _skill_route_discovery_pass3_route_discovery_index(candidate_lane_inventory)
    activation_handoff = _skill_route_discovery_pass3_activation_handoff(candidate_lane_inventory)
    activation_rows = [
        row for row in activation_handoff.get("rows", []) if isinstance(row, Mapping)
    ]

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    replay_commands: list[str] = []
    queue_blockers: list[str] = []

    for index_row in route_index.get("rows", []):
        if not isinstance(index_row, Mapping):
            continue
        proposal_id = str(index_row.get("proposal_id") or "")
        route_profiles = _string_list(index_row.get("route_profiles"))
        allowed_local_lanes = _string_list(index_row.get("allowed_local_lanes"))
        selected_local_lane = str(index_row.get("selected_local_lane") or "")
        replay_command = str(index_row.get("replay_command") or "")
        activation_blockers = _string_list(index_row.get("activation_blockers"))
        matching_activation_rows = [
            row
            for row in activation_rows
            if set(_string_list(row.get("route_profiles"))) & set(route_profiles)
        ]
        for activation_row in matching_activation_rows:
            activation_blockers.extend(_string_list(activation_row.get("activation_blockers")))

        if str(index_row.get("status") or "") != "ready":
            activation_blockers.append("route_index_row_not_ready")
        if matching_activation_rows and any(
            str(row.get("activation_decision") or "") != "ready_for_supervisor_replay"
            for row in matching_activation_rows
        ):
            activation_blockers.append("activation_handoff_row_not_ready")
        if not matching_activation_rows and activation_handoff.get("status") != "ready":
            activation_blockers.append("activation_handoff_row_missing")
        if selected_local_lane not in allowed_local_lanes:
            activation_blockers.append("selected_lane_not_bounded")
        if not _string_list(index_row.get("selected_evidence_item_ids")):
            activation_blockers.append("missing_selected_item_ids_or_frozen_fixture")

        observed_profiles.extend(route_profiles)
        if selected_local_lane:
            selected_lanes.append(selected_local_lane)
        if replay_command:
            replay_commands.append(replay_command)
        if activation_blockers:
            queue_blockers.extend(f"{proposal_id}:{blocker}" for blocker in activation_blockers)

        rows.append(
            {
                "proposal_id": proposal_id,
                "status": "ready" if not activation_blockers else "blocked",
                "queue_decision": (
                    "ready_for_final_pass_replay"
                    if not activation_blockers
                    else "blocked_before_final_pass_replay"
                ),
                "candidate_names": _string_list(index_row.get("candidate_names")),
                "candidate_source_hashes": _string_list(index_row.get("candidate_source_hashes")),
                "route_profiles": route_profiles,
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_local_lane if selected_local_lane in allowed_local_lanes else "",
                "selected_evidence_item_ids": _string_list(index_row.get("selected_evidence_item_ids")),
                "validation_gates": _string_list(index_row.get("validation_gates")),
                "validation_target": str(index_row.get("validation_target") or ""),
                "replay_command": replay_command,
                "activation_blockers": list(dict.fromkeys(activation_blockers)),
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    observed_required_profiles = [
        profile for profile in required_route_profiles if profile in set(observed_profiles)
    ]
    missing_route_profiles = [
        profile for profile in required_route_profiles if profile not in set(observed_profiles)
    ]
    if missing_route_profiles:
        queue_blockers.append("missing_required_route_profiles:" + ",".join(missing_route_profiles))

    ready = (
        bool(rows)
        and not queue_blockers
        and route_index.get("status") == "ready"
        and activation_handoff.get("status") == "ready"
    )
    return {
        "controller_surface": "skill_route_discovery_pass3_preflight_queue",
        "status": "ready" if ready else "blocked",
        "decision": (
            "pass3_skill_route_preflight_ready_for_final_pass_replay"
            if ready
            else "repair_pass3_skill_route_preflight_before_final_pass"
        ),
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "operator_handoff": "external_supervisor_replay_before_final_pass",
        "route_index_status": str(route_index.get("status") or ""),
        "activation_handoff_status": str(activation_handoff.get("status") or ""),
        "required_route_profiles": list(required_route_profiles),
        "observed_route_profiles": observed_required_profiles,
        "missing_route_profiles": missing_route_profiles,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": list(dict.fromkeys(selected_lanes)),
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "queue_blockers": list(dict.fromkeys(queue_blockers)),
        "row_count": len(rows),
        "ready_row_count": len([row for row in rows if row["status"] == "ready"]),
        "blocked_proposal_ids": [row["proposal_id"] for row in rows if row["status"] != "ready"],
        "required_evidence": [
            "pass3_route_discovery_index",
            "pass3_activation_handoff",
            "selected_item_ids_or_frozen_fixture",
            "rollback_artifact",
            "focused_local_validation",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass3_local_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Expose the active pass-3 skill-route proposals as local validation lanes."""

    specs = (
        {
            "proposal_id": "p1-skill-route-discovery-index",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow",),
            "selected_local_lane": "test",
            "validation_target": "skill_like_repository_fixtures_keep_lanes_bounded",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k pass3_local_validation_lane",
        },
        {
            "proposal_id": "p2-game-frontend-skill-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "document_game_frontend_workflow_without_expanding_lanes",
            "replay_command": "python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery",
        },
        {
            "proposal_id": "p3-skill-ecosystem-state-handoff",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_metadata_stays_local_and_body_free",
            "replay_command": "python -m pytest tests/test_skill_routing.py -q -k pass3_local_validation_lane",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    replay_commands: list[str] = []
    downgraded_lane_names: list[str] = []
    uncertainty_notes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        matched_profiles: list[str] = []
        validation_gates: list[str] = []
        matched_downgraded_lanes: list[str] = []
        row_uncertainty_notes: list[str] = []

        for candidate in candidate_lane_inventory:
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_names.append(str(candidate.get("candidate_name") or ""))
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or "")))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            matched_downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))
            row_uncertainty_notes.append(str(candidate.get("uncertainty") or ""))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")

        status = "ready" if not blockers else "blocked"
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)
        replay_commands.append(str(spec["replay_command"]))
        downgraded_lane_names.extend(matched_downgraded_lanes)
        uncertainty_notes.extend(note for note in row_uncertainty_notes if note)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": status,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "replay_command": spec["replay_command"],
                "bounded_lane_contract": {
                    "controller_surface": "skill_route_discovery_pass3_bounded_lane_contract",
                    "selected_lane_bounded": selected_lane in bounded_lanes,
                    "allowed_lane_count": len(bounded_lanes),
                    "unsupported_lanes_removed": sorted(dict.fromkeys(matched_downgraded_lanes)),
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
                },
                "downgraded_lane_names": list(dict.fromkeys(matched_downgraded_lanes)),
                "uncertainty": next((note for note in row_uncertainty_notes if note), ""),
                "activation_blockers": blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_rows = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_rows
    return {
        "controller_surface": "skill_route_discovery_pass3_local_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "pass3_skill_route_local_lanes_ready_for_validation"
            if ready
            else "repair_pass3_skill_route_local_lanes_before_activation"
        ),
        "source_digest": "github-growth-20260627T194729.481658Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "operator_handoff": "external_supervisor_replay_before_final_pass",
        "proposal_count": len(rows),
        "ready_proposal_count": len(rows) - len(blocked_rows),
        "blocked_proposal_ids": blocked_rows,
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "downgraded_lane_names": sorted(dict.fromkeys(downgraded_lane_names)),
        "uncertainty_notes": list(dict.fromkeys(note for note in uncertainty_notes if note)),
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "three_skill_workflow_item_shapes",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_replay_contract": _skill_route_discovery_pass3_operator_replay_contract(rows, ready),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass3_operator_replay_contract(
    rows: Sequence[Mapping[str, Any]],
    ready: bool,
) -> dict[str, Any]:
    """Give the supervisor one body-free replay contract for pass-3 skill lanes."""

    blocked_proposal_ids = [
        str(row.get("proposal_id") or "")
        for row in rows
        if str(row.get("status") or "") != "ready"
    ]
    replay_commands = [
        str(row.get("replay_command") or "")
        for row in rows
        if str(row.get("replay_command") or "").strip()
    ]
    return {
        "controller_surface": "skill_route_discovery_pass3_operator_replay_contract",
        "status": "ready" if ready else "blocked",
        "decision": (
            "supervisor_can_replay_pass3_skill_lanes_before_final_pass"
            if ready
            else "repair_pass3_skill_lanes_before_supervisor_replay"
        ),
        "proposal_ids": [
            str(row.get("proposal_id") or "")
            for row in rows
            if str(row.get("proposal_id") or "").strip()
        ],
        "blocked_proposal_ids": [proposal_id for proposal_id in blocked_proposal_ids if proposal_id],
        "row_count": len(rows),
        "ready_row_count": len(rows) - len(blocked_proposal_ids),
        "selected_local_lanes": list(
            dict.fromkeys(
                str(row.get("selected_local_lane") or "")
                for row in rows
                if str(row.get("selected_local_lane") or "").strip()
            )
        ),
        "replay_command_hashes": [_stable_hash(command) for command in dict.fromkeys(replay_commands)],
        "rollback_artifact_required": True,
        "rollback_ref_required": True,
        "activation_gate": "local_validation_before_activation",
        "operator_next_action": (
            "run_replay_commands_then_continue_to_final_pass"
            if ready
            else "repair_blocked_rows_then_rebuild_pass3_local_validation_lane"
        ),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def _skill_route_discovery_pass3_current_wake_acceptance_packet(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Bind the active pass-3 proposals to bounded lanes and eval-only adjacency."""

    skill_rows: list[dict[str, Any]] = []
    candidate_names: list[str] = []
    candidate_source_hashes: list[str] = []
    route_profiles: list[str] = []
    selected_evidence_item_ids: list[str] = []
    validation_gates: list[str] = []
    unsupported_lane_names: list[str] = []
    skill_blockers: list[str] = []

    for candidate in sorted(
        candidate_lane_inventory,
        key=lambda item: str(item.get("candidate_name") or "").casefold(),
    ):
        candidate_name = str(candidate.get("candidate_name") or "")
        allowed_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        candidate_item_ids = _string_list(candidate.get("evidence_item_ids"))
        candidate_validation_gates = _skill_route_discovery_validation_gates(candidate)
        candidate_blockers: list[str] = []
        if str(candidate.get("route_class") or "") != SKILL_ROUTE_DISCOVERY_ROUTE_CLASS:
            candidate_blockers.append("route_class_mismatch")
        if not allowed_lanes:
            candidate_blockers.append("bounded_local_lanes_missing")
        if not candidate_item_ids:
            candidate_blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if candidate.get("local_validation_required") is not True:
            candidate_blockers.append("local_validation_not_required")
        if str(candidate.get("runtime_action") or "none") != "none":
            candidate_blockers.append("runtime_action_requested")
        if candidate.get("external_skill_activation_allowed") is not False:
            candidate_blockers.append("external_skill_activation_not_denied")

        if candidate_blockers:
            skill_blockers.extend(f"{candidate_name}:{blocker}" for blocker in candidate_blockers)

        candidate_names.append(candidate_name)
        candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
        route_profiles.extend(candidate_profiles)
        selected_evidence_item_ids.extend(candidate_item_ids)
        validation_gates.extend(candidate_validation_gates)
        unsupported_lane_names.extend(_string_list(candidate.get("downgraded_lane_names")))

        skill_rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": _stable_hash(str(candidate.get("source_url") or candidate_name)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": str(candidate.get("route_class") or ""),
                "route_profiles": candidate_profiles,
                "allowed_local_lanes": allowed_lanes,
                "selected_evidence_item_ids": candidate_item_ids,
                "validation_gates": candidate_validation_gates,
                "activation_blockers": candidate_blockers,
                "row_status": "ready" if not candidate_blockers else "blocked",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    required_profiles = (
        "generic_skill_workflow",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    )
    observed_profile_set = set(route_profiles)
    missing_profiles = [profile for profile in required_profiles if profile not in observed_profile_set]
    if missing_profiles:
        skill_blockers.append("missing_required_route_profiles:" + ",".join(missing_profiles))

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-eval-fixtures",
    )
    adjacent_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "replay_command"
        }
        | {
            "replay_command_hash": _stable_hash(str(row.get("replay_command") or "")),
            "raw_replay_command_exported": False,
        }
        for row in adjacent_rows
    ]
    adjacent_blockers: list[str] = []
    for row in adjacent_rows:
        item_id = str(row.get("item_id") or "")
        if row["evaluation_lane"] != "agent_harness_eval_required":
            adjacent_blockers.append(f"{item_id}:evaluation_lane_not_agent_harness_eval_required")
        if row["skill_route_discovery_inherited"] is not False:
            adjacent_blockers.append(f"{item_id}:skill_route_discovery_inherited")
        if row["direct_runtime_route_allowed"] is not False:
            adjacent_blockers.append(f"{item_id}:direct_runtime_route_allowed")
        if row["direct_code_patch_route_allowed"] is not False:
            adjacent_blockers.append(f"{item_id}:direct_code_patch_route_allowed")
        if row["external_harness_execution_allowed"] is not False:
            adjacent_blockers.append(f"{item_id}:external_harness_execution_allowed")

    proposal_rows = [
        {
            "proposal_id": "p1-skill-route-discovery-index",
            "proposal_kind": "test",
            "selected_local_lane": "test",
            "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
            "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
            "route_profiles": sorted(dict.fromkeys(route_profiles)),
            "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
            "validation_gates": list(dict.fromkeys(validation_gates)),
            "validation_target": "current_wake_skill_route_index_fixtures_keep_lanes_bounded",
            "replay_command_hash": _stable_hash(
                "python -m pytest tests/test_skill_routing.py -q -k pass3_current_wake_acceptance_packet"
            ),
            "status": "ready" if skill_rows and not skill_blockers else "blocked",
            "activation_blockers": skill_blockers,
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
        },
        {
            "proposal_id": "p2-skill-route-discovery-docs",
            "proposal_kind": "documentation",
            "selected_local_lane": "documentation",
            "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
            "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
            "route_profiles": sorted(dict.fromkeys(route_profiles)),
            "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
            "validation_gates": list(dict.fromkeys(validation_gates)),
            "validation_target": "document_current_wake_skill_route_boundary_without_expanding_lanes",
            "replay_command_hash": _stable_hash(
                "python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery"
            ),
            "status": "ready" if skill_rows and not skill_blockers else "blocked",
            "activation_blockers": skill_blockers,
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
        },
        {
            "proposal_id": "p3-agent-harness-eval-fixtures",
            "proposal_kind": "test",
            "selected_local_lane": "agent_harness_eval_required",
            "candidate_names": [str(row.get("name") or "") for row in adjacent_rows],
            "candidate_source_hashes": [str(row.get("source_hash") or "") for row in adjacent_rows],
            "route_profiles": [],
            "selected_evidence_item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
            "validation_gates": ["local_agent_harness_eval_required_before_implementation_route"],
            "validation_target": "general_agent_projects_without_skill_workflow_stay_eval_only",
            "replay_command_hash": _stable_hash(
                "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
            ),
            "status": "ready" if adjacent_rows and not adjacent_blockers else "blocked",
            "activation_blockers": adjacent_blockers,
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        },
    ]

    blocked_proposal_ids = [
        str(row["proposal_id"])
        for row in proposal_rows
        if row["status"] != "ready"
    ]
    ready = bool(proposal_rows) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_pass3_current_wake_acceptance_packet",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_wake_pass3_lanes_ready_for_supervisor_acceptance"
            if ready
            else "repair_current_wake_pass3_lane_acceptance_before_final_pass"
        ),
        "source_digest": source_digest or "github-growth-20260627T210729.503389Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-index",
            "p2-skill-route-discovery-docs",
            "p3-agent-harness-eval-fixtures",
        ],
        "ready_proposal_count": len(proposal_rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(skill_rows),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": sorted(dict.fromkeys(route_profiles)),
        "missing_route_profiles": missing_profiles,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": ["test", "documentation"],
        "adjacent_evaluation_lane": "agent_harness_eval_required",
        "unsupported_lane_names_removed": sorted(dict.fromkeys(unsupported_lane_names)),
        "required_evidence": [
            "three_skill_workflow_item_shapes",
            "adjacent_general_agent_item_without_skill_workflow_signal",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
        ],
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": proposal_rows,
        "skill_route_rows": skill_rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_pass3_active_window_review_packet(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Expose this pass-3 proposal window as one bounded review packet."""

    skill_rows: list[dict[str, Any]] = []
    candidate_names: list[str] = []
    candidate_source_hashes: list[str] = []
    route_profiles: list[str] = []
    selected_evidence_item_ids: list[str] = []
    validation_gates: list[str] = []
    unsupported_lane_names: list[str] = []
    skill_blockers: list[str] = []

    for candidate in sorted(
        candidate_lane_inventory,
        key=lambda item: str(item.get("candidate_name") or "").casefold(),
    ):
        candidate_name = str(candidate.get("candidate_name") or "")
        allowed_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        candidate_item_ids = _string_list(candidate.get("evidence_item_ids"))
        candidate_validation_gates = _skill_route_discovery_validation_gates(candidate)
        candidate_blockers: list[str] = []
        if not set(candidate_profiles).intersection(
            {"generic_skill_workflow", "game_frontend_workflow", "skill_ecosystem_state_handoff"}
        ):
            candidate_blockers.append("unsupported_route_profile_for_active_window")
        if not allowed_lanes:
            candidate_blockers.append("bounded_local_lanes_missing")
        if not candidate_item_ids:
            candidate_blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if candidate.get("local_validation_required") is not True:
            candidate_blockers.append("local_validation_not_required")
        if str(candidate.get("runtime_action") or "none") != "none":
            candidate_blockers.append("runtime_action_requested")
        if candidate.get("external_skill_activation_allowed") is not False:
            candidate_blockers.append("external_skill_activation_not_denied")

        if candidate_blockers:
            skill_blockers.extend(f"{candidate_name}:{blocker}" for blocker in candidate_blockers)

        candidate_names.append(candidate_name)
        candidate_source_hash = _stable_hash(str(candidate.get("source_url") or candidate_name))
        candidate_source_hashes.append(candidate_source_hash)
        route_profiles.extend(candidate_profiles)
        selected_evidence_item_ids.extend(candidate_item_ids)
        validation_gates.extend(candidate_validation_gates)
        unsupported_lane_names.extend(_string_list(candidate.get("downgraded_lane_names")))

        skill_rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": candidate_source_hash,
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": str(candidate.get("route_class") or ""),
                "route_profiles": candidate_profiles,
                "allowed_local_lanes": allowed_lanes,
                "selected_evidence_item_ids": candidate_item_ids,
                "validation_gates": candidate_validation_gates,
                "classification_decision": "skill_route_discovery_first",
                "activation_blockers": candidate_blockers,
                "row_status": "ready" if not candidate_blockers else "blocked",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    required_profiles = (
        "generic_skill_workflow",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    )
    observed_profile_set = set(route_profiles)
    missing_profiles = [profile for profile in required_profiles if profile not in observed_profile_set]
    if missing_profiles:
        skill_blockers.append("missing_required_route_profiles:" + ",".join(missing_profiles))

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-eval-fixtures",
    )
    adjacent_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "replay_command"
        }
        | {
            "replay_command_hash": _stable_hash(str(row.get("replay_command") or "")),
            "raw_replay_command_exported": False,
        }
        for row in adjacent_rows
    ]
    adjacent_blockers: list[str] = []
    for row in adjacent_rows:
        item_id = str(row.get("item_id") or "")
        if row["evaluation_lane"] != "agent_harness_eval_required":
            adjacent_blockers.append(f"{item_id}:evaluation_lane_not_agent_harness_eval_required")
        if row["skill_route_discovery_inherited"] is not False:
            adjacent_blockers.append(f"{item_id}:skill_route_discovery_inherited")
        if row["direct_runtime_route_allowed"] is not False:
            adjacent_blockers.append(f"{item_id}:direct_runtime_route_allowed")
        if row["direct_code_patch_route_allowed"] is not False:
            adjacent_blockers.append(f"{item_id}:direct_code_patch_route_allowed")
        if row["external_harness_execution_allowed"] is not False:
            adjacent_blockers.append(f"{item_id}:external_harness_execution_allowed")

    proposal_rows = [
        {
            "proposal_id": "p1-skill-route-discovery-matrix",
            "proposal_kind": "test",
            "selected_local_lane": "test",
            "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
            "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
            "route_profiles": sorted(dict.fromkeys(route_profiles)),
            "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
            "validation_gates": list(dict.fromkeys(validation_gates)),
            "validation_target": "active_window_skill_workflow_matrix_keeps_lanes_bounded",
            "replay_command_hash": _stable_hash(
                "python -m pytest tests/test_skill_routing.py -q -k pass3_active_window_review_packet"
            ),
            "status": "ready" if skill_rows and not skill_blockers else "blocked",
            "activation_blockers": skill_blockers,
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
        },
        {
            "proposal_id": "p2-skill-route-documentation",
            "proposal_kind": "documentation",
            "selected_local_lane": "documentation",
            "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
            "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
            "route_profiles": sorted(dict.fromkeys(route_profiles)),
            "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
            "validation_gates": list(dict.fromkeys(validation_gates)),
            "validation_target": "document_active_window_skill_route_interpretation",
            "replay_command_hash": _stable_hash(
                "python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery"
            ),
            "status": "ready" if skill_rows and not skill_blockers else "blocked",
            "activation_blockers": skill_blockers,
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
        },
        {
            "proposal_id": "p3-agent-harness-eval-fixtures",
            "proposal_kind": "test",
            "selected_local_lane": "agent_harness_eval_required",
            "candidate_names": [str(row.get("name") or "") for row in adjacent_rows],
            "candidate_source_hashes": [str(row.get("source_hash") or "") for row in adjacent_rows],
            "route_profiles": [],
            "selected_evidence_item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
            "validation_gates": ["local_agent_harness_eval_required_before_implementation_route"],
            "validation_target": "general_agent_projects_without_skill_workflow_stay_eval_only",
            "replay_command_hash": _stable_hash(
                "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
            ),
            "status": "ready" if adjacent_rows and not adjacent_blockers else "blocked",
            "activation_blockers": adjacent_blockers,
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        },
    ]

    blocked_proposal_ids = [
        str(row["proposal_id"])
        for row in proposal_rows
        if row["status"] != "ready"
    ]
    ready = bool(proposal_rows) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_pass3_active_window_review_packet",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_window_pass3_routes_ready_for_supervisor_review"
            if ready
            else "repair_active_window_pass3_routes_before_final_pass"
        ),
        "source_digest": source_digest or "github-growth-20260627T222729.506372Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-matrix",
            "p2-skill-route-documentation",
            "p3-agent-harness-eval-fixtures",
        ],
        "ready_proposal_count": len(proposal_rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(skill_rows),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": sorted(dict.fromkeys(route_profiles)),
        "missing_route_profiles": missing_profiles,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": ["test", "documentation"],
        "adjacent_evaluation_lane": "agent_harness_eval_required",
        "unsupported_lane_names_removed": sorted(dict.fromkeys(unsupported_lane_names)),
        "required_evidence": [
            "generic_game_and_ecosystem_skill_workflow_shapes",
            "adjacent_general_agent_item_without_skill_workflow_signal",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
        ],
        "operator_next_action": (
            "run_hashed_replay_commands_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_active_window_review_packet"
        ),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": proposal_rows,
        "skill_route_rows": skill_rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_pass3_active_proposal_acceptance_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Expose the current active skill-route proposals as local acceptance lanes."""

    profile_proposals: Mapping[str, Mapping[str, str]] = {
        "generic_skill_workflow": {
            "proposal_id": "p1-skill-route-discovery-generic",
            "proposal_kind": "test",
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_fixture_preserves_bounded_lanes",
        },
        "source_cited_domain_research": {
            "proposal_id": "p1-skill-route-discovery-generic",
            "proposal_kind": "test",
            "selected_local_lane": "test",
            "validation_target": "source_cited_skill_workflow_fixture_preserves_advice_boundaries",
        },
        "game_frontend_workflow": {
            "proposal_id": "p2-game-frontend-skill-workflow",
            "proposal_kind": "documentation",
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_workflow_profile_requires_local_frontend_validation",
        },
        "skill_ecosystem_state_handoff": {
            "proposal_id": "p3-skill-ecosystem-state-handoff",
            "proposal_kind": "config",
            "selected_local_lane": "config",
            "validation_target": "skill_ecosystem_state_handoff_preserves_profile_memory_boundaries",
        },
    }
    required_proposal_ids = (
        "p1-skill-route-discovery-generic",
        "p2-game-frontend-skill-workflow",
        "p3-skill-ecosystem-state-handoff",
    )
    allowed_profile_names = set(profile_proposals)

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    blocked_rows: list[str] = []
    unsupported_lane_names: list[str] = []

    for candidate in sorted(
        candidate_lane_inventory,
        key=lambda item: str(item.get("candidate_name") or "").casefold(),
    ):
        candidate_name = str(candidate.get("candidate_name") or "")
        route_profiles = [
            profile
            for profile in (_string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"])
            if profile in allowed_profile_names
        ]
        if not route_profiles:
            continue

        allowed_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        evidence_item_ids = _string_list(candidate.get("evidence_item_ids"))
        validation_gates = _skill_route_discovery_validation_gates(candidate)
        unsupported_lane_names.extend(_string_list(candidate.get("downgraded_lane_names")))

        for route_profile in route_profiles:
            proposal = profile_proposals[route_profile]
            selected_lane = str(proposal["selected_local_lane"])
            row_blockers: list[str] = []
            if str(candidate.get("route_class") or "") != SKILL_ROUTE_DISCOVERY_ROUTE_CLASS:
                row_blockers.append("route_class_mismatch")
            if selected_lane not in allowed_lanes:
                row_blockers.append("selected_local_lane_not_available")
            if not allowed_lanes:
                row_blockers.append("bounded_local_lanes_missing")
            if not evidence_item_ids:
                row_blockers.append("selected_item_ids_or_frozen_fixture_missing")
            if not validation_gates:
                row_blockers.append("validation_gate_missing")
            if candidate.get("local_validation_required") is not True:
                row_blockers.append("local_validation_not_required")
            if str(candidate.get("runtime_action") or "none") != "none":
                row_blockers.append("runtime_action_requested")
            if candidate.get("external_skill_activation_allowed") is not False:
                row_blockers.append("external_skill_activation_not_denied")

            if row_blockers:
                blocked_rows.append(f"{candidate_name}:{route_profile}")

            observed_profiles.append(route_profile)
            rows.append(
                {
                    "proposal_id": proposal["proposal_id"],
                    "proposal_kind": proposal["proposal_kind"],
                    "candidate_name": candidate_name,
                    "candidate_source_hash": _stable_hash(str(candidate.get("source_url") or candidate_name)),
                    "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                    "route_class": str(candidate.get("route_class") or ""),
                    "route_profile": route_profile,
                    "allowed_local_lanes": allowed_lanes,
                    "selected_local_lane": selected_lane,
                    "queued_local_lanes": [lane for lane in allowed_lanes if lane != selected_lane],
                    "selected_evidence_item_ids": evidence_item_ids,
                    "validation_gates": validation_gates,
                    "validation_target": proposal["validation_target"],
                    "replay_command_hash": _stable_hash(
                        "python -m pytest tests/test_skill_routing.py -q -k "
                        "pass3_active_proposal_acceptance_lane"
                    ),
                    "activation_blockers": row_blockers,
                    "row_status": "ready" if not row_blockers else "blocked",
                    "local_validation_required": True,
                    "runtime_action": "none",
                    "external_skill_activation_allowed": False,
                    "external_harness_execution_allowed": False,
                    "provider_runtime_launch_allowed": False,
                    "remote_execution_allowed": False,
                    "profile_write_allowed": False,
                    "memory_write_allowed": False,
                    "raw_replay_command_exported": False,
                    "raw_source_url_exported": False,
                    "raw_evidence_urls_exported": False,
                    "raw_target_paths_exported": False,
                    "raw_upstream_body_exported": False,
                }
            )

    proposal_ids_with_rows = {str(row["proposal_id"]) for row in rows}
    missing_proposals = [
        proposal_id
        for proposal_id in required_proposal_ids
        if proposal_id not in proposal_ids_with_rows
    ]
    blocked_proposal_ids = sorted(
        {
            str(row["proposal_id"])
            for row in rows
            if row["row_status"] != "ready"
        }
        | set(missing_proposals)
    )
    ready = bool(rows) and not blocked_rows and not missing_proposals
    return {
        "controller_surface": "skill_route_discovery_pass3_active_proposal_acceptance_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass3_skill_route_proposals_ready_for_local_acceptance"
            if ready
            else "repair_active_pass3_skill_route_proposals_before_acceptance"
        ),
        "source_digest": source_digest or "github-growth-20260627T234729.527065Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": list(required_proposal_ids),
        "ready_proposal_count": len(required_proposal_ids) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "required_route_profiles": [
            "generic_skill_workflow",
            "game_frontend_workflow",
            "skill_ecosystem_state_handoff",
        ],
        "observed_route_profiles": [
            profile
            for profile in (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane
            for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            if lane in {str(row["selected_local_lane"]) for row in rows}
        ],
        "unsupported_lane_names_removed": sorted(dict.fromkeys(unsupported_lane_names)),
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_next_action": (
            "run_hashed_replay_commands_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_pass3_active_proposal_acceptance_lane"
        ),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass4_local_lane_validation(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Close the skill-route slice with bounded local validation lanes.

    This packet is the final-pass operator view for skill-route evidence. It
    confirms the active skill workflow profiles can become only local
    documentation, config, test, or code_patch work, while adjacent general
    agent projects without skill workflow signals remain in the separate agent
    harness evaluation queue.
    """

    required_profiles = (
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    )
    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    replay_commands: list[str] = []
    blocked_candidates: list[str] = []

    for candidate in candidate_lane_inventory:
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        if not set(route_profiles).intersection(required_profiles):
            continue

        candidate_name = str(candidate.get("candidate_name") or "")
        source_hash = _stable_hash(str(candidate.get("source_url") or candidate_name))
        allowed_lanes = [
            lane
            for lane in _string_list(candidate.get("proposal_kinds"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        handoff_metadata = candidate.get("handoff_metadata")
        handoff_metadata = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
        selected_lane = str(handoff_metadata.get("selected_local_lane") or "")
        if selected_lane not in allowed_lanes:
            selected_lane = allowed_lanes[0] if allowed_lanes else ""

        validation_gates = _string_list(handoff_metadata.get("validation_gates"))
        validation_target = _skill_route_discovery_validation_target(selected_lane, route_profiles)
        replay_command = _skill_route_discovery_replay_command(selected_lane, route_profiles)
        row_ready = bool(
            selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and allowed_lanes
            and validation_gates
            and candidate.get("local_validation_required") is True
            and str(candidate.get("runtime_action") or "none") == "none"
            and candidate.get("external_skill_activation_allowed") is False
        )
        if not row_ready and candidate_name:
            blocked_candidates.append(candidate_name)

        observed_profiles.extend(route_profiles)
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_lanes.append(selected_lane)
        if replay_command:
            replay_commands.append(replay_command)

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": source_hash,
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": route_profiles,
                "allowed_local_lanes": allowed_lanes,
                "selected_local_lane": selected_lane,
                "queued_local_lanes": [lane for lane in allowed_lanes if lane != selected_lane],
                "selected_evidence_item_ids": _string_list(candidate.get("evidence_item_ids")),
                "validation_gates": validation_gates,
                "validation_target": validation_target,
                "replay_command": replay_command,
                "row_status": "ready" if row_ready else "blocked",
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

    observed_profile_set = set(observed_profiles)
    missing_profiles = [profile for profile in required_profiles if profile not in observed_profile_set]
    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-eval-for-general-agent-projects",
    )
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        and row["runtime_action"] == "none"
        for row in adjacent_rows
    )
    ready = bool(rows) and not blocked_candidates and not missing_profiles and adjacent_ready
    return {
        "controller_surface": "skill_route_discovery_pass4_local_lane_validation",
        "status": "ready" if ready else "blocked",
        "decision": (
            "complete_skill_route_slice_with_bounded_local_lanes"
            if ready
            else "repair_skill_route_pass4_local_lanes_before_completion"
        ),
        "proposal_ids": [
            "proposal-skill-route-discovery-generic-001",
            "proposal-skill-route-discovery-game-frontend-002",
            "proposal-skill-state-handoff-003",
        ],
        "operator_handoff": "external_supervisor_replay_before_activation",
        "capability_slice_complete": ready,
        "required_route_profiles": list(required_profiles),
        "covered_route_profiles": [
            profile for profile in required_profiles if profile in observed_profile_set
        ],
        "missing_route_profiles": missing_profiles,
        "candidate_count": len(rows),
        "ready_candidate_count": len([row for row in rows if row["row_status"] == "ready"]),
        "adjacent_general_agent_count": len(adjacent_rows),
        "blocked_candidate_names": blocked_candidates,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "completion_recovery_workflow": (
            "run_pass4_replay_commands_then_recheck_pass4_local_lane_validation"
            if ready
            else "repair_blocked_rows_then_rerun_pass4_local_lane_validation"
        ),
        "activation_boundary": (
            "supervisor_may_review_local_diff_after_replay; "
            "kernel_does_not_restart_or_activate_external_skills"
        ),
        "general_agent_project_policy": {
            "proposal_id": "p4-p5-agent-harness-eval-queue",
            "when": "general_agent_project_without_skill_workflow_signal",
            "evaluation_lane": "agent_harness_eval_required",
            "allowed_local_lanes": ["documentation", "test", "code_patch"] if adjacent_rows else [],
            "direct_local_change_proposals_allowed": False,
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "replay_command": "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_upstream_body_exported": False,
        },
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
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_adjacent_general_agent_rows(
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    proposal_id: str,
) -> list[dict[str, Any]]:
    """Represent non-skill general-agent evidence as eval-only adjacent rows."""

    return [
        {
            "proposal_id": proposal_id,
            "item_id": str(item.get("item_id") or ""),
            "item_kind": str(item.get("item_kind") or ""),
            "name": str(item.get("name") or ""),
            "source_hash": str(item.get("source_hash") or ""),
            "ignored_reason": str(item.get("ignored_reason") or ""),
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes": ["documentation", "test", "code_patch"],
            "direct_runtime_route_allowed": False,
            "direct_code_patch_route_allowed": False,
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "replay_command": "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        for item in ignored_evidence_items
    ]


def _skill_route_discovery_pass4_completion_handoff(
    pass4_local_lane_validation: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the final skill-route supervisor handoff without activating it."""

    raw_rows = pass4_local_lane_validation.get("rows")
    pass4_rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    route_profiles: list[str] = []
    replay_command_hashes: list[str] = []
    blocked_candidate_names: list[str] = []

    for raw_row in pass4_rows:
        if not isinstance(raw_row, Mapping):
            continue
        candidate_name = str(raw_row.get("candidate_name") or "")
        selected_lane = str(raw_row.get("selected_local_lane") or "")
        candidate_profiles = _string_list(raw_row.get("route_profiles"))
        replay_command = str(raw_row.get("replay_command") or "")
        row_ready = (
            raw_row.get("row_status") == "ready"
            and selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and raw_row.get("local_validation_required") is True
            and str(raw_row.get("runtime_action") or "none") == "none"
            and raw_row.get("external_skill_activation_allowed") is False
            and raw_row.get("external_harness_execution_allowed") is False
            and raw_row.get("provider_runtime_launch_allowed") is False
            and raw_row.get("remote_execution_allowed") is False
        )
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_lanes.append(selected_lane)
        route_profiles.extend(candidate_profiles)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))
        if not row_ready and candidate_name:
            blocked_candidate_names.append(candidate_name)

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": str(raw_row.get("candidate_source_hash") or ""),
                "route_profiles": candidate_profiles,
                "selected_local_lane": selected_lane,
                "selected_evidence_item_ids": _string_list(raw_row.get("selected_evidence_item_ids")),
                "validation_target": str(raw_row.get("validation_target") or ""),
                "replay_command_hash": _stable_hash(replay_command) if replay_command else "",
                "inspection_requirements": [
                    "selected_digest_item_ids_or_frozen_fixture",
                    "body_free_repository_summary",
                    "changed_file_review_against_selected_lane",
                    "focused_local_validation_result",
                    "rollback_artifact_and_ref",
                    "review_note_for_uncertainty_or_blockers",
                ],
                "row_status": "ready" if row_ready else "blocked",
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

    general_policy = pass4_local_lane_validation.get("general_agent_project_policy")
    general_policy = general_policy if isinstance(general_policy, Mapping) else {}
    raw_adjacent_rows = pass4_local_lane_validation.get("adjacent_general_agent_rows")
    adjacent_rows = (
        raw_adjacent_rows
        if isinstance(raw_adjacent_rows, Sequence) and not isinstance(raw_adjacent_rows, (str, bytes))
        else []
    )
    adjacent_general_agent_rows = [
        {
            "proposal_id": str(row.get("proposal_id") or ""),
            "item_id": str(row.get("item_id") or ""),
            "item_kind": str(row.get("item_kind") or ""),
            "name": str(row.get("name") or ""),
            "source_hash": str(row.get("source_hash") or ""),
            "ignored_reason": str(row.get("ignored_reason") or ""),
            "evaluation_lane": str(row.get("evaluation_lane") or "agent_harness_eval_required"),
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes": _string_list(row.get("allowed_local_lanes")),
            "direct_runtime_route_allowed": False,
            "direct_code_patch_route_allowed": False,
            "required_before_implementation": str(
                row.get("required_before_implementation") or "local_agent_harness_eval_route_established"
            ),
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        for row in adjacent_rows
        if isinstance(row, Mapping)
    ]
    pass4_ready = pass4_local_lane_validation.get("status") == "ready"
    rows_ready = bool(rows) and not blocked_candidate_names and all(
        row["row_status"] == "ready" for row in rows
    )
    ready = pass4_ready and rows_ready

    return {
        "controller_surface": "skill_route_discovery_pass4_completion_handoff",
        "status": "ready" if ready else "blocked",
        "decision": (
            "handoff_current_skill_route_window_to_supervisor_replay"
            if ready
            else "repair_pass4_completion_handoff_before_supervisor_replay"
        ),
        "depends_on_controller_surface": "skill_route_discovery_pass4_local_lane_validation",
        "capability_slice_complete": ready,
        "handoff_mode": "external_supervisor_replay_without_kernel_restart",
        "operator_steps": [
            {
                "step": "verify_rollback_ref_and_artifact",
                "status": "required_before_activation",
                "recovery_hint_code": "rollback_contract_missing",
            },
            {
                "step": "run_pass4_replay_commands",
                "status": "required_before_activation",
                "recovery_hint_code": "pass4_replay_not_confirmed",
            },
            {
                "step": "inspect_changed_files_against_selected_lanes",
                "status": "required_before_activation",
                "recovery_hint_code": "lane_artifact_review_missing",
            },
            {
                "step": "confirm_external_activation_boundary",
                "status": "required_before_activation",
                "recovery_hint_code": "external_activation_boundary_weakened",
            },
            {
                "step": "handoff_to_configured_supervisor",
                "status": "after_local_validation",
                "recovery_hint_code": "supervisor_handoff_pending",
            },
        ],
        "candidate_count": len(rows),
        "ready_candidate_count": len([row for row in rows if row["row_status"] == "ready"]),
        "adjacent_general_agent_count": len(adjacent_general_agent_rows),
        "blocked_candidate_names": blocked_candidate_names,
        "covered_route_profiles": sorted(dict.fromkeys(profile for profile in route_profiles if profile)),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
        "rollback_contract": {
            "rollback_ref_required": True,
            "rollback_artifact_required": True,
            "rollback_execution": "explicit_destructive_operator_action_only",
        },
        "adjacent_general_agent_project_boundary": {
            "evaluation_lane": str(general_policy.get("evaluation_lane") or "agent_harness_eval_required"),
            "skill_route_discovery_inherited": False,
            "direct_local_change_proposals_allowed": False,
            "required_before_implementation": str(
                general_policy.get("required_before_implementation")
                or "local_agent_harness_eval_route_established"
            ),
            "allowed_local_lanes_after_eval": _string_list(general_policy.get("allowed_local_lanes")),
            "adjacent_record_count": len(adjacent_general_agent_rows),
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        },
        "activation_boundary": (
            "supervisor_may_review_local_diff_after_replay; "
            "kernel_does_not_restart_or_activate_external_skills"
        ),
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
        "adjacent_general_agent_rows": adjacent_general_agent_rows,
    }


def _skill_route_discovery_pass4_operator_replay_manifest(
    pass4_completion_handoff: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize final-pass replay requirements without exposing raw paths."""

    raw_rows = pass4_completion_handoff.get("rows")
    rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    selected_lanes = [
        lane
        for lane in _string_list(pass4_completion_handoff.get("selected_local_lanes"))
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    lane_artifact_rows = [
        {
            "lane": lane,
            "artifact_target_hashes": [
                _stable_hash(target)
                for target in SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS.get(lane, ())
            ],
            "artifact_target_count": len(SKILL_ROUTE_DISCOVERY_LOCAL_ARTIFACT_TARGETS.get(lane, ())),
            "changed_file_review": "must_match_selected_lane_or_be_recorded_as_review_note",
        }
        for lane in selected_lanes
    ]
    candidate_rows = [
        {
            "candidate_name": str(row.get("candidate_name") or ""),
            "route_profiles": _string_list(row.get("route_profiles")),
            "selected_local_lane": str(row.get("selected_local_lane") or ""),
            "candidate_source_hash": str(row.get("candidate_source_hash") or ""),
            "replay_command_hash": str(row.get("replay_command_hash") or ""),
            "row_status": str(row.get("row_status") or "blocked"),
        }
        for row in rows
        if isinstance(row, Mapping)
    ]
    ready = (
        pass4_completion_handoff.get("status") == "ready"
        and bool(candidate_rows)
        and all(row["row_status"] == "ready" for row in candidate_rows)
        and bool(lane_artifact_rows)
    )
    adjacent_boundary = pass4_completion_handoff.get("adjacent_general_agent_project_boundary")
    adjacent_boundary = adjacent_boundary if isinstance(adjacent_boundary, Mapping) else {}

    return {
        "controller_surface": "skill_route_discovery_pass4_operator_replay_manifest",
        "status": "ready" if ready else "blocked",
        "decision": (
            "supervisor_can_replay_selected_local_lanes_before_activation_review"
            if ready
            else "repair_pass4_replay_manifest_before_supervisor_handoff"
        ),
        "depends_on_controller_surface": "skill_route_discovery_pass4_completion_handoff",
        "handoff_mode": "body_free_operator_replay_manifest",
        "candidate_count": len(candidate_rows),
        "ready_candidate_count": len([row for row in candidate_rows if row["row_status"] == "ready"]),
        "selected_local_lanes": selected_lanes,
        "lane_artifact_targets": lane_artifact_rows,
        "replay_command_hashes": _string_list(pass4_completion_handoff.get("replay_command_hashes")),
        "candidate_rows": candidate_rows,
        "operator_replay_requirements": [
            "confirm_rollback_ref_and_artifact",
            "run_selected_lane_replay_commands_from_pass4_local_lane_validation",
            "compare_changed_files_with_hashed_lane_artifact_targets",
            "record_any_unmatched_file_as_review_note_or_blocker",
            "keep_activation_external_to_the_kernel",
        ],
        "completion_blocker_hints": [
            "rollback_contract_missing",
            "pass4_replay_not_confirmed",
            "lane_artifact_review_missing",
            "external_activation_boundary_weakened",
        ],
        "adjacent_general_agent_project_boundary": {
            "evaluation_lane": str(adjacent_boundary.get("evaluation_lane") or "agent_harness_eval_required"),
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes_after_eval": _string_list(
                adjacent_boundary.get("allowed_local_lanes_after_eval")
            ),
            "adjacent_record_count": int(adjacent_boundary.get("adjacent_record_count") or 0),
            "required_before_implementation": str(
                adjacent_boundary.get("required_before_implementation")
                or "local_agent_harness_eval_route_established"
            ),
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        },
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
        "raw_replay_command_exported": False,
    }


def _skill_route_discovery_active_pass4_completion_matrix(
    pass4_completion_handoff: Mapping[str, Any],
    pass4_operator_replay_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind this wake's final proposal IDs to validated bounded lanes."""

    proposal_specs = (
        {
            "proposal_id": "proposal_skill_route_discovery_inventory_001",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_discovery_inventory",
            "route_profiles": (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "skill_route_discovery_note_references_only_local_lanes",
        },
        {
            "proposal_id": "proposal_skill_route_discovery_tests_002",
            "proposal_kind": "test",
            "proposal_track": "skill_route_discovery_classification_tests",
            "route_profiles": (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "skill_route_discovery_classification_fixture_replay",
        },
        {
            "proposal_id": "proposal_game_skill_profile_route_003",
            "proposal_kind": "config",
            "proposal_track": "game_frontend_workflow_profile",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "config",
            "validation_target": "game_frontend_workflow_profile_stays_bounded",
        },
    )

    raw_rows = pass4_completion_handoff.get("rows")
    handoff_rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    replay_ready = pass4_operator_replay_manifest.get("status") == "ready"
    handoff_ready = pass4_completion_handoff.get("status") == "ready"
    rows: list[dict[str, Any]] = []
    blocked_proposal_ids: list[str] = []
    observed_selected_lanes: list[str] = []

    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        observed_profiles: list[str] = []
        observed_lanes: list[str] = []
        replay_command_hashes: list[str] = []

        for handoff_row in handoff_rows:
            if not isinstance(handoff_row, Mapping):
                continue
            row_profiles = _string_list(handoff_row.get("route_profiles"))
            if not required_profiles.intersection(row_profiles):
                continue
            candidate_name = str(handoff_row.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hash = str(handoff_row.get("candidate_source_hash") or "")
            if candidate_source_hash:
                candidate_source_hashes.append(candidate_source_hash)
            selected_evidence_item_ids.extend(_string_list(handoff_row.get("selected_evidence_item_ids")))
            observed_profiles.extend(row_profiles)
            selected_row_lane = str(handoff_row.get("selected_local_lane") or "")
            if selected_row_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
                observed_lanes.append(selected_row_lane)
            replay_hash = str(handoff_row.get("replay_command_hash") or "")
            if replay_hash:
                replay_command_hashes.append(replay_hash)

        selected_lane = str(spec["selected_local_lane"])
        allowed_local_lanes = list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        profile_covered = required_profiles.issubset(set(observed_profiles))
        row_ready = bool(
            handoff_ready
            and replay_ready
            and candidate_names
            and profile_covered
            and selected_lane in allowed_local_lanes
            and selected_evidence_item_ids
            and replay_command_hashes
        )
        if row_ready:
            observed_selected_lanes.append(selected_lane)
        else:
            blocked_proposal_ids.append(str(spec["proposal_id"]))

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if row_ready else "blocked",
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile for profile in spec["route_profiles"] if profile in set(observed_profiles)
                ],
                "required_route_profiles": list(spec["route_profiles"]),
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_lane if selected_lane in allowed_local_lanes else "",
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gate": "focused-evidence-review",
                "validation_target": spec["validation_target"],
                "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
                "activation_blockers": []
                if row_ready
                else _skill_route_discovery_active_pass4_completion_blockers(
                    handoff_ready=handoff_ready,
                    replay_ready=replay_ready,
                    candidate_names=candidate_names,
                    profile_covered=profile_covered,
                    selected_lane=selected_lane,
                    selected_evidence_item_ids=selected_evidence_item_ids,
                    replay_command_hashes=replay_command_hashes,
                ),
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_commands_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_boundary = pass4_completion_handoff.get("adjacent_general_agent_project_boundary")
    adjacent_boundary = adjacent_boundary if isinstance(adjacent_boundary, Mapping) else {}
    ready = bool(rows) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_active_pass4_completion_matrix",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass4_skill_route_proposals_ready_for_supervisor_replay"
            if ready
            else "repair_active_pass4_skill_route_proposals_before_completion"
        ),
        "depends_on_controller_surfaces": [
            "skill_route_discovery_pass4_completion_handoff",
            "skill_route_discovery_pass4_operator_replay_manifest",
        ],
        "source_digest": "github-growth-20260627T224729.532285Z",
        "capability_pass": 4,
        "total_passes": 4,
        "capability_slice_complete": ready,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(observed_selected_lanes)
        ],
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "controller_recomputed_gates",
            "review_note",
        ],
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "adjacent_general_agent_project_boundary": {
            "evaluation_lane": str(adjacent_boundary.get("evaluation_lane") or "agent_harness_eval_required"),
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes_after_eval": _string_list(
                adjacent_boundary.get("allowed_local_lanes_after_eval")
            ),
            "adjacent_record_count": int(adjacent_boundary.get("adjacent_record_count") or 0),
            "required_before_implementation": str(
                adjacent_boundary.get("required_before_implementation")
                or "local_agent_harness_eval_route_established"
            ),
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        },
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "remote_execution_allowed": False,
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_active_pass4_completion_blockers(
    *,
    handoff_ready: bool,
    replay_ready: bool,
    candidate_names: Sequence[str],
    profile_covered: bool,
    selected_lane: str,
    selected_evidence_item_ids: Sequence[str],
    replay_command_hashes: Sequence[str],
) -> list[str]:
    blockers: list[str] = []
    if not handoff_ready:
        blockers.append("pass4_completion_handoff_not_ready")
    if not replay_ready:
        blockers.append("pass4_operator_replay_manifest_not_ready")
    if not candidate_names:
        blockers.append("missing_candidate_evidence")
    if not profile_covered:
        blockers.append("missing_required_route_profile")
    if selected_lane not in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
        blockers.append("selected_lane_not_bounded")
    if not selected_evidence_item_ids:
        blockers.append("missing_selected_evidence_item_ids")
    if not replay_command_hashes:
        blockers.append("missing_replay_command_hash")
    return blockers


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


def _skill_route_discovery_pass1_validation_matrix(
    local_activation_targets: Mapping[str, Any],
) -> dict[str, Any]:
    """Flatten pass-1 activation targets into a replayable lane matrix."""

    raw_rows = local_activation_targets.get("rows")
    target_rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    rows: list[dict[str, Any]] = []
    blocked_candidate_names: list[str] = []
    selected_lanes: list[str] = []
    queued_lanes: list[str] = []
    replay_commands: list[str] = []

    for raw_row in target_rows:
        if not isinstance(raw_row, Mapping):
            continue
        candidate_name = str(raw_row.get("candidate_name") or "")
        selected_lane = str(raw_row.get("selected_local_lane") or "")
        queued_local_lanes = [
            lane
            for lane in _string_list(raw_row.get("queued_local_lanes"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        route_profiles = _string_list(raw_row.get("route_profiles")) or ["generic_skill_workflow"]
        replay_command = str(raw_row.get("replay_command") or "")
        promotion_proof = raw_row.get("promotion_proof")
        promotion_proof = promotion_proof if isinstance(promotion_proof, Mapping) else {}
        activation_ready = raw_row.get("activation_ready") is True
        activation_blockers = _string_list(raw_row.get("activation_blockers"))

        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_lanes.append(selected_lane)
        queued_lanes.extend(queued_local_lanes)
        if replay_command:
            replay_commands.append(replay_command)
        if not activation_ready and candidate_name:
            blocked_candidate_names.append(candidate_name)

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": str(raw_row.get("candidate_source_hash") or ""),
                "route_profiles": route_profiles,
                "selected_local_lane": selected_lane,
                "queued_local_lanes": queued_local_lanes,
                "validation_gates": _string_list(raw_row.get("validation_gates")),
                "validation_target": str(raw_row.get("validation_target") or ""),
                "replay_command": replay_command,
                "promotion_proof": dict(promotion_proof),
                "selected_evidence_item_ids": _string_list(raw_row.get("selected_evidence_item_ids")),
                "first_route_required": raw_row.get("first_route_required") is True,
                "first_route_confirmed": raw_row.get("first_route_confirmed") is True,
                "activation_ready": activation_ready,
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
        )

    ready = bool(rows) and not blocked_candidate_names
    return {
        "controller_surface": "skill_route_discovery_pass1_validation_matrix",
        "status": "ready" if ready else "blocked",
        "decision": (
            "replay_pass1_bounded_lanes_before_activation"
            if ready
            else "repair_pass1_bounded_lanes_before_activation"
        ),
        "row_count": len(rows),
        "ready_row_count": len([row for row in rows if row["activation_ready"] is True]),
        "blocked_row_count": len([row for row in rows if row["activation_ready"] is not True]),
        "blocked_candidate_names": blocked_candidate_names,
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "queued_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(queued_lanes)
        ],
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "rollback_artifact",
            "focused_local_validation",
            "changed_file_review",
            "review_note",
        ],
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


def _skill_route_discovery_pass2_validation_handoff(
    local_activation_targets: Mapping[str, Any],
    route_profile_handoff_queue: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose pass-2 profile lanes as a bounded operator validation handoff."""

    raw_rows = local_activation_targets.get("rows")
    target_rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    rows: list[dict[str, Any]] = []
    blocked_candidate_names: list[str] = []
    selected_lanes: list[str] = []
    validation_targets: list[str] = []
    replay_commands: list[str] = []
    route_profiles: list[str] = []

    ordered_target_rows = sorted(
        (row for row in target_rows if isinstance(row, Mapping)),
        key=_skill_route_discovery_pass2_handoff_sort_key,
    )
    for raw_row in ordered_target_rows:
        if not isinstance(raw_row, Mapping):
            continue
        candidate_name = str(raw_row.get("candidate_name") or "")
        selected_lane = str(raw_row.get("selected_local_lane") or "")
        candidate_profiles = _string_list(raw_row.get("route_profiles")) or ["generic_skill_workflow"]
        queued_local_lanes = [
            lane
            for lane in _string_list(raw_row.get("queued_local_lanes"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        validation_target = str(raw_row.get("validation_target") or "")
        replay_command = str(raw_row.get("replay_command") or "")
        activation_ready = raw_row.get("activation_ready") is True
        activation_blockers = _string_list(raw_row.get("activation_blockers"))

        route_profiles.extend(candidate_profiles)
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_lanes.append(selected_lane)
        if validation_target:
            validation_targets.append(validation_target)
        if replay_command:
            replay_commands.append(replay_command)
        if not activation_ready and candidate_name:
            blocked_candidate_names.append(candidate_name)

        rows.append(
            {
                "candidate_name": candidate_name,
                "candidate_source_hash": str(raw_row.get("candidate_source_hash") or ""),
                "route_profiles": candidate_profiles,
                "primary_route": SKILL_ROUTE_DISCOVERY_HINT,
                "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
                "selected_local_lane": selected_lane,
                "queued_local_lanes": queued_local_lanes,
                "validation_target": validation_target,
                "replay_command": replay_command,
                "validation_gates": _string_list(raw_row.get("validation_gates")),
                "selected_evidence_item_ids": _string_list(raw_row.get("selected_evidence_item_ids")),
                "activation_ready": activation_ready,
                "activation_blockers": activation_blockers,
                "skill_route_discovery_inherited": True,
                "agent_harness_eval_required": False,
                "agent_harness_eval_allowed_after": "local_skill_route_validation",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    queue_rows = route_profile_handoff_queue.get("rows")
    queue_rows = queue_rows if isinstance(queue_rows, Sequence) and not isinstance(queue_rows, (str, bytes)) else []
    profile_queue_ready = route_profile_handoff_queue.get("status") == "ready"
    rows_ready = bool(rows) and not blocked_candidate_names and all(
        row["selected_local_lane"] in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        and row["activation_ready"] is True
        and row["runtime_action"] == "none"
        and row["external_skill_activation_allowed"] is False
        for row in rows
    )
    ready = rows_ready and profile_queue_ready

    return {
        "controller_surface": "skill_route_discovery_pass2_validation_handoff",
        "status": "ready" if ready else "blocked",
        "decision": (
            "handoff_pass2_profiles_to_bounded_local_validation"
            if ready
            else "repair_pass2_profile_lanes_before_validation_handoff"
        ),
        "candidate_count": len(rows),
        "route_profile_count": len(set(route_profiles)),
        "ready_candidate_count": len([row for row in rows if row["activation_ready"] is True]),
        "blocked_candidate_count": len([row for row in rows if row["activation_ready"] is not True]),
        "blocked_candidate_names": blocked_candidate_names,
        "observed_route_profiles": sorted(
            dict.fromkeys(profile for profile in route_profiles if profile)
        ),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "validation_targets": list(dict.fromkeys(validation_targets)),
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "profile_handoff_queue_status": str(route_profile_handoff_queue.get("status") or ""),
        "profile_handoff_queue_count": len([row for row in queue_rows if isinstance(row, Mapping)]),
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "rollback_artifact",
            "focused_local_validation",
            "changed_file_review",
            "review_note",
        ],
        "adjacent_general_agent_policy": {
            "primary_route": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes": ["documentation", "test", "code_patch"],
            "required_before_implementation": "local_agent_harness_eval",
            "replay_command": "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_upstream_body_exported": False,
        },
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_growth_route_summary_artifact(
    pass2_fixture_validation_lane: Mapping[str, Any],
    pass2_profile_lane_handoff: Mapping[str, Any],
    pass2_validation_handoff: Mapping[str, Any],
    downgraded_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize pass-2 skill-route growth without exporting executable inputs."""

    raw_handoff_rows = pass2_profile_lane_handoff.get("rows")
    handoff_rows = (
        raw_handoff_rows
        if isinstance(raw_handoff_rows, Sequence) and not isinstance(raw_handoff_rows, (str, bytes))
        else []
    )
    downgraded_lane_names: list[str] = []
    for candidate in downgraded_candidates:
        if not isinstance(candidate, Mapping):
            continue
        downgraded_lane_names.extend(_string_list(candidate.get("rejected_lanes")))

    rows: list[dict[str, Any]] = []
    observed_route_profiles: list[str] = []
    selected_local_lanes: list[str] = []
    selected_evidence_item_ids: list[str] = []
    validation_targets: list[str] = []
    replay_command_hashes: list[str] = []
    blocked_proposal_ids: list[str] = []

    for raw_row in handoff_rows:
        if not isinstance(raw_row, Mapping):
            continue
        proposal_id = str(raw_row.get("proposal_id") or "")
        route_profiles = _string_list(raw_row.get("route_profiles"))
        selected_lane = str(raw_row.get("selected_local_lane") or "")
        validation_target = str(raw_row.get("validation_target") or "")
        replay_command = str(raw_row.get("replay_command") or "")
        activation_blockers = _string_list(raw_row.get("activation_blockers"))
        row_status = str(raw_row.get("status") or "")

        observed_route_profiles.extend(route_profiles)
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_local_lanes.append(selected_lane)
        selected_evidence_item_ids.extend(_string_list(raw_row.get("selected_evidence_item_ids")))
        if validation_target:
            validation_targets.append(validation_target)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))
        if row_status != "ready" and proposal_id:
            blocked_proposal_ids.append(proposal_id)

        rows.append(
            {
                "proposal_id": proposal_id,
                "status": "ready" if row_status == "ready" and not activation_blockers else "blocked",
                "route_profiles": route_profiles,
                "selected_local_lane": selected_lane,
                "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
                "validation_target": validation_target,
                "validation_gates": _string_list(raw_row.get("validation_gates")),
                "candidate_source_hashes": _string_list(raw_row.get("candidate_source_hashes")),
                "selected_evidence_item_ids": _string_list(raw_row.get("selected_evidence_item_ids")),
                "replay_command_hash": _stable_hash(replay_command) if replay_command else "",
                "activation_blockers": activation_blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
                "raw_replay_command_exported": False,
            }
        )

    ready = (
        bool(rows)
        and not blocked_proposal_ids
        and pass2_fixture_validation_lane.get("status") == "ready"
        and pass2_profile_lane_handoff.get("status") == "ready"
        and pass2_validation_handoff.get("status") == "ready"
        and all(row["status"] == "ready" for row in rows)
    )

    return {
        "controller_surface": "skill_route_discovery_growth_route_summary_artifact",
        "status": "ready" if ready else "blocked",
        "decision": (
            "summarize_pass2_skill_routes_for_operator_review"
            if ready
            else "repair_pass2_skill_route_surfaces_before_summary_handoff"
        ),
        "capability_pass": 2,
        "review_gate": "focused-evidence-review",
        "artifact_contract": "body_free_hash_only_growth_route_summary",
        "candidate_count": int(pass2_fixture_validation_lane.get("candidate_count") or 0),
        "proposal_count": len(rows),
        "ready_proposal_count": len([row for row in rows if row["status"] == "ready"]),
        "blocked_proposal_ids": blocked_proposal_ids,
        "observed_route_profiles": sorted(dict.fromkeys(observed_route_profiles)),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_local_lanes)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "downgraded_lane_names": sorted(dict.fromkeys(downgraded_lane_names)),
        "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
        "validation_targets": list(dict.fromkeys(validation_targets)),
        "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
        "source_surface_statuses": {
            "pass2_fixture_validation_lane": str(pass2_fixture_validation_lane.get("status") or ""),
            "pass2_profile_lane_handoff": str(pass2_profile_lane_handoff.get("status") or ""),
            "pass2_validation_handoff": str(pass2_validation_handoff.get("status") or ""),
        },
        "required_evidence": [
            "route_classification_fixture",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
            "changed_file_review",
            "review_note",
        ],
        "operator_handoff": "external_supervisor_review_before_activation",
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "raw_replay_commands_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_pass2_handoff_sort_key(row: Mapping[str, Any]) -> tuple[int, str]:
    profiles = set(_string_list(row.get("route_profiles")))
    if "codex_workflow_gate" in profiles:
        rank = 0
    elif "skill_ecosystem_state_handoff" in profiles:
        rank = 1
    elif "source_cited_domain_research" in profiles:
        rank = 2
    elif "game_frontend_workflow" in profiles:
        rank = 3
    else:
        rank = 4
    return (rank, str(row.get("candidate_name") or "").casefold())


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


def _skill_route_discovery_completion_workflow(
    local_activation_targets: Mapping[str, Any],
    adoption_manifest: Mapping[str, Any],
    privacy_review_panel: Mapping[str, Any],
    route_profile_handoff_queue: Mapping[str, Any],
) -> dict[str, Any]:
    """Render a rollback-aware operator workflow for completing local lanes."""

    raw_target_rows = local_activation_targets.get("rows")
    target_rows = (
        raw_target_rows
        if isinstance(raw_target_rows, Sequence) and not isinstance(raw_target_rows, (str, bytes))
        else []
    )
    rows = [row for row in target_rows if isinstance(row, Mapping)]
    ready_rows = [row for row in rows if row.get("activation_ready") is True]
    blocked_rows = [row for row in rows if row.get("activation_ready") is not True]
    replay_commands = [
        str(row.get("replay_command") or "")
        for row in ready_rows
        if str(row.get("replay_command") or "").strip()
    ]
    validation_targets = [
        str(row.get("validation_target") or "")
        for row in ready_rows
        if str(row.get("validation_target") or "").strip()
    ]
    selected_lanes = [
        str(row.get("selected_local_lane") or "")
        for row in ready_rows
        if str(row.get("selected_local_lane") or "") in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    blocked_candidate_names = [
        str(row.get("candidate_name") or "")
        for row in blocked_rows
        if str(row.get("candidate_name") or "").strip()
    ]
    promotion_readiness = adoption_manifest.get("promotion_readiness")
    promotion_readiness = promotion_readiness if isinstance(promotion_readiness, Mapping) else {}

    targets_ready = local_activation_targets.get("status") == "ready" and bool(ready_rows) and not blocked_rows
    manifest_ready = adoption_manifest.get("status") == "ready"
    profile_queue_ready = route_profile_handoff_queue.get("status") == "ready"
    workflow_ready = targets_ready and manifest_ready and profile_queue_ready
    privacy_review_required = privacy_review_panel.get("status") == "review_required"

    return {
        "controller_surface": "skill_route_discovery_completion_workflow",
        "status": "ready" if workflow_ready else "blocked",
        "decision": (
            "complete_bounded_local_validation_then_external_supervisor_handoff"
            if workflow_ready
            else "repair_bounded_skill_route_lanes_before_completion"
        ),
        "candidate_count": len(rows),
        "ready_candidate_count": len(ready_rows),
        "blocked_candidate_count": len(blocked_rows),
        "blocked_candidate_names": blocked_candidate_names,
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "validation_targets": list(dict.fromkeys(validation_targets)),
        "replay_commands": list(dict.fromkeys(replay_commands)),
        "required_evidence": [
            "rollback_ref",
            "rollback_artifact",
            "focused_local_validation",
            "changed_file_review",
            "review_note",
        ],
        "operator_sequence": [
            "confirm_rollback_ref_and_artifact_exist",
            "run_replay_commands_for_selected_local_lanes",
            "review_changed_files_and_privacy_panel",
            "leave_activation_to_external_supervisor",
        ],
        "privacy_review_required": privacy_review_required,
        "privacy_review_gate": str(privacy_review_panel.get("review_gate") or ""),
        "privacy_review_candidate_count": int(privacy_review_panel.get("review_row_count") or 0),
        "promotion_readiness_status": str(promotion_readiness.get("status") or ""),
        "promotion_readiness_decision": str(promotion_readiness.get("decision") or ""),
        "supervisor_handoff": "external_supervisor_only",
        "rollback_ref_required": True,
        "rollback_artifact_required": True,
        "kernel_self_restart_allowed": False,
        "restart_or_remote_activation_required": False,
        "promotion_or_push_performed": False,
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


def _skill_route_discovery_privacy_review_panel(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    rejected_candidates: Sequence[Mapping[str, Any]],
    downgraded_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize privacy-sensitive skill-route evidence without exporting bodies."""

    review_rows: list[dict[str, Any]] = []
    for candidate in candidate_lane_inventory:
        review_reasons = _skill_route_discovery_privacy_review_reasons(candidate)
        if not review_reasons:
            continue
        handoff_metadata = candidate.get("handoff_metadata")
        selected_lane = (
            str(handoff_metadata.get("selected_local_lane") or "")
            if isinstance(handoff_metadata, Mapping)
            else ""
        )
        review_rows.append(
            {
                "candidate_name": str(candidate.get("candidate_name") or ""),
                "candidate_source_hash": _stable_hash(str(candidate.get("source_url") or "")),
                "route_profiles": _string_list(candidate.get("route_profiles")),
                "selected_local_lane": selected_lane,
                "review_reasons": review_reasons,
                "validation_gates": _skill_route_discovery_validation_gates(candidate),
                "review_gate": "privacy-leakage-human-review",
                "review_behavior": "body_free_boundary_review_only",
                "local_validation_required": True,
                "runtime_action": "none",
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "provider_runtime_launch_allowed": False,
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
                "sensitive_value_export_allowed": False,
            }
        )

    return {
        "controller_surface": "skill_route_discovery_privacy_review_panel",
        "status": "review_required" if review_rows else "not_required",
        "decision": (
            "keep_privacy_sensitive_skill_routes_review_only_until_boundary_validated"
            if review_rows
            else "no_privacy_sensitive_skill_route_boundary_detected"
        ),
        "review_gate": "privacy-leakage-human-review",
        "review_only_risk_flags": ["privacy-leakage"],
        "review_row_count": len(review_rows),
        "review_candidate_names": [row["candidate_name"] for row in review_rows],
        "downgraded_candidate_count": len(downgraded_candidates),
        "rejected_candidate_count": len(rejected_candidates),
        "rows": review_rows,
        "local_validation_required": bool(review_rows),
        "runtime_action": "none",
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "provider_runtime_launch_allowed": False,
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "sensitive_value_export_allowed": False,
    }


def _skill_route_discovery_privacy_review_reasons(candidate: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    route_profiles = set(_string_list(candidate.get("route_profiles")))
    if "skill_ecosystem_state_handoff" in route_profiles:
        reasons.append("state_or_profile_boundary")
    if "source_cited_domain_research" in route_profiles:
        reasons.append("advice_or_domain_research_boundary")

    boundary = candidate.get("state_profile_boundary")
    if isinstance(boundary, Mapping) and boundary.get("privacy_boundary_required") is True:
        reasons.append("privacy_boundary_required")
    if isinstance(boundary, Mapping) and (
        boundary.get("profile_write_allowed") is False or boundary.get("memory_write_allowed") is False
    ):
        reasons.append("profile_or_memory_write_denied")

    domain_boundary = candidate.get("domain_research_boundary")
    if isinstance(domain_boundary, Mapping) and domain_boundary.get("private_context_export_allowed") is False:
        reasons.append("private_context_export_denied")
    if isinstance(domain_boundary, Mapping) and domain_boundary.get("provider_runtime_launch_allowed") is False:
        reasons.append("provider_runtime_launch_denied")

    return list(dict.fromkeys(reasons))


def _skill_route_discovery_pass1_proposal_id(route_profiles: Sequence[str]) -> str:
    profile_set = set(route_profiles)
    if "game_frontend_workflow" in profile_set:
        return "p2-game-frontend-skill-profile"
    if "skill_ecosystem_state_handoff" in profile_set:
        return "p1-skill-route-discovery-fixtures"
    if profile_set & {"generic_skill_workflow", "source_cited_domain_research"}:
        return "p1-skill-route-discovery-fixtures"
    return ""


def _skill_route_discovery_validation_gates(candidate: Mapping[str, Any]) -> list[str]:
    contract = candidate.get("route_validation_contract")
    if not isinstance(contract, Mapping):
        return []
    rows = contract.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return list(
        dict.fromkeys(
            str(row.get("validation_gate"))
            for row in rows
            if isinstance(row, Mapping) and str(row.get("validation_gate") or "").strip()
        )
    )


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
        public_activity_signals=tuple(
            dict.fromkeys((*left.public_activity_signals, *right.public_activity_signals))
        ),
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


def _public_activity_signals(value: Mapping[str, Any]) -> tuple[str, ...]:
    """Normalize public popularity or fork metadata without preserving counts."""

    explicit = _string_tuple(
        value.get("public_activity_signals")
        or value.get("activity_signals")
        or value.get("repository_activity_signals")
    )
    signals = list(explicit)
    for field_name, signal_name in (
        ("star_count", "stars_present"),
        ("stars", "stars_present"),
        ("fork_count", "forks_present"),
        ("forks", "forks_present"),
        ("forked_from", "fork_lineage_present"),
        ("upstream_source_url", "fork_lineage_present"),
        ("watcher_count", "watchers_present"),
        ("watchers", "watchers_present"),
    ):
        raw_value = value.get(field_name)
        if raw_value in (None, "", [], ()):
            continue
        signals.append(signal_name)
    return tuple(dict.fromkeys(signals))


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


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


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
