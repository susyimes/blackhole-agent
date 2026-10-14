"""Outcome probe: interval schedules fire a governed tool after hang-up and restart.

POST /invoke currently occupies the HTTP client for the whole tool runtime,
so an operator cannot arm a capability to run on a cadence. This probe starts
the invocation plane as a separate OS process and requires:

1. serve --schedule listens and GET /health reports schedules true.
2. POST /schedules of the fixture text-reverser returns HTTP 201 with a schedule id.
3. GET /schedules/{id} eventually reports a completed last run whose output is
   the declared reverse, after the creating request has already returned.
4. After the server is killed and restarted on the same root, the schedule is
   still listed and a later run still reverses.
5. DELETE /schedules/{id} removes it; a later GET stays 404.
6. A plane started without --schedule reports schedules false and POST
   /schedules is HTTP 400 schedules_disabled.
7. POST /invoke of the same fixture still returns the declared reverse.

On the pre-mission plane the schedules module is absent, so the probe reports
passed=false. Both outcomes exit 0 with JSON passed and nonempty observed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

PROBE_TEXT = "schedule-cadence-af3a83c6"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
REVERSE_ID = "capability.absorbed-text-reverser"
_REVERSE_TOOL = (
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


def _write_tool(root: Path) -> None:
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(_REVERSE_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "text-reverser",
                "name": "probe text reverser",
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
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {REVERSE_ID: _ledger_entry(REVERSE_ID, "probe text reverser")},
            }
        ),
        encoding="utf-8",
    )


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    timeout: int = 20,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
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


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    try:
        line = process.stdout.readline() if process.stdout is not None else ""
        sink["ready"] = json.loads(line)
    except Exception as exc:
        sink["ready"] = None
        sink["ready_error"] = f"{type(exc).__name__}: {exc}"


def _start_plane(src_root: Path, root: Path, extra_args: list[str] | None = None) -> tuple[subprocess.Popen, dict]:
    env = dict(os.environ)
    env.pop("BLACKHOLE_SCHEDULE", None)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    command = [
        sys.executable,
        "-m",
        "blackhole_agent.capability_service",
        "serve",
        "--port",
        "0",
        "--root",
        str(root),
    ]
    if extra_args:
        command.extend(extra_args)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    sink: dict[str, object] = {}
    reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
    reader.start()
    reader.join(timeout=30)
    return process, sink


def _stop_plane(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.kill()
    try:
        _out, err = process.communicate(timeout=10)
    except Exception:
        err = ""
    return err if isinstance(err, str) else ""


def _wait_completed(url: str, schedule_id: str, *, minimum_runs: int) -> tuple[int, object]:
    deadline = time.time() + 15
    status = 0
    body: object = None
    while time.time() < deadline:
        status, body = _request("GET", f"{url}/schedules/{schedule_id}")
        if (
            status == 200
            and isinstance(body, dict)
            and body.get("last_status") == "completed"
            and int(body.get("run_count") or 0) >= minimum_runs
        ):
            return status, body
        time.sleep(0.15)
    return status, body


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "invocation-schedules"}
    try:
        import blackhole_agent.capability_service as service
        import blackhole_agent.invocation_schedules as schedules
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "accept_schedule_post") or not hasattr(schedules, "SchedulePlane"):
        observed["detail"] = "baseline plane has no interval schedule HTTP surface"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    health_ok = post_ok = complete_ok = restart_ok = cancel_ok = closed_ok = reverse_ok = False
    scratch = tempfile.TemporaryDirectory(prefix="invocation-schedules-probe-", ignore_cleanup_errors=True)
    try:
        root = Path(scratch.name) / "repo"
        _write_tool(root)
        process, sink = _start_plane(src_root, root, ["--schedule"])
        try:
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = _stop_plane(process)[-2000:]
                return {"passed": False, "observed": observed}
            url = f"http://127.0.0.1:{ready['listening']}"
            health_status, health = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health_schedules"] = health.get("schedules") if isinstance(health, dict) else None
            health_ok = health_status == 200 and isinstance(health, dict) and health.get("schedules") is True

            post_status, created = _request(
                "POST",
                f"{url}/schedules",
                {
                    "capability_id": REVERSE_ID,
                    "input": {"raw_text": PROBE_TEXT},
                    "every_seconds": 1,
                },
            )
            observed["post_status"] = post_status
            observed["created"] = created if isinstance(created, dict) else None
            schedule_id = created.get("schedule_id") if isinstance(created, dict) else None
            post_ok = (
                post_status == 201
                and isinstance(created, dict)
                and created.get("ok") is True
                and isinstance(schedule_id, str)
                and bool(schedule_id)
            )
            if not post_ok or not isinstance(schedule_id, str):
                observed["detail"] = "schedule was not accepted"
                return {"passed": False, "observed": observed}

            get_status, completed = _wait_completed(url, schedule_id, minimum_runs=1)
            observed["get_status"] = get_status
            observed["completed"] = completed if isinstance(completed, dict) else None
            first_runs = int(completed.get("run_count") or 0) if isinstance(completed, dict) else 0
            complete_ok = (
                get_status == 200
                and isinstance(completed, dict)
                and completed.get("last_status") == "completed"
                and completed.get("last_output", {}).get("reversed_text") == EXPECTED_REVERSE
                and first_runs >= 1
            )

            reverse_status, reversed_body = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
            )
            observed["reverse_status"] = reverse_status
            reverse_ok = (
                reverse_status == 200
                and isinstance(reversed_body, dict)
                and reversed_body.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-2000:]

        if not (health_ok and post_ok and complete_ok):
            observed["detail"] = "first cadence did not complete"
            return {"passed": False, "observed": observed}

        restarted, restart_sink = _start_plane(src_root, root, ["--schedule"])
        try:
            restart_ready = restart_sink.get("ready")
            observed["restart_ready"] = restart_ready
            if not isinstance(restart_ready, dict) or not restart_ready.get("listening"):
                observed["detail"] = "restarted server never reported a listening port"
                observed["restart_stderr"] = _stop_plane(restarted)[-2000:]
                return {"passed": False, "observed": observed}
            restart_url = f"http://127.0.0.1:{restart_ready['listening']}"
            listed_status, listed = _request("GET", f"{restart_url}/schedules/{schedule_id}")
            observed["restart_get_status"] = listed_status
            still_there = (
                listed_status == 200
                and isinstance(listed, dict)
                and listed.get("schedule_id") == schedule_id
                and listed.get("last_output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
            later_status, later = _wait_completed(
                restart_url, schedule_id, minimum_runs=first_runs + 1
            )
            observed["later"] = later if isinstance(later, dict) else None
            restart_ok = (
                still_there
                and later_status == 200
                and isinstance(later, dict)
                and later.get("last_output", {}).get("reversed_text") == EXPECTED_REVERSE
                and int(later.get("run_count") or 0) >= first_runs + 1
            )
            delete_status, deleted = _request("DELETE", f"{restart_url}/schedules/{schedule_id}")
            observed["delete_status"] = delete_status
            observed["deleted"] = deleted if isinstance(deleted, dict) else None
            time.sleep(1.4)
            gone_status, gone = _request("GET", f"{restart_url}/schedules/{schedule_id}")
            observed["gone_status"] = gone_status
            observed["gone"] = gone if isinstance(gone, dict) else None
            cancel_ok = (
                delete_status == 200
                and isinstance(deleted, dict)
                and deleted.get("cancelled") is True
                and gone_status == 404
                and isinstance(gone, dict)
                and gone.get("error") == "schedule_unknown"
            )
        finally:
            observed["restart_stderr"] = (_stop_plane(restarted) or "")[-2000:]

        closed_root = Path(scratch.name) / "closed"
        _write_tool(closed_root)
        closed, closed_sink = _start_plane(src_root, closed_root)
        try:
            closed_ready = closed_sink.get("ready")
            if not isinstance(closed_ready, dict) or not closed_ready.get("listening"):
                observed["detail"] = "closed plane never reported a listening port"
                observed["closed_stderr"] = _stop_plane(closed)[-2000:]
                return {"passed": False, "observed": observed}
            closed_url = f"http://127.0.0.1:{closed_ready['listening']}"
            closed_health_status, closed_health = _request("GET", f"{closed_url}/health")
            closed_post_status, closed_post = _request(
                "POST",
                f"{closed_url}/schedules",
                {
                    "capability_id": REVERSE_ID,
                    "input": {"raw_text": PROBE_TEXT},
                    "every_seconds": 1,
                },
            )
            observed["closed_health_schedules"] = (
                closed_health.get("schedules") if isinstance(closed_health, dict) else None
            )
            observed["closed_post_status"] = closed_post_status
            observed["closed_post"] = closed_post if isinstance(closed_post, dict) else None
            closed_ok = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("schedules") is False
                and closed_post_status == 400
                and isinstance(closed_post, dict)
                and closed_post.get("error") == "schedules_disabled"
            )
        finally:
            observed["closed_stderr"] = (_stop_plane(closed) or "")[-1500:]
    finally:
        scratch.cleanup()

    passed = bool(health_ok and post_ok and complete_ok and restart_ok and cancel_ok and closed_ok and reverse_ok)
    observed["checks"] = {
        "health": health_ok,
        "post": post_ok,
        "completed": complete_ok,
        "restart": restart_ok,
        "cancel": cancel_ok,
        "closed": closed_ok,
        "invoke": reverse_ok,
    }
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main()))
