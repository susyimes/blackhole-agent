"""Real HTTP peers must not overlap scheduled tools sharing a service root.

The tool emits timestamped reports through the ordinary artifact surface.
The same script runs unchanged against baseline and candidate source. An
unmet outcome returns JSON passed=false and exits zero, without assertions
on source, ledger flags, or a builtin proof.
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
from urllib import request
from urllib.error import HTTPError

CAPABILITY = "capability.absorbed-schedule-reporter"
TOOL = """import json, sys, tempfile, time, uuid
from pathlib import Path
data = json.load(sys.stdin)
report = {'id': uuid.uuid4().hex, 'label': data['label'], 'start': time.monotonic_ns()}
time.sleep(data['seconds'])
report['end'] = time.monotonic_ns()
Path(tempfile.gettempdir(), 'report-' + report['id'] + '.json').write_text(json.dumps(report))
print(json.dumps({'echo': data['label']}))
"""


def _write_tool(root: Path) -> None:
    directory = root / "capabilities" / "absorbed" / "schedule-reporter"
    directory.mkdir(parents=True)
    (directory / "tool.py").write_text(TOOL, encoding="utf-8")
    (directory / "absorption.json").write_text(json.dumps({
        "schema_version": 1, "slug": "schedule-reporter", "name": "schedule reporter",
        "command": ["python", "tool.py"], "requires": ["label", "seconds"], "provides": ["echo"],
        "cases": [{"input": {"label": word, "seconds": 0}, "expect": {"echo": word}} for word in ("a", "b")],
    }), encoding="utf-8")
    entry = {
        "id": CAPABILITY, "name": "schedule reporter", "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "python -c pass", "dependencies": [], "behavior_paths": [],
        "capability_delta": "", "tags": [], "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z", "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    (root / "capabilities" / "ledger.json").write_text(json.dumps({
        "schema_version": 1, "updated_at": "", "capabilities": {CAPABILITY: entry},
    }), encoding="utf-8")


def _request(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode()
    req = request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _start(src: Path, root: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("BLACKHOLE_")}
    env.update(PYTHONPATH=str(src), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    log = tempfile.TemporaryFile()
    process = subprocess.Popen(
        [sys.executable, "-m", "blackhole_agent.capability_service", "serve", "--root", str(root),
         "--port", "0", "--schedule"],
        stdout=subprocess.PIPE, stderr=log, env=env, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    result = {"process": process, "log": log}
    lines = []
    reader = threading.Thread(target=lambda: lines.append(process.stdout.readline()), daemon=True)
    reader.start()
    reader.join(timeout=20)
    try:
        ready = json.loads(lines[0]) if lines else {}
        result["url"] = f"http://127.0.0.1:{ready['listening']}"
    except (ValueError, KeyError):
        _stop(result)
        raise RuntimeError("HTTP service did not report readiness") from None
    return result


def _stop(server: dict) -> None:
    process = server["process"]
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)
    if process.stdout:
        process.stdout.close()
    server["log"].close()


def _until(read, predicate, *, timeout: float = 18):
    deadline = time.monotonic() + timeout
    value = None
    while time.monotonic() < deadline:
        value = read()
        if predicate(value):
            return value
        time.sleep(0.1)
    return value


def _schedule(url: str, label: str, seconds: float, interval: int) -> str:
    status, body = _request(url + "/schedules", "POST", {
        "capability_id": CAPABILITY, "input": {"label": label, "seconds": seconds}, "every_seconds": interval,
    })
    if status != 201:
        raise RuntimeError(f"schedule creation failed: {status} {body}")
    return body["schedule_id"]


def _record(url: str, ident: str) -> dict:
    return _request(url + "/schedules/" + ident)[1]


def _reports(root: Path, label: str) -> list[dict]:
    found = {}
    folder = root / ".blackhole-agent" / "invocation-artifacts"
    for path in folder.glob("*/report-*.json"):
        try:
            report = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if report.get("label") == label:
            found[report["id"]] = {**report, "artifact": path.parent.name + "/" + path.name}
    return sorted(found.values(), key=lambda row: row["start"])


def _execution_count(root: Path) -> int:
    folder = root / ".blackhole-agent" / "invocation-artifacts"
    return sum(1 for path in folder.glob("*") if path.is_dir())


def main() -> dict:
    from blackhole_agent import capability_service

    observed = {}
    servers = []
    scratch = tempfile.TemporaryDirectory(prefix="blackhole-schedule-ownership-")
    try:
        src = Path(capability_service.__file__).resolve().parents[1]
        root = Path(scratch.name) / "repo"
        _write_tool(root)
        owner = _start(src, root)
        servers.append(owner)
        slow = _schedule(owner["url"], "overlap", 4, 1)
        _until(lambda: _record(owner["url"], slow), lambda row: row.get("last_status") == "running")
        standby = _start(src, root)
        servers.append(standby)
        observed["status_after_standby_start"] = _record(standby["url"], slow).get("last_status")
        _until(lambda: _reports(root, "overlap"), lambda rows: len(rows) >= 2)
        deleted, _ = _request(standby["url"] + "/schedules/" + slow, "DELETE")
        # A fire already reserved at DELETE may finish, but no subsequent
        # fire may start. Let those bounded four-second tools drain.
        time.sleep(5)
        reports = _reports(root, "overlap")
        observed["slow_intervals_ns"] = [[r["start"], r["end"]] for r in reports]
        observed["non_overlapping"] = len(reports) >= 2 and all(
            left["end"] <= right["start"] for left, right in zip(reports, reports[1:])
        )
        before = _execution_count(root)
        time.sleep(1.3)
        missing, _ = _request(standby["url"] + "/schedules/" + slow)
        observed["delete_stops_fires"] = deleted == 200 and missing == 404 and _execution_count(root) == before
        if reports:
            code, downloaded = _request(standby["url"] + "/artifacts/" + reports[0]["artifact"])
            observed["report_download_matches"] = code == 200 and all(
                downloaded.get(key) == reports[0][key] for key in ("id", "start", "end", "label")
            )

        # Exit the owner between fires; the standby must continue this
        # existing schedule, preserving its saved output and run count.
        # Leave ample room for sandbox setup/teardown before the next fire,
        # so this tests an idle-owner exit rather than an uncertain run.
        quick = _schedule(owner["url"], "failover", 0.05, 8)
        completed = _until(lambda: _record(owner["url"], quick), lambda row: row.get("last_status") == "completed")
        count = completed.get("run_count", 0)
        _stop(owner)
        servers.remove(owner)
        recovered = _until(lambda: _record(standby["url"], quick), lambda row: row.get("run_count", 0) > count)
        observed["failover_run_counts"] = [count, recovered.get("run_count", 0)]
        observed["failover_output"] = recovered.get("last_output")
        observed["failover_status"] = recovered.get("last_status")
        _request(standby["url"] + "/schedules/" + quick, "DELETE")

        # Crash after reservation and real execution admission. A new owner
        # cannot know which effects completed, and must not retry this fire.
        before = _execution_count(root)
        uncertain = _schedule(standby["url"], "uncertain", 4, 1)
        _until(lambda: _execution_count(root), lambda n: n > before)
        _stop(standby)
        servers.remove(standby)
        after_crash = _execution_count(root)
        successor = _start(src, root)
        servers.append(successor)
        time.sleep(1.4)
        interrupted = _record(successor["url"], uncertain)
        observed["interrupted_status"] = interrupted.get("last_status")
        observed["interrupted_error"] = interrupted.get("last_error")
        observed["crash_execution_counts"] = [after_crash, _execution_count(root)]
        observed["unknown_outcome_not_replayed"] = (
            interrupted.get("last_status") == "interrupted"
            and "schedule_outcome_unknown" in str(interrupted.get("last_error"))
            and _execution_count(root) == after_crash
        )
        _request(successor["url"] + "/schedules/" + uncertain, "DELETE")
        status, result = _request(successor["url"] + "/invoke", "POST", {
            "capability_id": CAPABILITY, "input": {"label": "ordinary-invoke", "seconds": 0},
        })
        observed["ordinary_invoke"] = {"status": status, "output": result.get("output")}
        # Also let any finite baseline orphan finish before fixture removal.
        time.sleep(4.5)
        return {"passed": bool(
            observed["status_after_standby_start"] == "running"
            and observed["non_overlapping"]
            and observed["delete_stops_fires"]
            and observed.get("report_download_matches")
            and count >= 1 and recovered.get("run_count", 0) > count
            and recovered.get("last_output") == {"echo": "failover"}
            and observed["unknown_outcome_not_replayed"]
            and status == 200 and result.get("output") == {"echo": "ordinary-invoke"}
        ), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        for server in servers:
            _stop(server)
        scratch.cleanup()


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
