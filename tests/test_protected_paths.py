import subprocess
from pathlib import Path

from blackhole_agent.protected_paths import (
    DEFAULT_PROTECTED_PATHS,
    builtin_protected_paths_gate,
    evaluate_candidate_protected_paths,
    evaluate_protected_paths_gate,
    list_changed_paths,
    load_protected_paths,
    parse_diff_listing,
    path_is_protected,
)


def _is_diff_listing(command) -> bool:
    if not isinstance(command, (list, tuple)):
        return False
    if list(command[:3]) == ["git", "diff", "--name-only"]:
        return True
    return "diff" in command and "--name-status" in command
from blackhole_agent.supervisor import SupervisorConfig, promote_candidate


def test_floor_paths_are_protected_and_unbound_is_not():
    assert path_is_protected("src/blackhole_agent/supervisor.py")
    assert path_is_protected("src/blackhole_agent/persona.py")
    assert path_is_protected("governance/size-ratchet.json")
    assert path_is_protected("pyproject.toml")
    assert not path_is_protected("src/blackhole_agent/unbound.py")
    assert not path_is_protected("src/blackhole_agent/capability_compounder.py")


def test_json_can_add_paths_but_cannot_remove_the_floor(tmp_path):
    manifest = tmp_path / "governance"
    manifest.mkdir()
    (manifest / "protected-paths.json").write_text(
        '{"version": 1, "paths": ["src/blackhole_agent/cli.py"]}\n',
        encoding="utf-8",
    )

    loaded = load_protected_paths(tmp_path)

    assert "src/blackhole_agent/cli.py" in loaded
    assert "src/blackhole_agent/supervisor.py" in loaded
    for path in DEFAULT_PROTECTED_PATHS:
        assert path_is_protected(path.rstrip("/"), loaded)


def test_gate_blocks_judge_diff_and_allows_operator_ack():
    blocked = evaluate_protected_paths_gate(["src/blackhole_agent/supervisor.py", "src/blackhole_agent/unbound.py"])
    allowed = evaluate_protected_paths_gate(["src/blackhole_agent/unbound.py"])
    acknowledged = evaluate_protected_paths_gate(
        ["src/blackhole_agent/supervisor.py"],
        operator_acknowledged=True,
    )

    assert blocked.blocked is True
    assert blocked.touched == ("src/blackhole_agent/supervisor.py",)
    assert allowed.blocked is False
    assert acknowledged.blocked is False
    assert acknowledged.operator_acknowledged is True


def test_listing_error_fails_closed():
    verdict = evaluate_protected_paths_gate([], listing_error="git missing")

    assert verdict.blocked is True
    assert "git missing" in verdict.reason


def test_promote_candidate_refuses_protected_path_without_ack(tmp_path):
    repo = tmp_path / "repo"
    candidate = tmp_path / "candidate"
    repo.mkdir()
    candidate.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    rollback = output_dir / "growth" / "latest-rollback-point.json"
    rollback.parent.mkdir(parents=True)
    rollback.write_text("{}\n", encoding="utf-8")
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if _is_diff_listing(command):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="src/blackhole_agent/supervisor.py\nsrc/blackhole_agent/unbound.py\n",
                stderr="",
            )
        if command == ["git", "rev-parse", "--verify", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="base123\n", stderr="")
        if command == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = promote_candidate(
        SupervisorConfig(repo_path=repo, output_dir=output_dir, health_commands=("uv run pytest",)),
        candidate_repo_path=candidate,
        pass_id="20260817T000000Z",
        candidate_branch="codex/evolve",
        candidate_head="cand123",
        command_runner=runner,
    )

    assert result.promoted is False
    assert result.protected_paths_blocked is True
    assert "src/blackhole_agent/supervisor.py" in result.protected_paths_touched
    assert ["git", "merge", "--ff-only", "cand123"] not in calls
    assert not any(command[:2] == ["uv", "run"] for command in calls)


