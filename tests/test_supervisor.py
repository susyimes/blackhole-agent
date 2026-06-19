import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from blackhole_agent.supervisor import (
    CLAUDE_SDK_PERMISSION_MODE_ENV,
    SupervisorConfig,
    build_claude_sdk_permission_preflight,
    build_provider_config_preflight,
    build_runtime_startup_preflight,
    build_upgrade_version_preflight,
    build_wake_command,
    create_candidate_worktree,
    run_health_checks,
    promote_candidate,
    run_startup_health_check,
    run_wake_once,
    supervisor_runner_status_from_heartbeat,
    validate_supervisor_config,
)
from blackhole_agent.tool_routing import ToolDescriptor


def test_build_wake_command_launches_one_shot_child(tmp_path):
    config = SupervisorConfig(
        repo_path=tmp_path,
        output_dir=tmp_path / "supervisor",
        evolution_mode="codex",
        model="gpt-5.5",
        extra_instruction="prefer tests",
    )

    command = build_wake_command(config)

    assert command[:3] == [sys.executable, "-m", "blackhole_agent.github_growth"]
    assert "--interval-seconds" not in command
    assert command[command.index("--evolution-mode") : command.index("--evolution-mode") + 2] == [
        "--evolution-mode",
        "codex",
    ]
    assert "--allow-claude-sdk-auto-permission-mode" in command
    assert command[command.index("--trend-query") + 1] == "agent language:Python"
    assert command[command.index("--output-dir") + 1] == str(tmp_path / "supervisor" / "growth")
    assert command[command.index("--repo-path") + 1] == str(tmp_path)
    assert command[command.index("--proposal-mode") + 1] == "hybrid"
    assert command[command.index("--proposal-timeout-seconds") + 1] == "180"
    assert Path(command[command.index("--self-model-path") + 1]).parts == ("docs", "self-model.md")
    assert command[command.index("--model") + 1] == "gpt-5.5"
    assert "--require-codex-route" in command
    assert "--force-evolve" in command
    assert "--ignore-user-config" in command
    extra_instruction = command[command.index("--extra-instruction") + 1]
    assert "size them by evidence, benefit, rollback coverage, and validation coverage rather than by smallness" in extra_instruction
    assert "allow broad local change sets when they remain auditable" in extra_instruction
    assert "prefer tests" in extra_instruction


def test_supervisor_preserves_long_nested_candidate_paths_in_worktree_and_child_command(tmp_path):
    repo = tmp_path / "repo-with-local-agent-controller"
    repo.mkdir()
    worktree_parent = (
        tmp_path
        / ".blackhole-agent-blackhole-worktrees"
        / "local-filesystem-regression"
        / "deeply-nested-candidate-parent"
    )
    pass_id = "20260616T133522Z-path-truncation-regression"
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        candidate_path = Path(command[4])
        candidate_path.mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0, stdout="prepared\n", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=repo / ".blackhole-agent" / "supervisor",
        worktree_parent_dir=worktree_parent,
    )
    worktree_path, completed = create_candidate_worktree(config, pass_id, command_runner=runner)
    child_command = build_wake_command(config, repo_path=worktree_path)

    assert completed.returncode == 0
    assert worktree_path == worktree_parent / pass_id
    assert calls[0][0] == ["git", "worktree", "add", "--detach", str(worktree_path), "main"]
    assert calls[0][1]["cwd"] == repo
    assert child_command[child_command.index("--repo-path") + 1] == str(worktree_path)
    assert child_command[child_command.index("--output-dir") + 1] == str(repo / ".blackhole-agent" / "supervisor" / "growth")
    child_repo_path = child_command[child_command.index("--repo-path") + 1].replace("\\", "/")
    assert child_repo_path.startswith(str(tmp_path).replace("\\", "/"))
    assert not child_repo_path.startswith(f"/{worktree_path.name}/")


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
    activation = json.loads((output_dir / "latest-activation.json").read_text(encoding="utf-8"))
    assert latest["promotion_result"]["promoted"] is True
    assert latest["promotion_result"]["pushed"] is True
    assert heartbeat["last_promoted"] is True
    assert heartbeat["last_pushed"] is True
    assert heartbeat["last_restart_requested"] is True
    assert heartbeat["runner_liveness"]["status"] == "runner_asleep"
    assert heartbeat["runner_liveness"]["controller_visible_status"] == "asleep"
    assert restart_request["target_head"] == "cand123"
    assert activation["reason"] == "promotion_applied"
    assert activation["current_head"] == "cand123"
    assert activation["previous_head"] == "base123"


