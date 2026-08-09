"""Upstream empire plane: multi-realm durable stewardship empire.

The realm plane (``upstream_realm``) closes multi-domain unions *within one
realm*. It does not:

1. chain multiple independent realms under a durable empire constitution;
2. allocate a shared global dispatch budget across realms by ROI;
3. admit/retire realm slots from an empire charter over time
   (deferred admission under a concurrent-active cap);
4. grow the empire charter mid-run via ``charter_expand`` (constitution growth
   beyond the initial charter, not just deferred admission of a fixed set);
5. federate multi-realm portfolio coverage into one empire world-model;
6. persist empire state so a later process can resume the union;
7. seal a multi-realm empire chronicle linking realm digests.

The empire plane closes that outer multi-realm loop:

1. **admit** — materialize realm slots from a durable empire charter
   (each slot owns a nested domain charter). When ``max_active_realms``
   is set, only that many *unmet* realms are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (empire constitution growth over time);
2. **schedule** — pick the next open realm by priority and historical ROI;
3. **realm** — call the realm plane (injected ``realm_runner``;
   default ``run_realm``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-realm portfolios into one empire world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark realms met when their realm_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **expand** — optional ``charter_expand`` may append new realm slots when
   the active charter has no pending work and all admitted realms are met,
   so the empire constitution can grow after start (not only defer a fixed charter);
7. **persist** — write ``empire_state.json`` after every realm round so a
   later ``run_empire(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
8. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across realms
   - empire goal met (``all_realms_met``: every *admitted*
     realm is met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

9. **seal** — write an empire receipt under
   ``artifacts/upstream-empire/`` with sha256 digests of every
   realm, portfolio federation, admission history, ROI history, stop
   reason, and an empire chain digest; ``verify_empire_receipt``
   re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is empire-level direction
over the realm plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_realm as ur
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-empire"

TERMINAL_SUCCESS_OUTCOMES = ur.TERMINAL_SUCCESS_OUTCOMES


class EmpireRefused(Exception):
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


def normalize_empire_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a empire charter into deterministic realm slots.

    Each slot is::

        {
          "realm_id": str,
          "priority": int,
          "charter": [...league slots...],  # nested domain charter
          "max_active_domains": int | None,
          "max_rounds": int,
          "realm_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        realm_id = str(
            raw.get("realm_id") or raw.get("id") or ""
        ).strip()
        if not realm_id or realm_id in seen:
            continue
        seen.add(realm_id)

        nested = ur.normalize_realm_charter(
            raw.get("charter")
            or raw.get("domains")
            or raw.get("confederations")
            or raw.get("leagues")
            or raw.get("institutions")
            or raw.get("programs")
        )
        if not nested:
            continue

        max_active_domains = raw.get("max_active_domains")
        if max_active_domains is not None:
            max_active_domains = max(1, int(max_active_domains))

        out.append(
            {
                "realm_id": realm_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_domains": max_active_domains,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "realm_goal": str(
                    raw.get("realm_goal") or "all_domains_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_realm"),
            }
        )
    return out


def admit_realm_slot(
    *,
    empire_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with realm_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    realm_id = str(slot.get("realm_id") or "")
    if not realm_id:
        raise EmpireRefused("empire_invalid", "slot missing realm_id")

    realm_root = Path(empire_dir) / "realms" / realm_id
    realm_root.mkdir(parents=True, exist_ok=True)

    nested_charter = ur.normalize_realm_charter(slot.get("charter"))
    if not nested_charter:
        raise EmpireRefused(
            "empire_invalid",
            f"institution slot {realm_id!r} has empty nested charter",
        )

    return {
        "realm_id": realm_id,
        "realm_root": str(realm_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_domains": slot.get("max_active_domains"),
        "max_rounds": int(slot.get("max_rounds") or 6),
        "realm_goal": str(slot.get("realm_goal") or "all_domains_met"),
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
        "source": "empire_federation",
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


def empire_terminal_coverage(
    *,
    realm_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Realm coverage across domain→commonwealth→…→program."""
    required_keys: list[tuple[str, str, str]] = []
    for dom in realm_states:
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
        # Nested domain_states from a completed domain round.
        for cws in list(dom.get("domain_states") or []):
            if isinstance(cws, Mapping):
                required_keys.extend(_collect_from_domain_state(cws))
        # Nested domain charter (commonwealth → confederation → … → program).
        for cslot in list(dom.get("charter") or []) + list(dom.get("domains") or []):
            if not isinstance(cslot, Mapping):
                continue
            required_keys.extend(_collect_from_domain_state(cslot))

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


