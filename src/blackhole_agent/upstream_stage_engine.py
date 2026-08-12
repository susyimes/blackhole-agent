"""Thin facade: multi-stage pipeline control flow lives in the control engine.

Preserves the historical import path and CLI so ledger proofs and domain
modules keep working. Implementation is upstream_control_engine (pipeline mode).
No skill-route discovery.
"""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from blackhole_agent.upstream_control_engine import (  # noqa: F401
    CAMPAIGN_NEST_STAGES,
    CAMPAIGN_STAGES,
    FLEET_STAGES,
    OPERATIONAL_NEST,
    PIPELINE_DIALECTS,
    PIPELINE_STACK,
    REPO_ROOT,
    SCHEMA_VERSION,
    AfterStage,
    ClassifyVerdict,
    PipelineDialect,
    PipelineNestHooks,
    PipelineState,
    RunStage,
    SealPipeline,
    ShouldAbort,
    StageRefused,
    annotate_control_nest,
    builtin_control_nest_proof,
    builtin_stage_engine_proof,
    collect_stage_digests,
    compose_pipeline_of_pipeline,
    get_pipeline_dialect,
    list_pipeline_dialects,
    nest_path,
    normalize_stages,
    operational_nest_path,
    run_control_graph,
    run_nested_pipeline,
    run_operational_spine,
    run_stage_pipeline,
    seal_pipeline_receipt,
    verify_pipeline_digest,
)

CONTROL_ENGINE_IMPL = True
CONTROL_ENGINE_MODE = "pipeline"
CONTROL_NEST_IMPL = True
CONTROL_GRAPH_IMPL = True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("proof", help="Run hermetic stage-engine proof")
    sub.add_parser("list", help="List registered pipeline dialects")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "list":
        print(json.dumps({"dialects": list_pipeline_dialects()}, indent=2))
        return 0
    if args.cmd == "proof":
        result = builtin_stage_engine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
