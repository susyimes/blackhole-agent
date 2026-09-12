"""Unit tests for scheduled acceptance-sweep hygiene."""

from __future__ import annotations

import json
from pathlib import Path

from blackhole_agent.durable_state import durable_read_path
from blackhole_agent.loop_acceptance_hygiene import (
    HYGIENE_HELPER,
    HYGIENE_TASK_NAME,
    HYGIENE_TRIGGER,
    dispatch_acceptance_hygiene,
    hygiene_registration_path,
    hygiene_report_path,
    hygiene_state_path,
    load_hygiene_registration,
    schedule_acceptance_hygiene,
)

_MET = """import json
print(json.dumps({"passed": True, "observed": {"sentinel": "GREEN"}}))
"""

_BROKEN = """import json
print(json.dumps({"passed": False, "observed": {"sentinel": "BROKEN"}}))
"""


def _make_repo(tmp_path: Path, *, flaky_green: bool = True) -> Path:
    repo = tmp_path / "repo"
    acceptance = repo / "tests" / "acceptance"
    acceptance.mkdir(parents=True)
    (acceptance / "test_stable.py").write_text(_MET, encoding="utf-8")
    (acceptance / "test_flaky.py").write_text(_MET if flaky_green else _BROKEN, encoding="utf-8")
    return repo


def _scheduler(calls: list[str]):
    def apply(registration: dict) -> dict:
        calls.append(str(registration.get("name") or ""))
        return {"backend": "proof", "applied": True}

    return apply


def test_schedule_writes_registration_xml_and_launcher(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    calls: list[str] = []
    scheduled = schedule_acceptance_hygiene(repo, scheduler=_scheduler(calls))
    assert scheduled["scheduled"] is True
    assert scheduled["ran"] is False
    assert scheduled["trigger"] == HYGIENE_TRIGGER
    assert scheduled["helper"] == HYGIENE_HELPER
    assert calls == [HYGIENE_TASK_NAME]
    xml = durable_read_path(Path(scheduled["task_xml_path"])).read_text(encoding="utf-8")
    assert "<CalendarTrigger>" in xml and "ScheduleByDay" in xml
    launcher = durable_read_path(Path(scheduled["launcher_path"])).read_text(encoding="utf-8")
    assert "dispatch_acceptance_hygiene" in launcher


def test_dispatch_surfaces_regression_and_recovery(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    schedule_acceptance_hygiene(repo, scheduler=_scheduler([]))

    first = dispatch_acceptance_hygiene(repo)
    assert first["ran"] is True
    assert first["ok"] is True
    assert first["regressions"] == []

    (repo / "tests" / "acceptance" / "test_flaky.py").write_text(_BROKEN, encoding="utf-8")
    second = dispatch_acceptance_hygiene(repo)
    assert second["ok"] is False
    assert [item["name"] for item in second["regressions"]] == ["test_flaky"]
    assert second["regressions"][0]["previously_green"] is True

    report = json.loads(durable_read_path(hygiene_report_path(repo)).read_text(encoding="utf-8"))
    assert [item["name"] for item in report["regressions"]] == ["test_flaky"]
    state = json.loads(durable_read_path(hygiene_state_path(repo)).read_text(encoding="utf-8"))
    assert "test_flaky" in state["green"]
    assert state["last_ok"] is False

    (repo / "tests" / "acceptance" / "test_flaky.py").write_text(_MET, encoding="utf-8")
    third = dispatch_acceptance_hygiene(repo)
    assert third["ok"] is True
    assert third["regressions"] == []


def test_dispatch_skips_missing_or_disabled_registration(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    skipped = dispatch_acceptance_hygiene(repo)
    assert skipped["ran"] is False
    assert skipped["skip_reason"] == "not_registered"

    schedule_acceptance_hygiene(repo, scheduler=_scheduler([]))
    registration = load_hygiene_registration(repo)
    assert registration is not None
    registration["enabled"] = False
    hygiene_registration_path(repo).parent.mkdir(parents=True, exist_ok=True)
    hygiene_registration_path(repo).write_text(json.dumps(registration), encoding="utf-8")
    disabled = dispatch_acceptance_hygiene(repo)
    assert disabled["ran"] is False
    assert disabled["skip_reason"] == "not_enabled"


def test_builtin_proof_is_green() -> None:
    from blackhole_agent.loop_acceptance_hygiene import builtin_acceptance_hygiene_proof

    result = builtin_acceptance_hygiene_proof()
    assert result["ok"], result.get("failed")
    assert result["used_skill_route_discovery"] is False
