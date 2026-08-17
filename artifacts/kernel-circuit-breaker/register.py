from pathlib import Path

from blackhole_agent.capability_compounder import (
    Capability,
    default_ledger_path,
    evaluate_outcome_contract,
    load_ledger,
    prove_capability,
    register_capability,
    save_ledger,
)

PROOF = (
    "uv run python -c \""
    "from blackhole_agent.kernel_health import builtin_kernel_circuit_breaker_proof; "
    "r=builtin_kernel_circuit_breaker_proof(); "
    "assert r['ok'] and r.get('action')=='kernel_circuit_breaker' "
    "and r.get('passed_count',0) >= 14 and not r.get('used_skill_route_discovery')\""
)

root = Path(".").resolve()
path = default_ledger_path(root)
ledger = load_ledger(path)
capability = Capability(
    id="capability.kernel-circuit-breaker",
    name="Kernel circuit breaker",
    description=(
        "A non-retryable first-class kernel death (402 quota, auth) trips a "
        "durable circuit breaker. Later turns and missions skip the open-circuit "
        "kernel and fail over to a peer CLI or the local capability kernel, so "
        "the harvested Grok 402 storm cannot retry a dead kernel or stall "
        "without a structured decision."
    ),
    kind="python",
    entry="blackhole_agent.kernel_health:builtin_kernel_circuit_breaker_proof",
    proof_command=PROOF,
    dependencies=(
        "repo.import-health",
        "capability.ledger-inventory",
        "unbound.milestone-gate",
        "capability.kernel-decision-salvage",
    ),
    behavior_paths=(
        "src/blackhole_agent/kernel_health.py",
        "src/blackhole_agent/kernel_salvage.py",
    ),
    capability_delta=(
        "Quota-exhausted Grok is remembered: the harvested 402 trips a durable "
        "breaker, later resolution skips that kernel, and the mission continues "
        "through a local capability kernel instead of blocking or burning twelve retries."
    ),
    tags=("unbound", "kernel", "resilience", "circuit-breaker"),
    source_mission_id="20260817T105215Z-9ad8cdb7",
    source_milestone=1,
)
register_capability(ledger, capability, replace=True)
save_ledger(path, ledger)
ledger, result = prove_capability(ledger, "capability.kernel-circuit-breaker", cwd=root)
save_ledger(path, ledger)
print("prove_ok", result.ok, result.exit_code, result.summary)
contract = evaluate_outcome_contract(
    root,
    "capability_proved:capability.kernel-circuit-breaker; capability_proved:capability.kernel-decision-salvage; no_skill_route",
    run_programs=False,
)
print("contract_met", contract.get("met"))
print(
    [
        (item.get("kind"), item.get("arg"), item.get("passed"))
        for item in contract.get("results") or []
    ]
)
