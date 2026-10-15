"""Outcome probe: completed worktrees are removed only when they are clean.

A published completed mission worktree with an untracked file stays on disk,
including that file. A completed worktree whose tip is only on the local
branch, not on the verified remote, also stays. A completed worktree whose
commits are on that remote and whose checkout has no unique or uncommitted
work is removed with ``git worktree remove`` and without ``--force``.

On the previous milestone every one of those directories is deleted with
``git worktree remove --force``, so this probe reports passed=false. Both
outcomes exit 0.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.unbound import UnboundMission, mission_root, reclaim_mission_worktrees, save_mission


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


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "gc@test.local")
    _git(repo, "config", "user.name", "GC Test")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    bare = root / "origin.git"
    _git(repo, "init", "--bare", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "origin", "HEAD:main")
    return repo


def _make_mission(repo: Path, mission_id: str, created_at: str) -> Path:
    parent = repo.parent / f".{repo.name}-unbound-worktrees"
    parent.mkdir(exist_ok=True)
    workspace = parent / mission_id
    branch = f"unbound/probe-{mission_id}"
    _git(repo, "worktree", "add", "-b", branch, str(workspace), "main")
    base_head = _git(workspace, "rev-parse", "HEAD")
    (workspace / f"{mission_id}.txt").write_text("milestone\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", f"milestone {mission_id}")
    head = _git(workspace, "rev-parse", "HEAD")
    _git(repo, "merge", "--ff-only", head)
    mission_dir = mission_root(repo, Path(".blackhole-agent/unbound")) / "missions" / mission_id
    save_mission(
        mission_dir / "state.json",
        UnboundMission(
            schema_version=1,
            mission_id=mission_id,
            created_at=created_at,
            updated_at=created_at,
            repo_path=str(repo),
            workspace_path=str(workspace),
            branch=branch,
            target_branch="main",
            goal="probe",
            done_when="probe",
            status="complete",
            stage="execution",
            base_head=base_head,
            last_milestone_head=head,
        ),
    )
    return workspace


def main() -> dict[str, object]:
    scratch = tempfile.TemporaryDirectory(prefix="verified-worktree-reclaim-")
    observed: dict[str, object] = {"family": "verified-worktree-reclaim"}
    try:
        repo = _init_repo(Path(scratch.name))
        clean = _make_mission(repo, "clean", "2026-01-01T00:00:00Z")
        _git(repo, "push", "origin", "HEAD:main")
        dirty = _make_mission(repo, "dirty", "2026-01-02T00:00:00Z")
        _git(repo, "push", "origin", "HEAD:main")
        (dirty / "stray.txt").write_text("unique leftover\n", encoding="utf-8")
        local_only = _make_mission(repo, "local-only", "2026-01-03T00:00:00Z")
        report = reclaim_mission_worktrees(
            repo,
            ancestor_refs=("main", "origin/main"),
            keep_recent=0,
        )
        commands = [list(item.get("remove_command") or []) for item in report.get("reclaimed") or []]
        forced = any("--force" in command or "-f" in command for command in commands)
        stray = dirty / "stray.txt"
        observed.update(
            {
                "ok": report.get("ok"),
                "force_removal": report.get("force_removal"),
                "clean_exists": clean.exists(),
                "dirty_exists": dirty.exists(),
                "stray_exists": stray.is_file(),
                "stray_text": stray.read_text(encoding="utf-8") if stray.is_file() else "",
                "local_only_exists": local_only.exists(),
                "reclaimed_ids": [item.get("mission_id") for item in report.get("reclaimed") or []],
                "kept_reasons": {
                    item.get("mission_id"): item.get("reason") for item in report.get("kept") or []
                },
                "remove_commands": commands,
                "forced_remove": forced,
                "errors": report.get("errors"),
            }
        )
        passed = (
            observed["ok"] is True
            and observed["clean_exists"] is False
            and observed["dirty_exists"] is True
            and observed["stray_exists"] is True
            and observed["stray_text"] == "unique leftover\n"
            and observed["local_only_exists"] is True
            and observed["reclaimed_ids"] == ["clean"]
            and forced is False
        )
        observed["checks_passed"] = passed
        return {"passed": passed, "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        scratch.cleanup()


if __name__ == "__main__":
    try:
        result = main()
    except Exception as exc:
        result = {
            "passed": False,
            "observed": {"family": "verified-worktree-reclaim", "error": f"{type(exc).__name__}: {exc}"},
        }
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
