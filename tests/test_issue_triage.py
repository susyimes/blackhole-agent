import json
from datetime import datetime, timezone

from blackhole_agent.issue_triage import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
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
    assert record.recommendation.labels == ["triaged", PRIORITY_HIGH, "comp:tests"]
    assert record.recommendation.priority == PRIORITY_HIGH
    assert record.recommendation.next_actions == ["run or add focused local validation before source changes"]
    assert record.mutation_plan.mode == "dry_run"
    assert record.mutation_plan.allowed is False
    assert record.mutation_plan.commands == []

    path = write_issue_triage_record(record, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["created_at"] == "2026-06-17T06:03:15Z"
    assert payload["lane"] == TRIAGE_VALIDATION
    assert payload["rationale"] == record.rationale
    assert payload["recommendation"]["labels"] == ["triaged", PRIORITY_HIGH, "comp:tests"]
    assert payload["mutation_plan"]["mode"] == "dry_run"
    assert payload["mutation_plan"]["commands"] == []
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
    assert record.recommendation.labels == ["triaged", "P3-low", "comp:runtime", "needs-info"]
    assert record.mutation_plan.commands == []


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
    assert record.recommendation.labels == ["triaged", "P3-low", "comp:security"]
    assert record.recommendation.next_actions == [
        "leave remote state unchanged unless a human confirms the no-action classification"
    ]
    assert record.mutation_plan.mode == "dry_run"


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
    assert record.recommendation.labels == ["needs-info"]
    assert record.mutation_plan.mode == "dry_run"
    assert record.rollback is not None
    assert record.rollback.recovery_commands[0] == "git reset --hard abc123"

    path = write_issue_triage_record(record, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["unsupported_shape"] is True
    assert payload["rollback"]["original_head"] == "abc123"
    assert payload["rollback"]["artifact_path"] == "artifacts/rollback/test.txt"


def test_issue_triage_remote_mutation_requires_controller_approval():
    issue = {
        "title": "Critical startup regression leaks token diagnostics",
        "body": "The supervisor startup fails and may expose a credential in provider config logs.",
        "html_url": "https://github.com/example/repo/issues/17",
    }

    dry_run = triage_issue_input(issue, now=FIXED_NOW)
    assert dry_run.recommendation.labels == ["triaged", PRIORITY_CRITICAL, "comp:security"]
    assert dry_run.mutation_plan.mode == "dry_run"
    assert dry_run.mutation_plan.allowed is False
    assert dry_run.mutation_plan.commands == []

    approved = triage_issue_input(issue, allow_remote_mutation=True, now=FIXED_NOW)
    assert approved.mutation_plan.mode == "approved_plan"
    assert approved.mutation_plan.allowed is True
    assert approved.mutation_plan.commands == [
        ["gh", "issue", "edit", "https://github.com/example/repo/issues/17", "--remove-label", "needs-triage"],
        [
            "gh",
            "issue",
            "edit",
            "https://github.com/example/repo/issues/17",
            "--add-label",
            "triaged,P0-critical,comp:security",
        ],
    ]


def test_issue_triage_duplicate_comment_is_only_planned_after_approval():
    issue = {
        "title": "Duplicate of #42",
        "body": "Duplicate of #42 for provider restart issue.",
        "html_url": "https://github.com/example/repo/issues/43",
    }

    dry_run = triage_issue_input(issue, now=FIXED_NOW)
    assert dry_run.recommendation.duplicate_of == 42
    assert "duplicate" in dry_run.recommendation.labels
    assert dry_run.mutation_plan.commands == []

    approved = triage_issue_input(issue, allow_remote_mutation=True, now=FIXED_NOW)
    assert approved.mutation_plan.commands[-1] == [
        "gh",
        "issue",
        "comment",
        "https://github.com/example/repo/issues/43",
        "--body",
        "Possible duplicate of #42.",
    ]
