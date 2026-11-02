"""A Kimi background-task wait must continue on the same kernel.

Harvested 2026-09-12 run 20260912T181339Z-47f10307 exited 124 while stderr
repeated that one background task was still running. The command had no
session id. The death stayed a retryable timeout, so the next resolution
sent the original mission prompt to another kernel.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

SESSION = "4f2c1a90-7b11-4e2a-9c31-0a6d5e8b1234"
MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed after a background-task wait."
KIMI_ERROR = "Kimi CLI timed out after 7200 seconds; result details were written to latest-kimi-run.json."
WAIT_STDERR = (
    "WARN grep timed out timeout_secs=20\n"
    "Waiting 4m 39s / 10m · 1 background task still running\n"
    "Waiting 14s / 10m · 1 background task still running\n"
)
HARVESTED_WAIT = {
    "returncode": 124,
    "timed_out": True,
    "last_message": "Confirmed the failures reproduce at HEAD. Now let me find what the proof checks.",
    "stdout_tail": "",
    "stderr_tail": WAIT_STDERR,
    "session_id": "",
    "command": [
        "C:\\Program Files\\nodejs\\node.EXE",
        "C:\\Users\\svmes\\AppData\\Roaming\\npm\\node_modules\\@moonshot-ai\\kimi-code\\dist\\main.mjs",
        "--output-format",
        "stream-json",
        "--prompt",
        "<prompt stored at kimi-task.md>",
    ],
}
SESSION_WAIT = {
    **HARVESTED_WAIT,
    "command": ["kimi", "--session-id", SESSION, "--prompt", "task.md"],
}
BARE_TIMEOUT = {
    "returncode": 124,
    "timed_out": True,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": "WARN grep timed out timeout_secs=20\nWARN MCP server 'gmail' timed out after 90s\n",
    "session_id": "",
    "command": ["kimi", "--prompt", "task.md"],
}
ZERO_EXIT = {
    "returncode": 0,
    "timed_out": False,
    "last_message": "The milestone gate rejected the claim.",
    "stdout_tail": "",
    "stderr_tail": "Waiting 1s / 10m · 1 background task still running\n",
    "session_id": "session_kept",
    "command": ["kimi", "--session-id", "session_kept"],
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
        mission_id="background-task-wait-probe",
        created_at="2026-09-12T18:14:35Z",
        updated_at="2026-09-12T18:14:35Z",
        repo_path=str(repo),
        workspace_path=str(repo),
        branch="probe",
        target_branch="main",
        goal="Continue Kimi after it is killed while waiting on a background task.",
        done_when="The same kernel emits a JSON decision, or another kernel continues.",
        stage="execution",
        kernel="kimi",
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
                "continuation": str("waited on a background task" in text.lower()),
            }
        )
        if state.kernel != "kimi":
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
                kernel="kimi",
                last_message=_decision("continued"),
                session_id=str(getattr(state, "session_id", "") or ""),
                command=("kimi",),
                result_path="",
            )
        kernel_dir = Path(turn_dir) / "kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)
        (kernel_dir / "latest-kimi-run.json").write_text(
            json.dumps(artifact),
            encoding="utf-8",
        )
        raise RuntimeError(KIMI_ERROR)

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
            installed_kernels={"kimi", "codex"},
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

    death = classify_run_artifact(HARVESTED_WAIT, error=KIMI_ERROR)
    bare_timeout = classify_run_artifact(BARE_TIMEOUT, error="Kimi CLI timed out after 7200 seconds")
    zero_exit = classify_run_artifact(ZERO_EXIT, error="")
    session_death = classify_run_artifact(SESSION_WAIT, error=KIMI_ERROR)

    resumed_calls, resumed_decision, resumed_meta, resumed_state, health_after_resume = _run(
        "background-wait-resume-",
        HARVESTED_WAIT,
        succeed_on_short=True,
    )
    exhausted_calls, exhausted_decision, exhausted_meta, exhausted_state, health_after_exhaustion = _run(
        "background-wait-exhaust-",
        HARVESTED_WAIT,
        succeed_on_short=False,
    )
    follow_calls, follow_decision, follow_meta, follow_state, _follow_health = _run(
        "background-wait-follow-",
        HARVESTED_WAIT,
        succeed_on_short=True,
        health=health_after_exhaustion,
        persist=False,
    )
    session_calls, session_decision, session_meta, session_state, _session_health = _run(
        "background-wait-session-",
        SESSION_WAIT,
        succeed_on_short=True,
    )

    short_resumes = [
        item
        for item in resumed_calls
        if item["kernel"] == "kimi" and item["full"] == "False" and item["continuation"] == "True"
    ]
    session_resumes = [
        item
        for item in session_calls
        if item["kernel"] == "kimi" and item["full"] == "False" and item["continuation"] == "True"
    ]
    breaker = (
        health_after_exhaustion.kernels.get("kimi")
        if isinstance(health_after_exhaustion.kernels, dict)
        else None
    )
    circuit_class = str(getattr(breaker, "class_id", "") or "")
    observed = {
        "death_class": death.class_id,
        "death_retryable": death.retryable,
        "bare_timeout_class": bare_timeout.class_id,
        "bare_timeout_retryable": bare_timeout.retryable,
        "zero_exit_class": zero_exit.class_id,
        "session_death_class": session_death.class_id,
        "resumed_calls": resumed_calls,
        "resumed_status": resumed_decision.status,
        "resumed_summary": resumed_decision.summary,
        "resumed_source": resumed_meta.get("source"),
        "resumed_kernel": resumed_state.kernel,
        "resumed_session": resumed_state.session_id,
        "kimi_available_after_resume": kernel_is_available(health_after_resume, "kimi"),
        "exhausted_calls": exhausted_calls,
        "exhausted_status": exhausted_decision.status,
        "exhausted_source": exhausted_meta.get("source"),
        "exhausted_kernel": exhausted_state.kernel,
        "kimi_available_after_exhaustion": kernel_is_available(health_after_exhaustion, "kimi"),
        "circuit_after_exhaustion": circuit_class,
        "follow_calls": follow_calls,
        "follow_status": follow_decision.status,
        "follow_kernel": follow_state.kernel,
        "follow_rerouted_from": follow_meta.get("rerouted_from"),
        "session_calls": session_calls,
        "session_status": session_decision.status,
        "session_source": session_meta.get("source"),
        "session_kept": session_state.session_id,
    }
    passed = bool(
        death.class_id == "background_task_wait"
        and death.retryable is False
        and bare_timeout.class_id == "timeout"
        and bare_timeout.retryable is True
        and zero_exit.class_id != "background_task_wait"
        and session_death.class_id == "background_task_wait"
        and len(resumed_calls) == 2
        and resumed_calls[0]["kernel"] == "kimi"
        and resumed_calls[0]["full"] == "True"
        and resumed_calls[0]["continuation"] == "False"
        and resumed_calls[0]["session"] == ""
        and len(short_resumes) == 1
        and short_resumes[0]["session"] == ""
        and resumed_decision.status == "continue"
        and resumed_decision.summary == "continued"
        and resumed_meta.get("source") == "background_task_resume"
        and resumed_state.kernel == "kimi"
        and resumed_state.session_id == ""
        and kernel_is_available(health_after_resume, "kimi") is True
        and len(exhausted_calls) == 3
        and exhausted_calls[0]["full"] == "True"
        and exhausted_calls[1]["kernel"] == "kimi"
        and exhausted_calls[1]["full"] == "False"
        and exhausted_calls[1]["continuation"] == "True"
        and exhausted_calls[2]["kernel"] == "codex"
        and exhausted_calls[2]["full"] == "True"
        and exhausted_decision.status == "continue"
        and exhausted_decision.summary == "other kernel"
        and exhausted_meta.get("source") == "failover"
        and exhausted_state.kernel == "codex"
        and kernel_is_available(health_after_exhaustion, "kimi") is True
        and circuit_class not in {"auth_failed", "background_task_wait"}
        and len(follow_calls) == 2
        and follow_calls[0]["kernel"] == "kimi"
        and follow_calls[0]["full"] == "True"
        and follow_decision.status == "continue"
        and follow_state.kernel == "kimi"
        and follow_meta.get("rerouted_from") in (None, "")
        and len(session_resumes) == 1
        and session_resumes[0]["session"] == SESSION
        and session_resumes[0]["started"] == "True"
        and session_decision.status == "continue"
        and session_meta.get("source") == "background_task_resume"
        and session_state.kernel == "kimi"
        and session_state.session_id == SESSION
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
