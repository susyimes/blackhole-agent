"""Acceptance probe: the live plane refuses excess concurrent tool trees.

Per-tree resource limits still leave the host exposed: every concurrent
POST /invoke starts another owned job. This probe starts the invocation
plane as a separate OS process with BLACKHOLE_MAX_INFLIGHT=1, holds that
single slot with a fixture tool, and requires a concurrent POST /invoke
to return HTTP 429 without spawning. After the hold finishes, a follow-up
text-reverser invoke still returns the declared reverse output.

On the pre-mission plane the second invoke runs (200, ran-canary written)
instead of 429, so the probe reports passed=false. Both outcomes exit 0
with JSON ``passed`` and nonempty ``observed``.
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

PROBE_TEXT = "admission-cap-a3fcac3b"
EXPECTED = PROBE_TEXT[::-1]

_HOLD_TOOL = r"""
import json, sys, time
from pathlib import Path
state = json.load(sys.stdin)
Path(state["canary_path"]).write_text("holding", encoding="utf-8")
time.sleep(8)
print(json.dumps({"held": True}))
"""

_RAN_TOOL = r"""
import json, sys
from pathlib import Path
state = json.load(sys.stdin)
Path(state["canary_path"]).write_text("ran", encoding="utf-8")
print(json.dumps({"ran": True}))
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
                        "expect": {key: True if key in {"held", "ran"} else "x" for key in provides},
                    }
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "hold-slot", _HOLD_TOOL, ["canary_path"], ["held"])
    _write_tool(root, "ran-flag", _RAN_TOOL, ["canary_path"], ["ran"])
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        "capability.absorbed-hold-slot": _ledger_entry(
            "capability.absorbed-hold-slot", "probe hold slot"
        ),
        "capability.absorbed-ran-flag": _ledger_entry(
            "capability.absorbed-ran-flag", "probe ran flag"
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


def _request(
    method: str, url: str, payload: dict | None = None, *, timeout: int = 30
) -> tuple[int, object, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, json.loads(response.read().decode("utf-8")), headers
    except HTTPError as exc:
        headers = {key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])}
        try:
            return exc.code, json.loads(exc.read().decode("utf-8")), headers
        except Exception:
            return exc.code, None, headers


def _canary_exists(path: Path) -> bool:
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "invocation-admission"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="invocation-admission-probe-", ignore_cleanup_errors=True)
    try:
        base = Path(scratch.name)
        root = _build_fixture_root(base)
        hold_canary = root / "capabilities" / "absorbed" / "hold-slot" / "canary.txt"
        ran_canary = root / "capabilities" / "absorbed" / "ran-flag" / "canary.txt"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        env["BLACKHOLE_MAX_INFLIGHT"] = "1"
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
            hold_payload = {
                "capability_id": "capability.absorbed-hold-slot",
                "input": {"canary_path": str(hold_canary)},
            }
            hold_box: dict[str, object] = {}

            def _hold() -> None:
                try:
                    hold_box["result"] = _request(
                        "POST", f"{base_url}/invoke", hold_payload, timeout=40
                    )
                except Exception as exc:
                    hold_box["error"] = f"{type(exc).__name__}: {exc}"

            holder = threading.Thread(target=_hold, daemon=True)
            holder.start()
            started = time.monotonic()
            while time.monotonic() - started < 20:
                if _canary_exists(hold_canary):
                    break
                time.sleep(0.05)
            hold_started = _canary_exists(hold_canary)
            observed["hold_started"] = hold_started
            if not hold_started:
                observed["detail"] = "hold tool never wrote its canary"
                observed["hold_box"] = hold_box
                err = ""
                try:
                    if process.stderr:
                        # Non-blocking-ish: process still running; skip full read.
                        err = ""
                except Exception:
                    err = ""
                observed["stderr"] = err
                return {"passed": False, "observed": observed}

            health_status, health, _health_headers = _request("GET", f"{base_url}/health")
            observed["health_status"] = health_status
            observed["health"] = health
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("ok") is True
                and int(health.get("max_inflight") or 0) == 1
                and int(health.get("inflight") or 0) >= 1
            )

            second_status, second, second_headers = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-ran-flag",
                    "input": {"canary_path": str(ran_canary)},
                },
                timeout=15,
            )
            time.sleep(0.2)
            ran_wrote = _canary_exists(ran_canary)
            observed["second_status"] = second_status
            observed["second_body"] = second
            observed["second_retry_after"] = second_headers.get("retry-after")
            observed["ran_canary_written"] = ran_wrote
            second_ok = (
                second_status == 429
                and isinstance(second, dict)
                and second.get("ok") is False
                and second.get("violation") == "admission_limited"
                and bool(second_headers.get("retry-after"))
                and not ran_wrote
            )

            holder.join(timeout=25)
            observed["hold_box"] = {
                "error": hold_box.get("error"),
                "status": hold_box["result"][0] if "result" in hold_box else None,
            }

            follow_status, follow, _follow_headers = _request(
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
            ready_cap = ready.get("max_inflight") if isinstance(ready, dict) else None
            observed["checks"] = {
                "hold_started": hold_started,
                "health_reports_cap": health_ok,
                "second_refused_without_spawn": second_ok,
                "follow_up_invoke_ok": follow_ok,
                "ready_max_inflight": ready_cap,
            }
            return {
                "passed": bool(hold_started and health_ok and second_ok and follow_ok),
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
                "family": "invocation-admission",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
