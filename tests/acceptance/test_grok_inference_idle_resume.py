"""A Grok inference idle timeout must resume the same session.

Harvested 2026-08-25 run 20260825T174327Z-1e9ef9af exited 124 after 20 model
calls. The transcript says inference idle timeout after 3600s with no chunks.
The run is recorded timed_out, and the same stderr also says grep timed out
and file lock timed out, so the death stayed a generic timeout and the next
resolution replayed the mission.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

SESSION = "a3f87572-fb23-4403-9500-d6ad0149baa9"
MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed after inference goes idle."
GROK_ERROR = "Grok CLI timed out after 7200 seconds; result details were written to latest-grok-run.json."
IDLE_STDERR = (
    "WARN grep timed out timeout_secs=20\n"
    'ERROR error=Internal error: "inference idle timeout after 3600s with no chunks"\n'
    "WARN auth: file lock timed out, waiting for sibling to finish\n"
    "WARN Final signal sync timed out during exit; continuing\n"
)
HARVESTED_IDLE = {
    "returncode": 124,
    "timed_out": True,
    "last_message": (
        "Internal error: {\n"
        '  "message": "inference idle timeout after 3600s with no chunks",\n'
        '  "promptUsage": {"modelCalls": 20}\n'
        "}"
    ),
    "stdout_tail": (
        '{"type":"error","message":"inference idle timeout after 3600s with no chunks",'
        '"num_turns":20}\n'
    ),
    "stderr_tail": IDLE_STDERR,
    "session_id": "",
    "command": [
        "C:\\Users\\svmes\\.grok\\bin\\grok.EXE",
        "--session-id",
        SESSION,
        "--prompt-file",
        "task.md",
    ],
}
BARE_TIMEOUT = {
    "returncode": 124,
    "timed_out": True,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": (
        "WARN grep timed out timeout_secs=20\n"
        "WARN auth: file lock timed out, waiting for sibling to finish\n"
    ),
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
            "outcome_evidence": ["resumed"],
            "validation": [],
            "done_when_met": False,
        }
    )


def _mission(repo: Path):
    from blackhole_agent.unbound import UnboundMission

    return UnboundMission(
        schema_version=1,
        mission_id="inference-idle-probe",
        created_at="2026-08-25T17:44:41Z",
        updated_at="2026-08-25T17:44:41Z",
        repo_path=str(repo),
        workspace_path=str(repo),
        branch="probe",
        target_branch="main",
        goal="Keep the Grok session after inference goes idle.",
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
                "continuation": str("inference went idle" in text.lower()),
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
                session_id=str(getattr(state, "session_id", "") or SESSION),
                command=("grok", "--resume", SESSION),
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

    death = classify_run_artifact(HARVESTED_IDLE, error=GROK_ERROR)
    bare_timeout = classify_run_artifact(BARE_TIMEOUT, error="Grok CLI timed out after 7200 seconds")
    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "last_message": "finished",
            "stdout_tail": "",
            "stderr_tail": (
                'ERROR error=Internal error: "inference idle timeout after 3600s with no chunks"\n'
            ),
            "command": ["grok.EXE", "--session-id", SESSION],
        },
        error="",
    )

    with tempfile.TemporaryDirectory(prefix="inference-idle-resume-") as tmp:
        repo = Path(tmp)
        resumed_calls: list[dict[str, str]] = []
        resumed_state = _mission(repo)
        _resumed_result, resumed_decision, resumed_meta = execute_kernel_turn_with_salvage(
            resumed_state,
            FULL_PROMPT,
            repo / "turn-resume",
            kernel_runner=_runner(resumed_calls, artifact=HARVESTED_IDLE, succeed_on_short=True),
            installed_kernels={"grok", "codex"},
            probe_peers=False,
            local_action=_local_action,
        )
        health_after_resume = load_kernel_health(repo)

    with tempfile.TemporaryDirectory(prefix="inference-idle-exhaust-") as tmp:
        repo = Path(tmp)
        exhausted_calls: list[dict[str, str]] = []
        exhausted_state = _mission(repo)
        _exhausted_result, exhausted_decision, exhausted_meta = execute_kernel_turn_with_salvage(
            exhausted_state,
            FULL_PROMPT,
            repo / "turn-exhausted",
            kernel_runner=_runner(exhausted_calls, artifact=HARVESTED_IDLE, succeed_on_short=False),
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
            kernel_runner=_runner(follow_calls, artifact=HARVESTED_IDLE, succeed_on_short=True),
            installed_kernels={"grok", "codex"},
            health=health_after_exhaustion,
            probe_peers=False,
            persist_health=False,
            local_action=_local_action,
        )

    short_resumes = [
        item
        for item in resumed_calls
        if item["kernel"] == "grok" and item["full"] == "False" and item["continuation"] == "True"
    ]
    breaker = health_after_exhaustion.kernels.get("grok") if isinstance(health_after_exhaustion.kernels, dict) else None
    circuit_class = str(getattr(breaker, "class_id", "") or "")
    observed = {
        "death_class": death.class_id,
        "death_retryable": death.retryable,
        "bare_timeout_class": bare_timeout.class_id,
        "bare_timeout_retryable": bare_timeout.retryable,
        "zero_exit_class": zero_exit.class_id,
        "resumed_calls": resumed_calls,
        "resumed_status": resumed_decision.status,
        "resumed_summary": resumed_decision.summary,
        "resumed_source": resumed_meta.get("source"),
        "resumed_kernel": resumed_state.kernel,
        "resumed_session": resumed_state.session_id,
        "grok_available_after_resume": kernel_is_available(health_after_resume, "grok"),
        "exhausted_calls": exhausted_calls,
        "exhausted_status": exhausted_decision.status,
        "exhausted_source": exhausted_meta.get("source"),
        "exhausted_kernel": exhausted_state.kernel,
        "grok_available_after_exhaustion": kernel_is_available(health_after_exhaustion, "grok"),
        "auth_circuit_after_exhaustion": circuit_class,
        "follow_calls": follow_calls,
        "follow_status": follow_decision.status,
        "follow_kernel": follow_state.kernel,
        "follow_rerouted_from": follow_meta.get("rerouted_from"),
    }
    passed = bool(
        death.class_id == "inference_idle_timeout"
        and death.retryable is False
        and bare_timeout.class_id == "timeout"
        and bare_timeout.retryable is True
        and zero_exit.class_id != "inference_idle_timeout"
        and len(resumed_calls) == 2
        and resumed_calls[0]["kernel"] == "grok"
        and resumed_calls[0]["full"] == "True"
        and resumed_calls[0]["continuation"] == "False"
        and len(short_resumes) == 1
        and short_resumes[0]["session"] == SESSION
        and short_resumes[0]["started"] == "True"
        and resumed_decision.status == "continue"
        and resumed_decision.summary == "continued"
        and resumed_meta.get("source") == "inference_idle_resume"
        and resumed_state.kernel == "grok"
        and resumed_state.session_id == SESSION
        and kernel_is_available(health_after_resume, "grok") is True
        and len(exhausted_calls) == 3
        and exhausted_calls[0]["kernel"] == "grok"
        and exhausted_calls[0]["full"] == "True"
        and exhausted_calls[1]["kernel"] == "grok"
        and exhausted_calls[1]["full"] == "False"
        and exhausted_calls[1]["continuation"] == "True"
        and exhausted_calls[1]["session"] == SESSION
        and exhausted_calls[2]["kernel"] == "codex"
        and exhausted_calls[2]["full"] == "True"
        and exhausted_decision.status == "continue"
        and exhausted_meta.get("source") == "failover"
        and exhausted_state.kernel == "codex"
        and kernel_is_available(health_after_exhaustion, "grok") is True
        and circuit_class != "auth_failed"
        and circuit_class != "inference_idle_timeout"
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
