"""Acceptance probe: scoped tokens show their allowlist and MCP refuses others.

A scoped bearer currently authorizes POST /invoke of listed tools, but GET
/console still renders the full catalog and MCP tools/call of a disallowed
name comes back as isError instead of JSON-RPC invalid-params. This probe
starts the invocation plane as a separate OS process with an operator token
and a scoped token that may invoke only one fixture tool, then drives real
loopback HTTP:

1. GET /health reports token_scopes true.
2. GET /console with the scoped Bearer embeds that token's allowlist (the
   shout id, not the reverser) in the served HTML catalog.
3. POST /mcp tools/call of the shout MCP name with the scoped token returns
   the declared shout output.
4. POST /mcp tools/call of the reverser MCP name with that same scoped token
   is JSON-RPC -32602 and does not return reversed output.
5. POST /mcp tools/call of the reverser with the operator token still
   reverses.
6. A plane started with only --token reports token_scopes false; GET
   /console is unscoped and that token still reverses over MCP.

On the pre-mission plane GET /console ignores the scoped bearer and MCP
tools/call of a listed-but-disallowed name is isError, so the probe reports
passed=false. Both outcomes exit 0 with JSON passed and nonempty observed.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

PROBE_TEXT = "token-scope-console-8e2b3589"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
REVERSE_ID = "capability.absorbed-text-reverser"
SHOUT_ID = "capability.absorbed-scope-shout"
SHOUT_INPUT = {"text": "blackhole unbound"}
SHOUT_OUTPUT = "BLACKHOLE UNBOUND!"
OPERATOR = "operator-token-8e2b3589"
SCOPED = "scoped-token-8e2b3589"

_REVERSE_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)
_SHOUT_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'shout_output': state['text'].upper() + '!'}))\n"
)


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 45,
) -> tuple[int, object, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
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
            try:
                return exc.code, exc.read().decode("utf-8"), captured
            except Exception:
                return exc.code, None, captured
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, {}


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
    tool_dir.mkdir(parents=True, exist_ok=True)
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
                    {"input": {key: "x" for key in requires}, "expect": {provides[0]: "x"}},
                    {"input": {key: "y" for key in requires}, "expect": {provides[0]: "y"}},
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "probe-workspace"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    _write_tool(root, "text-reverser", _REVERSE_TOOL, ["raw_text"], ["reversed_text"])
    _write_tool(root, "scope-shout", _SHOUT_TOOL, ["text"], ["shout_output"])
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    REVERSE_ID: _ledger_entry(REVERSE_ID, "probe text reverser"),
                    SHOUT_ID: _ledger_entry(SHOUT_ID, "probe scope shout"),
                },
            }
        ),
        encoding="utf-8",
    )


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline() if process.stdout is not None else ""
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _start_plane(
    src_root: Path,
    root: Path,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen, dict[str, object]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("BLACKHOLE_BUNDLE_IMPORT", None)
    env.pop("BLACKHOLE_INVOCATION_TOKEN", None)
    env.pop("BLACKHOLE_TOKEN_SCOPE", None)
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


def _parse_allowlist(page: object) -> dict[str, object] | None:
    if not isinstance(page, str):
        return None
    match = re.search(r'<pre id="token-allowlist">(.*?)</pre>', page, re.DOTALL)
    if not match:
        return None
    try:
        payload = json.loads(html.unescape(match.group(1).strip()))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _mcp_call(
    url: str,
    *,
    token: str,
    session: str,
    request_id: int,
    name: str,
    arguments: dict,
) -> tuple[int, object]:
    status, body, _hdrs = _request(
        "POST",
        url,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        token=token,
        headers={"Mcp-Session-Id": session},
    )
    return status, body


def _mcp_session(url: str, token: str) -> tuple[bool, str, object]:
    status, body, headers = _request(
        "POST",
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "token-scope-console-mcp", "version": "1"},
            },
        },
        token=token,
    )
    session = str(headers.get("mcp-session-id") or "")
    result = body.get("result") if isinstance(body, dict) else None
    ok = status == 200 and bool(session) and isinstance(result, dict)
    return ok, session, body


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "token-scope-console-mcp"}
    try:
        import blackhole_agent.capability_service as service
        import blackhole_agent.capability_console as console
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "bind_optional_bearer") and not hasattr(
        service, "_bind_optional_principal"
    ):
        # Baseline may already have token scopes; the leftover is console + MCP.
        pass
    src_root = Path(service.__file__).resolve().parents[1]
    if "token-allowlist" not in getattr(console, "_PAGE", "") and not hasattr(
        console, "principal_allowlist_payload"
    ):
        observed["detail"] = "baseline console has no token allowlist"
        # Continue to exercise HTTP so observed is populated; still fail closed.

    scope_flag = f"{SCOPED}={SHOUT_ID}"
    with tempfile.TemporaryDirectory(prefix="token-scope-console-mcp-") as directory:
        base = Path(directory)
        root = base / "repo"
        _write_workspace(root)

        process, sink = _start_plane(
            src_root,
            root,
            ["--token", OPERATOR, "--token-scope", scope_flag],
        )
        try:
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = _stop_plane(process)
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            url = f"http://127.0.0.1:{ready['listening']}"
            mcp = f"{url}/mcp"

            health_status, health, _ = _request("GET", f"{url}/health")
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("token_scopes") is True
            )

            console_status, console_page, console_headers = _request(
                "GET", f"{url}/console", token=SCOPED
            )
            allowlist = _parse_allowlist(console_page)
            observed["console_status"] = console_status
            observed["console_content_type"] = console_headers.get("content-type", "")
            observed["console_allowlist"] = allowlist
            page_text = console_page if isinstance(console_page, str) else ""
            observed["console_has_shout"] = SHOUT_ID in page_text
            observed["console_has_reverser"] = REVERSE_ID in page_text
            console_ok = (
                console_status == 200
                and "text/html" in str(console_headers.get("content-type") or "")
                and isinstance(allowlist, dict)
                and allowlist.get("scoped") is True
                and allowlist.get("allow") == [SHOUT_ID]
                and SHOUT_ID in page_text
                and REVERSE_ID not in page_text
            )

            open_status, open_page, _ = _request("GET", f"{url}/console")
            open_allowlist = _parse_allowlist(open_page)
            observed["open_console_allowlist"] = open_allowlist
            open_ok = open_status == 200 and (
                open_allowlist is None or open_allowlist.get("scoped") is not True
            )

            mcp_ok, session, init_body = _mcp_session(mcp, SCOPED)
            observed["mcp_init"] = init_body if isinstance(init_body, dict) else None
            observed["mcp_session"] = session

            shout_status, shouted = _mcp_call(
                mcp,
                token=SCOPED,
                session=session,
                request_id=2,
                name="scope-shout",
                arguments=SHOUT_INPUT,
            )
            shout_result = shouted.get("result") if isinstance(shouted, dict) else None
            shout_structured = (
                shout_result.get("structuredContent") if isinstance(shout_result, dict) else None
            )
            observed["scoped_shout"] = shouted if isinstance(shouted, dict) else None
            shout_ok = (
                mcp_ok
                and shout_status == 200
                and isinstance(shout_structured, dict)
                and shout_structured.get("shout_output") == SHOUT_OUTPUT
                and shout_result.get("isError") is False
            )

            denied_status, denied = _mcp_call(
                mcp,
                token=SCOPED,
                session=session,
                request_id=3,
                name="text-reverser",
                arguments={"raw_text": PROBE_TEXT},
            )
            denied_error = denied.get("error") if isinstance(denied, dict) else None
            denied_result = denied.get("result") if isinstance(denied, dict) else None
            observed["denied_mcp"] = denied if isinstance(denied, dict) else None
            denied_blob = json.dumps(denied) if isinstance(denied, dict) else ""
            denied_ok = (
                denied_status == 200
                and isinstance(denied_error, dict)
                and denied_error.get("code") == -32602
                and "tool not allowed" in str(denied_error.get("message") or "").lower()
                and EXPECTED_REVERSE not in denied_blob
                and not (isinstance(denied_result, dict) and denied_result.get("isError") is True)
            )

            op_ok, op_session, _op_init = _mcp_session(mcp, OPERATOR)
            op_status, reversed_body = _mcp_call(
                mcp,
                token=OPERATOR,
                session=op_session,
                request_id=2,
                name="text-reverser",
                arguments={"raw_text": PROBE_TEXT},
            )
            op_result = reversed_body.get("result") if isinstance(reversed_body, dict) else None
            op_structured = (
                op_result.get("structuredContent") if isinstance(op_result, dict) else None
            )
            observed["operator_reverse"] = (
                reversed_body if isinstance(reversed_body, dict) else None
            )
            operator_ok = (
                op_ok
                and op_status == 200
                and isinstance(op_structured, dict)
                and op_structured.get("reversed_text") == EXPECTED_REVERSE
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-4000:]

        closed_root = base / "closed"
        _write_workspace(closed_root)
        closed, closed_sink = _start_plane(
            src_root,
            closed_root,
            ["--token", OPERATOR],
        )
        try:
            closed_ready = closed_sink.get("ready")
            observed["closed_ready"] = closed_ready
            if not isinstance(closed_ready, dict) or not closed_ready.get("listening"):
                err = _stop_plane(closed)
                observed["closed_detail"] = "closed plane never reported a listening port"
                observed["closed_stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            closed_url = f"http://127.0.0.1:{closed_ready['listening']}"
            closed_health_status, closed_health, _ = _request("GET", f"{closed_url}/health")
            closed_console_status, closed_console, _ = _request(
                "GET", f"{closed_url}/console", token=OPERATOR
            )
            closed_allowlist = _parse_allowlist(closed_console)
            observed["closed_allowlist"] = closed_allowlist
            closed_mcp_ok, closed_session, _ = _mcp_session(f"{closed_url}/mcp", OPERATOR)
            closed_rev_status, closed_reversed = _mcp_call(
                f"{closed_url}/mcp",
                token=OPERATOR,
                session=closed_session,
                request_id=2,
                name="text-reverser",
                arguments={"raw_text": PROBE_TEXT},
            )
            closed_result = (
                closed_reversed.get("result") if isinstance(closed_reversed, dict) else None
            )
            closed_structured = (
                closed_result.get("structuredContent") if isinstance(closed_result, dict) else None
            )
            closed_ok = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("token_scopes") is False
                and closed_console_status == 200
                and (closed_allowlist is None or closed_allowlist.get("scoped") is not True)
                and closed_mcp_ok
                and closed_rev_status == 200
                and isinstance(closed_structured, dict)
                and closed_structured.get("reversed_text") == EXPECTED_REVERSE
            )
        finally:
            observed["closed_stderr"] = (_stop_plane(closed) or "")[-4000:]

        passed = all(
            (
                health_ok,
                console_ok,
                open_ok,
                shout_ok,
                denied_ok,
                operator_ok,
                closed_ok,
            )
        )
        observed["checks"] = {
            "health": health_ok,
            "scoped_console_allowlist": console_ok,
            "unauthenticated_console": open_ok,
            "scoped_mcp_shout": shout_ok,
            "scoped_mcp_denied_invalid_params": denied_ok,
            "operator_mcp_reverse": operator_ok,
            "fail_closed": closed_ok,
        }
        return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
