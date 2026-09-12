"""Replay real CLI repairs over an aged history, preserving real live owners.

The baseline still repairs correctly but leaves years of expired receipts on
disk. Both implementations exit zero and report their observable outcome.
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
    from blackhole_agent.loop_login_rollup import LOGIN_AUDIT_ROLLUP_EVENT
    from blackhole_agent.loop_login_rollup_journal import login_rollup_repair_journal_path
    from blackhole_agent.loop_login_task import (
        dispatch_login_startup,
        login_startup_registration_path,
        register_loop_restore_at_login,
    )
    from blackhole_agent.loop_login_verify import verify_login_audit_rollup
    from blackhole_agent.unbound import (
        continuous_loop_guard,
        continuous_loop_lock_path,
        continuous_loop_state_path,
        pid_is_running,
        save_continuous_loop_state,
    )

    source = str(Path(blackhole_agent.__file__).resolve().parent.parent)

    def cli(command: str, repo: Path, root: Path) -> dict:
        run = subprocess.run(
            [sys.executable, "-I", "-c",
             "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));"
             "runpy.run_module('blackhole_agent.unbound',run_name='__main__')",
             source, command, "--repo-path", str(repo), "--output-dir", str(root)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        if run.returncode:
            raise RuntimeError(f"{command}: {run.stderr}")
        return json.loads(run.stdout)

    moment = datetime.now(timezone.utc)

    def stamp(days: int) -> str:
        return (moment - timedelta(days=days)).isoformat().replace("+00:00", "Z")

    def line(record: dict) -> bytes:
        return (json.dumps(record, sort_keys=True) + "\r\n").encode("utf-8")

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="acceptance-journal-retention-") as directory:
        parent = Path(directory)
        schedules = []

        def scheduler(payload):
            schedules.append(dict(payload))
            return {"applied": True, "backend": "acceptance"}

        repos = [parent / "target", parent / "surviving"]
        for repo in repos:
            repo.mkdir()
            save_continuous_loop_state(continuous_loop_state_path(repo), {
                "status": "running_mission", "pid": os.getpid(),
                "current_mission_id": "unfinished", "last_error": "preserve diagnostic",
            })
            continuous_loop_lock_path(repo).write_text(f"{os.getpid()}\n", encoding="utf-8")
            register_loop_restore_at_login(repo, scheduler=scheduler)

        # Hold real owner guards throughout the CLI operations. Journal
        # maintenance must neither acquire nor rewrite these guards/PID files.
        with continuous_loop_guard(continuous_loop_lock_path(repos[0])), \
                continuous_loop_guard(continuous_loop_lock_path(repos[1])):
            # Windows refuses reads of the locked guard byte itself.
            owner_files = {p: p.read_bytes() for repo in repos for p in repo.rglob("*")
                           if p.is_file() and p.suffix != ".guard"}
            schedules_before = list(schedules)
            root = login_startup_registration_path(repos[0]).parent
            audit = login_audit_log_path(root)
            journal = login_rollup_repair_journal_path(root)
            original = {
                "schema_version": 1, "event": LOGIN_AUDIT_ROLLUP_EVENT, "rollup": True,
                "compacted_count": 0, "compaction_runs": 3,
                "oldest_pruned_at": stamp(900), "newest_pruned_at": stamp(800),
                "last_compacted_at": stamp(500), "claim_note": {"keep": [0, "old claims"]},
            }

            def drift():
                audit.write_bytes(line(original))

            drift()
            first = cli("loop-login-rollup-repair", repos[0], root)
            template, completion = [json.loads(raw) for raw in journal.read_bytes().splitlines()]

            def pair(repair_id: str, days: int) -> bytes:
                receipt = dict(template, repair_id=repair_id, repaired_at=stamp(days), journaled_at=stamp(days))
                marker = dict(completion, repair_id=repair_id, applied_at=stamp(days))
                return line(receipt) + line(marker)

            aged_count = 900
            old = b"".join(pair(f"expired-{i}", 366 + i) for i in range(aged_count))
            recent = b"".join(pair(f"recent-{i}", i + 1) for i in range(3))
            pending = line(dict(template, repair_id="unresolved", repaired_at=stamp(900), journaled_at=stamp(900)))
            undated = line(dict(template, repair_id="undated", state="applied", journaled_at="invalid"))
            legacy = dict(template, repaired_at=stamp(800), journaled_at=stamp(800))
            legacy.pop("state")
            legacy.pop("repair_id")
            journal.write_bytes(old + line(legacy) + recent + pending + undated + b'{"torn":')
            before_size = journal.stat().st_size
            drift()
            repaired = cli("loop-login-rollup-repair", repos[0], root)
            raw = journal.read_bytes()
            history = cli("loop-login-rollup-journal", repos[0], root)
            entries = history["entries"]
            checks["repair_still_verifies"] = (
                first["repaired"] and repaired["repaired"] and verify_login_audit_rollup(root)["verified"]
            )
            checks["years_of_receipts_and_markers_expire_automatically"] = (
                b"expired-" not in raw and line(legacy) not in raw
                and history["entry_count"] == 6 and journal.stat().st_size < before_size // 20
            )
            checks["recent_pending_and_uncertain_bytes_retained"] = (
                recent + pending + undated + b'{"torn":\n' in raw and history["malformed_count"] == 1
                and next(e for e in entries if e.get("repair_id") == "unresolved")["state"] == "prepared"
            )
            checks["new_claims_auditable_after_cli_restart"] = (
                entries[-1]["prior_rollups"] == [original]
                and entries[-1]["corrected_rollup"] == repaired["rollup"]
                and entries[-1]["state"] == "applied"
            )
            plateau = []
            for cycle in range(3):
                with journal.open("ab") as stream:
                    stream.write(b"".join(pair(f"cycle-expired-{cycle}-{i}", 700 + i) for i in range(40)))
                drift()
                cli("loop-login-rollup-repair", repos[0], root)
                raw = journal.read_bytes()
                plateau.append(journal.stat().st_size)
            final_history = cli("loop-login-rollup-journal", repos[0], root)
            checks["subsequent_repairs_continue_bounding_history"] = (
                b"expired-" not in raw and final_history["entry_count"] == 9
                and max(plateau) < before_size // 20
            )
            unchanged = audit.read_bytes(), journal.read_bytes()
            idle = cli("loop-login-rollup-repair", repos[0], root)
            checks["verified_retry_is_byte_identical"] = (
                idle["reason"] == "already_verified" and (audit.read_bytes(), journal.read_bytes()) == unchanged
            )
            checks["live_owners_undisturbed"] = (
                pid_is_running(os.getpid()) and schedules == schedules_before
                and all(path.read_bytes() == before for path, before in owner_files.items())
                and all(dispatch_login_startup(repo).get("restore_reason") == "live_owner" for repo in repos)
                and all(path.read_bytes() == before for path, before in owner_files.items())
                and not login_rollup_repair_journal_path(login_startup_registration_path(repos[1]).parent).exists()
            )
            return {"passed": all(checks.values()), "observed": {
                "checks": checks, "seeded_aged_repairs": aged_count + 1 + 120,
                "journal_bytes_before": before_size, "journal_bytes_after": len(raw),
                "subsequent_journal_bytes": plateau, "remaining_receipts": final_history["entry_count"],
                "live_owner_pid": os.getpid(), "surviving_repos": 2,
            }}


if __name__ == "__main__":
    try:
        result = probe()
    except Exception as error:
        result = {"passed": False, "observed": {"error": type(error).__name__, "detail": str(error)}}
    print(json.dumps(result, sort_keys=True))
