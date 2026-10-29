"""Local Grok CLI kernel used by blackhole-agent growth passes.

Windows controller launches leave ``HOME`` and ``GROK_HOME`` unset. Grok then
logs ``auto worktree gc failed`` because it does not read ``USERPROFILE``, and
its own session worktrees are never collected. The launch environment fills
``HOME`` from an existing profile directory unless a home is already set.

The same launches inherit the controller ``PYTHONHOME``. Plugin commands such
as ``uvx --python 3.12`` then load that prefix's standard library and die
before they can answer an MCP initialize request. The launch environment
drops ``PYTHONHOME`` so each plugin interpreter keeps its own prefix.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from blackhole_agent.process_capture import run_captured_process

_DEFAULT_COMMAND_RUNNER = subprocess.run


@dataclass(frozen=True)
class GrokCliConfig:
    """Configuration for one headless Grok Build invocation."""

    grok_bin: str = "grok"
    model: str | None = None
    require_explicit_route: bool = False
    sandbox: str = "workspace"
    permission_mode: str = "bypassPermissions"
    output_format: str = "json"
    no_memory: bool = True
    no_subagents: bool = True
    disable_web_search: bool = True
    max_turns: int | None = None
    deny_rules: tuple[str, ...] = ("Bash(git commit *)", "Bash(git push *)")
    session_id: str | None = None
    resume_session_id: str | None = None
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrokCliRunResult:
    """Result of one headless Grok CLI kernel invocation."""

    command: list[str]
    provider_preflight: dict[str, Any]
    returncode: int
    timed_out: bool
    task_path: Path
    last_message_path: Path
    result_path: Path
    stdout_tail: str
    stderr_tail: str
    last_message: str


class GrokCliKernel:
    """Run a controller-shaped task through local headless Grok Build."""

    def __init__(
        self,
        config: GrokCliConfig | None = None,
        *,
        command_runner: Any = subprocess.run,
    ) -> None:
        self.config = config or GrokCliConfig()
        self._command_runner = command_runner

    def run(
        self,
        task: str,
        *,
        cwd: Path,
        output_dir: Path,
        timeout_seconds: int = 3600,
    ) -> GrokCliRunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_path, last_message_path, result_path = allocate_run_artifact_paths(output_dir, timestamp)
        task_path.write_text(task, encoding="utf-8")

        provider_preflight = build_grok_provider_preflight(self.config)
        preflight_path = output_dir / f"grok-provider-preflight-{timestamp}.json"
        preflight_text = json.dumps(provider_preflight, indent=2, sort_keys=True) + "\n"
        preflight_path.write_text(preflight_text, encoding="utf-8")
        (output_dir / "latest-grok-provider-preflight.json").write_text(preflight_text, encoding="utf-8")
        if not provider_preflight["ok"]:
            diagnostics = "; ".join(str(item) for item in provider_preflight["diagnostics"])
            raise ValueError(f"Grok provider/config preflight failed: {diagnostics}")

        command = build_grok_command(self.config, cwd=cwd, prompt_file=task_path)
        launch_env = grok_launch_environment()
        timed_out = False
        try:
            if self._command_runner is _DEFAULT_COMMAND_RUNNER:
                completed = run_captured_process(
                    command,
                    cwd=cwd,
                    timeout=timeout_seconds,
                    env=launch_env,
                )
            else:
                completed = self._command_runner(
                    command,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    env=launch_env,
                )
            returncode = int(completed.returncode)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as error:
            timed_out = True
            returncode = 124
            stdout = timeout_text(error.stdout)
            stderr = timeout_text(error.stderr) or f"Timed out after {timeout_seconds} seconds."

        last_message = extract_grok_last_message(stdout)
        if last_message:
            last_message_path.write_text(last_message, encoding="utf-8")
        result = GrokCliRunResult(
            command=command,
            provider_preflight=provider_preflight,
            returncode=returncode,
            timed_out=timed_out,
            task_path=task_path,
            last_message_path=last_message_path,
            result_path=result_path,
            stdout_tail=tail_text(stdout),
            stderr_tail=tail_text(stderr),
            last_message=last_message,
        )
        payload = serialize_run_result(result, cwd=cwd)
        result_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        result_path.write_text(result_text, encoding="utf-8")
        (output_dir / "latest-grok-run.json").write_text(result_text, encoding="utf-8")

        if result.timed_out:
            raise TimeoutError(
                f"Grok CLI timed out after {timeout_seconds} seconds; result details were written to {result_path}."
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"Grok CLI failed with exit code {result.returncode}; result details were written to {result_path}."
            )
        if not result.last_message:
            raise RuntimeError(f"Grok CLI returned no final message; result details were written to {result_path}.")
        return result


def allocate_run_artifact_paths(output_dir: Path, timestamp: str) -> tuple[Path, Path, Path]:
    for index in range(1000):
        suffix = timestamp if index == 0 else f"{timestamp}-{index:03d}"
        task_path = output_dir / f"grok-task-{suffix}.md"
        last_message_path = output_dir / f"grok-last-message-{suffix}.md"
        result_path = output_dir / f"grok-run-{suffix}.json"
        if not task_path.exists() and not last_message_path.exists() and not result_path.exists():
            return task_path, last_message_path, result_path
    raise RuntimeError(f"Could not allocate unique Grok run artifact paths for timestamp {timestamp}")


def normalize_grok_sandbox(value: str) -> str:
    aliases = {
        "workspace-write": "workspace",
        "read_only": "read-only",
        "danger-full-access": "off",
    }
    return aliases.get(value, value)


def _env_lookup(environment: Mapping[str, str], name: str) -> str:
    folded = name.casefold()
    for key, value in environment.items():
        if str(key).casefold() == folded:
            return str(value or "").strip()
    return ""


def _delete_env_key(environment: dict[str, str], name: str) -> None:
    folded = name.casefold()
    for key in [key for key in environment if str(key).casefold() == folded]:
        del environment[key]


def grok_launch_environment(
    environment: Mapping[str, str | None] | None = None,
) -> dict[str, str]:
    """Return the environment used to start the Grok CLI.

    Harvested runs log ``auto worktree gc failed`` with ``neither $GROK_HOME
    nor $HOME is set``. Grok does not consult ``USERPROFILE``. When both home
    variables are blank, ``HOME`` is set to an existing ``USERPROFILE``
    directory so the CLI can collect its session worktrees. An explicit
    ``HOME`` or ``GROK_HOME`` is preserved. A profile path that is not a
    directory is not copied into ``HOME``.

    ``PYTHONHOME`` is always removed. Harvested browser-use MCP servers exit
    before initialize: the controller prefix is CPython 3.13, the plugin
    command is ``uvx --python 3.12``, and 3.12 then imports 3.13 ``typing.py``
    and crashes on ``NoDefault``. Grok itself does not read ``PYTHONHOME``.
    ``PYTHONPATH`` is left in place.
    """

    source = os.environ if environment is None else environment
    env = {str(key): str(value) for key, value in source.items() if value is not None}
    _delete_env_key(env, "PYTHONHOME")
    if _env_lookup(env, "HOME") or _env_lookup(env, "GROK_HOME"):
        return env
    profile = _env_lookup(env, "USERPROFILE")
    if profile and Path(profile).is_dir():
        _delete_env_key(env, "HOME")
        env["HOME"] = profile
        return env
    if environment is not None:
        return env
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        return env
    if home.is_dir():
        _delete_env_key(env, "HOME")
        env["HOME"] = str(home)
    return env


def build_grok_command(config: GrokCliConfig, *, cwd: Path, prompt_file: Path) -> list[str]:
    grok_bin = shutil.which(config.grok_bin) or config.grok_bin
    command = [
        grok_bin,
        "--cwd",
        str(cwd),
        "--output-format",
        config.output_format,
        "--permission-mode",
        config.permission_mode,
        "--sandbox",
        normalize_grok_sandbox(config.sandbox),
    ]
    if config.model:
        command.extend(["--model", config.model])
    if config.no_memory:
        command.append("--no-memory")
    if config.no_subagents:
        command.append("--no-subagents")
    if config.disable_web_search:
        command.append("--disable-web-search")
    if config.max_turns is not None:
        command.extend(["--max-turns", str(config.max_turns)])
    if config.resume_session_id:
        command.extend(["--resume", config.resume_session_id])
    elif config.session_id:
        command.extend(["--session-id", config.session_id])
    for rule in config.deny_rules:
        command.extend(["--deny", rule])
    command.extend(config.extra_args)
    command.extend(["--prompt-file", str(prompt_file)])
    return command


def build_grok_provider_preflight(
    config: GrokCliConfig,
    *,
    env: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    environment = os.environ if env is None else env
    resolved_binary = shutil.which(config.grok_bin)
    model = str(config.model or "").strip()
    diagnostics: list[str] = []
    if resolved_binary is None:
        diagnostics.append("grok executable was not found on PATH")
    if config.require_explicit_route and not model:
        diagnostics.append("grok mode requires an explicit --model to avoid implicit provider fallback")
    return {
        "schema_version": 1,
        "ok": not diagnostics,
        "diagnostics": diagnostics,
        "provider": "grok",
        "selected_provider": "grok_cli",
        "binary_present": resolved_binary is not None,
        "binary_value_recorded": False,
        "route_selector": "model" if model else "implicit_default",
        "model": model or None,
        "model_present": bool(model),
        "requires_explicit_route": config.require_explicit_route,
        "cached_login_supported": True,
        "xai_api_key_present": bool(str(environment.get("XAI_API_KEY") or "").strip()),
        "token_value_recorded": False,
    }


def extract_grok_last_message(stdout: str) -> str:
    text = stdout.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict):
        value = payload.get("text")
        if isinstance(value, str) and value.strip():
            return value.strip()
        if payload.get("type") == "error":
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return ""


def serialize_run_result(result: GrokCliRunResult, *, cwd: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "grok_cli",
        "command": result.command,
        "cwd": str(cwd),
        "provider_preflight": result.provider_preflight,
        "returncode": result.returncode,
        "timed_out": result.timed_out,
        "task_path": str(result.task_path),
        "last_message_path": str(result.last_message_path),
        "stdout_tail": result.stdout_tail,
        "stderr_tail": result.stderr_tail,
        "last_message": result.last_message,
    }


def timeout_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def tail_text(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]
