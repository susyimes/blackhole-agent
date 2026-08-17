"""Salvage a structured Unbound decision when a kernel CLI dies.

Harvested class ``kernel_turn_failed`` is a kernel that exits (402 quota,
timeout, empty last_message, malformed JSON) before the controller can record
a turn decision. This module classifies the failure, reuses any parseable
decision, fails over to another installed first-class kernel on quota/auth,
and otherwise synthesizes a blocked or continue decision so the mission loop
does not stall.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

FAILOVER_ORDER = ("codex", "kimi", "grok")
FAILOVER_CLASSES = frozenset({"quota_exhausted", "auth_failed"})
ARTIFACT_NAMES = ("latest-grok-run.json", "latest-kimi-run.json", "latest-codex-run.json")

_QUOTA_MARKERS = (
    "payment required",
    "usage balance exhausted",
    "quota exceeded",
    "rate limit",
    "status 402",
    "status=402",
    '"http_status": 402',
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


def classify_kernel_failure(
    *,
    returncode: int = 0,
    timed_out: bool = False,
    stdout_tail: str = "",
    stderr_tail: str = "",
    last_message: str = "",
    error: str = "",
) -> KernelFailureClass:
    blob = _haystack(stdout_tail, stderr_tail, last_message, error)
    evidence = (error or stderr_tail or stdout_tail or last_message or "")[:400]
    if timed_out or "timed out" in blob:
        return KernelFailureClass("timeout", True, evidence)
    if _contains_any(blob, _QUOTA_MARKERS):
        return KernelFailureClass("quota_exhausted", False, evidence)
    if _contains_any(blob, _AUTH_MARKERS):
        return KernelFailureClass("auth_failed", False, evidence)
    if "did not contain a json decision" in blob or "malformed" in blob:
        return KernelFailureClass("malformed_decision", True, evidence)
    if "no final message" in blob or (returncode == 0 and not (last_message or "").strip()):
        return KernelFailureClass("empty_message", True, evidence)
    return KernelFailureClass("cli_error", True, evidence)


def classify_run_artifact(artifact: dict[str, Any], *, error: str = "") -> KernelFailureClass:
    return classify_kernel_failure(
        returncode=int(artifact.get("returncode") or 0),
        timed_out=bool(artifact.get("timed_out")),
        stdout_tail=str(artifact.get("stdout_tail") or ""),
        stderr_tail=str(artifact.get("stderr_tail") or ""),
        last_message=str(artifact.get("last_message") or ""),
        error=error,
    )


def load_kernel_run_artifact(turn_dir: Path) -> dict[str, Any]:
    kernel_dir = turn_dir / "kernel"
    if not kernel_dir.is_dir():
        return {}
    for name in ARTIFACT_NAMES:
        path = kernel_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["_artifact_path"] = str(path)
            return payload
    return {}


def installed_first_class_kernels(*, which: Callable[[str], str | None] = shutil.which) -> set[str]:
    return {name for name in FAILOVER_ORDER if which(name)}


def select_failover_kernel(current: str, installed: Iterable[str]) -> str:
    present = set(installed)
    for name in FAILOVER_ORDER:
        if name != current and name in present:
            return name
    return ""


def empty_decision(**overrides: Any) -> dict[str, Any]:
    payload = {
        "status": "continue",
        "summary": "",
        "strategy": "",
        "next_step": "",
        "capability_delta": "",
        "outcome_evidence": [],
        "validation": [],
        "done_when_met": False,
        "commit_message": "",
        "mission_goal": "",
        "done_when": "",
    }
    payload.update(overrides)
    return payload


def synthesize_decision(
    failure: KernelFailureClass,
    *,
    current_kernel: str,
    failover_kernel: str = "",
) -> dict[str, Any]:
    if failover_kernel:
        return empty_decision(
            status="continue",
            summary=(
                f"Kernel {current_kernel} failed ({failure.class_id}); "
                f"failing over to {failover_kernel} so the mission does not stall."
            ),
            strategy=f"Continue on {failover_kernel} after {failure.class_id} on {current_kernel}.",
            next_step=f"Resume on the {failover_kernel} kernel.",
            outcome_evidence=[failure.evidence] if failure.evidence else [],
        )
    if not failure.retryable:
        return empty_decision(
            status="blocked",
            summary=(
                f"Kernel {current_kernel} failed ({failure.class_id}) before a model decision. "
                "Recorded a structured blocked decision instead of stalling the mission."
            ),
            strategy="Wait for provider/operator recovery; do not invent work while the kernel cannot run.",
            next_step=(
                f"Unblock {failure.class_id} on {current_kernel} or install another first-class kernel."
            ),
            outcome_evidence=[failure.evidence] if failure.evidence else [],
        )
    return empty_decision(
        status="continue",
        summary=(
            f"Kernel {current_kernel} failed ({failure.class_id}) before a model decision. "
            "Recorded a structured continue so the mission can retry."
        ),
        strategy=f"Retry {current_kernel} after a {failure.class_id} failure.",
        next_step="Retry the turn with the same mission state.",
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
) -> KernelSalvage:
    artifact = artifact or {}
    error_text = str(error)
    blob = last_message or str(artifact.get("last_message") or "")
    if not blob:
        blob = str(artifact.get("stdout_tail") or "")
    parsed = try_extract_json_decision(blob)
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
    failure = classify_run_artifact(artifact, error=error_text)
    installed = (
        set(installed_kernels)
        if installed_kernels is not None
        else installed_first_class_kernels()
    )
    failover = ""
    if allow_failover and failure.class_id in FAILOVER_CLASSES:
        failover = select_failover_kernel(current_kernel, installed)
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
    last_message = ""
    command: tuple[str, ...] = ()
    result_path = salvaged.artifact_path
    session_id = getattr(state, "session_id", "") or ""
    if prior is not None:
        last_message = prior.last_message or last_message
        command = tuple(prior.command or ())
        result_path = result_path or prior.result_path
        session_id = prior.session_id or session_id
    return kernel_turn_result(
        kernel=getattr(state, "kernel", ""),
        last_message=last_message or json.dumps(salvaged.decision),
        session_id=session_id,
        command=command,
        result_path=result_path,
    )


def execute_kernel_turn_with_salvage(
    state: Any,
    prompt: str,
    turn_dir: Path,
    *,
    kernel_runner: Callable[..., Any],
    command_runner: Callable[..., Any] | None = None,
    installed_kernels: Iterable[str] | None = None,
) -> tuple[Any, Any, dict[str, Any]]:
    """Run the kernel; on death, salvage a decision instead of raising."""

    from blackhole_agent.unbound import KernelTurnResult, TurnDecision, extract_json_decision

    kernel_result = None
    try:
        kernel_result = kernel_runner(
            state,
            prompt,
            turn_dir,
            command_runner=command_runner,
        )
        decision = TurnDecision.from_payload(extract_json_decision(kernel_result.last_message))
        return kernel_result, decision, {"ok": False, "source": "kernel"}
    except Exception as error:
        if kernel_result is not None:
            state.session_id = kernel_result.session_id or state.session_id
            state.session_started = bool(state.session_id) or state.session_started
        artifact = load_kernel_run_artifact(turn_dir)
        salvaged = salvage_kernel_failure(
            error=error,
            current_kernel=state.kernel,
            last_message=kernel_result.last_message if kernel_result else "",
            artifact=artifact,
            installed_kernels=installed_kernels,
        )
        if salvaged.source == "message":
            decision = TurnDecision.from_payload(salvaged.decision)
            result = kernel_result or _synthetic_result(state, salvaged, None, KernelTurnResult)
            return result, decision, salvaged.to_dict()
        if salvaged.failover_kernel:
            previous = state.kernel
            state.kernel = salvaged.failover_kernel
            state.session_id = ""
            state.session_started = False
            try:
                kernel_result = kernel_runner(
                    state,
                    prompt,
                    turn_dir,
                    command_runner=command_runner,
                )
                decision = TurnDecision.from_payload(extract_json_decision(kernel_result.last_message))
                meta = salvaged.to_dict()
                meta.update({"ok": True, "source": "failover", "from_kernel": previous})
                return kernel_result, decision, meta
            except Exception as failover_error:
                artifact = load_kernel_run_artifact(turn_dir)
                salvaged = salvage_kernel_failure(
                    error=failover_error,
                    current_kernel=state.kernel,
                    last_message=kernel_result.last_message if kernel_result else "",
                    artifact=artifact,
                    installed_kernels=installed_kernels,
                    allow_failover=False,
                )
        decision = TurnDecision.from_payload(salvaged.decision)
        result = _synthetic_result(state, salvaged, kernel_result, KernelTurnResult)
        return result, decision, salvaged.to_dict()


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
    )
    checks["blocks_without_peer"] = (
        blocked.decision["status"] == "blocked" and blocked.class_id == "quota_exhausted"
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

    import tempfile

    class _State:
        kernel = "grok"
        session_id = "sess"
        session_started = True

    with tempfile.TemporaryDirectory(prefix="kernel-salvage-") as tmp:
        turn_dir = Path(tmp) / "turn"
        (turn_dir / "kernel").mkdir(parents=True)
        (turn_dir / "kernel" / "latest-grok-run.json").write_text(
            json.dumps(HARVESTED_GROK_402),
            encoding="utf-8",
        )

        def boom(state: Any, prompt: str, turn_dir: Path, **kwargs: Any) -> Any:
            raise RuntimeError("Grok CLI failed with exit code 1")

        result, decision, meta = execute_kernel_turn_with_salvage(
            _State(),
            "prompt",
            turn_dir,
            kernel_runner=boom,
            installed_kernels=set(),
        )
    checks["execute_does_not_raise"] = (
        isinstance(decision, TurnDecision)
        and decision.status == "blocked"
        and meta.get("class_id") == "quota_exhausted"
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
