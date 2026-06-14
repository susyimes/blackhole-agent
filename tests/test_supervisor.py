import json
import subprocess
import sys

from blackhole_agent.supervisor import (
    SupervisorConfig,
    build_wake_command,
    run_wake_once,
)


def test_build_wake_command_launches_one_shot_child(tmp_path):
    config = SupervisorConfig(
        repo_path=tmp_path,
        output_dir=tmp_path / "supervisor",
        evolution_mode="codex",
        extra_instruction="prefer tests",
    )

    command = build_wake_command(config)

    assert command[:3] == [sys.executable, "-m", "blackhole_agent.github_growth"]
    assert "--interval-seconds" not in command
    assert command[command.index("--evolution-mode") : command.index("--evolution-mode") + 2] == [
        "--evolution-mode",
        "codex",
    ]
    assert command[command.index("--trend-query") + 1] == "agent language:Python"
    assert command[command.index("--output-dir") + 1] == str(tmp_path / "supervisor" / "growth")
    assert "--force-evolve" in command
    assert "--ignore-user-config" in command
    assert "prefer tests" in command[command.index("--extra-instruction") + 1]


def test_run_wake_once_records_success_and_commits_dirty_worktree(tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="codex/evolve\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="before123\n", stderr="")
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout=" M src/example.py\n", stderr="")
        if command[:2] == ["git", "add"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["git", "commit"]:
            return subprocess.CompletedProcess(command, 0, stdout="[branch abc123] ok\n", stderr="")
        if command[:3] == ["git", "rev-parse", "--verify"]:
            return subprocess.CompletedProcess(command, 0, stdout="abc123\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="child ok", stderr="")

    config = SupervisorConfig(repo_path=tmp_path, output_dir=tmp_path / "supervisor")
    record = run_wake_once(config, command_runner=runner)

    assert record.returncode == 0
    assert record.start_branch == "codex/evolve"
    assert record.start_head == "before123"
    assert record.finish_branch == "codex/evolve"
    assert record.finish_head == "before123"
    assert record.commit_result is not None
    assert record.commit_result.committed is True
    assert record.commit_result.commit_sha == "abc123"
    assert calls[2][0][:3] == [sys.executable, "-m", "blackhole_agent.github_growth"]
    assert ["git", "commit", "-m"] in [call[0][:3] for call in calls]
    latest = json.loads((tmp_path / "supervisor" / "latest-supervisor-pass.json").read_text(encoding="utf-8"))
    heartbeat = json.loads(
        (tmp_path / "supervisor" / "latest-supervisor-heartbeat.json").read_text(encoding="utf-8")
    )
    assert latest["returncode"] == 0
    assert latest["start_branch"] == "codex/evolve"
    assert latest["start_head"] == "before123"
    assert latest["finish_branch"] == "codex/evolve"
    assert latest["finish_head"] == "before123"
    assert latest["commit_result"]["committed"] is True
    assert heartbeat["last_pass_id"] == record.pass_id
    assert (tmp_path / "supervisor" / "supervisor.log").exists()


def test_run_wake_once_does_not_commit_failed_pass(tmp_path):
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="codex/evolve\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="before123\n", stderr="")
        return subprocess.CompletedProcess(command, 3, stdout="", stderr="failed")

    config = SupervisorConfig(repo_path=tmp_path, output_dir=tmp_path / "supervisor")
    record = run_wake_once(config, command_runner=runner)

    assert record.returncode == 3
    assert record.commit_result is None
    assert not any(call[0][:2] == ["git", "status"] for call in calls)
