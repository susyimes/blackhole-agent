import json
import os
import subprocess
from pathlib import Path

import pytest

from blackhole_agent.unbound import (
    DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
    KernelTurnResult,
    PublicationResult,
    TurnDecision,
    UnboundMission,
    build_turn_prompt,
    continuous_loop_state_path,
    create_mission,
    evaluate_milestone,
    extract_json_decision,
    git_head,
    invoke_kernel_turn,
    load_mission,
    mission_turn_lock,
    publish_lineage,
    resolve_unbound_kernel,
    run_continuous_loop,
    run_unbound_turn,
    save_mission,
)


def init_repository(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Blackhole Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "blackhole@example.invalid"], cwd=path, check=True)
    (path / "src").mkdir()
    (path / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=path, check=True, capture_output=True, text=True)


def make_state(tmp_path: Path, **overrides) -> UnboundMission:
    values = {
        "schema_version": 1,
        "mission_id": "mission-1",
        "created_at": "2026-07-28T00:00:00Z",
        "updated_at": "2026-07-28T00:00:00Z",
        "repo_path": str(tmp_path),
        "workspace_path": str(tmp_path),
        "branch": "unbound/test",
        "target_branch": "main",
        "goal": "Create a real end-to-end capability.",
        "done_when": "A runnable behavior proves the capability.",
        "stage": "execution",
        "base_head": "abc",
        "last_milestone_head": "abc",
    }
    values.update(overrides)
    return UnboundMission(**values)


def decision_payload(status: str, **overrides) -> str:
    payload = {
        "status": status,
        "mission_goal": "",
        "done_when": "",
        "summary": "Implemented a working capability path.",
        "strategy": "Replace the legacy seam with a direct implementation.",
        "next_step": "Exercise the behavior against a realistic fixture.",
        "capability_delta": "",
        "outcome_evidence": [],
        "validation": [],
        "done_when_met": False,
        "commit_message": "",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_prompt_is_compact_outcome_oriented_and_single_agent(tmp_path):
    state = make_state(
        tmp_path,
        recent_turns=[
            {
                "iteration": index,
                "effective_status": "continue",
                "summary": "x" * 4_000,
                "next_step": "continue",
            }
            for index in range(20)
        ],
    )
    prompt = build_turn_prompt(
        state,
        {
            "head": "abc",
            "status": " M src/seed.py",
            "diff_stat": "src/seed.py | 5 +++++",
            "recent_commits": "abc seed",
        },
        state_path=tmp_path / "state.json",
    )

    assert len(prompt) < 12_100
    assert "single long-running agent" in prompt
    assert "Do not spawn, delegate to, fork, or simulate subagents" in prompt
    assert "Tests, lint, documents, and artifacts" in prompt
    assert "skill_route_discovery_capability_pipeline" not in prompt
    assert prompt.count('"iteration"') <= 8


def test_extract_json_decision_uses_last_valid_object():
    message = 'note {"status":"continue"}\n```json\n{"status":"milestone","summary":"done"}\n```'

    assert extract_json_decision(message) == {"status": "milestone", "summary": "done"}


def test_milestone_gate_rejects_paperwork_and_accepts_behavior_change():
    decision = TurnDecision.from_payload(
        json.loads(
            decision_payload(
                "milestone",
                capability_delta="The controller can now execute a durable mission.",
                outcome_evidence=["demo command produced the expected result"],
                validation=[{"command": "python demo.py", "exit_code": 0, "summary": "worked"}],
            )
        )
    )

    rejected = evaluate_milestone(
        decision,
        changed_paths=["docs/design.md", "tests/test_design.py", "artifacts/report.json"],
    )
    accepted = evaluate_milestone(
        decision,
        changed_paths=["src/blackhole_agent/unbound.py", "tests/test_unbound.py"],
    )

    assert rejected.accepted is False
    assert "changes are limited to docs, tests, artifacts, or controller state" in rejected.reasons
    assert accepted.accepted is True
    assert accepted.behavior_paths == ("src/blackhole_agent/unbound.py",)


def test_complete_gate_rejects_failed_machine_checkable_done_when():
    """Complete status must fail when structured done_when predicates do not hold."""

    repo = Path(__file__).resolve().parents[1]
    decision = TurnDecision.from_payload(
        json.loads(
            decision_payload(
                "complete",
                capability_delta="Evidence-bound completion path.",
                outcome_evidence=["contract evaluator ran"],
                validation=[{"command": "python demo.py", "exit_code": 0, "summary": "worked"}],
                done_when_met=True,
                done_when="min_capabilities:999999",
            )
        )
    )
    rejected = evaluate_milestone(
        decision,
        changed_paths=["src/blackhole_agent/unbound.py"],
        workspace=repo,
        mission_done_when="min_capabilities:999999",
    )
    accepted = evaluate_milestone(
        decision,
        changed_paths=["src/blackhole_agent/unbound.py"],
        workspace=repo,
        mission_done_when="min_capabilities:1; capability_exists:repo.import-health; no_skill_route",
    )
    assert rejected.accepted is False
    assert any("machine-checkable done_when failed" in reason for reason in rejected.reasons)
    assert accepted.accepted is True


def test_unbound_grok_turn_keeps_one_persistent_agent_with_full_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.grok_cli.shutil.which", lambda _: "C:/tools/grok.exe")
    seen = []

    def runner(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"text": decision_payload("continue"), "stopReason": "EndTurn"}),
            stderr="",
        )

    state = make_state(
        tmp_path,
        kernel="grok",
        model="grok-4.5",
        session_id="00000000-0000-0000-0000-000000000123",
    )
    first = invoke_kernel_turn(state, "work", tmp_path / "turn-1", command_runner=runner)
    state.session_started = True
    second = invoke_kernel_turn(state, "continue", tmp_path / "turn-2", command_runner=runner)

    assert first.session_id == state.session_id
    assert "--no-subagents" in seen[0]
    assert "--no-memory" not in seen[0]
    assert "--disable-web-search" not in seen[0]
    assert "--deny" not in seen[0]
    assert seen[0][seen[0].index("--sandbox") + 1] == "off"
    assert seen[0][seen[0].index("--session-id") + 1] == state.session_id
    assert seen[1][seen[1].index("--resume") + 1] == state.session_id
    assert second.kernel == "grok"


