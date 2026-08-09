"""Upstream civilization plane: multi-empire durable stewardship civilization.

The empire plane (``upstream_empire``) closes multi-realm unions *within one
empire*. It does not:

1. chain multiple independent empires under a durable civilization constitution;
2. allocate a shared global dispatch budget across empires by ROI;
3. admit/retire empire slots from a civilization charter over time
   (deferred admission under a concurrent-active cap);
4. grow the civilization charter mid-run via ``charter_expand`` (constitution
   growth beyond the initial charter, not just deferred admission of a fixed set);
5. federate multi-empire portfolio coverage into one civilization world-model;
6. persist civilization state so a later process can resume the union;
7. seal a multi-empire civilization chronicle linking empire digests.

The civilization plane closes that outer multi-empire loop:

1. **admit** — materialize empire slots from a durable civilization charter
   (each slot owns a nested realm charter). When ``max_active_empires``
   is set, only that many *unmet* empires are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (civilization constitution growth over time);
2. **schedule** — pick the next open empire by priority and historical ROI;
3. **empire** — call the empire plane (injected ``empire_runner``;
   default ``run_empire``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-empire portfolios into one civilization world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark empires met when their empire_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **expand** — optional ``charter_expand`` may append new empire slots when
   the active charter has no pending work and all admitted empires are met,
   so the civilization constitution can grow after start (not only defer a fixed charter);
7. **persist** — write ``civilization_state.json`` after every empire round so a
   later ``run_civilization(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
8. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across empires
   - civilization goal met (``all_empires_met``: every *admitted*
     empire is met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

9. **seal** — write a civilization receipt under
   ``artifacts/upstream-civilization/`` with sha256 digests of every
   empire, portfolio federation, admission history, ROI history, stop
   reason, and a civilization chain digest; ``verify_civilization_receipt``
   re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is civilization-level direction
over the empire plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_empire as ue
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-civilization"

TERMINAL_SUCCESS_OUTCOMES = ue.TERMINAL_SUCCESS_OUTCOMES


class CivilizationRefused(Exception):
    """A verdict-bearing refusal: the realm must not continue."""

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


def normalize_civilization_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a empire charter into deterministic realm slots.

    Each slot is::

        {
          "empire_id": str,
          "priority": int,
          "charter": [...league slots...],  # nested domain charter
          "max_active_realms": int | None,
          "max_rounds": int,
          "empire_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        empire_id = str(
            raw.get("empire_id") or raw.get("id") or ""
        ).strip()
        if not empire_id or empire_id in seen:
            continue
        seen.add(empire_id)

        nested = ue.normalize_empire_charter(
            raw.get("charter")
            or raw.get("realms") or raw.get("domains")
            or raw.get("confederations")
            or raw.get("leagues")
            or raw.get("institutions")
            or raw.get("programs")
        )
        if not nested:
            continue

        max_active_realms = raw.get("max_active_realms")
        if max_active_realms is not None:
            max_active_realms = max(1, int(max_active_realms))

        out.append(
            {
                "empire_id": empire_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_realms": max_active_realms,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "empire_goal": str(
                    raw.get("empire_goal") or "all_realms_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_empire"),
            }
        )
    return out


def admit_empire_slot(
    *,
    civilization_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with empire_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    empire_id = str(slot.get("empire_id") or "")
    if not empire_id:
        raise CivilizationRefused("civilization_invalid", "slot missing empire_id")

    empire_root = Path(civilization_dir) / "empires" / empire_id
    empire_root.mkdir(parents=True, exist_ok=True)

    nested_charter = ue.normalize_empire_charter(slot.get("charter"))
    if not nested_charter:
        raise CivilizationRefused(
            "civilization_invalid",
            f"institution slot {empire_id!r} has empty nested charter",
        )

    return {
        "empire_id": empire_id,
        "empire_root": str(empire_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_realms": slot.get("max_active_realms"),
        "max_rounds": int(slot.get("max_rounds") or 6),
        "empire_goal": str(slot.get("empire_goal") or "all_realms_met"),
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
        "source": "civilization_federation",
    }
    portfolio["portfolio_digest"] = _recompute_portfolio_digest(portfolio)
    return portfolio


def _collect_program_target_keys(pslot: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    keys: list[tuple[str, str, str]] = []
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
                keys.append((name, version, did))
    return keys


def _collect_from_institution_state(inst: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    keys: list[tuple[str, str, str]] = []
    for ps in list(inst.get("program_states") or []):
        if not isinstance(ps, Mapping):
            continue
        stew = ps.get("stewardship_root")
        if not stew:
            continue
        root = Path(str(stew))
        if root.is_dir():
            keys.extend(up.inventory_defect_keys(root))
    for slot in list(inst.get("charter") or []) + list(inst.get("programs") or []):
        if isinstance(slot, Mapping):
            keys.extend(_collect_program_target_keys(slot))
    return keys


def _collect_from_league_state(lg: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    keys: list[tuple[str, str, str]] = []
    for inst in list(lg.get("institution_states") or []):
        if isinstance(inst, Mapping):
            keys.extend(_collect_from_institution_state(inst))
    for islot in list(lg.get("charter") or []) + list(lg.get("institutions") or []):
        if not isinstance(islot, Mapping):
            continue
        for pslot in list(islot.get("charter") or []) + list(islot.get("programs") or []):
            if isinstance(pslot, Mapping):
                keys.extend(_collect_program_target_keys(pslot))
    return keys


def _collect_from_confederation_state(cf: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    keys: list[tuple[str, str, str]] = []
    for lg in list(cf.get("league_states") or []):
        if isinstance(lg, Mapping):
            keys.extend(_collect_from_league_state(lg))
    for lslot in list(cf.get("charter") or []) + list(cf.get("leagues") or []):
        if not isinstance(lslot, Mapping):
            continue
        for islot in list(lslot.get("charter") or []) + list(lslot.get("institutions") or []):
            if not isinstance(islot, Mapping):
                continue
            for pslot in list(islot.get("charter") or []) + list(islot.get("programs") or []):
                if isinstance(pslot, Mapping):
                    keys.extend(_collect_program_target_keys(pslot))
    return keys


def _collect_from_commonwealth_state(cw: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    keys: list[tuple[str, str, str]] = []
    for cf in list(cw.get("confederation_states") or []) + list(
        cw.get("league_states") or []
    ):
        if isinstance(cf, Mapping):
            keys.extend(_collect_from_confederation_state(cf))
    for cslot in list(cw.get("charter") or []) + list(cw.get("confederations") or []):
        if not isinstance(cslot, Mapping):
            continue
        for lslot in list(cslot.get("charter") or []) + list(cslot.get("leagues") or []):
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
                    if isinstance(pslot, Mapping):
                        keys.extend(_collect_program_target_keys(pslot))
    return keys


def _collect_from_domain_state(dom: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Walk a domain-shaped state/charter down to program inventory keys."""
    keys: list[tuple[str, str, str]] = []
    for cws in list(dom.get("commonwealth_states") or []):
        if isinstance(cws, Mapping):
            keys.extend(_collect_from_commonwealth_state(cws))
    for cslot in list(dom.get("charter") or []) + list(dom.get("commonwealths") or []):
        if isinstance(cslot, Mapping):
            keys.extend(_collect_from_commonwealth_state(cslot))
    return keys


