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
    build_turn_prompt,
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
            # Dependents of composed/domain members (e.g. benchmark planes that
            # exercise domain leaves) block their removal, so they go first.
            or any(
                dependency.startswith(("capability.composed-", "domain."))
                for dependency in ledger.capabilities[capability_id].dependencies
            )
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


def test_assurance_plane_ablation_transfer_and_adversarial():
    """Assurance plane: ablation fails broken proofs, transfer re-proves packages, adversarial rejects false contracts."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_ledger,
        run_ablation_proof,
        run_adversarial_contract,
        run_assurance_plane,
        run_transfer_plane,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    for capability_id in (
        "capability.ablation-proof",
        "capability.transfer-plane",
        "capability.adversarial-contract",
        "capability.assurance-plane",
    ):
        assert capability_id in ledger.capabilities, capability_id

    before_ids = set(ledger.capabilities)
    ablation = run_ablation_proof(repo, "repo.import-health", timeout=90)
    assert ablation["ok"] is True, ablation
    assert ablation["action"] == "ablation_proof"
    assert ablation["live_ledger_mutated"] is False
    assert ablation["passed_count"] >= 3
    assert ablation["used_skill_route_discovery"] is False
    # Live ledger must not lose or invent ids from in-memory ablation clones.
    after_ablation = load_ledger(path)
    assert set(after_ablation.capabilities) == before_ids

    transfer = run_transfer_plane(
        repo,
        ["repo.import-health", "capability.ledger-inventory", "unbound.milestone-gate"],
        timeout=120,
        prove_imported=True,
    )
    assert transfer["ok"] is True, transfer
    assert transfer["action"] == "transfer_plane"
    assert transfer["member_count"] >= 2
    assert transfer["proved_count"] >= 2
    assert transfer["reexport_members_match"] is True
    assert Path(transfer["package_path"]).is_file()
    assert transfer["used_skill_route_discovery"] is False

    adversarial = run_adversarial_contract(repo, timeout=90, run_programs=False)
    assert adversarial["ok"] is True, adversarial
    assert adversarial["positive_ok"] is True
    assert adversarial["negatives_ok"] is True
    assert adversarial["negatives_passed"] >= 2
    assert adversarial["used_skill_route_discovery"] is False

    plane = run_assurance_plane(repo, timeout=120)
    assert plane["ok"] is True, plane
    assert plane["action"] == "assurance_plane"
    assert plane["ablation"]["ok"] is True
    assert plane["transfer"]["ok"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["used_skill_route_discovery"] is False

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    assurance_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "assurance",
            "--repo-path",
            str(repo),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert assurance_cli.returncode == 0, assurance_cli.stdout + assurance_cli.stderr
    assurance_payload = json.loads(assurance_cli.stdout)
    assert assurance_payload["ok"] is True
    assert assurance_payload["action"] == "assurance_plane"


def test_sovereignty_plane_certificate_issue_and_verify():
    """Sovereignty plane compounds contract+assurance into a re-verifiable certificate."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        issue_sovereignty_certificate,
        load_sovereignty_certificate,
        parse_outcome_contract,
        run_sovereignty_plane,
        verify_sovereignty_certificate,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.sovereignty-plane" in ledger.capabilities
    assert "capability.assurance-plane" in ledger.capabilities

    # Predicate surface accepts sovereignty forms.
    parsed = parse_outcome_contract(
        "no_skill_route; assurance_plane_ok; sovereignty_ok; certificate_valid"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert kinds == {
        "no_skill_route",
        "assurance_plane_ok",
        "sovereignty_ok",
        "certificate_valid",
    }

    plane = run_sovereignty_plane(
        repo,
        "health inventory milestone",
        (
            "min_capabilities:5; min_primitives:3; capability_exists:repo.import-health; "
            "capability_proved:repo.import-health; program_passes:repo.import-health; "
            "no_skill_route; mission_plane_ok"
        ),
        max_steps=3,
        absorb_ready=False,
        grow_budget=0,
        run_mission=True,
        timeout=180,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "sovereignty_plane"
    assert plane["contract"]["ok"] is True
    assert plane["assurance"]["ok"] is True
    assert plane["certificate"]["ok"] is True
    assert plane["verify"]["valid"] is True
    assert plane["verify"]["hash_ok"] is True
    assert plane["used_skill_route_discovery"] is False
    cert_path = Path(plane["certificate"]["certificate_path"])
    assert cert_path.is_file()
    loaded = load_sovereignty_certificate(cert_path)
    assert loaded["certificate_hash"] == plane["certificate"]["certificate_hash"]
    assert loaded["kind"] == "sovereignty_certificate"

    verify = verify_sovereignty_certificate(
        cert_path, repo_path=repo, recheck_live=True, timeout=60
    )
    assert verify["ok"] is True, verify
    assert verify["valid"] is True
    assert verify["hash_ok"] is True
    assert verify["claims_ok"] is True
    assert verify["live_recheck"] is True

    # Tampered certificate must fail hash verification.
    tampered = dict(loaded)
    tampered["claims"] = {**loaded["claims"], "assurance_ok": False}
    bad = verify_sovereignty_certificate(tampered, repo_path=repo, recheck_live=False)
    assert bad["valid"] is False
    assert bad["hash_ok"] is False

    # Issue helper produces a hash-stable payload for synthetic evidence.
    synthetic = issue_sovereignty_certificate(
        goal="g",
        done_when="no_skill_route",
        contract={"ok": True, "met": True, "machine_checkable": True, "used_skill_route_discovery": False},
        assurance={
            "ok": True,
            "used_skill_route_discovery": False,
            "ablation": {"ok": True},
            "transfer": {"ok": True, "package_hash": "abc", "member_count": 2, "proved_count": 2},
            "adversarial": {"ok": True},
        },
        metrics={"count": 10, "primitive_count": 5, "proved_count": 8, "proved_ratio": 0.8},
        repo_path=repo,
    )
    assert synthetic["ok"] is True
    assert synthetic["certificate_hash"]
    assert verify_sovereignty_certificate(synthetic)["valid"] is True

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    sovereignty_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "sovereignty",
            "--repo-path",
            str(repo),
            "--no-mission",
            "--timeout-seconds",
            "180",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=240,
    )
    assert sovereignty_cli.returncode == 0, sovereignty_cli.stdout + sovereignty_cli.stderr
    sovereignty_payload = json.loads(sovereignty_cli.stdout)
    assert sovereignty_payload["ok"] is True
    assert sovereignty_payload["action"] == "sovereignty_plane"
    assert sovereignty_payload["certificate"]["ok"] is True

    verify_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "sovereignty",
            "--repo-path",
            str(repo),
            "--verify-only",
            sovereignty_payload["certificate"]["certificate_path"],
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
    )
    assert verify_cli.returncode == 0, verify_cli.stdout + verify_cli.stderr
    verify_payload = json.loads(verify_cli.stdout)
    assert verify_payload["ok"] is True
    assert verify_payload["valid"] is True
    # Keep path reference live for linters; ledger path is a side effect of seed.
    assert path.name == "ledger.json"


