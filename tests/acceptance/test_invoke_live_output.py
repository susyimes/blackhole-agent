"""Acceptance probe: POST /invoke streams tool output before the JSON result.

JSON POST /invoke currently withholds every stdout and stderr byte until the
owned tree exits, so a browser operator cannot watch a running tool. This
probe starts the invocation plane as a separate OS process, POSTs a fixture
tool that prints a progress line, sleeps, then returns the reversed input,
and reads the response incrementally.

On the candidate plane ``Accept: text/event-stream`` (without application/json)
yields SSE: an ``output`` event carrying the progress line arrives while the
tool is still sleeping, then a ``result`` event carries the reversed text.
The operator console document requests that Accept header. A follow-up JSON
invoke of the text-reverser still returns the declared reverse output.

On the previous-milestone plane the same Accept header is ignored, the body
is a single JSON object after the sleep, and the console still uses postJSON,
so the probe reports passed=false.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes.
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

PROBE_TEXT = "live-output-e15f8bec"
EXPECTED = PROBE_TEXT[::-1]
PROGRESS_MARK = "LIVE-PROGRESS-e15f8bec"
SLEEP_SECONDS = 1.5

_SLOW_TOOL = f"""
import json, sys, time
state = json.load(sys.stdin)
print({PROGRESS_MARK!r}, file=sys.stderr, flush=True)
time.sleep({SLEEP_SECONDS})
print(json.dumps({{"reversed_text": state["raw_text"][::-1]}}), flush=True)
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
                        "expect": {key: "x" for key in provides},
                    }
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "slow-reverser", _SLOW_TOOL, ["raw_text"], ["reversed_text"])
    _write_tool(
        root,
        "text-reverser",
        "import json, sys\nstate = json.load(sys.stdin)\nprint(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n",
        ["raw_text"],
        ["reversed_text"],
    )
    capabilities = {
        "capability.absorbed-slow-reverser": _ledger_entry(
            "capability.absorbed-slow-reverser", "probe slow reverser"
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


def _parse_sse_block(raw: str) -> tuple[str, object]:
    event_name = "message"
    payload: object = None
    for line in raw.split("\n"):
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            text = line[5:].strip()
            try:
                payload = json.loads(text)
            except Exception:
                payload = text
    return event_name, payload


def _read_http_headers(
    sock: socket.socket, deadline: float
) -> tuple[int, dict[str, str], bytes]:
    buf = b""
    while b"\r\n\r\n" not in buf:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock.settimeout(min(0.4, remaining))
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            continue
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if len(buf) > 65536:
            break
    header_blob, _, rest = buf.partition(b"\r\n\r\n")
    lines = header_blob.decode("iso-8859-1", errors="replace").split("\r\n")
    status = 0
    if lines:
        parts = lines[0].split(" ", 2)
        if len(parts) >= 2 and parts[1].isdigit():
            status = int(parts[1])
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return status, headers, rest


def _stream_invoke(host: str, port: int, payload: dict, timeout: float = 20.0) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    started = time.monotonic()
    events: list[dict[str, object]] = []
    progress_at: float | None = None
    result_at: float | None = None
    status = 0
    content_type = ""
    buf = b""
    sock = socket.create_connection((host, port), timeout=10)
    try:
        sock.sendall(
            (
                f"POST /invoke HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Content-Type: application/json\r\n"
                f"Accept: text/event-stream\r\n"
                f"Content-Length: {len(data)}\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode("ascii")
            + data
        )
        deadline = started + timeout
        status, headers, buf = _read_http_headers(sock, deadline)
        content_type = headers.get("content-type", "")
        # Pre-mission JSON invoke sends headers only after the tool exits.
        # Do not wait for SSE delimiters on that body.
        if "text/event-stream" not in content_type.lower():
            return {
                "status": status,
                "content_type": content_type,
                "events": events,
                "progress_at": None,
                "result_at": None,
                "elapsed": time.monotonic() - started,
                "body_preview": buf.decode("utf-8", errors="replace")[:400],
            }
        while time.monotonic() < deadline:
            while b"\n\n" in buf:
                raw, buf = buf.split(b"\n\n", 1)
                event_name, event_payload = _parse_sse_block(
                    raw.decode("utf-8", errors="replace")
                )
                events.append({"event": event_name, "data": event_payload})
                now = time.monotonic() - started
                if (
                    event_name == "output"
                    and isinstance(event_payload, dict)
                    and PROGRESS_MARK in str(event_payload.get("text") or "")
                ):
                    if progress_at is None:
                        progress_at = now
                if event_name in {"result", "error"} and result_at is None:
                    result_at = now
            if result_at is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(min(0.4, remaining))
            try:
                chunk = sock.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return {
        "status": status,
        "content_type": content_type,
        "events": events,
        "progress_at": progress_at,
        "result_at": result_at,
        "elapsed": time.monotonic() - started,
        "body_preview": buf.decode("utf-8", errors="replace")[:400],
    }


def _json_invoke(url: str, payload: dict, timeout: int = 30) -> tuple[int, object]:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _get(url: str) -> tuple[int, str, str]:
    req = urlrequest.Request(url, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=15) as response:
            return (
                response.status,
                response.headers.get("Content-Type") or "",
                response.read().decode("utf-8"),
            )
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type") or "", exc.read().decode("utf-8", errors="replace")


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "invoke-live-output"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="invoke-live-output-probe-", ignore_cleanup_errors=True)
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

            port = int(ready["listening"])
            base_url = f"http://127.0.0.1:{port}"

            health_status, health_ctype, health_body = _get(f"{base_url}/health")
            try:
                health = json.loads(health_body)
            except Exception:
                health = None
            observed["health_status"] = health_status
            observed["health"] = health
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("ok") is True
                and health.get("live_invoke_stream") is True
            )

            streamed = _stream_invoke(
                "127.0.0.1",
                port,
                {
                    "capability_id": "capability.absorbed-slow-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            observed["stream_status"] = streamed["status"]
            observed["stream_content_type"] = streamed["content_type"]
            observed["stream_event_names"] = [
                item.get("event") for item in streamed["events"] if isinstance(item, dict)
            ]
            observed["progress_at"] = streamed["progress_at"]
            observed["result_at"] = streamed["result_at"]
            observed["stream_elapsed"] = streamed["elapsed"]
            result_payload = None
            for item in streamed["events"]:
                if isinstance(item, dict) and item.get("event") == "result":
                    result_payload = item.get("data")
            observed["stream_result"] = result_payload
            reversed_ok = (
                isinstance(result_payload, dict)
                and (result_payload.get("output") or {}).get("reversed_text") == EXPECTED
            )
            ctype = str(streamed["content_type"] or "").lower()
            progress_at = streamed["progress_at"]
            result_at = streamed["result_at"]
            live_ok = (
                streamed["status"] == 200
                and "text/event-stream" in ctype
                and isinstance(progress_at, float)
                and isinstance(result_at, float)
                and progress_at < result_at
                and (result_at - progress_at) >= 1.0
                and reversed_ok
            )

            console_status, console_ctype, console_html = _get(f"{base_url}/console")
            observed["console_status"] = console_status
            observed["console_ctype"] = console_ctype
            console_ok = (
                console_status == 200
                and "text/html" in (console_ctype or "").lower()
                and 'Accept": "text/event-stream"' in console_html
                and "text/event-stream" in console_html
            )

            json_status, json_body = _json_invoke(
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            observed["json_status"] = json_status
            observed["json_body"] = json_body
            json_ok = (
                json_status == 200
                and isinstance(json_body, dict)
                and (json_body.get("output") or {}).get("reversed_text") == EXPECTED
            )

            observed["checks"] = {
                "health_ok": health_ok,
                "live_ok": live_ok,
                "console_ok": console_ok,
                "json_ok": json_ok,
            }
            passed = bool(health_ok and live_ok and console_ok and json_ok)
            return {"passed": passed, "observed": observed}
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
                "family": "invoke-live-output",
            },
        }
    print(json.dumps(verdict, sort_keys=True))
    sys.exit(0)
