"""Thin facade: multi-round loop control flow lives in the control engine.

Preserves the historical import path and CLI so ledger proofs and domain
modules keep working. Implementation is upstream_control_engine (loop mode).
No skill-route discovery.
"""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from blackhole_agent.upstream_control_engine import (  # noqa: F401
    CIVILIZATION_SPINE_DEFAULT_ROOTS,
    CIVILIZATION_SPINE_IMPL,
    CONTINUUM_SPINE_DEFAULT_ROOTS,
    CONTINUUM_SPINE_IMPL,
    GOVERNANCE_NEST_PATH,
    LOOP_DIALECTS,
    LOOP_STACK,
    OPERATIONAL_NEST,
    REPO_ROOT,
    SCHEMA_VERSION,
    STEWARDSHIP_SPINE_DEFAULT_ROOTS,
    TOTAL_SPINE_ADAPTIVE_IMPL,
    TOTAL_SPINE_COMPRESS_THRESHOLD,
    TOTAL_SPINE_CONTINUITY_FILENAME,
    TOTAL_SPINE_CONTINUITY_IMPL,
    TOTAL_SPINE_CONTINUITY_KIND,
    TOTAL_SPINE_DEFAULT_ADAPTIVE_ROUNDS,
    TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES,
    TOTAL_SPINE_DEFAULT_GOAL_MAX_STEPS,
    TOTAL_SPINE_DEFAULT_GROW_BUDGET,
    TOTAL_SPINE_DEFAULT_ROOT,
    TOTAL_SPINE_DEFAULT_ROOTS,
    TOTAL_SPINE_EFFECT_IMPL,
    TOTAL_SPINE_FEDERATION_FILENAME,
    TOTAL_SPINE_FEDERATION_IMPL,
    TOTAL_SPINE_FEDERATION_KIND,
    TOTAL_SPINE_FEDERATION_MIN_ORIGINS,
    TOTAL_SPINE_FINALITY_FILENAME,
    TOTAL_SPINE_FINALITY_IMPL,
    TOTAL_SPINE_FINALITY_KIND,
    TOTAL_SPINE_GOAL_IMPL,
    TOTAL_SPINE_IMPL,
    TOTAL_SPINE_QUORUM_IMPL,
    TOTAL_SPINE_QUORUM_MIN_ORIGINS,
    TOTAL_SPINE_ACTUATION_FILENAME,
    TOTAL_SPINE_ACTUATION_IMPL,
    TOTAL_SPINE_ACTUATION_KIND,
    TOTAL_SPINE_ACTUATION_MIN_ACTIONS,
    TOTAL_SPINE_SETTLEMENT_FILENAME,
    TOTAL_SPINE_SETTLEMENT_IMPL,
    TOTAL_SPINE_SETTLEMENT_KIND,
    TOTAL_SPINE_SETTLEMENT_MIN_OBSERVATIONS,
    TOTAL_SPINE_CLEARING_FILENAME,
    TOTAL_SPINE_CLEARING_IMPL,
    TOTAL_SPINE_CLEARING_KIND,
    TOTAL_SPINE_CLEARING_MIN_SETTLEMENTS,
    TOTAL_SPINE_DELIVERY_FILENAME,
    TOTAL_SPINE_DELIVERY_IMPL,
    TOTAL_SPINE_DELIVERY_KIND,
    TOTAL_SPINE_DELIVERY_MIN_CLEARINGS,
    TOTAL_SPINE_CUSTODY_FILENAME,
    TOTAL_SPINE_CUSTODY_IMPL,
    TOTAL_SPINE_CUSTODY_KIND,
    TOTAL_SPINE_CUSTODY_MIN_DELIVERIES,
    TOTAL_SPINE_MARGIN_FILENAME,
    TOTAL_SPINE_MARGIN_IMPL,
    TOTAL_SPINE_MARGIN_KIND,
    TOTAL_SPINE_MARGIN_MIN_CUSTODIES,
    TOTAL_SPINE_COLLATERAL_FILENAME,
    TOTAL_SPINE_COLLATERAL_IMPL,
    TOTAL_SPINE_COLLATERAL_KIND,
    TOTAL_SPINE_COLLATERAL_MIN_COLLATERALS,
    TOTAL_SPINE_LIQUIDITY_FILENAME,
    TOTAL_SPINE_LIQUIDITY_IMPL,
    TOTAL_SPINE_LIQUIDITY_KIND,
    TOTAL_SPINE_LIQUIDITY_MIN_LIQUIDITIES,
    TOTAL_SPINE_FUNDING_FILENAME,
    TOTAL_SPINE_FUNDING_IMPL,
    TOTAL_SPINE_FUNDING_KIND,
    TOTAL_SPINE_FUNDING_MIN_FUNDINGS,
    TOTAL_SPINE_CAPITAL_FILENAME,
    TOTAL_SPINE_CAPITAL_IMPL,
    TOTAL_SPINE_CAPITAL_KIND,
    TOTAL_SPINE_CAPITAL_MIN_CAPITALS,
    TOTAL_SPINE_EXECUTION_FILENAME,
    TOTAL_SPINE_EXECUTION_IMPL,
    TOTAL_SPINE_EXECUTION_KIND,
    BuildChildKwargs,
    ExtractChildDigest,
    ExtractDispatched,
    ExtractPortfolio,
    IsIdleRound,
    LoopClassifyVerdict,
    LoopDialect,
    LoopNestHooks,
    LoopRefused,
    LoopState,
    OnChildResult,
    PipelineNestHooks,
    PostRoundStop,
    PreRoundStop,
    SealLoop,
    StageRefused,
    annotate_control_nest,
    annotate_governance_spine,
    annotate_outer_governance_spine,
    annotate_stewardship_spine,
    annotate_total_spine,
    annotate_total_spine_contract,
    annotate_total_spine_effects,
    annotate_total_spine_actuation,
    annotate_total_spine_settlement,
    annotate_total_spine_clearing,
    annotate_total_spine_delivery,
    annotate_total_spine_custody,
    annotate_total_spine_margin,
    annotate_total_spine_collateral,
    annotate_total_spine_liquidity,
    annotate_total_spine_funding,
    annotate_total_spine_capital,
    annotate_total_spine_execution,
    annotate_total_spine_federation,
    annotate_total_spine_finality,
    build_live_domain_hooks,
    builtin_civilization_spine_proof,
    builtin_continuum_spine_proof,
    builtin_control_nest_proof,
    builtin_governance_spine_proof,
    builtin_loop_engine_proof,
    builtin_stewardship_spine_proof,
    builtin_total_spine_adaptive_proof,
    builtin_total_spine_continuity_proof,
    builtin_total_spine_effect_proof,
    actuate_total_spine,
    actuation_certificate_path,
    builtin_total_spine_actuation_proof,
    builtin_total_spine_settlement_proof,
    builtin_total_spine_clearing_proof,
    builtin_total_spine_delivery_proof,
    builtin_total_spine_custody_proof,
    builtin_total_spine_margin_proof,
    builtin_total_spine_collateral_proof,
    builtin_total_spine_liquidity_proof,
    builtin_total_spine_funding_proof,
    builtin_total_spine_capital_proof,
    builtin_total_spine_execution_proof,
    builtin_total_spine_federation_proof,
    builtin_total_spine_finality_proof,
    builtin_total_spine_goal_proof,
    builtin_total_spine_proof,
    builtin_total_spine_quorum_proof,
    classify_total_spine_federation_conflict,
    cluster_total_spine_finality_origins,
    default_total_spine_quorum_threshold,
    compose_loop_of_loop,
    compose_pipeline_of_pipeline,
    continuity_checkpoint_path,
    default_extract_dispatched,
    dispatch_total_spine_effects,
    evaluate_total_spine_contract,
    compute_total_spine_action_root,
    compute_total_spine_settlement_root,
    compute_total_spine_clearing_root,
    compute_total_spine_delivery_root,
    compute_total_spine_custody_root,
    compute_total_spine_margin_root,
    compute_total_spine_collateral_root,
    compute_total_spine_liquidity_root,
    compute_total_spine_funding_root,
    compute_total_spine_capital_root,
    execute_total_spine,
    execution_certificate_path,
    federate_total_spine,
    federation_certificate_path,
    finality_certificate_path,
    get_loop_dialect,
    governance_nest_depth,
    governance_nest_path,
    list_loop_dialects,
    load_total_spine_actuation_certificate,
    load_total_spine_settlement_certificate,
    load_total_spine_clearing_certificate,
    load_total_spine_delivery_certificate,
    load_total_spine_custody_certificate,
    load_total_spine_margin_certificate,
    load_total_spine_collateral_certificate,
    load_total_spine_liquidity_certificate,
    load_total_spine_funding_certificate,
    load_total_spine_capital_certificate,
    load_total_spine_continuity_checkpoint,
    load_total_spine_execution_certificate,
    load_total_spine_federation_certificate,
    load_total_spine_finality_certificate,
    make_governance_institution_child_runner,
    make_governance_league_child_runner,
    make_operational_program_child_runner,
    make_progress_loop_hooks,
    make_stewardship_child_runner,
    nest_path,
    open_loop_dir,
    operational_nest_path,
    outer_governance_nest_depth,
    outer_governance_nest_path,
    plan_total_spine_goal_effects,
    recover_governance_child_path,
    resolve_total_spine_goals,
    resolve_portfolio,
    run_control_graph,
    run_durable_loop,
    run_governance_spine,
    run_nested_control,
    run_nested_pipeline,
    run_operational_spine,
    run_outer_governance_spine,
    run_stewardship_spine,
    run_total_spine,
    settle_total_spine,
    settlement_certificate_path,
    clear_total_spine,
    clearing_certificate_path,
    deliver_total_spine,
    delivery_certificate_path,
    custody_total_spine,
    custody_certificate_path,
    margin_total_spine,
    margin_certificate_path,
    collateral_total_spine,
    collateral_certificate_path,
    liquidity_total_spine,
    liquidity_certificate_path,
    funding_total_spine,
    funding_certificate_path,
    capital_total_spine,
    capital_certificate_path,
    book_total_spine_fundings,
    book_total_spine_liquidities,
    book_total_spine_collaterals,
    book_total_spine_margins,
    book_total_spine_deliveries,
    book_total_spine_custodies,
    pair_total_spine_clearings,
    net_total_spine_settlements,
    observe_total_spine_actions,
    seal_json_receipt,
    seal_total_spine_adaptive_chain,
    seal_total_spine_continuity_chain,
    seal_total_spine_continuity_checkpoint,
    seal_total_spine_contract,
    seal_total_spine_effect_chain,
    seal_total_spine_actuation_certificate,
    seal_total_spine_actuation_chain,
    seal_total_spine_settlement_certificate,
    seal_total_spine_settlement_chain,
    seal_total_spine_clearing_certificate,
    seal_total_spine_clearing_chain,
    seal_total_spine_delivery_certificate,
    seal_total_spine_delivery_chain,
    seal_total_spine_custody_certificate,
    seal_total_spine_custody_chain,
    seal_total_spine_margin_certificate,
    seal_total_spine_margin_chain,
    seal_total_spine_collateral_certificate,
    seal_total_spine_collateral_chain,
    seal_total_spine_liquidity_certificate,
    seal_total_spine_liquidity_chain,
    seal_total_spine_funding_certificate,
    seal_total_spine_funding_chain,
    seal_total_spine_capital_certificate,
    seal_total_spine_capital_chain,
    seal_total_spine_execution_certificate,
    seal_total_spine_execution_chain,
    seal_total_spine_federation_certificate,
    seal_total_spine_federation_chain,
    seal_total_spine_finality_certificate,
    seal_total_spine_finality_chain,
    seal_total_spine_hop_chain,
    select_total_spine_quorum_cluster,
    stewardship_constitution_chain,
    stewardship_nest_depth,
    stewardship_nest_path,
    total_nest_depth,
    total_nest_path,
    verify_loop_receipt,
    verify_total_spine_actuation_certificate,
    verify_total_spine_settlement_certificate,
    verify_total_spine_clearing_certificate,
    verify_total_spine_delivery_certificate,
    verify_total_spine_custody_certificate,
    verify_total_spine_margin_certificate,
    verify_total_spine_collateral_certificate,
    verify_total_spine_liquidity_certificate,
    verify_total_spine_funding_certificate,
    verify_total_spine_capital_certificate,
    verify_total_spine_continuity_checkpoint,
    verify_total_spine_execution_certificate,
    verify_total_spine_federation_certificate,
    verify_total_spine_finality_certificate,
    write_total_spine_actuation_certificate,
    write_total_spine_settlement_certificate,
    write_total_spine_clearing_certificate,
    write_total_spine_delivery_certificate,
    write_total_spine_custody_certificate,
    write_total_spine_margin_certificate,
    write_total_spine_collateral_certificate,
    write_total_spine_liquidity_certificate,
    write_total_spine_funding_certificate,
    write_total_spine_capital_certificate,
    write_total_spine_continuity_checkpoint,
    write_total_spine_execution_certificate,
    write_total_spine_federation_certificate,
    write_total_spine_finality_certificate,
)

