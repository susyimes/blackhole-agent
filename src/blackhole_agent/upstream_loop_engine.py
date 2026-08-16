"""Thin facade: multi-round loop control flow lives in the control engine.

Preserves the historical import path and CLI so ledger proofs and domain
modules keep working. Implementation is upstream_control_engine (loop mode).
Attribute access delegates to the engine module (PEP 562), so the facade
stays thin no matter how many names the engine grows; only the loop-mode
marker constants and the CLI dispatch live here. No skill-route discovery.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Sequence

from blackhole_agent import upstream_control_engine as _engine

# Loop-mode marker constants (checked by the control-engine proof).
CONTROL_ENGINE_IMPL = True
CONTROL_ENGINE_MODE = "loop"
CONTROL_NEST_IMPL = True
CONTROL_GRAPH_IMPL = True
GOVERNANCE_SPINE_IMPL = True
STEWARDSHIP_SPINE_IMPL = True

# Historical name before control-engine merge: on this facade ClassifyVerdict
# is the loop-mode alias, not the engine's pipeline-mode one.
ClassifyVerdict = _engine.LoopClassifyVerdict

# CLI subcommand -> engine builtin. Preserved from the historical facade so
# operator invocations and the registered ledger proof command keep working.
_CLI_DISPATCH = {
    "proof": "builtin_loop_engine_proof",
    "governance-proof": "builtin_governance_spine_proof",
    "stewardship-proof": "builtin_stewardship_spine_proof",
    "civilization-proof": "builtin_civilization_spine_proof",
    "continuum-proof": "builtin_continuum_spine_proof",
    "total-proof": "builtin_total_spine_proof",
    "effect-proof": "builtin_total_spine_effect_proof",
    "goal-proof": "builtin_total_spine_goal_proof",
    "adaptive-proof": "builtin_total_spine_adaptive_proof",
    "continuity-proof": "builtin_total_spine_continuity_proof",
    "finality-proof": "builtin_total_spine_finality_proof",
    "federation-proof": "builtin_total_spine_federation_proof",
    "quorum-proof": "builtin_total_spine_quorum_proof",
    "execution-proof": "builtin_total_spine_execution_proof",
    "actuation-proof": "builtin_total_spine_actuation_proof",
    "settlement-proof": "builtin_total_spine_settlement_proof",
    "clearing-proof": "builtin_total_spine_clearing_proof",
    "delivery-proof": "builtin_total_spine_delivery_proof",
    "custody-proof": "builtin_total_spine_custody_proof",
    "margin-proof": "builtin_total_spine_margin_proof",
    "collateral-proof": "builtin_total_spine_collateral_proof",
    "liquidity-proof": "builtin_total_spine_liquidity_proof",
    "funding-proof": "builtin_total_spine_funding_proof",
    "capital-proof": "builtin_total_spine_capital_proof",
    "solvency-proof": "builtin_total_spine_solvency_proof",
    "risk-proof": "builtin_total_spine_risk_proof",
    "stress-proof": "builtin_total_spine_stress_proof",
    "recovery-proof": "builtin_total_spine_recovery_proof",
    "resolution-proof": "builtin_total_spine_resolution_proof",
    "restructuring-proof": "builtin_total_spine_restructuring_proof",
    "emergence-proof": "builtin_total_spine_emergence_proof",
    "reorganization-proof": "builtin_total_spine_reorganization_proof",
    "rehabilitation-proof": "builtin_total_spine_rehabilitation_proof",
}


def __getattr__(name: str) -> Any:
    """Delegate every non-local name to the control engine (PEP 562)."""

    return getattr(_engine, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_engine)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List registered loop dialects")
    for command in sorted(_CLI_DISPATCH):
        sub.add_parser(command, help=f"Run {_CLI_DISPATCH[command]}")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        print(json.dumps({"dialects": _engine.list_loop_dialects()}, indent=2))
        return 0
    result = getattr(_engine, _CLI_DISPATCH[args.cmd])()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
