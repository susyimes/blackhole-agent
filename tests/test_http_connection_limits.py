"""Hermetic tests for HTTP request timeout and connection occupancy caps."""

from __future__ import annotations

import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from blackhole_agent.http_connection_limits import (
    CONNECTION_LIMIT_VIOLATION,
    DEFAULT_HTTP_REQUEST_TIMEOUT,
    DEFAULT_MAX_HTTP_CONNECTIONS,
    HTTP_CONNECTIONS,
    HTTP_REQUEST_TIMEOUT_ENV,
    MAX_HTTP_CONNECTIONS_ENV,
    ConnectionLimiter,
    configure_http_request_timeout,
    current_http_request_timeout,
    parse_http_request_timeout,
    parse_max_http_connections,
    reject_http_connection,
)


def test_parse_http_request_timeout_clamps_and_falls_back() -> None:
    assert parse_http_request_timeout(None) == DEFAULT_HTTP_REQUEST_TIMEOUT
    assert parse_http_request_timeout("") == DEFAULT_HTTP_REQUEST_TIMEOUT
    assert parse_http_request_timeout("nope") == DEFAULT_HTTP_REQUEST_TIMEOUT
    assert parse_http_request_timeout("0") == DEFAULT_HTTP_REQUEST_TIMEOUT
    assert parse_http_request_timeout("999") == DEFAULT_HTTP_REQUEST_TIMEOUT
    assert parse_http_request_timeout("1") == 1
    assert parse_http_request_timeout("15") == 15
    assert parse_http_request_timeout("120") == 120


def test_parse_max_http_connections_clamps_and_falls_back() -> None:
    assert parse_max_http_connections(None) == DEFAULT_MAX_HTTP_CONNECTIONS
    assert parse_max_http_connections("") == DEFAULT_MAX_HTTP_CONNECTIONS
    assert parse_max_http_connections("nope") == DEFAULT_MAX_HTTP_CONNECTIONS
    assert parse_max_http_connections("0") == DEFAULT_MAX_HTTP_CONNECTIONS
    assert parse_max_http_connections("99999") == DEFAULT_MAX_HTTP_CONNECTIONS
    assert parse_max_http_connections("1") == 1
    assert parse_max_http_connections("256") == 256


def test_timeout_pin_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_http_request_timeout(None)
    monkeypatch.setenv(HTTP_REQUEST_TIMEOUT_ENV, "4")
    assert current_http_request_timeout() == 4
    configure_http_request_timeout(2)
    assert current_http_request_timeout() == 2
    configure_http_request_timeout(None)
    monkeypatch.setenv(HTTP_REQUEST_TIMEOUT_ENV, "not-a-number")
    assert current_http_request_timeout() == DEFAULT_HTTP_REQUEST_TIMEOUT


def test_limiter_refuses_when_full_then_releases() -> None:
    limiter = ConnectionLimiter()
    limiter.configure(1)
    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is False
    assert limiter.snapshot() == {"http_connections": 1, "max_http_connections": 1}
    limiter.release()
    assert limiter.try_acquire() is True
    limiter.release()


def test_limiter_reads_env_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = ConnectionLimiter()
    monkeypatch.setenv(MAX_HTTP_CONNECTIONS_ENV, "3")
    assert limiter.max_connections() == 3
    monkeypatch.setenv(MAX_HTTP_CONNECTIONS_ENV, "not-a-number")
    assert limiter.max_connections() == DEFAULT_MAX_HTTP_CONNECTIONS


def test_concurrent_acquire_never_exceeds_cap() -> None:
    limiter = ConnectionLimiter()
    limiter.configure(2)
    acquired: list[int] = []
    refused: list[int] = []

    def attempt() -> None:
        if limiter.try_acquire():
            acquired.append(1)
        else:
            refused.append(1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: attempt(), range(8)))
    assert len(acquired) == 2
    assert len(refused) == 6
    limiter.release()
    limiter.release()


def test_reject_http_connection_writes_503() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2)
    accepted, _addr = server.accept()
    try:
        reject_http_connection(accepted)
        client.settimeout(2)
        data = b""
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\r\n\r\n" in data and len(data) >= 64:
                break
        assert data.startswith(b"HTTP/1.1 503 ")
        assert b"Retry-After: 1" in data
        body = data.split(b"\r\n\r\n", 1)[1]
        payload = json.loads(body.decode("utf-8"))
        assert payload["ok"] is False
        assert payload["violation"] == CONNECTION_LIMIT_VIOLATION
    finally:
        try:
            client.close()
        except OSError:
            pass
        try:
            accepted.close()
        except OSError:
            pass
        server.close()


def test_live_server_times_out_incomplete_request_and_caps_connections(tmp_path: Path) -> None:
    from blackhole_agent.capability_service import build_server

    configure_http_request_timeout(2)
    HTTP_CONNECTIONS.reset()
    HTTP_CONNECTIONS.configure(2)
    root = tmp_path / "repo"
    (root / "capabilities").mkdir(parents=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": {}}),
        encoding="utf-8",
    )
    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = "127.0.0.1", httpd.server_address[1]
        incomplete = (
            f"POST /invoke HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            "Content-Type: application/json\r\nContent-Length: 200\r\n\r\n{"
        ).encode("ascii")
        sock_a = socket.create_connection((host, port), timeout=2)
        sock_a.sendall(incomplete)
        sock_b = socket.create_connection((host, port), timeout=2)
        sock_b.sendall(incomplete)
        time.sleep(0.2)
        overflow = socket.create_connection((host, port), timeout=2)
        overflow.settimeout(2)
        data = b""
        try:
            while True:
                chunk = overflow.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\r\n\r\n" in data:
                    break
        finally:
            overflow.close()
        assert data.startswith(b"HTTP/1.1 503 ")
        payload = json.loads(data.split(b"\r\n\r\n", 1)[1].decode("utf-8"))
        assert payload["violation"] == CONNECTION_LIMIT_VIOLATION
        sock_a.settimeout(4)
        timed = sock_a.recv(4096)
        assert timed == b"" or not timed
        sock_a.close()
        sock_b.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)
        HTTP_CONNECTIONS.reset()
        configure_http_request_timeout(None)
