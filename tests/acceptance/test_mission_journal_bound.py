"""Outcome probe: closed mission journals keep a path-list digest, not the full inventory.

A completed fixture whose events journal and state repeat a changed-path list
longer than the retention bound is compacted. The rewritten state still
reports the original goal, status complete, and last error, and the receipt
records that path list's sha256 and count. A sibling active mission keeps
identical events and state bytes. A newly written turn file keeps the digest
and omits a middle sentinel path.

On the previous milestone the bounder is absent, so this probe reports
passed=false. Both outcomes exit 0.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path


SENTINEL = "artifacts/forage/UNIQUE-SENTINEL-NOT-IN-SAMPLE.whl"
GOAL = "Keep regenerated forage paths out of the mission journal."
LAST_ERROR = "journal grew without a bound"


def _sha256(paths: list[str]) -> str:
    return hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()


def _paths() -> list[str]:
    paths = [f"artifacts/forage/regenerated-cache-object-{index:05d}.whl" for index in range(400)]
    paths[200] = SENTINEL
    return paths


def _mission(root: Path, name: str, status: str, paths: list[str]) -> Path:
    mission = root / name
    mission.mkdir(parents=True)
    record = {
        "changed_paths": list(paths),
        "effective_status": "continue",
        "last_error": LAST_ERROR,
        "milestone_gate": {
            "accepted": False,
            "behavior_paths": list(paths),
            "changed_paths": list(paths),
            "reasons": ["kept-diagnosis"],
            "requested": True,
        },
        "summary": "turn stored every changed path",
    }
    state = {
        "done_when": "journal stays bounded",
        "goal": GOAL,
        "last_error": LAST_ERROR,
        "mission_id": name,
        "recent_turns": [record],
        "status": status,
    }
    (mission / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (mission / "events.jsonl").write_text(json.dumps({"event": "turn.completed", **record}) + "\n", encoding="utf-8")
    return mission


def _observe() -> dict:
    try:
        from blackhole_agent.mission_journal_bound import (
            compact_closed_mission_journal,
            write_bounded_turn_files,
        )
    except ImportError:
        return {"passed": False, "observed": "mission journal bounder is absent"}

    paths = _paths()
    expected = _sha256(paths)
    parent = Path(tempfile.mkdtemp(prefix="mission-journal-bound-"))
    try:
        completed = _mission(parent, "completed-mission", "complete", paths)
        active = _mission(parent, "active-mission", "active", paths)
        active_before = {
            "state": (active / "state.json").read_bytes(),
            "events": (active / "events.jsonl").read_bytes(),
        }
        original_state = (completed / "state.json").stat().st_size
        original_events = (completed / "events.jsonl").stat().st_size
        receipt = compact_closed_mission_journal(completed, allowed_root=parent)
        active_same = (
            (active / "state.json").read_bytes() == active_before["state"]
            and (active / "events.jsonl").read_bytes() == active_before["events"]
        )
        active_refusal = compact_closed_mission_journal(active, allowed_root=parent)
        active_still = (
            (active / "state.json").read_bytes() == active_before["state"]
            and (active / "events.jsonl").read_bytes() == active_before["events"]
        )
        rewritten = json.loads((completed / "state.json").read_text(encoding="utf-8"))
        events_text = (completed / "events.jsonl").read_text(encoding="utf-8")
        state_text = (completed / "state.json").read_text(encoding="utf-8")
        inventories = [
            item
            for file_row in receipt.get("files") or []
            for item in file_row.get("inventories") or []
            if item.get("field") == "changed_paths"
        ]
        live = parent / "live-mission"
        persisted = write_bounded_turn_files(
            live,
            {
                "changed_paths": list(paths),
                "milestone_gate": {"changed_paths": list(paths), "behavior_paths": list(paths)},
                "summary": "new turn",
            },
            turn_dir=live / "turns" / "0001",
            mission_id="live-mission",
        )
        turn_text = (live / "turns" / "0001" / "turn.json").read_text(encoding="utf-8")
        live_events = (live / "events.jsonl").read_text(encoding="utf-8")
        passed = bool(
            receipt.get("ok") is True
            and (completed / "state.json").stat().st_size < original_state
            and (completed / "events.jsonl").stat().st_size < original_events
            and rewritten.get("goal") == GOAL
            and rewritten.get("status") == "complete"
            and rewritten.get("last_error") == LAST_ERROR
            and SENTINEL not in state_text
            and SENTINEL not in events_text
            and any(item.get("sha256") == expected and item.get("count") == len(paths) for item in inventories)
            and active_same
            and active_refusal.get("ok") is False
            and str(active_refusal.get("reason") or "").startswith("status_active")
            and active_still
            and persisted.get("changed_paths_inventory", {}).get("sha256") == expected
            and persisted.get("changed_paths_inventory", {}).get("count") == len(paths)
            and SENTINEL not in turn_text
            and SENTINEL not in live_events
        )
        return {
            "passed": passed,
            "observed": {
                "completed_bytes": [
                    original_state,
                    (completed / "state.json").stat().st_size,
                    original_events,
                    (completed / "events.jsonl").stat().st_size,
                ],
                "receipt_reason": receipt.get("reason"),
                "goal": rewritten.get("goal"),
                "status": rewritten.get("status"),
                "last_error": rewritten.get("last_error"),
                "sentinel_removed": SENTINEL not in state_text and SENTINEL not in events_text,
                "active_unchanged": active_still,
                "active_reason": active_refusal.get("reason"),
                "turn_digest": persisted.get("changed_paths_inventory", {}).get("sha256"),
            },
        }
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def main() -> int:
    print(json.dumps(_observe(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
