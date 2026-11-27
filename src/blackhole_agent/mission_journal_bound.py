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
from pathlib import Path, PurePosixPath
from typing import Any

from blackhole_agent.file_guard import file_guard

PATH_LIST_KEEP = 32
PATH_SAMPLE = 8
_PATH_FIELDS = ("changed_paths", "behavior_paths")
_REPARSE = 0x400


def path_list_sha256(paths: list[str]) -> str:
    """Identity of a path inventory. Forward slashes, one path per line."""

    digest = hashlib.sha256()
    for index, path in enumerate(paths):
        if index:
            digest.update(b"\n")
        digest.update(str(path).replace("\\", "/").encode("utf-8"))
    return digest.hexdigest()


def bound_path_list(paths: list[Any]) -> tuple[list[Any], dict[str, Any] | None]:
    """Return the list to store and an inventory when the list is longer than the bound."""

    if len(paths) <= PATH_LIST_KEEP or not all(isinstance(item, str) for item in paths):
        return paths, None
    inventory = {
        "bounded": True,
        "count": len(paths),
        "sha256": path_list_sha256(paths),
        "sample_head": [p.replace("\\", "/") for p in paths[:PATH_SAMPLE]],
        "sample_tail": [p.replace("\\", "/") for p in paths[-PATH_SAMPLE:]],
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
    """Compact a closed mission. Retry this same call after a worker exits.

    All original and replacement hashes are recorded before the first install.
    A retry accepts only those two file states. A successful retry returns the
    original receipt, including for archives written by the one-pass compactor.
    """
    mission = Path(mission_dir).absolute()
    state_path = mission / "state.json"
    if _is_reparse(mission) or not mission.is_dir():
        return _refusal("mission_dir_unavailable")
    if allowed_root is not None and not _strictly_inside(Path(allowed_root), mission):
        return _refusal("outside_allowed_root")
    pending = mission / "journal-bound-pending.json"
    if _is_reparse(state_path) or not state_path.is_file():
        return _refusal("journal_conflict" if pending.exists() else "state_missing", "state.json")
    try:
        raw = state_path.read_bytes()
        state = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError) as exc:
        return _refusal("journal_conflict" if pending.exists() else f"state_unreadable:{exc}", "state.json")
    if not isinstance(state, dict) or state.get("status") != "complete":
        if pending.exists():
            return _refusal("journal_conflict", "state.json")
        if not isinstance(state, dict):
            return _refusal("state_not_object")
        return dict(_refusal(f"status_{state.get('status') or 'missing'}"), mission_id=str(state.get("mission_id") or ""))
    try:
        if _is_reparse(state_path.with_name("state.json.guard")):
            return _refusal("journal_conflict", "state guard is a reparse point")
        with file_guard(state_path):
            return _compact(mission, pending, raw, state)
    except (OSError, ValueError, RecursionError) as exc:
        return _refusal("journal_unreadable", str(exc))


def _refusal(reason: str, detail: str = "") -> dict[str, Any]:
    return {"ok": False, "reason": reason, "detail": detail, "files": [], "skipped": []}


def _compact(mission: Path, pending: Path, raw_state: bytes, state: dict[str, Any]) -> dict[str, Any]:
    final = mission / "journal-bound-receipt.json"
    mission_id = str(state.get("mission_id") or mission.name)
    if _is_reparse(final) or _is_reparse(pending) or (final.exists() and pending.exists()):
        return _refusal("journal_conflict", "ambiguous compaction receipt")
    committed = final.exists()
    receipt = None
    if committed or pending.exists():
        try:
            receipt = json.loads((final if committed else pending).read_bytes())
        except (ValueError, RecursionError):
            return _refusal("journal_conflict", "unreadable compaction receipt")
        if (not isinstance(receipt, dict) or receipt.get("ok") is not True
                or receipt.get("mission_id") != mission_id or not isinstance(receipt.get("files"), list)):
            return _refusal("journal_conflict", "invalid compaction receipt")
        if receipt.get("version") != 2 and not (committed and "version" not in receipt):
            return _refusal("journal_conflict", "unknown compaction receipt version")
    elif _sha256_file(mission / "state.json") != hashlib.sha256(raw_state).hexdigest():
        return _refusal("journal_conflict", "state.json changed before compaction acquired the lock")

    skipped: list[dict[str, str]] = []
    paths = [mission / "state.json", *_journal_files(mission, skipped)]
    targets = {path.relative_to(mission).as_posix(): path for path in paths}
    expected = {}
    if receipt is not None:
        if "version" not in receipt:
            # Old receipts store absolute or relative paths and final sizes, but no final hash.
            # Match against discovered files so an archive can be moved without following a stored path.
            try:
                names = [PurePosixPath(row["path"].replace("\\", "/")) for row in receipt["files"]]
                sizes = {name.relative_to(names[0].parent).as_posix(): row["bytes_after"]
                         for name, row in zip(names, receipt["files"])}
            except (AttributeError, IndexError, KeyError, TypeError, ValueError):
                return _refusal("journal_conflict", "invalid legacy receipt")
            if len(sizes) == len(names) and sizes == {name: p.stat().st_size for name, p in targets.items()}:
                return receipt
            return _refusal("journal_conflict", "legacy archive file set or size changed")
        expected = {row["relative_path"]: row for row in receipt["files"]
                    if isinstance(row, dict) and isinstance(row.get("relative_path"), str)
                    and all(isinstance(row.get(k), str) and len(row[k]) == 64 for k in ("sha256_before", "sha256_after"))}
        if expected.keys() != targets.keys() or len(expected) != len(receipt["files"]):
            return _refusal("journal_conflict", "journal file set changed")

    files = []
    installs = []
    try:
        for name, path in targets.items():
            row = expected.get(name)
            if row is not None:
                current = _sha256_file(path)
                if current == row.get("sha256_after"):
                    continue
                if committed or current != row["sha256_before"]:
                    return _refusal("journal_conflict", name)
            prepared = _prepare(path, (raw_state, state) if name == "state.json" else None)
            prepared["relative_path"] = name
            if prepared["outcome"] == "rewritten":
                installs.append((path, prepared))
            if row is not None and (prepared["sha256_before"], prepared["sha256_after"]) != (
                row["sha256_before"], row["sha256_after"]
            ):
                return _refusal("journal_conflict", name)
            files.append(prepared)

        if committed:
            return receipt
        if receipt is None:
            receipt = {
                "ok": True, "reason": "compacted", "version": 2, "mission_id": mission_id,
                "bytes_before": sum(row["bytes_before"] for row in files),
                "bytes_after": sum(row["bytes_after"] for row in files),
                "files": files, "skipped": skipped,
            }
            _atomic_json(pending, receipt)
        for path, row in installs:
            stage = _staging_path(path)
            if (_is_reparse(path) or _is_reparse(stage) or _sha256_file(path) != row["sha256_before"]
                    or _sha256_file(stage) != row["sha256_after"]):
                return _refusal("journal_conflict", row["relative_path"])
            os.replace(stage, path)
        os.replace(pending, final)
        return receipt
    finally:
        for path, _ in installs:
            _staging_path(path).unlink(missing_ok=True)


