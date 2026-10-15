"""Outcome probe: a repaired paperwork class leaves genesis fuel.

Durable mission memory can still store paperwork_milestone after intake
decline shipped. Genesis fuel must omit that class and keep an unrepaired
class stored beside it. The same probe prints passed=false on a controller
that still offers the historical class.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from blackhole_agent.experience_fuel import render_experience_for_genesis
from blackhole_agent.kernel_mission_memory import recall_open_classes, save_mission_memory


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperwork-fuel-") as tmp:
        root = Path(tmp)
        save_mission_memory(
            root,
            {
                "classes": {
                    "paperwork_milestone": {
                        "class_id": "paperwork_milestone",
                        "count": 170,
                        "evidence": (
                            "no repository change exists since the previous milestone; "
                            "changes are limited to docs, tests, artifacts, or controller state"
                        ),
                        "summary": "turn 2 milestone rejected",
                        "source": "unbound",
                    },
                    "health_check_failed": {
                        "class_id": "health_check_failed",
                        "count": 1,
                        "evidence": "health check still failing",
                        "summary": "health check failed",
                        "source": "unbound",
                    },
                }
            },
        )
        recalled = [item.class_id for item in recall_open_classes(root)]
        rendered = render_experience_for_genesis(root)
    observed = {
        "recalled": recalled,
        "rendered_mentions_paperwork": "paperwork_milestone" in rendered,
        "rendered_mentions_unrepaired": "health_check_failed" in rendered,
    }
    passed = (
        "paperwork_milestone" not in recalled
        and "health_check_failed" in recalled
        and observed["rendered_mentions_paperwork"] is False
        and observed["rendered_mentions_unrepaired"] is True
    )
    print(json.dumps({"passed": bool(passed), "observed": observed}))


if __name__ == "__main__":
    main()
