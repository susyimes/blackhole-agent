"""Acceptance probe: vendored tool execution cannot see operator secrets.

The invocation plane executes untrusted third-party tool code as
subprocesses. The plane's own process environment typically carries
operator credentials (API tokens, session material). This probe builds a
minimal ledger with a tool that reports which environment variables it can
observe, starts the plane as a separate OS process with a canary secret in
its environment (the way an operator's shell would), and drives a real
loopback ``POST /invoke``: the tool must answer correctly, must see the
runtime surface it needs (PATH), and must NOT see the canary secret.

Prints JSON with boolean passed and nonempty observed. Exits 0 for both met
and unmet outcomes so the controller can replay the same probe on baseline
and candidate source trees: the baseline plane copies the whole ambient
environment into tool subprocesses, so the canary is visible and the probe
reports passed=false.
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

CANARY_KEY = "BH_PROBE_OPERATOR_SECRET"
CANARY_VALUE = "canary-value-7f3a9c"

_ENV_ECHO_TOOL = (
    "import json, os, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({\n"
    "    'reversed_text': state['raw_text'][::-1],\n"
    "    'observed_secret': os.environ.get('" + CANARY_KEY + "'),\n"
    "    'has_path': bool(os.environ.get('PATH')),\n"
    "}))\n"
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


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "env-echo"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_ENV_ECHO_TOOL, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": "env-echo",
        "name": "probe env echo",
        "command": ["python", "tool.py"],
        "requires": ["raw_text"],
        "provides": ["reversed_text", "observed_secret", "has_path"],
        "cases": [
            {
                "input": {"raw_text": value},
                "expect": {"reversed_text": value[::-1]},
            }
            for value in ("ab", "cd")
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    entry = {
        "id": "capability.absorbed-env-echo",
        "name": "probe env echo",
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
    observed: dict[str, object] = {"family": "tool-env-scrubbing"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:  # baseline source tree has no invocation plane
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="tool-env-probe-") as directory:
        root = _build_fixture_root(Path(directory))
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        env[CANARY_KEY] = CANARY_VALUE
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

            status, invoked = _request(
                "POST",
                f"{base}/invoke",
                {
                    "capability_id": "capability.absorbed-env-echo",
                    "input": {"raw_text": "blackhole"},
                },
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["invoke_status"] = status
            observed["tool_observed_secret"] = (
                "leaked" if isinstance(output, dict) and output.get("observed_secret") else "absent"
            )
            observed["tool_has_path"] = (
                output.get("has_path") if isinstance(output, dict) else None
            )
            observed["tool_behavior"] = (
                output.get("reversed_text") if isinstance(output, dict) else None
            )
            behavior_ok = (
                status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == "elohkcalb"
            )
            runtime_ok = isinstance(output, dict) and output.get("has_path") is True
            secret_ok = isinstance(output, dict) and output.get("observed_secret") in (None, "")
            observed["checks"] = {
                "tool_behavior_correct": behavior_ok,
                "runtime_surface_present": runtime_ok,
                "operator_secret_invisible": secret_ok,
            }
            return {"passed": behavior_ok and runtime_ok and secret_ok, "observed": observed}
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
