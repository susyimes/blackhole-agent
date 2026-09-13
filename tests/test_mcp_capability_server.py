"""Unit tests for the MCP capability server (server-side exposure of the ledger)."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from blackhole_agent.mcp_capability_server import (
    PROTOCOL_VERSION,
    SERVER_INFO,
    CapabilityCatalog,
    handle_message,
    tool_name_for_slug,
)
from blackhole_agent.mcp_client import McpProtocolError, McpStdioSession

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


def _fixture_root(base: Path, *, extra_slugs: int = 0) -> Path:
    root = base / "repo"
    capabilities: dict[str, dict] = {}

    def add_tool(slug: str, *, proved: bool, body: str = _TOOL) -> None:
        tool_dir = root / "capabilities" / "absorbed" / slug
        tool_dir.mkdir(parents=True, exist_ok=True)
        (tool_dir / "tool.py").write_text(body, encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "slug": slug,
            "name": f"probe {slug}",
            "command": ["python", "tool.py"],
            "requires": ["raw_text"],
            "provides": ["reversed_text"],
            "cases": [
                {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
                {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
            ],
        }
        (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
        capabilities[f"capability.absorbed-{slug}"] = {
            "id": f"capability.absorbed-{slug}",
            "name": f"probe {slug}",
            "kind": "python",
            "last_proved_at": "2026-01-01T00:00:00Z" if proved else None,
            "last_proof_exit_code": 0 if proved else 1,
        }

    add_tool("text-reverser", proved=True)
    add_tool("unproved-tool", proved=False)
    for index in range(extra_slugs):
        add_tool(f"extra-tool-{index:03d}", proved=True)
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def test_tool_names_are_spec_legal_and_unique() -> None:
    taken: set[str] = set()
    names = {
        tool_name_for_slug(slug, taken)
        for slug in (
            "text-reverser",
            "docutils.utils.math mathml",
            "a" * 100,
            "a" * 100 + "-different-tail",
            "",
        )
    }
    assert len(names) == 5
    for name in names:
        assert 1 <= len(name) <= 64
        assert all(ch.isalnum() or ch in "_-" for ch in name)


def test_catalog_lists_only_proved_invocable(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    catalog = CapabilityCatalog(root)
    assert [tool["name"] for tool in catalog.tools] == ["text-reverser"]
    tool = catalog.tools[0]
    assert tool["inputSchema"]["required"] == ["raw_text"]
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["outputSchema"]["required"] == ["reversed_text"]
    assert tool["outputSchema"]["properties"]["reversed_text"] == {"type": "string"}


def test_catalog_pagination_has_no_gaps_or_duplicates(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path, extra_slugs=4)
    catalog = CapabilityCatalog(root)
    collected: list[str] = []
    cursor = ""
    pages = 0
    while True:
        page = catalog.list_page(cursor, 2)
        collected.extend(tool["name"] for tool in page["tools"])
        pages += 1
        cursor = page.get("nextCursor") or ""
        if not cursor:
            break
    assert pages == 3
    assert len(collected) == 5
    assert len(set(collected)) == 5
    with pytest.raises(ValueError):
        catalog.list_page("not-a-cursor", 2)
    with pytest.raises(ValueError):
        catalog.list_page("99", 2)


def test_catalog_tracks_ledger_changes(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    catalog = CapabilityCatalog(root)
    assert len(catalog.tools) == 1
    _fixture_root(tmp_path, extra_slugs=2)
    ledger_path = root / "capabilities" / "ledger.json"
    import os

    os.utime(ledger_path, (ledger_path.stat().st_atime, ledger_path.stat().st_mtime + 5))
    catalog.refresh()
    assert len(catalog.tools) == 3


def test_handle_message_protocol_surface(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    reply = handle_message(catalog, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert reply["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert reply["result"]["serverInfo"] == SERVER_INFO
    assert handle_message(catalog, {"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}
    assert handle_message(catalog, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    unknown = handle_message(catalog, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert unknown["error"]["code"] == -32601


def test_live_session_executes_real_capability(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    session = McpStdioSession(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(root)],
        timeout_seconds=30,
    )
    try:
        session.start()
        assert session.server_info == SERVER_INFO
        assert session.protocol_version == PROTOCOL_VERSION
        listing = session.paginate_tools()
        names = [tool["name"] for tool in listing["tools"]]
        assert names == ["text-reverser"]
        result = session.call_tool("text-reverser", {"raw_text": "unbound"})
        assert result.get("isError") is False
        assert result.get("structuredContent") == {"reversed_text": "dnuobnu"}
        refused = session.call_tool("text-reverser", {"wrong": 1})
        assert refused.get("isError") is True
        with pytest.raises(McpProtocolError, match="unknown tool"):
            session.call_tool("no-such-tool", {})
    finally:
        session.kill()


_SLOW_TOOL = (
    "import json, time\n"
    "time.sleep(30)\n"
    "print(json.dumps({'done': True}))\n"
)


def _add_slow_tool(root: Path, *, sleep_seconds: int = 30) -> None:
    body = _SLOW_TOOL.replace("30", str(sleep_seconds), 1)
    tool_dir = root / "capabilities" / "absorbed" / "slow-tool"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(body, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": "slow-tool",
        "name": "probe slow tool",
        "command": ["python", "tool.py"],
        "requires": [],
        "provides": ["done"],
        "cases": [
            {"input": {}, "expect": {"done": True}},
            {"input": {}, "expect": {"done": True}},
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    ledger_path = root / "capabilities" / "ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["capabilities"]["capability.absorbed-slow-tool"] = {
        "id": "capability.absorbed-slow-tool",
        "name": "probe slow tool",
        "kind": "python",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")


def _session(root: Path, timeout: float = 30.0) -> McpStdioSession:
    return McpStdioSession(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(root)],
        timeout_seconds=timeout,
    )


def test_cancelled_call_terminates_tool_and_releases_session(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _add_slow_tool(root)
    session = _session(root)
    try:
        session.start()
        started = time.monotonic()
        with pytest.raises(McpProtocolError, match="-32800"):
            session.call_tool("slow-tool", {}, cancel_after=0.5)
        elapsed = time.monotonic() - started
        assert elapsed < 10, f"cancelled call took {elapsed:.1f}s; tool tree was not terminated"
        assert session.cancelled_request_ids, "client never sent notifications/cancelled"
        result = session.call_tool("text-reverser", {"raw_text": "after"})
        assert result.get("structuredContent") == {"reversed_text": "retfa"}
    finally:
        session.kill()


def test_progress_notifications_wrap_progress_token_calls(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    session = _session(root)
    try:
        session.start()
        result = session.call_tool("text-reverser", {"raw_text": "tok"}, progress_token="probe-token")
        assert result.get("isError") is False
        progress = [
            note
            for note in session.server_notifications
            if note.get("method") == "notifications/progress"
            and (note.get("params") or {}).get("progressToken") == "probe-token"
        ]
        assert progress, f"no progress notifications seen: {session.server_notifications!r}"
        assert progress[0]["params"]["progress"] == 0
        assert progress[-1]["params"]["progress"] == 1
    finally:
        session.kill()


def test_sibling_requests_answered_while_call_in_flight(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _add_slow_tool(root)
    process = subprocess.Popen(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(root)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    replies: dict[int, dict] = {}
    lines: queue.Queue[str | None] = queue.Queue()
    try:
        assert process.stdin is not None and process.stdout is not None

        def pump() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        threading.Thread(target=pump, daemon=True).start()

        def send(message: dict) -> None:
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()

        def read_until(request_id: int, timeout: float) -> dict:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if request_id in replies:
                    return replies[request_id]
                try:
                    line = lines.get(timeout=max(0.05, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if line is None:
                    raise AssertionError("server stdout closed")
                payload = json.loads(line)
                if isinstance(payload, dict) and "id" in payload:
                    replies[payload["id"]] = payload
            raise AssertionError(f"no reply for id={request_id} within {timeout}s")

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        read_until(1, 10)
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "slow-tool", "arguments": {}}})
        time.sleep(0.5)
        ping_at = time.monotonic()
        send({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        ping_reply = read_until(3, 5)
        ping_elapsed = time.monotonic() - ping_at
        assert ping_reply.get("result") == {}
        assert ping_elapsed < 5, f"ping blocked {ping_elapsed:.1f}s behind the in-flight call"
        send({"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}})
        listing = read_until(4, 5)
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "slow-tool" in names
        send(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 2, "reason": "probe done"},
            }
        )
        cancelled = read_until(2, 5)
        assert (cancelled.get("error") or {}).get("code") == -32800
    finally:
        process.kill()
