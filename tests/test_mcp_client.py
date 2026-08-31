"""Tests for the live MCP client (real subprocess session -> sealed trace -> proof)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from blackhole_agent import mcp_client
from blackhole_agent.capability_compounder import atomic_write_json


def test_echo_server_handshake_and_tools_list() -> None:
    with mcp_client.McpStdioSession(mcp_client.echo_server_command()) as session:
        assert session.server_info["name"] == "blackhole-echo-mcp"
        assert session.protocol_version
        tools = session.list_tools()
        names = {tool["name"] for tool in tools["tools"]}
        assert names == {"echo", "sha256"}


def test_echo_server_lists_and_gets_prompts() -> None:
    with mcp_client.McpStdioSession(mcp_client.echo_server_command()) as session:
        assert isinstance(session.server_capabilities.get("prompts"), dict)
        listed = session.list_prompts()
        names = {item["name"] for item in listed["prompts"]}
        assert "about" in names
        about = mcp_client.extract_prompt_text(session.get_prompt("about"))
        assert about == "blackhole-echo-mcp"
        assert any(item.get("name") == "note" for item in listed["prompts"])
        note = mcp_client.extract_prompt_text(session.get_prompt("note", {"id": "beacon"}))
        assert note == "note:beacon"


def test_echo_server_lists_and_reads_resources() -> None:
    with mcp_client.McpStdioSession(mcp_client.echo_server_command()) as session:
        assert isinstance(session.server_capabilities.get("resources"), dict)
        listed = session.list_resources()
        uris = {item["uri"] for item in listed["resources"]}
        assert "resource://blackhole/echo/about" in uris
        about = mcp_client.extract_resource_text(
            session.read_resource("resource://blackhole/echo/about")
        )
        assert about == "blackhole-echo-mcp"
        templates = session.list_resource_templates()
        assert any(
            item.get("uriTemplate") == "resource://blackhole/echo/note/{id}"
            for item in templates["resourceTemplates"]
        )
        note = mcp_client.extract_resource_text(
            session.read_resource("resource://blackhole/echo/note/beacon")
        )
        assert note == "note:beacon"


def test_live_tool_call_returns_real_result() -> None:
    with mcp_client.McpStdioSession(mcp_client.echo_server_command()) as session:
        result = session.call_tool("echo", {"text": "hello-live"})
        assert result["content"][0]["text"] == "hello-live"
        digest = session.call_tool("sha256", {"text": "hello-live"})
        assert len(digest["content"][0]["text"]) == 64


def test_unknown_tool_raises_protocol_error() -> None:
    with mcp_client.McpStdioSession(mcp_client.echo_server_command()) as session:
        with pytest.raises(mcp_client.McpProtocolError):
            session.call_tool("nope", {})


def test_dead_server_command_fails_closed() -> None:
    session = mcp_client.McpStdioSession(["definitely-not-a-real-command-xyz"], timeout_seconds=5)
    with pytest.raises((mcp_client.McpProtocolError, OSError)):
        session.start()


def test_run_live_execution_seals_and_verifies(tmp_path: Path) -> None:
    out = tmp_path / "live"
    run = mcp_client.run_live_execution(
        server_name="echo",
        tool_name="echo",
        arguments={"text": "sealed"},
        output_dir=out,
    )
    assert run["ok"] and run["result_text"] == "sealed"
    assert "echo:echo" in run["imported_tool_names"]
    verify = mcp_client.verify_execution_trace(out)
    assert verify["ok"], verify


def test_tampered_trace_fails_verification(tmp_path: Path) -> None:
    out = tmp_path / "live"
    mcp_client.run_live_execution(arguments={"text": "original"}, output_dir=out)
    trace = json.loads((out / "execution.json").read_text(encoding="utf-8"))
    trace["routing"]["executable"] = False
    atomic_write_json(out / "execution.json", trace)
    verify = mcp_client.verify_execution_trace(out)
    assert not verify["ok"]
    assert not verify["checks"]["routing_digest"] or not verify["checks"]["trace_digest"]


def test_builtin_proof_is_green() -> None:
    result = mcp_client.builtin_mcp_live_execution_proof()
    assert result["ok"], result
    assert result["tamper_falsified"] and result["unknown_tool_fail_closed"]
    assert result["live_result_echoed"]


def test_external_filesystem_proof_is_green() -> None:
    # Hermetic registered proof: pure re-verification of the durable sealed
    # external trace; needs no npx/network, but the sealed evidence must exist.
    result = mcp_client.builtin_mcp_live_external_proof()
    assert result["ok"], result
    assert result["server_info"]["name"] == "secure-filesystem-server"
    assert result["external_result_verified"] and result["tamper_falsified"]
    assert result["pointer_binding_ok"] and result["pointer_forgery_detected"]
