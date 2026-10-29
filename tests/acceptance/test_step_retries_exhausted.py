"""A Cursor step runner that already exhausted its retries must keep its session.

The harvested 2026-09-11 run exited 1 with ``RetriableError: [internal] Failed
to run step, exceeded max retries`` and ``missing terminal result`` while
session ``0d6e78f5-c0d9-48b4-949c-afa016be23ab`` was present. That death stayed
a retryable CLI error, so the turn left Cursor and replayed the mission.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

SESSION = "0d6e78f5-c0d9-48b4-949c-afa016be23ab"
MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed on the first step exhaustion."
HARVESTED_STEP = {
    "returncode": 1,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": (
        "RetriableError: [internal] Failed to run step, exceeded max retries\n"
        "Error: command failed unexpectedly.\n\n"
        "missing terminal result"
    ),
    "session_id": SESSION,
    "decision_final": False,
}
GENERIC_MISSING = {
    "returncode": 1,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": "missing terminal result",
    "session_id": SESSION,
    "decision_final": False,
}
CURSOR_ERROR = "Cursor CLI failed (exit 1): missing terminal result"


def _decision(summary: str) -> str:
    return json.dumps(
        {
            "status": "continue",
            "summary": summary,
            "strategy": "continue",
            "next_step": "continue the mission",
            "capability_delta": "",
            "outcome_evidence": ["resumed"],
            "validation": [],
            "done_when_met": False,
        }
    )


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import kernel_is_available, load_kernel_health
    from blackhole_agent.kernel_salvage import classify_kernel_failure, classify_run_artifact
    from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage
    from blackhole_agent.unbound import KernelTurnResult, UnboundMission

    harvested = classify_run_artifact(HARVESTED_STEP, error=CURSOR_ERROR)
    bare_missing = classify_kernel_failure(
        returncode=1,
        stderr_tail="missing terminal result",
        session_id=SESSION,
        error=CURSOR_ERROR,
    )
    bare_retries = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: exceeded max retries while polling",
        session_id=SESSION,
        error=CURSOR_ERROR,
    )
    quoted_success = classify_kernel_failure(
        returncode=0,
        last_message=(
            "notes mention RetriableError Failed to run step, exceeded max retries "
            "as an example"
        ),
    )

    def mission(repo: Path) -> UnboundMission:
        return UnboundMission(
            schema_version=1,
            mission_id="step-retry-probe",
            created_at="2026-09-11T05:04:49Z",
            updated_at="2026-09-11T05:04:49Z",
            repo_path=str(repo),
            workspace_path=str(repo),
            branch="probe",
            target_branch="main",
            goal="Finish the interrupted Cursor session.",
            done_when="The session emits a JSON decision.",
            stage="execution",
            kernel="cursor",
            session_id="",
            session_started=False,
        )

    def runner(calls: list[dict[str, str]], *, artifact: dict, succeed_on_short: bool):
        def run(state, prompt, turn_dir, **kwargs):
            del kwargs
            text = str(prompt)
            calls.append(
                {
                    "kernel": str(state.kernel),
                    "session": str(getattr(state, "session_id", "") or ""),
                    "started": str(bool(getattr(state, "session_started", False))),
                    "full": str(MARKER in text),
                    "continuation": str("internal retries" in text),
                }
            )
            if state.kernel != "cursor":
                return KernelTurnResult(
                    kernel=str(state.kernel),
                    last_message=_decision("other kernel"),
                    session_id="",
                    command=(str(state.kernel),),
                    result_path="",
                )
            short = MARKER not in text
            if succeed_on_short and short:
                return KernelTurnResult(
                    kernel="cursor",
                    last_message=_decision("continued"),
                    session_id=str(getattr(state, "session_id", "") or SESSION),
                    command=("cursor", "--resume", SESSION),
                    result_path="",
                )
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "latest-cursor-run.json").write_text(
                json.dumps(artifact),
                encoding="utf-8",
            )
            raise RuntimeError(CURSOR_ERROR)

        return run

    def local_action(state, workspace):
        del state, workspace
        return {"status": "continue", "summary": "local tick"}

    with tempfile.TemporaryDirectory(prefix="step-retry-") as tmp:
        repo = Path(tmp)
        resumed_calls: list[dict[str, str]] = []
        resumed_state = mission(repo)
        _resumed_result, resumed_decision, resumed_meta = execute_kernel_turn_with_salvage(
            resumed_state,
            FULL_PROMPT,
            repo / "turn-resume",
            kernel_runner=runner(resumed_calls, artifact=HARVESTED_STEP, succeed_on_short=True),
            installed_kernels={"cursor", "grok"},
            probe_peers=False,
            local_action=local_action,
        )
        health = load_kernel_health(repo)
        exhausted_calls: list[dict[str, str]] = []
        exhausted_state = mission(repo)
        _exhausted_result, exhausted_decision, exhausted_meta = execute_kernel_turn_with_salvage(
            exhausted_state,
            FULL_PROMPT,
            repo / "turn-exhausted",
            kernel_runner=runner(exhausted_calls, artifact=HARVESTED_STEP, succeed_on_short=False),
            installed_kernels={"cursor", "grok"},
            probe_peers=False,
            local_action=local_action,
        )
        health_after = load_kernel_health(repo)
        generic_calls: list[dict[str, str]] = []
        generic_state = mission(repo)
        _generic_result, generic_decision, generic_meta = execute_kernel_turn_with_salvage(
            generic_state,
            FULL_PROMPT,
            repo / "turn-generic",
            kernel_runner=runner(generic_calls, artifact=GENERIC_MISSING, succeed_on_short=False),
            installed_kernels={"cursor", "grok"},
            probe_peers=False,
            local_action=local_action,
        )

    short_resumes = [
        item
        for item in resumed_calls
        if item["kernel"] == "cursor" and item["full"] == "False" and item["continuation"] == "True"
    ]
    observed = {
        "harvested_class": harvested.class_id,
        "harvested_retryable": harvested.retryable,
        "bare_missing_class": bare_missing.class_id,
        "bare_missing_retryable": bare_missing.retryable,
        "bare_retries_class": bare_retries.class_id,
        "bare_retries_retryable": bare_retries.retryable,
        "quoted_class": quoted_success.class_id,
        "resumed_calls": resumed_calls,
        "resumed_status": resumed_decision.status,
        "resumed_source": resumed_meta.get("source"),
        "resumed_kernel": resumed_state.kernel,
        "resumed_session": resumed_state.session_id,
        "cursor_available_after_resume": kernel_is_available(health, "cursor"),
        "exhausted_calls": exhausted_calls,
        "exhausted_status": exhausted_decision.status,
        "exhausted_source": exhausted_meta.get("source"),
        "exhausted_kernel": exhausted_state.kernel,
        "cursor_available_after_exhaustion": kernel_is_available(health_after, "cursor"),
        "generic_calls": generic_calls,
        "generic_status": generic_decision.status,
        "generic_source": generic_meta.get("source"),
        "generic_kernel": generic_state.kernel,
    }
    passed = bool(
        harvested.class_id == "step_retries_exhausted"
        and harvested.retryable is False
        and bare_missing.class_id == "cli_error"
        and bare_missing.retryable is True
        and bare_retries.class_id == "cli_error"
        and bare_retries.retryable is True
        and quoted_success.class_id != "step_retries_exhausted"
        and len(resumed_calls) == 2
        and resumed_calls[0]["kernel"] == "cursor"
        and resumed_calls[0]["full"] == "True"
        and len(short_resumes) == 1
        and short_resumes[0]["session"] == SESSION
        and short_resumes[0]["started"] == "True"
        and resumed_decision.status == "continue"
        and resumed_decision.summary == "continued"
        and resumed_meta.get("source") == "step_retry_resume"
        and resumed_state.kernel == "cursor"
        and resumed_state.session_id == SESSION
        and kernel_is_available(health, "cursor") is True
        and len(exhausted_calls) == 3
        and exhausted_calls[0]["kernel"] == "cursor"
        and exhausted_calls[0]["full"] == "True"
        and exhausted_calls[1]["kernel"] == "cursor"
        and exhausted_calls[1]["full"] == "False"
        and exhausted_calls[1]["continuation"] == "True"
        and exhausted_calls[1]["session"] == SESSION
        and exhausted_calls[2]["kernel"] == "grok"
        and exhausted_calls[2]["full"] == "True"
        and exhausted_decision.status == "continue"
        and exhausted_meta.get("source") == "failover"
        and exhausted_state.kernel == "grok"
        and kernel_is_available(health_after, "cursor") is True
        and len(generic_calls) == 2
        and generic_calls[0]["kernel"] == "cursor"
        and generic_calls[0]["full"] == "True"
        and generic_calls[1]["kernel"] == "grok"
        and generic_calls[1]["full"] == "True"
        and generic_decision.status == "continue"
        and generic_meta.get("source") == "failover"
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
