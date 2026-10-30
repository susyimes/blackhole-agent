"""A Codex responses 404 must not be launched again.

The harvested 2026-09-03 run exited 1 after the CLI retried
``unexpected status 404 Not Found`` on ``backend-api/codex/responses`` for
both the websocket and the HTTPS fallback. A session id was present. That
death stayed a retryable CLI error, so the next resolution launched Codex
again.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_CODEX_404 = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": (
        '{"type":"thread.started","thread_id":"01a067d1-2173-7fb2-9cae-f3b9b80e0910"}\n'
        '{"type":"item.completed","item":{"id":"item_0","type":"error",'
        '"message":"Model metadata for `grok-4.6` not found. Defaulting to '
        'fallback metadata; this can degrade performance and cause issues."}}\n'
        '{"type":"turn.failed","error":{"message":"unexpected status 404 Not Found: '
        'Unknown error, url: https://chatgpt.com/backend-api/codex/responses, '
        'cf-ray: a355ad53ca7e456e-SJC"}}\n'
    ),
    "stderr_tail": (
        "2026-09-03T15:09:31.274859Z  WARN codex_core::client: falling back to HTTP\n"
        "2026-09-03T15:09:31.992880Z  WARN codex_core::responses_retry: stream "
        "disconnected - retrying sampling request (1/5 in 181ms)... "
        "sampling_error=unexpected status 404 Not Found: Unknown error, "
        "url: https://chatgpt.com/backend-api/codex/responses\n"
        "2026-09-03T15:09:43.171601Z ERROR codex_api::endpoint::responses_websocket: "
        "failed to connect to websocket: HTTP error: 404 Not Found, "
        "url: wss://chatgpt.com/backend-api/codex/responses\n"
    ),
    "last_message": "",
    "session_id": "01a067d1-2173-7fb2-9cae-f3b9b80e0910",
}
CODEX_ERROR = (
    "Codex CLI failed with exit code 1; result details were written to latest-codex-run.json."
)


def _continue_message(summary: str) -> str:
    return json.dumps(
        {
            "status": "continue",
            "summary": summary,
            "strategy": "continue",
            "next_step": "continue the mission",
            "capability_delta": "",
            "outcome_evidence": [],
            "validation": [],
            "done_when_met": False,
        }
    )


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import kernel_is_available, load_kernel_health
    from blackhole_agent.kernel_salvage import (
        classify_kernel_failure,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.unbound import KernelTurnResult

    missing = classify_run_artifact(HARVESTED_CODEX_404, error=CODEX_ERROR)
    bare_404 = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: upstream returned 404 Not Found for an unrelated asset",
        session_id="01a067d1-2173-7fb2-9cae-f3b9b80e0910",
        error=CODEX_ERROR,
    )
    session_404 = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "Failed to restore session from remote\n"
            "session get failed: 404 Not Found"
        ),
        error="Grok CLI failed with exit code 1",
    )
    metadata_warning = classify_kernel_failure(
        returncode=1,
        stdout_tail=(
            "Model metadata for `grok-4.6` not found. Defaulting to fallback metadata"
        ),
        error=CODEX_ERROR,
    )
    model_rejection = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "The 'grok-4.6' model is not supported when using Codex with a ChatGPT account"
        ),
        error=CODEX_ERROR,
    )
    calls: dict[str, list[str]] = {"first": [], "second": []}

    class _State:
        kernel = "codex"
        session_id = "01a067d1-2173-7fb2-9cae-f3b9b80e0910"
        session_started = True
        model = "grok-4.6"
        repo_path = ""

    def runner(bucket: str):
        def run(state, prompt, turn_dir, **kwargs):
            del prompt, kwargs
            calls[bucket].append(state.kernel)
            if state.kernel == "codex":
                kernel_dir = Path(turn_dir) / "kernel"
                kernel_dir.mkdir(parents=True, exist_ok=True)
                (kernel_dir / "latest-codex-run.json").write_text(
                    json.dumps(HARVESTED_CODEX_404),
                    encoding="utf-8",
                )
                raise RuntimeError(CODEX_ERROR)
            return KernelTurnResult(
                kernel=state.kernel,
                last_message=_continue_message(f"{state.kernel} continued"),
                session_id="peer-session",
                command=(state.kernel,),
                result_path="",
            )

        return run

    with tempfile.TemporaryDirectory(prefix="responses-endpoint-") as tmp:
        repo = Path(tmp)
        first = _State()
        first.repo_path = str(repo)
        _result, first_decision, first_meta = execute_kernel_turn_with_salvage(
            first,
            "prompt",
            repo / "turn-1",
            kernel_runner=runner("first"),
            installed_kernels={"codex", "grok"},
            probe_peers=False,
        )
        health = load_kernel_health(repo)
        breaker = health.kernels.get("codex")
        circuit_open = not kernel_is_available(health, "codex")
        circuit_class = breaker.class_id if breaker is not None else ""
        second = _State()
        second.repo_path = str(repo)
        _second_result, second_decision, second_meta = execute_kernel_turn_with_salvage(
            second,
            "prompt",
            repo / "turn-2",
            kernel_runner=runner("second"),
            installed_kernels={"codex", "grok"},
            probe_peers=False,
        )

    observed = {
        "missing_class": missing.class_id,
        "missing_retryable": missing.retryable,
        "bare_404_class": bare_404.class_id,
        "bare_404_retryable": bare_404.retryable,
        "session_404_class": session_404.class_id,
        "metadata_warning_class": metadata_warning.class_id,
        "model_rejection_class": model_rejection.class_id,
        "first_calls": calls["first"],
        "first_status": first_decision.status,
        "first_source": first_meta.get("source"),
        "first_class": first_meta.get("class_id"),
        "first_failover": first_meta.get("failover_kernel"),
        "first_kernel": first.kernel,
        "circuit_open": circuit_open,
        "circuit_class": circuit_class,
        "second_calls": calls["second"],
        "second_status": second_decision.status,
        "second_kernel": second.kernel,
        "second_rerouted_from": second_meta.get("rerouted_from"),
    }
    passed = bool(
        missing.class_id == "responses_endpoint_missing"
        and missing.retryable is False
        and bare_404.class_id == "cli_error"
        and bare_404.retryable is True
        and session_404.class_id == "session_not_found"
        and metadata_warning.class_id == "cli_error"
        and model_rejection.class_id == "model_unavailable"
        and calls["first"] == ["codex", "grok"]
        and first_decision.status == "continue"
        and first_meta.get("source") == "failover"
        and first_meta.get("class_id") == "responses_endpoint_missing"
        and first_meta.get("failover_kernel") == "grok"
        and first.kernel == "grok"
        and circuit_open is True
        and circuit_class == "responses_endpoint_missing"
        and calls["second"] == ["grok"]
        and "codex" not in calls["second"]
        and second_decision.status == "continue"
        and second.kernel == "grok"
        and second_meta.get("rerouted_from") == "codex"
    )
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcomes must still print JSON
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
