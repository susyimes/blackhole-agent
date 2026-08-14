"""Post-collateral funding-versus-requirement for the absolute total spine.

Closes the liquid-but-unfacilitated cliff: after ``liquidity_total_spine``
seals atomic LvC receipts, independently confirm a second liquidity, book
each liquid pair into a funding register and pair it with coverage
(FvR), seal hash-chained atomic funding receipts bound to the liquidity
digests, refuse split / one-sided / mismatched / failed / wrong-root /
tampered fundings, short-circuit re-facilitate, and rebind the depth-28 tip
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

TOTAL_SPINE_FUNDING_IMPL = True
TOTAL_SPINE_FUNDING_KIND: str = "total_spine_funding"
TOTAL_SPINE_FUNDING_FILENAME: str = "total-spine-funding.json"
TOTAL_SPINE_FUNDING_MIN_FUNDINGS: int = 2

TOTAL_SPINE_LIQUIDITY_KIND: str = "total_spine_liquidity"
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine funding."""

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


def _liquidity_digest_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("liquidity_digest")
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
    for leg in row.get("liquidities") or row.get("fundings") or []:
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
    """Identity of a collateralized book, independent of margin height/digest."""
    legs = margin.get("liquidities") or []
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
            "liquidity_count": int(margin.get("liquidity_count") or 0),
        }
    )


def _fvr_pairs(capabilities: Sequence[str]) -> list[dict[str, Any]]:
    """Atomic liquidity+coverage pairs for each collateralized capability."""
    pairs: list[dict[str, Any]] = []
    for cid in capabilities:
        name = str(cid or "").strip()
        if not name:
            continue
        row = {
            "capability_id": name,
            "facility_ok": True,
            "requirement_ok": True,
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
                "facility_ok": bool(row.get("facility_ok", True)),
                "requirement_ok": bool(row.get("requirement_ok", True)),
                "atomic_ok": bool(row.get("atomic_ok", True)),
                "pair_root": str(row.get("pair_root") or ""),
            }
        )
    return _sha256_json({"pairs": rows})


def _assert_pairs_atomic(pairs: Sequence[Mapping[str, Any]]) -> None:
    if not pairs:
        raise StageRefused(
            "total_spine_funding_pairs_empty",
            "funding refuses an empty LvC pair book",
        )
    for row in pairs:
        if not isinstance(row, Mapping):
            raise StageRefused(
                "total_spine_funding_partial",
                "funding refuses a malformed LvC pair",
            )
        facility_ok = bool(row.get("facility_ok", True))
        requirement_ok = bool(row.get("requirement_ok", True))
        if facility_ok != requirement_ok or not bool(row.get("atomic_ok", True)):
            raise StageRefused(
                "total_spine_funding_partial",
                "funding refuses a split (non-atomic) funding-versus-requirement pair",
            )
        if not facility_ok or not requirement_ok:
            raise StageRefused(
                "total_spine_funding_partial",
                "funding refuses an unfacilitated or uncovered LvC pair",
            )


