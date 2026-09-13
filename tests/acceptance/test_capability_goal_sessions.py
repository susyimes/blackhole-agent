"""Acceptance probe: the live plane runs durable, interactive goal sessions.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe
is fully self-contained: it builds a minimal ledger with chainable vendored
tools in a temp directory, starts the invocation plane as a separate OS
process (the way an operator would), and drives it over a real loopback
socket through the four session behaviors that define the mission:

1. Elicitation — a session whose goal needs a state key no capability
   provides answers ``awaiting_input`` naming exactly that key (with the
   consuming capability) and spawns no subprocess.
2. Interaction — supplying the elicited key through the session endpoint
   resumes execution and reaches ``solved`` with a digest-bound outcome;
   the session ``plan_digest`` equals the one-shot ``POST /solve`` digest
   for the same goal, proving the interactive path is the same real
   execution, not a parallel fake.
3. Durability — the server process is killed while sessions are mid-flight;
   a fresh server process on the same root still serves the awaiting
   session to completion, and a session that was mid-execution at the kill
   comes back as ``interrupted`` and resumes to ``solved`` from its
   persisted threaded state.
4. Cancellation — ``DELETE`` on a session running a long-lived tool kills
   the tool's entire process tree: the tool's post-sleep side effect never
   materializes even after its full sleep would have elapsed, and the
   session records a ``cancelled`` verdict.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees: the baseline plane has no ``/sessions`` path,
so session creation is answered 404 and the probe reports passed=false.
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
from urllib.error import HTTPError

_REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_SHOUTER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'loud_text': state['reversed_text'].upper()}))\n"
)

_SLOW_MARKER = (
    "import json, sys, time, pathlib\n"
    "state = json.load(sys.stdin)\n"
    f"time.sleep({int(os.environ.get('PROBE_SLEEP', '0')) or 20})\n"
    "pathlib.Path(state['marker_path']).write_text('done')\n"
    "print(json.dumps({'marker_done': True}))\n"
)


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
    except Exception:
        return 0, None


def _write_tool(root: Path, slug: str, source: str, requires: list, provides: list) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    cases = []
    for value in ("ab", "cd"):
        case_input = {}
        for key in requires:
            case_input[key] = str(root / "case-marker.txt") if key == "marker_path" else value
        cases.append({"input": case_input, "expect": {key: "x" for key in provides}})
    manifest = {
        "schema_version": 1,
        "slug": slug,
        "name": f"probe {slug}",
        "command": ["python", "tool.py"],
        "requires": requires,
        "provides": provides,
        "cases": cases,
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")


def _ledger_entry(capability_id: str) -> dict:
    return {
        "id": capability_id,
        "name": capability_id,
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


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "text-reverser", _REVERSER, ["raw_text"], ["reversed_text"])
    _write_tool(root, "loud-shouter", _SHOUTER, ["reversed_text"], ["loud_text"])
    _write_tool(root, "slow-marker", _SLOW_MARKER, ["start_token", "marker_path"], ["marker_done"])
    ids = [
        "capability.absorbed-text-reverser",
        "capability.absorbed-loud-shouter",
        "capability.absorbed-slow-marker",
    ]
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {cid: _ledger_entry(cid) for cid in ids},
            }
        ),
        encoding="utf-8",
    )
    return root


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _start_server(src_root: Path, root: Path) -> tuple[subprocess.Popen, str] | None:
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
    reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
    reader.start()
    reader.join(timeout=60)
    ready = sink.get("ready")
    if not isinstance(ready, dict) or not ready.get("listening"):
        process.kill()
        return None
    return process, f"http://127.0.0.1:{ready['listening']}"


def _stop_server(process: subprocess.Popen, *, hard: bool = False) -> None:
    if hard:
        process.kill()
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _wait_session(base: str, session_id: str, wanted: set, timeout: float = 40.0) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = _request("GET", f"{base}/sessions/{session_id}")
        if status == 200 and isinstance(body, dict):
            session = body.get("session") or {}
            if session.get("status") in wanted:
                return session
        time.sleep(0.2)
    return None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "capability-goal-sessions"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "build_server"):
        observed["detail"] = "baseline plane cannot serve"
        return {"passed": False, "observed": observed}
    try:
        import blackhole_agent.capability_sessions  # noqa: F401
    except Exception:
        observed["detail"] = "baseline plane has no goal sessions"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="capability-session-probe-") as directory:
        root = _build_fixture_root(Path(directory))
        started = _start_server(src_root, root)
        if started is None:
            observed["detail"] = "server never reported a listening port"
            return {"passed": False, "observed": observed}
        process, base = started
        try:
            # 1. elicitation: missing external key is named, nothing runs
            status, created = _request(
                "POST", f"{base}/sessions", {"initial_state": {}, "goal": ["loud_text"]}
            )
            session = created.get("session") if isinstance(created, dict) else None
            observed["create_status"] = status
            observed["create_body_status"] = session.get("status") if session else None
            session_id = session.get("session_id") if session else None
            checks["elicitation"] = (
                status == 200
                and isinstance(session, dict)
                and session.get("status") == "awaiting_input"
                and session.get("pending_keys") == ["raw_text"]
                and session.get("key_consumers", {}).get("raw_text")
                == "capability.absorbed-text-reverser"
                and session.get("steps") == []
            )

            # interrupted resume fixture: a slow session mid-execution at kill time
            resume_marker = Path(directory) / "resume-marker.txt"
            status, slow_created = _request(
                "POST",
                f"{base}/sessions",
                {
                    "initial_state": {
                        "start_token": "go",
                        "marker_path": str(resume_marker),
                    },
                    "goal": ["marker_done"],
                },
            )
            slow_session = slow_created.get("session") if isinstance(slow_created, dict) else {}
            slow_id = slow_session.get("session_id")
            checks["slow_session_running"] = slow_session.get("status") == "running"
            time.sleep(2.0)  # let the tool subprocess actually spawn

            # 3a. durability: kill the server mid-flight with sessions open
            _stop_server(process, hard=True)
            restarted = _start_server(src_root, root)
            if restarted is None:
                observed["detail"] = "restarted server never reported a port"
                return {"passed": False, "observed": observed}
            process, base = restarted
            status, body = _request("GET", f"{base}/sessions/{session_id}")
            checks["awaiting_survives_restart"] = (
                status == 200
                and isinstance(body, dict)
                and body.get("session", {}).get("status") == "awaiting_input"
            )
            interrupted = _wait_session(base, slow_id, {"interrupted"}, timeout=10)
            checks["running_marks_interrupted"] = interrupted is not None

            # 3b. resume the interrupted session from persisted threaded state
            if interrupted is not None:
                status, _ = _request("POST", f"{base}/sessions/{slow_id}/resume", {"input": {}})
                resumed = _wait_session(base, slow_id, {"solved", "failed"}, timeout=45)
                checks["interrupted_resumes_to_solved"] = (
                    resumed is not None
                    and resumed.get("status") == "solved"
                    and resumed.get("outcome") == {"marker_done": True}
                    and resume_marker.is_file()
                )
            else:
                checks["interrupted_resumes_to_solved"] = False

            # 2. interaction: supply the elicited key on the awaited session
            status, answered = _request(
                "POST",
                f"{base}/sessions/{session_id}/input",
                {"input": {"raw_text": "blackhole"}},
            )
            checks["input_accepted"] = status == 200
            solved = _wait_session(base, session_id, {"solved", "failed"}, timeout=40)
            observed["solved_outcome"] = solved.get("outcome") if solved else None
            checks["elicted_session_solves"] = (
                solved is not None
                and solved.get("status") == "solved"
                and solved.get("outcome") == {"loud_text": "ELOHKCALB"}
                and bool(solved.get("plan_digest"))
            )

            # same real execution as the one-shot solve path: the plan and
            # every per-step response digest (binding capability id, input,
            # and output) must be identical, not a parallel fake.
            status, oneshot = _request(
                "POST",
                f"{base}/solve",
                {"initial_state": {"raw_text": "blackhole"}, "goal": ["loud_text"]},
            )
            oneshot_steps = oneshot.get("steps") if isinstance(oneshot, dict) else None
            session_steps = solved.get("steps") if solved else None
            checks["digest_matches_one_shot_solve"] = (
                status == 200
                and isinstance(oneshot, dict)
                and oneshot.get("solved") is True
                and solved is not None
                and oneshot.get("plan") == solved.get("plan")
                and isinstance(oneshot_steps, list)
                and isinstance(session_steps, list)
                and [s.get("response_digest") for s in oneshot_steps]
                == [s.get("response_digest") for s in session_steps]
            )

            # 4. cancellation: DELETE kills the running tool's whole tree
            cancel_marker = Path(directory) / "cancel-marker.txt"
            cancel_started = time.monotonic()
            status, cancel_created = _request(
                "POST",
                f"{base}/sessions",
                {
                    "initial_state": {
                        "start_token": "go",
                        "marker_path": str(cancel_marker),
                    },
                    "goal": ["marker_done"],
                },
            )
            cancel_session = cancel_created.get("session") if isinstance(cancel_created, dict) else {}
            cancel_id = cancel_session.get("session_id")
            time.sleep(2.0)
            status, _ = _request("DELETE", f"{base}/sessions/{cancel_id}")
            cancelled = _wait_session(base, cancel_id, {"cancelled"}, timeout=15)
            cancel_elapsed = time.monotonic() - cancel_started
            checks["cancel_records_verdict"] = (
                cancelled is not None
                and cancelled.get("status") == "cancelled"
                and cancel_elapsed < 20
            )
            remaining = 22 - cancel_elapsed
            if remaining > 0:
                time.sleep(remaining)
            checks["cancelled_tree_side_effect_absent"] = not cancel_marker.exists()
            observed["cancel_elapsed_seconds"] = round(cancel_elapsed, 1)
        finally:
            _stop_server(process)

    observed["checks"] = checks
    return {"passed": bool(checks) and all(checks.values()), "observed": observed}


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
