"""Reconcile mission creations interrupted before their state file existed.

Experience fuel: on 2026-09-10 a Windows servicing reboot killed the
continuous loop during ``git worktree add``; the checkout stayed locked
initializing with no mission state, and the next loop start overwrote the
``creating_mission`` loop state without recording that the attempt was
interrupted. The abandoned worktree (directory plus branch, no
``missions/<id>/state.json``) is invisible to ``reclaim_mission_worktrees``,
which scans state files only, so it leaked without any durable receipt.

This module makes the interruption reconcilable while preserving the work:
at loop startup, directories in the worktree parent that have no mission
state are named in a durable orphan inventory and in one
``continuous_loop.mission_create_interrupted`` event each. Repeated
reconciliation leaves the receipt unchanged, registered missions are
untouched, and the abandoned worktree and branch are never deleted.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
ORPHAN_INVENTORY_NAME = "orphaned-creations.json"
INTERRUPTED_EVENT = "continuous_loop.mission_create_interrupted"

__all__ = [
    "INTERRUPTED_EVENT",
    "ORPHAN_INVENTORY_NAME",
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
    result = command_runner(
        args,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if getattr(result, "returncode", 1) != 0:
        return ""
    return str(getattr(result, "stdout", "") or "").strip()


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
    left unchanged so repeated reconciliation stays idempotent. Nothing is
    deleted.
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

    if report["new_orphans"]:
        atomic_write_json(inventory_path, inventory)
    return report
