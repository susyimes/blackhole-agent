"""Replay real compaction followed by corruption; report outcomes, never crash.

Uses public behavior and temporary live-owner repos. No ledger proofs,
installed tasks, source inspection, or process termination are involved.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def probe():
    from blackhole_agent.loop_login_audit import login_audit_log_path, read_login_scrub_audit
    from blackhole_agent.loop_login_compact import compact_login_audit_tombstones
    from blackhole_agent.loop_login_rollup import is_login_audit_rollup
    from blackhole_agent.loop_login_rollup_repair import repair_login_audit_rollup
    from blackhole_agent.loop_login_task import (
        dispatch_login_startup,
        login_startup_registration_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT
    from blackhole_agent.loop_login_verify import verify_login_audit_rollup
    from blackhole_agent.unbound import (
        continuous_loop_lock_path, continuous_loop_state_path, pid_is_running,
        save_continuous_loop_state,
    )

    observed = {}
    with tempfile.TemporaryDirectory(prefix="acceptance-rollup-integrity-") as directory:
        parent = Path(directory)
        scheduler_calls = []

        def scheduler(payload):
            scheduler_calls.append(dict(payload))
            return {"backend": "acceptance", "applied": True}

        surviving = [parent / "owner-a", parent / "owner-b"]
        for repo in surviving:
            repo.mkdir()
            (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
            save_continuous_loop_state(continuous_loop_state_path(repo), {
                "loop_id": "integrity-owner", "status": "running_mission", "pid": os.getpid(),
                "current_mission_id": "unfinished", "current_state_path": str(repo / "mission.json"),
            })
            continuous_loop_lock_path(repo).write_text(f"{os.getpid()}\n", encoding="utf-8")
            register_loop_restore_at_login(repo, scheduler=scheduler)

        root = login_startup_registration_path(surviving[0]).parent
        path = login_audit_log_path(root)

        def tombstone(name, pruned_at):
            return {
                "event": LOGIN_AUDIT_TOMBSTONE_EVENT, "tombstone": True,
                "task_name": name, "pruned_at": pruned_at,
            }

        path.write_text("\n".join(json.dumps(record) for record in [
            tombstone("old-a", "2024-01-01T00:00:00Z"),
            tombstone("old-b", "2024-02-01T00:00:00Z"),
            tombstone("survivor", "2026-09-01T00:00:00Z"),
        ]) + "\n", encoding="utf-8")
        compacted = compact_login_audit_tombstones(root, now=datetime(2026, 9, 12, tzinfo=timezone.utc))
        original = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        rollup = next(record for record in original if is_login_audit_rollup(record))
        survivor = next(record for record in original if record.get("task_name") == "survivor")
        intact = verify_login_audit_rollup(root)
        observed["intact_verified"] = intact.get("verified")
        observed["compacted_count"] = compacted.get("compacted_count")

        # Protect every file in both live repos, excluding only the audit fixture.
        protected = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                     for repo in surviving for p in repo.rglob("*") if p.is_file() and p != path}
        calls_before = list(scheduler_calls)
        encoded_rollup, encoded_survivor = json.dumps(rollup), json.dumps(survivor)
        covering = dict(rollup, newest_pruned_at=survivor["pruned_at"])
        cases = {
            "truncated_rollup": [encoded_survivor, encoded_rollup[:-8]],
            "truncated_survivor": [encoded_rollup, encoded_survivor[:-8]],
            "rollup_flag_changed": [encoded_survivor, json.dumps(dict(rollup, rollup=False))],
            "rollup_event_changed": [encoded_survivor, json.dumps(dict(rollup, event="altered"))],
            "hidden_span_survivor": [json.dumps(covering), json.dumps(dict(survivor, tombstone=False))],
            "duplicate_count_key": [encoded_survivor, '{"compacted_count":0,' + encoded_rollup[1:]],
            "non_record_line": [encoded_rollup, encoded_survivor, "null"],
        }
        outcomes = {}
        for name, lines in cases.items():
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            raw, modified = path.read_bytes(), path.stat().st_mtime_ns
            verified = verify_login_audit_rollup(root)
            surfaced = read_login_scrub_audit(root)["tombstone_rollup_verification"]
            outcomes[name] = {
                "verified": verified.get("verified"), "audit_verified": surfaced.get("verified"),
                "reason": verified.get("reason"), "drift": verified.get("drift"),
                "pure_read": path.read_bytes() == raw and path.stat().st_mtime_ns == modified,
            }

        # An incomplete trail cannot be safely repaired using just its intact lines.
        path.write_text(json.dumps(dict(rollup, compacted_count=0)) + "\n{truncated\n", encoding="utf-8")
        raw = path.read_bytes()
        repaired = repair_login_audit_rollup(root)
        observed["incomplete_repair_refused"] = repaired.get("repaired") is False and path.read_bytes() == raw
        restores = [dispatch_login_startup(repo, controller_starter=None) for repo in surviving]
        observed["live_owners_preserved"] = (
            pid_is_running(os.getpid())
            and all(p.is_file() and (p.read_bytes(), p.stat().st_mtime_ns) == content
                    for p, content in protected.items())
            and all(result.get("restore_reason") == "live_owner" and result.get("started") is False
                    for result in restores)
            and scheduler_calls == calls_before
        )
        observed["cases"] = outcomes
        passed = (
            observed["intact_verified"] is True and observed["compacted_count"] == 2
            and observed["incomplete_repair_refused"] and observed["live_owners_preserved"]
            and all(case["verified"] is False and case["audit_verified"] is False and case["pure_read"]
                    for case in outcomes.values())
        )
    return {"passed": bool(passed), "observed": observed}


if __name__ == "__main__":
    try:
        result = probe()
    except Exception as error:
        result = {"passed": False, "observed": {"error": type(error).__name__, "detail": str(error)}}
    print(json.dumps(result, sort_keys=True))
