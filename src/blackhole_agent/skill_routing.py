"""Deterministic local skill routing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Any, Mapping, Sequence


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
            "evidence_summary": self.evidence_summary,
            "name": self.name,
            "requested_actions": list(self.requested_actions),
            "route_hints": list(self.route_hints),
            "route_status": SKILL_ROUTE_DISCOVERY_INVALID if errors else SKILL_ROUTE_DISCOVERY_DISABLED,
            "source_url": self.source_url,
            "validation_errors": list(errors),
            "validation_status": self.validation_status,
        }


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


def _validate_public_github_source_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    host = (parsed.hostname or "").casefold()
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https":
        return "source_url_must_use_https"
    if host not in SKILL_ROUTE_DISCOVERY_ALLOWED_SOURCE_HOSTS:
        return "source_url_must_be_public_github_repository"
    if len(path_parts) < 2:
        return "source_url_must_include_repository_owner_and_name"
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        return "source_url_must_be_plain_repository_url"
    return None


def _discovery_event_effect(event_kind: str) -> str:
    if event_kind == "repository_created":
        return "record_only_no_install"
    if event_kind == "repository_deleted":
        return "record_only_no_local_deletion"
    return "record_only"


def _route_weight(route: str) -> int:
    if route == EXACT_TRIGGER_MATCH:
        return 3
    if route == TOPICAL_MATCH:
        return 2
    return 1


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError("skill metadata fields must be strings or sequences of strings")