def test_supervisor_runner_liveness_marks_reconnected_idle_runner_as_asleep(tmp_path):
    heartbeat_path = tmp_path / "latest-supervisor-heartbeat.json"
    heartbeat = {
        "last_pass_id": "20260617T040000Z",
        "last_finished_at": "2026-06-17T04:00:00Z",
        "last_effective_returncode": 0,
    }

    status = supervisor_runner_status_from_heartbeat(
        heartbeat_path,
        heartbeat=heartbeat,
        interval_seconds=3600,
        now=datetime(2026, 6, 17, 4, 10, tzinfo=timezone.utc),
        controller_connected=True,
    )

    assert status.status == "runner_asleep"
    assert status.controller_visible_status == "asleep"
    assert status.reason == "between_scheduled_wakes"
    assert status.active_child_count == 0
    assert status.active_child_sessions == []
    assert status.next_wake_due_at == "2026-06-17T05:00:00Z"
    assert "asleep" in status.user_visible_message


def test_supervisor_runner_liveness_surfaces_active_children_instead_of_sleeping(tmp_path):
    heartbeat_path = tmp_path / "latest-supervisor-heartbeat.json"
    heartbeat = {
        "last_pass_id": "20260617T040000Z",
        "last_finished_at": "2026-06-17T04:00:00Z",
        "last_effective_returncode": 0,
        "child_sessions": [
            {
                "id": "child-a",
                "state": "running",
                "busy": True,
                "current_task_status": "searching",
                "pending_elicitations_count": 0,
            },
            {
                "id": "child-b",
                "state": "sleeping",
                "busy": False,
                "current_task_status": "idle",
                "pending_elicitations_count": 0,
            },
            {
                "id": "child-c",
                "state": "sleeping",
                "busy": False,
                "pending_elicitations_count": 1,
            },
        ],
    }

    status = supervisor_runner_status_from_heartbeat(
        heartbeat_path,
        heartbeat=heartbeat,
        interval_seconds=3600,
        now=datetime(2026, 6, 17, 4, 10, tzinfo=timezone.utc),
        controller_connected=True,
    )

    assert status.status == "child_agents_active"
    assert status.controller_visible_status == "children_active"
    assert status.reason == "active_child_sessions"
    assert status.active_child_count == 2
    assert status.child_status_counts == {"running": 1, "sleeping": 2}
    assert [session["id"] for session in status.active_child_sessions] == ["child-a", "child-c"]
    assert "2 child agents active" in status.user_visible_message


def test_supervisor_runner_liveness_surfaces_terminating_children_until_cleanup_finishes(tmp_path):
    heartbeat = {
        "last_pass_id": "20260618T223207Z",
        "last_finished_at": "2026-06-18T22:32:07Z",
        "last_effective_returncode": 0,
        "child_sessions": [
            {
                "id": "terminating-cli-transport",
                "pass_id": "20260618T223207Z",
                "state": "terminating",
                "busy": False,
                "current_task_status": "",
                "pending_elicitations_count": 0,
            }
        ],
    }

    status = supervisor_runner_status_from_heartbeat(
        tmp_path / "latest-supervisor-heartbeat.json",
        heartbeat=heartbeat,
        now=datetime(2026, 6, 18, 22, 40, tzinfo=timezone.utc),
    )

    assert status.status == "child_agents_active"
    assert status.controller_visible_status == "children_active"
    assert status.reason == "active_child_sessions"
    assert status.active_child_count == 1
    assert status.active_child_sessions == [
        {
            "id": "terminating-cli-transport",
            "status": "terminating",
            "busy": False,
            "current_task_status": "",
            "pending_elicitations_count": 0,
        }
    ]


