"""A rejected model must not be retried on the same kernel.

The harvested 2026-10-15 Cursor run exited 1 because grok-4.7-xhigh was not
an available model. The harvested 2026-09-04 Kimi run exited 1 because
grok-4.6 was not configured. Both used to stay a retryable CLI error, so the
next resolution launched the same kernel with the same model.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_CURSOR_STDERR = (
    "Cannot use this model: grok-4.7-xhigh. Available models: \n\n"
    "missing terminal result"
)
HARVESTED_CURSOR_MODEL = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": HARVESTED_CURSOR_STDERR,
    "last_message": "",
    "session_id": "",
    "decision_final": False,
}
HARVESTED_KIMI_STDERR = (
    'error: failed to run prompt: Model "grok-4.6" is not configured in config.toml.\n'
    "See log: C:/Users/svmes/.kimi-code/logs/kimi-code.log\n"
)
HARVESTED_KIMI_MODEL = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": HARVESTED_KIMI_STDERR,
    "last_message": "",
    "session_id": "",
}
CODEX_UNKNOWN_MODEL_WARNING = (
    "WARN codex_models_manager::model_info: Unknown model grok-4.6 is used. "
    "This will use fallback model metadata."
)


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import (
        apply_health_reroute,
        kernel_is_available,
        load_kernel_health,
    )
    from blackhole_agent.kernel_salvage import (
        classify_kernel_failure,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
        salvage_kernel_failure,
    )
    from blackhole_agent.unbound import KernelTurnResult

    cursor_error = "Cursor CLI failed (exit 1): " + HARVESTED_CURSOR_STDERR
    kimi_error = "Kimi CLI failed (exit 1): " + HARVESTED_KIMI_STDERR
    cursor_failure = classify_run_artifact(HARVESTED_CURSOR_MODEL, error=cursor_error)
    kimi_failure = classify_run_artifact(HARVESTED_KIMI_MODEL, error=kimi_error)
    cursor_salvage = salvage_kernel_failure(
        error=cursor_error,
        current_kernel="cursor",
        artifact=HARVESTED_CURSOR_MODEL,
        installed_kernels={"grok", "cursor"},
    )
    kimi_salvage = salvage_kernel_failure(
        error=kimi_error,
        current_kernel="kimi",
        artifact=HARVESTED_KIMI_MODEL,
        installed_kernels={"grok", "kimi"},
    )
    warning = classify_kernel_failure(
        returncode=1,
        stderr_tail=CODEX_UNKNOWN_MODEL_WARNING,
        error="Codex CLI failed with exit code 1",
    )
    missing_terminal = classify_kernel_failure(
        returncode=1,
        stderr_tail="missing terminal result",
        error="Cursor CLI failed",
    )
    timeout = classify_kernel_failure(timed_out=True, error="Timed out after 30 seconds.")
    spending = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "status=403 Forbidden error_message=personal-team-blocked:spending-limit: "
            "You have run out of credits"
        ),
        error="Grok CLI failed with exit code 1",
    )
    quoted = classify_kernel_failure(
        returncode=0,
        stderr_tail=HARVESTED_CURSOR_STDERR,
        last_message='{"status":"continue","summary":"quoted a model rejection"}',
    )

    calls: list[dict[str, str | None]] = []

    class _State:
        kernel = "cursor"
        session_id = ""
        session_started = False
        model: str | None = "grok-4.7-xhigh"
        repo_path = ""

    def runner(state, prompt, turn_dir, **kwargs):
        del prompt, kwargs
        calls.append({"kernel": state.kernel, "model": state.model})
        if state.kernel == "cursor":
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "latest-cursor-run.json").write_text(
                json.dumps(HARVESTED_CURSOR_MODEL),
                encoding="utf-8",
            )
            raise RuntimeError(cursor_error)
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=json.dumps(
                {
                    "status": "continue",
                    "summary": "peer kernel ran without the rejected model",
                    "strategy": "continue",
                    "next_step": "choose a mission",
                    "capability_delta": "",
                    "outcome_evidence": [],
                    "validation": [],
                    "done_when_met": False,
                }
            ),
            session_id="peer-session",
            command=(state.kernel,),
            result_path="",
        )

    with tempfile.TemporaryDirectory(prefix="model-unavailable-") as tmp:
        repo = Path(tmp)
        state = _State()
        state.repo_path = str(repo)
        _result, decision, meta = execute_kernel_turn_with_salvage(
            state,
            "prompt",
            repo / "turn",
            kernel_runner=runner,
            installed_kernels={"grok", "cursor"},
            probe_peers=False,
        )
        health = load_kernel_health(repo)
        reroute = apply_health_reroute("cursor", health, installed={"grok", "cursor"})
        cursor_open = not kernel_is_available(health, "cursor")
        breaker = health.kernels.get("cursor")
        cursor_class = breaker.class_id if breaker is not None else ""

    observed = {
        "cursor_class": cursor_failure.class_id,
        "cursor_retryable": cursor_failure.retryable,
        "kimi_class": kimi_failure.class_id,
        "kimi_retryable": kimi_failure.retryable,
        "cursor_salvage_failover": cursor_salvage.failover_kernel,
        "cursor_salvage_status": cursor_salvage.decision.get("status"),
        "cursor_salvage_next_step": cursor_salvage.decision.get("next_step"),
        "kimi_salvage_failover": kimi_salvage.failover_kernel,
        "kimi_salvage_next_step": kimi_salvage.decision.get("next_step"),
        "warning_class": warning.class_id,
        "warning_retryable": warning.retryable,
        "missing_terminal_class": missing_terminal.class_id,
        "timeout_class": timeout.class_id,
        "timeout_retryable": timeout.retryable,
        "spending_class": spending.class_id,
        "quoted_class": quoted.class_id,
        "calls": calls,
        "execute_kernel": state.kernel,
        "execute_model": state.model,
        "execute_status": decision.status,
        "execute_source": meta.get("source"),
        "cursor_circuit_open": cursor_open,
        "cursor_circuit_class": cursor_class,
        "next_resolution": reroute,
    }
    passed = bool(
        cursor_failure.class_id == "model_unavailable"
        and cursor_failure.retryable is False
        and kimi_failure.class_id == "model_unavailable"
        and kimi_failure.retryable is False
        and cursor_salvage.failover_kernel == "grok"
        and cursor_salvage.decision.get("status") == "continue"
        and "grok" in str(cursor_salvage.decision.get("next_step") or "").lower()
        and kimi_salvage.failover_kernel == "grok"
        and "grok" in str(kimi_salvage.decision.get("next_step") or "").lower()
        and warning.class_id == "cli_error"
        and warning.retryable is True
        and missing_terminal.class_id == "cli_error"
        and timeout.class_id == "timeout"
        and timeout.retryable is True
        and spending.class_id == "quota_exhausted"
        and quoted.class_id != "model_unavailable"
        and calls == [
            {"kernel": "cursor", "model": "grok-4.7-xhigh"},
            {"kernel": "grok", "model": None},
        ]
        and state.kernel == "grok"
        and state.model is None
        and decision.status == "continue"
        and meta.get("source") == "failover"
        and cursor_open is True
        and cursor_class == "model_unavailable"
        and reroute == "grok"
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet baseline must still print JSON
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    if not observed:
        observed = {"error": "empty"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
