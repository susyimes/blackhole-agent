"""Total-spine pair-effect engine: 15 generated modules collapse into data + one logic core.

Every ``upstream_total_spine_<effect>`` module from delivery through
reorganization was a mechanically generated copy of the same pair-booking
logic: confirm a second predecessor book, pair it with this effect's
requirement, seal a hash-chained irreversible certificate, rebind the tip.
The only real differences are per-effect tokens (nouns, pair codes, verdict
fields, adjectives, refusal-kind suffixes, and a few historical residue
strings). Those now live in :data:`PAIR_EFFECT_SPECS`; leftover public
signature blocks derive from tokens plus a compact quirk overlay.
The logic lives here once.

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
from dataclasses import dataclass, replace
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
    refusal_pred_short: str  # margins_short
    refusal_pred_not_done: str  # capital_uncapitalized
    refusal_pred_unmet: str  # capital_unrequired
    refusal_code_failed: str  # cva_failed
    summary: str  # one-line module summary (CLI description)
    refusal_pred_partial: str | None = None  # margin_partial (None: no atomic check, e.g. delivery)
    out_extra_flags: tuple[str, ...] = ()  # extra total_spine_* booleans in proof output
    proof_goal: str = ""  # finality-origin goal prose (residue; default: "<effect> proof origin")
    chain_tag: str = ""  # chain-material prefix (residue: "risk" for stress..reorganization)
    # Confirm-step plan (historical divergence carried as data):
    confirm_source: str = "first_or_bundle"  # first_or_bundle | bundle | preds_or_body | list:<role>
    confirm_kwargs: tuple[str, ...] | None = None  # roles; default preds+margins+clearings+settlements+actuation+body
    confirm_accessor_plural: str = ""  # accessor feeding preds (default: pred-of-pred plural)
    confirm_drops: str = "base"  # base | none | self_loaded
    refusal_confirm_missing: str = "confirmation_missing"
    book_fn_prefix: str = "book"  # historical book-function prefix ("pair" for delivery)
    # pred block in annotate: three setdefault suffixes (default: pred, pred_done, <pred_code>_ok)
    pred_block: tuple[str, str, str] | None = None
    # _book_signature shape: (sig row sources, include clearing root, include delivery root,
    # signatures key, include pair_count, count key)
    book_sig: tuple[tuple[str, ...], bool, bool, str, bool, str] | None = None
    chain_layout: str = "full"  # "full" | "delivery" | "custody" (seal-chain material slot layout)
    # runner contract ctx: {outer, inner[(key, role)...], outer_extra[(key, role)...]}; roles: true|count:<noun>|tip|state
    ctx: dict[str, Any] | None = None
    out_tip_skip: tuple[str, ...] = ()  # chain members omitted from printed tip roots (recovery skips risk)
    # mis-keyed height reads in the historical proof second calls: link -> wrong noun
    second_height_miskey: dict[str, str] | None = None
    # printed tip roots sourced from a different link (recovery prints risk's tip under tip_stress_root)
    out_tip_alias: dict[str, str] | None = None
    live_dir: str = ""  # proof live-run dir (default: live-<abbr>)
    short_dir: str = ""  # proof short-circuit run dir (default: short-<abbr>)
    short_resume_dir: str = ""  # short-run resume fallback (default: live-<abbr>)
    # Optional leftover override. Live rows leave this empty so
    # :func:`derive_pair_effect_signatures` fills the historical surface.
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


SPINE_SIGNATURE_CATALOG_IMPL = True
_EARLY_PRED = frozenset({"clearing", "delivery", "custody", "margin"})


def pair_effect_public_names(spec: PairEffectSpec) -> tuple[str, ...]:
    """Historical public function names on one synthesized pair-effect module."""

    return (
        f"annotate_total_spine_{spec.effect}",
        f"{spec.book_fn_prefix}_total_spine_{spec.pred_plural}",
        f"builtin_total_spine_{spec.effect}_proof",
        f"compute_total_spine_{spec.effect}_root",
        f"load_total_spine_{spec.effect}_certificate",
        f"seal_total_spine_{spec.effect}_certificate",
        f"seal_total_spine_{spec.effect}_chain",
        f"verify_total_spine_{spec.effect}_certificate",
        f"write_total_spine_{spec.effect}_certificate",
        f"{spec.verb}_total_spine",
        f"{spec.effect}_certificate_path",
        "main",
    )


def pair_effect_surface_names(spec: PairEffectSpec) -> tuple[str, ...]:
    """Control-engine names historically imported from one pair-effect module."""

    return (
        f"TOTAL_SPINE_{spec.upper}_FILENAME",
        f"TOTAL_SPINE_{spec.upper}_IMPL",
        f"TOTAL_SPINE_{spec.upper}_KIND",
        f"TOTAL_SPINE_{spec.upper}_MIN_{spec.min_name}",
        *pair_effect_public_names(spec)[:-1],
    )


def pair_effect_signature_quirks(spec: PairEffectSpec) -> dict[str, Any]:
    """Historical leftover signature slices that are data, not another block."""

    early = spec.pred in _EARLY_PRED
    book_arg = spec.pred_plural if early else "margins"
    if spec.chain_tag == "risk" and spec.pred != "risk":
        compute_arg = "risks"
    elif early:
        compute_arg = spec.plural
    else:
        compute_arg = spec.pred_plural
    return {
        "book_arg": book_arg,
        "compute_arg": compute_arg,
        "runner_margins": book_arg == "margins" and spec.pred_plural != "margins",
        "runner_clearings": spec.effect != "delivery",
        "chain_layout": spec.chain_layout,
    }


def _format_signature(params: Sequence[str], ret: str, *, oneline: bool = False) -> str:
    if not params:
        return f"() -> {ret}"
    if oneline:
        return f"({params[0]}) -> {ret}"
    return "(\n    " + ",\n    ".join(params) + ",\n) -> " + ret


def derive_pair_effect_signatures(spec: PairEffectSpec) -> dict[str, str]:
    """Build the historical public signature block from tokens + quirks.

    A new pair-effect family is a token row. The 12-function signature
    copy is derived. Probe specs with empty ``signatures`` still get a
    full public surface.
    """

    quirks = pair_effect_signature_quirks(spec)
    min_const = f"TOTAL_SPINE_{spec.upper}_MIN_{spec.min_name}"
    seq_map = "Sequence[Mapping[str, Any]]"
    seq_path = "Sequence[Mapping[str, Any] | Path | str]"
    book_name = f"{spec.book_fn_prefix}_total_spine_{spec.pred_plural}"
    runner_params = [
        "source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None",
        "*",
        f"{spec.pred_plural}: {seq_path} | None = None",
    ]
    if quirks["runner_margins"]:
        runner_params.append(f"margins: {seq_path} | None = None")
    runner_params.extend(
        [
            "out_root: Path | None = None",
            "prior_tip: str | None = None",
            "body: dict[str, Any] | None = None",
            f"min_{spec.plural}: int = {min_const}",
            f"parent_{spec.effect}_root: str = \"\"",
            f"{spec.effect}_height: int | None = None",
            "short_circuit: bool = False",
            "repo_path: Path | None = None",
            "confirm: bool = True",
            "actuation: Mapping[str, Any] | None = None",
            "settlements: Sequence[Mapping[str, Any]] | None = None",
        ]
    )
    if quirks["runner_clearings"]:
        runner_params.append("clearings: Sequence[Mapping[str, Any]] | None = None")

    if spec.chain_layout == "delivery":
        chain_params = [
            "prior_tip: str",
            f"{spec.effect}_digest: str",
            f"tip_{spec.effect}_root: str",
            f"bound_{spec.pred}_root: str",
            "bound_settlement_root: str",
            "bound_action_root: str",
            "bound_state_root: str",
            "actuation_digest: str",
            f"{spec.pred}_digest: str",
            f"{spec.effect}_height: int",
            "short_circuit: bool = False",
        ]
    elif spec.chain_layout == "custody":
        chain_params = [
            "prior_tip: str",
            f"{spec.effect}_digest: str",
            f"tip_{spec.effect}_root: str",
            f"bound_{spec.pred}_root: str",
            "bound_clearing_root: str",
            "bound_settlement_root: str",
            "bound_action_root: str",
            "bound_state_root: str",
            "actuation_digest: str",
            f"{spec.pred}_digest: str",
            f"{spec.effect}_height: int",
            "short_circuit: bool = False",
        ]
    else:
        chain_params = [
            "prior_tip: str",
            f"{spec.effect}_digest: str",
            f"tip_{spec.effect}_root: str",
            f"bound_{spec.pred}_root: str",
            "bound_delivery_root: str",
            "bound_clearing_root: str",
            "bound_settlement_root: str",
            "bound_action_root: str",
            "bound_state_root: str",
            "actuation_digest: str",
            f"{spec.pred}_digest: str",
            "delivery_digest: str",
            f"{spec.effect}_height: int",
            "short_circuit: bool = False",
        ]

    names = pair_effect_public_names(spec)
    return {
        names[0]: _format_signature(
            [
                "body: dict[str, Any]",
                "*",
                "certificate: Mapping[str, Any]",
                "prior_tip: str",
                "short_circuit: bool = False",
            ],
            "dict[str, Any]",
        ),
        book_name: _format_signature(
            [
                f"{quirks['book_arg']}: {seq_map}",
                "*",
                f"min_{spec.plural}: int = {min_const}",
                f"parent_{spec.effect}_root: str = \"\"",
                f"{spec.effect}_height: int | None = None",
            ],
            "list[dict[str, Any]]",
        ),
        names[2]: _format_signature((), "dict[str, Any]"),
        names[3]: _format_signature(
            [f"{quirks['compute_arg']}: {seq_map}"],
            "str",
        ),
        names[4]: _format_signature(["path: Path | str"], "dict[str, Any]"),
        names[5]: _format_signature(["body: Mapping[str, Any]"], "dict[str, Any]"),
        names[6]: _format_signature(["*", *chain_params], "dict[str, Any]"),
        names[7]: _format_signature(
            ["certificate: Mapping[str, Any]"], "dict[str, Any]"
        ),
        names[8]: _format_signature(
            [
                "out_root: Path",
                "body: Mapping[str, Any]",
                "*",
                "allow_idempotent: bool = True",
            ],
            "dict[str, Any]",
        ),
        names[9]: _format_signature(runner_params, "dict[str, Any]"),
        names[10]: _format_signature(["root: Path"], "Path", oneline=True),
        names[11]: _format_signature(
            ["argv: Sequence[str] | None = None"], "int", oneline=True
        ),
    }


SPINE_CONTRACT_CATALOG_IMPL = True
# Historical materializer scratch prefixes that drifted from spec.abbr.
_CONTRACT_CHAIN_ABBR_QUIRKS: dict[str, str] = {
    "clearing": "clr",
    "restructuring": "rst",
    "reorganization": "reo",
}


def pair_effect_contract_quirks(spec: PairEffectSpec) -> dict[str, Any]:
    """Historical leftover contract-materializer slices that are data."""

    adj_ok = f"{spec.adj_1}_ok"
    effect_ok = f"{spec.effect}_ok"
    include_verdict_1 = spec.verdict_1 not in {adj_ok, effect_ok} and spec.effect != "delivery"
    include_verdict_2 = spec.effect != "delivery"
    include_adj_2_ok = spec.effect != "delivery" and bool(spec.adj_2)
    extra_before_code = ("liquid_ok",) if spec.effect == "liquidity" else ()
    return {
        "include_verdict_1": include_verdict_1,
        "include_verdict_2": include_verdict_2,
        "include_adj_2_ok": include_adj_2_ok,
        "extra_before_code": extra_before_code,
        "abbr": _CONTRACT_CHAIN_ABBR_QUIRKS.get(spec.effect, spec.abbr),
    }


def derive_pair_effect_contract_config(spec: PairEffectSpec) -> dict[str, Any]:
    """Build the historical outcome-contract materializer row from tokens.

    A new pair-effect family is a token row. The leftover ``_MAT_PAIR_CONFIG``
    copy is derived. Probe specs still get a full materializer surface.
    """

    quirks = pair_effect_contract_quirks(spec)
    effect = spec.effect
    fields: dict[str, list[Any]] = {
        "action": ["lit", f"total_spine_{effect}_contract"],
        spec.adj_1: ["lit", True],
        f"{spec.adj_1}_ok": ["lit", True],
    }
    for extra in quirks["extra_before_code"]:
        fields[extra] = ["lit", True]
    if quirks["include_verdict_1"]:
        fields[spec.verdict_1] = ["lit", True]
    fields[f"{spec.code}_ok"] = ["lit", True]
    if quirks["include_verdict_2"]:
        fields[spec.verdict_2] = ["lit", True]
    if quirks["include_adj_2_ok"]:
        fields[f"{spec.adj_2}_ok"] = ["lit", True]
    fields.update(
        {
            f"{effect}_root_valid": ["lit", True],
            f"{effect}_count": ["int", f"total_spine_{effect}_count", "0"],
            "tip_height": ["int", f"total_spine_{effect}_height", "0"],
            f"{effect}_root": ["get", f"'total_spine_tip_{effect}_root'"],
            f"tip_{effect}_root": ["get", f"'total_spine_tip_{effect}_root'"],
            "bound_state_root": ["get", "'total_spine_state_root'"],
            "bound_action_root": ["get", "'total_spine_tip_action_root'"],
            f"bound_{spec.pred}_root": ["get", f"'total_spine_tip_{spec.pred}_root'"],
            f"{effect}_certificate": ["get", f"'total_spine_{effect}_certificate'"],
            "certificate_valid": ["lit", True],
            f"total_spine_{effect}": ["lit", True],
            "ledger_capability_ok": ["ledger"],
            "used_skill_route_discovery": ["bool", "'used_skill_route_discovery'"],
        }
    )
    return {
        "family": "inline",
        "abbr": quirks["abbr"],
        "ledger_tokens": [effect, spec.code],
        "fields": fields,
        "ok_terms": [
            ["bool", "ok"],
            ["is", f"total_spine_{effect}", True],
            ["is", f"total_spine_{spec.adj_1}", True],
            ["is", f"total_spine_{spec.code}_ok", True],
            ["min", f"total_spine_{effect}_count", 2],
            ["bool", f"total_spine_tip_{effect}_root"],
            ["ledger"],
            ["not_bool", "used_skill_route_discovery"],
        ],
    }


def derive_pair_effect_contract_kinds(spec: PairEffectSpec) -> frozenset[str]:
    """Predicate kinds that trigger one pair-effect contract materializer."""

    quirks = pair_effect_contract_quirks(spec)
    kinds = {
        f"{spec.effect}_ok",
        f"{spec.adj_1}_ok",
        f"min_{spec.plural}",
        f"{spec.effect}_root_valid",
        f"{spec.code}_ok",
    }
    kinds.update(quirks["extra_before_code"])
    if quirks["include_verdict_1"]:
        kinds.add(spec.verdict_1)
    if quirks["include_verdict_2"]:
        kinds.add(spec.verdict_2)
    if quirks["include_adj_2_ok"]:
        kinds.add(f"{spec.adj_2}_ok")
    return frozenset(kinds)


def derive_pair_effect_contract_catalog(
    *,
    pair_families: Sequence[str] | None = None,
    extra: Sequence[PairEffectSpec] = (),
) -> dict[str, dict[str, Any]]:
    """Live or probe contract-materializer catalog. A probe extra is not live."""

    if pair_families is None:
        specs = list(PAIR_EFFECT_SPECS.values())
    else:
        specs = [PAIR_EFFECT_SPECS[name] for name in pair_families]
    catalog = {spec.effect: derive_pair_effect_contract_config(spec) for spec in specs}
    for spec in extra:
        catalog[spec.effect] = derive_pair_effect_contract_config(spec)
    return catalog


def derive_pair_effect_contract_kind_sets(
    *,
    pair_families: Sequence[str] | None = None,
) -> tuple[tuple[str, frozenset[str]], ...]:
    """Pair-effect materializer kind-sets in tower order."""

    if pair_families is None:
        names = [name for name in TOTAL_SPINE_CHAIN if name in PAIR_EFFECT_SPECS]
    else:
        names = list(pair_families)
    return tuple(
        (name, derive_pair_effect_contract_kinds(PAIR_EFFECT_SPECS[name]))
        for name in names
    )


def derive_spine_contract_chain_maps(
    *,
    extra_chain: Sequence[tuple[str, str, str, str]] = (),
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Verb / predecessor / abbr maps for the inline materializer chain.

    Derived from :data:`SPINE_FAMILY_CHAIN` plus spec tokens. Clearing stays
    on the map (log-shaped predecessor of delivery). A probe extra chain row
    appears without mutating the live maps.
    """

    from blackhole_agent.upstream_spine_catalog import SPINE_FAMILY_CHAIN

    verbs: dict[str, str] = {}
    preds: dict[str, str] = {}
    abbrs: dict[str, str] = {}
    rows = tuple(SPINE_FAMILY_CHAIN) + tuple(extra_chain)
    started = False
    for name, pred, verb, _variant in rows:
        if name == "clearing" or started:
            started = True
            verbs[name] = verb
            preds[name] = pred
            if name in PAIR_EFFECT_SPECS:
                abbrs[name] = pair_effect_contract_quirks(PAIR_EFFECT_SPECS[name])[
                    "abbr"
                ]
            else:
                abbrs[name] = _CONTRACT_CHAIN_ABBR_QUIRKS.get(name, name[:3])
    return verbs, preds, abbrs


