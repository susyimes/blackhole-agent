"""Interval schedules that fire governed live-plane invokes after hang-up.

``POST /invoke`` occupies the HTTP client for the whole tool runtime, so an
operator cannot arm a capability to run later or on a cadence. This module is
the opt-in timer:

- ``--schedule`` (or ``BLACKHOLE_SCHEDULE``) enables ``POST /schedules``
- a posted ``capability_id``, ``input``, and ``every_seconds`` persist under
  the service root in SQLite and survive process restart
- a background worker fires the same governed invoke path used by REST
  ``POST /invoke``, including after the creating client has hung up
- ``GET /schedules/{id}`` reports last-run status and tool output
- ``DELETE /schedules/{id}`` cancels further fires
- a plane without the flag stays fail-closed: ``GET /health`` reports
  ``schedules`` false and ``POST /schedules`` is ``400 schedules_disabled``

One OS-held guard elects a scheduler for each root, including across server
processes. Standbys keep serving HTTP and take over when the owner releases
the guard. A graceful stop retains ownership until its tools finish.

The next deadline is committed before execution. An abandoned running fire
has an unknown outcome: the new owner marks that schedule interrupted and
does not replay it. Reconcile its effects, then delete and recreate the
schedule deliberately. This cannot promise exactly-once effects in a tool.
"""

from __future__ import annotations

import errno
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator, Mapping

SCHEMA_VERSION = 1
SCHEDULE_ENV = "BLACKHOLE_SCHEDULE"
SCHEDULES_PATH = "/schedules"
SCHEDULES_PATH_PREFIX = "/schedules/"
DB_RELATIVE = Path(".blackhole-agent") / "invocation-schedules.sqlite3"
GUARD_RELATIVE = Path(".blackhole-agent") / "invocation-schedules.guard"
MIN_EVERY_SECONDS = 1
MAX_EVERY_SECONDS = 86_400
MAX_SCHEDULES = 64
WORKER_POLL_SECONDS = 0.2
CAPABILITY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
SCHEDULE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

InvokeFn = Callable[..., dict[str, Any]]


