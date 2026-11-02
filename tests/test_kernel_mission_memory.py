from pathlib import Path

from blackhole_agent.capability_compounder import default_ledger_path, load_ledger
from blackhole_agent.kernel_class_closure import CLASS_CLOSURE_REQUIREMENTS, KERNEL_TURN_FAILED
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.kernel_mission_memory import (
    HARVESTED_ERROR_TURN,
    MISSION_MEMORY_DONE_WHEN,
    MISSION_MEMORY_GOAL,
    MISSION_MEMORY_ID,
    builtin_kernel_mission_memory_proof,
    events_from_turn,
    harvest_state_surface_classes,
)
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
from blackhole_agent.pattern_register import classify_unbound_turn


def test_repeated_remember_does_not_inflate_count(tmp_path: Path) -> None:
    from blackhole_agent.kernel_mission_memory import load_mission_memory, remember_turn_record

    turn = dict(HARVESTED_ERROR_TURN)
    remember_turn_record(tmp_path, turn, source_mission_id="")
    remember_turn_record(tmp_path, turn, source_mission_id="mission-a")
    row = load_mission_memory(tmp_path)["classes"]["kernel_turn_failed"]
    assert row["count"] == 1
    later = dict(turn)
    later["iteration"] = 14
    later["finished_at"] = "2026-08-16T06:10:00Z"
    later["summary"] = "turn 14 failed before a structured decision"
    remember_turn_record(tmp_path, later, source_mission_id="mission-a")
    assert load_mission_memory(tmp_path)["classes"]["kernel_turn_failed"]["count"] == 2


def test_goal_binds_mission_memory_plane() -> None:
    assert leftover_marker_ids(MISSION_MEMORY_GOAL) == (MISSION_MEMORY_ID,)
    assert MISSION_MEMORY_ID in LOCAL_DENYLIST
    assert any(item.get("class_id") == KERNEL_TURN_FAILED for item in classify_unbound_turn(HARVESTED_ERROR_TURN))
    assert KERNEL_TURN_FAILED not in harvest_state_surface_classes(
        {
            "status": "complete",
            "next_step": "None. Mission complete.",
            "last_error": "",
            "recent_turns": [],
        }
    )
    assert any(item.get("class_id") == KERNEL_TURN_FAILED for item in events_from_turn(HARVESTED_ERROR_TURN))
    assert CLASS_CLOSURE_REQUIREMENTS[KERNEL_TURN_FAILED]


def test_builtin_proof_recalls_turn_only_class_from_durable_memory() -> None:
    report = builtin_kernel_mission_memory_proof()
    assert report["ok"] is True, report.get("checks")
    assert report["action"] == "kernel_mission_memory"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == len(report["checks"])
    assert report["checks"]["state_surface_misses_turn_only_class"]
    assert report["checks"]["harvest_recalls_turn_only_class"]
    assert report["checks"]["harvest_without_mission_dir_still_recalls"]
    assert report["checks"]["genesis_bind_replays_instead_of_inventing"]
    assert report["checks"]["closed_class_does_not_replay"]
    assert report["mission_goal"] == MISSION_MEMORY_GOAL
    assert report["done_when"] == MISSION_MEMORY_DONE_WHEN
    ledger = load_ledger(default_ledger_path(Path(".")))
    capability = ledger.capabilities[MISSION_MEMORY_ID]
    assert capability.last_proof_exit_code == 0
    assert "memory" in capability.tags
    assert "genesis" in capability.tags
