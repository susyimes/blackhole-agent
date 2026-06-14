import json
import subprocess

import pytest

from blackhole_agent.kernels.codex_cli import CodexCliConfig, CodexCliKernel, build_codex_exec_command


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
