import json
import subprocess
import sys
from pathlib import Path

from blackhole_agent.supervisor import (
    SupervisorConfig,
    build_wake_command,
    promote_candidate,
    run_startup_health_check,
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
    assert command[command.index("--repo-path") + 1] == str(tmp_path)
    assert "--force-evolve" in command
    assert "--ignore-user-config" in command
    assert "prefer tests" in command[command.index("--extra-instruction") + 1]


def test_run_wake_once_promotes_candidate_worktree_and_pushes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    rollback = output_dir / "growth" / "latest-rollback-point.json"
    rollback.parent.mkdir(parents=True)
    rollback.write_text("{}\n", encoding="utf-8")
    state: dict[str, object] = {
        "child_ran": False,
        "committed": False,
        "merged": False,
        "pushed": False,
        "removed": False,
    }

    def runner(command, **kwargs):
        cwd = Path(kwargs["cwd"])
        if command[:4] == ["git", "worktree", "add", "--detach"]:
            candidate_path = Path(command[4])
            candidate_path.mkdir(parents=True)
            state["candidate"] = candidate_path
            return subprocess.CompletedProcess(command, 0, stdout="prepared\n", stderr="")
        if command[:3] == [sys.executable, "-m", "blackhole_agent.github_growth"]:
            state["child_ran"] = True
            return subprocess.CompletedProcess(command, 0, stdout="child ok", stderr="")
        if command == ["git", "branch", "--show-current"]:
            if cwd == repo:
                return subprocess.CompletedProcess(command, 0, stdout="main\n", stderr="")
            branch = "codex/evolve\n" if state["child_ran"] else "\n"
            return subprocess.CompletedProcess(command, 0, stdout=branch, stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            if cwd == repo:
                head = "cand123\n" if state["merged"] else "base123\n"
            else:
                head = "cand123\n" if state["child_ran"] else "base123\n"
            return subprocess.CompletedProcess(command, 0, stdout=head, stderr="")
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="cand123\n", stderr="")
        if command == ["git", "rev-parse", "--verify", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="base123\n", stderr="")
        if command[:2] == ["git", "status"]:
            dirty = cwd != repo and state["child_ran"] and not state["committed"]
            return subprocess.CompletedProcess(command, 0, stdout=" M src/example.py\n" if dirty else "", stderr="")
        if command[:2] == ["git", "add"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["git", "commit"]:
            state["committed"] = True
            return subprocess.CompletedProcess(command, 0, stdout="[branch cand123] ok\n", stderr="")
        if command[:2] == ["uv", "run"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")
        if command == ["git", "switch", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "merge", "--ff-only", "cand123"]:
            state["merged"] = True
            return subprocess.CompletedProcess(command, 0, stdout="merged\n", stderr="")
        if command == ["git", "push", "origin", "main"]:
            state["pushed"] = True
            return subprocess.CompletedProcess(command, 0, stdout="pushed\n", stderr="")
        if command[:3] == ["git", "worktree", "remove"]:
            state["removed"] = True
            return subprocess.CompletedProcess(command, 0, stdout="removed\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=output_dir,
        worktree_parent_dir=tmp_path / "worktrees",
        model="gpt-5.5",
        bypass_approvals_and_sandbox=True,
    )
    record = run_wake_once(config, command_runner=runner)

    assert record.returncode == 0
    assert record.worktree_result is not None
    assert record.worktree_result.created is True
    assert record.worktree_result.removed is True
    assert record.commit_result is not None
    assert record.commit_result.committed is True
    assert record.promotion_result is not None
    assert record.promotion_result.promoted is True
    assert record.promotion_result.pushed is True
    assert record.promotion_result.rollback_artifact_exists is True
    assert record.promotion_result.restart_requested is True
    assert state["pushed"] is True
    assert state["removed"] is True

    latest = json.loads((output_dir / "latest-supervisor-pass.json").read_text(encoding="utf-8"))
    heartbeat = json.loads((output_dir / "latest-supervisor-heartbeat.json").read_text(encoding="utf-8"))
    restart_request = json.loads((output_dir / "latest-restart-request.json").read_text(encoding="utf-8"))
    assert latest["promotion_result"]["promoted"] is True
    assert latest["promotion_result"]["pushed"] is True
    assert heartbeat["last_promoted"] is True
    assert heartbeat["last_pushed"] is True
    assert heartbeat["last_restart_requested"] is True
    assert restart_request["target_head"] == "cand123"


def test_promote_candidate_rolls_back_when_post_merge_health_fails(tmp_path):
    repo = tmp_path / "repo"
    candidate = tmp_path / "candidate"
    repo.mkdir()
    candidate.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    rollback = output_dir / "growth" / "latest-rollback-point.json"
    rollback.parent.mkdir(parents=True)
    rollback.write_text("{}\n", encoding="utf-8")
    state = {"merged": False, "reset": False}
    calls = []

    def runner(command, **kwargs):
        cwd = Path(kwargs["cwd"])
        calls.append((command, cwd))
        if command == ["git", "rev-parse", "--verify", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="base123\n", stderr="")
        if command == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["uv", "run"]:
            if cwd == candidate:
                return subprocess.CompletedProcess(command, 0, stdout="candidate ok\n", stderr="")
            return subprocess.CompletedProcess(command, 7, stdout="", stderr="post merge failed")
        if command == ["git", "switch", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "merge", "--ff-only", "cand123"]:
            state["merged"] = True
            return subprocess.CompletedProcess(command, 0, stdout="merged\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            head = "base123\n" if state["reset"] else "cand123\n"
            return subprocess.CompletedProcess(command, 0, stdout=head, stderr="")
        if command == ["git", "reset", "--hard", "base123"]:
            state["reset"] = True
            return subprocess.CompletedProcess(command, 0, stdout="reset\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=output_dir,
        health_commands=("uv run pytest",),
        push_promotions=True,
    )
    result = promote_candidate(
        config,
        candidate_repo_path=candidate,
        pass_id="20260614T000000Z",
        candidate_branch="codex/evolve",
        candidate_head="cand123",
        command_runner=runner,
    )

    assert result.promoted is False
    assert result.pushed is False
    assert result.returncode == 7
    assert result.rollback_attempted is True
    assert result.rollback_succeeded is True
    assert state["merged"] is True
    assert state["reset"] is True
    assert ["git", "push", "origin", "main"] not in [call[0] for call in calls]


def test_startup_health_failure_rolls_back_to_previous_promotion(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    output_dir.mkdir(parents=True)
    (output_dir / "latest-supervisor-pass.json").write_text(
        json.dumps({"promotion_result": {"target_before": "base123"}}) + "\n",
        encoding="utf-8",
    )
    calls = []

    def runner(command, **kwargs):
        calls.append((command, Path(kwargs["cwd"])))
        if command[:2] == ["uv", "run"]:
            return subprocess.CompletedProcess(command, 9, stdout="", stderr="broken startup")
        if command == ["git", "reset", "--hard", "base123"]:
            return subprocess.CompletedProcess(command, 0, stdout="reset\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=output_dir,
        health_commands=("uv run pytest",),
    )
    record = run_startup_health_check(config, command_runner=runner)

    assert record.returncode == 0
    assert record.rollback_attempted is True
    assert record.rollback_succeeded is True
    assert record.rollback_target == "base123"
    assert ["git", "reset", "--hard", "base123"] in [call[0] for call in calls]
    latest = json.loads((output_dir / "latest-startup-health.json").read_text(encoding="utf-8"))
    assert latest["rollback_succeeded"] is True


def test_run_wake_once_does_not_commit_or_promote_failed_pass(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    calls = []

    def runner(command, **kwargs):
        calls.append((command, Path(kwargs["cwd"])))
        if command[:4] == ["git", "worktree", "add", "--detach"]:
            Path(command[4]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="main\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="before123\n", stderr="")
        if command[:3] == [sys.executable, "-m", "blackhole_agent.github_growth"]:
            return subprocess.CompletedProcess(command, 3, stdout="", stderr="failed")
        if command[:3] == ["git", "worktree", "remove"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    config = SupervisorConfig(repo_path=repo, output_dir=repo / ".blackhole-agent" / "supervisor")
    record = run_wake_once(config, command_runner=runner)

    assert record.returncode == 3
    assert record.commit_result is None
    assert record.promotion_result is None
    assert not any(call[0][:2] == ["git", "commit"] for call in calls)
    assert not any(call[0][:2] == ["git", "merge"] for call in calls)