# Historical name before control-engine merge.
ClassifyVerdict = LoopClassifyVerdict

CONTROL_ENGINE_IMPL = True
CONTROL_ENGINE_MODE = "loop"
CONTROL_NEST_IMPL = True
CONTROL_GRAPH_IMPL = True
GOVERNANCE_SPINE_IMPL = True
STEWARDSHIP_SPINE_IMPL = True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("proof", help="Run hermetic multi-round loop-engine proof")
    sub.add_parser("list", help="List registered loop dialects")
    sub.add_parser(
        "governance-proof",
        help="Governance spine: institution + operational nest proof",
    )
    sub.add_parser(
        "stewardship-proof",
        help="Stewardship spine: confederation→…→campaign cascade proof",
    )
    sub.add_parser(
        "civilization-proof",
        help=(
            "Civilization spine: full civilization tower defaults into "
            "operational nest"
        ),
    )
    sub.add_parser(
        "continuum-proof",
        help=(
            "Continuum spine: full continuum SI tower defaults into "
            "operational nest"
        ),
    )
    sub.add_parser(
        "total-proof",
        help=(
            "Total spine: absolute quettacontinuum→…→campaign via compressed "
            "hop seals + live operational nest"
        ),
    )
    sub.add_parser(
        "effect-proof",
        help=(
            "Total spine effects: absolute tower dispatches ledger "
            "capabilities with sealed effect digests"
        ),
    )
    sub.add_parser(
        "goal-proof",
        help=(
            "Total spine goal: free-text goal plans effects and "
            "done_when contracts gate the absolute tower tip"
        ),
    )
    sub.add_parser(
        "adaptive-proof",
        help=(
            "Total spine adaptive: closed-loop recovery from failed "
            "effects with multi-round sealed digests"
        ),
    )
    sub.add_parser(
        "continuity-proof",
        help=(
            "Total spine continuity: sealed adaptive checkpoints resume "
            "mid-recovery across process boundaries"
        ),
    )
    sub.add_parser(
        "finality-proof",
        help=(
            "Total spine finality: irreversible certificates short-circuit "
            "re-dispatch on finalized absolute-tower resume"
        ),
    )
    sub.add_parser(
        "federation-proof",
        help=(
            "Total spine federation: multi-origin finality certificates "
            "federate into a dual-origin sealed absolute-tower tip"
        ),
    )
    sub.add_parser(
        "quorum-proof",
        help=(
            "Total spine quorum: N-of-M majority federation excludes "
            "Byzantine minority finality and rebinds the absolute-tower tip"
        ),
    )
    sub.add_parser(
        "execution-proof",
        help=(
            "Total spine execution: post-quorum world-state roots seal "
            "into irreversible execution certificates on the absolute tip"
        ),
    )
    sub.add_parser(
        "actuation-proof",
        help=(
            "Total spine actuation: post-execution multi-action effects seal "
            "into irreversible actuation certificates on the absolute tip"
        ),
    )
    sub.add_parser(
        "settlement-proof",
        help=(
            "Total spine settlement: post-actuation observations close "
            "done_when into irreversible settlement receipts on the tip"
        ),
    )
    sub.add_parser(
        "clearing-proof",
        help=(
            "Total spine clearing: post-settlement netting discharges "
            "matching observation books into irreversible clearing receipts"
        ),
    )
    sub.add_parser(
        "delivery-proof",
        help=(
            "Total spine delivery: post-clearing atomic DvP seals matching "
            "clearing books into irreversible delivery receipts"
        ),
    )
    sub.add_parser(
        "custody-proof",
        help=(
            "Total spine custody: post-delivery atomic CvT seals matching "
            "delivery books into irreversible custody receipts"
        ),
    )
    sub.add_parser(
        "margin-proof",
        help=(
            "Total spine margin: post-custody atomic MvE seals matching "
            "custody books into irreversible margin receipts"
        ),
    )
    sub.add_parser(
        "collateral-proof",
        help=(
            "Total spine collateral: post-margin atomic CvO seals matching "
            "margin books into irreversible collateral receipts"
        ),
    )
    sub.add_parser(
        "liquidity-proof",
        help=(
            "Total spine liquidity: post-collateral atomic LvC seals matching "
            "collateral books into irreversible liquidity receipts"
        ),
    )
    sub.add_parser(
        "funding-proof",
        help=(
            "Total spine funding: post-liquidity atomic FvR seals matching "
            "liquidity books into irreversible funding receipts"
        ),
    )
    sub.add_parser(
        "capital-proof",
        help=(
            "Total spine capital: post-funding atomic CvA seals matching "
            "funding books into irreversible capital receipts"
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "list":
        print(json.dumps({"dialects": list_loop_dialects()}, indent=2))
        return 0
    if args.cmd == "proof":
        result = builtin_loop_engine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "governance-proof":
        result = builtin_governance_spine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "stewardship-proof":
        result = builtin_stewardship_spine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "civilization-proof":
        result = builtin_civilization_spine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "continuum-proof":
        result = builtin_continuum_spine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "total-proof":
        result = builtin_total_spine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "effect-proof":
        result = builtin_total_spine_effect_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "goal-proof":
        result = builtin_total_spine_goal_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "adaptive-proof":
        result = builtin_total_spine_adaptive_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "continuity-proof":
        result = builtin_total_spine_continuity_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "finality-proof":
        result = builtin_total_spine_finality_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "federation-proof":
        result = builtin_total_spine_federation_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "quorum-proof":
        result = builtin_total_spine_quorum_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "execution-proof":
        result = builtin_total_spine_execution_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "actuation-proof":
        result = builtin_total_spine_actuation_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "settlement-proof":
        result = builtin_total_spine_settlement_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "clearing-proof":
        result = builtin_total_spine_clearing_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "delivery-proof":
        result = builtin_total_spine_delivery_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "custody-proof":
        result = builtin_total_spine_custody_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "margin-proof":
        result = builtin_total_spine_margin_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "collateral-proof":
        result = builtin_total_spine_collateral_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "liquidity-proof":
        result = builtin_total_spine_liquidity_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "funding-proof":
        result = builtin_total_spine_funding_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    if args.cmd == "capital-proof":
        result = builtin_total_spine_capital_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
