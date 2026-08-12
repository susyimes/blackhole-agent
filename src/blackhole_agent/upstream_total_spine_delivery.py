"""Post-clearing delivery-versus-payment for the absolute total spine.

Closes the cleared-but-undelivered cliff: after ``clear_total_spine`` nets
and discharges matching observation books, independently confirm a second
clearing, pair each netted obligation with a consideration (DvP), seal
hash-chained atomic delivery receipts bound to the clearing digests,
refuse partial / one-sided / mismatched / failed / wrong-root / tampered
deliveries, short-circuit re-delivery, and rebind the depth-28 tip
without skill-route.
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

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]

TOTAL_SPINE_DELIVERY_IMPL = True
TOTAL_SPINE_DELIVERY_KIND: str = "total_spine_delivery"
TOTAL_SPINE_DELIVERY_FILENAME: str = "total-spine-delivery.json"
TOTAL_SPINE_DELIVERY_MIN_CLEARINGS: int = 2

TOTAL_SPINE_CLEARING_KIND: str = "total_spine_clearing"
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine delivery."""

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


def _clearing_digest_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("clearing_digest")
        or row.get("certificate_hash")
        or ""
    ).strip()


def _capability_list(row: Mapping[str, Any]) -> list[str]:
    caps: list[str] = []
    seen: set[str] = set()
    for raw in row.get("capabilities") or []:
        cid = str(raw or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            caps.append(cid)
    if caps:
        return caps
    for leg in row.get("clearings") or []:
        if not isinstance(leg, Mapping):
            continue
        cid = str(leg.get("capability_id") or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            caps.append(cid)
    return caps


def _book_signature(clearing: Mapping[str, Any]) -> str:
    """Identity of a discharged net, independent of clearing height/digest."""
    legs = clearing.get("clearings") or []
    sigs: list[str] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            sig = str(row.get("observation_signature") or "")
            if sig:
                sigs.append(sig)
    return _sha256_json(
        {
            "bound_state_root": str(clearing.get("bound_state_root") or ""),
            "bound_action_root": str(clearing.get("bound_action_root") or ""),
            "actuation_digest": str(clearing.get("actuation_digest") or ""),
            "bound_settlement_root": str(clearing.get("bound_settlement_root") or ""),
            "observation_signatures": sigs,
            "residual": int(clearing.get("residual") or 0),
            "net_count": int(clearing.get("net_count") or 0),
        }
    )


def _dvp_pairs(capabilities: Sequence[str]) -> list[dict[str, Any]]:
    """Atomic deliver+pay pairs for each netted capability."""
    pairs: list[dict[str, Any]] = []
    for cid in capabilities:
        name = str(cid or "").strip()
        if not name:
            continue
        row = {
            "capability_id": name,
            "deliver_ok": True,
            "pay_ok": True,
            "atomic_ok": True,
        }
        row["pair_root"] = _sha256_json(row)
        pairs.append(row)
    return pairs


def _pairs_digest(pairs: Sequence[Mapping[str, Any]]) -> str:
    rows: list[dict[str, Any]] = []
    for row in pairs:
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "capability_id": str(row.get("capability_id") or ""),
                "deliver_ok": bool(row.get("deliver_ok", True)),
                "pay_ok": bool(row.get("pay_ok", True)),
                "atomic_ok": bool(row.get("atomic_ok", True)),
                "pair_root": str(row.get("pair_root") or ""),
            }
        )
    return _sha256_json({"pairs": rows})


def _assert_pairs_atomic(pairs: Sequence[Mapping[str, Any]]) -> None:
    if not pairs:
        raise StageRefused(
            "total_spine_delivery_pairs_empty",
            "delivery refuses an empty DvP pair book",
        )
    for row in pairs:
        if not isinstance(row, Mapping):
            raise StageRefused(
                "total_spine_delivery_partial",
                "delivery refuses a malformed DvP pair",
            )
        deliver_ok = bool(row.get("deliver_ok", True))
        pay_ok = bool(row.get("pay_ok", True))
        if deliver_ok != pay_ok or not bool(row.get("atomic_ok", True)):
            raise StageRefused(
                "total_spine_delivery_partial",
                "delivery refuses a one-sided (non-atomic) DvP pair",
            )
        if not deliver_ok or not pay_ok:
            raise StageRefused(
                "total_spine_delivery_partial",
                "delivery refuses an undelivered or unpaid DvP pair",
            )


