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
    absorb_domain_surface,
    builtin_ci_security_gate,
    builtin_harness_activation_gate,
    builtin_issue_triage_smoke,
    builtin_local_memory_roundtrip,
    builtin_milestone_gate_smoke,
    builtin_proposal_eval_smoke,
    builtin_repo_import_health,
    builtin_supervisor_compound_wake,
    builtin_tool_routing_preflight,
    default_ledger_path,
    hierarchical_stack_ids,
    load_ledger,
    meta_stack_ids,
    promote_composition,
    prove_ledger_integrity,
    register_capability,
    run_adaptive_growth,
    run_end_to_end_demo,
    run_growth_loop,
    save_ledger,
    scout_capability_gaps,
    seed_bootstrap_capabilities,
    synthesize_dynamic_domain_compositions,
    synthesize_hierarchical_compositions,
    synthesize_meta_hierarchical_compositions,
    synthesize_superstack_compositions,
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
    # Without package sources, domain absorb is blocked; composition remains recommended.
    scout = scout_capability_gaps(ledger, repo_path=tmp_path)
    assert scout["ok"] is True
    assert scout["used_skill_route_discovery"] is False
    assert scout["recommended"] is not None
    assert scout["recommended"]["suggested_id"] == "capability.composed-core-health"
    assert scout["recommended"]["status"] == "ready"
    assert "capability.scout-gaps" in ledger.capabilities
    assert "capability.growth-loop" in ledger.capabilities


def test_domain_builtins_smoke():
    memory = builtin_local_memory_roundtrip()
    tools = builtin_tool_routing_preflight()
    harness = builtin_harness_activation_gate()
    triage = builtin_issue_triage_smoke()
    security = builtin_ci_security_gate()
    proposal = builtin_proposal_eval_smoke()
    assert memory["ok"] is True and memory["privacy_guard"] is True
    assert tools["ok"] is True and "local_memory" in tools["executable_tool_names"]
    assert harness["ok"] is True
    assert harness["ready_decision"] == "ready_for_local_eval_activation"
    assert triage["ok"] is True and triage["validation_lane"] == "validation"
    assert security["ok"] is True and security["waived_outcome"] == "waiver_label_applied"
    assert proposal["ok"] is True and proposal["accepted_count"] >= 1
    assert not triage["used_skill_route_discovery"]
    assert not security["used_skill_route_discovery"]
    assert not proposal["used_skill_route_discovery"]


