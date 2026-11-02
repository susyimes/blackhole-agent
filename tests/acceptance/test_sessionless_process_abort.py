"""A Kimi all-ones exit after a tool result continues without a session.

Harvested 2026-07-31 run 20260731T102420Z exited 4294967295 with timed_out
false, an empty last message, no resume flag, and a tool-result record in
stdout. That death stayed a retryable CLI error, so the next resolution
replayed the mission prompt.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

MARKER = "FULL_MISSION_PROMPT_MARKER"
FULL_PROMPT = MARKER + " mission body that must not be replayed after a sessionless abort."
KIMI_ERROR = (
    "Kimi CLI failed with exit code 4294967295; "
    "result details were written to latest-kimi-run.json."
)
TOOL_RESULT = (
    '{"role":"tool","tool_call_id":"tool_1FCbhacfvBuQt0pEYfZwgckE",'
    '"content":"structural identity alliance vs pact: 1028/2306 = 44.6%"}'
)
HARVESTED_DEATH = {
    "returncode": 4294967295,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": TOOL_RESULT,
    "stderr_tail": "def builtin_federation_plane() -> dict[str, Any]:",
    "session_id": "",
    "command": [
        "node.EXE",
        "main.mjs",
        "--output-format",
        "stream-json",
        "--prompt",
        "task.md",
    ],
}
MENTION_ONLY = {
    "returncode": 4294967295,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "tool output that is not a session",
    "stderr_tail": "",
    "session_id": "",
    "command": ["kimi", "--prompt", "task.md"],
}
EXIT_ONE = {
    "returncode": 1,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": TOOL_RESULT,
    "stderr_tail": "",
    "session_id": "",
    "command": ["node.EXE", "main.mjs", "--prompt", "task.md"],
}
RESUMED_GROK = {
    "returncode": 4294967295,
    "timed_out": False,
    "last_message": "",
    "stdout_tail": "",
    "stderr_tail": "extract_initial_tokens warning\n",
    "session_id": "",
    "command": ["grok.EXE", "--resume", "b3c94acc-389f-43e5-ad01-34ad7502e679"],
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
        mission_id="sessionless-process-abort-probe",
        created_at="2026-07-31T10:24:20Z",
        updated_at="2026-07-31T10:24:20Z",
        repo_path=str(repo),
        workspace_path=str(repo),
        branch="probe",
        target_branch="main",
        goal="Continue Kimi after Windows records exit 4294967295 with a tool result and no session.",
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
                "continuation": str(
                    "4294967295" in text and "No session id was recorded" in text and MARKER not in text
                ),
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
    from blackhole_agent.kernel_salvage import classify_run_artifact, salvage_kernel_failure

    death = classify_run_artifact(HARVESTED_DEATH, error=KIMI_ERROR)
    mention = classify_run_artifact(MENTION_ONLY, error=KIMI_ERROR)
    exit_one = classify_run_artifact(EXIT_ONE, error="Kimi CLI failed with exit code 1")
    resumed = classify_run_artifact(RESUMED_GROK, error="Grok CLI failed with exit code 4294967295")
    salvaged = salvage_kernel_failure(
        error=KIMI_ERROR,
        current_kernel="kimi",
        artifact=HARVESTED_DEATH,
        installed_kernels={"kimi", "codex"},
        allow_failover=True,
    )
    continued_calls, continued_decision, continued_meta, continued_state, health_after = _run(
        "sessionless-abort-continue-",
        HARVESTED_DEATH,
        succeed_on_short=True,
    )
    exhausted_calls, exhausted_decision, exhausted_meta, exhausted_state, health_after_exhaustion = _run(
        "sessionless-abort-exhaust-",
        HARVESTED_DEATH,
        succeed_on_short=False,
    )
    short_continues = [
        item
        for item in continued_calls
        if item["kernel"] == "kimi" and item["full"] == "False" and item["continuation"] == "True"
    ]
    breaker = (
        health_after_exhaustion.kernels.get("kimi")
        if isinstance(getattr(health_after_exhaustion, "kernels", None), dict)
        else None
    )
    circuit_class = str(getattr(breaker, "class_id", "") or "")
    observed = {
        "death_class": death.class_id,
        "death_retryable": death.retryable,
        "mention_class": mention.class_id,
        "mention_retryable": mention.retryable,
        "exit_one_class": exit_one.class_id,
        "exit_one_retryable": exit_one.retryable,
        "resumed_grok_class": resumed.class_id,
        "salvage_status": salvaged.decision.get("status"),
        "salvage_summary": salvaged.decision.get("summary"),
        "salvage_class": salvaged.class_id,
        "continued_calls": continued_calls,
        "continued_status": continued_decision.status,
        "continued_summary": continued_decision.summary,
        "continued_source": continued_meta.get("source"),
        "continued_kernel": continued_state.kernel,
        "continued_session": continued_state.session_id,
        "kimi_available_after_continue": kernel_is_available(health_after, "kimi"),
        "exhausted_calls": exhausted_calls,
        "exhausted_status": exhausted_decision.status,
        "exhausted_source": exhausted_meta.get("source"),
        "exhausted_kernel": exhausted_state.kernel,
        "kimi_available_after_exhaustion": kernel_is_available(health_after_exhaustion, "kimi"),
        "circuit_after_exhaustion": circuit_class,
    }
    passed = bool(
        death.class_id == "sessionless_process_abort"
        and death.retryable is False
        and mention.class_id == "cli_error"
        and mention.retryable is True
        and exit_one.class_id == "cli_error"
        and exit_one.retryable is True
        and resumed.class_id == "abnormal_process_exit"
        and salvaged.class_id == "sessionless_process_abort"
        and salvaged.decision.get("status") == "continue"
        and "not replayed" in str(salvaged.decision.get("summary") or "")
        and len(continued_calls) == 2
        and continued_calls[0]["kernel"] == "kimi"
        and continued_calls[0]["full"] == "True"
        and continued_calls[0]["session"] == ""
        and len(short_continues) == 1
        and short_continues[0]["session"] == ""
        and short_continues[0]["started"] == "False"
        and continued_decision.status == "continue"
        and continued_decision.summary == "continued"
        and continued_meta.get("source") == "sessionless_abort_continue"
        and continued_state.kernel == "kimi"
        and continued_state.session_id == ""
        and kernel_is_available(health_after, "kimi") is True
        and len(exhausted_calls) == 3
        and exhausted_calls[0]["kernel"] == "kimi"
        and exhausted_calls[0]["full"] == "True"
        and exhausted_calls[1]["kernel"] == "kimi"
        and exhausted_calls[1]["continuation"] == "True"
        and exhausted_calls[2]["kernel"] == "codex"
        and exhausted_calls[2]["full"] == "True"
        and exhausted_decision.status == "continue"
        and exhausted_decision.summary == "other kernel"
        and exhausted_meta.get("source") == "failover"
        and exhausted_state.kernel == "codex"
        and kernel_is_available(health_after_exhaustion, "kimi") is True
        and circuit_class not in {"auth_failed", "sessionless_process_abort"}
    )
    return passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
