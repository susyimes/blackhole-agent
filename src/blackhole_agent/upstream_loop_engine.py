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
    LOOP_DIALECTS,
    LOOP_STACK,
    OPERATIONAL_NEST,
    REPO_ROOT,
    SCHEMA_VERSION,
    BuildChildKwargs,
    ExtractChildDigest,
    ExtractDispatched,
    ExtractPortfolio,
    IsIdleRound,
    LoopClassifyVerdict,
    LoopDialect,
    LoopRefused,
    LoopState,
    OnChildResult,
    PostRoundStop,
    PreRoundStop,
    SealLoop,
    annotate_control_nest,
    builtin_loop_engine_proof,
    compose_loop_of_loop,
    default_extract_dispatched,
    get_loop_dialect,
    list_loop_dialects,
    nest_path,
    open_loop_dir,
    operational_nest_path,
    resolve_portfolio,
    run_durable_loop,
    run_nested_control,
    seal_json_receipt,
    verify_loop_receipt,
)

# Historical name before control-engine merge.
ClassifyVerdict = LoopClassifyVerdict

CONTROL_ENGINE_IMPL = True
CONTROL_ENGINE_MODE = "loop"
CONTROL_NEST_IMPL = True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("proof", help="Run hermetic multi-round loop-engine proof")
    sub.add_parser("list", help="List registered loop dialects")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "list":
        print(json.dumps({"dialects": list_loop_dialects()}, indent=2))
        return 0
    if args.cmd == "proof":
        result = builtin_loop_engine_proof()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