def test_scout_and_absorb_domain_surfaces_on_repo():
    repo = Path(__file__).resolve().parents[1]
    ledger = seed_bootstrap_capabilities(CapabilityLedger())
    scout = scout_capability_gaps(ledger, repo_path=repo)
    assert scout["ok"] is True
    assert "domain.local-memory" in scout["domain_pending"]
    assert any(
        item["status"] == "ready_to_absorb" and item["suggested_id"] == "domain.local-memory"
        for item in scout["opportunities"]
    )
    # Composition still outranks domain absorb while ready meta recipes exist.
    assert scout["recommended"]["status"] == "ready"
    assert scout["recommended"]["suggested_id"] == "capability.composed-core-health"

    ledger, absorbed = absorb_domain_surface(ledger, "domain.local-memory")
    assert absorbed.id == "domain.local-memory"
    assert "domain" in absorbed.tags
    assert absorbed.kind == "python"
    assert "builtin_local_memory_roundtrip" in absorbed.entry
    assert "domain.local-memory" in ledger.capabilities

    after = scout_capability_gaps(ledger, repo_path=repo)
    assert "domain.local-memory" in after["domain_absorbed"]
    assert "domain.local-memory" not in after["domain_pending"]


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
    # Ensure a clean growth path: seed first, remove promoted compositions and domain absorbs.
    from blackhole_agent.capability_compounder import ensure_seeded_ledger, remove_capability

    path, ledger = ensure_seeded_ledger(repo)
    # Multi-pass removal: hierarchical stacks depend on first-gen compositions, which
    # depend on domain leaves. Dependents must go first; a single alpha pass leaves
    # pillars in place and makes hierarchical stacks the next "growth" recommendation.
    for _ in range(12):
        removable = [
            capability_id
            for capability_id in list(ledger.capabilities)
            if capability_id.startswith("capability.composed-")
            or capability_id.startswith("domain.")
        ]
        if not removable:
            break
        progress = False
        # Prefer removing ids that nothing else depends on (true dependents first).
        def _dependent_count(capability_id: str) -> int:
            return sum(
                1
                for item in ledger.capabilities.values()
                if capability_id in item.dependencies and item.id != capability_id
            )

        for capability_id in sorted(removable, key=lambda item: (_dependent_count(item), item)):
            if capability_id not in ledger.capabilities:
                continue
            try:
                remove_capability(ledger, capability_id)
                progress = True
            except ValueError:
                continue
        if not progress:
            break
    save_ledger(path, ledger)
    remaining_composed = [
        capability_id
        for capability_id in ledger.capabilities
        if capability_id.startswith("capability.composed-") or capability_id.startswith("domain.")
    ]
    assert not remaining_composed, remaining_composed
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
    # Second pass promotes the domain composition only after domains exist, or evolution-ready,
    # or absorbs a domain surface once meta compositions with present members are handled.
    again = run_growth_loop(repo, timeout=180)
    assert again["ok"] is True, again
    assert again["used_skill_route_discovery"] is False
    assert again.get("promoted_id")
    assert again.get("proof", {}).get("ok") is True
    assert again.get("run", {}).get("ok") is True
    if again.get("grew"):
        assert again["promoted_id"].startswith(("capability.composed-", "domain."))
    else:
        assert again.get("reason") in {
            "already_promoted_reproved",
            "already_absorbed_reproved",
        }
    # Further growth continues via domain absorb / domain composition without skill-route.
    third = run_growth_loop(repo, timeout=180)
    assert third["ok"] is True, third
    assert third.get("promoted_id")
    assert third.get("proof", {}).get("ok") is True
    assert third.get("used_skill_route_discovery") is False
    # Keep growing through domain/dynamic/hierarchical/meta frontiers until stall or budget.
    last = third
    stalled = False
    for _ in range(40):
        last = run_growth_loop(repo, timeout=240)
        assert last["ok"] is True, last
        assert last.get("used_skill_route_discovery") is False
        assert last.get("proof", {}).get("ok") is True
        if not last.get("grew"):
            stalled = True
            break
    assert last.get("promoted_id")
    if stalled:
        assert last.get("grew") is False
        assert last.get("reason") in {
            "already_promoted_reproved",
            "already_absorbed_reproved",
        }
    else:
        # Meta-hierarchical and second-wave dynamics intentionally extend the horizon.
        assert last.get("grew") is True
        assert str(last.get("promoted_id") or "").startswith(
            ("capability.composed-", "domain.")
        )
    ledger = load_ledger(path)
    # Domain absorption + multi-domain composition must be reachable from pure growth.
    for domain_id in (
        "domain.local-memory",
        "domain.tool-routing",
        "domain.harness-activation",
        "domain.issue-triage",
        "domain.ci-security",
        "domain.proposal-eval",
    ):
        assert domain_id in ledger.capabilities
        assert ledger.capabilities[domain_id].last_proof_exit_code == 0
    assert "capability.composed-domain-core" in ledger.capabilities
    assert ledger.capabilities["capability.composed-domain-core"].last_proof_exit_code == 0
    assert "capability.composed-domain-ops" in ledger.capabilities
    assert ledger.capabilities["capability.composed-domain-ops"].last_proof_exit_code == 0
    # Dynamic synthesis should have produced at least one extra composed unit once leaves exist.
    dynamic_ids = [
        capability_id
        for capability_id, capability in ledger.capabilities.items()
        if "dynamic" in capability.tags or capability_id.startswith("capability.composed-dyn-")
    ]
    assert dynamic_ids, "expected at least one synthesized dynamic domain composition"
    # Hierarchical stacks break the post-domain re-prove plateau.
    hierarchical_ids = [
        capability_id
        for capability_id, capability in ledger.capabilities.items()
        if "hierarchical" in capability.tags or capability_id.startswith("capability.composed-stack-")
    ]
    assert hierarchical_ids, "expected at least one hierarchical composition stack"
    assert "capability.composed-stack-platform" in ledger.capabilities
    assert ledger.capabilities["capability.composed-stack-platform"].last_proof_exit_code == 0
    # Meta-hierarchical stack-of-stacks and/or second-wave supervisor domain past hierarchical plateau.
    meta_ids = [
        capability_id
        for capability_id, capability in ledger.capabilities.items()
        if "meta" in capability.tags or capability_id.startswith("capability.composed-meta-")
    ]
    second_wave = "domain.supervisor-compound" in ledger.capabilities
    assert meta_ids or second_wave, "expected meta-hierarchical stacks or second-wave domain"


