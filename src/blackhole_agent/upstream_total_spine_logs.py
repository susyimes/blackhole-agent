"""Total-spine log-family engine: execution, actuation, settlement, clearing.

The pre-pair-effect tower — execution (single-state) plus actuation,
settlement, and clearing (multi-row logs) — is one spec-driven engine.
A meta-path finder synthesizes
``blackhole_agent.upstream_total_spine_<family>`` with the historical public
names bound to the engine functions, so control-engine imports, ledger proof
commands, and ``python -m`` keep working after the physical files are
deleted.

Certificate seal/verify and apply/proof for every log family are one
spec-driven engine (:func:`_seal_log_certificate`,
:func:`_verify_log_certificate`, :func:`_apply_log_family`,
:func:`_run_log_family_proof`). Public seal/verify/apply/proof names stay
as thin wrappers so a new family is a :class:`LogFamilySpec` row (shape
``rows`` or ``state``) plus a build hook, not another control-engine copy.
No skill-route discovery.
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
TOTAL_SPINE_EXECUTION_IMPL = True
TOTAL_SPINE_EXECUTION_KIND: str = "total_spine_execution"
TOTAL_SPINE_EXECUTION_FILENAME: str = "total-spine-execution.json"


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


def _sha256_json_compact(payload: Mapping[str, Any]) -> str:
    """Control-engine canonicalizer: compact separators, no default=str."""
    blob = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
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
    return _seal_log_certificate("actuation", body)


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
    return _verify_log_certificate("actuation", certificate)


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
    return _apply_log_family(
        "actuation",
        source,
        out_root=out_root,
        prior_tip=prior_tip,
        body=body,
        capabilities=capabilities,
        min_actions=min_actions,
        parent_action_root=parent_action_root,
        action_height=action_height,
        short_circuit=short_circuit,
        repo_path=repo_path,
        effect_timeout=effect_timeout,
        dispatch=dispatch,
    )


def _actuation_apply_core(
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
    """Actuation apply core: dispatch effects, build the action log, finish."""
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
        return _short_circuit_log_apply("actuation", resolved, body, prior_tip)

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

    return _finish_log_apply(
        "actuation",
        cert_body=act_body,
        out_root=out_root,
        body=body,
        prior_tip=tip,
        short_circuit=short_circuit,
        extra={
            "total_spine_actuation_bound_state_root": state_root,
            "total_spine_actuation_execution_digest": exec_digest,
        },
    )


def builtin_total_spine_actuation_proof() -> dict[str, Any]:
    """Hermetic proof: post-execution multi-action actuation on absolute tower."""
    return _run_log_family_proof("actuation")



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
    return _seal_log_certificate("settlement", body)


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
    return _verify_log_certificate("settlement", certificate)


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
    return _apply_log_family(
        "settlement",
        source,
        out_root=out_root,
        prior_tip=prior_tip,
        body=body,
        min_observations=min_observations,
        parent_observation_root=parent_observation_root,
        observation_height=observation_height,
        short_circuit=short_circuit,
        repo_path=repo_path,
        observation_records=observation_records,
        require_contract=require_contract,
    )


def _settlement_apply_core(
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
    """Settlement apply core: observe actions, evaluate contract, finish."""
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
        return _short_circuit_log_apply("settlement", resolved, body, prior_tip)

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

    extra: dict[str, Any] = {
        "total_spine_settlement_bound_state_root": state_root,
        "total_spine_settlement_bound_action_root": action_root,
        "total_spine_settlement_actuation_digest": actuation_digest,
    }
    if (
        str(resolved.get("kind") or "") == TOTAL_SPINE_ACTUATION_KIND
        or resolved.get("actions")
        or resolved.get("tip_action_root")
    ):
        extra["setdefault_actuation_certificate"] = dict(resolved)
    return _finish_log_apply(
        "settlement",
        cert_body=set_body,
        out_root=out_root,
        body=body,
        prior_tip=tip,
        short_circuit=short_circuit,
        extra=extra,
    )


def builtin_total_spine_settlement_proof() -> dict[str, Any]:
    """Hermetic proof: post-actuation settlement on the absolute tower."""
    return _run_log_family_proof("settlement")


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
# Clearing log family (hosted; synthesized as upstream_total_spine_clearing).
# ---------------------------------------------------------------------------

TOTAL_SPINE_CLEARING_IMPL = True
TOTAL_SPINE_CLEARING_KIND: str = "total_spine_clearing"
TOTAL_SPINE_CLEARING_FILENAME: str = "total-spine-clearing.json"
TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS: int = 2



def _observation_signature(observations: Sequence[Mapping[str, Any]]) -> str:
    rows: list[dict[str, Any]] = []
    for row in observations:
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "capability_id": str(row.get("capability_id") or ""),
                "observed_ok": bool(row.get("observed_ok", True)),
                "observed_exit_code": int(row.get("observed_exit_code") or 0),
            }
        )
    return _sha256_json({"observations": rows})


def _settlement_digest_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("settlement_digest")
        or row.get("certificate_hash")
        or ""
    ).strip()


def _clearing_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine clearing certificate digests."""
    legs = body.get("clearings") or body.get("legs") or []
    clearing_rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            clearing_rows.append(
                {
                    "settlement_index": int(row.get("settlement_index") or 0),
                    "settlement_height": int(row.get("settlement_height") or 0),
                    "settlement_digest": str(row.get("settlement_digest") or ""),
                    "bound_settlement_root": str(
                        row.get("bound_settlement_root") or ""
                    ),
                    "bound_state_root": str(row.get("bound_state_root") or ""),
                    "bound_action_root": str(row.get("bound_action_root") or ""),
                    "actuation_digest": str(row.get("actuation_digest") or ""),
                    "observation_count": int(row.get("observation_count") or 0),
                    "observation_signature": str(
                        row.get("observation_signature") or ""
                    ),
                    "observations_ok": bool(row.get("observations_ok", True)),
                    "net_ok": bool(row.get("net_ok", True)),
                    "discharged": bool(row.get("discharged", True)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_clearing_root": str(
                        row.get("parent_clearing_root") or ""
                    ),
                    "clearing_root": str(row.get("clearing_root") or ""),
                    "post_settlement": bool(row.get("post_settlement", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_CLEARING_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "settlement_digest": str(body.get("settlement_digest") or ""),
        "parent_clearing_root": str(body.get("parent_clearing_root") or ""),
        "tip_clearing_root": str(body.get("tip_clearing_root") or ""),
        "clearing_height": int(body.get("clearing_height") or 0),
        "clearing_count": int(body.get("clearing_count") or 0),
        "gross_count": int(body.get("gross_count") or 0),
        "net_count": int(body.get("net_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "cleared": bool(body.get("cleared", True)),
        "clearings_ok": bool(body.get("clearings_ok", True)),
        "settlements_ok": bool(body.get("settlements_ok", True)),
        "net_ok": bool(body.get("net_ok", True)),
        "discharged": bool(body.get("discharged", True)),
        "post_settlement": bool(body.get("post_settlement", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "clearings": clearing_rows,
    }


def compute_total_spine_clearing_root(
    clearings: Sequence[Mapping[str, Any]],
) -> str:
    """Tip clearing root of a hash-chained netting log (empty → zero)."""
    if not clearings:
        return "0" * 64
    last = clearings[-1]
    tip = str(last.get("clearing_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(clearings):
        body = {
            "settlement_index": int(row.get("settlement_index") or idx),
            "settlement_height": int(row.get("settlement_height") or (idx + 1)),
            "settlement_digest": str(row.get("settlement_digest") or ""),
            "bound_settlement_root": str(row.get("bound_settlement_root") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "observation_count": int(row.get("observation_count") or 0),
            "observation_signature": str(row.get("observation_signature") or ""),
            "observations_ok": bool(row.get("observations_ok", True)),
            "net_ok": bool(row.get("net_ok", True)),
            "discharged": bool(row.get("discharged", True)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_clearing_root": parent,
            "post_settlement": True,
            "deterministic": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def net_total_spine_settlements(
    settlements: Sequence[Mapping[str, Any]],
    *,
    min_clearings: int = TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS,
    parent_clearing_root: str = "",
    clearing_height: int | None = None,
) -> list[dict[str, Any]]:
    """Net independently verified settlement receipts into hash-chained legs.

    Two (or more) settlements discharge only when they share the same
    bound_state_root, bound_action_root, actuation_digest, and ordered
    (capability, observed_ok) signature. Disagreement is a refusal.
    """
    from blackhole_agent.upstream_total_spine_settlement import (
        verify_total_spine_settlement_certificate,
    )

    want = max(int(min_clearings), TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS)
    verified: list[Mapping[str, Any]] = []
    for raw in settlements:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_total_spine_settlement_certificate(raw)
        if not verify.get("ok"):
            raise StageRefused(
                "total_spine_clearing_settlement_tampered",
                "clearing refuses a settlement whose digest/chain does not verify",
            )
        if raw.get("settled") is False or raw.get("success") is False:
            raise StageRefused(
                "total_spine_clearing_settlement_unsettled",
                "clearing refuses an unsettled settlement receipt",
            )
        if raw.get("observations_ok") is False:
            raise StageRefused(
                "total_spine_clearing_settlement_observations_failed",
                "clearing refuses a settlement whose observations_ok is false",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            "total_spine_clearing_settlements_short",
            f"clearing requires >= {want} independent settlements, "
            f"got {len(verified)}",
        )

    first = verified[0]
    book_state = str(first.get("bound_state_root") or "")
    book_action = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    book_actuation = str(first.get("actuation_digest") or "")
    book_sig = _observation_signature(list(first.get("observations") or []))
    if not book_state or not book_action or not book_actuation:
        raise StageRefused(
            "total_spine_clearing_root_missing",
            "clearing requires settlement bound state/action/actuation roots",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_clearing_root or "")
    for idx, settlement in enumerate(verified):
        state = str(settlement.get("bound_state_root") or "")
        action = str(
            settlement.get("bound_action_root")
            or settlement.get("tip_action_root")
            or ""
        )
        actuation = str(settlement.get("actuation_digest") or "")
        if state != book_state or action != book_action or actuation != book_actuation:
            raise StageRefused(
                "total_spine_clearing_root_mismatch",
                "clearing refuses settlements bound to different "
                "state/action/actuation roots",
            )
        observations = list(settlement.get("observations") or [])
        sig = _observation_signature(observations)
        if sig != book_sig:
            raise StageRefused(
                "total_spine_clearing_net_failed",
                "independent settlement observation books disagree; "
                "residual cannot be discharged",
            )
        observations_ok = all(
            isinstance(row, Mapping) and bool(row.get("observed_ok", True))
            for row in observations
        )
        if not observations_ok:
            raise StageRefused(
                "total_spine_clearing_settlement_observations_failed",
                "clearing refuses a settlement with a failed observation",
            )
        height = (
            int(clearing_height) + idx
            if clearing_height is not None
            else (idx + 1)
        )
        material = {
            "settlement_index": idx,
            "settlement_height": height,
            "settlement_digest": _settlement_digest_of(settlement),
            "bound_settlement_root": str(
                settlement.get("tip_settlement_root") or ""
            ),
            "bound_state_root": state,
            "bound_action_root": action,
            "actuation_digest": actuation,
            "observation_count": int(
                settlement.get("observation_count") or len(observations)
            ),
            "observation_signature": sig,
            "observations_ok": True,
            "net_ok": True,
            "discharged": True,
            "residual": 0,
            "independent": True,
            "parent_clearing_root": parent,
            "post_settlement": True,
            "deterministic": True,
        }
        clearing_root = _sha256_json(material)
        row = dict(material)
        row["clearing_root"] = clearing_root
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = clearing_root
    return legs


def seal_total_spine_clearing_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-settlement netting log into a tamper-evident receipt."""
    return _seal_log_certificate("clearing", body)


def clearing_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-clearing.json`` under a clearing/out root."""
    return resolve_certificate_path(
        Path(root),
        filename=TOTAL_SPINE_CLEARING_FILENAME,
        subdir="clearing",
        kind=TOTAL_SPINE_CLEARING_KIND,
        parent_sibling=True,
    )


def write_total_spine_clearing_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a clearing receipt under ``out_root``."""
    return write_irreversible_certificate(
        out_root,
        body,
        family="clearing",
        digest_key="clearing_digest",
        seal=seal_total_spine_clearing_certificate,
        resolve=clearing_certificate_path,
        load=load_total_spine_clearing_certificate,
        allow_idempotent=allow_idempotent,
        refused=StageRefused,
    )


def verify_total_spine_clearing_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute clearing digest and netting roots; fail closed on tamper."""
    return _verify_log_certificate("clearing", certificate)


def load_total_spine_clearing_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed clearing receipt."""
    return load_irreversible_certificate(
        path,
        family="clearing",
        label="clearing certificate",
        path_key="clearing_path",
        verify_key="clearing_verify",
        resolve=clearing_certificate_path,
        verify=verify_total_spine_clearing_certificate,
        refused=StageRefused,
        accept=lambda payload: str(payload.get("kind") or "")
        == TOTAL_SPINE_CLEARING_KIND
        or bool(payload.get("total_spine_clearing")),
    )


def seal_total_spine_clearing_chain(
    *,
    prior_tip: str,
    clearing_digest: str,
    tip_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    settlement_digest: str,
    clearing_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal clearing hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    cd = str(clearing_digest or "").strip() or ("0" * 64)
    cr = str(tip_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    sd = str(settlement_digest or "").strip() or ("0" * 64)
    material = (
        f"clearing|{int(bool(short_circuit))}|{int(clearing_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{sd}|{cr}|{cd}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "clearing_height": int(clearing_height),
        "tip_clearing_root": cr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "settlement_digest": sd,
        "clearing_digest": cd,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_clearing": True,
        "irreversible": True,
        "post_settlement": True,
        "deterministic": True,
    }


def annotate_total_spine_clearing(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-settlement clearing onto a total-spine result and rebind tip."""
    clr_digest = str(
        certificate.get("clearing_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_clearing_root = str(certificate.get("tip_clearing_root") or "")
    clearing_height = int(certificate.get("clearing_height") or 0)
    clearing_count = int(certificate.get("clearing_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    settlement_digest = str(certificate.get("settlement_digest") or "")
    chain = seal_total_spine_clearing_chain(
        prior_tip=prior_tip,
        clearing_digest=clr_digest,
        tip_clearing_root=tip_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        settlement_digest=settlement_digest,
        clearing_height=clearing_height,
        short_circuit=short_circuit,
    )
    clr_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{clr_tip}".encode("utf-8"))
    body["total_spine_clearing"] = True
    body["total_spine_clearing_impl"] = TOTAL_SPINE_CLEARING_IMPL
    body["total_spine_clearing_short_circuit"] = bool(short_circuit)
    body["total_spine_clearing_irreversible"] = True
    body["total_spine_clearing_post_settlement"] = True
    body["total_spine_clearing_deterministic"] = True
    body["total_spine_clearing_certificate"] = dict(certificate)
    body["total_spine_clearing_digest"] = clr_digest
    body["total_spine_clearing_chain"] = chain
    body["total_spine_clearing_tip"] = clr_tip
    body["total_spine_clearing_bound_tip"] = bound
    body["total_spine_digest_pre_clearing"] = prior_tip
    body["total_spine_tip_clearing_root"] = tip_clearing_root
    body["total_spine_clearing_height"] = clearing_height
    body["total_spine_clearing_count"] = clearing_count
    body["total_spine_cleared"] = bool(certificate.get("cleared", True))
    body["total_spine_cleared_ok"] = bool(certificate.get("cleared", True))
    body["total_spine_clearings_ok"] = bool(certificate.get("clearings_ok", True))
    body["total_spine_clearing_root_valid"] = bool(tip_clearing_root)
    body["total_spine_discharged"] = bool(certificate.get("discharged", True))
    body["total_spine_net_ok"] = bool(certificate.get("net_ok", True))
    body["total_spine_clearing_residual"] = int(certificate.get("residual") or 0)
    body["total_spine_clearing_gross_count"] = int(
        certificate.get("gross_count") or 0
    )
    body["total_spine_clearing_net_count"] = int(certificate.get("net_count") or 0)
    body["clearing_root"] = tip_clearing_root
    body["tip_clearing_root"] = tip_clearing_root
    body["clearing_count"] = clearing_count
    body["clearing_height"] = clearing_height
    body["cleared"] = bool(certificate.get("cleared", True))
    body["cleared_ok"] = bool(certificate.get("cleared", True))
    if certificate.get("clearing_path"):
        body["total_spine_clearing_path"] = certificate.get("clearing_path")
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
    if bound_settlement_root:
        body["total_spine_tip_settlement_root"] = bound_settlement_root
        body["settlement_root"] = bound_settlement_root
        body["tip_settlement_root"] = bound_settlement_root
        body.setdefault("total_spine_settlement", True)
        body.setdefault("total_spine_settled", True)
    if actuation_digest:
        body["total_spine_actuation_digest"] = actuation_digest
    if settlement_digest:
        body["total_spine_settlement_digest"] = settlement_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_clearing_ok_short_circuit"
        if short_circuit
        else "total_spine_clearing_ok"
    )
    body["ok"] = True
    return body


def _as_settlement_mapping(value: Any) -> dict[str, Any] | None:
    from blackhole_agent.upstream_total_spine_settlement import (
        StageRefused as SettlementRefused,
        load_total_spine_settlement_certificate,
    )

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_SETTLEMENT_KIND or value.get(
            "total_spine_settlement"
        ) or value.get("total_spine_settlement_loaded") or value.get(
            "tip_settlement_root"
        ):
            nested = value.get("total_spine_settlement_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_settlement_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_settlement_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / "settlement" / "total-spine-settlement.json"
            named = path / "total-spine-settlement.json"
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != TOTAL_SPINE_SETTLEMENT_KIND:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_total_spine_settlement_certificate(path)
    except SettlementRefused as exc:
        if str(exc.verdict) == "total_spine_settlement_tampered":
            raise StageRefused(str(exc.verdict), str(exc.detail)) from exc
        return None
    except Exception:  # noqa: BLE001
        return None


def _as_clearing_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_CLEARING_KIND or value.get(
            "total_spine_clearing"
        ) or value.get("total_spine_clearing_loaded"):
            nested = value.get("total_spine_clearing_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_clearing_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_clearing_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    try:
        return load_total_spine_clearing_certificate(Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == "total_spine_clearing_tampered":
            raise
        return None
    except Exception:  # noqa: BLE001
        return None


def _confirm_settlement(
    primary: Mapping[str, Any],
    *,
    actuation: Mapping[str, Any] | None,
    out_root: Path | None,
    prior_tip: str,
    repo_path: Path | None,
) -> dict[str, Any]:
    """Independently re-settle the same actuation as a confirmation book."""
    from blackhole_agent.upstream_total_spine_settlement import settle_total_spine

    if actuation is None:
        raise StageRefused(
            "total_spine_clearing_confirmation_missing",
            "single settlement requires an actuation source to confirm-clear",
        )
    confirm_out = None
    if out_root is not None:
        confirm_out = Path(out_root) / "clearing-confirm"
    tip_settlement = str(primary.get("tip_settlement_root") or "")
    obs_height = int(primary.get("observation_height") or 0)
    confirmed = settle_total_spine(
        actuation,
        out_root=confirm_out,
        prior_tip=prior_tip,
        parent_observation_root=tip_settlement,
        observation_height=obs_height + 1 if obs_height else None,
        repo_path=repo_path or REPO_ROOT,
    )
    cert = confirmed.get("total_spine_settlement_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            "total_spine_clearing_confirmation_missing",
            "confirmation settlement did not produce a certificate",
        )
    return dict(cert)


def _actuation_from_settlement(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Rebuild an actuation source from a settlement that still carries actions."""
    nested = row.get("total_spine_actuation_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("actions") or nested.get("tip_action_root")
    ):
        return dict(nested)
    actions = row.get("actions")
    if not isinstance(actions, list) or not actions:
        return None
    return {
        "kind": "total_spine_actuation",
        "actions": list(actions),
        "tip_action_root": str(
            row.get("bound_action_root") or row.get("tip_action_root") or ""
        ),
        "bound_action_root": str(row.get("bound_action_root") or ""),
        "bound_state_root": str(row.get("bound_state_root") or ""),
        "state_root": str(row.get("bound_state_root") or ""),
        "actuation_digest": str(row.get("actuation_digest") or ""),
        "execution_digest": str(row.get("execution_digest") or ""),
        "goal": str(row.get("goal") or ""),
        "done_when": str(row.get("done_when") or ""),
        "root_layer": str(row.get("root_layer") or ""),
        "capabilities": list(row.get("capabilities") or []),
        "irreversible": True,
        "success": True,
        "effects_ok": True,
        "post_execution": True,
        "deterministic": True,
    }


def _collect_settlements(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None,
    body: Mapping[str, Any] | None,
    extra: Sequence[Mapping[str, Any] | Path | str] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None]:
    """Return (existing_clearing, settlements, actuation)."""
    existing = _as_clearing_mapping(source)
    if existing is None and body is not None:
        existing = _as_clearing_mapping(body)
    settlements: list[dict[str, Any]] = []
    actuation: dict[str, Any] | None = None

    def _take_actuation(item: Any) -> None:
        nonlocal actuation
        if actuation is not None or not isinstance(item, Mapping):
            return
        recovered = _actuation_from_settlement(item)
        if recovered is not None:
            actuation = recovered
            return
        nested_act = item.get("total_spine_actuation_certificate")
        if isinstance(nested_act, Mapping):
            actuation = dict(nested_act)

    def _push(item: Any) -> None:
        mapped = _as_settlement_mapping(item)
        if mapped is not None:
            settlements.append(mapped)
            _take_actuation(mapped)
        if isinstance(item, Mapping):
            _take_actuation(item)

    if existing is None:
        if isinstance(source, Sequence) and not isinstance(
            source, (str, bytes, Mapping)
        ):
            for item in source:
                _push(item)
        else:
            _push(source)
    if body is not None:
        _push(body.get("total_spine_settlement_certificate"))
        _push(body)
        _take_actuation(body)
    for item in extra or []:
        _push(item)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in settlements:
        digest = _settlement_digest_of(row)
        tip = str(row.get("tip_settlement_root") or "")
        key = digest or tip
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return existing, deduped, actuation


def _strip_clearing_predicates(done_when: str) -> str:
    """Evaluate the pre-clearing contract, never clearing_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "clearing_ok",
        "cleared_ok",
        "min_clearings",
        "clearing_root_valid",
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


def clear_total_spine(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    settlements: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_clearings: int = TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS,
    parent_clearing_root: str = "",
    clearing_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply post-settlement multilateral clearing on the absolute total spine."""
    return _apply_log_family(
        "clearing",
        source,
        settlements=settlements,
        out_root=out_root,
        prior_tip=prior_tip,
        body=body,
        min_clearings=min_clearings,
        parent_clearing_root=parent_clearing_root,
        clearing_height=clearing_height,
        short_circuit=short_circuit,
        repo_path=repo_path,
        confirm=confirm,
        actuation=actuation,
    )


def _clearing_apply_core(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    settlements: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_clearings: int = TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS,
    parent_clearing_root: str = "",
    clearing_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Clearing apply core: collect/net settlements, evaluate contract, finish."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_CLEARING_IMPL:
        raise StageRefused(
            "total_spine_clearing_disabled",
            "TOTAL_SPINE_CLEARING_IMPL is False",
        )

    existing, collected, found_actuation = _collect_settlements(
        source, body, settlements
    )
    if actuation is None:
        actuation = found_actuation
    else:
        actuation = dict(actuation)
    if (
        existing is not None
        and existing.get("tip_clearing_root")
        and (
            str(existing.get("kind") or "") == TOTAL_SPINE_CLEARING_KIND
            or existing.get("total_spine_clearing_loaded")
            or existing.get("total_spine_clearing")
        )
    ):
        tip = str(
            prior_tip
            or existing.get("prior_tip")
            or (body or {}).get("total_spine_digest")
            or ""
        )
        return _short_circuit_log_apply("clearing", existing, body, prior_tip)

    want = max(int(min_clearings), TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_settlement(
                collected[0],
                actuation=actuation,
                out_root=out_root,
                prior_tip=str(
                    prior_tip
                    or (body or {}).get("total_spine_settlement_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            "total_spine_clearing_settlements_short",
            f"clearing requires >= {want} independent settlements, "
            f"got {len(collected)}",
        )

    legs = net_total_spine_settlements(
        collected,
        min_clearings=want,
        parent_clearing_root=parent_clearing_root,
        clearing_height=clearing_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("tip_settlement_root") or "")
    settlement_digest = _settlement_digest_of(first)
    root_layer = str(
        first.get("root_layer")
        or (body or {}).get("total_spine_root")
        or ENGINE_DEFAULT_ROOT
        or TOTAL_SPINE_DEFAULT_ROOT
    )
    goal = str(first.get("goal") or (body or {}).get("total_spine_goal") or "")
    done_when = str(
        first.get("done_when") or (body or {}).get("total_spine_done_when") or ""
    )

    contract_met = True
    contract_machine = False
    contract_eval: dict[str, Any] | None = None
    pre_clearing = _strip_clearing_predicates(done_when)
    if pre_clearing:
        ctx = {
            "settlement": {
                "ok": True,
                "settled": True,
                "settled_ok": True,
                "settlement_root_valid": True,
                "observation_count": int(first.get("observation_count") or 0),
                "settlement_count": int(first.get("observation_count") or 0),
                "tip_settlement_root": settlement_root,
            },
            "observation_count": int(first.get("observation_count") or 0),
            "settlement_count": len(collected),
            "tip_settlement_root": settlement_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_clearing,
            context=ctx,
            cwd=repo_path or REPO_ROOT,
            timeout=60,
        )
        contract_machine = bool(contract_eval.get("machine_checkable"))
        contract_met = (
            contract_eval.get("met") is True if contract_machine else True
        )
        if contract_machine and contract_met is not True:
            raise StageRefused(
                "total_spine_clearing_contract_unmet",
                f"done_when not met at clearing: {pre_clearing!r}",
            )

    tip_clearing_root = compute_total_spine_clearing_root(legs)
    clr_height = int(legs[-1]["settlement_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_settlement_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    capabilities = []
    for settlement in collected:
        for row in settlement.get("observations") or []:
            if isinstance(row, Mapping):
                cid = str(row.get("capability_id") or "")
                if cid and cid not in capabilities:
                    capabilities.append(cid)
    gross = sum(
        int(s.get("observation_count") or len(s.get("observations") or []))
        for s in collected
    )
    net_count = int(first.get("observation_count") or len(first.get("observations") or []))

    clr_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_CLEARING_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "settlement_digest": settlement_digest,
        "prior_tip": tip,
        "parent_clearing_root": str(
            parent_clearing_root
            or (legs[0].get("parent_clearing_root") if legs else "")
            or ""
        ),
        "clearings": legs,
        "clearing_count": len(legs),
        "clearing_height": clr_height,
        "tip_clearing_root": tip_clearing_root,
        "gross_count": gross,
        "net_count": net_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "cleared": True,
        "clearings_ok": True,
        "settlements_ok": True,
        "net_ok": True,
        "discharged": True,
        "post_settlement": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "cleared_at": utc_now_iso(),
    }
    if contract_eval is not None:
        clr_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    return _finish_log_apply(
        "clearing",
        cert_body=clr_body,
        out_root=out_root,
        body=body,
        prior_tip=tip,
        short_circuit=short_circuit,
        extra={
            "total_spine_clearing_bound_state_root": state_root,
            "total_spine_clearing_bound_action_root": action_root,
            "total_spine_clearing_bound_settlement_root": settlement_root,
            "total_spine_clearing_actuation_digest": actuation_digest,
        },
    )


def builtin_total_spine_clearing_proof() -> dict[str, Any]:
    """Hermetic proof: post-settlement multilateral clearing on the absolute tower."""
    return _run_log_family_proof("clearing")


def clearing_main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "clearing-proof",
        help=(
            "Total spine clearing proof: post-settlement netting discharges "
            "matching observation books into irreversible clearing receipts"
        ),
    )
    sub.add_parser("proof", help="Alias for clearing-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"clearing-proof", "proof"}:
        result = builtin_total_spine_clearing_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


# ---------------------------------------------------------------------------
# Synthesis: log-family modules with exact historical names and bindings.
# ---------------------------------------------------------------------------

_LOG_MODULE_PREFIX = "blackhole_agent.upstream_total_spine_"


@dataclass(frozen=True)
class LogFamilySpec:
    """Tokens that distinguish one remaining log-family module.

    Certificate seal/verify is driven by the fields below: a new hash-chained
    family is a row, not another copy of the digest/chain walk.
    """

    name: str
    pred: str
    verb: str
    summary: str
    exports: tuple[str, ...]
    main_name: str = "main"
    # Certificate engine (seal + verify).
    shape: str = "rows"  # "rows" (hash-chained log) | "state" (single state root)
    digest_style: str = "spaced"  # "spaced" | "compact" (control-engine historical)
    kind: str = ""
    filename: str = ""
    impl_flag: str = ""
    min_value: int = 2
    rows_key: str = "actions"
    tip_key: str = "tip_action_root"
    count_key: str = "action_count"
    height_key: str = "action_height"
    parent_key: str = "parent_action_root"
    row_root_key: str = "action_root"
    digest_key: str = "actuation_digest"
    timestamp_key: str = "actuated_at"
    post_flag: str = "post_execution"
    material_fn: str = "_actuation_certificate_material"
    tip_fn: str = "compute_total_spine_action_root"
    row_material_fn: str = "_actuation_row_material"
    carry_keys: tuple[str, ...] = ()
    bind_fields: tuple[str, ...] = ("bound_state_root",)
    required_nonempty: tuple[str, ...] = ("bound_state_root",)
    required_true: tuple[str, ...] = ()
    required_zero: tuple[str, ...] = ()
    require_execution_digest: bool = False
    book_sig_field: str = ""
    rows_ok_fn: str = ""
    verify_root_ok_key: str = "action_root_ok"
    verify_recomputed_key: str = "recomputed_tip_action_root"
    verify_min_ok_key: str = "min_actions_ok"
    verify_rows_ok_key: str = ""
    verify_flag_keys: tuple[tuple[str, str], ...] = ()
    # Apply/proof runner.
    apply_fn: str = "actuate_total_spine"
    apply_core_fn: str = "_actuation_apply_core"
    proof_origin: str = "actuation proof origin"
    scratch_prefix: str = "total-spine-actuation-proof-"
    pred_impl_flag: str = "TOTAL_SPINE_EXECUTION_IMPL"
    result_path_key: str = "total_spine_actuation_path"
    result_tip_key: str = "total_spine_tip_action_root"
    result_count_key: str = "total_spine_action_count"
    result_height_key: str = "total_spine_action_height"
    result_bound_tip_key: str = "total_spine_actuation_bound_tip"
    result_post_key: str = "total_spine_actuation_post_execution"
    result_irreversible_key: str = "total_spine_actuation_irreversible"
    result_short_key: str = "total_spine_actuation_short_circuit"
    result_chain_key: str = "total_spine_actuation_chain"
    result_tip_chain_key: str = "total_spine_actuation_tip"
    loaded_key: str = "total_spine_actuation_loaded"
    verify_bag_key: str = "actuation_verify"
    verify_extra: tuple[str, ...] = ("action_root_ok",)
    offline_true: tuple[str, ...] = (
        "total_spine_actuation",
        "total_spine_actuation_post_execution",
        "total_spine_actuation_irreversible",
        "total_spine_effects_applied",
    )
    tamper_height_field: str = "action_height"
    supersession_drop: tuple[str, ...] = (
        "actuation_verify",
        "total_spine_actuation_loaded",
        "actuation_path",
        "actuation_digest",
        "certificate_hash",
        "actuated_at",
        "total_spine_actuation",
        "total_spine_actuation_impl",
        "used_skill_route_discovery",
    )
    parent_kwarg: str = "parent_action_root"
    height_kwarg: str = "action_height"
    live_flags: tuple[str, ...] = ("execution", "actuation")
    live_true: tuple[str, ...] = (
        "total_spine_finality",
        "total_spine_federation",
        "total_spine_quorum",
        "total_spine_execution",
        "total_spine_actuation",
        "total_spine_effects_applied",
    )
    engine_true_token: str = "actuation=True"
    engine_sig_token: str = "actuation: bool = False"
    ledger_id: str = "capability.upstream-total-spine-actuation"
    ledger_entry_needles: tuple[str, ...] = (
        "upstream_total_spine_actuation",
        "upstream_control_engine",
    )
    ledger_proof_needle: str = "builtin_total_spine_actuation_proof"
    ledger_delta_needles: tuple[str, ...] = (
        "action",
        "actuate_total_spine",
        "post-execution",
        "post_execution",
    )
    chain_params: tuple[tuple[str, str, str], ...] = (
        ("prior_tip", "prior_tip", "str"),
        ("actuation_digest", "actuation_digest", "str"),
        ("tip_action_root", "tip_action_root", "str"),
        ("bound_state_root", "bound_state_root", "str"),
        ("action_height", "action_height", "int"),
        ("short_circuit", "short_circuit", "bool"),
    )
    extra_proofs: tuple[str, ...] = ()
    return_count_key: str = "action_count"
    pred_digest_source: str = "executed"
    mod_needles: tuple[str, ...] = (
        "total_spine_actuation_supersession_refused",
        "total_spine_actuation_tampered",
    )
    live_path_out_key: str = "live_actuation_path"
    live_tip_out_key: str = "live_tip_action_root"
    return_tip_keys: tuple[tuple[str, str], ...] = ()


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


_CLEARING_EXPORTS: tuple[str, ...] = (
    "Any",
    "Mapping",
    "Path",
    "REPO_ROOT",
    "SCHEMA_VERSION",
    "Sequence",
    "StageRefused",
    "TOTAL_SPINE_CLEARING_FILENAME",
    "TOTAL_SPINE_CLEARING_IMPL",
    "TOTAL_SPINE_CLEARING_KIND",
    "TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS",
    "TOTAL_SPINE_DEFAULT_ROOT",
    "TOTAL_SPINE_SETTLEMENT_KIND",
    "annotate_total_spine_clearing",
    "annotations",
    "atomic_write_json",
    "builtin_total_spine_clearing_proof",
    "clear_total_spine",
    "clearing_certificate_path",
    "compute_total_spine_clearing_root",
    "durable_read_path",
    "json",
    "legacy_pipeline_was_used",
    "load_irreversible_certificate",
    "load_total_spine_clearing_certificate",
    "main",
    "net_total_spine_settlements",
    "resolve_certificate_path",
    "seal_total_spine_clearing_certificate",
    "seal_total_spine_clearing_chain",
    "utc_now_iso",
    "verify_total_spine_clearing_certificate",
    "write_irreversible_certificate",
    "write_total_spine_clearing_certificate",
)


LOG_FAMILY_SPECS: dict[str, LogFamilySpec] = {
    "execution": LogFamilySpec(
        name="execution",
        pred="quorum",
        verb="execute",
        summary=(
            "Post-consensus world-state execution for the absolute total spine. "
            "Closes the certificate-only cliff."
        ),
        exports=(),
        shape="state",
        digest_style="compact",
        kind=TOTAL_SPINE_EXECUTION_KIND,
        filename=TOTAL_SPINE_EXECUTION_FILENAME,
        impl_flag="TOTAL_SPINE_EXECUTION_IMPL",
        min_value=1,
        rows_key="",
        tip_key="state_root",
        count_key="",
        height_key="state_height",
        parent_key="parent_state_root",
        row_root_key="",
        digest_key="execution_digest",
        timestamp_key="executed_at",
        post_flag="post_finality",
        material_fn="_execution_certificate_material",
        tip_fn="compute_total_spine_state_root",
        row_material_fn="",
        required_nonempty=("source_digest",),
        verify_root_ok_key="state_root_ok",
        verify_recomputed_key="recomputed_state_root",
        apply_fn="execute_total_spine",
        apply_core_fn="_execution_apply_core",
        proof_origin="execution proof origin",
        scratch_prefix="total-spine-execution-proof-",
        ledger_id="capability.upstream-total-spine-execution",
        ledger_entry_needles=("upstream_control_engine",),
        ledger_proof_needle="builtin_total_spine_execution_proof",
        ledger_delta_needles=("execute_total_spine", "state_root", "post-quorum"),
    ),
    "actuation": LogFamilySpec(
        name="actuation",
        pred="execution",
        verb="actuate",
        summary=(
            "Post-execution actuation for the absolute total spine. "
            "Closes the inert state-root cliff."
        ),
        exports=_ACTUATION_EXPORTS,
        kind=TOTAL_SPINE_ACTUATION_KIND,
        filename=TOTAL_SPINE_ACTUATION_FILENAME,
        impl_flag="TOTAL_SPINE_ACTUATION_IMPL",
        min_value=TOTAL_SPINE_ACTUATION_MIN_ACTIONS,
        rows_key="actions",
        tip_key="tip_action_root",
        count_key="action_count",
        height_key="action_height",
        parent_key="parent_action_root",
        row_root_key="action_root",
        digest_key="actuation_digest",
        timestamp_key="actuated_at",
        post_flag="post_execution",
        material_fn="_actuation_certificate_material",
        tip_fn="compute_total_spine_action_root",
        row_material_fn="_actuation_row_material",
        required_nonempty=("bound_state_root",),
        require_execution_digest=True,
        verify_root_ok_key="action_root_ok",
        verify_recomputed_key="recomputed_tip_action_root",
        verify_min_ok_key="min_actions_ok",
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
        kind=TOTAL_SPINE_SETTLEMENT_KIND,
        filename=TOTAL_SPINE_SETTLEMENT_FILENAME,
        impl_flag="TOTAL_SPINE_SETTLEMENT_IMPL",
        min_value=TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS,
        rows_key="observations",
        tip_key="tip_settlement_root",
        count_key="observation_count",
        height_key="observation_height",
        parent_key="parent_observation_root",
        row_root_key="observation_root",
        digest_key="settlement_digest",
        timestamp_key="settled_at",
        post_flag="post_actuation",
        material_fn="_settlement_certificate_material",
        tip_fn="compute_total_spine_settlement_root",
        row_material_fn="_settlement_row_material",
        carry_keys=("actions",),
        bind_fields=("bound_state_root", "actuation_digest"),
        required_nonempty=("bound_state_root", "bound_action_root", "actuation_digest"),
        required_true=("settled",),
        rows_ok_fn="_settlement_rows_ok",
        verify_root_ok_key="settlement_root_ok",
        verify_recomputed_key="recomputed_tip_settlement_root",
        verify_min_ok_key="min_observations_ok",
        verify_rows_ok_key="observations_ok",
        verify_flag_keys=(("settled_ok", "settled"),),
        apply_fn="settle_total_spine",
        apply_core_fn="_settlement_apply_core",
        proof_origin="settlement proof origin",
        scratch_prefix="total-spine-settlement-proof-",
        pred_impl_flag="TOTAL_SPINE_ACTUATION_IMPL",
        result_path_key="total_spine_settlement_path",
        result_tip_key="total_spine_tip_settlement_root",
        result_count_key="total_spine_observation_count",
        result_height_key="total_spine_observation_height",
        result_bound_tip_key="total_spine_settlement_bound_tip",
        result_post_key="total_spine_settlement_post_actuation",
        result_irreversible_key="total_spine_settlement_irreversible",
        result_short_key="total_spine_settlement_short_circuit",
        result_chain_key="total_spine_settlement_chain",
        result_tip_chain_key="total_spine_settlement_tip",
        loaded_key="total_spine_settlement_loaded",
        verify_bag_key="settlement_verify",
        verify_extra=("settlement_root_ok", "observations_ok"),
        offline_true=(
            "total_spine_settlement",
            "total_spine_settlement_post_actuation",
            "total_spine_settlement_irreversible",
            "total_spine_settled",
            "total_spine_observations_ok",
        ),
        tamper_height_field="observation_height",
        supersession_drop=(
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
        ),
        parent_kwarg="parent_observation_root",
        height_kwarg="observation_height",
        live_flags=("execution", "actuation", "settlement"),
        live_true=(
            "total_spine_finality",
            "total_spine_federation",
            "total_spine_quorum",
            "total_spine_execution",
            "total_spine_actuation",
            "total_spine_settlement",
            "total_spine_settled",
        ),
        engine_true_token="settlement=True",
        engine_sig_token="settlement: bool = False",
        ledger_id="capability.upstream-total-spine-settlement",
        ledger_entry_needles=(
            "upstream_total_spine_settlement",
            "upstream_control_engine",
        ),
        ledger_proof_needle="builtin_total_spine_settlement_proof",
        ledger_delta_needles=(
            "settle_total_spine",
            "post-actuation",
            "post_actuation",
            "observation",
        ),
        chain_params=(
            ("prior_tip", "prior_tip", "str"),
            ("settlement_digest", "settlement_digest", "str"),
            ("tip_settlement_root", "tip_settlement_root", "str"),
            ("bound_action_root", "bound_action_root", "str"),
            ("bound_state_root", "bound_state_root", "str"),
            ("actuation_digest", "actuation_digest", "str"),
            ("observation_height", "observation_height", "int"),
            ("short_circuit", "short_circuit", "bool"),
        ),
        extra_proofs=("unmet",),
        return_count_key="observation_count",
        pred_digest_source="actuated",
        mod_needles=(
            "total_spine_settlement_supersession_refused",
            "total_spine_settlement_tampered",
            "total_spine_settlement_contract_unmet",
        ),
        live_path_out_key="live_settlement_path",
        live_tip_out_key="live_tip_settlement_root",
        return_tip_keys=(("tip_action_root", "tip_action"),),
    ),
    "clearing": LogFamilySpec(
        name="clearing",
        pred="settlement",
        verb="clear",
        summary=(
            "Post-settlement clearing for the absolute total spine. "
            "Closes the settled-but-uncleared cliff."
        ),
        exports=_CLEARING_EXPORTS,
        main_name="clearing_main",
        kind=TOTAL_SPINE_CLEARING_KIND,
        filename=TOTAL_SPINE_CLEARING_FILENAME,
        impl_flag="TOTAL_SPINE_CLEARING_IMPL",
        min_value=TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS,
        rows_key="clearings",
        tip_key="tip_clearing_root",
        count_key="clearing_count",
        height_key="clearing_height",
        parent_key="parent_clearing_root",
        row_root_key="clearing_root",
        digest_key="clearing_digest",
        timestamp_key="cleared_at",
        post_flag="post_settlement",
        material_fn="_clearing_certificate_material",
        tip_fn="compute_total_spine_clearing_root",
        row_material_fn="_clearing_row_material",
        bind_fields=("bound_state_root", "actuation_digest"),
        required_nonempty=("bound_state_root", "bound_action_root", "actuation_digest"),
        required_true=("cleared", "discharged"),
        required_zero=("residual",),
        book_sig_field="observation_signature",
        rows_ok_fn="_clearing_rows_ok",
        verify_root_ok_key="clearing_root_ok",
        verify_recomputed_key="recomputed_tip_clearing_root",
        verify_min_ok_key="min_clearings_ok",
        verify_rows_ok_key="clearings_ok",
        verify_flag_keys=(("cleared_ok", "cleared"), ("discharged_ok", "discharged")),
        apply_fn="clear_total_spine",
        apply_core_fn="_clearing_apply_core",
        proof_origin="clearing proof origin",
        scratch_prefix="total-spine-clearing-proof-",
        pred_impl_flag="TOTAL_SPINE_SETTLEMENT_IMPL",
        result_path_key="total_spine_clearing_path",
        result_tip_key="total_spine_tip_clearing_root",
        result_count_key="total_spine_clearing_count",
        result_height_key="total_spine_clearing_height",
        result_bound_tip_key="total_spine_clearing_bound_tip",
        result_post_key="total_spine_clearing_post_settlement",
        result_irreversible_key="total_spine_clearing_irreversible",
        result_short_key="total_spine_clearing_short_circuit",
        result_chain_key="total_spine_clearing_chain",
        result_tip_chain_key="total_spine_clearing_tip",
        loaded_key="total_spine_clearing_loaded",
        verify_bag_key="clearing_verify",
        verify_extra=("clearing_root_ok", "clearings_ok"),
        offline_true=(
            "total_spine_clearing",
            "total_spine_clearing_post_settlement",
            "total_spine_clearing_irreversible",
            "total_spine_cleared",
            "total_spine_discharged",
            "total_spine_net_ok",
        ),
        tamper_height_field="clearing_height",
        supersession_drop=(
            "clearing_verify",
            "total_spine_clearing_loaded",
            "clearing_path",
            "clearing_digest",
            "certificate_hash",
            "cleared_at",
            "total_spine_clearing",
            "total_spine_clearing_impl",
            "used_skill_route_discovery",
            "contract_eval",
        ),
        parent_kwarg="parent_clearing_root",
        height_kwarg="clearing_height",
        live_flags=("execution", "actuation", "settlement", "clearing"),
        live_true=(
            "total_spine_finality",
            "total_spine_federation",
            "total_spine_quorum",
            "total_spine_execution",
            "total_spine_actuation",
            "total_spine_settlement",
            "total_spine_clearing",
            "total_spine_cleared",
            "total_spine_discharged",
        ),
        engine_true_token="clearing=True",
        engine_sig_token="clearing: bool = False",
        ledger_id="capability.upstream-total-spine-clearing",
        ledger_entry_needles=(
            "upstream_total_spine_clearing",
            "upstream_control_engine",
        ),
        ledger_proof_needle="builtin_total_spine_clearing_proof",
        ledger_delta_needles=(
            "clear_total_spine",
            "post-settlement",
            "post_settlement",
            "net",
        ),
        chain_params=(
            ("prior_tip", "prior_tip", "str"),
            ("clearing_digest", "clearing_digest", "str"),
            ("tip_clearing_root", "tip_clearing_root", "str"),
            ("bound_settlement_root", "bound_settlement_root", "str"),
            ("bound_action_root", "bound_action_root", "str"),
            ("bound_state_root", "bound_state_root", "str"),
            ("actuation_digest", "actuation_digest", "str"),
            ("settlement_digest", "settlement_digest", "str"),
            ("clearing_height", "clearing_height", "int"),
            ("short_circuit", "short_circuit", "bool"),
        ),
        extra_proofs=("mismatch",),
        return_count_key="clearing_count",
        pred_digest_source="settled",
        mod_needles=(
            "total_spine_clearing_supersession_refused",
            "total_spine_clearing_tampered",
            "total_spine_clearing_net_failed",
        ),
        live_path_out_key="live_clearing_path",
        live_tip_out_key="live_tip_clearing_root",
        return_tip_keys=(
            ("tip_settlement_root", "tip_settlement"),
            ("tip_action_root", "tip_action"),
        ),
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


# ---------------------------------------------------------------------------
# Execution (state-shaped) certificate material. Seal/verify are spec-driven.
# ---------------------------------------------------------------------------


def _execution_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical fields that bind a total-spine execution certificate digest."""
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_EXECUTION_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "source_kind": str(body.get("source_kind") or ""),
        "source_digest": str(body.get("source_digest") or ""),
        "prior_tip": str(body.get("prior_tip") or ""),
        "parent_state_root": str(body.get("parent_state_root") or ""),
        "state_height": int(body.get("state_height") or 0),
        "state_root": str(body.get("state_root") or ""),
        "capabilities": list(body.get("capabilities") or []),
        "effects_ok": bool(body.get("effects_ok", True)),
        "contract_met": body.get("contract_met"),
        "origin_count": int(body.get("origin_count") or 0),
        "quorum_met": bool(body.get("quorum_met", False)),
        "post_finality": True,
        "deterministic": True,
        "irreversible": True,
        "success": bool(body.get("success", True)),
    }


def compute_total_spine_state_root(body: Mapping[str, Any]) -> str:
    """Deterministic world-state root from consensus projection fields.

    Excludes wall-clock and certificate envelope fields so recompute from the
    same source digest + height + parent root yields an identical tip.
    """
    projection = {
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "effects_ok": bool(body.get("effects_ok", True)),
        "contract_met": body.get("contract_met"),
        "origin_count": int(body.get("origin_count") or 0),
        "quorum_met": bool(body.get("quorum_met", False)),
        "capabilities": list(body.get("capabilities") or []),
    }
    material = {
        "root_layer": str(body.get("root_layer") or ""),
        "source_kind": str(body.get("source_kind") or ""),
        "source_digest": str(body.get("source_digest") or ""),
        "prior_tip": str(body.get("prior_tip") or ""),
        "parent_state_root": str(body.get("parent_state_root") or ""),
        "state_height": int(body.get("state_height") or 0),
        "projection": projection,
    }
    return _sha256_json_compact(material)


def seal_total_spine_execution_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-consensus world-state into a tamper-evident execution cert."""
    return _seal_log_certificate("execution", body)


def verify_total_spine_execution_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute execution digest and state root; fail closed on tamper."""
    return _verify_log_certificate("execution", certificate)


def execution_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-execution.json`` under an execution/out root."""
    return resolve_certificate_path(
        Path(root),
        filename=TOTAL_SPINE_EXECUTION_FILENAME,
        subdir="execution",
        kind=TOTAL_SPINE_EXECUTION_KIND,
        parent_sibling=True,
    )


def write_total_spine_execution_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write an execution certificate under ``out_root``.

    Irreversible supersession: identical digests return idempotently;
    divergent reseal raises ``total_spine_execution_supersession_refused``.
    """
    from blackhole_agent.upstream_control_engine import StageRefused as EngineRefused

    return write_irreversible_certificate(
        out_root,
        body,
        family="execution",
        digest_key="execution_digest",
        seal=seal_total_spine_execution_certificate,
        resolve=execution_certificate_path,
        load=load_total_spine_execution_certificate,
        allow_idempotent=allow_idempotent,
        refused=EngineRefused,
    )


def load_total_spine_execution_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed execution certificate.

    Raises ``total_spine_execution_tampered`` on digest mismatch.
    """
    from blackhole_agent.upstream_control_engine import StageRefused as EngineRefused

    return load_irreversible_certificate(
        path,
        family="execution",
        label="execution certificate",
        path_key="execution_path",
        verify_key="execution_verify",
        resolve=execution_certificate_path,
        verify=verify_total_spine_execution_certificate,
        refused=EngineRefused,
    )


def seal_total_spine_execution_chain(
    *,
    prior_tip: str,
    execution_digest: str,
    state_root: str,
    state_height: int,
    source_kind: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal execution hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    ed = str(execution_digest or "").strip() or ("0" * 64)
    sr = str(state_root or "").strip() or ("0" * 64)
    material = (
        f"execution|{int(bool(short_circuit))}|{int(state_height)}|"
        f"{str(source_kind or '')}|{sr}|{ed}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "state_height": int(state_height),
        "state_root": sr,
        "source_kind": str(source_kind or ""),
        "execution_digest": ed,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_execution": True,
        "irreversible": True,
        "post_finality": True,
        "deterministic": True,
    }


def annotate_total_spine_execution(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-consensus execution onto a total-spine result and rebind tip."""
    exec_digest = str(
        certificate.get("execution_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    state_root = str(certificate.get("state_root") or "")
    state_height = int(certificate.get("state_height") or 0)
    source_kind = str(certificate.get("source_kind") or "")
    chain = seal_total_spine_execution_chain(
        prior_tip=prior_tip,
        execution_digest=exec_digest,
        state_root=state_root,
        state_height=state_height,
        source_kind=source_kind,
        short_circuit=short_circuit,
    )
    exec_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{exec_tip}".encode("utf-8"))
    body["total_spine_execution"] = True
    body["total_spine_execution_impl"] = TOTAL_SPINE_EXECUTION_IMPL
    body["total_spine_execution_short_circuit"] = bool(short_circuit)
    body["total_spine_execution_irreversible"] = True
    body["total_spine_execution_post_finality"] = True
    body["total_spine_execution_deterministic"] = True
    body["total_spine_execution_certificate"] = dict(certificate)
    body["total_spine_execution_digest"] = exec_digest
    body["total_spine_execution_chain"] = chain
    body["total_spine_execution_tip"] = exec_tip
    body["total_spine_execution_bound_tip"] = bound
    body["total_spine_digest_pre_execution"] = prior_tip
    body["total_spine_state_root"] = state_root
    body["total_spine_state_height"] = state_height
    body["total_spine_state_applied"] = True
    body["total_spine_state_applied_ok"] = True
    body["total_spine_state_root_valid"] = bool(state_root)
    body["state_root"] = state_root
    body["state_height"] = state_height
    body["state_applied"] = True
    if certificate.get("execution_path"):
        body["total_spine_execution_path"] = certificate.get("execution_path")
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_execution_ok_short_circuit"
        if short_circuit
        else "total_spine_execution_ok"
    )
    body["ok"] = True
    return body


def _resolve_execution_source(
    source: Path | str | Mapping[str, Any] | None,
    body: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve federation/finality/execution source for world-state apply."""
    from blackhole_agent.upstream_control_engine import (
        StageRefused as EngineRefused,
        TOTAL_SPINE_FEDERATION_KIND,
        TOTAL_SPINE_FINALITY_KIND,
        load_total_spine_federation_certificate,
        load_total_spine_finality_certificate,
    )

    if isinstance(source, Mapping):
        kind = str(source.get("kind") or "")
        if kind == TOTAL_SPINE_EXECUTION_KIND or source.get(
            "total_spine_execution"
        ):
            return dict(source)
        if kind == TOTAL_SPINE_FEDERATION_KIND or source.get(
            "total_spine_federation"
        ):
            return dict(source)
        if kind == TOTAL_SPINE_FINALITY_KIND or source.get(
            "total_spine_finality"
        ):
            return dict(source)
        cert = (
            source.get("total_spine_federation_certificate")
            or source.get("total_spine_finality_certificate")
            or source.get("total_spine_execution_certificate")
        )
        if isinstance(cert, Mapping):
            return dict(cert)
        return dict(source)

    if source is not None:
        path = Path(source)
        try:
            return load_total_spine_execution_certificate(path)
        except EngineRefused as exc:
            if str(exc.verdict) == "total_spine_execution_tampered":
                raise
        except Exception:  # noqa: BLE001
            pass
        try:
            return load_total_spine_federation_certificate(path)
        except EngineRefused as exc:
            if str(exc.verdict) == "total_spine_federation_tampered":
                raise
        except Exception:  # noqa: BLE001
            pass
        return load_total_spine_finality_certificate(path)

    if body is not None:
        cert = (
            body.get("total_spine_federation_certificate")
            or body.get("total_spine_finality_certificate")
            or body.get("total_spine_execution_certificate")
        )
        if isinstance(cert, Mapping):
            return dict(cert)
        if body.get("total_spine_federation") or body.get("total_spine_finality"):
            return dict(body)
    raise EngineRefused(
        "total_spine_execution_source_missing",
        "execution requires a finality, federation, or spine source",
    )


def _source_kind_and_digest(
    source: Mapping[str, Any],
) -> tuple[str, str]:
    """Classify consensus source and extract its digest."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_FEDERATION_KIND,
        TOTAL_SPINE_FINALITY_KIND,
    )

    kind = str(source.get("kind") or "")
    if (
        kind == TOTAL_SPINE_FEDERATION_KIND
        or source.get("total_spine_federation")
        or source.get("quorum") is True
    ):
        digest = str(
            source.get("federation_digest")
            or source.get("certificate_hash")
            or source.get("total_spine_federation_digest")
            or ""
        )
        if source.get("quorum") is True or source.get("total_spine_quorum"):
            return "quorum", digest
        return "federation", digest
    if kind == TOTAL_SPINE_FINALITY_KIND or source.get("total_spine_finality"):
        digest = str(
            source.get("finality_digest")
            or source.get("certificate_hash")
            or source.get("total_spine_finality_digest")
            or ""
        )
        return "finality", digest
    if kind == TOTAL_SPINE_EXECUTION_KIND or source.get("total_spine_execution"):
        digest = str(
            source.get("execution_digest")
            or source.get("certificate_hash")
            or source.get("source_digest")
            or ""
        )
        return str(source.get("source_kind") or "execution"), digest
    digest = str(
        source.get("federation_digest")
        or source.get("finality_digest")
        or source.get("certificate_hash")
        or source.get("total_spine_digest")
        or ""
    )
    return "finality", digest


def builtin_total_spine_execution_proof() -> dict[str, Any]:
    """Hermetic proof: post-quorum world-state execution on absolute tower."""
    return _run_log_family_proof("execution")


def execute_total_spine(
    source: Path | str | Mapping[str, Any] | None = None,
    *,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    parent_state_root: str = "",
    state_height: int | None = None,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Apply post-consensus world-state on the absolute total spine."""
    return _apply_log_family(
        "execution",
        source,
        out_root=out_root,
        prior_tip=prior_tip,
        body=body,
        parent_state_root=parent_state_root,
        state_height=state_height,
        short_circuit=short_circuit,
    )


def _execution_apply_core(
    source: Path | str | Mapping[str, Any] | None = None,
    *,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    parent_state_root: str = "",
    state_height: int | None = None,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Execution apply core: project state root, finish through the engine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        StageRefused as EngineRefused,
    )

    if not TOTAL_SPINE_EXECUTION_IMPL:
        raise EngineRefused(
            "total_spine_execution_disabled",
            "TOTAL_SPINE_EXECUTION_IMPL is False",
        )

    resolved = _resolve_execution_source(source, body)
    if (
        str(resolved.get("kind") or "") == TOTAL_SPINE_EXECUTION_KIND
        or resolved.get("total_spine_execution_loaded")
    ) and resolved.get("state_root"):
        return _short_circuit_log_apply("execution", resolved, body, prior_tip)

    source_kind, source_digest = _source_kind_and_digest(resolved)
    if not source_digest:
        raise EngineRefused(
            "total_spine_execution_source_digest_missing",
            "execution source lacks a consensus digest",
        )
    if not bool(resolved.get("success", True)):
        raise EngineRefused(
            "total_spine_execution_source_not_success",
            "execution refuses non-success consensus source",
        )
    if resolved.get("irreversible") is False:
        raise EngineRefused(
            "total_spine_execution_source_not_irreversible",
            "execution requires irreversible consensus source",
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
    caps = list(
        resolved.get("capabilities")
        or (body or {}).get("total_spine_effect_capabilities")
        or []
    )
    if not caps and isinstance(resolved.get("origins"), list):
        seen: list[str] = []
        for row in resolved.get("origins") or []:
            if not isinstance(row, Mapping):
                continue
            for cap in row.get("capabilities") or []:
                c = str(cap).strip()
                if c and c not in seen:
                    seen.append(c)
        caps = seen

    origin_count = int(
        resolved.get("origin_count")
        or len(resolved.get("origins") or [])
        or (1 if source_kind == "finality" else 0)
    )
    quorum_met = bool(
        resolved.get("quorum_met")
        or resolved.get("total_spine_quorum_met")
        or (source_kind == "quorum")
    )
    effects_ok = bool(
        resolved.get("effects_ok", True)
        if "effects_ok" in resolved
        else (body or {}).get("total_spine_effects_ok", True)
    )
    contract_met = resolved.get("contract_met")
    if contract_met is None and body is not None:
        contract_met = body.get("total_spine_contract_met")

    height = int(state_height) if state_height is not None else 1
    parent = str(parent_state_root or "").strip()
    if height < 1:
        raise EngineRefused(
            "total_spine_execution_invalid_height",
            f"state_height must be >= 1 (got {height})",
        )
    if height == 1 and parent:
        parent = ""
    if height > 1 and not parent:
        raise EngineRefused(
            "total_spine_execution_parent_required",
            f"state_height={height} requires parent_state_root",
        )

    tip = str(
        prior_tip
        or (body or {}).get("total_spine_federation_bound_tip")
        or (body or {}).get("total_spine_finality_bound_tip")
        or (body or {}).get("total_spine_digest")
        or resolved.get("bound_tip")
        or resolved.get("operational_tip")
        or ""
    )

    exec_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_EXECUTION_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "source_kind": source_kind,
        "source_digest": source_digest,
        "prior_tip": tip,
        "parent_state_root": parent,
        "state_height": height,
        "capabilities": caps,
        "effects_ok": effects_ok,
        "contract_met": contract_met,
        "origin_count": origin_count,
        "quorum_met": quorum_met,
        "post_finality": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "executed_at": utc_now_iso(),
    }
    exec_body["state_root"] = compute_total_spine_state_root(exec_body)
    return _finish_log_apply(
        "execution",
        cert_body=exec_body,
        out_root=out_root,
        body=body,
        prior_tip=tip,
        short_circuit=short_circuit,
        extra={
            "total_spine_execution_source_kind": source_kind,
            "total_spine_execution_source_digest": source_digest,
        },
    )


# ---------------------------------------------------------------------------
# Spec-driven certificate seal/verify. Public family names stay thin wrappers.
# ---------------------------------------------------------------------------


def _actuation_row_material(
    row: Mapping[str, Any], idx: int, parent: str
) -> dict[str, Any]:
    return {
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


def _settlement_row_material(
    row: Mapping[str, Any], idx: int, parent: str
) -> dict[str, Any]:
    return {
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


def _clearing_row_material(
    row: Mapping[str, Any], idx: int, parent: str
) -> dict[str, Any]:
    return {
        "settlement_index": int(row.get("settlement_index") or idx),
        "settlement_height": int(row.get("settlement_height") or (idx + 1)),
        "settlement_digest": str(row.get("settlement_digest") or ""),
        "bound_settlement_root": str(row.get("bound_settlement_root") or ""),
        "bound_state_root": str(row.get("bound_state_root") or ""),
        "bound_action_root": str(row.get("bound_action_root") or ""),
        "actuation_digest": str(row.get("actuation_digest") or ""),
        "observation_count": int(row.get("observation_count") or 0),
        "observation_signature": str(row.get("observation_signature") or ""),
        "observations_ok": bool(row.get("observations_ok", True)),
        "net_ok": bool(row.get("net_ok", True)),
        "discharged": bool(row.get("discharged", True)),
        "residual": int(row.get("residual") or 0),
        "independent": bool(row.get("independent", True)),
        "parent_clearing_root": parent,
        "post_settlement": True,
        "deterministic": True,
    }


def _settlement_rows_ok(rows: Sequence[Any]) -> bool:
    return all(
        isinstance(row, Mapping) and bool(row.get("observed_ok", True))
        for row in rows
    )


def _clearing_rows_ok(rows: Sequence[Any]) -> bool:
    return all(
        isinstance(row, Mapping)
        and bool(row.get("net_ok", True))
        and bool(row.get("discharged", True))
        and int(row.get("residual") or 0) == 0
        for row in rows
    )


def _log_family_spec(name: str) -> LogFamilySpec:
    spec = LOG_FAMILY_SPECS.get(name)
    if spec is None:
        raise KeyError(name)
    return spec


def _seal_log_certificate(name: str, body: Mapping[str, Any]) -> dict[str, Any]:
    """Seal one log-family certificate from :data:`LOG_FAMILY_SPECS`."""

    spec = _log_family_spec(name)
    host = sys.modules[__name__]
    material_fn = getattr(host, spec.material_fn)
    tip_fn = getattr(host, spec.tip_fn)
    impl = getattr(host, spec.impl_flag)
    hasher = _sha256_json_compact if spec.digest_style == "compact" else _sha256_json
    sealed_body = dict(body)
    if spec.shape == "state":
        if not str(sealed_body.get(spec.tip_key) or "").strip():
            sealed_body[spec.tip_key] = tip_fn(sealed_body)
    else:
        rows = list(sealed_body.get(spec.rows_key) or [])
        if not str(sealed_body.get(spec.tip_key) or "").strip():
            sealed_body[spec.tip_key] = tip_fn(rows)
        if spec.count_key and not int(sealed_body.get(spec.count_key) or 0):
            sealed_body[spec.count_key] = len(rows)
        if spec.height_key and not int(sealed_body.get(spec.height_key) or 0):
            sealed_body[spec.height_key] = len(rows)
    material = material_fn(sealed_body)
    material[spec.tip_key] = str(sealed_body.get(spec.tip_key) or "")
    digest = hasher(material)
    sealed = dict(material)
    sealed[spec.digest_key] = digest
    sealed["certificate_hash"] = digest
    sealed[f"total_spine_{spec.name}"] = True
    sealed[f"total_spine_{spec.name}_impl"] = impl
    sealed[spec.timestamp_key] = str(body.get(spec.timestamp_key) or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    for key in spec.carry_keys:
        value = body.get(key)
        if isinstance(value, list) and value:
            sealed[key] = [
                dict(row) if isinstance(row, Mapping) else row for row in value
            ]
    return sealed


def _verify_state_certificate(
    spec: LogFamilySpec, certificate: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify a single-state family (execution); fail closed on tamper."""

    host = sys.modules[__name__]
    material_fn = getattr(host, spec.material_fn)
    tip_fn = getattr(host, spec.tip_fn)
    impl = getattr(host, spec.impl_flag)
    hasher = _sha256_json_compact if spec.digest_style == "compact" else _sha256_json
    claimed = str(
        certificate.get(spec.digest_key)
        or certificate.get("certificate_hash")
        or ""
    )
    material = material_fn(certificate)
    expected = hasher(material)
    recomputed_root = tip_fn(certificate)
    claimed_root = str(certificate.get(spec.tip_key) or "")
    height = int(certificate.get(spec.height_key) or 0)
    parent = str(certificate.get(spec.parent_key) or "")
    parent_ok = (height == 1 and not parent) or (height > 1 and bool(parent))
    required_ok = all(
        bool(str(certificate.get(field) or "").strip())
        for field in spec.required_nonempty
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == spec.kind
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get(spec.post_flag) is True
        and certificate.get("deterministic") is True
        and bool(certificate.get("success"))
        and height >= 1
        and bool(claimed_root)
        and claimed_root == recomputed_root
        and parent_ok
        and required_ok
        and impl is True
    )
    return {
        "ok": ok,
        "action": f"verify_total_spine_{spec.name}",
        "claimed_digest": claimed,
        "expected_digest": expected,
        spec.verify_root_ok_key: claimed_root == recomputed_root and bool(claimed_root),
        spec.verify_recomputed_key: recomputed_root,
        "parent_ok": parent_ok,
        "kind_ok": str(certificate.get("kind") or "") == spec.kind,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        f"total_spine_{spec.name}": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def _verify_log_certificate(
    name: str, certificate: Mapping[str, Any]
) -> dict[str, Any]:
    """Recompute digest and row roots for one log family; fail closed on tamper."""

    spec = _log_family_spec(name)
    if spec.shape == "state":
        return _verify_state_certificate(spec, certificate)
    host = sys.modules[__name__]
    material_fn = getattr(host, spec.material_fn)
    tip_fn = getattr(host, spec.tip_fn)
    row_material_fn = getattr(host, spec.row_material_fn)
    impl = getattr(host, spec.impl_flag)
    claimed = str(
        certificate.get(spec.digest_key)
        or certificate.get("certificate_hash")
        or ""
    )
    material = material_fn(certificate)
    expected = _sha256_json(material)
    rows = list(certificate.get(spec.rows_key) or [])
    recomputed_tip = tip_fn(rows)
    claimed_tip = str(certificate.get(spec.tip_key) or "")
    height = int(certificate.get(spec.height_key) or 0)
    count = int(certificate.get(spec.count_key) or 0)
    cert_parent = str(certificate.get(spec.parent_key) or "")
    bind_expected = {
        field: str(certificate.get(field) or "") for field in spec.bind_fields
    }
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(rows):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if any(
            str(row.get(field) or "") != expected_value
            for field, expected_value in bind_expected.items()
        ):
            chain_ok = False
            break
        if str(row.get(spec.parent_key) or "") != parent:
            chain_ok = False
            break
        if spec.book_sig_field:
            sig = str(row.get(spec.book_sig_field) or "")
            if not book_sig:
                book_sig = sig
            elif sig != book_sig:
                chain_ok = False
                break
        material_row = row_material_fn(row, idx, parent)
        expected_root = _sha256_json(material_row)
        if str(row.get(spec.row_root_key) or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= spec.min_value and height >= count
    rows_ok = True
    if spec.rows_ok_fn:
        rows_ok = bool(getattr(host, spec.rows_ok_fn)(rows))
    required_ok = all(
        bool(str(certificate.get(field) or "").strip())
        for field in spec.required_nonempty
    )
    flags_ok = all(certificate.get(flag) is True for flag in spec.required_true)
    zeros_ok = all(int(certificate.get(field) or 0) == 0 for field in spec.required_zero)
    exec_ok = True
    if spec.require_execution_digest:
        exec_ok = bool(str(certificate.get("execution_digest") or "").strip())
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == spec.kind
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get(spec.post_flag) is True
        and certificate.get("deterministic") is True
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(rows)
        and height >= count
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and rows_ok
        and required_ok
        and flags_ok
        and zeros_ok
        and exec_ok
        and impl is True
    )
    result: dict[str, Any] = {
        "ok": ok,
        "action": f"verify_total_spine_{spec.name}",
        "claimed_digest": claimed,
        "expected_digest": expected,
        spec.verify_root_ok_key: claimed_tip == recomputed_tip and bool(claimed_tip),
        spec.verify_recomputed_key: recomputed_tip,
        "chain_ok": chain_ok,
        spec.verify_min_ok_key: min_ok,
        "kind_ok": str(certificate.get("kind") or "") == spec.kind,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        f"total_spine_{spec.name}": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }
    if spec.verify_rows_ok_key:
        result[spec.verify_rows_ok_key] = rows_ok
    for out_key, cert_key in spec.verify_flag_keys:
        result[out_key] = certificate.get(cert_key) is True
    return result


def builtin_log_family_engine_proof() -> dict[str, Any]:
    """Hermetic proof: four log families share one seal/verify engine."""

    import inspect
    import tempfile

    host = sys.modules[__name__]
    checks: dict[str, bool] = {}
    wired: dict[str, bool] = {}
    for name in ("execution", "actuation", "settlement", "clearing"):
        seal_fn = getattr(host, f"seal_total_spine_{name}_certificate")
        verify_fn = getattr(host, f"verify_total_spine_{name}_certificate")
        wired[f"{name}_seal"] = "_seal_log_certificate" in inspect.getsource(seal_fn)
        wired[f"{name}_verify"] = "_verify_log_certificate" in inspect.getsource(
            verify_fn
        )
    checks["wired_wrappers"] = all(wired.values())
    checks["four_specs"] = set(LOG_FAMILY_SPECS) == {
        "execution",
        "actuation",
        "settlement",
        "clearing",
    }
    checks["execution_state_shape"] = LOG_FAMILY_SPECS["execution"].shape == "state"
    checks["execution_compact_digest"] = (
        LOG_FAMILY_SPECS["execution"].digest_style == "compact"
    )
    checks["row_shapes"] = all(
        LOG_FAMILY_SPECS[name].shape == "rows"
        for name in ("actuation", "settlement", "clearing")
    )
    checks["shared_seal"] = callable(_seal_log_certificate)
    checks["shared_verify"] = callable(_verify_log_certificate)
    checks["shared_state_verify"] = callable(_verify_state_certificate)

    exec_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_EXECUTION_KIND,
        "root_layer": TOTAL_SPINE_DEFAULT_ROOT,
        "goal": "log-family-execution",
        "done_when": "min_proved:1; no_skill_route",
        "source_kind": "quorum",
        "source_digest": "d" * 64,
        "prior_tip": "a" * 64,
        "parent_state_root": "",
        "state_height": 1,
        "capabilities": ["repo.import-health"],
        "effects_ok": True,
        "contract_met": True,
        "origin_count": 3,
        "quorum_met": True,
        "post_finality": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "executed_at": "2026-08-15T00:00:00+00:00",
    }
    sealed_exec = seal_total_spine_execution_certificate(exec_body)
    generic_exec = _seal_log_certificate("execution", exec_body)
    exec_verify = verify_total_spine_execution_certificate(sealed_exec)
    checks["execution_seal_matches"] = (
        sealed_exec.get("execution_digest") == generic_exec.get("execution_digest")
        and bool(sealed_exec.get("execution_digest"))
    )
    checks["execution_verify_ok"] = exec_verify.get("ok") is True
    checks["execution_parent_ok"] = exec_verify.get("parent_ok") is True
    tampered_exec = dict(sealed_exec)
    tampered_exec["source_digest"] = "t" * 64
    checks["execution_tamper_closed"] = (
        verify_total_spine_execution_certificate(tampered_exec).get("ok") is False
    )

    state_root = "s" * 64
    execution_digest = "e" * 64
    actions = build_total_spine_action_log(
        capabilities=list(TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES),
        bound_state_root=state_root,
        execution_digest=execution_digest,
    )
    act_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_ACTUATION_KIND,
        "root_layer": TOTAL_SPINE_DEFAULT_ROOT,
        "bound_state_root": state_root,
        "bound_state_height": 1,
        "execution_digest": execution_digest,
        "actions": actions,
        "capabilities": [str(row.get("capability_id") or "") for row in actions],
        "effects_applied": True,
        "effects_ok": True,
        "post_execution": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
    }
    sealed_act = seal_total_spine_actuation_certificate(act_body)
    generic_act = _seal_log_certificate("actuation", act_body)
    act_verify = verify_total_spine_actuation_certificate(sealed_act)
    checks["actuation_seal_matches"] = (
        sealed_act.get("actuation_digest") == generic_act.get("actuation_digest")
        and bool(sealed_act.get("actuation_digest"))
    )
    checks["actuation_verify_ok"] = act_verify.get("ok") is True
    tampered_act = dict(sealed_act)
    tampered_act["bound_state_root"] = "t" * 64
    checks["actuation_tamper_closed"] = (
        verify_total_spine_actuation_certificate(tampered_act).get("ok") is False
    )

    observations = observe_total_spine_actions(
        actions=actions,
        actuation_digest=str(sealed_act.get("actuation_digest") or ""),
        bound_state_root=state_root,
    )
    set_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_SETTLEMENT_KIND,
        "root_layer": TOTAL_SPINE_DEFAULT_ROOT,
        "bound_state_root": state_root,
        "bound_action_root": str(sealed_act.get("tip_action_root") or ""),
        "actuation_digest": str(sealed_act.get("actuation_digest") or ""),
        "execution_digest": execution_digest,
        "actions": list(sealed_act.get("actions") or []),
        "observations": observations,
        "capabilities": [str(row.get("capability_id") or "") for row in observations],
        "contract_met": True,
        "contract_machine": False,
        "settled": True,
        "observations_ok": True,
        "effects_ok": True,
        "post_actuation": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
    }
    sealed_set = seal_total_spine_settlement_certificate(set_body)
    generic_set = _seal_log_certificate("settlement", set_body)
    set_verify = verify_total_spine_settlement_certificate(sealed_set)
    checks["settlement_seal_matches"] = (
        sealed_set.get("settlement_digest") == generic_set.get("settlement_digest")
        and bool(sealed_set.get("settlement_digest"))
    )
    checks["settlement_verify_ok"] = set_verify.get("ok") is True
    checks["settlement_carries_actions"] = bool(sealed_set.get("actions"))
    tampered_set = dict(sealed_set)
    tampered_set["bound_action_root"] = "x" * 64
    checks["settlement_tamper_closed"] = (
        verify_total_spine_settlement_certificate(tampered_set).get("ok") is False
    )

    peer = dict(sealed_set)
    peer["settled_at"] = "peer"
    sealed_peer = seal_total_spine_settlement_certificate(peer)
    legs = net_total_spine_settlements([sealed_set, sealed_peer])
    clr_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_CLEARING_KIND,
        "root_layer": TOTAL_SPINE_DEFAULT_ROOT,
        "bound_state_root": state_root,
        "bound_action_root": str(sealed_set.get("bound_action_root") or ""),
        "actuation_digest": str(sealed_set.get("actuation_digest") or ""),
        "bound_settlement_root": str(sealed_set.get("tip_settlement_root") or ""),
        "settlement_digest": str(sealed_set.get("settlement_digest") or ""),
        "clearings": legs,
        "gross_count": 2,
        "net_count": 2,
        "residual": 0,
        "capabilities": list(sealed_set.get("capabilities") or []),
        "contract_met": True,
        "contract_machine": False,
        "cleared": True,
        "clearings_ok": True,
        "settlements_ok": True,
        "net_ok": True,
        "discharged": True,
        "post_settlement": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
    }
    sealed_clr = seal_total_spine_clearing_certificate(clr_body)
    generic_clr = _seal_log_certificate("clearing", clr_body)
    clr_verify = verify_total_spine_clearing_certificate(sealed_clr)
    checks["clearing_seal_matches"] = (
        sealed_clr.get("clearing_digest") == generic_clr.get("clearing_digest")
        and bool(sealed_clr.get("clearing_digest"))
    )
    checks["clearing_verify_ok"] = clr_verify.get("ok") is True
    tampered_clr = dict(sealed_clr)
    tampered_clr["residual"] = 1
    checks["clearing_tamper_closed"] = (
        verify_total_spine_clearing_certificate(tampered_clr).get("ok") is False
    )

    with tempfile.TemporaryDirectory(prefix="blackhole-log-family-") as tmp:
        root = Path(tmp)
        written = write_total_spine_actuation_certificate(root, act_body)
        loaded = load_total_spine_actuation_certificate(root)
        checks["actuation_roundtrip"] = (
            loaded.get("actuation_digest") == written.get("actuation_digest")
            and loaded.get("total_spine_actuation_loaded") is True
        )

    checks["no_skill_route"] = not legacy_pipeline_was_used()
    wired_count = sum(1 for ok in wired.values() if ok)
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "log_family_engine_proof",
        "ok": all(checks.values()) and wired_count == 8,
        "checks": checks,
        "wired": wired,
        "wired_count": wired_count,
        "families": sorted(LOG_FAMILY_SPECS),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def _hosted_execution_family_proof() -> dict[str, Any]:
    """Hermetic proof: post-quorum world-state execution on absolute tower.

    Closes the certificate-only cliff: after N-of-M quorum federation seals
    irreversible consensus, ``execute_total_spine`` / ``run_total_spine(
    execution=True)`` projects deterministic hash-chained state roots, seals
    re-verifiable execution certificates, refuses supersession, short-circuits
    on re-execute, chains multi-height state, and rebinds the depth-28 tip
    without skill-route discovery.
    """
    import tempfile
    import shutil
    scratch = Path(tempfile.mkdtemp(prefix="total-spine-execution-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade
        import tempfile

        from blackhole_agent.capability_compounder import (
            default_ledger_path,
            load_ledger,
        )
        from blackhole_agent.upstream_control_engine import (
            SCHEMA_VERSION,
            TOTAL_SPINE_ADAPTIVE_IMPL,
            TOTAL_SPINE_CONTINUITY_IMPL,
            TOTAL_SPINE_EFFECT_IMPL,
            TOTAL_SPINE_FEDERATION_IMPL,
            TOTAL_SPINE_FINALITY_IMPL,
            TOTAL_SPINE_FINALITY_KIND,
            TOTAL_SPINE_GOAL_IMPL,
            TOTAL_SPINE_IMPL,
            TOTAL_SPINE_QUORUM_IMPL,
            StageRefused as EngineRefused,
            _facade_surface_ok,
            federate_total_spine,
            run_total_spine,
            write_total_spine_finality_certificate,
        )
        from blackhole_agent import upstream_control_engine as uce

        flags_ok = (
            TOTAL_SPINE_EXECUTION_IMPL is True
            and TOTAL_SPINE_QUORUM_IMPL is True
            and TOTAL_SPINE_FEDERATION_IMPL is True
            and TOTAL_SPINE_FINALITY_IMPL is True
            and TOTAL_SPINE_CONTINUITY_IMPL is True
            and TOTAL_SPINE_ADAPTIVE_IMPL is True
            and TOTAL_SPINE_GOAL_IMPL is True
            and TOTAL_SPINE_EFFECT_IMPL is True
            and TOTAL_SPINE_IMPL is True
            and TOTAL_SPINE_EXECUTION_KIND == "total_spine_execution"
            and bool(TOTAL_SPINE_EXECUTION_FILENAME)
        )

        missing_id = "capability.does-not-exist-for-execution-proof"
        good_id = "repo.import-health"
        contract_pass = "min_proved:1; no_skill_route"
        contract_byzantine = "min_proved:99; no_skill_route"

        # Phase 1: live absolute tower seals finality for honest origin A.
        partial = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "origin-a-partial",
            max_rounds=2,
            dispatch=True,
            dispatch_budget=3,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[missing_id, good_id],
            done_when=contract_pass,
            adaptive=True,
            adaptive_rounds=1,
            continuity=True,
            finality=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        partial_path = partial.get("total_spine_continuity_checkpoint_path")
        origin_a = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "origin-a",
            max_rounds=2,
            dispatch=True,
            dispatch_budget=3,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[missing_id, good_id],
            done_when=contract_pass,
            adaptive=True,
            adaptive_rounds=1,
            continuity=True,
            finality=True,
            resume_dir=partial_path,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        origin_a_path = origin_a.get("total_spine_finality_path")
        origin_a_ok = (
            bool(origin_a.get("ok"))
            and origin_a.get("total_spine_finality") is True
            and origin_a.get("total_spine_finality_irreversible") is True
            and origin_a.get("total_spine_effects_ok") is True
            and origin_a.get("total_spine_contract_met") is True
            and int(origin_a.get("total_nest_depth") or 0) == 28
            and isinstance(origin_a_path, str)
            and Path(origin_a_path).is_file()
            and not legacy_pipeline_was_used()
        )

        # Phase 2: honest peer B + Byzantine peer C (hard-conflicts done_when).
        peer_b_body = {
            "schema_version": SCHEMA_VERSION,
            "kind": TOTAL_SPINE_FINALITY_KIND,
            "root_layer": "quettacontinuum",
            "goal": str(
                (origin_a.get("total_spine_finality_certificate") or {}).get(
                    "goal"
                )
                or ""
            ),
            "done_when": contract_pass,
            "capabilities": [good_id],
            "operational_tip": "b" * 64,
            "bound_tip": "c" * 64,
            "continuity_digest": "d" * 64,
            "adaptive_round_count": 1,
            "effects_ok": True,
            "contract_met": True,
            "recovered": True,
            "irreversible": True,
            "success": True,
            "finalized_at": utc_now_iso(),
        }
        peer_b_cert = write_total_spine_finality_certificate(
            scratch / "origin-b", peer_b_body
        )
        peer_b_path = peer_b_cert.get("finality_path")
        peer_c_body = dict(peer_b_body)
        peer_c_body["done_when"] = contract_byzantine
        peer_c_body["operational_tip"] = "e" * 64
        peer_c_body["bound_tip"] = "f" * 64
        peer_c_cert = write_total_spine_finality_certificate(
            scratch / "origin-c", peer_c_body
        )
        peer_c_path = peer_c_cert.get("finality_path")
        peers_ok = (
            isinstance(peer_b_path, str)
            and Path(peer_b_path).is_file()
            and isinstance(peer_c_path, str)
            and Path(peer_c_path).is_file()
        )

        # Phase 3: offline quorum then execute world-state height 1.
        quorumed = federate_total_spine(
            [str(origin_a_path), str(peer_b_path), str(peer_c_path)],
            out_root=scratch / "quorum",
            prior_tip=str(origin_a.get("total_spine_finality_bound_tip") or ""),
            quorum=True,
        )
        quorum_path = quorumed.get("total_spine_federation_path")
        executed = execute_total_spine(
            quorumed.get("total_spine_federation_certificate") or quorum_path,
            out_root=scratch / "exec-h1",
            prior_tip=str(
                quorumed.get("total_spine_federation_bound_tip")
                or quorumed.get("total_spine_digest")
                or ""
            ),
            body={
                "ok": True,
                "total_spine": True,
                "total_spine_root": "quettacontinuum",
                "total_spine_compressed": True,
                "total_nest_depth": 28,
                "total_spine_federation": True,
                "total_spine_quorum": True,
                "total_spine_quorum_met": True,
                "total_spine_federation_certificate": quorumed.get(
                    "total_spine_federation_certificate"
                ),
                "total_spine_federation_bound_tip": quorumed.get(
                    "total_spine_federation_bound_tip"
                ),
                "total_spine_digest": quorumed.get("total_spine_digest"),
                "institution_digest": origin_a.get("institution_digest"),
            },
            state_height=1,
        )
        exec_path = executed.get("total_spine_execution_path")
        state_root_1 = str(executed.get("total_spine_state_root") or "")
        offline_exec_ok = (
            bool(executed.get("ok"))
            and executed.get("total_spine_execution") is True
            and executed.get("total_spine_state_applied") is True
            and executed.get("total_spine_execution_deterministic") is True
            and executed.get("total_spine_execution_post_finality") is True
            and executed.get("total_spine_execution_irreversible") is True
            and int(executed.get("total_spine_state_height") or 0) == 1
            and len(state_root_1) >= 32
            and str(executed.get("total_spine_execution_source_kind") or "")
            == "quorum"
            and isinstance(exec_path, str)
            and Path(exec_path).is_file()
            and isinstance(executed.get("total_spine_execution_digest"), str)
            and len(str(executed.get("total_spine_execution_digest"))) >= 32
            and str(executed.get("total_spine_digest") or "")
            != str(quorumed.get("total_spine_digest") or "")
            and not legacy_pipeline_was_used()
        )

        # Load + verify; tamper fails.
        loaded = load_total_spine_execution_certificate(exec_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_execution_loaded")
            and (loaded.get("execution_verify") or {}).get("ok")
            and (loaded.get("execution_verify") or {}).get("state_root_ok")
        )
        tampered_path = scratch / "tampered-execution.json"
        tampered_body = dict(loaded)
        for drop in (
            "execution_verify",
            "total_spine_execution_loaded",
            "execution_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["state_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_execution_certificate(tampered_path)
        except EngineRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_execution_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        # Supersession refused on divergent reseal.
        supersession_ok = False
        try:
            write_total_spine_execution_certificate(
                scratch / "exec-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "execution_verify",
                            "total_spine_execution_loaded",
                            "execution_path",
                            "execution_digest",
                            "certificate_hash",
                            "executed_at",
                            "total_spine_execution",
                            "total_spine_execution_impl",
                            "used_skill_route_discovery",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "state_root": "",  # force recompute
                },
            )
        except EngineRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_execution_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        # Multi-height chain: height 2 parented on height 1 state root.
        executed_h2 = execute_total_spine(
            quorumed.get("total_spine_federation_certificate") or quorum_path,
            out_root=scratch / "exec-h2",
            prior_tip=str(executed.get("total_spine_execution_bound_tip") or ""),
            parent_state_root=state_root_1,
            state_height=2,
            body={
                "ok": True,
                "total_spine": True,
                "total_spine_root": "quettacontinuum",
                "total_spine_compressed": True,
                "total_nest_depth": 28,
                "total_spine_federation_certificate": quorumed.get(
                    "total_spine_federation_certificate"
                ),
            },
        )
        state_root_2 = str(executed_h2.get("total_spine_state_root") or "")
        multi_height_ok = (
            bool(executed_h2.get("ok"))
            and int(executed_h2.get("total_spine_state_height") or 0) == 2
            and state_root_2
            and state_root_2 != state_root_1
            and str(
                (
                    executed_h2.get("total_spine_execution_certificate") or {}
                ).get("parent_state_root")
                or ""
            )
            == state_root_1
        )

        # Determinism: recompute state root from certificate material.
        recomputed = compute_total_spine_state_root(loaded)
        determinism_ok = recomputed == state_root_1 and bool(recomputed)

        # Live run: resume finality + quorum peers + execution=True.
        live_exec = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-exec",
            max_rounds=2,
            dispatch=True,
            dispatch_budget=3,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[missing_id, good_id],
            done_when=contract_pass,
            adaptive=True,
            adaptive_rounds=1,
            continuity=True,
            finality=True,
            resume_dir=origin_a_path,
            federation_peers=[str(peer_b_path), str(peer_c_path)],
            federation_quorum=True,
            execution=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_exec_path = live_exec.get("total_spine_execution_path")
        live_ok = (
            bool(live_exec.get("ok"))
            and live_exec.get("total_spine") is True
            and live_exec.get("total_spine_finality") is True
            and live_exec.get("total_spine_finality_short_circuit") is True
            and live_exec.get("total_spine_federation") is True
            and live_exec.get("total_spine_quorum") is True
            and live_exec.get("total_spine_quorum_met") is True
            and live_exec.get("total_spine_execution") is True
            and live_exec.get("total_spine_state_applied") is True
            and int(live_exec.get("total_spine_state_height") or 0) >= 1
            and isinstance(live_exec.get("total_spine_state_root"), str)
            and len(str(live_exec.get("total_spine_state_root"))) >= 32
            and int(live_exec.get("total_nest_depth") or 0) == 28
            and isinstance(live_exec_path, str)
            and Path(live_exec_path).is_file()
            and not legacy_pipeline_was_used()
        )

        # Short-circuit re-execute: resume execution cert, no re-dispatch.
        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-exec",
            max_rounds=2,
            dispatch=True,
            dispatch_budget=3,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=[missing_id, good_id],
            done_when=contract_pass,
            adaptive=True,
            adaptive_rounds=1,
            continuity=True,
            finality=True,
            execution=True,
            resume_dir=live_exec_path or (scratch / "live-exec"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_execution") is True
            and shorted.get("total_spine_execution_short_circuit") is True
            and shorted.get("total_spine_state_applied") is True
            and str(shorted.get("total_spine_state_root") or "")
            == str(live_exec.get("total_spine_state_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        # Execution chain re-seal integrity.
        exec_chain = live_exec.get("total_spine_execution_chain") or {}
        chain_integrity_ok = False
        if isinstance(exec_chain, Mapping) and exec_chain:
            re_seal = seal_total_spine_execution_chain(
                prior_tip=str(exec_chain.get("prior_tip") or ""),
                execution_digest=str(exec_chain.get("execution_digest") or ""),
                state_root=str(exec_chain.get("state_root") or ""),
                state_height=int(exec_chain.get("state_height") or 0),
                source_kind=str(exec_chain.get("source_kind") or ""),
                short_circuit=bool(exec_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == exec_chain.get("digest")
                and re_seal.get("digest")
                == live_exec.get("total_spine_execution_tip")
            )

        # Differential: execution tip moves beyond quorum tip.
        differential_ok = (
            offline_exec_ok
            and live_ok
            and str(quorumed.get("total_spine_digest") or "")
            != str(executed.get("total_spine_digest") or "")
            and str(origin_a.get("total_spine_digest") or "")
            != str(live_exec.get("total_spine_digest") or "")
        )

        # Finality-only execution (no federation) still works.
        fin_only = execute_total_spine(
            origin_a_path,
            out_root=scratch / "exec-finality-only",
            prior_tip=str(origin_a.get("total_spine_finality_bound_tip") or ""),
        )
        finality_only_ok = (
            bool(fin_only.get("ok"))
            and fin_only.get("total_spine_execution") is True
            and str(fin_only.get("total_spine_execution_source_kind") or "")
            == "finality"
            and int(fin_only.get("total_spine_state_height") or 0) == 1
        )

        # Facade exposes this stage's surface (delegation identity;
        # source-text greps predate the thin PEP 562 facade).
        source_ok = _facade_surface_ok(
            le_facade, "TOTAL_SPINE_EXECUTION_IMPL", "builtin_total_spine_execution_proof", "execute_total_spine"
        )

        engine_path = Path(uce.__file__).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "def builtin_total_spine_execution_proof" in engine_text
            and "def execute_total_spine" in engine_text
            and "def compute_total_spine_state_root" in engine_text
            and "TOTAL_SPINE_EXECUTION_IMPL" in engine_text
            and "execution=True" in engine_text
            or "execution: bool = False" in engine_text
        )
        engine_source_ok = (
            "def builtin_total_spine_execution_proof" in engine_text
            and "def execute_total_spine" in engine_text
            and "def compute_total_spine_state_root" in engine_text
            and "TOTAL_SPINE_EXECUTION_IMPL" in engine_text
            and (
                "execution=True" in engine_text
                or "execution: bool = False" in engine_text
            )
            and "total_spine_execution_supersession_refused" in engine_text
            and "total_spine_execution_tampered" in engine_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-execution"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (
                (entry.capability_delta or "").lower() if entry else ""
            )
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and "upstream_control_engine" in (entry.entry or "")
                and "builtin_total_spine_execution_proof" in (entry.entry or "")
                and (
                    "execution" in tags_blob
                    or "execution" in name_blob
                    or "execution" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "state_root" in delta_blob
                    or "world-state" in delta_blob
                    or "world state" in delta_blob
                    or "post-quorum" in delta_blob
                    or "post_quorum" in delta_blob
                )
                and (
                    "execute_total_spine" in delta_blob
                    or "execution=true" in delta_blob
                    or "execution=True" in (entry.capability_delta or "")
                )
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        ok = all(
            [
                flags_ok,
                origin_a_ok,
                peers_ok,
                offline_exec_ok,
                verify_ok,
                tamper_ok,
                supersession_ok,
                multi_height_ok,
                determinism_ok,
                live_ok,
                short_ok,
                chain_integrity_ok,
                differential_ok,
                finality_only_ok,
                source_ok,
                engine_source_ok,
                ledger_ok,
                not legacy_pipeline_was_used(),
            ]
        )
        return {
            "ok": ok,
            "action": "total_spine_execution_proof",
            "flags_ok": flags_ok,
            "origin_a_ok": origin_a_ok,
            "origin_a_path": origin_a_path,
            "peers_ok": peers_ok,
            "offline_exec_ok": offline_exec_ok,
            "execution_path": exec_path,
            "state_root": state_root_1,
            "state_height": executed.get("total_spine_state_height"),
            "source_kind": executed.get("total_spine_execution_source_kind"),
            "execution_digest": executed.get("total_spine_execution_digest"),
            "verify_ok": verify_ok,
            "tamper_ok": tamper_ok,
            "supersession_ok": supersession_ok,
            "multi_height_ok": multi_height_ok,
            "state_root_h2": state_root_2,
            "determinism_ok": determinism_ok,
            "live_ok": live_ok,
            "live_execution_path": live_exec_path,
            "live_state_root": live_exec.get("total_spine_state_root"),
            "live_digest": live_exec.get("total_spine_digest"),
            "short_ok": short_ok,
            "chain_integrity_ok": chain_integrity_ok,
            "differential_ok": differential_ok,
            "finality_only_ok": finality_only_ok,
            "source_ok": source_ok,
            "engine_source_ok": engine_source_ok,
            "ledger_capability_ok": ledger_ok,
            "used_skill_route_discovery": legacy_pipeline_was_used(),
            "control_engine": True,
            "total_spine": True,
            "total_spine_effects": True,
            "total_spine_adaptive": True,
            "total_spine_continuity": True,
            "total_spine_finality": True,
            "total_spine_federation": True,
            "total_spine_quorum": True,
            "total_spine_execution": True,
            "total_spine_compressed": True,
            "done_when_met": ok,
        }
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _apply_log_family(name: str, source: Any, **kwargs: Any) -> dict[str, Any]:
    """Dispatch one log-family apply through the spec-owned core."""

    spec = _log_family_spec(name)
    core = getattr(sys.modules[__name__], spec.apply_core_fn)
    return core(source, **kwargs)


def _short_circuit_log_apply(
    name: str,
    resolved: Mapping[str, Any],
    body: dict[str, Any] | None,
    prior_tip: str | None,
) -> dict[str, Any]:
    spec = _log_family_spec(name)
    annotate = getattr(sys.modules[__name__], f"annotate_total_spine_{name}")
    tip = str(
        prior_tip
        or resolved.get("prior_tip")
        or (body or {}).get("total_spine_digest")
        or ""
    )
    result = body if body is not None else {
        "ok": True,
        "action": f"{spec.verb}_total_spine",
        "total_spine": True,
    }
    return annotate(
        result,
        certificate=resolved,
        prior_tip=tip,
        short_circuit=True,
    )


def _finish_log_apply(
    name: str,
    *,
    cert_body: Mapping[str, Any],
    out_root: Path | None,
    body: dict[str, Any] | None,
    prior_tip: str,
    short_circuit: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Shared seal/write + annotate + compressed hop-chain tail."""

    from blackhole_agent.upstream_control_engine import (
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    host = sys.modules[__name__]
    write_fn = getattr(host, f"write_total_spine_{name}_certificate")
    seal_fn = getattr(host, f"seal_total_spine_{name}_certificate")
    annotate = getattr(host, f"annotate_total_spine_{name}")
    spec = _log_family_spec(name)
    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_fn(write_target, cert_body)
    else:
        certificate = seal_fn(cert_body)
    root_layer = str(cert_body.get("root_layer") or "")
    result = body if body is not None else {
        "ok": True,
        "action": f"{spec.verb}_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate(
        result,
        certificate=certificate,
        prior_tip=prior_tip,
        short_circuit=short_circuit,
    )
    if annotated.get("total_spine_compressed") and root_layer:
        live_result = {
            "institution_digest": annotated.get("institution_digest") or prior_tip,
            "ok": True,
        }
        bound = str(annotated.get(f"total_spine_{name}_bound_tip") or prior_tip)
        hops = seal_total_spine_hop_chain(root_layer, live_result, tip=bound)
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    if extra:
        for key, value in extra.items():
            if key == "setdefault_actuation_certificate" and value:
                annotated.setdefault("total_spine_actuation_certificate", value)
            else:
                annotated[key] = value
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def _proof_write_origins(scratch: Path, origin_goal: str) -> list[str]:
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_FINALITY_KIND,
        write_total_spine_finality_certificate,
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
            "goal": origin_goal,
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
    return paths


def _proof_execute_tower(scratch: Path, paths: Sequence[str]) -> dict[str, Any]:
    from blackhole_agent.upstream_control_engine import (
        execute_total_spine,
        federate_total_spine,
    )

    quorumed = federate_total_spine(
        list(paths),
        out_root=scratch / "quorum",
        prior_tip="a" * 64,
        quorum=True,
    )
    executed = execute_total_spine(
        quorumed.get("total_spine_federation_certificate"),
        out_root=scratch / "exec-h1",
        prior_tip=str(quorumed.get("total_spine_federation_bound_tip") or ""),
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
    return {"quorumed": quorumed, "executed": executed}


def _proof_build_offline(
    name: str,
    scratch: Path,
    executed: Mapping[str, Any],
    quorumed: Mapping[str, Any],
) -> dict[str, Any]:
    """Family-specific predecessor + offline apply. Shared proof consumes this."""

    good_id = "repo.import-health"
    inv_id = "capability.ledger-inventory"
    if name == "actuation":
        offline = actuate_total_spine(
            executed.get("total_spine_execution_certificate")
            or executed.get("total_spine_execution_path"),
            out_root=scratch / "act-h1",
            prior_tip=str(executed.get("total_spine_execution_bound_tip") or ""),
            body=dict(executed),
            capabilities=[good_id, inv_id],
            repo_path=REPO_ROOT,
            effect_timeout=90,
            dispatch=True,
        )
        return {
            "offline": offline,
            "state_root": str(executed.get("total_spine_state_root") or ""),
            "pred_digest": str(executed.get("total_spine_digest") or ""),
            "multi_source": executed.get("total_spine_execution_certificate"),
            "multi_kwargs": {
                "dispatch": False,
                "capabilities": [good_id, inv_id],
                "repo_path": REPO_ROOT,
                "effect_timeout": 90,
            },
            "write_dir": scratch / "act-h1",
            "executed": executed,
            "quorumed": quorumed,
        }
    actuated = actuate_total_spine(
        executed.get("total_spine_execution_certificate")
        or executed.get("total_spine_execution_path"),
        out_root=scratch / "act-h1",
        prior_tip=str(executed.get("total_spine_execution_bound_tip") or ""),
        body=dict(executed),
        capabilities=[good_id, inv_id],
        repo_path=REPO_ROOT,
        effect_timeout=90,
        dispatch=True,
    )
    if name == "settlement":
        offline = settle_total_spine(
            actuated.get("total_spine_actuation_certificate")
            or actuated.get("total_spine_actuation_path"),
            out_root=scratch / "set-h1",
            prior_tip=str(actuated.get("total_spine_actuation_bound_tip") or ""),
            body=dict(actuated),
            repo_path=REPO_ROOT,
        )
        return {
            "offline": offline,
            "state_root": str(actuated.get("total_spine_state_root") or ""),
            "pred_digest": str(actuated.get("total_spine_digest") or ""),
            "tip_action": str(actuated.get("total_spine_tip_action_root") or ""),
            "multi_source": actuated.get("total_spine_actuation_certificate"),
            "multi_kwargs": {"repo_path": REPO_ROOT},
            "write_dir": scratch / "set-h1",
            "actuated": actuated,
            "executed": executed,
            "quorumed": quorumed,
        }
    settled = settle_total_spine(
        actuated.get("total_spine_actuation_certificate")
        or actuated.get("total_spine_actuation_path"),
        out_root=scratch / "set-h1",
        prior_tip=str(actuated.get("total_spine_actuation_bound_tip") or ""),
        body=dict(actuated),
        repo_path=REPO_ROOT,
    )
    tip_settlement = str(settled.get("total_spine_tip_settlement_root") or "")
    confirmed = settle_total_spine(
        actuated.get("total_spine_actuation_certificate"),
        out_root=scratch / "set-h2",
        prior_tip=str(settled.get("total_spine_settlement_bound_tip") or ""),
        parent_observation_root=tip_settlement,
        observation_height=int(settled.get("total_spine_observation_height") or 0)
        + 1,
        repo_path=REPO_ROOT,
    )
    s1 = settled.get("total_spine_settlement_certificate") or {}
    s2 = confirmed.get("total_spine_settlement_certificate") or {}
    offline = clear_total_spine(
        [s1, s2],
        out_root=scratch / "clr-h1",
        prior_tip=str(
            confirmed.get("total_spine_settlement_bound_tip")
            or settled.get("total_spine_settlement_bound_tip")
            or ""
        ),
        body=dict(confirmed),
        repo_path=REPO_ROOT,
        confirm=False,
    )
    return {
        "offline": offline,
        "state_root": str(settled.get("total_spine_state_root") or ""),
        "pred_digest": str(settled.get("total_spine_digest") or ""),
        "tip_action": str(settled.get("total_spine_tip_action_root") or ""),
        "tip_settlement": tip_settlement,
        "multi_source": [s1, s2],
        "multi_kwargs": {"repo_path": REPO_ROOT, "confirm": False},
        "write_dir": scratch / "clr-h1",
        "s1": s1,
        "s2": s2,
        "actuated": actuated,
        "settled": settled,
        "executed": executed,
        "quorumed": quorumed,
    }


def _run_log_family_proof(name: str) -> dict[str, Any]:
    """One hermetic proof runner for actuation, settlement, and clearing."""

    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import run_total_spine

    spec = _log_family_spec(name)
    if spec.shape == "state":
        return _hosted_execution_family_proof()
    host = sys.modules[__name__]
    apply_fn = getattr(host, spec.apply_fn)
    load_fn = getattr(host, f"load_total_spine_{name}_certificate")
    write_fn = getattr(host, f"write_total_spine_{name}_certificate")
    seal_fn = getattr(host, f"seal_total_spine_{name}_certificate")
    verify_fn = getattr(host, f"verify_total_spine_{name}_certificate")
    chain_fn = getattr(host, f"seal_total_spine_{name}_chain")
    tip_fn = getattr(host, spec.tip_fn)
    impl = getattr(host, spec.impl_flag)
    from blackhole_agent import upstream_control_engine as uce

    pred_impl = getattr(host, spec.pred_impl_flag, None)
    if pred_impl is None:
        pred_impl = getattr(uce, spec.pred_impl_flag, True)
    proof_fn = getattr(host, f"builtin_total_spine_{name}_proof")

    scratch = Path(tempfile.mkdtemp(prefix=spec.scratch_prefix))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            impl is True
            and pred_impl is True
            and spec.kind == f"total_spine_{name}"
            and bool(spec.filename)
            and spec.min_value >= 2
        )
        # Engine alias used by historical flags_ok (control-engine re-export).
        from blackhole_agent import upstream_control_engine as uce

        engine_impl = getattr(uce, spec.impl_flag, impl)
        flags_ok = flags_ok and engine_impl is True

        paths = _proof_write_origins(scratch, spec.proof_origin)
        tower = _proof_execute_tower(scratch, paths)
        built = _proof_build_offline(
            name, scratch, tower["executed"], tower["quorumed"]
        )
        offline = built["offline"]
        state_root = str(built["state_root"] or "")
        tip = str(offline.get(spec.result_tip_key) or "")
        path = offline.get(spec.result_path_key)
        offline_ok = (
            bool(offline.get("ok"))
            and all(offline.get(key) is True for key in spec.offline_true)
            and int(offline.get(spec.result_count_key) or 0) >= 2
            and int(offline.get(spec.result_height_key) or 0) >= 2
            and len(tip) >= 32
            and str(offline.get("total_spine_state_root") or "") == state_root
            and str(offline.get("total_spine_digest") or "")
            != str(built.get("pred_digest") or "")
            and isinstance(path, str)
            and Path(path).is_file()
            and not legacy_pipeline_was_used()
        )
        if name == "clearing":
            offline_ok = offline_ok and int(
                offline.get("total_spine_clearing_residual") or 0
            ) == 0
        if name in {"settlement", "clearing"}:
            offline_ok = offline_ok and str(
                offline.get("total_spine_tip_action_root") or ""
            ) == str(built.get("tip_action") or "")

        loaded = load_fn(path or scratch)
        verify_bag = loaded.get(spec.verify_bag_key) or {}
        verify_ok = bool(
            loaded.get(spec.loaded_key)
            and verify_bag.get("ok")
            and verify_bag.get("chain_ok")
            and all(verify_bag.get(key) for key in spec.verify_extra)
        )

        tampered_path = scratch / f"tampered-{name}.json"
        tampered_body = dict(loaded)
        for drop in (spec.verify_bag_key, spec.loaded_key, f"{name}_path"):
            tampered_body.pop(drop, None)
        tampered_body[spec.tamper_height_field] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_fn(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == f"total_spine_{name}_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_fn(
                built["write_dir"],
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k not in spec.supersession_drop
                    },
                    "goal": "forged-supersession-goal",
                    spec.tip_key: "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == f"total_spine_{name}_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_body = dict(loaded)
        for drop in (spec.verify_bag_key, spec.loaded_key, f"{name}_path"):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_fn(wrong_body)
        wrong_verify = verify_fn(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get(spec.verify_root_ok_key) is False
        )

        multi_kwargs = dict(built.get("multi_kwargs") or {})
        multi_kwargs.update(
            {
                "out_root": scratch / f"{spec.name[:3]}-h2",
                "prior_tip": str(offline.get(spec.result_bound_tip_key) or ""),
                spec.parent_kwarg: tip,
                spec.height_kwarg: int(offline.get(spec.result_height_key) or 0)
                + 1,
            }
        )
        h2 = apply_fn(built.get("multi_source"), **multi_kwargs)
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get(spec.result_count_key) or 0) >= 2
            and str(h2.get(spec.result_tip_key) or "") != tip
            and str(
                (h2.get(f"total_spine_{name}_certificate") or {}).get(
                    spec.parent_key
                )
                or ""
            )
            == tip
        )

        recomputed = tip_fn(loaded.get(spec.rows_key) or [])
        determinism_ok = recomputed == tip and bool(recomputed)

        extras: dict[str, bool] = {}
        if "unmet" in spec.extra_proofs:
            extras["unmet_ok"] = False
            try:
                fail_act = dict(
                    (built.get("actuated") or {}).get(
                        "total_spine_actuation_certificate"
                    )
                    or {}
                )
                fail_act["done_when"] = "min_proved:99999; no_skill_route"
                settle_total_spine(
                    fail_act,
                    out_root=scratch / "set-unmet",
                    prior_tip=str(
                        (built.get("actuated") or {}).get(
                            "total_spine_actuation_bound_tip"
                        )
                        or ""
                    ),
                    repo_path=REPO_ROOT,
                    require_contract=True,
                )
            except StageRefused as exc:
                extras["unmet_ok"] = (
                    str(exc.verdict) == "total_spine_settlement_contract_unmet"
                )
            except Exception:  # noqa: BLE001
                extras["unmet_ok"] = False
        if "mismatch" in spec.extra_proofs:
            extras["mismatch_ok"] = False
            try:
                from blackhole_agent.upstream_control_engine import (
                    execute_total_spine,
                )

                executed = built["executed"]
                quorumed = built["quorumed"]
                executed2 = execute_total_spine(
                    quorumed.get("total_spine_federation_certificate"),
                    out_root=scratch / "exec-h2",
                    prior_tip=str(
                        executed.get("total_spine_execution_bound_tip") or ""
                    ),
                    parent_state_root=state_root,
                    state_height=2,
                )
                actuated2 = actuate_total_spine(
                    executed2.get("total_spine_execution_certificate"),
                    out_root=scratch / "act-h2",
                    prior_tip=str(
                        executed2.get("total_spine_execution_bound_tip") or ""
                    ),
                    capabilities=["repo.import-health", "capability.ledger-inventory"],
                    repo_path=REPO_ROOT,
                    effect_timeout=90,
                    dispatch=True,
                )
                other = settle_total_spine(
                    actuated2.get("total_spine_actuation_certificate"),
                    out_root=scratch / "set-other",
                    prior_tip=str(
                        actuated2.get("total_spine_actuation_bound_tip") or ""
                    ),
                    repo_path=REPO_ROOT,
                )
                net_total_spine_settlements(
                    [
                        built.get("s1") or {},
                        other.get("total_spine_settlement_certificate") or {},
                    ],
                    min_clearings=2,
                )
            except StageRefused as exc:
                extras["mismatch_ok"] = (
                    str(exc.verdict) == "total_spine_clearing_root_mismatch"
                )
            except Exception:  # noqa: BLE001
                extras["mismatch_ok"] = False

        contract_pass = "min_proved:1; no_skill_route"
        live_kwargs = {
            flag: True for flag in spec.live_flags
        }
        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / f"live-{spec.name[:3]}",
            max_rounds=1,
            dispatch=True,
            dispatch_budget=2,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=["repo.import-health", "capability.ledger-inventory"],
            done_when=contract_pass,
            adaptive=False,
            continuity=False,
            finality=True,
            resume_dir=paths[0],
            federation_peers=[paths[1], paths[2]],
            federation_quorum=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
            **live_kwargs,
        )
        live_path = live.get(spec.result_path_key)
        live_ok = (
            bool(live.get("ok"))
            and live.get("total_spine") is True
            and all(live.get(key) is True for key in spec.live_true)
            and int(live.get(spec.result_count_key) or 0) >= 2
            and isinstance(live.get(spec.result_tip_key), str)
            and len(str(live.get(spec.result_tip_key))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_path, str)
            and Path(live_path).is_file()
            and not legacy_pipeline_was_used()
        )

        short_kwargs = {
            flag: True for flag in spec.live_flags
        }
        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / f"short-{spec.name[:3]}",
            max_rounds=1,
            dispatch=True,
            dispatch_budget=2,
            max_successions=1,
            max_epochs=1,
            max_waves=1,
            compress=True,
            effects=True,
            capabilities=["repo.import-health", "capability.ledger-inventory"],
            done_when=contract_pass,
            finality=True,
            resume_dir=live_path or (scratch / f"live-{spec.name[:3]}"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
            **short_kwargs,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get(f"total_spine_{name}") is True
            and shorted.get(spec.result_short_key) is True
            and str(shorted.get(spec.result_tip_key) or "")
            == str(live.get(spec.result_tip_key) or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        chain = live.get(spec.result_chain_key) or {}
        chain_integrity_ok = False
        if isinstance(chain, Mapping) and chain:
            reseal_kwargs: dict[str, Any] = {}
            for param, key, kind in spec.chain_params:
                raw = chain.get(key)
                if kind == "int":
                    reseal_kwargs[param] = int(raw or 0)
                elif kind == "bool":
                    reseal_kwargs[param] = bool(raw)
                else:
                    reseal_kwargs[param] = str(raw or "")
            re_seal = chain_fn(**reseal_kwargs)
            chain_integrity_ok = (
                re_seal.get("digest") == chain.get("digest")
                and re_seal.get("digest") == live.get(spec.result_tip_chain_key)
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(built.get("pred_digest") or "")
            != str(offline.get("total_spine_digest") or "")
        )

        source_ok = (
            getattr(le_facade, spec.impl_flag, None) is impl
            and getattr(le_facade, f"builtin_total_spine_{name}_proof", None)
            is proof_fn
            and getattr(le_facade, spec.apply_fn, None) is apply_fn
            and callable(getattr(le_facade, f"builtin_total_spine_{name}_proof", None))
            and callable(getattr(le_facade, spec.apply_fn, None))
            and getattr(le_facade, spec.impl_flag, False) is True
        )

        engine_path = Path(uce.__file__).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            getattr(uce, spec.impl_flag, None) is True
            and callable(getattr(uce, spec.apply_fn, None))
            and getattr(uce, spec.apply_fn, None) is apply_fn
            and callable(getattr(uce, spec.ledger_proof_needle, None))
            and (
                spec.engine_true_token in engine_text
                or spec.engine_sig_token in engine_text
            )
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            f"def {spec.apply_fn}" in mod_text
            and f"def builtin_total_spine_{name}_proof" in mod_text
            and all(needle in mod_text for needle in spec.mod_needles)
        )

        ledger_ok = False
        try:
            ledger = load_ledger(default_ledger_path(REPO_ROOT))
            entry = ledger.capabilities.get(spec.ledger_id)
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and any(needle in (entry.entry or "") for needle in spec.ledger_entry_needles)
                and spec.ledger_proof_needle in (entry.entry or "")
                and (
                    name in tags_blob
                    or name in name_blob
                    or name in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and any(needle in delta_blob for needle in spec.ledger_delta_needles)
            )
        except Exception:  # noqa: BLE001
            ledger_ok = False

        required = [
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
        required.extend(extras.values())
        ok = all(required)
        out: dict[str, Any] = {
            "ok": ok,
            "action": f"total_spine_{name}_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            spec.result_path_key.replace("total_spine_", "")
            if False
            else f"{name}_path": path,
            spec.result_tip_key.replace("total_spine_tip_", "tip_"): tip,
            "state_root": state_root,
            spec.return_count_key: offline.get(spec.result_count_key),
            "verify_ok": verify_ok,
            "tamper_ok": tamper_ok,
            "supersession_ok": supersession_ok,
            "wrong_root_ok": wrong_root_ok,
            "multi_height_ok": multi_height_ok,
            "determinism_ok": determinism_ok,
            "live_ok": live_ok,
            spec.live_path_out_key: live_path,
            spec.live_tip_out_key: live.get(spec.result_tip_key),
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
            f"total_spine_{name}": True,
            "total_spine_execution": True,
            "total_spine_quorum": True,
            "done_when_met": ok,
        }
        # Historical output keys: actuation_path / tip_action_root, etc.
        out[f"{name}_path"] = path
        out[spec.result_tip_key.replace("total_spine_tip_", "tip_")] = tip
        for out_key, ctx_key in spec.return_tip_keys:
            out[out_key] = built.get(ctx_key)
        if name == "settlement":
            out["tip_settlement_root"] = tip
            out["tip_action_root"] = built.get("tip_action")
            out["settlement_path"] = path
        if name == "actuation":
            out["actuation_path"] = path
            out["tip_action_root"] = tip
        if name == "clearing":
            out["clearing_path"] = path
            out["tip_clearing_root"] = tip
            out["tip_settlement_root"] = built.get("tip_settlement")
            out["tip_action_root"] = built.get("tip_action")
            out["total_spine_settlement"] = True
            out["total_spine_actuation"] = True
        if name == "settlement":
            out["total_spine_actuation"] = True
        out.update(extras)
        return out
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def builtin_log_family_runner_proof() -> dict[str, Any]:
    """Hermetic proof: apply + family proofs are one spec-driven runner."""

    import inspect

    host = sys.modules[__name__]
    checks: dict[str, bool] = {}
    wired: dict[str, bool] = {}
    row_specs = {
        name: spec
        for name, spec in LOG_FAMILY_SPECS.items()
        if spec.shape == "rows"
    }
    for name, spec in LOG_FAMILY_SPECS.items():
        apply_fn = getattr(host, spec.apply_fn)
        proof_fn = getattr(host, f"builtin_total_spine_{name}_proof")
        wired[f"{name}_apply"] = "_apply_log_family" in inspect.getsource(apply_fn)
        wired[f"{name}_proof"] = "_run_log_family_proof" in inspect.getsource(
            proof_fn
        )
        wired[f"{name}_core"] = callable(getattr(host, spec.apply_core_fn, None))
    checks["wired_wrappers"] = all(wired.values())
    checks["three_row_specs"] = set(row_specs) == {
        "actuation",
        "settlement",
        "clearing",
    }
    checks["catalog_includes_execution"] = "execution" in LOG_FAMILY_SPECS
    checks["execution_apply_wired"] = wired.get("execution_apply") is True
    checks["execution_proof_wired"] = wired.get("execution_proof") is True
    checks["shared_apply"] = callable(_apply_log_family)
    checks["shared_proof"] = callable(_run_log_family_proof)
    checks["shared_finish"] = callable(_finish_log_apply)

    # Cheap apply identity: short-circuit a sealed actuation through the runner.
    actions = build_total_spine_action_log(
        capabilities=list(TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES),
        bound_state_root="s" * 64,
        execution_digest="e" * 64,
    )
    sealed = seal_total_spine_actuation_certificate(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": TOTAL_SPINE_ACTUATION_KIND,
            "bound_state_root": "s" * 64,
            "bound_state_height": 1,
            "execution_digest": "e" * 64,
            "actions": actions,
            "effects_applied": True,
            "effects_ok": True,
            "post_execution": True,
            "deterministic": True,
            "irreversible": True,
            "success": True,
        }
    )
    shorted = _apply_log_family(
        "actuation",
        sealed,
        short_circuit=True,
        dispatch=False,
    )
    checks["apply_short_circuit"] = (
        shorted.get("total_spine_actuation") is True
        and shorted.get("total_spine_actuation_short_circuit") is True
        and shorted.get("ok") is True
    )
    exec_sealed = seal_total_spine_execution_certificate(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": TOTAL_SPINE_EXECUTION_KIND,
            "root_layer": TOTAL_SPINE_DEFAULT_ROOT,
            "source_kind": "quorum",
            "source_digest": "d" * 64,
            "prior_tip": "a" * 64,
            "parent_state_root": "",
            "state_height": 1,
            "capabilities": ["repo.import-health"],
            "effects_ok": True,
            "contract_met": True,
            "origin_count": 3,
            "quorum_met": True,
            "post_finality": True,
            "deterministic": True,
            "irreversible": True,
            "success": True,
            "executed_at": "2026-08-15T00:00:00+00:00",
        }
    )
    exec_shorted = _apply_log_family(
        "execution",
        exec_sealed,
        short_circuit=True,
    )
    checks["execution_apply_short_circuit"] = (
        exec_shorted.get("total_spine_execution") is True
        and exec_shorted.get("total_spine_execution_short_circuit") is True
        and exec_shorted.get("ok") is True
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()
    wired_count = sum(1 for ok in wired.values() if ok)
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "log_family_runner_proof",
        "ok": all(checks.values()) and wired_count == 12,
        "checks": checks,
        "wired": wired,
        "wired_count": wired_count,
        "families": sorted(LOG_FAMILY_SPECS),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }

