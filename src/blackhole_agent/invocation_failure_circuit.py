"""Persisted consecutive-failure circuit for governed tool invokes.

A capability that exits nonzero three times in a row is closed: later
``POST /invoke`` calls return HTTP 409 ``capability_circuit_open`` and do
not spawn. The streak and the open flag live in SQLite under the service
root, so a process restart keeps the circuit closed. One successful exit
before the threshold clears the streak. ``POST /circuits/{id}`` with
``{"action": "close"}`` clears an open circuit so the next call can spawn.
A different capability is unaffected.

Resource-limit quarantine is a separate ledger flag. Callers record
completed nonzero exits, wall-clock timeouts, and zero exits that do not
return the declared JSON output. Admission limits, operator cancellation,
and resource-limit quarantine are not circuit failures.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

FAILURE_CIRCUIT_THRESHOLD = 3
CIRCUITS_PREFIX = "/circuits/"
DB_RELATIVE = Path(".blackhole-agent") / "invocation-failure-circuit.sqlite3"
CAPABILITY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


class CircuitStoreError(Exception):
    """The circuit database could not be read or written."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def parse_circuit_path(path: str) -> str | None:
    """Return the capability id for ``/circuits/{id}``, or None for other paths."""

    raw = str(path or "").split("?", 1)[0]
    if not raw.startswith(CIRCUITS_PREFIX):
        return None
    rest = raw[len(CIRCUITS_PREFIX) :]
    if not rest or "/" in rest:
        return None
    return rest


def validate_capability_id(capability_id: str) -> str:
    ident = str(capability_id or "")
    if CAPABILITY_ID_RE.fullmatch(ident) is None:
        raise ValueError("capability_id must be 1-128 letters, digits, or ._:-")
    return ident


def failure_circuit_health(root: Path) -> dict[str, Any]:
    """Health fragment. A store error still reports the feature as present."""

    payload = {
        "failure_circuit": True,
        "failure_circuit_threshold": FAILURE_CIRCUIT_THRESHOLD,
        "failure_circuit_open": 0,
        "failure_circuit_counts_timeout": True,
        "failure_circuit_counts_undeclared_output": True,
    }
    try:
        payload["failure_circuit_open"] = FailureCircuit(root).open_count()
    except CircuitStoreError:
        payload["failure_circuit_open"] = 0
    return payload


def public_circuit_view(capability_id: str, view: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "capability_id": capability_id,
        "open": bool(view["open"]),
        "consecutive_failures": int(view["consecutive_failures"]),
        "threshold": int(view["threshold"]),
    }


class FailureCircuit:
    """Root-scoped streak counter shared by threads and later processes."""

    def __init__(self, root: Path, *, threshold: int = FAILURE_CIRCUIT_THRESHOLD) -> None:
        self.root = Path(root).resolve()
        self.threshold = int(threshold)
        if self.threshold < 1:
            raise ValueError("threshold must be at least 1")
        self.path = self.root / DB_RELATIVE
        self._lock = _lock_for(self.path)

    @contextmanager
    def _database(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS circuits ("
                "capability_id TEXT PRIMARY KEY, "
                "consecutive_failures INTEGER NOT NULL, "
                "open INTEGER NOT NULL, "
                "updated_at TEXT NOT NULL)"
            )
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError) as exc:
            raise CircuitStoreError("failure circuit storage unavailable") from exc
        finally:
            if connection is not None:
                connection.close()

    def _empty(self, capability_id: str) -> dict[str, Any]:
        return {
            "capability_id": capability_id,
            "open": False,
            "consecutive_failures": 0,
            "threshold": self.threshold,
        }

    def _from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "capability_id": str(row["capability_id"]),
            "open": bool(row["open"]),
            "consecutive_failures": int(row["consecutive_failures"]),
            "threshold": self.threshold,
        }

    def view(self, capability_id: str) -> dict[str, Any]:
        ident = validate_capability_id(capability_id)
        with self._lock, self._database() as connection:
            row = connection.execute(
                "SELECT * FROM circuits WHERE capability_id = ?", (ident,)
            ).fetchone()
        if row is None:
            return self._empty(ident)
        return self._from_row(row)

    def open_count(self) -> int:
        with self._lock, self._database() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM circuits WHERE open = 1"
            ).fetchone()
        return int(row["n"] if row is not None else 0)

    def note_failure(self, capability_id: str) -> dict[str, Any]:
        """Count one completed failure. The call that reaches the threshold opens the circuit."""

        ident = validate_capability_id(capability_id)
        with self._lock, self._database() as connection:
            row = connection.execute(
                "SELECT * FROM circuits WHERE capability_id = ?", (ident,)
            ).fetchone()
            if row is not None and bool(row["open"]):
                return self._from_row(row)
            consecutive = int(row["consecutive_failures"] if row is not None else 0) + 1
            opened = 1 if consecutive >= self.threshold else 0
            connection.execute(
                "INSERT INTO circuits (capability_id, consecutive_failures, open, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(capability_id) DO UPDATE SET "
                "consecutive_failures = excluded.consecutive_failures, "
                "open = excluded.open, updated_at = excluded.updated_at",
                (ident, consecutive, opened, _utc_now_iso()),
            )
            stored = connection.execute(
                "SELECT * FROM circuits WHERE capability_id = ?", (ident,)
            ).fetchone()
        if stored is None:
            raise CircuitStoreError("failure circuit write did not persist")
        return self._from_row(stored)

    def note_success(self, capability_id: str) -> dict[str, Any]:
        """A successful exit before the threshold clears the streak."""

        ident = validate_capability_id(capability_id)
        with self._lock, self._database() as connection:
            connection.execute("DELETE FROM circuits WHERE capability_id = ?", (ident,))
        return self._empty(ident)

    def close(self, capability_id: str) -> dict[str, Any]:
        """Operator close. Idempotent when the circuit is already clear."""

        ident = validate_capability_id(capability_id)
        with self._lock, self._database() as connection:
            connection.execute("DELETE FROM circuits WHERE capability_id = ?", (ident,))
        return self._empty(ident)
