"""Bound persisted Unbound turn journals.

A completed mission stored every changed path, including regenerated forage
files, inside each turn record. Those lists were copied into ``turn.json``,
``events.jsonl``, and ``state.json`` until one closed mission held several
gigabytes. Persistence now keeps a short sample plus a sha256 of the full
normalized path list. Compaction rewrites a completed mission directory in
place and refuses an active, blocked, or stopped mission.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

PATH_LIST_KEEP = 32
PATH_SAMPLE = 8
_PATH_FIELDS = ("changed_paths", "behavior_paths")
_REPARSE = 0x400


def path_list_sha256(paths: list[str]) -> str:
    """Identity of a path inventory. Forward slashes, one path per line."""

    normalized = [str(path).replace("\\", "/") for path in paths]
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


def bound_path_list(paths: list[Any]) -> tuple[list[Any], dict[str, Any] | None]:
    """Return the list to store and an inventory when the list is longer than the bound."""

    if len(paths) <= PATH_LIST_KEEP or not all(isinstance(item, str) for item in paths):
        return paths, None
    normalized = [str(path).replace("\\", "/") for path in paths]
    inventory = {
        "bounded": True,
        "count": len(normalized),
        "sha256": path_list_sha256(normalized),
        "sample_head": normalized[:PATH_SAMPLE],
        "sample_tail": normalized[-PATH_SAMPLE:],
    }
    return inventory["sample_head"], inventory


def bound_turn_record(record: dict[str, Any]) -> dict[str, Any]:
    """Copy a turn record, replacing oversized path lists with a sample and digest."""

    copied = json.loads(json.dumps(record, sort_keys=True, ensure_ascii=False))
    _bound_document(copied, [])
    return copied


def write_bounded_turn_files(
    mission_dir: Path,
    record: dict[str, Any],
    *,
    turn_dir: Path,
    mission_id: str,
) -> dict[str, Any]:
    """Write one bounded ``turn.json`` and append the same record to ``events.jsonl``."""

    mission = Path(mission_dir)
    turn = Path(turn_dir)
    if _is_reparse(mission):
        raise ValueError("mission directory is a reparse point")
    if _is_reparse(turn):
        raise ValueError("turn directory is a reparse point")
    if not _strictly_inside(mission, turn):
        raise ValueError("turn directory is outside the mission directory")
    persisted = bound_turn_record(record)
    _atomic_json(turn / "turn.json", persisted)
    _append_jsonl(
        mission / "events.jsonl",
        {"event": "turn.completed", "mission_id": mission_id, **persisted},
    )
    return persisted


def compact_closed_mission_journal(
    mission_dir: Path,
    *,
    allowed_root: Path | None = None,
) -> dict[str, Any]:
    """Rewrite path inventories in one completed mission directory.

    Active, blocked, and stopped missions are left untouched. Reparse points
    are not followed. The receipt records each original file sha256 and the
    path-list digests that replaced oversized inventories.
    """

    mission = Path(mission_dir)
    if _is_reparse(mission) or not mission.is_dir():
        return {"ok": False, "reason": "mission_dir_unavailable", "files": [], "skipped": []}
    if allowed_root is not None and not _strictly_inside(Path(allowed_root), mission):
        return {"ok": False, "reason": "outside_allowed_root", "files": [], "skipped": []}
    state_path = mission / "state.json"
    if _is_reparse(state_path) or not state_path.is_file():
        return {"ok": False, "reason": "state_missing", "files": [], "skipped": []}
    try:
        raw_state = state_path.read_bytes()
        state = json.loads(raw_state.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": f"state_unreadable:{exc}", "files": [], "skipped": []}
    if not isinstance(state, dict):
        return {"ok": False, "reason": "state_not_object", "files": [], "skipped": []}
    status = str(state.get("status") or "")
    if status != "complete":
        return {
            "ok": False,
            "reason": f"status_{status or 'missing'}",
            "mission_id": str(state.get("mission_id") or ""),
            "files": [],
            "skipped": [],
        }

    skipped: list[dict[str, str]] = []
    files: list[dict[str, Any]] = [_rewrite_loaded_state(state_path, raw_state, state)]
    for path in _journal_files(mission, skipped):
        files.append(_rewrite_journal_file(path))
    bytes_before = sum(int(item["bytes_before"]) for item in files)
    bytes_after = sum(int(item["bytes_after"]) for item in files)
    receipt = {
        "ok": True,
        "reason": "compacted",
        "mission_id": str(state.get("mission_id") or mission.name),
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
        "files": files,
        "skipped": skipped,
    }
    _atomic_json(mission / "journal-bound-receipt.json", receipt)
    return receipt


def _journal_files(mission: Path, skipped: list[dict[str, str]]) -> list[Path]:
    found: list[Path] = []
    events = mission / "events.jsonl"
    if events.is_file() and not _is_reparse(events):
        found.append(events)
    elif events.exists():
        skipped.append({"path": str(events), "reason": "reparse_not_followed"})
    for entry in _scandir(mission):
        if entry.name.startswith("state") and entry.name.endswith(".bak"):
            path = Path(entry.path)
            if _is_reparse(path):
                skipped.append({"path": str(path), "reason": "reparse_not_followed"})
            elif entry.is_file(follow_symlinks=False):
                found.append(path)
    turns = mission / "turns"
    if not turns.exists():
        return found
    if _is_reparse(turns):
        skipped.append({"path": str(turns), "reason": "reparse_not_followed"})
        return found
    stack = [turns]
    while stack:
        current = stack.pop()
        if _is_reparse(current):
            skipped.append({"path": str(current), "reason": "reparse_not_followed"})
            continue
        try:
            children = list(os.scandir(current))
        except OSError as exc:
            skipped.append({"path": str(current), "reason": str(exc)})
            continue
        for child in children:
            path = Path(child.path)
            if _is_reparse(path):
                skipped.append({"path": str(path), "reason": "reparse_not_followed"})
                continue
            if child.is_dir(follow_symlinks=False):
                stack.append(path)
            elif child.is_file(follow_symlinks=False) and child.name == "turn.json":
                found.append(path)
    return found


def _scandir(path: Path):
    try:
        return list(os.scandir(path))
    except OSError:
        return []


def _rewrite_loaded_state(path: Path, raw: bytes, state: dict[str, Any]) -> dict[str, Any]:
    inventories: list[dict[str, Any]] = []
    _bound_document(state, inventories)
    if inventories:
        rendered = (json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        _replace_bytes(path, rendered)
        after = rendered
        outcome = "rewritten"
    else:
        after = raw
        outcome = "already_bounded"
    return {
        "path": str(path),
        "bytes_before": len(raw),
        "bytes_after": len(after),
        "sha256_before": hashlib.sha256(raw).hexdigest(),
        "inventories": inventories,
        "outcome": outcome,
    }


def _rewrite_journal_file(path: Path) -> dict[str, Any]:
    if path.name == "events.jsonl":
        return _rewrite_events(path)
    return _rewrite_json_object(path)


def _rewrite_json_object(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    inventories: list[dict[str, Any]] = []
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {
            "path": str(path),
            "bytes_before": len(raw),
            "bytes_after": len(raw),
            "sha256_before": hashlib.sha256(raw).hexdigest(),
            "inventories": [],
            "outcome": "skipped_unreadable",
        }
    if isinstance(payload, dict):
        _bound_document(payload, inventories)
        rendered = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        if inventories:
            _replace_bytes(path, rendered)
            after = rendered
            outcome = "rewritten"
        else:
            after = raw
            outcome = "already_bounded"
    else:
        after = raw
        outcome = "skipped_not_object"
    return {
        "path": str(path),
        "bytes_before": len(raw),
        "bytes_after": len(after),
        "sha256_before": hashlib.sha256(raw).hexdigest(),
        "inventories": inventories,
        "outcome": outcome,
    }


def _rewrite_events(path: Path) -> dict[str, Any]:
    temporary = path.with_name(path.name + ".bound.tmp")
    digest = hashlib.sha256()
    before = 0
    after = 0
    inventories: list[dict[str, Any]] = []
    try:
        with path.open("rb") as source, temporary.open("wb") as sink:
            for line in source:
                before += len(line)
                digest.update(line)
                stripped = line.strip()
                if not stripped:
                    sink.write(line)
                    after += len(line)
                    continue
                payload = json.loads(stripped.decode("utf-8"))
                if isinstance(payload, dict):
                    _bound_document(payload, inventories)
                    rendered = (json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
                else:
                    rendered = line if line.endswith(b"\n") else line + b"\n"
                sink.write(rendered)
                after += len(rendered)
            sink.flush()
            os.fsync(sink.fileno())
        if inventories:
            os.replace(temporary, path)
            outcome = "rewritten"
        else:
            temporary.unlink(missing_ok=True)
            after = before
            outcome = "already_bounded"
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "path": str(path),
        "bytes_before": before,
        "bytes_after": after,
        "sha256_before": digest.hexdigest(),
        "inventories": inventories,
        "outcome": outcome,
    }


def _bound_document(node: Any, inventories: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        for field in _PATH_FIELDS:
            value = node.get(field)
            if not isinstance(value, list):
                continue
            sample, inventory = bound_path_list(value)
            if inventory is None:
                continue
            node[field] = sample
            node[f"{field}_inventory"] = inventory
            inventories.append({"field": field, "count": inventory["count"], "sha256": inventory["sha256"]})
        for value in list(node.values()):
            _bound_document(value, inventories)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, (dict, list)):
                _bound_document(item, inventories)


def _replace_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".bound.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _replace_bytes(
        path,
        (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def _is_reparse(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _REPARSE) or stat.S_ISLNK(info.st_mode)


def _strictly_inside(parent: Path, child: Path) -> bool:
    parent_abs = os.path.abspath(parent)
    child_abs = os.path.abspath(child)
    try:
        return os.path.commonpath([parent_abs, child_abs]) == parent_abs and child_abs != parent_abs
    except ValueError:
        return False
