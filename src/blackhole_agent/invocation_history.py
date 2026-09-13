"""Invocation evidence journal: measured per-capability execution history.

The goal planner's syntactic core (BFS over ``requires``/``provides`` key
sets) answers *which* programs can solve a goal, but when several proved
programs cover the same goal it chooses lexicographically — blind to what
actually happens when capabilities run. This module records the missing
evidence and turns it into a deterministic ranking:

- every real tool execution on the invocation plane appends one JSONL record
  (capability id, wall-clock duration, ok/failed verdict) to the root-scoped
  journal ``.blackhole-agent/invocation-history.jsonl`` — evidence, not
  receipts: no request payloads, no idempotency semantics;
- :func:`load_capability_stats` folds a bounded tail of the journal into
  per-capability aggregates (invocations, failures, mean duration), so a
  huge journal cannot make planning unbounded;
- :func:`rank_programs` orders candidate programs by recorded failures
  first, then recorded mean duration, then a deterministic lexicographic
  tie-break — with no history at all the ranking degenerates exactly to the
  planner's previous syntactic order;
- :func:`plan_evidence` renders the ranking as an auditable response trace:
  which programs were considered and the measured stats that decided.

Honesty boundary: stats describe this workspace's recorded history only. A
capability with no records is not "known good" — it is unmeasured, and the
ranking treats unmeasured steps as zero-failure zero-duration, falling back
to deterministic order rather than fabricating evidence.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
JOURNAL_RELATIVE = Path(".blackhole-agent") / "invocation-history.jsonl"
# Planning reads at most this many trailing records: evidence stays fresh and
# stats loading stays bounded no matter how long the plane has been serving.
DEFAULT_STATS_RECORD_LIMIT = 5000
MAX_ERROR_CHARS = 200

_LOCK = threading.Lock()


def journal_path(root: Path) -> Path:
    return Path(root).resolve() / JOURNAL_RELATIVE


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def record_invocation(
    root: Path,
    capability_id: str,
    *,
    duration_ms: float,
    ok: bool,
    error: str | None = None,
) -> None:
    """Append one execution record; evidence collection never breaks service."""

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capability_id": capability_id,
        "duration_ms": round(max(float(duration_ms), 0.0), 3),
        "ok": bool(ok),
        "at": _utc_now_iso(),
    }
    if error:
        record["error"] = str(error)[:MAX_ERROR_CHARS]
    line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    try:
        with _LOCK:
            path = journal_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        pass


def load_records(root: Path, *, record_limit: int = DEFAULT_STATS_RECORD_LIMIT) -> list[dict[str, Any]]:
    """Return the trailing valid records, oldest first; corrupt lines are skipped."""

    path = journal_path(root)
    records: deque[dict[str, Any]] = deque(maxlen=max(int(record_limit), 1))
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(record, dict)
                    and isinstance(record.get("capability_id"), str)
                    and isinstance(record.get("ok"), bool)
                    and isinstance(record.get("duration_ms"), (int, float))
                ):
                    records.append(record)
    except OSError:
        return []
    return list(records)


def load_capability_stats(
    root: Path, *, record_limit: int = DEFAULT_STATS_RECORD_LIMIT
) -> dict[str, dict[str, Any]]:
    """Fold the journal tail into per-capability measured aggregates."""

    aggregates: dict[str, dict[str, Any]] = {}
    for record in load_records(root, record_limit=record_limit):
        stats = aggregates.setdefault(
            record["capability_id"],
            {"invocations": 0, "failures": 0, "total_duration_ms": 0.0, "last_ok": None},
        )
        stats["invocations"] += 1
        stats["failures"] += 0 if record["ok"] else 1
        stats["total_duration_ms"] += float(record["duration_ms"])
        stats["last_ok"] = record["ok"]
    for stats in aggregates.values():
        invocations = stats["invocations"]
        stats["mean_duration_ms"] = (
            round(stats["total_duration_ms"] / invocations, 3) if invocations else 0.0
        )
        del stats["total_duration_ms"]
    return aggregates


def program_rank_key(
    program: Sequence[str], stats: Mapping[str, Mapping[str, Any]]
) -> tuple[Any, ...]:
    """Deterministic ranking: fewest recorded failures, then lowest recorded
    mean duration, then most measured steps, then lexicographic order.

    With an empty stats mapping every program ranks by ``tuple(program)``
    alone — exactly the planner's previous deterministic order, so evidence
    ranking never changes behavior where no evidence exists.
    """

    failures = sum(int(stats.get(cid, {}).get("failures", 0)) for cid in program)
    duration = sum(float(stats.get(cid, {}).get("mean_duration_ms", 0.0)) for cid in program)
    measured = sum(1 for cid in program if cid in stats)
    return (failures, round(duration, 3), -measured, tuple(program))


def rank_programs(
    programs: Sequence[Sequence[str]], stats: Mapping[str, Mapping[str, Any]]
) -> list[list[str]]:
    """Order candidate programs best-first under :func:`program_rank_key`."""

    return sorted((list(program) for program in programs), key=lambda p: program_rank_key(p, stats))


def plan_evidence(
    ranked_programs: Sequence[Sequence[str]],
    stats: Mapping[str, Mapping[str, Any]],
    *,
    selected: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Render the auditable ranking trace included in solve responses."""

    ranking = []
    for program in ranked_programs:
        steps = []
        for cid in program:
            entry = stats.get(cid)
            steps.append(
                {
                    "capability_id": cid,
                    "recorded_invocations": int(entry.get("invocations", 0)) if entry else 0,
                    "recorded_failures": int(entry.get("failures", 0)) if entry else 0,
                    "mean_duration_ms": float(entry.get("mean_duration_ms", 0.0)) if entry else 0.0,
                    "measured": entry is not None,
                }
            )
        ranking.append({"program": list(program), "steps": steps})
    return {
        "schema_version": SCHEMA_VERSION,
        "policy": (
            "fewest recorded invocation failures, then lowest recorded mean "
            "duration, then deterministic program order"
        ),
        "candidates_considered": len(ranked_programs),
        "selected": list(selected) if selected is not None else None,
        "ranking": ranking,
    }


def monotonic_ms() -> float:
    return time.perf_counter() * 1000.0