def test_unbound_codex_turn_records_session_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.codex_cli.shutil.which", lambda _: "C:/tools/codex.exe")
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        last_message_path = Path(command[command.index("--output-last-message") + 1])
        last_message_path.write_text(decision_payload("continue"), encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"thread.started","thread_id":"codex-session-123"}\n',
            stderr="",
        )

    state = make_state(tmp_path, kernel="codex", model="gpt-5.6")
    first = invoke_kernel_turn(state, "work", tmp_path / "turn-1", command_runner=runner)
    state.session_id = first.session_id
    state.session_started = True
    invoke_kernel_turn(state, "continue", tmp_path / "turn-2", command_runner=runner)

    assert first.session_id == "codex-session-123"
    assert "--ephemeral" not in commands[0]
    assert "--json" in commands[0]
    assert "--dangerously-bypass-approvals-and-sandbox" in commands[0]
    assert commands[1][1:4] == ["exec", "resume", "codex-session-123"]


def test_unbound_kimi_turn_records_native_session_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: "C:/tools/kimi.exe")
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        stdout = "\n".join(
            [
                json.dumps({"role": "assistant", "content": decision_payload("continue")}),
                json.dumps(
                    {
                        "role": "meta",
                        "type": "session.resume_hint",
                        "session_id": "session-kimi-123",
                    }
                ),
            ]
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    state = make_state(tmp_path, kernel="kimi")
    first = invoke_kernel_turn(state, "work", tmp_path / "turn-1", command_runner=runner)
    state.session_id = first.session_id
    state.session_started = True
    second = invoke_kernel_turn(state, "continue", tmp_path / "turn-2", command_runner=runner)

    assert first.kernel == "kimi"
    assert first.session_id == "session-kimi-123"
    assert second.session_id == "session-kimi-123"
    assert "--session" not in commands[0]
    assert commands[1][commands[1].index("--session") + 1] == "session-kimi-123"
    assert "--auto" not in commands[0]
    assert "--plan" not in commands[0]
    assert commands[0][commands[0].index("--output-format") + 1] == "stream-json"
    assert "work" not in first.command


def test_continuing_work_persists_without_commit_until_capability_milestone(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    state_path = create_mission(
        repo_path=repo,
        goal="Add a runnable capability.",
        done_when="The new module runs and is validated.",
        worktree_parent=tmp_path / "worktrees",
    )
    initial_state = load_mission(state_path)
    workspace = Path(initial_state.workspace_path)
    baseline_count = int(
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    responses = [
        decision_payload("continue", summary="Implementation is substantial but not demonstrated yet."),
        decision_payload(
            "milestone",
            capability_delta="A new executable capability module now returns a verified result.",
            outcome_evidence=["src/capability.py returned CAPABILITY_OK"],
            validation=[
                {
                    "command": "python src/capability.py",
                    "exit_code": 0,
                    "summary": "printed CAPABILITY_OK",
                }
            ],
            commit_message="Add executable capability path",
        ),
    ]

    def fake_kernel(state, prompt, turn_dir, **kwargs):
        if state.iteration == 0:
            (Path(state.workspace_path) / "src" / "capability.py").write_text(
                "print('CAPABILITY_OK')\n",
                encoding="utf-8",
            )
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=responses[state.iteration],
            session_id=state.session_id,
            command=("fake-kernel",),
            result_path=str(turn_dir / "fake-result.json"),
        )

    first = run_unbound_turn(state_path, kernel_runner=fake_kernel)
    count_after_continue = int(
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    second = run_unbound_turn(state_path, kernel_runner=fake_kernel)
    final_state = load_mission(state_path)
    final_count = int(
        subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )

    assert first["effective_status"] == "continue"
    assert count_after_continue == baseline_count
    assert second["effective_status"] == "milestone"
    assert second["milestone_gate"]["accepted"] is True
    assert final_count == baseline_count + 1
    assert final_state.milestone_count == 1
    assert final_state.status == "active"
    assert final_state.last_milestone_head == second["commit_sha"]


def test_genesis_turn_can_define_the_mission_without_forcing_a_goal_at_start(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    state_path = create_mission(repo_path=repo, worktree_parent=tmp_path / "worktrees")

    def genesis_kernel(state, prompt, turn_dir, **kwargs):
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=decision_payload(
                "continue",
                mission_goal="Replace the append-only controller with a measurable execution path.",
                done_when="A real end-to-end run succeeds and legacy complexity is reduced.",
                summary="Selected the mission after inspecting the repository.",
            ),
            session_id=state.session_id,
            command=("fake-kernel",),
            result_path=str(turn_dir / "fake-result.json"),
        )

    run_unbound_turn(state_path, kernel_runner=genesis_kernel)
    state = load_mission(state_path)

    assert state.stage == "execution"
    assert state.goal.startswith("Replace the append-only controller")
    assert state.done_when.startswith("A real end-to-end run succeeds")


def test_create_mission_recovers_when_worktree_add_times_out_after_clean_checkout(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    worktrees = tmp_path / "worktrees"

    def timeout_after_checkout(command, **kwargs):
        completed = subprocess.run(command, **kwargs)
        if command[:3] == ["git", "worktree", "add"]:
            raise subprocess.TimeoutExpired(
                command,
                kwargs["timeout"],
                output=completed.stdout,
                stderr=completed.stderr,
            )
        return completed

    state_path = create_mission(
        repo_path=repo,
        worktree_parent=worktrees,
        command_runner=timeout_after_checkout,
    )
    state = load_mission(state_path)
    event = json.loads(
        (state_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    )

    assert Path(state.workspace_path).is_dir()
    assert git_head(Path(state.workspace_path)) == state.base_head
    assert event["event"] == "mission.created"
    assert event["worktree_setup_recovered"] is True


def test_continuous_loop_defaults_to_thirty_minutes():
    assert DEFAULT_CONTINUOUS_INTERVAL_SECONDS == 30 * 60


def test_mission_turn_lock_reclaims_stale_pid(tmp_path):
    state_path = tmp_path / "mission" / "state.json"
    state_path.parent.mkdir()
    lock_path = state_path.parent / "turn.lock"
    lock_path.write_text("99999999\n", encoding="utf-8")

    with mission_turn_lock(state_path):
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())

    assert not lock_path.exists()


def test_mission_turn_lock_preserves_live_owner(tmp_path):
    state_path = tmp_path / "mission" / "state.json"
    state_path.parent.mkdir()
    lock_path = state_path.parent / "turn.lock"
    lock_path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    try:
        with mission_turn_lock(state_path):
            raise AssertionError("live lock must not be acquired")
    except RuntimeError as error:
        assert "Another Unbound turn owns this mission" in str(error)
    else:
        raise AssertionError("live lock must fail closed")

    assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_continuous_loop_starts_new_genesis_missions_and_compounds_proven_heads(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    worktrees = tmp_path / "worktrees"
    created_from = []
    waits = []
    completed_heads = []

    def recording_creator(**kwargs):
        created_from.append(kwargs["target_branch"])
        return create_mission(**kwargs)

    def completing_runner(state_path, **kwargs):
        state = load_mission(state_path)
        workspace = Path(state.workspace_path)
        capability = workspace / "src" / f"capability_{state.mission_id[-8:]}.py"
        capability.write_text(f"MISSION_ID = {state.mission_id!r}\n", encoding="utf-8")
        subprocess.run(["git", "add", str(capability)], cwd=workspace, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"complete {state.mission_id}"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
        state.status = "complete"
        state.milestone_count = 1
        state.last_milestone_head = git_head(workspace)
        completed_heads.append(state.last_milestone_head)
        save_mission(state_path, state)
        return 0

    def recording_waiter(seconds, stop_path):
        waits.append(seconds)
        return False

    result = run_continuous_loop(
        repo_path=repo,
        interval_seconds=DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
        max_missions=2,
        resume_latest=False,
        worktree_parent=worktrees,
        mission_creator=recording_creator,
        mission_runner=completing_runner,
        interval_waiter=recording_waiter,
    )
    loop_state = json.loads(continuous_loop_state_path(repo).read_text(encoding="utf-8"))

    assert result == 0
    assert created_from[0] == "main"
    assert created_from[1] == completed_heads[0]
    assert waits == [1800]
    assert loop_state["mission_count"] == 2
    assert loop_state["run_count"] == 2
    assert loop_state["lineage_ref"] == completed_heads[1]
    assert loop_state["status"] == "stopped"
    assert loop_state["stop_reason"] == "max_missions_reached"


def test_continuous_loop_retries_failed_mission_creation(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    worktrees = tmp_path / "worktrees"
    create_attempts = []
    waits = []

    def flaky_creator(**kwargs):
        create_attempts.append(kwargs["target_branch"])
        if len(create_attempts) == 1:
            raise subprocess.TimeoutExpired(["git", "worktree", "add"], 900)
        return create_mission(**kwargs)

    def completing_runner(state_path, **kwargs):
        state = load_mission(state_path)
        state.status = "complete"
        save_mission(state_path, state)
        return 0

    def recording_waiter(seconds, stop_path):
        waits.append(seconds)
        return False

    result = run_continuous_loop(
        repo_path=repo,
        interval_seconds=DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
        max_missions=1,
        resume_latest=False,
        worktree_parent=worktrees,
        mission_creator=flaky_creator,
        mission_runner=completing_runner,
        interval_waiter=recording_waiter,
    )
    loop_state = json.loads(continuous_loop_state_path(repo).read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (
            repo / ".blackhole-agent" / "unbound" / "continuous-loop-events.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    failure = next(
        event
        for event in events
        if event["event"] == "continuous_loop.mission_create_failed"
    )

    assert result == 0
    assert create_attempts == ["main", "main"]
    assert waits == [1800]
    assert loop_state["mission_count"] == 1
    assert loop_state["mission_create_attempt_count"] == 2
    assert loop_state["mission_create_failure_count"] == 1
    assert loop_state["last_mission_create_error"] == ""
    assert failure["error_type"] == "TimeoutExpired"
    assert failure["base_ref"] == "main"


def test_publish_lineage_pushes_and_verifies_exact_remote_head(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    init_repository(repo)
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True, text=True)
    commit_sha = git_head(repo)

    result = publish_lineage(repo, commit_sha, str(remote), "main")
    remote_head = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert result.ok is True
    assert result.remote_before == ""
    assert result.remote_after == commit_sha
    assert remote_head == commit_sha


def test_continuous_loop_retries_failed_publication_before_creating_another_mission(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    worktrees = tmp_path / "worktrees"
    waits = []
    publish_attempts = []

    def completing_runner(state_path, **kwargs):
        state = load_mission(state_path)
        workspace = Path(state.workspace_path)
        capability = workspace / "src" / "published_capability.py"
        capability.write_text("PUBLISHED = True\n", encoding="utf-8")
        subprocess.run(["git", "add", str(capability)], cwd=workspace, check=True)
        subprocess.run(
            ["git", "commit", "-m", "complete publishable capability"],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
        )
        state.status = "complete"
        state.milestone_count = 1
        state.last_milestone_head = git_head(workspace)
        save_mission(state_path, state)
        return 0

    def flaky_publisher(repo_path, commit_sha, remote, branch, **kwargs):
        publish_attempts.append(commit_sha)
        if len(publish_attempts) == 1:
            raise RuntimeError("simulated remote failure")
        return PublicationResult(
            ok=True,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before="",
            remote_after=commit_sha,
            error="",
            command=("git", "push"),
        )

    def recording_waiter(seconds, stop_path):
        waits.append(seconds)
        return False

    result = run_continuous_loop(
        repo_path=repo,
        interval_seconds=DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
        max_missions=1,
        resume_latest=False,
        publish_remote="origin",
        worktree_parent=worktrees,
        mission_runner=completing_runner,
        lineage_publisher=flaky_publisher,
        interval_waiter=recording_waiter,
    )
    loop_state = json.loads(continuous_loop_state_path(repo).read_text(encoding="utf-8"))

    assert result == 0
    assert len(publish_attempts) == 2
    assert waits == [1800]
    assert loop_state["mission_count"] == 1
    assert loop_state["publish_attempt_count"] == 2
    assert loop_state["publish_count"] == 1
    assert loop_state["pending_publish_ref"] == ""
    assert loop_state["last_publish_error"] == ""
    assert loop_state["last_published_ref"] == publish_attempts[-1]


def test_execution_stage_turn_can_refine_done_when_before_gating(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    state_path = create_mission(
        repo_path=repo,
        goal="Ship a real capability.",
        done_when="min_capabilities:999999",
        worktree_parent=tmp_path / "worktrees",
    )

    def refining_kernel(state, prompt, turn_dir, **kwargs):
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=decision_payload(
                "continue",
                done_when="min_capabilities:1",
                summary="Refined the completion contract into the parser grammar.",
            ),
            session_id=state.session_id,
            command=("fake-kernel",),
            result_path=str(turn_dir / "fake-result.json"),
        )

    run_unbound_turn(state_path, kernel_runner=refining_kernel)
    state = load_mission(state_path)

    assert state.stage == "execution"
    assert state.done_when == "min_capabilities:1"


def test_resolve_unbound_kernel_auto_selects_installed_first_class_kernel():
    kernel, resolution = resolve_unbound_kernel(
        "auto",
        available_commands={"kimi"},
        environ={},
        platform="linux",
    )

    assert kernel == "kimi"
    assert resolution["mode"] == "auto"
    assert resolution["selected_harness"] == "kimi-cli"
    assert resolution["skipped"]["codex-cli"] == ["missing_dependency:codex"]
    assert resolution["skipped"]["grok-cli"] == ["missing_dependency:grok"]


def test_resolve_unbound_kernel_auto_prefers_catalog_priority():
    kernel, _ = resolve_unbound_kernel(
        "auto",
        available_commands={"codex", "grok", "kimi"},
        environ={},
        platform="linux",
    )
    grok_and_kimi, _ = resolve_unbound_kernel(
        "auto",
        available_commands={"grok", "kimi"},
        environ={},
        platform="linux",
    )

    assert kernel == "codex"
    assert grok_and_kimi == "grok"


def test_resolve_unbound_kernel_explicit_passthrough_and_unknown_rejected():
    assert resolve_unbound_kernel("kimi", available_commands=set(), environ={}, platform="linux") == (
        "kimi",
        {"mode": "explicit", "kernel": "kimi"},
    )

    with pytest.raises(ValueError, match="kernel must be one of"):
        resolve_unbound_kernel("not-a-kernel", available_commands=set(), environ={}, platform="linux")


def test_resolve_unbound_kernel_auto_fails_closed_with_skip_diagnostics():
    with pytest.raises(ValueError, match="no first-class CLI kernel"):
        resolve_unbound_kernel("auto", available_commands=set(), environ={}, platform="linux")


def test_create_mission_resolves_auto_kernel_and_records_resolution(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)

    state_path = create_mission(
        repo_path=repo,
        kernel="auto",
        worktree_parent=tmp_path / "worktrees",
        kernel_resolver=lambda kernel: resolve_unbound_kernel(
            kernel,
            available_commands={"grok"},
            environ={},
            platform="linux",
        ),
    )
    state = load_mission(state_path)

    assert state.kernel == "grok"
    events = [
        json.loads(line)
        for line in (state_path.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    created = next(event for event in events if event["event"] == "mission.created")
    assert created["kernel_resolution"]["mode"] == "auto"
    assert created["kernel_resolution"]["kernel"] == "grok"


def test_create_mission_rejects_unknown_kernel(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)

    with pytest.raises(ValueError, match="kernel must be one of"):
        create_mission(repo_path=repo, kernel="not-a-kernel", worktree_parent=tmp_path / "worktrees")
