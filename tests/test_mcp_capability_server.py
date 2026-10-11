"""Unit tests for the MCP capability server (server-side exposure of the ledger)."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from blackhole_agent.invocation_receipts import InvocationReceipts, ReceiptError
from blackhole_agent.mcp_capability_server import (
    CATALOG_URI,
    CAPABILITY_URI_TEMPLATE,
    LOG_MESSAGE_METHOD,
    PREPARE_PROMPT_NAME,
    PROTOCOL_VERSION,
    RESOURCES_LIST_CHANGED_NOTIFICATION,
    RESOURCES_UPDATED_METHOD,
    SERVER_CAPABILITIES,
    SERVER_INFO,
    TOOLS_LIST_CHANGED_NOTIFICATION,
    CapabilityCatalog,
    CatalogChangeWatcher,
    McpHttpSession,
    ResourceWatch,
    ToolCallError,
    capability_resource_uri,
    handle_http_rpc,
    handle_message,
    log_level_allowed,
    run_governed_tools_call,
    tool_name_for_slug,
)
from blackhole_agent.mcp_client import McpProtocolError, McpStdioSession, extract_resource_updated

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
    assert [tool["name"] for tool in catalog.tools] == ["text-reverser", "solve_goal"]
    tool = catalog.tools[0]
    assert tool["inputSchema"]["required"] == ["raw_text"]
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["outputSchema"]["required"] == ["reversed_text"]
    assert tool["outputSchema"]["properties"]["reversed_text"] == {"type": "string"}
    solve = catalog.tools[-1]
    assert solve["inputSchema"]["required"] == ["initial_state", "goal"]
    assert "solve_goal" not in catalog.by_name


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
    assert len(collected) == 6
    assert len(set(collected)) == 6
    with pytest.raises(ValueError):
        catalog.list_page("not-a-cursor", 2)
    with pytest.raises(ValueError):
        catalog.list_page("99", 2)


def test_catalog_tracks_ledger_changes(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    catalog = CapabilityCatalog(root)
    assert len(catalog.tools) == 2
    _fixture_root(tmp_path, extra_slugs=2)
    ledger_path = root / "capabilities" / "ledger.json"
    os.utime(ledger_path, (ledger_path.stat().st_atime, ledger_path.stat().st_mtime + 5))
    catalog.refresh()
    assert len(catalog.tools) == 4


def test_catalog_watcher_publishes_list_changed_on_new_invocable(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    catalog = CapabilityCatalog(root)
    published: list[str] = []
    watcher = CatalogChangeWatcher(
        catalog, lambda payload: published.append(str(payload.get("method"))), interval=0.05
    )
    watcher.start()
    try:
        assert catalog.fingerprint() == ("capability.absorbed-text-reverser",)
        _fixture_root(tmp_path, extra_slugs=1)
        ledger_path = root / "capabilities" / "ledger.json"
        os.utime(ledger_path, (ledger_path.stat().st_atime, ledger_path.stat().st_mtime + 5))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and TOOLS_LIST_CHANGED_NOTIFICATION["method"] not in published:
            time.sleep(0.05)
        assert TOOLS_LIST_CHANGED_NOTIFICATION["method"] in published
        assert RESOURCES_LIST_CHANGED_NOTIFICATION["method"] in published
        assert "capability.absorbed-extra-tool-000" in catalog.fingerprint()
    finally:
        watcher.stop()


def test_catalog_watcher_publishes_resource_updated_on_quarantine(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    catalog = CapabilityCatalog(root)
    uri = capability_resource_uri("capability.absorbed-text-reverser")
    published: list[dict] = []
    watcher = CatalogChangeWatcher(
        catalog,
        lambda payload: published.append(dict(payload)),
        interval=0.05,
        on_resource_updated=lambda watched: published.append(
            {"jsonrpc": "2.0", "method": RESOURCES_UPDATED_METHOD, "params": {"uri": watched}}
        ),
    )
    watcher.start()
    try:
        ledger_path = root / "capabilities" / "ledger.json"
        document = json.loads(ledger_path.read_text(encoding="utf-8"))
        document["capabilities"]["capability.absorbed-text-reverser"]["resource_quarantine"] = {
            "reason": "probe"
        }
        ledger_path.write_text(json.dumps(document), encoding="utf-8")
        os.utime(ledger_path, (ledger_path.stat().st_atime, ledger_path.stat().st_mtime + 5))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if any(item.get("method") == RESOURCES_UPDATED_METHOD for item in published):
                break
            time.sleep(0.05)
        updated = [
            item.get("params", {}).get("uri")
            for item in published
            if item.get("method") == RESOURCES_UPDATED_METHOD
        ]
        assert uri in updated
        assert TOOLS_LIST_CHANGED_NOTIFICATION["method"] not in [
            item.get("method") for item in published
        ]
        metadata = json.loads(catalog.read_resource(uri)["contents"][0]["text"])
        assert metadata["available"] is False
    finally:
        watcher.stop()


def test_handle_message_subscribes_and_unsubscribes_live_catalog_uri(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    watches = ResourceWatch()
    uri = capability_resource_uri("capability.absorbed-text-reverser")
    reply = handle_message(
        catalog,
        {"jsonrpc": "2.0", "id": 1, "method": "resources/subscribe", "params": {"uri": uri}},
        watches=watches,
    )
    assert reply["result"] == {}
    assert watches.contains(uri)
    missing = handle_message(
        catalog,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/subscribe",
            "params": {"uri": "blackhole://capabilities/missing"},
        },
        watches=watches,
    )
    assert missing["error"]["code"] == -32002
    assert not watches.contains("blackhole://capabilities/missing")
    dropped = handle_message(
        catalog,
        {"jsonrpc": "2.0", "id": 3, "method": "resources/unsubscribe", "params": {"uri": uri}},
        watches=watches,
    )
    assert dropped["result"] == {}
    assert not watches.contains(uri)


def test_http_rpc_subscribe_is_session_scoped(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    session = McpHttpSession()
    uri = capability_resource_uri("capability.absorbed-text-reverser")
    reply = handle_http_rpc(
        catalog,
        {"jsonrpc": "2.0", "id": 1, "method": "resources/subscribe", "params": {"uri": uri}},
        session=session,
    )
    assert reply["result"] == {}
    assert session.watches.contains(uri)
    outsider = McpHttpSession()
    assert not outsider.watches.contains(uri)


def test_handle_message_protocol_surface(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    reply = handle_message(catalog, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert reply["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert reply["result"]["serverInfo"] == SERVER_INFO
    assert reply["result"]["capabilities"]["tools"] == {"listChanged": True}
    assert reply["result"]["capabilities"]["resources"] == {
        "subscribe": True,
        "listChanged": True,
    }
    assert reply["result"]["capabilities"]["prompts"] == {"listChanged": False}
    assert reply["result"]["capabilities"]["completions"] == {}
    assert reply["result"]["capabilities"]["logging"] == {}
    assert reply["result"]["capabilities"]["experimental"] == {"idempotencyKey": True}
    assert reply["result"]["capabilities"] == SERVER_CAPABILITIES
    assert handle_message(catalog, {"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}
    assert handle_message(catalog, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    unknown = handle_message(catalog, {"jsonrpc": "2.0", "id": 3, "method": "unknown/method"})
    assert unknown["error"]["code"] == -32601


def test_logging_set_level_is_session_scoped(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    session = McpHttpSession()
    reply = handle_http_rpc(
        catalog,
        {"jsonrpc": "2.0", "id": 1, "method": "logging/setLevel", "params": {"level": "debug"}},
        session=session,
    )
    assert reply["result"] == {}
    assert session.logs.current() == "debug"
    outsider = McpHttpSession()
    assert outsider.logs.current() == "info"
    bad = handle_http_rpc(
        catalog,
        {"jsonrpc": "2.0", "id": 2, "method": "logging/setLevel", "params": {"level": "nope"}},
        session=session,
    )
    assert bad["error"]["code"] == -32602
    assert session.logs.current() == "debug"


def test_log_level_floor_filters_debug() -> None:
    assert log_level_allowed("info", "info") is True
    assert log_level_allowed("info", "warning") is True
    assert log_level_allowed("info", "debug") is False
    assert log_level_allowed("error", "info") is False


def test_tools_call_publishes_stderr_log_messages(tmp_path: Path, monkeypatch) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    session = McpHttpSession()
    listener = session.subscribe()

    def fake_invoke(root, capability_id, provided_input, **kwargs):
        output_listener = kwargs.get("output_listener")
        if output_listener is not None:
            output_listener("stderr", "BH-UNIT-LOG\n")
        return {
            "ok": True,
            "capability_id": capability_id,
            "output": {"reversed_text": provided_input["raw_text"][::-1]},
            "response_digest": "unit",
        }

    monkeypatch.setattr("blackhole_agent.mcp_capability_server.invoke_capability", fake_invoke)
    reply = handle_http_rpc(
        catalog,
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "text-reverser", "arguments": {"raw_text": "ab"}},
        },
        session=session,
    )
    structured = reply["result"]["structuredContent"]
    assert structured["reversed_text"] == "ba"
    messages = []
    while True:
        try:
            item = listener.get_nowait()
        except queue.Empty:
            break
        if isinstance(item, dict):
            messages.append(item)
    log_events = [item for item in messages if item.get("method") == LOG_MESSAGE_METHOD]
    assert log_events
    data = (log_events[0].get("params") or {}).get("data") or {}
    assert data.get("stream") == "stderr"
    assert "BH-UNIT-LOG" in str(data.get("text") or "")
    assert (log_events[0].get("params") or {}).get("level") == "info"


def test_error_log_floor_suppresses_tool_stderr(tmp_path: Path, monkeypatch) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    session = McpHttpSession()
    session.logs.set_level("error")
    listener = session.subscribe()

    def fake_invoke(root, capability_id, provided_input, **kwargs):
        output_listener = kwargs.get("output_listener")
        if output_listener is not None:
            output_listener("stderr", "BH-UNIT-LOG\n")
            output_listener("stdout", '{"reversed_text":"ba"}\n')
        return {
            "ok": True,
            "capability_id": capability_id,
            "output": {"reversed_text": "ba"},
            "response_digest": "unit",
        }

    monkeypatch.setattr("blackhole_agent.mcp_capability_server.invoke_capability", fake_invoke)
    handle_http_rpc(
        catalog,
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "text-reverser", "arguments": {"raw_text": "ab"}},
        },
        session=session,
    )
    messages = []
    while True:
        try:
            item = listener.get_nowait()
        except queue.Empty:
            break
        if isinstance(item, dict):
            messages.append(item)
    assert not [item for item in messages if item.get("method") == LOG_MESSAGE_METHOD]


def test_completion_complete_matches_live_catalog_without_execution(tmp_path: Path, monkeypatch) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))

    def refuse_execution(*args, **kwargs):
        pytest.fail("completion executed a tool")

    monkeypatch.setattr("blackhole_agent.mcp_capability_server.invoke_capability", refuse_execution)
    target = "capability.absorbed-text-reverser"
    prompt = handle_message(catalog, {
        "jsonrpc": "2.0", "id": 10, "method": "completion/complete",
        "params": {
            "ref": {"type": "ref/prompt", "name": PREPARE_PROMPT_NAME},
            "argument": {"name": "capability_id", "value": "text"},
        },
    })
    assert prompt["result"]["completion"]["values"] == [target]
    assert prompt["result"]["completion"]["hasMore"] is False
    resource = handle_message(catalog, {
        "jsonrpc": "2.0", "id": 11, "method": "completion/complete",
        "params": {
            "ref": {"type": "ref/resource", "uri": CAPABILITY_URI_TEMPLATE},
            "argument": {"name": "capability_id", "value": "capability.absorbed-text"},
        },
    })
    assert resource["result"]["completion"]["values"] == [target]
    empty = handle_message(catalog, {
        "jsonrpc": "2.0", "id": 12, "method": "completion/complete",
        "params": {
            "ref": {"type": "ref/prompt", "name": PREPARE_PROMPT_NAME},
            "argument": {"name": "task", "value": "text"},
        },
    })
    assert empty["result"]["completion"]["values"] == []
    miss = handle_message(catalog, {
        "jsonrpc": "2.0", "id": 13, "method": "completion/complete",
        "params": {
            "ref": {"type": "ref/prompt", "name": PREPARE_PROMPT_NAME},
            "argument": {"name": "capability_id", "value": "no-such-prefix"},
        },
    })
    assert miss["result"]["completion"]["values"] == []


def test_resources_and_prompt_expose_only_public_contract_without_execution(tmp_path: Path, monkeypatch) -> None:
    root = _fixture_root(tmp_path)
    catalog = CapabilityCatalog(root)

    def refuse_execution(*args, **kwargs):
        pytest.fail("metadata retrieval executed a tool")

    monkeypatch.setattr("blackhole_agent.mcp_capability_server.invoke_capability", refuse_execution)
    capability_id = "capability.absorbed-text-reverser"
    uri = capability_resource_uri(capability_id)
    listing = catalog.list_resources()
    assert [item["uri"] for item in listing["resources"]] == [CATALOG_URI, uri]
    content = catalog.read_resource(uri)["contents"][0]
    assert content["mimeType"] == "application/json"
    metadata = json.loads(content["text"])
    assert metadata["id"] == capability_id
    assert metadata["requires"] == ["raw_text"]
    assert metadata["provides"] == ["reversed_text"]
    assert metadata["available"] is True
    assert metadata["tool"] == catalog.tools[0]
    index = json.loads(catalog.read_resource(CATALOG_URI)["contents"][0]["text"])
    assert index["count"] == 1
    assert index["capabilities"] == [metadata]
    assert len(index["catalog_digest"]) == 64
    for private in ("tool_root", "command", "proof_command", "cases", str(root), "last_proof_exit_code"):
        assert private not in json.dumps(index)
    prompts = catalog.list_prompts()["prompts"]
    assert len(prompts) == 1 and prompts[0]["name"] == PREPARE_PROMPT_NAME
    prompt = catalog.get_prompt(PREPARE_PROMPT_NAME, {"capability_id": capability_id, "task": "reverse hello"})
    assert prompt["messages"][1] == {"role": "user", "content": {"type": "resource", "resource": content}}
    assert prompt["messages"][2]["content"]["text"] == "reverse hello"
    assert catalog.tools[0]["name"] in prompt["messages"][0]["content"]["text"]
    template = catalog.list_resource_templates()["resourceTemplates"][0]
    assert template["uriTemplate"].replace("{capability_id}", capability_id) == uri


def test_resources_paginate_and_refresh_availability(tmp_path: Path) -> None:
    import os

    root = _fixture_root(tmp_path, extra_slugs=3)
    catalog = CapabilityCatalog(root)
    before = catalog.read_resource(CATALOG_URI)
    cursor, uris = "", []
    while True:
        page = catalog.list_resources(cursor, 2)
        uris.extend(item["uri"] for item in page["resources"])
        if "nextCursor" not in page:
            break
        cursor = page["nextCursor"]
    assert len(uris) == len(set(uris)) == 5
    ledger_path = root / "capabilities" / "ledger.json"
    document = json.loads(ledger_path.read_text(encoding="utf-8"))
    capability_id = "capability.absorbed-text-reverser"
    document["capabilities"][capability_id]["resource_quarantine"] = {"reason": "private host path"}
    del document["capabilities"]["capability.absorbed-extra-tool-000"]
    ledger_path.write_text(json.dumps(document), encoding="utf-8")
    os.utime(ledger_path, (ledger_path.stat().st_atime, ledger_path.stat().st_mtime + 5))
    after = catalog.read_resource(CATALOG_URI)
    assert before != after
    metadata = json.loads(catalog.read_resource(capability_resource_uri(capability_id))["contents"][0]["text"])
    assert metadata["available"] is False
    assert metadata["unavailable_reason"] == "resource_quarantined"
    assert "private host path" not in json.dumps(after)
    assert len(catalog.list_resources()["resources"]) == 4
    with pytest.raises(ValueError, match="not available"):
        catalog.get_prompt(PREPARE_PROMPT_NAME, {"capability_id": capability_id})
    removed = handle_message(catalog, {
        "jsonrpc": "2.0", "id": 1, "method": "resources/read",
        "params": {"uri": capability_resource_uri("capability.absorbed-extra-tool-000")},
    })
    assert removed["error"]["code"] == -32002
    ledger_path.unlink()
    assert json.loads(catalog.read_resource(CATALOG_URI)["contents"][0]["text"])["count"] == 0


@pytest.mark.parametrize(("method", "params", "error"), [
    ("resources/read", {"uri": "file:///etc/passwd"}, -32002),
    ("resources/read", {"uri": CATALOG_URI + "/../ledger.json"}, -32002),
    ("resources/read", {"uri": CATALOG_URI + "/%2e%2e/ledger.json"}, -32002),
    ("resources/read", {"uri": CATALOG_URI + "/capability.absorbed-unproved-tool"}, -32002),
    ("resources/read", {}, -32602),
    ("resources/subscribe", {"uri": "file:///etc/passwd"}, -32002),
    ("resources/subscribe", {}, -32602),
    ("resources/unsubscribe", {"uri": []}, -32602),
    ("resources/unsubscribe", {}, -32602),
    ("resources/read", {"uri": []}, -32602),
    ("resources/list", {"cursor": -1}, -32602),
    ("resources/list", {"cursor": "-1"}, -32602),
    ("resources/list", {"cursor": "999"}, -32602),
    ("resources/list", {"cursor": "not-a-cursor"}, -32602),
    ("resources/templates/list", {"cursor": []}, -32602),
    ("prompts/list", {"cursor": True}, -32602),
    ("prompts/list", {"cursor": "2"}, -32602),
    ("prompts/get", {"name": "missing"}, -32602),
    ("prompts/get", {"name": PREPARE_PROMPT_NAME}, -32602),
    ("prompts/get", {"name": PREPARE_PROMPT_NAME, "arguments": []}, -32602),
    ("prompts/get", {"name": PREPARE_PROMPT_NAME, "arguments": {"capability_id": []}}, -32602),
    ("prompts/get", {"name": PREPARE_PROMPT_NAME, "arguments": {"capability_id": "missing"}}, -32602),
    ("prompts/get", {"name": PREPARE_PROMPT_NAME, "arguments": {"capability_id": "x", "extra": "y"}}, -32602),
    ("resources/list", [], -32602),
    ("completion/complete", {}, -32602),
    ("completion/complete", {"ref": [], "argument": {"name": "capability_id", "value": ""}}, -32602),
    ("completion/complete", {"ref": {"type": "ref/prompt", "name": "missing"}, "argument": {"name": "capability_id", "value": ""}}, -32602),
    ("completion/complete", {"ref": {"type": "ref/resource", "uri": "file:///etc/passwd"}, "argument": {"name": "capability_id", "value": ""}}, -32602),
])
def test_metadata_protocol_errors_are_structured(tmp_path: Path, method: str, params, error: int) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    reply = handle_message(catalog, {"jsonrpc": "2.0", "id": 42, "method": method, "params": params})
    assert reply["id"] == 42
    assert reply["error"]["code"] == error
    assert handle_message(catalog, {"jsonrpc": "2.0", "id": 43, "method": "ping"})["result"] == {}


def test_live_stdio_metadata_prepares_an_invocable_tool(tmp_path: Path) -> None:
    session = McpStdioSession(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(_fixture_root(tmp_path))],
        timeout_seconds=30,
    )
    try:
        session.start()
        assert "resources" in session.server_capabilities
        assert session.server_capabilities["resources"]["subscribe"] is True
        assert "prompts" in session.server_capabilities
        assert len(session.list_resources()["resources"]) == 2
        assert session.list_resource_templates()["resourceTemplates"]
        catalog = json.loads(session.read_resource(CATALOG_URI)["contents"][0]["text"])
        metadata = catalog["capabilities"][0]
        prompt_name = session.list_prompts()["prompts"][0]["name"]
        prompt = session.get_prompt(prompt_name, {"capability_id": metadata["id"]})
        embedded = json.loads(prompt["messages"][1]["content"]["resource"]["text"])
        assert embedded == metadata
        called = session.call_tool(embedded["tool"]["name"], {embedded["requires"][0]: "metadata-client"})
        assert called["structuredContent"] == {embedded["provides"][0]: "tneilc-atadatem"}
    finally:
        session.kill()


def test_live_stdio_subscribe_updated_on_quarantine(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    session = McpStdioSession(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(root)],
        timeout_seconds=30,
    )
    try:
        session.start()
        uri = capability_resource_uri("capability.absorbed-text-reverser")
        assert session.subscribe_resource(uri) == {}
        ledger_path = root / "capabilities" / "ledger.json"
        document = json.loads(ledger_path.read_text(encoding="utf-8"))
        document["capabilities"]["capability.absorbed-text-reverser"]["resource_quarantine"] = {
            "reason": "probe"
        }
        ledger_path.write_text(json.dumps(document), encoding="utf-8")
        os.utime(ledger_path, (ledger_path.stat().st_atime, ledger_path.stat().st_mtime + 5))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if uri in extract_resource_updated(session.server_notifications):
                break
            session.request("ping")
            time.sleep(0.05)
        assert uri in extract_resource_updated(session.server_notifications)
        metadata = json.loads(session.read_resource(uri)["contents"][0]["text"])
        assert metadata["available"] is False
        assert metadata["unavailable_reason"] == "resource_quarantined"
    finally:
        session.kill()


def test_handle_http_rpc_executes_tools_call(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    reply = handle_http_rpc(
        catalog,
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "text-reverser", "arguments": {"raw_text": "http-mcp"}},
        },
    )
    assert reply["id"] == 9
    assert reply["result"]["isError"] is False
    assert reply["result"]["structuredContent"] == {"reversed_text": "pcm-ptth"}
    unknown = handle_http_rpc(
        catalog,
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "missing-tool", "arguments": {}},
        },
    )
    assert unknown["error"]["code"] == -32602
    assert handle_http_rpc(
        catalog, {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None


def test_handle_http_rpc_replays_idempotent_tools_call(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    tool_dir = root / "capabilities" / "absorbed" / "append-event"
    tool_dir.mkdir(parents=True)
    events = tool_dir / "effects.txt"
    (tool_dir / "tool.py").write_text(
        "import json, sys\n"
        "s = json.load(sys.stdin)\n"
        "open(s['events'], 'a', encoding='utf-8').write(s['label'] + '\\n')\n"
        "print(json.dumps({'saved': s['label']}))\n",
        encoding="utf-8",
    )
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": "append-event",
                "name": "append event",
                "command": ["python", "tool.py"],
                "requires": ["events", "label"],
                "provides": ["saved"],
                "cases": [
                    {
                        "input": {"events": str(events), "label": label},
                        "expect": {"saved": label},
                    }
                    for label in ("a", "b")
                ],
            }
        ),
        encoding="utf-8",
    )
    ledger = json.loads((root / "capabilities" / "ledger.json").read_text(encoding="utf-8"))
    ledger["capabilities"]["capability.absorbed-append-event"] = {
        "id": "capability.absorbed-append-event",
        "name": "append event",
        "kind": "python",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }
    (root / "capabilities" / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    catalog = CapabilityCatalog(root)
    payload = {
        "jsonrpc": "2.0",
        "id": 21,
        "method": "tools/call",
        "params": {
            "name": "append-event",
            "arguments": {"events": str(events), "label": "once"},
            "_meta": {"idempotencyKey": "mcp-once"},
        },
    }
    first = handle_http_rpc(catalog, payload)
    second = handle_http_rpc(catalog, dict(payload, id=22))
    assert first["result"]["structuredContent"] == {"saved": "once"}
    assert second["result"]["structuredContent"] == {"saved": "once"}
    assert second["result"]["_meta"]["idempotencyReplayed"] is True
    assert events.read_text(encoding="utf-8").splitlines() == ["once"]
    conflict = handle_http_rpc(
        catalog,
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {
                "name": "append-event",
                "arguments": {"events": str(events), "label": "other"},
                "_meta": {"idempotencyKey": "mcp-once"},
            },
        },
    )
    assert conflict["error"]["code"] == -32001
    assert conflict["error"]["data"]["code"] == "idempotency_conflict"
    assert events.read_text(encoding="utf-8").splitlines() == ["once"]


def test_unknown_tool_with_idempotency_key_does_not_reserve(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    with pytest.raises(ToolCallError):
        run_governed_tools_call(
            catalog, "no-such-tool", {"raw_text": "ab"}, idempotency_key="ghost-key"
        )
    with pytest.raises(ReceiptError) as caught:
        InvocationReceipts(catalog.root).lookup("ghost-key")
    assert caught.value.status == 404


def test_admission_429_drops_mcp_receipt_so_key_can_be_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    calls = {"n": 0}

    def refuse(*_args, **_kwargs):
        calls["n"] += 1
        return {
            "content": [{"type": "text", "text": "invocation refused (429): too many"}],
            "isError": True,
        }

    monkeypatch.setattr(catalog, "call", refuse)
    first, replayed = run_governed_tools_call(
        catalog, "text-reverser", {"raw_text": "ab"}, idempotency_key="retry-after"
    )
    assert first["isError"] is True and replayed is False
    with pytest.raises(ReceiptError) as missing:
        InvocationReceipts(catalog.root).lookup("retry-after")
    assert missing.value.status == 404

    def succeed(*_args, **_kwargs):
        calls["n"] += 1
        return {
            "content": [{"type": "text", "text": '{"reversed_text": "ba"}'}],
            "structuredContent": {"reversed_text": "ba"},
            "isError": False,
        }

    monkeypatch.setattr(catalog, "call", succeed)
    second, replayed = run_governed_tools_call(
        catalog, "text-reverser", {"raw_text": "ab"}, idempotency_key="retry-after"
    )
    assert second["isError"] is False and replayed is False
    assert second["structuredContent"] == {"reversed_text": "ba"}
    assert calls["n"] == 2


def test_handle_http_rpc_publishes_progress_on_session(tmp_path: Path) -> None:
    catalog = CapabilityCatalog(_fixture_root(tmp_path))
    session = McpHttpSession()
    listener = session.subscribe()
    reply = handle_http_rpc(
        catalog,
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "text-reverser",
                "arguments": {"raw_text": "sse"},
                "_meta": {"progressToken": "unit-progress"},
            },
        },
        session=session,
    )
    assert reply["result"]["structuredContent"] == {"reversed_text": "ess"}
    published = []
    while True:
        try:
            published.append(listener.get_nowait())
        except queue.Empty:
            break
    progress = [
        item
        for item in published
        if isinstance(item, dict) and item.get("method") == "notifications/progress"
    ]
    assert [item.get("method") for item in progress] == [
        "notifications/progress",
        "notifications/progress",
    ]
    assert progress[0]["params"]["progressToken"] == "unit-progress"
    assert handle_http_rpc(
        catalog,
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 11}},
        session=session,
    ) is None


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
        assert names == ["text-reverser", "solve_goal"]
        result = session.call_tool("text-reverser", {"raw_text": "unbound"})
        assert result.get("isError") is False
        assert result.get("structuredContent") == {"reversed_text": "dnuobnu"}
        refused = session.call_tool("text-reverser", {"wrong": 1})
        assert refused.get("isError") is True
        with pytest.raises(McpProtocolError, match="unknown tool"):
            session.call_tool("no-such-tool", {})
    finally:
        session.kill()


def test_live_session_solves_declarative_goal(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    session = McpStdioSession(
        [sys.executable, "-m", "blackhole_agent.mcp_capability_server", "--root", str(root)],
        timeout_seconds=30,
    )
    try:
        session.start()
        result = session.call_tool(
            "solve_goal",
            {"initial_state": {"raw_text": "unbound"}, "goal": ["reversed_text"]},
        )
        assert result.get("isError") is False
        structured = result["structuredContent"]
        assert structured["solved"] is True
        assert structured["plan"] == ["capability.absorbed-text-reverser"]
        assert structured["outcome"] == {"reversed_text": "dnuobnu"}
        assert structured["plan_digest"]
        unsolvable = session.call_tool(
            "solve_goal", {"initial_state": {}, "goal": ["no_such_state_key"]}
        )
        assert unsolvable.get("isError") is False
        assert unsolvable["structuredContent"]["solved"] is False
        assert unsolvable["structuredContent"]["plan"] is None
        malformed = session.call_tool("solve_goal", {"initial_state": {}, "goal": []})
        assert malformed.get("isError") is True
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