class ScheduleError(Exception):
    """Fail-closed schedule refusal with an HTTP status."""

    def __init__(self, status: int, error: str, extra: Mapping[str, Any] | None = None) -> None:
        super().__init__(error)
        self.status = int(status)
        self.error = str(error)
        self.extra = dict(extra or {})
        self.payload = {"ok": False, "error": self.error, **self.extra}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_from_unix(value: float) -> str:
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_schedule_enabled(
    flag: bool | None = None, *, env: Mapping[str, str] | None = None
) -> bool:
    """Return whether POST /schedules is opted in (CLI flag or env)."""

    if flag:
        return True
    source = env if env is not None else os.environ
    text = str(source.get(SCHEDULE_ENV) or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def parse_schedules_path(path: str) -> str | None:
    """Return ``''`` for the collection, an id for ``/schedules/{id}``, or None."""

    raw = str(path or "").split("?", 1)[0]
    if raw in {SCHEDULES_PATH, f"{SCHEDULES_PATH}/"}:
        return ""
    if not raw.startswith(SCHEDULES_PATH_PREFIX):
        return None
    rest = raw[len(SCHEDULES_PATH_PREFIX) :]
    if not rest or "/" in rest:
        return None
    return rest


def public_schedule_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """HTTP copy of a schedule: stable keys, ISO timestamps."""

    next_fire = record.get("next_fire_at")
    if isinstance(next_fire, (int, float)):
        next_fire = _iso_from_unix(float(next_fire))
    last_run = record.get("last_run_at")
    if isinstance(last_run, (int, float)):
        last_run = _iso_from_unix(float(last_run))
    return {
        "ok": True,
        "capability_id": record.get("capability_id"),
        "created_at": record.get("created_at"),
        "every_seconds": int(record.get("every_seconds") or 0),
        "input": dict(record.get("input") or {}),
        "last_error": record.get("last_error"),
        "last_invocation_id": record.get("last_invocation_id"),
        "last_output": record.get("last_output"),
        "last_run_at": last_run,
        "last_status": record.get("last_status"),
        "next_fire_at": next_fire,
        "run_count": int(record.get("run_count") or 0),
        "schedule_id": record.get("schedule_id"),
        "schema_version": SCHEMA_VERSION,
    }


class SchedulePlane:
    """Persist interval schedules and fire them on a background worker."""

    def __init__(
        self,
        root: Path,
        *,
        enabled: bool = False,
        invoke: InvokeFn | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.enabled = bool(enabled)
        self._invoke = invoke
        self._lock = threading.Lock()
        self._dispatch_lock = threading.Lock()
        self._guard: BinaryIO | None = None
        self._in_flight: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self.root / DB_RELATIVE

    def health(self) -> dict[str, Any]:
        count = 0
        if self.enabled:
            try:
                count = len(self.list_schedules())
            except ScheduleError:
                count = 0
        return {
            "schedules": self.enabled,
            "schedule_count": count,
            "scheduler_role": "disabled" if not self.enabled else ("owner" if self._guard is not None else "standby"),
        }

    def start(self) -> None:
        if not self.enabled or (self._thread is not None and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="invocation-schedules",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        if thread is None or not thread.is_alive():
            self._thread = None
        with self._dispatch_lock:
            self._release_if_idle()

    def create(
        self,
        capability_id: str,
        provided_input: Mapping[str, Any],
        every_seconds: Any,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise ScheduleError(400, "schedules_disabled")
        ident = str(capability_id or "")
        if CAPABILITY_ID_RE.fullmatch(ident) is None:
            raise ScheduleError(400, "capability_id must be 1-128 letters, digits, or ._-:")
        if not isinstance(provided_input, Mapping):
            raise ScheduleError(422, "input must be a JSON object")
        try:
            interval = int(every_seconds)
        except (TypeError, ValueError) as exc:
            raise ScheduleError(400, "every_seconds must be an integer") from exc
        if isinstance(every_seconds, bool) or interval < MIN_EVERY_SECONDS or interval > MAX_EVERY_SECONDS:
            raise ScheduleError(
                400,
                f"every_seconds must be {MIN_EVERY_SECONDS}–{MAX_EVERY_SECONDS}",
            )
        payload = {str(key): value for key, value in dict(provided_input).items()}
        record = {
            "schedule_id": uuid.uuid4().hex,
            "capability_id": ident,
            "input": payload,
            "every_seconds": interval,
            "created_at": _utc_now_iso(),
            "next_fire_at": time.time(),
            "run_count": 0,
            "last_run_at": None,
            "last_status": "pending",
            "last_output": None,
            "last_error": None,
            "last_invocation_id": None,
        }
        with self._lock, self._database() as connection:
            existing = connection.execute("SELECT COUNT(*) AS n FROM schedules").fetchone()
            if int(existing["n"] if existing is not None else 0) >= MAX_SCHEDULES:
                raise ScheduleError(429, "schedule_limit", extra={"max_schedules": MAX_SCHEDULES})
            self._insert(connection, record)
        return public_schedule_record(record)

    def get(self, schedule_id: str) -> dict[str, Any]:
        if not self.enabled:
            raise ScheduleError(400, "schedules_disabled")
        ident = str(schedule_id or "")
        if SCHEDULE_ID_RE.fullmatch(ident) is None:
            raise ScheduleError(400, "schedule_id must be 1-128 ASCII letters, digits, ._:-")
        record = self._load(ident)
        if record is None:
            raise ScheduleError(404, "schedule_unknown")
        return public_schedule_record(record)

    def list_schedules(self) -> list[dict[str, Any]]:
        if not self.enabled:
            raise ScheduleError(400, "schedules_disabled")
        with self._lock, self._database() as connection:
            rows = connection.execute(
                "SELECT * FROM schedules ORDER BY created_at ASC, schedule_id ASC"
            ).fetchall()
        return [public_schedule_record(self._row_to_record(row)) for row in rows]

    def delete(self, schedule_id: str) -> dict[str, Any]:
        if not self.enabled:
            raise ScheduleError(400, "schedules_disabled")
        ident = str(schedule_id or "")
        if SCHEDULE_ID_RE.fullmatch(ident) is None:
            raise ScheduleError(400, "schedule_id must be 1-128 ASCII letters, digits, ._:-")
        with self._lock, self._database() as connection:
            row = connection.execute(
                "SELECT * FROM schedules WHERE schedule_id = ?", (ident,)
            ).fetchone()
            if row is None:
                raise ScheduleError(404, "schedule_unknown")
            record = self._row_to_record(row)
            connection.execute("DELETE FROM schedules WHERE schedule_id = ?", (ident,))
        # Deletion stops future fires, not a tool already executing. Keep its
        # ownership until the worker exits, even when its row is gone.
        payload = public_schedule_record(record)
        payload["cancelled"] = True
        payload["last_status"] = "cancelled"
        return payload

    def dispatch_due(self, *, now: float | None = None) -> int:
        """Only the root's scheduler owner may reserve and start due fires."""

        if not self.enabled:
            return 0
        with self._dispatch_lock:
            if self._stop.is_set() or not self._acquire_ownership():
                return 0
            moment = time.time() if now is None else float(now)
            started = 0
            for record in self._due(moment):
                schedule_id = str(record["schedule_id"])
                with self._lock:
                    if schedule_id in self._in_flight:
                        continue
                claimed = self._claim_due(schedule_id, moment)
                if claimed is None:
                    continue
                with self._lock:
                    self._in_flight.add(schedule_id)
                worker = threading.Thread(
                    target=self._run_tool,
                    args=(schedule_id, str(claimed["capability_id"]), dict(claimed["input"])),
                    name=f"schedule-run-{schedule_id[:8]}",
                    # A graceful interpreter exit must drain governed runs
                    # before releasing the root's ownership to a standby.
                    daemon=False,
                )
                try:
                    worker.start()
                except Exception:
                    with self._lock:
                        self._in_flight.discard(schedule_id)
                    self._finish(schedule_id, status="failed", error="schedule_worker_start_failed")
                    raise
                started += 1
            return started

    def _acquire_ownership(self) -> bool:
        """Nonblocking OS lock; never unlink its file or expire a live owner."""

        if self._guard is not None:
            return True
        path = self.root / GUARD_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        guard = path.open("a+b")
        try:
            guard.seek(0, os.SEEK_END)
            if guard.tell() == 0:
                guard.write(b"\0")
                guard.flush()
            guard.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            guard.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise
        self._guard = guard
        try:
            # Only a newly elected owner may recover durable running rows.
            self._mark_interrupted()
        except BaseException:
            self._release_ownership()
            raise
        return True

    def _release_ownership(self) -> None:
        guard = self._guard
        if guard is not None:
            # Closing releases the OS lock on both supported platforms.
            guard.close()
            self._guard = None

    def _release_if_idle(self) -> None:
        with self._lock:
            if not self._in_flight:
                self._release_ownership()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.dispatch_due()
            except Exception:
                pass
            self._stop.wait(WORKER_POLL_SECONDS)

    def _run_tool(self, schedule_id: str, capability_id: str, provided_input: dict[str, Any]) -> None:
        invoke = self._invoke
        try:
            if invoke is None:
                self._finish(schedule_id, status="failed", error="schedule_invoke_unbound")
                return
            try:
                result = invoke(self.root, capability_id, provided_input, cancel_event=None)
            except Exception as exc:
                error = str(getattr(exc, "error", None) or f"{type(exc).__name__}: {exc}")
                self._finish(schedule_id, status="failed", error=error[:400])
                return
            output = result.get("output") if isinstance(result, Mapping) else None
            invocation_id = result.get("invocation_id") if isinstance(result, Mapping) else None
            self._finish(
                schedule_id,
                status="completed",
                output=dict(output) if isinstance(output, Mapping) else output,
                invocation_id=invocation_id if isinstance(invocation_id, str) else None,
            )
        finally:
            with self._lock:
                self._in_flight.discard(schedule_id)
            with self._dispatch_lock:
                if self._stop.is_set():
                    self._release_if_idle()

    def _finish(
        self,
        schedule_id: str,
        *,
        status: str,
        error: str | None = None,
        output: Any = None,
        invocation_id: str | None = None,
    ) -> None:
        output_text = None if output is None else json.dumps(output, sort_keys=True, separators=(",", ":"))
        with self._lock, self._database() as connection:
            connection.execute(
                "UPDATE schedules SET last_status = ?, last_error = ?, last_output = ?, "
                "last_invocation_id = ?, last_run_at = ?, run_count = run_count + 1 "
                "WHERE schedule_id = ? AND last_status = 'running'",
                (status, error, output_text, invocation_id, time.time(), schedule_id),
            )

    def _due(self, now: float) -> list[dict[str, Any]]:
        with self._lock, self._database() as connection:
            rows = connection.execute(
                "SELECT * FROM schedules WHERE next_fire_at <= ? "
                "AND last_status IN ('pending', 'completed', 'failed') "
                "ORDER BY next_fire_at ASC, schedule_id ASC",
                (float(now),),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def _load(self, schedule_id: str) -> dict[str, Any] | None:
        with self._lock, self._database() as connection:
            row = connection.execute(
                "SELECT * FROM schedules WHERE schedule_id = ?", (schedule_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def _claim_due(self, schedule_id: str, now: float) -> dict[str, Any] | None:
        # Re-read inside the reservation transaction: a concurrent DELETE
        # may have removed a row returned by _due(). Never resurrect it.
        with self._lock, self._database() as connection:
            row = connection.execute(
                "SELECT * FROM schedules WHERE schedule_id = ? AND next_fire_at <= ? "
                "AND last_status IN ('pending', 'completed', 'failed')",
                (schedule_id, now),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE schedules SET last_status = 'running', next_fire_at = ? WHERE schedule_id = ?",
                (now + int(row["every_seconds"]), schedule_id),
            )
            return self._row_to_record(row)

    def _mark_interrupted(self) -> None:
        with self._lock, self._database() as connection:
            connection.execute(
                "UPDATE schedules SET last_status = 'interrupted', last_error = ? WHERE last_status = 'running'",
                ("schedule_outcome_unknown: reconcile effects before deleting and recreating this schedule",),
            )

    def _ensure_schema(self) -> None:
        with self._lock, self._database():
            return

    def _database(self) -> Iterator[sqlite3.Connection]:
        return _schedule_database(self.db_path)

    def _insert(self, connection: sqlite3.Connection, record: Mapping[str, Any]) -> None:
        output = record.get("last_output")
        output_text = None if output is None else json.dumps(output, sort_keys=True, separators=(",", ":"))
        input_text = json.dumps(record.get("input") or {}, sort_keys=True, separators=(",", ":"))
        last_run = record.get("last_run_at")
        connection.execute(
            "INSERT INTO schedules ("
            "schedule_id, capability_id, input_json, every_seconds, created_at, "
            "next_fire_at, run_count, last_run_at, last_status, last_output, "
            "last_error, last_invocation_id"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(record["schedule_id"]),
                str(record["capability_id"]),
                input_text,
                int(record["every_seconds"]),
                str(record["created_at"]),
                float(record["next_fire_at"]),
                int(record.get("run_count") or 0),
                None if last_run is None else float(last_run),
                str(record.get("last_status") or "pending"),
                output_text,
                record.get("last_error"),
                record.get("last_invocation_id"),
            ),
        )

    def _row_to_record(self, row: sqlite3.Row) -> dict[str, Any]:
        try:
            provided_input = json.loads(row["input_json"])
        except (TypeError, json.JSONDecodeError):
            provided_input = {}
        if not isinstance(provided_input, dict):
            provided_input = {}
        output: Any = row["last_output"]
        if isinstance(output, str) and output:
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                pass
        return {
            "schedule_id": row["schedule_id"],
            "capability_id": row["capability_id"],
            "input": provided_input,
            "every_seconds": int(row["every_seconds"]),
            "created_at": row["created_at"],
            "next_fire_at": float(row["next_fire_at"]),
            "run_count": int(row["run_count"] or 0),
            "last_run_at": row["last_run_at"],
            "last_status": row["last_status"],
            "last_output": output,
            "last_error": row["last_error"],
            "last_invocation_id": row["last_invocation_id"],
        }


@contextmanager
def _schedule_database(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schedules ("
            "schedule_id TEXT PRIMARY KEY, "
            "capability_id TEXT NOT NULL, "
            "input_json TEXT NOT NULL, "
            "every_seconds INTEGER NOT NULL, "
            "created_at TEXT NOT NULL, "
            "next_fire_at REAL NOT NULL, "
            "run_count INTEGER NOT NULL DEFAULT 0, "
            "last_run_at REAL, "
            "last_status TEXT NOT NULL DEFAULT 'pending', "
            "last_output TEXT, "
            "last_error TEXT, "
            "last_invocation_id TEXT)"
        )
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


__all__ = [
    "MAX_EVERY_SECONDS",
    "MAX_SCHEDULES",
    "MIN_EVERY_SECONDS",
    "SCHEDULE_ENV",
    "ScheduleError",
    "SchedulePlane",
    "parse_schedules_path",
    "public_schedule_record",
    "resolve_schedule_enabled",
]