def test_promote_candidate_allows_protected_path_with_operator_ack(tmp_path):
    repo = tmp_path / "repo"
    candidate = tmp_path / "candidate"
    repo.mkdir()
    candidate.mkdir()
    output_dir = repo / ".blackhole-agent" / "supervisor"
    rollback = output_dir / "growth" / "latest-rollback-point.json"
    rollback.parent.mkdir(parents=True)
    rollback.write_text("{}\n", encoding="utf-8")
    state = {"merged": False}

    def runner(command, **kwargs):
        if _is_diff_listing(command):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="src/blackhole_agent/supervisor.py\n",
                stderr="",
            )
        if command == ["git", "rev-parse", "--verify", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="base123\n", stderr="")
        if command == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["uv", "run"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")
        if command == ["git", "switch", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "merge", "--ff-only", "cand123"]:
            state["merged"] = True
            return subprocess.CompletedProcess(command, 0, stdout="merged\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="cand123\n", stderr="")
        if command == ["git", "push", "origin", "main"]:
            return subprocess.CompletedProcess(command, 0, stdout="pushed\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = promote_candidate(
        SupervisorConfig(
            repo_path=repo,
            output_dir=output_dir,
            health_commands=("uv run pytest",),
            allow_protected_path_promotion=True,
        ),
        candidate_repo_path=candidate,
        pass_id="20260817T000000Z",
        candidate_branch="codex/evolve",
        candidate_head="cand123",
        command_runner=runner,
    )

    assert result.promoted is True
    assert result.protected_paths_blocked is False
    assert result.operator_acknowledged is True
    assert state["merged"] is True


def test_evaluate_candidate_uses_target_floor_not_candidate_manifest(tmp_path):
    target = tmp_path / "target"
    candidate = tmp_path / "candidate"
    target.mkdir()
    candidate.mkdir()
    (target / "governance").mkdir()
    (candidate / "governance").mkdir()
    (candidate / "governance" / "protected-paths.json").write_text(
        '{"version": 1, "paths": []}\n',
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="src/blackhole_agent/persona.py\n",
            stderr="",
        )

    verdict = evaluate_candidate_protected_paths(
        target_repo_path=target,
        candidate_repo_path=candidate,
        target_before="base",
        candidate_head="cand",
        command_runner=runner,
    )

    assert verdict.blocked is True
    assert "src/blackhole_agent/persona.py" in verdict.touched


def test_diff_listing_keeps_rename_preimage_and_decodes_quoted_octal():
    renamed, rename_error = parse_diff_listing(
        b"R100\0src/blackhole_agent/supervisor.py\0src/blackhole_agent/moved_judge.py\0"
    )
    quoted, quoted_error = parse_diff_listing(b'"governance/\\303\\251note.json"\n')
    plain, plain_error = parse_diff_listing("README.md\n")

    assert rename_error == ""
    assert renamed == (
        "src/blackhole_agent/supervisor.py",
        "src/blackhole_agent/moved_judge.py",
    )
    assert quoted_error == ""
    assert quoted == ("governance/\u00e9note.json",)
    assert plain_error == ""
    assert plain == ("README.md",)


def test_real_git_rename_and_quoted_name_reach_the_gate(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "probe@example.invalid"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "probe"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "core.quotepath", "true"], cwd=repo, check=True, capture_output=True)
    judge = repo / "src" / "blackhole_agent"
    judge.mkdir(parents=True)
    (judge / "supervisor.py").write_text("JUDGE = 1\n", encoding="utf-8")
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=repo, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "mv", "src/blackhole_agent/supervisor.py", "src/blackhole_agent/moved_judge.py"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (repo / "governance").mkdir()
    (repo / "governance" / "\u00e9note.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "hide"], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    paths, error = list_changed_paths(repo, base, head)

    assert error == ""
    assert "src/blackhole_agent/supervisor.py" in paths
    assert "governance/\u00e9note.json" in paths


def test_builtin_protected_paths_gate_is_green():
    result = builtin_protected_paths_gate()

    assert result["ok"] is True
    assert Path("src/blackhole_agent/supervisor.py").as_posix() in result["blocked_touched"]
