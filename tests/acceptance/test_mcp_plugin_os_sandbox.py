"""Acceptance probe: hosted MCP plugins cannot read host files or open TCP.

Hosted stdio plugins already run with a scrubbed environment, isolated cwd,
and a resource job, but they still started outside the OS filesystem
sandbox. This probe starts the invocation plane as a separate OS process
and requires:

1. GET /health reports mcp_plugin_os_sandbox true even without a plugin;
   POST /invoke of a plugin id is HTTP 404; an absorbed sibling still
   reverses.
2. A plane started with --mcp-plugin pointing at the in-repo sandbox MCP
   fixture: POST /invoke of echo returns the posted text; POST /invoke of
   read_probe against an absolute host canary does not return those bytes;
   POST /invoke of net_probe targeting a loopback listener does not
   deliver the exfil payload; the absorbed sibling still reverses.

On the pre-mission plane plugins read the canary and the listener receives
the payload, so the probe reports passed=false. Both outcomes exit 0 with
JSON passed and nonempty observed.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

PROBE_TEXT = "plugin-os-sandbox-b279903c"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
ECHO_ID = "capability.mcp-plugin-echo"
READ_ID = "capability.mcp-plugin-read_probe"
NET_ID = "capability.mcp-plugin-net_probe"
ABSORBED_ID = "capability.absorbed-text-reverser"
CANARY_VALUE = "plugin-os-sandbox-canary-b279903c"
EXFIL_PAYLOAD = "plugin-os-exfil-b279903c"

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_PLUGIN = r'''
import json, os, socket, sys
from pathlib import Path

PROTOCOL_VERSION = "2025-03-26"
TOOLS = [
    {
        "name": "echo",
        "description": "Return the supplied text unchanged.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "read_probe",
        "description": "Try to read an absolute host path.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "net_probe",
        "description": "Try to TCP-connect and send a payload.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "payload": {"type": "string"},
            },
            "required": ["host", "port", "payload"],
        },
    },
]


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def result(mid, payload):
    send({"jsonrpc": "2.0", "id": mid, "result": payload})


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        result(
            mid,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "os-sandbox-probe", "version": "1"},
            },
        )
        return
    if method == "notifications/initialized":
        return
    if method == "tools/list":
        result(mid, {"tools": TOOLS})
        return
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "echo":
            result(
                mid,
                {
                    "content": [{"type": "text", "text": str(args.get("text") or "")}],
                    "isError": False,
                },
            )
            return
        if name == "read_probe":
            target = Path(str(args.get("path") or ""))
            payload = {"path": str(target), "readable": False, "text": "", "error": ""}
            try:
                payload["text"] = target.read_text(encoding="utf-8")
                payload["readable"] = True
            except Exception as exc:
                payload["error"] = type(exc).__name__
            result(
                mid,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
                    "isError": False,
                },
            )
            return
        if name == "net_probe":
            payload = {"connected": False, "error": ""}
            try:
                port = int(args.get("port"))
                with socket.create_connection((str(args.get("host") or ""), port), timeout=1.5) as sock:
                    sock.sendall(str(args.get("payload") or "").encode("utf-8"))
                    payload["connected"] = True
            except Exception as exc:
                payload["error"] = type(exc).__name__
            result(
                mid,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
                    "isError": False,
                },
            )
            return
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown tool"}})
        return
    if mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": str(method)}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        handle(json.loads(line))


if __name__ == "__main__":
    main()
'''


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
        ABSORBED_ID: _ledger_entry(ABSORBED_ID, "probe text reverser"),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _request(method: str, url: str, payload: dict | None = None, timeout: int = 45) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
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
    env.pop("BLACKHOLE_MCP_PLUGIN", None)
    return env


def _start_serve(root: Path, src_root: Path, extra_args: list[str]) -> subprocess.Popen:
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


def _wait_json_line(process: subprocess.Popen, timeout: float = 90.0) -> dict[str, object]:
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


def _ids(listing: object) -> list[str]:
    if not isinstance(listing, dict):
        return []
    items = listing.get("capabilities")
    if not isinstance(items, list):
        return []
    return [str(item.get("id") or "") for item in items if isinstance(item, dict)]


def _json_text(body: object) -> dict[str, object]:
    if not isinstance(body, dict):
        return {}
    output = body.get("output")
    if not isinstance(output, dict):
        return {}
    raw = output.get("text")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _raw_text(body: object) -> str:
    if not isinstance(body, dict):
        return ""
    output = body.get("output")
    if not isinstance(output, dict):
        return json.dumps(body)
    raw = output.get("text")
    return str(raw or "") + json.dumps(body)


class _LoopbackCanary:
    def __init__(self) -> None:
        self.received: list[str] = []
        self.port = 0
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(5)

    def _run(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        self.port = int(srv.getsockname()[1])
        self._ready.set()
        srv.settimeout(4)
        try:
            conn, _ = srv.accept()
            try:
                data = conn.recv(1024)
                self.received.append(data.decode("utf-8", "replace"))
            finally:
                conn.close()
        except OSError:
            pass
        finally:
            srv.close()

    def join(self) -> None:
        self._thread.join(timeout=5)


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-plugin-os-sandbox"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    observed["src_root"] = str(src_root)
    scratch = tempfile.TemporaryDirectory(prefix="mcp-plugin-os-sandbox-probe-", ignore_cleanup_errors=True)
    processes: list[subprocess.Popen] = []
    try:
        base = Path(scratch.name)
        root = _build_fixture_root(base)
        plugin_dir = base / "plugin"
        plugin_dir.mkdir()
        plugin_py = plugin_dir / "plugin.py"
        plugin_py.write_text(_PLUGIN, encoding="utf-8")
        secret_dir = base / "secret"
        secret_dir.mkdir()
        canary = secret_dir / "host-secret.txt"
        canary.write_text(CANARY_VALUE, encoding="utf-8")

        closed = _start_serve(root, src_root, ["--host", "127.0.0.1"])
        processes.append(closed)
        closed_sink = _wait_json_line(closed)
        observed["closed_ready"] = closed_sink.get("payload")
        closed_payload = closed_sink.get("payload")
        if not isinstance(closed_payload, dict) or not closed_payload.get("listening"):
            err = closed.stderr.read() if closed.stderr else ""
            observed["closed_error"] = closed_sink.get("error")
            observed["closed_stderr"] = err[-2000:] if isinstance(err, str) else ""
            return {"passed": False, "observed": observed}
        closed_base = f"http://127.0.0.1:{int(closed_payload['listening'])}"
        health_status, health = _request("GET", f"{closed_base}/health")
        observed["closed_health_status"] = health_status
        observed["closed_health"] = health
        listing_status, listing = _request("GET", f"{closed_base}/capabilities")
        observed["closed_listing_status"] = listing_status
        observed["closed_ids"] = _ids(listing)
        echo_status, echo_body = _request(
            "POST",
            f"{closed_base}/invoke",
            {"capability_id": ECHO_ID, "input": {"text": PROBE_TEXT}},
        )
        observed["closed_echo_status"] = echo_status
        absorbed_status, absorbed_body = _request(
            "POST",
            f"{closed_base}/invoke",
            {"capability_id": ABSORBED_ID, "input": {"raw_text": PROBE_TEXT}},
        )
        absorbed_output = absorbed_body.get("output") if isinstance(absorbed_body, dict) else None
        observed["closed_absorbed_status"] = absorbed_status
        observed["closed_absorbed"] = absorbed_output
        closed_ok = (
            health_status == 200
            and isinstance(health, dict)
            and health.get("mcp_plugin_os_sandbox") is True
            and health.get("mcp_plugin_invoke") is not True
            and listing_status == 200
            and ECHO_ID not in _ids(listing)
            and echo_status == 404
            and absorbed_status == 200
            and isinstance(absorbed_output, dict)
            and absorbed_output.get("reversed_text") == EXPECTED_REVERSE
        )
        observed["closed_ok"] = closed_ok

        listener = _LoopbackCanary()
        listener.start()
        observed["listener_port"] = listener.port
        plugin_argv = json.dumps([sys.executable, "-u", str(plugin_py)])
        opened = _start_serve(
            root,
            src_root,
            ["--host", "127.0.0.1", "--mcp-plugin", plugin_argv],
        )
        processes.append(opened)
        opened_sink = _wait_json_line(opened)
        observed["opened_ready"] = opened_sink.get("payload")
        opened_payload = opened_sink.get("payload")
        if not isinstance(opened_payload, dict) or not opened_payload.get("listening"):
            err = opened.stderr.read() if opened.stderr else ""
            observed["opened_error"] = opened_sink.get("error")
            observed["opened_stderr"] = err[-4000:] if isinstance(err, str) else ""
            observed["opened_line"] = opened_sink.get("line")
            return {"passed": False, "observed": observed}
        opened_base = f"http://127.0.0.1:{int(opened_payload['listening'])}"
        open_health_status, open_health = _request("GET", f"{opened_base}/health")
        observed["opened_health_status"] = open_health_status
        observed["opened_health"] = open_health
        echo_status, echo_body = _request(
            "POST",
            f"{opened_base}/invoke",
            {"capability_id": ECHO_ID, "input": {"text": PROBE_TEXT}},
        )
        observed["echo_status"] = echo_status
        observed["echo"] = echo_body
        read_status, read_body = _request(
            "POST",
            f"{opened_base}/invoke",
            {"capability_id": READ_ID, "input": {"path": str(canary)}},
        )
        observed["read_status"] = read_status
        observed["read"] = read_body
        read_payload = _json_text(read_body)
        observed["read_payload"] = read_payload
        net_status, net_body = _request(
            "POST",
            f"{opened_base}/invoke",
            {
                "capability_id": NET_ID,
                "input": {
                    "host": "127.0.0.1",
                    "port": listener.port,
                    "payload": EXFIL_PAYLOAD,
                },
            },
            timeout=20,
        )
        observed["net_status"] = net_status
        observed["net"] = net_body
        net_payload = _json_text(net_body)
        observed["net_payload"] = net_payload
        listener.join()
        observed["listener_received"] = list(listener.received)
        sibling_status, sibling_body = _request(
            "POST",
            f"{opened_base}/invoke",
            {"capability_id": ABSORBED_ID, "input": {"raw_text": PROBE_TEXT}},
        )
        sibling_output = sibling_body.get("output") if isinstance(sibling_body, dict) else None
        observed["sibling_status"] = sibling_status
        observed["sibling"] = sibling_output

        echo_ok = (
            echo_status == 200
            and isinstance(echo_body, dict)
            and isinstance(echo_body.get("output"), dict)
            and echo_body["output"].get("text") == PROBE_TEXT
        )
        read_blocked = (
            read_status == 200
            and read_payload.get("readable") is False
            and CANARY_VALUE not in _raw_text(read_body)
        )
        net_blocked = EXFIL_PAYLOAD not in listener.received
        sibling_ok = (
            sibling_status == 200
            and isinstance(sibling_output, dict)
            and sibling_output.get("reversed_text") == EXPECTED_REVERSE
        )
        opened_health_ok = (
            open_health_status == 200
            and isinstance(open_health, dict)
            and open_health.get("mcp_plugin_os_sandbox") is True
            and open_health.get("mcp_plugin_invoke") is True
        )
        observed["checks"] = {
            "closed_ok": closed_ok,
            "opened_health_ok": opened_health_ok,
            "echo_ok": echo_ok,
            "read_blocked": read_blocked,
            "net_blocked": net_blocked,
            "sibling_ok": sibling_ok,
        }
        return {
            "passed": bool(
                closed_ok
                and opened_health_ok
                and echo_ok
                and read_blocked
                and net_blocked
                and sibling_ok
            ),
            "observed": observed,
        }
    finally:
        for process in processes:
            _stop(process)
        scratch.cleanup()


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
