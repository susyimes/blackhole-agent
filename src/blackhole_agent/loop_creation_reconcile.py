"""Reconcile mission creations interrupted before their state file existed.

Experience fuel: on 2026-09-10 a Windows servicing reboot killed the
continuous loop during ``git worktree add``; the checkout stayed locked
initializing with no mission state, and the next loop start overwrote the
``creating_mission`` loop state without recording that the attempt was
interrupted. The abandoned worktree (directory plus branch, no
``missions/<id>/state.json``) is invisible to ``reclaim_mission_worktrees``,
which scans state files only, so it leaked without any durable receipt.

A later look at that same registration (mission 20260910T111645Z-2594c2eb)
found the checkout directory gone while ``git worktree list`` still reported
``locked initializing``. ``git worktree prune`` will not drop a locked
registration, so the stale admin entry survived the directory.

This module makes the interruption reconcilable while preserving the work:
at loop startup, directories in the worktree parent that have no mission
state are named in a durable orphan inventory and in one
``continuous_loop.mission_create_interrupted`` event each. Repeated
reconciliation leaves that receipt unchanged and does not delete a checkout
that is still on disk. A registration whose directory is already gone is
released only when its lock reason is exactly ``initializing`` and no mission
state file exists. The branch ref stays. A lock with any other reason, and a
locked checkout whose directory still exists, are left alone.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
ORPHAN_INVENTORY_NAME = "orphaned-creations.json"
INTERRUPTED_EVENT = "continuous_loop.mission_create_interrupted"
REGISTRATION_RELEASED_EVENT = "continuous_loop.initializing_registration_released"
_INITIALIZING_LOCK = "initializing"
_REPARSE_ATTRIBUTE = 0x400

__all__ = [
    "INTERRUPTED_EVENT",
    "ORPHAN_INVENTORY_NAME",
    "REGISTRATION_RELEASED_EVENT",
    "orphan_inventory_path",
    "reconcile_interrupted_creations",
]


def orphan_inventory_path(repo_path: Path, output_dir: Path | None = None) -> Path:
    from blackhole_agent.unbound import DEFAULT_OUTPUT_DIR, mission_root

    root = mission_root(repo_path, DEFAULT_OUTPUT_DIR if output_dir is None else output_dir)
    return root / ORPHAN_INVENTORY_NAME


def _default_worktree_parent(repo_path: Path) -> Path:
    return repo_path.parent / f".{repo_path.name}-unbound-worktrees"


def _load_inventory(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    orphans = payload.get("orphans")
    if not isinstance(orphans, list):
        orphans = []
    return {"schema_version": SCHEMA_VERSION, "orphans": orphans}


def _git_text(
    repo_path: Path,
    args: list[str],
    *,
    command_runner: Callable[..., Any],
) -> str:
    result = _git_run(repo_path, args, command_runner=command_runner)
    if getattr(result, "returncode", 1) != 0:
        return ""
    return str(getattr(result, "stdout", "") or "").strip()


def _git_run(
    repo_path: Path,
    args: list[str],
    *,
    command_runner: Callable[..., Any],
) -> Any:
    return command_runner(
        args,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _is_reparse(path: Path) -> bool:
    """True only when the path exists and is a link or reparse point.

    A missing path is not a reparse. Callers that delete still have to see
    the directory is absent themselves.
    """

    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _REPARSE_ATTRIBUTE) or path.is_symlink()


def _parse_worktree_porcelain(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("worktree "):
            if current is not None:
                records.append(current)
            current = {"path": line[len("worktree ") :].strip(), "locked": "", "branch": "", "head": "", "prunable": ""}
            continue
        if current is None or not line:
            continue
        if line.startswith("locked"):
            current["locked"] = line[len("locked") :].strip()
        elif line.startswith("branch "):
            current["branch"] = line[len("branch ") :].strip()
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :].strip()
        elif line.startswith("prunable"):
            current["prunable"] = line[len("prunable") :].strip() or "prunable"
    if current is not None:
        records.append(current)
    return records


def _inside_parent(parent: Path, candidate: str) -> bool:
    parent_abs = os.path.normcase(os.path.abspath(parent))
    candidate_abs = os.path.normcase(os.path.abspath(candidate))
    try:
        return os.path.commonpath((parent_abs, candidate_abs)) == parent_abs and candidate_abs != parent_abs
    except ValueError:
        return False


def _worktree_admin(common_dir: Path, workspace: Path) -> Path | None:
    worktrees = common_dir / "worktrees"
    if _is_reparse(worktrees) or not worktrees.is_dir():
        return None
    expected = workspace / ".git"
    for child in worktrees.iterdir():
        if _is_reparse(child) or not child.is_dir():
            continue
        gitdir = child / "gitdir"
        try:
            recorded = gitdir.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if recorded and _same_path(recorded, expected):
            return child
    return None


def _drop_worktree_admin(common_dir: Path, admin: Path) -> bool:
    """Remove one worktree admin directory. Never removes the worktrees root."""

    worktrees = (common_dir / "worktrees").resolve()
    if _is_reparse(admin):
        return False
    target = admin.resolve()
    if target == worktrees or target.parent != worktrees:
        return False
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    return not target.exists()


def _release_missing_initializing_registrations(
    repo_path: Path,
    parent: Path,
    missions_dir: Path,
    *,
    command_runner: Callable[..., Any],
) -> list[dict[str, str]]:
    """Unlock and drop registrations whose checkout directory is already gone.

    Only a lock reason of exactly ``initializing`` is released, and only when
    the path is inside the managed parent and no mission state file exists.
    The branch ref is not deleted. A directory that still exists is not
    touched, even when it carries the same lock.
    """

    if _is_reparse(parent) or not parent.is_dir():
        return []
    porcelain = _git_text(
        repo_path,
        ["git", "worktree", "list", "--porcelain"],
        command_runner=command_runner,
    )
    common_text = _git_text(
        repo_path,
        ["git", "rev-parse", "--git-common-dir"],
        command_runner=command_runner,
    )
    if not porcelain or not common_text:
        return []
    common_dir = Path(common_text)
    if not common_dir.is_absolute():
        common_dir = repo_path / common_dir
    common_dir = common_dir.resolve()
    released: list[dict[str, str]] = []
    for record in _parse_worktree_porcelain(porcelain):
        workspace_text = record["path"]
        initializing = record["locked"] == _INITIALIZING_LOCK
        # A previous unlock can leave the entry prunable. Drop that admin
        # entry too, still only when the directory is already gone.
        already_prunable = record["locked"] == "" and bool(record["prunable"])
        if not initializing and not already_prunable:
            continue
        if not _inside_parent(parent, workspace_text):
            continue
        workspace = Path(workspace_text)
        if workspace.exists() or _is_reparse(workspace):
            continue
        if (missions_dir / workspace.name / "state.json").is_file():
            continue
        admin = _worktree_admin(common_dir, workspace)
        if admin is None:
            continue
        if initializing:
            unlocked = _git_run(
                repo_path,
                ["git", "worktree", "unlock", str(workspace)],
                command_runner=command_runner,
            )
            if getattr(unlocked, "returncode", 1) != 0:
                continue
            if (admin / "locked").exists() or workspace.exists():
                continue
        if not _drop_worktree_admin(common_dir, admin):
            continue
        branch = record["branch"].removeprefix("refs/heads/")
        released.append(
            {
                "mission_id": workspace.name,
                "workspace": str(workspace),
                "branch": branch,
                "head": record["head"],
            }
        )
    return released


def reconcile_interrupted_creations(
    repo_path: Path,
    output_dir: Path | None = None,
    worktree_parent: Path | None = None,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Record a durable receipt for stateless leftover creation worktrees.

    Every directory under the worktree parent without a matching
    ``missions/<name>/state.json`` is an aborted creation leftover. New
    leftovers are named in the orphan inventory and in one
    ``continuous_loop.mission_create_interrupted`` event; known leftovers are
    left unchanged so repeated reconciliation stays idempotent. A checkout
    that is still on disk is never deleted.

    A git registration whose directory is already gone and whose lock reason
    is exactly ``initializing`` is unlocked and its admin entry dropped.
    The branch ref stays. Any other lock, and any directory that still
    exists, is left registered.
    """

    from blackhole_agent.unbound import (
        DEFAULT_OUTPUT_DIR,
        append_jsonl,
        atomic_write_json,
        continuous_loop_events_path,
        mission_root,
        utc_now_iso,
    )

    repo_path = Path(repo_path).resolve()
    output = DEFAULT_OUTPUT_DIR if output_dir is None else output_dir
    parent = (
        Path(worktree_parent).resolve()
        if worktree_parent is not None
        else _default_worktree_parent(repo_path)
    )
    missions_dir = mission_root(repo_path, output) / "missions"
    inventory_path = orphan_inventory_path(repo_path, output)
    inventory = _load_inventory(inventory_path)
    known = {
        str(entry.get("mission_id", "")): entry
        for entry in inventory["orphans"]
        if isinstance(entry, dict)
    }
    report: dict[str, Any] = {
        "ok": True,
        "action": "reconcile_interrupted_creations",
        "worktree_parent": str(parent),
        "inventory_path": str(inventory_path),
        "scanned": 0,
        "registered_skipped": 0,
        "known_orphans": 0,
        "new_orphans": [],
        "released_registrations": [],
    }
    if not parent.is_dir():
        return report

    now = utc_now_iso()
    for workspace in sorted(parent.iterdir()):
        if not workspace.is_dir():
            continue
        report["scanned"] += 1
        mission_id = workspace.name
        if (missions_dir / mission_id / "state.json").is_file():
            report["registered_skipped"] += 1
            continue
        if mission_id in known:
            report["known_orphans"] += 1
            continue
        branch = _git_text(
            repo_path,
            ["git", "-C", str(workspace), "rev-parse", "--abbrev-ref", "HEAD"],
            command_runner=command_runner,
        )
        head = _git_text(
            repo_path,
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            command_runner=command_runner,
        )
        entry = {
            "mission_id": mission_id,
            "workspace": str(workspace),
            "branch": branch,
            "head": head,
            "git_registered": bool(branch),
            "first_seen_at": now,
        }
        inventory["orphans"].append(entry)
        known[mission_id] = entry
        report["new_orphans"].append(entry)
        append_jsonl(
            continuous_loop_events_path(repo_path, output),
            {
                "event": INTERRUPTED_EVENT,
                "at": now,
                "mission_id": mission_id,
                "workspace": str(workspace),
                "branch": branch,
                "head": head,
                "git_registered": bool(branch),
            },
        )

    released = _release_missing_initializing_registrations(
        repo_path,
        parent,
        missions_dir,
        command_runner=command_runner,
    )
    report["released_registrations"] = released
    inventory_changed = False
    for entry in inventory["orphans"]:
        if not isinstance(entry, dict):
            continue
        workspace = str(entry.get("workspace") or "")
        if not workspace or not any(_same_path(workspace, item["workspace"]) for item in released):
            continue
        if entry.get("git_registered") is False and entry.get("registration_released_at"):
            continue
        entry["git_registered"] = False
        entry["registration_released_at"] = now
        inventory_changed = True
    for item in released:
        append_jsonl(
            continuous_loop_events_path(repo_path, output),
            {
                "event": REGISTRATION_RELEASED_EVENT,
                "at": now,
                "mission_id": item["mission_id"],
                "workspace": item["workspace"],
                "branch": item["branch"],
                "head": item["head"],
            },
        )
    if report["new_orphans"] or inventory_changed:
        atomic_write_json(inventory_path, inventory)
    return report