def test_supervisor_runner_liveness_ignores_pending_children_from_other_pass(tmp_path):
    heartbeat = {
        "last_pass_id": "20260617T054315Z",
        "last_finished_at": "2026-06-17T05:43:15Z",
        "last_effective_returncode": 0,
        "active_child_count": 1,
        "child_sessions": [
            {
                "id": "stale-pending-card",
                "pass_id": "20260617T044315Z",
                "state": "awaiting_user",
                "pending_elicitations_count": 1,
            },
            {
                "id": "current-idle-child",
                "pass_id": "20260617T054315Z",
                "state": "sleeping",
                "current_task_status": "idle",
                "pending_elicitations_count": 0,
            },
        ],
    }

    status = supervisor_runner_status_from_heartbeat(
        tmp_path / "latest-supervisor-heartbeat.json",
        heartbeat=heartbeat,
        now=datetime(2026, 6, 17, 5, 50, tzinfo=timezone.utc),
    )

    assert status.status == "runner_asleep"
    assert status.reason == "between_scheduled_wakes"
    assert status.active_child_count == 0
    assert status.child_status_counts == {"sleeping": 1}
    assert status.active_child_sessions == []


def test_supervisor_runner_liveness_counts_nested_child_sessions(tmp_path):
    heartbeat = {
        "last_pass_id": "20260617T040000Z",
        "last_finished_at": "2026-06-17T04:00:00Z",
        "last_effective_returncode": 0,
        "child_sessions": {
            "child-a": {
                "status": "sleeping",
                "children": {
                    "grandchild-a": {
                        "status": "busy",
                        "current_task_status": "validating",
                    }
                },
            }
        },
    }

    status = supervisor_runner_status_from_heartbeat(
        tmp_path / "latest-supervisor-heartbeat.json",
        heartbeat=heartbeat,
        now=datetime(2026, 6, 17, 4, 10, tzinfo=timezone.utc),
    )

    assert status.status == "child_agents_active"
    assert status.active_child_count == 1
    assert status.child_status_counts == {"sleeping": 1, "busy": 1}
    assert status.active_child_sessions[0]["id"] == "grandchild-a"


def test_supervisor_runner_liveness_distinguishes_disconnect_from_asleep(tmp_path):
    heartbeat_path = tmp_path / "latest-supervisor-heartbeat.json"
    heartbeat = {
        "last_pass_id": "20260617T040000Z",
        "last_finished_at": "2026-06-17T04:00:00Z",
        "last_effective_returncode": 0,
    }

    status = supervisor_runner_status_from_heartbeat(
        heartbeat_path,
        heartbeat=heartbeat,
        now=datetime(2026, 6, 17, 4, 10, tzinfo=timezone.utc),
        controller_connected=False,
    )

    assert status.status == "controller_disconnected"
    assert status.controller_visible_status == "disconnected"
    assert status.reason == "controller_not_connected"


def test_supervisor_runner_liveness_marks_missing_or_stale_heartbeat_unavailable(tmp_path):
    heartbeat_path = tmp_path / "latest-supervisor-heartbeat.json"

    missing = supervisor_runner_status_from_heartbeat(
        heartbeat_path,
        now=datetime(2026, 6, 17, 4, 10, tzinfo=timezone.utc),
    )
    stale = supervisor_runner_status_from_heartbeat(
        heartbeat_path,
        heartbeat={
            "last_pass_id": "20260617T010000Z",
            "last_finished_at": "2026-06-17T01:00:00Z",
            "last_effective_returncode": 0,
        },
        interval_seconds=3600,
        now=datetime(2026, 6, 17, 4, 10, tzinfo=timezone.utc),
    )

    assert missing.status == "runner_unavailable"
    assert missing.reason == "missing_heartbeat"
    assert stale.status == "runner_unavailable"
    assert stale.reason == "stale_or_invalid_heartbeat"


