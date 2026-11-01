"""A tool timeout must not hide a max_tokens truncation.

Harvested 2026-08-25 run 20260825T054458Z-daa11fd7 exited 1 after 25 turns.
The transcript says response truncated by max_tokens and error_kind
max_tokens_truncation. The same stderr also says grep timed out and signal
sync timed out, so the death stayed a generic timeout and the next resolution
replayed the mission prompt.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

SESSION = "7878ab71-f28d-4a71-a2d6-bc40e293145e"
MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed after a hidden truncation."
GROK_ERROR = "Grok CLI failed with exit code 1; result details were written to latest-grok-run.json."
MASKED_STDERR = (
    "2026-08-25T05:46:39.453256Z  WARN grep timed out timeout_secs=20\n"
    "2026-08-25T06:38:34.784077Z ERROR error=Internal error: {\n"
    '  "message": "response truncated by max_tokens",\n'
    '  "error_kind": "max_tokens_truncation"\n'
    "}\n"
    "2026-08-25T06:38:36.862707Z  WARN Final signal sync timed out during exit; "
    f"continuing session_id={SESSION} timeout_ms=2000\n"
)
HARVESTED_MASKED = {
    "returncode": 1,
    "timed_out": False,
    "last_message": (
        "Internal error: {\n"
        '  "message": "response truncated by max_tokens",\n'
        '  "error_kind": "max_tokens_truncation"\n'
        "}"
    ),
    "stdout_tail": (
        '{"type":"error","message":"Internal error: {\\n  \\"message\\": '
        '\\"response truncated by max_tokens\\",\\n  \\"error_kind\\": '
        '\\"max_tokens_truncation\\"\\n}","num_turns":25}\n'
    ),
    "stderr_tail": MASKED_STDERR,
    "session_id": "",
    "command": ["grok.EXE", "--session-id", SESSION, "--prompt-file", "task.md"],
}
BARE_TIMEOUT = {
    "returncode": 1,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": "WARN grep timed out timeout_secs=20\n",
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


def observe() -> tuple[bool, dict]:
    from blackhole_agent.kernel_health import kernel_is_available, load_kernel_health
    from blackhole_agent.kernel_salvage import classify_run_artifact, execute_kernel_turn_with_salvage
    from blackhole_agent.unbound import KernelTurnResult, UnboundMission, build_turn_prompt

    death = classify_run_artifact(HARVESTED_MASKED, error=GROK_ERROR)
    bare_timeout = classify_run_artifact(BARE_TIMEOUT, error=GROK_ERROR)
    zero_exit = classify_run_artifact(
        {
            "returncode": 0,
            "timed_out": False,
            "last_message": "finished",
            "stdout_tail": "",
            "stderr_tail": (
                "WARN grep timed out timeout_secs=20\n"
                'ERROR error=Internal error: "response truncated by max_tokens" '
                "error_kind max_tokens_truncation\n"
            ),
            "command": ["grok.EXE", "--session-id", SESSION],
        },
    )
    one_phrase = classify_run_artifact(
        {
            "returncode": 1,
            "timed_out": False,
            "last_message": "",
            "stdout_tail": "",
            "stderr_tail": (
                "WARN grep timed out timeout_secs=20\n"
                "notes mention max_tokens_truncation only\n"
            ),
            "command": ["grok.EXE", "--session-id", SESSION],
        },
        error=GROK_ERROR,
    )

    def mission(repo: Path) -> UnboundMission:
        return UnboundMission(
            schema_version=1,
            mission_id="masked-truncation-probe",
            created_at="2026-08-25T05:45:48Z",
            updated_at="2026-08-25T06:38:36Z",
            repo_path=str(repo),
            workspace_path=str(repo),
            branch="probe",
            target_branch="main",
            goal="Finish the truncated session.",
            done_when="The session emits a JSON decision.",
            stage="execution",
            kernel="grok",
            session_id=SESSION,
            session_started=True,
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
                    "decision_only": str("do not call tools" in text.lower()),
                }
            )
            kernel_dir = Path(turn_dir) / "kernel"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            short = MARKER not in text
            if succeed_on_short and short and state.kernel == "grok":
                return KernelTurnResult(
                    kernel="grok",
                    last_message=_decision("decision only"),
                    session_id=SESSION,
                    command=("grok", "--resume", SESSION),
                    result_path="",
                )
            (kernel_dir / f"latest-{state.kernel}-run.json").write_text(
                json.dumps(artifact),
                encoding="utf-8",
            )
            raise RuntimeError(GROK_ERROR)

        return run

    def local_action(state, workspace):
        del state, workspace
        return {"status": "continue", "summary": "local tick"}

    with tempfile.TemporaryDirectory(prefix="masked-truncation-resume-") as tmp:
        repo = Path(tmp)
        resumed_calls: list[dict[str, str]] = []
        resumed_state = mission(repo)
        _resumed_result, resumed_decision, resumed_meta = execute_kernel_turn_with_salvage(
            resumed_state,
            FULL_PROMPT,
            repo / "turn-resume",
            kernel_runner=runner(resumed_calls, artifact=HARVESTED_MASKED, succeed_on_short=True),
            installed_kernels={"grok", "cursor"},
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
            kernel_runner=runner(exhausted_calls, artifact=HARVESTED_MASKED, succeed_on_short=False),
            installed_kernels={"grok", "cursor"},
            probe_peers=False,
            local_action=local_action,
        )
        follow_up = build_turn_prompt(
            exhausted_state,
            {
                "head": "abc",
                "status": MARKER,
                "diff_stat": MARKER,
                "recent_commits": MARKER,
            },
            state_path=repo / "state.json",
        )
        bare_calls: list[dict[str, str]] = []
        bare_state = mission(repo)
        _bare_result, bare_decision, bare_meta = execute_kernel_turn_with_salvage(
            bare_state,
            FULL_PROMPT,
            repo / "turn-bare",
            kernel_runner=runner(bare_calls, artifact=BARE_TIMEOUT, succeed_on_short=True),
            installed_kernels={"grok", "cursor"},
            probe_peers=False,
            local_action=local_action,
        )

    short_resumes = [
        item
        for item in resumed_calls
        if item["kernel"] == "grok" and item["full"] == "False" and item["decision_only"] == "True"
    ]
    bare_decision_only = [item for item in bare_calls if item["decision_only"] == "True"]
    observed = {
        "death_class": death.class_id,
        "death_retryable": death.retryable,
        "bare_timeout_class": bare_timeout.class_id,
        "bare_timeout_retryable": bare_timeout.retryable,
        "zero_exit_class": zero_exit.class_id,
        "one_phrase_class": one_phrase.class_id,
        "resumed_calls": resumed_calls,
        "resumed_status": resumed_decision.status,
        "resumed_summary": resumed_decision.summary,
        "resumed_source": resumed_meta.get("source"),
        "resumed_kernel": resumed_state.kernel,
        "resumed_session": resumed_state.session_id,
        "grok_available": kernel_is_available(health, "grok"),
        "exhausted_calls": exhausted_calls,
        "exhausted_status": exhausted_decision.status,
        "exhausted_source": exhausted_meta.get("source"),
        "exhausted_kernel": exhausted_state.kernel,
        "exhausted_session": exhausted_state.session_id,
        "decision_only_resume": bool(getattr(exhausted_state, "decision_only_resume", False)),
        "follow_up_has_marker": MARKER in follow_up,
        "follow_up_decision_only": "do not call tools" in follow_up.lower(),
        "bare_calls": bare_calls,
        "bare_status": bare_decision.status,
        "bare_source": bare_meta.get("source"),
        "bare_kernel": bare_state.kernel,
    }
    passed = bool(
        death.class_id == "output_truncated"
        and death.retryable is False
        and bare_timeout.class_id == "timeout"
        and bare_timeout.retryable is True
        and zero_exit.class_id != "output_truncated"
        and one_phrase.class_id == "timeout"
        and len(resumed_calls) == 2
        and resumed_calls[0]["kernel"] == "grok"
        and resumed_calls[0]["full"] == "True"
        and resumed_calls[0]["decision_only"] == "False"
        and len(short_resumes) == 1
        and short_resumes[0]["session"] == SESSION
        and short_resumes[0]["started"] == "True"
        and resumed_decision.status == "continue"
        and resumed_decision.summary == "decision only"
        and resumed_meta.get("source") == "decision_only_resume"
        and resumed_state.kernel == "grok"
        and resumed_state.session_id == SESSION
        and kernel_is_available(health, "grok") is True
        and len(exhausted_calls) == 2
        and exhausted_calls[0]["full"] == "True"
        and exhausted_calls[1]["full"] == "False"
        and exhausted_calls[1]["decision_only"] == "True"
        and all(item["kernel"] == "grok" for item in exhausted_calls)
        and exhausted_decision.status == "continue"
        and exhausted_meta.get("source") == "decision_only_resume"
        and exhausted_state.kernel == "grok"
        and exhausted_state.session_id == SESSION
        and bool(getattr(exhausted_state, "decision_only_resume", False)) is True
        and MARKER not in follow_up
        and "do not call tools" in follow_up.lower()
        and "Finish the truncated session." in follow_up
        and not bare_decision_only
        and bare_meta.get("source") != "decision_only_resume"
        and bare_decision.status == "continue"
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
