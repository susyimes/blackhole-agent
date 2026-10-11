"""Global in-flight cap for untrusted tool trees on the invocation plane.

Per-tree resource limits (memory, process count, CPU seconds) still leave
the host exposed: every concurrent ``POST /invoke`` / ``POST /solve`` /
session step / MCP ``tools/call`` starts another 256 MiB job. Parallel
clients can exhaust RAM without any single tree tripping its own bound.

This limiter admits a small number of owned tool trees at a time. Excess
attempts fail closed with HTTP 429 and never spawn. The cap is read from
``BLACKHOLE_MAX_INFLIGHT`` (default 8, clamped to 1..1024) so an operator
can size it to the host without restarting from source.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

MAX_INFLIGHT_ENV = "BLACKHOLE_MAX_INFLIGHT"
DEFAULT_MAX_INFLIGHT = 8
MIN_MAX_INFLIGHT = 1
MAX_MAX_INFLIGHT = 1024
RETRY_AFTER_SECONDS = 1
ADMISSION_VIOLATION = "admission_limited"


class AdmissionLimited(Exception):
    """The plane already owns the maximum number of untrusted tool trees."""

    def __init__(self, max_inflight: int, inflight: int) -> None:
        self.max_inflight = int(max_inflight)
        self.inflight = int(inflight)
        super().__init__(
            f"too many in-flight tool executions ({self.inflight}/{self.max_inflight})"
        )

    def payload(self) -> dict[str, object]:
        return {
            "violation": ADMISSION_VIOLATION,
            "inflight": self.inflight,
            "max_inflight": self.max_inflight,
            "retry_after": RETRY_AFTER_SECONDS,
        }


def parse_max_inflight(raw: str | None) -> int:
    """Return a host-safe cap; invalid values fall back to the default."""

    text = str(raw or "").strip()
    if not text.isdigit():
        return DEFAULT_MAX_INFLIGHT
    value = int(text)
    if value < MIN_MAX_INFLIGHT or value > MAX_MAX_INFLIGHT:
        return DEFAULT_MAX_INFLIGHT
    return value


class AdmissionLimiter:
    """Thread-safe counting semaphore that never queues: full means refuse."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight = 0
        self._configured: int | None = None

    def configure(self, max_inflight: int | None) -> None:
        """Pin the cap (or clear the pin so the process env is read)."""

        with self._lock:
            if max_inflight is None:
                self._configured = None
                return
            self._configured = parse_max_inflight(str(int(max_inflight)))

    def max_inflight(self) -> int:
        configured = self._configured
        if configured is not None:
            return configured
        return parse_max_inflight(os.environ.get(MAX_INFLIGHT_ENV))

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "inflight": self._inflight,
                "max_inflight": self.max_inflight(),
            }

    def acquire(self) -> None:
        with self._lock:
            cap = self.max_inflight()
            if self._inflight >= cap:
                raise AdmissionLimited(cap, self._inflight)
            self._inflight += 1

    def release(self) -> None:
        with self._lock:
            if self._inflight > 0:
                self._inflight -= 1

    def reset(self) -> None:
        """Drop in-flight accounting. Tests only; live servers never call this."""

        with self._lock:
            self._inflight = 0
            self._configured = None

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()


ADMISSION = AdmissionLimiter()
