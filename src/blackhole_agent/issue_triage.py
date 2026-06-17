"""Local issue-like input triage for controller workflows."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRIAGE_VALIDATION = "validation"
TRIAGE_FOLLOW_UP = "follow_up"
TRIAGE_NO_ACTION = "no_action"
TRIAGE_LANES = {TRIAGE_VALIDATION, TRIAGE_FOLLOW_UP, TRIAGE_NO_ACTION}
TRIAGE_SCHEMA_VERSION = 2

PRIORITY_CRITICAL = "P0-critical"
PRIORITY_HIGH = "P1-high"
PRIORITY_NORMAL = "P2-normal"
PRIORITY_LOW = "P3-low"
PRIORITIES = {PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW}

ALLOWED_LABELS = {
    "duplicate",
    "good-first-issue",
    "help-wanted",
    "needs-info",
    "needs-triage",
    "triaged",
    "comp:controller",
    "comp:docs",
    "comp:runtime",
    "comp:security",
    "comp:tests",
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_NORMAL,
    PRIORITY_LOW,
}

VALIDATION_TERMS = (
    "bug",
    "broken",
    "coverage",
    "failing",
    "fails",
    "fix",
    "regression",
    "reproduce",
    "test",
    "tests",
    "validate",
    "validation",
)
FOLLOW_UP_TERMS = (
    "clarify",
    "question",
    "request",
    "should we",
    "what about",
    "would it",
)
NO_ACTION_TERMS = (
    "duplicate",
    "invalid",
    "no action",
    "spam",
    "wontfix",
    "won't fix",
)

CRITICAL_TERMS = ("critical", "data loss", "security", "secret", "credential", "token", "p0")
HIGH_TERMS = ("blocked", "blocking", "crash", "regression", "p1", "startup")
LOW_TERMS = ("docs", "documentation", "typo", "question", "clarify", "should", "would it", "p3")

COMPONENT_TERMS = (
    ("comp:security", ("security", "secret", "credential", "token", "privacy", "exfiltration")),
    ("comp:tests", ("test", "tests", "pytest", "coverage", "validation", "harness")),
    ("comp:controller", ("digest", "proposal", "trend", "github", "scoring", "triage")),
    ("comp:runtime", ("supervisor", "scheduler", "startup", "restart", "provider", "config")),
    ("comp:docs", ("docs", "documentation", "readme", "guide")),
)


@dataclass(frozen=True)
class IssueTriageRollback:
    """Rollback metadata attached to each persisted triage record."""

    original_branch: str
    original_head: str
    rollback_ref: str
    artifact_path: str
    recovery_commands: list[str]


@dataclass(frozen=True)
class IssueTriageRecommendation:
    """Local recommendation that can be reviewed before any remote mutation."""

    labels: list[str]
    priority: str
    next_actions: list[str]
    duplicate_of: int | None


@dataclass(frozen=True)
class IssueTriageMutationPlan:
    """Replayable mutation intent; commands are plans, not executed by this module."""

    mode: str
    allowed: bool
    reason: str
    commands: list[list[str]]


@dataclass(frozen=True)
class IssueTriageRecord:
    """Classified issue-like input and the controller rationale for its lane."""

    schema_version: int
    triage_id: str
    created_at: str
    input_kind: str
    title: str
    source_url: str
    lane: str
    rationale: list[str]
    recommendation: IssueTriageRecommendation
    mutation_plan: IssueTriageMutationPlan
    validation_task: str
    follow_up_prompt: str
    unsupported_shape: bool
    rollback: IssueTriageRollback | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rollback"] = asdict(self.rollback) if self.rollback is not None else None
        return payload


def triage_issue_input(
    issue_like: Any,
    *,
    rollback: IssueTriageRollback | None = None,
    allow_remote_mutation: bool = False,
    now: datetime | None = None,
) -> IssueTriageRecord:
    """Classify one issue-like input into validation, follow-up, or no-action."""

    created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    normalized = normalize_issue_like(issue_like)
    if normalized is None:
        recommendation = IssueTriageRecommendation(
            labels=["needs-info"],
            priority=PRIORITY_LOW,
            next_actions=["request a supported issue title/body payload"],
            duplicate_of=None,
        )
        return IssueTriageRecord(
            schema_version=TRIAGE_SCHEMA_VERSION,
            triage_id=stable_triage_id({"unsupported": repr(issue_like)[:500]}),
            created_at=created_at,
            input_kind=type(issue_like).__name__,
            title="",
            source_url="",
            lane=TRIAGE_NO_ACTION,
            rationale=[
                "input shape is unsupported; expected an issue-like object with at least title or body text",
                "no local validation task can be derived safely from this shape",
            ],
            recommendation=recommendation,
            mutation_plan=build_mutation_plan(
                None,
                recommendation,
                allow_remote_mutation=allow_remote_mutation,
            ),
            validation_task="",
            follow_up_prompt="Provide an issue title, body, and optional source URL before local validation.",
            unsupported_shape=True,
            rollback=rollback,
        )

    text = f"{normalized['title']}\n{normalized['body']}".lower()
    rationale: list[str] = []
    if has_any_term(text, NO_ACTION_TERMS) or normalized["state"] in {"closed", "resolved"}:
        lane = TRIAGE_NO_ACTION
        rationale.append("issue text or state indicates duplicate, invalid, spam, wontfix, or already resolved")
    elif has_any_term(text, VALIDATION_TERMS):
        lane = TRIAGE_VALIDATION
        rationale.append("issue text contains validation-oriented terms that can map to a local check")
    elif "?" in text or has_any_term(text, FOLLOW_UP_TERMS) or len(text.strip()) < 80:
        lane = TRIAGE_FOLLOW_UP
        rationale.append("issue needs more context before a meaningful local validation task can be selected")
    else:
        lane = TRIAGE_FOLLOW_UP
        rationale.append("issue is shaped correctly but lacks a concrete validation signal")

    validation_task = ""
    follow_up_prompt = ""
    if lane == TRIAGE_VALIDATION:
        validation_task = build_validation_task(normalized)
    elif lane == TRIAGE_FOLLOW_UP:
        follow_up_prompt = build_follow_up_prompt(normalized)

    recommendation = build_recommendation(normalized, lane)
    return IssueTriageRecord(
        schema_version=TRIAGE_SCHEMA_VERSION,
        triage_id=stable_triage_id(normalized),
        created_at=created_at,
        input_kind=normalized["input_kind"],
        title=normalized["title"],
        source_url=normalized["source_url"],
        lane=lane,
        rationale=rationale,
        recommendation=recommendation,
        mutation_plan=build_mutation_plan(
            normalized,
            recommendation,
            allow_remote_mutation=allow_remote_mutation,
        ),
        validation_task=validation_task,
        follow_up_prompt=follow_up_prompt,
        unsupported_shape=False,
        rollback=rollback,
    )


def write_issue_triage_record(record: IssueTriageRecord, output_dir: Path) -> Path:
    """Persist a triage record as replayable JSON and return the written path."""

    if record.lane not in TRIAGE_LANES:
        raise ValueError(f"unsupported triage lane: {record.lane}")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{record.triage_id}.json"
    path.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def normalize_issue_like(issue_like: Any) -> dict[str, str] | None:
    """Normalize dict or string issue-like input into stable text fields."""

    if isinstance(issue_like, str):
        text = issue_like.strip()
        if not text:
            return None
        return {
            "input_kind": "str",
            "title": first_line(text),
            "body": text,
            "state": "",
            "source_url": "",
        }
    if not isinstance(issue_like, dict):
        return None

    title = first_non_empty(issue_like, "title", "summary", "subject")
    body = first_non_empty(issue_like, "body", "description", "text", "content")
    if not title and not body:
        return None
    return {
        "input_kind": "dict",
        "title": title or first_line(body),
        "body": body,
        "state": str(issue_like.get("state") or issue_like.get("status") or "").strip().lower(),
        "source_url": str(issue_like.get("html_url") or issue_like.get("url") or issue_like.get("source_url") or "").strip(),
    }


def build_validation_task(issue: dict[str, str]) -> str:
    title = issue["title"] or "issue"
    source = f" Source: {issue['source_url']}" if issue["source_url"] else ""
    return f"Create or run a focused local validation check for: {title}.{source}".strip()


def build_follow_up_prompt(issue: dict[str, str]) -> str:
    title = issue["title"] or "this issue"
    return f"Ask for reproduction steps, expected behavior, actual behavior, and affected files for: {title}."


def build_recommendation(issue: dict[str, str], lane: str) -> IssueTriageRecommendation:
    text = f"{issue['title']}\n{issue['body']}".lower()
    priority = PRIORITY_LOW if lane == TRIAGE_NO_ACTION else priority_for_text(text)
    labels = ["triaged", priority, component_label_for_text(text)]
    next_actions: list[str]
    duplicate_of = duplicate_number_for_text(text) if lane == TRIAGE_NO_ACTION else None

    if lane == TRIAGE_VALIDATION:
        next_actions = ["run or add focused local validation before source changes"]
        if "good first" in text or "simple" in text:
            labels.append("good-first-issue")
        if "help wanted" in text:
            labels.append("help-wanted")
    elif lane == TRIAGE_FOLLOW_UP:
        labels.append("needs-info")
        next_actions = ["ask for reproduction steps and affected files before validation"]
    else:
        next_actions = ["leave remote state unchanged unless a human confirms the no-action classification"]
        if duplicate_of is not None:
            labels.append("duplicate")

    return IssueTriageRecommendation(
        labels=dedupe_allowed_labels(labels),
        priority=labels[1],
        next_actions=next_actions,
        duplicate_of=duplicate_of,
    )


def build_mutation_plan(
    issue: dict[str, str] | None,
    recommendation: IssueTriageRecommendation,
    *,
    allow_remote_mutation: bool,
) -> IssueTriageMutationPlan:
    if not allow_remote_mutation:
        return IssueTriageMutationPlan(
            mode="dry_run",
            allowed=False,
            reason="remote mutation was not approved by the controller",
            commands=[],
        )
    if issue is None or not issue["source_url"]:
        return IssueTriageMutationPlan(
            mode="blocked",
            allowed=False,
            reason="approved mutation still requires a source URL for the target issue",
            commands=[],
        )

    commands = [
        ["gh", "issue", "edit", issue["source_url"], "--remove-label", "needs-triage"],
        ["gh", "issue", "edit", issue["source_url"], "--add-label", ",".join(recommendation.labels)],
    ]
    if recommendation.duplicate_of is not None:
        commands.append(
            [
                "gh",
                "issue",
                "comment",
                issue["source_url"],
                "--body",
                f"Possible duplicate of #{recommendation.duplicate_of}.",
            ]
        )
    return IssueTriageMutationPlan(
        mode="approved_plan",
        allowed=True,
        reason="controller explicitly approved remote mutation planning",
        commands=commands,
    )


def priority_for_text(text: str) -> str:
    if has_any_term(text, CRITICAL_TERMS):
        return PRIORITY_CRITICAL
    if has_any_term(text, HIGH_TERMS):
        return PRIORITY_HIGH
    if has_any_term(text, LOW_TERMS):
        return PRIORITY_LOW
    return PRIORITY_NORMAL


def component_label_for_text(text: str) -> str:
    for label, terms in COMPONENT_TERMS:
        if has_any_term(text, terms):
            return label
    return "comp:controller"


def duplicate_number_for_text(text: str) -> int | None:
    match = re.search(r"\bduplicate\s+(?:of\s+)?#?(\d+)\b", text)
    return int(match.group(1)) if match else None


def dedupe_allowed_labels(labels: list[str]) -> list[str]:
    deduped: list[str] = []
    for label in labels:
        if label in ALLOWED_LABELS and label not in deduped:
            deduped.append(label)
    return deduped


def first_non_empty(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def first_line(text: str) -> str:
    return text.strip().splitlines()[0][:160].strip()


def has_any_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\b", text) for term in terms)


def stable_triage_id(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"issue-triage-{digest}"
