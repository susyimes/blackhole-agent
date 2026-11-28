"""Recover a mission turn from a failed provider CLI.

A usable final reply can supply the decision even if the process exits with an
error. Otherwise the run artifact determines whether to continue a session,
start a fresh one, retry the decision only, or try another provider. A successor
receives the task and the worktree state. Provider-wide failures open the
corresponding circuit in kernel_health so subsequent turns can route around it.

The classifier orders provider diagnoses ahead of incidental tool warnings.
The acceptance fixtures under tests/acceptance preserve the harvested CLI
transcripts, mission identifiers, and the expected next dispatch.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

from blackhole_agent.file_guard import atomic_write_text
from blackhole_agent.kernel_health import (
    CLI_FAILOVER_ORDER,
    FAILOVER_ORDER,
    LOCAL_KERNEL,
    TRIP_CLASSES,
    KernelHealth,
    apply_health_reroute,
    empty_local_decision,
    invoke_local_kernel,
    kernel_dispatch_admission,
    kernel_is_available,
    load_kernel_health,
    mark_kernel_success,
    refresh_kernel_breakers,
    save_kernel_health,
    trip_kernel,
)

PRE_SESSION_TRANSPORT_ABORT = "pre_session_transport_abort"
SESSION_ALREADY_IN_USE = "session_already_in_use"
SESSION_NOT_FOUND = "session_not_found"
MODEL_UNAVAILABLE = "model_unavailable"
PROVIDER_OVERLOADED = "provider_overloaded"
OUTPUT_TRUNCATED = "output_truncated"
STEP_RETRIES_EXHAUSTED = "step_retries_exhausted"
RESPONSES_ENDPOINT_MISSING = "responses_endpoint_missing"
PROVIDER_CONNECTION_FAILED = "provider_connection_failed"
RESPONSE_STREAM_FAILED = "response_stream_failed"
AUTH_TEMPORARILY_UNAVAILABLE = "auth_temporarily_unavailable"
TOKEN_GENERATION_FAILED = "token_generation_failed"
INFERENCE_IDLE_TIMEOUT = "inference_idle_timeout"
SESSION_ACTOR_DEAD = "session_actor_dead"
DOOM_LOOP_REPETITION = "doom_loop_repetition"
BACKGROUND_TASK_WAIT = "background_task_wait"
ABNORMAL_PROCESS_EXIT = "abnormal_process_exit"
SESSIONLESS_PROCESS_ABORT = "sessionless_process_abort"
_UNSIGNED_PROCESS_EXIT = 0xFFFFFFFF

# Provider failures can change routes. Session-local failures use the retry rules below.
FAILOVER_CLASSES = TRIP_CLASSES | frozenset(
    {
        PRE_SESSION_TRANSPORT_ABORT,
        MODEL_UNAVAILABLE,
        PROVIDER_OVERLOADED,
        RESPONSES_ENDPOINT_MISSING,
        PROVIDER_CONNECTION_FAILED,
        RESPONSE_STREAM_FAILED,
    }
)
# Match every phrase in a row. Order matters when a provider emits several diagnoses.
# Timeout and quota precedence are handled separately in classify_kernel_failure.
_EXIT_DIAGNOSES = (
    (SESSION_ALREADY_IN_USE, ("session id", "already in use")),
    (SESSION_NOT_FOUND, ("failed to restore session from remote", "session get failed: 404")),
    (MODEL_UNAVAILABLE, ("cannot use this model",)),
    (MODEL_UNAVAILABLE, ("model is not supported when using codex",)),
    (MODEL_UNAVAILABLE, ("model ", "is not configured in config.toml")),
    ("auth_failed", ("failed to fetch an access token",)),
    ("auth_failed", ("not signed in", "grok login")),
    (PROVIDER_CONNECTION_FAILED,
     ("provider.connection_error: connection error", "turn.step.retrying", "apiconnectionerror")),
    (PROVIDER_OVERLOADED, ("provider.rate_limit",)),
    (PROVIDER_OVERLOADED, ("engine is currently overloaded",)),
    (RESPONSES_ENDPOINT_MISSING, ("unexpected status 404 not found", "backend-api/codex/responses")),
    (STEP_RETRIES_EXHAUSTED, ("failed to run step", "exceeded max retries")),
)

# cmd.exe can report launch failure in English, Chinese, or a lossy GBK capture.
COMMAND_LINE_TOO_LONG = "command_line_too_long"
_COMMAND_LINE_TOO_LONG_MARKERS = (
    "命令行太长",
    "输入行太长",
    "the command line is too long",
    "the input line is too long",
    "filename or extension is too long",
    "\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\u032b\ufffd\ufffd\ufffd\ufffd",
)
_OUTPUT_TRUNCATION_MARKERS = ("max_tokens_truncation", "response truncated by max_tokens")
DECISION_ONLY_PROMPT = (
    "The previous response was truncated by max_tokens before a JSON decision. "
    "Do not call tools. Do not re-explore the repository. Do not repeat the mission prompt. "
    "Reply with only the JSON decision object for the work already done in this session. "
    "Use status continue if that work is unfinished. Keep the object small."
)
STEP_CONTINUE_PROMPT = (
    "The previous step exhausted this kernel's internal retries before a JSON decision. "
    "Do not restart the mission from the beginning. Continue from files already changed in this session. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
STREAM_CONTINUE_PROMPT = (
    "The previous responses stream died before a JSON decision. "
    "Do not restart the mission from the beginning. Continue the same session from work already done. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
WAKE_CONTINUE_PROMPT = (
    "Authentication was temporarily unavailable after wake. The session is still signed in. "
    "Do not run login. Do not restart the mission from the beginning. "
    "Continue the same session from work already done. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
TOKEN_GENERATION_CONTINUE_PROMPT = (
    "Token generation failed with an internal server error. "
    "Do not restart the mission from the beginning. Continue the same session from work already done. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
INFERENCE_IDLE_CONTINUE_PROMPT = (
    "Inference went idle and produced no further chunks. "
    "Do not restart the mission from the beginning. Continue the same session from work already done. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
DEAD_ACTOR_CONTINUE_PROMPT = (
    "The resident session actor exited unexpectedly and was reaped as DeadFailed. "
    "Do not resume that session. Continue from files already changed in the workspace. "
    "Do not restart the mission from the beginning. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
DOOM_LOOP_CONTINUE_PROMPT = (
    "The previous response repeated itself in a thinking tail-repetition doom loop. "
    "Do not restart the mission from the beginning. Continue the same session from work already done. "
    "Stop repeating. Finish the unfinished edit, then reply with only the JSON decision object."
)
BACKGROUND_CONTINUE_PROMPT = (
    "The previous process was killed while it waited on a background task. "
    "Do not wait, poll, or start another background shell. "
    "Do not restart the mission from the beginning. Continue from files already changed in the workspace. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
ABNORMAL_EXIT_CONTINUE_PROMPT = (
    "The previous process exited with Windows status 4294967295 before a JSON decision. "
    "Do not restart the mission from the beginning. Continue the same session from work already done. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)
SESSIONLESS_ABORT_CONTINUE_PROMPT = (
    "The previous process exited with Windows status 4294967295 after a tool result "
    "and before a JSON decision. No session id was recorded. Do not resume a session. "
    "Do not restart the mission from the beginning. Continue from files already changed in the workspace. "
    "Finish the unfinished edit, then reply with only the JSON decision object."
)


@dataclass(frozen=True)
class _SessionRetry:
    source: str
    prompt: str | None
    session: Literal["required", "optional", "fresh"] = "required"


_FRESH_SESSION = _SessionRetry("fresh_session", None, "fresh")
_SESSION_RETRIES = {
    SESSION_ALREADY_IN_USE: _FRESH_SESSION,
    SESSION_NOT_FOUND: _FRESH_SESSION,
    OUTPUT_TRUNCATED: _SessionRetry("decision_only_resume", DECISION_ONLY_PROMPT),
    STEP_RETRIES_EXHAUSTED: _SessionRetry("step_retry_resume", STEP_CONTINUE_PROMPT),
    RESPONSE_STREAM_FAILED: _SessionRetry("stream_resume", STREAM_CONTINUE_PROMPT),
    AUTH_TEMPORARILY_UNAVAILABLE: _SessionRetry("wake_resume", WAKE_CONTINUE_PROMPT),
    TOKEN_GENERATION_FAILED: _SessionRetry("token_generation_resume", TOKEN_GENERATION_CONTINUE_PROMPT),
    INFERENCE_IDLE_TIMEOUT: _SessionRetry("inference_idle_resume", INFERENCE_IDLE_CONTINUE_PROMPT),
    SESSION_ACTOR_DEAD: _SessionRetry("dead_actor_fresh_session", DEAD_ACTOR_CONTINUE_PROMPT, "fresh"),
    DOOM_LOOP_REPETITION: _SessionRetry("doom_loop_resume", DOOM_LOOP_CONTINUE_PROMPT),
    BACKGROUND_TASK_WAIT: _SessionRetry("background_task_resume", BACKGROUND_CONTINUE_PROMPT, "optional"),
    ABNORMAL_PROCESS_EXIT: _SessionRetry("abnormal_process_resume", ABNORMAL_EXIT_CONTINUE_PROMPT, "optional"),
    SESSIONLESS_PROCESS_ABORT: _SessionRetry("sessionless_abort_continue", SESSIONLESS_ABORT_CONTINUE_PROMPT, "fresh"),
}


_TOOL_RESULT_MARKER = '"role":"tool"'
ARTIFACT_NAMES = (
    "latest-cursor-run.json",
    "latest-grok-run.json",
    "latest-kimi-run.json",
    "latest-codex-run.json",
    "latest-local-run.json",
)

_QUOTA_MARKERS = (
    "payment required",
    "usage balance exhausted",
    "quota exceeded",
    "rate limit",
    "status 402",
    "status=402",
    '"http_status": 402',
    # HTTP 403 credit blocks. A bare 403 Forbidden is not quota.
    "spending-limit",
    "spending limit",
    "personal-team-blocked",
    "run out of credits",
    "out of credits",
    "usage limit",
)
_AUTH_MARKERS = (
    "authentication failed",
    "unauthorized",
    "invalid api key",
    "invalid token",
    "status 401",
    "status=401",
    '"http_status": 401',
)

# Frozen shape of the 2026-08-16 turn-13 Grok 402 that died pre-decision.
HARVESTED_GROK_402 = {
    "returncode": 1,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": (
        '{"type":"error","message":"Internal error: {\\n  \\"message\\": '
        '\\"API error (status 402 Payment Required): Grok Build usage '
        'balance exhausted\\",\\n  \\"http_status\\": 402\\n}"}'
    ),
    "stderr_tail": (
        "ERROR responses API error status=402 Payment Required "
        "error_message=Grok Build usage balance exhausted"
    ),
}


@dataclass(frozen=True)
class KernelFailureClass:
    class_id: str
    retryable: bool
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KernelSalvage:
    class_id: str
    retryable: bool
    source: str
    decision: dict[str, Any]
    failover_kernel: str
    evidence: str
    artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_json_decision(message: str) -> dict[str, Any]:
    """Find the last valid decision object in a model response."""

    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, character in enumerate(message):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(message[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "status" in payload:
            candidates.append(payload)
    if not candidates:
        raise ValueError("Kernel final message did not contain a JSON decision object.")
    return candidates[-1]


def try_extract_json_decision(message: str) -> dict[str, Any] | None:
    if not (message or "").strip():
        return None
    try:
        return extract_json_decision(message)
    except ValueError:
        return None


def _haystack(*parts: str) -> str:
    return "\n".join(part or "" for part in parts).lower()


def _contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(marker in text for marker in markers)


def _has_tool_result(text: str) -> bool:
    """True when a transcript contains a tool-result record.

    The harvested Kimi abort writes ``{"role":"tool"``. A sentence that only
    mentions a tool does not. Spaces around the colon still count.
    """

    return _TOOL_RESULT_MARKER in str(text or "").replace(" ", "")


def _resume_session_id(session_id: str, command: Any) -> str:
    """Session id already chosen for this launch, including ``--resume``."""

    direct = str(session_id or "").strip()
    if direct:
        return direct
    if isinstance(command, (list, tuple)):
        return session_id_from_artifact({"command": list(command)})
    return ""


def classify_kernel_failure(
    *,
    returncode: int = 0,
    timed_out: bool = False,
    stdout_tail: str = "",
    stderr_tail: str = "",
    last_message: str = "",
    error: str = "",
    session_id: str = "",
    command: Any = None,
    kernel: str = "",
) -> KernelFailureClass:
    blob = _haystack(stdout_tail, stderr_tail, last_message, error)
    evidence = (error or stderr_tail or stdout_tail or last_message or "")[:400]
    code = int(returncode or 0)
    failed = bool(code or timed_out)

    # Scope the login refusal to the failing Cursor process's own diagnostic line.
    if kernel == "cursor" and code and not timed_out and any(
        line.lstrip().startswith("error: authentication required.") and "agent login" in line and "cursor_api_key" in line
        for line in stderr_tail.lower().splitlines()
    ):
        return KernelFailureClass("auth_failed", False, evidence)

    def mentions(*phrases: str) -> bool:
        return all(phrase in blob for phrase in phrases)

    # Provider diagnoses take precedence over incidental tool timeouts in the same receipt.
    if failed and mentions("authentication is temporarily unavailable", "still signed in", "no need to run"):
        return KernelFailureClass(AUTH_TEMPORARILY_UNAVAILABLE, False, evidence)
    if code and mentions("internal error during token generation", "status 500"):
        return KernelFailureClass(TOKEN_GENERATION_FAILED, False, evidence)
    if failed and mentions("inference idle timeout", "no chunks"):
        return KernelFailureClass(INFERENCE_IDLE_TIMEOUT, False, evidence)
    if failed and mentions("resident session actor exited unexpectedly", "reaping as deadfailed"):
        return KernelFailureClass(SESSION_ACTOR_DEAD, False, evidence)
    timeout = timed_out or "timed out" in blob
    # Under timeout both truncation markers must agree; either suffices on a clean nonzero exit.
    truncated = mentions(*_OUTPUT_TRUNCATION_MARKERS) if timeout else _contains_any(blob, _OUTPUT_TRUNCATION_MARKERS)
    if code and truncated:
        return KernelFailureClass(OUTPUT_TRUNCATED, False, evidence)
    if failed and mentions("doom loop detected", "tail_repetition"):
        return KernelFailureClass(DOOM_LOOP_REPETITION, False, evidence)
    if code and _contains_any(blob, _COMMAND_LINE_TOO_LONG_MARKERS):
        return KernelFailureClass(COMMAND_LINE_TOO_LONG, False, evidence)
    if code and "reqwest error stream" in blob:
        return KernelFailureClass(RESPONSE_STREAM_FAILED, False, evidence)
    if (timed_out or code == 124) and "background task still running" in blob:
        return KernelFailureClass(BACKGROUND_TASK_WAIT, False, evidence)
    if timeout:
        return KernelFailureClass("timeout", True, evidence)
    if _contains_any(blob, _QUOTA_MARKERS):
        return KernelFailureClass("quota_exhausted", False, evidence)
    if _contains_any(blob, _AUTH_MARKERS):
        return KernelFailureClass("auth_failed", False, evidence)
    if code:
        if not str(session_id or "").strip() and "disconnected before secure tls connection was established" in blob:
            return KernelFailureClass(PRE_SESSION_TRANSPORT_ABORT, False, evidence)
        for class_id, phrases in _EXIT_DIAGNOSES:
            if mentions(*phrases):
                return KernelFailureClass(class_id, False, evidence)
        if code & _UNSIGNED_PROCESS_EXIT == _UNSIGNED_PROCESS_EXIT:
            if _resume_session_id(session_id, command):
                return KernelFailureClass(ABNORMAL_PROCESS_EXIT, False, evidence)
            if _has_tool_result(f"{stdout_tail}\n{stderr_tail}"):
                return KernelFailureClass(SESSIONLESS_PROCESS_ABORT, False, evidence)
    if "did not contain a json decision" in blob or "malformed" in blob:
        return KernelFailureClass("malformed_decision", True, evidence)
    if "no final message" in blob or (returncode == 0 and not (last_message or "").strip()):
        return KernelFailureClass("empty_message", True, evidence)
    return KernelFailureClass("cli_error", True, evidence)


def classify_run_artifact(artifact: dict[str, Any], *, error: str = "", kernel: str = "") -> KernelFailureClass:
    preflight = artifact.get("provider_preflight")
    if not kernel and isinstance(preflight, Mapping):
        kernel = str(preflight.get("provider") or "")
    return classify_kernel_failure(
        kernel=kernel,
        returncode=int(artifact.get("returncode") or 0),
        timed_out=bool(artifact.get("timed_out")),
        stdout_tail=str(artifact.get("stdout_tail") or ""),
        stderr_tail=str(artifact.get("stderr_tail") or ""),
        last_message=str(artifact.get("last_message") or ""),
        error=error,
        session_id=str(artifact.get("session_id") or ""),
        command=artifact.get("command"),
    )


def session_id_from_artifact(artifact: Mapping[str, Any] | None) -> str:
    """Return a session id recorded on a kernel run, including Grok's command."""

    artifact = artifact or {}
    direct = str(artifact.get("session_id") or "").strip()
    if direct:
        return direct
    command = artifact.get("command")
    if not isinstance(command, list):
        return ""
    flags = {"--resume", "--session-id", "--session"}
    for index, item in enumerate(command):
        if str(item) in flags and index + 1 < len(command):
            candidate = str(command[index + 1] or "").strip()
            if candidate:
                return candidate
    return ""


def load_kernel_run_artifact(turn_dir: Path, *, kernel: str = "") -> dict[str, Any]:
    kernel_dir = turn_dir / "kernel"
    if kernel and kernel not in FAILOVER_ORDER:
        return {}
    names = (f"latest-{kernel}-run.json",) if kernel else ARTIFACT_NAMES
    for name in names:
        path = kernel_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["_artifact_path"] = str(path)
            return payload
    return {}


def _publish_attempt(attempt: Path, kernel: str) -> None:
    """Refresh the operator's latest files. Only the attempt's own receipt can drive recovery."""
    if kernel not in FAILOVER_ORDER:
        return
    for suffix in ("run.json", "last-message.md" if kernel == LOCAL_KERNEL else "provider-preflight.json"):
        name = f"latest-{kernel}-{suffix}"
        source = attempt / "kernel" / name
        try:
            text = source.read_text(encoding="utf-8")
            if source.suffix == ".json" and not isinstance(json.loads(text), dict):
                raise ValueError("expected a JSON object")
            atomic_write_text(attempt.parent / "kernel" / name, text)
        except FileNotFoundError:
            continue  # Preflight can fail before the adapter writes a run receipt.
        except (OSError, ValueError) as error:
            logging.getLogger(__name__).warning("Could not refresh %s: %s", name, error)


def installed_first_class_kernels(*, which: Callable[[str], str | None] = shutil.which) -> set[str]:
    from blackhole_agent.kernels.cursor_cli import resolve_cursor_binary

    installed = {name for name in CLI_FAILOVER_ORDER if name != "cursor" and which(name)}
    if resolve_cursor_binary(which=which):
        installed.add("cursor")
    return installed


def select_failover_kernel(
    current: str,
    installed: Iterable[str],
    *,
    health: KernelHealth | None = None,
    now: datetime | None = None,
    allow_local: bool = True,
    exclude: Iterable[str] = (),
) -> str:
    present = {name for name in installed if name}
    if allow_local:
        present.add(LOCAL_KERNEL)
    skipped = {name for name in exclude if name}
    skipped.add(current)
    for name in FAILOVER_ORDER:
        if name in skipped or name not in present:
            continue
        if health is not None and not kernel_is_available(health, name, now=now):
            continue
        return name
    return LOCAL_KERNEL if allow_local and LOCAL_KERNEL not in skipped else ""


def empty_decision(**overrides: Any) -> dict[str, Any]:
    overrides.setdefault("acceptance_probe", "")
    return empty_local_decision(**overrides)


def synthesize_decision(
    failure: KernelFailureClass,
    *,
    current_kernel: str,
    failover_kernel: str = "",
) -> dict[str, Any]:
    status = "continue"
    if failure.class_id == OUTPUT_TRUNCATED:
        summary = (
            f"Kernel {current_kernel} truncated by max_tokens. "
            "The session stays on a decision-only resume and the original mission prompt is not replayed."
        )
        strategy = "Resume the same session with a decision-only prompt. Do not replay the full mission prompt."
        next_step = "Resume the truncated session with a decision-only prompt."
    elif failure.class_id == STEP_RETRIES_EXHAUSTED:
        summary = (
            f"Kernel {current_kernel} exhausted its internal step retries. "
            "The same session continues once without replaying the mission prompt."
        )
        strategy = (
            "Resume the same session with a continuation prompt. Do not abandon the session on the first exhaustion."
        )
        next_step = f"Resume on the {current_kernel} kernel."
    elif failure.class_id in {SESSION_ALREADY_IN_USE, SESSION_NOT_FOUND}:
        if failure.class_id == SESSION_NOT_FOUND:
            reason = "the missing remote session was dropped"
            strategy = f"Drop the missing session and continue on {current_kernel}."
        else:
            reason = "the occupied session was released"
            strategy = f"Drop the occupied session and continue on {current_kernel}."
        summary = (
            f"Kernel {current_kernel} failed ({failure.class_id}); "
            f"{reason} so the same kernel can continue on a fresh session."
        )
        next_step = f"Resume on the {current_kernel} kernel with a fresh session."
    elif failure.class_id == ABNORMAL_PROCESS_EXIT:
        summary = (
            f"Kernel {current_kernel} exited with Windows status 4294967295 while a session was already selected. "
            "The same session continues once and the original mission prompt is not replayed."
        )
        strategy = "Resume the same session with a continuation prompt. Do not replay the full mission prompt."
        next_step = f"Resume the {current_kernel} session after the abnormal process exit."
    elif failure.class_id == SESSIONLESS_PROCESS_ABORT:
        summary = (
            f"Kernel {current_kernel} exited with Windows status 4294967295 "
            "after a tool result and before a session id existed. The same kernel continues once "
            "and the original mission prompt is not replayed."
        )
        strategy = (
            "Continue on the same kernel from files already changed. "
            "Do not attach a session id. Do not replay the full mission prompt."
        )
        next_step = f"Continue on the {current_kernel} kernel after the sessionless process abort."
    elif failover_kernel:
        summary = (
            f"Kernel {current_kernel} failed ({failure.class_id}); "
            f"failing over to {failover_kernel} so the mission does not stall."
        )
        strategy = f"Continue on {failover_kernel} after {failure.class_id} on {current_kernel}."
        next_step = f"Resume on the {failover_kernel} kernel."
    else:
        summary = f"Kernel {current_kernel} failed ({failure.class_id}) before a model decision. "
        if failure.retryable:
            summary += "Recorded a structured continue so the mission can retry."
            strategy = f"Retry {current_kernel} after a {failure.class_id} failure."
            next_step = "Retry the turn with the same mission state."
        else:
            status = "blocked"
            summary += "Recorded a structured blocked decision instead of stalling the mission."
            strategy = "Wait for provider/operator recovery; do not invent work while the kernel cannot run."
            next_step = f"Unblock {failure.class_id} on {current_kernel} or install another first-class kernel."
    return empty_decision(
        status=status,
        summary=summary,
        strategy=strategy,
        next_step=next_step,
        outcome_evidence=[failure.evidence] if failure.evidence else [],
    )


def salvage_kernel_failure(
    *,
    error: BaseException | str,
    current_kernel: str,
    last_message: str = "",
    artifact: dict[str, Any] | None = None,
    installed_kernels: Iterable[str] | None = None,
    allow_failover: bool = True,
    health: KernelHealth | None = None,
    now: datetime | None = None,
) -> KernelSalvage:
    artifact = artifact or {}
    error_text = str(error)
    blob = last_message or str(artifact.get("last_message") or "")
    if not blob:
        blob = str(artifact.get("stdout_tail") or "")
    parsed = try_extract_json_decision(blob)
    if current_kernel == "cursor" and artifact.get("decision_final") is not True:
        parsed = None
    if parsed:
        return KernelSalvage(
            class_id="decision_salvaged",
            retryable=True,
            source="message",
            decision=empty_decision(**{key: parsed[key] for key in empty_decision() if key in parsed}),
            failover_kernel="",
            evidence=error_text[:400],
            artifact_path=str(artifact.get("_artifact_path") or ""),
        )
    failure = classify_run_artifact(artifact, error=error_text, kernel=current_kernel)
    installed = (
        set(installed_kernels)
        if installed_kernels is not None
        else installed_first_class_kernels()
    )
    failover = ""
    if allow_failover and failure.class_id in FAILOVER_CLASSES:
        failover = select_failover_kernel(
            current_kernel,
            installed,
            health=health,
            now=now,
            allow_local=True,
        )
    return KernelSalvage(
        class_id=failure.class_id,
        retryable=failure.retryable,
        source="synthesized",
        decision=synthesize_decision(failure, current_kernel=current_kernel, failover_kernel=failover),
        failover_kernel=failover,
        evidence=failure.evidence,
        artifact_path=str(artifact.get("_artifact_path") or ""),
    )


def _synthetic_result(state: Any, salvaged: KernelSalvage, prior: Any, kernel_turn_result: Any) -> Any:
    return kernel_turn_result(
        kernel=getattr(state, "kernel", ""),
        last_message=getattr(prior, "last_message", "") or json.dumps(salvaged.decision),
        session_id=getattr(prior, "session_id", "") or getattr(state, "session_id", "") or "",
        command=tuple(getattr(prior, "command", ()) or ()),
        result_path=salvaged.artifact_path or getattr(prior, "result_path", ""),
    )


def _repo_from_state(state: Any) -> Path | None:
    value = getattr(state, "repo_path", None)
    return Path(value) if value else None


def _release_session(state: Any) -> None:
    state.session_id = ""
    state.session_started = False
    if hasattr(state, "decision_only_resume"):
        state.decision_only_resume = False


def _switch_kernel(state: Any, kernel: str) -> None:
    if getattr(state, "kernel", None) != kernel:
        state.kernel = kernel
        _release_session(state)
        if hasattr(state, "model"):
            state.model = None  # Provider-specific model names cannot cross a failover route.


def execute_kernel_turn_with_salvage(
    state: Any,
    prompt: str,
    turn_dir: Path,
    *,
    kernel_runner: Callable[..., Any],
    command_runner: Callable[..., Any] | None = None,
    refresh_prompt: Callable[[], str] | None = None,
    installed_kernels: Iterable[str] | None = None,
    health: KernelHealth | None = None,
    now: datetime | None = None,
    persist_health: bool = True,
    local_action: Callable[..., Any] | None = None,
    probe_peers: bool = True,
    peer_probe: Callable[[str], Mapping[str, Any]] | None = None,
) -> tuple[Any, Any, dict[str, Any]]:
    """Run the kernel; on death, salvage a decision instead of raising.

    Half-open peer CLI kernels are pinged before the requested kernel runs so
    cooldown recovery cannot stall behind a healthy mission kernel.
    A replacement kernel starts with the full task and a fresh view of the
    worktree. String-only callers can supply a fixed full task instead.
    Each dispatch writes to its own directory under the turn. Its result path
    remains readable after retries. The turn's latest files are refreshed at exit.
    """

    from blackhole_agent.kernel_half_open_probe import (
        disabled_peer_probe_report,
        probe_half_open_peer_kernels,
    )
    from blackhole_agent.unbound import KernelTurnResult, TurnDecision, extract_json_decision

    turn_dir = Path(turn_dir)
    repo = _repo_from_state(state)
    store = health if health is not None else (load_kernel_health(repo) if repo else KernelHealth())
    refresh_kernel_breakers(store, now=now)
    installed = (
        set(installed_kernels)
        if installed_kernels is not None
        else installed_first_class_kernels()
    )

    def persist() -> None:
        if persist_health and repo is not None:
            save_kernel_health(repo, store, now=now)

    persist()
    requested = str(getattr(state, "kernel", "") or "")
    peer_probe_report: dict[str, Any]
    if probe_peers:
        try:
            peer_probe_report = probe_half_open_peer_kernels(
                store,
                requested=requested,
                installed=installed,
                probe=peer_probe,
                now=now,
                persist=persist if persist_health else None,
            )
        except Exception as error:  # noqa: BLE001 - peer ping must not stall the mission
            peer_probe_report = {
                "ok": False,
                "skipped": False,
                "error": type(error).__name__,
                "requested": requested,
                "probed": [],
                "recovered": [],
                "retripped": [],
                "left_half_open": [],
            }
    else:
        peer_probe_report = disabled_peer_probe_report(requested)

    def with_probe_meta(meta: dict[str, Any]) -> dict[str, Any]:
        meta.setdefault("peer_probe", peer_probe_report)
        return meta

    def dispatch(attempt: Path) -> Any:
        if state.kernel == LOCAL_KERNEL:
            local = invoke_local_kernel(
                state,
                prompt,
                turn_dir,
                action=local_action,
                now=now,
                output_dir=attempt / "kernel",
            )
            return KernelTurnResult(
                kernel=LOCAL_KERNEL,
                last_message=str(local["last_message"]),
                session_id=str(local.get("session_id") or getattr(state, "session_id", "") or "local"),
                command=tuple(local.get("command") or ("local-capability-kernel",)),
                result_path=str(local.get("result_path") or ""),
            )
        return kernel_runner(
            state,
            prompt,
            attempt,
            command_runner=command_runner,
        )

    original = state.kernel
    original_prompt = prompt

    def full_task() -> str:
        return refresh_prompt() if refresh_prompt is not None else original_prompt

    tried: set[str] = set()
    with kernel_dispatch_admission(repo if persist_health else None, store, now=now) as admit:

        def reserve(candidate: str) -> str:
            while candidate and not admit(candidate):
                tried.add(candidate)
                candidate = select_failover_kernel(candidate, installed, health=store, now=now, exclude=tried)
            return candidate

        rerouted = reserve(apply_health_reroute(original, store, installed, now=now))
        if rerouted != original:
            _switch_kernel(state, rerouted)
            prompt = full_task()

        retries: set[tuple[str, str]] = set()
        source = "kernel"
        from_kernel = original
        salvaged = None
        turn_dir.mkdir(parents=True, exist_ok=True)
        while True:
            # Reserve before dispatch, even on a same-session retry or a reopened turn.
            attempt = Path(tempfile.mkdtemp(prefix="attempt-", dir=turn_dir))
            provider = state.kernel
            kernel_result = None
            try:
                try:
                    kernel_result = dispatch(attempt)
                finally:
                    _publish_attempt(attempt, provider)
                decision = TurnDecision.from_payload(extract_json_decision(kernel_result.last_message))
                mark_kernel_success(store, state.kernel, now=now)
                persist()
                if source == "kernel":
                    meta = {"ok": True, "source": source}
                    if rerouted != original:
                        meta.update({"rerouted_from": original, "health_reroute": True})
                else:
                    meta = salvaged.to_dict()
                    meta.update(
                        ok=True, source=source, from_kernel=from_kernel,
                        failover_kernel=state.kernel if source == "failover" else "",
                        released_session=source == "fresh_session",
                    )
                if source == "decision_only_resume" and hasattr(state, "decision_only_resume"):
                    state.decision_only_resume = False
                return kernel_result, decision, with_probe_meta(meta)
            except Exception as error:
                if kernel_result is not None:
                    state.session_id = kernel_result.session_id or state.session_id
                    state.session_started = bool(state.session_id) or state.session_started
                tried.add(state.kernel)
                artifact = load_kernel_run_artifact(attempt, kernel=provider)
                if state.kernel == "cursor" and artifact.get("session_id"):
                    state.session_id = str(artifact["session_id"])
                    state.session_started = True
                evidence = dict(
                    error=error, current_kernel=provider, artifact=artifact,
                    installed_kernels=installed, health=store, now=now,
                )
                message = kernel_result.last_message if kernel_result else ""
                salvaged = salvage_kernel_failure(**evidence, last_message=message)
                retry = _SESSION_RETRIES.get(salvaged.class_id)
                if retry is not None:
                    if retry.session != "fresh" and not str(getattr(state, "session_id", "") or "").strip():
                        adopted = session_id_from_artifact(artifact)
                        if adopted:
                            state.session_id = adopted
                            state.session_started = True
                    resumable = bool(str(getattr(state, "session_id", "") or "").strip()) and bool(
                        getattr(state, "session_started", False)
                    )
                    key = (state.kernel, retry.source)
                    if key not in retries and (retry.session != "required" or resumable):
                        persist()
                        if admit(state.kernel):
                            retries.add(key)
                            if retry.session == "fresh":
                                _release_session(state)
                            from_kernel = state.kernel
                            source = retry.source
                            prompt = retry.prompt if retry.prompt is not None else full_task()
                            continue
                    elif salvaged.class_id == OUTPUT_TRUNCATED and resumable:
                        state.decision_only_resume = True
                        exhausted = salvage_kernel_failure(**evidence, allow_failover=False)
                        decision = TurnDecision.from_payload(exhausted.decision)
                        result = _synthetic_result(state, exhausted, None, KernelTurnResult)
                        meta = exhausted.to_dict()
                        meta.update(
                            ok=False, exhausted=True, source="decision_only_resume",
                            from_kernel=state.kernel, failover_kernel="",
                        )
                        return result, decision, with_probe_meta(meta)
                if salvaged.class_id in FAILOVER_CLASSES and kernel_is_available(store, state.kernel, now=now):
                    trip_kernel(store, state.kernel, salvaged.class_id, salvaged.evidence, now=now)
                # A different turn may have taken our next provider out of service during dispatch.
                persist()
                if salvaged.source == "message":
                    receipt_session = session_id_from_artifact(artifact)
                    if receipt_session and not getattr(kernel_result, "session_id", ""):
                        state.session_id = receipt_session
                        state.session_started = True
                    decision = TurnDecision.from_payload(salvaged.decision)
                    result = _synthetic_result(state, salvaged, kernel_result, KernelTurnResult)
                    return result, decision, with_probe_meta(salvaged.to_dict())
                next_kernel = reserve(select_failover_kernel(provider, installed, health=store, now=now, exclude=tried))
                if not next_kernel:
                    blocked = salvage_kernel_failure(**evidence, last_message=message, allow_failover=False)
                    decision = TurnDecision.from_payload(blocked.decision)
                    result = _synthetic_result(state, blocked, kernel_result, KernelTurnResult)
                    return result, decision, with_probe_meta(blocked.to_dict())
                from_kernel = state.kernel
                _switch_kernel(state, next_kernel)
                source = "failover"
                prompt = full_task()


def builtin_kernel_decision_salvage_proof() -> dict[str, Any]:
    """Hermetic proof: the harvested 402 cannot stall a turn without a decision."""

    from blackhole_agent.pattern_register import classify_unbound_turn
    from blackhole_agent.unbound import KernelTurnResult, TurnDecision

    checks: dict[str, bool] = {}
    harvested = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    checks["harvested_402"] = harvested.class_id == "quota_exhausted" and not harvested.retryable

    blocked = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
        allow_failover=False,
    )
    checks["blocks_when_failover_disabled"] = (
        blocked.decision["status"] == "blocked" and blocked.class_id == "quota_exhausted"
    )
    local = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels=set(),
    )
    checks["failsover_to_local"] = (
        local.failover_kernel == LOCAL_KERNEL and local.decision["status"] == "continue"
    )

    failover = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        artifact=HARVESTED_GROK_402,
        installed_kernels={"kimi"},
    )
    checks["failsover_to_peer"] = (
        failover.failover_kernel == "kimi" and failover.decision["status"] == "continue"
    )

    salvaged = salvage_kernel_failure(
        error="Grok CLI failed with exit code 1",
        current_kernel="grok",
        last_message='note {"status":"continue","summary":"kept working"}',
        installed_kernels=set(),
    )
    checks["salvages_embedded_decision"] = (
        salvaged.source == "message" and salvaged.decision["status"] == "continue"
    )

    timeout = classify_kernel_failure(timed_out=True, error="Timed out after 30 seconds.")
    checks["timeout_retryable"] = timeout.class_id == "timeout" and timeout.retryable

    spending = classify_kernel_failure(
        returncode=1,
        stdout_tail=(
            '{"type":"error","message":"API error (status 403 Forbidden): '
            'personal-team-blocked:spending-limit: You have run out of credits"}'
        ),
        stderr_tail=(
            "status=403 Forbidden error_message=personal-team-blocked:spending-limit: "
            "You have run out of credits"
        ),
        error="Grok CLI failed with exit code 1",
    )
    checks["harvested_403_spending_limit"] = (
        spending.class_id == "quota_exhausted" and not spending.retryable
    )
    kimi_usage = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "provider.auth_error: 403 You've reached your usage limit for this billing cycle."
        ),
        error="Kimi CLI failed with exit code 1",
    )
    checks["kimi_usage_limit_is_quota"] = (
        kimi_usage.class_id == "quota_exhausted" and not kimi_usage.retryable
    )
    plain_forbidden = classify_kernel_failure(
        returncode=1,
        stderr_tail="HTTP 403 Forbidden",
        error="request failed",
    )
    checks["bare_403_stays_cli_error"] = (
        plain_forbidden.class_id == "cli_error" and plain_forbidden.retryable
    )
    signed_out = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            'Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")\n'
            "Error: Not signed in. Run `grok login` to authenticate "
            "(or `grok login --device-code` if no browser is available).\n"
        ),
        stdout_tail=(
            '{"type":"error","message":"Not signed in. Run `grok login` to authenticate"}\n'
        ),
        error="Grok CLI failed with exit code 1",
    )
    checks["grok_signed_out_is_auth"] = (
        signed_out.class_id == "auth_failed" and not signed_out.retryable
    )
    credential_warning = classify_kernel_failure(
        returncode=1,
        stderr_tail='WARN Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")',
        error="Grok CLI failed with exit code 1",
    )
    checks["grok_credential_warning_stays_cli_error"] = (
        credential_warning.class_id == "cli_error" and credential_warning.retryable
    )
    response_stream = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            'ERROR error=Internal error: "reqwest error stream: Transport error: '
            'error decoding response body"'
        ),
        stdout_tail=(
            '{"type":"error","message":"Internal error: reqwest error stream: '
            'error decoding response body"}'
        ),
        error="Grok CLI failed with exit code 1",
    )
    checks["grok_response_stream_is_not_retryable"] = (
        response_stream.class_id == RESPONSE_STREAM_FAILED and not response_stream.retryable
    )
    telemetry = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            'ERROR name="BatchSpanProcessor.ExportError" '
            'error="Operation failed: HTTP export failed: network error"'
        ),
        error="Grok CLI failed with exit code 1",
    )
    checks["telemetry_network_error_stays_cli_error"] = (
        telemetry.class_id == "cli_error" and telemetry.retryable
    )
    doom_loop = classify_kernel_failure(
        returncode=124,
        timed_out=True,
        stderr_tail=(
            "WARN grep timed out timeout_secs=20\n"
            "WARN doom-loop recovery: retaining the failed response and retrying with guidance "
            "reason=doom loop detected: tail_repetition:64@thinking"
        ),
        error="Grok CLI timed out after 7200 seconds",
    )
    checks["grok_doom_loop_is_not_a_tool_timeout"] = (
        doom_loop.class_id == DOOM_LOOP_REPETITION and not doom_loop.retryable
    )

    events = classify_unbound_turn(
        {
            "iteration": 13,
            "effective_status": "blocked",
            "requested_status": "blocked",
            "summary": blocked.decision["summary"],
            "kernel_salvage": blocked.to_dict(),
        }
    )
    checks["not_kernel_turn_failed"] = not any(
        item.get("class_id") == "kernel_turn_failed" for item in events
    )

    class _State:
        kernel = "grok"
        session_id = "sess"
        session_started = True

    with tempfile.TemporaryDirectory(prefix="kernel-salvage-") as tmp:
        turn_dir = Path(tmp) / "turn"
        def boom(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
            receipt = turn_dir / "kernel" / "latest-grok-run.json"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(HARVESTED_GROK_402), encoding="utf-8")
            raise RuntimeError("Grok CLI failed with exit code 1")

        result, decision, meta = execute_kernel_turn_with_salvage(
            _State(),
            "prompt",
            turn_dir,
            kernel_runner=boom,
            installed_kernels=set(),
            persist_health=False,
        )
    checks["execute_does_not_raise"] = (
        isinstance(decision, TurnDecision)
        and decision.status == "continue"
        and meta.get("source") == "failover"
        and meta.get("failover_kernel") == LOCAL_KERNEL
        and isinstance(result, KernelTurnResult)
        and bool(result.last_message)
    )

    calls: list[str] = []

    class _FailoverState:
        kernel = "grok"
        session_id = "sess"
        session_started = True

    def runner(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
        calls.append(state.kernel)
        if state.kernel == "grok":
            raise RuntimeError(
                "Grok CLI failed with exit code 1; Payment Required usage balance exhausted"
            )
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=json.dumps(empty_decision(status="continue", summary="peer kernel ran")),
            session_id="peer",
            command=("peer",),
            result_path="",
        )

    state = _FailoverState()
    with tempfile.TemporaryDirectory(prefix="kernel-failover-") as tmp:
        _result, peer_decision, peer_meta = execute_kernel_turn_with_salvage(
            state,
            "prompt",
            Path(tmp),
            kernel_runner=runner,
            installed_kernels={"kimi"},
        )
    checks["same_turn_failover"] = (
        calls == ["grok", "kimi"]
        and state.kernel == "kimi"
        and peer_decision.status == "continue"
        and peer_meta.get("source") == "failover"
        and peer_decision.summary == "peer kernel ran"
    )
    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "kernel_decision_salvage",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "used_skill_route_discovery": False,
    }
