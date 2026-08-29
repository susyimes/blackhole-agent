"""Pattern register: class-level failure ledger (Meta-over-Patch).

``memory.json`` already stores lessons, but nothing forces a recurring
failure to become a class-level repair. This register records error
classes, lifetime and open recurrence, a root-cause sketch, and the
structural fix. When an open class recurs ``>= N`` times, the next
Unbound mission and the next self-evolution plan must target that class.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
DEFAULT_RECURRENCE_THRESHOLD = 3
DEFAULT_OCCURRENCE_LIMIT = 20
REGISTER_RELATIVE = Path(".blackhole-agent") / "pattern-register.json"

PATTERN_CLASSES: dict[str, dict[str, str]] = {
    "health_check_failed": {
        "name": "Health check failed",
        "root_cause": "Candidate or post-merge health command failed.",
        "structural_fix": "Repair the failing health surface so the class cannot recur; do not patch one instance.",
    },
    "protected_path_blocked": {
        "name": "Protected path blocked",
        "root_cause": "A candidate tried to rewrite a judge file on the automatic promotion path.",
        "structural_fix": "Keep governance edits off the automatic write path; evolve behavior around the judges.",
    },
    "promotion_refused": {
        "name": "Promotion refused",
        "root_cause": "Promotion failed for a reason other than health or protected paths.",
        "structural_fix": "Make the promotion preconditions mechanically true: clean target, rollback artifact, fast-forward.",
    },
    "supervisor_pass_failed": {
        "name": "Supervisor pass failed",
        "root_cause": "The one-shot child wake exited non-zero.",
        "structural_fix": "Fix the child wake class (timeout, kernel crash, intake failure), not the last pass.",
    },
    "supervisor_timeout": {
        "name": "Supervisor pass timed out",
        "root_cause": "A wake exceeded the pass timeout.",
        "structural_fix": "Bound wake work and fail fast; do not raise the timeout to hide the class.",
    },
    "kernel_turn_failed": {
        "name": "Kernel turn failed",
        "root_cause": "The kernel died before a structured decision was recorded.",
        "structural_fix": "Harden kernel invocation and decision parsing so a bad turn cannot stall the mission.",
    },
    "milestone_rejected": {
        "name": "Milestone rejected",
        "root_cause": (
            "The controller refused a claimed milestone, including git add -A "
            "dying on unreadable or long-path scratch while staging."
        ),
        "structural_fix": (
            "Stage porcelain-listed paths with core.longpaths enabled; never "
            "walk the whole working tree with git add -A. Unreadable forage "
            "scratch must not reject a proved behavior increment."
        ),
    },
    "paperwork_milestone": {
        "name": "Paperwork-only milestone",
        "root_cause": "A milestone claimed docs/tests/artifacts as capability growth.",
        "structural_fix": "Require a behavior-path delta; stop treating paperwork as a milestone class.",
    },
    "validation_replay_failed": {
        "name": "Validation replay failed",
        "root_cause": "A claimed validation did not reproduce under controller replay.",
        "structural_fix": "Report only commands the controller can re-run; remove fabricated exit codes.",
    },
    "mission_blocked": {
        "name": "Mission blocked",
        "root_cause": "An Unbound mission entered blocked status.",
        "structural_fix": "Remove the external blocker class or make the mission self-unblocking.",
    },
    "genesis_selection_blocked": {
        "name": "Genesis selection blocked",
        "root_cause": (
            "Autonomous genesis invented a saturated or near-duplicate mission after a "
            "consumed campaign left goal/done_when empty; selection gates rejected it "
            "until the mission blocked."
        ),
        "structural_fix": (
            "Bind a gate-passing successor in-process when class_closed genesis has no "
            "remaining campaign; do not invent forage into blocked status."
        ),
    },
    "publication_failed": {
        "name": "Lineage publication failed",
        "root_cause": "A proven commit could not be fast-forwarded to the remote.",
        "structural_fix": "Make publication idempotent and fail closed on remote-head mismatch.",
    },
    "size_ratchet_failed": {
        "name": "Repository size ratchet failed",
        "root_cause": "Measured repository size grew past the shrink-only baseline.",
        "structural_fix": "Delete or shrink existing code before adding more; do not raise the ceiling.",
    },
    "worktree_create_failed": {
        "name": "Candidate worktree create failed",
        "root_cause": "The supervisor could not create an isolated candidate worktree.",
        "structural_fix": "Repair worktree setup so wakes do not depend on a leftover dirty tree.",
    },
}


@dataclass
class PatternOccurrence:
    at: str
    source: str
    summary: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PatternOccurrence":
        return cls(
            at=str(payload.get("at") or ""),
            source=str(payload.get("source") or ""),
            summary=str(payload.get("summary") or ""),
            evidence=str(payload.get("evidence") or ""),
        )


@dataclass
class PatternClass:
    class_id: str
    name: str
    count: int = 0
    open_count: int = 0
    first_seen: str = ""
    last_seen: str = ""
    root_cause: str = ""
    structural_fix: str = ""
    status: str = "open"
    resolved_at: str = ""
    occurrences: list[PatternOccurrence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["occurrences"] = [item.to_dict() for item in self.occurrences]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PatternClass":
        catalog = PATTERN_CLASSES.get(str(payload.get("class_id") or ""), {})
        occurrences = [
            PatternOccurrence.from_dict(item)
            for item in payload.get("occurrences", [])
            if isinstance(item, dict)
        ]
        return cls(
            class_id=str(payload.get("class_id") or ""),
            name=str(payload.get("name") or catalog.get("name") or payload.get("class_id") or ""),
            count=int(payload.get("count") or 0),
            open_count=int(payload.get("open_count") or 0),
            first_seen=str(payload.get("first_seen") or ""),
            last_seen=str(payload.get("last_seen") or ""),
            root_cause=str(payload.get("root_cause") or catalog.get("root_cause") or ""),
            structural_fix=str(payload.get("structural_fix") or catalog.get("structural_fix") or ""),
            status=str(payload.get("status") or "open"),
            resolved_at=str(payload.get("resolved_at") or ""),
            occurrences=occurrences,
        )


@dataclass
class PatternRegister:
    version: int = SCHEMA_VERSION
    recurrence_threshold: int = DEFAULT_RECURRENCE_THRESHOLD
    updated_at: str = ""
    classes: dict[str, PatternClass] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "recurrence_threshold": self.recurrence_threshold,
            "updated_at": self.updated_at,
            "classes": {key: value.to_dict() for key, value in sorted(self.classes.items())},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PatternRegister":
        raw_classes = payload.get("classes") if isinstance(payload, dict) else {}
        classes: dict[str, PatternClass] = {}
        if isinstance(raw_classes, dict):
            for key, value in raw_classes.items():
                if not isinstance(value, dict):
                    continue
                entry = PatternClass.from_dict({"class_id": key, **value})
                if entry.class_id:
                    classes[entry.class_id] = entry
        return cls(
            version=int(payload.get("version") or SCHEMA_VERSION),
            recurrence_threshold=int(payload.get("recurrence_threshold") or DEFAULT_RECURRENCE_THRESHOLD),
            updated_at=str(payload.get("updated_at") or ""),
            classes=classes,
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_register_path(repo_path: Path) -> Path:
    return repo_path / REGISTER_RELATIVE


def load_register(repo_path: Path, path: Path | None = None) -> PatternRegister:
    target = path or default_register_path(repo_path)
    if not target.exists():
        return PatternRegister()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return PatternRegister()
    if not isinstance(payload, dict):
        return PatternRegister()
    return PatternRegister.from_dict(payload)


def save_register(repo_path: Path, register: PatternRegister, path: Path | None = None) -> Path:
    target = path or default_register_path(repo_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    register.updated_at = utc_now_iso()
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(register.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(target)
    return target


def classify_from_catalog(class_id: str) -> dict[str, str]:
    return dict(PATTERN_CLASSES.get(class_id) or {"name": class_id, "root_cause": "", "structural_fix": ""})


def record_occurrence(
    register: PatternRegister,
    class_id: str,
    *,
    source: str,
    summary: str,
    evidence: str = "",
    at: str | None = None,
) -> PatternClass:
    """Append one occurrence and flip the class to forced when open_count >= N."""

    catalog = classify_from_catalog(class_id)
    entry = register.classes.get(class_id)
    if entry is None:
        entry = PatternClass(
            class_id=class_id,
            name=catalog["name"],
            root_cause=catalog["root_cause"],
            structural_fix=catalog["structural_fix"],
        )
        register.classes[class_id] = entry
    stamp = at or utc_now_iso()
    entry.count += 1
    entry.open_count += 1
    entry.first_seen = entry.first_seen or stamp
    entry.last_seen = stamp
    entry.root_cause = entry.root_cause or catalog["root_cause"]
    entry.structural_fix = entry.structural_fix or catalog["structural_fix"]
    entry.occurrences.append(
        PatternOccurrence(at=stamp, source=source, summary=summary, evidence=evidence)
    )
    if len(entry.occurrences) > DEFAULT_OCCURRENCE_LIMIT:
        entry.occurrences = entry.occurrences[-DEFAULT_OCCURRENCE_LIMIT:]
    if entry.open_count >= register.recurrence_threshold:
        entry.status = "forced"
        entry.resolved_at = ""
    elif entry.status == "resolved":
        entry.status = "open"
    return entry


def resolve_class(
    register: PatternRegister,
    class_id: str,
    *,
    structural_fix: str = "",
    at: str | None = None,
) -> PatternClass | None:
    entry = register.classes.get(class_id)
    if entry is None:
        return None
    entry.status = "resolved"
    entry.open_count = 0
    entry.resolved_at = at or utc_now_iso()
    if structural_fix.strip():
        entry.structural_fix = structural_fix.strip()
    return entry


def forced_classes(register: PatternRegister) -> list[PatternClass]:
    forced = [entry for entry in register.classes.values() if entry.status == "forced"]
    forced.sort(key=lambda item: (-item.open_count, item.last_seen))
    return forced


def required_pattern_mission(repo_path: Path, register: PatternRegister | None = None) -> dict[str, str] | None:
    """Return the next required class-level mission, or None."""

    live = register if register is not None else load_register(repo_path)
    pending = forced_classes(live)
    if pending:
        try:
            from blackhole_agent.kernel_class_closure import class_is_closed

            pending = [
                entry
                for entry in pending
                if not class_is_closed(entry.class_id, Path(repo_path))
            ]
        except Exception:  # noqa: BLE001 - missing closer table must not hide open classes
            pass
    if not pending:
        return None
    entry = pending[0]
    goal = (
        f"Eliminate recurring failure class `{entry.class_id}` ({entry.name}) "
        "with a structural fix, not an instance patch."
    )
    done_when = (
        f"The pattern register marks `{entry.class_id}` resolved after a class-level "
        "repair; a later occurrence of the same class must not be fixable by repeating "
        "the last instance patch."
    )
    return {
        "class_id": entry.class_id,
        "name": entry.name,
        "goal": goal,
        "done_when": done_when,
        "open_count": str(entry.open_count),
        "threshold": str(live.recurrence_threshold),
        "root_cause": entry.root_cause,
        "structural_fix": entry.structural_fix,
        "instruction": (
            f"Forced pattern-class mission: `{entry.class_id}` has recurred "
            f"{entry.open_count} times (threshold {live.recurrence_threshold}). "
            f"{entry.structural_fix} This wake must target that class."
        ),
    }


def maybe_resolve_from_goal(repo_path: Path, goal: str, *, structural_fix: str = "") -> str:
    """Resolve a forced class when a completed mission targeted it."""

    if not goal.strip():
        return ""
    register = load_register(repo_path)
    for entry in forced_classes(register):
        if entry.class_id in goal:
            resolve_class(register, entry.class_id, structural_fix=structural_fix or goal)
            save_register(repo_path, register)
            return entry.class_id
    return ""


def _health_failed(checks: Any) -> bool:
    if not isinstance(checks, list):
        return False
    return any(isinstance(item, dict) and int(item.get("returncode") or 0) != 0 for item in checks)


def classify_supervisor_pass(record: dict[str, Any]) -> list[dict[str, str]]:
    """Map one supervisor pass record onto zero or more error classes."""

    events: list[dict[str, str]] = []
    pass_id = str(record.get("pass_id") or "")
    at = str(record.get("finished_at") or record.get("started_at") or "")
    if record.get("timed_out"):
        events.append(
            {
                "class_id": "supervisor_timeout",
                "source": "supervisor",
                "summary": f"pass {pass_id} timed out",
                "evidence": str(record.get("stderr_tail") or "")[:400],
                "at": at,
            }
        )
    worktree = record.get("worktree_result") or {}
    if isinstance(worktree, dict) and worktree.get("attempted") and not worktree.get("created"):
        events.append(
            {
                "class_id": "worktree_create_failed",
                "source": "supervisor",
                "summary": f"pass {pass_id} failed to create a candidate worktree",
                "evidence": str(worktree.get("stderr_tail") or "")[:400],
                "at": at,
            }
        )
    if int(record.get("returncode") or 0) != 0 and not record.get("timed_out"):
        events.append(
            {
                "class_id": "supervisor_pass_failed",
                "source": "supervisor",
                "summary": f"pass {pass_id} exited {record.get('returncode')}",
                "evidence": str(record.get("stderr_tail") or record.get("stdout_tail") or "")[:400],
                "at": at,
            }
        )
    promotion = record.get("promotion_result") or {}
    if isinstance(promotion, dict) and promotion.get("attempted") and not promotion.get("promoted"):
        touched = promotion.get("protected_paths_touched") or []
        # A block without touched paths is a diff-listing infrastructure
        # failure (fail-closed), not a governance interception.
        if promotion.get("protected_paths_blocked") and touched:
            events.append(
                {
                    "class_id": "protected_path_blocked",
                    "source": "supervisor",
                    "summary": f"pass {pass_id} touched protected paths",
                    "evidence": ", ".join(str(item) for item in touched)[:400],
                    "at": at,
                }
            )
        elif _health_failed(promotion.get("health_checks")) or _health_failed(
            promotion.get("post_merge_health_checks")
        ):
            events.append(
                {
                    "class_id": "health_check_failed",
                    "source": "supervisor",
                    "summary": f"pass {pass_id} failed a promotion health command",
                    "evidence": str(promotion.get("stderr_tail") or "")[:400],
                    "at": at,
                }
            )
        else:
            events.append(
                {
                    "class_id": "promotion_refused",
                    "source": "supervisor",
                    "summary": f"pass {pass_id} was refused promotion",
                    "evidence": str(promotion.get("stderr_tail") or "")[:400],
                    "at": at,
                }
            )
    return events


def blocked_class_id(record: Mapping[str, Any] | None) -> str:
    """Distinguish selection-gate blocks from other blocked missions."""

    payload = record or {}
    selection = payload.get("selection_gate")
    if isinstance(selection, Mapping) and selection.get("accepted") is False:
        return "genesis_selection_blocked"
    summary = str(payload.get("last_summary") or payload.get("summary") or "").lower()
    if "mission selection rejected" in summary or "autonomous mission selection rejected" in summary:
        return "genesis_selection_blocked"
    for turn in reversed(list(payload.get("recent_turns") or [])):
        if not isinstance(turn, Mapping):
            continue
        gate = turn.get("selection_gate")
        if isinstance(gate, Mapping) and gate.get("accepted") is False:
            return "genesis_selection_blocked"
    return "mission_blocked"


def classify_unbound_turn(record: dict[str, Any]) -> list[dict[str, str]]:
    """Map one Unbound turn or failure record onto zero or more error classes."""

    events: list[dict[str, str]] = []
    at = str(record.get("finished_at") or record.get("started_at") or "")
    iteration = record.get("iteration")
    if record.get("effective_status") == "error" or record.get("error"):
        events.append(
            {
                "class_id": "kernel_turn_failed",
                "source": "unbound",
                "summary": f"turn {iteration} failed before a structured decision",
                "evidence": str(record.get("error") or record.get("summary") or "")[:400],
                "at": at,
            }
        )
        return events
    if record.get("effective_status") == "blocked" or record.get("requested_status") == "blocked":
        class_id = blocked_class_id(record)
        events.append(
            {
                "class_id": class_id,
                "source": "unbound",
                "summary": f"turn {iteration} reported blocked",
                "evidence": str(record.get("summary") or "")[:400],
                "at": at,
            }
        )
    gate = record.get("milestone_gate") or {}
    if isinstance(gate, dict) and gate.get("requested") and not gate.get("accepted"):
        reasons = [str(item) for item in (gate.get("reasons") or [])]
        joined = "; ".join(reasons)
        class_id = "milestone_rejected"
        if any("docs, tests, artifacts" in reason or "paperwork" in reason.lower() for reason in reasons):
            class_id = "paperwork_milestone"
        if any("replay" in reason.lower() or "reproduced" in reason.lower() for reason in reasons):
            class_id = "validation_replay_failed"
        events.append(
            {
                "class_id": class_id,
                "source": "unbound",
                "summary": f"turn {iteration} milestone rejected",
                "evidence": joined[:400],
                "at": at,
            }
        )
    return events


def ingest_events(repo_path: Path, events: list[dict[str, str]]) -> PatternRegister:
    register = load_register(repo_path)
    for event in events:
        class_id = str(event.get("class_id") or "").strip()
        if not class_id:
            continue
        record_occurrence(
            register,
            class_id,
            source=str(event.get("source") or ""),
            summary=str(event.get("summary") or ""),
            evidence=str(event.get("evidence") or ""),
            at=str(event.get("at") or "") or None,
        )
    if events:
        save_register(repo_path, register)
    return register


def ingest_supervisor_pass(repo_path: Path, record: dict[str, Any]) -> PatternRegister:
    return ingest_events(repo_path, classify_supervisor_pass(record))


def ingest_unbound_turn(repo_path: Path, record: dict[str, Any]) -> PatternRegister:
    return ingest_events(repo_path, classify_unbound_turn(record))


def builtin_pattern_register() -> dict[str, Any]:
    """Invocable smoke: three recurrences force the next mission onto that class."""

    register = PatternRegister(recurrence_threshold=3)
    for index in range(3):
        record_occurrence(
            register,
            "health_check_failed",
            source="smoke",
            summary=f"occurrence {index + 1}",
            at=f"2026-08-17T00:00:0{index}Z",
        )
    forced = required_pattern_mission(Path("."), register=register)
    resolved = resolve_class(register, "health_check_failed", structural_fix="class-level health repair")
    return {
        "ok": bool(
            forced
            and forced["class_id"] == "health_check_failed"
            and resolved is not None
            and resolved.status == "resolved"
            and required_pattern_mission(Path("."), register=register) is None
        ),
        "action": "pattern_register",
        "forced_class": (forced or {}).get("class_id", ""),
        "open_count_before_resolve": 3,
        "resolved_status": getattr(resolved, "status", ""),
    }