def test_supervisor_runner_liveness_surfaces_failed_last_pass(tmp_path):
    status = supervisor_runner_status_from_heartbeat(
        tmp_path / "latest-supervisor-heartbeat.json",
        heartbeat={
            "last_pass_id": "20260617T040000Z",
            "last_finished_at": "2026-06-17T04:00:00Z",
            "last_effective_returncode": 7,
        },
        now=datetime(2026, 6, 17, 4, 10, tzinfo=timezone.utc),
    )

    assert status.status == "runner_failed"
    assert status.controller_visible_status == "failed"
    assert status.last_effective_returncode == 7


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


def test_run_health_checks_isolates_candidate_import_environment(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "outer" / ".venv"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "outer" / "src"))
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        seen["cwd"] = Path(kwargs["cwd"])
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=repo / ".blackhole-agent" / "supervisor",
        health_commands=("uv run pytest",),
    )
    results = run_health_checks(config, repo, command_runner=runner)

    assert results[0].returncode == 0
    assert seen["command"] == ["uv", "run", "pytest"]
    assert seen["cwd"] == repo
    assert "VIRTUAL_ENV" not in seen["env"]
    assert seen["env"]["PYTHONPATH"] == str(repo / "src")
    assert seen["env"]["UV_PROJECT_ENVIRONMENT"] == str(output_dir / "health-venv")


def test_run_health_checks_keeps_candidate_worktree_on_its_own_uv_environment(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    candidate = tmp_path / "candidate"
    repo.mkdir()
    candidate.mkdir()
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "inherited-health-venv")
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        seen["cwd"] = Path(kwargs["cwd"])
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=repo / ".blackhole-agent" / "supervisor",
        health_commands=("uv run pytest",),
    )
    results = run_health_checks(config, candidate, command_runner=runner)

    assert results[0].returncode == 0
    assert seen["command"] == ["uv", "run", "pytest"]
    assert seen["cwd"] == candidate
    assert "UV_PROJECT_ENVIRONMENT" not in seen["env"]


def test_run_health_checks_uses_dedicated_main_worktree_health_venv(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=output_dir,
        health_commands=("uv run pytest",),
    )
    results = run_health_checks(config, repo, command_runner=runner)

    assert results[0].returncode == 0
    assert seen["command"] == ["uv", "run", "pytest"]
    assert seen["env"]["UV_PROJECT_ENVIRONMENT"] == str(output_dir / "health-venv")


def test_provider_config_preflight_reports_missing_required_token_without_value(tmp_path, monkeypatch):
    monkeypatch.delenv("BLACKHOLE_TEST_TOKEN", raising=False)
    config = SupervisorConfig(
        repo_path=tmp_path,
        token_env="BLACKHOLE_TEST_TOKEN",
        require_token_env=True,
    )

    preflight = build_provider_config_preflight(config)

    assert preflight["ok"] is False
    assert preflight["token_env_name"] == "BLACKHOLE_TEST_TOKEN"
    assert preflight["token_env_name_recorded"] is True
    assert preflight["token_env_present"] is False
    assert preflight["token_env_usable"] is False
    assert preflight["token_env_quality"] == "absent"
    assert preflight["token_value_recorded"] is False
    assert preflight["diagnostics"] == [
        "required token environment variable is not set or empty",
        "codex mode requires an explicit --model or --profile to avoid implicit provider fallback",
    ]
    assert preflight["recovery_hints"] == [
        {
            "code": "set_required_token_env",
            "scope": "github_token",
            "action": "set the required GitHub token environment variable before supervisor startup",
            "env_names": ["BLACKHOLE_TEST_TOKEN"],
            "value_recorded": False,
        },
        {
            "code": "explicit_codex_route_required",
            "scope": "codex_route",
            "action": "configure --model or --profile before codex mode starts, or explicitly allow the default route",
            "env_names": [],
            "value_recorded": False,
        },
    ]


