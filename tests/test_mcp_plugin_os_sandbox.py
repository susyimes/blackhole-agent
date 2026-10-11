"""Unit tests for hosted MCP plugin OS-sandbox helpers."""

from __future__ import annotations

from pathlib import Path

from blackhole_agent.mcp_plugin_invoke import mcp_plugin_health
from blackhole_agent.mcp_plugin_sandbox import plugin_command_rx_paths
from blackhole_agent.process_capture import filesystem_sandbox_available


def test_health_advertises_mcp_plugin_os_sandbox_without_plugin() -> None:
    health = mcp_plugin_health()
    assert health["mcp_plugin_os_sandbox"] is bool(filesystem_sandbox_available())
    assert health["mcp_plugin_sandbox"] is True
    assert health["mcp_plugin_invoke"] is False


def test_plugin_command_rx_paths_includes_existing_script_and_pythonpath(
    tmp_path: Path, monkeypatch
) -> None:
    script = tmp_path / "plugin.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    extra = tmp_path / "lib"
    extra.mkdir()
    paths = plugin_command_rx_paths(
        [str(script)],
        {"PYTHONPATH": str(extra)},
    )
    resolved = {path.resolve() for path in paths}
    assert script.resolve() in resolved
    assert script.parent.resolve() in resolved
    assert extra.resolve() in resolved
