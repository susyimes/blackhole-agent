"""Acceptance probe: the compounded ledger is served to real MCP clients.

The controller replays probes on baseline and candidate source trees, so
this probe is fully self-contained and exits 0 for both met and unmet
outcomes. On baseline source the server module does not exist, the import
or the spawn fails, and the probe reports passed=false. On candidate
source it must:

1. complete a real MCP ``initialize`` over a live stdio pipe against a
   hermetic fixture ledger (one proved text-reverser, one unproved tool);
2. receive a ``tools/list`` containing exactly the proved invocable
   capability, with an inputSchema/outputSchema derived from its vendored
   manifest contract;
3. execute ``tools/call`` and observe the tool's real transformed output
   as structuredContent (not a replayed fixture: the probe chooses the
   input and checks the reversal itself);
4. observe protocol-correct failure modes: ``isError`` for invalid input,
   JSON-RPC ``-32602`` for an unknown tool;
5. against the real checkout ledger, paginate the full ``tools/list`` and
   confirm one spec-legal, unique tool per invocable ledger capability
   (dozens today), proving the served catalog tracks the live ledger.

Prints JSON with boolean passed and nonempty observed.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


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
    unproved_dir = root / "capabilities" / "absorbed" / "unproved-tool"
    unproved_dir.mkdir(parents=True)
    (unproved_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    (unproved_dir / "absorption.json").write_text(
        json.dumps(dict(manifest, slug="unproved-tool", name="unproved")), encoding="utf-8"
    )
    capabilities = {
        "capability.absorbed-text-reverser": {
            "id": "capability.absorbed-text-reverser",
            "name": "probe text reverser",
            "kind": "python",
            "last_proved_at": "2026-01-01T00:00:00Z",
            "last_proof_exit_code": 0,
        },
        "capability.absorbed-unproved-tool": {
            "id": "capability.absorbed-unproved-tool",
            "name": "unproved",
            "kind": "python",
            "last_proved_at": None,
            "last_proof_exit_code": 1,
        },
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


class _StdioClient:
    """Minimal NDJSON JSON-RPC client driving the server over a real pipe."""

    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process
        self._lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._next_id = 0

    def _pump(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def request(self, method: str, params: dict | None = None, *, timeout: float = 60.0) -> dict:
        self._next_id += 1
        request_id = self._next_id
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()
        while True:
            try:
                line = self._lines.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f"no response to {method} within {timeout}s") from exc
            if line is None:
                raise ConnectionError(f"server stdout closed while awaiting {method}")
            payload = json.loads(line)
            if not isinstance(payload, dict) or payload.get("id") != request_id:
                continue
            return payload


def _spawn(src_root: Path, root: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _paginate_tools(client: _StdioClient) -> list[dict]:
    tools: list[dict] = []
    cursor = ""
    for _ in range(64):
        params = {"cursor": cursor} if cursor else {}
        reply = client.request("tools/list", params)
        result = reply.get("result") or {}
        tools.extend(result.get("tools") or [])
        cursor = str(result.get("nextCursor") or "")
        if not cursor:
            return tools
    raise RuntimeError("tools/list pagination did not terminate")


def _check_fixture_server(src_root: Path, observed: dict) -> bool:
    with tempfile.TemporaryDirectory(prefix="mcp-capability-probe-") as directory:
        root = _build_fixture_root(Path(directory))
        process = _spawn(src_root, root)
        try:
            client = _StdioClient(process)
            handshake = client.request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "acceptance-probe", "version": "1.0.0"},
                },
            )
            result = handshake.get("result") or {}
            observed["fixture_server_info"] = result.get("serverInfo")
            observed["fixture_protocol"] = result.get("protocolVersion")
            handshake_ok = (
                result.get("protocolVersion") == "2025-03-26"
                and isinstance(result.get("serverInfo"), dict)
                and "tools" in (result.get("capabilities") or {})
            )

            tools = _paginate_tools(client)
            names = [tool.get("name") for tool in tools]
            observed["fixture_tools"] = names
            listing_ok = names == ["text-reverser"]
            schema = tools[0] if tools else {}
            schema_ok = (
                (schema.get("inputSchema") or {}).get("required") == ["raw_text"]
                and (schema.get("outputSchema") or {}).get("required") == ["reversed_text"]
            )

            probe_input = "unbound mission probe"
            called = client.request(
                "tools/call", {"name": "text-reverser", "arguments": {"raw_text": probe_input}}
            )
            call_result = called.get("result") or {}
            structured = call_result.get("structuredContent")
            observed["fixture_structured"] = structured
            observed["fixture_is_error"] = call_result.get("isError")
            call_ok = (
                call_result.get("isError") is False
                and structured == {"reversed_text": probe_input[::-1]}
                and isinstance(call_result.get("content"), list)
            )

            refused = client.request(
                "tools/call", {"name": "text-reverser", "arguments": {"unexpected": 1}}
            )
            refused_result = refused.get("result") or {}
            observed["fixture_refused_is_error"] = refused_result.get("isError")
            refused_ok = refused_result.get("isError") is True

            unknown = client.request("tools/call", {"name": "no-such-tool", "arguments": {}})
            unknown_error = unknown.get("error") or {}
            observed["fixture_unknown_error"] = unknown_error
            unknown_ok = unknown_error.get("code") == -32602

            observed["fixture_checks"] = {
                "handshake": handshake_ok,
                "listing": listing_ok,
                "schema": schema_ok,
                "call": call_ok,
                "refused": refused_ok,
                "unknown": unknown_ok,
            }
            return all(observed["fixture_checks"].values())
        finally:
            process.kill()


def _check_real_ledger(src_root: Path, observed: dict) -> bool:
    repo_root = src_root.parent
    from blackhole_agent.capability_service import load_invocable_capabilities

    invocable = load_invocable_capabilities(repo_root)
    expected = len(invocable)
    observed["real_invocable_count"] = expected
    if expected == 0:
        observed["detail"] = "real ledger has no invocable capabilities to serve"
        return False
    process = _spawn(src_root, repo_root)
    try:
        client = _StdioClient(process)
        client.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "acceptance-probe", "version": "1.0.0"},
            },
        )
        tools = _paginate_tools(client)
        names = [str(tool.get("name") or "") for tool in tools]
        observed["real_tool_count"] = len(names)
        observed["real_names_spec_legal"] = all(_NAME_PATTERN.match(name) for name in names)
        observed["real_names_unique"] = len(set(names)) == len(names)
        schemas_ok = all(
            isinstance(tool.get("inputSchema"), dict)
            and tool["inputSchema"].get("type") == "object"
            and isinstance(tool["inputSchema"].get("required"), list)
            for tool in tools
        )
        observed["real_schemas_ok"] = schemas_ok
        return (
            len(names) == expected
            and observed["real_names_spec_legal"]
            and observed["real_names_unique"]
            and schemas_ok
        )
    finally:
        process.kill()


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-capability-plane"}
    try:
        import blackhole_agent.mcp_capability_server as server
    except Exception as error:  # baseline source tree has no capability MCP server
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(server.__file__).resolve().parents[1]
    try:
        fixture_ok = _check_fixture_server(src_root, observed)
    except Exception as error:
        observed["fixture_error"] = f"{type(error).__name__}: {error}"
        fixture_ok = False
    try:
        real_ok = _check_real_ledger(src_root, observed)
    except Exception as error:
        observed["real_error"] = f"{type(error).__name__}: {error}"
        real_ok = False
    observed["fixture_ok"] = fixture_ok
    observed["real_ledger_ok"] = real_ok
    return {"passed": bool(fixture_ok and real_ok), "observed": observed}


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as error:  # never crash the sweep: unmet, not crashed
        verdict = {
            "passed": False,
            "observed": {
                "family": "mcp-capability-plane",
                "fatal": f"{type(error).__name__}: {error}",
            },
        }
    print(json.dumps(verdict))
    sys.exit(0)
