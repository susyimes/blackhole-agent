"""Local Codex CLI kernel.

This wrapper intentionally treats Codex as a local mutation kernel, not as a
remote publisher. It can edit the checkout under the configured sandbox, while
the blackhole controller keeps rollback, run artifacts, and runtime capability
selection outside the model process.
"""

import json
import logging
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


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


@dataclass(frozen=True)
class CodexStreamChunk:
    """Deterministic fixture event for Codex streaming regression tests."""

    offset_seconds: float
    text: str = ""
    completed: bool = False


@dataclass(frozen=True)
class CodexStreamAssemblyResult:
    """Paragraphs and completion state produced from streamed Codex chunks."""

    paragraphs: list[str]
    completed: bool


@dataclass(frozen=True)
class ProcessTreeCleanupResult:
    """Best-effort cleanup details for a local CLI subprocess tree."""

    root_pid: int | None
    child_pids: tuple[int, ...]
    terminated_pids: tuple[int, ...]
    killed_pids: tuple[int, ...]
    timeout_pids: tuple[int, ...]
    errors: tuple[str, ...]

    @property
    def all_exited(self) -> bool:
        return not self.timeout_pids and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CodexStreamTimeoutError(TimeoutError):
    """Raised when a simulated Codex stream stalls before completion."""


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


def build_codex_provider_preflight(
    config: CodexCliConfig,
    *,
    env: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
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
        "ambient_openai": build_ambient_openai_preflight(os.environ if env is None else env),
        "ambient_google": build_ambient_google_preflight(os.environ if env is None else env),
    }


def build_ambient_openai_preflight(env: Mapping[str, str | None]) -> dict[str, Any]:
    """Summarize ambient OpenAI env routing without recording credential or URL values."""

    api_key_present = bool(str(env.get("OPENAI_API_KEY") or "").strip())
    base_url_present = bool(str(env.get("OPENAI_BASE_URL") or "").strip())
    if api_key_present and base_url_present:
        route_hint = "openai_compatible_gateway"
        endpoint_source = "OPENAI_BASE_URL"
        provider_family = "openai"
    elif api_key_present:
        route_hint = "openai_default_endpoint"
        endpoint_source = "default_openai"
        provider_family = "openai"
    elif base_url_present:
        route_hint = "base_url_without_api_key"
        endpoint_source = "OPENAI_BASE_URL"
        provider_family = None
    else:
        route_hint = "not_configured"
        endpoint_source = None
        provider_family = None

    diagnostics: list[str] = []
    if base_url_present and not api_key_present:
        diagnostics.append("OPENAI_BASE_URL is present without OPENAI_API_KEY; ambient OpenAI credentials are incomplete")

    return {
        "schema_version": 1,
        "provider_family": provider_family,
        "route_hint": route_hint,
        "endpoint_source": endpoint_source,
        "api_key_env": "OPENAI_API_KEY",
        "api_key_present": api_key_present,
        "api_key_value_recorded": False,
        "base_url_env": "OPENAI_BASE_URL",
        "base_url_present": base_url_present,
        "base_url_value_recorded": False,
        "diagnostics": diagnostics,
    }


