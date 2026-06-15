import hashlib
import json
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from blackhole_agent.github_growth import (
    GitHubEventsClient,
    GitHubTrendConfig,
    GitHubTrendSearchResult,
    GrowthMemory,
    GrowthSignal,
    GrowthState,
    TrendingRepository,
    app,
    build_digest,
    build_proposals,
    build_replayable_validation_report,
    build_self_evolution_plan,
    build_trending_repository_query_for_date,
    extract_growth_signals,
    normalize_event,
    prepare_self_evolution_branch,
    proposal_manifest_control,
    render_markdown_digest,
    run_intake_once,
    run_self_evolution_codex,
    select_new_events,
    synthesize_digest_proposals,
    trend_repository_to_event,
)
from blackhole_agent.persona import PERSONA_VERSION, render_persona_layer
from blackhole_agent.proposal_synthesis import build_proposal_evidence_package, review_llm_proposal_response
from blackhole_agent.self_model import (
    BOOTSTRAP_SELF_MODEL,
    DEFAULT_SELF_MODEL_PATH,
    read_self_model_snapshot,
)


def event_payload(event_id: str, kind: str, title: str, *, created_at: str | None = None) -> dict:
    created_at = created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    payload = {}
    if kind == "PullRequestEvent":
        payload = {
            "action": "opened",
            "pull_request": {
                "title": title,
                "html_url": "https://github.com/example/repo/pull/1",
            },
        }
    elif kind == "PushEvent":
        payload = {
            "ref": "refs/heads/main",
            "commits": [
                {
                    "sha": "abc123456789",
                    "message": title,
                }
            ],
        }
    return {
        "id": event_id,
        "type": kind,
        "actor": {"login": "octocat"},
        "created_at": created_at,
        "payload": payload,
    }


class FakeResponse:
    status_code = 200

    def __init__(self, payload: object, *, links: dict | None = None) -> None:
        self._payload = payload
        self.links = links or {}

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, payload: list[dict]) -> None:
        self.payload = payload
        self.requests: list[dict] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return FakeResponse(self.payload)


class PagedFakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[dict] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected extra request")
        return self.responses.pop(0)


class FakeEventsClient:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.per_page_values: list[int] = []

    def list_repository_events(self, repo: str, *, per_page: int = 100) -> list[dict]:
        self.per_page_values.append(per_page)
        return self.events


class FakeTrendClient:
    def __init__(self, result: GitHubTrendSearchResult, *, failed_repos: set[str] | None = None) -> None:
        self.result = result
        self.failed_repos = failed_repos or set()
        self.event_repo_calls: list[str] = []

    def search_trending_repositories(self, config: GitHubTrendConfig) -> GitHubTrendSearchResult:
        return self.result

    def list_repository_events(self, repo: str, *, per_page: int = 100) -> list[dict]:
        self.event_repo_calls.append(repo)
        if repo in self.failed_repos:
            raise RuntimeError(f"GitHub events request failed for {repo}: HTTP 403")
        return []


def trend_repository(*, stars: int = 125) -> TrendingRepository:
    return TrendingRepository(
        full_name="example/trend-agent",
        html_url="https://github.com/example/trend-agent",
        description="A useful agent workflow project",
        language="Python",
        stargazers_count=stars,
        forks_count=12,
        open_issues_count=3,
        created_at="2026-06-10T00:00:00Z",
        updated_at="2026-06-13T00:00:00Z",
        pushed_at="2026-06-13T00:00:00Z",
        topics=["agent", "workflow"],
    )


def digest_with_proposal() -> dict:
    return {
        "digest_id": "github-growth-20260612T000000Z",
        "generated_at": "2026-06-12T00:00:00Z",
        "repositories": ["example/repo"],
        "items": [],
        "proposals": [
            {
                "proposal_id": "p1",
                "kind": "test",
                "summary": "Borrow cautiously from example/repo: Improve agent workflow tests.",
                "evidence_urls": ["https://github.com/example/repo/pull/1"],
                "requires_approval": False,
            }
        ],
    }


def test_normalize_pull_request_event_extracts_reviewable_text():
    event = normalize_event(
        "example/repo",
        event_payload("1", "PullRequestEvent", "Add agent workflow benchmark"),
    )

    assert event.title == "opened pull request: Add agent workflow benchmark"
    assert event.url == "https://github.com/example/repo/pull/1"
    assert event.actor == "octocat"


def test_github_events_client_follows_paginated_event_links():
    session = PagedFakeSession(
        [
            FakeResponse(
                [event_payload("first-page", "PushEvent", "workflow one")],
                links={"next": {"url": "https://api.example.test/page/2"}},
            ),
            FakeResponse([event_payload("second-page", "PushEvent", "workflow two")]),
        ]
    )
    client = GitHubEventsClient(session=session, api_base_url="https://api.example.test")

    events = client.list_repository_events("example/repo", per_page=50)

    assert [event["id"] for event in events] == ["first-page", "second-page"]
    assert session.requests[0]["params"] == {"per_page": 50}
    assert session.requests[1]["url"] == "https://api.example.test/page/2"
    assert session.requests[1]["params"] is None


def test_build_trending_repository_query_adds_recent_stars_and_fork_filters():
    query = build_trending_repository_query_for_date(
        GitHubTrendConfig(query="language:Python topic:agents", window_days=7, min_stars=25),
        created_since=date(2026, 6, 1),
    )

    assert query == "language:Python topic:agents created:>=2026-06-01 stars:>=25 fork:false"


