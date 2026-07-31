"""Generic data-driven plane engine.

One name-parameterized implementation of the layer-transition semantics that
``capability_compounder.py`` historically copy-pastes once per plane
(``run_realm_plane``, ``run_cosmos_plane``, ... ~58 near-identical ~2300-line
functions produced by token-rename generator scripts under ``artifacts/``).

A plane layer transitions a parent bundle into a deterministic hash-chained
child log: derive one spec per parent grant, append one chained entry per spec,
issue a certificate per entry, package the tip into a portable bundle, and
reject mutation, reorder, wrong-parent binding, duplicate grants, forged roots,
height gaps, broken certificates, and digest tamper.

Every field name the legacy code hard-codes per layer is derived here from the
layer's declared nouns, so one engine covers any configured layer. The engine
is digest-equivalent to the legacy per-layer functions: given the same parent
bundle and specs it produces identical roots, plan digests, certificates, and
bundle hashes (modulo wall-clock fields). ``differential_proof`` demonstrates
that equivalence against the legacy realm implementation and is the registered
proof for ``capability.plane-engine``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)

SCHEMA_VERSION = 1

# Wall-clock fields excluded from deterministic equivalence comparisons.
VOLATILE_FIELDS = frozenset({"applied_at", "updated_at", "issued_at", "exported_at"})


@dataclass(frozen=True)
class PlaneLayer:
    """Nouns that parameterize one plane layer transition."""

    name: str  # self noun, e.g. "realm"
    parent: str  # parent noun, e.g. "dominion"
    plural: str  # self plural, log key inside the bundle, e.g. "realms"
    parent_plural: str  # parent plural key inside the parent bundle
    outcome: str  # past-tense outcome verb, e.g. "realmed"
    bundle_relative: Path  # default bundle directory relative to repo root


# Layers are registered only after the differential proof covers them.
LAYERS: dict[str, PlaneLayer] = {
    "realm": PlaneLayer(
        name="realm",
        parent="dominion",
        plural="realms",
        parent_plural="dominions",
        outcome="realmed",
        bundle_relative=Path("artifacts") / "realm-bundles",
    ),
}


def get_layer(name: str) -> PlaneLayer:
    layer = LAYERS.get(str(name).strip().lower())
    if layer is None:
        raise KeyError(
            f"plane layer {name!r} is not registered; "
            f"registered: {sorted(LAYERS)}"
        )
    return layer


def _sha24(payload: Mapping[str, Any]) -> str:
    digest = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(digest.encode("utf-8")).hexdigest()[:24]


def _skill_route_used() -> bool:
    return legacy_pipeline_was_used()


# ---------------------------------------------------------------------------
# Log / root / digest primitives
# ---------------------------------------------------------------------------


def empty_log(layer: PlaneLayer) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": f"{layer.name}_log",
        "entries": [],
        "entry_count": 0,
        "tip_height": 0,
        f"tip_{layer.name}_root": "",
        f"bound_{layer.parent}_root": "",
        f"bound_{layer.parent}_height": 0,
        f"{layer.parent}_hash": "",
        f"{layer.name}_plan_digest": "",
        "updated_at": utc_now_iso(),
    }


def compute_root(layer: PlaneLayer, entry: Mapping[str, Any]) -> str:
    """Hash an entry excluding its own root, certificate, and volatile fields."""

    excluded = {
        f"{layer.name}_root",
        f"{layer.name}_certificate",
        "ok",
        "valid",
        "action",
        "goal",
        "claims",
        *VOLATILE_FIELDS,
    }
    body = {key: value for key, value in entry.items() if key not in excluded}
    return _sha24(body)


def compute_certificate_hash(payload: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in payload.items()
        if key not in {"certificate_hash", "ok", "valid"}
    }
    return _sha24(body)


def compute_bundle_hash(layer: PlaneLayer, bundle: Mapping[str, Any]) -> str:
    excluded = {
        f"{layer.name}_hash",
        "ok",
        "bundle_path",
        "source_ledger_path",
        "action",
        "exported_at",
    }
    body = {key: value for key, value in bundle.items() if key not in excluded}
    return _sha24(body)


def compute_plan_digest(
    layer: PlaneLayer,
    *,
    parent_digest: str,
    bound_parent_root: str,
    parent_plan_digest: str,
    capability_id: str,
    outcome: str = "",
    position_ratio_bps: int = 1000,
) -> str:
    """Chain the prior child digest with one newly transitioned scenario."""

    payload = {
        f"parent_{layer.name}_digest": parent_digest or "",
        f"bound_{layer.parent}_root": bound_parent_root,
        f"{layer.parent}_plan_digest": parent_plan_digest,
        "capability_id": capability_id,
        "outcome": outcome or layer.outcome,
        "position_ratio_bps": int(position_ratio_bps),
        "plane": layer.name,
    }
    return _sha24(payload)


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------


def issue_certificate(
    layer: PlaneLayer,
    *,
    height: int,
    root: str,
    parent_root: str,
    bound_parent_root: str,
    bound_parent_height: int,
    parent_hash: str,
    parent_certificate_hash: str,
    package_hash: str,
    lineage_head_hash: str,
    parent_plan_digest: str,
    plan_digest: str,
    count: int,
    member_ids: Sequence[str] | None = None,
    goal: str = "",
    claims: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    members = sorted({str(item).strip() for item in (member_ids or []) if str(item).strip()})
    cert: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": f"{layer.name}_certificate",
        "issued_at": utc_now_iso(),
        f"{layer.name}_height": int(height),
        f"{layer.name}_root": str(root or ""),
        f"parent_{layer.name}_root": str(parent_root or ""),
        f"bound_{layer.parent}_root": str(bound_parent_root or ""),
        f"bound_{layer.parent}_height": int(bound_parent_height or 0),
        f"{layer.parent}_hash": str(parent_hash or ""),
        f"{layer.parent}_certificate_hash": str(parent_certificate_hash or ""),
        "package_hash": str(package_hash or ""),
        "lineage_head_hash": str(lineage_head_hash or ""),
        f"{layer.parent}_plan_digest": str(parent_plan_digest or ""),
        f"{layer.name}_plan_digest": str(plan_digest or ""),
        f"{layer.name}_count": int(count),
        "member_ids": members,
        "member_count": len(members),
        "goal": goal or "",
        "claims": dict(claims or {}),
        "deterministic": True,
        f"post_{layer.parent}": True,
        "used_skill_route_discovery": _skill_route_used(),
    }
    cert["certificate_hash"] = compute_certificate_hash(cert)
    cert["ok"] = (
        bool(cert["certificate_hash"])
        and bool(cert[f"{layer.name}_root"])
        and bool(cert[f"bound_{layer.parent}_root"])
        and bool(cert[f"{layer.parent}_hash"])
        and bool(cert[f"{layer.name}_plan_digest"])
        and bool(cert[f"{layer.parent}_plan_digest"])
        and cert[f"{layer.name}_height"] >= 1
        and cert[f"{layer.name}_count"] >= 1
        and cert["deterministic"] is True
        and cert[f"post_{layer.parent}"] is True
        and not bool(cert["used_skill_route_discovery"])
    )
    cert["valid"] = bool(cert["ok"])
    return cert


def verify_certificate(
    layer: PlaneLayer, payload: Mapping[str, Any] | Path
) -> dict[str, Any]:
    if isinstance(payload, Path):
        data = json.loads(payload.read_text(encoding="utf-8"))
    else:
        data = dict(payload)
    recomputed = compute_certificate_hash(data)
    stored = str(data.get("certificate_hash") or "")
    hash_ok = bool(stored) and stored == recomputed
    valid = (
        hash_ok
        and data.get("kind") == f"{layer.name}_certificate"
        and bool(data.get(f"{layer.name}_root"))
        and bool(data.get(f"bound_{layer.parent}_root"))
        and bool(data.get(f"{layer.parent}_hash"))
        and bool(data.get(f"{layer.name}_plan_digest"))
        and bool(data.get(f"{layer.parent}_plan_digest"))
        and int(data.get(f"{layer.name}_height") or 0) >= 1
        and int(data.get(f"{layer.name}_count") or 0) >= 1
        and data.get("deterministic") is True
        and data.get(f"post_{layer.parent}") is True
        and not bool(data.get("used_skill_route_discovery"))
    )
    return {
        "ok": valid,
        "valid": valid,
        "hash_ok": hash_ok,
        "certificate_hash": stored if hash_ok else recomputed,
        f"{layer.name}_height": data.get(f"{layer.name}_height"),
        f"{layer.name}_root": data.get(f"{layer.name}_root"),
        f"bound_{layer.parent}_root": data.get(f"bound_{layer.parent}_root"),
        f"{layer.name}_plan_digest": data.get(f"{layer.name}_plan_digest"),
        f"{layer.parent}_hash": data.get(f"{layer.parent}_hash"),
        "used_skill_route_discovery": bool(data.get("used_skill_route_discovery")),
    }


def write_certificate(path: Path, certificate: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, dict(certificate))
    return path


# ---------------------------------------------------------------------------
# Spec derivation and transitions
# ---------------------------------------------------------------------------


def derive_specs(
    layer: PlaneLayer,
    parent_bundle: Mapping[str, Any],
    *,
    min_count: int = 2,
) -> list[dict[str, Any]]:
    """Derive one child spec per parent grant (multi-grant required)."""

    parent_log = (
        parent_bundle.get(layer.parent_plural)
        if isinstance(parent_bundle.get(layer.parent_plural), Mapping)
        else {}
    )
    entries = list(parent_log.get("entries") or [])
    specs: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        parent_root = str(entry.get(f"{layer.parent}_root") or "")
        if not parent_root:
            continue
        specs.append(
            {
                "capability_id": str(entry.get("capability_id") or ""),
                "effect": str(entry.get("effect") or ""),
                f"bound_{layer.parent}_root": parent_root,
                f"bound_{layer.parent}_height": int(
                    entry.get(f"{layer.parent}_height") or 0
                ),
                f"{layer.parent}_plan_digest": str(
                    entry.get(f"{layer.parent}_plan_digest") or ""
                ),
                "receipt_digest": str(entry.get("receipt_digest") or ""),
                "bound_settlement_root": str(entry.get("bound_settlement_root") or ""),
                "bound_action_root": str(entry.get("bound_action_root") or ""),
                "package_hash": str(
                    entry.get("package_hash")
                    or parent_bundle.get("package_hash")
                    or ""
                ),
                "outcome": layer.outcome,
                "position_ratio_bps": 1000 + 100 * len(specs),
            }
        )
    want = max(2, int(min_count))
    return specs[:want] if len(specs) >= want else specs


def apply_transition(
    layer: PlaneLayer,
    log: Mapping[str, Any],
    spec: Mapping[str, Any],
    *,
    parent_bundle: Mapping[str, Any],
    goal: str = "",
    claims: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one child entry bound to a known parent grant root."""

    new_log = copy.deepcopy(dict(log)) if log else empty_log(layer)
    entries = list(new_log.get("entries") or [])
    next_height = len(entries) + 1
    parent_root = (
        str(entries[-1].get(f"{layer.name}_root") or "") if entries else ""
    )
    parent_digest = (
        str(entries[-1].get(f"{layer.name}_plan_digest") or "") if entries else ""
    )

    bound_root = str(spec.get(f"bound_{layer.parent}_root") or "")
    bound_height = int(spec.get(f"bound_{layer.parent}_height") or 0)
    capability_id = str(spec.get("capability_id") or "")
    effect = str(spec.get("effect") or "")
    outcome = str(spec.get("outcome") or layer.outcome)
    package_hash = str(
        spec.get("package_hash") or parent_bundle.get("package_hash") or ""
    )
    parent_hash = str(parent_bundle.get(f"{layer.parent}_hash") or "")
    tip_parent_root = str(parent_bundle.get(f"tip_{layer.parent}_root") or "")
    parent_log = (
        parent_bundle.get(layer.parent_plural)
        if isinstance(parent_bundle.get(layer.parent_plural), Mapping)
        else {}
    )
    parent_entries = list(parent_log.get("entries") or [])
    known_roots = {
        str(item.get(f"{layer.parent}_root") or "")
        for item in parent_entries
        if isinstance(item, Mapping) and item.get(f"{layer.parent}_root")
    }
    if tip_parent_root:
        known_roots.add(tip_parent_root)

    if not capability_id or not bound_root or not parent_hash:
        return {
            "ok": False,
            "action": "apply_transition",
            "error": f"missing_{layer.parent}_bind_fields",
            "log": new_log,
            "used_skill_route_discovery": _skill_route_used(),
        }
    if bound_root not in known_roots:
        return {
            "ok": False,
            "action": "apply_transition",
            "error": f"bound_{layer.parent}_root_mismatch",
            f"bound_{layer.parent}_root": bound_root,
            f"known_{layer.parent}_roots": sorted(known_roots),
            "log": new_log,
            "used_skill_route_discovery": _skill_route_used(),
        }
    if any(
        str(item.get(f"bound_{layer.parent}_root") or "") == bound_root
        and str(item.get("outcome") or "") == outcome
        for item in entries
    ):
        return {
            "ok": False,
            "action": "apply_transition",
            "error": f"duplicate_{layer.parent}_rejected",
            "log": new_log,
            "used_skill_route_discovery": _skill_route_used(),
        }

    parent_cert = (
        parent_bundle.get(f"{layer.parent}_certificate")
        if isinstance(parent_bundle.get(f"{layer.parent}_certificate"), Mapping)
        else {}
    )
    parent_cert_hash = str(parent_cert.get("certificate_hash") or "")
    lineage_head = str(parent_bundle.get("lineage_head_hash") or "")
    member_ids = list(parent_bundle.get("member_ids") or [])
    parent_plan_digest = str(spec.get(f"{layer.parent}_plan_digest") or "")
    position_ratio_bps = int(spec.get("position_ratio_bps") or 1000)
    if not parent_plan_digest:
        for item in parent_entries:
            if (
                isinstance(item, Mapping)
                and str(item.get(f"{layer.parent}_root") or "") == bound_root
            ):
                parent_plan_digest = str(
                    item.get(f"{layer.parent}_plan_digest") or ""
                )
                break
    plan_digest = compute_plan_digest(
        layer,
        parent_digest=parent_digest,
        bound_parent_root=bound_root,
        parent_plan_digest=parent_plan_digest,
        position_ratio_bps=position_ratio_bps,
        capability_id=capability_id,
        outcome=outcome,
    )

    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": f"{layer.name}_action",
        f"{layer.name}_height": next_height,
        f"parent_{layer.name}_root": parent_root,
        f"bound_{layer.parent}_root": bound_root,
        f"bound_{layer.parent}_height": bound_height,
        f"{layer.parent}_hash": parent_hash,
        f"{layer.parent}_certificate_hash": parent_cert_hash,
        "package_hash": package_hash,
        "lineage_head_hash": lineage_head,
        "capability_id": capability_id,
        "effect": effect,
        "outcome": outcome,
        f"{layer.parent}_plan_digest": parent_plan_digest,
        f"{layer.name}_plan_digest": plan_digest,
        "position_ratio_bps": position_ratio_bps,
        f"parent_{layer.name}_digest": parent_digest,
        "bound_action_root": str(spec.get("bound_action_root") or ""),
        "member_ids": sorted({str(m).strip() for m in member_ids if str(m).strip()}),
        "deterministic": True,
        f"post_{layer.parent}": True,
        "applied_at": utc_now_iso(),
        "goal": goal or str(parent_bundle.get("goal") or ""),
        "claims": dict(claims or {}),
        "used_skill_route_discovery": _skill_route_used(),
    }
    root = compute_root(layer, body)
    body[f"{layer.name}_root"] = root
    cert = issue_certificate(
        layer,
        height=next_height,
        root=root,
        parent_root=parent_root,
        bound_parent_root=bound_root,
        bound_parent_height=bound_height,
        parent_hash=parent_hash,
        parent_certificate_hash=parent_cert_hash,
        package_hash=package_hash,
        lineage_head_hash=lineage_head,
        parent_plan_digest=parent_plan_digest,
        plan_digest=plan_digest,
        count=next_height,
        member_ids=body["member_ids"],
        goal=goal or str(parent_bundle.get("goal") or ""),
        claims={
            "capability_id": capability_id,
            "effect": effect,
            "outcome": outcome,
            "plane": layer.name,
            **dict(claims or {}),
        },
    )
    body[f"{layer.name}_certificate"] = cert
    body["ok"] = (
        bool(cert.get("ok"))
        and bool(root)
        and bool(plan_digest)
        and body["deterministic"] is True
        and body[f"post_{layer.parent}"] is True
        and not bool(body.get("used_skill_route_discovery"))
    )

    entries.append(body)
    new_log["entries"] = entries
    new_log["entry_count"] = len(entries)
    new_log["tip_height"] = next_height
    new_log[f"tip_{layer.name}_root"] = root
    new_log[f"bound_{layer.parent}_root"] = bound_root
    new_log[f"bound_{layer.parent}_height"] = bound_height
    new_log[f"{layer.parent}_hash"] = parent_hash
    new_log[f"{layer.name}_plan_digest"] = plan_digest
    new_log["updated_at"] = utc_now_iso()
    new_log["schema_version"] = SCHEMA_VERSION
    new_log["kind"] = f"{layer.name}_log"
    return {
        "ok": bool(body.get("ok")),
        "action": "apply_transition",
        "entry": body,
        f"{layer.name}_height": next_height,
        f"{layer.name}_root": root,
        f"parent_{layer.name}_root": parent_root,
        f"bound_{layer.parent}_root": bound_root,
        f"{layer.name}_plan_digest": plan_digest,
        "log": new_log,
        "used_skill_route_discovery": _skill_route_used(),
    }


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------


