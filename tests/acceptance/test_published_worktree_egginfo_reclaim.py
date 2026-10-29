"""Published worktrees must not stay forever because of egg-info or a dead gitfile.

Harvested completed checkouts from 2026-10-29 are otherwise clean and
published, and ``git status --ignored`` lists only ``src/blackhole_agent.egg-info/``.
That ignored setuptools metadata is classified as unique work, so safe
reclaim keeps the checkout. The 2026-10-11 checkout
``20261011T171710Z-af3a83c6`` still has a ``.git`` gitfile whose gitdir
directory is gone (``fatal: not a git repository: (NULL)``). That status
failure is classified unreadable because the gitfile exists, so the
matching published tree is never removed.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.worktree_reclaim_verify import (
    assess_worktree_removal,
    git_worktree_remove_command,
)


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
    repo = root / "fixture-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "reclaim@test.local")
    _git(repo, "config", "user.name", "Reclaim Probe")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / ".gitignore").write_text("*.egg-info/\n__pycache__/\n", encoding="utf-8")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "seed")
    return repo


def _worktree(repo: Path, name: str) -> Path:
    parent = repo.parent / f".{repo.name}-unbound-worktrees"
    parent.mkdir(exist_ok=True)
    workspace = parent / name
    _git(repo, "worktree", "add", "-b", f"unbound/{name}", str(workspace), "main")
    return workspace


def _break_gitdir(workspace: Path) -> None:
    gitfile = workspace / ".git"
    text = gitfile.read_text(encoding="utf-8", errors="replace")
    target = Path(text.strip().split(":", 1)[1].strip())
    if target.exists():
        shutil.rmtree(target)


def _observe(root: Path) -> dict[str, object]:
    repo = _init_repo(root)
    head = _git(repo, "rev-parse", "HEAD")
    egg = _worktree(repo, "egg-info")
    egg_meta = egg / "src" / "pkg.egg-info"
    egg_meta.mkdir(parents=True)
    (egg_meta / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: pkg\n", encoding="utf-8")
    dead = _worktree(repo, "dead-gitdir")
    _break_gitdir(dead)
    stray = _worktree(repo, "stray-source")
    (stray / "notes.txt").write_text("keep me\n", encoding="utf-8")

    def assess(workspace: Path, branch: str):
        return assess_worktree_removal(
            repo,
            workspace,
            branch=branch,
            milestone_head=head,
            ancestor_refs=("main",),
        )

    egg_result = assess(egg, "unbound/egg-info")
    dead_result = assess(dead, "unbound/dead-gitdir")
    stray_result = assess(stray, "unbound/stray-source")
    command = git_worktree_remove_command(egg)
    return {
        "egg_info_removable": egg_result.removable,
        "egg_info_reason": egg_result.reason,
        "egg_info_stale": egg_result.stale_published_tree,
        "dead_gitdir_removable": dead_result.removable,
        "dead_gitdir_reason": dead_result.reason,
        "dead_gitdir_stale": dead_result.stale_published_tree,
        "stray_removable": stray_result.removable,
        "stray_reason": stray_result.reason,
        "remove_command": command,
        "remove_command_has_force": ("--force" in command or "-f" in command),
        "harvested_egg_info": "src/blackhole_agent.egg-info/",
        "harvested_dead_gitdir": "20261011T171710Z-af3a83c6",
    }


def main() -> int:
    observed: dict[str, object]
    try:
        with tempfile.TemporaryDirectory(prefix="bh-reclaim-") as tmp:
            observed = _observe(Path(tmp))
        passed = (
            observed["egg_info_removable"] is True
            and observed["egg_info_reason"] == ""
            and observed["dead_gitdir_removable"] is True
            and observed["dead_gitdir_stale"] is True
            and observed["dead_gitdir_reason"] == ""
            and observed["stray_removable"] is False
            and observed["stray_reason"] == "unique_or_uncommitted_work"
            and observed["remove_command_has_force"] is False
        )
    except Exception as error:  # noqa: BLE001 - probe must report unmet, not crash
        observed = {"error": f"{error.__class__.__name__}: {error}"}
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
