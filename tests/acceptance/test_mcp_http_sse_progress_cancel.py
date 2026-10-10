"""Acceptance probe: GET /mcp SSE carries progress; cross-POST cancel reaps tools.

Streamable HTTP MCP hosts open GET /mcp as a session event stream and cancel
in-flight tools/call with a concurrent POST notifications/cancelled. The
pre-mission plane answers GET /mcp with 404/405/406 and ignores that
notification, so a heartbeat tool keeps running. This probe starts the
invocation plane as a separate OS process and requires:

1. initialize returns Mcp-Session-Id.
2. GET /mcp without a session is HTTP 404.
3. GET /mcp with the session and Accept text/event-stream stays open and
   delivers notifications/progress for a progressToken tools/call.
4. A concurrent POST notifications/cancelled stops the fixture heartbeat
   tool; the original tools/call returns JSON-RPC -32800.
5. A follow-up REST POST /invoke of the text-reverser still returns the
   declared reverse output.

On the pre-mission plane GET /mcp is not an event stream and the heartbeat
keeps growing after the cancelled notification, so the probe reports
passed=false. Both outcomes exit 0 with JSON ``passed`` and nonempty
``observed``.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

_SLOW_TOOL = r"""
import json, sys, time
from pathlib import Path
state = json.load(sys.stdin)
path = Path(state["heartbeat_path"])
deadline = time.monotonic() + 25
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

PROBE_TEXT = "sse-progress-a93abae1"
EXPECTED = PROBE_TEXT[::-1]
CALL_ID = 42
PROGRESS_TOKEN = "sse-progress-a93abae1"


