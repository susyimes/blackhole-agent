"""Total-spine log-family engine: actuation (then settlement, clearing).

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
    )
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

