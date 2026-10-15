"""Genesis fuel drops a paperwork class once intake decline is the closer."""

from __future__ import annotations

from blackhole_agent.kernel_class_closure import class_is_closed
from blackhole_agent.kernel_mission_memory import recall_open_classes, save_mission_memory


def test_historical_paperwork_class_leaves_genesis_fuel(tmp_path):
    save_mission_memory(
        tmp_path,
        {
            "classes": {
                "paperwork_milestone": {
                    "class_id": "paperwork_milestone",
                    "count": 2,
                    "evidence": "changes are limited to docs, tests, artifacts, or controller state",
                    "summary": "turn 2 milestone rejected",
                },
                "health_check_failed": {
                    "class_id": "health_check_failed",
                    "count": 1,
                    "evidence": "still open",
                    "summary": "health check failed",
                },
            }
        },
    )
    recalled = [item.class_id for item in recall_open_classes(tmp_path)]
    assert class_is_closed("paperwork_milestone", tmp_path) is True
    assert class_is_closed("health_check_failed", tmp_path) is False
    assert "paperwork_milestone" not in recalled
    assert "health_check_failed" in recalled