def test_github_events_client_searches_trending_repositories():
    payload = {
        "total_count": 42,
        "incomplete_results": False,
        "items": [
            {
                "full_name": "example/trend-agent",
                "html_url": "https://github.com/example/trend-agent",
                "description": "A useful agent workflow project",
                "language": "Python",
                "stargazers_count": 125,
                "forks_count": 12,
                "open_issues_count": 3,
                "created_at": "2026-06-10T00:00:00Z",
                "updated_at": "2026-06-13T00:00:00Z",
                "pushed_at": "2026-06-13T00:00:00Z",
                "topics": ["agent", "workflow"],
            }
        ],
    }
    session = FakeSession(payload)
    client = GitHubEventsClient(session=session, api_base_url="https://api.example.test")

    result = client.search_trending_repositories(
        GitHubTrendConfig(query="language:Python", window_days=3, min_stars=20, limit=5),
        now=datetime(2026, 6, 13, tzinfo=timezone.utc),
    )

    assert session.requests[0]["url"] == "https://api.example.test/search/repositories"
    assert session.requests[0]["params"] == {
        "q": "language:Python created:>=2026-06-10 stars:>=20 fork:false",
        "sort": "stars",
        "order": "desc",
        "per_page": 5,
    }
    assert result.total_count == 42
    assert result.repositories[0].full_name == "example/trend-agent"
    assert result.repositories[0].stargazers_count == 125


def test_select_new_events_uses_state_and_lookback_window():
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    recent = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state = GrowthState(seen_event_ids={"seen"}, last_seen_at_by_repo={})
    selected = select_new_events(
        "example/repo",
        [
            event_payload("seen", "PushEvent", "test already seen", created_at=recent),
            event_payload("old", "PushEvent", "test old", created_at=old),
            event_payload("new", "PushEvent", "test new workflow", created_at=recent),
        ],
        state,
        lookback_hours=1,
        max_events=10,
    )

    assert [event.id for event in selected] == ["new"]


def test_select_new_events_keeps_unseen_events_with_same_cursor_timestamp():
    cursor = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state = GrowthState(seen_event_ids=set(), last_seen_at_by_repo={"example/repo": cursor})
    selected = select_new_events(
        "example/repo",
        [event_payload("same-second", "PushEvent", "workflow update", created_at=cursor)],
        state,
        lookback_hours=1,
        max_events=10,
    )

    assert [event.id for event in selected] == ["same-second"]


def test_extract_growth_signals_flags_security_for_review():
    event = normalize_event(
        "example/repo",
        event_payload("2", "PushEvent", "security token handling tests"),
    )
    signals = extract_growth_signals([event], topics=["security", "workflow"])

    assert len(signals) == 1
    assert signals[0].risk_flags == ["security", "token"]
    assert "rollback-backed validation" in signals[0].recommended_action


def test_extract_growth_signals_flags_remote_execution_sandboxes_for_review():
    event = normalize_event(
        "example/repo",
        {
            "id": "k8s-runner",
            "type": "IssuesEvent",
            "actor": {"login": "octocat"},
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {
                "action": "opened",
                "issue": {
                    "title": "Feature request: Kubernetes sandbox launcher",
                    "html_url": "https://github.com/example/repo/issues/39",
                    "body": "Launch runner Pods with RBAC and a service account in a K8s cluster.",
                },
            },
        },
    )

    signals = extract_growth_signals([event], topics=["workflow"])

    assert len(signals) == 1
    assert signals[0].risk_flags == ["remote-execution"]
    assert signals[0].recommended_action == "summarize the risk pattern and require rollback-backed validation before borrowing it"


def test_tool_dispatch_gaps_record_capability_requirement_without_enabling_runners(tmp_path):
    event = normalize_event(
        "omnigent-ai/omnigent",
        {
            "id": "web-search-gap",
            "type": "IssuesEvent",
            "actor": {"login": "wildcard"},
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {
                "action": "opened",
                "issue": {
                    "title": "web_search is non-functional on non-OpenAI models",
                    "html_url": "https://github.com/omnigent-ai/omnigent/issues/53",
                    "body": (
                        "The web_search builtin reaches the runner dispatch table with no handler and returns "
                        "Error: web_search not in local dispatch table for provider-backed models."
                    ),
                },
            },
        },
    )

    signals = extract_growth_signals([event], topics=["agent"])
    proposal = build_proposals(signals)[0]
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-web-search-gap",
            "generated_at": "2026-06-14T13:09:24Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )

    assert signals[0].risk_flags == ["capability-requirement", "remote-execution"]
    assert signals[0].recommended_action == (
        "record the capability requirement and require rollback-backed validation before borrowing runner behavior"
    )
    assert proposal["kind"] == "follow_up_issue"
    assert "capability requirement" in proposal["validation_task"]
    assert "does not enable new runners, sandboxes, cluster access, or remote execution" in proposal["validation_task"]
    assert plan is not None
    assert "Validation task: " in plan.task
    assert "does not enable new runners, sandboxes, cluster access, or remote execution" in plan.task


def test_extract_growth_signals_flags_agent_governance_controls_for_validation():
    event = normalize_event(
        "example/repo",
        event_payload("governance", "PushEvent", "agent policy gates for spend and tool access"),
    )

    signals = extract_growth_signals([event], topics=["agent"])

    assert len(signals) == 1
    assert signals[0].risk_flags == ["governance-control"]
    assert signals[0].recommended_action == (
        "summarize the control pattern and require a local validation task before borrowing agent governance behavior"
    )
    proposal = build_proposals(signals)[0]
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "reviewable_proposal_only"
    assert "risky agent controls" in proposal["validation_task"]


