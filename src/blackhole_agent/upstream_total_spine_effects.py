"""Total-spine pair-effect engine: 15 generated modules collapse into data + one logic core.

Every ``upstream_total_spine_<effect>`` module from delivery through
reorganization was a mechanically generated copy of the same pair-booking
logic: confirm a second predecessor book, pair it with this effect's
requirement, seal a hash-chained irreversible certificate, rebind the tip.
The only real differences are per-effect tokens (nouns, pair codes, verdict
fields, adjectives, refusal-kind suffixes, and a few historical residue
strings). Those now live in :data:`PAIR_EFFECT_SPECS`; the logic lives here
once.

Synthesized modules keep the historical import paths
(``blackhole_agent.upstream_total_spine_<effect>``) and their exact public
names and signatures — a meta-path finder installed from the package
``__init__`` materializes them on demand, and ``python -m
blackhole_agent.upstream_total_spine_<effect>`` keeps working through the
loader's ``get_code``. Per-effect historical quirks (e.g. a ``post_risk``
key where the chain pattern expects ``post_solvency``) are carried verbatim
in the spec so sealed digests are unchanged. No skill-route discovery.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
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

TOTAL_SPINE_DEFAULT_ROOT: str = "quettacontinuum"


@dataclass(frozen=True)
class PairEffectSpec:
    """Every per-effect token the generated modules differed by."""

    effect: str  # solvency
    plural: str  # solvencies
    verb: str  # solvency (runner name: <verb>_total_spine)
    pred: str  # capital
    pred_plural: str  # capitals
    code: str  # svr
    code_upper: str  # SvR
    pred_code: str  # cva
    pred_code_upper: str  # CvA
    verdict_1: str  # surplus_ok
    verdict_2: str  # solvency_requirement_ok
    adj_1: str  # solvent
    adj_2: str  # required
    adj_1_negated: str  # insolvent
    counterpart: str  # requirement
    pred_done: str  # capitalized
    pred_verdict_1: str  # adequate
    pred_verdict_2: str  # cva_ok
    post_key: str  # post_capital (quirk: risk uses post_risk)
    min_name: str  # SOLVENCIES (TOTAL_SPINE_<E>_MIN_<MIN_NAME>)
    # Body certificate push order in _collect (chain nouns, historical order).
    collect_push: tuple[str, ...]  # ("capital","funding","collateral","margin","custody","delivery")
    abbr: str  # sol (proof scratch dir prefix)
    # Refusal-kind suffixes as historically generated (residue preserved):
    refusal_pred_tampered: str  # margin_tampered
    refusal_pred_partial: str  # margin_partial
    refusal_pred_short: str  # margins_short
    refusal_pred_not_done: str  # capital_uncapitalized
    refusal_pred_unmet: str  # capital_unrequired
    refusal_code_failed: str  # cva_failed
    summary: str  # one-line module summary (CLI description)
    out_extra_flags: tuple[str, ...] = ()  # extra total_spine_* booleans in proof output
    # Exact historical def-signature texts (params + return) per public name,
    # so synthesized modules reproduce the original API surface byte-for-byte.
    signatures: dict[str, str] | None = None

    @property
    def upper(self) -> str:
        return self.effect.upper()

    @property
    def pred_upper(self) -> str:
        return self.pred.upper()

    @property
    def kind(self) -> str:
        return f"total_spine_{self.effect}"

    @property
    def pred_kind(self) -> str:
        return f"total_spine_{self.pred}"

    @property
    def filename(self) -> str:
        return f"total-spine-{self.effect}.json"

    @property
    def min_value(self) -> int:
        return 2


PAIR_EFFECT_SPECS: dict[str, PairEffectSpec] = {}


def _register(spec: PairEffectSpec) -> None:
    PAIR_EFFECT_SPECS[spec.effect] = spec


_register(
    PairEffectSpec(
        effect="solvency",
        plural="solvencies",
        verb="solvency",
        pred="capital",
        pred_plural="capitals",
        code="svr",
        code_upper="SvR",
        pred_code="cva",
        pred_code_upper="CvA",
        verdict_1="surplus_ok",
        verdict_2="solvency_requirement_ok",
        adj_1="solvent",
        adj_2="required",
        adj_1_negated="insolvent",
        counterpart="requirement",
        pred_done="capitalized",
        pred_verdict_1="adequate",
        pred_verdict_2="cva_ok",
        post_key="post_capital",
        min_name="SOLVENCIES",
        collect_push=("capital", "funding", "collateral", "margin", "custody", "delivery"),
        abbr="sol",
        signatures={
            'annotate_total_spine_solvency': '(\n    body: dict[str, Any],\n    *,\n    certificate: Mapping[str, Any],\n    prior_tip: str,\n    short_circuit: bool = False,\n) -> dict[str, Any]',
            'book_total_spine_capitals': '(\n    margins: Sequence[Mapping[str, Any]],\n    *,\n    min_solvencies: int = TOTAL_SPINE_SOLVENCY_MIN_SOLVENCIES,\n    parent_solvency_root: str = "",\n    solvency_height: int | None = None,\n) -> list[dict[str, Any]]',
            'builtin_total_spine_solvency_proof': '() -> dict[str, Any]',
            'compute_total_spine_solvency_root': '(\n    capitals: Sequence[Mapping[str, Any]],\n) -> str',
            'load_total_spine_solvency_certificate': '(\n    path: Path | str,\n) -> dict[str, Any]',
            'seal_total_spine_solvency_certificate': '(\n    body: Mapping[str, Any],\n) -> dict[str, Any]',
            'seal_total_spine_solvency_chain': '(\n    *,\n    prior_tip: str,\n    solvency_digest: str,\n    tip_solvency_root: str,\n    bound_capital_root: str,\n    bound_delivery_root: str,\n    bound_clearing_root: str,\n    bound_settlement_root: str,\n    bound_action_root: str,\n    bound_state_root: str,\n    actuation_digest: str,\n    capital_digest: str,\n    delivery_digest: str,\n    solvency_height: int,\n    short_circuit: bool = False,\n) -> dict[str, Any]',
            'verify_total_spine_solvency_certificate': '(\n    certificate: Mapping[str, Any],\n) -> dict[str, Any]',
            'write_total_spine_solvency_certificate': '(\n    out_root: Path,\n    body: Mapping[str, Any],\n    *,\n    allow_idempotent: bool = True,\n) -> dict[str, Any]',
            'solvency_total_spine': '(\n    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,\n    *,\n    capitals: Sequence[Mapping[str, Any] | Path | str] | None = None,\n    margins: Sequence[Mapping[str, Any] | Path | str] | None = None,\n    out_root: Path | None = None,\n    prior_tip: str | None = None,\n    body: dict[str, Any] | None = None,\n    min_solvencies: int = TOTAL_SPINE_SOLVENCY_MIN_SOLVENCIES,\n    parent_solvency_root: str = "",\n    solvency_height: int | None = None,\n    short_circuit: bool = False,\n    repo_path: Path | None = None,\n    confirm: bool = True,\n    actuation: Mapping[str, Any] | None = None,\n    settlements: Sequence[Mapping[str, Any]] | None = None,\n    clearings: Sequence[Mapping[str, Any]] | None = None,\n) -> dict[str, Any]',
            'solvency_certificate_path': '(root: Path) -> Path',
            'main': '(argv: Sequence[str] | None = None) -> int',
        },
        refusal_pred_tampered="margin_tampered",
        refusal_pred_partial="margin_partial",
        refusal_pred_short="margins_short",
        refusal_pred_not_done="capital_uncapitalized",
        refusal_pred_unmet="capital_unrequired",
        refusal_code_failed="cva_failed",
        summary="Post-capital solvency-versus-requirement for the absolute total spine.",
    )
)


class StageRefused(Exception):
    """A verdict-bearing refusal from a total-spine pair effect."""

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


def _pred_digest_of(spec: PairEffectSpec, row: Mapping[str, Any]) -> str:
    return str(
        row.get(f"{spec.pred}_digest")
        or row.get("certificate_hash")
        or ""
    ).strip()


def _capability_list(spec: PairEffectSpec, row: Mapping[str, Any]) -> list[str]:
    caps: list[str] = []
    seen: set[str] = set()
    for raw in row.get("capabilities") or []:
        cid = str(raw or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            caps.append(cid)
    if caps:
        return caps
    for leg in row.get(spec.pred_plural) or row.get(spec.plural) or []:
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


def _book_signature(spec: PairEffectSpec, margin: Mapping[str, Any]) -> str:
    """Identity of a collateralized book, independent of margin height/digest."""

    legs = margin.get(spec.pred_plural) or []
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


def _pairs(spec: PairEffectSpec, capabilities: Sequence[str]) -> list[dict[str, Any]]:
    """Atomic effect+counterpart pairs for each booked capability."""

    pairs: list[dict[str, Any]] = []
    for cid in capabilities:
        name = str(cid or "").strip()
        if not name:
            continue
        row = {
            "capability_id": name,
            spec.verdict_1: True,
            spec.verdict_2: True,
            "atomic_ok": True,
        }
        row["pair_root"] = _sha256_json(row)
        pairs.append(row)
    return pairs


def _pairs_digest(spec: PairEffectSpec, pairs: Sequence[Mapping[str, Any]]) -> str:
    rows: list[dict[str, Any]] = []
    for row in pairs:
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "capability_id": str(row.get("capability_id") or ""),
                spec.verdict_1: bool(row.get(spec.verdict_1, True)),
                spec.verdict_2: bool(row.get(spec.verdict_2, True)),
                "atomic_ok": bool(row.get("atomic_ok", True)),
                "pair_root": str(row.get("pair_root") or ""),
            }
        )
    return _sha256_json({"pairs": rows})


def _assert_pairs_atomic(spec: PairEffectSpec, pairs: Sequence[Mapping[str, Any]]) -> None:
    kind = spec.kind
    if not pairs:
        raise StageRefused(
            f"{kind}_pairs_empty",
            f"{spec.effect} refuses an empty LvC pair book",
        )
    for row in pairs:
        if not isinstance(row, Mapping):
            raise StageRefused(
                f"{kind}_partial",
                f"{spec.effect} refuses a malformed LvC pair",
            )
        verdict_1 = bool(row.get(spec.verdict_1, True))
        verdict_2 = bool(row.get(spec.verdict_2, True))
        if verdict_1 != verdict_2 or not bool(row.get("atomic_ok", True)):
            raise StageRefused(
                f"{kind}_partial",
                f"{spec.effect} refuses a split (non-atomic) "
                f"{spec.pred}-versus-{spec.counterpart} pair",
            )
        if not verdict_1 or not verdict_2:
            raise StageRefused(
                f"{kind}_partial",
                f"{spec.effect} refuses an {spec.adj_1_negated} or uncovered LvC pair",
            )


def _certificate_material(spec: PairEffectSpec, body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine effect certificate digests."""

    legs = body.get(spec.plural) or body.get("legs") or []
    rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            rows.append(
                {
                    f"{spec.pred}_index": int(row.get(f"{spec.pred}_index") or 0),
                    f"{spec.pred}_height": int(row.get(f"{spec.pred}_height") or 0),
                    f"{spec.pred}_digest": str(row.get(f"{spec.pred}_digest") or ""),
                    f"bound_{spec.pred}_root": str(
                        row.get(f"bound_{spec.pred}_root") or ""
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
                    spec.adj_1: bool(row.get(spec.adj_1, True)),
                    spec.adj_2: bool(row.get(spec.adj_2, True)),
                    "atomic_ok": bool(row.get("atomic_ok", True)),
                    "one_sided": bool(row.get("one_sided", False)),
                    "residual": int(row.get("residual") or 0),
                    "independent": bool(row.get("independent", True)),
                    f"parent_{spec.effect}_root": str(
                        row.get(f"parent_{spec.effect}_root") or ""
                    ),
                    f"{spec.pred}_root": str(row.get(f"{spec.pred}_root") or ""),
                    spec.post_key: bool(row.get(spec.post_key, True)),
                    "deterministic": bool(row.get("deterministic", True)),
                    spec.code: bool(row.get(spec.code, True)),
                }
            )
    return {
        "schema_version": int(body.get("schema_version") or SCHEMA_VERSION),
        "kind": str(body.get("kind") or spec.kind),
        "root_layer": str(body.get("root_layer") or ""),
        "goal": str(body.get("goal") or ""),
        "done_when": str(body.get("done_when") or ""),
        "bound_state_root": str(body.get("bound_state_root") or ""),
        "bound_action_root": str(body.get("bound_action_root") or ""),
        "actuation_digest": str(body.get("actuation_digest") or ""),
        "bound_settlement_root": str(body.get("bound_settlement_root") or ""),
        "bound_clearing_root": str(body.get("bound_clearing_root") or ""),
        f"bound_{spec.pred}_root": str(body.get(f"bound_{spec.pred}_root") or ""),
        "bound_custody_root": str(body.get("bound_custody_root") or ""),
        "bound_delivery_root": str(body.get("bound_delivery_root") or ""),
        f"{spec.pred}_digest": str(body.get(f"{spec.pred}_digest") or ""),
        "delivery_digest": str(body.get("delivery_digest") or ""),
        f"parent_{spec.effect}_root": str(body.get(f"parent_{spec.effect}_root") or ""),
        f"tip_{spec.effect}_root": str(body.get(f"tip_{spec.effect}_root") or ""),
        f"{spec.effect}_height": int(body.get(f"{spec.effect}_height") or 0),
        f"{spec.effect}_count": int(body.get(f"{spec.effect}_count") or 0),
        "pair_count": int(body.get("pair_count") or 0),
        "residual": int(body.get("residual") or 0),
        "capabilities": list(body.get("capabilities") or []),
        "contract_met": bool(body.get("contract_met", True)),
        "contract_machine": bool(body.get("contract_machine", False)),
        spec.adj_1: bool(body.get(spec.adj_1, True)),
        spec.adj_2: bool(body.get(spec.adj_2, True)),
        "atomic_ok": bool(body.get("atomic_ok", True)),
        f"{spec.code}_ok": bool(body.get(f"{spec.code}_ok", True)),
        "one_sided": bool(body.get("one_sided", False)),
        f"{spec.plural}_ok": bool(body.get(f"{spec.plural}_ok", True)),
        f"{spec.plural}_ok": bool(body.get(f"{spec.plural}_ok", True)),
        spec.post_key: bool(body.get(spec.post_key, True)),
        "deterministic": bool(body.get("deterministic", True)),
        "irreversible": bool(body.get("irreversible", True)),
        "success": bool(body.get("success", True)),
        spec.plural: rows,
    }



def compute_tip_root(spec: PairEffectSpec, preds: Sequence[Mapping[str, Any]]) -> str:
    """Tip effect root of a hash-chained log (empty → zero)."""

    if not preds:
        return "0" * 64
    last = preds[-1]
    tip = str(last.get(f"{spec.pred}_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(preds):
        body = {
            f"{spec.pred}_index": int(row.get(f"{spec.pred}_index") or idx),
            f"{spec.pred}_height": int(row.get(f"{spec.pred}_height") or (idx + 1)),
            f"{spec.pred}_digest": str(row.get(f"{spec.pred}_digest") or ""),
            f"bound_{spec.pred}_root": str(row.get(f"bound_{spec.pred}_root") or ""),
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
            spec.adj_1: bool(row.get(spec.adj_1, True)),
            spec.adj_2: bool(row.get(spec.adj_2, True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            f"parent_{spec.effect}_root": parent,
            spec.post_key: True,
            "deterministic": True,
            spec.code: True,
        }
        parent = _sha256_json(body)
    return parent or ("0" * 64)


def book_predecessors(
    spec: PairEffectSpec,
    margins: Sequence[Mapping[str, Any]],
    *,
    min_count: int = 2,
    parent_root: str = "",
    effect_height: int | None = None,
) -> list[dict[str, Any]]:
    """Book independently verified predecessor receipts into atomic legs."""

    from blackhole_agent import upstream_control_engine as _engine

    verify_pred = getattr(_engine, f"verify_total_spine_{spec.pred}_certificate")
    kind = spec.kind
    want = max(int(min_count), spec.min_value)
    verified: list[Mapping[str, Any]] = []
    for raw in margins:
        if not isinstance(raw, Mapping):
            continue
        verify = verify_pred(raw)
        if not verify.get("ok"):
            raise StageRefused(
                f"{kind}_{spec.refusal_pred_tampered}",
                f"{spec.effect} refuses a margin whose digest/chain does not verify",
            )
        if raw.get(spec.pred_done) is False or raw.get("success") is False:
            raise StageRefused(
                f"{kind}_{spec.refusal_pred_not_done}",
                f"{spec.effect} refuses an un{spec.pred_done} {spec.pred} receipt",
            )
        if raw.get(spec.pred_verdict_1) is False or raw.get(spec.pred_verdict_2) is False:
            raise StageRefused(
                f"{kind}_{spec.refusal_pred_unmet}",
                f"{spec.effect} refuses a {spec.pred} whose {spec.pred_code_upper} is not complete",
            )
        if raw.get("atomic_ok") is False:
            raise StageRefused(
                f"{kind}_{spec.refusal_pred_partial}",
                f"{spec.effect} refuses a non-atomic margin receipt",
            )
        if int(raw.get("residual") or 0) != 0:
            raise StageRefused(
                f"{kind}_residual",
                f"{spec.effect} refuses a margin with a non-zero residual",
            )
        verified.append(raw)
    if len(verified) < want:
        raise StageRefused(
            f"{kind}_{spec.refusal_pred_short}",
            f"{spec.pred} requires >= {want} independent {spec.pred_plural}, "
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
    book_sig = _book_signature(spec, first)
    book_caps = tuple(_capability_list(spec, first))
    if not book_state or not book_action or not book_actuation:
        raise StageRefused(
            f"{kind}_root_missing",
            f"{spec.pred} requires liquidity bound state/action/actuation roots",
        )
    if not book_caps:
        raise StageRefused(
            f"{kind}_pairs_empty",
            f"{spec.effect} refuses a liquidity with no funded capabilities",
        )

    legs: list[dict[str, Any]] = []
    parent = str(parent_root or "")
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
                f"{kind}_root_mismatch",
                f"{spec.effect} refuses collaterals bound to different "
                "state/action/actuation roots",
            )
        if settlement and book_settlement and settlement != book_settlement:
            raise StageRefused(
                f"{kind}_root_mismatch",
                f"{spec.effect} refuses collaterals bound to different settlement roots",
            )
        if clearing and book_clearing and clearing != book_clearing:
            raise StageRefused(
                f"{kind}_root_mismatch",
                f"{spec.effect} refuses collaterals bound to different clearing roots",
            )
        sig = _book_signature(spec, margin)
        if sig != book_sig:
            raise StageRefused(
                f"{kind}_{spec.refusal_code_failed}",
                f"independent liquidity books disagree; {spec.code_upper} cannot complete",
            )
        caps = tuple(_capability_list(spec, margin))
        if caps != book_caps:
            raise StageRefused(
                f"{kind}_one_sided",
                f"{spec.effect} refuses one-sided books whose capability sets differ",
            )
        pairs = _pairs(spec, book_caps)
        _assert_pairs_atomic(spec, pairs)
        height = (
            int(effect_height) + idx
            if effect_height is not None
            else (idx + 1)
        )
        material = {
            f"{spec.pred}_index": idx,
            f"{spec.pred}_height": height,
            f"{spec.pred}_digest": _pred_digest_of(spec, margin),
            f"bound_{spec.pred}_root": str(
                margin.get(f"tip_{spec.pred}_root") or ""
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
            "pairs_digest": _pairs_digest(spec, pairs),
            "pairs_atomic": True,
            spec.adj_1: True,
            spec.adj_2: True,
            "atomic_ok": True,
            "one_sided": False,
            "residual": 0,
            "independent": True,
            f"parent_{spec.effect}_root": parent,
            spec.post_key: True,
            "deterministic": True,
            spec.code: True,
        }
        pred_root = _sha256_json(material)
        row = dict(material)
        row[f"{spec.pred}_root"] = pred_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = pred_root
    return legs


def seal_certificate(spec: PairEffectSpec, body: Mapping[str, Any]) -> dict[str, Any]:
    """Seal the effect log into a tamper-evident receipt."""

    sealed_body = dict(body)
    legs = list(sealed_body.get(spec.plural) or [])
    if not str(sealed_body.get(f"tip_{spec.effect}_root") or "").strip():
        sealed_body[f"tip_{spec.effect}_root"] = compute_tip_root(spec, legs)
    if not int(sealed_body.get(f"{spec.effect}_count") or 0):
        sealed_body[f"{spec.effect}_count"] = len(legs)
    if not int(sealed_body.get(f"{spec.effect}_height") or 0):
        sealed_body[f"{spec.effect}_height"] = len(legs)
    material = _certificate_material(spec, sealed_body)
    material[f"tip_{spec.effect}_root"] = str(
        sealed_body.get(f"tip_{spec.effect}_root") or ""
    )
    digest = _sha256_json(material)
    sealed = dict(material)
    sealed[f"{spec.effect}_digest"] = digest
    sealed["certificate_hash"] = digest
    sealed[spec.kind] = True
    sealed[f"{spec.kind}_impl"] = True
    sealed[f"{spec.adj_1}_at"] = str(body.get(f"{spec.adj_1}_at") or utc_now_iso())
    sealed["used_skill_route_discovery"] = legacy_pipeline_was_used()
    if legs:
        sealed_pairs: list[Any] = []
        for src_row, dest in zip(legs, sealed.get(spec.plural) or []):
            if isinstance(src_row, Mapping) and isinstance(dest, dict):
                if src_row.get("pairs"):
                    dest["pairs"] = list(src_row.get("pairs") or [])
                sealed_pairs.append(dest)
        if sealed_pairs:
            sealed[spec.plural] = sealed_pairs
    return sealed


def certificate_path(spec: PairEffectSpec, root: Path) -> Path:
    """Resolve the effect certificate under its out root."""

    path = Path(root)
    if path.is_file():
        if path.name == spec.filename or path.suffix == ".json":
            try:
                probe = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                probe = None
            if isinstance(probe, Mapping) and (
                str(probe.get("kind") or "") == spec.kind
                or path.name == spec.filename
            ):
                return path
        parent = path.parent
        sibling = parent / spec.filename
        if sibling.is_file():
            return sibling
        nested = parent / spec.effect / spec.filename
        if nested.is_file():
            return nested
        grand = parent.parent / spec.effect / spec.filename
        if grand.is_file():
            return grand
        grand_sib = parent.parent / spec.filename
        if grand_sib.is_file():
            return grand_sib
        return parent / spec.effect / spec.filename
    named = path / spec.filename
    if named.is_file():
        return named
    nested = path / spec.effect / spec.filename
    if nested.is_file():
        return nested
    return path / spec.effect / spec.filename


def write_certificate(
    spec: PairEffectSpec,
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write an effect receipt under ``out_root``."""

    sealed = seal_certificate(spec, body)
    path = certificate_path(spec, Path(out_root))
    if path.is_file():
        try:
            existing = load_certificate(spec, path)
        except StageRefused:
            existing = None
        if existing is not None:
            existing_digest = str(
                existing.get(f"{spec.effect}_digest")
                or existing.get("certificate_hash")
                or ""
            )
            new_digest = str(
                sealed.get(f"{spec.effect}_digest")
                or sealed.get("certificate_hash")
                or ""
            )
            if (
                existing_digest
                and existing_digest == new_digest
                and allow_idempotent
            ):
                existing[f"{spec.effect}_path"] = str(path)
                existing[f"{spec.kind}_idempotent"] = True
                return existing
            raise StageRefused(
                f"{spec.kind}_supersession_refused",
                f"irreversible {spec.pred} already sealed at {path} "
                f"(existing={existing_digest!r} attempted={new_digest!r})",
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, sealed)
    sealed[f"{spec.effect}_path"] = str(path)
    sealed[f"{spec.kind}_idempotent"] = False
    return sealed


def verify_certificate(spec: PairEffectSpec, certificate: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute the digest and chain roots; fail closed on tamper."""

    claimed = str(
        certificate.get(f"{spec.effect}_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    material = _certificate_material(spec, certificate)
    expected = _sha256_json(material)
    legs = list(certificate.get(spec.plural) or [])
    recomputed_tip = compute_tip_root(spec, legs)
    claimed_tip = str(certificate.get(f"tip_{spec.effect}_root") or "")
    height = int(certificate.get(f"{spec.effect}_height") or 0)
    count = int(certificate.get(f"{spec.effect}_count") or 0)
    bound_root = str(certificate.get("bound_state_root") or "")
    bound_action = str(certificate.get("bound_action_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    cert_parent = str(certificate.get(f"parent_{spec.effect}_root") or "")
    chain_ok = True
    parent = cert_parent
    book_sig = ""
    for idx, row in enumerate(legs):
        if not isinstance(row, Mapping):
            chain_ok = False
            break
        if str(row.get("bound_state_root") or "") != bound_root:
            chain_ok = False
            break
        if str(row.get("actuation_digest") or "") != actuation_digest:
            chain_ok = False
            break
        if str(row.get(f"parent_{spec.effect}_root") or "") != parent:
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
            if _pairs_digest(spec, pairs) != pairs_digest:
                chain_ok = False
                break
            try:
                _assert_pairs_atomic(spec, pairs)
            except StageRefused:
                chain_ok = False
                break
        material_row = {
            f"{spec.pred}_index": int(row.get(f"{spec.pred}_index") or idx),
            f"{spec.pred}_height": int(row.get(f"{spec.pred}_height") or (idx + 1)),
            f"{spec.pred}_digest": str(row.get(f"{spec.pred}_digest") or ""),
            f"bound_{spec.pred}_root": str(row.get(f"bound_{spec.pred}_root") or ""),
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
            spec.adj_1: bool(row.get(spec.adj_1, True)),
            spec.adj_2: bool(row.get(spec.adj_2, True)),
            "atomic_ok": bool(row.get("atomic_ok", True)),
            "one_sided": bool(row.get("one_sided", False)),
            "residual": int(row.get("residual") or 0),
            "independent": bool(row.get("independent", True)),
            f"parent_{spec.effect}_root": parent,
            spec.post_key: True,
            "deterministic": True,
            spec.code: True,
        }
        expected_root = _sha256_json(material_row)
        if str(row.get(f"{spec.pred}_root") or "") != expected_root:
            chain_ok = False
            break
        parent = expected_root
    parent_ok = (not cert_parent and height == count) or (
        bool(cert_parent) and height >= count
    )
    min_ok = count >= spec.min_value and height >= count
    legs_ok = all(
        isinstance(row, Mapping)
        and bool(row.get(spec.adj_1, True))
        and bool(row.get(spec.adj_2, True))
        and bool(row.get("atomic_ok", True))
        and bool(row.get(spec.code, True))
        and not bool(row.get("one_sided", False))
        and int(row.get("residual") or 0) == 0
        for row in legs
    )
    ok = (
        bool(claimed)
        and claimed == expected
        and str(certificate.get("kind") or "") == spec.kind
        and int(certificate.get("schema_version") or 0) == SCHEMA_VERSION
        and certificate.get("irreversible") is True
        and certificate.get(spec.post_key) is True
        and certificate.get("deterministic") is True
        and certificate.get(spec.adj_1) is True
        and certificate.get(spec.adj_2) is True
        and certificate.get("atomic_ok") is True
        and certificate.get(f"{spec.code}_ok") is True
        and certificate.get("one_sided") is False
        and bool(certificate.get("success"))
        and height >= 1
        and count >= 1
        and count == len(legs)
        and height >= count
        and bool(bound_root)
        and bool(bound_action)
        and bool(actuation_digest)
        and bool(claimed_tip)
        and claimed_tip == recomputed_tip
        and chain_ok
        and parent_ok
        and min_ok
        and legs_ok
        and int(certificate.get("residual") or 0) == 0
    )
    return {
        "ok": ok,
        "action": f"verify_total_spine_{spec.effect}",
        "claimed_digest": claimed,
        "expected_digest": expected,
        f"{spec.effect}_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        f"{spec.pred}_root_ok": claimed_tip == recomputed_tip and bool(claimed_tip),
        f"recomputed_tip_{spec.effect}_root": recomputed_tip,
        "chain_ok": chain_ok,
        f"min_{spec.plural}_ok": min_ok,
        f"{spec.plural}_ok": legs_ok,
        f"{spec.code}_ok": certificate.get(f"{spec.code}_ok") is True,
        "atomic_ok": certificate.get("atomic_ok") is True,
        "kind_ok": str(certificate.get("kind") or "") == spec.kind,
        "schema_ok": int(certificate.get("schema_version") or 0) == SCHEMA_VERSION,
        "irreversible_ok": certificate.get("irreversible") is True,
        f"{spec.adj_1}_ok": certificate.get(spec.adj_1) is True,
        f"{spec.adj_2}_ok": certificate.get(spec.adj_2) is True,
        spec.kind: True,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def load_certificate(spec: PairEffectSpec, path: Path | str) -> dict[str, Any]:
    """Load and integrity-check a sealed effect receipt."""

    file_path = certificate_path(spec, Path(path))
    if not file_path.is_file():
        raise StageRefused(
            f"{spec.kind}_missing",
            f"{spec.pred} certificate not found at {file_path}",
        )
    raw_path = durable_read_path(file_path)
    try:
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRefused(
            f"{spec.kind}_unreadable",
            f"{spec.pred} certificate unreadable at {file_path}: {exc}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise StageRefused(
            f"{spec.kind}_invalid",
            f"{spec.pred} certificate root must be a JSON object",
        )
    if str(payload.get("kind") or "") != spec.kind and not payload.get(spec.kind):
        raise StageRefused(
            f"{spec.kind}_missing",
            f"{spec.pred} certificate not found at {file_path}",
        )
    verify = verify_certificate(spec, payload)
    if not verify.get("ok"):
        raise StageRefused(
            f"{spec.kind}_tampered",
            f"{spec.pred} certificate digest mismatch at {file_path} "
            f"(claimed={verify.get('claimed_digest')!r} "
            f"expected={verify.get('expected_digest')!r})",
        )
    body = dict(payload)
    body[f"{spec.effect}_path"] = str(file_path)
    body[f"{spec.effect}_verify"] = verify
    body[f"{spec.kind}_loaded"] = True
    return body


def seal_chain(
    spec: PairEffectSpec,
    *,
    prior_tip: str,
    effect_digest: str,
    tip_effect_root: str,
    bound_pred_root: str,
    bound_delivery_root: str,
    bound_clearing_root: str,
    bound_settlement_root: str,
    bound_action_root: str,
    bound_state_root: str,
    actuation_digest: str,
    pred_digest: str,
    delivery_digest: str,
    effect_height: int,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Seal the effect hop into the absolute-tower tip."""

    tip = str(prior_tip or "").strip() or ("0" * 64)
    md = str(effect_digest or "").strip() or ("0" * 64)
    mr = str(tip_effect_root or "").strip() or ("0" * 64)
    cr = str(bound_pred_root or "").strip() or ("0" * 64)
    dlr = str(bound_delivery_root or "").strip() or ("0" * 64)
    clr = str(bound_clearing_root or "").strip() or ("0" * 64)
    sr = str(bound_settlement_root or "").strip() or ("0" * 64)
    ar = str(bound_action_root or "").strip() or ("0" * 64)
    st = str(bound_state_root or "").strip() or ("0" * 64)
    ad = str(actuation_digest or "").strip() or ("0" * 64)
    cd = str(pred_digest or "").strip() or ("0" * 64)
    dvd = str(delivery_digest or "").strip() or ("0" * 64)
    material = (
        f"{spec.effect}|{int(bool(short_circuit))}|{int(effect_height)}|"
        f"{st}|{ar}|{ad}|{sr}|{clr}|{dlr}|{cr}|{dvd}|{cd}|{mr}|{md}|{tip}"
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        f"{spec.effect}_height": int(effect_height),
        f"tip_{spec.effect}_root": mr,
        f"bound_{spec.pred}_root": cr,
        "bound_delivery_root": dlr,
        "bound_clearing_root": clr,
        "bound_settlement_root": sr,
        "bound_action_root": ar,
        "bound_state_root": st,
        "actuation_digest": ad,
        f"{spec.pred}_digest": cd,
        "delivery_digest": dvd,
        f"{spec.effect}_digest": md,
        "prior_tip": tip,
        "digest": digest,
        spec.kind: True,
        "irreversible": True,
        spec.post_key: True,
        "deterministic": True,
        spec.code: True,
    }


def annotate(
    spec: PairEffectSpec,
    body: dict[str, Any],
    *,
    certificate: Mapping[str, Any],
    prior_tip: str,
    short_circuit: bool = False,
) -> dict[str, Any]:
    """Stamp the effect onto a total-spine result and rebind the tip."""

    cst_digest = str(
        certificate.get(f"{spec.effect}_digest")
        or certificate.get("certificate_hash")
        or ""
    )
    tip_effect_root = str(certificate.get(f"tip_{spec.effect}_root") or "")
    effect_height = int(certificate.get(f"{spec.effect}_height") or 0)
    effect_count = int(certificate.get(f"{spec.effect}_count") or 0)
    bound_state_root = str(certificate.get("bound_state_root") or "")
    bound_action_root = str(certificate.get("bound_action_root") or "")
    bound_settlement_root = str(certificate.get("bound_settlement_root") or "")
    bound_clearing_root = str(certificate.get("bound_clearing_root") or "")
    bound_pred_root = str(certificate.get(f"bound_{spec.pred}_root") or "")
    bound_delivery_root = str(certificate.get("bound_delivery_root") or "")
    actuation_digest = str(certificate.get("actuation_digest") or "")
    pred_digest = str(certificate.get(f"{spec.pred}_digest") or "")
    delivery_digest = str(certificate.get("delivery_digest") or "")
    chain = seal_chain(
        spec,
        prior_tip=prior_tip,
        effect_digest=cst_digest,
        tip_effect_root=tip_effect_root,
        bound_pred_root=bound_pred_root,
        bound_delivery_root=bound_delivery_root,
        bound_clearing_root=bound_clearing_root,
        bound_settlement_root=bound_settlement_root,
        bound_action_root=bound_action_root,
        bound_state_root=bound_state_root,
        actuation_digest=actuation_digest,
        pred_digest=pred_digest,
        delivery_digest=delivery_digest,
        effect_height=effect_height,
        short_circuit=short_circuit,
    )
    cst_tip = str(chain.get("digest") or prior_tip)
    bound = _sha256_bytes(f"{prior_tip}|{cst_tip}".encode("utf-8"))
    kind = spec.kind
    body[kind] = True
    body[f"{kind}_impl"] = True
    body[f"{kind}_short_circuit"] = bool(short_circuit)
    body[f"{kind}_irreversible"] = True
    body[f"{kind}_{spec.post_key}"] = True
    body[f"{kind}_deterministic"] = True
    body[f"{kind}_{spec.code}"] = True
    body[f"{kind}_certificate"] = dict(certificate)
    body[f"{kind}_digest"] = cst_digest
    body[f"{kind}_chain"] = chain
    body[f"{kind}_tip"] = cst_tip
    body[f"{kind}_bound_tip"] = bound
    body[f"total_spine_digest_pre_{spec.pred}"] = prior_tip
    body[f"total_spine_tip_{spec.effect}_root"] = tip_effect_root
    body[f"{kind}_height"] = effect_height
    body[f"{kind}_count"] = effect_count
    body[f"total_spine_{spec.adj_1}"] = bool(certificate.get(spec.adj_1, True))
    body[f"total_spine_{spec.adj_1}_ok"] = bool(certificate.get(spec.adj_1, True))
    body[f"total_spine_{spec.adj_2}"] = bool(certificate.get(spec.adj_2, True))
    body[f"total_spine_{spec.adj_2}_ok"] = bool(certificate.get(spec.adj_2, True))
    body[f"total_spine_{spec.code}_ok"] = bool(certificate.get(f"{spec.code}_ok", True))
    body[f"{kind}_atomic"] = bool(certificate.get("atomic_ok", True))
    body[f"{kind}_one_sided"] = bool(
        certificate.get("one_sided", False)
    )
    body[f"total_spine_{spec.plural}_ok"] = bool(
        certificate.get(f"{spec.plural}_ok", True)
    )
    body[f"{kind}_root_valid"] = bool(tip_effect_root)
    body[f"{kind}_residual"] = int(certificate.get("residual") or 0)
    body[f"{kind}_pair_count"] = int(
        certificate.get("pair_count") or 0
    )
    body[f"{spec.effect}_root"] = tip_effect_root
    body[f"tip_{spec.effect}_root"] = tip_effect_root
    body[f"{spec.effect}_count"] = effect_count
    body[f"{spec.effect}_height"] = effect_height
    body[spec.adj_1] = bool(certificate.get(spec.adj_1, True))
    body[f"{spec.adj_1}_ok"] = bool(certificate.get(spec.adj_1, True))
    body[f"{spec.effect}_ok"] = bool(certificate.get(spec.adj_1, True))
    body[f"{spec.code}_ok"] = bool(certificate.get(f"{spec.code}_ok", True))
    body[spec.adj_2] = bool(certificate.get(spec.adj_2, True))
    if certificate.get(f"{spec.effect}_path"):
        body[f"{kind}_path"] = certificate.get(f"{spec.effect}_path")
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
    if bound_pred_root:
        body[f"total_spine_tip_{spec.pred}_root"] = bound_pred_root
        body[f"{spec.pred}_root"] = bound_pred_root
        body[f"tip_{spec.pred}_root"] = bound_pred_root
        body.setdefault(f"total_spine_{spec.pred}", True)
        body.setdefault(f"total_spine_{spec.pred_done}", True)
        body.setdefault(f"total_spine_{spec.pred_code}_ok", True)
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
    if pred_digest:
        body[f"total_spine_{spec.pred}_digest"] = pred_digest
    if delivery_digest:
        body["total_spine_delivery_digest"] = delivery_digest
    if certificate.get("contract_met") is not None:
        body["total_spine_contract_met"] = bool(certificate.get("contract_met"))
        body["total_spine_contract_ok"] = bool(certificate.get("contract_met"))
        body["total_spine_contract"] = True
    body["total_spine_digest"] = bound
    body["verdict"] = (
        f"{kind}_ok_short_circuit"
        if short_circuit
        else f"{kind}_ok"
    )
    body["ok"] = True
    return body


# ---------------------------------------------------------------------------
# Predecessor accessors (shared: absolute chain nouns, not per-effect).
# ---------------------------------------------------------------------------


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


# Accessor dispatch for the pair chain below the effect itself.
_CHAIN_ACCESSORS = {
    "margins": _margins_from,
    "custodies": _custodies_from,
    "deliveries": _deliveries_from,
    "clearings": _clearings_from,
    "settlements": _settlements_from,
    "collaterals": _collaterals_from,
    "liquidities": _liquidities_from,
    "fundings": _fundings_from,
}


def _as_pred_mapping(spec: PairEffectSpec, value: Any) -> dict[str, Any] | None:
    from blackhole_agent import upstream_control_engine as _engine

    load_pred = getattr(_engine, f"load_total_spine_{spec.pred}_certificate")
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == spec.kind or value.get(spec.kind):
            nested_liq = value.get(f"{spec.pred_kind}_certificate")
            if isinstance(nested_liq, Mapping) and nested_liq.get(
                f"tip_{spec.pred}_root"
            ):
                return dict(nested_liq)
        if kind == spec.pred_kind or value.get(
            spec.pred_kind
        ) or value.get(f"{spec.pred_kind}_loaded") or value.get(
            f"tip_{spec.pred}_root"
        ):
            nested = value.get(f"{spec.pred_kind}_certificate")
            if isinstance(nested, Mapping) and nested.get(f"tip_{spec.pred}_root"):
                return dict(nested)
            return dict(value)
        nested = value.get(f"{spec.pred_kind}_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    path = Path(str(value))
    try:
        probe_path = path
        if path.is_dir():
            nested = path / spec.pred / spec.filename.replace(spec.effect, spec.pred)
            named = path / spec.filename.replace(spec.effect, spec.pred)
            probe_path = nested if nested.is_file() else named
        if probe_path.is_file():
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            if isinstance(probe, Mapping):
                kind = str(probe.get("kind") or "")
                if kind and kind != spec.pred_kind:
                    return None
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_pred(path)
    except Exception as exc:  # noqa: BLE001 — pred modules each define their own StageRefused
        verdict = getattr(exc, "verdict", None)
        if verdict is not None and str(verdict) == f"{spec.pred_kind}_tampered":
            raise StageRefused(str(verdict), str(getattr(exc, "detail", exc))) from exc
        return None


def _as_effect_mapping(spec: PairEffectSpec, value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "")
        if kind == spec.kind or value.get(
            spec.kind
        ) or value.get(f"{spec.kind}_loaded"):
            nested = value.get(f"{spec.kind}_certificate")
            if isinstance(nested, Mapping) and nested.get(f"tip_{spec.effect}_root"):
                return dict(nested)
            return dict(value)
        nested = value.get(f"{spec.kind}_certificate")
        if isinstance(nested, Mapping):
            return dict(nested)
        return None
    if value is None:
        return None
    try:
        return load_certificate(spec, Path(str(value)))
    except StageRefused as exc:
        if str(exc.verdict) == f"{spec.kind}_tampered":
            raise
        return None
    except Exception:  # noqa: BLE001
        return None


# The full absolute-tower chain from settlement up (pair effects in bold order).
TOTAL_SPINE_CHAIN: tuple[str, ...] = (
    "settlement",
    "clearing",
    "delivery",
    "custody",
    "margin",
    "collateral",
    "liquidity",
    "funding",
    "capital",
    "solvency",
    "risk",
    "stress",
    "recovery",
    "resolution",
    "restructuring",
    "emergence",
    "reorganization",
)

_CHAIN_PLURALS = {
    "settlement": "settlements",
    "clearing": "clearings",
    "delivery": "deliveries",
    "custody": "custodies",
    "margin": "margins",
    "collateral": "collaterals",
    "liquidity": "liquidities",
    "funding": "fundings",
    "capital": "capitals",
    "solvency": "solvencies",
    "risk": "risks",
    "stress": "stresses",
    "recovery": "recoveries",
    "resolution": "resolutions",
    "restructuring": "restructurings",
    "emergence": "emergences",
    "reorganization": "reorganizations",
}


def _pred_pred_plural(spec: PairEffectSpec) -> str:
    idx = TOTAL_SPINE_CHAIN.index(spec.pred)
    return _CHAIN_PLURALS[TOTAL_SPINE_CHAIN[idx - 1]]


def _confirm_pred(
    spec: PairEffectSpec,
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
    """Independently re-run the predecessor on the same book as confirmation."""

    from blackhole_agent import upstream_control_engine as _engine

    pred_runner = getattr(_engine, f"{spec.pred}_total_spine")

    # Do not nest confirm writes under out_root: each prior plane appends
    # its own *-confirm directory, and the full cascade exceeds Windows
    # MAX_PATH. The confirmation predecessor is sealed in-memory.
    confirm_out = None
    tip_pred = str(primary.get(f"tip_{spec.pred}_root") or "")
    pred_height = int(primary.get(f"{spec.pred}_height") or 0)
    confirm_body: dict[str, Any] = {}
    if isinstance(body, Mapping):
        confirm_body = dict(body)
    elif isinstance(primary, Mapping):
        confirm_body = dict(primary)
    for drop in (
        spec.pred_kind,
        f"{spec.pred_kind}_certificate",
        f"{spec.pred_kind}_loaded",
        spec.kind,
        f"{spec.kind}_certificate",
        "kind",
        f"tip_{spec.pred}_root",
        f"tip_{spec.effect}_root",
        f"{spec.pred}_digest",
        f"{spec.effect}_digest",
        "certificate_hash",
    ):
        kind = str(confirm_body.get("kind") or "")
        if kind in {spec.pred_kind, spec.kind}:
            confirm_body.pop("kind", None)
        confirm_body.pop(drop, None)
    pred_preds: list[dict[str, Any]] = []
    seen: set[str] = set()
    pred_pred_accessor = _CHAIN_ACCESSORS.get(_pred_pred_plural(spec))
    for src in (primary, body, confirm_body):
        if pred_pred_accessor is None:
            break
        for row in pred_pred_accessor(src):
            key = str(
                row.get(f"{TOTAL_SPINE_CHAIN[TOTAL_SPINE_CHAIN.index(spec.pred) - 1]}_digest")
                or row.get("certificate_hash")
                or row.get(f"tip_{TOTAL_SPINE_CHAIN[TOTAL_SPINE_CHAIN.index(spec.pred) - 1]}_root")
                or ""
            )
            if not key or key in seen:
                continue
            seen.add(key)
            pred_preds.append(row)
    bundle: list[Any] = list(pred_preds)
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
    if not pred_preds and not bundle and not confirm_body:
        raise StageRefused(
            f"{spec.kind}_confirmation_missing",
            f"single {spec.pred} requires {_pred_pred_plural(spec)}, collaterals, margins, "
            "custodies, deliveries, clearings, settlements, or actuation "
            f"to confirm-{spec.effect}",
        )
    source: Any = pred_preds[0] if len(pred_preds) == 1 else (pred_preds or bundle)
    confirmed = pred_runner(
        source,
        **{
            _pred_pred_plural(spec): pred_preds or None,
            "margins": margins or None,
            "clearings": clearings or None,
            "settlements": settlements or None,
            "actuation": actuation,
            "body": confirm_body or None,
            "out_root": confirm_out,
            "prior_tip": prior_tip,
            f"parent_{spec.pred}_root": tip_pred,
            f"{spec.pred}_height": pred_height + 1 if pred_height else None,
            "repo_path": repo_path or REPO_ROOT,
            "confirm": True,
        },
    )
    cert = confirmed.get(f"{spec.pred_kind}_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            f"{spec.kind}_confirmation_missing",
            f"confirmation {spec.pred} did not produce a certificate",
        )
    return dict(cert)


def _collect_preds(
    spec: PairEffectSpec,
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None,
    body: Mapping[str, Any] | None,
    extra: Sequence[Mapping[str, Any] | Path | str] | None,
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
]:
    """Return (existing, preds, collaterals, margins, custodies, deliveries, clearings, settlements, actuation)."""

    existing = _as_effect_mapping(spec, source)
    if existing is None and body is not None:
        existing = _as_effect_mapping(spec, body)
    preds: list[dict[str, Any]] = []
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
        mapped = _as_pred_mapping(spec, item)
        if mapped is not None:
            preds.append(mapped)
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
        for chain_name in spec.collect_push:
            _push(body.get(f"total_spine_{chain_name}_certificate"))
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
    for row in preds:
        digest = _pred_digest_of(spec, row)
        tip = str(row.get(f"tip_{spec.pred}_root") or "")
        key = digest or tip
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    def _dedup(rows: list[dict[str, Any]], noun: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for row in rows:
            digest = str(
                row.get(f"{noun}_digest")
                or row.get("certificate_hash")
                or row.get(f"tip_{noun}_root")
                or ""
            )
            if not digest or digest in seen_keys:
                continue
            seen_keys.add(digest)
            out.append(row)
        return out

    return (
        existing,
        deduped,
        _dedup(collaterals, "collateral"),
        _dedup(margins, "margin"),
        _dedup(custodies, "custody"),
        _dedup(deliveries, "delivery"),
        _dedup(clearings, "clearing"),
        _dedup(settlements, "settlement"),
        actuation,
    )


def _strip_effect_predicates(spec: PairEffectSpec, done_when: str) -> str:
    """Evaluate the pre-effect contract, never the effect's own (no recurse)."""

    text = str(done_when or "").strip()
    if not text:
        return ""
    blocked = {
        f"{spec.effect}_ok",
        spec.verdict_1,
        f"{spec.adj_1}_ok",
        f"min_{spec.plural}",
        f"{spec.effect}_root_valid",
        f"{spec.code}_ok",
        spec.verdict_2,
        f"{spec.adj_2}_ok",
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


def run_pair_effect(
    spec: PairEffectSpec,
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Apply the atomic pair effect on the absolute total spine."""

    from blackhole_agent.upstream_control_engine import (
        TOTAL_SPINE_DEFAULT_ROOT as ENGINE_DEFAULT_ROOT,
        evaluate_total_spine_contract,
        seal_total_spine_hop_chain,
        total_nest_depth,
    )

    extra_pred_books = kwargs.get(spec.pred_plural)
    margins_arg = kwargs.get("margins")
    out_root = kwargs.get("out_root")
    prior_tip = kwargs.get("prior_tip")
    body = kwargs.get("body")
    min_count = int(kwargs.get(f"min_{spec.plural}") or spec.min_value)
    parent_root = str(kwargs.get(f"parent_{spec.effect}_root") or "")
    effect_height = kwargs.get(f"{spec.effect}_height")
    short_circuit = bool(kwargs.get("short_circuit", False))
    repo_path = kwargs.get("repo_path")
    confirm = bool(kwargs.get("confirm", True))
    actuation = kwargs.get("actuation")
    settlements_arg = kwargs.get("settlements")
    clearings_arg = kwargs.get("clearings")

    extra_books: list[Any] = []
    extra_books.extend(list(extra_pred_books or []))
    extra_books.extend(list(margins_arg or []))
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
    ) = _collect_preds(spec, source, body, extra_books)
    if actuation is None:
        actuation = found_actuation
    else:
        actuation = dict(actuation)
    extra_clearings = list(clearings_arg or [])
    if extra_clearings:
        found_clearings = list(found_clearings) + list(extra_clearings)
    extra_settlements = list(settlements_arg or [])
    if extra_settlements:
        found_settlements = list(found_settlements) + list(extra_settlements)
    if (
        existing is not None
        and existing.get(f"tip_{spec.effect}_root")
        and (
            str(existing.get("kind") or "") == spec.kind
            or existing.get(f"{spec.kind}_loaded")
            or existing.get(spec.kind)
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
            "action": f"{spec.verb}_total_spine",
            "total_spine": True,
        }
        return annotate(
            spec,
            result,
            certificate=existing,
            prior_tip=tip,
            short_circuit=True,
        )

    want = max(int(min_count), spec.min_value)
    if len(collected) < want and confirm and collected:
        collected.append(
            _confirm_pred(
                spec,
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
                    or (body or {}).get(f"total_spine_{spec.pred}_bound_tip")
                    or (body or {}).get("total_spine_digest")
                    or ""
                ),
                repo_path=repo_path,
                body=body,
            )
        )
    if len(collected) < want:
        raise StageRefused(
            f"{spec.kind}_{spec.refusal_pred_short}",
            f"{spec.pred} requires >= {want} independent {spec.pred_plural}, "
            f"got {len(collected)}",
        )

    legs = book_predecessors(
        spec,
        collected,
        min_count=want,
        parent_root=parent_root,
        effect_height=effect_height,
    )
    first = collected[0]
    state_root = str(first.get("bound_state_root") or "")
    action_root = str(
        first.get("bound_action_root") or first.get("tip_action_root") or ""
    )
    actuation_digest = str(first.get("actuation_digest") or "")
    settlement_root = str(first.get("bound_settlement_root") or "")
    clearing_root = str(first.get("bound_clearing_root") or "")
    pred_root = str(first.get(f"tip_{spec.pred}_root") or "")
    pred_digest = _pred_digest_of(spec, first)
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
    capabilities = _capability_list(spec, first)

    contract_met = True
    contract_machine = False
    contract_eval: dict[str, Any] | None = None
    pre_effect = _strip_effect_predicates(spec, done_when)
    if pre_effect:
        ctx = {
            "liquidity": {
                "ok": True,
                "funded": True,
                "funded_ok": True,
                f"{spec.pred}_root_valid": True,
                "lvc_ok": True,
                "liquidity_count": int(first.get("liquidity_count") or 0),
                f"tip_{spec.pred}_root": pred_root,
            },
            "liquidity_count": int(first.get("liquidity_count") or 0),
            f"tip_{spec.pred}_root": pred_root,
            "state_root": state_root,
        }
        contract_eval = evaluate_total_spine_contract(
            pre_effect,
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
                f"{spec.kind}_contract_unmet",
                f"done_when not met at collateral: {pre_effect!r}",
            )

    tip_effect_root = compute_tip_root(spec, legs)
    cst_height = int(legs[-1][f"{spec.pred}_height"]) if legs else 0
    tip = str(
        prior_tip
        or (body or {}).get(f"total_spine_{spec.pred}_bound_tip")
        or (body or {}).get("total_spine_digest")
        or first.get("prior_tip")
        or ""
    )
    pair_count = int(legs[0].get("pair_count") or 0) if legs else 0

    cst_body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": spec.kind,
        "root_layer": root_layer,
        "goal": goal,
        "done_when": done_when,
        "bound_state_root": state_root,
        "bound_action_root": action_root,
        "actuation_digest": actuation_digest,
        "bound_settlement_root": settlement_root,
        "bound_clearing_root": clearing_root,
        f"bound_{spec.pred}_root": pred_root,
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
        f"{spec.pred}_digest": pred_digest,
        "delivery_digest": str(
            first.get("delivery_digest")
            or first.get("certificate_hash")
            or ""
        ),
        "prior_tip": tip,
        f"parent_{spec.effect}_root": str(
            parent_root
            or (legs[0].get(f"parent_{spec.effect}_root") if legs else "")
            or ""
        ),
        spec.plural: legs,
        f"{spec.effect}_count": len(legs),
        f"{spec.effect}_height": cst_height,
        f"tip_{spec.effect}_root": tip_effect_root,
        "pair_count": pair_count,
        "residual": 0,
        "capabilities": capabilities,
        "contract_met": contract_met,
        "contract_machine": contract_machine,
        spec.adj_1: True,
        spec.adj_2: True,
        "atomic_ok": True,
        f"{spec.code}_ok": True,
        "one_sided": False,
        f"{spec.plural}_ok": True,
        f"{spec.plural}_ok": True,
        spec.post_key: True,
        "deterministic": True,
        "irreversible": True,
        "success": True,
        f"{spec.adj_1}_at": utc_now_iso(),
    }
    if contract_eval is not None:
        cst_body["contract_eval"] = {
            "met": contract_eval.get("met"),
            "machine_checkable": contract_eval.get("machine_checkable"),
            "ok": contract_eval.get("ok"),
        }

    write_target = Path(out_root) if out_root is not None else None
    if write_target is not None:
        certificate = write_certificate(spec, write_target, cst_body)
    else:
        certificate = seal_certificate(spec, cst_body)

    result = body if body is not None else {
        "ok": True,
        "action": f"{spec.verb}_total_spine",
        "total_spine": True,
        "total_spine_root": root_layer,
        "total_nest_depth": total_nest_depth(root_layer),
    }
    annotated = annotate(
        spec,
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
        cst_bound = str(annotated.get(f"{spec.kind}_bound_tip") or tip)
        hops = seal_total_spine_hop_chain(
            root_layer, live_result, tip=cst_bound
        )
        annotated["total_spine_hop_chain"] = hops
        annotated["total_spine_hop_count"] = len(hops)
        if hops:
            annotated["total_spine_digest"] = hops[0].get("digest")
            annotated[f"{root_layer}_digest"] = hops[0].get("digest")
    annotated[f"{spec.kind}_bound_state_root"] = state_root
    annotated[f"{spec.kind}_bound_action_root"] = action_root
    annotated[f"{spec.kind}_bound_settlement_root"] = settlement_root
    annotated[f"{spec.kind}_bound_clearing_root"] = clearing_root
    annotated[f"{spec.kind}_bound_{spec.pred}_root"] = pred_root
    annotated[f"{spec.kind}_actuation_digest"] = actuation_digest
    annotated["used_skill_route_discovery"] = legacy_pipeline_was_used()
    return annotated


_CHAIN_VERBS = {
    "clearing": "clear",
    "delivery": "deliver",
    "custody": "custody",
    "margin": "margin",
    "collateral": "collateral",
    "liquidity": "liquidity",
    "funding": "funding",
    "capital": "capital",
    "solvency": "solvency",
    "risk": "risk",
    "stress": "stress",
    "recovery": "recovery",
    "resolution": "resolution",
    "restructuring": "restructuring",
    "emergence": "emerge",
    "reorganization": "reorganize",
}

_CHAIN_ABBRS = {
    "clearing": "clr",
    "delivery": "dlv",
    "custody": "cst",
    "margin": "mgn",
    "collateral": "col",
    "liquidity": "liq",
    "funding": "fnd",
    "capital": "cap",
    "solvency": "sol",
    "risk": "rsk",
    "stress": "str",
    "recovery": "rec",
    "resolution": "res",
    "restructuring": "rst",
    "emergence": "emg",
    "reorganization": "reo",
}


def _builtin_pair_effect_proof(spec: PairEffectSpec) -> dict[str, Any]:
    """Hermetic proof: the pair effect on the absolute tower."""

    import shutil
    import tempfile

    from blackhole_agent.capability_compounder import (
        default_ledger_path,
        load_ledger,
    )
    from blackhole_agent import upstream_control_engine as ce

    scratch = Path(tempfile.mkdtemp(prefix=f"total-spine-{spec.effect}-proof-"))
    try:
        from blackhole_agent import upstream_loop_engine as le_facade

        pred_idx = TOTAL_SPINE_CHAIN.index(spec.pred)
        eff_idx = TOTAL_SPINE_CHAIN.index(spec.effect)
        # Pair links from clearing up to the predecessor, in chain order.
        pair_links = [
            name for name in TOTAL_SPINE_CHAIN[1:pred_idx + 1]
        ]
        runners = {
            name: getattr(ce, f"{_CHAIN_VERBS[name]}_total_spine")
            for name in pair_links
        }

        flags_ok = (
            getattr(ce, f"TOTAL_SPINE_{spec.upper}_IMPL") is True
            and all(
                getattr(ce, f"TOTAL_SPINE_{name.upper()}_IMPL") is True
                for name in pair_links
                if hasattr(ce, f"TOTAL_SPINE_{name.upper()}_IMPL")
            )
            and spec.kind == f"total_spine_{spec.effect}"
            and bool(spec.filename)
            and spec.min_value >= 2
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
                "schema_version": ce.SCHEMA_VERSION,
                "kind": ce.TOTAL_SPINE_FINALITY_KIND,
                "root_layer": "quettacontinuum",
                "goal": f"{spec.effect} proof origin",
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
            cert = ce.write_total_spine_finality_certificate(
                scratch / f"origin-{idx}", body
            )
            paths.append(str(cert.get("finality_path") or ""))

        quorumed = ce.federate_total_spine(
            paths,
            out_root=scratch / "quorum",
            prior_tip="a" * 64,
            quorum=True,
        )
        executed = ce.execute_total_spine(
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
        actuated = ce.actuate_total_spine(
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
        settled = ce.settle_total_spine(
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
        confirmed_set = ce.settle_total_spine(
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

        state_root = str(settled.get("total_spine_state_root") or "")
        tip_action = str(settled.get("total_spine_tip_action_root") or "")

        # Walk the pair chain from clearing up to the predecessor, two
        # independent books per link; each link's pair is [pred1, pred2].
        prev_certs = [
            settled.get("total_spine_settlement_certificate") or {},
            confirmed_set.get("total_spine_settlement_certificate") or {},
        ]
        prev_result = confirmed_set
        tip_roots: dict[str, str] = {"settlement": tip_settlement}
        for name in pair_links:
            runner = runners[name]
            abbr = _CHAIN_ABBRS[name]
            first = runner(
                list(prev_certs),
                out_root=scratch / f"{abbr}-h1",
                prior_tip=str(
                    prev_result.get(f"total_spine_{TOTAL_SPINE_CHAIN[TOTAL_SPINE_CHAIN.index(name) - 1]}_bound_tip") or ""
                ),
                body=dict(prev_result),
                repo_path=REPO_ROOT,
                confirm=False,
            )
            cert_1 = first.get(f"total_spine_{name}_certificate") or {}
            tip_root = str(first.get(f"total_spine_tip_{name}_root") or "")
            pred_name = TOTAL_SPINE_CHAIN[TOTAL_SPINE_CHAIN.index(name) - 1]
            second = runner(
                list(prev_certs),
                out_root=scratch / f"{abbr}-h2",
                prior_tip=str(first.get(f"total_spine_{name}_bound_tip") or ""),
                **{
                    f"parent_{name}_root": tip_root,
                    f"{name}_height": int(first.get(f"total_spine_{name}_height") or 0) + 1,
                    "repo_path": REPO_ROOT,
                    "confirm": False,
                },
            )
            cert_2 = second.get(f"total_spine_{name}_certificate") or {}
            prev_certs = [cert_1, cert_2]
            prev_result = second
            tip_roots[name] = tip_root

        # The effect itself, offline.
        offline = run_pair_effect(
            spec,
            list(prev_certs),
            out_root=scratch / f"{spec.abbr}-h1",
            prior_tip=str(prev_result.get(f"{spec.pred_kind}_bound_tip") or ""),
            body=dict(prev_result),
            repo_path=REPO_ROOT,
            confirm=False,
        )
        cert_path = offline.get(f"{spec.kind}_path")
        tip_effect = str(offline.get(f"total_spine_tip_{spec.effect}_root") or "")
        offline_ok = (
            bool(offline.get("ok"))
            and offline.get(spec.kind) is True
            and offline.get(f"{spec.kind}_{spec.post_key}") is True
            and offline.get(f"{spec.kind}_irreversible") is True
            and offline.get(f"total_spine_{spec.adj_1}") is True
            and offline.get(f"total_spine_{spec.adj_2}") is True
            and offline.get(f"total_spine_{spec.code}_ok") is True
            and offline.get(f"{spec.kind}_atomic") is True
            and offline.get(f"{spec.kind}_one_sided") is False
            and int(offline.get(f"{spec.kind}_count") or 0) >= 2
            and int(offline.get(f"{spec.kind}_height") or 0) >= 2
            and int(offline.get(f"{spec.kind}_residual") or 0) == 0
            and int(offline.get(f"{spec.kind}_pair_count") or 0) >= 1
            and len(tip_effect) >= 32
            and str(offline.get("total_spine_state_root") or "") == state_root
            and str(offline.get("total_spine_tip_action_root") or "")
            == tip_action
            and str(offline.get("total_spine_digest") or "")
            != str(prev_certs[0].get("total_spine_digest") or "")
            and isinstance(cert_path, str)
            and Path(cert_path).is_file()
            and not legacy_pipeline_was_used()
        )

        loaded = load_certificate(spec, cert_path or scratch)
        verify_ok = bool(
            loaded.get(f"{spec.kind}_loaded")
            and (loaded.get(f"{spec.effect}_verify") or {}).get("ok")
            and (loaded.get(f"{spec.effect}_verify") or {}).get(f"{spec.effect}_root_ok")
            and (loaded.get(f"{spec.effect}_verify") or {}).get("chain_ok")
            and (loaded.get(f"{spec.effect}_verify") or {}).get(f"{spec.plural}_ok")
            and (loaded.get(f"{spec.effect}_verify") or {}).get(f"{spec.code}_ok")
        )

        tampered_path = scratch / f"tampered-{spec.effect}.json"
        tampered_body = dict(loaded)
        for drop in (
            f"{spec.effect}_verify",
            f"{spec.kind}_loaded",
            f"{spec.effect}_path",
        ):
            tampered_body.pop(drop, None)
        tampered_body[f"{spec.effect}_height"] = 99
        atomic_write_json(tampered_path, tampered_body)
        tamper_ok = False
        try:
            load_certificate(spec, tampered_path)
        except StageRefused as exc:
            tamper_ok = str(exc.verdict) == f"{spec.kind}_tampered"
        except Exception:  # noqa: BLE001
            tamper_ok = False

        supersession_ok = False
        try:
            write_certificate(
                spec,
                scratch / f"{spec.abbr}-h1",
                {
                    **{
                        k: v
                        for k, v in loaded.items()
                        if k
                        not in {
                            f"{spec.effect}_verify",
                            f"{spec.kind}_loaded",
                            f"{spec.effect}_path",
                            f"{spec.effect}_digest",
                            "certificate_hash",
                            f"{spec.adj_1}_at",
                            spec.kind,
                            f"{spec.kind}_impl",
                            "used_skill_route_discovery",
                            "contract_eval",
                        }
                    },
                    "goal": "forged-supersession-goal",
                    f"tip_{spec.effect}_root": "",
                },
            )
        except StageRefused as exc:
            supersession_ok = (
                str(exc.verdict) == f"{spec.kind}_supersession_refused"
            )
        except Exception:  # noqa: BLE001
            supersession_ok = False

        wrong_root_ok = False
        wrong_body = dict(loaded)
        for drop in (
            f"{spec.effect}_verify",
            f"{spec.kind}_loaded",
            f"{spec.effect}_path",
        ):
            wrong_body.pop(drop, None)
        wrong_body["bound_state_root"] = "f" * 64
        resealed = seal_certificate(spec, wrong_body)
        wrong_verify = verify_certificate(spec, resealed)
        wrong_root_ok = wrong_verify.get("ok") is False and (
            wrong_verify.get("chain_ok") is False
            or wrong_verify.get(f"{spec.effect}_root_ok") is False
        )

        mismatch_ok = False
        try:
            mixed = dict(prev_certs[0])
            mixed["bound_state_root"] = "e" * 64
            book_predecessors(
                spec,
                [prev_certs[0], mixed],
                min_count=2,
            )
        except StageRefused:
            mismatch_ok = True
        except Exception:  # noqa: BLE001
            mismatch_ok = False

        one_sided_ok = False
        try:
            from blackhole_agent import upstream_control_engine as _ce2

            seal_pred = getattr(_ce2, f"seal_total_spine_{spec.pred}_certificate")
            forged = dict(prev_certs[1])
            forged["capabilities"] = ["capability.one-sided-only"]
            for drop in (
                f"{spec.pred}_digest",
                "certificate_hash",
                f"{spec.pred_done}_at",
                f"{spec.pred}_path",
                f"{spec.pred}_verify",
                f"{spec.pred_kind}_loaded",
            ):
                forged.pop(drop, None)
            resealed_one = seal_pred(forged)
            book_predecessors(
                spec,
                [prev_certs[0], resealed_one],
                min_count=2,
            )
        except StageRefused as exc:
            one_sided_ok = str(exc.verdict) == f"{spec.kind}_one_sided"
        except Exception:  # noqa: BLE001
            one_sided_ok = False

        partial_ok = False
        try:
            _assert_pairs_atomic(
                spec,
                [
                    {
                        "capability_id": good_id,
                        spec.verdict_1: True,
                        spec.verdict_2: False,
                        "atomic_ok": False,
                    }
                ],
            )
        except StageRefused as exc:
            partial_ok = str(exc.verdict) == f"{spec.kind}_partial"
        except Exception:  # noqa: BLE001
            partial_ok = False

        h2 = run_pair_effect(
            spec,
            list(prev_certs),
            out_root=scratch / f"{spec.abbr}-h2",
            prior_tip=str(
                offline.get(f"{spec.kind}_bound_tip") or ""
            ),
            **{
                f"parent_{spec.effect}_root": tip_effect,
                f"{spec.effect}_height": int(
                    offline.get(f"{spec.kind}_height") or 0
                )
                + 1,
                "repo_path": REPO_ROOT,
                "confirm": False,
            },
        )
        multi_height_ok = (
            bool(h2.get("ok"))
            and int(h2.get(f"{spec.kind}_count") or 0) >= 2
            and str(h2.get(f"total_spine_tip_{spec.effect}_root") or "") != tip_effect
            and str(
                (h2.get(f"{spec.kind}_certificate") or {}).get(
                    f"parent_{spec.effect}_root"
                )
                or ""
            )
            == tip_effect
        )

        recomputed = compute_tip_root(
            spec,
            loaded.get(spec.plural) or [],
        )
        determinism_ok = recomputed == tip_effect and bool(recomputed)

        live_kwargs = {
            name: True for name in TOTAL_SPINE_CHAIN[:eff_idx + 1]
        }
        live = ce.run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / f"live-{spec.abbr}",
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
            effect_timeout=90,
            repo_path=REPO_ROOT,
            **live_kwargs,
        )
        live_cert_path = live.get(f"{spec.kind}_path")
        live_ok = (
            bool(live.get("ok"))
            and live.get("total_spine") is True
            and live.get("total_spine_finality") is True
            and live.get("total_spine_federation") is True
            and live.get("total_spine_quorum") is True
            and live.get("total_spine_execution") is True
            and live.get("total_spine_actuation") is True
            and all(
                live.get(f"total_spine_{name}") is True
                for name in TOTAL_SPINE_CHAIN[:eff_idx + 1]
            )
            and live.get(f"total_spine_{spec.adj_1}") is True
            and live.get(f"total_spine_{spec.code}_ok") is True
            and int(live.get(f"{spec.kind}_count") or 0) >= 2
            and isinstance(live.get(f"total_spine_tip_{spec.effect}_root"), str)
            and len(str(live.get(f"total_spine_tip_{spec.effect}_root"))) >= 32
            and int(live.get("total_nest_depth") or 0) == 28
            and isinstance(live_cert_path, str)
            and Path(live_cert_path).is_file()
            and not legacy_pipeline_was_used()
        )

        shorted = ce.run_total_spine(
            root_layer="quettacontinuum",
            out_root=scratch / f"short-{spec.abbr}",
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
            resume_dir=live_cert_path or (scratch / f"live-{spec.abbr}"),
            effect_timeout=90,
            repo_path=REPO_ROOT,
            **live_kwargs,
        )
        short_ok = (
            bool(shorted.get("ok"))
            and shorted.get(spec.kind) is True
            and shorted.get(f"{spec.kind}_short_circuit") is True
            and str(shorted.get(f"total_spine_tip_{spec.effect}_root") or "")
            == str(live.get(f"total_spine_tip_{spec.effect}_root") or "")
            and int(shorted.get("total_nest_depth") or 0) == 28
            and not legacy_pipeline_was_used()
        )

        cap_chain = live.get(f"{spec.kind}_chain") or {}
        chain_integrity_ok = False
        if isinstance(cap_chain, Mapping) and cap_chain:
            re_seal = seal_chain(
                spec,
                prior_tip=str(cap_chain.get("prior_tip") or ""),
                effect_digest=str(cap_chain.get(f"{spec.effect}_digest") or ""),
                tip_effect_root=str(cap_chain.get(f"tip_{spec.effect}_root") or ""),
                bound_pred_root=str(
                    cap_chain.get(f"bound_{spec.pred}_root") or ""
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
                pred_digest=str(cap_chain.get(f"{spec.pred}_digest") or ""),
                delivery_digest=str(cap_chain.get("delivery_digest") or ""),
                effect_height=int(cap_chain.get(f"{spec.effect}_height") or 0),
                short_circuit=bool(cap_chain.get("short_circuit")),
            )
            chain_integrity_ok = (
                re_seal.get("digest") == cap_chain.get("digest")
                and re_seal.get("digest") == live.get(f"{spec.kind}_tip")
            )

        differential_ok = (
            offline_ok
            and live_ok
            and str(prev_certs[0].get("total_spine_digest") or "")
            != str(offline.get("total_spine_digest") or "")
        )

        # Synthesized-module architecture: the effect's public names are
        # bound on the synthesized module and re-exported by the control
        # engine (delegation identity through the PEP 562 facade).
        synth = sys.modules[f"blackhole_agent.upstream_total_spine_{spec.effect}"]
        runner_name = f"{spec.verb}_total_spine"
        proof_name = f"builtin_total_spine_{spec.effect}_proof"
        impl_name = f"TOTAL_SPINE_{spec.upper}_IMPL"
        source_ok = (
            getattr(le_facade, impl_name, None) is True
            and getattr(le_facade, proof_name, None) is getattr(synth, proof_name)
            and getattr(le_facade, runner_name, None) is getattr(synth, runner_name)
            and callable(getattr(le_facade, proof_name, None))
            and callable(getattr(le_facade, runner_name, None))
        )

        engine_path = Path(ce.__file__).resolve()
        engine_text = engine_path.read_text(encoding="utf-8")
        engine_source_ok = (
            impl_name in engine_text
            and runner_name in engine_text
            and (
                f"{spec.effect}=True" in engine_text
                or f"{spec.effect}: bool = False" in engine_text
            )
            and proof_name in engine_text
        )

        engine_mod_path = Path(__file__).resolve()
        engine_mod_text = engine_mod_path.read_text(encoding="utf-8")
        mod_source_ok = (
            spec.effect in PAIR_EFFECT_SPECS
            and f'effect="{spec.effect}"' in engine_mod_text
            and "def run_pair_effect" in engine_mod_text
            and "def verify_certificate" in engine_mod_text
        )

        ledger_path = default_ledger_path(REPO_ROOT)
        ledger_ok = False
        try:
            ledger = load_ledger(ledger_path)
            entry = ledger.capabilities.get(
                f"capability.upstream-total-spine-{spec.effect}"
            )
            tags_blob = " ".join(entry.tags).lower() if entry else ""
            delta_blob = (entry.capability_delta or "").lower() if entry else ""
            name_blob = (entry.name or "").lower() if entry else ""
            ledger_ok = (
                entry is not None
                and (
                    f"upstream_total_spine_{spec.effect}" in (entry.entry or "")
                    or "upstream_control_engine" in (entry.entry or "")
                )
                and proof_name in (entry.entry or "")
                and (
                    spec.effect in tags_blob
                    or spec.effect in name_blob
                    or spec.effect in delta_blob
                )
                and ("total" in tags_blob or "total" in name_blob)
                and (
                    f"{spec.verb}_total_spine" in delta_blob
                    or f"post-{spec.pred}" in delta_blob
                    or f"post_{spec.pred}" in delta_blob
                    or spec.pred_code in delta_blob
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
        result: dict[str, Any] = {
            "ok": ok,
            "action": f"{spec.kind}_proof",
            "flags_ok": flags_ok,
            "offline_ok": offline_ok,
            f"{spec.effect}_path": cert_path,
            f"tip_{spec.effect}_root": tip_effect,
        }
        for name in reversed(TOTAL_SPINE_CHAIN[:pred_idx + 1]):
            result[f"tip_{name}_root"] = tip_roots.get(name, "")
        result.update(
            {
                "tip_action_root": tip_action,
                "state_root": state_root,
                f"{spec.effect}_count": offline.get(f"{spec.kind}_count"),
                "pair_count": offline.get(f"{spec.kind}_pair_count"),
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
                f"live_{spec.effect}_path": live_cert_path,
                f"live_tip_{spec.effect}_root": live.get(f"total_spine_tip_{spec.effect}_root"),
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
                spec.kind: True,
            }
        )
        for extra_flag in spec.out_extra_flags:
            result[f"total_spine_{extra_flag}"] = True
        result.update(
            {
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
        )
        return result
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# Synthesis: per-effect modules with exact historical names and signatures.
# ---------------------------------------------------------------------------

_EFFECT_MODULE_PREFIX = "blackhole_agent.upstream_total_spine_"


def _forward(spec: PairEffectSpec, public_name: str, ns: dict[str, Any]) -> Any:
    """Dispatch one synthesized public call to the generic implementation."""

    if public_name == f"{spec.verb}_total_spine":
        source = ns.pop("source", None)
        return run_pair_effect(spec, source, **ns)
    if public_name == f"book_total_spine_{spec.pred_plural}":
        return book_predecessors(
            spec,
            ns["margins"],
            min_count=ns[f"min_{spec.plural}"],
            parent_root=ns[f"parent_{spec.effect}_root"],
            effect_height=ns[f"{spec.effect}_height"],
        )
    if public_name == f"compute_total_spine_{spec.effect}_root":
        return compute_tip_root(spec, ns[spec.pred_plural])
    if public_name == f"{spec.effect}_certificate_path":
        return certificate_path(spec, ns["root"])
    if public_name == f"write_total_spine_{spec.effect}_certificate":
        return write_certificate(
            spec, ns["out_root"], ns["body"], allow_idempotent=ns["allow_idempotent"]
        )
    if public_name == f"verify_total_spine_{spec.effect}_certificate":
        return verify_certificate(spec, ns["certificate"])
    if public_name == f"load_total_spine_{spec.effect}_certificate":
        return load_certificate(spec, ns["path"])
    if public_name == f"seal_total_spine_{spec.effect}_certificate":
        return seal_certificate(spec, ns["body"])
    if public_name == f"seal_total_spine_{spec.effect}_chain":
        return seal_chain(
            spec,
            prior_tip=ns["prior_tip"],
            effect_digest=ns[f"{spec.effect}_digest"],
            tip_effect_root=ns[f"tip_{spec.effect}_root"],
            bound_pred_root=ns[f"bound_{spec.pred}_root"],
            bound_delivery_root=ns["bound_delivery_root"],
            bound_clearing_root=ns["bound_clearing_root"],
            bound_settlement_root=ns["bound_settlement_root"],
            bound_action_root=ns["bound_action_root"],
            bound_state_root=ns["bound_state_root"],
            actuation_digest=ns["actuation_digest"],
            pred_digest=ns[f"{spec.pred}_digest"],
            delivery_digest=ns["delivery_digest"],
            effect_height=ns[f"{spec.effect}_height"],
            short_circuit=ns.get("short_circuit", False),
        )
    if public_name == f"annotate_total_spine_{spec.effect}":
        return annotate(
            spec,
            ns["body"],
            certificate=ns["certificate"],
            prior_tip=ns["prior_tip"],
            short_circuit=ns.get("short_circuit", False),
        )
    if public_name == f"builtin_total_spine_{spec.effect}_proof":
        return _builtin_pair_effect_proof(spec)
    raise KeyError(f"no generic implementation for {public_name!r}")


def _effect_main(spec: PairEffectSpec, argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=spec.summary)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        f"{spec.effect}-proof",
        help=f"Total spine {spec.pred} proof: post-{spec.pred} atomic {spec.pred_code_upper} seals",
    )
    sub.add_parser("proof", help=f"Alias for {spec.effect}-proof")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd in {f"{spec.effect}-proof", "proof"}:
        result = _builtin_pair_effect_proof(spec)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


def _synthesize_effect_module(spec: PairEffectSpec) -> Any:
    """Materialize ``blackhole_agent.upstream_total_spine_<effect>``."""

    import types

    fullname = f"{_EFFECT_MODULE_PREFIX}{spec.effect}"
    module = sys.modules.get(fullname)
    if module is not None and module.__dict__.get(f"TOTAL_SPINE_{spec.upper}_IMPL"):
        return module
    if module is None:
        module = types.ModuleType(fullname)
        sys.modules[fullname] = module
    module.__file__ = f"<upstream-total-spine-effect:{spec.effect}>"
    module.__doc__ = spec.summary
    g = module.__dict__
    # Match the physical modules' import surface (public names in api-surface).
    import __future__
    import json as _json
    from typing import Any as _Any, Mapping as _Mapping, Sequence as _Sequence

    g["annotations"] = __future__.annotations
    g["json"] = _json
    g["Path"] = Path
    g["Any"] = _Any
    g["Mapping"] = _Mapping
    g["Sequence"] = _Sequence
    g["atomic_write_json"] = atomic_write_json
    g["durable_read_path"] = durable_read_path
    g["legacy_pipeline_was_used"] = legacy_pipeline_was_used
    g["utc_now_iso"] = utc_now_iso
    g["SCHEMA_VERSION"] = SCHEMA_VERSION
    g["REPO_ROOT"] = REPO_ROOT
    g["TOTAL_SPINE_DEFAULT_ROOT"] = TOTAL_SPINE_DEFAULT_ROOT
    g["StageRefused"] = StageRefused
    g[f"TOTAL_SPINE_{spec.upper}_IMPL"] = True
    g[f"TOTAL_SPINE_{spec.upper}_KIND"] = spec.kind
    g[f"TOTAL_SPINE_{spec.upper}_FILENAME"] = spec.filename
    g[f"TOTAL_SPINE_{spec.upper}_MIN_{spec.min_name}"] = spec.min_value
    g[f"TOTAL_SPINE_{spec.pred_upper}_KIND"] = spec.pred_kind

    public_functions = {
        f"annotate_total_spine_{spec.effect}",
        f"book_total_spine_{spec.pred_plural}",
        f"builtin_total_spine_{spec.effect}_proof",
        f"compute_total_spine_{spec.effect}_root",
        f"load_total_spine_{spec.effect}_certificate",
        f"seal_total_spine_{spec.effect}_certificate",
        f"seal_total_spine_{spec.effect}_chain",
        f"verify_total_spine_{spec.effect}_certificate",
        f"write_total_spine_{spec.effect}_certificate",
        f"{spec.verb}_total_spine",
        f"{spec.effect}_certificate_path",
    }
    for public_name, signature in spec.signatures.items():
        if public_name == "main":
            stub = (
                "from __future__ import annotations\n"
                "from pathlib import Path\n"
                "from typing import Any, Mapping, Sequence\n"
                f"def main{signature}:\n"
                "    return _effect_main(_SPEC, argv)\n"
            )
            stub_ns = dict(g)
            stub_ns["_effect_main"] = _effect_main
            stub_ns["_SPEC"] = spec
            exec(compile(stub, f"<upstream-total-spine-effect {spec.effect}>", "exec"), stub_ns)
            g["main"] = stub_ns["main"]
            continue
        if public_name not in public_functions:
            continue
        stub = (
            "from __future__ import annotations\n"
            "from pathlib import Path\n"
            "from typing import Any, Mapping, Sequence\n"
            f"def {public_name}{signature}:\n"
            f"    return _forward(_SPEC, {public_name!r}, locals())\n"
        )
        stub_ns: dict[str, Any] = dict(g)
        stub_ns["_forward"] = _forward
        stub_ns["_SPEC"] = spec
        exec(compile(stub, f"<upstream-total-spine-effect {spec.effect}>", "exec"), stub_ns)
        g[public_name] = stub_ns[public_name]
    return module


class _PairEffectLoader(Loader):
    def __init__(self, fullname: str, spec: PairEffectSpec) -> None:
        self._fullname = fullname
        self._spec = spec

    def create_module(self, spec_obj: ModuleSpec) -> None:
        return None

    def exec_module(self, module: Any) -> None:
        synthesized = _synthesize_effect_module(self._spec)
        module.__dict__.update(synthesized.__dict__)

    def get_code(self, fullname: str) -> Any:
        source = (
            "from blackhole_agent.upstream_total_spine_effects import _effect_main_from_module\n"
            f"_effect_main_from_module({self._spec.effect!r}, globals())\n"
        )
        return compile(source, f"<upstream-total-spine-effect {self._spec.effect}>", "exec")


def _effect_main_from_module(effect: str, module_globals: dict[str, Any]) -> None:
    """``python -m`` entry: synthesize the namespace, then run its main."""

    spec = PAIR_EFFECT_SPECS[effect]
    module = _synthesize_effect_module(spec)
    for key, value in module.__dict__.items():
        if not (key.startswith("__") and key.endswith("__")):
            module_globals[key] = value
    if module_globals.get("__name__") == "__main__":
        sys.exit(_effect_main(spec))


class _PairEffectFinder(MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> ModuleSpec | None:
        if not fullname.startswith(_EFFECT_MODULE_PREFIX):
            return None
        effect = fullname[len(_EFFECT_MODULE_PREFIX):]
        spec = PAIR_EFFECT_SPECS.get(effect)
        if spec is None:
            return None
        return ModuleSpec(
            fullname,
            _PairEffectLoader(fullname, spec),
            origin=f"<upstream-total-spine-effect:{effect}>",
            is_package=False,
        )


def install_pair_effect_finder() -> None:
    """Idempotently install the pair-effect meta-path finder."""

    if not any(isinstance(finder, _PairEffectFinder) for finder in sys.meta_path):
        sys.meta_path.append(_PairEffectFinder())
