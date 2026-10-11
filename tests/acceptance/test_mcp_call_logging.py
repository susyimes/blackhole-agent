"""Acceptance probe: MCP tools/call streams notifications/message live.

Initialize currently omits logging, logging/setLevel is method-not-found,
and a host that opened GET /mcp never receives notifications/message while
an untrusted tool is running. This probe starts the invocation plane as a
separate OS process and requires:

1. GET /health reports mcp_logging.
2. POST /mcp initialize advertises logging and returns Mcp-Session-Id.
3. POST /mcp logging/setLevel to debug succeeds.
4. GET /mcp with that session and Accept text/event-stream stays open.
5. tools/call of a fixture that prints a stderr progress line while sleeping
   delivers notifications/message on the GET stream containing that line
   while the call is still in flight.
6. The tools/call JSON-RPC result still contains the declared reverse output.
7. An unknown log level is JSON-RPC -32602.
8. A follow-up REST POST /invoke of the text-reverser still returns the
   declared reverse output.

On the pre-mission plane initialize omits logging, setLevel is
method-not-found, and the GET stream receives no notifications/message
during the call, so the probe reports passed=false. Both outcomes exit 0
with JSON passed and nonempty observed.

The controller copies this file to a scratch path and injects implementation
src via ``python -I`` + sys.path. Serve children must load that injected
tree: import capability_service from sys.path, then replace PYTHONPATH with
that src root only.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

_LOG_TOOL = r"""
import json, sys, time
state = json.load(sys.stdin)
sys.stderr.write("BH-LOG-PROGRESS-9f686c4b\n")
sys.stderr.flush()
time.sleep(1.6)
print(json.dumps({"reversed_text": state["raw_text"][::-1]}))
"""

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

PROBE_TEXT = "mcp-logging-9f686c4b"
EXPECTED = PROBE_TEXT[::-1]
LOG_MARK = "BH-LOG-PROGRESS-9f686c4b"
CALL_ID = 77


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


def _write_tool(root: Path, slug: str, source: str) -> None:
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
                "requires": ["raw_text"],
                "provides": ["reversed_text"],
                "cases": [
                    {"input": {"raw_text": value}, "expect": {"reversed_text": value[::-1]}}
                    for value in ("ab", "cd")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "log-hold", _LOG_TOOL)
    _write_tool(root, "text-reverser", _FAST_TOOL)
    capabilities = {
        "capability.absorbed-log-hold": _ledger_entry(
            "capability.absorbed-log-hold", "probe log hold"
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


def _is_progress_log(item: dict) -> bool:
    if item.get("method") != "notifications/message":
        return False
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    data = params.get("data") if isinstance(params.get("data"), dict) else {}
    return LOG_MARK in str(data.get("text") or "") or LOG_MARK in str(params)


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-call-logging"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    observed["implementation_src"] = str(src_root)
    tmp = tempfile.mkdtemp(prefix="bh-mcp-logging-")
    process: subprocess.Popen[str] | None = None
    sse_sock: socket.socket | None = None
    collector: threading.Thread | None = None
    stop_sse = threading.Event()
    try:
        root = _build_root(Path(tmp))
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
        sink: dict[str, object] = {}

        def _read_ready() -> None:
            if process is None or process.stdout is None:
                sink["ready"] = None
                return
            line = process.stdout.readline()
            try:
                sink["ready"] = json.loads(line) if line.strip().startswith("{") else line
            except json.JSONDecodeError:
                sink["ready"] = line

        reader = threading.Thread(target=_read_ready, daemon=True)
        reader.start()
        reader.join(timeout=60)
        ready = sink.get("ready")
        observed["ready"] = ready
        if not isinstance(ready, dict) or not ready.get("listening"):
            err = ""
            if process.stderr is not None:
                try:
                    err = process.stderr.read()
                except Exception:
                    err = ""
            observed["detail"] = "server never reported a listening port"
            observed["stderr"] = err[-2000:] if isinstance(err, str) else ""
            return {"passed": False, "observed": observed}

        host = "127.0.0.1"
        port = int(ready["listening"])
        base = f"http://{host}:{port}"
        health_status, health, _ = _request("GET", f"{base}/health")
        mcp = f"{base}/mcp"
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
                    "clientInfo": {"name": "mcp-logging-probe", "version": "1"},
                },
            },
        )
        session = str(headers.get("mcp-session-id") or "")
        result = handshake.get("result") if isinstance(handshake, dict) else None
        advertised = result.get("capabilities") if isinstance(result, dict) else None
        if not isinstance(advertised, dict):
            advertised = {}
        mcp_hdr = {"Mcp-Session-Id": session} if session else None
        set_status, set_body, _ = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "logging/setLevel",
                "params": {"level": "debug"},
            },
            headers=mcp_hdr,
        )
        bad_status, bad_body, _ = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "logging/setLevel",
                "params": {"level": "not-a-level"},
            },
            headers=mcp_hdr,
        )

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
                        "name": "log-hold",
                        "arguments": {"raw_text": PROBE_TEXT},
                    },
                },
                headers=mcp_hdr,
                timeout=40,
            )

        caller = threading.Thread(target=_call, daemon=True)
        caller.start()
        log_while_running = False
        started = time.monotonic()
        while time.monotonic() - started < 12:
            if any(_is_progress_log(item) for item in events):
                log_while_running = caller.is_alive()
                break
            time.sleep(0.05)
        caller.join(timeout=20)
        call_status = call_box.get("status")
        call_body = call_box.get("body")
        call_result = call_body.get("result") if isinstance(call_body, dict) else None
        structured = (
            call_result.get("structuredContent") if isinstance(call_result, dict) else None
        )
        follow_status, follow, _ = _request(
            "POST",
            f"{base}/invoke",
            {
                "capability_id": "capability.absorbed-text-reverser",
                "input": {"raw_text": PROBE_TEXT},
            },
        )
        follow_output = follow.get("output") if isinstance(follow, dict) else None
        observed["health_status"] = health_status
        observed["health"] = health
        observed["initialize_status"] = init_status
        observed["mcp_session"] = session
        observed["logging_advertised"] = advertised.get("logging")
        observed["set_level_status"] = set_status
        observed["set_level_body"] = set_body
        observed["bad_level_status"] = bad_status
        observed["bad_level_code"] = _error_code(bad_body)
        observed["sse_status"] = sse_status
        observed["log_events"] = [item for item in events if item.get("method") == "notifications/message"][:6]
        observed["log_while_running"] = log_while_running
        observed["call_status"] = call_status
        observed["call_structured"] = structured
        observed["follow_status"] = follow_status
        observed["follow_output"] = follow_output
        checks = {
            "health_ok": health_status == 200
            and isinstance(health, dict)
            and health.get("mcp_logging") is True,
            "initialize_ok": init_status == 200 and bool(session),
            "logging_advertised": advertised.get("logging") == {},
            "set_level_ok": set_status == 200
            and isinstance(set_body, dict)
            and set_body.get("result") == {},
            "unknown_level_invalid": _error_code(bad_body) == -32602,
            "sse_open": sse_status == 200,
            "live_log_message": log_while_running,
            "call_result_ok": call_status == 200
            and isinstance(structured, dict)
            and structured.get("reversed_text") == EXPECTED,
            "follow_ok": follow_status == 200
            and isinstance(follow_output, dict)
            and follow_output.get("reversed_text") == EXPECTED,
        }
        observed["checks"] = checks
        return {"passed": all(checks.values()), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        stop_sse.set()
        if sse_sock is not None:
            try:
                sse_sock.close()
            except OSError:
                pass
        if collector is not None:
            collector.join(timeout=2)
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except Exception:
                process.kill()
                try:
                    process.wait(timeout=5)
                except Exception:
                    pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as exc:
        verdict = {
            "passed": False,
            "observed": {
                "error": type(exc).__name__,
                "detail": str(exc),
                "family": "mcp-call-logging",
            },
        }
    print(json.dumps(verdict, sort_keys=True))
    raise SystemExit(0)
