"""Outcome probe: published supervisor evolution checkouts can be reclaimed.

The storage budget counts ``.{repo}-blackhole-worktrees``. Mission reclaim
only visits unbound checkouts, so finished supervisor worktrees stay
registered. A clean checkout whose commits are in ``origin/main`` is removed
with ``git worktree remove`` and without ``--force``. A dirty checkout, a
checkout with unpublished commits, and an unbound mission checkout stay.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


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


def _init_published_repo(root: Path) -> Path:
    remote = root / "origin.git"
    repo = root / "blackhole-agent"
    remote.mkdir()
    repo.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "reclaim@test.local")
    _git(repo, "config", "user.name", "Reclaim Test")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "origin", "HEAD:refs/heads/main")
    _git(repo, "fetch", "origin")
    return repo


def _add_worktree(repo: Path, parent: Path, name: str, branch: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    workspace = parent / name
    _git(repo, "worktree", "add", "-b", branch, str(workspace), "main")
    return workspace


def _exercise(reclaim) -> dict:
    observed: dict = {"removed_name": "", "kept_reasons": {}, "force_flags": []}
    scratch = tempfile.TemporaryDirectory(prefix="bh-supervisor-reclaim-")
    try:
        root = Path(scratch.name)
        repo = _init_published_repo(root)
        supervisor = root / ".blackhole-agent-blackhole-worktrees"
        published = _add_worktree(repo, supervisor, "20260615T071859Z", "evolve/published")
        dirty = _add_worktree(repo, supervisor, "20260615T092959Z", "evolve/dirty")
        (dirty / "notes.txt").write_text("unique local note\n", encoding="utf-8")
        unpublished = _add_worktree(repo, supervisor, "20260616T040147Z", "evolve/unpublished")
        (unpublished / "extra.txt").write_text("not pushed\n", encoding="utf-8")
        _git(unpublished, "add", "extra.txt")
        _git(unpublished, "commit", "-m", "unpublished")
        unbound = _add_worktree(
            repo,
            root / ".blackhole-agent-unbound-worktrees",
            "20261102T002252Z-b3f40e28",
            "unbound/stay",
        )
        report = reclaim(repo)
        receipt_path = repo / ".blackhole-agent" / "unbound" / "storage-budget.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
        targets = [item for item in receipt.get("cleanup_targets") or [] if isinstance(item, dict)]
        removed_targets = [
            item
            for item in targets
            if item.get("outcome") == "removed" and Path(str(item.get("path") or "")).name == published.name
        ]
        commands = [item.get("command") or [] for item in removed_targets]
        observed = {
            "published_exists": published.exists(),
            "dirty_exists": dirty.exists(),
            "unpublished_exists": unpublished.exists(),
            "unbound_exists": unbound.exists(),
            "removed_names": [Path(str(item.get("workspace") or item.get("path") or "")).name for item in report.get("reclaimed") or [] if item.get("removed") is True],
            "kept_reasons": {
                Path(str(item.get("workspace") or "")).name: item.get("reason")
                for item in report.get("kept") or []
                if isinstance(item, dict)
            },
            "force_flags": [item.get("force") for item in removed_targets],
            "commands_include_force": any("--force" in command or "-f" in command for command in commands),
            "errors": report.get("errors"),
        }
        passed = (
            observed["published_exists"] is False
            and observed["dirty_exists"] is True
            and observed["unpublished_exists"] is True
            and observed["unbound_exists"] is True
            and observed["removed_names"] == ["20260615T071859Z"]
            and observed["force_flags"] == [False]
            and observed["commands_include_force"] is False
            and not observed["errors"]
        )
        return {"passed": passed, "observed": observed}
    except Exception as error:
        observed["error"] = f"{type(error).__name__}: {error}"
        return {"passed": False, "observed": observed}
    finally:
        scratch.cleanup()


def main() -> int:
    try:
        from blackhole_agent.storage_budget import reclaim_supervisor_evolution_checkouts
    except ImportError as error:
        print(
            json.dumps(
                {
                    "passed": False,
                    "observed": f"supervisor evolution reclaim is absent: {error}",
                }
            )
        )
        return 0
    print(json.dumps(_exercise(reclaim_supervisor_evolution_checkouts)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
