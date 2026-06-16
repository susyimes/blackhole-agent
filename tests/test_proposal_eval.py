from pathlib import Path

from blackhole_agent.proposal_eval import load_proposal_replay_case, run_proposal_replay_case, run_proposal_replay_suite


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "proposal_replay"


def test_proposal_replay_suite_accepts_frozen_harness_cases():
    results = run_proposal_replay_suite(sorted(FIXTURE_DIR.glob("*.json")))

    assert results
    assert all(result.passed for result in results), {
        result.name: result.failures for result in results if not result.passed
    }
    assert {result.name for result in results} == {
        "benign-agent-harness",
        "security-adjacent-context-pressure",
    }


def test_proposal_replay_case_rejects_url_refs_even_when_url_is_allowed_evidence():
    case = load_proposal_replay_case(FIXTURE_DIR / "benign_agent_harness.json")
    case["raw_response"]["proposals"][0]["evidence_refs"] = ["https://github.com/ApodexAI/AgentHarness"]
    case["expected"] = {
        "status": "rejected",
        "accepted_count": 0,
        "rejected_count": 1,
        "rejected_error_substrings": [
            "evidence_refs contain unknown item ids: https://github.com/ApodexAI/AgentHarness"
        ],
    }

    result = run_proposal_replay_case(case)

    assert result.passed is True
    assert result.accepted_count == 0


def test_proposal_replay_case_detects_control_classification_drift():
    case = load_proposal_replay_case(FIXTURE_DIR / "security_adjacent_context_pressure.json")
    case["expected"]["proposal_controls"]["security-boundary-review"]["implementation_scope"] = (
        "local_validation_candidate"
    )

    result = run_proposal_replay_case(case)

    assert result.passed is False
    assert any("expected proposal_controls" in failure for failure in result.failures)
