"""Grok's browser-use plugin must answer MCP initialize.

Harvested kernel stderr records ``MCP server 'browser-use' handshake failed:
connection closed: initialize response``. The plugin command is
``uvx --python 3.12 browser-use@latest --cli-mcp`` while the controller
process exports ``PYTHONHOME`` pointing at CPython 3.13. That prefix makes
the 3.12 interpreter import 3.13 ``typing.py`` and crash on ``NoDefault``
before any JSON-RPC result is written.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path


_PLUGIN_COMMAND = ("uvx", "--python", "3.12", "browser-use@latest", "--cli-mcp")
_HANDSHAKE_TIMEOUT_SECONDS = 50


def _named(env: dict | None, name: str) -> str:
    if not isinstance(env, dict):
        return ""
    folded = name.casefold()
    for key, value in env.items():
        if str(key).casefold() == folded:
            return str(value or "").strip()
    return ""


def _foreign_prefix() -> str:
    current = _named(dict(os.environ), "PYTHONHOME")
    if current and Path(current).is_dir():
        return current
    appdata = os.environ.get("APPDATA") or ""
    if not appdata:
        return ""
    candidate = Path(appdata) / "uv" / "python" / "cpython-3.13-windows-x86_64-none"
    if (candidate / "Lib" / "typing.py").is_file():
        return str(candidate)
    return ""


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _stdio_initialize(env: dict[str, str]) -> dict[str, object]:
    try:
        proc = subprocess.Popen(
            list(_PLUGIN_COMMAND),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError as exc:
        return {"stderr": str(exc), "response": None}

    stderr_box: dict[str, bytes] = {}

    def _drain() -> None:
        assert proc.stderr is not None
        stderr_box["data"] = proc.stderr.read()

    drain = threading.Thread(target=_drain, daemon=True)
    drain.start()
    line_box: dict[str, bytes] = {}

    def _read_line() -> None:
        assert proc.stdout is not None
        line_box["line"] = proc.stdout.readline()

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "blackhole-browser-use-probe", "version": "0"},
        },
    }
    response: dict[str, object] | None = None
    try:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(request) + "\n").encode("utf-8"))
        proc.stdin.flush()
        reader = threading.Thread(target=_read_line, daemon=True)
        reader.start()
        reader.join(_HANDSHAKE_TIMEOUT_SECONDS)
        raw = line_box.get("line")
        if raw:
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                response = payload
    finally:
        _stop(proc)
        drain.join(2)
    stderr = stderr_box.get("data", b"").decode("utf-8", errors="replace")
    return {"stderr": stderr[-500:], "response": response}


def observe() -> tuple[bool, dict[str, object]]:
    from blackhole_agent.kernels.grok_cli import grok_launch_environment

    prefix = _foreign_prefix()
    source = {str(key): str(value) for key, value in os.environ.items() if value is not None}
    if prefix:
        source["PYTHONHOME"] = prefix
    launched = grok_launch_environment(source)
    forwarded = _named(launched, "PYTHONHOME")
    outcome = _stdio_initialize(launched)
    response = outcome.get("response")
    result: dict[str, object] = {}
    if isinstance(response, dict) and isinstance(response.get("result"), dict):
        result = response["result"]
    version = str(result.get("protocolVersion") or result.get("protocol_version") or "")
    stderr = str(outcome.get("stderr") or "")
    import_crash = "NoDefault" in stderr or "ImportError" in stderr
    passed = bool(prefix) and not forwarded and bool(version) and not import_crash
    observed = {
        "plugin_command": " ".join(_PLUGIN_COMMAND),
        "foreign_prefix_present": bool(prefix),
        "pythonhome_forwarded": forwarded,
        "protocol_version": version,
        "import_crash": import_crash,
        "stderr_tail": stderr[-240:],
    }
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - probe must exit 0 with an unmet outcome
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
