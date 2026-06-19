"""Deterministic local skill routing helpers."""

from __future__ import annotations

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
SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS = ("github.com", "www.github.com")
SKILL_ROUTE_DISCOVERY_ALLOWED_EVENTS = (
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
            "route_hints": list(self.route_hints),
            "route_status": SKILL_ROUTE_DISCOVERY_INVALID if errors else SKILL_ROUTE_DISCOVERY_DISABLED,
            "source_url": self.source_url,
            "validation_errors": list(errors),
            "validation_status": self.validation_status,
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

        for lane in allowed_lanes:
            proposal_lanes.append(
                {
                    "candidate_name": name,
                    "source_url": source_url,
                    "proposal_kind": lane,
                    "route_hint": SKILL_ROUTE_DISCOVERY_HINT,
                    "status": SKILL_ROUTE_DISCOVERY_PROPOSAL_LANE,
                    "evidence_urls": _proposal_lane_evidence_urls(candidate, source_url),
                    "evidence_item_ids": _proposal_lane_evidence_item_ids(candidate),
                    "local_validation_required": True,
                    "runtime_action": "none",
                    "reason": "recognized_skill_project_evidence",
                }
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
    return any(
        marker in text
        for marker in (
            "agent skill",
            "codex skill",
            "claude skill",
            "director skill",
            "fablecodex",
            "skill ecosystem",
            "skill.md",
            "skills/",
            "workflow skill",
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
    lanes = tuple(dict.fromkeys((*suggested, *keyword_lanes)))
    return lanes or ("documentation",)


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
        requested_actions=tuple(dict.fromkeys((*left.requested_actions, *right.requested_actions))),
        validation_status=left.validation_status,
        enabled=left.enabled or right.enabled,
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
