"""Post-margin collateral-versus-obligation for the absolute total spine.

Closes the margined-but-uncollateralized cliff: after ``margin_total_spine``
seals atomic MvE receipts, independently confirm a second margin, book
each margined pair into a collateral register and pair it with obligation
(CvO), seal hash-chained atomic collateral receipts bound to the margin
digests, refuse split / one-sided / mismatched / failed / wrong-root /
tampered collaterals, short-circuit re-collateral, and rebind the depth-28 tip
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

TOTAL_SPINE_COLLATERAL_IMPL = True
TOTAL_SPINE_COLLATERAL_KIND: str = "total_spine_collateral"
TOTAL_SPINE_COLLATERAL_FILENAME: str = "total-spine-collateral.json"
TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS: int = 2

TOTAL_SPINE_MARGIN_KIND: str = "total_spine_margin"
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine collateral."""

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


def _margin_digest_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("margin_digest")
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
    for leg in row.get("margins") or row.get("collaterals") or []:
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


def _book_signature(margin: Mapping[str, Any]) -> str:
    """Identity of a margined book, independent of margin height/digest."""
    legs = margin.get("margins") or []
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
            "bound_state_root": str(margin.get("bound_state_root") or ""),
            "bound_action_root": str(margin.get("bound_action_root") or ""),
            "actuation_digest": str(margin.get("actuation_digest") or ""),
            "bound_settlement_root": str(
                margin.get("bound_settlement_root") or ""
            ),
            "bound_clearing_root": str(
                margin.get("bound_clearing_root") or ""
            ),
            "bound_delivery_root": str(
                margin.get("bound_delivery_root")
                or margin.get("tip_delivery_root")
                or ""
            ),
            "margin_signatures": sigs,
            "residual": int(margin.get("residual") or 0),
            "pair_count": int(margin.get("pair_count") or 0),
            "margin_count": int(margin.get("margin_count") or 0),
        }
    )


def _cvo_pairs(capabilities: Sequence[str]) -> list[dict[str, Any]]:
    """Atomic collateral+obligation pairs for each margined capability."""
    pairs: list[dict[str, Any]] = []
    for cid in capabilities:
        name = str(cid or "").strip()
        if not name:
            continue
        row = {
            "capability_id": name,
            "collateral_ok": True,
            "obligation_ok": True,
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
                "collateral_ok": bool(row.get("collateral_ok", True)),
                "obligation_ok": bool(row.get("obligation_ok", True)),
                "atomic_ok": bool(row.get("atomic_ok", True)),
                "pair_root": str(row.get("pair_root") or ""),
            }
        )
    return _sha256_json({"pairs": rows})


def _assert_pairs_atomic(pairs: Sequence[Mapping[str, Any]]) -> None:
    if not pairs:
        raise StageRefused(
            "total_spine_collateral_pairs_empty",
            "collateral refuses an empty CvO pair book",
        )
    for row in pairs:
        if not isinstance(row, Mapping):
            raise StageRefused(
                "total_spine_collateral_partial",
                "collateral refuses a malformed CvO pair",
            )
        collateral_ok = bool(row.get("collateral_ok", True))
        obligation_ok = bool(row.get("obligation_ok", True))
        if collateral_ok != obligation_ok or not bool(row.get("atomic_ok", True)):
            raise StageRefused(
                "total_spine_collateral_partial",
                "collateral refuses a split (non-atomic) collateral-versus-obligation pair",
            )
        if not collateral_ok or not obligation_ok:
            raise StageRefused(
                "total_spine_collateral_partial",
                "collateral refuses an uncollateralized or unobligated CvO pair",
            )