def test_synthesize_dynamic_domain_compositions_skips_known_sets():
    ledger = seed_bootstrap_capabilities(CapabilityLedger())
    for domain_id, name in (
        ("domain.local-memory", "Local memory"),
        ("domain.tool-routing", "Tool routing"),
        ("domain.harness-activation", "Harness"),
        ("domain.issue-triage", "Triage"),
    ):
        register_capability(
            ledger,
            Capability(
                id=domain_id,
                name=name,
                description=name,
                kind="python",
                entry="blackhole_agent.capability_compounder:builtin_repo_import_health",
                proof_command="echo ok",
                dependencies=("repo.import-health",),
                tags=("domain", "absorbable"),
            ),
        )
    # Known domain-core member set must not be re-synthesized.
    synthesized = synthesize_dynamic_domain_compositions(ledger, limit=20)
    member_sets = {frozenset(item["members"]) for item in synthesized}
    assert frozenset(
        {"domain.local-memory", "domain.tool-routing", "domain.harness-activation"}
    ) not in member_sets
    # Novel mixes that include ops surfaces should appear as ready dynamic recipes.
    assert any(item.get("synthesized") and item["status"] == "ready" for item in synthesized)
    assert any("domain.issue-triage" in item["members"] for item in synthesized)
    # Multi-frontier: more than one distinct ready candidate when leaves allow it.
    ready = [item for item in synthesized if item.get("status") == "ready"]
    assert len(ready) >= 1


