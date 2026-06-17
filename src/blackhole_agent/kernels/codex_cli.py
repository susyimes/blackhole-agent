"""Local Codex CLI kernel.

This wrapper intentionally treats Codex as a local mutation kernel, not as a
remote publisher. It can edit the checkout under the configured sandbox, while
the blackhole controller keeps rollback, run artifacts, and runtime capability
selection outside the model process.
"""

import json
import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodexCliConfig:
    """Configuration for `codex exec`."""

    codex_bin: str = "codex"
    model: str | None = None
    profile: str | None = None
    require_explicit_route: bool = False
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    ephemeral: bool = True
    ignore_user_config: bool = True
    skip_git_repo_check: bool = False
    bypass_approvals_and_sandbox: bool = False
    color: str = "never"
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodexCliRunResult:
    """Result of one Codex CLI kernel invocation."""

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


class CodexCliKernel:
    """Run a controller-shaped task through local `codex exec`."""

    def __init__(
        self,
        config: CodexCliConfig | None = None,
        *,
        command_runner: Any = subprocess.run,
    ) -> None:
        self.config = config or CodexCliConfig()
        self._command_runner = command_runner

    def run(
        self,
        task: str,
        *,
        cwd: Path,
        output_dir: Path,
        timeout_seconds: int = 3600,
    ) -> CodexCliRunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_path, last_message_path, result_path = allocate_run_artifact_paths(output_dir, timestamp)
        task_path.write_text(task, encoding="utf-8")
        provider_preflight = build_codex_provider_preflight(self.config)
        provider_preflight_path = output_dir / f"codex-provider-preflight-{timestamp}.json"
        provider_preflight_text = json.dumps(provider_preflight, indent=2, sort_keys=True) + "\n"
        provider_preflight_path.write_text(provider_preflight_text, encoding="utf-8")
        (output_dir / "latest-codex-provider-preflight.json").write_text(
            provider_preflight_text,
            encoding="utf-8",
        )
        if not provider_preflight["ok"]:
            diagnostics = "; ".join(str(item) for item in provider_preflight["diagnostics"])
            raise ValueError(f"Codex provider/config preflight failed: {diagnostics}")

        command = build_codex_exec_command(
            self.config,
            cwd=cwd,
            output_last_message=last_message_path,
        )
        timed_out = False
        try:
            completed = self._command_runner(
                command,
                cwd=cwd,
                input=task,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            returncode = int(completed.returncode)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as error:
            timed_out = True
            returncode = 124
            stdout = timeout_text(error.stdout)
            stderr = timeout_text(error.stderr) or f"Timed out after {timeout_seconds} seconds."
        last_message = last_message_path.read_text(encoding="utf-8") if last_message_path.exists() else ""
        result = CodexCliRunResult(
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
        result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (output_dir / "latest-codex-run.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if result.timed_out:
            raise TimeoutError(
                f"Codex CLI timed out after {timeout_seconds} seconds; "
                f"result details were written to {result_path}."
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"Codex CLI failed with exit code {result.returncode}; "
                f"result details were written to {result_path}."
            )
        return result


def allocate_run_artifact_paths(output_dir: Path, timestamp: str) -> tuple[Path, Path, Path]:
    """Return fresh per-run artifact paths, even for multiple runs in one second."""

    for index in range(1000):
        suffix = timestamp if index == 0 else f"{timestamp}-{index:03d}"
        task_path = output_dir / f"codex-task-{suffix}.md"
        last_message_path = output_dir / f"codex-last-message-{suffix}.md"
        result_path = output_dir / f"codex-run-{suffix}.json"
        if not task_path.exists() and not last_message_path.exists() and not result_path.exists():
            return task_path, last_message_path, result_path
    raise RuntimeError(f"Could not allocate unique Codex run artifact paths for timestamp {timestamp}")


def build_codex_exec_command(
    config: CodexCliConfig,
    *,
    cwd: Path,
    output_last_message: Path,
) -> list[str]:
    """Build a `codex exec` command that reads the task from stdin."""

    codex_bin = shutil.which(config.codex_bin) or config.codex_bin
    command = [
        codex_bin,
        "exec",
        "--cd",
        str(cwd),
        "--color",
        config.color,
        "--output-last-message",
        str(output_last_message),
    ]
    if config.model:
        command.extend(["--model", config.model])
    if config.profile:
        command.extend(["--profile", config.profile])
    if config.ignore_user_config:
        command.append("--ignore-user-config")
    if config.bypass_approvals_and_sandbox:
        command.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        command.extend(["--sandbox", config.sandbox])
        # Modern `codex exec` is non-interactive and no longer accepts an
        # approval-policy flag. Keep the config field for controller/API
        # compatibility, but do not emit the removed CLI option.
    if config.ephemeral:
        command.append("--ephemeral")
    if config.skip_git_repo_check:
        command.append("--skip-git-repo-check")
    command.extend(config.extra_args)
    command.append("-")
    return command


def build_codex_provider_preflight(config: CodexCliConfig) -> dict[str, Any]:
    """Return metadata-only diagnostics for the selected Codex execution route."""

    model = str(config.model or "").strip()
    profile = str(config.profile or "").strip()
    has_model = bool(model)
    has_profile = bool(profile)
    if has_model and has_profile:
        route_selector = "model_and_profile"
    elif has_model:
        route_selector = "model"
    elif has_profile:
        route_selector = "profile"
    else:
        route_selector = "implicit_default"
    diagnostics: list[str] = []
    if config.require_explicit_route and route_selector == "implicit_default":
        diagnostics.append("codex mode requires an explicit --model or --profile to avoid implicit provider fallback")
    return {
        "schema_version": 1,
        "ok": not diagnostics,
        "diagnostics": diagnostics,
        "provider": "codex",
        "selected_provider": "codex_cli",
        "route_selector": route_selector,
        "model": model if has_model else None,
        "model_present": has_model,
        "profile_present": has_profile,
        "profile_value_recorded": False,
        "requires_explicit_route": config.require_explicit_route,
        "implicit_default_route_allowed": not config.require_explicit_route,
        "token_value_recorded": False,
    }


def serialize_run_result(result: CodexCliRunResult, *, cwd: Path) -> dict[str, Any]:
    data = asdict(result)
    for key in ("task_path", "last_message_path", "result_path"):
        data[key] = str(data[key])
    data["cwd"] = str(cwd)
    return data


def tail_text(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def timeout_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def shutdown_subprocess_cli_transport_stderr(
    transport: Any,
    *,
    logger: logging.Logger | None = None,
) -> bool:
    """Best-effort stderr task-group shutdown for SDK subprocess transports.

    Some Claude SDK transport versions expose ``_stderr_task_group`` during
    teardown and some do not. Treat missing or already-cleared state as an
    idempotent shutdown outcome so provider cleanup cannot fail with
    ``AttributeError`` while the controller is already exiting.
    """

    log = logger or LOGGER
    missing = object()
    stderr_task_group = getattr(transport, "_stderr_task_group", missing)
    if stderr_task_group is missing:
        log.debug(
            "subprocess CLI transport shutdown skipped stderr task-group cleanup: "
            "_stderr_task_group is absent"
        )
        return False
    if stderr_task_group is None:
        log.debug(
            "subprocess CLI transport shutdown skipped stderr task-group cleanup: "
            "_stderr_task_group is already cleared"
        )
        return False

    cancel_scope = getattr(stderr_task_group, "cancel_scope", None)
    cancel = getattr(cancel_scope, "cancel", None)
    if callable(cancel):
        cancel()
        setattr(transport, "_stderr_task_group", None)
        log.debug("subprocess CLI transport stderr task-group cancel scope was cancelled")
        return True

    close = getattr(stderr_task_group, "close", None)
    if callable(close):
        close()
        setattr(transport, "_stderr_task_group", None)
        log.debug("subprocess CLI transport stderr task-group was closed")
        return True

    log.debug(
        "subprocess CLI transport shutdown left stderr task-group untouched: "
        "no cancel scope or close method is available"
    )
    return False
