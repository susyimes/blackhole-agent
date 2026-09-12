"""Unit tests for blackhole_agent.validation_env."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from blackhole_agent import validation_env


def _fake_venv_python(repo: Path) -> Path:
    interpreter = validation_env.venv_python(repo)
    interpreter.parent.mkdir(parents=True, exist_ok=True)
    interpreter.write_text("", encoding="utf-8")
    return interpreter


def _runner_returning(missing: list[str], calls: list[list[str]]):
    def runner(command, **kwargs):
        calls.append([str(part) for part in command])
        return subprocess.CompletedProcess(command, 0, json.dumps(missing), "")

    return runner


def test_healthy_environment_is_not_repaired(tmp_path: Path) -> None:
    _fake_venv_python(tmp_path)
    calls: list[list[str]] = []
    report = validation_env.ensure_validation_environment(
        tmp_path,
        command_runner=_runner_returning([], calls),
    )
    assert report["ok"] is True
    assert report["repaired"] is False
    assert report["missing_tools"] == []
    assert all("sync" not in call for call in calls)


def test_drifted_environment_is_repaired(tmp_path: Path) -> None:
    _fake_venv_python(tmp_path)
    state = {"synced": False}

    def runner(command, **kwargs):
        command = [str(part) for part in command]
        if command[:2] == ["uv", "sync"]:
            state["synced"] = True
            return subprocess.CompletedProcess(command, 0, "", "")
        missing = [] if state["synced"] else ["pytest", "ruff", "yaml"]
        return subprocess.CompletedProcess(command, 0, json.dumps(missing), "")

    report = validation_env.ensure_validation_environment(tmp_path, command_runner=runner)
    assert state["synced"] is True
    assert report["ok"] is True
    assert report["repaired"] is True
    assert report["missing_before"] == ["pytest", "ruff", "yaml"]
    assert report["sync_exit_code"] == 0


def test_missing_venv_triggers_repair_attempt(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append([str(part) for part in command])
        return subprocess.CompletedProcess(command, 0, "", "")

    report = validation_env.ensure_validation_environment(tmp_path, command_runner=runner)
    assert report["ok"] is False
    assert report["repaired"] is False
    assert ["uv", "sync", "--extra", "dev"] in calls


def test_sync_failure_is_reported_not_raised(tmp_path: Path) -> None:
    def runner(command, **kwargs):
        raise OSError("uv not found")

    report = validation_env.ensure_validation_environment(tmp_path, command_runner=runner)
    assert report["ok"] is False
    assert report["repaired"] is False
    assert report["sync_error"] == "uv not found"


def test_foreign_path_fallback_is_named(tmp_path: Path, monkeypatch) -> None:
    _fake_venv_python(tmp_path)
    foreign = tmp_path / "elsewhere" / "bin"
    foreign.mkdir(parents=True)
    foreign_pytest = foreign / "pytest"
    foreign_pytest.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        validation_env.shutil,
        "which",
        lambda name: str(foreign_pytest) if name == "pytest" else None,
    )
    report = validation_env.validation_environment_report(
        tmp_path,
        command_runner=_runner_returning(["pytest"], []),
    )
    assert report["ok"] is False
    assert report["foreign_path_fallback"] == ["pytest"]