def _ledger_entry(capability_id: str, name: str) -> dict:
    return {
        "id": capability_id,
        "name": name,
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


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": f"probe {slug}",
                "command": ["python", "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": [
                    {
                        "input": {key: "x" for key in requires},
                        "expect": {key: 1 if key == "beats" else "x" for key in provides},
                    }
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "heartbeat-hold", _SLOW_TOOL, ["heartbeat_path"], ["beats"])
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        "capability.absorbed-heartbeat-hold": _ledger_entry(
            "capability.absorbed-heartbeat-hold", "probe heartbeat hold"
        ),
        "capability.absorbed-text-reverser": _ledger_entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _read_beats(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
) -> tuple[int, object, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            captured = {key.lower(): value for key, value in response.headers.items()}
            raw = response.read().decode("utf-8")
            try:
                parsed: object = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return response.status, parsed, captured
    except HTTPError as exc:
        captured = {key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])}
        try:
            return exc.code, json.loads(exc.read().decode("utf-8")), captured
        except Exception:
            return exc.code, None, captured
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, {}


def _read_http_headers(sock: socket.socket) -> tuple[int, bytes]:
    buf = b""
    sock.settimeout(10)
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    header, rest = buf.split(b"\r\n\r\n", 1) if b"\r\n\r\n" in buf else (buf, b"")
    status_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    parts = status_line.split(" ", 2)
    status = int(parts[1]) if len(parts) >= 2 else 0
    return status, rest


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-http-sse-progress-cancel"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="mcp-http-sse-probe-", ignore_cleanup_errors=True)
    try:
        base = Path(scratch.name)
        root = _build_fixture_root(base)
        heartbeat = root / "capabilities" / "absorbed" / "heartbeat-hold" / "heartbeat.txt"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "blackhole_agent.capability_service",
                "serve",
                "--port",
                "0",
                "--root",
                str(root),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        sse_sock: socket.socket | None = None
        collector: threading.Thread | None = None
        stop_sse = threading.Event()
        try:
            sink: dict[str, object] = {}
            reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
            reader.start()
            reader.join(timeout=60)
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = process.stderr.read() if process.stderr else ""
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:] if isinstance(err, str) else ""
                return {"passed": False, "observed": observed}

            host = "127.0.0.1"
            port = int(ready["listening"])
            mcp = f"http://{host}:{port}/mcp"
            status, handshake, headers = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "mcp-sse-probe", "version": "1"},
                    },
                },
            )
            session = str(headers.get("mcp-session-id") or "")
            result = handshake.get("result") if isinstance(handshake, dict) else None
            observed["initialize_status"] = status
            observed["mcp_session"] = session
            initialize_ok = (
                status == 200
                and bool(session)
                and isinstance(result, dict)
                and "serverInfo" in result
            )

            status, missing, _ = _request("GET", mcp)
            observed["missing_session_status"] = status
            observed["missing_session_body"] = missing
            session_required = status == 404

            hdr = {"Mcp-Session-Id": session}
            events: list[dict] = []
            sse_status = 0
            if session:
                sse_sock = socket.create_connection((host, port), timeout=10)
                sse_sock.sendall(
                    (
                        f"GET /mcp HTTP/1.1\r\n"
                        f"Host: {host}:{port}\r\n"
                        f"Accept: text/event-stream\r\n"
                        f"Mcp-Session-Id: {session}\r\n"
                        f"Connection: keep-alive\r\n"
                        f"\r\n"
                    ).encode("ascii")
                )
                sse_status, pending = _read_http_headers(sse_sock)
                observed["sse_status"] = sse_status
                if sse_status == 200:

                    def _collect() -> None:
                        buf = pending
                        while not stop_sse.is_set() and sse_sock is not None:
                            sse_sock.settimeout(0.4)
                            try:
                                chunk = sse_sock.recv(4096)
                            except TimeoutError:
                                continue
                            except OSError:
                                break
                            if not chunk:
                                break
                            buf += chunk
                            while b"\n\n" in buf:
                                raw, buf = buf.split(b"\n\n", 1)
                                data_lines = [
                                    line[5:].lstrip()
                                    for line in raw.decode("utf-8", errors="replace").splitlines()
                                    if line.startswith("data:")
                                ]
                                if not data_lines:
                                    continue
                                try:
                                    payload = json.loads("\n".join(data_lines))
                                except json.JSONDecodeError:
                                    continue
                                if isinstance(payload, dict):
                                    events.append(payload)

                    collector = threading.Thread(target=_collect, daemon=True)
                    collector.start()

            call_box: dict[str, object] = {}

            def _call() -> None:
                call_box["status"], call_box["body"], _ = _request(
                    "POST",
                    mcp,
                    {
                        "jsonrpc": "2.0",
                        "id": CALL_ID,
                        "method": "tools/call",
                        "params": {
                            "name": "heartbeat-hold",
                            "arguments": {"heartbeat_path": str(heartbeat)},
                            "_meta": {"progressToken": PROGRESS_TOKEN},
                        },
                    },
                    headers=hdr,
                    timeout=40,
                )

            caller = threading.Thread(target=_call, daemon=True)
            caller.start()
            started = time.monotonic()
            first_beat = 0
            while time.monotonic() - started < 15:
                first_beat = _read_beats(heartbeat)
                if first_beat >= 1:
                    break
                time.sleep(0.05)
            observed["first_beat"] = first_beat
            progress_seen = any(
                item.get("method") == "notifications/progress"
                and (item.get("params") or {}).get("progressToken") == PROGRESS_TOKEN
                for item in events
            )
            observed["progress_events"] = events[:8]
            observed["progress_seen"] = progress_seen

            cancel_status, cancel_body, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": CALL_ID},
                },
                headers=hdr,
            )
            observed["cancel_status"] = cancel_status
            observed["cancel_body"] = cancel_body
            caller.join(timeout=12)
            call_status = call_box.get("status")
            call_body = call_box.get("body")
            observed["call_status"] = call_status
            observed["call_body"] = call_body
            cancelled_rpc = (
                call_status == 200
                and isinstance(call_body, dict)
                and (call_body.get("error") or {}).get("code") == -32800
            )

            time.sleep(1.2)
            sample_a = _read_beats(heartbeat)
            time.sleep(0.8)
            sample_b = _read_beats(heartbeat)
            observed["sample_a"] = sample_a
            observed["sample_b"] = sample_b
            stopped = first_beat >= 1 and sample_b == sample_a

            follow_status, follow, _ = _request(
                "POST",
                f"http://{host}:{port}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            output = follow.get("output") if isinstance(follow, dict) else None
            observed["follow_status"] = follow_status
            observed["follow_output"] = output
            follow_ok = (
                follow_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == EXPECTED
            )

            checks = {
                "initialize": initialize_ok,
                "get_without_session_404": session_required,
                "sse_stream_open": sse_status == 200,
                "progress_on_get_stream": progress_seen,
                "tool_started": first_beat >= 1,
                "cancelled_rpc_32800": cancelled_rpc,
                "heartbeats_stopped_after_cancel": stopped,
                "follow_up_invoke_ok": follow_ok,
            }
            observed["checks"] = checks
            return {"passed": all(checks.values()), "observed": observed}
        finally:
            stop_sse.set()
            if sse_sock is not None:
                try:
                    sse_sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sse_sock.close()
                except OSError:
                    pass
            if collector is not None:
                collector.join(timeout=2)
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
    finally:
        try:
            scratch.cleanup()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as exc:
        verdict = {
            "passed": False,
            "observed": {
                "error": type(exc).__name__,
                "detail": str(exc),
                "family": "mcp-http-sse-progress-cancel",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
