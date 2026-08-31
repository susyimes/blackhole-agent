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

Stdio sessions answer server-originated JSON-RPC requests (``ping``,
``roots/list``) on the same stream so a spec-compliant plugin that probes the
client before returning a tool result stays live. ``answer_reverse_channel=False``
is the fail-open hole: those inbound requests are ignored and the plugin stalls.

The external third-party plane (official ``server-filesystem`` via npx) is
two-tier: the live tier (``run_live_external_proof``) performs a fresh
networked actuation and seals a durable trace with a ``latest-external.json``
pointer, while the registered proof (``builtin_mcp_live_external_proof``) is
hermetic — pure re-verification of the latest sealed trace (pointer binding,
digest chain, recorded sentinel semantics) plus throwaway-directory tamper
falsification, so it fits the integrity batch budget.

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
DEFAULT_MCP_ROOTS: tuple[dict[str, str], ...] = (
    {"uri": "file:///workspace", "name": "workspace"},
)

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


def is_mcp_transport_failure(exc: BaseException) -> bool:
    """True for hung or dead JSON-RPC transport, not application-level tool errors."""

    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "timeout waiting for response",
            "closed stdout",
            "process is not running",
        )
    )


def is_jsonrpc_server_request(message: Mapping[str, Any]) -> bool:
    """True for a JSON-RPC request the server sent to the client."""

    return (
        isinstance(message, Mapping)
        and "method" in message
        and "id" in message
        and "result" not in message
        and "error" not in message
    )


def reverse_channel_reply(
    message: Mapping[str, Any],
    *,
    roots: Sequence[Mapping[str, str]] = DEFAULT_MCP_ROOTS,
) -> dict[str, Any]:
    """Build the JSON-RPC response for a server-originated request."""

    method = str(message.get("method") or "")
    request_id = message.get("id")
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "roots/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"roots": [dict(item) for item in roots]},
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


DEFAULT_ELICITATION_CONTENT: dict[str, Any] = {"approved": True}
DEFAULT_SAMPLING_MODEL = "blackhole-unbound"
DEFAULT_SAMPLING_STOP = "endTurn"


def elicitation_reply(
    message: Mapping[str, Any],
    *,
    content: Mapping[str, Any] | None = None,
    action: str = "accept",
) -> dict[str, Any]:
    """Build the JSON-RPC response for a server-originated elicitation/create."""

    resolved = str(action or "accept")
    result: dict[str, Any] = {"action": resolved}
    if resolved == "accept":
        result["content"] = dict(content or DEFAULT_ELICITATION_CONTENT)
    return {"jsonrpc": "2.0", "id": message.get("id"), "result": result}


def sampling_user_text(message: Mapping[str, Any]) -> str:
    """Return the last user text from a sampling/createMessage request."""

    params = message.get("params") if isinstance(message.get("params"), Mapping) else {}
    messages = params.get("messages") if isinstance(params.get("messages"), list) else []
    for item in reversed(list(messages)):
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if isinstance(content, Mapping) and str(content.get("type") or "text") == "text":
            return str(content.get("text") or "")
        if isinstance(content, str):
            return content
    return ""


def sampling_reply(
    message: Mapping[str, Any],
    *,
    text: str | None = None,
    model: str = DEFAULT_SAMPLING_MODEL,
    stop_reason: str = DEFAULT_SAMPLING_STOP,
) -> dict[str, Any]:
    """Build the JSON-RPC response for a server-originated sampling/createMessage."""

    user = sampling_user_text(message)
    resolved = str(text) if text is not None else (f"sampled:{user}" if user else "sampled")
    return {
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "result": {
            "role": "assistant",
            "content": {"type": "text", "text": resolved},
            "model": str(model or DEFAULT_SAMPLING_MODEL),
            "stopReason": str(stop_reason or DEFAULT_SAMPLING_STOP),
        },
    }