def realms_all_met(realm_states: Sequence[Mapping[str, Any]]) -> bool:
    if not realm_states:
        return False
    return all(bool(ist.get("realm_met")) for ist in realm_states)


def open_unmet_count(realm_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet realm_met."""
    return sum(1 for ist in realm_states if not ist.get("realm_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    realm_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then realm_id-asc."""
    known = {str(ist.get("realm_id") or "") for ist in realm_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("realm_id") or "")
        and str(slot.get("realm_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("realm_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    realm_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    empire_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if empire_goal == "none":
        return False
    if empire_goal == "terminal_coverage":
        cov = empire_terminal_coverage(
            realm_states=realm_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, realm_states
        )
    if empire_goal == "all_realms_met":
        if not realm_states:
            return False
        if pending_charter_slots(charter, realm_states):
            return False
        return realms_all_met(realm_states)
    return False


def merge_empire_charter(
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge additional realm slots into a empire charter.

    Existing ``realm_id`` values win (additions with the same id are
    ignored). Returns a fully re-normalized charter so nested confederation
    charters stay deterministic.
    """
    base = normalize_empire_charter(existing)
    if not additions:
        return base
    known = {str(s.get("realm_id") or "") for s in base}
    merged: list[Mapping[str, Any]] = list(base)
    for raw in additions:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get("realm_id") or raw.get("id") or "").strip()
        if not cid or cid in known:
            continue
        known.add(cid)
        merged.append(raw)
    return normalize_empire_charter(merged)


def make_empire_charter_expand(
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
    pending_growth = normalize_empire_charter(growth)
    applied_ids: set[str] = set(str(x) for x in (applied or []))
    state: dict[str, Any] = {
        "applied": applied_ids,
        "growth": pending_growth,
        "max_slots_per_expand": max(1, int(max_slots_per_expand)),
    }

    def _runner(
        *,
        active_charter: Sequence[Mapping[str, Any]],
        realm_states: Sequence[Mapping[str, Any]],
        round_index: int,
        roi_history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        remaining = [
            s
            for s in pending_growth
            if str(s.get("realm_id") or "") not in applied_ids
            and str(s.get("realm_id") or "")
            not in {str(x.get("realm_id") or "") for x in active_charter}
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
            applied_ids.add(str(s.get("realm_id") or ""))
        merged = merge_empire_charter(active_charter, take)
        state["applied"] = applied_ids
        return {
            "expanded": True,
            "added": [str(s.get("realm_id") or "") for s in take],
            "charter": merged,
            "detail": "charter_growth_applied",
            "round_index": round_index,
            "realms_met": realms_all_met(realm_states),
        }

    _runner.charter_state = state  # type: ignore[attr-defined]
    return _runner


def admit_pending_slots(
    *,
    empire_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    realm_states: list[dict[str, Any]],
    max_active_realms: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_realms`` caps *unmet* concurrent realms. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``realm_states``).
    """
    pending = pending_charter_slots(charter, realm_states)
    if not pending:
        return []

    open_n = open_unmet_count(realm_states)
    if max_active_realms is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_realms) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_realm_slot(empire_dir=empire_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        realm_states.append(
            {
                "realm_id": admission["realm_id"],
                "realm_root": admission["realm_root"],
                "charter": admission["charter"],
                "max_active_domains": admission.get("max_active_domains"),
                "max_rounds": admission["max_rounds"],
                "realm_goal": admission["realm_goal"],
                "priority": admission["priority"],
                "realm_met": False,
                "last_realm_dir": None,
                "last_realm_digest": None,
                "portfolio": None,
                "domain_states": [],
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


# ---------------------------------------------------------------------------
# ROI + scheduling


def score_realm_roi(
    *,
    round_index: int,
    realm_id: str,
    domain_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one institution round for league learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(domain_result.get("total_dispatched_ok") or 0)
    dispatched = int(domain_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "realm_id": realm_id,
        "stop_reason": domain_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "realm_met": bool(domain_result.get("realm_met")),
        "realm_digest": domain_result.get("realm_digest"),
        "domains_admitted": int(domain_result.get("domains_admitted") or 0),
        "domains_met_count": int(domain_result.get("domains_met_count") or 0),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_realm": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_realm: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get("realm_id") or "")
        bucket = by_realm.setdefault(
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
    for iid, bucket in by_realm.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_realm": by_realm,
    }


def select_next_realm(
    realm_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable realm_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in realm_states if not ist.get("realm_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_realm = summary.get("by_realm") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("realm_id") or "")
        hist = by_realm.get(iid) or {}
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


def allocate_realm_budget(
    *,
    remaining_budget: int | None,
    open_realm_count: int,
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
    open_n = max(1, int(open_realm_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_realm") or {}).get(
        str(selected.get("realm_id") or "")
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
    empire_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    realm_states: Sequence[Mapping[str, Any]],
    realm_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    empire_goal: str,
    max_active_realms: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
    charter_expansions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "empire_id": empire_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "realm_states": [dict(ist) for ist in realm_states],
        "realm_digests": list(realm_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "empire_goal": empire_goal,
        "max_active_realms": max_active_realms,
        "admissions": [dict(a) for a in (admissions or [])],
        "charter_expansions": [dict(e) for e in (charter_expansions or [])],
        "pending_realm_ids": [
            str(s.get("realm_id") or "")
            for s in pending_charter_slots(charter, realm_states)
        ],
    }


def write_empire_state(empire_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(empire_dir) / "empire_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_empire_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "empire_state.json")
    if not path.is_file():
        raise EmpireRefused(
            "empire_state_missing",
            f"no empire_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmpireRefused("empire_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise EmpireRefused("empire_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _realm_round_record(
    *,
    round_index: int,
    realm_id: str,
    domain_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "realm_id": realm_id,
        "ok": bool(domain_result.get("ok")),
        "verdict": domain_result.get("verdict"),
        "stop_reason": domain_result.get("stop_reason"),
        "realm_dir": domain_result.get("realm_dir"),
        "realm_digest": domain_result.get("realm_digest"),
        "domains_admitted": int(domain_result.get("domains_admitted") or 0),
        "domains_met_count": int(domain_result.get("domains_met_count") or 0),
        "total_dispatched": int(domain_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(domain_result.get("total_dispatched_ok") or 0),
        "realm_met": bool(domain_result.get("realm_met")),
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


def _empire_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "empire_id": receipt.get("empire_id"),
        "empire_goal": receipt.get("empire_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_realms": receipt.get("max_active_realms"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "realm_digests": list(receipt.get("realm_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "empire_met": receipt.get("empire_met"),
        "coverage_end": receipt.get("coverage_end"),
        "realms_met_count": receipt.get("realms_met_count"),
        "realms_admitted": receipt.get("realms_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "charter_expansion_count": receipt.get("charter_expansion_count"),
        "charter_expanded_ids": list(receipt.get("charter_expanded_ids") or []),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_empire_receipt(empire_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(empire_dir) / "empire.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_empire_digest_payload(receipt))
    recorded = str(receipt.get("empire_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("empire_digest")

    institutions = list(receipt.get("realms") or receipt.get("leagues") or [])
    listed = list(receipt.get("realm_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("realm_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("realm_digest"):
                mismatched.append(f"realm_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("realm_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "realm.json").is_file():
            nested = ur.verify_realm_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "empire_sealed" if ok else "empire_tampered",
        "empire_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run realm


def run_empire(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_realms: int | None = None,
    dispatch: bool = True,
    realm_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    charter_expand: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    empire_goal: str = "all_realms_met",
    refresh_promotions: Mapping[str, str] | None = None,
    empire_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_empire_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_realms:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    empire_goal:
        ``all_realms_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``empire_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise EmpireRefused("empire_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise EmpireRefused(
            "empire_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_realms is not None and int(max_active_realms) < 1:
        raise EmpireRefused(
            "empire_invalid", "max_active_realms must be >= 1 when set"
        )
    if empire_goal not in {"all_realms_met", "terminal_coverage", "none"}:
        raise EmpireRefused(
            "empire_invalid",
            f"unknown empire_goal: {empire_goal}",
        )

    runner = realm_runner or ur.run_realm

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    realm_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_empire_id: str | None = None
    realm_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    charter_expansions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_empire_state(resume_dir)
        resumed = True
        resume_empire_id = str(state.get("empire_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        realm_digests = [str(d) for d in (state.get("realm_digests") or [])]
        realm_states = [
            dict(ist)
            for ist in (state.get("realm_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_empire_charter(
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
            state.get("max_active_realms") is not None
            and max_active_realms is None
        ):
            resumed_max_active = int(state["max_active_realms"])
        # Resume may also merge a caller-supplied charter growth tail.
        if charter:
            active_charter = merge_empire_charter(active_charter, charter)
    else:
        active_charter = normalize_empire_charter(charter)

    active_max = (
        max_active_realms
        if max_active_realms is not None
        else resumed_max_active
    )

    if not active_charter and not realm_states:
        raise EmpireRefused(
            "empire_empty",
            "empire charter has no admitable realm slots",
        )

    lid = (
        empire_id
        or resume_empire_id
        or f"empire-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        empire_dir = Path(out_root)
        if (empire_dir / "empire.json").is_file():
            empire_dir = empire_dir / stamp
    else:
        empire_dir = ARTIFACTS_ROOT / stamp
    empire_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    # Single-letter path segments keep Windows MAX_PATH headroom under deep planes.
    lg_root = Path(league_out_root) if league_out_root else (empire_dir / "c")
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root = empire_dir / "p"
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        empire_dir=empire_dir,
        charter=active_charter,
        realm_states=realm_states,
        max_active_realms=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not realm_states and not pending_charter_slots(
        active_charter, realm_states
    ):
        raise EmpireRefused("empire_empty", "no realm slots admitted")
    if not realm_states and pending_charter_slots(
        active_charter, realm_states
    ):
        raise EmpireRefused(
            "empire_empty",
            "no realm slots admitted under max_active_realms policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in realm_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    empire_met = False
    coverage_end: dict[str, Any] = empire_terminal_coverage(
        realm_states=realm_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            empire_dir=empire_dir,
            charter=active_charter,
            realm_states=realm_states,
            max_active_realms=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = empire_terminal_coverage(
            realm_states=realm_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            realm_states=realm_states,
            charter=active_charter,
            empire_goal=empire_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "empire_met"
            empire_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_realm(
            realm_states, roi_history, round_index=round_index
        )
        if selected is None:
            if not pending_charter_slots(active_charter, realm_states):
                stop_reason = "empire_met"
                empire_met = True
            else:
                stop_reason = "empire_idle"
            coverage_end = coverage_before
            break

        open_count = sum(
            1 for ist in realm_states if not ist.get("realm_met")
        )
        allocated = allocate_realm_budget(
            remaining_budget=remaining_budget,
            open_realm_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        realm_id = str(selected["realm_id"])
        resume_realm_dir = selected.get("last_realm_dir")
        domain_resume: Path | None = None
        if (
            resume_realm_dir
            and (Path(str(resume_realm_dir)) / "realm_state.json").is_file()
            and not selected.get("realm_met")
        ):
            domain_resume = Path(str(resume_realm_dir))

        # Short stamp: r0-ia (avoid deep Windows paths under succession/epoch/wave).
        safe_id = "".join(c if c.isalnum() else "" for c in realm_id)[:6] or "i"
        out_dir = lg_root / f"r{round_index:x}-{safe_id}"
        inst_out = inst_flat_root / f"r{round_index:x}-{safe_id}"
        domain_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "realm_goal": str(
                selected.get("realm_goal") or "all_domains_met"
            ),
            "realm_id": realm_id,
            "out_root": out_dir,
            "league_out_root": inst_out,
        }
        if selected.get("max_active_domains") is not None:
            domain_kwargs["max_active_domains"] = int(
                selected["max_active_domains"]
            )
        if domain_resume is not None:
            domain_kwargs["resume_dir"] = domain_resume
            # charter already on resume state
            domain_kwargs.pop("charter", None)
        if program_runner is not None:
            domain_kwargs["program_runner"] = program_runner
        if campaign_runner is not None:
            domain_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            domain_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            domain_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            domain_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            domain_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            domain_kwargs["refresh_promotions"] = refresh_promotions

        try:
            domain_result = runner(**domain_kwargs)
        except ur.RealmRefused as exc:
            if local_index == 0 and not resumed:
                raise EmpireRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"realm_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise EmpireRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise EmpireRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(domain_result.get("total_dispatched") or 0)
        dispatched_ok = int(domain_result.get("total_dispatched_ok") or 0)
        prior_inst_dispatched = int(selected.get("total_dispatched") or 0)
        prior_inst_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_inst_dispatched)
        delta_ok = max(0, dispatched_ok - prior_inst_ok)
        if domain_resume is None and prior_inst_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        nested_realm_dir = domain_result.get("realm_dir")
        nested_domain_states: list[dict[str, Any]] = []
        nested_receipt_path = (
            Path(str(nested_realm_dir)) / "realm.json"
            if nested_realm_dir
            else None
        )
        if nested_receipt_path is not None and nested_receipt_path.is_file():
            receipt = json.loads(nested_receipt_path.read_text(encoding="utf-8"))
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(
                receipt.get("domain_states") or receipt.get("domains") or []
            ):
                if isinstance(ist, Mapping):
                    nested_domain_states.append(dict(ist))
        if after_portfolio is None and isinstance(
            domain_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(domain_result["federated_portfolio"])  # type: ignore[index]
        if not nested_domain_states:
            for ist in list(domain_result.get("domain_states") or []):
                if isinstance(ist, Mapping):
                    nested_domain_states.append(dict(ist))

        for i, lst in enumerate(realm_states):
            if str(lst.get("realm_id")) != realm_id:
                continue
            updated = dict(lst)
            updated["last_realm_dir"] = domain_result.get("realm_dir")
            updated["last_realm_digest"] = domain_result.get("realm_digest")
            updated["realm_met"] = bool(domain_result.get("realm_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_domain_states:
                updated["domain_states"] = nested_domain_states
            realm_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in realm_states]
        )
        coverage_after = empire_terminal_coverage(
            realm_states=realm_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_realm_roi(
            round_index=round_index,
            realm_id=realm_id,
            domain_result=domain_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(domain_result.get("realm_digest") or "")
        if idigest:
            realm_digests.append(idigest)

        rec = _realm_round_record(
            round_index=round_index,
            realm_id=realm_id,
            domain_result=domain_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            empire_dir=empire_dir,
            charter=active_charter,
            realm_states=realm_states,
            max_active_realms=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = empire_terminal_coverage(
                realm_states=realm_states,
                federated_portfolio=federated_portfolio,
            )

        write_empire_state(
            empire_dir,
            _state_payload(
                empire_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                realm_states=realm_states,
                realm_digests=realm_digests,
                charter=active_charter,
                stop_reason=None,
                empire_goal=empire_goal,
                max_active_realms=active_max,
                admissions=admissions,
                charter_expansions=charter_expansions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not domain_result.get("realm_met")
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
                    "realm_states": realm_states,
                    "last_realm_id": realm_id,
                    "federated_portfolio": federated_portfolio,
                    "empire_dir": str(empire_dir),
                    "pending_realm_ids": [
                        str(s.get("realm_id") or "")
                        for s in pending_charter_slots(
                            active_charter, realm_states
                        )
                    ],
                    "admissions": admissions,
                    "charter_expansions": charter_expansions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        # Grow constitution before declaring empire_met when expand remains.
        if (
            charter_expand is not None
            and not pending_charter_slots(active_charter, realm_states)
            and realms_all_met(realm_states)
        ):
            growth = charter_expand(
                active_charter=active_charter,
                realm_states=realm_states,
                round_index=round_index,
                roi_history=roi_history,
            )
            if growth.get("expanded") and growth.get("charter"):
                active_charter = normalize_empire_charter(
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
                    empire_dir=empire_dir,
                    charter=active_charter,
                    realm_states=realm_states,
                    max_active_realms=active_max,
                    round_index=round_index + 1,
                )
                if post_growth:
                    admissions.extend(post_growth)
                write_empire_state(
                    empire_dir,
                    _state_payload(
                        empire_id=lid,
                        round_count=round_index + 1,
                        total_dispatched=total_dispatched,
                        total_dispatched_ok=total_dispatched_ok,
                        federated_portfolio=federated_portfolio,
                        roi_history=roi_history,
                        realm_states=realm_states,
                        realm_digests=realm_digests,
                        charter=active_charter,
                        stop_reason=None,
                        empire_goal=empire_goal,
                        max_active_realms=active_max,
                        admissions=admissions,
                        charter_expansions=charter_expansions,
                    ),
                )
                # Continue the outer loop with the grown charter.
                continue

        if constitution_satisfied(
            realm_states=realm_states,
            charter=active_charter,
            empire_goal=empire_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "empire_met"
            empire_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            realm_states=realm_states,
            charter=active_charter,
            empire_goal=empire_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "empire_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        empire_dir=empire_dir,
        charter=active_charter,
        realm_states=realm_states,
        max_active_realms=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in realm_states]
    )
    coverage_end = empire_terminal_coverage(
        realm_states=realm_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        realm_states=realm_states,
        charter=active_charter,
        empire_goal=empire_goal,
        federated_portfolio=federated_portfolio,
    ):
        empire_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    realms_met_count = sum(
        1 for ist in realm_states if ist.get("realm_met")
    )
    pending_remaining = [
        str(s.get("realm_id") or "")
        for s in pending_charter_slots(active_charter, realm_states)
    ]

    if empire_met and stop_reason in {"empire_met", "max_rounds"}:
        verdict = "empire_met"
        ok = True
        stop_reason = "empire_met"
    elif stop_reason == "rank_only":
        verdict = "empire_ranked"
        ok = True
    elif stop_reason == "empire_idle":
        verdict = "empire_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "realm_budgeted"
        ok = True
    elif stop_reason.startswith("domain_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "realm_refused_mid"
        ok = False
    else:
        verdict = "realm_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "empire_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_realms": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "empire_goal": empire_goal,
        "empire_met": empire_met,
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
        "realms": institutions,
        "realm_digests": [
            i.get("realm_digest")
            for i in institutions
            if i.get("realm_digest")
        ],
        "realm_states": realm_states,
        "realms_admitted": len(realm_states),
        "realms_met_count": realms_met_count,
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
    receipt["realm_digests"] = [
        str(i.get("realm_digest") or "") for i in institutions
    ]
    receipt["empire_digest"] = _sha256_json(_empire_digest_payload(receipt))
    atomic_write_json(empire_dir / "empire.json", receipt)
    atomic_write_json(
        empire_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "empire_id": receipt["empire_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "empire_met": receipt["empire_met"],
            "realms_admitted": receipt["realms_admitted"],
            "realms_met_count": receipt["realms_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "charter_expansion_count": receipt["charter_expansion_count"],
            "max_active_realms": receipt["max_active_realms"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "empire_digest": receipt["empire_digest"],
            "resumed": resumed,
        },
    )

    write_empire_state(
        empire_dir,
        _state_payload(
            empire_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            realm_states=realm_states,
            realm_digests=receipt["realm_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            empire_goal=empire_goal,
            max_active_realms=active_max,
            admissions=admissions,
            charter_expansions=charter_expansions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "empire_dir": str(empire_dir),
        "empire_digest": receipt["empire_digest"],
        "empire_id": lid,
        "round_count": len(institutions),
        "realm_digests": list(receipt["realm_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "empire_met": empire_met,
        "realms_admitted": len(realm_states),
        "realms_met_count": realms_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_realms": active_max,
        "admissions": admissions,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": list(receipt["charter_expanded_ids"]),
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "realm_states": realm_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "realms": institutions,
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
    return ur._program_slot(
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
    return ur._inst_slot(
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
    return ur._commonwealth_slot(
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
    """Build a hermetic realm charter domain slot.

    Prefer ``commonwealths=`` (nested commonwealth slots). ``institutions=``
    wraps a single auto commonwealth when only lower work is supplied.
    """
    nested: list[dict[str, Any]]
    if commonwealths is not None:
        nested = list(commonwealths)
    elif institutions:
        nested = [
            _commonwealth_slot(
                f"{domain_id}c",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "domain_id": domain_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "domain_goal": domain_goal,
        "max_active_commonwealths": max_active_commonwealths,
    }


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
    """Build a hermetic empire charter realm slot.

    Prefer ``domains=`` (nested commonwealth slots). ``institutions=``
    wraps a single auto commonwealth when only lower work is supplied.
    """
    nested: list[dict[str, Any]]
    if domains is not None:
        nested = list(domains)
    elif institutions:
        nested = [
            _domain_slot(
                f"{realm_id}c",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "realm_id": realm_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "realm_goal": realm_goal,
        "max_active_domains": max_active_domains,
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


def builtin_upstream_empire_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-realm empire plane (no network)."""
    scratch = _proof_scratch()
    try:
        campaign = _proof_campaign_runner(scratch)

        # Two realms; ultra-short ids for Windows nested artifact paths.
        charter = [
            _realm_slot(
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
            _realm_slot(
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

        confed = run_empire(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            empire_goal="all_realms_met",
            out_root=scratch / "m",
        )
        multi_realm_ok = (
            confed["ok"]
            and confed["empire_met"] is True
            and confed["stop_reason"] == "empire_met"
            and confed["realms_admitted"] == 2
            and confed["realms_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        scheduled_ids = {
            i.get("realm_id") for i in (confed.get("realms") or [])
        }
        multi_realm_scheduled = multi_realm_ok and scheduled_ids >= {"a", "b"}

        verified = verify_empire_receipt(Path(confed["empire_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed[
            "round_count"
        ]

        # Tamper detection.
        confed_path = Path(confed["empire_dir"]) / "empire.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["empire_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_empire_receipt(Path(confed["empire_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "empire_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across leagues.
        campaign2 = _proof_campaign_runner(scratch / "b")
        budgeted = run_empire(
            charter=[
                _realm_slot(
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
                _realm_slot(
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
            empire_goal="none",
            out_root=scratch / "bg",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit via custom realm_runner.
        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            nested_charter = ur.normalize_realm_charter(kwargs.get("charter"))
            entries: list[dict[str, Any]] = []
            domain_states: list[dict[str, Any]] = []
            for dslot in nested_charter:
                domain_entries: list[dict[str, Any]] = []
                commonwealth_states: list[dict[str, Any]] = []
                for cslot in list(dslot.get("charter") or []) + list(
                    dslot.get("commonwealths") or []
                ):
                    if not isinstance(cslot, Mapping):
                        continue
                    confed_entries: list[dict[str, Any]] = []
                    confederation_states: list[dict[str, Any]] = []
                    for conf_slot in list(cslot.get("charter") or []) + list(
                        cslot.get("confederations") or []
                    ):
                        if not isinstance(conf_slot, Mapping):
                            continue
                        league_states: list[dict[str, Any]] = []
                        conf_entries: list[dict[str, Any]] = []
                        for lslot in list(conf_slot.get("charter") or []) + list(
                            conf_slot.get("leagues") or []
                        ):
                            if not isinstance(lslot, Mapping):
                                continue
                            league_entries: list[dict[str, Any]] = []
                            institution_states: list[dict[str, Any]] = []
                            for islot in list(lslot.get("charter") or []) + list(
                                lslot.get("institutions") or []
                            ):
                                if not isinstance(islot, Mapping):
                                    continue
                                inst_entries: list[dict[str, Any]] = []
                                for pslot in list(islot.get("charter") or []) + list(
                                    islot.get("programs") or []
                                ):
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
                        confederation_states.append(
                            {
                                "confederation_id": conf_slot.get("confederation_id"),
                                "confederation_met": True,
                                "charter": list(conf_slot.get("charter") or []),
                                "portfolio": uf._proof_portfolio(conf_entries),
                                "league_states": league_states,
                            }
                        )
                    commonwealth_states.append(
                        {
                            "commonwealth_id": cslot.get("commonwealth_id"),
                            "commonwealth_met": True,
                            "charter": list(cslot.get("charter") or []),
                            "portfolio": uf._proof_portfolio(confed_entries),
                            "confederation_states": confederation_states,
                        }
                    )
                domain_states.append(
                    {
                        "domain_id": dslot.get("domain_id"),
                        "domain_met": True,
                        "charter": list(dslot.get("charter") or []),
                        "portfolio": uf._proof_portfolio(domain_entries),
                        "commonwealth_states": commonwealth_states,
                    }
                )
            portfolio = uf._proof_portfolio(entries)
            digest = _sha256_json({"premet": True, "entries": len(entries)})
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "realm_met",
                "stop_reason": "realm_met",
                "realm_id": kwargs.get("realm_id"),
                "realm_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "domains_admitted": len(nested_charter),
                "domains_met_count": len(nested_charter),
                "realm_digest": digest,
                "federated_portfolio": portfolio,
                "domain_states": domain_states,
                "coverage_end": {
                    "required": len(entries),
                    "covered": len(entries),
                    "met": True,
                    "coverage_ratio": 1.0,
                },
            }
            atomic_write_json(out / "realm.json", receipt)
            atomic_write_json(
                out / "realm_state.json",
                {
                    "realm_id": kwargs.get("realm_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "domain_states": domain_states,
                    "stop_reason": "realm_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "realm_met",
                "stop_reason": "realm_met",
                "realm_dir": str(out),
                "realm_digest": digest,
                "realm_id": kwargs.get("realm_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "realm_met": True,
                "domains_admitted": len(nested_charter),
                "domains_met_count": len(nested_charter),
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "domain_states": domain_states,
                "used_skill_route_discovery": False,
            }

        pre_met = run_empire(
            charter=[
                _realm_slot(
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
            realm_runner=_premet_runner,
            empire_goal="all_realms_met",
            out_root=scratch / "pm",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["empire_met"] is True
            and pre_met["stop_reason"] == "empire_met"
            and pre_met["realms_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only domain.
        ranked = run_empire(
            charter=[
                _realm_slot(
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
                _realm_slot(
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
            empire_goal="none",
            out_root=scratch / "rk",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "empire_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_empire(
                charter=[],
                dispatch=False,
                empire_goal="none",
                out_root=scratch / "e",
            )
        except EmpireRefused as exc:
            empty_refused = exc.verdict in {
                "empire_empty",
                "empire_invalid",
            }

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_empire(
            charter=[
                _realm_slot(
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
                _realm_slot(
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
            empire_goal="none",
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
        partial = run_empire(
            charter=[
                _realm_slot(
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
                _realm_slot(
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
            empire_goal="none",
            empire_id="resume-empire-proof",
            out_root=scratch / "pa",
        )
        state_path = Path(partial["empire_dir"]) / "empire_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "rb")
        resumed = run_empire(
            resume_dir=Path(partial["empire_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            empire_goal="none",
            out_root=scratch / "rs",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["empire_id"] == "resume-empire-proof"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-league budget allocation evidence.
        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_realm"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_realm") or {}) >= 2
        )

        first_cw = (confed.get("realms") or [{}])[0].get("realm_id")
        priority_ok = first_cw == "a"

        # Federation: inventories across both realms form a joint surface.
        fed_keys: set[tuple[str, str, str]] = set()
        for rst in confed.get("realm_states") or []:
            if not isinstance(rst, Mapping):
                continue
            for dst in list(rst.get("domain_states") or []):
                if not isinstance(dst, Mapping):
                    continue
                for cws in list(dst.get("commonwealth_states") or []):
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
        federation_ok = multi_realm_ok and len(fed_keys) >= 3

        # Deferred admission: max_active=1 grows domain charter over time.
        campaign6 = _proof_campaign_runner(scratch / "dc")
        deferred = run_empire(
            charter=[
                _realm_slot(
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
                _realm_slot(
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
                _realm_slot(
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
            max_active_realms=1,
            dispatch=True,
            campaign_runner=campaign6,
            empire_goal="all_realms_met",
            out_root=scratch / "dl",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("realm_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["empire_met"] is True
            and deferred["realms_admitted"] == 3
            and deferred["realms_met_count"] == 3
            and deferred.get("max_active_realms") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        # Charter expansion: start with one domain; grow constitution mid-run.
        campaign7 = _proof_campaign_runner(scratch / "xg")
        expand_runner = make_empire_charter_expand(
            [
                _realm_slot(
                    "xg",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "xgi",
                            programs=[
                                _program_slot(
                                    "xgp", initial=[("xg", "1.0.0", "xg-1")]
                                )
                            ],
                        )
                    ],
                    max_rounds=3,
                )
            ],
            max_slots_per_expand=1,
        )
        expanded = run_empire(
            charter=[
                _realm_slot(
                    "xe",
                    priority=2,
                    institutions=[
                        _inst_slot(
                            "xei",
                            programs=[
                                _program_slot(
                                    "xep", initial=[("xe", "1.0.0", "xe-1")]
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
            max_active_realms=1,
            dispatch=True,
            campaign_runner=campaign7,
            charter_expand=expand_runner,
            empire_goal="all_realms_met",
            out_root=scratch / "xe",
        )
        expand_ok = (
            expanded["ok"]
            and expanded["empire_met"] is True
            and expanded["realms_admitted"] == 2
            and expanded["realms_met_count"] == 2
            and int(expanded.get("charter_expansion_count") or 0) >= 1
            and "xg" in set(expanded.get("charter_expanded_ids") or [])
            and not (expanded.get("pending_remaining") or [])
        )

        # merge_empire_charter unit evidence (ids de-dupe, additions append).
        merged = merge_empire_charter(
            [_realm_slot("m1", institutions=[_inst_slot("mi", programs=[_program_slot("mp", initial=[("m", "1.0.0", "m-1")])])])],
            [
                _realm_slot("m1", institutions=[_inst_slot("mi2", programs=[_program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])])]),
                _realm_slot("m2", institutions=[_inst_slot("mj", programs=[_program_slot("mq", initial=[("n", "1.0.0", "n-1")])])]),
            ],
        )
        merge_ok = [s["realm_id"] for s in merged] == ["m1", "m2"]

        ok = all(
            [
                multi_realm_ok,
                multi_realm_scheduled,
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
            "empire_met": multi_realm_ok,
            "multi_realm_progressed": multi_realm_scheduled,
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
            "empire_digest": confed.get("empire_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "realms_admitted": confed.get("realms_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_realm_ok": multi_realm_ok,
                "multi_realm_scheduled": multi_realm_scheduled,
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
        result = verify_empire_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_empire_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
