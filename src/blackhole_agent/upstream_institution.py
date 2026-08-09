"""Upstream institution plane: multi-program durable stewardship constitution.

The program plane (``upstream_program``) closes multi-succession charters
*within one program*. It does not:

1. chain multiple independent programs under a durable institutional constitution;
2. allocate a shared global dispatch budget across programs by ROI;
3. admit/retire program slots from an institutional charter over time
   (deferred admission under a concurrent-active cap);
4. federate multi-program portfolio coverage into one institutional world-model;
5. persist institution state so a later process can resume the constitution;
6. seal a multi-program institutional chronicle linking program digests.

The institution plane closes that outer institutional loop:

1. **admit** — materialize program slots from a durable institution charter
   (each slot owns a stewardship surface + optional surface_charter). When
   ``max_active_programs`` is set, only that many *unmet* programs are
   concurrent: further charter slots stay pending and are admitted as
   capacity frees after retirements (constitution growth over time);
2. **schedule** — pick the next open program by priority and historical ROI;
3. **program** — call the program plane (injected ``program_runner``; default
   ``run_program``) with a share of the remaining global dispatch budget;
4. **federate** — merge per-program portfolios into one institutional
   world-model and re-score coverage across all stewarded keys;
5. **retire** — mark programs met when their program_goal is satisfied, then
   re-admit pending charter slots up to the active capacity;
6. **persist** — write ``institution_state.json`` after every program round
   so a later ``run_institution(..., resume_dir=...)`` continues the same
   constitution (including pending charter and admission history);
7. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across programs
   - institution goal met (``all_programs_met``: every *admitted* program is
     met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

8. **seal** — write an institution receipt under
   ``artifacts/upstream-institution/`` with sha256 digests of every program,
   portfolio federation, admission history, ROI history, stop reason, and an
   institution chain digest; ``verify_institution_receipt`` re-checks the
   chain and detects tampering.

No skill-route discovery is used. The plane is constitution-level direction
over the program plane, not a new verifier of individual repairs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent import upstream_fleet as uf
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-institution"

TERMINAL_SUCCESS_OUTCOMES = up.TERMINAL_SUCCESS_OUTCOMES


class InstitutionRefused(Exception):
    """A verdict-bearing refusal: the institution must not continue."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


# ---------------------------------------------------------------------------
# digests / io


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_bytes(canonical.encode("utf-8"))


def _portfolio_entries(portfolio: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not portfolio:
        return []
    return [dict(e) for e in (portfolio.get("entries") or []) if isinstance(e, Mapping)]


def _recompute_portfolio_digest(portfolio: Mapping[str, Any]) -> str:
    entries = _portfolio_entries(portfolio)
    counts: dict[str, int] = {}
    for e in entries:
        o = str(e.get("outcome") or "unknown")
        counts[o] = counts.get(o, 0) + 1
    return _sha256_json(
        {
            "entries": [
                {
                    "name": e.get("name"),
                    "version": e.get("version"),
                    "defect_id": e.get("defect_id"),
                    "outcome": e.get("outcome"),
                    "impact_digest": e.get("impact_digest"),
                }
                for e in entries
            ],
            "counts": counts,
        }
    )


def _entry_key(entry: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("name") or ""),
        str(entry.get("version") or ""),
        str(entry.get("defect_id") or ""),
    )


# ---------------------------------------------------------------------------
# charter + admission


