"""Unit tests for persisted interval schedules."""

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from blackhole_agent.invocation_schedules import ScheduleError, SchedulePlane


def test_disabled_plane_refuses_create(tmp_path: Path) -> None:
    plane = SchedulePlane(tmp_path, enabled=False)
    with pytest.raises(ScheduleError) as caught:
        plane.create("capability.absorbed-text-reverser", {"raw_text": "ab"}, 1)
    assert caught.value.status == 400
    assert caught.value.error == "schedules_disabled"
    assert plane.health()["schedules"] is False


def test_schedule_survives_a_new_plane_and_fires_again(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def invoke(root: Path, capability_id: str, provided_input: dict, *, cancel_event: object = None) -> dict:
        calls.append({"root": root, "capability_id": capability_id, "input": dict(provided_input)})
        return {
            "ok": True,
            "output": {"reversed_text": str(provided_input["raw_text"])[::-1]},
            "invocation_id": f"inv-{len(calls)}",
            "artifacts": [],
        }

    plane = SchedulePlane(tmp_path, enabled=True, invoke=invoke)
    created = plane.create("capability.absorbed-text-reverser", {"raw_text": "ab"}, 1)
    assert created["last_status"] == "pending"
    assert plane.dispatch_due() == 1
    deadline = time.time() + 5
    record = plane.get(created["schedule_id"])
    while time.time() < deadline and record["last_status"] != "completed":
        time.sleep(0.05)
        record = plane.get(created["schedule_id"])
    assert record["last_status"] == "completed"
    assert record["last_output"] == {"reversed_text": "ba"}
    assert record["run_count"] == 1
    plane.stop()

    restarted = SchedulePlane(tmp_path, enabled=True, invoke=invoke)
    again = restarted.get(created["schedule_id"])
    assert again["run_count"] == 1
    assert again["last_output"] == {"reversed_text": "ba"}
    # The first fire already pushed next_fire_at forward. Wait it out, then dispatch.
    time.sleep(1.1)
    assert restarted.dispatch_due() == 1
    deadline = time.time() + 5
    record = restarted.get(created["schedule_id"])
    while time.time() < deadline and int(record["run_count"]) < 2:
        time.sleep(0.05)
        record = restarted.get(created["schedule_id"])
    assert record["run_count"] == 2
    cancelled = restarted.delete(created["schedule_id"])
    assert cancelled["cancelled"] is True
    with pytest.raises(ScheduleError) as missing:
        restarted.get(created["schedule_id"])
    assert missing.value.status == 404
    assert restarted.dispatch_due(now=time.time() + 10_000) == 0
    restarted.stop()


def _wait_for(predicate, *, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "condition did not become true"


def test_standby_preserves_running_work_and_waits_for_drain(tmp_path: Path) -> None:
    release = threading.Event()
    began = threading.Event()
    calls = []

    def invoke(*args, **kwargs):
        calls.append(args[1])
        began.set()
        assert release.wait(5)
        return {"output": {"value": len(calls)}}

    owner = SchedulePlane(tmp_path, enabled=True, invoke=invoke)
    standby = SchedulePlane(tmp_path, enabled=True, invoke=invoke)
    item = owner.create("capability.slow", {}, 1)
    ident = item["schedule_id"]
    try:
        assert owner.dispatch_due() == 1
        assert began.wait(3)
        standby.start()
        assert standby.get(ident)["last_status"] == "running"
        assert standby.dispatch_due(now=time.time() + 100) == 0
        assert len(calls) == 1
        # Even after its timer stops, the owner must hold the guard until
        # the outstanding invocation finishes.
        owner.stop()
        assert standby.dispatch_due(now=time.time() + 100) == 0
        release.set()
        _wait_for(lambda: standby.get(ident)["run_count"] == 1)
        _wait_for(lambda: owner.health()["scheduler_role"] == "standby")
        assert standby.dispatch_due(now=time.time() + 100) == 1
        _wait_for(lambda: standby.get(ident)["run_count"] == 2)
        assert len(calls) == 2
    finally:
        release.set()
        owner.stop()
        standby.stop()


def test_deleted_running_schedule_still_holds_ownership_until_finished(tmp_path: Path) -> None:
    release = threading.Event()
    began = threading.Event()

    def invoke(*args, **kwargs):
        began.set()
        assert release.wait(5)
        return {"output": {"value": 1}}

    owner = SchedulePlane(tmp_path, enabled=True, invoke=invoke)
    standby = SchedulePlane(tmp_path, enabled=True, invoke=invoke)
    ident = owner.create("capability.deleted", {}, 1)["schedule_id"]
    try:
        owner.dispatch_due()
        assert began.wait(3)
        standby.delete(ident)
        standby.create("capability.next", {}, 1)
        owner.stop()
        assert standby.dispatch_due() == 0
        release.set()
        _wait_for(lambda: owner.health()["scheduler_role"] == "standby")
        assert standby.dispatch_due() == 1
        with pytest.raises(ScheduleError):
            standby.get(ident)
    finally:
        release.set()
        owner.stop()
        standby.stop()


def test_delete_between_due_scan_and_reservation_never_runs(tmp_path: Path, monkeypatch) -> None:
    calls = []
    owner = SchedulePlane(tmp_path, enabled=True, invoke=lambda *a, **k: calls.append(a))
    other = SchedulePlane(tmp_path, enabled=True)
    ident = owner.create("capability.deleted", {}, 1)["schedule_id"]
    original_due = owner._due

    def delete_after_scan(now):
        due = original_due(now)
        other.delete(ident)
        return due

    monkeypatch.setattr(owner, "_due", delete_after_scan)
    try:
        assert owner.dispatch_due() == 0
        assert calls == []
        assert other.list_schedules() == []
    finally:
        owner.stop()
        other.stop()


def test_abandoned_fire_is_paused_while_other_schedules_continue(tmp_path: Path) -> None:
    calls = []

    def invoke(root, capability_id, provided_input, **kwargs):
        calls.append(capability_id)
        return {"output": provided_input}

    owner = SchedulePlane(tmp_path, enabled=True, invoke=invoke)
    uncertain = owner.create("capability.unknown", {}, 1)["schedule_id"]
    # A durable pre-execution reservation left by a dead process.
    with sqlite3.connect(owner.db_path) as connection:
        connection.execute("UPDATE schedules SET last_status = 'running' WHERE schedule_id = ?", (uncertain,))
    ready = owner.create("capability.ready", {"value": 7}, 1)["schedule_id"]
    try:
        assert owner.dispatch_due() == 1
        _wait_for(lambda: owner.get(ready)["last_status"] == "completed")
        recovered = owner.get(uncertain)
        assert recovered["last_status"] == "interrupted"
        assert "schedule_outcome_unknown" in recovered["last_error"]
        assert recovered["run_count"] == 0
        owner.delete(ready)
        assert owner.dispatch_due(now=time.time() + 100) == 0
        assert calls == ["capability.ready"]
    finally:
        owner.stop()


def test_independent_roots_execute_concurrently(tmp_path: Path) -> None:
    began = threading.Barrier(3)
    release = threading.Event()

    def invoke(*args, **kwargs):
        began.wait(timeout=5)
        assert release.wait(5)
        return {"output": {"ok": True}}

    planes = [SchedulePlane(tmp_path / name, enabled=True, invoke=invoke) for name in ("a", "b")]
    try:
        for plane in planes:
            plane.create("capability.independent", {}, 1)
            assert plane.dispatch_due() == 1
        began.wait(timeout=5)
    finally:
        release.set()
        for plane in planes:
            plane.stop()


def test_failed_http_bind_cannot_start_or_own_schedules(tmp_path: Path, monkeypatch) -> None:
    from blackhole_agent import capability_service

    called = threading.Event()

    def invoke(*args, **kwargs):
        called.set()
        return {"output": {"echo": "bound"}}

    original_init = SchedulePlane.__init__

    def configure_invoke(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._invoke = invoke

    monkeypatch.setattr(SchedulePlane, "__init__", configure_invoke)
    store = SchedulePlane(tmp_path, enabled=True)
    ident = store.create("capability.bind", {}, 60)["schedule_id"]
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        with pytest.raises(OSError):
            capability_service.build_server(tmp_path, port=occupied.getsockname()[1], schedule_enabled=True)
        assert not called.wait(0.3)
        assert store.get(ident)["last_status"] == "pending"
    server = capability_service.build_server(tmp_path, port=0, schedule_enabled=True)
    try:
        assert called.wait(3)
        _wait_for(lambda: store.get(ident)["last_status"] == "completed")
        assert store.get(ident)["run_count"] == 1
    finally:
        server.server_close()
        store.stop()


def test_graceful_process_exit_commits_inflight_result(tmp_path: Path) -> None:
    script = """
import sys, threading, time
from pathlib import Path
from blackhole_agent.invocation_schedules import SchedulePlane
began = threading.Event()
def invoke(*args, **kwargs):
    began.set()
    time.sleep(0.4)
    return {'output': {'drained': True}}
plane = SchedulePlane(Path(sys.argv[1]), enabled=True, invoke=invoke)
plane.create('capability.drain', {}, 60)
plane.start()
assert began.wait(3)
plane.stop()
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], env=env, capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    store = SchedulePlane(tmp_path, enabled=True)
    [record] = store.list_schedules()
    assert record["last_status"] == "completed"
    assert record["last_output"] == {"drained": True}
    assert record["run_count"] == 1
    assert store.dispatch_due() == 0
    assert store.get(record["schedule_id"])["last_status"] == "completed"
    store.stop()
