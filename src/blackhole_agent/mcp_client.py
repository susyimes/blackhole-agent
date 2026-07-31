"""Live MCP actuation: real stdio JSON-RPC sessions with sealed execution evidence.

``capability.mcp-tool-import`` converts MCP ``tools/list`` payloads into
routable descriptors, but it never talks to a server. This module closes that
gap: it spawns a real MCP server subprocess, performs the initialize
handshake over newline-delimited JSON-RPC 2.0, imports the live tool list
through the policy-routing layer (explicit ``mcp`` provider opt-in), executes
a real ``tools/call``, and seals the whole session — handshake, tools,
routing decision, call, and result — into a digest-chained artifact under
``artifacts/mcp-live/`` that ``verify_execution_trace`` re-checks.

The hermetic proof uses the in-repo reference server
(``blackhole_agent.mcp_echo_server``), so no network or third-party server is
needed; the same code path works against any standards-compliant stdio MCP
server command.

Determinism/falsifiability contract: ``verify_execution_trace`` recomputes
every digest from the recorded payloads, so a tampered trace fails
verification. The builtin proof also proves the fail-closed path: an unknown
tool call returns a JSON-RPC error and raises instead of silently passing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import atomic_write_json, utc_now_iso
from blackhole_agent.tool_routing import (
    DEFAULT_EXECUTABLE_TOOL_PROVIDERS,
    EXECUTABLE_TOOL_ROUTE,
    MCP_TOOL_PROVIDER,
    route_tool_descriptor,
    tool_descriptors_from_mcp_tools,
)

SCHEMA_VERSION = 1
DEFAULT_PROTOCOL_VERSION = "2025-03-26"
CLIENT_INFO = {"name": "blackhole-unbound", "version": "1.0.0"}
DEFAULT_ARTIFACT_DIR = "artifacts/mcp-live"

REPO_ROOT = Path(__file__).resolve().parents[2]


def echo_server_command() -> list[str]:
    """Command line that spawns the in-repo reference MCP server."""

    return [sys.executable, "-m", "blackhole_agent.mcp_echo_server"]


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class McpProtocolError(RuntimeError):
    """Raised when the server misbehaves, times out, or returns a JSON-RPC error."""


class McpStdioSession:
    """One live MCP stdio session: initialize -> tools/list -> tools/call."""

    def __init__(self, command: Sequence[str], *, timeout_seconds: float = 30.0) -> None:
        self.command = [str(part) for part in command]
        self.timeout_seconds = float(timeout_seconds)
        self._process: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._next_id = 0
        self.server_info: dict[str, Any] = {}
        self.protocol_version = ""

    def start(self) -> "McpStdioSession":
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            cwd=str(REPO_ROOT),
        )
        reader = threading.Thread(target=self._pump, daemon=True)
        reader.start()
        handshake = self.request(
            "initialize",
            {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        if not isinstance(handshake, Mapping) or "serverInfo" not in handshake:
            raise McpProtocolError(f"malformed initialize result: {handshake!r}")
        self.server_info = dict(handshake.get("serverInfo") or {})
        self.protocol_version = str(handshake.get("protocolVersion") or "")
        self.notify("notifications/initialized", {})
        return self

    def _pump(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, message: Mapping[str, Any]) -> None:
        if self._process is None or self._process.stdin is None or self._process.poll() is not None:
            raise McpProtocolError("MCP server process is not running")
        self._process.stdin.write(json.dumps(message) + "\n")
        self._process.stdin.flush()

    def _read_response(self, request_id: int) -> dict[str, Any]:
        while True:
            try:
                line = self._lines.get(timeout=self.timeout_seconds)
            except queue.Empty as error:
                raise McpProtocolError(f"timeout waiting for response id={request_id}") from error
            if line is None:
                raise McpProtocolError("MCP server closed stdout before responding")
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("id") != request_id:
                # Notifications or unrelated traffic; keep waiting for our response.
                continue
            return message

    def request(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params or {})})
        response = self._read_response(request_id)
        if "error" in response:
            error = response["error"] or {}
            raise McpProtocolError(
                f"JSON-RPC error {error.get('code')}: {error.get('message')} for method {method}"
            )
        return response.get("result")

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": dict(params or {})})

    def list_tools(self) -> dict[str, Any]:
        result = self.request("tools/list", {})
        if not isinstance(result, Mapping) or not isinstance(result.get("tools"), list):
            raise McpProtocolError(f"malformed tools/list result: {result!r}")
        return dict(result)

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": dict(arguments)})
        if not isinstance(result, Mapping):
            raise McpProtocolError(f"malformed tools/call result: {result!r}")
        return dict(result)

    def close(self) -> None:
        if self._process is None:
            return
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
        except OSError:
            pass
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
        self._process = None

    def __enter__(self) -> "McpStdioSession":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()


def _extract_text(result: Mapping[str, Any]) -> str:
    content = result.get("content") or []
    parts = [str(item.get("text") or "") for item in content if isinstance(item, Mapping)]
    return "".join(parts)


def run_live_execution(
    *,
    command: Sequence[str] | None = None,
    server_name: str = "echo",
    tool_name: str = "echo",
    arguments: Mapping[str, Any] | None = None,
    output_dir: Path | None = None,
    recorded_at: str | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """Run one live MCP session end-to-end and seal it as a digest-chained trace.

    Stages: spawn server -> initialize handshake -> live tools/list -> import
    through the routing layer (explicit mcp provider opt-in) -> require the
    target tool to route executable -> live tools/call -> seal trace.
    """

    command = [str(part) for part in (command or echo_server_command())]
    arguments = dict(arguments or {"text": "blackhole-live-mcp"})
    with McpStdioSession(command, timeout_seconds=timeout_seconds) as session:
        handshake = {"serverInfo": session.server_info, "protocolVersion": session.protocol_version}
        tools_payload = session.list_tools()
        descriptors = tool_descriptors_from_mcp_tools(tools_payload, server_name=server_name)
        target_name = f"{server_name}:{tool_name}"
        target = next((item for item in descriptors if item.name == target_name), None)
        if target is None:
            raise McpProtocolError(f"tool {tool_name!r} not advertised by server {server_name!r}")
        decision = route_tool_descriptor(
            target,
            executable_providers=(*DEFAULT_EXECUTABLE_TOOL_PROVIDERS, MCP_TOOL_PROVIDER),
        )
        routing = {
            "descriptor": {
                "name": target.name,
                "provider": target.provider,
                "tool_type": target.tool_type,
                "risk_flags": list(target.risk_flags),
                "parameters": target.parameters,
            },
            "route": decision.route,
            "reasons": list(decision.reasons),
            "executable": decision.executable,
        }
        if not decision.executable:
            raise McpProtocolError(f"tool {target_name!r} did not route executable: {decision.reasons}")
        call_result = session.call_tool(tool_name, arguments)

    trace_body = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mcp_live_execution_trace",
        "recorded_at": recorded_at or utc_now_iso(),
        "server_command": command,
        "server_name": server_name,
        "handshake": handshake,
        "handshake_digest": _digest(handshake),
        "tools_payload": tools_payload,
        "tools_digest": _digest(tools_payload),
        "imported_tool_names": [item.name for item in descriptors],
        "routing": routing,
        "routing_digest": _digest(routing),
        "call": {"name": tool_name, "arguments": arguments, "result": call_result},
        "call_digest": _digest({"name": tool_name, "arguments": arguments, "result": call_result}),
    }
    trace = {**trace_body, "trace_digest": _digest(trace_body)}

    out = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="mcp-live-"))
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out / "execution.json", trace)
    return {
        "ok": True,
        "trace_digest": trace["trace_digest"],
        "output_dir": str(out),
        "server_info": handshake["serverInfo"],
        "imported_tool_names": trace_body["imported_tool_names"],
        "result_text": _extract_text(call_result),
    }


def verify_execution_trace(trace_dir: Path) -> dict[str, Any]:
    """Re-verify a sealed live-execution trace; any tamper or drift fails."""

    trace_path = Path(trace_dir) / "execution.json"
    if not trace_path.exists():
        return {"ok": False, "error": f"missing execution trace in {trace_dir}"}
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    body = {key: value for key, value in trace.items() if key != "trace_digest"}
    call = trace.get("call") or {}
    checks = {
        "trace_digest": _digest(body) == trace.get("trace_digest"),
        "handshake_digest": _digest(trace.get("handshake")) == trace.get("handshake_digest"),
        "tools_digest": _digest(trace.get("tools_payload")) == trace.get("tools_digest"),
        "routing_digest": _digest(trace.get("routing")) == trace.get("routing_digest"),
        "call_digest": _digest(
            {"name": call.get("name"), "arguments": call.get("arguments"), "result": call.get("result")}
        )
        == trace.get("call_digest"),
        "handshake_has_server_info": bool((trace.get("handshake") or {}).get("serverInfo")),
        "routing_executable": (trace.get("routing") or {}).get("executable") is True
        and (trace.get("routing") or {}).get("route") == EXECUTABLE_TOOL_ROUTE,
        "call_result_present": bool(call.get("result")),
        "tool_was_imported": f"{trace.get('server_name')}:{call.get('name')}"
        in (trace.get("imported_tool_names") or []),
    }
    return {"ok": all(checks.values()), "checks": checks, "trace_digest": trace.get("trace_digest")}


def external_filesystem_server_command(allowed_dir: Path) -> list[str] | None:
    """Command line for the official third-party filesystem MCP server.

    Returns None when no npx launcher is available. On Windows npx is a batch
    shim that CreateProcess cannot exec directly, so it goes through cmd.exe.
    """

    import shutil

    npx = shutil.which("npx")
    if npx is None:
        return None
    base = ["cmd.exe", "/c", npx] if sys.platform.startswith("win") else [npx]
    return [*base, "-y", "@modelcontextprotocol/server-filesystem", str(allowed_dir)]


def builtin_mcp_live_external_proof() -> dict[str, Any]:
    """Registered proof for ``capability.mcp-live-external``.

    Runs the full live actuation path against a real external third-party MCP
    server — the official ``@modelcontextprotocol/server-filesystem`` spawned
    via npx: handshake against ``secure-filesystem-server``, live tools/list,
    policy-routed import, a real ``read_file`` call returning a sentinel file
    the server read from disk, sealed + re-verified trace, tamper
    falsification, and a fail-closed check that reading outside the allowed
    directory is refused by the server.
    """

    import shutil

    with tempfile.TemporaryDirectory(prefix="mcp-external-proof-") as tmp:
        sandbox = Path(tmp) / "sandbox"
        sandbox.mkdir()
        sentinel = "blackhole-external-mcp-sentinel"
        sentinel_path = sandbox / "sentinel.txt"
        sentinel_path.write_text(sentinel + "\n", encoding="utf-8")

        command = external_filesystem_server_command(sandbox)
        if command is None:
            return {"ok": False, "error": "npx not available; cannot spawn external MCP server"}

        out = Path(tmp) / "live"
        try:
            run = run_live_execution(
                command=command,
                server_name="fs",
                tool_name="read_file",
                arguments={"path": str(sentinel_path)},
                output_dir=out,
                timeout_seconds=180.0,
            )
        except McpProtocolError as error:
            return {"ok": False, "error": f"external session failed: {error}"}
        verify = verify_execution_trace(out)

        # Tamper falsification: edited recorded result must fail verification.
        clone = Path(tmp) / "tampered"
        shutil.copytree(out, clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["call"]["result"]["content"][0]["text"] = "forged"
        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_execution_trace(clone)

        # Fail-closed: the server must refuse paths outside its allowed root.
        outside_refused = False
        with McpStdioSession(command, timeout_seconds=180.0) as session:
            outside = session.call_tool("read_file", {"path": str(Path(tmp) / "outside.txt")})
            outside_refused = bool(outside.get("isError"))

    server = run.get("server_info") or {}
    ok = (
        run["ok"]
        and verify["ok"]
        and sentinel in run["result_text"]
        and not tampered["ok"]
        and outside_refused
        and server.get("name") == "secure-filesystem-server"
        and "fs:read_file" in run["imported_tool_names"]
        and "fs:write_file" in run["imported_tool_names"]
    )
    return {
        "ok": bool(ok),
        "trace_digest": run.get("trace_digest"),
        "server_info": server,
        "imported_tool_count": len(run.get("imported_tool_names") or []),
        "external_result_verified": sentinel in run.get("result_text", ""),
        "trace_verified": verify["ok"],
        "tamper_falsified": not tampered["ok"],
        "outside_allowed_dir_refused": outside_refused,
    }


def builtin_mcp_live_execution_proof() -> dict[str, Any]:
    """Registered proof for ``capability.mcp-live-execution``.

    Spawns the real reference MCP server subprocess, runs a full live session
    (handshake -> tools/list -> policy routing -> tools/call), checks the
    echo result is the server's actual response, seals and re-verifies the
    trace, and proves falsifiability: a tampered trace copy must fail
    verification, and an unknown-tool call must raise a JSON-RPC error.
    """

    import shutil

    with tempfile.TemporaryDirectory(prefix="mcp-live-proof-") as tmp:
        out = Path(tmp) / "live"
        sentinel = "blackhole-live-mcp-proof"
        run = run_live_execution(
            server_name="echo",
            tool_name="echo",
            arguments={"text": sentinel},
            output_dir=out,
        )
        verify = verify_execution_trace(out)

        # Tamper falsification: edited recorded result must fail verification.
        clone = Path(tmp) / "tampered"
        shutil.copytree(out, clone)
        trace = json.loads((clone / "execution.json").read_text(encoding="utf-8"))
        trace["call"]["result"]["content"][0]["text"] = "forged"
        atomic_write_json(clone / "execution.json", trace)
        tampered = verify_execution_trace(clone)

        # Fail-closed: unknown tool raises a JSON-RPC error instead of passing.
        unknown_tool_failed = False
        with McpStdioSession(echo_server_command()) as session:
            try:
                session.call_tool("does-not-exist", {})
            except McpProtocolError:
                unknown_tool_failed = True

    ok = (
        run["ok"]
        and verify["ok"]
        and run["result_text"] == sentinel
        and not tampered["ok"]
        and unknown_tool_failed
        and "echo:echo" in run["imported_tool_names"]
        and "echo:sha256" in run["imported_tool_names"]
    )
    return {
        "ok": bool(ok),
        "trace_digest": run.get("trace_digest"),
        "server_info": run.get("server_info"),
        "imported_tool_names": run.get("imported_tool_names"),
        "live_result_echoed": run.get("result_text") == sentinel,
        "trace_verified": verify["ok"],
        "tamper_falsified": not tampered["ok"],
        "unknown_tool_fail_closed": unknown_tool_failed,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live MCP execution with sealed evidence")
    sub = parser.add_subparsers(dest="command_name", required=True)

    execute = sub.add_parser("execute", help="Run one live MCP execution and seal the trace")
    execute.add_argument("--command", nargs="+", default=None, help="MCP server command (default: in-repo echo server)")
    execute.add_argument("--server-name", default="echo")
    execute.add_argument("--tool", default="echo")
    execute.add_argument("--args", default='{"text": "blackhole-live-mcp"}')
    execute.add_argument("--output-dir", default=None)

    verify = sub.add_parser("verify", help="Re-verify a sealed execution trace")
    verify.add_argument("--trace-dir", required=True)

    args = parser.parse_args(argv)
    if args.command_name == "execute":
        output_dir = Path(args.output_dir) if args.output_dir else (
            REPO_ROOT / DEFAULT_ARTIFACT_DIR / utc_now_iso().replace(":", "").replace("-", "")
        )
        result = run_live_execution(
            command=args.command,
            server_name=args.server_name,
            tool_name=args.tool,
            arguments=json.loads(args.args),
            output_dir=output_dir,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    result = verify_execution_trace(Path(args.trace_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
