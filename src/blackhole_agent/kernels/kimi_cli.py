"""Local Kimi Code CLI kernel used by blackhole-agent growth passes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class KimiCliConfig:
    """Configuration for one native non-interactive Kimi Code invocation."""

    kimi_bin: str = "kimi"
    model: str | None = None
    require_explicit_route: bool = False
    output_format: str = "stream-json"
    resume_session_id: str | None = None
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class KimiCliRunResult:
    """Result of one native Kimi Code CLI kernel invocation."""

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
    session_id: str
    tool_titles: tuple[str, ...]


class KimiCliKernel:
    """Run a controller-shaped task through native Kimi prompt mode."""

    def __init__(
        self,
        config: KimiCliConfig | None = None,
        *,
        command_runner: Any = subprocess.run,
    ) -> None:
        self.config = config or KimiCliConfig()
        self._command_runner = command_runner

    def run(
        self,
        task: str,
        *,
        cwd: Path,
        output_dir: Path,
        timeout_seconds: int = 3600,
    ) -> KimiCliRunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        task_path, last_message_path, result_path = allocate_run_artifact_paths(output_dir, timestamp)
        task_path.write_text(task, encoding="utf-8")

        provider_preflight = build_kimi_provider_preflight(self.config)
        preflight_path = output_dir / f"kimi-provider-preflight-{timestamp}.json"
        preflight_text = json.dumps(provider_preflight, indent=2, sort_keys=True) + "\n"
        preflight_path.write_text(preflight_text, encoding="utf-8")
        (output_dir / "latest-kimi-provider-preflight.json").write_text(
            preflight_text,
            encoding="utf-8",
        )
        if not provider_preflight["ok"]:
            diagnostics = "; ".join(str(item) for item in provider_preflight["diagnostics"])
            raise ValueError(f"Kimi provider/config preflight failed: {diagnostics}")

        invocation_command = build_kimi_command(self.config, prompt=task)
        recorded_command = redact_prompt_argument(invocation_command, task_path=task_path)
        timed_out = False
        try:
            completed = self._command_runner(
                invocation_command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
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

        last_message, streamed_session_id, tool_titles = extract_kimi_stream(stdout)
        session_id = streamed_session_id or str(self.config.resume_session_id or "")
        if returncode != 0:
            last_message = ""
        if last_message:
            last_message_path.write_text(last_message, encoding="utf-8")
        result = KimiCliRunResult(
            command=recorded_command,
            provider_preflight=provider_preflight,
            returncode=returncode,
            timed_out=timed_out,
            task_path=task_path,
            last_message_path=last_message_path,
            result_path=result_path,
            stdout_tail=tail_text(stdout),
            stderr_tail=tail_text(stderr),
            last_message=last_message,
            session_id=session_id,
            tool_titles=tool_titles,
        )
        payload = serialize_run_result(result, cwd=cwd)
        result_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        result_path.write_text(result_text, encoding="utf-8")
        (output_dir / "latest-kimi-run.json").write_text(result_text, encoding="utf-8")

        if result.timed_out:
            raise TimeoutError(
                f"Kimi CLI timed out after {timeout_seconds} seconds; result details were written to {result_path}."
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"Kimi CLI failed with exit code {result.returncode}; result details were written to {result_path}."
            )
        if not result.session_id:
            raise RuntimeError(f"Kimi CLI returned no native session ID; result details were written to {result_path}.")
        if not result.last_message:
            raise RuntimeError(f"Kimi CLI returned no final message; result details were written to {result_path}.")
        return result


def allocate_run_artifact_paths(output_dir: Path, timestamp: str) -> tuple[Path, Path, Path]:
    for index in range(1000):
        suffix = timestamp if index == 0 else f"{timestamp}-{index:03d}"
        task_path = output_dir / f"kimi-task-{suffix}.md"
        last_message_path = output_dir / f"kimi-last-message-{suffix}.md"
        result_path = output_dir / f"kimi-run-{suffix}.json"
        if not task_path.exists() and not last_message_path.exists() and not result_path.exists():
            return task_path, last_message_path, result_path
    raise RuntimeError(f"Could not allocate unique Kimi run artifact paths for timestamp {timestamp}")


def build_kimi_command(config: KimiCliConfig, *, prompt: str) -> list[str]:
    command = resolve_kimi_invocation_prefix(config.kimi_bin)
    if config.model:
        command.extend(["--model", config.model])
    if config.resume_session_id:
        command.extend(["--session", config.resume_session_id])
    command.extend(config.extra_args)
    command.extend(["--output-format", config.output_format, "--prompt", prompt])
    return command


def resolve_kimi_invocation_prefix(kimi_bin: str) -> list[str]:
    """Bypass the Windows npm batch shim so long prompts reach Kimi intact."""

    resolved_value = shutil.which(kimi_bin) or kimi_bin
    resolved_binary = Path(resolved_value)
    if resolved_binary.suffix.lower() not in {".cmd", ".bat"}:
        return [resolved_value]

    entrypoint = resolved_binary.parent / "node_modules" / "@moonshot-ai" / "kimi-code" / "dist" / "main.mjs"
    bundled_node = resolved_binary.parent / "node.exe"
    node_binary = str(bundled_node) if bundled_node.is_file() else shutil.which("node")
    if entrypoint.is_file() and node_binary:
        return [node_binary, str(entrypoint)]
    return [str(resolved_binary)]


def build_kimi_provider_preflight(
    config: KimiCliConfig,
    *,
    env: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    environment = os.environ if env is None else env
    resolved_binary = shutil.which(config.kimi_bin)
    model = str(config.model or "").strip()
    incompatible_prompt_flags = sorted(
        {argument for argument in config.extra_args if argument in {"--auto", "--plan", "--yolo", "-y"}}
    )
    diagnostics: list[str] = []
    if resolved_binary is None:
        diagnostics.append("kimi executable was not found on PATH")
    if config.require_explicit_route and not model:
        diagnostics.append("kimi mode requires an explicit --model to avoid implicit provider fallback")
    if incompatible_prompt_flags:
        diagnostics.append(
            "kimi prompt mode cannot be combined with permission or plan flags: " + ", ".join(incompatible_prompt_flags)
        )
    return {
        "schema_version": 1,
        "ok": not diagnostics,
        "diagnostics": diagnostics,
        "provider": "kimi",
        "selected_provider": "kimi_cli",
        "binary_present": resolved_binary is not None,
        "binary_value_recorded": False,
        "route_selector": "model" if model else "implicit_default",
        "model": model or None,
        "model_present": bool(model),
        "requires_explicit_route": config.require_explicit_route,
        "cached_login_supported": True,
        "kimi_api_key_present": bool(str(environment.get("KIMI_API_KEY") or "").strip()),
        "moonshot_api_key_present": bool(str(environment.get("MOONSHOT_API_KEY") or "").strip()),
        "token_value_recorded": False,
        "permission_mode": "auto",
        "permission_mode_source": "native_prompt_mode",
        "explicit_permission_flag": False,
        "incompatible_prompt_flags": incompatible_prompt_flags,
    }


def extract_kimi_stream(stdout: str) -> tuple[str, str, tuple[str, ...]]:
    assistant_messages: list[str] = []
    session_id = ""
    tool_titles: list[str] = []
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("role") == "assistant":
            content = event.get("content")
            if isinstance(content, str) and content.strip():
                assistant_messages.append(content.strip())
            calls = event.get("tool_calls")
            if isinstance(calls, list):
                for call in calls:
                    if not isinstance(call, dict):
                        continue
                    name = call.get("name")
                    function = call.get("function")
                    if not name and isinstance(function, dict):
                        name = function.get("name")
                    if isinstance(name, str) and name.strip():
                        tool_titles.append(name.strip())
        if event.get("role") == "meta" and event.get("type") == "session.resume_hint":
            candidate = event.get("session_id")
            if isinstance(candidate, str) and candidate.strip():
                session_id = candidate.strip()
    return "\n".join(assistant_messages).strip(), session_id, tuple(tool_titles)


def redact_prompt_argument(command: list[str], *, task_path: Path) -> list[str]:
    recorded = list(command)
    try:
        prompt_index = recorded.index("--prompt") + 1
    except ValueError:
        return recorded
    if prompt_index < len(recorded):
        recorded[prompt_index] = f"<prompt stored at {task_path}>"
    return recorded


def serialize_run_result(result: KimiCliRunResult, *, cwd: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "kimi_cli",
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
        "session_id": result.session_id,
        "tool_titles": list(result.tool_titles),
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
