"""A reaped Grok session actor must not keep that session or leave the kernel.

Harvested 2026-08-26 run 20260826T102353Z-ee74a113 exited 124 after 26 model
calls. The transcript says the resident session actor exited unexpectedly and
was reaped as DeadFailed for session 858749f4-3c21-4375-955c-65c08166b900.
The same stderr also says auth file lock timed out, so the death stayed a
generic timeout and the next resolution left Grok.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

SESSION = "858749f4-3c21-4375-955c-65c08166b900"
MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed after the session actor dies."
GROK_ERROR = "Grok CLI timed out after 7200 seconds; result details were written to latest-grok-run.json."
DEAD_STDERR = (
    "WARN auth: file lock timed out, waiting for sibling to finish\n"
    "WARN auth: returning transient to avoid RT reuse\n"
    "WARN Resident session actor exited unexpectedly; reaping as DeadFailed "
    f"session_id={SESSION}\n"
)
HARVESTED_DEAD = {
    "returncode": 124,
    "timed_out": True,
    "last_message": "Inspect the repo, then keep going from the files already changed.",
    "stdout_tail": '{"num_turns": 26, "modelUsage": {"grok-4.6-build": {"modelCalls": 26}}}',
    "stderr_tail": DEAD_STDERR,
    "session_id": "",
    "command": [
        "C:\\Users\\svmes\\.grok\\bin\\grok.EXE",
        "--session-id",
        SESSION,
        "--prompt-file",
        "task.md",
    ],
}
FILE_LOCK_TIMEOUT = {
    "returncode": 124,
    "timed_out": True,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": "WARN auth: file lock timed out, waiting for sibling to finish\n",
    "session_id": "",
    "command": ["grok.EXE", "--session-id", SESSION],
}


def _decision(summary: str) -> str:
    return json.dumps(
        {
            "status": "continue",
            "summary": summary,
            "strategy": "continue",
            "next_step": "continue the mission",
            "capability_delta": "",
            "outcome_evidence": ["fresh-session"],
            "validation": [],
            "done_when_met": False,
        }
    )


def _mission(repo: Path):
    from blackhole_agent.unbound import UnboundMission

    return UnboundMission(
        schema_version=1,
        mission_id="dead-session-actor-probe",
        created_at="2026-08-26T10:24:46Z",
        updated_at="2026-08-26T10:24:46Z",
        repo_path=str(repo),
        workspace_path=str(repo),
        branch="probe",
        target_branch="main",
        goal="Drop a Grok session whose resident actor was reaped as DeadFailed.",
        done_when="Grok continues once on a fresh session, or another kernel continues.",
        stage="execution",
        kernel="grok",
        session_id=SESSION,
        session_started=True,
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
                "continuation": str("resident session actor" in text.lower()),
                "resumes_dead_session": str(SESSION in text or str(getattr(state, "session_id", "") or "") == SESSION),
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
                session_id="",
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


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import kernel_is_available, load_kernel_health
    from blackhole_agent.kernel_salvage import classify_run_artifact, execute_kernel_turn_with_salvage

    death = classify_run_artifact(HARVESTED_DEAD, error=GROK_ERROR)
    file_lock = classify_run_artifact(FILE_LOCK_TIMEOUT, error=GROK_ERROR)
    one_phrase = classify_run_artifact(
        {
            "returncode": 124,
            "timed_out": True,
            "stderr_tail": "WARN Resident session actor exited unexpectedly\n",
            "last_message": "",
            "command": ["grok.EXE", "--session-id", SESSION],
        },
        error=GROK_ERROR,
    )
    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "stderr_tail": DEAD_STDERR,
            "last_message": "finished",
            "command": ["grok.EXE", "--session-id", SESSION],
        },
        error="",
    )

    with tempfile.TemporaryDirectory(prefix="dead-actor-fresh-") as tmp:
        repo = Path(tmp)
        fresh_calls: list[dict[str, str]] = []
        fresh_state = _mission(repo)
        _fresh_result, fresh_decision, fresh_meta = execute_kernel_turn_with_salvage(
            fresh_state,
            FULL_PROMPT,
            repo / "turn-fresh",
            kernel_runner=_runner(fresh_calls, artifact=HARVESTED_DEAD, succeed_on_short=True),
            installed_kernels={"grok", "codex"},
            probe_peers=False,
            local_action=_local_action,
        )
        health_after_fresh = load_kernel_health(repo)

    with tempfile.TemporaryDirectory(prefix="dead-actor-exhaust-") as tmp:
        repo = Path(tmp)
        exhausted_calls: list[dict[str, str]] = []
        exhausted_state = _mission(repo)
        _exhausted_result, exhausted_decision, exhausted_meta = execute_kernel_turn_with_salvage(
            exhausted_state,
            FULL_PROMPT,
            repo / "turn-exhausted",
            kernel_runner=_runner(exhausted_calls, artifact=HARVESTED_DEAD, succeed_on_short=False),
            installed_kernels={"grok", "codex"},
            probe_peers=False,
            local_action=_local_action,
        )
        health_after_exhaustion = load_kernel_health(repo)
        follow_calls: list[dict[str, str]] = []
        follow_state = _mission(repo)
        _follow_result, follow_decision, follow_meta = execute_kernel_turn_with_salvage(
            follow_state,
            FULL_PROMPT,
            repo / "turn-follow",
            kernel_runner=_runner(follow_calls, artifact=HARVESTED_DEAD, succeed_on_short=True),
            installed_kernels={"grok", "codex"},
            health=health_after_exhaustion,
            probe_peers=False,
            persist_health=False,
            local_action=_local_action,
        )

    fresh_continuations = [
        item
        for item in fresh_calls
        if item["kernel"] == "grok" and item["full"] == "False" and item["continuation"] == "True"
    ]
    breaker = health_after_exhaustion.kernels.get("grok") if isinstance(health_after_exhaustion.kernels, dict) else None
    circuit_class = str(getattr(breaker, "class_id", "") or "")
    observed = {
        "death_class": death.class_id,
        "death_retryable": death.retryable,
        "file_lock_class": file_lock.class_id,
        "one_phrase_class": one_phrase.class_id,
        "zero_exit_class": zero_exit.class_id,
        "fresh_calls": fresh_calls,
        "fresh_status": fresh_decision.status,
        "fresh_summary": fresh_decision.summary,
        "fresh_source": fresh_meta.get("source"),
        "fresh_kernel": fresh_state.kernel,
        "fresh_session": fresh_state.session_id,
        "grok_available_after_fresh": kernel_is_available(health_after_fresh, "grok"),
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
        death.class_id == "session_actor_dead"
        and death.retryable is False
        and file_lock.class_id == "timeout"
        and file_lock.retryable is True
        and one_phrase.class_id != "session_actor_dead"
        and zero_exit.class_id != "session_actor_dead"
        and len(fresh_calls) == 2
        and fresh_calls[0]["kernel"] == "grok"
        and fresh_calls[0]["session"] == SESSION
        and fresh_calls[0]["started"] == "True"
        and fresh_calls[0]["full"] == "True"
        and fresh_calls[0]["continuation"] == "False"
        and len(fresh_continuations) == 1
        and fresh_continuations[0]["session"] == ""
        and fresh_continuations[0]["started"] == "False"
        and fresh_continuations[0]["resumes_dead_session"] == "False"
        and fresh_decision.status == "continue"
        and fresh_decision.summary == "continued"
        and fresh_meta.get("source") == "dead_actor_fresh_session"
        and fresh_state.kernel == "grok"
        and fresh_state.session_id == ""
        and kernel_is_available(health_after_fresh, "grok") is True
        and len(exhausted_calls) == 3
        and exhausted_calls[0]["kernel"] == "grok"
        and exhausted_calls[0]["session"] == SESSION
        and exhausted_calls[0]["full"] == "True"
        and exhausted_calls[1]["kernel"] == "grok"
        and exhausted_calls[1]["full"] == "False"
        and exhausted_calls[1]["continuation"] == "True"
        and exhausted_calls[1]["session"] == ""
        and exhausted_calls[1]["resumes_dead_session"] == "False"
        and exhausted_calls[2]["kernel"] == "codex"
        and exhausted_calls[2]["full"] == "True"
        and exhausted_decision.status == "continue"
        and exhausted_meta.get("source") == "failover"
        and exhausted_state.kernel == "codex"
        and kernel_is_available(health_after_exhaustion, "grok") is True
        and circuit_class not in {"auth_failed", "session_actor_dead"}
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
