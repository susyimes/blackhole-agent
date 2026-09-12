"""Observe restart reconciliation of a mission creation interrupted mid-checkout.

Builds a sandbox repository with a worktree-parent directory that has no
mission state (the shape a reboot during ``git worktree add`` leaves behind),
runs the loop-startup reconciliation twice, and reports whether a durable,
idempotent receipt names the abandoned worktree and branch without deleting
them or disturbing a registered mission.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=False
    )
    return (result.stdout or "").strip()


def main() -> dict:
    try:
        from blackhole_agent.loop_creation_reconcile import (
            INTERRUPTED_EVENT,
            orphan_inventory_path,
            reconcile_interrupted_creations,
        )
        from blackhole_agent.unbound import continuous_loop_events_path
    except ImportError as error:
        return {"passed": False, "observed": f"reconciliation absent: {error}"}

    with tempfile.TemporaryDirectory(prefix="accept-creation-reconcile-") as directory:
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Blackhole Acceptance")
        git(repo, "config", "user.email", "blackhole@example.invalid")
        (repo / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "seed")

        parent = root / "worktrees"
        parent.mkdir()

        # Orphan: a checkout interrupted before its mission state existed.
        orphan_id = "20260910T191600Z-deadbeef"
        orphan_branch = "unbound/autonomous-genesis-deadbeef"
        orphan_workspace = parent / orphan_id
        subprocess.run(
            ["git", "worktree", "add", "-b", orphan_branch, str(orphan_workspace), "main"],
            cwd=repo, check=True, capture_output=True, text=True,
        )

        # Registered mission: same parent, but with durable state.
        live_id = "20260912T000000Z-livebeef"
        live_workspace = parent / live_id
        subprocess.run(
            ["git", "worktree", "add", "-b", "unbound/live-livebeef", str(live_workspace), "main"],
            cwd=repo, check=True, capture_output=True, text=True,
        )
        state_dir = repo / ".blackhole-agent" / "unbound" / "missions" / live_id
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_text("{}", encoding="utf-8")

        first = reconcile_interrupted_creations(repo, worktree_parent=parent)
        second = reconcile_interrupted_creations(repo, worktree_parent=parent)

        inventory = json.loads(orphan_inventory_path(repo).read_text(encoding="utf-8"))
        events_path = continuous_loop_events_path(repo)
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ] if events_path.exists() else []
        interrupted = [e for e in events if e["event"] == INTERRUPTED_EVENT]

        observed = {
            "new_orphans_first": [e["mission_id"] for e in first["new_orphans"]],
            "new_orphans_second": len(second["new_orphans"]),
            "inventory_orphans": [e["mission_id"] for e in inventory["orphans"]],
            "receipt_names_branch": inventory["orphans"][0].get("branch") == orphan_branch,
            "receipt_names_workspace": inventory["orphans"][0].get("workspace") == str(orphan_workspace),
            "interrupted_events": len(interrupted),
            "orphan_workspace_preserved": orphan_workspace.is_dir(),
            "orphan_branch_preserved": orphan_branch in git(repo, "branch", "--list", orphan_branch),
            "registered_workspace_preserved": live_workspace.is_dir(),
            "registered_skipped": second["registered_skipped"],
        }
        observed["passed"] = bool(
            observed["new_orphans_first"] == [orphan_id]
            and observed["new_orphans_second"] == 0
            and observed["inventory_orphans"] == [orphan_id]
            and observed["receipt_names_branch"]
            and observed["receipt_names_workspace"]
            and observed["interrupted_events"] == 1
            and observed["orphan_workspace_preserved"]
            and observed["orphan_branch_preserved"]
            and observed["registered_workspace_preserved"]
            and observed["registered_skipped"] == 1
        )
        return {"passed": observed["passed"], "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
    sys.exit(0)
