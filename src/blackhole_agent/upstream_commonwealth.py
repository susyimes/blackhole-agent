"""Upstream commonwealth plane: multi-confederation durable stewardship commonwealth.

The confederation plane (``upstream_confederation``) closes multi-league unions
*within one confederation*. It does not:

1. chain multiple independent confederations under a durable commonwealth constitution;
2. allocate a shared global dispatch budget across confederations by ROI;
3. admit/retire confederation slots from a commonwealth charter over time
   (deferred admission under a concurrent-active cap);
4. federate multi-confederation portfolio coverage into one commonwealth world-model;
5. persist commonwealth state so a later process can resume the union;
6. seal a multi-confederation commonwealth chronicle linking confederation digests.

The commonwealth plane closes that outer multi-confederation loop:

1. **admit** — materialize confederation slots from a durable commonwealth charter
   (each slot owns a nested league charter). When ``max_active_confederations``
   is set, only that many *unmet* confederations are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (commonwealth constitution growth over time);
2. **schedule** — pick the next open confederation by priority and historical ROI;
3. **confederation** — call the confederation plane (injected ``confederation_runner``;
   default ``run_confederation``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-confederation portfolios into one commonwealth world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark confederations met when their confederation_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **persist** — write ``commonwealth_state.json`` after every confederation round so a
   later ``run_commonwealth(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
7. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across confederations
   - commonwealth goal met (``all_confederations_met``: every *admitted*
     confederation is met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

8. **seal** — write a commonwealth receipt under
   ``artifacts/upstream-commonwealth/`` with sha256 digests of every
   confederation, portfolio federation, admission history, ROI history, stop
   reason, and a commonwealth chain digest; ``verify_commonwealth_receipt``
   re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is commonwealth-level direction
over the confederation plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_confederation as ucf
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-commonwealth"

TERMINAL_SUCCESS_OUTCOMES = ucf.TERMINAL_SUCCESS_OUTCOMES


class CommonwealthRefused(Exception):
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


def normalize_commonwealth_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a commonwealth charter into deterministic confederation slots.

    Each slot is::

        {
          "confederation_id": str,
          "priority": int,
          "charter": [...league slots...],  # nested confederation charter
          "max_active_leagues": int | None,
          "max_rounds": int,
          "confederation_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        confederation_id = str(
            raw.get("confederation_id") or raw.get("id") or ""
        ).strip()
        if not confederation_id or confederation_id in seen:
            continue
        seen.add(confederation_id)

        nested = ucf.normalize_confederation_charter(
            raw.get("charter") or raw.get("leagues") or raw.get("institutions") or raw.get("programs")
        )
        if not nested:
            continue

        max_active_leagues = raw.get("max_active_leagues")
        if max_active_leagues is not None:
            max_active_leagues = max(1, int(max_active_leagues))

        out.append(
            {
                "confederation_id": confederation_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_leagues": max_active_leagues,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "confederation_goal": str(
                    raw.get("confederation_goal") or "all_leagues_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_confederation"),
            }
        )
    return out


def admit_confederation_slot(
    *,
    commonwealth_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with confederation_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    confederation_id = str(slot.get("confederation_id") or "")
    if not confederation_id:
        raise CommonwealthRefused("commonwealth_invalid", "slot missing confederation_id")

    confederation_root = Path(commonwealth_dir) / "confederations" / confederation_id
    confederation_root.mkdir(parents=True, exist_ok=True)

    nested_charter = ucf.normalize_confederation_charter(slot.get("charter"))
    if not nested_charter:
        raise CommonwealthRefused(
            "commonwealth_invalid",
            f"institution slot {confederation_id!r} has empty nested charter",
        )

    return {
        "confederation_id": confederation_id,
        "confederation_root": str(confederation_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_leagues": slot.get("max_active_leagues"),
        "max_rounds": int(slot.get("max_rounds") or 6),
        "confederation_goal": str(slot.get("confederation_goal") or "all_leagues_met"),
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
        "source": "commonwealth_federation",
    }
    portfolio["portfolio_digest"] = _recompute_portfolio_digest(portfolio)
    return portfolio


def commonwealth_terminal_coverage(
    *,
    confederation_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """League coverage: every admitted institution's inventory is terminal-success."""
    required_keys: list[tuple[str, str, str]] = []
    for ist in confederation_states:
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
        # Nested league_states from a completed confederation round.
        for lg in list(ist.get("league_states") or []):
            if not isinstance(lg, Mapping):
                continue
            for inst in list(lg.get("institution_states") or []):
                if not isinstance(inst, Mapping):
                    continue
                for ps in list(inst.get("program_states") or []):
                    if not isinstance(ps, Mapping):
                        continue
                    stew = ps.get("stewardship_root")
                    if not stew:
                        continue
                    root = Path(str(stew))
                    if root.is_dir():
                        required_keys.extend(up.inventory_defect_keys(root))
                for slot in list(inst.get("charter") or []):
                    if not isinstance(slot, Mapping):
                        continue
                    for tgt in list(slot.get("initial_targets") or []) + list(
                        slot.get("surface_charter") or []
                    ):
                        if not isinstance(tgt, Mapping):
                            continue
                        name = str(tgt.get("name") or "")
                        version = str(tgt.get("version") or "")
                        for d in list(tgt.get("defects") or []):
                            if not isinstance(d, Mapping):
                                continue
                            did = str(d.get("id") or "")
                            if name and did:
                                required_keys.append((name, version, did))
            for islot in list(lg.get("charter") or []):
                if not isinstance(islot, Mapping):
                    continue
                for pslot in list(islot.get("charter") or []) + list(
                    islot.get("programs") or []
                ):
                    if not isinstance(pslot, Mapping):
                        continue
                    for tgt in list(pslot.get("initial_targets") or []) + list(
                        pslot.get("surface_charter") or []
                    ):
                        if not isinstance(tgt, Mapping):
                            continue
                        name = str(tgt.get("name") or "")
                        version = str(tgt.get("version") or "")
                        for d in list(tgt.get("defects") or []):
                            if not isinstance(d, Mapping):
                                continue
                            did = str(d.get("id") or "")
                            if name and did:
                                required_keys.append((name, version, did))
        # Nested confederation charter (league -> institution -> program) when not yet run.
        for lslot in list(ist.get("charter") or []):
            if not isinstance(lslot, Mapping):
                continue
            for islot in list(lslot.get("charter") or []) + list(
                lslot.get("institutions") or []
            ):
                if not isinstance(islot, Mapping):
                    continue
                for pslot in list(islot.get("charter") or []) + list(
                    islot.get("programs") or []
                ):
                    if not isinstance(pslot, Mapping):
                        continue
                    for tgt in list(pslot.get("initial_targets") or []) + list(
                        pslot.get("surface_charter") or []
                    ):
                        if not isinstance(tgt, Mapping):
                            continue
                        name = str(tgt.get("name") or "")
                        version = str(tgt.get("version") or "")
                        for d in list(tgt.get("defects") or []):
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


