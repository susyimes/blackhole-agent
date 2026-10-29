"""A deleted Grok remote session must be dropped instead of resumed again.

The harvested 2026-08-13 runs exited 1 on --resume 5e8a33de-5b06-42a7-b238-d3106f402fb2
because the server no longer had that session. Stderr contained
"Failed to restore session from remote" and "session get failed: 404 Not Found".
That death stayed a retryable CLI error, so the turn left Grok.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

MISSING_SESSION = "5e8a33de-5b06-42a7-b238-d3106f402fb2"
HARVESTED_STDERR = (
    "2026-08-13T14:39:58.289697Z WARN auto worktree gc failed "
    "error=neither $GROK_HOME nor $HOME is set\n"
    'Session "5e8a33de-5b06-42a7-b238-d3106f402fb2" not found locally, '
    "restoring conversation from remote...\n"
    "Error: Failed to restore session from remote: fetching session record: "
    "session get failed: 404 Not Found\n"
)
HARVESTED_MISSING_SESSION = {
    "returncode": 1,
    "timed_out": False,
    "stdout_tail": "",
    "stderr_tail": HARVESTED_STDERR,
    "last_message": "",
    "session_id": "",
    "command": ["grok", "--resume", MISSING_SESSION, "--prompt-file", "task.md"],
}
GROK_ERROR = "Grok CLI failed with exit code 1; result details were written to latest-grok-run.json."
OCCUPIED_STDERR = (
    "Error: Error: Session ID f187f002-4163-45d5-bb0b-affc94cd98b0 is already in use.\n"
)


def _decision(summary: str) -> str:
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


def _launch_view(state) -> dict:
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


def _record(state) -> dict:
    # Snapshot before the planner. A missing session mints a new id in place.
    record = {
        "kernel": state.kernel,
        "session_id_before": str(getattr(state, "session_id", "") or ""),
        "session_started_before": bool(getattr(state, "session_started", False)),
    }
    plan = _launch_view(state) if state.kernel == "grok" else {}
    record["flag"] = plan.get("session_flag")
    record["launched_session"] = plan.get("session_id")
    return record


class _State:
    def __init__(self, repo: Path) -> None:
        self.kernel = "grok"
        self.session_id = MISSING_SESSION
        self.session_started = True
        self.model = "grok-4.7"
        self.repo_path = str(repo)
        self.decision_only_resume = False


def _run(repo: Path, runner) -> tuple:
    from blackhole_agent.kernel_health import kernel_is_available, load_kernel_health
    from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage

    state = _State(repo)
    result, decision, meta = execute_kernel_turn_with_salvage(
        state,
        "prompt",
        repo / "turn",
        kernel_runner=runner,
        installed_kernels={"grok", "cursor"},
        probe_peers=False,
    )
    health = load_kernel_health(repo)
    return state, result, decision, meta, not kernel_is_available(health, "grok")


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_salvage import classify_kernel_failure, classify_run_artifact, salvage_kernel_failure
    from blackhole_agent.unbound import KernelTurnResult

    failure = classify_run_artifact(HARVESTED_MISSING_SESSION, error=GROK_ERROR)
    salvaged = salvage_kernel_failure(
        error=GROK_ERROR,
        current_kernel="grok",
        artifact=HARVESTED_MISSING_SESSION,
        installed_kernels={"grok", "cursor"},
    )
    occupied = classify_kernel_failure(
        returncode=1,
        stderr_tail=OCCUPIED_STDERR,
        error=GROK_ERROR,
    )
    bare_404 = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: upstream returned 404 Not Found for an unrelated url",
        error=GROK_ERROR,
    )
    quoted = classify_kernel_failure(
        returncode=0,
        last_message=(
            "notes mention Failed to restore session from remote and "
            "session get failed: 404 Not Found as an example"
        ),
    )
    gc_only = classify_kernel_failure(
        returncode=1,
        stderr_tail="WARN auto worktree gc failed error=neither $GROK_HOME nor $HOME is set",
        session_id=MISSING_SESSION,
        error=GROK_ERROR,
    )

    fresh_calls: list[dict] = []

    def fresh_runner(state, prompt, turn_dir, **kwargs):
        del prompt, kwargs
        record = _record(state)
        fresh_calls.append(record)
        if state.kernel == "grok" and record["launched_session"] == MISSING_SESSION:
            state.session_started = True
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "latest-grok-run.json").write_text(
                json.dumps(HARVESTED_MISSING_SESSION),
                encoding="utf-8",
            )
            raise RuntimeError(GROK_ERROR)
        if state.kernel == "grok":
            state.session_started = True
            return KernelTurnResult(
                kernel="grok",
                last_message=_decision("fresh grok session ran"),
                session_id=str(state.session_id),
                command=("grok", record.get("flag") or "", str(state.session_id)),
                result_path="",
            )
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=_decision("other kernel ran"),
            session_id="other-kernel",
            command=(state.kernel,),
            result_path="",
        )

    second_calls: list[dict] = []

    def always_missing(state, prompt, turn_dir, **kwargs):
        del prompt, kwargs
        record = _record(state)
        second_calls.append(record)
        if state.kernel == "grok":
            state.session_started = True
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "latest-grok-run.json").write_text(
                json.dumps(HARVESTED_MISSING_SESSION),
                encoding="utf-8",
            )
            raise RuntimeError(GROK_ERROR)
        return KernelTurnResult(
            kernel=state.kernel,
            last_message=_decision("failover kernel ran"),
            session_id="other-kernel",
            command=(state.kernel,),
            result_path="",
        )

    with tempfile.TemporaryDirectory(prefix="missing-session-") as tmp:
        repo = Path(tmp)
        state, result, decision, meta, grok_open = _run(repo, fresh_runner)
        second_repo = repo / "second"
        second_repo.mkdir()
        second_state, _second_result, second_decision, second_meta, second_open = _run(
            second_repo, always_missing
        )

    fresh = fresh_calls[1] if len(fresh_calls) > 1 else {}
    launched = str(fresh.get("launched_session") or "")
    second_kernels = [item["kernel"] for item in second_calls]
    observed = {
        "class_id": failure.class_id,
        "retryable": failure.retryable,
        "salvage_failover": salvaged.failover_kernel,
        "salvage_status": salvaged.decision.get("status"),
        "salvage_next_step": salvaged.decision.get("next_step"),
        "calls": fresh_calls,
        "execute_kernel": state.kernel,
        "execute_status": decision.status,
        "execute_source": meta.get("source"),
        "execute_failover": meta.get("failover_kernel"),
        "result_session_id": getattr(result, "session_id", ""),
        "grok_circuit_open": grok_open,
        "fresh_flag": fresh.get("flag"),
        "fresh_session_before": fresh.get("session_id_before"),
        "fresh_started_before": fresh.get("session_started_before"),
        "fresh_launched_session": launched,
        "occupied_class": occupied.class_id,
        "bare_404_class": bare_404.class_id,
        "bare_404_retryable": bare_404.retryable,
        "quoted_class": quoted.class_id,
        "gc_only_class": gc_only.class_id,
        "second_kernels": second_kernels,
        "second_flags": [item.get("flag") for item in second_calls],
        "second_kernel": second_state.kernel,
        "second_status": second_decision.status,
        "second_source": second_meta.get("source"),
        "second_circuit_open": second_open,
    }
    first = fresh_calls[0] if fresh_calls else {}
    passed = bool(
        failure.class_id == "session_not_found"
        and failure.retryable is False
        and salvaged.failover_kernel == ""
        and salvaged.decision.get("status") == "continue"
        and "fresh session" in str(salvaged.decision.get("next_step") or "").lower()
        and len(fresh_calls) == 2
        and first.get("kernel") == "grok"
        and first.get("session_id_before") == MISSING_SESSION
        and first.get("session_started_before") is True
        and first.get("flag") == "--resume"
        and first.get("launched_session") == MISSING_SESSION
        and fresh.get("kernel") == "grok"
        and fresh.get("session_id_before") == ""
        and fresh.get("session_started_before") is False
        and fresh.get("flag") == "--session-id"
        and launched not in {"", MISSING_SESSION}
        and state.kernel == "grok"
        and decision.status == "continue"
        and meta.get("source") == "fresh_session"
        and not meta.get("failover_kernel")
        and getattr(result, "session_id", "") == launched
        and grok_open is False
        and occupied.class_id == "session_already_in_use"
        and bare_404.class_id == "cli_error"
        and bare_404.retryable is True
        and quoted.class_id != "session_not_found"
        and gc_only.class_id == "cli_error"
        and second_kernels == ["grok", "grok", "cursor"]
        and observed["second_flags"][:2] == ["--resume", "--session-id"]
        and second_state.kernel == "cursor"
        and second_decision.status == "continue"
        and second_meta.get("source") == "failover"
        and second_open is False
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
