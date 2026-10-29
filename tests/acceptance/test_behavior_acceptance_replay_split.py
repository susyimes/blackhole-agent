"""A failed before/after probe is not a validation command replay.

Harvested milestone rejections from 2026-09-11 through 2026-10-11 recorded
``validation replay failed: controller:behavior-acceptance reported exit 0
but controller replay got exit None`` beside a real behavior-acceptance
failure. This probe prints passed true only when that synthetic reason is
absent, the behavior-acceptance failure remains, a command that replays
with exit 1 is still rejected, and the acceptance failure alone is not
classified as validation_replay_failed.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.pattern_register import classify_unbound_turn
from blackhole_agent.unbound import TurnDecision, evaluate_milestone

HARVESTED_ACCEPTANCE_ERROR = (
    "the same probe must show baseline passed=false and candidate passed=true"
)


def _runner(exit_code: int):
    def runner(command, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(command, exit_code, stdout="[]\n", stderr="")

    return runner


def _gate(exit_code: int):
    import blackhole_agent.unbound as unbound

    unbound.replay_behavior_acceptance = (
        lambda workspace, baseline_ref, probe_path, **kwargs: {
            "ok": False,
            "error": HARVESTED_ACCEPTANCE_ERROR,
            "baseline_ref": baseline_ref,
            "probe": probe_path,
        }
    )
    workspace = Path(tempfile.mkdtemp(prefix="bh-replay-split-"))
    source = workspace / "src"
    source.mkdir(parents=True)
    (source / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    decision = TurnDecision.from_payload(
        {
            "status": "milestone",
            "capability_delta": "separate behavior acceptance from command replay",
            "outcome_evidence": ["gate reasons"],
            "validation": [{"command": "python -c \"print('ok')\"", "exit_code": 0}],
            "acceptance_probe": "tests/acceptance/test_behavior_acceptance_replay_split.py",
        }
    )
    return evaluate_milestone(
        decision,
        workspace=workspace,
        changed_paths=["src/seed.py"],
        autonomous=True,
        baseline_ref="HEAD",
        command_runner=_runner(exit_code),
    )


def main() -> None:
    passing_command = _gate(0)
    failing_command = _gate(1)
    passing_reasons = [str(reason) for reason in passing_command.reasons]
    failing_reasons = [str(reason) for reason in failing_command.reasons]
    synthetic = [
        reason
        for reason in passing_reasons
        if "validation replay failed" in reason and "controller:behavior-acceptance" in reason
    ]
    acceptance_failure = any(
        reason.startswith("behavior acceptance failed") and HARVESTED_ACCEPTANCE_ERROR in reason
        for reason in passing_reasons
    )
    real_replay = any(
        reason.startswith("validation replay failed")
        and "exit 1" in reason
        and "controller:behavior-acceptance" not in reason
        for reason in failing_reasons
    )
    events = classify_unbound_turn(
        {
            "iteration": 1,
            "milestone_gate": {
                "requested": True,
                "accepted": False,
                "reasons": passing_reasons,
            },
        }
    )
    class_id = str(events[0]["class_id"]) if events else ""
    passed = (
        not synthetic
        and acceptance_failure
        and real_replay
        and class_id != "validation_replay_failed"
        and passing_command.accepted is False
        and failing_command.accepted is False
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "observed": {
                    "acceptance_failure": acceptance_failure,
                    "synthetic_replay_reasons": synthetic,
                    "acceptance_only_class": class_id,
                    "passing_command_reasons": passing_reasons,
                    "failing_command_reasons": failing_reasons,
                    "passing_command_accepted": passing_command.accepted,
                    "failing_command_accepted": failing_command.accepted,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