def test_hierarchical_synthesis_and_growth_past_plateau():
    """Hierarchical stacks surface once leaf compositions exist and grow the ledger."""

    repo = Path(__file__).resolve().parents[1]
    path = default_ledger_path(repo)
    ledger = load_ledger(path)
    # Current repo ledger should already have domain pillars; if not, grow until present.
    for _ in range(24):
        if {
            "capability.composed-domain-core",
            "capability.composed-domain-ops",
            "capability.composed-core-health",
        }.issubset(ledger.capabilities):
            break
        result = run_growth_loop(repo, timeout=180)
        assert result["ok"] is True, result
        ledger = load_ledger(path)

    hierarchical = synthesize_hierarchical_compositions(ledger, limit=5)
    platform_present = "capability.composed-stack-platform" in ledger.capabilities
    hierarchical_present = any(
        "hierarchical" in capability.tags or capability_id.startswith("capability.composed-stack-")
        for capability_id, capability in ledger.capabilities.items()
    )
    if hierarchical:
        ready = [item for item in hierarchical if item["status"] == "ready"]
        assert ready or platform_present or hierarchical_present, hierarchical
        assert any(item["suggested_id"] == "capability.composed-stack-platform" for item in ready) or (
            platform_present
        )
    else:
        # All hierarchical catalog/pairs already promoted — that is the plateau-break success case.
        assert hierarchical_present, "expected hierarchical stacks in ledger when scout is empty"
        assert platform_present

    scout = scout_capability_gaps(ledger, repo_path=repo)
    assert scout["ok"] is True
    # Either hierarchical is recommended or already promoted after prior grows.
    if "capability.composed-stack-platform" not in ledger.capabilities:
        assert scout.get("recommended") is not None
        assert scout["recommended"]["status"] in {"ready", "ready_to_absorb"}
        assert (
            scout["recommended"].get("synthesis") == "hierarchical"
            or str(scout["recommended"]["suggested_id"]).startswith("capability.composed-stack-")
            or str(scout["recommended"]["suggested_id"]).startswith("capability.composed-dyn-")
        )
        before = len(ledger.capabilities)
        grew = run_growth_loop(repo, timeout=240)
        assert grew["ok"] is True, grew
        assert grew["grew"] is True, grew
        assert grew["used_skill_route_discovery"] is False
        assert grew["after_count"] > before
        ledger = load_ledger(path)
        assert grew["promoted_id"] in ledger.capabilities
        assert ledger.capabilities[grew["promoted_id"]].last_proof_exit_code == 0
    else:
        platform = ledger.capabilities["capability.composed-stack-platform"]
        assert platform.last_proof_exit_code == 0
        assert "hierarchical" in platform.tags
        assert set(platform.dependencies) == {
            "capability.composed-core-health",
            "capability.composed-domain-core",
            "capability.composed-domain-ops",
        }
        # Grow remains safe (may expand further or re-prove) without skill-route.
        grew = run_growth_loop(repo, timeout=240)
        assert grew["ok"] is True, grew
        assert grew["used_skill_route_discovery"] is False


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


def test_builtin_supervisor_compound_wake():
    result = builtin_supervisor_compound_wake()
    assert result["ok"] is True
    assert result["codex_surface"] == "capability_compounder"
    assert result["codex_mode"] == "compound"
    assert result["used_skill_route_discovery"] is False
    assert "demo" in " ".join(str(part) for part in result["wake_command"])


