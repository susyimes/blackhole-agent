"""Outcome probe: a captured signed webhook body cannot start the tool again.

A live capability_service process with webhook opt-in must:

1. Report webhook_replay_guard true on GET /health.
2. Accept one signed POST /hooks/shout with HTTP 202 and return the tool output.
3. Refuse that identical signed body with HTTP 409 webhook_replayed and write
   no second run file.
4. Still refuse that body after a process restart that reuses the same root.
5. Accept a different signed body with HTTP 202 and return its output.
6. A plane without the webhook secret reports webhook_replay_guard false and
   POST /hooks/shout is HTTP 404.

On the previous milestone the same signed body is accepted twice, so this
probe reports passed=false. Both outcomes exit 0 with JSON passed and a
nonempty observed object.
"""

from __future__ import annotations

import hashlib
import hmac
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

SECRET = "webhook-replay-guard-secret"
SHOUT_ID = "capability.absorbed-webhook-shout"
SIGNATURE_HEADER = "X-Hub-Signature-256"

_ECHO_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'echo_output': state['text']}))\n"
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
    tool_dir = root / "capabilities" / "absorbed" / "webhook-shout"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(_ECHO_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "webhook-shout",
                "name": "probe webhook shout",
                "command": ["python", "tool.py"],
                "requires": ["text"],
                "provides": ["echo_output"],
                "cases": [
                    {"input": {"text": "x"}, "expect": {"echo_output": "x"}},
                    {"input": {"text": "y"}, "expect": {"echo_output": "y"}},
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
                "capabilities": {SHOUT_ID: _ledger_entry(SHOUT_ID, "probe webhook shout")},
            }
        ),
        encoding="utf-8",
    )


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _encode(text: str) -> bytes:
    return json.dumps({"input": {"text": text}}, separators=(",", ":")).encode("utf-8")


