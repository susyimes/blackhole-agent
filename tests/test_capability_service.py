"""Unit tests for the live capability invocation plane."""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError
from urllib.parse import urlparse

import pytest

from blackhole_agent.capability_service import (
    BindPolicyError,
    HOST_NOT_ALLOWED,
    ORIGIN_NOT_ALLOWED,
    TlsConfigError,
    build_server,
    capability_listing,
    evaluate_contract_request,
    evaluate_request_identity,
    host_is_loopback,
    hostname_is_permitted,
    invoke_capability,
    load_invocable_capabilities,
    origin_is_permitted,
    parse_authority,
    parse_solve_dry_run,
    plan_goal_program,
    prefer_solve_preview,
    record_resource_quarantine,
    resolve_solve_dry_run,
    resolve_tls_files,
    serve,
    solve_goal_request,
    InvocationError,
)

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_FAILING_TOOL = "import sys\nsys.exit(3)\n"

_CHAIN_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'loud_text': state['reversed_text'].upper()}))\n"
)

_ENV_ECHO_TOOL = (
    "import json, os, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({\n"
    "    'reversed_text': state['raw_text'][::-1],\n"
    "    'seen_probe_keys': sorted(k for k in os.environ if k.startswith('BH_PROBE_')),\n"
    "    'has_path': bool(os.environ.get('PATH')),\n"
    "}))\n"
)


def _write_env_echo_tool(root: Path) -> None:
    _write_tool(
        root,
        "env-echo",
        _ENV_ECHO_TOOL,
        requires=["raw_text"],
        provides=["reversed_text", "seen_probe_keys", "has_path"],
    )
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["capabilities"]["capability.absorbed-env-echo"] = _ledger_entry(
        "capability.absorbed-env-echo"
    )
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")


def _write_tool(
    root: Path,
    slug: str,
    tool_source: str = _TOOL,
    *,
    requires: list[str] | None = None,
    provides: list[str] | None = None,
) -> None:
    requires = requires or ["raw_text"]
    provides = provides or ["reversed_text"]
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(tool_source, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": slug,
        "name": f"fixture {slug}",
        "command": ["python", "tool.py"],
        "requires": requires,
        "provides": provides,
        "cases": [
            {
                "input": {key: value for key in requires},
                "expect": {key: "x" for key in provides},
            }
            for value in ("ab", "cd")
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write_chain_tool(root: Path) -> None:
    _write_tool(
        root,
        "loud-shouter",
        _CHAIN_TOOL,
        requires=["reversed_text"],
        provides=["loud_text"],
    )
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["capabilities"]["capability.absorbed-loud-shouter"] = _ledger_entry(
        "capability.absorbed-loud-shouter"
    )
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")


def _ledger_entry(capability_id: str, *, proved: bool = True) -> dict:
    return {
        "id": capability_id,
        "name": capability_id,
        "description": f"fixture {capability_id}",
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z" if proved else None,
        "last_proof_exit_code": 0 if proved else 1,
    }


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _write_tool(root, "text-reverser")
    _write_tool(root, "snake-case", requires=["raw_text"], provides=["snake_text"])
    _write_tool(
        root, "broken-tool", _FAILING_TOOL, requires=["raw_text"], provides=["broken_text"]
    )
    capabilities = {
        "capability.absorbed-text-reverser": _ledger_entry("capability.absorbed-text-reverser"),
        "capability.absorbed-snake-case": _ledger_entry("capability.absorbed-snake-case"),
        "capability.absorbed-broken-tool": _ledger_entry("capability.absorbed-broken-tool"),
        "capability.absorbed-unproved": _ledger_entry("capability.absorbed-unproved", proved=False),
        "repo.import-health": _ledger_entry("repo.import-health"),
    }
    (root / "capabilities").mkdir(exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    status, body, _captured = _request_full(method, url, payload, headers=headers)
    return status, body


def _request_full(
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            captured = {key.lower(): value for key, value in response.headers.items()}
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}, captured
    except HTTPError as exc:
        captured = {key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])}
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return exc.code, body, captured


@pytest.fixture()
def server(tmp_path: Path):
    root = _fixture_root(tmp_path)
    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield root, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=10)


def test_listing_only_exposes_proved_absorbed_capabilities(server) -> None:
    _, base = server
    status, listing = _request("GET", f"{base}/capabilities")
    assert status == 200
    ids = [item["id"] for item in listing["capabilities"]]
    assert ids == [
        "capability.absorbed-broken-tool",
        "capability.absorbed-snake-case",
        "capability.absorbed-text-reverser",
    ]
    assert listing["count"] == 3
    assert listing["listing_digest"]
    reverser = listing["capabilities"][2]
    assert reverser["requires"] == ["raw_text"]
    assert reverser["provides"] == ["reversed_text"]
    assert "command" not in reverser and "tool_root" not in reverser


