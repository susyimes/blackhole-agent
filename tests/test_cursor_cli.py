import json
import subprocess

import pytest

from blackhole_agent.kernels.cursor_cli import (
    CursorCliConfig,
    CursorCliKernel,
    build_cursor_command,
    cursor_invocation_prefix,
    extract_cursor_result,
    resolve_cursor_binary,
)
from blackhole_agent.unbound import invoke_kernel_turn, resolve_unbound_kernel
from tests.test_unbound import make_state


def terminal(message='{"status":"continue"}', session="cursor-session"):
    return json.dumps(
        {"type": "result", "subtype": "success", "is_error": False, "result": message, "session_id": session}
    )


def test_discovery_never_uses_grok_agent_or_editor():
    calls = []

    def which(name):
        calls.append(name)
        return "C:/grok/agent.exe" if name == "agent" else None

    assert resolve_cursor_binary(environ={}, which=which) is None
    assert calls == ["cursor-agent"]


def test_windows_discovery_and_shell_free_launcher(tmp_path):
    root = tmp_path / "cursor-agent"
    version = root / "versions" / "2026.09.08-6caf4ff"
    version.mkdir(parents=True)
    (root / "cursor-agent.cmd").write_text("launcher")
    (version / "node.exe").touch()
    (version / "index.js").touch()
    binary = resolve_cursor_binary(environ={"LOCALAPPDATA": str(tmp_path)}, which=lambda _: None)
    assert binary == str(root / "cursor-agent.cmd")
    assert cursor_invocation_prefix(binary) == [str(version / "node.exe"), str(version / "index.js")]


def test_command_preserves_model_resume_and_workspace(tmp_path):
    command = build_cursor_command(
        CursorCliConfig(model="model[effort=high]", resume_session_id="session-1"), binary="cursor-agent", cwd=tmp_path
    )
    assert command[:4] == ["cursor-agent", "--print", "--output-format", "stream-json"]
    assert command[command.index("--resume") + 1] == "session-1"
    assert command[command.index("--model") + 1] == "model[effort=high]"
    assert "--force" in command
    assert "--continue" not in command and "--worktree" not in command


def test_stream_uses_terminal_result_not_assistant_flushes():
    stream = "\n".join(
        [json.dumps({"type": "assistant", "message": {"content": [{"text": "partial"}]}}), terminal("完成")]
    )
    assert extract_cursor_result(stream) == ("完成", "cursor-session", "")
    assert extract_cursor_result('{"type":"assistant","text":"partial"}')[2] == "missing terminal result"


def test_long_unicode_prompt_stdin_and_unique_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.cursor_cli.resolve_cursor_binary", lambda *_: "cursor-agent")
    prompt = '中文 "quotes" & $values\n' * 3000
    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["input"] == prompt
        assert kwargs["encoding"] == "utf-8" and kwargs["errors"] == "replace"
        assert len(subprocess.list2cmdline(command)) < 2000
        return subprocess.CompletedProcess(command, 0, stdout=terminal("完成"), stderr="")

    kernel = CursorCliKernel(command_runner=runner)
    first = kernel.run(prompt, cwd=tmp_path, output_dir=tmp_path)
    second = kernel.run(prompt, cwd=tmp_path, output_dir=tmp_path)
    assert first.result_path != second.result_path
    assert first.task_path.read_text(encoding="utf-8") == prompt
    assert first.last_message == "完成"
    assert prompt not in first.result_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "stdout,code",
    [
        ("not json", 0),
        (terminal(""), 0),
        ('{"type":"result","subtype":"error","is_error":true,"result":"unauthorized"}', 0),
        (terminal(), 1),
        (terminal(session=""), 0),
    ],
)
def test_bad_output_never_succeeds_and_persists_evidence(tmp_path, monkeypatch, stdout, code):
    monkeypatch.setattr("blackhole_agent.kernels.cursor_cli.resolve_cursor_binary", lambda *_: "cursor-agent")
    kernel = CursorCliKernel(command_runner=lambda cmd, **kw: subprocess.CompletedProcess(cmd, code, stdout, ""))
    with pytest.raises(RuntimeError):
        kernel.run("test", cwd=tmp_path, output_dir=tmp_path)
    assert (tmp_path / "latest-cursor-run.json").is_file()


def test_timeout_records_partial_session_but_not_completion(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.cursor_cli.resolve_cursor_binary", lambda *_: "cursor-agent")

    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd, 1, output=b'{"type":"system","session_id":"partial-id"}', stderr=b"\xfftimeout"
        )

    with pytest.raises(TimeoutError):
        CursorCliKernel(command_runner=timeout).run("test", cwd=tmp_path, output_dir=tmp_path, timeout_seconds=1)
    payload = json.loads((tmp_path / "latest-cursor-run.json").read_text(encoding="utf-8"))
    assert payload["timed_out"] and payload["session_id"] == "partial-id"
    assert payload["last_message"] == ""


def test_unbound_cursor_native_session_resume(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.cursor_cli.resolve_cursor_binary", lambda *_: "cursor-agent")
    seen = []

    def runner(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, terminal(), "")

    state = make_state(tmp_path, kernel="cursor", model="auto", session_id="", session_started=False)
    first = invoke_kernel_turn(state, "first", tmp_path / "one", command_runner=runner)
    state.session_id, state.session_started = first.session_id, True
    second = invoke_kernel_turn(state, "second", tmp_path / "two", command_runner=runner)
    assert first.kernel == second.kernel == "cursor"
    assert "--resume" not in seen[0]
    assert seen[1][seen[1].index("--resume") + 1] == "cursor-session"


def test_auto_resolves_cursor_cli_not_optional_sdk():
    assert resolve_unbound_kernel("auto", available_commands={"cursor-agent"}, environ={})[0] == "cursor"
    with pytest.raises(ValueError):
        resolve_unbound_kernel("auto", available_commands={"agent", "cursor"}, environ={})


def test_cursor_partial_decision_cannot_be_salvaged():
    from blackhole_agent.kernel_salvage import salvage_kernel_failure

    result = salvage_kernel_failure(
        error="timeout", current_kernel="cursor", installed_kernels=[], allow_failover=False,
        artifact={"returncode": 124, "timed_out": True, "decision_final": False,
                  "last_message": '{"status":"complete","done_when_met":true}'},
    )
    assert result.source == "synthesized" and result.decision["status"] != "complete"


def test_failure_artifacts_do_not_cross_provider_routes(tmp_path):
    from blackhole_agent.kernel_salvage import load_kernel_run_artifact, _switch_kernel

    directory = tmp_path / "kernel"
    directory.mkdir()
    (directory / "latest-cursor-run.json").write_text('{"returncode":1,"stderr_tail":"unauthorized"}')
    (directory / "latest-grok-run.json").write_text('{"returncode":124,"timed_out":true}')
    assert load_kernel_run_artifact(tmp_path, kernel="grok")["timed_out"]
    state = make_state(tmp_path, kernel="grok", model="grok-4.6", session_id="grok-session", session_started=True)
    _switch_kernel(state, "cursor")
    assert state.model is None and state.session_id == "" and not state.session_started
