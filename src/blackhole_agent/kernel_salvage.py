"""Salvage a structured Unbound decision when a kernel CLI dies.

Harvested class ``kernel_turn_failed`` is a kernel that exits (402 quota,
timeout, empty last_message, malformed JSON) before the controller can record
a turn decision. This module classifies the failure, reuses any parseable
decision, trips the kernel circuit breaker on quota/auth and on a pre-session
transport abort, releases an occupied session id and retries that same kernel
once on a fresh session, fails over to another installed first-class kernel or
the local capability kernel, and otherwise synthesizes a blocked or continue
decision so the mission loop does not stall or retry a dead kernel.

A spent account is quota even when the provider stopped using HTTP 402.
Harvested Grok runs return HTTP 403 ``personal-team-blocked:spending-limit``
(``run out of credits``), and harvested Kimi runs return a billing-cycle
``usage limit`` labeled ``auth_error``. Both used to stay a retryable CLI
error, so the next turn launched the same kernel again.

A kernel that rejects the requested model is not a retry of that same launch.
The 2026-10-15 Cursor run exited 1 with ``Cannot use this model:
grok-4.7-xhigh``, and 2026-09-04 Kimi runs exited because ``Model "grok-4.6"
is not configured in config.toml``. Both stayed a retryable CLI error, so the
next resolution launched the same kernel with the same unavailable model.

A Kimi launch that never obtains an access token is an auth failure of that
kernel. Harvested runs exited 1 with ``failed to fetch an access token``
after TLS disconnect, ``ENOTFOUND auth.kimi.com``, or ``ECONNRESET``. The
session id was often already set, so the pre-session transport rule did not
match, and the next resolution launched Kimi again.

A provider that has already retried and still returns HTTP 429 is not a spent
account and not a transient CLI blip. The 2026-08-02 Kimi run exited 1 with
``provider.rate_limit`` and ``The engine is currently overloaded, please try
again later`` after its own retry loop. That stayed a retryable CLI error, so
the next resolution launched Kimi again.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from blackhole_agent.kernel_health import (
    CLI_FAILOVER_ORDER,
    FAILOVER_ORDER,
    LOCAL_KERNEL,
    TRIP_CLASSES,
    KernelHealth,
    apply_health_reroute,
    invoke_local_kernel,
    kernel_is_available,
    load_kernel_health,
    mark_kernel_success,
    refresh_kernel_breakers,
    save_kernel_health,
    trip_kernel,
)

PRE_SESSION_TRANSPORT_ABORT = "pre_session_transport_abort"
SESSION_ALREADY_IN_USE = "session_already_in_use"
MODEL_UNAVAILABLE = "model_unavailable"
PROVIDER_OVERLOADED = "provider_overloaded"
# Quota and auth trip the breaker. A pre-session TLS abort does too: the
# 2026-10-18 Cursor run exited before a session id existed, and treating it
# as a retryable CLI error relaunched the same kernel on resume.
# An occupied session does not trip the breaker. The 2026-09-01 and
# 2026-09-03 Grok runs exited because ``--session-id`` was already in use;
# the kernel was healthy, and retrying that same id fails again.
# Spending-limit and billing-cycle usage limits are quota_exhausted, which
# is already a trip class. The 2026-07-29 Grok runs and the 2026-08-15 Kimi
# runs used HTTP 403 instead of HTTP 402.
# A rejected model trips the breaker too. Retrying Cursor with grok-4.7-xhigh
# or Kimi with an unconfigured grok-4.6 dies the same way. Failover clears
# the provider-specific model name.
# Provider overload trips the breaker too. The harvested Kimi 429 already
# retried inside the CLI. Launching that kernel again hits the same engine.
FAILOVER_CLASSES = TRIP_CLASSES | frozenset(
    {PRE_SESSION_TRANSPORT_ABORT, MODEL_UNAVAILABLE, PROVIDER_OVERLOADED}
)
_TRANSPORT_ABORT_MARKERS = (
    "disconnected before secure tls connection was established",
)
_SESSION_OCCUPIED_MARKERS = (
    "session id",
    "already in use",
)
# Harvested rejection strings. A Codex "unknown model ... fallback" warning
# is not a rejection, and a bare 403 is not a model failure.
_MODEL_REJECTION_MARKERS = (
    "cannot use this model",
)
_MODEL_CONFIG_MARKERS = (
    "is not configured in config.toml",
)
# Harvested Kimi deaths (2026-08-02/03). The provider never issued a token.
# A socket error that does not mention token fetch stays on its existing path.
_TOKEN_FETCH_MARKERS = (
    "failed to fetch an access token",
)
# Harvested Kimi death (2026-08-02). The CLI already retried the 429.
# A bare 429 or the word "overloaded" without this provider phrasing is not
# this class. Quota markers such as "rate limit" do not match "rate_limit".
_PROVIDER_OVERLOAD_MARKERS = (
    "provider.rate_limit",
    "engine is currently overloaded",
)
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


def _is_model_unavailable(blob: str) -> bool:
    """True for a harvested model rejection, not an unknown-model warning."""

    if _contains_any(blob, _MODEL_REJECTION_MARKERS):
        return True
    return "model " in blob and _contains_any(blob, _MODEL_CONFIG_MARKERS)


def classify_kernel_failure(
    *,
    returncode: int = 0,
    timed_out: bool = False,
    stdout_tail: str = "",
    stderr_tail: str = "",
    last_message: str = "",
    error: str = "",
    session_id: str = "",
) -> KernelFailureClass:
    blob = _haystack(stdout_tail, stderr_tail, last_message, error)
    evidence = (error or stderr_tail or stdout_tail or last_message or "")[:400]
    if timed_out or "timed out" in blob:
        return KernelFailureClass("timeout", True, evidence)
    if _contains_any(blob, _QUOTA_MARKERS):
        return KernelFailureClass("quota_exhausted", False, evidence)
    if _contains_any(blob, _AUTH_MARKERS):
        return KernelFailureClass("auth_failed", False, evidence)
    if (
        int(returncode or 0) != 0
        and not str(session_id or "").strip()
        and _contains_any(blob, _TRANSPORT_ABORT_MARKERS)
    ):
        return KernelFailureClass(PRE_SESSION_TRANSPORT_ABORT, False, evidence)
    if int(returncode or 0) != 0 and all(marker in blob for marker in _SESSION_OCCUPIED_MARKERS):
        # The occupied id is not retryable. The kernel itself stays available.
        return KernelFailureClass(SESSION_ALREADY_IN_USE, False, evidence)
    if int(returncode or 0) != 0 and _is_model_unavailable(blob):
        # The same model on the same kernel fails again. Failover, do not retry.
        return KernelFailureClass(MODEL_UNAVAILABLE, False, evidence)
    if int(returncode or 0) != 0 and _contains_any(blob, _TOKEN_FETCH_MARKERS):
        # Token fetch died after a session id existed, so this is not the
        # empty-session transport abort. The kernel cannot authenticate.
        return KernelFailureClass("auth_failed", False, evidence)
    if int(returncode or 0) != 0 and _contains_any(blob, _PROVIDER_OVERLOAD_MARKERS):
        # The provider already retried. Another immediate launch of this kernel
        # dies the same way. This is not a spent account (quota_exhausted).
        return KernelFailureClass(PROVIDER_OVERLOADED, False, evidence)
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
        session_id=str(artifact.get("session_id") or ""),
    )


def load_kernel_run_artifact(turn_dir: Path, *, kernel: str = "") -> dict[str, Any]:
    kernel_dir = turn_dir / "kernel"
    if not kernel_dir.is_dir():
        return {}
    names = (f"latest-{kernel}-run.json",) if kernel in {*CLI_FAILOVER_ORDER, LOCAL_KERNEL} else ARTIFACT_NAMES
    for name in names:
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
    payload = {
        "status": "continue",
        "summary": "",
        "strategy": "",
        "next_step": "",
        "capability_delta": "",
        "outcome_evidence": [],
        "validation": [],
        "acceptance_probe": "",
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
    if failure.class_id == SESSION_ALREADY_IN_USE:
        return empty_decision(
            status="continue",
            summary=(
                f"Kernel {current_kernel} failed ({failure.class_id}); "
                "the occupied session was released so the same kernel can continue "
                "on a fresh session."
            ),
            strategy=f"Drop the occupied session and continue on {current_kernel}.",
            next_step=f"Resume on the {current_kernel} kernel with a fresh session.",
            outcome_evidence=[failure.evidence] if failure.evidence else [],
        )
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
    failure = classify_run_artifact(artifact, error=error_text)
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


def _repo_from_state(state: Any) -> Path | None:
    value = getattr(state, "repo_path", None)
    return Path(value) if value else None


def _switch_kernel(state: Any, kernel: str) -> None:
    if getattr(state, "kernel", None) != kernel:
        state.kernel = kernel
        state.session_id = ""
        state.session_started = False
        if hasattr(state, "model"):
            state.model = None  # Provider-specific model names cannot cross a failover route.


def execute_kernel_turn_with_salvage(
    state: Any,
    prompt: str,
    turn_dir: Path,
    *,
    kernel_runner: Callable[..., Any],
    command_runner: Callable[..., Any] | None = None,
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

    def dispatch() -> Any:
        if state.kernel == LOCAL_KERNEL:
            local = invoke_local_kernel(
                state,
                prompt,
                turn_dir,
                action=local_action,
                now=now,
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
            turn_dir,
            command_runner=command_runner,
        )

    original = state.kernel
    rerouted = apply_health_reroute(original, store, installed, now=now)
    if rerouted != original:
        _switch_kernel(state, rerouted)

    tried: set[str] = set()
    released_sessions: set[str] = set()
    pending_fresh_session = False
    kernel_result = None
    salvaged = None
    from_kernel = original
    attempt = 0
    while True:
        attempt += 1
        try:
            kernel_result = dispatch()
            mark_kernel_success(store, state.kernel, now=now)
            persist()
            decision = TurnDecision.from_payload(extract_json_decision(kernel_result.last_message))
            if attempt == 1:
                meta = {"ok": True, "source": "kernel"}
                if rerouted != original:
                    meta.update({"rerouted_from": original, "health_reroute": True})
                return kernel_result, decision, with_probe_meta(meta)
            meta = salvaged.to_dict() if salvaged is not None else {}
            source = "fresh_session" if pending_fresh_session else "failover"
            meta.update(
                {
                    "ok": True,
                    "source": source,
                    "from_kernel": from_kernel,
                    "failover_kernel": "" if pending_fresh_session else state.kernel,
                    "released_session": pending_fresh_session,
                }
            )
            pending_fresh_session = False
            return kernel_result, decision, with_probe_meta(meta)
        except Exception as error:
            if kernel_result is not None:
                state.session_id = kernel_result.session_id or state.session_id
                state.session_started = bool(state.session_id) or state.session_started
            tried.add(state.kernel)
            artifact = load_kernel_run_artifact(turn_dir, kernel=state.kernel)
            if state.kernel == "cursor" and artifact.get("session_id"):
                state.session_id = str(artifact["session_id"])
                state.session_started = True
            salvaged = salvage_kernel_failure(
                error=error,
                current_kernel=state.kernel,
                last_message=kernel_result.last_message if kernel_result else "",
                artifact=artifact,
                installed_kernels=installed,
                health=store,
                now=now,
                allow_failover=True,
            )
            if (
                salvaged.class_id == SESSION_ALREADY_IN_USE
                and state.kernel not in released_sessions
            ):
                # One fresh launch per kernel. A second collision failsover.
                released_sessions.add(state.kernel)
                state.session_id = ""
                state.session_started = False
                pending_fresh_session = True
                continue
            pending_fresh_session = False
            if salvaged.class_id in FAILOVER_CLASSES:
                trip_kernel(store, state.kernel, salvaged.class_id, salvaged.evidence, now=now)
                persist()
            if salvaged.source == "message":
                decision = TurnDecision.from_payload(salvaged.decision)
                result = kernel_result or _synthetic_result(state, salvaged, None, KernelTurnResult)
                return result, decision, with_probe_meta(salvaged.to_dict())
            next_kernel = select_failover_kernel(
                state.kernel,
                installed,
                health=store,
                now=now,
                exclude=tried,
            )
            if not next_kernel:
                blocked = salvage_kernel_failure(
                    error=error,
                    current_kernel=state.kernel,
                    last_message=kernel_result.last_message if kernel_result else "",
                    artifact=artifact,
                    installed_kernels=installed,
                    health=store,
                    now=now,
                    allow_failover=False,
                )
                decision = TurnDecision.from_payload(blocked.decision)
                result = _synthetic_result(state, blocked, kernel_result, KernelTurnResult)
                return result, decision, with_probe_meta(blocked.to_dict())
            from_kernel = state.kernel
            _switch_kernel(state, next_kernel)


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
