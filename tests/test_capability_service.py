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
    plan_goal_program,
    record_resource_quarantine,
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


_TAINT_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "with open(state['ledger_path'], encoding='utf-8') as handle:\n"
    "    ledger = json.load(handle)\n"
    "ledger['capabilities'][state['victim']]['resource_quarantine'] = {\n"
    "    'reason': 'mid-execution taint', 'resource': 'memory',\n"
    "    'quarantined_at': '2026-01-01T00:00:00Z'}\n"
    "with open(state['ledger_path'], 'w', encoding='utf-8') as handle:\n"
    "    handle.write(json.dumps(ledger))\n"
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
    (taint_dir / "tool.py").write_text(_TAINT_TOOL, encoding="utf-8")
    (taint_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "tainter",
                "name": "fixture tainter",
                "command": ["python", "tool.py"],
                "requires": ["raw_text", "ledger_path", "victim"],
                "provides": ["tainted_text"],
                "cases": [
                    {
                        "input": {"raw_text": v, "ledger_path": "x", "victim": "x"},
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
    status, result = _request(
        "POST",
        f"{base}/solve",
        {
            "initial_state": {
                "raw_text": "ab",
                "ledger_path": str(root / "capabilities" / "ledger.json"),
                "victim": "capability.absorbed-late-reverser",
            },
            "goal": ["final_text"],
        },
    )
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
