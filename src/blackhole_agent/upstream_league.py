"""Upstream league plane: multi-institution durable stewardship federation.

The institution plane (``upstream_institution``) closes multi-program
constitutions *within one institution*. It does not:

1. chain multiple independent institutions under a durable league constitution;
2. allocate a shared global dispatch budget across institutions by ROI;
3. admit/retire institution slots from a league charter over time
   (deferred admission under a concurrent-active cap);
4. federate multi-institution portfolio coverage into one league world-model;
5. persist league state so a later process can resume the federation;
6. seal a multi-institution league chronicle linking institution digests.

The league plane closes that outer federated loop:

1. **admit** — materialize institution slots from a durable league charter
   (each slot owns a nested program charter). When ``max_active_institutions``
   is set, only that many *unmet* institutions are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (league constitution growth over time);
2. **schedule** — pick the next open institution by priority and historical ROI;
3. **institution** — call the institution plane (injected ``institution_runner``;
   default ``run_institution``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-institution portfolios into one league world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark institutions met when their institution_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **persist** — write ``league_state.json`` after every institution round so a
   later ``run_league(..., resume_dir=...)`` continues the same federation
   (including pending charter and admission history);
7. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across institutions
   - league goal met (``all_institutions_met``: every *admitted* institution is
     met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

8. **seal** — write a league receipt under ``artifacts/upstream-league/`` with
   sha256 digests of every institution, portfolio federation, admission
   history, ROI history, stop reason, and a league chain digest;
   ``verify_league_receipt`` re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is federation-level direction over
the institution plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_institution as ui
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-league"

TERMINAL_SUCCESS_OUTCOMES = ui.TERMINAL_SUCCESS_OUTCOMES


class LeagueRefused(Exception):
    """A verdict-bearing refusal: the league must not continue."""

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


def normalize_league_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a league charter into deterministic institution slots.

    Each slot is::

        {
          "institution_id": str,
          "priority": int,
          "charter": [...program slots...],  # institution program charter
          "max_active_programs": int | None,
          "max_successions_per_program": int | None,
          "max_rounds": int,
          "institution_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        institution_id = str(
            raw.get("institution_id") or raw.get("id") or ""
        ).strip()
        if not institution_id or institution_id in seen:
            continue
        seen.add(institution_id)

        nested = ui.normalize_institution_charter(raw.get("charter") or raw.get("programs"))
        if not nested:
            continue

        max_active_programs = raw.get("max_active_programs")
        if max_active_programs is not None:
            max_active_programs = max(1, int(max_active_programs))

        max_successions = raw.get("max_successions_per_program")
        if max_successions is not None:
            max_successions = max(1, int(max_successions))

        out.append(
            {
                "institution_id": institution_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_programs": max_active_programs,
                "max_successions_per_program": max_successions,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "institution_goal": str(
                    raw.get("institution_goal") or "all_programs_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_institution"),
            }
        )
    return out


def admit_institution_slot(
    *,
    league_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with institution_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    institution_id = str(slot.get("institution_id") or "")
    if not institution_id:
        raise LeagueRefused("league_invalid", "slot missing institution_id")

    institution_root = Path(league_dir) / "institutions" / institution_id
    institution_root.mkdir(parents=True, exist_ok=True)

    nested_charter = ui.normalize_institution_charter(slot.get("charter"))
    if not nested_charter:
        raise LeagueRefused(
            "league_invalid",
            f"institution slot {institution_id!r} has empty nested charter",
        )

    return {
        "institution_id": institution_id,
        "institution_root": str(institution_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_programs": slot.get("max_active_programs"),
        "max_successions_per_program": slot.get("max_successions_per_program"),
        "max_rounds": int(slot.get("max_rounds") or 6),
        "institution_goal": str(slot.get("institution_goal") or "all_programs_met"),
        "priority": int(slot.get("priority") or 0),
    }


# ---------------------------------------------------------------------------
# federation + coverage


def federate_portfolios(
    portfolios: Sequence[Mapping[str, Any] | None],
) -> dict[str, Any]:
    """Merge institution portfolios into one league world-model.

    Later entries win on the same (name, version, defect_id) key so a
    fresher institution outcome overwrites a stale one.
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
        "source": "league_federation",
    }
    portfolio["portfolio_digest"] = _recompute_portfolio_digest(portfolio)
    return portfolio


