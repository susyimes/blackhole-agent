"""Tests for mission-worktree reclamation (hermetic; throwaway git repos)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from blackhole_agent.unbound import (
    PublicationResult,
    UnboundMission,
    continuous_loop_events_path,
    continuous_loop_state_path,
    mission_root,
    reclaim_mission_worktrees,
    run_continuous_loop,
    save_mission,
)

DEFAULT_OUTPUT_DIR = Path(".blackhole-agent/unbound")


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return (completed.stdout or "").strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "gc@test.local")
    _git(repo, "config", "user.name", "GC Test")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    return repo


def _make_mission(
    repo: Path,
    mission_id: str,
    *,
    status: str,
    created_at: str,
    milestone: bool = True,
    merge_into_main: bool = True,
) -> Path:
    """Create a real mission worktree + durable state under the repo."""

    parent = repo.parent / f".{repo.name}-unbound-worktrees"
    parent.mkdir(exist_ok=True)
    workspace = parent / mission_id
    branch = f"unbound/test-{mission_id}"
    _git(repo, "worktree", "add", "-b", branch, str(workspace), "main")
    base_head = _git(workspace, "rev-parse", "HEAD")
    head = base_head
    if milestone:
        (workspace / f"{mission_id}.txt").write_text("milestone\n", encoding="utf-8")
        _git(workspace, "add", ".")
        _git(workspace, "commit", "-m", f"milestone {mission_id}")
        head = _git(workspace, "rev-parse", "HEAD")
    if milestone and merge_into_main:
        _git(repo, "merge", "--ff-only", head)
    mission_dir = mission_root(repo, DEFAULT_OUTPUT_DIR) / "missions" / mission_id
    state = UnboundMission(
        schema_version=1,
        mission_id=mission_id,
        created_at=created_at,
        updated_at=created_at,
        repo_path=str(repo),
        workspace_path=str(workspace),
        branch=branch,
        target_branch="main",
        goal="test goal",
        done_when="test done",
        status=status,
        stage="execution",
        base_head=base_head,
        last_milestone_head=head,
    )
    save_mission(mission_dir / "state.json", state)
    return workspace


def test_reclaims_only_published_complete_missions(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    published = _make_mission(repo, "m1-published", status="complete", created_at="2026-01-01T00:00:00Z")
    active = _make_mission(repo, "m2-active", status="active", created_at="2026-01-02T00:00:00Z")
    blocked = _make_mission(repo, "m3-blocked", status="blocked", created_at="2026-01-03T00:00:00Z")
    unpublished = _make_mission(
        repo,
        "m4-unpublished",
        status="complete",
        created_at="2026-01-04T00:00:00Z",
        merge_into_main=False,
    )

    report = reclaim_mission_worktrees(repo, ancestor_refs=("main",), keep_recent=0)

    assert report["ok"] is True, report
    assert report["scanned"] == 4
    assert [item["mission_id"] for item in report["reclaimed"]] == ["m1-published"]
    assert report["reclaimed"][0]["removed"] is True
    assert not published.exists()
    assert active.exists()
    assert blocked.exists()
    assert unpublished.exists()
    kept_reasons = {item["mission_id"]: item["reason"] for item in report["kept"]}
    assert kept_reasons["m2-active"] == "status_active"
    assert kept_reasons["m3-blocked"] == "status_blocked"
    assert kept_reasons["m4-unpublished"] == "milestones_not_in_lineage"
    # The branch survives by default so milestone commits stay referenced.
    assert "unbound/test-m1-published" in _git(repo, "branch", "--list", "unbound/test-m1-published")


def test_keep_recent_preserves_newest_reclaimable(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    older = _make_mission(repo, "m1-old", status="complete", created_at="2026-01-01T00:00:00Z")
    newer = _make_mission(repo, "m2-new", status="complete", created_at="2026-02-01T00:00:00Z")

    report = reclaim_mission_worktrees(repo, ancestor_refs=("main",), keep_recent=1)

    assert [item["mission_id"] for item in report["reclaimed"]] == ["m1-old"]
    assert not older.exists()
    assert newer.exists()
    kept_reasons = {item["mission_id"]: item["reason"] for item in report["kept"]}
    assert kept_reasons["m2-new"] == "keep_recent"


def test_dry_run_removes_nothing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    workspace = _make_mission(repo, "m1", status="complete", created_at="2026-01-01T00:00:00Z")

    report = reclaim_mission_worktrees(repo, ancestor_refs=("main",), keep_recent=0, dry_run=True)

    assert report["dry_run"] is True
    assert [item["mission_id"] for item in report["reclaimed"]] == ["m1"]
    assert report["reclaimed"][0]["removed"] is False
    assert workspace.exists()


def test_dirty_complete_worktree_is_still_reclaimed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    workspace = _make_mission(repo, "m1", status="complete", created_at="2026-01-01T00:00:00Z")
    (workspace / "stray.txt").write_text("leftover\n", encoding="utf-8")

    report = reclaim_mission_worktrees(repo, ancestor_refs=("main",), keep_recent=0)

    assert report["ok"] is True, report
    assert not workspace.exists()


def test_delete_branches_removes_merged_branch_only(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _make_mission(repo, "m1", status="complete", created_at="2026-01-01T00:00:00Z")

    report = reclaim_mission_worktrees(
        repo,
        ancestor_refs=("main",),
        keep_recent=0,
        delete_branches=True,
    )

    assert report["reclaimed"][0]["branch_deleted"] is True
    assert _git(repo, "branch", "--list", "unbound/test-m1") == ""


def test_missing_workspace_is_pruned_from_registry(tmp_path: Path) -> None:
    import shutil

    repo = _init_repo(tmp_path)
    workspace = _make_mission(repo, "m1", status="complete", created_at="2026-01-01T00:00:00Z")
    shutil.rmtree(workspace)

    report = reclaim_mission_worktrees(repo, ancestor_refs=("main",), keep_recent=0)

    assert report["ok"] is True, report
    assert [item["mission_id"] for item in report["pruned_missing"]] == ["m1"]
    assert workspace.as_posix() not in _git(repo, "worktree", "list", "--porcelain")


def test_unreadable_state_is_kept_and_reported(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    mission_dir = mission_root(repo, DEFAULT_OUTPUT_DIR) / "missions" / "m1-broken"
    mission_dir.mkdir(parents=True)
    (mission_dir / "state.json").write_text("{not json", encoding="utf-8")

    report = reclaim_mission_worktrees(repo, ancestor_refs=("main",), keep_recent=0)

    assert report["ok"] is True
    assert report["reclaimed"] == []
    assert report["kept"][0]["mission_id"] == "m1-broken"
    assert report["kept"][0]["reason"].startswith("unreadable_state")


def test_continuous_loop_runs_worktree_gc_after_publication(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    calls: list[dict[str, object]] = []

    def mission_creator(**kwargs) -> Path:
        _make_mission(
            repo,
            "loop-m1",
            status="active",
            created_at="2026-01-01T00:00:00Z",
            milestone=False,
        )
        return mission_root(repo, DEFAULT_OUTPUT_DIR) / "missions" / "loop-m1" / "state.json"

    def mission_runner(state_path: Path, **kwargs) -> int:
        state_file = Path(state_path)
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        payload["status"] = "complete"
        state_file.write_text(json.dumps(payload), encoding="utf-8")
        return 0

    def lineage_publisher(repo_path: Path, commit_sha: str, remote: str, branch: str, **kwargs) -> PublicationResult:
        return PublicationResult(
            ok=True,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before="",
            remote_after=commit_sha,
            error="",
            command=(),
        )

    def worktree_reclaimer(repo_path: Path, **kwargs) -> dict[str, object]:
        calls.append({"repo_path": Path(repo_path), **kwargs})
        return {
            "ok": True,
            "scanned": 1,
            "reclaimed": [{"mission_id": "loop-m1", "removed": True}],
            "kept": [],
            "errors": [],
            "pruned_missing": [],
            "ancestor_refs": list(kwargs.get("ancestor_refs") or ()),
        }

    exit_code = run_continuous_loop(
        repo_path=repo,
        kernel="grok",
        publish_remote="origin",
        max_missions=1,
        wait_first=False,
        resume_latest=False,
        worktree_gc_keep_recent=2,
        mission_creator=mission_creator,
        mission_runner=mission_runner,
        lineage_publisher=lineage_publisher,
        worktree_reclaimer=worktree_reclaimer,
        interval_waiter=lambda seconds, stop_path: False,
    )

    assert exit_code == 0
    assert len(calls) == 1, calls
    assert calls[0]["keep_recent"] == 2
    assert "main" in tuple(calls[0]["ancestor_refs"])
    assert "origin/main" in tuple(calls[0]["ancestor_refs"])

    loop_state = json.loads(continuous_loop_state_path(repo, DEFAULT_OUTPUT_DIR).read_text(encoding="utf-8"))
    assert loop_state["worktree_gc_count"] == 1
    assert loop_state["worktree_reclaimed_count"] == 1
    assert loop_state["last_worktree_gc_error"] == ""

    events = [
        json.loads(line)
        for line in continuous_loop_events_path(repo, DEFAULT_OUTPUT_DIR)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    gc_events = [event for event in events if event["event"] == "continuous_loop.worktree_gc"]
    assert len(gc_events) == 1
    assert gc_events[0]["trigger"] == "publication"
    assert gc_events[0]["reclaimed_ids"] == ["loop-m1"]


def test_continuous_loop_gc_failure_never_breaks_the_loop(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    def mission_creator(**kwargs) -> Path:
        _make_mission(repo, "loop-m1", status="active", created_at="2026-01-01T00:00:00Z", milestone=False)
        return mission_root(repo, DEFAULT_OUTPUT_DIR) / "missions" / "loop-m1" / "state.json"

    def mission_runner(state_path: Path, **kwargs) -> int:
        state_file = Path(state_path)
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        payload["status"] = "complete"
        state_file.write_text(json.dumps(payload), encoding="utf-8")
        return 0

    def lineage_publisher(repo_path: Path, commit_sha: str, remote: str, branch: str, **kwargs) -> PublicationResult:
        return PublicationResult(
            ok=True,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before="",
            remote_after=commit_sha,
            error="",
            command=(),
        )

    def broken_reclaimer(repo_path: Path, **kwargs) -> dict[str, object]:
        raise RuntimeError("gc exploded")

    exit_code = run_continuous_loop(
        repo_path=repo,
        kernel="grok",
        publish_remote="origin",
        max_missions=1,
        wait_first=False,
        resume_latest=False,
        mission_creator=mission_creator,
        mission_runner=mission_runner,
        lineage_publisher=lineage_publisher,
        worktree_reclaimer=broken_reclaimer,
        interval_waiter=lambda seconds, stop_path: False,
    )

    assert exit_code == 0
    loop_state = json.loads(continuous_loop_state_path(repo, DEFAULT_OUTPUT_DIR).read_text(encoding="utf-8"))
    assert loop_state["worktree_gc_count"] == 0
    assert loop_state["last_worktree_gc_error"] == "gc exploded"
    events = [
        json.loads(line)
        for line in continuous_loop_events_path(repo, DEFAULT_OUTPUT_DIR)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert any(event["event"] == "continuous_loop.worktree_gc_failed" for event in events)
