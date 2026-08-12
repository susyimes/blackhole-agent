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
    TOTAL_SPINE_COMPRESS_THRESHOLD,
    TOTAL_SPINE_DEFAULT_EFFECT_CAPABILITIES,
    TOTAL_SPINE_DEFAULT_ROOT,
    TOTAL_SPINE_DEFAULT_ROOTS,
    TOTAL_SPINE_EFFECT_IMPL,
    TOTAL_SPINE_IMPL,
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
    annotate_total_spine_effects,
    build_live_domain_hooks,
    builtin_civilization_spine_proof,
    builtin_continuum_spine_proof,
    builtin_control_nest_proof,
    builtin_governance_spine_proof,
    builtin_loop_engine_proof,
    builtin_stewardship_spine_proof,
    builtin_total_spine_effect_proof,
    builtin_total_spine_proof,
    compose_loop_of_loop,
    compose_pipeline_of_pipeline,
    default_extract_dispatched,
    dispatch_total_spine_effects,
    get_loop_dialect,
    governance_nest_depth,
    governance_nest_path,
    list_loop_dialects,
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
    recover_governance_child_path,
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
    seal_total_spine_effect_chain,
    seal_total_spine_hop_chain,
    stewardship_constitution_chain,
    stewardship_nest_depth,
    stewardship_nest_path,
    total_nest_depth,
    total_nest_path,
    verify_loop_receipt,
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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
