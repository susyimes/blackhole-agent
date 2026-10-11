"""Acceptance probe: GET /mcp SSE resumes missed events via Last-Event-ID.

Streamable HTTP MCP hosts open GET /mcp as a session event stream. CORS
already advertises Last-Event-ID, but the pre-mission plane writes SSE
events without an id and drops notifications when no GET listener is
attached. A host that reconnects after a dropped GET never receives the
missed tools/list_changed (or progress/logging) notifications.

This probe starts the invocation plane as a separate OS process and
requires:

1. GET /health reports mcp_sse_resume true.
2. POST /mcp initialize returns Mcp-Session-Id.
3. GET /mcp without a session is HTTP 404.
4. GET /mcp with the session and Accept text/event-stream stays open and
   delivers notifications/tools/list_changed with a nonempty SSE id after
   a new proved absorbed capability is written into the served workspace.
5. After that GET is closed, a second ledger mutation is published while
   disconnected. A reconnect GET /mcp that sends Last-Event-ID of the last
   seen event delivers the missed tools/list_changed notification.
6. A subsequent tools/list includes the second late tool and tools/call
   returns its declared reverse output.
7. A follow-up REST POST /invoke of the original text-reverser still
   returns the declared reverse output.

On the pre-mission plane GET /health omits mcp_sse_resume, SSE events have
no id, and a reconnect GET does not replay notifications published while
disconnected, so the probe reports passed=false. Both outcomes exit 0 with
JSON passed and nonempty observed.

The controller copies this file to a scratch path and injects implementation
src via ``python -I`` + sys.path. Serve children must load that injected
tree: import capability_service from sys.path, then replace PYTHONPATH with
that src root only.
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

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

PROBE_TEXT = "sse-resume-d5b94bce"
EXPECTED = PROBE_TEXT[::-1]
LATE_A_TEXT = "late-a-d5b94bce"
LATE_A_EXPECTED = LATE_A_TEXT[::-1]
LATE_A_SLUG = "late-resume-a"
LATE_A_ID = "capability.absorbed-late-resume-a"
LATE_A_TOOL = "late-resume-a"
LATE_B_TEXT = "late-b-d5b94bce"
LATE_B_EXPECTED = LATE_B_TEXT[::-1]
LATE_B_SLUG = "late-resume-b"
LATE_B_ID = "capability.absorbed-late-resume-b"
LATE_B_TOOL = "late-resume-b"


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


def _write_tool(root: Path, slug: str) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": f"probe {slug}",
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


def _write_ledger(root: Path, capabilities: dict, *, bump: float = 5) -> None:
    path = root / "capabilities" / "ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    now = time.time()
    os.utime(path, (now + bump, now + bump))


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "text-reverser")
    _write_ledger(
        root,
        {
            "capability.absorbed-text-reverser": _ledger_entry(
                "capability.absorbed-text-reverser", "probe text reverser"
            ),
        },
    )
    return root


def _add_late_tool(root: Path, slug: str, capability_id: str, name: str, *, bump: float) -> None:
    _write_tool(root, slug)
    ledger_path = root / "capabilities" / "ledger.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    capabilities = dict(payload.get("capabilities") or {})
    capabilities[capability_id] = _ledger_entry(capability_id, name)
    _write_ledger(root, capabilities, bump=bump)


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline() if process.stdout is not None else ""
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


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


def _parse_sse_block(raw: bytes) -> tuple[str, dict | None]:
    event_id = ""
    data_lines: list[str] = []
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    for line in text.splitlines():
        if line.startswith("id:"):
            event_id = line[3:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return event_id, None
    try:
        payload = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return event_id, None
    return event_id, payload if isinstance(payload, dict) else None


def _tool_names(body: object) -> list[str]:
    if not isinstance(body, dict):
        return []
    result = body.get("result") if "result" in body else body
    if not isinstance(result, dict):
        return []
    tools = result.get("tools") or []
    names: list[str] = []
    for item in tools:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return names


def _open_sse(host: str, port: int, session: str, last_event_id: str = "") -> tuple[socket.socket, int, bytes]:
    sock = socket.create_connection((host, port), timeout=10)
    extra = f"Last-Event-ID: {last_event_id}\r\n" if last_event_id != "" else ""
    sock.sendall(
        (
            f"GET /mcp HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Accept: text/event-stream\r\n"
            f"Mcp-Session-Id: {session}\r\n"
            f"{extra}"
            f"Connection: keep-alive\r\n"
            f"\r\n"
        ).encode("ascii")
    )
    status, pending = _read_http_headers(sock)
    return sock, status, pending


def _close_sse(sock: socket.socket | None) -> None:
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def _collect_sse(
    sock: socket.socket,
    pending: bytes,
    events: list[dict],
    stop: threading.Event,
) -> None:
    buf = pending
    while not stop.is_set():
        sock.settimeout(0.4)
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            continue
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        while b"\n\n" in buf:
            raw, buf = buf.split(b"\n\n", 1)
            event_id, payload = _parse_sse_block(raw)
            if not isinstance(payload, dict):
                continue
            events.append({"id": event_id, "payload": payload})


def _wait_list_changed(events: list[dict], seen: int, timeout: float) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for item in events[seen:]:
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if payload.get("method") == "notifications/tools/list_changed":
                return item
        time.sleep(0.05)
    return None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-sse-resume"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    observed["implementation_src"] = str(src_root)
    scratch = tempfile.TemporaryDirectory(prefix="mcp-sse-resume-probe-", ignore_cleanup_errors=True)
    try:
        root = _build_fixture_root(Path(scratch.name))
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
        first_sock: socket.socket | None = None
        resume_sock: socket.socket | None = None
        first_collector: threading.Thread | None = None
        resume_collector: threading.Thread | None = None
        stop_first = threading.Event()
        stop_resume = threading.Event()
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
            health_status, health, _ = _request("GET", f"http://{host}:{port}/health")
            observed["health"] = health
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("mcp_sse_resume") is True
            )

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
                        "clientInfo": {"name": "mcp-sse-resume-probe", "version": "1"},
                    },
                },
            )
            session = str(headers.get("mcp-session-id") or "")
            result = handshake.get("result") if isinstance(handshake, dict) else None
            observed["initialize_status"] = status
            observed["mcp_session"] = session
            initialize_ok = status == 200 and bool(session) and isinstance(result, dict)

            missing_status, _, _ = _request("GET", mcp)
            observed["missing_session_status"] = missing_status
            session_required = missing_status == 404

            hdr = {"Mcp-Session-Id": session}
            first_events: list[dict] = []
            first_status = 0
            if session:
                first_sock, first_status, pending = _open_sse(host, port, session)
                observed["first_sse_status"] = first_status
                if first_status == 200:
                    first_collector = threading.Thread(
                        target=_collect_sse,
                        args=(first_sock, pending, first_events, stop_first),
                        daemon=True,
                    )
                    first_collector.start()

            _add_late_tool(
                root,
                LATE_A_SLUG,
                LATE_A_ID,
                "probe late resume a",
                bump=5,
            )
            first_changed = _wait_list_changed(first_events, 0, 8)
            first_ids = [str(item.get("id") or "") for item in first_events]
            first_methods = [
                (item.get("payload") or {}).get("method")
                for item in first_events
                if isinstance(item.get("payload"), dict)
            ]
            observed["first_sse_ids"] = first_ids
            observed["first_sse_methods"] = first_methods
            last_seen_id = ""
            if first_changed is not None:
                last_seen_id = str(first_changed.get("id") or "")
            if first_ids:
                last_seen_id = next((value for value in reversed(first_ids) if value), last_seen_id)
            observed["last_seen_id"] = last_seen_id
            first_had_id = bool(last_seen_id) and last_seen_id.isdigit()
            first_list_changed = first_changed is not None and first_had_id

            stop_first.set()
            _close_sse(first_sock)
            first_sock = None
            if first_collector is not None:
                first_collector.join(timeout=2)
            time.sleep(0.2)

            resume_events: list[dict] = []
            _add_late_tool(
                root,
                LATE_B_SLUG,
                LATE_B_ID,
                "probe late resume b",
                bump=15,
            )
            time.sleep(1.2)

            resume_status = 0
            if session and last_seen_id:
                resume_sock, resume_status, pending = _open_sse(
                    host, port, session, last_event_id=last_seen_id
                )
                observed["resume_sse_status"] = resume_status
                if resume_status == 200:
                    resume_collector = threading.Thread(
                        target=_collect_sse,
                        args=(resume_sock, pending, resume_events, stop_resume),
                        daemon=True,
                    )
                    resume_collector.start()

            resumed_changed = _wait_list_changed(resume_events, 0, 8)
            resume_ids = [str(item.get("id") or "") for item in resume_events]
            resume_methods = [
                (item.get("payload") or {}).get("method")
                for item in resume_events
                if isinstance(item.get("payload"), dict)
            ]
            observed["resume_sse_ids"] = resume_ids
            observed["resume_sse_methods"] = resume_methods
            replayed = resumed_changed is not None

            after_status, after_listed, _ = _request(
                "POST",
                mcp,
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
                headers=hdr,
            )
            after_names = _tool_names(after_listed)
            observed["tools_after"] = after_names
            late_b_listed = after_status == 200 and LATE_B_TOOL in after_names

            call_status, call_body, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": LATE_B_TOOL,
                        "arguments": {"raw_text": LATE_B_TEXT},
                    },
                },
                headers=hdr,
            )
            structured = None
            if isinstance(call_body, dict):
                structured = (call_body.get("result") or {}).get("structuredContent")
            observed["late_b_call_status"] = call_status
            observed["late_b_call_output"] = structured
            late_b_call_ok = (
                call_status == 200
                and isinstance(structured, dict)
                and structured.get("reversed_text") == LATE_B_EXPECTED
            )

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
                "health_reports_sse_resume": health_ok,
                "initialize_ok": initialize_ok,
                "get_without_session_404": session_required,
                "first_sse_open": first_status == 200,
                "first_list_changed_has_id": first_list_changed,
                "resume_sse_open": resume_status == 200,
                "replayed_list_changed": replayed,
                "late_b_listed": late_b_listed,
                "late_b_call_ok": late_b_call_ok,
                "follow_up_invoke_ok": follow_ok,
            }
            observed["checks"] = checks
            return {"passed": all(checks.values()), "observed": observed}
        finally:
            stop_first.set()
            stop_resume.set()
            _close_sse(first_sock)
            _close_sse(resume_sock)
            if first_collector is not None:
                first_collector.join(timeout=2)
            if resume_collector is not None:
                resume_collector.join(timeout=2)
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
                "family": "mcp-sse-resume",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
