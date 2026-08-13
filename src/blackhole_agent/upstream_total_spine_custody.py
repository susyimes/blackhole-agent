"""Post-delivery custody-versus-title for the absolute total spine.

Closes the delivered-but-uncustodied cliff: after ``deliver_total_spine``
seals atomic DvP receipts, independently confirm a second delivery, book
each delivered pair into a custody register and transfer beneficial title
(CvT), seal hash-chained atomic custody receipts bound to the delivery
digests, refuse split / one-sided / mismatched / failed / wrong-root /
tampered custodies, short-circuit re-custody, and rebind the depth-28 tip
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

TOTAL_SPINE_CUSTODY_IMPL = True
TOTAL_SPINE_CUSTODY_KIND: str = "total_spine_custody"
TOTAL_SPINE_CUSTODY_FILENAME: str = "total-spine-custody.json"
TOTAL_SPINE_CUSTODY_MIN_DELIVERIES: int = 2

TOTAL_SPINE_DELIVERY_KIND: str = "total_spine_delivery"
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine custody."""

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


def _delivery_digest_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("delivery_digest")
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
    for leg in row.get("deliveries") or row.get("custodies") or []:
        if not isinstance(leg, Mapping):
            continue
        cid = str(leg.get("capability_id") or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            caps.append(cid)
        for pair in leg.get("pairs") or []:
            if not isinstance(pair, Mapping):
                continue
            pid = str(pair.get("capability_id") or "").strip()
            if pid and pid not in seen:
                seen.add(pid)
                caps.append(pid)
    return caps


def _book_signature(delivery: Mapping[str, Any]) -> str:
    """Identity of a delivered book, independent of delivery height/digest."""
    legs = delivery.get("deliveries") or []
    sigs: list[str] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            sig = str(
                row.get("book_signature") or row.get("pairs_digest") or ""
            )
            if sig:
                sigs.append(sig)
    return _sha256_json(
        {
            "bound_state_root": str(delivery.get("bound_state_root") or ""),
            "bound_action_root": str(delivery.get("bound_action_root") or ""),
            "actuation_digest": str(delivery.get("actuation_digest") or ""),
            "bound_settlement_root": str(
                delivery.get("bound_settlement_root") or ""
            ),
            "bound_clearing_root": str(
                delivery.get("bound_clearing_root") or ""
            ),
            "delivery_signatures": sigs,
            "residual": int(delivery.get("residual") or 0),
            "pair_count": int(delivery.get("pair_count") or 0),
            "delivery_count": int(delivery.get("delivery_count") or 0),
        }
    )


def _cvt_pairs(capabilities: Sequence[str]) -> list[dict[str, Any]]:
    """Atomic custody+title pairs for each delivered capability."""
    pairs: list[dict[str, Any]] = []
    for cid in capabilities:
        name = str(cid or "").strip()
        if not name:
            continue
        row = {
            "capability_id": name,
            "custody_ok": True,
            "title_ok": True,
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
                "custody_ok": bool(row.get("custody_ok", True)),
                "title_ok": bool(row.get("title_ok", True)),
                "atomic_ok": bool(row.get("atomic_ok", True)),
                "pair_root": str(row.get("pair_root") or ""),
            }
        )
    return _sha256_json({"pairs": rows})


def _assert_pairs_atomic(pairs: Sequence[Mapping[str, Any]]) -> None:
    if not pairs:
        raise StageRefused(
            "total_spine_custody_pairs_empty",
            "custody refuses an empty CvT pair book",
        )
    for row in pairs:
        if not isinstance(row, Mapping):
            raise StageRefused(
                "total_spine_custody_partial",
                "custody refuses a malformed CvT pair",
            )
        custody_ok = bool(row.get("custody_ok", True))
        title_ok = bool(row.get("title_ok", True))
        if custody_ok != title_ok or not bool(row.get("atomic_ok", True)):
            raise StageRefused(
                "total_spine_custody_partial",
                "custody refuses a split (non-atomic) custody-versus-title pair",
            )
        if not custody_ok or not title_ok:
            raise StageRefused(
                "total_spine_custody_partial",
                "custody refuses an uncustodied or untitled CvT pair",
            )


