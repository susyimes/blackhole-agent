"""Cursor Agent print-mode adapter (not the unrelated Grok ``agent`` alias)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from blackhole_agent.process_capture import run_captured_process

_DEFAULT_COMMAND_RUNNER = subprocess.run


def resolve_cursor_binary(
    binary: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] | None = None,
) -> str | None:
    env = os.environ if environ is None else environ
    locate = which or shutil.which
    explicit = binary or env.get("CURSOR_AGENT_BIN")
    if explicit:
        return locate(explicit)
    named = locate("cursor-agent")
    if named:
        return named
    # Do not fall back to bare `agent`: Grok also installs that name.
    local = env.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "cursor-agent" / "cursor-agent.cmd"
        if candidate.is_file():
            return str(candidate)
    return None


def cursor_invocation_prefix(binary: str) -> list[str]:
    path = Path(binary)
    if path.suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return [binary]
    # Official Windows launcher wraps PowerShell, then bundled Node. Bypass
    # both shells so quotes, Unicode and long stdin prompts are lossless.
    root = path.parent
    candidates = [root]
    versions = root / "versions"
    if versions.is_dir():
        candidates += sorted(
            (
                p
                for p in versions.iterdir()
                if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(?:-\d{2}-\d{2}-\d{2})?-[a-f0-9]+", p.name)
            ),
            key=lambda p: p.name,
            reverse=True,
        )
    for candidate in candidates:
        node, entry = candidate / "node.exe", candidate / "index.js"
        if node.is_file() and entry.is_file():
            return [str(node), str(entry)]
    raise ValueError("Cursor Windows launcher has no bundled node.exe/index.js; set CURSOR_AGENT_BIN explicitly")


@dataclass(frozen=True)
class CursorCliConfig:
    cursor_bin: str | None = None
    model: str | None = None
    require_explicit_route: bool = False
    output_format: str = "stream-json"
    resume_session_id: str | None = None
    force: bool = True
    mode: str | None = None
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CursorCliRunResult:
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


def build_cursor_provider_preflight(config: CursorCliConfig) -> dict[str, Any]:
    resolved = resolve_cursor_binary(config.cursor_bin)
    diagnostics = []
    if not resolved:
        diagnostics.append("Cursor Agent CLI not found; install it or set CURSOR_AGENT_BIN (never a Grok agent alias)")
    elif any(part.lower() in {".grok", "grok"} for part in Path(resolved).parts):
        diagnostics.append("resolved executable belongs to Grok, not Cursor Agent")
    if config.require_explicit_route and not config.model:
        diagnostics.append("an explicit Cursor model is required")
    if config.output_format not in {"json", "stream-json"}:
        diagnostics.append("Cursor adapter requires json or stream-json terminal results")
    if config.mode not in {None, "ask", "plan"}:
        diagnostics.append("mode must be ask, plan, or None for agent mode")
    if config.extra_args:
        diagnostics.append(
            "extra_args are unsupported; use typed config fields to preserve routing and artifact redaction"
        )
    return {
        "ok": not diagnostics,
        "provider": "cursor",
        "binary": resolved,
        "model": config.model,
        "diagnostics": diagnostics,
    }


def build_cursor_command(config: CursorCliConfig, *, binary: str, cwd: Path) -> list[str]:
    command = [
        *cursor_invocation_prefix(binary),
        "--print",
        "--output-format",
        config.output_format,
        "--workspace",
        str(cwd),
        "--trust",
    ]
    if config.model:
        command += ["--model", config.model]
    if config.resume_session_id:
        command += ["--resume", config.resume_session_id]
    if config.force:
        command.append("--force")
    if config.mode:
        command += ["--mode", config.mode]
    return command


def extract_cursor_result(stdout: str) -> tuple[str, str, str]:
    """Only a terminal success is final: partial assistant/tool text is not."""
    session_id, last, error = "", "", "missing terminal result"
    try:
        payloads = [json.loads(stdout)]
    except ValueError:
        payloads = []
        for line in stdout.splitlines():
            try:
                payloads.append(json.loads(line))
            except ValueError:
                continue
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        if payload.get("session_id"):
            session_id = str(payload["session_id"])
        if payload.get("type") == "error":
            last, error = "", str(payload.get("message") or "Cursor error event")
        if payload.get("type") != "result":
            continue
        if payload.get("is_error") or payload.get("subtype") != "success":
            last, error = "", str(payload.get("result") or "Cursor terminal error")
        elif isinstance(payload.get("result"), str) and payload["result"].strip():
            last, error = payload["result"].strip(), ""
        else:
            last, error = "", "empty terminal result"
    return last, session_id, error


def _text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


class CursorCliKernel:
    def __init__(self, config: CursorCliConfig | None = None, *, command_runner: Any = subprocess.run) -> None:
        self.config = config or CursorCliConfig()
        self._command_runner = command_runner

    def run(self, task: str, *, cwd: Path, output_dir: Path, timeout_seconds: int = 3600) -> CursorCliRunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        task_path = output_dir / f"cursor-task-{token}.md"
        message_path = output_dir / f"cursor-last-message-{token}.md"
        result_path = output_dir / f"cursor-run-{token}.json"
        task_path.write_text(task, encoding="utf-8")
        preflight = build_cursor_provider_preflight(self.config)
        (output_dir / "latest-cursor-provider-preflight.json").write_text(
            json.dumps(preflight, indent=2), encoding="utf-8"
        )
        command: list[str] = []
        stdout = stderr = ""
        returncode, timed_out = 0, False
        try:
            if not preflight["ok"]:
                raise ValueError("; ".join(preflight["diagnostics"]))
            command = build_cursor_command(self.config, binary=preflight["binary"], cwd=cwd)
            if self._command_runner is _DEFAULT_COMMAND_RUNNER:
                completed = run_captured_process(command, cwd=cwd, timeout=timeout_seconds, input=task)
            else:
                completed = self._command_runner(
                    command,
                    cwd=cwd,
                    input=task,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                )
            returncode, stdout, stderr = int(completed.returncode), _text(completed.stdout), _text(completed.stderr)
        except subprocess.TimeoutExpired as exc:
            returncode, timed_out = 124, True
            stdout, stderr = _text(exc.stdout), _text(exc.stderr) or f"Timed out after {timeout_seconds} seconds"
        except (OSError, ValueError) as exc:
            returncode, stderr = 127, str(exc)
        message, session_id, parse_error = extract_cursor_result(stdout)
        session_id = session_id or self.config.resume_session_id or ""
        if returncode or timed_out:
            message = ""  # Failed/partial output must not be salvaged into a completion.
        if parse_error:
            stderr = (stderr + "\n" + parse_error).strip()
        if message:
            message_path.write_text(message, encoding="utf-8")
        result = CursorCliRunResult(
            command,
            preflight,
            returncode,
            timed_out,
            task_path,
            message_path,
            result_path,
            stdout[-4000:],
            stderr[-4000:],
            message,
            session_id,
        )
        payload = {
            **asdict(result),
            "cwd": str(cwd),
            "decision_final": bool(message and session_id and not parse_error and not returncode and not timed_out),
        }
        encoded = json.dumps(payload, default=str, indent=2, ensure_ascii=False) + "\n"
        result_path.write_text(encoded, encoding="utf-8")
        (output_dir / "latest-cursor-run.json").write_text(encoded, encoding="utf-8")
        if timed_out:
            raise TimeoutError(f"Cursor CLI timed out; details: {result_path}")
        if returncode or parse_error or not session_id:
            raise RuntimeError(
                f"Cursor CLI failed (exit {returncode}): {stderr or 'no session ID'}; details: {result_path}"
            )
        return result
