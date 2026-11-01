"""Move the controller checkout forward to a commit already published.

The continuous loop pushes milestone commits to ``origin/main`` and leaves
the controller working tree on the older local ``main``. The editable
install loads that working tree, so the next mission create still executes
the pre-publication modules. A clean checkout that is a strict ancestor of
the published commit is fast-forwarded with ``git merge --ff-only``. A dirty
tree, a detached checkout, and a commit that is not a descendant stay where
they are. This module never resets, force-pushes, or deletes a worktree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

_IMPORT_SCRIPT = """
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "src"))
module = importlib.import_module(sys.argv[2])
value = getattr(module, sys.argv[3])
sys.stdout.write(str(value))
"""


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_MERGE_AUTOEDIT"] = "no"
    return env


def _run(
    command: Sequence[str],
    cwd: Path,
    command_runner: Callable[..., Any],
) -> subprocess.CompletedProcess[str]:
    if command_runner is subprocess.run:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    else:
        completed = command_runner(
            list(command),
            cwd=cwd,
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    if not isinstance(getattr(completed, "stdout", None), str):
        completed.stdout = "" if completed.stdout is None else str(completed.stdout)
    if not isinstance(getattr(completed, "stderr", None), str):
        completed.stderr = "" if completed.stderr is None else str(completed.stderr)
    return completed


def _text(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stdout or "").strip()


def _blank(
    *,
    branch: str,
    reason: str,
    head: str = "",
    published: str = "",
    commands: list[str] | None = None,
) -> dict[str, Any]:
    current = head
    return {
        "adopted": False,
        "moved": False,
        "reason": reason,
        "branch": branch,
        "head_before": current,
        "head_after": current,
        "published": published,
        "reset_used": False,
        "commands": list(commands or []),
    }


def adopt_published_controller(
    repo_path: Path,
    published_sha: str,
    *,
    branch: str = "main",
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Fast-forward ``branch`` to ``published_sha`` when that is a clean descendant.

    ``adopted`` is true when HEAD equals the published commit after the call,
    including when the checkout was already there. ``moved`` is true only when
    this call advanced HEAD. ``reset_used`` is always false.
    """

    repo = Path(repo_path)
    wanted = str(published_sha or "").strip()
    commands: list[str] = []

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        command = ["git", *arguments]
        commands.append(" ".join(command))
        return _run(command, repo, command_runner)

    if not wanted or wanted.startswith("-"):
        return _blank(branch=branch, reason="unresolvable", commands=commands)
    if not repo.exists() or not (repo / ".git").exists():
        return _blank(branch=branch, reason="not_a_repository", commands=commands)

    resolved = git("rev-parse", "--verify", "--end-of-options", f"{wanted}^{{commit}}")
    if resolved.returncode != 0:
        return _blank(branch=branch, reason="unresolvable", commands=commands)
    published = _text(resolved)

    head_cmd = git("rev-parse", "--verify", "HEAD")
    if head_cmd.returncode != 0:
        return _blank(branch=branch, reason="no_head", published=published, commands=commands)
    head_before = _text(head_cmd)

    checked_out = git("rev-parse", "--abbrev-ref", "HEAD")
    current_branch = _text(checked_out)
    if checked_out.returncode != 0 or current_branch in {"", "HEAD"}:
        return _blank(
            branch=branch,
            reason="detached",
            head=head_before,
            published=published,
            commands=commands,
        )
    if current_branch != branch:
        return _blank(
            branch=branch,
            reason="not_controller_branch",
            head=head_before,
            published=published,
            commands=commands,
        )

    if head_before == published:
        return {
            "adopted": True,
            "moved": False,
            "reason": "already_current",
            "branch": branch,
            "head_before": head_before,
            "head_after": head_before,
            "published": published,
            "reset_used": False,
            "commands": commands,
        }

    status = git("status", "--porcelain=v1", "--untracked-files=normal")
    if status.returncode != 0:
        return _blank(
            branch=branch,
            reason="status_failed",
            head=head_before,
            published=published,
            commands=commands,
        )
    if (status.stdout or "").strip():
        return _blank(
            branch=branch,
            reason="dirty",
            head=head_before,
            published=published,
            commands=commands,
        )

    ancestor = git("merge-base", "--is-ancestor", head_before, published)
    if ancestor.returncode != 0:
        return _blank(
            branch=branch,
            reason="not_fast_forward",
            head=head_before,
            published=published,
            commands=commands,
        )

    merged = git("merge", "--ff-only", "--no-edit", published)
    head_after_cmd = git("rev-parse", "--verify", "HEAD")
    head_after = _text(head_after_cmd) or head_before
    moved = head_after == published and head_after != head_before
    if merged.returncode != 0 or not moved:
        return {
            "adopted": False,
            "moved": False,
            "reason": "merge_failed",
            "branch": branch,
            "head_before": head_before,
            "head_after": head_after,
            "published": published,
            "reset_used": False,
            "commands": commands,
        }
    return {
        "adopted": True,
        "moved": True,
        "reason": "fast_forward",
        "branch": branch,
        "head_before": head_before,
        "head_after": head_after,
        "published": published,
        "reset_used": False,
        "commands": commands,
    }


def adopt_remote_controller(
    repo_path: Path,
    *,
    remote: str = "origin",
    branch: str = "main",
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Fast-forward the controller checkout to ``remote/branch`` when it exists."""

    repo = Path(repo_path)
    ref = f"refs/remotes/{remote}/{branch}"
    if not repo.exists() or not (repo / ".git").exists():
        return _blank(branch=branch, reason="not_a_repository")
    lookup = _run(
        ["git", "rev-parse", "--verify", "--end-of-options", ref],
        repo,
        command_runner,
    )
    if lookup.returncode != 0 or not _text(lookup):
        return _blank(branch=branch, reason="no_remote")
    return adopt_published_controller(
        repo,
        _text(lookup),
        branch=branch,
        command_runner=command_runner,
    )


def import_checkout_attribute(
    repo_path: Path,
    module: str,
    attribute: str,
    *,
    executable: str | None = None,
) -> dict[str, Any]:
    """Import ``module.attribute`` from ``repo/src`` in a fresh interpreter.

    The fresh process does not reuse this process's ``sys.modules``, so it
    reads the checkout that adoption just fast-forwarded.
    """

    repo = Path(repo_path)
    completed = subprocess.run(
        [
            executable or sys.executable,
            "-I",
            "-c",
            _IMPORT_SCRIPT,
            str(repo),
            module,
            attribute,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    value = completed.stdout if isinstance(completed.stdout, str) else ""
    return {
        "ok": completed.returncode == 0 and value != "",
        "exit_code": int(completed.returncode),
        "value": value.strip(),
        "stderr": (completed.stderr or "")[-400:],
    }


def commands_use_reset(report: Mapping[str, Any]) -> bool:
    """True when a reported git command resets history."""

    if report.get("reset_used") is True:
        return True
    for command in report.get("commands") or []:
        parts = str(command).split()
        if "reset" in parts or "--hard" in parts:
            return True
    return False