def test_provider_config_preflight_rejects_placeholder_required_token_without_value(tmp_path, monkeypatch):
    placeholder_token = "dummy-github-token"
    monkeypatch.setenv("BLACKHOLE_TEST_TOKEN", placeholder_token)
    config = SupervisorConfig(
        repo_path=tmp_path,
        token_env="BLACKHOLE_TEST_TOKEN",
        require_token_env=True,
        model="gpt-5.5",
    )

    preflight = build_provider_config_preflight(config)

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["token_env_present"] is True
    assert preflight["token_env_usable"] is False
    assert preflight["token_env_quality"] == "placeholder"
    assert preflight["token_value_recorded"] is False
    assert preflight["diagnostics"] == ["required token environment variable is a placeholder value"]
    assert preflight["recovery_hints"] == [
        {
            "code": "replace_required_token_placeholder",
            "scope": "github_token",
            "action": "replace the placeholder GitHub token value with a real credential or unset it",
            "env_names": ["BLACKHOLE_TEST_TOKEN"],
            "value_recorded": False,
        }
    ]
    assert placeholder_token not in rendered


def test_provider_config_preflight_never_records_token_value(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKHOLE_TEST_TOKEN", "secret-token-value")
    config = SupervisorConfig(
        repo_path=tmp_path,
        token_env="BLACKHOLE_TEST_TOKEN",
        require_token_env=True,
        model="gpt-5.5",
    )

    preflight = build_provider_config_preflight(config)

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is True
    assert preflight["token_env_present"] is True
    assert preflight["token_env_usable"] is True
    assert preflight["token_env_quality"] == "provided"
    assert preflight["token_value_recorded"] is False
    assert preflight["codex"]["route_selector"] == "model"
    assert "secret-token-value" not in rendered


def test_runtime_startup_preflight_rejects_placeholder_ambient_provider_env_without_leakage(tmp_path):
    placeholder_token = "sk-dummy-openai-token"
    config = SupervisorConfig(
        repo_path=tmp_path,
        model="gpt-5.5",
    )

    preflight = build_runtime_startup_preflight(
        config,
        env={"OPENAI_API_KEY": placeholder_token},
    )

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["provider_config"]["codex"]["ambient_openai"]["api_key_quality"] == "placeholder"
    assert preflight["diagnostics"] == [
        "OPENAI_API_KEY is a placeholder value; ambient OpenAI credentials are invalid",
    ]
    assert preflight["recovery_hints"] == [
        {
            "code": "replace_openai_placeholder_key",
            "scope": "ambient_openai",
            "action": "replace the placeholder OpenAI API key with a real credential or unset the variable",
            "env_names": ["OPENAI_API_KEY"],
            "value_recorded": False,
        }
    ]
    assert placeholder_token not in rendered


def test_provider_config_preflight_blocks_implicit_codex_route_before_scheduling(tmp_path):
    config = SupervisorConfig(repo_path=tmp_path)

    preflight = build_provider_config_preflight(config)

    assert preflight["ok"] is False
    assert preflight["codex"]["selected_provider"] == "codex_cli"
    assert preflight["codex"]["route_selector"] == "implicit_default"
    assert preflight["codex"]["profile_value_recorded"] is False
    assert preflight["diagnostics"] == [
        "codex mode requires an explicit --model or --profile to avoid implicit provider fallback"
    ]
    assert preflight["recovery_hints"][0]["code"] == "explicit_codex_route_required"


def test_claude_sdk_permission_preflight_defaults_to_auto_with_explicit_metadata(monkeypatch):
    monkeypatch.delenv(CLAUDE_SDK_PERMISSION_MODE_ENV, raising=False)

    preflight = build_claude_sdk_permission_preflight()

    assert preflight["ok"] is True
    assert preflight["permission_mode"] == "auto"
    assert preflight["permission_mode_source"] == "default"
    assert preflight["permission_mode_recorded"] is True
    assert preflight["permission_mode_env_present"] is False
    assert preflight["auto_mode"] is True
    assert preflight["auto_mode_local_enforcement"] is False
    assert "bypassPermissions" in preflight["valid_permission_modes"]


def test_claude_sdk_permission_preflight_accepts_env_override_without_secret_leakage(monkeypatch):
    monkeypatch.setenv(CLAUDE_SDK_PERMISSION_MODE_ENV, "plan")

    preflight = build_claude_sdk_permission_preflight()

    assert preflight["ok"] is True
    assert preflight["permission_mode"] == "plan"
    assert preflight["permission_mode_source"] == "env"
    assert preflight["permission_mode_env_present"] is True
    assert preflight["permission_mode_env_value_recorded"] is True


def test_claude_sdk_permission_preflight_blocks_auto_when_runtime_policy_disallows_it(monkeypatch):
    monkeypatch.delenv(CLAUDE_SDK_PERMISSION_MODE_ENV, raising=False)

    preflight = build_claude_sdk_permission_preflight(allow_auto_mode=False)

    assert preflight["ok"] is False
    assert preflight["permission_mode"] == "auto"
    assert preflight["auto_mode_allowed"] is False
    assert preflight["diagnostics"] == ["Claude SDK permission mode 'auto' is disallowed by runtime policy"]


def test_claude_sdk_permission_preflight_does_not_echo_invalid_permission_mode(monkeypatch):
    secret_shaped_input = "sk-live-secret-token"
    monkeypatch.setenv(CLAUDE_SDK_PERMISSION_MODE_ENV, secret_shaped_input)

    preflight = build_claude_sdk_permission_preflight()

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["permission_mode"] is None
    assert preflight["permission_mode_recorded"] is False
    assert preflight["permission_mode_env_value_recorded"] is False
    assert preflight["diagnostics"] == ["Claude SDK permission mode must be one of the supported SDK modes"]
    assert secret_shaped_input not in rendered


def test_provider_config_preflight_includes_claude_sdk_permission_gate(tmp_path, monkeypatch):
    monkeypatch.delenv(CLAUDE_SDK_PERMISSION_MODE_ENV, raising=False)
    config = SupervisorConfig(
        repo_path=tmp_path,
        model="gpt-5.5",
        allow_claude_sdk_auto_permission_mode=False,
    )

    preflight = build_provider_config_preflight(config)

    assert preflight["ok"] is False
    assert preflight["codex"]["ok"] is True
    assert preflight["claude_sdk"]["permission_mode"] == "auto"
    assert preflight["diagnostics"] == ["Claude SDK permission mode 'auto' is disallowed by runtime policy"]
    assert preflight["recovery_hints"] == [
        {
            "code": "select_claude_sdk_permission_mode",
            "scope": "claude_sdk",
            "action": "configure a non-auto Claude SDK permission mode accepted by runtime policy",
            "env_names": [CLAUDE_SDK_PERMISSION_MODE_ENV],
            "value_recorded": False,
        }
    ]


def test_validate_supervisor_config_rejects_malformed_token_env_before_scheduling(tmp_path):
    config = SupervisorConfig(repo_path=tmp_path, token_env="GITHUB TOKEN", model="gpt-5.5")

    with pytest.raises(ValueError, match="runtime startup preflight failed"):
        validate_supervisor_config(config)


def test_provider_config_preflight_does_not_echo_malformed_token_env_text(tmp_path):
    secret_shaped_input = "sk-live-secret-token"
    config = SupervisorConfig(repo_path=tmp_path, token_env=secret_shaped_input, model="gpt-5.5")

    preflight = build_provider_config_preflight(config)

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["token_env_name"] is None
    assert preflight["token_env_name_recorded"] is False
    assert preflight["token_env_valid"] is False
    assert preflight["diagnostics"] == ["token_env must be a valid environment variable name"]
    assert preflight["recovery_hints"] == [
        {
            "code": "fix_token_env_name",
            "scope": "github_token",
            "action": "replace token_env with a valid environment variable name",
            "env_names": [],
            "value_recorded": False,
        }
    ]
    assert secret_shaped_input not in rendered


def test_validate_supervisor_config_does_not_echo_malformed_token_env_text(tmp_path):
    secret_shaped_input = "sk-live-secret-token"
    config = SupervisorConfig(repo_path=tmp_path, token_env=secret_shaped_input, model="gpt-5.5")

    with pytest.raises(ValueError) as error:
        validate_supervisor_config(config)

    assert "token_env must be a valid environment variable name" in str(error.value)
    assert secret_shaped_input not in str(error.value)


def test_runtime_startup_preflight_combines_provider_and_tool_gaps_without_token_leakage(tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKHOLE_TEST_TOKEN", "secret-token-value")
    config = SupervisorConfig(
        repo_path=tmp_path,
        token_env="BLACKHOLE_TEST_TOKEN",
        require_token_env=True,
        model="gpt-5.5",
        required_tool_names=("local_memory", "browser"),
    )

    preflight = build_runtime_startup_preflight(
        config,
        tool_descriptors=(
            ToolDescriptor(name="local_memory", provider="local"),
            ToolDescriptor(name="security_review", provider="local", risk_flags=("offensive-behavior",)),
            ToolDescriptor(name="remote_browser", provider="mcp"),
        ),
    )

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["provider_config"]["ok"] is True
    assert preflight["provider_config"]["token_env_present"] is True
    assert preflight["tool_routing"]["missing_required_tool_names"] == ["browser"]
    assert preflight["diagnostics"] == [
        "required tool is not executable or is unavailable: browser",
    ]
    assert preflight["recovery_hints"] == [
        {
            "code": "make_required_tool_available",
            "scope": "tool_routing",
            "action": "configure or expose the required local tool before startup",
            "tool_name": "browser",
            "value_recorded": False,
        }
    ]
    assert preflight["token_value_recorded"] is False
    assert "secret-token-value" not in rendered


def test_runtime_startup_preflight_aggregates_provider_recovery_without_secret_values(tmp_path):
    placeholder_token = "sk-dummy-openai-token"
    config = SupervisorConfig(repo_path=tmp_path)

    preflight = build_runtime_startup_preflight(
        config,
        env={"OPENAI_API_KEY": placeholder_token},
    )

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert [hint["code"] for hint in preflight["recovery_hints"]] == [
        "explicit_codex_route_required",
        "replace_openai_placeholder_key",
    ]
    assert all(hint["value_recorded"] is False for hint in preflight["recovery_hints"])
    assert placeholder_token not in rendered


def test_upgrade_version_preflight_allows_newer_stable_upgrade():
    preflight = build_upgrade_version_preflight(
        current_version="1.4.2",
        latest_version="1.5.0",
    )

    assert preflight["ok"] is True
    assert preflight["outcome"] == "upgrade_needed"
    assert preflight["should_upgrade"] is True
    assert preflight["upgrade_action_permitted"] is True
    assert preflight["diagnostics"] == []


def test_upgrade_version_preflight_reports_already_current_without_action():
    preflight = build_upgrade_version_preflight(
        current_version="v1.5",
        latest_version="1.5.0",
    )

    assert preflight["ok"] is True
    assert preflight["outcome"] == "already_current"
    assert preflight["should_upgrade"] is False
    assert preflight["upgrade_action_permitted"] is False
    assert preflight["diagnostics"] == ["current_version already matches latest_version"]


def test_upgrade_version_preflight_blocks_downgrade():
    preflight = build_upgrade_version_preflight(
        current_version="2.0.0",
        latest_version="1.9.9",
    )

    assert preflight["ok"] is False
    assert preflight["outcome"] == "downgrade_blocked"
    assert preflight["should_upgrade"] is False
    assert preflight["upgrade_action_permitted"] is False
    assert preflight["diagnostics"] == ["latest_version is older than current_version"]


def test_upgrade_version_preflight_blocks_dev_versions_by_default():
    preflight = build_upgrade_version_preflight(
        current_version="1.5.0",
        latest_version="1.6.0-dev.1",
    )

    assert preflight["ok"] is False
    assert preflight["outcome"] == "dev_version_blocked"
    assert preflight["should_upgrade"] is False
    assert preflight["upgrade_action_permitted"] is False
    assert preflight["current_version_is_dev"] is False
    assert preflight["latest_version_is_dev"] is True
    assert preflight["diagnostics"] == ["development or preview versions require explicit opt-in before upgrade"]


def test_startup_health_success_records_manual_activation_baseline(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    output_dir.mkdir(parents=True)
    (output_dir / "latest-activation.json").write_text(
        json.dumps(
            {
                "current_branch": "main",
                "current_head": "stable123",
                "previous_branch": "main",
                "previous_head": "older123",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        if command[:2] == ["uv", "run"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="hotfix123\n", stderr="")
        if command == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=output_dir,
        health_commands=("uv run pytest",),
    )
    record = run_startup_health_check(config, command_runner=runner)

    assert record.returncode == 0
    activation = json.loads((output_dir / "latest-activation.json").read_text(encoding="utf-8"))
    assert activation["reason"] == "startup_health_passed"
    assert activation["current_head"] == "hotfix123"
    assert activation["previous_head"] == "stable123"


def test_startup_health_success_bootstraps_activation_from_latest_promotion(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    output_dir.mkdir(parents=True)
    (output_dir / "latest-supervisor-pass.json").write_text(
        json.dumps(
            {
                "promotion_result": {
                    "target_before": "older123",
                    "target_after": "stable123",
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        if command[:2] == ["uv", "run"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="hotfix123\n", stderr="")
        if command == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="main\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    config = SupervisorConfig(
        repo_path=repo,
        output_dir=output_dir,
        health_commands=("uv run pytest",),
    )
    record = run_startup_health_check(config, command_runner=runner)

    assert record.returncode == 0
    activation = json.loads((output_dir / "latest-activation.json").read_text(encoding="utf-8"))
    assert activation["current_head"] == "hotfix123"
    assert activation["previous_head"] == "stable123"


def test_startup_health_failure_rolls_back_to_activation_previous_head(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    output_dir.mkdir(parents=True)
    (output_dir / "latest-activation.json").write_text(
        json.dumps(
            {
                "current_branch": "main",
                "current_head": "bad123",
                "previous_branch": "main",
                "previous_head": "stable123",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    calls = []

    def runner(command, **kwargs):
        calls.append((command, Path(kwargs["cwd"])))
        if command[:2] == ["uv", "run"]:
            return subprocess.CompletedProcess(command, 9, stdout="", stderr="broken startup")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="bad123\n", stderr="")
        if command == ["git", "reset", "--hard", "stable123"]:
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
    assert record.rollback_target == "stable123"
    assert ["git", "reset", "--hard", "stable123"] in [call[0] for call in calls]


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

    config = SupervisorConfig(repo_path=repo, output_dir=repo / ".blackhole-agent" / "supervisor", model="gpt-5.5")
    record = run_wake_once(config, command_runner=runner)

    assert record.returncode == 3
    assert record.commit_result is None
    assert record.promotion_result is None
    assert not any(call[0][:2] == ["git", "commit"] for call in calls)
    assert not any(call[0][:2] == ["git", "merge"] for call in calls)
