"""Upstream omniverse plane: multi-multiverse durable stewardship omniverse.

The multiverse plane (``upstream_multiverse``) closes multi-civilization unions *within one
multiverse*. It does not:

1. chain multiple independent multiverses under a durable omniverse constitution;
2. allocate a shared global dispatch budget across multiverses by ROI;
3. admit/retire multiverse slots from a omniverse charter over time
   (deferred admission under a concurrent-active cap);
4. grow the omniverse charter mid-run via ``charter_expand`` (constitution
   growth beyond the initial charter, not just deferred admission of a fixed set);
5. federate multi-multiverse portfolio coverage into one omniverse world-model;
6. persist omniverse state so a later process can resume the union;
7. seal a multi-multiverse omniverse chronicle linking multiverse digests.

The omniverse plane closes that outer multi-multiverse loop:

1. **admit** — materialize multiverse slots from a durable omniverse charter
   (each slot owns a nested cosmos charter). When ``max_active_multiverses``
   is set, only that many *unmet* multiverses are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (omniverse constitution growth over time);
2. **schedule** — pick the next open multiverse by priority and historical ROI;
3. **multiverse** — call the multiverse plane (injected ``multiverse_runner``;
   default ``run_multiverse``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-multiverse portfolios into one omniverse world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark multiverses met when their multiverse_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **expand** — optional ``charter_expand`` may append new multiverse slots when
   the active charter has no pending work and all admitted multiverses are met,
   so the omniverse constitution can grow after start (not only defer a fixed charter);
7. **persist** — write ``omniverse_state.json`` after every multiverse round so a
   later ``run_omniverse(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
8. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across multiverses
   - omniverse goal met (``all_multiverses_met``: every *admitted*
     multiverse is met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

9. **seal** — write a omniverse receipt under
   ``artifacts/upstream-omniverse/`` with sha256 digests of every
   multiverse, portfolio federation, admission history, ROI history, stop
   reason, and a omniverse chain digest; ``verify_omniverse_receipt``
   re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is omniverse-level direction
over the multiverse plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_multiverse as umv
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-omniverse"

TERMINAL_SUCCESS_OUTCOMES = umv.TERMINAL_SUCCESS_OUTCOMES


class OmniverseRefused(Exception):
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


def normalize_omniverse_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a omniverse charter into deterministic multiverse slots.

    Each slot is::

        {
          "multiverse_id": str,
          "priority": int,
          "charter": [...cosmos slots...],  # nested multiverse charter
          "max_active_cosmoses": int | None,
          "max_rounds": int,
          "multiverse_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        multiverse_id = str(
            raw.get("multiverse_id") or raw.get("id") or ""
        ).strip()
        if not multiverse_id or multiverse_id in seen:
            continue
        seen.add(multiverse_id)

        nested = umv.normalize_multiverse_charter(
            raw.get("charter")
            or raw.get("cosmoses")
            or raw.get("civilizations")
            or raw.get("empires")
            or raw.get("realms")
            or raw.get("domains")
            or raw.get("confederations")
            or raw.get("leagues")
            or raw.get("institutions")
            or raw.get("programs")
        )
        if not nested:
            continue

        max_active_cosmoses = raw.get("max_active_cosmoses")
        if max_active_cosmoses is None:
            max_active_cosmoses = raw.get("max_active_civilizations")
        if max_active_cosmoses is None:
            max_active_cosmoses = raw.get("max_active_realms")
        if max_active_cosmoses is not None:
            max_active_cosmoses = max(1, int(max_active_cosmoses))

        out.append(
            {
                "multiverse_id": multiverse_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_cosmoses": max_active_cosmoses,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "multiverse_goal": str(
                    raw.get("multiverse_goal") or "all_cosmoses_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_multiverse"),
            }
        )
    return out


def admit_multiverse_slot(
    *,
    omniverse_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with multiverse_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    multiverse_id = str(slot.get("multiverse_id") or "")
    if not multiverse_id:
        raise OmniverseRefused("omniverse_invalid", "slot missing multiverse_id")

    multiverse_root = Path(omniverse_dir) / "multiverses" / multiverse_id
    multiverse_root.mkdir(parents=True, exist_ok=True)

    nested_charter = umv.normalize_multiverse_charter(slot.get("charter"))
    if not nested_charter:
        raise OmniverseRefused(
            "omniverse_invalid",
            f"multiverse slot {multiverse_id!r} has empty nested charter",
        )

    max_active_cosmoses = slot.get("max_active_cosmoses")
    if max_active_cosmoses is None:
        max_active_cosmoses = slot.get("max_active_civilizations")
    if max_active_cosmoses is None:
        max_active_cosmoses = slot.get("max_active_realms")

    return {
        "multiverse_id": multiverse_id,
        "multiverse_root": str(multiverse_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_cosmoses": max_active_cosmoses,
        "max_rounds": int(slot.get("max_rounds") or 6),
        "multiverse_goal": str(slot.get("multiverse_goal") or "all_cosmoses_met"),
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
        "source": "omniverse_federation",
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


def omniverse_terminal_coverage(
    *,
    multiverse_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Coverage across multiverse→cosmos→civilization→…→program."""
    # Peel the multiverse layer and reuse the multiverse plane walker over
    # nested cosmos_states (or pre-run multiverse charters of cosmos slots).
    cosmos_states: list[dict[str, Any]] = []
    for mv in multiverse_states:
        if not isinstance(mv, Mapping):
            continue
        nested = list(mv.get("cosmos_states") or [])
        if nested:
            for cos in nested:
                if isinstance(cos, Mapping):
                    cosmos_states.append(dict(cos))
            continue
        # Pre-run: multiverse charter is a list of cosmos slots.
        for cslot in list(mv.get("charter") or []) + list(mv.get("cosmoses") or []):
            if isinstance(cslot, Mapping):
                cosmos_states.append(dict(cslot))
        # Fallback: older civilization_states mirrors (treat as cosmos-shaped).
        if not nested and not list(mv.get("charter") or []):
            for cos in list(mv.get("civilization_states") or []) + list(
                mv.get("empire_states") or []
            ):
                if isinstance(cos, Mapping):
                    cosmos_states.append(dict(cos))
        for raw in list(mv.get("inventory_keys") or []):
            # Hand inventory keys through as a synthetic cosmos state.
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                cosmos_states.append(
                    {
                        "inventory_keys": [
                            (str(raw[0]), str(raw[1]), str(raw[2]))
                        ]
                    }
                )
            elif isinstance(raw, Mapping):
                cosmos_states.append({"inventory_keys": [raw]})
    return umv.multiverse_terminal_coverage(
        cosmos_states=cosmos_states,
        federated_portfolio=federated_portfolio,
    )


