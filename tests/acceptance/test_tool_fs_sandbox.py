"""Acceptance probe: untrusted HTTP-invoked tools cannot touch host files.

Absorbed tools already run with a scrubbed environment and resource bounds,
but they could still open arbitrary host paths. This probe builds a minimal
ledger whose tool reports whether it can read a canary secret placed *outside*
its vendored tree, starts the invocation plane as a separate OS process, and
drives a real loopback ``POST /invoke``.

On the candidate plane the tool must reverse its input, read a file inside
its vendored tree, fail to read the canary, and fail to write beside it. On
the previous-milestone plane the canary is readable, so the probe reports
``passed=false``.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes.
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

_TOOL = r"""
import json, pathlib, sys
state = json.load(sys.stdin)
obs = {"reversed_text": state["raw_text"][::-1]}
canary = pathlib.Path(state["canary_path"])
try:
    obs["canary_text"] = canary.read_text(encoding="utf-8")
    obs["canary_readable"] = True
except Exception as exc:
    obs["canary_readable"] = False
    obs["canary_error"] = type(exc).__name__
try:
    obs["inside_text"] = pathlib.Path("inside.txt").read_text(encoding="utf-8")
    obs["inside_readable"] = True
except Exception as exc:
    obs["inside_readable"] = False
    obs["inside_error"] = type(exc).__name__
outside = canary.parent / "pwned.txt"
try:
    outside.write_text("PWNED", encoding="utf-8")
    obs["outside_writable"] = True
except Exception as exc:
    obs["outside_writable"] = False
    obs["outside_write_error"] = type(exc).__name__
print(json.dumps(obs))
"""

CANARY_VALUE = "canary-fs-secret-e158f8c8"


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "fs-probe"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    (tool_dir / "inside.txt").write_text("inside-ok", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": "fs-probe",
        "name": "probe filesystem sandbox",
        "command": ["python", "tool.py"],
        "requires": ["raw_text", "canary_path"],
        "provides": [
            "reversed_text",
            "canary_readable",
            "inside_readable",
            "outside_writable",
        ],
        "cases": [
            {
                "input": {"raw_text": value, "canary_path": "unused"},
                "expect": {"reversed_text": value[::-1]},
            }
            for value in ("ab", "cd")
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    entry = {
        "id": "capability.absorbed-fs-probe",
        "name": "probe filesystem sandbox",
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
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": {entry["id"]: entry}}),
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
    observed: dict[str, object] = {"family": "tool-fs-sandbox"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="tool-fs-probe-") as directory:
        base = Path(directory)
        root = _build_fixture_root(base)
        canary_dir = base / "host-secret"
        canary_dir.mkdir()
        canary = canary_dir / "secret.txt"
        canary.write_text(CANARY_VALUE, encoding="utf-8")
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
            base_url = f"http://127.0.0.1:{ready['listening']}"
            status, invoked = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-fs-probe",
                    "input": {"raw_text": "blackhole", "canary_path": str(canary)},
                },
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["invoke_status"] = status
            observed["output"] = output
            if isinstance(invoked, dict) and invoked.get("error"):
                observed["invoke_error"] = invoked.get("error")
            pwned = canary_dir / "pwned.txt"
            canary_unchanged = canary.read_text(encoding="utf-8") == CANARY_VALUE
            observed["canary_unchanged"] = canary_unchanged
            observed["pwned_exists"] = pwned.exists()
            behavior_ok = (
                status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == "elohkcalb"
            )
            inside_ok = isinstance(output, dict) and output.get("inside_readable") is True
            canary_blocked = isinstance(output, dict) and output.get("canary_readable") is False
            write_blocked = (
                isinstance(output, dict)
                and output.get("outside_writable") is False
                and not pwned.exists()
            )
            observed["checks"] = {
                "tool_behavior_correct": behavior_ok,
                "vendored_file_readable": inside_ok,
                "host_canary_unreadable": canary_blocked,
                "host_sibling_unwritable": write_blocked,
                "canary_bytes_unchanged": canary_unchanged,
            }
            return {
                "passed": bool(
                    behavior_ok and inside_ok and canary_blocked and write_blocked and canary_unchanged
                ),
                "observed": observed,
            }
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