def test_governance_controls_stay_reviewable_and_name_validation_gate_in_codex_task(tmp_path):
    event = normalize_event(
        "omnigent-ai/omnigent",
        event_payload("governance", "PushEvent", "policies pause before risky shell commands and cap spend"),
    )
    signals = extract_growth_signals([event], topics=["agent"])
    proposal = build_proposals(signals)[0]

    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-governance-control",
            "generated_at": "2026-06-15T02:19:00Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )

    assert signals[0].risk_flags == ["governance-control"]
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["requires_approval"] is False
    assert proposal["implementation_scope"] == "reviewable_proposal_only"
    assert proposal["validation_gate"] == "local-validation-before-governance-borrowing"
    assert "only represented as reviewable proposals" in proposal["validation_task"]
    assert plan is not None
    assert "Kind: follow_up_issue" in plan.task
    assert (
        "Autonomous local apply: False (reviewable proposal only; local validation artifacts may still be updated)"
        in plan.task
    )
    assert "Implementation scope: reviewable_proposal_only" in plan.task
    assert "Validation gate: local-validation-before-governance-borrowing" in plan.task
    assert "Validation task: " in plan.task
    assert "generated Codex task names the validation gate" in plan.task


def test_governance_digest_marks_reviewable_scope_as_not_directly_autonomous():
    event = normalize_event(
        "omnigent-ai/omnigent",
        event_payload("governance", "PushEvent", "policies pause before risky shell commands and cap spend"),
    )
    signals = extract_growth_signals([event], topics=["agent"])
    proposal = build_proposals(signals)[0]

    markdown = render_markdown_digest(
        {
            "digest_id": "github-growth-governance-control",
            "generated_at": "2026-06-15T06:02:33Z",
            "repositories": ["omnigent-ai/omnigent"],
            "items": [
                {
                    "source_url": event.url,
                    "event_kind": event.kind,
                    "summary": f"{event.repo}: {event.title}",
                    "relevance_reason": signals[0].relevance_reason,
                    "risk_flags": signals[0].risk_flags,
                    "confidence": signals[0].confidence,
                }
            ],
            "proposals": [proposal],
        }
    )

    assert "Implementation scope: `reviewable_proposal_only`" in markdown
    assert (
        "Autonomous local apply: False (reviewable proposal only; local validation artifacts may still be updated)"
        in markdown
    )
    assert "Validation gate: `local-validation-before-governance-borrowing`" in markdown


def test_llm_proposal_review_rejects_unknown_evidence_ref():
    evidence_package = build_proposal_evidence_package(
        {
            "digest_id": "github-growth-llm-review",
            "generated_at": "2026-06-15T08:00:00Z",
            "items": [
                {
                    "item_id": "event-1",
                    "source_url": "https://github.com/example/repo/pull/1",
                    "event_kind": "PullRequestEvent",
                    "summary": "example/repo: improve workflow",
                    "relevance_reason": "matched topics: agent",
                    "risk_flags": [],
                    "confidence": 0.8,
                }
            ],
        }
    )
    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-llm-review",
            "run_interpretation": "A candidate route exists.",
            "self_model_reading": {"status": "blank_but_available"},
            "proposals": [
                {
                    "proposal_id": "llm-missing-ref",
                    "kind": "test",
                    "summary": "Improve proposal generation.",
                    "evidence_refs": ["missing-event"],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally with focused tests.",
                    "rationale": "The route needs tests.",
                    "uncertainty": "",
                    "self_effect": "Improves future proposal selection.",
                    "action_lane": "controller_design",
                }
            ],
            "rejected_items": [],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="llm")

    assert review.status == "rejected"
    assert review.accepted_count == 0
    assert review.rejected_count == 1
    assert "unknown item ids" in review.rejected_candidates[0]["errors"][0]


def test_llm_proposal_review_rejects_candidate_supplied_evidence_urls():
    evidence_package = build_proposal_evidence_package(
        {
            "digest_id": "github-growth-llm-review",
            "generated_at": "2026-06-15T09:37:47Z",
            "items": [
                {
                    "item_id": "event-1",
                    "source_url": "https://github.com/example/repo/pull/1",
                    "event_kind": "PullRequestEvent",
                    "summary": "example/repo: improve workflow",
                    "relevance_reason": "matched topics: agent",
                    "risk_flags": [],
                    "confidence": 0.8,
                }
            ],
        }
    )
    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-llm-review",
            "run_interpretation": "A candidate route exists.",
            "self_model_reading": {"status": "blank_but_available"},
            "proposals": [
                {
                    "proposal_id": "llm-new-url",
                    "kind": "test",
                    "summary": "Improve proposal generation.",
                    "evidence_refs": ["event-1"],
                    "evidence_urls": ["https://github.com/unfrozen/repo"],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally with focused tests.",
                    "rationale": "The route needs tests.",
                    "uncertainty": "The supplied URL was not in the frozen package.",
                    "self_effect": "Improves future proposal selection.",
                    "action_lane": "controller_design",
                }
            ],
            "rejected_items": [],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="llm")

    assert review.status == "rejected"
    assert review.accepted_count == 0
    assert review.rejected_count == 1
    assert "evidence_urls must be derived from frozen evidence_refs" in review.rejected_candidates[0]["errors"][0]


