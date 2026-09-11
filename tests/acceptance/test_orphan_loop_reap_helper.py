"""Acceptance probe: dead owner is orphaned; live owner is not rewritten.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both
met and unmet outcomes so the controller can replay the same probe on
baseline and candidate source trees.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

observed: dict[str, object] = {"family": "orphan-loop-reap"}
passed = False

try:
    from blackhole_agent.orphan_loop_reap import annotate_loop_status, reap_orphaned_loop
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )
except Exception as error:  # pragma: no cover - baseline missing the helper
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    print(json.dumps({"passed": False, "observed": observed}, sort_keys=True))
    raise SystemExit(0)


def _seed(repo: Path, *, pid: int, status: str = "running_mission") -> Path:
    path = continuous_loop_state_path(repo)
    save_continuous_loop_state(
        path,
        {
            "loop_id": "acceptance-orphan",
            "status": status,
            "pid": pid,
            "current_mission_id": "unfinished-mission",
            "current_state_path": str(repo / "mission.json"),
            "lineage_ref": "proven-commit",
            "pending_publish_ref": "pending-commit",
            "next_wake_at": "2099-01-01T00:00:00Z",
            "last_error": "retained diagnostic",
        },
    )
    continuous_loop_lock_path(repo).write_text(f"{pid}\n", encoding="utf-8")
    return path


try:
    dead_pid = 1_000_009
    while pid_is_running(dead_pid):
        dead_pid += 2
    live_pid = os.getpid()

    with tempfile.TemporaryDirectory(prefix="accept-orphan-dead-") as tmp:
        repo = Path(tmp)
        (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
        mission_before = (repo / "mission.json").read_bytes()
        path = _seed(repo, pid=dead_pid)
        original = json.loads(path.read_text(encoding="utf-8"))
        durable_before = path.read_bytes()
        shown_read_only = annotate_loop_status(json.loads(durable_before))
        annotation_preserved = (
            shown_read_only.get("status") == "running_mission"
            and path.read_bytes() == durable_before
        )
        read_only_ok = (
            shown_read_only.get("effective_status") == "orphaned"
            and shown_read_only.get("pid_alive") is False
            and annotation_preserved
        )
        reaped = reap_orphaned_loop(repo)
        persisted = json.loads(path.read_text(encoding="utf-8"))
        dead_ok = (
            read_only_ok
            and reaped.get("status") == "orphaned"
            and reaped.get("effective_status") == "orphaned"
            and persisted.get("status") == "orphaned"
            and persisted.get("orphaned_from_status") == "running_mission"
            and persisted.get("pid") == dead_pid
            and persisted.get("current_mission_id") == original["current_mission_id"]
            and persisted.get("lineage_ref") == original["lineage_ref"]
            and persisted.get("pending_publish_ref") == original["pending_publish_ref"]
            and persisted.get("last_error") == original["last_error"]
            and persisted.get("next_wake_at") == ""
            and bool(persisted.get("reaped_at"))
            and not continuous_loop_lock_path(repo).exists()
            and (repo / "mission.json").read_bytes() == mission_before
        )

    with tempfile.TemporaryDirectory(prefix="accept-orphan-live-") as tmp:
        repo = Path(tmp)
        path = _seed(repo, pid=live_pid)
        before = path.read_bytes()
        shown = annotate_loop_status(json.loads(path.read_text(encoding="utf-8")))
        result = reap_orphaned_loop(repo)
        live_ok = (
            shown.get("effective_status") == "running_mission"
            and shown.get("pid_alive") is True
            and result.get("status") == "running_mission"
            and result.get("effective_status") == "running_mission"
            and path.read_bytes() == before
            and continuous_loop_lock_path(repo).read_text(encoding="utf-8") == f"{live_pid}\n"
        )

    observed.update(
        {
            "dead_pid": dead_pid,
            "live_pid": live_pid,
            "dead_owner_orphaned": dead_ok,
            "live_owner_untouched": live_ok,
            "annotation_preserved": annotation_preserved,
            "sentinel": "BH-ORPHAN-LOOP-REAP-OK" if dead_ok and live_ok else "",
            "error": "",
        }
    )
    passed = bool(dead_ok and live_ok)
except Exception as error:  # pragma: no cover - fixture or helper failure
    observed["error"] = type(error).__name__
    observed["detail"] = str(error)
    passed = False

print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