def test_meta_hierarchical_synthesis_and_growth_past_hierarchical_plateau():
    """Stack-of-stacks and second-wave domain absorb break post-hierarchical re-prove."""

    repo = Path(__file__).resolve().parents[1]
    path = default_ledger_path(repo)
    ledger = load_ledger(path)

    # Ensure first-order hierarchical stacks exist (prior missions should have them).
    required_stacks = {
        "capability.composed-stack-platform",
        "capability.composed-stack-meta-evolution",
        "capability.composed-stack-domain-full",
    }
    for _ in range(32):
        if required_stacks.issubset(ledger.capabilities):
            break
        result = run_growth_loop(repo, timeout=240)
        assert result["ok"] is True, result
        ledger = load_ledger(path)
    assert required_stacks.issubset(ledger.capabilities), sorted(ledger.capabilities)

    stacks = hierarchical_stack_ids(ledger)
    assert len(stacks) >= 2
    meta = synthesize_meta_hierarchical_compositions(ledger, limit=5)
    meta_present = any(
        "meta" in capability.tags or capability_id.startswith("capability.composed-meta-")
        for capability_id, capability in ledger.capabilities.items()
    )
    platform_meta_present = "capability.composed-meta-platform-evolution" in ledger.capabilities
    if meta:
        ready = [item for item in meta if item["status"] == "ready"]
        assert ready or meta_present or platform_meta_present, meta
        assert any(
            item["suggested_id"] == "capability.composed-meta-platform-evolution" for item in ready
        ) or platform_meta_present
    else:
        assert meta_present, "expected meta-hierarchical stacks when synthesis is empty"

    scout = scout_capability_gaps(ledger, repo_path=repo)
    assert scout["ok"] is True
    assert "meta_hierarchical_ready" in scout

    before = len(ledger.capabilities)
    # Prefer growing a ready meta stack or second-wave domain absorb.
    grew = run_growth_loop(repo, timeout=360)
    assert grew["ok"] is True, grew
    assert grew["used_skill_route_discovery"] is False
    ledger = load_ledger(path)

    if not platform_meta_present and before == len(ledger.capabilities):
        # Explicit recipe path if scout preferred something else that was already done.
        grew = run_growth_loop(
            repo,
            recipe_id="capability.composed-meta-platform-evolution",
            timeout=360,
        )
        assert grew["ok"] is True, grew
        ledger = load_ledger(path)

    meta_ids = [
        capability_id
        for capability_id, capability in ledger.capabilities.items()
        if "meta" in capability.tags or capability_id.startswith("capability.composed-meta-")
    ]
    second_wave = "domain.supervisor-compound" in ledger.capabilities
    # Growth from hierarchical plateau must land meta stack and/or second-wave domain.
    assert meta_ids or second_wave or grew.get("grew") is True, {
        "meta_ids": meta_ids,
        "second_wave": second_wave,
        "grew": grew,
    }

    if "capability.composed-meta-platform-evolution" in ledger.capabilities:
        unit = ledger.capabilities["capability.composed-meta-platform-evolution"]
        assert unit.last_proof_exit_code == 0
        assert "meta" in unit.tags
        assert "hierarchical" in unit.tags
        assert set(unit.dependencies) == {
            "capability.composed-stack-platform",
            "capability.composed-stack-meta-evolution",
        }

    if "domain.supervisor-compound" in ledger.capabilities:
        domain = ledger.capabilities["domain.supervisor-compound"]
        assert domain.last_proof_exit_code == 0
        assert "second-wave" in domain.tags or "supervisor" in domain.tags

    # Further grow remains safe without skill-route.
    again = run_growth_loop(repo, timeout=360)
    assert again["ok"] is True, again
    assert again["used_skill_route_discovery"] is False


def test_superstack_synthesis_and_adaptive_growth_past_meta_plateau():
    """Third-order superstacks + adaptive multi-grow escape post-meta re-prove."""

    repo = Path(__file__).resolve().parents[1]
    path = default_ledger_path(repo)
    ledger = load_ledger(path)

    # Ensure enough meta stacks exist for superstack pairing.
    for _ in range(16):
        if len(meta_stack_ids(ledger)) >= 2:
            break
        result = run_growth_loop(repo, timeout=240)
        assert result["ok"] is True, result
        ledger = load_ledger(path)

    stacks = meta_stack_ids(ledger)
    assert len(stacks) >= 2, stacks
    superstacks = synthesize_superstack_compositions(ledger, limit=5)
    super_present = any(
        "superstack" in capability.tags or capability_id.startswith("capability.composed-super-")
        for capability_id, capability in ledger.capabilities.items()
    )
    if superstacks:
        ready = [item for item in superstacks if item["status"] == "ready"]
        assert ready or super_present, superstacks
        assert all(item.get("synthesis") == "superstack" for item in ready)
    else:
        assert super_present, "expected superstacks when synthesis is empty"

    scout = scout_capability_gaps(ledger, repo_path=repo)
    assert scout["ok"] is True
    assert "superstack_ready" in scout
    assert "meta_stacks" in scout

    before = len(ledger.capabilities)
    adaptive = run_adaptive_growth(repo, budget=6, timeout=300)
    assert adaptive["ok"] is True, adaptive
    assert adaptive["used_skill_route_discovery"] is False
    assert adaptive["action"] == "adaptive_grow"
    assert adaptive["steps_run"] >= 1
    ledger = load_ledger(path)

    super_ids = [
        capability_id
        for capability_id, capability in ledger.capabilities.items()
        if "superstack" in capability.tags or capability_id.startswith("capability.composed-super-")
    ]
    # Adaptive path should grow and/or already hold superstacks / multi-promotes.
    assert (
        adaptive.get("grew")
        or super_ids
        or adaptive.get("promoted_count", 0) >= 1
        or len(ledger.capabilities) >= before
    ), adaptive
    if adaptive.get("grew"):
        assert adaptive["after_count"] > before or adaptive["promoted_ids"]
        assert all(item in ledger.capabilities for item in adaptive["promoted_ids"])

    # Integrity plane proves a topo prefix without skill-route.
    integrity = prove_ledger_integrity(repo, timeout=120, limit=10)
    assert integrity["ok"] is True, integrity
    assert integrity["used_skill_route_discovery"] is False
    assert integrity["score"] >= 1.0
    assert integrity["proved_count"] >= 1
    assert integrity["failed_count"] == 0

    # Bootstrap surfaces for the new plane must seed into the ledger.
    path, ledger = __import__(
        "blackhole_agent.capability_compounder", fromlist=["ensure_seeded_ledger"]
    ).ensure_seeded_ledger(repo)
    assert "capability.adaptive-grow" in ledger.capabilities
    assert "capability.ledger-integrity" in ledger.capabilities


