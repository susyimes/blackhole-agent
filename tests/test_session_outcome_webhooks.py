"""Unit tests for HMAC-signed outbound session outcome callbacks."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

import pytest

from blackhole_agent.capability_service import build_server
from blackhole_agent.session_notify import (
    SIGNATURE_HEADER,
    NotifyTargetError,
    normalize_notify_spec,
    validate_notify_url,
    verify_notify_signature,
)

_REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)
SECRET = "notify-secret-fixture"
PROBE_TEXT = "webhook-unit"


def _write_tool(root: Path) -> None:
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_REVERSER, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "text-reverser",
                "name": "fixture reverser",
                "command": ["python", "tool.py"],
                "requires": ["raw_text"],
                "provides": ["reversed_text"],
                "cases": [
                    {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
                    {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    cid = "capability.absorbed-text-reverser"
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    cid: {
                        "id": cid,
                        "name": cid,
                        "kind": "python",
                        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
                        "proof_command": "uv run python -c \"pass\"",
                        "dependencies": [],
                        "behavior_paths": [],
                        "capability_delta": "",
                        "tags": [],
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "last_proved_at": "2026-01-01T00:00:00Z",
                        "last_proof_exit_code": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _start_listener(*, fail_first: bool = False):
    box: dict = {"lock": threading.Lock(), "items": [], "fail_first": fail_first}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            item = {
                "path": self.path,
                "raw": raw,
                "sig": self.headers.get(SIGNATURE_HEADER) or "",
            }
            with box["lock"]:
                box["items"].append(item)
                count = len(box["items"])
            if box["fail_first"] and count == 1:
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/hooks/session"
    return server, thread, url, box


def _stop_listener(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _wait_items(box: dict, count: int, timeout: float = 8.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with box["lock"]:
            if len(box["items"]) >= count:
                return list(box["items"])
        time.sleep(0.02)
    with box["lock"]:
        return list(box["items"])


def _wait_status(base: str, session_id: str, wanted: set[str], timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        status, body = _request("GET", f"{base}/sessions/{session_id}")
        assert status == 200
        session = body["session"]
        if session["status"] in wanted:
            return session
        assert time.monotonic() < deadline, f"session stuck at {session['status']}"
        time.sleep(0.05)


@pytest.fixture()
def plane(tmp_path: Path):
    root = tmp_path / "repo"
    _write_tool(root)
    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=10)


def test_loopback_url_accepted_and_non_loopback_refused() -> None:
    assert validate_notify_url("http://127.0.0.1:9/hooks") == "http://127.0.0.1:9/hooks"
    with pytest.raises(NotifyTargetError):
        validate_notify_url("http://8.8.8.8/hooks")
    with pytest.raises(NotifyTargetError):
        validate_notify_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(NotifyTargetError):
        validate_notify_url("file:///etc/passwd")
    with pytest.raises(NotifyTargetError):
        normalize_notify_spec("http://127.0.0.1:9/hooks", None)
    with pytest.raises(NotifyTargetError):
        normalize_notify_spec(None, SECRET)


def test_terminal_session_posts_signed_callback(plane: str) -> None:
    server, thread, url, box = _start_listener()
    try:
        status, created = _request(
            "POST",
            f"{plane}/sessions",
            {
                "initial_state": {"raw_text": PROBE_TEXT},
                "goal": ["reversed_text"],
                "notify_url": url,
                "notify_secret": SECRET,
            },
        )
        assert status == 200
        session = created["session"]
        assert "notify_secret" not in session
        assert session["notify_secret_present"] is True
        session_id = session["session_id"]
        final = _wait_status(plane, session_id, {"solved"})
        assert final["outcome"] == {"reversed_text": PROBE_TEXT[::-1]}
        assert "notify_secret" not in final
        items = _wait_items(box, 1)
        assert len(items) == 1
        payload = json.loads(items[0]["raw"].decode("utf-8"))
        assert payload["event"] == "session.terminal"
        assert payload["session_id"] == session_id
        assert payload["status"] == "solved"
        assert payload["outcome"] == {"reversed_text": PROBE_TEXT[::-1]}
        assert payload["session_digest"] == final["session_digest"]
        assert verify_notify_signature(SECRET, items[0]["raw"], items[0]["sig"])
        assert not verify_notify_signature("wrong-secret-value", items[0]["raw"], items[0]["sig"])
        delivered = _wait_status(plane, session_id, {"solved"})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not (delivered.get("notify") or {}).get("delivered"):
            time.sleep(0.05)
            delivered = _wait_status(plane, session_id, {"solved"})
        assert delivered["notify"]["delivered"] is True
        assert delivered["notify"]["attempts"] >= 1
    finally:
        _stop_listener(server, thread)


def test_503_then_200_retries_and_marks_delivered(plane: str) -> None:
    server, thread, url, box = _start_listener(fail_first=True)
    try:
        status, created = _request(
            "POST",
            f"{plane}/sessions",
            {
                "initial_state": {"raw_text": PROBE_TEXT},
                "goal": ["reversed_text"],
                "notify_url": url,
                "notify_secret": SECRET,
            },
        )
        assert status == 200
        session_id = created["session"]["session_id"]
        _wait_status(plane, session_id, {"solved"})
        items = _wait_items(box, 2)
        assert len(items) >= 2
        deadline = time.monotonic() + 5
        delivered = False
        while time.monotonic() < deadline:
            _, body = _request("GET", f"{plane}/sessions/{session_id}")
            if (body["session"].get("notify") or {}).get("delivered"):
                delivered = True
                break
            time.sleep(0.05)
        assert delivered
    finally:
        _stop_listener(server, thread)


def test_session_without_notify_does_not_post(plane: str) -> None:
    server, thread, url, box = _start_listener()
    try:
        status, created = _request(
            "POST",
            f"{plane}/sessions",
            {"initial_state": {"raw_text": PROBE_TEXT}, "goal": ["reversed_text"]},
        )
        assert status == 200
        session_id = created["session"]["session_id"]
        assert created["session"].get("notify_url") is None
        _wait_status(plane, session_id, {"solved"})
        time.sleep(0.4)
        with box["lock"]:
            assert box["items"] == []
    finally:
        _stop_listener(server, thread)


def test_non_loopback_notify_url_refused_before_tools(plane: str) -> None:
    status, body = _request(
        "POST",
        f"{plane}/sessions",
        {
            "initial_state": {"raw_text": PROBE_TEXT},
            "goal": ["reversed_text"],
            "notify_url": "http://8.8.8.8/hooks/session",
            "notify_secret": SECRET,
        },
    )
    assert status == 422
    assert body["ok"] is False
    listed = _request("GET", f"{plane}/sessions")
    assert listed[0] == 200
    assert listed[1]["count"] == 0
