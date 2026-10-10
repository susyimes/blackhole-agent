"""Acceptance probe: a browser operator drives session elicitation live.

Durable goal sessions already elicit missing keys over REST, but the
operator console only listed them. An operator with a browser could not
create a session, supply pending keys, watch status, or cancel a running
tool without a custom HTTP client. This probe starts the invocation plane
and requires:

1. GET /console is self-contained HTML whose own JavaScript drives
   POST /sessions, POST /sessions/{id}/input, DELETE /sessions/{id},
   POST /sessions/{id}/resume, and GET /sessions/{id}/events with
   Accept text/event-stream.
2. Creating a session whose goal needs an external key answers
   awaiting_input naming that key and does not spawn the tool.
3. GET /sessions/{id}/events without Accept text/event-stream is HTTP
   406; an unknown id is 404.
4. Opening the event stream, then supplying the elicited key, delivers
   session events that reach solved with the declared reverse output.
5. DELETE on a running heartbeat session stops the tool and the stream
   reports cancelled.
6. A follow-up REST POST /invoke of the text-reverser still returns the
   declared reverse output.

On the pre-mission plane GET /sessions/{id}/events is not an event
stream and the console cannot create or elicit sessions, so the probe
reports passed=false. Both outcomes exit 0 with JSON ``passed`` and
nonempty ``observed``.
"""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