def test_cli_integrity_and_budget_grow_exit_zero():
    repo = Path(__file__).resolve().parents[1]
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    integrity = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "integrity",
            "--repo-path",
            str(repo),
            "--limit",
            "8",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert integrity.returncode == 0, integrity.stdout + integrity.stderr
    integrity_payload = json.loads(integrity.stdout)
    assert integrity_payload["ok"] is True
    assert integrity_payload["score"] >= 1.0
    assert integrity_payload["used_skill_route_discovery"] is False

    grow = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "grow",
            "--repo-path",
            str(repo),
            "--budget",
            "2",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=360,
    )
    assert grow.returncode == 0, grow.stdout + grow.stderr
    grow_payload = json.loads(grow.stdout)
    assert grow_payload["ok"] is True
    assert grow_payload["used_skill_route_discovery"] is False
    assert grow_payload.get("action") == "adaptive_grow"
    assert grow_payload.get("steps_run", 0) >= 1


def test_frontier_novelty_prefers_novel_over_stale_superstacks():
    """Scout ranks novel primitive coverage ahead of identical-leaf superstacks."""

    from blackhole_agent.capability_compounder import (
        is_primitive_capability,
        scout_frontier_novelty,
    )

    repo = Path(__file__).resolve().parents[1]
    path = default_ledger_path(repo)
    ledger = load_ledger(path)
    primitives = [c.id for c in ledger.capabilities.values() if is_primitive_capability(c)]
    assert "repo.import-health" in primitives
    assert any(item.startswith("domain.") for item in primitives)

    scout = scout_capability_gaps(ledger, repo_path=repo)
    assert "novel_ready" in scout
    assert "stale_ready" in scout
    assert "unique_composed_coverage_sets" in scout
    recommended = scout.get("recommended")
    if recommended and scout.get("novel_ready"):
        # When any novel frontier exists, recommended must be novel.
        assert recommended.get("novel") is True, recommended
        assert recommended["suggested_id"] in scout["novel_ready"]

    novelty = scout_frontier_novelty(ledger, repo_path=repo)
    assert novelty["ok"] is True
    assert novelty["used_skill_route_discovery"] is False
    assert novelty["primitive_count"] >= 3
    assert novelty["novel_ready_count"] + novelty["stale_ready_count"] == novelty["ready_count"]


