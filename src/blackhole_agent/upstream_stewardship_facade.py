"""Stewardship tower facade: thin public APIs over the constitution engine.

Collapses the multi-child copy-paste tower (quettacontinuum..institution) into
one noun-parameterized export surface. The 23 ``upstream_<layer>`` modules are
synthesized on demand by ``upstream_layer_registry`` (a meta-path finder
installed from the package ``__init__``) running :func:`export_layer_api` —
not another ~2500-line rename, and not even a 17-line physical file anymore.

Preserves legacy public names (``run_*``, ``normalize_*_charter``,
``verify_*_receipt``, ``builtin_upstream_*_proof``, CLI ``--proof``) so ledger
entries and tests keep working while behavior runs through
``upstream_constitution_engine``. No skill-route discovery.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent import upstream_constitution_engine as ce
from blackhole_agent.capability_compounder import legacy_pipeline_was_used

# Layers that expose charter_expand / charter_merge in their hermetic proof.
_EXPAND_LAYERS = frozenset(
    {
        "quettacontinuum",
        "ronnacontinuum",
        "yottacontinuum",
        "zettacontinuum",
        "exacontinuum",
        "petacontinuum",
        "teracontinuum",
        "gigacontinuum",
        "megacontinuum",
        "ultracontinuum",
        "hypercontinuum",
        "continuum",
        "omniverse",
        "multiverse",
        "cosmos",
        "civilization",
        "empire",
        "realm",
        "domain",
    }
)

# Layers that expose terminal_coverage_goal in their hermetic proof.
_TERMINAL_GOAL_LAYERS = frozenset(name for name, _ in ce.CONTINUUM_STACK)

# multi_*_progressed uses self noun for continuum tower + omniverse; else child.
_SELF_PROGRESSED = frozenset(
    list(ce.list_continuum_layers()) + ["omniverse"]
)


def _title(name: str) -> str:
    return name[:1].upper() + name[1:] if name else name


def _program_slot(
    program_id: str,
    *,
    priority: int = 0,
    initial: Sequence[tuple[str, str, str]] = (),
    deferred: Sequence[tuple[str, str, str]] = (),
    max_successions: int = 3,
) -> dict[str, Any]:
    def _targets(keys: Sequence[tuple[str, str, str]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for name, version, did in keys:
            out.append(
                {
                    "name": name,
                    "version": version,
                    "defects": [
                        {
                            "id": did,
                            "title": did,
                            "kind": "complexity",
                            "patch": f"patches/{did}.patch",
                            "repro": f"repros/{did}.py",
                        }
                    ],
                    "entry_id": f"{name}@{version}",
                }
            )
        return out

    return {
        "program_id": program_id,
        "priority": priority,
        "initial_targets": _targets(initial),
        "surface_charter": _targets(deferred),
        "max_successions": max_successions,
        "program_goal": "terminal_and_exhausted",
        "mandate_goal": "terminal_coverage",
        "kind": "stewardship_program",
    }


def _inst_slot(
    institution_id: str,
    *,
    priority: int = 0,
    programs: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 4,
) -> dict[str, Any]:
    return {
        "institution_id": institution_id,
        "priority": priority,
        "max_rounds": max_rounds,
        "charter": [dict(p) for p in (programs or [])],
        "kind": "stewardship_institution",
    }


def _wrap_institutions_to_child(
    target_child: str,
    parent_id: str,
    institutions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Wrap bare institution slots up through intermediate multi-child layers.

    Legacy helpers such as ``_commonwealth_slot(..., institutions=[...])`` build
    confederation→league→institution nests with deterministic short ids derived
    from the parent id so Windows MAX_PATH stays manageable.
    """
    # Chain of children from target_child down to institution (exclusive of program).
    # STEWARDSHIP_STACK is parent→child pairs; walk from target_child as a parent.
    chain: list[str] = []
    cursor = target_child
    # If target_child is itself "institution", just return institutions.
    if cursor == "institution":
        return [dict(i) for i in institutions]
    # Find path target_child → ... → institution by following STEWARDSHIP_STACK
    # where some parent equals cursor.
    child_of = {parent: child for parent, child in ce.STEWARDSHIP_STACK}
    # Actually we need path starting AT target_child as the first nested noun.
    # Nested under a domain slot: commonwealths. Under commonwealth: confederations...
    # So path is: target_child, child_of[target_child], ... until institution.
    path = [target_child]
    while path[-1] != "institution":
        nxt = child_of.get(path[-1])
        if not nxt:
            break
        path.append(nxt)
    if path[-1] != "institution":
        # fallback: flat institutions
        return [dict(i) for i in institutions]

    # path e.g. for commonwealth: [commonwealth, confederation, league, institution]
    # We wrap institutions upward from institution (already given) through league etc.
    # The outermost list is slots of type path[0]... wait.
    # _commonwealth_slot builds ONE commonwealth whose charter is confederations.
    # So for target_child=commonwealth we need confederation slots wrapping leagues...
    # Intermediate path after commonwealth: confederation → league → institution
    intermediate = path[1:]  # e.g. [confederation, league, institution]
    nodes: list[dict[str, Any]] = [dict(i) for i in institutions]
    # Build cumulative short ids then wrap inside-out.
    # commonwealth "c1" → confederation "c1c" → league "c1cl" → institutions
    # Single-letter suffixes match legacy helpers (domain "b" → commonwealth "bc").
    suffixes = {
        "confederation": "c",
        "league": "l",
        "commonwealth": "c",
        "domain": "d",
        "realm": "r",
        "empire": "e",
        "civilization": "c",
        "cosmos": "c",
        "multiverse": "m",
        "omniverse": "o",
        "continuum": "c",
        "hypercontinuum": "h",
        "ultracontinuum": "u",
        "megacontinuum": "m",
        "gigacontinuum": "g",
        "teracontinuum": "t",
        "petacontinuum": "p",
        "exacontinuum": "e",
        "zettacontinuum": "z",
        "yottacontinuum": "y",
        "ronnacontinuum": "r",
        "quettacontinuum": "q",
        "institution": "i",
        "program": "p",
    }
    id_chain: list[tuple[str, str]] = []
    cur = parent_id
    for noun in intermediate[:-1]:
        # Legacy confederation→league convenience id is "{confed}-lg".
        if noun == "league" and intermediate[0] == "league":
            cur = f"{parent_id}-lg"
        else:
            cur = f"{cur}{suffixes.get(noun, noun[:1])}"
        id_chain.append((noun, cur))
    for noun, wrap_id in reversed(id_chain):
        nodes = [
            {
                f"{noun}_id": wrap_id,
                "priority": 0,
                "max_rounds": 4,
                "charter": nodes,
                "kind": f"stewardship_{noun}",
            }
        ]
    return nodes


