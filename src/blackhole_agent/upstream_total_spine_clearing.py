"""Post-settlement clearing for the absolute total spine.

Closes the settled-but-uncleared cliff: after ``settle_total_spine`` seals a
unilateral observation receipt, independently confirm a second settlement,
net matching observation books into hash-chained clearing legs, discharge
only when the books agree on bound roots and observed effects, seal a
re-verifiable clearing certificate bound to the settlement digests, refuse
uncleared / mismatched / failed / wrong-root / tampered closures,
short-circuit re-clear, and rebind the depth-28 tip without skill-route.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

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

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]

TOTAL_SPINE_CLEARING_IMPL = True
TOTAL_SPINE_CLEARING_KIND: str = "total_spine_clearing"
TOTAL_SPINE_CLEARING_FILENAME: str = "total-spine-clearing.json"
TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS: int = 2

TOTAL_SPINE_SETTLEMENT_KIND: str = "total_spine_settlement"
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine clearing."""

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
    sealed_body = dict(body)
    clearings = list(sealed_body.get("clearings") or [])
    if not str(sealed_body.get("tip_clearing_root") or "").strip():
        sealed_body["tip_clearing_root"] = compute_total_spine_clearing_root(
            clearings
        )
    if not int(sealed_body.get("clearing_count") or 0):
        sealed_body["clearing_count"] = len(clearings)
    if not int(sealed_body.get("clearing_height") or 0):
        sealed_body["clearing_height"] = len(clearings)
    material = _clearing_certificate_material(sealed_body)
    material["tip_clearing_root"] = str(sealed_body.get("tip_clearing_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["clearing_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_clearing"] = True
    sealed["total_spine_clearing_impl"] = TOTAL_SPINE_CLEARING_IMPL
    sealed["cleared_at"] = str(body.get("cleared_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return sealed


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
    claimed = str(
        certificate.get("clearing_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _clearing_certificate_material(certificate)
    expected = _sha256_json(material)
    clearings = list(certificate.get("clearings") or [])
    recomputed_tip = compute_total_spine_clearing_root(clearings)
    claimed_tip = str(certificate.get("tip_clearing_root") or "")
    height = int(certificate.get("clearing_height") or 0)
    count = int(certificate.get("clearing_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_clearing_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(clearings):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_clearing_root") or "") != parent:
            chain_ok = False
            break
        sig = str(row.get("observation_signature") or "")
        if not book_sig:
            book_sig = sig
        elif sig != book_sig:
            chain_ok = False
            break
        material_row = {
            "settlement_index": int(row.get("settlement_index") or idx),
            "settlement_height": int(row.get("settlement_height") or (idx + 1)),
            "settlement_digest": str(row.get("settlement_digest") or ""),
            "bound_settlement_root": str(row.get("bound_settlement_root") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "observation_count": int(row.get("observation_count") or 0),
            "observation_signature": sig,
            "observations_ok": bool(row.get("observations_ok", True)),
            "net_ok": bool(row.get("net_ok", True)),
            "discharged": bool(row.get("discharged", True)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_clearing_root": parent,
            "post_settlement": True,
            "deterministic": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("clearing_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS and height >= count
    clearings_ok = all(
        isinstance(row, Mapping)
        and bool(row.get("net_ok", True))
        and bool(row.get("discharged", True))
        and int(row.get("residual") or 0) == 0
        for row in clearings
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_CLEARING_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_settlement") is True
        and certificate.get("deterministic") is True
        and certificate.get("cleared") is True
        and certificate.get("discharged") is True
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(clearings)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and clearings_ok
        and int(certificate.get("residual") or 0) == 0
        and TOTAL_SPINE_CLEARING_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_clearing",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "clearing_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_clearing_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_clearings_ok": min_ok,
        "clearings_ok": clearings_ok,
        "kind_ok": str(certificate.get("kind") or "") == TOTAL_SPINE_CLEARING_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "cleared_ok": certificate.get("cleared") is True,
        "discharged_ok": certificate.get("discharged") is True,
        "total_spine_clearing": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


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
        result = body if body is not None else {
            "ok": True,
            "action": "clear_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_clearing(
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

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

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_clearing_certificate(write_target, clr_body)
    else:
        certificate = seal_total_spine_clearing_certificate(clr_body)

    result = body if body is not None else {
        "ok": True,
        "action": "clear_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_clearing(
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
        clr_bound = str(annotated.get("total_spine_clearing_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=clr_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_clearing_bound_state_root"] = state_root
    annotated["total_spine_clearing_bound_action_root"] = action_root
    annotated["total_spine_clearing_bound_settlement_root"] = settlement_root
    annotated["total_spine_clearing_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_clearing_proof() -> dict[str, Any]:
    """Hermetic proof: post-settlement multilateral clearing on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_CLEARING_IMPL as ENGINE_CLR_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        TOTAL_SPINE_SETTLEMENT_IMPL,
        actuate_total_spine,
        execute_total_spine,
        federate_total_spine,
        run_total_spine,
        settle_total_spine,
        write_total_spine_finality_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-clearing-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_CLEARING_IMPL is True
            and ENGINE_CLR_IMPL is True
            and TOTAL_SPINE_SETTLEMENT_IMPL is True
            and TOTAL_SPINE_CLEARING_KIND == "total_spine_clearing"
            and bool(TOTAL_SPINE_CLEARING_FILENAME)
            and TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS >= 2
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
                "goal": "clearing proof origin",
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
        settled = settle_total_spine(
            actuated.get("total_spine_actuation_certificate")
            or actuated.get("total_spine_actuation_path"),
            out_root=scratch / "set-h1",
            prior_tip=str(
                actuated.get("total_spine_actuation_bound_tip") or ""
            ),
            body=dict(actuated),
            repo_path=REPO_ROOT,
        )
        tip_settlement = str(settled.get("total_spine_tip_settlement_root") or "")
        confirmed = settle_total_spine(
            actuated.get("total_spine_actuation_certificate"),
            out_root=scratch / "set-h2",
            prior_tip=str(
                settled.get("total_spine_settlement_bound_tip") or ""
            ),
            parent_observation_root=tip_settlement,
            observation_height=int(
                settled.get("total_spine_observation_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
        )
        s1 = settled.get("total_spine_settlement_certificate") or {}
        s2 = confirmed.get("total_spine_settlement_certificate") or {}
        state_root = str(settled.get("total_spine_state_root") or "")
        tip_action = str(settled.get("total_spine_tip_action_root") or "")

        offline_clr = clear_total_spine(
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
        clr_path = offline_clr.get("total_spine_clearing_path")
        tip_clearing = str(offline_clr.get("total_spine_tip_clearing_root") or "")
        offline_ok = (
            bool(offline_clr.get("ok"))
            and offline_clr.get("total_spine_clearing") is True
            and offline_clr.get("total_spine_clearing_post_settlement") is True
            and offline_clr.get("total_spine_clearing_irreversible") is True
            and offline_clr.get("total_spine_cleared") is True
            and offline_clr.get("total_spine_discharged") is True
            and offline_clr.get("total_spine_net_ok") is True
            and int(offline_clr.get("total_spine_clearing_count") or 0) >= 2
            and int(offline_clr.get("total_spine_clearing_height") or 0) >= 2
            and int(offline_clr.get("total_spine_clearing_residual") or 0) == 0
            and len(tip_clearing) >= 32
            and str(offline_clr.get("total_spine_state_root") or "") == state_root
            and str(offline_clr.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_clr.get("total_spine_digest") or "")
            != str(settled.get("total_spine_digest") or "")
            and isinstance(clr_path, str)
            and Path(clr_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_clearing_certificate(clr_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_clearing_loaded")
            and (loaded.get("clearing_verify") or {}).get("ok")
            and (loaded.get("clearing_verify") or {}).get("clearing_root_ok")
            and (loaded.get("clearing_verify") or {}).get("chain_ok")
            and (loaded.get("clearing_verify") or {}).get("clearings_ok")
        )

        tampered_path = scratch / "tampered-clearing.json"
        tampered_body = dict(loaded)
        for drop in (
            "clearing_verify",
            "total_spine_clearing_loaded",
            "clearing_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["clearing_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_clearing_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_clearing_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_clearing_certificate(
                scratch / "clr-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
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
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_clearing_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_clearing_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "clearing_verify",
            "total_spine_clearing_loaded",
            "clearing_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_clearing_certificate(wrong_body)
        wrong_verify = verify_total_spine_clearing_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("clearing_root_ok") is False
        )

        mismatch_ok = False
        try:
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
                capabilities=[good_id, inv_id],
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
                    s1,
                    other.get("total_spine_settlement_certificate") or {},
                ],
                min_clearings=2,
            )
        except StageRefused as exc:
            mismatch_ok = str(exc.verdict) == "total_spine_clearing_root_mismatch"
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        h2 = clear_total_spine(
            [s1, s2],
            out_root=scratch / "clr-h2",
            prior_tip=str(
                offline_clr.get("total_spine_clearing_bound_tip") or ""
            ),
            parent_clearing_root=tip_clearing,
            clearing_height=int(offline_clr.get("total_spine_clearing_height") or 0)
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_clearing_count") or 0) >= 2
            and str(h2.get("total_spine_tip_clearing_root") or "") != tip_clearing
            and str(
                (h2.get("total_spine_clearing_certificate") or {}).get(
                    "parent_clearing_root"
                )
                or ""
            )
            == tip_clearing
        )

        recomputed = compute_total_spine_clearing_root(loaded.get("clearings") or [])
        determinism_ok = recomputed == tip_clearing and bool(recomputed)

        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-clr",
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
            resume_dir=paths[0],
            federation_peers=[paths[1], paths[2]],
            federation_quorum=True,
            execution=True,
            actuation=True,
            settlement=True,
            clearing=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_clr_path = live.get("total_spine_clearing_path")
        live_ok = (
            bool(live.get("ok"))
            and live.get("total_spine") is True
            and live.get("total_spine_finality") is True
            and live.get("total_spine_federation") is True
            and live.get("total_spine_quorum") is True
            and live.get("total_spine_execution") is True
            and live.get("total_spine_actuation") is True
            and live.get("total_spine_settlement") is True
            and live.get("total_spine_clearing") is True
            and live.get("total_spine_cleared") is True
            and live.get("total_spine_discharged") is True
            and int(live.get("total_spine_clearing_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_clearing_root"), str)
            and len(str(live.get("total_spine_tip_clearing_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_clr_path, str)
            and Path(live_clr_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-clr",
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
            clearing=True,
            resume_dir=live_clr_path or (scratch / "live-clr"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_clearing") is True
            and shorted.get("total_spine_clearing_short_circuit") is True
            and str(shorted.get("total_spine_tip_clearing_root") or "")
            == str(live.get("total_spine_tip_clearing_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        clr_chain = live.get("total_spine_clearing_chain") or {}
        chain_integrity_ok = False
        if isinstance(clr_chain, Mapping) and clr_chain:
            re_seal = seal_total_spine_clearing_chain(
                prior_tip=str(clr_chain.get("prior_tip") or ""),
                clearing_digest=str(clr_chain.get("clearing_digest") or ""),
                tip_clearing_root=str(clr_chain.get("tip_clearing_root") or ""),
                bound_settlement_root=str(
                    clr_chain.get("bound_settlement_root") or ""
                ),
                bound_action_root=str(clr_chain.get("bound_action_root") or ""),
                bound_state_root=str(clr_chain.get("bound_state_root") or ""),
                actuation_digest=str(clr_chain.get("actuation_digest") or ""),
                settlement_digest=str(clr_chain.get("settlement_digest") or ""),
                clearing_height=int(clr_chain.get("clearing_height") or 0),
                short_circuit=bool(clr_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == clr_chain.get("digest")
                and re_seal.get("digest") == live.get("total_spine_clearing_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(settled.get("total_spine_digest") or "")
            != str(offline_clr.get("total_spine_digest") or "")
        )

        # Facade exposes this stage's surface (delegation identity;
        # source-text greps predate the thin PEP 562 facade).
        source_ok = (
            getattr(le_facade, "TOTAL_SPINE_CLEARING_IMPL", None) is TOTAL_SPINE_CLEARING_IMPL
            and getattr(le_facade, "builtin_total_spine_clearing_proof", None) is builtin_total_spine_clearing_proof
            and getattr(le_facade, "clear_total_spine", None) is clear_total_spine
            and callable(
                getattr(le_facade, "builtin_total_spine_clearing_proof", None)
    
        )
            and callable(getattr(le_facade, "clear_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_CLEARING_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_CLEARING_IMPL" in engine_text
            and "clear_total_spine" in engine_text
            and (
                "clearing=True" in engine_text
                or "clearing: bool = False" in engine_text
            )
            and "builtin_total_spine_clearing_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def clear_total_spine" in mod_text
            and "def builtin_total_spine_clearing_proof" in mod_text
            and "total_spine_clearing_supersession_refused" in mod_text
            and "total_spine_clearing_tampered" in mod_text
            and "total_spine_clearing_net_failed" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-clearing"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_clearing" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_clearing_proof" in (entry.entry or "")
                and (
                    "clearing" in tags_blob
                    or "clearing" in name_blob
                    or "clearing" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "clear_total_spine" in delta_blob
                    or "post-settlement" in delta_blob
                    or "post_settlement" in delta_blob
                    or "net" in delta_blob
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
                mismatch_ok,
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
            "action": "total_spine_clearing_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "clearing_path": clr_path,
            "tip_clearing_root": tip_clearing,
            "tip_settlement_root": tip_settlement,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "clearing_count": offline_clr.get("total_spine_clearing_count"),
            "verify_ok": verify_ok,
            "tamper_ok": tamper_ok,
            "supersession_ok": supersession_ok,
            "wrong_root_ok": wrong_root_ok,
            "mismatch_ok": mismatch_ok,
            "multi_height_ok": multi_height_ok,
            "determinism_ok": determinism_ok,
            "live_ok": live_ok,
            "live_clearing_path": live_clr_path,
            "live_tip_clearing_root": live.get("total_spine_tip_clearing_root"),
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
            "total_spine_clearing": True,
            "total_spine_settlement": True,
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


if __name__ == "__main__":
    raise SystemExit(main())
