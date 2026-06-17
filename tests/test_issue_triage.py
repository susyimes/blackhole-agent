import json
from datetime import datetime, timezone

from blackhole_agent.issue_triage import (
    TRIAGE_FOLLOW_UP,
    TRIAGE_NO_ACTION,
    TRIAGE_VALIDATION,
    IssueTriageRollback,
    triage_issue_input,
    write_issue_triage_record,
)


FIXED_NOW = datetime(2026, 6, 17, 6, 3, 15, tzinfo=timezone.utc)


def rollback_context() -> IssueTriageRollback:
    return IssueTriageRollback(
        original_branch="codex/blackhole-evolve/test",
        original_head="abc123",
        rollback_ref="refs/rollback/test",
        artifact_path="artifacts/rollback/test.txt",
        recovery_commands=["git reset --hard abc123", "git clean -fd", "git switch codex/blackhole-evolve/test"],
    )


def test_issue_triage_routes_validation_inputs_and_persists_rationale(tmp_path):
    record = triage_issue_input(
        {
            "title": "Regression in trend scoring",
            "body": "Please add a focused test because the digest route fails on review signals.",
            "html_url": "https://github.com/example/repo/issues/7",
        },
        rollback=rollback_context(),
        now=FIXED_NOW,
    )

    assert record.lane == TRIAGE_VALIDATION
    assert record.validation_task.startswith("Create or run a focused local validation check")
    assert record.follow_up_prompt == ""
    assert record.rationale == ["issue text contains validation-oriented terms that can map to a local check"]

    path = write_issue_triage_record(record, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["created_at"] == "2026-06-17T06:03:15Z"
    assert payload["lane"] == TRIAGE_VALIDATION
    assert payload["rationale"] == record.rationale
    assert payload["rollback"]["rollback_ref"] == "refs/rollback/test"


def test_issue_triage_routes_follow_up_inputs_without_validation_task():
    record = triage_issue_input(
        {
            "title": "Should scheduler expose child status?",
            "body": "Would it make sense to show child sessions in the heartbeat?",
        },
        now=FIXED_NOW,
    )

    assert record.lane == TRIAGE_FOLLOW_UP
    assert record.validation_task == ""
    assert "reproduction steps" in record.follow_up_prompt
    assert record.unsupported_shape is False


def test_issue_triage_routes_no_action_inputs():
    record = triage_issue_input(
        {
            "title": "Duplicate: provider token preflight",
            "body": "This is a duplicate of the existing provider config issue.",
            "state": "open",
        },
        now=FIXED_NOW,
    )

    assert record.lane == TRIAGE_NO_ACTION
    assert record.validation_task == ""
    assert record.follow_up_prompt == ""
    assert "duplicate" in record.rationale[0]


def test_issue_triage_unsupported_shapes_keep_rollback_metadata_for_recovery(tmp_path):
    record = triage_issue_input(
        ["not", "an", "issue"],
        rollback=rollback_context(),
        now=FIXED_NOW,
    )

    assert record.lane == TRIAGE_NO_ACTION
    assert record.unsupported_shape is True
    assert record.validation_task == ""
    assert "unsupported" in record.rationale[0]
    assert record.rollback is not None
    assert record.rollback.recovery_commands[0] == "git reset --hard abc123"

    path = write_issue_triage_record(record, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["unsupported_shape"] is True
    assert payload["rollback"]["original_head"] == "abc123"
    assert payload["rollback"]["artifact_path"] == "artifacts/rollback/test.txt"
