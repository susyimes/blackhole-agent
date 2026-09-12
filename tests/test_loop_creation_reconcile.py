"""Tests for interrupted mission-creation reconciliation at loop startup."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from blackhole_agent.loop_creation_reconcile import (
    INTERRUPTED_EVENT,
    orphan_inventory_path,
    reconcile_interrupted_creations,
)
from blackhole_agent.unbound import (
    DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
    continuous_loop_events_path,
    load_mission,
    run_continuous_loop,
    save_mission,
)


def init_repository(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Blackhole Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "blackhole@example.invalid"], cwd=path, check=True)
    (path / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=path, check=True, capture_output=True, text=True)


def add_orphan_worktree(repo: Path, parent: Path, mission_id: str) -> tuple[Path, str]:
    branch = f"unbound/autonomous-genesis-{mission_id[-8:]}"
    workspace = parent / mission_id
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(workspace), "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace, branch


def read_events(repo: Path) -> list[dict]:
    path = continuous_loop_events_path(repo)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_stateless_worktree_is_recorded_and_preserved(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    parent = tmp_path / "worktrees"
    parent.mkdir()
    workspace, branch = add_orphan_worktree(repo, parent, "20260910T191600Z-deadbeef")

    report = reconcile_interrupted_creations(repo, worktree_parent=parent)

    assert report["ok"] and report["scanned"] == 1
    assert len(report["new_orphans"]) == 1
    entry = report["new_orphans"][0]
    assert entry["mission_id"] == "20260910T191600Z-deadbeef"
    assert entry["branch"] == branch
    assert entry["git_registered"] is True

    inventory = json.loads(orphan_inventory_path(repo).read_text(encoding="utf-8"))
    assert [item["mission_id"] for item in inventory["orphans"]] == ["20260910T191600Z-deadbeef"]
    events = [e for e in read_events(repo) if e["event"] == INTERRUPTED_EVENT]
    assert len(events) == 1
    assert events[0]["workspace"] == str(workspace)

    # Preserved, never deleted.
    assert workspace.is_dir()
    listed = subprocess.run(
        ["git", "branch", "--list", branch], cwd=repo, check=True, capture_output=True, text=True
    )
    assert branch in listed.stdout


def test_repeated_reconciliation_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    parent = tmp_path / "worktrees"
    parent.mkdir()
    add_orphan_worktree(repo, parent, "20260910T191600Z-deadbeef")

    first = reconcile_interrupted_creations(repo, worktree_parent=parent)
    inventory_before = orphan_inventory_path(repo).read_text(encoding="utf-8")
    second = reconcile_interrupted_creations(repo, worktree_parent=parent)

    assert len(first["new_orphans"]) == 1
    assert second["new_orphans"] == []
    assert second["known_orphans"] == 1
    assert orphan_inventory_path(repo).read_text(encoding="utf-8") == inventory_before
    events = [e for e in read_events(repo) if e["event"] == INTERRUPTED_EVENT]
    assert len(events) == 1


def test_registered_mission_worktree_is_untouched(tmp_path):
    from blackhole_agent.unbound import mission_root

    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    parent = tmp_path / "worktrees"
    parent.mkdir()
    workspace, _branch = add_orphan_worktree(repo, parent, "20260912T000000Z-livebeef")
    state_dir = mission_root(repo) / "missions" / "20260912T000000Z-livebeef"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("{}", encoding="utf-8")

    report = reconcile_interrupted_creations(repo, worktree_parent=parent)

    assert report["registered_skipped"] == 1
    assert report["new_orphans"] == []
    assert not orphan_inventory_path(repo).exists()
    assert read_events(repo) == []
    assert workspace.is_dir()


def test_empty_or_missing_worktree_parent_is_a_noop(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)

    report = reconcile_interrupted_creations(repo, worktree_parent=tmp_path / "absent")

    assert report["ok"] and report["scanned"] == 0 and report["new_orphans"] == []
    assert not orphan_inventory_path(repo).exists()


def test_loop_startup_reconciles_interrupted_creation_before_next_mission(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repository(repo)
    worktrees = tmp_path / "worktrees"
    worktrees.mkdir()
    orphan_workspace, orphan_branch = add_orphan_worktree(repo, worktrees, "20260910T191600Z-deadbeef")

    def completing_runner(state_path, **kwargs):
        state = load_mission(state_path)
        state.status = "complete"
        save_mission(state_path, state)
        return 0

    result = run_continuous_loop(
        repo_path=repo,
        interval_seconds=DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
        max_missions=1,
        resume_latest=False,
        worktree_parent=worktrees,
        mission_runner=completing_runner,
        interval_waiter=lambda seconds, stop_path: False,
    )

    assert result == 0
    inventory = json.loads(orphan_inventory_path(repo).read_text(encoding="utf-8"))
    assert [item["mission_id"] for item in inventory["orphans"]] == ["20260910T191600Z-deadbeef"]
    assert inventory["orphans"][0]["branch"] == orphan_branch
    events = read_events(repo)
    interrupted = [e for e in events if e["event"] == INTERRUPTED_EVENT]
    assert len(interrupted) == 1
    assert interrupted[0]["workspace"] == str(orphan_workspace)
    started = next(e for e in events if e["event"] == "continuous_loop.started")
    assert started["interrupted_creations_reconciled"] == 1
    assert orphan_workspace.is_dir()
