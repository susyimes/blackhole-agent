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
import inspect
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
    """Nouns that parameterize one plane layer transition.

    The defaults reproduce the plan-digest family (recovery..cosmos). The
    settlement dialect (clearing..resilience) renames the digest/ratio/kind
    slots; settlement itself is an unchained receipt dialect bound to
    actuation action roots.
    """

    name: str  # self noun, e.g. "realm"
    parent: str  # parent noun, e.g. "dominion"
    plural: str  # self plural, log key inside the bundle, e.g. "realms"
    parent_plural: str  # parent plural key inside the parent bundle
    outcome: str  # past-tense outcome verb, e.g. "realmed"
    bundle_relative: Path  # default bundle directory relative to repo root
    legacy_derive: str = ""  # override for irregular legacy derive fn names
    parent_digest: str = ""  # override for the parent digest field name
    self_digest: str = ""  # override for the own chain digest field name
    parent_chain: str = ""  # override for the parent-chain digest field name
    ratio_field: str | None = "position_ratio_bps"  # None = ratio-less dialect
    entry_kind: str = ""  # entry "kind" value, default f"{name}_action"
    chained: bool = True  # False = unchained receipt dialect (settlement)
    cert_self_digest: bool = True  # certificate carries the self digest slot
    cert_parent_digest: bool = True  # certificate carries the parent digest slot
    bind_noun: str = ""  # binding noun, default parent; settlement: "action"
    hash_noun: str = ""  # parent hash/cert noun, default parent; settlement: "actuation"
    carried_spec_fields: tuple[str, ...] = (
        "receipt_digest",
        "bound_settlement_root",
        "bound_action_root",
    )
    entry_extra_fields: tuple[str, ...] = ()
    includes_settlement_vocab: bool = True  # bundle carries settlement-era keys
    bundle_parent_digest: bool = True  # bundle top-level parent digest slot
    parent_cert_label: str = ""  # certificates-dict label for the parent cert
    bundle_kind: str = ""  # bundle "kind" value, default f"{name}_bundle"

    @property
    def parent_digest_field(self) -> str:
        """Field carrying the parent plan/buffer digest (dialect boundary)."""

        return self.parent_digest or f"{self.parent}_plan_digest"

    @property
    def self_digest_field(self) -> str:
        """Field carrying this layer's own chaining digest."""

        return self.self_digest or f"{self.name}_plan_digest"

    @property
    def parent_chain_field(self) -> str:
        """Field chaining the previous entry's digest."""

        return self.parent_chain or f"parent_{self.name}_digest"

    @property
    def kind_name(self) -> str:
        return self.entry_kind or f"{self.name}_action"

    @property
    def bind(self) -> str:
        return self.bind_noun or self.parent

    @property
    def hash_parent(self) -> str:
        return self.hash_noun or self.parent


# Parent chain for the whole plane stack. Layers below ``recovery`` belong to
# the older net-position-digest dialect and are not engine-registered yet, but
# their links are needed to issue synthetic parent certificates.
PARENT_OF: dict[str, str] = {
    "cosmos": "realm",
    "realm": "dominion",
    "dominion": "empire",
    "empire": "commonwealth",
    "commonwealth": "union",
    "union": "confederation",
    "confederation": "coalition",
    "coalition": "alliance",
    "alliance": "pact",
    "pact": "treaty",
    "treaty": "covenant",
    "covenant": "constitution",
    "constitution": "charter",
    "charter": "mandate",
    "mandate": "privilege",
    "privilege": "standing",
    "standing": "reputation",
    "reputation": "recognition",
    "recognition": "reaccreditation",
    "reaccreditation": "reverification",
    "reverification": "revalidation",
    "revalidation": "reattestation",
    "reattestation": "recertification",
    "recertification": "reauthorization",
    "reauthorization": "reinstatement",
    "reinstatement": "rehabilitation",
    "rehabilitation": "reorganization",
    "reorganization": "restructuring",
    "restructuring": "resolution",
    "resolution": "recovery",
    "recovery": "resilience",
    "resilience": "stress",
    "stress": "risk",
    "risk": "solvency",
    "solvency": "capital",
    "capital": "funding",
    "funding": "liquidity",
    "liquidity": "collateral",
    "collateral": "margin",
    "margin": "clearing",
    "clearing": "settlement",
    "settlement": "actuation",
    "actuation": "execution",
}


def _layer(
    name: str,
    plural: str,
    parent_plural: str,
    outcome: str,
    legacy_derive: str = "",
    parent_digest: str = "",
    **dialect: Any,
) -> PlaneLayer:
    return PlaneLayer(
        name=name,
        parent=PARENT_OF[name],
        plural=plural,
        parent_plural=parent_plural,
        outcome=outcome,
        bundle_relative=Path("artifacts") / f"{name}-bundles",
        legacy_derive=legacy_derive,
        parent_digest=parent_digest,
        **dialect,
    )