def test_invoke_executes_vendored_tool(server) -> None:
    _, base = server
    status, result = _request(
        "POST",
        f"{base}/invoke",
        {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": "blackhole"}},
    )
    assert status == 200
    assert result["ok"] is True
    assert result["output"] == {"reversed_text": "elohkcalb"}
    assert result["response_digest"]


def test_invoke_refuses_unknown_unproved_and_non_absorbed(server) -> None:
    _, base = server
    for capability_id in (
        "capability.absorbed-does-not-exist",
        "capability.absorbed-unproved",
        "repo.import-health",
    ):
        status, result = _request(
            "POST", f"{base}/invoke", {"capability_id": capability_id, "input": {}}
        )
        assert status == 404, capability_id
        assert result["ok"] is False


def test_invoke_validates_input_keys_strictly(server) -> None:
    _, base = server
    for payload in (
        {"capability_id": "capability.absorbed-text-reverser", "input": {}},
        {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": "a", "x": 1}},
        {"capability_id": "capability.absorbed-text-reverser", "input": "raw"},
        {"capability_id": "", "input": {"raw_text": "a"}},
    ):
        status, result = _request("POST", f"{base}/invoke", payload)
        assert status in (400, 422), payload
        assert result["ok"] is False


def test_invoke_reports_tool_failure(server) -> None:
    _, base = server
    status, result = _request(
        "POST",
        f"{base}/invoke",
        {"capability_id": "capability.absorbed-broken-tool", "input": {"raw_text": "a"}},
    )
    assert status == 502
    assert result["ok"] is False
    assert "exited 3" in result["error"]


def test_unknown_paths_and_health(server) -> None:
    _, base = server
    status, health = _request("GET", f"{base}/health")
    assert status == 200 and health["ok"] is True
    assert health["vendored_tree_readonly"] is True
    assert health["mcp_completions"] is True
    assert health["mcp_resource_subscribe"] is True
    assert health["mcp_logging"] is True
    assert health["non_loopback_requires_token"] is True
    assert health["loopback_host_origin"] is True
    assert health["tls"] is False
    assert health["mcp_plugin_invoke"] is False
    assert health["mcp_plugin_count"] == 0
    assert int(health["max_scratch_bytes"]) > 0
    assert health["http_connection_limits"] is True
    assert int(health["http_request_timeout_seconds"]) > 0
    assert int(health["max_http_connections"]) > 0
    assert health["bundle_import"] is False
    assert health["oauth_protected_resource"] is False
    assert health["oauth_authorize_consent"] is False
    status, result = _request("GET", f"{base}/nope")
    assert status == 404 and result["ok"] is False
    status, result = _request("POST", f"{base}/capabilities", {"x": 1})
    assert status == 404


def test_host_is_loopback_classifies_bind_targets() -> None:
    assert host_is_loopback("127.0.0.1") is True
    assert host_is_loopback("::1") is True
    assert host_is_loopback("[::1]") is True
    assert host_is_loopback("localhost") is True
    assert host_is_loopback("0.0.0.0") is False
    assert host_is_loopback("::") is False
    assert host_is_loopback("") is False
    assert host_is_loopback("*") is False
    assert host_is_loopback("192.168.1.9") is False
    assert host_is_loopback("example.internal") is False


def test_parse_authority_and_identity_helpers() -> None:
    assert parse_authority("127.0.0.1:8080") == ("127.0.0.1", 8080)
    assert parse_authority("[::1]:9") == ("::1", 9)
    assert parse_authority("localhost") == ("localhost", None)
    assert hostname_is_permitted("127.0.0.1", bind_host="0.0.0.0", local_addr="127.0.0.1") is True
    assert hostname_is_permitted("evil.example", bind_host="127.0.0.1", local_addr="127.0.0.1") is False
    assert hostname_is_permitted("192.168.1.9", bind_host="0.0.0.0", local_addr="192.168.1.9") is True
    assert origin_is_permitted(
        "http://127.0.0.1:8765",
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    ) is True
    assert origin_is_permitted(
        "http://evil.example",
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    ) is False
    assert origin_is_permitted(
        "http://127.0.0.1:9",
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    ) is False
    missing = evaluate_request_identity(
        {},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    )
    assert missing is not None and missing[0] == 400 and missing[1]["error"] == HOST_NOT_ALLOWED
    rebound = evaluate_request_identity(
        {"Host": "evil.example"},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    )
    assert rebound is not None and rebound[0] == 400 and rebound[1]["error"] == HOST_NOT_ALLOWED
    csrf = evaluate_request_identity(
        {"Host": "127.0.0.1:8765", "Origin": "http://evil.example"},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    )
    assert csrf is not None and csrf[0] == 403 and csrf[1]["error"] == ORIGIN_NOT_ALLOWED
    ok = evaluate_request_identity(
        {"Host": "127.0.0.1:8765"},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    )
    assert ok is None
    same_origin = evaluate_request_identity(
        {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    )
    assert same_origin is None
    inspector = evaluate_request_identity(
        {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:6274"},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
        allow_loopback_oauth_origin=True,
    )
    assert inspector is None
    inspector_blocked = evaluate_request_identity(
        {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:6274"},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
    )
    assert inspector_blocked is not None and inspector_blocked[1]["error"] == ORIGIN_NOT_ALLOWED
    evil_oauth = evaluate_request_identity(
        {"Host": "127.0.0.1:8765", "Origin": "http://evil.example"},
        bind_host="127.0.0.1",
        local_addr="127.0.0.1",
        listen_port=8765,
        allow_loopback_oauth_origin=True,
    )
    assert evil_oauth is not None and evil_oauth[1]["error"] == ORIGIN_NOT_ALLOWED


def _raw_http(
    method: str,
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port, timeout=30)
    extra = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        extra.setdefault("Content-Type", "application/json")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    try:
        conn.request(method, path, body=body, headers=extra)
        response = conn.getresponse()
        raw = response.read()
        try:
            parsed_body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            parsed_body = {"raw": raw.decode("utf-8", errors="replace")}
        return response.status, parsed_body if isinstance(parsed_body, dict) else {"raw": parsed_body}
    finally:
        conn.close()


def test_invoke_rejects_rebinding_host_and_foreign_origin(server) -> None:
    _, base = server
    port = int(urlparse(base).port)
    payload = {
        "capability_id": "capability.absorbed-text-reverser",
        "input": {"raw_text": "rebinding"},
    }
    status, body = _raw_http(
        "POST",
        f"{base}/invoke",
        payload,
        headers={"Host": "evil.example"},
    )
    assert status == 400
    assert body["ok"] is False
    assert body["error"] == HOST_NOT_ALLOWED
    assert "reversed_text" not in json.dumps(body)
    status, body = _raw_http(
        "POST",
        f"{base}/invoke",
        payload,
        headers={"Origin": "http://evil.example"},
    )
    assert status == 403
    assert body["ok"] is False
    assert body["error"] == ORIGIN_NOT_ALLOWED
    status, body = _raw_http(
        "POST",
        f"{base}/invoke",
        payload,
        headers={"Origin": f"http://127.0.0.1:{port}"},
    )
    assert status == 200
    assert body["ok"] is True
    assert body["output"]["reversed_text"] == "rebinding"[::-1]


def test_build_server_refuses_open_non_loopback_bind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BLACKHOLE_INVOCATION_TOKEN", raising=False)
    root = _fixture_root(tmp_path)
    with pytest.raises(BindPolicyError) as exc:
        build_server(root, host="0.0.0.0", port=0)
    assert exc.value.payload["error"] == "bind_requires_token"
    assert exc.value.payload["ok"] is False
    httpd = build_server(root, host="0.0.0.0", port=0, token="lan-token-0788e9e0")
    try:
        assert httpd.server_address[1] > 0
    finally:
        httpd.server_close()


def test_serve_prints_bind_requires_token_without_listening(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BLACKHOLE_INVOCATION_TOKEN", raising=False)
    root = _fixture_root(tmp_path)
    code = serve(root, host="0.0.0.0", port=0)
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "bind_requires_token"
    assert payload["host"] == "0.0.0.0"


def _tls_fixture_pair(directory: Path) -> tuple[Path, Path]:
    probe = Path(__file__).resolve().parent / "acceptance" / "test_invocation_tls.py"
    namespace: dict[str, object] = {"__name__": "tls_probe_constants"}
    exec(compile(probe.read_text(encoding="utf-8"), str(probe), "exec"), namespace)
    cert = directory / "tls-cert.pem"
    key = directory / "tls-key.pem"
    cert.write_text(str(namespace["TLS_CERT_PEM"]), encoding="ascii")
    key.write_text(str(namespace["TLS_KEY_PEM"]), encoding="ascii")
    return cert, key


def _https_request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    timeout: int = 15,
) -> tuple[int | None, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    ctx = ssl._create_unverified_context()
    try:
        with urlrequest.urlopen(req, timeout=timeout, context=ctx) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return exc.code, None
    except Exception:
        return None, None


def test_resolve_tls_files_omitted_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BLACKHOLE_TLS_CERT", raising=False)
    monkeypatch.delenv("BLACKHOLE_TLS_KEY", raising=False)
    assert resolve_tls_files() is None
    cert, key = _tls_fixture_pair(tmp_path)
    with pytest.raises(TlsConfigError) as only_cert:
        resolve_tls_files(cert=cert)
    assert only_cert.value.payload["error"] == "tls_requires_cert_and_key"
    with pytest.raises(TlsConfigError) as missing:
        resolve_tls_files(cert=tmp_path / "missing.pem", key=key)
    assert missing.value.payload["error"] == "tls_cert_unreadable"
    pair = resolve_tls_files(cert=cert, key=key)
    assert pair == (cert, key)


def test_serve_prints_tls_cert_unreadable_without_listening(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BLACKHOLE_TLS_CERT", raising=False)
    monkeypatch.delenv("BLACKHOLE_TLS_KEY", raising=False)
    root = _fixture_root(tmp_path)
    _, key = _tls_fixture_pair(tmp_path)
    code = serve(root, tls_cert=tmp_path / "no-such-cert.pem", tls_key=key)
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "tls_cert_unreadable"
    assert payload.get("listening") is None


def test_tls_server_serves_https_invoke_and_blocks_http(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    cert, key = _tls_fixture_pair(tmp_path)
    httpd = build_server(root, port=0, tls_cert=cert, tls_key=key)
    assert httpd.tls_enabled is True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        status, health = _https_request("GET", f"https://127.0.0.1:{port}/health")
        assert status == 200
        assert health["tls"] is True
        status, result = _https_request(
            "POST",
            f"https://127.0.0.1:{port}/invoke",
            {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": "blackhole"}},
        )
        assert status == 200
        assert result["ok"] is True
        assert result["output"] == {"reversed_text": "elohkcalb"}
        leaked = False
        try:
            with urlrequest.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                body = json.loads(response.read().decode("utf-8"))
                leaked = body.get("ok") is True
        except Exception:
            leaked = False
        assert leaked is False
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_load_invocable_skips_missing_manifest(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "capabilities" / "absorbed" / "snake-case" / "absorption.json").unlink()
    invocable = load_invocable_capabilities(root)
    assert "capability.absorbed-snake-case" not in invocable
    assert "capability.absorbed-text-reverser" in invocable


def test_invoke_capability_direct(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    result = invoke_capability(root, "capability.absorbed-text-reverser", {"raw_text": "unbound"})
    assert result["output"] == {"reversed_text": "dnuobnu"}
    with pytest.raises(InvocationError) as excinfo:
        invoke_capability(root, "capability.absorbed-text-reverser", {"raw_text": "a", "z": 2})
    assert excinfo.value.status == 422
    assert "unexpected keys" in excinfo.value.error


def test_listing_digest_is_stable(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    first = capability_listing(root)
    second = capability_listing(root)
    assert first["listing_digest"] == second["listing_digest"]


def _write_program_capability(root: Path) -> None:
    (root / "fixture_unit_cap.py").write_text(
        "def run():\n    return {'ok': True, 'echo': 'fixture'}\n", encoding="utf-8"
    )
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    entry = _ledger_entry("capability.fixture-program")
    entry["entry"] = "fixture_unit_cap:run"
    ledger["capabilities"]["capability.fixture-program"] = entry
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")


def test_contract_endpoint_machine_checks_done_when(server) -> None:
    root, base = server
    _write_program_capability(root)
    status, verdict = _request(
        "POST",
        f"{base}/contract",
        {"done_when": "program_passes:capability.fixture-program;no_skill_route"},
    )
    assert status == 200
    assert verdict["met"] is True
    assert verdict["used_skill_route_discovery"] is False
    assert verdict["contract_digest"]
    by_kind = {item["kind"]: item["passed"] for item in verdict["results"]}
    assert by_kind == {"program_passes": True, "no_skill_route": True}


def test_contract_endpoint_reports_unmet_program(server) -> None:
    _, base = server
    status, verdict = _request(
        "POST",
        f"{base}/contract",
        {"done_when": "program_passes:capability.absorbed-does-not-exist;no_skill_route"},
    )
    assert status == 200
    assert verdict["met"] is False
    assert verdict["failed_count"] == 1


def test_contract_endpoint_refuses_non_machine_contracts(server) -> None:
    _, base = server
    for payload in (
        {"done_when": ""},
        {"done_when": "   "},
        {"done_when": "the ledger feels healthy"},
        {"done_when": 42},
        {},
    ):
        status, result = _request("POST", f"{base}/contract", payload)
        assert status == 422, payload
        assert result["ok"] is False


def test_evaluate_contract_request_direct(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _write_program_capability(root)
    verdict = evaluate_contract_request(
        root, "program_passes:capability.fixture-program;no_skill_route"
    )
    assert verdict["met"] is True
    assert verdict["ok"] is True
    with pytest.raises(InvocationError) as excinfo:
        evaluate_contract_request(root, "")
    assert excinfo.value.status == 422
    with pytest.raises(InvocationError) as excinfo:
        evaluate_contract_request(root, "no machine predicates here")
    assert excinfo.value.status == 422


def test_solve_derives_and_executes_single_step(server) -> None:
    _, base = server
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"]},
    )
    assert status == 200
    assert result["ok"] is True and result["solved"] is True
    assert result["plan"] == ["capability.absorbed-text-reverser"]
    assert result["outcome"] == {"reversed_text": "elohkcalb"}
    assert len(result["steps"]) == 1
    assert result["steps"][0]["response_digest"]
    assert result["plan_digest"]


def test_solve_derives_multi_step_chain_with_threaded_state(server) -> None:
    root, base = server
    _write_chain_tool(root)
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["loud_text"]},
    )
    assert status == 200
    assert result["solved"] is True
    assert result["plan"] == [
        "capability.absorbed-text-reverser",
        "capability.absorbed-loud-shouter",
    ]
    assert result["outcome"] == {"loud_text": "ELOHKCALB"}
    assert result["steps"][1]["input"] == {"reversed_text": "elohkcalb"}
    assert len({step["response_digest"] for step in result["steps"]}) == 2


def test_solve_reports_unsolvable_goal_honestly(server) -> None:
    _, base = server
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["no_such_key"]},
    )
    assert status == 200
    assert result["ok"] is True and result["solved"] is False
    assert result["plan"] is None
    assert "steps" not in result


def test_solve_satisfied_goal_needs_no_subprocess(server) -> None:
    _, base = server
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"reversed_text": "elohkcalb"}, "goal": ["reversed_text"]},
    )
    assert status == 200
    assert result["solved"] is True
    assert result["plan"] == [] and result["steps"] == []
    assert result["outcome"] == {"reversed_text": "elohkcalb"}


def test_solve_refuses_malformed_requests(server) -> None:
    _, base = server
    for payload in (
        {},
        {"initial_state": {"raw_text": "a"}},
        {"goal": ["reversed_text"]},
        {"initial_state": "raw", "goal": ["reversed_text"]},
        {"initial_state": {}, "goal": []},
        {"initial_state": {}, "goal": ["  "]},
        {"initial_state": {}, "goal": "reversed_text"},
    ):
        status, result = _request("POST", f"{base}/solve", payload)
        assert status == 422, payload
        assert result["ok"] is False


def test_solve_ignores_unproved_capabilities(server) -> None:
    _, base = server
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"]},
    )
    assert status == 200
    assert "capability.absorbed-unproved" not in result["plan"]


_HEAL_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'healed_text': state['raw_text'][::-1]}))\n"
)


