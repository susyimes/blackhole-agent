"""Outcome probe: paperwork-only milestone requests are declined at intake.

Baseline controllers route a docs/tests-only milestone request into the
milestone gate as a requested-but-rejected milestone, which is exactly the
recurring ``paperwork_milestone`` failure class. The repaired controller
declines the request at decision intake instead: the gate reports
``requested=False`` with ``auto_declined=True``, so the turn continues and no
failure-class occurrence can be recorded. A request backed by a real
behavior-path delta must still reach the gate and be accepted.
"""

from __future__ import annotations

import json

from blackhole_agent.unbound import TurnDecision, evaluate_milestone


def _decision() -> TurnDecision:
    return TurnDecision.from_payload(
        {
            "status": "milestone",
            "summary": "probe decision",
            "strategy": "direct",
            "next_step": "none",
            "capability_delta": "Probe-visible delta.",
            "outcome_evidence": ["probe observation"],
            "validation": [
                {"command": "git rev-parse --verify HEAD", "exit_code": 0, "summary": "head resolves"}
            ],
            "done_when_met": False,
            "commit_message": "",
            "mission_goal": "",
            "done_when": "",
        }
    )


def main() -> None:
    paperwork = evaluate_milestone(
        _decision(), changed_paths=["docs/guide.md", "tests/test_probe.py"]
    )
    behavior = evaluate_milestone(
        _decision(), changed_paths=["src/blackhole_agent/unbound.py"]
    )
    observed = {
        "paperwork": {
            "requested": paperwork.requested,
            "accepted": paperwork.accepted,
            "auto_declined": getattr(paperwork, "auto_declined", False),
            "reasons": list(paperwork.reasons),
        },
        "behavior": {
            "requested": behavior.requested,
            "accepted": behavior.accepted,
            "auto_declined": getattr(behavior, "auto_declined", False),
        },
    }
    passed = (
        observed["paperwork"]["requested"] is False
        and observed["paperwork"]["accepted"] is False
        and observed["paperwork"]["auto_declined"] is True
        and observed["behavior"]["requested"] is True
        and observed["behavior"]["accepted"] is True
    )
    print(json.dumps({"passed": bool(passed), "observed": observed}))


if __name__ == "__main__":
    main()
