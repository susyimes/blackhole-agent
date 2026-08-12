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
    federate_total_spine,
    federation_certificate_path,
    finality_certificate_path,
    get_loop_dialect,
    governance_nest_depth,
    governance_nest_path,
    list_loop_dialects,
    load_total_spine_continuity_checkpoint,
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
    seal_json_receipt,
    seal_total_spine_adaptive_chain,
    seal_total_spine_continuity_chain,
    seal_total_spine_continuity_checkpoint,
    seal_total_spine_contract,
    seal_total_spine_effect_chain,
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
    verify_total_spine_continuity_checkpoint,
    verify_total_spine_federation_certificate,
    verify_total_spine_finality_certificate,
    write_total_spine_continuity_checkpoint,
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
