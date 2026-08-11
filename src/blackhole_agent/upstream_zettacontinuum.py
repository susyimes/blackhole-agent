"""Upstream zettacontinuum plane: multi-exacontinuum durable stewardship zettacontinuum.

The exacontinuum plane (``upstream_exacontinuum``) closes multi-continuum unions *within one
exacontinuum*. It does not:

1. chain multiple independent exacontinuums under a durable zettacontinuum constitution;
2. allocate a shared global dispatch budget across exacontinuums by ROI;
3. admit/retire exacontinuum slots from an zettacontinuum charter over time
   (deferred admission under a concurrent-active cap);
4. grow the zettacontinuum charter mid-run via ``charter_expand`` (constitution
   growth beyond the initial charter, not just deferred admission of a fixed set);
5. federate multi-exacontinuum portfolio coverage into one zettacontinuum world-model;
6. persist zettacontinuum state so a later process can resume the union;
7. seal a multi-exacontinuum zettacontinuum chronicle linking exacontinuum digests.

The zettacontinuum plane closes that outer multi-exacontinuum loop:

1. **admit** — materialize exacontinuum slots from a durable zettacontinuum charter
   (each slot owns a nested continuum charter). When ``max_active_exacontinuums``
   is set, only that many *unmet* exacontinuums are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (zettacontinuum constitution growth over time);
2. **schedule** — pick the next open exacontinuum by priority and historical ROI;
3. **exacontinuum** — call the exacontinuum plane (injected ``exacontinuum_runner``;
   default ``run_exacontinuum``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-exacontinuum portfolios into one zettacontinuum world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark exacontinuums met when their exacontinuum_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **expand** — optional ``charter_expand`` may append new exacontinuum slots when
   the active charter has no pending work and all admitted exacontinuums are met,
   so the zettacontinuum constitution can grow after start (not only defer a fixed charter);
7. **persist** — write ``zettacontinuum_state.json`` after every exacontinuum round so a
   later ``run_zettacontinuum(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
8. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across exacontinuums
   - zettacontinuum goal met (``all_exacontinuums_met``: every *admitted*
     exacontinuum is met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

9. **seal** — write an zettacontinuum receipt under
   ``artifacts/upstream-zettacontinuum/`` with sha256 digests of every
   exacontinuum, portfolio federation, admission history, ROI history, stop
   reason, and an zettacontinuum chain digest; ``verify_zettacontinuum_receipt``
   re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is zettacontinuum-level direction
over the exacontinuum plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_exacontinuum as ee
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-zettacontinuum"

TERMINAL_SUCCESS_OUTCOMES = ee.TERMINAL_SUCCESS_OUTCOMES


class ZettacontinuumRefused(Exception):
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


def normalize_zettacontinuum_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize an zettacontinuum charter into deterministic continuum slots.

    Each slot is::

        {
          "exacontinuum_id": str,
          "priority": int,
          "charter": [...petacontinuum slots...],  # nested exacontinuum charter
          "max_active_petacontinuums": int | None,
          "max_rounds": int,
          "exacontinuum_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        exacontinuum_id = str(
            raw.get("exacontinuum_id") or raw.get("id") or ""
        ).strip()
        if not exacontinuum_id or exacontinuum_id in seen:
            continue
        seen.add(exacontinuum_id)

        nested = ee.normalize_exacontinuum_charter(
            raw.get("charter")
            or raw.get("petacontinuums")
            or raw.get("gigacontinuums")
            or raw.get("megacontinuums")
            or raw.get("ultracontinuums")
            or raw.get("continuums")
            or raw.get("omniverses")
            or raw.get("multiverses")
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

        max_active_petacontinuums = raw.get("max_active_petacontinuums")
        if max_active_petacontinuums is None:
            max_active_petacontinuums = raw.get("max_active_continuums")
        if max_active_petacontinuums is None:
            max_active_petacontinuums = raw.get("max_active_civilizations")
        if max_active_petacontinuums is not None:
            max_active_petacontinuums = max(1, int(max_active_petacontinuums))

        out.append(
            {
                "exacontinuum_id": exacontinuum_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_petacontinuums": max_active_petacontinuums,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "exacontinuum_goal": str(
                    raw.get("exacontinuum_goal") or "all_petacontinuums_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_exacontinuum"),
            }
        )
    return out


def admit_exacontinuum_slot(
    *,
    zettacontinuum_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with exacontinuum_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    exacontinuum_id = str(slot.get("exacontinuum_id") or "")
    if not exacontinuum_id:
        raise ZettacontinuumRefused("zettacontinuum_invalid", "slot missing exacontinuum_id")

    exacontinuum_root = Path(zettacontinuum_dir) / "exacontinuums" / exacontinuum_id
    exacontinuum_root.mkdir(parents=True, exist_ok=True)

    nested_charter = ee.normalize_exacontinuum_charter(slot.get("charter"))
    if not nested_charter:
        raise ZettacontinuumRefused(
            "zettacontinuum_invalid",
            f"continuum slot {exacontinuum_id!r} has empty nested charter",
        )

    max_active_petacontinuums = slot.get("max_active_petacontinuums")
    if max_active_petacontinuums is None:
        max_active_petacontinuums = slot.get("max_active_continuums")
    if max_active_petacontinuums is None:
        max_active_petacontinuums = slot.get("max_active_civilizations")

    return {
        "exacontinuum_id": exacontinuum_id,
        "exacontinuum_root": str(exacontinuum_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_petacontinuums": max_active_petacontinuums,
        "max_rounds": int(slot.get("max_rounds") or 6),
        "exacontinuum_goal": str(slot.get("exacontinuum_goal") or "all_petacontinuums_met"),
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
        "source": "zettacontinuum_federation",
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


def zettacontinuum_terminal_coverage(
    *,
    exacontinuum_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Coverage across exacontinuum->petacontinuum->...->program."""
    petacontinuum_states: list[dict[str, Any]] = []
    for uc in exacontinuum_states:
        if not isinstance(uc, Mapping):
            continue
        nested = (
            list(uc.get("petacontinuum_states") or [])
            or list(uc.get("megacontinuum_states") or [])
            or list(uc.get("ultracontinuum_states") or [])
        )
        if nested:
            for hc in nested:
                if isinstance(hc, Mapping):
                    petacontinuum_states.append(dict(hc))
            continue
        # Pre-run: exacontinuum charter is a list of petacontinuum slots.
        for cslot in list(uc.get("charter") or []) + list(
            uc.get("petacontinuums") or []
        ) + list(uc.get("megacontinuums") or []) + list(uc.get("ultracontinuums") or []) + list(
            uc.get("continuums") or []
        ) + list(uc.get("omniverses") or []) + list(uc.get("multiverses") or []):
            if isinstance(cslot, Mapping):
                petacontinuum_states.append(dict(cslot))
        if not nested and not list(uc.get("charter") or []):
            for cont in list(uc.get("continuum_states") or []) + list(
                uc.get("omniverse_states") or []
            ) + list(uc.get("multiverse_states") or []) + list(
                uc.get("cosmos_states") or []
            ) + list(uc.get("civilization_states") or []):
                if isinstance(cont, Mapping):
                    petacontinuum_states.append(dict(cont))
        for raw in list(uc.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                petacontinuum_states.append(
                    {
                        "inventory_keys": [
                            (str(raw[0]), str(raw[1]), str(raw[2]))
                        ]
                    }
                )
            elif isinstance(raw, Mapping):
                petacontinuum_states.append({"inventory_keys": [raw]})
    return ee.exacontinuum_terminal_coverage(
        petacontinuum_states=petacontinuum_states,
        federated_portfolio=federated_portfolio,
    )


def exacontinuums_all_met(exacontinuum_states: Sequence[Mapping[str, Any]]) -> bool:
    if not exacontinuum_states:
        return False
    return all(bool(ist.get("exacontinuum_met")) for ist in exacontinuum_states)


def open_unmet_count(exacontinuum_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet continuum_met."""
    return sum(1 for ist in exacontinuum_states if not ist.get("exacontinuum_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    exacontinuum_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then exacontinuum_id-asc."""
    known = {str(ist.get("exacontinuum_id") or "") for ist in exacontinuum_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("exacontinuum_id") or "")
        and str(slot.get("exacontinuum_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("exacontinuum_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    exacontinuum_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    zettacontinuum_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if zettacontinuum_goal == "none":
        return False
    if zettacontinuum_goal == "terminal_coverage":
        cov = zettacontinuum_terminal_coverage(
            exacontinuum_states=exacontinuum_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, exacontinuum_states
        )
    if zettacontinuum_goal == "all_exacontinuums_met":
        if not exacontinuum_states:
            return False
        if pending_charter_slots(charter, exacontinuum_states):
            return False
        return exacontinuums_all_met(exacontinuum_states)
    return False


def reopen_incomplete_exacontinuums(
    exacontinuum_states: list[dict[str, Any]],
    *,
    federated_portfolio: Mapping[str, Any] | None,
) -> list[str]:
    """Clear ``continuum_met`` on children still short of terminal coverage.

    Nested exacontinuums can retire after only partial surface work (e.g. before
    deferred program targets expand). Under a ``terminal_coverage`` zettacontinuum
    goal those children must re-run until federated inventory is fully
    terminal-success. Returns the reopened ``exacontinuum_id`` list.
    """
    cov = zettacontinuum_terminal_coverage(
        exacontinuum_states=exacontinuum_states,
        federated_portfolio=federated_portfolio,
    )
    if cov.get("met"):
        return []
    open_keys: set[tuple[str, str, str]] = set()
    for item in list(cov.get("open_or_missing") or []):
        if not isinstance(item, Mapping):
            continue
        key = (
            str(item.get("name") or ""),
            str(item.get("version") or ""),
            str(item.get("defect_id") or ""),
        )
        if key[0] and key[2]:
            open_keys.add(key)
    reopened: list[str] = []
    for i, ist in enumerate(exacontinuum_states):
        if not ist.get("exacontinuum_met"):
            continue
        # Prefer precise reopen when inventory keys are known; otherwise reopen
        # every met child until federated coverage is green.
        child_keys: set[tuple[str, str, str]] = set()
        for raw in list(ist.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                child_keys.add((str(raw[0]), str(raw[1]), str(raw[2])))
            elif isinstance(raw, Mapping):
                child_keys.add(
                    (
                        str(raw.get("name") or ""),
                        str(raw.get("version") or ""),
                        str(raw.get("defect_id") or ""),
                    )
                )
        # Walk nested megacontinuum / ultracontinuum / multiverse charter surfaces.
        for mv in list(ist.get("petacontinuum_states") or []) + list(
            ist.get("megacontinuum_states") or []
        ) + list(ist.get("ultracontinuum_states") or []) + list(
            ist.get("continuum_states") or []
        ) + list(ist.get("omniverse_states") or []) + list(
            ist.get("multiverse_states") or []
        ) + list(ist.get("charter") or []):
            if isinstance(mv, Mapping):
                child_keys.update(_collect_from_realm_state(mv))
                for cos in list(mv.get("charter") or []) + list(
                    mv.get("continuums") or []
                ) + list(mv.get("cosmoses") or []):
                    if isinstance(cos, Mapping):
                        child_keys.update(_collect_from_realm_state(cos))
        owns_open = (not open_keys) or (not child_keys) or bool(child_keys & open_keys)
        if not owns_open and open_keys:
            # Still reopen when this child contributed zero covered entries but
            # federated coverage is incomplete (inventory may only live nested).
            owns_open = True
        if not owns_open:
            continue
        updated = dict(ist)
        updated["exacontinuum_met"] = False
        exacontinuum_states[i] = updated
        reopened.append(str(updated.get("exacontinuum_id") or ""))
    return [r for r in reopened if r]


def merge_zettacontinuum_charter(
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge additional realm slots into a continuum charter.

    Existing ``exacontinuum_id`` values win (additions with the same id are
    ignored). Returns a fully re-normalized charter so nested confederation
    charters stay deterministic.
    """
    base = normalize_zettacontinuum_charter(existing)
    if not additions:
        return base
    known = {str(s.get("exacontinuum_id") or "") for s in base}
    merged: list[Mapping[str, Any]] = list(base)
    for raw in additions:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get("exacontinuum_id") or raw.get("id") or "").strip()
        if not cid or cid in known:
            continue
        known.add(cid)
        merged.append(raw)
    return normalize_zettacontinuum_charter(merged)


def make_zettacontinuum_charter_expand(
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
    pending_growth = normalize_zettacontinuum_charter(growth)
    applied_ids: set[str] = set(str(x) for x in (applied or []))
    state: dict[str, Any] = {
        "applied": applied_ids,
        "growth": pending_growth,
        "max_slots_per_expand": max(1, int(max_slots_per_expand)),
    }

    def _runner(
        *,
        active_charter: Sequence[Mapping[str, Any]],
        exacontinuum_states: Sequence[Mapping[str, Any]],
        round_index: int,
        roi_history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        remaining = [
            s
            for s in pending_growth
            if str(s.get("exacontinuum_id") or "") not in applied_ids
            and str(s.get("exacontinuum_id") or "")
            not in {str(x.get("exacontinuum_id") or "") for x in active_charter}
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
            applied_ids.add(str(s.get("exacontinuum_id") or ""))
        merged = merge_zettacontinuum_charter(active_charter, take)
        state["applied"] = applied_ids
        return {
            "expanded": True,
            "added": [str(s.get("exacontinuum_id") or "") for s in take],
            "charter": merged,
            "detail": "charter_growth_applied",
            "round_index": round_index,
            "realms_met": exacontinuums_all_met(exacontinuum_states),
        }

    _runner.charter_state = state  # type: ignore[attr-defined]
    return _runner


def admit_pending_slots(
    *,
    zettacontinuum_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    exacontinuum_states: list[dict[str, Any]],
    max_active_exacontinuums: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_exacontinuums`` caps *unmet* concurrent realms. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``exacontinuum_states``).
    """
    pending = pending_charter_slots(charter, exacontinuum_states)
    if not pending:
        return []

    open_n = open_unmet_count(exacontinuum_states)
    if max_active_exacontinuums is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_exacontinuums) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_exacontinuum_slot(zettacontinuum_dir=zettacontinuum_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        exacontinuum_states.append(
            {
                "exacontinuum_id": admission["exacontinuum_id"],
                "exacontinuum_root": admission["exacontinuum_root"],
                "charter": admission["charter"],
                "max_active_petacontinuums": admission.get("max_active_petacontinuums"),
                "max_rounds": admission["max_rounds"],
                "exacontinuum_goal": admission["exacontinuum_goal"],
                "priority": admission["priority"],
                "exacontinuum_met": False,
                "last_exacontinuum_dir": None,
                "last_exacontinuum_digest": None,
                "portfolio": None,
                "omniverse_states": [],
                "multiverse_states": [],
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


def score_exacontinuum_roi(
    *,
    round_index: int,
    exacontinuum_id: str,
    continuum_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one institution round for league learning / scheduling bias."""
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(continuum_result.get("total_dispatched_ok") or 0)
    dispatched = int(continuum_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        "exacontinuum_id": exacontinuum_id,
        "stop_reason": continuum_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "exacontinuum_met": bool(continuum_result.get("exacontinuum_met")),
        "continuum_digest": continuum_result.get("exacontinuum_digest"),
        "continuums_admitted": int(
            continuum_result.get("petacontinuums_admitted")
            or continuum_result.get("megacontinuums_admitted")
            or continuum_result.get("ultracontinuums_admitted")
            or continuum_result.get("exacontinuums_admitted")
            or continuum_result.get("continuums_admitted")
            or continuum_result.get("omniverses_admitted")
            or continuum_result.get("multiverses_admitted")
            or continuum_result.get("empires_admitted")
            or continuum_result.get("realms_admitted")
            or 0
        ),
        "continuums_met_count": int(
            continuum_result.get("petacontinuums_met_count")
            or continuum_result.get("megacontinuums_met_count")
            or continuum_result.get("ultracontinuums_met_count")
            or continuum_result.get("exacontinuums_met_count")
            or continuum_result.get("continuums_met_count")
            or continuum_result.get("omniverses_met_count")
            or continuum_result.get("multiverses_met_count")
            or continuum_result.get("empires_met_count")
            or continuum_result.get("realms_met_count")
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
            "by_continuum": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_continuum: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get("exacontinuum_id") or "")
        bucket = by_continuum.setdefault(
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
    for iid, bucket in by_continuum.items():
        n = max(1, int(bucket["rounds"]))
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / n
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_continuum": by_continuum,
    }


def select_next_exacontinuum(
    exacontinuum_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable exacontinuum_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in exacontinuum_states if not ist.get("exacontinuum_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_continuum = summary.get("by_continuum") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("exacontinuum_id") or "")
        hist = by_continuum.get(iid) or {}
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


def allocate_exacontinuum_budget(
    *,
    remaining_budget: int | None,
    open_continuum_count: int,
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
    open_n = max(1, int(open_continuum_count))
    base = max(1, remaining // open_n)
    summary = _roi_summary(roi_history)
    hist = (summary.get("by_continuum") or {}).get(
        str(selected.get("exacontinuum_id") or "")
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
    zettacontinuum_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    exacontinuum_states: Sequence[Mapping[str, Any]],
    exacontinuum_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    zettacontinuum_goal: str,
    max_active_exacontinuums: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
    charter_expansions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "zettacontinuum_id": zettacontinuum_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "exacontinuum_states": [dict(ist) for ist in exacontinuum_states],
        "exacontinuum_digests": list(exacontinuum_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "zettacontinuum_goal": zettacontinuum_goal,
        "max_active_exacontinuums": max_active_exacontinuums,
        "admissions": [dict(a) for a in (admissions or [])],
        "charter_expansions": [dict(e) for e in (charter_expansions or [])],
        "pending_exacontinuum_ids": [
            str(s.get("exacontinuum_id") or "")
            for s in pending_charter_slots(charter, exacontinuum_states)
        ],
    }


def write_zettacontinuum_state(zettacontinuum_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(zettacontinuum_dir) / "zettacontinuum_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_zettacontinuum_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "zettacontinuum_state.json")
    if not path.is_file():
        raise ZettacontinuumRefused(
            "zettacontinuum_state_missing",
            f"no zettacontinuum_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ZettacontinuumRefused("zettacontinuum_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise ZettacontinuumRefused("zettacontinuum_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _exacontinuum_round_record(
    *,
    round_index: int,
    exacontinuum_id: str,
    continuum_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "exacontinuum_id": exacontinuum_id,
        "ok": bool(continuum_result.get("ok")),
        "verdict": continuum_result.get("verdict"),
        "stop_reason": continuum_result.get("stop_reason"),
        "exacontinuum_dir": continuum_result.get("exacontinuum_dir"),
        "exacontinuum_digest": continuum_result.get("exacontinuum_digest"),
        "continuums_admitted": int(
            continuum_result.get("petacontinuums_admitted")
            or continuum_result.get("megacontinuums_admitted")
            or continuum_result.get("ultracontinuums_admitted")
            or continuum_result.get("exacontinuums_admitted")
            or continuum_result.get("continuums_admitted")
            or continuum_result.get("omniverses_admitted")
            or continuum_result.get("multiverses_admitted")
            or continuum_result.get("empires_admitted")
            or continuum_result.get("realms_admitted")
            or 0
        ),
        "continuums_met_count": int(
            continuum_result.get("petacontinuums_met_count")
            or continuum_result.get("megacontinuums_met_count")
            or continuum_result.get("ultracontinuums_met_count")
            or continuum_result.get("exacontinuums_met_count")
            or continuum_result.get("continuums_met_count")
            or continuum_result.get("omniverses_met_count")
            or continuum_result.get("multiverses_met_count")
            or continuum_result.get("empires_met_count")
            or continuum_result.get("realms_met_count")
            or 0
        ),
        "total_dispatched": int(continuum_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(continuum_result.get("total_dispatched_ok") or 0),
        "exacontinuum_met": bool(continuum_result.get("exacontinuum_met")),
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


def _zettacontinuum_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "zettacontinuum_id": receipt.get("zettacontinuum_id"),
        "zettacontinuum_goal": receipt.get("zettacontinuum_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_exacontinuums": receipt.get("max_active_exacontinuums"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "exacontinuum_digests": list(receipt.get("exacontinuum_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "zettacontinuum_met": receipt.get("zettacontinuum_met"),
        "coverage_end": receipt.get("coverage_end"),
        "exacontinuums_met_count": receipt.get("exacontinuums_met_count"),
        "exacontinuums_admitted": receipt.get("exacontinuums_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "charter_expansion_count": receipt.get("charter_expansion_count"),
        "charter_expanded_ids": list(receipt.get("charter_expanded_ids") or []),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_zettacontinuum_receipt(zettacontinuum_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(zettacontinuum_dir) / "zettacontinuum.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_zettacontinuum_digest_payload(receipt))
    recorded = str(receipt.get("zettacontinuum_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("zettacontinuum_digest")

    institutions = list(receipt.get("exacontinuums") or receipt.get("realms") or receipt.get("leagues") or [])
    listed = list(receipt.get("exacontinuum_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("exacontinuum_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("exacontinuum_digest"):
                mismatched.append(f"exacontinuum_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("exacontinuum_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "exacontinuum.json").is_file():
            nested = ee.verify_exacontinuum_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "zettacontinuum_sealed" if ok else "zettacontinuum_tampered",
        "zettacontinuum_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run realm


def run_zettacontinuum(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_exacontinuums: int | None = None,
    dispatch: bool = True,
    exacontinuum_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    charter_expand: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    zettacontinuum_goal: str = "all_exacontinuums_met",
    refresh_promotions: Mapping[str, str] | None = None,
    zettacontinuum_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_zettacontinuum_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_exacontinuums:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    zettacontinuum_goal:
        ``all_exacontinuums_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``zettacontinuum_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise ZettacontinuumRefused("zettacontinuum_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise ZettacontinuumRefused(
            "zettacontinuum_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_exacontinuums is not None and int(max_active_exacontinuums) < 1:
        raise ZettacontinuumRefused(
            "zettacontinuum_invalid", "max_active_exacontinuums must be >= 1 when set"
        )
    if zettacontinuum_goal not in {"all_exacontinuums_met", "terminal_coverage", "none"}:
        raise ZettacontinuumRefused(
            "zettacontinuum_invalid",
            f"unknown zettacontinuum_goal: {zettacontinuum_goal}",
        )

    runner = exacontinuum_runner or ee.run_exacontinuum

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    exacontinuum_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_zettacontinuum_id: str | None = None
    exacontinuum_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    charter_expansions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_zettacontinuum_state(resume_dir)
        resumed = True
        resume_zettacontinuum_id = str(state.get("zettacontinuum_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        exacontinuum_digests = [str(d) for d in (state.get("exacontinuum_digests") or [])]
        exacontinuum_states = [
            dict(ist)
            for ist in (state.get("exacontinuum_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_zettacontinuum_charter(
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
            state.get("max_active_exacontinuums") is not None
            and max_active_exacontinuums is None
        ):
            resumed_max_active = int(state["max_active_exacontinuums"])
        # Resume may also merge a caller-supplied charter growth tail.
        if charter:
            active_charter = merge_zettacontinuum_charter(active_charter, charter)
    else:
        active_charter = normalize_zettacontinuum_charter(charter)

    active_max = (
        max_active_exacontinuums
        if max_active_exacontinuums is not None
        else resumed_max_active
    )

    if not active_charter and not exacontinuum_states:
        raise ZettacontinuumRefused(
            "zettacontinuum_empty",
            "continuum charter has no admitable realm slots",
        )

    lid = (
        zettacontinuum_id
        or resume_zettacontinuum_id
        or f"zettacontinuum-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        zettacontinuum_dir = Path(out_root)
        if (zettacontinuum_dir / "zettacontinuum.json").is_file():
            zettacontinuum_dir = zettacontinuum_dir / stamp
    else:
        zettacontinuum_dir = ARTIFACTS_ROOT / stamp
    zettacontinuum_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    # Child continuum trees already consume most of MAX_PATH; place their roots
    # on a flat ultra-short base (not under zettacontinuum_dir) so one extra
    # federation layer still fits on Windows.
    import os as _os

    if league_out_root is not None:
        lg_root = Path(league_out_root)
    elif _os.name == "nt":
        lg_root = Path("C:/t") / "p"
    else:
        lg_root = zettacontinuum_dir / "e"
    lg_root.mkdir(parents=True, exist_ok=True)
    if _os.name == "nt":
        inst_flat_root = Path("C:/t") / "q"
    else:
        inst_flat_root = zettacontinuum_dir / "x"
    inst_flat_root.mkdir(parents=True, exist_ok=True)
    # Per-run namespace so parallel/resumed ultracontinua do not collide.
    # Prefer a short random token over the human lid (often "zettacontinuum-…")
    # so Windows paths stay short and never re-enter a prior exacontinuum_dir that
    # already has continuum.json (which forces an extra timestamp segment).
    import secrets as _secrets

    _run_ns = _secrets.token_hex(2)
    lg_root = lg_root / _run_ns
    inst_flat_root = inst_flat_root / _run_ns
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        zettacontinuum_dir=zettacontinuum_dir,
        charter=active_charter,
        exacontinuum_states=exacontinuum_states,
        max_active_exacontinuums=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not exacontinuum_states and not pending_charter_slots(
        active_charter, exacontinuum_states
    ):
        raise ZettacontinuumRefused("zettacontinuum_empty", "no realm slots admitted")
    if not exacontinuum_states and pending_charter_slots(
        active_charter, exacontinuum_states
    ):
        raise ZettacontinuumRefused(
            "zettacontinuum_empty",
            "no realm slots admitted under max_active_exacontinuums policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in exacontinuum_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    zettacontinuum_met = False
    terminal_reopen_count = 0
    max_terminal_reopens = max(2, (len(exacontinuum_states) or 1) * 4)
    coverage_end: dict[str, Any] = zettacontinuum_terminal_coverage(
        exacontinuum_states=exacontinuum_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            zettacontinuum_dir=zettacontinuum_dir,
            charter=active_charter,
            exacontinuum_states=exacontinuum_states,
            max_active_exacontinuums=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = zettacontinuum_terminal_coverage(
            exacontinuum_states=exacontinuum_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            exacontinuum_states=exacontinuum_states,
            charter=active_charter,
            zettacontinuum_goal=zettacontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "zettacontinuum_met"
            zettacontinuum_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_exacontinuum(
            exacontinuum_states, roi_history, round_index=round_index
        )
        if selected is None:
            # Children may all report met while federated terminal coverage is
            # still incomplete (e.g. deferred surfaces). Only declare zettacontinuum
            # met when the active zettacontinuum_goal is actually satisfied.
            if constitution_satisfied(
                exacontinuum_states=exacontinuum_states,
                charter=active_charter,
                zettacontinuum_goal=zettacontinuum_goal,
                federated_portfolio=federated_portfolio,
            ):
                stop_reason = "zettacontinuum_met"
                zettacontinuum_met = True
                coverage_end = coverage_before
                break
            if (
                zettacontinuum_goal == "terminal_coverage"
                and terminal_reopen_count < max_terminal_reopens
            ):
                reopened = reopen_incomplete_exacontinuums(
                    exacontinuum_states,
                    federated_portfolio=federated_portfolio,
                )
                if reopened:
                    terminal_reopen_count += 1
                    selected = select_next_exacontinuum(
                        exacontinuum_states, roi_history, round_index=round_index
                    )
            if selected is None:
                stop_reason = "zettacontinuum_idle"
                coverage_end = coverage_before
                break

        open_count = sum(
            1 for ist in exacontinuum_states if not ist.get("exacontinuum_met")
        )
        allocated = allocate_exacontinuum_budget(
            remaining_budget=remaining_budget,
            open_continuum_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        exacontinuum_id = str(selected["exacontinuum_id"])
        resume_exacontinuum_dir = selected.get("last_exacontinuum_dir")
        continuum_resume: Path | None = None
        if (
            resume_exacontinuum_dir
            and (Path(str(resume_exacontinuum_dir)) / "exacontinuum_state.json").is_file()
            and not selected.get("exacontinuum_met")
        ):
            continuum_resume = Path(str(resume_exacontinuum_dir))

        # Ultra-short stamp (each outer plane tightens Windows MAX_PATH).
        # Do NOT nest child exacontinuum trees under zettacontinuum roots:
        # let the exacontinuum plane use its own flat C:/t/{h,i} bases so the
        # deep continuum→…→wave chain still fits. Only the exacontinuum receipt
        # itself lands on a flat unique out_root.
        safe_id = "".join(c if c.isalnum() else "" for c in exacontinuum_id)[:2] or "i"
        child_token = _secrets.token_hex(2)
        if _os.name == "nt":
            out_dir = Path("C:/t") / "p" / f"{child_token}{safe_id}"
            inst_out = None
        else:
            out_dir = lg_root / f"{round_index:x}{safe_id}"
            inst_out = inst_flat_root / f"{round_index:x}{safe_id}"
        continuum_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "max_epochs_per_succession": max_epochs_per_succession,
            "max_waves_per_epoch": max_waves_per_epoch,
            "per_wave_dispatch_limit": per_wave_dispatch_limit,
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            "exacontinuum_goal": str(
                selected.get("exacontinuum_goal") or "all_petacontinuums_met"
            ),
            "exacontinuum_id": exacontinuum_id,
            "out_root": out_dir,
        }
        if inst_out is not None:
            continuum_kwargs["league_out_root"] = inst_out
        max_active_petacontinuums = selected.get("max_active_petacontinuums")
        if max_active_petacontinuums is None:
            max_active_petacontinuums = selected.get("max_active_continuums")
        if max_active_petacontinuums is None:
            max_active_petacontinuums = selected.get("max_active_civilizations")
        if max_active_petacontinuums is not None:
            continuum_kwargs["max_active_petacontinuums"] = int(
                max_active_petacontinuums
            )
        if continuum_resume is not None:
            continuum_kwargs["resume_dir"] = continuum_resume
            # charter already on resume state
            continuum_kwargs.pop("charter", None)
        if program_runner is not None:
            continuum_kwargs["program_runner"] = program_runner
        if campaign_runner is not None:
            continuum_kwargs["campaign_runner"] = campaign_runner
        if succession_runner is not None:
            continuum_kwargs["succession_runner"] = succession_runner
        if epoch_runner is not None:
            continuum_kwargs["epoch_runner"] = epoch_runner
        if impact_refresh_runner is not None:
            continuum_kwargs["impact_refresh_runner"] = impact_refresh_runner
        if feedback_runner is not None:
            continuum_kwargs["feedback_runner"] = feedback_runner
        if refresh_promotions is not None:
            continuum_kwargs["refresh_promotions"] = refresh_promotions

        try:
            continuum_result = runner(**continuum_kwargs)
        except ee.ExacontinuumRefused as exc:
            if local_index == 0 and not resumed:
                raise ZettacontinuumRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"continuum_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise ZettacontinuumRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise ZettacontinuumRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"fleet_refused:{exc.verdict}"
            coverage_end = coverage_before
            break

        dispatched_n = int(continuum_result.get("total_dispatched") or 0)
        dispatched_ok = int(continuum_result.get("total_dispatched_ok") or 0)
        prior_inst_dispatched = int(selected.get("total_dispatched") or 0)
        prior_inst_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_inst_dispatched)
        delta_ok = max(0, dispatched_ok - prior_inst_ok)
        if continuum_resume is None and prior_inst_dispatched == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        nested_exacontinuum_dir = continuum_result.get("exacontinuum_dir")
        nested_multiverse_states: list[dict[str, Any]] = []
        nested_receipt_path = (
            Path(str(nested_exacontinuum_dir)) / "exacontinuum.json"
            if nested_exacontinuum_dir
            else None
        )
        if nested_receipt_path is not None and nested_receipt_path.is_file():
            receipt = json.loads(nested_receipt_path.read_text(encoding="utf-8"))
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(
                receipt.get("petacontinuum_states")
                or receipt.get("megacontinuum_states")
                or receipt.get("ultracontinuum_states")
                or receipt.get("continuum_states")
                or receipt.get("omniverse_states")
                or receipt.get("multiverse_states")
                or receipt.get("cosmos_states")
                or receipt.get("civilization_states")
                or receipt.get("empire_states")
                or receipt.get("realm_states")
                or []
            ):
                if isinstance(ist, Mapping):
                    nested_multiverse_states.append(dict(ist))
        if after_portfolio is None and isinstance(
            continuum_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(continuum_result["federated_portfolio"])  # type: ignore[index]
        if not nested_multiverse_states:
            for ist in list(
                continuum_result.get("petacontinuum_states")
                or continuum_result.get("megacontinuum_states")
                or continuum_result.get("ultracontinuum_states")
                or continuum_result.get("continuum_states")
                or continuum_result.get("omniverse_states")
                or continuum_result.get("multiverse_states")
                or continuum_result.get("cosmos_states")
                or continuum_result.get("civilization_states")
                or continuum_result.get("empire_states")
                or []
            ):
                if isinstance(ist, Mapping):
                    nested_multiverse_states.append(dict(ist))

        for i, lst in enumerate(exacontinuum_states):
            if str(lst.get("exacontinuum_id")) != exacontinuum_id:
                continue
            updated = dict(lst)
            updated["last_exacontinuum_dir"] = continuum_result.get("exacontinuum_dir")
            updated["last_exacontinuum_digest"] = continuum_result.get("exacontinuum_digest")
            updated["exacontinuum_met"] = bool(continuum_result.get("exacontinuum_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_multiverse_states:
                updated["petacontinuum_states"] = nested_multiverse_states
                updated["megacontinuum_states"] = nested_multiverse_states
                updated["ultracontinuum_states"] = nested_multiverse_states
                updated["continuum_states"] = nested_multiverse_states
                updated["omniverse_states"] = nested_multiverse_states
                updated["multiverse_states"] = nested_multiverse_states
                updated["cosmos_states"] = nested_multiverse_states
                updated["civilization_states"] = nested_multiverse_states
                updated["empire_states"] = nested_multiverse_states
            exacontinuum_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in exacontinuum_states]
        )
        coverage_after = zettacontinuum_terminal_coverage(
            exacontinuum_states=exacontinuum_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_exacontinuum_roi(
            round_index=round_index,
            exacontinuum_id=exacontinuum_id,
            continuum_result=continuum_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(continuum_result.get("exacontinuum_digest") or "")
        if idigest:
            exacontinuum_digests.append(idigest)

        rec = _exacontinuum_round_record(
            round_index=round_index,
            exacontinuum_id=exacontinuum_id,
            continuum_result=continuum_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            zettacontinuum_dir=zettacontinuum_dir,
            charter=active_charter,
            exacontinuum_states=exacontinuum_states,
            max_active_exacontinuums=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = zettacontinuum_terminal_coverage(
                exacontinuum_states=exacontinuum_states,
                federated_portfolio=federated_portfolio,
            )

        write_zettacontinuum_state(
            zettacontinuum_dir,
            _state_payload(
                zettacontinuum_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                exacontinuum_states=exacontinuum_states,
                exacontinuum_digests=exacontinuum_digests,
                charter=active_charter,
                stop_reason=None,
                zettacontinuum_goal=zettacontinuum_goal,
                max_active_exacontinuums=active_max,
                admissions=admissions,
                charter_expansions=charter_expansions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not continuum_result.get("exacontinuum_met")
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
                    "exacontinuum_states": exacontinuum_states,
                    "last_exacontinuum_id": exacontinuum_id,
                    "federated_portfolio": federated_portfolio,
                    "zettacontinuum_dir": str(zettacontinuum_dir),
                    "pending_exacontinuum_ids": [
                        str(s.get("exacontinuum_id") or "")
                        for s in pending_charter_slots(
                            active_charter, exacontinuum_states
                        )
                    ],
                    "admissions": admissions,
                    "charter_expansions": charter_expansions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        # Grow constitution before declaring zettacontinuum_met when expand remains.
        if (
            charter_expand is not None
            and not pending_charter_slots(active_charter, exacontinuum_states)
            and exacontinuums_all_met(exacontinuum_states)
        ):
            growth = charter_expand(
                active_charter=active_charter,
                exacontinuum_states=exacontinuum_states,
                round_index=round_index,
                roi_history=roi_history,
            )
            if growth.get("expanded") and growth.get("charter"):
                active_charter = normalize_zettacontinuum_charter(
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
                    zettacontinuum_dir=zettacontinuum_dir,
                    charter=active_charter,
                    exacontinuum_states=exacontinuum_states,
                    max_active_exacontinuums=active_max,
                    round_index=round_index + 1,
                )
                if post_growth:
                    admissions.extend(post_growth)
                write_zettacontinuum_state(
                    zettacontinuum_dir,
                    _state_payload(
                        zettacontinuum_id=lid,
                        round_count=round_index + 1,
                        total_dispatched=total_dispatched,
                        total_dispatched_ok=total_dispatched_ok,
                        federated_portfolio=federated_portfolio,
                        roi_history=roi_history,
                        exacontinuum_states=exacontinuum_states,
                        exacontinuum_digests=exacontinuum_digests,
                        charter=active_charter,
                        stop_reason=None,
                        zettacontinuum_goal=zettacontinuum_goal,
                        max_active_exacontinuums=active_max,
                        admissions=admissions,
                        charter_expansions=charter_expansions,
                    ),
                )
                # Continue the outer loop with the grown charter.
                continue

        if constitution_satisfied(
            exacontinuum_states=exacontinuum_states,
            charter=active_charter,
            zettacontinuum_goal=zettacontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "zettacontinuum_met"
            zettacontinuum_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            exacontinuum_states=exacontinuum_states,
            charter=active_charter,
            zettacontinuum_goal=zettacontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "zettacontinuum_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        zettacontinuum_dir=zettacontinuum_dir,
        charter=active_charter,
        exacontinuum_states=exacontinuum_states,
        max_active_exacontinuums=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in exacontinuum_states]
    )
    coverage_end = zettacontinuum_terminal_coverage(
        exacontinuum_states=exacontinuum_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        exacontinuum_states=exacontinuum_states,
        charter=active_charter,
        zettacontinuum_goal=zettacontinuum_goal,
        federated_portfolio=federated_portfolio,
    ):
        zettacontinuum_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    exacontinuums_met_count = sum(
        1 for ist in exacontinuum_states if ist.get("exacontinuum_met")
    )
    pending_remaining = [
        str(s.get("exacontinuum_id") or "")
        for s in pending_charter_slots(active_charter, exacontinuum_states)
    ]

    if zettacontinuum_met and stop_reason in {"zettacontinuum_met", "max_rounds"}:
        verdict = "zettacontinuum_met"
        ok = True
        stop_reason = "zettacontinuum_met"
    elif stop_reason == "rank_only":
        verdict = "zettacontinuum_ranked"
        ok = True
    elif stop_reason == "zettacontinuum_idle":
        verdict = "zettacontinuum_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "zettacontinuum_budgeted"
        ok = True
    elif stop_reason.startswith("domain_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "continuum_refused_mid"
        ok = False
    else:
        verdict = "zettacontinuum_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "zettacontinuum_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_exacontinuums": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "zettacontinuum_goal": zettacontinuum_goal,
        "zettacontinuum_met": zettacontinuum_met,
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
        "exacontinuums": institutions,
        "exacontinuum_digests": [
            i.get("exacontinuum_digest")
            for i in institutions
            if i.get("exacontinuum_digest")
        ],
        "exacontinuum_states": exacontinuum_states,
        "exacontinuums_admitted": len(exacontinuum_states),
        "exacontinuums_met_count": exacontinuums_met_count,
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
    receipt["exacontinuum_digests"] = [
        str(i.get("exacontinuum_digest") or "") for i in institutions
    ]
    receipt["zettacontinuum_digest"] = _sha256_json(_zettacontinuum_digest_payload(receipt))
    atomic_write_json(zettacontinuum_dir / "zettacontinuum.json", receipt)
    atomic_write_json(
        zettacontinuum_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "zettacontinuum_id": receipt["zettacontinuum_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "zettacontinuum_met": receipt["zettacontinuum_met"],
            "exacontinuums_admitted": receipt["exacontinuums_admitted"],
            "exacontinuums_met_count": receipt["exacontinuums_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "charter_expansion_count": receipt["charter_expansion_count"],
            "max_active_exacontinuums": receipt["max_active_exacontinuums"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "zettacontinuum_digest": receipt["zettacontinuum_digest"],
            "resumed": resumed,
        },
    )

    write_zettacontinuum_state(
        zettacontinuum_dir,
        _state_payload(
            zettacontinuum_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            exacontinuum_states=exacontinuum_states,
            exacontinuum_digests=receipt["exacontinuum_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            zettacontinuum_goal=zettacontinuum_goal,
            max_active_exacontinuums=active_max,
            admissions=admissions,
            charter_expansions=charter_expansions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "zettacontinuum_dir": str(zettacontinuum_dir),
        "zettacontinuum_digest": receipt["zettacontinuum_digest"],
        "zettacontinuum_id": lid,
        "round_count": len(institutions),
        "exacontinuum_digests": list(receipt["exacontinuum_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "zettacontinuum_met": zettacontinuum_met,
        "exacontinuums_admitted": len(exacontinuum_states),
        "exacontinuums_met_count": exacontinuums_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_exacontinuums": active_max,
        "admissions": admissions,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": list(receipt["charter_expanded_ids"]),
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "exacontinuum_states": exacontinuum_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "exacontinuums": institutions,
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
    return ee._program_slot(
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
    return ee._inst_slot(
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
    return ee._commonwealth_slot(
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
    return ee._domain_slot(
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
    """Build a hermetic realm slot for an continuum charter."""
    return ee._realm_slot(
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
    """Build a hermetic nested empire slot for a continuum charter."""
    return ee._empire_slot(
        empire_id,
        priority=priority,
        realms=realms,
        institutions=institutions,
        max_rounds=max_rounds,
        empire_goal=empire_goal,
        max_active_realms=max_active_realms,
    )


def _exacontinuum_slot(
    exacontinuum_id: str,
    *,
    priority: int = 0,
    petacontinuums: Sequence[dict[str, Any]] | None = None,
    megacontinuums: Sequence[dict[str, Any]] | None = None,
    ultracontinuums: Sequence[dict[str, Any]] | None = None,
    multiverses: Sequence[dict[str, Any]] | None = None,
    cosmoses: Sequence[dict[str, Any]] | None = None,
    civilizations: Sequence[dict[str, Any]] | None = None,
    empires: Sequence[dict[str, Any]] | None = None,
    realms: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    exacontinuum_goal: str = "all_petacontinuums_met",
    max_active_petacontinuums: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic zettacontinuum charter exacontinuum slot.

    Prefer ``petacontinuums=`` (nested giga slots for the exacontinuum plane).
    ``institutions=`` wrap a single auto giga with mega nesting underneath.
    """
    nested: list[dict[str, Any]]
    if petacontinuums is not None:
        nested = list(petacontinuums)
    elif megacontinuums is not None:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                megacontinuums=list(megacontinuums),
                max_rounds=max_rounds,
            )
        ]
    elif ultracontinuums is not None:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                ultracontinuums=list(ultracontinuums),
                max_rounds=max_rounds,
            )
        ]
    elif multiverses is not None:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                multiverses=list(multiverses),
                max_rounds=max_rounds,
            )
        ]
    elif cosmoses is not None:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                cosmoses=list(cosmoses),
                max_rounds=max_rounds,
            )
        ]
    elif civilizations is not None:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                civilizations=list(civilizations),
                max_rounds=max_rounds,
            )
        ]
    elif empires is not None:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                empires=list(empires),
                max_rounds=max_rounds,
            )
        ]
    elif realms is not None:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                realms=list(realms),
                max_rounds=max_rounds,
            )
        ]
    elif institutions:
        nested = [
            ee._petacontinuum_slot(
                f"{exacontinuum_id[:1]}g",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "exacontinuum_id": exacontinuum_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "exacontinuum_goal": exacontinuum_goal,
        "max_active_petacontinuums": max_active_petacontinuums,
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


def builtin_upstream_zettacontinuum_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-exacontinuum zettacontinuum plane (no network).

    Uses an injected fast ``exacontinuum_runner`` so the outer plane constitution
    (admit/schedule/federate/retire/expand/resume/seal/terminal reopen) is fully
    exercised without paying full nested giga→…→wave wall-clock cost. Nested
    giga receipts are still written and verified through the real tera seal path.
    """
    scratch = _proof_scratch()
    try:
        # Per-exacontinuum progress for budget/resume/terminal multi-call realism.
        _progress: dict[str, dict[str, Any]] = {}

        def _walk_program_targets(node: Mapping[str, Any], bag: list[tuple[str, str, str]], *, include_deferred: bool) -> None:
            for pslot in list(node.get("charter") or []) + list(node.get("programs") or []):
                if not isinstance(pslot, Mapping):
                    continue
                if pslot.get("program_id") or pslot.get("initial_targets") or pslot.get("surface_charter"):
                    for tgt in list(pslot.get("initial_targets") or []) + list(pslot.get("surface_charter") or []):
                        if not isinstance(tgt, Mapping):
                            continue
                        name = str(tgt.get("name") or "")
                        ver = str(tgt.get("version") or "")
                        for d in list(tgt.get("defects") or []):
                            if isinstance(d, Mapping):
                                bag.append((name, ver, str(d.get("id") or "")))
                    if include_deferred:
                        for tgt in list(pslot.get("deferred_targets") or []):
                            if not isinstance(tgt, Mapping):
                                continue
                            name = str(tgt.get("name") or "")
                            ver = str(tgt.get("version") or "")
                            for d in list(tgt.get("defects") or []):
                                if isinstance(d, Mapping):
                                    bag.append((name, ver, str(d.get("id") or "")))
                else:
                    _walk_program_targets(pslot, bag, include_deferred=include_deferred)
            for key in (
                "petacontinuums",
                "megacontinuums",
                "ultracontinuums",
                "continuums",
                "omniverses",
                "multiverses",
                "cosmoses",
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
                        _walk_program_targets(child, bag, include_deferred=include_deferred)

        def _collect_keys(charter: Sequence[Mapping[str, Any]] | None, *, include_deferred: bool) -> list[tuple[str, str, str]]:
            bag: list[tuple[str, str, str]] = []
            for slot in list(charter or []):
                if isinstance(slot, Mapping):
                    _walk_program_targets(slot, bag, include_deferred=include_deferred)
            # de-dupe preserve order
            seen: set[tuple[str, str, str]] = set()
            out: list[tuple[str, str, str]] = []
            for k in bag:
                if k[0] and k[2] and k not in seen:
                    seen.add(k)
                    out.append(k)
            return out

        def _fast_mega_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            mid = str(kwargs.get("exacontinuum_id") or "m")
            nested_charter = ee.normalize_exacontinuum_charter(kwargs.get("charter"))
            if kwargs.get("resume_dir") is not None and not nested_charter:
                state_path = Path(str(kwargs["resume_dir"])) / "exacontinuum_state.json"
                if state_path.is_file():
                    st = json.loads(state_path.read_text(encoding="utf-8"))
                    nested_charter = ee.normalize_exacontinuum_charter(st.get("charter"))
                    mid = str(st.get("exacontinuum_id") or mid)

            goal = str(kwargs.get("exacontinuum_goal") or "all_petacontinuums_met")
            # terminal_coverage at parent may force reopen; expose deferred only after first meet.
            st = _progress.setdefault(
                mid,
                {"done": set(), "calls": 0, "dispatched": 0, "dispatched_ok": 0},
            )
            st["calls"] = int(st["calls"]) + 1
            include_deferred = st["calls"] > 1 or goal == "all_petacontinuums_met"
            # For first call under parent terminal-style partial: only initials.
            if st["calls"] == 1 and mid.startswith("t"):
                include_deferred = False
            keys = _collect_keys(nested_charter, include_deferred=include_deferred)
            all_keys = _collect_keys(nested_charter, include_deferred=True)
            remaining = [k for k in keys if k not in st["done"]]
            if kwargs.get("dispatch") is False:
                take = []
            else:
                budget = kwargs.get("dispatch_budget")
                if budget is None:
                    take = list(remaining)
                else:
                    take = remaining[: max(0, int(budget))]
            for k in take:
                st["done"].add(k)
            n = len(take)
            st["dispatched"] = int(st["dispatched"]) + n
            st["dispatched_ok"] = int(st["dispatched_ok"]) + n

            covered_keys = [k for k in all_keys if k in st["done"]]
            # Premature met when initials done but deferred remain (terminal reopen path).
            premature = bool(all_keys) and set(keys).issubset(st["done"]) and set(all_keys) - set(keys)
            mega_met = set(all_keys).issubset(st["done"]) if all_keys else True
            if premature and not mega_met:
                # Nested plane may report met before deferred surfaces expand.
                report_met = True
            else:
                report_met = mega_met

            entries = [
                {
                    "name": n_,
                    "version": v_,
                    "defect_id": d_,
                    "outcome": "impact_merged",
                    "impact_digest": "c" * 64,
                    "ok": True,
                }
                for n_, v_, d_ in covered_keys
            ]
            portfolio = uf._proof_portfolio(entries)
            petacontinuum_states = [
                {
                    "petacontinuum_id": str(
                        s.get("petacontinuum_id") or s.get("id") or "g"
                    ),
                    "petacontinuum_met": report_met,
                    "charter": list(s.get("charter") or []),
                    "portfolio": portfolio,
                    "inventory_keys": list(all_keys),  # required surface incl. deferred
                }
                for s in nested_charter
                if isinstance(s, Mapping)
            ] or [
                {
                    "petacontinuum_id": "g0",
                    "petacontinuum_met": report_met,
                    "charter": list(nested_charter),
                    "portfolio": portfolio,
                    "inventory_keys": list(all_keys),  # required surface incl. deferred
                }
            ]
            required = len(all_keys)
            covered_n = len(covered_keys)
            ratio = (covered_n / required) if required else 1.0
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "exacontinuum_met" if report_met else "exacontinuum_completed",
                "stop_reason": "exacontinuum_met" if report_met else "dispatch_budget",
                "exacontinuum_id": mid,
                "exacontinuum_goal": str(
                    kwargs.get("exacontinuum_goal") or "all_petacontinuums_met"
                ),
                "max_rounds": int(kwargs.get("max_rounds") or 6),
                "max_active_petacontinuums": kwargs.get("max_active_petacontinuums"),
                "dispatch_budget": kwargs.get("dispatch_budget"),
                "exacontinuum_met": report_met,
                "total_dispatched": st["dispatched"],
                "total_dispatched_ok": st["dispatched_ok"],
                "petacontinuums": [],
                "petacontinuum_digests": [],
                "petacontinuums_admitted": max(1, len(nested_charter) or 1),
                "petacontinuums_met_count": (
                    max(1, len(nested_charter) or 1) if report_met else 0
                ),
                "admission_count": 0,
                "pending_remaining": [],
                "charter_expansion_count": 0,
                "charter_expanded_ids": [],
                "round_count": st["calls"],
                "portfolio_start_digest": None,
                "portfolio_end_digest": portfolio.get("portfolio_digest"),
                "federated_portfolio": portfolio,
                "petacontinuum_states": petacontinuum_states,
                "coverage_end": {
                    "required": required,
                    "covered": covered_n,
                    "met": covered_n == required and required > 0,
                    "coverage_ratio": ratio,
                    "open_or_missing": [
                        {"name": n_, "version": v_, "defect_id": d_}
                        for n_, v_, d_ in all_keys
                        if (n_, v_, d_) not in st["done"]
                    ],
                },
                "roi_summary": {
                    "rounds": st["calls"],
                    "total_dispatched_ok": st["dispatched_ok"],
                },
            }
            receipt["exacontinuum_digest"] = _sha256_json(
                ee._exacontinuum_digest_payload(receipt)
            )
            digest = receipt["exacontinuum_digest"]
            atomic_write_json(out / "exacontinuum.json", receipt)
            atomic_write_json(
                out / "exacontinuum_state.json",
                {
                    "exacontinuum_id": mid,
                    "round_count": st["calls"],
                    "total_dispatched": st["dispatched"],
                    "total_dispatched_ok": st["dispatched_ok"],
                    "federated_portfolio": portfolio,
                    "petacontinuum_states": petacontinuum_states,
                    "stop_reason": receipt["stop_reason"],
                    "charter": nested_charter,
                    "exacontinuum_met": report_met,
                },
            )
            return {
                "ok": True,
                "verdict": receipt["verdict"],
                "stop_reason": receipt["stop_reason"],
                "exacontinuum_dir": str(out),
                "exacontinuum_digest": digest,
                "exacontinuum_id": mid,
                "total_dispatched": st["dispatched"],
                "total_dispatched_ok": st["dispatched_ok"],
                "exacontinuum_met": report_met,
                "petacontinuums_admitted": receipt["petacontinuums_admitted"],
                "petacontinuums_met_count": receipt["petacontinuums_met_count"],
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "petacontinuum_states": petacontinuum_states,
                "used_skill_route_discovery": False,
            }

        def _slot(mid: str, *, priority: int = 1, initial: Sequence[tuple[str, str, str]], deferred: Sequence[tuple[str, str, str]] = (), max_rounds: int = 4) -> dict[str, Any]:
            return _exacontinuum_slot(
                mid,
                priority=priority,
                institutions=[
                    _inst_slot(
                        f"i{mid}",
                        programs=[
                            _program_slot(
                                f"p{mid}",
                                initial=list(initial),
                                deferred=list(deferred),
                            )
                        ],
                        max_rounds=max_rounds,
                    )
                ],
                max_rounds=max_rounds,
            )

        # --- main multi-mega ---
        charter = [
            _slot("a", priority=2, initial=[("alpha", "1.0.0", "alpha-dos")]),
            _slot(
                "b",
                priority=1,
                initial=[("beta", "2.0.0", "beta-xss")],
                deferred=[("gamma", "3.0.0", "gamma-rce")],
            ),
        ]
        confed = run_zettacontinuum(
            charter=charter,
            max_rounds=8,
            dispatch_budget=12,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="all_exacontinuums_met",
            out_root=scratch / "m",
        )
        multi_zettacontinuum_ok = (
            confed["ok"]
            and confed["zettacontinuum_met"] is True
            and confed["stop_reason"] == "zettacontinuum_met"
            and confed["exacontinuums_admitted"] == 2
            and confed["exacontinuums_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
        )
        scheduled_ids = {
            i.get("exacontinuum_id")
            for i in (confed.get("exacontinuums") or [])
        }
        multi_zettacontinuum_scheduled = multi_zettacontinuum_ok and scheduled_ids >= {"a", "b"}

        verified = verify_zettacontinuum_receipt(Path(confed["zettacontinuum_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed["round_count"]

        confed_path = Path(confed["zettacontinuum_dir"]) / "zettacontinuum.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["zettacontinuum_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_zettacontinuum_receipt(Path(confed["zettacontinuum_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "zettacontinuum_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop
        _progress.clear()
        budgeted = run_zettacontinuum(
            charter=[
                _slot("b1", initial=[("d1", "1.0.0", "d1-1")]),
                _slot("b2", initial=[("d2", "1.0.0", "d2-1")]),
            ],
            max_rounds=6,
            dispatch_budget=1,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="none",
            out_root=scratch / "g",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit (zero dispatch child)
        def _premet_runner(**kwargs: Any) -> dict[str, Any]:
            out = Path(kwargs["out_root"])
            out.mkdir(parents=True, exist_ok=True)
            nested_charter = ee.normalize_exacontinuum_charter(kwargs.get("charter"))
            keys = _collect_keys(nested_charter, include_deferred=True)
            entries = [
                {
                    "name": n_,
                    "version": v_,
                    "defect_id": d_,
                    "outcome": "impact_merged",
                    "impact_digest": "c" * 64,
                    "ok": True,
                }
                for n_, v_, d_ in keys
            ]
            portfolio = uf._proof_portfolio(entries)
            receipt = {
                "schema_version": 1,
                "ok": True,
                "verdict": "exacontinuum_met",
                "stop_reason": "exacontinuum_met",
                "exacontinuum_id": kwargs.get("exacontinuum_id"),
                "exacontinuum_goal": "all_petacontinuums_met",
                "max_rounds": 1,
                "max_active_petacontinuums": None,
                "dispatch_budget": None,
                "exacontinuum_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "petacontinuums": [],
                "petacontinuum_digests": [],
                "petacontinuums_admitted": max(1, len(nested_charter) or 1),
                "petacontinuums_met_count": max(1, len(nested_charter) or 1),
                "admission_count": 0,
                "pending_remaining": [],
                "charter_expansion_count": 0,
                "charter_expanded_ids": [],
                "round_count": 0,
                "portfolio_start_digest": None,
                "portfolio_end_digest": portfolio.get("portfolio_digest"),
                "federated_portfolio": portfolio,
                "petacontinuum_states": [
                    {
                        "petacontinuum_id": "g",
                        "petacontinuum_met": True,
                        "inventory_keys": list(keys),
                        "portfolio": portfolio,
                    }
                ],
                "coverage_end": {
                    "required": len(keys),
                    "covered": len(keys),
                    "met": True,
                    "coverage_ratio": 1.0,
                    "open_or_missing": [],
                },
                "roi_summary": {"rounds": 0, "total_dispatched_ok": 0},
            }
            receipt["exacontinuum_digest"] = _sha256_json(
                ee._exacontinuum_digest_payload(receipt)
            )
            digest = receipt["exacontinuum_digest"]
            atomic_write_json(out / "exacontinuum.json", receipt)
            atomic_write_json(
                out / "exacontinuum_state.json",
                {
                    "exacontinuum_id": kwargs.get("exacontinuum_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "petacontinuum_states": receipt["petacontinuum_states"],
                    "stop_reason": "exacontinuum_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "exacontinuum_met",
                "stop_reason": "exacontinuum_met",
                "exacontinuum_dir": str(out),
                "exacontinuum_digest": digest,
                "exacontinuum_id": kwargs.get("exacontinuum_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "exacontinuum_met": True,
                "petacontinuums_admitted": receipt["petacontinuums_admitted"],
                "petacontinuums_met_count": receipt["petacontinuums_met_count"],
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "petacontinuum_states": receipt["petacontinuum_states"],
                "used_skill_route_discovery": False,
            }

        pre_met = run_zettacontinuum(
            charter=[_slot("om", initial=[("om", "9.0.0", "omega-merged")])],
            max_rounds=3,
            dispatch=True,
            exacontinuum_runner=_premet_runner,
            zettacontinuum_goal="all_exacontinuums_met",
            out_root=scratch / "p",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["zettacontinuum_met"] is True
            and pre_met["stop_reason"] == "zettacontinuum_met"
            and pre_met["exacontinuums_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        ranked = run_zettacontinuum(
            charter=[
                _slot("ra", initial=[("r1", "1.0.0", "r1-1")]),
                _slot("rb", initial=[("r2", "1.0.0", "r2-1")]),
            ],
            max_rounds=3,
            dispatch=False,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="none",
            out_root=scratch / "k",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "zettacontinuum_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        empty_refused = False
        try:
            run_zettacontinuum(
                charter=[],
                dispatch=False,
                zettacontinuum_goal="none",
                out_root=scratch / "z",
            )
        except ZettacontinuumRefused as exc:
            empty_refused = exc.verdict in {
                "zettacontinuum_empty",
                "zettacontinuum_invalid",
            }

        _progress.clear()
        custom = run_zettacontinuum(
            charter=[
                _slot("c1", initial=[("c1", "1.0.0", "c1-1")]),
                _slot("c2", initial=[("c2", "1.0.0", "c2-1")]),
            ],
            max_rounds=6,
            dispatch_budget=8,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="none",
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

        _progress.clear()
        partial = run_zettacontinuum(
            charter=[
                _slot("z1", priority=2, initial=[("zeta", "1.0.0", "zeta-1")]),
                _slot("z2", priority=1, initial=[("eta", "1.0.0", "eta-1")]),
            ],
            max_rounds=1,
            dispatch_budget=1,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="none",
            zettacontinuum_id="rcp",
            out_root=scratch / "a",
        )
        state_path = Path(partial["zettacontinuum_dir"]) / "zettacontinuum_state.json"
        state_exists = state_path.is_file()
        resumed = run_zettacontinuum(
            resume_dir=Path(partial["zettacontinuum_dir"]),
            max_rounds=4,
            dispatch_budget=4,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="none",
            out_root=scratch / "r",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["zettacontinuum_id"] == "rcp"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_continuum"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_continuum") or {}) >= 2
        )

        first_cw = (confed.get("exacontinuums") or [{}])[0].get("exacontinuum_id")
        priority_ok = first_cw == "a"

        fed_portfolio = confed.get("coverage_end") or {}
        federation_ok = multi_zettacontinuum_ok and (
            float(fed_portfolio.get("coverage_ratio") or 0) == 1.0
            and int(fed_portfolio.get("required") or 0) >= 3
        )

        _progress.clear()
        deferred = run_zettacontinuum(
            charter=[
                _slot("da", priority=3, initial=[("da", "1.0.0", "da-1")], max_rounds=3),
                _slot("db", priority=2, initial=[("db", "1.0.0", "db-1")], max_rounds=3),
                _slot("dc", priority=1, initial=[("dc", "1.0.0", "dc-1")], max_rounds=3),
            ],
            max_rounds=8,
            dispatch_budget=6,
            max_active_exacontinuums=1,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="all_exacontinuums_met",
            out_root=scratch / "d",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("exacontinuum_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["zettacontinuum_met"] is True
            and deferred["exacontinuums_admitted"] == 3
            and deferred["exacontinuums_met_count"] == 3
            and deferred.get("max_active_exacontinuums") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        _progress.clear()
        expand_runner = make_zettacontinuum_charter_expand(
            [_slot("xg", priority=1, initial=[("xg", "1.0.0", "xg-1")], max_rounds=3)],
            max_slots_per_expand=1,
        )
        expanded = run_zettacontinuum(
            charter=[_slot("xe", priority=2, initial=[("xe", "1.0.0", "xe-1")], max_rounds=3)],
            max_rounds=6,
            dispatch_budget=6,
            max_active_exacontinuums=1,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            charter_expand=expand_runner,
            zettacontinuum_goal="all_exacontinuums_met",
            out_root=scratch / "x",
        )
        expand_ok = (
            expanded["ok"]
            and expanded["zettacontinuum_met"] is True
            and expanded["exacontinuums_admitted"] == 2
            and expanded["exacontinuums_met_count"] == 2
            and int(expanded.get("charter_expansion_count") or 0) >= 1
            and "xg" in set(expanded.get("charter_expanded_ids") or [])
            and not (expanded.get("pending_remaining") or [])
        )

        merged = merge_zettacontinuum_charter(
            [_slot("m1", initial=[("m", "1.0.0", "m-1")])],
            [
                _slot("m1", initial=[("m2", "1.0.0", "m2-1")]),
                _slot("m2", initial=[("n", "1.0.0", "n-1")]),
            ],
        )
        merge_ok = [s["exacontinuum_id"] for s in merged] == ["m1", "m2"]

        # Terminal coverage with premature-met + deferred reopen (ids start with t)
        _progress.clear()
        terminal = run_zettacontinuum(
            charter=[
                _slot("t1", priority=2, initial=[("tau", "1.0.0", "tau-dos")]),
                _slot(
                    "t2",
                    priority=1,
                    initial=[("upsilon", "2.0.0", "ups-xss")],
                    deferred=[("phi", "3.0.0", "phi-rce")],
                ),
            ],
            max_rounds=10,
            dispatch_budget=12,
            dispatch=True,
            exacontinuum_runner=_fast_mega_runner,
            zettacontinuum_goal="terminal_coverage",
            out_root=scratch / "tc",
        )
        cov_end = terminal.get("coverage_end") or {}
        terminal_ok = (
            terminal["ok"]
            and terminal["zettacontinuum_met"] is True
            and terminal["stop_reason"] == "zettacontinuum_met"
            and float(cov_end.get("coverage_ratio") or 0) == 1.0
            and int(cov_end.get("required") or 0) >= 3
            and bool(cov_end.get("met"))
            and not (terminal.get("pending_remaining") or [])
            and terminal["exacontinuums_admitted"] == 2
            and terminal["total_dispatched_ok"] >= 3
        )

        ok = all(
            [
                multi_zettacontinuum_ok,
                multi_zettacontinuum_scheduled,
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
                terminal_ok,
            ]
        )
        return {
            "ok": ok,
            "zettacontinuum_met": multi_zettacontinuum_ok,
            "multi_zettacontinuum_progressed": multi_zettacontinuum_scheduled,
            "federation_coverage": federation_ok,
            "priority_scheduling": priority_ok,
            "deferred_admission": deferred_ok,
            "charter_expand": expand_ok,
            "charter_merge": merge_ok,
            "terminal_coverage_goal": terminal_ok,
            "seal_verified": seal_ok,
            "tamper_detected": tamper_detected,
            "budget_stops": budget_ok,
            "premet_short_circuits": premet_ok,
            "rank_only": rank_only_ok,
            "empty_refused": empty_refused,
            "custom_stop": custom_ok,
            "durable_resume": resume_ok,
            "roi_scored": roi_ok,
            "zettacontinuum_digest": confed.get("zettacontinuum_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "exacontinuums_admitted": confed.get("exacontinuums_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_zettacontinuum_ok": multi_zettacontinuum_ok,
                "multi_zettacontinuum_scheduled": multi_zettacontinuum_scheduled,
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
                "terminal_ok": terminal_ok,
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
        result = verify_zettacontinuum_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_zettacontinuum_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