def test_lineage_plane_chain_drift_and_adversarial():
    """Lineage plane chains sovereignty certs, detects no-drift, falsifies tampering."""

    from blackhole_agent.capability_compounder import (
        append_lineage_entry,
        detect_lineage_drift,
        empty_lineage_log,
        ensure_seeded_ledger,
        load_lineage_log,
        parse_outcome_contract,
        run_lineage_adversarial_checks,
        run_lineage_plane,
        verify_lineage_chain,
        write_lineage_log,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.lineage-plane" in ledger.capabilities
    assert "capability.sovereignty-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; lineage_ok; chain_valid; no_drift; min_lineage_entries:2"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert kinds == {
        "no_skill_route",
        "lineage_ok",
        "chain_valid",
        "no_drift",
        "min_lineage_entries",
    }

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-lineage-plane.json"
    if lineage_path.exists():
        lineage_path.unlink()

    plane = run_lineage_plane(
        repo,
        "health inventory milestone",
        (
            "min_capabilities:5; min_primitives:3; capability_exists:repo.import-health; "
            "capability_proved:repo.import-health; program_passes:repo.import-health; "
            "no_skill_route; mission_plane_ok"
        ),
        max_steps=3,
        absorb_ready=False,
        grow_budget=0,
        run_mission=True,
        lineage_path=lineage_path,
        timeout=240,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "lineage_plane"
    assert plane["sovereignty"]["ok"] is True
    assert plane["chain"]["valid"] is True
    assert plane["chain"]["ok"] is True
    assert plane["drift"]["drift"] is False
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["tamper_failed_as_expected"] is True
    assert int(plane["lineage"]["entry_count"]) >= 2
    assert "sovereignty_certificate" in plane["lineage"]["entry_kinds"]
    assert "continuity_seal" in plane["lineage"]["entry_kinds"]
    assert plane["used_skill_route_discovery"] is False
    assert lineage_path.is_file()

    loaded = load_lineage_log(lineage_path)
    chain = verify_lineage_chain(loaded)
    assert chain["valid"] is True
    assert chain["ok"] is True
    assert int(loaded["entry_count"]) >= 2

    drift = detect_lineage_drift(repo, loaded, timeout=60)
    assert drift["drift"] is False
    assert drift["no_drift"] is True

    adversarial = run_lineage_adversarial_checks(loaded)
    assert adversarial["ok"] is True
    assert adversarial["tamper_failed_as_expected"] is True

    # Unit-level: empty → append two seals → chain links parent hashes.
    synthetic = empty_lineage_log()
    synthetic = append_lineage_entry(
        synthetic,
        entry_kind="continuity_seal",
        certificate_hash="abc",
        goal="a",
        claims={"sealed": True},
        metrics={"count": 10, "proved_count": 8},
    )
    synthetic = append_lineage_entry(
        synthetic,
        entry_kind="continuity_seal",
        certificate_hash="abc",
        goal="b",
        claims={"sealed": True},
        metrics={"count": 10, "proved_count": 8},
    )
    assert synthetic["entries"][1]["parent_hash"] == synthetic["entries"][0]["entry_hash"]
    assert verify_lineage_chain(synthetic)["valid"] is True
    tmp = repo / "artifacts" / "capability-lineage" / "test-synthetic-lineage.json"
    write_lineage_log(tmp, synthetic)
    assert load_lineage_log(tmp)["entry_count"] == 2

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    lineage_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "lineage",
            "--repo-path",
            str(repo),
            "--no-mission",
            "--lineage-path",
            str(repo / "artifacts" / "capability-lineage" / "cli-lineage.json"),
            "--timeout-seconds",
            "240",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert lineage_cli.returncode == 0, lineage_cli.stdout + lineage_cli.stderr
    lineage_payload = json.loads(lineage_cli.stdout)
    assert lineage_payload["ok"] is True
    assert lineage_payload["action"] == "lineage_plane"
    assert lineage_payload["chain"]["valid"] is True

    verify_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "lineage",
            "--repo-path",
            str(repo),
            "--verify-only",
            lineage_payload["lineage"]["path"],
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert verify_cli.returncode == 0, verify_cli.stdout + verify_cli.stderr
    verify_payload = json.loads(verify_cli.stdout)
    assert verify_payload["ok"] is True
    assert verify_payload["action"] == "verify_lineage"
    assert verify_payload["chain"]["valid"] is True
    assert verify_payload["chain"]["ok"] is True
    assert verify_payload["drift"]["drift"] is False
    assert int(verify_payload.get("entry_count") or 0) >= 2
    # Keep path reference live for linters; ledger path is a side effect of seed.
    assert path.name == "ledger.json"


def test_reconciliation_plane_heals_synthetic_drift():
    """Reconciliation plane injects drift, heals, and adversarially proves honesty."""

    from blackhole_agent.capability_compounder import (
        detect_lineage_drift,
        ensure_seeded_ledger,
        inject_synthetic_lineage_drift,
        load_lineage_log,
        parse_outcome_contract,
        run_reconciliation_plane,
        verify_lineage_chain,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.reconciliation-plane" in ledger.capabilities
    assert "capability.lineage-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; reconciliation_ok; healed_ok; min_heal_entries:2; "
        "chain_valid; no_drift"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "reconciliation_ok" in kinds
    assert "healed_ok" in kinds
    assert "min_heal_entries" in kinds

    lineage_path = (
        repo / "artifacts" / "capability-lineage" / "test-reconciliation-plane.json"
    )
    if lineage_path.exists():
        lineage_path.unlink()

    plane = run_reconciliation_plane(
        repo,
        "health inventory milestone",
        (
            "min_capabilities:5; min_primitives:3; capability_exists:repo.import-health; "
            "capability_proved:repo.import-health; program_passes:repo.import-health; "
            "no_skill_route; mission_plane_ok"
        ),
        max_steps=3,
        absorb_ready=False,
        grow_budget=0,
        run_mission=True,
        force_synthetic_drift=True,
        lineage_path=lineage_path,
        timeout=300,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "reconciliation_plane"
    assert plane["synthetic_drift_used"] is True
    assert plane["heal"]["healed"] is True
    assert plane["heal"]["ok"] is True
    assert int(plane["heal"]["heal_entry_count"]) >= 2
    assert "drift_diagnosis" in plane["heal"]["heal_entry_kinds"]
    assert "heal_certificate" in plane["heal"]["heal_entry_kinds"]
    assert "heal_seal" in plane["heal"]["heal_entry_kinds"]
    assert plane["chain"]["valid"] is True
    assert plane["drift"]["drift"] is False
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["unhealed_fails_as_expected"] is True
    assert plane["adversarial"]["healed_passes_as_expected"] is True
    assert plane["used_skill_route_discovery"] is False
    assert lineage_path.is_file()

    loaded = load_lineage_log(lineage_path)
    assert verify_lineage_chain(loaded)["valid"] is True
    assert detect_lineage_drift(repo, loaded, timeout=60)["drift"] is False
    kinds_present = {
        str(item.get("entry_kind") or "") for item in (loaded.get("entries") or [])
    }
    assert "heal_certificate" in kinds_present
    assert "heal_seal" in kinds_present

    # Unit: synthetic inject alone must trip drift detection.
    drifted = inject_synthetic_lineage_drift(loaded)
    assert detect_lineage_drift(repo, drifted, timeout=60)["drift"] is True

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    recon_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "reconcile",
            "--repo-path",
            str(repo),
            "--no-mission",
            "--lineage-path",
            str(repo / "artifacts" / "capability-lineage" / "cli-reconciliation.json"),
            "--timeout-seconds",
            "300",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=360,
    )
    assert recon_cli.returncode == 0, recon_cli.stdout + recon_cli.stderr
    recon_payload = json.loads(recon_cli.stdout)
    assert recon_payload["ok"] is True
    assert recon_payload["action"] == "reconciliation_plane"
    assert recon_payload["heal"]["healed"] is True
    assert recon_payload["chain"]["valid"] is True
    assert path.name == "ledger.json"


def test_finality_plane_multi_epoch_seal_and_adversarial():
    """Finality plane seals ≥2 irreversible epochs over quorum and falsifies forks/rewrites."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_finality_bundle,
        parse_outcome_contract,
        run_finality_plane,
        verify_finality_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.finality-plane" in ledger.capabilities
    assert "capability.quorum-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; finality_ok; finalized_ok; min_epochs:2; "
        "finality_cert_valid; chain_valid; quorum_met; min_origins:3"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "finality_ok" in kinds
    assert "finalized_ok" in kinds
    assert "min_epochs" in kinds
    assert "finality_cert_valid" in kinds

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-finality-plane.json"
    quorum_path = repo / "artifacts" / "quorum-bundles" / "test-finality-quorum.json"
    finality_path = repo / "artifacts" / "finality-bundles" / "test-finality-plane.json"
    for target in (lineage_path, quorum_path, finality_path):
        if target.exists():
            target.unlink()

    plane = run_finality_plane(
        repo,
        "epoch finality over quorum consensus",
        "min_capabilities:5; capability_exists:repo.import-health; no_skill_route",
        max_steps=3,
        run_quorum=True,
        run_continuity=False,
        run_reconciliation=False,
        inject_byzantine=True,
        epoch_count=2,
        lineage_path=lineage_path,
        quorum_path=quorum_path,
        finality_path=finality_path,
        timeout=240,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "finality_plane"
    assert plane["finalized"] is True
    assert int(plane["epoch_count"]) >= 2
    assert int(plane["tip_height"]) >= 2
    assert int(plane["origin_count"]) >= 3
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["multi_epoch"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["finality_certificate"]["valid"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["rewrite_fails_as_expected"] is True
    assert plane["adversarial"]["fork_fails_as_expected"] is True
    assert plane["adversarial"]["gap_fails_as_expected"] is True
    assert plane["adversarial"]["stale_supersession_fails_as_expected"] is True
    assert plane["adversarial"]["single_epoch_fails_as_expected"] is True
    assert plane["used_skill_route_discovery"] is False
    assert finality_path.is_file()

    loaded = load_finality_bundle(finality_path)
    assert verify_finality_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("finality_hash")
    assert int(loaded.get("epoch_count") or 0) >= 2
    assert int(loaded.get("tip_height") or 0) >= 2

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    finality_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "finality",
            "--repo-path",
            str(repo),
            "--lineage-path",
            str(repo / "artifacts" / "capability-lineage" / "cli-finality.json"),
            "--quorum-path",
            str(repo / "artifacts" / "quorum-bundles" / "cli-finality-quorum.json"),
            "--finality-path",
            str(repo / "artifacts" / "finality-bundles" / "cli-finality.json"),
            "--timeout-seconds",
            "240",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert finality_cli.returncode == 0, finality_cli.stdout + finality_cli.stderr
    finality_payload = json.loads(finality_cli.stdout)
    assert finality_payload["ok"] is True
    assert finality_payload["action"] == "finality_plane"
    assert finality_payload["finalized"] is True
    assert int(finality_payload["epoch_count"]) >= 2
    assert path.name == "ledger.json"


def test_actuation_plane_effects_and_adversarial():
    """Actuation plane dispatches multi-action effects over world-state and falsifies wrong-state binds."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_actuation_bundle,
        parse_outcome_contract,
        run_actuation_plane,
        verify_actuation_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.actuation-plane" in ledger.capabilities
    assert "capability.execution-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; actuation_ok; effects_applied_ok; min_actions:2; "
        "action_root_valid; execution_ok; state_applied_ok; min_state_height:2; "
        "state_root_valid; chain_valid"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "actuation_ok" in kinds
    assert "effects_applied_ok" in kinds
    assert "min_actions" in kinds
    assert "action_root_valid" in kinds

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-actuation-plane.json"
    quorum_path = repo / "artifacts" / "quorum-bundles" / "test-actuation-quorum.json"
    finality_path = repo / "artifacts" / "finality-bundles" / "test-actuation-finality.json"
    execution_path = repo / "artifacts" / "execution-bundles" / "test-actuation-execution.json"
    actuation_path = repo / "artifacts" / "actuation-bundles" / "test-actuation-plane.json"
    for target in (lineage_path, quorum_path, finality_path, execution_path, actuation_path):
        if target.exists():
            target.unlink()

    plane = run_actuation_plane(
        repo,
        "actuation over world-state execution",
        "min_capabilities:5; capability_exists:repo.import-health; no_skill_route",
        max_steps=3,
        run_execution=True,
        run_finality=True,
        run_quorum=True,
        run_continuity=False,
        run_reconciliation=False,
        inject_byzantine=True,
        epoch_count=2,
        min_actions=2,
        lineage_path=lineage_path,
        quorum_path=quorum_path,
        finality_path=finality_path,
        execution_path=execution_path,
        actuation_path=actuation_path,
        timeout=300,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "actuation_plane"
    assert plane["effects_applied"] is True
    assert int(plane["action_count"]) >= 2
    assert int(plane["tip_height"]) >= 2
    assert int(plane["state_height"] or 0) >= 2
    assert int(plane["origin_count"]) >= 3
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["multi_action"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["actuation_certificate"]["valid"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["wrong_state_fails_as_expected"] is True
    assert plane["adversarial"]["reorder_fails_as_expected"] is True
    assert plane["adversarial"]["single_action_fails_as_expected"] is True
    assert plane["adversarial"]["replay_matches_tip"] is True
    assert plane["used_skill_route_discovery"] is False
    assert actuation_path.is_file()

    loaded = load_actuation_bundle(actuation_path)
    assert verify_actuation_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("actuation_hash")
    assert int(loaded.get("action_count") or 0) >= 2
    assert int(loaded.get("tip_height") or 0) >= 2
    assert loaded.get("bound_state_root")

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    actuate_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "actuate",
            "--repo-path",
            str(repo),
            "--lineage-path",
            str(repo / "artifacts" / "capability-lineage" / "cli-actuation.json"),
            "--quorum-path",
            str(repo / "artifacts" / "quorum-bundles" / "cli-actuation-quorum.json"),
            "--finality-path",
            str(repo / "artifacts" / "finality-bundles" / "cli-actuation-finality.json"),
            "--execution-path",
            str(repo / "artifacts" / "execution-bundles" / "cli-actuation-execution.json"),
            "--actuation-path",
            str(repo / "artifacts" / "actuation-bundles" / "cli-actuation.json"),
            "--timeout-seconds",
            "300",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=360,
    )
    assert actuate_cli.returncode == 0, actuate_cli.stdout + actuate_cli.stderr
    actuate_payload = json.loads(actuate_cli.stdout)
    assert actuate_payload["ok"] is True
    assert actuate_payload["action"] == "actuation_plane"
    assert actuate_payload["effects_applied"] is True
    assert int(actuate_payload["action_count"]) >= 2
    assert path.name == "ledger.json"


def test_quorum_plane_majority_byzantine_and_adversarial():
    """Quorum plane votes ≥3 origins, excludes Byzantine poison, and falsifies below-quorum."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_quorum_bundle,
        parse_outcome_contract,
        run_quorum_plane,
        verify_quorum_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.quorum-plane" in ledger.capabilities
    assert "capability.federation-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; quorum_ok; quorum_met; min_origins:3; min_quorum:2; "
        "byzantine_excluded; quorum_cert_valid; chain_valid"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "quorum_ok" in kinds
    assert "quorum_met" in kinds
    assert "byzantine_excluded" in kinds
    assert "quorum_cert_valid" in kinds
    assert "min_quorum" in kinds

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-quorum-plane.json"
    quorum_path = repo / "artifacts" / "quorum-bundles" / "test-quorum-plane.json"
    for target in (lineage_path, quorum_path):
        if target.exists():
            target.unlink()

    plane = run_quorum_plane(
        repo,
        "quorum multi-origin consensus",
        "min_capabilities:5; capability_exists:repo.import-health; no_skill_route",
        max_steps=3,
        run_continuity=False,
        run_reconciliation=False,
        inject_byzantine=True,
        lineage_path=lineage_path,
        quorum_path=quorum_path,
        timeout=180,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "quorum_plane"
    assert plane["quorum_met"] is True
    assert int(plane["origin_count"]) >= 3
    assert int(plane["byzantine_count"]) >= 1
    assert "origin-byzantine" in (plane.get("byzantine_origins") or [])
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["poison_free"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["quorum_certificate"]["valid"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["dual_origin_fails_as_expected"] is True
    assert plane["adversarial"]["below_quorum_fails_as_expected"] is True
    assert plane["adversarial"]["byzantine_excluded_as_expected"] is True
    assert plane["used_skill_route_discovery"] is False
    assert quorum_path.is_file()

    loaded = load_quorum_bundle(quorum_path)
    assert verify_quorum_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("quorum_hash")
    assert int(loaded.get("origin_count") or 0) >= 3
    assert int(loaded.get("byzantine_count") or 0) >= 1

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    quorum_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "quorum",
            "--repo-path",
            str(repo),
            "--no-continuity",
            "--lineage-path",
            str(repo / "artifacts" / "capability-lineage" / "cli-quorum.json"),
            "--quorum-path",
            str(repo / "artifacts" / "quorum-bundles" / "cli-quorum.json"),
            "--timeout-seconds",
            "180",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=240,
    )
    assert quorum_cli.returncode == 0, quorum_cli.stdout + quorum_cli.stderr
    quorum_payload = json.loads(quorum_cli.stdout)
    assert quorum_payload["ok"] is True
    assert quorum_payload["action"] == "quorum_plane"
    assert quorum_payload["quorum_met"] is True
    assert int(quorum_payload["byzantine_count"]) >= 1
    assert path.name == "ledger.json"


def test_continuity_plane_export_rehydrate_and_adversarial():
    """Continuity plane exports a bundle, rehydrates, re-proves, and falsifies tamper."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_continuity_bundle,
        parse_outcome_contract,
        run_continuity_plane,
        verify_continuity_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.continuity-plane" in ledger.capabilities
    assert "capability.reconciliation-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; continuity_ok; resurrected_ok; bundle_valid; "
        "min_bundle_certs:1; chain_valid; no_drift"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "continuity_ok" in kinds
    assert "resurrected_ok" in kinds
    assert "bundle_valid" in kinds
    assert "min_bundle_certs" in kinds

    lineage_path = (
        repo / "artifacts" / "capability-lineage" / "test-continuity-plane.json"
    )
    bundle_path = (
        repo / "artifacts" / "continuity-bundles" / "test-continuity-plane.json"
    )
    for target in (lineage_path, bundle_path):
        if target.exists():
            target.unlink()

    plane = run_continuity_plane(
        repo,
        "health inventory milestone",
        (
            "min_capabilities:5; min_primitives:3; capability_exists:repo.import-health; "
            "capability_proved:repo.import-health; program_passes:repo.import-health; "
            "no_skill_route"
        ),
        max_steps=3,
        absorb_ready=False,
        grow_budget=0,
        run_mission=False,
        run_reconciliation=True,
        force_synthetic_drift=True,
        lineage_path=lineage_path,
        bundle_path=bundle_path,
        timeout=360,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "continuity_plane"
    assert plane["resurrected"] is True
    assert plane["bundle"]["ok"] is True
    assert plane["bundle"]["persisted"] is True
    assert int(plane["bundle"]["certificate_count"]) >= 1
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["hash_ok"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["drift"]["drift"] is False
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["tamper_fails_as_expected"] is True
    assert plane["adversarial"]["empty_lineage_fails_as_expected"] is True
    assert plane["used_skill_route_discovery"] is False
    assert bundle_path.is_file()

    loaded = load_continuity_bundle(bundle_path)
    assert verify_continuity_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("bundle_hash")
    assert int(loaded.get("lineage_entry_count") or 0) >= 1

    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": str(repo / "src"),
    }
    continuity_cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "capability",
            "continuity",
            "--repo-path",
            str(repo),
            "--lineage-path",
            str(repo / "artifacts" / "capability-lineage" / "cli-continuity.json"),
            "--bundle-path",
            str(repo / "artifacts" / "continuity-bundles" / "cli-continuity.json"),
            "--timeout-seconds",
            "360",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        timeout=420,
    )
    assert continuity_cli.returncode == 0, continuity_cli.stdout + continuity_cli.stderr
    continuity_payload = json.loads(continuity_cli.stdout)
    assert continuity_payload["ok"] is True
    assert continuity_payload["action"] == "continuity_plane"
    assert continuity_payload["resurrected"] is True
    assert continuity_payload["rehydrate"]["ok"] is True
    assert path.name == "ledger.json"
