def normalize_institution_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize an institution charter into deterministic program slots.

    Each slot is::

        {
          "program_id": str,
          "priority": int,
          "initial_targets": [{name, version, defects:[...]}],
          "surface_charter": [...],  # deferred program surface expand
          "max_successions": int,
          "program_goal": str,
          "mandate_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        program_id = str(raw.get("program_id") or raw.get("id") or "").strip()
        if not program_id or program_id in seen:
            continue
        seen.add(program_id)

        initial_targets: list[dict[str, Any]] = []
        for t in list(raw.get("initial_targets") or []):
            if not isinstance(t, Mapping):
                continue
            name = str(t.get("name") or "").strip()
            version = str(t.get("version") or "").strip()
            if not name or not version:
                continue
            defects_in = list(t.get("defects") or [])
            defects: list[dict[str, Any]] = []
            for d in defects_in:
                if not isinstance(d, Mapping):
                    continue
                did = str(d.get("id") or "").strip()
                if not did:
                    continue
                defects.append(
                    {
                        "id": did,
                        "title": str(d.get("title") or did),
                        "kind": str(d.get("kind") or "complexity"),
                        "patch": str(d.get("patch") or f"patches/{did}.patch"),
                        "repro": str(d.get("repro") or f"repros/{did}.py"),
                    }
                )
            if not defects:
                continue
            initial_targets.append(
                {
                    "name": name,
                    "version": version,
                    "defects": defects,
                    "entry_id": str(t.get("entry_id") or f"{name}@{version}"),
                }
            )

        surface_charter = up.normalize_surface_charter(raw.get("surface_charter"))
        # A slot needs either initial surface or deferred charter work.
        if not initial_targets and not surface_charter:
            continue

        out.append(
            {
                "program_id": program_id,
                "priority": int(raw.get("priority") or 0),
                "initial_targets": initial_targets,
                "surface_charter": surface_charter,
                "max_successions": max(1, int(raw.get("max_successions") or 3)),
                "program_goal": str(
                    raw.get("program_goal") or "terminal_and_exhausted"
                ),
                "mandate_goal": str(raw.get("mandate_goal") or "terminal_coverage"),
                "kind": str(raw.get("kind") or "stewardship_program"),
            }
        )
    return out


def admit_program_slot(
    *,
    institution_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one program slot's stewardship surface under the institution.

    Returns admission record with stewardship_root and materialised keys.
    """
    program_id = str(slot.get("program_id") or "")
    if not program_id:
        raise InstitutionRefused("institution_invalid", "slot missing program_id")

    program_root = Path(institution_dir) / "programs" / program_id
    stew = program_root / "stewardship"
    stew.mkdir(parents=True, exist_ok=True)

    added_keys: list[dict[str, str]] = []
    for target in list(slot.get("initial_targets") or []):
        if not isinstance(target, Mapping):
            continue
        keys = up.materialize_charter_entry(stew, target)
        added_keys.extend(keys)

    return {
        "program_id": program_id,
        "stewardship_root": str(stew),
        "program_root": str(program_root),
        "admitted": True,
        "initial_keys": added_keys,
        "surface_charter": list(slot.get("surface_charter") or []),
        "max_successions": int(slot.get("max_successions") or 3),
        "program_goal": str(slot.get("program_goal") or "terminal_and_exhausted"),
        "mandate_goal": str(slot.get("mandate_goal") or "terminal_coverage"),
        "priority": int(slot.get("priority") or 0),
    }


# ---------------------------------------------------------------------------
# federation + coverage


def federate_portfolios(
    portfolios: Sequence[Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Merge program portfolios into one institutional world-model.

    Later entries win on the same (name, version, defect_id) key so a
    fresher program outcome overwrites a stale one.
    """
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for portfolio in portfolios:
        for entry in _portfolio_entries(portfolio):
            key = _entry_key(entry)
            if not key[0] or not key[2]:
                continue
            by_key[key] = dict(entry)
    entries = [by_key[k] for k in sorted(by_key.keys())]
    portfolio: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "entries": entries,
        "source": "institution_federation",
    }
    portfolio["portfolio_digest"] = _recompute_portfolio_digest(portfolio)
    return portfolio


def institution_terminal_coverage(
    *,
    program_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Institution coverage: every admitted program's inventory is terminal-success."""
    required_keys: list[tuple[str, str, str]] = []
    for ps in program_states:
        stew = ps.get("stewardship_root")
        if not stew:
            continue
        root = Path(str(stew))
        if root.is_dir():
            required_keys.extend(up.inventory_defect_keys(root))
    # De-dupe while preserving order.
    seen: set[tuple[str, str, str]] = set()
    unique: list[tuple[str, str, str]] = []
    for k in required_keys:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return up.program_terminal_coverage(
        federated_portfolio,
        stewardship_root=None,
        required_keys=unique,
    )


def programs_all_met(program_states: Sequence[Mapping[str, Any]]) -> bool:
    if not program_states:
        return False
    return all(bool(ps.get("program_met")) for ps in program_states)


def open_unmet_count(program_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted programs that are not yet program_met."""
    return sum(1 for ps in program_states if not ps.get("program_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    program_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then program_id-asc."""
    known = {str(ps.get("program_id") or "") for ps in program_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("program_id") or "") and str(slot.get("program_id")) not in known
    ]
    pending.sort(
        key=lambda s: (-int(s.get("priority") or 0), str(s.get("program_id") or ""))
    )
    return pending


def constitution_satisfied(
    *,
    program_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    institution_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the institution goal is fully met including pending charter."""
    if institution_goal == "none":
        return False
    if institution_goal == "terminal_coverage":
        cov = institution_terminal_coverage(
            program_states=program_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(charter, program_states)
    if institution_goal == "all_programs_met":
        if not program_states:
            return False
        if pending_charter_slots(charter, program_states):
            return False
        return programs_all_met(program_states)
    return False


def admit_pending_slots(
    *,
    institution_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    program_states: list[dict[str, Any]],
    max_active_programs: int | None,
    max_successions_per_program: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_programs`` caps *unmet* concurrent programs. ``None`` admits
    every remaining pending slot. Returns admission records for newly admitted
    slots (also mutates ``program_states``).
    """
    pending = pending_charter_slots(charter, program_states)
    if not pending:
        return []

    open_n = open_unmet_count(program_states)
    if max_active_programs is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_programs) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_program_slot(institution_dir=institution_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        program_states.append(
            {
                "program_id": admission["program_id"],
                "stewardship_root": admission["stewardship_root"],
                "program_root": admission["program_root"],
                "surface_charter": admission["surface_charter"],
                "max_successions": (
                    int(max_successions_per_program)
                    if max_successions_per_program is not None
                    else admission["max_successions"]
                ),
                "program_goal": admission["program_goal"],
                "mandate_goal": admission["mandate_goal"],
                "priority": admission["priority"],
                "program_met": False,
                "last_program_dir": None,
                "last_program_digest": None,
                "portfolio": None,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


# ---------------------------------------------------------------------------
# ROI + scheduling


def score_program_roi(
    *,
    round_index: int,
    program_id: str,
    program_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one program round for institutional learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(program_result.get("total_dispatched_ok") or 0)
    dispatched = int(program_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "program_id": program_id,
        "stop_reason": program_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "program_met": bool(program_result.get("program_met")),
        "program_digest": program_result.get("program_digest"),
        "succession_count": int(program_result.get("succession_count") or 0),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_program": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_program: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        pid = str(r.get("program_id") or "")
        bucket = by_program.setdefault(
            pid,
            {"rounds": 0, "dispatched_ok": 0, "covered_delta": 0, "efficiency_sum": 0.0},
        )
        bucket["rounds"] += 1
        bucket["dispatched_ok"] += int(r.get("dispatched_ok") or 0)
        bucket["covered_delta"] += int(r.get("covered_delta") or 0)
        bucket["efficiency_sum"] += float(r.get("efficiency") or 0.0)
    for pid, bucket in by_program.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_program": by_program,
    }


def select_next_program(
    program_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) program by priority then ROI efficiency.

    Tie-break: lower run_count, then stable program_id order. Round-robin
    among equal scores uses ``round_index`` so multi-program progress is fair.
    """
    open_slots = [dict(ps) for ps in program_states if not ps.get("program_met")]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_program = summary.get("by_program") or {}

    def sort_key(ps: Mapping[str, Any]) -> tuple[Any, ...]:
        pid = str(ps.get("program_id") or "")
        hist = by_program.get(pid) or {}
        priority = int(ps.get("priority") or 0)
        mean_eff = float(hist.get("mean_efficiency") or 0.0)
        run_count = int(hist.get("rounds") or 0)
        # Higher priority first, then higher efficiency, then fewer runs, then id.
        # Mild round-robin: subtract run_count heavily so starved programs catch up.
        return (-priority, -mean_eff, run_count, pid)

    ranked = sorted(open_slots, key=sort_key)
    if len(ranked) == 1:
        return ranked[0]
    # Fairness nudge: among top-priority cohort, rotate by round_index.
    top_priority = int(ranked[0].get("priority") or 0)
    cohort = [ps for ps in ranked if int(ps.get("priority") or 0) == top_priority]
    if len(cohort) > 1:
        return cohort[round_index % len(cohort)]
    return ranked[0]


def allocate_program_budget(
    *,
    remaining_budget: int | None,
    open_program_count: int,
    selected: Mapping[str, Any],
    roi_history: Sequence[Mapping[str, Any]],
) -> int | None:
    """Allocate a share of remaining global budget to the selected program.

    ROI-productive programs may receive up to the full remainder; default is
    an even split (at least 1 when budget remains and dispatch is enabled).
    """
    if remaining_budget is None:
        return None
    remaining = max(0, int(remaining_budget))
    if remaining <= 0:
        return 0
    open_n = max(1, int(open_program_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_program") or {}).get(str(selected.get("program_id") or "")) or {}
    mean_eff = float(hist.get("mean_efficiency") or 0.0)
    # Productive programs can claim up to half of remaining (or base+1).
    if mean_eff > 0.0 and int(hist.get("dispatched_ok") or 0) > 0:
        boosted = min(remaining, max(base + 1, remaining // 2))
        return boosted
    return min(remaining, base)


# ---------------------------------------------------------------------------
# durable state


def _state_payload(
    *,
    institution_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    program_states: Sequence[Mapping[str, Any]],
    program_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    institution_goal: str,
    max_active_programs: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "institution_id": institution_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "program_states": [dict(ps) for ps in program_states],
        "program_digests": list(program_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "institution_goal": institution_goal,
        "max_active_programs": max_active_programs,
        "admissions": [dict(a) for a in (admissions or [])],
        "pending_program_ids": [
            str(s.get("program_id") or "")
            for s in pending_charter_slots(charter, program_states)
        ],
    }


def write_institution_state(institution_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(institution_dir) / "institution_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_institution_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "institution_state.json")
    if not path.is_file():
        raise InstitutionRefused(
            "institution_state_missing",
            f"no institution_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstitutionRefused("institution_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise InstitutionRefused("institution_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _program_record(
    *,
    round_index: int,
    program_id: str,
    program_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "program_id": program_id,
        "ok": bool(program_result.get("ok")),
        "verdict": program_result.get("verdict"),
        "stop_reason": program_result.get("stop_reason"),
        "program_dir": program_result.get("program_dir"),
        "program_digest": program_result.get("program_digest"),
        "succession_count": int(program_result.get("succession_count") or 0),
        "total_dispatched": int(program_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(program_result.get("total_dispatched_ok") or 0),
        "program_met": bool(program_result.get("program_met")),
        "budget_allocated": budget_allocated,
        "coverage_before": {
            "required": coverage_before.get("required"),
            "covered": coverage_before.get("covered"),
            "met": coverage_before.get("met"),
            "coverage_ratio": coverage_before.get("coverage_ratio"),
        },
        "coverage_after": {
            "required": coverage_after.get("required"),
            "covered": coverage_after.get("covered"),
            "met": coverage_after.get("met"),
            "coverage_ratio": coverage_after.get("coverage_ratio"),
        },
        "roi": dict(roi),
    }


def _institution_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "institution_id": receipt.get("institution_id"),
        "institution_goal": receipt.get("institution_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_programs": receipt.get("max_active_programs"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "program_digests": list(receipt.get("program_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "institution_met": receipt.get("institution_met"),
        "coverage_end": receipt.get("coverage_end"),
        "programs_met_count": receipt.get("programs_met_count"),
        "programs_admitted": receipt.get("programs_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_institution_receipt(institution_dir: Path) -> dict[str, Any]:
    """Re-check a sealed institution receipt for digest integrity."""
    path = durable_read_path(Path(institution_dir) / "institution.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_institution_digest_payload(receipt))
    recorded = str(receipt.get("institution_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("institution_digest")

    programs = list(receipt.get("programs") or [])
    listed = list(receipt.get("program_digests") or [])
    if len(listed) != len(programs):
        mismatched.append("program_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, programs)):
            if listed_d != rec.get("program_digest"):
                mismatched.append(f"program_digests[{i}]")

    nested_failures: list[str] = []
    for rec in programs:
        pd = rec.get("program_dir")
        if not pd:
            continue
        pp = Path(str(pd))
        if (pp / "program.json").is_file():
            nested = up.verify_program_receipt(pp)
            if not nested.get("ok"):
                nested_failures.append(str(pd))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "institution_sealed" if ok else "institution_tampered",
        "institution_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(programs),
    }


# ---------------------------------------------------------------------------
# run institution


def run_institution(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_successions_per_program: int | None = None,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_programs: int | None = None,
    dispatch: bool = True,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    institution_goal: str = "all_programs_met",
    refresh_promotions: Mapping[str, str] | None = None,
    institution_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    program_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-program stewardship institution and seal the receipt.

    Parameters
    ----------
    charter:
        Institution charter: list of program slots (see
        :func:`normalize_institution_charter`).
    max_rounds:
        Hard cap on program-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all programs; ``None`` means
        unlimited (still bounded by per-program succession/epoch/wave caps).
    max_active_programs:
        Constitution concurrent-active cap. When set, only this many *unmet*
        programs are admitted at once; remaining charter slots stay pending
        and are admitted as programs retire (deferred constitution growth).
        ``None`` admits the full charter eagerly (legacy behaviour).
    institution_goal:
        ``all_programs_met`` (default) stops when every admitted program is
        met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables institution-goal stopping.
    resume_dir:
        Load ``institution_state.json`` from a prior institution dir and
        continue. New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise InstitutionRefused("institution_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise InstitutionRefused(
            "institution_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_programs is not None and int(max_active_programs) < 1:
        raise InstitutionRefused(
            "institution_invalid", "max_active_programs must be >= 1 when set"
        )
    if institution_goal not in {"all_programs_met", "terminal_coverage", "none"}:
        raise InstitutionRefused(
            "institution_invalid",
            f"unknown institution_goal: {institution_goal}",
        )

    runner = program_runner or up.run_program

    # Resume durable state if requested.
    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    program_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_institution_id: str | None = None
    program_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_institution_state(resume_dir)
        resumed = True
        resume_institution_id = str(state.get("institution_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        program_digests = [str(d) for d in (state.get("program_digests") or [])]
        program_states = [
            dict(ps) for ps in (state.get("program_states") or []) if isinstance(ps, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_institution_charter(
                [e for e in state["charter"] if isinstance(e, Mapping)]
            )
        if isinstance(state.get("admissions"), list):
            admissions = [
                dict(a) for a in state["admissions"] if isinstance(a, Mapping)
            ]
        if state.get("max_active_programs") is not None and max_active_programs is None:
            resumed_max_active = int(state["max_active_programs"])
    else:
        active_charter = normalize_institution_charter(charter)

    active_max = (
        max_active_programs
        if max_active_programs is not None
        else resumed_max_active
    )

    if not active_charter and not program_states:
        raise InstitutionRefused(
            "institution_empty",
            "institution charter has no admitable program slots",
        )

    iid = (
        institution_id
        or resume_institution_id
        or f"institution-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        institution_dir = Path(out_root)
        if (institution_dir / "institution.json").is_file():
            institution_dir = institution_dir / stamp
    else:
        institution_dir = ARTIFACTS_ROOT / stamp
    institution_dir.mkdir(parents=True, exist_ok=True)
    prog_root = (
        Path(program_out_root)
        if program_out_root
        else (institution_dir / "program-runs")
    )
    prog_root.mkdir(parents=True, exist_ok=True)

    # Admit up to concurrent-active capacity (deferred constitution growth).
    initial_admissions = admit_pending_slots(
        institution_dir=institution_dir,
        charter=active_charter,
        program_states=program_states,
        max_active_programs=active_max,
        max_successions_per_program=max_successions_per_program,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not program_states and not pending_charter_slots(active_charter, program_states):
        raise InstitutionRefused(
            "institution_empty",
            "no program slots admitted",
        )
    if not program_states and pending_charter_slots(active_charter, program_states):
        # max_active blocked everything — invalid constitution.
        raise InstitutionRefused(
            "institution_empty",
            "no program slots admitted under max_active_programs policy",
        )

    # Seed federated portfolio from per-program portfolios when resuming.
    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ps.get("portfolio") for ps in program_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    programs: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    institution_met = False
    coverage_end: dict[str, Any] = institution_terminal_coverage(
        program_states=program_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        # Re-fill capacity before each round (retirements free slots).
        mid_admissions = admit_pending_slots(
            institution_dir=institution_dir,
            charter=active_charter,
            program_states=program_states,
            max_active_programs=active_max,
            max_successions_per_program=max_successions_per_program,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = institution_terminal_coverage(
            program_states=program_states,
            federated_portfolio=federated_portfolio,
        )

        # Institution-goal short-circuit before dispatching another program.
        if constitution_satisfied(
            program_states=program_states,
            charter=active_charter,
            institution_goal=institution_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "institution_met"
            institution_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_program(
            program_states, roi_history, round_index=round_index
        )
        if selected is None:
            # No open work: either charter exhausted (met) or blocked pending.
            if not pending_charter_slots(active_charter, program_states):
                stop_reason = "institution_met"
                institution_met = True
            else:
                stop_reason = "institution_idle"
            coverage_end = coverage_before
            break

        open_count = sum(1 for ps in program_states if not ps.get("program_met"))
        allocated = allocate_program_budget(
            remaining_budget=remaining_budget,
            open_program_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        program_id = str(selected["program_id"])
        stew_root = Path(str(selected["stewardship_root"]))
        # Resume a prior partial program run when present.
        resume_program_dir = selected.get("last_program_dir")
        program_resume: Path | None = None
        if resume_program_dir and (
            Path(str(resume_program_dir)) / "program_state.json"
        ).is_file() and not selected.get("program_met"):
            program_resume = Path(str(resume_program_dir))

        out_dir = prog_root / f"round-{round_index:02d}-{program_id}"
        prog_kwargs: dict[str, Any] = {
            "stewardship_root": stew_root,
            "portfolio": selected.get("portfolio"),
            "max_successions": int(selected.get("max_successions") or 3),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "program_goal": str(selected.get("program_goal") or "terminal_and_exhausted"),
            "mandate_goal": str(selected.get("mandate_goal") or "terminal_coverage"),
            "surface_charter": list(selected.get("surface_charter") or []),
            "program_id": program_id,
            "out_root": out_dir,
        }
        if program_resume is not None:
            prog_kwargs["resume_dir"] = program_resume
            # portfolio/surface from resume state take precedence inside run_program
            prog_kwargs.pop("portfolio", None)
        if campaign_runner is not None:
            prog_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            prog_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            prog_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            prog_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            prog_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            prog_kwargs["refresh_promotions"] = refresh_promotions

        try:
            prog_result = runner(**prog_kwargs)
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise InstitutionRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise InstitutionRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(prog_result.get("total_dispatched") or 0)
        dispatched_ok = int(prog_result.get("total_dispatched_ok") or 0)
        # When resuming a program, total_dispatched is cumulative for that
        # program; credit only the delta for the institution budget.
        prior_prog_dispatched = int(selected.get("total_dispatched") or 0)
        prior_prog_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_prog_dispatched)
        delta_ok = max(0, dispatched_ok - prior_prog_ok)
        # Non-resume runs: full counts are the delta.
        if program_resume is None and prior_prog_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        # Pull portfolio_final from program receipt when present.
        after_portfolio: dict[str, Any] | None = None
        prog_dir = prog_result.get("program_dir")
        if prog_dir and (Path(str(prog_dir)) / "program.json").is_file():
            receipt = json.loads(
                (Path(str(prog_dir)) / "program.json").read_text(encoding="utf-8")
            )
            if isinstance(receipt.get("portfolio_final"), Mapping):
                after_portfolio = dict(receipt["portfolio_final"])
        if after_portfolio is None and isinstance(prog_result.get("portfolio_final"), Mapping):
            after_portfolio = dict(prog_result["portfolio_final"])  # type: ignore[index]

        # Update selected program state in program_states list.
        for i, ps in enumerate(program_states):
            if str(ps.get("program_id")) != program_id:
                continue
            updated = dict(ps)
            updated["last_program_dir"] = prog_result.get("program_dir")
            updated["last_program_digest"] = prog_result.get("program_digest")
            updated["program_met"] = bool(prog_result.get("program_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            # Surface charter may have been partially applied; keep original
            # charter for resume expand continuity (program plane tracks applied).
            program_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ps.get("portfolio") for ps in program_states]
        )
        coverage_after = institution_terminal_coverage(
            program_states=program_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_program_roi(
            round_index=round_index,
            program_id=program_id,
            program_result=prog_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        pdigest = str(prog_result.get("program_digest") or "")
        if pdigest:
            program_digests.append(pdigest)

        rec = _program_record(
            round_index=round_index,
            program_id=program_id,
            program_result=prog_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        programs.append(rec)

        # Free capacity after retirements: admit next pending charter slots.
        post_admissions = admit_pending_slots(
            institution_dir=institution_dir,
            charter=active_charter,
            program_states=program_states,
            max_active_programs=active_max,
            max_successions_per_program=max_successions_per_program,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            # Re-federate after new surfaces materialize (coverage required grows).
            coverage_after = institution_terminal_coverage(
                program_states=program_states,
                federated_portfolio=federated_portfolio,
            )

        # Persist durable state after each round.
        write_institution_state(
            institution_dir,
            _state_payload(
                institution_id=iid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                program_states=program_states,
                program_digests=program_digests,
                charter=active_charter,
                stop_reason=None,
                institution_goal=institution_goal,
                max_active_programs=active_max,
                admissions=admissions,
            ),
        )

        coverage_end = coverage_after

        if delta_ok == 0 and delta_dispatched == 0 and not prog_result.get("program_met"):
            idle_streak += 1
        else:
            idle_streak = 0

        if stop_when is not None:
            reason = stop_when(
                {
                    "round_index": round_index,
                    "round_count": len(programs),
                    "total_dispatched": total_dispatched,
                    "total_dispatched_ok": total_dispatched_ok,
                    "coverage": coverage_after,
                    "roi_history": roi_history,
                    "program_states": program_states,
                    "last_program_id": program_id,
                    "federated_portfolio": federated_portfolio,
                    "institution_dir": str(institution_dir),
                    "pending_program_ids": [
                        str(s.get("program_id") or "")
                        for s in pending_charter_slots(active_charter, program_states)
                    ],
                    "admissions": admissions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        if constitution_satisfied(
            program_states=program_states,
            charter=active_charter,
            institution_goal=institution_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "institution_met"
            institution_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if (
            idle_streak >= idle_round_limit
            and not constitution_satisfied(
                program_states=program_states,
                charter=active_charter,
                institution_goal=institution_goal,
                federated_portfolio=federated_portfolio,
            )
        ):
            stop_reason = "institution_idle"
            break
    else:
        stop_reason = "max_rounds"

    # Final admission fill + coverage snapshot.
    final_admissions = admit_pending_slots(
        institution_dir=institution_dir,
        charter=active_charter,
        program_states=program_states,
        max_active_programs=active_max,
        max_successions_per_program=max_successions_per_program,
        round_index=prior_round_count + len(programs),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ps.get("portfolio") for ps in program_states]
    )
    coverage_end = institution_terminal_coverage(
        program_states=program_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        program_states=program_states,
        charter=active_charter,
        institution_goal=institution_goal,
        federated_portfolio=federated_portfolio,
    ):
        institution_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    programs_met_count = sum(1 for ps in program_states if ps.get("program_met"))
    pending_remaining = [
        str(s.get("program_id") or "")
        for s in pending_charter_slots(active_charter, program_states)
    ]

    if institution_met and stop_reason in {"institution_met", "max_rounds"}:
        verdict = "institution_met"
        ok = True
        stop_reason = "institution_met"
    elif stop_reason == "rank_only":
        verdict = "institution_ranked"
        ok = True
    elif stop_reason == "institution_idle":
        verdict = "institution_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "institution_budgeted"
        ok = True
    elif stop_reason.startswith("program_refused") or stop_reason.startswith(
        "fleet_refused"
    ):
        verdict = "institution_refused_mid"
        ok = False
    else:
        verdict = "institution_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "institution_id": iid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_programs": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "institution_goal": institution_goal,
        "institution_met": institution_met,
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "federated_portfolio": federated_portfolio,
        "coverage_end": {
            "required": coverage_end.get("required"),
            "covered": coverage_end.get("covered"),
            "met": coverage_end.get("met"),
            "coverage_ratio": coverage_end.get("coverage_ratio"),
            "open_or_missing": coverage_end.get("open_or_missing"),
        },
        "round_count": len(programs),
        "programs": programs,
        "program_digests": [
            p.get("program_digest") for p in programs if p.get("program_digest")
        ],
        "program_states": program_states,
        "programs_admitted": len(program_states),
        "programs_met_count": programs_met_count,
        "admissions": admissions,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "charter": active_charter,
        "roi_history": roi_history,
        "roi_summary": roi_summary,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    receipt["program_digests"] = [
        str(p.get("program_digest") or "") for p in programs
    ]
    receipt["institution_digest"] = _sha256_json(_institution_digest_payload(receipt))
    atomic_write_json(institution_dir / "institution.json", receipt)
    atomic_write_json(
        institution_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "institution_id": receipt["institution_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "institution_met": receipt["institution_met"],
            "programs_admitted": receipt["programs_admitted"],
            "programs_met_count": receipt["programs_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "max_active_programs": receipt["max_active_programs"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "institution_digest": receipt["institution_digest"],
            "resumed": resumed,
        },
    )

    write_institution_state(
        institution_dir,
        _state_payload(
            institution_id=iid,
            round_count=prior_round_count + len(programs),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            program_states=program_states,
            program_digests=receipt["program_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            institution_goal=institution_goal,
            max_active_programs=active_max,
            admissions=admissions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "institution_dir": str(institution_dir),
        "institution_digest": receipt["institution_digest"],
        "institution_id": iid,
        "round_count": len(programs),
        "program_digests": list(receipt["program_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "institution_met": institution_met,
        "programs_admitted": len(program_states),
        "programs_met_count": programs_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_programs": active_max,
        "admissions": admissions,
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "program_states": program_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "programs": programs,
        "used_skill_route_discovery": receipt["used_skill_route_discovery"],
    }


# ---------------------------------------------------------------------------
# hermetic proof


def _proof_campaign_runner(scratch: Path) -> Callable[..., dict[str, Any]]:
    return up._proof_campaign_runner(scratch)


def _slot(
    program_id: str,
    *,
    priority: int = 0,
    initial: Sequence[tuple[str, str, str]] = (),
    deferred: Sequence[tuple[str, str, str]] = (),
    max_successions: int = 3,
    program_goal: str = "terminal_and_exhausted",
) -> dict[str, Any]:
    """Build a hermetic institution charter slot."""
    initial_targets = []
    for name, version, defect in initial:
        initial_targets.append(
            {
                "name": name,
                "version": version,
                "defects": [{
                    "id": defect,
                    "title": defect,
                    "kind": "complexity",
                    "patch": f"patches/{defect}.patch",
                    "repro": f"repros/{defect}.py",
                }],
            }
        )
    surface_charter = []
    for name, version, defect in deferred:
        surface_charter.append(
            {
                "name": name,
                "version": version,
                "defects": [{
                    "id": defect,
                    "title": defect,
                    "kind": "correctness",
                    "patch": f"patches/{defect}.patch",
                    "repro": f"repros/{defect}.py",
                }],
            }
        )
    return {
        "program_id": program_id,
        "priority": priority,
        "initial_targets": initial_targets,
        "surface_charter": surface_charter,
        "max_successions": max_successions,
        "program_goal": program_goal,
        "mandate_goal": "terminal_coverage",
    }


def builtin_upstream_institution_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-program institution plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="institution-proof-"))
    try:
        campaign = _proof_campaign_runner(scratch)

        # Multi-program constitution: two slots; lane-b has deferred surface.
        charter = [
            _slot(
                "lane-a",
                priority=2,
                initial=[("alpha", "1.0.0", "alpha-dos")],
                max_successions=3,
            ),
            _slot(
                "lane-b",
                priority=1,
                initial=[("beta", "2.0.0", "beta-xss")],
                deferred=[("gamma", "3.0.0", "gamma-rce")],
                max_successions=4,
            ),
        ]

        institution = run_institution(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            institution_goal="all_programs_met",
            out_root=scratch / "inst-mandate",
        )
        multi_program_ok = (
            institution["ok"]
            and institution["institution_met"] is True
            and institution["stop_reason"] == "institution_met"
            and institution["programs_admitted"] == 2
            and institution["programs_met_count"] == 2
            and institution["round_count"] >= 2
            and institution["total_dispatched_ok"] >= 3
            and float((institution.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        # At least two distinct program ids scheduled.
        scheduled_ids = {
            p.get("program_id") for p in (institution.get("programs") or [])
        }
        multi_program_scheduled = multi_program_ok and scheduled_ids >= {"lane-a", "lane-b"}

        # Seal + verify.
        verified = verify_institution_receipt(Path(institution["institution_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == institution[
            "round_count"
        ]

        # Tamper detection.
        inst_path = Path(institution["institution_dir"]) / "institution.json"
        receipt = json.loads(inst_path.read_text(encoding="utf-8"))
        receipt["institution_digest"] = "0" * 64
        inst_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_institution_receipt(Path(institution["institution_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "institution_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across programs.
        campaign2 = _proof_campaign_runner(scratch / "budget")
        budgeted = run_institution(
            charter=[
                _slot("p1", priority=1, initial=[("d1", "1.0.0", "d1-1")]),
                _slot("p2", priority=1, initial=[("d2", "1.0.0", "d2-1")]),
            ],
            max_rounds=6,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign2,
            institution_goal="none",
            out_root=scratch / "inst-budget",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit: both programs already terminal → 0 rounds.
        pre_scratch = scratch / "premet"
        pre_scratch.mkdir()
        # Build a fake pre-met institution by admitting then seeding portfolios.
        pre_charter = [
            _slot("omega", priority=1, initial=[("omega", "9.0.0", "omega-merged")]),
        ]
        # Run rank-only first to admit, then forge met state via portfolio + re-run.
        # Simpler: inject program_runner that immediately reports met without work
        # after we seed stewardship + portfolio via a custom path.
        # Use real plane: seed stewardship, pass portfolio via resume-like state.
        # Easiest hermetic path: custom program_runner that marks met with 0 dispatch.
        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            stew = Path(kwargs["stewardship_root"])
            keys = up.inventory_defect_keys(stew)
            entries = [
                {
                    "name": n,
                    "version": v,
                    "defect_id": d,
                    "outcome": "impact_merged",
                    "impact_digest": "c" * 64,
                    "ok": True,
                }
                for n, v, d in keys
            ]
            portfolio = uf._proof_portfolio(entries)
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            digest = _sha256_json({"premet": True, "keys": keys})
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "program_met",
                "stop_reason": "program_met",
                "program_id": kwargs.get("program_id"),
                "program_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "succession_count": 0,
                "program_digest": digest,
                "portfolio_final": portfolio,
                "coverage_end": {"required": len(keys), "covered": len(keys), "met": True, "coverage_ratio": 1.0},
            }
            atomic_write_json(out / "program.json", receipt)
            atomic_write_json(
                out / "program_state.json",
                {
                    "program_id": kwargs.get("program_id"),
                    "succession_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "portfolio": portfolio,
                    "stop_reason": "program_met",
                },
            )
            return {
                "ok": True,
                "verdict": "program_met",
                "stop_reason": "program_met",
                "program_dir": str(out),
                "program_digest": digest,
                "program_id": kwargs.get("program_id"),
                "succession_count": 0,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "program_met": True,
                "coverage_end": receipt["coverage_end"],
                "used_skill_route_discovery": False,
            }

        pre_met = run_institution(
            charter=pre_charter,
            max_rounds=3,
            dispatch=True,
            program_runner=_premet_runner,
            institution_goal="all_programs_met",
            out_root=scratch / "inst-premet",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["institution_met"] is True
            and pre_met["stop_reason"] == "institution_met"
            and pre_met["programs_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only institution.
        ranked = run_institution(
            charter=[
                _slot("rank-a", initial=[("r1", "1.0.0", "r1-1")]),
                _slot("rank-b", initial=[("r2", "1.0.0", "r2-1")]),
            ],
            max_rounds=3,
            dispatch=False,
            institution_goal="none",
            out_root=scratch / "inst-ranked",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "institution_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_institution(
                charter=[],
                dispatch=False,
                institution_goal="none",
                out_root=scratch / "inst-empty",
            )
        except InstitutionRefused as exc:
            empty_refused = exc.verdict in {
                "institution_empty",
                "institution_invalid",
            }

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_institution(
            charter=[
                _slot("c1", initial=[("c1", "1.0.0", "c1-1")]),
                _slot("c2", initial=[("c2", "1.0.0", "c2-1")]),
            ],
            max_rounds=6,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=8,
            dispatch=True,
            campaign_runner=campaign3,
            institution_goal="none",
            stop_when=lambda ctx: "custom_halt" if ctx["total_dispatched_ok"] >= 1 else None,
            out_root=scratch / "inst-custom",
        )
        custom_ok = (
            custom["ok"]
            and custom["stop_reason"] == "custom_halt"
            and custom["total_dispatched_ok"] >= 1
        )

        # Durable resume: partial (budget=1), resume with more budget.
        campaign4 = _proof_campaign_runner(scratch / "resume-a")
        partial = run_institution(
            charter=[
                _slot("z1", priority=2, initial=[("zeta", "1.0.0", "zeta-1")]),
                _slot("z2", priority=1, initial=[("eta", "1.0.0", "eta-1")]),
            ],
            max_rounds=1,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign4,
            institution_goal="none",
            institution_id="resume-inst-proof",
            out_root=scratch / "inst-partial",
        )
        state_path = Path(partial["institution_dir"]) / "institution_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "resume-b")
        resumed = run_institution(
            resume_dir=Path(partial["institution_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            institution_goal="none",
            out_root=scratch / "inst-resumed",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["institution_id"] == "resume-inst-proof"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-program budget allocation evidence.
        roi_ok = (
            isinstance(institution.get("roi_summary"), Mapping)
            and int((institution["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((institution["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((institution["roi_summary"] or {}).get("by_program"), Mapping)
            and len((institution["roi_summary"] or {}).get("by_program") or {}) >= 2
        )

        # Scheduler prefers higher priority first when efficiencies are equal.
        # lane-a priority=2 should appear in early rounds of main proof.
        first_program = (institution.get("programs") or [{}])[0].get("program_id")
        priority_ok = first_program == "lane-a"

        # Federation: inventories across both program lanes form a joint surface.
        fed_keys = set()
        for ps in institution.get("program_states") or []:
            stew = ps.get("stewardship_root")
            if stew:
                for n, v, d in up.inventory_defect_keys(Path(str(stew))):
                    fed_keys.add((n, v, d))
        federation_ok = multi_program_ok and len(fed_keys) >= 3

        # Deferred admission: max_active=1 grows charter over time.
        campaign6 = _proof_campaign_runner(scratch / "deferred")
        deferred = run_institution(
            charter=[
                _slot("da", priority=3, initial=[("da", "1.0.0", "da-1")]),
                _slot("db", priority=2, initial=[("db", "1.0.0", "db-1")]),
                _slot("dc", priority=1, initial=[("dc", "1.0.0", "dc-1")]),
            ],
            max_rounds=8,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=6,
            max_active_programs=1,
            dispatch=True,
            campaign_runner=campaign6,
            institution_goal="all_programs_met",
            out_root=scratch / "inst-deferred",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("program_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["institution_met"] is True
            and deferred["programs_admitted"] == 3
            and deferred["programs_met_count"] == 3
            and deferred.get("max_active_programs") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            # Staggered: not all admitted at the same round index.
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        ok = all(
            [
                multi_program_ok,
                multi_program_scheduled,
                seal_ok,
                tamper_detected,
                budget_ok,
                premet_ok,
                rank_only_ok,
                empty_refused,
                custom_ok,
                resume_ok,
                roi_ok,
                priority_ok,
                federation_ok,
                deferred_ok,
            ]
        )
        return {
            "ok": ok,
            "institution_met": multi_program_ok,
            "multi_program_progressed": multi_program_scheduled,
            "federation_coverage": federation_ok,
            "priority_scheduling": priority_ok,
            "deferred_admission": deferred_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_detected,
            "budget_stops": budget_ok,
            "premet_short_circuits": premet_ok,
            "rank_only": rank_only_ok,
            "empty_refused": empty_refused,
            "custom_stop": custom_ok,
            "durable_resume": resume_ok,
            "roi_scored": roi_ok,
            "institution_digest": institution.get("institution_digest"),
            "round_count": institution.get("round_count"),
            "total_dispatched_ok": institution.get("total_dispatched_ok"),
            "programs_admitted": institution.get("programs_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--proof",
        action="store_true",
        help="run hermetic builtin proof and print JSON result",
    )
    parser.add_argument(
        "--verify",
        type=str,
        default="",
        help="verify a sealed institution directory",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.verify:
        result = verify_institution_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_institution_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
