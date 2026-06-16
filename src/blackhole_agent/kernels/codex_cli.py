"""Local Codex CLI kernel.

This wrapper intentionally treats Codex as a local mutation kernel, not as a
remote publisher. It can edit the checkout under the configured sandbox, while
the blackhole controller keeps rollback, run artifacts, and runtime capability
selection outside the model process.
"""

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CodexCliConfig:
    """Configuration for `codex exec`."""

    codex_bin: str = "codex"
    model: str | None = None
    profile: str | None = None
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
