"""A spent account must open the quota circuit instead of launching again.

Harvested Grok runs (2026-07-29) exited 1 with HTTP 403
personal-team-blocked:spending-limit ("run out of credits"). Harvested Kimi
runs exited 1 with a billing-cycle usage limit labeled auth_error. Neither
shape is HTTP 402, so both stayed a retryable CLI error and the next turn
launched the same kernel. Prints JSON with boolean passed and nonempty
observed. Exit 0 for both met and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_GROK_403 = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": (
        '{"type":"error","message":"Internal error: {\\n  \\"message\\": '
        '\\"API error (status 403 Forbidden): personal-team-blocked:spending-limit: '
        'You have run out of credits or need a Grok subscription.\\",\\n  '
        '\\"http_status\\": 403\\n}"}\\n'
    ),
    "stderr_tail": (
        "ERROR responses API error status=403 Forbidden "
        "error_message=personal-team-blocked:spending-limit: "
        "You have run out of credits or need a Grok subscription.\n"
    ),
    "last_message": "",
    "session_id": "",
}
HARVESTED_KIMI_USAGE = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": (
        "error: failed to run prompt: provider.auth_error: 403 "
        "You've reached your usage limit for this billing cycle. "
        "Your quota will be refreshed in the next cycle.\n"
    ),
    "last_message": "",
    "session_id": "",
}
GROK_ERROR = (
    "Grok CLI failed with exit code 1; result details were written to latest-grok-run.json."
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
        HARVESTED_GROK_402,
        classify_kernel_failure,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
    )
    from blackhole_agent.unbound import KernelTurnResult

    spending = classify_run_artifact(HARVESTED_GROK_403, error=GROK_ERROR)
    kimi = classify_run_artifact(
        HARVESTED_KIMI_USAGE,
        error="Kimi CLI failed with exit code 1; result details were written to latest-kimi-run.json.",
    )
    payment = classify_run_artifact(HARVESTED_GROK_402, error="Grok CLI failed with exit code 1")
    bare_forbidden = classify_kernel_failure(
        returncode=1,
        stderr_tail="HTTP 403 Forbidden",
        error="request failed",
    )
    calls: dict[str, list[str]] = {"first": [], "second": []}

    class _State:
        kernel = "grok"
        session_id = "76b1625d-e8bc-43ed-9055-b29f9be54128"
        session_started = True
        model = "grok-4.5"
        repo_path = ""

    def runner(bucket: str):
        def run(state, prompt, turn_dir, **kwargs):
            del prompt, kwargs
            calls[bucket].append(state.kernel)
            if state.kernel == "grok":
                kernel_dir = Path(turn_dir) / "kernel"
                kernel_dir.mkdir(parents=True, exist_ok=True)
                (kernel_dir / "latest-grok-run.json").write_text(
                    json.dumps(HARVESTED_GROK_403),
                    encoding="utf-8",
                )
                raise RuntimeError(GROK_ERROR)
            return KernelTurnResult(
                kernel=state.kernel,
                last_message=_continue_message(f"{state.kernel} continued"),
                session_id="peer-session",
                command=(state.kernel,),
                result_path="",
            )

        return run

    with tempfile.TemporaryDirectory(prefix="spending-limit-") as tmp:
        repo = Path(tmp)
        first = _State()
        first.repo_path = str(repo)
        _result, first_decision, first_meta = execute_kernel_turn_with_salvage(
            first,
            "prompt",
            repo / "turn-1",
            kernel_runner=runner("first"),
            installed_kernels={"grok", "cursor"},
            probe_peers=False,
        )
        health = load_kernel_health(repo)
        breaker = health.kernels.get("grok")
        circuit_open = not kernel_is_available(health, "grok")
        circuit_class = breaker.class_id if breaker is not None else ""
        second = _State()
        second.repo_path = str(repo)
        _second_result, second_decision, second_meta = execute_kernel_turn_with_salvage(
            second,
            "prompt",
            repo / "turn-2",
            kernel_runner=runner("second"),
            installed_kernels={"grok", "cursor"},
            probe_peers=False,
        )

    observed = {
        "spending_class": spending.class_id,
        "spending_retryable": spending.retryable,
        "kimi_class": kimi.class_id,
        "kimi_retryable": kimi.retryable,
        "payment_402_class": payment.class_id,
        "bare_403_class": bare_forbidden.class_id,
        "bare_403_retryable": bare_forbidden.retryable,
        "first_calls": calls["first"],
        "first_status": first_decision.status,
        "first_source": first_meta.get("source"),
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
        spending.class_id == "quota_exhausted"
        and spending.retryable is False
        and kimi.class_id == "quota_exhausted"
        and kimi.retryable is False
        and payment.class_id == "quota_exhausted"
        and bare_forbidden.class_id == "cli_error"
        and bare_forbidden.retryable is True
        and calls["first"] == ["grok", "cursor"]
        and first_decision.status == "continue"
        and first_meta.get("source") == "failover"
        and first_meta.get("failover_kernel") == "cursor"
        and first.kernel == "cursor"
        and circuit_open is True
        and circuit_class == "quota_exhausted"
        and calls["second"] == ["cursor"]
        and "grok" not in calls["second"]
        and second_decision.status == "continue"
        and second.kernel == "cursor"
        and second_meta.get("rerouted_from") == "grok"
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
