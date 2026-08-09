"""Upstream hypercontinuum plane: multi-continuum durable stewardship hypercontinuum.

The continuum plane (``upstream_continuum``) closes multi-omniverse unions *within one
continuum*. It does not:

1. chain multiple independent continuums under a durable hypercontinuum constitution;
2. allocate a shared global dispatch budget across continuums by ROI;
3. admit/retire continuum slots from a hypercontinuum charter over time
   (deferred admission under a concurrent-active cap);
4. grow the hypercontinuum charter mid-run via ``charter_expand`` (constitution
   growth beyond the initial charter, not just deferred admission of a fixed set);
5. federate multi-continuum portfolio coverage into one hypercontinuum world-model;
6. persist hypercontinuum state so a later process can resume the union;
7. seal a multi-continuum hypercontinuum chronicle linking continuum digests.

The hypercontinuum plane closes that outer multi-continuum loop:

1. **admit** — materialize continuum slots from a durable hypercontinuum charter
   (each slot owns a nested omniverse charter). When ``max_active_continuums``
   is set, only that many *unmet* continuums are concurrent: further charter
   slots stay pending and are admitted as capacity frees after retirements
   (hypercontinuum constitution growth over time);
2. **schedule** — pick the next open continuum by priority and historical ROI;
3. **continuum** — call the continuum plane (injected ``continuum_runner``;
   default ``run_continuum``) with a share of the remaining global dispatch
   budget;
4. **federate** — merge per-continuum portfolios into one hypercontinuum world-model
   and re-score coverage across all stewarded keys;
5. **retire** — mark continuums met when their continuum_goal is satisfied,
   then re-admit pending charter slots up to the active capacity;
6. **expand** — optional ``charter_expand`` may append new continuum slots when
   the active charter has no pending work and all admitted continuums are met,
   so the hypercontinuum constitution can grow after start (not only defer a fixed charter);
7. **persist** — write ``hypercontinuum_state.json`` after every continuum round so a
   later ``run_hypercontinuum(..., resume_dir=...)`` continues the same union
   (including pending charter and admission history);
8. **stop** when any of:

   - ``max_rounds`` reached
   - global ``dispatch_budget`` exhausted across continuums
   - hypercontinuum goal met (``all_continuums_met``: every *admitted*
     continuum is met *and* no pending charter slots remain)
   - consecutive idle/no-progress rounds (``idle_round_limit``)
   - explicit ``stop_when`` predicate returns a reason string

9. **seal** — write a hypercontinuum receipt under
   ``artifacts/upstream-hypercontinuum/`` with sha256 digests of every
   continuum, portfolio federation, admission history, ROI history, stop
   reason, and a hypercontinuum chain digest; ``verify_hypercontinuum_receipt``
   re-checks the chain and detects tampering.

No skill-route discovery is used. The plane is hypercontinuum-level direction
over the continuum plane, not a new verifier of individual repairs.
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
from blackhole_agent import upstream_continuum as uc
from blackhole_agent import upstream_program as up
from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = REPO_ROOT / "artifacts" / "upstream-hypercontinuum"

TERMINAL_SUCCESS_OUTCOMES = uc.TERMINAL_SUCCESS_OUTCOMES


class HypercontinuumRefused(Exception):
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


def normalize_hypercontinuum_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize a hypercontinuum charter into deterministic continuum slots.

    Each slot is::

        {
          "continuum_id": str,
          "priority": int,
          "charter": [...multiverse slots...],  # nested continuum charter
          "max_active_omniverses": int | None,
          "max_rounds": int,
          "continuum_goal": str,
        }
    """
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        continuum_id = str(
            raw.get("continuum_id") or raw.get("id") or ""
        ).strip()
        if not continuum_id or continuum_id in seen:
            continue
        seen.add(continuum_id)

        nested = uc.normalize_continuum_charter(
            raw.get("charter")
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

        max_active_omniverses = raw.get("max_active_omniverses")
        if max_active_omniverses is None:
            max_active_omniverses = raw.get("max_active_cosmoses")
        if max_active_omniverses is None:
            max_active_omniverses = raw.get("max_active_civilizations")
        if max_active_omniverses is not None:
            max_active_omniverses = max(1, int(max_active_omniverses))

        out.append(
            {
                "continuum_id": continuum_id,
                "priority": int(raw.get("priority") or 0),
                "charter": nested,
                "max_active_omniverses": max_active_omniverses,
                "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
                "continuum_goal": str(
                    raw.get("continuum_goal") or "all_omniverses_met"
                ),
                "kind": str(raw.get("kind") or "stewardship_continuum"),
            }
        )
    return out


def admit_continuum_slot(
    *,
    hypercontinuum_dir: Path,
    slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize one institution slot under the league directory.

    Returns admission record with continuum_root and nested charter.
    Stewardship surfaces are created lazily by the institution plane on run.
    """
    continuum_id = str(slot.get("continuum_id") or "")
    if not continuum_id:
        raise HypercontinuumRefused("hypercontinuum_invalid", "slot missing continuum_id")

    continuum_root = Path(hypercontinuum_dir) / "continuums" / continuum_id
    continuum_root.mkdir(parents=True, exist_ok=True)

    nested_charter = uc.normalize_continuum_charter(slot.get("charter"))
    if not nested_charter:
        raise HypercontinuumRefused(
            "hypercontinuum_invalid",
            f"continuum slot {continuum_id!r} has empty nested charter",
        )

    max_active_omniverses = slot.get("max_active_omniverses")
    if max_active_omniverses is None:
        max_active_omniverses = slot.get("max_active_cosmoses")
    if max_active_omniverses is None:
        max_active_omniverses = slot.get("max_active_civilizations")

    return {
        "continuum_id": continuum_id,
        "continuum_root": str(continuum_root),
        "admitted": True,
        "charter": nested_charter,
        "max_active_omniverses": max_active_omniverses,
        "max_rounds": int(slot.get("max_rounds") or 6),
        "continuum_goal": str(slot.get("continuum_goal") or "all_omniverses_met"),
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
        "source": "hypercontinuum_federation",
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


def hypercontinuum_terminal_coverage(
    *,
    continuum_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Coverage across continuum->omniverse->multiverse->...->program."""
    omniverse_states: list[dict[str, Any]] = []
    for cont in continuum_states:
        if not isinstance(cont, Mapping):
            continue
        nested = list(cont.get("omniverse_states") or [])
        if nested:
            for ov in nested:
                if isinstance(ov, Mapping):
                    omniverse_states.append(dict(ov))
            continue
        for oslot in list(cont.get("charter") or []) + list(cont.get("omniverses") or []) + list(
            cont.get("multiverses") or []
        ):
            if isinstance(oslot, Mapping):
                omniverse_states.append(dict(oslot))
        if not nested and not list(cont.get("charter") or []):
            for ov in list(cont.get("multiverse_states") or []) + list(
                cont.get("cosmos_states") or []
            ) + list(cont.get("civilization_states") or []):
                if isinstance(ov, Mapping):
                    omniverse_states.append(dict(ov))
        for raw in list(cont.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                omniverse_states.append(
                    {
                        "inventory_keys": [
                            (str(raw[0]), str(raw[1]), str(raw[2]))
                        ]
                    }
                )
            elif isinstance(raw, Mapping):
                omniverse_states.append({"inventory_keys": [raw]})
    return uc.continuum_terminal_coverage(
        omniverse_states=omniverse_states,
        federated_portfolio=federated_portfolio,
    )


def continuums_all_met(continuum_states: Sequence[Mapping[str, Any]]) -> bool:
    if not continuum_states:
        return False
    return all(bool(ist.get("continuum_met")) for ist in continuum_states)


def open_unmet_count(continuum_states: Sequence[Mapping[str, Any]]) -> int:
    """Count admitted institutions that are not yet continuum_met."""
    return sum(1 for ist in continuum_states if not ist.get("continuum_met"))


def pending_charter_slots(
    charter: Sequence[Mapping[str, Any]],
    continuum_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Charter slots not yet admitted, priority-desc then continuum_id-asc."""
    known = {str(ist.get("continuum_id") or "") for ist in continuum_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get("continuum_id") or "")
        and str(slot.get("continuum_id")) not in known
    ]
    pending.sort(
        key=lambda s: (
            -int(s.get("priority") or 0),
            str(s.get("continuum_id") or ""),
        )
    )
    return pending


def constitution_satisfied(
    *,
    continuum_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    hypercontinuum_goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    """True when the league goal is fully met including pending charter."""
    if hypercontinuum_goal == "none":
        return False
    if hypercontinuum_goal == "terminal_coverage":
        cov = hypercontinuum_terminal_coverage(
            continuum_states=continuum_states,
            federated_portfolio=federated_portfolio,
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            charter, continuum_states
        )
    if hypercontinuum_goal == "all_continuums_met":
        if not continuum_states:
            return False
        if pending_charter_slots(charter, continuum_states):
            return False
        return continuums_all_met(continuum_states)
    return False


def reopen_incomplete_continuums(
    continuum_states: list[dict[str, Any]],
    *,
    federated_portfolio: Mapping[str, Any] | None,
) -> list[str]:
    """Clear ``continuum_met`` on children still short of terminal coverage.

    Nested continuums can retire after only partial surface work (e.g. before
    deferred program targets expand). Under a ``terminal_coverage`` hypercontinuum
    goal those children must re-run until federated inventory is fully
    terminal-success. Returns the reopened ``continuum_id`` list.
    """
    cov = hypercontinuum_terminal_coverage(
        continuum_states=continuum_states,
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
    for i, ist in enumerate(continuum_states):
        if not ist.get("continuum_met"):
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
        # Walk nested multiverse / program charter surfaces for keys.
        for mv in list(ist.get("omniverse_states") or []) + list(ist.get("multiverse_states") or []) + list(
            ist.get("charter") or []
        ):
            if isinstance(mv, Mapping):
                child_keys.update(_collect_from_realm_state(mv))
                # multiverse charter slots may be multiverse-shaped
                for cos in list(mv.get("charter") or []) + list(mv.get("cosmoses") or []):
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
        updated["continuum_met"] = False
        continuum_states[i] = updated
        reopened.append(str(updated.get("continuum_id") or ""))
    return [r for r in reopened if r]


def merge_hypercontinuum_charter(
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge additional realm slots into a continuum charter.

    Existing ``continuum_id`` values win (additions with the same id are
    ignored). Returns a fully re-normalized charter so nested confederation
    charters stay deterministic.
    """
    base = normalize_hypercontinuum_charter(existing)
    if not additions:
        return base
    known = {str(s.get("continuum_id") or "") for s in base}
    merged: list[Mapping[str, Any]] = list(base)
    for raw in additions:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get("continuum_id") or raw.get("id") or "").strip()
        if not cid or cid in known:
            continue
        known.add(cid)
        merged.append(raw)
    return normalize_hypercontinuum_charter(merged)


def make_hypercontinuum_charter_expand(
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
    pending_growth = normalize_hypercontinuum_charter(growth)
    applied_ids: set[str] = set(str(x) for x in (applied or []))
    state: dict[str, Any] = {
        "applied": applied_ids,
        "growth": pending_growth,
        "max_slots_per_expand": max(1, int(max_slots_per_expand)),
    }

    def _runner(
        *,
        active_charter: Sequence[Mapping[str, Any]],
        continuum_states: Sequence[Mapping[str, Any]],
        round_index: int,
        roi_history: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        remaining = [
            s
            for s in pending_growth
            if str(s.get("continuum_id") or "") not in applied_ids
            and str(s.get("continuum_id") or "")
            not in {str(x.get("continuum_id") or "") for x in active_charter}
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
            applied_ids.add(str(s.get("continuum_id") or ""))
        merged = merge_hypercontinuum_charter(active_charter, take)
        state["applied"] = applied_ids
        return {
            "expanded": True,
            "added": [str(s.get("continuum_id") or "") for s in take],
            "charter": merged,
            "detail": "charter_growth_applied",
            "round_index": round_index,
            "realms_met": continuums_all_met(continuum_states),
        }

    _runner.charter_state = state  # type: ignore[attr-defined]
    return _runner


def admit_pending_slots(
    *,
    hypercontinuum_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    continuum_states: list[dict[str, Any]],
    max_active_continuums: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    """Admit pending charter slots up to concurrent-active capacity.

    ``max_active_continuums`` caps *unmet* concurrent realms. ``None``
    admits every remaining pending slot. Returns admission records for newly
    admitted slots (also mutates ``continuum_states``).
    """
    pending = pending_charter_slots(charter, continuum_states)
    if not pending:
        return []

    open_n = open_unmet_count(continuum_states)
    if max_active_continuums is None:
        capacity = len(pending)
    else:
        capacity = max(0, int(max_active_continuums) - open_n)
    if capacity <= 0:
        return []

    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_continuum_slot(hypercontinuum_dir=hypercontinuum_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        continuum_states.append(
            {
                "continuum_id": admission["continuum_id"],
                "continuum_root": admission["continuum_root"],
                "charter": admission["charter"],
                "max_active_omniverses": admission.get("max_active_omniverses"),
                "max_rounds": admission["max_rounds"],
                "continuum_goal": admission["continuum_goal"],
                "priority": admission["priority"],
                "continuum_met": False,
                "last_continuum_dir": None,
                "last_continuum_digest": None,
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


def score_continuum_roi(
    *,
    round_index: int,
    continuum_id: str,
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
        "continuum_id": continuum_id,
        "stop_reason": continuum_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        "continuum_met": bool(continuum_result.get("continuum_met")),
        "continuum_digest": continuum_result.get("continuum_digest"),
        "multiverses_admitted": int(
            continuum_result.get("multiverses_admitted")
            or continuum_result.get("empires_admitted")
            or continuum_result.get("realms_admitted")
            or 0
        ),
        "multiverses_met_count": int(
            continuum_result.get("multiverses_met_count")
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
        iid = str(r.get("continuum_id") or "")
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


def select_next_continuum(
    continuum_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    """Pick the next open (not met) institution by priority then ROI efficiency.

    Tie-break: lower run_count, then stable continuum_id order. Round-robin
    among equal scores uses ``round_index`` so multi-institution progress is fair.
    """
    open_slots = [
        dict(ist) for ist in continuum_states if not ist.get("continuum_met")
    ]
    if not open_slots:
        return None

    summary = _roi_summary(roi_history)
    by_continuum = summary.get("by_continuum") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get("continuum_id") or "")
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


def allocate_continuum_budget(
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
        str(selected.get("continuum_id") or "")
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
    hypercontinuum_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    continuum_states: Sequence[Mapping[str, Any]],
    continuum_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    hypercontinuum_goal: str,
    max_active_continuums: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
    charter_expansions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "hypercontinuum_id": hypercontinuum_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        "continuum_states": [dict(ist) for ist in continuum_states],
        "continuum_digests": list(continuum_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        "hypercontinuum_goal": hypercontinuum_goal,
        "max_active_continuums": max_active_continuums,
        "admissions": [dict(a) for a in (admissions or [])],
        "charter_expansions": [dict(e) for e in (charter_expansions or [])],
        "pending_continuum_ids": [
            str(s.get("continuum_id") or "")
            for s in pending_charter_slots(charter, continuum_states)
        ],
    }


def write_hypercontinuum_state(hypercontinuum_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(hypercontinuum_dir) / "hypercontinuum_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_hypercontinuum_state(resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / "hypercontinuum_state.json")
    if not path.is_file():
        raise HypercontinuumRefused(
            "hypercontinuum_state_missing",
            f"no hypercontinuum_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HypercontinuumRefused("hypercontinuum_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise HypercontinuumRefused("hypercontinuum_state_invalid", "state root must be object")
    return state


# ---------------------------------------------------------------------------
# seal / verify


def _continuum_round_record(
    *,
    round_index: int,
    continuum_id: str,
    continuum_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        "continuum_id": continuum_id,
        "ok": bool(continuum_result.get("ok")),
        "verdict": continuum_result.get("verdict"),
        "stop_reason": continuum_result.get("stop_reason"),
        "continuum_dir": continuum_result.get("continuum_dir"),
        "continuum_digest": continuum_result.get("continuum_digest"),
        "multiverses_admitted": int(
            continuum_result.get("multiverses_admitted")
            or continuum_result.get("empires_admitted")
            or continuum_result.get("realms_admitted")
            or 0
        ),
        "multiverses_met_count": int(
            continuum_result.get("multiverses_met_count")
            or continuum_result.get("empires_met_count")
            or continuum_result.get("realms_met_count")
            or 0
        ),
        "total_dispatched": int(continuum_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(continuum_result.get("total_dispatched_ok") or 0),
        "continuum_met": bool(continuum_result.get("continuum_met")),
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


def _hypercontinuum_digest_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        "hypercontinuum_id": receipt.get("hypercontinuum_id"),
        "hypercontinuum_goal": receipt.get("hypercontinuum_goal"),
        "max_rounds": receipt.get("max_rounds"),
        "max_active_continuums": receipt.get("max_active_continuums"),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        "continuum_digests": list(receipt.get("continuum_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        "hypercontinuum_met": receipt.get("hypercontinuum_met"),
        "coverage_end": receipt.get("coverage_end"),
        "continuums_met_count": receipt.get("continuums_met_count"),
        "continuums_admitted": receipt.get("continuums_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "charter_expansion_count": receipt.get("charter_expansion_count"),
        "charter_expanded_ids": list(receipt.get("charter_expanded_ids") or []),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_hypercontinuum_receipt(hypercontinuum_dir: Path) -> dict[str, Any]:
    """Re-check a sealed league receipt for digest integrity."""
    path = durable_read_path(Path(hypercontinuum_dir) / "hypercontinuum.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}

    expected = _sha256_json(_hypercontinuum_digest_payload(receipt))
    recorded = str(receipt.get("hypercontinuum_digest") or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append("hypercontinuum_digest")

    institutions = list(receipt.get("continuums") or receipt.get("realms") or receipt.get("leagues") or [])
    listed = list(receipt.get("continuum_digests") or [])
    if len(listed) != len(institutions):
        mismatched.append("continuum_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, institutions)):
            if listed_d != rec.get("continuum_digest"):
                mismatched.append(f"continuum_digests[{i}]")

    nested_failures: list[str] = []
    for rec in institutions:
        idir = rec.get("continuum_dir")
        if not idir:
            continue
        ip = Path(str(idir))
        if (ip / "continuum.json").is_file():
            nested = uc.verify_continuum_receipt(ip)
            if not nested.get("ok"):
                nested_failures.append(str(idir))

    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": "hypercontinuum_sealed" if ok else "hypercontinuum_tampered",
        "hypercontinuum_digest": recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(institutions),
    }


# ---------------------------------------------------------------------------
# run realm


def run_hypercontinuum(
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    max_epochs_per_succession: int = 3,
    max_waves_per_epoch: int = 3,
    per_wave_dispatch_limit: int = 1,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active_continuums: int | None = None,
    dispatch: bool = True,
    continuum_runner: Callable[..., dict[str, Any]] | None = None,
    program_runner: Callable[..., dict[str, Any]] | None = None,
    campaign_runner: Callable[..., dict[str, Any]] | None = None,
    succession_runner: Callable[..., dict[str, Any]] | None = None,
    epoch_runner: Callable[..., dict[str, Any]] | None = None,
    impact_refresh_runner: Callable[..., dict[str, Any]] | None = None,
    feedback_runner: Callable[..., dict[str, Any]] | None = None,
    charter_expand: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    hypercontinuum_goal: str = "all_continuums_met",
    refresh_promotions: Mapping[str, str] | None = None,
    hypercontinuum_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
    league_out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-institution stewardship league and seal the receipt.

    Parameters
    ----------
    charter:
        League charter: list of institution slots (see
        :func:`normalize_hypercontinuum_charter`).
    max_rounds:
        Hard cap on institution-dispatch rounds (including idle/rank-only).
    dispatch_budget:
        Total dispatch *attempts* across all institutions; ``None`` means
        unlimited (still bounded by nested institution/program/epoch/wave caps).
    max_active_continuums:
        League concurrent-active cap. When set, only this many *unmet*
        institutions are admitted at once; remaining charter slots stay pending
        and are admitted as institutions retire (deferred federation growth).
        ``None`` admits the full charter eagerly.
    hypercontinuum_goal:
        ``all_continuums_met`` (default) stops when every admitted institution
        is met *and* the charter has no pending slots; ``terminal_coverage``
        stops when federated inventory is fully terminal-success and the
        charter is exhausted; ``none`` disables league-goal stopping.
    resume_dir:
        Load ``hypercontinuum_state.json`` from a prior league dir and continue.
        New receipt is written under ``out_root`` (or a fresh stamp).
    """
    if max_rounds < 1:
        raise HypercontinuumRefused("hypercontinuum_invalid", "max_rounds must be >= 1")
    if per_wave_dispatch_limit < 0:
        raise HypercontinuumRefused(
            "hypercontinuum_invalid", "per_wave_dispatch_limit must be >= 0"
        )
    if max_active_continuums is not None and int(max_active_continuums) < 1:
        raise HypercontinuumRefused(
            "hypercontinuum_invalid", "max_active_continuums must be >= 1 when set"
        )
    if hypercontinuum_goal not in {"all_continuums_met", "terminal_coverage", "none"}:
        raise HypercontinuumRefused(
            "hypercontinuum_invalid",
            f"unknown hypercontinuum_goal: {hypercontinuum_goal}",
        )

    runner = continuum_runner or uc.run_continuum

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    continuum_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_hypercontinuum_id: str | None = None
    continuum_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    charter_expansions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_hypercontinuum_state(resume_dir)
        resumed = True
        resume_hypercontinuum_id = str(state.get("hypercontinuum_id") or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        continuum_digests = [str(d) for d in (state.get("continuum_digests") or [])]
        continuum_states = [
            dict(ist)
            for ist in (state.get("continuum_states") or [])
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_hypercontinuum_charter(
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
            state.get("max_active_continuums") is not None
            and max_active_continuums is None
        ):
            resumed_max_active = int(state["max_active_continuums"])
        # Resume may also merge a caller-supplied charter growth tail.
        if charter:
            active_charter = merge_hypercontinuum_charter(active_charter, charter)
    else:
        active_charter = normalize_hypercontinuum_charter(charter)

    active_max = (
        max_active_continuums
        if max_active_continuums is not None
        else resumed_max_active
    )

    if not active_charter and not continuum_states:
        raise HypercontinuumRefused(
            "hypercontinuum_empty",
            "continuum charter has no admitable realm slots",
        )

    lid = (
        hypercontinuum_id
        or resume_hypercontinuum_id
        or f"hypercontinuum-{utc_now_iso().replace(':', '').replace('-', '')}"
    )

    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        hypercontinuum_dir = Path(out_root)
        if (hypercontinuum_dir / "hypercontinuum.json").is_file():
            hypercontinuum_dir = hypercontinuum_dir / stamp
    else:
        hypercontinuum_dir = ARTIFACTS_ROOT / stamp
    hypercontinuum_dir.mkdir(parents=True, exist_ok=True)
    # Keep nested artifact paths short (Windows MAX_PATH / deep plane nesting).
    # Child continuum trees already consume most of MAX_PATH; place their roots
    # on a flat ultra-short base (not under hypercontinuum_dir) so one extra
    # federation layer still fits on Windows.
    import os as _os

    if league_out_root is not None:
        lg_root = Path(league_out_root)
    elif _os.name == "nt":
        lg_root = Path("C:/t") / "h"
    else:
        lg_root = hypercontinuum_dir / "e"
    lg_root.mkdir(parents=True, exist_ok=True)
    if _os.name == "nt":
        inst_flat_root = Path("C:/t") / "i"
    else:
        inst_flat_root = hypercontinuum_dir / "x"
    inst_flat_root.mkdir(parents=True, exist_ok=True)
    # Per-run namespace so parallel/resumed hypercontinua do not collide.
    # Prefer a short random token over the human lid (often "hypercontinuum-…")
    # so Windows paths stay short and never re-enter a prior continuum_dir that
    # already has continuum.json (which forces an extra timestamp segment).
    import secrets as _secrets

    _run_ns = _secrets.token_hex(2)
    lg_root = lg_root / _run_ns
    inst_flat_root = inst_flat_root / _run_ns
    lg_root.mkdir(parents=True, exist_ok=True)
    inst_flat_root.mkdir(parents=True, exist_ok=True)

    initial_admissions = admit_pending_slots(
        hypercontinuum_dir=hypercontinuum_dir,
        charter=active_charter,
        continuum_states=continuum_states,
        max_active_continuums=active_max,
        round_index=prior_round_count,
    )
    admissions.extend(initial_admissions)

    if not continuum_states and not pending_charter_slots(
        active_charter, continuum_states
    ):
        raise HypercontinuumRefused("hypercontinuum_empty", "no realm slots admitted")
    if not continuum_states and pending_charter_slots(
        active_charter, continuum_states
    ):
        raise HypercontinuumRefused(
            "hypercontinuum_empty",
            "no realm slots admitted under max_active_continuums policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in continuum_states]
        )

    portfolio_start_digest = federated_portfolio.get("portfolio_digest")

    institutions: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    hypercontinuum_met = False
    terminal_reopen_count = 0
    max_terminal_reopens = max(2, (len(continuum_states) or 1) * 4)
    coverage_end: dict[str, Any] = hypercontinuum_terminal_coverage(
        continuum_states=continuum_states,
        federated_portfolio=federated_portfolio,
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index

        mid_admissions = admit_pending_slots(
            hypercontinuum_dir=hypercontinuum_dir,
            charter=active_charter,
            continuum_states=continuum_states,
            max_active_continuums=active_max,
            round_index=round_index,
        )
        if mid_admissions:
            admissions.extend(mid_admissions)

        coverage_before = hypercontinuum_terminal_coverage(
            continuum_states=continuum_states,
            federated_portfolio=federated_portfolio,
        )

        if constitution_satisfied(
            continuum_states=continuum_states,
            charter=active_charter,
            hypercontinuum_goal=hypercontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "hypercontinuum_met"
            hypercontinuum_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_continuum(
            continuum_states, roi_history, round_index=round_index
        )
        if selected is None:
            # Children may all report met while federated terminal coverage is
            # still incomplete (e.g. deferred surfaces). Only declare hypercontinuum
            # met when the active hypercontinuum_goal is actually satisfied.
            if constitution_satisfied(
                continuum_states=continuum_states,
                charter=active_charter,
                hypercontinuum_goal=hypercontinuum_goal,
                federated_portfolio=federated_portfolio,
            ):
                stop_reason = "hypercontinuum_met"
                hypercontinuum_met = True
                coverage_end = coverage_before
                break
            if (
                hypercontinuum_goal == "terminal_coverage"
                and terminal_reopen_count < max_terminal_reopens
            ):
                reopened = reopen_incomplete_continuums(
                    continuum_states,
                    federated_portfolio=federated_portfolio,
                )
                if reopened:
                    terminal_reopen_count += 1
                    selected = select_next_continuum(
                        continuum_states, roi_history, round_index=round_index
                    )
            if selected is None:
                stop_reason = "hypercontinuum_idle"
                coverage_end = coverage_before
                break

        open_count = sum(
            1 for ist in continuum_states if not ist.get("continuum_met")
        )
        allocated = allocate_continuum_budget(
            remaining_budget=remaining_budget,
            open_continuum_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        continuum_id = str(selected["continuum_id"])
        resume_continuum_dir = selected.get("last_continuum_dir")
        continuum_resume: Path | None = None
        if (
            resume_continuum_dir
            and (Path(str(resume_continuum_dir)) / "continuum_state.json").is_file()
            and not selected.get("continuum_met")
        ):
            continuum_resume = Path(str(resume_continuum_dir))

        # Ultra-short stamp (continuum adds a plane; Windows MAX_PATH is tight).
        safe_id = "".join(c if c.isalnum() else "" for c in continuum_id)[:2] or "i"
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
            "continuum_goal": str(
                selected.get("continuum_goal") or "all_omniverses_met"
            ),
            "continuum_id": continuum_id,
            "out_root": out_dir,
            "league_out_root": inst_out,
        }
        max_active_omniverses = selected.get("max_active_omniverses")
        if max_active_omniverses is None:
            max_active_omniverses = selected.get("max_active_cosmoses")
        if max_active_omniverses is None:
            max_active_omniverses = selected.get("max_active_civilizations")
        if max_active_omniverses is not None:
            continuum_kwargs["max_active_omniverses"] = int(
                max_active_omniverses
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
        except uc.ContinuumRefused as exc:
            if local_index == 0 and not resumed:
                raise HypercontinuumRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"continuum_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except up.ProgramRefused as exc:
            if local_index == 0 and not resumed:
                raise HypercontinuumRefused(exc.verdict, exc.detail) from exc
            stop_reason = f"program_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except uf.FleetRefused as exc:
            if local_index == 0 and not resumed:
                raise HypercontinuumRefused(exc.verdict, exc.detail) from exc
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
        nested_continuum_dir = continuum_result.get("continuum_dir")
        nested_multiverse_states: list[dict[str, Any]] = []
        nested_receipt_path = (
            Path(str(nested_continuum_dir)) / "continuum.json"
            if nested_continuum_dir
            else None
        )
        if nested_receipt_path is not None and nested_receipt_path.is_file():
            receipt = json.loads(nested_receipt_path.read_text(encoding="utf-8"))
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(
                receipt.get("omniverse_states")
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
                continuum_result.get("omniverse_states")
                or continuum_result.get("omniverse_states")
                or continuum_result.get("multiverse_states")
                or continuum_result.get("cosmos_states")
                or continuum_result.get("civilization_states")
                or continuum_result.get("empire_states")
                or []
            ):
                if isinstance(ist, Mapping):
                    nested_multiverse_states.append(dict(ist))

        for i, lst in enumerate(continuum_states):
            if str(lst.get("continuum_id")) != continuum_id:
                continue
            updated = dict(lst)
            updated["last_continuum_dir"] = continuum_result.get("continuum_dir")
            updated["last_continuum_digest"] = continuum_result.get("continuum_digest")
            updated["continuum_met"] = bool(continuum_result.get("continuum_met"))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_multiverse_states:
                updated["omniverse_states"] = nested_multiverse_states
                updated["multiverse_states"] = nested_multiverse_states
                updated["cosmos_states"] = nested_multiverse_states
                updated["civilization_states"] = nested_multiverse_states
                updated["empire_states"] = nested_multiverse_states
            continuum_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in continuum_states]
        )
        coverage_after = hypercontinuum_terminal_coverage(
            continuum_states=continuum_states,
            federated_portfolio=federated_portfolio,
        )

        roi = score_continuum_roi(
            round_index=round_index,
            continuum_id=continuum_id,
            continuum_result=continuum_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)

        idigest = str(continuum_result.get("continuum_digest") or "")
        if idigest:
            continuum_digests.append(idigest)

        rec = _continuum_round_record(
            round_index=round_index,
            continuum_id=continuum_id,
            continuum_result=continuum_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
            budget_allocated=allocated,
            roi=roi,
        )
        institutions.append(rec)

        post_admissions = admit_pending_slots(
            hypercontinuum_dir=hypercontinuum_dir,
            charter=active_charter,
            continuum_states=continuum_states,
            max_active_continuums=active_max,
            round_index=round_index + 1,
        )
        if post_admissions:
            admissions.extend(post_admissions)
            coverage_after = hypercontinuum_terminal_coverage(
                continuum_states=continuum_states,
                federated_portfolio=federated_portfolio,
            )

        write_hypercontinuum_state(
            hypercontinuum_dir,
            _state_payload(
                hypercontinuum_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                continuum_states=continuum_states,
                continuum_digests=continuum_digests,
                charter=active_charter,
                stop_reason=None,
                hypercontinuum_goal=hypercontinuum_goal,
                max_active_continuums=active_max,
                admissions=admissions,
                charter_expansions=charter_expansions,
            ),
        )

        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not continuum_result.get("continuum_met")
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
                    "continuum_states": continuum_states,
                    "last_continuum_id": continuum_id,
                    "federated_portfolio": federated_portfolio,
                    "hypercontinuum_dir": str(hypercontinuum_dir),
                    "pending_continuum_ids": [
                        str(s.get("continuum_id") or "")
                        for s in pending_charter_slots(
                            active_charter, continuum_states
                        )
                    ],
                    "admissions": admissions,
                    "charter_expansions": charter_expansions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        # Grow constitution before declaring hypercontinuum_met when expand remains.
        if (
            charter_expand is not None
            and not pending_charter_slots(active_charter, continuum_states)
            and continuums_all_met(continuum_states)
        ):
            growth = charter_expand(
                active_charter=active_charter,
                continuum_states=continuum_states,
                round_index=round_index,
                roi_history=roi_history,
            )
            if growth.get("expanded") and growth.get("charter"):
                active_charter = normalize_hypercontinuum_charter(
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
                    hypercontinuum_dir=hypercontinuum_dir,
                    charter=active_charter,
                    continuum_states=continuum_states,
                    max_active_continuums=active_max,
                    round_index=round_index + 1,
                )
                if post_growth:
                    admissions.extend(post_growth)
                write_hypercontinuum_state(
                    hypercontinuum_dir,
                    _state_payload(
                        hypercontinuum_id=lid,
                        round_count=round_index + 1,
                        total_dispatched=total_dispatched,
                        total_dispatched_ok=total_dispatched_ok,
                        federated_portfolio=federated_portfolio,
                        roi_history=roi_history,
                        continuum_states=continuum_states,
                        continuum_digests=continuum_digests,
                        charter=active_charter,
                        stop_reason=None,
                        hypercontinuum_goal=hypercontinuum_goal,
                        max_active_continuums=active_max,
                        admissions=admissions,
                        charter_expansions=charter_expansions,
                    ),
                )
                # Continue the outer loop with the grown charter.
                continue

        if constitution_satisfied(
            continuum_states=continuum_states,
            charter=active_charter,
            hypercontinuum_goal=hypercontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "hypercontinuum_met"
            hypercontinuum_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            continuum_states=continuum_states,
            charter=active_charter,
            hypercontinuum_goal=hypercontinuum_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = "hypercontinuum_idle"
            break
    else:
        stop_reason = "max_rounds"

    final_admissions = admit_pending_slots(
        hypercontinuum_dir=hypercontinuum_dir,
        charter=active_charter,
        continuum_states=continuum_states,
        max_active_continuums=active_max,
        round_index=prior_round_count + len(institutions),
    )
    if final_admissions:
        admissions.extend(final_admissions)

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in continuum_states]
    )
    coverage_end = hypercontinuum_terminal_coverage(
        continuum_states=continuum_states,
        federated_portfolio=federated_portfolio,
    )
    if constitution_satisfied(
        continuum_states=continuum_states,
        charter=active_charter,
        hypercontinuum_goal=hypercontinuum_goal,
        federated_portfolio=federated_portfolio,
    ):
        hypercontinuum_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    roi_summary = _roi_summary(roi_history)
    continuums_met_count = sum(
        1 for ist in continuum_states if ist.get("continuum_met")
    )
    pending_remaining = [
        str(s.get("continuum_id") or "")
        for s in pending_charter_slots(active_charter, continuum_states)
    ]

    if hypercontinuum_met and stop_reason in {"hypercontinuum_met", "max_rounds"}:
        verdict = "hypercontinuum_met"
        ok = True
        stop_reason = "hypercontinuum_met"
    elif stop_reason == "rank_only":
        verdict = "hypercontinuum_ranked"
        ok = True
    elif stop_reason == "hypercontinuum_idle":
        verdict = "hypercontinuum_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = "hypercontinuum_budgeted"
        ok = True
    elif stop_reason.startswith("domain_refused") or stop_reason.startswith(
        "program_refused"
    ) or stop_reason.startswith("fleet_refused"):
        verdict = "continuum_refused_mid"
        ok = False
    else:
        verdict = "hypercontinuum_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "hypercontinuum_id": lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        "max_active_continuums": active_max,
        "max_epochs_per_succession": max_epochs_per_succession,
        "max_waves_per_epoch": max_waves_per_epoch,
        "per_wave_dispatch_limit": per_wave_dispatch_limit,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        "hypercontinuum_goal": hypercontinuum_goal,
        "hypercontinuum_met": hypercontinuum_met,
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
        "continuums": institutions,
        "continuum_digests": [
            i.get("continuum_digest")
            for i in institutions
            if i.get("continuum_digest")
        ],
        "continuum_states": continuum_states,
        "continuums_admitted": len(continuum_states),
        "continuums_met_count": continuums_met_count,
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
    receipt["continuum_digests"] = [
        str(i.get("continuum_digest") or "") for i in institutions
    ]
    receipt["hypercontinuum_digest"] = _sha256_json(_hypercontinuum_digest_payload(receipt))
    atomic_write_json(hypercontinuum_dir / "hypercontinuum.json", receipt)
    atomic_write_json(
        hypercontinuum_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            "hypercontinuum_id": receipt["hypercontinuum_id"],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            "hypercontinuum_met": receipt["hypercontinuum_met"],
            "continuums_admitted": receipt["continuums_admitted"],
            "continuums_met_count": receipt["continuums_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "charter_expansion_count": receipt["charter_expansion_count"],
            "max_active_continuums": receipt["max_active_continuums"],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            "portfolio_start_digest": receipt["portfolio_start_digest"],
            "portfolio_end_digest": receipt["portfolio_end_digest"],
            "hypercontinuum_digest": receipt["hypercontinuum_digest"],
            "resumed": resumed,
        },
    )

    write_hypercontinuum_state(
        hypercontinuum_dir,
        _state_payload(
            hypercontinuum_id=lid,
            round_count=prior_round_count + len(institutions),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            continuum_states=continuum_states,
            continuum_digests=receipt["continuum_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            hypercontinuum_goal=hypercontinuum_goal,
            max_active_continuums=active_max,
            admissions=admissions,
            charter_expansions=charter_expansions,
        ),
    )

    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        "hypercontinuum_dir": str(hypercontinuum_dir),
        "hypercontinuum_digest": receipt["hypercontinuum_digest"],
        "hypercontinuum_id": lid,
        "round_count": len(institutions),
        "continuum_digests": list(receipt["continuum_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "hypercontinuum_met": hypercontinuum_met,
        "continuums_admitted": len(continuum_states),
        "continuums_met_count": continuums_met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        "max_active_continuums": active_max,
        "admissions": admissions,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": list(receipt["charter_expanded_ids"]),
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "continuum_states": continuum_states,
        "roi_summary": roi_summary,
        "resumed": resumed,
        "continuums": institutions,
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
    return uc._program_slot(
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
    return uc._inst_slot(
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
    return uc._commonwealth_slot(
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
    return uc._domain_slot(
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
    return uc._realm_slot(
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
    return uc._empire_slot(
        empire_id,
        priority=priority,
        realms=realms,
        institutions=institutions,
        max_rounds=max_rounds,
        empire_goal=empire_goal,
        max_active_realms=max_active_realms,
    )


def _continuum_slot(
    continuum_id: str,
    *,
    priority: int = 0,
    omniverses: Sequence[dict[str, Any]] | None = None,
    multiverses: Sequence[dict[str, Any]] | None = None,
    cosmoses: Sequence[dict[str, Any]] | None = None,
    civilizations: Sequence[dict[str, Any]] | None = None,
    empires: Sequence[dict[str, Any]] | None = None,
    realms: Sequence[dict[str, Any]] | None = None,
    institutions: Sequence[dict[str, Any]] | None = None,
    max_rounds: int = 6,
    continuum_goal: str = "all_omniverses_met",
    max_active_omniverses: int | None = None,
) -> dict[str, Any]:
    """Build a hermetic hypercontinuum charter continuum slot.

    Prefer ``omniverses=`` (nested omniverse slots for the continuum plane).
    ``institutions=`` wrap a single auto omniverse with multiverse nesting underneath.
    """
    nested: list[dict[str, Any]]
    if omniverses is not None:
        nested = list(omniverses)
    elif multiverses is not None:
        nested = [
            uc._omniverse_slot(
                f"{continuum_id[:1]}v",
                multiverses=list(multiverses),
                max_rounds=max_rounds,
            )
        ]
    elif cosmoses is not None:
        nested = [
            uc._omniverse_slot(
                f"{continuum_id[:1]}v",
                cosmoses=list(cosmoses),
                max_rounds=max_rounds,
            )
        ]
    elif civilizations is not None:
        nested = [
            uc._omniverse_slot(
                f"{continuum_id[:1]}v",
                civilizations=list(civilizations),
                max_rounds=max_rounds,
            )
        ]
    elif empires is not None:
        nested = [
            uc._omniverse_slot(
                f"{continuum_id[:1]}v",
                empires=list(empires),
                max_rounds=max_rounds,
            )
        ]
    elif realms is not None:
        nested = [
            uc._omniverse_slot(
                f"{continuum_id[:1]}v",
                realms=list(realms),
                max_rounds=max_rounds,
            )
        ]
    elif institutions:
        nested = [
            uc._omniverse_slot(
                f"{continuum_id[:1]}v",
                institutions=list(institutions),
                max_rounds=max_rounds,
            )
        ]
    else:
        nested = []
    return {
        "continuum_id": continuum_id,
        "priority": priority,
        "charter": nested,
        "max_rounds": max_rounds,
        "continuum_goal": continuum_goal,
        "max_active_omniverses": max_active_omniverses,
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


def builtin_upstream_hypercontinuum_proof() -> dict[str, Any]:
    """Hermetic end-to-end proof of the multi-continuum continuum plane (no network)."""
    scratch = _proof_scratch()
    try:
        campaign = _proof_campaign_runner(scratch)

        # Two realms; ultra-short ids for Windows nested artifact paths.
        charter = [
            _continuum_slot(
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
            _continuum_slot(
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

        confed = run_hypercontinuum(
            charter=charter,
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign,
            hypercontinuum_goal="all_continuums_met",
            out_root=scratch / "m",
        )
        multi_hypercontinuum_ok = (
            confed["ok"]
            and confed["hypercontinuum_met"] is True
            and confed["stop_reason"] == "hypercontinuum_met"
            and confed["continuums_admitted"] == 2
            and confed["continuums_met_count"] == 2
            and confed["round_count"] >= 2
            and confed["total_dispatched_ok"] >= 3
            and float((confed.get("coverage_end") or {}).get("coverage_ratio") or 0)
            == 1.0
        )
        scheduled_ids = {
            i.get("continuum_id") for i in (confed.get("continuums") or confed.get("realms") or [])
        }
        multi_hypercontinuum_scheduled = multi_hypercontinuum_ok and scheduled_ids >= {"a", "b"}

        verified = verify_hypercontinuum_receipt(Path(confed["hypercontinuum_dir"]))
        seal_ok = bool(verified.get("ok")) and verified.get("round_count") == confed[
            "round_count"
        ]

        # Tamper detection.
        confed_path = Path(confed["hypercontinuum_dir"]) / "hypercontinuum.json"
        receipt = json.loads(confed_path.read_text(encoding="utf-8"))
        receipt["hypercontinuum_digest"] = "0" * 64
        confed_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = verify_hypercontinuum_receipt(Path(confed["hypercontinuum_dir"]))
        tamper_detected = (
            not tampered["ok"]
            and "hypercontinuum_digest" in (tampered.get("mismatched") or [])
        )

        # Budget stop across leagues.
        campaign2 = _proof_campaign_runner(scratch / "b")
        budgeted = run_hypercontinuum(
            charter=[
                _continuum_slot(
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
                _continuum_slot(
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
            hypercontinuum_goal="none",
            out_root=scratch / "g",
        )
        budget_ok = (
            budgeted["ok"]
            and budgeted["total_dispatched"] == 1
            and budgeted["stop_reason"] == "dispatch_budget"
        )

        # Pre-met short circuit via custom continuum_runner.
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
            nested_charter = uc.normalize_continuum_charter(kwargs.get("charter"))
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
                "verdict": "continuum_met",
                "stop_reason": "continuum_met",
                "continuum_id": kwargs.get("continuum_id"),
                "continuum_met": True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "civilizations_admitted": len(nested_charter),
                "civilizations_met_count": len(nested_charter),
                "continuum_digest": digest,
                "federated_portfolio": portfolio,
                "civilization_states": civilization_states,
                "coverage_end": {
                    "required": len(entries),
                    "covered": len(entries),
                    "met": True,
                    "coverage_ratio": 1.0,
                },
            }
            atomic_write_json(out / "continuum.json", receipt)
            atomic_write_json(
                out / "continuum_state.json",
                {
                    "continuum_id": kwargs.get("continuum_id"),
                    "round_count": 0,
                    "total_dispatched": 0,
                    "total_dispatched_ok": 0,
                    "federated_portfolio": portfolio,
                    "civilization_states": civilization_states,
                    "stop_reason": "continuum_met",
                    "charter": nested_charter,
                },
            )
            return {
                "ok": True,
                "verdict": "continuum_met",
                "stop_reason": "continuum_met",
                "continuum_dir": str(out),
                "continuum_digest": digest,
                "continuum_id": kwargs.get("continuum_id"),
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "continuum_met": True,
                "civilizations_admitted": len(nested_charter),
                "civilizations_met_count": len(nested_charter),
                "coverage_end": receipt["coverage_end"],
                "federated_portfolio": portfolio,
                "civilization_states": civilization_states,
                "used_skill_route_discovery": False,
            }

        pre_met = run_hypercontinuum(
            charter=[
                _continuum_slot(
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
            continuum_runner=_premet_runner,
            hypercontinuum_goal="all_continuums_met",
            out_root=scratch / "p",
        )
        premet_ok = (
            pre_met["ok"]
            and pre_met["hypercontinuum_met"] is True
            and pre_met["stop_reason"] == "hypercontinuum_met"
            and pre_met["continuums_met_count"] == 1
            and pre_met["total_dispatched"] == 0
        )

        # Rank-only domain.
        ranked = run_hypercontinuum(
            charter=[
                _continuum_slot(
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
                _continuum_slot(
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
            hypercontinuum_goal="none",
            out_root=scratch / "k",
        )
        rank_only_ok = (
            ranked["ok"]
            and ranked["verdict"] == "hypercontinuum_ranked"
            and ranked["stop_reason"] == "rank_only"
            and ranked["total_dispatched"] == 0
            and ranked["round_count"] >= 1
        )

        # Empty charter refuses.
        empty_refused = False
        try:
            run_hypercontinuum(
                charter=[],
                dispatch=False,
                hypercontinuum_goal="none",
                out_root=scratch / "z",
            )
        except HypercontinuumRefused as exc:
            empty_refused = exc.verdict in {
                "hypercontinuum_empty",
                "hypercontinuum_invalid",
            }

        # Custom stop_when.
        campaign3 = _proof_campaign_runner(scratch / "stop")
        custom = run_hypercontinuum(
            charter=[
                _continuum_slot(
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
                _continuum_slot(
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
            hypercontinuum_goal="none",
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
        partial = run_hypercontinuum(
            charter=[
                _continuum_slot(
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
                _continuum_slot(
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
            hypercontinuum_goal="none",
            hypercontinuum_id="rcp",
            out_root=scratch / "a",
        )
        state_path = Path(partial["hypercontinuum_dir"]) / "hypercontinuum_state.json"
        state_exists = state_path.is_file()
        campaign5 = _proof_campaign_runner(scratch / "rb")
        resumed = run_hypercontinuum(
            resume_dir=Path(partial["hypercontinuum_dir"]),
            max_rounds=4,
            max_epochs_per_succession=2,
            max_waves_per_epoch=2,
            per_wave_dispatch_limit=1,
            dispatch_budget=4,
            dispatch=True,
            campaign_runner=campaign5,
            hypercontinuum_goal="none",
            out_root=scratch / "r",
        )
        resume_ok = (
            partial["ok"]
            and state_exists
            and resumed["ok"]
            and resumed["resumed"] is True
            and resumed["hypercontinuum_id"] == "rcp"
            and resumed["total_dispatched"] > partial["total_dispatched"]
        )

        # ROI scoring + multi-league budget allocation evidence.
        roi_ok = (
            isinstance(confed.get("roi_summary"), Mapping)
            and int((confed["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((confed["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
            and isinstance((confed["roi_summary"] or {}).get("by_continuum"), Mapping)
            and len((confed["roi_summary"] or {}).get("by_continuum") or {}) >= 2
        )

        first_cw = (confed.get("continuums") or confed.get("realms") or [{}])[0].get("continuum_id")
        priority_ok = first_cw == "a"

        # Federation: inventories across both continuums form a joint surface.
        fed_keys: set[tuple[str, str, str]] = set()
        for est in confed.get("continuum_states") or []:
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
        federation_ok = multi_hypercontinuum_ok and (
            len(fed_keys) >= 3
            or float(fed_portfolio.get("coverage_ratio") or 0) == 1.0
            and int(fed_portfolio.get("required") or 0) >= 3
        )

        # Deferred admission: max_active=1 grows domain charter over time.
        campaign6 = _proof_campaign_runner(scratch / "dc")
        deferred = run_hypercontinuum(
            charter=[
                _continuum_slot(
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
                _continuum_slot(
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
                _continuum_slot(
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
            max_active_continuums=1,
            dispatch=True,
            campaign_runner=campaign6,
            hypercontinuum_goal="all_continuums_met",
            out_root=scratch / "d",
        )
        admit_rounds = [
            a.get("admitted_at_round")
            for a in (deferred.get("admissions") or [])
            if a.get("admitted_at_round") is not None
        ]
        admit_ids = [a.get("continuum_id") for a in (deferred.get("admissions") or [])]
        deferred_ok = (
            deferred["ok"]
            and deferred["hypercontinuum_met"] is True
            and deferred["continuums_admitted"] == 3
            and deferred["continuums_met_count"] == 3
            and deferred.get("max_active_continuums") == 1
            and not (deferred.get("pending_remaining") or [])
            and admit_ids == ["da", "db", "dc"]
            and len(set(admit_rounds)) >= 2
            and min(admit_rounds) == 0
        )

        # Charter expansion: start with one domain; grow constitution mid-run.
        campaign7 = _proof_campaign_runner(scratch / "xg")
        expand_runner = make_hypercontinuum_charter_expand(
            [
                _continuum_slot(
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
        expanded = run_hypercontinuum(
            charter=[
                _continuum_slot(
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
            max_active_continuums=1,
            dispatch=True,
            campaign_runner=campaign7,
            charter_expand=expand_runner,
            hypercontinuum_goal="all_continuums_met",
            out_root=scratch / "x",
        )
        expand_ok = (
            expanded["ok"]
            and expanded["hypercontinuum_met"] is True
            and expanded["continuums_admitted"] == 2
            and expanded["continuums_met_count"] == 2
            and int(expanded.get("charter_expansion_count") or 0) >= 1
            and "xg" in set(expanded.get("charter_expanded_ids") or [])
            and not (expanded.get("pending_remaining") or [])
        )

        # merge_hypercontinuum_charter unit evidence (ids de-dupe, additions append).
        merged = merge_hypercontinuum_charter(
            [_continuum_slot("m1", institutions=[_inst_slot("mi", programs=[_program_slot("mp", initial=[("m", "1.0.0", "m-1")])])])],
            [
                _continuum_slot("m1", institutions=[_inst_slot("mi2", programs=[_program_slot("mp2", initial=[("m2", "1.0.0", "m2-1")])])]),
                _continuum_slot("m2", institutions=[_inst_slot("mj", programs=[_program_slot("mq", initial=[("n", "1.0.0", "n-1")])])]),
            ],
        )
        merge_ok = [s["continuum_id"] for s in merged] == ["m1", "m2"]

        # Terminal-coverage constitution goal: hypercontinuum_met when federated
        # inventory is fully terminal-success (not only per-continuum met flags).
        # Uses the same multi-defect shape as the main multi-continuum run so
        # nested deferred surface expansion is exercised under terminal_coverage.
        campaign8 = _proof_campaign_runner(scratch / "tc")
        terminal = run_hypercontinuum(
            charter=[
                _continuum_slot(
                    "t1",
                    priority=2,
                    institutions=[
                        _inst_slot(
                            "ti",
                            programs=[
                                _program_slot(
                                    "tp",
                                    priority=1,
                                    initial=[("tau", "1.0.0", "tau-dos")],
                                )
                            ],
                            max_rounds=4,
                        )
                    ],
                    max_rounds=4,
                ),
                _continuum_slot(
                    "t2",
                    priority=1,
                    institutions=[
                        _inst_slot(
                            "tj",
                            programs=[
                                _program_slot(
                                    "tq",
                                    priority=1,
                                    initial=[("upsilon", "2.0.0", "ups-xss")],
                                    deferred=[("phi", "3.0.0", "phi-rce")],
                                )
                            ],
                            max_rounds=5,
                        )
                    ],
                    max_rounds=5,
                ),
            ],
            max_rounds=8,
            max_epochs_per_succession=3,
            max_waves_per_epoch=3,
            per_wave_dispatch_limit=1,
            dispatch_budget=12,
            dispatch=True,
            campaign_runner=campaign8,
            hypercontinuum_goal="terminal_coverage",
            out_root=scratch / "tc",
        )
        cov_end = terminal.get("coverage_end") or {}
        terminal_ok = (
            terminal["ok"]
            and terminal["hypercontinuum_met"] is True
            and terminal["stop_reason"] == "hypercontinuum_met"
            and float(cov_end.get("coverage_ratio") or 0) == 1.0
            and int(cov_end.get("required") or 0) >= 3
            and bool(cov_end.get("met"))
            and not (terminal.get("pending_remaining") or [])
            and terminal["continuums_admitted"] == 2
            and terminal["total_dispatched_ok"] >= 3
        )

        ok = all(
            [
                multi_hypercontinuum_ok,
                multi_hypercontinuum_scheduled,
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
            "hypercontinuum_met": multi_hypercontinuum_ok,
            "multi_hypercontinuum_progressed": multi_hypercontinuum_scheduled,
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
            "hypercontinuum_digest": confed.get("hypercontinuum_digest"),
            "round_count": confed.get("round_count"),
            "total_dispatched_ok": confed.get("total_dispatched_ok"),
            "continuums_admitted": confed.get("continuums_admitted"),
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "flags": {
                "multi_hypercontinuum_ok": multi_hypercontinuum_ok,
                "multi_hypercontinuum_scheduled": multi_hypercontinuum_scheduled,
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
        result = verify_hypercontinuum_receipt(Path(args.verify))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    if args.proof:
        result = builtin_upstream_hypercontinuum_proof()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
