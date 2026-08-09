"""Upstream confederation plane: multi-league durable stewardship confederation.

The league plane (``upstream_league``) closes multi-institution federations
*within one league*. It does not:

1. chain multiple independent leagues under a durable confederation constitution;
2. allocate a shared global dispatch budget across leagues by ROI;
3. admit/retire league slots from a confederation charter over time
   (deferred admission under a concurrent-active cap);
4. federate multi-league portfolio coverage into one confederation world-model;
5. persist confederation state so a later process can resume the union;
6. seal a multi-league confederation chronicle linking league digests.

The confederation plane closes that outer multi-league loop:

1. **admit** — materialize league slots from a durable confederation charter
   (each slot owns a nested institution charter). When ``max_active_leagues``
   is set, only that many *unmet* leagues are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (confederation constitution growth over time);
2. **schedule** — pick the next open league by priority and historical ROI;
3. **league** — call the league plane (injected ``league_runner``; default
   ``run_league``) with a share of the remaining global dispatch budget;
4. **federate** — merge per-league portfolios into one confederation world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark leagues met when their league_goal is satisfied, then
   re-admit pending charter slots up to the active capacity;
6. **persist** — write ``confederation_state.json`` after every league round so a
   later ``run_confederation(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
7. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across leagues
   - confederation goal met (``all_leagues_met``: every *admitted* league is
     met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

8. **seal** — write a confederation receipt under
   ``artifacts/upstream-confederation/`` with sha256 digests of every league,
   portfolio federation, admission history, ROI history, stop reason, and a
   confederation chain digest; ``verify_confederation_receipt`` re-checks the
   chain and detects tampering.

No skill-route discovery is used. The plane is confederation-level direction
over the league plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_league as ul
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-confederation"

TERMINAL_SUCCESS_OUTCOMES = ul.TERMINAL_SUCCESS_OUTCOMES


class ConfederationRefused(Exception):
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


def normalize_confederation_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a league charter into deterministic institution slots.

    Each slot is::

        {
          "league_id": str,
          "priority": int,
          "charter": [...institution slots...],  # nested league charter
          "max_active_institutions": int | None,
          "max_rounds": int,
          "league_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        league_id = str(
            raw.get("league_id") or raw.get("id") or ""
        ).strip()
        if not league_id or league_id in seen:
            continue
        seen.add(league_id)

        nested = ul.normalize_league_charter(
            raw.get("charter") or raw.get("institutions") or raw.get("programs")
        )
        if not nested:
            continue

        max_active_institutions = raw.get("max_active_institutions")
        if max_active_institutions is not None:
            max_active_institutions = max(1, int(max_active_institutions))

        out.append(
            {
                "league_id": league_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_institutions": max_active_institutions,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "league_goal": str(
                    raw.get("league_goal") or "all_institutions_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_league"),
            }
        )
    return out


def admit_league_slot(
    *,
    confederation_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with league_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    league_id = str(slot.get("league_id") or "")
    if not league_id:
        raise ConfederationRefused("confederation_invalid", "slot missing league_id")

    league_root = Path(confederation_dir) / "leagues" / league_id
    league_root.mkdir(parents=True, exist_ok=True)

    nested_charter = ul.normalize_league_charter(slot.get("charter"))
    if not nested_charter:
        raise ConfederationRefused(
            "confederation_invalid",
            f"institution slot {league_id!r} has empty nested charter",
        )

    return {
        "league_id": league_id,
        "league_root": str(league_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_institutions": slot.get("max_active_institutions"),
        "max_rounds": int(slot.get("max_rounds") or 6),
        "league_goal": str(slot.get("league_goal") or "all_institutions_met"),
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
        "source": "confederation_federation",
    }
    portfolio["portfolio_digest"] = _recompute_portfolio_digest(portfolio)
    return portfolio


def confederation_terminal_coverage(
    *,
    league_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """League coverage: every admitted institution's inventory is terminal-success."""
    required_keys: list[tuple[str, str, str]] = []
    for ist in league_states:
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
        # Nested institution states from a completed league round.
        for inst in list(ist.get("institution_states") or []):
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
        # Nested league charter institution slots when not yet run.
        for slot in list(ist.get("charter") or []):
            if not isinstance(slot, Mapping):
                continue
            for pslot in list(slot.get("charter") or []) + list(
                slot.get("programs") or []
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


def leagues_all_met(league_states: Sequence[Mapping[str, Any]]) -> bool:
    if not league_states:
        return False
    return all(bool(ist.get("league_met")) for ist in league_states)


def open_unmet_count(league_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet league_met."""
    return sum(1 for ist in league_states if not ist.get("league_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    league_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then league_id-asc."""
    known = {str(ist.get("league_id") or "") for ist in league_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("league_id") or "")
        and str(slot.get("league_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("league_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    league_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    confederation_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if confederation_goal == "none":
        return False
    if confederation_goal == "terminal_coverage":
        cov = confederation_terminal_coverage(
            league_states=league_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, league_states
        )
    if confederation_goal == "all_leagues_met":
        if not league_states:
            return False
        if pending_charter_slots(charter, league_states):
            return False
        return leagues_all_met(league_states)
    return False


def admit_pending_slots(
    *,
    confederation_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    league_states: list[dict[str, Any]],
    max_active_leagues: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_leagues`` caps *unmet* concurrent institutions. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``league_states``).
    """
    pending = pending_charter_slots(charter, league_states)
    if not pending:
        return []

    open_n = open_unmet_count(league_states)
    if max_active_leagues is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_leagues) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_league_slot(confederation_dir=confederation_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        league_states.append(
            {
                "league_id": admission["league_id"],
                "league_root": admission["league_root"],
                "charter": admission["charter"],
                "max_active_institutions": admission.get("max_active_institutions"),
                "max_rounds": admission["max_rounds"],
                "league_goal": admission["league_goal"],
                "priority": admission["priority"],
                "league_met": False,
                "last_league_dir": None,
                "last_league_digest": None,
                "portfolio": None,
                "institution_states": [],
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


# ---------------------------------------------------------------------------
# ROI + scheduling


def score_league_roi(
    *,
    round_index: int,
    league_id: str,
    league_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one institution round for league learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(league_result.get("total_dispatched_ok") or 0)
    dispatched = int(league_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "league_id": league_id,
        "stop_reason": league_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "league_met": bool(league_result.get("league_met")),
        "league_digest": league_result.get("league_digest"),
        "institutions_admitted": int(league_result.get("institutions_admitted") or 0),
        "institutions_met_count": int(league_result.get("institutions_met_count") or 0),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_league": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_league: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get("league_id") or "")
        bucket = by_league.setdefault(
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
    for iid, bucket in by_league.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_league": by_league,
    }


def select_next_league(
    league_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable league_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in league_states if not ist.get("league_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_league = summary.get("by_league") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("league_id") or "")
        hist = by_league.get(iid) or {}
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


def allocate_league_budget(
    *,
    remaining_budget: int | None,
    open_league_count: int,
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
    open_n = max(1, int(open_league_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_league") or {}).get(
        str(selected.get("league_id") or "")
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
    confederation_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    league_states: Sequence[Mapping[str, Any]],
    league_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    confederation_goal: str,
    max_active_leagues: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "confederation_id": confederation_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "league_states": [dict(ist) for ist in league_states],
        "league_digests": list(league_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "confederation_goal": confederation_goal,
        "max_active_leagues": max_active_leagues,
        "admissions": [dict(a) for a in (admissions or [])],
        "pending_confederation_ids": [
            str(s.get("league_id") or "")
            for s in pending_charter_slots(charter, league_states)
        ],
    }


def write_confederation_state(confederation_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(confederation_dir) / "confederation_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_confederation_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "confederation_state.json")
    if not path.is_file():
        raise ConfederationRefused(
            "confederation_state_missing",
            f"no confederation_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfederationRefused("confederation_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise ConfederationRefused("confederation_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _league_round_record(
    *,
    round_index: int,
    league_id: str,
    league_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "league_id": league_id,
        "ok": bool(league_result.get("ok")),
        "verdict": league_result.get("verdict"),
        "stop_reason": league_result.get("stop_reason"),
        "league_dir": league_result.get("league_dir"),
        "league_digest": league_result.get("league_digest"),
        "institutions_admitted": int(league_result.get("institutions_admitted") or 0),
        "institutions_met_count": int(league_result.get("institutions_met_count") or 0),
        "total_dispatched": int(league_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(league_result.get("total_dispatched_ok") or 0),
        "league_met": bool(league_result.get("league_met")),
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


def _confederation_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "confederation_id": receipt.get("confederation_id"),
        "confederation_goal": receipt.get("confederation_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_leagues": receipt.get("max_active_leagues"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "league_digests": list(receipt.get("league_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "confederation_met": receipt.get("confederation_met"),
        "coverage_end": receipt.get("coverage_end"),
        "leagues_met_count": receipt.get("leagues_met_count"),
        "leagues_admitted": receipt.get("leagues_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_confederation_receipt(confederation_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(confederation_dir) / "confederation.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_confederation_digest_payload(receipt))
    recorded = str(receipt.get("confederation_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("confederation_digest")

    institutions = list(receipt.get("leagues") or [])
    listed = list(receipt.get("league_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("league_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("league_digest"):
                mismatched.append(f"league_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("league_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "league.json").is_file():
            nested = ul.verify_league_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "confederation_sealed" if ok else "confederation_tampered",
        "confederation_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run league


def run_confederation(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_leagues: int | None = None,
    dispatch: bool = True,
    league_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    confederation_goal: str = "all_leagues_met",
    refresh_promotions: Mapping[str, str] | None = None,
    confederation_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_confederation_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_leagues:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    confederation_goal:
        ``all_leagues_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``confederation_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise ConfederationRefused("confederation_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise ConfederationRefused(
            "confederation_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_leagues is not None and int(max_active_leagues) < 1:
        raise ConfederationRefused(
            "confederation_invalid", "max_active_leagues must be >= 1 when set"
        )
    if confederation_goal not in {"all_leagues_met", "terminal_coverage", "none"}:
        raise ConfederationRefused(
            "confederation_invalid",
            f"unknown confederation_goal: {confederation_goal}",
        )

    runner = league_runner or ul.run_league

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    league_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_confederation_id: str | None = None
    league_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_confederation_state(resume_dir)
        resumed = True
        resume_confederation_id = str(state.get("confederation_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        league_digests = [str(d) for d in (state.get("league_digests") or [])]
        league_states = [
            dict(ist)
            for ist in (state.get("league_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_confederation_charter(
                [e for e in state["charter"] if isinstance(e, Mapping)]
            )
        if isinstance(state.get("admissions"), list):
            admissions = [
                dict(a) for a in state["admissions"] if isinstance(a, Mapping)
            ]
        if (
            state.get("max_active_leagues") is not None
            and max_active_leagues is None
        ):
            resumed_max_active = int(state["max_active_leagues"])
    else:
        active_charter = normalize_confederation_charter(charter)

    active_max = (
        max_active_leagues
        if max_active_leagues is not None
        else resumed_max_active
    )

    if not active_charter and not league_states:
        raise ConfederationRefused(
            "confederation_empty",
            "league charter has no admitable institution slots",
        )

    lid = (
        confederation_id
        or resume_confederation_id
        or f"league-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        confederation_dir = Path(out_root)
        if (confederation_dir / "confederation.json").is_file():
            confederation_dir = confederation_dir / stamp
    else:
        confederation_dir = ARTIFACTS_ROOT / stamp
    confederation_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    lg_root = (
        Path(league_out_root) if league_out_root else (confederation_dir / "ir")
    )
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root = confederation_dir / "pr"
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        confederation_dir=confederation_dir,
        charter=active_charter,
        league_states=league_states,
        max_active_leagues=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not league_states and not pending_charter_slots(
        active_charter, league_states
    ):
        raise ConfederationRefused("confederation_empty", "no institution slots admitted")
    if not league_states and pending_charter_slots(
        active_charter, league_states
    ):
        raise ConfederationRefused(
            "confederation_empty",
            "no institution slots admitted under max_active_leagues policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in league_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    confederation_met = False
    coverage_end: dict[str, Any] = confederation_terminal_coverage(
        league_states=league_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            confederation_dir=confederation_dir,
            charter=active_charter,
            league_states=league_states,
            max_active_leagues=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = confederation_terminal_coverage(
            league_states=league_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            league_states=league_states,
            charter=active_charter,
            confederation_goal=confederation_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "confederation_met"
            confederation_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_league(
            league_states, roi_history, round_index=round_index
        )
        if selected is None:
            if not pending_charter_slots(active_charter, league_states):
                stop_reason = "confederation_met"
                confederation_met = True
            else:
                stop_reason = "confederation_idle"
            coverage_end = coverage_before
            break

        open_count = sum(
            1 for ist in league_states if not ist.get("league_met")
        )
        allocated = allocate_league_budget(
            remaining_budget=remaining_budget,
            open_league_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        league_id = str(selected["league_id"])
        resume_league_dir = selected.get("last_league_dir")
        league_resume: Path | None = None
        if (
            resume_league_dir
            and (Path(str(resume_league_dir)) / "institution_state.json").is_file()
            and not selected.get("league_met")
        ):
            league_resume = Path(str(resume_league_dir))

        # Short stamp: r00-ia (avoid deep Windows paths under succession/epoch/wave).
        safe_id = "".join(c if c.isalnum() else "" for c in league_id)[:12] or "i"
        out_dir = lg_root / f"r{round_index:02d}-{safe_id}"
        inst_out = inst_flat_root / f"r{round_index:02d}-{safe_id}"
        league_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "league_goal": str(
                selected.get("league_goal") or "all_institutions_met"
            ),
            "league_id": league_id,
            "out_root": out_dir,
            "institution_out_root": inst_out,
        }
        if selected.get("max_active_institutions") is not None:
            league_kwargs["max_active_institutions"] = int(
                selected["max_active_institutions"]
            )
        if league_resume is not None:
            league_kwargs["resume_dir"] = league_resume
            # charter already on resume state
            league_kwargs.pop("charter", None)
        if program_runner is not None:
            league_kwargs["program_runner"] = program_runner
        if campaign_runner is not None:
            league_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            league_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            league_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            league_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            league_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            league_kwargs["refresh_promotions"] = refresh_promotions

        try:
            league_result = runner(**league_kwargs)
        except ul.LeagueRefused as exc:
            if local_index == 0 and not resumed:
                raise ConfederationRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"league_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise ConfederationRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise ConfederationRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(league_result.get("total_dispatched") or 0)
        dispatched_ok = int(league_result.get("total_dispatched_ok") or 0)
        prior_inst_dispatched = int(selected.get("total_dispatched") or 0)
        prior_inst_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_inst_dispatched)
        delta_ok = max(0, dispatched_ok - prior_inst_ok)
        if league_resume is None and prior_inst_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        nested_league_dir = league_result.get("league_dir")
        nested_institution_states: list[dict[str, Any]] = []
        if nested_league_dir and (Path(str(nested_league_dir)) / "league.json").is_file():
            receipt = json.loads(
                (Path(str(nested_league_dir)) / "league.json").read_text(
                    encoding="utf-8"
                )
            )
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(receipt.get("institution_states") or []):
                if isinstance(ist, Mapping):
                    nested_institution_states.append(dict(ist))
        if after_portfolio is None and isinstance(
            league_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(league_result["federated_portfolio"])  # type: ignore[index]
        if not nested_institution_states:
            for ist in list(league_result.get("institution_states") or []):
                if isinstance(ist, Mapping):
                    nested_institution_states.append(dict(ist))

        for i, lst in enumerate(league_states):
            if str(lst.get("league_id")) != league_id:
                continue
            updated = dict(lst)
            updated["last_league_dir"] = league_result.get("league_dir")
            updated["last_league_digest"] = league_result.get("league_digest")
            updated["league_met"] = bool(league_result.get("league_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_institution_states:
                updated["institution_states"] = nested_institution_states
            league_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in league_states]
        )
        coverage_after = confederation_terminal_coverage(
            league_states=league_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_league_roi(
            round_index=round_index,
            league_id=league_id,
            league_result=league_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(league_result.get("league_digest") or "")
        if idigest:
            league_digests.append(idigest)

        rec = _league_round_record(
            round_index=round_index,
            league_id=league_id,
            league_result=league_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            confederation_dir=confederation_dir,
            charter=active_charter,
            league_states=league_states,
            max_active_leagues=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = confederation_terminal_coverage(
                league_states=league_states,
                federated_portfolio=federated_portfolio,
            )

        write_confederation_state(
            confederation_dir,
            _state_payload(
                confederation_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                league_states=league_states,
                league_digests=league_digests,
                charter=active_charter,
                stop_reason=None,
                confederation_goal=confederation_goal,
                max_active_leagues=active_max,
                admissions=admissions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not league_result.get("league_met")
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
                    "league_states": league_states,
                    "last_league_id": league_id,
                    "federated_portfolio": federated_portfolio,
                    "confederation_dir": str(confederation_dir),
                    "pending_league_ids": [
                        str(s.get("league_id") or "")
                        for s in pending_charter_slots(
                            active_charter, league_states
                        )
                    ],
                    "admissions": admissions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        if constitution_satisfied(
            league_states=league_states,
            charter=active_charter,
            confederation_goal=confederation_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "confederation_met"
            confederation_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            league_states=league_states,
            charter=active_charter,
            confederation_goal=confederation_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "confederation_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        confederation_dir=confederation_dir,
        charter=active_charter,
        league_states=league_states,
        max_active_leagues=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in league_states]
    )
    coverage_end = confederation_terminal_coverage(
        league_states=league_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        league_states=league_states,
        charter=active_charter,
        confederation_goal=confederation_goal,
        federated_portfolio=federated_portfolio,
    ):
        confederation_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    leagues_met_count = sum(
        1 for ist in league_states if ist.get("league_met")
    )
    pending_remaining = [
        str(s.get("league_id") or "")
        for s in pending_charter_slots(active_charter, league_states)
    ]

    if confederation_met and stop_reason in {"confederation_met", "max_rounds"}:
        verdict = "confederation_met"
        ok = True
        stop_reason = "confederation_met"
    elif stop_reason == "rank_only":
        verdict = "confederation_ranked"
        ok = True
    elif stop_reason == "confederation_idle":
        verdict = "confederation_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "confederation_budgeted"
        ok = True
    elif stop_reason.startswith("league_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "confederation_refused_mid"
        ok = False
    else:
        verdict = "confederation_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "confederation_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_leagues": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "confederation_goal": confederation_goal,
        "confederation_met": confederation_met,
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
        "leagues": institutions,
        "league_digests": [
            i.get("league_digest")
            for i in institutions
            if i.get("league_digest")
        ],
        "league_states": league_states,
        "leagues_admitted": len(league_states),
        "leagues_met_count": leagues_met_count,
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
    receipt["league_digests"] = [
        str(i.get("league_digest") or "") for i in institutions
    ]
    receipt["confederation_digest"] = _sha256_json(_confederation_digest_payload(receipt))
    atomic_write_json(confederation_dir / "confederation.json", receipt)
    atomic_write_json(
        confederation_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "confederation_id": receipt["confederation_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "confederation_met": receipt["confederation_met"],
            "leagues_admitted": receipt["leagues_admitted"],
            "leagues_met_count": receipt["leagues_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "max_active_leagues": receipt["max_active_leagues"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "confederation_digest": receipt["confederation_digest"],
            "resumed": resumed,
        },
    )

    write_confederation_state(
        confederation_dir,
        _state_payload(
            confederation_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            league_states=league_states,
            league_digests=receipt["league_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            confederation_goal=confederation_goal,
            max_active_leagues=active_max,
            admissions=admissions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "confederation_dir": str(confederation_dir),
        "confederation_digest": receipt["confederation_digest"],
        "confederation_id": lid,
        "round_count": len(institutions),
        "league_digests": list(receipt["league_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "confederation_met": confederation_met,
        "leagues_admitted": len(league_states),
        "leagues_met_count": leagues_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_leagues": active_max,
        "admissions": admissions,
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "league_states": league_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "leagues": institutions,
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
    return ul._program_slot(
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
    return ul._inst_slot(
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
    """Build a hermetic confederation charter league slot."""
    return {
        "league_id": league_id,
        "priority": priority,
        "charter": list(institutions or []),
        "max_rounds": max_rounds,
        "league_goal": league_goal,
        "max_active_institutions": max_active_institutions,
    }


def builtin_upstream_confederation_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-league confederation plane (no network)."""
    scratch = Path(tempfile.mkdtemp(prefix="confed-proof-"))
    try:
        campaign = _proof_campaign_runner(scratch)

        # Two leagues, each with nested institution/program work.
        # Short ids keep Windows nested artifact paths under MAX_PATH.
        charter = [
            _league_slot(
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
            _league_slot(
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

        confed = run_confederation(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            confederation_goal="all_leagues_met",
            out_root=scratch / "m",
        )
        multi_league_ok = (
            confed["ok"]
            and confed["confederation_met"] is True
            and confed["stop_reason"] == "confederation_met"
            and confed["leagues_admitted"] == 2
            and confed["leagues_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        scheduled_ids = {
            i.get("league_id") for i in (confed.get("leagues") or [])
        }
        multi_league_scheduled = multi_league_ok and scheduled_ids >= {"la", "lb"}

        verified = verify_confederation_receipt(Path(confed["confederation_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed[
            "round_count"
        ]

        # Tamper detection.
        confed_path = Path(confed["confederation_dir"]) / "confederation.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["confederation_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_confederation_receipt(Path(confed["confederation_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "confederation_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across leagues.
        campaign2 = _proof_campaign_runner(scratch / "b")
        budgeted = run_confederation(
            charter=[
                _league_slot(
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
                _league_slot(
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
            confederation_goal="none",
            out_root=scratch / "bg",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit via custom league_runner.
        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            nested_charter = ul.normalize_league_charter(kwargs.get("charter"))
            entries: list[dict[str, Any]] = []
            institution_states: list[dict[str, Any]] = []
            for slot in nested_charter:
                inst_entries: list[dict[str, Any]] = []
                for pslot in list(slot.get("charter") or []):
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
                institution_states.append(
                    {
                        "institution_id": slot.get("institution_id"),
                        "institution_met": True,
                        "charter": list(slot.get("charter") or []),
                        "portfolio": uf._proof_portfolio(inst_entries),
                        "program_states": [],
                    }
                )
            portfolio = uf._proof_portfolio(entries)
            digest = _sha256_json({"premet": True, "entries": len(entries)})
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "league_met",
                "stop_reason": "league_met",
                "league_id": kwargs.get("league_id"),
                "league_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "institutions_admitted": len(nested_charter),
                "institutions_met_count": len(nested_charter),
                "league_digest": digest,
                "federated_portfolio": portfolio,
                "institution_states": institution_states,
                "coverage_end": {
                    "required": len(entries),
                    "covered": len(entries),
                    "met": True,
                    "coverage_ratio": 1.0,
                },
            }
            atomic_write_json(out / "league.json", receipt)
            atomic_write_json(
                out / "league_state.json",
                {
                    "league_id": kwargs.get("league_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "institution_states": institution_states,
                    "stop_reason": "league_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "league_met",
                "stop_reason": "league_met",
                "league_dir": str(out),
                "league_digest": digest,
                "league_id": kwargs.get("league_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "league_met": True,
                "institutions_admitted": len(nested_charter),
                "institutions_met_count": len(nested_charter),
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "institution_states": institution_states,
                "used_skill_route_discovery": False,
            }

        pre_met = run_confederation(
            charter=[
                _league_slot(
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
            league_runner=_premet_runner,
            confederation_goal="all_leagues_met",
            out_root=scratch / "pm",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["confederation_met"] is True
            and pre_met["stop_reason"] == "confederation_met"
            and pre_met["leagues_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only confederation.
        ranked = run_confederation(
            charter=[
                _league_slot(
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
                _league_slot(
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
            confederation_goal="none",
            out_root=scratch / "rk",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "confederation_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_confederation(
                charter=[],
                dispatch=False,
                confederation_goal="none",
                out_root=scratch / "e",
            )
        except ConfederationRefused as exc:
            empty_refused = exc.verdict in {
                "confederation_empty",
                "confederation_invalid",
            }

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_confederation(
            charter=[
                _league_slot(
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
                _league_slot(
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
            confederation_goal="none",
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
        partial = run_confederation(
            charter=[
                _league_slot(
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
                _league_slot(
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
            confederation_goal="none",
            confederation_id="resume-confed-proof",
            out_root=scratch / "pa",
        )
        state_path = Path(partial["confederation_dir"]) / "confederation_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "rb")
        resumed = run_confederation(
            resume_dir=Path(partial["confederation_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            confederation_goal="none",
            out_root=scratch / "rs",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["confederation_id"] == "resume-confed-proof"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-league budget allocation evidence.
        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_league"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_league") or {}) >= 2
        )

        first_league = (confed.get("leagues") or [{}])[0].get("league_id")
        priority_ok = first_league == "la"

        # Federation: inventories across both leagues form a joint surface.
        fed_keys: set[tuple[str, str, str]] = set()
        for lst in confed.get("league_states") or []:
            for ist in lst.get("institution_states") or []:
                if not isinstance(ist, Mapping):
                    continue
                for ps in ist.get("program_states") or []:
                    stew = (
                        ps.get("stewardship_root") if isinstance(ps, Mapping) else None
                    )
                    if stew:
                        for n, v, d in up.inventory_defect_keys(Path(str(stew))):
                            fed_keys.add((n, v, d))
        federation_ok = multi_league_ok and len(fed_keys) >= 3

        # Deferred admission: max_active=1 grows confederation charter over time.
        campaign6 = _proof_campaign_runner(scratch / "dc")
        deferred = run_confederation(
            charter=[
                _league_slot(
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
                _league_slot(
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
                _league_slot(
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
            max_active_leagues=1,
            dispatch=True,
            campaign_runner=campaign6,
            confederation_goal="all_leagues_met",
            out_root=scratch / "dl",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("league_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["confederation_met"] is True
            and deferred["leagues_admitted"] == 3
            and deferred["leagues_met_count"] == 3
            and deferred.get("max_active_leagues") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        ok = all(
            [
                multi_league_ok,
                multi_league_scheduled,
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
            "confederation_met": multi_league_ok,
            "multi_league_progressed": multi_league_scheduled,
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
            "confederation_digest": confed.get("confederation_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "leagues_admitted": confed.get("leagues_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_league_ok": multi_league_ok,
                "multi_league_scheduled": multi_league_scheduled,
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
        result = verify_confederation_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_confederation_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