def verify_chain(layer: PlaneLayer, log: Mapping[str, Any]) -> dict[str, Any]:
    """Validate heights, parent roots, digests, hashes, and certificates."""

    entries = list(log.get("entries") or [])
    errors: list[str] = []
    if not entries:
        return {
            "ok": False,
            "valid": False,
            "action": "verify_chain",
            "entry_count": 0,
            "tip_height": 0,
            f"tip_{layer.name}_root": "",
            "errors": [f"empty_{layer.name}_log"],
            "used_skill_route_discovery": _skill_route_used(),
        }

    prev_root = ""
    prev_digest = ""
    bound_roots: set[str] = set()
    parent_hashes: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, Mapping):
            errors.append(f"entry[{index}]_not_mapping")
            continue
        height = int(raw.get(f"{layer.name}_height") or 0)
        expected_height = index + 1
        if height != expected_height:
            errors.append(f"entry[{index}]_height={height}_expected={expected_height}")
        parent = str(raw.get(f"parent_{layer.name}_root") or "")
        if index == 0:
            if parent:
                errors.append(f"entry[{index}]_genesis_has_parent")
        elif parent != prev_root:
            errors.append(
                f"entry[{index}]_parent_mismatch"
                f" got={parent[:12]} expected={prev_root[:12]}"
            )
        stored = str(raw.get(f"{layer.name}_root") or "")
        recomputed = compute_root(layer, {**dict(raw), f"{layer.name}_root": ""})
        if not stored or stored != recomputed:
            errors.append(f"entry[{index}]_{layer.name}_root_mismatch")
        if raw.get("deterministic") is not True:
            errors.append(f"entry[{index}]_not_deterministic")
        if raw.get(f"post_{layer.parent}") is not True:
            errors.append(f"entry[{index}]_not_post_{layer.parent}")
        bound = str(raw.get(f"bound_{layer.parent}_root") or "")
        if not bound:
            errors.append(f"entry[{index}]_missing_bound_{layer.parent}_root")
        else:
            bound_roots.add(bound)
        p_hash = str(raw.get(f"{layer.parent}_hash") or "")
        if not p_hash:
            errors.append(f"entry[{index}]_missing_{layer.parent}_hash")
        else:
            parent_hashes.add(p_hash)
        parent_plan_digest = str(raw.get(f"{layer.parent}_plan_digest") or "")
        stored_parent_digest = str(raw.get(f"parent_{layer.name}_digest") or "")
        if stored_parent_digest != prev_digest:
            errors.append(f"entry[{index}]_parent_{layer.name}_digest_mismatch")
        expected_digest = compute_plan_digest(
            layer,
            parent_digest=prev_digest,
            bound_parent_root=bound,
            parent_plan_digest=parent_plan_digest,
            position_ratio_bps=int(raw.get("position_ratio_bps") or 1000),
            capability_id=str(raw.get("capability_id") or ""),
            outcome=str(raw.get("outcome") or layer.outcome),
        )
        stored_digest = str(raw.get(f"{layer.name}_plan_digest") or "")
        if not stored_digest or stored_digest != expected_digest:
            errors.append(f"entry[{index}]_{layer.name}_plan_digest_mismatch")
        cert = raw.get(f"{layer.name}_certificate")
        if not isinstance(cert, Mapping):
            errors.append(f"entry[{index}]_missing_{layer.name}_certificate")
        else:
            cert_verify = verify_certificate(layer, cert)
            if not cert_verify.get("valid"):
                errors.append(f"entry[{index}]_cert_invalid")
            if str(cert.get(f"{layer.name}_root") or "") != stored:
                errors.append(f"entry[{index}]_cert_{layer.name}_root_mismatch")
            if int(cert.get(f"{layer.name}_height") or 0) != height:
                errors.append(f"entry[{index}]_cert_height_mismatch")
            if str(cert.get(f"bound_{layer.parent}_root") or "") != bound:
                errors.append(f"entry[{index}]_cert_bound_{layer.parent}_mismatch")
            if str(cert.get(f"{layer.name}_plan_digest") or "") != stored_digest:
                errors.append(f"entry[{index}]_cert_digest_mismatch")
        prev_root = stored
        prev_digest = stored_digest

    if len(parent_hashes) > 1:
        errors.append(f"mixed_{layer.parent}_hashes")

    tip = entries[-1] if entries else {}
    tip_height = int(tip.get(f"{layer.name}_height") or 0) if isinstance(tip, Mapping) else 0
    tip_root = str(tip.get(f"{layer.name}_root") or "") if isinstance(tip, Mapping) else ""
    tip_digest = (
        str(tip.get(f"{layer.name}_plan_digest") or "") if isinstance(tip, Mapping) else ""
    )
    log_tip_height = int(log.get("tip_height") or 0)
    log_tip_root = str(log.get(f"tip_{layer.name}_root") or "")
    log_digest = str(log.get(f"{layer.name}_plan_digest") or "")
    if log_tip_height and log_tip_height != tip_height:
        errors.append("tip_height_metadata_mismatch")
    if log_tip_root and log_tip_root != tip_root:
        errors.append(f"tip_{layer.name}_root_metadata_mismatch")
    if log_digest and log_digest != tip_digest:
        errors.append(f"{layer.name}_plan_digest_metadata_mismatch")

    valid = not errors and tip_height >= 1 and bool(tip_root) and bool(tip_digest)
    return {
        "ok": valid,
        "valid": valid,
        "action": "verify_chain",
        "entry_count": len(entries),
        "tip_height": tip_height,
        f"tip_{layer.name}_root": tip_root,
        f"{layer.name}_plan_digest": tip_digest,
        f"bound_{layer.parent}_roots": sorted(bound_roots),
        f"{layer.parent}_hash": next(iter(parent_hashes), ""),
        "errors": errors,
        "used_skill_route_discovery": _skill_route_used(),
    }