PAIR_EFFECT_SPECS: dict[str, PairEffectSpec] = {}


def _register(spec: PairEffectSpec) -> None:
    if not spec.signatures:
        spec = replace(spec, signatures=derive_pair_effect_signatures(spec))
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
        refusal_pred_tampered="margin_tampered",
        refusal_pred_partial="margin_partial",
        refusal_pred_short="margins_short",
        refusal_pred_not_done="capital_uncapitalized",
        refusal_pred_unmet="capital_unrequired",
        refusal_code_failed="cva_failed",
        summary="Post-capital solvency-versus-requirement for the absolute total spine.",
    )
)


_register(
    PairEffectSpec(
        effect="risk",
        plural="risks",
        verb="risk",
        pred="solvency",
        pred_plural="solvencies",
        code="rva",
        code_upper="RvA",
        pred_code="svr",
        pred_code_upper="SvR",
        verdict_1="assessed_ok",
        verdict_2="appetite_ok",
        adj_1="risked",
        adj_2="appetent",
        adj_1_negated="unrisked",
        counterpart="requirement",
        pred_done="solvent",
        pred_verdict_1="required",
        pred_verdict_2="svr_ok",
        post_key="post_risk",
        min_name="RISKS",
        collect_push=("solvency", "capital", "funding", "collateral", "margin", "custody", "delivery"),
        abbr="rsk",
        refusal_pred_tampered="margin_tampered",
        refusal_pred_partial="margin_partial",
        refusal_pred_short="margins_short",
        refusal_pred_not_done="capital_insolvent",
        refusal_pred_unmet="capital_unrequired",
        refusal_code_failed="svr_failed",
        summary="Post-solvency risk-versus-appetite for the absolute total spine.",
    )
)


