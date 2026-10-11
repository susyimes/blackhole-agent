"""Hosted MCP plugin tools become POST /invoke capabilities after opt-in."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

from blackhole_agent.capability_service import build_server
from blackhole_agent.mcp_client import echo_server_command
from blackhole_agent.mcp_plugin_invoke import (
    PLUGIN_ID_PREFIX,
    parse_mcp_plugin_command,
    resolve_mcp_plugin_commands,
)

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

ECHO_ID = f"{PLUGIN_ID_PREFIX}echo"
PROBE_TEXT = "plugin-echo-da345025"


def _ledger_entry(capability_id: str) -> dict:
    return {
        "id": capability_id,
        "name": capability_id,
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


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "text-reverser",
                "name": "text reverser",
                "command": ["python", "tool.py"],
                "requires": ["raw_text"],
                "provides": ["reversed_text"],
                "cases": [
                    {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
                    {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    capabilities = {
        "capability.absorbed-text-reverser": _ledger_entry("capability.absorbed-text-reverser"),
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def _serve(root: Path, **kwargs):
    httpd = build_server(root, port=0, **kwargs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_parse_mcp_plugin_command_json_and_shell() -> None:
    assert parse_mcp_plugin_command('["python","-m","blackhole_agent.mcp_echo_server"]') == [
        "python",
        "-m",
        "blackhole_agent.mcp_echo_server",
    ]
    assert parse_mcp_plugin_command("python -m blackhole_agent.mcp_echo_server")[-1] == (
        "blackhole_agent.mcp_echo_server"
    )


def test_resolve_mcp_plugin_commands_from_env() -> None:
    env = {"BLACKHOLE_MCP_PLUGIN": json.dumps(["python", "-m", "blackhole_agent.mcp_echo_server"])}
    assert resolve_mcp_plugin_commands(env=env) == [
        ["python", "-m", "blackhole_agent.mcp_echo_server"]
    ]
    assert resolve_mcp_plugin_commands(env={}) == []


def test_fail_closed_plane_does_not_list_or_invoke_plugin_tools(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    httpd, base = _serve(root)
    try:
        status, health = _request("GET", f"{base}/health")
        assert status == 200
        assert health["mcp_plugin_invoke"] is False
        assert health["mcp_plugin_count"] == 0
        status, listing = _request("GET", f"{base}/capabilities")
        ids = [item["id"] for item in listing["capabilities"]]
        assert ECHO_ID not in ids
        status, result = _request(
            "POST",
            f"{base}/invoke",
            {"capability_id": ECHO_ID, "input": {"text": PROBE_TEXT}},
        )
        assert status == 404
        assert result["ok"] is False
        status, result = _request(
            "POST",
            f"{base}/invoke",
            {
                "capability_id": "capability.absorbed-text-reverser",
                "input": {"raw_text": PROBE_TEXT},
            },
        )
        assert status == 200
        assert result["output"]["reversed_text"] == PROBE_TEXT[::-1]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_health_advertises_mcp_plugin_sandbox_without_plugin(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    httpd, base = _serve(root)
    try:
        status, health = _request("GET", f"{base}/health")
        assert status == 200
        assert health["mcp_plugin_sandbox"] is True
        assert health["mcp_plugin_invoke"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_sandboxed_plugin_hides_operator_secret_and_repo_cwd(tmp_path: Path, monkeypatch) -> None:
    from blackhole_agent.mcp_plugin_sandbox import (
        CANARY_ENV_KEY,
        sandbox_plugin_command,
    )

    canary = "unit-plugin-sandbox-secret"
    monkeypatch.setenv(CANARY_ENV_KEY, canary)
    root = _fixture_root(tmp_path)
    httpd, base = _serve(root, mcp_plugin_commands=[sandbox_plugin_command()])
    try:
        status, health = _request("GET", f"{base}/health")
        assert status == 200
        assert health["mcp_plugin_sandbox"] is True
        assert health["mcp_plugin_invoke"] is True
        status, echo = _request(
            "POST",
            f"{base}/invoke",
            {"capability_id": ECHO_ID, "input": {"text": PROBE_TEXT}},
        )
        assert status == 200
        assert echo["output"]["text"] == PROBE_TEXT
        status, env_body = _request(
            "POST",
            f"{base}/invoke",
            {"capability_id": f"{PLUGIN_ID_PREFIX}env_probe", "input": {"text": PROBE_TEXT}},
        )
        assert status == 200
        env_payload = json.loads(env_body["output"]["text"])
        assert env_payload["observed_secret"] != canary
        assert env_payload["has_path"] is True
        assert CANARY_ENV_KEY not in env_payload["blackhole_keys"]
        status, write_body = _request(
            "POST",
            f"{base}/invoke",
            {"capability_id": f"{PLUGIN_ID_PREFIX}write_probe", "input": {"text": PROBE_TEXT}},
        )
        assert status == 200
        write_payload = json.loads(write_body["output"]["text"])
        repo_root = Path(__file__).resolve().parents[1]
        assert Path(write_payload["cwd"]).resolve() != repo_root.resolve()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_opted_in_echo_plugin_is_invocable(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    httpd, base = _serve(root, mcp_plugin_commands=[echo_server_command()])
    try:
        status, health = _request("GET", f"{base}/health")
        assert status == 200
        assert health["mcp_plugin_invoke"] is True
        assert health["mcp_plugin_count"] >= 1
        status, listing = _request("GET", f"{base}/capabilities")
        ids = [item["id"] for item in listing["capabilities"]]
        assert ECHO_ID in ids
        echo = next(item for item in listing["capabilities"] if item["id"] == ECHO_ID)
        assert echo["requires"] == ["text"]
        assert echo["provides"] == ["text"]
        status, result = _request(
            "POST",
            f"{base}/invoke",
            {"capability_id": ECHO_ID, "input": {"text": PROBE_TEXT}},
        )
        assert status == 200
        assert result["ok"] is True
        assert result["output"]["text"] == PROBE_TEXT
        assert result["plugin_tool"] == "echo"
        status, result = _request(
            "POST",
            f"{base}/invoke",
            {
                "capability_id": "capability.absorbed-text-reverser",
                "input": {"raw_text": PROBE_TEXT},
            },
        )
        assert status == 200
        assert result["output"]["reversed_text"] == PROBE_TEXT[::-1]
    finally:
        httpd.shutdown()
        httpd.server_close()
