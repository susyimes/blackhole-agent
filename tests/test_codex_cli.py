import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import blackhole_agent.kernels.codex_cli as codex_cli
from blackhole_agent.kernels.codex_cli import (
    CodexCliConfig,
    CodexCliKernel,
    build_codex_exec_command,
    build_codex_provider_preflight,
    shutdown_subprocess_cli_transport_stderr,
)


def test_build_codex_exec_command_reads_task_from_stdin(tmp_path):
    command = build_codex_exec_command(
        CodexCliConfig(model="gpt-5", profile="work", skip_git_repo_check=True),
        cwd=tmp_path,
        output_last_message=tmp_path / "last.md",
    )

    assert command[1:4] == ["exec", "--cd", str(tmp_path)]
    assert ["--model", "gpt-5"] == command[command.index("--model") : command.index("--model") + 2]
    assert ["--profile", "work"] == command[command.index("--profile") : command.index("--profile") + 2]
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--skip-git-repo-check" in command
    assert "--ask-for-approval" not in command
    assert command[-1] == "-"


def test_codex_kernel_writes_task_and_result_files(tmp_path):
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("done")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)
    result = kernel.run("Improve tests", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=12)

    assert calls[0][0][1] == "exec"
    assert calls[0][0][-1] == "-"
    assert calls[0][1]["input"] == "Improve tests"
    assert calls[0][1]["timeout"] == 12
    assert result.returncode == 0
    assert result.last_message == "done"
    assert result.task_path.read_text(encoding="utf-8") == "Improve tests"
    latest = json.loads((tmp_path / "out" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["last_message"] == "done"
    assert latest["provider_preflight"]["selected_provider"] == "codex_cli"


def test_codex_provider_preflight_blocks_implicit_default_route_when_required():
    preflight = build_codex_provider_preflight(CodexCliConfig(require_explicit_route=True))

    assert preflight["ok"] is False
    assert preflight["selected_provider"] == "codex_cli"
    assert preflight["route_selector"] == "implicit_default"
    assert preflight["diagnostics"] == [
        "codex mode requires an explicit --model or --profile to avoid implicit provider fallback"
    ]
    assert preflight["token_value_recorded"] is False
    assert preflight["profile_value_recorded"] is False


def test_codex_provider_preflight_accepts_explicit_model_or_profile():
    model_preflight = build_codex_provider_preflight(CodexCliConfig(model="gpt-5.5", require_explicit_route=True))
    profile_preflight = build_codex_provider_preflight(CodexCliConfig(profile="work", require_explicit_route=True))

    assert model_preflight["ok"] is True
    assert model_preflight["route_selector"] == "model"
    assert model_preflight["model"] == "gpt-5.5"
    assert profile_preflight["ok"] is True
    assert profile_preflight["route_selector"] == "profile"
    assert profile_preflight["profile_present"] is True
    assert profile_preflight["profile_value_recorded"] is False


def test_codex_kernel_fails_before_exec_when_route_is_implicit(tmp_path):
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="unexpected", stderr="")

    kernel = CodexCliKernel(
        CodexCliConfig(codex_bin="codex", require_explicit_route=True),
        command_runner=fake_runner,
    )

    with pytest.raises(ValueError, match="Codex provider/config preflight failed"):
        kernel.run("Improve tests", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=12)

    assert calls == []
    latest = json.loads((tmp_path / "out" / "latest-codex-provider-preflight.json").read_text(encoding="utf-8"))
    assert latest["ok"] is False
    assert latest["route_selector"] == "implicit_default"


def test_codex_kernel_preserves_long_nested_local_paths_in_command_and_artifacts(tmp_path):
    workspace = (
        tmp_path
        / ".bh-worktrees"
        / "20260616T133522Z"
        / "nested-local-workspace"
    )
    output_dir = workspace / ".blackhole-agent" / "codex"
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        last_message = command[command.index("--output-last-message") + 1]
        Path(last_message).write_text("done from nested workspace", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)
    result = kernel.run("Exercise nested path handling", cwd=workspace, output_dir=output_dir, timeout_seconds=12)

    command = calls[0][0]
    assert command[command.index("--cd") + 1] == str(workspace)
    assert command[command.index("--output-last-message") + 1] == str(result.last_message_path)
    assert result.last_message_path.is_absolute()
    assert str(result.last_message_path).startswith(str(output_dir))

    latest = json.loads((output_dir / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["cwd"] == str(workspace)
    assert latest["task_path"] == str(result.task_path)
    assert latest["last_message_path"] == str(result.last_message_path)
    assert latest["result_path"] == str(result.result_path)
    serialized_cwd = latest["cwd"].replace("\\", "/")
    assert serialized_cwd.startswith(str(tmp_path).replace("\\", "/"))
    assert not serialized_cwd.startswith(f"/{workspace.name}/")


def test_build_codex_exec_command_can_bypass_sandbox(tmp_path):
    command = build_codex_exec_command(
        CodexCliConfig(bypass_approvals_and_sandbox=True),
        cwd=tmp_path,
        output_last_message=tmp_path / "last.md",
    )

    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--sandbox" not in command


def test_codex_kernel_raises_on_nonzero_exit_after_writing_result(tmp_path):
    def fake_runner(command, **kwargs):
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("partial failure details")
        return subprocess.CompletedProcess(command, 7, stdout="partial stdout", stderr="boom")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)

    with pytest.raises(RuntimeError, match="Codex CLI failed with exit code 7"):
        kernel.run("Improve tests", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=12)

    latest = json.loads((tmp_path / "out" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["returncode"] == 7
    assert latest["last_message"] == "partial failure details"
    assert latest["stderr_tail"] == "boom"


def test_codex_kernel_cancel_recover_uses_fresh_artifacts_for_same_second(tmp_path, monkeypatch):
    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 16, 9, 17, 3, tzinfo=timezone.utc)

    attempts = 0
    last_message_paths = []

    def fake_runner(command, **kwargs):
        nonlocal attempts
        attempts += 1
        last_message = command[command.index("--output-last-message") + 1]
        last_message_paths.append(last_message)
        if attempts == 1:
            with open(last_message, "w", encoding="utf-8") as handle:
                handle.write("partial state from interrupted run")
            raise subprocess.TimeoutExpired(command, timeout=1, output="started", stderr="")
        assert not Path(last_message).exists()
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("recovered cleanly")
        return subprocess.CompletedProcess(command, 0, stdout="finished", stderr="")

    monkeypatch.setattr(codex_cli, "datetime", FixedDatetime)
    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)

    with pytest.raises(TimeoutError, match="Codex CLI timed out after 1 seconds"):
        kernel.run("Interruptible task", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=1)
    result = kernel.run("Recover task", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=5)

    assert last_message_paths[0] != last_message_paths[1]
    assert Path(last_message_paths[0]).read_text(encoding="utf-8") == "partial state from interrupted run"
    assert result.last_message == "recovered cleanly"
    assert result.returncode == 0
    assert result.timed_out is False

    latest = json.loads((tmp_path / "out" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["last_message"] == "recovered cleanly"
    assert latest["timed_out"] is False
    assert latest["result_path"].endswith("codex-run-20260616T091703Z-001.json")


def test_shutdown_subprocess_cli_transport_stderr_treats_absent_task_group_as_already_closed(caplog):
    class TransportWithoutStderrTaskGroup:
        pass

    caplog.set_level(logging.DEBUG, logger=codex_cli.__name__)

    cleaned = shutdown_subprocess_cli_transport_stderr(TransportWithoutStderrTaskGroup())

    assert cleaned is False
    assert "_stderr_task_group is absent" in caplog.text


def test_shutdown_subprocess_cli_transport_stderr_is_idempotent_after_cancel_scope(caplog):
    class CancelScope:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    class TaskGroup:
        def __init__(self):
            self.cancel_scope = CancelScope()

    class Transport:
        def __init__(self):
            self._stderr_task_group = TaskGroup()

    transport = Transport()
    task_group = transport._stderr_task_group
    caplog.set_level(logging.DEBUG, logger=codex_cli.__name__)

    first_cleaned = shutdown_subprocess_cli_transport_stderr(transport)
    second_cleaned = shutdown_subprocess_cli_transport_stderr(transport)

    assert first_cleaned is True
    assert task_group.cancel_scope.cancelled is True
    assert transport._stderr_task_group is None
    assert second_cleaned is False
    assert "_stderr_task_group is already cleared" in caplog.text