def _write_healable_tool(root: Path) -> str:
    tool_dir = root / "capabilities" / "absorbed" / "heal-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_HEAL_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "heal-reverser",
                "name": "fixture heal-reverser",
                "command": ["python", "tool.py"],
                "requires": ["raw_text"],
                "provides": ["healed_text"],
                "cases": [
                    {"input": {"raw_text": "ab"}, "expect": {"healed_text": "ba"}},
                    {"input": {"raw_text": "cd"}, "expect": {"healed_text": "dc"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    capability_id = "capability.absorbed-heal-reverser"
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["capabilities"][capability_id] = _ledger_entry(capability_id)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    return capability_id


def _quarantine(root: Path, capability_id: str) -> None:
    record_resource_quarantine(
        root,
        capability_id,
        {"resource": "memory", "reason": "fixture violation", "limit_bytes": 1},
    )


def test_solve_self_heals_quarantined_blocker(server) -> None:
    root, base = server
    capability_id = _write_healable_tool(root)
    _quarantine(root, capability_id)
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "unbound"}, "goal": ["healed_text"]},
    )
    assert status == 200
    assert result["solved"] is True
    assert result["plan"] == [capability_id]
    assert result["outcome"] == {"healed_text": "dnuobnu"}
    assert result["healing"] == [
        {
            "capability_id": capability_id,
            "reinstated": True,
            "case_count": 2,
            "cases_pass": True,
        }
    ]
    ledger = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    entry = ledger["capabilities"][capability_id]
    assert "resource_quarantine" not in entry
    assert entry["resource_reproof"]["cases_pass"] is True


