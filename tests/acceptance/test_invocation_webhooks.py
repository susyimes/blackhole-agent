"""Outcome probe: signed inbound webhooks start a governed live-plane invoke.

POST /invoke currently occupies the HTTP client for the whole tool runtime,
so CI that can only deliver a signed callback cannot start a governed tool.
This probe starts the invocation plane as a separate OS process and requires:

1. GET /health reports webhook_hooks true when started with --webhook-secret
   and --webhook-hook shout=capability.absorbed-webhook-shout.
2. POST /hooks/shout with a valid X-Hub-Signature-256 returns HTTP 202 with a
   nonempty run_id in under one second while the mapped tool still sleeps.
3. GET /hooks/{run_id} eventually returns HTTP 200 with status completed and
   the declared shout_output.
4. A POST with a missing or wrong signature is HTTP 401 and writes no run
   files.
5. POST /hooks/unknown with a valid signature is HTTP 404.
6. A plane started without --webhook-secret reports webhook_hooks false and
   POST /hooks/shout is HTTP 404.
7. POST /invoke of the sibling text-reverser still returns the declared reverse.

On the pre-mission plane --webhook-secret is unknown or GET /health omits
webhook_hooks, so the probe reports passed=false. Both outcomes exit 0 with
JSON passed and nonempty observed.
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

PROBE_TEXT = "webhook-hooks-a2f49846"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
SECRET = "webhook-secret-a2f49846"
SHOUT_ID = "capability.absorbed-webhook-shout"
REVERSE_ID = "capability.absorbed-text-reverser"
SHOUT_INPUT = {"text": "blackhole unbound"}
SHOUT_OUTPUT = "BLACKHOLE UNBOUND!"
SIGNATURE_HEADER = "X-Hub-Signature-256"

_SHOUT_TOOL = (
    "import json, sys, time\n"
    "time.sleep(1.2)\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'shout_output': state['text'].upper() + '!'}))\n"
)
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
                        "expect": {provides[0]: "x"},
                    }
                    for _ in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    _write_tool(root, "webhook-shout", _SHOUT_TOOL, ["text"], ["shout_output"])
    _write_tool(root, "text-reverser", _REVERSE_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        SHOUT_ID: _ledger_entry(SHOUT_ID, "probe webhook shout"),
        REVERSE_ID: _ledger_entry(REVERSE_ID, "probe text reverser"),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 40,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    extra = dict(headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if "X-Hub-Signature-256" not in extra and SIGNATURE_HEADER not in extra:
            pass
    for key, value in extra.items():
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
    return sorted(path.name for path in runs.glob("*.json"))


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "invocation-webhooks"}
    try:
        import blackhole_agent.capability_service as service
        import blackhole_agent.invocation_webhooks as hooks
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "accept_webhook_post") or not hasattr(hooks, "WebhookPlane"):
        observed["detail"] = "baseline plane has no inbound webhook HTTP surface"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    health_ok = post_ok = complete_ok = auth_ok = unknown_ok = reverse_ok = closed_ok = False
    payload = {"input": SHOUT_INPUT}
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    scratch = tempfile.TemporaryDirectory(prefix="invocation-webhooks-probe-", ignore_cleanup_errors=True)
    try:
        root = _build_fixture_root(Path(scratch.name))
        extra = [
            "--webhook-secret",
            SECRET,
            "--webhook-hook",
            f"shout={SHOUT_ID}",
        ]
        process, sink = _start_plane(src_root, root, extra)
        try:
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = _stop_plane(process)
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            url = f"http://127.0.0.1:{ready['listening']}"
            observed["ready_webhook_hooks"] = ready.get("webhook_hooks")

            health_status, health = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("webhook_hooks") is True
            )

            payload = {"input": SHOUT_INPUT}
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            started = time.perf_counter()
            post_status, accepted = _request(
                "POST",
                f"{url}/hooks/shout",
                payload,
                headers={SIGNATURE_HEADER: _sign(body)},
                timeout=5,
            )
            post_elapsed = time.perf_counter() - started
            observed["post_status"] = post_status
            observed["post_elapsed_s"] = round(post_elapsed, 3)
            observed["accepted"] = accepted if isinstance(accepted, dict) else None
            run_id = accepted.get("run_id") if isinstance(accepted, dict) else None
            post_ok = (
                post_status == 202
                and isinstance(accepted, dict)
                and accepted.get("ok") is True
                and accepted.get("status") == "accepted"
                and isinstance(run_id, str)
                and bool(run_id)
                and post_elapsed < 1.0
            )

            completed = None
            get_status = 0
            deadline = time.time() + 20
            while time.time() < deadline:
                get_status, completed = _request("GET", f"{url}/hooks/{run_id}")
                if (
                    get_status == 200
                    and isinstance(completed, dict)
                    and completed.get("status") in {"completed", "failed"}
                ):
                    break
                time.sleep(0.1)
            observed["get_status"] = get_status
            observed["completed"] = completed if isinstance(completed, dict) else None
            complete_ok = (
                get_status == 200
                and isinstance(completed, dict)
                and completed.get("status") == "completed"
                and completed.get("output", {}).get("shout_output") == SHOUT_OUTPUT
            )

            before_runs = set(_run_files(root))
            missing_status, missing = _request(
                "POST",
                f"{url}/hooks/shout",
                payload,
                timeout=5,
            )
            observed["missing_status"] = missing_status
            observed["missing"] = missing if isinstance(missing, dict) else None
            wrong_status, wrong = _request(
                "POST",
                f"{url}/hooks/shout",
                payload,
                headers={SIGNATURE_HEADER: "sha256=00"},
                timeout=5,
            )
            observed["wrong_status"] = wrong_status
            observed["wrong"] = wrong if isinstance(wrong, dict) else None
            after_auth_runs = set(_run_files(root))
            auth_ok = (
                missing_status == 401
                and isinstance(missing, dict)
                and missing.get("error") == "webhook_signature_required"
                and wrong_status == 401
                and isinstance(wrong, dict)
                and wrong.get("error") == "webhook_signature_invalid"
                and after_auth_runs == before_runs
            )

            unknown_status, unknown = _request(
                "POST",
                f"{url}/hooks/unknown",
                payload,
                headers={SIGNATURE_HEADER: _sign(body)},
                timeout=5,
            )
            observed["unknown_status"] = unknown_status
            observed["unknown"] = unknown if isinstance(unknown, dict) else None
            unknown_ok = (
                unknown_status == 404
                and isinstance(unknown, dict)
                and unknown.get("error") == "hook_unknown"
            )

            reverse_status, reversed_body = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
            )
            observed["reverse_status"] = reverse_status
            observed["reversed"] = reversed_body if isinstance(reversed_body, dict) else None
            reverse_ok = (
                reverse_status == 200
                and isinstance(reversed_body, dict)
                and reversed_body.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-4000:]

        closed_root = Path(scratch.name) / "closed"
        _write_tool(closed_root, "text-reverser", _REVERSE_TOOL, ["raw_text"], ["reversed_text"])
        (closed_root / "capabilities" / "ledger.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "",
                    "capabilities": {REVERSE_ID: _ledger_entry(REVERSE_ID, "probe text reverser")},
                }
            ),
            encoding="utf-8",
        )
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
            closed_health_status, closed_health = _request("GET", f"{closed_url}/health")
            observed["closed_health"] = closed_health if isinstance(closed_health, dict) else None
            closed_health_ok = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("webhook_hooks") is False
            )
            closed_post_status, closed_post = _request(
                "POST",
                f"{closed_url}/hooks/shout",
                payload,
                headers={SIGNATURE_HEADER: _sign(body)},
                timeout=5,
            )
            observed["closed_post_status"] = closed_post_status
            observed["closed_post"] = closed_post if isinstance(closed_post, dict) else None
            closed_ok = (
                closed_health_ok
                and closed_post_status == 404
                and isinstance(closed_post, dict)
                and closed_post.get("error") == "webhook_disabled"
            )
        finally:
            observed["closed_stderr"] = (_stop_plane(closed) or "")[-2000:]
    finally:
        scratch.cleanup()

    passed = bool(
        health_ok
        and post_ok
        and complete_ok
        and auth_ok
        and unknown_ok
        and reverse_ok
        and closed_ok
    )
    observed["checks"] = {
        "health_ok": health_ok,
        "post_ok": post_ok,
        "complete_ok": complete_ok,
        "auth_ok": auth_ok,
        "unknown_ok": unknown_ok,
        "reverse_ok": reverse_ok,
        "closed_ok": closed_ok,
    }
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
