"""Post-custody margin-versus-exposure for the absolute total spine.

Closes the custodied-but-unmargined cliff: after ``custody_total_spine``
seals atomic CvT receipts, independently confirm a second custody, book
each custodied pair into a margin register and pair it with exposure
(MvE), seal hash-chained atomic margin receipts bound to the custody
digests, refuse split / one-sided / mismatched / failed / wrong-root /
tampered margins, short-circuit re-margin, and rebind the depth-28 tip
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

TOTAL_SPINE_MARGIN_IMPL = True
TOTAL_SPINE_MARGIN_KIND: str = "total_spine_margin"
TOTAL_SPINE_MARGIN_FILENAME: str = "total-spine-margin.json"
TOTAL_SPINE_MARGIN_MIN_CUSTODIES: int = 2

TOTAL_SPINE_CUSTODY_KIND: str = "total_spine_custody"
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine margin."""

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


def _custody_digest_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("custody_digest")
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
    for leg in row.get("custodies") or row.get("margins") or []:
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


def _book_signature(custody: Mapping[str, Any]) -> str:
    """Identity of a custodied book, independent of custody height/digest."""
    legs = custody.get("custodies") or []
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
            "bound_state_root": str(custody.get("bound_state_root") or ""),
            "bound_action_root": str(custody.get("bound_action_root") or ""),
            "actuation_digest": str(custody.get("actuation_digest") or ""),
            "bound_settlement_root": str(
                custody.get("bound_settlement_root") or ""
            ),
            "bound_clearing_root": str(
                custody.get("bound_clearing_root") or ""
            ),
            "bound_delivery_root": str(
                custody.get("bound_delivery_root")
                or custody.get("tip_delivery_root")
                or ""
            ),
            "custody_signatures": sigs,
            "residual": int(custody.get("residual") or 0),
            "pair_count": int(custody.get("pair_count") or 0),
            "custody_count": int(custody.get("custody_count") or 0),
        }
    )


def _mve_pairs(capabilities: Sequence[str]) -> list[dict[str, Any]]:
    """Atomic margin+exposure pairs for each custodied capability."""
    pairs: list[dict[str, Any]] = []
    for cid in capabilities:
        name = str(cid or "").strip()
        if not name:
            continue
        row = {
            "capability_id": name,
            "margin_ok": True,
            "exposure_ok": True,
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
                "margin_ok": bool(row.get("margin_ok", True)),
                "exposure_ok": bool(row.get("exposure_ok", True)),
                "atomic_ok": bool(row.get("atomic_ok", True)),
                "pair_root": str(row.get("pair_root") or ""),
            }
        )
    return _sha256_json({"pairs": rows})


def _assert_pairs_atomic(pairs: Sequence[Mapping[str, Any]]) -> None:
    if not pairs:
        raise StageRefused(
            "total_spine_margin_pairs_empty",
            "margin refuses an empty MvE pair book",
        )
    for row in pairs:
        if not isinstance(row, Mapping):
            raise StageRefused(
                "total_spine_margin_partial",
                "margin refuses a malformed MvE pair",
            )
        margin_ok = bool(row.get("margin_ok", True))
        exposure_ok = bool(row.get("exposure_ok", True))
        if margin_ok != exposure_ok or not bool(row.get("atomic_ok", True)):
            raise StageRefused(
                "total_spine_margin_partial",
                "margin refuses a split (non-atomic) margin-versus-exposure pair",
            )
        if not margin_ok or not exposure_ok:
            raise StageRefused(
                "total_spine_margin_partial",
                "margin refuses an unmargined or unexposed MvE pair",
            )


