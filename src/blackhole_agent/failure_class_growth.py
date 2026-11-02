"""Cluster unclassified operational failures into a confirmable class.

Hand-written pattern classes stay the confirmed taxonomy. A failure that
matches one of those classes keeps that class. Three failures that share a
stack fingerprint and match none of those classes become one candidate card.
Confirming the card registers it on the pattern register, so a later copy
increments the same class and the required pattern mission can name it.

A proved closer hides that whole class from genesis fuel. The latest forced
occurrence still becomes a symptom card when its command text is outside the
closer and outside a later completed repair. A covered command, a repaired
command, a selection-gate rejection, and an open class stay off that card.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.pattern_register import (
    classify_unbound_turn,
    load_register,
    record_occurrence,
    required_pattern_mission,
    save_register,
)

CLUSTER_THRESHOLD = 3
SCAN_LIMIT = 24
MAX_STATE_BYTES = 2_000_000
GENERIC_CLASS = "kernel_turn_failed"

_EXCEPTION_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_PATH_RE = re.compile(r"(?:[A-Za-z]:\\[^\s'\"]+|/(?:[\w.-]+/)+[\w.-]+)")
_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
_NUMBER_RE = re.compile(r"\d+")


def failure_signature(text: str) -> str:
    """Stable fingerprint of one failure, ignoring ids, paths, and counts."""

    raw = " ".join(str(text or "").split())
    match = _EXCEPTION_RE.search(raw)
    exception_name = match.group(1) if match else "untyped"
    message = raw[match.end() :] if match else raw
    message = _UUID_RE.sub("<id>", message)
    message = _PATH_RE.sub("<path>", message)
    message = _HEX_RE.sub("<hex>", message)
    message = _NUMBER_RE.sub("#", message).lower()[:160]
    return f"{exception_name}|{message}"


def candidate_class_id(signature: str) -> str:
    digest = hashlib.sha256(str(signature or "").encode("utf-8")).hexdigest()[:12]
    return f"grown-{digest}"


def known_pattern_class(turn: Mapping[str, Any] | None) -> str:
    """Return a hand-written class id, or empty when the turn is generic."""

    if not isinstance(turn, Mapping):
        return ""
    for event in classify_unbound_turn(dict(turn)):
        class_id = str(event.get("class_id") or "")
        if class_id and class_id != GENERIC_CLASS:
            return class_id
    return ""


def _failure_text(item: Mapping[str, Any] | str) -> str:
    if isinstance(item, str):
        return item
    text = item.get("text")
    if text:
        return str(text)
    turn = item.get("turn")
    if isinstance(turn, Mapping):
        return str(turn.get("error") or turn.get("summary") or "")
    return ""


def _failure_turn(item: Mapping[str, Any] | str) -> dict[str, Any] | None:
    if isinstance(item, str):
        return {"effective_status": "error", "error": item, "iteration": 1}
    turn = item.get("turn")
    if isinstance(turn, Mapping):
        return dict(turn)
    text = _failure_text(item)
    if not text:
        return None
    return {"effective_status": "error", "error": text, "iteration": 1}


def cluster_unclassified_failures(
    failures: Sequence[Mapping[str, Any] | str],
    *,
    threshold: int = CLUSTER_THRESHOLD,
) -> list[dict[str, Any]]:
    """Group unclassified failures. Only a group of ``threshold`` becomes a card."""

    grouped: dict[str, list[str]] = {}
    for item in failures:
        turn = _failure_turn(item)
        if known_pattern_class(turn):
            continue
        text = _failure_text(item) or str((turn or {}).get("error") or "")
        if not text.strip():
            continue
        signature = failure_signature(text)
        grouped.setdefault(signature, []).append(" ".join(text.split())[:240])
    cards: list[dict[str, Any]] = []
    minimum = max(2, int(threshold))
    for signature in sorted(grouped):
        samples = grouped[signature]
        if len(samples) < minimum:
            continue
        exception_name, _, message = signature.partition("|")
        readable = message.strip(" |") or exception_name
        cards.append(
            {
                "class_id": candidate_class_id(signature),
                "signature": signature,
                "sample_count": len(samples),
                "name": f"Unclassified {exception_name}",
                "root_cause": (
                    f"Repeated unclassified failure {exception_name} sharing one "
                    f"stack fingerprint: {readable[:120]}"
                ),
                "structural_fix": (
                    f"Repair the shared {exception_name} failure. Registering another "
                    "copy as a generic kernel turn failure does not name the class."
                ),
                "samples": samples[:8],
            }
        )
    return cards


def confirm_failure_candidate(repo_path: Path, card: Mapping[str, Any]) -> dict[str, Any]:
    """Register one candidate so later copies increment it and can force a mission."""

    class_id = str(card.get("class_id") or "")
    if not class_id:
        raise ValueError("candidate card needs a class_id")
    root = Path(repo_path)
    register = load_register(root)
    samples = [str(item) for item in (card.get("samples") or []) if str(item).strip()]
    if not samples:
        samples = [str(card.get("signature") or class_id)]
    for sample in samples:
        record_occurrence(
            register,
            class_id,
            source="failure-class-growth",
            summary=str(card.get("name") or class_id),
            evidence=sample[:400],
        )
    entry = register.classes[class_id]
    entry.name = str(card.get("name") or entry.name or class_id)
    entry.root_cause = str(card.get("root_cause") or entry.root_cause)
    entry.structural_fix = str(card.get("structural_fix") or entry.structural_fix)
    save_register(root, register)
    mission = required_pattern_mission(root, register)
    return {
        "class_id": class_id,
        "open_count": entry.open_count,
        "status": entry.status,
        "mission_class_id": "" if mission is None else str(mission.get("class_id") or ""),
        "mission_goal": "" if mission is None else str(mission.get("goal") or ""),
    }


def record_matching_failure(repo_path: Path, class_id: str, evidence: str) -> int:
    """Increment an already registered grown class and return its open count."""

    root = Path(repo_path)
    register = load_register(root)
    if class_id not in register.classes:
        raise KeyError(class_id)
    entry = record_occurrence(
        register,
        class_id,
        source="failure-class-growth",
        summary=register.classes[class_id].name,
        evidence=str(evidence or "")[:400],
    )
    save_register(root, register)
    return int(entry.open_count)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_STATE_BYTES:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def collect_unclassified_failures(repo_path: Path, *, limit: int = SCAN_LIMIT) -> list[dict[str, Any]]:
    """Read recent mission errors without walking the whole mission archive."""

    missions = Path(repo_path) / ".blackhole-agent" / "unbound" / "missions"
    if not missions.is_dir():
        return []
    try:
        paths = sorted(
            (path for path in missions.glob("*/state.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []
    failures: list[dict[str, Any]] = []
    for path in paths[: max(1, int(limit))]:
        state = _read_json(path)
        if not state:
            continue
        last_error = str(state.get("last_error") or "").strip()
        if last_error:
            failures.append(
                {
                    "text": last_error,
                    "turn": {
                        "effective_status": "error",
                        "error": last_error,
                        "iteration": state.get("iteration") or 1,
                    },
                }
            )
        for turn in state.get("recent_turns") or []:
            if not isinstance(turn, dict):
                continue
            error = str(turn.get("error") or "").strip()
            if error:
                failures.append({"text": error, "turn": turn})
            gate = turn.get("milestone_gate")
            if isinstance(gate, dict) and gate.get("requested") and not gate.get("accepted"):
                reasons = " ".join(str(item) for item in (gate.get("reasons") or []))
                if reasons.strip():
                    failures.append({"text": reasons, "turn": turn})
    return failures


_GENERIC_SYMPTOM_TOKENS = frozenset(
    {
        "acceptance",
        "behavior",
        "capability",
        "closer",
        "command",
        "commands",
        "complete",
        "controller",
        "exit",
        "failed",
        "failure",
        "false",
        "milestone",
        "mission",
        "none",
        "proved",
        "python",
        "rejected",
        "replay",
        "reported",
        "structural",
        "true",
        "unbound",
        "validation",
    }
)
_RARE_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def rare_symptom_tokens(text: str) -> set[str]:
    """Distinctive command tokens. Generic replay words do not count."""

    found: set[str] = set()
    for token in _RARE_TOKEN.findall(str(text or "").lower()):
        if len(token) < 8 or token in _GENERIC_SYMPTOM_TOKENS or token.isdigit():
            continue
        found.add(token)
    return found


def _later_repair_text(repo_path: Path, occurrence_at: str) -> str:
    """Goal and summary text from completed missions at or after ``occurrence_at``."""

    missions = Path(repo_path) / ".blackhole-agent" / "unbound" / "missions"
    if not missions.is_dir() or not occurrence_at:
        return ""
    try:
        paths = sorted(
            (path for path in missions.glob("*/state.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""
    chunks: list[str] = []
    for path in paths[:SCAN_LIMIT]:
        state = _read_json(path)
        if str(state.get("status") or "") != "complete":
            continue
        stamps = [str(state.get("created_at") or ""), str(state.get("updated_at") or "")]
        for item in state.get("milestones") or []:
            if isinstance(item, dict):
                stamps.append(str(item.get("at") or ""))
        if not any(stamp and stamp >= occurrence_at for stamp in stamps):
            continue
        chunks.append(str(state.get("goal") or ""))
        chunks.append(str(state.get("last_summary") or ""))
    return "\n".join(chunks)


def novel_closed_class_symptoms(repo_path: Path) -> list[dict[str, Any]]:
    """Latest forced occurrence a proved closer and later repairs do not name.

    The occurrence must be a replay failure. Its rare command tokens must fall
    outside the class structural fix, and none of those unseen tokens may
    appear in a completed mission that started at or after the occurrence.
    """

    root = Path(repo_path)
    try:
        from blackhole_agent.kernel_class_closure import class_is_closed, load_effective_ledger

        ledger = load_effective_ledger(root)
    except Exception:  # noqa: BLE001 - growth text must still render other cards
        return []
    register = load_register(root)
    cards: list[dict[str, Any]] = []
    for class_id in sorted(register.classes):
        entry = register.classes[class_id]
        if entry.status != "forced" or not entry.occurrences:
            continue
        try:
            closed = class_is_closed(class_id, root, ledger=ledger)
        except Exception:  # noqa: BLE001 - one bad class must not hide the rest
            continue
        if not closed:
            continue
        latest = entry.occurrences[-1]
        evidence = str(latest.evidence or latest.summary or "").strip()
        if "replay" not in evidence.lower():
            continue
        outside = rare_symptom_tokens(evidence) - rare_symptom_tokens(entry.structural_fix)
        if not outside:
            continue
        repairs = _later_repair_text(root, str(latest.at or ""))
        repair_tokens = rare_symptom_tokens(repairs)
        if outside & repair_tokens:
            continue
        cards.append(
            {
                "class_id": class_id,
                "evidence": evidence[:400],
                "unseen_tokens": sorted(outside),
                "occurred_at": str(latest.at or ""),
            }
        )
    return cards


def render_unclassified_growth_for_genesis(repo_path: Path) -> str:
    """Compact candidate cards for a genesis prompt. Empty when none qualify."""

    cards = cluster_unclassified_failures(collect_unclassified_failures(repo_path))
    symptoms = novel_closed_class_symptoms(repo_path)
    if not cards and not symptoms:
        return ""
    lines: list[str] = []
    if cards:
        lines.append(
            "Unclassified failure clusters (a card is ready to confirm into the pattern register):"
        )
        for card in cards[:5]:
            lines.append(
                f"- `{card['class_id']}` samples={card['sample_count']} "
                f"signature={card['signature'][:160]}"
            )
    if symptoms:
        lines.append(
            "Closed-class novel symptoms (a proved closer does not name this command):"
        )
        for card in symptoms[:5]:
            lines.append(f"- `{card['class_id']}` evidence={card['evidence'][:240]}")
    return "\n".join(lines)