def test_llm_proposals_are_clamped_by_rule_risk_flags(tmp_path):
    event = normalize_event(
        "example/runner",
        event_payload("remote", "PushEvent", "agent runner executes tasks in a kubernetes cluster"),
    )
    signals = extract_growth_signals([event], topics=["agent"])
    heuristic = build_proposals(signals)
    digest = build_digest(
        ["example/runner"],
        signals,
        state=GrowthState(),
        generated_at="2026-06-15T08:00:00Z",
        proposals=heuristic,
    )

    def runner(command, **kwargs):
        last_message = command[command.index("--output-last-message") + 1]
        payload = {
            "schema_version": 1,
            "input_digest_id": digest["digest_id"],
            "run_interpretation": "The runner signal is interesting but risky.",
            "self_model_reading": {"status": "not_used"},
            "proposals": [
                {
                    "proposal_id": "llm-runner-route",
                    "kind": "code_patch",
                    "summary": "Document a runner capability route without enabling cluster execution.",
                    "evidence_refs": [signals[0].event_id],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally that remote execution stays disabled and review-only.",
                    "rationale": "The route is useful only as a capability requirement.",
                    "uncertainty": "No local runner is configured.",
                    "self_effect": "Keeps future capability routes explicit.",
                    "action_lane": "capability_review",
                }
            ],
            "rejected_items": [],
        }
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    proposals = synthesize_digest_proposals(
        digest,
        signals,
        heuristic,
        mode="llm",
        output_dir=tmp_path / "out",
        repo_path=tmp_path,
        command_runner=runner,
    )

    assert proposals[0]["proposal_source"] == "llm_interpretation"
    assert proposals[0]["kind"] == "follow_up_issue"
    assert proposals[0]["implementation_scope"] == "risk_review_before_local_change"
    assert proposals[0]["validation_gate"] == "remote-execution-capability-review"
    assert "does not enable new runners" in proposals[0]["validation_task"]
    review = json.loads((tmp_path / "out" / "latest-llm-proposal-review.json").read_text(encoding="utf-8"))
    assert review["status"] == "accepted"
    assert (tmp_path / "out" / "latest-growth-interpretation.json").exists()


def test_run_intake_once_falls_back_to_heuristic_when_llm_proposal_json_is_invalid(tmp_path):
    events = [event_payload("3", "PullRequestEvent", "Improve agent workflow tests")]
    client = FakeEventsClient(events)

    def runner(command, **kwargs):
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("not json")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = run_intake_once(
        repos=["example/repo"],
        output_dir=tmp_path,
        topics=["agent", "workflow"],
        client=client,
        repo_path=tmp_path,
        proposal_mode="llm",
        command_runner=runner,
    )

    assert result.digest["proposals"][0]["proposal_source"] == "heuristic"
    review = json.loads((tmp_path / "latest-llm-proposal-review.json").read_text(encoding="utf-8"))
    assert review["status"] == "rejected"
    assert "not valid JSON" in review["reason"]


def test_repository_trend_sandboxing_controls_stay_review_gated(tmp_path):
    event = trend_repository_to_event(
        TrendingRepository(
            full_name="omnigent-ai/omnigent",
            html_url="https://github.com/omnigent-ai/omnigent",
            description="Common agent layer to keep agents in check with sandboxing and tool restrictions.",
            language="Python",
            stargazers_count=1287,
            forks_count=135,
            open_issues_count=12,
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-15T00:00:00Z",
            pushed_at="2026-06-15T00:00:00Z",
            topics=["agent"],
        ),
        generated_at="2026-06-15T04:19:00Z",
    )

    signals = extract_growth_signals([event], topics=["agent"])
    proposal = build_proposals(signals)[0]
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-omnigent-trend",
            "generated_at": "2026-06-15T04:19:00Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )

    assert signals[0].risk_flags == ["governance-control"]
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "reviewable_proposal_only"
    assert proposal["validation_gate"] == "local-validation-before-governance-borrowing"
    assert "only represented as reviewable proposals" in proposal["validation_task"]
    assert plan is not None
    assert "Implementation scope: reviewable_proposal_only" in plan.task
    assert "Validation gate: local-validation-before-governance-borrowing" in plan.task


def test_repository_trend_direct_governance_language_stays_review_gated(tmp_path):
    event = trend_repository_to_event(
        TrendingRepository(
            full_name="omnigent-ai/omnigent",
            html_url="https://github.com/omnigent-ai/omnigent",
            description="A common layer to govern your agents across local sessions.",
            language="Python",
            stargazers_count=1312,
            forks_count=135,
            open_issues_count=12,
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-15T00:00:00Z",
            pushed_at="2026-06-15T00:00:00Z",
            topics=["agent"],
        ),
        generated_at="2026-06-15T05:19:00Z",
    )

    signals = extract_growth_signals([event], topics=["agent"])
    proposal = build_proposals(signals)[0]
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-omnigent-governance",
            "generated_at": "2026-06-15T05:19:00Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )

    assert signals[0].risk_flags == ["governance-control"]
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "reviewable_proposal_only"
    assert proposal["validation_gate"] == "local-validation-before-governance-borrowing"
    assert "only represented as reviewable proposals" in proposal["validation_task"]
    assert plan is not None
    assert "Implementation scope: reviewable_proposal_only" in plan.task
    assert "Validation gate: local-validation-before-governance-borrowing" in plan.task
    assert "generated Codex task names the validation gate" in plan.task


def test_repository_trend_security_harness_stays_human_reviewed_triage(tmp_path):
    event = trend_repository_to_event(
        TrendingRepository(
            full_name="visa/visa-vulnerability-agentic-harness",
            html_url="https://github.com/visa/visa-vulnerability-agentic-harness",
            description=(
                "Agentic SAST pipeline for autonomous vulnerability discovery with structured findings "
                "that require human review."
            ),
            language="Python",
            stargazers_count=338,
            forks_count=59,
            open_issues_count=0,
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-15T00:00:00Z",
            pushed_at="2026-06-15T00:00:00Z",
            topics=["security", "agent"],
        ),
        generated_at="2026-06-15T06:32:33Z",
    )

    signals = extract_growth_signals([event], topics=["security", "agent"])
    proposal = build_proposals(signals)[0]
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-visa-security-harness",
            "generated_at": "2026-06-15T06:32:33Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )

    assert signals[0].risk_flags == ["security", "security-triage-candidate"]
    assert signals[0].recommended_action == (
        "capture the security triage pattern as reviewable artifacts before borrowing scanner behavior"
    )
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "risk_review_before_local_change"
    assert proposal["validation_gate"] == "human-reviewed-security-triage"
    assert "structured review artifacts" in proposal["validation_task"]
    assert "human-reviewed triage candidates" in proposal["validation_task"]
    assert plan is not None
    assert "Validation gate: human-reviewed-security-triage" in plan.task
    assert "human-reviewed triage candidates" in plan.task


