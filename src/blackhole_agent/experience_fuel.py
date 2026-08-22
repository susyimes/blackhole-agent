"""Experience-driven evolution fuel.

GitHub trends and genesis self-selection are not the only inputs. Failed
supervisor passes, refused promotions, rejected milestones, and kernel
errors already land in artifacts; this module harvests them into candidate
missions for the next genesis turn and the next self-evolution plan.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from blackhole_agent.pattern_register import (
    PATTERN_CLASSES,
    classify_from_catalog,
    forced_classes,
    load_register,
    required_pattern_mission,
)

DEFAULT_CANDIDATE_LIMIT = 5
DEFAULT_PASS_SCAN_LIMIT = 8
DEFAULT_MISSION_SCAN_LIMIT = 8
DEFAULT_LEFTOVER_SCAN_LIMIT = 16

_GENERIC_NEXT_PREFIXES = (
    "none",
    "resume on a healthy",
    "keep advancing",
    "keep compounding",
    "n/a",
)
_LEFTOVER_HINTS = (
    "follow-on",
    "follow on",
    "leftover",
    "later work",
    "later turn",
    "later genesis",
    "once cheap",
    "rotation is exhausted",
    "mission-plane",
    "cheap-anchor",
)
_SALVAGE_CLASSES = frozenset({"quota_exhausted", "auth_failed"})


@dataclass(frozen=True)
class ExperienceCandidate:
    source: str
    class_id: str
    summary: str
    evidence: str = ""
    priority: int = 0
    forced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_proposal(self) -> dict[str, Any]:
        catalog = classify_from_catalog(self.class_id)
        kind = "repair" if self.class_id else "test"
        return {
            "proposal_id": f"experience-{self.class_id or 'operational'}-{self.source}",
            "proposal_source": "experience",
            "kind": kind,
            "summary": self.summary,
            "evidence_urls": [],
            "risk_flags": [],
            "implementation_scope": catalog.get("structural_fix") or "Repair the recurring operational class.",
            "validation_gate": "local health and the pattern register must show the class is no longer forced",
            "validation_task": (
                f"Prove class `{self.class_id}` cannot recur by the same instance patch."
                if self.class_id
                else "Prove the harvested operational failure is closed."
            ),
            "requires_approval": False,
            "experience_class_id": self.class_id,
            "experience_forced": self.forced,
        }


@dataclass
class ExperienceFuel:
    forced: dict[str, str] | None = None
    candidates: list[ExperienceCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "forced": dict(self.forced) if self.forced else None,
            "candidates": [item.to_dict() for item in self.candidates],
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _recent_json_files(directory: Path, pattern: str, *, limit: int) -> list[Path]:
    if not directory.is_dir():
        return []
    files = [path for path in directory.glob(pattern) if path.is_file()]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files[:limit]


def _candidate_from_event(event: dict[str, str], *, priority: int, forced: bool = False) -> ExperienceCandidate:
    class_id = str(event.get("class_id") or "")
    catalog = PATTERN_CLASSES.get(class_id, {})
    summary = str(event.get("summary") or catalog.get("name") or "Operational failure")
    return ExperienceCandidate(
        source=str(event.get("source") or "artifact"),
        class_id=class_id,
        summary=summary,
        evidence=str(event.get("evidence") or "")[:400],
        priority=priority,
        forced=forced,
    )


def harvest_supervisor_failures(repo_path: Path, *, limit: int = DEFAULT_PASS_SCAN_LIMIT) -> list[ExperienceCandidate]:
    from blackhole_agent.pattern_register import classify_supervisor_pass

    output_dir = repo_path / ".blackhole-agent" / "supervisor"
    candidates: list[ExperienceCandidate] = []
    seen: set[tuple[str, str]] = set()
    paths = _recent_json_files(output_dir, "supervisor-pass-*.json", limit=limit)
    latest = output_dir / "latest-supervisor-pass.json"
    if latest.exists():
        paths = [latest, *[path for path in paths if path.resolve() != latest.resolve()]]
    for path in paths:
        record = _read_json(path)
        if not record:
            continue
        for event in classify_supervisor_pass(record):
            key = (event.get("class_id", ""), event.get("summary", ""))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(_candidate_from_event(event, priority=2))
    return candidates


def leftover_next_step(text: str) -> str:
    """Return leftover follow-on work, or empty when the next_step is generic/closed."""

    raw = " ".join(str(text or "").split())
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in {"none.", "none", "n/a", "n/a."}:
        return ""
    if any(lowered.startswith(prefix) for prefix in _GENERIC_NEXT_PREFIXES):
        return ""
    if any(hint in lowered for hint in _LEFTOVER_HINTS):
        return raw
    return ""


def harvest_unbound_failures(repo_path: Path, *, limit: int = DEFAULT_MISSION_SCAN_LIMIT) -> list[ExperienceCandidate]:
    from blackhole_agent.pattern_register import classify_unbound_turn

    missions_dir = repo_path / ".blackhole-agent" / "unbound" / "missions"
    if not missions_dir.is_dir():
        return []
    candidates: list[ExperienceCandidate] = []
    seen: set[tuple[str, str]] = set()
    all_states = sorted(
        missions_dir.glob("*/state.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    state_files = all_states[: max(int(limit), DEFAULT_LEFTOVER_SCAN_LIMIT)]
    for state_path in state_files:
        state = _read_json(state_path)
        if not state:
            continue
        if state.get("last_error"):
            event = {
                "class_id": "kernel_turn_failed",
                "source": "unbound",
                "summary": f"mission {state.get('mission_id', '')} last_error",
                "evidence": str(state.get("last_error"))[:400],
            }
            key = (event["class_id"], event["summary"])
            if key not in seen:
                seen.add(key)
                candidates.append(_candidate_from_event(event, priority=3))
        if state.get("status") == "blocked":
            event = {
                "class_id": "mission_blocked",
                "source": "unbound",
                "summary": f"mission {state.get('mission_id', '')} blocked",
                "evidence": str(state.get("last_summary") or "")[:400],
            }
            key = (event["class_id"], event["summary"])
            if key not in seen:
                seen.add(key)
                candidates.append(_candidate_from_event(event, priority=2))
        leftover = leftover_next_step(str(state.get("next_step") or ""))
        if leftover:
            mission_id = str(state.get("mission_id") or "")
            leftover_open = True
            try:
                from blackhole_agent.kernel_leftover import leftover_is_open

                leftover_open = leftover_is_open(
                    leftover,
                    Path(repo_path),
                    source_mission_id=mission_id,
                )
            except Exception:  # noqa: BLE001 - harvest must still surface unknown leftovers
                leftover_open = True
            if leftover_open:
                event = {
                    "class_id": "mission_leftover",
                    "source": "unbound",
                    "summary": leftover,
                    "evidence": f"mission {mission_id} leftover next_step",
                }
                key = (event["class_id"], event["summary"])
                if key not in seen:
                    seen.add(key)
                    candidates.append(_candidate_from_event(event, priority=5))
        for turn in reversed(list(state.get("recent_turns") or [])):
            if not isinstance(turn, dict):
                continue
            salvage = turn.get("kernel_salvage") if isinstance(turn.get("kernel_salvage"), dict) else {}
            salvage_class = str(salvage.get("class_id") or "")
            if salvage_class in _SALVAGE_CLASSES:
                event = {
                    "class_id": salvage_class,
                    "source": "unbound-salvage",
                    "summary": (
                        f"mission {state.get('mission_id', '')} salvaged "
                        f"{salvage_class} without stalling"
                    ),
                    "evidence": str(salvage.get("evidence") or salvage.get("source") or "")[:400],
                }
                key = (event["class_id"], event["summary"])
                if key not in seen:
                    seen.add(key)
                    candidates.append(_candidate_from_event(event, priority=2))
            for event in classify_unbound_turn(turn):
                key = (event.get("class_id", ""), event.get("summary", ""))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(_candidate_from_event(event, priority=3))
    loop_state = _read_json(repo_path / ".blackhole-agent" / "unbound" / "continuous-loop.json")
    if loop_state.get("last_publish_error"):
        candidates.append(
            ExperienceCandidate(
                source="unbound",
                class_id="publication_failed",
                summary="continuous loop publication failed",
                evidence=str(loop_state.get("last_publish_error"))[:400],
                priority=2,
            )
        )
    return candidates


def harvest_experience(repo_path: Path, *, limit: int = DEFAULT_CANDIDATE_LIMIT) -> ExperienceFuel:
    """Collect forced pattern classes and harvested operational failures."""

    register = load_register(repo_path)
    forced = required_pattern_mission(repo_path, register=register)
    candidates: list[ExperienceCandidate] = []
    if forced:
        candidates.append(
            ExperienceCandidate(
                source="pattern-register",
                class_id=forced["class_id"],
                summary=forced["goal"],
                evidence=forced["structural_fix"],
                priority=100,
                forced=True,
            )
        )
    for entry in forced_classes(register):
        if forced and entry.class_id == forced["class_id"]:
            continue
        candidates.append(
            ExperienceCandidate(
                source="pattern-register",
                class_id=entry.class_id,
                summary=f"{entry.name} has recurred {entry.open_count} times",
                evidence=entry.structural_fix,
                priority=10 + entry.open_count,
            )
        )
    candidates.extend(harvest_supervisor_failures(repo_path))
    candidates.extend(harvest_unbound_failures(repo_path))
    deduped: list[ExperienceCandidate] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=lambda row: row.priority, reverse=True):
        key = item.class_id or item.summary
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return ExperienceFuel(forced=forced, candidates=deduped)


def experience_proposals(repo_path: Path, *, limit: int = DEFAULT_CANDIDATE_LIMIT) -> list[dict[str, Any]]:
    return [item.to_proposal() for item in harvest_experience(repo_path, limit=limit).candidates]


def merge_experience_into_proposals(
    proposals: list[dict[str, Any]],
    repo_path: Path,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Prepend harvested operational missions; keep digest proposals behind them."""

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proposal in [*experience_proposals(repo_path, limit=limit), *proposals]:
        if not isinstance(proposal, dict):
            continue
        proposal_id = str(proposal.get("proposal_id") or proposal.get("summary") or "")
        if proposal_id and proposal_id in seen:
            continue
        if proposal_id:
            seen.add(proposal_id)
        merged.append(proposal)
        if len(merged) >= limit:
            break
    return merged