def league_terminal_coverage(
    *,
    institution_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """League coverage: every admitted institution's inventory is terminal-success."""
    required_keys: list[tuple[str, str, str]] = []
    for ist in institution_states:
        # Prefer explicit inventory keys when present (resume / pre-seeded).
        for raw in list(ist.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                required_keys.append((str(raw[0]), str(raw[1]), str(raw[2])))
                continue
            if isinstance(raw, Mapping):
                n = str(raw.get("name") or "")
                v = str(raw.get("version") or "")
                d = str(raw.get("defect_id") or raw.get("id") or "")
                if n and d:
                    required_keys.append((n, v, d))
        # Also scan program stewardship roots from nested institution state.
        for ps in list(ist.get("program_states") or []):
            if not isinstance(ps, Mapping):
                continue
            stew = ps.get("stewardship_root")
            if not stew:
                continue
            root = Path(str(stew))
            if root.is_dir():
                required_keys.extend(up.inventory_defect_keys(root))
        # Nested charter keys when surfaces not yet materialized.
        for slot in list(ist.get("charter") or []):
            if not isinstance(slot, Mapping):
                continue
            for t in list(slot.get("initial_targets") or []) + list(
                slot.get("surface_charter") or []
            ):
                if not isinstance(t, Mapping):
                    continue
                name = str(t.get("name") or "")
                version = str(t.get("version") or "")
                for d in list(t.get("defects") or []):
                    if not isinstance(d, Mapping):
                        continue
                    did = str(d.get("id") or "")
                    if name and did:
                        required_keys.append((name, version, did))

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


def institutions_all_met(institution_states: Sequence[Mapping[str, Any]]) -> bool:
    if not institution_states:
        return False
    return all(bool(ist.get("institution_met")) for ist in institution_states)


def open_unmet_count(institution_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet institution_met."""
    return sum(1 for ist in institution_states if not ist.get("institution_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    institution_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then institution_id-asc."""
    known = {str(ist.get("institution_id") or "") for ist in institution_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("institution_id") or "")
        and str(slot.get("institution_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("institution_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    institution_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    league_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if league_goal == "none":
        return False
    if league_goal == "terminal_coverage":
        cov = league_terminal_coverage(
            institution_states=institution_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, institution_states
        )
    if league_goal == "all_institutions_met":
        if not institution_states:
            return False
        if pending_charter_slots(charter, institution_states):
            return False
        return institutions_all_met(institution_states)
    return False


def admit_pending_slots(
    *,
    league_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    institution_states: list[dict[str, Any]],
    max_active_institutions: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_institutions`` caps *unmet* concurrent institutions. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``institution_states``).
    """
    pending = pending_charter_slots(charter, institution_states)
    if not pending:
        return []

    open_n = open_unmet_count(institution_states)
    if max_active_institutions is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_institutions) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_institution_slot(league_dir=league_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        institution_states.append(
            {
                "institution_id": admission["institution_id"],
                "institution_root": admission["institution_root"],
                "charter": admission["charter"],
                "max_active_programs": admission["max_active_programs"],
                "max_successions_per_program": admission[
                    "max_successions_per_program"
                ],
                "max_rounds": admission["max_rounds"],
                "institution_goal": admission["institution_goal"],
                "priority": admission["priority"],
                "institution_met": False,
                "last_institution_dir": None,
                "last_institution_digest": None,
                "portfolio": None,
                "program_states": [],
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


# ---------------------------------------------------------------------------
# ROI + scheduling


def score_institution_roi(
    *,
    round_index: int,
    institution_id: str,
    institution_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one institution round for league learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(institution_result.get("total_dispatched_ok") or 0)
    dispatched = int(institution_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "institution_id": institution_id,
        "stop_reason": institution_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "institution_met": bool(institution_result.get("institution_met")),
        "institution_digest": institution_result.get("institution_digest"),
        "programs_admitted": int(institution_result.get("programs_admitted") or 0),
        "programs_met_count": int(institution_result.get("programs_met_count") or 0),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_institution": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_institution: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get("institution_id") or "")
        bucket = by_institution.setdefault(
            iid,
            {
                "rounds": 0,
                "dispatched_ok": 0,
                "covered_delta": 0,
                "efficiency_sum": 0.0,
            },
        )
        bucket["rounds"] += 1
        bucket["dispatched_ok"] += int(r.get("dispatched_ok") or 0)
        bucket["covered_delta"] += int(r.get("covered_delta") or 0)
        bucket["efficiency_sum"] += float(r.get("efficiency") or 0.0)
    for iid, bucket in by_institution.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_institution": by_institution,
    }


def select_next_institution(
    institution_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable institution_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in institution_states if not ist.get("institution_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_institution = summary.get("by_institution") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("institution_id") or "")
        hist = by_institution.get(iid) or {}
        priority = int(ist.get("priority") or 0)
        mean_eff = float(hist.get("mean_efficiency") or 0.0)
        run_count = int(hist.get("rounds") or 0)
        return (-priority, -mean_eff, run_count, iid)

    ranked = sorted(open_slots, key=sort_key)
    if len(ranked) == 1:
        return ranked[0]
    top_priority = int(ranked[0].get("priority") or 0)
    cohort = [ist for ist in ranked if int(ist.get("priority") or 0) == top_priority]
    if len(cohort) > 1:
        return cohort[round_index % len(cohort)]
    return ranked[0]


def allocate_institution_budget(
    *,
    remaining_budget: int | None,
    open_institution_count: int,
    selected: Mapping[str, Any],
    roi_history: Sequence[Mapping[str, Any]],
) -> int | None:
    """Allocate a share of remaining global budget to the selected institution.

    ROI-productive institutions may receive up to the full remainder; default is
    an even split (at least 1 when budget remains and dispatch is enabled).
    """
    if remaining_budget is None:
        return None
    remaining = max(0, int(remaining_budget))
    if remaining <= 0:
        return 0
    open_n = max(1, int(open_institution_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_institution") or {}).get(
        str(selected.get("institution_id") or "")
    ) or {}
    mean_eff = float(hist.get("mean_efficiency") or 0.0)
    if mean_eff > 0.0 and int(hist.get("dispatched_ok") or 0) > 0:
        boosted = min(remaining, max(base + 1, remaining // 2))
        return boosted
    return min(remaining, base)


# ---------------------------------------------------------------------------
# durable state


def _state_payload(
    *,
    league_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    institution_states: Sequence[Mapping[str, Any]],
    institution_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    league_goal: str,
    max_active_institutions: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "league_id": league_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "institution_states": [dict(ist) for ist in institution_states],
        "institution_digests": list(institution_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "league_goal": league_goal,
        "max_active_institutions": max_active_institutions,
        "admissions": [dict(a) for a in (admissions or [])],
        "pending_institution_ids": [
            str(s.get("institution_id") or "")
            for s in pending_charter_slots(charter, institution_states)
        ],
    }


def write_league_state(league_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(league_dir) / "league_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_league_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "league_state.json")
    if not path.is_file():
        raise LeagueRefused(
            "league_state_missing",
            f"no league_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LeagueRefused("league_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise LeagueRefused("league_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _institution_record(
    *,
    round_index: int,
    institution_id: str,
    institution_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "institution_id": institution_id,
        "ok": bool(institution_result.get("ok")),
        "verdict": institution_result.get("verdict"),
        "stop_reason": institution_result.get("stop_reason"),
        "institution_dir": institution_result.get("institution_dir"),
        "institution_digest": institution_result.get("institution_digest"),
        "programs_admitted": int(institution_result.get("programs_admitted") or 0),
        "programs_met_count": int(institution_result.get("programs_met_count") or 0),
        "total_dispatched": int(institution_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(institution_result.get("total_dispatched_ok") or 0),
        "institution_met": bool(institution_result.get("institution_met")),
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


def _league_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "league_id": receipt.get("league_id"),
        "league_goal": receipt.get("league_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_institutions": receipt.get("max_active_institutions"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "institution_digests": list(receipt.get("institution_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "league_met": receipt.get("league_met"),
        "coverage_end": receipt.get("coverage_end"),
        "institutions_met_count": receipt.get("institutions_met_count"),
        "institutions_admitted": receipt.get("institutions_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_league_receipt(league_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(league_dir) / "league.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_league_digest_payload(receipt))
    recorded = str(receipt.get("league_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("league_digest")

    institutions = list(receipt.get("institutions") or [])
    listed = list(receipt.get("institution_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("institution_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("institution_digest"):
                mismatched.append(f"institution_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("institution_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "institution.json").is_file():
            nested = ui.verify_institution_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "league_sealed" if ok else "league_tampered",
        "league_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run league


def run_league(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_institutions: int | None = None,
    dispatch: bool = True,
    institution_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    league_goal: str = "all_institutions_met",
    refresh_promotions: Mapping[str, str] | None = None,
    league_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    institution_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_league_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_institutions:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    league_goal:
        ``all_institutions_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``league_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise LeagueRefused("league_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise LeagueRefused(
            "league_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_institutions is not None and int(max_active_institutions) < 1:
        raise LeagueRefused(
            "league_invalid", "max_active_institutions must be >= 1 when set"
        )
    if league_goal not in {"all_institutions_met", "terminal_coverage", "none"}:
        raise LeagueRefused(
            "league_invalid",
            f"unknown league_goal: {league_goal}",
        )

    runner = institution_runner or ui.run_institution

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    institution_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_league_id: str | None = None
    institution_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_league_state(resume_dir)
        resumed = True
        resume_league_id = str(state.get("league_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        institution_digests = [str(d) for d in (state.get("institution_digests") or [])]
        institution_states = [
            dict(ist)
            for ist in (state.get("institution_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_league_charter(
                [e for e in state["charter"] if isinstance(e, Mapping)]
            )
        if isinstance(state.get("admissions"), list):
            admissions = [
                dict(a) for a in state["admissions"] if isinstance(a, Mapping)
            ]
        if (
            state.get("max_active_institutions") is not None
            and max_active_institutions is None
        ):
            resumed_max_active = int(state["max_active_institutions"])
    else:
        active_charter = normalize_league_charter(charter)

    active_max = (
        max_active_institutions
        if max_active_institutions is not None
        else resumed_max_active
    )

    if not active_charter and not institution_states:
        raise LeagueRefused(
            "league_empty",
            "league charter has no admitable institution slots",
        )

    lid = (
        league_id
        or resume_league_id
        or f"league-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        league_dir = Path(out_root)
        if (league_dir / "league.json").is_file():
            league_dir = league_dir / stamp
    else:
        league_dir = ARTIFACTS_ROOT / stamp
    league_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    inst_root = (
        Path(institution_out_root) if institution_out_root else (league_dir / "ir")
    )
    inst_root.mkdir(parents=True, exist_ok=True)
    prog_flat_root = league_dir / "pr"
    prog_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        league_dir=league_dir,
        charter=active_charter,
        institution_states=institution_states,
        max_active_institutions=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not institution_states and not pending_charter_slots(
        active_charter, institution_states
    ):
        raise LeagueRefused("league_empty", "no institution slots admitted")
    if not institution_states and pending_charter_slots(
        active_charter, institution_states
    ):
        raise LeagueRefused(
            "league_empty",
            "no institution slots admitted under max_active_institutions policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in institution_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    league_met = False
    coverage_end: dict[str, Any] = league_terminal_coverage(
        institution_states=institution_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            league_dir=league_dir,
            charter=active_charter,
            institution_states=institution_states,
            max_active_institutions=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = league_terminal_coverage(
            institution_states=institution_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            institution_states=institution_states,
            charter=active_charter,
            league_goal=league_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "league_met"
            league_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_institution(
            institution_states, roi_history, round_index=round_index
        )
        if selected is None:
            if not pending_charter_slots(active_charter, institution_states):
                stop_reason = "league_met"
                league_met = True
            else:
                stop_reason = "league_idle"
            coverage_end = coverage_before
            break

        open_count = sum(
            1 for ist in institution_states if not ist.get("institution_met")
        )
        allocated = allocate_institution_budget(
            remaining_budget=remaining_budget,
            open_institution_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        institution_id = str(selected["institution_id"])
        resume_inst_dir = selected.get("last_institution_dir")
        institution_resume: Path | None = None
        if (
            resume_inst_dir
            and (Path(str(resume_inst_dir)) / "institution_state.json").is_file()
            and not selected.get("institution_met")
        ):
            institution_resume = Path(str(resume_inst_dir))

        # Short stamp: r00-ia (avoid deep Windows paths under succession/epoch/wave).
        safe_id = "".join(c if c.isalnum() else "" for c in institution_id)[:12] or "i"
        out_dir = inst_root / f"r{round_index:02d}-{safe_id}"
        prog_out = prog_flat_root / f"r{round_index:02d}-{safe_id}"
        inst_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "institution_goal": str(
                selected.get("institution_goal") or "all_programs_met"
            ),
            "institution_id": institution_id,
            "out_root": out_dir,
            "program_out_root": prog_out,
        }
        if selected.get("max_active_programs") is not None:
            inst_kwargs["max_active_programs"] = int(selected["max_active_programs"])
        if selected.get("max_successions_per_program") is not None:
            inst_kwargs["max_successions_per_program"] = int(
                selected["max_successions_per_program"]
            )
        if institution_resume is not None:
            inst_kwargs["resume_dir"] = institution_resume
            # charter already on resume state
            inst_kwargs.pop("charter", None)
        if program_runner is not None:
            inst_kwargs["program_runner"] = program_runner
        if campaign_runner is not None:
            inst_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            inst_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            inst_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            inst_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            inst_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            inst_kwargs["refresh_promotions"] = refresh_promotions

        try:
            inst_result = runner(**inst_kwargs)
        except ui.InstitutionRefused as exc:
            if local_index == 0 and not resumed:
                raise LeagueRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"institution_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise LeagueRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise LeagueRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(inst_result.get("total_dispatched") or 0)
        dispatched_ok = int(inst_result.get("total_dispatched_ok") or 0)
        prior_inst_dispatched = int(selected.get("total_dispatched") or 0)
        prior_inst_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_inst_dispatched)
        delta_ok = max(0, dispatched_ok - prior_inst_ok)
        if institution_resume is None and prior_inst_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        inst_dir = inst_result.get("institution_dir")
        nested_program_states: list[dict[str, Any]] = []
        if inst_dir and (Path(str(inst_dir)) / "institution.json").is_file():
            receipt = json.loads(
                (Path(str(inst_dir)) / "institution.json").read_text(encoding="utf-8")
            )
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ps in list(receipt.get("program_states") or []):
                if isinstance(ps, Mapping):
                    nested_program_states.append(dict(ps))
        if after_portfolio is None and isinstance(
            inst_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(inst_result["federated_portfolio"])  # type: ignore[index]
        if not nested_program_states:
            for ps in list(inst_result.get("program_states") or []):
                if isinstance(ps, Mapping):
                    nested_program_states.append(dict(ps))

        for i, ist in enumerate(institution_states):
            if str(ist.get("institution_id")) != institution_id:
                continue
            updated = dict(ist)
            updated["last_institution_dir"] = inst_result.get("institution_dir")
            updated["last_institution_digest"] = inst_result.get("institution_digest")
            updated["institution_met"] = bool(inst_result.get("institution_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_program_states:
                updated["program_states"] = nested_program_states
            institution_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in institution_states]
        )
        coverage_after = league_terminal_coverage(
            institution_states=institution_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_institution_roi(
            round_index=round_index,
            institution_id=institution_id,
            institution_result=inst_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(inst_result.get("institution_digest") or "")
        if idigest:
            institution_digests.append(idigest)

        rec = _institution_record(
            round_index=round_index,
            institution_id=institution_id,
            institution_result=inst_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            league_dir=league_dir,
            charter=active_charter,
            institution_states=institution_states,
            max_active_institutions=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = league_terminal_coverage(
                institution_states=institution_states,
                federated_portfolio=federated_portfolio,
            )

        write_league_state(
            league_dir,
            _state_payload(
                league_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                institution_states=institution_states,
                institution_digests=institution_digests,
                charter=active_charter,
                stop_reason=None,
                league_goal=league_goal,
                max_active_institutions=active_max,
                admissions=admissions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not inst_result.get("institution_met")
        ):
            idle_streak += 1
        else:
            idle_streak = 0

        if stop_when is not None:
            reason = stop_when(
                {
                    "round_index": round_index,
                    "round_count": len(institutions),
                    "total_dispatched": total_dispatched,
                    "total_dispatched_ok": total_dispatched_ok,
                    "coverage": coverage_after,
                    "roi_history": roi_history,
                    "institution_states": institution_states,
                    "last_institution_id": institution_id,
                    "federated_portfolio": federated_portfolio,
                    "league_dir": str(league_dir),
                    "pending_institution_ids": [
                        str(s.get("institution_id") or "")
                        for s in pending_charter_slots(
                            active_charter, institution_states
                        )
                    ],
                    "admissions": admissions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        if constitution_satisfied(
            institution_states=institution_states,
            charter=active_charter,
            league_goal=league_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "league_met"
            league_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            institution_states=institution_states,
            charter=active_charter,
            league_goal=league_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "league_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        league_dir=league_dir,
        charter=active_charter,
        institution_states=institution_states,
        max_active_institutions=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in institution_states]
    )
    coverage_end = league_terminal_coverage(
        institution_states=institution_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        institution_states=institution_states,
        charter=active_charter,
        league_goal=league_goal,
        federated_portfolio=federated_portfolio,
    ):
        league_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    institutions_met_count = sum(
        1 for ist in institution_states if ist.get("institution_met")
    )
    pending_remaining = [
        str(s.get("institution_id") or "")
        for s in pending_charter_slots(active_charter, institution_states)
    ]

    if league_met and stop_reason in {"league_met", "max_rounds"}:
        verdict = "league_met"
        ok = True
        stop_reason = "league_met"
    elif stop_reason == "rank_only":
        verdict = "league_ranked"
        ok = True
    elif stop_reason == "league_idle":
        verdict = "league_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "league_budgeted"
        ok = True
    elif stop_reason.startswith("institution_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "league_refused_mid"
        ok = False
    else:
        verdict = "league_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "league_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_institutions": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "league_goal": league_goal,
        "league_met": league_met,
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
        "round_count": len(institutions),
        "institutions": institutions,
        "institution_digests": [
            i.get("institution_digest")
            for i in institutions
            if i.get("institution_digest")
        ],
        "institution_states": institution_states,
        "institutions_admitted": len(institution_states),
        "institutions_met_count": institutions_met_count,
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
    receipt["institution_digests"] = [
        str(i.get("institution_digest") or "") for i in institutions
    ]
    receipt["league_digest"] = _sha256_json(_league_digest_payload(receipt))
    atomic_write_json(league_dir / "league.json", receipt)
    atomic_write_json(
        league_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "league_id": receipt["league_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "league_met": receipt["league_met"],
            "institutions_admitted": receipt["institutions_admitted"],
            "institutions_met_count": receipt["institutions_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "max_active_institutions": receipt["max_active_institutions"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "league_digest": receipt["league_digest"],
            "resumed": resumed,
        },
    )

    write_league_state(
        league_dir,
        _state_payload(
            league_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            institution_states=institution_states,
            institution_digests=receipt["institution_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            league_goal=league_goal,
            max_active_institutions=active_max,
            admissions=admissions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "league_dir": str(league_dir),
        "league_digest": receipt["league_digest"],
        "league_id": lid,
        "round_count": len(institutions),
        "institution_digests": list(receipt["institution_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "league_met": league_met,
        "institutions_admitted": len(institution_states),
        "institutions_met_count": institutions_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_institutions": active_max,
        "admissions": admissions,
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "institution_states": institution_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "institutions": institutions,
        "used_skill_route_discovery": receipt["used_skill_route_discovery"],
    }


# ---------------------------------------------------------------------------
# hermetic proof


def _proof_campaign_runner(scratch: Path) -> Callable[..., dict[str, Any]]:
    return up._proof_campaign_runner(scratch)


def _program_slot(
    program_id: str,
    *,
    priority: int = 0,
    initial: Sequence[tuple[str, str, str]] = (),
    deferred: Sequence[tuple[str, str, str]] = (),
    max_successions: int = 3,
    program_goal: str = "terminal_and_exhausted",
) -> dict[str, Any]:
    """Build a hermetic nested program charter slot (institution plane)."""
    return ui._slot(
        program_id,
        priority=priority,
        initial=initial,
        deferred=deferred,
        max_successions=max_successions,
        program_goal=program_goal,
    )


def _inst_slot(
    institution_id: str,
    *,
    priority: int = 0,
    programs: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    institution_goal: str = "all_programs_met",
    max_active_programs: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic league charter institution slot."""
    return {
        "institution_id": institution_id,
        "priority": priority,
        "charter": list(programs or []),
        "max_rounds": max_rounds,
        "institution_goal": institution_goal,
        "max_active_programs": max_active_programs,
    }


def builtin_upstream_league_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-institution league plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="league-proof-"))
    try:
        campaign = _proof_campaign_runner(scratch)

        # Multi-institution constitution: two institutions, multi-program nested.
        # Short ids keep Windows nested artifact paths under MAX_PATH.
        charter = [
            _inst_slot(
                "ia",
                priority=2,
                programs=[
                    _program_slot(
                        "la",
                        priority=1,
                        initial=[("alpha", "1.0.0", "alpha-dos")],
                    ),
                ],
                max_rounds=4,
            ),
            _inst_slot(
                "ib",
                priority=1,
                programs=[
                    _program_slot(
                        "lb",
                        priority=1,
                        initial=[("beta", "2.0.0", "beta-xss")],
                        deferred=[("gamma", "3.0.0", "gamma-rce")],
                    ),
                ],
                max_rounds=5,
            ),
        ]

        league = run_league(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            league_goal="all_institutions_met",
            out_root=scratch / "m",
        )
        multi_institution_ok = (
            league["ok"]
            and league["league_met"] is True
            and league["stop_reason"] == "league_met"
            and league["institutions_admitted"] == 2
            and league["institutions_met_count"] == 2
            and league["round_count"] >= 2
            and league["total_dispatched_ok"] >= 3
            and float((league.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        scheduled_ids = {
            i.get("institution_id") for i in (league.get("institutions") or [])
        }
        multi_institution_scheduled = multi_institution_ok and scheduled_ids >= {
            "ia",
            "ib",
        }

        verified = verify_league_receipt(Path(league["league_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == league[
            "round_count"
        ]

        # Tamper detection.
        league_path = Path(league["league_dir"]) / "league.json"
        receipt = json.loads(league_path.read_text(encoding="utf-8"))
        receipt["league_digest"] = "0" * 64
        league_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_league_receipt(Path(league["league_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "league_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across institutions.
        campaign2 = _proof_campaign_runner(scratch / "b")
        budgeted = run_league(
            charter=[
                _inst_slot(
                    "b1",
                    priority=1,
                    programs=[
                        _program_slot("p1", initial=[("d1", "1.0.0", "d1-1")])
                    ],
                ),
                _inst_slot(
                    "b2",
                    priority=1,
                    programs=[
                        _program_slot("p2", initial=[("d2", "1.0.0", "d2-1")])
                    ],
                ),
            ],
            max_rounds=6,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign2,
            league_goal="none",
            out_root=scratch / "bg",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit via custom institution_runner.
        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            nested_charter = ui.normalize_institution_charter(kwargs.get("charter"))
            entries: list[dict[str, Any]] = []
            for slot in nested_charter:
                for t in list(slot.get("initial_targets") or []) + list(
                    slot.get("surface_charter") or []
                ):
                    for d in list(t.get("defects") or []):
                        entries.append(
                            {
                                "name": t.get("name"),
                                "version": t.get("version"),
                                "defect_id": d.get("id"),
                                "outcome": "impact_merged",
                                "impact_digest": "c" * 64,
                                "ok": True,
                            }
                        )
            portfolio = uf._proof_portfolio(entries)
            digest = _sha256_json({"premet": True, "entries": len(entries)})
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "institution_met",
                "stop_reason": "institution_met",
                "institution_id": kwargs.get("institution_id"),
                "institution_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "programs_admitted": len(nested_charter),
                "programs_met_count": len(nested_charter),
                "institution_digest": digest,
                "federated_portfolio": portfolio,
                "program_states": [],
                "coverage_end": {
                    "required": len(entries),
                    "covered": len(entries),
                    "met": True,
                    "coverage_ratio": 1.0,
                },
            }
            atomic_write_json(out / "institution.json", receipt)
            atomic_write_json(
                out / "institution_state.json",
                {
                    "institution_id": kwargs.get("institution_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "program_states": [],
                    "stop_reason": "institution_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "institution_met",
                "stop_reason": "institution_met",
                "institution_dir": str(out),
                "institution_digest": digest,
                "institution_id": kwargs.get("institution_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "institution_met": True,
                "programs_admitted": len(nested_charter),
                "programs_met_count": len(nested_charter),
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "program_states": [],
                "used_skill_route_discovery": False,
            }

        pre_met = run_league(
            charter=[
                _inst_slot(
                    "omega",
                    programs=[
                        _program_slot(
                            "omega-lane",
                            initial=[("omega", "9.0.0", "omega-merged")],
                        )
                    ],
                )
            ],
            max_rounds=3,
            dispatch=True,
            institution_runner=_premet_runner,
            league_goal="all_institutions_met",
            out_root=scratch / "pm",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["league_met"] is True
            and pre_met["stop_reason"] == "league_met"
            and pre_met["institutions_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only league.
        ranked = run_league(
            charter=[
                _inst_slot(
                    "rank-a",
                    programs=[
                        _program_slot("ra", initial=[("r1", "1.0.0", "r1-1")])
                    ],
                ),
                _inst_slot(
                    "rank-b",
                    programs=[
                        _program_slot("rb", initial=[("r2", "1.0.0", "r2-1")])
                    ],
                ),
            ],
            max_rounds=3,
            dispatch=False,
            league_goal="none",
            out_root=scratch / "rk",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "league_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_league(
                charter=[],
                dispatch=False,
                league_goal="none",
                out_root=scratch / "e",
            )
        except LeagueRefused as exc:
            empty_refused = exc.verdict in {"league_empty", "league_invalid"}

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_league(
            charter=[
                _inst_slot(
                    "c1",
                    programs=[
                        _program_slot("c1p", initial=[("c1", "1.0.0", "c1-1")])
                    ],
                ),
                _inst_slot(
                    "c2",
                    programs=[
                        _program_slot("c2p", initial=[("c2", "1.0.0", "c2-1")])
                    ],
                ),
            ],
            max_rounds=6,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=8,
            dispatch=True,
            campaign_runner=campaign3,
            league_goal="none",
            stop_when=lambda ctx: (
                "custom_halt" if ctx["total_dispatched_ok"] >= 1 else None
            ),
            out_root=scratch / "cs",
        )
        custom_ok = (
            custom["ok"]
            and custom["stop_reason"] == "custom_halt"
            and custom["total_dispatched_ok"] >= 1
        )

        # Durable resume: partial (budget=1), resume with more budget.
        campaign4 = _proof_campaign_runner(scratch / "ra")
        partial = run_league(
            charter=[
                _inst_slot(
                    "z1",
                    priority=2,
                    programs=[
                        _program_slot("z1p", initial=[("zeta", "1.0.0", "zeta-1")])
                    ],
                ),
                _inst_slot(
                    "z2",
                    priority=1,
                    programs=[
                        _program_slot("z2p", initial=[("eta", "1.0.0", "eta-1")])
                    ],
                ),
            ],
            max_rounds=1,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=1,
            dispatch=True,
            campaign_runner=campaign4,
            league_goal="none",
            league_id="resume-league-proof",
            out_root=scratch / "pa",
        )
        state_path = Path(partial["league_dir"]) / "league_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "rb")
        resumed = run_league(
            resume_dir=Path(partial["league_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            league_goal="none",
            out_root=scratch / "rs",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["league_id"] == "resume-league-proof"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-institution budget allocation evidence.
        roi_ok = (
            isinstance(league.get("roi_summary"), Mapping)
            and int((league["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((league["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance(
                (league["roi_summary"] or {}).get("by_institution"), Mapping
            )
            and len((league["roi_summary"] or {}).get("by_institution") or {}) >= 2
        )

        first_institution = (league.get("institutions") or [{}])[0].get(
            "institution_id"
        )
        priority_ok = first_institution == "ia"

        # Federation: inventories across both institutions form a joint surface.
        fed_keys: set[tuple[str, str, str]] = set()
        for ist in league.get("institution_states") or []:
            for ps in ist.get("program_states") or []:
                stew = ps.get("stewardship_root") if isinstance(ps, Mapping) else None
                if stew:
                    for n, v, d in up.inventory_defect_keys(Path(str(stew))):
                        fed_keys.add((n, v, d))
        federation_ok = multi_institution_ok and len(fed_keys) >= 3

        # Deferred admission: max_active=1 grows league charter over time.
        campaign6 = _proof_campaign_runner(scratch / "dc")
        deferred = run_league(
            charter=[
                _inst_slot(
                    "da",
                    priority=3,
                    programs=[
                        _program_slot("dap", initial=[("da", "1.0.0", "da-1")])
                    ],
                    max_rounds=3,
                ),
                _inst_slot(
                    "db",
                    priority=2,
                    programs=[
                        _program_slot("dbp", initial=[("db", "1.0.0", "db-1")])
                    ],
                    max_rounds=3,
                ),
                _inst_slot(
                    "dc",
                    priority=1,
                    programs=[
                        _program_slot("dcp", initial=[("dc", "1.0.0", "dc-1")])
                    ],
                    max_rounds=3,
                ),
            ],
            max_rounds=8,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=6,
            max_active_institutions=1,
            dispatch=True,
            campaign_runner=campaign6,
            league_goal="all_institutions_met",
            out_root=scratch / "dl",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("institution_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["league_met"] is True
            and deferred["institutions_admitted"] == 3
            and deferred["institutions_met_count"] == 3
            and deferred.get("max_active_institutions") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        ok = all(
            [
                multi_institution_ok,
                multi_institution_scheduled,
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
            "league_met": multi_institution_ok,
            "multi_institution_progressed": multi_institution_scheduled,
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
            "league_digest": league.get("league_digest"),
            "round_count": league.get("round_count"),
            "total_dispatched_ok": league.get("total_dispatched_ok"),
            "institutions_admitted": league.get("institutions_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_institution_ok": multi_institution_ok,
                "multi_institution_scheduled": multi_institution_scheduled,
                "seal_ok": seal_ok,
                "tamper_detected": tamper_detected,
                "budget_ok": budget_ok,
                "premet_ok": premet_ok,
                "rank_only_ok": rank_only_ok,
                "empty_refused": empty_refused,
                "custom_ok": custom_ok,
                "resume_ok": resume_ok,
                "roi_ok": roi_ok,
                "priority_ok": priority_ok,
                "federation_ok": federation_ok,
                "deferred_ok": deferred_ok,
            },
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
        help="verify a sealed league directory",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.verify:
        result = verify_league_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_league_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
