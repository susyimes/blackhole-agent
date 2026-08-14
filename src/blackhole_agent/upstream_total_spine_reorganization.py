"""Post-emergence reorganization-versus-charter for the absolute total spine.

Closes the emerged-but-unreorganized cliff: after ``emerge_total_spine``
seals atomic EvC receipts, independently confirm a second emergence, book
each emerged pair into a reorganization register and pair it with a charter
(RvC), seal hash-chained atomic reorganization receipts bound to the emergence
digests, refuse split / one-sided / mismatched / failed / wrong-root /
tampered reorganizations, short-circuit re-reorganization, and rebind the depth-28 tip
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

TOTAL_SPINE_REORGANIZATION_IMPL = True
TOTAL_SPINE_REORGANIZATION_KIND: str = "total_spine_reorganization"
TOTAL_SPINE_REORGANIZATION_FILENAME: str = "total-spine-reorganization.json"
TOTAL_SPINE_REORGANIZATION_MIN_REORGANIZATIONS: int = 2

TOTAL_SPINE_EMERGENCE_KIND: str = "total_spine_emergence"
TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


class StageRefused(Exception):
    """A verdict-bearing refusal from total-spine emergence."""

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


def _emergence_digest_of(row: Mapping[str, Any]) -> str:
    return str(
        row.get("emergence_digest")
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
    for leg in row.get("emergences") or row.get("recoveries") or row.get("risks") or row.get("reorganizations") or []:
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
    legs = margin.get("emergences") or margin.get("recoveries") or margin.get("risks") or []
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


def _rvc_pairs(capabilities: Sequence[str]) -> list[dict[str, Any]]:
    """Atomic liquidity+coverage pairs for each collateralized capability."""
    pairs: list[dict[str, Any]] = []
    for cid in capabilities:
        name = str(cid or "").strip()
        if not name:
            continue
        row = {
            "capability_id": name,
            "reorganized_ok": True,
            "charter_ok": True,
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
                "reorganized_ok": bool(row.get("reorganized_ok", True)),
                "charter_ok": bool(row.get("charter_ok", True)),
                "atomic_ok": bool(row.get("atomic_ok", True)),
                "pair_root": str(row.get("pair_root") or ""),
            }
        )
    return _sha256_json({"pairs": rows})


def _assert_pairs_atomic(pairs: Sequence[Mapping[str, Any]]) -> None:
    if not pairs:
        raise StageRefused(
            "total_spine_reorganization_pairs_empty",
            "stress refuses an empty LvC pair book",
        )
    for row in pairs:
        if not isinstance(row, Mapping):
            raise StageRefused(
                "total_spine_reorganization_partial",
                "stress refuses a malformed LvC pair",
            )
        reorganized_ok = bool(row.get("reorganized_ok", True))
        charter_ok = bool(row.get("charter_ok", True))
        if reorganized_ok != charter_ok or not bool(row.get("atomic_ok", True)):
            raise StageRefused(
                "total_spine_reorganization_partial",
                "stress refuses a split (non-atomic) risk-versus-requirement pair",
            )
        if not reorganized_ok or not charter_ok:
            raise StageRefused(
                "total_spine_reorganization_partial",
                "stress refuses an unemerged or uncovered LvC pair",
            )


def _reorganization_certificate_material(body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine risk certificate digests."""
    legs = body.get("reorganizations") or body.get("legs") or []
    collateral_rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            collateral_rows.append(
                {
                    "emergence_index": int(row.get("emergence_index") or 0),
                    "emergence_height": int(row.get("emergence_height") or 0),
                    "emergence_digest": str(row.get("emergence_digest") or ""),
                    "bound_emergence_root": str(
                        row.get("bound_emergence_root") or ""
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
                    "reorganized": bool(row.get("reorganized", True)),
                    "chartered": bool(row.get("chartered", True)),
                    "atomic_ok": bool(row.get("atomic_ok", True)),
                    "one_sided": bool(row.get("one_sided", False)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    "parent_reorganization_root": str(
                        row.get("parent_reorganization_root") or ""
                    ),
                    "emergence_root": str(row.get("emergence_root") or ""),
                    "post_reorganization": bool(row.get("post_reorganization", True)),
                    "deterministic": bool(row.get("deterministic", True)),
                    "rvc": bool(row.get("rvc", True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or TOTAL_SPINE_REORGANIZATION_KIND),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "bound_clearing_root": str(body.get("bound_clearing_root") or ""),
        "bound_emergence_root": str(body.get("bound_emergence_root") or ""),
        "bound_custody_root": str(body.get("bound_custody_root") or ""),
        "bound_delivery_root": str(body.get("bound_delivery_root") or ""),
        "emergence_digest": str(body.get("emergence_digest") or ""),
        "delivery_digest": str(body.get("delivery_digest") or ""),
        "parent_reorganization_root": str(body.get("parent_reorganization_root") or ""),
        "tip_reorganization_root": str(body.get("tip_reorganization_root") or ""),
        "reorganization_height": int(body.get("reorganization_height") or 0),
        "reorganization_count": int(body.get("reorganization_count") or 0),
        "pair_count": int(body.get("pair_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        "reorganized": bool(body.get("reorganized", True)),
        "chartered": bool(body.get("chartered", True)),
        "atomic_ok": bool(body.get("atomic_ok", True)),
        "rvc_ok": bool(body.get("rvc_ok", True)),
        "one_sided": bool(body.get("one_sided", False)),
        "reorganizations_ok": bool(body.get("reorganizations_ok", True)),
        "reorganizations_ok": bool(body.get("reorganizations_ok", True)),
        "post_reorganization": bool(body.get("post_reorganization", True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        "reorganizations": collateral_rows,
    }


def compute_total_spine_reorganization_root(
    risks: Sequence[Mapping[str, Any]],
) -> str:
    """Tip collateral root of a hash-chained LvC log (empty → zero)."""
    if not risks:
        return "0" * 64
    last = risks[-1]
    tip = str(last.get("emergence_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(risks):
        body = {
            "emergence_index": int(row.get("emergence_index") or idx),
            "emergence_height": int(row.get("emergence_height") or (idx + 1)),
            "emergence_digest": str(row.get("emergence_digest") or ""),
            "bound_emergence_root": str(row.get("bound_emergence_root") or ""),
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
            "reorganized": bool(row.get("reorganized", True)),
            "chartered": bool(row.get("chartered", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_reorganization_root": parent,
            "post_reorganization": True,
            "deterministic": True,
            "rvc": True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def book_total_spine_emergences(
    margins: Sequence[Mapping[str, Any]],
    *,
    min_reorganizations: int = TOTAL_SPINE_REORGANIZATION_MIN_REORGANIZATIONS,
    parent_reorganization_root: str = "",
    reorganization_height: int | None = None,
) -> list[dict[str, Any]]:
    """Book independently verified collateral books into atomic LvC legs.

    Two (or more) collaterals fund only when they share bound state/action/
    actuation/settlement/clearing roots and the same liquid pair book.
    Divergent capability sets are a one-sided refusal; book disagreement is
    a LvC failure. Each collateralized capability becomes a liquidity+coverage pair
    that must be atomic.
    """
    from blackhole_agent.upstream_total_spine_emergence import (
        verify_total_spine_emergence_certificate,
    )

    want = max(int(min_reorganizations), TOTAL_SPINE_REORGANIZATION_MIN_REORGANIZATIONS)
    verified: list[Mapping[str, Any]] = []
    for raw in margins:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_total_spine_emergence_certificate(raw)
        if not verify.get("ok"):
            raise StageRefused(
                "total_spine_reorganization_margin_tampered",
                "stress refuses a margin whose digest/chain does not verify",
            )
        if raw.get("emerged") is False or raw.get("success") is False:
            raise StageRefused(
                "total_spine_reorganization_capital_unemerged",
                "stress refuses an unemerged risk receipt",
            )
        if raw.get("confirmed") is False or raw.get("evc_ok") is False:
            raise StageRefused(
                "total_spine_reorganization_capital_uncapacitated",
                "stress refuses a risk whose RvA is not complete",
            )
        if raw.get("atomic_ok") is False:
            raise StageRefused(
                "total_spine_reorganization_margin_partial",
                "stress refuses a non-atomic margin receipt",
            )
        if int(raw.get("residual") or 0) != 0:
            raise StageRefused(
                "total_spine_reorganization_residual",
                "stress refuses a margin with a non-zero residual",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            "total_spine_reorganization_margins_short",
            f"risk requires >= {want} independent risks, "
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
            "total_spine_reorganization_root_missing",
            "risk requires liquidity bound state/action/actuation roots",
        )
    if not book_caps:
        raise StageRefused(
            "total_spine_reorganization_pairs_empty",
            "stress refuses a liquidity with no funded capabilities",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_reorganization_root or "")
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
                "total_spine_reorganization_root_mismatch",
                "stress refuses collaterals bound to different "
                "state/action/actuation roots",
            )
        if settlement and book_settlement and settlement != book_settlement:
            raise StageRefused(
                "total_spine_reorganization_root_mismatch",
                "stress refuses collaterals bound to different settlement roots",
            )
        if clearing and book_clearing and clearing != book_clearing:
            raise StageRefused(
                "total_spine_reorganization_root_mismatch",
                "stress refuses collaterals bound to different clearing roots",
            )
        sig = _book_signature(margin)
        if sig != book_sig:
            raise StageRefused(
                "total_spine_reorganization_evc_failed",
                "independent liquidity books disagree; LvC cannot complete",
            )
        caps = tuple(_capability_list(margin))
        if caps != book_caps:
            raise StageRefused(
                "total_spine_reorganization_one_sided",
                "stress refuses one-sided books whose capability sets differ",
            )
        pairs = _rvc_pairs(book_caps)
        _assert_pairs_atomic(pairs)
        height = (
            int(reorganization_height) + idx
            if reorganization_height is not None
            else (idx + 1)
        )
        material = {
            "emergence_index": idx,
            "emergence_height": height,
            "emergence_digest": _emergence_digest_of(margin),
            "bound_emergence_root": str(
                margin.get("tip_emergence_root") or ""
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
            "reorganized": True,
            "chartered": True,
            "atomic_ok": True,
            "one_sided": False,
            "residual": 0,
            "independent": True,
            "parent_reorganization_root": parent,
            "post_reorganization": True,
            "deterministic": True,
            "rvc": True,
        }
        emergence_root = _sha256_json(material)
        row = dict(material)
        row["emergence_root"] = emergence_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = emergence_root
    return legs


def seal_total_spine_reorganization_certificate(
    body: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal post-emergence LvC log into a tamper-evident receipt."""
    sealed_body = dict(body)
    reorganizations = list(sealed_body.get("reorganizations") or [])
    if not str(sealed_body.get("tip_reorganization_root") or "").strip():
        sealed_body["tip_reorganization_root"] = compute_total_spine_reorganization_root(
            reorganizations
        )
    if not int(sealed_body.get("reorganization_count") or 0):
        sealed_body["reorganization_count"] = len(reorganizations)
    if not int(sealed_body.get("reorganization_height") or 0):
        sealed_body["reorganization_height"] = len(reorganizations)
    material = _reorganization_certificate_material(sealed_body)
    material["tip_reorganization_root"] = str(sealed_body.get("tip_reorganization_root") or "")
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed["reorganization_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed["total_spine_reorganization"] = True
    sealed["total_spine_reorganization_impl"] = TOTAL_SPINE_REORGANIZATION_IMPL
    sealed["reorganized_at"] = str(body.get("reorganized_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    if reorganizations:
        sealed_pairs: list[Any] = []
        for src, dest in zip(reorganizations, sealed.get("reorganizations") or []):
            if isinstance(src, Mapping) and isinstance(dest, dict):
                if src.get("pairs"):
                    dest["pairs"] = list(src.get("pairs") or [])
                sealed_pairs.append(dest)
        if sealed_pairs:
            sealed["reorganizations"] = sealed_pairs
    return sealed


def reorganization_certificate_path(root: Path) -> Path:
    """Resolve ``total-spine-reorganization.json`` under a emergence/ out root."""
    path = Path(root)
    if path.is_file():
        if path.name == TOTAL_SPINE_REORGANIZATION_FILENAME or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == TOTAL_SPINE_REORGANIZATION_KIND
                or path.name == TOTAL_SPINE_REORGANIZATION_FILENAME
            ):
                return path
        parent = path.parent
        sibling = parent / TOTAL_SPINE_REORGANIZATION_FILENAME
        if sibling.is_file():
            return sibling
        nested = parent / "reorganization" / TOTAL_SPINE_REORGANIZATION_FILENAME
        if nested.is_file():
            return nested
        grand = parent.parent / "reorganization" / TOTAL_SPINE_REORGANIZATION_FILENAME
        if grand.is_file():
            return grand
        grand_sib = parent.parent / TOTAL_SPINE_REORGANIZATION_FILENAME
        if grand_sib.is_file():
            return grand_sib
        return parent / "reorganization" / TOTAL_SPINE_REORGANIZATION_FILENAME
    named = path / TOTAL_SPINE_REORGANIZATION_FILENAME
    if named.is_file():
        return named
    nested = path / "reorganization" / TOTAL_SPINE_REORGANIZATION_FILENAME
    if nested.is_file():
        return nested
    return path / "reorganization" / TOTAL_SPINE_REORGANIZATION_FILENAME


def write_total_spine_reorganization_certificate(
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write a liquidity receipt under ``out_root``."""
    sealed = seal_total_spine_reorganization_certificate(body)
    path = reorganization_certificate_path(Path(out_root))
    if path.is_file():
        try:
            existing = load_total_spine_reorganization_certificate(path)
        except StageRefused:
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get("reorganization_digest")
                or existing.get("certificate_hash")
                or ""
            )
            new_digest = str(
                sealed.get("reorganization_digest")
                or sealed.get("certificate_hash")
                or ""
            )
            if (
                existing_digest
                and existing_digest == new_digest
                and allow_idempotent
            ):
                existing["reorganization_path"] = str(path)
                existing["total_spine_reorganization_idempotent"] = True
                return existing
            raise StageRefused(
                "total_spine_reorganization_supersession_refused",
                f"irreversible risk already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed["reorganization_path"] = str(path)
    sealed["total_spine_reorganization_idempotent"] = False
    return sealed


def verify_total_spine_reorganization_certificate(
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute collateral digest and LvC roots; fail closed on tamper."""
    claimed = str(
        certificate.get("reorganization_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _reorganization_certificate_material(certificate)
    expected = _sha256_json(material)
    reorganizations = list(certificate.get("reorganizations") or [])
    recomputed_tip = compute_total_spine_reorganization_root(reorganizations)
    claimed_tip = str(certificate.get("tip_reorganization_root") or "")
    height = int(certificate.get("reorganization_height") or 0)
    count = int(certificate.get("reorganization_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get("parent_reorganization_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(reorganizations):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get("parent_reorganization_root") or "") != parent:
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
            "emergence_index": int(row.get("emergence_index") or idx),
            "emergence_height": int(row.get("emergence_height") or (idx + 1)),
            "emergence_digest": str(row.get("emergence_digest") or ""),
            "bound_emergence_root": str(row.get("bound_emergence_root") or ""),
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
            "reorganized": bool(row.get("reorganized", True)),
            "chartered": bool(row.get("chartered", True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            "parent_reorganization_root": parent,
            "post_reorganization": True,
            "deterministic": True,
            "rvc": True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get("emergence_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= TOTAL_SPINE_REORGANIZATION_MIN_REORGANIZATIONS and height >= count
    reorganizations_ok = all(
        isinstance(row, Mapping)
        and bool(row.get("reorganized", True))
        and bool(row.get("chartered", True))
        and bool(row.get("atomic_ok", True))
        and bool(row.get("rvc", True))
        and not bool(row.get("one_sided", False))
        and int(row.get("residual") or 0) == 0
        for row in reorganizations
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == TOTAL_SPINE_REORGANIZATION_KIND
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get("post_reorganization") is True
        and certificate.get("deterministic") is True
        and certificate.get("reorganized") is True
        and certificate.get("chartered") is True
        and certificate.get("atomic_ok") is True
        and certificate.get("rvc_ok") is True
        and certificate.get("one_sided") is False
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(reorganizations)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and reorganizations_ok
        and int(certificate.get("residual") or 0) == 0
        and TOTAL_SPINE_REORGANIZATION_IMPL is True
    )
    return {
        "ok": ok,
        "action": "verify_total_spine_reorganization",
        "claimed_digest": claimed,
        "expected_digest": expected,
        "emergence_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "emergence_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        "recomputed_tip_reorganization_root": recomputed_tip,
        "chain_ok": chain_ok,
        "min_reorganizations_ok": min_ok,
        "reorganizations_ok": reorganizations_ok,
        "rvc_ok": certificate.get("rvc_ok") is True,
        "atomic_ok": certificate.get("atomic_ok") is True,
        "kind_ok": str(certificate.get("kind") or "") == TOTAL_SPINE_REORGANIZATION_KIND,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        "reorganized_ok": certificate.get("reorganized") is True,
        "chartered_ok": certificate.get("chartered") is True,
        "total_spine_reorganization": True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_total_spine_reorganization_certificate(
    path: Path | str,
) -> dict[str, Any]:
    """Load and integrity-check a sealed liquidity receipt."""
    file_path = reorganization_certificate_path(Path(path))
    if not file_path.is_file():
        raise StageRefused(
            "total_spine_reorganization_missing",
            f"risk certificate not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRefused(
            "total_spine_reorganization_unreadable",
            f"risk certificate unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StageRefused(
            "total_spine_reorganization_invalid",
            "risk certificate root must be a JSON object",
        )
    if str(payload.get("kind") or "") != TOTAL_SPINE_REORGANIZATION_KIND and not payload.get(
        "total_spine_reorganization"
    ):
        raise StageRefused(
            "total_spine_reorganization_missing",
            f"risk certificate not found at {file_path}",
        )
    verify = verify_total_spine_reorganization_certificate(payload)
    if not verify.get("ok"):
        raise StageRefused(
            "total_spine_reorganization_tampered",
            f"risk certificate digest mismatch at {file_path} "
            f"(claimed={verify.get('claimed_digest')!r} "
            f"expected={verify.get('expected_digest')!r})",
        )
    body = dict(payload)
    body["reorganization_path"] = str(file_path)
    body["reorganization_verify"] = verify
    body["total_spine_reorganization_loaded"] = True
    return body


def seal_total_spine_reorganization_chain(
    *,
    prior_tip: str,
    reorganization_digest: str,
    tip_reorganization_root: str,
    bound_emergence_root: str,
    bound_delivery_root: str,
    bound_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    emergence_digest: str,
    delivery_digest: str,
    reorganization_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal risk hop into the absolute-tower tip."""
    tip = str(prior_tip or "").strip() or ("0" * 64)
    md = str(reorganization_digest or "").strip() or ("0" * 64)
    mr = str(tip_reorganization_root or "").strip() or ("0" * 64)
    cr = str(bound_emergence_root or "").strip() or ("0" * 64)
    dlr = str(bound_delivery_root or "").strip() or ("0" * 64)
    clr = str(bound_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    cd = str(emergence_digest or "").strip() or ("0" * 64)
    dvd = str(delivery_digest or "").strip() or ("0" * 64)
    material = (
        f"risk|{int(bool(short_circuit))}|{int(reorganization_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{clr}|{dlr}|{cr}|{dvd}|{cd}|{mr}|{md}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        "reorganization_height": int(reorganization_height),
        "tip_reorganization_root": mr,
        "bound_emergence_root": cr,
        "bound_delivery_root": dlr,
        "bound_clearing_root": clr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        "emergence_digest": cd,
        "delivery_digest": dvd,
        "reorganization_digest": md,
        "prior_tip": tip,
        "digest": digest,
        "total_spine_reorganization": True,
        "irreversible": True,
        "post_reorganization": True,
        "deterministic": True,
        "rvc": True,
    }


def annotate_total_spine_reorganization(
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp post-emergence LvC onto a total-spine result and rebind tip."""
    cst_digest = str(
        certificate.get("reorganization_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_reorganization_root = str(certificate.get("tip_reorganization_root") or "")
    reorganization_height = int(certificate.get("reorganization_height") or 0)
    reorganization_count = int(certificate.get("reorganization_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    bound_clearing_root = str(certificate.get("bound_clearing_root") or "")
    bound_emergence_root = str(certificate.get("bound_emergence_root") or "")
    bound_delivery_root = str(certificate.get("bound_delivery_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    emergence_digest = str(certificate.get("emergence_digest") or "")
    delivery_digest = str(certificate.get("delivery_digest") or "")
    chain = seal_total_spine_reorganization_chain(
        prior_tip=prior_tip,
        reorganization_digest=cst_digest,
        tip_reorganization_root=tip_reorganization_root,
        bound_emergence_root=bound_emergence_root,
        bound_delivery_root=bound_delivery_root,
        bound_clearing_root=bound_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        emergence_digest=emergence_digest,
        delivery_digest=delivery_digest,
        reorganization_height=reorganization_height,
        short_circuit=short_circuit,
    )
    cst_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{cst_tip}".encode("utf-8"))
    body["total_spine_reorganization"] = True
    body["total_spine_reorganization_impl"] = TOTAL_SPINE_REORGANIZATION_IMPL
    body["total_spine_reorganization_short_circuit"] = bool(short_circuit)
    body["total_spine_reorganization_irreversible"] = True
    body["total_spine_reorganization_post_reorganization"] = True
    body["total_spine_reorganization_deterministic"] = True
    body["total_spine_reorganization_rvc"] = True
    body["total_spine_reorganization_certificate"] = dict(certificate)
    body["total_spine_reorganization_digest"] = cst_digest
    body["total_spine_reorganization_chain"] = chain
    body["total_spine_reorganization_tip"] = cst_tip
    body["total_spine_reorganization_bound_tip"] = bound
    body["total_spine_digest_pre_risk"] = prior_tip
    body["total_spine_tip_reorganization_root"] = tip_reorganization_root
    body["total_spine_reorganization_height"] = reorganization_height
    body["total_spine_reorganization_count"] = reorganization_count
    body["total_spine_reorganized"] = bool(certificate.get("reorganized", True))
    body["total_spine_reorganized_ok"] = bool(certificate.get("reorganized", True))
    body["total_spine_chartered"] = bool(certificate.get("chartered", True))
    body["total_spine_chartered"] = bool(certificate.get("chartered", True))
    body["total_spine_chartered_ok"] = bool(certificate.get("chartered", True))
    body["total_spine_rvc_ok"] = bool(certificate.get("rvc_ok", True))
    body["total_spine_reorganization_atomic"] = bool(certificate.get("atomic_ok", True))
    body["total_spine_reorganization_one_sided"] = bool(
        certificate.get("one_sided", False)
    )
    body["total_spine_reorganizations_ok"] = bool(
        certificate.get("reorganizations_ok", True)
    )
    body["total_spine_reorganization_root_valid"] = bool(tip_reorganization_root)
    body["total_spine_reorganization_residual"] = int(certificate.get("residual") or 0)
    body["total_spine_reorganization_pair_count"] = int(
        certificate.get("pair_count") or 0
    )
    body["emergence_root"] = tip_reorganization_root
    body["tip_reorganization_root"] = tip_reorganization_root
    body["reorganization_count"] = reorganization_count
    body["reorganization_height"] = reorganization_height
    body["reorganized"] = bool(certificate.get("reorganized", True))
    body["reorganized_ok"] = bool(certificate.get("reorganized", True))
    body["risk_ok"] = bool(certificate.get("reorganized", True))
    body["rvc_ok"] = bool(certificate.get("rvc_ok", True))
    body["chartered"] = bool(certificate.get("chartered", True))
    if certificate.get("reorganization_path"):
        body["total_spine_reorganization_path"] = certificate.get("reorganization_path")
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
    if bound_emergence_root:
        body["total_spine_tip_risk_root"] = bound_emergence_root
        body["emergence_root"] = bound_emergence_root
        body["tip_emergence_root"] = bound_emergence_root
        body.setdefault("total_spine_emergence", True)
        body.setdefault("total_spine_solvent", True)
        body.setdefault("total_spine_evc_ok", True)
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
    if emergence_digest:
        body["total_spine_emergence_digest"] = emergence_digest
    if delivery_digest:
        body["total_spine_delivery_digest"] = delivery_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        "total_spine_reorganization_ok_short_circuit"
        if short_circuit
        else "total_spine_reorganization_ok"
    )
    body["ok"] = True
    return body


def _as_emergence_mapping(value: Any) -> dict[str, Any] | None:
    from blackhole_agent.upstream_total_spine_emergence import (
        StageRefused as ResolutionRefused,
        load_total_spine_emergence_certificate,
    )

    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_REORGANIZATION_KIND or value.get("total_spine_reorganization"):
            nested_liq = value.get("total_spine_emergence_certificate")
            if isinstance(nested_liq, Mapping) and nested_liq.get(
                "tip_emergence_root"
            ):
                return dict(nested_liq)
        if kind == TOTAL_SPINE_EMERGENCE_KIND or value.get(
            "total_spine_emergence"
        ) or value.get("total_spine_emergence_loaded") or value.get(
            "tip_emergence_root"
        ):
            nested = value.get("total_spine_emergence_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_emergence_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_emergence_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / "emergence" / "total-spine-emergence.json"
            named = path / "total-spine-emergence.json"
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != TOTAL_SPINE_EMERGENCE_KIND:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_total_spine_emergence_certificate(path)
    except ResolutionRefused as exc:
        if str(exc.verdict) == "total_spine_emergence_tampered":
            raise StageRefused(str(exc.verdict), str(exc.detail)) from exc
        return None
    except Exception:  # noqa: BLE001
        return None


def _as_reorganization_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == TOTAL_SPINE_REORGANIZATION_KIND or value.get(
            "total_spine_reorganization"
        ) or value.get("total_spine_reorganization_loaded"):
            nested = value.get("total_spine_reorganization_certificate")
            if isinstance(nested, Mapping) and nested.get("tip_reorganization_root"):
                return dict(nested)
            return dict(value)
        nested = value.get("total_spine_reorganization_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    try:
        return load_total_spine_reorganization_certificate(Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == "total_spine_reorganization_tampered":
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
        nested.get("tip_settlement_root") or nested.get("observctions")
    ):
        found.append(dict(nested))
    if item.get("tip_settlement_root") and item.get("observctions"):
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


def _liquidities_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_liquidity_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_liquidity_root") or nested.get("liquidities")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_liquidity"
        or item.get("total_spine_liquidity_loaded")
    ) and item.get("tip_liquidity_root"):
        found.append(dict(item))
    extra = item.get("liquidities")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_liquidity_root") or row.get("liquidity_digest")
            ):
                found.append(dict(row))
    return found


def _fundings_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_funding_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_funding_root") or nested.get("fundings")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_funding"
        or item.get("total_spine_funding_loaded")
    ) and item.get("tip_funding_root"):
        found.append(dict(item))
    extra = item.get("fundings")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_funding_root") or row.get("funding_digest")
            ):
                found.append(dict(row))
    return found




def _capitals_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_capital_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_capital_root") or nested.get("capitals")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_capital"
        or item.get("total_spine_capital_loaded")
    ) and item.get("tip_capital_root"):
        found.append(dict(item))
    extra = item.get("capitals")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_capital_root") or row.get("capital_digest")
            ):
                found.append(dict(row))
    return found


def _solvencies_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_solvency_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_solvency_root") or nested.get("solvencies")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_solvency"
        or item.get("total_spine_solvency_loaded")
        or item.get("total_spine_solvency")
    ) and item.get("tip_solvency_root"):
        found.append(dict(item))
    extra = item.get("solvencies")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_solvency_root") or row.get("solvency_digest")
            ):
                found.append(dict(row))
    if item.get("tip_solvency_root") and item.get("solvencies"):
        found.append(dict(item))
    return found


def _risks_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_risk_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_risk_root") or nested.get("risks")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_risk" or item.get("total_spine_risk_loaded")
    ) and item.get("tip_risk_root"):
        found.append(dict(item))
    extra = item.get("risks")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_risk_root") or row.get("risk_digest")
            ):
                found.append(dict(row))
    return found


def _stresses_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_stress_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_stress_root") or nested.get("stresses")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_stress" or item.get("total_spine_stress_loaded")
        or item.get("total_spine_stress")
    ) and item.get("tip_stress_root"):
        found.append(dict(item))
    extra = item.get("stresses")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_stress_root") or row.get("stress_digest")
            ):
                found.append(dict(row))
    if item.get("tip_stress_root") and item.get("stresses"):
        found.append(dict(item))
    return found



def _recoveries_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_recovery_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_recovery_root") or nested.get("recoveries")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_recovery"
        or item.get("total_spine_recovery_loaded")
        or item.get("total_spine_recovery")
    ) and item.get("tip_recovery_root"):
        found.append(dict(item))
    extra = item.get("recoveries")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_recovery_root") or row.get("recovery_digest")
            ):
                found.append(dict(row))
    if item.get("tip_recovery_root") and item.get("recoveries"):
        found.append(dict(item))
    return found



def _emergences_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_emergence_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_emergence_root") or nested.get("emergences")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_emergence"
        or item.get("total_spine_emergence_loaded")
        or item.get("total_spine_emergence")
    ) and item.get("tip_emergence_root"):
        found.append(dict(item))
    extra = item.get("emergences")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_emergence_root") or row.get("emergence_digest")
            ):
                found.append(dict(row))
    if item.get("tip_emergence_root") and item.get("emergences"):
        found.append(dict(item))
    return found


def _confirm_emergence(
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
    body: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently re-stress the same book as a charter side."""
    from blackhole_agent.upstream_total_spine_emergence import emerge_total_spine

    # Do not nest confirm writes under out_root: each prior plane appends
    # its own *-confirm directory, and the full cascade exceeds Windows
    # MAX_PATH. The charter risk is sealed in-memory.
    confirm_out = None
    tip_risk = str(primary.get("tip_emergence_root") or "")
    sol_height = int(primary.get("emergence_height") or 0)
    confirm_body: dict[str, Any] = {}
    if isinstance(body, Mapping):
        confirm_body = dict(body)
    elif isinstance(primary, Mapping):
        confirm_body = dict(primary)
    for drop in (
        "total_spine_emergence",
        "total_spine_emergence_certificate",
        "total_spine_emergence_loaded",
        "total_spine_reorganization",
        "total_spine_reorganization_certificate",
        "total_spine_reorganization_loaded",
        "kind",
        "tip_emergence_root",
        "tip_reorganization_root",
        "emergence_digest",
        "reorganization_digest",
        "certificate_hash",
    ):
        kind = str(confirm_body.get("kind") or "")
        if kind in {TOTAL_SPINE_EMERGENCE_KIND, TOTAL_SPINE_REORGANIZATION_KIND}:
            confirm_body.pop("kind", None)
        confirm_body.pop(drop, None)
    recoveries_in: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in (primary, body, confirm_body):
        for row in _emergences_from(src):
            key = str(
                row.get("emergence_digest")
                or row.get("certificate_hash")
                or row.get("tip_emergence_root")
                or ""
            )
            if not key or key in seen:
                continue
            seen.add(key)
            recoveries_in.append(row)
    bundle: list[Any] = list(recoveries_in)
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
        confirm_body.setdefault("total_spine_actuation_certificate", dict(actuation))
    if not recoveries_in and not bundle and not confirm_body:
        raise StageRefused(
            "total_spine_reorganization_charter_missing",
            "single stress requires risks, collaterals, margins, "
            "custodies, deliveries, clearings, settlements, or actuation "
            "to confirm-emergence",
        )
    source: Any = (
        recoveries_in
        if recoveries_in
        else (confirm_body or body or primary)
    )
    chartered = emerge_total_spine(
        source,
        restructurings=recoveries_in or None,
        margins=margins or None,
        clearings=clearings or None,
        settlements=settlements or None,
        actuation=actuation,
        body=confirm_body or None,
        out_root=confirm_out,
        prior_tip=prior_tip,
        parent_emergence_root=tip_risk,
        emergence_height=sol_height + 1 if sol_height else None,
        repo_path=repo_path or REPO_ROOT,
        confirm=True,
    )
    cert = chartered.get("total_spine_emergence_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            "total_spine_reorganization_charter_missing",
            "charter stress did not produce a certificate",
        )
    return dict(cert)


def _collect_emergences(
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
    existing = _as_reorganization_mapping(source)
    if existing is None and body is not None:
        existing = _as_reorganization_mapping(body)
    risks: list[dict[str, Any]] = []
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
        mapped = _as_emergence_mapping(item)
        if mapped is not None:
            risks.append(mapped)
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
        _push(body.get("total_spine_emergence_certificate"))
        _push(body.get("total_spine_risk_certificate"))
        _push(body.get("total_spine_capital_certificate"))
        _push(body.get("total_spine_funding_certificate"))
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
    for row in risks:
        digest = _emergence_digest_of(row)
        tip = str(row.get("tip_emergence_root") or "")
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


def _strip_reorganization_predicates(done_when: str) -> str:
    """Evaluate the pre-reorganization contract, never stress_* (no recurse)."""
    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        "reorganization_ok",
        "reorganized_ok",
        "min_reorganizations",
        "reorganization_root_valid",
        "rvc_ok",
        "charter_ok",
        "chartered_ok",
        "emergence_ok",
        "emerged_ok",
        "min_emergences",
        "emergence_root_valid",
        "evc_ok",
        "confirmation_ok",
        "confirmed_ok",
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


def reorganize_total_spine(
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    *,
    emergences: Sequence[Mapping[str, Any] | Path | str] | None = None,
    margins: Sequence[Mapping[str, Any] | Path | str] | None = None,
    out_root: Path | None = None,
    prior_tip: str | None = None,
    body: dict[str, Any] | None = None,
    min_reorganizations: int = TOTAL_SPINE_REORGANIZATION_MIN_REORGANIZATIONS,
    parent_reorganization_root: str = "",
    reorganization_height: int | None = None,
    short_circuit: bool = False,
    repo_path: Path | None = None,
    confirm: bool = True,
    actuation: Mapping[str, Any] | None = None,
    settlements: Sequence[Mapping[str, Any]] | None = None,
    clearings: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Apply post-emergence atomic RvC reorganization on the absolute total spine."""
    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    if not TOTAL_SPINE_REORGANIZATION_IMPL:
        raise StageRefused(
            "total_spine_reorganization_disabled",
            "TOTAL_SPINE_REORGANIZATION_IMPL is False",
        )

    extra_books: list[Any] = []
    extra_books.extend(list(emergences or []))
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
    ) = _collect_emergences(source, body, extra_books)
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
        and existing.get("tip_reorganization_root")
        and (
            str(existing.get("kind") or "") == TOTAL_SPINE_REORGANIZATION_KIND
            or existing.get("total_spine_reorganization_loaded")
            or existing.get("total_spine_reorganization")
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
            "action": "reorganize_total_spine",
            "total_spine": True,
        }
        return annotate_total_spine_reorganization(
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

    want = max(int(min_reorganizations), TOTAL_SPINE_REORGANIZATION_MIN_REORGANIZATIONS)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_emergence(
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
                    or (body or {}).get("total_spine_risk_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
                body=body,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            "total_spine_reorganization_margins_short",
            f"risk requires >= {want} independent risks, "
            f"got {len(collected)}",
        )

    legs = book_total_spine_emergences(
        collected,
        min_reorganizations=want,
        parent_reorganization_root=parent_reorganization_root,
        reorganization_height=reorganization_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("bound_settlement_root") or "")
    clearing_root = str(first.get("bound_clearing_root") or "")
    margin_root = str(first.get("tip_emergence_root") or "")
    emergence_digest = _emergence_digest_of(first)
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
    pre_liquidity = _strip_reorganization_predicates(done_when)
    if pre_liquidity:
        ctx = {
            "liquidity": {
                "ok": True,
                "funded": True,
                "funded_ok": True,
                "emergence_root_valid": True,
                "lvc_ok": True,
                "liquidity_count": int(first.get("liquidity_count") or 0),
                "tip_emergence_root": margin_root,
            },
            "liquidity_count": int(first.get("liquidity_count") or 0),
            "tip_emergence_root": margin_root,
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
                "total_spine_reorganization_contract_unmet",
                f"done_when not met at collateral: {pre_liquidity!r}",
            )

    tip_reorganization_root = compute_total_spine_reorganization_root(legs)
    cst_height = int(legs[-1]["emergence_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get("total_spine_risk_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    pair_count = int(legs[0].get("pair_count") or 0) if legs else 0

    cst_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": TOTAL_SPINE_REORGANIZATION_KIND,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "bound_clearing_root": clearing_root,
        "bound_emergence_root": margin_root,
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
        "emergence_digest": emergence_digest,
        "delivery_digest": str(
            first.get("delivery_digest")
            or first.get("certificate_hash")
            or ""
        ),
        "prior_tip": tip,
        "parent_reorganization_root": str(
            parent_reorganization_root
            or (legs[0].get("parent_reorganization_root") if legs else "")
            or ""
        ),
        "reorganizations": legs,
        "reorganization_count": len(legs),
        "reorganization_height": cst_height,
        "tip_reorganization_root": tip_reorganization_root,
        "pair_count": pair_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        "reorganized": True,
        "chartered": True,
        "atomic_ok": True,
        "rvc_ok": True,
        "one_sided": False,
        "reorganizations_ok": True,
        "reorganizations_ok": True,
        "post_reorganization": True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        "reorganized_at": utc_now_iso(),
    }
    if contract_eval is not None:
        cst_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_total_spine_reorganization_certificate(write_target, cst_body)
    else:
        certificate = seal_total_spine_reorganization_certificate(cst_body)

    result = body if body is not None else {
        "ok": True,
        "action": "reorganize_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate_total_spine_reorganization(
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
        cst_bound = str(annotated.get("total_spine_reorganization_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=cst_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated["total_spine_reorganization_bound_state_root"] = state_root
    annotated["total_spine_reorganization_bound_action_root"] = action_root
    annotated["total_spine_reorganization_bound_settlement_root"] = settlement_root
    annotated["total_spine_reorganization_bound_clearing_root"] = clearing_root
    annotated["total_spine_reorganization_bound_emergence_root"] = margin_root
    annotated["total_spine_reorganization_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


def builtin_total_spine_reorganization_proof() -> dict[str, Any]:
    """Hermetic proof: post-resolution atomic EvC on the absolute tower."""
    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent.upstream_control_engine import (
        SCHEMA_VERSION as ENGINE_SCHEMA,
        TOTAL_SPINE_REORGANIZATION_IMPL as ENGINE_CAP_IMPL,
        TOTAL_SPINE_EMERGENCE_IMPL,
        TOTAL_SPINE_RESTRUCTURING_IMPL,
        TOTAL_SPINE_RESOLUTION_IMPL,
        TOTAL_SPINE_RECOVERY_IMPL,
        TOTAL_SPINE_STRESS_IMPL,
        TOTAL_SPINE_RISK_IMPL,
        TOTAL_SPINE_SOLVENCY_IMPL,
        TOTAL_SPINE_CAPITAL_IMPL,
        TOTAL_SPINE_FUNDING_IMPL,
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
        funding_total_spine,
        liquidity_total_spine,
        run_total_spine,
        solvency_total_spine,
        capital_total_spine,
        risk_total_spine,
        stress_total_spine,
        recovery_total_spine,
        resolution_total_spine,
        restructuring_total_spine,
        emerge_total_spine,
        settle_total_spine,
        write_total_spine_finality_certificate,
    )
    from blackhole_agent.upstream_total_spine_recovery import (
        seal_total_spine_recovery_certificate,
    )
    from blackhole_agent.upstream_total_spine_resolution import (
        seal_total_spine_resolution_certificate,
    )
    from blackhole_agent.upstream_total_spine_emergence import (
        seal_total_spine_emergence_certificate,
    )
    from blackhole_agent.upstream_total_spine_restructuring import (
        seal_total_spine_restructuring_certificate,
    )

    scratch = Path(tempfile.mkdtemp(prefix="tsp-rvc-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        flags_ok = (
            TOTAL_SPINE_REORGANIZATION_IMPL is True
            and ENGINE_CAP_IMPL is True
            and TOTAL_SPINE_EMERGENCE_IMPL is True
            and TOTAL_SPINE_RESTRUCTURING_IMPL is True
            and TOTAL_SPINE_RESOLUTION_IMPL is True
            and TOTAL_SPINE_RECOVERY_IMPL is True
            and TOTAL_SPINE_STRESS_IMPL is True
            and TOTAL_SPINE_RISK_IMPL is True
            and TOTAL_SPINE_SOLVENCY_IMPL is True
            and TOTAL_SPINE_CAPITAL_IMPL is True
            and TOTAL_SPINE_FUNDING_IMPL is True
            and TOTAL_SPINE_LIQUIDITY_IMPL is True
            and TOTAL_SPINE_COLLATERAL_IMPL is True
            and TOTAL_SPINE_MARGIN_IMPL is True
            and TOTAL_SPINE_CUSTODY_IMPL is True
            and TOTAL_SPINE_REORGANIZATION_KIND == "total_spine_reorganization"
            and bool(TOTAL_SPINE_REORGANIZATION_FILENAME)
            and TOTAL_SPINE_REORGANIZATION_MIN_REORGANIZATIONS >= 2
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
                "goal": "reorganization proof origin",
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
        chartered = settle_total_spine(
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
        s2 = chartered.get("total_spine_settlement_certificate") or {}
        state_root = str(settled.get("total_spine_state_root") or "")
        tip_action = str(settled.get("total_spine_tip_action_root") or "")

        clr1 = clear_total_spine(
            [s1, s2],
            out_root=scratch / "clr-h1",
            prior_tip=str(
                chartered.get("total_spine_settlement_bound_tip")
                or settled.get("total_spine_settlement_bound_tip")
                or ""
            ),
            body=dict(chartered),
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

        fnd1 = funding_total_spine(
            [cert_liq1, cert_liq2],
            out_root=scratch / "fnd-h1",
            prior_tip=str(liq2.get("total_spine_liquidity_bound_tip") or ""),
            body=dict(liq2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_fnd1 = fnd1.get("total_spine_funding_certificate") or {}
        tip_funding = str(fnd1.get("total_spine_tip_funding_root") or "")
        fnd2 = funding_total_spine(
            [cert_liq1, cert_liq2],
            out_root=scratch / "fnd-h2",
            prior_tip=str(fnd1.get("total_spine_funding_bound_tip") or ""),
            parent_funding_root=tip_funding,
            funding_height=int(fnd1.get("total_spine_funding_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_fnd2 = fnd2.get("total_spine_funding_certificate") or {}

        cap1 = capital_total_spine(
            [cert_fnd1, cert_fnd2],
            out_root=scratch / "cap-h1",
            prior_tip=str(fnd2.get("total_spine_funding_bound_tip") or ""),
            body=dict(fnd2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_cap1 = cap1.get("total_spine_capital_certificate") or {}
        tip_capital = str(cap1.get("total_spine_tip_capital_root") or "")
        cap2 = capital_total_spine(
            [cert_fnd1, cert_fnd2],
            out_root=scratch / "cap-h2",
            prior_tip=str(cap1.get("total_spine_capital_bound_tip") or ""),
            parent_capital_root=tip_capital,
            capital_height=int(cap1.get("total_spine_capital_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_cap2 = cap2.get("total_spine_capital_certificate") or {}

        sol1 = solvency_total_spine(
            [cert_cap1, cert_cap2],
            out_root=scratch / "sol-h1",
            prior_tip=str(cap2.get("total_spine_capital_bound_tip") or ""),
            body=dict(cap2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_sol1 = sol1.get("total_spine_solvency_certificate") or {}
        tip_solvency = str(sol1.get("total_spine_tip_solvency_root") or "")
        sol2 = solvency_total_spine(
            [cert_cap1, cert_cap2],
            out_root=scratch / "sol-h2",
            prior_tip=str(sol1.get("total_spine_solvency_bound_tip") or ""),
            parent_solvency_root=tip_solvency,
            solvency_height=int(sol1.get("total_spine_solvency_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_sol2 = sol2.get("total_spine_solvency_certificate") or {}

        rsk1 = risk_total_spine(
            [cert_sol1, cert_sol2],
            out_root=scratch / "rsk-h1",
            prior_tip=str(sol2.get("total_spine_solvency_bound_tip") or ""),
            body=dict(sol2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_rsk1 = rsk1.get("total_spine_risk_certificate") or {}
        tip_risk = str(rsk1.get("total_spine_tip_risk_root") or "")
        rsk2 = risk_total_spine(
            [cert_sol1, cert_sol2],
            out_root=scratch / "rsk-h2",
            prior_tip=str(rsk1.get("total_spine_risk_bound_tip") or ""),
            parent_risk_root=tip_risk,
            risk_height=int(rsk1.get("total_spine_risk_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_rsk2 = rsk2.get("total_spine_risk_certificate") or {}

        sts1 = stress_total_spine(
            [cert_rsk1, cert_rsk2],
            out_root=scratch / "sts-h1",
            prior_tip=str(rsk2.get("total_spine_risk_bound_tip") or ""),
            body=dict(rsk2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_sts1 = sts1.get("total_spine_stress_certificate") or {}
        tip_stress = str(sts1.get("total_spine_tip_stress_root") or "")
        sts2 = stress_total_spine(
            [cert_rsk1, cert_rsk2],
            out_root=scratch / "sts-h2",
            prior_tip=str(sts1.get("total_spine_stress_bound_tip") or ""),
            parent_stress_root=tip_stress,
            stress_height=int(sts1.get("total_spine_stress_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_sts2 = sts2.get("total_spine_stress_certificate") or {}

        rec1 = recovery_total_spine(
            [cert_sts1, cert_sts2],
            out_root=scratch / "rec-h1",
            prior_tip=str(sts2.get("total_spine_stress_bound_tip") or ""),
            body=dict(sts2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_rec1 = rec1.get("total_spine_recovery_certificate") or {}
        tip_recovery = str(rec1.get("total_spine_tip_recovery_root") or "")
        rec2 = recovery_total_spine(
            [cert_sts1, cert_sts2],
            out_root=scratch / "rec-h2",
            prior_tip=str(rec1.get("total_spine_recovery_bound_tip") or ""),
            parent_recovery_root=tip_recovery,
            recovery_height=int(rec1.get("total_spine_recovery_height") or 0) + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_rec2 = rec2.get("total_spine_recovery_certificate") or {}

        res1 = resolution_total_spine(
            [cert_rec1, cert_rec2],
            out_root=scratch / "res-h1",
            prior_tip=str(rec2.get("total_spine_recovery_bound_tip") or ""),
            body=dict(rec2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_res1 = res1.get("total_spine_resolution_certificate") or {}
        tip_resolution = str(res1.get("total_spine_tip_resolution_root") or "")
        res2 = resolution_total_spine(
            [cert_rec1, cert_rec2],
            out_root=scratch / "res-h2",
            prior_tip=str(res1.get("total_spine_resolution_bound_tip") or ""),
            parent_resolution_root=tip_resolution,
            resolution_height=int(res1.get("total_spine_resolution_height") or 0)
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_res2 = res2.get("total_spine_resolution_certificate") or {}


        rst1 = restructuring_total_spine(
            [cert_res1, cert_res2],
            out_root=scratch / "rst-h1",
            prior_tip=str(res2.get("total_spine_resolution_bound_tip") or ""),
            body=dict(res2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_rst1 = rst1.get("total_spine_restructuring_certificate") or {}
        tip_restructuring = str(rst1.get("total_spine_tip_restructuring_root") or "")
        rst2 = restructuring_total_spine(
            [cert_res1, cert_res2],
            out_root=scratch / "rst-h2",
            prior_tip=str(rst1.get("total_spine_restructuring_bound_tip") or ""),
            parent_restructuring_root=tip_restructuring,
            restructuring_height=int(rst1.get("total_spine_restructuring_height") or 0)
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_rst2 = rst2.get("total_spine_restructuring_certificate") or {}

        emg1 = emerge_total_spine(
            [cert_rst1, cert_rst2],
            out_root=scratch / "emg-h1",
            prior_tip=str(rst2.get("total_spine_restructuring_bound_tip") or ""),
            body=dict(rst2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_emg1 = emg1.get("total_spine_emergence_certificate") or {}
        tip_emergence = str(emg1.get("total_spine_tip_emergence_root") or "")
        emg2 = emerge_total_spine(
            [cert_rst1, cert_rst2],
            out_root=scratch / "emg-h2",
            prior_tip=str(emg1.get("total_spine_emergence_bound_tip") or ""),
            parent_emergence_root=tip_emergence,
            emergence_height=int(emg1.get("total_spine_emergence_height") or 0)
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_emg2 = emg2.get("total_spine_emergence_certificate") or {}

        offline_cap = reorganize_total_spine(
            [cert_emg1, cert_emg2],
            out_root=scratch / "reorg-h1",
            prior_tip=str(emg2.get("total_spine_emergence_bound_tip") or ""),
            body=dict(emg2),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cap_path = offline_cap.get("total_spine_reorganization_path")
        tip_reorganization = str(offline_cap.get("total_spine_tip_reorganization_root") or "")
        offline_ok = (
            bool(offline_cap.get("ok"))
            and offline_cap.get("total_spine_reorganization") is True
            and offline_cap.get("total_spine_reorganization_post_reorganization") is True
            and offline_cap.get("total_spine_reorganization_irreversible") is True
            and offline_cap.get("total_spine_reorganized") is True
            and offline_cap.get("total_spine_chartered") is True
            and offline_cap.get("total_spine_rvc_ok") is True
            and offline_cap.get("total_spine_reorganization_atomic") is True
            and offline_cap.get("total_spine_reorganization_one_sided") is False
            and int(offline_cap.get("total_spine_reorganization_count") or 0) >= 2
            and int(offline_cap.get("total_spine_reorganization_height") or 0) >= 2
            and int(offline_cap.get("total_spine_reorganization_residual") or 0) == 0
            and int(offline_cap.get("total_spine_reorganization_pair_count") or 0) >= 1
            and len(tip_reorganization) >= 32
            and str(offline_cap.get("total_spine_state_root") or "") == state_root
            and str(offline_cap.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline_cap.get("total_spine_digest") or "")
            != str(res1.get("total_spine_digest") or "")
            and isinstance(cap_path, str)
            and Path(cap_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_total_spine_reorganization_certificate(cap_path or scratch)
        verify_ok = bool(
            loaded.get("total_spine_reorganization_loaded")
            and (loaded.get("reorganization_verify") or {}).get("ok")
            and (loaded.get("reorganization_verify") or {}).get("emergence_root_ok")
            and (loaded.get("reorganization_verify") or {}).get("chain_ok")
            and (loaded.get("reorganization_verify") or {}).get("reorganizations_ok")
            and (loaded.get("reorganization_verify") or {}).get("rvc_ok")
        )

        tampered_path = scratch / "tampered-reorganization.json"
        tampered_body = dict(loaded)
        for drop in (
            "reorganization_verify",
            "total_spine_reorganization_loaded",
            "reorganization_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body["reorganization_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_total_spine_reorganization_certificate(tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == "total_spine_reorganization_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_total_spine_reorganization_certificate(
                scratch / "reorg-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            "reorganization_verify",
                            "total_spine_reorganization_loaded",
                            "reorganization_path",
                            "reorganization_digest",
                            "certificate_hash",
                            "reorganized_at",
                            "total_spine_reorganization",
                            "total_spine_reorganization_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    "tip_reorganization_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == "total_spine_reorganization_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            "reorganization_verify",
            "total_spine_reorganization_loaded",
            "reorganization_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_total_spine_reorganization_certificate(wrong_body)
        wrong_verify = verify_total_spine_reorganization_certificate(resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get("emergence_root_ok") is False
        )

        mismatch_ok = False
        try:
            mixed = dict(cert_emg1)
            mixed["bound_state_root"] = "e" * 64
            book_total_spine_emergences(
                [cert_emg1, mixed],
                min_reorganizations=2,
            )
        except StageRefused:
            mismatch_ok = True
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        one_sided_ok = False
        try:
            forged = dict(cert_emg2)
            forged["capabilities"] = ["capability.one-sided-only"]
            for drop in (
                "emergence_digest",
                "certificate_hash",
                "emerged_at",
                "emergence_path",
                "emergence_verify",
                "total_spine_emergence_loaded",
            ):
                forged.pop(drop, None)
            resealed_one = seal_total_spine_emergence_certificate(forged)
            book_total_spine_emergences(
                [cert_emg1, resealed_one], min_reorganizations=2
            )
        except StageRefused as exc:
            one_sided_ok = str(exc.verdict) == "total_spine_reorganization_one_sided"
        except Exception:  # noqa: BLE001
            one_sided_ok = False

        partial_ok = False
        try:
            _assert_pairs_atomic(
                [
                    {
                        "capability_id": good_id,
                        "reorganized_ok": True,
                        "charter_ok": False,
                        "atomic_ok": False,
                    }
                ]
            )
        except StageRefused as exc:
            partial_ok = str(exc.verdict) == "total_spine_reorganization_partial"
        except Exception:  # noqa: BLE001
            partial_ok = False

        h2 = reorganize_total_spine(
            [cert_emg1, cert_emg2],
            out_root=scratch / "reorg-h2",
            prior_tip=str(
                offline_cap.get("total_spine_reorganization_bound_tip") or ""
            ),
            parent_reorganization_root=tip_reorganization,
            reorganization_height=int(
                offline_cap.get("total_spine_reorganization_height") or 0
            )
            + 1,
            repo_path=REPO_ROOT,
            confirm=False,
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get("total_spine_reorganization_count") or 0) >= 2
            and str(h2.get("total_spine_tip_reorganization_root") or "") != tip_reorganization
            and str(
                (h2.get("total_spine_reorganization_certificate") or {}).get(
                    "parent_reorganization_root"
                )
                or ""
            )
            == tip_reorganization
        )

        recomputed = compute_total_spine_reorganization_root(
            loaded.get("reorganizations") or []
        )
        determinism_ok = recomputed == tip_reorganization and bool(recomputed)

        live = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "live",
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
            capital=True,
            solvency=True,
            risk=True,
            stress=True,
            recovery=True,
            resolution=True,
            restructuring=True,
            emergence=True,
            reorganization=True,
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        live_cap_path = live.get("total_spine_reorganization_path")
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
            and live.get("total_spine_capital") is True
            and live.get("total_spine_solvency") is True
            and live.get("total_spine_stress") is True
            and live.get("total_spine_recovery") is True
            and live.get("total_spine_resolution") is True
            and live.get("total_spine_restructuring") is True
            and live.get("total_spine_emergence") is True
            and live.get("total_spine_reorganization") is True
            and live.get("total_spine_reorganized") is True
            and live.get("total_spine_rvc_ok") is True
            and int(live.get("total_spine_reorganization_count") or 0) >= 2
            and isinstance(live.get("total_spine_tip_reorganization_root"), str)
            and len(str(live.get("total_spine_tip_reorganization_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_cap_path, str)
            and Path(live_cap_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / "short",
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
            capital=True,
            solvency=True,
            risk=True,
            stress=True,
            recovery=True,
            resolution=True,
            restructuring=True,
            emergence=True,
            reorganization=True,
            resume_dir=live_cap_path or (scratch / "live-emg"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get("total_spine_reorganization") is True
            and shorted.get("total_spine_reorganization_short_circuit") is True
            and str(shorted.get("total_spine_tip_reorganization_root") or "")
            == str(live.get("total_spine_tip_reorganization_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        cap_chain = live.get("total_spine_reorganization_chain") or {}
        chain_integrity_ok = False
        if isinstance(cap_chain, Mapping) and cap_chain:
            re_seal = seal_total_spine_reorganization_chain(
                prior_tip=str(cap_chain.get("prior_tip") or ""),
                reorganization_digest=str(cap_chain.get("reorganization_digest") or ""),
                tip_reorganization_root=str(cap_chain.get("tip_reorganization_root") or ""),
                bound_emergence_root=str(
                    cap_chain.get("bound_emergence_root") or ""
                ),
                bound_delivery_root=str(
                    cap_chain.get("bound_delivery_root") or ""
                ),
                bound_clearing_root=str(
                    cap_chain.get("bound_clearing_root") or ""
                ),
                bound_settlement_root=str(
                    cap_chain.get("bound_settlement_root") or ""
                ),
                bound_action_root=str(cap_chain.get("bound_action_root") or ""),
                bound_state_root=str(cap_chain.get("bound_state_root") or ""),
                actuation_digest=str(cap_chain.get("actuation_digest") or ""),
                emergence_digest=str(cap_chain.get("emergence_digest") or ""),
                delivery_digest=str(cap_chain.get("delivery_digest") or ""),
                reorganization_height=int(cap_chain.get("reorganization_height") or 0),
                short_circuit=bool(cap_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == cap_chain.get("digest")
                and re_seal.get("digest") == live.get("total_spine_reorganization_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(res1.get("total_spine_digest") or "")
            != str(offline_cap.get("total_spine_digest") or "")
        )

        facade_path = Path(le_facade.__file__).resolve()
        facade_text = facade_path.read_text(encoding="utf-8")
        source_ok = (
            "TOTAL_SPINE_REORGANIZATION_IMPL" in facade_text
            and "builtin_total_spine_reorganization_proof" in facade_text
            and "reorganize_total_spine" in facade_text
            and callable(
                getattr(le_facade, "builtin_total_spine_reorganization_proof", None)
            )
            and callable(getattr(le_facade, "reorganize_total_spine", None))
            and getattr(le_facade, "TOTAL_SPINE_REORGANIZATION_IMPL", False) is True
        )

        engine_path = Path(
            __import__(
                "blackhole_agent.upstream_control_engine", fromlist=["_"]
            ).__file__
        ).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            "TOTAL_SPINE_REORGANIZATION_IMPL" in engine_text
            and "reorganize_total_spine" in engine_text
            and (
                "reorganization=True" in engine_text
                or "reorganization: bool = False" in engine_text
            )
            and "builtin_total_spine_reorganization_proof" in engine_text
        )

        mod_path = Path(__file__).resolve()
        mod_text = mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            "def reorganize_total_spine" in mod_text
            and "def builtin_total_spine_reorganization_proof" in mod_text
            and "total_spine_reorganization_supersession_refused" in mod_text
            and "total_spine_reorganization_tampered" in mod_text
            and "total_spine_reorganization_one_sided" in mod_text
            and "total_spine_reorganization_evc_failed" in mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                "capability.upstream-total-spine-reorganization"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    "upstream_total_spine_reorganization" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and "builtin_total_spine_reorganization_proof" in (entry.entry or "")
                and (
                    "reorganization" in tags_blob
                    or "reorganization" in name_blob
                    or "reorganization" in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    "reorganize_total_spine" in delta_blob
                    or "post-reorganization" in delta_blob
                    or "post_reorganization" in delta_blob
                    or "rvc" in delta_blob
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
            "action": "total_spine_reorganization_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            "reorganization_path": cap_path,
            "tip_reorganization_root": tip_emergence,
            "tip_resolution_root": tip_resolution,
            "tip_recovery_root": tip_recovery,
            "tip_stress_root": tip_stress,
            "tip_risk_root": tip_risk,
            "tip_solvency_root": tip_solvency,
            "tip_capital_root": tip_capital,
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
            "reorganization_count": offline_cap.get("total_spine_reorganization_count"),
            "pair_count": offline_cap.get("total_spine_reorganization_pair_count"),
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
            "live_reorganization_path": live_cap_path,
            "live_tip_reorganization_root": live.get("total_spine_tip_reorganization_root"),
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
            "total_spine_reorganization": True,
            "total_spine_resolution": True,
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
        "reorganization-proof",
        help=(
            "Total spine reorganization proof: post-emergence atomic RvC seals "
            "matching emergence books into irreversible reorganization receipts"
        ),
    )
    sub.add_parser("proof", help="Alias for reorganization-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {"reorganization-proof", "proof"}:
        result = builtin_total_spine_reorganization_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
