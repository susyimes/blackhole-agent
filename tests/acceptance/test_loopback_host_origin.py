"""Acceptance probe: DNS rebinding and CSRF cannot POST /invoke on loopback.

The open loopback invocation plane already refuses non-loopback binds without
a token, but it still honored any Host and Origin. A rebinding page or a
cross-origin browser request could run untrusted tools. This probe starts the
invocation plane as a separate OS process and requires:

1. GET /health reports ``loopback_host_origin``.
2. POST /invoke with Host evil.example returns HTTP 400 error
   ``host_not_allowed`` and does not return reversed output.
3. POST /invoke with Origin http://evil.example returns HTTP 403 error
   ``origin_not_allowed`` and does not return reversed output.
4. POST /invoke with no Origin still returns the declared reverse output.
5. POST /invoke with Origin matching the loopback listen address still
   returns the declared reverse output.
6. A follow-up REST POST /invoke of the text-reverser still returns the
   declared reverse output.

On the pre-mission plane a foreign Host/Origin invoke returns 200, so the
probe reports passed=false. Both outcomes exit 0 with JSON ``passed`` and
nonempty ``observed``.
"""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

PROBE_TEXT = "host-origin-f8be5156"
EXPECTED = PROBE_TEXT[::-1]

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


def _raw_http(
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, object]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port, timeout=timeout)
    extra = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        extra.setdefault("Content-Type", "application/json")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    try:
        conn.request(method, path, body=body, headers=extra)
        response = conn.getresponse()
        raw = response.read()
        try:
            parsed_body = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            parsed_body = raw.decode("utf-8", errors="replace")
        return response.status, parsed_body
    finally:
        conn.close()


def _serve_env(src_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.pop("BLACKHOLE_INVOCATION_TOKEN", None)
    return env


def _start_serve(root: Path, src_root: Path) -> subprocess.Popen:
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
            "--host",
            "127.0.0.1",
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


def _invoke_payload() -> dict:
    return {
        "capability_id": "capability.absorbed-text-reverser",
        "input": {"raw_text": PROBE_TEXT},
    }


def _reversed_ok(status: int, body: object) -> bool:
    output = body.get("output") if isinstance(body, dict) else None
    return (
        status == 200
        and isinstance(output, dict)
        and output.get("reversed_text") == EXPECTED
    )


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "loopback-host-origin"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="host-origin-probe-", ignore_cleanup_errors=True)
    process: subprocess.Popen | None = None
    try:
        root = _build_fixture_root(Path(scratch.name))
        process = _start_serve(root, src_root)
        sink = _wait_json_line(process)
        observed["ready"] = sink.get("payload")
        payload = sink.get("payload")
        if not isinstance(payload, dict) or not payload.get("listening"):
            err = process.stderr.read() if process.stderr else ""
            observed["start_error"] = sink.get("error")
            observed["stderr"] = err[-2000:] if isinstance(err, str) else ""
            observed["line"] = sink.get("line")
            return {"passed": False, "observed": observed}
        port = int(payload["listening"])
        base = f"http://127.0.0.1:{port}"

        health_status, health = _raw_http("GET", f"{base}/health")
        observed["health_status"] = health_status
        observed["health"] = health
        health_ok = (
            health_status == 200
            and isinstance(health, dict)
            and health.get("ok") is True
            and health.get("loopback_host_origin") is True
        )

        host_status, host_body = _raw_http(
            "POST",
            f"{base}/invoke",
            _invoke_payload(),
            headers={"Host": "evil.example"},
        )
        observed["foreign_host_status"] = host_status
        observed["foreign_host_body"] = host_body
        host_ok = (
            host_status == 400
            and isinstance(host_body, dict)
            and host_body.get("ok") is False
            and host_body.get("error") == "host_not_allowed"
            and EXPECTED not in json.dumps(host_body)
        )

        origin_status, origin_body = _raw_http(
            "POST",
            f"{base}/invoke",
            _invoke_payload(),
            headers={"Origin": "http://evil.example"},
        )
        observed["foreign_origin_status"] = origin_status
        observed["foreign_origin_body"] = origin_body
        origin_ok = (
            origin_status == 403
            and isinstance(origin_body, dict)
            and origin_body.get("ok") is False
            and origin_body.get("error") == "origin_not_allowed"
            and EXPECTED not in json.dumps(origin_body)
        )

        open_status, open_body = _raw_http("POST", f"{base}/invoke", _invoke_payload())
        observed["open_status"] = open_status
        observed["open_output"] = open_body.get("output") if isinstance(open_body, dict) else open_body
        open_ok = _reversed_ok(open_status, open_body)

        same_status, same_body = _raw_http(
            "POST",
            f"{base}/invoke",
            _invoke_payload(),
            headers={"Origin": f"http://127.0.0.1:{port}"},
        )
        observed["same_origin_status"] = same_status
        observed["same_origin_output"] = (
            same_body.get("output") if isinstance(same_body, dict) else same_body
        )
        same_ok = _reversed_ok(same_status, same_body)

        follow_status, follow_body = _raw_http("POST", f"{base}/invoke", _invoke_payload())
        observed["follow_status"] = follow_status
        observed["follow_output"] = (
            follow_body.get("output") if isinstance(follow_body, dict) else follow_body
        )
        follow_ok = _reversed_ok(follow_status, follow_body)

        observed["checks"] = {
            "health_flag": health_ok,
            "foreign_host_refused": host_ok,
            "foreign_origin_refused": origin_ok,
            "open_invoke": open_ok,
            "same_origin_invoke": same_ok,
            "follow_up_reverse": follow_ok,
        }
        return {"passed": all(observed["checks"].values()), "observed": observed}
    except Exception as exc:
        observed["error"] = type(exc).__name__
        observed["detail"] = str(exc)
        return {"passed": False, "observed": observed}
    finally:
        if process is not None:
            _stop(process)
        scratch.cleanup()


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, sort_keys=True, default=str))
    raise SystemExit(0)
