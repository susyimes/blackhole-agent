from pathlib import Path

from blackhole_agent.kernel_class_closure import class_closure_ids
from blackhole_agent.kernel_consumed_growth import is_cheap_inventory_id
from blackhole_agent.kernel_genesis_bind import (
    GENESIS_SELECTION_BLOCKED,
    KERNEL_GENESIS_BIND_ID,
    PROGRAM_FABRIC_DONE_WHEN,
    PROGRAM_FABRIC_GOAL,
    PROGRAM_FABRIC_ID,
    PROGRAM_LATTICE_GOAL,
    PROGRAM_LATTICE_ID,
    PROGRAM_WEAVE_GOAL,
)
from blackhole_agent.kernel_health import LOCAL_KERNEL
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_program_fabric import (
    PROGRAM_FABRIC_UNIT_PREFIX,
    builtin_kernel_program_fabric_proof,
    fabric_id_from_members,
    is_program_fabric_id,
)
from blackhole_agent.kernel_program_lattice import PROGRAM_LATTICE_MEMBER_SEP, PROGRAM_LATTICE_UNIT_PREFIX
from blackhole_agent.kernel_program_tower import PROGRAM_TOWER_MEMBER_SEP
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.local_mission_sovereignty import LocalCampaign, save_campaign
from blackhole_agent.mission_selection import semantic_signature, semantic_similarity
from blackhole_agent.unbound import UnboundMission, build_turn_prompt


def test_program_fabric_units_are_not_cheap():
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
    first = fabric_id_from_members((first_lattice, second_lattice))
    assert first.startswith(f"{PROGRAM_FABRIC_UNIT_PREFIX}-")
    assert len(first) <= 128
    assert is_program_fabric_id(first) is True
    assert is_cheap_inventory_id(first) is False
    assert is_cheap_inventory_id(PROGRAM_FABRIC_ID) is False
    assert is_program_fabric_id(PROGRAM_FABRIC_ID) is False


def test_fabric_goal_is_not_a_lattice_near_duplicate():
    similarity = semantic_similarity(
        semantic_signature(PROGRAM_LATTICE_GOAL),
        semantic_signature(PROGRAM_FABRIC_GOAL),
    )
    assert similarity < 0.82
    weave_similarity = semantic_similarity(
        semantic_signature(PROGRAM_FABRIC_GOAL),
        semantic_signature(PROGRAM_WEAVE_GOAL),
    )
    assert weave_similarity < 0.82
    assert PROGRAM_FABRIC_ID in leftover_marker_ids(PROGRAM_FABRIC_GOAL)
    assert PROGRAM_LATTICE_ID not in leftover_marker_ids(PROGRAM_FABRIC_GOAL)
    assert PROGRAM_FABRIC_ID not in leftover_marker_ids(PROGRAM_LATTICE_GOAL)


def test_hydrate_consumed_campaign_binds_fabric_after_lattice(tmp_path: Path):
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
            last_summary="Local program-lattice minted and proved capability.program-lattice-1-2__2-3___2-3__3-4____2-3__3-4___3-4__4-5_____2-3__3-4___3-4__4-5____3-4__4-5___4-5__5-6 in-process so recovered kernels keep compounding fabrics instead of falling back to cheap inventory probes.",
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
        PROGRAM_FABRIC_GOAL in prompt
        or PROGRAM_LATTICE_GOAL in prompt
        or KERNEL_GENESIS_BIND_ID in (state.done_when or prompt)
    )
    assert state.stage == "execution"


def test_builtin_proof_promotes_program_fabric():
    report = builtin_kernel_program_fabric_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_program_fabric"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["promote_registers_unique_fabric_coverage"]
    assert report["checks"]["second_promote_expands_fabric_coverage"]
    assert report["checks"]["tick_after_saturated_lattices_runs_fabric"]
    assert report["checks"]["proved_fabric_skips_to_weave"]
    assert PROGRAM_FABRIC_ID in LOCAL_DENYLIST
    assert class_closure_ids(GENESIS_SELECTION_BLOCKED) == (KERNEL_GENESIS_BIND_ID,)
    assert PROGRAM_FABRIC_ID in leftover_marker_ids(PROGRAM_FABRIC_GOAL)
    assert PROGRAM_FABRIC_DONE_WHEN in report["done_when"]
    assert PROGRAM_WEAVE_GOAL
    assert LOCAL_KERNEL == "local"
    assert report["checks"]["hydrate_fills_program_fabric"]
    assert report["checks"]["unscoped_remaining_still_wins"]
    assert report["checks"]["preserves_operator_bind"]
    assert report["checks"]["novelty_ranks_pair_first"]