def _collect_from_realm_state(realm: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Walk a realm-shaped state/charter (domains) down to program keys."""
    keys: list[tuple[str, str, str]] = []
    for ds in list(realm.get("domain_states") or []):
        if isinstance(ds, Mapping):
            keys.extend(_collect_from_domain_state(ds))
    for dslot in list(realm.get("charter") or []) + list(realm.get("domains") or []):
        if isinstance(dslot, Mapping):
            # realm charter slots may be domain-shaped or already commonwealth-shaped
            if dslot.get("domain_id") or dslot.get("commonwealths") or dslot.get("commonwealth_states"):
                keys.extend(_collect_from_domain_state(dslot))
            else:
                keys.extend(_collect_from_domain_state(dslot))
    # Also accept commonwealth nesting directly on simplified proof mocks
    for cws in list(realm.get("commonwealth_states") or []):
        if isinstance(cws, Mapping):
            keys.extend(_collect_from_commonwealth_state(cws))
    return keys


def civilization_terminal_coverage(
    *,
    empire_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Realm coverage across domain→commonwealth→…→program."""
    required_keys: list[tuple[str, str, str]] = []
    for dom in empire_states:
        for raw in list(dom.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                required_keys.append((str(raw[0]), str(raw[1]), str(raw[2])))
                continue
            if isinstance(raw, Mapping):
                n = str(raw.get("name") or "")
                v = str(raw.get("version") or "")
                d = str(raw.get("defect_id") or raw.get("id") or "")
                if n and d:
                    required_keys.append((n, v, d))
        # Nested realm_states from a completed domain round.
        for cws in list(dom.get("realm_states") or []):
            if isinstance(cws, Mapping):
                required_keys.extend(_collect_from_realm_state(cws))
        # Nested domain charter (commonwealth → confederation → … → program).
        for cslot in list(dom.get("charter") or []) + list(dom.get("realms") or []):
            if not isinstance(cslot, Mapping):
                continue
            required_keys.extend(_collect_from_realm_state(cslot))

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


def empires_all_met(empire_states: Sequence[Mapping[str, Any]]) -> bool:
    if not empire_states:
        return False
    return all(bool(ist.get("empire_met")) for ist in empire_states)


def open_unmet_count(empire_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet empire_met."""
    return sum(1 for ist in empire_states if not ist.get("empire_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    empire_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then empire_id-asc."""
    known = {str(ist.get("empire_id") or "") for ist in empire_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("empire_id") or "")
        and str(slot.get("empire_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("empire_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    empire_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    civilization_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if civilization_goal == "none":
        return False
    if civilization_goal == "terminal_coverage":
        cov = civilization_terminal_coverage(
            empire_states=empire_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, empire_states
        )
    if civilization_goal == "all_empires_met":
        if not empire_states:
            return False
        if pending_charter_slots(charter, empire_states):
            return False
        return empires_all_met(empire_states)
    return False


def merge_civilization_charter(
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge additional realm slots into a empire charter.

    Existing ``empire_id`` values win (additions with the same id are
    ignored). Returns a fully re-normalized charter so nested confederation
    charters stay deterministic.
    """
    base = normalize_civilization_charter(existing)
    if not additions:
        return base
    known = {str(s.get("empire_id") or "") for s in base}
    merged: list[Mapping[str, Any]] = list(base)
    for raw in additions:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get("empire_id") or raw.get("id") or "").strip()
        if not cid or cid in known:
            continue
        known.add(cid)
        merged.append(raw)
    return normalize_civilization_charter(merged)


def make_civilization_charter_expand(
    growth: Sequence[Mapping[str, Any]],
    *,
    max_slots_per_expand: int = 1,
    applied: Sequence[str] | None = None,
) -> Callable[..., dict[str, Any]]:
    """Build a charter-expand runner that appends realm slots mid-run.

    Invoked when every *admitted* domain is met and no pending slots
    remain on the active charter. Returns ``{"expanded": bool, "added": [...],
    "charter": [...]}`` where ``charter`` is the full merged charter.
    """
    pending_growth = normalize_civilization_charter(growth)
    applied_ids: set[str] = set(str(x) for x in (applied or []))
    state: dict[str, Any] = {
        "applied": applied_ids,
        "growth": pending_growth,
        "max_slots_per_expand": max(1, int(max_slots_per_expand)),
    }

    def _runner(
        *,
        active_charter: Sequence[Mapping[str, Any]],
        empire_states: Sequence[Mapping[str, Any]],
        round_index: int,
        roi_history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        remaining = [
            s
            for s in pending_growth
            if str(s.get("empire_id") or "") not in applied_ids
            and str(s.get("empire_id") or "")
            not in {str(x.get("empire_id") or "") for x in active_charter}
        ]
        if not remaining:
            return {
                "expanded": False,
                "added": [],
                "charter": list(active_charter),
                "detail": "charter_growth_exhausted",
                "round_index": round_index,
            }
        # ROI-productive realms may take one extra slot.
        batch = int(state["max_slots_per_expand"])
        summary = _roi_summary(roi_history)
        if float(summary.get("mean_efficiency") or 0.0) > 0.0 and int(
            summary.get("total_dispatched_ok") or 0
        ) > 0:
            batch = min(len(remaining), batch + 1)
        take = remaining[:batch]
        for s in take:
            applied_ids.add(str(s.get("empire_id") or ""))
        merged = merge_civilization_charter(active_charter, take)
        state["applied"] = applied_ids
        return {
            "expanded": True,
            "added": [str(s.get("empire_id") or "") for s in take],
            "charter": merged,
            "detail": "charter_growth_applied",
            "round_index": round_index,
            "realms_met": empires_all_met(empire_states),
        }

    _runner.charter_state = state  # type: ignore[attr-defined]
    return _runner


def admit_pending_slots(
    *,
    civilization_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    empire_states: list[dict[str, Any]],
    max_active_empires: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_empires`` caps *unmet* concurrent realms. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``empire_states``).
    """
    pending = pending_charter_slots(charter, empire_states)
    if not pending:
        return []

    open_n = open_unmet_count(empire_states)
    if max_active_empires is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_empires) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_empire_slot(civilization_dir=civilization_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        empire_states.append(
            {
                "empire_id": admission["empire_id"],
                "empire_root": admission["empire_root"],
                "charter": admission["charter"],
                "max_active_realms": admission.get("max_active_realms"),
                "max_rounds": admission["max_rounds"],
                "empire_goal": admission["empire_goal"],
                "priority": admission["priority"],
                "empire_met": False,
                "last_empire_dir": None,
                "last_empire_digest": None,
                "portfolio": None,
                "realm_states": [],
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


# ---------------------------------------------------------------------------
# ROI + scheduling


def score_empire_roi(
    *,
    round_index: int,
    empire_id: str,
    empire_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one institution round for league learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(empire_result.get("total_dispatched_ok") or 0)
    dispatched = int(empire_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "empire_id": empire_id,
        "stop_reason": empire_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "empire_met": bool(empire_result.get("empire_met")),
        "empire_digest": empire_result.get("empire_digest"),
        "realms_admitted": int(empire_result.get("realms_admitted") or 0),
        "realms_met_count": int(empire_result.get("realms_met_count") or 0),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_empire": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_empire: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get("empire_id") or "")
        bucket = by_empire.setdefault(
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
    for iid, bucket in by_empire.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_empire": by_empire,
    }


def select_next_empire(
    empire_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable empire_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in empire_states if not ist.get("empire_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_empire = summary.get("by_empire") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("empire_id") or "")
        hist = by_empire.get(iid) or {}
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


def allocate_empire_budget(
    *,
    remaining_budget: int | None,
    open_empire_count: int,
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
    open_n = max(1, int(open_empire_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_empire") or {}).get(
        str(selected.get("empire_id") or "")
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
    civilization_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    empire_states: Sequence[Mapping[str, Any]],
    empire_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    civilization_goal: str,
    max_active_empires: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
    charter_expansions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "civilization_id": civilization_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "empire_states": [dict(ist) for ist in empire_states],
        "empire_digests": list(empire_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "civilization_goal": civilization_goal,
        "max_active_empires": max_active_empires,
        "admissions": [dict(a) for a in (admissions or [])],
        "charter_expansions": [dict(e) for e in (charter_expansions or [])],
        "pending_empire_ids": [
            str(s.get("empire_id") or "")
            for s in pending_charter_slots(charter, empire_states)
        ],
    }


def write_civilization_state(civilization_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(civilization_dir) / "civilization_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_civilization_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "civilization_state.json")
    if not path.is_file():
        raise CivilizationRefused(
            "civilization_state_missing",
            f"no civilization_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CivilizationRefused("civilization_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise CivilizationRefused("civilization_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _empire_round_record(
    *,
    round_index: int,
    empire_id: str,
    empire_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "empire_id": empire_id,
        "ok": bool(empire_result.get("ok")),
        "verdict": empire_result.get("verdict"),
        "stop_reason": empire_result.get("stop_reason"),
        "empire_dir": empire_result.get("empire_dir"),
        "empire_digest": empire_result.get("empire_digest"),
        "realms_admitted": int(empire_result.get("realms_admitted") or 0),
        "realms_met_count": int(empire_result.get("realms_met_count") or 0),
        "total_dispatched": int(empire_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(empire_result.get("total_dispatched_ok") or 0),
        "empire_met": bool(empire_result.get("empire_met")),
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


def _civilization_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "civilization_id": receipt.get("civilization_id"),
        "civilization_goal": receipt.get("civilization_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_empires": receipt.get("max_active_empires"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "empire_digests": list(receipt.get("empire_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "civilization_met": receipt.get("civilization_met"),
        "coverage_end": receipt.get("coverage_end"),
        "empires_met_count": receipt.get("empires_met_count"),
        "empires_admitted": receipt.get("empires_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "charter_expansion_count": receipt.get("charter_expansion_count"),
        "charter_expanded_ids": list(receipt.get("charter_expanded_ids") or []),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_civilization_receipt(civilization_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(civilization_dir) / "civilization.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_civilization_digest_payload(receipt))
    recorded = str(receipt.get("civilization_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("civilization_digest")

    institutions = list(receipt.get("empires") or receipt.get("realms") or receipt.get("leagues") or [])
    listed = list(receipt.get("empire_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("empire_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("empire_digest"):
                mismatched.append(f"empire_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("empire_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "empire.json").is_file():
            nested = ue.verify_empire_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "civilization_sealed" if ok else "civilization_tampered",
        "civilization_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run realm


def run_civilization(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_empires: int | None = None,
    dispatch: bool = True,
    empire_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    charter_expand: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    civilization_goal: str = "all_empires_met",
    refresh_promotions: Mapping[str, str] | None = None,
    civilization_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_civilization_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_empires:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    civilization_goal:
        ``all_empires_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``civilization_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise CivilizationRefused("civilization_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise CivilizationRefused(
            "civilization_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_empires is not None and int(max_active_empires) < 1:
        raise CivilizationRefused(
            "civilization_invalid", "max_active_empires must be >= 1 when set"
        )
    if civilization_goal not in {"all_empires_met", "terminal_coverage", "none"}:
        raise CivilizationRefused(
            "civilization_invalid",
            f"unknown civilization_goal: {civilization_goal}",
        )

    runner = empire_runner or ue.run_empire

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    empire_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_civilization_id: str | None = None
    empire_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    charter_expansions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_civilization_state(resume_dir)
        resumed = True
        resume_civilization_id = str(state.get("civilization_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        empire_digests = [str(d) for d in (state.get("empire_digests") or [])]
        empire_states = [
            dict(ist)
            for ist in (state.get("empire_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_civilization_charter(
                [e for e in state["charter"] if isinstance(e, Mapping)]
            )
        if isinstance(state.get("admissions"), list):
            admissions = [
                dict(a) for a in state["admissions"] if isinstance(a, Mapping)
            ]
        if isinstance(state.get("charter_expansions"), list):
            charter_expansions = [
                dict(e) for e in state["charter_expansions"] if isinstance(e, Mapping)
            ]
        if (
            state.get("max_active_empires") is not None
            and max_active_empires is None
        ):
            resumed_max_active = int(state["max_active_empires"])
        # Resume may also merge a caller-supplied charter growth tail.
        if charter:
            active_charter = merge_civilization_charter(active_charter, charter)
    else:
        active_charter = normalize_civilization_charter(charter)

    active_max = (
        max_active_empires
        if max_active_empires is not None
        else resumed_max_active
    )

    if not active_charter and not empire_states:
        raise CivilizationRefused(
            "civilization_empty",
            "empire charter has no admitable realm slots",
        )

    lid = (
        civilization_id
        or resume_civilization_id
        or f"empire-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        civilization_dir = Path(out_root)
        if (civilization_dir / "civilization.json").is_file():
            civilization_dir = civilization_dir / stamp
    else:
        civilization_dir = ARTIFACTS_ROOT / stamp
    civilization_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    # Single-letter path segments keep Windows MAX_PATH headroom under deep planes.
    lg_root = Path(league_out_root) if league_out_root else (civilization_dir / "e")
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root = civilization_dir / "x"
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        civilization_dir=civilization_dir,
        charter=active_charter,
        empire_states=empire_states,
        max_active_empires=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not empire_states and not pending_charter_slots(
        active_charter, empire_states
    ):
        raise CivilizationRefused("civilization_empty", "no realm slots admitted")
    if not empire_states and pending_charter_slots(
        active_charter, empire_states
    ):
        raise CivilizationRefused(
            "civilization_empty",
            "no realm slots admitted under max_active_empires policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in empire_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    civilization_met = False
    coverage_end: dict[str, Any] = civilization_terminal_coverage(
        empire_states=empire_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            civilization_dir=civilization_dir,
            charter=active_charter,
            empire_states=empire_states,
            max_active_empires=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = civilization_terminal_coverage(
            empire_states=empire_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            empire_states=empire_states,
            charter=active_charter,
            civilization_goal=civilization_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "civilization_met"
            civilization_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_empire(
            empire_states, roi_history, round_index=round_index
        )
        if selected is None:
            if not pending_charter_slots(active_charter, empire_states):
                stop_reason = "civilization_met"
                civilization_met = True
            else:
                stop_reason = "civilization_idle"
            coverage_end = coverage_before
            break

        open_count = sum(
            1 for ist in empire_states if not ist.get("empire_met")
        )
        allocated = allocate_empire_budget(
            remaining_budget=remaining_budget,
            open_empire_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        empire_id = str(selected["empire_id"])
        resume_empire_dir = selected.get("last_empire_dir")
        empire_resume: Path | None = None
        if (
            resume_empire_dir
            and (Path(str(resume_empire_dir)) / "empire_state.json").is_file()
            and not selected.get("empire_met")
        ):
            empire_resume = Path(str(resume_empire_dir))

        # Ultra-short stamp (civilization adds a plane; Windows MAX_PATH is tight).
        safe_id = "".join(c if c.isalnum() else "" for c in empire_id)[:3] or "i"
        out_dir = lg_root / f"{round_index:x}{safe_id}"
        inst_out = inst_flat_root / f"{round_index:x}{safe_id}"
        empire_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "empire_goal": str(
                selected.get("empire_goal") or "all_realms_met"
            ),
            "empire_id": empire_id,
            "out_root": out_dir,
            "league_out_root": inst_out,
        }
        if selected.get("max_active_realms") is not None:
            empire_kwargs["max_active_realms"] = int(
                selected["max_active_realms"]
            )
        if empire_resume is not None:
            empire_kwargs["resume_dir"] = empire_resume
            # charter already on resume state
            empire_kwargs.pop("charter", None)
        if program_runner is not None:
            empire_kwargs["program_runner"] = program_runner
        if campaign_runner is not None:
            empire_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            empire_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            empire_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            empire_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            empire_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            empire_kwargs["refresh_promotions"] = refresh_promotions

        try:
            empire_result = runner(**empire_kwargs)
        except ue.EmpireRefused as exc:
            if local_index == 0 and not resumed:
                raise CivilizationRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"empire_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise CivilizationRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise CivilizationRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(empire_result.get("total_dispatched") or 0)
        dispatched_ok = int(empire_result.get("total_dispatched_ok") or 0)
        prior_inst_dispatched = int(selected.get("total_dispatched") or 0)
        prior_inst_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_inst_dispatched)
        delta_ok = max(0, dispatched_ok - prior_inst_ok)
        if empire_resume is None and prior_inst_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        nested_empire_dir = empire_result.get("empire_dir")
        nested_realm_states: list[dict[str, Any]] = []
        nested_receipt_path = (
            Path(str(nested_empire_dir)) / "empire.json"
            if nested_empire_dir
            else None
        )
        if nested_receipt_path is not None and nested_receipt_path.is_file():
            receipt = json.loads(nested_receipt_path.read_text(encoding="utf-8"))
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(
                receipt.get("realm_states") or receipt.get("domains") or []
            ):
                if isinstance(ist, Mapping):
                    nested_realm_states.append(dict(ist))
        if after_portfolio is None and isinstance(
            empire_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(empire_result["federated_portfolio"])  # type: ignore[index]
        if not nested_realm_states:
            for ist in list(empire_result.get("realm_states") or []):
                if isinstance(ist, Mapping):
                    nested_realm_states.append(dict(ist))

        for i, lst in enumerate(empire_states):
            if str(lst.get("empire_id")) != empire_id:
                continue
            updated = dict(lst)
            updated["last_empire_dir"] = empire_result.get("empire_dir")
            updated["last_empire_digest"] = empire_result.get("empire_digest")
            updated["empire_met"] = bool(empire_result.get("empire_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_realm_states:
                updated["realm_states"] = nested_realm_states
            empire_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in empire_states]
        )
        coverage_after = civilization_terminal_coverage(
            empire_states=empire_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_empire_roi(
            round_index=round_index,
            empire_id=empire_id,
            empire_result=empire_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(empire_result.get("empire_digest") or "")
        if idigest:
            empire_digests.append(idigest)

        rec = _empire_round_record(
            round_index=round_index,
            empire_id=empire_id,
            empire_result=empire_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            civilization_dir=civilization_dir,
            charter=active_charter,
            empire_states=empire_states,
            max_active_empires=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = civilization_terminal_coverage(
                empire_states=empire_states,
                federated_portfolio=federated_portfolio,
            )

        write_civilization_state(
            civilization_dir,
            _state_payload(
                civilization_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                empire_states=empire_states,
                empire_digests=empire_digests,
                charter=active_charter,
                stop_reason=None,
                civilization_goal=civilization_goal,
                max_active_empires=active_max,
                admissions=admissions,
                charter_expansions=charter_expansions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not empire_result.get("empire_met")
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
                    "empire_states": empire_states,
                    "last_empire_id": empire_id,
                    "federated_portfolio": federated_portfolio,
                    "civilization_dir": str(civilization_dir),
                    "pending_empire_ids": [
                        str(s.get("empire_id") or "")
                        for s in pending_charter_slots(
                            active_charter, empire_states
                        )
                    ],
                    "admissions": admissions,
                    "charter_expansions": charter_expansions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        # Grow constitution before declaring civilization_met when expand remains.
        if (
            charter_expand is not None
            and not pending_charter_slots(active_charter, empire_states)
            and empires_all_met(empire_states)
        ):
            growth = charter_expand(
                active_charter=active_charter,
                empire_states=empire_states,
                round_index=round_index,
                roi_history=roi_history,
            )
            if growth.get("expanded") and growth.get("charter"):
                active_charter = normalize_civilization_charter(
                    [e for e in (growth.get("charter") or []) if isinstance(e, Mapping)]
                )
                charter_expansions.append(
                    {
                        "round_index": round_index,
                        "added": list(growth.get("added") or []),
                        "detail": growth.get("detail"),
                    }
                )
                post_growth = admit_pending_slots(
                    civilization_dir=civilization_dir,
                    charter=active_charter,
                    empire_states=empire_states,
                    max_active_empires=active_max,
                    round_index=round_index + 1,
                )
                if post_growth:
                    admissions.extend(post_growth)
                write_civilization_state(
                    civilization_dir,
                    _state_payload(
                        civilization_id=lid,
                        round_count=round_index + 1,
                        total_dispatched=total_dispatched,
                        total_dispatched_ok=total_dispatched_ok,
                        federated_portfolio=federated_portfolio,
                        roi_history=roi_history,
                        empire_states=empire_states,
                        empire_digests=empire_digests,
                        charter=active_charter,
                        stop_reason=None,
                        civilization_goal=civilization_goal,
                        max_active_empires=active_max,
                        admissions=admissions,
                        charter_expansions=charter_expansions,
                    ),
                )
                # Continue the outer loop with the grown charter.
                continue

        if constitution_satisfied(
            empire_states=empire_states,
            charter=active_charter,
            civilization_goal=civilization_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "civilization_met"
            civilization_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            empire_states=empire_states,
            charter=active_charter,
            civilization_goal=civilization_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "civilization_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        civilization_dir=civilization_dir,
        charter=active_charter,
        empire_states=empire_states,
        max_active_empires=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in empire_states]
    )
    coverage_end = civilization_terminal_coverage(
        empire_states=empire_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        empire_states=empire_states,
        charter=active_charter,
        civilization_goal=civilization_goal,
        federated_portfolio=federated_portfolio,
    ):
        civilization_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    empires_met_count = sum(
        1 for ist in empire_states if ist.get("empire_met")
    )
    pending_remaining = [
        str(s.get("empire_id") or "")
        for s in pending_charter_slots(active_charter, empire_states)
    ]

    if civilization_met and stop_reason in {"civilization_met", "max_rounds"}:
        verdict = "civilization_met"
        ok = True
        stop_reason = "civilization_met"
    elif stop_reason == "rank_only":
        verdict = "civilization_ranked"
        ok = True
    elif stop_reason == "civilization_idle":
        verdict = "civilization_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "civilization_budgeted"
        ok = True
    elif stop_reason.startswith("domain_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "empire_refused_mid"
        ok = False
    else:
        verdict = "civilization_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "civilization_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_empires": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "civilization_goal": civilization_goal,
        "civilization_met": civilization_met,
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
        "empires": institutions,
        "empire_digests": [
            i.get("empire_digest")
            for i in institutions
            if i.get("empire_digest")
        ],
        "empire_states": empire_states,
        "empires_admitted": len(empire_states),
        "empires_met_count": empires_met_count,
        "admissions": admissions,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "charter": active_charter,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": [
            str(cid)
            for exp in charter_expansions
            for cid in list(exp.get("added") or [])
        ],
        "roi_history": roi_history,
        "roi_summary": roi_summary,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    receipt["empire_digests"] = [
        str(i.get("empire_digest") or "") for i in institutions
    ]
    receipt["civilization_digest"] = _sha256_json(_civilization_digest_payload(receipt))
    atomic_write_json(civilization_dir / "civilization.json", receipt)
    atomic_write_json(
        civilization_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "civilization_id": receipt["civilization_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "civilization_met": receipt["civilization_met"],
            "empires_admitted": receipt["empires_admitted"],
            "empires_met_count": receipt["empires_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "charter_expansion_count": receipt["charter_expansion_count"],
            "max_active_empires": receipt["max_active_empires"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "civilization_digest": receipt["civilization_digest"],
            "resumed": resumed,
        },
    )

    write_civilization_state(
        civilization_dir,
        _state_payload(
            civilization_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            empire_states=empire_states,
            empire_digests=receipt["empire_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            civilization_goal=civilization_goal,
            max_active_empires=active_max,
            admissions=admissions,
            charter_expansions=charter_expansions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "civilization_dir": str(civilization_dir),
        "civilization_digest": receipt["civilization_digest"],
        "civilization_id": lid,
        "round_count": len(institutions),
        "empire_digests": list(receipt["empire_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "civilization_met": civilization_met,
        "empires_admitted": len(empire_states),
        "empires_met_count": empires_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_empires": active_max,
        "admissions": admissions,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": list(receipt["charter_expanded_ids"]),
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "empire_states": empire_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "empires": institutions,
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
    return ue._program_slot(
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
    """Build a hermetic nested institution slot."""
    return ue._inst_slot(
        institution_id,
        priority=priority,
        programs=programs,
        max_rounds=max_rounds,
        institution_goal=institution_goal,
        max_active_programs=max_active_programs,
    )


def _commonwealth_slot(
    commonwealth_id: str,
    *,
    priority: int = 0,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    commonwealth_goal: str = "all_confederations_met",
    max_active_confederations: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic commonwealth slot for a domain charter."""
    return ue._commonwealth_slot(
        commonwealth_id,
        priority=priority,
        institutions=list(institutions or []),
        max_rounds=max_rounds,
        commonwealth_goal=commonwealth_goal,
        max_active_confederations=max_active_confederations,
    )


def _domain_slot(
    domain_id: str,
    *,
    priority: int = 0,
    commonwealths: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    domain_goal: str = "all_commonwealths_met",
    max_active_commonwealths: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic domain slot for a realm charter."""
    return ue._domain_slot(
        domain_id,
        priority=priority,
        commonwealths=commonwealths,
        institutions=institutions,
        max_rounds=max_rounds,
        domain_goal=domain_goal,
        max_active_commonwealths=max_active_commonwealths,
    )


def _realm_slot(
    realm_id: str,
    *,
    priority: int = 0,
    domains: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    realm_goal: str = "all_domains_met",
    max_active_domains: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic realm slot for an empire charter."""
    return ue._realm_slot(
        realm_id,
        priority=priority,
        domains=domains,
        institutions=institutions,
        max_rounds=max_rounds,
        realm_goal=realm_goal,
        max_active_domains=max_active_domains,
    )


def _empire_slot(
    empire_id: str,
    *,
    priority: int = 0,
    realms: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    empire_goal: str = "all_realms_met",
    max_active_realms: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic civilization charter empire slot.

    Prefer ``realms=`` (nested realm slots). ``institutions=`` wraps a single
    auto realm when only lower work is supplied.
    """
    nested: list[dict[str, Any]]
    if realms is not None:
        nested = list(realms)
    elif institutions:
        nested = [
            _realm_slot(
                f"{empire_id[:1]}r",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "empire_id": empire_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "empire_goal": empire_goal,
        "max_active_realms": max_active_realms,
    }


def _proof_scratch() -> Path:
    """Short temp root so deep realm→…→wave paths stay under Windows MAX_PATH."""
    import os

    if os.name == "nt":
        root = Path("C:/t")
        try:
            root.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix="d", dir=str(root)))
        except OSError:
            pass
    return Path(tempfile.mkdtemp(prefix="d"))


def builtin_upstream_civilization_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-empire empire plane (no network)."""
    scratch = _proof_scratch()
    try:
        campaign = _proof_campaign_runner(scratch)

        # Two realms; ultra-short ids for Windows nested artifact paths.
        charter = [
            _empire_slot(
                "a",
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
            _empire_slot(
                "b",
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

        confed = run_civilization(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            civilization_goal="all_empires_met",
            out_root=scratch / "m",
        )
        multi_empire_ok = (
            confed["ok"]
            and confed["civilization_met"] is True
            and confed["stop_reason"] == "civilization_met"
            and confed["empires_admitted"] == 2
            and confed["empires_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        scheduled_ids = {
            i.get("empire_id") for i in (confed.get("empires") or confed.get("realms") or [])
        }
        multi_empire_scheduled = multi_empire_ok and scheduled_ids >= {"a", "b"}

        verified = verify_civilization_receipt(Path(confed["civilization_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed[
            "round_count"
        ]

        # Tamper detection.
        confed_path = Path(confed["civilization_dir"]) / "civilization.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["civilization_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_civilization_receipt(Path(confed["civilization_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "civilization_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across leagues.
        campaign2 = _proof_campaign_runner(scratch / "b")
        budgeted = run_civilization(
            charter=[
                _empire_slot(
                    "b1",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "i1",
                            programs=[
                                _program_slot("p1", initial=[("d1", "1.0.0", "d1-1")])
                            ],
                        )
                    ],
                ),
                _empire_slot(
                    "b2",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "i2",
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
            civilization_goal="none",
            out_root=scratch / "g",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit via custom empire_runner.
        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            nested_charter = ue.normalize_empire_charter(kwargs.get("charter"))
            entries: list[dict[str, Any]] = []
            realm_states: list[dict[str, Any]] = []
            for rslot in nested_charter:
                realm_entries: list[dict[str, Any]] = []
                domain_states: list[dict[str, Any]] = []
                domain_slots = list(rslot.get("charter") or []) + list(
                    rslot.get("domains") or []
                )
                if not domain_slots:
                    domain_slots = [rslot]
                for dslot in domain_slots:
                    if not isinstance(dslot, Mapping):
                        continue
                    domain_entries: list[dict[str, Any]] = []
                    commonwealth_states: list[dict[str, Any]] = []
                    cw_slots = list(dslot.get("charter") or []) + list(
                        dslot.get("commonwealths") or []
                    )
                    if not cw_slots and (
                        dslot.get("institutions") or dslot.get("programs")
                    ):
                        cw_slots = [dslot]
                    for cslot in cw_slots:
                        if not isinstance(cslot, Mapping):
                            continue
                        confed_entries: list[dict[str, Any]] = []
                        confederation_states: list[dict[str, Any]] = []
                        conf_slots = list(cslot.get("charter") or []) + list(
                            cslot.get("confederations") or []
                        )
                        if not conf_slots:
                            conf_slots = [cslot]
                        for conf_slot in conf_slots:
                            if not isinstance(conf_slot, Mapping):
                                continue
                            league_states: list[dict[str, Any]] = []
                            conf_entries: list[dict[str, Any]] = []
                            league_slots = list(conf_slot.get("charter") or []) + list(
                                conf_slot.get("leagues") or []
                            )
                            if not league_slots:
                                league_slots = [conf_slot]
                            for lslot in league_slots:
                                if not isinstance(lslot, Mapping):
                                    continue
                                league_entries: list[dict[str, Any]] = []
                                institution_states: list[dict[str, Any]] = []
                                inst_slots = list(lslot.get("charter") or []) + list(
                                    lslot.get("institutions") or []
                                )
                                if not inst_slots:
                                    inst_slots = [lslot]
                                for islot in inst_slots:
                                    if not isinstance(islot, Mapping):
                                        continue
                                    inst_entries: list[dict[str, Any]] = []
                                    prog_slots = list(islot.get("charter") or []) + list(
                                        islot.get("programs") or []
                                    )
                                    for pslot in prog_slots:
                                        if not isinstance(pslot, Mapping):
                                            continue
                                        for tgt in list(
                                            pslot.get("initial_targets") or []
                                        ) + list(pslot.get("surface_charter") or []):
                                            if not isinstance(tgt, Mapping):
                                                continue
                                            for d in list(tgt.get("defects") or []):
                                                if not isinstance(d, Mapping):
                                                    continue
                                                e = {
                                                    "name": tgt.get("name"),
                                                    "version": tgt.get("version"),
                                                    "defect_id": d.get("id"),
                                                    "outcome": "impact_merged",
                                                    "impact_digest": "c" * 64,
                                                    "ok": True,
                                                }
                                                entries.append(e)
                                                inst_entries.append(e)
                                                league_entries.append(e)
                                                conf_entries.append(e)
                                                confed_entries.append(e)
                                                domain_entries.append(e)
                                                realm_entries.append(e)
                                    institution_states.append(
                                        {
                                            "institution_id": islot.get("institution_id")
                                            or islot.get("id")
                                            or "i",
                                            "institution_met": True,
                                            "charter": list(islot.get("charter") or []),
                                            "portfolio": uf._proof_portfolio(inst_entries),
                                            "program_states": [],
                                        }
                                    )
                                league_states.append(
                                    {
                                        "league_id": lslot.get("league_id") or "l",
                                        "league_met": True,
                                        "charter": list(lslot.get("charter") or []),
                                        "portfolio": uf._proof_portfolio(league_entries),
                                        "institution_states": institution_states,
                                    }
                                )
                            confederation_states.append(
                                {
                                    "confederation_id": conf_slot.get("confederation_id")
                                    or "cf",
                                    "confederation_met": True,
                                    "charter": list(conf_slot.get("charter") or []),
                                    "portfolio": uf._proof_portfolio(conf_entries),
                                    "league_states": league_states,
                                }
                            )
                        commonwealth_states.append(
                            {
                                "commonwealth_id": cslot.get("commonwealth_id") or "cw",
                                "commonwealth_met": True,
                                "charter": list(cslot.get("charter") or []),
                                "portfolio": uf._proof_portfolio(confed_entries),
                                "confederation_states": confederation_states,
                            }
                        )
                    domain_states.append(
                        {
                            "domain_id": dslot.get("domain_id") or "d",
                            "domain_met": True,
                            "charter": list(dslot.get("charter") or []),
                            "portfolio": uf._proof_portfolio(domain_entries),
                            "commonwealth_states": commonwealth_states,
                        }
                    )
                realm_states.append(
                    {
                        "realm_id": rslot.get("realm_id"),
                        "realm_met": True,
                        "charter": list(rslot.get("charter") or []),
                        "portfolio": uf._proof_portfolio(realm_entries),
                        "domain_states": domain_states,
                    }
                )
            portfolio = uf._proof_portfolio(entries)
            digest = _sha256_json({"premet": True, "entries": len(entries)})
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "empire_met",
                "stop_reason": "empire_met",
                "empire_id": kwargs.get("empire_id"),
                "empire_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "realms_admitted": len(nested_charter),
                "realms_met_count": len(nested_charter),
                "empire_digest": digest,
                "federated_portfolio": portfolio,
                "realm_states": realm_states,
                "coverage_end": {
                    "required": len(entries),
                    "covered": len(entries),
                    "met": True,
                    "coverage_ratio": 1.0,
                },
            }
            atomic_write_json(out / "empire.json", receipt)
            atomic_write_json(
                out / "empire_state.json",
                {
                    "empire_id": kwargs.get("empire_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "realm_states": realm_states,
                    "stop_reason": "empire_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "empire_met",
                "stop_reason": "empire_met",
                "empire_dir": str(out),
                "empire_digest": digest,
                "empire_id": kwargs.get("empire_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "empire_met": True,
                "realms_admitted": len(nested_charter),
                "realms_met_count": len(nested_charter),
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "realm_states": realm_states,
                "used_skill_route_discovery": False,
            }

        pre_met = run_civilization(
            charter=[
                _empire_slot(
                    "om",
                    institutions=[
                        _inst_slot(
                            "oi",
                            programs=[
                                _program_slot(
                                    "op",
                                    initial=[("om", "9.0.0", "omega-merged")],
                                )
                            ],
                        )
                    ],
                )
            ],
            max_rounds=3,
            dispatch=True,
            empire_runner=_premet_runner,
            civilization_goal="all_empires_met",
            out_root=scratch / "p",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["civilization_met"] is True
            and pre_met["stop_reason"] == "civilization_met"
            and pre_met["empires_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only domain.
        ranked = run_civilization(
            charter=[
                _empire_slot(
                    "ra",
                    institutions=[
                        _inst_slot(
                            "ri",
                            programs=[
                                _program_slot("ra", initial=[("r1", "1.0.0", "r1-1")])
                            ],
                        )
                    ],
                ),
                _empire_slot(
                    "rb",
                    institutions=[
                        _inst_slot(
                            "rj",
                            programs=[
                                _program_slot("rb", initial=[("r2", "1.0.0", "r2-1")])
                            ],
                        )
                    ],
                ),
            ],
            max_rounds=3,
            dispatch=False,
            civilization_goal="none",
            out_root=scratch / "k",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "civilization_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_civilization(
                charter=[],
                dispatch=False,
                civilization_goal="none",
                out_root=scratch / "z",
            )
        except CivilizationRefused as exc:
            empty_refused = exc.verdict in {
                "civilization_empty",
                "civilization_invalid",
            }

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_civilization(
            charter=[
                _empire_slot(
                    "c1",
                    institutions=[
                        _inst_slot(
                            "k1",
                            programs=[
                                _program_slot("p1", initial=[("c1", "1.0.0", "c1-1")])
                            ],
                        )
                    ],
                ),
                _empire_slot(
                    "c2",
                    institutions=[
                        _inst_slot(
                            "k2",
                            programs=[
                                _program_slot("p2", initial=[("c2", "1.0.0", "c2-1")])
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
            civilization_goal="none",
            stop_when=lambda ctx: (
                "custom_halt" if ctx["total_dispatched_ok"] >= 1 else None
            ),
            out_root=scratch / "s",
        )
        custom_ok = (
            custom["ok"]
            and custom["stop_reason"] == "custom_halt"
            and custom["total_dispatched_ok"] >= 1
        )

        # Durable resume: partial (budget=1), resume with more budget.
        campaign4 = _proof_campaign_runner(scratch / "ra")
        partial = run_civilization(
            charter=[
                _empire_slot(
                    "z1",
                    priority=2,
                    institutions=[
                        _inst_slot(
                            "y1",
                            programs=[
                                _program_slot(
                                    "q1", initial=[("zeta", "1.0.0", "zeta-1")]
                                )
                            ],
                        )
                    ],
                ),
                _empire_slot(
                    "z2",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "y2",
                            programs=[
                                _program_slot(
                                    "q2", initial=[("eta", "1.0.0", "eta-1")]
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
            civilization_goal="none",
            civilization_id="rcp",
            out_root=scratch / "a",
        )
        state_path = Path(partial["civilization_dir"]) / "civilization_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "rb")
        resumed = run_civilization(
            resume_dir=Path(partial["civilization_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            civilization_goal="none",
            out_root=scratch / "r",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["civilization_id"] == "rcp"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-league budget allocation evidence.
        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_empire"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_empire") or {}) >= 2
        )

        first_cw = (confed.get("empires") or confed.get("realms") or [{}])[0].get("empire_id")
        priority_ok = first_cw == "a"

        # Federation: inventories across both empires form a joint surface.
        fed_keys: set[tuple[str, str, str]] = set()
        for est in confed.get("empire_states") or []:
            if not isinstance(est, Mapping):
                continue
            for rst in list(est.get("realm_states") or []):
                if not isinstance(rst, Mapping):
                    continue
                domain_iter = list(rst.get("domain_states") or [])
                if not domain_iter:
                    domain_iter = [rst]
                for dst in domain_iter:
                    if not isinstance(dst, Mapping):
                        continue
                    for cws in list(dst.get("commonwealth_states") or []) + (
                        [dst] if dst.get("commonwealth_id") else []
                    ):
                        if not isinstance(cws, Mapping):
                            continue
                        for cfs in list(cws.get("confederation_states") or []) + list(
                            cws.get("league_states") or []
                        ):
                            if not isinstance(cfs, Mapping):
                                continue
                            for lst in list(cfs.get("league_states") or [cfs]):
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
                                            for n, v, d in up.inventory_defect_keys(
                                                Path(str(stew))
                                            ):
                                                fed_keys.add((n, v, d))
        # Also accept federated portfolio coverage as federation evidence.
        fed_portfolio = confed.get("coverage_end") or {}
        federation_ok = multi_empire_ok and (
            len(fed_keys) >= 3
            or float(fed_portfolio.get("coverage_ratio") or 0) == 1.0
            and int(fed_portfolio.get("required") or 0) >= 3
        )

        # Deferred admission: max_active=1 grows domain charter over time.
        campaign6 = _proof_campaign_runner(scratch / "dc")
        deferred = run_civilization(
            charter=[
                _empire_slot(
                    "da",
                    priority=3,
                    institutions=[
                        _inst_slot(
                            "u1",
                            programs=[
                                _program_slot(
                                    "v1", initial=[("da", "1.0.0", "da-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                ),
                _empire_slot(
                    "db",
                    priority=2,
                    institutions=[
                        _inst_slot(
                            "u2",
                            programs=[
                                _program_slot(
                                    "v2", initial=[("db", "1.0.0", "db-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                ),
                _empire_slot(
                    "dc",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "u3",
                            programs=[
                                _program_slot(
                                    "v3", initial=[("dc", "1.0.0", "dc-1")]
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
            max_active_empires=1,
            dispatch=True,
            campaign_runner=campaign6,
            civilization_goal="all_empires_met",
            out_root=scratch / "d",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("empire_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["civilization_met"] is True
            and deferred["empires_admitted"] == 3
            and deferred["empires_met_count"] == 3
            and deferred.get("max_active_empires") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        # Charter expansion: start with one domain; grow constitution mid-run.
        campaign7 = _proof_campaign_runner(scratch / "xg")
        expand_runner = make_civilization_charter_expand(
            [
                _empire_slot(
                    "xg",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "w2",
                            programs=[
                                _program_slot(
                                    "t2", initial=[("xg", "1.0.0", "xg-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                )
            ],
            max_slots_per_expand=1,
        )
        expanded = run_civilization(
            charter=[
                _empire_slot(
                    "xe",
                    priority=2,
                    institutions=[
                        _inst_slot(
                            "w1",
                            programs=[
                                _program_slot(
                                    "t1", initial=[("xe", "1.0.0", "xe-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                )
            ],
            max_rounds=6,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=6,
            max_active_empires=1,
            dispatch=True,
            campaign_runner=campaign7,
            charter_expand=expand_runner,
            civilization_goal="all_empires_met",
            out_root=scratch / "x",
        )
        expand_ok = (
            expanded["ok"]
            and expanded["civilization_met"] is True
            and expanded["empires_admitted"] == 2
            and expanded["empires_met_count"] == 2
            and int(expanded.get("charter_expansion_count") or 0) >= 1
            and "xg" in set(expanded.get("charter_expanded_ids") or [])
            and not (expanded.get("pending_remaining") or [])
        )

        # merge_civilization_charter unit evidence (ids de-dupe, additions append).
        merged = merge_civilization_charter(
            [_empire_slot("m1", institutions=[_inst_slot("mi", programs=[_program_slot("mp", initial=[("m", "1.0.0", "m-1")])])])],
            [
                _empire_slot("m1", institutions=[_inst_slot("mi2", programs=[_program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])])]),
                _empire_slot("m2", institutions=[_inst_slot("mj", programs=[_program_slot("mq", initial=[("n", "1.0.0", "n-1")])])]),
            ],
        )
        merge_ok = [s["empire_id"] for s in merged] == ["m1", "m2"]

        ok = all(
            [
                multi_empire_ok,
                multi_empire_scheduled,
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
                expand_ok,
                merge_ok,
            ]
        )
        return {
            "ok": ok,
            "civilization_met": multi_empire_ok,
            "multi_empire_progressed": multi_empire_scheduled,
            "federation_coverage": federation_ok,
            "priority_scheduling": priority_ok,
            "deferred_admission": deferred_ok,
            "charter_expand": expand_ok,
            "charter_merge": merge_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_detected,
            "budget_stops": budget_ok,
            "premet_short_circuits": premet_ok,
            "rank_only": rank_only_ok,
            "empty_refused": empty_refused,
            "custom_stop": custom_ok,
            "durable_resume": resume_ok,
            "roi_scored": roi_ok,
            "civilization_digest": confed.get("civilization_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "empires_admitted": confed.get("empires_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_empire_ok": multi_empire_ok,
                "multi_empire_scheduled": multi_empire_scheduled,
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
                "expand_ok": expand_ok,
                "merge_ok": merge_ok,
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
        help="verify a sealed realm directory",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.verify:
        result = verify_civilization_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_civilization_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