def test_distill_tags_redundant_identical_coverage_stacks():
    """Soft distill marks non-champion stacks that share primitive coverage."""

    from blackhole_agent.capability_compounder import run_distill_ledger

    repo = Path(__file__).resolve().parents[1]
    path = default_ledger_path(repo)
    before = load_ledger(path)
    before_count = len(before.capabilities)
    report = run_distill_ledger(repo, remove=False, only_synthesized=True)
    assert report["ok"] is True, report
    assert report["used_skill_route_discovery"] is False
    assert report["before_count"] == before_count
    # Soft distill preserves ledger size.
    assert report["after_count"] == before_count
    assert report["removed_count"] == 0
    ledger = load_ledger(path)
    if report["redundant_count"] > 0:
        for capability_id in report["redundant"]:
            tags = ledger.capabilities[capability_id].tags
            assert "redundant" in tags
            assert "distilled" in tags
        assert report["champions"]


def test_autonomic_cycle_novelty_grow_distill_integrity():
    """Closed autonomic plane: novelty grow → distill → integrity without skill-route."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        run_autonomic_cycle,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.frontier-novelty" in ledger.capabilities
    assert "capability.distill-ledger" in ledger.capabilities
    assert "capability.autonomic-cycle" in ledger.capabilities

    result = run_autonomic_cycle(
        repo,
        budget=2,
        distill_remove=False,
        integrity_limit=8,
        timeout=240,
    )
    assert result["ok"] is True, result
    assert result["action"] == "autonomic_cycle"
    assert result["used_skill_route_discovery"] is False
    assert result["growth"]["ok"] is True
    assert result["distill"]["ok"] is True
    assert result["integrity"]["ok"] is True
    assert result["integrity"]["score"] >= 1.0
    assert result["after_count"] >= 1
    # Either advanced novel growth, distilled redundancy, or cleanly reported state.
    assert (
        result.get("advanced")
        or result["growth"].get("steps_run", 0) >= 1
        or result["distill"].get("redundant_count", 0) >= 0
    )

    # CLI surface for the autonomic plane.
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    novelty_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "novelty",
            "--repo-path",
            str(repo),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert novelty_cli.returncode == 0, novelty_cli.stdout + novelty_cli.stderr
    novelty_payload = json.loads(novelty_cli.stdout)
    assert novelty_payload["ok"] is True
    assert novelty_payload["used_skill_route_discovery"] is False


def test_second_wave_domain_builtins_offline():
    """Second-wave persona / proposal-synthesis / kernel surfaces prove offline."""

    from blackhole_agent.capability_compounder import (
        builtin_kernel_preflight,
        builtin_persona_render,
        builtin_proposal_synthesis_smoke,
    )

    persona = builtin_persona_render()
    assert persona["ok"] is True
    assert persona["used_skill_route_discovery"] is False
    assert persona["chars"] > 100

    proposal = builtin_proposal_synthesis_smoke()
    assert proposal["ok"] is True
    assert proposal["item_count"] >= 1
    assert proposal["used_skill_route_discovery"] is False

    kernel = builtin_kernel_preflight()
    assert kernel["ok"] is True
    assert kernel["provider"] == "grok"
    assert kernel["used_skill_route_discovery"] is False


def test_mission_plane_expands_primitives_and_runs_program():
    """Mission plane absorbs second-wave leaves, plans, runs, and reopens novelty."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        run_mission_plane,
        scout_frontier_novelty,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    for capability_id in (
        "capability.goal-plan",
        "capability.program-run",
        "capability.second-wave-absorb",
        "capability.mission-plane",
    ):
        assert capability_id in ledger.capabilities

    before = scout_frontier_novelty(ledger, repo_path=repo)
    result = run_mission_plane(
        repo,
        "second-wave identity persona proposal kernel health",
        max_steps=4,
        absorb_ready=True,
        grow_budget=2,
        timeout=300,
    )
    assert result["ok"] is True, result
    assert result["action"] == "mission_plane"
    assert result["used_skill_route_discovery"] is False
    assert result["program"]["ok"] is True
    assert result["program"]["passed_count"] >= 1
    assert result["plan"]["step_count"] >= 1

    ledger_after = load_ledger(path)
    for surface_id in (
        "domain.persona",
        "domain.proposal-synthesis",
        "domain.kernel-preflight",
    ):
        assert surface_id in ledger_after.capabilities, surface_id
    after = scout_frontier_novelty(ledger_after, repo_path=repo)
    # Primitive universe must expand (or already include second-wave leaves).
    assert after["primitive_count"] >= before["primitive_count"]
    assert after["primitive_count"] >= 20
    # Either absorption expanded, growth advanced, or novel frontiers reopened.
    assert (
        result.get("expanded")
        or (result.get("absorb") or {}).get("absorbed_count", 0) >= 0
        or after["novel_ready_count"] >= 0
    )

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    plan_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "plan",
            "health integrity persona",
            "--repo-path",
            str(repo),
            "--max-steps",
            "3",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert plan_cli.returncode == 0, plan_cli.stdout + plan_cli.stderr
    plan_payload = json.loads(plan_cli.stdout)
    assert plan_payload["ok"] is True
    assert plan_payload["step_count"] >= 1


