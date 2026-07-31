import json
import subprocess

import pytest

from blackhole_agent.github_growth import (
    SelfEvolutionPlan,
    run_proposal_interpretation_kernel,
    run_self_evolution_kimi,
)
from blackhole_agent.kernels.kimi_cli import (
    KimiCliConfig,
    KimiCliKernel,
    build_kimi_command,
    build_kimi_provider_preflight,
    extract_kimi_stream,
)
from blackhole_agent.supervisor import SupervisorConfig, build_wake_command
from blackhole_agent.self_model import read_self_model_snapshot


def kimi_stream(message: str, *, session_id: str = "session-kimi-123") -> str:
    return "\n".join(
        [
            json.dumps({"role": "assistant", "content": message}),
            json.dumps(
                {
                    "role": "meta",
                    "type": "session.resume_hint",
                    "session_id": session_id,
                }
            ),
        ]
    )


def test_build_kimi_command_uses_native_prompt_mode_and_resume(monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: "C:/tools/kimi.exe")
    command = build_kimi_command(
        KimiCliConfig(
            model="kimi-model",
            resume_session_id="session-existing",
        ),
        prompt="Continue the mission.",
    )

    assert command[0] == "C:/tools/kimi.exe"
    assert command[command.index("--model") + 1] == "kimi-model"
    assert command[command.index("--session") + 1] == "session-existing"
    assert "--auto" not in command
    assert "--plan" not in command
    assert "--yolo" not in command
    assert command[command.index("--output-format") + 1] == "stream-json"
    assert command[command.index("--prompt") + 1] == "Continue the mission."


def test_kimi_kernel_writes_artifacts_extracts_session_and_redacts_recorded_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: "C:/tools/kimi.exe")
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        assert command[command.index("--prompt") + 1] == "Implement the capability."
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=kimi_stream("Implemented and validated."),
            stderr="",
        )

    result = KimiCliKernel(
        KimiCliConfig(model="kimi-model", require_explicit_route=True),
        command_runner=runner,
    ).run(
        "Implement the capability.",
        cwd=tmp_path,
        output_dir=tmp_path / "out",
        timeout_seconds=30,
    )

    assert result.returncode == 0
    assert result.last_message == "Implemented and validated."
    assert result.session_id == "session-kimi-123"
    assert result.last_message_path.read_text(encoding="utf-8") == "Implemented and validated."
    assert result.task_path.read_text(encoding="utf-8") == "Implement the capability."
    assert result.command[result.command.index("--prompt") + 1].startswith("<prompt stored at ")
    assert "Implement the capability." not in json.dumps(result.command)
    assert (tmp_path / "out" / "latest-kimi-run.json").exists()
    assert seen["kwargs"]["cwd"] == tmp_path


def test_kimi_kernel_preserves_failure_artifact_before_raising(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: "C:/tools/kimi.exe")

    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="authentication failed")

    kernel = KimiCliKernel(KimiCliConfig(model="kimi-model"), command_runner=runner)
    with pytest.raises(RuntimeError, match="exit code 7"):
        kernel.run("Task", cwd=tmp_path, output_dir=tmp_path / "out")

    payload = json.loads((tmp_path / "out" / "latest-kimi-run.json").read_text(encoding="utf-8"))
    assert payload["returncode"] == 7
    assert payload["stderr_tail"] == "authentication failed"
    assert payload["session_id"] == ""


def test_kimi_preflight_requires_binary_and_explicit_model(monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: None)
    preflight = build_kimi_provider_preflight(KimiCliConfig(require_explicit_route=True), env={})

    assert preflight["ok"] is False
    assert preflight["diagnostics"] == [
        "kimi executable was not found on PATH",
        "kimi mode requires an explicit --model to avoid implicit provider fallback",
    ]
    assert preflight["token_value_recorded"] is False


def test_kimi_preflight_rejects_flags_incompatible_with_native_prompt_mode(monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: "C:/tools/kimi.exe")
    preflight = build_kimi_provider_preflight(
        KimiCliConfig(extra_args=("--auto", "--plan", "--yolo")),
        env={},
    )

    assert preflight["ok"] is False
    assert preflight["incompatible_prompt_flags"] == ["--auto", "--plan", "--yolo"]
    assert preflight["diagnostics"] == [
        "kimi prompt mode cannot be combined with permission or plan flags: --auto, --plan, --yolo"
    ]


def test_extract_kimi_stream_collects_messages_session_and_tool_names():
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "role": "assistant",
                    "content": "Working.",
                    "tool_calls": [{"function": {"name": "Shell"}}],
                }
            ),
            json.dumps({"role": "assistant", "content": "Complete."}),
            json.dumps(
                {
                    "role": "meta",
                    "type": "session.resume_hint",
                    "session_id": "session-final",
                }
            ),
        ]
    )

    message, session_id, tool_titles = extract_kimi_stream(stdout)

    assert message == "Working.\nComplete."
    assert session_id == "session-final"
    assert tool_titles == ("Shell",)


def test_proposal_interpretation_selects_native_kimi_prompt_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: "C:/tools/kimi.exe")
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=kimi_stream('{"schema_version":1,"proposals":[]}'),
            stderr="",
        )

    message = run_proposal_interpretation_kernel(
        {"digest_id": "digest-1", "items": []},
        output_dir=tmp_path / "artifacts",
        repo_path=tmp_path,
        kernel="kimi",
        command_runner=runner,
    )

    assert message == '{"schema_version":1,"proposals":[]}'
    assert "--plan" not in seen["command"]
    assert "--auto" not in seen["command"]


def test_self_evolution_kimi_writes_native_kernel_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("blackhole_agent.kernels.kimi_cli.shutil.which", lambda _: "C:/tools/kimi.exe")
    plan = SelfEvolutionPlan(
        generated_at="2026-07-31T00:00:00Z",
        repo_path=str(tmp_path),
        branch_name="kimi/evolve",
        self_model_path="docs/self-model.md",
        self_model_before=read_self_model_snapshot(tmp_path),
        task="Implement one capability.",
        proposals=[],
        source_digest_id="digest-kimi",
        source_digest_generated_at="2026-07-31T00:00:00Z",
    )

    def runner(command, **kwargs):
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="head-kimi\n", stderr="")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=kimi_stream("Kimi mutation complete."),
            stderr="",
        )

    result = run_self_evolution_kimi(
        plan,
        output_dir=tmp_path / "out",
        model="kimi-model",
        command_runner=runner,
    )

    manifest = json.loads((tmp_path / "out" / "latest-self-evolution-manifest.json").read_text(encoding="utf-8"))
    run_metadata = json.loads((tmp_path / "out" / "latest-self-evolution-run.json").read_text(encoding="utf-8"))
    assert result.last_message == "Kimi mutation complete."
    assert manifest["kernel"] == "kimi"
    assert manifest["target_head"] == "head-kimi"
    assert manifest["session_id"] == "session-kimi-123"
    assert manifest["kimi_cli"]["permission_mode_source"] == "native_prompt_mode"
    assert run_metadata["kernel"] == "kimi"
    assert "Implement one capability." not in json.dumps(run_metadata["command"])


def test_supervisor_wake_command_selects_kimi_kernel(tmp_path):
    config = SupervisorConfig(
        repo_path=tmp_path,
        kernel="kimi",
        model="kimi-model",
        branch_prefix="kimi/blackhole-evolve",
    )
    command = build_wake_command(config)

    assert command[command.index("--kernel") + 1] == "kimi"
    assert command[command.index("--model") + 1] == "kimi-model"
    assert command[command.index("--branch-prefix") + 1] == "kimi/blackhole-evolve"
