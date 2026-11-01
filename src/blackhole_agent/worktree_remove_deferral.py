"""Remember a mission worktree whose removal already timed out.

Harvested GC on 2026-08-26 spent 600 seconds in ``git worktree remove`` for
mission ``20260825T162001Z-581c83d3`` and then aborted the rest of the pass.
The same-pass continuation still starts that remove again on the next
reclaim. One wedged checkout can therefore consume another 600 seconds
before any other published worktree is considered.

This module records that mission id beside the mission states. A later
reclaim skips ``git worktree remove`` for that id and still reclaims other
published checkouts. The directory stays on disk. Removal never uses
``--force``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFERRAL_NAME = "worktree-remove-deferrals.json"
SCHEMA_VERSION = 1


def deferral_path(repo_path: Path, output_dir: Path) -> Path:
    root = output_dir.resolve() if output_dir.is_absolute() else (repo_path / output_dir).resolve()
    return root / DEFERRAL_NAME


def _empty() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "deferrals": {}}


def load_deferrals(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(payload, dict):
        return _empty()
    deferrals = payload.get("deferrals")
    if not isinstance(deferrals, dict):
        payload = _empty()
    else:
        payload["schema_version"] = SCHEMA_VERSION
        payload["deferrals"] = {
            str(mission_id): record
            for mission_id, record in deferrals.items()
            if str(mission_id) and isinstance(record, dict)
        }
    return payload


def deferred_mission_ids(repo_path: Path, output_dir: Path) -> set[str]:
    payload = load_deferrals(deferral_path(repo_path, output_dir))
    return set(payload["deferrals"])


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def remember_timed_out_remove(
    repo_path: Path,
    output_dir: Path,
    mission_id: str,
    workspace: Path,
    error: str,
) -> None:
    """Persist one timed-out removal so the next pass does not repeat it."""

    mission = str(mission_id or "").strip()
    if not mission:
        return
    path = deferral_path(repo_path, output_dir)
    payload = load_deferrals(path)
    payload["deferrals"][mission] = {
        "error": str(error or "")[:500],
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "workspace": str(workspace),
    }
    _write(path, payload)


def forget_timed_out_remove(repo_path: Path, output_dir: Path, mission_id: str) -> None:
    """Drop a deferral once that checkout is gone or was removed another way."""

    mission = str(mission_id or "").strip()
    if not mission:
        return
    path = deferral_path(repo_path, output_dir)
    payload = load_deferrals(path)
    if mission not in payload["deferrals"]:
        return
    del payload["deferrals"][mission]
    _write(path, payload)
