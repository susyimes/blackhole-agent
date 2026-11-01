"""A Grok CLI that exits unsigned must not be launched again.

Harvested runs (2026-08-13) exited 1 with "Not signed in. Run `grok login`"
after "No auth credentials for cli-chat-proxy". That death stayed a retryable
CLI error, so the next resolution launched Grok again.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

HARVESTED_GROK_SIGNED_OUT = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": (
        '{"type":"error","message":"Not signed in. Run `grok login` to authenticate '
        '(or `grok login --device-code` if no browser is available)."}\n'
    ),
    "stderr_tail": (
        "WARN config: ignored unrecognized or invalid entry path=privacy field=(entry)\n"
        "WARN Failed to fetch models: Auth(\"No auth credentials for cli-chat-proxy\")\n"
        "WARN model refresh failed, leaving existing models unchanged\n"
        "Error: Not signed in. Run `grok login` to authenticate "
        "(or `grok login --device-code` if no browser is available).\n"
    ),
    "last_message": "",
    "session_id": "",
}
GROK_ERROR = "Grok CLI failed with exit code 1; result details were written to latest-grok-run.json."


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
    from blackhole_agent.kernel_salvage import classify_kernel_failure, classify_run_artifact, execute_kernel_turn_with_salvage
    from blackhole_agent.unbound import KernelTurnResult

    signed_out = classify_run_artifact(HARVESTED_GROK_SIGNED_OUT, error=GROK_ERROR)
    credential_warning = classify_kernel_failure(
        returncode=1,
        stderr_tail='WARN Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")',
        error=GROK_ERROR,
    )
    zero_exit = classify_kernel_failure(
        returncode=0,
        stderr_tail='WARN Failed to fetch models: Auth("No auth credentials for cli-chat-proxy")',
        last_message="finished",
    )
    calls: dict[str, list[str]] = {"first": [], "second": []}

    class _State:
        kernel = "grok"
        session_id = ""
        session_started = False
        model = "grok-4.6"
        repo_path = ""

    def runner(bucket: str):
        def run(state, prompt, turn_dir, **kwargs):
            del prompt, kwargs
            calls[bucket].append(state.kernel)
            if state.kernel == "grok":
                kernel_dir = Path(turn_dir) / "kernel"
                kernel_dir.mkdir(parents=True, exist_ok=True)
                (kernel_dir / "latest-grok-run.json").write_text(
                    json.dumps(HARVESTED_GROK_SIGNED_OUT),
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

    with tempfile.TemporaryDirectory(prefix="grok-signed-out-") as tmp:
        repo = Path(tmp)
        first = _State()
        first.repo_path = str(repo)
        _result, first_decision, first_meta = execute_kernel_turn_with_salvage(
            first,
            "prompt",
            repo / "turn-1",
            kernel_runner=runner("first"),
            installed_kernels={"grok", "codex"},
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
            installed_kernels={"grok", "codex"},
            probe_peers=False,
        )

    observed = {
        "signed_out_class": signed_out.class_id,
        "signed_out_retryable": signed_out.retryable,
        "credential_warning_class": credential_warning.class_id,
        "credential_warning_retryable": credential_warning.retryable,
        "zero_exit_warning_class": zero_exit.class_id,
        "zero_exit_warning_retryable": zero_exit.retryable,
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
        signed_out.class_id == "auth_failed"
        and signed_out.retryable is False
        and credential_warning.class_id == "cli_error"
        and credential_warning.retryable is True
        and zero_exit.class_id != "auth_failed"
        and zero_exit.retryable is True
        and calls["first"] == ["grok", "codex"]
        and first_decision.status == "continue"
        and first_meta.get("source") == "failover"
        and first_meta.get("class_id") == "auth_failed"
        and first_meta.get("failover_kernel") == "codex"
        and first.kernel == "codex"
        and circuit_open is True
        and circuit_class == "auth_failed"
        and calls["second"] == ["codex"]
        and "grok" not in calls["second"]
        and second_decision.status == "continue"
        and second.kernel == "codex"
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
