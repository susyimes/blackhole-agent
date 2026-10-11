"""Acceptance probe: GET /mcp SSE pushes resources/updated for a watched URI.

Streamable HTTP MCP hosts currently see resources.subscribe=false and
resources/subscribe as method-not-found, so a host that opened GET /mcp
never receives notifications/resources/updated when a watched catalog URI
is quarantined or reinstated. This probe starts the invocation plane as a
separate OS process and requires:

1. GET /health reports mcp_resource_subscribe.
2. POST /mcp initialize advertises resources.subscribe=true and returns
   Mcp-Session-Id.
3. GET /mcp without a session is HTTP 404.
4. POST resources/subscribe for the watch-target catalog URI succeeds.
5. GET /mcp with the session and Accept text/event-stream stays open.
6. After that URI is quarantined in the served workspace, the open GET
   stream delivers notifications/resources/updated for it (and not for the
   unwatched catalog index) without the client re-reading first.
7. A subsequent resources/read of the watched URI shows available false.
8. Reinstating the URI delivers another updated notification and
   resources/read shows available true.
9. An unknown URI is JSON-RPC -32002.
10. A follow-up REST POST /invoke of the original text-reverser still
    returns the declared reverse output.

On the pre-mission plane initialize advertises subscribe=false and
resources/subscribe is method-not-found, so the probe reports passed=false.
Both outcomes exit 0 with JSON ``passed`` and nonempty ``observed``.

The controller copies this file to a scratch path and injects implementation
src via ``python -I`` + sys.path. Serve children must load that injected
tree: import capability_service from sys.path, then replace PYTHONPATH with
that src root only. Joining ambient PYTHONPATH or deriving src from
``__file__`` leaks the candidate tree into the baseline run.
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

PROBE_TEXT = "resource-subscribe-8e932ba0"
EXPECTED = PROBE_TEXT[::-1]
WATCH_SLUG = "watch-target"
WATCH_ID = "capability.absorbed-watch-target"
WATCH_URI = "blackhole://capabilities/capability.absorbed-watch-target"
CATALOG_URI = "blackhole://capabilities"
REVERSER_ID = "capability.absorbed-text-reverser"


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


def _write_ledger(root: Path, capabilities: dict) -> None:
    path = root / "capabilities" / "ledger.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    now = time.time()
    os.utime(path, (now + 5, now + 5))


def _build_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "text-reverser")
    _write_tool(root, WATCH_SLUG)
    _write_ledger(
        root,
        {
            REVERSER_ID: _ledger_entry(REVERSER_ID, "probe text reverser"),
            WATCH_ID: _ledger_entry(WATCH_ID, "probe watch target"),
        },
    )
    return root


def _mutate_quarantine(root: Path, *, quarantined: bool) -> None:
    path = root / "capabilities" / "ledger.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    capabilities = dict(payload.get("capabilities") or {})
    entry = dict(capabilities.get(WATCH_ID) or {})
    if quarantined:
        entry["resource_quarantine"] = {
            "reason": "probe",
            "resource": "memory",
            "quarantined_at": "2026-01-01T00:00:00Z",
        }
    else:
        entry.pop("resource_quarantine", None)
    capabilities[WATCH_ID] = entry
    _write_ledger(root, capabilities)


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


def _error_code(payload: object) -> object:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    return error.get("code")


def _resource_available(payload: object) -> object:
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    contents = result.get("contents") or []
    if not contents or not isinstance(contents[0], dict):
        return None
    try:
        body = json.loads(str(contents[0].get("text") or ""))
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    return body.get("available")


def _updated_uris(events: list[dict]) -> list[str]:
    uris: list[str] = []
    for item in events:
        if item.get("method") != "notifications/resources/updated":
            continue
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        uri = str(params.get("uri") or "")
        if uri:
            uris.append(uri)
    return uris


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-resource-subscribe"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    observed["implementation_src"] = str(src_root)
    scratch = tempfile.TemporaryDirectory(prefix="mcp-resource-subscribe-probe-", ignore_cleanup_errors=True)
    try:
        root = _build_root(Path(scratch.name))
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
            base = f"http://{host}:{port}"
            mcp = f"{base}/mcp"
            health_status, health, _ = _request("GET", f"{base}/health")
            observed["health"] = health
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("mcp_resource_subscribe") is True
            )

            init_status, handshake, headers = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "mcp-resource-subscribe-probe", "version": "1"},
                    },
                },
            )
            session = str(headers.get("mcp-session-id") or "")
            result = handshake.get("result") if isinstance(handshake, dict) else None
            advertised = (
                ((result or {}).get("capabilities") or {}).get("resources")
                if isinstance(result, dict)
                else None
            )
            observed["initialize_status"] = init_status
            observed["mcp_session"] = bool(session)
            observed["resources_subscribe_advertised"] = advertised
            initialize_ok = (
                init_status == 200
                and bool(session)
                and isinstance(result, dict)
                and "serverInfo" in result
                and isinstance(advertised, dict)
                and advertised.get("subscribe") is True
            )

            missing_status, _, _ = _request("GET", mcp)
            observed["missing_session_status"] = missing_status
            session_required = missing_status == 404

            hdr = {"Mcp-Session-Id": session} if session else None
            sub_status, sub_body, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "resources/subscribe",
                    "params": {"uri": WATCH_URI},
                },
                headers=hdr,
            )
            observed["subscribe_status"] = sub_status
            observed["subscribe_body"] = sub_body
            subscribe_ok = (
                sub_status == 200
                and isinstance(sub_body, dict)
                and sub_body.get("result") == {}
                and "error" not in sub_body
            )

            unknown_status, unknown_body, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "resources/subscribe",
                    "params": {"uri": "blackhole://capabilities/missing"},
                },
                headers=hdr,
            )
            unknown_code = _error_code(unknown_body)
            observed["unknown_subscribe_code"] = unknown_code
            unknown_ok = unknown_status == 200 and unknown_code == -32002

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

            _mutate_quarantine(root, quarantined=True)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if WATCH_URI in _updated_uris(events):
                    break
                time.sleep(0.05)
            after_quarantine = _updated_uris(events)
            observed["updated_after_quarantine"] = after_quarantine
            quarantine_updated = after_quarantine == [WATCH_URI]

            read_status, read_body, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "resources/read",
                    "params": {"uri": WATCH_URI},
                },
                headers=hdr,
            )
            quarantined_available = _resource_available(read_body)
            observed["quarantined_available"] = quarantined_available
            read_quarantined_ok = read_status == 200 and quarantined_available is False

            _mutate_quarantine(root, quarantined=False)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if _updated_uris(events).count(WATCH_URI) >= 2:
                    break
                time.sleep(0.05)
            after_reinstatement = _updated_uris(events)
            observed["updated_after_reinstatement"] = after_reinstatement
            reinstated_updated = after_reinstatement == [WATCH_URI, WATCH_URI]

            live_status, live_body, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "resources/read",
                    "params": {"uri": WATCH_URI},
                },
                headers=hdr,
            )
            live_available = _resource_available(live_body)
            observed["reinstated_available"] = live_available
            read_reinstated_ok = live_status == 200 and live_available is True

            follow_status, follow, _ = _request(
                "POST",
                f"{base}/invoke",
                {"capability_id": REVERSER_ID, "input": {"raw_text": PROBE_TEXT}},
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
                "health_ok": health_ok,
                "initialize_subscribe": initialize_ok,
                "get_without_session_404": session_required,
                "subscribe_ok": subscribe_ok,
                "unknown_uri_not_found": unknown_ok,
                "sse_stream_open": sse_status == 200,
                "quarantine_updated": quarantine_updated,
                "read_quarantined": read_quarantined_ok,
                "reinstatement_updated": reinstated_updated,
                "read_reinstated": read_reinstated_ok,
                "follow_up_invoke_ok": follow_ok,
            }
            observed["checks"] = checks
            observed["sse_methods"] = [item.get("method") for item in events]
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
                process.wait(timeout=5)
            except Exception:
                process.kill()
                try:
                    process.wait(timeout=5)
                except Exception:
                    pass
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        scratch.cleanup()


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as exc:
        verdict = {
            "passed": False,
            "observed": {
                "error": type(exc).__name__,
                "detail": str(exc),
                "family": "mcp-resource-subscribe",
            },
        }
    print(json.dumps(verdict, sort_keys=True))
    raise SystemExit(0)
