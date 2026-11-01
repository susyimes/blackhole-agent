"""Controller checkout adoption follows a published fast-forward."""

from __future__ import annotations

import subprocess
from pathlib import Path

from blackhole_agent.controller_adoption import (
    adopt_published_controller,
    adopt_remote_controller,
    commands_use_reset,
    import_checkout_attribute,
    storage_gate_needs_reimport,
)
from blackhole_agent.unbound import create_mission


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return (completed.stdout or "").strip()


def _controller(repo: Path) -> str:
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "controller@test.local")
    _git(repo, "config", "user.name", "Controller Test")
    _git(repo, "config", "core.autocrlf", "false")
    source = repo / "src"
    source.mkdir()
    (source / "published_marker.py").write_text('VALUE = "stale"\n', encoding="utf-8")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "stale")
    _git(repo, "checkout", "-b", "published")
    (source / "published_marker.py").write_text('VALUE = "published"\n', encoding="utf-8")
    _git(repo, "add", "src/published_marker.py")
    _git(repo, "commit", "-m", "published")
    published = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", published)
    _git(repo, "checkout", "main")
    return published


def test_storage_gate_reimports_when_publication_already_fast_forwarded() -> None:
    already = {"moved": False, "reason": "already_current", "adopted": True}
    assert storage_gate_needs_reimport(already, loaded_sha="old", checkout_sha="new") is True
    assert storage_gate_needs_reimport(already, loaded_sha="", checkout_sha="new") is True
    assert storage_gate_needs_reimport(already, loaded_sha="same", checkout_sha="same") is False
    assert storage_gate_needs_reimport({"moved": True}, loaded_sha="same", checkout_sha="same") is True
    assert storage_gate_needs_reimport(already, loaded_sha="old", checkout_sha="") is False


def test_clean_checkout_adopts_published_marker(tmp_path: Path) -> None:
    repo = tmp_path / "controller"
    published = _controller(repo)

    report = adopt_published_controller(repo, published)
    imported = import_checkout_attribute(repo, "published_marker", "VALUE")

    assert report["adopted"] is True
    assert report["moved"] is True
    assert report["reason"] == "fast_forward"
    assert report["head_after"] == published
    assert report["reset_used"] is False
    assert commands_use_reset(report) is False
    assert imported["ok"] is True
    assert imported["value"] == "published"


def test_remote_alias_adopts_origin_main(tmp_path: Path) -> None:
    repo = tmp_path / "controller"
    published = _controller(repo)

    report = adopt_remote_controller(repo)

    assert report["adopted"] is True
    assert report["head_after"] == published
    assert import_checkout_attribute(repo, "published_marker", "VALUE")["value"] == "published"


def test_dirty_checkout_and_diverged_commit_stay(tmp_path: Path) -> None:
    dirty_repo = tmp_path / "dirty"
    published = _controller(dirty_repo)
    (dirty_repo / "README.md").write_text("dirty local\n", encoding="utf-8")
    before = _git(dirty_repo, "rev-parse", "HEAD")

    dirty = adopt_published_controller(dirty_repo, published)

    assert dirty["adopted"] is False
    assert dirty["reason"] == "dirty"
    assert _git(dirty_repo, "rev-parse", "HEAD") == before
    assert (dirty_repo / "README.md").read_text(encoding="utf-8") == "dirty local\n"
    assert commands_use_reset(dirty) is False

    diverged = tmp_path / "diverged"
    _controller(diverged)
    _git(diverged, "checkout", "-b", "side")
    (diverged / "src" / "published_marker.py").write_text('VALUE = "side"\n', encoding="utf-8")
    _git(diverged, "add", "src/published_marker.py")
    _git(diverged, "commit", "-m", "side")
    side = _git(diverged, "rev-parse", "HEAD")
    _git(diverged, "checkout", "main")
    (diverged / "README.md").write_text("local edit\n", encoding="utf-8")
    _git(diverged, "add", "README.md")
    _git(diverged, "commit", "-m", "local")
    local = _git(diverged, "rev-parse", "HEAD")

    refused = adopt_published_controller(diverged, side)

    assert refused["adopted"] is False
    assert refused["reason"] == "not_fast_forward"
    assert _git(diverged, "rev-parse", "HEAD") == local
    assert (diverged / "README.md").read_text(encoding="utf-8") == "local edit\n"
    assert commands_use_reset(refused) is False


def test_create_mission_adopts_origin_main_before_the_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "controller"
    published = _controller(repo)

    state_path = create_mission(
        repo_path=repo,
        goal="Adopt the published controller checkout.",
        done_when="The checkout reads the published marker.",
        worktree_parent=tmp_path / "worktrees",
        kernel_resolver=lambda kernel: (kernel, {"mode": "test", "kernel": kernel}),
    )

    assert _git(repo, "rev-parse", "HEAD") == published
    assert (repo / "src" / "published_marker.py").read_text(encoding="utf-8") == 'VALUE = "published"\n'
    from blackhole_agent.unbound import load_mission

    state = load_mission(state_path)
    assert state.base_head == published
    assert Path(state.workspace_path, "src", "published_marker.py").read_text(encoding="utf-8") == (
        'VALUE = "published"\n'
    )
