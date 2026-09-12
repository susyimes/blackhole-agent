"""Acceptance probe: the live plane solves declarative goals end-to-end.

The controller replays probes via runpy from a temp copy with only the
implementation ``src`` on sys.path (isolated ``python -I``), so this probe
is fully self-contained: it builds a minimal ledger with two chainable
vendored tools in a temp directory, starts the invocation plane as a
separate OS process (the way an operator would), and drives it over a real
loopback socket — submitting a declarative goal (initial state + goal keys,
no capability id) to ``POST /solve`` and confirming the plane derives the
minimal two-step program, executes both steps as real subprocesses with
threaded state, and returns the digest-bound outcome; that an unsolvable
goal is honestly reported without a plan; and that malformed requests are
refused fail-closed.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees: the baseline plane has no ``/solve`` path, so
the goal request is answered 404 and the probe reports passed=false.
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


def _write_tool(root: Path, slug: str, source: str, requires: list, provides: list) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": slug,
        "name": f"probe {slug}",
        "command": ["python", "tool.py"],
        "requires": requires,
        "provides": provides,
        "cases": [
            {
                "input": {key: value for key in requires},
                "expect": {key: "x" for key in provides},
            }
            for value in ("ab", "cd")
        ],
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
    capabilities = {
        "capability.absorbed-text-reverser": _ledger_entry("capability.absorbed-text-reverser"),
        "capability.absorbed-loud-shouter": _ledger_entry("capability.absorbed-loud-shouter"),
    }
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
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


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "capability-goal-solve"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "solve_goal_request"):
        observed["detail"] = "baseline plane has no goal solver"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="capability-solve-probe-") as directory:
        root = _build_fixture_root(Path(directory))
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
                observed["detail"] = "server never reported a listening port"
                return {"passed": False, "observed": observed}
            base = f"http://127.0.0.1:{ready['listening']}"

            status, solved = _request(
                "POST",
                f"{base}/solve",
                {"initial_state": {"raw_text": "blackhole"}, "goal": ["loud_text"]},
            )
            observed["solve_status"] = status
            observed["solve_plan"] = solved.get("plan") if isinstance(solved, dict) else None
            observed["solve_outcome"] = (
                solved.get("outcome") if isinstance(solved, dict) else None
            )
            steps = solved.get("steps") if isinstance(solved, dict) else None
            observed["solve_steps"] = [
                {"capability_id": step.get("capability_id"), "input": step.get("input")}
                for step in steps
            ] if isinstance(steps, list) else steps
            solve_ok = (
                status == 200
                and isinstance(solved, dict)
                and solved.get("solved") is True
                and solved.get("plan")
                == ["capability.absorbed-text-reverser", "capability.absorbed-loud-shouter"]
                and solved.get("outcome") == {"loud_text": "ELOHKCALB"}
                and isinstance(steps, list)
                and len(steps) == 2
                and steps[1].get("input") == {"reversed_text": "elohkcalb"}
                and all(step.get("response_digest") for step in steps)
                and bool(solved.get("plan_digest"))
            )

            status, unsolved = _request(
                "POST",
                f"{base}/solve",
                {"initial_state": {"raw_text": "blackhole"}, "goal": ["no_such_key"]},
            )
            observed["unsolved_status"] = status
            observed["unsolved_body"] = unsolved
            unsolved_ok = (
                status == 200
                and isinstance(unsolved, dict)
                and unsolved.get("solved") is False
                and unsolved.get("plan") is None
            )

            status, malformed = _request(
                "POST", f"{base}/solve", {"initial_state": {}, "goal": []}
            )
            observed["malformed_status"] = status
            malformed_ok = (
                status == 422
                and isinstance(malformed, dict)
                and malformed.get("ok") is False
            )

            observed["checks"] = {
                "derived_program_executed": solve_ok,
                "unsolvable_honest": unsolved_ok,
                "malformed_refused": malformed_ok,
            }
            passed = solve_ok and unsolved_ok and malformed_ok
            return {"passed": passed, "observed": observed}
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