def _request(
    method: str,
    url: str,
    data: bytes | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> tuple[int, object]:
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
    for key, value in dict(headers or {}).items():
        req.add_header(key, value)
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
        sink["ready_line"] = line[:500] if isinstance(line, str) else ""
        sink["ready"] = json.loads(line)
    except Exception as exc:
        sink["ready"] = None
        sink["ready_error"] = f"{type(exc).__name__}: {exc}"


def _start_plane(src_root: Path, root: Path, extra_args: list[str] | None = None) -> tuple[subprocess.Popen, dict]:
    env = dict(os.environ)
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
    reader.join(timeout=60)
    return process, sink


def _stop_plane(process: subprocess.Popen) -> str:
    process.kill()
    try:
        _out, err = process.communicate(timeout=10)
    except Exception:
        err = ""
    return err if isinstance(err, str) else ""


def _run_files(root: Path) -> list[str]:
    runs = root / ".blackhole-agent" / "webhook-runs"
    if not runs.is_dir():
        return []
    return sorted(path.name for path in runs.glob("*.json") if not path.name.endswith(".tmp"))


def _wait_output(url: str, run_id: str) -> tuple[int, object]:
    status = 0
    body: object = {}
    deadline = time.time() + 20
    while time.time() < deadline:
        status, body = _request("GET", f"{url}/hooks/{run_id}")
        if (
            status == 200
            and isinstance(body, dict)
            and body.get("status") in {"completed", "failed"}
        ):
            return status, body
        time.sleep(0.05)
    return status, body


def _listening_url(sink: dict) -> str:
    ready = sink.get("ready")
    if not isinstance(ready, dict) or not ready.get("listening"):
        return ""
    return f"http://127.0.0.1:{ready['listening']}"


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "webhook-replay-guard"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    extra = ["--webhook-secret", SECRET, "--webhook-hook", f"shout={SHOUT_ID}"]
    first_body = _encode("replay-once")
    second_body = _encode("replay-twice")
    first_signature = _sign(first_body)
    scratch = tempfile.TemporaryDirectory(prefix="webhook-replay-guard-", ignore_cleanup_errors=True)
    try:
        root = Path(scratch.name) / "repo"
        root.mkdir()
        _write_tool(root)
        process, sink = _start_plane(src_root, root, extra)
        try:
            url = _listening_url(sink)
            observed["ready"] = sink.get("ready")
            if not url:
                observed["detail"] = "server never reported a listening port"
                return {"passed": False, "observed": observed}
            health_status, health = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["webhook_replay_guard"] = health.get("webhook_replay_guard") if isinstance(health, dict) else None
            post_status, accepted = _request(
                "POST",
                f"{url}/hooks/shout",
                first_body,
                headers={SIGNATURE_HEADER: first_signature},
                timeout=5,
            )
            observed["post_status"] = post_status
            run_id = accepted.get("run_id") if isinstance(accepted, dict) else None
            get_status, completed = _wait_output(url, str(run_id or ""))
            observed["completed_status"] = get_status
            observed["completed_output"] = (
                completed.get("output") if isinstance(completed, dict) else None
            )
            runs_after_first = _run_files(root)
            replay_status, replay = _request(
                "POST",
                f"{url}/hooks/shout",
                first_body,
                headers={SIGNATURE_HEADER: first_signature},
                timeout=5,
            )
            observed["replay_status"] = replay_status
            observed["replay_error"] = replay.get("error") if isinstance(replay, dict) else None
            runs_after_replay = _run_files(root)
            observed["run_count_after_replay"] = len(runs_after_replay)
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-1500:]

        restarted, restart_sink = _start_plane(src_root, root, extra)
        try:
            restart_url = _listening_url(restart_sink)
            observed["restart_ready"] = restart_sink.get("ready")
            if not restart_url:
                observed["detail"] = "restarted server never reported a listening port"
                return {"passed": False, "observed": observed}
            persisted_status, persisted = _request(
                "POST",
                f"{restart_url}/hooks/shout",
                first_body,
                headers={SIGNATURE_HEADER: first_signature},
                timeout=5,
            )
            observed["persisted_replay_status"] = persisted_status
            observed["persisted_replay_error"] = persisted.get("error") if isinstance(persisted, dict) else None
            fresh_status, fresh = _request(
                "POST",
                f"{restart_url}/hooks/shout",
                second_body,
                headers={SIGNATURE_HEADER: _sign(second_body)},
                timeout=5,
            )
            fresh_id = fresh.get("run_id") if isinstance(fresh, dict) else None
            fresh_get, fresh_body = _wait_output(restart_url, str(fresh_id or ""))
            observed["fresh_status"] = fresh_status
            observed["fresh_output"] = fresh_body.get("output") if isinstance(fresh_body, dict) else None
            observed["run_count_after_fresh"] = len(_run_files(root))
        finally:
            observed["restart_stderr"] = (_stop_plane(restarted) or "")[-1500:]

        closed_root = Path(scratch.name) / "closed"
        closed_root.mkdir()
        _write_tool(closed_root)
        closed, closed_sink = _start_plane(src_root, closed_root)
        try:
            closed_url = _listening_url(closed_sink)
            if not closed_url:
                observed["detail"] = "closed plane never reported a listening port"
                return {"passed": False, "observed": observed}
            closed_health_status, closed_health = _request("GET", f"{closed_url}/health")
            closed_post_status, closed_post = _request(
                "POST",
                f"{closed_url}/hooks/shout",
                first_body,
                headers={SIGNATURE_HEADER: first_signature},
                timeout=5,
            )
            observed["closed_health_status"] = closed_health_status
            observed["closed_webhook_replay_guard"] = (
                closed_health.get("webhook_replay_guard") if isinstance(closed_health, dict) else None
            )
            observed["closed_post_status"] = closed_post_status
            observed["closed_post_error"] = closed_post.get("error") if isinstance(closed_post, dict) else None
        finally:
            _stop_plane(closed)

        first_output = observed.get("completed_output")
        fresh_output = observed.get("fresh_output")
        passed = bool(
            observed.get("webhook_replay_guard") is True
            and observed.get("post_status") == 202
            and isinstance(first_output, dict)
            and first_output.get("echo_output") == "replay-once"
            and observed.get("replay_status") == 409
            and observed.get("replay_error") == "webhook_replayed"
            and observed.get("run_count_after_replay") == 1
            and runs_after_replay == runs_after_first
            and observed.get("persisted_replay_status") == 409
            and observed.get("persisted_replay_error") == "webhook_replayed"
            and observed.get("fresh_status") == 202
            and isinstance(fresh_output, dict)
            and fresh_output.get("echo_output") == "replay-twice"
            and observed.get("run_count_after_fresh") == 2
            and observed.get("closed_webhook_replay_guard") is False
            and observed.get("closed_post_status") == 404
            and observed.get("closed_post_error") == "webhook_disabled"
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
            "observed": {"family": "webhook-replay-guard", "error": f"{type(exc).__name__}: {exc}"},
        }
    print(json.dumps(report, sort_keys=True))
