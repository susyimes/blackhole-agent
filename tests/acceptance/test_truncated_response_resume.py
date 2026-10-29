"""A Grok reply truncated by max_tokens must not replay the mission prompt.

The harvested 2026-09-04 run exited 1 after 37 model calls with
error_kind max_tokens_truncation and "response truncated by max_tokens".
The session id was 93715a1d-ec3d-40be-b69f-dd95c6b63e85. That death stayed a
retryable CLI error, so the next launch sent the same full mission prompt.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

SESSION = "93715a1d-ec3d-40be-b69f-dd95c6b63e85"
MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed after truncation."
HARVESTED_TRUNCATION = {
    "returncode": 1,
    "timed_out": False,
    "last_message": (
        'Internal error: {\n  "message": "response truncated by max_tokens",\n'
        '  "error_kind": "max_tokens_truncation"\n}'
    ),
    "stdout_tail": (
        '{"type":"error","message":"Internal error: {\\n  \\"message\\": '
        '\\"response truncated by max_tokens\\",\\n  \\"error_kind\\": '
        '\\"max_tokens_truncation\\"\\n}"}'
    ),
    "stderr_tail": (
        "ERROR error=Internal error: {\n"
        '  "message": "response truncated by max_tokens",\n'
        '  "error_kind": "max_tokens_truncation"\n}'
    ),
    "command": ["grok", "--session-id", SESSION, "--prompt-file", "task.md"],
}
GROK_ERROR = "Grok CLI failed with exit code 1; result details were written to latest-grok-run.json."


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
    from blackhole_agent.unbound import KernelTurnResult, UnboundMission, build_turn_prompt

    harvested = classify_run_artifact(HARVESTED_TRUNCATION, error=GROK_ERROR)
    bare_truncated = classify_kernel_failure(
        returncode=1,
        stderr_tail="warning: output was truncated in an unrelated log",
        session_id=SESSION,
        error=GROK_ERROR,
    )
    quoted_success = classify_kernel_failure(
        returncode=0,
        last_message=(
            "notes mention response truncated by max_tokens and "
            "error_kind max_tokens_truncation as an example"
        ),
    )

    def mission(repo: Path) -> UnboundMission:
        return UnboundMission(
            schema_version=1,
            mission_id="truncated-probe",
            created_at="2026-09-04T06:33:38Z",
            updated_at="2026-09-04T06:33:38Z",
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

    def runner(calls: list[dict[str, str]], *, succeed_on_short: bool):
        def run(state, prompt, turn_dir, **kwargs):
            del kwargs
            text = str(prompt)
            calls.append(
                {
                    "kernel": str(state.kernel),
                    "session": str(getattr(state, "session_id", "") or ""),
                    "started": str(bool(getattr(state, "session_started", False))),
                    "full": str(MARKER in text),
                    "prompt": text[:240],
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
            (kernel_dir / "latest-grok-run.json").write_text(
                json.dumps(HARVESTED_TRUNCATION),
                encoding="utf-8",
            )
            if state.kernel != "grok":
                (kernel_dir / f"latest-{state.kernel}-run.json").write_text(
                    json.dumps(HARVESTED_TRUNCATION),
                    encoding="utf-8",
                )
            raise RuntimeError(GROK_ERROR)

        return run

    def local_action(state, workspace):
        del state, workspace
        return {"status": "continue", "summary": "local tick"}

    with tempfile.TemporaryDirectory(prefix="truncated-resume-") as tmp:
        repo = Path(tmp)
        resumed_calls: list[dict[str, str]] = []
        resumed_state = mission(repo)
        _resumed_result, resumed_decision, resumed_meta = execute_kernel_turn_with_salvage(
            resumed_state,
            FULL_PROMPT,
            repo / "turn-resume",
            kernel_runner=runner(resumed_calls, succeed_on_short=True),
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
            kernel_runner=runner(exhausted_calls, succeed_on_short=False),
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

    full_replays = [item for item in exhausted_calls if item["full"] == "True"]
    short_resumes = [
        item for item in resumed_calls if item["kernel"] == "grok" and item["full"] == "False"
    ]
    observed = {
        "harvested_class": harvested.class_id,
        "harvested_retryable": harvested.retryable,
        "bare_class": bare_truncated.class_id,
        "bare_retryable": bare_truncated.retryable,
        "quoted_class": quoted_success.class_id,
        "resumed_calls": resumed_calls,
        "resumed_status": resumed_decision.status,
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
        "full_replay_count": len(full_replays),
    }
    passed = bool(
        harvested.class_id == "output_truncated"
        and harvested.retryable is False
        and bare_truncated.class_id == "cli_error"
        and bare_truncated.retryable is True
        and quoted_success.class_id != "output_truncated"
        and len(resumed_calls) == 2
        and resumed_calls[0]["kernel"] == "grok"
        and resumed_calls[0]["full"] == "True"
        and len(short_resumes) == 1
        and short_resumes[0]["session"] == SESSION
        and short_resumes[0]["started"] == "True"
        and resumed_decision.status == "continue"
        and resumed_decision.summary == "decision only"
        and resumed_meta.get("source") == "decision_only_resume"
        and resumed_state.kernel == "grok"
        and resumed_state.session_id == SESSION
        and kernel_is_available(health, "grok") is True
        and len(full_replays) == 1
        and all(item["kernel"] == "grok" for item in exhausted_calls)
        and exhausted_decision.status == "continue"
        and exhausted_meta.get("source") == "decision_only_resume"
        and exhausted_state.kernel == "grok"
        and exhausted_state.session_id == SESSION
        and bool(getattr(exhausted_state, "decision_only_resume", False)) is True
        and MARKER not in follow_up
        and "do not call tools" in follow_up.lower()
        and "Finish the truncated session." in follow_up
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
