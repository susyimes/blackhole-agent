import json
import os

import pytest
from typer.testing import CliRunner

from blackhole_agent import unbound


def seed_loop(repo, *, status="running_mission", pid=123, lock="123\n"):
    path = unbound.continuous_loop_state_path(repo)
    unbound.save_continuous_loop_state(path, {
        "loop_id": "orphan", "status": status, "pid": pid,
        "current_mission_id": "unfinished", "current_state_path": "mission.json",
        "next_wake_at": "tomorrow", "last_error": "preserve diagnostic",
    })
    if lock is not None:
        unbound.continuous_loop_lock_path(repo).write_text(lock, encoding="utf-8")
    return path


@pytest.mark.parametrize("status", [
    "starting", "running", "creating_mission", "running_mission", "publishing", "sleeping",
    "sleeping_publish_retry", "sleeping_mission_create_retry",
])
@pytest.mark.parametrize("lock", ["123\n", None])
def test_reaps_every_active_phase_once(tmp_path, monkeypatch, status, lock):
    monkeypatch.setattr(unbound, "pid_is_running", lambda _: False)
    path = seed_loop(tmp_path, status=status, lock=lock)
    first = unbound.reap_orphaned_continuous_loop(tmp_path)
    persisted = path.read_bytes()
    second = unbound.reap_orphaned_continuous_loop(tmp_path)
    events = unbound.continuous_loop_events_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert first["status"] == second["status"] == "orphaned"
    assert first["orphaned_from_status"] == status
    assert first["last_error"] == "preserve diagnostic"
    assert first["stop_reason"] == "controller_process_missing"
    assert first["next_wake_at"] == ""
    assert path.read_bytes() == persisted
    assert len(events) == 1
    assert not unbound.continuous_loop_lock_path(tmp_path).exists()


@pytest.mark.parametrize("pid", [None, "bad", 0, -1, True, 3.5, 2**40])
def test_invalid_pid_is_unknown_and_never_reaped(tmp_path, pid):
    path = seed_loop(tmp_path, pid=pid)
    before = path.read_bytes()
    result = unbound.reap_orphaned_continuous_loop(tmp_path)
    assert result["effective_status"] == "unknown"
    assert result["pid_alive"] is None
    assert result["liveness_error"]
    assert path.read_bytes() == before


def test_failed_liveness_query_never_means_dead(tmp_path, monkeypatch):
    def denied(_):
        raise PermissionError("process query denied")

    monkeypatch.setattr(unbound, "pid_is_running", denied)
    path = seed_loop(tmp_path)
    before = path.read_bytes()
    result = unbound.reap_orphaned_continuous_loop(tmp_path)
    assert result["effective_status"] == "unknown"
    assert result["pid_alive"] is None
    assert path.read_bytes() == before


@pytest.mark.parametrize("status", ["stopped", "orphaned"])
def test_terminal_state_is_not_rewritten(tmp_path, monkeypatch, status):
    monkeypatch.setattr(unbound, "pid_is_running", lambda _: False)
    path = seed_loop(tmp_path, status=status)
    before = path.read_bytes()
    result = unbound.reap_orphaned_continuous_loop(tmp_path)
    assert result["status"] == status
    assert path.read_bytes() == before


@pytest.mark.parametrize("lock", ["broken", "0", "456\n"])
def test_unknown_or_live_lock_owner_blocks_reaping(tmp_path, monkeypatch, lock):
    monkeypatch.setattr(unbound, "pid_is_running", lambda pid: pid == 456)
    path = seed_loop(tmp_path, lock=lock)
    before = path.read_bytes()
    result = unbound.reap_orphaned_continuous_loop(tmp_path)
    assert result["status"] == "running_mission"
    assert result["reaping_error"]
    assert path.read_bytes() == before
    assert unbound.continuous_loop_lock_path(tmp_path).read_text(encoding="utf-8") == lock


def test_guard_prevents_reaping_old_state_during_controller_takeover(tmp_path, monkeypatch):
    monkeypatch.setattr(unbound, "pid_is_running", lambda pid: pid == os.getpid())
    path = seed_loop(tmp_path)
    before = path.read_bytes()
    lock = unbound.continuous_loop_lock_path(tmp_path)
    with unbound.continuous_loop_lock(lock):
        result = unbound.reap_orphaned_continuous_loop(tmp_path)
        assert result["reaping_error"]
        assert path.read_bytes() == before
        assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())
        with pytest.raises(RuntimeError, match="guard"):
            with unbound.continuous_loop_lock(lock):
                pytest.fail("duplicate controller acquired ownership")
    assert not lock.exists()


def test_reaper_rechecks_state_after_acquiring_guard(tmp_path, monkeypatch):
    from contextlib import contextmanager

    monkeypatch.setattr(unbound, "pid_is_running", lambda pid: pid == os.getpid())
    path = seed_loop(tmp_path)
    original_guard = unbound.continuous_loop_guard

    @contextmanager
    def replaced_state(lock):
        seed_loop(tmp_path, pid=os.getpid(), lock=f"{os.getpid()}\n")
        with original_guard(lock):
            yield

    monkeypatch.setattr(unbound, "continuous_loop_guard", replaced_state)
    result = unbound.reap_orphaned_continuous_loop(tmp_path)
    assert result["status"] == "running_mission"
    assert result["pid_alive"] is True
    assert json.loads(path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    assert not unbound.continuous_loop_events_path(tmp_path).exists()


def test_status_read_only_preserves_orphan_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(unbound, "pid_is_running", lambda _: False)
    path = seed_loop(tmp_path)
    before = path.read_bytes()
    result = CliRunner().invoke(unbound.app, ["loop-status", "--repo-path", str(tmp_path), "--read-only"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["effective_status"] == "orphaned"
    assert path.read_bytes() == before
    assert unbound.continuous_loop_lock_path(tmp_path).exists()
    assert not unbound.continuous_loop_events_path(tmp_path).exists()


def test_stop_reaps_dead_owner_instead_of_waiting_for_it(tmp_path, monkeypatch):
    monkeypatch.setattr(unbound, "pid_is_running", lambda _: False)
    path = seed_loop(tmp_path)
    result = CliRunner().invoke(unbound.app, ["loop-stop", "--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "orphaned"
    assert not unbound.continuous_loop_stop_path(tmp_path).exists()


def test_stop_live_owner_still_requests_graceful_stop(tmp_path):
    path = seed_loop(tmp_path, pid=os.getpid(), lock=f"{os.getpid()}\n")
    before = path.read_bytes()
    result = CliRunner().invoke(unbound.app, ["loop-stop", "--repo-path", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert path.read_bytes() == before
    assert unbound.continuous_loop_stop_path(tmp_path).exists()
