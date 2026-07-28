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
    register_capability,
    run_end_to_end_demo,
    save_ledger,
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
