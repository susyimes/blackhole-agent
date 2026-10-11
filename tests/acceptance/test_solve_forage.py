"""Acceptance probe: POST /solve forages an operator-named local package.

Declarative POST /solve currently returns solved false and stops when no
proved program covers the goal, even when the operator names a local package
that would provide the missing state keys. This probe starts the live
invocation plane as a separate OS process with --forage-root and drives
real loopback HTTP:

1. GET /health reports solve_forage true.
2. POST /solve of a goal covered only after foraging the fixture package
   returns HTTP 200 with solved true and the fixture output.
3. GET /capabilities lists the newly absorbed id.
4. A second POST /solve of the same goal with no forage list still returns
   that output.
5. POST /solve with a path outside the forage root returns HTTP 400 and
   does not absorb a second tree.
6. A plane started without --forage-root reports solve_forage false,
   returns solved false for the uncovered goal, and refuses a forage list
   with HTTP 400 forage_disabled.
7. A follow-up REST POST /invoke of the text-reverser still returns the
   declared reverse output.

On the pre-mission plane forage is ignored, the first solve returns solved
false, and GET /health does not report solve_forage, so the probe reports
passed=false. Both outcomes exit 0 with JSON passed and nonempty observed.
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

REVERSE_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)
PACKAGE_SOURCE = '''"""Probe fixture: a bare package the live plane must forage."""

def shout(text):
    return text.upper() + "!"
'''
PROBE_TEXT = "solve-forage-a90a084e"
EXPECTED = PROBE_TEXT[::-1]
SHOUT_STATE = {"text": "blackhole unbound"}
SHOUT_OUTPUT = "BLACKHOLE UNBOUND!"
ABSORBED_ID = "capability.absorbed-shout-lab"
REVERSE_ID = "capability.absorbed-text-reverser"


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


def _add_reverser(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "probe-workspace"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(REVERSE_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "text-reverser",
                "name": "probe text reverser",
                "command": [sys.executable, "tool.py"],
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
    capabilities = {
        REVERSE_ID: {
            "id": REVERSE_ID,
            "name": "probe text reverser",
            "description": "probe fixture reverser",
            "kind": "python",
            "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
            "proof_command": "uv run python -c \"pass\"",
            "dependencies": [],
            "behavior_paths": [],
            "last_proved_at": "2026-01-01T00:00:00Z",
            "last_proof_exit_code": 0,
        }
    }
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )


def _write_candidate(forage_root: Path) -> Path:
    package = forage_root / "shout-lab"
    package.mkdir(parents=True)
    (package / "shout_lab.py").write_text(PACKAGE_SOURCE, encoding="utf-8")
    return package


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _start_plane(
    src_root: Path,
    root: Path,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen, dict[str, object]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
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
    reader.join(timeout=60)
    return process, sink


def _stop_plane(process: subprocess.Popen) -> str:
    process.kill()
    try:
        _out, err = process.communicate(timeout=10)
    except Exception:
        err = ""
    return err if isinstance(err, str) else ""


def _console_drives_forage(page: str) -> bool:
    return all(
        marker in page
        for marker in (
            'id="solve-forage"',
            "body.forage = forage",
            "function solveGoal()",
            'postJSON("/solve"',
        )
    )


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "solve-forage"}
    try:
        import blackhole_agent.capability_service as service
        import blackhole_agent.goal_foraging as foraging
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "_solve_http_request") or not hasattr(foraging, "resolve_live_forage_candidates"):
        observed["detail"] = "baseline plane has no live forage dispatch"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="solve-forage-probe-") as directory:
        base = Path(directory)
        root = base / "repo"
        _add_reverser(root)
        forage_root = base / "forage"
        _write_candidate(forage_root)

        process, sink = _start_plane(
            src_root,
            root,
            ["--forage-root", str(forage_root)],
        )
        try:
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = _stop_plane(process)
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            url = f"http://127.0.0.1:{ready['listening']}"
            observed["ready_solve_forage"] = ready.get("solve_forage")

            health_status, health, _ = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("solve_forage") is True
            )

            forage_body = {
                "initial_state": SHOUT_STATE,
                "goal": ["shout_output"],
                "forage": [{"name": "shout-lab", "slug": "shout-lab", "hint": "shout_lab"}],
            }
            forage_status, forage, _ = _request(
                "POST", f"{url}/solve", forage_body, timeout=240
            )
            observed["forage_status"] = forage_status
            observed["forage"] = forage if isinstance(forage, dict) else None
            acquisition = (
                forage.get("acquisition")
                if isinstance(forage, dict) and isinstance(forage.get("acquisition"), dict)
                else {}
            )
            forage_ok = (
                forage_status == 200
                and isinstance(forage, dict)
                and forage.get("solved") is True
                and forage.get("outcome", {}).get("shout_output") == SHOUT_OUTPUT
                and ABSORBED_ID in (forage.get("plan") or [])
                and acquisition.get("needed") is True
                and ABSORBED_ID in (acquisition.get("acquired_capability_ids") or [])
            )

            cap_status, listing, _ = _request("GET", f"{url}/capabilities")
            observed["capabilities_status"] = cap_status
            ids = []
            if isinstance(listing, dict):
                ids = [
                    str(item.get("id"))
                    for item in (listing.get("capabilities") or [])
                    if isinstance(item, dict)
                ]
            observed["capability_ids"] = ids
            listed_ok = cap_status == 200 and ABSORBED_ID in ids

            replay_status, replay, _ = _request(
                "POST",
                f"{url}/solve",
                {"initial_state": SHOUT_STATE, "goal": ["shout_output"]},
            )
            observed["replay_status"] = replay_status
            observed["replay"] = replay if isinstance(replay, dict) else None
            replay_acquisition = (
                replay.get("acquisition")
                if isinstance(replay, dict) and isinstance(replay.get("acquisition"), dict)
                else {}
            )
            replay_ok = (
                replay_status == 200
                and isinstance(replay, dict)
                and replay.get("solved") is True
                and replay.get("outcome", {}).get("shout_output") == SHOUT_OUTPUT
                and replay_acquisition.get("needed") in (None, False)
            )

            before_escape = {
                path.name
                for path in (root / "capabilities" / "absorbed").iterdir()
                if path.is_dir()
            }
            escape_status, escaped, _ = _request(
                "POST",
                f"{url}/solve",
                {
                    "initial_state": SHOUT_STATE,
                    "goal": ["shout_output"],
                    "forage": ["../outside"],
                },
            )
            observed["escape_status"] = escape_status
            observed["escape"] = escaped if isinstance(escaped, dict) else None
            after_escape = {
                path.name
                for path in (root / "capabilities" / "absorbed").iterdir()
                if path.is_dir()
            }
            escape_ok = (
                escape_status == 400
                and isinstance(escaped, dict)
                and escaped.get("error") == "forage_path_not_allowed"
                and after_escape == before_escape
            )

            console_status, console_page, console_headers = _request("GET", f"{url}/console")
            page_text = console_page if isinstance(console_page, str) else json.dumps(console_page)
            console_ok = (
                console_status == 200
                and "text/html" in str(console_headers.get("content-type") or "")
                and _console_drives_forage(page_text)
            )
            observed["console_drives_forage"] = console_ok

            invoke_status, invoked, _ = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
            )
            observed["invoke_status"] = invoke_status
            observed["invoked"] = invoked if isinstance(invoked, dict) else None
            invoke_ok = (
                invoke_status == 200
                and isinstance(invoked, dict)
                and invoked.get("output", {}).get("reversed_text") == EXPECTED
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-4000:]

        closed_root = base / "closed"
        _add_reverser(closed_root)
        closed, closed_sink = _start_plane(src_root, closed_root)
        try:
            closed_ready = closed_sink.get("ready")
            observed["closed_ready"] = closed_ready
            if not isinstance(closed_ready, dict) or not closed_ready.get("listening"):
                err = _stop_plane(closed)
                observed["closed_detail"] = "closed plane never reported a listening port"
                observed["closed_stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            closed_url = f"http://127.0.0.1:{closed_ready['listening']}"
            closed_health_status, closed_health, _ = _request("GET", f"{closed_url}/health")
            observed["closed_health"] = closed_health if isinstance(closed_health, dict) else None
            closed_health_ok = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("solve_forage") is False
            )
            unsolved_status, unsolved, _ = _request(
                "POST",
                f"{closed_url}/solve",
                {"initial_state": SHOUT_STATE, "goal": ["shout_output"]},
            )
            observed["closed_unsolved"] = unsolved if isinstance(unsolved, dict) else None
            unsolved_ok = (
                unsolved_status == 200
                and isinstance(unsolved, dict)
                and unsolved.get("solved") is False
            )
            refused_status, refused, _ = _request(
                "POST",
                f"{closed_url}/solve",
                {
                    "initial_state": SHOUT_STATE,
                    "goal": ["shout_output"],
                    "forage": [{"name": "shout-lab", "slug": "shout-lab"}],
                },
            )
            observed["closed_refused"] = refused if isinstance(refused, dict) else None
            refused_ok = (
                refused_status == 400
                and isinstance(refused, dict)
                and refused.get("error") == "forage_disabled"
            )
            closed_ok = closed_health_ok and unsolved_ok and refused_ok
        finally:
            observed["closed_stderr"] = (_stop_plane(closed) or "")[-4000:]

        passed = all(
            (
                health_ok,
                forage_ok,
                listed_ok,
                replay_ok,
                escape_ok,
                console_ok,
                invoke_ok,
                closed_ok,
            )
        )
        observed["checks"] = {
            "health": health_ok,
            "forage_solve": forage_ok,
            "listed": listed_ok,
            "replay": replay_ok,
            "escape": escape_ok,
            "console": console_ok,
            "reverse_invoke": invoke_ok,
            "fail_closed": closed_ok,
        }
        return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