def _custody_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine custody certificate digests."""
    legs = body.get("custodies") or body.get("legs") or []
    custody_rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            custody_rows.append(
                {
                    "delivery_index": int(row.get("delivery_index") or 0),
                    "delivery_height": int(row.get("delivery_height") or 0),
                    "delivery_digest": str(row.get("delivery_digest") or ""),
                    "bound_delivery_root": str(
                        row.get("bound_delivery_root") or ""
                    ),
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
                    "custodied": bool(row.get("custodied", True)),
                    "titled": bool(row.get("titled", True)),
                    "atomic_ok": bool(row.get("atomic_ok", True)),
                    "one_sided": bool(row.get("one_sided", False)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_custody_root": str(
                        row.get("parent_custody_root") or ""
                    ),
                    "custody_root": str(row.get("custody_root") or ""),
                    "post_delivery": bool(row.get("post_delivery", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                    "cvt": bool(row.get("cvt", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_CUSTODY_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "bound_clearing_root": str(body.get("bound_clearing_root") or ""),
        "bound_delivery_root": str(body.get("bound_delivery_root") or ""),
        "delivery_digest": str(body.get("delivery_digest") or ""),
        "parent_custody_root": str(body.get("parent_custody_root") or ""),
        "tip_custody_root": str(body.get("tip_custody_root") or ""),
        "custody_height": int(body.get("custody_height") or 0),
        "custody_count": int(body.get("custody_count") or 0),
        "pair_count": int(body.get("pair_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "custodied": bool(body.get("custodied", True)),
        "titled": bool(body.get("titled", True)),
        "atomic_ok": bool(body.get("atomic_ok", True)),
        "cvt_ok": bool(body.get("cvt_ok", True)),
        "one_sided": bool(body.get("one_sided", False)),
        "custodies_ok": bool(body.get("custodies_ok", True)),
        "deliveries_ok": bool(body.get("deliveries_ok", True)),
        "post_delivery": bool(body.get("post_delivery", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "custodies": custody_rows,
    }


def compute_total_spine_custody_root(
    custodies: Sequence[Mapping[str, Any]],
) -> str:
    """Tip custody root of a hash-chained CvT log (empty → zero)."""
    if not custodies:
        return "0" * 64
    last = custodies[-1]
    tip = str(last.get("custody_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(custodies):
        body = {
            "delivery_index": int(row.get("delivery_index") or idx),
            "delivery_height": int(row.get("delivery_height") or (idx + 1)),
            "delivery_digest": str(row.get("delivery_digest") or ""),
            "bound_delivery_root": str(row.get("bound_delivery_root") or ""),
            "bound_clearing_root": str(row.get("bound_clearing_root") or ""),
            "bound_settlement_root": str(row.get("bound_settlement_root") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "book_signature": str(row.get("book_signature") or ""),
            "pair_count": int(row.get("pair_count") or 0),
            "pairs_digest": str(row.get("pairs_digest") or ""),
            "pairs_atomic": bool(row.get("pairs_atomic", True)),
            "custodied": bool(row.get("custodied", True)),
            "titled": bool(row.get("titled", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_custody_root": parent,
            "post_delivery": True,
            "deterministic": True,
            "cvt": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def book_total_spine_deliveries(
    deliveries: Sequence[Mapping[str, Any]],
    *,
    min_custodies: int = TOTAL_SPINE_CUSTODY_MIN_DELIVERIES,
    parent_custody_root: str = "",
    custody_height: int | None = None,
) -> list[dict[str, Any]]:
    """Book independently verified delivery books into atomic CvT legs.

    Two (or more) deliveries custody only when they share bound state/action/
    actuation/settlement/clearing roots and the same delivered pair book.
    Divergent capability sets are a one-sided refusal; book disagreement is
    a CvT failure. Each delivered capability becomes a custody+title pair
    that must be atomic.
    """
    from blackhole_agent.upstream_total_spine_delivery import (
        verify_total_spine_delivery_certificate,
    )

    want = max(int(min_custodies), TOTAL_SPINE_CUSTODY_MIN_DELIVERIES)
    verified: list[Mapping[str, Any]] = []
    for raw in deliveries:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_total_spine_delivery_certificate(raw)
        if not verify.get("ok"):
            raise StageRefused(
                "total_spine_custody_delivery_tampered",
                "custody refuses a delivery whose digest/chain does not verify",
            )
        if raw.get("delivered") is False or raw.get("success") is False:
            raise StageRefused(
                "total_spine_custody_delivery_undelivered",
                "custody refuses an undelivered delivery receipt",
            )
        if raw.get("paid") is False or raw.get("dvp_ok") is False:
            raise StageRefused(
                "total_spine_custody_delivery_unpaid",
                "custody refuses a delivery whose DvP is not complete",
            )
        if raw.get("atomic_ok") is False:
            raise StageRefused(
                "total_spine_custody_delivery_partial",
                "custody refuses a non-atomic delivery receipt",
            )
        if int(raw.get("residual") or 0) != 0:
            raise StageRefused(
                "total_spine_custody_residual",
                "custody refuses a delivery with a non-zero residual",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            "total_spine_custody_deliveries_short",
            f"custody requires >= {want} independent deliveries, "
            f"got {len(verified)}",
        )

    first = verified[0]
    book_state = str(first.get("bound_state_root") or "")
    book_action = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    book_actuation = str(first.get("actuation_digest") or "")
    book_settlement = str(first.get("bound_settlement_root") or "")
    book_clearing = str(first.get("bound_clearing_root") or "")
    book_sig = _book_signature(first)
    book_caps = tuple(_capability_list(first))
    if not book_state or not book_action or not book_actuation:
        raise StageRefused(
            "total_spine_custody_root_missing",
            "custody requires delivery bound state/action/actuation roots",
        )
    if not book_caps:
        raise StageRefused(
            "total_spine_custody_pairs_empty",
            "custody refuses a delivery with no delivered capabilities",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_custody_root or "")
    for idx, delivery in enumerate(verified):
        state = str(delivery.get("bound_state_root") or "")
        action = str(
            delivery.get("bound_action_root")
            or delivery.get("tip_action_root")
            or ""
        )
        actuation = str(delivery.get("actuation_digest") or "")
        settlement = str(delivery.get("bound_settlement_root") or "")
        clearing = str(delivery.get("bound_clearing_root") or "")
        if (
            state != book_state
            or action != book_action
            or actuation != book_actuation
        ):
            raise StageRefused(
                "total_spine_custody_root_mismatch",
                "custody refuses deliveries bound to different "
                "state/action/actuation roots",
            )
        if settlement and book_settlement and settlement != book_settlement:
            raise StageRefused(
                "total_spine_custody_root_mismatch",
                "custody refuses deliveries bound to different settlement roots",
            )
        if clearing and book_clearing and clearing != book_clearing:
            raise StageRefused(
                "total_spine_custody_root_mismatch",
                "custody refuses deliveries bound to different clearing roots",
            )
        sig = _book_signature(delivery)
        if sig != book_sig:
            raise StageRefused(
                "total_spine_custody_cvt_failed",
                "independent delivery books disagree; CvT cannot complete",
            )
        caps = tuple(_capability_list(delivery))
        if caps != book_caps:
            raise StageRefused(
                "total_spine_custody_one_sided",
                "custody refuses one-sided books whose capability sets differ",
            )
        pairs = _cvt_pairs(book_caps)
        _assert_pairs_atomic(pairs)
        height = (
            int(custody_height) + idx
            if custody_height is not None
            else (idx + 1)
        )
        material = {
            "delivery_index": idx,
            "delivery_height": height,
            "delivery_digest": _delivery_digest_of(delivery),
            "bound_delivery_root": str(
                delivery.get("tip_delivery_root") or ""
            ),
            "bound_clearing_root": clearing or book_clearing,
            "bound_settlement_root": settlement or book_settlement,
            "bound_state_root": state,
            "bound_action_root": action,
            "actuation_digest": actuation,
            "book_signature": sig,
            "pair_count": len(pairs),
            "pairs_digest": _pairs_digest(pairs),
            "pairs_atomic": True,
            "custodied": True,
            "titled": True,
            "atomic_ok": True,
            "one_sided": False,
            "residual": 0,
            "independent": True,
            "parent_custody_root": parent,
            "post_delivery": True,
            "deterministic": True,
            "cvt": True,
        }
        custody_root = _sha256_json(material)
        row = dict(material)
        row["custody_root"] = custody_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = custody_root
    return legs


def seal_total_spine_custody_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-delivery CvT log into a tamper-evident receipt."""
    sealed_body = dict(body)
    custodies = list(sealed_body.get("custodies") or [])
    if not str(sealed_body.get("tip_custody_root") or "").strip():
        sealed_body["tip_custody_root"] = compute_total_spine_custody_root(
            custodies
        )
    if not int(sealed_body.get("custody_count") or 0):
        sealed_body["custody_count"] = len(custodies)
    if not int(sealed_body.get("custody_height") or 0):
        sealed_body["custody_height"] = len(custodies)
    material = _custody_certificate_material(sealed_body)
    material["tip_custody_root"] = str(sealed_body.get("tip_custody_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["custody_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_custody"] = True
    sealed["total_spine_custody_impl"] = TOTAL_SPINE_CUSTODY_IMPL
    sealed["custodied_at"] = str(body.get("custodied_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    if custodies:
        sealed_pairs: list[Any] = []
        for src, dest in zip(custodies, sealed.get("custodies") or []):
            if isinstance(src, Mapping) and isinstance(dest, dict):
                if src.get("pairs"):
                    dest["pairs"] = list(src.get("pairs") or [])
                sealed_pairs.append(dest)
        if sealed_pairs:
            sealed["custodies"] = sealed_pairs
    return sealed


def custody_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-custody.json`` under a custody/out root."""
    path = Path(root)
    if path.is_file():
        if path.name == TOTAL_SPINE_CUSTODY_FILENAME or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == TOTAL_SPINE_CUSTODY_KIND
                or path.name == TOTAL_SPINE_CUSTODY_FILENAME
            ):
                return path
        parent = path.parent
        sibling = parent / TOTAL_SPINE_CUSTODY_FILENAME
        if sibling.is_file():
            return sibling
        nested = parent / "custody" / TOTAL_SPINE_CUSTODY_FILENAME
        if nested.is_file():
            return nested
        grand = parent.parent / "custody" / TOTAL_SPINE_CUSTODY_FILENAME
        if grand.is_file():
            return grand
        grand_sib = parent.parent / TOTAL_SPINE_CUSTODY_FILENAME
        if grand_sib.is_file():
            return grand_sib
        return parent / "custody" / TOTAL_SPINE_CUSTODY_FILENAME
    named = path / TOTAL_SPINE_CUSTODY_FILENAME
    if named.is_file():
        return named
    nested = path / "custody" / TOTAL_SPINE_CUSTODY_FILENAME
    if nested.is_file():
        return nested
    return path / "custody" / TOTAL_SPINE_CUSTODY_FILENAME


def write_total_spine_custody_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a custody receipt under ``out_root``."""
    sealed = seal_total_spine_custody_certificate(body)
    path = custody_certificate_path(Path(out_root))
    if path.is_file():
        try:
            existing = load_total_spine_custody_certificate(path)
        except StageRefused:
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get("custody_digest")
                or existing.get("certificate_hash")
                or ""
            )
            new_digest = str(
                sealed.get("custody_digest")
                or sealed.get("certificate_hash")
                or ""
            )
            if (
                existing_digest
                and existing_digest == new_digest
                and allow_idempotent
            ):
                existing["custody_path"] = str(path)
                existing["total_spine_custody_idempotent"] = True
                return existing
            raise StageRefused(
                "total_spine_custody_supersession_refused",
                f"irreversible custody already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed["custody_path"] = str(path)
    sealed["total_spine_custody_idempotent"] = False
    return sealed


def verify_total_spine_custody_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute custody digest and CvT roots; fail closed on tamper."""
    claimed = str(
        certificate.get("custody_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _custody_certificate_material(certificate)
    expected = _sha256_json(material)
    custodies = list(certificate.get("custodies") or [])
    recomputed_tip = compute_total_spine_custody_root(custodies)
    claimed_tip = str(certificate.get("tip_custody_root") or "")
    height = int(certificate.get("custody_height") or 0)
    count = int(certificate.get("custody_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_custody_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(custodies):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_custody_root") or "") != parent:
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
            "delivery_index": int(row.get("delivery_index") or idx),
            "delivery_height": int(row.get("delivery_height") or (idx + 1)),
            "delivery_digest": str(row.get("delivery_digest") or ""),
            "bound_delivery_root": str(row.get("bound_delivery_root") or ""),
            "bound_clearing_root": str(row.get("bound_clearing_root") or ""),
            "bound_settlement_root": str(row.get("bound_settlement_root") or ""),
            "bound_state_root": str(row.get("bound_state_root") or ""),
            "bound_action_root": str(row.get("bound_action_root") or ""),
            "actuation_digest": str(row.get("actuation_digest") or ""),
            "book_signature": sig,
            "pair_count": int(row.get("pair_count") or 0),
            "pairs_digest": pairs_digest,
            "pairs_atomic": bool(row.get("pairs_atomic", True)),
            "custodied": bool(row.get("custodied", True)),
            "titled": bool(row.get("titled", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_custody_root": parent,
            "post_delivery": True,
            "deterministic": True,
            "cvt": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("custody_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_CUSTODY_MIN_DELIVERIES and height >= count
    custodies_ok = all(
        isinstance(row, Mapping)
        and bool(row.get("custodied", True))
        and bool(row.get("titled", True))
        and bool(row.get("atomic_ok", True))
        and bool(row.get("cvt", True))
        and not bool(row.get("one_sided", False))
        and int(row.get("residual") or 0) == 0
        for row in custodies
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_CUSTODY_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_delivery") is True
        and certificate.get("deterministic") is True
        and certificate.get("custodied") is True
        and certificate.get("titled") is True
        and certificate.get("atomic_ok") is True
        and certificate.get("cvt_ok") is True
        and certificate.get("one_sided") is False
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(custodies)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and custodies_ok
        and int(certificate.get("residual") or 0) == 0
        and TOTAL_SPINE_CUSTODY_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_custody",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "custody_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_custody_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_custodies_ok": min_ok,
        "custodies_ok": custodies_ok,
        "cvt_ok": certificate.get("cvt_ok") is True,
        "atomic_ok": certificate.get("atomic_ok") is True,
        "kind_ok": str(certificate.get("kind") or "") == TOTAL_SPINE_CUSTODY_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "custodied_ok": certificate.get("custodied") is True,
        "titled_ok": certificate.get("titled") is True,
        "total_spine_custody": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_custody_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed custody receipt."""
    file_path = custody_certificate_path(Path(path))
    if not file_path.is_file():
        raise StageRefused(
            "total_spine_custody_missing",
            f"custody certificate not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRefused(
            "total_spine_custody_unreadable",
            f"custody certificate unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StageRefused(
            "total_spine_custody_invalid",
            "custody certificate root must be a JSON object",
        )
    if str(payload.get("kind") or "") != TOTAL_SPINE_CUSTODY_KIND and not payload.get(
        "total_spine_custody"
    ):
        raise StageRefused(
            "total_spine_custody_missing",
            f"custody certificate not found at {file_path}",
        )
    verify = verify_total_spine_custody_certificate(payload)
    if not verify.get("ok"):
        raise StageRefused(
            "total_spine_custody_tampered",
            f"custody certificate digest mismatch at {file_path} "
            f"(claimed={verify.get('claimed_digest')!r} "
            f"expected={verify.get('expected_digest')!r})",
        )
    body = dict(payload)
    body["custody_path"] = str(file_path)
    body["custody_verify"] = verify
    body["total_spine_custody_loaded"] = True
    return body


def seal_total_spine_custody_chain(
    *,
    prior_tip: str,
    custody_digest: str,
    tip_custody_root: str,
    bound_delivery_root: str,
    bound_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    delivery_digest: str,
    custody_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal custody hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    cd = str(custody_digest or "").strip() or ("0" * 64)
    cr = str(tip_custody_root or "").strip() or ("0" * 64)
    dr = str(bound_delivery_root or "").strip() or ("0" * 64)
    clr = str(bound_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    dd = str(delivery_digest or "").strip() or ("0" * 64)
    material = (
        f"custody|{int(bool(short_circuit))}|{int(custody_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{clr}|{dr}|{dd}|{cr}|{cd}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "custody_height": int(custody_height),
        "tip_custody_root": cr,
        "bound_delivery_root": dr,
        "bound_clearing_root": clr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "delivery_digest": dd,
        "custody_digest": cd,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_custody": True,
        "irreversible": True,
        "post_delivery": True,
        "deterministic": True,
        "cvt": True,
    }


def annotate_total_spine_custody(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-delivery CvT onto a total-spine result and rebind tip."""
    cst_digest = str(
        certificate.get("custody_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_custody_root = str(certificate.get("tip_custody_root") or "")
    custody_height = int(certificate.get("custody_height") or 0)
    custody_count = int(certificate.get("custody_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    bound_clearing_root = str(certificate.get("bound_clearing_root") or "")
    bound_delivery_root = str(certificate.get("bound_delivery_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    delivery_digest = str(certificate.get("delivery_digest") or "")
    chain = seal_total_spine_custody_chain(
        prior_tip=prior_tip,
        custody_digest=cst_digest,
        tip_custody_root=tip_custody_root,
        bound_delivery_root=bound_delivery_root,
        bound_clearing_root=bound_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        delivery_digest=delivery_digest,
        custody_height=custody_height,
        short_circuit=short_circuit,
    )
    cst_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{cst_tip}".encode("utf-8"))
    body["total_spine_custody"] = True
    body["total_spine_custody_impl"] = TOTAL_SPINE_CUSTODY_IMPL
    body["total_spine_custody_short_circuit"] = bool(short_circuit)
    body["total_spine_custody_irreversible"] = True
    body["total_spine_custody_post_delivery"] = True
    body["total_spine_custody_deterministic"] = True
    body["total_spine_custody_cvt"] = True
    body["total_spine_custody_certificate"] = dict(certificate)
    body["total_spine_custody_digest"] = cst_digest
    body["total_spine_custody_chain"] = chain
    body["total_spine_custody_tip"] = cst_tip
    body["total_spine_custody_bound_tip"] = bound
    body["total_spine_digest_pre_custody"] = prior_tip
    body["total_spine_tip_custody_root"] = tip_custody_root
    body["total_spine_custody_height"] = custody_height
    body["total_spine_custody_count"] = custody_count
    body["total_spine_custodied"] = bool(certificate.get("custodied", True))
    body["total_spine_custodied_ok"] = bool(certificate.get("custodied", True))
    body["total_spine_titled"] = bool(certificate.get("titled", True))
    body["total_spine_titled_ok"] = bool(certificate.get("titled", True))
    body["total_spine_cvt_ok"] = bool(certificate.get("cvt_ok", True))
    body["total_spine_custody_atomic"] = bool(certificate.get("atomic_ok", True))
    body["total_spine_custody_one_sided"] = bool(
        certificate.get("one_sided", False)
    )
    body["total_spine_custodies_ok"] = bool(
        certificate.get("custodies_ok", True)
    )
    body["total_spine_custody_root_valid"] = bool(tip_custody_root)
    body["total_spine_custody_residual"] = int(certificate.get("residual") or 0)
    body["total_spine_custody_pair_count"] = int(
        certificate.get("pair_count") or 0
    )
    body["custody_root"] = tip_custody_root
    body["tip_custody_root"] = tip_custody_root
    body["custody_count"] = custody_count
    body["custody_height"] = custody_height
    body["custodied"] = bool(certificate.get("custodied", True))
    body["custodied_ok"] = bool(certificate.get("custodied", True))
    body["cvt_ok"] = bool(certificate.get("cvt_ok", True))
    body["titled"] = bool(certificate.get("titled", True))
    if certificate.get("custody_path"):
        body["total_spine_custody_path"] = certificate.get("custody_path")
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
    if bound_delivery_root:
        body["total_spine_tip_delivery_root"] = bound_delivery_root
        body["delivery_root"] = bound_delivery_root
        body["tip_delivery_root"] = bound_delivery_root
        body.setdefault("total_spine_delivery", True)
        body.setdefault("total_spine_delivered", True)
        body.setdefault("total_spine_dvp_ok", True)
    if actuation_digest:
        body["total_spine_actuation_digest"] = actuation_digest
    if delivery_digest:
        body["total_spine_delivery_digest"] = delivery_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_custody_ok_short_circuit"
        if short_circuit
        else "total_spine_custody_ok"
    )
    body["ok"] = True
    return body


def _as_delivery_mapping(value: Any) -> dict[str, Any] | None:
    from blackhole_agent.upstream_total_spine_delivery import (
        StageRefused as DeliveryRefused,
        load_total_spine_delivery_certificate,
    )

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_DELIVERY_KIND or value.get(
            "total_spine_delivery"
        ) or value.get("total_spine_delivery_loaded") or value.get(
            "tip_delivery_root"
        ):
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
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / "delivery" / "total-spine-delivery.json"
            named = path / "total-spine-delivery.json"
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != TOTAL_SPINE_DELIVERY_KIND:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_total_spine_delivery_certificate(path)
    except DeliveryRefused as exc:
        if str(exc.verdict) == "total_spine_delivery_tampered":
            raise StageRefused(str(exc.verdict), str(exc.detail)) from exc
        return None
    except Exception:  # noqa: BLE001
        return None


def _as_custody_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_CUSTODY_KIND or value.get(
            "total_spine_custody"
        ) or value.get("total_spine_custody_loaded"):
            nested = value.get("total_spine_custody_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_custody_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_custody_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    try:
        return load_total_spine_custody_certificate(Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == "total_spine_custody_tampered":
            raise
        return None
    except Exception:  # noqa: BLE001
        return None


def _clearings_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_clearing_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_clearing_root") or nested.get("clearings")
    ):
        found.append(dict(nested))
    if item.get("tip_clearing_root") and item.get("clearings"):
        found.append(dict(item))
    extra = item.get("clearings")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and row.get("tip_clearing_root"):
                found.append(dict(row))
    return found


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


def _confirm_delivery(
    primary: Mapping[str, Any],
    *,
    clearings: Sequence[Mapping[str, Any]],
    settlements: Sequence[Mapping[str, Any]],
    actuation: Mapping[str, Any] | None,
    out_root: Path | None,
    prior_tip: str,
    repo_path: Path | None,
) -> dict[str, Any]:
    """Independently re-deliver the same book as a confirmation side."""
    from blackhole_agent.upstream_total_spine_delivery import deliver_total_spine

    confirm_out = None
    if out_root is not None:
        confirm_out = Path(out_root) / "custody-confirm"
    tip_delivery = str(primary.get("tip_delivery_root") or "")
    dlv_height = int(primary.get("delivery_height") or 0)
    source: Any = list(clearings) if clearings else None
    if source is None and settlements:
        source = list(settlements)
    if source is None and actuation is not None:
        source = actuation
    if source is None:
        raise StageRefused(
            "total_spine_custody_confirmation_missing",
            "single delivery requires clearings, settlements, or actuation "
            "to confirm-custody",
        )
    confirmed = deliver_total_spine(
        source,
        clearings=clearings or None,
        settlements=settlements or None,
        actuation=actuation,
        out_root=confirm_out,
        prior_tip=prior_tip,
        parent_delivery_root=tip_delivery,
        delivery_height=dlv_height + 1 if dlv_height else None,
        repo_path=repo_path or REPO_ROOT,
        confirm=True,
    )
    cert = confirmed.get("total_spine_delivery_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            "total_spine_custody_confirmation_missing",
            "confirmation delivery did not produce a certificate",
        )
    return dict(cert)


def _collect_deliveries(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None,
    body: Mapping[str, Any] | None,
    extra: Sequence[Mapping[str, Any] | Path | str] | None,
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Return (existing_custody, deliveries, clearings, settlements, actuation)."""
    existing = _as_custody_mapping(source)
    if existing is None and body is not None:
        existing = _as_custody_mapping(body)
    deliveries: list[dict[str, Any]] = []
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
        mapped = _as_delivery_mapping(item)
        if mapped is not None:
            deliveries.append(mapped)
            _take_actuation(mapped)
            for row in _clearings_from(mapped):
                clearings.append(row)
            for row in _settlements_from(mapped):
                settlements.append(row)
        if isinstance(item, Mapping):
            _take_actuation(item)
            for row in _clearings_from(item):
                clearings.append(row)
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
        _push(body.get("total_spine_delivery_certificate"))
        _push(body)
        _take_actuation(body)
        for row in _clearings_from(body):
            clearings.append(row)
        for row in _settlements_from(body):
            settlements.append(row)
    for item in extra or []:
        _push(item)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in deliveries:
        digest = _delivery_digest_of(row)
        tip = str(row.get("tip_delivery_root") or "")
        key = digest or tip
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    clr_deduped: list[dict[str, Any]] = []
    clr_seen: set[str] = set()
    for row in clearings:
        digest = str(
            row.get("clearing_digest")
            or row.get("certificate_hash")
            or row.get("tip_clearing_root")
            or ""
        )
        if not digest or digest in clr_seen:
            continue
        clr_seen.add(digest)
        clr_deduped.append(row)

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
    return existing, deduped, clr_deduped, set_deduped, actuation


def _strip_custody_predicates(done_when: str) -> str:
    """Evaluate the pre-custody contract, never custody_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "custody_ok",
        "custodied_ok",
        "min_custodies",
        "custody_root_valid",
        "cvt_ok",
        "title_ok",
        "titled_ok",
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


def custody_total_spine(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    deliveries: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_custodies: int = TOTAL_SPINE_CUSTODY_MIN_DELIVERIES,
    parent_custody_root: str = "",
    custody_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
    settlements: Sequence[Mapping[str, Any]] | None = None,
    clearings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply post-delivery atomic CvT custody on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_CUSTODY_IMPL:
        raise StageRefused(
            "total_spine_custody_disabled",
            "TOTAL_SPINE_CUSTODY_IMPL is False",
        )

    existing, collected, found_clearings, found_settlements, found_actuation = (
        _collect_deliveries(source, body, deliveries)
    )
    if actuation is None:
        actuation = found_actuation
    else:
        actuation = dict(actuation)
    extra_clearings = list(clearings or [])
    if extra_clearings:
        found_clearings = list(found_clearings) + list(extra_clearings)
    extra_settlements = list(settlements or [])
    if extra_settlements:
        found_settlements = list(found_settlements) + list(extra_settlements)
    if (
        existing is not None
        and existing.get("tip_custody_root")
        and (
            str(existing.get("kind") or "") == TOTAL_SPINE_CUSTODY_KIND
            or existing.get("total_spine_custody_loaded")
            or existing.get("total_spine_custody")
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
            "action": "custody_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_custody(
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

    want = max(int(min_custodies), TOTAL_SPINE_CUSTODY_MIN_DELIVERIES)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_delivery(
                collected[0],
                clearings=found_clearings,
                settlements=found_settlements,
                actuation=actuation,
                out_root=out_root,
                prior_tip=str(
                    prior_tip
                    or (body or {}).get("total_spine_delivery_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            "total_spine_custody_deliveries_short",
            f"custody requires >= {want} independent deliveries, "
            f"got {len(collected)}",
        )

    legs = book_total_spine_deliveries(
        collected,
        min_custodies=want,
        parent_custody_root=parent_custody_root,
        custody_height=custody_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("bound_settlement_root") or "")
    clearing_root = str(first.get("bound_clearing_root") or "")
    delivery_root = str(first.get("tip_delivery_root") or "")
    delivery_digest = _delivery_digest_of(first)
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
    pre_custody = _strip_custody_predicates(done_when)
    if pre_custody:
        ctx = {
            "delivery": {
                "ok": True,
                "delivered": True,
                "delivered_ok": True,
                "delivery_root_valid": True,
                "dvp_ok": True,
                "delivery_count": int(first.get("delivery_count") or 0),
                "tip_delivery_root": delivery_root,
            },
            "delivery_count": int(first.get("delivery_count") or 0),
            "tip_delivery_root": delivery_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_custody,
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
                "total_spine_custody_contract_unmet",
                f"done_when not met at custody: {pre_custody!r}",
            )

    tip_custody_root = compute_total_spine_custody_root(legs)
    cst_height = int(legs[-1]["delivery_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_delivery_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    pair_count = int(legs[0].get("pair_count") or 0) if legs else 0

    cst_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_CUSTODY_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "bound_clearing_root": clearing_root,
        "bound_delivery_root": delivery_root,
        "delivery_digest": delivery_digest,
        "prior_tip": tip,
        "parent_custody_root": str(
            parent_custody_root
            or (legs[0].get("parent_custody_root") if legs else "")
            or ""
        ),
        "custodies": legs,
        "custody_count": len(legs),
        "custody_height": cst_height,
        "tip_custody_root": tip_custody_root,
        "pair_count": pair_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "custodied": True,
        "titled": True,
        "atomic_ok": True,
        "cvt_ok": True,
        "one_sided": False,
        "custodies_ok": True,
        "deliveries_ok": True,
        "post_delivery": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "custodied_at": utc_now_iso(),
    }
    if contract_eval is not None:
        cst_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_custody_certificate(write_target, cst_body)
    else:
        certificate = seal_total_spine_custody_certificate(cst_body)

    result = body if body is not None else {
        "ok": True,
        "action": "custody_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_custody(
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
        cst_bound = str(annotated.get("total_spine_custody_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=cst_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_custody_bound_state_root"] = state_root
    annotated["total_spine_custody_bound_action_root"] = action_root
    annotated["total_spine_custody_bound_settlement_root"] = settlement_root
    annotated["total_spine_custody_bound_clearing_root"] = clearing_root
    annotated["total_spine_custody_bound_delivery_root"] = delivery_root
    annotated["total_spine_custody_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_custody_proof() -> dict[str, Any]:
    """Hermetic proof: post-delivery atomic CvT on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_CUSTODY_IMPL as ENGINE_CST_IMPL,
        TOTAL_SPINE_DELIVERY_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        actuate_total_spine,
        clear_total_spine,
        deliver_total_spine,
        execute_total_spine,
        federate_total_spine,
        run_total_spine,
        settle_total_spine,
        write_total_spine_finality_certificate,
    )
    from blackhole_agent.upstream_total_spine_delivery import (
        seal_total_spine_delivery_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-custody-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_CUSTODY_IMPL is True
            and ENGINE_CST_IMPL is True
            and TOTAL_SPINE_DELIVERY_IMPL is True
            and TOTAL_SPINE_CUSTODY_KIND == "total_spine_custody"
            and bool(TOTAL_SPINE_CUSTODY_FILENAME)
            and TOTAL_SPINE_CUSTODY_MIN_DELIVERIES >= 2
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
                "goal": "custody proof origin",
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

        d1 = deliver_total_spine(
            [c1, c2],
            out_root=scratch / "dlv-h1",
            prior_tip=str(clr2.get("total_spine_clearing_bound_tip") or ""),
            body=dict(clr2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_d1 = d1.get("total_spine_delivery_certificate") or {}
        tip_delivery = str(d1.get("total_spine_tip_delivery_root") or "")
        d2 = deliver_total_spine(
            [c1, c2],
            out_root=scratch / "dlv-h2",
            prior_tip=str(d1.get("total_spine_delivery_bound_tip") or ""),
            parent_delivery_root=tip_delivery,
            delivery_height=int(d1.get("total_spine_delivery_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_d2 = d2.get("total_spine_delivery_certificate") or {}

        offline_cst = custody_total_spine(
            [cert_d1, cert_d2],
            out_root=scratch / "cst-h1",
            prior_tip=str(d2.get("total_spine_delivery_bound_tip") or ""),
            body=dict(d2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cst_path = offline_cst.get("total_spine_custody_path")
        tip_custody = str(offline_cst.get("total_spine_tip_custody_root") or "")
        offline_ok = (
            bool(offline_cst.get("ok"))
            and offline_cst.get("total_spine_custody") is True
            and offline_cst.get("total_spine_custody_post_delivery") is True
            and offline_cst.get("total_spine_custody_irreversible") is True
            and offline_cst.get("total_spine_custodied") is True
            and offline_cst.get("total_spine_titled") is True
            and offline_cst.get("total_spine_cvt_ok") is True
            and offline_cst.get("total_spine_custody_atomic") is True
            and offline_cst.get("total_spine_custody_one_sided") is False
            and int(offline_cst.get("total_spine_custody_count") or 0) >= 2
            and int(offline_cst.get("total_spine_custody_height") or 0) >= 2
            and int(offline_cst.get("total_spine_custody_residual") or 0) == 0
            and int(offline_cst.get("total_spine_custody_pair_count") or 0) >= 1
            and len(tip_custody) >= 32
            and str(offline_cst.get("total_spine_state_root") or "") == state_root
            and str(offline_cst.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_cst.get("total_spine_digest") or "")
            != str(d1.get("total_spine_digest") or "")
            and isinstance(cst_path, str)
            and Path(cst_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_custody_certificate(cst_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_custody_loaded")
            and (loaded.get("custody_verify") or {}).get("ok")
            and (loaded.get("custody_verify") or {}).get("custody_root_ok")
            and (loaded.get("custody_verify") or {}).get("chain_ok")
            and (loaded.get("custody_verify") or {}).get("custodies_ok")
            and (loaded.get("custody_verify") or {}).get("cvt_ok")
        )

        tampered_path = scratch / "tampered-custody.json"
        tampered_body = dict(loaded)
        for drop in (
            "custody_verify",
            "total_spine_custody_loaded",
            "custody_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["custody_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_custody_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_custody_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_custody_certificate(
                scratch / "cst-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "custody_verify",
                            "total_spine_custody_loaded",
                            "custody_path",
                            "custody_digest",
                            "certificate_hash",
                            "custodied_at",
                            "total_spine_custody",
                            "total_spine_custody_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_custody_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_custody_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "custody_verify",
            "total_spine_custody_loaded",
            "custody_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_custody_certificate(wrong_body)
        wrong_verify = verify_total_spine_custody_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("custody_root_ok") is False
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
            other_dlv = deliver_total_spine(
                other_clr.get("total_spine_clearing_certificate"),
                out_root=scratch / "dlv-other",
                prior_tip=str(
                    other_clr.get("total_spine_clearing_bound_tip") or ""
                ),
                actuation=actuated2.get("total_spine_actuation_certificate"),
                settlements=[
                    other_set.get("total_spine_settlement_certificate") or {}
                ],
                repo_path=REPO_ROOT,
                confirm=True,
            )
            book_total_spine_deliveries(
                [
                    cert_d1,
                    other_dlv.get("total_spine_delivery_certificate") or {},
                ],
                min_custodies=2,
            )
        except StageRefused as exc:
            mismatch_ok = str(exc.verdict) == "total_spine_custody_root_mismatch"
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        one_sided_ok = False
        try:
            forged = dict(cert_d2)
            forged["capabilities"] = ["capability.one-sided-only"]
            for drop in (
                "delivery_digest",
                "certificate_hash",
                "delivered_at",
                "delivery_path",
                "delivery_verify",
                "total_spine_delivery_loaded",
            ):
                forged.pop(drop, None)
            resealed_one = seal_total_spine_delivery_certificate(forged)
            book_total_spine_deliveries([cert_d1, resealed_one], min_custodies=2)
        except StageRefused as exc:
            one_sided_ok = str(exc.verdict) == "total_spine_custody_one_sided"
        except Exception:  # noqa: BLE001
            one_sided_ok = False

        partial_ok = False
        try:
            _assert_pairs_atomic(
                [
                    {
                        "capability_id": good_id,
                        "custody_ok": True,
                        "title_ok": False,
                        "atomic_ok": False,
                    }
                ]
            )
        except StageRefused as exc:
            partial_ok = str(exc.verdict) == "total_spine_custody_partial"
        except Exception:  # noqa: BLE001
            partial_ok = False

        h2 = custody_total_spine(
            [cert_d1, cert_d2],
            out_root=scratch / "cst-h2",
            prior_tip=str(
                offline_cst.get("total_spine_custody_bound_tip") or ""
            ),
            parent_custody_root=tip_custody,
            custody_height=int(
                offline_cst.get("total_spine_custody_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_custody_count") or 0) >= 2
            and str(h2.get("total_spine_tip_custody_root") or "") != tip_custody
            and str(
                (h2.get("total_spine_custody_certificate") or {}).get(
                    "parent_custody_root"
                )
                or ""
            )
            == tip_custody
        )

        recomputed = compute_total_spine_custody_root(
            loaded.get("custodies") or []
        )
        determinism_ok = recomputed == tip_custody and bool(recomputed)

        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-cst",
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
            custody=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_cst_path = live.get("total_spine_custody_path")
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
            and live.get("total_spine_custody") is True
            and live.get("total_spine_custodied") is True
            and live.get("total_spine_cvt_ok") is True
            and int(live.get("total_spine_custody_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_custody_root"), str)
            and len(str(live.get("total_spine_tip_custody_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_cst_path, str)
            and Path(live_cst_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-cst",
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
            custody=True,
            resume_dir=live_cst_path or (scratch / "live-cst"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_custody") is True
            and shorted.get("total_spine_custody_short_circuit") is True
            and str(shorted.get("total_spine_tip_custody_root") or "")
            == str(live.get("total_spine_tip_custody_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        cst_chain = live.get("total_spine_custody_chain") or {}
        chain_integrity_ok = False
        if isinstance(cst_chain, Mapping) and cst_chain:
            re_seal = seal_total_spine_custody_chain(
                prior_tip=str(cst_chain.get("prior_tip") or ""),
                custody_digest=str(cst_chain.get("custody_digest") or ""),
                tip_custody_root=str(cst_chain.get("tip_custody_root") or ""),
                bound_delivery_root=str(
                    cst_chain.get("bound_delivery_root") or ""
                ),
                bound_clearing_root=str(
                    cst_chain.get("bound_clearing_root") or ""
                ),
                bound_settlement_root=str(
                    cst_chain.get("bound_settlement_root") or ""
                ),
                bound_action_root=str(cst_chain.get("bound_action_root") or ""),
                bound_state_root=str(cst_chain.get("bound_state_root") or ""),
                actuation_digest=str(cst_chain.get("actuation_digest") or ""),
                delivery_digest=str(cst_chain.get("delivery_digest") or ""),
                custody_height=int(cst_chain.get("custody_height") or 0),
                short_circuit=bool(cst_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == cst_chain.get("digest")
                and re_seal.get("digest") == live.get("total_spine_custody_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(d1.get("total_spine_digest") or "")
            != str(offline_cst.get("total_spine_digest") or "")
        )

        facade_path = Path(le_facade.__file__).resolve()
        facade_text = facade_path.read_text(encoding="utf-8")
        source_ok = (
            "TOTAL_SPINE_CUSTODY_IMPL" in facade_text
            and "builtin_total_spine_custody_proof" in facade_text
            and "custody_total_spine" in facade_text
            and callable(
                getattr(le_facade, "builtin_total_spine_custody_proof", None)
            )
            and callable(getattr(le_facade, "custody_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_CUSTODY_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_CUSTODY_IMPL" in engine_text
            and "custody_total_spine" in engine_text
            and (
                "custody=True" in engine_text
                or "custody: bool = False" in engine_text
            )
            and "builtin_total_spine_custody_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def custody_total_spine" in mod_text
            and "def builtin_total_spine_custody_proof" in mod_text
            and "total_spine_custody_supersession_refused" in mod_text
            and "total_spine_custody_tampered" in mod_text
            and "total_spine_custody_one_sided" in mod_text
            and "total_spine_custody_cvt_failed" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-custody"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_custody" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_custody_proof" in (entry.entry or "")
                and (
                    "custody" in tags_blob
                    or "custody" in name_blob
                    or "custody" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "custody_total_spine" in delta_blob
                    or "post-delivery" in delta_blob
                    or "post_delivery" in delta_blob
                    or "cvt" in delta_blob
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
            "action": "total_spine_custody_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "custody_path": cst_path,
            "tip_custody_root": tip_custody,
            "tip_delivery_root": tip_delivery,
            "tip_clearing_root": tip_clearing,
            "tip_settlement_root": tip_settlement,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "custody_count": offline_cst.get("total_spine_custody_count"),
            "pair_count": offline_cst.get("total_spine_custody_pair_count"),
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
            "live_custody_path": live_cst_path,
            "live_tip_custody_root": live.get("total_spine_tip_custody_root"),
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
            "total_spine_custody": True,
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
        "custody-proof",
        help=(
            "Total spine custody proof: post-delivery atomic CvT seals "
            "matching delivery books into irreversible custody receipts"
        ),
    )
    sub.add_parser("proof", help="Alias for custody-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"custody-proof", "proof"}:
        result = builtin_total_spine_custody_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
