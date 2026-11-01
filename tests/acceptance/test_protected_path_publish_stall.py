"""Outcome probe: a protected-path refusal releases the pending publish.

Harvested continuous-loop publications from 2026-08-17 through 2026-08-22
retried commit e7b754131c475cdb13012f16f8b29f212125fd56 222 times after
"protected paths require operator acknowledgment" for experience_fuel.py.
That refusal must clear the pending publish. A DNS failure and a connect
failure must keep it. The path stays blocked unless an operator acknowledges
it. The previous milestone keeps the pending publish, so this probe reports
passed=false there. Both outcomes exit 0.
"""

from __future__ import annotations

import json

HARVESTED_SHA = "e7b754131c475cdb13012f16f8b29f212125fd56"
HARVESTED_MISSION = "20260817T150703Z-4f1451c3"
PROTECTED = "src/blackhole_agent/experience_fuel.py"
DNS = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "Could not resolve host: github.com"
)
CONNECT = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "Failed to connect to github.com port 443 after 21097 ms: Could not connect to server"
)


def _state() -> dict[str, str]:
    return {
        "pending_publish_ref": HARVESTED_SHA,
        "pending_publish_mission_id": HARVESTED_MISSION,
        "last_publish_error": "",
    }


def main() -> None:
    from blackhole_agent.protected_paths import evaluate_protected_paths_gate
    from blackhole_agent.publication_resilience import apply_publication_failure

    verdict = evaluate_protected_paths_gate((PROTECTED,), operator_acknowledged=False)
    error = verdict.reason
    if verdict.touched:
        error = f"{error}: {', '.join(verdict.touched)}"
    refused = _state()
    apply_publication_failure(refused, error)
    dns = _state()
    apply_publication_failure(dns, DNS)
    connect = _state()
    apply_publication_failure(connect, CONNECT)
    acknowledged = evaluate_protected_paths_gate((PROTECTED,), operator_acknowledged=True)
    passed = (
        verdict.blocked is True
        and verdict.operator_acknowledged is False
        and PROTECTED in verdict.touched
        and error.startswith("protected paths require operator acknowledgment")
        and refused["pending_publish_ref"] == ""
        and refused["pending_publish_mission_id"] == ""
        and "protected paths require operator acknowledgment" in refused["last_publish_error"].lower()
        and dns["pending_publish_ref"] == HARVESTED_SHA
        and dns["pending_publish_mission_id"] == HARVESTED_MISSION
        and connect["pending_publish_ref"] == HARVESTED_SHA
        and connect["pending_publish_mission_id"] == HARVESTED_MISSION
        and acknowledged.blocked is False
        and acknowledged.operator_acknowledged is True
    )
    observed = {
        "refusal": error,
        "pending_after_refusal": refused["pending_publish_ref"],
        "mission_after_refusal": refused["pending_publish_mission_id"],
        "recorded_error": refused["last_publish_error"],
        "pending_after_dns": dns["pending_publish_ref"],
        "pending_after_connect": connect["pending_publish_ref"],
        "gate_blocked": verdict.blocked,
        "acknowledged_blocked": acknowledged.blocked,
        "loop_would_sleep_publish_retry": bool(refused["pending_publish_ref"]),
    }
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
