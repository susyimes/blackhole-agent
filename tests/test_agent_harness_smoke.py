import json
import subprocess

import pytest

from blackhole_agent.kernels.codex_cli import (
    CodexCliConfig,
    CodexCliKernel,
    summarize_codex_local_execution_controls,
)
from blackhole_agent.tool_routing import ToolCompatibilityCache, ToolDescriptor


def test_local_agent_harness_smoke_captures_runner_result_and_tool_route(tmp_path, monkeypatch):
    """Harmless fixture task: invoke a fake local runner and route one local tool."""

    for env_name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(env_name, raising=False)

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

    controls = summarize_codex_local_execution_controls(
        result.command,
        runner_kwargs=calls[0][1],
        provider_preflight=result.provider_preflight,
    )
    assert controls.to_dict() == {
        "network_required": False,
        "credentials_required": False,
        "destructive_filesystem_requested": False,
        "shell_invoked": False,
        "stdin_task": True,
        "local_cwd_configured": True,
        "artifacts_configured": True,
        "local_only": True,
    }
    assert result.provider_preflight["ambient_openai"]["api_key_present"] is False
    assert result.provider_preflight["ambient_openai"]["base_url_present"] is False
    assert result.provider_preflight["ambient_google"]["api_key_present"] is False
    assert result.provider_preflight["ambient_google"]["application_credentials_present"] is False

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


def test_local_agent_harness_smoke_rejects_network_credentials_shell_and_destructive_hints(tmp_path):
    provider_preflight = {
        "ambient_openai": {
            "api_key_present": True,
            "base_url_present": False,
        },
        "ambient_google": {
            "api_key_present": False,
            "application_credentials_present": False,
        },
    }
    command = [
        "codex",
        "exec",
        "--cd",
        str(tmp_path),
        "--output-last-message",
        str(tmp_path / "last.md"),
        "--dangerously-bypass-approvals-and-sandbox",
        "https://example.invalid/task",
        "-",
    ]

    controls = summarize_codex_local_execution_controls(
        command,
        runner_kwargs={
            "cwd": tmp_path,
            "input": "fixture task",
            "capture_output": True,
            "text": True,
            "shell": True,
        },
        provider_preflight=provider_preflight,
    )

    assert controls.local_only is False
    assert controls.network_required is True
    assert controls.credentials_required is True
    assert controls.destructive_filesystem_requested is True
    assert controls.shell_invoked is True
