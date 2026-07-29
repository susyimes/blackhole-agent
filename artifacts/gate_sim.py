"""Simulate unbound milestone gate for execution-plane complete."""
from __future__ import annotations

from pathlib import Path

from blackhole_agent.unbound import (
    TurnDecision,
    changed_paths_since,
    evaluate_milestone,
    is_behavior_path,
)

workspace = Path(__file__).resolve().parents[1]
done_when = (
    "no_skill_route; execution_ok; state_applied_ok; min_state_height:2; state_root_valid; "
    "finality_ok; finalized_ok; min_epochs:2; finality_cert_valid; chain_valid; "
    "capability_exists:capability.finality-plane; capability_exists:repo.import-health"
)
decision = TurnDecision(
    status="complete",
    mission_goal=(
        "Build a deterministic world-state execution plane that materializes "
        "irreversible multi-epoch finality into hash-chained state transitions "
        "with re-verifiable execution certificates, sterile rehydrate+prove, "
        "genesis-replay tip match, and adversarial falsification of post-finality "
        "mutation/reorder/forged-root attacks — without skill-route."
    ),
    done_when=done_when,
    summary="Execution plane complete and proved.",
    strategy="Compound finality into deterministic world-state.",
    next_step="",
    capability_delta=(
        "Execution plane materializes irreversible multi-epoch finality into "
        "deterministic hash-chained world-state transitions with execution "
        "certificates, sterile tip re-prove, genesis replay matching tip, and "
        "adversarial falsification of post-finality mutation/reorder/forged-root "
        "without skill-route."
    ),
    outcome_evidence=(
        "src/blackhole_agent/capability_compounder.py",
        "src/blackhole_agent/unbound.py",
        "capabilities/ledger.json",
        "artifacts/execution-bundles/",
    ),
    validation=(
        {
            "command": (
                "python -c \"from blackhole_agent.capability_compounder import "
                "run_execution_plane; from pathlib import Path; "
                "r=run_execution_plane(Path('.'), epoch_count=2, run_finality=True, "
                "run_quorum=True, run_continuity=False, inject_byzantine=True, "
                "timeout=300); assert r['ok'] and r['state_applied']\""
            ),
            "exit_code": 0,
            "summary": "plane ok",
        },
        {
            "command": (
                "python -c \"from blackhole_agent.capability_compounder import "
                "ensure_seeded_ledger; from pathlib import Path; "
                "p,l=ensure_seeded_ledger(Path('.')); "
                "assert 'capability.execution-plane' in l.capabilities\""
            ),
            "exit_code": 0,
            "summary": "ledger has execution-plane",
        },
    ),
    done_when_met=True,
    commit_message=(
        "Blackhole unbound complete: world-state execution plane over multi-epoch finality"
    ),
)

changed = changed_paths_since(
    workspace, "faccb8b8f562e1bd97e9a9fbc631f29928af9583"
)
print("changed count", len(changed))
print("behavior", [p for p in changed if is_behavior_path(p)])
gate = evaluate_milestone(
    decision,
    changed_paths=changed,
    workspace=workspace,
    mission_done_when=done_when,
)
print("requested", gate.requested)
print("accepted", gate.accepted)
print("reasons", gate.reasons)
print("behavior_paths", gate.behavior_paths)
