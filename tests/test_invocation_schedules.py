"""Unit tests for persisted interval schedules."""

from __future__ import annotations

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