def test_solve_unhealable_blocker_keeps_quarantine(server) -> None:
    root, base = server
    capability_id = "capability.absorbed-broken-tool"
    _quarantine(root, capability_id)
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "unbound"}, "goal": ["broken_text"]},
    )
    assert status == 200
    assert result["solved"] is False
    assert capability_id in result["reason"]
    assert result["healing"][0]["capability_id"] == capability_id
    assert result["healing"][0]["reinstated"] is False
    assert result["healing"][0]["cases_pass"] is False
    ledger = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    assert "resource_quarantine" in ledger["capabilities"][capability_id]


def test_solve_healthy_goal_reports_no_healing(server) -> None:
    _, base = server
    status, result = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"]},
    )
    assert status == 200
    assert result["solved"] is True
    assert result["healing"] == []


_HOLD_TOOL = (
    "import json, sys, time\n"
    "from pathlib import Path\n"
    "state = json.load(sys.stdin)\n"
    "Path('ready.txt').write_text('1', encoding='utf-8')\n"
    "time.sleep(float(state.get('hold_seconds') or 1.5))\n"
    "print(json.dumps({'tainted_text': state['raw_text']}))\n"
)

_LATE_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'final_text': state['tainted_text'][::-1]}))\n"
)


def _write_midexec_chain(root: Path) -> None:
    taint_dir = root / "capabilities" / "absorbed" / "tainter"
    taint_dir.mkdir(parents=True)
    (taint_dir / "tool.py").write_text(_HOLD_TOOL, encoding="utf-8")
    (taint_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "tainter",
                "name": "fixture tainter",
                "command": ["python", "tool.py"],
                "requires": ["raw_text", "hold_seconds"],
                "provides": ["tainted_text"],
                "cases": [
                    {
                        "input": {"raw_text": v, "hold_seconds": "0"},
                        "expect": {"tainted_text": v},
                    }
                    for v in ("ab", "cd")
                ],
            }
        ),
        encoding="utf-8",
    )
    late_dir = root / "capabilities" / "absorbed" / "late-reverser"
    late_dir.mkdir(parents=True)
    (late_dir / "tool.py").write_text(_LATE_TOOL, encoding="utf-8")
    (late_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "late-reverser",
                "name": "fixture late-reverser",
                "command": ["python", "tool.py"],
                "requires": ["tainted_text"],
                "provides": ["final_text"],
                "cases": [
                    {"input": {"tainted_text": "ab"}, "expect": {"final_text": "ba"}},
                    {"input": {"tainted_text": "cd"}, "expect": {"final_text": "dc"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    for slug in ("tainter", "late-reverser"):
        capability_id = f"capability.absorbed-{slug}"
        ledger["capabilities"][capability_id] = _ledger_entry(capability_id)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")


def test_solve_heals_mid_execution_quarantine(server) -> None:
    root, base = server
    _write_midexec_chain(root)
    ready = root / "capabilities" / "absorbed" / "tainter" / "ready.txt"
    box: dict[str, object] = {}

    def _solve() -> None:
        box["status"], box["result"] = _request(
            "POST",
            f"{base}/solve",
            {
                "initial_state": {"raw_text": "ab", "hold_seconds": "2"},
                "goal": ["final_text"],
            },
        )

    worker = threading.Thread(target=_solve)
    worker.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not ready.is_file():
        time.sleep(0.05)
    assert ready.is_file(), "hold step never started"
    record_resource_quarantine(
        root,
        "capability.absorbed-late-reverser",
        {"reason": "mid-execution taint", "resource": "memory"},
    )
    worker.join(timeout=30)
    status = box.get("status")
    result = box.get("result") or {}
    assert status == 200
    assert result["solved"] is True
    assert result["plan"] == ["capability.absorbed-tainter", "capability.absorbed-late-reverser"]
    assert result["outcome"] == {"final_text": "ba"}
    healed = result["healing"][-1]
    assert healed["capability_id"] == "capability.absorbed-late-reverser"
    assert healed["reinstated"] is True
    ledger = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    assert "resource_quarantine" not in ledger["capabilities"]["capability.absorbed-late-reverser"]



def test_solve_goal_request_direct_and_digest_stability(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    first = solve_goal_request(root, {"raw_text": "unbound"}, ["reversed_text"])
    second = solve_goal_request(root, {"raw_text": "unbound"}, ["reversed_text"])
    assert first["solved"] is True
    assert first["outcome"] == {"reversed_text": "dnuobnu"}
    assert first["plan_digest"] == second["plan_digest"]
    with pytest.raises(InvocationError) as excinfo:
        solve_goal_request(root, {"raw_text": "a"}, [])
    assert excinfo.value.status == 422


def test_solve_dry_run_returns_plan_without_executing(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _write_tool(
        root,
        "append-event",
        (
            "import json, sys\n"
            "from pathlib import Path\n"
            "state = json.load(sys.stdin)\n"
            "Path(state['events']).write_text(state['label'], encoding='utf-8')\n"
            "print(json.dumps({'saved': state['label']}))\n"
        ),
        requires=["events", "label"],
        provides=["saved"],
    )
    tool_dir = root / "capabilities" / "absorbed" / "append-event"
    manifest_path = tool_dir / "absorption.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["command"] = [sys.executable, "tool.py"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    canary = tool_dir / "effects.txt"
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["capabilities"]["capability.absorbed-append-event"] = _ledger_entry(
        "capability.absorbed-append-event"
    )
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    preview = solve_goal_request(
        root,
        {"events": str(canary), "label": "preview-should-not-write"},
        ["saved"],
        dry_run=True,
    )
    assert preview["solved"] is True
    assert preview["dry_run"] is True
    assert preview["plan"] == ["capability.absorbed-append-event"]
    assert preview["steps"] == []
    assert "outcome" not in preview
    assert not canary.exists()
    live = solve_goal_request(
        root,
        {"events": str(canary), "label": "preview-should-not-write"},
        ["saved"],
    )
    assert live["solved"] is True
    assert live.get("dry_run") is not True
    assert canary.read_text(encoding="utf-8") == "preview-should-not-write"
    unsolved = solve_goal_request(root, {"raw_text": "x"}, ["no_such_key"], dry_run=True)
    assert unsolved["solved"] is False
    assert unsolved["dry_run"] is True
    assert unsolved["plan"] is None
    satisfied = solve_goal_request(root, {"reversed_text": "ab"}, ["reversed_text"], dry_run=True)
    assert satisfied["solved"] is True
    assert satisfied["plan"] == []
    assert satisfied["outcome"] == {"reversed_text": "ab"}
    with pytest.raises(InvocationError) as excinfo:
        parse_solve_dry_run("yes")
    assert excinfo.value.status == 422
    assert parse_solve_dry_run(None) is False
    assert parse_solve_dry_run(True) is True
    assert prefer_solve_preview("foo, solve=preview") is True
    assert prefer_solve_preview("return=minimal") is False
    assert resolve_solve_dry_run({"dry_run": False}, "solve=preview") is True
    assert resolve_solve_dry_run({"dry_run": True}, None) is True
    assert resolve_solve_dry_run({}, None) is False


def test_solve_http_preview_and_prefer_header(server) -> None:
    root, base = server
    status, health = _request("GET", f"{base}/health")
    assert status == 200
    assert health["solve_plan_preview"] is True
    status, preview = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"], "dry_run": True},
    )
    assert status == 200
    assert preview["dry_run"] is True
    assert preview["solved"] is True
    assert preview["plan"] == ["capability.absorbed-text-reverser"]
    assert preview["steps"] == []
    status, via_prefer = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"]},
        headers={"Prefer": "solve=preview"},
    )
    assert status == 200
    assert via_prefer["dry_run"] is True
    assert via_prefer["plan"] == ["capability.absorbed-text-reverser"]
    status, live = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"]},
    )
    assert status == 200
    assert live.get("dry_run") is not True
    assert live["outcome"]["reversed_text"] == "elohkcalb"
    status, bad = _request(
        "POST",
        f"{base}/solve",
        {"initial_state": {"raw_text": "blackhole"}, "goal": ["reversed_text"], "dry_run": "yes"},
    )
    assert status == 422
    from blackhole_agent.capability_console import console_html

    page = console_html(root)
    assert "function previewSolve()" in page
    assert "body.dry_run = true" in page


def test_plan_goal_program_minimality_and_honesty(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _write_chain_tool(root)
    invocable = load_invocable_capabilities(root)
    direct = plan_goal_program(invocable, {"raw_text"}, ["reversed_text"])
    assert direct == ["capability.absorbed-text-reverser"]
    chained = plan_goal_program(invocable, {"raw_text"}, ["loud_text"])
    assert chained == [
        "capability.absorbed-text-reverser",
        "capability.absorbed-loud-shouter",
    ]
    assert plan_goal_program(invocable, {"raw_text"}, ["missing_key"]) is None
    assert plan_goal_program(invocable, {"reversed_text"}, ["reversed_text"]) == []
    bounded = plan_goal_program(invocable, {"raw_text"}, ["loud_text"], max_steps=1)
    assert bounded is None


def test_tool_execution_env_scrubs_ambient_secrets(monkeypatch) -> None:
    from blackhole_agent.capability_absorption import TOOL_ENV_PASSTHROUGH, tool_execution_env

    monkeypatch.setenv("BH_PROBE_SECRET", "canary-value")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "canary-secret")
    env = tool_execution_env()
    assert "BH_PROBE_SECRET" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env.get("PATH")
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    leaked = [key for key in env if key not in TOOL_ENV_PASSTHROUGH]
    assert sorted(leaked) == ["PYTHONDONTWRITEBYTECODE", "PYTHONIOENCODING"]
    with_extra = tool_execution_env({"BH_PROBE_DELIBERATE": "declared"})
    assert with_extra["BH_PROBE_DELIBERATE"] == "declared"
    assert "BH_PROBE_SECRET" not in with_extra


def test_mcp_streamable_http_executes_absorbed_tool_and_keeps_rest(server) -> None:
    _, base = server
    mcp = f"{base}/mcp"
    status, handshake, headers = _request_full(
        "POST",
        mcp,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        },
    )
    session = headers.get("mcp-session-id") or ""
    assert status == 200
    assert session
    assert handshake["result"]["serverInfo"]["name"] == "blackhole-capability-mcp"
    hdr = {"Mcp-Session-Id": session}

    status, listed = _request(
        "POST", mcp, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, headers=hdr
    )
    names = [item["name"] for item in listed["result"]["tools"]]
    assert "text-reverser" in names
    assert "solve_goal" in names

    probe_text = "mcp-http-92080663"
    status, called = _request(
        "POST",
        mcp,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "text-reverser", "arguments": {"raw_text": probe_text}},
        },
        headers=hdr,
    )
    assert status == 200
    assert called["result"]["isError"] is False
    assert called["result"]["structuredContent"] == {"reversed_text": probe_text[::-1]}

    status, unknown = _request(
        "POST",
        mcp,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "not-a-real-tool", "arguments": {}},
        },
        headers=hdr,
    )
    assert status == 200
    assert unknown["error"]["code"] == -32602

    status, missing = _request(
        "POST", mcp, {"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}}
    )
    assert status == 404
    assert missing["error"] == "mcp_session_unknown"

    status, solved = _request(
        "POST",
        mcp,
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "solve_goal",
                "arguments": {"initial_state": {"raw_text": probe_text}, "goal": ["reversed_text"]},
            },
        },
        headers=hdr,
    )
    assert status == 200
    assert solved["result"]["structuredContent"]["solved"] is True
    assert solved["result"]["structuredContent"]["outcome"]["reversed_text"] == probe_text[::-1]

    status, get_mcp = _request("GET", mcp)
    assert status == 404
    assert get_mcp["error"] == "mcp_session_unknown"
    status, get_no_sse = _request("GET", mcp, headers=hdr)
    assert status == 406
    assert get_no_sse["error"] == "mcp_get_requires_event_stream"

    status, closed = _request("DELETE", mcp, headers=hdr)
    assert status == 200 and closed["closed"] is True
    status, after = _request(
        "POST", mcp, {"jsonrpc": "2.0", "id": 7, "method": "ping", "params": {}}, headers=hdr
    )
    assert status == 404

    status, invoked = _request(
        "POST",
        f"{base}/invoke",
        {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": probe_text}},
    )
    assert status == 200
    assert invoked["output"] == {"reversed_text": probe_text[::-1]}


def test_mcp_streamable_http_requires_bearer_when_configured(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    httpd = build_server(root, port=0, token="mcp-plane-token")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        mcp = f"{base}/mcp"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}},
        }
        status, body = _request("POST", mcp, payload)
        assert status == 401
        assert body["error"] == "authorization_required"
        status, body = _request(
            "POST", mcp, payload, headers={"Authorization": "Bearer wrong-token"}
        )
        assert status == 403
        status, handshake, headers = _request_full(
            "POST", mcp, payload, headers={"Authorization": "Bearer mcp-plane-token"}
        )
        assert status == 200
        assert headers.get("mcp-session-id")
        assert handshake["result"]["serverInfo"]["name"] == "blackhole-capability-mcp"
        session_headers = {"Mcp-Session-Id": headers["mcp-session-id"]}
        authorized_headers = {**session_headers, "Authorization": "Bearer mcp-plane-token"}
        for method, params in (
            ("resources/list", {}),
            ("resources/read", {"uri": "blackhole://capabilities/capability.absorbed-text-reverser"}),
            ("resources/templates/list", {}),
            ("prompts/list", {}),
            ("prompts/get", {
                "name": "prepare_capability_call", "arguments": {"capability_id": "capability.absorbed-text-reverser"},
            }),
        ):
            rpc = {"jsonrpc": "2.0", "id": 2, "method": method, "params": params}
            assert _request("POST", mcp, rpc, headers=session_headers)[0] == 401
            assert _request("POST", mcp, rpc, headers={
                **session_headers, "Authorization": "Bearer wrong-token",
            })[0] == 403
            status, response = _request("POST", mcp, rpc, headers=authorized_headers)
            assert status == 200 and "result" in response, response
        metadata = json.loads(response["result"]["messages"][1]["content"]["resource"]["text"])
        assert metadata["requires"] == ["raw_text"]
        assert metadata["tool"]["name"] == "text-reverser"
        get_status, get_body = _request("GET", mcp, headers=session_headers)
        assert get_status == 401
        get_status, get_body = _request("GET", mcp, headers=authorized_headers)
        assert get_status == 406
        assert get_body["error"] == "mcp_get_requires_event_stream"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def _read_http_headers(sock: socket.socket) -> tuple[int, bytes]:
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    header, rest = buf.split(b"\r\n\r\n", 1) if b"\r\n\r\n" in buf else (buf, b"")
    status_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
    parts = status_line.split(" ", 2)
    status = int(parts[1]) if len(parts) >= 2 else 0
    return status, rest


