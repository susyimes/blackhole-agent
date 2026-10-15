"""Decide whether one mission worktree may be removed, without ``--force``.

``git worktree remove --force`` deletes untracked files, ignored secrets, and
a checkout whose extra commits never reached the remote. This module refuses
that. A directory is removable only when the path stays inside the managed
worktree parent, every branch and checkout commit is in the verified lineage
(the remote-tracking tips when any were supplied), no reparse point is
present, and tracked, untracked, and ignored paths hold no unique or
uncommitted work. Process use is checked separately, immediately before the
delete, so a lock discovered at that moment still preserves the directory.
"""

from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

_REPARSE_ATTRIBUTE = 0x400
_REPRODUCIBLE_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "htmlcov",
        ".venv",
    }
)
_REPRODUCIBLE_FILE_NAMES = frozenset({".coverage"})
_REPRODUCIBLE_SUFFIXES = frozenset({".pyc", ".pyo"})


@dataclass(frozen=True)
class WorktreeRemovalAssessment:
    """Removal decision for one existing mission workspace."""

    removable: bool
    reason: str = ""
    stale_published_tree: bool = False


def managed_worktree_parent(repo_path: Path) -> Path:
    """Parent directory Blackhole uses for mission worktrees of this repo."""

    repo = Path(repo_path).resolve()
    return repo.parent / f".{repo.name}-unbound-worktrees"


def git_worktree_remove_command(workspace: Path) -> list[str]:
    """The only worktree-removal command this module allows."""

    command = ["git", "worktree", "remove", str(workspace)]
    if "--force" in command or "-f" in command:
        raise RuntimeError("git worktree remove must not use --force")
    return command


def assess_worktree_removal(
    repo_path: Path,
    workspace: Path,
    *,
    branch: str,
    milestone_head: str,
    ancestor_refs: Sequence[str],
    command_runner: Callable[..., Any] = subprocess.run,
) -> WorktreeRemovalAssessment:
    """Return whether this workspace is safe to remove.

    Does not rename or delete. Call :func:`directory_in_use` immediately
    before the actual removal; a process can appear after this assessment.
    """

    repo = Path(repo_path)
    target = Path(workspace)
    if _is_reparse(target) or not _inside_managed_parent(repo, target):
        return WorktreeRemovalAssessment(False, "outside_owned_root")

    lineage = _lineage_block_reason(
        repo,
        target,
        branch=branch,
        milestone_head=milestone_head,
        ancestor_refs=ancestor_refs,
        command_runner=command_runner,
    )
    if lineage is not None:
        return WorktreeRemovalAssessment(False, lineage)

    if _contains_reparse(target):
        return WorktreeRemovalAssessment(False, "reparse_point_present")

    status = _run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignored=matching",
            "-z",
        ],
        target,
        command_runner,
    )
    if status.returncode != 0:
        if (target / ".git").exists():
            return WorktreeRemovalAssessment(False, "worktree_status_unreadable")
        if _published_tree_matches(repo, milestone_head, target, command_runner):
            return WorktreeRemovalAssessment(True, "", stale_published_tree=True)
        return WorktreeRemovalAssessment(False, "stale_directory_has_unique_work")

    unique = _unique_work_reason(status.stdout or "")
    if unique is not None:
        return WorktreeRemovalAssessment(False, unique)
    return WorktreeRemovalAssessment(True, "")


def directory_in_use(workspace: Path) -> str | None:
    """Return a skip reason when a live process is using this directory.

    On Windows a process current directory cannot be renamed. The PEB
    directory string is not reliable for the uv Python trampoline, which
    updates the real current directory without rewriting that string, so the
    check renames the directory onto a sibling and immediately renames it
    back. On POSIX the check reads ``/proc`` current directories and command
    lines. A failed enumeration blocks removal.
    """

    target = Path(workspace)
    if os.name == "nt":
        reason = _windows_directory_in_use(target)
    else:
        reason = _posix_directory_in_use(target)
    if reason is not None:
        return reason
    lock = _git_index_lock(target)
    if lock is not None:
        return lock
    return None