def confederations_all_met(confederation_states: Sequence[Mapping[str, Any]]) -> bool:
    if not confederation_states:
        return False
    return all(bool(ist.get("confederation_met")) for ist in confederation_states)


def open_unmet_count(confederation_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet confederation_met."""
    return sum(1 for ist in confederation_states if not ist.get("confederation_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    confederation_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then confederation_id-asc."""
    known = {str(ist.get("confederation_id") or "") for ist in confederation_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("confederation_id") or "")
        and str(slot.get("confederation_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("confederation_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    confederation_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    commonwealth_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if commonwealth_goal == "none":
        return False
    if commonwealth_goal == "terminal_coverage":
        cov = commonwealth_terminal_coverage(
            confederation_states=confederation_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, confederation_states
        )
    if commonwealth_goal == "all_confederations_met":
        if not confederation_states:
            return False
        if pending_charter_slots(charter, confederation_states):
            return False
        return confederations_all_met(confederation_states)
    return False


def admit_pending_slots(
    *,
    commonwealth_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    confederation_states: list[dict[str, Any]],
    max_active_confederations: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_confederations`` caps *unmet* concurrent institutions. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``confederation_states``).
    """
    pending = pending_charter_slots(charter, confederation_states)
    if not pending:
        return []

    open_n = open_unmet_count(confederation_states)
    if max_active_confederations is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_confederations) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_confederation_slot(commonwealth_dir=commonwealth_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        confederation_states.append(
            {
                "confederation_id": admission["confederation_id"],
                "confederation_root": admission["confederation_root"],
                "charter": admission["charter"],
                "max_active_leagues": admission.get("max_active_leagues"),
                "max_rounds": admission["max_rounds"],
                "confederation_goal": admission["confederation_goal"],
                "priority": admission["priority"],
                "confederation_met": False,
                "last_confederation_dir": None,
                "last_confederation_digest": None,
                "portfolio": None,
                "league_states": [],
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


# ---------------------------------------------------------------------------
# ROI + scheduling


def score_confederation_roi(
    *,
    round_index: int,
    confederation_id: str,
    confederation_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one institution round for league learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(confederation_result.get("total_dispatched_ok") or 0)
    dispatched = int(confederation_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "confederation_id": confederation_id,
        "stop_reason": confederation_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "confederation_met": bool(confederation_result.get("confederation_met")),
        "confederation_digest": confederation_result.get("confederation_digest"),
        "leagues_admitted": int(confederation_result.get("leagues_admitted") or 0),
        "leagues_met_count": int(confederation_result.get("leagues_met_count") or 0),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_confederation": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_confederation: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get("confederation_id") or "")
        bucket = by_confederation.setdefault(
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
    for iid, bucket in by_confederation.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_confederation": by_confederation,
    }


def select_next_confederation(
    confederation_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable confederation_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in confederation_states if not ist.get("confederation_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_confederation = summary.get("by_confederation") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("confederation_id") or "")
        hist = by_confederation.get(iid) or {}
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


def allocate_confederation_budget(
    *,
    remaining_budget: int | None,
    open_confederation_count: int,
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
    open_n = max(1, int(open_confederation_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_confederation") or {}).get(
        str(selected.get("confederation_id") or "")
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
    commonwealth_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    confederation_states: Sequence[Mapping[str, Any]],
    confederation_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    commonwealth_goal: str,
    max_active_confederations: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "commonwealth_id": commonwealth_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "confederation_states": [dict(ist) for ist in confederation_states],
        "confederation_digests": list(confederation_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "commonwealth_goal": commonwealth_goal,
        "max_active_confederations": max_active_confederations,
        "admissions": [dict(a) for a in (admissions or [])],
        "pending_commonwealth_ids": [
            str(s.get("confederation_id") or "")
            for s in pending_charter_slots(charter, confederation_states)
        ],
    }


def write_commonwealth_state(commonwealth_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(commonwealth_dir) / "commonwealth_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_commonwealth_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "commonwealth_state.json")
    if not path.is_file():
        raise CommonwealthRefused(
            "commonwealth_state_missing",
            f"no commonwealth_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommonwealthRefused("commonwealth_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise CommonwealthRefused("commonwealth_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _confederation_round_record(
    *,
    round_index: int,
    confederation_id: str,
    confederation_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "confederation_id": confederation_id,
        "ok": bool(confederation_result.get("ok")),
        "verdict": confederation_result.get("verdict"),
        "stop_reason": confederation_result.get("stop_reason"),
        "confederation_dir": confederation_result.get("confederation_dir"),
        "confederation_digest": confederation_result.get("confederation_digest"),
        "leagues_admitted": int(confederation_result.get("leagues_admitted") or 0),
        "leagues_met_count": int(confederation_result.get("leagues_met_count") or 0),
        "total_dispatched": int(confederation_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(confederation_result.get("total_dispatched_ok") or 0),
        "confederation_met": bool(confederation_result.get("confederation_met")),
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


def _commonwealth_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "commonwealth_id": receipt.get("commonwealth_id"),
        "commonwealth_goal": receipt.get("commonwealth_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_confederations": receipt.get("max_active_confederations"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "confederation_digests": list(receipt.get("confederation_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "commonwealth_met": receipt.get("commonwealth_met"),
        "coverage_end": receipt.get("coverage_end"),
        "confederations_met_count": receipt.get("confederations_met_count"),
        "confederations_admitted": receipt.get("confederations_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_commonwealth_receipt(commonwealth_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(commonwealth_dir) / "commonwealth.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_commonwealth_digest_payload(receipt))
    recorded = str(receipt.get("commonwealth_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("commonwealth_digest")

    institutions = list(receipt.get("confederations") or receipt.get("leagues") or [])
    listed = list(receipt.get("confederation_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("confederation_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("confederation_digest"):
                mismatched.append(f"confederation_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("confederation_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "confederation.json").is_file():
            nested = ucf.verify_confederation_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "commonwealth_sealed" if ok else "commonwealth_tampered",
        "commonwealth_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run commonwealth


def run_commonwealth(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_confederations: int | None = None,
    dispatch: bool = True,
    confederation_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    commonwealth_goal: str = "all_confederations_met",
    refresh_promotions: Mapping[str, str] | None = None,
    commonwealth_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_commonwealth_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_confederations:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    commonwealth_goal:
        ``all_confederations_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``commonwealth_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise CommonwealthRefused("commonwealth_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise CommonwealthRefused(
            "commonwealth_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_confederations is not None and int(max_active_confederations) < 1:
        raise CommonwealthRefused(
            "commonwealth_invalid", "max_active_confederations must be >= 1 when set"
        )
    if commonwealth_goal not in {"all_confederations_met", "terminal_coverage", "none"}:
        raise CommonwealthRefused(
            "commonwealth_invalid",
            f"unknown commonwealth_goal: {commonwealth_goal}",
        )

    runner = confederation_runner or ucf.run_confederation

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    confederation_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_commonwealth_id: str | None = None
    confederation_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_commonwealth_state(resume_dir)
        resumed = True
        resume_commonwealth_id = str(state.get("commonwealth_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        confederation_digests = [str(d) for d in (state.get("confederation_digests") or [])]
        confederation_states = [
            dict(ist)
            for ist in (state.get("confederation_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_commonwealth_charter(
                [e for e in state["charter"] if isinstance(e, Mapping)]
            )
        if isinstance(state.get("admissions"), list):
            admissions = [
                dict(a) for a in state["admissions"] if isinstance(a, Mapping)
            ]
        if (
            state.get("max_active_confederations") is not None
            and max_active_confederations is None
        ):
            resumed_max_active = int(state["max_active_confederations"])
    else:
        active_charter = normalize_commonwealth_charter(charter)

    active_max = (
        max_active_confederations
        if max_active_confederations is not None
        else resumed_max_active
    )

    if not active_charter and not confederation_states:
        raise CommonwealthRefused(
            "commonwealth_empty",
            "commonwealth charter has no admitable confederation slots",
        )

    lid = (
        commonwealth_id
        or resume_commonwealth_id
        or f"commonwealth-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        commonwealth_dir = Path(out_root)
        if (commonwealth_dir / "commonwealth.json").is_file():
            commonwealth_dir = commonwealth_dir / stamp
    else:
        commonwealth_dir = ARTIFACTS_ROOT / stamp
    commonwealth_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    lg_root = (
        Path(league_out_root) if league_out_root else (commonwealth_dir / "ir")
    )
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root = commonwealth_dir / "pr"
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        commonwealth_dir=commonwealth_dir,
        charter=active_charter,
        confederation_states=confederation_states,
        max_active_confederations=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not confederation_states and not pending_charter_slots(
        active_charter, confederation_states
    ):
        raise CommonwealthRefused("commonwealth_empty", "no confederation slots admitted")
    if not confederation_states and pending_charter_slots(
        active_charter, confederation_states
    ):
        raise CommonwealthRefused(
            "commonwealth_empty",
            "no confederation slots admitted under max_active_confederations policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in confederation_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    commonwealth_met = False
    coverage_end: dict[str, Any] = commonwealth_terminal_coverage(
        confederation_states=confederation_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            commonwealth_dir=commonwealth_dir,
            charter=active_charter,
            confederation_states=confederation_states,
            max_active_confederations=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = commonwealth_terminal_coverage(
            confederation_states=confederation_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            confederation_states=confederation_states,
            charter=active_charter,
            commonwealth_goal=commonwealth_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "commonwealth_met"
            commonwealth_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_confederation(
            confederation_states, roi_history, round_index=round_index
        )
        if selected is None:
            if not pending_charter_slots(active_charter, confederation_states):
                stop_reason = "commonwealth_met"
                commonwealth_met = True
            else:
                stop_reason = "commonwealth_idle"
            coverage_end = coverage_before
            break

        open_count = sum(
            1 for ist in confederation_states if not ist.get("confederation_met")
        )
        allocated = allocate_confederation_budget(
            remaining_budget=remaining_budget,
            open_confederation_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        confederation_id = str(selected["confederation_id"])
        resume_confederation_dir = selected.get("last_confederation_dir")
        confederation_resume: Path | None = None
        if (
            resume_confederation_dir
            and (Path(str(resume_confederation_dir)) / "commonwealth_state.json").is_file()
            and not selected.get("confederation_met")
        ):
            confederation_resume = Path(str(resume_confederation_dir))

        # Short stamp: r00-ia (avoid deep Windows paths under succession/epoch/wave).
        safe_id = "".join(c if c.isalnum() else "" for c in confederation_id)[:12] or "i"
        out_dir = lg_root / f"r{round_index:02d}-{safe_id}"
        inst_out = inst_flat_root / f"r{round_index:02d}-{safe_id}"
        confederation_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "confederation_goal": str(
                selected.get("confederation_goal") or "all_leagues_met"
            ),
            "confederation_id": confederation_id,
            "out_root": out_dir,
            "league_out_root": inst_out,
        }
        if selected.get("max_active_leagues") is not None:
            confederation_kwargs["max_active_leagues"] = int(
                selected["max_active_leagues"]
            )
        if confederation_resume is not None:
            confederation_kwargs["resume_dir"] = confederation_resume
            # charter already on resume state
            confederation_kwargs.pop("charter", None)
        if program_runner is not None:
            confederation_kwargs["program_runner"] = program_runner
        if campaign_runner is not None:
            confederation_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            confederation_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            confederation_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            confederation_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            confederation_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            confederation_kwargs["refresh_promotions"] = refresh_promotions

        try:
            confederation_result = runner(**confederation_kwargs)
        except ucf.ConfederationRefused as exc:
            if local_index == 0 and not resumed:
                raise CommonwealthRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"confederation_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise CommonwealthRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise CommonwealthRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(confederation_result.get("total_dispatched") or 0)
        dispatched_ok = int(confederation_result.get("total_dispatched_ok") or 0)
        prior_inst_dispatched = int(selected.get("total_dispatched") or 0)
        prior_inst_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_inst_dispatched)
        delta_ok = max(0, dispatched_ok - prior_inst_ok)
        if confederation_resume is None and prior_inst_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        nested_confederation_dir = confederation_result.get("confederation_dir")
        nested_league_states: list[dict[str, Any]] = []
        nested_receipt_path = (
            Path(str(nested_confederation_dir)) / "confederation.json"
            if nested_confederation_dir
            else None
        )
        if nested_receipt_path is not None and nested_receipt_path.is_file():
            receipt = json.loads(nested_receipt_path.read_text(encoding="utf-8"))
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(receipt.get("league_states") or []):
                if isinstance(ist, Mapping):
                    nested_league_states.append(dict(ist))
        if after_portfolio is None and isinstance(
            confederation_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(confederation_result["federated_portfolio"])  # type: ignore[index]
        if not nested_league_states:
            for ist in list(confederation_result.get("league_states") or []):
                if isinstance(ist, Mapping):
                    nested_league_states.append(dict(ist))

        for i, lst in enumerate(confederation_states):
            if str(lst.get("confederation_id")) != confederation_id:
                continue
            updated = dict(lst)
            updated["last_confederation_dir"] = confederation_result.get("confederation_dir")
            updated["last_confederation_digest"] = confederation_result.get("confederation_digest")
            updated["confederation_met"] = bool(confederation_result.get("confederation_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_league_states:
                updated["league_states"] = nested_league_states
            confederation_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in confederation_states]
        )
        coverage_after = commonwealth_terminal_coverage(
            confederation_states=confederation_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_confederation_roi(
            round_index=round_index,
            confederation_id=confederation_id,
            confederation_result=confederation_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(confederation_result.get("confederation_digest") or "")
        if idigest:
            confederation_digests.append(idigest)

        rec = _confederation_round_record(
            round_index=round_index,
            confederation_id=confederation_id,
            confederation_result=confederation_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            commonwealth_dir=commonwealth_dir,
            charter=active_charter,
            confederation_states=confederation_states,
            max_active_confederations=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = commonwealth_terminal_coverage(
                confederation_states=confederation_states,
                federated_portfolio=federated_portfolio,
            )

        write_commonwealth_state(
            commonwealth_dir,
            _state_payload(
                commonwealth_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                confederation_states=confederation_states,
                confederation_digests=confederation_digests,
                charter=active_charter,
                stop_reason=None,
                commonwealth_goal=commonwealth_goal,
                max_active_confederations=active_max,
                admissions=admissions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not confederation_result.get("confederation_met")
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
                    "confederation_states": confederation_states,
                    "last_confederation_id": confederation_id,
                    "federated_portfolio": federated_portfolio,
                    "commonwealth_dir": str(commonwealth_dir),
                    "pending_confederation_ids": [
                        str(s.get("confederation_id") or "")
                        for s in pending_charter_slots(
                            active_charter, confederation_states
                        )
                    ],
                    "admissions": admissions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        if constitution_satisfied(
            confederation_states=confederation_states,
            charter=active_charter,
            commonwealth_goal=commonwealth_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "commonwealth_met"
            commonwealth_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            confederation_states=confederation_states,
            charter=active_charter,
            commonwealth_goal=commonwealth_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "commonwealth_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        commonwealth_dir=commonwealth_dir,
        charter=active_charter,
        confederation_states=confederation_states,
        max_active_confederations=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in confederation_states]
    )
    coverage_end = commonwealth_terminal_coverage(
        confederation_states=confederation_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        confederation_states=confederation_states,
        charter=active_charter,
        commonwealth_goal=commonwealth_goal,
        federated_portfolio=federated_portfolio,
    ):
        commonwealth_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    confederations_met_count = sum(
        1 for ist in confederation_states if ist.get("confederation_met")
    )
    pending_remaining = [
        str(s.get("confederation_id") or "")
        for s in pending_charter_slots(active_charter, confederation_states)
    ]

    if commonwealth_met and stop_reason in {"commonwealth_met", "max_rounds"}:
        verdict = "commonwealth_met"
        ok = True
        stop_reason = "commonwealth_met"
    elif stop_reason == "rank_only":
        verdict = "commonwealth_ranked"
        ok = True
    elif stop_reason == "commonwealth_idle":
        verdict = "commonwealth_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "commonwealth_budgeted"
        ok = True
    elif stop_reason.startswith("confederation_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "commonwealth_refused_mid"
        ok = False
    else:
        verdict = "commonwealth_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "commonwealth_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_confederations": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "commonwealth_goal": commonwealth_goal,
        "commonwealth_met": commonwealth_met,
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
        "confederations": institutions,
        "confederation_digests": [
            i.get("confederation_digest")
            for i in institutions
            if i.get("confederation_digest")
        ],
        "confederation_states": confederation_states,
        "confederations_admitted": len(confederation_states),
        "confederations_met_count": confederations_met_count,
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
    receipt["confederation_digests"] = [
        str(i.get("confederation_digest") or "") for i in institutions
    ]
    receipt["commonwealth_digest"] = _sha256_json(_commonwealth_digest_payload(receipt))
    atomic_write_json(commonwealth_dir / "commonwealth.json", receipt)
    atomic_write_json(
        commonwealth_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "commonwealth_id": receipt["commonwealth_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "commonwealth_met": receipt["commonwealth_met"],
            "confederations_admitted": receipt["confederations_admitted"],
            "confederations_met_count": receipt["confederations_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "max_active_confederations": receipt["max_active_confederations"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "commonwealth_digest": receipt["commonwealth_digest"],
            "resumed": resumed,
        },
    )

    write_commonwealth_state(
        commonwealth_dir,
        _state_payload(
            commonwealth_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            confederation_states=confederation_states,
            confederation_digests=receipt["confederation_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            commonwealth_goal=commonwealth_goal,
            max_active_confederations=active_max,
            admissions=admissions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "commonwealth_dir": str(commonwealth_dir),
        "commonwealth_digest": receipt["commonwealth_digest"],
        "commonwealth_id": lid,
        "round_count": len(institutions),
        "confederation_digests": list(receipt["confederation_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "commonwealth_met": commonwealth_met,
        "confederations_admitted": len(confederation_states),
        "confederations_met_count": confederations_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_confederations": active_max,
        "admissions": admissions,
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "confederation_states": confederation_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "confederations": institutions,
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
    """Build a hermetic nested program charter slot."""
    return ucf._program_slot(
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
    """Build a hermetic nested institution slot for a league charter."""
    return ucf._inst_slot(
        institution_id,
        priority=priority,
        programs=programs,
        max_rounds=max_rounds,
        institution_goal=institution_goal,
        max_active_programs=max_active_programs,
    )



def _league_slot(
    league_id: str,
    *,
    priority: int = 0,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    league_goal: str = "all_institutions_met",
    max_active_institutions: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic nested league slot for a confederation charter."""
    return {
        "league_id": league_id,
        "priority": priority,
        "charter": list(institutions or []),
        "max_rounds": max_rounds,
        "league_goal": league_goal,
        "max_active_institutions": max_active_institutions,
    }


def _confederation_slot(
    confederation_id: str,
    *,
    priority: int = 0,
    leagues: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    confederation_goal: str = "all_leagues_met",
    max_active_leagues: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic commonwealth charter confederation slot.

    Prefer ``leagues=`` (nested league slots). ``institutions=`` is a
    convenience that wraps a single auto league when only institution work
    is supplied.
    """
    nested: list[dict[str, Any]]
    if leagues is not None:
        nested = list(leagues)
    elif institutions:
        nested = [
            _league_slot(
                f"{confederation_id}-lg",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "confederation_id": confederation_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "confederation_goal": confederation_goal,
        "max_active_leagues": max_active_leagues,
    }


def builtin_upstream_commonwealth_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-confederation commonwealth plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="cwealth-proof-"))
    try:
        campaign = _proof_campaign_runner(scratch)

        # Two leagues, each with nested institution/program work.
        # Short ids keep Windows nested artifact paths under MAX_PATH.
        charter = [
            _confederation_slot(
                "la",
                priority=2,
                institutions=[
                    _inst_slot(
                        "ia",
                        priority=1,
                        programs=[
                            _program_slot(
                                "pa",
                                priority=1,
                                initial=[("alpha", "1.0.0", "alpha-dos")],
                            ),
                        ],
                        max_rounds=4,
                    ),
                ],
                max_rounds=4,
            ),
            _confederation_slot(
                "lb",
                priority=1,
                institutions=[
                    _inst_slot(
                        "ib",
                        priority=1,
                        programs=[
                            _program_slot(
                                "pb",
                                priority=1,
                                initial=[("beta", "2.0.0", "beta-xss")],
                                deferred=[("gamma", "3.0.0", "gamma-rce")],
                            ),
                        ],
                        max_rounds=5,
                    ),
                ],
                max_rounds=5,
            ),
        ]

        confed = run_commonwealth(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            commonwealth_goal="all_confederations_met",
            out_root=scratch / "m",
        )
        multi_confederation_ok = (
            confed["ok"]
            and confed["commonwealth_met"] is True
            and confed["stop_reason"] == "commonwealth_met"
            and confed["confederations_admitted"] == 2
            and confed["confederations_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        scheduled_ids = {
            i.get("confederation_id") for i in (confed.get("confederations") or [])
        }
        multi_confederation_scheduled = multi_confederation_ok and scheduled_ids >= {"la", "lb"}

        verified = verify_commonwealth_receipt(Path(confed["commonwealth_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed[
            "round_count"
        ]

        # Tamper detection.
        confed_path = Path(confed["commonwealth_dir"]) / "commonwealth.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["commonwealth_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_commonwealth_receipt(Path(confed["commonwealth_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "commonwealth_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across leagues.
        campaign2 = _proof_campaign_runner(scratch / "b")
        budgeted = run_commonwealth(
            charter=[
                _confederation_slot(
                    "b1",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "bi1",
                            programs=[
                                _program_slot("p1", initial=[("d1", "1.0.0", "d1-1")])
                            ],
                        )
                    ],
                ),
                _confederation_slot(
                    "b2",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "bi2",
                            programs=[
                                _program_slot("p2", initial=[("d2", "1.0.0", "d2-1")])
                            ],
                        )
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
            commonwealth_goal="none",
            out_root=scratch / "bg",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit via custom confederation_runner.
        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            nested_charter = ucf.normalize_confederation_charter(kwargs.get("charter"))
            entries: list[dict[str, Any]] = []
            league_states: list[dict[str, Any]] = []
            for lslot in nested_charter:
                league_entries: list[dict[str, Any]] = []
                institution_states: list[dict[str, Any]] = []
                for islot in list(lslot.get("charter") or []):
                    inst_entries: list[dict[str, Any]] = []
                    for pslot in list(islot.get("charter") or []) + list(
                        islot.get("programs") or []
                    ):
                        for t in list(pslot.get("initial_targets") or []) + list(
                            pslot.get("surface_charter") or []
                        ):
                            for d in list(t.get("defects") or []):
                                e = {
                                    "name": t.get("name"),
                                    "version": t.get("version"),
                                    "defect_id": d.get("id"),
                                    "outcome": "impact_merged",
                                    "impact_digest": "c" * 64,
                                    "ok": True,
                                }
                                entries.append(e)
                                inst_entries.append(e)
                                league_entries.append(e)
                    institution_states.append(
                        {
                            "institution_id": islot.get("institution_id"),
                            "institution_met": True,
                            "charter": list(islot.get("charter") or []),
                            "portfolio": uf._proof_portfolio(inst_entries),
                            "program_states": [],
                        }
                    )
                league_states.append(
                    {
                        "league_id": lslot.get("league_id"),
                        "league_met": True,
                        "charter": list(lslot.get("charter") or []),
                        "portfolio": uf._proof_portfolio(league_entries),
                        "institution_states": institution_states,
                    }
                )
            portfolio = uf._proof_portfolio(entries)
            digest = _sha256_json({"premet": True, "entries": len(entries)})
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "confederation_met",
                "stop_reason": "confederation_met",
                "confederation_id": kwargs.get("confederation_id"),
                "confederation_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "leagues_admitted": len(nested_charter),
                "leagues_met_count": len(nested_charter),
                "confederation_digest": digest,
                "federated_portfolio": portfolio,
                "league_states": league_states,
                "coverage_end": {
                    "required": len(entries),
                    "covered": len(entries),
                    "met": True,
                    "coverage_ratio": 1.0,
                },
            }
            atomic_write_json(out / "confederation.json", receipt)
            atomic_write_json(
                out / "confederation_state.json",
                {
                    "confederation_id": kwargs.get("confederation_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "league_states": league_states,
                    "stop_reason": "confederation_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "confederation_met",
                "stop_reason": "confederation_met",
                "confederation_dir": str(out),
                "confederation_digest": digest,
                "confederation_id": kwargs.get("confederation_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "confederation_met": True,
                "leagues_admitted": len(nested_charter),
                "leagues_met_count": len(nested_charter),
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "league_states": league_states,
                "used_skill_route_discovery": False,
            }

        pre_met = run_commonwealth(
            charter=[
                _confederation_slot(
                    "omega",
                    institutions=[
                        _inst_slot(
                            "oi",
                            programs=[
                                _program_slot(
                                    "op",
                                    initial=[("omega", "9.0.0", "omega-merged")],
                                )
                            ],
                        )
                    ],
                )
            ],
            max_rounds=3,
            dispatch=True,
            confederation_runner=_premet_runner,
            commonwealth_goal="all_confederations_met",
            out_root=scratch / "pm",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["commonwealth_met"] is True
            and pre_met["stop_reason"] == "commonwealth_met"
            and pre_met["confederations_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only confederation.
        ranked = run_commonwealth(
            charter=[
                _confederation_slot(
                    "rank-a",
                    institutions=[
                        _inst_slot(
                            "rai",
                            programs=[
                                _program_slot("ra", initial=[("r1", "1.0.0", "r1-1")])
                            ],
                        )
                    ],
                ),
                _confederation_slot(
                    "rank-b",
                    institutions=[
                        _inst_slot(
                            "rbi",
                            programs=[
                                _program_slot("rb", initial=[("r2", "1.0.0", "r2-1")])
                            ],
                        )
                    ],
                ),
            ],
            max_rounds=3,
            dispatch=False,
            commonwealth_goal="none",
            out_root=scratch / "rk",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "commonwealth_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_commonwealth(
                charter=[],
                dispatch=False,
                commonwealth_goal="none",
                out_root=scratch / "e",
            )
        except CommonwealthRefused as exc:
            empty_refused = exc.verdict in {
                "commonwealth_empty",
                "commonwealth_invalid",
            }

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_commonwealth(
            charter=[
                _confederation_slot(
                    "c1",
                    institutions=[
                        _inst_slot(
                            "ci1",
                            programs=[
                                _program_slot("c1p", initial=[("c1", "1.0.0", "c1-1")])
                            ],
                        )
                    ],
                ),
                _confederation_slot(
                    "c2",
                    institutions=[
                        _inst_slot(
                            "ci2",
                            programs=[
                                _program_slot("c2p", initial=[("c2", "1.0.0", "c2-1")])
                            ],
                        )
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
            commonwealth_goal="none",
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
        partial = run_commonwealth(
            charter=[
                _confederation_slot(
                    "z1",
                    priority=2,
                    institutions=[
                        _inst_slot(
                            "zi1",
                            programs=[
                                _program_slot(
                                    "z1p", initial=[("zeta", "1.0.0", "zeta-1")]
                                )
                            ],
                        )
                    ],
                ),
                _confederation_slot(
                    "z2",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "zi2",
                            programs=[
                                _program_slot(
                                    "z2p", initial=[("eta", "1.0.0", "eta-1")]
                                )
                            ],
                        )
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
            commonwealth_goal="none",
            commonwealth_id="resume-confed-proof",
            out_root=scratch / "pa",
        )
        state_path = Path(partial["commonwealth_dir"]) / "commonwealth_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "rb")
        resumed = run_commonwealth(
            resume_dir=Path(partial["commonwealth_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            commonwealth_goal="none",
            out_root=scratch / "rs",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["commonwealth_id"] == "resume-confed-proof"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-league budget allocation evidence.
        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_confederation"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_confederation") or {}) >= 2
        )

        first_league = (confed.get("confederations") or [{}])[0].get("confederation_id")
        priority_ok = first_league == "la"

        # Federation: inventories across both leagues form a joint surface.
        fed_keys: set[tuple[str, str, str]] = set()
        for cst in confed.get("confederation_states") or []:
            for lst in (cst.get("league_states") or []) if isinstance(cst, Mapping) else []:
                if not isinstance(lst, Mapping):
                    continue
                for ist in lst.get("institution_states") or []:
                    if not isinstance(ist, Mapping):
                        continue
                    for ps in ist.get("program_states") or []:
                        stew = (
                            ps.get("stewardship_root")
                            if isinstance(ps, Mapping)
                            else None
                        )
                        if stew:
                            for n, v, d in up.inventory_defect_keys(Path(str(stew))):
                                fed_keys.add((n, v, d))
        federation_ok = multi_confederation_ok and len(fed_keys) >= 3

        # Deferred admission: max_active=1 grows confederation charter over time.
        campaign6 = _proof_campaign_runner(scratch / "dc")
        deferred = run_commonwealth(
            charter=[
                _confederation_slot(
                    "da",
                    priority=3,
                    institutions=[
                        _inst_slot(
                            "dai",
                            programs=[
                                _program_slot(
                                    "dap", initial=[("da", "1.0.0", "da-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                ),
                _confederation_slot(
                    "db",
                    priority=2,
                    institutions=[
                        _inst_slot(
                            "dbi",
                            programs=[
                                _program_slot(
                                    "dbp", initial=[("db", "1.0.0", "db-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                ),
                _confederation_slot(
                    "dc",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "dci",
                            programs=[
                                _program_slot(
                                    "dcp", initial=[("dc", "1.0.0", "dc-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                ),
            ],
            max_rounds=8,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=6,
            max_active_confederations=1,
            dispatch=True,
            campaign_runner=campaign6,
            commonwealth_goal="all_confederations_met",
            out_root=scratch / "dl",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("confederation_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["commonwealth_met"] is True
            and deferred["confederations_admitted"] == 3
            and deferred["confederations_met_count"] == 3
            and deferred.get("max_active_confederations") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        ok = all(
            [
                multi_confederation_ok,
                multi_confederation_scheduled,
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
            "commonwealth_met": multi_confederation_ok,
            "multi_confederation_progressed": multi_confederation_scheduled,
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
            "commonwealth_digest": confed.get("commonwealth_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "confederations_admitted": confed.get("confederations_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_confederation_ok": multi_confederation_ok,
                "multi_confederation_scheduled": multi_confederation_scheduled,
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
        result = verify_commonwealth_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_commonwealth_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
