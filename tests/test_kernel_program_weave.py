from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_genesis_bind import (
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_ID,
    PROGRAM_FABRIC_GOAL,
    PROGRAM_FABRIC_ID,
    PROGRAM_WEAVE_DONE_WHEN,
    PROGRAM_WEAVE_GOAL,
    PROGRAM_WEAVE_ID,
)
from blackhole_agent.kernel_genesis_diversify import GENESIS_DIVERSIFY_GOAL
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_program_fabric import (
    PROGRAM_FABRIC_UNIT_PREFIX,
    fabric_id_from_members,
)
from blackhole_agent.kernel_program_lattice import PROGRAM_LATTICE_MEMBER_SEP, PROGRAM_LATTICE_UNIT_PREFIX
from blackhole_agent.kernel_program_tower import PROGRAM_TOWER_MEMBER_SEP
from blackhole_agent.kernel_program_weave import (
    PROGRAM_WEAVE_UNIT_PREFIX,
    builtin_kernel_program_weave_proof,
    is_program_weave_id,
    weave_id_from_members,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.mission_selection import semantic_signature, semantic_similarity
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_program_weave_units_are_not_cheap():
    first_lattice = (
        f"{PROGRAM_LATTICE_UNIT_PREFIX}-1-2__2-3___2-3__3-4"
        f"{PROGRAM_TOWER_MEMBER_SEP}2-3__3-4___3-4__4-5"
        f"{PROGRAM_LATTICE_MEMBER_SEP}2-3__3-4___3-4__4-5"
        f"{PROGRAM_TOWER_MEMBER_SEP}3-4__4-5___4-5__5-6"
    )
    second_lattice = (
        f"{PROGRAM_LATTICE_UNIT_PREFIX}-2-3__3-4___3-4__4-5"
        f"{PROGRAM_TOWER_MEMBER_SEP}3-4__4-5___4-5__5-6"
        f"{PROGRAM_LATTICE_MEMBER_SEP}3-4__4-5___4-5__5-6"
        f"{PROGRAM_TOWER_MEMBER_SEP}4-5__5-6___5-6__6-7"
    )
    third_lattice = (
        f"{PROGRAM_LATTICE_UNIT_PREFIX}-3-4__4-5___4-5__5-6"
        f"{PROGRAM_TOWER_MEMBER_SEP}4-5__5-6___5-6__6-7"
        f"{PROGRAM_LATTICE_MEMBER_SEP}4-5__5-6___5-6__6-7"
        f"{PROGRAM_TOWER_MEMBER_SEP}5-6__6-7___6-7__7-8"
    )
    first_fabric = fabric_id_from_members((first_lattice, second_lattice))
    second_fabric = fabric_id_from_members((second_lattice, third_lattice))
    first = weave_id_from_members((first_fabric, second_fabric))
    assert first.startswith(f"{PROGRAM_WEAVE_UNIT_PREFIX}-")
    assert len(first) <= 128
    assert is_program_weave_id(first) is True
    assert is_cheap_inventory_id(first) is False
    assert is_cheap_inventory_id(PROGRAM_WEAVE_ID) is False
    assert is_program_weave_id(PROGRAM_WEAVE_ID) is False
    assert first_fabric.startswith(f"{PROGRAM_FABRIC_UNIT_PREFIX}-")


def test_weave_goal_is_not_a_fabric_near_duplicate():
    similarity = semantic_similarity(
        semantic_signature(PROGRAM_FABRIC_GOAL),
        semantic_signature(PROGRAM_WEAVE_GOAL),
    )
    assert similarity < 0.82
    diversity_similarity = semantic_similarity(
        semantic_signature(PROGRAM_WEAVE_GOAL),
        semantic_signature(GENESIS_DIVERSIFY_GOAL),
    )
    assert diversity_similarity < 0.82
    assert PROGRAM_WEAVE_ID in leftover_marker_ids(PROGRAM_WEAVE_GOAL)
    assert PROGRAM_FABRIC_ID not in leftover_marker_ids(PROGRAM_WEAVE_GOAL)
    assert PROGRAM_WEAVE_ID not in leftover_marker_ids(PROGRAM_FABRIC_GOAL)


def test_hydrate_consumed_campaign_binds_weave_after_fabric(tmp_path: Path):
    save_campaign(
        tmp_path,
        LocalCampaign(
            mission_id="prior",
            goal="Resume remaining durable campaign work after class_closed left genesis unscoped: capability.ledger-attestation",
            done_when="program_passes:capability.ledger-attestation;no_skill_route",
            bound_from="class_closed",
            tick_count=3,
            last_contract_met=True,
            consumed_at="2026-08-29T08:32:38Z",
            last_summary="Local program-fabric minted and proved capability.program-fabric-deadbeef in-process so recovered kernels keep compounding weaves instead of probing cheap inventory.",
        ),
    )
    state = UnboundMission(
        schema_version=1,
        mission_id="mission-1",
        created_at="2026-08-29T00:00:00Z",
        updated_at="2026-08-29T00:00:00Z",
        repo_path=str(tmp_path),
        workspace_path=str(tmp_path),
        branch="unbound/test",
        target_branch="main",
        goal="",
        done_when="",
        stage="genesis",
        base_head="abc",
        last_milestone_head="abc",
    )
    prompt = build_turn_prompt(
        state,
        {"head": "abc", "status": "", "diff_stat": "", "recent_commits": "abc seed"},
        state_path=tmp_path / "state.json",
    )
    assert "Mission genesis is still open" not in prompt
    assert (
        PROGRAM_WEAVE_GOAL in prompt
        or PROGRAM_FABRIC_GOAL in prompt
        or KERNEL_GENESIS_BIND_ID in (state.done_when or prompt)
    )
    assert state.stage == "execution"


def test_builtin_proof_raises_program_weave():
    report = builtin_kernel_program_weave_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_program_weave"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["promote_registers_unique_weave_coverage"]
    assert report["checks"]["tick_after_saturated_fabrics_runs_weave"]
    assert report["checks"]["proved_weave_skips_to_diversity"]
    assert PROGRAM_WEAVE_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert PROGRAM_WEAVE_ID in leftover_marker_ids(PROGRAM_WEAVE_GOAL)
    assert PROGRAM_WEAVE_DONE_WHEN in report["done_when"]
    assert GENESIS_DIVERSIFY_GOAL
    assert LOCAL_KERNEL == "local"
    assert report["checks"]["hydrate_fills_program_weave"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["preserves_operator_bind"]
    assert report["checks"]["novelty_ranks_pair_first"]
    assert report["checks"]["needed_on_bound_weave_when_saturated"]
