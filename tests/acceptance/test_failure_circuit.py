"""Outcome probe: three consecutive nonzero exits open a persisted failure circuit.

A live capability_service process must:

1. Report failure_circuit true and threshold 3 on GET /health.
2. Let two nonzero exits followed by a success reset the streak.
3. Open the circuit on the third consecutive nonzero exit.
4. Answer the next POST /invoke of that id with HTTP 409 capability_circuit_open
   and leave the invocation journal unchanged.
5. Still run a different capability while the circuit is open.
6. Keep the circuit open after a process restart on the same root.
7. Accept POST /circuits/{id} {"action": "close"} and then return the declared
   output from the next invoke.

On the previous milestone the fourth consecutive failure still runs the tool,
GET /health has no failure_circuit flag, and POST /circuits is unknown, so
this probe reports passed=false. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

FLAKY_ID = "capability.absorbed-circuit-flaky"
SIBLING_ID = "capability.absorbed-circuit-sibling"

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "if state.get('text') == 'fail':\n"
    "    sys.stderr.write('deliberate failure\\n')\n"
    "    raise SystemExit(1)\n"
    "print(json.dumps({'echo_output': state['text']}))\n"
)


def _ledger_entry(capability_id: str, name: str) -> dict:
    return {
        "id": capability_id,
        "name": name,
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }


def _write_tool(root: Path, slug: str, capability_id: str, name: str) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": name,
                "command": ["python", "tool.py"],
                "requires": ["text"],
                "provides": ["echo_output"],
                "cases": [
                    {"input": {"text": "ok"}, "expect": {"echo_output": "ok"}},
                    {"input": {"text": "recovered"}, "expect": {"echo_output": "recovered"}},
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_repo(root: Path) -> None:
    _write_tool(root, "circuit-flaky", FLAKY_ID, "probe circuit flaky")
    _write_tool(root, "circuit-sibling", SIBLING_ID, "probe circuit sibling")
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    FLAKY_ID: _ledger_entry(FLAKY_ID, "probe circuit flaky"),
                    SIBLING_ID: _ledger_entry(SIBLING_ID, "probe circuit sibling"),
                },
            }
        ),
        encoding="utf-8",
    )


def _request(
    method: str,
    url: str,
    data: bytes | None = None,
    *,
    timeout: int = 30,
) -> tuple[int, object]:
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            try:
                return response.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return response.status, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return exc.code, raw
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def _invoke(url: str, capability_id: str, text: str) -> tuple[int, object]:
    body = json.dumps(
        {"capability_id": capability_id, "input": {"text": text}},
        separators=(",", ":"),
    ).encode("utf-8")
    return _request("POST", f"{url}/invoke", body)


def _journal_count(root: Path, capability_id: str) -> int:
    path = root / ".blackhole-agent" / "invocation-history.jsonl"
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("capability_id") == capability_id:
            count += 1
    return count


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    try:
        line = process.stdout.readline() if process.stdout is not None else ""
        sink["ready_line"] = line[:500] if isinstance(line, str) else ""
        sink["ready"] = json.loads(line)
    except Exception as exc:
        sink["ready"] = None
        sink["ready_error"] = f"{type(exc).__name__}: {exc}"


def _start_plane(src_root: Path, root: Path) -> tuple[subprocess.Popen, dict]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
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
    reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
    reader.start()
    reader.join(timeout=60)
    return process, sink


def _stop_plane(process: subprocess.Popen) -> str:
    process.kill()
    try:
        _out, err = process.communicate(timeout=10)
    except Exception:
        err = ""
    return err if isinstance(err, str) else ""


def _listening_url(sink: dict) -> str:
    ready = sink.get("ready")
    if not isinstance(ready, dict) or not ready.get("listening"):
        return ""
    return f"http://127.0.0.1:{ready['listening']}"


def _error_of(body: object) -> object:
    if isinstance(body, dict):
        return body.get("error")
    return None


def _output_of(body: object) -> object:
    if isinstance(body, dict):
        return body.get("output")
    return None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "failure-circuit"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="failure-circuit-", ignore_cleanup_errors=True)
    try:
        root = Path(scratch.name) / "repo"
        root.mkdir()
        _write_repo(root)
        process, sink = _start_plane(src_root, root)
        try:
            url = _listening_url(sink)
            observed["ready"] = sink.get("ready")
            if not url:
                observed["detail"] = "server never reported a listening port"
                return {"passed": False, "observed": observed}
            health_status, health = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["failure_circuit"] = health.get("failure_circuit") if isinstance(health, dict) else None
            observed["failure_circuit_threshold"] = (
                health.get("failure_circuit_threshold") if isinstance(health, dict) else None
            )
            reset_statuses = []
            for text in ("fail", "fail", "ok"):
                status, body = _invoke(url, FLAKY_ID, text)
                reset_statuses.append(status)
                if text == "ok":
                    observed["reset_output"] = _output_of(body)
            observed["reset_statuses"] = reset_statuses
            streak_statuses = []
            for _ in range(3):
                status, _body = _invoke(url, FLAKY_ID, "fail")
                streak_statuses.append(status)
            observed["streak_statuses"] = streak_statuses
            blocked_status, blocked = _invoke(url, FLAKY_ID, "fail")
            observed["blocked_status"] = blocked_status
            observed["blocked_error"] = _error_of(blocked)
            observed["journal_after_block"] = _journal_count(root, FLAKY_ID)
            sibling_status, sibling = _invoke(url, SIBLING_ID, "sibling")
            observed["sibling_status"] = sibling_status
            observed["sibling_output"] = _output_of(sibling)
            circuit_status, circuit = _request("GET", f"{url}/circuits/{FLAKY_ID}")
            observed["circuit_status"] = circuit_status
            observed["circuit_open"] = circuit.get("open") if isinstance(circuit, dict) else None
            observed["circuit_consecutive"] = (
                circuit.get("consecutive_failures") if isinstance(circuit, dict) else None
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-1500:]

        restarted, restart_sink = _start_plane(src_root, root)
        try:
            restart_url = _listening_url(restart_sink)
            observed["restart_ready"] = restart_sink.get("ready")
            if not restart_url:
                observed["detail"] = "restarted server never reported a listening port"
                return {"passed": False, "observed": observed}
            persisted_status, persisted = _invoke(restart_url, FLAKY_ID, "fail")
            observed["persisted_status"] = persisted_status
            observed["persisted_error"] = _error_of(persisted)
            observed["journal_after_restart"] = _journal_count(root, FLAKY_ID)
            close_body = json.dumps({"action": "close"}).encode("utf-8")
            close_status, closed = _request(
                "POST", f"{restart_url}/circuits/{FLAKY_ID}", close_body
            )
            observed["close_status"] = close_status
            observed["close_open"] = closed.get("open") if isinstance(closed, dict) else None
            recovered_status, recovered = _invoke(restart_url, FLAKY_ID, "recovered")
            observed["recovered_status"] = recovered_status
            observed["recovered_output"] = _output_of(recovered)
            observed["journal_after_recover"] = _journal_count(root, FLAKY_ID)
        finally:
            observed["restart_stderr"] = (_stop_plane(restarted) or "")[-1500:]

        reset_output = observed.get("reset_output")
        sibling_output = observed.get("sibling_output")
        recovered_output = observed.get("recovered_output")
        passed = bool(
            observed.get("failure_circuit") is True
            and observed.get("failure_circuit_threshold") == 3
            and observed.get("reset_statuses") == [502, 502, 200]
            and isinstance(reset_output, dict)
            and reset_output.get("echo_output") == "ok"
            and observed.get("streak_statuses") == [502, 502, 502]
            and observed.get("blocked_status") == 409
            and observed.get("blocked_error") == "capability_circuit_open"
            and observed.get("journal_after_block") == 6
            and observed.get("sibling_status") == 200
            and isinstance(sibling_output, dict)
            and sibling_output.get("echo_output") == "sibling"
            and observed.get("circuit_status") == 200
            and observed.get("circuit_open") is True
            and observed.get("circuit_consecutive") == 3
            and observed.get("persisted_status") == 409
            and observed.get("persisted_error") == "capability_circuit_open"
            and observed.get("journal_after_restart") == 6
            and observed.get("close_status") == 200
            and observed.get("close_open") is False
            and observed.get("recovered_status") == 200
            and isinstance(recovered_output, dict)
            and recovered_output.get("echo_output") == "recovered"
            and observed.get("journal_after_recover") == 7
        )
        observed["checks_passed"] = passed
        return {"passed": passed, "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        scratch.cleanup()


if __name__ == "__main__":
    try:
        report = main()
    except Exception as exc:
        report = {
            "passed": False,
            "observed": {"family": "failure-circuit", "error": f"{type(exc).__name__}: {exc}"},
        }
    print(json.dumps(report, sort_keys=True))
