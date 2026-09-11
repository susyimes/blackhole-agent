from pathlib import Path

from blackhole_agent.leftover_handoff_rebind import (
    LEFTOVER_HANDOFF_REBIND_DONE_WHEN,
    LEFTOVER_HANDOFF_REBIND_GOAL,
    LEFTOVER_HANDOFF_REBIND_ID,
    builtin_leftover_handoff_rebind_proof,
)
from blackhole_agent.mission_selection import assess_mission_selection
from blackhole_agent.orphan_loop_reap import ORPHAN_LOOP_REAP_GOAL


def test_builtin_proof_drops_consumed_leftover_and_binds_rebind():
    report = builtin_leftover_handoff_rebind_proof()
    assert report["ok"] is True
    assert report["action"] == "leftover_handoff_rebind"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["consumed_leftover_leaves_brief"]
    assert report["checks"]["open_leftover_stays_in_brief"]
    assert report["checks"]["empty_genesis_binds_rebind"]
    assert report["checks"]["catalog_handoff_markers_stay"]


def test_selection_accepts_rebind_and_rejects_handshake_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        LEFTOVER_HANDOFF_REBIND_GOAL,
        LEFTOVER_HANDOFF_REBIND_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert LEFTOVER_HANDOFF_REBIND_ID not in gate.capability_family
    orphan = assess_mission_selection(
        tmp_path,
        ORPHAN_LOOP_REAP_GOAL,
        "A durable loop whose owner pid is gone reports effective_status=orphaned.",
        history=[],
    )
    assert orphan.accepted is True