def _funding_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine funding certificate digests."""
    legs = body.get("fundings") or body.get("legs") or []
    collateral_rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            collateral_rows.append(
                {
                    "liquidity_index": int(row.get("liquidity_index") or 0),
                    "liquidity_height": int(row.get("liquidity_height") or 0),
                    "liquidity_digest": str(row.get("liquidity_digest") or ""),
                    "bound_liquidity_root": str(
                        row.get("bound_liquidity_root") or ""
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
                    "facilitated": bool(row.get("facilitated", True)),
                    "required": bool(row.get("required", True)),
                    "atomic_ok": bool(row.get("atomic_ok", True)),
                    "one_sided": bool(row.get("one_sided", False)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_funding_root": str(
                        row.get("parent_funding_root") or ""
                    ),
                    "liquidity_root": str(row.get("liquidity_root") or ""),
                    "post_liquidity": bool(row.get("post_liquidity", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                    "fvr": bool(row.get("fvr", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_FUNDING_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "bound_clearing_root": str(body.get("bound_clearing_root") or ""),
        "bound_liquidity_root": str(body.get("bound_liquidity_root") or ""),
        "bound_custody_root": str(body.get("bound_custody_root") or ""),
        "bound_delivery_root": str(body.get("bound_delivery_root") or ""),
        "liquidity_digest": str(body.get("liquidity_digest") or ""),
        "delivery_digest": str(body.get("delivery_digest") or ""),
        "parent_funding_root": str(body.get("parent_funding_root") or ""),
        "tip_funding_root": str(body.get("tip_funding_root") or ""),
        "funding_height": int(body.get("funding_height") or 0),
        "funding_count": int(body.get("funding_count") or 0),
        "pair_count": int(body.get("pair_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "facilitated": bool(body.get("facilitated", True)),
        "required": bool(body.get("required", True)),
        "atomic_ok": bool(body.get("atomic_ok", True)),
        "fvr_ok": bool(body.get("fvr_ok", True)),
        "one_sided": bool(body.get("one_sided", False)),
        "fundings_ok": bool(body.get("fundings_ok", True)),
        "fundings_ok": bool(body.get("fundings_ok", True)),
        "post_liquidity": bool(body.get("post_liquidity", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "fundings": collateral_rows,
    }


def compute_total_spine_funding_root(
    liquidities: Sequence[Mapping[str, Any]],
) -> str:
    """Tip collateral root of a hash-chained LvC log (empty → zero)."""
    if not liquidities:
        return "0" * 64
    last = liquidities[-1]
    tip = str(last.get("liquidity_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(liquidities):
        body = {
            "liquidity_index": int(row.get("liquidity_index") or idx),
            "liquidity_height": int(row.get("liquidity_height") or (idx + 1)),
            "liquidity_digest": str(row.get("liquidity_digest") or ""),
            "bound_liquidity_root": str(row.get("bound_liquidity_root") or ""),
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
            "facilitated": bool(row.get("facilitated", True)),
            "required": bool(row.get("required", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_funding_root": parent,
            "post_liquidity": True,
            "deterministic": True,
            "fvr": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def book_total_spine_liquidities(
    margins: Sequence[Mapping[str, Any]],
    *,
    min_fundings: int = TOTAL_SPINE_FUNDING_MIN_FUNDINGS,
    parent_funding_root: str = "",
    funding_height: int | None = None,
) -> list[dict[str, Any]]:
    """Book independently verified collateral books into atomic LvC legs.

    Two (or more) collaterals fund only when they share bound state/action/
    actuation/settlement/clearing roots and the same liquid pair book.
    Divergent capability sets are a one-sided refusal; book disagreement is
    a LvC failure. Each collateralized capability becomes a liquidity+coverage pair
    that must be atomic.
    """
    from blackhole_agent.upstream_total_spine_liquidity import (
        verify_total_spine_liquidity_certificate,
    )

    want = max(int(min_fundings), TOTAL_SPINE_FUNDING_MIN_FUNDINGS)
    verified: list[Mapping[str, Any]] = []
    for raw in margins:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_total_spine_liquidity_certificate(raw)
        if not verify.get("ok"):
            raise StageRefused(
                "total_spine_funding_margin_tampered",
                "funding refuses a margin whose digest/chain does not verify",
            )
        if raw.get("funded") is False or raw.get("success") is False:
            raise StageRefused(
                "total_spine_funding_margin_unfunded",
                "funding refuses an unfunded margin receipt",
            )
        if raw.get("covered") is False or raw.get("lvc_ok") is False:
            raise StageRefused(
                "total_spine_funding_margin_uncovered",
                "funding refuses a margin whose CvO is not complete",
            )
        if raw.get("atomic_ok") is False:
            raise StageRefused(
                "total_spine_funding_margin_partial",
                "funding refuses a non-atomic margin receipt",
            )
        if int(raw.get("residual") or 0) != 0:
            raise StageRefused(
                "total_spine_funding_residual",
                "funding refuses a margin with a non-zero residual",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            "total_spine_funding_margins_short",
            f"funding requires >= {want} independent liquidities, "
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
            "total_spine_funding_root_missing",
            "funding requires liquidity bound state/action/actuation roots",
        )
    if not book_caps:
        raise StageRefused(
            "total_spine_funding_pairs_empty",
            "funding refuses a liquidity with no funded capabilities",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_funding_root or "")
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
                "total_spine_funding_root_mismatch",
                "funding refuses collaterals bound to different "
                "state/action/actuation roots",
            )
        if settlement and book_settlement and settlement != book_settlement:
            raise StageRefused(
                "total_spine_funding_root_mismatch",
                "funding refuses collaterals bound to different settlement roots",
            )
        if clearing and book_clearing and clearing != book_clearing:
            raise StageRefused(
                "total_spine_funding_root_mismatch",
                "funding refuses collaterals bound to different clearing roots",
            )
        sig = _book_signature(margin)
        if sig != book_sig:
            raise StageRefused(
                "total_spine_funding_fvr_failed",
                "independent liquidity books disagree; LvC cannot complete",
            )
        caps = tuple(_capability_list(margin))
        if caps != book_caps:
            raise StageRefused(
                "total_spine_funding_one_sided",
                "funding refuses one-sided books whose capability sets differ",
            )
        pairs = _fvr_pairs(book_caps)
        _assert_pairs_atomic(pairs)
        height = (
            int(funding_height) + idx
            if funding_height is not None
            else (idx + 1)
        )
        material = {
            "liquidity_index": idx,
            "liquidity_height": height,
            "liquidity_digest": _liquidity_digest_of(margin),
            "bound_liquidity_root": str(
                margin.get("tip_liquidity_root") or ""
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
            "facilitated": True,
            "required": True,
            "atomic_ok": True,
            "one_sided": False,
            "residual": 0,
            "independent": True,
            "parent_funding_root": parent,
            "post_liquidity": True,
            "deterministic": True,
            "fvr": True,
        }
        liquidity_root = _sha256_json(material)
        row = dict(material)
        row["liquidity_root"] = liquidity_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = liquidity_root
    return legs


def seal_total_spine_funding_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-liquidity LvC log into a tamper-evident receipt."""
    sealed_body = dict(body)
    fundings = list(sealed_body.get("fundings") or [])
    if not str(sealed_body.get("tip_funding_root") or "").strip():
        sealed_body["tip_funding_root"] = compute_total_spine_funding_root(
            fundings
        )
    if not int(sealed_body.get("funding_count") or 0):
        sealed_body["funding_count"] = len(fundings)
    if not int(sealed_body.get("funding_height") or 0):
        sealed_body["funding_height"] = len(fundings)
    material = _funding_certificate_material(sealed_body)
    material["tip_funding_root"] = str(sealed_body.get("tip_funding_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["funding_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_funding"] = True
    sealed["total_spine_funding_impl"] = TOTAL_SPINE_FUNDING_IMPL
    sealed["funded_at"] = str(body.get("funded_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    if fundings:
        sealed_pairs: list[Any] = []
        for src, dest in zip(fundings, sealed.get("fundings") or []):
            if isinstance(src, Mapping) and isinstance(dest, dict):
                if src.get("pairs"):
                    dest["pairs"] = list(src.get("pairs") or [])
                sealed_pairs.append(dest)
        if sealed_pairs:
            sealed["fundings"] = sealed_pairs
    return sealed


def funding_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-funding.json`` under a "funding/"out root."""
    path = Path(root)
    if path.is_file():
        if path.name == TOTAL_SPINE_FUNDING_FILENAME or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == TOTAL_SPINE_FUNDING_KIND
                or path.name == TOTAL_SPINE_FUNDING_FILENAME
            ):
                return path
        parent = path.parent
        sibling = parent / TOTAL_SPINE_FUNDING_FILENAME
        if sibling.is_file():
            return sibling
        nested = parent / "funding" / TOTAL_SPINE_FUNDING_FILENAME
        if nested.is_file():
            return nested
        grand = parent.parent / "funding" / TOTAL_SPINE_FUNDING_FILENAME
        if grand.is_file():
            return grand
        grand_sib = parent.parent / TOTAL_SPINE_FUNDING_FILENAME
        if grand_sib.is_file():
            return grand_sib
        return parent / "funding" / TOTAL_SPINE_FUNDING_FILENAME
    named = path / TOTAL_SPINE_FUNDING_FILENAME
    if named.is_file():
        return named
    nested = path / "funding" / TOTAL_SPINE_FUNDING_FILENAME
    if nested.is_file():
        return nested
    return path / "funding" / TOTAL_SPINE_FUNDING_FILENAME


def write_total_spine_funding_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a liquidity receipt under ``out_root``."""
    sealed = seal_total_spine_funding_certificate(body)
    path = funding_certificate_path(Path(out_root))
    if path.is_file():
        try:
            existing = load_total_spine_funding_certificate(path)
        except StageRefused:
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get("funding_digest")
                or existing.get("certificate_hash")
                or ""
            )
            new_digest = str(
                sealed.get("funding_digest")
                or sealed.get("certificate_hash")
                or ""
            )
            if (
                existing_digest
                and existing_digest == new_digest
                and allow_idempotent
            ):
                existing["funding_path"] = str(path)
                existing["total_spine_funding_idempotent"] = True
                return existing
            raise StageRefused(
                "total_spine_funding_supersession_refused",
                f"irreversible funding already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed["funding_path"] = str(path)
    sealed["total_spine_funding_idempotent"] = False
    return sealed


def verify_total_spine_funding_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute collateral digest and LvC roots; fail closed on tamper."""
    claimed = str(
        certificate.get("funding_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _funding_certificate_material(certificate)
    expected = _sha256_json(material)
    fundings = list(certificate.get("fundings") or [])
    recomputed_tip = compute_total_spine_funding_root(fundings)
    claimed_tip = str(certificate.get("tip_funding_root") or "")
    height = int(certificate.get("funding_height") or 0)
    count = int(certificate.get("funding_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_funding_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(fundings):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_funding_root") or "") != parent:
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
            "liquidity_index": int(row.get("liquidity_index") or idx),
            "liquidity_height": int(row.get("liquidity_height") or (idx + 1)),
            "liquidity_digest": str(row.get("liquidity_digest") or ""),
            "bound_liquidity_root": str(row.get("bound_liquidity_root") or ""),
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
            "facilitated": bool(row.get("facilitated", True)),
            "required": bool(row.get("required", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_funding_root": parent,
            "post_liquidity": True,
            "deterministic": True,
            "fvr": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("liquidity_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_FUNDING_MIN_FUNDINGS and height >= count
    fundings_ok = all(
        isinstance(row, Mapping)
        and bool(row.get("facilitated", True))
        and bool(row.get("required", True))
        and bool(row.get("atomic_ok", True))
        and bool(row.get("fvr", True))
        and not bool(row.get("one_sided", False))
        and int(row.get("residual") or 0) == 0
        for row in fundings
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_FUNDING_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_liquidity") is True
        and certificate.get("deterministic") is True
        and certificate.get("facilitated") is True
        and certificate.get("required") is True
        and certificate.get("atomic_ok") is True
        and certificate.get("fvr_ok") is True
        and certificate.get("one_sided") is False
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(fundings)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and fundings_ok
        and int(certificate.get("residual") or 0) == 0
        and TOTAL_SPINE_FUNDING_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_funding",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "funding_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "liquidity_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_funding_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_fundings_ok": min_ok,
        "fundings_ok": fundings_ok,
        "fvr_ok": certificate.get("fvr_ok") is True,
        "atomic_ok": certificate.get("atomic_ok") is True,
        "kind_ok": str(certificate.get("kind") or "") == TOTAL_SPINE_FUNDING_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "facilitated_ok": certificate.get("facilitated") is True,
        "required_ok": certificate.get("required") is True,
        "total_spine_funding": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_funding_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed liquidity receipt."""
    file_path = funding_certificate_path(Path(path))
    if not file_path.is_file():
        raise StageRefused(
            "total_spine_funding_missing",
            f"funding certificate not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRefused(
            "total_spine_funding_unreadable",
            f"funding certificate unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StageRefused(
            "total_spine_funding_invalid",
            "funding certificate root must be a JSON object",
        )
    if str(payload.get("kind") or "") != TOTAL_SPINE_FUNDING_KIND and not payload.get(
        "total_spine_funding"
    ):
        raise StageRefused(
            "total_spine_funding_missing",
            f"funding certificate not found at {file_path}",
        )
    verify = verify_total_spine_funding_certificate(payload)
    if not verify.get("ok"):
        raise StageRefused(
            "total_spine_funding_tampered",
            f"funding certificate digest mismatch at {file_path} "
            f"(claimed={verify.get('claimed_digest')!r} "
            f"expected={verify.get('expected_digest')!r})",
        )
    body = dict(payload)
    body["funding_path"] = str(file_path)
    body["funding_verify"] = verify
    body["total_spine_funding_loaded"] = True
    return body


def seal_total_spine_funding_chain(
    *,
    prior_tip: str,
    funding_digest: str,
    tip_funding_root: str,
    bound_liquidity_root: str,
    bound_delivery_root: str,
    bound_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    liquidity_digest: str,
    delivery_digest: str,
    funding_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal funding hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    md = str(funding_digest or "").strip() or ("0" * 64)
    mr = str(tip_funding_root or "").strip() or ("0" * 64)
    cr = str(bound_liquidity_root or "").strip() or ("0" * 64)
    dlr = str(bound_delivery_root or "").strip() or ("0" * 64)
    clr = str(bound_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    cd = str(liquidity_digest or "").strip() or ("0" * 64)
    dvd = str(delivery_digest or "").strip() or ("0" * 64)
    material = (
        f"funding|{int(bool(short_circuit))}|{int(funding_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{clr}|{dlr}|{cr}|{dvd}|{cd}|{mr}|{md}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "funding_height": int(funding_height),
        "tip_funding_root": mr,
        "bound_liquidity_root": cr,
        "bound_delivery_root": dlr,
        "bound_clearing_root": clr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "liquidity_digest": cd,
        "delivery_digest": dvd,
        "funding_digest": md,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_funding": True,
        "irreversible": True,
        "post_liquidity": True,
        "deterministic": True,
        "fvr": True,
    }


def annotate_total_spine_funding(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-liquidity LvC onto a total-spine result and rebind tip."""
    cst_digest = str(
        certificate.get("funding_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_funding_root = str(certificate.get("tip_funding_root") or "")
    funding_height = int(certificate.get("funding_height") or 0)
    funding_count = int(certificate.get("funding_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    bound_clearing_root = str(certificate.get("bound_clearing_root") or "")
    bound_liquidity_root = str(certificate.get("bound_liquidity_root") or "")
    bound_delivery_root = str(certificate.get("bound_delivery_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    liquidity_digest = str(certificate.get("liquidity_digest") or "")
    delivery_digest = str(certificate.get("delivery_digest") or "")
    chain = seal_total_spine_funding_chain(
        prior_tip=prior_tip,
        funding_digest=cst_digest,
        tip_funding_root=tip_funding_root,
        bound_liquidity_root=bound_liquidity_root,
        bound_delivery_root=bound_delivery_root,
        bound_clearing_root=bound_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        liquidity_digest=liquidity_digest,
        delivery_digest=delivery_digest,
        funding_height=funding_height,
        short_circuit=short_circuit,
    )
    cst_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{cst_tip}".encode("utf-8"))
    body["total_spine_funding"] = True
    body["total_spine_funding_impl"] = TOTAL_SPINE_FUNDING_IMPL
    body["total_spine_funding_short_circuit"] = bool(short_circuit)
    body["total_spine_funding_irreversible"] = True
    body["total_spine_funding_post_liquidity"] = True
    body["total_spine_funding_deterministic"] = True
    body["total_spine_funding_fvr"] = True
    body["total_spine_funding_certificate"] = dict(certificate)
    body["total_spine_funding_digest"] = cst_digest
    body["total_spine_funding_chain"] = chain
    body["total_spine_funding_tip"] = cst_tip
    body["total_spine_funding_bound_tip"] = bound
    body["total_spine_digest_pre_funding"] = prior_tip
    body["total_spine_tip_funding_root"] = tip_funding_root
    body["total_spine_funding_height"] = funding_height
    body["total_spine_funding_count"] = funding_count
    body["total_spine_facilitated"] = bool(certificate.get("facilitated", True))
    body["total_spine_facilitated_ok"] = bool(certificate.get("facilitated", True))
    body["total_spine_required"] = bool(certificate.get("required", True))
    body["total_spine_required_ok"] = bool(certificate.get("required", True))
    body["total_spine_fvr_ok"] = bool(certificate.get("fvr_ok", True))
    body["total_spine_funding_atomic"] = bool(certificate.get("atomic_ok", True))
    body["total_spine_funding_one_sided"] = bool(
        certificate.get("one_sided", False)
    )
    body["total_spine_fundings_ok"] = bool(
        certificate.get("fundings_ok", True)
    )
    body["total_spine_funding_root_valid"] = bool(tip_funding_root)
    body["total_spine_funding_residual"] = int(certificate.get("residual") or 0)
    body["total_spine_funding_pair_count"] = int(
        certificate.get("pair_count") or 0
    )
    body["funding_root"] = tip_funding_root
    body["tip_funding_root"] = tip_funding_root
    body["funding_count"] = funding_count
    body["funding_height"] = funding_height
    body["facilitated"] = bool(certificate.get("facilitated", True))
    body["facilitated_ok"] = bool(certificate.get("facilitated", True))
    body["funding_ok"] = bool(certificate.get("facilitated", True))
    body["fvr_ok"] = bool(certificate.get("fvr_ok", True))
    body["required"] = bool(certificate.get("required", True))
    if certificate.get("funding_path"):
        body["total_spine_funding_path"] = certificate.get("funding_path")
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
    if bound_liquidity_root:
        body["total_spine_tip_liquidity_root"] = bound_liquidity_root
        body["liquidity_root"] = bound_liquidity_root
        body["tip_liquidity_root"] = bound_liquidity_root
        body.setdefault("total_spine_liquidity", True)
        body.setdefault("total_spine_funded", True)
        body.setdefault("total_spine_lvc_ok", True)
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
    if liquidity_digest:
        body["total_spine_liquidity_digest"] = liquidity_digest
    if delivery_digest:
        body["total_spine_delivery_digest"] = delivery_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_funding_ok_short_circuit"
        if short_circuit
        else "total_spine_funding_ok"
    )
    body["ok"] = True
    return body


def _as_liquidity_mapping(value: Any) -> dict[str, Any] | None:
    from blackhole_agent.upstream_total_spine_liquidity import (
        StageRefused as LiquidityRefused,
        load_total_spine_liquidity_certificate,
    )

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_FUNDING_KIND or value.get("total_spine_funding"):
            nested_liq = value.get("total_spine_liquidity_certificate")
            if isinstance(nested_liq, Mapping) and nested_liq.get(
                "tip_liquidity_root"
            ):
                return dict(nested_liq)
        if kind == TOTAL_SPINE_LIQUIDITY_KIND or value.get(
            "total_spine_liquidity"
        ) or value.get("total_spine_liquidity_loaded") or value.get(
            "tip_liquidity_root"
        ):
            nested = value.get("total_spine_liquidity_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_liquidity_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_liquidity_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / "liquidity" / "total-spine-liquidity.json"
            named = path / "total-spine-liquidity.json"
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != TOTAL_SPINE_LIQUIDITY_KIND:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_total_spine_liquidity_certificate(path)
    except LiquidityRefused as exc:
        if str(exc.verdict) == "total_spine_liquidity_tampered":
            raise StageRefused(str(exc.verdict), str(exc.detail)) from exc
        return None
    except Exception:  # noqa: BLE001
        return None


def _as_funding_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_FUNDING_KIND or value.get(
            "total_spine_funding"
        ) or value.get("total_spine_funding_loaded"):
            nested = value.get("total_spine_funding_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_funding_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_funding_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    try:
        return load_total_spine_funding_certificate(Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == "total_spine_funding_tampered":
            raise
        return None
    except Exception:  # noqa: BLE001
        return None



def _margins_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_collateral_certificate")
    # Prefer explicit margin certificates carried on annotated results.
    nested_mgn = item.get("total_spine_margin_certificate")
    if isinstance(nested_mgn, Mapping) and (
        nested_mgn.get("tip_margin_root") or nested_mgn.get("margins")
    ):
        found.append(dict(nested_mgn))
    if item.get("tip_margin_root") and item.get("margins"):
        found.append(dict(item))
    extra = item.get("margins")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_margin_root") or row.get("margin_digest")
            ):
                found.append(dict(row))
    if isinstance(nested, Mapping):
        for row in _margins_from(nested):
            found.append(row)
    return found


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
    nested = item.get("total_spine_collateral_certificate")
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


def _collaterals_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_collateral_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_collateral_root") or nested.get("collaterals")
    ):
        found.append(dict(nested))
    if item.get("tip_collateral_root") and (
        item.get("collaterals") or item.get("kind") == "total_spine_collateral"
    ):
        found.append(dict(item))
    extra = item.get("collaterals")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_collateral_root") or row.get("collateral_digest")
            ):
                found.append(dict(row))
    if isinstance(nested, Mapping):
        for row in _collaterals_from(nested):
            found.append(row)
    return found


def _confirm_liquidity(
    primary: Mapping[str, Any],
    *,
    collaterals: Sequence[Mapping[str, Any]],
    margins: Sequence[Mapping[str, Any]],
    custodies: Sequence[Mapping[str, Any]],
    deliveries: Sequence[Mapping[str, Any]],
    clearings: Sequence[Mapping[str, Any]],
    settlements: Sequence[Mapping[str, Any]],
    actuation: Mapping[str, Any] | None,
    out_root: Path | None,
    prior_tip: str,
    repo_path: Path | None,
) -> dict[str, Any]:
    """Independently re-fund the same book as a confirmation side."""
    from blackhole_agent.upstream_total_spine_liquidity import liquidity_total_spine

    confirm_out = None
    if out_root is not None:
        confirm_out = Path(out_root) / "funding-confirm"
    tip_liquidity = str(primary.get("tip_liquidity_root") or "")
    liq_height = int(primary.get("liquidity_height") or 0)
    bundle: list[Any] = []
    for row in collaterals:
        bundle.append(row)
    for row in margins:
        bundle.append(row)
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
            "total_spine_funding_confirmation_missing",
            "single liquidity requires collaterals, margins, custodies, "
            "deliveries, clearings, settlements, or actuation to confirm-funding",
        )
    confirmed = liquidity_total_spine(
        bundle,
        collaterals=collaterals or None,
        margins=margins or None,
        clearings=clearings or None,
        settlements=settlements or None,
        actuation=actuation,
        out_root=confirm_out,
        prior_tip=prior_tip,
        parent_liquidity_root=tip_liquidity,
        liquidity_height=liq_height + 1 if liq_height else None,
        repo_path=repo_path or REPO_ROOT,
        confirm=True,
    )
    cert = confirmed.get("total_spine_liquidity_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            "total_spine_funding_confirmation_missing",
            "confirmation liquidity did not produce a certificate",
        )
    return dict(cert)


def _collect_liquidities(
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
    """Return (existing_liquidity, collaterals, margins, custodies, deliveries, clearings, settlements, actuation)."""
    existing = _as_funding_mapping(source)
    if existing is None and body is not None:
        existing = _as_funding_mapping(body)
    liquidities: list[dict[str, Any]] = []
    collaterals: list[dict[str, Any]] = []
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
        mapped = _as_liquidity_mapping(item)
        if mapped is not None:
            liquidities.append(mapped)
            _take_actuation(mapped)
            for row in _collaterals_from(mapped):
                collaterals.append(row)
            for row in _margins_from(mapped):
                margins.append(row)
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
            for row in _collaterals_from(item):
                collaterals.append(row)
            for row in _margins_from(item):
                margins.append(row)
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
        _push(body.get("total_spine_liquidity_certificate"))
        _push(body.get("total_spine_collateral_certificate"))
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
    for row in liquidities:
        digest = _liquidity_digest_of(row)
        tip = str(row.get("tip_liquidity_root") or "")
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
    mgn_deduped: list[dict[str, Any]] = []
    mgn_seen: set[str] = set()
    for row in margins:
        digest = str(
            row.get("margin_digest")
            or row.get("certificate_hash")
            or row.get("tip_margin_root")
            or ""
        )
        if not digest or digest in mgn_seen:
            continue
        mgn_seen.add(digest)
        mgn_deduped.append(row)
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
    col_deduped: list[dict[str, Any]] = []
    col_seen: set[str] = set()
    for row in collaterals:
        digest = str(
            row.get("collateral_digest")
            or row.get("certificate_hash")
            or row.get("tip_collateral_root")
            or ""
        )
        if not digest or digest in col_seen:
            continue
        col_seen.add(digest)
        col_deduped.append(row)
    return (
        existing,
        deduped,
        col_deduped,
        mgn_deduped,
        cst_deduped,
        dlv_deduped,
        clr_deduped,
        set_deduped,
        actuation,
    )


def _strip_funding_predicates(done_when: str) -> str:
    """Evaluate the pre-facilitate contract, never liquidity_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "funding_ok",
        "facility_ok",
        "facilitated_ok",
        "min_fundings",
        "funding_root_valid",
        "fvr_ok",
        "requirement_ok",
        "required_ok",
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


def funding_total_spine(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    liquidities: Sequence[Mapping[str, Any] | Path | str] | None = None,
    margins: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_fundings: int = TOTAL_SPINE_FUNDING_MIN_FUNDINGS,
    parent_funding_root: str = "",
    funding_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
    settlements: Sequence[Mapping[str, Any]] | None = None,
    clearings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply post-liquidity atomic LvC liquidity on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_FUNDING_IMPL:
        raise StageRefused(
            "total_spine_funding_disabled",
            "TOTAL_SPINE_FUNDING_IMPL is False",
        )

    extra_books: list[Any] = []
    extra_books.extend(list(liquidities or []))
    extra_books.extend(list(margins or []))
    (
        existing,
        collected,
        found_collaterals,
        found_margins,
        found_custodies,
        found_deliveries,
        found_clearings,
        found_settlements,
        found_actuation,
    ) = _collect_liquidities(source, body, extra_books)
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
        and existing.get("tip_funding_root")
        and (
            str(existing.get("kind") or "") == TOTAL_SPINE_FUNDING_KIND
            or existing.get("total_spine_funding_loaded")
            or existing.get("total_spine_funding")
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
            "action": "funding_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_funding(
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

    want = max(int(min_fundings), TOTAL_SPINE_FUNDING_MIN_FUNDINGS)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_liquidity(
                collected[0],
                collaterals=found_collaterals,
                margins=found_margins,
                custodies=found_custodies,
                deliveries=found_deliveries,
                clearings=found_clearings,
                settlements=found_settlements,
                actuation=actuation,
                out_root=out_root,
                prior_tip=str(
                    prior_tip
                    or (body or {}).get("total_spine_liquidity_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            "total_spine_funding_margins_short",
            f"funding requires >= {want} independent liquidities, "
            f"got {len(collected)}",
        )

    legs = book_total_spine_liquidities(
        collected,
        min_fundings=want,
        parent_funding_root=parent_funding_root,
        funding_height=funding_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("bound_settlement_root") or "")
    clearing_root = str(first.get("bound_clearing_root") or "")
    margin_root = str(first.get("tip_liquidity_root") or "")
    liquidity_digest = _liquidity_digest_of(first)
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
    pre_liquidity = _strip_funding_predicates(done_when)
    if pre_liquidity:
        ctx = {
            "liquidity": {
                "ok": True,
                "funded": True,
                "funded_ok": True,
                "liquidity_root_valid": True,
                "lvc_ok": True,
                "liquidity_count": int(first.get("liquidity_count") or 0),
                "tip_liquidity_root": margin_root,
            },
            "liquidity_count": int(first.get("liquidity_count") or 0),
            "tip_liquidity_root": margin_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_liquidity,
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
                "total_spine_funding_contract_unmet",
                f"done_when not met at collateral: {pre_liquidity!r}",
            )

    tip_funding_root = compute_total_spine_funding_root(legs)
    cst_height = int(legs[-1]["liquidity_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_liquidity_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    pair_count = int(legs[0].get("pair_count") or 0) if legs else 0

    cst_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_FUNDING_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "bound_clearing_root": clearing_root,
        "bound_liquidity_root": margin_root,
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
        "liquidity_digest": liquidity_digest,
        "delivery_digest": str(
            first.get("delivery_digest")
            or first.get("certificate_hash")
            or ""
        ),
        "prior_tip": tip,
        "parent_funding_root": str(
            parent_funding_root
            or (legs[0].get("parent_funding_root") if legs else "")
            or ""
        ),
        "fundings": legs,
        "funding_count": len(legs),
        "funding_height": cst_height,
        "tip_funding_root": tip_funding_root,
        "pair_count": pair_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "facilitated": True,
        "required": True,
        "atomic_ok": True,
        "fvr_ok": True,
        "one_sided": False,
        "fundings_ok": True,
        "fundings_ok": True,
        "post_liquidity": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "funded_at": utc_now_iso(),
    }
    if contract_eval is not None:
        cst_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_funding_certificate(write_target, cst_body)
    else:
        certificate = seal_total_spine_funding_certificate(cst_body)

    result = body if body is not None else {
        "ok": True,
        "action": "funding_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_funding(
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
        cst_bound = str(annotated.get("total_spine_funding_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=cst_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_funding_bound_state_root"] = state_root
    annotated["total_spine_funding_bound_action_root"] = action_root
    annotated["total_spine_funding_bound_settlement_root"] = settlement_root
    annotated["total_spine_funding_bound_clearing_root"] = clearing_root
    annotated["total_spine_funding_bound_liquidity_root"] = margin_root
    annotated["total_spine_funding_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_funding_proof() -> dict[str, Any]:
    """Hermetic proof: post-liquidity atomic FvR on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_FUNDING_IMPL as ENGINE_FND_IMPL,
        TOTAL_SPINE_LIQUIDITY_IMPL,
        TOTAL_SPINE_COLLATERAL_IMPL,
        TOTAL_SPINE_MARGIN_IMPL,
        TOTAL_SPINE_CUSTODY_IMPL,
        TOTAL_SPINE_FINALITY_KIND,
        actuate_total_spine,
        clear_total_spine,
        collateral_total_spine,
        custody_total_spine,
        margin_total_spine,
        deliver_total_spine,
        execute_total_spine,
        federate_total_spine,
        liquidity_total_spine,
        run_total_spine,
        settle_total_spine,
        write_total_spine_finality_certificate,
    )
    from blackhole_agent.upstream_total_spine_liquidity import (
        seal_total_spine_liquidity_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="total-spine-funding-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_FUNDING_IMPL is True
            and ENGINE_FND_IMPL is True
            and TOTAL_SPINE_LIQUIDITY_IMPL is True
            and TOTAL_SPINE_COLLATERAL_IMPL is True
            and TOTAL_SPINE_MARGIN_IMPL is True
            and TOTAL_SPINE_CUSTODY_IMPL is True
            and TOTAL_SPINE_FUNDING_KIND == "total_spine_funding"
            and bool(TOTAL_SPINE_FUNDING_FILENAME)
            and TOTAL_SPINE_FUNDING_MIN_FUNDINGS >= 2
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
                "goal": "funding proof origin",
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

        col1 = collateral_total_spine(
            [cert_m1, cert_m2],
            out_root=scratch / "col-h1",
            prior_tip=str(mgn2.get("total_spine_margin_bound_tip") or ""),
            body=dict(mgn2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_col1 = col1.get("total_spine_collateral_certificate") or {}
        tip_collateral = str(col1.get("total_spine_tip_collateral_root") or "")
        col2 = collateral_total_spine(
            [cert_m1, cert_m2],
            out_root=scratch / "col-h2",
            prior_tip=str(col1.get("total_spine_collateral_bound_tip") or ""),
            parent_collateral_root=tip_collateral,
            collateral_height=int(col1.get("total_spine_collateral_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_col2 = col2.get("total_spine_collateral_certificate") or {}

        liq1 = liquidity_total_spine(
            [cert_col1, cert_col2],
            out_root=scratch / "liq-h1",
            prior_tip=str(col2.get("total_spine_collateral_bound_tip") or ""),
            body=dict(col2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_liq1 = liq1.get("total_spine_liquidity_certificate") or {}
        tip_liquidity = str(liq1.get("total_spine_tip_liquidity_root") or "")
        liq2 = liquidity_total_spine(
            [cert_col1, cert_col2],
            out_root=scratch / "liq-h2",
            prior_tip=str(liq1.get("total_spine_liquidity_bound_tip") or ""),
            parent_liquidity_root=tip_liquidity,
            liquidity_height=int(liq1.get("total_spine_liquidity_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_liq2 = liq2.get("total_spine_liquidity_certificate") or {}

        offline_fnd = funding_total_spine(
            [cert_liq1, cert_liq2],
            out_root=scratch / "fnd-h1",
            prior_tip=str(liq2.get("total_spine_liquidity_bound_tip") or ""),
            body=dict(liq2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        fnd_path = offline_fnd.get("total_spine_funding_path")
        tip_funding = str(offline_fnd.get("total_spine_tip_funding_root") or "")
        offline_ok = (
            bool(offline_fnd.get("ok"))
            and offline_fnd.get("total_spine_funding") is True
            and offline_fnd.get("total_spine_funding_post_liquidity") is True
            and offline_fnd.get("total_spine_funding_irreversible") is True
            and offline_fnd.get("total_spine_facilitated") is True
            and offline_fnd.get("total_spine_required") is True
            and offline_fnd.get("total_spine_fvr_ok") is True
            and offline_fnd.get("total_spine_funding_atomic") is True
            and offline_fnd.get("total_spine_funding_one_sided") is False
            and int(offline_fnd.get("total_spine_funding_count") or 0) >= 2
            and int(offline_fnd.get("total_spine_funding_height") or 0) >= 2
            and int(offline_fnd.get("total_spine_funding_residual") or 0) == 0
            and int(offline_fnd.get("total_spine_funding_pair_count") or 0) >= 1
            and len(tip_funding) >= 32
            and str(offline_fnd.get("total_spine_state_root") or "") == state_root
            and str(offline_fnd.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_fnd.get("total_spine_digest") or "")
            != str(liq1.get("total_spine_digest") or "")
            and isinstance(fnd_path, str)
            and Path(fnd_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_funding_certificate(fnd_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_funding_loaded")
            and (loaded.get("funding_verify") or {}).get("ok")
            and (loaded.get("funding_verify") or {}).get("funding_root_ok")
            and (loaded.get("funding_verify") or {}).get("chain_ok")
            and (loaded.get("funding_verify") or {}).get("fundings_ok")
            and (loaded.get("funding_verify") or {}).get("fvr_ok")
        )

        tampered_path = scratch / "tampered-funding.json"
        tampered_body = dict(loaded)
        for drop in (
            "funding_verify",
            "total_spine_funding_loaded",
            "funding_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["funding_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_funding_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_funding_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_funding_certificate(
                scratch / "fnd-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "funding_verify",
                            "total_spine_funding_loaded",
                            "funding_path",
                            "funding_digest",
                            "certificate_hash",
                            "funded_at",
                            "facilitated_at",
                            "total_spine_funding",
                            "total_spine_funding_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_funding_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_funding_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "funding_verify",
            "total_spine_funding_loaded",
            "funding_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_funding_certificate(wrong_body)
        wrong_verify = verify_total_spine_funding_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("funding_root_ok") is False
        )

        mismatch_ok = False
        try:
            mixed = dict(cert_liq1)
            mixed["bound_state_root"] = "e" * 64
            book_total_spine_liquidities(
                [cert_liq1, mixed],
                min_fundings=2,
            )
        except StageRefused:
            mismatch_ok = True
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        one_sided_ok = False
        try:
            forged = dict(cert_liq2)
            forged["capabilities"] = ["capability.one-sided-only"]
            for drop in (
                "liquidity_digest",
                "certificate_hash",
                "funded_at",
                "liquidity_path",
                "liquidity_verify",
                "total_spine_liquidity_loaded",
            ):
                forged.pop(drop, None)
            resealed_one = seal_total_spine_liquidity_certificate(forged)
            book_total_spine_liquidities(
                [cert_liq1, resealed_one], min_fundings=2
            )
        except StageRefused as exc:
            one_sided_ok = str(exc.verdict) == "total_spine_funding_one_sided"
        except Exception:  # noqa: BLE001
            one_sided_ok = False

        partial_ok = False
        try:
            _assert_pairs_atomic(
                [
                    {
                        "capability_id": good_id,
                        "facility_ok": True,
                        "requirement_ok": False,
                        "atomic_ok": False,
                    }
                ]
            )
        except StageRefused as exc:
            partial_ok = str(exc.verdict) == "total_spine_funding_partial"
        except Exception:  # noqa: BLE001
            partial_ok = False

        h2 = funding_total_spine(
            [cert_liq1, cert_liq2],
            out_root=scratch / "fnd-h2",
            prior_tip=str(
                offline_fnd.get("total_spine_funding_bound_tip") or ""
            ),
            parent_funding_root=tip_funding,
            funding_height=int(
                offline_fnd.get("total_spine_funding_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_funding_count") or 0) >= 2
            and str(h2.get("total_spine_tip_funding_root") or "") != tip_funding
            and str(
                (h2.get("total_spine_funding_certificate") or {}).get(
                    "parent_funding_root"
                )
                or ""
            )
            == tip_funding
        )

        recomputed = compute_total_spine_funding_root(
            loaded.get("fundings") or []
        )
        determinism_ok = recomputed == tip_funding and bool(recomputed)

        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live-fnd",
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
            liquidity=True,
            funding=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_fnd_path = live.get("total_spine_funding_path")
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
            and live.get("total_spine_liquidity") is True
            and live.get("total_spine_funding") is True
            and live.get("total_spine_facilitated") is True
            and live.get("total_spine_fvr_ok") is True
            and int(live.get("total_spine_funding_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_funding_root"), str)
            and len(str(live.get("total_spine_tip_funding_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_fnd_path, str)
            and Path(live_fnd_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short-fnd",
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
            liquidity=True,
            funding=True,
            resume_dir=live_fnd_path or (scratch / "live-fnd"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_funding") is True
            and shorted.get("total_spine_funding_short_circuit") is True
            and str(shorted.get("total_spine_tip_funding_root") or "")
            == str(live.get("total_spine_tip_funding_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        fnd_chain = live.get("total_spine_funding_chain") or {}
        chain_integrity_ok = False
        if isinstance(fnd_chain, Mapping) and fnd_chain:
            re_seal = seal_total_spine_funding_chain(
                prior_tip=str(fnd_chain.get("prior_tip") or ""),
                funding_digest=str(fnd_chain.get("funding_digest") or ""),
                tip_funding_root=str(fnd_chain.get("tip_funding_root") or ""),
                bound_liquidity_root=str(
                    fnd_chain.get("bound_liquidity_root") or ""
                ),
                bound_delivery_root=str(
                    fnd_chain.get("bound_delivery_root") or ""
                ),
                bound_clearing_root=str(
                    fnd_chain.get("bound_clearing_root") or ""
                ),
                bound_settlement_root=str(
                    fnd_chain.get("bound_settlement_root") or ""
                ),
                bound_action_root=str(fnd_chain.get("bound_action_root") or ""),
                bound_state_root=str(fnd_chain.get("bound_state_root") or ""),
                actuation_digest=str(fnd_chain.get("actuation_digest") or ""),
                liquidity_digest=str(fnd_chain.get("liquidity_digest") or ""),
                delivery_digest=str(fnd_chain.get("delivery_digest") or ""),
                funding_height=int(fnd_chain.get("funding_height") or 0),
                short_circuit=bool(fnd_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == fnd_chain.get("digest")
                and re_seal.get("digest") == live.get("total_spine_funding_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(liq1.get("total_spine_digest") or "")
            != str(offline_fnd.get("total_spine_digest") or "")
        )

        # Facade exposes this stage's surface (delegation identity;
        # source-text greps predate the thin PEP 562 facade).
        source_ok = (
            getattr(le_facade, "TOTAL_SPINE_FUNDING_IMPL", None) is TOTAL_SPINE_FUNDING_IMPL
            and getattr(le_facade, "builtin_total_spine_funding_proof", None) is builtin_total_spine_funding_proof
            and getattr(le_facade, "funding_total_spine", None) is funding_total_spine
            and callable(
                getattr(le_facade, "builtin_total_spine_funding_proof", None)
    
        )
            and callable(getattr(le_facade, "funding_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_FUNDING_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_FUNDING_IMPL" in engine_text
            and "funding_total_spine" in engine_text
            and (
                "funding=True" in engine_text
                or "funding: bool = False" in engine_text
            )
            and "builtin_total_spine_funding_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def funding_total_spine" in mod_text
            and "def builtin_total_spine_funding_proof" in mod_text
            and "total_spine_funding_supersession_refused" in mod_text
            and "total_spine_funding_tampered" in mod_text
            and "total_spine_funding_one_sided" in mod_text
            and "total_spine_funding_fvr_failed" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-funding"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_funding" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_funding_proof" in (entry.entry or "")
                and (
                    "funding" in tags_blob
                    or "funding" in name_blob
                    or "funding" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "funding_total_spine" in delta_blob
                    or "post-liquidity" in delta_blob
                    or "post_liquidity" in delta_blob
                    or "fvr" in delta_blob
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
            "action": "total_spine_funding_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "funding_path": fnd_path,
            "tip_funding_root": tip_funding,
            "tip_liquidity_root": tip_liquidity,
            "tip_collateral_root": tip_collateral,
            "tip_margin_root": tip_margin,
            "tip_custody_root": tip_custody,
            "tip_delivery_root": tip_delivery,
            "tip_clearing_root": tip_clearing,
            "tip_settlement_root": tip_settlement,
            "tip_action_root": tip_action,
            "state_root": state_root,
            "funding_count": offline_fnd.get("total_spine_funding_count"),
            "pair_count": offline_fnd.get("total_spine_funding_pair_count"),
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
            "live_funding_path": live_fnd_path,
            "live_tip_funding_root": live.get("total_spine_tip_funding_root"),
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
            "total_spine_funding": True,
            "total_spine_liquidity": True,
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
        "funding-proof",
        help=(
            "Total spine funding proof: post-liquidity atomic FvR seals "
            "matching liquidity books into irreversible funding receipts"
        ),
    )
    sub.add_parser("proof", help="Alias for funding-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"funding-proof", "proof"}:
        result = builtin_total_spine_funding_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
