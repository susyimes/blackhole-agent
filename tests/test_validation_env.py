"""Exercise validation readiness with a real venv and controlled sync results."""

import shutil
import subprocess
import sys
import venv
from pathlib import Path
from unittest.mock import Mock

from blackhole_agent import validation_env


def test_repair_ignores_shadow_modules_and_is_idempotent(tmp_path, monkeypatch):
    local = tmp_path / ".venv"
    venv.create(local, with_pip=False)
    python = validation_env.venv_python(tmp_path)
    purelib = Path(subprocess.check_output(
        [python, "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True,
    ).strip())
    # These files are visible via both the project's cwd and the inherited Python path.
    tools = [tmp_path / f"{name}.py" for name in validation_env.DEV_TOOL_MODULES]
    for tool in tools:
        tool.touch()
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda name: sys.executable if name == "pytest" else None)
    syncs = []

    def runner(command, **kwargs):
        if command[:2] != ["uv", "sync"]:
            return subprocess.run(command, **kwargs)
        syncs.append(command)
        for tool in tools:
            shutil.copyfile(tool, purelib / tool.name)
        return subprocess.CompletedProcess(command, 0)

    repaired = validation_env.ensure_validation_environment(tmp_path, command_runner=runner)
    healthy = validation_env.ensure_validation_environment(tmp_path, command_runner=runner)
    assert repaired["ok"] and repaired["repaired"] and repaired["sync_exit_code"] == 0
    assert repaired["missing_before"] == ["pytest", "ruff", "yaml"]
    assert repaired["foreign_path_fallback_before"] == ["pytest"]
    assert healthy["ok"] and not healthy["repaired"] and healthy["missing_tools"] == []
    assert syncs == [["uv", "sync", "--extra", "dev"]]


def test_missing_venv_triggers_repair_attempt(tmp_path):
    runner = Mock(return_value=subprocess.CompletedProcess([], 0))
    report = validation_env.ensure_validation_environment(tmp_path, command_runner=runner)
    assert not report["ok"] and not report["repaired"]
    assert runner.call_args.args[0] == ["uv", "sync", "--extra", "dev"]


def test_sync_failure_is_reported(tmp_path):
    runner = Mock(side_effect=OSError("uv not found"))
    report = validation_env.ensure_validation_environment(tmp_path, command_runner=runner)
    assert not report["ok"] and not report["repaired"]
    assert report["sync_error"] == "uv not found"
