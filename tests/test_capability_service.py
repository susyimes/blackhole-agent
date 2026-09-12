"""Unit tests for the live capability invocation plane."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

import pytest

from blackhole_agent.capability_service import (
    build_server,
    capability_listing,
    evaluate_contract_request,
    invoke_capability,
    load_invocable_capabilities,
    InvocationError,
)

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_FAILING_TOOL = "import sys\nsys.exit(3)\n"


def _write_tool(root: Path, slug: str, tool_source: str = _TOOL) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(tool_source, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": slug,
        "name": f"fixture {slug}",
        "command": ["python", "tool.py"],
        "requires": ["raw_text"],
        "provides": ["reversed_text"],
        "cases": [
            {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")


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
    _write_tool(root, "snake-case")
    _write_tool(root, "broken-tool", _FAILING_TOOL)
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


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


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
    status, result = _request("GET", f"{base}/nope")
    assert status == 404 and result["ok"] is False
    status, result = _request("POST", f"{base}/capabilities", {"x": 1})
    assert status == 404


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
