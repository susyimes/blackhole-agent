"""Acceptance probe: the live plane caps HTTP occupancy and drops slowloris.

Untrusted-tool admission already caps in-flight process trees, but the
listen socket still accepted connections with no request timeout and no
HTTP connection cap. A client that opens sockets and never finishes
headers occupies worker threads and RAM without starting a tool.

This probe starts the invocation plane as a separate OS process with
BLACKHOLE_HTTP_REQUEST_TIMEOUT=2 and BLACKHOLE_MAX_HTTP_CONNECTIONS=2
and requires:

1. GET /health reports http_connection_limits true,
   http_request_timeout_seconds 2, and max_http_connections 2.
2. A TCP client that sends an incomplete POST /invoke is closed after
   the timeout without returning reversed output.
3. With two incomplete connections occupying the cap, a third connection
   is refused HTTP 503 with violation connection_limited and never starts
   a tool.
4. After those sockets close, POST /invoke of the text-reverser still
   returns the declared reverse output.

On the pre-mission plane health omits the occupancy fields, the incomplete
POST stays open past the timeout, and a third connection is accepted, so
the probe reports passed=false. Both outcomes exit 0 with JSON ``passed``
and nonempty ``observed``.
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
from urllib.error import HTTPError

PROBE_TEXT = "http-occupancy-9ce592dc"
EXPECTED = PROBE_TEXT[::-1]
TIMEOUT_SECONDS = 2
MAX_CONNECTIONS = 2

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


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
                        "expect": {provides[0]: "x"},
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
    capabilities = {
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
    try:
        line = process.stdout.readline()
        sink["ready_line"] = line[:500] if isinstance(line, str) else ""
        sink["ready"] = json.loads(line)
    except Exception as exc:
        sink["ready"] = None
        sink["ready_error"] = f"{type(exc).__name__}: {exc}"


def _request(
    method: str, url: str, payload: dict | None = None, *, timeout: int = 30
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _recv_http(sock: socket.socket, *, timeout: float) -> bytes:
    sock.settimeout(timeout)
    data = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\r\n\r\n" in data:
                header, rest = data.split(b"\r\n\r\n", 1)
                length = 0
                for line in header.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        try:
                            length = int(line.split(b":", 1)[1].strip())
                        except ValueError:
                            length = 0
                if len(rest) >= length:
                    break
    except (TimeoutError, socket.timeout, ConnectionResetError, ConnectionAbortedError, OSError):
        return data
    return data


def _open_incomplete(host: str, port: int) -> socket.socket:
    sock = socket.create_connection((host, port), timeout=2)
    sock.sendall(
        (
            f"POST /invoke HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            "Content-Type: application/json\r\nContent-Length: 200\r\n\r\n{"
        ).encode("ascii")
    )
    return sock


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "http-connection-limits"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="http-occupancy-probe-", ignore_cleanup_errors=True)
    try:
        root = _build_fixture_root(Path(scratch.name))
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["BLACKHOLE_HTTP_REQUEST_TIMEOUT"] = str(TIMEOUT_SECONDS)
        env["BLACKHOLE_MAX_HTTP_CONNECTIONS"] = str(MAX_CONNECTIONS)
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
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        try:
            sink: dict[str, object] = {}
            reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
            reader.start()
            reader.join(timeout=60)
            ready = sink.get("ready")
            observed["ready"] = ready
            if sink.get("ready_error"):
                observed["ready_error"] = sink.get("ready_error")
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = process.stderr.read() if process.stderr else ""
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:] if isinstance(err, str) else ""
                observed["ready_line"] = sink.get("ready_line")
                return {"passed": False, "observed": observed}

            port = int(ready["listening"])
            host = "127.0.0.1"
            base_url = f"http://{host}:{port}"

            health_status, health = _request("GET", f"{base_url}/health")
            observed["health_status"] = health_status
            observed["health"] = health
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("ok") is True
                and health.get("http_connection_limits") is True
                and int(health.get("http_request_timeout_seconds") or 0) == TIMEOUT_SECONDS
                and int(health.get("max_http_connections") or 0) == MAX_CONNECTIONS
            )

            sock_a = _open_incomplete(host, port)
            sock_b = _open_incomplete(host, port)
            time.sleep(0.3)
            overflow = socket.create_connection((host, port), timeout=2)
            overflow_raw = _recv_http(overflow, timeout=2)
            overflow.close()
            overflow_text = overflow_raw.decode("utf-8", "replace")
            overflow_payload = None
            if "\r\n\r\n" in overflow_text:
                try:
                    overflow_payload = json.loads(overflow_text.split("\r\n\r\n", 1)[1])
                except json.JSONDecodeError:
                    overflow_payload = None
            observed["overflow_raw_prefix"] = overflow_text[:240]
            observed["overflow_payload"] = overflow_payload
            overflow_ok = (
                overflow_raw.startswith(b"HTTP/1.1 503 ")
                and isinstance(overflow_payload, dict)
                and overflow_payload.get("ok") is False
                and overflow_payload.get("violation") == "connection_limited"
                and EXPECTED not in overflow_text
            )

            sock_a.settimeout(TIMEOUT_SECONDS + 2)
            slow_started = time.monotonic()
            try:
                slow_data = sock_a.recv(4096)
                slow_error = None
            except Exception as exc:
                slow_data = b""
                slow_error = type(exc).__name__
            slow_waited = time.monotonic() - slow_started
            slow_text = slow_data.decode("utf-8", "replace")
            observed["slowloris_bytes"] = len(slow_data)
            observed["slowloris_prefix"] = slow_text[:160]
            observed["slowloris_error"] = slow_error
            observed["slowloris_waited"] = round(slow_waited, 3)
            # TimeoutError means the server never closed; that is the old plane.
            slowloris_ok = (
                EXPECTED not in slow_text
                and slow_error != "TimeoutError"
                and (
                    (slow_data == b"" and slow_error is None)
                    or slow_error in {"ConnectionResetError", "ConnectionAbortedError"}
                )
                and slow_waited >= 1.0
            )
            try:
                sock_a.close()
            except OSError:
                pass
            try:
                sock_b.close()
            except OSError:
                pass
            time.sleep(0.2)

            follow_status, follow = _request(
                "POST",
                f"{base_url}/invoke",
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
            observed["checks"] = {
                "health_reports_limits": health_ok,
                "overflow_refused": overflow_ok,
                "slowloris_closed": slowloris_ok,
                "follow_up_invoke_ok": follow_ok,
            }
            return {
                "passed": bool(health_ok and overflow_ok and slowloris_ok and follow_ok),
                "observed": observed,
            }
        finally:
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
                "family": "http-connection-limits",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