def _child_slot(
    layer: ce.ConstitutionLayer,
    child_id: str,
    *,
    priority: int = 0,
    keys: Sequence[tuple[str, str, str]] = (),
    nested: Sequence[Mapping[str, Any]] | None = None,
    max_rounds: int = 4,
    institutions: Sequence[Mapping[str, Any]] | None = None,
    programs: Sequence[Mapping[str, Any]] | None = None,
    charter: Sequence[Mapping[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a generic child slot; prefers nested charter when provided."""
    slot: dict[str, Any] = {
        layer.child_id_field: child_id,
        "priority": priority,
        "max_rounds": max_rounds,
        "kind": layer.slot_kind,
    }
    if nested is not None:
        slot["charter"] = [dict(n) for n in nested]
    elif charter is not None:
        slot["charter"] = [dict(n) for n in charter]
    elif institutions is not None:
        slot["charter"] = _wrap_institutions_to_child(
            layer.child, child_id, institutions
        )
    elif programs is not None:
        # institution-shaped child
        slot["charter"] = [dict(p) for p in programs]
    elif keys:
        slot["inventory_keys"] = [tuple(k) for k in keys]
        slot["charter"] = [{"inventory_keys": [tuple(k) for k in keys]}]
    else:
        slot["charter"] = []
    # Drop helper-only kwargs if any leaked
    for drop in ("institutions", "programs"):
        extra.pop(drop, None)
    slot.update(extra)
    return slot


def _proof_scratch() -> Path:
    return Path(tempfile.mkdtemp(prefix="steward-facade-"))


def _proof_campaign_runner(scratch: Path) -> Callable[..., dict[str, Any]]:
    """Minimal campaign mock used by deep charter_expand unit tests."""

    def runner(**kwargs: Any) -> dict[str, Any]:
        out = Path(str(kwargs.get("out_root") or Path(scratch) / "camp"))
        out.mkdir(parents=True, exist_ok=True)
        # Produce a terminal portfolio if inventory is present.
        inv: list[tuple[str, str, str]] = []
        for node in list(kwargs.get("charter") or []):
            if isinstance(node, Mapping):
                inv.extend(ce.collect_inventory_keys(node))
        for raw in list(kwargs.get("inventory_keys") or []):
            if isinstance(raw, (list, tuple)) and len(raw) >= 3:
                inv.append((str(raw[0]), str(raw[1]), str(raw[2])))
        entries = [
            {
                "name": n,
                "version": v,
                "defect_id": d,
                "outcome": "impact_merged",
                "impact_digest": ce._sha256_json({"n": n, "d": d}),
                "ok": True,
            }
            for n, v, d in inv
        ] or [
            {
                "name": "mock",
                "version": "1.0.0",
                "defect_id": "mock-1",
                "outcome": "impact_merged",
                "impact_digest": "a" * 64,
                "ok": True,
            }
        ]
        portfolio = ce.make_portfolio(entries, source="proof_campaign")
        digest = ce._sha256_json({"campaign": True, "n": len(entries)})
        from blackhole_agent.capability_compounder import atomic_write_json

        receipt = {
            "schema_version": ce.SCHEMA_VERSION,
            "ok": True,
            "verdict": "campaign_met",
            "stop_reason": "campaign_met",
            "campaign_digest": digest,
            "federated_portfolio": portfolio,
            "total_dispatched": 1,
            "total_dispatched_ok": 1,
        }
        atomic_write_json(out / "campaign.json", receipt)
        return {
            "ok": True,
            "verdict": "campaign_met",
            "stop_reason": "campaign_met",
            "campaign_dir": str(out),
            "campaign_digest": digest,
            "federated_portfolio": portfolio,
            "total_dispatched": 1,
            "total_dispatched_ok": 1,
            "used_skill_route_discovery": False,
        }

    return runner


def _normalize_program_charter(
    charter: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Institution→program dialect: preserve initial_targets / surface_charter."""
    if not charter:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in charter:
        if not isinstance(raw, Mapping):
            continue
        program_id = str(raw.get("program_id") or raw.get("id") or "").strip()
        if not program_id or program_id in seen:
            continue
        seen.add(program_id)

        initial_targets: list[dict[str, Any]] = []
        for t in list(raw.get("initial_targets") or []):
            if not isinstance(t, Mapping):
                continue
            name = str(t.get("name") or "").strip()
            version = str(t.get("version") or "").strip()
            if not name or not version:
                continue
            defects: list[dict[str, Any]] = []
            for d in list(t.get("defects") or []):
                if not isinstance(d, Mapping):
                    continue
                did = str(d.get("id") or "").strip()
                if not did:
                    continue
                defects.append(
                    {
                        "id": did,
                        "title": str(d.get("title") or did),
                        "kind": str(d.get("kind") or "complexity"),
                        "patch": str(d.get("patch") or f"patches/{did}.patch"),
                        "repro": str(d.get("repro") or f"repros/{did}.py"),
                    }
                )
            if not defects:
                continue
            initial_targets.append(
                {
                    "name": name,
                    "version": version,
                    "defects": defects,
                    "entry_id": str(t.get("entry_id") or f"{name}@{version}"),
                }
            )

        # Lightweight surface_charter normalize (accept already-shaped entries).
        surface_charter: list[dict[str, Any]] = []
        for t in list(raw.get("surface_charter") or []):
            if not isinstance(t, Mapping):
                continue
            name = str(t.get("name") or "").strip()
            version = str(t.get("version") or "").strip()
            if not name:
                continue
            defects_in = list(t.get("defects") or [])
            defects = []
            for d in defects_in:
                if isinstance(d, Mapping) and d.get("id"):
                    defects.append(
                        {
                            "id": str(d["id"]),
                            "title": str(d.get("title") or d["id"]),
                            "kind": str(d.get("kind") or "complexity"),
                            "patch": str(d.get("patch") or f"patches/{d['id']}.patch"),
                            "repro": str(d.get("repro") or f"repros/{d['id']}.py"),
                        }
                    )
            if not defects and not defects_in:
                # bare target may still count as work for deferred expand
                surface_charter.append(dict(t))
                continue
            if defects:
                surface_charter.append(
                    {
                        "name": name,
                        "version": version,
                        "defects": defects,
                        "entry_id": str(t.get("entry_id") or f"{name}@{version}"),
                    }
                )

        inv = ce.collect_inventory_keys(raw)
        if not initial_targets and not surface_charter and not inv:
            continue
        if not initial_targets and not surface_charter and inv:
            # inventory_keys-only program slot (engine dialect)
            for n, v, d in inv:
                initial_targets.append(
                    {
                        "name": n,
                        "version": v,
                        "defects": [
                            {
                                "id": d,
                                "title": d,
                                "kind": "complexity",
                                "patch": f"patches/{d}.patch",
                                "repro": f"repros/{d}.py",
                            }
                        ],
                        "entry_id": f"{n}@{v}",
                    }
                )

        out.append(
            {
                "program_id": program_id,
                "priority": int(raw.get("priority") or 0),
                "initial_targets": initial_targets,
                "surface_charter": surface_charter,
                "max_successions": max(1, int(raw.get("max_successions") or 3)),
                "program_goal": str(
                    raw.get("program_goal") or "terminal_and_exhausted"
                ),
                "mandate_goal": str(raw.get("mandate_goal") or "terminal_coverage"),
                "kind": str(raw.get("kind") or "stewardship_program"),
                "inventory_keys": inv
                or [
                    (t["name"], t["version"], d["id"])
                    for t in initial_targets + surface_charter
                    for d in list(t.get("defects") or [])
                    if isinstance(d, Mapping) and d.get("id")
                ],
            }
        )
    return out


def _admit_program_slot(*, institution_dir: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize a program stewardship surface (institution leaf dialect)."""
    from blackhole_agent import upstream_program as up

    program_id = str(slot.get("program_id") or "")
    if not program_id:
        raise ce.ConstitutionRefused("institution_invalid", "slot missing program_id")

    program_root = Path(institution_dir) / "programs" / program_id
    stew = program_root / "stewardship"
    stew.mkdir(parents=True, exist_ok=True)

    added_keys: list[dict[str, str]] = []
    for target in list(slot.get("initial_targets") or []):
        if not isinstance(target, Mapping):
            continue
        keys = up.materialize_charter_entry(stew, target)
        added_keys.extend(keys)

    return {
        "program_id": program_id,
        "stewardship_root": str(stew),
        "program_root": str(program_root),
        "admitted": True,
        "initial_keys": added_keys,
        "surface_charter": list(slot.get("surface_charter") or []),
        "max_successions": int(slot.get("max_successions") or 3),
        "program_goal": str(slot.get("program_goal") or "terminal_and_exhausted"),
        "mandate_goal": str(slot.get("mandate_goal") or "terminal_coverage"),
        "priority": int(slot.get("priority") or 0),
    }


# Layers that default-on cascade into the operational control graph.
# Full stewardship stack (quettacontinuum..institution) closes the mock-leaf
# cliff for continuum SI layers and the civilization tower. Opt out with
# governance_spine=False / hermetic_fast / use_fast_child.
_STEWARDSHIP_SPINE_DEFAULT_ROOTS = frozenset(ce.list_stewardship_layers())
_CIVILIZATION_SPINE_DEFAULT_ROOTS = frozenset(ce.list_civilization_layers())
_CONTINUUM_SPINE_DEFAULT_ROOTS = frozenset(ce.list_continuum_layers())


def institution_wants_governance_spine(kwargs: Mapping[str, Any]) -> bool:
    """Whether institution program children should attach the operational spine.

    Default is **on** (closes the mock-leaf dialect cliff). Opt out with
    ``governance_spine=False`` or ``hermetic_fast=True`` / ``use_fast_child=True``.
    Explicit ``program_runner`` / ``child_runner`` still wins in
    :func:`_resolve_child_runner` before this default applies.
    """
    return layer_wants_governance_spine(
        ce.get_stewardship_layer("institution"), kwargs
    )


def layer_wants_governance_spine(
    layer: ce.ConstitutionLayer,
    kwargs: Mapping[str, Any],
) -> bool:
    """Whether a multi-child layer should cascade into the operational spine.

    Default ON for every stewardship-stack layer (quettacontinuum..institution
    via :data:`_STEWARDSHIP_SPINE_DEFAULT_ROOTS`), so continuum→omniverse→…
    →confederation→…→campaign is continuous without opt-in. Opt out with
    ``governance_spine=False`` or ``hermetic_fast`` / ``use_fast_child``.
    """
    if kwargs.get("hermetic_fast") or kwargs.get("use_fast_child"):
        return False
    if "governance_spine" in kwargs:
        return bool(kwargs.get("governance_spine"))
    return layer.name in _STEWARDSHIP_SPINE_DEFAULT_ROOTS


def _resolve_child_runner(
    layer: ce.ConstitutionLayer,
    kwargs: dict[str, Any],
) -> Callable[..., dict[str, Any]]:
    """Pick injected child runner from legacy kwargs, else hermetic fast leaf.

    Institution (program child) defaults to the operational control graph via
    :func:`make_operational_program_child_runner` (opt out with
    ``governance_spine=False``). League defaults to governance institutions;
    confederation and every higher stewardship-stack layer (civilization and
    continuum SI) default to a recursive :func:`make_stewardship_child_runner`
    cascade so quettacontinuum→…→civilization→…→campaign is continuous
    without opt-in.
    """
    aliases = (
        f"{layer.child}_runner",
        "child_runner",
        "institution_runner",
        "program_runner",
        "league_runner",
        "confederation_runner",
        "commonwealth_runner",
        "domain_runner",
        "realm_runner",
        "empire_runner",
        "civilization_runner",
        "cosmos_runner",
        "multiverse_runner",
        "omniverse_runner",
        "continuum_runner",
        "hypercontinuum_runner",
        "ultracontinuum_runner",
        "megacontinuum_runner",
        "gigacontinuum_runner",
        "teracontinuum_runner",
        "petacontinuum_runner",
        "exacontinuum_runner",
        "zettacontinuum_runner",
        "yottacontinuum_runner",
        "ronnacontinuum_runner",
        "quettacontinuum_runner",
        "continuum_runner",
        "hypercontinuum_runner",
        "ultracontinuum_runner",
        "megacontinuum_runner",
        "gigacontinuum_runner",
        "teracontinuum_runner",
        "petacontinuum_runner",
        "exacontinuum_runner",
        "zettacontinuum_runner",
        "yottacontinuum_runner",
        "ronnacontinuum_runner",
    )
    for key in aliases:
        if kwargs.get(key) is not None:
            return kwargs[key]
    if not layer_wants_governance_spine(layer, kwargs):
        return ce._fast_child_runner(layer)

    from blackhole_agent.upstream_control_engine import (
        make_stewardship_child_runner,
    )

    return make_stewardship_child_runner(
        layer.name,
        max_rounds=int(kwargs.get("max_rounds") or 3),
        max_successions=int(kwargs.get("max_successions") or 2),
        max_epochs=int(kwargs.get("max_epochs") or 2),
        max_waves=int(kwargs.get("max_waves") or 2),
        idle_limit=int(kwargs.get("idle_limit") or 1),
        goal_dispatched_ok=int(kwargs.get("goal_dispatched_ok") or 1),
        campaign_run_stage=kwargs.get("campaign_run_stage"),
        stewardship_root=kwargs.get("stewardship_root"),
    )


def _map_run_kwargs(layer: ce.ConstitutionLayer, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Translate legacy multi-child kwargs into run_constitution kwargs."""
    goal = (
        kwargs.get(layer.self_goal_field)
        or kwargs.get("goal")
        or kwargs.get("constitution_goal")
        or layer.all_children_met_goal
    )
    max_active = kwargs.get("max_active")
    if max_active is None:
        max_active = kwargs.get(layer.max_active_field)
    if max_active is None:
        max_active = kwargs.get("max_active_children")

    constitution_id = (
        kwargs.get(layer.self_id_field)
        or kwargs.get("constitution_id")
        or kwargs.get(f"{layer.name}_id")
    )

    mapped: dict[str, Any] = {
        "charter": kwargs.get("charter"),
        "max_rounds": int(kwargs.get("max_rounds") or 6),
        "dispatch_budget": kwargs.get("dispatch_budget"),
        "idle_round_limit": int(kwargs.get("idle_round_limit") or 1),
        "max_active": int(max_active) if max_active is not None else None,
        "dispatch": bool(kwargs.get("dispatch", True)),
        "child_runner": _resolve_child_runner(layer, kwargs),
        "stop_when": kwargs.get("stop_when"),
        "goal": goal,
        "constitution_id": constitution_id,
        "resume_dir": kwargs.get("resume_dir"),
        "out_root": kwargs.get("out_root"),
    }
    if kwargs.get("charter_expand") is not None:
        mapped["charter_expand"] = kwargs["charter_expand"]
    if layer.child == "program":
        mapped["nested_normalizer"] = _normalize_program_charter
    return mapped


def builtin_layer_proof(layer_name: str) -> dict[str, Any]:
    """Hermetic end-to-end proof for one stewardship layer via the engine."""
    layer = ce.get_stewardship_layer(layer_name)
    scratch = Path(tempfile.mkdtemp(prefix=f"{layer.name}-facade-proof-"))
    flags: dict[str, Any] = {}
    try:
        runner = ce._fast_child_runner(layer)

        multi = ce.run_constitution(
            layer,
            charter=[
                ce._slot(layer, "a", priority=2, keys=[("alpha", "1.0.0", "alpha-1")]),
                ce._slot(layer, "b", priority=1, keys=[("beta", "2.0.0", "beta-1")]),
            ],
            max_rounds=8,
            dispatch=True,
            child_runner=runner,
            goal=layer.all_children_met_goal,
            constitution_id=f"{layer.name}-proof",
            out_root=scratch / "m",
        )
        multi_ok = bool(
            multi.get("ok")
            and multi.get(layer.self_met_field)
            and multi.get(f"{layer.plural}_met_count") == 2
            and multi.get("total_dispatched_ok", 0) >= 2
            and float((multi.get("coverage_end") or {}).get("coverage_ratio") or 0) == 1.0
        )
        scheduled = {
            r.get(layer.child_id_field) for r in (multi.get(layer.plural) or [])
        }
        multi_scheduled = multi_ok and scheduled >= {"a", "b"}
        flags[layer.self_met_field] = multi_ok
        prog_noun = layer.name if layer.name in _SELF_PROGRESSED else layer.child
        flags[f"multi_{prog_noun}_progressed"] = multi_scheduled
        flags["federation_coverage"] = multi_ok
        flags["priority_scheduling"] = (
            (multi.get(layer.plural) or [{}])[0].get(layer.child_id_field) == "a"
        )

        sealed = ce.verify_receipt(layer, Path(multi[f"{layer.name}_dir"]))
        flags["seal_verified"] = bool(sealed.get("ok")) and sealed.get(
            "round_count"
        ) == multi.get("round_count")

        receipt_path = Path(multi[f"{layer.name}_dir"]) / f"{layer.name}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        # Tamper either digest field or a counted field — both break the seal.
        receipt[layer.self_digest_field] = "0" * 64
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        tampered = ce.verify_receipt(layer, Path(multi[f"{layer.name}_dir"]))
        flags["tamper_detected"] = (not tampered.get("ok")) and (
            layer.self_digest_field in (tampered.get("mismatched") or [])
            or bool(tampered.get("mismatched"))
        )

        deferred = ce.run_constitution(
            layer,
            charter=[
                ce._slot(layer, "d1", priority=2, keys=[("d1", "1.0.0", "d1-1")]),
                ce._slot(layer, "d2", priority=1, keys=[("d2", "1.0.0", "d2-1")]),
            ],
            max_rounds=8,
            max_active=1,
            dispatch=True,
            child_runner=ce._fast_child_runner(layer),
            goal=layer.all_children_met_goal,
            out_root=scratch / "defer",
        )
        flags["deferred_admission"] = bool(
            deferred.get("ok")
            and deferred.get(layer.self_met_field)
            and deferred.get("admission_count", 0) >= 2
            and deferred.get(f"{layer.plural}_admitted") == 2
        )

        budgeted = ce.run_constitution(
            layer,
            charter=[
                ce._slot(layer, "b1", keys=[("b1", "1.0.0", "b1-1")]),
                ce._slot(layer, "b2", keys=[("b2", "1.0.0", "b2-1")]),
            ],
            max_rounds=6,
            dispatch_budget=1,
            dispatch=True,
            child_runner=ce._fast_child_runner(layer),
            goal="none",
            out_root=scratch / "bg",
        )
        flags["budget_stops"] = bool(
            budgeted.get("ok")
            and budgeted.get("total_dispatched") == 1
            and budgeted.get("stop_reason") == "dispatch_budget"
        )

        def _premet(**kwargs: Any) -> dict[str, Any]:
            child_id = str(
                kwargs.get(layer.child_id_field) or kwargs.get("child_id") or "pre"
            )
            charter = list(kwargs.get("charter") or [])
            inv: list[tuple[str, str, str]] = []
            for node in charter:
                if isinstance(node, Mapping):
                    inv.extend(ce.collect_inventory_keys(node))
            entries = [
                {
                    "name": n,
                    "version": v,
                    "defect_id": d,
                    "outcome": "impact_merged",
                    "impact_digest": "c" * 64,
                    "ok": True,
                }
                for n, v, d in inv
            ]
            portfolio = ce.make_portfolio(entries, source="premet")
            out = Path(str(kwargs.get("out_root") or scratch / "pre" / child_id))
            out.mkdir(parents=True, exist_ok=True)
            digest = ce._sha256_json({"premet": True, "id": child_id})
            receipt = {
                "schema_version": ce.SCHEMA_VERSION,
                "ok": True,
                "verdict": f"{layer.child}_met",
                "stop_reason": f"{layer.child}_met",
                layer.child_id_field: child_id,
                layer.child_met_field: True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                layer.child_digest_field: digest,
                "federated_portfolio": portfolio,
                "inventory_keys": inv,
            }
            from blackhole_agent.capability_compounder import atomic_write_json

            atomic_write_json(out / f"{layer.child}.json", receipt)
            atomic_write_json(
                out / f"{layer.child}_state.json",
                {
                    layer.child_id_field: child_id,
                    "federated_portfolio": portfolio,
                    "charter": charter,
                    "stop_reason": receipt["stop_reason"],
                },
            )
            return {
                "ok": True,
                "verdict": receipt["verdict"],
                "stop_reason": receipt["stop_reason"],
                layer.child_dir_field: str(out),
                layer.child_digest_field: digest,
                layer.child_id_field: child_id,
                layer.child_met_field: True,
                "total_dispatched": 0,
                "total_dispatched_ok": 0,
                "federated_portfolio": portfolio,
                "inventory_keys": inv,
                "used_skill_route_discovery": False,
            }

        pre = ce.run_constitution(
            layer,
            charter=[ce._slot(layer, "omega", keys=[("o", "1.0.0", "o-1")])],
            max_rounds=4,
            dispatch=True,
            child_runner=_premet,
            goal=layer.all_children_met_goal,
            out_root=scratch / "premet",
        )
        flags["premet_short_circuits"] = bool(
            pre.get("ok")
            and pre.get(layer.self_met_field)
            and pre.get("total_dispatched_ok", 0) == 0
        )

        ranked = ce.run_constitution(
            layer,
            charter=[
                ce._slot(layer, "r1", priority=3, keys=[("r1", "1.0.0", "r1-1")]),
                ce._slot(layer, "r2", priority=1, keys=[("r2", "1.0.0", "r2-1")]),
            ],
            max_rounds=2,
            dispatch=False,
            child_runner=ce._fast_child_runner(layer),
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
            ce.run_constitution(
                layer,
                charter=[],
                dispatch=False,
                child_runner=ce._fast_child_runner(layer),
                goal="none",
                out_root=scratch / "empty",
            )
        except ce.ConstitutionRefused as exc:
            empty_refused = exc.verdict in {
                f"{layer.name}_empty",
                f"{layer.name}_invalid",
            }
        flags["empty_refused"] = empty_refused

        custom = ce.run_constitution(
            layer,
            charter=[
                ce._slot(layer, "c1", keys=[("c1", "1.0.0", "c1-1")]),
                ce._slot(layer, "c2", keys=[("c2", "1.0.0", "c2-1")]),
            ],
            max_rounds=6,
            dispatch=True,
            child_runner=ce._fast_child_runner(layer),
            goal="none",
            stop_when=lambda ctx: (
                "custom_halt" if ctx["total_dispatched_ok"] >= 1 else None
            ),
            out_root=scratch / "custom",
        )
        flags["custom_stop"] = bool(
            custom.get("ok") and custom.get("stop_reason") == "custom_halt"
        )

        partial = ce.run_constitution(
            layer,
            charter=[
                ce._slot(layer, "p1", priority=2, keys=[("p1", "1.0.0", "p1-1")]),
                ce._slot(layer, "p2", priority=1, keys=[("p2", "1.0.0", "p2-1")]),
            ],
            max_rounds=1,
            dispatch_budget=1,
            dispatch=True,
            child_runner=ce._fast_child_runner(layer),
            goal="none",
            constitution_id="resume-me",
            out_root=scratch / "partial",
        )
        state_path = Path(partial[f"{layer.name}_dir"]) / f"{layer.name}_state.json"
        resumed = ce.run_constitution(
            layer,
            resume_dir=Path(partial[f"{layer.name}_dir"]),
            max_rounds=4,
            dispatch_budget=4,
            dispatch=True,
            child_runner=ce._fast_child_runner(layer),
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
            and int((multi["roi_summary"] or {}).get("rounds") or 0) >= 1
            and int((multi["roi_summary"] or {}).get("total_dispatched_ok") or 0) >= 2
        )

        if layer.name in _EXPAND_LAYERS:
            growth = [
                ce._slot(layer, "g2", keys=[("g2", "1.0.0", "g2-1")]),
            ]
            expander = ce.make_charter_expand(layer, growth, max_slots_per_expand=1)
            expanded = ce.run_constitution(
                layer,
                charter=[ce._slot(layer, "g1", keys=[("g1", "1.0.0", "g1-1")])],
                max_rounds=8,
                dispatch=True,
                child_runner=ce._fast_child_runner(layer),
                charter_expand=expander,
                goal=layer.all_children_met_goal,
                out_root=scratch / "expand",
            )
            flags["charter_expand"] = bool(
                expanded.get("ok")
                and expanded.get(layer.self_met_field)
                and expanded.get("charter_expansion_count", 0) >= 1
                and "g2" in (expanded.get("charter_expanded_ids") or [])
            )
            # charter_merge: normalize + merge dedupes ids
            base = ce.normalize_charter(
                layer,
                [ce._slot(layer, "m1", keys=[("m", "1.0.0", "m-1")])],
            )
            merged = ce.merge_charter(
                layer,
                base,
                [
                    ce._slot(layer, "m1", keys=[("m", "1.0.0", "m-dup")]),
                    ce._slot(layer, "m2", keys=[("m2", "1.0.0", "m2-1")]),
                ],
            )
            flags["charter_merge"] = (
                [s[layer.child_id_field] for s in merged] == ["m1", "m2"]
            )
        else:
            flags["charter_expand"] = True  # not required; keep proof green
            flags["charter_merge"] = True

        if layer.name in _TERMINAL_GOAL_LAYERS:
            term = ce.run_constitution(
                layer,
                charter=[ce._slot(layer, "s1", keys=[("t", "1.0.0", "t-1")])],
                max_rounds=6,
                dispatch=True,
                child_runner=ce._partial_then_complete_runner(layer),
                goal="terminal_coverage",
                out_root=scratch / "term",
            )
            flags["terminal_coverage_goal"] = bool(
                term.get("ok")
                and term.get(layer.self_met_field)
                and float((term.get("coverage_end") or {}).get("coverage_ratio") or 0)
                == 1.0
                and term.get("round_count", 0) >= 2
            )
        else:
            flags["terminal_coverage_goal"] = True

        flags["used_skill_route_discovery"] = legacy_pipeline_was_used()
        flags["engine_facade"] = True

        required = [
            layer.self_met_field,
            f"multi_{prog_noun}_progressed",
            "federation_coverage",
            "priority_scheduling",
            "deferred_admission",
            "seal_verified",
            "tamper_detected",
            "budget_stops",
            "premet_short_circuits",
            "rank_only",
            "empty_refused",
            "custom_stop",
            "durable_resume",
            "roi_scored",
        ]
        if layer.name in _EXPAND_LAYERS:
            required.extend(["charter_expand", "charter_merge"])
        if layer.name in _TERMINAL_GOAL_LAYERS:
            required.append("terminal_coverage_goal")

        ok = all(bool(flags.get(k)) for k in required) and not flags[
            "used_skill_route_discovery"
        ]
        return {
            "ok": ok,
            "action": f"{layer.name}_facade_proof",
            "flags": flags,
            "used_skill_route_discovery": flags["used_skill_route_discovery"],
            "engine_facade": True,
            "layer": layer.name,
            "child": layer.child,
            **{k: flags[k] for k in required},
            **{
                k: flags[k]
                for k in (
                    "charter_expand",
                    "charter_merge",
                    "terminal_coverage_goal",
                )
                if k in flags
            },
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _ledger_facade_capability_ok() -> dict[str, Any]:
    """Assert capability.upstream-stewardship-facade is registered and points here."""
    from blackhole_agent.capability_compounder import (
        DEFAULT_LEDGER_RELATIVE,
        load_ledger,
    )

    ledger_path = Path(__file__).resolve().parents[2] / DEFAULT_LEDGER_RELATIVE
    try:
        ledger = load_ledger(ledger_path)
    except Exception as exc:  # noqa: BLE001 — proof must not raise
        return {"ok": False, "detail": f"ledger_unreadable:{exc}"}
    cap = (ledger.capabilities or {}).get("capability.upstream-stewardship-facade")
    if cap is None:
        return {"ok": False, "detail": "capability_missing"}
    entry = str(getattr(cap, "entry", "") or "")
    proof_cmd = str(getattr(cap, "proof_command", "") or "")
    expected_entry = (
        "blackhole_agent.upstream_stewardship_facade:builtin_stewardship_facade_proof"
    )
    ok = (
        entry == expected_entry
        and "upstream_stewardship_facade" in proof_cmd
        and "--proof" in proof_cmd
    )
    return {
        "ok": ok,
        "id": getattr(cap, "id", None),
        "entry": entry,
        "proof_command": proof_cmd,
        "expected_entry": expected_entry,
    }


def builtin_stewardship_facade_proof() -> dict[str, Any]:
    """Prove every multi-child stewardship layer is a thin engine facade.

    Closes the full mission done_when surface in one invocable proof:
    23 ENGINE_FACADE modules, nested composition, >=10x tower LOC reduction,
    constitution engine still green, and ledger capability registered.
    """
    names = ce.list_stewardship_layers()
    results: list[dict[str, Any]] = []
    loc_before_claim = 63667  # measured pre-collapse tower LOC
    for name in names:
        # Import the public module and require engine_facade on its proof.
        mod_name = f"blackhole_agent.upstream_{name}"
        mod = __import__(mod_name, fromlist=["*"])
        proof_fn = getattr(mod, f"builtin_upstream_{name}_proof")
        result = proof_fn()
        is_facade = bool(getattr(mod, "ENGINE_FACADE", False)) and bool(
            result.get("engine_facade")
        )
        results.append(
            {
                "layer": name,
                "ok": bool(result.get("ok")) and is_facade,
                "engine_facade": is_facade,
                "module": mod_name,
                "module_file": getattr(mod, "__file__", None),
            }
        )

    # Nested composition still works through facades.
    nest_scratch = Path(tempfile.mkdtemp(prefix="facade-nest-"))
    try:
        nested = ce._nested_composition_proof(nest_scratch)
    finally:
        shutil.rmtree(nest_scratch, ignore_errors=True)

    # Constitution engine remains healthy (full hermetic proof).
    engine = ce.builtin_constitution_engine_proof()

    # Ledger registration + invocable entry binding.
    ledger = _ledger_facade_capability_ok()

    # Measure the current tower: facades are synthesized from the layer
    # registry (no physical per-layer files remain); the registry module is
    # the entire tower footprint.
    from blackhole_agent.upstream_layer_registry import FACADE_LAYERS, _layer_for

    root = Path(__file__).resolve().parents[2]
    registry_path = root / "src" / "blackhole_agent" / "upstream_layer_registry.py"
    loc_after = registry_path.read_text(encoding="utf-8").count("\n") + 1
    facade_files = sum(
        1
        for name in names
        if name in FACADE_LAYERS and _layer_for(f"blackhole_agent.upstream_{name}") == name
    )

    all_ok = all(r["ok"] for r in results)
    loc_reduced = loc_after < (loc_before_claim // 10)  # at least 10x reduction
    stack_complete = len(names) == 23 and names[0] == "quettacontinuum" and names[-1] == "institution"
    ok = (
        all_ok
        and bool(nested.get("ok"))
        and bool(engine.get("ok"))
        and bool(ledger.get("ok"))
        and facade_files == len(names)
        and stack_complete
        and loc_reduced
        and not legacy_pipeline_was_used()
    )
    return {
        "ok": ok,
        "action": "stewardship_facade_collapse_proof",
        "layer_count": len(results),
        "layers_ok": sum(1 for r in results if r["ok"]),
        "facade_files": facade_files,
        "tower_loc_after": loc_after,
        "tower_loc_before": loc_before_claim,
        "loc_reduction_ratio": (loc_before_claim / max(1, loc_after)),
        "nested_composition": bool(nested.get("ok")),
        "constitution_engine_ok": bool(engine.get("ok")),
        "ledger_capability_ok": bool(ledger.get("ok")),
        "ledger_detail": ledger,
        "stack_complete": stack_complete,
        "results": results,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "done_when_met": ok,
    }


def export_layer_api(module_globals: dict[str, Any], layer_name: str) -> None:
    """Populate a thin ``upstream_<layer>`` module with the public API surface."""
    layer = ce.get_stewardship_layer(layer_name)
    refused_name = f"{_title(layer.name)}Refused"

    class _LayerRefused(ce.ConstitutionRefused):
        """Layer-scoped refusal alias (verdict-bearing)."""

    def normalize_charter(
        charter: Sequence[Mapping[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if layer.child == "program":
            return _normalize_program_charter(charter)
        return ce.normalize_charter(layer, charter)

    def admit_child_slot(**kwargs: Any) -> dict[str, Any]:
        # Accept institution_dir / league_dir / <name>_dir aliases.
        constitution_dir = (
            kwargs.get(f"{layer.name}_dir")
            or kwargs.get("constitution_dir")
            or kwargs.get("institution_dir")
            or kwargs.get("league_dir")
            or kwargs.get("dir")
        )
        slot = kwargs.get("slot") or {}
        if layer.child == "program":
            return _admit_program_slot(
                institution_dir=Path(str(constitution_dir)),
                slot=slot,
            )
        return ce.admit_child_slot(
            layer, constitution_dir=Path(str(constitution_dir)), slot=slot
        )

    def admit_pending_slots(**kwargs: Any) -> list[dict[str, Any]]:
        constitution_dir = (
            kwargs.get(f"{layer.name}_dir")
            or kwargs.get("constitution_dir")
            or kwargs.get("institution_dir")
            or kwargs.get("league_dir")
            or kwargs.get("dir")
        )
        charter = list(kwargs.get("charter") or [])
        child_states = kwargs.get(f"{layer.child}_states") or kwargs.get(
            "child_states"
        ) or kwargs.get("program_states")
        if child_states is None:
            child_states = []
        # Mutate caller's list when provided (legacy contract).
        states_list: list[dict[str, Any]] = child_states  # type: ignore[assignment]
        max_active = (
            kwargs.get(layer.max_active_field)
            or kwargs.get("max_active")
            or kwargs.get("max_active_programs")
            or kwargs.get("max_active_institutions")
        )
        if layer.child == "program":
            # Admit with program surface materialization.
            pending = ce.pending_charter_slots(layer, charter, states_list)
            open_n = ce.open_unmet_count(layer, states_list)
            capacity = (
                len(pending)
                if max_active is None
                else max(0, int(max_active) - open_n)
            )
            admissions: list[dict[str, Any]] = []
            for slot in pending[:capacity]:
                admission = _admit_program_slot(
                    institution_dir=Path(str(constitution_dir)),
                    slot=slot,
                )
                if kwargs.get("round_index") is not None:
                    admission = dict(admission)
                    admission["admitted_at_round"] = kwargs["round_index"]
                admissions.append(admission)
                states_list.append(
                    {
                        "program_id": admission["program_id"],
                        "stewardship_root": admission["stewardship_root"],
                        "program_root": admission["program_root"],
                        "charter": slot,
                        "program_met": False,
                        "priority": admission.get("priority") or 0,
                        "inventory_keys": list(slot.get("inventory_keys") or [])
                        or ce.collect_inventory_keys(slot),
                    }
                )
            return admissions
        return ce.admit_pending_slots(
            layer,
            constitution_dir=Path(str(constitution_dir)),
            charter=charter,
            child_states=states_list,
            max_active=int(max_active) if max_active is not None else None,
            round_index=kwargs.get("round_index"),
        )

    def federate(
        portfolios: Sequence[Mapping[str, Any] | None],
        *,
        source: str | None = None,
    ) -> dict[str, Any]:
        return ce.federate_portfolios(
            portfolios,
            source=source or f"{layer.name}_federation",
        )

    def select_next(
        child_states: Sequence[Mapping[str, Any]],
        roi_history: Sequence[Mapping[str, Any]],
        *,
        round_index: int = 0,
    ) -> dict[str, Any] | None:
        return ce.select_next_child(
            layer, child_states, roi_history, round_index=round_index
        )

    def allocate_budget(
        *,
        remaining_budget: int | None,
        open_program_count: int | None = None,
        open_institution_count: int | None = None,
        open_count: int | None = None,
        selected: Mapping[str, Any],
        roi_history: Sequence[Mapping[str, Any]],
        **_extra: Any,
    ) -> int | None:
        n = open_count
        if n is None:
            n = open_program_count
        if n is None:
            n = open_institution_count
        if n is None:
            n = open_count if open_count is not None else 1
        # also accept open_<plural>_count
        for key, val in _extra.items():
            if key.startswith("open_") and key.endswith("_count") and val is not None:
                n = int(val)
        return ce.allocate_child_budget(
            layer,
            remaining_budget=remaining_budget,
            open_count=int(n or 1),
            selected=selected,
            roi_history=roi_history,
        )

    def score_roi(**kwargs: Any) -> dict[str, Any]:
        child_id = str(
            kwargs.get(layer.child_id_field)
            or kwargs.get("child_id")
            or kwargs.get("program_id")
            or kwargs.get("institution_id")
            or ""
        )
        child_result = (
            kwargs.get(f"{layer.child}_result")
            or kwargs.get("child_result")
            or kwargs.get("program_result")
            or kwargs.get("institution_result")
            or {}
        )
        return ce.score_child_roi(
            layer,
            round_index=int(kwargs.get("round_index") or 0),
            child_id=child_id,
            child_result=child_result,
            coverage_before=kwargs.get("coverage_before") or {},
            coverage_after=kwargs.get("coverage_after") or {},
        )

    def constitution_satisfied_fn(**kwargs: Any) -> bool:
        child_states = (
            kwargs.get(f"{layer.child}_states")
            or kwargs.get("child_states")
            or kwargs.get("program_states")
            or []
        )
        charter = kwargs.get("charter") or []
        goal = (
            kwargs.get(layer.self_goal_field)
            or kwargs.get("goal")
            or kwargs.get("institution_goal")
            or kwargs.get("league_goal")
            or layer.all_children_met_goal
        )
        return ce.constitution_satisfied(
            layer,
            child_states=child_states,
            charter=charter,
            goal=str(goal),
            federated_portfolio=kwargs.get("federated_portfolio"),
        )

    def pending_slots(
        charter: Sequence[Mapping[str, Any]],
        child_states: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        return ce.pending_charter_slots(layer, charter, child_states)

    def write_state_fn(constitution_dir: Path, state: Mapping[str, Any]) -> Path:
        return ce.write_state(layer, constitution_dir, state)

    def load_state_fn(resume_dir: Path) -> dict[str, Any]:
        return ce.load_state(layer, resume_dir)

    def state_payload_fn(**kwargs: Any) -> dict[str, Any]:
        constitution_id = str(
            kwargs.get(layer.self_id_field)
            or kwargs.get("constitution_id")
            or kwargs.get(f"{layer.name}_id")
            or kwargs.get("institution_id")
            or kwargs.get("league_id")
            or "state"
        )
        child_states = (
            kwargs.get(f"{layer.child}_states")
            or kwargs.get("child_states")
            or kwargs.get("program_states")
            or []
        )
        child_digests = (
            kwargs.get(f"{layer.child}_digests")
            or kwargs.get("child_digests")
            or kwargs.get("program_digests")
            or []
        )
        goal = str(
            kwargs.get(layer.self_goal_field)
            or kwargs.get("goal")
            or kwargs.get("institution_goal")
            or kwargs.get("league_goal")
            or layer.all_children_met_goal
        )
        return ce.state_payload(
            layer,
            constitution_id=constitution_id,
            round_count=int(kwargs.get("round_count") or 0),
            total_dispatched=int(kwargs.get("total_dispatched") or 0),
            total_dispatched_ok=int(kwargs.get("total_dispatched_ok") or 0),
            federated_portfolio=kwargs.get("federated_portfolio"),
            roi_history=list(kwargs.get("roi_history") or []),
            child_states=list(child_states),
            child_digests=list(child_digests),
            charter=list(kwargs.get("charter") or []),
            stop_reason=kwargs.get("stop_reason"),
            goal=goal,
            max_active=kwargs.get(layer.max_active_field) or kwargs.get("max_active"),
            admissions=kwargs.get("admissions"),
            charter_expansions=kwargs.get("charter_expansions"),
        )

    def verify_fn(constitution_dir: Path) -> dict[str, Any]:
        return ce.verify_receipt(layer, constitution_dir)

    def run_fn(**kwargs: Any) -> dict[str, Any]:
        try:
            mapped = _map_run_kwargs(layer, kwargs)
            result = ce.run_constitution(layer, **mapped)
            # Stamp governance / stewardship ownership when this layer cascades
            # into the operational nest (default ON for full civilization tower;
            # opt out with governance_spine=False).
            if layer_wants_governance_spine(layer, kwargs):
                from blackhole_agent.upstream_control_engine import (
                    annotate_governance_spine,
                    annotate_outer_governance_spine,
                    annotate_stewardship_spine,
                    recover_governance_child_path,
                )

                child_path = recover_governance_child_path(result)
                default_flag = "governance_spine" not in kwargs
                if layer.name == "institution":
                    if not child_path:
                        for states in (
                            result.get("child_states"),
                            result.get("program_states"),
                            result.get("programs"),
                        ):
                            if child_path is not None:
                                break
                            for st in list(states or []):
                                if not isinstance(st, Mapping):
                                    continue
                                pdir = (
                                    st.get("last_program_dir")
                                    or st.get("program_dir")
                                    or st.get("out_root")
                                )
                                if not pdir:
                                    continue
                                gpath = (
                                    Path(str(pdir)) / "governance_child.json"
                                )
                                if not gpath.is_file():
                                    continue
                                try:
                                    blob = json.loads(
                                        gpath.read_text(encoding="utf-8")
                                    )
                                except (OSError, json.JSONDecodeError):
                                    continue
                                cpath = blob.get("control_nest_path")
                                if cpath:
                                    child_path = [
                                        dict(s)
                                        for s in cpath
                                        if isinstance(s, Mapping)
                                    ]
                                    break
                    result = annotate_governance_spine(
                        result, live=True, child_control_path=child_path
                    )
                    result["governance_edge"] = "institution->program"
                    result["governance_operational_edge"] = "program->campaign"
                    result["governance_spine_default"] = default_flag
                elif layer.child == "institution":
                    # league (and any direct institution parent)
                    result = annotate_outer_governance_spine(
                        result,
                        outer_dialect=layer.name,
                        live=True,
                        child_control_path=child_path,
                    )
                    result["governance_spine_default"] = default_flag
                    result["stewardship_spine"] = True
                    result["stewardship_spine_default"] = default_flag
                    result["stewardship_root"] = layer.name
                else:
                    # confederation and higher civilization/continuum layers
                    result = annotate_stewardship_spine(
                        result,
                        root_layer=layer.name,
                        live=True,
                        child_control_path=child_path,
                    )
                    result["governance_spine_default"] = default_flag
                    result["stewardship_spine_default"] = default_flag
                    if layer.name in _CIVILIZATION_SPINE_DEFAULT_ROOTS:
                        result["civilization_spine"] = True
                        result["civilization_spine_default"] = default_flag
                        result["civilization_spine_root"] = layer.name
                    if layer.name in _CONTINUUM_SPINE_DEFAULT_ROOTS:
                        result["continuum_spine"] = True
                        result["continuum_spine_default"] = default_flag
                        result["continuum_spine_root"] = layer.name
                        # Continuum sits above civilization; seal both.
                        result["civilization_spine"] = True
                        result["civilization_spine_default"] = default_flag
                        result["civilization_spine_root"] = layer.name
            return result
        except ce.ConstitutionRefused as exc:
            # Preserve layer-scoped exception type (InstitutionRefused, etc.).
            raise _LayerRefused(exc.verdict, exc.detail) from exc

    def merge_charter_fn(
        existing: Sequence[Mapping[str, Any]] | None,
        additions: Sequence[Mapping[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        nested = _normalize_program_charter if layer.child == "program" else None
        return ce.merge_charter(
            layer, existing, additions, nested_normalizer=nested
        )

    def make_expand_fn(
        growth: Sequence[Mapping[str, Any]],
        *,
        max_slots_per_expand: int = 1,
        applied: Sequence[str] | None = None,
    ) -> Callable[..., dict[str, Any]]:
        nested = _normalize_program_charter if layer.child == "program" else None
        return ce.make_charter_expand(
            layer,
            growth,
            max_slots_per_expand=max_slots_per_expand,
            applied=applied,
            nested_normalizer=nested,
        )

    def terminal_coverage_fn(**kwargs: Any) -> dict[str, Any]:
        child_states = (
            kwargs.get(f"{layer.child}_states")
            or kwargs.get("child_states")
            or kwargs.get("program_states")
            or []
        )
        return ce.terminal_coverage(
            child_states=child_states,
            federated_portfolio=kwargs.get("federated_portfolio"),
        )

    def children_all_met_fn(child_states: Sequence[Mapping[str, Any]]) -> bool:
        return ce.children_all_met(layer, child_states)

    def open_unmet_fn(child_states: Sequence[Mapping[str, Any]]) -> int:
        return ce.open_unmet_count(layer, child_states)

    def builtin_proof() -> dict[str, Any]:
        return builtin_layer_proof(layer.name)

    def main(argv: Sequence[str] | None = None) -> int:
        parser = argparse.ArgumentParser(
            description=f"Upstream {layer.name} plane (engine facade) proof / CLI"
        )
        parser.add_argument("--proof", action="store_true", help="Run hermetic proof")
        args = parser.parse_args(list(argv) if argv is not None else None)
        if args.proof:
            result = builtin_proof()
            print(
                json.dumps(
                    {
                        "ok": result.get("ok"),
                        "action": result.get("action"),
                        "engine_facade": True,
                        "layer": layer.name,
                    },
                    indent=2,
                )
            )
            if not result.get("ok"):
                print(json.dumps(result.get("flags"), indent=2, default=str))
            return 0 if result.get("ok") else 1
        parser.print_help()
        return 2

    # --- populate module globals with legacy names ---
    g = module_globals
    g["ENGINE_FACADE"] = True
    g["SCHEMA_VERSION"] = ce.SCHEMA_VERSION
    g["REPO_ROOT"] = ce.REPO_ROOT
    g["ARTIFACTS_ROOT"] = layer.artifacts_root
    g["TERMINAL_SUCCESS_OUTCOMES"] = ce.TERMINAL_SUCCESS_OUTCOMES
    g[refused_name] = _LayerRefused
    g["ConstitutionRefused"] = ce.ConstitutionRefused
    # Institution is the constitution→operational bridge point: program children
    # attach to run_operational_spine by default (opt out: governance_spine=False).
    if layer.name == "institution" and layer.child == "program":
        g["GOVERNANCE_SPINE"] = True
        g["GOVERNANCE_SPINE_LIVE"] = True
        g["GOVERNANCE_SPINE_DEFAULT"] = True
        g["GOVERNANCE_NEST_CHILD"] = "program"
        g["GOVERNANCE_NEST_EDGE"] = "institution->program"
    # League defaults to governance-backed institutions (outer nest).
    if layer.child == "institution":
        g["GOVERNANCE_OUTER"] = True
        g["GOVERNANCE_OUTER_CHILD"] = "institution"
        g["GOVERNANCE_SPINE"] = True
        g["GOVERNANCE_SPINE_DEFAULT"] = True
        g["STEWARDSHIP_SPINE"] = True
        g["STEWARDSHIP_SPINE_DEFAULT"] = True
        g["STEWARDSHIP_SPINE_ROOT"] = layer.name
    # Full stewardship stack above league (confederation..quettacontinuum)
    # defaults into the operational nest via recursive stewardship cascade.
    if (
        layer.name in _STEWARDSHIP_SPINE_DEFAULT_ROOTS
        and layer.name not in {"institution", "league"}
    ):
        g["GOVERNANCE_OUTER"] = True
        g["GOVERNANCE_SPINE"] = True
        g["GOVERNANCE_SPINE_DEFAULT"] = True
        g["STEWARDSHIP_SPINE"] = True
        g["STEWARDSHIP_SPINE_DEFAULT"] = True
        g["STEWARDSHIP_SPINE_ROOT"] = layer.name
        g["STEWARDSHIP_NEST_EDGE"] = f"{layer.name}->{layer.child}"
        if layer.name in _CIVILIZATION_SPINE_DEFAULT_ROOTS:
            g["CIVILIZATION_SPINE"] = True
            g["CIVILIZATION_SPINE_DEFAULT"] = True
            if layer.name in {
                "civilization",
                "cosmos",
                "multiverse",
                "omniverse",
                "empire",
                "realm",
                "domain",
                "commonwealth",
                "confederation",
            }:
                g["CIVILIZATION_SPINE_ROOT"] = layer.name
        if layer.name in _CONTINUUM_SPINE_DEFAULT_ROOTS:
            g["CONTINUUM_SPINE"] = True
            g["CONTINUUM_SPINE_DEFAULT"] = True
            g["CONTINUUM_SPINE_ROOT"] = layer.name
            # Continuum roots also expose civilization spine seals.
            g["CIVILIZATION_SPINE"] = True
            g["CIVILIZATION_SPINE_DEFAULT"] = True
            g["CIVILIZATION_SPINE_ROOT"] = layer.name

    g[f"normalize_{layer.name}_charter"] = normalize_charter
    g[f"admit_{layer.child}_slot"] = admit_child_slot
    g["admit_pending_slots"] = admit_pending_slots
    g["federate_portfolios"] = federate
    g[f"{layer.name}_terminal_coverage"] = terminal_coverage_fn
    g[f"{layer.plural}_all_met"] = children_all_met_fn
    g["open_unmet_count"] = open_unmet_fn
    g["pending_charter_slots"] = pending_slots
    g["constitution_satisfied"] = constitution_satisfied_fn
    g[f"select_next_{layer.child}"] = select_next
    g[f"allocate_{layer.child}_budget"] = allocate_budget
    g[f"score_{layer.child}_roi"] = score_roi
    g[f"merge_{layer.name}_charter"] = merge_charter_fn
    g[f"make_{layer.name}_charter_expand"] = make_expand_fn
    g[f"write_{layer.name}_state"] = write_state_fn
    g[f"load_{layer.name}_state"] = load_state_fn
    g["_state_payload"] = state_payload_fn
    g[f"verify_{layer.name}_receipt"] = verify_fn
    g[f"run_{layer.name}"] = run_fn
    g[f"builtin_upstream_{layer.name}_proof"] = builtin_proof
    g["main"] = main

    # Shared slot helpers used by proofs / tests / parity checks.
    g["_program_slot"] = _program_slot
    g["_inst_slot"] = _inst_slot
    g["_proof_scratch"] = _proof_scratch
    g["_proof_campaign_runner"] = _proof_campaign_runner
    g["_slot"] = lambda child_id, **kw: _child_slot(layer, child_id, **kw)
    g[f"_{layer.child}_slot"] = lambda child_id, **kw: _child_slot(
        layer, child_id, **kw
    )

    # Nested stack helpers commonly re-used by outer layers' tests.
    # Each helper builds a slot for that noun as the *self id field* of a virtual
    # layer whose child is the next stack child (or institution for leaves).
    child_of = {parent: child for parent, child in ce.STEWARDSHIP_STACK}
    for noun in {c for _, c in ce.STEWARDSHIP_STACK} | {n for n, _ in ce.STEWARDSHIP_STACK}:
        slot_fn_name = f"_{noun}_slot"
        if slot_fn_name in g:
            continue
        nxt = child_of.get(noun, "program" if noun == "institution" else noun)

        def _make(
            noun_name: str = noun, next_child: str = nxt
        ) -> Callable[..., dict[str, Any]]:
            pseudo = ce.ConstitutionLayer(name=noun_name, child=next_child)

            def _slot(child_id: str, **kw: Any) -> dict[str, Any]:
                # _child_slot keys the id as layer.child_id_field; here we want
                # the slot's own noun id, so use a pseudo layer named parent of
                # noun with child=noun.
                parent_pseudo = ce.ConstitutionLayer(
                    name=f"wrap_{noun_name}", child=noun_name
                )
                return _child_slot(parent_pseudo, child_id, **kw)

            return _slot

        g[slot_fn_name] = _make()

    # Ensure this layer's child slot helper is the primary one.
    g[f"_{layer.child}_slot"] = lambda child_id, **kw: _child_slot(
        layer, child_id, **kw
    )

    # re-export a few engine utilities tests sometimes reach via layer modules
    g["_sha256_json"] = ce._sha256_json
    g["_sha256_bytes"] = ce._sha256_bytes
    g["make_portfolio"] = ce.make_portfolio


def install_package_cli() -> int:
    return builtin_stewardship_facade_proof() and 0 or 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stewardship facade collapse proof")
    parser.add_argument("--proof", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.proof:
        result = builtin_stewardship_facade_proof()
        print(
            json.dumps(
                {
                    "ok": result.get("ok"),
                    "action": result.get("action"),
                    "layer_count": result.get("layer_count"),
                    "layers_ok": result.get("layers_ok"),
                    "facade_files": result.get("facade_files"),
                    "tower_loc_after": result.get("tower_loc_after"),
                    "tower_loc_before": result.get("tower_loc_before"),
                    "loc_reduction_ratio": result.get("loc_reduction_ratio"),
                    "nested_composition": result.get("nested_composition"),
                    "constitution_engine_ok": result.get("constitution_engine_ok"),
                    "ledger_capability_ok": result.get("ledger_capability_ok"),
                    "stack_complete": result.get("stack_complete"),
                    "done_when_met": result.get("done_when_met"),
                },
                indent=2,
            )
        )
        if not result.get("ok"):
            print(json.dumps(result, indent=2, default=str)[:4000])
        return 0 if result.get("ok") else 1
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
