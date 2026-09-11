from pathlib import Path

from blackhole_agent.loop_reboot_restore import LOOP_REBOOT_RESTORE_GOAL, LOOP_REBOOT_RESTORE_ID
from blackhole_agent.mission_selection import assess_mission_selection
from blackhole_agent.orphan_loop_reap import (
    ORPHAN_LOOP_REAP_DONE_WHEN,
    ORPHAN_LOOP_REAP_GOAL,
    ORPHAN_LOOP_REAP_ID,
    builtin_orphan_loop_reap_proof,
)


def test_builtin_proof_reaps_dead_owner_and_spares_live_owner():
    report = builtin_orphan_loop_reap_proof()
    assert report["ok"] is True
    assert report["action"] == "orphan_loop_reap"
    assert report["used_skill_route_discovery"] is False
    assert report["passed_count"] == report["check_count"]
    assert report["checks"]["dead_owner_effective_orphaned"]
    assert report["checks"]["reap_clears_running_mission"]
    assert report["checks"]["live_owner_untouched"]
    assert report["checks"]["catalog_names_reboot_restore"]


def test_selection_accepts_orphan_reap_and_next_family(tmp_path: Path):
    gate = assess_mission_selection(
        tmp_path,
        ORPHAN_LOOP_REAP_GOAL,
        ORPHAN_LOOP_REAP_DONE_WHEN,
        history=[],
    )
    assert gate.accepted is True
    assert ORPHAN_LOOP_REAP_ID not in gate.capability_family
    nxt = assess_mission_selection(
        tmp_path,
        LOOP_REBOOT_RESTORE_GOAL,
        "A reaped orphaned continuous-loop state is restored by a startup helper.",
        history=[],
    )
    assert nxt.accepted is True
    assert LOOP_REBOOT_RESTORE_ID not in nxt.capability_family
