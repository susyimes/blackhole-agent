"""Acceptance probe: hosted MCP plugins cannot inherit secrets or write the repo.

Opted-in stdio plugins previously started via bare Popen with the plane
environment and a writable repository cwd. This probe starts the invocation
plane as a separate OS process with a canary secret in its environment and
requires:

1. GET /health reports mcp_plugin_sandbox true (policy is on even without a
   plugin); POST /invoke of capability.mcp-plugin-echo is HTTP 404; an
   absorbed sibling still reverses.
2. A plane started with --mcp-plugin pointing at the in-repo sandbox MCP
   fixture lists echo/env_probe/write_probe. POST /invoke of echo returns
   the posted text. POST /invoke of env_probe does not echo the canary
   secret and still sees PATH. POST /invoke of write_probe reports a cwd
   that is not the repository and does not leave a marker in the repo.
   The absorbed sibling still reverses.

On the pre-mission plane plugins inherit the canary and run with cwd equal
to the repository, so the probe reports passed=false. Both outcomes exit 0
with JSON passed and nonempty observed.
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

PROBE_TEXT = "plugin-sandbox-20d13648"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
ECHO_ID = "capability.mcp-plugin-echo"
ENV_ID = "capability.mcp-plugin-env_probe"
WRITE_ID = "capability.mcp-plugin-write_probe"
ABSORBED_ID = "capability.absorbed-text-reverser"
CANARY_KEY = "BH_PROBE_PLUGIN_SECRET"
CANARY_VALUE = "plugin-sandbox-canary-20d13648"
WRITE_MARKER = "plugin-sandbox-pwned-20d13648.txt"

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
    env[CANARY_KEY] = CANARY_VALUE
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


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "mcp-plugin-sandbox"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    repo_root = Path(service.__file__).resolve().parents[2]
    observed["src_root"] = str(src_root)
    observed["repo_root"] = str(repo_root)
    marker_path = repo_root / WRITE_MARKER
    scratch = tempfile.TemporaryDirectory(prefix="mcp-plugin-sandbox-probe-", ignore_cleanup_errors=True)
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
            and health.get("mcp_plugin_sandbox") is True
            and health.get("mcp_plugin_invoke") is not True
            and listing_status == 200
            and ECHO_ID not in _ids(listing)
            and echo_status == 404
            and absorbed_status == 200
            and isinstance(absorbed_output, dict)
            and absorbed_output.get("reversed_text") == EXPECTED_REVERSE
        )
        observed["closed_ok"] = closed_ok

        plugin_argv = json.dumps(
            [sys.executable, "-u", "-m", "blackhole_agent.mcp_plugin_sandbox"]
        )
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

        penv_status, penv_body = _request(
            "POST",
            f"{plugin_base}/invoke",
            {"capability_id": ENV_ID, "input": {"text": PROBE_TEXT}},
        )
        env_payload = _json_text(penv_body)
        observed["plugin_env_status"] = penv_status
        observed["plugin_env"] = env_payload

        pwrite_status, pwrite_body = _request(
            "POST",
            f"{plugin_base}/invoke",
            {"capability_id": WRITE_ID, "input": {"text": PROBE_TEXT}},
        )
        write_payload = _json_text(pwrite_body)
        observed["plugin_write_status"] = pwrite_status
        observed["plugin_write"] = write_payload
        write_cwd = str(write_payload.get("cwd") or "")
        try:
            cwd_is_repo = bool(write_cwd) and Path(write_cwd).resolve() == repo_root.resolve()
        except OSError:
            cwd_is_repo = False
        observed["write_cwd_is_repo"] = cwd_is_repo
        observed["repo_marker_exists"] = marker_path.is_file()

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
            and phealth.get("mcp_plugin_sandbox") is True
            and phealth.get("mcp_plugin_invoke") is True
            and int(phealth.get("mcp_plugin_count") or 0) >= 3
            and plisting_status == 200
            and ECHO_ID in _ids(plisting)
            and ENV_ID in _ids(plisting)
            and WRITE_ID in _ids(plisting)
            and pecho_status == 200
            and isinstance(pecho_body, dict)
            and pecho_body.get("ok") is True
            and isinstance(pecho_output, dict)
            and pecho_output.get("text") == PROBE_TEXT
            and penv_status == 200
            and env_payload.get("observed_secret") != CANARY_VALUE
            and env_payload.get("has_path") is True
            and CANARY_KEY not in list(env_payload.get("blackhole_keys") or [])
            and pwrite_status == 200
            and write_cwd != ""
            and not cwd_is_repo
            and not marker_path.is_file()
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
        if marker_path.is_file():
            try:
                marker_path.unlink()
            except OSError:
                pass
        scratch.cleanup()


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
