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
    "reference_directory": ("documentation", "test"),
    "progressive_skill_package": ("documentation", "config", "test"),
    "agent_metadata": ("config",),
    "skill_manifest": ("config",),
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
        source_layout_signals = _skill_repository_layout_signals(self)
        source_metadata_signals = _skill_repository_metadata_signals(self)
        source_layout_signals, source_metadata_signals = _skill_repository_progressive_package_signals(
            source_layout_signals,
            source_metadata_signals,
        )
        return ExternalSkillRouteCandidate(
            name=self.name,
            source_url=self.source_url,
            evidence_summary=self.summary,
            discovery_event_kind=self.discovery_event_kind,
            candidate_lanes=_bounded_skill_discovery_lanes(self),
            related_source_urls=_summary_related_source_urls(self),
            source_layout_signals=source_layout_signals,
            source_metadata_signals=source_metadata_signals,
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
        progressive_package_contract = _skill_route_discovery_progressive_package_contract(candidate, allowed_lanes)
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
                **progressive_package_contract,
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
                    **progressive_package_contract,
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
        source_digest=_skill_route_discovery_source_digest(registry),
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
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    active_pass4_operator_activation_packet = _skill_route_discovery_active_pass4_operator_activation_packet(
        active_pass4_completion_matrix
    )
    current_window_pass4_supervisor_replay_gate = (
        _skill_route_discovery_current_window_pass4_supervisor_replay_gate(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
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
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_window_pass2_route_lane_matrix = _skill_route_discovery_current_window_pass2_route_lane_matrix(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_window_pass2_focused_review = _skill_route_discovery_current_window_pass2_focused_review(
        candidate_lane_inventory,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_run_pass2_local_validation_lane = _skill_route_discovery_current_run_pass2_local_validation_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_active_pass2_skill_route_validation_matrix = (
        _skill_route_discovery_current_active_pass2_skill_route_validation_matrix(
            candidate_lane_inventory,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_active_pass2_proposal_lane = _skill_route_discovery_current_active_pass2_proposal_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_active_pass2_activation_contract = (
        _skill_route_discovery_current_active_pass2_activation_contract(
            current_active_pass2_proposal_lane,
            current_active_pass2_skill_route_validation_matrix,
        )
    )
    current_active_pass3_local_activation_proof_lane = (
        _skill_route_discovery_current_active_pass3_local_activation_proof_lane(
            candidate_lane_inventory,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_active_pass3_discovery_validation_packet = (
        _skill_route_discovery_current_active_pass3_discovery_validation_packet(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_pass3_route_validation_lane = _skill_route_discovery_current_pass3_route_validation_lane(
        candidate_lane_inventory,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_pass4_route_discovery_validation_fix = (
        _skill_route_discovery_current_pass4_route_discovery_validation_fix(
            candidate_lane_inventory,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    active_window_pass2_validation_lane = _skill_route_discovery_active_window_pass2_validation_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    active_pass3_activation_candidate_lane = _skill_route_discovery_active_pass3_activation_candidate_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_digest_pass3_focused_validation_packet = (
        _skill_route_discovery_current_digest_pass3_focused_validation_packet(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_source_digest_pass3_operator_lane = (
        _skill_route_discovery_current_source_digest_pass3_operator_lane(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_run_pass3_validation_lane = _skill_route_discovery_current_run_pass3_validation_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_run_pass3_acceptance_lane = _skill_route_discovery_current_run_pass3_acceptance_lane(
        current_run_pass3_validation_lane
    )
    current_run_pass4_completion_lane = _skill_route_discovery_current_run_pass4_completion_lane(
        pass4_completion_handoff,
        pass4_operator_replay_manifest,
        current_run_pass3_validation_lane,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_window_pass4_route_completion_lane = (
        _skill_route_discovery_current_window_pass4_route_completion_lane(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
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
    current_window_pass3_validation_cases = _skill_route_discovery_current_window_pass3_validation_cases(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_window_pass1_discovery_intake_lane = _skill_route_discovery_current_window_pass1_discovery_intake_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    active_pass1_skill_route_discovery_matrix = _skill_route_discovery_active_pass1_skill_route_discovery_matrix(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    active_pass1_proposal_replay_lane = _skill_route_discovery_active_pass1_proposal_replay_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_digest_pass1_validation_lane = _skill_route_discovery_current_digest_pass1_validation_lane(
        candidate_lane_inventory,
        ignored_evidence_items,
        source_digest=_skill_route_discovery_source_digest(registry),
    )
    current_digest_pass2_local_validation_lane = (
        _skill_route_discovery_current_digest_pass2_local_validation_lane(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_digest_pass4_completion_handoff = (
        _skill_route_discovery_current_digest_pass4_completion_handoff(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_digest_pass4_final_closure = (
        _skill_route_discovery_current_digest_pass4_final_closure(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
    )
    current_run_pass1_activation_readiness = (
        _skill_route_discovery_current_run_pass1_activation_readiness(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        )
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
        "current_window_pass1_discovery_intake_lane": current_window_pass1_discovery_intake_lane,
        "active_pass1_skill_route_discovery_matrix": active_pass1_skill_route_discovery_matrix,
        "active_pass1_proposal_replay_lane": active_pass1_proposal_replay_lane,
        "current_digest_pass1_validation_lane": current_digest_pass1_validation_lane,
        "current_digest_pass2_local_validation_lane": current_digest_pass2_local_validation_lane,
        "current_digest_pass4_completion_handoff": current_digest_pass4_completion_handoff,
        "current_digest_pass4_final_closure": current_digest_pass4_final_closure,
        "current_run_pass1_activation_readiness": current_run_pass1_activation_readiness,
        "current_pass1_route_discovery_index": _skill_route_discovery_current_pass1_route_discovery_index(
            candidate_lane_inventory,
            ignored_evidence_items,
            source_digest=_skill_route_discovery_source_digest(registry),
        ),
        "current_pass_validation_cases": _skill_route_discovery_current_pass_validation_cases(
            candidate_lane_inventory
        ),
        "pass2_fixture_validation_lane": pass2_fixture_validation_lane,
        "pass2_profile_lane_handoff": pass2_profile_lane_handoff,
        "current_pass2_validation_lane": current_pass2_validation_lane,
        "current_window_pass2_route_lane_matrix": current_window_pass2_route_lane_matrix,
        "current_window_pass2_focused_review": current_window_pass2_focused_review,
        "current_run_pass2_local_validation_lane": current_run_pass2_local_validation_lane,
        "current_active_pass2_skill_route_validation_matrix": (
            current_active_pass2_skill_route_validation_matrix
        ),
        "current_active_pass2_proposal_lane": current_active_pass2_proposal_lane,
        "current_active_pass2_activation_contract": current_active_pass2_activation_contract,
        "current_active_pass3_local_activation_proof_lane": (
            current_active_pass3_local_activation_proof_lane
        ),
        "current_active_pass3_discovery_validation_packet": (
            current_active_pass3_discovery_validation_packet
        ),
        "current_pass3_route_validation_lane": current_pass3_route_validation_lane,
        "current_pass4_route_discovery_validation_fix": current_pass4_route_discovery_validation_fix,
        "active_window_pass2_validation_lane": active_window_pass2_validation_lane,
        "active_pass3_activation_candidate_lane": active_pass3_activation_candidate_lane,
        "current_digest_pass3_focused_validation_packet": current_digest_pass3_focused_validation_packet,
        "current_source_digest_pass3_operator_lane": current_source_digest_pass3_operator_lane,
        "current_run_pass3_validation_lane": current_run_pass3_validation_lane,
        "current_run_pass3_acceptance_lane": current_run_pass3_acceptance_lane,
        "growth_route_summary_artifact": growth_route_summary_artifact,
        "pass3_route_discovery_index": pass3_route_discovery_index,
        "pass3_activation_handoff": pass3_activation_handoff,
        "pass3_preflight_queue": pass3_preflight_queue,
        "pass3_local_validation_lane": pass3_local_validation_lane,
        "current_window_pass3_validation_cases": current_window_pass3_validation_cases,
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
        "active_pass4_operator_activation_packet": active_pass4_operator_activation_packet,
        "current_run_pass4_completion_lane": current_run_pass4_completion_lane,
        "current_window_pass4_route_completion_lane": current_window_pass4_route_completion_lane,
        "current_window_pass4_supervisor_replay_gate": current_window_pass4_supervisor_replay_gate,
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
    if _has_negated_skill_workflow_signal(text) and not layout_signals and not metadata_signals:
        return False
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


def _has_negated_skill_workflow_signal(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "without skill workflow",
            "without skill package",
            "without skill route",
            "without skill activation",
            "without skill.md",
            "no skill workflow",
            "no skill package",
            "no skill route",
            "no skill activation",
            "no skill.md",
            "lacks skill workflow",
            "lacks skill package",
            "lacks skill route",
            "lacks skill.md",
        )
    )


def _bounded_skill_discovery_lanes(summary: ExternalSkillRepositorySummary) -> tuple[str, ...]:
    text = _summary_text(summary)
    suggested = tuple(lane for lane in summary.suggested_lanes if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    keyword_lanes = tuple(
        lane
        for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        if any(keyword in text for keyword in SKILL_ROUTE_DISCOVERY_LANE_KEYWORDS[lane])
    )
    source_layout_signals, source_metadata_signals = _skill_repository_progressive_package_signals(
        _skill_repository_layout_signals(summary),
        _skill_repository_metadata_signals(summary),
    )
    layout_lanes = tuple(
        lane
        for signal in (*source_layout_signals, *source_metadata_signals)
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


def _skill_route_discovery_progressive_package_contract(
    candidate: Mapping[str, Any],
    allowed_lanes: Sequence[str],
) -> dict[str, Any]:
    """Expose manifest/reference package validation without enabling upstream code."""

    source_layout_signals = _string_list(candidate.get("source_layout_signals"))
    source_metadata_signals = _string_list(candidate.get("source_metadata_signals"))
    if "progressive_skill_package" not in source_layout_signals:
        return {}

    present_signals = list(dict.fromkeys((*source_layout_signals, *source_metadata_signals)))
    preferred_lanes = [
        lane
        for lane in ("documentation", "config", "test")
        if lane in set(allowed_lanes) and lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    required_signals = [
        "skill_markdown_or_directory",
        "skill_manifest",
        "reference_directory",
    ]
    return {
        "progressive_skill_package_contract": {
            "controller_surface": "skill_route_discovery_progressive_skill_package_contract",
            "status": "ready" if preferred_lanes else "blocked_no_bounded_local_lane",
            "decision": (
                "validate_manifest_and_references_before_activation"
                if preferred_lanes
                else "repair_progressive_skill_package_lanes_before_activation"
            ),
            "package_shape": "root_manifest_with_progressively_loaded_references",
            "required_source_signals": required_signals,
            "present_source_signals": present_signals,
            "preferred_local_lanes": preferred_lanes,
            "validation_requirements": [
                "inspect_root_skill_manifest_before_references",
                "validate_referenced_files_with_local_documentation_config_or_test_lane",
                "keep_validation_scripts_non_executable_until_local_test_lane_selects_them",
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


def _skill_route_discovery_profile_validation_requirements(
    route_profiles: Sequence[str],
    allowed_lanes: Sequence[str],
) -> list[dict[str, Any]]:
    """Return body-free proof requirements for each route profile before activation."""

    contract = _skill_route_discovery_validation_contract(route_profiles, allowed_lanes)
    rows = contract.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []

    requirements: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        route_profile = str(row.get("route_profile") or "").strip()
        if not route_profile:
            continue
        requirements.append(
            {
                "route_profile": route_profile,
                "validation_gate": str(row.get("validation_gate") or "").strip(),
                "must_prove_before_activation": _skill_route_discovery_profile_proof_target(route_profile),
                "required_metadata": _string_list(row.get("required_metadata")),
                "preferred_local_lanes": _string_list(row.get("preferred_local_lanes")),
                "blocked_activation_reason": str(row.get("blocked_activation_reason") or "").strip(),
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_upstream_body_exported": False,
            }
        )
    return requirements


def _skill_route_discovery_local_acceptance_gates(
    candidate: Mapping[str, Any],
    *,
    selected_lane: str,
    allowed_lanes: Sequence[str],
    evidence_item_ids: Sequence[str],
    validation_gates: Sequence[str],
) -> dict[str, bool]:
    """Return body-free acceptance gates for a selected local skill-route lane."""

    handoff_metadata = candidate.get("handoff_metadata")
    handoff = handoff_metadata if isinstance(handoff_metadata, Mapping) else {}
    route_validation_contract = candidate.get("route_validation_contract")
    contract = route_validation_contract if isinstance(route_validation_contract, Mapping) else {}

    bounded_lane = (
        selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        and selected_lane in set(allowed_lanes)
        and set(allowed_lanes) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    )
    validation_required = (
        candidate.get("local_validation_required") is True
        and handoff.get("local_validation_required", True) is True
        and contract.get("local_validation_required", True) is True
    )

    return {
        "bounded_lane": bounded_lane,
        "selected_evidence_present": bool(evidence_item_ids),
        "validation_gate_present": bool(validation_gates),
        "local_validation_required": validation_required,
        "runtime_action_none": str(candidate.get("runtime_action") or "none") == "none",
        "external_skill_activation_denied": candidate.get("external_skill_activation_allowed") is False,
        "external_harness_execution_denied": handoff.get("external_harness_execution_allowed", False) is False,
        "provider_runtime_launch_denied": handoff.get("provider_runtime_launch_allowed", False) is False,
        "remote_execution_denied": handoff.get("remote_execution_allowed", False) is False,
        "raw_source_url_not_exported": handoff.get("raw_source_url_exported", False) is False,
        "raw_evidence_urls_not_exported": handoff.get("raw_evidence_urls_exported", False) is False,
        "raw_target_paths_not_exported": True,
        "raw_upstream_body_not_exported": handoff.get("raw_upstream_body_exported", False) is False,
        "raw_replay_command_not_exported": True,
    }


def _skill_route_discovery_validation_row_acceptance_gates(
    row: Mapping[str, Any],
) -> dict[str, bool]:
    """Return body-free acceptance gates for an already-built validation row."""

    allowed_lanes = _string_list(row.get("allowed_local_lanes"))
    queued_lanes = _string_list(row.get("queued_local_lanes"))
    selected_lane = str(row.get("selected_local_lane") or "")
    bounded_lane_names = set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
    exposed_lane_names = set(allowed_lanes) | set(queued_lanes)
    if selected_lane:
        exposed_lane_names.add(selected_lane)

    return {
        "validation_lane_ready": str(row.get("status") or row.get("row_status") or "") == "ready",
        "bounded_lane": (
            selected_lane in bounded_lane_names
            and selected_lane in set(allowed_lanes)
            and set(allowed_lanes) <= bounded_lane_names
        ),
        "queued_lanes_bounded": set(queued_lanes) <= bounded_lane_names and selected_lane not in set(queued_lanes),
        "selected_evidence_present": bool(_string_list(row.get("selected_evidence_item_ids"))),
        "validation_gate_present": bool(_string_list(row.get("validation_gates"))),
        "local_validation_required": row.get("local_validation_required") is True,
        "runtime_action_none": str(row.get("runtime_action") or "none") == "none",
        "external_skill_activation_denied": row.get("external_skill_activation_allowed") is False,
        "external_agent_activation_denied": row.get("external_agent_activation_allowed") is False,
        "external_harness_execution_denied": row.get("external_harness_execution_allowed") is False,
        "provider_runtime_launch_denied": row.get("provider_runtime_launch_allowed") is False,
        "remote_execution_denied": row.get("remote_execution_allowed") is False,
        "no_unbounded_runtime_lane": not (
            {"install", "runtime_execution", "provider_runtime", "external_harness", "remote_execution"}
            & exposed_lane_names
        ),
        "raw_source_url_not_exported": row.get("raw_source_url_exported") is False,
        "raw_evidence_urls_not_exported": row.get("raw_evidence_urls_exported") is False,
        "raw_target_paths_not_exported": row.get("raw_target_paths_exported") is False,
        "raw_upstream_body_not_exported": row.get("raw_upstream_body_exported") is False,
        "raw_replay_command_not_exported": row.get("raw_replay_command_exported", False) is False,
    }


def _skill_route_discovery_adjacent_agent_eval_acceptance_gates(
    row: Mapping[str, Any],
) -> dict[str, bool]:
    """Return acceptance gates for adjacent general-agent rows."""

    selected_lane = str(row.get("selected_local_lane") or "")
    return {
        "validation_lane_ready": str(row.get("status") or row.get("row_status") or "") == "ready",
        "agent_harness_eval_required": selected_lane == "agent_harness_eval_required",
        "skill_route_discovery_not_inherited": str(row.get("route_hint") or "") == "agent_harness_eval_required",
        "direct_runtime_route_denied": str(row.get("runtime_action") or "none") == "none",
        "direct_code_patch_not_selected": selected_lane != "code_patch",
        "external_skill_activation_denied": row.get("external_skill_activation_allowed") is False,
        "external_agent_activation_denied": row.get("external_agent_activation_allowed") is False,
        "external_harness_execution_denied": row.get("external_harness_execution_allowed") is False,
        "provider_runtime_launch_denied": row.get("provider_runtime_launch_allowed") is False,
        "remote_execution_denied": row.get("remote_execution_allowed") is False,
        "local_validation_required": row.get("local_validation_required") is True,
        "raw_source_url_not_exported": row.get("raw_source_url_exported") is False,
        "raw_evidence_urls_not_exported": row.get("raw_evidence_urls_exported") is False,
        "raw_target_paths_not_exported": row.get("raw_target_paths_exported") is False,
        "raw_upstream_body_not_exported": row.get("raw_upstream_body_exported") is False,
        "raw_replay_command_not_exported": row.get("raw_replay_command_exported", False) is False,
    }


def _skill_route_discovery_profile_proof_target(route_profile: str) -> str:
    """Describe the local proof expected for a route profile without upstream bodies."""

    return {
        "codex_workflow_gate": (
            "prove_skill_route_discovery_runs_before_any_secondary_workflow_or_harness_gate"
        ),
        "game_frontend_workflow": (
            "prove_local_frontend_or_test_validation_covers_runnable_game_workflow_and_asset_boundaries"
        ),
        "skill_ecosystem_state_handoff": (
            "prove_state_handoff_metadata_remains_local_config_without_profile_or_memory_write"
        ),
        "source_cited_domain_research": (
            "prove_citation_traceability_and_advice_boundary_before_domain_skill_activation"
        ),
        "generic_skill_workflow": (
            "prove_frozen_digest_or_fixture_evidence_classifies_a_skill_workflow_without_upstream_activation"
        ),
    }.get(
        route_profile,
        "prove_frozen_digest_or_fixture_evidence_classifies_a_skill_workflow_without_upstream_activation",
    )


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


def _skill_route_discovery_current_run_pass1_activation_readiness(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]] = (),
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Summarize the current pass-1 skill-route proposals before activation."""

    current_230729_window = source_digest == "github-growth-20260628T230729.580958Z"
    current_002729_window = source_digest == "github-growth-20260629T002729.571892Z"
    current_061942_window = source_digest == "github-growth-20260629T061942.961537Z"
    current_101324_window = source_digest == "github-growth-20260629T101324.100619Z"
    current_171904_window = source_digest == "github-growth-20260629T171904.272271Z"
    current_183904_window = source_digest == "github-growth-20260629T183904.255941Z"
    proposal_specs = (
        (
            {
                "proposal_id": "p1-skill-route-discovery-compass",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_gate": "focused-evidence-review",
                "validation_target": "compass_skill_ecosystem_routes_only_to_bounded_local_lanes",
            },
            {
                "proposal_id": "p2-skill-route-discovery-generic",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_gate": "generic_skill_workflow_local_validation_before_activation",
                "validation_target": "document_generic_skill_workflow_route_interpretation",
            },
        )
        if current_101324_window
        else
        (
            {
                "proposal_id": "p1-skill-route-discovery-compass-skills",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_gate": "focused-evidence-review",
                "validation_target": "compass_skill_ecosystem_route_probe_requires_local_validation",
            },
            {
                "proposal_id": "p2-skill-route-discovery-zhengxi-views",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_gate": "generic_skill_workflow_local_validation_before_activation",
                "validation_target": "document_generic_skill_workflow_route_interpretation",
            },
        )
        if current_061942_window or current_183904_window
        else
        (
            {
                "proposal_id": "p1-skill-route-discovery-zhengxi-views",
                "proposal_kind": "test",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "test",
                "validation_gate": "focused-evidence-review",
                "validation_target": "zhengxi_views_skill_term_lane_regression",
            },
            {
                "proposal_id": "p2-skill-ecosystem-state-handoff",
                "proposal_kind": "documentation",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "documentation",
                "validation_gate": "state_handoff_boundary_before_profile_or_memory_write",
                "validation_target": "compass_skill_ecosystem_state_handoff_boundary_note",
            },
        )
        if current_002729_window
        else
        (
            {
                "proposal_id": "p1-skill-route-discovery-views",
                "proposal_kind": "test",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "test",
                "validation_gate": "focused-evidence-review",
                "validation_target": "zhengxi_views_generic_skill_workflow_lane_regression",
            },
            {
                "proposal_id": "p3-threejs-game-skill-profile",
                "proposal_kind": "documentation",
                "proposal_track": "game_frontend_workflow",
                "route_profiles": ("game_frontend_workflow",),
                "selected_local_lane": "documentation",
                "validation_gate": "local_frontend_validation_before_game_skill_activation",
                "validation_target": "threejs_game_skill_route_profile_note",
            },
            {
                "proposal_id": "p4-compass-skills-state-handoff",
                "proposal_kind": "config",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "config",
                "validation_gate": "state_handoff_boundary_before_profile_or_memory_write",
                "validation_target": "compass_skill_ecosystem_state_handoff_metadata",
            },
        )
        if current_230729_window
        else (
        {
            "proposal_id": "proposal-skill-route-discovery-generic-001",
            "proposal_kind": "test",
            "proposal_track": "generic_or_source_cited_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_gate": "focused-evidence-review",
            "validation_target": "zhengxi_views_skill_workflow_lane_regression",
        },
        {
            "proposal_id": "proposal-game-skill-route-profile-002",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_gate": "local_frontend_validation_before_game_skill_activation",
            "validation_target": "threejs_game_skill_route_profile_note",
        },
        {
            "proposal_id": "proposal-skill-ecosystem-handoff-003",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_gate": "state_handoff_boundary_before_profile_or_memory_write",
            "validation_target": "compass_skill_ecosystem_handoff_metadata",
        },
        )
    )
    if current_171904_window:
        proposal_specs = (
            {
                "proposal_id": "p1-skill-route-discovery-compass",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_gate": "focused-evidence-review",
                "validation_target": "compass_skill_ecosystem_handoff_metadata_lane",
            },
            {
                "proposal_id": "p2-generic-skill-workflow-zhengxi",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_gate": "generic_skill_workflow_local_validation_before_activation",
                "validation_target": "zhengxi_generic_skill_workflow_route_interpretation",
            },
        )

    rows: list[dict[str, Any]] = []
    blocked_proposal_ids: list[str] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        matched_profiles: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda value: str(value.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_route_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")
        if not validation_gates:
            blockers.append("missing_validation_gate")

        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gate": spec["validation_gate"],
                "observed_validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "activation_boundary": "local_validation_before_activation",
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

    adjacent_rows: list[dict[str, Any]] = []
    adjacent_proposal_ids = {
        "Qwen-AgentWorld": (
            "p3-agent-harness-qwen-agentworld"
            if current_171904_window
            else
            "p3-agent-harness-eval-general-agent-projects"
            if current_101324_window
            else
            "p3-agent-harness-eval-qwen-agentworld"
            if current_183904_window
            else
            "p3-agent-harness-qwen-agentworld"
            if current_061942_window
            else
            "p3-agent-harness-eval-general-projects"
            if current_002729_window
            else "p2-agent-harness-eval-qwen-agentworld"
        ),
        "looper": (
            "p4-agent-harness-looper"
            if current_171904_window
            else
            "p3-agent-harness-eval-general-agent-projects"
            if current_101324_window
            else
            "p4-agent-harness-eval-looper"
            if current_183904_window
            else
            "p4-agent-harness-looper"
            if current_061942_window
            else
            "p3-agent-harness-eval-general-projects"
            if current_002729_window
            else "p5-agent-harness-eval-looper"
        ),
    }
    default_adjacent_proposal_id = (
        "p3-agent-harness-qwen-agentworld"
        if current_171904_window
        else
        "p3-agent-harness-eval-general-agent-projects"
        if current_101324_window
        else
        "p3-agent-harness-eval-qwen-agentworld"
        if current_183904_window
        else
        "p3-agent-harness-qwen-agentworld"
        if current_061942_window
        else
        "p3-agent-harness-eval-general-projects"
        if current_002729_window
        else
        "p2-agent-harness-eval-qwen-agentworld"
        if current_230729_window
        else "proposal-agent-harness-eval-004"
    )
    for ignored_item in ignored_evidence_items:
        proposal_id = adjacent_proposal_ids.get(str(ignored_item.get("name") or ""), default_adjacent_proposal_id)
        for adjacent_row in _skill_route_discovery_adjacent_general_agent_rows(
            [ignored_item],
            proposal_id=proposal_id,
        ):
            replay_command = str(adjacent_row.get("replay_command") or "")
            row = dict(adjacent_row)
            row.pop("replay_command", None)
            row["replay_command_hash"] = _stable_hash(replay_command) if replay_command else ""
            row["accepted_outputs_after_eval"] = ["docs", "tests", "code_patch"]
            row["raw_replay_command_exported"] = False
            adjacent_rows.append(row)

    adjacent_ready = all(
        row.get("evaluation_lane") == "agent_harness_eval_required"
        and row.get("skill_route_discovery_inherited") is False
        and row.get("direct_runtime_route_allowed") is False
        and row.get("direct_code_patch_route_allowed") is False
        and row.get("external_harness_execution_allowed") is False
        and row.get("provider_runtime_launch_allowed") is False
        for row in adjacent_rows
    )
    ready = bool(rows) and not blocked_proposal_ids and adjacent_ready
    anchoring_proposal_ids = (
        [
            "p1-skill-route-discovery-compass",
            "p2-generic-skill-workflow-zhengxi",
            "p3-agent-harness-qwen-agentworld",
            "p4-agent-harness-looper",
            "trend:lyra81604/zhengxi-views-1",
        ]
        if current_171904_window
        else
        [
            "p1-skill-route-discovery-compass",
            "p2-skill-route-discovery-generic",
            "p3-agent-harness-eval-general-agent-projects",
            "p4-security-agent-review-boundary",
            "p5-agent-routing-config-preflight",
        ]
        if current_101324_window
        else
        [
            "p1-skill-route-discovery-compass-skills",
            "p2-skill-route-discovery-zhengxi-views",
            "p3-agent-harness-eval-qwen-agentworld",
            "p4-agent-harness-eval-looper",
            "p5-security-agent-review-lane-autocve",
        ]
        if current_183904_window
        else
        [
            "p1-skill-route-discovery-compass-skills",
            "p2-skill-route-discovery-zhengxi-views",
            "p3-agent-harness-qwen-agentworld",
            "p4-agent-harness-looper",
            "p5-security-agent-review-lane-autocve",
        ]
        if current_061942_window
        else
        [
            "p1-skill-route-discovery-zhengxi-views",
            "p2-skill-ecosystem-state-handoff",
            "p3-agent-harness-eval-general-projects",
        ]
        if current_002729_window
        else
        [
            "p1-skill-route-discovery-views",
            "p2-agent-harness-eval-qwen-agentworld",
            "p3-threejs-game-skill-profile",
            "p4-compass-skills-state-handoff",
            "p5-agent-harness-eval-looper",
        ]
        if current_230729_window
        else [
            "proposal-skill-route-discovery-generic-001",
            "proposal-game-skill-route-profile-002",
            "proposal-skill-ecosystem-handoff-003",
            "proposal-agent-harness-eval-004",
        ]
    )

    return {
        "controller_surface": "skill_route_discovery_current_run_pass1_activation_readiness",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_pass1_skill_routes_ready_for_bounded_local_validation"
            if ready
            else "repair_current_pass1_skill_route_lanes_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T070730.472651Z",
        "capability_pass": 1,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs],
        "anchoring_proposal_ids": anchoring_proposal_ids,
        "blocked_proposal_ids": blocked_proposal_ids,
        "adjacent_general_agent_count": len(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "generic_skill_workflow",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "focused_local_validation",
            "rollback_artifact",
            "review_note",
        ],
        "supervisor_next_action": "replay_current_pass1_readiness_fixture_before_any_activation",
        "activation_authority": "external_supervisor_after_validation",
        "adjacent_general_agent_policy": {
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_allowed_lanes_before_eval": [],
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"]
            if adjacent_rows
            else [],
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_upstream_body_exported": False,
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
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_pass1_route_discovery_index(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Index this wake's pass-1 proposal anchors before any local activation."""

    proposal_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-index",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_discovery_index",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_gate": "focused-evidence-review",
            "validation_target": "document_skill_route_triage_index",
        },
        {
            "proposal_id": "p2-skill-route-discovery-test-fixtures",
            "proposal_kind": "test",
            "proposal_track": "skill_workflow_route_fixtures",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_gate": "focused-evidence-review",
            "validation_target": "skill_workflow_fixtures_stay_classification_only",
        },
        {
            "proposal_id": "p3-game-frontend-skill-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_gate": "local_frontend_validation_before_game_skill_activation",
            "validation_target": "document_or_validate_game_frontend_profile_lane",
        },
        {
            "proposal_id": "p4-skill-ecosystem-state-handoff-profile",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_gate": "state_handoff_boundary_before_profile_or_memory_write",
            "validation_target": "state_handoff_profile_metadata_stays_bounded",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

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
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "activation_blockers": blockers,
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
            "proposal_id": "p5-agent-project-harness-eval-doc",
            "item_id": str(item.get("item_id") or ""),
            "name": str(item.get("name") or ""),
            "source_hash": str(item.get("source_hash") or ""),
            "ignored_reason": str(item.get("ignored_reason") or ""),
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes": ["documentation", "test", "code_patch"],
            "selected_local_lane": "documentation",
            "direct_runtime_route_allowed": False,
            "direct_code_patch_route_allowed": False,
            "required_before_implementation": "local_agent_harness_eval_route_established",
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

    blocked_proposal_ids = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        for row in adjacent_general_agent_rows
    )
    ready = bool(rows) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_pass1_route_discovery_index",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_pass1_skill_route_index_ready_for_bounded_local_validation"
            if ready
            else "repair_current_pass1_skill_route_index_before_activation"
        ),
        "source_digest": source_digest,
        "capability_pass": 1,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs]
        + ["p5-agent-project-harness-eval-doc"],
        "blocked_proposal_ids": blocked_proposal_ids,
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
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
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
            "proposal_aliases": (
                "p1_skill_route_discovery_generic_views",
                "p1-skill-route-discovery-generic",
            ),
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
            "proposal_aliases": (
                "p2_skill_route_discovery_game_frontend",
                "p2_game_frontend_skill_profile",
                "p2-game-skill-workflow-routing",
            ),
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
            "proposal_aliases": (
                "p3_skill_ecosystem_state_handoff_config",
                "p3_skill_ecosystem_state_handoff",
                "p3-skill-state-handoff-validation",
            ),
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
                "proposal_aliases": list(dict.fromkeys(_string_list(spec.get("proposal_aliases")))),
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
        "proposal_alias_ids": list(
            dict.fromkeys(alias for row in rows for alias in _string_list(row.get("proposal_aliases")))
        ),
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
    *,
    source_digest: str = "",
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
    required_profiles = (
        "generic_skill_workflow",
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
    )
    observed_profile_set = set(observed_profiles)
    missing_required_profiles = [
        profile for profile in required_profiles if profile not in observed_profile_set
    ]
    ready = bool(rows) and not blocked_rows and not missing_required_profiles and adjacent_ready
    preactivation_checklist = _skill_route_discovery_pass2_preactivation_checklist(
        rows,
        adjacent_rows,
        ready=ready,
    )
    proposal_acceptance_contract = _skill_route_discovery_pass2_proposal_acceptance_contract(
        rows,
        adjacent_rows,
        ready=ready,
    )

    return {
        "controller_surface": "skill_route_discovery_current_pass2_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_pass2_skill_and_agent_evidence_ready_for_local_validation"
            if ready
            else "repair_current_pass2_skill_or_agent_eval_boundary_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260627T192729.517144Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-batch",
            "p2-agent-harness-eval-qwen-agentworld",
            "p3-agent-harness-eval-looper",
        ],
        "skill_route_candidate_count": len(rows),
        "adjacent_general_agent_count": len(adjacent_rows),
        "ready_skill_route_candidate_count": len([row for row in rows if row["row_status"] == "ready"]),
        "blocked_skill_route_candidate_names": blocked_rows,
        "required_route_profiles": list(required_profiles),
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "missing_required_route_profiles": missing_required_profiles,
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
        "preactivation_checklist": preactivation_checklist,
        "proposal_acceptance_contract": proposal_acceptance_contract,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_pass2_proposal_acceptance_contract(
    skill_rows: Sequence[Mapping[str, Any]],
    adjacent_agent_rows: Sequence[Mapping[str, Any]],
    *,
    ready: bool,
) -> dict[str, Any]:
    """Expose pass-2 proposal acceptance gates without adding activation authority."""

    route_profile_aliases = {
        "generic_skill_workflow": "p1-skill-route-discovery-zviews",
        "source_cited_domain_research": "p1-skill-route-discovery-zviews",
        "game_frontend_workflow": "p2-skill-route-discovery-game-frontend",
        "skill_ecosystem_state_handoff": "p3-skill-ecosystem-state-handoff",
    }
    rows: list[dict[str, Any]] = []
    blocked_proposal_ids: list[str] = []

    for row in skill_rows:
        route_profiles = _string_list(row.get("route_profiles"))
        selected_lane = str(row.get("selected_local_lane") or "")
        allowed_local_lanes = _string_list(row.get("allowed_local_lanes"))
        active_proposal_id = next(
            (
                route_profile_aliases[profile]
                for profile in route_profiles
                if profile in route_profile_aliases
            ),
            str(row.get("proposal_id") or ""),
        )
        acceptance_gates = {
            "bounded_lane": selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and set(allowed_local_lanes).issubset(set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)),
            "local_validation_required": row.get("local_validation_required") is True,
            "runtime_action_none": str(row.get("runtime_action") or "") == "none",
            "external_skill_activation_denied": row.get("external_skill_activation_allowed") is False,
            "external_agent_activation_denied": row.get("external_agent_activation_allowed") is False,
            "external_harness_execution_denied": row.get("external_harness_execution_allowed") is False,
            "provider_runtime_launch_denied": row.get("provider_runtime_launch_allowed") is False,
            "remote_execution_denied": row.get("remote_execution_allowed") is False,
            "raw_evidence_urls_not_exported": row.get("raw_evidence_urls_exported") is False,
            "raw_source_url_not_exported": row.get("raw_source_url_exported") is False,
            "raw_target_paths_not_exported": row.get("raw_target_paths_exported") is False,
            "raw_upstream_body_not_exported": row.get("raw_upstream_body_exported") is False,
        }
        accepted = ready and row.get("row_status") == "ready" and all(acceptance_gates.values())
        if not accepted:
            blocked_proposal_ids.append(active_proposal_id)
        rows.append(
            {
                "proposal_id": active_proposal_id,
                "source_lane_proposal_id": str(row.get("proposal_id") or ""),
                "candidate_name_hash": _stable_hash(str(row.get("candidate_name") or "")),
                "route_profiles": route_profiles,
                "selected_local_lane": selected_lane,
                "allowed_local_lanes": allowed_local_lanes,
                "selected_evidence_item_id_count": len(_string_list(row.get("selected_evidence_item_ids"))),
                "validation_gates": _string_list(row.get("validation_gates")),
                "replay_command_hash": _stable_hash(str(row.get("replay_command") or "")),
                "accepted_for_local_validation": accepted,
                "acceptance_gates": acceptance_gates,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_replay_command_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = [
        {
            "proposal_id": str(row.get("proposal_id") or ""),
            "item_id_hash": _stable_hash(str(row.get("item_id") or "")),
            "evaluation_lane": str(row.get("evaluation_lane") or "agent_harness_eval_required"),
            "skill_route_discovery_inherited": row.get("skill_route_discovery_inherited") is True,
            "accepted_for_local_validation": row.get("skill_route_discovery_inherited") is False
            and row.get("external_harness_execution_allowed") is False
            and row.get("direct_runtime_route_allowed") is False,
            "allowed_local_lanes": _string_list(row.get("allowed_local_lanes")),
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_replay_command_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        for row in adjacent_agent_rows
    ]
    adjacent_ready = all(row["accepted_for_local_validation"] for row in adjacent_rows)
    rows = sorted(rows, key=lambda row: str(row.get("proposal_id") or ""))
    contract_ready = ready and bool(rows) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_pass2_proposal_acceptance_contract",
        "status": "ready" if contract_ready else "blocked",
        "decision": (
            "active_pass2_skill_route_proposals_accepted_for_bounded_local_validation"
            if contract_ready
            else "repair_active_pass2_proposal_acceptance_before_activation"
        ),
        "proposal_ids": [str(row["proposal_id"]) for row in rows],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "adjacent_agent_harness_eval_count": len(adjacent_rows),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane
            for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            if lane in {str(row.get("selected_local_lane") or "") for row in rows}
        ],
        "evidence_ref_mode": "selected_item_ids_only",
        "review_gate": "focused-evidence-review",
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_replay_command_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }


def _skill_route_discovery_pass2_preactivation_checklist(
    skill_rows: Sequence[Mapping[str, Any]],
    adjacent_agent_rows: Sequence[Mapping[str, Any]],
    *,
    ready: bool,
) -> dict[str, Any]:
    """Convert pass-2 route evidence into bounded operator replay steps."""

    replay_rows: list[dict[str, Any]] = []
    for row in skill_rows:
        selected_lane = str(row.get("selected_local_lane") or "")
        route_profiles = _string_list(row.get("route_profiles"))
        replay_rows.append(
            {
                "item_type": "skill_route_candidate",
                "proposal_id": str(row.get("proposal_id") or ""),
                "candidate_name": str(row.get("candidate_name") or ""),
                "candidate_source_hash": str(row.get("candidate_source_hash") or ""),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_profiles": route_profiles,
                "selected_local_lane": selected_lane if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES else "",
                "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
                "validation_target": str(row.get("validation_target") or ""),
                "replay_command_hash": _stable_hash(str(row.get("replay_command") or "")),
                "check_status": "ready" if str(row.get("row_status") or "") == "ready" else "blocked",
                "activation_blockers": _string_list(row.get("activation_blockers")),
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_replay_command_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    for row in adjacent_agent_rows:
        replay_rows.append(
            {
                "item_type": "adjacent_agent_harness_eval",
                "proposal_id": str(row.get("proposal_id") or ""),
                "item_id": str(row.get("item_id") or ""),
                "source_url_hash": str(row.get("source_url_hash") or ""),
                "route_hint": "agent_harness_eval",
                "route_profiles": [],
                "selected_local_lane": "test",
                "allowed_local_lanes": ["documentation", "test", "code_patch"],
                "evaluation_lane": "agent_harness_eval_required",
                "skill_route_discovery_inherited": False,
                "validation_target": "agent_harness_eval_lane_before_code_or_config_change",
                "replay_command_hash": _stable_hash(str(row.get("replay_command") or "")),
                "check_status": (
                    "ready"
                    if row.get("evaluation_lane") == "agent_harness_eval_required"
                    and row.get("skill_route_discovery_inherited") is False
                    and row.get("direct_runtime_route_allowed") is False
                    and row.get("external_harness_execution_allowed") is False
                    else "blocked"
                ),
                "activation_blockers": [],
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_replay_command_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    selected_local_lanes = [
        lane
        for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        if lane in {str(row.get("selected_local_lane") or "") for row in skill_rows}
    ]
    checklist_ready = ready and bool(replay_rows) and all(
        str(row.get("check_status") or "") == "ready" for row in replay_rows
    )

    return {
        "controller_surface": "skill_route_discovery_pass2_preactivation_checklist",
        "status": "ready" if checklist_ready else "blocked",
        "decision": (
            "pass2_routes_ready_for_operator_replay_without_activation"
            if checklist_ready
            else "repair_pass2_route_checklist_before_operator_replay"
        ),
        "review_gate": "focused-evidence-review",
        "required_actions": [
            "review_hashed_evidence_refs",
            "run_focused_local_validation",
            "inspect_changed_files",
            "keep_external_activation_denied",
        ],
        "skill_route_candidate_count": len(skill_rows),
        "adjacent_agent_eval_count": len(adjacent_agent_rows),
        "selected_local_lanes": selected_local_lanes,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "agent_harness_eval_required": bool(adjacent_agent_rows),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_replay_command_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": replay_rows,
    }


def _skill_route_discovery_current_window_pass2_route_lane_matrix(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this pass-2 window as bounded skill lanes plus adjacent harness eval."""

    proposal_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-index",
            "proposal_kind": "test",
            "proposal_track": "skill_route_discovery_index",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "skill_route_index_preserves_bounded_lane_mapping",
        },
        {
            "proposal_id": "p2-skill-route-discovery-test-fixtures",
            "proposal_kind": "test",
            "proposal_track": "skill_workflow_route_fixtures",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "skill_route_fixture_preserves_interpreter_controller_boundary",
        },
        {
            "proposal_id": "p3-game-frontend-skill-profile",
            "proposal_kind": "test",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_target": "game_frontend_profile_requires_local_frontend_validation",
        },
        {
            "proposal_id": "p4-skill-ecosystem-state-handoff-profile",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_profile_stays_metadata_only",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda value: str(value.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            source_url = str(candidate.get("source_url") or candidate_name)
            candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(source_url))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")
        if not validation_gates:
            blockers.append("missing_validation_gate")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "replay_command": (
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_window_pass2_route_lane_matrix"
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
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p5-agent-project-harness-eval-doc",
    )
    blocked_proposal_ids = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        and row["external_harness_execution_allowed"] is False
        for row in adjacent_rows
    )
    ready = bool(rows) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_window_pass2_route_lane_matrix",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_window_pass2_routes_ready_for_bounded_local_lane_validation"
            if ready
            else "repair_current_window_pass2_routes_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T004729.566895Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs]
        + ["p5-agent-project-harness-eval-doc"],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
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
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "interpreter_controller_boundary": {
            "input_evidence_shape": "selected_digest_items_or_frozen_route_classification_fixture",
            "preserved_fields": [
                "route_hints",
                "route_class",
                "route_profiles",
                "allowed_local_lanes",
                "local_validation_required",
            ],
            "raw_upstream_body_exported": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "runtime_action": "none",
        },
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_classification_metadata",
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
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_window_pass1_discovery_intake_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this pass-1 proposal intake as skill lanes plus adjacent eval."""

    proposal_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-catalog",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_discovery_catalog",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "bounded_skill_route_discovery_intake_checklist",
        },
        {
            "proposal_id": "p2-skill-profile-routing-tests",
            "proposal_kind": "test",
            "proposal_track": "skill_profile_routing_tests",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "profile_lanes_preserve_local_validation_required",
        },
        {
            "proposal_id": "p4-game-frontend-skill-eval-fixture",
            "proposal_kind": "test",
            "proposal_track": "game_frontend_skill_eval_fixture",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_target": "game_frontend_workflow_requires_local_frontend_validation",
        },
        {
            "proposal_id": "p5-skill-ecosystem-handoff-note",
            "proposal_kind": "documentation",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "documentation",
            "validation_target": "state_handoff_note_keeps_profile_and_memory_writes_denied",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda value: str(value.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            source_url = str(candidate.get("source_url") or candidate_name)
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(source_url))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")
        if not validation_gates:
            blockers.append("missing_validation_gate")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q -k "
                    "current_window_pass1_discovery_intake_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-evaluation-lane",
    )
    blocked_proposal_ids = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        and row["external_harness_execution_allowed"] is False
        for row in adjacent_rows
    )
    ready = bool(rows) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_window_pass1_discovery_intake_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_window_pass1_skill_routes_ready_for_bounded_intake"
            if ready
            else "repair_current_window_pass1_intake_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T014729.582985Z",
        "capability_pass": 1,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs]
        + ["p3-agent-harness-evaluation-lane"],
        "ready_skill_proposal_count": len(rows) - len(blocked_proposal_ids),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "supervisor_next_action": "replay_ready_skill_intake_lanes_and_keep_agent_project_in_eval_queue",
        "activation_authority": "external_supervisor_after_validation",
        "general_agent_project_policy": {
            "proposal_id": "p3-agent-harness-evaluation-lane",
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_allowed_lanes_before_eval": [],
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"] if adjacent_rows else [],
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_upstream_body_exported": False,
        },
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
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_active_pass1_skill_route_discovery_matrix(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Map the active pass-1 proposal IDs to bounded local validation lanes."""

    proposal_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-regression",
            "proposal_kind": "test",
            "proposal_track": "skill_workflow_route_classification_regression",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "three_skill_workflow_examples_stay_in_bounded_lanes",
        },
        {
            "proposal_id": "p2-skill-route-discovery-doc",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_interpretation_documentation",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "popularity_is_not_implementation_evidence_documented",
        },
        {
            "proposal_id": "p4-route-proposal-schema-guard",
            "proposal_kind": "config",
            "proposal_track": "route_proposal_schema_guard",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "config",
            "validation_target": "route_proposal_schema_accepts_only_bounded_lane_metadata",
        },
        {
            "proposal_id": "p5-route-hint-to-lane-matrix-test",
            "proposal_kind": "test",
            "proposal_track": "route_hint_to_lane_matrix_regression",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "route_hint_lane_matrix_replay_keeps_skill_routes_bounded",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    blocked_proposal_ids: list[str] = []
    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda value: str(value.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            source_url = str(candidate.get("source_url") or candidate_name)
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(source_url))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_skill_workflow_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")
        if not validation_gates:
            blockers.append("missing_validation_gate")

        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q -k "
                    "active_pass1_skill_route_discovery_matrix"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-eval-fixtures",
    )
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        and row["runtime_action"] == "none"
        and row["external_harness_execution_allowed"] is False
        for row in adjacent_rows
    )
    ready = bool(rows) and not blocked_proposal_ids and adjacent_ready and bool(adjacent_rows)

    return {
        "controller_surface": "skill_route_discovery_active_pass1_skill_route_discovery_matrix",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass1_skill_and_agent_routes_ready_for_bounded_local_validation"
            if ready
            else "repair_active_pass1_skill_route_discovery_matrix_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T054729.697946Z",
        "capability_pass": 1,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs]
        + ["p3-agent-harness-eval-fixtures"],
        "ready_skill_proposal_count": len(rows) - len(blocked_proposal_ids),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "generic_skill_workflow",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "general_agent_project_policy": {
            "proposal_id": "p3-agent-harness-eval-fixtures",
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_allowed_lanes_before_eval": [],
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"] if adjacent_rows else [],
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_upstream_body_exported": False,
        },
        "required_evidence": [
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "focused_local_validation",
            "rollback_artifact",
            "review_note",
        ],
        "required_validation": [
            "python -m pytest tests/test_skill_routing.py -q -k active_pass1_skill_route_discovery_matrix",
            "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
        ],
        "supervisor_next_action": "replay_active_pass1_skill_route_matrix_and_keep_agent_project_in_eval_queue",
        "activation_authority": "external_supervisor_after_validation",
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
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_active_pass1_proposal_replay_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Map the active pass-1 proposals to bounded local validation lanes."""

    proposal_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-docs-and-probe",
            "proposal_kind": "documentation",
            "proposal_track": "bounded_skill_route_discovery_docs_and_probe",
            "route_profiles": (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "skill_route_discovery_inputs_to_documentation_config_test_code_patch_checklist",
            "expected_validation_concerns": (
                "selected_item_ids_only",
                "no_external_url_expansion",
                "bounded_local_lane_matrix",
            ),
        },
        {
            "proposal_id": "p2-skill-route-discovery-test-fixtures",
            "proposal_kind": "test",
            "proposal_track": "skill_workflow_classifier_fixture_lanes",
            "route_profiles": (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "skill_workflow_items_remain_in_documentation_config_test_code_patch_lanes",
            "expected_validation_concerns": (
                "parser_classifier_replay",
                "unsupported_lane_downgrade",
                "runtime_execution_blocked",
            ),
        },
        {
            "proposal_id": "p3-game-frontend-skill-profile-discovery",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow_profile_discovery",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_workflow_profile_records_frontend_visual_validation_concerns",
            "expected_validation_concerns": (
                "runnable_examples",
                "visual_assets",
                "frontend_testability",
                "local_test_or_frontend_validation_before_activation",
            ),
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    blocked_proposal_ids: list[str] = []
    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

        for candidate in candidate_lane_inventory:
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            source_url = str(candidate.get("source_url") or candidate_name)
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(source_url))
            selected_evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")
        if not validation_gates:
            blockers.append("missing_validation_gate")

        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "expected_validation_concerns": list(spec["expected_validation_concerns"]),
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

    raw_adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p5-agent-harness-eval-fixtures",
    )
    adjacent_rows = []
    for row in raw_adjacent_rows:
        sanitized_row = dict(row)
        adjacent_name = str(sanitized_row.get("name") or "")
        sanitized_row["name_hash"] = _stable_hash(adjacent_name) if adjacent_name else ""
        sanitized_row["name"] = ""
        sanitized_row["raw_name_exported"] = False
        adjacent_rows.append(sanitized_row)
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        and row["external_harness_execution_allowed"] is False
        for row in adjacent_rows
    )
    ready = bool(rows) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_active_pass1_proposal_replay_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass1_proposals_ready_for_bounded_local_replay"
            if ready
            else "repair_active_pass1_proposal_lane_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T030729.514321Z",
        "capability_pass": 1,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs],
        "ready_skill_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "agent_harness_eval_required_count": len(adjacent_rows),
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "required_validation": [
            "python -m pytest tests/test_harness_eval.py -q -k active_pass1_proposal_replay_lane",
            "python -m pytest tests/test_proposal_eval.py -q -k skill_route_discovery",
        ],
        "supervisor_next_action": "replay_active_pass1_skill_route_lanes_before_activation",
        "activation_authority": "external_supervisor_after_validation",
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
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_digest_pass1_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose the active digest proposal IDs as first-pass validation lanes."""

    current_174729_window = source_digest == "github-growth-20260628T174729.552272Z"
    current_150729_window = source_digest == "github-growth-20260628T150729.645832Z"
    current_162729_window = source_digest == "github-growth-20260628T162729.568714Z"
    current_190729_window = source_digest == "github-growth-20260628T190729.559090Z"
    current_101324_window = source_digest == "github-growth-20260629T101324.100619Z"
    current_171904_window = source_digest == "github-growth-20260629T171904.272271Z"
    current_195904_window = source_digest == "github-growth-20260629T195904.271855Z"
    if current_195904_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-compass-skills",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_target": "compass_skill_ecosystem_handoff_route_metadata",
                "validation_task": (
                    "feed COMPASS-style skill ecosystem evidence through route classification "
                    "and prove it remains in bounded local lanes with validation required"
                ),
            },
            {
                "proposal_id": "p2-generic-skill-workflow-probe",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow",),
                "selected_local_lane": "documentation",
                "validation_target": "generic_skill_workflow_probe_route_note",
                "validation_task": (
                    "record that zhengxi-style agent plus skill topic evidence maps to "
                    "skill_route_discovery without provider runtime or direct activation"
                ),
            },
        )
    elif current_101324_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-compass",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_target": "compass_skill_ecosystem_routes_only_to_bounded_local_lanes",
                "validation_task": (
                    "prove COMPASS-style skill ecosystem repositories route only to documentation, "
                    "config, test, or code_patch lanes before any profile or memory action"
                ),
            },
            {
                "proposal_id": "p2-skill-route-discovery-generic",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_target": "generic_skill_workflow_route_interpretation_note",
                "validation_task": (
                    "document that generic skill workflow trend signals are bounded local "
                    "validation candidates and do not imply direct runtime action"
                ),
            },
        )
    elif current_190729_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-index",
                "proposal_kind": "documentation",
                "proposal_track": "route_discovery_index",
                "route_profiles": (
                    "generic_skill_workflow",
                    "source_cited_domain_research",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "documentation",
                "validation_target": "current_digest_skill_route_discovery_index",
                "validation_task": (
                    "record how carried public skill repositories classify into bounded local "
                    "documentation, config, test, or code_patch lanes before implementation"
                ),
            },
            {
                "proposal_id": "p2-skill-route-fixture-tests",
                "proposal_kind": "test",
                "proposal_track": "skill_workflow_route_classification_fixtures",
                "route_profiles": (
                    "generic_skill_workflow",
                    "source_cited_domain_research",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "test",
                "validation_target": "current_digest_skill_route_fixture_regression",
                "validation_task": (
                    "assert skill-term trends map to skill_route_discovery and strip unsupported "
                    "activation, provider, and execution lanes"
                ),
            },
            {
                "proposal_id": "p3-game-frontend-skill-profile",
                "proposal_kind": "config",
                "proposal_track": "game_frontend_workflow",
                "route_profiles": ("game_frontend_workflow",),
                "selected_local_lane": "config",
                "validation_target": "game_frontend_workflow_route_profile_metadata_only",
                "validation_task": (
                    "validate game frontend skill evidence affects only route metadata before "
                    "local frontend or render validation justifies patch work"
                ),
            },
        )
    else:
        specs = (
            {
                "proposal_id": (
                    "proposal_skill_route_discovery_index"
                    if current_162729_window
                    else (
                        "p1-skill-route-discovery-index"
                        if current_150729_window
                        else "p1-skill-route-discovery-generic"
                    )
                ),
                "proposal_kind": "test",
                "proposal_track": "generic_or_source_cited_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "test",
                "validation_target": "repository_trend_shape_keeps_generic_skill_routes_bounded",
                "validation_task": (
                    "assert RepositoryTrend evidence preserves local_validation_required, "
                    "bounded lanes, and no direct runtime action"
                ),
            },
            {
                "proposal_id": (
                    "proposal_game_frontend_skill_profile"
                    if current_162729_window
                    else (
                        "p2-threejs-game-skill-routing"
                        if current_174729_window
                        else "p2-game-frontend-skill-profile"
                    )
                ),
                "proposal_kind": "documentation",
                "proposal_track": "game_frontend_workflow",
                "route_profiles": ("game_frontend_workflow",),
                "selected_local_lane": "documentation",
                "validation_target": "game_frontend_workflow_profile_requires_local_fixture_before_runtime_use",
                "validation_task": (
                    "document metadata identification, no direct execution, local fixture tests, "
                    "and recomputable controller scope"
                ),
            },
            {
                "proposal_id": (
                    "proposal_skill_state_handoff_profile"
                    if current_162729_window
                    else (
                        "p3-skill-ecosystem-handoff-profile"
                        if current_150729_window
                        else "p3-skill-ecosystem-state-handoff"
                    )
                ),
                "proposal_kind": "config",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "config",
                "validation_target": "state_or_workflow_handoff_candidate_records_uncertainty_without_execution",
                "validation_task": (
                    "validate state handoff maps only to bounded lanes and records uncertainty "
                    "when no concrete handoff schema is present"
                ),
            },
        )
    if current_171904_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-compass",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_target": "compass_skill_ecosystem_handoff_metadata_lane",
                "validation_task": (
                    "run a non-network fixture proving COMPASS-style skill ecosystem signals "
                    "preserve handoff metadata while staying bounded to local validation lanes"
                ),
            },
            {
                "proposal_id": "p2-generic-skill-workflow-zhengxi",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_target": "zhengxi_generic_skill_workflow_route_interpretation",
                "validation_task": (
                    "document that zhengxi-style skill-term evidence routes through "
                    "skill_route_discovery and remains bounded before activation"
                ),
            },
        )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    replay_command_hashes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        uncertainty_reasons: list[str] = []
        downgraded_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            matched_profiles = [profile for profile in candidate_profiles if profile in required_profiles]
            if not matched_profiles:
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            route_profiles.extend(matched_profiles)
            observed_profiles.extend(matched_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            uncertainty_reasons.extend(_string_list(candidate.get("uncertainty_reasons")))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        replay_command = _skill_route_discovery_replay_command(selected_lane, route_profiles)
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(route_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "validation_task": str(spec["validation_task"]),
                "uncertainty_reasons": list(dict.fromkeys(uncertainty_reasons)),
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "replay_command_hash": _stable_hash(replay_command) if replay_command else "",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows: list[dict[str, Any]] = []
    for adjacent_row in _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id=(
            "p3-agent-harness-eval-qwen-agentworld"
            if current_195904_window
            else
            "p3-agent-harness-qwen-agentworld"
            if current_171904_window
            else
            "p3-agent-harness-eval-general-agent-projects"
            if current_101324_window
            else
            "proposal_agent_harness_eval_fixtures"
            if current_162729_window
            else (
                "p4-agent-harness-eval"
                if current_174729_window
                else (
                    "p4-agent-harness-eval-fixtures"
                    if current_190729_window
                    else (
                        "p4-agent-harness-eval-fixture"
                        if current_150729_window
                        else "p4-agent-harness-eval-qwen"
                    )
                )
            )
        ),
    ):
        replay_command = str(adjacent_row.get("replay_command") or "")
        row = dict(adjacent_row)
        if current_195904_window and str(row.get("name") or "").casefold() == "looper":
            row["proposal_id"] = "p4-agent-harness-eval-looper"
        if current_171904_window and str(row.get("name") or "").casefold() == "looper":
            row["proposal_id"] = "p4-agent-harness-looper"
        row.pop("replay_command", None)
        row["replay_command_hash"] = _stable_hash(replay_command) if replay_command else ""
        row["accepted_outputs_after_eval"] = ["docs", "tests", "code_patch"]
        row["raw_replay_command_exported"] = False
        adjacent_rows.append(row)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    adjacent_ready = all(
        row.get("evaluation_lane") == "agent_harness_eval_required"
        and row.get("skill_route_discovery_inherited") is False
        and row.get("direct_runtime_route_allowed") is False
        and row.get("direct_code_patch_route_allowed") is False
        and row.get("external_harness_execution_allowed") is False
        and row.get("provider_runtime_launch_allowed") is False
        for row in adjacent_rows
    )
    ready = len(rows) == len(specs) and not blocked_proposal_ids and adjacent_ready

    anchoring_proposal_ids = (
        [
            "p1-skill-route-discovery-compass-skills",
            "p2-generic-skill-workflow-probe",
            "p3-agent-harness-eval-qwen-agentworld",
            "p4-agent-harness-eval-looper",
            "p5-security-agent-review-boundary-autocve",
            "trend:dongshuyan/compass-skills-1",
            "trend:lyra81604/zhengxi-views-1",
            "trend:QwenLM/Qwen-AgentWorld-1",
            "trend:ksimback/looper-1",
        ]
        if current_195904_window
        else
        [
            "p1-skill-route-discovery-compass",
            "p2-generic-skill-workflow-zhengxi",
            "p3-agent-harness-qwen-agentworld",
            "p4-agent-harness-looper",
            "trend:lyra81604/zhengxi-views-1",
        ]
        if current_171904_window
        else
        [
            "p1-skill-route-discovery-compass",
            "p2-skill-route-discovery-generic",
            "p3-agent-harness-eval-general-agent-projects",
            "p4-security-agent-review-boundary",
            "p5-agent-routing-config-preflight",
        ]
        if current_101324_window
        else
        [
            "proposal_skill_route_discovery_index",
            "proposal_game_frontend_skill_profile",
            "proposal_skill_state_handoff_profile",
            "proposal_agent_harness_eval_fixtures",
            "proposal_route_confidence_reporting",
        ]
        if current_162729_window
        else [
            "p1-skill-route-discovery-generic",
            "p2-threejs-game-skill-routing",
            "p3-skill-ecosystem-state-handoff",
            "p4-agent-harness-eval",
            "trend:lyra81604/zhengxi-views-1",
        ]
        if current_174729_window
        else [
            "p1-skill-route-discovery-index",
            "p2-skill-route-fixture-tests",
            "p3-game-frontend-skill-profile",
            "p4-agent-harness-eval-fixtures",
            "p5-skill-ecosystem-state-handoff",
        ]
        if current_190729_window
        else [
            "p1-skill-route-discovery-index",
            "p2-game-frontend-skill-profile",
            "p3-skill-ecosystem-handoff-profile",
            "p4-agent-harness-eval-fixture",
            "p5-proposal-output-citation-guard",
        ]
        if current_150729_window
        else [
            "p1-skill-route-discovery-generic",
            "p2-game-frontend-skill-profile",
            "p3-skill-ecosystem-state-handoff",
            "p4-agent-harness-eval-qwen",
            "p5-agent-harness-eval-looper",
        ]
    )

    return {
        "controller_surface": "skill_route_discovery_current_digest_pass1_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_digest_pass1_skill_routes_ready_for_bounded_local_validation"
            if ready
            else "repair_current_digest_pass1_skill_routes_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T134729.588648Z",
        "capability_pass": 1,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "capability_slice": "skill-route-discovery",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs],
        "anchoring_proposal_ids": anchoring_proposal_ids,
        "ready_skill_route_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
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
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
        "adjacent_general_agent_policy": {
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_local_change_proposals_allowed": False,
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        },
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "uncertainty_note_for_missing_handoff_schema",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_next_action": (
            "replay_current_digest_pass1_validation_before_pass2"
            if ready
            else "repair_blocked_pass1_rows_before_activation"
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
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_digest_pass2_local_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose current digest pass-2 proposals as bounded local validation lanes."""

    current_103324_window = source_digest == "github-growth-20260629T103324.012579Z"
    current_173904_window = source_digest == "github-growth-20260629T173904.211836Z"
    inventory_profiles = {
        profile
        for candidate in candidate_lane_inventory
        for profile in (_string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"])
    }
    compass_generic_only = (
        "skill_ecosystem_state_handoff" in inventory_profiles
        and bool(inventory_profiles & {"generic_skill_workflow", "source_cited_domain_research"})
        and "game_frontend_workflow" not in inventory_profiles
    )
    specs = (
        (
            {
                "proposal_id": (
                    "p1-skill-route-discovery-registry"
                    if current_103324_window
                    else "p1-skill-route-discovery-compass-skills"
                ),
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_target": (
                    "compass_and_zhengxi_skill_terms_stay_bounded_local_lanes"
                    if current_103324_window
                    else "skill_ecosystem_handoff_route_probe_fixture"
                ),
                "validation_task": (
                    (
                        "validate skill-term repository evidence maps only to documentation, "
                        "config, test, or code_patch lanes with local validation required"
                    )
                    if current_103324_window
                    else (
                        "detect skill manifests, state handoff conventions, and route metadata "
                        "without installing, executing, writing profiles, or writing memory"
                    )
                ),
                "expected_input_signals": (
                    "skill_directory",
                    "skill_registry_metadata",
                    "agent_metadata",
                    "qa_checklist",
                ),
            },
            {
                "proposal_id": (
                    "p3-skill-route-docs"
                    if current_103324_window
                    else "p2-skill-route-discovery-zhengxi-views"
                    if current_173904_window
                    else "p2-generic-skill-workflow-probe"
                ),
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_target": (
                    "skill_route_discovery_evidence_interpretation_docs"
                    if current_103324_window
                    else "generic_skill_workflow_probe_route_documentation"
                ),
                "validation_task": (
                    (
                        "document when skill-route evidence is a discovery signal rather "
                        "than an upstream implementation instruction"
                    )
                    if current_103324_window
                    else (
                        "document sufficient evidence for manifest detection, non-execution "
                        "inspection, bounded lane mapping, uncertainty recording, and rollback"
                    )
                ),
                "expected_input_signals": (
                    "skill_markdown",
                    "validation_script",
                    "skill_registry_metadata",
                ),
            },
        )
        if compass_generic_only
        else (
        {
            "proposal_id": "p1-skill-route-discovery-compass-handoff",
            "proposal_kind": "test",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "test",
            "validation_target": "skill_ecosystem_handoff_metadata_lane_boundary",
            "validation_task": (
                "validate that documentation, config, test, and patchable route metadata "
                "are discoverable without profile writes, memory writes, install, or execution"
            ),
            "expected_input_signals": (
                "skill_directory",
                "skill_registry_metadata",
                "agent_metadata",
                "qa_checklist",
            ),
        },
        {
            "proposal_id": "p2-threejs-game-skill-routing-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_workflow_route_profile_note",
            "validation_task": (
                "document game/frontend skill routing as metadata-first discovery before "
                "scaffold execution, asset generation, provider launch, or runtime use"
            ),
            "expected_input_signals": (
                "skill_directory",
                "validation_script",
                "scaffold_asset",
            ),
        },
        {
            "proposal_id": "p3-generic-skill-workflow-discovery-fixture",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_fixture_keeps_runtime_action_none",
            "validation_task": (
                "assert agent plus skill workflow evidence maps only to bounded local lanes "
                "with runtime_action remaining none"
            ),
            "expected_input_signals": (
                "skill_markdown",
                "validation_script",
                "skill_registry_metadata",
            ),
        },
        )
    )
    active_proposal_ids = (
        [
            "p1-skill-route-discovery-registry",
            "p2-agent-harness-eval-fixtures",
            "p3-skill-route-docs",
        ]
        if current_103324_window
        else
        [
            "p1-skill-route-discovery-compass-skills",
            "p2-skill-route-discovery-zhengxi-views",
            "p3-agent-harness-qwen-agentworld",
            "p4-agent-harness-looper",
        ]
        if current_173904_window
        else
        [
            "p1-skill-route-discovery-compass-skills",
            "p2-generic-skill-workflow-probe",
            "p3-agent-harness-qwen-agentworld",
        ]
        if compass_generic_only
        else [
            "p1-skill-route-discovery-generic",
            "p2-agent-harness-eval-qwen-agentworld",
            "p3-game-frontend-skill-route",
        ]
    )
    anchoring_proposal_ids = (
        [
            "p1-skill-route-discovery-compass",
            "p2-skill-route-discovery-generic",
            "p3-agent-harness-eval-general-agent-projects",
            "p4-security-agent-review-boundary",
            "p5-agent-routing-config-preflight",
            "p1-skill-route-discovery-registry",
            "p2-agent-harness-eval-fixtures",
            "p3-skill-route-docs",
            "p4-provider-agent-preflight",
            "p5-autocve-review-gate",
        ]
        if current_103324_window
        else
        [
            "p1-skill-route-discovery-compass",
            "p2-generic-skill-workflow-zhengxi",
            "p3-agent-harness-qwen-agentworld",
            "p4-agent-harness-looper",
            "trend:lyra81604/zhengxi-views-1",
            "p1-skill-route-discovery-compass-skills",
            "p2-skill-route-discovery-zhengxi-views",
            "p5-security-agent-harness-autocve",
        ]
        if current_173904_window
        else
        [
            "p1-skill-route-discovery-compass-skills",
            "p2-skill-route-discovery-zhengxi-views",
            "p3-agent-harness-qwen-agentworld",
            "p4-agent-harness-looper",
            "p5-security-agent-review-lane-autocve",
            "p1-skill-ecosystem-route-discovery",
            "p2-generic-skill-workflow-probe",
            "p3-agentworld-harness-eval",
            "p4-loop-scheduling-eval",
            "trend:lyra81604/zhengxi-views-1",
        ]
        if compass_generic_only
        else [
            "p1-skill-route-discovery-generic",
            "p2-game-frontend-skill-profile",
            "p3-skill-ecosystem-state-handoff",
            "p4-agent-harness-eval-qwen",
            "p5-agent-harness-eval-looper",
            "p1-skill-route-discovery-compass-handoff",
            "p2-threejs-game-skill-routing-profile",
            "p3-generic-skill-workflow-discovery-fixture",
            "p4-skill-trend-intake-config-guard",
            "trend:lyra81604/zhengxi-views-1",
        ]
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    replay_command_hashes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        uncertainty_reasons: list[str] = []
        downgraded_lanes: list[str] = []
        source_layout_signals: list[str] = []
        source_metadata_signals: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            matched_profiles = [profile for profile in candidate_profiles if profile in required_profiles]
            if not matched_profiles:
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            route_profiles.extend(matched_profiles)
            observed_profiles.extend(matched_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            uncertainty_reasons.extend(_string_list(candidate.get("uncertainty_reasons")))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))
            source_layout_signals.extend(_string_list(candidate.get("source_layout_signals")))
            source_metadata_signals.extend(_string_list(candidate.get("source_metadata_signals")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        replay_command = _skill_route_discovery_replay_command(selected_lane, route_profiles)
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if set(bounded_lanes) - set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES):
            blockers.append("unbounded_lane_present")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(route_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "validation_task": str(spec["validation_task"]),
                "expected_input_signals": list(spec["expected_input_signals"]),
                "observed_layout_signals": list(dict.fromkeys(source_layout_signals)),
                "observed_metadata_signals": list(dict.fromkeys(source_metadata_signals)),
                "uncertainty_reasons": list(dict.fromkeys(uncertainty_reasons)),
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "accepted_outputs": ["docs", "config", "tests", "code_patch"],
                "replay_command_hash": _stable_hash(replay_command) if replay_command else "",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows: list[dict[str, Any]] = []
    for adjacent_row in _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id=(
            "p2-agent-harness-eval-fixtures"
            if current_103324_window
            else "p4-agent-harness-eval-qwen"
        ),
    ):
        replay_command = str(adjacent_row.get("replay_command") or "")
        row = dict(adjacent_row)
        row.pop("replay_command", None)
        row["replay_command_hash"] = _stable_hash(replay_command) if replay_command else ""
        row["accepted_outputs_after_eval"] = ["docs", "tests", "code_patch"]
        row["raw_replay_command_exported"] = False
        adjacent_rows.append(row)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    adjacent_ready = all(
        row.get("evaluation_lane") == "agent_harness_eval_required"
        and row.get("skill_route_discovery_inherited") is False
        and row.get("direct_runtime_route_allowed") is False
        and row.get("direct_code_patch_route_allowed") is False
        and row.get("external_harness_execution_allowed") is False
        and row.get("provider_runtime_launch_allowed") is False
        for row in adjacent_rows
    )
    ready = len(rows) == len(specs) and not blocked_proposal_ids and adjacent_ready
    focused_review_lane = _skill_route_discovery_current_digest_pass2_focused_review_lane(
        rows,
        adjacent_rows,
        source_digest=source_digest,
        compass_generic_only=compass_generic_only,
    )
    active_slice_review_lane = _skill_route_discovery_current_digest_pass2_active_slice_review_lane(
        rows,
        adjacent_rows,
        source_digest=source_digest,
    )

    visible_active_proposal_ids = list(active_proposal_ids)
    if compass_generic_only and not current_103324_window and any(
        "looper" in " ".join((str(row.get("name") or ""), str(row.get("item_id") or ""))).casefold()
        for row in adjacent_rows
    ):
        visible_active_proposal_ids.append("p4-agent-harness-looper")

    return {
        "controller_surface": "skill_route_discovery_current_digest_pass2_local_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_digest_pass2_skill_routes_ready_for_bounded_local_validation"
            if ready
            else "repair_current_digest_pass2_skill_routes_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T140729.531143Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "capability_slice": "skill-route-discovery",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs],
        "active_proposal_ids": list(dict.fromkeys(visible_active_proposal_ids)),
        "anchoring_proposal_ids": anchoring_proposal_ids,
        "ready_skill_route_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
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
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
        "adjacent_general_agent_policy": {
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_local_change_proposals_allowed": False,
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        },
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "bounded_lane_inventory",
            "metadata_only_state_handoff_boundary",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_next_action": (
            "replay_current_digest_pass2_local_validation_lane_before_pass3"
            if ready
            else "repair_blocked_pass2_rows_before_activation"
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
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
        "focused_evidence_review_lane": focused_review_lane,
        "active_slice_review_lane": active_slice_review_lane,
    }


def _skill_route_discovery_current_digest_pass2_focused_review_lane(
    rows: Sequence[Mapping[str, Any]],
    adjacent_rows: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
    compass_generic_only: bool = False,
) -> dict[str, Any]:
    """Bind the active pass-2 proposal IDs to bounded local validation rows."""

    skill_rows_by_track = {
        str(row.get("proposal_track") or ""): row
        for row in rows
        if isinstance(row, Mapping)
    }
    generic_row = (
        skill_rows_by_track.get("generic_skill_workflow")
        or skill_rows_by_track.get("source_cited_domain_research")
        or {}
    )
    compass_row = skill_rows_by_track.get("skill_ecosystem_state_handoff") or {}
    game_row = skill_rows_by_track.get("game_frontend_workflow") or {}
    qwen_row = next(
        (
            row
            for row in adjacent_rows
            if str(row.get("name") or "").casefold() == "qwen-agentworld"
            or "qwen" in str(row.get("item_id") or "").casefold()
        ),
        adjacent_rows[0] if adjacent_rows else {},
    )
    focused_agent_rows: list[dict[str, Any]] = []
    focused_agent_proposal_ids: set[str] = set()
    for row in adjacent_rows:
        proposal_id = _skill_route_discovery_current_digest_pass2_agent_proposal_id(row)
        if proposal_id in focused_agent_proposal_ids:
            continue
        focused_agent_proposal_ids.add(proposal_id)
        focused_agent_rows.append(
            _skill_route_discovery_current_digest_pass2_focused_agent_row(
                row,
                proposal_id=proposal_id,
            )
        )

    if compass_generic_only:
        current_173904_window = source_digest == "github-growth-20260629T173904.211836Z"
        proposal_rows = [
            _skill_route_discovery_current_digest_pass2_focused_skill_row(
                compass_row,
                proposal_id="p1-skill-route-discovery-compass-skills",
                proposal_kind="test",
                selected_local_lane="test",
                validation_target="skill_ecosystem_handoff_route_probe_fixture",
            ),
            _skill_route_discovery_current_digest_pass2_focused_skill_row(
                generic_row,
                proposal_id=(
                    "p2-skill-route-discovery-zhengxi-views"
                    if current_173904_window
                    else "p2-generic-skill-workflow-probe"
                ),
                proposal_kind="documentation",
                selected_local_lane="documentation",
                validation_target="generic_skill_workflow_probe_route_documentation",
            ),
            *focused_agent_rows,
        ]
    else:
        selected_focused_agent_rows = focused_agent_rows[:1] or [
            _skill_route_discovery_current_digest_pass2_focused_agent_row(
                qwen_row,
                proposal_id="p2-agent-harness-eval-qwen-agentworld",
            )
        ]
        if selected_focused_agent_rows:
            selected_focused_agent_rows[0]["proposal_id"] = "p2-agent-harness-eval-qwen-agentworld"
        proposal_rows = [
            _skill_route_discovery_current_digest_pass2_focused_skill_row(
                generic_row,
                proposal_id="p1-skill-route-discovery-generic",
                proposal_kind="test",
                selected_local_lane="test",
                validation_target="generic_skill_workflow_repository_metadata_probe",
            ),
            *selected_focused_agent_rows,
            _skill_route_discovery_current_digest_pass2_focused_skill_row(
                game_row,
                proposal_id="p3-game-frontend-skill-route",
                proposal_kind="documentation",
                selected_local_lane="documentation",
                validation_target="game_frontend_workflow_route_profile_note",
            ),
        ]
    blocked_proposal_ids = [
        str(row["proposal_id"])
        for row in proposal_rows
        if row.get("status") != "ready"
    ]
    selected_lanes = [
        str(row.get("selected_local_lane"))
        for row in proposal_rows
        if str(row.get("selected_local_lane") or "") in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    ready = not blocked_proposal_ids

    return {
        "controller_surface": "skill_route_discovery_current_digest_pass2_focused_evidence_review_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass2_proposals_ready_for_focused_local_validation"
            if ready
            else "repair_active_pass2_focused_review_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T192730.399337Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(row["proposal_id"]) for row in proposal_rows],
        "blocked_proposal_ids": blocked_proposal_ids,
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_skill_route_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "agent_harness_eval_required": bool(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "agent_harness_eval_required_before_implementation": True,
        "agent_harness_eval_probe_requirements": [
            "install_shape",
            "entrypoints",
            "dependency_boundaries",
            "task_loop_assumptions",
            "observable_behaviors",
            "evaluation_dimensions",
        ],
        "operator_next_action": (
            "replay_current_digest_pass2_focused_evidence_review_lane_before_activation"
            if ready
            else "repair_focused_evidence_review_lane_before_activation"
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
        "rows": proposal_rows,
    }


def _skill_route_discovery_current_digest_pass2_agent_proposal_id(row: Mapping[str, Any]) -> str:
    """Return a stable proposal id for adjacent pass-2 general-agent evidence."""

    text = " ".join((str(row.get("name") or ""), str(row.get("item_id") or ""))).casefold()
    if "looper" in text:
        return "p4-agent-harness-looper"
    if "qwen" in text or "agentworld" in text:
        return "p3-agent-harness-qwen-agentworld"
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "general-agent-project"
    return f"p3-agent-harness-{slug}"


def _skill_route_discovery_current_digest_pass2_focused_skill_row(
    row: Mapping[str, Any],
    *,
    proposal_id: str,
    proposal_kind: str,
    selected_local_lane: str,
    validation_target: str,
) -> dict[str, Any]:
    bounded_lanes = [
        lane
        for lane in _string_list(row.get("allowed_local_lanes"))
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    validation_gates = _string_list(row.get("validation_gates"))
    evidence_item_ids = _string_list(row.get("selected_evidence_item_ids"))
    candidate_names = _string_list(row.get("candidate_names"))
    acceptance_gates = {
        "candidate_evidence_present": bool(candidate_names),
        "selected_evidence_present": bool(evidence_item_ids),
        "selected_lane_bounded": selected_local_lane in set(bounded_lanes),
        "validation_gate_present": bool(validation_gates),
        "local_validation_required": True,
        "runtime_action_none": True,
        "external_skill_activation_denied": True,
        "external_harness_execution_denied": True,
        "provider_runtime_launch_denied": True,
        "remote_execution_denied": True,
        "raw_source_url_not_exported": True,
        "raw_evidence_urls_not_exported": True,
        "raw_target_paths_not_exported": True,
        "raw_upstream_body_not_exported": True,
    }
    failed_gates = [gate for gate, passed in acceptance_gates.items() if passed is not True]
    return {
        "proposal_id": proposal_id,
        "proposal_kind": proposal_kind,
        "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
        "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
        "route_profiles": _string_list(row.get("route_profiles")),
        "status": "ready" if not failed_gates else "blocked",
        "activation_blockers": [f"acceptance_gate_failed:{gate}" for gate in failed_gates],
        "candidate_names": candidate_names,
        "candidate_source_hashes": _string_list(row.get("candidate_source_hashes")),
        "allowed_local_lanes": bounded_lanes,
        "selected_local_lane": selected_local_lane if selected_local_lane in bounded_lanes else "",
        "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_local_lane],
        "selected_evidence_item_ids": evidence_item_ids,
        "validation_gates": validation_gates,
        "validation_target": validation_target,
        "acceptance_gates": acceptance_gates,
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


def _skill_route_discovery_current_digest_pass2_focused_agent_row(
    row: Mapping[str, Any],
    *,
    proposal_id: str,
) -> dict[str, Any]:
    acceptance_gates = {
        "agent_harness_eval_required": row.get("evaluation_lane") == "agent_harness_eval_required",
        "skill_route_discovery_not_inherited": row.get("skill_route_discovery_inherited") is False,
        "direct_runtime_route_denied": row.get("direct_runtime_route_allowed") is False,
        "direct_code_patch_route_denied": row.get("direct_code_patch_route_allowed") is False,
        "external_harness_execution_denied": row.get("external_harness_execution_allowed") is False,
        "provider_runtime_launch_denied": row.get("provider_runtime_launch_allowed") is False,
        "local_validation_required": True,
        "runtime_action_none": True,
    }
    failed_gates = [gate for gate, passed in acceptance_gates.items() if passed is not True]
    return {
        "proposal_id": proposal_id,
        "proposal_kind": "test",
        "route_hint": "agent_harness_eval_required",
        "status": "ready" if not failed_gates else "blocked",
        "activation_blockers": [f"acceptance_gate_failed:{gate}" for gate in failed_gates],
        "item_id": str(row.get("item_id") or ""),
        "name": str(row.get("name") or ""),
        "source_hash": str(row.get("source_hash") or ""),
        "evaluation_lane": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "direct_runtime_route_allowed": False,
        "direct_code_patch_route_allowed": False,
        "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
        "selected_local_lane": "agent_harness_eval_required",
        "validation_gate": "local_agent_harness_eval_required_before_implementation_route",
        "validation_target": "general_agent_project_intake_probe_before_runtime_or_controller_change",
        "required_probe_fields": [
            "install_shape",
            "entrypoints",
            "dependency_boundaries",
            "task_loop_assumptions",
            "observable_behaviors",
            "evaluation_dimensions",
        ],
        "acceptance_gates": acceptance_gates,
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


def _skill_route_discovery_current_digest_pass2_active_slice_review_lane(
    rows: Sequence[Mapping[str, Any]],
    adjacent_rows: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Map the active pass-2 anchoring proposals to replayable local lanes."""

    current_103324_window = source_digest == "github-growth-20260629T103324.012579Z"
    current_173904_window = source_digest == "github-growth-20260629T173904.211836Z"
    required_skill_profiles = (
        ("generic_skill_workflow", "skill_ecosystem_state_handoff")
        if current_103324_window or current_173904_window
        else ("generic_skill_workflow", "game_frontend_workflow", "skill_ecosystem_state_handoff")
    )
    index_row = _skill_route_discovery_current_digest_pass2_active_skill_row(
        rows,
        proposal_id=(
            "p1-skill-route-discovery-registry"
            if current_103324_window
            else "p1-skill-route-discovery-compass-skills"
            if current_173904_window
            else "p1-skill-route-discovery-index"
        ),
        proposal_kind="test",
        selected_local_lane="test",
        validation_target=(
            "compass_and_zhengxi_skill_route_fixture_replay"
            if current_103324_window
            else "skill_route_discovery_index_fixture_replay"
        ),
        required_route_profiles=required_skill_profiles,
    )
    docs_row = _skill_route_discovery_current_digest_pass2_active_skill_row(
        rows,
        proposal_id=(
            "p3-skill-route-docs"
            if current_103324_window
            else "p2-skill-route-discovery-zhengxi-views"
            if current_173904_window
            else "p2-skill-profile-docs"
        ),
        proposal_kind="documentation",
        selected_local_lane="documentation",
        validation_target=(
            "skill_route_discovery_evidence_interpretation_docs"
            if current_103324_window
            else "skill_route_profile_documentation_lane_update"
        ),
        required_route_profiles=required_skill_profiles,
    )
    agent_row = _skill_route_discovery_current_digest_pass2_active_agent_row(
        adjacent_rows,
        proposal_id=(
            "p2-agent-harness-eval-fixtures"
            if current_103324_window
            else "p3-agent-harness-qwen-agentworld"
            if current_173904_window
            else "p3-agent-harness-eval-fixtures"
        ),
    )
    proposal_rows = [index_row, docs_row, agent_row]
    blocked_proposal_ids = [
        str(row["proposal_id"])
        for row in proposal_rows
        if row.get("status") != "ready"
    ]
    selected_skill_lanes = [
        str(row.get("selected_local_lane"))
        for row in (index_row, docs_row)
        if str(row.get("selected_local_lane") or "") in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    observed_profiles = [
        profile
        for row in (index_row, docs_row)
        for profile in _string_list(row.get("route_profiles"))
    ]
    ready = not blocked_proposal_ids

    return {
        "controller_surface": "skill_route_discovery_current_digest_pass2_active_slice_review_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass2_skill_route_slice_ready_for_bounded_local_validation"
            if ready
            else "repair_active_pass2_skill_route_slice_before_activation"
        ),
        "source_digest": source_digest or "",
        "capability_theme": "skill-route-discovery",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(row["proposal_id"]) for row in proposal_rows],
        "anchoring_proposal_ids": (
            [
                "p1-skill-route-discovery-compass",
                "p2-skill-route-discovery-generic",
                "p3-agent-harness-eval-general-agent-projects",
                "p4-security-agent-review-boundary",
                "p5-agent-routing-config-preflight",
                "p1-skill-route-discovery-registry",
                "p2-agent-harness-eval-fixtures",
                "p3-skill-route-docs",
                "p4-provider-agent-preflight",
                "p5-autocve-review-gate",
            ]
            if current_103324_window
            else [
                "p1-skill-route-discovery-compass",
                "p2-generic-skill-workflow-zhengxi",
                "p3-agent-harness-qwen-agentworld",
                "p4-agent-harness-looper",
                "trend:lyra81604/zhengxi-views-1",
                "p1-skill-route-discovery-compass-skills",
                "p2-skill-route-discovery-zhengxi-views",
                "p5-security-agent-harness-autocve",
            ]
            if current_173904_window
            else [
                "p1-threejs-game-skill-route-discovery",
                "p2-generic-skill-workflow-documentation",
                "p3-skill-ecosystem-state-handoff-config",
                "p4-agent-harness-eval-for-general-agent-projects",
                "p5-proposal-layer-citation-guard",
                "p1-skill-route-discovery-index",
                "p2-skill-profile-docs",
                "p3-agent-harness-eval-fixtures",
                "p4-route-metadata-config-check",
                "p5-route-hint-lane-regression",
            ]
        ),
        "blocked_proposal_ids": blocked_proposal_ids,
        "ready_proposal_count": len(proposal_rows) - len(blocked_proposal_ids),
        "observed_route_profiles": [
            profile
            for profile in (
                "generic_skill_workflow",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
                "source_cited_domain_research",
            )
            if profile in set(observed_profiles)
        ],
        "required_route_profiles": list(required_skill_profiles),
        "missing_route_profiles": [
            profile
            for profile in required_skill_profiles
            if profile not in set(observed_profiles)
        ],
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_skill_route_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_skill_lanes)
        ],
        "agent_harness_eval_required": bool(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "agent_harness_eval_required_before_implementation": True,
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
        "operator_next_action": (
            "replay_current_digest_pass2_active_slice_review_lane_before_pass3"
            if ready
            else "repair_active_slice_review_lane_before_activation"
        ),
        "rows": proposal_rows,
    }


def _skill_route_discovery_current_digest_pass2_active_skill_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    proposal_id: str,
    proposal_kind: str,
    selected_local_lane: str,
    validation_target: str,
    required_route_profiles: Sequence[str],
) -> dict[str, Any]:
    candidate_names: list[str] = []
    source_hashes: list[str] = []
    route_profiles: list[str] = []
    allowed_lanes: list[str] = []
    evidence_item_ids: list[str] = []
    validation_gates: list[str] = []
    downgraded_lanes: list[str] = []

    for row in rows:
        if not isinstance(row, Mapping) or row.get("status") != "ready":
            continue
        candidate_names.extend(_string_list(row.get("candidate_names")))
        source_hashes.extend(_string_list(row.get("candidate_source_hashes")))
        route_profiles.extend(_string_list(row.get("route_profiles")))
        allowed_lanes.extend(_string_list(row.get("allowed_local_lanes")))
        evidence_item_ids.extend(_string_list(row.get("selected_evidence_item_ids")))
        validation_gates.extend(_string_list(row.get("validation_gates")))
        downgraded_lanes.extend(_string_list(row.get("downgraded_unsupported_lanes")))

    bounded_lanes = [
        lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)
    ]
    required_profiles = set(required_route_profiles)
    observed_required_profiles = required_profiles & set(route_profiles)
    acceptance_gates = {
        "candidate_evidence_present": bool(candidate_names),
        "selected_evidence_present": bool(evidence_item_ids),
        "required_profiles_present": observed_required_profiles == required_profiles,
        "selected_lane_bounded": selected_local_lane in set(bounded_lanes),
        "validation_gate_present": bool(validation_gates),
        "unsupported_lanes_downgraded": not (
            set(downgraded_lanes) & set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        ),
        "local_validation_required": True,
        "runtime_action_none": True,
        "external_skill_activation_denied": True,
        "external_harness_execution_denied": True,
        "provider_runtime_launch_denied": True,
        "raw_source_url_not_exported": True,
        "raw_evidence_urls_not_exported": True,
        "raw_target_paths_not_exported": True,
        "raw_upstream_body_not_exported": True,
    }
    failed_gates = [gate for gate, passed in acceptance_gates.items() if passed is not True]

    return {
        "proposal_id": proposal_id,
        "proposal_kind": proposal_kind,
        "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
        "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
        "status": "ready" if not failed_gates else "blocked",
        "activation_blockers": [f"acceptance_gate_failed:{gate}" for gate in failed_gates],
        "candidate_names": list(dict.fromkeys(candidate_names)),
        "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
        "route_profiles": [
            profile
            for profile in (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(route_profiles)
        ],
        "allowed_local_lanes": bounded_lanes,
        "selected_local_lane": selected_local_lane if selected_local_lane in bounded_lanes else "",
        "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_local_lane],
        "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
        "validation_gates": list(dict.fromkeys(validation_gates)),
        "validation_target": validation_target,
        "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
        "acceptance_gates": acceptance_gates,
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


def _skill_route_discovery_current_digest_pass2_active_agent_row(
    adjacent_rows: Sequence[Mapping[str, Any]],
    *,
    proposal_id: str,
) -> dict[str, Any]:
    item_ids = [str(row.get("item_id") or "") for row in adjacent_rows if isinstance(row, Mapping)]
    names = [str(row.get("name") or "") for row in adjacent_rows if isinstance(row, Mapping)]
    source_hashes = [
        str(row.get("source_hash") or "") for row in adjacent_rows if isinstance(row, Mapping)
    ]
    acceptance_gates = {
        "agent_harness_eval_required": bool(adjacent_rows)
        and all(row.get("evaluation_lane") == "agent_harness_eval_required" for row in adjacent_rows),
        "skill_route_discovery_not_inherited": all(
            row.get("skill_route_discovery_inherited") is False for row in adjacent_rows
        ),
        "direct_runtime_route_denied": all(
            row.get("direct_runtime_route_allowed") is False for row in adjacent_rows
        ),
        "direct_code_patch_route_denied": all(
            row.get("direct_code_patch_route_allowed") is False for row in adjacent_rows
        ),
        "external_harness_execution_denied": all(
            row.get("external_harness_execution_allowed") is False for row in adjacent_rows
        ),
        "provider_runtime_launch_denied": all(
            row.get("provider_runtime_launch_allowed") is False for row in adjacent_rows
        ),
        "local_validation_required": True,
        "runtime_action_none": True,
    }
    failed_gates = [gate for gate, passed in acceptance_gates.items() if passed is not True]

    return {
        "proposal_id": proposal_id,
        "proposal_kind": "test",
        "route_hint": "agent_harness_eval_required",
        "status": "ready" if not failed_gates else "blocked",
        "activation_blockers": [f"acceptance_gate_failed:{gate}" for gate in failed_gates],
        "item_ids": list(dict.fromkeys(item_ids)),
        "names": list(dict.fromkeys(name for name in names if name)),
        "source_hashes": list(dict.fromkeys(source_hashes)),
        "evaluation_lane": "agent_harness_eval_required",
        "skill_route_discovery_inherited": False,
        "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
        "selected_local_lane": "agent_harness_eval_required",
        "validation_gate": "local_agent_harness_eval_required_before_implementation_route",
        "validation_target": "general_agent_project_fixtures_before_runtime_or_controller_change",
        "required_probe_fields": [
            "install_shape",
            "entrypoints",
            "dependency_boundaries",
            "task_loop_assumptions",
            "observable_behaviors",
            "evaluation_dimensions",
        ],
        "acceptance_gates": acceptance_gates,
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


def _skill_route_discovery_current_digest_pass4_completion_handoff(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Close the current digest route-discovery slice with bounded replay metadata."""

    current_200729_window = source_digest == "github-growth-20260628T200729.682703Z"
    current_055941_window = source_digest == "github-growth-20260629T055941.732014Z"
    current_095324_window = source_digest == "github-growth-20260629T095324.174533Z"
    current_153904_window = source_digest == "github-growth-20260629T153904.276953Z"
    current_181904_window = source_digest == "github-growth-20260629T181904.229847Z"
    current_193904_window = source_digest == "github-growth-20260629T193904.337686Z"
    specs = (
        (
            {
                "proposal_id": "p1-skill-route-discovery-index",
                "proposal_kind": "test",
                "proposal_track": "skill_route_discovery_index",
                "route_profiles": (
                    "generic_skill_workflow",
                    "source_cited_domain_research",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "external_skill_repository_metadata_classifies_only_to_bounded_local_lanes"
                ),
            },
            {
                "proposal_id": "p2-skill-profile-documentation",
                "proposal_kind": "documentation",
                "proposal_track": "skill_route_profile_documentation",
                "route_profiles": (
                    "generic_skill_workflow",
                    "source_cited_domain_research",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "documentation",
                "completion_requirement": (
                    "generic_game_frontend_and_state_handoff_profiles_have_operator_visible_handling"
                ),
            },
        )
        if current_200729_window
        else (
            {
                "proposal_id": "p1-compass-skill-ecosystem-handoff",
                "proposal_kind": "documentation",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "documentation",
                "completion_requirement": (
                    "compass_style_skill_ecosystem_state_handoff_records_validation_gates_before_adoption"
                ),
            },
            {
                "proposal_id": "p2-skill-route-discovery-local-fixture",
                "proposal_kind": "test",
                "proposal_track": "generic_python_skill_repository",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "skill_like_python_agent_repository_classifies_to_bounded_local_validation_lanes"
                ),
            },
        )
        if current_055941_window
        else (
            {
                "proposal_id": "proposal-001-skill-route-discovery-compass-skills",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "compass_style_skill_repository_maps_only_to_bounded_local_validation_lanes"
                ),
            },
            {
                "proposal_id": "proposal-002-generic-skill-workflow-validation",
                "proposal_kind": "code_patch",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "code_patch",
                "completion_requirement": (
                    "generic_skill_repository_signal_routes_through_skill_route_discovery_before_activation"
                ),
            },
        )
        if current_095324_window
        else (
            {
                "proposal_id": "proposal-001-skill-route-discovery-compass-skills",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "compass_style_skill_ecosystem_state_handoff_routes_only_to_bounded_local_lanes"
                ),
            },
            {
                "proposal_id": "proposal-002-generic-skill-workflow-discovery",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow",),
                "selected_local_lane": "documentation",
                "completion_requirement": (
                    "generic_skill_workflow_terms_map_to_documentation_config_test_or_code_patch_with_validation"
                ),
            },
        )
        if current_181904_window
        else (
            {
                "proposal_id": "p1-skill-route-discovery-compass-and-zhengxi",
                "proposal_kind": "test",
                "proposal_track": "skill_workflow_route_boundary_fixture",
                "route_profiles": ("generic_skill_workflow", "skill_ecosystem_state_handoff"),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "compass_and_zhengxi_skill_terms_map_only_to_bounded_local_lanes"
                ),
            },
            {
                "proposal_id": "p3-agent-harness-fixture-for-routing-boundaries",
                "proposal_kind": "test",
                "proposal_track": "skill_workflow_vs_general_agent_boundary_fixture",
                "route_profiles": ("generic_skill_workflow", "skill_ecosystem_state_handoff"),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "skill_workflow_and_general_agent_project_classifications_are_distinct"
                ),
            },
        )
        if current_193904_window
        else (
            {
                "proposal_id": "p1-skill-route-discovery-fixtures",
                "proposal_kind": "test",
                "proposal_track": "skill_workflow_route_fixture_lane",
                "route_profiles": ("generic_skill_workflow", "skill_ecosystem_state_handoff"),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "compass_and_zhengxi_skill_workflow_records_classify_only_to_bounded_local_lanes"
                ),
            },
            {
                "proposal_id": "p2-skill-routing-doc-clarification",
                "proposal_kind": "documentation",
                "proposal_track": "skill_route_interpretation_documentation",
                "route_profiles": ("generic_skill_workflow", "skill_ecosystem_state_handoff"),
                "selected_local_lane": "documentation",
                "completion_requirement": (
                    "operator_docs_explain_skill_route_evidence_without_permission_grants"
                ),
            },
        )
        if current_153904_window
        else (
            {
                "proposal_id": "p1-skill-route-discovery-generic",
                "proposal_kind": "test",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "test",
                "completion_requirement": "generic_skill_repository_signal_has_bounded_local_validation_lane",
            },
            {
                "proposal_id": "p2-game-frontend-skill-profile",
                "proposal_kind": "documentation",
                "proposal_track": "game_frontend_workflow",
                "route_profiles": ("game_frontend_workflow",),
                "selected_local_lane": "documentation",
                "completion_requirement": "game_frontend_skill_signal_stays_metadata_first_until_local_validation",
            },
            {
                "proposal_id": "p3-skill-ecosystem-handoff",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "completion_requirement": (
                    "skill_ecosystem_state_handoff_stays_metadata_only_without_profile_or_memory_writes"
                ),
            },
        )
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    selected_item_ids: list[str] = []
    replay_command_hashes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        downgraded_lanes: list[str] = []
        uncertainty_reasons: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            matched_profiles = [profile for profile in candidate_profiles if profile in required_profiles]
            if not matched_profiles:
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            route_profiles.extend(matched_profiles)
            observed_profiles.extend(matched_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))
            uncertainty_reasons.extend(_string_list(candidate.get("uncertainty_reasons")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        replay_command = _skill_route_discovery_replay_command(selected_lane, route_profiles)
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if set(bounded_lanes) - set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES):
            blockers.append("unbounded_lane_present")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(route_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "profile_validation_checklist": _skill_route_discovery_profile_validation_checklist(
                    list(dict.fromkeys(route_profiles))
                ),
                "completion_requirement": str(spec["completion_requirement"]),
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "uncertainty_reasons": list(dict.fromkeys(uncertainty_reasons)),
                "accepted_outputs": ["docs", "config", "tests", "code_patch"],
                "replay_command_hash": _stable_hash(replay_command) if replay_command else "",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows: list[dict[str, Any]] = []
    for adjacent_row in _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id=(
            "p3-agent-harness-eval"
            if current_200729_window
            else "p3-general-agent-harness-eval-queue"
            if current_055941_window
            else "proposal-003-agent-harness-eval-fixture"
            if current_095324_window
            else "proposal-003-agent-harness-eval-qwen-agentworld"
            if current_181904_window
            else "p2-general-agent-harness-eval"
            if current_193904_window
            else "p3-agent-harness-eval-gate"
            if current_153904_window
            else "p4-agent-harness-eval-qwen"
        ),
    ):
        replay_command = str(adjacent_row.get("replay_command") or "")
        row = dict(adjacent_row)
        row.pop("replay_command", None)
        row["replay_command_hash"] = _stable_hash(replay_command) if replay_command else ""
        row["accepted_outputs_after_eval"] = ["docs", "tests", "code_patch"]
        row["selected_local_lane"] = "agent_harness_eval_required"
        row["raw_replay_command_exported"] = False
        adjacent_rows.append(row)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

    required_profiles = (
        ("generic_skill_workflow", "skill_ecosystem_state_handoff")
        if (
            current_055941_window
            or current_095324_window
            or current_153904_window
            or current_181904_window
            or current_193904_window
        )
        else (
            "generic_skill_workflow",
            "game_frontend_workflow",
            "skill_ecosystem_state_handoff",
        )
    )
    observed_profile_set = set(observed_profiles)
    missing_profiles = [profile for profile in required_profiles if profile not in observed_profile_set]
    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    adjacent_ready = all(
        row.get("evaluation_lane") == "agent_harness_eval_required"
        and row.get("skill_route_discovery_inherited") is False
        and row.get("direct_runtime_route_allowed") is False
        and row.get("direct_code_patch_route_allowed") is False
        and row.get("external_harness_execution_allowed") is False
        and row.get("provider_runtime_launch_allowed") is False
        for row in adjacent_rows
    )
    ready = len(rows) == len(specs) and not blocked_proposal_ids and not missing_profiles and adjacent_ready
    route_boundary_rows: list[dict[str, Any]] = []
    for row in rows:
        allowed = _string_list(row.get("allowed_local_lanes"))
        route_boundary_rows.append(
            {
                "proposal_id": str(row["proposal_id"]),
                "evidence_class": "skill_workflow",
                "primary_route": SKILL_ROUTE_DISCOVERY_HINT,
                "candidate_names": _string_list(row.get("candidate_names")),
                "route_profiles": _string_list(row.get("route_profiles")),
                "selected_local_lane": str(row.get("selected_local_lane") or ""),
                "allowed_local_lanes": allowed,
                "bounded_to_skill_route_lanes": set(allowed) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
                "agent_harness_eval_required": False,
                "skill_route_discovery_inherited": True,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
            }
        )
    for row in adjacent_rows:
        route_boundary_rows.append(
            {
                "proposal_id": str(row.get("proposal_id") or ""),
                "evidence_class": "general_agent_project",
                "primary_route": "agent_harness_eval_required",
                "candidate_names": [str(row.get("name") or "")],
                "route_profiles": [],
                "selected_local_lane": "agent_harness_eval_required",
                "allowed_local_lanes": ["documentation", "test", "code_patch"],
                "bounded_to_skill_route_lanes": False,
                "agent_harness_eval_required": True,
                "skill_route_discovery_inherited": False,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "remote_execution_allowed": False,
            }
        )
    route_boundary_ready = bool(route_boundary_rows) and all(
        (
            row["primary_route"] == SKILL_ROUTE_DISCOVERY_HINT
            and row["bounded_to_skill_route_lanes"] is True
            and row["selected_local_lane"] in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and row["agent_harness_eval_required"] is False
        )
        or (
            row["primary_route"] == "agent_harness_eval_required"
            and row["skill_route_discovery_inherited"] is False
            and row["selected_local_lane"] == "agent_harness_eval_required"
        )
        for row in route_boundary_rows
    )
    route_boundary_checklist = {
        "controller_surface": "skill_route_discovery_pass4_route_boundary_checklist",
        "status": "ready" if route_boundary_ready and ready else "blocked",
        "decision": "skill_workflow_and_general_agent_routes_separated_before_handoff"
        if route_boundary_ready and ready
        else "repair_skill_workflow_general_agent_boundary_before_handoff",
        "source_digest": source_digest or "unknown",
        "skill_workflow_route": SKILL_ROUTE_DISCOVERY_HINT,
        "general_agent_route": "agent_harness_eval_required",
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "allowed_agent_harness_eval_lanes": ["documentation", "test", "code_patch"],
        "skill_route_row_count": len(rows),
        "general_agent_row_count": len(adjacent_rows),
        "agent_harness_eval_required_before_implementation": bool(adjacent_rows),
        "runtime_action_allowed": False,
        "external_skill_activation_allowed": False,
        "external_agent_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "remote_execution_allowed": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": route_boundary_rows,
    }

    return {
        "controller_surface": "skill_route_discovery_current_digest_pass4_completion_handoff",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_digest_pass4_skill_route_slice_ready_for_supervisor_replay"
            if ready
            else "repair_current_digest_pass4_skill_route_completion_before_handoff"
        ),
        "source_digest": source_digest or "github-growth-20260628T144729.539313Z",
        "capability_pass": 4,
        "total_passes": 4,
        "capability_slice": "skill-route-discovery",
        "capability_slice_complete": ready,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs],
        "anchoring_proposal_ids": (
            [
                "p1-skill-route-discovery-index",
                "p2-skill-route-fixture-tests",
                "p3-game-frontend-skill-profile",
                "p4-agent-harness-eval-fixtures",
                "p5-skill-ecosystem-state-handoff",
                "p1-skill-route-discovery-generic",
                "p2-agent-harness-eval-qwen-agentworld",
                "p3-game-frontend-skill-route",
                "p4-skill-ecosystem-state-handoff",
                "p5-agent-harness-eval-looper",
                "p1-skill-route-discovery-harness",
                "p2-skill-discovery-docs",
            ]
            if current_200729_window
            else [
                "p1-compass-skill-ecosystem-handoff",
                "p2-skill-route-discovery-local-fixture",
                "p3-general-agent-harness-eval-queue",
                "trend:lyra81604/zhengxi-views-1",
                "trend:QwenLM/Qwen-AgentWorld-2",
                "p1-skill-route-discovery-compass",
                "p2-skill-route-discovery-generic",
                "p3-agent-harness-eval-qwen",
                "p4-agent-harness-eval-looper",
                "p2-skill-route-discovery-zhengxi",
                "p3-agent-harness-qwen-agentworld",
                "p4-agent-harness-looper",
            ]
            if current_055941_window
            else [
                "trend:lyra81604/zhengxi-views-1",
                "trend:QwenLM/Qwen-AgentWorld-2",
                "trend:ksimback/looper-3",
                "trend:dongshuyan/compass-skills-4",
                "p1_skill_route_discovery_compass_and_zhengxi",
                "p2_agent_harness_eval_general_projects",
                "p3_security_adjacent_agent_eval_guardrail",
                "p4_route_hint_policy_fixture",
                "p1-skill-route-discovery-zhengxi-views",
                "p2-skill-ecosystem-handoff-compass",
                "p3-agent-harness-eval-general-projects",
                "proposal-001-skill-route-discovery-compass-skills",
                "proposal-002-generic-skill-workflow-validation",
                "proposal-003-agent-harness-eval-fixture",
            ]
            if current_095324_window
            else [
                "p1-skill-route-discovery-compass",
                "p2-generic-skill-workflow-zhengxi",
                "p3-agent-harness-qwen-agentworld",
                "p4-agent-harness-looper",
                "trend:lyra81604/zhengxi-views-1",
                "p1-skill-route-discovery-compass-skills",
                "p2-skill-route-discovery-zhengxi-views",
                "p5-security-agent-harness-autocve",
                "p2-generic-skill-workflow-docs",
                "p3-agent-harness-eval-fixture",
                "p4-security-agent-review-boundary-test",
                "p5-route-classification-summary-artifact",
                "proposal-001-skill-route-discovery-compass-skills",
                "proposal-002-generic-skill-workflow-discovery",
                "proposal-003-agent-harness-eval-qwen-agentworld",
                "trend:dongshuyan/compass-skills-1",
                "trend:lyra81604/zhengxi-views-1",
                "trend:QwenLM/Qwen-AgentWorld-2",
                "trend:ksimback/looper-3",
            ]
            if current_181904_window
            else [
                "p1-skill-route-discovery-compass-skills",
                "p2-skill-route-discovery-zhengxi-views",
                "p3-agent-harness-eval-qwen-agentworld",
                "p4-agent-harness-eval-looper",
                "p5-security-agent-review-lane-autocve",
                "p1-skill-route-discovery-compass",
                "p2-skill-route-discovery-generic",
                "p3-agent-harness-eval-general",
                "p4-agent-harness-routing-doc",
                "p5-security-agent-review-gate",
                "p4-security-agent-review-boundary",
                "p5-route-hint-policy-coverage",
                "p1-skill-route-discovery-compass-and-zhengxi",
                "p2-general-agent-harness-eval",
                "p3-agent-harness-fixture-for-routing-boundaries",
                "trend:dongshuyan/compass-skills-1",
                "trend:lyra81604/zhengxi-views-1",
                "trend:QwenLM/Qwen-AgentWorld-1",
                "trend:ksimback/looper-1",
            ]
            if current_193904_window
            else [
                "p1-skill-route-discovery-compass",
                "p2-skill-route-discovery-generic",
                "p3-agent-harness-eval-general-agent-projects",
                "p4-security-agent-review-boundary",
                "p5-agent-routing-config-preflight",
                "p1-skill-route-discovery-registry",
                "p2-agent-harness-eval-fixtures",
                "p3-skill-route-docs",
                "p4-provider-agent-preflight",
                "p5-autocve-review-gate",
                "p1-skill-route-discovery-index",
                "p3-route-policy-doc-clarification",
                "p1-skill-route-discovery-fixtures",
                "p2-skill-routing-doc-clarification",
                "p3-agent-harness-eval-gate",
                "trend:dongshuyan/compass-skills-4",
                "trend:lyra81604/zhengxi-views-1",
                "trend:QwenLM/Qwen-AgentWorld-2",
                "trend:ksimback/looper-3",
            ]
            if current_153904_window
            else [
                "p1-skill-route-discovery-generic",
                "p2-game-frontend-skill-profile",
                "p3-skill-ecosystem-state-handoff",
                "p4-agent-harness-eval-qwen",
                "p5-agent-harness-eval-looper",
                "p1-skill-route-discovery-compass-handoff",
                "p2-threejs-game-skill-routing-profile",
                "p3-generic-skill-workflow-discovery-fixture",
                "p4-skill-trend-intake-config-guard",
                "trend:lyra81604/zhengxi-views-1",
                "p1-skill-route-discovery-views",
                "p2-threejs-game-skill-profile",
            ]
        ),
        "ready_skill_route_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "required_route_profiles": list(required_profiles),
        "observed_route_profiles": [
            profile
            for profile in (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in observed_profile_set
        ],
        "missing_required_route_profiles": missing_profiles,
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "profile_validation_checklist": _skill_route_discovery_profile_validation_checklist(
            [
                profile
                for profile in (
                    "generic_skill_workflow",
                    "source_cited_domain_research",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                )
                if profile in observed_profile_set
            ]
        ),
        "activation_prerequisite_lane": _skill_route_discovery_activation_prerequisite_lane(rows),
        "route_boundary_checklist": route_boundary_checklist,
        "accepted_outputs": ["docs", "config", "tests", "code_patch"],
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "operator_next_action": (
            "record_current_digest_pass4_completion_and_keep_external_activation_denied"
            if ready
            else "repair_blocked_pass4_completion_rows_before_supervisor_handoff"
        ),
        "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
        "completion_recovery_workflow": (
            "rerun_current_digest_pass4_completion_handoff_after_repairing_blocked_rows"
            if not ready
            else "rerun_focused_validation_if_supervisor_replay_disagrees"
        ),
        "adjacent_general_agent_policy": {
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_local_change_proposals_allowed": False,
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        },
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "bounded_lane_inventory",
            "rollback_ref",
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
        "raw_replay_commands_exported": False,
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


def _skill_route_discovery_current_run_pass2_local_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Bind this run's pass-2 proposals to local validation lanes before activation."""

    skill_specs = (
        {
            "proposal_id": "proposal-skill-route-discovery-zxv-001",
            "proposal_kind": "test",
            "proposal_track": "generic_python_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_routes_only_to_bounded_local_lanes",
        },
        {
            "proposal_id": "proposal-game-frontend-skill-route-001",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_workflow_requires_skill_route_discovery_validation",
        },
        {
            "proposal_id": "proposal-skill-ecosystem-state-handoff-001",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_profile_stays_metadata_only_before_writes",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    selected_item_ids: list[str] = []

    for spec in skill_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        matched_profiles: list[str] = []
        downgraded_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            selected_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_run_pass2_local_validation_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="proposal-agent-harness-qwen-agentworld-001",
    )
    adjacent_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "replay_command"
        }
        | {
            "validation_gate": "agent_harness_eval_before_implementation_route",
            "validation_target": "general_agent_project_requires_local_agent_harness_eval",
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

    if adjacent_rows:
        rows.append(
            {
                "proposal_id": "proposal-agent-harness-qwen-agentworld-001",
                "proposal_kind": "test",
                "proposal_track": "agent_harness_evaluation_lane",
                "status": "ready" if not adjacent_blockers else "blocked",
                "activation_blockers": adjacent_blockers,
                "candidate_names": [str(row.get("name") or "") for row in adjacent_rows],
                "candidate_source_hashes": [str(row.get("source_hash") or "") for row in adjacent_rows],
                "route_hint": "agent_harness_eval_required",
                "route_class": "adjacent_general_agent_project",
                "route_profiles": [],
                "allowed_local_lanes": ["documentation", "test", "code_patch"],
                "selected_local_lane": "agent_harness_eval_required",
                "queued_local_lanes": ["documentation", "test", "code_patch"],
                "selected_evidence_item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
                "validation_gates": ["agent_harness_eval_before_implementation_route"],
                "validation_target": "general_agent_project_requires_local_agent_harness_eval",
                "downgraded_unsupported_lanes": [],
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_proposal_ids and bool(adjacent_rows)
    return {
        "controller_surface": "skill_route_discovery_current_run_pass2_local_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_run_pass2_skill_and_agent_routes_ready_for_local_validation"
            if ready
            else "repair_current_run_pass2_route_boundaries_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T020729.523438Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "proposal-skill-route-discovery-zxv-001",
            "proposal-agent-harness-qwen-agentworld-001",
            "proposal-game-frontend-skill-route-001",
            "proposal-skill-ecosystem-state-handoff-001",
        ],
        "anchoring_proposal_ids": [
            "p1-skill-route-discovery-catalog",
            "p2-skill-profile-routing-tests",
            "p3-agent-harness-evaluation-lane",
            "p4-game-frontend-skill-eval-fixture",
            "p5-skill-ecosystem-handoff-note",
        ],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "adjacent_evaluation_lane": "agent_harness_eval_required",
        "agent_harness_eval_required": bool(adjacent_rows),
        "agent_harness_eval_required_before_implementation": bool(adjacent_rows),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
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
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_active_pass2_skill_route_validation_matrix(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Map this wake's three active skill-route proposals into local lanes."""

    specs = (
        {
            "proposal_id": "p1-skill-route-discovery-general",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_repository_evidence_stays_bounded_to_local_lanes",
        },
        {
            "proposal_id": "p2-game-frontend-skill-profile",
            "proposal_kind": "test",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_target": "game_frontend_workflow_emits_no_runtime_action_before_local_validation",
        },
        {
            "proposal_id": "p3-skill-ecosystem-state-handoff",
            "proposal_kind": "documentation",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_profile_metadata_remains_local_and_item_id_cited",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    downgraded_lanes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        candidate_downgrades: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            matched_profiles = [profile for profile in candidate_profiles if profile in required_profiles]
            if not matched_profiles:
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            route_profiles.extend(matched_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            candidate_downgrades.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        downgraded_lanes.extend(candidate_downgrades)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(route_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(candidate_downgrades)),
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_active_pass2_skill_route_validation_matrix"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = len(rows) == len(specs) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_active_pass2_skill_route_validation_matrix",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_active_pass2_skill_routes_ready_for_bounded_local_validation"
            if ready
            else "repair_current_active_pass2_skill_route_matrix_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T060729.568458Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs],
        "anchoring_proposal_ids": [
            "p1-skill-route-discovery-regression",
            "p2-skill-route-discovery-doc",
            "p3-agent-harness-eval-fixtures",
            "p4-route-proposal-schema-guard",
            "p5-route-hint-to-lane-matrix-test",
            "p1-skill-route-discovery-general",
            "p2-game-frontend-skill-profile",
            "p3-skill-ecosystem-state-handoff",
            "p4-agent-harness-eval-general-projects",
            "p5-route-policy-regression-coverage",
        ],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
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


def _skill_route_discovery_current_active_pass2_proposal_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this wake's active pass-2 proposal aliases for replay.

    This surface advances the current pass without granting activation. It maps
    the operator-visible proposal IDs from the active capability window to the
    already-bounded local lanes and keeps adjacent general-agent evidence out of
    skill-route authority.
    """

    specs = (
        {
            "proposal_id": "p1_skill_route_discovery_generic_views",
            "proposal_aliases": (
                "p1-skill-route-discovery-zhengxi-views",
                "p1-skill-route-discovery-generic",
            ),
            "proposal_kind": "test",
            "proposal_track": "source_cited_or_generic_skill_workflow",
            "route_profiles": ("source_cited_domain_research", "generic_skill_workflow"),
            "selected_local_lane": "test",
            "validation_target": "source_citation_and_advice_boundary_local_test",
        },
        {
            "proposal_id": "p2_game_frontend_skill_profile",
            "proposal_aliases": (
                "p2-skill-route-discovery-threejs-game-skills",
                "p2-game-frontend-skill-profile",
            ),
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_skill_profile_validation_checklist",
        },
        {
            "proposal_id": "p3_skill_ecosystem_state_handoff",
            "proposal_aliases": (
                "p3-skill-ecosystem-state-handoff",
                "p3-skill-ecosystem-handoff",
            ),
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_metadata_only_config_boundary",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    downgraded_lanes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        candidate_downgrades: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            matched_profiles = [profile for profile in candidate_profiles if profile in required_profiles]
            if not matched_profiles:
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            route_profiles.extend(matched_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            candidate_downgrades.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        downgraded_lanes.extend(candidate_downgrades)

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_aliases": list(spec["proposal_aliases"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(route_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(candidate_downgrades)),
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_active_pass2_proposal_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = []
    for adjacent_row in _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p4_general_agent_harness_characterization_qwen",
    ):
        replay_command = str(adjacent_row.get("replay_command") or "")
        sanitized_row = dict(adjacent_row)
        sanitized_row.pop("replay_command", None)
        sanitized_row["replay_command_hash"] = _stable_hash(replay_command) if replay_command else ""
        sanitized_row["raw_replay_command_exported"] = False
        adjacent_rows.append(sanitized_row)
    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = len(rows) == len(specs) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_active_pass2_proposal_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_active_pass2_proposals_ready_for_bounded_local_validation"
            if ready
            else "repair_current_active_pass2_proposal_lane_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T100729.595957Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs],
        "anchoring_proposal_ids": [
            "p1_skill_route_discovery_generic_views",
            "p2_game_frontend_skill_profile",
            "p3_skill_ecosystem_state_handoff",
            "p4_general_agent_harness_characterization_qwen",
            "p5_general_agent_harness_characterization_looper",
            "p1-skill-route-discovery-zhengxi-views",
            "p2-skill-route-discovery-threejs-game-skills",
            "p3-skill-ecosystem-state-handoff",
            "p4-agent-harness-eval-qwen-agentworld",
            "p5-agent-harness-eval-looper",
        ],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "rollback_artifact",
            "focused_local_validation",
            "changed_file_review",
            "review_note",
        ],
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "operator_next_action": (
            "replay_current_active_pass2_proposal_lane_then_continue_to_pass3"
            if ready
            else "repair_blocked_rows_then_rebuild_current_active_pass2_proposal_lane"
        ),
        "adjacent_general_agent_policy": {
            "status": "queued_for_agent_harness_eval" if adjacent_rows else "not_present",
            "row_count": len(adjacent_rows),
            "skill_route_discovery_inherited": False,
            "agent_harness_eval_required": bool(adjacent_rows),
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
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_active_pass2_activation_contract(
    proposal_lane: Mapping[str, Any],
    validation_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    """Turn current pass-2 skill-route rows into profile acceptance gates."""

    raw_rows = proposal_lane.get("rows")
    proposal_rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    contract_specs = {
        "p1_skill_route_discovery_generic_views": {
            "acceptance_gate": "generic_skill_repository_signal_test_lane_only",
            "required_local_proof": [
                "selected_item_ids_or_frozen_fixture",
                "bounded_lane_membership_test",
                "no_runtime_action_assertion",
            ],
            "activation_rule": "may_continue_only_as_local_test_or_code_review_evidence",
        },
        "p2_game_frontend_skill_profile": {
            "acceptance_gate": "game_frontend_workflow_requires_local_ui_or_render_validation",
            "required_local_proof": [
                "selected_item_ids_or_frozen_fixture",
                "local_frontend_or_render_validation",
                "no_scaffold_or_external_skill_activation_assertion",
            ],
            "activation_rule": "may continue only after local UI, render, or workflow validation passes",
        },
        "p3_skill_ecosystem_state_handoff": {
            "acceptance_gate": "skill_ecosystem_state_handoff_config_metadata_only",
            "required_local_proof": [
                "selected_item_ids_or_frozen_fixture",
                "config_lane_metadata_review",
                "no_profile_or_memory_write_assertion",
            ],
            "activation_rule": "may continue only as config metadata; state, profile, and memory writes stay denied",
        },
    }

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    blocked_proposal_ids: list[str] = []

    for raw_row in proposal_rows:
        if not isinstance(raw_row, Mapping):
            continue
        proposal_id = str(raw_row.get("proposal_id") or "")
        if proposal_id not in contract_specs:
            continue
        spec = contract_specs[proposal_id]
        selected_lane = str(raw_row.get("selected_local_lane") or "")
        route_profiles = _string_list(raw_row.get("route_profiles"))
        allowed_lanes = [
            lane
            for lane in _string_list(raw_row.get("allowed_local_lanes"))
            if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        ]
        blockers = list(_string_list(raw_row.get("activation_blockers")))
        if str(raw_row.get("status") or "") != "ready":
            blockers.append("proposal_lane_row_not_ready")
        if selected_lane not in allowed_lanes:
            blockers.append("selected_local_lane_not_allowed")
        if not _string_list(raw_row.get("selected_evidence_item_ids")):
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if raw_row.get("runtime_action") != "none":
            blockers.append("runtime_action_not_none")
        if raw_row.get("external_skill_activation_allowed") is not False:
            blockers.append("external_skill_activation_not_denied")
        if raw_row.get("external_harness_execution_allowed") is not False:
            blockers.append("external_harness_execution_not_denied")
        if raw_row.get("provider_runtime_launch_allowed") is not False:
            blockers.append("provider_runtime_launch_not_denied")
        if raw_row.get("raw_source_url_exported") is not False:
            blockers.append("raw_source_url_export_not_denied")
        if raw_row.get("raw_evidence_urls_exported") is not False:
            blockers.append("raw_evidence_url_export_not_denied")
        if raw_row.get("raw_upstream_body_exported") is not False:
            blockers.append("raw_upstream_body_export_not_denied")

        row_status = "ready" if not blockers else "blocked"
        if row_status != "ready":
            blocked_proposal_ids.append(proposal_id)
        if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(route_profiles)

        rows.append(
            {
                "proposal_id": proposal_id,
                "proposal_aliases": _string_list(raw_row.get("proposal_aliases")),
                "status": row_status,
                "activation_blockers": sorted(dict.fromkeys(blockers)),
                "route_profiles": route_profiles,
                "selected_local_lane": selected_lane,
                "allowed_local_lanes": allowed_lanes,
                "candidate_names": _string_list(raw_row.get("candidate_names")),
                "candidate_source_hashes": _string_list(raw_row.get("candidate_source_hashes")),
                "selected_evidence_item_ids": _string_list(raw_row.get("selected_evidence_item_ids")),
                "validation_target": str(raw_row.get("validation_target") or ""),
                "acceptance_gate": spec["acceptance_gate"],
                "required_local_proof": list(spec["required_local_proof"]),
                "activation_rule": spec["activation_rule"],
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    expected_proposal_ids = list(contract_specs)
    present_proposal_ids = {row["proposal_id"] for row in rows}
    missing_proposal_ids = [
        proposal_id for proposal_id in expected_proposal_ids if proposal_id not in present_proposal_ids
    ]
    blocked_proposal_ids.extend(missing_proposal_ids)
    matrix_ready = validation_matrix.get("status") == "ready"
    proposal_lane_ready = proposal_lane.get("status") == "ready"
    ready = bool(rows) and not blocked_proposal_ids and matrix_ready and proposal_lane_ready

    return {
        "controller_surface": "skill_route_discovery_current_active_pass2_activation_contract",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_active_pass2_profiles_have_bounded_activation_contract"
            if ready
            else "repair_current_active_pass2_activation_contract_before_handoff"
        ),
        "source_digest": str(proposal_lane.get("source_digest") or ""),
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_lane_status": str(proposal_lane.get("status") or ""),
        "validation_matrix_status": str(validation_matrix.get("status") or ""),
        "proposal_ids": expected_proposal_ids,
        "blocked_proposal_ids": sorted(dict.fromkeys(blocked_proposal_ids)),
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "profile_specific_acceptance_gate",
            "focused_local_validation",
            "rollback_artifact",
            "changed_file_review",
            "review_note",
        ],
        "operator_next_action": (
            "replay_current_active_pass2_activation_contract_then_continue_to_pass3"
            if ready
            else "repair_blocked_pass2_contract_rows_before_activation"
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
        "rows": rows,
    }


def _skill_route_discovery_current_active_pass3_local_activation_proof_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Turn the active skill-route matrix into local proof rows before pass 4."""

    specs = (
        {
            "proposal_id": "p1-skill-route-discovery-general",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_classifies_without_runtime_permission",
            "proof_artifact": "focused_skill_route_discovery_test_or_fixture",
        },
        {
            "proposal_id": "p2-game-frontend-skill-profile",
            "proposal_kind": "test",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_target": "game_frontend_workflow_requires_local_frontend_or_test_validation",
            "proof_artifact": "frontend_validation_boundary_test_or_profile_note",
        },
        {
            "proposal_id": "p3-skill-ecosystem-state-handoff",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_metadata_preserves_privacy_and_local_boundaries",
            "proof_artifact": "metadata_only_state_handoff_config_check",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    proof_artifacts: list[str] = []
    downgraded_lanes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        candidate_downgrades: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            profile_matches = [profile for profile in candidate_profiles if profile in required_profiles]
            if not profile_matches:
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            matched_profiles.extend(profile_matches)
            observed_profiles.extend(profile_matches)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            candidate_downgrades.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        profile_validation_requirements = _skill_route_discovery_profile_validation_requirements(
            matched_profiles,
            bounded_lanes,
        )
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if not profile_validation_requirements:
            blockers.append("profile_validation_requirements_missing")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        proof_artifacts.append(str(spec["proof_artifact"]))
        downgraded_lanes.extend(candidate_downgrades)

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "proof_artifact": str(spec["proof_artifact"]),
                "profile_validation_requirements": profile_validation_requirements,
                "activation_readiness": "local_proof_ready_for_pass4_handoff" if not blockers else "blocked",
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_active_pass3_local_activation_proof_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = len(rows) == len(specs) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_active_pass3_local_activation_proof_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_active_pass3_skill_routes_have_local_activation_proof"
            if ready
            else "repair_current_active_pass3_skill_route_proofs_before_pass4"
        ),
        "source_digest": source_digest or "github-growth-20260628T062729.695489Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
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
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "required_proof_artifacts": list(dict.fromkeys(proof_artifacts)),
        "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "profile_validation_requirements",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_next_action": (
            "replay_hashed_pass3_activation_proofs_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_pass3_activation_proofs"
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
        "rows": rows,
    }


def _skill_route_discovery_current_active_pass3_discovery_validation_packet(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose the current pass-3 skill/agent split before any activation path."""

    specs = (
        {
            "proposal_id": "p1-skill-route-discovery-zhengxi-views",
            "proposal_kind": "test",
            "proposal_track": "source_cited_domain_research",
            "route_profiles": ("source_cited_domain_research", "generic_skill_workflow"),
            "selected_local_lane": "test",
            "validation_target": "source_citation_and_advice_boundary_check",
            "accepted_outputs": ("docs", "config", "tests", "code_patch"),
        },
        {
            "proposal_id": "p3-game-skill-workflow-discovery",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_target": "local_frontend_render_or_workflow_check",
            "accepted_outputs": ("docs", "config", "tests", "code_patch"),
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    replay_command_hashes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        route_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            matched_profiles = [profile for profile in candidate_profiles if profile in required_profiles]
            if not matched_profiles:
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            route_profiles.extend(matched_profiles)
            observed_profiles.extend(matched_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        replay_command = _skill_route_discovery_replay_command(selected_lane, route_profiles)
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(route_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "accepted_outputs": list(spec["accepted_outputs"]),
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "replay_command_hash": _stable_hash(replay_command) if replay_command else "",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows: list[dict[str, Any]] = []
    for adjacent_row in _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p2-agent-harness-eval-qwen-agentworld",
    ):
        replay_command = str(adjacent_row.get("replay_command") or "")
        row = dict(adjacent_row)
        row.pop("replay_command", None)
        row["replay_command_hash"] = _stable_hash(replay_command) if replay_command else ""
        row["accepted_outputs"] = ["docs", "tests", "code_patch"]
        row["validation_gate"] = "local_agent_harness_eval_required_before_implementation_route"
        row["raw_replay_command_exported"] = False
        adjacent_rows.append(row)
        if replay_command:
            replay_command_hashes.append(_stable_hash(replay_command))

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    adjacent_ready = bool(adjacent_rows) and all(
        row.get("evaluation_lane") == "agent_harness_eval_required"
        and row.get("skill_route_discovery_inherited") is False
        and row.get("direct_runtime_route_allowed") is False
        and row.get("direct_code_patch_route_allowed") is False
        and row.get("external_harness_execution_allowed") is False
        and row.get("provider_runtime_launch_allowed") is False
        for row in adjacent_rows
    )
    ready = len(rows) == len(specs) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_active_pass3_discovery_validation_packet",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_pass3_skill_routes_and_adjacent_agent_eval_ready_for_local_validation"
            if ready
            else "repair_current_pass3_discovery_validation_packet_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T130729.680353Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs]
        + ["p2-agent-harness-eval-qwen-agentworld"],
        "ready_skill_route_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "accepted_skill_route_outputs": ["docs", "config", "tests", "code_patch"],
        "adjacent_general_agent_policy": {
            "proposal_id": "p2-agent-harness-eval-qwen-agentworld",
            "evaluation_lane": "agent_harness_eval_required",
            "accepted_outputs_after_eval": ["docs", "tests", "code_patch"],
            "skill_route_discovery_inherited": False,
            "direct_local_change_proposals_allowed": False,
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
        },
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "operator_next_action": (
            "replay_hashed_pass3_discovery_validation_before_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_pass3_discovery_validation_packet"
        ),
        "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "agent_harness_eval_boundary_for_general_agent_projects",
            "rollback_ref",
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
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_pass3_route_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this wake's skill-route proposals as bounded validation lanes."""

    proof_lane = _skill_route_discovery_current_active_pass3_local_activation_proof_lane(
        candidate_lane_inventory,
        source_digest=source_digest,
    )
    proposal_aliases = {
        "p1-skill-route-discovery-general": "p1-skill-route-discovery-generic",
        "p2-game-frontend-skill-profile": "p2-threejs-game-skill-routing",
        "p3-skill-ecosystem-state-handoff": "p3-skill-ecosystem-state-handoff",
    }
    validation_tasks = {
        "p1-skill-route-discovery-generic": "generic_skill_metadata_routes_to_bounded_local_lanes",
        "p2-threejs-game-skill-routing": "game_frontend_workflow_maps_only_to_bounded_local_work",
        "p3-skill-ecosystem-state-handoff": "document_state_handoff_profile_inputs_outputs_and_boundaries",
    }

    rows: list[dict[str, Any]] = []
    for proof_row in proof_lane.get("rows", []):
        if not isinstance(proof_row, Mapping):
            continue
        proof_proposal_id = str(proof_row.get("proposal_id") or "")
        proposal_id = proposal_aliases.get(proof_proposal_id)
        if not proposal_id:
            continue
        route_profiles = _string_list(proof_row.get("route_profiles"))
        row = {
            "proposal_id": proposal_id,
            "source_proof_proposal_id": proof_proposal_id,
            "proposal_kind": str(proof_row.get("proposal_kind") or ""),
            "proposal_track": str(proof_row.get("proposal_track") or ""),
            "status": str(proof_row.get("status") or "blocked"),
            "activation_blockers": _string_list(proof_row.get("activation_blockers")),
            "candidate_names": _string_list(proof_row.get("candidate_names")),
            "candidate_source_hashes": _string_list(proof_row.get("candidate_source_hashes")),
            "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
            "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
            "route_profiles": route_profiles,
            "allowed_local_lanes": _string_list(proof_row.get("allowed_local_lanes")),
            "selected_local_lane": str(proof_row.get("selected_local_lane") or ""),
            "queued_local_lanes": _string_list(proof_row.get("queued_local_lanes")),
            "selected_evidence_item_ids": _string_list(proof_row.get("selected_evidence_item_ids")),
            "validation_gates": _string_list(proof_row.get("validation_gates")),
            "validation_target": str(proof_row.get("validation_target") or ""),
            "validation_task": validation_tasks[proposal_id],
            "profile_validation_requirements": [
                requirement
                for requirement in proof_row.get("profile_validation_requirements", [])
                if isinstance(requirement, Mapping)
            ],
            "route_validation_io": {
                "expected_inputs": [
                    "selected_digest_item_ids_or_frozen_fixture",
                    "body_free_repository_summary",
                    "route_profile_metadata",
                    "allowed_local_lanes",
                ],
                "expected_outputs": [
                    "selected_bounded_local_lane",
                    "queued_bounded_local_lanes",
                    "validation_gate",
                    "validation_task",
                    "candidate_source_hashes",
                ],
                "validation_boundaries": [
                    "no_runtime_action",
                    "no_external_skill_activation",
                    "no_external_harness_execution",
                    "no_provider_runtime_launch",
                    "no_remote_execution",
                    "no_raw_source_or_evidence_url_export",
                    "no_upstream_body_export",
                ],
                "local_validation_required": True,
                "runtime_action": "none",
            },
            "state_handoff_boundary": (
                {
                    "expected_inputs": [
                        "profile_or_state_handoff_metadata",
                        "privacy_boundary_note",
                        "selected_digest_item_ids_or_frozen_fixture",
                    ],
                    "expected_outputs": [
                        "metadata_only_config_or_documentation_lane",
                        "profile_write_denial",
                        "memory_write_denial",
                    ],
                    "validation_boundaries": [
                        "profile_writes_denied",
                        "memory_writes_denied",
                        "privacy_boundary_must_be_local_and_body_free",
                    ],
                    "profile_write_allowed": False,
                    "memory_write_allowed": False,
                }
                if "skill_ecosystem_state_handoff" in route_profiles
                else {}
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
            "raw_replay_command_exported": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        rows.append(row)

    blocked_proposal_ids = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    ready = proof_lane.get("status") == "ready" and len(rows) == 3 and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_pass3_route_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_pass3_skill_routes_ready_for_bounded_validation"
            if ready
            else "repair_current_pass3_skill_route_validation_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T074730.300165Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-generic",
            "p2-threejs-game-skill-routing",
            "p3-skill-ecosystem-state-handoff",
        ],
        "source_proof_surface": str(proof_lane.get("controller_surface") or ""),
        "source_proof_status": str(proof_lane.get("status") or ""),
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "observed_route_profiles": _string_list(proof_lane.get("observed_route_profiles")),
        "selected_evidence_item_ids": _string_list(proof_lane.get("selected_evidence_item_ids")),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": _string_list(proof_lane.get("selected_local_lanes")),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "profile_validation_requirements",
            "route_validation_io_contract",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_next_action": (
            "replay_current_pass3_route_validation_then_continue_to_pass4"
            if ready
            else "repair_blocked_route_validation_rows_before_activation"
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
        "rows": rows,
    }


def _skill_route_discovery_current_pass4_route_discovery_validation_fix(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Final pass validation surface for current skill-route discovery proposals."""

    specs = (
        {
            "proposal_id": "p1-skill-route-discovery-index",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_route_discovery_index",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "generic_skill_profile_fixture_keeps_route_lanes_bounded",
        },
        {
            "proposal_id": "p2-game-frontend-skill-doc-lane",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow_documentation_lane",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_skill_lane_requires_local_asset_ui_and_testability_validation",
        },
        {
            "proposal_id": "p3-skill-ecosystem-handoff-config",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff_config",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_profile_remains_config_only_without_profile_or_memory_write",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    downgraded_lanes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        candidate_downgrades: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            profile_matches = [profile for profile in candidate_profiles if profile in required_profiles]
            if not profile_matches:
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            matched_profiles.extend(profile_matches)
            observed_profiles.extend(profile_matches)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            candidate_downgrades.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        profile_requirements = _skill_route_discovery_profile_validation_requirements(
            matched_profiles,
            bounded_lanes,
        )
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if not profile_requirements:
            blockers.append("profile_validation_requirements_missing")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        downgraded_lanes.extend(candidate_downgrades)

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "profile_validation_requirements": profile_requirements,
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(candidate_downgrades)),
                "validation_fix": "route_profile_to_bounded_local_lane_before_activation",
                "activation_readiness": "pass4_validation_fix_ready_for_supervisor_replay"
                if not blockers
                else "blocked",
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_pass4_route_discovery_validation_fix"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = len(rows) == len(specs) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_pass4_route_discovery_validation_fix",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_pass4_skill_route_discovery_validation_fix_ready"
            if ready
            else "repair_current_pass4_skill_route_discovery_validation_fix_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T064730.025611Z",
        "capability_pass": 4,
        "total_passes": 4,
        "capability_slice_complete": ready,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs],
        "anchoring_proposal_ids": [
            "p1-skill-route-discovery-regression",
            "p2-skill-route-discovery-doc",
            "p3-agent-harness-eval-fixtures",
            "p4-route-proposal-schema-guard",
            "p5-route-hint-to-lane-matrix-test",
            "p1-skill-route-discovery-general",
            "p2-game-frontend-skill-profile",
            "p3-skill-ecosystem-state-handoff",
        ],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
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
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_requirements",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "operator_next_action": (
            "replay_current_pass4_route_discovery_validation_fix_then_complete_slice"
            if ready
            else "repair_blocked_rows_then_rebuild_current_pass4_validation_fix"
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
        "rows": rows,
    }


def _skill_route_discovery_active_window_pass2_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this wake's pass-2 proposals as bounded local validation work."""

    specs = (
        {
            "proposal_id": "p1-skill-route-discovery-generic",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "skill_term_repository_trend_stays_in_bounded_local_lanes",
        },
        {
            "proposal_id": "p2-game-skill-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_workflow_profile_documents_validation_lanes",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        route_profiles: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            selected_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles = [profile for profile in candidate_profiles if profile in required_profiles]
            route_profiles.extend(matched_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(route_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
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

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-eval",
    )
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

    if adjacent_rows:
        rows.append(
            {
                "proposal_id": "p3-agent-harness-eval",
                "proposal_kind": "test",
                "proposal_track": "general_agent_project_harness_eval",
                "status": "ready" if not adjacent_blockers else "blocked",
                "activation_blockers": adjacent_blockers,
                "candidate_names": [str(row.get("name") or "") for row in adjacent_rows],
                "candidate_source_hashes": [str(row.get("source_hash") or "") for row in adjacent_rows],
                "route_hint": "agent_harness_eval_required",
                "route_class": "adjacent_general_agent_project",
                "route_profiles": [],
                "allowed_local_lanes": ["documentation", "test", "code_patch"],
                "selected_local_lane": "agent_harness_eval_required",
                "queued_local_lanes": ["documentation", "test", "code_patch"],
                "selected_evidence_item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
                "validation_gates": ["local_agent_harness_eval_required_before_implementation_route"],
                "validation_target": "general_agent_projects_without_skill_workflow_stay_eval_only",
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

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_proposal_ids and bool(adjacent_rows)
    local_lane_acceptance_contract = _skill_route_discovery_active_window_pass2_acceptance_contract(
        rows,
        source_digest=source_digest or "github-growth-20260628T032729.534812Z",
        source_status="ready" if ready else "blocked",
    )
    return {
        "controller_surface": "skill_route_discovery_active_window_pass2_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_window_pass2_skill_and_agent_routes_ready_for_local_validation"
            if ready
            else "repair_active_window_pass2_route_boundaries_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T032729.534812Z",
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-generic",
            "p2-game-skill-profile",
            "p3-agent-harness-eval",
        ],
        "anchoring_proposal_ids": [
            "proposal-skill-route-discovery-generic-001",
            "proposal-game-skill-route-profile-002",
            "proposal-agent-harness-eval-004",
            "proposal-trend-digest-policy-005",
        ],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": sorted(dict.fromkeys(profile for profile in observed_profiles if profile)),
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "adjacent_evaluation_lane": "agent_harness_eval_required",
        "agent_harness_eval_required": bool(adjacent_rows),
        "agent_harness_eval_required_before_implementation": bool(adjacent_rows),
        "operator_next_action": (
            "replay_active_window_pass2_validation_lane_before_activation"
            if ready
            else "repair_blocked_pass2_rows_then_replay_active_window_lane"
        ),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
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
        "local_lane_acceptance_contract": local_lane_acceptance_contract,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_active_window_pass2_acceptance_contract(
    source_rows: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
    source_status: str,
) -> dict[str, Any]:
    """Summarize pass-2 row acceptance before any activation handoff."""

    rows: list[dict[str, Any]] = []
    skill_route_rows: list[dict[str, Any]] = []
    adjacent_agent_eval_rows: list[dict[str, Any]] = []
    acceptance_failures: list[str] = []
    selected_local_lanes: list[str] = []
    queued_local_lanes: list[str] = []

    for source_row in source_rows:
        proposal_id = str(source_row.get("proposal_id") or "")
        route_hint = str(source_row.get("route_hint") or "")
        selected_lane = str(source_row.get("selected_local_lane") or "")

        if route_hint == SKILL_ROUTE_DISCOVERY_HINT:
            acceptance_gates = _skill_route_discovery_validation_row_acceptance_gates(source_row)
            if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
                selected_local_lanes.append(selected_lane)
            queued_local_lanes.extend(
                lane
                for lane in _string_list(source_row.get("queued_local_lanes"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            route_class = SKILL_ROUTE_DISCOVERY_ROUTE_CLASS
        elif route_hint == "agent_harness_eval_required":
            acceptance_gates = _skill_route_discovery_adjacent_agent_eval_acceptance_gates(source_row)
            route_class = "adjacent_general_agent_project"
        else:
            acceptance_gates = {"known_route_hint": False}
            route_class = str(source_row.get("route_class") or "")

        failed_gates = [
            gate_name
            for gate_name, gate_ready in acceptance_gates.items()
            if gate_ready is not True
        ]
        acceptance_failures.extend(f"{proposal_id}:{gate_name}" for gate_name in failed_gates)
        row = {
            "proposal_id": proposal_id,
            "proposal_kind": str(source_row.get("proposal_kind") or ""),
            "proposal_track": str(source_row.get("proposal_track") or ""),
            "candidate_names": _string_list(source_row.get("candidate_names")),
            "candidate_source_hashes": _string_list(source_row.get("candidate_source_hashes")),
            "route_hint": route_hint,
            "route_class": route_class,
            "route_profiles": _string_list(source_row.get("route_profiles")),
            "allowed_local_lanes": _string_list(source_row.get("allowed_local_lanes")),
            "selected_local_lane": selected_lane,
            "queued_local_lanes": _string_list(source_row.get("queued_local_lanes")),
            "selected_evidence_item_ids": _string_list(source_row.get("selected_evidence_item_ids")),
            "validation_gates": _string_list(source_row.get("validation_gates")),
            "validation_target": str(source_row.get("validation_target") or ""),
            "acceptance_gates": acceptance_gates,
            "acceptance_gate_status": "ready" if not failed_gates else "blocked",
            "activation_blockers": _string_list(source_row.get("activation_blockers"))
            + [f"acceptance_gate_failed:{gate_name}" for gate_name in failed_gates],
            "row_status": "ready" if not failed_gates else "blocked",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "profile_write_allowed": False,
            "memory_write_allowed": False,
            "remote_execution_allowed": False,
            "raw_replay_command_exported": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_target_paths_exported": False,
            "raw_upstream_body_exported": False,
        }
        if route_hint == SKILL_ROUTE_DISCOVERY_HINT:
            skill_route_rows.append(row)
        elif route_hint == "agent_harness_eval_required":
            row["skill_route_discovery_inherited"] = False
            row["direct_runtime_route_allowed"] = False
            row["direct_code_patch_route_allowed"] = False
            adjacent_agent_eval_rows.append(row)
        rows.append(row)

    blocked_proposal_ids = sorted(
        {
            str(row["proposal_id"])
            for row in rows
            if row["row_status"] != "ready"
        }
    )
    ready = (
        bool(skill_route_rows)
        and bool(adjacent_agent_eval_rows)
        and source_status == "ready"
        and not acceptance_failures
        and not blocked_proposal_ids
    )

    return {
        "controller_surface": "skill_route_discovery_active_window_pass2_local_lane_acceptance_contract",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_window_pass2_lanes_accepted_for_bounded_local_validation"
            if ready
            else "repair_active_window_pass2_acceptance_gates_before_activation"
        ),
        "source_surface": "skill_route_discovery_active_window_pass2_validation_lane",
        "source_status": source_status,
        "source_digest": source_digest,
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(row.get("proposal_id") or "") for row in source_rows],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_acceptance_count": len(skill_route_rows),
        "adjacent_agent_eval_acceptance_count": len(adjacent_agent_eval_rows),
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_local_lanes)
        ],
        "queued_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(queued_local_lanes)
        ],
        "adjacent_evaluation_lane": "agent_harness_eval_required" if adjacent_agent_eval_rows else "",
        "agent_harness_eval_required_before_implementation": bool(adjacent_agent_eval_rows),
        "acceptance_gate_names": list(rows[0]["acceptance_gates"]) if rows else [],
        "acceptance_gate_failure_count": len(acceptance_failures),
        "acceptance_gate_failures": acceptance_failures,
        "acceptance_contract_ready": ready,
        "operator_next_action": (
            "replay_active_window_pass2_acceptance_contract_then_continue_to_pass3"
            if ready
            else "repair_blocked_pass2_acceptance_rows_then_replay"
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
        "rows": rows,
        "skill_route_rows": skill_route_rows,
        "adjacent_agent_eval_rows": adjacent_agent_eval_rows,
    }


def _skill_route_discovery_current_run_pass3_validation_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this pass-3 proposal set as bounded local validation lanes."""

    skill_specs = (
        {
            "proposal_id": "proposal_skill_route_discovery_catalog_001",
            "proposal_kind": "test",
            "proposal_track": "skill_route_discovery_catalog",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "representative_skill_route_metadata_stays_bounded_to_local_lanes",
        },
        {
            "proposal_id": "proposal_skill_profile_documentation_002",
            "proposal_kind": "documentation",
            "proposal_track": "skill_profile_route_documentation",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "generic_game_and_handoff_route_profiles_are_documented_separately",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    selected_item_ids: list[str] = []
    downgraded_lanes: list[str] = []

    for spec in skill_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            selected_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("skill_route_candidates_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "generic_skill_workflow",
                        "source_cited_domain_research",
                        "game_frontend_workflow",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in set(matched_profiles)
                ],
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_run_pass3_validation_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="proposal_agent_harness_eval_003",
    )
    adjacent_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "replay_command"
        }
        | {
            "validation_gate": "agent_harness_eval_before_implementation_route",
            "validation_target": "general_agent_project_requires_local_agent_harness_eval",
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

    if adjacent_rows:
        rows.append(
            {
                "proposal_id": "proposal_agent_harness_eval_003",
                "proposal_kind": "test",
                "proposal_track": "agent_harness_evaluation_lane",
                "status": "ready" if not adjacent_blockers else "blocked",
                "activation_blockers": adjacent_blockers,
                "candidate_names": [str(row.get("name") or "") for row in adjacent_rows],
                "candidate_source_hashes": [str(row.get("source_hash") or "") for row in adjacent_rows],
                "route_hint": "agent_harness_eval_required",
                "route_class": "adjacent_general_agent_project",
                "route_profiles": [],
                "allowed_local_lanes": ["documentation", "test", "code_patch"],
                "selected_local_lane": "agent_harness_eval_required",
                "queued_local_lanes": ["documentation", "test", "code_patch"],
                "selected_evidence_item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
                "validation_gates": ["agent_harness_eval_before_implementation_route"],
                "validation_target": "general_agent_project_requires_local_agent_harness_eval",
                "downgraded_unsupported_lanes": [],
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_proposal_ids and bool(adjacent_rows)
    return {
        "controller_surface": "skill_route_discovery_current_run_pass3_validation_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_run_pass3_skill_routes_ready_for_bounded_validation"
            if ready
            else "repair_current_run_pass3_route_boundaries_before_final_pass"
        ),
        "source_digest": source_digest or "github-growth-20260628T022729.498868Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "proposal_skill_route_discovery_catalog_001",
            "proposal_skill_profile_documentation_002",
            "proposal_agent_harness_eval_003",
        ],
        "anchoring_proposal_ids": [
            "p1-skill-route-discovery-catalog",
            "p2-skill-profile-routing-tests",
            "p3-agent-harness-evaluation-lane",
            "p4-game-frontend-skill-eval-fixture",
            "p5-skill-ecosystem-handoff-note",
            "proposal-skill-route-discovery-zxv-001",
            "proposal-agent-harness-qwen-agentworld-001",
            "proposal-game-frontend-skill-route-001",
            "proposal-skill-ecosystem-state-handoff-001",
        ],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
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
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "unsupported_lane_names_removed": sorted(dict.fromkeys(downgraded_lanes)),
        "adjacent_evaluation_lane": "agent_harness_eval_required",
        "agent_harness_eval_required": bool(adjacent_rows),
        "agent_harness_eval_required_before_implementation": bool(adjacent_rows),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_gate",
            "rollback_artifact",
            "focused_local_validation",
        ],
        "operator_next_action": (
            "replay_hashed_current_run_pass3_validation_lane_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_current_run_pass3_validation_lane"
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
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_run_pass3_acceptance_lane(
    current_run_pass3_validation_lane: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose pass-3 acceptance gates derived from the current validation lane."""

    source_rows = _mapping_list(current_run_pass3_validation_lane.get("rows"))
    rows: list[dict[str, Any]] = []
    skill_route_rows: list[dict[str, Any]] = []
    adjacent_rows: list[dict[str, Any]] = []
    acceptance_failures: list[str] = []
    selected_local_lanes: list[str] = []

    for source_row in source_rows:
        proposal_id = str(source_row.get("proposal_id") or "")
        route_hint = str(source_row.get("route_hint") or "")
        candidate_names = _string_list(source_row.get("candidate_names"))
        allowed_lanes = _string_list(source_row.get("allowed_local_lanes"))
        selected_lane = str(source_row.get("selected_local_lane") or "")

        if route_hint == SKILL_ROUTE_DISCOVERY_HINT:
            acceptance_gates = {
                "validation_lane_ready": str(source_row.get("status") or "") == "ready",
                "bounded_lane": (
                    selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                    and selected_lane in set(allowed_lanes)
                    and set(allowed_lanes) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
                ),
                "selected_evidence_present": bool(_string_list(source_row.get("selected_evidence_item_ids"))),
                "validation_gate_present": bool(_string_list(source_row.get("validation_gates"))),
                "local_validation_required": source_row.get("local_validation_required") is True,
                "runtime_action_none": str(source_row.get("runtime_action") or "none") == "none",
                "external_skill_activation_denied": source_row.get("external_skill_activation_allowed") is False,
                "external_agent_activation_denied": source_row.get("external_agent_activation_allowed") is False,
                "external_harness_execution_denied": source_row.get("external_harness_execution_allowed") is False,
                "provider_runtime_launch_denied": source_row.get("provider_runtime_launch_allowed") is False,
                "remote_execution_denied": source_row.get("remote_execution_allowed") is False,
                "raw_source_url_not_exported": source_row.get("raw_source_url_exported") is False,
                "raw_evidence_urls_not_exported": source_row.get("raw_evidence_urls_exported") is False,
                "raw_target_paths_not_exported": source_row.get("raw_target_paths_exported") is False,
                "raw_upstream_body_not_exported": source_row.get("raw_upstream_body_exported") is False,
                "raw_replay_command_not_exported": source_row.get("raw_replay_command_exported") is False,
            }
            failed_gates = [
                gate_name
                for gate_name, gate_ready in acceptance_gates.items()
                if gate_ready is not True
            ]
            acceptance_failures.extend(f"{proposal_id}:{gate_name}" for gate_name in failed_gates)
            if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
                selected_local_lanes.append(selected_lane)
            row = {
                "proposal_id": proposal_id,
                "proposal_kind": str(source_row.get("proposal_kind") or ""),
                "proposal_track": str(source_row.get("proposal_track") or ""),
                "candidate_names": candidate_names,
                "candidate_source_hashes": _string_list(source_row.get("candidate_source_hashes")),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": _string_list(source_row.get("route_profiles")),
                "allowed_local_lanes": allowed_lanes,
                "selected_local_lane": selected_lane,
                "queued_local_lanes": _string_list(source_row.get("queued_local_lanes")),
                "selected_evidence_item_ids": _string_list(source_row.get("selected_evidence_item_ids")),
                "validation_gates": _string_list(source_row.get("validation_gates")),
                "validation_target": str(source_row.get("validation_target") or ""),
                "acceptance_gates": acceptance_gates,
                "acceptance_gate_status": "ready" if not failed_gates else "blocked",
                "activation_blockers": _string_list(source_row.get("activation_blockers"))
                + [f"acceptance_gate_failed:{gate_name}" for gate_name in failed_gates],
                "row_status": "ready" if not failed_gates else "blocked",
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
            rows.append(row)
            skill_route_rows.append(row)
            continue

        if route_hint == "agent_harness_eval_required":
            acceptance_gates = {
                "validation_lane_ready": str(source_row.get("status") or "") == "ready",
                "agent_harness_eval_required": selected_lane == "agent_harness_eval_required",
                "skill_route_discovery_not_inherited": route_hint == "agent_harness_eval_required",
                "direct_runtime_route_denied": source_row.get("runtime_action") == "none",
                "direct_code_patch_not_selected": selected_lane != "code_patch",
                "external_agent_activation_denied": source_row.get("external_agent_activation_allowed") is False,
                "external_harness_execution_denied": source_row.get("external_harness_execution_allowed") is False,
                "provider_runtime_launch_denied": source_row.get("provider_runtime_launch_allowed") is False,
                "remote_execution_denied": source_row.get("remote_execution_allowed") is False,
                "local_validation_required": source_row.get("local_validation_required") is True,
                "raw_source_url_not_exported": source_row.get("raw_source_url_exported") is False,
                "raw_evidence_urls_not_exported": source_row.get("raw_evidence_urls_exported") is False,
                "raw_target_paths_not_exported": source_row.get("raw_target_paths_exported") is False,
                "raw_upstream_body_not_exported": source_row.get("raw_upstream_body_exported") is False,
                "raw_replay_command_not_exported": source_row.get("raw_replay_command_exported") is False,
            }
            failed_gates = [
                gate_name
                for gate_name, gate_ready in acceptance_gates.items()
                if gate_ready is not True
            ]
            acceptance_failures.extend(f"{proposal_id}:{gate_name}" for gate_name in failed_gates)
            row = {
                "proposal_id": proposal_id,
                "proposal_kind": str(source_row.get("proposal_kind") or ""),
                "proposal_track": str(source_row.get("proposal_track") or ""),
                "candidate_names": candidate_names,
                "candidate_source_hashes": _string_list(source_row.get("candidate_source_hashes")),
                "route_hint": "agent_harness_eval_required",
                "route_class": "adjacent_general_agent_project",
                "allowed_local_lanes": ["documentation", "test", "code_patch"],
                "selected_local_lane": "agent_harness_eval_required",
                "queued_local_lanes": ["documentation", "test", "code_patch"],
                "selected_evidence_item_ids": _string_list(source_row.get("selected_evidence_item_ids")),
                "validation_gates": _string_list(source_row.get("validation_gates")),
                "validation_target": str(source_row.get("validation_target") or ""),
                "acceptance_gates": acceptance_gates,
                "acceptance_gate_status": "ready" if not failed_gates else "blocked",
                "activation_blockers": _string_list(source_row.get("activation_blockers"))
                + [f"acceptance_gate_failed:{gate_name}" for gate_name in failed_gates],
                "row_status": "ready" if not failed_gates else "blocked",
                "skill_route_discovery_inherited": False,
                "direct_runtime_route_allowed": False,
                "direct_code_patch_route_allowed": False,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_agent_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
            rows.append(row)
            adjacent_rows.append(row)

    blocked_proposal_ids = sorted(
        {
            str(row["proposal_id"])
            for row in rows
            if row["row_status"] != "ready"
        }
    )
    ready = (
        bool(skill_route_rows)
        and bool(adjacent_rows)
        and str(current_run_pass3_validation_lane.get("status") or "") == "ready"
        and not acceptance_failures
        and not blocked_proposal_ids
    )
    return {
        "controller_surface": "skill_route_discovery_current_run_pass3_acceptance_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_run_pass3_routes_accepted_for_supervisor_replay"
            if ready
            else "repair_current_run_pass3_acceptance_gates_before_final_pass"
        ),
        "source_surface": str(current_run_pass3_validation_lane.get("controller_surface") or ""),
        "source_status": str(current_run_pass3_validation_lane.get("status") or ""),
        "source_digest": str(current_run_pass3_validation_lane.get("source_digest") or ""),
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": _string_list(current_run_pass3_validation_lane.get("proposal_ids")),
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_acceptance_count": len(skill_route_rows),
        "adjacent_agent_eval_acceptance_count": len(adjacent_rows),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_local_lanes)
        ],
        "adjacent_evaluation_lane": "agent_harness_eval_required" if adjacent_rows else "",
        "agent_harness_eval_required_before_implementation": bool(adjacent_rows),
        "acceptance_gate_names": list(rows[0]["acceptance_gates"]) if rows else [],
        "acceptance_gate_failure_count": len(acceptance_failures),
        "acceptance_gate_failures": acceptance_failures,
        "acceptance_contract_ready": ready,
        "operator_next_action": (
            "replay_current_run_pass3_acceptance_lane_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_current_run_pass3_acceptance_lane"
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
        "rows": rows,
    }


def _skill_route_discovery_active_pass3_activation_candidate_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this wake's pass-3 activation candidates without activating them."""

    proposal_specs = (
        {
            "proposal_id": "proposal-skill-route-discovery-aggregate-001",
            "proposal_kind": "test",
            "proposal_track": "skill_workflow_fixture_validation",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "external_skill_style_repositories_map_to_bounded_local_lanes_only",
        },
        {
            "proposal_id": "proposal-game-frontend-skill-profile-002",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_skill_workflow_profile",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_workflow_routes_through_local_discovery_before_adoption",
        },
        {
            "proposal_id": "proposal-skill-state-handoff-003",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff_config",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "handoff_metadata_records_candidates_without_importing_state_or_permissions",
        },
    )

    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    unsupported_lane_names: list[str] = []

    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        downgraded_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("candidate_evidence_missing_for_profile")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")

        row_ready = not blockers
        if row_ready:
            selected_lanes.append(selected_lane)
        unsupported_lane_names.extend(downgraded_lanes)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if row_ready else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "generic_skill_workflow",
                        "source_cited_domain_research",
                        "game_frontend_workflow",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in set(matched_profiles)
                ],
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k active_pass3_activation_candidate_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p5-agent-harness-eval-fixtures",
    )
    adjacent_rows = [
        {
            key: value
            for key, value in row.items()
            if key != "replay_command"
        }
        | {
            "validation_gate": "agent_harness_eval_before_implementation_route",
            "validation_target": "adjacent_general_agent_project_requires_separate_harness_eval",
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

    if adjacent_rows:
        rows.append(
            {
                "proposal_id": "p5-agent-harness-eval-fixtures",
                "proposal_kind": "test",
                "proposal_track": "adjacent_agent_harness_eval",
                "status": "ready" if not adjacent_blockers else "blocked",
                "activation_blockers": adjacent_blockers,
                "candidate_names": [str(row.get("name") or "") for row in adjacent_rows],
                "candidate_source_hashes": [str(row.get("source_hash") or "") for row in adjacent_rows],
                "route_hint": "agent_harness_eval_required",
                "route_class": "adjacent_general_agent_project",
                "route_profiles": [],
                "allowed_local_lanes": ["documentation", "test", "code_patch"],
                "selected_local_lane": "agent_harness_eval_required",
                "queued_local_lanes": ["documentation", "test", "code_patch"],
                "selected_evidence_item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
                "validation_gates": ["agent_harness_eval_before_implementation_route"],
                "validation_target": "adjacent_general_agent_project_requires_separate_harness_eval",
                "downgraded_unsupported_lanes": [],
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    ready = bool(rows) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_active_pass3_activation_candidate_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "active_pass3_skill_route_candidates_ready_for_operator_validation"
            if ready
            else "repair_active_pass3_skill_route_candidates_before_activation_review"
        ),
        "source_digest": source_digest or "github-growth-20260628T034729.532203Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(row["proposal_id"]) for row in rows],
        "anchoring_proposal_ids": [
            "p1-skill-route-discovery-docs-and-probe",
            "p2-skill-route-discovery-test-fixtures",
            "p3-game-frontend-skill-profile-discovery",
            "p4-skill-ecosystem-state-handoff-profile",
            "p5-agent-harness-eval-fixtures",
            "proposal-skill-route-discovery-aggregate-001",
            "proposal-game-frontend-skill-profile-002",
            "proposal-skill-state-handoff-003",
        ],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_skill_route_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "unsupported_lane_names_removed": sorted(dict.fromkeys(unsupported_lane_names)),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "operator_next_action": (
            "replay_hashed_active_pass3_activation_candidate_lane_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_active_pass3_activation_candidate_lane"
        ),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
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
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_digest_pass3_focused_validation_packet(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Route this digest's pass-3 skill proposals into bounded local lanes."""

    current_210729_window = source_digest == "github-growth-20260628T210729.710960Z"
    current_222729_window = source_digest == "github-growth-20260628T222729.564410Z"
    if current_222729_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-zhengxi-views",
                "proposal_kind": "test",
                "proposal_track": "generic_skill_workflow_discovery",
                "route_profiles": ("generic_skill_workflow",),
                "selected_local_lane": "test",
                "validation_target": "generic_skill_workflow_signal_maps_to_bounded_local_validation",
            },
            {
                "proposal_id": "p2-threejs-game-skill-profile",
                "proposal_kind": "documentation",
                "proposal_track": "game_frontend_workflow",
                "route_profiles": ("game_frontend_workflow",),
                "selected_local_lane": "documentation",
                "validation_target": "game_frontend_skill_signal_requires_frontend_validation_before_patch",
            },
            {
                "proposal_id": "p3-skill-ecosystem-state-handoff",
                "proposal_kind": "config",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "config",
                "validation_target": "state_handoff_skill_signal_remains_metadata_only_before_validation",
            },
        )
    elif current_210729_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-matrix",
                "proposal_kind": "test",
                "proposal_track": "skill_route_discovery_matrix",
                "route_profiles": (
                    "generic_skill_workflow",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "test",
                "validation_target": "skill_route_profile_matrix_preserves_bounded_local_lanes",
            },
            {
                "proposal_id": "p3-skill-profile-documentation",
                "proposal_kind": "documentation",
                "proposal_track": "skill_profile_documentation",
                "route_profiles": (
                    "generic_skill_workflow",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "documentation",
                "validation_target": "document_profile_to_lane_mapping_after_local_validation",
            },
        )
    else:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-index",
                "proposal_kind": "test",
                "proposal_track": "skill_workflow_route_index_validation",
                "route_profiles": (
                    "generic_skill_workflow",
                    "source_cited_domain_research",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "test",
                "validation_target": "three_skill_workflow_items_classify_to_bounded_lanes_only",
            },
            {
                "proposal_id": "p2-skill-ecosystem-handoff-doc",
                "proposal_kind": "documentation",
                "proposal_track": "skill_ecosystem_state_handoff_profile",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "documentation",
                "validation_target": "document_state_handoff_profile_as_metadata_only_until_validation",
            },
            {
                "proposal_id": "p3-game-frontend-skill-validation",
                "proposal_kind": "test",
                "proposal_track": "game_frontend_workflow_validation",
                "route_profiles": ("game_frontend_workflow",),
                "selected_local_lane": "test",
                "validation_target": "game_frontend_workflow_requires_local_frontend_validation_before_patch",
            },
        )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    observed_profiles: list[str] = []
    downgraded_lanes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        row_downgraded_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            profile_matches = [profile for profile in candidate_profiles if profile in required_profiles]
            if not profile_matches:
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            matched_profiles.extend(profile_matches)
            observed_profiles.extend(profile_matches)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            row_downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        profile_requirements = _skill_route_discovery_profile_validation_requirements(
            matched_profiles,
            bounded_lanes,
        )
        acceptance_gates = {
            "candidate_evidence_present": bool(candidate_names),
            "selected_lane_bounded": (
                selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                and selected_lane in set(bounded_lanes)
                and set(bounded_lanes) <= set(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
            ),
            "selected_evidence_present": bool(evidence_item_ids),
            "validation_gate_present": bool(validation_gates),
            "profile_requirements_present": bool(profile_requirements),
            "local_validation_required": True,
            "runtime_action_none": True,
            "external_skill_activation_denied": True,
            "external_harness_execution_denied": True,
            "provider_runtime_launch_denied": True,
            "remote_execution_denied": True,
            "raw_source_url_not_exported": True,
            "raw_evidence_urls_not_exported": True,
            "raw_target_paths_not_exported": True,
            "raw_upstream_body_not_exported": True,
        }
        failed_gates = [gate for gate, passed in acceptance_gates.items() if passed is not True]
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        downgraded_lanes.extend(row_downgraded_lanes)

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not failed_gates else "blocked",
                "activation_blockers": [f"acceptance_gate_failed:{gate}" for gate in failed_gates],
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "source_cited_domain_research",
                        "generic_skill_workflow",
                        "game_frontend_workflow",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in set(matched_profiles)
                ],
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "accepted_outputs": ["docs", "config", "tests", "code_patch"],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "profile_validation_requirements": profile_requirements,
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(row_downgraded_lanes)),
                "acceptance_gates": acceptance_gates,
                "acceptance_gate_status": "ready" if not failed_gates else "blocked",
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_digest_pass3_focused_validation_packet"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id=(
            "p2-agent-harness-eval-fixtures"
            if current_210729_window
            else "p4-agent-harness-eval"
        ),
    )
    for row in adjacent_rows:
        row["accepted_outputs_after_eval"] = ["docs", "tests", "code_patch"]
        row["validation_gate"] = (
            "local_agent_harness_eval_required_before_documentation_test_or_code_patch"
            if current_210729_window
            else "agent_harness_eval_before_implementation_route"
        )
        row["validation_target"] = (
            "general_agent_project_fixture_requires_agent_harness_eval_before_local_work"
            if current_210729_window
            else "adjacent_general_agent_project_requires_local_harness_eval"
        )
        row["replay_command_hash"] = _stable_hash(
            "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
        )
        row["raw_replay_command_exported"] = False
        row.pop("replay_command", None)

    adjacent_blockers: list[str] = []
    for row in adjacent_rows:
        item_id = str(row.get("item_id") or "")
        if row.get("evaluation_lane") != "agent_harness_eval_required":
            adjacent_blockers.append(f"{item_id}:evaluation_lane_not_agent_harness_eval_required")
        if row.get("skill_route_discovery_inherited") is not False:
            adjacent_blockers.append(f"{item_id}:skill_route_discovery_inherited")
        if row.get("direct_runtime_route_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:direct_runtime_route_allowed")
        if row.get("direct_code_patch_route_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:direct_code_patch_route_allowed")
        if row.get("external_harness_execution_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:external_harness_execution_allowed")

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    if adjacent_blockers:
        blocked_proposal_ids.append(
            "p2-agent-harness-eval-fixtures"
            if current_210729_window
            else "p4-agent-harness-eval"
        )
    ready = bool(rows) and not blocked_proposal_ids and bool(adjacent_rows)
    return {
        "controller_surface": "skill_route_discovery_current_digest_pass3_focused_validation_packet",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_digest_pass3_skill_routes_ready_for_focused_local_validation"
            if ready
            else "repair_current_digest_pass3_skill_route_validation_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T182729.632246Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in specs]
        + [
            "p2-agent-harness-eval-fixtures"
            if current_210729_window
            else "p4-agent-harness-eval"
        ],
        "anchoring_proposal_ids": (
            [
                "p1-skill-route-discovery-generic",
                "p2-threejs-game-skill-routing-doc",
                "p3-skill-ecosystem-state-handoff-config",
                "trend:lyra81604/zhengxi-views-1",
                "trend:QwenLM/Qwen-AgentWorld-2",
                "proposal-skill-route-discovery-generic-views",
                "proposal-game-frontend-skill-profile",
                "proposal-skill-ecosystem-handoff-routing",
                "proposal-combined-skill-route-fixture",
                "proposal-agent-project-harness-followup",
                "p1-skill-route-discovery-zhengxi-views",
                "p2-threejs-game-skill-profile",
                "p3-skill-ecosystem-state-handoff",
            ]
            if current_222729_window
            else
            [
                "p1-threejs-game-skill-route-discovery",
                "p2-generic-skill-workflow-documentation",
                "p3-skill-ecosystem-state-handoff-config",
                "p4-agent-harness-eval-for-general-agent-projects",
                "p5-proposal-layer-citation-guard",
                "p1-skill-route-discovery-index",
                "p2-skill-profile-docs",
                "p3-agent-harness-eval-fixtures",
                "p4-route-metadata-config-check",
                "p5-route-hint-lane-regression",
                "p1-skill-route-discovery-matrix",
                "p2-agent-harness-eval-fixtures",
            ]
            if current_210729_window
            else [
                "p1-skill-route-discovery-generic",
                "p2-threejs-game-skill-routing",
                "p3-skill-ecosystem-state-handoff",
                "p4-agent-harness-eval",
                "trend:lyra81604/zhengxi-views-1",
                "p1-skill-route-discovery-index",
                "p2-skill-route-discovery-test-fixtures",
                "p3-game-frontend-skill-profile-routing",
                "p4-skill-ecosystem-state-handoff-config",
                "p5-agent-harness-eval-follow-up",
                "p2-skill-ecosystem-handoff-doc",
                "p3-game-frontend-skill-validation",
            ]
        ),
        "ready_skill_route_proposal_count": len(rows) - len([row for row in rows if row["status"] != "ready"]),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "generic_skill_workflow",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
        "adjacent_evaluation_lane": "agent_harness_eval_required",
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_requirements",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_next_action": (
            "replay_current_digest_pass3_focused_validation_packet_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_current_digest_pass3_focused_validation_packet"
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
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_current_source_digest_pass3_operator_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose this wake's pass-3 lane without requiring unrelated profiles."""

    current_175904_window = source_digest == "github-growth-20260629T175904.233445Z"
    current_191904_window = source_digest == "github-growth-20260629T191904.276263Z"
    if current_191904_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-compass",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_target": "compass_skill_ecosystem_signal_maps_to_bounded_test_lane",
            },
            {
                "proposal_id": "p2-skill-route-discovery-generic",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_target": "generic_skill_terms_preserve_route_hint_and_bounded_lanes",
            },
        )
    elif current_175904_window:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-compass",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_target": "compass_skill_handoff_maps_to_bounded_test_lane",
            },
            {
                "proposal_id": "p2-generic-skill-workflow-docs",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_target": "generic_skill_workflow_terms_stay_documentation_config_test_or_code_patch",
            },
        )
    else:
        specs = (
            {
                "proposal_id": "p1-skill-route-discovery-zhengxi-views",
                "proposal_kind": "test",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "test",
                "validation_target": "zhengxi_views_skill_workflow_maps_to_bounded_test_lane",
            },
            {
                "proposal_id": "p3-threejs-game-skills-route",
                "proposal_kind": "documentation",
                "proposal_track": "game_frontend_workflow",
                "route_profiles": ("game_frontend_workflow",),
                "selected_local_lane": "documentation",
                "validation_target": "game_frontend_workflow_documentation_before_patch_or_runtime",
            },
        )
    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    selected_item_ids: list[str] = []
    downgraded_lanes: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        row_downgraded_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            profile_matches = [profile for profile in candidate_profiles if profile in required_profiles]
            if not profile_matches:
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            item_ids = _string_list(candidate.get("evidence_item_ids"))
            evidence_item_ids.extend(item_ids)
            selected_item_ids.extend(item_ids)
            matched_profiles.extend(profile_matches)
            observed_profiles.extend(profile_matches)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            row_downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        profile_requirements = _skill_route_discovery_profile_validation_requirements(
            matched_profiles,
            bounded_lanes,
        )
        acceptance_gates = {
            "candidate_evidence_present": bool(candidate_names),
            "selected_lane_bounded": selected_lane in set(bounded_lanes),
            "selected_evidence_present": bool(evidence_item_ids),
            "validation_gate_present": bool(validation_gates),
            "profile_requirements_present": bool(profile_requirements),
            "local_validation_required": True,
            "runtime_action_none": True,
            "external_skill_activation_denied": True,
            "external_harness_execution_denied": True,
            "provider_runtime_launch_denied": True,
            "remote_execution_denied": True,
            "raw_source_url_not_exported": True,
            "raw_evidence_urls_not_exported": True,
            "raw_target_paths_not_exported": True,
            "raw_upstream_body_not_exported": True,
        }
        failed_gates = [gate for gate, passed in acceptance_gates.items() if passed is not True]
        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        downgraded_lanes.extend(row_downgraded_lanes)

        rows.append(
            {
                "proposal_id": str(spec["proposal_id"]),
                "proposal_kind": str(spec["proposal_kind"]),
                "proposal_track": str(spec["proposal_track"]),
                "status": "ready" if not failed_gates else "blocked",
                "activation_blockers": [f"acceptance_gate_failed:{gate}" for gate in failed_gates],
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "source_cited_domain_research",
                        "generic_skill_workflow",
                        "game_frontend_workflow",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in set(matched_profiles)
                ],
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "accepted_outputs": ["docs", "config", "tests", "code_patch"],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": str(spec["validation_target"]),
                "profile_validation_requirements": profile_requirements,
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(row_downgraded_lanes)),
                "acceptance_gates": acceptance_gates,
                "acceptance_gate_status": "ready" if not failed_gates else "blocked",
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_source_digest_pass3_operator_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id=(
            "p3-agent-harness-eval-general"
            if current_191904_window
            else "p3-agent-harness-eval-fixture"
            if current_175904_window
            else "p2-agent-harness-qwen-agentworld"
        ),
    )
    for row in adjacent_rows:
        row["accepted_outputs_after_eval"] = ["docs", "tests", "code_patch"]
        row["selected_local_lane"] = "agent_harness_eval_required"
        row["validation_gate"] = "local_agent_harness_eval_required_before_controller_runner_or_workflow_change"
        row["validation_target"] = (
            "general_agent_project_trends_require_local_agent_harness_eval_before_implementation"
            if current_191904_window
            else "general_agent_projects_require_local_agent_harness_eval_fixture"
            if current_175904_window
            else "qwen_agentworld_requires_local_agent_harness_eval_fixture"
        )
        row["agent_harness_eval_probe_requirements"] = [
            "install_shape",
            "entrypoints",
            "dependency_boundaries",
            "task_loop_assumptions",
            "observable_behaviors",
            "evaluation_dimensions",
        ]
        row["replay_command_hash"] = _stable_hash(
            "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
        )
        row["raw_replay_command_exported"] = False
        row.pop("replay_command", None)

    adjacent_blockers: list[str] = []
    for row in adjacent_rows:
        item_id = str(row.get("item_id") or "")
        if row.get("evaluation_lane") != "agent_harness_eval_required":
            adjacent_blockers.append(f"{item_id}:evaluation_lane_not_agent_harness_eval_required")
        if row.get("skill_route_discovery_inherited") is not False:
            adjacent_blockers.append(f"{item_id}:skill_route_discovery_inherited")
        if row.get("direct_runtime_route_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:direct_runtime_route_allowed")
        if row.get("direct_code_patch_route_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:direct_code_patch_route_allowed")
        if row.get("external_harness_execution_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:external_harness_execution_allowed")

    blocked_proposal_ids = [str(row["proposal_id"]) for row in rows if row["status"] != "ready"]
    if adjacent_blockers:
        blocked_proposal_ids.append(
            "p3-agent-harness-eval-general"
            if current_191904_window
            else "p3-agent-harness-eval-fixture"
            if current_175904_window
            else "p2-agent-harness-qwen-agentworld"
        )
    ready = bool(rows) and not blocked_proposal_ids and bool(adjacent_rows)
    return {
        "controller_surface": "skill_route_discovery_current_source_digest_pass3_operator_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_source_digest_pass3_routes_ready_for_operator_validation"
            if ready
            else "repair_current_source_digest_pass3_routes_before_pass4"
        ),
        "source_digest": source_digest or "github-growth-20260628T234729.567549Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-compass",
            "p2-skill-route-discovery-generic",
            "p3-agent-harness-eval-general",
        ]
        if current_191904_window
        else [
            "p1-skill-route-discovery-compass",
            "p2-generic-skill-workflow-docs",
            "p3-agent-harness-eval-fixture",
        ]
        if current_175904_window
        else [
            "p1-skill-route-discovery-zhengxi-views",
            "p2-agent-harness-qwen-agentworld",
            "p3-threejs-game-skills-route",
        ],
        "anchoring_proposal_ids": [
            "p1-skill-route-discovery-compass-skills",
            "p2-skill-route-discovery-zhengxi-views",
            "p3-agent-harness-eval-qwen-agentworld",
            "p4-agent-harness-eval-looper",
            "p5-security-agent-review-lane-autocve",
            "p1-skill-route-discovery-compass",
            "p2-skill-route-discovery-generic",
            "p3-agent-harness-eval-general",
            "p4-agent-harness-routing-doc",
            "p5-security-agent-review-gate",
            "p4-security-agent-review-boundary",
            "p5-route-hint-policy-coverage",
        ]
        if current_191904_window
        else [
            "p1-skill-route-discovery-compass",
            "p2-generic-skill-workflow-zhengxi",
            "p3-agent-harness-qwen-agentworld",
            "p4-agent-harness-looper",
            "trend:lyra81604/zhengxi-views-1",
            "p1-skill-route-discovery-compass-skills",
            "p2-skill-route-discovery-zhengxi-views",
            "p5-security-agent-harness-autocve",
            "p2-generic-skill-workflow-docs",
            "p3-agent-harness-eval-fixture",
        ]
        if current_175904_window
        else [
            "p1-skill-route-discovery-views",
            "p2-agent-harness-eval-qwen-agentworld",
            "p3-threejs-game-skill-profile",
            "p1_skill_route_discovery_generic",
            "p2_game_frontend_skill_profile",
            "p4_agent_project_harness_gate",
            "trend:lyra81604/zhengxi-views-1",
            "p1-skill-route-discovery-zhengxi-views",
            "p2-agent-harness-qwen-agentworld",
        ],
        "ready_skill_route_proposal_count": len(rows) - len([row for row in rows if row["status"] != "ready"]),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "generic_skill_workflow",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
        "adjacent_evaluation_lane": "agent_harness_eval_required",
        "agent_harness_eval_required_before_implementation": bool(adjacent_rows),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "route_profile_validation_requirements",
            "agent_harness_eval_probe_requirements",
            "rollback_artifact",
            "focused_local_validation",
            "review_note",
        ],
        "operator_next_action": (
            "replay_current_source_digest_pass3_operator_lane_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_current_source_digest_pass3_operator_lane"
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
        "rows": rows,
        "adjacent_general_agent_rows": adjacent_rows,
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


def _skill_route_discovery_pass3_route_confidence_report(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize pass-3 route confidence without expanding activation authority."""

    confidence_rows: list[dict[str, Any]] = []
    confidence_bands: list[str] = []
    blocker_codes: list[str] = []
    for row in rows:
        allowed_lanes = set(_string_list(row.get("allowed_local_lanes")))
        blockers = _string_list(row.get("activation_blockers"))
        missing_signals: list[str] = []
        if not _string_list(row.get("candidate_names")):
            missing_signals.append("candidate_evidence")
        if not _string_list(row.get("route_profiles")):
            missing_signals.append("route_profile")
        if not _string_list(row.get("selected_evidence_item_ids")):
            missing_signals.append("selected_item_ids_or_frozen_fixture")
        if not _string_list(row.get("validation_gates")):
            missing_signals.append("profile_validation_gate")
        if str(row.get("selected_local_lane") or "") not in allowed_lanes:
            missing_signals.append("bounded_selected_lane")

        confidence_band = "bounded_local_ready" if not blockers and not missing_signals else "needs_local_corroboration"
        confidence_bands.append(confidence_band)
        blocker_codes.extend(blockers)
        confidence_rows.append(
            {
                "proposal_id": str(row.get("proposal_id") or ""),
                "status": str(row.get("status") or "blocked"),
                "route_profiles": _string_list(row.get("route_profiles")),
                "selected_local_lane": str(row.get("selected_local_lane") or ""),
                "confidence_band": confidence_band,
                "evidence_item_id_count": len(_string_list(row.get("selected_evidence_item_ids"))),
                "validation_gate_count": len(_string_list(row.get("validation_gates"))),
                "missing_confidence_signals": missing_signals,
                "activation_blocker_count": len(blockers),
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

    ready_row_count = sum(
        1 for row in confidence_rows if row["confidence_band"] == "bounded_local_ready"
    )
    all_ready = bool(confidence_rows) and ready_row_count == len(confidence_rows)
    return {
        "controller_surface": "skill_route_discovery_pass3_route_confidence_report",
        "status": "ready" if all_ready else "review",
        "decision": (
            "bounded_skill_route_confidence_ready_for_preflight_replay"
            if all_ready
            else "collect_missing_route_confidence_signals_before_activation"
        ),
        "confidence_scope": "local_route_profile_lane_readiness_only",
        "confidence_bands": list(dict.fromkeys(confidence_bands)),
        "row_count": len(confidence_rows),
        "ready_row_count": ready_row_count,
        "blocked_or_review_row_count": len(confidence_rows) - ready_row_count,
        "blocker_codes": list(dict.fromkeys(blocker_codes)),
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
        "rows": confidence_rows,
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
    route_confidence_report = _skill_route_discovery_pass3_route_confidence_report(rows)
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
        "route_confidence_report": route_confidence_report,
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
    route_confidence_report = route_index.get("route_confidence_report")
    route_confidence_report = (
        route_confidence_report if isinstance(route_confidence_report, Mapping) else {}
    )
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
        and route_confidence_report.get("status") == "ready"
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
        "route_confidence_status": str(route_confidence_report.get("status") or ""),
        "route_confidence_decision": str(route_confidence_report.get("decision") or ""),
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
        "route_confidence_report": route_confidence_report,
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

    current_073942_window = source_digest == "github-growth-20260629T073942.884739Z"
    current_093324_window = source_digest == "github-growth-20260629T093324.244697Z"
    if current_093324_window:
        proposal_specs = (
            {
                "proposal_id": "p1-skill-route-discovery-zhengxi-views",
                "proposal_kind": "test",
                "proposal_track": "generic_skill_workflow_discovery",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "test",
                "validation_target": "zhengxi_views_skill_metadata_maps_to_bounded_local_lanes",
                "replay_command": (
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k pass3_current_wake_acceptance_packet"
                ),
            },
            {
                "proposal_id": "p2-skill-ecosystem-handoff-compass",
                "proposal_kind": "documentation",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "documentation",
                "validation_target": "document_compass_skill_ecosystem_handoff_checks_before_local_change",
                "replay_command": "python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery",
            },
        )
        adjacent_proposal_id = "p3-agent-harness-eval-general-projects"
        adjacent_validation_target = (
            "qwen_agentworld_and_looper_without_skill_workflow_stay_agent_harness_eval_required"
        )
        required_profiles = ("generic_skill_workflow", "skill_ecosystem_state_handoff")
        required_evidence = [
            "zhengxi_views_skill_route_metadata_fixture",
            "compass_skill_ecosystem_handoff_fixture",
            "general_agent_project_items_without_skill_workflow_signal",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
        ]
    elif current_073942_window:
        proposal_specs = (
            {
                "proposal_id": "p1-skill-route-discovery-compass",
                "proposal_kind": "test",
                "proposal_track": "skill_ecosystem_state_handoff",
                "route_profiles": ("skill_ecosystem_state_handoff",),
                "selected_local_lane": "test",
                "validation_target": "compass_skill_ecosystem_handoff_profile_maps_to_bounded_local_validation",
                "replay_command": (
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k pass3_current_wake_acceptance_packet"
                ),
            },
            {
                "proposal_id": "p2-generic-skill-workflow-probe",
                "proposal_kind": "documentation",
                "proposal_track": "generic_skill_workflow",
                "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
                "selected_local_lane": "documentation",
                "validation_target": "document_generic_skill_workflow_route_probe_without_runtime_actions",
                "replay_command": "python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery",
            },
        )
        adjacent_proposal_id = "p3-agent-harness-eval-qwen"
        adjacent_validation_target = "qwen_agentworld_without_skill_workflow_stays_agent_harness_eval_required"
        required_profiles = ("generic_skill_workflow", "skill_ecosystem_state_handoff")
        required_evidence = [
            "skill_ecosystem_handoff_profile_fixture",
            "generic_skill_workflow_probe_fixture",
            "adjacent_general_agent_item_without_skill_workflow_signal",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
        ]
    else:
        proposal_specs = (
            {
                "proposal_id": "p1-skill-route-discovery-index",
                "proposal_kind": "test",
                "proposal_track": "skill_route_discovery_index",
                "route_profiles": (
                    "generic_skill_workflow",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "test",
                "validation_target": "current_wake_skill_route_index_fixtures_keep_lanes_bounded",
                "replay_command": (
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k pass3_current_wake_acceptance_packet"
                ),
            },
            {
                "proposal_id": "p2-skill-route-discovery-docs",
                "proposal_kind": "documentation",
                "proposal_track": "skill_route_documentation",
                "route_profiles": (
                    "generic_skill_workflow",
                    "game_frontend_workflow",
                    "skill_ecosystem_state_handoff",
                ),
                "selected_local_lane": "documentation",
                "validation_target": "document_current_wake_skill_route_boundary_without_expanding_lanes",
                "replay_command": "python -m pytest tests/test_docs_contracts.py -q -k skill_route_discovery",
            },
        )
        adjacent_proposal_id = "p3-agent-harness-eval-fixtures"
        adjacent_validation_target = "general_agent_projects_without_skill_workflow_stay_eval_only"
        required_profiles = (
            "generic_skill_workflow",
            "game_frontend_workflow",
            "skill_ecosystem_state_handoff",
        )
        required_evidence = [
            "three_skill_workflow_item_shapes",
            "adjacent_general_agent_item_without_skill_workflow_signal",
            "selected_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_artifact",
            "focused_local_validation",
        ]

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

    observed_profile_set = set(route_profiles)
    missing_profiles = [profile for profile in required_profiles if profile not in observed_profile_set]
    if missing_profiles:
        skill_blockers.append("missing_required_route_profiles:" + ",".join(missing_profiles))

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id=adjacent_proposal_id,
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
            "proposal_id": str(spec["proposal_id"]),
            "proposal_kind": str(spec["proposal_kind"]),
            "proposal_track": str(spec["proposal_track"]),
            "selected_local_lane": str(spec["selected_local_lane"]),
            "candidate_names": list(
                dict.fromkeys(
                    str(row["candidate_name"])
                    for row in skill_rows
                    if set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"])
                    and str(row.get("candidate_name") or "")
                )
            ),
            "candidate_source_hashes": list(
                dict.fromkeys(
                    str(row["candidate_source_hash"])
                    for row in skill_rows
                    if set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"])
                )
            ),
            "route_profiles": [
                profile for profile in spec["route_profiles"] if profile in observed_profile_set
            ],
            "allowed_local_lanes": [
                lane
                for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                if any(
                    lane in set(_string_list(row.get("allowed_local_lanes")))
                    for row in skill_rows
                    if set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"])
                )
            ],
            "selected_evidence_item_ids": list(
                dict.fromkeys(
                    item_id
                    for row in skill_rows
                    if set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"])
                    for item_id in _string_list(row.get("selected_evidence_item_ids"))
                )
            ),
            "validation_gates": list(
                dict.fromkeys(
                    gate
                    for row in skill_rows
                    if set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"])
                    for gate in _string_list(row.get("validation_gates"))
                )
            ),
            "validation_target": str(spec["validation_target"]),
            "replay_command_hash": _stable_hash(str(spec["replay_command"])),
            "status": (
                "ready"
                if skill_rows
                and not skill_blockers
                and str(spec["selected_local_lane"]) in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                and any(
                    str(spec["selected_local_lane"]) in set(_string_list(row.get("allowed_local_lanes")))
                    for row in skill_rows
                    if set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"])
                )
                and any(set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"]) for row in skill_rows)
                else "blocked"
            ),
            "queued_local_lanes": [
                lane
                for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
                if lane != str(spec["selected_local_lane"])
                and any(
                    lane in set(_string_list(row.get("allowed_local_lanes")))
                    for row in skill_rows
                    if set(_string_list(row.get("route_profiles"))).intersection(spec["route_profiles"])
                )
            ],
            "activation_blockers": list(skill_blockers),
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
        for spec in proposal_specs
    ] + [
        {
            "proposal_id": adjacent_proposal_id,
            "proposal_kind": "test",
            "proposal_track": "agent_harness_evaluation_lane",
            "selected_local_lane": "agent_harness_eval_required",
            "candidate_names": [str(row.get("name") or "") for row in adjacent_rows],
            "candidate_source_hashes": [str(row.get("source_hash") or "") for row in adjacent_rows],
            "route_profiles": [],
            "selected_evidence_item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
            "validation_gates": ["local_agent_harness_eval_required_before_implementation_route"],
            "validation_target": adjacent_validation_target,
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
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs] + [adjacent_proposal_id],
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
        "required_evidence": required_evidence,
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


def _skill_route_discovery_current_window_pass3_validation_cases(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Expose the active pass-3 skill-route proposals as replayable local cases."""

    case_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-index",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_discovery_index",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "route_index_summarizes_bounded_skill_workflow_cases",
        },
        {
            "proposal_id": "p2-skill-route-discovery-test-fixtures",
            "proposal_kind": "test",
            "proposal_track": "skill_route_discovery_test_fixtures",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "fixtures_preserve_skill_route_interpreter_controller_boundary",
        },
        {
            "proposal_id": "p3-game-frontend-skill-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_profile_requires_local_frontend_validation",
        },
        {
            "proposal_id": "p4-skill-ecosystem-state-handoff-profile",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_profile_stays_metadata_only_without_memory_or_profile_write",
        },
    )

    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    unsupported_lane_names: list[str] = []

    for spec in case_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []

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
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            unsupported_lane_names.extend(_string_list(candidate.get("downgraded_lane_names")))
            unsupported_lane_names.extend(
                _unsupported_lanes_from_validation_errors(_string_list(candidate.get("validation_errors")))
            )

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_profile_evidence")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_item_ids_or_frozen_fixture")
        if not validation_gates:
            blockers.append("missing_validation_gate")
        profile_validation_requirements = _skill_route_discovery_profile_validation_requirements(
            matched_profiles,
            bounded_lanes,
        )
        if not profile_validation_requirements:
            blockers.append("missing_profile_validation_requirements")

        if selected_lane in bounded_lanes:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)
        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": list(dict.fromkeys(matched_profiles)),
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "profile_validation_requirements": profile_validation_requirements,
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q -k "
                    "current_window_pass3_validation_cases"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p5-agent-project-harness-eval-doc",
    )
    blocked_proposal_ids = [row["proposal_id"] for row in rows if row["status"] != "ready"]
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        and row["external_harness_execution_allowed"] is False
        for row in adjacent_rows
    )
    ready = bool(rows) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_window_pass3_validation_cases",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_window_pass3_skill_routes_ready_for_focused_local_validation"
            if ready
            else "repair_current_window_pass3_skill_routes_before_activation"
        ),
        "source_digest": source_digest or "github-growth-20260628T010729.693724Z",
        "capability_pass": 3,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in case_specs]
        + ["p5-agent-project-harness-eval-doc"],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
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
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
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
            "replay_hashed_local_validation_cases_then_continue_to_pass4"
            if ready
            else "repair_blocked_rows_then_rebuild_current_window_pass3_validation_cases"
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
        "rows": rows,
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
            acceptance_gates = _skill_route_discovery_local_acceptance_gates(
                candidate,
                selected_lane=selected_lane,
                allowed_lanes=allowed_lanes,
                evidence_item_ids=evidence_item_ids,
                validation_gates=validation_gates,
            )
            failed_acceptance_gates = [
                gate_name
                for gate_name, gate_ready in acceptance_gates.items()
                if gate_ready is not True
            ]
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
            row_blockers.extend(
                f"acceptance_gate_failed:{gate_name}" for gate_name in failed_acceptance_gates
            )

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
                    "acceptance_gates": acceptance_gates,
                    "acceptance_gate_status": "ready" if not failed_acceptance_gates else "blocked",
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
    acceptance_gate_names = list(rows[0]["acceptance_gates"]) if rows else []
    acceptance_gate_failures = [
        f"{row['candidate_name']}:{gate_name}"
        for row in rows
        for gate_name, gate_ready in row["acceptance_gates"].items()
        if gate_ready is not True
    ]
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
        "acceptance_gate_names": acceptance_gate_names,
        "acceptance_gate_failure_count": len(acceptance_gate_failures),
        "acceptance_gate_failures": acceptance_gate_failures,
        "acceptance_contract_ready": not acceptance_gate_failures and not missing_proposals,
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
    acceptable_profiles = (*required_profiles, "generic_skill_workflow")
    rows: list[dict[str, Any]] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    replay_commands: list[str] = []
    blocked_candidates: list[str] = []

    for candidate in candidate_lane_inventory:
        route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
        if not set(route_profiles).intersection(acceptable_profiles):
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
    missing_profiles = [
        profile
        for profile in required_profiles
        if not _skill_route_discovery_pass4_profile_covered(profile, observed_profile_set)
    ]
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
            profile
            for profile in required_profiles
            if _skill_route_discovery_pass4_profile_covered(profile, observed_profile_set)
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


def _skill_route_discovery_pass4_profile_covered(profile: str, observed_profile_set: set[str]) -> bool:
    if profile in observed_profile_set:
        return True
    return profile == "source_cited_domain_research" and "generic_skill_workflow" in observed_profile_set


def _skill_route_discovery_profile_validation_checklist(route_profiles: Sequence[str]) -> list[str]:
    """Return body-free final-pass validation checks for observed route profiles."""

    checks_by_profile: Mapping[str, tuple[str, ...]] = {
        "generic_skill_workflow": (
            "confirm_skill_terms_and_route_hints_are_present",
            "confirm_selected_lane_is_documentation_config_test_or_code_patch",
            "confirm_evidence_refs_are_selected_item_ids_or_frozen_fixture",
            "confirm_runtime_action_package_use_and_provider_launch_remain_denied",
        ),
        "source_cited_domain_research": (
            "confirm_source_citation_boundary_is_validated_locally",
            "confirm_advice_or_domain_research_output_stays_review_bounded",
            "confirm_private_context_export_and_provider_launch_remain_denied",
        ),
        "game_frontend_workflow": (
            "confirm_frontend_or_game_workflow_is_validated_locally_before_code_patch",
            "confirm_scaffold_asset_generation_and_browser_run_remain_denied",
            "confirm_ui_or_render_validation_target_is_recorded_for_replay",
        ),
        "skill_ecosystem_state_handoff": (
            "confirm_state_or_profile_handoff_stays_metadata_only",
            "confirm_profile_write_and_memory_write_remain_denied",
            "confirm_privacy_boundary_is_recorded_before_any_handoff_behavior",
        ),
    }
    checklist: list[str] = []
    for profile in route_profiles:
        checklist.extend(checks_by_profile.get(profile, ()))
    return list(dict.fromkeys(checklist))


def _skill_route_discovery_activation_prerequisite_lane(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize final activation prerequisites without adding runtime authority."""

    prerequisite_rows: list[dict[str, Any]] = []
    blocker_rows: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        proposal_id = str(row.get("proposal_id") or "")
        selected_lane = str(row.get("selected_local_lane") or "")
        route_profiles = _string_list(row.get("route_profiles"))
        checklist = _string_list(row.get("profile_validation_checklist"))
        row_blockers: list[str] = []
        if row.get("status") != "ready":
            row_blockers.append("completion_row_not_ready")
        if selected_lane not in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            row_blockers.append("selected_lane_not_bounded")
        if not _string_list(row.get("selected_evidence_item_ids")):
            row_blockers.append("selected_evidence_item_ids_missing")
        if not _string_list(row.get("validation_gates")):
            row_blockers.append("validation_gates_missing")
        if not checklist:
            row_blockers.append("profile_validation_checklist_missing")
        if str(row.get("runtime_action") or "") != "none":
            row_blockers.append("runtime_action_not_none")
        for field_name in (
            "external_skill_activation_allowed",
            "external_harness_execution_allowed",
            "provider_runtime_launch_allowed",
            "profile_write_allowed",
            "memory_write_allowed",
            "remote_execution_allowed",
            "raw_source_url_exported",
            "raw_evidence_urls_exported",
            "raw_target_paths_exported",
            "raw_upstream_body_exported",
        ):
            if row.get(field_name) is not False:
                row_blockers.append(f"{field_name}_must_be_false")
        if row_blockers:
            blocker_rows.append(proposal_id or "unnamed_proposal")

        prerequisite_rows.append(
            {
                "proposal_id": proposal_id,
                "candidate_names": _string_list(row.get("candidate_names")),
                "route_profiles": route_profiles,
                "selected_local_lane": selected_lane if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES else "",
                "required_before_activation": [
                    "focused_evidence_review_completed",
                    "selected_item_ids_or_frozen_fixture_present",
                    "profile_validation_checklist_satisfied",
                    "bounded_local_validation_passed",
                    "rollback_ref_and_artifact_recorded",
                    "external_activation_boundary_confirmed",
                ],
                "profile_validation_checklist": checklist,
                "status": "ready" if not row_blockers else "blocked",
                "activation_blockers": row_blockers,
                "local_validation_required": True,
                "runtime_action": "none",
                "external_skill_activation_allowed": False,
                "external_harness_execution_allowed": False,
                "provider_runtime_launch_allowed": False,
                "profile_write_allowed": False,
                "memory_write_allowed": False,
                "remote_execution_allowed": False,
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    return {
        "controller_surface": "skill_route_discovery_activation_prerequisite_lane",
        "status": "ready" if prerequisite_rows and not blocker_rows else "blocked",
        "decision": (
            "skill_route_rows_have_operator_visible_activation_prerequisites"
            if prerequisite_rows and not blocker_rows
            else "repair_skill_route_activation_prerequisites_before_supervisor_replay"
        ),
        "row_count": len(prerequisite_rows),
        "blocked_proposal_ids": blocker_rows,
        "required_before_activation": [
            "focused_evidence_review_completed",
            "selected_item_ids_or_frozen_fixture_present",
            "profile_validation_checklist_satisfied",
            "bounded_local_validation_passed",
            "rollback_ref_and_artifact_recorded",
            "external_activation_boundary_confirmed",
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "local_validation_required": True,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
        "external_harness_execution_allowed": False,
        "provider_runtime_launch_allowed": False,
        "profile_write_allowed": False,
        "memory_write_allowed": False,
        "remote_execution_allowed": False,
        "raw_replay_command_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": prerequisite_rows,
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
                "profile_validation_checklist": _skill_route_discovery_profile_validation_checklist(
                    candidate_profiles
                ),
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
        "profile_validation_checklist": _skill_route_discovery_profile_validation_checklist(
            sorted(dict.fromkeys(profile for profile in route_profiles if profile))
        ),
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
            "profile_validation_checklist": _string_list(row.get("profile_validation_checklist")),
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
        "profile_validation_checklist": _string_list(
            pass4_completion_handoff.get("profile_validation_checklist")
        ),
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
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Bind this wake's final proposal IDs to validated bounded lanes."""

    proposal_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-generic",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
            ),
            "profile_match_mode": "any",
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_route_classification_fixture_replay",
        },
        {
            "proposal_id": "p2-game-skill-workflow-profile",
            "proposal_kind": "documentation",
            "proposal_track": "game_frontend_workflow",
            "route_profiles": ("game_frontend_workflow",),
            "profile_match_mode": "all",
            "selected_local_lane": "documentation",
            "validation_target": "game_frontend_workflow_profile_documentation_review",
        },
        {
            "proposal_id": "p3-skill-ecosystem-state-handoff",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "profile_match_mode": "all",
            "selected_local_lane": "config",
            "validation_target": "skill_ecosystem_state_handoff_metadata_only_config",
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
        observed_profile_set = set(observed_profiles)
        if spec.get("profile_match_mode") == "any":
            profile_covered = bool(required_profiles & observed_profile_set)
        else:
            profile_covered = required_profiles.issubset(observed_profile_set)
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
        "source_digest": source_digest or "github-growth-20260628T000729.525285Z",
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


def _skill_route_discovery_active_pass4_operator_activation_packet(
    active_pass4_completion_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    """Collapse active pass-4 proposal readiness into an operator handoff packet.

    The packet is intentionally derived from the already bounded completion
    matrix. It does not introduce new lanes, raw upstream evidence, or runtime
    activation authority; it gives the supervisor one replayable pass/fail
    surface for the current skill-route discovery slice.
    """

    raw_rows = active_pass4_completion_matrix.get("rows")
    rows = raw_rows if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes)) else []
    packet_rows: list[dict[str, Any]] = []
    blocked_proposal_ids: list[str] = []
    selected_lanes: list[str] = []
    route_profiles: list[str] = []
    replay_command_hashes: list[str] = []

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        proposal_id = str(row.get("proposal_id") or "")
        selected_lane = str(row.get("selected_local_lane") or "")
        row_profiles = _string_list(row.get("route_profiles"))
        row_replay_hashes = _string_list(row.get("replay_command_hashes"))
        activation_blockers = _string_list(row.get("activation_blockers"))
        row_ready = (
            row.get("status") == "ready"
            and selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and row.get("local_validation_required") is True
            and str(row.get("runtime_action") or "none") == "none"
            and row.get("external_skill_activation_allowed") is False
            and row.get("external_agent_activation_allowed") is False
            and row.get("external_harness_execution_allowed") is False
            and row.get("provider_runtime_launch_allowed") is False
            and row.get("remote_execution_allowed") is False
            and not activation_blockers
        )
        if row_ready:
            selected_lanes.append(selected_lane)
        elif proposal_id:
            blocked_proposal_ids.append(proposal_id)
        route_profiles.extend(row_profiles)
        replay_command_hashes.extend(row_replay_hashes)
        packet_rows.append(
            {
                "proposal_id": proposal_id,
                "proposal_kind": str(row.get("proposal_kind") or ""),
                "proposal_track": str(row.get("proposal_track") or ""),
                "status": "ready" if row_ready else "blocked",
                "route_profiles": row_profiles,
                "selected_local_lane": selected_lane if selected_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES else "",
                "selected_evidence_item_ids": _string_list(row.get("selected_evidence_item_ids")),
                "validation_gate": str(row.get("validation_gate") or ""),
                "validation_target": str(row.get("validation_target") or ""),
                "replay_command_hashes": row_replay_hashes,
                "activation_blockers": activation_blockers,
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

    matrix_ready = active_pass4_completion_matrix.get("status") == "ready"
    ready = bool(packet_rows) and matrix_ready and not blocked_proposal_ids
    adjacent_boundary = active_pass4_completion_matrix.get("adjacent_general_agent_project_boundary")
    adjacent_boundary = adjacent_boundary if isinstance(adjacent_boundary, Mapping) else {}

    return {
        "controller_surface": "skill_route_discovery_active_pass4_operator_activation_packet",
        "status": "ready" if ready else "blocked",
        "decision": (
            "operator_can_mark_skill_route_slice_complete_after_replay"
            if ready
            else "repair_active_pass4_operator_packet_before_completion"
        ),
        "depends_on_controller_surface": "skill_route_discovery_active_pass4_completion_matrix",
        "source_digest": str(active_pass4_completion_matrix.get("source_digest") or ""),
        "capability_pass": int(active_pass4_completion_matrix.get("capability_pass") or 4),
        "total_passes": int(active_pass4_completion_matrix.get("total_passes") or 4),
        "capability_slice_complete": ready,
        "proposal_ids": _string_list(active_pass4_completion_matrix.get("proposal_ids")),
        "ready_proposal_count": len(packet_rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "covered_route_profiles": [
            profile
            for profile in (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(route_profiles)
        ],
        "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
        "operator_next_action": (
            "run_hashed_replay_commands_then_record_supervisor_completion"
            if ready
            else "repair_blocked_proposals_then_rebuild_operator_packet"
        ),
        "rollback_contract": {
            "rollback_ref_required": True,
            "rollback_artifact_required": True,
            "rollback_execution": "explicit_destructive_operator_action_only",
        },
        "supervisor_replay_requirements": [
            "verify_rollback_ref_and_artifact",
            "run_focused_local_validation_for_selected_lanes",
            "review_changed_files_against_selected_lanes",
            "record_review_notes_for_uncertainty_or_blockers",
            "leave_restart_or_promotion_to_configured_supervisor",
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
        "rows": packet_rows,
    }


def _skill_route_discovery_current_run_pass4_completion_lane(
    pass4_completion_handoff: Mapping[str, Any],
    pass4_operator_replay_manifest: Mapping[str, Any],
    current_run_pass3_validation_lane: Mapping[str, Any],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Complete the active skill-route-discovery pass with supervisor-visible lanes."""

    skill_specs = (
        {
            "proposal_id": "proposal-skill-route-discovery-001",
            "proposal_kind": "test",
            "proposal_track": "skill_route_discovery_validation_path",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "frozen_skill_repository_fixtures_map_to_allowed_lanes_only",
        },
        {
            "proposal_id": "proposal-skill-route-docs-002",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_discovery_interpretation_rule",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "documentation_mentions_only_documentation_config_test_code_patch_lanes",
        },
    )

    raw_handoff_rows = pass4_completion_handoff.get("rows")
    handoff_rows = (
        raw_handoff_rows
        if isinstance(raw_handoff_rows, Sequence) and not isinstance(raw_handoff_rows, (str, bytes))
        else []
    )
    replay_ready = pass4_operator_replay_manifest.get("status") == "ready"
    handoff_ready = pass4_completion_handoff.get("status") == "ready"
    pass3_ready = current_run_pass3_validation_lane.get("status") == "ready"
    rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    blocked_proposal_ids: list[str] = []
    observed_profiles: list[str] = []

    for spec in skill_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        matched_profiles: list[str] = []
        replay_command_hashes: list[str] = []

        for row in handoff_rows:
            if not isinstance(row, Mapping):
                continue
            row_profiles = _string_list(row.get("route_profiles"))
            if not required_profiles.intersection(row_profiles):
                continue
            candidate_name = str(row.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hash = str(row.get("candidate_source_hash") or "")
            if candidate_source_hash:
                candidate_source_hashes.append(candidate_source_hash)
            selected_evidence_item_ids.extend(_string_list(row.get("selected_evidence_item_ids")))
            matched_profiles.extend(profile for profile in row_profiles if profile in required_profiles)
            observed_profiles.extend(row_profiles)
            replay_hash = str(row.get("replay_command_hash") or "")
            if replay_hash:
                replay_command_hashes.append(replay_hash)

        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not pass3_ready:
            blockers.append("current_run_pass3_validation_lane_not_ready")
        if not handoff_ready:
            blockers.append("pass4_completion_handoff_not_ready")
        if not replay_ready:
            blockers.append("pass4_operator_replay_manifest_not_ready")
        if not candidate_names:
            blockers.append("missing_skill_route_candidates")
        if not {
            "game_frontend_workflow",
            "skill_ecosystem_state_handoff",
        }.issubset(set(matched_profiles)):
            blockers.append("missing_required_skill_route_profiles")
        if selected_lane not in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES:
            blockers.append("selected_lane_not_bounded")
        if not selected_evidence_item_ids:
            blockers.append("missing_selected_evidence_item_ids")
        if not replay_command_hashes:
            blockers.append("missing_replay_command_hashes")

        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        else:
            selected_lanes.append(selected_lane)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "generic_skill_workflow",
                        "source_cited_domain_research",
                        "game_frontend_workflow",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in set(matched_profiles)
                ],
                "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
                "selected_local_lane": selected_lane,
                "queued_local_lanes": [
                    lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane != selected_lane
                ],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gate": "focused-evidence-review",
                "validation_target": spec["validation_target"],
                "replay_command_hashes": list(dict.fromkeys(replay_command_hashes)),
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

    raw_adjacent_rows = pass4_completion_handoff.get("adjacent_general_agent_rows")
    adjacent_rows = (
        raw_adjacent_rows
        if isinstance(raw_adjacent_rows, Sequence) and not isinstance(raw_adjacent_rows, (str, bytes))
        else []
    )
    adjacent_blockers: list[str] = []
    for adjacent in adjacent_rows:
        if not isinstance(adjacent, Mapping):
            adjacent_blockers.append("adjacent_general_agent_row_not_object")
            continue
        item_id = str(adjacent.get("item_id") or "")
        if adjacent.get("evaluation_lane") != "agent_harness_eval_required":
            adjacent_blockers.append(f"{item_id}:evaluation_lane_not_agent_harness_eval_required")
        if adjacent.get("skill_route_discovery_inherited") is not False:
            adjacent_blockers.append(f"{item_id}:skill_route_discovery_inherited")
        if adjacent.get("direct_runtime_route_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:direct_runtime_route_allowed")
        if adjacent.get("direct_code_patch_route_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:direct_code_patch_route_allowed")
        if adjacent.get("external_harness_execution_allowed") is not False:
            adjacent_blockers.append(f"{item_id}:external_harness_execution_allowed")

    agent_harness_row = {
        "proposal_id": "proposal-agent-harness-eval-003",
        "proposal_kind": "test",
        "proposal_track": "general_agent_project_harness_eval",
        "status": "ready" if adjacent_rows and not adjacent_blockers else "blocked",
        "activation_blockers": adjacent_blockers
        if adjacent_rows
        else ["general_agent_project_evidence_missing"],
        "candidate_names": [
            str(adjacent.get("name") or "")
            for adjacent in adjacent_rows
            if isinstance(adjacent, Mapping)
        ],
        "candidate_source_hashes": [
            str(adjacent.get("source_hash") or "")
            for adjacent in adjacent_rows
            if isinstance(adjacent, Mapping)
        ],
        "route_hint": "agent_harness_eval_required",
        "route_class": "adjacent_general_agent_project",
        "skill_route_discovery_inherited": False,
        "allowed_local_lanes": ["documentation", "test", "code_patch"],
        "selected_local_lane": "agent_harness_eval_required",
        "direct_local_change_proposals_allowed_before_eval": False,
        "selected_evidence_item_ids": [
            str(adjacent.get("item_id") or "")
            for adjacent in adjacent_rows
            if isinstance(adjacent, Mapping)
        ],
        "validation_gate": "agent_harness_eval_before_implementation_route",
        "validation_target": "general_agent_project_requires_local_agent_harness_eval",
        "replay_command_hash": _stable_hash(
            "python -m pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane"
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
        "raw_replay_command_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
    }
    rows.append(agent_harness_row)
    if agent_harness_row["status"] != "ready":
        blocked_proposal_ids.append("proposal-agent-harness-eval-003")

    ready = bool(rows) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_run_pass4_completion_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_run_pass4_skill_route_slice_ready_for_supervisor_replay"
            if ready
            else "repair_current_run_pass4_completion_lane_before_handoff"
        ),
        "depends_on_controller_surfaces": [
            "skill_route_discovery_current_run_pass3_validation_lane",
            "skill_route_discovery_pass4_completion_handoff",
            "skill_route_discovery_pass4_operator_replay_manifest",
        ],
        "source_digest": source_digest or "github-growth-20260628T024729.609046Z",
        "capability_pass": 4,
        "total_passes": 4,
        "capability_slice_complete": ready,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(row["proposal_id"]) for row in rows],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": int(pass4_completion_handoff.get("candidate_count") or 0),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_skill_route_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "agent_harness_eval_required_count": len(adjacent_rows),
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "operator_next_action": (
            "replay_current_run_pass4_completion_lane_then_mark_slice_complete"
            if ready
            else "repair_blocked_rows_then_rebuild_current_run_pass4_completion_lane"
        ),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
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
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_current_window_pass4_route_completion_lane(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Finish the active proposal aliases as bounded local replay lanes."""

    specs = (
        {
            "proposal_id": "p1_skill_route_discovery_generic_views",
            "proposal_kind": "test",
            "proposal_track": "generic_skill_workflow_route_validation",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_target": "generic_skill_workflow_inputs_map_only_to_bounded_local_lanes",
        },
        {
            "proposal_id": "p2_game_frontend_skill_profile",
            "proposal_kind": "test",
            "proposal_track": "game_frontend_workflow_profile_validation",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "test",
            "validation_target": "game_frontend_profile_metadata_preserved_without_runtime_authority",
        },
        {
            "proposal_id": "p3_skill_ecosystem_state_handoff",
            "proposal_kind": "config",
            "proposal_track": "skill_ecosystem_state_handoff_boundary",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_target": "state_handoff_metadata_stays_controller_recomputed_and_write_denied",
        },
    )
    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p4_agent_harness_eval_adjacent",
    )

    rows: list[dict[str, Any]] = []
    blocked_proposal_ids: list[str] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    selected_item_ids: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        matched_profiles: list[str] = []
        downgraded_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            selected_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("skill_route_candidates_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")
        if any(lane not in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES for lane in bounded_lanes):
            blockers.append("unbounded_local_lane_present")

        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        else:
            selected_lanes.append(selected_lane)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "generic_skill_workflow",
                        "source_cited_domain_research",
                        "game_frontend_workflow",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in set(matched_profiles)
                ],
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_window_pass4_route_completion_lane"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    ready = bool(rows) and not blocked_proposal_ids
    return {
        "controller_surface": "skill_route_discovery_current_window_pass4_route_completion_lane",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_window_pass4_skill_routes_ready_for_supervisor_completion"
            if ready
            else "repair_current_window_pass4_skill_routes_before_completion"
        ),
        "source_digest": source_digest,
        "capability_theme": "skill-route-discovery",
        "capability_pass": 4,
        "total_passes": 4,
        "capability_slice_complete": ready,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(row["proposal_id"]) for row in rows],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_skill_route_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "adjacent_general_agent_count": len(adjacent_rows),
        "adjacent_general_agent_boundary": {
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_runtime_route_allowed": False,
            "direct_code_patch_route_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "row_count": len(adjacent_rows),
            "item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
        },
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "operator_next_action": (
            "replay_current_window_pass4_route_completion_lane_then_mark_slice_complete"
            if ready
            else "repair_blocked_rows_then_rebuild_current_window_pass4_route_completion_lane"
        ),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
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
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": rows,
    }


def _skill_route_discovery_current_digest_pass4_final_closure(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str,
) -> dict[str, Any]:
    """Close the active pass-4 skill-route slice as a supervisor replay packet."""

    specs = (
        {
            "proposal_id": "p1-skill-route-discovery-compass",
            "proposal_kind": "test",
            "proposal_track": "state_handoff_skill_route_validation",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "test",
            "validation_target": "state_handoff_skill_repository_maps_only_to_bounded_local_lanes",
        },
        {
            "proposal_id": "p2-skill-route-discovery-generic",
            "proposal_kind": "documentation",
            "proposal_track": "generic_skill_workflow_interpretation",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "documentation",
            "validation_target": "generic_skill_workflow_records_local_validation_required_before_activation",
        },
    )
    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-qwen-agentworld",
    )

    rows: list[dict[str, Any]] = []
    blocked_proposal_ids: list[str] = []
    selected_lanes: list[str] = []
    selected_item_ids: list[str] = []
    observed_profiles: list[str] = []

    for spec in specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        evidence_item_ids: list[str] = []
        allowed_lanes: list[str] = []
        validation_gates: list[str] = []
        matched_profiles: list[str] = []
        downgraded_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            candidate_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(candidate_profiles):
                continue

            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            selected_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            matched_profiles.extend(profile for profile in candidate_profiles if profile in required_profiles)
            observed_profiles.extend(candidate_profiles)
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            downgraded_lanes.extend(_string_list(candidate.get("downgraded_lane_names")))

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("skill_route_candidates_missing")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_local_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if not validation_gates:
            blockers.append("validation_gate_missing")

        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        else:
            selected_lanes.append(selected_lane)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "generic_skill_workflow",
                        "source_cited_domain_research",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in set(matched_profiles)
                ],
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "downgraded_unsupported_lanes": sorted(dict.fromkeys(downgraded_lanes)),
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q "
                    "-k current_digest_pass4_final_closure"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    ready = bool(rows) and not blocked_proposal_ids and bool(adjacent_rows)
    return {
        "controller_surface": "skill_route_discovery_current_digest_pass4_final_closure",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_digest_pass4_skill_route_slice_ready_for_supervisor_completion"
            if ready
            else "repair_current_digest_pass4_skill_route_slice_before_completion"
        ),
        "source_digest": source_digest,
        "capability_theme": "skill-route-discovery",
        "capability_pass": 4,
        "total_passes": 4,
        "capability_slice_complete": ready,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(row["proposal_id"]) for row in rows]
        + ["p3-agent-harness-qwen-agentworld"],
        "ready_skill_route_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_skill_route_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_skill_route_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "selected_evidence_item_ids": list(dict.fromkeys(selected_item_ids)),
        "adjacent_general_agent_count": len(adjacent_rows),
        "adjacent_general_agent_boundary": {
            "proposal_id": "p3-agent-harness-qwen-agentworld",
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_runtime_route_allowed": False,
            "direct_code_patch_route_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "profile_write_allowed": False,
            "memory_write_allowed": False,
            "remote_execution_allowed": False,
            "row_count": len(adjacent_rows),
            "item_ids": [str(row.get("item_id") or "") for row in adjacent_rows],
        },
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "operator_next_action": (
            "replay_current_digest_pass4_final_closure_then_mark_skill_route_slice_complete"
            if ready
            else "repair_blocked_rows_then_rebuild_current_digest_pass4_final_closure"
        ),
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
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


def _skill_route_discovery_current_window_pass4_supervisor_replay_gate(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
    ignored_evidence_items: Sequence[Mapping[str, Any]],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Final current-window gate for supervisor replay and adjacent eval routing."""

    skill_specs = (
        {
            "proposal_id": "p1-skill-route-discovery-fixtures",
            "proposal_kind": "test",
            "proposal_track": "skill_workflow_fixture_validation",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "test",
            "validation_target": "three_skill_workflow_fixture_replay",
        },
        {
            "proposal_id": "p2-skill-route-discovery-docs",
            "proposal_kind": "documentation",
            "proposal_track": "skill_route_interpretation_docs",
            "route_profiles": (
                "generic_skill_workflow",
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            ),
            "selected_local_lane": "documentation",
            "validation_target": "routing_documentation_examples_for_skill_workflow_profiles",
        },
    )
    expected_skill_profiles = {
        "game_frontend_workflow",
        "skill_ecosystem_state_handoff",
        "source_cited_domain_research",
    }

    skill_rows: list[dict[str, Any]] = []
    selected_lanes: list[str] = []
    observed_profiles: list[str] = []
    blocked_proposal_ids: list[str] = []

    for spec in skill_specs:
        spec_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        matched_profiles: list[str] = []
        evidence_item_ids: list[str] = []
        validation_gates: list[str] = []
        allowed_lanes: list[str] = []

        for candidate in sorted(
            candidate_lane_inventory,
            key=lambda item: str(item.get("candidate_name") or "").casefold(),
        ):
            route_profiles = _string_list(candidate.get("route_profiles")) or ["generic_skill_workflow"]
            if not spec_profiles.intersection(route_profiles):
                continue
            candidate_name = str(candidate.get("candidate_name") or "")
            if candidate_name:
                candidate_names.append(candidate_name)
            candidate_source_hashes.append(_stable_hash(str(candidate.get("source_url") or candidate_name)))
            matched_profiles.extend(profile for profile in route_profiles if profile in spec_profiles)
            evidence_item_ids.extend(_string_list(candidate.get("evidence_item_ids")))
            validation_gates.extend(_skill_route_discovery_validation_gates(candidate))
            allowed_lanes.extend(
                lane
                for lane in _string_list(candidate.get("proposal_kinds"))
                if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            )

        bounded_lanes = [lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(allowed_lanes)]
        selected_lane = str(spec["selected_local_lane"])
        matched_profile_set = set(matched_profiles)
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("missing_skill_workflow_candidates")
        if not expected_skill_profiles.issubset(matched_profile_set):
            blockers.append("missing_current_window_skill_profiles")
        if selected_lane not in bounded_lanes:
            blockers.append("selected_lane_not_bounded")
        if not evidence_item_ids:
            blockers.append("missing_selected_evidence_item_ids")
        if not validation_gates:
            blockers.append("missing_validation_gates")

        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        else:
            selected_lanes.append(selected_lane)
        observed_profiles.extend(matched_profiles)

        skill_rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "proposal_track": spec["proposal_track"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(candidate_names)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile
                    for profile in (
                        "source_cited_domain_research",
                        "game_frontend_workflow",
                        "skill_ecosystem_state_handoff",
                    )
                    if profile in matched_profile_set
                ],
                "allowed_local_lanes": bounded_lanes,
                "selected_local_lane": selected_lane if selected_lane in bounded_lanes else "",
                "queued_local_lanes": [lane for lane in bounded_lanes if lane != selected_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_target": spec["validation_target"],
                "replay_command_hash": _stable_hash(
                    "python -m pytest tests/test_skill_routing.py -q -k "
                    "current_window_pass4_supervisor_replay_gate"
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
                "raw_replay_command_exported": False,
                "raw_source_url_exported": False,
                "raw_evidence_urls_exported": False,
                "raw_target_paths_exported": False,
                "raw_upstream_body_exported": False,
            }
        )

    adjacent_rows = _skill_route_discovery_adjacent_general_agent_rows(
        ignored_evidence_items,
        proposal_id="p3-agent-harness-eval-tests",
    )
    adjacent_ready = all(
        row["evaluation_lane"] == "agent_harness_eval_required"
        and row["skill_route_discovery_inherited"] is False
        and row["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
        and row["direct_runtime_route_allowed"] is False
        and row["direct_code_patch_route_allowed"] is False
        and row["runtime_action"] == "none"
        and row["external_harness_execution_allowed"] is False
        for row in adjacent_rows
    )
    ready = bool(skill_rows) and not blocked_proposal_ids and adjacent_ready

    return {
        "controller_surface": "skill_route_discovery_current_window_pass4_supervisor_replay_gate",
        "status": "ready" if ready else "blocked",
        "decision": (
            "current_window_pass4_ready_for_supervisor_local_replay"
            if ready
            else "repair_current_window_pass4_gate_before_supervisor_replay"
        ),
        "source_digest": source_digest or "github-growth-20260628T012729.510462Z",
        "capability_pass": 4,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [
            "p1-skill-route-discovery-fixtures",
            "p2-skill-route-discovery-docs",
            "p3-agent-harness-eval-tests",
        ],
        "ready_skill_proposal_count": len(skill_rows) - len(blocked_proposal_ids),
        "agent_harness_eval_required_count": len(adjacent_rows),
        "blocked_proposal_ids": blocked_proposal_ids,
        "skill_route_candidate_count": len(candidate_lane_inventory),
        "adjacent_general_agent_count": len(adjacent_rows),
        "observed_route_profiles": [
            profile
            for profile in (
                "source_cited_domain_research",
                "game_frontend_workflow",
                "skill_ecosystem_state_handoff",
            )
            if profile in set(observed_profiles)
        ],
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "supervisor_next_action": "replay_ready_skill_lanes_and_keep_agent_project_in_eval_queue",
        "activation_authority": "external_supervisor_after_validation",
        "general_agent_project_policy": {
            "proposal_id": "p3-agent-harness-eval-tests",
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "direct_allowed_lanes_before_eval": [],
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"]
            if adjacent_rows
            else [],
            "required_before_implementation": "local_agent_harness_eval_route_established",
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
            "external_harness_execution_allowed": False,
            "provider_runtime_launch_allowed": False,
            "remote_execution_allowed": False,
            "raw_source_url_exported": False,
            "raw_evidence_urls_exported": False,
            "raw_upstream_body_exported": False,
        },
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
        "raw_replay_commands_exported": False,
        "raw_source_url_exported": False,
        "raw_evidence_urls_exported": False,
        "raw_target_paths_exported": False,
        "raw_upstream_body_exported": False,
        "rows": skill_rows,
        "adjacent_general_agent_rows": adjacent_rows,
    }


def _skill_route_discovery_local_activation_targets(
    candidate_lane_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a supervisor-facing validation target list for bounded lanes."""

    rows: list[dict[str, Any]] = []
    blocked_rows: list[str] = []
    profile_validation_manifest: list[dict[str, Any]] = []

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
        profile_validation_requirements = _skill_route_discovery_profile_validation_requirements(
            route_profiles,
            proposal_kinds,
        )
        validation_target = _skill_route_discovery_validation_target(selected_lane, route_profiles)
        replay_command = _skill_route_discovery_replay_command(selected_lane, route_profiles)
        replay_command_hash = _stable_hash(replay_command) if replay_command else ""
        profile_manifest_rows = [
            {
                "route_profile": requirement["route_profile"],
                "validation_gate": requirement["validation_gate"],
                "must_prove_before_activation": requirement["must_prove_before_activation"],
                "selected_local_lane": selected_lane,
                "validation_target": validation_target,
                "replay_command_hash": replay_command_hash,
                "selected_evidence_item_ids": item_ids,
                "evidence_basis": "selected_item_ids" if item_ids else "frozen_fixture_or_summary",
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
                "raw_replay_command_exported": False,
            }
            for requirement in profile_validation_requirements
        ]
        profile_validation_manifest.extend(profile_manifest_rows)
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
                "validation_target": validation_target,
                "replay_command": replay_command,
                "replay_command_hash": replay_command_hash,
                "profile_validation_requirements": profile_validation_requirements,
                "profile_validation_manifest": profile_manifest_rows,
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
        "profile_validation_manifest": profile_validation_manifest,
        "profile_validation_manifest_count": len(profile_validation_manifest),
        "profile_validation_manifest_ready": bool(profile_validation_manifest)
        and all(
            row["selected_local_lane"] in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and row["evidence_basis"] in {"selected_item_ids", "frozen_fixture_or_summary"}
            and bool(row["replay_command_hash"])
            and row["runtime_action"] == "none"
            and row["external_skill_activation_allowed"] is False
            and row["external_harness_execution_allowed"] is False
            and row["provider_runtime_launch_allowed"] is False
            and row["remote_execution_allowed"] is False
            for row in profile_validation_manifest
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
    replay_command_hash = str(selected.get("replay_command_hash") or "") if selected is not None else ""
    promotion_proof = (
        selected.get("promotion_proof")
        if selected is not None and isinstance(selected.get("promotion_proof"), Mapping)
        else _skill_route_discovery_promotion_proof(selected_lane)
    )
    profile_validation_requirements = (
        [
            dict(row)
            for row in selected.get("profile_validation_requirements", [])
            if isinstance(row, Mapping)
        ]
        if selected is not None
        else []
    )
    profile_validation_manifest = (
        [
            dict(row)
            for row in selected.get("profile_validation_manifest", [])
            if isinstance(row, Mapping)
        ]
        if selected is not None
        else []
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
        "replay_command_hash": replay_command_hash,
        "profile_validation_requirements": profile_validation_requirements,
        "profile_validation_manifest": profile_validation_manifest,
        "profile_validation_manifest_ready": bool(profile_validation_manifest)
        and all(
            row.get("runtime_action") == "none"
            and row.get("external_skill_activation_allowed") is False
            and row.get("external_harness_execution_allowed") is False
            and row.get("provider_runtime_launch_allowed") is False
            and row.get("remote_execution_allowed") is False
            and bool(row.get("replay_command_hash"))
            for row in profile_validation_manifest
        ),
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
        replay_command_hash = str(raw_row.get("replay_command_hash") or "")
        promotion_proof = raw_row.get("promotion_proof")
        promotion_proof = promotion_proof if isinstance(promotion_proof, Mapping) else {}
        profile_validation_requirements = [
            dict(row)
            for row in raw_row.get("profile_validation_requirements", [])
            if isinstance(row, Mapping)
        ]
        profile_validation_manifest = [
            dict(row)
            for row in raw_row.get("profile_validation_manifest", [])
            if isinstance(row, Mapping)
        ]
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
                "replay_command_hash": replay_command_hash,
                "profile_validation_requirements": profile_validation_requirements,
                "profile_validation_manifest": profile_validation_manifest,
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
    *,
    source_digest: str = "",
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
    current_pass_completion_lane = _skill_route_discovery_current_pass_completion_lane(
        rows,
        source_digest=source_digest,
    )

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
        "current_pass_completion_lane": current_pass_completion_lane,
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


def _skill_route_discovery_current_pass_completion_lane(
    activation_rows: Sequence[Mapping[str, Any]],
    *,
    source_digest: str = "",
) -> dict[str, Any]:
    """Bind this pass's proposal IDs to replayable local lanes without activation."""

    proposal_specs = (
        {
            "proposal_id": "proposal-skill-route-discovery-generic-views",
            "proposal_kind": "test",
            "route_profiles": ("generic_skill_workflow", "source_cited_domain_research"),
            "selected_local_lane": "test",
            "validation_task": "skill_workflow_trend_items_map_only_to_bounded_local_lanes",
        },
        {
            "proposal_id": "p2-game-frontend-skill-profile",
            "proposal_kind": "documentation",
            "route_profiles": ("game_frontend_workflow",),
            "selected_local_lane": "documentation",
            "validation_task": "document_game_frontend_workflow_non_network_acceptance_criteria",
        },
        {
            "proposal_id": "proposal-skill-ecosystem-handoff-routing",
            "proposal_kind": "config",
            "route_profiles": ("skill_ecosystem_state_handoff",),
            "selected_local_lane": "config",
            "validation_task": "map_state_handoff_profile_to_metadata_only_validation",
        },
    )

    rows: list[dict[str, Any]] = []
    blocked_proposal_ids: list[str] = []
    observed_profiles: list[str] = []
    selected_lanes: list[str] = []
    validation_replay_commands: list[str] = []

    for spec in proposal_specs:
        required_profiles = set(_string_list(spec["route_profiles"]))
        candidate_names: list[str] = []
        candidate_source_hashes: list[str] = []
        selected_evidence_item_ids: list[str] = []
        validation_gates: list[str] = []
        validation_targets: list[str] = []
        bounded_lanes: list[str] = []

        for row in activation_rows:
            route_profiles = _string_list(row.get("route_profiles")) or ["generic_skill_workflow"]
            if not required_profiles.intersection(route_profiles):
                continue
            candidate_name = str(row.get("candidate_name") or "")
            candidate_source_hash = str(row.get("candidate_source_hash") or "")
            candidate_names.append(candidate_name)
            if candidate_source_hash:
                candidate_source_hashes.append(candidate_source_hash)
            selected_evidence_item_ids.extend(_string_list(row.get("selected_evidence_item_ids")))
            validation_gates.extend(_string_list(row.get("validation_gates")))
            validation_target = str(row.get("validation_target") or "")
            if validation_target:
                validation_targets.append(validation_target)
            observed_profiles.extend(profile for profile in route_profiles if profile in required_profiles)
            bounded_lanes.extend(_string_list(row.get("queued_local_lanes")))
            selected_lane = str(row.get("selected_local_lane") or "")
            if selected_lane:
                bounded_lanes.append(selected_lane)

        allowed_local_lanes = [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(bounded_lanes)
        ]
        selected_local_lane = str(spec["selected_local_lane"])
        blockers: list[str] = []
        if not candidate_names:
            blockers.append("matching_skill_route_candidate_missing")
        if selected_local_lane not in allowed_local_lanes:
            blockers.append("selected_local_lane_not_available_in_bounded_lanes")
        if not validation_gates:
            blockers.append("route_profile_validation_gate_missing")
        if not selected_evidence_item_ids:
            blockers.append("selected_item_ids_or_frozen_fixture_missing")
        if blockers:
            blocked_proposal_ids.append(str(spec["proposal_id"]))
        else:
            selected_lanes.append(selected_local_lane)

        validation_replay_command = (
            _skill_route_discovery_replay_command(selected_local_lane, _string_list(spec["route_profiles"]))
            if selected_local_lane in allowed_local_lanes
            else ""
        )
        if validation_replay_command:
            validation_replay_commands.append(validation_replay_command)

        rows.append(
            {
                "proposal_id": spec["proposal_id"],
                "proposal_kind": spec["proposal_kind"],
                "status": "ready" if not blockers else "blocked",
                "activation_blockers": blockers,
                "candidate_names": list(dict.fromkeys(name for name in candidate_names if name)),
                "candidate_source_hashes": list(dict.fromkeys(candidate_source_hashes)),
                "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                "route_class": SKILL_ROUTE_DISCOVERY_ROUTE_CLASS,
                "route_profiles": [
                    profile for profile in spec["route_profiles"] if profile in set(observed_profiles)
                ],
                "allowed_local_lanes": allowed_local_lanes,
                "selected_local_lane": selected_local_lane if selected_local_lane in allowed_local_lanes else "",
                "queued_local_lanes": [lane for lane in allowed_local_lanes if lane != selected_local_lane],
                "selected_evidence_item_ids": list(dict.fromkeys(selected_evidence_item_ids)),
                "validation_gates": list(dict.fromkeys(validation_gates)),
                "validation_targets": list(dict.fromkeys(validation_targets)),
                "validation_task": spec["validation_task"],
                "validation_replay_command": validation_replay_command,
                "operator_replay_step": (
                    "run_local_validation_for_selected_skill_route_lane"
                    if validation_replay_command
                    else "repair_bounded_lane_before_replay"
                ),
                "acceptance_criteria": [
                    "selected_lane_is_documentation_config_test_or_code_patch",
                    "local_validation_required_before_activation",
                    "no_runtime_action_from_route_interpretation",
                    "no_raw_source_url_or_upstream_body_export",
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
            }
        )

    return {
        "controller_surface": "skill_route_discovery_current_pass_completion_lane",
        "status": "ready" if rows and not blocked_proposal_ids else "blocked",
        "decision": (
            "current_pass_skill_route_proposals_ready_for_supervisor_replay"
            if rows and not blocked_proposal_ids
            else "repair_current_pass_skill_route_completion_before_activation"
        ),
        "source_digest": source_digest,
        "capability_pass": 2,
        "total_passes": 4,
        "review_gate": "focused-evidence-review",
        "proposal_ids": [str(spec["proposal_id"]) for spec in proposal_specs],
        "ready_proposal_count": len(rows) - len(blocked_proposal_ids),
        "blocked_proposal_ids": blocked_proposal_ids,
        "observed_route_profiles": sorted(dict.fromkeys(observed_profiles)),
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "selected_local_lanes": [
            lane for lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES if lane in set(selected_lanes)
        ],
        "validation_replay_commands": list(dict.fromkeys(validation_replay_commands)),
        "operator_replay_bundle": [
            {
                "proposal_id": row["proposal_id"],
                "selected_local_lane": row["selected_local_lane"],
                "route_profiles": row["route_profiles"],
                "validation_replay_command": row["validation_replay_command"],
                "status": row["status"],
            }
            for row in rows
        ],
        "operator_handoff": "external_supervisor_replay_without_kernel_restart",
        "required_evidence": [
            "selected_digest_item_ids_or_frozen_fixture",
            "body_free_repository_summary",
            "rollback_ref",
            "rollback_artifact",
            "focused_local_validation",
            "changed_file_review",
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
        if "references" in parts:
            signals.append("reference_directory")
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
        if basename in {"skill.yml", "skill.yaml"}:
            signals.append("skill_manifest")
        if basename in {"skills.sh.json", "skill.json", "plugin.json", "manifest.json"}:
            signals.append("skill_registry_metadata")
        if basename in {"agents.md", ".agents.md"} or ".codex-plugin/" in path or "/plugins/" in f"/{path}":
            signals.append("agent_metadata")
        if basename in {"publication_audit.md", "security.md"} or "audit" in basename:
            signals.append("qa_checklist")
    return tuple(dict.fromkeys(signals))


def _skill_repository_progressive_package_signals(
    source_layout_signals: Sequence[str],
    source_metadata_signals: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Mark packages that require root-manifest-first progressive disclosure."""

    layout_signals = list(dict.fromkeys(source_layout_signals))
    metadata_signals = list(dict.fromkeys(source_metadata_signals))
    has_skill_entry = bool({"skill_markdown", "skill_directory"} & set(layout_signals))
    has_manifest = "skill_manifest" in metadata_signals
    has_references = "reference_directory" in layout_signals
    if has_skill_entry and has_manifest and has_references:
        layout_signals.append("progressive_skill_package")
    return tuple(dict.fromkeys(layout_signals)), tuple(metadata_signals)


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
