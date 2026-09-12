"""Replayable operator outcome: complete repair history survives replacement.

Uses real temporary audit files, CLI repair/read, and a real live owner PID.
The same probe exits zero with a JSON verdict on both baseline and candidate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def probe() -> dict:
    import blackhole_agent
    from blackhole_agent.loop_login_audit import login_audit_log_path
    from blackhole_agent.loop_login_compact import compact_login_audit_tombstones
    from blackhole_agent.loop_login_rollup import is_login_audit_rollup
    from blackhole_agent.loop_login_rollup_journal import login_rollup_repair_journal_path
    from blackhole_agent.loop_login_task import (
        dispatch_login_startup,
        login_startup_registration_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.loop_login_tombstone import LOGIN_AUDIT_TOMBSTONE_EVENT
    from blackhole_agent.loop_login_verify import verify_login_audit_rollup
    from blackhole_agent.unbound import (
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )

    source = str(Path(blackhole_agent.__file__).resolve().parent.parent)

    def cli(command: str, repo: Path, root: Path) -> dict:
        # Explicit source selection also works in the controller's isolated
        # baseline subprocess. Readback cannot rely on in-memory repair data.
        run = subprocess.run(
            [sys.executable, "-I", "-c",
             "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));"
             "runpy.run_module('blackhole_agent.unbound',run_name='__main__')",
             source, command, "--repo-path", str(repo), "--output-dir", str(root)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        if run.returncode:
            raise RuntimeError(f"{command} failed: {run.stderr}")
        return json.loads(run.stdout)

    def stamp(days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="acceptance-rollup-journal-") as directory:
        parent = Path(directory)
        scheduled: list[dict] = []

        def scheduler(payload: dict) -> dict:
            scheduled.append(dict(payload))
            return {"backend": "acceptance", "applied": True}

        repos = [parent / "target", parent / "surviving"]
        for repo in repos:
            repo.mkdir()
            (repo / "mission.json").write_text('{"status":"active"}\n', encoding="utf-8")
            save_continuous_loop_state(continuous_loop_state_path(repo), {
                "status": "running_mission", "pid": os.getpid(),
                "current_state_path": str(repo / "mission.json"),
                "current_mission_id": "unfinished", "last_error": "preserve diagnostic",
            })
            continuous_loop_lock_path(repo).write_text(f"{os.getpid()}\n", encoding="utf-8")
            register_loop_restore_at_login(repo, scheduler=scheduler)
        owner_files = {
            file: file.read_bytes() for repo in repos for file in repo.rglob("*") if file.is_file()
        }
        schedules_before = list(scheduled)
        root = login_startup_registration_path(repos[0]).parent
        audit = login_audit_log_path(root)
        journal = login_rollup_repair_journal_path(root)
        tombstones = [{
            "schema_version": 1, "event": LOGIN_AUDIT_TOMBSTONE_EVENT,
            "tombstone": True, "task_name": f"old-{days}", "pruned_at": stamp(days),
        } for days in (450, 400, 30)]
        audit.write_text("".join(json.dumps(r) + "\n" for r in tombstones), encoding="utf-8")
        compacted = compact_login_audit_tombstones(root)
        records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
        base = next(record for record in records if is_login_audit_rollup(record))
        prior = [
            dict(base, compacted_count=0, newest_pruned_at=stamp(0), claim_note="first drift"),
            dict(base, compacted_count=7, compaction_runs=3, claim_note={"second": ["unique", 7]}),
        ]
        survivors = [record for record in records if not is_login_audit_rollup(record)]
        audit.write_text("".join(json.dumps(r) + "\n" for r in survivors + prior), encoding="utf-8")
        repaired = cli("loop-login-rollup-repair", repos[0], root)
        history = cli("loop-login-rollup-journal", repos[0], root)
        entries = history.get("entries") or []
        entry = entries[0] if entries else {}
        corrected = repaired.get("rollup") or {}
        checks["real_compaction_and_repair"] = (
            compacted.get("compacted") is True and repaired.get("repaired") is True
            and verify_login_audit_rollup(root)["verified"] is True
        )
        checks["all_original_claims_readable_after_restart"] = entry.get("prior_rollups") == prior
        checks["correction_readable_after_restart"] = (
            entry.get("corrected_rollup") == corrected and corrected.get("compacted_count") == 7
            and corrected.get("compaction_runs") == 4
            and "merged_duplicate_rollup" in entry.get("corrections", [])
            and "span_clamped_below_survivor" in entry.get("corrections", [])
            and "duplicate_rollup" in entry.get("drift", [])
        )
        checks["receipt_linked_and_completed"] = (
            bool(corrected.get("repair_id")) and entry.get("repair_id") == corrected.get("repair_id")
            and entry.get("state") == "applied"
        )
        first_entry = dict(entry)
        second_prior = dict(corrected, compacted_count=0, claim_note="second repair")
        audit.write_text("".join(json.dumps(r) + "\n" for r in survivors + [second_prior]), encoding="utf-8")
        second = cli("loop-login-rollup-repair", repos[0], root)
        history2 = cli("loop-login-rollup-journal", repos[0], root)
        entries2 = history2.get("entries") or []
        checks["repeated_repairs_retain_history"] = (
            second.get("repaired") is True and len(entries2) == 2 and entries2[0] == first_entry
            and entries2[1].get("prior_rollups") == [second_prior]
            and entries2[1].get("corrected_rollup") == second.get("rollup")
        )
        unchanged_audit, unchanged_journal = audit.read_bytes(), journal.read_bytes()
        idle = cli("loop-login-rollup-repair", repos[0], root)
        checks["verified_retry_is_byte_identical"] = (
            idle.get("repaired") is False and idle.get("reason") == "already_verified"
            and audit.read_bytes() == unchanged_audit and journal.read_bytes() == unchanged_journal
        )

        # A directory at the journal pathname reliably reproduces a real
        # storage failure, including on Windows and when running as admin.
        failed_root = parent / "unwritable-journal"
        failed_root.mkdir()
        failed_audit = login_audit_log_path(failed_root)
        failed_journal = login_rollup_repair_journal_path(failed_root)
        failed_audit.write_text(json.dumps(prior[0]) + "\n", encoding="utf-8")
        failed_before = failed_audit.read_bytes()
        failed_journal.mkdir()
        failure = cli("loop-login-rollup-repair", repos[0], failed_root)
        checks["journal_failure_preserves_drifted_claims"] = (
            failure.get("repaired") is False and failure.get("reason") == "journal_write_failed"
            and failed_audit.read_bytes() == failed_before
            and not list(failed_root.glob("*.tmp"))
        )
        failed_journal.rmdir()
        retry = cli("loop-login-rollup-repair", repos[0], failed_root)
        retry_history = cli("loop-login-rollup-journal", repos[0], failed_root)
        checks["storage_recovery_can_repair_with_evidence"] = (
            retry.get("repaired") is True
            and len(retry_history.get("entries", [])) == 1
            and retry_history["entries"][0].get("prior_rollups") == [prior[0]]
        )
        checks["live_owners_undisturbed"] = (
            all(path.read_bytes() == before for path, before in owner_files.items())
            and pid_is_running(os.getpid()) and scheduled == schedules_before
            and all(dispatch_login_startup(repo, controller_starter=None).get("restore_reason") == "live_owner"
                    for repo in repos)
            and all(path.read_bytes() == before for path, before in owner_files.items())
            and not login_audit_log_path(login_startup_registration_path(repos[1]).parent).exists()
            and not login_rollup_repair_journal_path(login_startup_registration_path(repos[1]).parent).exists()
        )
        return {
            "passed": all(checks.values()),
            "observed": {"checks": checks, "repairs_read_back": len(entries2),
                         "original_duplicate_claims": entry.get("prior_rollups"),
                         "journal_failure_reason": failure.get("reason"),
                         "live_owner_pid": os.getpid()},
        }


if __name__ == "__main__":
    try:
        result = probe()
    except Exception as error:
        result = {"passed": False, "observed": {"error": type(error).__name__, "detail": str(error)}}
    print(json.dumps(result, sort_keys=True))