# ---------------------------------------------------------------------------
# Bundle application, build, and integrity
# ---------------------------------------------------------------------------


def apply_bundle(
    layer: PlaneLayer,
    parent_bundle: Mapping[str, Any],
    *,
    goal: str = "",
    min_count: int = 2,
    parent_integrity_verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Post multi-grant scenarios into a deterministic child plan log."""

    if parent_integrity_verifier is not None:
        integrity = parent_integrity_verifier(parent_bundle)
        if not integrity.get("ok"):
            return {
                "ok": False,
                "action": "apply_bundle",
                "error": f"{layer.parent}_integrity_failed",
                "integrity": dict(integrity),
                "used_skill_route_discovery": _skill_route_used(),
            }
    specs = derive_specs(layer, parent_bundle, min_count=min_count)
    if len(specs) < 2:
        return {
            "ok": False,
            "action": "apply_bundle",
            "error": f"need_multi_{layer.name}",
            "spec_count": len(specs),
            "used_skill_route_discovery": _skill_route_used(),
        }

    log = empty_log(layer)
    applied: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        result = apply_transition(
            layer,
            log,
            spec,
            parent_bundle=parent_bundle,
            goal=f"{goal or parent_bundle.get('goal') or 'clearing'} (clearing {index + 1})",
            claims={"clearing_index": index + 1, "plane": layer.name},
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "action": "apply_bundle",
                "error": result.get("error") or "apply_failed",
                "applied_count": len(applied),
                "apply": {
                    "ok": result.get("ok"),
                    "error": result.get("error"),
                    f"{layer.name}_height": result.get(f"{layer.name}_height"),
                },
                "log": log,
                "used_skill_route_discovery": _skill_route_used(),
            }
        log = result["log"]
        applied.append(result["entry"])

    chain = verify_chain(layer, log)
    ok = bool(chain.get("valid")) and len(applied) >= 2 and not _skill_route_used()
    return {
        "ok": ok,
        "action": "apply_bundle",
        "log": log,
        "applied": applied,
        "applied_count": len(applied),
        f"{layer.name}_count": len(applied),
        "tip_height": log.get("tip_height"),
        f"tip_{layer.name}_root": log.get(f"tip_{layer.name}_root"),
        f"bound_{layer.parent}_root": log.get(f"bound_{layer.parent}_root"),
        f"{layer.name}_plan_digest": log.get(f"{layer.name}_plan_digest"),
        "chain": chain,
        "used_skill_route_discovery": _skill_route_used(),
    }


def build_bundle(
    layer: PlaneLayer,
    log: Mapping[str, Any],
    parent_bundle: Mapping[str, Any],
    *,
    goal: str = "",
) -> dict[str, Any]:
    """Package the child log plus parent tip into a portable layer bundle."""

    chain = verify_chain(layer, log)
    if not chain.get("valid"):
        return {
            "ok": False,
            "action": "build_bundle",
            "error": f"{layer.parent}_chain_invalid",
            "chain": chain,
            "used_skill_route_discovery": _skill_route_used(),
        }
    entries = list(log.get("entries") or [])
    tip = entries[-1]
    tip_cert = (
        tip.get(f"{layer.name}_certificate")
        if isinstance(tip.get(f"{layer.name}_certificate"), Mapping)
        else {}
    )
    tip_cert_verify = (
        verify_certificate(layer, tip_cert) if tip_cert else {"valid": False}
    )
    parent_cert = (
        parent_bundle.get(f"{layer.parent}_certificate")
        if isinstance(parent_bundle.get(f"{layer.parent}_certificate"), Mapping)
        else {}
    )
    act_cert = (
        parent_bundle.get("actuation_certificate")
        if isinstance(parent_bundle.get("actuation_certificate"), Mapping)
        else {}
    )
    package = (
        parent_bundle.get("package")
        if isinstance(parent_bundle.get("package"), Mapping)
        else {}
    )
    certificates: dict[str, dict[str, Any]] = {}
    for entry in entries:
        cert = entry.get(f"{layer.name}_certificate")
        if isinstance(cert, Mapping) and cert.get("certificate_hash"):
            certificates[str(cert["certificate_hash"])] = {
                "certificate_hash": cert.get("certificate_hash"),
                "payload": cert,
                f"{layer.name}_height": entry.get(f"{layer.name}_height"),
            }
    if isinstance(parent_cert, Mapping) and parent_cert.get("certificate_hash"):
        certificates[str(parent_cert["certificate_hash"])] = {
            "certificate_hash": parent_cert.get("certificate_hash"),
            "payload": parent_cert,
            "kind": f"{layer.name}_certificate",
        }
    if isinstance(act_cert, Mapping) and act_cert.get("certificate_hash"):
        certificates[str(act_cert["certificate_hash"])] = {
            "certificate_hash": act_cert.get("certificate_hash"),
            "payload": act_cert,
            "kind": "actuation_certificate",
        }
    exec_cert = (
        parent_bundle.get("execution_certificate")
        if isinstance(parent_bundle.get("execution_certificate"), Mapping)
        else {}
    )
    if isinstance(exec_cert, Mapping) and exec_cert.get("certificate_hash"):
        certificates[str(exec_cert["certificate_hash"])] = {
            "certificate_hash": exec_cert.get("certificate_hash"),
            "payload": exec_cert,
            "kind": "execution_certificate",
        }
    settle_cert_nested = (
        parent_bundle.get("settlement_certificate")
        if isinstance(parent_bundle.get("settlement_certificate"), Mapping)
        else {}
    )
    if isinstance(settle_cert_nested, Mapping) and settle_cert_nested.get(
        "certificate_hash"
    ):
        certificates[str(settle_cert_nested["certificate_hash"])] = {
            "certificate_hash": settle_cert_nested.get("certificate_hash"),
            "payload": settle_cert_nested,
            "kind": "settlement_certificate",
        }

    member_ids = list(parent_bundle.get("member_ids") or package.get("member_ids") or [])
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": f"{layer.name}_bundle",
        "action": f"build_{layer.name}_bundle",
        "goal": goal or f"{layer.name} over {layer.parent}",
        layer.plural: copy.deepcopy(dict(log)),
        layer.parent_plural: copy.deepcopy(
            parent_bundle.get(layer.parent_plural)
            if isinstance(parent_bundle.get(layer.parent_plural), Mapping)
            else {}
        ),
        "settlements": copy.deepcopy(
            parent_bundle.get("settlements")
            if isinstance(parent_bundle.get("settlements"), Mapping)
            else {}
        ),
        "actions": copy.deepcopy(
            parent_bundle.get("actions")
            if isinstance(parent_bundle.get("actions"), Mapping)
            else {}
        ),
        "package": copy.deepcopy(dict(package)),
        "lineage": copy.deepcopy(
            parent_bundle.get("lineage")
            if isinstance(parent_bundle.get("lineage"), Mapping)
            else {}
        ),
        f"{layer.name}_certificate": copy.deepcopy(dict(tip_cert)),
        f"{layer.parent}_certificate": copy.deepcopy(dict(parent_cert)),
        "settlement_certificate": copy.deepcopy(dict(settle_cert_nested)),
        "actuation_certificate": copy.deepcopy(dict(act_cert)),
        "execution_certificate": copy.deepcopy(dict(exec_cert)),
        "certificates": certificates,
        "certificate_count": len(certificates),
        f"{layer.name}_count": len(entries),
        f"{layer.parent}_count": int(parent_bundle.get(f"{layer.parent}_count") or 0),
        "settlement_count": int(parent_bundle.get("settlement_count") or 0),
        "action_count": int(parent_bundle.get("action_count") or 0),
        "tip_height": int(log.get("tip_height") or 0),
        f"tip_{layer.name}_root": str(log.get(f"tip_{layer.name}_root") or ""),
        f"bound_{layer.parent}_root": str(log.get(f"bound_{layer.parent}_root") or ""),
        f"bound_{layer.parent}_height": int(
            log.get(f"bound_{layer.parent}_height") or 0
        ),
        f"tip_{layer.parent}_root": str(
            parent_bundle.get(f"tip_{layer.parent}_root") or ""
        ),
        "bound_settlement_root": str(parent_bundle.get("bound_settlement_root") or ""),
        "tip_settlement_root": str(parent_bundle.get("tip_settlement_root") or ""),
        "bound_action_root": str(parent_bundle.get("bound_action_root") or ""),
        "tip_action_root": str(parent_bundle.get("tip_action_root") or ""),
        "bound_state_root": str(parent_bundle.get("bound_state_root") or ""),
        f"{layer.name}_plan_digest": str(log.get(f"{layer.name}_plan_digest") or ""),
        f"{layer.parent}_plan_digest": str(
            parent_bundle.get(f"{layer.parent}_plan_digest") or ""
        ),
        f"{layer.parent}_hash": str(parent_bundle.get(f"{layer.parent}_hash") or ""),
        "settlement_hash": str(parent_bundle.get("settlement_hash") or ""),
        "actuation_hash": str(parent_bundle.get("actuation_hash") or ""),
        "execution_hash": str(parent_bundle.get("execution_hash") or ""),
        "package_hash": str(parent_bundle.get("package_hash") or ""),
        "member_ids": sorted({str(m).strip() for m in member_ids if str(m).strip()}),
        "member_count": len(member_ids),
        "lineage_head_hash": str(parent_bundle.get("lineage_head_hash") or ""),
        "lineage_entry_count": int(parent_bundle.get("lineage_entry_count") or 0),
        "origin_count": parent_bundle.get("origin_count"),
        "agreeing_count": parent_bundle.get("agreeing_count"),
        "byzantine_count": parent_bundle.get("byzantine_count"),
        "state_count": parent_bundle.get("state_count"),
        "epoch_count": parent_bundle.get("epoch_count"),
        "deterministic": True,
        f"post_{layer.parent}": True,
        "exported_at": utc_now_iso(),
        "used_skill_route_discovery": _skill_route_used(),
    }
    bundle[f"{layer.name}_hash"] = compute_bundle_hash(layer, bundle)
    bundle["ok"] = (
        bool(chain.get("valid"))
        and bool(tip_cert_verify.get("valid"))
        and len(entries) >= 2
        and bool(bundle[f"{layer.name}_hash"])
        and bool(bundle[f"{layer.parent}_hash"])
        and bool(bundle[f"{layer.name}_plan_digest"])
        and bundle["deterministic"] is True
        and bundle[f"post_{layer.parent}"] is True
        and not bool(bundle["used_skill_route_discovery"])
    )
    return bundle


def write_bundle(path: Path, bundle: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, dict(bundle))
    return path


def load_bundle(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("plane bundle must be a JSON object")
    return data


def verify_bundle_integrity(
    layer: PlaneLayer,
    bundle: Mapping[str, Any],
    *,
    parent_certificate_verifier: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> dict[str, Any]:
    expected = str(bundle.get(f"{layer.name}_hash") or "").strip()
    recomputed = compute_bundle_hash(layer, bundle)
    hash_ok = bool(expected) and expected == recomputed
    child_log = (
        bundle.get(layer.plural) if isinstance(bundle.get(layer.plural), Mapping) else {}
    )
    chain = (
        verify_chain(layer, child_log)
        if child_log
        else {"ok": False, "valid": False, "errors": [f"missing_{layer.plural}"]}
    )
    cert = (
        bundle.get(f"{layer.name}_certificate")
        if isinstance(bundle.get(f"{layer.name}_certificate"), Mapping)
        else {}
    )
    cert_verify = (
        verify_certificate(layer, cert) if cert else {"valid": False, "ok": False}
    )
    parent_cert = (
        bundle.get(f"{layer.parent}_certificate")
        if isinstance(bundle.get(f"{layer.parent}_certificate"), Mapping)
        else {}
    )
    parent_cert_verify = (
        parent_certificate_verifier(parent_cert)
        if parent_cert
        else {"valid": False, "ok": False}
    )
    multi = int(bundle.get(f"{layer.name}_count") or chain.get("entry_count") or 0) >= 2
    package = bundle.get("package") if isinstance(bundle.get("package"), Mapping) else {}
    package_ok = bool(package) and bool(bundle.get("package_hash"))
    bound_ok = bool(bundle.get(f"bound_{layer.parent}_root")) and bool(
        bundle.get(f"{layer.parent}_hash")
    )
    digest_ok = bool(bundle.get(f"{layer.name}_plan_digest")) and str(
        bundle.get(f"{layer.name}_plan_digest") or ""
    ) == str(
        chain.get(f"{layer.name}_plan_digest")
        or bundle.get(f"{layer.name}_plan_digest")
        or ""
    )
    deterministic = bundle.get("deterministic") is True
    post_parent = bundle.get(f"post_{layer.parent}") is True
    used_skill = bool(bundle.get("used_skill_route_discovery")) or _skill_route_used()
    ok = (
        hash_ok
        and bool(chain.get("valid"))
        and bool(cert_verify.get("valid"))
        and bool(parent_cert_verify.get("valid"))
        and multi
        and package_ok
        and bound_ok
        and digest_ok
        and deterministic
        and post_parent
        and not used_skill
    )
    return {
        "ok": ok,
        "valid": ok,
        "action": "verify_bundle_integrity",
        "hash_ok": hash_ok,
        "chain": chain,
        "certificate": cert_verify,
        f"{layer.parent}_certificate": dict(parent_cert_verify),
        "multi": multi,
        f"{layer.name}_count": int(
            bundle.get(f"{layer.name}_count") or chain.get("entry_count") or 0
        ),
        f"{layer.name}_hash": expected if hash_ok else recomputed,
        f"tip_{layer.name}_root": chain.get(f"tip_{layer.name}_root"),
        f"{layer.name}_plan_digest": bundle.get(f"{layer.name}_plan_digest"),
        "used_skill_route_discovery": used_skill,
    }


# ---------------------------------------------------------------------------
# Differential proof against the legacy per-layer implementation
# ---------------------------------------------------------------------------


def normalize_volatile(value: Any) -> Any:
    """Recursively replace wall-clock fields with a fixed marker."""

    if isinstance(value, Mapping):
        return {
            key: ("<volatile>" if key in VOLATILE_FIELDS else normalize_volatile(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_volatile(item) for item in value]
    return value


FROZEN_CLOCK = "2026-01-01T00:00:00.000000Z"


@contextmanager
def _frozen_clock(value: str = FROZEN_CLOCK):
    """Pin both this module's and the legacy module's wall clock.

    Certificate hashes cover ``issued_at``, so digest-level equivalence
    against the legacy implementation requires a shared deterministic clock.
    """

    from blackhole_agent import capability_compounder as legacy_mod

    engine_mod = sys.modules[__name__]
    orig_legacy = legacy_mod.utc_now_iso
    orig_engine = engine_mod.utc_now_iso
    legacy_mod.utc_now_iso = lambda: value
    engine_mod.utc_now_iso = lambda: value
    try:
        yield
    finally:
        legacy_mod.utc_now_iso = orig_legacy
        engine_mod.utc_now_iso = orig_engine


def _synthetic_parent_bundle(layer: PlaneLayer) -> dict[str, Any]:
    """Build a deterministic synthetic parent bundle for the realm layer.

    The parent (dominion) certificate is issued through the legacy issuer so
    that legacy verifiers accept the bundle; this keeps the differential proof
    a true cross-implementation check rather than a self-agreement test.
    """

    if layer.name != "realm":
        raise KeyError(f"no synthetic parent fixture for layer {layer.name!r}")
    from blackhole_agent.capability_compounder import issue_dominion_certificate

    entries = []
    for index in range(3):
        root = hashlib.sha256(f"dominion-root-{index}".encode()).hexdigest()[:24]
        digest = hashlib.sha256(f"dominion-digest-{index}".encode()).hexdigest()[:24]
        entries.append(
            {
                "dominion_root": root,
                "dominion_height": index + 1,
                "dominion_plan_digest": digest,
                "capability_id": f"capability.fixture-{index}",
                "effect": f"fixture-effect-{index}",
                "receipt_digest": hashlib.sha256(
                    f"receipt-{index}".encode()
                ).hexdigest()[:24],
                "bound_settlement_root": hashlib.sha256(
                    f"settlement-{index}".encode()
                ).hexdigest()[:24],
                "bound_action_root": hashlib.sha256(
                    f"action-{index}".encode()
                ).hexdigest()[:24],
            }
        )
    dominion_hash = hashlib.sha256(b"dominion-bundle-hash").hexdigest()[:24]
    package_hash = hashlib.sha256(b"fixture-package").hexdigest()[:24]
    lineage_head = hashlib.sha256(b"fixture-lineage").hexdigest()[:24]
    cert = issue_dominion_certificate(
        dominion_height=3,
        dominion_root=entries[-1]["dominion_root"],
        parent_dominion_root=entries[-2]["dominion_root"],
        bound_empire_root=hashlib.sha256(b"empire-root").hexdigest()[:24],
        bound_empire_height=2,
        empire_hash=hashlib.sha256(b"empire-hash").hexdigest()[:24],
        empire_certificate_hash=hashlib.sha256(b"empire-cert").hexdigest()[:24],
        package_hash=package_hash,
        lineage_head_hash=lineage_head,
        empire_plan_digest=hashlib.sha256(b"empire-digest").hexdigest()[:24],
        dominion_plan_digest=entries[-1]["dominion_plan_digest"],
        dominion_count=3,
        member_ids=["capability.fixture-0", "capability.fixture-1"],
        goal="differential fixture",
    )
    return {
        "kind": "dominion_bundle",
        "goal": "differential fixture",
        "dominions": {"entries": entries, "entry_count": len(entries)},
        "tip_dominion_root": entries[-1]["dominion_root"],
        "dominion_count": len(entries),
        "dominion_hash": dominion_hash,
        "dominion_certificate": cert,
        "dominion_plan_digest": entries[-1]["dominion_plan_digest"],
        "package": {"package_hash": package_hash, "member_ids": ["capability.fixture-0"]},
        "package_hash": package_hash,
        "lineage_head_hash": lineage_head,
        "member_ids": ["capability.fixture-0", "capability.fixture-1"],
    }


def differential_proof(repo_path: Path | None = None) -> dict[str, Any]:
    """Prove the engine is digest-equivalent to the legacy realm plane.

    Checks, all against the same synthetic dominion parent bundle:

    1. spec derivation equality with ``derive_realm_specs_from_dominion``
    2. per-entry equality (roots, digests, certificates) with the legacy
       ``apply_realm_transition`` loop, modulo wall-clock fields
    3. cross chain verification: each implementation accepts the other's log
    4. bundle equality with ``build_realm_bundle`` modulo wall-clock fields
    5. cross bundle integrity: each implementation's integrity verifier
       accepts the other's bundle
    6. adversarial agreement: tampered roots, reordered entries, height gaps,
       wrong parent binding, forged genesis parent, and broken certificates
       are rejected by both implementations
    """

    from blackhole_agent import capability_compounder as legacy

    with _frozen_clock():
        return _differential_proof_frozen(legacy, repo_path)


def _differential_proof_frozen(
    legacy: Any, repo_path: Path | None = None
) -> dict[str, Any]:
    """Differential proof body executed under a frozen deterministic clock."""

    layer = get_layer("realm")
    parent = _synthetic_parent_bundle(layer)
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    # 1. Spec derivation equality.
    legacy_specs = legacy.derive_realm_specs_from_dominion(parent, min_realms=2)
    engine_specs = derive_specs(layer, parent, min_count=2)
    record(
        "spec_derivation_equal",
        normalize_volatile(legacy_specs) == normalize_volatile(engine_specs)
        and len(engine_specs) >= 2,
        f"legacy={len(legacy_specs)} engine={len(engine_specs)}",
    )

    # 2. Transition equality entry by entry.
    legacy_log = legacy.empty_realm_log()
    engine_log = empty_log(layer)
    transitions_equal = True
    for index, spec in enumerate(legacy_specs):
        goal = f"{parent.get('goal')} (clearing {index + 1})"
        claims = {"clearing_index": index + 1, "plane": "realm"}
        legacy_result = legacy.apply_realm_transition(
            legacy_log, spec, dominion_bundle=parent, goal=goal, claims=claims
        )
        engine_result = apply_transition(
            layer, engine_log, spec, parent_bundle=parent, goal=goal, claims=claims
        )
        if not legacy_result.get("ok") or not engine_result.get("ok"):
            transitions_equal = False
            break
        if normalize_volatile(legacy_result["entry"]) != normalize_volatile(
            engine_result["entry"]
        ):
            transitions_equal = False
            break
        legacy_log = legacy_result["realm_log"]
        engine_log = engine_result["log"]
    record(
        "transitions_equal",
        transitions_equal
        and normalize_volatile(legacy_log) == normalize_volatile(engine_log),
        f"entries={len(engine_log.get('entries') or [])}",
    )

    # 3. Cross chain verification.
    legacy_chain_own = legacy.verify_realm_chain(legacy_log)
    engine_chain_own = verify_chain(layer, engine_log)
    legacy_chain_engine = legacy.verify_realm_chain(engine_log)
    engine_chain_legacy = verify_chain(layer, legacy_log)
    record(
        "cross_chain_verification",
        bool(legacy_chain_own.get("valid"))
        and bool(engine_chain_own.get("valid"))
        and bool(legacy_chain_engine.get("valid"))
        and bool(engine_chain_legacy.get("valid")),
        f"tip={engine_chain_own.get('tip_realm_root')}",
    )

    # 4. Bundle equality and 5. cross integrity.
    goal = "realm over dominion"
    legacy_bundle = legacy.build_realm_bundle(legacy_log, parent, goal=goal)
    engine_bundle = build_bundle(layer, engine_log, parent, goal=goal)
    record(
        "bundles_equal",
        normalize_volatile(legacy_bundle) == normalize_volatile(engine_bundle),
        f"realm_hash={engine_bundle.get('realm_hash')}",
    )
    legacy_accepts_engine = legacy.verify_realm_bundle_integrity(engine_bundle)
    engine_accepts_legacy = verify_bundle_integrity(
        layer,
        legacy_bundle,
        parent_certificate_verifier=legacy.verify_dominion_certificate,
    )
    record(
        "cross_bundle_integrity",
        bool(legacy_accepts_engine.get("ok")) and bool(engine_accepts_legacy.get("ok")),
        f"legacy_ok={legacy_accepts_engine.get('ok')}"
        f" engine_ok={engine_accepts_legacy.get('ok')}",
    )

    # 6. Adversarial agreement on mutations of the engine log.
    mutations: dict[str, dict[str, Any]] = {}
    tampered = copy.deepcopy(engine_log)
    tampered["entries"][1]["realm_root"] = "f" * 24
    mutations["tampered_root"] = tampered
    reordered = copy.deepcopy(engine_log)
    reordered["entries"] = [reordered["entries"][1], reordered["entries"][0]]
    mutations["reordered_entries"] = reordered
    gapped = copy.deepcopy(engine_log)
    gapped["entries"][1]["realm_height"] = 5
    mutations["height_gap"] = gapped
    wrong_binding = copy.deepcopy(engine_log)
    wrong_binding["entries"][0]["bound_dominion_root"] = "0" * 24
    mutations["wrong_parent_binding"] = wrong_binding
    forged = copy.deepcopy(engine_log)
    forged["entries"][0]["parent_realm_root"] = "a" * 24
    mutations["forged_genesis_parent"] = forged
    broken_cert = copy.deepcopy(engine_log)
    broken_cert["entries"][0]["realm_certificate"]["realm_root"] = "b" * 24
    mutations["broken_certificate"] = broken_cert

    adversarial_ok = True
    adversarial_detail: list[str] = []
    for name, mutated in mutations.items():
        engine_verdict = verify_chain(layer, mutated)
        legacy_verdict = legacy.verify_realm_chain(mutated)
        agreed = (not engine_verdict.get("valid")) and (not legacy_verdict.get("valid"))
        adversarial_ok = adversarial_ok and agreed
        adversarial_detail.append(f"{name}:{'reject' if agreed else 'ACCEPTED'}")
    record("adversarial_agreement", adversarial_ok, ",".join(adversarial_detail))

    ok = all(check["ok"] for check in checks) and not _skill_route_used()
    result: dict[str, Any] = {
        "ok": ok,
        "action": "plane_engine_differential_proof",
        "layer": layer.name,
        "parent": layer.parent,
        "checks": checks,
        "tip_realm_root": engine_chain_own.get("tip_realm_root"),
        "realm_hash": engine_bundle.get("realm_hash"),
        "used_skill_route_discovery": _skill_route_used(),
    }

    if repo_path is not None and ok:
        out_dir = (Path(repo_path) / "artifacts" / "plane-engine").resolve()
        bundle_path = write_bundle(out_dir / "proof-realm.json", engine_bundle)
        tip_cert = engine_bundle.get("realm_certificate") or {}
        write_certificate(out_dir / "certificate-realm.json", tip_cert)
        result["bundle_path"] = str(bundle_path)
    return result


def builtin_plane_engine() -> dict[str, Any]:
    """Invocable capability entry: run the differential proof and persist evidence."""

    repo_path = Path(__file__).resolve().parents[2]
    return differential_proof(repo_path)