_register(
    PairEffectSpec(
        effect="capital",
        plural="capitals",
        verb="capital",
        pred="funding",
        pred_plural="fundings",
        code="cva",
        code_upper="CvA",
        pred_code="fvr",
        pred_code_upper="FvR",
        verdict_1="buffer_ok",
        verdict_2="adequacy_ok",
        adj_1="capitalized",
        adj_2="adequate",
        adj_1_negated="uncapitalized",
        counterpart="requirement",
        pred_done="facilitated",
        pred_verdict_1="required",
        pred_verdict_2="fvr_ok",
        post_key="post_funding",
        min_name="CAPITALS",
        collect_push=("funding", "collateral", "margin", "custody", "delivery"),
        abbr="cap",
        refusal_pred_tampered="margin_tampered",
        refusal_pred_partial="margin_partial",
        refusal_pred_short="margins_short",
        refusal_pred_not_done="funding_unfacilitated",
        refusal_pred_unmet="funding_unrequired",
        refusal_code_failed="fvr_failed",
        out_extra_flags=(),
        proof_goal="funding proof origin",
        summary="Post-funding capital-versus-adequacy for the absolute total spine.",
    )
)


_register(
    PairEffectSpec(
        effect='stress',
        chain_tag='risk',
        plural='stresses',
        verb='stress',
        pred='risk',
        pred_plural='risks',
        code='svc',
        code_upper='Svc',
        pred_code='rva',
        pred_code_upper='Rva',
        verdict_1='stressed_ok',
        verdict_2='capacity_ok',
        adj_1='stressed',
        adj_2='capacious',
        adj_1_negated='unstressed',
        counterpart='requirement',
        pred_done='risked',
        pred_verdict_1='appetent',
        pred_verdict_2='rva_ok',
        post_key='post_stress',
        min_name='STRESSES',
        collect_push=('risk', 'capital', 'funding', 'collateral', 'margin', 'custody', 'delivery'),
        abbr='sts',
        refusal_pred_tampered='margin_tampered',
        refusal_pred_partial='margin_partial',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='capital_unrisked',
        refusal_pred_unmet='capital_unrequired',
        refusal_code_failed='rva_failed',
        summary='Post-risk stress-versus-capacity for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='recovery',
        out_tip_skip=('risk',),
        second_height_miskey={'risk': 'stress'},
        out_tip_alias={'stress': 'risk'},
        chain_tag='risk',
        plural='recoveries',
        verb='recovery',
        pred='stress',
        pred_plural='stresses',
        code='rvp',
        code_upper='Rvp',
        pred_code='svc',
        pred_code_upper='Svc',
        verdict_1='restored_ok',
        verdict_2='plan_ok',
        adj_1='restored',
        adj_2='planned',
        adj_1_negated='unrestored',
        counterpart='requirement',
        pred_done='stressed',
        pred_verdict_1='capacious',
        pred_verdict_2='svc_ok',
        post_key='post_recovery',
        min_name='RECOVERIES',
        collect_push=('stress', 'risk', 'capital', 'funding', 'collateral', 'margin', 'custody', 'delivery'),
        abbr='rec',
        refusal_pred_tampered='margin_tampered',
        refusal_pred_partial='margin_partial',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='capital_unstressed',
        refusal_pred_unmet='capital_uncapacitated',
        refusal_code_failed='svc_failed',
        summary='Post-stress recovery-versus-plan for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='resolution',
        chain_tag='risk',
        plural='resolutions',
        verb='resolution',
        pred='recovery',
        pred_plural='recoveries',
        code='rvs',
        code_upper='Rvs',
        pred_code='rvp',
        pred_code_upper='Rvp',
        verdict_1='resolved_ok',
        verdict_2='strategy_ok',
        adj_1='resolved',
        adj_2='strategic',
        adj_1_negated='unrestored',
        counterpart='requirement',
        pred_done='restored',
        pred_verdict_1='planned',
        pred_verdict_2='rvp_ok',
        post_key='post_resolution',
        min_name='RESOLUTIONS',
        collect_push=('recovery', 'risk', 'capital', 'funding', 'collateral', 'margin', 'custody', 'delivery'),
        abbr='res',
        out_extra_flags=('recovery',),
        refusal_pred_tampered='margin_tampered',
        refusal_pred_partial='margin_partial',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='capital_unrestored',
        refusal_pred_unmet='capital_uncapacitated',
        refusal_code_failed='rvp_failed',
        summary='Post-recovery resolution-versus-strategy for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='restructuring',
        chain_tag='risk',
        live_dir='live',
        short_dir='short',
        short_resume_dir='live-res',
        plural='restructurings',
        verb='restructuring',
        pred='resolution',
        pred_plural='resolutions',
        code='rvm',
        code_upper='Rvm',
        pred_code='rvs',
        pred_code_upper='Rvs',
        verdict_1='restructured_ok',
        verdict_2='mandate_ok',
        adj_1='restructured',
        adj_2='mandated',
        adj_1_negated='unresolved',
        counterpart='requirement',
        pred_done='resolved',
        pred_verdict_1='strategic',
        pred_verdict_2='rvs_ok',
        post_key='post_restructuring',
        min_name='RESTRUCTURINGS',
        collect_push=('resolution', 'risk', 'capital', 'funding', 'collateral', 'margin', 'custody', 'delivery'),
        abbr='res',
        out_extra_flags=('resolution',),
        refusal_pred_tampered='margin_tampered',
        refusal_pred_partial='margin_partial',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='capital_unresolved',
        refusal_pred_unmet='capital_uncapacitated',
        refusal_code_failed='rvs_failed',
        summary='Post-resolution restructuring-versus-mandate for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='emergence',
        live_dir='live',
        short_dir='short',
        short_resume_dir='live-emg',
        out_tip_skip=('restructuring',),
        out_tip_alias={'emergence': 'restructuring'},
        plural='emergences',
        verb='emerge',
        pred='restructuring',
        pred_plural='restructurings',
        code='evc',
        code_upper='Evc',
        pred_code='rvm',
        pred_code_upper='Rvm',
        verdict_1='emerged_ok',
        verdict_2='confirmation_ok',
        adj_1='emerged',
        adj_2='confirmed',
        adj_1_negated='unrestructured',
        counterpart='requirement',
        pred_done='restructured',
        pred_verdict_1='mandated',
        pred_verdict_2='rvm_ok',
        post_key='post_emergence',
        min_name='EMERGENCES',
        collect_push=('restructuring', 'risk', 'capital', 'funding', 'collateral', 'margin', 'custody', 'delivery'),
        abbr='emg',
        chain_tag='risk',
        out_extra_flags=('resolution',),
        confirm_source='preds_or_body',
        confirm_accessor_plural='restructurings',
        confirm_drops='self_loaded',
        refusal_pred_tampered='margin_tampered',
        refusal_pred_partial='margin_partial',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='capital_unrestructured',
        refusal_pred_unmet='capital_uncapacitated',
        refusal_code_failed='rvm_failed',
        summary='Post-restructuring emergence-versus-confirmation for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='reorganization',
        live_dir='live',
        short_dir='short',
        short_resume_dir='live-emg',
        out_tip_skip=('emergence', 'restructuring'),
        out_tip_alias={'reorganization': 'emergence'},
        plural='reorganizations',
        verb='reorganize',
        pred='emergence',
        pred_plural='emergences',
        code='rvc',
        code_upper='Rvc',
        pred_code='evc',
        pred_code_upper='Evc',
        verdict_1='reorganized_ok',
        verdict_2='charter_ok',
        adj_1='reorganized',
        adj_2='chartered',
        adj_1_negated='unemerged',
        counterpart='requirement',
        pred_done='emerged',
        pred_verdict_1='confirmed',
        pred_verdict_2='evc_ok',
        post_key='post_reorganization',
        min_name='REORGANIZATIONS',
        collect_push=('emergence', 'risk', 'capital', 'funding', 'collateral', 'margin', 'custody', 'delivery'),
        abbr='reorg',
        chain_tag='risk',
        out_extra_flags=('resolution',),
        confirm_source='preds_or_body',
        confirm_accessor_plural='emergences',
        confirm_drops='self_loaded',
        refusal_confirm_missing='charter_missing',
        refusal_pred_tampered='margin_tampered',
        refusal_pred_partial='margin_partial',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='capital_unemerged',
        refusal_pred_unmet='capital_uncapacitated',
        refusal_code_failed='evc_failed',
        summary='Post-emergence reorganization-versus-charter for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='delivery',
        chain_layout='delivery',
        book_sig=(("observation_signature",), False, False, "observation_signatures", False, "net_count"),
        plural='deliveries',
        verb='deliver',
        pred='clearing',
        pred_plural='clearings',
        code='dvp',
        code_upper='Dvp',
        pred_code='net',
        pred_code_upper='Net',
        verdict_1='deliver_ok',
        verdict_2='pay_ok',
        adj_1='delivered',
        adj_2='paid',
        adj_1_negated=None,
        counterpart=None,
        pred_done='cleared',
        pred_verdict_1='discharged',
        pred_verdict_2='net_ok',
        post_key='post_clearing',
        min_name='CLEARINGS',
        collect_push=('clearing',),
        abbr='dlv',
        confirm_source='list:settlements',
        confirm_kwargs=('settlements', 'actuation'),
        confirm_drops='none',
        pred_block=('total_spine_clearing', 'total_spine_cleared', 'total_spine_discharged'),
        ctx={'outer': 'clearing', 'inner': [('ok', 'true'), ('cleared', 'true'), ('cleared_ok', 'true'), ('clearing_root_valid', 'true'), ('clearing_count', 'count:clearing'), ('tip_clearing_root', 'tip')], 'outer_extra': [('clearing_count', 'count:clearing'), ('tip_clearing_root', 'tip'), ('state_root', 'state')]},
        book_fn_prefix='pair',
        refusal_pred_tampered='clearing_tampered',
        refusal_pred_short='clearings_short',
        refusal_pred_not_done='clearing_uncleared',
        refusal_pred_unmet='clearing_undischarged',
        refusal_code_failed='dvp_failed',
        summary='Post-clearing delivery-versus-payment for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='custody',
        chain_layout='custody',
        book_sig=(("book_signature", "pairs_digest"), True, False, "delivery_signatures", True, "delivery_count"),
        plural='custodies',
        verb='custody',
        pred='delivery',
        pred_plural='deliveries',
        code='cvt',
        code_upper='Cvt',
        pred_code='dvp',
        pred_code_upper='Dvp',
        verdict_1='custody_ok',
        verdict_2='title_ok',
        adj_1='custodied',
        adj_2='titled',
        adj_1_negated=None,
        counterpart='title',
        pred_done='delivered',
        pred_verdict_1='paid',
        pred_verdict_2='dvp_ok',
        post_key='post_delivery',
        min_name='DELIVERIES',
        collect_push=('delivery',),
        abbr='cst',
        confirm_source='list:clearings',
        confirm_kwargs=('clearings', 'settlements', 'actuation'),
        confirm_drops='none',
        pred_block=('total_spine_delivery', 'total_spine_delivered', 'total_spine_dvp_ok'),
        ctx={'outer': 'delivery', 'inner': [('ok', 'true'), ('delivered', 'true'), ('delivered_ok', 'true'), ('delivery_root_valid', 'true'), ('dvp_ok', 'true'), ('delivery_count', 'count:delivery'), ('tip_delivery_root', 'tip')], 'outer_extra': [('delivery_count', 'count:delivery'), ('tip_delivery_root', 'tip'), ('state_root', 'state')]},
        refusal_pred_partial='delivery_partial',
        refusal_pred_tampered='delivery_tampered',
        refusal_pred_short='deliveries_short',
        refusal_pred_not_done='delivery_undelivered',
        refusal_pred_unmet='delivery_unpaid',
        refusal_code_failed='cvt_failed',
        summary='Post-delivery custody-versus-title for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='margin',
        book_sig=(("book_signature", "pairs_digest"), True, True, "custody_signatures", True, "custody_count"),
        plural='margins',
        verb='margin',
        pred='custody',
        pred_plural='custodies',
        code='mve',
        code_upper='Mve',
        pred_code='cvt',
        pred_code_upper='Cvt',
        verdict_1='margin_ok',
        verdict_2='exposure_ok',
        adj_1='margined',
        adj_2='exposed',
        adj_1_negated=None,
        counterpart='exposure',
        pred_done='custodied',
        pred_verdict_1='titled',
        pred_verdict_2='cvt_ok',
        post_key='post_custody',
        min_name='CUSTODIES',
        collect_push=('custody', 'delivery'),
        abbr='mgn',
        confirm_source='list:deliveries',
        confirm_kwargs=('deliveries', 'clearings', 'settlements', 'actuation'),
        confirm_drops='none',
        pred_block=('total_spine_custody', 'total_spine_custodied', 'total_spine_cvt_ok'),
        ctx={'outer': 'custody', 'inner': [('ok', 'true'), ('custodied', 'true'), ('custodied_ok', 'true'), ('custody_root_valid', 'true'), ('cvt_ok', 'true'), ('custody_count', 'count:custody'), ('tip_custody_root', 'tip')], 'outer_extra': [('custody_count', 'count:custody'), ('tip_custody_root', 'tip'), ('state_root', 'state')]},
        refusal_pred_partial='custody_partial',
        refusal_pred_tampered='custody_tampered',
        refusal_pred_short='custodies_short',
        refusal_pred_not_done='custody_uncustodied',
        refusal_pred_unmet='custody_untitled',
        refusal_code_failed='mve_failed',
        summary='Post-custody margin-versus-exposure for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='collateral',
        book_sig=(("book_signature", "pairs_digest"), True, True, "margin_signatures", True, "margin_count"),
        plural='collaterals',
        verb='collateral',
        pred='margin',
        pred_plural='margins',
        code='cvo',
        code_upper='Cvo',
        pred_code='mve',
        pred_code_upper='Mve',
        verdict_1='collateral_ok',
        verdict_2='obligation_ok',
        adj_1='collateralized',
        adj_2='obligated',
        adj_1_negated=None,
        counterpart='obligation',
        pred_done='margined',
        pred_verdict_1='exposed',
        pred_verdict_2='mve_ok',
        post_key='post_margin',
        min_name='COLLATERALS',
        collect_push=('margin', 'custody', 'delivery'),
        abbr='col',
        confirm_source='bundle',
        confirm_kwargs=('custodies', 'clearings', 'settlements', 'actuation'),
        confirm_drops='none',
        pred_block=('total_spine_margin', 'total_spine_margined', 'total_spine_mve_ok'),
        ctx={'outer': 'margin', 'inner': [('ok', 'true'), ('margined', 'true'), ('margined_ok', 'true'), ('margin_root_valid', 'true'), ('mve_ok', 'true'), ('margin_count', 'count:margin'), ('tip_margin_root', 'tip')], 'outer_extra': [('margin_count', 'count:margin'), ('tip_margin_root', 'tip'), ('state_root', 'state')]},
        refusal_pred_partial='margin_partial',
        refusal_pred_tampered='margin_tampered',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='margin_unmargined',
        refusal_pred_unmet='margin_unexposed',
        refusal_code_failed='cvo_failed',
        summary='Post-margin collateral-versus-obligation for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='liquidity',
        book_sig=(("book_signature", "pairs_digest"), True, True, "margin_signatures", True, "collateral_count"),
        plural='liquidities',
        verb='liquidity',
        pred='collateral',
        pred_plural='collaterals',
        code='lvc',
        code_upper='Lvc',
        pred_code='cvo',
        pred_code_upper='Cvo',
        verdict_1='liquidity_ok',
        verdict_2='coverage_ok',
        adj_1='funded',
        adj_2='covered',
        adj_1_negated='unfunded',
        counterpart='coverage',
        pred_done='collateralized',
        pred_verdict_1='obligated',
        pred_verdict_2='cvo_ok',
        post_key='post_collateral',
        min_name='LIQUIDITIES',
        collect_push=('collateral', 'margin', 'custody', 'delivery'),
        abbr='liq',
        confirm_source='bundle',
        confirm_kwargs=('margins', 'clearings', 'settlements', 'actuation'),
        confirm_drops='none',
        pred_block=('total_spine_collateral', 'total_spine_collateralized', 'total_spine_cvo_ok'),
        ctx={'outer': 'margin', 'inner': [('ok', 'true'), ('collateralized', 'true'), ('collateralized_ok', 'true'), ('margin_root_valid', 'true'), ('cvo_ok', 'true'), ('collateral_count', 'count:collateral'), ('tip_collateral_root', 'tip')], 'outer_extra': [('collateral_count', 'count:collateral'), ('tip_collateral_root', 'tip'), ('state_root', 'state')]},
        refusal_pred_partial='margin_partial',
        refusal_pred_tampered='margin_tampered',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='margin_uncollateralized',
        refusal_pred_unmet='margin_unobligated',
        refusal_code_failed='lvc_failed',
        summary='Post-collateral liquidity-versus-coverage for the absolute total spine.',
    )
)