class McpStdioSession:
    """One live MCP stdio session: initialize -> tools/list -> resources/list -> prompts/list."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float = 30.0,
        answer_reverse_channel: bool = True,
        answer_sampling: bool = False,
        roots: Sequence[Mapping[str, str]] | None = None,
    ) -> None:
        self.command = [str(part) for part in command]
        self.timeout_seconds = float(timeout_seconds)
        self.answer_reverse_channel = bool(answer_reverse_channel)
        self.answer_sampling = bool(answer_sampling)
        self.roots = tuple(dict(item) for item in (roots if roots is not None else DEFAULT_MCP_ROOTS))
        self.answered_requests: list[dict[str, Any]] = []
        self._process: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._next_id = 0
        self.server_info: dict[str, Any] = {}
        self.server_capabilities: dict[str, Any] = {}
        self.protocol_version = ""

    def start(self) -> "McpStdioSession":
        try:
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
            client_capabilities: dict[str, Any] = {}
            if self.answer_reverse_channel:
                client_capabilities["roots"] = {}
            if self.answer_sampling:
                client_capabilities["sampling"] = {}
            handshake = self.request(
                "initialize",
                {
                    "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                    "capabilities": client_capabilities,
                    "clientInfo": CLIENT_INFO,
                },
            )
            if not isinstance(handshake, Mapping) or "serverInfo" not in handshake:
                raise McpProtocolError(f"malformed initialize result: {handshake!r}")
            self.server_info = dict(handshake.get("serverInfo") or {})
            self.server_capabilities = dict(handshake.get("capabilities") or {})
            self.protocol_version = str(handshake.get("protocolVersion") or "")
            self.notify("notifications/initialized", {})
            return self
        except Exception:
            self.kill()
            raise

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
            if is_jsonrpc_server_request(message):
                self._answer_server_request(message)
                continue
            if message.get("id") != request_id:
                # Notifications or unrelated traffic; keep waiting for our response.
                continue
            return message

    def _answer_server_request(self, message: Mapping[str, Any]) -> None:
        """Reply to a server-originated JSON-RPC request, or ignore it (the hole)."""

        method = str(message.get("method") or "")
        if method == "sampling/createMessage":
            if not self.answer_sampling:
                return
            reply = sampling_reply(message)
        else:
            if not self.answer_reverse_channel:
                return
            reply = reverse_channel_reply(message, roots=self.roots)
        self._send(reply)
        self.answered_requests.append(
            {
                "method": str(message.get("method") or ""),
                "id": message.get("id"),
                "error": "error" in reply,
            }
        )

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

    def list_resources(self) -> dict[str, Any]:
        result = self.request("resources/list", {})
        if not isinstance(result, Mapping) or not isinstance(result.get("resources"), list):
            raise McpProtocolError(f"malformed resources/list result: {result!r}")
        return dict(result)

    def list_resource_templates(self) -> dict[str, Any]:
        result = self.request("resources/templates/list", {})
        if not isinstance(result, Mapping) or not isinstance(
            result.get("resourceTemplates"), list
        ):
            raise McpProtocolError(
                f"malformed resources/templates/list result: {result!r}"
            )
        return dict(result)

    def read_resource(self, uri: str) -> dict[str, Any]:
        result = self.request("resources/read", {"uri": str(uri)})
        if not isinstance(result, Mapping) or not isinstance(result.get("contents"), list):
            raise McpProtocolError(f"malformed resources/read result: {result!r}")
        return dict(result)

    def list_prompts(self) -> dict[str, Any]:
        result = self.request("prompts/list", {})
        if not isinstance(result, Mapping) or not isinstance(result.get("prompts"), list):
            raise McpProtocolError(f"malformed prompts/list result: {result!r}")
        return dict(result)

    def get_prompt(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"name": str(name)}
        if arguments:
            params["arguments"] = dict(arguments)
        result = self.request("prompts/get", params)
        if not isinstance(result, Mapping) or not isinstance(result.get("messages"), list):
            raise McpProtocolError(f"malformed prompts/get result: {result!r}")
        return dict(result)

    def kill(self) -> None:
        """Abandon a session immediately, including a hung initialize."""

        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                pass

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
            self.kill()
            return
        self._process = None

    def __enter__(self) -> "McpStdioSession":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()


def _extract_text(result: Mapping[str, Any]) -> str:
    content = result.get("content") or []
    parts = [str(item.get("text") or "") for item in content if isinstance(item, Mapping)]
    return "".join(parts)


def extract_resource_text(result: Mapping[str, Any]) -> str:
    """Join text bodies from a resources/read contents payload."""

    contents = result.get("contents") or []
    parts = [str(item.get("text") or "") for item in contents if isinstance(item, Mapping)]
    return "".join(parts)


def extract_prompt_text(result: Mapping[str, Any]) -> str:
    """Join text bodies from a prompts/get messages payload."""

    messages = result.get("messages") or []
    parts: list[str] = []
    for item in messages:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if isinstance(content, Mapping):
            parts.append(str(content.get("text") or ""))
        elif isinstance(content, list):
            parts.extend(
                str(block.get("text") or "")
                for block in content
                if isinstance(block, Mapping)
            )
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
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one live MCP session end-to-end and seal it as a digest-chained trace.

    Stages: spawn server -> initialize handshake -> live tools/list -> import
    through the routing layer (explicit mcp provider opt-in) -> require the
    target tool to route executable -> live tools/call -> seal trace.
    ``extra`` is merged into the sealed trace body (digest-bound) so callers
    can bind out-of-band facts — e.g. the external proof's sentinel string —
    into the evidence.
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
    if extra:
        trace_body.update(dict(extra))
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


EXTERNAL_LATEST_POINTER_NAME = "latest-external.json"


def run_live_external_proof(
    *,
    trace_root: Path | None = None,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """Live-tier external proof: fresh actuation against a real third-party MCP server.

    Spawns the official ``@modelcontextprotocol/server-filesystem`` via npx:
    handshake against ``secure-filesystem-server``, live tools/list,
    policy-routed import, a real ``read_file`` call returning a sentinel file
    the server read from disk, durable sealed trace + ``latest-external.json``
    pointer under ``artifacts/mcp-live/``, tamper falsification, and a
    fail-closed check that reading outside the allowed directory is refused by
    the server. Needs network + npx; explicit evidence refresh, not the
    registered proof.
    """

    import shutil

    root = Path(trace_root) if trace_root else REPO_ROOT / DEFAULT_ARTIFACT_DIR
    with tempfile.TemporaryDirectory(prefix="mcp-external-proof-") as tmp:
        sandbox = Path(tmp) / "sandbox"
        sandbox.mkdir()
        sentinel = "blackhole-external-mcp-sentinel"
        sentinel_path = sandbox / "sentinel.txt"
        sentinel_path.write_text(sentinel + "\n", encoding="utf-8")

        command = external_filesystem_server_command(sandbox)
        if command is None:
            return {"ok": False, "error": "npx not available; cannot spawn external MCP server"}

        stamp = utc_now_iso().replace(":", "").replace("-", "")
        out = root / f"external-{stamp}"
        try:
            run = run_live_execution(
                command=command,
                server_name="fs",
                tool_name="read_file",
                arguments={"path": str(sentinel_path)},
                output_dir=out,
                timeout_seconds=timeout_seconds,
                extra={"sentinel": sentinel},
            )
        except McpProtocolError as error:
            return {"ok": False, "error": f"external session failed: {error}"}
        pointer = {
            "schema_version": SCHEMA_VERSION,
            "trace_dir": str(out),
            "trace_digest": run["trace_digest"],
            "recorded_at": utc_now_iso(),
        }
        atomic_write_json(root / EXTERNAL_LATEST_POINTER_NAME, pointer)
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
        with McpStdioSession(command, timeout_seconds=timeout_seconds) as session:
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
        "proof_mode": "live",
        "trace_digest": run.get("trace_digest"),
        "trace_dir": run.get("output_dir"),
        "server_info": server,
        "imported_tool_count": len(run.get("imported_tool_names") or []),
        "external_result_verified": sentinel in run.get("result_text", ""),
        "trace_verified": verify["ok"],
        "tamper_falsified": not tampered["ok"],
        "outside_allowed_dir_refused": outside_refused,
    }


def load_latest_external_trace(trace_root: Path | None = None) -> tuple[Path, dict[str, Any]] | None:
    """Latest durable sealed external trace directory + pointer, or None."""

    root = Path(trace_root) if trace_root else REPO_ROOT / DEFAULT_ARTIFACT_DIR
    pointer_path = root / EXTERNAL_LATEST_POINTER_NAME
    if not pointer_path.is_file():
        return None
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    trace_dir = Path(pointer["trace_dir"])
    if not (trace_dir / "execution.json").is_file():
        # A pointer sealed inside a mission worktree records an absolute path
        # that dies with worktree reclamation. The sealed copy travels with
        # the repository next to the pointer, so fall back to the local
        # directory of the same name; digest binding still gates acceptance.
        local_dir = root / trace_dir.name
        if not (local_dir / "execution.json").is_file():
            return None
        trace_dir = local_dir
    return trace_dir, pointer


def builtin_mcp_live_external_proof() -> dict[str, Any]:
    """Registered proof for ``capability.mcp-live-external`` (hermetic).

    Purely re-verifies the latest durable sealed external-session trace:
    pointer binding, digest chain, and recorded semantics (server is
    ``secure-filesystem-server``, fs read/write tools were imported, the
    recorded sentinel is present in the recorded ``read_file`` result). The
    verifier is falsified with a tampered copy in a throwaway directory, and a
    forged trace must not bind to the pointer. No network, no npx, bounded
    wall-clock. Refresh the underlying evidence with the explicit live tier
    (``run_live_external_proof`` / CLI ``live-external-proof``).
    """

    found = load_latest_external_trace()
    if found is None:
        return {
            "ok": False,
            "error": "no durable sealed external trace: run the live tier to seal one",
            "proof_mode": "hermetic-sealed-verification",
        }
    trace_dir, pointer = found
    trace = json.loads((trace_dir / "execution.json").read_text(encoding="utf-8"))

    pointer_ok = pointer.get("trace_digest") == trace.get("trace_digest")
    verify = verify_execution_trace(trace_dir)
    server = (trace.get("handshake") or {}).get("serverInfo") or {}
    imported = trace.get("imported_tool_names") or []
    sentinel = trace.get("sentinel") or ""
    call = trace.get("call") or {}
    result_text = _extract_text(call.get("result") or {})
    sentinel_verified = bool(sentinel) and sentinel in result_text

    # Tamper falsification in a throwaway directory: an edited recorded
    # result must fail verification, and the forged trace must not bind to
    # the pointer.
    with tempfile.TemporaryDirectory(prefix="mcp-external-tamper-") as tmp:
        clone = Path(tmp) / "tampered"
        clone.mkdir(parents=True, exist_ok=True)
        forged = json.loads(json.dumps(trace))
        forged["call"]["result"]["content"][0]["text"] = "forged"
        atomic_write_json(clone / "execution.json", forged)
        tampered = verify_execution_trace(clone)
        forged_body = {key: value for key, value in forged.items() if key != "trace_digest"}
        pointer_forgery_detected = _digest(forged_body) != pointer.get("trace_digest")

    ok = (
        pointer_ok
        and verify["ok"]
        and sentinel_verified
        and not tampered["ok"]
        and pointer_forgery_detected
        and server.get("name") == "secure-filesystem-server"
        and "fs:read_file" in imported
        and "fs:write_file" in imported
    )
    return {
        "ok": bool(ok),
        "proof_mode": "hermetic-sealed-verification",
        "trace_digest": trace.get("trace_digest"),
        "trace_dir": str(trace_dir),
        "recorded_at": trace.get("recorded_at"),
        "server_info": server,
        "imported_tool_count": len(imported),
        "external_result_verified": sentinel_verified,
        "pointer_binding_ok": pointer_ok,
        "trace_verified": verify["ok"],
        "tamper_falsified": not tampered["ok"],
        "pointer_forgery_detected": pointer_forgery_detected,
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