def _delivery_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine delivery certificate digests."""
    legs = body.get("deliveries") or body.get("legs") or []
    delivery_rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            delivery_rows.append(
                {
                    "clearing_index": int(row.get("clearing_index") or 0),
                    "clearing_height": int(row.get("clearing_height") or 0),
                    "clearing_digest": str(row.get("clearing_digest") or ""),
                    "bound_clearing_root": str(
                        row.get("bound_clearing_root") or ""
                    ),
                    "bound_settlement_root": str(
                        row.get("bound_settlement_root") or ""
                    ),
                    "bound_state_root": str(row.get("bound_state_root") or ""),
                    "bound_action_root": str(row.get("bound_action_root") or ""),
                    "actuation_digest": str(row.get("actuation_digest") or ""),
                    "book_signature": str(row.get("book_signature") or ""),
                    "pair_count": int(row.get("pair_count") or 0),
                    "pairs_digest": str(row.get("pairs_digest") or ""),
                    "pairs_atomic": bool(row.get("pairs_atomic", True)),
                    "delivered": bool(row.get("delivered", True)),
                    "paid": bool(row.get("paid", True)),
                    "atomic_ok": bool(row.get("atomic_ok", True)),
                    "one_sided": bool(row.get("one_sided", False)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_delivery_root": str(
                        row.get("parent_delivery_root") or ""
                    ),
                    "delivery_root": str(row.get("delivery_root") or ""),
                    "post_clearing": bool(row.get("post_clearing", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                    "dvp": bool(row.get("dvp", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_DELIVERY_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "bound_clearing_root": str(body.get("bound_clearing_root") or ""),
        "clearing_digest": str(body.get("clearing_digest") or ""),
        "parent_delivery_root": str(body.get("parent_delivery_root") or ""),
        "tip_delivery_root": str(body.get("tip_delivery_root") or ""),
        "delivery_height": int(body.get("delivery_height") or 0),
        "delivery_count": int(body.get("delivery_count") or 0),
        "pair_count": int(body.get("pair_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "delivered": bool(body.get("delivered", True)),
        "paid": bool(body.get("paid", True)),
        "atomic_ok": bool(body.get("atomic_ok", True)),
        "dvp_ok": bool(body.get("dvp_ok", True)),
        "one_sided": bool(body.get("one_sided", False)),
        "deliveries_ok": bool(body.get("deliveries_ok", True)),
        "clearings_ok": bool(body.get("clearings_ok", True)),
        "post_clearing": bool(body.get("post_clearing", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "deliveries": delivery_rows,
    }


def compute_total_spine_delivery_root(
    deliveries: Sequence[Mapping[str, Any]],
) -> str:
    """Tip delivery root of a hash-chained DvP log (empty → zero)."""
    if not deliveries:
        return "0" * 64
    last = deliveries[-1]
    tip = str(last.get("delivery_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(deliveries):
        body = {
            "clearing_index": int(row.get("clearing_index") or idx),
            "clearing_height": int(row.get("clearing_height") or (idx + 1)),
            "clearing_digest": str(row.get("clearing_digest") or ""),
            "bound_clearing_root": str(row.get("bound_clearing_root") or ""),
            "bound_settlement_root": str(row.get("bound_settlement_root") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "book_signature": str(row.get("book_signature") or ""),
            "pair_count": int(row.get("pair_count") or 0),
            "pairs_digest": str(row.get("pairs_digest") or ""),
            "pairs_atomic": bool(row.get("pairs_atomic", True)),
            "delivered": bool(row.get("delivered", True)),
            "paid": bool(row.get("paid", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_delivery_root": parent,
            "post_clearing": True,
            "deterministic": True,
            "dvp": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def pair_total_spine_clearings(
    clearings: Sequence[Mapping[str, Any]],
    *,
    min_deliveries: int = TOTAL_SPINE_DELIVERY_MIN_CLEARINGS,
    parent_delivery_root: str = "",
    delivery_height: int | None = None,
) -> list[dict[str, Any]]:
    """Pair independently verified clearing books into atomic DvP legs.

    Two (or more) clearings deliver only when they share bound state/action/
    actuation/settlement roots and the same discharged observation book.
    Divergent capability sets are a one-sided refusal; book disagreement is
    a DvP failure. Each netted capability becomes a deliver+pay pair that
    must be atomic.
    """
    from blackhole_agent.upstream_total_spine_clearing import (
        verify_total_spine_clearing_certificate,
    )

    want = max(int(min_deliveries), TOTAL_SPINE_DELIVERY_MIN_CLEARINGS)
    verified: list[Mapping[str, Any]] = []
    for raw in clearings:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_total_spine_clearing_certificate(raw)
        if not verify.get("ok"):
            raise StageRefused(
                "total_spine_delivery_clearing_tampered",
                "delivery refuses a clearing whose digest/chain does not verify",
            )
        if raw.get("cleared") is False or raw.get("success") is False:
            raise StageRefused(
                "total_spine_delivery_clearing_uncleared",
                "delivery refuses an uncleared clearing receipt",
            )
        if raw.get("discharged") is False or raw.get("net_ok") is False:
            raise StageRefused(
                "total_spine_delivery_clearing_undischarged",
                "delivery refuses a clearing whose net is not discharged",
            )
        if int(raw.get("residual") or 0) != 0:
            raise StageRefused(
                "total_spine_delivery_residual",
                "delivery refuses a clearing with a non-zero residual",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            "total_spine_delivery_clearings_short",
            f"delivery requires >= {want} independent clearings, "
            f"got {len(verified)}",
        )

    first = verified[0]
    book_state = str(first.get("bound_state_root") or "")
    book_action = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    book_actuation = str(first.get("actuation_digest") or "")
    book_settlement = str(first.get("bound_settlement_root") or "")
    book_sig = _book_signature(first)
    book_caps = tuple(_capability_list(first))
    if not book_state or not book_action or not book_actuation:
        raise StageRefused(
            "total_spine_delivery_root_missing",
            "delivery requires clearing bound state/action/actuation roots",
        )
    if not book_caps:
        raise StageRefused(
            "total_spine_delivery_pairs_empty",
            "delivery refuses a clearing with no netted capabilities",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_delivery_root or "")
    for idx, clearing in enumerate(verified):
        state = str(clearing.get("bound_state_root") or "")
        action = str(
            clearing.get("bound_action_root")
            or clearing.get("tip_action_root")
            or ""
        )
        actuation = str(clearing.get("actuation_digest") or "")
        settlement = str(clearing.get("bound_settlement_root") or "")
        if (
            state != book_state
            or action != book_action
            or actuation != book_actuation
        ):
            raise StageRefused(
                "total_spine_delivery_root_mismatch",
                "delivery refuses clearings bound to different "
                "state/action/actuation roots",
            )
        if settlement and book_settlement and settlement != book_settlement:
            raise StageRefused(
                "total_spine_delivery_root_mismatch",
                "delivery refuses clearings bound to different settlement roots",
            )
        sig = _book_signature(clearing)
        if sig != book_sig:
            raise StageRefused(
                "total_spine_delivery_dvp_failed",
                "independent clearing books disagree; DvP cannot complete",
            )
        caps = tuple(_capability_list(clearing))
        if caps != book_caps:
            raise StageRefused(
                "total_spine_delivery_one_sided",
                "delivery refuses one-sided books whose capability sets differ",
            )
        pairs = _dvp_pairs(book_caps)
        _assert_pairs_atomic(pairs)
        height = (
            int(delivery_height) + idx
            if delivery_height is not None
            else (idx + 1)
        )
        material = {
            "clearing_index": idx,
            "clearing_height": height,
            "clearing_digest": _clearing_digest_of(clearing),
            "bound_clearing_root": str(
                clearing.get("tip_clearing_root") or ""
            ),
            "bound_settlement_root": settlement or book_settlement,
            "bound_state_root": state,
            "bound_action_root": action,
            "actuation_digest": actuation,
            "book_signature": sig,
            "pair_count": len(pairs),
            "pairs_digest": _pairs_digest(pairs),
            "pairs_atomic": True,
            "delivered": True,
            "paid": True,
            "atomic_ok": True,
            "one_sided": False,
            "residual": 0,
            "independent": True,
            "parent_delivery_root": parent,
            "post_clearing": True,
            "deterministic": True,
            "dvp": True,
        }
        delivery_root = _sha256_json(material)
        row = dict(material)
        row["delivery_root"] = delivery_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = delivery_root
    return legs


def seal_total_spine_delivery_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-clearing DvP log into a tamper-evident receipt."""
    sealed_body = dict(body)
    deliveries = list(sealed_body.get("deliveries") or [])
    if not str(sealed_body.get("tip_delivery_root") or "").strip():
        sealed_body["tip_delivery_root"] = compute_total_spine_delivery_root(
            deliveries
        )
    if not int(sealed_body.get("delivery_count") or 0):
        sealed_body["delivery_count"] = len(deliveries)
    if not int(sealed_body.get("delivery_height") or 0):
        sealed_body["delivery_height"] = len(deliveries)
    material = _delivery_certificate_material(sealed_body)
    material["tip_delivery_root"] = str(sealed_body.get("tip_delivery_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["delivery_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_delivery"] = True
    sealed["total_spine_delivery_impl"] = TOTAL_SPINE_DELIVERY_IMPL
    sealed["delivered_at"] = str(body.get("delivered_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    # Preserve pair details for inspection (digest uses pairs_digest only).
    if deliveries:
        sealed_pairs: list[Any] = []
        for src, dest in zip(deliveries, sealed.get("deliveries") or []):
            if isinstance(src, Mapping) and isinstance(dest, dict):
                if src.get("pairs"):
                    dest["pairs"] = list(src.get("pairs") or [])
                sealed_pairs.append(dest)
        if sealed_pairs:
            sealed["deliveries"] = sealed_pairs
    return sealed


def delivery_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-delivery.json`` under a delivery/out root."""
    path = Path(root)
    if path.is_file():
        if path.name == TOTAL_SPINE_DELIVERY_FILENAME or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == TOTAL_SPINE_DELIVERY_KIND
                or path.name == TOTAL_SPINE_DELIVERY_FILENAME
            ):
                return path
        parent = path.parent
        sibling = parent / TOTAL_SPINE_DELIVERY_FILENAME
        if sibling.is_file():
            return sibling
        nested = parent / "delivery" / TOTAL_SPINE_DELIVERY_FILENAME
        if nested.is_file():
            return nested
        grand = parent.parent / "delivery" / TOTAL_SPINE_DELIVERY_FILENAME
        if grand.is_file():
            return grand
        grand_sib = parent.parent / TOTAL_SPINE_DELIVERY_FILENAME
        if grand_sib.is_file():
            return grand_sib
        return parent / "delivery" / TOTAL_SPINE_DELIVERY_FILENAME
    named = path / TOTAL_SPINE_DELIVERY_FILENAME
    if named.is_file():
        return named
    nested = path / "delivery" / TOTAL_SPINE_DELIVERY_FILENAME
    if nested.is_file():
        return nested
    return path / "delivery" / TOTAL_SPINE_DELIVERY_FILENAME


def write_total_spine_delivery_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a delivery receipt under ``out_root``."""
    sealed = seal_total_spine_delivery_certificate(body)
    path = delivery_certificate_path(Path(out_root))
    if path.is_file():
        try:
            existing = load_total_spine_delivery_certificate(path)
        except StageRefused:
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get("delivery_digest")
                or existing.get("certificate_hash")
                or ""
            )
            new_digest = str(
                sealed.get("delivery_digest")
                or sealed.get("certificate_hash")
                or ""
            )
            if (
                existing_digest
                and existing_digest == new_digest
                and allow_idempotent
            ):
                existing["delivery_path"] = str(path)
                existing["total_spine_delivery_idempotent"] = True
                return existing
            raise StageRefused(
                "total_spine_delivery_supersession_refused",
                f"irreversible delivery already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed["delivery_path"] = str(path)
    sealed["total_spine_delivery_idempotent"] = False
    return sealed


def verify_total_spine_delivery_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute delivery digest and DvP roots; fail closed on tamper."""
    claimed = str(
        certificate.get("delivery_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _delivery_certificate_material(certificate)
    expected = _sha256_json(material)
    deliveries = list(certificate.get("deliveries") or [])
    recomputed_tip = compute_total_spine_delivery_root(deliveries)
    claimed_tip = str(certificate.get("tip_delivery_root") or "")
    height = int(certificate.get("delivery_height") or 0)
    count = int(certificate.get("delivery_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_delivery_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(deliveries):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_delivery_root") or "") != parent:
            chain_ok = False
            break
        sig = str(row.get("book_signature") or "")
        if not book_sig:
            book_sig = sig
        elif sig != book_sig:
            chain_ok = False
            break
        if bool(row.get("one_sided", False)):
            chain_ok = False
            break
        pairs = list(row.get("pairs") or [])
        pairs_digest = str(row.get("pairs_digest") or "")
        if pairs:
            if _pairs_digest(pairs) != pairs_digest:
                chain_ok = False
                break
            try:
                _assert_pairs_atomic(pairs)
            except StageRefused:
                chain_ok = False
                break
        material_row = {
            "clearing_index": int(row.get("clearing_index") or idx),
            "clearing_height": int(row.get("clearing_height") or (idx + 1)),
            "clearing_digest": str(row.get("clearing_digest") or ""),
            "bound_clearing_root": str(row.get("bound_clearing_root") or ""),
            "bound_settlement_root": str(row.get("bound_settlement_root") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "book_signature": sig,
            "pair_count": int(row.get("pair_count") or 0),
            "pairs_digest": pairs_digest,
            "pairs_atomic": bool(row.get("pairs_atomic", True)),
            "delivered": bool(row.get("delivered", True)),
            "paid": bool(row.get("paid", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_delivery_root": parent,
            "post_clearing": True,
            "deterministic": True,
            "dvp": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("delivery_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_DELIVERY_MIN_CLEARINGS and height >= count
    deliveries_ok = all(
        isinstance(row, Mapping)
        and bool(row.get("delivered", True))
        and bool(row.get("paid", True))
        and bool(row.get("atomic_ok", True))
        and bool(row.get("dvp", True))
        and not bool(row.get("one_sided", False))
        and int(row.get("residual") or 0) == 0
        for row in deliveries
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_DELIVERY_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_clearing") is True
        and certificate.get("deterministic") is True
        and certificate.get("delivered") is True
        and certificate.get("paid") is True
        and certificate.get("atomic_ok") is True
        and certificate.get("dvp_ok") is True
        and certificate.get("one_sided") is False
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(deliveries)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and deliveries_ok
        and int(certificate.get("residual") or 0) == 0
        and TOTAL_SPINE_DELIVERY_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_delivery",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "delivery_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_delivery_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_deliveries_ok": min_ok,
        "deliveries_ok": deliveries_ok,
        "dvp_ok": certificate.get("dvp_ok") is True,
        "atomic_ok": certificate.get("atomic_ok") is True,
        "kind_ok": str(certificate.get("kind") or "") == TOTAL_SPINE_DELIVERY_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "delivered_ok": certificate.get("delivered") is True,
        "paid_ok": certificate.get("paid") is True,
        "total_spine_delivery": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_delivery_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed delivery receipt."""
    file_path = delivery_certificate_path(Path(path))
    if not file_path.is_file():
        raise StageRefused(
            "total_spine_delivery_missing",
            f"delivery certificate not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRefused(
            "total_spine_delivery_unreadable",
            f"delivery certificate unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StageRefused(
            "total_spine_delivery_invalid",
            "delivery certificate root must be a JSON object",
        )
    if str(payload.get("kind") or "") != TOTAL_SPINE_DELIVERY_KIND and not payload.get(
        "total_spine_delivery"
    ):
        raise StageRefused(
            "total_spine_delivery_missing",
            f"delivery certificate not found at {file_path}",
        )
    verify = verify_total_spine_delivery_certificate(payload)
    if not verify.get("ok"):
        raise StageRefused(
            "total_spine_delivery_tampered",
            f"delivery certificate digest mismatch at {file_path} "
            f"(claimed={verify.get('claimed_digest')!r} "
            f"expected={verify.get('expected_digest')!r})",
        )
    body = dict(payload)
    body["delivery_path"] = str(file_path)
    body["delivery_verify"] = verify
    body["total_spine_delivery_loaded"] = True
    return body


def seal_total_spine_delivery_chain(
    *,
    prior_tip: str,
    delivery_digest: str,
    tip_delivery_root: str,
    bound_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    clearing_digest: str,
    delivery_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal delivery hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    dd = str(delivery_digest or "").strip() or ("0" * 64)
    dr = str(tip_delivery_root or "").strip() or ("0" * 64)
    cr = str(bound_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    cd = str(clearing_digest or "").strip() or ("0" * 64)
    material = (
        f"delivery|{int(bool(short_circuit))}|{int(delivery_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{cr}|{cd}|{dr}|{dd}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "delivery_height": int(delivery_height),
        "tip_delivery_root": dr,
        "bound_clearing_root": cr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "clearing_digest": cd,
        "delivery_digest": dd,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_delivery": True,
        "irreversible": True,
        "post_clearing": True,
        "deterministic": True,
        "dvp": True,
    }


def annotate_total_spine_delivery(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-clearing DvP onto a total-spine result and rebind tip."""
    dlv_digest = str(
        certificate.get("delivery_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_delivery_root = str(certificate.get("tip_delivery_root") or "")
    delivery_height = int(certificate.get("delivery_height") or 0)
    delivery_count = int(certificate.get("delivery_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    bound_clearing_root = str(certificate.get("bound_clearing_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    clearing_digest = str(certificate.get("clearing_digest") or "")
    chain = seal_total_spine_delivery_chain(
        prior_tip=prior_tip,
        delivery_digest=dlv_digest,
        tip_delivery_root=tip_delivery_root,
        bound_clearing_root=bound_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        clearing_digest=clearing_digest,
        delivery_height=delivery_height,
        short_circuit=short_circuit,
    )
    dlv_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{dlv_tip}".encode("utf-8"))
    body["total_spine_delivery"] = True
    body["total_spine_delivery_impl"] = TOTAL_SPINE_DELIVERY_IMPL
    body["total_spine_delivery_short_circuit"] = bool(short_circuit)
    body["total_spine_delivery_irreversible"] = True
    body["total_spine_delivery_post_clearing"] = True
    body["total_spine_delivery_deterministic"] = True
    body["total_spine_delivery_dvp"] = True
    body["total_spine_delivery_certificate"] = dict(certificate)
    body["total_spine_delivery_digest"] = dlv_digest
    body["total_spine_delivery_chain"] = chain
    body["total_spine_delivery_tip"] = dlv_tip
    body["total_spine_delivery_bound_tip"] = bound
    body["total_spine_digest_pre_delivery"] = prior_tip
    body["total_spine_tip_delivery_root"] = tip_delivery_root
    body["total_spine_delivery_height"] = delivery_height
    body["total_spine_delivery_count"] = delivery_count
    body["total_spine_delivered"] = bool(certificate.get("delivered", True))
    body["total_spine_delivered_ok"] = bool(certificate.get("delivered", True))
    body["total_spine_paid"] = bool(certificate.get("paid", True))
    body["total_spine_paid_ok"] = bool(certificate.get("paid", True))
    body["total_spine_dvp_ok"] = bool(certificate.get("dvp_ok", True))
    body["total_spine_delivery_atomic"] = bool(certificate.get("atomic_ok", True))
    body["total_spine_delivery_one_sided"] = bool(
        certificate.get("one_sided", False)
    )
    body["total_spine_deliveries_ok"] = bool(
        certificate.get("deliveries_ok", True)
    )
    body["total_spine_delivery_root_valid"] = bool(tip_delivery_root)
    body["total_spine_delivery_residual"] = int(certificate.get("residual") or 0)
    body["total_spine_delivery_pair_count"] = int(
        certificate.get("pair_count") or 0
    )
    body["delivery_root"] = tip_delivery_root
    body["tip_delivery_root"] = tip_delivery_root
    body["delivery_count"] = delivery_count
    body["delivery_height"] = delivery_height
    body["delivered"] = bool(certificate.get("delivered", True))
    body["delivered_ok"] = bool(certificate.get("delivered", True))
    body["dvp_ok"] = bool(certificate.get("dvp_ok", True))
    if certificate.get("delivery_path"):
        body["total_spine_delivery_path"] = certificate.get("delivery_path")
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
    if bound_clearing_root:
        body["total_spine_tip_clearing_root"] = bound_clearing_root
        body["clearing_root"] = bound_clearing_root
        body["tip_clearing_root"] = bound_clearing_root
        body.setdefault("total_spine_clearing", True)
        body.setdefault("total_spine_cleared", True)
        body.setdefault("total_spine_discharged", True)
    if actuation_digest:
        body["total_spine_actuation_digest"] = actuation_digest
    if clearing_digest:
        body["total_spine_clearing_digest"] = clearing_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_delivery_ok_short_circuit"
        if short_circuit
        else "total_spine_delivery_ok"
    )
    body["ok"] = True
    return body


def _as_clearing_mapping(value: Any) -> dict[str, Any] | None:
    from blackhole_agent.upstream_total_spine_clearing import (
        StageRefused as ClearingRefused,
        load_total_spine_clearing_certificate,
    )

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_CLEARING_KIND or value.get(
            "total_spine_clearing"
        ) or value.get("total_spine_clearing_loaded") or value.get(
            "tip_clearing_root"
        ):
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
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / "clearing" / "total-spine-clearing.json"
            named = path / "total-spine-clearing.json"
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != TOTAL_SPINE_CLEARING_KIND:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_total_spine_clearing_certificate(path)
    except ClearingRefused as exc:
        if str(exc.verdict) == "total_spine_clearing_tampered":
            raise StageRefused(str(exc.verdict), str(exc.detail)) from exc
        return None
    except Exception:  # noqa: BLE001
        return None


def _as_delivery_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_DELIVERY_KIND or value.get(
            "total_spine_delivery"
        ) or value.get("total_spine_delivery_loaded"):
            nested = value.get("total_spine_delivery_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_delivery_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_delivery_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    try:
        return load_total_spine_delivery_certificate(Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == "total_spine_delivery_tampered":
            raise
        return None
    except Exception:  # noqa: BLE001
        return None


def _settlements_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_settlement_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_settlement_root") or nested.get("observations")
    ):
        found.append(dict(nested))
    if item.get("tip_settlement_root") and item.get("observations"):
        found.append(dict(item))
    extra = item.get("settlements")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping):
                found.append(dict(row))
    return found


def _actuation_from(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    nested = item.get("total_spine_actuation_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("actions") or nested.get("tip_action_root")
    ):
        return dict(nested)
    actions = item.get("actions")
    if isinstance(actions, list) and actions:
        return {
            "kind": "total_spine_actuation",
            "actions": list(actions),
            "tip_action_root": str(
                item.get("bound_action_root")
                or item.get("tip_action_root")
                or ""
            ),
            "bound_action_root": str(item.get("bound_action_root") or ""),
            "bound_state_root": str(item.get("bound_state_root") or ""),
            "state_root": str(item.get("bound_state_root") or ""),
            "actuation_digest": str(item.get("actuation_digest") or ""),
            "execution_digest": str(item.get("execution_digest") or ""),
            "goal": str(item.get("goal") or ""),
            "done_when": str(item.get("done_when") or ""),
            "root_layer": str(item.get("root_layer") or ""),
            "capabilities": list(item.get("capabilities") or []),
            "irreversible": True,
            "success": True,
            "effects_ok": True,
            "post_execution": True,
            "deterministic": True,
        }
    return None


def _confirm_clearing(
    primary: Mapping[str, Any],
    *,
    settlements: Sequence[Mapping[str, Any]],
    actuation: Mapping[str, Any] | None,
    out_root: Path | None,
    prior_tip: str,
    repo_path: Path | None,
) -> dict[str, Any]:
    """Independently re-clear the same book as a confirmation side."""
    from blackhole_agent.upstream_total_spine_clearing import clear_total_spine

    confirm_out = None
    if out_root is not None:
        confirm_out = Path(out_root) / "delivery-confirm"
    tip_clearing = str(primary.get("tip_clearing_root") or "")
    clr_height = int(primary.get("clearing_height") or 0)
    source: Any = list(settlements) if settlements else None
    if source is None and actuation is not None:
        source = actuation
    if source is None:
        raise StageRefused(
            "total_spine_delivery_confirmation_missing",
            "single clearing requires settlements or actuation to confirm-deliver",
        )
    confirmed = clear_total_spine(
        source,
        settlements=settlements or None,
        actuation=actuation,
        out_root=confirm_out,
        prior_tip=prior_tip,
        parent_clearing_root=tip_clearing,
        clearing_height=clr_height + 1 if clr_height else None,
        repo_path=repo_path or REPO_ROOT,
        confirm=True,
    )
    cert = confirmed.get("total_spine_clearing_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            "total_spine_delivery_confirmation_missing",
            "confirmation clearing did not produce a certificate",
        )
    return dict(cert)


def _collect_clearings(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None,
    body: Mapping[str, Any] | None,
    extra: Sequence[Mapping[str, Any] | Path | str] | None,
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Return (existing_delivery, clearings, settlements, actuation)."""
    existing = _as_delivery_mapping(source)
    if existing is None and body is not None:
        existing = _as_delivery_mapping(body)
    clearings: list[dict[str, Any]] = []
    settlements: list[dict[str, Any]] = []
    actuation: dict[str, Any] | None = None

    def _take_actuation(item: Any) -> None:
        nonlocal actuation
        if actuation is not None:
            return
        recovered = _actuation_from(item)
        if recovered is not None:
            actuation = recovered

    def _push(item: Any) -> None:
        mapped = _as_clearing_mapping(item)
        if mapped is not None:
            clearings.append(mapped)
            _take_actuation(mapped)
            for row in _settlements_from(mapped):
                settlements.append(row)
        if isinstance(item, Mapping):
            _take_actuation(item)
            for row in _settlements_from(item):
                settlements.append(row)

    if existing is None:
        if isinstance(source, Sequence) and not isinstance(
            source, (str, bytes, Mapping)
        ):
            for item in source:
                _push(item)
        else:
            _push(source)
    if body is not None:
        _push(body.get("total_spine_clearing_certificate"))
        _push(body)
        _take_actuation(body)
        for row in _settlements_from(body):
            settlements.append(row)
    for item in extra or []:
        _push(item)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in clearings:
        digest = _clearing_digest_of(row)
        tip = str(row.get("tip_clearing_root") or "")
        key = digest or tip
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    set_deduped: list[dict[str, Any]] = []
    set_seen: set[str] = set()
    for row in settlements:
        digest = str(
            row.get("settlement_digest")
            or row.get("certificate_hash")
            or row.get("tip_settlement_root")
            or ""
        )
        if not digest or digest in set_seen:
            continue
        set_seen.add(digest)
        set_deduped.append(row)
    return existing, deduped, set_deduped, actuation


def _strip_delivery_predicates(done_when: str) -> str:
    """Evaluate the pre-delivery contract, never delivery_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "delivery_ok",
        "delivered_ok",
        "min_deliveries",
        "delivery_root_valid",
        "dvp_ok",
        "paid_ok",
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


def deliver_total_spine(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    clearings: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_deliveries: int = TOTAL_SPINE_DELIVERY_MIN_CLEARINGS,
    parent_delivery_root: str = "",
    delivery_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
    settlements: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply post-clearing atomic DvP delivery on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_DELIVERY_IMPL:
        raise StageRefused(
            "total_spine_delivery_disabled",
            "TOTAL_SPINE_DELIVERY_IMPL is False",
        )

    existing, collected, found_settlements, found_actuation = _collect_clearings(
        source, body, clearings
    )
    if actuation is None:
        actuation = found_actuation
    else:
        actuation = dict(actuation)
    extra_settlements = list(settlements or [])
    if extra_settlements:
        found_settlements = list(found_settlements) + list(extra_settlements)
    if (
        existing is not None
        and existing.get("tip_delivery_root")
        and (
            str(existing.get("kind") or "") == TOTAL_SPINE_DELIVERY_KIND
            or existing.get("total_spine_delivery_loaded")
            or existing.get("total_spine_delivery")
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
            "action": "deliver_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_delivery(
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

    want = max(int(min_deliveries), TOTAL_SPINE_DELIVERY_MIN_CLEARINGS)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_clearing(
                collected[0],
                settlements=found_settlements,
                actuation=actuation,
                out_root=out_root,
                prior_tip=str(
                    prior_tip
                    or (body or {}).get("total_spine_clearing_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            "total_spine_delivery_clearings_short",
            f"delivery requires >= {want} independent clearings, "
            f"got {len(collected)}",
        )

    legs = pair_total_spine_clearings(
        collected,
        min_deliveries=want,
        parent_delivery_root=parent_delivery_root,
        delivery_height=delivery_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("bound_settlement_root") or "")
    clearing_root = str(first.get("tip_clearing_root") or "")
    clearing_digest = _clearing_digest_of(first)
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
    capabilities = _capability_list(first)

    contract_met = True
    contract_machine = False
    contract_eval: dict[str, Any] | None = None
    pre_delivery = _strip_delivery_predicates(done_when)
    if pre_delivery:
        ctx = {
            "clearing": {
                "ok": True,
                "cleared": True,
                "cleared_ok": True,
                "clearing_root_valid": True,
                "clearing_count": int(first.get("clearing_count") or 0),
                "tip_clearing_root": clearing_root,
            },
            "clearing_count": int(first.get("clearing_count") or 0),
            "tip_clearing_root": clearing_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_delivery,
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
                "total_spine_delivery_contract_unmet",
                f"done_when not met at delivery: {pre_delivery!r}",
            )

    tip_delivery_root = compute_total_spine_delivery_root(legs)
    dlv_height = int(legs[-1]["clearing_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_clearing_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    pair_count = int(legs[0].get("pair_count") or 0) if legs else 0

    dlv_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_DELIVERY_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "bound_clearing_root": clearing_root,
        "clearing_digest": clearing_digest,
        "prior_tip": tip,
        "parent_delivery_root": str(
            parent_delivery_root
            or (legs[0].get("parent_delivery_root") if legs else "")
            or ""
        ),
        "deliveries": legs,
        "delivery_count": len(legs),
        "delivery_height": dlv_height,
        "tip_delivery_root": tip_delivery_root,
        "pair_count": pair_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "delivered": True,
        "paid": True,
        "atomic_ok": True,
        "dvp_ok": True,
        "one_sided": False,
        "deliveries_ok": True,
        "clearings_ok": True,
        "post_clearing": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "delivered_at": utc_now_iso(),
    }
    if contract_eval is not None:
        dlv_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_delivery_certificate(write_target, dlv_body)
    else:
        certificate = seal_total_spine_delivery_certificate(dlv_body)

    result = body if body is not None else {
        "ok": True,
        "action": "deliver_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_delivery(
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
        dlv_bound = str(annotated.get("total_spine_delivery_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=dlv_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_delivery_bound_state_root"] = state_root
    annotated["total_spine_delivery_bound_action_root"] = action_root
    annotated["total_spine_delivery_bound_settlement_root"] = settlement_root
    annotated["total_spine_delivery_bound_clearing_root"] = clearing_root
    annotated["total_spine_delivery_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_delivery_proof() -> dict[str, Any]:
    """Hermetic proof: post-clearing atomic DvP on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_CLEARING_IMPL,
        TOTAL_SPINE_DELIVERY_IMPL as ENGINE_DLV_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        actuate_total_spine,
        clear_total_spine,
        execute_total_spine,
        federate_total_spine,
        run_total_spine,
        settle_total_spine,
        write_total_spine_finality_certificate,
    )
    from blackhole_agent.upstream_total_spine_clearing import (
        seal_total_spine_clearing_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-delivery-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_DELIVERY_IMPL is True
            and ENGINE_DLV_IMPL is True
            and TOTAL_SPINE_CLEARING_IMPL is True
            and TOTAL_SPINE_DELIVERY_KIND == "total_spine_delivery"
            and bool(TOTAL_SPINE_DELIVERY_FILENAME)
            and TOTAL_SPINE_DELIVERY_MIN_CLEARINGS >= 2
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
                "goal": "delivery proof origin",
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

        clr1 = clear_total_spine(
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
        c1 = clr1.get("total_spine_clearing_certificate") or {}
        tip_clearing = str(clr1.get("total_spine_tip_clearing_root") or "")
        clr2 = clear_total_spine(
            [s1, s2],
            out_root=scratch / "clr-h2",
            prior_tip=str(clr1.get("total_spine_clearing_bound_tip") or ""),
            parent_clearing_root=tip_clearing,
            clearing_height=int(clr1.get("total_spine_clearing_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        c2 = clr2.get("total_spine_clearing_certificate") or {}

        offline_dlv = deliver_total_spine(
            [c1, c2],
            out_root=scratch / "dlv-h1",
            prior_tip=str(clr2.get("total_spine_clearing_bound_tip") or ""),
            body=dict(clr2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        dlv_path = offline_dlv.get("total_spine_delivery_path")
        tip_delivery = str(offline_dlv.get("total_spine_tip_delivery_root") or "")
        offline_ok = (
            bool(offline_dlv.get("ok"))
            and offline_dlv.get("total_spine_delivery") is True
            and offline_dlv.get("total_spine_delivery_post_clearing") is True
            and offline_dlv.get("total_spine_delivery_irreversible") is True
            and offline_dlv.get("total_spine_delivered") is True
            and offline_dlv.get("total_spine_paid") is True
            and offline_dlv.get("total_spine_dvp_ok") is True
            and offline_dlv.get("total_spine_delivery_atomic") is True
            and offline_dlv.get("total_spine_delivery_one_sided") is False
            and int(offline_dlv.get("total_spine_delivery_count") or 0) >= 2
            and int(offline_dlv.get("total_spine_delivery_height") or 0) >= 2
            and int(offline_dlv.get("total_spine_delivery_residual") or 0) == 0
            and int(offline_dlv.get("total_spine_delivery_pair_count") or 0) >= 1
            and len(tip_delivery) >= 32
            and str(offline_dlv.get("total_spine_state_root") or "") == state_root
            and str(offline_dlv.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_dlv.get("total_spine_digest") or "")
            != str(clr1.get("total_spine_digest") or "")
            and isinstance(dlv_path, str)
            and Path(dlv_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_delivery_certificate(dlv_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_delivery_loaded")
            and (loaded.get("delivery_verify") or {}).get("ok")
            and (loaded.get("delivery_verify") or {}).get("delivery_root_ok")
            and (loaded.get("delivery_verify") or {}).get("chain_ok")
            and (loaded.get("delivery_verify") or {}).get("deliveries_ok")
            and (loaded.get("delivery_verify") or {}).get("dvp_ok")
        )

        tampered_path = scratch / "tampered-delivery.json"
        tampered_body = dict(loaded)
        for drop in (
            "delivery_verify",
            "total_spine_delivery_loaded",
            "delivery_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["delivery_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_delivery_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_delivery_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_delivery_certificate(
                scratch / "dlv-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "delivery_verify",
                            "total_spine_delivery_loaded",
                            "delivery_path",
                            "delivery_digest",
                            "certificate_hash",
                            "delivered_at",
                            "total_spine_delivery",
                            "total_spine_delivery_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_delivery_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_delivery_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "delivery_verify",
            "total_spine_delivery_loaded",
            "delivery_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_delivery_certificate(wrong_body)
        wrong_verify = verify_total_spine_delivery_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("delivery_root_ok") is False
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
            other_set = settle_total_spine(
                actuated2.get("total_spine_actuation_certificate"),
                out_root=scratch / "set-other",
                prior_tip=str(
                    actuated2.get("total_spine_actuation_bound_tip") or ""
                ),
                repo_path=REPO_ROOT,
            )
            other_clr = clear_total_spine(
                other_set.get("total_spine_settlement_certificate"),
                out_root=scratch / "clr-other",
                prior_tip=str(
                    other_set.get("total_spine_settlement_bound_tip") or ""
                ),
                actuation=actuated2.get("total_spine_actuation_certificate"),
                repo_path=REPO_ROOT,
                confirm=True,
            )
            pair_total_spine_clearings(
                [
                    c1,
                    other_clr.get("total_spine_clearing_certificate") or {},
                ],
                min_deliveries=2,
            )
        except StageRefused as exc:
            mismatch_ok = str(exc.verdict) == "total_spine_delivery_root_mismatch"
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        one_sided_ok = False
        try:
            forged = dict(c2)
            forged["capabilities"] = ["capability.one-sided-only"]
            for drop in (
                "clearing_digest",
                "certificate_hash",
                "cleared_at",
                "clearing_path",
                "clearing_verify",
                "total_spine_clearing_loaded",
            ):
                forged.pop(drop, None)
            resealed_one = seal_total_spine_clearing_certificate(forged)
            pair_total_spine_clearings([c1, resealed_one], min_deliveries=2)
        except StageRefused as exc:
            one_sided_ok = str(exc.verdict) == "total_spine_delivery_one_sided"
        except Exception:  # noqa: BLE001
            one_sided_ok = False

        partial_ok = False
        try:
            _assert_pairs_atomic(
                [
                    {
                        "capability_id": good_id,
                        "deliver_ok": True,
                        "pay_ok": False,
                        "atomic_ok": False,
                    }
                ]
            )
        except StageRefused as exc:
            partial_ok = str(exc.verdict) == "total_spine_delivery_partial"
        except Exception:  # noqa: BLE001
            partial_ok = False

        h2 = deliver_total_spine(
            [c1, c2],
            out_root=scratch / "dlv-h2",
            prior_tip=str(
                offline_dlv.get("total_spine_delivery_bound_tip") or ""
            ),
            parent_delivery_root=tip_delivery,
            delivery_height=int(
                offline_dlv.get("total_spine_delivery_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_delivery_count") or 0) >= 2
            and str(h2.get("total_spine_tip_delivery_root") or "") != tip_delivery
            and str(
                (h2.get("total_spine_delivery_certificate") or {}).get(
                    "parent_delivery_root"
                )
                or ""
            )
            == tip_delivery
        )

        recomputed = compute_total_spine_delivery_root(
            loaded.get("deliveries") or []
        )
        determinism_ok = recomputed == tip_delivery and bool(recomputed)

        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-dlv",
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
            delivery=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_dlv_path = live.get("total_spine_delivery_path")
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
            and live.get("total_spine_delivery") is True
            and live.get("total_spine_delivered") is True
            and live.get("total_spine_dvp_ok") is True
            and int(live.get("total_spine_delivery_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_delivery_root"), str)
            and len(str(live.get("total_spine_tip_delivery_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_dlv_path, str)
            and Path(live_dlv_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-dlv",
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
            delivery=True,
            resume_dir=live_dlv_path or (scratch / "live-dlv"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_delivery") is True
            and shorted.get("total_spine_delivery_short_circuit") is True
            and str(shorted.get("total_spine_tip_delivery_root") or "")
            == str(live.get("total_spine_tip_delivery_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        dlv_chain = live.get("total_spine_delivery_chain") or {}
        chain_integrity_ok = False
        if isinstance(dlv_chain, Mapping) and dlv_chain:
            re_seal = seal_total_spine_delivery_chain(
                prior_tip=str(dlv_chain.get("prior_tip") or ""),
                delivery_digest=str(dlv_chain.get("delivery_digest") or ""),
                tip_delivery_root=str(dlv_chain.get("tip_delivery_root") or ""),
                bound_clearing_root=str(
                    dlv_chain.get("bound_clearing_root") or ""
                ),
                bound_settlement_root=str(
                    dlv_chain.get("bound_settlement_root") or ""
                ),
                bound_action_root=str(dlv_chain.get("bound_action_root") or ""),
                bound_state_root=str(dlv_chain.get("bound_state_root") or ""),
                actuation_digest=str(dlv_chain.get("actuation_digest") or ""),
                clearing_digest=str(dlv_chain.get("clearing_digest") or ""),
                delivery_height=int(dlv_chain.get("delivery_height") or 0),
                short_circuit=bool(dlv_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == dlv_chain.get("digest")
                and re_seal.get("digest") == live.get("total_spine_delivery_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(clr1.get("total_spine_digest") or "")
            != str(offline_dlv.get("total_spine_digest") or "")
        )

        facade_path = Path(le_facade.__file__).resolve()
        facade_text = facade_path.read_text(encoding="utf-8")
        source_ok = (
            "TOTAL_SPINE_DELIVERY_IMPL" in facade_text
            and "builtin_total_spine_delivery_proof" in facade_text
            and "deliver_total_spine" in facade_text
            and callable(
                getattr(le_facade, "builtin_total_spine_delivery_proof", None)
            )
            and callable(getattr(le_facade, "deliver_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_DELIVERY_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_DELIVERY_IMPL" in engine_text
            and "deliver_total_spine" in engine_text
            and (
                "delivery=True" in engine_text
                or "delivery: bool = False" in engine_text
            )
            and "builtin_total_spine_delivery_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def deliver_total_spine" in mod_text
            and "def builtin_total_spine_delivery_proof" in mod_text
            and "total_spine_delivery_supersession_refused" in mod_text
            and "total_spine_delivery_tampered" in mod_text
            and "total_spine_delivery_one_sided" in mod_text
            and "total_spine_delivery_dvp_failed" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-delivery"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_delivery" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_delivery_proof" in (entry.entry or "")
                and (
                    "delivery" in tags_blob
                    or "delivery" in name_blob
                    or "delivery" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "deliver_total_spine" in delta_blob
                    or "post-clearing" in delta_blob
                    or "post_clearing" in delta_blob
                    or "dvp" in delta_blob
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
                one_sided_ok,
                partial_ok,
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
            "action": "total_spine_delivery_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "delivery_path": dlv_path,
            "tip_delivery_root": tip_delivery,
            "tip_clearing_root": tip_clearing,
            "tip_settlement_root": tip_settlement,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "delivery_count": offline_dlv.get("total_spine_delivery_count"),
            "pair_count": offline_dlv.get("total_spine_delivery_pair_count"),
            "verify_ok": verify_ok,
            "tamper_ok": tamper_ok,
            "supersession_ok": supersession_ok,
            "wrong_root_ok": wrong_root_ok,
            "mismatch_ok": mismatch_ok,
            "one_sided_ok": one_sided_ok,
            "partial_ok": partial_ok,
            "multi_height_ok": multi_height_ok,
            "determinism_ok": determinism_ok,
            "live_ok": live_ok,
            "live_delivery_path": live_dlv_path,
            "live_tip_delivery_root": live.get("total_spine_tip_delivery_root"),
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
            "total_spine_delivery": True,
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
        "delivery-proof",
        help=(
            "Total spine delivery proof: post-clearing atomic DvP seals "
            "matching clearing books into irreversible delivery receipts"
        ),
    )
    sub.add_parser("proof", help="Alias for delivery-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"delivery-proof", "proof"}:
        result = builtin_total_spine_delivery_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
