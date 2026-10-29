"""A Codex ChatGPT-account model rejection must not relaunch that kernel.

Harvested Codex runs from 2026-08-24 through 2026-09-06 exited 1 with
``The 'grok-4.6' model is not supported when using Codex with a ChatGPT
account``. That stayed a retryable CLI error, so the next resolution
launched Codex again with the same model. An unknown-model fallback warning
is not this rejection.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_REJECTION = (
    "The 'grok-4.6' model is not supported when using Codex with a ChatGPT account."
)
HARVESTED_STDOUT = (
    '{"type":"turn.failed","error":{"message":"{\\"type\\":\\"error\\",\\"status\\":400,'
    '\\"error\\":{\\"type\\":\\"invalid_request_error\\",\\"message\\":\\"'
    + HARVESTED_REJECTION
    + '\\"}}"}}'
)
UNKNOWN_MODEL_WARNING = (
    "WARN codex_models_manager::model_info: Unknown model grok-4.6 is used. "
    "This will use fallback model metadata."
)
HARVESTED_CODEX = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": HARVESTED_STDOUT,
    "stderr_tail": UNKNOWN_MODEL_WARNING + "\n" + HARVESTED_REJECTION + "\n",
    "last_message": "",
    "session_id": "",
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

    error = "Codex CLI failed with exit code 1: " + HARVESTED_REJECTION
    failure = classify_run_artifact(HARVESTED_CODEX, error=error)
    salvaged = salvage_kernel_failure(
        error=error,
        current_kernel="codex",
        artifact=HARVESTED_CODEX,
        installed_kernels={"codex", "grok"},
    )
    warning = classify_kernel_failure(
        returncode=1,
        stderr_tail=UNKNOWN_MODEL_WARNING,
        error="Codex CLI failed with exit code 1",
    )
    unrelated = classify_kernel_failure(
        returncode=1,
        stderr_tail="this feature is not supported on this host",
        error="Codex CLI failed with exit code 1",
    )
    quoted = classify_kernel_failure(
        returncode=0,
        stdout_tail=HARVESTED_STDOUT,
        stderr_tail=HARVESTED_REJECTION,
        last_message='{"status":"continue","summary":"quoted the rejection"}',
    )

    calls: list[dict[str, str | None]] = []

    class _State:
        kernel = "codex"
        session_id = ""
        session_started = False
        model: str | None = "grok-4.6"
        repo_path = ""

    def runner(state, prompt, turn_dir, **kwargs):
        del prompt, kwargs
        calls.append({"kernel": state.kernel, "model": state.model})
        if state.kernel == "codex":
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "latest-codex-run.json").write_text(
                json.dumps(HARVESTED_CODEX),
                encoding="utf-8",
            )
            raise RuntimeError(error)
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

    with tempfile.TemporaryDirectory(prefix="codex-account-model-") as tmp:
        repo = Path(tmp)
        state = _State()
        state.repo_path = str(repo)
        _result, decision, meta = execute_kernel_turn_with_salvage(
            state,
            "prompt",
            repo / "turn",
            kernel_runner=runner,
            installed_kernels={"codex", "grok"},
            probe_peers=False,
        )
        health = load_kernel_health(repo)
        reroute = apply_health_reroute("codex", health, installed={"codex", "grok"})
        codex_open = not kernel_is_available(health, "codex")
        breaker = health.kernels.get("codex")
        circuit_class = breaker.class_id if breaker is not None else ""

    observed = {
        "failure_class": failure.class_id,
        "failure_retryable": failure.retryable,
        "salvage_failover": salvaged.failover_kernel,
        "salvage_status": salvaged.decision.get("status"),
        "salvage_next_step": salvaged.decision.get("next_step"),
        "warning_class": warning.class_id,
        "warning_retryable": warning.retryable,
        "unrelated_class": unrelated.class_id,
        "quoted_class": quoted.class_id,
        "calls": calls,
        "execute_kernel": state.kernel,
        "execute_model": state.model,
        "execute_status": decision.status,
        "execute_source": meta.get("source"),
        "codex_circuit_open": codex_open,
        "codex_circuit_class": circuit_class,
        "next_resolution": reroute,
    }
    passed = bool(
        failure.class_id == "model_unavailable"
        and failure.retryable is False
        and salvaged.failover_kernel == "grok"
        and salvaged.decision.get("status") == "continue"
        and "grok" in str(salvaged.decision.get("next_step") or "").lower()
        and warning.class_id == "cli_error"
        and warning.retryable is True
        and unrelated.class_id == "cli_error"
        and quoted.class_id != "model_unavailable"
        and calls == [
            {"kernel": "codex", "model": "grok-4.6"},
            {"kernel": "grok", "model": None},
        ]
        and state.kernel == "grok"
        and state.model is None
        and decision.status == "continue"
        and meta.get("source") == "failover"
        and codex_open is True
        and circuit_class == "model_unavailable"
        and reroute == "grok"
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
