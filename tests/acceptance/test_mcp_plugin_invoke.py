"""Acceptance probe: opted-in MCP plugin tools are POST /invoke capabilities.

GET /capabilities and POST /invoke currently list and run only vendored
absorbed Python tools. A live stdio MCP plugin never appears as an
invocable capability. This probe starts the invocation plane as a
separate OS process and requires:

1. A plane without ``--mcp-plugin`` does not list
   ``capability.mcp-plugin-echo``, POST /invoke of that id is HTTP 404,
   GET /health does not report ``mcp_plugin_invoke`` true, and an
   absorbed sibling still reverses its input.
2. A plane started with ``--mcp-plugin`` pointing at the in-repo echo
   MCP server lists ``capability.mcp-plugin-echo``, POST /invoke with
   ``{"text": ...}`` returns that text in ``output.text``, GET /health
   reports ``mcp_plugin_invoke`` true, and the absorbed sibling still
   reverses its input.

On the pre-mission plane ``--mcp-plugin`` is unknown or ignored, so the
plugin half fails and the probe reports passed=false. Both outcomes
exit 0 with JSON ``passed`` and nonempty ``observed``.
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
from urllib.error import HTTPError

PROBE_TEXT = "plugin-echo-da345025"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
ECHO_ID = "capability.mcp-plugin-echo"
ABSORBED_ID = "capability.absorbed-text-reverser"

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
        ABSORBED_ID: _ledger_entry(ABSORBED_ID, "probe text reverser"),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _request(method: str, url: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, object]:
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


def _ids(listing: object) -> list[str]:
    if not isinstance(listing, dict):
        return []
    items = listing.get("capabilities")
    if not isinstance(items, list):
        return []
    return [str(item.get("id") or "") for item in items if isinstance(item, dict)]


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-plugin-invoke"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scratch = tempfile.TemporaryDirectory(prefix="mcp-plugin-invoke-probe-", ignore_cleanup_errors=True)
    processes: list[subprocess.Popen] = []
    try:
        root = _build_fixture_root(Path(scratch.name))

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
        observed["closed_echo_ok"] = echo_body.get("ok") if isinstance(echo_body, dict) else None
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
            and health.get("mcp_plugin_invoke") is not True
            and listing_status == 200
            and ECHO_ID not in _ids(listing)
            and echo_status == 404
            and absorbed_status == 200
            and isinstance(absorbed_output, dict)
            and absorbed_output.get("reversed_text") == EXPECTED_REVERSE
        )
        observed["closed_ok"] = closed_ok

        plugin_argv = json.dumps([sys.executable, "-u", "-m", "blackhole_agent.mcp_echo_server"])
        plugin = _start_serve(
            root,
            src_root,
            ["--host", "127.0.0.1", "--mcp-plugin", plugin_argv],
        )
        processes.append(plugin)
        plugin_sink = _wait_json_line(plugin)
        observed["plugin_ready"] = plugin_sink.get("payload")
        observed["plugin_line"] = plugin_sink.get("line")
        observed["plugin_error"] = plugin_sink.get("error")
        plugin_payload = plugin_sink.get("payload")
        if not isinstance(plugin_payload, dict) or not plugin_payload.get("listening"):
            err = plugin.stderr.read() if plugin.stderr else ""
            observed["plugin_stderr"] = err[-2000:] if isinstance(err, str) else ""
            observed["plugin_returncode"] = plugin.poll()
            return {"passed": False, "observed": observed}
        plugin_base = f"http://127.0.0.1:{int(plugin_payload['listening'])}"
        phealth_status, phealth = _request("GET", f"{plugin_base}/health")
        observed["plugin_health_status"] = phealth_status
        observed["plugin_health"] = phealth
        plisting_status, plisting = _request("GET", f"{plugin_base}/capabilities")
        observed["plugin_listing_status"] = plisting_status
        observed["plugin_ids"] = _ids(plisting)
        pecho_status, pecho_body = _request(
            "POST",
            f"{plugin_base}/invoke",
            {"capability_id": ECHO_ID, "input": {"text": PROBE_TEXT}},
        )
        pecho_output = pecho_body.get("output") if isinstance(pecho_body, dict) else None
        observed["plugin_echo_status"] = pecho_status
        observed["plugin_echo"] = pecho_body
        pabs_status, pabs_body = _request(
            "POST",
            f"{plugin_base}/invoke",
            {"capability_id": ABSORBED_ID, "input": {"raw_text": PROBE_TEXT}},
        )
        pabs_output = pabs_body.get("output") if isinstance(pabs_body, dict) else None
        observed["plugin_absorbed_status"] = pabs_status
        observed["plugin_absorbed"] = pabs_output
        plugin_ok = (
            phealth_status == 200
            and isinstance(phealth, dict)
            and phealth.get("mcp_plugin_invoke") is True
            and int(phealth.get("mcp_plugin_count") or 0) >= 1
            and plisting_status == 200
            and ECHO_ID in _ids(plisting)
            and pecho_status == 200
            and isinstance(pecho_body, dict)
            and pecho_body.get("ok") is True
            and isinstance(pecho_output, dict)
            and pecho_output.get("text") == PROBE_TEXT
            and pabs_status == 200
            and isinstance(pabs_output, dict)
            and pabs_output.get("reversed_text") == EXPECTED_REVERSE
        )
        observed["plugin_ok"] = plugin_ok
        passed = bool(closed_ok and plugin_ok)
        return {"passed": passed, "observed": observed}
    except Exception as exc:
        observed["error"] = type(exc).__name__
        observed["detail"] = str(exc)
        return {"passed": False, "observed": observed}
    finally:
        for process in processes:
            _stop(process)
        scratch.cleanup()


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
