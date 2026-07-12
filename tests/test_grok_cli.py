import json
import subprocess
from pathlib import Path

import pytest

from blackhole_agent.kernels.grok_cli import (
    GrokCliConfig,
    GrokCliKernel,
    build_grok_command,
    build_grok_provider_preflight,
    extract_grok_last_message,
)
from blackhole_agent.supervisor import SupervisorConfig, build_wake_command


def test_build_grok_command_uses_prompt_file_and_normalizes_workspace_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.grok_cli.shutil.which", lambda _: "C:/tools/grok.exe")
    prompt_file = tmp_path / "task.md"
    command = build_grok_command(
        GrokCliConfig(model="grok-4.5", sandbox="workspace-write"),
        cwd=tmp_path,
        prompt_file=prompt_file,
    )

    assert command[:3] == ["C:/tools/grok.exe", "--cwd", str(tmp_path)]
    assert command[command.index("--sandbox") + 1] == "workspace"
    assert command[command.index("--model") + 1] == "grok-4.5"
    assert command[-2:] == ["--prompt-file", str(prompt_file)]
    assert "--no-memory" in command
    assert "--no-subagents" in command
    assert "--disable-web-search" in command
    assert "Bash(git commit *)" in command
    assert "Bash(git push *)" in command


def test_grok_kernel_writes_artifacts_and_extracts_json_message(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.grok_cli.shutil.which", lambda _: "C:/tools/grok.exe")
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        task_path = Path(command[command.index("--prompt-file") + 1])
        assert task_path.read_text(encoding="utf-8") == "Make one safe change."
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"text": "Completed safely.", "stopReason": "EndTurn"}),
            stderr="",
        )

    result = GrokCliKernel(
        GrokCliConfig(model="grok-4.5", require_explicit_route=True),
        command_runner=runner,
    ).run("Make one safe change.", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=30)

    assert result.returncode == 0
    assert result.last_message == "Completed safely."
    assert result.last_message_path.read_text(encoding="utf-8") == "Completed safely."
    assert (tmp_path / "out" / "latest-grok-run.json").exists()
    assert seen["kwargs"]["cwd"] == tmp_path
    assert "input" not in seen["kwargs"]


def test_grok_kernel_preserves_failure_artifact_before_raising(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.grok_cli.shutil.which", lambda _: "C:/tools/grok.exe")

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="authentication failed")

    kernel = GrokCliKernel(GrokCliConfig(model="grok-4.5"), command_runner=runner)
    with pytest.raises(RuntimeError, match="exit code 7"):
        kernel.run("Task", cwd=tmp_path, output_dir=tmp_path / "out")

    payload = json.loads((tmp_path / "out" / "latest-grok-run.json").read_text(encoding="utf-8"))
    assert payload["returncode"] == 7
    assert payload["stderr_tail"] == "authentication failed"


def test_grok_preflight_requires_binary_and_explicit_model(monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.grok_cli.shutil.which", lambda _: None)
    preflight = build_grok_provider_preflight(GrokCliConfig(require_explicit_route=True), env={})

    assert preflight["ok"] is False
    assert preflight["diagnostics"] == [
        "grok executable was not found on PATH",
        "grok mode requires an explicit --model to avoid implicit provider fallback",
    ]
    assert preflight["token_value_recorded"] is False


def test_extract_grok_last_message_accepts_verified_headless_shape():
    assert extract_grok_last_message('{"text":"GROK_HEADLESS_OK","stopReason":"EndTurn"}') == "GROK_HEADLESS_OK"


def test_supervisor_wake_command_selects_grok_kernel(tmp_path):
    config = SupervisorConfig(
        repo_path=tmp_path,
        kernel="grok",
        model="grok-4.5",
        branch_prefix="grok/blackhole-evolve",
    )
    command = build_wake_command(config)

    assert command[command.index("--kernel") + 1] == "grok"
    assert command[command.index("--model") + 1] == "grok-4.5"
    assert command[command.index("--branch-prefix") + 1] == "grok/blackhole-evolve"