def build_ambient_google_preflight(env: Mapping[str, str | None]) -> dict[str, Any]:
    """Summarize ambient Google model credentials without recording values."""

    api_key_env_names = ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    api_key_present_names = [name for name in api_key_env_names if str(env.get(name) or "").strip()]
    application_credentials_present = bool(str(env.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip())

    if api_key_present_names and application_credentials_present:
        route_hint = "google_api_key_and_application_credentials"
        provider_family = "google"
    elif api_key_present_names:
        route_hint = "google_api_key"
        provider_family = "google"
    elif application_credentials_present:
        route_hint = "google_application_credentials_without_api_key"
        provider_family = "google"
    else:
        route_hint = "not_configured"
        provider_family = None

    diagnostics: list[str] = []
    if application_credentials_present and not api_key_present_names:
        diagnostics.append(
            "GOOGLE_APPLICATION_CREDENTIALS is present without GOOGLE_API_KEY or GEMINI_API_KEY; "
            "ambient Google API-key credentials are incomplete"
        )

    return {
        "schema_version": 1,
        "provider_family": provider_family,
        "route_hint": route_hint,
        "api_key_envs": list(api_key_env_names),
        "api_key_present": bool(api_key_present_names),
        "api_key_present_envs": api_key_present_names,
        "api_key_values_recorded": False,
        "application_credentials_env": "GOOGLE_APPLICATION_CREDENTIALS",
        "application_credentials_present": application_credentials_present,
        "application_credentials_value_recorded": False,
        "diagnostics": diagnostics,
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


class CodexStreamParagraphAssembler:
    """Assemble streamed text into finalized paragraphs.

    Codex streaming regressions are most visible when buffered text hangs at
    completion or a new paragraph is appended directly to the previous one.
    This fixture-oriented assembler keeps that behavior locally testable
    without network access, provider tokens, or a live UI stream.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        paragraphs: list[str] = []
        while True:
            split_at = _find_paragraph_boundary(self._buffer)
            if split_at is None:
                return paragraphs
            paragraph = self._buffer[:split_at].strip()
            self._buffer = self._buffer[split_at:]
            self._buffer = self._buffer.lstrip("\r\n")
            if paragraph:
                paragraphs.append(paragraph)

    def finish(self) -> list[str]:
        paragraph = self._buffer.strip()
        self._buffer = ""
        return [paragraph] if paragraph else []


def assemble_codex_stream_chunks(
    chunks: Iterable[CodexStreamChunk],
    *,
    idle_timeout_seconds: float,
) -> CodexStreamAssemblyResult:
    """Consume deterministic stream chunks and fail on stalled completion."""

    if idle_timeout_seconds <= 0:
        raise ValueError("idle_timeout_seconds must be greater than zero")

    assembler = CodexStreamParagraphAssembler()
    paragraphs: list[str] = []
    previous_offset: float | None = None
    completed = False

    for chunk in chunks:
        offset = float(chunk.offset_seconds)
        if previous_offset is not None:
            idle_seconds = offset - previous_offset
            if idle_seconds < 0:
                raise ValueError("Codex stream chunk offsets must be monotonic")
            if idle_seconds > idle_timeout_seconds:
                raise CodexStreamTimeoutError(
                    f"Codex stream stalled for {idle_seconds:g} seconds before completion"
                )
        previous_offset = offset
        if chunk.text:
            paragraphs.extend(assembler.feed(chunk.text))
        if chunk.completed:
            completed = True
            paragraphs.extend(assembler.finish())
            break

    if not completed:
        raise CodexStreamTimeoutError("Codex stream ended without a completion marker")

    return CodexStreamAssemblyResult(paragraphs=paragraphs, completed=True)


def _find_paragraph_boundary(value: str) -> int | None:
    indexes = [index for marker in ("\r\n\r\n", "\n\n") if (index := value.find(marker)) != -1]
    if not indexes:
        return None
    return min(indexes)


def cleanup_orphaned_process_tree(
    root_process: Any,
    *,
    grace_seconds: float = 2.0,
    logger: logging.Logger | None = None,
) -> ProcessTreeCleanupResult:
    """Terminate a local CLI process and children without requiring psutil.

    The helper accepts process-like objects from SDK transports or tests. When a
    transport exposes ``children(recursive=True)``, children are stopped before
    the root process so orphaned descendants do not keep a terminal session
    looking active after the parent is already gone.
    """

    log = logger or LOGGER
    errors: list[str] = []
    children = _process_children(root_process, errors)
    processes = [*children, root_process]
    terminated_pids: list[int] = []
    killed_pids: list[int] = []
    timeout_pids: list[int] = []

    for process in processes:
        pid = _process_pid(process)
        terminate = getattr(process, "terminate", None)
        if not callable(terminate):
            continue
        try:
            terminate()
            if pid is not None:
                terminated_pids.append(pid)
        except Exception as error:  # pragma: no cover - defensive against transport-specific process shims
            message = f"terminate failed for pid {pid}: {error}"
            errors.append(message)
            log.debug(message)

    remaining: list[Any] = []
    for process in processes:
        if not _wait_process(process, timeout=grace_seconds, errors=errors, log=log):
            remaining.append(process)

    for process in remaining:
        pid = _process_pid(process)
        kill = getattr(process, "kill", None)
        if not callable(kill):
            if pid is not None:
                timeout_pids.append(pid)
            continue
        try:
            kill()
            if pid is not None:
                killed_pids.append(pid)
        except Exception as error:  # pragma: no cover - defensive against transport-specific process shims
            message = f"kill failed for pid {pid}: {error}"
            errors.append(message)
            log.debug(message)
            if pid is not None:
                timeout_pids.append(pid)

    for process in remaining:
        pid = _process_pid(process)
        if not _wait_process(process, timeout=grace_seconds, errors=errors, log=log) and pid is not None:
            timeout_pids.append(pid)

    return ProcessTreeCleanupResult(
        root_pid=_process_pid(root_process),
        child_pids=tuple(pid for child in children if (pid := _process_pid(child)) is not None),
        terminated_pids=tuple(terminated_pids),
        killed_pids=tuple(killed_pids),
        timeout_pids=tuple(dict.fromkeys(timeout_pids)),
        errors=tuple(errors),
    )


def _process_children(root_process: Any, errors: list[str]) -> list[Any]:
    children = getattr(root_process, "children", None)
    if not callable(children):
        return []
    try:
        child_processes = children(recursive=True)
    except TypeError:
        child_processes = children()
    except Exception as error:  # pragma: no cover - defensive against transport-specific process shims
        errors.append(f"children lookup failed: {error}")
        return []
    return list(child_processes or [])


def _process_pid(process: Any) -> int | None:
    try:
        pid = getattr(process, "pid", None)
        return int(pid) if pid is not None else None
    except (TypeError, ValueError):
        return None


def _wait_process(process: Any, *, timeout: float, errors: list[str], log: logging.Logger) -> bool:
    wait = getattr(process, "wait", None)
    pid = _process_pid(process)
    if not callable(wait):
        return False
    try:
        wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False
    except TimeoutError:
        return False
    except Exception as error:  # pragma: no cover - defensive against transport-specific process shims
        message = f"wait failed for pid {pid}: {error}"
        errors.append(message)
        log.debug(message)
        return False


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