def multiverses_all_met(multiverse_states: Sequence[Mapping[str, Any]]) -> bool:
    if not multiverse_states:
        return False
    return all(bool(ist.get("multiverse_met")) for ist in multiverse_states)


def open_unmet_count(multiverse_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet multiverse_met."""
    return sum(1 for ist in multiverse_states if not ist.get("multiverse_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    multiverse_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then multiverse_id-asc."""
    known = {str(ist.get("multiverse_id") or "") for ist in multiverse_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("multiverse_id") or "")
        and str(slot.get("multiverse_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("multiverse_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    multiverse_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    omniverse_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if omniverse_goal == "none":
        return False
    if omniverse_goal == "terminal_coverage":
        cov = omniverse_terminal_coverage(
            multiverse_states=multiverse_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, multiverse_states
        )
    if omniverse_goal == "all_multiverses_met":
        if not multiverse_states:
            return False
        if pending_charter_slots(charter, multiverse_states):
            return False
        return multiverses_all_met(multiverse_states)
    return False


def merge_omniverse_charter(
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge additional realm slots into a multiverse charter.

    Existing ``multiverse_id`` values win (additions with the same id are
    ignored). Returns a fully re-normalized charter so nested confederation
    charters stay deterministic.
    """
    base = normalize_omniverse_charter(existing)
    if not additions:
        return base
    known = {str(s.get("multiverse_id") or "") for s in base}
    merged: list[Mapping[str, Any]] = list(base)
    for raw in additions:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get("multiverse_id") or raw.get("id") or "").strip()
        if not cid or cid in known:
            continue
        known.add(cid)
        merged.append(raw)
    return normalize_omniverse_charter(merged)


def make_omniverse_charter_expand(
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
    pending_growth = normalize_omniverse_charter(growth)
    applied_ids: set[str] = set(str(x) for x in (applied or []))
    state: dict[str, Any] = {
        "applied": applied_ids,
        "growth": pending_growth,
        "max_slots_per_expand": max(1, int(max_slots_per_expand)),
    }

    def _runner(
        *,
        active_charter: Sequence[Mapping[str, Any]],
        multiverse_states: Sequence[Mapping[str, Any]],
        round_index: int,
        roi_history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        remaining = [
            s
            for s in pending_growth
            if str(s.get("multiverse_id") or "") not in applied_ids
            and str(s.get("multiverse_id") or "")
            not in {str(x.get("multiverse_id") or "") for x in active_charter}
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
            applied_ids.add(str(s.get("multiverse_id") or ""))
        merged = merge_omniverse_charter(active_charter, take)
        state["applied"] = applied_ids
        return {
            "expanded": True,
            "added": [str(s.get("multiverse_id") or "") for s in take],
            "charter": merged,
            "detail": "charter_growth_applied",
            "round_index": round_index,
            "realms_met": multiverses_all_met(multiverse_states),
        }

    _runner.charter_state = state  # type: ignore[attr-defined]
    return _runner


def admit_pending_slots(
    *,
    omniverse_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    multiverse_states: list[dict[str, Any]],
    max_active_multiverses: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_multiverses`` caps *unmet* concurrent realms. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``multiverse_states``).
    """
    pending = pending_charter_slots(charter, multiverse_states)
    if not pending:
        return []

    open_n = open_unmet_count(multiverse_states)
    if max_active_multiverses is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_multiverses) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_multiverse_slot(omniverse_dir=omniverse_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        multiverse_states.append(
            {
                "multiverse_id": admission["multiverse_id"],
                "multiverse_root": admission["multiverse_root"],
                "charter": admission["charter"],
                "max_active_cosmoses": admission.get("max_active_cosmoses"),
                "max_rounds": admission["max_rounds"],
                "multiverse_goal": admission["multiverse_goal"],
                "priority": admission["priority"],
                "multiverse_met": False,
                "last_multiverse_dir": None,
                "last_multiverse_digest": None,
                "portfolio": None,
                "cosmos_states": [],
                "civilization_states": [],
                "empire_states": [],
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


# ---------------------------------------------------------------------------
# ROI + scheduling


def score_multiverse_roi(
    *,
    round_index: int,
    multiverse_id: str,
    multiverse_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one institution round for league learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(multiverse_result.get("total_dispatched_ok") or 0)
    dispatched = int(multiverse_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "multiverse_id": multiverse_id,
        "stop_reason": multiverse_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "multiverse_met": bool(multiverse_result.get("multiverse_met")),
        "multiverse_digest": multiverse_result.get("multiverse_digest"),
        "empires_admitted": int(
            multiverse_result.get("empires_admitted")
            or multiverse_result.get("realms_admitted")
            or 0
        ),
        "empires_met_count": int(
            multiverse_result.get("empires_met_count")
            or multiverse_result.get("realms_met_count")
            or 0
        ),
    }


def _roi_summary(roi_history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_multiverse": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_multiverse: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get("multiverse_id") or "")
        bucket = by_multiverse.setdefault(
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
    for iid, bucket in by_multiverse.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_multiverse": by_multiverse,
    }


def select_next_multiverse(
    multiverse_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable multiverse_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in multiverse_states if not ist.get("multiverse_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_multiverse = summary.get("by_multiverse") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("multiverse_id") or "")
        hist = by_multiverse.get(iid) or {}
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


def allocate_multiverse_budget(
    *,
    remaining_budget: int | None,
    open_multiverse_count: int,
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
    open_n = max(1, int(open_multiverse_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_multiverse") or {}).get(
        str(selected.get("multiverse_id") or "")
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
    omniverse_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    multiverse_states: Sequence[Mapping[str, Any]],
    multiverse_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    omniverse_goal: str,
    max_active_multiverses: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
    charter_expansions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "omniverse_id": omniverse_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "multiverse_states": [dict(ist) for ist in multiverse_states],
        "multiverse_digests": list(multiverse_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "omniverse_goal": omniverse_goal,
        "max_active_multiverses": max_active_multiverses,
        "admissions": [dict(a) for a in (admissions or [])],
        "charter_expansions": [dict(e) for e in (charter_expansions or [])],
        "pending_multiverse_ids": [
            str(s.get("multiverse_id") or "")
            for s in pending_charter_slots(charter, multiverse_states)
        ],
    }


def write_omniverse_state(omniverse_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(omniverse_dir) / "omniverse_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_omniverse_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "omniverse_state.json")
    if not path.is_file():
        raise OmniverseRefused(
            "omniverse_state_missing",
            f"no omniverse_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OmniverseRefused("omniverse_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise OmniverseRefused("omniverse_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _multiverse_round_record(
    *,
    round_index: int,
    multiverse_id: str,
    multiverse_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "multiverse_id": multiverse_id,
        "ok": bool(multiverse_result.get("ok")),
        "verdict": multiverse_result.get("verdict"),
        "stop_reason": multiverse_result.get("stop_reason"),
        "multiverse_dir": multiverse_result.get("multiverse_dir"),
        "multiverse_digest": multiverse_result.get("multiverse_digest"),
        "empires_admitted": int(
            multiverse_result.get("empires_admitted")
            or multiverse_result.get("realms_admitted")
            or 0
        ),
        "empires_met_count": int(
            multiverse_result.get("empires_met_count")
            or multiverse_result.get("realms_met_count")
            or 0
        ),
        "total_dispatched": int(multiverse_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(multiverse_result.get("total_dispatched_ok") or 0),
        "multiverse_met": bool(multiverse_result.get("multiverse_met")),
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


def _omniverse_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "omniverse_id": receipt.get("omniverse_id"),
        "omniverse_goal": receipt.get("omniverse_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_multiverses": receipt.get("max_active_multiverses"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "multiverse_digests": list(receipt.get("multiverse_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "omniverse_met": receipt.get("omniverse_met"),
        "coverage_end": receipt.get("coverage_end"),
        "multiverses_met_count": receipt.get("multiverses_met_count"),
        "multiverses_admitted": receipt.get("multiverses_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "charter_expansion_count": receipt.get("charter_expansion_count"),
        "charter_expanded_ids": list(receipt.get("charter_expanded_ids") or []),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_omniverse_receipt(omniverse_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(omniverse_dir) / "omniverse.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_omniverse_digest_payload(receipt))
    recorded = str(receipt.get("omniverse_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("omniverse_digest")

    institutions = list(receipt.get("multiverses") or receipt.get("realms") or receipt.get("leagues") or [])
    listed = list(receipt.get("multiverse_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("multiverse_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("multiverse_digest"):
                mismatched.append(f"multiverse_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("multiverse_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "multiverse.json").is_file():
            nested = umv.verify_multiverse_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "omniverse_sealed" if ok else "omniverse_tampered",
        "omniverse_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run realm


def run_omniverse(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_multiverses: int | None = None,
    dispatch: bool = True,
    multiverse_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    charter_expand: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    omniverse_goal: str = "all_multiverses_met",
    refresh_promotions: Mapping[str, str] | None = None,
    omniverse_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_omniverse_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_multiverses:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    omniverse_goal:
        ``all_multiverses_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``omniverse_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise OmniverseRefused("omniverse_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise OmniverseRefused(
            "omniverse_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_multiverses is not None and int(max_active_multiverses) < 1:
        raise OmniverseRefused(
            "omniverse_invalid", "max_active_multiverses must be >= 1 when set"
        )
    if omniverse_goal not in {"all_multiverses_met", "terminal_coverage", "none"}:
        raise OmniverseRefused(
            "omniverse_invalid",
            f"unknown omniverse_goal: {omniverse_goal}",
        )

    runner = multiverse_runner or umv.run_multiverse

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    multiverse_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_omniverse_id: str | None = None
    multiverse_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    charter_expansions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_omniverse_state(resume_dir)
        resumed = True
        resume_omniverse_id = str(state.get("omniverse_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        multiverse_digests = [str(d) for d in (state.get("multiverse_digests") or [])]
        multiverse_states = [
            dict(ist)
            for ist in (state.get("multiverse_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_omniverse_charter(
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
            state.get("max_active_multiverses") is not None
            and max_active_multiverses is None
        ):
            resumed_max_active = int(state["max_active_multiverses"])
        # Resume may also merge a caller-supplied charter growth tail.
        if charter:
            active_charter = merge_omniverse_charter(active_charter, charter)
    else:
        active_charter = normalize_omniverse_charter(charter)

    active_max = (
        max_active_multiverses
        if max_active_multiverses is not None
        else resumed_max_active
    )

    if not active_charter and not multiverse_states:
        raise OmniverseRefused(
            "omniverse_empty",
            "multiverse charter has no admitable realm slots",
        )

    lid = (
        omniverse_id
        or resume_omniverse_id
        or f"multiverse-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        omniverse_dir = Path(out_root)
        if (omniverse_dir / "omniverse.json").is_file():
            omniverse_dir = omniverse_dir / stamp
    else:
        omniverse_dir = ARTIFACTS_ROOT / stamp
    omniverse_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    # Single-letter path segments keep Windows MAX_PATH headroom under deep planes.
    lg_root = Path(league_out_root) if league_out_root else (omniverse_dir / "e")
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root = omniverse_dir / "x"
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        omniverse_dir=omniverse_dir,
        charter=active_charter,
        multiverse_states=multiverse_states,
        max_active_multiverses=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not multiverse_states and not pending_charter_slots(
        active_charter, multiverse_states
    ):
        raise OmniverseRefused("omniverse_empty", "no realm slots admitted")
    if not multiverse_states and pending_charter_slots(
        active_charter, multiverse_states
    ):
        raise OmniverseRefused(
            "omniverse_empty",
            "no realm slots admitted under max_active_multiverses policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in multiverse_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    omniverse_met = False
    coverage_end: dict[str, Any] = omniverse_terminal_coverage(
        multiverse_states=multiverse_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            omniverse_dir=omniverse_dir,
            charter=active_charter,
            multiverse_states=multiverse_states,
            max_active_multiverses=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = omniverse_terminal_coverage(
            multiverse_states=multiverse_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            multiverse_states=multiverse_states,
            charter=active_charter,
            omniverse_goal=omniverse_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "omniverse_met"
            omniverse_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_multiverse(
            multiverse_states, roi_history, round_index=round_index
        )
        if selected is None:
            if not pending_charter_slots(active_charter, multiverse_states):
                stop_reason = "omniverse_met"
                omniverse_met = True
            else:
                stop_reason = "omniverse_idle"
            coverage_end = coverage_before
            break

        open_count = sum(
            1 for ist in multiverse_states if not ist.get("multiverse_met")
        )
        allocated = allocate_multiverse_budget(
            remaining_budget=remaining_budget,
            open_multiverse_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        multiverse_id = str(selected["multiverse_id"])
        resume_multiverse_dir = selected.get("last_multiverse_dir")
        multiverse_resume: Path | None = None
        if (
            resume_multiverse_dir
            and (Path(str(resume_multiverse_dir)) / "multiverse_state.json").is_file()
            and not selected.get("multiverse_met")
        ):
            multiverse_resume = Path(str(resume_multiverse_dir))

        # Ultra-short stamp (omniverse adds a plane; Windows MAX_PATH is tight).
        safe_id = "".join(c if c.isalnum() else "" for c in multiverse_id)[:3] or "i"
        out_dir = lg_root / f"{round_index:x}{safe_id}"
        inst_out = inst_flat_root / f"{round_index:x}{safe_id}"
        multiverse_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "multiverse_goal": str(
                selected.get("multiverse_goal") or "all_cosmoses_met"
            ),
            "multiverse_id": multiverse_id,
            "out_root": out_dir,
            "league_out_root": inst_out,
        }
        max_active_cosmoses = selected.get("max_active_cosmoses")
        if max_active_cosmoses is None:
            max_active_cosmoses = selected.get("max_active_civilizations")
        if max_active_cosmoses is None:
            max_active_cosmoses = selected.get("max_active_realms")
        if max_active_cosmoses is not None:
            multiverse_kwargs["max_active_cosmoses"] = int(
                max_active_cosmoses
            )
        if multiverse_resume is not None:
            multiverse_kwargs["resume_dir"] = multiverse_resume
            # charter already on resume state
            multiverse_kwargs.pop("charter", None)
        if program_runner is not None:
            multiverse_kwargs["program_runner"] = program_runner
        if campaign_runner is not None:
            multiverse_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            multiverse_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            multiverse_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            multiverse_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            multiverse_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            multiverse_kwargs["refresh_promotions"] = refresh_promotions

        try:
            multiverse_result = runner(**multiverse_kwargs)
        except umv.MultiverseRefused as exc:
            if local_index == 0 and not resumed:
                raise OmniverseRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"multiverse_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise OmniverseRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise OmniverseRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(multiverse_result.get("total_dispatched") or 0)
        dispatched_ok = int(multiverse_result.get("total_dispatched_ok") or 0)
        prior_inst_dispatched = int(selected.get("total_dispatched") or 0)
        prior_inst_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_inst_dispatched)
        delta_ok = max(0, dispatched_ok - prior_inst_ok)
        if multiverse_resume is None and prior_inst_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        nested_multiverse_dir = multiverse_result.get("multiverse_dir")
        nested_cosmos_states: list[dict[str, Any]] = []
        nested_receipt_path = (
            Path(str(nested_multiverse_dir)) / "multiverse.json"
            if nested_multiverse_dir
            else None
        )
        if nested_receipt_path is not None and nested_receipt_path.is_file():
            receipt = json.loads(nested_receipt_path.read_text(encoding="utf-8"))
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(
                receipt.get("cosmos_states")
                or receipt.get("civilization_states")
                or receipt.get("empire_states")
                or receipt.get("realm_states")
                or receipt.get("domains")
                or []
            ):
                if isinstance(ist, Mapping):
                    nested_cosmos_states.append(dict(ist))
        if after_portfolio is None and isinstance(
            multiverse_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(multiverse_result["federated_portfolio"])  # type: ignore[index]
        if not nested_cosmos_states:
            for ist in list(
                multiverse_result.get("cosmos_states")
                or multiverse_result.get("civilization_states")
                or multiverse_result.get("empire_states")
                or multiverse_result.get("realm_states")
                or []
            ):
                if isinstance(ist, Mapping):
                    nested_cosmos_states.append(dict(ist))

        for i, lst in enumerate(multiverse_states):
            if str(lst.get("multiverse_id")) != multiverse_id:
                continue
            updated = dict(lst)
            updated["last_multiverse_dir"] = multiverse_result.get("multiverse_dir")
            updated["last_multiverse_digest"] = multiverse_result.get("multiverse_digest")
            updated["multiverse_met"] = bool(multiverse_result.get("multiverse_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_cosmos_states:
                updated["cosmos_states"] = nested_cosmos_states
                updated["civilization_states"] = nested_cosmos_states
                updated["empire_states"] = nested_cosmos_states
            multiverse_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in multiverse_states]
        )
        coverage_after = omniverse_terminal_coverage(
            multiverse_states=multiverse_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_multiverse_roi(
            round_index=round_index,
            multiverse_id=multiverse_id,
            multiverse_result=multiverse_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(multiverse_result.get("multiverse_digest") or "")
        if idigest:
            multiverse_digests.append(idigest)

        rec = _multiverse_round_record(
            round_index=round_index,
            multiverse_id=multiverse_id,
            multiverse_result=multiverse_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            omniverse_dir=omniverse_dir,
            charter=active_charter,
            multiverse_states=multiverse_states,
            max_active_multiverses=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = omniverse_terminal_coverage(
                multiverse_states=multiverse_states,
                federated_portfolio=federated_portfolio,
            )

        write_omniverse_state(
            omniverse_dir,
            _state_payload(
                omniverse_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                multiverse_states=multiverse_states,
                multiverse_digests=multiverse_digests,
                charter=active_charter,
                stop_reason=None,
                omniverse_goal=omniverse_goal,
                max_active_multiverses=active_max,
                admissions=admissions,
                charter_expansions=charter_expansions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not multiverse_result.get("multiverse_met")
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
                    "multiverse_states": multiverse_states,
                    "last_multiverse_id": multiverse_id,
                    "federated_portfolio": federated_portfolio,
                    "omniverse_dir": str(omniverse_dir),
                    "pending_multiverse_ids": [
                        str(s.get("multiverse_id") or "")
                        for s in pending_charter_slots(
                            active_charter, multiverse_states
                        )
                    ],
                    "admissions": admissions,
                    "charter_expansions": charter_expansions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        # Grow constitution before declaring omniverse_met when expand remains.
        if (
            charter_expand is not None
            and not pending_charter_slots(active_charter, multiverse_states)
            and multiverses_all_met(multiverse_states)
        ):
            growth = charter_expand(
                active_charter=active_charter,
                multiverse_states=multiverse_states,
                round_index=round_index,
                roi_history=roi_history,
            )
            if growth.get("expanded") and growth.get("charter"):
                active_charter = normalize_omniverse_charter(
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
                    omniverse_dir=omniverse_dir,
                    charter=active_charter,
                    multiverse_states=multiverse_states,
                    max_active_multiverses=active_max,
                    round_index=round_index + 1,
                )
                if post_growth:
                    admissions.extend(post_growth)
                write_omniverse_state(
                    omniverse_dir,
                    _state_payload(
                        omniverse_id=lid,
                        round_count=round_index + 1,
                        total_dispatched=total_dispatched,
                        total_dispatched_ok=total_dispatched_ok,
                        federated_portfolio=federated_portfolio,
                        roi_history=roi_history,
                        multiverse_states=multiverse_states,
                        multiverse_digests=multiverse_digests,
                        charter=active_charter,
                        stop_reason=None,
                        omniverse_goal=omniverse_goal,
                        max_active_multiverses=active_max,
                        admissions=admissions,
                        charter_expansions=charter_expansions,
                    ),
                )
                # Continue the outer loop with the grown charter.
                continue

        if constitution_satisfied(
            multiverse_states=multiverse_states,
            charter=active_charter,
            omniverse_goal=omniverse_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "omniverse_met"
            omniverse_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            multiverse_states=multiverse_states,
            charter=active_charter,
            omniverse_goal=omniverse_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "omniverse_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        omniverse_dir=omniverse_dir,
        charter=active_charter,
        multiverse_states=multiverse_states,
        max_active_multiverses=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in multiverse_states]
    )
    coverage_end = omniverse_terminal_coverage(
        multiverse_states=multiverse_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        multiverse_states=multiverse_states,
        charter=active_charter,
        omniverse_goal=omniverse_goal,
        federated_portfolio=federated_portfolio,
    ):
        omniverse_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    multiverses_met_count = sum(
        1 for ist in multiverse_states if ist.get("multiverse_met")
    )
    pending_remaining = [
        str(s.get("multiverse_id") or "")
        for s in pending_charter_slots(active_charter, multiverse_states)
    ]

    if omniverse_met and stop_reason in {"omniverse_met", "max_rounds"}:
        verdict = "omniverse_met"
        ok = True
        stop_reason = "omniverse_met"
    elif stop_reason == "rank_only":
        verdict = "omniverse_ranked"
        ok = True
    elif stop_reason == "omniverse_idle":
        verdict = "omniverse_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "omniverse_budgeted"
        ok = True
    elif stop_reason.startswith("domain_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "multiverse_refused_mid"
        ok = False
    else:
        verdict = "omniverse_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "omniverse_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_multiverses": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "omniverse_goal": omniverse_goal,
        "omniverse_met": omniverse_met,
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
        "multiverses": institutions,
        "multiverse_digests": [
            i.get("multiverse_digest")
            for i in institutions
            if i.get("multiverse_digest")
        ],
        "multiverse_states": multiverse_states,
        "multiverses_admitted": len(multiverse_states),
        "multiverses_met_count": multiverses_met_count,
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
    receipt["multiverse_digests"] = [
        str(i.get("multiverse_digest") or "") for i in institutions
    ]
    receipt["omniverse_digest"] = _sha256_json(_omniverse_digest_payload(receipt))
    atomic_write_json(omniverse_dir / "omniverse.json", receipt)
    atomic_write_json(
        omniverse_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "omniverse_id": receipt["omniverse_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "omniverse_met": receipt["omniverse_met"],
            "multiverses_admitted": receipt["multiverses_admitted"],
            "multiverses_met_count": receipt["multiverses_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "charter_expansion_count": receipt["charter_expansion_count"],
            "max_active_multiverses": receipt["max_active_multiverses"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "omniverse_digest": receipt["omniverse_digest"],
            "resumed": resumed,
        },
    )

    write_omniverse_state(
        omniverse_dir,
        _state_payload(
            omniverse_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            multiverse_states=multiverse_states,
            multiverse_digests=receipt["multiverse_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            omniverse_goal=omniverse_goal,
            max_active_multiverses=active_max,
            admissions=admissions,
            charter_expansions=charter_expansions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "omniverse_dir": str(omniverse_dir),
        "omniverse_digest": receipt["omniverse_digest"],
        "omniverse_id": lid,
        "round_count": len(institutions),
        "multiverse_digests": list(receipt["multiverse_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "omniverse_met": omniverse_met,
        "multiverses_admitted": len(multiverse_states),
        "multiverses_met_count": multiverses_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_multiverses": active_max,
        "admissions": admissions,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": list(receipt["charter_expanded_ids"]),
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "multiverse_states": multiverse_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "multiverses": institutions,
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
    return umv._program_slot(
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
    return umv._inst_slot(
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
    return umv._commonwealth_slot(
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
    return umv._domain_slot(
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
    """Build a hermetic realm slot for an multiverse charter."""
    return umv._realm_slot(
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
    """Build a hermetic nested empire slot for a multiverse charter."""
    return umv._empire_slot(
        empire_id,
        priority=priority,
        realms=realms,
        institutions=institutions,
        max_rounds=max_rounds,
        empire_goal=empire_goal,
        max_active_realms=max_active_realms,
    )


def _multiverse_slot(
    multiverse_id: str,
    *,
    priority: int = 0,
    cosmoses: Sequence[dict[str, Any]] | None = None,
    civilizations: Sequence[dict[str, Any]] | None = None,
    empires: Sequence[dict[str, Any]] | None = None,
    realms: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    multiverse_goal: str = "all_cosmoses_met",
    max_active_cosmoses: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic omniverse charter multiverse slot.

    Prefer ``cosmoses=`` (nested cosmos slots for the multiverse plane).
    ``civilizations=`` / ``institutions=`` wrap a single auto cosmos.
    """
    nested: list[dict[str, Any]]
    if cosmoses is not None:
        nested = list(cosmoses)
    elif civilizations is not None:
        nested = [
            umv._cosmos_slot(
                f"{multiverse_id[:1]}o",
                civilizations=list(civilizations),
                max_rounds=max_rounds,
            )
        ]
    elif empires is not None:
        nested = [
            umv._cosmos_slot(
                f"{multiverse_id[:1]}o",
                empires=list(empires),
                max_rounds=max_rounds,
            )
        ]
    elif realms is not None:
        nested = [
            umv._cosmos_slot(
                f"{multiverse_id[:1]}o",
                realms=list(realms),
                max_rounds=max_rounds,
            )
        ]
    elif institutions:
        nested = [
            umv._cosmos_slot(
                f"{multiverse_id[:1]}o",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "multiverse_id": multiverse_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "multiverse_goal": multiverse_goal,
        "max_active_cosmoses": max_active_cosmoses,
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


def builtin_upstream_omniverse_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-multiverse multiverse plane (no network)."""
    scratch = _proof_scratch()
    try:
        campaign = _proof_campaign_runner(scratch)

        # Two realms; ultra-short ids for Windows nested artifact paths.
        charter = [
            _multiverse_slot(
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
            _multiverse_slot(
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

        confed = run_omniverse(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            omniverse_goal="all_multiverses_met",
            out_root=scratch / "m",
        )
        multi_omniverse_ok = (
            confed["ok"]
            and confed["omniverse_met"] is True
            and confed["stop_reason"] == "omniverse_met"
            and confed["multiverses_admitted"] == 2
            and confed["multiverses_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        scheduled_ids = {
            i.get("multiverse_id") for i in (confed.get("multiverses") or confed.get("realms") or [])
        }
        multi_omniverse_scheduled = multi_omniverse_ok and scheduled_ids >= {"a", "b"}

        verified = verify_omniverse_receipt(Path(confed["omniverse_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed[
            "round_count"
        ]

        # Tamper detection.
        confed_path = Path(confed["omniverse_dir"]) / "omniverse.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["omniverse_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_omniverse_receipt(Path(confed["omniverse_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "omniverse_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across leagues.
        campaign2 = _proof_campaign_runner(scratch / "b")
        budgeted = run_omniverse(
            charter=[
                _multiverse_slot(
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
                _multiverse_slot(
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
            omniverse_goal="none",
            out_root=scratch / "g",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit via custom multiverse_runner.
        def _walk_program_entries(node: Mapping[str, Any], bag: list[dict[str, Any]]) -> None:
            for pslot in list(node.get("charter") or []) + list(node.get("programs") or []):
                if not isinstance(pslot, Mapping):
                    continue
                if pslot.get("program_id") or pslot.get("initial_targets") or pslot.get(
                    "surface_charter"
                ):
                    for tgt in list(pslot.get("initial_targets") or []) + list(
                        pslot.get("surface_charter") or []
                    ):
                        if not isinstance(tgt, Mapping):
                            continue
                        for d in list(tgt.get("defects") or []):
                            if not isinstance(d, Mapping):
                                continue
                            bag.append(
                                {
                                    "name": tgt.get("name"),
                                    "version": tgt.get("version"),
                                    "defect_id": d.get("id"),
                                    "outcome": "impact_merged",
                                    "impact_digest": "c" * 64,
                                    "ok": True,
                                }
                            )
                else:
                    _walk_program_entries(pslot, bag)
            for key in (
                "civilizations",
                "empires",
                "realms",
                "domains",
                "commonwealths",
                "confederations",
                "leagues",
                "institutions",
            ):
                for child in list(node.get(key) or []):
                    if isinstance(child, Mapping):
                        _walk_program_entries(child, bag)

        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            nested_charter = umv.normalize_multiverse_charter(kwargs.get("charter"))
            entries: list[dict[str, Any]] = []
            civilization_states: list[dict[str, Any]] = []
            for cslot in nested_charter:
                if not isinstance(cslot, Mapping):
                    continue
                civ_entries: list[dict[str, Any]] = []
                _walk_program_entries(cslot, civ_entries)
                entries.extend(civ_entries)
                empire_states: list[dict[str, Any]] = []
                for eslot in list(cslot.get("charter") or []) + list(
                    cslot.get("empires") or []
                ):
                    if not isinstance(eslot, Mapping):
                        continue
                    empire_states.append(
                        {
                            "empire_id": eslot.get("empire_id") or eslot.get("id") or "e",
                            "empire_met": True,
                            "charter": list(eslot.get("charter") or []),
                            "portfolio": uf._proof_portfolio(civ_entries),
                            "realm_states": [],
                        }
                    )
                civilization_states.append(
                    {
                        "civilization_id": cslot.get("civilization_id")
                        or cslot.get("id")
                        or "c",
                        "civilization_met": True,
                        "charter": list(cslot.get("charter") or []),
                        "portfolio": uf._proof_portfolio(civ_entries),
                        "empire_states": empire_states,
                    }
                )
            portfolio = uf._proof_portfolio(entries)
            digest = _sha256_json({"premet": True, "entries": len(entries)})
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "multiverse_met",
                "stop_reason": "multiverse_met",
                "multiverse_id": kwargs.get("multiverse_id"),
                "multiverse_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "civilizations_admitted": len(nested_charter),
                "civilizations_met_count": len(nested_charter),
                "multiverse_digest": digest,
                "federated_portfolio": portfolio,
                "civilization_states": civilization_states,
                "coverage_end": {
                    "required": len(entries),
                    "covered": len(entries),
                    "met": True,
                    "coverage_ratio": 1.0,
                },
            }
            atomic_write_json(out / "multiverse.json", receipt)
            atomic_write_json(
                out / "multiverse_state.json",
                {
                    "multiverse_id": kwargs.get("multiverse_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "civilization_states": civilization_states,
                    "stop_reason": "multiverse_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "multiverse_met",
                "stop_reason": "multiverse_met",
                "multiverse_dir": str(out),
                "multiverse_digest": digest,
                "multiverse_id": kwargs.get("multiverse_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "multiverse_met": True,
                "civilizations_admitted": len(nested_charter),
                "civilizations_met_count": len(nested_charter),
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "civilization_states": civilization_states,
                "used_skill_route_discovery": False,
            }

        pre_met = run_omniverse(
            charter=[
                _multiverse_slot(
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
            multiverse_runner=_premet_runner,
            omniverse_goal="all_multiverses_met",
            out_root=scratch / "p",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["omniverse_met"] is True
            and pre_met["stop_reason"] == "omniverse_met"
            and pre_met["multiverses_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only domain.
        ranked = run_omniverse(
            charter=[
                _multiverse_slot(
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
                _multiverse_slot(
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
            omniverse_goal="none",
            out_root=scratch / "k",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "omniverse_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_omniverse(
                charter=[],
                dispatch=False,
                omniverse_goal="none",
                out_root=scratch / "z",
            )
        except OmniverseRefused as exc:
            empty_refused = exc.verdict in {
                "omniverse_empty",
                "omniverse_invalid",
            }

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_omniverse(
            charter=[
                _multiverse_slot(
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
                _multiverse_slot(
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
            omniverse_goal="none",
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
        partial = run_omniverse(
            charter=[
                _multiverse_slot(
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
                _multiverse_slot(
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
            omniverse_goal="none",
            omniverse_id="rcp",
            out_root=scratch / "a",
        )
        state_path = Path(partial["omniverse_dir"]) / "omniverse_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "rb")
        resumed = run_omniverse(
            resume_dir=Path(partial["omniverse_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            omniverse_goal="none",
            out_root=scratch / "r",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["omniverse_id"] == "rcp"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-league budget allocation evidence.
        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_multiverse"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_multiverse") or {}) >= 2
        )

        first_cw = (confed.get("multiverses") or confed.get("realms") or [{}])[0].get("multiverse_id")
        priority_ok = first_cw == "a"

        # Federation: inventories across both multiverses form a joint surface.
        fed_keys: set[tuple[str, str, str]] = set()
        for est in confed.get("multiverse_states") or []:
            if not isinstance(est, Mapping):
                continue
            empire_iter = list(est.get("empire_states") or [])
            if not empire_iter:
                empire_iter = list(est.get("realm_states") or [est])
            for emp in empire_iter:
                if not isinstance(emp, Mapping):
                    continue
                for rst in list(emp.get("realm_states") or [emp]):
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
        federation_ok = multi_omniverse_ok and (
            len(fed_keys) >= 3
            or float(fed_portfolio.get("coverage_ratio") or 0) == 1.0
            and int(fed_portfolio.get("required") or 0) >= 3
        )

        # Deferred admission: max_active=1 grows domain charter over time.
        campaign6 = _proof_campaign_runner(scratch / "dc")
        deferred = run_omniverse(
            charter=[
                _multiverse_slot(
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
                _multiverse_slot(
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
                _multiverse_slot(
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
            max_active_multiverses=1,
            dispatch=True,
            campaign_runner=campaign6,
            omniverse_goal="all_multiverses_met",
            out_root=scratch / "d",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("multiverse_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["omniverse_met"] is True
            and deferred["multiverses_admitted"] == 3
            and deferred["multiverses_met_count"] == 3
            and deferred.get("max_active_multiverses") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        # Charter expansion: start with one domain; grow constitution mid-run.
        campaign7 = _proof_campaign_runner(scratch / "xg")
        expand_runner = make_omniverse_charter_expand(
            [
                _multiverse_slot(
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
        expanded = run_omniverse(
            charter=[
                _multiverse_slot(
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
            max_active_multiverses=1,
            dispatch=True,
            campaign_runner=campaign7,
            charter_expand=expand_runner,
            omniverse_goal="all_multiverses_met",
            out_root=scratch / "x",
        )
        expand_ok = (
            expanded["ok"]
            and expanded["omniverse_met"] is True
            and expanded["multiverses_admitted"] == 2
            and expanded["multiverses_met_count"] == 2
            and int(expanded.get("charter_expansion_count") or 0) >= 1
            and "xg" in set(expanded.get("charter_expanded_ids") or [])
            and not (expanded.get("pending_remaining") or [])
        )

        # merge_omniverse_charter unit evidence (ids de-dupe, additions append).
        merged = merge_omniverse_charter(
            [_multiverse_slot("m1", institutions=[_inst_slot("mi", programs=[_program_slot("mp", initial=[("m", "1.0.0", "m-1")])])])],
            [
                _multiverse_slot("m1", institutions=[_inst_slot("mi2", programs=[_program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])])]),
                _multiverse_slot("m2", institutions=[_inst_slot("mj", programs=[_program_slot("mq", initial=[("n", "1.0.0", "n-1")])])]),
            ],
        )
        merge_ok = [s["multiverse_id"] for s in merged] == ["m1", "m2"]

        ok = all(
            [
                multi_omniverse_ok,
                multi_omniverse_scheduled,
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
            "omniverse_met": multi_omniverse_ok,
            "multi_omniverse_progressed": multi_omniverse_scheduled,
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
            "omniverse_digest": confed.get("omniverse_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "multiverses_admitted": confed.get("multiverses_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_omniverse_ok": multi_omniverse_ok,
                "multi_omniverse_scheduled": multi_omniverse_scheduled,
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
        result = verify_omniverse_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_omniverse_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
