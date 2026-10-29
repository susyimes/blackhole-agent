"""Release a git worktree registration left locked initializing after its directory vanished.

Builds a sandbox repository with three checkouts:

- one locked ``initializing`` whose directory is deleted
- one locked for another reason whose directory is deleted
- one locked checkout whose directory still exists

Reconciliation must drop only the first registration. Its branch ref must still
resolve, and both locked survivors must stay registered.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def worktree_block(repo: Path, workspace: Path) -> str:
    listed = git(repo, "worktree", "list", "--porcelain")
    for block in (listed.stdout or "").split("\n\n"):
        for line in block.splitlines():
            if line.startswith("worktree ") and Path(line.split(" ", 1)[1]).resolve() == workspace.resolve():
                return block
    return ""


def add_worktree(repo: Path, parent: Path, name: str, branch: str) -> Path:
    workspace = parent / name
    created = git(repo, "worktree", "add", "-b", branch, str(workspace), "main")
    if created.returncode != 0:
        raise RuntimeError(created.stderr or created.stdout)
    return workspace


def lock_file(workspace: Path, reason: str) -> None:
    gitfile = (workspace / ".git").read_text(encoding="utf-8")
    admin = Path(gitfile.split("gitdir:", 1)[1].strip())
    (admin / "locked").write_text(reason + "\n", encoding="utf-8")


def main() -> dict:
    try:
        from blackhole_agent.loop_creation_reconcile import reconcile_interrupted_creations
    except ImportError as error:
        return {"passed": False, "observed": f"reconciliation absent: {error}"}

    with tempfile.TemporaryDirectory(prefix="accept-missing-initializing-") as directory:
        root = Path(directory)
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Blackhole Acceptance")
        git(repo, "config", "user.email", "blackhole@example.invalid")
        (repo / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "seed")
        parent = root / "worktrees"
        parent.mkdir()

        missing_branch = "unbound/autonomous-genesis-2594c2eb"
        held_branch = "unbound/autonomous-genesis-holdlock"
        kept_branch = "unbound/autonomous-genesis-keeplock"
        missing = add_worktree(repo, parent, "20260910T111645Z-2594c2eb", missing_branch)
        held = add_worktree(repo, parent, "20261029T000000Z-holdlock", held_branch)
        kept = add_worktree(repo, parent, "20261029T000000Z-keeplock", kept_branch)
        lock_file(missing, "initializing")
        lock_file(held, "operator hold")
        lock_file(kept, "operator hold")
        shutil.rmtree(missing)
        shutil.rmtree(held)

        reconcile_interrupted_creations(repo, worktree_parent=parent)

        missing_block = worktree_block(repo, missing)
        held_block = worktree_block(repo, held)
        kept_block = worktree_block(repo, kept)
        missing_ref = git(repo, "rev-parse", "--verify", f"refs/heads/{missing_branch}")
        observed = {
            "missing_initializing_still_registered": bool(missing_block),
            "missing_directory_absent": not missing.exists(),
            "missing_branch_resolves": missing_ref.returncode == 0 and bool((missing_ref.stdout or "").strip()),
            "other_lock_still_registered": "locked operator hold" in held_block,
            "other_lock_directory_absent": not held.exists(),
            "present_lock_still_registered": "locked operator hold" in kept_block,
            "present_directory_remains": kept.is_dir(),
        }
        passed = bool(
            observed["missing_initializing_still_registered"] is False
            and observed["missing_directory_absent"]
            and observed["missing_branch_resolves"]
            and observed["other_lock_still_registered"]
            and observed["other_lock_directory_absent"]
            and observed["present_lock_still_registered"]
            and observed["present_directory_remains"]
        )
        return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
    sys.exit(0)