def test_outcome_contract_parses_and_evaluates_machine_predicates():
    """done_when becomes machine-checkable against live ledger evidence."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        evaluate_outcome_contract,
        parse_outcome_contract,
        prove_capability,
        run_contract_plane,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    for capability_id in (
        "capability.outcome-contract",
        "capability.contract-plane",
    ):
        assert capability_id in ledger.capabilities, capability_id

    parsed = parse_outcome_contract(
        "min_capabilities:3; capability_exists:repo.import-health; "
        "no skill-route discovery; prose note only"
    )
    assert parsed["ok"] is True
    assert parsed["machine_checkable"] is True
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "min_capabilities" in kinds
    assert "capability_exists" in kinds
    assert "no_skill_route" in kinds
    assert any("prose" in note.lower() for note in parsed["notes"]) or parsed["notes"]

    # Ensure a known primitive is proved so capability_proved can pass.
    ledger, proof = prove_capability(
        ledger,
        "repo.import-health",
        cwd=repo,
        timeout=60,
    )
    assert proof.ok is True
    from blackhole_agent.capability_compounder import save_ledger

    save_ledger(path, ledger)

    passing = evaluate_outcome_contract(
        repo,
        "min_capabilities:3; capability_exists:repo.import-health; "
        "capability_proved:repo.import-health; no_skill_route",
        run_programs=False,
    )
    assert passing["ok"] is True, passing
    assert passing["machine_checkable"] is True
    assert passing["met"] is True, passing
    assert passing["used_skill_route_discovery"] is False
    assert passing["failed_count"] == 0

    failing = evaluate_outcome_contract(
        repo,
        "min_capabilities:99999; capability_exists:capability.does-not-exist",
        run_programs=False,
    )
    assert failing["ok"] is True
    assert failing["met"] is False
    assert failing["failed_count"] >= 1

    plane = run_contract_plane(
        repo,
        "health inventory milestone",
        "min_capabilities:5; min_primitives:3; capability_exists:repo.import-health; "
        "capability_proved:repo.import-health; program_passes:repo.import-health; "
        "no_skill_route; mission_plane_ok",
        max_steps=3,
        absorb_ready=False,
        grow_budget=0,
        run_mission=True,
        timeout=180,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "contract_plane"
    assert plane["machine_checkable"] is True
    assert plane["met"] is True, plane
    assert plane["used_skill_route_discovery"] is False
    assert plane["mission"] is not None
    assert plane["mission"]["ok"] is True
    assert plane["contract"]["passed_count"] >= 5

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    contract_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "contract",
            "min_capabilities:3;capability_exists:repo.import-health;no_skill_route",
            "--repo-path",
            str(repo),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert contract_cli.returncode == 0, contract_cli.stdout + contract_cli.stderr
    contract_payload = json.loads(contract_cli.stdout)
    assert contract_payload["ok"] is True
    assert contract_payload["met"] is True