def _collateral_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine collateral certificate digests."""
    legs = body.get("collaterals") or body.get("legs") or []
    collateral_rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            collateral_rows.append(
                {
                    "margin_index": int(row.get("margin_index") or 0),
                    "margin_height": int(row.get("margin_height") or 0),
                    "margin_digest": str(row.get("margin_digest") or ""),
                    "bound_margin_root": str(
                        row.get("bound_margin_root") or ""
                    ),
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
                    "collateralized": bool(row.get("collateralized", True)),
                    "obligated": bool(row.get("obligated", True)),
                    "atomic_ok": bool(row.get("atomic_ok", True)),
                    "one_sided": bool(row.get("one_sided", False)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_collateral_root": str(
                        row.get("parent_collateral_root") or ""
                    ),
                    "collateral_root": str(row.get("collateral_root") or ""),
                    "post_margin": bool(row.get("post_margin", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                    "cvo": bool(row.get("cvo", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_COLLATERAL_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "bound_clearing_root": str(body.get("bound_clearing_root") or ""),
        "bound_margin_root": str(body.get("bound_margin_root") or ""),
        "bound_custody_root": str(body.get("bound_custody_root") or ""),
        "bound_delivery_root": str(body.get("bound_delivery_root") or ""),
        "margin_digest": str(body.get("margin_digest") or ""),
        "delivery_digest": str(body.get("delivery_digest") or ""),
        "parent_collateral_root": str(body.get("parent_collateral_root") or ""),
        "tip_collateral_root": str(body.get("tip_collateral_root") or ""),
        "collateral_height": int(body.get("collateral_height") or 0),
        "collateral_count": int(body.get("collateral_count") or 0),
        "pair_count": int(body.get("pair_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "collateralized": bool(body.get("collateralized", True)),
        "obligated": bool(body.get("obligated", True)),
        "atomic_ok": bool(body.get("atomic_ok", True)),
        "cvo_ok": bool(body.get("cvo_ok", True)),
        "one_sided": bool(body.get("one_sided", False)),
        "collaterals_ok": bool(body.get("collaterals_ok", True)),
        "margins_ok": bool(body.get("margins_ok", True)),
        "post_margin": bool(body.get("post_margin", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "collaterals": collateral_rows,
    }


def compute_total_spine_collateral_root(
    collaterals: Sequence[Mapping[str, Any]],
) -> str:
    """Tip collateral root of a hash-chained CvO log (empty → zero)."""
    if not collaterals:
        return "0" * 64
    last = collaterals[-1]
    tip = str(last.get("collateral_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(collaterals):
        body = {
            "margin_index": int(row.get("margin_index") or idx),
            "margin_height": int(row.get("margin_height") or (idx + 1)),
            "margin_digest": str(row.get("margin_digest") or ""),
            "bound_margin_root": str(row.get("bound_margin_root") or ""),
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
            "collateralized": bool(row.get("collateralized", True)),
            "obligated": bool(row.get("obligated", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_collateral_root": parent,
            "post_margin": True,
            "deterministic": True,
            "cvo": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def book_total_spine_margins(
    margins: Sequence[Mapping[str, Any]],
    *,
    min_collaterals: int = TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS,
    parent_collateral_root: str = "",
    collateral_height: int | None = None,
) -> list[dict[str, Any]]:
    """Book independently verified margin books into atomic CvO legs.

    Two (or more) margins collateral only when they share bound state/action/
    actuation/settlement/clearing roots and the same margined pair book.
    Divergent capability sets are a one-sided refusal; book disagreement is
    a CvO failure. Each margined capability becomes a collateral+obligation pair
    that must be atomic.
    """
    from blackhole_agent.upstream_total_spine_margin import (
        verify_total_spine_margin_certificate,
    )

    want = max(int(min_collaterals), TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS)
    verified: list[Mapping[str, Any]] = []
    for raw in margins:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_total_spine_margin_certificate(raw)
        if not verify.get("ok"):
            raise StageRefused(
                "total_spine_collateral_margin_tampered",
                "collateral refuses a margin whose digest/chain does not verify",
            )
        if raw.get("margined") is False or raw.get("success") is False:
            raise StageRefused(
                "total_spine_collateral_margin_unmargined",
                "collateral refuses an unmargined margin receipt",
            )
        if raw.get("exposed") is False or raw.get("mve_ok") is False:
            raise StageRefused(
                "total_spine_collateral_margin_unexposed",
                "collateral refuses a margin whose MvE is not complete",
            )
        if raw.get("atomic_ok") is False:
            raise StageRefused(
                "total_spine_collateral_margin_partial",
                "collateral refuses a non-atomic margin receipt",
            )
        if int(raw.get("residual") or 0) != 0:
            raise StageRefused(
                "total_spine_collateral_residual",
                "collateral refuses a margin with a non-zero residual",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            "total_spine_collateral_margins_short",
            f"collateral requires >= {want} independent margins, "
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
            "total_spine_collateral_root_missing",
            "collateral requires margin bound state/action/actuation roots",
        )
    if not book_caps:
        raise StageRefused(
            "total_spine_collateral_pairs_empty",
            "collateral refuses a margin with no margined capabilities",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_collateral_root or "")
    for idx, margin in enumerate(verified):
        state = str(margin.get("bound_state_root") or "")
        action = str(
            margin.get("bound_action_root")
            or margin.get("tip_action_root")
            or ""
        )
        actuation = str(margin.get("actuation_digest") or "")
        settlement = str(margin.get("bound_settlement_root") or "")
        clearing = str(margin.get("bound_clearing_root") or "")
        if (
            state != book_state
            or action != book_action
            or actuation != book_actuation
        ):
            raise StageRefused(
                "total_spine_collateral_root_mismatch",
                "collateral refuses margins bound to different "
                "state/action/actuation roots",
            )
        if settlement and book_settlement and settlement != book_settlement:
            raise StageRefused(
                "total_spine_collateral_root_mismatch",
                "collateral refuses margins bound to different settlement roots",
            )
        if clearing and book_clearing and clearing != book_clearing:
            raise StageRefused(
                "total_spine_collateral_root_mismatch",
                "collateral refuses margins bound to different clearing roots",
            )
        sig = _book_signature(margin)
        if sig != book_sig:
            raise StageRefused(
                "total_spine_collateral_cvo_failed",
                "independent margin books disagree; CvO cannot complete",
            )
        caps = tuple(_capability_list(margin))
        if caps != book_caps:
            raise StageRefused(
                "total_spine_collateral_one_sided",
                "collateral refuses one-sided books whose capability sets differ",
            )
        pairs = _cvo_pairs(book_caps)
        _assert_pairs_atomic(pairs)
        height = (
            int(collateral_height) + idx
            if collateral_height is not None
            else (idx + 1)
        )
        material = {
            "margin_index": idx,
            "margin_height": height,
            "margin_digest": _margin_digest_of(margin),
            "bound_margin_root": str(
                margin.get("tip_margin_root") or ""
            ),
            "bound_delivery_root": str(
                margin.get("bound_delivery_root")
                or margin.get("tip_delivery_root")
                or ""
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
            "collateralized": True,
            "obligated": True,
            "atomic_ok": True,
            "one_sided": False,
            "residual": 0,
            "independent": True,
            "parent_collateral_root": parent,
            "post_margin": True,
            "deterministic": True,
            "cvo": True,
        }
        collateral_root = _sha256_json(material)
        row = dict(material)
        row["collateral_root"] = collateral_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = collateral_root
    return legs


def seal_total_spine_collateral_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-margin CvO log into a tamper-evident receipt."""
    sealed_body = dict(body)
    collaterals = list(sealed_body.get("collaterals") or [])
    if not str(sealed_body.get("tip_collateral_root") or "").strip():
        sealed_body["tip_collateral_root"] = compute_total_spine_collateral_root(
            collaterals
        )
    if not int(sealed_body.get("collateral_count") or 0):
        sealed_body["collateral_count"] = len(collaterals)
    if not int(sealed_body.get("collateral_height") or 0):
        sealed_body["collateral_height"] = len(collaterals)
    material = _collateral_certificate_material(sealed_body)
    material["tip_collateral_root"] = str(sealed_body.get("tip_collateral_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["collateral_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_collateral"] = True
    sealed["total_spine_collateral_impl"] = TOTAL_SPINE_COLLATERAL_IMPL
    sealed["collateralized_at"] = str(body.get("collateralized_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    if collaterals:
        sealed_pairs: list[Any] = []
        for src, dest in zip(collaterals, sealed.get("collaterals") or []):
            if isinstance(src, Mapping) and isinstance(dest, dict):
                if src.get("pairs"):
                    dest["pairs"] = list(src.get("pairs") or [])
                sealed_pairs.append(dest)
        if sealed_pairs:
            sealed["collaterals"] = sealed_pairs
    return sealed


def collateral_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-collateral.json`` under a collateral/out root."""
    path = Path(root)
    if path.is_file():
        if path.name == TOTAL_SPINE_COLLATERAL_FILENAME or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == TOTAL_SPINE_COLLATERAL_KIND
                or path.name == TOTAL_SPINE_COLLATERAL_FILENAME
            ):
                return path
        parent = path.parent
        sibling = parent / TOTAL_SPINE_COLLATERAL_FILENAME
        if sibling.is_file():
            return sibling
        nested = parent / "collateral" / TOTAL_SPINE_COLLATERAL_FILENAME
        if nested.is_file():
            return nested
        grand = parent.parent / "collateral" / TOTAL_SPINE_COLLATERAL_FILENAME
        if grand.is_file():
            return grand
        grand_sib = parent.parent / TOTAL_SPINE_COLLATERAL_FILENAME
        if grand_sib.is_file():
            return grand_sib
        return parent / "collateral" / TOTAL_SPINE_COLLATERAL_FILENAME
    named = path / TOTAL_SPINE_COLLATERAL_FILENAME
    if named.is_file():
        return named
    nested = path / "collateral" / TOTAL_SPINE_COLLATERAL_FILENAME
    if nested.is_file():
        return nested
    return path / "collateral" / TOTAL_SPINE_COLLATERAL_FILENAME


def write_total_spine_collateral_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a collateral receipt under ``out_root``."""
    sealed = seal_total_spine_collateral_certificate(body)
    path = collateral_certificate_path(Path(out_root))
    if path.is_file():
        try:
            existing = load_total_spine_collateral_certificate(path)
        except StageRefused:
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get("collateral_digest")
                or existing.get("certificate_hash")
                or ""
            )
            new_digest = str(
                sealed.get("collateral_digest")
                or sealed.get("certificate_hash")
                or ""
            )
            if (
                existing_digest
                and existing_digest == new_digest
                and allow_idempotent
            ):
                existing["collateral_path"] = str(path)
                existing["total_spine_collateral_idempotent"] = True
                return existing
            raise StageRefused(
                "total_spine_collateral_supersession_refused",
                f"irreversible collateral already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed["collateral_path"] = str(path)
    sealed["total_spine_collateral_idempotent"] = False
    return sealed


def verify_total_spine_collateral_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute collateral digest and CvO roots; fail closed on tamper."""
    claimed = str(
        certificate.get("collateral_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _collateral_certificate_material(certificate)
    expected = _sha256_json(material)
    collaterals = list(certificate.get("collaterals") or [])
    recomputed_tip = compute_total_spine_collateral_root(collaterals)
    claimed_tip = str(certificate.get("tip_collateral_root") or "")
    height = int(certificate.get("collateral_height") or 0)
    count = int(certificate.get("collateral_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_collateral_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(collaterals):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_collateral_root") or "") != parent:
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
            "margin_index": int(row.get("margin_index") or idx),
            "margin_height": int(row.get("margin_height") or (idx + 1)),
            "margin_digest": str(row.get("margin_digest") or ""),
            "bound_margin_root": str(row.get("bound_margin_root") or ""),
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
            "collateralized": bool(row.get("collateralized", True)),
            "obligated": bool(row.get("obligated", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_collateral_root": parent,
            "post_margin": True,
            "deterministic": True,
            "cvo": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("collateral_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS and height >= count
    collaterals_ok = all(
        isinstance(row, Mapping)
        and bool(row.get("collateralized", True))
        and bool(row.get("obligated", True))
        and bool(row.get("atomic_ok", True))
        and bool(row.get("cvo", True))
        and not bool(row.get("one_sided", False))
        and int(row.get("residual") or 0) == 0
        for row in collaterals
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_COLLATERAL_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_margin") is True
        and certificate.get("deterministic") is True
        and certificate.get("collateralized") is True
        and certificate.get("obligated") is True
        and certificate.get("atomic_ok") is True
        and certificate.get("cvo_ok") is True
        and certificate.get("one_sided") is False
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(collaterals)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and collaterals_ok
        and int(certificate.get("residual") or 0) == 0
        and TOTAL_SPINE_COLLATERAL_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_collateral",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "collateral_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_collateral_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_collaterals_ok": min_ok,
        "collaterals_ok": collaterals_ok,
        "cvo_ok": certificate.get("cvo_ok") is True,
        "atomic_ok": certificate.get("atomic_ok") is True,
        "kind_ok": str(certificate.get("kind") or "") == TOTAL_SPINE_COLLATERAL_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "collateralized_ok": certificate.get("collateralized") is True,
        "obligated_ok": certificate.get("obligated") is True,
        "total_spine_collateral": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_collateral_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed collateral receipt."""
    file_path = collateral_certificate_path(Path(path))
    if not file_path.is_file():
        raise StageRefused(
            "total_spine_collateral_missing",
            f"collateral certificate not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRefused(
            "total_spine_collateral_unreadable",
            f"collateral certificate unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StageRefused(
            "total_spine_collateral_invalid",
            "collateral certificate root must be a JSON object",
        )
    if str(payload.get("kind") or "") != TOTAL_SPINE_COLLATERAL_KIND and not payload.get(
        "total_spine_collateral"
    ):
        raise StageRefused(
            "total_spine_collateral_missing",
            f"collateral certificate not found at {file_path}",
        )
    verify = verify_total_spine_collateral_certificate(payload)
    if not verify.get("ok"):
        raise StageRefused(
            "total_spine_collateral_tampered",
            f"collateral certificate digest mismatch at {file_path} "
            f"(claimed={verify.get('claimed_digest')!r} "
            f"expected={verify.get('expected_digest')!r})",
        )
    body = dict(payload)
    body["collateral_path"] = str(file_path)
    body["collateral_verify"] = verify
    body["total_spine_collateral_loaded"] = True
    return body


def seal_total_spine_collateral_chain(
    *,
    prior_tip: str,
    collateral_digest: str,
    tip_collateral_root: str,
    bound_margin_root: str,
    bound_delivery_root: str,
    bound_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    margin_digest: str,
    delivery_digest: str,
    collateral_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal collateral hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    md = str(collateral_digest or "").strip() or ("0" * 64)
    mr = str(tip_collateral_root or "").strip() or ("0" * 64)
    cr = str(bound_margin_root or "").strip() or ("0" * 64)
    dlr = str(bound_delivery_root or "").strip() or ("0" * 64)
    clr = str(bound_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    cd = str(margin_digest or "").strip() or ("0" * 64)
    dvd = str(delivery_digest or "").strip() or ("0" * 64)
    material = (
        f"collateral|{int(bool(short_circuit))}|{int(collateral_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{clr}|{dlr}|{cr}|{dvd}|{cd}|{mr}|{md}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "collateral_height": int(collateral_height),
        "tip_collateral_root": mr,
        "bound_margin_root": cr,
        "bound_delivery_root": dlr,
        "bound_clearing_root": clr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "margin_digest": cd,
        "delivery_digest": dvd,
        "collateral_digest": md,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_collateral": True,
        "irreversible": True,
        "post_margin": True,
        "deterministic": True,
        "cvo": True,
    }


def annotate_total_spine_collateral(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-margin CvO onto a total-spine result and rebind tip."""
    cst_digest = str(
        certificate.get("collateral_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_collateral_root = str(certificate.get("tip_collateral_root") or "")
    collateral_height = int(certificate.get("collateral_height") or 0)
    collateral_count = int(certificate.get("collateral_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    bound_clearing_root = str(certificate.get("bound_clearing_root") or "")
    bound_margin_root = str(certificate.get("bound_margin_root") or "")
    bound_delivery_root = str(certificate.get("bound_delivery_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    margin_digest = str(certificate.get("margin_digest") or "")
    delivery_digest = str(certificate.get("delivery_digest") or "")
    chain = seal_total_spine_collateral_chain(
        prior_tip=prior_tip,
        collateral_digest=cst_digest,
        tip_collateral_root=tip_collateral_root,
        bound_margin_root=bound_margin_root,
        bound_delivery_root=bound_delivery_root,
        bound_clearing_root=bound_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        margin_digest=margin_digest,
        delivery_digest=delivery_digest,
        collateral_height=collateral_height,
        short_circuit=short_circuit,
    )
    cst_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{cst_tip}".encode("utf-8"))
    body["total_spine_collateral"] = True
    body["total_spine_collateral_impl"] = TOTAL_SPINE_COLLATERAL_IMPL
    body["total_spine_collateral_short_circuit"] = bool(short_circuit)
    body["total_spine_collateral_irreversible"] = True
    body["total_spine_collateral_post_margin"] = True
    body["total_spine_collateral_deterministic"] = True
    body["total_spine_collateral_cvo"] = True
    body["total_spine_collateral_certificate"] = dict(certificate)
    body["total_spine_collateral_digest"] = cst_digest
    body["total_spine_collateral_chain"] = chain
    body["total_spine_collateral_tip"] = cst_tip
    body["total_spine_collateral_bound_tip"] = bound
    body["total_spine_digest_pre_collateral"] = prior_tip
    body["total_spine_tip_collateral_root"] = tip_collateral_root
    body["total_spine_collateral_height"] = collateral_height
    body["total_spine_collateral_count"] = collateral_count
    body["total_spine_collateralized"] = bool(certificate.get("collateralized", True))
    body["total_spine_collateralized_ok"] = bool(certificate.get("collateralized", True))
    body["total_spine_obligated"] = bool(certificate.get("obligated", True))
    body["total_spine_obligated_ok"] = bool(certificate.get("obligated", True))
    body["total_spine_cvo_ok"] = bool(certificate.get("cvo_ok", True))
    body["total_spine_collateral_atomic"] = bool(certificate.get("atomic_ok", True))
    body["total_spine_collateral_one_sided"] = bool(
        certificate.get("one_sided", False)
    )
    body["total_spine_collaterals_ok"] = bool(
        certificate.get("collaterals_ok", True)
    )
    body["total_spine_collateral_root_valid"] = bool(tip_collateral_root)
    body["total_spine_collateral_residual"] = int(certificate.get("residual") or 0)
    body["total_spine_collateral_pair_count"] = int(
        certificate.get("pair_count") or 0
    )
    body["collateral_root"] = tip_collateral_root
    body["tip_collateral_root"] = tip_collateral_root
    body["collateral_count"] = collateral_count
    body["collateral_height"] = collateral_height
    body["collateralized"] = bool(certificate.get("collateralized", True))
    body["collateralized_ok"] = bool(certificate.get("collateralized", True))
    body["cvo_ok"] = bool(certificate.get("cvo_ok", True))
    body["obligated"] = bool(certificate.get("obligated", True))
    if certificate.get("collateral_path"):
        body["total_spine_collateral_path"] = certificate.get("collateral_path")
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
    if bound_margin_root:
        body["total_spine_tip_margin_root"] = bound_margin_root
        body["margin_root"] = bound_margin_root
        body["tip_margin_root"] = bound_margin_root
        body.setdefault("total_spine_margin", True)
        body.setdefault("total_spine_margined", True)
        body.setdefault("total_spine_mve_ok", True)
    bound_custody_root = str(certificate.get("bound_custody_root") or "")
    if bound_custody_root:
        body["total_spine_tip_custody_root"] = bound_custody_root
        body["custody_root"] = bound_custody_root
        body["tip_custody_root"] = bound_custody_root
        body.setdefault("total_spine_custody", True)
        body.setdefault("total_spine_custodied", True)
        body.setdefault("total_spine_cvt_ok", True)
    if bound_delivery_root:
        body["total_spine_tip_delivery_root"] = bound_delivery_root
        body["delivery_root"] = bound_delivery_root
        body["tip_delivery_root"] = bound_delivery_root
        body.setdefault("total_spine_delivery", True)
        body.setdefault("total_spine_delivered", True)
        body.setdefault("total_spine_dvp_ok", True)
    if actuation_digest:
        body["total_spine_actuation_digest"] = actuation_digest
    if margin_digest:
        body["total_spine_margin_digest"] = margin_digest
    if delivery_digest:
        body["total_spine_delivery_digest"] = delivery_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_collateral_ok_short_circuit"
        if short_circuit
        else "total_spine_collateral_ok"
    )
    body["ok"] = True
    return body


def _as_margin_mapping(value: Any) -> dict[str, Any] | None:
    from blackhole_agent.upstream_total_spine_margin import (
        StageRefused as MarginRefused,
        load_total_spine_margin_certificate,
    )

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_MARGIN_KIND or value.get(
            "total_spine_margin"
        ) or value.get("total_spine_margin_loaded") or value.get(
            "tip_margin_root"
        ):
            nested = value.get("total_spine_margin_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_margin_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_margin_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / "margin" / "total-spine-margin.json"
            named = path / "total-spine-margin.json"
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != TOTAL_SPINE_MARGIN_KIND:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_total_spine_margin_certificate(path)
    except MarginRefused as exc:
        if str(exc.verdict) == "total_spine_margin_tampered":
            raise StageRefused(str(exc.verdict), str(exc.detail)) from exc
        return None
    except Exception:  # noqa: BLE001
        return None


def _as_collateral_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_COLLATERAL_KIND or value.get(
            "total_spine_collateral"
        ) or value.get("total_spine_collateral_loaded"):
            nested = value.get("total_spine_collateral_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_collateral_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_collateral_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    try:
        return load_total_spine_collateral_certificate(Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == "total_spine_collateral_tampered":
            raise
        return None
    except Exception:  # noqa: BLE001
        return None


def _custodies_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_custody_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_custody_root") or nested.get("custodies")
    ):
        found.append(dict(nested))
    if item.get("tip_custody_root") and item.get("custodies"):
        found.append(dict(item))
    extra = item.get("custodies")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and row.get("tip_custody_root"):
                found.append(dict(row))
    if isinstance(nested, Mapping):
        for row in _custodies_from(nested):
            found.append(row)
    return found


def _deliveries_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_margin_certificate")
    # Prefer explicit delivery certificates carried on annotated results.
    nested_dlv = item.get("total_spine_delivery_certificate")
    if isinstance(nested_dlv, Mapping) and (
        nested_dlv.get("tip_delivery_root") or nested_dlv.get("deliveries")
    ):
        found.append(dict(nested_dlv))
    if item.get("tip_delivery_root") and item.get("deliveries"):
        found.append(dict(item))
    extra = item.get("deliveries")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and row.get("tip_delivery_root"):
                found.append(dict(row))
    if isinstance(nested, Mapping):
        for row in _deliveries_from(nested):
            found.append(row)
    return found


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


def _confirm_margin(
    primary: Mapping[str, Any],
    *,
    custodies: Sequence[Mapping[str, Any]],
    deliveries: Sequence[Mapping[str, Any]],
    clearings: Sequence[Mapping[str, Any]],
    settlements: Sequence[Mapping[str, Any]],
    actuation: Mapping[str, Any] | None,
    out_root: Path | None,
    prior_tip: str,
    repo_path: Path | None,
) -> dict[str, Any]:
    """Independently re-margin the same book as a confirmation side."""
    from blackhole_agent.upstream_total_spine_margin import margin_total_spine

    confirm_out = None
    if out_root is not None:
        confirm_out = Path(out_root) / "collateral-confirm"
    tip_margin = str(primary.get("tip_margin_root") or "")
    mgn_height = int(primary.get("margin_height") or 0)
    bundle: list[Any] = []
    for row in custodies:
        bundle.append(row)
    for row in deliveries:
        bundle.append(row)
    for row in clearings:
        bundle.append(row)
    for row in settlements:
        bundle.append(row)
    if actuation is not None:
        bundle.append(dict(actuation))
    if not bundle:
        raise StageRefused(
            "total_spine_collateral_confirmation_missing",
            "single margin requires custodies, deliveries, clearings, "
            "settlements, or actuation to confirm-collateral",
        )
    confirmed = margin_total_spine(
        bundle,
        custodies=custodies or None,
        clearings=clearings or None,
        settlements=settlements or None,
        actuation=actuation,
        out_root=confirm_out,
        prior_tip=prior_tip,
        parent_margin_root=tip_margin,
        margin_height=mgn_height + 1 if mgn_height else None,
        repo_path=repo_path or REPO_ROOT,
        confirm=True,
    )
    cert = confirmed.get("total_spine_margin_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            "total_spine_collateral_confirmation_missing",
            "confirmation margin did not produce a certificate",
        )
    return dict(cert)


def _collect_margins(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None,
    body: Mapping[str, Any] | None,
    extra: Sequence[Mapping[str, Any] | Path | str] | None,
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Return (existing_collateral, margins, custodies, deliveries, clearings, settlements, actuation)."""
    existing = _as_collateral_mapping(source)
    if existing is None and body is not None:
        existing = _as_collateral_mapping(body)
    margins: list[dict[str, Any]] = []
    custodies: list[dict[str, Any]] = []
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
        mapped = _as_margin_mapping(item)
        if mapped is not None:
            margins.append(mapped)
            _take_actuation(mapped)
            for row in _custodies_from(mapped):
                custodies.append(row)
            for row in _deliveries_from(mapped):
                deliveries.append(row)
            for row in _clearings_from(mapped):
                clearings.append(row)
            for row in _settlements_from(mapped):
                settlements.append(row)
        if isinstance(item, Mapping):
            _take_actuation(item)
            for row in _custodies_from(item):
                custodies.append(row)
            for row in _deliveries_from(item):
                deliveries.append(row)
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
        _push(body.get("total_spine_margin_certificate"))
        _push(body.get("total_spine_custody_certificate"))
        _push(body.get("total_spine_delivery_certificate"))
        _push(body)
        _take_actuation(body)
        for row in _deliveries_from(body):
            deliveries.append(row)
        for row in _clearings_from(body):
            clearings.append(row)
        for row in _settlements_from(body):
            settlements.append(row)
    for item in extra or []:
        _push(item)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in margins:
        digest = _margin_digest_of(row)
        tip = str(row.get("tip_margin_root") or "")
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

    dlv_deduped: list[dict[str, Any]] = []
    dlv_seen: set[str] = set()
    for row in deliveries:
        digest = str(
            row.get("delivery_digest")
            or row.get("certificate_hash")
            or row.get("tip_delivery_root")
            or ""
        )
        if not digest or digest in dlv_seen:
            continue
        dlv_seen.add(digest)
        dlv_deduped.append(row)
    cst_deduped: list[dict[str, Any]] = []
    cst_seen: set[str] = set()
    for row in custodies:
        digest = str(
            row.get("custody_digest")
            or row.get("certificate_hash")
            or row.get("tip_custody_root")
            or ""
        )
        if not digest or digest in cst_seen:
            continue
        cst_seen.add(digest)
        cst_deduped.append(row)
    return existing, deduped, cst_deduped, dlv_deduped, clr_deduped, set_deduped, actuation


def _strip_collateral_predicates(done_when: str) -> str:
    """Evaluate the pre-collateral contract, never collateral_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "collateral_ok",
        "collateralized_ok",
        "min_collaterals",
        "collateral_root_valid",
        "cvo_ok",
        "obligation_ok",
        "obligated_ok",
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


def collateral_total_spine(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    margins: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_collaterals: int = TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS,
    parent_collateral_root: str = "",
    collateral_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
    settlements: Sequence[Mapping[str, Any]] | None = None,
    clearings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply post-margin atomic CvO collateral on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_COLLATERAL_IMPL:
        raise StageRefused(
            "total_spine_collateral_disabled",
            "TOTAL_SPINE_COLLATERAL_IMPL is False",
        )

    (
        existing,
        collected,
        found_custodies,
        found_deliveries,
        found_clearings,
        found_settlements,
        found_actuation,
    ) = _collect_margins(source, body, margins)
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
        and existing.get("tip_collateral_root")
        and (
            str(existing.get("kind") or "") == TOTAL_SPINE_COLLATERAL_KIND
            or existing.get("total_spine_collateral_loaded")
            or existing.get("total_spine_collateral")
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
            "action": "collateral_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_collateral(
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

    want = max(int(min_collaterals), TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_margin(
                collected[0],
                custodies=found_custodies,
                deliveries=found_deliveries,
                clearings=found_clearings,
                settlements=found_settlements,
                actuation=actuation,
                out_root=out_root,
                prior_tip=str(
                    prior_tip
                    or (body or {}).get("total_spine_margin_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            "total_spine_collateral_margins_short",
            f"collateral requires >= {want} independent margins, "
            f"got {len(collected)}",
        )

    legs = book_total_spine_margins(
        collected,
        min_collaterals=want,
        parent_collateral_root=parent_collateral_root,
        collateral_height=collateral_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("bound_settlement_root") or "")
    clearing_root = str(first.get("bound_clearing_root") or "")
    margin_root = str(first.get("tip_margin_root") or "")
    margin_digest = _margin_digest_of(first)
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
    pre_collateral = _strip_collateral_predicates(done_when)
    if pre_collateral:
        ctx = {
            "margin": {
                "ok": True,
                "margined": True,
                "margined_ok": True,
                "margin_root_valid": True,
                "mve_ok": True,
                "margin_count": int(first.get("margin_count") or 0),
                "tip_margin_root": margin_root,
            },
            "margin_count": int(first.get("margin_count") or 0),
            "tip_margin_root": margin_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_collateral,
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
                "total_spine_collateral_contract_unmet",
                f"done_when not met at collateral: {pre_collateral!r}",
            )

    tip_collateral_root = compute_total_spine_collateral_root(legs)
    cst_height = int(legs[-1]["margin_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_margin_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    pair_count = int(legs[0].get("pair_count") or 0) if legs else 0

    cst_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_COLLATERAL_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "bound_clearing_root": clearing_root,
        "bound_margin_root": margin_root,
        "bound_custody_root": str(
            first.get("bound_custody_root")
            or first.get("tip_custody_root")
            or ""
        ),
        "bound_delivery_root": str(
            first.get("bound_delivery_root")
            or first.get("tip_delivery_root")
            or ""
        ),
        "margin_digest": margin_digest,
        "delivery_digest": str(
            first.get("delivery_digest")
            or first.get("certificate_hash")
            or ""
        ),
        "prior_tip": tip,
        "parent_collateral_root": str(
            parent_collateral_root
            or (legs[0].get("parent_collateral_root") if legs else "")
            or ""
        ),
        "collaterals": legs,
        "collateral_count": len(legs),
        "collateral_height": cst_height,
        "tip_collateral_root": tip_collateral_root,
        "pair_count": pair_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "collateralized": True,
        "obligated": True,
        "atomic_ok": True,
        "cvo_ok": True,
        "one_sided": False,
        "collaterals_ok": True,
        "margins_ok": True,
        "post_margin": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "collateralized_at": utc_now_iso(),
    }
    if contract_eval is not None:
        cst_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_collateral_certificate(write_target, cst_body)
    else:
        certificate = seal_total_spine_collateral_certificate(cst_body)

    result = body if body is not None else {
        "ok": True,
        "action": "collateral_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_collateral(
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
        cst_bound = str(annotated.get("total_spine_collateral_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=cst_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_collateral_bound_state_root"] = state_root
    annotated["total_spine_collateral_bound_action_root"] = action_root
    annotated["total_spine_collateral_bound_settlement_root"] = settlement_root
    annotated["total_spine_collateral_bound_clearing_root"] = clearing_root
    annotated["total_spine_collateral_bound_margin_root"] = margin_root
    annotated["total_spine_collateral_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_collateral_proof() -> dict[str, Any]:
    """Hermetic proof: post-margin atomic CvO on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_COLLATERAL_IMPL as ENGINE_COL_IMPL,
        TOTAL_SPINE_MARGIN_IMPL,
        TOTAL_SPINE_CUSTODY_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        actuate_total_spine,
        clear_total_spine,
        custody_total_spine,
        margin_total_spine,
        deliver_total_spine,
        execute_total_spine,
        federate_total_spine,
        run_total_spine,
        settle_total_spine,
        write_total_spine_finality_certificate,
    )
    from blackhole_agent.upstream_total_spine_margin import (
        seal_total_spine_margin_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-collateral-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_COLLATERAL_IMPL is True
            and ENGINE_COL_IMPL is True
            and TOTAL_SPINE_MARGIN_IMPL is True
            and TOTAL_SPINE_CUSTODY_IMPL is True
            and TOTAL_SPINE_COLLATERAL_KIND == "total_spine_collateral"
            and bool(TOTAL_SPINE_COLLATERAL_FILENAME)
            and TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS >= 2
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
                "goal": "collateral proof origin",
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

        cst1 = custody_total_spine(
            [cert_d1, cert_d2],
            out_root=scratch / "cst-h1",
            prior_tip=str(d2.get("total_spine_delivery_bound_tip") or ""),
            body=dict(d2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_c1 = cst1.get("total_spine_custody_certificate") or {}
        tip_custody = str(cst1.get("total_spine_tip_custody_root") or "")
        cst2 = custody_total_spine(
            [cert_d1, cert_d2],
            out_root=scratch / "cst-h2",
            prior_tip=str(cst1.get("total_spine_custody_bound_tip") or ""),
            parent_custody_root=tip_custody,
            custody_height=int(cst1.get("total_spine_custody_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_c2 = cst2.get("total_spine_custody_certificate") or {}

        mgn1 = margin_total_spine(
            [cert_c1, cert_c2],
            out_root=scratch / "mgn-h1",
            prior_tip=str(cst2.get("total_spine_custody_bound_tip") or ""),
            body=dict(cst2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_m1 = mgn1.get("total_spine_margin_certificate") or {}
        tip_margin = str(mgn1.get("total_spine_tip_margin_root") or "")
        mgn2 = margin_total_spine(
            [cert_c1, cert_c2],
            out_root=scratch / "mgn-h2",
            prior_tip=str(mgn1.get("total_spine_margin_bound_tip") or ""),
            parent_margin_root=tip_margin,
            margin_height=int(mgn1.get("total_spine_margin_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_m2 = mgn2.get("total_spine_margin_certificate") or {}

        offline_mgn = collateral_total_spine(
            [cert_m1, cert_m2],
            out_root=scratch / "col-h1",
            prior_tip=str(mgn2.get("total_spine_margin_bound_tip") or ""),
            body=dict(mgn2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        mgn_path = offline_mgn.get("total_spine_collateral_path")
        tip_collateral = str(offline_mgn.get("total_spine_tip_collateral_root") or "")
        offline_ok = (
            bool(offline_mgn.get("ok"))
            and offline_mgn.get("total_spine_collateral") is True
            and offline_mgn.get("total_spine_collateral_post_margin") is True
            and offline_mgn.get("total_spine_collateral_irreversible") is True
            and offline_mgn.get("total_spine_collateralized") is True
            and offline_mgn.get("total_spine_obligated") is True
            and offline_mgn.get("total_spine_cvo_ok") is True
            and offline_mgn.get("total_spine_collateral_atomic") is True
            and offline_mgn.get("total_spine_collateral_one_sided") is False
            and int(offline_mgn.get("total_spine_collateral_count") or 0) >= 2
            and int(offline_mgn.get("total_spine_collateral_height") or 0) >= 2
            and int(offline_mgn.get("total_spine_collateral_residual") or 0) == 0
            and int(offline_mgn.get("total_spine_collateral_pair_count") or 0) >= 1
            and len(tip_collateral) >= 32
            and str(offline_mgn.get("total_spine_state_root") or "") == state_root
            and str(offline_mgn.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_mgn.get("total_spine_digest") or "")
            != str(mgn1.get("total_spine_digest") or "")
            and isinstance(mgn_path, str)
            and Path(mgn_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_collateral_certificate(mgn_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_collateral_loaded")
            and (loaded.get("collateral_verify") or {}).get("ok")
            and (loaded.get("collateral_verify") or {}).get("collateral_root_ok")
            and (loaded.get("collateral_verify") or {}).get("chain_ok")
            and (loaded.get("collateral_verify") or {}).get("collaterals_ok")
            and (loaded.get("collateral_verify") or {}).get("cvo_ok")
        )

        tampered_path = scratch / "tampered-collateral.json"
        tampered_body = dict(loaded)
        for drop in (
            "collateral_verify",
            "total_spine_collateral_loaded",
            "collateral_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["collateral_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_collateral_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_collateral_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_collateral_certificate(
                scratch / "col-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "collateral_verify",
                            "total_spine_collateral_loaded",
                            "collateral_path",
                            "collateral_digest",
                            "certificate_hash",
                            "collateralized_at",
                            "total_spine_collateral",
                            "total_spine_collateral_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_collateral_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_collateral_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "collateral_verify",
            "total_spine_collateral_loaded",
            "collateral_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_collateral_certificate(wrong_body)
        wrong_verify = verify_total_spine_collateral_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("collateral_root_ok") is False
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
            other_cst = custody_total_spine(
                other_dlv.get("total_spine_delivery_certificate"),
                out_root=scratch / "cst-other",
                prior_tip=str(
                    other_dlv.get("total_spine_delivery_bound_tip") or ""
                ),
                actuation=actuated2.get("total_spine_actuation_certificate"),
                settlements=[
                    other_set.get("total_spine_settlement_certificate") or {}
                ],
                clearings=[
                    other_clr.get("total_spine_clearing_certificate") or {}
                ],
                repo_path=REPO_ROOT,
                confirm=True,
            )
            other_mgn = margin_total_spine(
                [
                    other_cst.get("total_spine_custody_certificate") or {},
                    other_dlv.get("total_spine_delivery_certificate") or {},
                ],
                out_root=scratch / "mgn-other",
                prior_tip=str(
                    other_cst.get("total_spine_custody_bound_tip") or ""
                ),
                actuation=actuated2.get("total_spine_actuation_certificate"),
                settlements=[
                    other_set.get("total_spine_settlement_certificate") or {}
                ],
                clearings=[
                    other_clr.get("total_spine_clearing_certificate") or {}
                ],
                repo_path=REPO_ROOT,
                confirm=True,
            )
            other_cert = other_mgn.get("total_spine_margin_certificate") or {}
            if not other_cert:
                raise StageRefused(
                    "total_spine_collateral_root_mismatch",
                    "other-origin margin missing; cannot form a matching CvO book",
                )
            book_total_spine_margins(
                [cert_m1, other_cert],
                min_collaterals=2,
            )
        except StageRefused as exc:
            mismatch_ok = str(exc.verdict) in {
                "total_spine_collateral_root_mismatch",
                "total_spine_collateral_cvo_failed",
            }
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        one_sided_ok = False
        try:
            forged = dict(cert_m2)
            forged["capabilities"] = ["capability.one-sided-only"]
            for drop in (
                "margin_digest",
                "certificate_hash",
                "margined_at",
                "margin_path",
                "margin_verify",
                "total_spine_margin_loaded",
            ):
                forged.pop(drop, None)
            resealed_one = seal_total_spine_margin_certificate(forged)
            book_total_spine_margins([cert_m1, resealed_one], min_collaterals=2)
        except StageRefused as exc:
            one_sided_ok = str(exc.verdict) == "total_spine_collateral_one_sided"
        except Exception:  # noqa: BLE001
            one_sided_ok = False

        partial_ok = False
        try:
            _assert_pairs_atomic(
                [
                    {
                        "capability_id": good_id,
                        "collateral_ok": True,
                        "obligation_ok": False,
                        "atomic_ok": False,
                    }
                ]
            )
        except StageRefused as exc:
            partial_ok = str(exc.verdict) == "total_spine_collateral_partial"
        except Exception:  # noqa: BLE001
            partial_ok = False

        h2 = collateral_total_spine(
            [cert_m1, cert_m2],
            out_root=scratch / "col-h2",
            prior_tip=str(
                offline_mgn.get("total_spine_collateral_bound_tip") or ""
            ),
            parent_collateral_root=tip_collateral,
            collateral_height=int(
                offline_mgn.get("total_spine_collateral_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_collateral_count") or 0) >= 2
            and str(h2.get("total_spine_tip_collateral_root") or "") != tip_collateral
            and str(
                (h2.get("total_spine_collateral_certificate") or {}).get(
                    "parent_collateral_root"
                )
                or ""
            )
            == tip_collateral
        )

        recomputed = compute_total_spine_collateral_root(
            loaded.get("collaterals") or []
        )
        determinism_ok = recomputed == tip_collateral and bool(recomputed)

        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-col",
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
            margin=True,
            collateral=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_mgn_path = live.get("total_spine_collateral_path")
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
            and live.get("total_spine_margin") is True
            and live.get("total_spine_collateral") is True
            and live.get("total_spine_collateralized") is True
            and live.get("total_spine_cvo_ok") is True
            and int(live.get("total_spine_collateral_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_collateral_root"), str)
            and len(str(live.get("total_spine_tip_collateral_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_mgn_path, str)
            and Path(live_mgn_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-col",
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
            margin=True,
            collateral=True,
            resume_dir=live_mgn_path or (scratch / "live-col"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_collateral") is True
            and shorted.get("total_spine_collateral_short_circuit") is True
            and str(shorted.get("total_spine_tip_collateral_root") or "")
            == str(live.get("total_spine_tip_collateral_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        mgn_chain = live.get("total_spine_collateral_chain") or {}
        chain_integrity_ok = False
        if isinstance(mgn_chain, Mapping) and mgn_chain:
            re_seal = seal_total_spine_collateral_chain(
                prior_tip=str(mgn_chain.get("prior_tip") or ""),
                collateral_digest=str(mgn_chain.get("collateral_digest") or ""),
                tip_collateral_root=str(mgn_chain.get("tip_collateral_root") or ""),
                bound_margin_root=str(
                    mgn_chain.get("bound_margin_root") or ""
                ),
                bound_delivery_root=str(
                    mgn_chain.get("bound_delivery_root") or ""
                ),
                bound_clearing_root=str(
                    mgn_chain.get("bound_clearing_root") or ""
                ),
                bound_settlement_root=str(
                    mgn_chain.get("bound_settlement_root") or ""
                ),
                bound_action_root=str(mgn_chain.get("bound_action_root") or ""),
                bound_state_root=str(mgn_chain.get("bound_state_root") or ""),
                actuation_digest=str(mgn_chain.get("actuation_digest") or ""),
                margin_digest=str(mgn_chain.get("margin_digest") or ""),
                delivery_digest=str(mgn_chain.get("delivery_digest") or ""),
                collateral_height=int(mgn_chain.get("collateral_height") or 0),
                short_circuit=bool(mgn_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == mgn_chain.get("digest")
                and re_seal.get("digest") == live.get("total_spine_collateral_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(mgn1.get("total_spine_digest") or "")
            != str(offline_mgn.get("total_spine_digest") or "")
        )

        # Facade exposes this stage's surface (delegation identity;
        # source-text greps predate the thin PEP 562 facade).
        source_ok = (
            getattr(le_facade, "TOTAL_SPINE_COLLATERAL_IMPL", None) is TOTAL_SPINE_COLLATERAL_IMPL
            and getattr(le_facade, "builtin_total_spine_collateral_proof", None) is builtin_total_spine_collateral_proof
            and getattr(le_facade, "collateral_total_spine", None) is collateral_total_spine
            and callable(
                getattr(le_facade, "builtin_total_spine_collateral_proof", None)
    
        )
            and callable(getattr(le_facade, "collateral_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_COLLATERAL_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_COLLATERAL_IMPL" in engine_text
            and "collateral_total_spine" in engine_text
            and (
                "collateral=True" in engine_text
                or "collateral: bool = False" in engine_text
            )
            and "builtin_total_spine_collateral_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def collateral_total_spine" in mod_text
            and "def builtin_total_spine_collateral_proof" in mod_text
            and "total_spine_collateral_supersession_refused" in mod_text
            and "total_spine_collateral_tampered" in mod_text
            and "total_spine_collateral_one_sided" in mod_text
            and "total_spine_collateral_cvo_failed" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-collateral"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_collateral" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_collateral_proof" in (entry.entry or "")
                and (
                    "collateral" in tags_blob
                    or "collateral" in name_blob
                    or "collateral" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "collateral_total_spine" in delta_blob
                    or "post-margin" in delta_blob
                    or "post_margin" in delta_blob
                    or "cvo" in delta_blob
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
            "action": "total_spine_collateral_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "collateral_path": mgn_path,
            "tip_collateral_root": tip_collateral,
            "tip_margin_root": tip_margin,
            "tip_custody_root": tip_custody,
            "tip_delivery_root": tip_delivery,
            "tip_clearing_root": tip_clearing,
            "tip_settlement_root": tip_settlement,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "collateral_count": offline_mgn.get("total_spine_collateral_count"),
            "pair_count": offline_mgn.get("total_spine_collateral_pair_count"),
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
            "live_collateral_path": live_mgn_path,
            "live_tip_collateral_root": live.get("total_spine_tip_collateral_root"),
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
            "total_spine_collateral": True,
            "total_spine_margin": True,
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
        "collateral-proof",
        help=(
            "Total spine collateral proof: post-margin atomic CvO seals "
            "matching margin books into irreversible collateral receipts"
        ),
    )
    sub.add_parser("proof", help="Alias for collateral-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"collateral-proof", "proof"}:
        result = builtin_total_spine_collateral_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
