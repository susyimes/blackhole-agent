"""Replay two archived turn-one rejections, then ask status and genesis what happened."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from blackhole_agent.experience_fuel import render_experience_for_genesis
from blackhole_agent.kernel_mission_memory import (
    load_mission_memory, remember_completed_mission_turns, remember_turn_record, save_mission_memory,
)
from blackhole_agent.mission_journal_bound import write_bounded_turn_files
from blackhole_agent.pattern_register import ingest_unbound_turn

REJECTIONS = (
    ("20261102T193522Z-39fc66ae", "2026-11-02T19:53:43.934196Z",
     "machine-checkable done_when failed (capability_exists:codec.encode)"),
    ("20261117T155202Z-fc1ba707", "2026-11-17T16:28:50.407514Z",
     "behavior acceptance failed: candidate probe crashed; this is not behavioral acceptance evidence"),
)


def rejection(at, reason):
    return dict(iteration=1, finished_at=at, effective_status="continue",
                milestone_gate=dict(requested=True, accepted=False, reasons=[reason]))


def exercise(root: Path) -> dict:
    for mission, at, reason in REJECTIONS:
        directory = root / ".blackhole-agent" / "unbound" / "missions" / mission
        turn_dir = directory / "turns" / "0001"
        turn_dir.mkdir(parents=True)
        state = dict(schema_version=1, mission_id=mission, created_at=at, updated_at=at, status="complete",
                     repo_path=str(root), workspace_path=str(root), branch=mission, target_branch="main")
        (directory / "state.json").write_text(json.dumps(state), encoding="utf-8")
        persisted = write_bounded_turn_files(directory, rejection(at, reason), turn_dir=turn_dir, mission_id=mission)
        ingest_unbound_turn(root, persisted)

    row = load_mission_memory(root)["classes"]["milestone_rejected"]
    live = [row["count"], row["evidence"], row.get("source_mission_id")]
    states = sorted(root.glob(".blackhole-agent/unbound/missions/*/state.json"))
    for path in reversed(states):
        remember_completed_mission_turns(root, state_path=path)
        remember_completed_mission_turns(root, state_path=path)
        (path.parent / "turns" / "0001" / "turn.json").unlink()
        (path.parent / "events.jsonl").unlink()

    histories = {}
    for path in states:
        command = [sys.executable, "-m", "blackhole_agent.unbound", "status", "--state-path", str(path)]
        status = json.loads(subprocess.check_output(command, encoding="utf-8", timeout=30))
        histories[status["mission_id"]] = [
            [item["class_id"], int(item["iteration"]), item["at"], item["evidence"]]
            for item in status.get("failures", [])
        ]
    genesis = render_experience_for_genesis(root)
    fuel = [line for line in genesis.splitlines() if "[mission-memory/milestone_rejected]" in line]
    count = load_mission_memory(root)["classes"]["milestone_rejected"]["count"]
    return dict(live=live, histories=histories, genesis=fuel, count=count)


def test_backfill_repairs_legacy_attribution(tmp_path):
    first, latest = REJECTIONS
    class_id = "milestone_rejected"
    summary = "turn 1 milestone rejected"
    legacy = dict(count=587, summary=summary, source_mission_id=first[0], evidence=latest[2],
                  first_seen=first[1], last_seen=latest[1], seen=[f"\n1\n{class_id}\n{summary}"])
    save_mission_memory(tmp_path, {"classes": {class_id: legacy}})
    for owner, at, reason in (latest, first, latest, first):
        remember_turn_record(tmp_path, rejection(at, reason), source_mission_id=owner)
    row = load_mission_memory(tmp_path)["classes"][class_id]
    assert (row["count"], row["source_mission_id"], row["evidence"]) == (587, latest[0], latest[2])
    assert (row["first_seen"], row["last_seen"]) == (first[1], latest[1])
    assert latest[0] in render_experience_for_genesis(tmp_path)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        observed = exercise(Path(directory))
    mission, _, reason = REJECTIONS[-1]
    expected = {owner: [["milestone_rejected", 1, at, error]] for owner, at, error in REJECTIONS}
    passed = (observed["histories"] == expected and observed["count"] == len(expected)
              and observed["live"] == [len(expected), reason, mission]
              and len(observed["genesis"]) == 1 and mission in observed["genesis"][0]
              and reason in observed["genesis"][0] and REJECTIONS[0][0] not in observed["genesis"][0])
    print(json.dumps({"passed": passed, "observed": observed}))
