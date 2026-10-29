"""A pre-session TLS abort must not be retried on the same kernel.

The harvested 2026-10-18 Cursor run exited 1 with an empty session because
the client socket disconnected before a secure TLS connection was established.
Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_STDERR = (
    "Error: [aborted] Client network socket disconnected before secure TLS "
    "connection was established\n\nmissing terminal result"
)
HARVESTED_CURSOR_TLS = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": HARVESTED_STDERR,
    "last_message": "",
    "session_id": "",
    "decision_final": False,
}


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

    error = "Cursor CLI failed (exit 1): " + HARVESTED_STDERR
    failure = classify_run_artifact(HARVESTED_CURSOR_TLS, error=error)
    salvaged = salvage_kernel_failure(
        error=error,
        current_kernel="cursor",
        artifact=HARVESTED_CURSOR_TLS,
        installed_kernels={"grok", "cursor"},
    )
    generic = classify_kernel_failure(
        returncode=1,
        stderr_tail="missing terminal result",
        error="Cursor CLI failed",
    )
    timeout = classify_kernel_failure(timed_out=True, error="Timed out after 30 seconds.")
    established = classify_run_artifact(
        {**HARVESTED_CURSOR_TLS, "session_id": "already-open"},
        error=error,
    )

    calls: list[str] = []

    class _State:
        kernel = "cursor"
        session_id = ""
        session_started = False
        model = "grok-4.7-xhigh"
        repo_path = ""

    def runner(state, prompt, turn_dir, **kwargs):
        del prompt, kwargs
        calls.append(state.kernel)
        if state.kernel == "cursor":
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "latest-cursor-run.json").write_text(
                json.dumps(HARVESTED_CURSOR_TLS),
                encoding="utf-8",
            )
            raise RuntimeError(error)
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=json.dumps(
                {
                    "status": "continue",
                    "summary": "peer kernel ran",
                    "strategy": "continue",
                    "next_step": "choose a mission",
                    "capability_delta": "",
                    "outcome_evidence": [],
                    "validation": [],
                    "done_when_met": False,
                }
            ),
            session_id="peer-session",
            command=("grok",),
            result_path="",
        )

    with tempfile.TemporaryDirectory(prefix="pre-session-abort-") as tmp:
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

    observed = {
        "class_id": failure.class_id,
        "retryable": failure.retryable,
        "salvage_failover": salvaged.failover_kernel,
        "salvage_status": salvaged.decision.get("status"),
        "salvage_next_step": salvaged.decision.get("next_step"),
        "generic_cli_class": generic.class_id,
        "generic_cli_retryable": generic.retryable,
        "timeout_class": timeout.class_id,
        "timeout_retryable": timeout.retryable,
        "established_session_class": established.class_id,
        "calls": calls,
        "execute_kernel": state.kernel,
        "execute_status": decision.status,
        "execute_source": meta.get("source"),
        "cursor_circuit_open": cursor_open,
        "next_resolution": reroute,
    }
    passed = bool(
        failure.class_id == "pre_session_transport_abort"
        and failure.retryable is False
        and salvaged.failover_kernel == "grok"
        and salvaged.decision.get("status") == "continue"
        and "grok" in str(salvaged.decision.get("next_step") or "").lower()
        and generic.class_id == "cli_error"
        and generic.retryable is True
        and timeout.class_id == "timeout"
        and timeout.retryable is True
        and established.class_id != "pre_session_transport_abort"
        and calls == ["cursor", "grok"]
        and state.kernel == "grok"
        and decision.status == "continue"
        and meta.get("source") == "failover"
        and cursor_open is True
        and reroute == "grok"
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet baseline must still print JSON
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