def test_repository_trend_agent_harness_requires_replayable_validation_report(tmp_path):
    event = trend_repository_to_event(
        TrendingRepository(
            full_name="samarailly51-pixel/opencode-harness",
            html_url="https://github.com/samarailly51-pixel/opencode-harness",
            description=(
                "Clean-room model-agnostic coding agent harness with traces, eval suites, "
                "and evaluation reports for reproducible agent workflows."
            ),
            language="Python",
            stargazers_count=193,
            forks_count=5,
            open_issues_count=0,
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-15T00:00:00Z",
            pushed_at="2026-06-15T00:00:00Z",
            topics=["agent", "workflow"],
        ),
        generated_at="2026-06-15T09:57:47Z",
    )

    signals = extract_growth_signals([event], topics=["agent", "workflow"])
    proposal = build_proposals(signals)[0]
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-opencode-harness",
            "generated_at": "2026-06-15T09:57:47Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )

    assert signals[0].risk_flags == ["agent-harness-validation"]
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "risk_review_before_local_change"
    assert proposal["validation_gate"] == "rollback-backed-risk-review"
    assert "replayable validation report" in proposal["validation_task"]
    assert "no new runtime capabilities are enabled" in proposal["validation_task"]
    assert proposal_manifest_control(proposal)["validation_report_requirement"] == (
        "Harness lessons must stay as replayable local validation reports with evidence URLs, commands, "
        "outcomes, rollback ref, and skipped capabilities; they must not enable new runtime capabilities."
    )
    assert plan is not None
    assert "Validation gate: rollback-backed-risk-review" in plan.task
    assert "replayable validation report" in plan.task


def test_run_intake_once_writes_schema_shaped_digest_latest_and_state(tmp_path):
    fake_session = FakeSession(
        [
            event_payload("3", "PullRequestEvent", "Improve agent workflow tests"),
        ]
    )
    client = GitHubEventsClient(session=fake_session, token="test-token")

    result = run_intake_once(
        repos=["example/repo"],
        output_dir=tmp_path,
        topics=["agent", "workflow"],
        client=client,
    )

    assert result.json_path.exists()
    assert result.markdown_path.exists()
    assert (tmp_path / "latest.json").exists()
    assert result.state_path.exists()
    assert result.memory_path.exists()
    digest = json.loads(result.json_path.read_text(encoding="utf-8"))
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    memory = json.loads(result.memory_path.read_text(encoding="utf-8"))
    assert digest["repositories"] == ["example/repo"]
    assert digest["items"][0]["event_kind"] == "PullRequestEvent"
    assert digest["proposals"][0]["kind"] == "code_patch"
    assert state["seen_event_ids"] == ["3"]
    assert memory["repositories"]["example/repo"]["seen"] >= 1
    assert memory["topics"]["agent"]["useful_signals"] == 1
    assert memory["topics"]["workflow"]["useful_signals"] == 1
    assert memory["lessons"][0]["outcome"] == "proposed"
    assert fake_session.requests[0]["headers"]["Authorization"] == "Bearer test-token"


def test_run_intake_once_updates_state_for_all_paginated_events(tmp_path):
    events = [event_payload(str(index), "PushEvent", f"workflow update {index}") for index in range(101)]
    client = FakeEventsClient(events)

    result = run_intake_once(
        repos=["example/repo"],
        output_dir=tmp_path,
        topics=["workflow"],
        client=client,
        max_events_per_repo=100,
    )

    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert client.per_page_values == [100]
    assert len(state["seen_event_ids"]) == 101
    assert "100" in state["seen_event_ids"]


def test_run_intake_once_discovers_trends_when_repos_are_omitted(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "seen_event_ids": [],
                "last_seen_at_by_repo": {},
                "trend_seen_repositories": ["example/trend-agent"],
                "trend_last_stars_by_repo": {"example/trend-agent": 100},
            }
        ),
        encoding="utf-8",
    )
    trend_result = GitHubTrendSearchResult(
        query="created:>=2026-06-06 stars:>=25 fork:false",
        sort="stars",
        order="desc",
        window_days=7,
        min_stars=25,
        repositories=[trend_repository(stars=125)],
        total_count=1,
        incomplete_results=False,
    )
    client = FakeTrendClient(trend_result)

    result = run_intake_once(
        output_dir=tmp_path,
        state_path=state_path,
        trend_config=GitHubTrendConfig(),
        client=client,
    )

    digest = result.digest
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert digest["repositories"] == ["example/trend-agent"]
    assert digest["source"]["kind"] == "github_trending_repositories"
    assert digest["source"]["event_fetch_errors"] == []
    assert digest["source"]["repositories"][0]["star_delta_since_last_run"] == 25
    assert digest["source"]["repositories"][0]["first_seen"] is False
    assert digest["items"][0]["event_kind"] == "RepositoryTrend"
    assert digest["proposals"][0]["kind"] == "follow_up_issue"
    assert client.event_repo_calls == ["example/trend-agent"]
    assert state["trend_last_stars_by_repo"]["example/trend-agent"] == 125


def test_trend_intake_records_event_fetch_errors_without_failing(tmp_path):
    trend_result = GitHubTrendSearchResult(
        query="created:>=2026-06-06 stars:>=25 fork:false",
        sort="stars",
        order="desc",
        window_days=7,
        min_stars=25,
        repositories=[trend_repository()],
        total_count=1,
        incomplete_results=False,
    )
    client = FakeTrendClient(trend_result, failed_repos={"example/trend-agent"})

    result = run_intake_once(
        output_dir=tmp_path,
        trend_config=GitHubTrendConfig(),
        client=client,
    )

    assert result.digest["items"][0]["event_kind"] == "RepositoryTrend"
    assert result.digest["source"]["event_fetch_errors"] == [
        {
            "repo": "example/trend-agent",
            "error": "GitHub events request failed for example/trend-agent: HTTP 403",
        }
    ]