def render_experience_for_genesis(repo_path: Path, *, limit: int = DEFAULT_CANDIDATE_LIMIT) -> str:
    """Compact genesis-prompt block. Empty when there is no operational fuel."""

    fuel = harvest_experience(repo_path, limit=limit)
    if not fuel.candidates:
        return ""
    lines = [
        "Operational experience (internal fuel — prefer these over a fresh invention):",
    ]
    if fuel.forced:
        lines.append(
            f"- FORCED class `{fuel.forced['class_id']}`: {fuel.forced['goal']} "
            f"Done when: {fuel.forced['done_when']}"
        )
    for item in fuel.candidates:
        if fuel.forced and item.class_id == fuel.forced["class_id"]:
            continue
        evidence = f" Evidence: {item.evidence}" if item.evidence else ""
        lines.append(f"- [{item.source}/{item.class_id or 'operational'}] {item.summary}.{evidence}")
    return "\n".join(lines)


def render_experience_brief(repo_path: Path) -> str:
    fuel = harvest_experience(repo_path, limit=3)
    if not fuel.candidates:
        return ""
    if fuel.forced:
        return fuel.forced["instruction"]
    summaries = "; ".join(item.summary for item in fuel.candidates[:3])
    return f"Operational experience candidates: {summaries}"


def builtin_experience_fuel() -> dict[str, Any]:
    """Invocable smoke: harvested supervisor failures become genesis candidates."""

    forced = {
        "class_id": "health_check_failed",
        "goal": "Eliminate recurring failure class `health_check_failed`.",
        "done_when": "resolved",
        "instruction": "Forced pattern-class mission.",
        "structural_fix": "Repair the health surface.",
        "name": "Health check failed",
        "open_count": "3",
        "threshold": "3",
        "root_cause": "health failed",
    }
    fuel = ExperienceFuel(
        forced=forced,
        candidates=[
            ExperienceCandidate(
                source="pattern-register",
                class_id="health_check_failed",
                summary=forced["goal"],
                priority=100,
                forced=True,
            )
        ],
    )
    proposal = fuel.candidates[0].to_proposal()
    return {
        "ok": proposal["proposal_source"] == "experience" and proposal["experience_forced"] is True,
        "action": "experience_fuel",
        "proposal_id": proposal["proposal_id"],
    }
