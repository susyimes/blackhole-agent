"""Tests for the durable Unbound capability compounder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    builtin_milestone_gate_smoke,
    builtin_repo_import_health,
    default_ledger_path,
    load_ledger,
    promote_composition,
    register_capability,
    run_end_to_end_demo,
    run_growth_loop,
    save_ledger,
    scout_capability_gaps,
    seed_bootstrap_capabilities,
    topological_order,
)
from blackhole_agent.unbound import (
    TurnDecision,
    build_turn_prompt,
    register_milestone_capability,
)


def _make_mission_state(tmp_path: Path):
    from blackhole_agent.unbound import UnboundMission

    return UnboundMission(
        schema_version=1,
        mission_id="mission-cap",
        created_at="2026-07-28T00:00:00Z",
        updated_at="2026-07-28T00:00:00Z",
        repo_path=str(tmp_path),
        workspace_path=str(tmp_path),
        branch="unbound/test",
        target_branch="main",
        goal="Compound capabilities.",
        done_when="Ledger works.",
        stage="execution",
        base_head="abc",
        last_milestone_head="abc",
    )


def test_register_and_topological_order(tmp_path: Path):
    ledger = CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id="base.one",
            name="Base",
            description="base",
            kind="command",
            entry="echo base",
            proof_command="echo base-proof",
        ),
    )
    register_capability(
        ledger,
        Capability(
            id="derived.two",
            name="Derived",
            description="derived",
            kind="command",
            entry="echo derived",
            proof_command="echo derived-proof",
            dependencies=("base.one",),
        ),
    )
    assert topological_order(ledger, ["derived.two"]) == ["base.one", "derived.two"]


def test_cycle_rejected():
    ledger = CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id="a.loop",
            name="A",
            description="a",
            kind="command",
            entry="echo a",
            proof_command="echo a",
        ),
    )
    register_capability(
        ledger,
        Capability(
            id="b.loop",
            name="B",
            description="b",
            kind="command",
            entry="echo b",
            proof_command="echo b",
            dependencies=("a.loop",),
        ),
    )
    with pytest.raises(ValueError, match="cycle"):
        register_capability(
            ledger,
            Capability(
                id="a.loop",
                name="A",
                description="a",
                kind="command",
                entry="echo a",
                proof_command="echo a",
                dependencies=("b.loop",),
            ),
            replace=True,
        )


def test_builtin_health_does_not_import_skill_routing():
    result = builtin_repo_import_health()
    assert result["ok"] is True
    assert result["skill_route_symbols_in_compounder"] == []
    assert result["imports_skill_routing"] is False


def test_builtin_milestone_gate_smoke():
    result = builtin_milestone_gate_smoke()
    assert result["ok"] is True
    assert result["accepted_behavior"] is True
    assert result["rejected_docs_only"] is True


def test_seed_prove_compose_demo_on_repo():
    repo = Path(__file__).resolve().parents[1]
    result = run_end_to_end_demo(repo)
    assert result["ok"] is True
    assert result["used_skill_route_discovery"] is False
    assert result["capability_count"] >= 3
    assert all(item["ok"] for item in result["composed"])


def test_prompt_includes_capability_ledger(tmp_path: Path):
    workspace = tmp_path
    (workspace / "capabilities").mkdir()
    ledger = seed_bootstrap_capabilities(CapabilityLedger())
    save_ledger(default_ledger_path(workspace), ledger)
    # Point builtins at empty-ish workspace by writing ledger only; prompt just reads JSON.
    state = _make_mission_state(workspace)
    prompt = build_turn_prompt(
        state,
        {
            "head": "abc",
            "status": "",
            "diff_stat": "",
            "recent_commits": "abc seed",
        },
        state_path=workspace / "state.json",
    )
    assert "Compounded capability ledger" in prompt
    assert "repo.import-health" in prompt
    assert "skill_route_discovery_capability_pipeline" not in prompt


def test_register_milestone_capability_persists(tmp_path: Path):
    decision = TurnDecision.from_payload(
        {
            "status": "milestone",
            "summary": "Added compounder",
            "strategy": "direct",
            "next_step": "compose",
            "capability_delta": "Ledger registers milestone capabilities",
            "outcome_evidence": ["capabilities/ledger.json"],
            "validation": [
                {
                    "command": f'"{sys.executable}" -c "print(1)"',
                    "exit_code": 0,
                    "summary": "ok",
                }
            ],
            "done_when_met": False,
            "commit_message": "cap",
            "mission_goal": "",
            "done_when": "",
        }
    )
    capability_id = register_milestone_capability(
        workspace=tmp_path,
        mission_id="mission-1",
        milestone_number=1,
        decision=decision,
        behavior_paths=("src/blackhole_agent/capability_compounder.py",),
    )
    assert capability_id
    ledger = load_ledger(default_ledger_path(tmp_path))
    assert capability_id in ledger.capabilities
    assert ledger.capabilities[capability_id].source_milestone == 1


def test_cli_demo_exits_zero():
    repo = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "blackhole_agent.unbound", "capability", "demo", "--repo-path", str(repo)],
        cwd=repo,
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(repo / "src")},
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["used_skill_route_discovery"] is False


def test_scout_ranks_ready_composition(tmp_path: Path):
    ledger = seed_bootstrap_capabilities(CapabilityLedger())
    scout = scout_capability_gaps(ledger, repo_path=tmp_path)
    assert scout["ok"] is True
    assert scout["used_skill_route_discovery"] is False
    assert scout["recommended"] is not None
    assert scout["recommended"]["suggested_id"] == "capability.composed-core-health"
    assert scout["recommended"]["status"] == "ready"
    assert "capability.scout-gaps" in ledger.capabilities
    assert "capability.growth-loop" in ledger.capabilities


def test_promote_composition_registers_invocable_unit(tmp_path: Path):
    ledger = seed_bootstrap_capabilities(CapabilityLedger())
    save_ledger(default_ledger_path(tmp_path), ledger)
    # Promotion against a temp ledger path still validates graph; run uses repo builtins.
    ledger, promoted = promote_composition(
        ledger,
        (
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ),
        capability_id="capability.composed-core-health",
    )
    assert promoted.id == "capability.composed-core-health"
    assert set(promoted.dependencies) == {
        "repo.import-health",
        "capability.ledger-inventory",
        "unbound.milestone-gate",
    }
    assert "composed" in promoted.tags
    assert promoted.kind == "python"
    assert "builtin_execute_composed_capability" in promoted.entry


def test_growth_loop_promotes_and_proves_on_repo():
    repo = Path(__file__).resolve().parents[1]
    # Ensure a clean growth path: seed first, remove promoted compositions from prior runs.
    from blackhole_agent.capability_compounder import ensure_seeded_ledger, remove_capability

    path, ledger = ensure_seeded_ledger(repo)
    for composed_id in (
        "capability.composed-core-health",
        "capability.composed-evolution-ready",
    ):
        if composed_id in ledger.capabilities:
            try:
                remove_capability(ledger, composed_id)
            except ValueError:
                pass
    save_ledger(path, ledger)
    before = len(load_ledger(path).capabilities)
    result = run_growth_loop(repo, timeout=180)
    assert result["ok"] is True, result
    assert result["used_skill_route_discovery"] is False
    assert result["grew"] is True
    assert result["promoted_id"] == "capability.composed-core-health"
    assert result["after_count"] > before
    assert result["proof"]["ok"] is True
    assert result["run"]["ok"] is True
    ledger = load_ledger(path)
    assert "capability.composed-core-health" in ledger.capabilities
    assert ledger.capabilities["capability.composed-core-health"].last_proof_exit_code == 0
    # Second pass may promote the next ready recipe or re-prove an existing one.
    again = run_growth_loop(repo, timeout=180)
    assert again["ok"] is True, again
    assert again["used_skill_route_discovery"] is False
    assert again.get("promoted_id")
    assert again.get("proof", {}).get("ok") is True
    assert again.get("run", {}).get("ok") is True
    if again.get("grew"):
        assert again["promoted_id"] == "capability.composed-evolution-ready"
    else:
        assert again.get("reason") == "already_promoted_reproved"
    # Exhaust remaining recipes, then grow must re-prove without failing.
    third = run_growth_loop(repo, timeout=180)
    assert third["ok"] is True, third
    assert third.get("promoted_id")
    assert third.get("proof", {}).get("ok") is True
    fourth = run_growth_loop(repo, timeout=180)
    assert fourth["ok"] is True, fourth
    assert fourth["grew"] is False
    assert fourth["reason"] == "already_promoted_reproved"
    assert fourth.get("promoted_id")


def test_cli_scout_and_grow_exit_zero():
    repo = Path(__file__).resolve().parents[1]
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    scout = subprocess.run(
        [sys.executable, "-m", "blackhole_agent.unbound", "capability", "scout", "--repo-path", str(repo)],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert scout.returncode == 0, scout.stdout + scout.stderr
    scout_payload = json.loads(scout.stdout)
    assert scout_payload["ok"] is True
    assert isinstance(scout_payload["opportunities"], list)

    grow = subprocess.run(
        [sys.executable, "-m", "blackhole_agent.unbound", "capability", "grow", "--repo-path", str(repo)],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=240,
    )
    assert grow.returncode == 0, grow.stdout + grow.stderr
    grow_payload = json.loads(grow.stdout)
    assert grow_payload["ok"] is True
    assert grow_payload["used_skill_route_discovery"] is False
    assert grow_payload.get("promoted_id") or grow_payload.get("grew") is False
