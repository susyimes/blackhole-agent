"""Verify ownership, lineage and remaining checkout contents before reclamation."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NamedTuple, Sequence

from blackhole_agent.revision_checkout import RevisionCheckout

_REPARSE_ATTRIBUTE = 0x400
_REPRODUCIBLE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "htmlcov", ".venv"}
_REPRODUCIBLE_FILE_NAMES = frozenset({".coverage"})
_REPRODUCIBLE_SUFFIXES = frozenset({".pyc", ".pyo"})


@dataclass(frozen=True)
class WorktreeRemovalAssessment:
    """Removal decision for one existing mission workspace."""

    removable: bool
    reason: str = ""
    stale_published_tree: bool = False


class _FileState(NamedTuple):
    mode: int
    size: int
    device: int
    inode: int
    mtime_ns: int
    ctime_ns: int


def managed_worktree_parent(repo_path: Path) -> Path:
    """Parent directory Blackhole uses for mission worktrees of this repo."""

    repo = Path(repo_path).resolve()
    return repo.parent / f".{repo.name}-unbound-worktrees"


def git_worktree_remove_command(workspace: Path) -> list[str]:
    if str(workspace) in {"-f", "--force"}:
        raise RuntimeError("git worktree remove must not use --force")
    return ["git", "worktree", "remove", str(workspace)]


def assess_worktree_removal(
    repo_path: Path,
    workspace: Path,
    *,
    branch: str,
    milestone_head: str,
    ancestor_refs: Sequence[str],
    command_runner: Callable[..., Any] = subprocess.run,
    managed_parent: Path | None = None,
) -> WorktreeRemovalAssessment:
    """Return whether this workspace is safe to remove.

    Does not rename or delete. Call :func:`directory_in_use` immediately
    before the actual removal; a process can appear after this assessment.
    ``managed_parent`` defaults to the unbound mission directory. Supervisor
    evolution checkouts pass their own sibling directory and are not treated
    as outside the owned root.
    """

    repo = Path(repo_path)
    target = Path(workspace)
    parent = Path(managed_parent) if managed_parent is not None else managed_worktree_parent(repo)
    if not _inside_parent(parent, target):
        return WorktreeRemovalAssessment(False, "outside_owned_root")

    # Git would otherwise discover an enclosing checkout when this gitfile is gone.
    detached = not os.path.lexists(target / ".git") or _dead_gitfile(target)
    lineage = _lineage_block_reason(
        repo,
        None if detached else target,
        branch=branch,
        milestone_head=milestone_head,
        ancestor_refs=ancestor_refs,
        command_runner=command_runner,
    )
    if lineage is not None:
        return WorktreeRemovalAssessment(False, lineage)
    if detached:
        if _verified_contents(repo, milestone_head, target, command_runner) is not None:
            return WorktreeRemovalAssessment(True, "", stale_published_tree=True)
        return WorktreeRemovalAssessment(False, "stale_directory_has_unique_work")

    try:
        for _ in _tree_entries(target):
            pass
    except OSError:
        return WorktreeRemovalAssessment(False, "reparse_point_present")

    status = _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching", "-z"],
        target,
        command_runner,
    )
    if status.returncode != 0:
        return WorktreeRemovalAssessment(False, "worktree_status_unreadable")

    for record in (status.stdout or "").split("\0"):
        if record and not (record.startswith("!! ") and _is_reproducible_ignored(record[3:])):
            return WorktreeRemovalAssessment(False, "unique_or_uncommitted_work")
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
    return reason or _git_index_lock(target)


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
    contents = _verified_contents(repo, commit, target, command_runner)
    if contents is None or not _inside_parent(managed_worktree_parent(repo), target):
        return False
    try:
        # Delete only the verified inventory. A new file must survive a late write.
        if directory_in_use(target) or dict(_tree_entries(target)) != contents:
            return False
        for path, state in reversed(contents.items()):
            if stat.S_ISDIR(state.mode):
                path.rmdir()
            elif _file_state(path.lstat()) != state or not _unlink(path):
                return False
        target.rmdir()
    except OSError:
        return False
    return True


def _lineage_block_reason(
    repo: Path,
    workspace: Path | None,
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
    checkout = _rev_parse(workspace, "HEAD", command_runner) if workspace is not None else ""
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


def _is_reproducible_ignored(relative: str) -> bool:
    pure = Path(relative)
    if pure.name in _REPRODUCIBLE_FILE_NAMES or pure.suffix in _REPRODUCIBLE_SUFFIXES:
        return True
    return any(
        part in _REPRODUCIBLE_DIR_NAMES or part.endswith(".egg-info")
        for part in pure.parts
    )


def _dead_gitfile(workspace: Path) -> bool:
    """True when ``.git`` is a gitfile and the directory it names is gone."""

    marker = workspace / ".git"
    try:
        if _is_reparse(marker) or not marker.is_file():
            return False
        lines = marker.read_bytes().splitlines()
        if len(lines) != 1 or not lines[0].startswith(b"gitdir: "):
            return False
        target = os.fsdecode(lines[0][8:])
        if target:
            try:
                (workspace / target).lstat()
            except FileNotFoundError:
                return True
    except (OSError, ValueError):
        pass
    return False


def _verified_contents(
    repo: Path,
    commit: str,
    workspace: Path,
    command_runner: Callable[..., Any],
) -> dict[Path, _FileState] | None:
    """Verify the surviving files of a possibly incomplete, unregistered checkout."""
    if not commit or commit.startswith("-") or not _inside_parent(managed_worktree_parent(repo), workspace):
        return None
    try:
        contents = dict(_tree_entries(workspace))
        marker = workspace / ".git"
        if marker in contents and not _dead_gitfile(workspace):
            return None
        files = {
            os.fsencode(path.relative_to(workspace).as_posix()): state
            for path, state in contents.items() if path != marker and stat.S_ISREG(state.mode)
        }
        with tempfile.TemporaryDirectory(prefix="bh-verify-checkout-") as directory:
            scratch = Path(directory)
            checkout = RevisionCheckout(repo, commit, scratch, command_runner)
            if _matches_checkout(checkout, scratch / "rendered", workspace, files):
                return contents
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def _matches_checkout(
    checkout: RevisionCheckout, rendered: Path, workspace: Path, files: dict[bytes, _FileState],
) -> bool:
    modes = checkout.modes()
    extra = files.keys() - modes.keys()
    if extra:
        if not all(_is_reproducible_ignored(os.fsdecode(name)) for name in extra):
            return False
        ignored = checkout.git("check-ignore", "--no-index", "-z", "--stdin", paths=sorted(extra), tree=workspace)
        if set(ignored.split(b"\0")[:-1]) != extra:
            return False

    tracked = {name: state for name, state in files.items() if name in modes}
    for name, state in tracked.items():
        if modes[name] not in {b"100644", b"100755", b"120000"}:
            return False
        if os.name != "nt" and bool(state.mode & stat.S_IXUSR) != (modes[name] == b"100755"):
            return False
    for batch in _checkout_batches(tracked):
        checkout.write(rendered, batch)
        for name in batch:
            relative = os.fsdecode(name)
            reference = rendered / relative
            # core.symlinks=false materializes link text as a regular file.
            if modes[name] == b"120000" and _is_reparse(reference):
                return False
            with reference.open("rb") as expected, (workspace / relative).open("rb") as actual:
                while chunk := expected.read(256 * 1024):
                    if actual.read(len(chunk)) != chunk:
                        return False
                if actual.read(1):
                    return False
            reference.unlink()
    return True


def _checkout_batches(files: dict[bytes, _FileState]) -> Iterator[list[bytes]]:
    """Limit scratch to small groups of files, or one large file at a time."""
    batch: list[bytes] = []
    size = 0
    for name, state in files.items():
        if batch and (len(batch) >= 512 or size + state.size > 8 * 1024 * 1024):
            yield batch
            batch, size = [], 0
        batch.append(name)
        size += state.size
    if batch:
        yield batch


def _file_state(info: os.stat_result) -> _FileState:
    return _FileState(info.st_mode, info.st_size, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)


def _tree_entries(root: Path) -> Iterator[tuple[Path, _FileState]]:
    """Yield parents before descendants, refusing links, special files and unreadable paths."""
    stack = [root]
    while stack:
        directory = stack.pop()
        if _is_reparse(directory):
            raise OSError(f"reparse point {directory}")
        for child in directory.iterdir():
            info = child.lstat()
            if getattr(info, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE:
                raise OSError(f"reparse point {child}")
            if stat.S_ISDIR(info.st_mode):
                stack.append(child)
            elif not stat.S_ISREG(info.st_mode):
                raise OSError(f"unsupported entry {child}")
            yield child, _file_state(info)


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


def _inside_parent(parent: Path, workspace: Path) -> bool:
    try:
        if _is_reparse(parent) or _is_reparse(workspace):
            return False
        parent_resolved = parent.resolve()
        resolved = workspace.resolve()
    except OSError:
        return False
    return resolved != parent_resolved and resolved.is_relative_to(parent_resolved)


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
        if cwd is not None and cwd.is_relative_to(root):
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
    gitdir = (workspace / ".git").absolute()
    completed = _run(["git", f"--git-dir={gitdir}", "rev-parse", "--git-path", "index.lock"], workspace, subprocess.run)
    relative = (completed.stdout or "").strip()
    if completed.returncode != 0 or not relative:
        return None
    try:
        if (workspace / relative).exists():
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
    return command_runner(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=None if command_runner is subprocess.run else 120,
    )
