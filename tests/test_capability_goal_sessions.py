"""Unit tests for durable, interactive, cancellable goal sessions."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError

import pytest

from blackhole_agent.capability_service import InvocationError, build_server
from blackhole_agent.capability_sessions import (
    SessionManager,
    external_state_keys,
    plan_goal_with_elicitation,
)

_REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)

_SHOUTER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'loud_text': state['reversed_text'].upper()}))\n"
)

_SLEEPER = (
    "import json, sys, time, pathlib\n"
    "state = json.load(sys.stdin)\n"
    "time.sleep(30)\n"
    "pathlib.Path(state['marker_path']).write_text('done')\n"
    "print(json.dumps({'marker_done': True}))\n"
)


def _write_tool(root: Path, slug: str, source: str, requires: list, provides: list) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
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


def _fixture_root(base: Path, *, with_sleeper: bool = False) -> Path:
    root = base / "repo"
    _write_tool(root, "text-reverser", _REVERSER, ["raw_text"], ["reversed_text"])
    _write_tool(root, "loud-shouter", _SHOUTER, ["reversed_text"], ["loud_text"])
    ids = ["capability.absorbed-text-reverser", "capability.absorbed-loud-shouter"]
    if with_sleeper:
        _write_tool(root, "slow-marker", _SLEEPER, ["start_token", "marker_path"], ["marker_done"])
        ids.append("capability.absorbed-slow-marker")
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {cid: _ledger_entry(cid) for cid in ids},
            }
        ),
        encoding="utf-8",
    )
    return root


def _request(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
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
    root = _fixture_root(tmp_path, with_sleeper=True)
    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield root, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=10)


def _wait_status(base: str, session_id: str, wanted: set[str], timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        status, body = _request("GET", f"{base}/sessions/{session_id}")
        assert status == 200
        if body["session"]["status"] in wanted:
            return body["session"]
        assert time.monotonic() < deadline, f"session stuck at {body['session']['status']}"
        time.sleep(0.1)


# -- elicitation planner ----------------------------------------------------


def test_planner_elicits_minimal_external_key(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    from blackhole_agent.capability_service import load_invocable_capabilities

    invocable = load_invocable_capabilities(root)
    planned = plan_goal_with_elicitation(invocable, set(), ["loud_text"])
    assert planned is not None
    assert planned["program"] == [
        "capability.absorbed-text-reverser",
        "capability.absorbed-loud-shouter",
    ]
    assert planned["elicited_keys"] == ["raw_text"]
    assert planned["key_consumers"] == {"raw_text": "capability.absorbed-text-reverser"}


def test_planner_no_elicitation_when_state_suffices(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    from blackhole_agent.capability_service import load_invocable_capabilities

    invocable = load_invocable_capabilities(root)
    planned = plan_goal_with_elicitation(invocable, {"raw_text"}, ["loud_text"])
    assert planned is not None
    assert planned["elicited_keys"] == []


def test_planner_elicits_goal_key_directly(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    from blackhole_agent.capability_service import load_invocable_capabilities

    invocable = load_invocable_capabilities(root)
    planned = plan_goal_with_elicitation(invocable, set(), ["raw_text"])
    assert planned is not None
    assert planned["program"] == []
    assert planned["elicited_keys"] == ["raw_text"]
    assert planned["key_consumers"] == {"raw_text": "goal"}


def test_planner_honest_unsolvable_beyond_elicitation(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    from blackhole_agent.capability_service import load_invocable_capabilities

    invocable = load_invocable_capabilities(root)
    assert plan_goal_with_elicitation(invocable, set(), ["no_such_key"]) is None


def test_external_state_keys_excludes_provided(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    from blackhole_agent.capability_service import load_invocable_capabilities

    invocable = load_invocable_capabilities(root)
    assert external_state_keys(invocable) == {"raw_text"}


# -- session lifecycle over HTTP --------------------------------------------


def test_session_elicits_then_solves(server) -> None:
    _, base = server
    status, created = _request("POST", f"{base}/sessions", {"initial_state": {}, "goal": ["loud_text"]})
    assert status == 200
    session = created["session"]
    assert session["status"] == "awaiting_input"
    assert session["pending_keys"] == ["raw_text"]
    assert session["steps"] == []

    status, answered = _request(
        "POST", f"{base}/sessions/{session['session_id']}/input", {"input": {"raw_text": "blackhole"}}
    )
    assert status == 200
    assert answered["session"]["status"] == "running"

    final = _wait_status(base, session["session_id"], {"solved"})
    assert final["outcome"] == {"loud_text": "ELOHKCALB"}
    assert final["plan"] == ["capability.absorbed-text-reverser", "capability.absorbed-loud-shouter"]
    assert final["plan_digest"]
    kinds = [t["kind"] for t in final["transitions"]]
    assert kinds == ["created", "elicited", "input_accepted", "planned", "step_completed", "step_completed", "solved"]


def test_session_solves_immediately_when_state_complete(server) -> None:
    _, base = server
    status, created = _request(
        "POST", f"{base}/sessions", {"initial_state": {"raw_text": "blackhole"}, "goal": ["loud_text"]}
    )
    assert status == 200
    session = created["session"]
    assert session["status"] == "running"
    final = _wait_status(base, session["session_id"], {"solved"})
    assert final["outcome"] == {"loud_text": "ELOHKCALB"}


def test_session_unsolvable_is_honest(server) -> None:
    _, base = server
    status, created = _request(
        "POST", f"{base}/sessions", {"initial_state": {}, "goal": ["no_such_key"]}
    )
    assert status == 200
    assert created["session"]["status"] == "unsolvable"
    assert created["session"]["plan"] is None


def test_session_input_validation_is_strict(server) -> None:
    _, base = server
    _, created = _request("POST", f"{base}/sessions", {"initial_state": {}, "goal": ["loud_text"]})
    session_id = created["session"]["session_id"]
    status, body = _request(
        "POST", f"{base}/sessions/{session_id}/input", {"input": {"wrong_key": "x"}}
    )
    assert status == 422
    assert body["ok"] is False
    status, body = _request(
        "POST",
        f"{base}/sessions/{session_id}/input",
        {"input": {"raw_text": "x", "surprise": "y"}},
    )
    assert status == 422
    assert body["ok"] is False


def test_session_input_rejected_when_not_awaiting(server) -> None:
    _, base = server
    _, created = _request(
        "POST", f"{base}/sessions", {"initial_state": {"raw_text": "x"}, "goal": ["loud_text"]}
    )
    session_id = created["session"]["session_id"]
    _wait_status(base, session_id, {"solved"})
    status, body = _request(
        "POST", f"{base}/sessions/{session_id}/input", {"input": {"raw_text": "y"}}
    )
    assert status == 409
    assert body["ok"] is False


def test_unknown_session_is_404(server) -> None:
    _, base = server
    status, body = _request("GET", f"{base}/sessions/deadbeef")
    assert status == 404
    status, body = _request("DELETE", f"{base}/sessions/deadbeef")
    assert status == 404


def test_cancel_awaiting_session(server) -> None:
    _, base = server
    _, created = _request("POST", f"{base}/sessions", {"initial_state": {}, "goal": ["loud_text"]})
    session_id = created["session"]["session_id"]
    status, body = _request("DELETE", f"{base}/sessions/{session_id}")
    assert status == 200
    assert body["session"]["status"] == "cancelled"
    status, body = _request("DELETE", f"{base}/sessions/{session_id}")
    assert status == 409


def test_cancel_running_session_kills_tool_tree(server, tmp_path: Path) -> None:
    _, base = server
    marker = tmp_path / "marker.txt"
    started = time.monotonic()
    status, created = _request(
        "POST",
        f"{base}/sessions",
        {
            "initial_state": {"start_token": "go", "marker_path": str(marker)},
            "goal": ["marker_done"],
        },
    )
    assert status == 200
    session_id = created["session"]["session_id"]
    assert created["session"]["status"] == "running"
    time.sleep(1.5)  # let the tool actually spawn
    status, body = _request("DELETE", f"{base}/sessions/{session_id}")
    assert status == 200
    final = _wait_status(base, session_id, {"cancelled"}, timeout=15)
    assert time.monotonic() - started < 20  # the tool sleeps 30s
    kinds = [t["kind"] for t in final["transitions"]]
    assert "cancel_requested" in kinds and kinds[-1] == "cancelled"
    time.sleep(30)  # beyond the tool's full sleep: the tree must be dead
    assert not marker.exists()


def test_session_listing(server) -> None:
    _, base = server
    _request("POST", f"{base}/sessions", {"initial_state": {}, "goal": ["loud_text"]})
    status, listing = _request("GET", f"{base}/sessions")
    assert status == 200
    assert listing["count"] == 1
    assert listing["sessions"][0]["status"] == "awaiting_input"


def test_sessions_survive_restart(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    _, created = _request("POST", f"{base}/sessions", {"initial_state": {}, "goal": ["loud_text"]})
    session_id = created["session"]["session_id"]
    digest_before = created["session"]["session_digest"]
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=10)

    httpd2 = build_server(root, port=0)
    thread2 = threading.Thread(target=httpd2.serve_forever, daemon=True)
    thread2.start()
    base2 = f"http://127.0.0.1:{httpd2.server_address[1]}"
    try:
        status, body = _request("GET", f"{base2}/sessions/{session_id}")
        assert status == 200
        assert body["session"]["status"] == "awaiting_input"
        assert body["session"]["session_digest"] == digest_before
        _request("POST", f"{base2}/sessions/{session_id}/input", {"input": {"raw_text": "blackhole"}})
        final = _wait_status(base2, session_id, {"solved"})
        assert final["outcome"] == {"loud_text": "ELOHKCALB"}
    finally:
        httpd2.shutdown()
        httpd2.server_close()
        thread2.join(timeout=10)


def test_interrupted_session_resumes_after_restart(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    manager = SessionManager(root)
    record = manager.create_session({"raw_text": "blackhole"}, ["loud_text"])["session"]
    # Simulate server death mid-execution: status running, one step persisted.
    record["steps"].append(
        {
            "capability_id": "capability.absorbed-text-reverser",
            "input": {"raw_text": "blackhole"},
            "output": {"reversed_text": "elohkcalb"},
            "response_digest": "deadbeef",
        }
    )
    record["state"]["reversed_text"] = "elohkcalb"
    manager._persist(record)
    recovered = manager.recover()
    assert recovered == [record["session_id"]]
    reloaded = manager.get_session(record["session_id"])["session"]
    assert reloaded["status"] == "interrupted"

    httpd = build_server(root, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, body = _request("POST", f"{base}/sessions/{record['session_id']}/resume", {"input": {}})
        assert status == 200
        final = _wait_status(base, record["session_id"], {"solved"})
        assert final["outcome"] == {"loud_text": "ELOHKCALB"}
        assert len(final["steps"]) == 2  # persisted step + resumed step
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_resume_rejected_when_not_interrupted(server) -> None:
    _, base = server
    _, created = _request("POST", f"{base}/sessions", {"initial_state": {}, "goal": ["loud_text"]})
    session_id = created["session"]["session_id"]
    status, body = _request("POST", f"{base}/sessions/{session_id}/resume", {"input": {}})
    assert status == 409
    assert body["ok"] is False


def test_manager_rejects_malformed_requests(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    manager = SessionManager(root)
    with pytest.raises(InvocationError):
        manager.create_session([], ["loud_text"])
    with pytest.raises(InvocationError):
        manager.create_session({}, [])
    with pytest.raises(InvocationError):
        manager.create_session({}, ["loud_text", "  "])