PROBE_TEXT = "console-elicit-018d65fd"
EXPECTED = PROBE_TEXT[::-1]

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

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
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    _write_tool(root, "heartbeat-hold", _SLOW_TOOL, ["heartbeat_path"], ["beats"])
    capabilities = {
        "capability.absorbed-text-reverser": _ledger_entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
        "capability.absorbed-heartbeat-hold": _ledger_entry(
            "capability.absorbed-heartbeat-hold", "probe heartbeat hold"
        ),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, object, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
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


def _parse_sse_frames(buf: bytes) -> tuple[list[dict], bytes]:
    events: list[dict] = []
    while b"\n\n" in buf:
        raw, buf = buf.split(b"\n\n", 1)
        payload = None
        event_name = ""
        for line in raw.decode("utf-8", errors="replace").replace("\r", "").split("\n"):
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                text = line[5:].strip()
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = text
        if payload is not None:
            events.append({"event": event_name or "message", "data": payload})
    return events, buf


def _collect_sse(sock: socket.socket, pending: bytes, collected: list[dict], stop: threading.Event) -> None:
    buf = pending
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        frames, buf = _parse_sse_frames(buf)
        collected.extend(frames)


def _read_beats(path: Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def _console_drives_sessions(page: str) -> bool:
    return all(
        marker in page
        for marker in (
            "function createSession()",
            "function supplySessionInput()",
            "function resumeSession()",
            "function cancelSession()",
            "function watchSessionEvents()",
            'postJSON("/sessions"',
            "/input",
            "/resume",
            'method: "DELETE"',
            "/events",
            "text/event-stream",
        )
    )


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "console-session-elicitation"}
    try:
        from blackhole_agent.capability_service import build_server
    except Exception as error:
        observed["error"] = f"{type(error).__name__}: {error}"
        return {"passed": False, "observed": observed}

    with tempfile.TemporaryDirectory(prefix="console-session-probe-") as directory:
        root = _build_fixture_root(Path(directory))
        heartbeat = root / "capabilities" / "absorbed" / "heartbeat-hold" / "heartbeat.txt"
        server = build_server(root, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host = "127.0.0.1"
        port = int(server.server_address[1])
        base = f"http://{host}:{port}"
        sse_sock: socket.socket | None = None
        cancel_sock: socket.socket | None = None
        stop_sse = threading.Event()
        stop_cancel = threading.Event()
        try:
            status, page, headers = _request("GET", f"{base}/console")
            observed["console_status"] = status
            page_text = page if isinstance(page, str) else json.dumps(page)
            observed["content_type"] = headers.get("content-type", "")
            console_ok = (
                status == 200
                and "text/html" in str(headers.get("content-type") or "")
                and _console_drives_sessions(page_text)
                and "capability.absorbed-text-reverser" in page_text
            )
            observed["console_drives_sessions"] = console_ok

            create_status, created, _ = _request(
                "POST",
                f"{base}/sessions",
                {"initial_state": {}, "goal": ["reversed_text"]},
            )
            session = created.get("session") if isinstance(created, dict) else None
            session_id = str((session or {}).get("session_id") or "")
            observed["create_status"] = create_status
            observed["create_status_name"] = (session or {}).get("status")
            observed["pending_keys"] = (session or {}).get("pending_keys")
            elicited_ok = (
                create_status == 200
                and bool(session_id)
                and (session or {}).get("status") == "awaiting_input"
                and (session or {}).get("pending_keys") == ["raw_text"]
                and not heartbeat.exists()
            )

            missing_status, missing, _ = _request("GET", f"{base}/sessions/missing-session/events")
            observed["unknown_events_status"] = missing_status
            unknown_ok = missing_status == 404

            accept_status, accept_body, _ = _request("GET", f"{base}/sessions/{session_id}/events")
            observed["events_without_accept_status"] = accept_status
            observed["events_without_accept_error"] = (
                accept_body.get("error") if isinstance(accept_body, dict) else accept_body
            )
            accept_ok = accept_status == 406 and (
                isinstance(accept_body, dict)
                and accept_body.get("error") == "session_get_events_requires_event_stream"
            )

            sse_sock = socket.create_connection((host, port), timeout=10)
            sse_sock.sendall(
                (
                    f"GET /sessions/{session_id}/events HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    f"Accept: text/event-stream\r\n"
                    f"Connection: keep-alive\r\n"
                    f"\r\n"
                ).encode("ascii")
            )
            sse_status, pending = _read_http_headers(sse_sock)
            observed["sse_status"] = sse_status
            events: list[dict] = []
            collector = threading.Thread(
                target=_collect_sse, args=(sse_sock, pending, events, stop_sse), daemon=True
            )
            collector.start()

            input_status, supplied, _ = _request(
                "POST",
                f"{base}/sessions/{session_id}/input",
                {"input": {"raw_text": PROBE_TEXT}},
            )
            observed["input_status"] = input_status
            deadline = time.monotonic() + 20
            solved_event = None
            while time.monotonic() < deadline and solved_event is None:
                for frame in list(events):
                    data = frame.get("data") if isinstance(frame, dict) else None
                    if isinstance(data, dict) and data.get("status") == "solved":
                        solved_event = data
                        break
                if solved_event is None:
                    time.sleep(0.05)
            stop_sse.set()
            observed["solved_event"] = solved_event
            observed["event_count"] = len(events)
            stream_ok = (
                sse_status == 200
                and input_status == 200
                and isinstance(solved_event, dict)
                and solved_event.get("outcome") == {"reversed_text": EXPECTED}
                and any(frame.get("event") == "session" for frame in events)
            )

            cancel_status, cancel_created, _ = _request(
                "POST",
                f"{base}/sessions",
                {"initial_state": {"heartbeat_path": str(heartbeat)}, "goal": ["beats"]},
            )
            cancel_session = cancel_created.get("session") if isinstance(cancel_created, dict) else None
            cancel_id = str((cancel_session or {}).get("session_id") or "")
            observed["cancel_create_status"] = cancel_status
            observed["cancel_session_id"] = cancel_id

            cancel_sock = socket.create_connection((host, port), timeout=10)
            cancel_sock.sendall(
                (
                    f"GET /sessions/{cancel_id}/events HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    f"Accept: text/event-stream\r\n"
                    f"Connection: keep-alive\r\n"
                    f"\r\n"
                ).encode("ascii")
            )
            cancel_sse_status, cancel_pending = _read_http_headers(cancel_sock)
            cancel_events: list[dict] = []
            cancel_collector = threading.Thread(
                target=_collect_sse,
                args=(cancel_sock, cancel_pending, cancel_events, stop_cancel),
                daemon=True,
            )
            cancel_collector.start()

            first_beat = 0
            beat_deadline = time.monotonic() + 10
            while time.monotonic() < beat_deadline and first_beat < 1:
                first_beat = _read_beats(heartbeat)
                time.sleep(0.05)
            observed["first_beat"] = first_beat
            delete_status, deleted, _ = _request("DELETE", f"{base}/sessions/{cancel_id}")
            observed["delete_status"] = delete_status
            cancelled_event = None
            cancel_deadline = time.monotonic() + 15
            while time.monotonic() < cancel_deadline and cancelled_event is None:
                for frame in list(cancel_events):
                    data = frame.get("data") if isinstance(frame, dict) else None
                    if isinstance(data, dict) and data.get("status") == "cancelled":
                        cancelled_event = data
                        break
                if cancelled_event is None:
                    time.sleep(0.05)
            time.sleep(0.8)
            sample_a = _read_beats(heartbeat)
            time.sleep(0.8)
            sample_b = _read_beats(heartbeat)
            stop_cancel.set()
            observed["cancel_sse_status"] = cancel_sse_status
            observed["cancelled_event"] = cancelled_event
            observed["sample_a"] = sample_a
            observed["sample_b"] = sample_b
            cancel_ok = (
                cancel_sse_status == 200
                and delete_status == 200
                and first_beat >= 1
                and isinstance(cancelled_event, dict)
                and sample_b == sample_a
            )

            follow_status, follow, _ = _request(
                "POST",
                f"{base}/invoke",
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
                "console_drives_sessions": console_ok,
                "elicited_awaiting_input": elicited_ok,
                "unknown_events_404": unknown_ok,
                "events_require_accept_406": accept_ok,
                "events_reach_solved": stream_ok,
                "cancel_stops_heartbeat": cancel_ok,
                "follow_up_invoke_ok": follow_ok,
            }
            observed["checks"] = checks
            return {"passed": bool(all(checks.values())), "observed": observed}
        finally:
            stop_sse.set()
            stop_cancel.set()
            for sock in (sse_sock, cancel_sock):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as error:  # never crash the sweep: unmet, not crashed
        verdict = {
            "passed": False,
            "observed": {
                "family": "console-session-elicitation",
                "fatal": f"{type(error).__name__}: {error}",
            },
        }
    print(json.dumps(verdict))
    raise SystemExit(0)
