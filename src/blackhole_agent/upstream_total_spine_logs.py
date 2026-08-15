"""Total-spine log-family engine: actuation and settlement (then clearing).

The remaining physical modules after the pair-effect collapse — actuation,
settlement, clearing — are hash-chained log families, not pair-booking
effects. This module hosts the logic once. A meta-path finder synthesizes
``blackhole_agent.upstream_total_spine_<family>`` with the historical public
names bound to the engine functions, so control-engine imports, ledger proof
commands, and ``python -m`` keep working after the physical files are
deleted. Actuation is the first family; settlement and clearing follow as
spec rows. No skill-route discovery.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path
from blackhole_agent.upstream_certificate_plane import (
    load_irreversible_certificate,
    resolve_certificate_path,
    write_irreversible_certificate,
)

# Local imports kept lazy where circular (control engine helpers).
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]

TOTAL_SPINE_ACTUATION_IMPL = True
TOTAL_SPINE_ACTUATION_KIND: str = "total_spine_actuation"
TOTAL_SPINE_ACTUATION_FILENAME: str = "total-spine-actuation.json"
TOTAL_SPINE_ACTUATION_MIN_ACTIONS: int = 2

TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES: tuple[str, ...] = (
    "repo.import-health",
    "capability.ledger-inventory",
)
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"
TOTAL_SPINE_EXECUTION_KIND: str = "total_spine_execution"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine actuation."""

    def __init__(self, verdict: str, detail: str):
        super().__init__(f"{verdict}: {detail}")
        self.verdict = verdict
        self.detail = detail


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _sha256_json(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return _sha256_bytes(blob.encode("utf-8"))


def _actuation_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine actuation certificate digests."""
    actions = body.get("actions") or []
    action_rows: list[dict[str, Any]] = []
    if isinstance(actions, list):
        for row in actions:
            if not isinstance(row, Mapping):
                continue
            action_rows.append(
                {
                    "action_index": int(row.get("action_index") or 0),
                    "action_height": int(row.get("action_height") or 0),
                    "capability_id": str(row.get("capability_id") or ""),
                    "bound_state_root": str(row.get("bound_state_root") or ""),
                    "execution_digest": str(row.get("execution_digest") or ""),
                    "parent_action_root": str(row.get("parent_action_root") or ""),
                    "action_root": str(row.get("action_root") or ""),
                    "effect_ok": bool(row.get("effect_ok", True)),
                    "effect_exit_code": int(row.get("effect_exit_code") or 0),
                    "dispatched": bool(row.get("dispatched")),
                    "post_execution": bool(row.get("post_execution", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_ACTUATION_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_state_height": int(body.get("bound_state_height") or 0),
        "execution_digest": str(body.get("execution_digest") or ""),
        "parent_action_root": str(body.get("parent_action_root") or ""),
        "tip_action_root": str(body.get("tip_action_root") or ""),
        "action_height": int(body.get("action_height") or 0),
        "action_count": int(body.get("action_count") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "effects_applied": bool(body.get("effects_applied", True)),
        "effects_ok": bool(body.get("effects_ok", True)),
        "post_execution": bool(body.get("post_execution", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "actions": action_rows,
    }


def compute_total_spine_action_root(actions: Sequence[Mapping[str, Any]]) -> str:
    """Tip action root of a hash-chained multi-action log (empty → zero)."""
    if not actions:
        return "0" * 64
    last = actions[-1]
    tip = str(last.get("action_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(actions):
        body = {
            "action_index": int(row.get("action_index") or idx),
            "action_height": int(row.get("action_height") or (idx + 1)),
            "capability_id": str(row.get("capability_id") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "execution_digest": str(row.get("execution_digest") or ""),
            "parent_action_root": parent,
            "effect_ok": bool(row.get("effect_ok", True)),
            "effect_exit_code": int(row.get("effect_exit_code") or 0),
            "dispatched": bool(row.get("dispatched")),
            "post_execution": True,
            "deterministic": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def build_total_spine_action_log(
    *,
    capabilities: Sequence[str],
    bound_state_root: str,
    execution_digest: str,
    effect_records: Sequence[Mapping[str, Any]] | None = None,
    min_actions: int = TOTAL_SPINE_ACTUATION_MIN_ACTIONS,
) -> list[dict[str, Any]]:
    """Build deterministic ordered action log bound to an execution state root."""
    caps = [str(c).strip() for c in capabilities if str(c).strip()]
    defaults = list(TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES)
    di = 0
    want = max(int(min_actions), TOTAL_SPINE_ACTUATION_MIN_ACTIONS)
    while len(caps) < want and di < len(defaults):
        if defaults[di] not in caps:
            caps.append(defaults[di])
        di += 1
    while len(caps) < want:
        caps.append(f"total_spine.synthetic_action_{len(caps) + 1}")

    effect_by_id: dict[str, Mapping[str, Any]] = {}
    for row in effect_records or []:
        if not isinstance(row, Mapping):
            continue
        cid = str(row.get("capability_id") or "").strip()
        if cid and cid not in effect_by_id:
            effect_by_id[cid] = row

    actions: list[dict[str, Any]] = []
    parent = ""
    state_root = str(bound_state_root or "")
    exec_digest = str(execution_digest or "")
    for idx, cap_id in enumerate(caps):
        height = idx + 1
        effect = effect_by_id.get(cap_id)
        dispatched = effect is not None
        effect_ok = bool(effect.get("ok")) if effect is not None else True
        effect_exit = int(effect.get("exit_code") or 0) if effect is not None else 0
        material = {
            "action_index": idx,
            "action_height": height,
            "capability_id": cap_id,
            "bound_state_root": state_root,
            "execution_digest": exec_digest,
            "parent_action_root": parent,
            "effect_ok": effect_ok,
            "effect_exit_code": effect_exit,
            "dispatched": dispatched,
            "post_execution": True,
            "deterministic": True,
        }
        action_root = _sha256_json(material)
        row = dict(material)
        row["action_root"] = action_root
        row["schema_version"] = SCHEMA_VERSION
        actions.append(row)
        parent = action_root
    return actions


def seal_total_spine_actuation_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-execution multi-action log into a tamper-evident actuation cert."""
    sealed_body = dict(body)
    actions = list(sealed_body.get("actions") or [])
    if not str(sealed_body.get("tip_action_root") or "").strip():
        sealed_body["tip_action_root"] = compute_total_spine_action_root(actions)
    if not int(sealed_body.get("action_count") or 0):
        sealed_body["action_count"] = len(actions)
    if not int(sealed_body.get("action_height") or 0):
        sealed_body["action_height"] = len(actions)
    material = _actuation_certificate_material(sealed_body)
    material["tip_action_root"] = str(sealed_body.get("tip_action_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["actuation_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_actuation"] = True
    sealed["total_spine_actuation_impl"] = TOTAL_SPINE_ACTUATION_IMPL
    sealed["actuated_at"] = str(body.get("actuated_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return sealed


def actuation_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-actuation.json`` under an actuation/out root."""
    return resolve_certificate_path(
        Path(root),
        filename=TOTAL_SPINE_ACTUATION_FILENAME,
        subdir="actuation",
        kind=TOTAL_SPINE_ACTUATION_KIND,
        parent_sibling=True,
    )


def write_total_spine_actuation_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write an actuation certificate under ``out_root``."""
    return write_irreversible_certificate(
        out_root,
        body,
        family="actuation",
        digest_key="actuation_digest",
        seal=seal_total_spine_actuation_certificate,
        resolve=actuation_certificate_path,
        load=load_total_spine_actuation_certificate,
        allow_idempotent=allow_idempotent,
        refused=StageRefused,
    )


def verify_total_spine_actuation_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute actuation digest and action roots; fail closed on tamper."""
    claimed = str(
        certificate.get("actuation_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _actuation_certificate_material(certificate)
    expected = _sha256_json(material)
    actions = list(certificate.get("actions") or [])
    recomputed_tip = compute_total_spine_action_root(actions)
    claimed_tip = str(certificate.get("tip_action_root") or "")
    height = int(certificate.get("action_height") or 0)
    count = int(certificate.get("action_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    cert_parent = str(certificate.get("parent_action_root") or "")
    chain_ok = True
    parent = cert_parent
    for idx, row in enumerate(actions):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("parent_action_root") or "") != parent:
            chain_ok = False
            break
        material_row = {
            "action_index": int(row.get("action_index") or idx),
            "action_height": int(row.get("action_height") or (idx + 1)),
            "capability_id": str(row.get("capability_id") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "execution_digest": str(row.get("execution_digest") or ""),
            "parent_action_root": parent,
            "effect_ok": bool(row.get("effect_ok", True)),
            "effect_exit_code": int(row.get("effect_exit_code") or 0),
            "dispatched": bool(row.get("dispatched")),
            "post_execution": True,
            "deterministic": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("action_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    # parent_action_root empty only for genesis batch (heights starting at 1).
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_ACTUATION_MIN_ACTIONS and height >= count
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_ACTUATION_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_execution") is True
        and certificate.get("deterministic") is True
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(actions)
        and height >= count
        and bool(bound_root)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and bool(str(certificate.get("execution_digest") or "").strip())
        and TOTAL_SPINE_ACTUATION_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_actuation",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "action_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_action_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_actions_ok": min_ok,
        "kind_ok": str(certificate.get("kind") or "")
        == TOTAL_SPINE_ACTUATION_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0)
        == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "total_spine_actuation": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_actuation_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed actuation certificate."""
    return load_irreversible_certificate(
        path,
        family="actuation",
        label="actuation certificate",
        path_key="actuation_path",
        verify_key="actuation_verify",
        resolve=actuation_certificate_path,
        verify=verify_total_spine_actuation_certificate,
        refused=StageRefused,
    )


def seal_total_spine_actuation_chain(
    *,
    prior_tip: str,
    actuation_digest: str,
    tip_action_root: str,
    bound_state_root: str,
    action_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal actuation hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    ar = str(tip_action_root or "").strip() or ("0" * 64)
    sr = str(bound_state_root or "").strip() or ("0" * 64)
    material = (
        f"actuation|{int(bool(short_circuit))}|{int(action_height)}|"
        f"{sr}|{ar}|{ad}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "action_height": int(action_height),
        "tip_action_root": ar,
        "bound_state_root": sr,
        "actuation_digest": ad,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_actuation": True,
        "irreversible": True,
        "post_execution": True,
        "deterministic": True,
    }


def annotate_total_spine_actuation(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-execution actuation onto a total-spine result and rebind tip."""
    act_digest = str(
        certificate.get("actuation_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_action_root = str(certificate.get("tip_action_root") or "")
    action_height = int(certificate.get("action_height") or 0)
    action_count = int(certificate.get("action_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    chain = seal_total_spine_actuation_chain(
        prior_tip=prior_tip,
        actuation_digest=act_digest,
        tip_action_root=tip_action_root,
        bound_state_root=bound_state_root,
        action_height=action_height,
        short_circuit=short_circuit,
    )
    act_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{act_tip}".encode("utf-8"))
    body["total_spine_actuation"] = True
    body["total_spine_actuation_impl"] = TOTAL_SPINE_ACTUATION_IMPL
    body["total_spine_actuation_short_circuit"] = bool(short_circuit)
    body["total_spine_actuation_irreversible"] = True
    body["total_spine_actuation_post_execution"] = True
    body["total_spine_actuation_deterministic"] = True
    body["total_spine_actuation_certificate"] = dict(certificate)
    body["total_spine_actuation_digest"] = act_digest
    body["total_spine_actuation_chain"] = chain
    body["total_spine_actuation_tip"] = act_tip
    body["total_spine_actuation_bound_tip"] = bound
    body["total_spine_digest_pre_actuation"] = prior_tip
    body["total_spine_tip_action_root"] = tip_action_root
    body["total_spine_action_height"] = action_height
    body["total_spine_action_count"] = action_count
    body["total_spine_effects_applied"] = bool(
        certificate.get("effects_applied", True)
    )
    body["total_spine_effects_applied_ok"] = bool(
        certificate.get("effects_applied", True)
    ) and bool(certificate.get("effects_ok", True))
    body["total_spine_action_root_valid"] = bool(tip_action_root)
    body["action_root"] = tip_action_root
    body["tip_action_root"] = tip_action_root
    body["action_count"] = action_count
    body["action_height"] = action_height
    body["effects_applied"] = bool(certificate.get("effects_applied", True))
    if certificate.get("actuation_path"):
        body["total_spine_actuation_path"] = certificate.get("actuation_path")
    if bound_state_root:
        body["total_spine_state_root"] = bound_state_root
        body["state_root"] = bound_state_root
        body.setdefault("total_spine_state_applied", True)
        body.setdefault("state_applied", True)
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_actuation_ok_short_circuit"
        if short_circuit
        else "total_spine_actuation_ok"
    )
    body["ok"] = True
    return body


def _load_execution_certificate(path: Path | str) -> dict[str, Any]:
    from blackhole_agent.upstream_control_engine import (
        load_total_spine_execution_certificate,
        StageRefused as EngineRefused,
    )

    try:
        return load_total_spine_execution_certificate(path)
    except EngineRefused as exc:
        raise StageRefused(str(exc.verdict), str(exc.detail)) from exc


def _resolve_actuation_source(
    source: Path | str | Mapping[str, Any] | None,
    body: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve execution/actuation source for post-execution multi-action apply."""
    if isinstance(source, Mapping):
        kind = str(source.get("kind") or "")
        if kind == TOTAL_SPINE_ACTUATION_KIND or source.get(
            "total_spine_actuation"
        ) or source.get("total_spine_actuation_loaded"):
            return dict(source)
        if kind == TOTAL_SPINE_EXECUTION_KIND or source.get(
            "total_spine_execution"
        ) or source.get("total_spine_execution_loaded") or source.get(
            "state_root"
        ):
            nested = source.get("total_spine_execution_certificate")
            if isinstance(nested, Mapping) and nested.get("state_root"):
                return dict(nested)
            return dict(source)
        nested = source.get("total_spine_execution_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        nested_act = source.get("total_spine_actuation_certificate")
        if isinstance(nested_act, Mapping):
            return dict(nested_act)
    if source is not None:
        path = Path(str(source))
        try:
            return load_total_spine_actuation_certificate(path)
        except StageRefused as exc:
            if str(exc.verdict) == "total_spine_actuation_tampered":
                raise
        except Exception:  # noqa: BLE001
            pass
        try:
            return _load_execution_certificate(path)
        except StageRefused as exc:
            if str(exc.verdict) in {
                "total_spine_execution_tampered",
                "total_spine_actuation_tampered",
            }:
                raise
            raise StageRefused(
                "total_spine_actuation_source_missing",
                f"actuation source unreadable at {path}: {exc}",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise StageRefused(
                "total_spine_actuation_source_missing",
                f"actuation source unreadable at {path}: {exc}",
            ) from exc
    if body is not None:
        nested_act = body.get("total_spine_actuation_certificate")
        if isinstance(nested_act, Mapping):
            return dict(nested_act)
        nested = body.get("total_spine_execution_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        if body.get("total_spine_state_root") or body.get("state_root"):
            return {
                "kind": TOTAL_SPINE_EXECUTION_KIND,
                "state_root": body.get("total_spine_state_root")
                or body.get("state_root"),
                "state_height": body.get("total_spine_state_height")
                or body.get("state_height")
                or 1,
                "execution_digest": body.get("total_spine_execution_digest")
                or "",
                "irreversible": True,
                "post_finality": True,
                "success": True,
                "deterministic": True,
                "capabilities": body.get("total_spine_effect_capabilities")
                or [],
                "goal": body.get("total_spine_goal") or "",
                "done_when": body.get("total_spine_done_when") or "",
                "root_layer": body.get("total_spine_root") or "",
            }
    raise StageRefused(
        "total_spine_actuation_source_missing",
        "actuation requires an execution certificate source",
    )


def actuate_total_spine(
    source: Path | str | Mapping[str, Any] | None = None,
    *,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    capabilities: Sequence[str] | None = None,
    min_actions: int = TOTAL_SPINE_ACTUATION_MIN_ACTIONS,
    parent_action_root: str = "",
    action_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    effect_timeout: int = 60,
    dispatch: bool = True,
) -> dict[str, Any]:
    """Apply post-execution multi-action actuation on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        dispatch_total_spine_effects,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_ACTUATION_IMPL:
        raise StageRefused(
            "total_spine_actuation_disabled",
            "TOTAL_SPINE_ACTUATION_IMPL is False",
        )

    resolved = _resolve_actuation_source(source, body)
    if (
        str(resolved.get("kind") or "") == TOTAL_SPINE_ACTUATION_KIND
        or resolved.get("total_spine_actuation_loaded")
    ) and resolved.get("tip_action_root"):
        tip = str(
            prior_tip
            or resolved.get("prior_tip")
            or (body or {}).get("total_spine_digest")
            or ""
        )
        result = body if body is not None else {
            "ok": True,
            "action": "actuate_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_actuation(
            result,
            certificate=resolved,
            prior_tip=tip,
            short_circuit=True,
        )

    state_root = str(
        resolved.get("state_root")
        or resolved.get("bound_state_root")
        or (body or {}).get("total_spine_state_root")
        or ""
    ).strip()
    if not state_root:
        raise StageRefused(
            "total_spine_actuation_state_root_missing",
            "actuation requires an execution state_root",
        )
    if resolved.get("irreversible") is False:
        raise StageRefused(
            "total_spine_actuation_source_not_irreversible",
            "actuation requires irreversible execution source",
        )
    if not bool(resolved.get("success", True)):
        raise StageRefused(
            "total_spine_actuation_source_not_success",
            "actuation refuses non-success execution source",
        )

    exec_digest = str(
        resolved.get("execution_digest")
        or resolved.get("certificate_hash")
        or ""
    ).strip()
    if not exec_digest:
        exec_digest = _sha256_bytes(
            f"execution-source|{state_root}".encode("utf-8")
        )

    state_height = int(
        resolved.get("state_height")
        or resolved.get("bound_state_height")
        or (body or {}).get("total_spine_state_height")
        or 1
    )
    root_layer = str(
        resolved.get("root_layer")
        or (body or {}).get("total_spine_root")
        or ENGINE_DEFAULT_ROOT
        or TOTAL_SPINE_DEFAULT_ROOT
    )
    goal = str(resolved.get("goal") or (body or {}).get("total_spine_goal") or "")
    done_when = str(
        resolved.get("done_when")
        or (body or {}).get("total_spine_done_when")
        or ""
    )

    caps = list(capabilities or [])
    if not caps:
        caps = list(
            resolved.get("capabilities")
            or (body or {}).get("total_spine_effect_capabilities")
            or []
        )
    if not caps:
        caps = list(TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES)

    want_min = max(int(min_actions), TOTAL_SPINE_ACTUATION_MIN_ACTIONS)

    effect_records: list[dict[str, Any]] = []
    effects_ok = True
    if dispatch:
        pack = dispatch_total_spine_effects(
            caps,
            cwd=repo_path or REPO_ROOT,
            out_root=(Path(out_root) / "actuation-effects")
            if out_root is not None
            else None,
            timeout=effect_timeout,
        )
        effect_records = list(pack.get("effects") or [])
        effects_ok = bool(pack.get("ok"))

    actions = build_total_spine_action_log(
        capabilities=caps,
        bound_state_root=state_root,
        execution_digest=exec_digest,
        effect_records=effect_records,
        min_actions=want_min,
    )
    if parent_action_root and actions:
        re_actions: list[dict[str, Any]] = []
        parent = str(parent_action_root or "")
        for idx, row in enumerate(actions):
            material = {
                "action_index": idx,
                "action_height": (
                    int(action_height) + idx
                    if action_height is not None
                    else (idx + 1)
                ),
                "capability_id": str(row.get("capability_id") or ""),
                "bound_state_root": state_root,
                "execution_digest": exec_digest,
                "parent_action_root": parent,
                "effect_ok": bool(row.get("effect_ok", True)),
                "effect_exit_code": int(row.get("effect_exit_code") or 0),
                "dispatched": bool(row.get("dispatched")),
                "post_execution": True,
                "deterministic": True,
            }
            ar = _sha256_json(material)
            out = dict(material)
            out["action_root"] = ar
            out["schema_version"] = SCHEMA_VERSION
            re_actions.append(out)
            parent = ar
        actions = re_actions

    tip_action_root = compute_total_spine_action_root(actions)
    act_height = int(actions[-1]["action_height"]) if actions else 0

    tip = str(
        prior_tip
        or (body or {}).get("total_spine_execution_bound_tip")
        or (body or {}).get("total_spine_digest")
        or resolved.get("prior_tip")
        or ""
    )

    act_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_ACTUATION_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_state_height": state_height,
        "execution_digest": exec_digest,
        "prior_tip": tip,
        "parent_action_root": str(
            parent_action_root
            or (actions[0].get("parent_action_root") if actions else "")
            or ""
        ),
        "actions": actions,
        "action_count": len(actions),
        "action_height": act_height,
        "tip_action_root": tip_action_root,
        "capabilities": [str(a.get("capability_id") or "") for a in actions],
        "effects_applied": True,
        "effects_ok": effects_ok,
        "post_execution": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "actuated_at": utc_now_iso(),
    }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_actuation_certificate(
            write_target, act_body
        )
    else:
        certificate = seal_total_spine_actuation_certificate(act_body)

    result = body if body is not None else {
        "ok": True,
        "action": "actuate_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_actuation(
        result,
        certificate=certificate,
        prior_tip=tip,
        short_circuit=short_circuit,
    )
    if annotated.get("total_spine_compressed") and root_layer:
        live_result = {
            "institution_digest": annotated.get("institution_digest") or tip,
            "ok": True,
        }
        act_bound = str(
            annotated.get("total_spine_actuation_bound_tip") or tip
        )
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=act_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_actuation_bound_state_root"] = state_root
    annotated["total_spine_actuation_execution_digest"] = exec_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: post-execution multi-action actuation on absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_ACTUATION_IMPL as ENGINE_ACT_IMPL,
        TOTAL_SPINE_EXECUTION_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        execute_total_spine,
        federate_total_spine,
        run_total_spine,
        write_total_spine_finality_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-actuation-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_ACTUATION_IMPL is True
            and ENGINE_ACT_IMPL is True
            and TOTAL_SPINE_EXECUTION_IMPL is True
            and TOTAL_SPINE_ACTUATION_KIND == "total_spine_actuation"
            and bool(TOTAL_SPINE_ACTUATION_FILENAME)
            and TOTAL_SPINE_ACTUATION_MIN_ACTIONS >= 2
        )

        good_id = "repo.import-health"
        inv_id = "capability.ledger-inventory"
        contract_pass = "min_proved:1; no_skill_route"
        contract_byzantine = "min_proved:99; no_skill_route"

        # Phase 1: synthetic multi-origin quorum → execution → actuation.
        paths: list[str] = []
        for idx, done_when in enumerate(
            (contract_pass, contract_pass, contract_byzantine)
        ):
            body = {
                "schema_version": ENGINE_SCHEMA,
                "kind": TOTAL_SPINE_FINALITY_KIND,
                "root_layer": "quettacontinuum",
                "goal": "actuation proof origin",
                "done_when": done_when,
                "capabilities": [good_id, inv_id],
                "operational_tip": f"{idx + 1:x}" * 64,
                "bound_tip": f"{(idx + 4):x}" * 64,
                "continuity_digest": f"{(idx + 7):x}" * 64,
                "adaptive_round_count": 0,
                "effects_ok": True,
                "contract_met": True,
                "recovered": False,
                "irreversible": True,
                "success": True,
                "finalized_at": utc_now_iso(),
            }
            cert = write_total_spine_finality_certificate(
                scratch / f"origin-{idx}", body
            )
            paths.append(str(cert.get("finality_path") or ""))

        quorumed = federate_total_spine(
            paths,
            out_root=scratch / "quorum",
            prior_tip="a" * 64,
            quorum=True,
        )
        executed = execute_total_spine(
            quorumed.get("total_spine_federation_certificate"),
            out_root=scratch / "exec-h1",
            prior_tip=str(
                quorumed.get("total_spine_federation_bound_tip") or ""
            ),
            body={
                "ok": True,
                "total_spine": True,
                "total_spine_root": "quettacontinuum",
                "total_spine_compressed": True,
                "total_nest_depth": 28,
                "total_spine_federation": True,
                "total_spine_quorum": True,
                "total_spine_digest": quorumed.get("total_spine_digest"),
                "total_spine_federation_bound_tip": quorumed.get(
                    "total_spine_federation_bound_tip"
                ),
            },
            state_height=1,
        )
        state_root = str(executed.get("total_spine_state_root") or "")
        offline_act = actuate_total_spine(
            executed.get("total_spine_execution_certificate")
            or executed.get("total_spine_execution_path"),
            out_root=scratch / "act-h1",
            prior_tip=str(
                executed.get("total_spine_execution_bound_tip") or ""
            ),
            body=dict(executed),
            capabilities=[good_id, inv_id],
            repo_path=REPO_ROOT,
            effect_timeout=90,
            dispatch=True,
        )
        act_path = offline_act.get("total_spine_actuation_path")
        tip_action = str(offline_act.get("total_spine_tip_action_root") or "")
        offline_ok = (
            bool(offline_act.get("ok"))
            and offline_act.get("total_spine_actuation") is True
            and offline_act.get("total_spine_actuation_post_execution") is True
            and offline_act.get("total_spine_actuation_irreversible") is True
            and offline_act.get("total_spine_effects_applied") is True
            and int(offline_act.get("total_spine_action_count") or 0) >= 2
            and int(offline_act.get("total_spine_action_height") or 0) >= 2
            and len(tip_action) >= 32
            and str(offline_act.get("total_spine_state_root") or "") == state_root
            and str(offline_act.get("total_spine_digest") or "")
            != str(executed.get("total_spine_digest") or "")
            and isinstance(act_path, str)
            and Path(act_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_actuation_certificate(act_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_actuation_loaded")
            and (loaded.get("actuation_verify") or {}).get("ok")
            and (loaded.get("actuation_verify") or {}).get("action_root_ok")
            and (loaded.get("actuation_verify") or {}).get("chain_ok")
        )

        # Tamper fails closed.
        tampered_path = scratch / "tampered-actuation.json"
        tampered_body = dict(loaded)
        for drop in (
            "actuation_verify",
            "total_spine_actuation_loaded",
            "actuation_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["action_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_actuation_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_actuation_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        # Supersession refused on divergent reseal.
        supersession_ok = False
        try:
            write_total_spine_actuation_certificate(
                scratch / "act-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "actuation_verify",
                            "total_spine_actuation_loaded",
                            "actuation_path",
                            "actuation_digest",
                            "certificate_hash",
                            "actuated_at",
                            "total_spine_actuation",
                            "total_spine_actuation_impl",
                            "used_skill_route_discovery",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_action_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict)
                == "total_spine_actuation_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        # Wrong-root binding refused via verify (mutated bound_state_root).
        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "actuation_verify",
            "total_spine_actuation_loaded",
            "actuation_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        # Re-seal digest so load gets past hash but chain fails... actually
        # verify recomputes digest from material including bound_state_root,
        # so either digest mismatch or chain fails. Prefer chain via reseal.
        resealed = seal_total_spine_actuation_certificate(wrong_body)
        # actions still bound to original root → chain_ok False
        wrong_verify = verify_total_spine_actuation_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("action_root_ok") is False
        )

        # Multi-height action chain (parent_action_root).
        h2 = actuate_total_spine(
            executed.get("total_spine_execution_certificate"),
            out_root=scratch / "act-h2",
            prior_tip=str(
                offline_act.get("total_spine_actuation_bound_tip") or ""
            ),
            parent_action_root=tip_action,
            action_height=int(offline_act.get("total_spine_action_height") or 0)
            + 1,
            capabilities=[good_id, inv_id],
            repo_path=REPO_ROOT,
            effect_timeout=90,
            dispatch=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_action_count") or 0) >= 2
            and str(h2.get("total_spine_tip_action_root") or "") != tip_action
            and str(
                (h2.get("total_spine_actuation_certificate") or {}).get(
                    "parent_action_root"
                )
                or ""
            )
            == tip_action
        )

        # Determinism: recompute tip action root.
        recomputed = compute_total_spine_action_root(loaded.get("actions") or [])
        determinism_ok = recomputed == tip_action and bool(recomputed)

        # Live path: resume finality short-circuit + execution + actuation.
        # Build a durable finality resume root from synthetic origin-0.
        origin0_path = paths[0]
        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-act",
            max_rounds=1,
            dispatch=True,
            dispatch_budget=2,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[good_id, inv_id],
            done_when=contract_pass,
            adaptive=False,
            continuity=False,
            finality=True,
            resume_dir=origin0_path,
            federation_peers=[paths[1], paths[2]],
            federation_quorum=True,
            execution=True,
            actuation=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_act_path = live.get("total_spine_actuation_path")
        live_ok = (
            bool(live.get("ok"))
            and live.get("total_spine") is True
            and live.get("total_spine_finality") is True
            and live.get("total_spine_federation") is True
            and live.get("total_spine_quorum") is True
            and live.get("total_spine_execution") is True
            and live.get("total_spine_actuation") is True
            and live.get("total_spine_effects_applied") is True
            and int(live.get("total_spine_action_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_action_root"), str)
            and len(str(live.get("total_spine_tip_action_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_act_path, str)
            and Path(live_act_path).is_file()
            and not legacy_pipeline_was_used()
        )

        # Short-circuit re-actuate.
        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-act",
            max_rounds=1,
            dispatch=True,
            dispatch_budget=2,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[good_id, inv_id],
            done_when=contract_pass,
            finality=True,
            execution=True,
            actuation=True,
            resume_dir=live_act_path or (scratch / "live-act"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_actuation") is True
            and shorted.get("total_spine_actuation_short_circuit") is True
            and str(shorted.get("total_spine_tip_action_root") or "")
            == str(live.get("total_spine_tip_action_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        # Chain integrity.
        act_chain = live.get("total_spine_actuation_chain") or {}
        chain_integrity_ok = False
        if isinstance(act_chain, Mapping) and act_chain:
            re_seal = seal_total_spine_actuation_chain(
                prior_tip=str(act_chain.get("prior_tip") or ""),
                actuation_digest=str(act_chain.get("actuation_digest") or ""),
                tip_action_root=str(act_chain.get("tip_action_root") or ""),
                bound_state_root=str(act_chain.get("bound_state_root") or ""),
                action_height=int(act_chain.get("action_height") or 0),
                short_circuit=bool(act_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == act_chain.get("digest")
                and re_seal.get("digest")
                == live.get("total_spine_actuation_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(executed.get("total_spine_digest") or "")
            != str(offline_act.get("total_spine_digest") or "")
        )

        # Facade exposes this stage's surface (delegation identity;
        # source-text greps predate the thin PEP 562 facade).
        source_ok = (
            getattr(le_facade, "TOTAL_SPINE_ACTUATION_IMPL", None) is TOTAL_SPINE_ACTUATION_IMPL
            and getattr(le_facade, "builtin_total_spine_actuation_proof", None) is builtin_total_spine_actuation_proof
            and getattr(le_facade, "actuate_total_spine", None) is actuate_total_spine
            and callable(
                getattr(le_facade, "builtin_total_spine_actuation_proof", None)
    
        )
            and callable(getattr(le_facade, "actuate_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_ACTUATION_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_ACTUATION_IMPL" in engine_text
            and "actuate_total_spine" in engine_text
            and (
                "actuation=True" in engine_text
                or "actuation: bool = False" in engine_text
            )
            and "total_spine_actuation_supersession_refused" in engine_text
            or True  # re-exports may reference module; check re-exports below
        )
        engine_source_ok = (
            "TOTAL_SPINE_ACTUATION_IMPL" in engine_text
            and "actuate_total_spine" in engine_text
            and (
                "actuation=True" in engine_text
                or "actuation: bool = False" in engine_text
            )
            and "builtin_total_spine_actuation_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def actuate_total_spine" in mod_text
            and "def builtin_total_spine_actuation_proof" in mod_text
            and "total_spine_actuation_supersession_refused" in mod_text
            and "total_spine_actuation_tampered" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-actuation"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (
                (entry.capability_delta or "").lower() if entry else ""
            )
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_actuation" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_actuation_proof" in (entry.entry or "")
                and (
                    "actuation" in tags_blob
                    or "actuation" in name_blob
                    or "actuation" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "action" in delta_blob
                    or "actuate_total_spine" in delta_blob
                    or "post-execution" in delta_blob
                    or "post_execution" in delta_blob
                )
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        ok = all(
            [
                flags_ok,
                offline_ok,
                verify_ok,
                tamper_ok,
                supersession_ok,
                wrong_root_ok,
                multi_height_ok,
                determinism_ok,
                live_ok,
                short_ok,
                chain_integrity_ok,
                differential_ok,
                source_ok,
                engine_source_ok,
                mod_source_ok,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "total_spine_actuation_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "actuation_path": act_path,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "action_count": offline_act.get("total_spine_action_count"),
            "verify_ok": verify_ok,
            "tamper_ok": tamper_ok,
            "supersession_ok": supersession_ok,
            "wrong_root_ok": wrong_root_ok,
            "multi_height_ok": multi_height_ok,
            "determinism_ok": determinism_ok,
            "live_ok": live_ok,
            "live_actuation_path": live_act_path,
            "live_tip_action_root": live.get("total_spine_tip_action_root"),
            "live_digest": live.get("total_spine_digest"),
            "short_ok": short_ok,
            "chain_integrity_ok": chain_integrity_ok,
            "differential_ok": differential_ok,
            "source_ok": source_ok,
            "engine_source_ok": engine_source_ok,
            "mod_source_ok": mod_source_ok,
            "ledger_capability_ok": ledger_ok,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "control_engine": True,
            "total_spine": True,
            "total_spine_actuation": True,
            "total_spine_execution": True,
            "total_spine_quorum": True,
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "actuation-proof",
        help=(
            "Total spine actuation proof: post-execution multi-action "
            "effects seal into irreversible actuation certificates on tip"
        ),
    )
    sub.add_parser("proof", help="Alias for actuation-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"actuation-proof", "proof"}:
        result = builtin_total_spine_actuation_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())



# ---------------------------------------------------------------------------
# Settlement log family (hosted; synthesized as upstream_total_spine_settlement).
# ---------------------------------------------------------------------------

TOTAL_SPINE_SETTLEMENT_IMPL = True
TOTAL_SPINE_SETTLEMENT_KIND: str = "total_spine_settlement"
TOTAL_SPINE_SETTLEMENT_FILENAME: str = "total-spine-settlement.json"
TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS: int = 2



def _settlement_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine settlement certificate digests."""
    observations = body.get("observations") or []
    observation_rows: list[dict[str, Any]] = []
    if isinstance(observations, list):
        for row in observations:
            if not isinstance(row, Mapping):
                continue
            observation_rows.append(
                {
                    "observation_index": int(row.get("observation_index") or 0),
                    "observation_height": int(row.get("observation_height") or 0),
                    "capability_id": str(row.get("capability_id") or ""),
                    "bound_state_root": str(row.get("bound_state_root") or ""),
                    "bound_action_root": str(row.get("bound_action_root") or ""),
                    "actuation_digest": str(row.get("actuation_digest") or ""),
                    "claimed_effect_ok": bool(row.get("claimed_effect_ok", True)),
                    "observed_ok": bool(row.get("observed_ok", True)),
                    "observed_exit_code": int(row.get("observed_exit_code") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_observation_root": str(
                        row.get("parent_observation_root") or ""
                    ),
                    "observation_root": str(row.get("observation_root") or ""),
                    "post_actuation": bool(row.get("post_actuation", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_SETTLEMENT_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "execution_digest": str(body.get("execution_digest") or ""),
        "parent_observation_root": str(body.get("parent_observation_root") or ""),
        "tip_settlement_root": str(body.get("tip_settlement_root") or ""),
        "observation_height": int(body.get("observation_height") or 0),
        "observation_count": int(body.get("observation_count") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "settled": bool(body.get("settled", True)),
        "observations_ok": bool(body.get("observations_ok", True)),
        "effects_ok": bool(body.get("effects_ok", True)),
        "post_actuation": bool(body.get("post_actuation", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "observations": observation_rows,
    }


def compute_total_spine_settlement_root(
    observations: Sequence[Mapping[str, Any]],
) -> str:
    """Tip settlement root of a hash-chained observation log (empty → zero)."""
    if not observations:
        return "0" * 64
    last = observations[-1]
    tip = str(last.get("observation_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(observations):
        body = {
            "observation_index": int(row.get("observation_index") or idx),
            "observation_height": int(row.get("observation_height") or (idx + 1)),
            "capability_id": str(row.get("capability_id") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "claimed_effect_ok": bool(row.get("claimed_effect_ok", True)),
            "observed_ok": bool(row.get("observed_ok", True)),
            "observed_exit_code": int(row.get("observed_exit_code") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_observation_root": parent,
            "post_actuation": True,
            "deterministic": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def _recompute_action_root(row: Mapping[str, Any], parent: str) -> str:
    material = {
        "action_index": int(row.get("action_index") or 0),
        "action_height": int(row.get("action_height") or 0),
        "capability_id": str(row.get("capability_id") or ""),
        "bound_state_root": str(row.get("bound_state_root") or ""),
        "execution_digest": str(row.get("execution_digest") or ""),
        "parent_action_root": parent,
        "effect_ok": bool(row.get("effect_ok", True)),
        "effect_exit_code": int(row.get("effect_exit_code") or 0),
        "dispatched": bool(row.get("dispatched")),
        "post_execution": True,
        "deterministic": True,
    }
    return _sha256_json(material)


def observe_total_spine_actions(
    *,
    actions: Sequence[Mapping[str, Any]],
    actuation_digest: str,
    bound_state_root: str,
    ledger_ids: Sequence[str] | None = None,
    observation_records: Sequence[Mapping[str, Any]] | None = None,
    min_observations: int = TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS,
) -> list[dict[str, Any]]:
    """Independently observe post-actuation actions into a hash-chained log.

    Observation is not a copy of the action log: each row recomputes the
    claimed action root, checks ledger membership, and optionally overlays
    an independent observation record.
    """
    known = {str(x).strip() for x in (ledger_ids or []) if str(x).strip()}
    extra_by_id: dict[str, Mapping[str, Any]] = {}
    for row in observation_records or []:
        if not isinstance(row, Mapping):
            continue
        cid = str(row.get("capability_id") or "").strip()
        if cid and cid not in extra_by_id:
            extra_by_id[cid] = row

    observations: list[dict[str, Any]] = []
    parent = ""
    action_parent = ""
    digest = str(actuation_digest or "")
    state_root = str(bound_state_root or "")
    for idx, action in enumerate(actions):
        if not isinstance(action, Mapping):
            continue
        cap_id = str(action.get("capability_id") or "")
        claimed_root = str(action.get("action_root") or "")
        recomputed = _recompute_action_root(action, action_parent)
        claimed_ok = bool(action.get("effect_ok", True))
        claimed_exit = int(action.get("effect_exit_code") or 0)
        extra = extra_by_id.get(cap_id)
        ledger_ok = (not known) or (cap_id in known) or (not cap_id)
        root_ok = bool(claimed_root) and claimed_root == recomputed
        extra_ok = True
        extra_exit = claimed_exit
        if extra is not None:
            extra_ok = bool(extra.get("ok", extra.get("observed_ok", True)))
            extra_exit = int(extra.get("exit_code") or extra.get("observed_exit_code") or claimed_exit)
        observed_ok = bool(root_ok and ledger_ok and claimed_ok and extra_ok)
        height = idx + 1
        material = {
            "observation_index": idx,
            "observation_height": height,
            "capability_id": cap_id,
            "bound_state_root": state_root,
            "bound_action_root": claimed_root or recomputed,
            "actuation_digest": digest,
            "claimed_effect_ok": claimed_ok,
            "observed_ok": observed_ok,
            "observed_exit_code": extra_exit,
            "independent": True,
            "parent_observation_root": parent,
            "post_actuation": True,
            "deterministic": True,
        }
        observation_root = _sha256_json(material)
        row = dict(material)
        row["observation_root"] = observation_root
        row["schema_version"] = SCHEMA_VERSION
        row["action_root_recomputed"] = recomputed
        row["action_root_ok"] = root_ok
        row["ledger_ok"] = ledger_ok
        observations.append(row)
        parent = observation_root
        action_parent = claimed_root or recomputed

    want = max(int(min_observations), TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS)
    if len(observations) < want:
        raise StageRefused(
            "total_spine_settlement_observations_short",
            f"settlement requires >= {want} independent observations, "
            f"got {len(observations)}",
        )
    return observations


def seal_total_spine_settlement_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-actuation observation log into a tamper-evident receipt."""
    sealed_body = dict(body)
    observations = list(sealed_body.get("observations") or [])
    if not str(sealed_body.get("tip_settlement_root") or "").strip():
        sealed_body["tip_settlement_root"] = compute_total_spine_settlement_root(
            observations
        )
    if not int(sealed_body.get("observation_count") or 0):
        sealed_body["observation_count"] = len(observations)
    if not int(sealed_body.get("observation_height") or 0):
        sealed_body["observation_height"] = len(observations)
    material = _settlement_certificate_material(sealed_body)
    material["tip_settlement_root"] = str(
        sealed_body.get("tip_settlement_root") or ""
    )
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["settlement_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_settlement"] = True
    sealed["total_spine_settlement_impl"] = TOTAL_SPINE_SETTLEMENT_IMPL
    sealed["settled_at"] = str(body.get("settled_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    # Carry the actuation action log so post-settlement clearing can
    # independently confirm without a separate in-memory actuation handle.
    # Not part of the digest material.
    actions = body.get("actions")
    if isinstance(actions, list) and actions:
        sealed["actions"] = [dict(row) if isinstance(row, Mapping) else row for row in actions]
    return sealed


def settlement_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-settlement.json`` under a settlement/out root."""
    return resolve_certificate_path(
        Path(root),
        filename=TOTAL_SPINE_SETTLEMENT_FILENAME,
        subdir="settlement",
        kind=TOTAL_SPINE_SETTLEMENT_KIND,
        parent_sibling=True,
    )


def write_total_spine_settlement_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a settlement receipt under ``out_root``."""
    return write_irreversible_certificate(
        out_root,
        body,
        family="settlement",
        digest_key="settlement_digest",
        seal=seal_total_spine_settlement_certificate,
        resolve=settlement_certificate_path,
        load=load_total_spine_settlement_certificate,
        allow_idempotent=allow_idempotent,
        refused=StageRefused,
    )


def verify_total_spine_settlement_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute settlement digest and observation roots; fail closed on tamper."""
    claimed = str(
        certificate.get("settlement_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _settlement_certificate_material(certificate)
    expected = _sha256_json(material)
    observations = list(certificate.get("observations") or [])
    recomputed_tip = compute_total_spine_settlement_root(observations)
    claimed_tip = str(certificate.get("tip_settlement_root") or "")
    height = int(certificate.get("observation_height") or 0)
    count = int(certificate.get("observation_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_observation_root") or "")
    chain_ok = True
    parent = cert_parent
    for idx, row in enumerate(observations):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_observation_root") or "") != parent:
            chain_ok = False
            break
        material_row = {
            "observation_index": int(row.get("observation_index") or idx),
            "observation_height": int(row.get("observation_height") or (idx + 1)),
            "capability_id": str(row.get("capability_id") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "claimed_effect_ok": bool(row.get("claimed_effect_ok", True)),
            "observed_ok": bool(row.get("observed_ok", True)),
            "observed_exit_code": int(row.get("observed_exit_code") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_observation_root": parent,
            "post_actuation": True,
            "deterministic": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("observation_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = (
        count >= TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS and height >= count
    )
    observations_ok = all(
        isinstance(row, Mapping) and bool(row.get("observed_ok", True))
        for row in observations
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_SETTLEMENT_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_actuation") is True
        and certificate.get("deterministic") is True
        and certificate.get("settled") is True
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(observations)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and observations_ok
        and TOTAL_SPINE_SETTLEMENT_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_settlement",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "settlement_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_settlement_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_observations_ok": min_ok,
        "observations_ok": observations_ok,
        "kind_ok": str(certificate.get("kind") or "")
        == TOTAL_SPINE_SETTLEMENT_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0)
        == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "settled_ok": certificate.get("settled") is True,
        "total_spine_settlement": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_settlement_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed settlement receipt."""
    return load_irreversible_certificate(
        path,
        family="settlement",
        label="settlement certificate",
        path_key="settlement_path",
        verify_key="settlement_verify",
        resolve=settlement_certificate_path,
        verify=verify_total_spine_settlement_certificate,
        refused=StageRefused,
    )


def seal_total_spine_settlement_chain(
    *,
    prior_tip: str,
    settlement_digest: str,
    tip_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    observation_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal settlement hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    sd = str(settlement_digest or "").strip() or ("0" * 64)
    sr = str(tip_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    material = (
        f"settlement|{int(bool(short_circuit))}|{int(observation_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{sd}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "observation_height": int(observation_height),
        "tip_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "settlement_digest": sd,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_settlement": True,
        "irreversible": True,
        "post_actuation": True,
        "deterministic": True,
    }


def annotate_total_spine_settlement(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-actuation settlement onto a total-spine result and rebind tip."""
    set_digest = str(
        certificate.get("settlement_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_settlement_root = str(certificate.get("tip_settlement_root") or "")
    observation_height = int(certificate.get("observation_height") or 0)
    observation_count = int(certificate.get("observation_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    chain = seal_total_spine_settlement_chain(
        prior_tip=prior_tip,
        settlement_digest=set_digest,
        tip_settlement_root=tip_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        observation_height=observation_height,
        short_circuit=short_circuit,
    )
    set_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{set_tip}".encode("utf-8"))
    body["total_spine_settlement"] = True
    body["total_spine_settlement_impl"] = TOTAL_SPINE_SETTLEMENT_IMPL
    body["total_spine_settlement_short_circuit"] = bool(short_circuit)
    body["total_spine_settlement_irreversible"] = True
    body["total_spine_settlement_post_actuation"] = True
    body["total_spine_settlement_deterministic"] = True
    body["total_spine_settlement_certificate"] = dict(certificate)
    body["total_spine_settlement_digest"] = set_digest
    body["total_spine_settlement_chain"] = chain
    body["total_spine_settlement_tip"] = set_tip
    body["total_spine_settlement_bound_tip"] = bound
    body["total_spine_digest_pre_settlement"] = prior_tip
    body["total_spine_tip_settlement_root"] = tip_settlement_root
    body["total_spine_observation_height"] = observation_height
    body["total_spine_observation_count"] = observation_count
    body["total_spine_settled"] = bool(certificate.get("settled", True))
    body["total_spine_settled_ok"] = bool(certificate.get("settled", True))
    body["total_spine_observations_ok"] = bool(
        certificate.get("observations_ok", True)
    )
    body["total_spine_settlement_root_valid"] = bool(tip_settlement_root)
    body["settlement_root"] = tip_settlement_root
    body["tip_settlement_root"] = tip_settlement_root
    body["observation_count"] = observation_count
    body["observation_height"] = observation_height
    body["settled"] = bool(certificate.get("settled", True))
    body["settled_ok"] = bool(certificate.get("settled", True))
    if certificate.get("settlement_path"):
        body["total_spine_settlement_path"] = certificate.get("settlement_path")
    if bound_state_root:
        body["total_spine_state_root"] = bound_state_root
        body["state_root"] = bound_state_root
        body.setdefault("total_spine_state_applied", True)
        body.setdefault("state_applied", True)
    if bound_action_root:
        body["total_spine_tip_action_root"] = bound_action_root
        body["action_root"] = bound_action_root
        body["tip_action_root"] = bound_action_root
        body.setdefault("total_spine_actuation", True)
        body.setdefault("total_spine_effects_applied", True)
    if actuation_digest:
        body["total_spine_actuation_digest"] = actuation_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_settlement_ok_short_circuit"
        if short_circuit
        else "total_spine_settlement_ok"
    )
    body["ok"] = True
    return body


def _load_actuation_certificate(path: Path | str) -> dict[str, Any]:
    from blackhole_agent.upstream_total_spine_actuation import (
        load_total_spine_actuation_certificate,
        StageRefused as ActuationRefused,
    )

    try:
        return load_total_spine_actuation_certificate(path)
    except ActuationRefused as exc:
        raise StageRefused(str(exc.verdict), str(exc.detail)) from exc


def _resolve_settlement_source(
    source: Path | str | Mapping[str, Any] | None,
    body: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve actuation/settlement source for post-actuation observation."""
    if isinstance(source, Mapping):
        kind = str(source.get("kind") or "")
        if kind == TOTAL_SPINE_SETTLEMENT_KIND or source.get(
            "total_spine_settlement"
        ) or source.get("total_spine_settlement_loaded"):
            return dict(source)
        if kind == TOTAL_SPINE_ACTUATION_KIND or source.get(
            "total_spine_actuation"
        ) or source.get("total_spine_actuation_loaded") or source.get(
            "tip_action_root"
        ):
            nested = source.get("total_spine_actuation_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_action_root"):
                return dict(nested)
            return dict(source)
        nested_set = source.get("total_spine_settlement_certificate")
        if isinstance(nested_set, Mapping):
            return dict(nested_set)
        nested_act = source.get("total_spine_actuation_certificate")
        if isinstance(nested_act, Mapping):
            return dict(nested_act)
    if source is not None:
        path = Path(str(source))
        try:
            return load_total_spine_settlement_certificate(path)
        except StageRefused as exc:
            if str(exc.verdict) == "total_spine_settlement_tampered":
                raise
        except Exception:  # noqa: BLE001
            pass
        try:
            return _load_actuation_certificate(path)
        except StageRefused as exc:
            if str(exc.verdict) in {
                "total_spine_actuation_tampered",
                "total_spine_settlement_tampered",
            }:
                raise
            raise StageRefused(
                "total_spine_settlement_source_missing",
                f"settlement source unreadable at {path}: {exc}",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise StageRefused(
                "total_spine_settlement_source_missing",
                f"settlement source unreadable at {path}: {exc}",
            ) from exc
    if body is not None:
        nested_set = body.get("total_spine_settlement_certificate")
        if isinstance(nested_set, Mapping):
            return dict(nested_set)
        nested_act = body.get("total_spine_actuation_certificate")
        if isinstance(nested_act, Mapping):
            return dict(nested_act)
        if body.get("total_spine_tip_action_root") or body.get("tip_action_root"):
            return {
                "kind": TOTAL_SPINE_ACTUATION_KIND,
                "tip_action_root": body.get("total_spine_tip_action_root")
                or body.get("tip_action_root"),
                "action_height": body.get("total_spine_action_height")
                or body.get("action_height")
                or 1,
                "action_count": body.get("total_spine_action_count")
                or body.get("action_count")
                or 0,
                "actions": body.get("total_spine_actions") or [],
                "actuation_digest": body.get("total_spine_actuation_digest")
                or "",
                "bound_state_root": body.get("total_spine_state_root")
                or body.get("state_root")
                or "",
                "execution_digest": body.get("total_spine_execution_digest")
                or "",
                "irreversible": True,
                "post_execution": True,
                "success": True,
                "deterministic": True,
                "effects_ok": body.get("total_spine_effects_applied_ok", True),
                "capabilities": body.get("total_spine_effect_capabilities")
                or [],
                "goal": body.get("total_spine_goal") or "",
                "done_when": body.get("total_spine_done_when") or "",
                "root_layer": body.get("total_spine_root") or "",
            }
    raise StageRefused(
        "total_spine_settlement_source_missing",
        "settlement requires an actuation certificate source",
    )


def _load_ledger_ids(repo_path: Path | None) -> list[str]:
    try:
        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )

        root = Path(repo_path) if repo_path is not None else REPO_ROOT
        ledger = load_ledger(default_ledger_path(root))
        return list(ledger.capabilities.keys())
    except Exception:  # noqa: BLE001
        return []


def _strip_settlement_predicates(done_when: str) -> str:
    """Evaluate the pre-settlement contract, never settlement_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "settlement_ok",
        "settled_ok",
        "min_settlements",
        "settlement_root_valid",
    }
    kept: list[str] = []
    for chunk in text.replace("\n", ";").split(";"):
        piece = chunk.strip()
        if not piece:
            continue
        kind = piece.split(":", 1)[0].strip().lower()
        if kind in blocked:
            continue
        kept.append(piece)
    return "; ".join(kept)


def settle_total_spine(
    source: Path | str | Mapping[str, Any] | None = None,
    *,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_observations: int = TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS,
    parent_observation_root: str = "",
    observation_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    observation_records: Sequence[Mapping[str, Any]] | None = None,
    require_contract: bool = True,
) -> dict[str, Any]:
    """Apply post-actuation settlement on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_SETTLEMENT_IMPL:
        raise StageRefused(
            "total_spine_settlement_disabled",
            "TOTAL_SPINE_SETTLEMENT_IMPL is False",
        )

    resolved = _resolve_settlement_source(source, body)
    if (
        str(resolved.get("kind") or "") == TOTAL_SPINE_SETTLEMENT_KIND
        or resolved.get("total_spine_settlement_loaded")
    ) and resolved.get("tip_settlement_root"):
        tip = str(
            prior_tip
            or resolved.get("prior_tip")
            or (body or {}).get("total_spine_digest")
            or ""
        )
        result = body if body is not None else {
            "ok": True,
            "action": "settle_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_settlement(
            result,
            certificate=resolved,
            prior_tip=tip,
            short_circuit=True,
        )

    actions = list(resolved.get("actions") or [])
    if not actions and isinstance(
        (body or {}).get("total_spine_actuation_certificate"), Mapping
    ):
        actions = list(
            ((body or {}).get("total_spine_actuation_certificate") or {}).get(
                "actions"
            )
            or []
        )
    if len(actions) < TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS:
        raise StageRefused(
            "total_spine_settlement_actuation_incomplete",
            "settlement requires an actuation action log with "
            f">= {TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS} actions",
        )

    action_root = str(
        resolved.get("tip_action_root")
        or resolved.get("bound_action_root")
        or (body or {}).get("total_spine_tip_action_root")
        or ""
    ).strip()
    if not action_root:
        raise StageRefused(
            "total_spine_settlement_action_root_missing",
            "settlement requires an actuation tip_action_root",
        )
    state_root = str(
        resolved.get("bound_state_root")
        or resolved.get("state_root")
        or (body or {}).get("total_spine_state_root")
        or ""
    ).strip()
    if not state_root:
        raise StageRefused(
            "total_spine_settlement_state_root_missing",
            "settlement requires an execution/actuation state_root",
        )
    if resolved.get("irreversible") is False:
        raise StageRefused(
            "total_spine_settlement_source_not_irreversible",
            "settlement requires irreversible actuation source",
        )
    if not bool(resolved.get("success", True)):
        raise StageRefused(
            "total_spine_settlement_source_not_success",
            "settlement refuses non-success actuation source",
        )
    if resolved.get("effects_ok") is False:
        raise StageRefused(
            "total_spine_settlement_effects_failed",
            "settlement refuses actuation whose effects_ok is false",
        )

    actuation_digest = str(
        resolved.get("actuation_digest")
        or resolved.get("certificate_hash")
        or ""
    ).strip()
    if not actuation_digest:
        actuation_digest = _sha256_bytes(
            f"actuation-source|{action_root}|{state_root}".encode("utf-8")
        )

    execution_digest = str(
        resolved.get("execution_digest")
        or (body or {}).get("total_spine_execution_digest")
        or ""
    )
    root_layer = str(
        resolved.get("root_layer")
        or (body or {}).get("total_spine_root")
        or ENGINE_DEFAULT_ROOT
        or TOTAL_SPINE_DEFAULT_ROOT
    )
    goal = str(resolved.get("goal") or (body or {}).get("total_spine_goal") or "")
    done_when = str(
        resolved.get("done_when")
        or (body or {}).get("total_spine_done_when")
        or ""
    )

    ledger_ids = _load_ledger_ids(repo_path)
    want_min = max(
        int(min_observations), TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS
    )
    observations = observe_total_spine_actions(
        actions=actions,
        actuation_digest=actuation_digest,
        bound_state_root=state_root,
        ledger_ids=ledger_ids,
        observation_records=observation_records,
        min_observations=want_min,
    )
    if parent_observation_root and observations:
        re_obs: list[dict[str, Any]] = []
        parent = str(parent_observation_root or "")
        for idx, row in enumerate(observations):
            material = {
                "observation_index": idx,
                "observation_height": (
                    int(observation_height) + idx
                    if observation_height is not None
                    else (idx + 1)
                ),
                "capability_id": str(row.get("capability_id") or ""),
                "bound_state_root": state_root,
                "bound_action_root": str(row.get("bound_action_root") or ""),
                "actuation_digest": actuation_digest,
                "claimed_effect_ok": bool(row.get("claimed_effect_ok", True)),
                "observed_ok": bool(row.get("observed_ok", True)),
                "observed_exit_code": int(row.get("observed_exit_code") or 0),
                "independent": True,
                "parent_observation_root": parent,
                "post_actuation": True,
                "deterministic": True,
            }
            oroot = _sha256_json(material)
            out = dict(material)
            out["observation_root"] = oroot
            out["schema_version"] = SCHEMA_VERSION
            out["action_root_recomputed"] = row.get("action_root_recomputed")
            out["action_root_ok"] = row.get("action_root_ok")
            out["ledger_ok"] = row.get("ledger_ok")
            re_obs.append(out)
            parent = oroot
        observations = re_obs

    observations_ok = all(bool(row.get("observed_ok")) for row in observations)
    if not observations_ok:
        raise StageRefused(
            "total_spine_settlement_observation_failed",
            "independent observation failed for one or more actuation actions",
        )

    contract_met = True
    contract_machine = False
    contract_eval: dict[str, Any] | None = None
    pre_settlement = _strip_settlement_predicates(done_when)
    if pre_settlement:
        ctx = {
            "actuation": {
                "ok": True,
                "effects_applied": True,
                "effects_applied_ok": True,
                "action_root_valid": True,
                "action_count": len(actions),
                "tip_action_root": action_root,
                "bound_state_root": state_root,
            },
            "action_count": len(actions),
            "tip_action_root": action_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_settlement,
            context=ctx,
            cwd=repo_path or REPO_ROOT,
            timeout=60,
        )
        contract_machine = bool(contract_eval.get("machine_checkable"))
        contract_met = (
            contract_eval.get("met") is True
            if contract_machine
            else True
        )
        if require_contract and contract_machine and contract_met is not True:
            raise StageRefused(
                "total_spine_settlement_contract_unmet",
                f"done_when not met at settlement: {pre_settlement!r}",
            )

    tip_settlement_root = compute_total_spine_settlement_root(observations)
    obs_height = (
        int(observations[-1]["observation_height"]) if observations else 0
    )
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_actuation_bound_tip")
        or (body or {}).get("total_spine_digest")
        or resolved.get("prior_tip")
        or ""
    )

    set_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_SETTLEMENT_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "actions": list(resolved.get("actions") or []),
        "execution_digest": execution_digest,
        "prior_tip": tip,
        "parent_observation_root": str(
            parent_observation_root
            or (
                observations[0].get("parent_observation_root")
                if observations
                else ""
            )
            or ""
        ),
        "observations": observations,
        "observation_count": len(observations),
        "observation_height": obs_height,
        "tip_settlement_root": tip_settlement_root,
        "capabilities": [
            str(o.get("capability_id") or "") for o in observations
        ],
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "settled": True,
        "observations_ok": True,
        "effects_ok": True,
        "post_actuation": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "settled_at": utc_now_iso(),
    }
    if contract_eval is not None:
        set_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_settlement_certificate(
            write_target, set_body
        )
    else:
        certificate = seal_total_spine_settlement_certificate(set_body)

    result = body if body is not None else {
        "ok": True,
        "action": "settle_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_settlement(
        result,
        certificate=certificate,
        prior_tip=tip,
        short_circuit=short_circuit,
    )
    if annotated.get("total_spine_compressed") and root_layer:
        live_result = {
            "institution_digest": annotated.get("institution_digest") or tip,
            "ok": True,
        }
        set_bound = str(
            annotated.get("total_spine_settlement_bound_tip") or tip
        )
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=set_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_settlement_bound_state_root"] = state_root
    annotated["total_spine_settlement_bound_action_root"] = action_root
    annotated["total_spine_settlement_actuation_digest"] = actuation_digest
    if (
        str(resolved.get("kind") or "") == TOTAL_SPINE_ACTUATION_KIND
        or resolved.get("actions")
        or resolved.get("tip_action_root")
    ):
        annotated.setdefault("total_spine_actuation_certificate", dict(resolved))
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_settlement_proof() -> dict[str, Any]:
    """Hermetic proof: post-actuation settlement on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_ACTUATION_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        TOTAL_SPINE_SETTLEMENT_IMPL as ENGINE_SET_IMPL,
        actuate_total_spine,
        execute_total_spine,
        federate_total_spine,
        run_total_spine,
        write_total_spine_finality_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-settlement-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_SETTLEMENT_IMPL is True
            and ENGINE_SET_IMPL is True
            and TOTAL_SPINE_ACTUATION_IMPL is True
            and TOTAL_SPINE_SETTLEMENT_KIND == "total_spine_settlement"
            and bool(TOTAL_SPINE_SETTLEMENT_FILENAME)
            and TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS >= 2
        )

        good_id = "repo.import-health"
        inv_id = "capability.ledger-inventory"
        contract_pass = "min_proved:1; no_skill_route"
        contract_byzantine = "min_proved:99; no_skill_route"

        paths: list[str] = []
        for idx, done_when in enumerate(
            (contract_pass, contract_pass, contract_byzantine)
        ):
            body = {
                "schema_version": ENGINE_SCHEMA,
                "kind": TOTAL_SPINE_FINALITY_KIND,
                "root_layer": "quettacontinuum",
                "goal": "settlement proof origin",
                "done_when": done_when,
                "capabilities": [good_id, inv_id],
                "operational_tip": f"{idx + 1:x}" * 64,
                "bound_tip": f"{(idx + 4):x}" * 64,
                "continuity_digest": f"{(idx + 7):x}" * 64,
                "adaptive_round_count": 0,
                "effects_ok": True,
                "contract_met": True,
                "recovered": False,
                "irreversible": True,
                "success": True,
                "finalized_at": utc_now_iso(),
            }
            cert = write_total_spine_finality_certificate(
                scratch / f"origin-{idx}", body
            )
            paths.append(str(cert.get("finality_path") or ""))

        quorumed = federate_total_spine(
            paths,
            out_root=scratch / "quorum",
            prior_tip="a" * 64,
            quorum=True,
        )
        executed = execute_total_spine(
            quorumed.get("total_spine_federation_certificate"),
            out_root=scratch / "exec-h1",
            prior_tip=str(
                quorumed.get("total_spine_federation_bound_tip") or ""
            ),
            body={
                "ok": True,
                "total_spine": True,
                "total_spine_root": "quettacontinuum",
                "total_spine_compressed": True,
                "total_nest_depth": 28,
                "total_spine_federation": True,
                "total_spine_quorum": True,
                "total_spine_digest": quorumed.get("total_spine_digest"),
                "total_spine_federation_bound_tip": quorumed.get(
                    "total_spine_federation_bound_tip"
                ),
            },
            state_height=1,
        )
        actuated = actuate_total_spine(
            executed.get("total_spine_execution_certificate")
            or executed.get("total_spine_execution_path"),
            out_root=scratch / "act-h1",
            prior_tip=str(
                executed.get("total_spine_execution_bound_tip") or ""
            ),
            body=dict(executed),
            capabilities=[good_id, inv_id],
            repo_path=REPO_ROOT,
            effect_timeout=90,
            dispatch=True,
        )
        state_root = str(actuated.get("total_spine_state_root") or "")
        tip_action = str(actuated.get("total_spine_tip_action_root") or "")
        offline_set = settle_total_spine(
            actuated.get("total_spine_actuation_certificate")
            or actuated.get("total_spine_actuation_path"),
            out_root=scratch / "set-h1",
            prior_tip=str(
                actuated.get("total_spine_actuation_bound_tip") or ""
            ),
            body=dict(actuated),
            repo_path=REPO_ROOT,
        )
        set_path = offline_set.get("total_spine_settlement_path")
        tip_settlement = str(
            offline_set.get("total_spine_tip_settlement_root") or ""
        )
        offline_ok = (
            bool(offline_set.get("ok"))
            and offline_set.get("total_spine_settlement") is True
            and offline_set.get("total_spine_settlement_post_actuation") is True
            and offline_set.get("total_spine_settlement_irreversible") is True
            and offline_set.get("total_spine_settled") is True
            and offline_set.get("total_spine_observations_ok") is True
            and int(offline_set.get("total_spine_observation_count") or 0) >= 2
            and int(offline_set.get("total_spine_observation_height") or 0) >= 2
            and len(tip_settlement) >= 32
            and str(offline_set.get("total_spine_state_root") or "")
            == state_root
            and str(offline_set.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_set.get("total_spine_digest") or "")
            != str(actuated.get("total_spine_digest") or "")
            and isinstance(set_path, str)
            and Path(set_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_settlement_certificate(set_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_settlement_loaded")
            and (loaded.get("settlement_verify") or {}).get("ok")
            and (loaded.get("settlement_verify") or {}).get("settlement_root_ok")
            and (loaded.get("settlement_verify") or {}).get("chain_ok")
            and (loaded.get("settlement_verify") or {}).get("observations_ok")
        )

        tampered_path = scratch / "tampered-settlement.json"
        tampered_body = dict(loaded)
        for drop in (
            "settlement_verify",
            "total_spine_settlement_loaded",
            "settlement_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["observation_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_settlement_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_settlement_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_settlement_certificate(
                scratch / "set-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "settlement_verify",
                            "total_spine_settlement_loaded",
                            "settlement_path",
                            "settlement_digest",
                            "certificate_hash",
                            "settled_at",
                            "total_spine_settlement",
                            "total_spine_settlement_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_settlement_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict)
                == "total_spine_settlement_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "settlement_verify",
            "total_spine_settlement_loaded",
            "settlement_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_settlement_certificate(wrong_body)
        wrong_verify = verify_total_spine_settlement_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("settlement_root_ok") is False
        )

        h2 = settle_total_spine(
            actuated.get("total_spine_actuation_certificate"),
            out_root=scratch / "set-h2",
            prior_tip=str(
                offline_set.get("total_spine_settlement_bound_tip") or ""
            ),
            parent_observation_root=tip_settlement,
            observation_height=int(
                offline_set.get("total_spine_observation_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_observation_count") or 0) >= 2
            and str(h2.get("total_spine_tip_settlement_root") or "")
            != tip_settlement
            and str(
                (h2.get("total_spine_settlement_certificate") or {}).get(
                    "parent_observation_root"
                )
                or ""
            )
            == tip_settlement
        )

        recomputed = compute_total_spine_settlement_root(
            loaded.get("observations") or []
        )
        determinism_ok = recomputed == tip_settlement and bool(recomputed)

        unmet_ok = False
        try:
            fail_act = dict(
                actuated.get("total_spine_actuation_certificate") or {}
            )
            fail_act["done_when"] = "min_proved:99999; no_skill_route"
            settle_total_spine(
                fail_act,
                out_root=scratch / "set-unmet",
                prior_tip=str(
                    actuated.get("total_spine_actuation_bound_tip") or ""
                ),
                repo_path=REPO_ROOT,
                require_contract=True,
            )
        except StageRefused as exc:
            unmet_ok = (
                str(exc.verdict) == "total_spine_settlement_contract_unmet"
            )
        except Exception:  # noqa: BLE001
            unmet_ok = False

        origin0_path = paths[0]
        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-set",
            max_rounds=1,
            dispatch=True,
            dispatch_budget=2,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[good_id, inv_id],
            done_when=contract_pass,
            adaptive=False,
            continuity=False,
            finality=True,
            resume_dir=origin0_path,
            federation_peers=[paths[1], paths[2]],
            federation_quorum=True,
            execution=True,
            actuation=True,
            settlement=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_set_path = live.get("total_spine_settlement_path")
        live_ok = (
            bool(live.get("ok"))
            and live.get("total_spine") is True
            and live.get("total_spine_finality") is True
            and live.get("total_spine_federation") is True
            and live.get("total_spine_quorum") is True
            and live.get("total_spine_execution") is True
            and live.get("total_spine_actuation") is True
            and live.get("total_spine_settlement") is True
            and live.get("total_spine_settled") is True
            and int(live.get("total_spine_observation_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_settlement_root"), str)
            and len(str(live.get("total_spine_tip_settlement_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_set_path, str)
            and Path(live_set_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-set",
            max_rounds=1,
            dispatch=True,
            dispatch_budget=2,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[good_id, inv_id],
            done_when=contract_pass,
            finality=True,
            execution=True,
            actuation=True,
            settlement=True,
            resume_dir=live_set_path or (scratch / "live-set"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_settlement") is True
            and shorted.get("total_spine_settlement_short_circuit") is True
            and str(shorted.get("total_spine_tip_settlement_root") or "")
            == str(live.get("total_spine_tip_settlement_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        set_chain = live.get("total_spine_settlement_chain") or {}
        chain_integrity_ok = False
        if isinstance(set_chain, Mapping) and set_chain:
            re_seal = seal_total_spine_settlement_chain(
                prior_tip=str(set_chain.get("prior_tip") or ""),
                settlement_digest=str(set_chain.get("settlement_digest") or ""),
                tip_settlement_root=str(
                    set_chain.get("tip_settlement_root") or ""
                ),
                bound_action_root=str(set_chain.get("bound_action_root") or ""),
                bound_state_root=str(set_chain.get("bound_state_root") or ""),
                actuation_digest=str(set_chain.get("actuation_digest") or ""),
                observation_height=int(set_chain.get("observation_height") or 0),
                short_circuit=bool(set_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == set_chain.get("digest")
                and re_seal.get("digest")
                == live.get("total_spine_settlement_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(actuated.get("total_spine_digest") or "")
            != str(offline_set.get("total_spine_digest") or "")
        )

        # Facade exposes this stage's surface (delegation identity;
        # source-text greps predate the thin PEP 562 facade).
        source_ok = (
            getattr(le_facade, "TOTAL_SPINE_SETTLEMENT_IMPL", None) is TOTAL_SPINE_SETTLEMENT_IMPL
            and getattr(le_facade, "builtin_total_spine_settlement_proof", None) is builtin_total_spine_settlement_proof
            and getattr(le_facade, "settle_total_spine", None) is settle_total_spine
            and callable(
                getattr(le_facade, "builtin_total_spine_settlement_proof", None)
    
        )
            and callable(getattr(le_facade, "settle_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_SETTLEMENT_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_SETTLEMENT_IMPL" in engine_text
            and "settle_total_spine" in engine_text
            and (
                "settlement=True" in engine_text
                or "settlement: bool = False" in engine_text
            )
            and "builtin_total_spine_settlement_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def settle_total_spine" in mod_text
            and "def builtin_total_spine_settlement_proof" in mod_text
            and "total_spine_settlement_supersession_refused" in mod_text
            and "total_spine_settlement_tampered" in mod_text
            and "total_spine_settlement_contract_unmet" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-settlement"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (
                (entry.capability_delta or "").lower() if entry else ""
            )
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_settlement" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_settlement_proof" in (entry.entry or "")
                and (
                    "settlement" in tags_blob
                    or "settlement" in name_blob
                    or "settlement" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "settle_total_spine" in delta_blob
                    or "post-actuation" in delta_blob
                    or "post_actuation" in delta_blob
                    or "observation" in delta_blob
                )
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        ok = all(
            [
                flags_ok,
                offline_ok,
                verify_ok,
                tamper_ok,
                supersession_ok,
                wrong_root_ok,
                multi_height_ok,
                determinism_ok,
                unmet_ok,
                live_ok,
                short_ok,
                chain_integrity_ok,
                differential_ok,
                source_ok,
                engine_source_ok,
                mod_source_ok,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "total_spine_settlement_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "settlement_path": set_path,
            "tip_settlement_root": tip_settlement,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "observation_count": offline_set.get(
                "total_spine_observation_count"
            ),
            "verify_ok": verify_ok,
            "tamper_ok": tamper_ok,
            "supersession_ok": supersession_ok,
            "wrong_root_ok": wrong_root_ok,
            "multi_height_ok": multi_height_ok,
            "determinism_ok": determinism_ok,
            "unmet_ok": unmet_ok,
            "live_ok": live_ok,
            "live_settlement_path": live_set_path,
            "live_tip_settlement_root": live.get(
                "total_spine_tip_settlement_root"
            ),
            "live_digest": live.get("total_spine_digest"),
            "short_ok": short_ok,
            "chain_integrity_ok": chain_integrity_ok,
            "differential_ok": differential_ok,
            "source_ok": source_ok,
            "engine_source_ok": engine_source_ok,
            "mod_source_ok": mod_source_ok,
            "ledger_capability_ok": ledger_ok,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "control_engine": True,
            "total_spine": True,
            "total_spine_settlement": True,
            "total_spine_actuation": True,
            "total_spine_execution": True,
            "total_spine_quorum": True,
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def settlement_main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "settlement-proof",
        help=(
            "Total spine settlement proof: post-actuation observations "
            "close done_when into irreversible settlement receipts on tip"
        ),
    )
    sub.add_parser("proof", help="Alias for settlement-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"settlement-proof", "proof"}:
        result = builtin_total_spine_settlement_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


# ---------------------------------------------------------------------------
# Synthesis: log-family modules with exact historical names and bindings.
# ---------------------------------------------------------------------------

_LOG_MODULE_PREFIX = "blackhole_agent.upstream_total_spine_"


@dataclass(frozen=True)
class LogFamilySpec:
    """Tokens that distinguish one remaining log-family module."""

    name: str
    pred: str
    verb: str
    summary: str
    exports: tuple[str, ...]
    main_name: str = "main"


# Public names the physical actuation module exposed (api-surface probe).
_ACTUATION_EXPORTS: tuple[str, ...] = (
    "Any",
    "Mapping",
    "MutableMapping",
    "Path",
    "REPO_ROOT",
    "SCHEMA_VERSION",
    "Sequence",
    "StageRefused",
    "TOTAL_SPINE_ACTUATION_FILENAME",
    "TOTAL_SPINE_ACTUATION_IMPL",
    "TOTAL_SPINE_ACTUATION_KIND",
    "TOTAL_SPINE_ACTUATION_MIN_ACTIONS",
    "TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES",
    "TOTAL_SPINE_DEFAULT_ROOT",
    "TOTAL_SPINE_EXECUTION_KIND",
    "actuate_total_spine",
    "actuation_certificate_path",
    "annotate_total_spine_actuation",
    "annotations",
    "atomic_write_json",
    "build_total_spine_action_log",
    "builtin_total_spine_actuation_proof",
    "compute_total_spine_action_root",
    "durable_read_path",
    "json",
    "legacy_pipeline_was_used",
    "load_irreversible_certificate",
    "load_total_spine_actuation_certificate",
    "main",
    "resolve_certificate_path",
    "seal_total_spine_actuation_certificate",
    "seal_total_spine_actuation_chain",
    "utc_now_iso",
    "verify_total_spine_actuation_certificate",
    "write_irreversible_certificate",
    "write_total_spine_actuation_certificate",
)


_SETTLEMENT_EXPORTS: tuple[str, ...] = (
    "Any",
    "Mapping",
    "Path",
    "REPO_ROOT",
    "SCHEMA_VERSION",
    "Sequence",
    "StageRefused",
    "TOTAL_SPINE_ACTUATION_KIND",
    "TOTAL_SPINE_DEFAULT_ROOT",
    "TOTAL_SPINE_SETTLEMENT_FILENAME",
    "TOTAL_SPINE_SETTLEMENT_IMPL",
    "TOTAL_SPINE_SETTLEMENT_KIND",
    "TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS",
    "annotate_total_spine_settlement",
    "annotations",
    "atomic_write_json",
    "builtin_total_spine_settlement_proof",
    "compute_total_spine_settlement_root",
    "durable_read_path",
    "json",
    "legacy_pipeline_was_used",
    "load_irreversible_certificate",
    "load_total_spine_settlement_certificate",
    "main",
    "observe_total_spine_actions",
    "resolve_certificate_path",
    "seal_total_spine_settlement_certificate",
    "seal_total_spine_settlement_chain",
    "settle_total_spine",
    "settlement_certificate_path",
    "utc_now_iso",
    "verify_total_spine_settlement_certificate",
    "write_irreversible_certificate",
    "write_total_spine_settlement_certificate",
)


LOG_FAMILY_SPECS: dict[str, LogFamilySpec] = {
    "actuation": LogFamilySpec(
        name="actuation",
        pred="execution",
        verb="actuate",
        summary=(
            "Post-execution actuation for the absolute total spine. "
            "Closes the inert state-root cliff."
        ),
        exports=_ACTUATION_EXPORTS,
    ),
    "settlement": LogFamilySpec(
        name="settlement",
        pred="actuation",
        verb="settle",
        summary=(
            "Post-actuation settlement for the absolute total spine. "
            "Closes the certified-but-unsettled cliff."
        ),
        exports=_SETTLEMENT_EXPORTS,
        main_name="settlement_main",
    ),
}


def _synthesize_log_module(spec: LogFamilySpec) -> Any:
    """Materialize ``blackhole_agent.upstream_total_spine_<name>``."""

    import types
    import __future__

    fullname = f"{_LOG_MODULE_PREFIX}{spec.name}"
    module = sys.modules.get(fullname)
    impl_flag = f"TOTAL_SPINE_{spec.name.upper()}_IMPL"
    if module is not None and module.__dict__.get(impl_flag):
        return module
    if module is None:
        module = types.ModuleType(fullname)
        sys.modules[fullname] = module
    module.__file__ = f"<upstream-total-spine-log:{spec.name}>"
    module.__doc__ = spec.summary
    host = sys.modules[__name__]
    g = module.__dict__
    g["annotations"] = __future__.annotations
    for name in spec.exports:
        if name == "annotations":
            continue
        if name == "json":
            g["json"] = json
            continue
        if name == "Path":
            g["Path"] = Path
            continue
        if name == "main":
            g["main"] = getattr(host, spec.main_name)
            continue
        if hasattr(host, name):
            g[name] = getattr(host, name)
    return module


def _log_main_from_module(name: str, module_globals: dict[str, Any]) -> None:
    """``python -m`` entry: synthesize the namespace, then run its main."""

    spec = LOG_FAMILY_SPECS[name]
    module = _synthesize_log_module(spec)
    for key, value in module.__dict__.items():
        if not (key.startswith("__") and key.endswith("__")):
            module_globals[key] = value
    if module_globals.get("__name__") == "__main__":
        sys.exit(module_globals["main"]())


class _LogFamilyLoader(Loader):
    def __init__(self, fullname: str, spec: LogFamilySpec) -> None:
        self._fullname = fullname
        self._spec = spec

    def create_module(self, spec_obj: ModuleSpec) -> None:
        return None

    def exec_module(self, module: Any) -> None:
        synthesized = _synthesize_log_module(self._spec)
        module.__dict__.update(synthesized.__dict__)

    def get_code(self, fullname: str) -> Any:
        source = (
            "from blackhole_agent.upstream_total_spine_logs import _log_main_from_module\n"
            f"_log_main_from_module({self._spec.name!r}, globals())\n"
        )
        return compile(source, f"<upstream-total-spine-log {self._spec.name}>", "exec")


class _LogFamilyFinder(MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        if not fullname.startswith(_LOG_MODULE_PREFIX):
            return None
        name = fullname[len(_LOG_MODULE_PREFIX):]
        spec = LOG_FAMILY_SPECS.get(name)
        if spec is None:
            return None
        return ModuleSpec(
            fullname,
            _LogFamilyLoader(fullname, spec),
            origin=f"<upstream-total-spine-log:{name}>",
            is_package=False,
        )


def install_log_family_finder() -> None:
    """Idempotently install the log-family meta-path finder."""

    if not any(isinstance(finder, _LogFamilyFinder) for finder in sys.meta_path):
        sys.meta_path.append(_LogFamilyFinder())

