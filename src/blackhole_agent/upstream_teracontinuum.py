"""Upstream teracontinuum plane: multi-gigacontinuum durable stewardship teracontinuum.

The gigacontinuum plane (``upstream_gigacontinuum``) closes multi-continuum unions *within one
gigacontinuum*. It does not:

1. chain multiple independent gigacontinuums under a durable teracontinuum constitution;
2. allocate a shared global dispatch budget across gigacontinuums by ROI;
3. admit/retire gigacontinuum slots from an teracontinuum charter over time
   (deferred admission under a concurrent-active cap);
4. grow the teracontinuum charter mid-run via ``charter_expand`` (constitution
   growth beyond the initial charter, not just deferred admission of a fixed set);
5. federate multi-gigacontinuum portfolio coverage into one teracontinuum world-model;
6. persist teracontinuum state so a later process can resume the union;
7. seal a multi-gigacontinuum teracontinuum chronicle linking gigacontinuum digests.

The teracontinuum plane closes that outer multi-gigacontinuum loop:

1. **admit** — materialize gigacontinuum slots from a durable teracontinuum charter
   (each slot owns a nested continuum charter). When ``max_active_gigacontinuums``
   is set, only that many *unmet* gigacontinuums are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (teracontinuum constitution growth over time);
2. **schedule** — pick the next open gigacontinuum by priority and historical ROI;
3. **gigacontinuum** — call the gigacontinuum plane (injected ``gigacontinuum_runner``;
   default ``run_gigacontinuum``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-gigacontinuum portfolios into one teracontinuum world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark gigacontinuums met when their gigacontinuum_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **expand** — optional ``charter_expand`` may append new gigacontinuum slots when
   the active charter has no pending work and all admitted gigacontinuums are met,
   so the teracontinuum constitution can grow after start (not only defer a fixed charter);
7. **persist** — write ``teracontinuum_state.json`` after every gigacontinuum round so a
   later ``run_teracontinuum(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
8. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across gigacontinuums
   - teracontinuum goal met (``all_gigacontinuums_met``: every *admitted*
     gigacontinuum is met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

9. **seal** — write an teracontinuum receipt under
   ``artifacts/upstream-teracontinuum/`` with sha256 digests of every
   gigacontinuum, portfolio federation, admission history, ROI history, stop
   reason, and an teracontinuum chain digest; ``verify_teracontinuum_receipt``
   re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is teracontinuum-level direction
over the gigacontinuum plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_gigacontinuum as gg
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-teracontinuum"

TERMINAL_SUCCESS_OUTCOMES = gg.TERMINAL_SUCCESS_OUTCOMES


class TeracontinuumRefused(Exception):
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


def normalize_teracontinuum_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a teracontinuum charter into deterministic continuum slots.

    Each slot is::

        {
          "gigacontinuum_id": str,
          "priority": int,
          "charter": [...multiverse slots...],  # nested continuum charter
          "max_active_megacontinuums": int | None,
          "max_rounds": int,
          "gigacontinuum_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        gigacontinuum_id = str(
            raw.get("gigacontinuum_id") or raw.get("id") or ""
        ).strip()
        if not gigacontinuum_id or gigacontinuum_id in seen:
            continue
        seen.add(gigacontinuum_id)

        nested = gg.normalize_gigacontinuum_charter(
            raw.get("charter")
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

        max_active_megacontinuums = raw.get("max_active_megacontinuums")
        if max_active_megacontinuums is None:
            max_active_megacontinuums = raw.get("max_active_continuums")
        if max_active_megacontinuums is None:
            max_active_megacontinuums = raw.get("max_active_civilizations")
        if max_active_megacontinuums is not None:
            max_active_megacontinuums = max(1, int(max_active_megacontinuums))

        out.append(
            {
                "gigacontinuum_id": gigacontinuum_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_megacontinuums": max_active_megacontinuums,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "gigacontinuum_goal": str(
                    raw.get("gigacontinuum_goal") or "all_megacontinuums_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_gigacontinuum"),
            }
        )
    return out


def admit_gigacontinuum_slot(
    *,
    teracontinuum_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with gigacontinuum_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    gigacontinuum_id = str(slot.get("gigacontinuum_id") or "")
    if not gigacontinuum_id:
        raise TeracontinuumRefused("teracontinuum_invalid", "slot missing gigacontinuum_id")

    gigacontinuum_root = Path(teracontinuum_dir) / "gigacontinuums" / gigacontinuum_id
    gigacontinuum_root.mkdir(parents=True, exist_ok=True)

    nested_charter = gg.normalize_gigacontinuum_charter(slot.get("charter"))
    if not nested_charter:
        raise TeracontinuumRefused(
            "teracontinuum_invalid",
            f"continuum slot {gigacontinuum_id!r} has empty nested charter",
        )

    max_active_megacontinuums = slot.get("max_active_megacontinuums")
    if max_active_megacontinuums is None:
        max_active_megacontinuums = slot.get("max_active_continuums")
    if max_active_megacontinuums is None:
        max_active_megacontinuums = slot.get("max_active_civilizations")

    return {
        "gigacontinuum_id": gigacontinuum_id,
        "gigacontinuum_root": str(gigacontinuum_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_megacontinuums": max_active_megacontinuums,
        "max_rounds": int(slot.get("max_rounds") or 6),
        "gigacontinuum_goal": str(slot.get("gigacontinuum_goal") or "all_megacontinuums_met"),
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
        "source": "teracontinuum_federation",
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


def teracontinuum_terminal_coverage(
    *,
    gigacontinuum_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Coverage across gigacontinuum->ultracontinuum->continuum->...->program."""
    ultracontinuum_states: list[dict[str, Any]] = []
    for uc in gigacontinuum_states:
        if not isinstance(uc, Mapping):
            continue
        nested = list(uc.get("megacontinuum_states") or []) or list(uc.get("ultracontinuum_states") or [])
        if nested:
            for hc in nested:
                if isinstance(hc, Mapping):
                    ultracontinuum_states.append(dict(hc))
            continue
        # Pre-run: gigacontinuum charter is a list of ultracontinuum slots.
        for cslot in list(uc.get("charter") or []) + list(
            uc.get("megacontinuums") or []
        ) + list(uc.get("ultracontinuums") or []) + list(uc.get("continuums") or []) + list(uc.get("omniverses") or []) + list(
            uc.get("multiverses") or []
        ):
            if isinstance(cslot, Mapping):
                ultracontinuum_states.append(dict(cslot))
        if not nested and not list(uc.get("charter") or []):
            for cont in list(uc.get("continuum_states") or []) + list(
                uc.get("omniverse_states") or []
            ) + list(uc.get("multiverse_states") or []) + list(
                uc.get("cosmos_states") or []
            ) + list(uc.get("civilization_states") or []):
                if isinstance(cont, Mapping):
                    ultracontinuum_states.append(dict(cont))
        for raw in list(uc.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                ultracontinuum_states.append(
                    {
                        "inventory_keys": [
                            (str(raw[0]), str(raw[1]), str(raw[2]))
                        ]
                    }
                )
            elif isinstance(raw, Mapping):
                ultracontinuum_states.append({"inventory_keys": [raw]})
    return gg.gigacontinuum_terminal_coverage(
        megacontinuum_states=ultracontinuum_states,
        federated_portfolio=federated_portfolio,
    )


def gigacontinuums_all_met(gigacontinuum_states: Sequence[Mapping[str, Any]]) -> bool:
    if not gigacontinuum_states:
        return False
    return all(bool(ist.get("gigacontinuum_met")) for ist in gigacontinuum_states)


def open_unmet_count(gigacontinuum_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet continuum_met."""
    return sum(1 for ist in gigacontinuum_states if not ist.get("gigacontinuum_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    gigacontinuum_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then gigacontinuum_id-asc."""
    known = {str(ist.get("gigacontinuum_id") or "") for ist in gigacontinuum_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("gigacontinuum_id") or "")
        and str(slot.get("gigacontinuum_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("gigacontinuum_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    gigacontinuum_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    teracontinuum_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if teracontinuum_goal == "none":
        return False
    if teracontinuum_goal == "terminal_coverage":
        cov = teracontinuum_terminal_coverage(
            gigacontinuum_states=gigacontinuum_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, gigacontinuum_states
        )
    if teracontinuum_goal == "all_gigacontinuums_met":
        if not gigacontinuum_states:
            return False
        if pending_charter_slots(charter, gigacontinuum_states):
            return False
        return gigacontinuums_all_met(gigacontinuum_states)
    return False


def reopen_incomplete_gigacontinuums(
    gigacontinuum_states: list[dict[str, Any]],
    *,
    federated_portfolio: Mapping[str, Any] | None,
) -> list[str]:
    """Clear ``continuum_met`` on children still short of terminal coverage.

    Nested gigacontinuums can retire after only partial surface work (e.g. before
    deferred program targets expand). Under a ``terminal_coverage`` teracontinuum
    goal those children must re-run until federated inventory is fully
    terminal-success. Returns the reopened ``gigacontinuum_id`` list.
    """
    cov = teracontinuum_terminal_coverage(
        gigacontinuum_states=gigacontinuum_states,
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
    for i, ist in enumerate(gigacontinuum_states):
        if not ist.get("gigacontinuum_met"):
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
        for mv in list(ist.get("megacontinuum_states") or []) + list(
            ist.get("ultracontinuum_states") or []
        ) + list(ist.get("continuum_states") or []) + list(
            ist.get("omniverse_states") or []
        ) + list(ist.get("multiverse_states") or []) + list(
            ist.get("charter") or []
        ):
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
        updated["gigacontinuum_met"] = False
        gigacontinuum_states[i] = updated
        reopened.append(str(updated.get("gigacontinuum_id") or ""))
    return [r for r in reopened if r]


def merge_teracontinuum_charter(
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge additional realm slots into a continuum charter.

    Existing ``gigacontinuum_id`` values win (additions with the same id are
    ignored). Returns a fully re-normalized charter so nested confederation
    charters stay deterministic.
    """
    base = normalize_teracontinuum_charter(existing)
    if not additions:
        return base
    known = {str(s.get("gigacontinuum_id") or "") for s in base}
    merged: list[Mapping[str, Any]] = list(base)
    for raw in additions:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get("gigacontinuum_id") or raw.get("id") or "").strip()
        if not cid or cid in known:
            continue
        known.add(cid)
        merged.append(raw)
    return normalize_teracontinuum_charter(merged)


def make_teracontinuum_charter_expand(
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
    pending_growth = normalize_teracontinuum_charter(growth)
    applied_ids: set[str] = set(str(x) for x in (applied or []))
    state: dict[str, Any] = {
        "applied": applied_ids,
        "growth": pending_growth,
        "max_slots_per_expand": max(1, int(max_slots_per_expand)),
    }

    def _runner(
        *,
        active_charter: Sequence[Mapping[str, Any]],
        gigacontinuum_states: Sequence[Mapping[str, Any]],
        round_index: int,
        roi_history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        remaining = [
            s
            for s in pending_growth
            if str(s.get("gigacontinuum_id") or "") not in applied_ids
            and str(s.get("gigacontinuum_id") or "")
            not in {str(x.get("gigacontinuum_id") or "") for x in active_charter}
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
            applied_ids.add(str(s.get("gigacontinuum_id") or ""))
        merged = merge_teracontinuum_charter(active_charter, take)
        state["applied"] = applied_ids
        return {
            "expanded": True,
            "added": [str(s.get("gigacontinuum_id") or "") for s in take],
            "charter": merged,
            "detail": "charter_growth_applied",
            "round_index": round_index,
            "realms_met": gigacontinuums_all_met(gigacontinuum_states),
        }

    _runner.charter_state = state  # type: ignore[attr-defined]
    return _runner


def admit_pending_slots(
    *,
    teracontinuum_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    gigacontinuum_states: list[dict[str, Any]],
    max_active_gigacontinuums: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_gigacontinuums`` caps *unmet* concurrent realms. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``gigacontinuum_states``).
    """
    pending = pending_charter_slots(charter, gigacontinuum_states)
    if not pending:
        return []

    open_n = open_unmet_count(gigacontinuum_states)
    if max_active_gigacontinuums is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_gigacontinuums) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_gigacontinuum_slot(teracontinuum_dir=teracontinuum_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        gigacontinuum_states.append(
            {
                "gigacontinuum_id": admission["gigacontinuum_id"],
                "gigacontinuum_root": admission["gigacontinuum_root"],
                "charter": admission["charter"],
                "max_active_megacontinuums": admission.get("max_active_megacontinuums"),
                "max_rounds": admission["max_rounds"],
                "gigacontinuum_goal": admission["gigacontinuum_goal"],
                "priority": admission["priority"],
                "gigacontinuum_met": False,
                "last_gigacontinuum_dir": None,
                "last_gigacontinuum_digest": None,
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


def score_gigacontinuum_roi(
    *,
    round_index: int,
    gigacontinuum_id: str,
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
        "gigacontinuum_id": gigacontinuum_id,
        "stop_reason": continuum_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "gigacontinuum_met": bool(continuum_result.get("gigacontinuum_met")),
        "continuum_digest": continuum_result.get("gigacontinuum_digest"),
        "continuums_admitted": int(
            continuum_result.get("megacontinuums_admitted")
            or continuum_result.get("ultracontinuums_admitted")
            or continuum_result.get("gigacontinuums_admitted")
            or continuum_result.get("continuums_admitted")
            or continuum_result.get("omniverses_admitted")
            or continuum_result.get("multiverses_admitted")
            or continuum_result.get("empires_admitted")
            or continuum_result.get("realms_admitted")
            or 0
        ),
        "continuums_met_count": int(
            continuum_result.get("megacontinuums_met_count")
            or continuum_result.get("ultracontinuums_met_count")
            or continuum_result.get("gigacontinuums_met_count")
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
        iid = str(r.get("gigacontinuum_id") or "")
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


def select_next_gigacontinuum(
    gigacontinuum_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable gigacontinuum_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in gigacontinuum_states if not ist.get("gigacontinuum_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_continuum = summary.get("by_continuum") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("gigacontinuum_id") or "")
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


def allocate_gigacontinuum_budget(
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
        str(selected.get("gigacontinuum_id") or "")
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
    teracontinuum_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    gigacontinuum_states: Sequence[Mapping[str, Any]],
    gigacontinuum_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    teracontinuum_goal: str,
    max_active_gigacontinuums: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
    charter_expansions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "teracontinuum_id": teracontinuum_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "gigacontinuum_states": [dict(ist) for ist in gigacontinuum_states],
        "gigacontinuum_digests": list(gigacontinuum_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "teracontinuum_goal": teracontinuum_goal,
        "max_active_gigacontinuums": max_active_gigacontinuums,
        "admissions": [dict(a) for a in (admissions or [])],
        "charter_expansions": [dict(e) for e in (charter_expansions or [])],
        "pending_gigacontinuum_ids": [
            str(s.get("gigacontinuum_id") or "")
            for s in pending_charter_slots(charter, gigacontinuum_states)
        ],
    }


def write_teracontinuum_state(teracontinuum_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(teracontinuum_dir) / "teracontinuum_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_teracontinuum_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "teracontinuum_state.json")
    if not path.is_file():
        raise TeracontinuumRefused(
            "teracontinuum_state_missing",
            f"no teracontinuum_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TeracontinuumRefused("teracontinuum_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise TeracontinuumRefused("teracontinuum_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _gigacontinuum_round_record(
    *,
    round_index: int,
    gigacontinuum_id: str,
    continuum_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "gigacontinuum_id": gigacontinuum_id,
        "ok": bool(continuum_result.get("ok")),
        "verdict": continuum_result.get("verdict"),
        "stop_reason": continuum_result.get("stop_reason"),
        "gigacontinuum_dir": continuum_result.get("gigacontinuum_dir"),
        "gigacontinuum_digest": continuum_result.get("gigacontinuum_digest"),
        "continuums_admitted": int(
            continuum_result.get("megacontinuums_admitted")
            or continuum_result.get("ultracontinuums_admitted")
            or continuum_result.get("gigacontinuums_admitted")
            or continuum_result.get("continuums_admitted")
            or continuum_result.get("omniverses_admitted")
            or continuum_result.get("multiverses_admitted")
            or continuum_result.get("empires_admitted")
            or continuum_result.get("realms_admitted")
            or 0
        ),
        "continuums_met_count": int(
            continuum_result.get("megacontinuums_met_count")
            or continuum_result.get("ultracontinuums_met_count")
            or continuum_result.get("gigacontinuums_met_count")
            or continuum_result.get("continuums_met_count")
            or continuum_result.get("omniverses_met_count")
            or continuum_result.get("multiverses_met_count")
            or continuum_result.get("empires_met_count")
            or continuum_result.get("realms_met_count")
            or 0
        ),
        "total_dispatched": int(continuum_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(continuum_result.get("total_dispatched_ok") or 0),
        "gigacontinuum_met": bool(continuum_result.get("gigacontinuum_met")),
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


def _teracontinuum_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "teracontinuum_id": receipt.get("teracontinuum_id"),
        "teracontinuum_goal": receipt.get("teracontinuum_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_gigacontinuums": receipt.get("max_active_gigacontinuums"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "gigacontinuum_digests": list(receipt.get("gigacontinuum_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "teracontinuum_met": receipt.get("teracontinuum_met"),
        "coverage_end": receipt.get("coverage_end"),
        "gigacontinuums_met_count": receipt.get("gigacontinuums_met_count"),
        "gigacontinuums_admitted": receipt.get("gigacontinuums_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "charter_expansion_count": receipt.get("charter_expansion_count"),
        "charter_expanded_ids": list(receipt.get("charter_expanded_ids") or []),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_teracontinuum_receipt(teracontinuum_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(teracontinuum_dir) / "teracontinuum.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_teracontinuum_digest_payload(receipt))
    recorded = str(receipt.get("teracontinuum_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("teracontinuum_digest")

    institutions = list(receipt.get("gigacontinuums") or receipt.get("realms") or receipt.get("leagues") or [])
    listed = list(receipt.get("gigacontinuum_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("gigacontinuum_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("gigacontinuum_digest"):
                mismatched.append(f"gigacontinuum_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("gigacontinuum_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "gigacontinuum.json").is_file():
            nested = gg.verify_gigacontinuum_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "teracontinuum_sealed" if ok else "teracontinuum_tampered",
        "teracontinuum_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run realm


def run_teracontinuum(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_gigacontinuums: int | None = None,
    dispatch: bool = True,
    gigacontinuum_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    charter_expand: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    teracontinuum_goal: str = "all_gigacontinuums_met",
    refresh_promotions: Mapping[str, str] | None = None,
    teracontinuum_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_teracontinuum_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_gigacontinuums:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    teracontinuum_goal:
        ``all_gigacontinuums_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``teracontinuum_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise TeracontinuumRefused("teracontinuum_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise TeracontinuumRefused(
            "teracontinuum_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_gigacontinuums is not None and int(max_active_gigacontinuums) < 1:
        raise TeracontinuumRefused(
            "teracontinuum_invalid", "max_active_gigacontinuums must be >= 1 when set"
        )
    if teracontinuum_goal not in {"all_gigacontinuums_met", "terminal_coverage", "none"}:
        raise TeracontinuumRefused(
            "teracontinuum_invalid",
            f"unknown teracontinuum_goal: {teracontinuum_goal}",
        )

    runner = gigacontinuum_runner or gg.run_gigacontinuum

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    gigacontinuum_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_teracontinuum_id: str | None = None
    gigacontinuum_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    charter_expansions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_teracontinuum_state(resume_dir)
        resumed = True
        resume_teracontinuum_id = str(state.get("teracontinuum_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        gigacontinuum_digests = [str(d) for d in (state.get("gigacontinuum_digests") or [])]
        gigacontinuum_states = [
            dict(ist)
            for ist in (state.get("gigacontinuum_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_teracontinuum_charter(
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
            state.get("max_active_gigacontinuums") is not None
            and max_active_gigacontinuums is None
        ):
            resumed_max_active = int(state["max_active_gigacontinuums"])
        # Resume may also merge a caller-supplied charter growth tail.
        if charter:
            active_charter = merge_teracontinuum_charter(active_charter, charter)
    else:
        active_charter = normalize_teracontinuum_charter(charter)

    active_max = (
        max_active_gigacontinuums
        if max_active_gigacontinuums is not None
        else resumed_max_active
    )

    if not active_charter and not gigacontinuum_states:
        raise TeracontinuumRefused(
            "teracontinuum_empty",
            "continuum charter has no admitable realm slots",
        )

    lid = (
        teracontinuum_id
        or resume_teracontinuum_id
        or f"teracontinuum-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        teracontinuum_dir = Path(out_root)
        if (teracontinuum_dir / "teracontinuum.json").is_file():
            teracontinuum_dir = teracontinuum_dir / stamp
    else:
        teracontinuum_dir = ARTIFACTS_ROOT / stamp
    teracontinuum_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    # Child continuum trees already consume most of MAX_PATH; place their roots
    # on a flat ultra-short base (not under teracontinuum_dir) so one extra
    # federation layer still fits on Windows.
    import os as _os

    if league_out_root is not None:
        lg_root = Path(league_out_root)
    elif _os.name == "nt":
        lg_root = Path("C:/t") / "r"
    else:
        lg_root = teracontinuum_dir / "e"
    lg_root.mkdir(parents=True, exist_ok=True)
    if _os.name == "nt":
        inst_flat_root = Path("C:/t") / "s"
    else:
        inst_flat_root = teracontinuum_dir / "x"
    inst_flat_root.mkdir(parents=True, exist_ok=True)
    # Per-run namespace so parallel/resumed ultracontinua do not collide.
    # Prefer a short random token over the human lid (often "teracontinuum-…")
    # so Windows paths stay short and never re-enter a prior gigacontinuum_dir that
    # already has continuum.json (which forces an extra timestamp segment).
    import secrets as _secrets

    _run_ns = _secrets.token_hex(2)
    lg_root = lg_root / _run_ns
    inst_flat_root = inst_flat_root / _run_ns
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        teracontinuum_dir=teracontinuum_dir,
        charter=active_charter,
        gigacontinuum_states=gigacontinuum_states,
        max_active_gigacontinuums=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not gigacontinuum_states and not pending_charter_slots(
        active_charter, gigacontinuum_states
    ):
        raise TeracontinuumRefused("teracontinuum_empty", "no realm slots admitted")
    if not gigacontinuum_states and pending_charter_slots(
        active_charter, gigacontinuum_states
    ):
        raise TeracontinuumRefused(
            "teracontinuum_empty",
            "no realm slots admitted under max_active_gigacontinuums policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in gigacontinuum_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    teracontinuum_met = False
    terminal_reopen_count = 0
    max_terminal_reopens = max(2, (len(gigacontinuum_states) or 1) * 4)
    coverage_end: dict[str, Any] = teracontinuum_terminal_coverage(
        gigacontinuum_states=gigacontinuum_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            teracontinuum_dir=teracontinuum_dir,
            charter=active_charter,
            gigacontinuum_states=gigacontinuum_states,
            max_active_gigacontinuums=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = teracontinuum_terminal_coverage(
            gigacontinuum_states=gigacontinuum_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            gigacontinuum_states=gigacontinuum_states,
            charter=active_charter,
            teracontinuum_goal=teracontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "teracontinuum_met"
            teracontinuum_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_gigacontinuum(
            gigacontinuum_states, roi_history, round_index=round_index
        )
        if selected is None:
            # Children may all report met while federated terminal coverage is
            # still incomplete (e.g. deferred surfaces). Only declare teracontinuum
            # met when the active teracontinuum_goal is actually satisfied.
            if constitution_satisfied(
                gigacontinuum_states=gigacontinuum_states,
                charter=active_charter,
                teracontinuum_goal=teracontinuum_goal,
                federated_portfolio=federated_portfolio,
            ):
                stop_reason = "teracontinuum_met"
                teracontinuum_met = True
                coverage_end = coverage_before
                break
            if (
                teracontinuum_goal == "terminal_coverage"
                and terminal_reopen_count < max_terminal_reopens
            ):
                reopened = reopen_incomplete_gigacontinuums(
                    gigacontinuum_states,
                    federated_portfolio=federated_portfolio,
                )
                if reopened:
                    terminal_reopen_count += 1
                    selected = select_next_gigacontinuum(
                        gigacontinuum_states, roi_history, round_index=round_index
                    )
            if selected is None:
                stop_reason = "teracontinuum_idle"
                coverage_end = coverage_before
                break

        open_count = sum(
            1 for ist in gigacontinuum_states if not ist.get("gigacontinuum_met")
        )
        allocated = allocate_gigacontinuum_budget(
            remaining_budget=remaining_budget,
            open_continuum_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        gigacontinuum_id = str(selected["gigacontinuum_id"])
        resume_gigacontinuum_dir = selected.get("last_gigacontinuum_dir")
        continuum_resume: Path | None = None
        if (
            resume_gigacontinuum_dir
            and (Path(str(resume_gigacontinuum_dir)) / "gigacontinuum_state.json").is_file()
            and not selected.get("gigacontinuum_met")
        ):
            continuum_resume = Path(str(resume_gigacontinuum_dir))

        # Ultra-short stamp (each outer plane tightens Windows MAX_PATH).
        # Do NOT nest child gigacontinuum trees under teracontinuum roots:
        # let the gigacontinuum plane use its own flat C:/t/{h,i} bases so the
        # deep continuum→…→wave chain still fits. Only the gigacontinuum receipt
        # itself lands on a flat unique out_root.
        safe_id = "".join(c if c.isalnum() else "" for c in gigacontinuum_id)[:2] or "i"
        child_token = _secrets.token_hex(2)
        if _os.name == "nt":
            out_dir = Path("C:/t") / "r" / f"{child_token}{safe_id}"
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
            "gigacontinuum_goal": str(
                selected.get("gigacontinuum_goal") or "all_megacontinuums_met"
            ),
            "gigacontinuum_id": gigacontinuum_id,
            "out_root": out_dir,
        }
        if inst_out is not None:
            continuum_kwargs["league_out_root"] = inst_out
        max_active_megacontinuums = selected.get("max_active_megacontinuums")
        if max_active_megacontinuums is None:
            max_active_megacontinuums = selected.get("max_active_continuums")
        if max_active_megacontinuums is None:
            max_active_megacontinuums = selected.get("max_active_civilizations")
        if max_active_megacontinuums is not None:
            continuum_kwargs["max_active_megacontinuums"] = int(
                max_active_megacontinuums
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
        except gg.GigacontinuumRefused as exc:
            if local_index == 0 and not resumed:
                raise TeracontinuumRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"continuum_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise TeracontinuumRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise TeracontinuumRefused(exc.verdict, exc.detail) from exc
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
        nested_gigacontinuum_dir = continuum_result.get("gigacontinuum_dir")
        nested_multiverse_states: list[dict[str, Any]] = []
        nested_receipt_path = (
            Path(str(nested_gigacontinuum_dir)) / "gigacontinuum.json"
            if nested_gigacontinuum_dir
            else None
        )
        if nested_receipt_path is not None and nested_receipt_path.is_file():
            receipt = json.loads(nested_receipt_path.read_text(encoding="utf-8"))
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(
                receipt.get("megacontinuum_states")
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
                continuum_result.get("megacontinuum_states")
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

        for i, lst in enumerate(gigacontinuum_states):
            if str(lst.get("gigacontinuum_id")) != gigacontinuum_id:
                continue
            updated = dict(lst)
            updated["last_gigacontinuum_dir"] = continuum_result.get("gigacontinuum_dir")
            updated["last_gigacontinuum_digest"] = continuum_result.get("gigacontinuum_digest")
            updated["gigacontinuum_met"] = bool(continuum_result.get("gigacontinuum_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_multiverse_states:
                updated["megacontinuum_states"] = nested_multiverse_states
                updated["ultracontinuum_states"] = nested_multiverse_states
                updated["continuum_states"] = nested_multiverse_states
                updated["omniverse_states"] = nested_multiverse_states
                updated["multiverse_states"] = nested_multiverse_states
                updated["cosmos_states"] = nested_multiverse_states
                updated["civilization_states"] = nested_multiverse_states
                updated["empire_states"] = nested_multiverse_states
            gigacontinuum_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in gigacontinuum_states]
        )
        coverage_after = teracontinuum_terminal_coverage(
            gigacontinuum_states=gigacontinuum_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_gigacontinuum_roi(
            round_index=round_index,
            gigacontinuum_id=gigacontinuum_id,
            continuum_result=continuum_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(continuum_result.get("gigacontinuum_digest") or "")
        if idigest:
            gigacontinuum_digests.append(idigest)

        rec = _gigacontinuum_round_record(
            round_index=round_index,
            gigacontinuum_id=gigacontinuum_id,
            continuum_result=continuum_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            teracontinuum_dir=teracontinuum_dir,
            charter=active_charter,
            gigacontinuum_states=gigacontinuum_states,
            max_active_gigacontinuums=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = teracontinuum_terminal_coverage(
                gigacontinuum_states=gigacontinuum_states,
                federated_portfolio=federated_portfolio,
            )

        write_teracontinuum_state(
            teracontinuum_dir,
            _state_payload(
                teracontinuum_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                gigacontinuum_states=gigacontinuum_states,
                gigacontinuum_digests=gigacontinuum_digests,
                charter=active_charter,
                stop_reason=None,
                teracontinuum_goal=teracontinuum_goal,
                max_active_gigacontinuums=active_max,
                admissions=admissions,
                charter_expansions=charter_expansions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not continuum_result.get("gigacontinuum_met")
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
                    "gigacontinuum_states": gigacontinuum_states,
                    "last_gigacontinuum_id": gigacontinuum_id,
                    "federated_portfolio": federated_portfolio,
                    "teracontinuum_dir": str(teracontinuum_dir),
                    "pending_gigacontinuum_ids": [
                        str(s.get("gigacontinuum_id") or "")
                        for s in pending_charter_slots(
                            active_charter, gigacontinuum_states
                        )
                    ],
                    "admissions": admissions,
                    "charter_expansions": charter_expansions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        # Grow constitution before declaring teracontinuum_met when expand remains.
        if (
            charter_expand is not None
            and not pending_charter_slots(active_charter, gigacontinuum_states)
            and gigacontinuums_all_met(gigacontinuum_states)
        ):
            growth = charter_expand(
                active_charter=active_charter,
                gigacontinuum_states=gigacontinuum_states,
                round_index=round_index,
                roi_history=roi_history,
            )
            if growth.get("expanded") and growth.get("charter"):
                active_charter = normalize_teracontinuum_charter(
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
                    teracontinuum_dir=teracontinuum_dir,
                    charter=active_charter,
                    gigacontinuum_states=gigacontinuum_states,
                    max_active_gigacontinuums=active_max,
                    round_index=round_index + 1,
                )
                if post_growth:
                    admissions.extend(post_growth)
                write_teracontinuum_state(
                    teracontinuum_dir,
                    _state_payload(
                        teracontinuum_id=lid,
                        round_count=round_index + 1,
                        total_dispatched=total_dispatched,
                        total_dispatched_ok=total_dispatched_ok,
                        federated_portfolio=federated_portfolio,
                        roi_history=roi_history,
                        gigacontinuum_states=gigacontinuum_states,
                        gigacontinuum_digests=gigacontinuum_digests,
                        charter=active_charter,
                        stop_reason=None,
                        teracontinuum_goal=teracontinuum_goal,
                        max_active_gigacontinuums=active_max,
                        admissions=admissions,
                        charter_expansions=charter_expansions,
                    ),
                )
                # Continue the outer loop with the grown charter.
                continue

        if constitution_satisfied(
            gigacontinuum_states=gigacontinuum_states,
            charter=active_charter,
            teracontinuum_goal=teracontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "teracontinuum_met"
            teracontinuum_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            gigacontinuum_states=gigacontinuum_states,
            charter=active_charter,
            teracontinuum_goal=teracontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "teracontinuum_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        teracontinuum_dir=teracontinuum_dir,
        charter=active_charter,
        gigacontinuum_states=gigacontinuum_states,
        max_active_gigacontinuums=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in gigacontinuum_states]
    )
    coverage_end = teracontinuum_terminal_coverage(
        gigacontinuum_states=gigacontinuum_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        gigacontinuum_states=gigacontinuum_states,
        charter=active_charter,
        teracontinuum_goal=teracontinuum_goal,
        federated_portfolio=federated_portfolio,
    ):
        teracontinuum_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    gigacontinuums_met_count = sum(
        1 for ist in gigacontinuum_states if ist.get("gigacontinuum_met")
    )
    pending_remaining = [
        str(s.get("gigacontinuum_id") or "")
        for s in pending_charter_slots(active_charter, gigacontinuum_states)
    ]

    if teracontinuum_met and stop_reason in {"teracontinuum_met", "max_rounds"}:
        verdict = "teracontinuum_met"
        ok = True
        stop_reason = "teracontinuum_met"
    elif stop_reason == "rank_only":
        verdict = "teracontinuum_ranked"
        ok = True
    elif stop_reason == "teracontinuum_idle":
        verdict = "teracontinuum_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "teracontinuum_budgeted"
        ok = True
    elif stop_reason.startswith("domain_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "continuum_refused_mid"
        ok = False
    else:
        verdict = "teracontinuum_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "teracontinuum_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_gigacontinuums": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "teracontinuum_goal": teracontinuum_goal,
        "teracontinuum_met": teracontinuum_met,
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
        "gigacontinuums": institutions,
        "gigacontinuum_digests": [
            i.get("gigacontinuum_digest")
            for i in institutions
            if i.get("gigacontinuum_digest")
        ],
        "gigacontinuum_states": gigacontinuum_states,
        "gigacontinuums_admitted": len(gigacontinuum_states),
        "gigacontinuums_met_count": gigacontinuums_met_count,
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
    receipt["gigacontinuum_digests"] = [
        str(i.get("gigacontinuum_digest") or "") for i in institutions
    ]
    receipt["teracontinuum_digest"] = _sha256_json(_teracontinuum_digest_payload(receipt))
    atomic_write_json(teracontinuum_dir / "teracontinuum.json", receipt)
    atomic_write_json(
        teracontinuum_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "teracontinuum_id": receipt["teracontinuum_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "teracontinuum_met": receipt["teracontinuum_met"],
            "gigacontinuums_admitted": receipt["gigacontinuums_admitted"],
            "gigacontinuums_met_count": receipt["gigacontinuums_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "charter_expansion_count": receipt["charter_expansion_count"],
            "max_active_gigacontinuums": receipt["max_active_gigacontinuums"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "teracontinuum_digest": receipt["teracontinuum_digest"],
            "resumed": resumed,
        },
    )

    write_teracontinuum_state(
        teracontinuum_dir,
        _state_payload(
            teracontinuum_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            gigacontinuum_states=gigacontinuum_states,
            gigacontinuum_digests=receipt["gigacontinuum_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            teracontinuum_goal=teracontinuum_goal,
            max_active_gigacontinuums=active_max,
            admissions=admissions,
            charter_expansions=charter_expansions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "teracontinuum_dir": str(teracontinuum_dir),
        "teracontinuum_digest": receipt["teracontinuum_digest"],
        "teracontinuum_id": lid,
        "round_count": len(institutions),
        "gigacontinuum_digests": list(receipt["gigacontinuum_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "teracontinuum_met": teracontinuum_met,
        "gigacontinuums_admitted": len(gigacontinuum_states),
        "gigacontinuums_met_count": gigacontinuums_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_gigacontinuums": active_max,
        "admissions": admissions,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": list(receipt["charter_expanded_ids"]),
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "gigacontinuum_states": gigacontinuum_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "gigacontinuums": institutions,
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
    return gg._program_slot(
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
    return gg._inst_slot(
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
    return gg._commonwealth_slot(
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
    return gg._domain_slot(
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
    return gg._realm_slot(
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
    return gg._empire_slot(
        empire_id,
        priority=priority,
        realms=realms,
        institutions=institutions,
        max_rounds=max_rounds,
        empire_goal=empire_goal,
        max_active_realms=max_active_realms,
    )


def _gigacontinuum_slot(
    gigacontinuum_id: str,
    *,
    priority: int = 0,
    megacontinuums: Sequence[dict[str, Any]] | None = None,
    ultracontinuums: Sequence[dict[str, Any]] | None = None,
    multiverses: Sequence[dict[str, Any]] | None = None,
    cosmoses: Sequence[dict[str, Any]] | None = None,
    civilizations: Sequence[dict[str, Any]] | None = None,
    empires: Sequence[dict[str, Any]] | None = None,
    realms: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    gigacontinuum_goal: str = "all_megacontinuums_met",
    max_active_megacontinuums: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic teracontinuum charter gigacontinuum slot.

    Prefer ``megacontinuums=`` (nested mega slots for the gigacontinuum plane).
    ``institutions=`` wrap a single auto mega with ultra nesting underneath.
    """
    nested: list[dict[str, Any]]
    if megacontinuums is not None:
        nested = list(megacontinuums)
    elif ultracontinuums is not None:
        nested = [
            gg._megacontinuum_slot(
                f"{gigacontinuum_id[:1]}m",
                ultracontinuums=list(ultracontinuums),
                max_rounds=max_rounds,
            )
        ]
    elif multiverses is not None:
        nested = [
            gg._megacontinuum_slot(
                f"{gigacontinuum_id[:1]}m",
                multiverses=list(multiverses),
                max_rounds=max_rounds,
            )
        ]
    elif cosmoses is not None:
        nested = [
            gg._megacontinuum_slot(
                f"{gigacontinuum_id[:1]}m",
                cosmoses=list(cosmoses),
                max_rounds=max_rounds,
            )
        ]
    elif civilizations is not None:
        nested = [
            gg._megacontinuum_slot(
                f"{gigacontinuum_id[:1]}m",
                civilizations=list(civilizations),
                max_rounds=max_rounds,
            )
        ]
    elif empires is not None:
        nested = [
            gg._megacontinuum_slot(
                f"{gigacontinuum_id[:1]}m",
                empires=list(empires),
                max_rounds=max_rounds,
            )
        ]
    elif realms is not None:
        nested = [
            gg._megacontinuum_slot(
                f"{gigacontinuum_id[:1]}m",
                realms=list(realms),
                max_rounds=max_rounds,
            )
        ]
    elif institutions:
        nested = [
            gg._megacontinuum_slot(
                f"{gigacontinuum_id[:1]}m",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "gigacontinuum_id": gigacontinuum_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "gigacontinuum_goal": gigacontinuum_goal,
        "max_active_megacontinuums": max_active_megacontinuums,
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


def builtin_upstream_teracontinuum_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-gigacontinuum teracontinuum plane (no network).

    Uses an injected fast ``gigacontinuum_runner`` so the outer plane constitution
    (admit/schedule/federate/retire/expand/resume/seal/terminal reopen) is fully
    exercised without paying full nested giga→…→wave wall-clock cost. Nested
    giga receipts are still written and verified through the real tera seal path.
    """
    scratch = _proof_scratch()
    try:
        # Per-gigacontinuum progress for budget/resume/terminal multi-call realism.
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
            mid = str(kwargs.get("gigacontinuum_id") or "m")
            nested_charter = gg.normalize_gigacontinuum_charter(kwargs.get("charter"))
            if kwargs.get("resume_dir") is not None and not nested_charter:
                state_path = Path(str(kwargs["resume_dir"])) / "gigacontinuum_state.json"
                if state_path.is_file():
                    st = json.loads(state_path.read_text(encoding="utf-8"))
                    nested_charter = gg.normalize_gigacontinuum_charter(st.get("charter"))
                    mid = str(st.get("gigacontinuum_id") or mid)

            goal = str(kwargs.get("gigacontinuum_goal") or "all_megacontinuums_met")
            # terminal_coverage at parent may force reopen; expose deferred only after first meet.
            st = _progress.setdefault(
                mid,
                {"done": set(), "calls": 0, "dispatched": 0, "dispatched_ok": 0},
            )
            st["calls"] = int(st["calls"]) + 1
            include_deferred = st["calls"] > 1 or goal == "all_megacontinuums_met"
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
            megacontinuum_states = [
                {
                    "megacontinuum_id": str(s.get("megacontinuum_id") or s.get("id") or "m"),
                    "megacontinuum_met": report_met,
                    "charter": list(s.get("charter") or []),
                    "portfolio": portfolio,
                    "inventory_keys": list(all_keys),  # required surface incl. deferred
                }
                for s in nested_charter
                if isinstance(s, Mapping)
            ] or [
                {
                    "megacontinuum_id": "m0",
                    "megacontinuum_met": report_met,
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
                "verdict": "gigacontinuum_met" if report_met else "gigacontinuum_completed",
                "stop_reason": "gigacontinuum_met" if report_met else "dispatch_budget",
                "gigacontinuum_id": mid,
                "gigacontinuum_goal": str(
                    kwargs.get("gigacontinuum_goal") or "all_megacontinuums_met"
                ),
                "max_rounds": int(kwargs.get("max_rounds") or 6),
                "max_active_megacontinuums": kwargs.get("max_active_megacontinuums"),
                "dispatch_budget": kwargs.get("dispatch_budget"),
                "gigacontinuum_met": report_met,
                "total_dispatched": st["dispatched"],
                "total_dispatched_ok": st["dispatched_ok"],
                "megacontinuums": [],
                "megacontinuum_digests": [],
                "megacontinuums_admitted": max(1, len(nested_charter) or 1),
                "megacontinuums_met_count": (
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
                "megacontinuum_states": megacontinuum_states,
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
            receipt["gigacontinuum_digest"] = _sha256_json(
                gg._gigacontinuum_digest_payload(receipt)
            )
            digest = receipt["gigacontinuum_digest"]
            atomic_write_json(out / "gigacontinuum.json", receipt)
            atomic_write_json(
                out / "gigacontinuum_state.json",
                {
                    "gigacontinuum_id": mid,
                    "round_count": st["calls"],
                    "total_dispatched": st["dispatched"],
                    "total_dispatched_ok": st["dispatched_ok"],
                    "federated_portfolio": portfolio,
                    "megacontinuum_states": megacontinuum_states,
                    "stop_reason": receipt["stop_reason"],
                    "charter": nested_charter,
                    "gigacontinuum_met": report_met,
                },
            )
            return {
                "ok": True,
                "verdict": receipt["verdict"],
                "stop_reason": receipt["stop_reason"],
                "gigacontinuum_dir": str(out),
                "gigacontinuum_digest": digest,
                "gigacontinuum_id": mid,
                "total_dispatched": st["dispatched"],
                "total_dispatched_ok": st["dispatched_ok"],
                "gigacontinuum_met": report_met,
                "megacontinuums_admitted": receipt["megacontinuums_admitted"],
                "megacontinuums_met_count": receipt["megacontinuums_met_count"],
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "megacontinuum_states": megacontinuum_states,
                "used_skill_route_discovery": False,
            }

        def _slot(mid: str, *, priority: int = 1, initial: Sequence[tuple[str, str, str]], deferred: Sequence[tuple[str, str, str]] = (), max_rounds: int = 4) -> dict[str, Any]:
            return _gigacontinuum_slot(
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
        confed = run_teracontinuum(
            charter=charter,
            max_rounds=8,
            dispatch_budget=12,
            dispatch=True,
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="all_gigacontinuums_met",
            out_root=scratch / "m",
        )
        multi_teracontinuum_ok = (
            confed["ok"]
            and confed["teracontinuum_met"] is True
            and confed["stop_reason"] == "teracontinuum_met"
            and confed["gigacontinuums_admitted"] == 2
            and confed["gigacontinuums_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
        )
        scheduled_ids = {
            i.get("gigacontinuum_id")
            for i in (confed.get("gigacontinuums") or [])
        }
        multi_teracontinuum_scheduled = multi_teracontinuum_ok and scheduled_ids >= {"a", "b"}

        verified = verify_teracontinuum_receipt(Path(confed["teracontinuum_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed["round_count"]

        confed_path = Path(confed["teracontinuum_dir"]) / "teracontinuum.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["teracontinuum_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_teracontinuum_receipt(Path(confed["teracontinuum_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "teracontinuum_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop
        _progress.clear()
        budgeted = run_teracontinuum(
            charter=[
                _slot("b1", initial=[("d1", "1.0.0", "d1-1")]),
                _slot("b2", initial=[("d2", "1.0.0", "d2-1")]),
            ],
            max_rounds=6,
            dispatch_budget=1,
            dispatch=True,
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="none",
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
            nested_charter = gg.normalize_gigacontinuum_charter(kwargs.get("charter"))
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
                "verdict": "gigacontinuum_met",
                "stop_reason": "gigacontinuum_met",
                "gigacontinuum_id": kwargs.get("gigacontinuum_id"),
                "gigacontinuum_goal": "all_megacontinuums_met",
                "max_rounds": 1,
                "max_active_megacontinuums": None,
                "dispatch_budget": None,
                "gigacontinuum_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "megacontinuums": [],
                "megacontinuum_digests": [],
                "megacontinuums_admitted": max(1, len(nested_charter) or 1),
                "megacontinuums_met_count": max(1, len(nested_charter) or 1),
                "admission_count": 0,
                "pending_remaining": [],
                "charter_expansion_count": 0,
                "charter_expanded_ids": [],
                "round_count": 0,
                "portfolio_start_digest": None,
                "portfolio_end_digest": portfolio.get("portfolio_digest"),
                "federated_portfolio": portfolio,
                "megacontinuum_states": [
                    {
                        "megacontinuum_id": "m",
                        "megacontinuum_met": True,
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
            receipt["gigacontinuum_digest"] = _sha256_json(
                gg._gigacontinuum_digest_payload(receipt)
            )
            digest = receipt["gigacontinuum_digest"]
            atomic_write_json(out / "gigacontinuum.json", receipt)
            atomic_write_json(
                out / "gigacontinuum_state.json",
                {
                    "gigacontinuum_id": kwargs.get("gigacontinuum_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "megacontinuum_states": receipt["megacontinuum_states"],
                    "stop_reason": "gigacontinuum_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "gigacontinuum_met",
                "stop_reason": "gigacontinuum_met",
                "gigacontinuum_dir": str(out),
                "gigacontinuum_digest": digest,
                "gigacontinuum_id": kwargs.get("gigacontinuum_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "gigacontinuum_met": True,
                "megacontinuums_admitted": receipt["megacontinuums_admitted"],
                "megacontinuums_met_count": receipt["megacontinuums_met_count"],
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "megacontinuum_states": receipt["megacontinuum_states"],
                "used_skill_route_discovery": False,
            }

        pre_met = run_teracontinuum(
            charter=[_slot("om", initial=[("om", "9.0.0", "omega-merged")])],
            max_rounds=3,
            dispatch=True,
            gigacontinuum_runner=_premet_runner,
            teracontinuum_goal="all_gigacontinuums_met",
            out_root=scratch / "p",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["teracontinuum_met"] is True
            and pre_met["stop_reason"] == "teracontinuum_met"
            and pre_met["gigacontinuums_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        ranked = run_teracontinuum(
            charter=[
                _slot("ra", initial=[("r1", "1.0.0", "r1-1")]),
                _slot("rb", initial=[("r2", "1.0.0", "r2-1")]),
            ],
            max_rounds=3,
            dispatch=False,
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="none",
            out_root=scratch / "k",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "teracontinuum_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        empty_refused = False
        try:
            run_teracontinuum(
                charter=[],
                dispatch=False,
                teracontinuum_goal="none",
                out_root=scratch / "z",
            )
        except TeracontinuumRefused as exc:
            empty_refused = exc.verdict in {
                "teracontinuum_empty",
                "teracontinuum_invalid",
            }

        _progress.clear()
        custom = run_teracontinuum(
            charter=[
                _slot("c1", initial=[("c1", "1.0.0", "c1-1")]),
                _slot("c2", initial=[("c2", "1.0.0", "c2-1")]),
            ],
            max_rounds=6,
            dispatch_budget=8,
            dispatch=True,
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="none",
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
        partial = run_teracontinuum(
            charter=[
                _slot("z1", priority=2, initial=[("zeta", "1.0.0", "zeta-1")]),
                _slot("z2", priority=1, initial=[("eta", "1.0.0", "eta-1")]),
            ],
            max_rounds=1,
            dispatch_budget=1,
            dispatch=True,
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="none",
            teracontinuum_id="rcp",
            out_root=scratch / "a",
        )
        state_path = Path(partial["teracontinuum_dir"]) / "teracontinuum_state.json"
        state_exists = state_path.is_file()
        resumed = run_teracontinuum(
            resume_dir=Path(partial["teracontinuum_dir"]),
            max_rounds=4,
            dispatch_budget=4,
            dispatch=True,
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="none",
            out_root=scratch / "r",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["teracontinuum_id"] == "rcp"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_continuum"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_continuum") or {}) >= 2
        )

        first_cw = (confed.get("gigacontinuums") or [{}])[0].get("gigacontinuum_id")
        priority_ok = first_cw == "a"

        fed_portfolio = confed.get("coverage_end") or {}
        federation_ok = multi_teracontinuum_ok and (
            float(fed_portfolio.get("coverage_ratio") or 0) == 1.0
            and int(fed_portfolio.get("required") or 0) >= 3
        )

        _progress.clear()
        deferred = run_teracontinuum(
            charter=[
                _slot("da", priority=3, initial=[("da", "1.0.0", "da-1")], max_rounds=3),
                _slot("db", priority=2, initial=[("db", "1.0.0", "db-1")], max_rounds=3),
                _slot("dc", priority=1, initial=[("dc", "1.0.0", "dc-1")], max_rounds=3),
            ],
            max_rounds=8,
            dispatch_budget=6,
            max_active_gigacontinuums=1,
            dispatch=True,
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="all_gigacontinuums_met",
            out_root=scratch / "d",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("gigacontinuum_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["teracontinuum_met"] is True
            and deferred["gigacontinuums_admitted"] == 3
            and deferred["gigacontinuums_met_count"] == 3
            and deferred.get("max_active_gigacontinuums") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        _progress.clear()
        expand_runner = make_teracontinuum_charter_expand(
            [_slot("xg", priority=1, initial=[("xg", "1.0.0", "xg-1")], max_rounds=3)],
            max_slots_per_expand=1,
        )
        expanded = run_teracontinuum(
            charter=[_slot("xe", priority=2, initial=[("xe", "1.0.0", "xe-1")], max_rounds=3)],
            max_rounds=6,
            dispatch_budget=6,
            max_active_gigacontinuums=1,
            dispatch=True,
            gigacontinuum_runner=_fast_mega_runner,
            charter_expand=expand_runner,
            teracontinuum_goal="all_gigacontinuums_met",
            out_root=scratch / "x",
        )
        expand_ok = (
            expanded["ok"]
            and expanded["teracontinuum_met"] is True
            and expanded["gigacontinuums_admitted"] == 2
            and expanded["gigacontinuums_met_count"] == 2
            and int(expanded.get("charter_expansion_count") or 0) >= 1
            and "xg" in set(expanded.get("charter_expanded_ids") or [])
            and not (expanded.get("pending_remaining") or [])
        )

        merged = merge_teracontinuum_charter(
            [_slot("m1", initial=[("m", "1.0.0", "m-1")])],
            [
                _slot("m1", initial=[("m2", "1.0.0", "m2-1")]),
                _slot("m2", initial=[("n", "1.0.0", "n-1")]),
            ],
        )
        merge_ok = [s["gigacontinuum_id"] for s in merged] == ["m1", "m2"]

        # Terminal coverage with premature-met + deferred reopen (ids start with t)
        _progress.clear()
        terminal = run_teracontinuum(
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
            gigacontinuum_runner=_fast_mega_runner,
            teracontinuum_goal="terminal_coverage",
            out_root=scratch / "tc",
        )
        cov_end = terminal.get("coverage_end") or {}
        terminal_ok = (
            terminal["ok"]
            and terminal["teracontinuum_met"] is True
            and terminal["stop_reason"] == "teracontinuum_met"
            and float(cov_end.get("coverage_ratio") or 0) == 1.0
            and int(cov_end.get("required") or 0) >= 3
            and bool(cov_end.get("met"))
            and not (terminal.get("pending_remaining") or [])
            and terminal["gigacontinuums_admitted"] == 2
            and terminal["total_dispatched_ok"] >= 3
        )

        ok = all(
            [
                multi_teracontinuum_ok,
                multi_teracontinuum_scheduled,
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
            "teracontinuum_met": multi_teracontinuum_ok,
            "multi_teracontinuum_progressed": multi_teracontinuum_scheduled,
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
            "teracontinuum_digest": confed.get("teracontinuum_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "gigacontinuums_admitted": confed.get("gigacontinuums_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_teracontinuum_ok": multi_teracontinuum_ok,
                "multi_teracontinuum_scheduled": multi_teracontinuum_scheduled,
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
        result = verify_teracontinuum_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_teracontinuum_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
