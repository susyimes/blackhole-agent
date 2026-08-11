
"""Generic multi-child durable stewardship constitution engine.

Collapses the continuum copy-paste tower (continuum..quettacontinuum) into one
noun-parameterized implementation: admit, schedule, child-run, federate, retire,
expand, persist, seal. New outer layers are ConstitutionLayer nouns + a child
runner — not another ~2800-line rename. No skill-route discovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
TERMINAL_SUCCESS_OUTCOMES = frozenset({"impact_released", "impact_merged"})


class ConstitutionRefused(Exception):
    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


@dataclass(frozen=True)
class ConstitutionLayer:
    name: str
    child: str
    artifacts_relative: str = ""
    kind_default: str = ""

    @property
    def plural(self) -> str:
        return f"{self.child}s"

    @property
    def child_id_field(self) -> str:
        return f"{self.child}_id"

    @property
    def child_met_field(self) -> str:
        return f"{self.child}_met"

    @property
    def child_digest_field(self) -> str:
        return f"{self.child}_digest"

    @property
    def child_dir_field(self) -> str:
        return f"{self.child}_dir"

    @property
    def child_goal_field(self) -> str:
        return f"{self.child}_goal"

    @property
    def self_id_field(self) -> str:
        return f"{self.name}_id"

    @property
    def self_met_field(self) -> str:
        return f"{self.name}_met"

    @property
    def self_goal_field(self) -> str:
        return f"{self.name}_goal"

    @property
    def self_digest_field(self) -> str:
        return f"{self.name}_digest"

    @property
    def max_active_field(self) -> str:
        return f"max_active_{self.plural}"

    @property
    def all_children_met_goal(self) -> str:
        return f"all_{self.plural}_met"

    @property
    def artifacts_root(self) -> Path:
        rel = self.artifacts_relative or f"artifacts/upstream-{self.name}"
        return REPO_ROOT / rel

    @property
    def slot_kind(self) -> str:
        return self.kind_default or f"stewardship_{self.child}"


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


def make_portfolio(entries: Sequence[Mapping[str, Any]], *, source: str) -> dict[str, Any]:
    portfolio: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "entries": [dict(e) for e in entries],
        "source": source,
    }
    portfolio["portfolio_digest"] = _recompute_portfolio_digest(portfolio)
    return portfolio


NESTED_WALK_FIELDS = (
    "charter", "programs", "institutions", "leagues", "confederations",
    "commonwealths", "domains", "realms", "empires", "civilizations",
    "cosmoses", "multiverses", "omniverses", "continuums", "hypercontinuums",
    "ultracontinuums", "megacontinuums", "gigacontinuums", "teracontinuums",
    "petacontinuums", "exacontinuums", "zettacontinuums", "yottacontinuums",
    "ronnacontinuums", "quettacontinuums", "children", "child_states",
    "program_states", "institution_states", "league_states",
    "confederation_states", "commonwealth_states", "domain_states",
    "realm_states", "empire_states", "civilization_states", "cosmos_states",
    "multiverse_states", "omniverse_states", "continuum_states",
    "hypercontinuum_states", "ultracontinuum_states", "megacontinuum_states",
    "gigacontinuum_states", "teracontinuum_states", "petacontinuum_states",
    "exacontinuum_states", "zettacontinuum_states", "yottacontinuum_states",
    "ronnacontinuum_states", "quettacontinuum_states",
)


def _collect_program_target_keys(pslot: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    keys: list[tuple[str, str, str]] = []
    for tgt in list(pslot.get("initial_targets") or []) + list(pslot.get("surface_charter") or []):
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


def collect_inventory_keys(node: Mapping[str, Any] | None, *, depth: int = 0) -> list[tuple[str, str, str]]:
    if not isinstance(node, Mapping) or depth > 24:
        return []
    keys: list[tuple[str, str, str]] = []
    for raw in list(node.get("inventory_keys") or []):
        if isinstance(raw, (list, tuple)) and len(raw) >= 3:
            keys.append((str(raw[0]), str(raw[1]), str(raw[2])))
        elif isinstance(raw, Mapping):
            n, v = str(raw.get("name") or ""), str(raw.get("version") or "")
            d = str(raw.get("defect_id") or raw.get("id") or "")
            if n and d:
                keys.append((n, v, d))
    keys.extend(_collect_program_target_keys(node))
    for field in NESTED_WALK_FIELDS:
        for child in list(node.get(field) or []):
            if isinstance(child, Mapping):
                keys.extend(collect_inventory_keys(child, depth=depth + 1))
    seen: set[tuple[str, str, str]] = set()
    out: list[tuple[str, str, str]] = []
    for k in keys:
        if k not in seen and k[0] and k[2]:
            seen.add(k)
            out.append(k)
    return out


def terminal_coverage(
    *,
    child_states: Sequence[Mapping[str, Any]],
    federated_portfolio: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required: list[tuple[str, str, str]] = []
    for st in child_states:
        if isinstance(st, Mapping):
            required.extend(collect_inventory_keys(st))
    seen: set[tuple[str, str, str]] = set()
    uniq: list[tuple[str, str, str]] = []
    for k in required:
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    covered_keys: set[tuple[str, str, str]] = set()
    for e in _portfolio_entries(federated_portfolio):
        if str(e.get("outcome") or "") in TERMINAL_SUCCESS_OUTCOMES:
            key = _entry_key(e)
            if key[0] and key[2]:
                covered_keys.add(key)
    open_or_missing = [
        {"name": n, "version": v, "defect_id": d}
        for (n, v, d) in uniq
        if (n, v, d) not in covered_keys
    ]
    req_n = len(uniq)
    cov_n = req_n - len(open_or_missing)
    ratio = (cov_n / req_n) if req_n else 1.0
    return {
        "required": req_n,
        "covered": cov_n,
        "met": req_n == 0 or len(open_or_missing) == 0,
        "coverage_ratio": ratio,
        "open_or_missing": open_or_missing,
    }


def normalize_charter(
    layer: ConstitutionLayer,
    charter: Sequence[Mapping[str, Any]] | None,
    *,
    nested_normalizer: Callable[[Any], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    id_field = layer.child_id_field
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        child_id = str(raw.get(id_field) or raw.get("id") or "").strip()
        if not child_id or child_id in seen:
            continue
        seen.add(child_id)
        nested_raw = (
            raw.get("charter") or raw.get("children") or raw.get("inventory_keys")
            or raw.get("yottacontinuums") or raw.get("zettacontinuums")
            or raw.get("exacontinuums") or raw.get("petacontinuums")
            or raw.get("teracontinuums") or raw.get("gigacontinuums")
            or raw.get("megacontinuums") or raw.get("ultracontinuums")
            or raw.get("hypercontinuums") or raw.get("continuums")
            or raw.get("omniverses") or raw.get("multiverses")
            or raw.get("cosmoses") or raw.get("civilizations")
            or raw.get("empires") or raw.get("realms") or raw.get("domains")
            or raw.get("commonwealths") or raw.get("confederations")
            or raw.get("leagues") or raw.get("institutions") or raw.get("programs")
        )
        nested: list[dict[str, Any]]
        if nested_normalizer is not None and nested_raw is not None and isinstance(nested_raw, list) and (
            not nested_raw or isinstance(nested_raw[0], Mapping)
        ):
            try:
                nested = nested_normalizer(nested_raw)
            except Exception:
                nested = [dict(x) for x in nested_raw if isinstance(x, Mapping)]
        elif isinstance(nested_raw, list) and nested_raw and isinstance(nested_raw[0], (list, tuple)):
            nested = [{"inventory_keys": [tuple(x) for x in nested_raw]}]
        elif isinstance(nested_raw, list):
            nested = [dict(x) for x in nested_raw if isinstance(x, Mapping)]
        elif raw.get("inventory_keys"):
            nested = [{"inventory_keys": list(raw.get("inventory_keys") or [])}]
        else:
            nested = []
        if not nested and raw.get("inventory_keys"):
            nested = [{"inventory_keys": list(raw.get("inventory_keys") or [])}]
        if not nested and collect_inventory_keys(raw):
            nested = [dict(raw)]
        if not nested:
            continue
        max_active_children = raw.get("max_active_children")
        for alias in (
            "max_active_yottacontinuums", "max_active_zettacontinuums",
            "max_active_continuums", "max_active_civilizations",
            "max_active_empires", "max_active_realms", "max_active_domains",
            "max_active_commonwealths", "max_active_confederations",
            "max_active_leagues", "max_active_institutions", "max_active_programs",
        ):
            if max_active_children is None and raw.get(alias) is not None:
                max_active_children = raw.get(alias)
        if max_active_children is not None:
            max_active_children = max(1, int(max_active_children))
        out.append({
            id_field: child_id,
            "priority": int(raw.get("priority") or 0),
            "charter": nested,
            "max_active_children": max_active_children,
            "max_rounds": max(1, int(raw.get("max_rounds") or 6)),
            layer.child_goal_field: str(raw.get(layer.child_goal_field) or "all_children_met"),
            "kind": str(raw.get("kind") or layer.slot_kind),
            "inventory_keys": list(raw.get("inventory_keys") or [])
            or collect_inventory_keys({"charter": nested}),
        })
    return out


def admit_child_slot(
    layer: ConstitutionLayer, *, constitution_dir: Path, slot: Mapping[str, Any]
) -> dict[str, Any]:
    child_id = str(slot.get(layer.child_id_field) or "")
    if not child_id:
        raise ConstitutionRefused(f"{layer.name}_invalid", f"slot missing {layer.child_id_field}")
    child_root = Path(constitution_dir) / layer.plural / child_id
    child_root.mkdir(parents=True, exist_ok=True)
    nested = list(slot.get("charter") or [])
    if not nested and slot.get("inventory_keys"):
        nested = [{"inventory_keys": list(slot.get("inventory_keys") or [])}]
    if not nested:
        raise ConstitutionRefused(
            f"{layer.name}_invalid", f"child slot {child_id!r} has empty nested charter"
        )
    return {
        layer.child_id_field: child_id,
        f"{layer.child}_root": str(child_root),
        "admitted": True,
        "charter": nested,
        "max_active_children": slot.get("max_active_children"),
        "max_rounds": int(slot.get("max_rounds") or 6),
        layer.child_goal_field: str(slot.get(layer.child_goal_field) or "all_children_met"),
        "priority": int(slot.get("priority") or 0),
        "inventory_keys": list(slot.get("inventory_keys") or [])
        or collect_inventory_keys({"charter": nested}),
    }


def pending_charter_slots(
    layer: ConstitutionLayer,
    charter: Sequence[Mapping[str, Any]],
    child_states: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    known = {str(ist.get(layer.child_id_field) or "") for ist in child_states}
    pending = [
        dict(slot)
        for slot in charter
        if str(slot.get(layer.child_id_field) or "")
        and str(slot.get(layer.child_id_field)) not in known
    ]
    pending.sort(
        key=lambda s: (-int(s.get("priority") or 0), str(s.get(layer.child_id_field) or ""))
    )
    return pending


def open_unmet_count(layer: ConstitutionLayer, child_states: Sequence[Mapping[str, Any]]) -> int:
    return sum(1 for ist in child_states if not ist.get(layer.child_met_field))


def children_all_met(layer: ConstitutionLayer, child_states: Sequence[Mapping[str, Any]]) -> bool:
    if not child_states:
        return False
    return all(bool(ist.get(layer.child_met_field)) for ist in child_states)


def admit_pending_slots(
    layer: ConstitutionLayer,
    *,
    constitution_dir: Path,
    charter: Sequence[Mapping[str, Any]],
    child_states: list[dict[str, Any]],
    max_active: int | None,
    round_index: int | None = None,
) -> list[dict[str, Any]]:
    pending = pending_charter_slots(layer, charter, child_states)
    if not pending:
        return []
    open_n = open_unmet_count(layer, child_states)
    capacity = len(pending) if max_active is None else max(0, int(max_active) - open_n)
    if capacity <= 0:
        return []
    admissions: list[dict[str, Any]] = []
    for slot in pending[:capacity]:
        admission = admit_child_slot(layer, constitution_dir=constitution_dir, slot=slot)
        if round_index is not None:
            admission = dict(admission)
            admission["admitted_at_round"] = round_index
        admissions.append(admission)
        child_states.append(
            {
                layer.child_id_field: admission[layer.child_id_field],
                f"{layer.child}_root": admission[f"{layer.child}_root"],
                "charter": admission["charter"],
                "max_active_children": admission.get("max_active_children"),
                "max_rounds": admission["max_rounds"],
                layer.child_goal_field: admission[layer.child_goal_field],
                "priority": admission["priority"],
                layer.child_met_field: False,
                f"last_{layer.child_dir_field}": None,
                f"last_{layer.child_digest_field}": None,
                "portfolio": None,
                "child_states": [],
                "inventory_keys": admission.get("inventory_keys") or [],
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "admitted_at_round": round_index,
            }
        )
    return admissions


def merge_charter(
    layer: ConstitutionLayer,
    existing: Sequence[Mapping[str, Any]] | None,
    additions: Sequence[Mapping[str, Any]] | None,
    *,
    nested_normalizer: Callable[[Any], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    base = normalize_charter(layer, existing, nested_normalizer=nested_normalizer)
    if not additions:
        return base
    known = {str(s.get(layer.child_id_field) or "") for s in base}
    merged: list[Mapping[str, Any]] = list(base)
    for raw in additions:
        if not isinstance(raw, Mapping):
            continue
        cid = str(raw.get(layer.child_id_field) or raw.get("id") or "").strip()
        if not cid or cid in known:
            continue
        known.add(cid)
        merged.append(raw)
    return normalize_charter(layer, merged, nested_normalizer=nested_normalizer)


def federate_portfolios(
    portfolios: Sequence[Mapping[str, Any] | None],
    *,
    source: str = "constitution_federation",
) -> dict[str, Any]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for portfolio in portfolios:
        for entry in _portfolio_entries(portfolio):
            key = _entry_key(entry)
            if not key[0] or not key[2]:
                continue
            by_key[key] = dict(entry)
    entries = [by_key[k] for k in sorted(by_key.keys())]
    return make_portfolio(entries, source=source)


def constitution_satisfied(
    layer: ConstitutionLayer,
    *,
    child_states: Sequence[Mapping[str, Any]],
    charter: Sequence[Mapping[str, Any]],
    goal: str,
    federated_portfolio: Mapping[str, Any] | None = None,
) -> bool:
    if goal == "none":
        return False
    if goal == "terminal_coverage":
        cov = terminal_coverage(
            child_states=child_states, federated_portfolio=federated_portfolio
        )
        return bool(cov.get("met")) and not pending_charter_slots(
            layer, charter, child_states
        )
    if goal in {layer.all_children_met_goal, "all_children_met"}:
        if not child_states or pending_charter_slots(layer, charter, child_states):
            return False
        return children_all_met(layer, child_states)
    return False


def reopen_incomplete_children(
    layer: ConstitutionLayer,
    child_states: list[dict[str, Any]],
    *,
    federated_portfolio: Mapping[str, Any] | None,
) -> list[str]:
    cov = terminal_coverage(
        child_states=child_states, federated_portfolio=federated_portfolio
    )
    if cov.get("met"):
        return []
    reopened: list[str] = []
    for i, ist in enumerate(child_states):
        if not ist.get(layer.child_met_field):
            continue
        updated = dict(ist)
        updated[layer.child_met_field] = False
        child_states[i] = updated
        reopened.append(str(updated.get(layer.child_id_field) or ""))
    return [r for r in reopened if r]


def score_child_roi(
    layer: ConstitutionLayer,
    *,
    round_index: int,
    child_id: str,
    child_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
) -> dict[str, Any]:
    before_ratio = float(coverage_before.get("coverage_ratio") or 0.0)
    after_ratio = float(coverage_after.get("coverage_ratio") or 0.0)
    covered_delta = int(coverage_after.get("covered") or 0) - int(
        coverage_before.get("covered") or 0
    )
    dispatched_ok = int(child_result.get("total_dispatched_ok") or 0)
    dispatched = int(child_result.get("total_dispatched") or 0)
    efficiency = (covered_delta / dispatched_ok) if dispatched_ok > 0 else 0.0
    return {
        "round_index": round_index,
        layer.child_id_field: child_id,
        "stop_reason": child_result.get("stop_reason"),
        "dispatched": dispatched,
        "dispatched_ok": dispatched_ok,
        "coverage_ratio_before": before_ratio,
        "coverage_ratio_after": after_ratio,
        "coverage_delta": after_ratio - before_ratio,
        "covered_delta": covered_delta,
        "efficiency": efficiency,
        layer.child_met_field: bool(child_result.get(layer.child_met_field)),
        "child_digest": child_result.get(layer.child_digest_field),
    }


def roi_summary(
    roi_history: Sequence[Mapping[str, Any]],
    *,
    layer: ConstitutionLayer | None = None,
) -> dict[str, Any]:
    id_field = layer.child_id_field if layer else "child_id"
    if not roi_history:
        return {
            "rounds": 0,
            "total_dispatched_ok": 0,
            "mean_coverage_delta": 0.0,
            "mean_efficiency": 0.0,
            "last_stop_reason": None,
            "by_child": {},
            "by_continuum": {},
        }
    total_ok = sum(int(r.get("dispatched_ok") or 0) for r in roi_history)
    deltas = [float(r.get("coverage_delta") or 0.0) for r in roi_history]
    effs = [float(r.get("efficiency") or 0.0) for r in roi_history]
    by_child: dict[str, dict[str, Any]] = {}
    for r in roi_history:
        iid = str(r.get(id_field) or r.get("child_id") or "")
        bucket = by_child.setdefault(
            iid,
            {"rounds": 0, "dispatched_ok": 0, "covered_delta": 0, "efficiency_sum": 0.0},
        )
        bucket["rounds"] += 1
        bucket["dispatched_ok"] += int(r.get("dispatched_ok") or 0)
        bucket["covered_delta"] += int(r.get("covered_delta") or 0)
        bucket["efficiency_sum"] += float(r.get("efficiency") or 0.0)
    for bucket in by_child.values():
        bucket["mean_efficiency"] = float(bucket["efficiency_sum"]) / max(
            1, int(bucket["rounds"])
        )
    return {
        "rounds": len(roi_history),
        "total_dispatched_ok": total_ok,
        "mean_coverage_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "mean_efficiency": (sum(effs) / len(effs)) if effs else 0.0,
        "last_stop_reason": roi_history[-1].get("stop_reason"),
        "by_child": by_child,
        "by_continuum": by_child,
    }


def select_next_child(
    layer: ConstitutionLayer,
    child_states: Sequence[Mapping[str, Any]],
    roi_history: Sequence[Mapping[str, Any]],
    *,
    round_index: int,
) -> dict[str, Any] | None:
    open_slots = [dict(ist) for ist in child_states if not ist.get(layer.child_met_field)]
    if not open_slots:
        return None
    by_child = roi_summary(roi_history, layer=layer).get("by_child") or {}

    def sort_key(ist: Mapping[str, Any]) -> tuple[Any, ...]:
        iid = str(ist.get(layer.child_id_field) or "")
        hist = by_child.get(iid) or {}
        return (
            -int(ist.get("priority") or 0),
            -float(hist.get("mean_efficiency") or 0.0),
            int(hist.get("rounds") or 0),
            iid,
        )

    ranked = sorted(open_slots, key=sort_key)
    if len(ranked) == 1:
        return ranked[0]
    top_priority = int(ranked[0].get("priority") or 0)
    cohort = [ist for ist in ranked if int(ist.get("priority") or 0) == top_priority]
    if len(cohort) > 1:
        return cohort[round_index % len(cohort)]
    return ranked[0]


def allocate_child_budget(
    layer: ConstitutionLayer,
    *,
    remaining_budget: int | None,
    open_count: int,
    selected: Mapping[str, Any],
    roi_history: Sequence[Mapping[str, Any]],
) -> int | None:
    if remaining_budget is None:
        return None
    remaining = max(0, int(remaining_budget))
    if remaining <= 0:
        return 0
    base = max(1, remaining // max(1, int(open_count)))
    hist = (roi_summary(roi_history, layer=layer).get("by_child") or {}).get(
        str(selected.get(layer.child_id_field) or "")
    ) or {}
    if float(hist.get("mean_efficiency") or 0.0) > 0.0 and int(hist.get("dispatched_ok") or 0) > 0:
        return min(remaining, max(base + 1, remaining // 2))
    return min(remaining, base)


def make_charter_expand(
    layer: ConstitutionLayer,
    growth: Sequence[Mapping[str, Any]],
    *,
    max_slots_per_expand: int = 1,
    applied: Sequence[str] | None = None,
    nested_normalizer: Callable[[Any], list[dict[str, Any]]] | None = None,
) -> Callable[..., dict[str, Any]]:
    pending_growth = normalize_charter(layer, growth, nested_normalizer=nested_normalizer)
    applied_ids: set[str] = set(str(x) for x in (applied or []))

    def _runner(
        *,
        active_charter: Sequence[Mapping[str, Any]],
        child_states: Sequence[Mapping[str, Any]] = (),
        round_index: int = 0,
        roi_history: Sequence[Mapping[str, Any]] = (),
        **_extra: Any,
    ) -> dict[str, Any]:
        # Accept legacy kw names used by quetta-style expanders.
        if not child_states and "ronnacontinuum_states" in _extra:
            child_states = _extra["ronnacontinuum_states"]
        remaining = [
            s
            for s in pending_growth
            if str(s.get(layer.child_id_field) or "") not in applied_ids
            and str(s.get(layer.child_id_field) or "")
            not in {str(x.get(layer.child_id_field) or "") for x in active_charter}
        ]
        if not remaining:
            return {
                "expanded": False,
                "added": [],
                "charter": list(active_charter),
                "detail": "charter_growth_exhausted",
                "round_index": round_index,
            }
        batch = max(1, int(max_slots_per_expand))
        summary = roi_summary(roi_history, layer=layer)
        if float(summary.get("mean_efficiency") or 0.0) > 0.0 and int(
            summary.get("total_dispatched_ok") or 0
        ) > 0:
            batch = min(len(remaining), batch + 1)
        take = remaining[:batch]
        for s in take:
            applied_ids.add(str(s.get(layer.child_id_field) or ""))
        return {
            "expanded": True,
            "added": [str(s.get(layer.child_id_field) or "") for s in take],
            "charter": merge_charter(
                layer, active_charter, take, nested_normalizer=nested_normalizer
            ),
            "detail": "charter_growth_applied",
            "round_index": round_index,
            "children_met": children_all_met(layer, child_states),
        }

    return _runner


def state_payload(
    layer: ConstitutionLayer,
    *,
    constitution_id: str,
    round_count: int,
    total_dispatched: int,
    total_dispatched_ok: int,
    federated_portfolio: Mapping[str, Any] | None,
    roi_history: Sequence[Mapping[str, Any]],
    child_states: Sequence[Mapping[str, Any]],
    child_digests: Sequence[str],
    charter: Sequence[Mapping[str, Any]],
    stop_reason: str | None,
    goal: str,
    max_active: int | None = None,
    admissions: Sequence[Mapping[str, Any]] | None = None,
    charter_expansions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        layer.self_id_field: constitution_id,
        "updated_at": utc_now_iso(),
        "round_count": round_count,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "federated_portfolio": dict(federated_portfolio) if federated_portfolio else None,
        "roi_history": list(roi_history),
        f"{layer.child}_states": [dict(ist) for ist in child_states],
        "child_states": [dict(ist) for ist in child_states],
        f"{layer.child}_digests": list(child_digests),
        "charter": list(charter),
        "stop_reason": stop_reason,
        layer.self_goal_field: goal,
        layer.max_active_field: max_active,
        "admissions": [dict(a) for a in (admissions or [])],
        "charter_expansions": [dict(e) for e in (charter_expansions or [])],
        f"pending_{layer.child}_ids": [
            str(s.get(layer.child_id_field) or "")
            for s in pending_charter_slots(layer, charter, child_states)
        ],
    }


def write_state(layer: ConstitutionLayer, constitution_dir: Path, state: Mapping[str, Any]) -> Path:
    path = Path(constitution_dir) / f"{layer.name}_state.json"
    atomic_write_json(path, dict(state))
    return path


def load_state(layer: ConstitutionLayer, resume_dir: Path) -> dict[str, Any]:
    path = durable_read_path(Path(resume_dir) / f"{layer.name}_state.json")
    if not path.is_file():
        raise ConstitutionRefused(
            f"{layer.name}_state_missing",
            f"no {layer.name}_state.json under {resume_dir}",
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConstitutionRefused(f"{layer.name}_state_unreadable", str(exc)) from exc
    if not isinstance(state, dict):
        raise ConstitutionRefused(f"{layer.name}_state_invalid", "state root must be object")
    return state


def _child_round_record(
    layer: ConstitutionLayer,
    *,
    round_index: int,
    child_id: str,
    child_result: Mapping[str, Any],
    coverage_before: Mapping[str, Any],
    coverage_after: Mapping[str, Any],
    budget_allocated: int | None,
    roi: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "round": round_index,
        layer.child_id_field: child_id,
        "ok": bool(child_result.get("ok")),
        "verdict": child_result.get("verdict"),
        "stop_reason": child_result.get("stop_reason"),
        layer.child_dir_field: child_result.get(layer.child_dir_field),
        layer.child_digest_field: child_result.get(layer.child_digest_field),
        "total_dispatched": int(child_result.get("total_dispatched") or 0),
        "total_dispatched_ok": int(child_result.get("total_dispatched_ok") or 0),
        layer.child_met_field: bool(child_result.get(layer.child_met_field)),
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


def digest_payload(layer: ConstitutionLayer, receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": receipt.get("schema_version"),
        "verdict": receipt.get("verdict"),
        "stop_reason": receipt.get("stop_reason"),
        layer.self_id_field: receipt.get(layer.self_id_field),
        layer.self_goal_field: receipt.get(layer.self_goal_field),
        "max_rounds": receipt.get("max_rounds"),
        layer.max_active_field: receipt.get(layer.max_active_field),
        "dispatch_budget": receipt.get("dispatch_budget"),
        "portfolio_start_digest": receipt.get("portfolio_start_digest"),
        "portfolio_end_digest": receipt.get("portfolio_end_digest"),
        "round_count": receipt.get("round_count"),
        f"{layer.child}_digests": list(receipt.get(f"{layer.child}_digests") or []),
        "total_dispatched": receipt.get("total_dispatched"),
        "total_dispatched_ok": receipt.get("total_dispatched_ok"),
        layer.self_met_field: receipt.get(layer.self_met_field),
        "coverage_end": receipt.get("coverage_end"),
        f"{layer.plural}_met_count": receipt.get(f"{layer.plural}_met_count"),
        f"{layer.plural}_admitted": receipt.get(f"{layer.plural}_admitted"),
        "admission_count": receipt.get("admission_count"),
        "pending_remaining": receipt.get("pending_remaining"),
        "charter_expansion_count": receipt.get("charter_expansion_count"),
        "charter_expanded_ids": list(receipt.get("charter_expanded_ids") or []),
        "roi_summary": receipt.get("roi_summary"),
    }


def verify_receipt(
    layer: ConstitutionLayer,
    constitution_dir: Path,
    *,
    nested_verify: Callable[[Path], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    path = durable_read_path(Path(constitution_dir) / f"{layer.name}.json")
    if not path.is_file():
        return {"ok": False, "verdict": "receipt_missing", "detail": str(path)}
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "verdict": "receipt_unreadable", "detail": str(exc)}
    expected = _sha256_json(digest_payload(layer, receipt))
    recorded = str(receipt.get(layer.self_digest_field) or "")
    mismatched: list[str] = []
    if not recorded or recorded != expected:
        mismatched.append(layer.self_digest_field)
    children = list(receipt.get(layer.plural) or [])
    listed = list(receipt.get(f"{layer.child}_digests") or [])
    if len(listed) != len(children):
        mismatched.append(f"{layer.child}_digests_length")
    else:
        for i, (listed_d, rec) in enumerate(zip(listed, children)):
            if listed_d != rec.get(layer.child_digest_field):
                mismatched.append(f"{layer.child}_digests[{i}]")
    nested_failures: list[str] = []
    if nested_verify is not None:
        for rec in children:
            cdir = rec.get(layer.child_dir_field)
            if not cdir:
                continue
            nested = nested_verify(Path(str(cdir)))
            if not nested.get("ok"):
                nested_failures.append(str(cdir))
    ok = not mismatched and not nested_failures
    return {
        "ok": ok,
        "verdict": f"{layer.name}_sealed" if ok else f"{layer.name}_tampered",
        layer.self_digest_field: recorded,
        "expected_digest": expected,
        "mismatched": mismatched,
        "nested_failures": nested_failures,
        "round_count": len(children),
    }


def run_constitution(
    layer: ConstitutionLayer,
    *,
    charter: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 6,
    dispatch_budget: int | None = None,
    idle_round_limit: int = 1,
    max_active: int | None = None,
    dispatch: bool = True,
    child_runner: Callable[..., dict[str, Any]],
    nested_normalizer: Callable[[Any], list[dict[str, Any]]] | None = None,
    charter_expand: Callable[..., dict[str, Any]] | None = None,
    stop_when: Callable[[Mapping[str, Any]], str | None] | None = None,
    goal: str | None = None,
    constitution_id: str | None = None,
    resume_dir: Path | None = None,
    out_root: Path | None = None,
) -> dict[str, Any]:
    """Run a multi-child durable stewardship constitution and seal the receipt."""
    constitution_goal = goal or layer.all_children_met_goal
    if max_rounds < 1:
        raise ConstitutionRefused(f"{layer.name}_invalid", "max_rounds must be >= 1")
    if max_active is not None and int(max_active) < 1:
        raise ConstitutionRefused(
            f"{layer.name}_invalid", f"{layer.max_active_field} must be >= 1 when set"
        )
    allowed = {layer.all_children_met_goal, "all_children_met", "terminal_coverage", "none"}
    if constitution_goal not in allowed:
        raise ConstitutionRefused(
            f"{layer.name}_invalid", f"unknown {layer.self_goal_field}: {constitution_goal}"
        )

    prior_round_count = 0
    roi_history: list[dict[str, Any]] = []
    child_digests: list[str] = []
    total_dispatched = 0
    total_dispatched_ok = 0
    resumed = False
    resume_id: str | None = None
    child_states: list[dict[str, Any]] = []
    active_charter: list[dict[str, Any]] = []
    federated_portfolio: dict[str, Any] | None = None
    admissions: list[dict[str, Any]] = []
    charter_expansions: list[dict[str, Any]] = []
    resumed_max_active: int | None = None

    if resume_dir is not None:
        state = load_state(layer, resume_dir)
        resumed = True
        resume_id = str(state.get(layer.self_id_field) or "") or None
        prior_round_count = int(state.get("round_count") or 0)
        total_dispatched = int(state.get("total_dispatched") or 0)
        total_dispatched_ok = int(state.get("total_dispatched_ok") or 0)
        roi_history = [
            dict(r) for r in (state.get("roi_history") or []) if isinstance(r, Mapping)
        ]
        child_digests = [
            str(d)
            for d in (state.get(f"{layer.child}_digests") or state.get("child_digests") or [])
        ]
        child_states = [
            dict(ist)
            for ist in (
                state.get(f"{layer.child}_states") or state.get("child_states") or []
            )
            if isinstance(ist, Mapping)
        ]
        if isinstance(state.get("federated_portfolio"), Mapping):
            federated_portfolio = dict(state["federated_portfolio"])
        if isinstance(state.get("charter"), list):
            active_charter = normalize_charter(
                layer,
                [e for e in state["charter"] if isinstance(e, Mapping)],
                nested_normalizer=nested_normalizer,
            )
        if isinstance(state.get("admissions"), list):
            admissions = [dict(a) for a in state["admissions"] if isinstance(a, Mapping)]
        if isinstance(state.get("charter_expansions"), list):
            charter_expansions = [
                dict(e) for e in state["charter_expansions"] if isinstance(e, Mapping)
            ]
        if state.get(layer.max_active_field) is not None and max_active is None:
            resumed_max_active = int(state[layer.max_active_field])
        if charter:
            active_charter = merge_charter(
                layer, active_charter, charter, nested_normalizer=nested_normalizer
            )
    else:
        active_charter = normalize_charter(
            layer, charter, nested_normalizer=nested_normalizer
        )

    active_max = max_active if max_active is not None else resumed_max_active
    if not active_charter and not child_states:
        raise ConstitutionRefused(
            f"{layer.name}_empty", "constitution charter has no admitable child slots"
        )

    lid = (
        constitution_id
        or resume_id
        or f"{layer.name}-{utc_now_iso().replace(':', '').replace('-', '')}"
    )
    stamp = utc_now_iso().replace(":", "").replace("-", "")
    if out_root is not None:
        constitution_dir = Path(out_root)
        if (constitution_dir / f"{layer.name}.json").is_file():
            constitution_dir = constitution_dir / stamp
    else:
        constitution_dir = layer.artifacts_root / stamp
    constitution_dir.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        child_flat = Path("C:/t") / "ce" / secrets.token_hex(2)
    else:
        child_flat = constitution_dir / "c" / secrets.token_hex(2)
    child_flat.mkdir(parents=True, exist_ok=True)

    admissions.extend(
        admit_pending_slots(
            layer,
            constitution_dir=constitution_dir,
            charter=active_charter,
            child_states=child_states,
            max_active=active_max,
            round_index=prior_round_count,
        )
    )
    if not child_states:
        raise ConstitutionRefused(
            f"{layer.name}_empty",
            "no child slots admitted under active capacity policy",
        )

    if federated_portfolio is None:
        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in child_states],
            source=f"{layer.name}_federation",
        )
    portfolio_start_digest = federated_portfolio.get("portfolio_digest")
    rounds: list[dict[str, Any]] = []
    stop_reason = "max_rounds"
    idle_streak = 0
    constitution_met = False
    terminal_reopen_count = 0
    max_terminal_reopens = max(2, (len(child_states) or 1) * 4)
    coverage_end = terminal_coverage(
        child_states=child_states, federated_portfolio=federated_portfolio
    )

    for local_index in range(max_rounds):
        round_index = prior_round_count + local_index
        mid = admit_pending_slots(
            layer,
            constitution_dir=constitution_dir,
            charter=active_charter,
            child_states=child_states,
            max_active=active_max,
            round_index=round_index,
        )
        if mid:
            admissions.extend(mid)

        coverage_before = terminal_coverage(
            child_states=child_states, federated_portfolio=federated_portfolio
        )
        if constitution_satisfied(
            layer,
            child_states=child_states,
            charter=active_charter,
            goal=constitution_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = f"{layer.name}_met"
            constitution_met = True
            coverage_end = coverage_before
            break

        remaining_budget: int | None = None
        if dispatch_budget is not None:
            remaining_budget = max(0, int(dispatch_budget) - total_dispatched)
            if dispatch and remaining_budget <= 0:
                stop_reason = "dispatch_budget"
                coverage_end = coverage_before
                break

        selected = select_next_child(
            layer, child_states, roi_history, round_index=round_index
        )
        if selected is None:
            if constitution_satisfied(
                layer,
                child_states=child_states,
                charter=active_charter,
                goal=constitution_goal,
                federated_portfolio=federated_portfolio,
            ):
                stop_reason = f"{layer.name}_met"
                constitution_met = True
                coverage_end = coverage_before
                break
            if (
                constitution_goal == "terminal_coverage"
                and terminal_reopen_count < max_terminal_reopens
            ):
                reopened = reopen_incomplete_children(
                    layer, child_states, federated_portfolio=federated_portfolio
                )
                if reopened:
                    terminal_reopen_count += 1
                    selected = select_next_child(
                        layer, child_states, roi_history, round_index=round_index
                    )
            if selected is None:
                stop_reason = f"{layer.name}_idle"
                coverage_end = coverage_before
                break

        open_count = open_unmet_count(layer, child_states)
        allocated = allocate_child_budget(
            layer,
            remaining_budget=remaining_budget,
            open_count=open_count,
            selected=selected,
            roi_history=roi_history,
        )
        if dispatch and allocated is not None and allocated <= 0:
            stop_reason = "dispatch_budget"
            coverage_end = coverage_before
            break

        child_id = str(selected[layer.child_id_field])
        resume_child_dir = selected.get(f"last_{layer.child_dir_field}")
        child_resume: Path | None = None
        if (
            resume_child_dir
            and (Path(str(resume_child_dir)) / f"{layer.child}_state.json").is_file()
            and not selected.get(layer.child_met_field)
        ):
            child_resume = Path(str(resume_child_dir))

        safe_id = "".join(c if c.isalnum() else "" for c in child_id)[:4] or "c"
        out_dir = child_flat / f"{round_index:x}{safe_id}{secrets.token_hex(1)}"
        out_dir.mkdir(parents=True, exist_ok=True)

        child_kwargs: dict[str, Any] = {
            "charter": list(selected.get("charter") or []),
            "max_rounds": int(selected.get("max_rounds") or 6),
            "dispatch_budget": allocated,
            "dispatch": bool(dispatch),
            layer.child_goal_field: str(
                selected.get(layer.child_goal_field) or "all_children_met"
            ),
            layer.child_id_field: child_id,
            "out_root": out_dir,
        }
        if selected.get("max_active_children") is not None:
            child_kwargs["max_active_children"] = int(selected["max_active_children"])
        if child_resume is not None:
            child_kwargs["resume_dir"] = child_resume
            # Keep charter/inventory on reopen so terminal_coverage re-runs can
            # still see required keys even when child state is thin.
            if not child_kwargs.get("charter") and selected.get("charter"):
                child_kwargs["charter"] = list(selected.get("charter") or [])
        if selected.get("inventory_keys"):
            child_kwargs["inventory_keys"] = list(selected.get("inventory_keys") or [])

        try:
            child_result = child_runner(**child_kwargs)
        except ConstitutionRefused as exc:
            if local_index == 0 and not resumed:
                raise
            stop_reason = f"child_refused:{exc.verdict}"
            coverage_end = coverage_before
            break
        except Exception as exc:  # noqa: BLE001
            verdict = getattr(exc, "verdict", None)
            if verdict and local_index == 0 and not resumed:
                raise ConstitutionRefused(
                    str(verdict), str(getattr(exc, "detail", exc))
                ) from exc
            if verdict:
                stop_reason = f"child_refused:{verdict}"
                coverage_end = coverage_before
                break
            raise

        dispatched_n = int(child_result.get("total_dispatched") or 0)
        dispatched_ok = int(child_result.get("total_dispatched_ok") or 0)
        prior_d = int(selected.get("total_dispatched") or 0)
        prior_ok = int(selected.get("total_dispatched_ok") or 0)
        delta_dispatched = max(0, dispatched_n - prior_d)
        delta_ok = max(0, dispatched_ok - prior_ok)
        if child_resume is None and prior_d == 0:
            delta_dispatched = dispatched_n
            delta_ok = dispatched_ok
        total_dispatched += delta_dispatched
        total_dispatched_ok += delta_ok

        after_portfolio: dict[str, Any] | None = None
        nested_dir = child_result.get(layer.child_dir_field)
        nested_states: list[dict[str, Any]] = []
        if nested_dir and (Path(str(nested_dir)) / f"{layer.child}.json").is_file():
            receipt = json.loads(
                (Path(str(nested_dir)) / f"{layer.child}.json").read_text(encoding="utf-8")
            )
            if isinstance(receipt.get("federated_portfolio"), Mapping):
                after_portfolio = dict(receipt["federated_portfolio"])
            for ist in list(
                receipt.get("child_states")
                or receipt.get(f"{layer.child}_states")
                or receipt.get("yottacontinuum_states")
                or []
            ):
                if isinstance(ist, Mapping):
                    nested_states.append(dict(ist))
        if after_portfolio is None and isinstance(
            child_result.get("federated_portfolio"), Mapping
        ):
            after_portfolio = dict(child_result["federated_portfolio"])  # type: ignore[index]
        if not nested_states:
            for ist in list(
                child_result.get("child_states")
                or child_result.get("yottacontinuum_states")
                or []
            ):
                if isinstance(ist, Mapping):
                    nested_states.append(dict(ist))

        for i, lst in enumerate(child_states):
            if str(lst.get(layer.child_id_field)) != child_id:
                continue
            updated = dict(lst)
            updated[f"last_{layer.child_dir_field}"] = child_result.get(
                layer.child_dir_field
            )
            updated[f"last_{layer.child_digest_field}"] = child_result.get(
                layer.child_digest_field
            )
            updated[layer.child_met_field] = bool(child_result.get(layer.child_met_field))
            updated["total_dispatched"] = dispatched_n
            updated["total_dispatched_ok"] = dispatched_ok
            if after_portfolio is not None:
                updated["portfolio"] = after_portfolio
            if nested_states:
                updated["child_states"] = nested_states
                updated["yottacontinuum_states"] = nested_states
            inv = list(updated.get("inventory_keys") or [])
            if child_result.get("inventory_keys"):
                inv = list(child_result["inventory_keys"])
            elif after_portfolio is not None:
                inv = [
                    _entry_key(e)
                    for e in _portfolio_entries(after_portfolio)
                    if _entry_key(e)[0] and _entry_key(e)[2]
                ]
            if inv:
                updated["inventory_keys"] = inv
            child_states[i] = updated
            selected = updated
            break

        federated_portfolio = federate_portfolios(
            [ist.get("portfolio") for ist in child_states],
            source=f"{layer.name}_federation",
        )
        coverage_after = terminal_coverage(
            child_states=child_states, federated_portfolio=federated_portfolio
        )
        roi = score_child_roi(
            layer,
            round_index=round_index,
            child_id=child_id,
            child_result=child_result,
            coverage_before=coverage_before,
            coverage_after=coverage_after,
        )
        roi_history.append(roi)
        idigest = str(child_result.get(layer.child_digest_field) or "")
        if idigest:
            child_digests.append(idigest)
        rounds.append(
            _child_round_record(
                layer,
                round_index=round_index,
                child_id=child_id,
                child_result=child_result,
                coverage_before=coverage_before,
                coverage_after=coverage_after,
                budget_allocated=allocated,
                roi=roi,
            )
        )

        post = admit_pending_slots(
            layer,
            constitution_dir=constitution_dir,
            charter=active_charter,
            child_states=child_states,
            max_active=active_max,
            round_index=round_index + 1,
        )
        if post:
            admissions.extend(post)

        write_state(
            layer,
            constitution_dir,
            state_payload(
                layer,
                constitution_id=lid,
                round_count=round_index + 1,
                total_dispatched=total_dispatched,
                total_dispatched_ok=total_dispatched_ok,
                federated_portfolio=federated_portfolio,
                roi_history=roi_history,
                child_states=child_states,
                child_digests=child_digests,
                charter=active_charter,
                stop_reason=None,
                goal=constitution_goal,
                max_active=active_max,
                admissions=admissions,
                charter_expansions=charter_expansions,
            ),
        )
        coverage_end = coverage_after

        if (
            delta_ok == 0
            and delta_dispatched == 0
            and not child_result.get(layer.child_met_field)
        ):
            idle_streak += 1
        else:
            idle_streak = 0

        if stop_when is not None:
            reason = stop_when(
                {
                    "round_index": round_index,
                    "round_count": len(rounds),
                    "total_dispatched": total_dispatched,
                    "total_dispatched_ok": total_dispatched_ok,
                    "coverage": coverage_after,
                    "roi_history": roi_history,
                    "child_states": child_states,
                    f"last_{layer.child_id_field}": child_id,
                    "federated_portfolio": federated_portfolio,
                    f"{layer.name}_dir": str(constitution_dir),
                    "pending_ids": [
                        str(s.get(layer.child_id_field) or "")
                        for s in pending_charter_slots(
                            layer, active_charter, child_states
                        )
                    ],
                    "admissions": admissions,
                    "charter_expansions": charter_expansions,
                }
            )
            if reason:
                stop_reason = str(reason)
                break

        if (
            charter_expand is not None
            and not pending_charter_slots(layer, active_charter, child_states)
            and children_all_met(layer, child_states)
        ):
            try:
                growth = charter_expand(
                    active_charter=active_charter,
                    child_states=child_states,
                    round_index=round_index,
                    roi_history=roi_history,
                )
            except TypeError:
                growth = charter_expand(
                    active_charter=active_charter,
                    ronnacontinuum_states=child_states,
                    round_index=round_index,
                    roi_history=roi_history,
                )
            if growth.get("expanded") and growth.get("charter"):
                active_charter = normalize_charter(
                    layer,
                    [e for e in (growth.get("charter") or []) if isinstance(e, Mapping)],
                    nested_normalizer=nested_normalizer,
                )
                charter_expansions.append(
                    {
                        "round_index": round_index,
                        "added": list(growth.get("added") or []),
                        "detail": growth.get("detail"),
                    }
                )
                post_growth = admit_pending_slots(
                    layer,
                    constitution_dir=constitution_dir,
                    charter=active_charter,
                    child_states=child_states,
                    max_active=active_max,
                    round_index=round_index + 1,
                )
                if post_growth:
                    admissions.extend(post_growth)
                continue

        if constitution_satisfied(
            layer,
            child_states=child_states,
            charter=active_charter,
            goal=constitution_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = f"{layer.name}_met"
            constitution_met = True
            break

        if dispatch_budget is not None and total_dispatched >= int(dispatch_budget):
            stop_reason = "dispatch_budget"
            break

        if not dispatch:
            stop_reason = "rank_only"
            break

        if idle_streak >= idle_round_limit and not constitution_satisfied(
            layer,
            child_states=child_states,
            charter=active_charter,
            goal=constitution_goal,
            federated_portfolio=federated_portfolio,
        ):
            stop_reason = f"{layer.name}_idle"
            break
    else:
        stop_reason = "max_rounds"

    federated_portfolio = federate_portfolios(
        [ist.get("portfolio") for ist in child_states],
        source=f"{layer.name}_federation",
    )
    coverage_end = terminal_coverage(
        child_states=child_states, federated_portfolio=federated_portfolio
    )
    if constitution_satisfied(
        layer,
        child_states=child_states,
        charter=active_charter,
        goal=constitution_goal,
        federated_portfolio=federated_portfolio,
    ):
        constitution_met = True

    portfolio_end_digest = (
        federated_portfolio.get("portfolio_digest") if federated_portfolio else None
    )
    summary_roi = roi_summary(roi_history, layer=layer)
    met_count = sum(1 for ist in child_states if ist.get(layer.child_met_field))
    pending_remaining = [
        str(s.get(layer.child_id_field) or "")
        for s in pending_charter_slots(layer, active_charter, child_states)
    ]

    if constitution_met and stop_reason in {f"{layer.name}_met", "max_rounds"}:
        verdict = f"{layer.name}_met"
        ok = True
        stop_reason = f"{layer.name}_met"
    elif stop_reason == "rank_only":
        verdict = f"{layer.name}_ranked"
        ok = True
    elif stop_reason == f"{layer.name}_idle":
        verdict = f"{layer.name}_idle"
        ok = True
    elif stop_reason == "dispatch_budget":
        verdict = f"{layer.name}_budgeted"
        ok = True
    elif stop_reason.startswith("child_refused"):
        verdict = "child_refused_mid"
        ok = False
    else:
        verdict = f"{layer.name}_completed"
        ok = True

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now_iso(),
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        layer.self_id_field: lid,
        "resumed": resumed,
        "prior_round_count": prior_round_count,
        "max_rounds": max_rounds,
        layer.max_active_field: active_max,
        "dispatch_budget": dispatch_budget,
        "dispatch_enabled": bool(dispatch),
        layer.self_goal_field: constitution_goal,
        layer.self_met_field: constitution_met,
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
        "round_count": len(rounds),
        layer.plural: rounds,
        f"{layer.child}_digests": [
            str(i.get(layer.child_digest_field) or "") for i in rounds
        ],
        f"{layer.child}_states": child_states,
        "child_states": child_states,
        f"{layer.plural}_admitted": len(child_states),
        f"{layer.plural}_met_count": met_count,
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
        "roi_summary": summary_roi,
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "layer": {"name": layer.name, "child": layer.child},
    }
    receipt[layer.self_digest_field] = _sha256_json(digest_payload(layer, receipt))
    atomic_write_json(constitution_dir / f"{layer.name}.json", receipt)
    atomic_write_json(
        constitution_dir / "summary.json",
        {
            "verdict": receipt["verdict"],
            "ok": receipt["ok"],
            "stop_reason": receipt["stop_reason"],
            layer.self_id_field: receipt[layer.self_id_field],
            "round_count": receipt["round_count"],
            "total_dispatched": receipt["total_dispatched"],
            "total_dispatched_ok": receipt["total_dispatched_ok"],
            layer.self_met_field: receipt[layer.self_met_field],
            f"{layer.plural}_admitted": receipt[f"{layer.plural}_admitted"],
            f"{layer.plural}_met_count": receipt[f"{layer.plural}_met_count"],
            "admission_count": receipt["admission_count"],
            "pending_remaining": receipt["pending_remaining"],
            "charter_expansion_count": receipt["charter_expansion_count"],
            layer.max_active_field: receipt[layer.max_active_field],
            "coverage_ratio": (receipt.get("coverage_end") or {}).get("coverage_ratio"),
            layer.self_digest_field: receipt[layer.self_digest_field],
            "resumed": resumed,
        },
    )
    write_state(
        layer,
        constitution_dir,
        state_payload(
            layer,
            constitution_id=lid,
            round_count=prior_round_count + len(rounds),
            total_dispatched=total_dispatched,
            total_dispatched_ok=total_dispatched_ok,
            federated_portfolio=federated_portfolio,
            roi_history=roi_history,
            child_states=child_states,
            child_digests=receipt[f"{layer.child}_digests"],
            charter=active_charter,
            stop_reason=stop_reason,
            goal=constitution_goal,
            max_active=active_max,
            admissions=admissions,
            charter_expansions=charter_expansions,
        ),
    )
    return {
        "ok": ok,
        "verdict": verdict,
        "stop_reason": stop_reason,
        f"{layer.name}_dir": str(constitution_dir),
        layer.self_digest_field: receipt[layer.self_digest_field],
        layer.self_id_field: lid,
        "round_count": len(rounds),
        f"{layer.child}_digests": list(receipt[f"{layer.child}_digests"]),
        "total_dispatched": total_dispatched,
        "total_dispatched_ok": total_dispatched_ok,
        layer.self_met_field: constitution_met,
        f"{layer.plural}_admitted": len(child_states),
        f"{layer.plural}_met_count": met_count,
        "admission_count": len(admissions),
        "pending_remaining": pending_remaining,
        layer.max_active_field: active_max,
        "admissions": admissions,
        "charter_expansions": charter_expansions,
        "charter_expansion_count": len(charter_expansions),
        "charter_expanded_ids": list(receipt["charter_expanded_ids"]),
        "coverage_end": receipt["coverage_end"],
        "portfolio_start_digest": portfolio_start_digest,
        "portfolio_end_digest": portfolio_end_digest,
        "child_states": child_states,
        "roi_summary": summary_roi,
        "resumed": resumed,
        layer.plural: rounds,
        "used_skill_route_discovery": receipt["used_skill_route_discovery"],
        "layer": {"name": layer.name, "child": layer.child},
    }


def _proof_scratch() -> Path:
    if os.name == "nt":
        root = Path("C:/t")
        try:
            root.mkdir(parents=True, exist_ok=True)
            return Path(tempfile.mkdtemp(prefix="ce", dir=str(root)))
        except OSError:
            pass
    return Path(tempfile.mkdtemp(prefix="ce"))


def _slot(
    layer: ConstitutionLayer,
    child_id: str,
    *,
    priority: int = 0,
    keys: Sequence[tuple[str, str, str]] = (),
    max_rounds: int = 4,
) -> dict[str, Any]:
    return {
        layer.child_id_field: child_id,
        "priority": priority,
        "max_rounds": max_rounds,
        "inventory_keys": [tuple(k) for k in keys],
        "charter": [{"inventory_keys": [tuple(k) for k in keys]}],
    }


def _fast_child_runner(layer: ConstitutionLayer) -> Callable[..., dict[str, Any]]:
    def runner(**kwargs: Any) -> dict[str, Any]:
        child_id = str(kwargs.get(layer.child_id_field) or kwargs.get("child_id") or "c")
        charter = list(kwargs.get("charter") or [])
        inv: list[tuple[str, str, str]] = []
        for node in charter:
            if isinstance(node, Mapping):
                inv.extend(collect_inventory_keys(node))
        dispatch = bool(kwargs.get("dispatch", True))
        budget = kwargs.get("dispatch_budget")
        dispatched = 0
        dispatched_ok = 0
        if dispatch and (budget is None or int(budget) > 0):
            dispatched = max(1, len(inv) or 1)
            dispatched_ok = dispatched
        entries = []
        if dispatched_ok > 0:
            for n, v, d in inv:
                entries.append(
                    {
                        "name": n,
                        "version": v,
                        "defect_id": d,
                        "outcome": "impact_merged",
                        "impact_digest": _sha256_json({"n": n, "d": d}),
                    }
                )
        portfolio = make_portfolio(entries, source=f"fast_{layer.child}")
        out = Path(str(kwargs.get("out_root") or _proof_scratch() / child_id))
        out.mkdir(parents=True, exist_ok=True)
        met = dispatched_ok > 0
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "verdict": f"{layer.child}_met" if met else f"{layer.child}_partial",
            "stop_reason": f"{layer.child}_met" if met else "dispatch_budget",
            layer.child_id_field: child_id,
            layer.child_met_field: met,
            "total_dispatched": dispatched,
            "total_dispatched_ok": dispatched_ok,
            "federated_portfolio": portfolio,
            "inventory_keys": inv,
            "child_states": [{"inventory_keys": inv, "portfolio": portfolio}],
        }
        receipt[layer.child_digest_field] = _sha256_json(
            {
                "id": child_id,
                "met": met,
                "portfolio": portfolio.get("portfolio_digest"),
                "dispatched": dispatched,
            }
        )
        atomic_write_json(out / f"{layer.child}.json", receipt)
        atomic_write_json(
            out / f"{layer.child}_state.json",
            {
                layer.child_id_field: child_id,
                "round_count": 1,
                "total_dispatched": dispatched,
                "total_dispatched_ok": dispatched_ok,
                "federated_portfolio": portfolio,
                "stop_reason": receipt["stop_reason"],
                "charter": charter,
            },
        )
        return {
            "ok": True,
            "verdict": receipt["verdict"],
            "stop_reason": receipt["stop_reason"],
            layer.child_dir_field: str(out),
            layer.child_digest_field: receipt[layer.child_digest_field],
            layer.child_id_field: child_id,
            layer.child_met_field: met,
            "total_dispatched": dispatched,
            "total_dispatched_ok": dispatched_ok,
            "federated_portfolio": portfolio,
            "inventory_keys": inv,
            "child_states": receipt["child_states"],
            "used_skill_route_discovery": False,
        }

    return runner


def _partial_then_complete_runner(layer: ConstitutionLayer) -> Callable[..., dict[str, Any]]:
    visits: dict[str, int] = {}

    def runner(**kwargs: Any) -> dict[str, Any]:
        child_id = str(kwargs.get(layer.child_id_field) or "c")
        charter = list(kwargs.get("charter") or [])
        if not charter and kwargs.get("resume_dir"):
            sp = Path(str(kwargs["resume_dir"])) / f"{layer.child}_state.json"
            if sp.is_file():
                try:
                    st = json.loads(sp.read_text(encoding="utf-8"))
                    charter = list(st.get("charter") or [])
                except (OSError, json.JSONDecodeError):
                    charter = []
        inv: list[tuple[str, str, str]] = []
        for node in charter:
            if isinstance(node, Mapping):
                inv.extend(collect_inventory_keys(node))
        if not inv and kwargs.get("inventory_keys"):
            for raw in kwargs["inventory_keys"]:
                if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                    inv.append((str(raw[0]), str(raw[1]), str(raw[2])))
        n = visits.get(child_id, 0)
        visits[child_id] = n + 1
        out = Path(str(kwargs.get("out_root") or _proof_scratch() / child_id))
        out.mkdir(parents=True, exist_ok=True)
        # First fresh visit retires early without covering inventory. Any later
        # visit (or resume/reopen) covers terminal inventory keys.
        if n == 0 and not kwargs.get("resume_dir"):
            portfolio = make_portfolio([], source="partial")
            met = True
            dispatched = 1
            dispatched_ok = 0
        else:
            entries = [
                {
                    "name": a,
                    "version": b,
                    "defect_id": c,
                    "outcome": "impact_released",
                    "impact_digest": _sha256_json({"a": a, "c": c}),
                }
                for a, b, c in inv
            ]
            portfolio = make_portfolio(entries, source="complete")
            met = True
            dispatched = max(1, len(inv))
            dispatched_ok = dispatched
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "verdict": f"{layer.child}_met",
            "stop_reason": f"{layer.child}_met",
            layer.child_id_field: child_id,
            layer.child_met_field: met,
            "total_dispatched": dispatched,
            "total_dispatched_ok": dispatched_ok,
            "federated_portfolio": portfolio,
            "inventory_keys": inv,
        }
        receipt[layer.child_digest_field] = _sha256_json(
            {"id": child_id, "n": n, "p": portfolio.get("portfolio_digest")}
        )
        atomic_write_json(out / f"{layer.child}.json", receipt)
        atomic_write_json(
            out / f"{layer.child}_state.json",
            {layer.child_id_field: child_id, "charter": charter, "n": n},
        )
        return {
            "ok": True,
            "verdict": receipt["verdict"],
            "stop_reason": receipt["stop_reason"],
            layer.child_dir_field: str(out),
            layer.child_digest_field: receipt[layer.child_digest_field],
            layer.child_id_field: child_id,
            layer.child_met_field: met,
            "total_dispatched": dispatched,
            "total_dispatched_ok": dispatched_ok,
            "federated_portfolio": portfolio,
            "inventory_keys": inv,
            "used_skill_route_discovery": False,
        }

    return runner


def _shared_mock_child(
    *,
    child: str,
    child_id: str,
    charter: Sequence[Mapping[str, Any]],
    out_root: Path,
    dispatch: bool,
    dispatch_budget: Any,
) -> dict[str, Any]:
    inv: list[tuple[str, str, str]] = []
    for node in charter:
        if isinstance(node, Mapping):
            inv.extend(collect_inventory_keys(node))
    dispatched = 0
    dispatched_ok = 0
    if dispatch and (dispatch_budget is None or int(dispatch_budget) > 0):
        dispatched = max(1, len(inv) or 1)
        dispatched_ok = dispatched
    entries = []
    if dispatched_ok > 0:
        for n, v, d in inv:
            entries.append(
                {
                    "name": n,
                    "version": v,
                    "defect_id": d,
                    "outcome": "impact_merged",
                    "impact_digest": _sha256_json({"n": n, "d": d}),
                }
            )
    portfolio = make_portfolio(entries, source="shared_mock")
    out = Path(out_root)
    out.mkdir(parents=True, exist_ok=True)
    met = dispatched_ok > 0
    y_states = [
        {
            "yottacontinuum_id": "g",
            "yottacontinuum_met": True,
            "inventory_keys": list(inv),
            "portfolio": portfolio,
        }
    ]
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "verdict": f"{child}_met" if met else f"{child}_partial",
        "stop_reason": f"{child}_met" if met else "dispatch_budget",
        f"{child}_id": child_id,
        f"{child}_met": met,
        "total_dispatched": dispatched,
        "total_dispatched_ok": dispatched_ok,
        "federated_portfolio": portfolio,
        "yottacontinuum_states": y_states,
        "yottacontinuums_admitted": 1,
        "yottacontinuums_met_count": 1 if met else 0,
        "inventory_keys": inv,
    }
    digest = _sha256_json(
        {"id": child_id, "met": met, "p": portfolio.get("portfolio_digest")}
    )
    receipt[f"{child}_digest"] = digest
    atomic_write_json(out / f"{child}.json", receipt)
    atomic_write_json(
        out / f"{child}_state.json",
        {
            f"{child}_id": child_id,
            "federated_portfolio": portfolio,
            "yottacontinuum_states": y_states,
            "charter": list(charter),
            "stop_reason": receipt["stop_reason"],
        },
    )
    return {
        "ok": True,
        "verdict": receipt["verdict"],
        "stop_reason": receipt["stop_reason"],
        f"{child}_dir": str(out),
        f"{child}_digest": digest,
        f"{child}_id": child_id,
        f"{child}_met": met,
        "total_dispatched": dispatched,
        "total_dispatched_ok": dispatched_ok,
        "federated_portfolio": portfolio,
        "yottacontinuum_states": y_states,
        "yottacontinuums_admitted": 1,
        "yottacontinuums_met_count": 1 if met else 0,
        "inventory_keys": inv,
        "used_skill_route_discovery": False,
    }


def _legacy_quetta_parity(scratch: Path) -> dict[str, Any]:
    from blackhole_agent import upstream_quettacontinuum as qt

    layer = ConstitutionLayer(name="quettacontinuum", child="ronnacontinuum")

    def engine_runner(**kwargs: Any) -> dict[str, Any]:
        return _shared_mock_child(
            child="ronnacontinuum",
            child_id=str(kwargs.get("ronnacontinuum_id") or "r"),
            charter=list(kwargs.get("charter") or []),
            out_root=Path(str(kwargs.get("out_root"))),
            dispatch=bool(kwargs.get("dispatch", True)),
            dispatch_budget=kwargs.get("dispatch_budget"),
        )

    def legacy_runner(**kwargs: Any) -> dict[str, Any]:
        return _shared_mock_child(
            child="ronnacontinuum",
            child_id=str(kwargs.get("ronnacontinuum_id") or "r"),
            charter=list(kwargs.get("charter") or []),
            out_root=Path(str(kwargs.get("out_root"))),
            dispatch=bool(kwargs.get("dispatch", True)),
            dispatch_budget=kwargs.get("dispatch_budget"),
        )

    eng_charter = [
        _slot(layer, "a", priority=2, keys=[("a", "1.0.0", "a-1")]),
        _slot(layer, "b", priority=1, keys=[("b", "1.0.0", "b-1")]),
    ]
    leg_charter = [
        qt._ronnacontinuum_slot(
            "a",
            priority=2,
            institutions=[
                qt._inst_slot(
                    "ia",
                    programs=[qt._program_slot("pa", initial=[("a", "1.0.0", "a-1")])],
                )
            ],
        ),
        qt._ronnacontinuum_slot(
            "b",
            priority=1,
            institutions=[
                qt._inst_slot(
                    "ib",
                    programs=[qt._program_slot("pb", initial=[("b", "1.0.0", "b-1")])],
                )
            ],
        ),
    ]
    eng = run_constitution(
        layer,
        charter=eng_charter,
        max_rounds=6,
        dispatch=True,
        child_runner=engine_runner,
        goal=layer.all_children_met_goal,
        out_root=scratch / "eng",
    )
    leg = qt.run_quettacontinuum(
        charter=leg_charter,
        max_rounds=6,
        dispatch=True,
        ronnacontinuum_runner=legacy_runner,
        quettacontinuum_goal="all_ronnacontinuums_met",
        out_root=scratch / "leg",
    )
    checks = {
        "both_ok": bool(eng.get("ok") and leg.get("ok")),
        "both_met": bool(eng.get("quettacontinuum_met") and leg.get("quettacontinuum_met")),
        "met_count_equal": eng.get("ronnacontinuums_met_count")
        == leg.get("ronnacontinuums_met_count")
        == 2,
        "stop_reason_equal": eng.get("stop_reason")
        == leg.get("stop_reason")
        == "quettacontinuum_met",
        "first_child_priority": (
            (eng.get("ronnacontinuums") or [{}])[0].get("ronnacontinuum_id") == "a"
            and (leg.get("ronnacontinuums") or [{}])[0].get("ronnacontinuum_id") == "a"
        ),
        "no_skill_route": (not eng.get("used_skill_route_discovery"))
        and (not leg.get("used_skill_route_discovery")),
    }
    eng_d = run_constitution(
        layer,
        charter=eng_charter,
        max_rounds=6,
        max_active=1,
        dispatch=True,
        child_runner=engine_runner,
        goal=layer.all_children_met_goal,
        out_root=scratch / "eng_d",
    )
    leg_d = qt.run_quettacontinuum(
        charter=leg_charter,
        max_rounds=6,
        max_active_ronnacontinuums=1,
        dispatch=True,
        ronnacontinuum_runner=legacy_runner,
        quettacontinuum_goal="all_ronnacontinuums_met",
        out_root=scratch / "leg_d",
    )
    checks["deferred_both_met"] = bool(
        eng_d.get("quettacontinuum_met") and leg_d.get("quettacontinuum_met")
    )
    checks["deferred_admitted_equal"] = eng_d.get("ronnacontinuums_admitted") == leg_d.get(
        "ronnacontinuums_admitted"
    )
    ok = all(checks.values())
    return {
        "ok": ok,
        "checks": checks,
        "engine": {
            "stop_reason": eng.get("stop_reason"),
            "met_count": eng.get("ronnacontinuums_met_count"),
        },
        "legacy": {
            "stop_reason": leg.get("stop_reason"),
            "met_count": leg.get("ronnacontinuums_met_count"),
        },
    }


def builtin_constitution_engine_proof() -> dict[str, Any]:
    """Hermetic proof that multi-child constitutions are data, not copy-paste modules."""
    scratch = _proof_scratch()
    flags: dict[str, Any] = {}
    try:
        layer = ConstitutionLayer(name="metaconstitution", child="province")
        runner = _fast_child_runner(layer)

        multi = run_constitution(
            layer,
            charter=[
                _slot(layer, "a", priority=2, keys=[("x", "1.0.0", "x-1")]),
                _slot(layer, "b", priority=1, keys=[("y", "1.0.0", "y-1")]),
                _slot(layer, "c", priority=0, keys=[("z", "1.0.0", "z-1")]),
            ],
            max_rounds=6,
            dispatch=True,
            child_runner=runner,
            goal=layer.all_children_met_goal,
            constitution_id="meta-1",
            out_root=scratch / "multi",
        )
        flags["multi_child_met"] = bool(
            multi.get("ok")
            and multi.get(layer.self_met_field)
            and multi.get(f"{layer.plural}_met_count") == 3
            and multi.get("total_dispatched_ok", 0) >= 3
        )
        flags["priority_scheduling"] = (
            (multi.get(layer.plural) or [{}])[0].get(layer.child_id_field) == "a"
        )
        flags["federation_coverage"] = (
            float((multi.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
        )

        sealed = verify_receipt(layer, Path(multi[f"{layer.name}_dir"]))
        flags["seal_verified"] = bool(sealed.get("ok"))

        receipt_path = Path(multi[f"{layer.name}_dir"]) / f"{layer.name}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["total_dispatched_ok"] = int(receipt.get("total_dispatched_ok") or 0) + 99
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        tampered = verify_receipt(layer, Path(multi[f"{layer.name}_dir"]))
        flags["tamper_detected"] = (not tampered.get("ok")) and tampered.get(
            "verdict"
        ) == f"{layer.name}_tampered"

        deferred = run_constitution(
            layer,
            charter=[
                _slot(layer, "d1", priority=1, keys=[("d1", "1.0.0", "d1-1")]),
                _slot(layer, "d2", priority=0, keys=[("d2", "1.0.0", "d2-1")]),
            ],
            max_rounds=6,
            max_active=1,
            dispatch=True,
            child_runner=_fast_child_runner(layer),
            goal=layer.all_children_met_goal,
            out_root=scratch / "defer",
        )
        flags["deferred_admission"] = bool(
            deferred.get("ok")
            and deferred.get(layer.self_met_field)
            and deferred.get("admission_count", 0) >= 2
            and deferred.get(f"{layer.plural}_admitted") == 2
        )

        expand_layer = ConstitutionLayer(name="expandcon", child="cell")
        growth = [_slot(expand_layer, "g2", keys=[("g2", "1.0.0", "g2-1")])]
        expander = make_charter_expand(expand_layer, growth, max_slots_per_expand=1)
        expanded = run_constitution(
            expand_layer,
            charter=[_slot(expand_layer, "g1", keys=[("g1", "1.0.0", "g1-1")])],
            max_rounds=8,
            dispatch=True,
            child_runner=_fast_child_runner(expand_layer),
            charter_expand=expander,
            goal=expand_layer.all_children_met_goal,
            out_root=scratch / "expand",
        )
        flags["charter_expand"] = bool(
            expanded.get("ok")
            and expanded.get(expand_layer.self_met_field)
            and expanded.get("charter_expansion_count", 0) >= 1
            and "g2" in (expanded.get("charter_expanded_ids") or [])
            and expanded.get(f"{expand_layer.plural}_met_count") == 2
        )

        tc_layer = ConstitutionLayer(name="termcon", child="sector")
        term = run_constitution(
            tc_layer,
            charter=[_slot(tc_layer, "s1", keys=[("t", "1.0.0", "t-1")])],
            max_rounds=6,
            dispatch=True,
            child_runner=_partial_then_complete_runner(tc_layer),
            goal="terminal_coverage",
            out_root=scratch / "term",
        )
        flags["terminal_coverage_goal"] = bool(
            term.get("ok")
            and term.get(tc_layer.self_met_field)
            and float((term.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
            and term.get("round_count", 0) >= 2
        )

        budget = run_constitution(
            layer,
            charter=[
                _slot(layer, "b1", keys=[("b1", "1.0.0", "b1-1")]),
                _slot(layer, "b2", keys=[("b2", "1.0.0", "b2-1")]),
            ],
            max_rounds=6,
            dispatch_budget=1,
            dispatch=True,
            child_runner=_fast_child_runner(layer),
            goal="none",
            out_root=scratch / "budget",
        )
        flags["budget_stops"] = bool(
            budget.get("ok")
            and budget.get("stop_reason") == "dispatch_budget"
            and budget.get("total_dispatched", 0) >= 1
            and not budget.get(layer.self_met_field)
        )

        ranked = run_constitution(
            layer,
            charter=[
                _slot(layer, "r1", priority=3, keys=[("r1", "1.0.0", "r1-1")]),
                _slot(layer, "r2", priority=1, keys=[("r2", "1.0.0", "r2-1")]),
            ],
            max_rounds=2,
            dispatch=False,
            child_runner=_fast_child_runner(layer),
            goal="none",
            out_root=scratch / "rank",
        )
        flags["rank_only"] = bool(
            ranked.get("ok")
            and ranked.get("verdict") == f"{layer.name}_ranked"
            and ranked.get("total_dispatched") == 0
        )

        empty_refused = False
        try:
            run_constitution(
                layer,
                charter=[],
                dispatch=False,
                child_runner=_fast_child_runner(layer),
                goal="none",
                out_root=scratch / "empty",
            )
        except ConstitutionRefused as exc:
            empty_refused = exc.verdict in {
                f"{layer.name}_empty",
                f"{layer.name}_invalid",
            }
        flags["empty_refused"] = empty_refused

        custom = run_constitution(
            layer,
            charter=[
                _slot(layer, "c1", keys=[("c1", "1.0.0", "c1-1")]),
                _slot(layer, "c2", keys=[("c2", "1.0.0", "c2-1")]),
            ],
            max_rounds=6,
            dispatch=True,
            child_runner=_fast_child_runner(layer),
            goal="none",
            stop_when=lambda ctx: (
                "custom_halt" if ctx["total_dispatched_ok"] >= 1 else None
            ),
            out_root=scratch / "custom",
        )
        flags["custom_stop"] = bool(
            custom.get("ok") and custom.get("stop_reason") == "custom_halt"
        )

        partial = run_constitution(
            layer,
            charter=[
                _slot(layer, "p1", priority=2, keys=[("p1", "1.0.0", "p1-1")]),
                _slot(layer, "p2", priority=1, keys=[("p2", "1.0.0", "p2-1")]),
            ],
            max_rounds=1,
            dispatch_budget=1,
            dispatch=True,
            child_runner=_fast_child_runner(layer),
            goal="none",
            constitution_id="resume-me",
            out_root=scratch / "partial",
        )
        state_path = Path(partial[f"{layer.name}_dir"]) / f"{layer.name}_state.json"
        resumed = run_constitution(
            layer,
            resume_dir=Path(partial[f"{layer.name}_dir"]),
            max_rounds=4,
            dispatch_budget=4,
            dispatch=True,
            child_runner=_fast_child_runner(layer),
            goal="none",
            out_root=scratch / "resumed",
        )
        flags["durable_resume"] = bool(
            partial.get("ok")
            and state_path.is_file()
            and resumed.get("ok")
            and resumed.get("resumed") is True
            and resumed.get(layer.self_id_field) == "resume-me"
            and resumed.get("total_dispatched", 0) > partial.get("total_dispatched", 0)
        )

        flags["roi_scored"] = bool(
            isinstance(multi.get("roi_summary"), Mapping)
            and int((multi["roi_summary"] or {}).get("rounds") or 0) >= 2
            and int((multi["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 3
        )

        layer2 = ConstitutionLayer(name="altcon", child="ward")
        alt = run_constitution(
            layer2,
            charter=[
                _slot(layer2, "w1", keys=[("w", "1.0.0", "w-1")]),
                _slot(layer2, "w2", keys=[("w2", "2.0.0", "w2-1")]),
            ],
            max_rounds=4,
            dispatch=True,
            child_runner=_fast_child_runner(layer2),
            goal=layer2.all_children_met_goal,
            out_root=scratch / "alt",
        )
        flags["second_layer_data_only"] = bool(
            alt.get("ok")
            and alt.get(layer2.self_met_field)
            and alt.get(f"{layer2.plural}_met_count") == 2
            and (alt.get("layer") or {}).get("name") == "altcon"
        )

        parity = _legacy_quetta_parity(scratch / "parity")
        flags["legacy_quetta_parity"] = bool(parity.get("ok"))
        flags["legacy_quetta_parity_detail"] = parity
        flags["used_skill_route_discovery"] = legacy_pipeline_was_used()

        required = (
            "multi_child_met",
            "priority_scheduling",
            "federation_coverage",
            "seal_verified",
            "tamper_detected",
            "deferred_admission",
            "charter_expand",
            "terminal_coverage_goal",
            "budget_stops",
            "rank_only",
            "empty_refused",
            "custom_stop",
            "durable_resume",
            "roi_scored",
            "second_layer_data_only",
            "legacy_quetta_parity",
        )
        ok = all(bool(flags[k]) for k in required) and not flags[
            "used_skill_route_discovery"
        ]
        return {
            "ok": ok,
            "action": "constitution_engine_proof",
            "flags": flags,
            "used_skill_route_discovery": flags["used_skill_route_discovery"],
            **{k: flags[k] for k in required},
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constitution engine proof / CLI")
    parser.add_argument("--proof", action="store_true", help="Run hermetic proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.proof:
        result = builtin_constitution_engine_proof()
        print(json.dumps({"ok": result.get("ok"), "action": result.get("action")}, indent=2))
        if not result.get("ok"):
            print(json.dumps(result.get("flags"), indent=2, default=str))
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