def _journal_files(mission: Path, skipped: list[dict[str, str]]):
    def accessible(path: Path) -> bool:
        if _is_reparse(path):
            skipped.append({"path": str(path), "reason": "reparse_not_followed"})
            return False
        return True

    for path in [mission / "events.jsonl", *sorted(mission.glob("state*.bak"))]:
        if accessible(path) and path.is_file():
            yield path
    turns = mission / "turns"
    if accessible(turns) and turns.is_dir():
        def on_error(exc: OSError) -> None:
            skipped.append({"path": str(exc.filename), "reason": str(exc)})

        for parent, dirs, names in os.walk(turns, onerror=on_error):
            folder = Path(parent)
            dirs[:] = sorted(name for name in dirs if accessible(folder / name))
            for name in names:
                path = folder / name
                if accessible(path) and name == "turn.json" and path.is_file():
                    yield path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare(path: Path, loaded: tuple[bytes, dict] | None) -> dict[str, Any]:
    """Stage one replacement without modifying the original. Stream events one line at a time."""
    events = path.name == "events.jsonl"
    stage = _staging_path(path)
    before, after = hashlib.sha256(), hashlib.sha256()
    inventories: list[dict[str, Any]] = []
    outcome = "already_bounded"
    try:
        with path.open("rb") as source, _fresh_file(stage) as sink:
            records = source
            if not events:
                records = (loaded[0],) if loaded is not None else (source.read(),)
            for raw in records:
                before.update(raw)
                rendered = raw
                try:
                    if events and not raw.strip():
                        document = None
                    else:
                        document = loaded[1] if loaded is not None else json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    if events:
                        raise
                    document = None
                    outcome = "skipped_unreadable"
                if isinstance(document, dict):
                    previous = len(inventories)
                    _bound_document(document, inventories)
                    if len(inventories) != previous:
                        rendered = _json_bytes(document, indent=None if events else 2)
                elif not events and outcome != "skipped_unreadable":
                    outcome = "skipped_not_object"
                if events or inventories:
                    sink.write(rendered)
                after.update(rendered)
            size_before = source.tell() if loaded is None else len(loaded[0])
            size_after = sink.tell() if inventories else size_before
            if inventories:
                sink.flush()
                os.fsync(sink.fileno())
        if not inventories:
            stage.unlink()
    except BaseException:
        stage.unlink(missing_ok=True)
        raise
    return {
        "path": str(path), "bytes_before": size_before, "bytes_after": size_after,
        "sha256_before": before.hexdigest(), "sha256_after": after.hexdigest(),
        "inventories": inventories, "outcome": "rewritten" if inventories else outcome,
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
        node = node.values()
    elif not isinstance(node, list):
        return
    for child in node:
        if isinstance(child, (dict, list)):
            _bound_document(child, inventories)


def _staging_path(path: Path) -> Path:
    return path.with_name(path.name + ".bound.tmp")


def _fresh_file(path: Path):
    # An interrupted preparation can leave a partial sibling. Never reuse its bytes.
    path.unlink(missing_ok=True)
    return path.open("xb")


def _json_bytes(payload: dict[str, Any], indent: int | None = 2) -> bytes:
    return (json.dumps(payload, indent=indent, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _staging_path(path)
    try:
        with _fresh_file(temporary) as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    target, root = child.resolve(), parent.resolve()
    return target != root and target.is_relative_to(root)
