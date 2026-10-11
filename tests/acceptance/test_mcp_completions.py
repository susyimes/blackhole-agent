"""Acceptance probe: MCP completion/complete resolves live catalog ids.

Streamable HTTP and stdio MCP hosts that send completion/complete currently
get method-not-found, initialize never advertises completions, and operators
typing the prepare-prompt or URI-template capability_id argument cannot
resolve live catalog ids from a prefix. This probe starts the invocation
plane as a separate OS process and requires:

1. GET /health reports mcp_completions.
2. POST /mcp initialize advertises completions and returns Mcp-Session-Id.
3. completion/complete for prepare_capability_call capability_id prefix
   "text" returns capability.absorbed-text-reverser without executing a tool.
4. completion/complete for the capability URI template with the same prefix
   returns that id.
5. An unknown prompt is JSON-RPC -32602.
6. A subsequent tools/call of text-reverser still returns the declared reverse
   output for a probe-chosen input.

On the pre-mission plane initialize omits completions and completion/complete
is method-not-found, so the probe reports passed=false. Both outcomes exit 0
with JSON passed and nonempty observed.

The controller copies this file to a scratch path and injects implementation
src via ``python -I`` + sys.path. Serve children must load that injected
tree: import capability_service from sys.path, then replace PYTHONPATH with
that src root only. Joining ambient PYTHONPATH or deriving src from
``__file__`` leaks the candidate tree into the baseline run.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)
PROBE_TEXT = "mcp-complete-87791c92"
EXPECTED = PROBE_TEXT[::-1]
TARGET = "capability.absorbed-text-reverser"
TEMPLATE = "blackhole://capabilities/{capability_id}"


def _request(method: str, url: str, payload: dict | None = None, headers: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            captured = {k.lower(): v for k, v in response.headers.items()}
            return response.status, parsed, captured
    except HTTPError as exc:
        captured = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        try:
            return exc.code, json.loads(exc.read().decode("utf-8")), captured
        except Exception:
            return exc.code, None, captured
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, {}


def _build_root(base: Path) -> Path:
    root = base / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps({
            "schema_version": 1,
            "slug": "text-reverser",
            "name": "probe text reverser",
            "command": ["python", "tool.py"],
            "requires": ["raw_text"],
            "provides": ["reversed_text"],
            "cases": [
                {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
                {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
            ],
        }),
        encoding="utf-8",
    )
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({
            "schema_version": 1,
            "updated_at": "",
            "capabilities": {
                TARGET: {
                    "id": TARGET,
                    "name": "probe text reverser",
                    "kind": "python",
                    "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
                    "proof_command": "uv run python -c \"pass\"",
                    "last_proved_at": "2026-01-01T00:00:00Z",
                    "last_proof_exit_code": 0,
                }
            },
        }),
        encoding="utf-8",
    )
    return root


def _completion_values(payload: object) -> object:
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    completion = result.get("completion")
    if not isinstance(completion, dict):
        return None
    return completion.get("values")


def _error_code(payload: object) -> object:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    return error.get("code")


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-completions"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    observed["implementation_src"] = str(src_root)
    tmp = tempfile.mkdtemp(prefix="bh-mcp-complete-")
    process: subprocess.Popen[str] | None = None
    try:
        root = _build_root(Path(tmp))
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
        sink: dict[str, object] = {}

        def _read_ready() -> None:
            if process.stdout is None:
                sink["ready"] = None
                return
            line = process.stdout.readline()
            try:
                sink["ready"] = json.loads(line) if line.strip().startswith("{") else line
            except json.JSONDecodeError:
                sink["ready"] = line

        reader = threading.Thread(target=_read_ready, daemon=True)
        reader.start()
        reader.join(timeout=60)
        ready = sink.get("ready")
        observed["ready"] = ready
        if not isinstance(ready, dict) or not ready.get("listening"):
            err = ""
            if process.stderr is not None:
                try:
                    err = process.stderr.read()
                except Exception:
                    err = ""
            observed["detail"] = "server never reported a listening port"
            observed["stderr"] = err[-2000:] if isinstance(err, str) else ""
            return {"passed": False, "observed": observed}

        port = int(ready["listening"])
        base = f"http://127.0.0.1:{port}"
        health_status, health, _ = _request("GET", f"{base}/health")
        mcp = f"{base}/mcp"
        init_status, handshake, headers = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "completion-probe", "version": "1"},
                },
            },
        )
        session = str(headers.get("mcp-session-id") or "")
        result = handshake.get("result") if isinstance(handshake, dict) else None
        advertised = result.get("capabilities") if isinstance(result, dict) else None
        if not isinstance(advertised, dict):
            advertised = {}
        mcp_hdr = {"Mcp-Session-Id": session} if session else None
        prompt_status, prompt, _ = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "completion/complete",
                "params": {
                    "ref": {"type": "ref/prompt", "name": "prepare_capability_call"},
                    "argument": {"name": "capability_id", "value": "text"},
                },
            },
            headers=mcp_hdr,
        )
        prompt_values = _completion_values(prompt)
        resource_status, resource, _ = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "completion/complete",
                "params": {
                    "ref": {"type": "ref/resource", "uri": TEMPLATE},
                    "argument": {"name": "capability_id", "value": "text"},
                },
            },
            headers=mcp_hdr,
        )
        resource_values = _completion_values(resource)
        bad_status, bad, _ = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "completion/complete",
                "params": {
                    "ref": {"type": "ref/prompt", "name": "missing"},
                    "argument": {"name": "capability_id", "value": "text"},
                },
            },
            headers=mcp_hdr,
        )
        bad_code = _error_code(bad)
        call_status, called, _ = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "text-reverser", "arguments": {"raw_text": PROBE_TEXT}},
            },
            headers=mcp_hdr,
        )
        structured = None
        if isinstance(called, dict) and isinstance(called.get("result"), dict):
            structured = called["result"].get("structuredContent")
        checks = {
            "health_ok": health_status == 200 and isinstance(health, dict) and health.get("mcp_completions") is True,
            "initialize_ok": init_status == 200 and bool(session),
            "completions_advertised": advertised.get("completions") == {},
            "prompt_complete": prompt_status == 200 and prompt_values == [TARGET],
            "resource_complete": resource_status == 200 and resource_values == [TARGET],
            "unknown_prompt": bad_status == 200 and bad_code == -32602,
            "tools_call_still_executes": (
                call_status == 200
                and isinstance(structured, dict)
                and structured.get("reversed_text") == EXPECTED
            ),
        }
        observed.update(
            {
                "health": health,
                "init_status": init_status,
                "completions_advertised": checks["completions_advertised"],
                "session": bool(session),
                "prompt_values": prompt_values,
                "resource_values": resource_values,
                "unknown_prompt_code": bad_code,
                "call_output": structured,
                "checks": checks,
            }
        )
        return {"passed": all(checks.values()), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except Exception:
                process.kill()
                try:
                    process.wait(timeout=5)
                except Exception:
                    pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as exc:
        verdict = {
            "passed": False,
            "observed": {
                "error": type(exc).__name__,
                "detail": str(exc),
                "family": "mcp-completions",
            },
        }
    print(json.dumps(verdict, sort_keys=True))
    raise SystemExit(0)
