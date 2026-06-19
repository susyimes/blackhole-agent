import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import blackhole_agent.kernels.codex_cli as codex_cli
from blackhole_agent.kernels.codex_cli import (
    CodexCliConfig,
    CodexCliKernel,
    CodexStreamChunk,
    CodexStreamTimeoutError,
    assemble_codex_stream_chunks,
    build_ambient_google_preflight,
    build_ambient_openai_preflight,
    build_codex_exec_command,
    build_codex_provider_preflight,
    cleanup_orphaned_process_tree,
    shutdown_subprocess_cli_transport_stderr,
)


def test_build_codex_exec_command_reads_task_from_stdin(tmp_path):
    command = build_codex_exec_command(
        CodexCliConfig(model="gpt-5", profile="work", skip_git_repo_check=True),
        cwd=tmp_path,
        output_last_message=tmp_path / "last.md",
    )

    assert command[1:4] == ["exec", "--cd", str(tmp_path)]
    assert ["--model", "gpt-5"] == command[command.index("--model") : command.index("--model") + 2]
    assert ["--profile", "work"] == command[command.index("--profile") : command.index("--profile") + 2]
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert "--skip-git-repo-check" in command
    assert "--ask-for-approval" not in command
    assert command[-1] == "-"


def test_codex_kernel_writes_task_and_result_files(tmp_path):
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("done")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)
    result = kernel.run("Improve tests", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=12)

    assert calls[0][0][1] == "exec"
    assert calls[0][0][-1] == "-"
    assert calls[0][1]["input"] == "Improve tests"
    assert calls[0][1]["timeout"] == 12
    assert result.returncode == 0
    assert result.last_message == "done"
    assert result.task_path.read_text(encoding="utf-8") == "Improve tests"
    latest = json.loads((tmp_path / "out" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["last_message"] == "done"
    assert latest["provider_preflight"]["selected_provider"] == "codex_cli"


def test_codex_provider_preflight_blocks_implicit_default_route_when_required():
    preflight = build_codex_provider_preflight(CodexCliConfig(require_explicit_route=True), env={})

    assert preflight["ok"] is False
    assert preflight["selected_provider"] == "codex_cli"
    assert preflight["route_selector"] == "implicit_default"
    assert preflight["diagnostics"] == [
        "codex mode requires an explicit --model or --profile to avoid implicit provider fallback"
    ]
    assert preflight["recovery_hints"] == [
        {
            "code": "explicit_codex_route_required",
            "scope": "codex_route",
            "action": "configure --model or --profile before codex mode starts, or explicitly allow the default route",
            "env_names": [],
            "value_recorded": False,
        }
    ]
    assert preflight["token_value_recorded"] is False
    assert preflight["profile_value_recorded"] is False


def test_codex_provider_preflight_accepts_explicit_model_or_profile():
    model_preflight = build_codex_provider_preflight(
        CodexCliConfig(model="gpt-5.5", require_explicit_route=True),
        env={},
    )
    profile_preflight = build_codex_provider_preflight(
        CodexCliConfig(profile="work", require_explicit_route=True),
        env={},
    )

    assert model_preflight["ok"] is True
    assert model_preflight["route_selector"] == "model"
    assert model_preflight["model"] == "gpt-5.5"
    assert profile_preflight["ok"] is True
    assert profile_preflight["route_selector"] == "profile"
    assert profile_preflight["profile_present"] is True
    assert profile_preflight["profile_value_recorded"] is False


def test_codex_provider_preflight_records_ambient_openai_matrix_without_values():
    secret_key = "sk-PRIVATE-OPENAI-TOKEN-DO-NOT-EXPORT"
    private_base_url = "https://gateway.example.invalid/private-openai-route"
    cases = [
        (
            {},
            {
                "provider_family": None,
                "route_hint": "not_configured",
                "endpoint_source": None,
                "api_key_present": False,
                "base_url_present": False,
                "diagnostics": [],
            },
        ),
        (
            {"OPENAI_API_KEY": secret_key},
            {
                "provider_family": "openai",
                "route_hint": "openai_default_endpoint",
                "endpoint_source": "default_openai",
                "api_key_present": True,
                "base_url_present": False,
                "diagnostics": [],
            },
        ),
        (
            {"OPENAI_BASE_URL": private_base_url},
            {
                "provider_family": None,
                "route_hint": "base_url_without_api_key",
                "endpoint_source": "OPENAI_BASE_URL",
                "api_key_present": False,
                "base_url_present": True,
                "diagnostics": [
                    "OPENAI_BASE_URL is present without OPENAI_API_KEY; ambient OpenAI credentials are incomplete"
                ],
            },
        ),
        (
            {"OPENAI_API_KEY": secret_key, "OPENAI_BASE_URL": private_base_url},
            {
                "provider_family": "openai",
                "route_hint": "openai_compatible_gateway",
                "endpoint_source": "OPENAI_BASE_URL",
                "api_key_present": True,
                "base_url_present": True,
                "diagnostics": [],
            },
        ),
    ]

    for env, expected in cases:
        preflight = build_codex_provider_preflight(CodexCliConfig(), env=env)
        ambient_openai = preflight["ambient_openai"]
        serialized = json.dumps(preflight, sort_keys=True)

        assert ambient_openai["schema_version"] == 1
        assert ambient_openai["api_key_env"] == "OPENAI_API_KEY"
        assert ambient_openai["base_url_env"] == "OPENAI_BASE_URL"
        assert ambient_openai["api_key_value_recorded"] is False
        assert ambient_openai["base_url_value_recorded"] is False
        for key, value in expected.items():
            assert ambient_openai[key] == value
        assert secret_key not in serialized
        assert private_base_url not in serialized


def test_ambient_openai_preflight_treats_blank_env_values_as_absent():
    ambient_openai = build_ambient_openai_preflight(
        {
            "OPENAI_API_KEY": "   ",
            "OPENAI_BASE_URL": "\t",
        }
    )

    assert ambient_openai["route_hint"] == "not_configured"
    assert ambient_openai["api_key_present"] is False
    assert ambient_openai["base_url_present"] is False
    assert ambient_openai["api_key_value_recorded"] is False
    assert ambient_openai["base_url_value_recorded"] is False


def test_codex_provider_preflight_rejects_placeholder_openai_key_without_leaking_value():
    placeholder_key = "sk-dummy-token-for-ci"

    preflight = build_codex_provider_preflight(
        CodexCliConfig(model="gpt-5.5", require_explicit_route=True),
        env={"OPENAI_API_KEY": placeholder_key, "OPENAI_BASE_URL": "https://gateway.example.invalid/private"},
    )

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["ambient_openai"]["api_key_present"] is True
    assert preflight["ambient_openai"]["api_key_usable"] is False
    assert preflight["ambient_openai"]["api_key_quality"] == "placeholder"
    assert preflight["ambient_openai"]["route_hint"] == "placeholder_api_key"
    assert preflight["diagnostics"] == [
        "OPENAI_API_KEY is a placeholder value; ambient OpenAI credentials are invalid",
        "OPENAI_BASE_URL is present without OPENAI_API_KEY; ambient OpenAI credentials are incomplete",
    ]
    assert preflight["recovery_hints"] == [
        {
            "code": "replace_openai_placeholder_key",
            "scope": "ambient_openai",
            "action": "replace the placeholder OpenAI API key with a real credential or unset the variable",
            "env_names": ["OPENAI_API_KEY"],
            "value_recorded": False,
        }
    ]
    assert placeholder_key not in rendered
    assert "gateway.example.invalid" not in rendered


def test_codex_provider_preflight_records_ambient_google_warnings_without_values():
    private_key = "GOOGLE-PRIVATE-KEY-DO-NOT-EXPORT"
    private_credentials_path = "C:/private/google/application-default-credentials.json"

    cases = [
        (
            {},
            {
                "provider_family": None,
                "route_hint": "not_configured",
                "api_key_present": False,
                "api_key_present_envs": [],
                "application_credentials_present": False,
                "diagnostics": [],
            },
        ),
        (
            {"GOOGLE_API_KEY": private_key},
            {
                "provider_family": "google",
                "route_hint": "google_api_key",
                "api_key_present": True,
                "api_key_present_envs": ["GOOGLE_API_KEY"],
                "application_credentials_present": False,
                "diagnostics": [],
            },
        ),
        (
            {"GEMINI_API_KEY": private_key},
            {
                "provider_family": "google",
                "route_hint": "google_api_key",
                "api_key_present": True,
                "api_key_present_envs": ["GEMINI_API_KEY"],
                "application_credentials_present": False,
                "diagnostics": [],
            },
        ),
        (
            {"GOOGLE_APPLICATION_CREDENTIALS": private_credentials_path},
            {
                "provider_family": "google",
                "route_hint": "google_application_credentials_without_api_key",
                "api_key_present": False,
                "api_key_present_envs": [],
                "application_credentials_present": True,
                "diagnostics": [
                    "GOOGLE_APPLICATION_CREDENTIALS is present without GOOGLE_API_KEY or GEMINI_API_KEY; "
                    "ambient Google API-key credentials are incomplete"
                ],
            },
        ),
        (
            {"GOOGLE_API_KEY": private_key, "GOOGLE_APPLICATION_CREDENTIALS": private_credentials_path},
            {
                "provider_family": "google",
                "route_hint": "google_api_key_and_application_credentials",
                "api_key_present": True,
                "api_key_present_envs": ["GOOGLE_API_KEY"],
                "application_credentials_present": True,
                "diagnostics": [],
            },
        ),
    ]

    for env, expected in cases:
        preflight = build_codex_provider_preflight(CodexCliConfig(), env=env)
        ambient_google = preflight["ambient_google"]
        serialized = json.dumps(preflight, sort_keys=True)

        assert ambient_google["schema_version"] == 1
        assert ambient_google["api_key_envs"] == ["GOOGLE_API_KEY", "GEMINI_API_KEY"]
        assert ambient_google["api_key_values_recorded"] is False
        assert ambient_google["application_credentials_env"] == "GOOGLE_APPLICATION_CREDENTIALS"
        assert ambient_google["application_credentials_value_recorded"] is False
        for key, value in expected.items():
            assert ambient_google[key] == value
        assert private_key not in serialized
        assert private_credentials_path not in serialized


def test_ambient_google_preflight_treats_blank_env_values_as_absent():
    ambient_google = build_ambient_google_preflight(
        {
            "GOOGLE_API_KEY": " ",
            "GEMINI_API_KEY": "\t",
            "GOOGLE_APPLICATION_CREDENTIALS": "",
        }
    )

    assert ambient_google["route_hint"] == "not_configured"
    assert ambient_google["api_key_present"] is False
    assert ambient_google["application_credentials_present"] is False
    assert ambient_google["api_key_values_recorded"] is False
    assert ambient_google["application_credentials_value_recorded"] is False


def test_codex_provider_preflight_rejects_placeholder_google_key_without_leaking_value():
    placeholder_key = "dummy-google-key"

    preflight = build_codex_provider_preflight(
        CodexCliConfig(model="gpt-5.5", require_explicit_route=True),
        env={"GEMINI_API_KEY": placeholder_key},
    )

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["ambient_google"]["api_key_present"] is True
    assert preflight["ambient_google"]["api_key_usable"] is False
    assert preflight["ambient_google"]["api_key_placeholder_envs"] == ["GEMINI_API_KEY"]
    assert preflight["diagnostics"] == [
        "Google API key environment contains a placeholder value; ambient Google credentials are invalid"
    ]
    assert preflight["recovery_hints"] == [
        {
            "code": "replace_google_placeholder_key",
            "scope": "ambient_google",
            "action": "replace placeholder Google API-key environment values with real credentials or unset them",
            "env_names": ["GEMINI_API_KEY"],
            "value_recorded": False,
        }
    ]
    assert placeholder_key not in rendered


def test_codex_provider_preflight_recovery_hints_cover_incomplete_ambient_routes_without_values():
    private_base_url = "https://gateway.example.invalid/private-openai-route"
    private_credentials_path = "C:/private/google/application-default-credentials.json"

    preflight = build_codex_provider_preflight(
        CodexCliConfig(model="gpt-5.5"),
        env={
            "OPENAI_BASE_URL": private_base_url,
            "GOOGLE_APPLICATION_CREDENTIALS": private_credentials_path,
        },
    )

    rendered = json.dumps(preflight, sort_keys=True)
    assert preflight["ok"] is False
    assert preflight["recovery_hints"] == [
        {
            "code": "complete_openai_gateway_credentials",
            "scope": "ambient_openai",
            "action": "set OPENAI_API_KEY for the configured OpenAI-compatible endpoint or unset OPENAI_BASE_URL",
            "env_names": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
            "value_recorded": False,
        },
        {
            "code": "complete_google_api_key_credentials",
            "scope": "ambient_google",
            "action": "set GOOGLE_API_KEY or GEMINI_API_KEY when Google application credentials are present",
            "env_names": ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"],
            "value_recorded": False,
        },
    ]
    assert private_base_url not in rendered
    assert private_credentials_path not in rendered


def test_codex_kernel_fails_before_exec_when_route_is_implicit(tmp_path):
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="unexpected", stderr="")

    kernel = CodexCliKernel(
        CodexCliConfig(codex_bin="codex", require_explicit_route=True),
        command_runner=fake_runner,
    )

    with pytest.raises(ValueError, match="Codex provider/config preflight failed"):
        kernel.run("Improve tests", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=12)

    assert calls == []
    latest = json.loads((tmp_path / "out" / "latest-codex-provider-preflight.json").read_text(encoding="utf-8"))
    assert latest["ok"] is False
    assert latest["route_selector"] == "implicit_default"


def test_codex_kernel_preserves_long_nested_local_paths_in_command_and_artifacts(tmp_path):
    workspace = (
        tmp_path
        / ".bh-worktrees"
        / "20260616T133522Z"
        / "nested-local-workspace"
    )
    output_dir = workspace / ".blackhole-agent" / "codex"
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        last_message = command[command.index("--output-last-message") + 1]
        Path(last_message).write_text("done from nested workspace", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)
    result = kernel.run("Exercise nested path handling", cwd=workspace, output_dir=output_dir, timeout_seconds=12)

    command = calls[0][0]
    assert command[command.index("--cd") + 1] == str(workspace)
    assert command[command.index("--output-last-message") + 1] == str(result.last_message_path)
    assert result.last_message_path.is_absolute()
    assert str(result.last_message_path).startswith(str(output_dir))

    latest = json.loads((output_dir / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["cwd"] == str(workspace)
    assert latest["task_path"] == str(result.task_path)
    assert latest["last_message_path"] == str(result.last_message_path)
    assert latest["result_path"] == str(result.result_path)
    serialized_cwd = latest["cwd"].replace("\\", "/")
    assert serialized_cwd.startswith(str(tmp_path).replace("\\", "/"))
    assert not serialized_cwd.startswith(f"/{workspace.name}/")


def test_build_codex_exec_command_can_bypass_sandbox(tmp_path):
    command = build_codex_exec_command(
        CodexCliConfig(bypass_approvals_and_sandbox=True),
        cwd=tmp_path,
        output_last_message=tmp_path / "last.md",
    )

    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--sandbox" not in command


def test_codex_kernel_raises_on_nonzero_exit_after_writing_result(tmp_path):
    def fake_runner(command, **kwargs):
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("partial failure details")
        return subprocess.CompletedProcess(command, 7, stdout="partial stdout", stderr="boom")

    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)

    with pytest.raises(RuntimeError, match="Codex CLI failed with exit code 7"):
        kernel.run("Improve tests", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=12)

    latest = json.loads((tmp_path / "out" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["returncode"] == 7
    assert latest["last_message"] == "partial failure details"
    assert latest["stderr_tail"] == "boom"


def test_codex_kernel_cancel_recover_uses_fresh_artifacts_for_same_second(tmp_path, monkeypatch):
    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 16, 9, 17, 3, tzinfo=timezone.utc)

    attempts = 0
    last_message_paths = []

    def fake_runner(command, **kwargs):
        nonlocal attempts
        attempts += 1
        last_message = command[command.index("--output-last-message") + 1]
        last_message_paths.append(last_message)
        if attempts == 1:
            with open(last_message, "w", encoding="utf-8") as handle:
                handle.write("partial state from interrupted run")
            raise subprocess.TimeoutExpired(command, timeout=1, output="started", stderr="")
        assert not Path(last_message).exists()
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("recovered cleanly")
        return subprocess.CompletedProcess(command, 0, stdout="finished", stderr="")

    monkeypatch.setattr(codex_cli, "datetime", FixedDatetime)
    kernel = CodexCliKernel(CodexCliConfig(codex_bin="codex"), command_runner=fake_runner)

    with pytest.raises(TimeoutError, match="Codex CLI timed out after 1 seconds"):
        kernel.run("Interruptible task", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=1)
    result = kernel.run("Recover task", cwd=tmp_path, output_dir=tmp_path / "out", timeout_seconds=5)

    assert last_message_paths[0] != last_message_paths[1]
    assert Path(last_message_paths[0]).read_text(encoding="utf-8") == "partial state from interrupted run"
    assert result.last_message == "recovered cleanly"
    assert result.returncode == 0
    assert result.timed_out is False

    latest = json.loads((tmp_path / "out" / "latest-codex-run.json").read_text(encoding="utf-8"))
    assert latest["last_message"] == "recovered cleanly"
    assert latest["timed_out"] is False
    assert latest["result_path"].endswith("codex-run-20260616T091703Z-001.json")


def test_codex_stream_assembler_flushes_split_paragraphs_and_completion():
    result = assemble_codex_stream_chunks(
        [
            CodexStreamChunk(0.0, "I'm drilling into runner now: first the module boundaries, then "),
            CodexStreamChunk(0.4, "the control path for policies, transports, and folder names."),
            CodexStreamChunk(0.8, "\n"),
            CodexStreamChunk(1.1, "\nI have the runner's main HTTP app now."),
            CodexStreamChunk(1.2, completed=True),
        ],
        idle_timeout_seconds=2,
    )

    assert result.completed is True
    assert result.paragraphs == [
        "I'm drilling into runner now: first the module boundaries, then "
        "the control path for policies, transports, and folder names.",
        "I have the runner's main HTTP app now.",
    ]


def test_codex_stream_assembler_handles_windows_paragraph_boundaries():
    result = assemble_codex_stream_chunks(
        [
            CodexStreamChunk(0.0, "First paragraph.\r"),
            CodexStreamChunk(0.1, "\n\r\nSecond paragraph."),
            CodexStreamChunk(0.2, completed=True),
        ],
        idle_timeout_seconds=1,
    )

    assert result.paragraphs == ["First paragraph.", "Second paragraph."]


def test_codex_stream_assembler_detects_idle_hang_before_completion():
    with pytest.raises(CodexStreamTimeoutError, match="stalled for 5 seconds"):
        assemble_codex_stream_chunks(
            [
                CodexStreamChunk(0.0, "Partial reasoning that has not completed"),
                CodexStreamChunk(5.0, " and arrives too late."),
                CodexStreamChunk(5.1, completed=True),
            ],
            idle_timeout_seconds=2,
        )


def test_codex_stream_assembler_requires_completion_marker():
    with pytest.raises(CodexStreamTimeoutError, match="ended without a completion marker"):
        assemble_codex_stream_chunks(
            [
                CodexStreamChunk(0.0, "Buffered final sentence."),
                CodexStreamChunk(0.1, "\n\nNext paragraph."),
            ],
            idle_timeout_seconds=2,
        )


def test_shutdown_subprocess_cli_transport_stderr_treats_absent_task_group_as_already_closed(caplog):
    class TransportWithoutStderrTaskGroup:
        pass

    caplog.set_level(logging.DEBUG, logger=codex_cli.__name__)

    cleaned = shutdown_subprocess_cli_transport_stderr(TransportWithoutStderrTaskGroup())

    assert cleaned is False
    assert "_stderr_task_group is absent" in caplog.text


def test_shutdown_subprocess_cli_transport_stderr_is_idempotent_after_cancel_scope(caplog):
    class CancelScope:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    class TaskGroup:
        def __init__(self):
            self.cancel_scope = CancelScope()

    class Transport:
        def __init__(self):
            self._stderr_task_group = TaskGroup()

    transport = Transport()
    task_group = transport._stderr_task_group
    caplog.set_level(logging.DEBUG, logger=codex_cli.__name__)

    first_cleaned = shutdown_subprocess_cli_transport_stderr(transport)
    second_cleaned = shutdown_subprocess_cli_transport_stderr(transport)

    assert first_cleaned is True
    assert task_group.cancel_scope.cancelled is True
    assert transport._stderr_task_group is None
    assert second_cleaned is False
    assert "_stderr_task_group is already cleared" in caplog.text


def test_cleanup_orphaned_process_tree_terminates_children_before_parent_and_kills_stubborn_child():
    events = []

    class FakeProcess:
        def __init__(self, pid, *, children=None, exits_on_terminate=True):
            self.pid = pid
            self._children = children or []
            self._exits_on_terminate = exits_on_terminate
            self._terminated = False
            self._killed = False

        def children(self, recursive=True):
            events.append(("children", self.pid, recursive))
            return self._children

        def terminate(self):
            events.append(("terminate", self.pid))
            self._terminated = True

        def kill(self):
            events.append(("kill", self.pid))
            self._killed = True

        def wait(self, timeout=None):
            events.append(("wait", self.pid, timeout))
            if self._killed or (self._terminated and self._exits_on_terminate):
                return 0
            raise subprocess.TimeoutExpired(["fake-process"], timeout=timeout)

    child = FakeProcess(202, exits_on_terminate=False)
    root = FakeProcess(101, children=[child], exits_on_terminate=True)

    result = cleanup_orphaned_process_tree(root, grace_seconds=0.1)

    assert result.root_pid == 101
    assert result.child_pids == (202,)
    assert result.terminated_pids == (202, 101)
    assert result.killed_pids == (202,)
    assert result.timeout_pids == ()
    assert result.errors == ()
    assert result.all_exited is True
    assert events.index(("terminate", 202)) < events.index(("terminate", 101))
    assert ("kill", 202) in events


def test_cleanup_orphaned_process_tree_reports_processes_that_cannot_be_waited_or_killed():
    class UncooperativeProcess:
        pid = 303

        def terminate(self):
            return None

    result = cleanup_orphaned_process_tree(UncooperativeProcess(), grace_seconds=0.1)

    assert result.root_pid == 303
    assert result.terminated_pids == (303,)
    assert result.killed_pids == ()
    assert result.timeout_pids == (303,)
    assert result.all_exited is False
