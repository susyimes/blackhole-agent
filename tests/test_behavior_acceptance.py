import subprocess
import sys

import pytest

from blackhole_agent.behavior_acceptance import replay_behavior_acceptance
from blackhole_agent.unbound import TurnDecision, evaluate_milestone
from tests.test_unbound import init_repository


def fixture(tmp_path, *, value=2, probe=None):
    init_repository(tmp_path)
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    tests = tmp_path / "tests" / "acceptance"
    tests.mkdir(parents=True)
    (tests / "probe.py").write_text(
        probe
        or (
            "import json\nfrom seed import VALUE\n"
            "print(json.dumps({'passed':VALUE == 2, 'observed': {'value':VALUE}}))\n"
        )
    )
    (tmp_path / "src" / "seed.py").write_text(f"VALUE = {value}\n")
    return baseline


def test_same_probe_replayed_on_immutable_baseline_and_candidate(tmp_path):
    baseline = fixture(tmp_path)
    result = replay_behavior_acceptance(tmp_path, baseline, "tests/acceptance/probe.py")
    assert result["ok"], result
    assert result["baseline"]["outcome"]["passed"] is False
    assert result["candidate"]["outcome"]["passed"] is True
    assert len(result["probe_sha256"]) == 64
    assert (tmp_path / "src" / "seed.py").read_text() == "VALUE = 2\n"


@pytest.mark.parametrize("value", [1, 3])
def test_no_improvement_or_wrong_outcome_cannot_pass(tmp_path, value):
    baseline = fixture(tmp_path, value=value)
    assert not replay_behavior_acceptance(tmp_path, baseline, "tests/acceptance/probe.py")["ok"]


@pytest.mark.parametrize(
    "probe",
    [
        "raise RuntimeError('broken test')",
        "print('{}')",
        "print('not-json')",
        "import json; print(json.dumps({'passed':True,'observed':'a ledger flag'}))",
    ],
)
def test_crash_or_always_green_self_assertion_is_not_evidence(tmp_path, probe):
    baseline = fixture(tmp_path, probe=probe)
    result = replay_behavior_acceptance(tmp_path, baseline, "tests/acceptance/probe.py")
    assert not result["ok"] and result.get("error")


def test_timeout_and_outside_probe_are_rejected(tmp_path):
    baseline = fixture(tmp_path, probe="import time; time.sleep(10)")
    assert not replay_behavior_acceptance(tmp_path, baseline, "../probe.py")["ok"]
    assert not replay_behavior_acceptance(tmp_path, baseline, "tests/acceptance/probe.py", timeout=1)["ok"]


def test_autonomous_milestone_retains_acceptance_receipt(tmp_path, monkeypatch):
    baseline = fixture(tmp_path)
    monkeypatch.setattr("blackhole_agent.unbound.run_workspace_goal_watchdog", lambda *a: None)
    payload = {
        "status": "complete",
        "capability_delta": "VALUE behavior repaired",
        "outcome_evidence": ["before/after observed values"],
        "done_when_met": True,
        "validation": [{"command": f'"{sys.executable}" -c "pass"', "exit_code": 0}],
        "acceptance_probe": "tests/acceptance/probe.py",
    }
    gate = evaluate_milestone(
        TurnDecision.from_payload(payload),
        workspace=tmp_path,
        changed_paths=["src/seed.py"],
        autonomous=True,
        baseline_ref=baseline,
        mission_done_when="The seed API returns 2 for the acceptance caller.",
    )
    assert gate.accepted, gate.reasons
    assert any(r["command"] == "controller:behavior-acceptance" and r["ok"] for r in gate.validation_replay)
    missing = evaluate_milestone(
        TurnDecision.from_payload({**payload, "acceptance_probe": ""}),
        workspace=tmp_path,
        changed_paths=["src/seed.py"],
        autonomous=True,
        baseline_ref=baseline,
    )
    assert not missing.accepted
