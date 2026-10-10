"""In-process coverage for HTTP client-disconnect cancellation."""

from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

from blackhole_agent.capability_service import build_server, http_client_disconnected

_SLOW_TOOL = """
import json, sys, time
from pathlib import Path
state = json.load(sys.stdin)
path = Path(state["heartbeat_path"])
deadline = time.monotonic() + 20
n = 0
while time.monotonic() < deadline:
    n += 1
    path.write_text(str(n), encoding="utf-8")
    time.sleep(0.05)
print(json.dumps({"beats": n}))
"""

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


def _entry(capability_id: str) -> dict:
    return {
        "id": capability_id,
        "name": capability_id,
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": slug,
                "command": ["python", "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": [
                    {"input": {key: "x" for key in requires}, "expect": {key: "x" for key in provides}}
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write_tool(root, "heartbeat-hold", _SLOW_TOOL, ["heartbeat_path"], ["beats"])
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    (root / "capabilities").mkdir(exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "capabilities": {
                    "capability.absorbed-heartbeat-hold": _entry("capability.absorbed-heartbeat-hold"),
                    "capability.absorbed-text-reverser": _entry("capability.absorbed-text-reverser"),
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def _beats(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def test_http_client_disconnected_detects_peer_close() -> None:
    left, right = socket.socketpair()
    try:
        assert http_client_disconnected(left) is False
        right.close()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not http_client_disconnected(left):
            time.sleep(0.02)
        assert http_client_disconnected(left) is True
    finally:
        left.close()
        try:
            right.close()
        except OSError:
            pass


def test_aborting_invoke_stops_heartbeat_and_plane_stays_up(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    heartbeat = root / "heartbeat.txt"
    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        body = json.dumps(
            {
                "capability_id": "capability.absorbed-heartbeat-hold",
                "input": {"heartbeat_path": str(heartbeat)},
            }
        ).encode("utf-8")
        sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        sock.sendall(
            (
                f"POST /invoke HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode("ascii")
            + body
        )
        started = time.monotonic()
        while time.monotonic() - started < 15 and _beats(heartbeat) < 1:
            time.sleep(0.05)
        assert _beats(heartbeat) >= 1
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
        time.sleep(1.5)
        sample_a = _beats(heartbeat)
        time.sleep(0.8)
        sample_b = _beats(heartbeat)
        assert sample_b == sample_a

        follow = json.dumps(
            {
                "capability_id": "capability.absorbed-text-reverser",
                "input": {"raw_text": "blackhole"},
            }
        ).encode("utf-8")
        follow_sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        try:
            follow_sock.sendall(
                (
                    f"POST /invoke HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(follow)}\r\n"
                    f"Connection: close\r\n"
                    f"\r\n"
                ).encode("ascii")
                + follow
            )
            response = b""
            follow_sock.settimeout(15)
            while True:
                chunk = follow_sock.recv(4096)
                if not chunk:
                    break
                response += chunk
        finally:
            follow_sock.close()
        assert b"elohkcalb" in response
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)