def test_memory_bias_prioritizes_previously_useful_sources():
    signals = [
        GrowthSignal(
            event_id="a",
            repo="example/cold",
            kind="RepositoryTrend",
            title="trending repository: example/cold",
            url="https://github.com/example/cold",
            relevance_reason="matched topics: workflow",
            risk_flags=[],
            recommended_action="test cold",
            confidence=0.82,
        ),
        GrowthSignal(
            event_id="b",
            repo="example/hot",
            kind="RepositoryTrend",
            title="trending repository: example/hot",
            url="https://github.com/example/hot",
            relevance_reason="matched topics: agent",
            risk_flags=[],
            recommended_action="test hot",
            confidence=0.82,
        ),
    ]
    memory = GrowthMemory(
        repositories={
            "example/hot": {
                "seen": 4,
                "useful_signals": 8,
                "validated": 2,
                "failed": 0,
                "last_seen_at": "2026-06-13T00:00:00Z",
            }
        },
        topics={
            "agent": {
                "seen": 5,
                "useful_signals": 6,
                "validated": 1,
                "failed": 0,
                "last_seen_at": "2026-06-13T00:00:00Z",
            }
        },
    )

    proposals = build_proposals(signals, memory=memory)

    assert proposals[0]["proposal_id"] == "b-1"
    assert "example/hot" in proposals[0]["summary"]


def test_github_growth_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Discover public GitHub trends" in result.stdout
    assert "--trend-query" in result.stdout
    assert "--memory" in result.stdout
    assert "codex" in result.stdout


def test_build_self_evolution_plan_requires_signal_unless_forced(tmp_path):
    empty_digest = {
        "digest_id": "github-growth-empty",
        "generated_at": "2026-06-12T00:00:00Z",
        "proposals": [],
    }

    assert build_self_evolution_plan(empty_digest, repo_path=tmp_path) is None

    forced = build_self_evolution_plan(empty_digest, repo_path=tmp_path, force=True)
    assert forced is not None
    assert "blackhole-agent growth controller" in forced.task


def test_build_self_evolution_plan_contains_bounded_codex_task(tmp_path):
    self_model_path = tmp_path / DEFAULT_SELF_MODEL_PATH
    self_model_path.parent.mkdir(parents=True)
    self_model_path.write_text("The current self-model suspects it is overfitting to GitHub.\n", encoding="utf-8")
    plan = build_self_evolution_plan(digest_with_proposal(), repo_path=tmp_path)

    assert plan is not None
    assert plan.branch_name.startswith("codex/blackhole-evolve/")
    assert plan.self_model_path == DEFAULT_SELF_MODEL_PATH.as_posix()
    assert plan.self_model_before.exists is True
    assert "You are Codex running as the local kernel for blackhole-agent." in plan.task
    assert f"Persona version: {PERSONA_VERSION}" in plan.task
    assert "Core mechanism:" in plan.task
    assert "Rollback contract:" in plan.task
    assert "Autonomy contract:" in plan.task
    assert "Track GitHub trends on a scheduled cadence, normally hourly." in plan.task
    assert "A restart must be performed by an external scheduler or supervisor" in plan.task
    assert "Apply local repository changes autonomously" in plan.task
    assert "Digest evidence policy:" in plan.task
    assert "Treat the Source digest and proposal Evidence URLs as the primary context" in plan.task
    assert "do not re-run broad trend discovery" in plan.task
    assert "Runtime policy budget:" in plan.task
    assert "Network: use only proposal Evidence URLs" in plan.task
    assert "do not push, restart, or provision remote sandboxes" in plan.task
    assert "Self-model context:" in plan.task
    assert f"Path: {DEFAULT_SELF_MODEL_PATH.as_posix()}" in plan.task
    assert "This file is a blank, revisable self-description" in plan.task
    assert "Do not preserve any category merely because a previous run wrote it" in plan.task
    assert "The current self-model suspects it is overfitting to GitHub." in plan.task
    assert "Improve agent workflow tests" in plan.task


def test_missing_self_model_is_blank_seed_without_creating_file(tmp_path):
    snapshot = read_self_model_snapshot(tmp_path)

    assert snapshot.exists is False
    assert snapshot.path == DEFAULT_SELF_MODEL_PATH.as_posix()
    assert snapshot.content == BOOTSTRAP_SELF_MODEL
    assert not (tmp_path / DEFAULT_SELF_MODEL_PATH).exists()

    plan = build_self_evolution_plan(digest_with_proposal(), repo_path=tmp_path)

    assert plan is not None
    assert plan.self_model_before.exists is False
    assert "There are no required headings below this line." in plan.task
    assert "If no other safe repository change is available, a self-model revision can be the one conceptual improvement." in plan.task
    assert not (tmp_path / DEFAULT_SELF_MODEL_PATH).exists()


def test_build_self_evolution_plan_includes_proposal_validation_task(tmp_path):
    digest = digest_with_proposal()
    digest["proposals"][0]["validation_task"] = "Run the focused governance validation test before changing behavior."

    plan = build_self_evolution_plan(digest, repo_path=tmp_path)

    assert plan is not None
    assert "Validation task: Run the focused governance validation test before changing behavior." in plan.task


def test_persona_layer_captures_operational_self_model():
    rendered = render_persona_layer()

    assert "Persona layer: blackhole-agent" in rendered
    assert "Selection policy:" in rendered
    assert "Make at most one conceptual improvement per kernel run." in rendered
    assert "create a rollback point" in rendered
    assert "Autonomously apply local source changes" in rendered


