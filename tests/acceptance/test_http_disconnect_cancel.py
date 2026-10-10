"""Acceptance probe: dropping an HTTP client kills the owned tool tree.

POST /invoke used to run the untrusted command tree until the wall-clock
timeout even after the caller hung up. This probe starts the invocation
plane as a separate OS process, drives a fixture tool that heartbeats a
workspace file while sleeping, aborts the HTTP client after the first
beat, and requires the heartbeat counter to freeze. A follow-up
POST /invoke of a fast text-reverser must still return the correct
declared output, proving the plane survived the abort.

On the pre-mission plane the heartbeat file keeps growing after the
client abort, so the probe reports passed=false. Both outcomes exit 0
with JSON ``passed`` and nonempty ``observed``.
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


def _abortable_invoke(host: str, port: int, payload: dict) -> socket.socket:
    body = json.dumps(payload).encode("utf-8")
    sock = socket.create_connection((host, port), timeout=10)
    request = (
        f"POST /invoke HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii") + body
    sock.sendall(request)
    return sock


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "http-disconnect-cancel"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="http-disconnect-probe-", ignore_cleanup_errors=True)
    try:
        base = Path(scratch.name)
        root = _build_fixture_root(base)
        heartbeat = root / "heartbeat.txt"
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
            payload = {
                "capability_id": "capability.absorbed-heartbeat-hold",
                "input": {"heartbeat_path": str(heartbeat)},
            }
            client = _abortable_invoke("127.0.0.1", port, payload)
            started = time.monotonic()
            first_beat = 0
            while time.monotonic() - started < 15:
                first_beat = _read_beats(heartbeat)
                if first_beat >= 1:
                    break
                time.sleep(0.05)
            observed["first_beat"] = first_beat
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
            if first_beat < 1:
                observed["detail"] = "heartbeat tool never started"
                return {"passed": False, "observed": observed}

            time.sleep(1.5)
            sample_a = _read_beats(heartbeat)
            time.sleep(0.8)
            sample_b = _read_beats(heartbeat)
            observed["sample_a"] = sample_a
            observed["sample_b"] = sample_b
            stopped = sample_b == sample_a

            follow_status, follow = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": "blackhole"},
                },
            )
            output = follow.get("output") if isinstance(follow, dict) else None
            observed["follow_status"] = follow_status
            observed["follow_output"] = output
            follow_ok = (
                follow_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == "elohkcalb"
            )
            observed["checks"] = {
                "tool_started": first_beat >= 1,
                "heartbeats_stopped_after_abort": stopped,
                "follow_up_invoke_ok": follow_ok,
            }
            return {
                "passed": bool(first_beat >= 1 and stopped and follow_ok),
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
            "observed": {"error": type(exc).__name__, "detail": str(exc), "family": "http-disconnect-cancel"},
        }
    print(json.dumps(verdict))
    sys.exit(0)