def test_mcp_http_get_sse_progress_and_cross_post_cancel(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    slow = (
        "import json, sys, time\n"
        "from pathlib import Path\n"
        "state = json.load(sys.stdin)\n"
        "path = Path(state['heartbeat_path'])\n"
        "deadline = time.monotonic() + 25\n"
        "n = 0\n"
        "while time.monotonic() < deadline:\n"
        "    n += 1\n"
        "    path.write_text(str(n), encoding='utf-8')\n"
        "    time.sleep(0.05)\n"
        "print(json.dumps({'beats': n}))\n"
    )
    _write_tool(
        root,
        "heartbeat-hold",
        slow,
        requires=["heartbeat_path"],
        provides=["beats"],
    )
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["capabilities"]["capability.absorbed-heartbeat-hold"] = _ledger_entry(
        "capability.absorbed-heartbeat-hold"
    )
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    heartbeat = root / "capabilities" / "absorbed" / "heartbeat-hold" / "heartbeat.txt"

    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host = "127.0.0.1"
        port = httpd.server_address[1]
        mcp = f"http://{host}:{port}/mcp"
        status, handshake, headers = _request_full(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
        )
        session = headers.get("mcp-session-id") or ""
        assert status == 200 and session
        hdr = {"Mcp-Session-Id": session}

        sse_sock = socket.create_connection((host, port), timeout=10)
        sse_sock.sendall(
            (
                f"GET /mcp HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                f"Accept: text/event-stream\r\n"
                f"Mcp-Session-Id: {session}\r\n"
                f"Connection: keep-alive\r\n"
                f"\r\n"
            ).encode("ascii")
        )
        sse_status, pending = _read_http_headers(sse_sock)
        assert sse_status == 200
        events: list[dict] = []
        stop_sse = threading.Event()

        def _collect() -> None:
            buf = pending
            while not stop_sse.is_set():
                sse_sock.settimeout(0.4)
                try:
                    chunk = sse_sock.recv(4096)
                except TimeoutError:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    raw, buf = buf.split(b"\n\n", 1)
                    data_lines = [
                        line[5:].lstrip()
                        for line in raw.decode("utf-8", errors="replace").splitlines()
                        if line.startswith("data:")
                    ]
                    if not data_lines:
                        continue
                    try:
                        payload = json.loads("\n".join(data_lines))
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        events.append(payload)

        collector = threading.Thread(target=_collect, daemon=True)
        collector.start()

        call_box: dict[str, object] = {}

        def _call() -> None:
            call_box["status"], call_box["body"] = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "tools/call",
                    "params": {
                        "name": "heartbeat-hold",
                        "arguments": {"heartbeat_path": str(heartbeat)},
                        "_meta": {"progressToken": "probe-progress"},
                    },
                },
                headers=hdr,
            )

        caller = threading.Thread(target=_call, daemon=True)
        caller.start()
        started = time.monotonic()
        first_beat = 0
        while time.monotonic() - started < 15:
            try:
                first_beat = int(heartbeat.read_text(encoding="utf-8").strip() or "0")
            except (OSError, ValueError):
                first_beat = 0
            if first_beat >= 1 and any(
                item.get("method") == "notifications/progress" for item in events
            ):
                break
            time.sleep(0.05)
        assert first_beat >= 1, "heartbeat tool never started"
        assert any(item.get("method") == "notifications/progress" for item in events)

        status, accepted = _request(
            "POST",
            mcp,
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 42},
            },
            headers=hdr,
        )
        assert status == 202
        caller.join(timeout=15)
        assert call_box.get("status") == 200
        body = call_box.get("body")
        assert isinstance(body, dict)
        assert body.get("error", {}).get("code") == -32800

        time.sleep(0.8)
        sample_a = int(heartbeat.read_text(encoding="utf-8").strip() or "0")
        time.sleep(0.6)
        sample_b = int(heartbeat.read_text(encoding="utf-8").strip() or "0")
        assert sample_b == sample_a

        status, invoked = _request(
            "POST",
            f"http://{host}:{port}/invoke",
            {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": "blackhole"}},
        )
        assert status == 200
        assert invoked["output"]["reversed_text"] == "elohkcalb"
        stop_sse.set()
        try:
            sse_sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sse_sock.close()
        collector.join(timeout=2)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_invoke_hides_operator_secrets_from_tool(server, monkeypatch) -> None:
    root, base = server
    _write_env_echo_tool(root)
    monkeypatch.setenv("BH_PROBE_OPERATOR_TOKEN", "canary-value")
    status, result = _request(
        "POST",
        f"{base}/invoke",
        {"capability_id": "capability.absorbed-env-echo", "input": {"raw_text": "blackhole"}},
    )
    assert status == 200
    assert result["output"]["reversed_text"] == "elohkcalb"
    assert result["output"]["seen_probe_keys"] == []
    assert result["output"]["has_path"] is True
