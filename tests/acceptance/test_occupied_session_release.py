"""An occupied Grok session must be released instead of retried or abandoned.

The harvested 2026-09-01 and 2026-09-03 Grok runs exited 1 because
``--session-id`` was already in use. Prints JSON with boolean passed and
nonempty observed. Exit 0 for both met and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

OCCUPIED_SESSION = "f187f002-4163-45d5-bb0b-affc94cd98b0"
HARVESTED_STDERR = (
    "Error: Error: Session ID f187f002-4163-45d5-bb0b-affc94cd98b0 is already in use.\n"
)
HARVESTED_GROK_SESSION = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": HARVESTED_STDERR,
    "last_message": "",
    "session_id": "",
}


def _launch_view(state) -> dict:
    """Read the real Grok launch plan when this src has one."""

    try:
        from blackhole_agent import unbound as unbound_mod
    except Exception as exc:  # noqa: BLE001 - baseline src must still print JSON
        unbound_mod = None
        planner_error = type(exc).__name__
    else:
        planner_error = ""
    planner = getattr(unbound_mod, "grok_launch_plan", None) if unbound_mod is not None else None
    if planner is None:
        started = bool(getattr(state, "session_started", False))
        return {
            "session_id": str(getattr(state, "session_id", "") or ""),
            "session_flag": "--resume" if started else "--session-id",
            "starting_session": not started,
            "planner": planner_error or "missing",
        }
    plan = dict(planner(state))
    plan["planner"] = "grok_launch_plan"
    return plan


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import kernel_is_available, load_kernel_health
    from blackhole_agent.kernel_salvage import (
        classify_kernel_failure,
        classify_run_artifact,
        execute_kernel_turn_with_salvage,
        salvage_kernel_failure,
    )
    from blackhole_agent.unbound import KernelTurnResult

    error = "Grok CLI failed with exit code 1; result details were written to latest-grok-run.json."
    failure = classify_run_artifact(HARVESTED_GROK_SESSION, error=error)
    salvaged = salvage_kernel_failure(
        error=error,
        current_kernel="grok",
        artifact=HARVESTED_GROK_SESSION,
        installed_kernels={"grok", "cursor"},
    )
    generic = classify_kernel_failure(
        returncode=1,
        stderr_tail="missing terminal result",
        error="Cursor CLI failed",
    )
    tls = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "stdout_tail": "",
            "stderr_tail": (
                "Error: [aborted] Client network socket disconnected before secure "
                "TLS connection was established\n\nmissing terminal result"
            ),
            "last_message": "",
            "session_id": "",
        },
        error="Cursor CLI failed",
    )
    calls: list[dict] = []

    class _State:
        kernel = "grok"
        session_id = OCCUPIED_SESSION
        session_started = False
        model = "grok-4.6"
        repo_path = ""

    def runner(state, prompt, turn_dir, **kwargs):
        del prompt, kwargs
        record = {
            "kernel": state.kernel,
            "session_id_before": str(state.session_id or ""),
            "session_started_before": bool(state.session_started),
        }
        if state.kernel == "grok":
            # Production sets session_started before the CLI returns, then
            # raises. Match that so a release has to clear a started session.
            if state.session_id == OCCUPIED_SESSION:
                plan = _launch_view(state)
                record.update(flag=plan.get("session_flag"), launched_session=plan.get("session_id"))
                state.session_started = True
                calls.append(record)
                kernel_dir = Path(turn_dir) / "kernel"
                kernel_dir.mkdir(parents=True, exist_ok=True)
                (kernel_dir / "latest-grok-run.json").write_text(
                    json.dumps(HARVESTED_GROK_SESSION),
                    encoding="utf-8",
                )
                raise RuntimeError(error)
            plan = _launch_view(state)
            record.update(flag=plan.get("session_flag"), launched_session=plan.get("session_id"))
            calls.append(record)
            return KernelTurnResult(
                kernel="grok",
                last_message=json.dumps(
                    {
                        "status": "continue",
                        "summary": "fresh grok session ran",
                        "strategy": "continue",
                        "next_step": "continue the mission",
                        "capability_delta": "",
                        "outcome_evidence": [],
                        "validation": [],
                        "done_when_met": False,
                    }
                ),
                session_id=str(state.session_id),
                command=("grok", plan.get("session_flag") or "", str(state.session_id)),
                result_path="",
            )
        calls.append(record)
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=json.dumps(
                {
                    "status": "continue",
                    "summary": "other kernel ran",
                    "strategy": "continue",
                    "next_step": "continue",
                    "capability_delta": "",
                    "outcome_evidence": [],
                    "validation": [],
                    "done_when_met": False,
                }
            ),
            session_id="other-kernel",
            command=(state.kernel,),
            result_path="",
        )

    with tempfile.TemporaryDirectory(prefix="occupied-session-") as tmp:
        repo = Path(tmp)
        state = _State()
        state.repo_path = str(repo)
        result, decision, meta = execute_kernel_turn_with_salvage(
            state,
            "prompt",
            repo / "turn",
            kernel_runner=runner,
            installed_kernels={"grok", "cursor"},
            probe_peers=False,
        )
        health = load_kernel_health(repo)
        grok_open = not kernel_is_available(health, "grok")

    fresh = calls[1] if len(calls) > 1 else {}
    observed = {
        "class_id": failure.class_id,
        "retryable": failure.retryable,
        "salvage_failover": salvaged.failover_kernel,
        "salvage_status": salvaged.decision.get("status"),
        "salvage_next_step": salvaged.decision.get("next_step"),
        "calls": calls,
        "execute_kernel": state.kernel,
        "execute_status": decision.status,
        "execute_source": meta.get("source"),
        "execute_failover": meta.get("failover_kernel"),
        "result_session_id": getattr(result, "session_id", ""),
        "grok_circuit_open": grok_open,
        "generic_cli_class": generic.class_id,
        "generic_cli_retryable": generic.retryable,
        "tls_class": tls.class_id,
        "fresh_flag": fresh.get("flag"),
        "fresh_session_before": fresh.get("session_id_before"),
        "fresh_started_before": fresh.get("session_started_before"),
        "fresh_launched_session": fresh.get("launched_session"),
    }
    launched = str(fresh.get("launched_session") or "")
    passed = bool(
        failure.class_id == "session_already_in_use"
        and failure.retryable is False
        and salvaged.failover_kernel == ""
        and salvaged.decision.get("status") == "continue"
        and "fresh session" in str(salvaged.decision.get("next_step") or "").lower()
        and len(calls) == 2
        and calls[0]["kernel"] == "grok"
        and calls[0]["session_id_before"] == OCCUPIED_SESSION
        and calls[0].get("flag") == "--session-id"
        and fresh.get("kernel") == "grok"
        and fresh.get("session_id_before") == ""
        and fresh.get("session_started_before") is False
        and fresh.get("flag") == "--session-id"
        and launched not in {"", OCCUPIED_SESSION}
        and state.kernel == "grok"
        and decision.status == "continue"
        and meta.get("source") == "fresh_session"
        and not meta.get("failover_kernel")
        and getattr(result, "session_id", "") == launched
        and grok_open is False
        and generic.class_id == "cli_error"
        and generic.retryable is True
        and tls.class_id == "pre_session_transport_abort"
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