def bounded_remove_published_tree(
    repo_path: Path,
    commit: str,
    workspace: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> bool:
    """Delete a detached checkout only when it matches ``commit`` exactly.

    Reparse points are not followed and block the delete. The managed
    worktree parent itself is never removed.
    """

    repo = Path(repo_path)
    target = Path(workspace)
    if directory_in_use(target) is not None:
        return False
    if not _published_tree_matches(repo, commit, target, command_runner):
        return False
    return _bounded_remove_tree(target, managed_worktree_parent(repo))


def _lineage_block_reason(
    repo: Path,
    workspace: Path,
    *,
    branch: str,
    milestone_head: str,
    ancestor_refs: Sequence[str],
    command_runner: Callable[..., Any],
) -> str | None:
    remote_tips: list[str] = []
    local_tips: list[str] = []
    for ref in ancestor_refs:
        name = str(ref).strip()
        if not name:
            continue
        sha = _rev_parse(repo, name, command_runner)
        if not sha:
            continue
        symbolic = _run(["git", "rev-parse", "--symbolic-full-name", name], repo, command_runner)
        full_name = (symbolic.stdout or "").strip() if symbolic.returncode == 0 else ""
        if full_name.startswith("refs/remotes/"):
            remote_tips.append(sha)
        else:
            local_tips.append(sha)
    used_remote = bool(remote_tips)
    tips = remote_tips if used_remote else local_tips
    if not tips:
        return "milestones_not_in_lineage"

    heads = [milestone_head.strip()]
    branch_tip = _rev_parse(repo, branch, command_runner) if str(branch).strip() else ""
    if branch_tip:
        heads.append(branch_tip)
    checkout = _rev_parse(workspace, "HEAD", command_runner)
    if checkout:
        heads.append(checkout)

    def contained(commit: str, lineage: Sequence[str]) -> bool:
        return any(_is_ancestor(repo, commit, tip, command_runner) for tip in lineage)

    if not milestone_head.strip() or not contained(milestone_head.strip(), tips):
        if used_remote and local_tips and contained(milestone_head.strip(), local_tips):
            return "commits_not_in_remote_lineage"
        return "milestones_not_in_lineage"
    for commit in heads:
        if not contained(commit, tips):
            return "commits_not_in_remote_lineage" if used_remote else "commits_not_in_lineage"
    return None


def _unique_work_reason(porcelain: str) -> str | None:
    for status, path in _parse_porcelain_z(porcelain):
        if status == "!!" and _is_reproducible_ignored(path):
            continue
        return "unique_or_uncommitted_work"
    return None


def _is_reproducible_ignored(relative: str) -> bool:
    pure = Path(relative.replace("\\", "/"))
    if pure.name in _REPRODUCIBLE_FILE_NAMES or pure.suffix in _REPRODUCIBLE_SUFFIXES:
        return True
    return any(part in _REPRODUCIBLE_DIR_NAMES for part in pure.parts)


def _parse_porcelain_z(payload: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    chunks = payload.split("\0")
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        index += 1
        if len(chunk) < 4:
            continue
        status = chunk[:2]
        path = chunk[3:]
        if status[:1] in {"R", "C"} and index < len(chunks):
            path = chunks[index]
            index += 1
        records.append((status, path))
    return records


def _published_tree_matches(
    repo: Path,
    commit: str,
    workspace: Path,
    command_runner: Callable[..., Any],
) -> bool:
    """True when every non-cache file matches the published blob bytes."""

    if not str(commit).strip() or not _inside_managed_parent(repo, workspace):
        return False
    if _is_reparse(workspace) or _contains_reparse(workspace):
        return False
    if (workspace / ".git").exists():
        return False
    listed = _run(["git", "ls-tree", "-r", "-z", commit], repo, command_runner)
    if listed.returncode != 0:
        return False
    blobs: dict[str, str] = {}
    for record in (listed.stdout or "").split("\0"):
        if "\t" not in record:
            continue
        meta, path = record.split("\t", 1)
        bits = meta.split()
        if len(bits) >= 3 and bits[1] == "blob":
            blobs[path.replace("\\", "/")] = bits[2]
    try:
        files = _regular_files(workspace)
    except OSError:
        return False
    for path in files:
        relative = path.relative_to(workspace.resolve()).as_posix()
        if _is_reproducible_ignored(relative):
            continue
        digest = blobs.get(relative)
        if digest is None:
            return False
        if not _file_matches_blob(repo, commit, relative, path):
            return False
    return True


def _file_matches_blob(repo: Path, commit: str, relative: str, path: Path) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "--filters", f"{commit}:{relative}"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    try:
        disk = path.read_bytes()
    except OSError:
        return False
    blob = completed.stdout
    if disk == blob:
        return True
    return disk.replace(b"\r\n", b"\n") == blob.replace(b"\r\n", b"\n")


def _bounded_remove_tree(root: Path, allowed_parent: Path) -> bool:
    try:
        resolved = root.resolve()
        parent = allowed_parent.resolve()
    except OSError:
        return False
    if resolved == parent or not _is_relative_to(resolved, parent):
        return False
    if _is_reparse(resolved) or _contains_reparse(resolved):
        return False
    try:
        files = _regular_files(resolved)
        directories = _directories(resolved)
    except OSError:
        return False
    for path in files:
        if not _unlink(path):
            return False
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        try:
            os.rmdir(path)
        except OSError:
            return False
    try:
        os.rmdir(resolved)
    except OSError:
        return False
    return not resolved.exists()


def _regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    stack = [root.resolve()]
    while stack:
        current = stack.pop()
        for entry in os.scandir(current):
            if _is_reparse(Path(entry.path)):
                raise OSError(f"reparse point {entry.path}")
            if entry.is_dir(follow_symlinks=False):
                stack.append(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                files.append(Path(entry.path))
    return files


def _directories(root: Path) -> list[Path]:
    found: list[Path] = []
    stack = [root.resolve()]
    while stack:
        current = stack.pop()
        for entry in os.scandir(current):
            if _is_reparse(Path(entry.path)):
                raise OSError(f"reparse point {entry.path}")
            if entry.is_dir(follow_symlinks=False):
                path = Path(entry.path)
                found.append(path)
                stack.append(path)
    return found


def _unlink(path: Path) -> bool:
    try:
        os.unlink(path)
        return True
    except OSError:
        try:
            os.chmod(path, stat.S_IWRITE)
            os.unlink(path)
            return True
        except OSError:
            return False


def _contains_reparse(root: Path) -> bool:
    if _is_reparse(root):
        return True
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            return True
        for entry in entries:
            path = Path(entry.path)
            if _is_reparse(path):
                return True
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
            except OSError:
                return True
    return False


def _inside_managed_parent(repo: Path, workspace: Path) -> bool:
    try:
        parent = managed_worktree_parent(repo).resolve()
        resolved = workspace.resolve()
    except OSError:
        return False
    if resolved == parent:
        return False
    return _is_relative_to(resolved, parent)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_reparse(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    if attributes & _REPARSE_ATTRIBUTE:
        return True
    return stat.S_ISLNK(info.st_mode)


def _windows_directory_in_use(workspace: Path) -> str | None:
    probe = workspace.with_name(f".{workspace.name}.inuse-probe")
    if probe.exists():
        return "directory_in_use_check_failed:probe_name_taken"
    try:
        os.rename(workspace, probe)
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        if winerror in {5, 32} or exc.errno in {13, 16}:
            return "directory_in_use"
        return f"directory_in_use_check_failed:{getattr(exc, 'winerror', exc.errno)}"
    try:
        os.rename(probe, workspace)
    except OSError as exc:
        return f"directory_in_use_check_failed:restore:{probe}:{getattr(exc, 'winerror', exc.errno)}"
    return None


def _posix_directory_in_use(workspace: Path) -> str | None:
    proc = Path("/proc")
    if not proc.is_dir():
        return "process_check_unavailable"
    try:
        root = workspace.resolve()
    except OSError:
        return "process_check_unavailable"
    root_text = str(root)
    try:
        entries = list(proc.iterdir())
    except OSError:
        return "process_check_unavailable"
    for entry in entries:
        if not entry.name.isdigit():
            continue
        cwd_link = entry / "cwd"
        try:
            cwd = cwd_link.resolve()
        except OSError:
            cwd = None
        if cwd is not None and (cwd == root or _is_relative_to(cwd, root)):
            return "directory_in_use"
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            command = ""
        if root_text and root_text in command:
            return "directory_in_use"
    return None


def _git_index_lock(workspace: Path) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--git-path", "index.lock"],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return None
    relative = (completed.stdout or "").strip()
    if not relative:
        return None
    lock = Path(relative)
    if not lock.is_absolute():
        lock = workspace / lock
    try:
        if lock.exists():
            return "directory_in_use"
    except OSError:
        return "directory_in_use"
    return None


def _rev_parse(cwd: Path, ref: str, command_runner: Callable[..., Any]) -> str:
    if not str(ref).strip():
        return ""
    completed = _run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd, command_runner)
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def _is_ancestor(
    repo: Path,
    ancestor: str,
    descendant: str,
    command_runner: Callable[..., Any],
) -> bool:
    if not ancestor or not descendant:
        return False
    completed = _run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        repo,
        command_runner,
    )
    return completed.returncode == 0


def _run(
    command: list[str],
    cwd: Path,
    command_runner: Callable[..., Any],
) -> subprocess.CompletedProcess[str]:
    if command_runner is subprocess.run:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    return command_runner(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