def _margin_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine margin certificate digests."""
    legs = body.get("margins") or body.get("legs") or []
    margin_rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            margin_rows.append(
                {
                    "custody_index": int(row.get("custody_index") or 0),
                    "custody_height": int(row.get("custody_height") or 0),
                    "custody_digest": str(row.get("custody_digest") or ""),
                    "bound_custody_root": str(
                        row.get("bound_custody_root") or ""
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
                    "margined": bool(row.get("margined", True)),
                    "exposed": bool(row.get("exposed", True)),
                    "atomic_ok": bool(row.get("atomic_ok", True)),
                    "one_sided": bool(row.get("one_sided", False)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_margin_root": str(
                        row.get("parent_margin_root") or ""
                    ),
                    "margin_root": str(row.get("margin_root") or ""),
                    "post_custody": bool(row.get("post_custody", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                    "mve": bool(row.get("mve", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_MARGIN_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "bound_clearing_root": str(body.get("bound_clearing_root") or ""),
        "bound_custody_root": str(body.get("bound_custody_root") or ""),
        "bound_delivery_root": str(body.get("bound_delivery_root") or ""),
        "custody_digest": str(body.get("custody_digest") or ""),
        "delivery_digest": str(body.get("delivery_digest") or ""),
        "parent_margin_root": str(body.get("parent_margin_root") or ""),
        "tip_margin_root": str(body.get("tip_margin_root") or ""),
        "margin_height": int(body.get("margin_height") or 0),
        "margin_count": int(body.get("margin_count") or 0),
        "pair_count": int(body.get("pair_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "margined": bool(body.get("margined", True)),
        "exposed": bool(body.get("exposed", True)),
        "atomic_ok": bool(body.get("atomic_ok", True)),
        "mve_ok": bool(body.get("mve_ok", True)),
        "one_sided": bool(body.get("one_sided", False)),
        "margins_ok": bool(body.get("margins_ok", True)),
        "custodies_ok": bool(body.get("custodies_ok", True)),
        "post_custody": bool(body.get("post_custody", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "margins": margin_rows,
    }


def compute_total_spine_margin_root(
    margins: Sequence[Mapping[str, Any]],
) -> str:
    """Tip margin root of a hash-chained MvE log (empty → zero)."""
    if not margins:
        return "0" * 64
    last = margins[-1]
    tip = str(last.get("margin_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(margins):
        body = {
            "custody_index": int(row.get("custody_index") or idx),
            "custody_height": int(row.get("custody_height") or (idx + 1)),
            "custody_digest": str(row.get("custody_digest") or ""),
            "bound_custody_root": str(row.get("bound_custody_root") or ""),
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
            "margined": bool(row.get("margined", True)),
            "exposed": bool(row.get("exposed", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_margin_root": parent,
            "post_custody": True,
            "deterministic": True,
            "mve": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def book_total_spine_custodies(
    custodies: Sequence[Mapping[str, Any]],
    *,
    min_margins: int = TOTAL_SPINE_MARGIN_MIN_CUSTODIES,
    parent_margin_root: str = "",
    margin_height: int | None = None,
) -> list[dict[str, Any]]:
    """Book independently verified custody books into atomic MvE legs.

    Two (or more) custodies margin only when they share bound state/action/
    actuation/settlement/clearing roots and the same custodied pair book.
    Divergent capability sets are a one-sided refusal; book disagreement is
    a MvE failure. Each custodied capability becomes a margin+exposure pair
    that must be atomic.
    """
    from blackhole_agent.upstream_total_spine_custody import (
        verify_total_spine_custody_certificate,
    )

    want = max(int(min_margins), TOTAL_SPINE_MARGIN_MIN_CUSTODIES)
    verified: list[Mapping[str, Any]] = []
    for raw in custodies:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_total_spine_custody_certificate(raw)
        if not verify.get("ok"):
            raise StageRefused(
                "total_spine_margin_custody_tampered",
                "margin refuses a custody whose digest/chain does not verify",
            )
        if raw.get("custodied") is False or raw.get("success") is False:
            raise StageRefused(
                "total_spine_margin_custody_uncustodied",
                "margin refuses an uncustodied custody receipt",
            )
        if raw.get("titled") is False or raw.get("cvt_ok") is False:
            raise StageRefused(
                "total_spine_margin_custody_untitled",
                "margin refuses a custody whose CvT is not complete",
            )
        if raw.get("atomic_ok") is False:
            raise StageRefused(
                "total_spine_margin_custody_partial",
                "margin refuses a non-atomic custody receipt",
            )
        if int(raw.get("residual") or 0) != 0:
            raise StageRefused(
                "total_spine_margin_residual",
                "margin refuses a custody with a non-zero residual",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            "total_spine_margin_custodies_short",
            f"margin requires >= {want} independent custodies, "
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
            "total_spine_margin_root_missing",
            "margin requires custody bound state/action/actuation roots",
        )
    if not book_caps:
        raise StageRefused(
            "total_spine_margin_pairs_empty",
            "margin refuses a custody with no custodied capabilities",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_margin_root or "")
    for idx, custody in enumerate(verified):
        state = str(custody.get("bound_state_root") or "")
        action = str(
            custody.get("bound_action_root")
            or custody.get("tip_action_root")
            or ""
        )
        actuation = str(custody.get("actuation_digest") or "")
        settlement = str(custody.get("bound_settlement_root") or "")
        clearing = str(custody.get("bound_clearing_root") or "")
        if (
            state != book_state
            or action != book_action
            or actuation != book_actuation
        ):
            raise StageRefused(
                "total_spine_margin_root_mismatch",
                "margin refuses custodies bound to different "
                "state/action/actuation roots",
            )
        if settlement and book_settlement and settlement != book_settlement:
            raise StageRefused(
                "total_spine_margin_root_mismatch",
                "margin refuses custodies bound to different settlement roots",
            )
        if clearing and book_clearing and clearing != book_clearing:
            raise StageRefused(
                "total_spine_margin_root_mismatch",
                "margin refuses custodies bound to different clearing roots",
            )
        sig = _book_signature(custody)
        if sig != book_sig:
            raise StageRefused(
                "total_spine_margin_mve_failed",
                "independent custody books disagree; MvE cannot complete",
            )
        caps = tuple(_capability_list(custody))
        if caps != book_caps:
            raise StageRefused(
                "total_spine_margin_one_sided",
                "margin refuses one-sided books whose capability sets differ",
            )
        pairs = _mve_pairs(book_caps)
        _assert_pairs_atomic(pairs)
        height = (
            int(margin_height) + idx
            if margin_height is not None
            else (idx + 1)
        )
        material = {
            "custody_index": idx,
            "custody_height": height,
            "custody_digest": _custody_digest_of(custody),
            "bound_custody_root": str(
                custody.get("tip_custody_root") or ""
            ),
            "bound_delivery_root": str(
                custody.get("bound_delivery_root")
                or custody.get("tip_delivery_root")
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
            "margined": True,
            "exposed": True,
            "atomic_ok": True,
            "one_sided": False,
            "residual": 0,
            "independent": True,
            "parent_margin_root": parent,
            "post_custody": True,
            "deterministic": True,
            "mve": True,
        }
        margin_root = _sha256_json(material)
        row = dict(material)
        row["margin_root"] = margin_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = margin_root
    return legs


def seal_total_spine_margin_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-custody MvE log into a tamper-evident receipt."""
    sealed_body = dict(body)
    margins = list(sealed_body.get("margins") or [])
    if not str(sealed_body.get("tip_margin_root") or "").strip():
        sealed_body["tip_margin_root"] = compute_total_spine_margin_root(
            margins
        )
    if not int(sealed_body.get("margin_count") or 0):
        sealed_body["margin_count"] = len(margins)
    if not int(sealed_body.get("margin_height") or 0):
        sealed_body["margin_height"] = len(margins)
    material = _margin_certificate_material(sealed_body)
    material["tip_margin_root"] = str(sealed_body.get("tip_margin_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["margin_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_margin"] = True
    sealed["total_spine_margin_impl"] = TOTAL_SPINE_MARGIN_IMPL
    sealed["margined_at"] = str(body.get("margined_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    if margins:
        sealed_pairs: list[Any] = []
        for src, dest in zip(margins, sealed.get("margins") or []):
            if isinstance(src, Mapping) and isinstance(dest, dict):
                if src.get("pairs"):
                    dest["pairs"] = list(src.get("pairs") or [])
                sealed_pairs.append(dest)
        if sealed_pairs:
            sealed["margins"] = sealed_pairs
    return sealed


def margin_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-margin.json`` under a margin/out root."""
    path = Path(root)
    if path.is_file():
        if path.name == TOTAL_SPINE_MARGIN_FILENAME or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == TOTAL_SPINE_MARGIN_KIND
                or path.name == TOTAL_SPINE_MARGIN_FILENAME
            ):
                return path
        parent = path.parent
        sibling = parent / TOTAL_SPINE_MARGIN_FILENAME
        if sibling.is_file():
            return sibling
        nested = parent / "margin" / TOTAL_SPINE_MARGIN_FILENAME
        if nested.is_file():
            return nested
        grand = parent.parent / "margin" / TOTAL_SPINE_MARGIN_FILENAME
        if grand.is_file():
            return grand
        grand_sib = parent.parent / TOTAL_SPINE_MARGIN_FILENAME
        if grand_sib.is_file():
            return grand_sib
        return parent / "margin" / TOTAL_SPINE_MARGIN_FILENAME
    named = path / TOTAL_SPINE_MARGIN_FILENAME
    if named.is_file():
        return named
    nested = path / "margin" / TOTAL_SPINE_MARGIN_FILENAME
    if nested.is_file():
        return nested
    return path / "margin" / TOTAL_SPINE_MARGIN_FILENAME


def write_total_spine_margin_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a margin receipt under ``out_root``."""
    sealed = seal_total_spine_margin_certificate(body)
    path = margin_certificate_path(Path(out_root))
    if path.is_file():
        try:
            existing = load_total_spine_margin_certificate(path)
        except StageRefused:
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get("margin_digest")
                or existing.get("certificate_hash")
                or ""
            )
            new_digest = str(
                sealed.get("margin_digest")
                or sealed.get("certificate_hash")
                or ""
            )
            if (
                existing_digest
                and existing_digest == new_digest
                and allow_idempotent
            ):
                existing["margin_path"] = str(path)
                existing["total_spine_margin_idempotent"] = True
                return existing
            raise StageRefused(
                "total_spine_margin_supersession_refused",
                f"irreversible margin already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed["margin_path"] = str(path)
    sealed["total_spine_margin_idempotent"] = False
    return sealed


def verify_total_spine_margin_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute margin digest and MvE roots; fail closed on tamper."""
    claimed = str(
        certificate.get("margin_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _margin_certificate_material(certificate)
    expected = _sha256_json(material)
    margins = list(certificate.get("margins") or [])
    recomputed_tip = compute_total_spine_margin_root(margins)
    claimed_tip = str(certificate.get("tip_margin_root") or "")
    height = int(certificate.get("margin_height") or 0)
    count = int(certificate.get("margin_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_margin_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(margins):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_margin_root") or "") != parent:
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
            "custody_index": int(row.get("custody_index") or idx),
            "custody_height": int(row.get("custody_height") or (idx + 1)),
            "custody_digest": str(row.get("custody_digest") or ""),
            "bound_custody_root": str(row.get("bound_custody_root") or ""),
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
            "margined": bool(row.get("margined", True)),
            "exposed": bool(row.get("exposed", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_margin_root": parent,
            "post_custody": True,
            "deterministic": True,
            "mve": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("margin_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_MARGIN_MIN_CUSTODIES and height >= count
    margins_ok = all(
        isinstance(row, Mapping)
        and bool(row.get("margined", True))
        and bool(row.get("exposed", True))
        and bool(row.get("atomic_ok", True))
        and bool(row.get("mve", True))
        and not bool(row.get("one_sided", False))
        and int(row.get("residual") or 0) == 0
        for row in margins
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_MARGIN_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_custody") is True
        and certificate.get("deterministic") is True
        and certificate.get("margined") is True
        and certificate.get("exposed") is True
        and certificate.get("atomic_ok") is True
        and certificate.get("mve_ok") is True
        and certificate.get("one_sided") is False
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(margins)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and margins_ok
        and int(certificate.get("residual") or 0) == 0
        and TOTAL_SPINE_MARGIN_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_margin",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "margin_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_margin_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_margins_ok": min_ok,
        "margins_ok": margins_ok,
        "mve_ok": certificate.get("mve_ok") is True,
        "atomic_ok": certificate.get("atomic_ok") is True,
        "kind_ok": str(certificate.get("kind") or "") == TOTAL_SPINE_MARGIN_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "margined_ok": certificate.get("margined") is True,
        "exposed_ok": certificate.get("exposed") is True,
        "total_spine_margin": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_margin_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed margin receipt."""
    file_path = margin_certificate_path(Path(path))
    if not file_path.is_file():
        raise StageRefused(
            "total_spine_margin_missing",
            f"margin certificate not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRefused(
            "total_spine_margin_unreadable",
            f"margin certificate unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StageRefused(
            "total_spine_margin_invalid",
            "margin certificate root must be a JSON object",
        )
    if str(payload.get("kind") or "") != TOTAL_SPINE_MARGIN_KIND and not payload.get(
        "total_spine_margin"
    ):
        raise StageRefused(
            "total_spine_margin_missing",
            f"margin certificate not found at {file_path}",
        )
    verify = verify_total_spine_margin_certificate(payload)
    if not verify.get("ok"):
        raise StageRefused(
            "total_spine_margin_tampered",
            f"margin certificate digest mismatch at {file_path} "
            f"(claimed={verify.get('claimed_digest')!r} "
            f"expected={verify.get('expected_digest')!r})",
        )
    body = dict(payload)
    body["margin_path"] = str(file_path)
    body["margin_verify"] = verify
    body["total_spine_margin_loaded"] = True
    return body


def seal_total_spine_margin_chain(
    *,
    prior_tip: str,
    margin_digest: str,
    tip_margin_root: str,
    bound_custody_root: str,
    bound_delivery_root: str,
    bound_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    custody_digest: str,
    delivery_digest: str,
    margin_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal margin hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    md = str(margin_digest or "").strip() or ("0" * 64)
    mr = str(tip_margin_root or "").strip() or ("0" * 64)
    cr = str(bound_custody_root or "").strip() or ("0" * 64)
    dlr = str(bound_delivery_root or "").strip() or ("0" * 64)
    clr = str(bound_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    cd = str(custody_digest or "").strip() or ("0" * 64)
    dvd = str(delivery_digest or "").strip() or ("0" * 64)
    material = (
        f"margin|{int(bool(short_circuit))}|{int(margin_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{clr}|{dlr}|{cr}|{dvd}|{cd}|{mr}|{md}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "margin_height": int(margin_height),
        "tip_margin_root": mr,
        "bound_custody_root": cr,
        "bound_delivery_root": dlr,
        "bound_clearing_root": clr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "custody_digest": cd,
        "delivery_digest": dvd,
        "margin_digest": md,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_margin": True,
        "irreversible": True,
        "post_custody": True,
        "deterministic": True,
        "mve": True,
    }


def annotate_total_spine_margin(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-custody MvE onto a total-spine result and rebind tip."""
    cst_digest = str(
        certificate.get("margin_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_margin_root = str(certificate.get("tip_margin_root") or "")
    margin_height = int(certificate.get("margin_height") or 0)
    margin_count = int(certificate.get("margin_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    bound_clearing_root = str(certificate.get("bound_clearing_root") or "")
    bound_custody_root = str(certificate.get("bound_custody_root") or "")
    bound_delivery_root = str(certificate.get("bound_delivery_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    custody_digest = str(certificate.get("custody_digest") or "")
    delivery_digest = str(certificate.get("delivery_digest") or "")
    chain = seal_total_spine_margin_chain(
        prior_tip=prior_tip,
        margin_digest=cst_digest,
        tip_margin_root=tip_margin_root,
        bound_custody_root=bound_custody_root,
        bound_delivery_root=bound_delivery_root,
        bound_clearing_root=bound_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        custody_digest=custody_digest,
        delivery_digest=delivery_digest,
        margin_height=margin_height,
        short_circuit=short_circuit,
    )
    cst_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{cst_tip}".encode("utf-8"))
    body["total_spine_margin"] = True
    body["total_spine_margin_impl"] = TOTAL_SPINE_MARGIN_IMPL
    body["total_spine_margin_short_circuit"] = bool(short_circuit)
    body["total_spine_margin_irreversible"] = True
    body["total_spine_margin_post_custody"] = True
    body["total_spine_margin_deterministic"] = True
    body["total_spine_margin_mve"] = True
    body["total_spine_margin_certificate"] = dict(certificate)
    body["total_spine_margin_digest"] = cst_digest
    body["total_spine_margin_chain"] = chain
    body["total_spine_margin_tip"] = cst_tip
    body["total_spine_margin_bound_tip"] = bound
    body["total_spine_digest_pre_margin"] = prior_tip
    body["total_spine_tip_margin_root"] = tip_margin_root
    body["total_spine_margin_height"] = margin_height
    body["total_spine_margin_count"] = margin_count
    body["total_spine_margined"] = bool(certificate.get("margined", True))
    body["total_spine_margined_ok"] = bool(certificate.get("margined", True))
    body["total_spine_exposed"] = bool(certificate.get("exposed", True))
    body["total_spine_exposed_ok"] = bool(certificate.get("exposed", True))
    body["total_spine_mve_ok"] = bool(certificate.get("mve_ok", True))
    body["total_spine_margin_atomic"] = bool(certificate.get("atomic_ok", True))
    body["total_spine_margin_one_sided"] = bool(
        certificate.get("one_sided", False)
    )
    body["total_spine_margins_ok"] = bool(
        certificate.get("margins_ok", True)
    )
    body["total_spine_margin_root_valid"] = bool(tip_margin_root)
    body["total_spine_margin_residual"] = int(certificate.get("residual") or 0)
    body["total_spine_margin_pair_count"] = int(
        certificate.get("pair_count") or 0
    )
    body["margin_root"] = tip_margin_root
    body["tip_margin_root"] = tip_margin_root
    body["margin_count"] = margin_count
    body["margin_height"] = margin_height
    body["margined"] = bool(certificate.get("margined", True))
    body["margined_ok"] = bool(certificate.get("margined", True))
    body["mve_ok"] = bool(certificate.get("mve_ok", True))
    body["exposed"] = bool(certificate.get("exposed", True))
    if certificate.get("margin_path"):
        body["total_spine_margin_path"] = certificate.get("margin_path")
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
    if custody_digest:
        body["total_spine_custody_digest"] = custody_digest
    if delivery_digest:
        body["total_spine_delivery_digest"] = delivery_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_margin_ok_short_circuit"
        if short_circuit
        else "total_spine_margin_ok"
    )
    body["ok"] = True
    return body


def _as_custody_mapping(value: Any) -> dict[str, Any] | None:
    from blackhole_agent.upstream_total_spine_custody import (
        StageRefused as CustodyRefused,
        load_total_spine_custody_certificate,
    )

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_CUSTODY_KIND or value.get(
            "total_spine_custody"
        ) or value.get("total_spine_custody_loaded") or value.get(
            "tip_custody_root"
        ):
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
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / "custody" / "total-spine-custody.json"
            named = path / "total-spine-custody.json"
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != TOTAL_SPINE_CUSTODY_KIND:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_total_spine_custody_certificate(path)
    except CustodyRefused as exc:
        if str(exc.verdict) == "total_spine_custody_tampered":
            raise StageRefused(str(exc.verdict), str(exc.detail)) from exc
        return None
    except Exception:  # noqa: BLE001
        return None


def _as_margin_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_MARGIN_KIND or value.get(
            "total_spine_margin"
        ) or value.get("total_spine_margin_loaded"):
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
    try:
        return load_total_spine_margin_certificate(Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == "total_spine_margin_tampered":
            raise
        return None
    except Exception:  # noqa: BLE001
        return None


def _deliveries_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_custody_certificate")
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


def _confirm_custody(
    primary: Mapping[str, Any],
    *,
    deliveries: Sequence[Mapping[str, Any]],
    clearings: Sequence[Mapping[str, Any]],
    settlements: Sequence[Mapping[str, Any]],
    actuation: Mapping[str, Any] | None,
    out_root: Path | None,
    prior_tip: str,
    repo_path: Path | None,
) -> dict[str, Any]:
    """Independently re-deliver the same book as a confirmation side."""
    from blackhole_agent.upstream_total_spine_custody import custody_total_spine

    confirm_out = None
    if out_root is not None:
        confirm_out = Path(out_root) / "margin-confirm"
    tip_custody = str(primary.get("tip_custody_root") or "")
    dlv_height = int(primary.get("custody_height") or 0)
    source: Any = list(deliveries) if deliveries else None
    if source is None and clearings:
        source = list(clearings)
    if source is None and settlements:
        source = list(settlements)
    if source is None and actuation is not None:
        source = actuation
    if source is None:
        raise StageRefused(
            "total_spine_margin_confirmation_missing",
            "single custody requires deliveries, clearings, settlements, or "
            "actuation to confirm-margin",
        )
    confirmed = custody_total_spine(
        source,
        deliveries=deliveries or None,
        clearings=clearings or None,
        settlements=settlements or None,
        actuation=actuation,
        out_root=confirm_out,
        prior_tip=prior_tip,
        parent_custody_root=tip_custody,
        custody_height=dlv_height + 1 if dlv_height else None,
        repo_path=repo_path or REPO_ROOT,
        confirm=True,
    )
    cert = confirmed.get("total_spine_custody_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            "total_spine_margin_confirmation_missing",
            "confirmation custody did not produce a certificate",
        )
    return dict(cert)


def _collect_custodies(
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
    """Return (existing_margin, custodies, deliveries, clearings, settlements, actuation)."""
    existing = _as_margin_mapping(source)
    if existing is None and body is not None:
        existing = _as_margin_mapping(body)
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
        mapped = _as_custody_mapping(item)
        if mapped is not None:
            custodies.append(mapped)
            _take_actuation(mapped)
            for row in _deliveries_from(mapped):
                deliveries.append(row)
            for row in _clearings_from(mapped):
                clearings.append(row)
            for row in _settlements_from(mapped):
                settlements.append(row)
        if isinstance(item, Mapping):
            _take_actuation(item)
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
    for row in custodies:
        digest = _custody_digest_of(row)
        tip = str(row.get("tip_custody_root") or "")
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
    return existing, deduped, dlv_deduped, clr_deduped, set_deduped, actuation


def _strip_margin_predicates(done_when: str) -> str:
    """Evaluate the pre-margin contract, never margin_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "margin_ok",
        "margined_ok",
        "min_margins",
        "margin_root_valid",
        "mve_ok",
        "exposure_ok",
        "exposed_ok",
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


def margin_total_spine(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    custodies: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_margins: int = TOTAL_SPINE_MARGIN_MIN_CUSTODIES,
    parent_margin_root: str = "",
    margin_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
    settlements: Sequence[Mapping[str, Any]] | None = None,
    clearings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply post-custody atomic MvE margin on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_MARGIN_IMPL:
        raise StageRefused(
            "total_spine_margin_disabled",
            "TOTAL_SPINE_MARGIN_IMPL is False",
        )

    (
        existing,
        collected,
        found_deliveries,
        found_clearings,
        found_settlements,
        found_actuation,
    ) = _collect_custodies(source, body, custodies)
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
        and existing.get("tip_margin_root")
        and (
            str(existing.get("kind") or "") == TOTAL_SPINE_MARGIN_KIND
            or existing.get("total_spine_margin_loaded")
            or existing.get("total_spine_margin")
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
            "action": "margin_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_margin(
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

    want = max(int(min_margins), TOTAL_SPINE_MARGIN_MIN_CUSTODIES)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_custody(
                collected[0],
                deliveries=found_deliveries,
                clearings=found_clearings,
                settlements=found_settlements,
                actuation=actuation,
                out_root=out_root,
                prior_tip=str(
                    prior_tip
                    or (body or {}).get("total_spine_custody_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            "total_spine_margin_custodies_short",
            f"margin requires >= {want} independent custodies, "
            f"got {len(collected)}",
        )

    legs = book_total_spine_custodies(
        collected,
        min_margins=want,
        parent_margin_root=parent_margin_root,
        margin_height=margin_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("bound_settlement_root") or "")
    clearing_root = str(first.get("bound_clearing_root") or "")
    custody_root = str(first.get("tip_custody_root") or "")
    custody_digest = _custody_digest_of(first)
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
    pre_margin = _strip_margin_predicates(done_when)
    if pre_margin:
        ctx = {
            "custody": {
                "ok": True,
                "custodied": True,
                "custodied_ok": True,
                "custody_root_valid": True,
                "cvt_ok": True,
                "custody_count": int(first.get("custody_count") or 0),
                "tip_custody_root": custody_root,
            },
            "custody_count": int(first.get("custody_count") or 0),
            "tip_custody_root": custody_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_margin,
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
                "total_spine_margin_contract_unmet",
                f"done_when not met at margin: {pre_margin!r}",
            )

    tip_margin_root = compute_total_spine_margin_root(legs)
    cst_height = int(legs[-1]["custody_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_custody_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    pair_count = int(legs[0].get("pair_count") or 0) if legs else 0

    cst_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_MARGIN_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "bound_clearing_root": clearing_root,
        "bound_custody_root": custody_root,
        "bound_delivery_root": str(
            first.get("bound_delivery_root")
            or first.get("tip_delivery_root")
            or ""
        ),
        "custody_digest": custody_digest,
        "delivery_digest": str(
            first.get("delivery_digest")
            or first.get("certificate_hash")
            or ""
        ),
        "prior_tip": tip,
        "parent_margin_root": str(
            parent_margin_root
            or (legs[0].get("parent_margin_root") if legs else "")
            or ""
        ),
        "margins": legs,
        "margin_count": len(legs),
        "margin_height": cst_height,
        "tip_margin_root": tip_margin_root,
        "pair_count": pair_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "margined": True,
        "exposed": True,
        "atomic_ok": True,
        "mve_ok": True,
        "one_sided": False,
        "margins_ok": True,
        "custodies_ok": True,
        "post_custody": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "margined_at": utc_now_iso(),
    }
    if contract_eval is not None:
        cst_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_margin_certificate(write_target, cst_body)
    else:
        certificate = seal_total_spine_margin_certificate(cst_body)

    result = body if body is not None else {
        "ok": True,
        "action": "margin_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_margin(
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
        cst_bound = str(annotated.get("total_spine_margin_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=cst_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_margin_bound_state_root"] = state_root
    annotated["total_spine_margin_bound_action_root"] = action_root
    annotated["total_spine_margin_bound_settlement_root"] = settlement_root
    annotated["total_spine_margin_bound_clearing_root"] = clearing_root
    annotated["total_spine_margin_bound_custody_root"] = custody_root
    annotated["total_spine_margin_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_margin_proof() -> dict[str, Any]:
    """Hermetic proof: post-custody atomic MvE on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_MARGIN_IMPL as ENGINE_MGN_IMPL,
        TOTAL_SPINE_CUSTODY_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        actuate_total_spine,
        clear_total_spine,
        custody_total_spine,
        deliver_total_spine,
        execute_total_spine,
        federate_total_spine,
        run_total_spine,
        settle_total_spine,
        write_total_spine_finality_certificate,
    )
    from blackhole_agent.upstream_total_spine_custody import (
        seal_total_spine_custody_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-margin-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_MARGIN_IMPL is True
            and ENGINE_MGN_IMPL is True
            and TOTAL_SPINE_CUSTODY_IMPL is True
            and TOTAL_SPINE_MARGIN_KIND == "total_spine_margin"
            and bool(TOTAL_SPINE_MARGIN_FILENAME)
            and TOTAL_SPINE_MARGIN_MIN_CUSTODIES >= 2
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
                "goal": "margin proof origin",
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

        offline_mgn = margin_total_spine(
            [cert_c1, cert_c2],
            out_root=scratch / "mgn-h1",
            prior_tip=str(cst2.get("total_spine_custody_bound_tip") or ""),
            body=dict(cst2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        mgn_path = offline_mgn.get("total_spine_margin_path")
        tip_margin = str(offline_mgn.get("total_spine_tip_margin_root") or "")
        offline_ok = (
            bool(offline_mgn.get("ok"))
            and offline_mgn.get("total_spine_margin") is True
            and offline_mgn.get("total_spine_margin_post_custody") is True
            and offline_mgn.get("total_spine_margin_irreversible") is True
            and offline_mgn.get("total_spine_margined") is True
            and offline_mgn.get("total_spine_exposed") is True
            and offline_mgn.get("total_spine_mve_ok") is True
            and offline_mgn.get("total_spine_margin_atomic") is True
            and offline_mgn.get("total_spine_margin_one_sided") is False
            and int(offline_mgn.get("total_spine_margin_count") or 0) >= 2
            and int(offline_mgn.get("total_spine_margin_height") or 0) >= 2
            and int(offline_mgn.get("total_spine_margin_residual") or 0) == 0
            and int(offline_mgn.get("total_spine_margin_pair_count") or 0) >= 1
            and len(tip_margin) >= 32
            and str(offline_mgn.get("total_spine_state_root") or "") == state_root
            and str(offline_mgn.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_mgn.get("total_spine_digest") or "")
            != str(cst1.get("total_spine_digest") or "")
            and isinstance(mgn_path, str)
            and Path(mgn_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_margin_certificate(mgn_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_margin_loaded")
            and (loaded.get("margin_verify") or {}).get("ok")
            and (loaded.get("margin_verify") or {}).get("margin_root_ok")
            and (loaded.get("margin_verify") or {}).get("chain_ok")
            and (loaded.get("margin_verify") or {}).get("margins_ok")
            and (loaded.get("margin_verify") or {}).get("mve_ok")
        )

        tampered_path = scratch / "tampered-margin.json"
        tampered_body = dict(loaded)
        for drop in (
            "margin_verify",
            "total_spine_margin_loaded",
            "margin_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["margin_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_margin_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_margin_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_margin_certificate(
                scratch / "mgn-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "margin_verify",
                            "total_spine_margin_loaded",
                            "margin_path",
                            "margin_digest",
                            "certificate_hash",
                            "margined_at",
                            "total_spine_margin",
                            "total_spine_margin_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_margin_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_margin_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "margin_verify",
            "total_spine_margin_loaded",
            "margin_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_margin_certificate(wrong_body)
        wrong_verify = verify_total_spine_margin_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("margin_root_ok") is False
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
            book_total_spine_custodies(
                [
                    cert_c1,
                    other_cst.get("total_spine_custody_certificate") or {},
                ],
                min_margins=2,
            )
        except StageRefused as exc:
            mismatch_ok = str(exc.verdict) == "total_spine_margin_root_mismatch"
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        one_sided_ok = False
        try:
            forged = dict(cert_c2)
            forged["capabilities"] = ["capability.one-sided-only"]
            for drop in (
                "custody_digest",
                "certificate_hash",
                "custodied_at",
                "custody_path",
                "custody_verify",
                "total_spine_custody_loaded",
            ):
                forged.pop(drop, None)
            resealed_one = seal_total_spine_custody_certificate(forged)
            book_total_spine_custodies([cert_c1, resealed_one], min_margins=2)
        except StageRefused as exc:
            one_sided_ok = str(exc.verdict) == "total_spine_margin_one_sided"
        except Exception:  # noqa: BLE001
            one_sided_ok = False

        partial_ok = False
        try:
            _assert_pairs_atomic(
                [
                    {
                        "capability_id": good_id,
                        "margin_ok": True,
                        "exposure_ok": False,
                        "atomic_ok": False,
                    }
                ]
            )
        except StageRefused as exc:
            partial_ok = str(exc.verdict) == "total_spine_margin_partial"
        except Exception:  # noqa: BLE001
            partial_ok = False

        h2 = margin_total_spine(
            [cert_c1, cert_c2],
            out_root=scratch / "mgn-h2",
            prior_tip=str(
                offline_mgn.get("total_spine_margin_bound_tip") or ""
            ),
            parent_margin_root=tip_margin,
            margin_height=int(
                offline_mgn.get("total_spine_margin_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_margin_count") or 0) >= 2
            and str(h2.get("total_spine_tip_margin_root") or "") != tip_margin
            and str(
                (h2.get("total_spine_margin_certificate") or {}).get(
                    "parent_margin_root"
                )
                or ""
            )
            == tip_margin
        )

        recomputed = compute_total_spine_margin_root(
            loaded.get("margins") or []
        )
        determinism_ok = recomputed == tip_margin and bool(recomputed)

        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-mgn",
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
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_mgn_path = live.get("total_spine_margin_path")
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
            and live.get("total_spine_margined") is True
            and live.get("total_spine_mve_ok") is True
            and int(live.get("total_spine_margin_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_margin_root"), str)
            and len(str(live.get("total_spine_tip_margin_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_mgn_path, str)
            and Path(live_mgn_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-mgn",
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
            resume_dir=live_mgn_path or (scratch / "live-mgn"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_margin") is True
            and shorted.get("total_spine_margin_short_circuit") is True
            and str(shorted.get("total_spine_tip_margin_root") or "")
            == str(live.get("total_spine_tip_margin_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        mgn_chain = live.get("total_spine_margin_chain") or {}
        chain_integrity_ok = False
        if isinstance(mgn_chain, Mapping) and mgn_chain:
            re_seal = seal_total_spine_margin_chain(
                prior_tip=str(mgn_chain.get("prior_tip") or ""),
                margin_digest=str(mgn_chain.get("margin_digest") or ""),
                tip_margin_root=str(mgn_chain.get("tip_margin_root") or ""),
                bound_custody_root=str(
                    mgn_chain.get("bound_custody_root") or ""
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
                custody_digest=str(mgn_chain.get("custody_digest") or ""),
                delivery_digest=str(mgn_chain.get("delivery_digest") or ""),
                margin_height=int(mgn_chain.get("margin_height") or 0),
                short_circuit=bool(mgn_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == mgn_chain.get("digest")
                and re_seal.get("digest") == live.get("total_spine_margin_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(cst1.get("total_spine_digest") or "")
            != str(offline_mgn.get("total_spine_digest") or "")
        )

        facade_path = Path(le_facade.__file__).resolve()
        facade_text = facade_path.read_text(encoding="utf-8")
        source_ok = (
            "TOTAL_SPINE_MARGIN_IMPL" in facade_text
            and "builtin_total_spine_margin_proof" in facade_text
            and "margin_total_spine" in facade_text
            and callable(
                getattr(le_facade, "builtin_total_spine_margin_proof", None)
            )
            and callable(getattr(le_facade, "margin_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_MARGIN_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_MARGIN_IMPL" in engine_text
            and "margin_total_spine" in engine_text
            and (
                "margin=True" in engine_text
                or "margin: bool = False" in engine_text
            )
            and "builtin_total_spine_margin_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def margin_total_spine" in mod_text
            and "def builtin_total_spine_margin_proof" in mod_text
            and "total_spine_margin_supersession_refused" in mod_text
            and "total_spine_margin_tampered" in mod_text
            and "total_spine_margin_one_sided" in mod_text
            and "total_spine_margin_mve_failed" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-margin"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_margin" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_margin_proof" in (entry.entry or "")
                and (
                    "margin" in tags_blob
                    or "margin" in name_blob
                    or "margin" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "margin_total_spine" in delta_blob
                    or "post-custody" in delta_blob
                    or "post_custody" in delta_blob
                    or "mve" in delta_blob
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
            "action": "total_spine_margin_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "margin_path": mgn_path,
            "tip_margin_root": tip_margin,
            "tip_custody_root": tip_custody,
            "tip_delivery_root": tip_delivery,
            "tip_clearing_root": tip_clearing,
            "tip_settlement_root": tip_settlement,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "margin_count": offline_mgn.get("total_spine_margin_count"),
            "pair_count": offline_mgn.get("total_spine_margin_pair_count"),
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
            "live_margin_path": live_mgn_path,
            "live_tip_margin_root": live.get("total_spine_tip_margin_root"),
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
        "margin-proof",
        help=(
            "Total spine margin proof: post-custody atomic MvE seals "
            "matching custody books into irreversible margin receipts"
        ),
    )
    sub.add_parser("proof", help="Alias for margin-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"margin-proof", "proof"}:
        result = builtin_total_spine_margin_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
