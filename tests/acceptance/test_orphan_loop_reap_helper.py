"""Run loop-status against legacy PID locks with live, missing and recycled owners."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from blackhole_agent import unbound


def observe(repo: Path, pid: int, *, old_state: bool, old_lock: bool, expect_orphan: bool, fresh_update=False) -> dict:
    repo.mkdir()
    mission = repo / "mission.json"
    mission.write_bytes(b'{"status":"active","next":"finish pending work"}\n')
    mission_before = mission.read_bytes()
    state = unbound.continuous_loop_state_path(repo)
    lock = unbound.continuous_loop_lock_path(repo)
    events = unbound.continuous_loop_events_path(repo)
    context = dict(pid=pid, loop_id="interrupted", current_mission_id="pending", current_state_path=str(mission),
                   lineage_ref="proven", pending_publish_ref="unpublished", last_error="retain diagnostic")
    created = "2000-01-01T00:00:00Z" if old_state else unbound.utc_now_iso()
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({
        **context, "status": "running_mission", "next_wake_at": "2099-01-01T00:00:00Z",
        "created_at": created, "updated_at": unbound.utc_now_iso() if fresh_update else created,
    }), encoding="utf-8")
    lock.write_text(f"{pid}\n", encoding="utf-8")
    if old_lock:
        os.utime(lock, (946684800, 946684800))
    original, marker, mtime = state.read_bytes(), lock.read_bytes(), lock.stat().st_mtime

    def status(*args):
        result = CliRunner().invoke(unbound.app, ["loop-status", "--repo-path", str(repo), *args])
        if result.exit_code:
            raise RuntimeError(result.output or str(result.exception))
        return json.loads(result.stdout)

    view = status("--read-only")
    read_only = state.read_bytes() == original and lock.read_bytes() == marker and not events.exists()
    status()
    after = state.read_bytes()
    receipts = events.read_bytes() if events.exists() else b""
    status()
    durable = json.loads(after)
    unchanged = state.read_bytes() == after and (events.read_bytes() if events.exists() else b"") == receipts
    lock_present = lock.exists()
    if expect_orphan:
        receipt = json.loads(receipts) if len(receipts.splitlines()) == 1 else {}
        reason = "controller_pid_reused" if view["pid_alive"] else "controller_process_missing"
        outcome = (view["effective_status"] == durable["status"] == "orphaned" and not lock_present
                   and durable["orphaned_from_status"] == "running_mission" and durable["reaped_at"]
                   and durable["next_wake_at"] == "" and receipt.get("event") == "continuous_loop.orphaned"
                   and receipt.get("reason") == durable["stop_reason"] == reason)
    else:
        outcome = after == original and lock.is_file() and lock.read_bytes() == marker and not receipts

    # A crash can leave this last numeric marker behind after state was written.
    if not lock_present:
        lock.write_bytes(marker)
        os.utime(lock, (mtime, mtime))

    def claim(repo, output, prior):
        with unbound.continuous_loop_lock(lock):
            return {"pid": int(lock.read_text(encoding="utf-8"))}

    handoff = unbound.restore_orphaned_continuous_loop(repo, controller_starter=claim)
    claimed = handoff.get("restored_pid") == os.getpid()
    preserved = mission.read_bytes() == mission_before and all(durable[key] == value for key, value in context.items())
    return {
        "read_only_status": view["effective_status"], "pid_alive": view["pid_alive"], "status": durable["status"],
        "reaping_events": len(receipts.splitlines()), "lock_present": lock_present, "successor_claimed": claimed,
        "pending_work_preserved": preserved,
        "ok": bool(outcome and read_only and unchanged and claimed == expect_orphan and preserved),
    }


def main():
    with tempfile.TemporaryDirectory(prefix="bh-loop-owner-") as tmp:
        root = Path(tmp)
        # The reference record predates this real process. Its pipe must still work after recovery.
        with subprocess.Popen([sys.executable, "-c", "import sys; print(sys.stdin.readline().strip())"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as peer:
            try:
                results = {
                    "recycled": observe(root / "recycled", peer.pid, old_state=True, old_lock=True, expect_orphan=True),
                    "live": observe(root / "live", peer.pid, old_state=False, old_lock=False, expect_orphan=False),
                    "fresh_lock": observe(root / "fresh", peer.pid, old_state=True, old_lock=False, expect_orphan=False),
                    "fresh_checkpoint": observe(root / "updated", peer.pid, old_state=True, old_lock=True,
                                                expect_orphan=False, fresh_update=True),
                }
            finally:
                reply, _ = peer.communicate("still here\n", timeout=10)
        results["dead"] = observe(root / "dead", peer.pid, old_state=False, old_lock=False, expect_orphan=True)
        passed = (all(row["ok"] for row in results.values()) and reply.strip() == "still here"
                  and results["recycled"]["pid_alive"] is True and results["live"]["read_only_status"] == "running_mission"
                  and results["dead"]["pid_alive"] is False)
        return {"passed": passed, "observed": {**results, "peer_reply": reply.strip()}}


if __name__ == "__main__":
    print(json.dumps(main()))
