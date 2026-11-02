"""A Windows all-ones exit on a resumed Grok session continues that session.

Harvested 2026-07-31 run 20260731T101316Z exited 4294967295 with an empty
transcript, timed_out false, and --resume b3c94acc-389f-43e5-ad01-34ad7502e679.
That death stayed a retryable CLI error, so the next resolution replayed the
mission prompt.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

SESSION = "b3c94acc-389f-43e5-ad01-34ad7502e679"
MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed after an abnormal process exit."
GROK_ERROR = (
    "Grok CLI failed with exit code 4294967295; "
    "result details were written to latest-grok-run.json."
)
HARVESTED_STDERR = (
    "auto worktree gc failed: neither $GROK_HOME nor $HOME is set\n"
    "extract_initial_tokens warning\n"
)
HARVESTED_DEATH = {
    "returncode": 4294967295,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": HARVESTED_STDERR,
    "session_id": "",
    "command": ["grok.EXE", "--resume", SESSION, "--prompt", "task.md"],
}
EXIT_ONE = {
    "returncode": 1,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": "",
    "session_id": SESSION,
    "command": ["grok.EXE", "--resume", SESSION],
}
TIMEOUT_EXIT = {
    "returncode": 124,
    "timed_out": True,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": "",
    "session_id": SESSION,
    "command": ["grok.EXE", "--resume", SESSION],
}
ZERO_EXIT = {
    "returncode": 0,
    "timed_out": False,
    "last_message": "finished",
    "stdout_tail": "",
    "stderr_tail": "",
    "session_id": SESSION,
    "command": ["grok.EXE", "--resume", SESSION],
}
NO_SESSION = {
    "returncode": 4294967295,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "tool output that is not a session",
    "stderr_tail": "",
    "session_id": "",
    "command": ["kimi", "--prompt", "task.md"],
}


def _decision(summary: str) -> str:
    return json.dumps(
        {
            "status": "continue",
            "summary": summary,
            "strategy": "continue",
            "next_step": "continue the mission",
            "capability_delta": "",
            "outcome_evidence": ["continued"],
            "validation": [],
            "done_when_met": False,
        }
    )


def _mission(repo: Path):
    from blackhole_agent.unbound import UnboundMission

    return UnboundMission(
        schema_version=1,
        mission_id="abnormal-process-exit-probe",
        created_at="2026-07-31T10:13:16Z",
        updated_at="2026-07-31T10:13:16Z",
        repo_path=str(repo),
        workspace_path=str(repo),
        branch="probe",
        target_branch="main",
        goal="Continue Grok after Windows records exit 4294967295 on a resumed session.",
        done_when="The same session emits a JSON decision, or another kernel continues.",
        stage="execution",
        kernel="grok",
        session_id="",
        session_started=False,
    )


def _runner(calls: list[dict[str, str]], *, artifact: dict, succeed_on_short: bool):
    from blackhole_agent.unbound import KernelTurnResult

    def run(state, prompt, turn_dir, **kwargs):
        del kwargs
        text = str(prompt)
        calls.append(
            {
                "kernel": str(state.kernel),
                "session": str(getattr(state, "session_id", "") or ""),
                "started": str(bool(getattr(state, "session_started", False))),
                "full": str(MARKER in text),
                "continuation": str("4294967295" in text and MARKER not in text),
            }
        )
        if state.kernel != "grok":
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
                kernel="grok",
                last_message=_decision("continued"),
                session_id=str(getattr(state, "session_id", "") or ""),
                command=("grok",),
                result_path="",
            )
        kernel_dir = Path(turn_dir) / "kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        (kernel_dir / "latest-grok-run.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )
        raise RuntimeError(GROK_ERROR)

    return run


def _local_action(state, workspace):
    del state, workspace
    return {"status": "continue", "summary": "local tick"}


def _run(repo_name: str, artifact: dict, *, succeed_on_short: bool, health=None, persist: bool = True):
    from blackhole_agent.kernel_salvage import execute_kernel_turn_with_salvage

    with tempfile.TemporaryDirectory(prefix=repo_name) as tmp:
        repo = Path(tmp)
        calls: list[dict[str, str]] = []
        state = _mission(repo)
        _result, decision, meta = execute_kernel_turn_with_salvage(
            state,
            FULL_PROMPT,
            repo / "turn",
            kernel_runner=_runner(calls, artifact=artifact, succeed_on_short=succeed_on_short),
            installed_kernels={"grok", "codex"},
            health=health,
            probe_peers=False,
            persist_health=persist,
            local_action=_local_action,
        )
        from blackhole_agent.kernel_health import load_kernel_health

        stored = health if not persist else load_kernel_health(repo)
        return calls, decision, meta, state, stored


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import kernel_is_available
    from blackhole_agent.kernel_salvage import classify_run_artifact

    death = classify_run_artifact(HARVESTED_DEATH, error=GROK_ERROR)
    exit_one = classify_run_artifact(EXIT_ONE, error="Grok CLI failed with exit code 1")
    timeout_exit = classify_run_artifact(TIMEOUT_EXIT, error="Grok CLI timed out after 7200 seconds")
    zero_exit = classify_run_artifact(ZERO_EXIT, error="")
    no_session = classify_run_artifact(NO_SESSION, error="Kimi CLI failed with exit code 4294967295")

    resumed_calls, resumed_decision, resumed_meta, resumed_state, health_after_resume = _run(
        "abnormal-exit-resume-",
        HARVESTED_DEATH,
        succeed_on_short=True,
    )
    exhausted_calls, exhausted_decision, exhausted_meta, exhausted_state, health_after_exhaustion = _run(
        "abnormal-exit-exhaust-",
        HARVESTED_DEATH,
        succeed_on_short=False,
    )
    follow_calls, follow_decision, follow_meta, follow_state, _follow_health = _run(
        "abnormal-exit-follow-",
        HARVESTED_DEATH,
        succeed_on_short=True,
        health=health_after_exhaustion,
        persist=False,
    )

    short_resumes = [
        item
        for item in resumed_calls
        if item["kernel"] == "grok" and item["full"] == "False" and item["continuation"] == "True"
    ]
    breaker = (
        health_after_exhaustion.kernels.get("grok")
        if isinstance(health_after_exhaustion.kernels, dict)
        else None
    )
    circuit_class = str(getattr(breaker, "class_id", "") or "")
    observed = {
        "death_class": death.class_id,
        "death_retryable": death.retryable,
        "exit_one_class": exit_one.class_id,
        "exit_one_retryable": exit_one.retryable,
        "timeout_class": timeout_exit.class_id,
        "timeout_retryable": timeout_exit.retryable,
        "zero_exit_class": zero_exit.class_id,
        "no_session_class": no_session.class_id,
        "no_session_retryable": no_session.retryable,
        "resumed_calls": resumed_calls,
        "resumed_status": resumed_decision.status,
        "resumed_summary": resumed_decision.summary,
        "resumed_source": resumed_meta.get("source"),
        "resumed_kernel": resumed_state.kernel,
        "resumed_session": resumed_state.session_id,
        "resumed_session_started": bool(getattr(resumed_state, "session_started", False)),
        "grok_available_after_resume": kernel_is_available(health_after_resume, "grok"),
        "exhausted_calls": exhausted_calls,
        "exhausted_status": exhausted_decision.status,
        "exhausted_source": exhausted_meta.get("source"),
        "exhausted_kernel": exhausted_state.kernel,
        "grok_available_after_exhaustion": kernel_is_available(health_after_exhaustion, "grok"),
        "circuit_after_exhaustion": circuit_class,
        "follow_calls": follow_calls,
        "follow_status": follow_decision.status,
        "follow_kernel": follow_state.kernel,
        "follow_rerouted_from": follow_meta.get("rerouted_from"),
    }
    passed = bool(
        death.class_id == "abnormal_process_exit"
        and death.retryable is False
        and exit_one.class_id == "cli_error"
        and exit_one.retryable is True
        and timeout_exit.class_id == "timeout"
        and timeout_exit.retryable is True
        and zero_exit.class_id != "abnormal_process_exit"
        and no_session.class_id == "cli_error"
        and no_session.retryable is True
        and len(resumed_calls) == 2
        and resumed_calls[0]["kernel"] == "grok"
        and resumed_calls[0]["full"] == "True"
        and resumed_calls[0]["continuation"] == "False"
        and resumed_calls[0]["session"] == ""
        and len(short_resumes) == 1
        and short_resumes[0]["session"] == SESSION
        and short_resumes[0]["started"] == "True"
        and resumed_decision.status == "continue"
        and resumed_decision.summary == "continued"
        and resumed_meta.get("source") == "abnormal_process_resume"
        and resumed_state.kernel == "grok"
        and resumed_state.session_id == SESSION
        and bool(getattr(resumed_state, "session_started", False)) is True
        and kernel_is_available(health_after_resume, "grok") is True
        and len(exhausted_calls) == 3
        and exhausted_calls[0]["full"] == "True"
        and exhausted_calls[1]["kernel"] == "grok"
        and exhausted_calls[1]["full"] == "False"
        and exhausted_calls[1]["continuation"] == "True"
        and exhausted_calls[1]["session"] == SESSION
        and exhausted_calls[2]["kernel"] == "codex"
        and exhausted_calls[2]["full"] == "True"
        and exhausted_decision.status == "continue"
        and exhausted_decision.summary == "other kernel"
        and exhausted_meta.get("source") == "failover"
        and exhausted_state.kernel == "codex"
        and kernel_is_available(health_after_exhaustion, "grok") is True
        and circuit_class not in {"auth_failed", "abnormal_process_exit"}
        and len(follow_calls) == 2
        and follow_calls[0]["kernel"] == "grok"
        and follow_calls[0]["full"] == "True"
        and follow_decision.status == "continue"
        and follow_state.kernel == "grok"
        and follow_meta.get("rerouted_from") in (None, "")
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
