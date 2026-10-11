"""Acceptance probe: POST /solve previews a plan without executing tools.

Declarative POST /solve currently always runs the planned untrusted program,
so an operator cannot inspect the evidence-ranked plan without side effects.
This probe starts the live invocation plane as a separate OS process and
drives real loopback HTTP:

1. GET /health reports solve_plan_preview.
2. POST /solve with dry_run true for a fixture append tool returns HTTP 200
   with solved true, dry_run true, a nonempty plan naming that tool, empty
   steps, and the append canary file is absent.
3. Prefer: solve=preview is equivalent and still writes no canary.
4. dry_run of an unsolvable goal returns solved false and spawns no tool.
5. GET /console includes a preview control that POSTs dry_run.
6. A follow-up live POST /solve of the same append goal writes the canary,
   and a reverse invoke still returns the declared reverse output.

On the pre-mission plane dry_run is ignored (the append tool runs) and
GET /health does not report solve_plan_preview, so the probe reports
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
APPEND_TOOL = (
    "import json, os, sys\n"
    "from pathlib import Path\n"
    "s = json.load(sys.stdin)\n"
    "path = Path(s['events'])\n"
    "path.parent.mkdir(parents=True, exist_ok=True)\n"
    "with path.open('a', encoding='utf-8') as handle:\n"
    "    handle.write(s['label'] + '\\n')\n"
    "    handle.flush()\n"
    "    os.fsync(handle.fileno())\n"
    "print(json.dumps({'saved': s['label']}))\n"
)
PROBE_TEXT = "solve-plan-preview-00e8c0f2"
EXPECTED = PROBE_TEXT[::-1]


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


def _add_tool(
    root: Path,
    *,
    slug: str,
    name: str,
    body: str,
    requires: list[str],
    provides: list[str],
    cases: list[dict],
) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(body, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": name,
                "command": [sys.executable, "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path, events: Path) -> Path:
    root = base / "repo"
    _add_tool(
        root,
        slug="text-reverser",
        name="probe text reverser",
        body=REVERSE_TOOL,
        requires=["raw_text"],
        provides=["reversed_text"],
        cases=[
            {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
        ],
    )
    _add_tool(
        root,
        slug="append-event",
        name="append event",
        body=APPEND_TOOL,
        requires=["events", "label"],
        provides=["saved"],
        cases=[
            {"input": {"events": str(events), "label": label}, "expect": {"saved": label}}
            for label in ("a", "b")
        ],
    )
    proved = {
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    capabilities = {
        "capability.absorbed-text-reverser": dict(
            proved, id="capability.absorbed-text-reverser", name="probe text reverser"
        ),
        "capability.absorbed-append-event": dict(
            proved, id="capability.absorbed-append-event", name="append event"
        ),
    }
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _count(events: Path, label: str) -> int:
    if not events.is_file():
        return 0
    return events.read_text(encoding="utf-8").splitlines().count(label)


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _console_drives_preview(page: str) -> bool:
    return all(
        marker in page
        for marker in (
            "function previewSolve()",
            "function solveGoal()",
            "body.dry_run = true",
            'postJSON("/solve"',
        )
    )


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "solve-plan-preview"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="solve-plan-preview-") as directory:
        base = Path(directory)
        root = base / "repo"
        events = root / "capabilities" / "absorbed" / "append-event" / "effects.txt"
        _build_fixture_root(base, events)
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
            url = f"http://127.0.0.1:{ready['listening']}"

            health_status, health, _ = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("solve_plan_preview") is True
            )

            preview_body = {
                "initial_state": {"events": str(events), "label": "preview-body"},
                "goal": ["saved"],
                "dry_run": True,
            }
            preview_status, preview, _ = _request("POST", f"{url}/solve", preview_body)
            observed["preview_status"] = preview_status
            observed["preview"] = preview if isinstance(preview, dict) else None
            observed["preview_body_count"] = _count(events, "preview-body")
            preview_ok = (
                preview_status == 200
                and isinstance(preview, dict)
                and preview.get("solved") is True
                and preview.get("dry_run") is True
                and preview.get("plan") == ["capability.absorbed-append-event"]
                and preview.get("steps") == []
                and _count(events, "preview-body") == 0
            )

            prefer_status, prefer, _ = _request(
                "POST",
                f"{url}/solve",
                {
                    "initial_state": {"events": str(events), "label": "preview-prefer"},
                    "goal": ["saved"],
                },
                headers={"Prefer": "solve=preview"},
            )
            observed["prefer_status"] = prefer_status
            observed["prefer"] = prefer if isinstance(prefer, dict) else None
            observed["preview_prefer_count"] = _count(events, "preview-prefer")
            prefer_ok = (
                prefer_status == 200
                and isinstance(prefer, dict)
                and prefer.get("dry_run") is True
                and prefer.get("plan") == ["capability.absorbed-append-event"]
                and prefer.get("steps") == []
                and _count(events, "preview-prefer") == 0
            )

            unsolved_status, unsolved, _ = _request(
                "POST",
                f"{url}/solve",
                {
                    "initial_state": {"events": str(events), "label": "preview-unsolved"},
                    "goal": ["no_such_key"],
                    "dry_run": True,
                },
            )
            observed["unsolved_status"] = unsolved_status
            observed["unsolved"] = unsolved if isinstance(unsolved, dict) else None
            observed["preview_unsolved_count"] = _count(events, "preview-unsolved")
            unsolved_ok = (
                unsolved_status == 200
                and isinstance(unsolved, dict)
                and unsolved.get("solved") is False
                and unsolved.get("dry_run") is True
                and unsolved.get("plan") is None
                and _count(events, "preview-unsolved") == 0
            )

            console_status, console_page, console_headers = _request("GET", f"{url}/console")
            page_text = console_page if isinstance(console_page, str) else json.dumps(console_page)
            observed["console_status"] = console_status
            observed["console_content_type"] = console_headers.get("content-type", "")
            console_ok = (
                console_status == 200
                and "text/html" in str(console_headers.get("content-type") or "")
                and _console_drives_preview(page_text)
            )
            observed["console_drives_preview"] = console_ok

            live_status, live, _ = _request(
                "POST",
                f"{url}/solve",
                {
                    "initial_state": {"events": str(events), "label": "live-run"},
                    "goal": ["saved"],
                },
            )
            observed["live_status"] = live_status
            observed["live"] = live if isinstance(live, dict) else None
            observed["live_count"] = _count(events, "live-run")
            live_ok = (
                live_status == 200
                and isinstance(live, dict)
                and live.get("solved") is True
                and live.get("dry_run") is not True
                and live.get("outcome", {}).get("saved") == "live-run"
                and _count(events, "live-run") == 1
            )

            invoke_status, invoked, _ = _request(
                "POST",
                f"{url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            observed["invoke_status"] = invoke_status
            observed["invoked"] = invoked if isinstance(invoked, dict) else None
            invoke_ok = (
                invoke_status == 200
                and isinstance(invoked, dict)
                and invoked.get("output", {}).get("reversed_text") == EXPECTED
            )

            passed = all(
                (
                    health_ok,
                    preview_ok,
                    prefer_ok,
                    unsolved_ok,
                    console_ok,
                    live_ok,
                    invoke_ok,
                )
            )
            observed["checks"] = {
                "health": health_ok,
                "preview_body": preview_ok,
                "preview_prefer": prefer_ok,
                "unsolved": unsolved_ok,
                "console": console_ok,
                "live_solve": live_ok,
                "reverse_invoke": invoke_ok,
            }
            return {"passed": passed, "observed": observed}
        finally:
            process.kill()
            try:
                process.wait(timeout=5)
            except Exception:
                pass


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict, sort_keys=True))
    sys.exit(0)
