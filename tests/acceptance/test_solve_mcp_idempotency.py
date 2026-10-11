"""Acceptance probe: POST /solve and MCP tools/call honor retry identity.

POST /invoke already reserves Idempotency-Key before execution. POST /solve
and MCP tools/call currently ignore retry identity, so a host that repeats a
dropped solve or tools/call runs the untrusted tool again. This probe starts
the live invocation plane as a separate OS process and drives real loopback
HTTP:

1. GET /health reports solve_idempotency and mcp_call_idempotency.
2. POST /solve with Idempotency-Key runs a fixture append tool once; a
   retry with the same key returns Idempotency-Replayed: true and the
   canary still has one line.
3. A conflicting solve payload with that key is HTTP 409; the canary is
   unchanged.
4. GET /invocations/{key} returns the completed solve response.
5. POST /mcp initialize advertises experimental.idempotencyKey.
6. MCP tools/call of the append tool with _meta.idempotencyKey writes once;
   a retry returns _meta.idempotencyReplayed and does not append again.
7. MCP tools/call of solve_goal with _meta.idempotencyKey writes once across
   a retry.
8. A follow-up REST POST /invoke of the text-reverser still returns the
   declared reverse output.

On the pre-mission plane POST /solve with Idempotency-Key is HTTP 400, two
solves append twice, and MCP tools/call ignores _meta.idempotencyKey. Both
outcomes exit 0 with JSON passed and nonempty observed.
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

REVERSE_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)
APPEND_TOOL = (
    "import json, os, sys\n"
    "from pathlib import Path\n"
    "s = json.load(sys.stdin)\n"
    "path = Path(s['events'])\n"
    "path.parent.mkdir(parents=True, exist_ok=True)\n"
    "with path.open('a', encoding='utf-8') as handle:\n"
    "    handle.write(s['label'] + '\\n')\n"
    "    handle.flush()\n"
    "    os.fsync(handle.fileno())\n"
    "print(json.dumps({'saved': s['label']}))\n"
)
PROBE_TEXT = "solve-mcp-idempotency-64949f24"
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


def _add_tool(
    root: Path,
    *,
    slug: str,
    name: str,
    body: str,
    requires: list[str],
    provides: list[str],
    cases: list[dict],
) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(body, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": name,
                "command": [sys.executable, "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": cases,
            }
        ),
        encoding="utf-8",
    )


def _build_fixture_root(base: Path, events: Path) -> Path:
    root = base / "repo"
    events.parent.mkdir(parents=True, exist_ok=True)
    _add_tool(
        root,
        slug="text-reverser",
        name="probe text reverser",
        body=REVERSE_TOOL,
        requires=["raw_text"],
        provides=["reversed_text"],
        cases=[
            {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
        ],
    )
    _add_tool(
        root,
        slug="append-event",
        name="append event",
        body=APPEND_TOOL,
        requires=["events", "label"],
        provides=["saved"],
        cases=[
            {
                "input": {"events": str(events), "label": label},
                "expect": {"saved": label},
            }
            for label in ("a", "b")
        ],
    )
    proved = {
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    capabilities = {
        "capability.absorbed-text-reverser": dict(
            proved, id="capability.absorbed-text-reverser", name="probe text reverser"
        ),
        "capability.absorbed-append-event": dict(
            proved, id="capability.absorbed-append-event", name="append event"
        ),
    }
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _count(events: Path, label: str) -> int:
    if not events.is_file():
        return 0
    return events.read_text(encoding="utf-8").splitlines().count(label)


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline()
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "solve-mcp-idempotency"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="solve-mcp-idempotency-") as directory:
        base = Path(directory)
        root = base / "repo"
        events = root / "capabilities" / "absorbed" / "append-event" / "effects.txt"
        _build_fixture_root(base, events)
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
            url = f"http://127.0.0.1:{ready['listening']}"
            mcp = f"{url}/mcp"

            health_status, health, _ = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("solve_idempotency") is True
                and health.get("mcp_call_idempotency") is True
            )

            solve_body = {
                "initial_state": {"events": str(events), "label": "solve-once"},
                "goal": ["saved"],
            }
            solve_status, solve_first, solve_headers = _request(
                "POST",
                f"{url}/solve",
                solve_body,
                headers={"Idempotency-Key": "solve-key-1"},
            )
            solve_replay_status, solve_replay, replay_headers = _request(
                "POST",
                f"{url}/solve",
                solve_body,
                headers={"Idempotency-Key": "solve-key-1"},
            )
            observed["solve_status"] = solve_status
            observed["solve_first"] = solve_first if isinstance(solve_first, dict) else None
            observed["solve_replay_status"] = solve_replay_status
            observed["solve_replayed_header"] = replay_headers.get("idempotency-replayed")
            observed["solve_append_count"] = _count(events, "solve-once")
            solve_ok = (
                solve_status == 200
                and isinstance(solve_first, dict)
                and solve_first.get("solved") is True
                and solve_first.get("outcome", {}).get("saved") == "solve-once"
                and solve_replay_status == 200
                and replay_headers.get("idempotency-replayed") == "true"
                and _count(events, "solve-once") == 1
            )

            conflict_status, conflict, _ = _request(
                "POST",
                f"{url}/solve",
                {
                    "initial_state": {"events": str(events), "label": "solve-conflict"},
                    "goal": ["saved"],
                },
                headers={"Idempotency-Key": "solve-key-1"},
            )
            observed["conflict_status"] = conflict_status
            observed["conflict"] = conflict if isinstance(conflict, dict) else None
            conflict_ok = (
                conflict_status == 409
                and isinstance(conflict, dict)
                and conflict.get("code") == "idempotency_conflict"
                and _count(events, "solve-conflict") == 0
            )

            lookup_status, lookup, _ = _request("GET", f"{url}/invocations/solve-key-1")
            observed["lookup_status"] = lookup_status
            observed["lookup_state"] = lookup.get("state") if isinstance(lookup, dict) else None
            lookup_ok = (
                lookup_status == 200
                and isinstance(lookup, dict)
                and lookup.get("state") == "completed"
                and isinstance(lookup.get("response"), dict)
                and lookup["response"].get("solved") is True
            )

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
                        "clientInfo": {"name": "idempotency-probe", "version": "1"},
                    },
                },
            )
            session = str(headers.get("mcp-session-id") or "")
            init_result = handshake.get("result") if isinstance(handshake, dict) else None
            experimental = (
                init_result.get("capabilities", {}).get("experimental")
                if isinstance(init_result, dict)
                else None
            )
            observed["initialize_status"] = init_status
            observed["mcp_session"] = session
            observed["experimental"] = experimental
            initialize_ok = (
                init_status == 200
                and bool(session)
                and isinstance(experimental, dict)
                and experimental.get("idempotencyKey") is True
            )

            missing_status, missing, _ = _request(
                "POST", mcp, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )
            observed["missing_session_status"] = missing_status
            session_required = missing_status == 404

            hdr = {"Mcp-Session-Id": session}
            mcp_args = {"events": str(events), "label": "mcp-once"}
            call_payload = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "append-event",
                    "arguments": mcp_args,
                    "_meta": {"idempotencyKey": "mcp-key-1"},
                },
            }
            call_status, call_first, _ = _request("POST", mcp, call_payload, headers=hdr)
            call_replay_status, call_replay, _ = _request(
                "POST", mcp, dict(call_payload, id=4), headers=hdr
            )
            first_result = call_first.get("result") if isinstance(call_first, dict) else None
            replay_result = call_replay.get("result") if isinstance(call_replay, dict) else None
            observed["mcp_call_status"] = call_status
            observed["mcp_call_first"] = first_result
            observed["mcp_call_replay_status"] = call_replay_status
            observed["mcp_call_replayed"] = (
                replay_result.get("_meta", {}).get("idempotencyReplayed")
                if isinstance(replay_result, dict)
                else None
            )
            observed["mcp_append_count"] = _count(events, "mcp-once")
            mcp_lookup_status, mcp_lookup, _ = _request("GET", f"{url}/invocations/mcp-key-1")
            observed["mcp_lookup_status"] = mcp_lookup_status
            observed["mcp_lookup_state"] = (
                mcp_lookup.get("state") if isinstance(mcp_lookup, dict) else None
            )
            mcp_call_ok = (
                call_status == 200
                and isinstance(first_result, dict)
                and first_result.get("isError") is False
                and first_result.get("structuredContent", {}).get("saved") == "mcp-once"
                and call_replay_status == 200
                and isinstance(replay_result, dict)
                and replay_result.get("_meta", {}).get("idempotencyReplayed") is True
                and _count(events, "mcp-once") == 1
                and mcp_lookup_status == 200
                and isinstance(mcp_lookup, dict)
                and mcp_lookup.get("state") == "completed"
            )

            solve_call = {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "solve_goal",
                    "arguments": {
                        "initial_state": {"events": str(events), "label": "mcp-solve"},
                        "goal": ["saved"],
                    },
                    "_meta": {"idempotencyKey": "mcp-solve-key"},
                },
            }
            sg_status, sg_first, _ = _request("POST", mcp, solve_call, headers=hdr)
            sg_replay_status, sg_replay, _ = _request(
                "POST", mcp, dict(solve_call, id=6), headers=hdr
            )
            sg_result = sg_first.get("result") if isinstance(sg_first, dict) else None
            sg_replay_result = sg_replay.get("result") if isinstance(sg_replay, dict) else None
            observed["mcp_solve_status"] = sg_status
            observed["mcp_solve_replayed"] = (
                sg_replay_result.get("_meta", {}).get("idempotencyReplayed")
                if isinstance(sg_replay_result, dict)
                else None
            )
            observed["mcp_solve_append_count"] = _count(events, "mcp-solve")
            mcp_solve_ok = (
                sg_status == 200
                and isinstance(sg_result, dict)
                and sg_result.get("isError") is False
                and sg_result.get("structuredContent", {}).get("solved") is True
                and sg_replay_status == 200
                and isinstance(sg_replay_result, dict)
                and sg_replay_result.get("_meta", {}).get("idempotencyReplayed") is True
                and _count(events, "mcp-solve") == 1
            )

            invoke_status, invoked, _ = _request(
                "POST",
                f"{url}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            output = invoked.get("output") if isinstance(invoked, dict) else None
            observed["invoke_status"] = invoke_status
            observed["invoke_output"] = output
            invoke_ok = (
                invoke_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == EXPECTED
            )

            checks = {
                "health_flags": health_ok,
                "solve_replay": solve_ok,
                "solve_conflict": conflict_ok,
                "solve_lookup": lookup_ok,
                "mcp_initialize": initialize_ok,
                "mcp_session_required": session_required,
                "mcp_tools_call_replay": mcp_call_ok,
                "mcp_solve_goal_replay": mcp_solve_ok,
                "rest_invoke_still_works": invoke_ok,
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
    print(json.dumps(verdict, sort_keys=True))
    sys.exit(0)
