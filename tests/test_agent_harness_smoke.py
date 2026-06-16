import json
import subprocess

import pytest

from blackhole_agent.kernels.codex_cli import CodexCliConfig, CodexCliKernel
from blackhole_agent.tool_routing import ToolCompatibilityCache, ToolDescriptor


def test_local_agent_harness_smoke_captures_runner_result_and_tool_route(tmp_path):
    """Harmless fixture task: invoke a fake local runner and route one local tool."""

    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("fixture complete")
        return subprocess.CompletedProcess(command, 0, stdout="trace: ok\n", stderr="")

    descriptor = ToolDescriptor(
        name="read_fixture",
        description="Read a local harmless fixture.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        provider="local",
        session_id="smoke",
    )
    cache = ToolCompatibilityCache()
    route_key = cache.set(descriptor, "fixture-reader")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)
    result = kernel.run("Summarize the harmless fixture.", cwd=tmp_path, output_dir=tmp_path / "runs", timeout_seconds=5)

    assert cache.get(descriptor) == "fixture-reader"
    assert route_key == descriptor.compatibility_key()
    assert calls[0][0][1] == "exec"
    assert calls[0][0][-1] == "-"
    assert calls[0][1]["input"] == "Summarize the harmless fixture."
    assert calls[0][1]["timeout"] == 5
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.last_message == "fixture complete"

    payload = json.loads(result.result_path.read_text(encoding="utf-8"))
    latest = json.loads((tmp_path / "runs" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert payload["timed_out"] is False
    assert payload["stdout_tail"] == "trace: ok\n"
    assert latest == payload


def test_local_agent_harness_smoke_captures_timeout_result(tmp_path):
    def timeout_runner(command, **kwargs):
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("partial fixture trace")
        raise subprocess.TimeoutExpired(command, timeout=2, output="before timeout", stderr=b"")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=timeout_runner)

    with pytest.raises(TimeoutError, match="Codex CLI timed out after 2 seconds"):
        kernel.run("Exercise timeout capture.", cwd=tmp_path, output_dir=tmp_path / "runs", timeout_seconds=2)

    latest = json.loads((tmp_path / "runs" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["returncode"] == 124
    assert latest["timed_out"] is True
    assert latest["stdout_tail"] == "before timeout"
    assert latest["stderr_tail"] == "Timed out after 2 seconds."
    assert latest["last_message"] == "partial fixture trace"