_register(
    PairEffectSpec(
        effect='funding',
        book_sig=(("book_signature", "pairs_digest"), True, True, "margin_signatures", True, "liquidity_count"),
        plural='fundings',
        verb='funding',
        pred='liquidity',
        pred_plural='liquidities',
        code='fvr',
        code_upper='Fvr',
        pred_code='lvc',
        pred_code_upper='Lvc',
        verdict_1='facility_ok',
        verdict_2='requirement_ok',
        adj_1='facilitated',
        adj_2='required',
        adj_1_negated='unfacilitated',
        counterpart='requirement',
        pred_done='funded',
        pred_verdict_1='covered',
        pred_verdict_2='lvc_ok',
        post_key='post_liquidity',
        min_name='FUNDINGS',
        collect_push=('liquidity', 'collateral', 'margin', 'custody', 'delivery'),
        abbr='fnd',
        confirm_source='bundle',
        confirm_kwargs=('collaterals', 'margins', 'clearings', 'settlements', 'actuation'),
        confirm_drops='none',
        pred_block=('total_spine_liquidity', 'total_spine_funded', 'total_spine_lvc_ok'),
        ctx={'outer': 'liquidity', 'inner': [('ok', 'true'), ('funded', 'true'), ('funded_ok', 'true'), ('liquidity_root_valid', 'true'), ('lvc_ok', 'true'), ('liquidity_count', 'count:liquidity'), ('tip_liquidity_root', 'tip')], 'outer_extra': [('liquidity_count', 'count:liquidity'), ('tip_liquidity_root', 'tip'), ('state_root', 'state')]},
        refusal_pred_partial='margin_partial',
        refusal_pred_tampered='margin_tampered',
        refusal_pred_short='margins_short',
        refusal_pred_not_done='margin_unfunded',
        refusal_pred_unmet='margin_uncovered',
        refusal_code_failed='fvr_failed',
        summary='Post-collateral funding-versus-requirement for the absolute total spine.',
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
    (
        sig_sources,
        with_clearing,
        with_delivery,
        signatures_key,
        with_pair_count,
        count_key,
    ) = spec.book_sig or (
        ("book_signature", "pairs_digest"),
        True,
        True,
        "margin_signatures",
        True,
        "liquidity_count",
    )
    sigs: list[str] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            sig = ""
            for source_key in sig_sources:
                sig = str(row.get(source_key) or "")
                if sig:
                    break
            if sig:
                sigs.append(sig)
    body: dict[str, Any] = {
        "bound_state_root": str(margin.get("bound_state_root") or ""),
        "bound_action_root": str(margin.get("bound_action_root") or ""),
        "actuation_digest": str(margin.get("actuation_digest") or ""),
        "bound_settlement_root": str(
            margin.get("bound_settlement_root") or ""
        ),
    }
    if with_clearing:
        body["bound_clearing_root"] = str(
            margin.get("bound_clearing_root") or ""
        )
    if with_delivery:
        body["bound_delivery_root"] = str(
            margin.get("bound_delivery_root")
            or margin.get("tip_delivery_root")
            or ""
        )
    body[signatures_key] = sigs
    body["residual"] = int(margin.get("residual") or 0)
    if with_pair_count:
        body["pair_count"] = int(margin.get("pair_count") or 0)
    body[count_key] = int(margin.get(f"{count_key}") or 0)
    return _sha256_json(body)


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



def _material_slots(spec: PairEffectSpec) -> dict[str, bool]:
    """Certificate-material slot inclusion, derived from chain position."""

    idx = TOTAL_SPINE_CHAIN.index(spec.effect)
    return {
        "delivery_root": idx >= TOTAL_SPINE_CHAIN.index("custody"),
        "custody_root": idx >= TOTAL_SPINE_CHAIN.index("margin"),
        "delivery_digest": idx >= TOTAL_SPINE_CHAIN.index("custody"),
        "pred_plural_ok": idx <= TOTAL_SPINE_CHAIN.index("liquidity"),
        "row_delivery_root": spec.effect != "delivery",
        # leg root key noun: own effect for delivery..collateral, predecessor above
        "leg_root_noun": spec.effect if idx <= TOTAL_SPINE_CHAIN.index("collateral") else spec.pred,
        # annotate main-section key inclusion
        "adj_2_key": idx >= TOTAL_SPINE_CHAIN.index("custody"),
        "effect_ok_key": idx >= TOTAL_SPINE_CHAIN.index("funding"),
        # digest-pre noun: own effect through liquidity, predecessor above
        "pre_noun": spec.effect if idx <= TOTAL_SPINE_CHAIN.index("liquidity") else spec.pred,
    }


def _certificate_material(spec: PairEffectSpec, body: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical material for total-spine effect certificate digests."""

    slots = _material_slots(spec)
    legs = body.get(spec.plural) or body.get("legs") or []
    rows: list[dict[str, Any]] = []
    if isinstance(legs, list):
        for row in legs:
            if not isinstance(row, Mapping):
                continue
            pred_row: dict[str, Any] = {
                f"{spec.pred}_index": int(row.get(f"{spec.pred}_index") or 0),
                f"{spec.pred}_height": int(row.get(f"{spec.pred}_height") or 0),
                f"{spec.pred}_digest": str(row.get(f"{spec.pred}_digest") or ""),
                f"bound_{spec.pred}_root": str(
                    row.get(f"bound_{spec.pred}_root") or ""
                ),
            }
            if slots["row_delivery_root"] and spec.pred != "delivery":
                pred_row["bound_delivery_root"] = str(
                    row.get("bound_delivery_root") or ""
                )
            if spec.pred != "clearing":
                pred_row["bound_clearing_root"] = str(
                    row.get("bound_clearing_root") or ""
                )
            rows.append(
                {
                    **pred_row,
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
                    f"{slots['leg_root_noun']}_root": str(row.get(f"{slots['leg_root_noun']}_root") or ""),
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
        **({"bound_custody_root": str(body.get("bound_custody_root") or "")} if slots["custody_root"] else {}),
        **({"bound_delivery_root": str(body.get("bound_delivery_root") or "")} if slots["delivery_root"] else {}),
        f"{spec.pred}_digest": str(body.get(f"{spec.pred}_digest") or ""),
        **({"delivery_digest": str(body.get("delivery_digest") or "")} if slots["delivery_digest"] else {}),
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
        **({f"{spec.pred_plural}_ok": bool(body.get(f"{spec.pred_plural}_ok", True))} if slots["pred_plural_ok"] else {f"{spec.plural}_ok": bool(body.get(f"{spec.plural}_ok", True))}),
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
    slots = _material_slots(spec)
    tip = str(last.get(f"{slots['leg_root_noun']}_root") or "").strip()
    if tip:
        return tip
    parent = ""
    for idx, row in enumerate(preds):
        slots = _material_slots(spec)
        body = {
            f"{spec.pred}_index": int(row.get(f"{spec.pred}_index") or idx),
            f"{spec.pred}_height": int(row.get(f"{spec.pred}_height") or (idx + 1)),
            f"{spec.pred}_digest": str(row.get(f"{spec.pred}_digest") or ""),
            f"bound_{spec.pred}_root": str(row.get(f"bound_{spec.pred}_root") or ""),
            **({"bound_delivery_root": str(row.get("bound_delivery_root") or "")} if slots["row_delivery_root"] and spec.pred != "delivery" else {}),
            **({"bound_clearing_root": str(row.get("bound_clearing_root") or "")} if spec.pred != "clearing" else {}),
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
        if spec.refusal_pred_partial and raw.get("atomic_ok") is False:
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
        slots = _material_slots(spec)
        material = {
            f"{spec.pred}_index": idx,
            f"{spec.pred}_height": height,
            f"{spec.pred}_digest": _pred_digest_of(spec, margin),
            f"bound_{spec.pred}_root": str(
                margin.get(f"tip_{spec.pred}_root") or ""
            ),
            **({"bound_delivery_root": str(
                margin.get("bound_delivery_root")
                or margin.get("tip_delivery_root")
                or ""
            )} if slots["row_delivery_root"] and spec.pred != "delivery" else {}),
            **({"bound_clearing_root": clearing or book_clearing} if spec.pred != "clearing" else {}),
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
        row[f"{slots['leg_root_noun']}_root"] = pred_root
        row["pairs"] = pairs
        row["schema_version"] = SCHEMA_VERSION
        legs.append(row)
        parent = pred_root
    return legs


def _seal_pair_certificate(
    spec: PairEffectSpec, body: Mapping[str, Any]
) -> dict[str, Any]:
    """Shape-private pair seal; public seal is :func:`seal_spine_family`."""

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


def seal_certificate(spec: PairEffectSpec, body: Mapping[str, Any]) -> dict[str, Any]:
    """Historical name: seal through the shared family engine."""

    from blackhole_agent.upstream_spine_family import seal_spine_family

    return seal_spine_family(spec.effect, body)


def certificate_path(spec: PairEffectSpec, root: Path) -> Path:
    """Resolve the effect certificate under its out root."""

    return resolve_certificate_path(
        Path(root),
        filename=spec.filename,
        subdir=spec.effect,
        kind=spec.kind,
        parent_sibling=True,
    )


def write_certificate(
    spec: PairEffectSpec,
    out_root: Path,
    body: Mapping[str, Any],
    *,
    allow_idempotent: bool = True,
) -> dict[str, Any]:
    """Seal and atomically write an effect receipt under ``out_root``."""

    return write_irreversible_certificate(
        out_root,
        body,
        family=spec.effect,
        digest_key=f"{spec.effect}_digest",
        seal=lambda payload: seal_certificate(spec, payload),
        resolve=lambda item: certificate_path(spec, item),
        load=lambda item: load_certificate(spec, item),
        allow_idempotent=allow_idempotent,
        refused=StageRefused,
        label=spec.pred,
        path_key=f"{spec.effect}_path",
        idempotent_key=f"{spec.kind}_idempotent",
    )


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
        slots = _material_slots(spec)
        material_row = {
            f"{spec.pred}_index": int(row.get(f"{spec.pred}_index") or idx),
            f"{spec.pred}_height": int(row.get(f"{spec.pred}_height") or (idx + 1)),
            f"{spec.pred}_digest": str(row.get(f"{spec.pred}_digest") or ""),
            f"bound_{spec.pred}_root": str(row.get(f"bound_{spec.pred}_root") or ""),
            **({"bound_delivery_root": str(row.get("bound_delivery_root") or "")} if slots["row_delivery_root"] and spec.pred != "delivery" else {}),
            **({"bound_clearing_root": str(row.get("bound_clearing_root") or "")} if spec.pred != "clearing" else {}),
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
        if str(row.get(f"{slots['leg_root_noun']}_root") or "") != expected_root:
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

    return load_irreversible_certificate(
        path,
        family=spec.effect,
        label=f"{spec.pred} certificate",
        path_key=f"{spec.effect}_path",
        verify_key=f"{spec.effect}_verify",
        resolve=lambda item: certificate_path(spec, item),
        verify=lambda payload: verify_certificate(spec, payload),
        refused=StageRefused,
        accept=lambda payload: str(payload.get("kind") or "") == spec.kind
        or bool(payload.get(spec.kind)),
        loaded_key=f"{spec.kind}_loaded",
    )


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
    if spec.chain_layout == "delivery":
        slots = [st, ar, ad, sr, clr, cd, mr, md, tip]
    elif spec.chain_layout == "custody":
        slots = [st, ar, ad, sr, clr, cr, dvd, mr, md, tip]
    else:
        slots = [st, ar, ad, sr, clr, dlr, cr, dvd, cd, mr, md, tip]
    material = (
        f"{spec.chain_tag or spec.effect}|{int(bool(short_circuit))}|{int(effect_height)}|"
        + "|".join(slots)
    ).encode("utf-8")
    digest = _sha256_bytes(material)
    return {
        "short_circuit": bool(short_circuit),
        f"{spec.effect}_height": int(effect_height),
        f"tip_{spec.effect}_root": mr,
        f"bound_{spec.pred}_root": cr,
        **({"bound_delivery_root": dlr} if spec.chain_layout != "delivery" else {}),
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
    body[f"total_spine_digest_pre_{_material_slots(spec)['pre_noun']}"] = prior_tip
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
    slots = _material_slots(spec)
    body[spec.adj_1] = bool(certificate.get(spec.adj_1, True))
    body[f"{spec.adj_1}_ok"] = bool(certificate.get(spec.adj_1, True))
    if slots["effect_ok_key"]:
        body[f"{spec.effect}_ok"] = bool(certificate.get(spec.adj_1, True))
    body[f"{spec.code}_ok"] = bool(certificate.get(f"{spec.code}_ok", True))
    if slots["adj_2_key"]:
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
        triplet = spec.pred_block or (
            f"total_spine_{spec.pred}",
            f"total_spine_{spec.pred_done}",
            f"total_spine_{spec.pred_code}_ok",
        )
        body[f"total_spine_tip_{spec.pred}_root"] = bound_pred_root
        body[f"{spec.pred}_root"] = bound_pred_root
        body[f"tip_{spec.pred}_root"] = bound_pred_root
        for key in triplet:
            body.setdefault(key, True)
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


def _restructurings_from(item: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if not isinstance(item, Mapping):
        return found
    nested = item.get("total_spine_restructuring_certificate")
    if isinstance(nested, Mapping) and (
        nested.get("tip_restructuring_root") or nested.get("restructurings")
    ):
        found.append(dict(nested))
    kind = str(item.get("kind") or "")
    if (
        kind == "total_spine_restructuring"
        or item.get("total_spine_restructuring_loaded")
        or item.get("total_spine_restructuring")
    ) and item.get("tip_restructuring_root"):
        found.append(dict(item))
    extra = item.get("restructurings")
    if isinstance(extra, list):
        for row in extra:
            if isinstance(row, Mapping) and (
                row.get("tip_restructuring_root") or row.get("restructuring_digest")
            ):
                found.append(dict(row))
    if item.get("tip_restructuring_root") and item.get("restructurings"):
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


# Accessor dispatch for the pair chain below the effect itself.
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


_CHAIN_ACCESSORS = {
    "margins": _margins_from,
    "custodies": _custodies_from,
    "deliveries": _deliveries_from,
    "clearings": _clearings_from,
    "settlements": _settlements_from,
    "collaterals": _collaterals_from,
    "liquidities": _liquidities_from,
    "fundings": _fundings_from,
    "capitals": _capitals_from,
    "restructurings": _restructurings_from,
    "emergences": _emergences_from,
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
    """Independently re-run the predecessor on the same book as confirmation.

    The historical modules' confirm steps diverge per effect; the plan is
    spec data: ``confirm_source`` picks the source expression, and
    ``confirm_kwargs`` the extra kwarg roles forwarded to the predecessor
    runner (in historical order).
    """

    from blackhole_agent import upstream_control_engine as _engine

    pred_runner = getattr(_engine, f"{_CHAIN_VERBS[spec.pred]}_total_spine")

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
    if spec.confirm_drops != "none":
        drops = [
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
        ]
        if spec.confirm_drops == "self_loaded":
            drops.insert(5, f"{spec.kind}_loaded")
        for drop in drops:
            kind = str(confirm_body.get("kind") or "")
            if kind in {spec.pred_kind, spec.kind}:
                confirm_body.pop("kind", None)
            confirm_body.pop(drop, None)
    accessor_plural = spec.confirm_accessor_plural or _pred_pred_plural(spec)
    pred_preds: list[dict[str, Any]] = []
    seen: set[str] = set()
    accessor = _CHAIN_ACCESSORS.get(accessor_plural)
    if accessor is not None:
        noun = accessor_plural[: -1] if accessor_plural.endswith("s") else accessor_plural
        # singular digest/tip keys use the chain noun (solvency, not solvencie)
        noun = {
            "custodies": "custody", "deliveries": "delivery", "clearings": "clearing",
            "settlements": "settlement", "collaterals": "collateral", "margins": "margin",
            "liquidities": "liquidity", "fundings": "funding", "capitals": "capital",
            "solvencies": "solvency", "risks": "risk", "stresses": "stress",
            "recoveries": "recovery", "resolutions": "resolution",
            "restructurings": "restructuring", "emergences": "emergence",
        }[accessor_plural]
        for item in (primary, body, confirm_body):
            for row in accessor(item):
                key = str(
                    row.get(f"{noun}_digest")
                    or row.get("certificate_hash")
                    or row.get(f"tip_{noun}_root")
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
            f"{spec.kind}_{spec.refusal_confirm_missing}",
            f"single {spec.pred} requires {accessor_plural}, collaterals, margins, "
            "custodies, deliveries, clearings, settlements, or actuation "
            f"to confirm-{spec.effect}",
        )
    if spec.confirm_source == "bundle":
        source: Any = bundle
    elif spec.confirm_source == "preds_or_body":
        source = pred_preds if pred_preds else (confirm_body or body or primary)
    elif spec.confirm_source.startswith("list:"):
        role = spec.confirm_source[5:]
        pool = {
            "settlements": settlements,
            "clearings": clearings,
            "deliveries": deliveries,
        }[role]
        source = list(pool) if pool else None
    else:  # first_or_bundle
        source = pred_preds[0] if len(pred_preds) == 1 else (pred_preds or bundle)
    roles = {
        "preds": pred_preds or None,
        "margins": margins or None,
        "clearings": clearings or None,
        "settlements": settlements or None,
        "custodies": custodies or None,
        "deliveries": deliveries or None,
        "collaterals": collaterals or None,
        "actuation": actuation,
        "body": confirm_body or None,
    }
    if spec.confirm_kwargs is not None:
        kwarg_names = list(spec.confirm_kwargs)
    else:
        kwarg_names = ["preds", "margins", "clearings", "settlements", "actuation", "body"]
    call_kwargs: dict[str, Any] = {}
    for role in kwarg_names:
        key = _pred_pred_plural(spec) if role == "preds" else role
        call_kwargs[key] = roles[role]
    confirmed = pred_runner(
        source,
        **call_kwargs,
        out_root=confirm_out,
        prior_tip=prior_tip,
        **{
            f"parent_{spec.pred}_root": tip_pred,
            f"{spec.pred}_height": pred_height + 1 if pred_height else None,
        },
        repo_path=repo_path or REPO_ROOT,
        confirm=True,
    )
    cert = confirmed.get(f"{spec.pred_kind}_certificate")
    if not isinstance(cert, Mapping):
        raise StageRefused(
            f"{spec.kind}_{spec.refusal_confirm_missing}",
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


def _apply_pair_effect_core(
    spec: PairEffectSpec,
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Shape-private pair apply; public apply is :func:`apply_spine_family`."""

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
        if spec.ctx is not None:
            def _ctx_value(role: str) -> Any:
                if role == "true":
                    return True
                if role == "tip":
                    return pred_root
                if role == "state":
                    return state_root
                if role.startswith("count:"):
                    return int(first.get(f"{role[6:]}_count") or 0)
                raise KeyError(role)

            ctx = {
                spec.ctx["outer"]: {
                    key: _ctx_value(role) for key, role in spec.ctx["inner"]
                },
            }
            for key, role in spec.ctx["outer_extra"]:
                ctx[key] = _ctx_value(role)
        else:
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


def run_pair_effect(
    spec: PairEffectSpec,
    source: Path | str | Mapping[str, Any] | Sequence[Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Historical name: apply through the shared family engine."""

    from blackhole_agent.upstream_spine_family import apply_spine_family

    return apply_spine_family(spec.effect, source, **kwargs)


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


def _pair_effect_proof_core(spec: PairEffectSpec) -> dict[str, Any]:
    """Shape-private pair proof; public proof is :func:`prove_spine_family`."""

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
                "goal": spec.proof_goal or f"{spec.effect} proof origin",
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
                    f"{name}_height": int(
                        first.get(
                            f"total_spine_{(spec.second_height_miskey or {}).get(name, name)}_height"
                        )
                        or 0
                    )
                    + 1,
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
            out_root=scratch / (spec.live_dir or f"live-{spec.abbr}"),
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
            out_root=scratch / (spec.short_dir or f"short-{spec.abbr}"),
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
            resume_dir=live_cert_path or (scratch / (spec.short_resume_dir or f"live-{spec.abbr}")),
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
            getattr(ce, impl_name, None) is True
            and callable(getattr(ce, runner_name, None))
            and getattr(ce, runner_name, None) is getattr(synth, runner_name)
            and callable(getattr(ce, proof_name, None))
            and getattr(ce, proof_name, None) is getattr(synth, proof_name)
            and (
                f"{spec.effect}=True" in engine_text
                or f"{spec.effect}: bool = False" in engine_text
            )
        )

        engine_mod_path = Path(__file__).resolve()
        engine_mod_text = engine_mod_path.read_text(encoding="utf-8")
        spec_pattern = (
            f'effect="{spec.effect}"'
            if f'effect="{spec.effect}"' in engine_mod_text
            else f"effect='{spec.effect}'"
        )
        mod_source_ok = (
            spec.effect in PAIR_EFFECT_SPECS
            and spec_pattern in engine_mod_text
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
            if name in spec.out_tip_skip:
                continue
            source_name = (spec.out_tip_alias or {}).get(name, name)
            result[f"tip_{name}_root"] = tip_roots.get(source_name, "")
        self_alias = (spec.out_tip_alias or {}).get(spec.effect)
        if self_alias is not None:
            # Historical duplicate-key overwrite: the self root prints the alias target's tip.
            result[f"tip_{spec.effect}_root"] = tip_roots.get(self_alias, "")
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
        mid_flags = {}
        for name in TOTAL_SPINE_CHAIN[1:eff_idx + 1]:
            if name in ("clearing", "delivery", "custody", "margin", "collateral", "liquidity"):
                mid_flags[f"total_spine_{name}"] = True
        # settlement is always printed (chain base).
        mid_flags["total_spine_settlement"] = True
        result.update(
            {
                **mid_flags,
                "total_spine_actuation": True,
                "total_spine_execution": True,
                "total_spine_quorum": True,
                "done_when_met": ok,
            }
        )
        return result
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _builtin_pair_effect_proof(spec: PairEffectSpec) -> dict[str, Any]:
    """Historical name: prove through the shared family engine."""

    from blackhole_agent.upstream_spine_family import prove_spine_family

    return prove_spine_family(spec.effect)


# ---------------------------------------------------------------------------
# Synthesis: per-effect modules with exact historical names and signatures.
# ---------------------------------------------------------------------------

_EFFECT_MODULE_PREFIX = "blackhole_agent.upstream_total_spine_"


def _forward(spec: PairEffectSpec, public_name: str, ns: dict[str, Any]) -> Any:
    """Dispatch one synthesized public call to the generic implementation."""

    if public_name == f"{spec.verb}_total_spine":
        from blackhole_agent.upstream_spine_family import apply_spine_family

        source = ns.pop("source", None)
        return apply_spine_family(spec.effect, source, **ns)
    if public_name == f"{spec.book_fn_prefix}_total_spine_{spec.pred_plural}":
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
        from blackhole_agent.upstream_spine_family import seal_spine_family

        return seal_spine_family(spec.effect, ns["body"])
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
        from blackhole_agent.upstream_spine_family import prove_spine_family

        return prove_spine_family(spec.effect)
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
        from blackhole_agent.upstream_spine_family import prove_spine_family

        result = prove_spine_family(spec.effect)
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


def _synthesize_effect_module(spec: PairEffectSpec) -> Any:
    """Historical name: populate through the shared family engine."""

    from blackhole_agent.upstream_spine_family import synthesize_family

    return synthesize_family("pair_effect", spec.effect)


def _effect_main_from_module(effect: str, module_globals: dict[str, Any]) -> None:
    """Historical ``python -m`` entry: delegate to the family engine."""

    from blackhole_agent.upstream_spine_family import run_family_main

    run_family_main("pair_effect", effect, module_globals)


def install_pair_effect_finder() -> None:
    """Historical name: install the shared module-synthesis finder."""

    from blackhole_agent.upstream_module_synthesis import (
        install_module_synthesis_finder,
    )

    install_module_synthesis_finder()


def builtin_spine_signature_catalog_proof() -> dict[str, Any]:
    """Hermetic proof: leftover pair-effect signatures are one catalog."""

    import inspect
    import importlib

    checks: dict[str, bool] = {}
    checks["impl"] = SPINE_SIGNATURE_CATALOG_IMPL is True
    checks["spec_count"] = len(PAIR_EFFECT_SPECS) == 15
    mismatches: list[str] = []
    for name, spec in PAIR_EFFECT_SPECS.items():
        derived = derive_pair_effect_signatures(spec)
        hist = spec.signatures or {}
        if derived != hist:
            mismatches.append(name)
        if set(derived) != set(pair_effect_public_names(spec)):
            mismatches.append(f"{name}:names")
    checks["derived_matches_live"] = mismatches == []
    checks["twelve_names"] = all(
        len(spec.signatures or {}) == 12 for spec in PAIR_EFFECT_SPECS.values()
    )

    probe = PairEffectSpec(
        effect="ratification",
        plural="ratifications",
        verb="ratify",
        pred="reorganization",
        pred_plural="reorganizations",
        code="rtr",
        code_upper="Rtr",
        pred_code="rvc",
        pred_code_upper="Rvc",
        verdict_1="ratified_ok",
        verdict_2="treaty_ok",
        adj_1="ratified",
        adj_2="treatied",
        adj_1_negated="unratified",
        counterpart="treaty",
        pred_done="reorganized",
        pred_verdict_1="chartered",
        pred_verdict_2="rvc_ok",
        post_key="post_reorganization",
        min_name="RATIFICATIONS",
        collect_push=("reorganization",),
        abbr="rat",
        refusal_pred_tampered="margin_tampered",
        refusal_pred_short="margins_short",
        refusal_pred_not_done="capital_unreorganized",
        refusal_pred_unmet="capital_unrequired",
        refusal_code_failed="rvc_failed",
        summary="probe signature catalog family",
    )
    probe_sigs = derive_pair_effect_signatures(probe)
    checks["probe_twelve"] = len(probe_sigs) == 12
    checks["probe_annotate"] = "annotate_total_spine_ratification" in probe_sigs
    checks["probe_runner"] = "ratify_total_spine" in probe_sigs
    checks["probe_not_live"] = "ratification" not in PAIR_EFFECT_SPECS

    effects_src = Path(__file__).read_text(encoding="utf-8")
    checks["no_leftover_signature_blocks"] = "\n        signatures={" not in effects_src
    checks["derive_present"] = "def derive_pair_effect_signatures" in effects_src
    checks["register_fills"] = "derive_pair_effect_signatures(spec)" in effects_src
    checks["public_names_present"] = "def pair_effect_public_names" in effects_src

    engine_src = (
        REPO_ROOT / "src" / "blackhole_agent" / "upstream_control_engine.py"
    ).read_text(encoding="utf-8")
    checks["surface_delegates"] = (
        "from blackhole_agent.upstream_total_spine_effects import pair_effect_surface_names"
        in engine_src
        and "return pair_effect_surface_names(spec)" in engine_src
    )
    checks["surface_no_name_copy"] = (
        'f"annotate_total_spine_{spec.effect}"' not in engine_src
    )

    solvency = importlib.import_module("blackhole_agent.upstream_total_spine_solvency")
    delivery = importlib.import_module("blackhole_agent.upstream_total_spine_delivery")
    recovery = importlib.import_module("blackhole_agent.upstream_total_spine_recovery")
    sol_params = list(inspect.signature(solvency.solvency_total_spine).parameters)
    checks["solvency_runner_params"] = sol_params[:3] == [
        "source",
        "capitals",
        "margins",
    ]
    book_params = list(inspect.signature(delivery.pair_total_spine_clearings).parameters)
    checks["delivery_book_arg"] = book_params[0] == "clearings"
    compute_params = list(
        inspect.signature(recovery.compute_total_spine_recovery_root).parameters
    )
    checks["recovery_compute_arg"] = compute_params == ["risks"]
    checks["solvency_annotate"] = callable(
        getattr(solvency, "annotate_total_spine_solvency", None)
    )
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    wired = {
        "derive": callable(derive_pair_effect_signatures),
        "quirks": callable(pair_effect_signature_quirks),
        "public_names": callable(pair_effect_public_names),
        "surface_names": callable(pair_effect_surface_names),
        "impl": SPINE_SIGNATURE_CATALOG_IMPL is True,
    }
    ok = all(checks.values()) and all(wired.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "action": "spine_signature_catalog_proof",
        "ok": ok,
        "checks": checks,
        "wired": wired,
        "wired_count": sum(1 for value in wired.values() if value),
        "spec_count": len(PAIR_EFFECT_SPECS),
        "mismatches": mismatches,
        "probe_family": "ratification",
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "spine_signature_catalog": True,
        "done_when_met": ok,
    }
    out = REPO_ROOT / "artifacts" / "capability-spine-signature-catalog"
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "plane-report.json", report)
    return report


def _probe_ratification_spec() -> PairEffectSpec:
    return PairEffectSpec(
        effect="ratification",
        plural="ratifications",
        verb="ratify",
        pred="reorganization",
        pred_plural="reorganizations",
        code="rtr",
        code_upper="Rtr",
        pred_code="rvc",
        pred_code_upper="Rvc",
        verdict_1="ratified_ok",
        verdict_2="treaty_ok",
        adj_1="ratified",
        adj_2="treatied",
        adj_1_negated="unratified",
        counterpart="treaty",
        pred_done="reorganized",
        pred_verdict_1="chartered",
        pred_verdict_2="rvc_ok",
        post_key="post_reorganization",
        min_name="RATIFICATIONS",
        collect_push=("reorganization",),
        abbr="rat",
        refusal_pred_tampered="margin_tampered",
        refusal_pred_short="margins_short",
        refusal_pred_not_done="capital_unreorganized",
        refusal_pred_unmet="capital_unrequired",
        refusal_code_failed="rvc_failed",
        summary="probe contract catalog family",
    )


def builtin_spine_contract_catalog_proof() -> dict[str, Any]:
    """Hermetic proof: leftover pair-effect contract materializers are one catalog."""

    import inspect

    from blackhole_agent import capability_compounder as compounder

    checks: dict[str, bool] = {}
    catalog = derive_pair_effect_contract_catalog()
    kinds = derive_pair_effect_contract_kind_sets()
    verbs, preds, abbrs = derive_spine_contract_chain_maps()
    checks["impl"] = SPINE_CONTRACT_CATALOG_IMPL is True
    checks["catalog_len"] = len(catalog) == 15
    checks["kind_len"] = len(kinds) == 15
    checks["kind_order"] = [name for name, _ in kinds] == [
        name for name in TOTAL_SPINE_CHAIN if name in PAIR_EFFECT_SPECS
    ]
    checks["chain_len"] = len(verbs) == 16 and len(preds) == 16 and len(abbrs) == 16
    checks["chain_starts_clearing"] = (
        list(verbs)[0] == "clearing" and verbs["clearing"] == "clear"
    )
    checks["chain_ends_reorganization"] = (
        list(verbs)[-1] == "reorganization" and verbs["reorganization"] == "reorganize"
    )
    checks["abbr_quirks"] = (
        abbrs["clearing"] == "clr"
        and abbrs["restructuring"] == "rst"
        and abbrs["reorganization"] == "reo"
        and abbrs["delivery"] == "dlv"
    )
    sol = catalog["solvency"]
    checks["solvency_fields"] = (
        sol["fields"]["surplus_ok"] == ["lit", True]
        and "action" in sol["fields"]
        and sol["abbr"] == "sol"
    )
    checks["delivery_no_pay"] = (
        "pay_ok" not in catalog["delivery"]["fields"]
        and "dvp_ok" in catalog["delivery"]["fields"]
    )
    checks["liquidity_liquid"] = "liquid_ok" in catalog["liquidity"]["fields"]
    kind_map = dict(kinds)
    checks["solvency_kinds"] = "svr_ok" in kind_map["solvency"] and (
        "surplus_ok" in kind_map["solvency"]
    )
    checks["delivery_kinds"] = kind_map["delivery"] == frozenset(
        {
            "delivery_ok",
            "delivered_ok",
            "min_deliveries",
            "delivery_root_valid",
            "dvp_ok",
        }
    )

    probe = _probe_ratification_spec()
    probe_cfg = derive_pair_effect_contract_config(probe)
    probe_kinds = derive_pair_effect_contract_kinds(probe)
    checks["probe_config"] = (
        probe_cfg["fields"]["ratified"] == ["lit", True]
        and "treaty_ok" in probe_cfg["fields"]
        and probe_cfg["abbr"] == "rat"
    )
    checks["probe_kinds"] = (
        "ratification_ok" in probe_kinds and "treaty_ok" in probe_kinds
    )
    checks["probe_not_live"] = "ratification" not in catalog
    probe_verbs, probe_preds, _probe_abbrs = derive_spine_contract_chain_maps(
        extra_chain=(("ratification", "reorganization", "ratify", "self"),)
    )
    checks["probe_chain"] = (
        probe_verbs.get("ratification") == "ratify"
        and probe_preds.get("ratification") == "reorganization"
        and "ratification" not in verbs
    )

    compounder_src = Path(compounder.__file__).read_text(encoding="utf-8")
    effects_src = Path(__file__).read_text(encoding="utf-8")
    checks["no_leftover_pair_config"] = "_MAT_PAIR_CONFIG:" not in compounder_src
    checks["no_leftover_chain_verbs"] = "_MAT_CHAIN_VERBS =" not in compounder_src
    checks["no_leftover_kind_unroll"] = (
        '("delivery", frozenset(' not in compounder_src
        and '("reorganization", frozenset(' not in compounder_src
    )
    checks["compounder_uses_catalog"] = (
        "derive_pair_effect_contract_config" in compounder_src
        and "derive_spine_contract_chain_maps" in compounder_src
        and "derive_pair_effect_contract_kind_sets" in compounder_src
        and "materialize_spine_family_contract_context" in compounder_src
    )
    checks["derive_present"] = "def derive_pair_effect_contract_config" in effects_src
    wrap_src = inspect.getsource(compounder.materialize_total_spine_solvency_contract_context)
    checks["solvency_wrapper_thin"] = (
        "materialize_spine_family_contract_context" in wrap_src
        and "_MAT_PAIR_CONFIG" not in wrap_src
    )
    checks["public_dispatch"] = callable(
        compounder.materialize_spine_family_contract_context
    )
    try:
        compounder.materialize_spine_family_contract_context(
            "not-a-family", REPO_ROOT, {}
        )
        checks["unknown_refused"] = False
    except KeyError:
        checks["unknown_refused"] = True
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    wired = {
        "derive_config": callable(derive_pair_effect_contract_config),
        "derive_kinds": callable(derive_pair_effect_contract_kinds),
        "derive_catalog": callable(derive_pair_effect_contract_catalog),
        "derive_kind_sets": callable(derive_pair_effect_contract_kind_sets),
        "derive_chain": callable(derive_spine_contract_chain_maps),
        "quirks": callable(pair_effect_contract_quirks),
        "dispatch": callable(compounder.materialize_spine_family_contract_context),
        "impl": SPINE_CONTRACT_CATALOG_IMPL is True,
    }
    ok = all(checks.values()) and all(wired.values())
    report = {
        "schema_version": SCHEMA_VERSION,
        "action": "spine_contract_catalog_proof",
        "ok": ok,
        "checks": checks,
        "wired": wired,
        "wired_count": sum(1 for value in wired.values() if value),
        "spec_count": len(PAIR_EFFECT_SPECS),
        "catalog_count": len(catalog),
        "kind_count": len(kinds),
        "chain_count": len(verbs),
        "probe_family": "ratification",
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "spine_contract_catalog": True,
        "done_when_met": ok,
    }
    out = REPO_ROOT / "artifacts" / "capability-spine-contract-catalog"
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "plane-report.json", report)
    return report
