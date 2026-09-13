"""Durable at-most-once admission for HTTP capability invocations.

A committed SQLite reservation precedes execution; a committed response
precedes delivery. Reservations are never expired or automatically retried:
after a crash, a tool may already have performed its side effect. A caller
must reconcile an unknown outcome before deliberately choosing a new key.
This does not promise exactly-once effects inside an arbitrary tool.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


class ReceiptError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.payload = {"ok": False, "error": message, "code": code}


def validate_key(key: str) -> None:
    if not isinstance(key, str) or KEY_PATTERN.fullmatch(key) is None:
        raise ReceiptError(400, "invalid_idempotency_key", "Idempotency-Key must be 1-128 ASCII letters, digits, ._:-")


def request_digest(capability_id: Any, provided_input: Any) -> str:
    try:
        encoded = json.dumps(
            {"capability_id": capability_id, "input": provided_input},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReceiptError(400, "invalid_invocation", "invocation must contain finite JSON values") from exc
    return hashlib.sha256(encoded).hexdigest()


class InvocationReceipts:
    """Root-scoped receipts shared by threads and independent server processes.

Only the reservation and response transactions hold the database lock;
unrelated keys execute concurrently. The local active set distinguishes work
this server is still executing from reservations with an unknown outcome
(including those owned by another server). No PID or elapsed-time heuristic
can authorize re-execution. Durable rows contain a request digest, not input.
"""

    def __init__(self, root: Path):
        self.path = Path(root).resolve() / ".blackhole-agent" / "invocation-receipts.sqlite3"
        self._lock = threading.Lock()
        self._active: set[str] = set()

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
                "CREATE TABLE IF NOT EXISTS receipts ("
                "key TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
                "status_code INTEGER, response TEXT)"
            )
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError) as exc:
            raise ReceiptError(
                503, "receipt_store_unavailable",
                "durable receipt storage unavailable; execution will not be retried automatically",
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def _view(self, row: sqlite3.Row) -> dict[str, Any]:
        completed = row["response"] is not None
        return {
            "ok": True,
            "idempotency_key": row["key"],
            "request_digest": row["request_digest"],
            "state": "completed" if completed else (
                "in_progress" if row["key"] in self._active else "outcome_unknown"
            ),
            "status_code": row["status_code"],
            "response": json.loads(row["response"]) if completed else None,
        }

    def lookup(self, key: str) -> dict[str, Any]:
        validate_key(key)
        with self._lock, self._database() as connection:
            row = connection.execute("SELECT * FROM receipts WHERE key = ?", (key,)).fetchone()
            if row is None:
                raise ReceiptError(404, "unknown_invocation", "no invocation exists for this key")
            return self._view(row)

    def execute(
        self,
        key: str,
        capability_id: Any,
        provided_input: Any,
        operation: Callable[[], tuple[int, dict[str, Any]]],
    ) -> tuple[int, dict[str, Any], bool]:
        """Return HTTP status, original response, and whether it was replayed.

        The operation translates known execution failures to HTTP responses;
        these are persisted too because failure does not imply no side effects.
        An unexpected exception or failed completion commit leaves the durable
        reservation in place and exposes an unknown outcome, never a retry.
        """
        validate_key(key)
        digest = request_digest(capability_id, provided_input)
        with self._lock:
            with self._database() as connection:
                row = connection.execute("SELECT * FROM receipts WHERE key = ?", (key,)).fetchone()
                if row is not None:
                    if row["request_digest"] != digest:
                        raise ReceiptError(409, "idempotency_conflict", "key is already bound to a different invocation")
                    if row["response"] is not None:
                        return row["status_code"], json.loads(row["response"]), True
                    state = self._view(row)["state"]
                    raise ReceiptError(
                        409, state,
                        "invocation is still executing" if state == "in_progress" else
                        "execution may already have had side effects; reconcile its outcome before using a new key",
                    )
                connection.execute(
                    "INSERT INTO receipts (key, request_digest) VALUES (?, ?)", (key, digest)
                )
            # Only a successfully committed reservation may reach operation().
            self._active.add(key)
        try:
            status, payload = operation()
            response = json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
            with self._database() as connection:
                connection.execute(
                    "UPDATE receipts SET status_code = ?, response = ? WHERE key = ?",
                    (status, response, key),
                )
            return status, payload, False
        except ReceiptError:
            raise
        except Exception as exc:
            raise ReceiptError(500, "outcome_unknown", "execution outcome is unknown; automatic retry refused") from exc
        finally:
            with self._lock:
                self._active.discard(key)