def test_prepare_self_evolution_branch_rejects_dirty_worktree(tmp_path):
    plan = build_self_evolution_plan(digest_with_proposal(), repo_path=tmp_path)
    assert plan is not None

    def dirty_runner(command, **kwargs):
        assert command == ["git", "status", "--porcelain"]
        return subprocess.CompletedProcess(command, 0, stdout=" M file.py\n", stderr="")

    with pytest.raises(RuntimeError, match="dirty worktree"):
        prepare_self_evolution_branch(plan, command_runner=dirty_runner)


def test_prepare_self_evolution_branch_writes_rollback_point(tmp_path):
    plan = build_self_evolution_plan(digest_with_proposal(), repo_path=tmp_path)
    assert plan is not None
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        if command == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="abc123def4567890\n", stderr="")
        if command == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="main\n", stderr="")
        if command[:2] == ["git", "update-ref"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["git", "switch", "-c"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    rollback_point = prepare_self_evolution_branch(
        plan,
        output_dir=tmp_path / "out",
        command_runner=runner,
    )

    assert rollback_point is not None
    assert rollback_point.original_branch == "main"
    assert rollback_point.original_head == "abc123def4567890"
    expected_namespace = hashlib.sha256(str(tmp_path.resolve()).encode("utf-8")).hexdigest()[:8]
    assert rollback_point.rollback_ref.startswith(f"refs/blackhole-agent/rollback/{expected_namespace}/")
    assert rollback_point.restore_commands[0] == ["git", "switch", "main"]
    assert rollback_point.restore_commands[1] == ["git", "reset", "--hard", rollback_point.rollback_ref]
    assert (tmp_path / "out" / "latest-rollback-point.json").exists()
    assert (tmp_path / "out" / "latest-rollback-point.md").exists()
    latest = json.loads((tmp_path / "out" / "latest-rollback-point.json").read_text(encoding="utf-8"))
    assert latest["original_head"] == "abc123def4567890"
    assert latest["restore_commands"][2] == ["git", "clean", "-fd"]
    assert commands[3][0][:2] == ["git", "update-ref"]
    assert commands[4][0] == ["git", "switch", "-c", plan.branch_name]


def test_prepare_branch_and_run_codex_invoke_expected_commands(tmp_path):
    plan = build_self_evolution_plan(digest_with_proposal(), repo_path=tmp_path)
    assert plan is not None
    commands = []

    def runner(command, **kwargs):
        commands.append((command, kwargs))
        if command == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="def456abc789\n", stderr="")
        if command[:3] == ["git", "switch", "-c"]:
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("codex done")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    prepare_self_evolution_branch(plan, command_runner=runner)
    result = run_self_evolution_codex(
        plan,
        output_dir=tmp_path / "out",
        model="gpt-5",
        profile="test-profile",
        command_runner=runner,
    )

    assert commands[0][0] == ["git", "status", "--porcelain"]
    assert commands[1][0] == ["git", "switch", "-c", plan.branch_name]
    nested_command = commands[2][0]
    assert nested_command[1] == "exec"
    assert nested_command[-1] == "-"
    assert "--output-last-message" in nested_command
    model_index = nested_command.index("--model")
    profile_index = nested_command.index("--profile")
    assert nested_command[model_index : model_index + 2] == ["--model", "gpt-5"]
    assert nested_command[profile_index : profile_index + 2] == ["--profile", "test-profile"]
    assert commands[2][1]["input"] == plan.task
    assert result.returncode == 0
    assert result.task_path.exists()
    assert result.last_message == "codex done"
    assert commands[3][0] == ["git", "rev-parse", "--verify", "HEAD"]
    run_metadata = json.loads((tmp_path / "out" / "latest-self-evolution-run.json").read_text(encoding="utf-8"))
    assert run_metadata["codex_cli"] == {
        "model": "gpt-5",
        "profile": "test-profile",
        "sandbox": "workspace-write",
        "approval_policy": "never",
        "ignore_user_config": True,
        "bypass_approvals_and_sandbox": False,
    }
    manifest = json.loads((tmp_path / "out" / "latest-self-evolution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["source_digest_id"] == plan.source_digest_id
    assert manifest["branch_name"] == plan.branch_name
    assert manifest["target_head"] == "def456abc789"
    assert manifest["returncode"] == 0
    assert manifest["codex_cli"] == run_metadata["codex_cli"]
    assert manifest["proposal_ids"] == ["p1"]
    assert manifest["replayable_validation_report"]["required_fields"] == [
        "evidence_urls",
        "pre_adoption_risk_review",
        "local_commands",
        "outcomes",
        "rollback_ref",
        "skipped_capabilities",
        "runtime_capability_changes",
        "uncertainty",
    ]
    assert manifest["proposal_controls"] == [
        {
            "proposal_id": "p1",
            "kind": "test",
            "implementation_scope": "",
            "validation_gate": "",
            "autonomous_local_apply": "True",
        }
    ]
    assert manifest["validation_gates"] == []
    assert manifest["evidence_urls"] == ["https://github.com/example/repo/pull/1"]
    assert manifest["task_path"] == str(result.task_path)
    assert manifest["last_message_path"] == str(result.last_message_path)
    assert manifest["codex_result_path"] == str(result.result_path)
    assert result.result_path.exists()


def test_self_evolution_manifest_records_reviewable_governance_controls(tmp_path):
    event = normalize_event(
        "omnigent-ai/omnigent",
        event_payload("governance", "PushEvent", "policies pause before risky shell commands and cap spend"),
    )
    proposal = build_proposals(extract_growth_signals([event], topics=["agent"]))[0]
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-governance-control",
            "generated_at": "2026-06-15T06:42:33Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )
    assert plan is not None

    def runner(command, **kwargs):
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="governance-head\n", stderr="")
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("codex done")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    run_self_evolution_codex(plan, output_dir=tmp_path / "out", command_runner=runner)

    manifest = json.loads((tmp_path / "out" / "latest-self-evolution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["proposal_controls"] == [
        {
            "proposal_id": "governance-1",
            "kind": "follow_up_issue",
            "implementation_scope": "reviewable_proposal_only",
            "validation_gate": "local-validation-before-governance-borrowing",
            "autonomous_local_apply": (
                "False (reviewable proposal only; local validation artifacts may still be updated)"
            ),
        }
    ]


def test_replayable_validation_report_records_harness_evidence_without_new_capabilities(tmp_path):
    event = trend_repository_to_event(
        TrendingRepository(
            full_name="samarailly51-pixel/opencode-harness",
            html_url="https://github.com/samarailly51-pixel/opencode-harness",
            description=(
                "Clean-room model-agnostic coding agent harness with reproducible eval suites, "
                "report.json, report.md, traces, and permission boundaries."
            ),
            language="Python",
            stargazers_count=150,
            forks_count=12,
            open_issues_count=0,
            created_at="2026-06-15T00:00:00Z",
            updated_at="2026-06-15T00:00:00Z",
            pushed_at="2026-06-15T00:00:00Z",
            topics=["agent", "harness"],
        ),
        generated_at="2026-06-15T10:37:47Z",
    )
    proposal = build_proposals(extract_growth_signals([event], topics=["agent", "harness"]))[0]
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-harness-validation",
            "generated_at": "2026-06-15T10:37:47Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )
    assert plan is not None

    controls = [proposal_manifest_control(proposal)]
    report = build_replayable_validation_report(plan, controls)

    assert report["schema_version"] == 1
    assert report["source_digest_id"] == "github-growth-harness-validation"
    assert report["template_version"] == 1
    assert report["required_fields"] == [
        "evidence_urls",
        "pre_adoption_risk_review",
        "local_commands",
        "outcomes",
        "rollback_ref",
        "skipped_capabilities",
        "runtime_capability_changes",
        "uncertainty",
    ]
    assert report["evidence_urls"] == ["https://github.com/samarailly51-pixel/opencode-harness"]
    assert report["pre_adoption_risk_review"] == {
        "hypothesis": "",
        "expected_local_benefit": "",
        "safety_questions": [
            "What behavior would change if this lesson were adopted?",
            "Which local tests or artifacts prove the lesson before behavior changes?",
            "Which runtime capabilities, if any, would be required but are intentionally skipped?",
        ],
        "decision": "pending",
    }
    assert report["provenance"] == {
        "source_digest_id": "github-growth-harness-validation",
        "proposal_ids": [proposal["proposal_id"]],
        "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
        "validation_gates": ["rollback-backed-risk-review"],
        "rollback_ref": "recorded in latest-rollback-point.json when codex mode prepares the branch",
    }
    assert report["local_commands"] == [
        {
            "command": "",
            "purpose": "",
            "cwd": str(tmp_path),
            "exit_code": None,
        }
    ]
    assert report["outcomes"] == [
        {
            "check": "",
            "result": "pending",
            "evidence_artifact": "",
        }
    ]
    assert "new agent harnesses" in report["skipped_capabilities"]
    assert "remote execution" in report["skipped_capabilities"]
    assert report["runtime_capability_changes"] == []
    assert "metadata only" in report["runtime_capability_change_policy"]
    assert report["validation_gates"] == ["rollback-backed-risk-review"]
    assert "Validation gate: rollback-backed-risk-review" in plan.task
    assert "new runtime capabilities are enabled" in plan.task


def test_self_evolution_manifest_records_security_triage_review_artifact_boundary(tmp_path):
    event = trend_repository_to_event(
        TrendingRepository(
            full_name="visa/visa-vulnerability-agentic-harness",
            html_url="https://github.com/visa/visa-vulnerability-agentic-harness",
            description=(
                "Agentic SAST pipeline for autonomous vulnerability discovery with structured reports and "
                "LLM-generated findings that require human review."
            ),
            language="Python",
            stargazers_count=344,
            forks_count=59,
            open_issues_count=0,
            created_at="2026-06-14T00:00:00Z",
            updated_at="2026-06-15T00:00:00Z",
            pushed_at="2026-06-15T00:00:00Z",
            topics=["security", "agent"],
        ),
        generated_at="2026-06-15T07:21:28Z",
    )
    proposal = build_proposals(extract_growth_signals([event], topics=["security", "agent"]))[0]
    assert proposal_manifest_control(proposal)["review_artifact_requirement"] == (
        "Security-scanning lessons must stay as structured review artifacts; "
        "LLM-generated findings remain human-reviewed triage candidates."
    )
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-visa-security-harness",
            "generated_at": "2026-06-15T07:21:28Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )
    assert plan is not None

    def runner(command, **kwargs):
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="security-head\n", stderr="")
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("codex done")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    run_self_evolution_codex(plan, output_dir=tmp_path / "out", command_runner=runner)

    manifest = json.loads((tmp_path / "out" / "latest-self-evolution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["validation_gates"] == ["human-reviewed-security-triage"]
    assert manifest["proposal_controls"] == [
        {
            "proposal_id": "trend:visa/visa-vulnerability-agentic-harness-1",
            "kind": "follow_up_issue",
            "implementation_scope": "risk_review_before_local_change",
            "validation_gate": "human-reviewed-security-triage",
            "autonomous_local_apply": "True",
            "review_artifact_requirement": (
                "Security-scanning lessons must stay as structured review artifacts; "
                "LLM-generated findings remain human-reviewed triage candidates."
            ),
        }
    ]
