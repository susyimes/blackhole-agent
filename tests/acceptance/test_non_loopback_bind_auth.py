"""Acceptance probe: non-loopback binds cannot stay an open tool runner.

Filesystem sandbox, env scrubbing, and resource caps already contain
untrusted tools, but ``serve --host 0.0.0.0`` without a bearer token still
listens on every interface. Any client that can reach the port can
POST /invoke. This probe starts the invocation plane as a separate OS
process and requires:

1. ``serve --host 0.0.0.0`` without a token never listens: it prints JSON
   ``error=bind_requires_token`` and exits nonzero.
2. GET /health on a loopback plane reports ``non_loopback_requires_token``.
3. Historical open loopback still works: ``serve --host 127.0.0.1`` without
   a token accepts POST /invoke and returns the declared reverse output.
4. A token-gated wildcard bind still serves: unauthenticated POST /invoke
   is HTTP 401; the correct Bearer token returns the declared reverse output.
5. A follow-up REST POST /invoke of the text-reverser on the open loopback
   plane still returns the declared reverse output.

On the pre-mission plane a wildcard bind without a token listens and
unauthenticated invoke returns 200, so the probe reports passed=false.
Both outcomes exit 0 with JSON ``passed`` and nonempty ``observed``.
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

PROBE_TEXT = "bind-policy-0788e9e0"
EXPECTED = PROBE_TEXT[::-1]
TOKEN = "probe-token-0788e9e0"

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
    _write_tool(root, "text-reverser", _FAST_TOOL, ["raw_text"], ["reversed_text"])
    capabilities = {
        "capability.absorbed-text-reverser": _ledger_entry(
            "capability.absorbed-text-reverser", "probe text reverser"
        ),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    token: str | None = None,
    timeout: int = 30,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return exc.code, None


def _serve_env(src_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.pop("BLACKHOLE_INVOCATION_TOKEN", None)
    return env


def _start_serve(
    root: Path,
    src_root: Path,
    extra_args: list[str],
) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "blackhole_agent.capability_service",
            "serve",
            "--port",
            "0",
            "--root",
            str(root),
            *extra_args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_serve_env(src_root),
    )


def _wait_json_line(process: subprocess.Popen, timeout: float = 60.0) -> dict[str, object]:
    sink: dict[str, object] = {}

    def reader() -> None:
        try:
            line = process.stdout.readline() if process.stdout else ""
            sink["line"] = line[:1000] if isinstance(line, str) else ""
            sink["payload"] = json.loads(line) if line else None
        except Exception as exc:
            sink["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    process.poll()
    sink["returncode"] = process.returncode
    return sink


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _invoke_reverse(base: str, *, token: str | None = None, capability_id: str = "capability.absorbed-text-reverser") -> tuple[int, object]:
    return _request(
        "POST",
        f"{base}/invoke",
        {"capability_id": capability_id, "input": {"raw_text": PROBE_TEXT}},
        token=token,
    )


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "non-loopback-bind-auth"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="bind-policy-probe-", ignore_cleanup_errors=True)
    processes: list[subprocess.Popen] = []
    try:
        root = _build_fixture_root(Path(scratch.name))

        refused = _start_serve(root, src_root, ["--host", "0.0.0.0"])
        processes.append(refused)
        refused_sink = _wait_json_line(refused)
        observed["wildcard_open"] = {
            "returncode": refused_sink.get("returncode"),
            "payload": refused_sink.get("payload"),
            "line": refused_sink.get("line"),
            "error": refused_sink.get("error"),
        }
        payload = refused_sink.get("payload")
        listening = isinstance(payload, dict) and payload.get("listening")
        if isinstance(payload, dict) and payload.get("error") == "bind_requires_token":
            try:
                refused.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            refused_sink["returncode"] = refused.returncode
            observed["wildcard_open"]["returncode"] = refused.returncode
        wildcard_open_ok = (
            isinstance(payload, dict)
            and payload.get("ok") is False
            and payload.get("error") == "bind_requires_token"
            and not listening
            and refused.returncode not in (None, 0)
        )
        if listening:
            try:
                port = int(payload["listening"])
                status, body = _invoke_reverse(f"http://127.0.0.1:{port}")
                observed["wildcard_open"]["invoke_status"] = status
                observed["wildcard_open"]["invoke_ok"] = (
                    body.get("ok") if isinstance(body, dict) else None
                )
            except Exception as exc:
                observed["wildcard_open"]["invoke_error"] = f"{type(exc).__name__}: {exc}"
            wildcard_open_ok = False

        loopback = _start_serve(root, src_root, ["--host", "127.0.0.1"])
        processes.append(loopback)
        loop_sink = _wait_json_line(loopback)
        observed["loopback_ready"] = loop_sink.get("payload")
        loop_payload = loop_sink.get("payload")
        if not isinstance(loop_payload, dict) or not loop_payload.get("listening"):
            err = loopback.stderr.read() if loopback.stderr else ""
            observed["loopback_error"] = loop_sink.get("error")
            observed["loopback_stderr"] = err[-2000:] if isinstance(err, str) else ""
            return {"passed": False, "observed": observed}
        loop_port = int(loop_payload["listening"])
        loop_base = f"http://127.0.0.1:{loop_port}"
        health_status, health = _request("GET", f"{loop_base}/health")
        observed["health_status"] = health_status
        observed["health"] = health
        health_ok = (
            health_status == 200
            and isinstance(health, dict)
            and health.get("ok") is True
            and health.get("non_loopback_requires_token") is True
        )
        loop_status, loop_body = _invoke_reverse(loop_base)
        loop_output = loop_body.get("output") if isinstance(loop_body, dict) else None
        observed["loopback_invoke_status"] = loop_status
        observed["loopback_output"] = loop_output
        loopback_ok = (
            loop_status == 200
            and isinstance(loop_output, dict)
            and loop_output.get("reversed_text") == EXPECTED
        )

        gated = _start_serve(
            root, src_root, ["--host", "0.0.0.0", "--token", TOKEN]
        )
        processes.append(gated)
        gated_sink = _wait_json_line(gated)
        observed["wildcard_token_ready"] = gated_sink.get("payload")
        gated_payload = gated_sink.get("payload")
        if not isinstance(gated_payload, dict) or not gated_payload.get("listening"):
            err = gated.stderr.read() if gated.stderr else ""
            observed["wildcard_token_error"] = gated_sink.get("error")
            observed["wildcard_token_stderr"] = err[-2000:] if isinstance(err, str) else ""
            observed["wildcard_token_line"] = gated_sink.get("line")
            return {"passed": False, "observed": observed}
        gated_port = int(gated_payload["listening"])
        gated_base = f"http://127.0.0.1:{gated_port}"
        unauth_status, unauth_body = _invoke_reverse(gated_base)
        observed["unauth_status"] = unauth_status
        observed["unauth_body"] = unauth_body
        unauth_ok = (
            unauth_status == 401
            and isinstance(unauth_body, dict)
            and unauth_body.get("error") == "authorization_required"
        )
        auth_status, auth_body = _invoke_reverse(gated_base, token=TOKEN)
        auth_output = auth_body.get("output") if isinstance(auth_body, dict) else None
        observed["auth_status"] = auth_status
        observed["auth_output"] = auth_output
        auth_ok = (
            auth_status == 200
            and isinstance(auth_output, dict)
            and auth_output.get("reversed_text") == EXPECTED
        )

        follow_status, follow_body = _invoke_reverse(loop_base)
        follow_output = follow_body.get("output") if isinstance(follow_body, dict) else None
        observed["follow_status"] = follow_status
        observed["follow_output"] = follow_output
        follow_ok = (
            follow_status == 200
            and isinstance(follow_output, dict)
            and follow_output.get("reversed_text") == EXPECTED
        )

        observed["checks"] = {
            "wildcard_open_refused": wildcard_open_ok,
            "health_flag": health_ok,
            "loopback_open_invoke": loopback_ok,
            "wildcard_unauth_401": unauth_ok,
            "wildcard_auth_invoke": auth_ok,
            "follow_up_reverse": follow_ok,
        }
        passed = all(observed["checks"].values())
        return {"passed": passed, "observed": observed}
    except Exception as exc:
        observed["error"] = type(exc).__name__
        observed["detail"] = str(exc)
        return {"passed": False, "observed": observed}
    finally:
        for process in processes:
            _stop(process)
        scratch.cleanup()


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, sort_keys=True, default=str))
    raise SystemExit(0)
