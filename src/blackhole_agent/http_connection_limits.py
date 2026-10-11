"""Cap HTTP occupancy on the live invocation plane.

Per-tree tool admission still leaves the listen socket exposed: every TCP
client that never finishes headers occupies a ``ThreadingHTTPServer``
thread until the process dies. A slowloris client, or a burst of open
sockets, can exhaust host threads and RAM without ever starting an
untrusted tool or hitting ``BLACKHOLE_MAX_INFLIGHT``.

This limiter:

- applies a request-socket timeout so incomplete headers and bodies are
  dropped instead of blocking a worker forever
- admits a bounded number of HTTP connections at a time; excess sockets
  are answered HTTP 503 with ``violation: connection_limited`` on the
  accept thread and never spawn a handler
- reports the live snapshot on ``GET /health`` so an operator can see
  the cap without a token

Long-running handlers (tool invoke, SSE reverse channels) keep working:
the timeout only fires on blocking socket reads and writes, not on idle
event streams or in-process tool waits. Kernel and git callers do not
use this module.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from http.server import ThreadingHTTPServer
from typing import Any

HTTP_REQUEST_TIMEOUT_ENV = "BLACKHOLE_HTTP_REQUEST_TIMEOUT"
DEFAULT_HTTP_REQUEST_TIMEOUT = 15
MIN_HTTP_REQUEST_TIMEOUT = 1
MAX_HTTP_REQUEST_TIMEOUT = 120

MAX_HTTP_CONNECTIONS_ENV = "BLACKHOLE_MAX_HTTP_CONNECTIONS"
DEFAULT_MAX_HTTP_CONNECTIONS = 256
MIN_MAX_HTTP_CONNECTIONS = 1
MAX_MAX_HTTP_CONNECTIONS = 4096

CONNECTION_LIMIT_VIOLATION = "connection_limited"
CONNECTION_RETRY_AFTER_SECONDS = 1

_timeout_lock = threading.Lock()
_configured_timeout: int | None = None


def parse_http_request_timeout(raw: str | None) -> int:
    """Return a host-safe request timeout; invalid values fall back to the default."""

    text = str(raw or "").strip()
    if not text.isdigit():
        return DEFAULT_HTTP_REQUEST_TIMEOUT
    value = int(text)
    if value < MIN_HTTP_REQUEST_TIMEOUT or value > MAX_HTTP_REQUEST_TIMEOUT:
        return DEFAULT_HTTP_REQUEST_TIMEOUT
    return value


def configure_http_request_timeout(timeout: int | None) -> None:
    """Pin the request timeout (or clear the pin so the process env is read)."""

    global _configured_timeout
    with _timeout_lock:
        if timeout is None:
            _configured_timeout = None
            return
        _configured_timeout = parse_http_request_timeout(str(int(timeout)))


def current_http_request_timeout() -> int:
    """Seconds a client may block while sending headers or a body."""

    with _timeout_lock:
        configured = _configured_timeout
    if configured is not None:
        return configured
    return parse_http_request_timeout(os.environ.get(HTTP_REQUEST_TIMEOUT_ENV))


def parse_max_http_connections(raw: str | None) -> int:
    """Return a host-safe connection cap; invalid values fall back to the default."""

    text = str(raw or "").strip()
    if not text.isdigit():
        return DEFAULT_MAX_HTTP_CONNECTIONS
    value = int(text)
    if value < MIN_MAX_HTTP_CONNECTIONS or value > MAX_MAX_HTTP_CONNECTIONS:
        return DEFAULT_MAX_HTTP_CONNECTIONS
    return value


class ConnectionLimiter:
    """Thread-safe counting semaphore that never queues: full means refuse."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight = 0
        self._configured: int | None = None

    def configure(self, max_connections: int | None) -> None:
        """Pin the cap (or clear the pin so the process env is read)."""

        with self._lock:
            if max_connections is None:
                self._configured = None
                return
            self._configured = parse_max_http_connections(str(int(max_connections)))

    def max_connections(self) -> int:
        configured = self._configured
        if configured is not None:
            return configured
        return parse_max_http_connections(os.environ.get(MAX_HTTP_CONNECTIONS_ENV))

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "http_connections": self._inflight,
                "max_http_connections": self.max_connections(),
            }

    def try_acquire(self) -> bool:
        with self._lock:
            cap = self.max_connections()
            if self._inflight >= cap:
                return False
            self._inflight += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self._inflight > 0:
                self._inflight -= 1

    def reset(self) -> None:
        """Drop occupancy accounting. Tests only; live servers never call this."""

        with self._lock:
            self._inflight = 0
            self._configured = None


HTTP_CONNECTIONS = ConnectionLimiter()


def connection_limit_payload() -> dict[str, Any]:
    snapshot = HTTP_CONNECTIONS.snapshot()
    return {
        "ok": False,
        "error": CONNECTION_LIMIT_VIOLATION,
        "violation": CONNECTION_LIMIT_VIOLATION,
        "http_connections": snapshot["http_connections"],
        "max_http_connections": snapshot["max_http_connections"],
        "retry_after": CONNECTION_RETRY_AFTER_SECONDS,
    }


def reject_http_connection(sock: socket.socket) -> None:
    """Answer 503 on the accept thread and close; never start a handler."""

    body = json.dumps(connection_limit_payload(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    header = (
        "HTTP/1.1 503 Service Unavailable\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Retry-After: {CONNECTION_RETRY_AFTER_SECONDS}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    try:
        sock.settimeout(1)
        sock.sendall(header + body)
    except OSError:
        pass
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that refuses connections past the occupancy cap."""

    daemon_threads = True

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if not HTTP_CONNECTIONS.try_acquire():
            reject_http_connection(request)
            try:
                self.shutdown_request(request)
            except OSError:
                pass
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            HTTP_CONNECTIONS.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            HTTP_CONNECTIONS.release()