# Layers are registered only after the differential proof covers them.
# The plan-digest dialect family: recovery .. cosmos.
LAYERS: dict[str, PlaneLayer] = {
    layer.name: layer
    for layer in (
        _layer(
            "recovery",
            "recoveries",
            "resiliences",
            "recovered",
            parent_digest="resilience_buffer_digest",
        ),
        _layer("resolution", "resolutions", "recoveries", "resolved"),
        _layer("restructuring", "restructurings", "resolutions", "restructured"),
        _layer("reorganization", "reorganizations", "restructurings", "reorganized"),
        _layer("rehabilitation", "rehabilitations", "reorganizations", "rehabilitated"),
        _layer("reinstatement", "reinstatements", "rehabilitations", "reinstated"),
        _layer("reauthorization", "reauthorizations", "reinstatements", "reauthorized"),
        _layer("recertification", "recertifications", "reauthorizations", "recertified"),
        _layer("reattestation", "reattestations", "recertifications", "reattested"),
        _layer("revalidation", "revalidations", "reattestations", "revalidated"),
        _layer("reverification", "reverifications", "revalidations", "reverified"),
        _layer("reaccreditation", "reaccreditations", "reverifications", "reaccredited"),
        _layer("recognition", "recognitions", "reaccreditations", "recognized"),
        _layer("reputation", "reputations", "recognitions", "reputed"),
        _layer("standing", "standings", "reputations", "stood"),
        _layer("privilege", "privileges", "standings", "privileged"),
        _layer("mandate", "mandates", "privileges", "mandated"),
        _layer("charter", "charters", "mandates", "chartered"),
        _layer(
            "constitution",
            "constitutions",
            "charters",
            "constituted",
            legacy_derive="deriveconstitutionspecs_fromcharter",
        ),
        _layer(
            "covenant",
            "covenants",
            "constitutions",
            "covenanted",
            legacy_derive="derivecovenantspecs_fromconstitution",
        ),
        _layer(
            "treaty",
            "treaties",
            "covenants",
            "treatied",
            legacy_derive="derivetreatiespecs_fromcovenant",
        ),
        _layer(
            "pact",
            "pacts",
            "treaties",
            "pacted",
            legacy_derive="derivepactspecs_fromtreaty",
        ),
        _layer("alliance", "alliances", "pacts", "allied"),
        _layer("coalition", "coalitions", "alliances", "coalitioned"),
        _layer("confederation", "confederations", "coalitions", "confederated"),
        _layer("union", "unions", "confederations", "united"),
        _layer("commonwealth", "commonwealths", "unions", "commonwealthed"),
        _layer("empire", "empires", "commonwealths", "empired"),
        _layer("dominion", "dominions", "empires", "dominioned"),
        _layer("realm", "realms", "dominions", "realmed"),
        _layer("cosmos", "cosmoses", "realms", "cosmosed"),
        # Settlement dialect: renamed digest/ratio/kind slots.
        _layer(
            "resilience",
            "resiliences",
            "stresses",
            "resilient",
            self_digest="resilience_buffer_digest",
            parent_digest="stress_scenario_digest",
            entry_kind="resilience_buffer",
            bundle_kind="stress_bundle",
        ),
        _layer(
            "stress",
            "stresses",
            "risks",
            "stressed",
            self_digest="stress_scenario_digest",
            parent_digest="risk_assessment_digest",
            entry_kind="stress_scenario",
        ),
        _layer(
            "risk",
            "risks",
            "solvencies",
            "risked",
            self_digest="risk_assessment_digest",
            parent_digest="solvency_position_digest",
            entry_kind="risk_assessment",
        ),
        _layer(
            "solvency",
            "solvencies",
            "capitals",
            "solvent",
            self_digest="solvency_position_digest",
            parent_digest="capital_buffer_digest",
            entry_kind="solvency_position",
        ),
        _layer(
            "capital",
            "capitals",
            "fundings",
            "capitalized",
            self_digest="capital_buffer_digest",
            parent_digest="funding_facility_digest",
            entry_kind="capital_buffer",
            ratio_field="buffer_ratio_bps",
        ),
        _layer(
            "funding",
            "fundings",
            "liquidities",
            "funded",
            self_digest="funding_facility_digest",
            parent_digest="liquidity_coverage_digest",
            entry_kind="funding_facility",
            ratio_field="facility_ratio_bps",
        ),
        _layer(
            "liquidity",
            "liquidities",
            "collaterals",
            "liquid",
            self_digest="liquidity_coverage_digest",
            parent_digest="collateral_allocation_digest",
            entry_kind="liquidity_coverage",
            ratio_field="coverage_ratio_bps",
        ),
        _layer(
            "collateral",
            "collaterals",
            "margins",
            "collateralized",
            self_digest="collateral_allocation_digest",
            parent_digest="margin_requirement_digest",
            entry_kind="collateral_allocation",
            ratio_field="cover_ratio_bps",
        ),
        _layer(
            "margin",
            "margins",
            "clearings",
            "margined",
            self_digest="margin_requirement_digest",
            parent_digest="net_position_digest",
            entry_kind="margin_requirement",
            ratio_field="haircut_bps",
            parent_cert_label="clearing_certificate",
        ),
        _layer(
            "clearing",
            "clearings",
            "settlements",
            "cleared",
            self_digest="net_position_digest",
            parent_digest="receipt_digest",
            parent_chain="parent_net_digest",
            entry_kind="clearing_position",
            ratio_field=None,
            cert_parent_digest=False,
            carried_spec_fields=("bound_action_root",),
            bundle_parent_digest=False,
            parent_cert_label="settlement_certificate",
        ),
        # Settlement: unchained receipt dialect bound to actuation actions.
        _layer(
            "settlement",
            "settlements",
            "actions",
            "settled",
            self_digest="receipt_digest",
            entry_kind="settlement_receipt",
            ratio_field=None,
            chained=False,
            cert_self_digest=False,
            cert_parent_digest=False,
            bind_noun="action",
            hash_noun="actuation",
            carried_spec_fields=("effect_digest", "entry"),
            entry_extra_fields=("effect_digest", "entry"),
            includes_settlement_vocab=False,
            bundle_parent_digest=False,
            parent_cert_label="actuation_certificate",
        ),
    )
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
    log: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": f"{layer.name}_log",
        "entries": [],
        "entry_count": 0,
        "tip_height": 0,
        f"tip_{layer.name}_root": "",
        f"bound_{layer.bind}_root": "",
        f"bound_{layer.bind}_height": 0,
        f"{layer.hash_parent}_hash": "",
        "updated_at": utc_now_iso(),
    }
    if layer.chained:
        log[layer.self_digest_field] = ""
    return log


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

    payload: dict[str, Any] = {
        layer.parent_chain_field: parent_digest or "",
        f"bound_{layer.bind}_root": bound_parent_root,
        layer.parent_digest_field: parent_plan_digest,
        "capability_id": capability_id,
        "outcome": outcome or layer.outcome,
        "plane": layer.name,
    }
    if layer.ratio_field:
        payload[layer.ratio_field] = int(position_ratio_bps)
    return _sha24(payload)


