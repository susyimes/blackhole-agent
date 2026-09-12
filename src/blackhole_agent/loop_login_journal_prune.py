"""Expire completed rollup repairs without losing recent or unresolved claims.

Receipts and their completion markers age out together. Every append runs
retention, and an explicit prune supports journals that are no longer active.
Only the selected journal and its dedicated guard are written; paths named
inside receipts are never followed.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_RETENTION_DAYS = 365

LOOP_LOGIN_JOURNAL_PRUNE_ID = "capability.loop-login-journal-prune"
LOOP_LOGIN_JOURNAL_PRUNE_DONE_WHEN = (
    "A login-scrub audit trail's rollup repair journal is pruned of aged "
    "repair records so the journal stays bounded without disturbing a live "
    "owner pid in any surviving repo."
)
LOOP_LOGIN_JOURNAL_PRUNE_GOAL = (
    "Repair login-repair-journal bloat: every rollup repair appends a "
    "permanent journal entry, so a trail that drifts for years piles "
    "journal entries up without bound until an operator prunes the journal "
    "by hand."
)
LOOP_LOGIN_JOURNAL_PRUNE_LEFTOVER = (
    "Later genesis can take login-repair-journal bloat so a repair journal "
    "stays bounded without an operator pruning the journal by hand."
)


def prune_login_rollup_repair_journal(
    root: Path | None = None,
    *,
    retention_days: int = DEFAULT_JOURNAL_RETENTION_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically remove completed repairs older than the retention window.

    Age starts at the latest receipt/completion timestamp, never at a date
    inside the old rollup's claims. An ambiguous ID, unresolved preparation,
    unknown schema, or missing/invalid timestamp is kept. Retained bytes are
    copied verbatim, including malformed lines. The journal is untouched on a no-op.
    Append and prune share an OS guard so replacement cannot lose an append.
    """
    from blackhole_agent.loop_login_rollup_journal import (
        login_rollup_repair_journal_path,
        repair_journal_guard,
    )

    path = login_rollup_repair_journal_path(root)
    report: dict[str, Any] = {
        "action": "rollup_repair_journal_prune", "journal_path": str(path),
        "pruned": False, "pruned_count": 0, "pruned_marker_count": 0,
        "kept_count": 0, "retention_days": retention_days,
    }
    if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days < 1:
        return dict(report, reason="invalid_retention_days")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        window = timedelta(days=retention_days)
    except OverflowError:
        return dict(report, reason="invalid_retention_days")
    # Avoid creating either the state directory or a guard for a missing log.
    try:
        path.stat()
    except FileNotFoundError:
        return dict(report, reason="no_journal")
    except OSError as error:
        return dict(report, reason="journal_read_failed", error=str(error))
    try:
        with repair_journal_guard(path):
            return _prune_locked(path, report, moment, window)
    except OSError as error:
        return dict(report, reason="journal_guard_failed", error=str(error))


def _prune_locked(path: Path, report: dict[str, Any], moment: datetime, window: timedelta) -> dict[str, Any]:
    from blackhole_agent.loop_login_prune import _parse_audit_time
    from blackhole_agent.loop_login_rollup_journal import (
        LOGIN_ROLLUP_REPAIR_APPLIED_EVENT,
        is_login_rollup_repair_journal_entry,
    )

    try:
        lines = path.read_bytes().splitlines(keepends=True)
    except FileNotFoundError:
        return dict(report, reason="no_journal")
    except OSError as error:
        return dict(report, reason="journal_read_failed", error=str(error))
    receipts: dict[int, dict[str, Any]] = {}
    groups: dict[str, list[int]] = {}
    markers: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except (ValueError, UnicodeError, RecursionError):
            continue
        if not isinstance(record, dict):
            continue
        repair_id = record.get("repair_id")
        if is_login_rollup_repair_journal_entry(record):
            receipts[index] = record
            if isinstance(repair_id, str) and repair_id:
                groups.setdefault(repair_id, []).append(index)
        elif record.get("event") == LOGIN_ROLLUP_REPAIR_APPLIED_EVENT:
            if isinstance(repair_id, str) and repair_id:
                markers.setdefault(repair_id, []).append((index, record))

    def aged(record: dict[str, Any], keys: tuple[str, ...]) -> bool:
        values = [record[key] for key in keys if key in record]
        if not values:
            return False
        for value in values:
            if not isinstance(value, str):
                return False
            try:
                stamp = _parse_audit_time(value)
                if stamp is None or moment - stamp <= window:
                    return False
            except (ValueError, OverflowError):
                return False
        return True

    dropped: set[int] = set()
    expired = 0

    def known_schema(record: dict[str, Any]) -> bool:
        version = record.get("schema_version", 1)
        return type(version) is int and version == 1

    for index, receipt in receipts.items():
        if not known_schema(receipt):
            continue
        repair_id = receipt.get("repair_id")
        if repair_id is not None and not isinstance(repair_id, str):
            continue
        linked = []
        if repair_id:
            if len(groups[repair_id]) != 1:
                continue
            linked = markers.get(repair_id, [])
        state = receipt.get("state", "applied")  # Original single-line receipts had no state.
        if state not in ("applied", "prepared") or (state == "prepared" and not linked):
            continue
        if not aged(receipt, ("journaled_at", "repaired_at", "applied_at")):
            continue
        if any(
            marker_index < index or not known_schema(marker)
            or not aged(marker, ("applied_at",))
            for marker_index, marker in linked
        ):
            continue
        dropped.add(index)
        dropped.update(marker_index for marker_index, _ in linked)
        expired += 1
    report["kept_count"] = len(receipts) - expired
    if not dropped:
        return dict(report, reason="nothing_stale")
    tmp_name = None
    try:
        handle, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(handle, "wb") as stream:
            for index, line in enumerate(lines):
                if index not in dropped:
                    stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    except OSError as error:
        return dict(report, kept_count=len(receipts), reason="journal_write_failed", error=str(error))
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    return dict(report, pruned=True, pruned_count=expired, pruned_marker_count=len(dropped) - expired,
                reason="aged_out")
