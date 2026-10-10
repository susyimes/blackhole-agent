"""Acceptance probe: token-gated HTTP invocation never runs tools unauthenticated.

The live plane executes absorbed tools for any client that can reach the
port unless an operator token is configured. This probe starts the
invocation plane as a separate OS process with BLACKHOLE_INVOCATION_TOKEN
set, then drives real loopback HTTP:

1. POST /invoke without Authorization returns 401 and a fixture tool does
   not write its vendored ran-canary.
2. POST /invoke with a wrong Bearer token returns 403 and still does not
   write the canary.
3. POST /invoke with the correct token returns 200 and the declared reverse
   output; a follow-up authenticated invoke of a fast text-reverser still
   works.
4. GET /health without a token returns 200.
5. GET /console JavaScript sends Authorization on invoke/solve fetches.

On the pre-mission plane an unauthenticated POST /invoke still executes
the tool, so the probe reports passed=false. Exits 0 for both met and
unmet outcomes.
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

TOKEN = "probe-token-184b6be4"
WRONG_TOKEN = "wrong-token-184b6be4"

_PROBE = r"""
import json, pathlib, sys
state = json.load(sys.stdin)
pathlib.Path("ran.txt").write_text("RAN", encoding="utf-8")
print(json.dumps({"reversed_text": state["raw_text"][::-1], "ran": True}))
"""

_REVERSER = r"""
import json, sys
state = json.load(sys.stdin)
print(json.dumps({"reversed_text": state["raw_text"][::-1]}))
"""


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    token: str | None = None,
) -> tuple[int, object, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            body = response.read().decode("utf-8")
            parsed: object
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = body
            return response.status, parsed, headers
    except HTTPError as exc:
        headers = {key.lower(): value for key, value in exc.headers.items()} if exc.headers else {}
        try:
            return exc.code, json.loads(exc.read().decode("utf-8")), headers
        except Exception:
            return exc.code, None, headers


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


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> Path:
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
                    {"input": {key: "x" for key in requires}, "expect": {provides[0]: "x"}}
                    for _ in ("ab", "cd")
                ],
            }
        ),
        encoding="utf-8",
    )
    return tool_dir


def _build_fixture_root(base: Path) -> tuple[Path, Path]:
    root = base / "repo"
    probe_dir = _write_tool(
        root,
        "auth-probe",
        _PROBE,
        ["raw_text"],
        ["reversed_text", "ran"],
    )
    _write_tool(root, "text-reverser", _REVERSER, ["raw_text"], ["reversed_text"])
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    "capability.absorbed-auth-probe": _ledger_entry(
                        "capability.absorbed-auth-probe", "probe invocation auth"
                    ),
                    "capability.absorbed-text-reverser": _ledger_entry(
                        "capability.absorbed-text-reverser", "probe text reverser"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    return root, probe_dir / "ran.txt"


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "invocation-auth"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="invocation-auth-probe-") as directory:
        base = Path(directory)
        root, canary = _build_fixture_root(base)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(src_root)
        env["PYTHONIOENCODING"] = "utf-8"
        env["BLACKHOLE_INVOCATION_TOKEN"] = TOKEN
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
            payload = {
                "capability_id": "capability.absorbed-auth-probe",
                "input": {"raw_text": "blackhole"},
            }

            missing_status, missing_body, missing_headers = _request(
                "POST", f"{base_url}/invoke", payload
            )
            observed["missing_status"] = missing_status
            observed["missing_body"] = missing_body
            observed["missing_www_authenticate"] = missing_headers.get("www-authenticate", "")
            observed["canary_after_missing"] = canary.is_file()

            wrong_status, wrong_body, _wrong_headers = _request(
                "POST", f"{base_url}/invoke", payload, token=WRONG_TOKEN
            )
            observed["wrong_status"] = wrong_status
            observed["wrong_body"] = wrong_body
            observed["canary_after_wrong"] = canary.is_file()

            ok_status, ok_body, _ok_headers = _request(
                "POST", f"{base_url}/invoke", payload, token=TOKEN
            )
            output = ok_body.get("output") if isinstance(ok_body, dict) else None
            observed["ok_status"] = ok_status
            observed["ok_output"] = output
            observed["canary_after_ok"] = canary.is_file()
            if canary.is_file():
                observed["canary_bytes"] = canary.read_text(encoding="utf-8")

            follow_status, follow_body, _follow_headers = _request(
                "POST",
                f"{base_url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": "blackhole"},
                },
                token=TOKEN,
            )
            follow_output = follow_body.get("output") if isinstance(follow_body, dict) else None
            observed["follow_status"] = follow_status
            observed["follow_output"] = follow_output

            health_status, health_body, _health_headers = _request("GET", f"{base_url}/health")
            observed["health_status"] = health_status
            observed["health_body"] = health_body

            catalog_status, catalog_body, _catalog_headers = _request(
                "GET", f"{base_url}/capabilities"
            )
            observed["catalog_status"] = catalog_status
            observed["catalog_body"] = catalog_body

            console_status, console_body, console_headers = _request("GET", f"{base_url}/console")
            console_text = console_body if isinstance(console_body, str) else json.dumps(console_body)
            observed["console_status"] = console_status
            observed["console_content_type"] = console_headers.get("content-type", "")
            observed["console_has_authorization"] = "Authorization" in console_text
            observed["console_has_bearer"] = "Bearer " in console_text
            observed["console_has_token_field"] = 'id="operator-token"' in console_text

            missing_ok = (
                missing_status == 401
                and isinstance(missing_body, dict)
                and missing_body.get("error") == "authorization_required"
                and "Bearer" in observed["missing_www_authenticate"]
                and observed["canary_after_missing"] is False
            )
            wrong_ok = (
                wrong_status == 403
                and isinstance(wrong_body, dict)
                and wrong_body.get("error") == "authorization_rejected"
                and observed["canary_after_wrong"] is False
            )
            invoke_ok = (
                ok_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == "elohkcalb"
                and observed["canary_after_ok"] is True
            )
            follow_ok = (
                follow_status == 200
                and isinstance(follow_output, dict)
                and follow_output.get("reversed_text") == "elohkcalb"
            )
            health_ok = health_status == 200 and isinstance(health_body, dict) and health_body.get("ok") is True
            catalog_protected = (
                catalog_status == 401
                and isinstance(catalog_body, dict)
                and catalog_body.get("error") == "authorization_required"
            )
            console_ok = (
                console_status == 200
                and observed["console_has_authorization"] is True
                and observed["console_has_bearer"] is True
                and observed["console_has_token_field"] is True
            )
            auth_required_flag = isinstance(ready, dict) and ready.get("auth_required") is True
            observed["checks"] = {
                "missing_token_rejected": missing_ok,
                "wrong_token_rejected": wrong_ok,
                "correct_token_runs_tool": invoke_ok,
                "followup_reverser_ok": follow_ok,
                "health_public": health_ok,
                "catalog_protected": catalog_protected,
                "console_sends_authorization": console_ok,
                "ready_auth_required": auth_required_flag,
            }
            return {
                "passed": bool(
                    missing_ok
                    and wrong_ok
                    and invoke_ok
                    and follow_ok
                    and health_ok
                    and catalog_protected
                    and console_ok
                    and auth_required_flag
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