def compute_receipt_digest(
    layer: PlaneLayer,
    *,
    capability_id: str,
    effect: str,
    bound_root: str,
    parent_hash: str,
    package_hash: str,
    outcome: str = "",
) -> str:
    """Unchained settlement receipt digest over one bound action."""

    payload = {
        "capability_id": capability_id,
        "effect": effect,
        f"bound_{layer.bind}_root": bound_root,
        f"{layer.hash_parent}_hash": parent_hash,
        "package_hash": package_hash,
        "outcome": outcome or layer.outcome,
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
        f"bound_{layer.bind}_root": str(bound_parent_root or ""),
        f"bound_{layer.bind}_height": int(bound_parent_height or 0),
        f"{layer.hash_parent}_hash": str(parent_hash or ""),
        f"{layer.hash_parent}_certificate_hash": str(parent_certificate_hash or ""),
        "package_hash": str(package_hash or ""),
        "lineage_head_hash": str(lineage_head_hash or ""),
        f"{layer.name}_count": int(count),
        "member_ids": members,
        "member_count": len(members),
        "goal": goal or "",
        "claims": dict(claims or {}),
        "deterministic": True,
        f"post_{layer.hash_parent}": True,
        "used_skill_route_discovery": _skill_route_used(),
    }
    if layer.cert_parent_digest:
        cert[layer.parent_digest_field] = str(parent_plan_digest or "")
    if layer.cert_self_digest:
        cert[layer.self_digest_field] = str(plan_digest or "")
    cert["certificate_hash"] = compute_certificate_hash(cert)
    cert["ok"] = (
        bool(cert["certificate_hash"])
        and bool(cert[f"{layer.name}_root"])
        and bool(cert[f"bound_{layer.bind}_root"])
        and bool(cert[f"{layer.hash_parent}_hash"])
        and (
            not layer.cert_self_digest
            or bool(cert[layer.self_digest_field])
        )
        and (
            not layer.cert_parent_digest
            or bool(cert[layer.parent_digest_field])
        )
        and cert[f"{layer.name}_height"] >= 1
        and cert[f"{layer.name}_count"] >= 1
        and cert["deterministic"] is True
        and cert[f"post_{layer.hash_parent}"] is True
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
        and bool(data.get(f"bound_{layer.bind}_root"))
        and bool(data.get(f"{layer.hash_parent}_hash"))
        and (
            not layer.cert_self_digest
            or bool(data.get(layer.self_digest_field))
        )
        and (
            not layer.cert_parent_digest
            or bool(data.get(layer.parent_digest_field))
        )
        and int(data.get(f"{layer.name}_height") or 0) >= 1
        and int(data.get(f"{layer.name}_count") or 0) >= 1
        and data.get("deterministic") is True
        and data.get(f"post_{layer.hash_parent}") is True
        and not bool(data.get("used_skill_route_discovery"))
    )
    return {
        "ok": valid,
        "valid": valid,
        "hash_ok": hash_ok,
        "certificate_hash": stored if hash_ok else recomputed,
        f"{layer.name}_height": data.get(f"{layer.name}_height"),
        f"{layer.name}_root": data.get(f"{layer.name}_root"),
        f"bound_{layer.bind}_root": data.get(f"bound_{layer.bind}_root"),
        layer.self_digest_field: data.get(layer.self_digest_field),
        f"{layer.hash_parent}_hash": data.get(f"{layer.hash_parent}_hash"),
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
        parent_root = str(entry.get(f"{layer.bind}_root") or "")
        if not parent_root:
            continue
        spec: dict[str, Any] = {
            "capability_id": str(entry.get("capability_id") or ""),
            "effect": str(entry.get("effect") or ""),
            f"bound_{layer.bind}_root": parent_root,
            f"bound_{layer.bind}_height": int(
                entry.get(f"{layer.bind}_height") or 0
            ),
        }
        if layer.chained:
            spec[layer.parent_digest_field] = str(
                entry.get(layer.parent_digest_field) or ""
            )
        for field in layer.carried_spec_fields:
            if field not in spec:
                spec[field] = str(entry.get(field) or "")
        spec["package_hash"] = str(
            entry.get("package_hash") or parent_bundle.get("package_hash") or ""
        )
        spec["outcome"] = layer.outcome
        if layer.ratio_field:
            spec[layer.ratio_field] = 1000 + 100 * len(specs)
        specs.append(spec)
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
        str(entries[-1].get(layer.self_digest_field) or "") if entries else ""
    )

    bound_root = str(spec.get(f"bound_{layer.bind}_root") or "")
    bound_height = int(spec.get(f"bound_{layer.bind}_height") or 0)
    capability_id = str(spec.get("capability_id") or "")
    effect = str(spec.get("effect") or "")
    outcome = str(spec.get("outcome") or layer.outcome)
    package_hash = str(
        spec.get("package_hash") or parent_bundle.get("package_hash") or ""
    )
    parent_hash = str(parent_bundle.get(f"{layer.hash_parent}_hash") or "")
    tip_parent_root = str(parent_bundle.get(f"tip_{layer.bind}_root") or "")
    parent_log = (
        parent_bundle.get(layer.parent_plural)
        if isinstance(parent_bundle.get(layer.parent_plural), Mapping)
        else {}
    )
    parent_entries = list(parent_log.get("entries") or [])
    known_roots = {
        str(item.get(f"{layer.bind}_root") or "")
        for item in parent_entries
        if isinstance(item, Mapping) and item.get(f"{layer.bind}_root")
    }
    if tip_parent_root:
        known_roots.add(tip_parent_root)

    if not capability_id or not bound_root or not parent_hash:
        return {
            "ok": False,
            "action": "apply_transition",
            "error": f"missing_{layer.bind}_bind_fields",
            "log": new_log,
            "used_skill_route_discovery": _skill_route_used(),
        }
    if bound_root not in known_roots:
        return {
            "ok": False,
            "action": "apply_transition",
            "error": f"bound_{layer.bind}_root_mismatch",
            f"bound_{layer.bind}_root": bound_root,
            f"known_{layer.bind}_roots": sorted(known_roots),
            "log": new_log,
            "used_skill_route_discovery": _skill_route_used(),
        }
    if any(
        str(item.get(f"bound_{layer.bind}_root") or "") == bound_root
        and str(item.get("outcome") or "") == outcome
        for item in entries
    ):
        return {
            "ok": False,
            "action": "apply_transition",
            "error": f"duplicate_{layer.bind}_rejected",
            "log": new_log,
            "used_skill_route_discovery": _skill_route_used(),
        }

    parent_cert = (
        parent_bundle.get(f"{layer.hash_parent}_certificate")
        if isinstance(parent_bundle.get(f"{layer.hash_parent}_certificate"), Mapping)
        else {}
    )
    parent_cert_hash = str(parent_cert.get("certificate_hash") or "")
    lineage_head = str(parent_bundle.get("lineage_head_hash") or "")
    member_ids = list(parent_bundle.get("member_ids") or [])
    ratio_bps = (
        int(spec.get(layer.ratio_field) or 1000) if layer.ratio_field else 0
    )
    if layer.chained:
        parent_plan_digest = str(spec.get(layer.parent_digest_field) or "")
        if not parent_plan_digest:
            for item in parent_entries:
                if (
                    isinstance(item, Mapping)
                    and str(item.get(f"{layer.bind}_root") or "") == bound_root
                ):
                    parent_plan_digest = str(
                        item.get(layer.parent_digest_field) or ""
                    )
                    break
        plan_digest = compute_plan_digest(
            layer,
            parent_digest=parent_digest,
            bound_parent_root=bound_root,
            parent_plan_digest=parent_plan_digest,
            position_ratio_bps=ratio_bps,
            capability_id=capability_id,
            outcome=outcome,
        )
    else:
        parent_plan_digest = ""
        plan_digest = compute_receipt_digest(
            layer,
            capability_id=capability_id,
            effect=effect,
            bound_root=bound_root,
            parent_hash=parent_hash,
            package_hash=package_hash,
            outcome=outcome,
        )

    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": layer.kind_name,
        f"{layer.name}_height": next_height,
        f"parent_{layer.name}_root": parent_root,
        f"bound_{layer.bind}_root": bound_root,
        f"bound_{layer.bind}_height": bound_height,
        f"{layer.hash_parent}_hash": parent_hash,
        f"{layer.hash_parent}_certificate_hash": parent_cert_hash,
        "package_hash": package_hash,
        "lineage_head_hash": lineage_head,
        "capability_id": capability_id,
        "effect": effect,
        "outcome": outcome,
        "member_ids": sorted({str(m).strip() for m in member_ids if str(m).strip()}),
        "deterministic": True,
        f"post_{layer.hash_parent}": True,
        "applied_at": utc_now_iso(),
        "goal": goal or str(parent_bundle.get("goal") or ""),
        "claims": dict(claims or {}),
        "used_skill_route_discovery": _skill_route_used(),
    }
    if layer.chained:
        body[layer.parent_digest_field] = parent_plan_digest
        body[layer.self_digest_field] = plan_digest
        body[layer.parent_chain_field] = parent_digest
    else:
        body[layer.self_digest_field] = plan_digest
    if layer.ratio_field:
        body[layer.ratio_field] = ratio_bps
    if layer.bind != "action":
        body["bound_action_root"] = str(spec.get("bound_action_root") or "")
    for field in layer.entry_extra_fields:
        body[field] = str(spec.get(field) or "")
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
        and body[f"post_{layer.hash_parent}"] is True
        and not bool(body.get("used_skill_route_discovery"))
    )

    entries.append(body)
    new_log["entries"] = entries
    new_log["entry_count"] = len(entries)
    new_log["tip_height"] = next_height
    new_log[f"tip_{layer.name}_root"] = root
    new_log[f"bound_{layer.bind}_root"] = bound_root
    new_log[f"bound_{layer.bind}_height"] = bound_height
    new_log[f"{layer.hash_parent}_hash"] = parent_hash
    if layer.chained:
        new_log[layer.self_digest_field] = plan_digest
    new_log["updated_at"] = utc_now_iso()
    new_log["schema_version"] = SCHEMA_VERSION
    new_log["kind"] = f"{layer.name}_log"
    result: dict[str, Any] = {
        "ok": bool(body.get("ok")),
        "action": "apply_transition",
        "entry": body,
        f"{layer.name}_height": next_height,
        f"{layer.name}_root": root,
        f"parent_{layer.name}_root": parent_root,
        f"bound_{layer.bind}_root": bound_root,
        "log": new_log,
        "used_skill_route_discovery": _skill_route_used(),
    }
    if layer.chained:
        result[layer.self_digest_field] = plan_digest
    return result


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
        if raw.get(f"post_{layer.hash_parent}") is not True:
            errors.append(f"entry[{index}]_not_post_{layer.hash_parent}")
        bound = str(raw.get(f"bound_{layer.bind}_root") or "")
        if not bound:
            errors.append(f"entry[{index}]_missing_bound_{layer.bind}_root")
        else:
            bound_roots.add(bound)
        p_hash = str(raw.get(f"{layer.hash_parent}_hash") or "")
        if not p_hash:
            errors.append(f"entry[{index}]_missing_{layer.hash_parent}_hash")
        else:
            parent_hashes.add(p_hash)
        if layer.chained:
            parent_plan_digest = str(raw.get(layer.parent_digest_field) or "")
            stored_parent_digest = str(raw.get(layer.parent_chain_field) or "")
            if stored_parent_digest != prev_digest:
                errors.append(f"entry[{index}]_{layer.parent_chain_field}_mismatch")
            expected_digest = compute_plan_digest(
                layer,
                parent_digest=prev_digest,
                bound_parent_root=bound,
                parent_plan_digest=parent_plan_digest,
                position_ratio_bps=(
                    int(raw.get(layer.ratio_field) or 1000)
                    if layer.ratio_field
                    else 0
                ),
                capability_id=str(raw.get("capability_id") or ""),
                outcome=str(raw.get("outcome") or layer.outcome),
            )
            stored_digest = str(raw.get(layer.self_digest_field) or "")
            if not stored_digest or stored_digest != expected_digest:
                errors.append(f"entry[{index}]_{layer.self_digest_field}_mismatch")
        else:
            stored_digest = str(raw.get(layer.self_digest_field) or "")
            if not stored_digest:
                errors.append(f"entry[{index}]_missing_{layer.self_digest_field}")
            else:
                expected_digest = compute_receipt_digest(
                    layer,
                    capability_id=str(raw.get("capability_id") or ""),
                    effect=str(raw.get("effect") or ""),
                    bound_root=bound,
                    parent_hash=p_hash,
                    package_hash=str(raw.get("package_hash") or ""),
                    outcome=str(raw.get("outcome") or layer.outcome),
                )
                if stored_digest != expected_digest:
                    errors.append(f"entry[{index}]_{layer.self_digest_field}_mismatch")
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
            if str(cert.get(f"bound_{layer.bind}_root") or "") != bound:
                errors.append(f"entry[{index}]_cert_bound_{layer.bind}_mismatch")
            if layer.cert_self_digest and str(
                cert.get(layer.self_digest_field) or ""
            ) != stored_digest:
                errors.append(f"entry[{index}]_cert_digest_mismatch")
        prev_root = stored
        prev_digest = stored_digest

    if len(parent_hashes) > 1:
        errors.append(f"mixed_{layer.hash_parent}_hashes")

    tip = entries[-1] if entries else {}
    tip_height = int(tip.get(f"{layer.name}_height") or 0) if isinstance(tip, Mapping) else 0
    tip_root = str(tip.get(f"{layer.name}_root") or "") if isinstance(tip, Mapping) else ""
    tip_digest = (
        str(tip.get(layer.self_digest_field) or "")
        if isinstance(tip, Mapping) and layer.chained
        else ""
    )
    log_tip_height = int(log.get("tip_height") or 0)
    log_tip_root = str(log.get(f"tip_{layer.name}_root") or "")
    if log_tip_height and log_tip_height != tip_height:
        errors.append("tip_height_metadata_mismatch")
    if log_tip_root and log_tip_root != tip_root:
        errors.append(f"tip_{layer.name}_root_metadata_mismatch")
    if layer.chained:
        log_digest = str(log.get(layer.self_digest_field) or "")
        if log_digest and log_digest != tip_digest:
            errors.append(f"{layer.self_digest_field}_metadata_mismatch")

    valid = not errors and tip_height >= 1 and bool(tip_root) and (
        bool(tip_digest) or not layer.chained
    )
    result: dict[str, Any] = {
        "ok": valid,
        "valid": valid,
        "action": "verify_chain",
        "entry_count": len(entries),
        "tip_height": tip_height,
        f"tip_{layer.name}_root": tip_root,
        f"bound_{layer.bind}_roots": sorted(bound_roots),
        f"{layer.hash_parent}_hash": next(iter(parent_hashes), ""),
        "errors": errors,
        "used_skill_route_discovery": _skill_route_used(),
    }
    if layer.chained:
        result[layer.self_digest_field] = tip_digest
    return result


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
    result_out: dict[str, Any] = {
        "ok": ok,
        "action": "apply_bundle",
        "log": log,
        "applied": applied,
        "applied_count": len(applied),
        f"{layer.name}_count": len(applied),
        "tip_height": log.get("tip_height"),
        f"tip_{layer.name}_root": log.get(f"tip_{layer.name}_root"),
        f"bound_{layer.bind}_root": log.get(f"bound_{layer.bind}_root"),
        "chain": chain,
        "used_skill_route_discovery": _skill_route_used(),
    }
    if layer.chained:
        result_out[layer.self_digest_field] = log.get(layer.self_digest_field)
    return result_out


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
        parent_bundle.get(f"{layer.hash_parent}_certificate")
        if isinstance(parent_bundle.get(f"{layer.hash_parent}_certificate"), Mapping)
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
            "kind": layer.parent_cert_label or f"{layer.name}_certificate",
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

    def _mapping(key: str) -> dict[str, Any]:
        value = parent_bundle.get(key)
        return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}

    member_ids = list(parent_bundle.get("member_ids") or package.get("member_ids") or [])
    vocab = layer.includes_settlement_vocab
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": layer.bundle_kind or f"{layer.name}_bundle",
        "action": f"build_{layer.name}_bundle",
        "goal": goal or f"{layer.name} over {layer.parent}",
        layer.plural: copy.deepcopy(dict(log)),
        layer.parent_plural: _mapping(layer.parent_plural),
    }
    ancestor_logs = ("settlements", "actions") if vocab else ("actions",)
    for key in ancestor_logs:
        if key not in bundle:
            bundle[key] = _mapping(key)
    bundle["package"] = copy.deepcopy(dict(package))
    bundle["lineage"] = _mapping("lineage")
    bundle[f"{layer.name}_certificate"] = copy.deepcopy(dict(tip_cert))
    bundle[f"{layer.hash_parent}_certificate"] = copy.deepcopy(dict(parent_cert))
    ancestor_certs = (
        ("settlement_certificate", "actuation_certificate", "execution_certificate")
        if vocab
        else ("actuation_certificate", "execution_certificate")
    )
    for key in ancestor_certs:
        if key not in bundle:
            bundle[key] = _mapping(key)
    bundle["certificates"] = certificates
    bundle["certificate_count"] = len(certificates)
    bundle[f"{layer.name}_count"] = len(entries)
    if vocab:
        bundle[f"{layer.parent}_count"] = int(
            parent_bundle.get(f"{layer.parent}_count") or 0
        )
    ancestor_counts = ("settlement_count", "action_count") if vocab else ("action_count",)
    for key in ancestor_counts:
        if key not in bundle:
            bundle[key] = int(parent_bundle.get(key) or 0)
    bundle["tip_height"] = int(log.get("tip_height") or 0)
    bundle[f"tip_{layer.name}_root"] = str(log.get(f"tip_{layer.name}_root") or "")
    bundle[f"bound_{layer.bind}_root"] = str(log.get(f"bound_{layer.bind}_root") or "")
    bundle[f"bound_{layer.bind}_height"] = int(
        log.get(f"bound_{layer.bind}_height") or 0
    )
    bundle[f"tip_{layer.bind}_root"] = str(
        parent_bundle.get(f"tip_{layer.bind}_root") or ""
    )
    ancestor_roots = (
        (
            "bound_settlement_root",
            "tip_settlement_root",
            "bound_action_root",
            "tip_action_root",
            "bound_state_root",
        )
        if vocab
        else ("bound_action_root", "tip_action_root", "bound_state_root")
    )
    for key in ancestor_roots:
        if key not in bundle:
            bundle[key] = str(parent_bundle.get(key) or "")
    if layer.chained:
        bundle[layer.self_digest_field] = str(log.get(layer.self_digest_field) or "")
    if layer.bundle_parent_digest:
        bundle[layer.parent_digest_field] = str(
            parent_bundle.get(layer.parent_digest_field) or ""
        )
    bundle[f"{layer.hash_parent}_hash"] = str(
        parent_bundle.get(f"{layer.hash_parent}_hash") or ""
    )
    ancestor_hashes = (
        ("settlement_hash", "actuation_hash", "execution_hash")
        if vocab
        else ("actuation_hash", "execution_hash")
    )
    for key in ancestor_hashes:
        if key not in bundle:
            bundle[key] = str(parent_bundle.get(key) or "")
    bundle["package_hash"] = str(parent_bundle.get("package_hash") or "")
    bundle["member_ids"] = sorted({str(m).strip() for m in member_ids if str(m).strip()})
    bundle["member_count"] = len(member_ids)
    bundle["lineage_head_hash"] = str(parent_bundle.get("lineage_head_hash") or "")
    bundle["lineage_entry_count"] = int(parent_bundle.get("lineage_entry_count") or 0)
    bundle["origin_count"] = parent_bundle.get("origin_count")
    bundle["agreeing_count"] = parent_bundle.get("agreeing_count")
    bundle["byzantine_count"] = parent_bundle.get("byzantine_count")
    bundle["state_count"] = parent_bundle.get("state_count")
    bundle["epoch_count"] = parent_bundle.get("epoch_count")
    bundle["deterministic"] = True
    bundle[f"post_{layer.hash_parent}"] = True
    bundle["exported_at"] = utc_now_iso()
    bundle["used_skill_route_discovery"] = _skill_route_used()
    bundle[f"{layer.name}_hash"] = compute_bundle_hash(layer, bundle)
    bundle["ok"] = (
        bool(chain.get("valid"))
        and bool(tip_cert_verify.get("valid"))
        and len(entries) >= 2
        and bool(bundle[f"{layer.name}_hash"])
        and bool(bundle[f"{layer.hash_parent}_hash"])
        and (not layer.chained or bool(bundle[layer.self_digest_field]))
        and bundle["deterministic"] is True
        and bundle[f"post_{layer.hash_parent}"] is True
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
    bound_ok = bool(bundle.get(f"bound_{layer.bind}_root")) and bool(
        bundle.get(f"{layer.hash_parent}_hash")
    )
    if layer.chained:
        digest_ok = bool(bundle.get(layer.self_digest_field)) and str(
            bundle.get(layer.self_digest_field) or ""
        ) == str(
            chain.get(layer.self_digest_field)
            or bundle.get(layer.self_digest_field)
            or ""
        )
    else:
        digest_ok = True
    deterministic = bundle.get("deterministic") is True
    post_parent = bundle.get(f"post_{layer.hash_parent}") is True
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
    result: dict[str, Any] = {
        "ok": ok,
        "valid": ok,
        "action": "verify_bundle_integrity",
        "hash_ok": hash_ok,
        "chain": chain,
        "certificate": cert_verify,
        f"{layer.hash_parent}_certificate": dict(parent_cert_verify),
        "multi": multi,
        f"{layer.name}_count": int(
            bundle.get(f"{layer.name}_count") or chain.get("entry_count") or 0
        ),
        f"{layer.name}_hash": expected if hash_ok else recomputed,
        f"tip_{layer.name}_root": chain.get(f"tip_{layer.name}_root"),
        "used_skill_route_discovery": used_skill,
    }
    if layer.chained:
        result[layer.self_digest_field] = bundle.get(layer.self_digest_field)
    return result


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


def _legacy_fn(legacy: Any, *candidates: str) -> Callable[..., Any]:
    for candidate in candidates:
        if candidate:
            fn = getattr(legacy, candidate, None)
            if callable(fn):
                return fn
    raise AttributeError(f"no legacy function among {candidates!r}")


def _synthetic_parent_bundle(
    layer: PlaneLayer, legacy: Any | None = None
) -> dict[str, Any]:
    """Build a deterministic synthetic parent bundle for any registered layer.

    The parent certificate is issued through the legacy issuer so that legacy
    verifiers accept the bundle; this keeps the differential proof a true
    cross-implementation check rather than a self-agreement test.
    """

    if legacy is None:
        from blackhole_agent import capability_compounder as legacy_mod

        legacy = legacy_mod
    parent = layer.parent
    bind = layer.bind
    hash_parent = layer.hash_parent
    grandparent = PARENT_OF[parent]
    entry_digest_field = layer.parent_digest_field
    entries = []
    for index in range(3):
        root = hashlib.sha256(f"{bind}-root-{index}".encode()).hexdigest()[:24]
        digest = hashlib.sha256(f"{bind}-digest-{index}".encode()).hexdigest()[:24]
        entry: dict[str, Any] = {
            f"{bind}_root": root,
            f"{bind}_height": index + 1,
            "capability_id": f"capability.fixture-{index}",
            "effect": f"fixture-effect-{index}",
        }
        if layer.chained:
            entry[entry_digest_field] = digest
        for field in layer.carried_spec_fields:
            if field not in entry:
                entry[field] = hashlib.sha256(
                    f"{field}-{index}".encode()
                ).hexdigest()[:24]
        entries.append(entry)
    parent_hash = hashlib.sha256(f"{hash_parent}-bundle-hash".encode()).hexdigest()[:24]
    package_hash = hashlib.sha256(b"fixture-package").hexdigest()[:24]
    lineage_head = hashlib.sha256(b"fixture-lineage").hexdigest()[:24]
    issuer = _legacy_fn(legacy, f"issue_{hash_parent}_certificate")
    offered = {
        f"{hash_parent}_height": 3,
        f"{hash_parent}_root": entries[-1][f"{bind}_root"],
        f"parent_{hash_parent}_root": entries[-2][f"{bind}_root"],
        f"bound_{grandparent}_root": hashlib.sha256(
            f"{grandparent}-root".encode()
        ).hexdigest()[:24],
        f"bound_{grandparent}_height": 2,
        f"{grandparent}_hash": hashlib.sha256(
            f"{grandparent}-hash".encode()
        ).hexdigest()[:24],
        f"{grandparent}_certificate_hash": hashlib.sha256(
            f"{grandparent}-cert".encode()
        ).hexdigest()[:24],
        "package_hash": package_hash,
        "lineage_head_hash": lineage_head,
        f"{grandparent}_plan_digest": hashlib.sha256(
            f"{grandparent}-digest".encode()
        ).hexdigest()[:24],
        f"{hash_parent}_count": 3,
        "member_ids": ["capability.fixture-0", "capability.fixture-1"],
        "goal": "differential fixture",
    }
    if layer.chained:
        offered[entry_digest_field] = entries[-1][entry_digest_field]
    accepted = set(inspect.signature(issuer).parameters)
    kwargs = {key: value for key, value in offered.items() if key in accepted}
    signature = inspect.signature(issuer)
    for name, parameter in signature.parameters.items():
        if name in kwargs or parameter.default is not inspect.Parameter.empty:
            continue
        # Dialect-boundary issuers rename digest kwargs (e.g.
        # stress_scenario_digest, resilience_buffer_digest); fill any other
        # required parameter deterministically.
        if name.endswith(("_count", "_height")):
            kwargs[name] = 3 if name.endswith("_count") else 2
        else:
            kwargs[name] = hashlib.sha256(f"{parent}-{name}".encode()).hexdigest()[:24]
    cert = issuer(**kwargs)
    bundle: dict[str, Any] = {
        "kind": f"{hash_parent}_bundle",
        "goal": "differential fixture",
        layer.parent_plural: {"entries": entries, "entry_count": len(entries)},
        f"tip_{bind}_root": entries[-1][f"{bind}_root"],
        f"{parent}_count": len(entries),
        f"{hash_parent}_hash": parent_hash,
        f"{hash_parent}_certificate": cert,
        "package": {
            "package_hash": package_hash,
            "member_ids": ["capability.fixture-0"],
        },
        "package_hash": package_hash,
        "lineage_head_hash": lineage_head,
        "member_ids": ["capability.fixture-0", "capability.fixture-1"],
    }
    if layer.chained:
        bundle[entry_digest_field] = entries[-1][entry_digest_field]
    return bundle


def differential_proof(
    repo_path: Path | None = None,
    layer_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Prove the engine is digest-equivalent to the legacy per-plane code.

    For every registered layer (or the given subset), against the same
    synthetic parent bundle:

    1. spec derivation equality with the legacy derive function
    2. per-entry equality (roots, digests, certificates) with the legacy
       transition loop, modulo wall-clock fields
    3. cross chain verification: each implementation accepts the other's log
    4. bundle equality with the legacy bundle builder modulo wall-clock fields
    5. cross bundle integrity: each implementation's integrity verifier
       accepts the other's bundle
    6. adversarial agreement: tampered roots, reordered entries, height gaps,
       wrong parent binding, forged genesis parent, and broken certificates
       are rejected by both implementations
    """

    from blackhole_agent import capability_compounder as legacy

    names = list(layer_names) if layer_names else list(LAYERS)
    with _frozen_clock():
        layer_results = [
            _differential_proof_layer(legacy, get_layer(name)) for name in names
        ]
    ok = all(item["ok"] for item in layer_results) and not _skill_route_used()
    result: dict[str, Any] = {
        "ok": ok,
        "action": "plane_engine_differential_proof",
        "layer_count": len(layer_results),
        "layers": layer_results,
        "used_skill_route_discovery": _skill_route_used(),
    }
    if repo_path is not None and ok:
        out_dir = (Path(repo_path) / "artifacts" / "plane-engine").resolve()
        bundle_paths: list[str] = []
        for item in layer_results:
            bundle = item.get("_bundle")
            if not isinstance(bundle, Mapping):
                continue
            bundle_path = write_bundle(
                out_dir / f"proof-{item['layer']}.json", bundle
            )
            tip_cert = bundle.get(f"{item['layer']}_certificate") or {}
            write_certificate(out_dir / f"certificate-{item['layer']}.json", tip_cert)
            bundle_paths.append(str(bundle_path))
        result["bundle_paths"] = bundle_paths
    for item in layer_results:
        item.pop("_bundle", None)
    return result


def _differential_proof_layer(legacy: Any, layer: PlaneLayer) -> dict[str, Any]:
    """Run the six differential checks for one layer under a frozen clock."""

    L = layer.name
    P = layer.parent
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        parent = _synthetic_parent_bundle(layer, legacy)

        # 1. Spec derivation equality.
        derive_fn = _legacy_fn(
            legacy,
            layer.legacy_derive,
            f"derive_{L}_specs_from_{P}",
        )
        derive_params = inspect.signature(derive_fn).parameters
        min_kwarg = next((p for p in derive_params if p.startswith("min_")), None)
        legacy_specs = derive_fn(parent, **({min_kwarg: 2} if min_kwarg else {}))
        engine_specs = derive_specs(layer, parent, min_count=2)
        record(
            "spec_derivation_equal",
            normalize_volatile(legacy_specs) == normalize_volatile(engine_specs)
            and len(engine_specs) >= 2,
            f"legacy={len(legacy_specs)} engine={len(engine_specs)}",
        )

        # 2. Transition equality entry by entry.
        legacy_empty = _legacy_fn(legacy, f"empty_{L}_log")
        legacy_apply = _legacy_fn(legacy, f"apply_{L}_transition")
        apply_params = inspect.signature(legacy_apply).parameters
        bundle_kwarg = next(p for p in apply_params if p.endswith("_bundle"))
        legacy_log = legacy_empty()
        engine_log = empty_log(layer)
        transitions_equal = True
        detail = ""
        for index, spec in enumerate(legacy_specs):
            goal = f"{parent.get('goal')} (clearing {index + 1})"
            claims = {"clearing_index": index + 1, "plane": L}
            legacy_result = legacy_apply(
                legacy_log, spec, goal=goal, claims=claims, **{bundle_kwarg: parent}
            )
            engine_result = apply_transition(
                layer, engine_log, spec, parent_bundle=parent, goal=goal, claims=claims
            )
            if not legacy_result.get("ok") or not engine_result.get("ok"):
                transitions_equal = False
                detail = (
                    f"apply failed legacy={legacy_result.get('error')}"
                    f" engine={engine_result.get('error')}"
                )
                break
            if normalize_volatile(legacy_result["entry"]) != normalize_volatile(
                engine_result["entry"]
            ):
                transitions_equal = False
                detail = f"entry[{index}] mismatch"
                break
            legacy_log = legacy_result[f"{L}_log"]
            engine_log = engine_result["log"]
        record(
            "transitions_equal",
            transitions_equal
            and normalize_volatile(legacy_log) == normalize_volatile(engine_log),
            detail or f"entries={len(engine_log.get('entries') or [])}",
        )

        # 3. Cross chain verification.
        legacy_chain_fn = _legacy_fn(legacy, f"verify_{L}_chain")
        legacy_chain_own = legacy_chain_fn(legacy_log)
        engine_chain_own = verify_chain(layer, engine_log)
        legacy_chain_engine = legacy_chain_fn(engine_log)
        engine_chain_legacy = verify_chain(layer, legacy_log)
        record(
            "cross_chain_verification",
            bool(legacy_chain_own.get("valid"))
            and bool(engine_chain_own.get("valid"))
            and bool(legacy_chain_engine.get("valid"))
            and bool(engine_chain_legacy.get("valid")),
            f"tip={engine_chain_own.get(f'tip_{L}_root')}",
        )

        # 4. Bundle equality and 5. cross integrity.
        goal = f"{L} over {P}"
        legacy_build = _legacy_fn(legacy, f"build_{L}_bundle")
        legacy_bundle = legacy_build(legacy_log, parent, goal=goal)
        engine_bundle = build_bundle(layer, engine_log, parent, goal=goal)
        record(
            "bundles_equal",
            normalize_volatile(legacy_bundle) == normalize_volatile(engine_bundle),
            f"{L}_hash={engine_bundle.get(f'{L}_hash')}",
        )
        legacy_integrity = _legacy_fn(legacy, f"verify_{L}_bundle_integrity")
        parent_cert_verifier = _legacy_fn(
            legacy, f"verify_{layer.hash_parent}_certificate"
        )
        legacy_accepts_engine = legacy_integrity(engine_bundle)
        engine_accepts_legacy = verify_bundle_integrity(
            layer,
            legacy_bundle,
            parent_certificate_verifier=parent_cert_verifier,
        )
        record(
            "cross_bundle_integrity",
            bool(legacy_accepts_engine.get("ok"))
            and bool(engine_accepts_legacy.get("ok")),
            f"legacy_ok={legacy_accepts_engine.get('ok')}"
            f" engine_ok={engine_accepts_legacy.get('ok')}",
        )

        # 6. Adversarial agreement on mutations of the engine log.
        mutations: dict[str, dict[str, Any]] = {}
        tampered = copy.deepcopy(engine_log)
        tampered["entries"][1][f"{L}_root"] = "f" * 24
        mutations["tampered_root"] = tampered
        reordered = copy.deepcopy(engine_log)
        reordered["entries"] = [reordered["entries"][1], reordered["entries"][0]]
        mutations["reordered_entries"] = reordered
        gapped = copy.deepcopy(engine_log)
        gapped["entries"][1][f"{L}_height"] = 5
        mutations["height_gap"] = gapped
        wrong_binding = copy.deepcopy(engine_log)
        wrong_binding["entries"][0][f"bound_{layer.bind}_root"] = "0" * 24
        mutations["wrong_parent_binding"] = wrong_binding
        forged = copy.deepcopy(engine_log)
        forged["entries"][0][f"parent_{L}_root"] = "a" * 24
        mutations["forged_genesis_parent"] = forged
        broken_cert = copy.deepcopy(engine_log)
        broken_cert["entries"][0][f"{L}_certificate"][f"{L}_root"] = "b" * 24
        mutations["broken_certificate"] = broken_cert

        adversarial_ok = True
        adversarial_detail: list[str] = []
        for name, mutated in mutations.items():
            engine_verdict = verify_chain(layer, mutated)
            legacy_verdict = legacy_chain_fn(mutated)
            agreed = (not engine_verdict.get("valid")) and (
                not legacy_verdict.get("valid")
            )
            adversarial_ok = adversarial_ok and agreed
            adversarial_detail.append(f"{name}:{'reject' if agreed else 'ACCEPTED'}")
        record("adversarial_agreement", adversarial_ok, ",".join(adversarial_detail))

        ok = all(check["ok"] for check in checks) and not _skill_route_used()
        return {
            "ok": ok,
            "layer": L,
            "parent": P,
            "checks": checks,
            f"tip_{L}_root": engine_chain_own.get(f"tip_{L}_root"),
            f"{L}_hash": engine_bundle.get(f"{L}_hash"),
            "_bundle": engine_bundle,
        }
    except Exception as exc:  # report the layer as failed, keep proof going
        record("exception", False, f"{type(exc).__name__}: {exc}")
        return {"ok": False, "layer": L, "parent": P, "checks": checks}


def builtin_plane_engine() -> dict[str, Any]:
    """Invocable capability entry: run the differential proof and persist evidence."""

    repo_path = Path(__file__).resolve().parents[2]
    return differential_proof(repo_path)


FULL_STACK_LAYER_COUNT = 42


def builtin_plane_engine_full_stack() -> dict[str, Any]:
    """Prove the engine covers the entire settlement..cosmos plane stack.

    Full-stack means every token-renamed plane layer generated by the legacy
    dynasty (42 layers: settlement through cosmos) is registered in ``LAYERS``
    and passes the six-check differential proof against the legacy code it
    replaces.
    """

    repo_path = Path(__file__).resolve().parents[2]
    result = differential_proof(repo_path)
    covered = sorted(LAYERS)
    ok = bool(result.get("ok")) and len(covered) == FULL_STACK_LAYER_COUNT
    return {
        "ok": ok,
        "action": "plane_engine_full_stack_proof",
        "layer_count": len(covered),
        "required_layer_count": FULL_STACK_LAYER_COUNT,
        "layers": covered,
        "differential_ok": bool(result.get("ok")),
        "used_skill_route_discovery": _skill_route_used(),
    }
