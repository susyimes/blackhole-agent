"""A Kimi kernel that dies on provider HTTP 429 must not be launched again.

The harvested 2026-08-02 run exited 1 with provider.rate_limit after the CLI
had already retried "The engine is currently overloaded, please try again
later". A session id was present. That death stayed a retryable CLI error, so
the next resolution launched Kimi again.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_KIMI_429 = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": (
        '{"role":"meta","type":"turn.step.retrying","failed_attempt":1,'
        '"next_attempt":2,"max_attempts":3,"error_name":"APIProviderRateLimitError",'
        '"error_message":"429 The engine is currently overloaded, please try again later",'
        '"status_code":429}\n'
    ),
    "stderr_tail": (
        "error: failed to run prompt: provider.rate_limit: 429 "
        "The engine is currently overloaded, please try again later\n"
        "See log: C:/Users/svmes/.kimi-code/logs/kimi-code.log\n"
    ),
    "last_message": "",
    "session_id": "session_101821fc-f52d-4822-ba75-9729754be536",
}
KIMI_ERROR = (
    "Kimi CLI failed with exit code 1; result details were written to latest-kimi-run.json."
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

    overload = classify_run_artifact(HARVESTED_KIMI_429, error=KIMI_ERROR)
    bare_429 = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: status_code=429 left in an unrelated log line",
        session_id="session_101821fc-f52d-4822-ba75-9729754be536",
        error=KIMI_ERROR,
    )
    spending = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "status=403 Forbidden error_message=personal-team-blocked:spending-limit: "
            "You have run out of credits"
        ),
        error="Grok CLI failed with exit code 1",
    )
    token_fetch = classify_kernel_failure(
        returncode=1,
        stderr_tail=(
            "provider.connection_error: OAuth provider "
            '"managed:kimi-code" failed to fetch an access token'
        ),
        session_id="session_fb6168fb-ca57-4fa5-851f-16f00d85139b",
        error=KIMI_ERROR,
    )
    calls: dict[str, list[str]] = {"first": [], "second": []}

    class _State:
        kernel = "kimi"
        session_id = "session_101821fc-f52d-4822-ba75-9729754be536"
        session_started = True
        model = "kimi"
        repo_path = ""

    def runner(bucket: str):
        def run(state, prompt, turn_dir, **kwargs):
            del prompt, kwargs
            calls[bucket].append(state.kernel)
            if state.kernel == "kimi":
                kernel_dir = Path(turn_dir) / "kernel"
                kernel_dir.mkdir(parents=True, exist_ok=True)
                (kernel_dir / "latest-kimi-run.json").write_text(
                    json.dumps(HARVESTED_KIMI_429),
                    encoding="utf-8",
                )
                raise RuntimeError(KIMI_ERROR)
            return KernelTurnResult(
                kernel=state.kernel,
                last_message=_continue_message(f"{state.kernel} continued"),
                session_id="peer-session",
                command=(state.kernel,),
                result_path="",
            )

        return run

    with tempfile.TemporaryDirectory(prefix="provider-overloaded-") as tmp:
        repo = Path(tmp)
        first = _State()
        first.repo_path = str(repo)
        _result, first_decision, first_meta = execute_kernel_turn_with_salvage(
            first,
            "prompt",
            repo / "turn-1",
            kernel_runner=runner("first"),
            installed_kernels={"kimi", "codex"},
            probe_peers=False,
        )
        health = load_kernel_health(repo)
        breaker = health.kernels.get("kimi")
        circuit_open = not kernel_is_available(health, "kimi")
        circuit_class = breaker.class_id if breaker is not None else ""
        second = _State()
        second.repo_path = str(repo)
        _second_result, second_decision, second_meta = execute_kernel_turn_with_salvage(
            second,
            "prompt",
            repo / "turn-2",
            kernel_runner=runner("second"),
            installed_kernels={"kimi", "codex"},
            probe_peers=False,
        )

    observed = {
        "overload_class": overload.class_id,
        "overload_retryable": overload.retryable,
        "bare_429_class": bare_429.class_id,
        "bare_429_retryable": bare_429.retryable,
        "spending_class": spending.class_id,
        "token_fetch_class": token_fetch.class_id,
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
        overload.class_id == "provider_overloaded"
        and overload.retryable is False
        and bare_429.class_id == "cli_error"
        and bare_429.retryable is True
        and spending.class_id == "quota_exhausted"
        and token_fetch.class_id == "auth_failed"
        and calls["first"] == ["kimi", "codex"]
        and first_decision.status == "continue"
        and first_meta.get("source") == "failover"
        and first_meta.get("class_id") == "provider_overloaded"
        and first_meta.get("failover_kernel") == "codex"
        and first.kernel == "codex"
        and circuit_open is True
        and circuit_class == "provider_overloaded"
        and calls["second"] == ["codex"]
        and "kimi" not in calls["second"]
        and second_decision.status == "continue"
        and second.kernel == "codex"
        and second_meta.get("rerouted_from") == "kimi"
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
