"""Acceptance probe: the live HTTP plane serves Streamable HTTP MCP.

MCP hosts that only speak Streamable HTTP (POST JSON-RPC, Mcp-Session-Id)
could not drive the compounded ledger: the plane spoke REST /invoke and
stdio MCP, not HTTP MCP. This probe starts the invocation plane as a
separate OS process and drives a real loopback MCP session:

1. POST /mcp initialize returns serverInfo and Mcp-Session-Id.
2. tools/list without a session is HTTP 404 (sessions are real).
3. tools/list with the session includes the fixture absorbed tool.
4. tools/call executes that tool for a probe-chosen input and returns the
   transformed output as structuredContent (not a replayed fixture).
5. An unknown tool is JSON-RPC -32602; invalid input is isError.
6. solve_goal over MCP derives and executes a real program.
7. DELETE /mcp ends the session; a later call with that id is 404.
8. REST POST /invoke still returns the same transformed output.

On the stdio-only / REST-only baseline, POST /mcp is an unknown path so
the probe reports passed=false. Both outcomes exit 0 with JSON
``passed`` and nonempty ``observed``.
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

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

PROBE_TEXT = "mcp-http-92080663"
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


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    manifest = {
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
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    entry = {
        "id": "",
        "name": "",
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    proved = dict(entry, last_proved_at="2026-01-01T00:00:00Z", last_proof_exit_code=0)
    unproved = dict(entry, last_proved_at=None, last_proof_exit_code=1)
    capabilities = {
        "capability.absorbed-text-reverser": dict(
            proved, id="capability.absorbed-text-reverser", name="probe text reverser"
        ),
        "capability.absorbed-unproved-tool": dict(
            unproved, id="capability.absorbed-unproved-tool", name="unproved"
        ),
        "repo.import-health": dict(proved, id="repo.import-health", name="import health"),
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


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-http-capability-plane"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="mcp-http-plane-probe-") as directory:
        root = _build_fixture_root(Path(directory))
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
                observed["detail"] = "server never reported a listening port"
                return {"passed": False, "observed": observed}
            base = f"http://127.0.0.1:{ready['listening']}"
            mcp = f"{base}/mcp"

            status, handshake, headers = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "mcp-http-probe", "version": "1"},
                    },
                },
            )
            session = str(headers.get("mcp-session-id") or "")
            result = handshake.get("result") if isinstance(handshake, dict) else None
            observed["initialize_status"] = status
            observed["mcp_session"] = session
            observed["initialize_server"] = (
                result.get("serverInfo") if isinstance(result, dict) else None
            )
            initialize_ok = (
                status == 200
                and bool(session)
                and isinstance(result, dict)
                and "serverInfo" in result
            )

            status, missing, _ = _request(
                "POST", mcp, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )
            observed["missing_session_status"] = status
            observed["missing_session_body"] = missing
            session_required = (
                status == 404
                and isinstance(missing, dict)
                and missing.get("error") == "mcp_session_unknown"
            )

            hdr = {"Mcp-Session-Id": session}
            status, listed, _ = _request(
                "POST",
                mcp,
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
                headers=hdr,
            )
            tools = (
                (listed.get("result") or {}).get("tools") if isinstance(listed, dict) else None
            )
            names = [
                item.get("name") for item in tools if isinstance(item, dict)
            ] if isinstance(tools, list) else []
            observed["list_status"] = status
            observed["tool_names"] = names
            list_ok = status == 200 and "text-reverser" in names and "solve_goal" in names

            status, called, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "text-reverser",
                        "arguments": {"raw_text": PROBE_TEXT},
                    },
                },
                headers=hdr,
            )
            call_result = called.get("result") if isinstance(called, dict) else None
            structured = (
                call_result.get("structuredContent") if isinstance(call_result, dict) else None
            )
            observed["call_status"] = status
            observed["call_structured"] = structured
            call_ok = (
                status == 200
                and isinstance(structured, dict)
                and structured.get("reversed_text") == EXPECTED
                and call_result.get("isError") is False
            )

            status, unknown, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "not-a-real-tool", "arguments": {}},
                },
                headers=hdr,
            )
            unknown_error = unknown.get("error") if isinstance(unknown, dict) else None
            observed["unknown_status"] = status
            observed["unknown_error"] = unknown_error
            unknown_ok = (
                status == 200
                and isinstance(unknown_error, dict)
                and unknown_error.get("code") == -32602
            )

            status, bad_input, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "text-reverser",
                        "arguments": {"wrong_key": PROBE_TEXT},
                    },
                },
                headers=hdr,
            )
            bad_result = bad_input.get("result") if isinstance(bad_input, dict) else None
            observed["bad_input_status"] = status
            observed["bad_input"] = bad_result
            bad_ok = (
                status == 200
                and isinstance(bad_result, dict)
                and bad_result.get("isError") is True
            )

            status, solved, _ = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "solve_goal",
                        "arguments": {
                            "initial_state": {"raw_text": PROBE_TEXT},
                            "goal": ["reversed_text"],
                        },
                    },
                },
                headers=hdr,
            )
            solve_structured = (
                (solved.get("result") or {}).get("structuredContent")
                if isinstance(solved, dict)
                else None
            )
            observed["solve_status"] = status
            observed["solve_outcome"] = (
                solve_structured.get("outcome") if isinstance(solve_structured, dict) else None
            )
            solve_ok = (
                status == 200
                and isinstance(solve_structured, dict)
                and solve_structured.get("solved") is True
                and (solve_structured.get("outcome") or {}).get("reversed_text") == EXPECTED
            )

            status, closed, _ = _request("DELETE", mcp, headers=hdr)
            observed["delete_status"] = status
            observed["delete_body"] = closed
            delete_ok = (
                status == 200 and isinstance(closed, dict) and closed.get("closed") is True
            )
            status, after, _ = _request(
                "POST",
                mcp,
                {"jsonrpc": "2.0", "id": 8, "method": "ping", "params": {}},
                headers=hdr,
            )
            observed["after_delete_status"] = status
            after_ok = status == 404

            status, invoked, _ = _request(
                "POST",
                f"{base}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["rest_invoke_status"] = status
            observed["rest_invoke_output"] = output
            rest_ok = status == 200 and output == {"reversed_text": EXPECTED}

            checks = {
                "initialize": initialize_ok,
                "session_required": session_required,
                "list": list_ok,
                "tools_call": call_ok,
                "unknown_tool": unknown_ok,
                "bad_input": bad_ok,
                "solve_goal": solve_ok,
                "delete_session": delete_ok,
                "session_dead": after_ok,
                "rest_invoke": rest_ok,
            }
            observed["checks"] = checks
            return {"passed": all(checks.values()), "observed": observed}
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
