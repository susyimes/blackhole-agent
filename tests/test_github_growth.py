import hashlib
import json
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import blackhole_agent.github_growth as github_growth
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
    validation_report_completion_status,
)
from blackhole_agent.persona import PERSONA_VERSION, render_persona_layer
from blackhole_agent.proposal_synthesis import (
    build_context_budget_preflight,
    build_provider_routing_preflight,
    build_proposal_evidence_package,
    review_llm_proposal_response,
    stable_hash,
)
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


class JourneyFakeGitHubClient:
    def __init__(self, *args, **kwargs) -> None:
        self.requests: list[tuple[str, int]] = []

    def list_repository_events(self, repo: str, *, per_page: int = 100) -> list[dict]:
        self.requests.append((repo, per_page))
        return [
            {
                "id": "terminal-e2e",
                "type": "PushEvent",
                "actor": {"login": "octocat"},
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "payload": {
                    "ref": "refs/heads/main",
                    "commits": [
                        {
                            "sha": "abc123",
                            "message": "terminal-driven end-to-end journey tests for local agent runner",
                        }
                    ],
                },
            }
        ]


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


def test_cli_codex_mode_runs_terminal_driven_controller_journey(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    output_dir = tmp_path / "out"
    calls: list[list[str]] = []
    codex_commands: list[list[str]] = []

    monkeypatch.setattr(github_growth, "GitHubEventsClient", JourneyFakeGitHubClient)

    def fake_run(command, **kwargs):
        calls.append(command)
        if command == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="base123\n", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="candidate123\n", stderr="")
        if command == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="main\n", stderr="")
        if command[:2] == ["git", "update-ref"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["git", "switch", "-c"]:
            return subprocess.CompletedProcess(command, 0, stdout="switched\n", stderr="")
        if command[1:4] == ["exec", "--cd", str(repo)]:
            codex_commands.append(command)
            last_message = command[command.index("--output-last-message") + 1]
            Path(last_message).write_text("journey complete", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="codex ok\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(github_growth.subprocess, "run", fake_run)
    original_prepare_self_evolution_branch = github_growth.prepare_self_evolution_branch
    original_run_self_evolution_codex = github_growth.run_self_evolution_codex

    def fake_prepare_self_evolution_branch(*args, **kwargs):
        kwargs["command_runner"] = fake_run
        return original_prepare_self_evolution_branch(*args, **kwargs)

    def fake_run_self_evolution_codex(*args, **kwargs):
        kwargs["command_runner"] = fake_run
        return original_run_self_evolution_codex(*args, **kwargs)

    monkeypatch.setattr(github_growth, "prepare_self_evolution_branch", fake_prepare_self_evolution_branch)
    monkeypatch.setattr(github_growth, "run_self_evolution_codex", fake_run_self_evolution_codex)
    result = CliRunner().invoke(
        app,
        [
            "--repos",
            "omnigent-ai/omnigent",
            "--output-dir",
            str(output_dir),
            "--repo-path",
            str(repo),
            "--evolution-mode",
            "codex",
            "--proposal-mode",
            "heuristic",
            "--codex-timeout-seconds",
            "12",
            "--extra-instruction",
            "Keep this journey terminal-driven.",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote self-evolution plan" in result.output
    assert "Wrote rollback point" in result.output
    assert "Codex kernel exited with 0" in result.output
    assert codex_commands, "expected the controller to launch the Codex CLI kernel"
    assert "--sandbox" in codex_commands[0]
    assert "--ask-for-approval" not in codex_commands[0]
    assert any(call[:3] == ["git", "switch", "-c"] for call in calls)

    digest = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
    plan = json.loads((output_dir / "latest-self-evolution-plan.json").read_text(encoding="utf-8"))
    run = json.loads((output_dir / "latest-self-evolution-run.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "latest-self-evolution-manifest.json").read_text(encoding="utf-8"))
    rollback = json.loads((output_dir / "latest-rollback-point.json").read_text(encoding="utf-8"))

    assert digest["proposals"][0]["proposal_id"] == "terminal-e2e-1"
    assert digest["proposals"][0]["validation_gate"] == "narrow-local-verification"
    assert "terminal-driven end-to-end journey" in plan["task"]
    assert run["last_message"] == "journey complete"
    assert manifest["proposal_ids"] == ["terminal-e2e-1"]
    assert manifest["validation_gates"] == ["narrow-local-verification"]
    assert rollback["original_head"] == "base123"


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


def test_extract_growth_signals_flags_privacy_leakage_for_review():
    event = normalize_event(
        "example/repo",
        event_payload("2", "PushEvent", "log auth token to validation report"),
    )
    signals = extract_growth_signals([event], topics=["security", "workflow"])

    assert len(signals) == 1
    assert signals[0].risk_flags == ["privacy-leakage"]
    assert signals[0].recommended_action == (
        "record the privacy-leakage boundary and keep sensitive data out of artifacts and runtime changes"
    )


def test_extract_growth_signals_does_not_flag_generic_security_token_language():
    event = normalize_event(
        "example/repo",
        event_payload("2", "PushEvent", "security token handling tests"),
    )
    signals = extract_growth_signals([event], topics=["security", "workflow"])

    assert len(signals) == 1
    assert signals[0].risk_flags == []
    assert signals[0].recommended_action == "cluster commit messages and keep only patterns with clear test evidence"


def test_extract_growth_signals_allows_remote_execution_sandboxes_for_local_validation():
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
    assert signals[0].risk_flags == []
    assert signals[0].recommended_action == (
        "adapt the runner or remote-execution pattern freely when configured capabilities and validation support it"
    )


def test_tool_dispatch_gaps_can_become_local_validation_candidates(tmp_path):
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

    assert signals[0].risk_flags == []
    assert signals[0].recommended_action == "adapt the capability route freely when local validation can cover it"
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "narrow-local-verification"
    assert "Verify the proposed lesson with a local test" in proposal["validation_task"]
    assert plan is not None
    assert "Validation task: " in plan.task
    assert "Implementation scope: local_validation_candidate" in plan.task


def test_extract_growth_signals_allows_agent_governance_controls_for_local_validation():
    event = normalize_event(
        "example/repo",
        event_payload("governance", "PushEvent", "agent policy gates for spend and tool access"),
    )

    signals = extract_growth_signals([event], topics=["agent"])

    assert len(signals) == 1
    assert signals[0].risk_flags == []
    assert signals[0].recommended_action == (
        "adapt the governance pattern freely when it improves local controller behavior without offensive use or privacy leakage"
    )
    proposal = build_proposals(signals)[0]
    assert proposal["kind"] == "test"
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "narrow-local-verification"


def test_governance_controls_can_apply_locally_and_name_validation_gate_in_codex_task(tmp_path):
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

    assert signals[0].risk_flags == []
    assert proposal["kind"] == "test"
    assert proposal["requires_approval"] is False
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "narrow-local-verification"
    assert "Verify the proposed lesson with a local test" in proposal["validation_task"]
    assert plan is not None
    assert "Kind: test" in plan.task
    assert "Autonomous local apply: True" in plan.task
    assert "Implementation scope: local_validation_candidate" in plan.task
    assert "Validation gate: narrow-local-verification" in plan.task
    assert "Validation task: " in plan.task
    assert "Verify the proposed lesson with a local test" in plan.task


def test_governance_digest_marks_local_validation_scope_as_autonomous():
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

    assert "Implementation scope: `local_validation_candidate`" in markdown
    assert "Autonomous local apply: True" in markdown
    assert "Validation gate: `narrow-local-verification`" in markdown


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


def test_proposal_evidence_package_truncates_context_without_mutating_evidence_refs():
    long_summary = "summary-" + ("x" * 200)
    long_reason = "reason-" + ("y" * 200)
    digest = {
        "digest_id": "github-growth-context-budget",
        "generated_at": "2026-06-16T04:26:01Z",
        "items": [
            {
                "item_id": "event-1",
                "source_url": "https://github.com/microsoft/fastcontext/issues/123?query=preserve",
                "event_kind": "IssueCommentEvent",
                "summary": long_summary,
                "relevance_reason": long_reason,
                "risk_flags": [],
                "confidence": 0.91,
            },
            {
                "item_id": "event-2",
                "source_url": "https://github.com/example/overflow",
                "event_kind": "PushEvent",
                "summary": "overflow",
                "relevance_reason": "should be item-count truncated",
                "risk_flags": [],
                "confidence": 0.5,
            },
        ],
    }

    first = build_proposal_evidence_package(
        digest,
        self_model_snapshot={"path": "docs/self-model.md", "sha256": "abc", "content": "z" * 50},
        max_items=1,
        max_item_text_chars=32,
        max_self_model_chars=10,
    )
    second = build_proposal_evidence_package(
        digest,
        self_model_snapshot={"path": "docs/self-model.md", "sha256": "abc", "content": "z" * 50},
        max_items=1,
        max_item_text_chars=32,
        max_self_model_chars=10,
    )

    assert first == second
    assert first["items"] == [
        {
            "item_id": "event-1",
            "source_url": "https://github.com/microsoft/fastcontext/issues/123?query=preserve",
            "event_kind": "IssueCommentEvent",
            "summary": long_summary[:32],
            "relevance_reason": long_reason[:32],
            "rule_risk_flags": [],
            "rule_confidence": 0.91,
        }
    ]
    assert first["allowed_evidence_urls"] == ["https://github.com/microsoft/fastcontext/issues/123?query=preserve"]
    assert first["context_budget"]["items_truncated"] is True
    assert first["context_budget"]["input_item_count"] == 2
    assert first["context_budget"]["item_selection_strategy"] == "risk_flags_then_confidence_then_original_order"
    assert first["context_budget"]["selected_item_ids"] == ["event-1"]
    assert first["context_budget"]["truncated_item_ids"] == ["event-2"]
    assert first["context_budget"]["item_selection_diagnostics"] == [
        {
            "original_index": 0,
            "rank": 1,
            "item_id": "event-1",
            "decision": "selected",
            "reason": "confidence",
            "risk_flag_count": 0,
            "confidence": 0.91,
            "truncated_fields": ["summary", "relevance_reason"],
        },
        {
            "original_index": 1,
            "rank": 2,
            "item_id": "event-2",
            "decision": "truncated",
            "reason": "max_items_exceeded",
            "risk_flag_count": 0,
            "confidence": 0.5,
            "truncated_fields": [],
        },
    ]
    assert first["context_budget"]["item_text_truncation"] == [
        {
            "item_id": "event-1",
            "fields": [
                {"field": "summary", "truncated": True, "original_chars": len(long_summary), "kept_chars": 32},
                {
                    "field": "relevance_reason",
                    "truncated": True,
                    "original_chars": len(long_reason),
                    "kept_chars": 32,
                },
            ],
        }
    ]
    assert first["self_model"]["content"] == "z" * 10
    assert first["self_model"]["truncated"] is True

    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-context-budget",
            "run_interpretation": "Use the preserved citation.",
            "self_model_reading": {"status": "bounded"},
            "proposals": [
                {
                    "proposal_id": "preserved-ref",
                    "kind": "test",
                    "summary": "Add context budget tests.",
                    "evidence_refs": ["event-1"],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally with oversized synthetic context.",
                    "rationale": "The evidence package must preserve citation identity.",
                    "uncertainty": "Only synthetic size pressure is covered.",
                    "self_effect": "Improves evidence preservation.",
                    "action_lane": "local_validation_candidate",
                }
            ],
            "rejected_items": [],
        }
    )

    review = review_llm_proposal_response(raw_response, first, mode="hybrid")

    assert review.status == "accepted"
    assert review.accepted_candidates[0]["evidence_refs"] == ["event-1"]
    assert review.accepted_candidates[0]["evidence_urls"] == [
        "https://github.com/microsoft/fastcontext/issues/123?query=preserve"
    ]


def test_proposal_evidence_package_prioritizes_items_before_truncation():
    digest = {
        "digest_id": "github-growth-context-priority",
        "generated_at": "2026-06-16T05:46:01Z",
        "items": [
            {
                "item_id": "low-earliest",
                "source_url": "https://github.com/example/low",
                "event_kind": "PushEvent",
                "summary": "low confidence item appeared first",
                "relevance_reason": "first input order should not dominate context budget",
                "risk_flags": [],
                "confidence": 0.1,
            },
            {
                "item_id": "top-confidence",
                "source_url": "https://github.com/microsoft/fastcontext/high",
                "event_kind": "IssuesEvent",
                "summary": "high confidence context-budget lesson",
                "relevance_reason": "strong fastcontext relevance",
                "risk_flags": [],
                "confidence": 0.95,
            },
            {
                "item_id": "middle-confidence",
                "source_url": "https://github.com/microsoft/fastcontext/middle",
                "event_kind": "IssueCommentEvent",
                "summary": "medium confidence context-budget lesson",
                "relevance_reason": "useful supporting signal",
                "risk_flags": [],
                "confidence": 0.7,
            },
            {
                "item_id": "review-boundary",
                "source_url": "https://github.com/omnigent-ai/omnigent/privacy",
                "event_kind": "PushEvent",
                "summary": "privacy boundary signal",
                "relevance_reason": "risk-gated evidence must survive budget pressure",
                "risk_flags": ["privacy-leakage"],
                "confidence": 0.4,
            },
        ],
    }

    first = build_proposal_evidence_package(digest, max_items=3, max_item_text_chars=200)
    second = build_proposal_evidence_package(digest, max_items=3, max_item_text_chars=200)

    assert first == second
    assert [item["item_id"] for item in first["items"]] == [
        "review-boundary",
        "top-confidence",
        "middle-confidence",
    ]
    assert first["context_budget"]["selected_item_ids"] == [
        "review-boundary",
        "top-confidence",
        "middle-confidence",
    ]
    assert first["context_budget"]["truncated_item_ids"] == ["low-earliest"]
    assert [
        (item["item_id"], item["decision"], item["reason"], item["rank"])
        for item in first["context_budget"]["item_selection_diagnostics"]
    ] == [
        ("low-earliest", "truncated", "max_items_exceeded", 4),
        ("top-confidence", "selected", "confidence", 2),
        ("middle-confidence", "selected", "confidence", 3),
        ("review-boundary", "selected", "risk_flags", 1),
    ]
    assert first["allowed_evidence_urls"] == [
        "https://github.com/microsoft/fastcontext/high",
        "https://github.com/microsoft/fastcontext/middle",
        "https://github.com/omnigent-ai/omnigent/privacy",
    ]

    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-context-priority",
            "run_interpretation": "Prioritize risk and confidence under context pressure.",
            "self_model_reading": {"status": "bounded"},
            "proposals": [
                {
                    "proposal_id": "risk-review-preserved",
                    "kind": "follow_up_issue",
                    "summary": "Keep privacy-boundary routes reviewable.",
                    "evidence_refs": ["review-boundary"],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally that privacy-boundary routes remain review-gated.",
                    "rationale": "Risk evidence should not be lost when item counts grow.",
                    "uncertainty": "Synthetic digest only covers ranking behavior.",
                    "self_effect": "Improves safety review under context pressure.",
                    "action_lane": "risk_review_before_local_change",
                },
                {
                    "proposal_id": "confidence-route",
                    "kind": "code_patch",
                    "summary": "Add context-budget routing checks.",
                    "evidence_refs": ["top-confidence", "middle-confidence"],
                    "added_risk_flags": [],
                    "validation_task": "Replay oversized synthetic context locally.",
                    "rationale": "High-confidence evidence should remain available for proposal generation.",
                    "uncertainty": "Does not call an external model.",
                    "self_effect": "Keeps proposal count stable under truncation.",
                    "action_lane": "local_validation_candidate",
                },
            ],
            "rejected_items": ["low-earliest"],
        }
    )

    review = review_llm_proposal_response(raw_response, first, mode="hybrid")

    assert review.status == "accepted"
    assert review.accepted_count == 2
    assert review.accepted_candidates[0]["evidence_refs"] == ["review-boundary"]
    assert review.accepted_candidates[1]["evidence_refs"] == ["top-confidence", "middle-confidence"]


def test_context_budget_preflight_reports_non_truncated_local_metadata_only():
    evidence_package = build_proposal_evidence_package(
        {
            "digest_id": "github-growth-context-preflight",
            "generated_at": "2026-06-16T05:06:01Z",
            "items": [
                {
                    "item_id": "event-1",
                    "source_url": "https://github.com/microsoft/fastcontext",
                    "event_kind": "PushEvent",
                    "summary": "compact context",
                    "relevance_reason": "fits within budget",
                    "risk_flags": [],
                    "confidence": 0.8,
                }
            ],
        },
        max_items=3,
        max_item_text_chars=100,
    )

    preflight = build_context_budget_preflight(evidence_package)

    assert preflight == {
        "schema_version": 1,
        "digest_id": "github-growth-context-preflight",
        "generated_at": "2026-06-16T05:06:01Z",
        "input_hash": stable_hash(evidence_package),
        "status": "within_budget",
        "local_metadata_only": True,
        "external_fetch_performed": False,
        "max_items": 3,
        "input_item_count": 1,
        "kept_item_count": 1,
        "items_truncated": False,
        "max_item_text_chars": 100,
        "truncated_item_count": 0,
        "whole_item_truncated_count": 0,
        "text_truncated_item_count": 0,
        "truncated_field_count": 0,
        "input_text_chars": len("compact context") + len("fits within budget"),
        "selected_text_original_chars": len("compact context") + len("fits within budget"),
        "selected_text_chars": len("compact context") + len("fits within budget"),
        "field_truncated_text_chars": 0,
        "item_selection_strategy": "risk_flags_then_confidence_then_original_order",
        "selected_item_ids": ["event-1"],
        "truncated_item_ids": [],
        "excluded_item_count": 0,
        "item_selection_diagnostics": [
            {
                "original_index": 0,
                "rank": 1,
                "item_id": "event-1",
                "decision": "selected",
                "reason": "confidence",
                "risk_flag_count": 0,
                "confidence": 0.8,
                "truncated_fields": [],
            }
        ],
        "self_model_truncated": False,
    }
    preflight_json = json.dumps(preflight, sort_keys=True)
    assert "allowed_evidence_urls" not in preflight
    assert "https://github.com/microsoft/fastcontext" not in preflight_json


@pytest.mark.parametrize(
    ("model", "provider_family", "model_family"),
    [
        ("databricks-gpt-5", "gpt", "gpt"),
        ("databricks-gemini-2-5-pro", "gemini", "gemini"),
    ],
)
def test_provider_routing_preflight_detects_codex_gateway_misroute_without_url_leakage(
    model: str,
    provider_family: str,
    model_family: str,
):
    preflight = build_provider_routing_preflight(
        {
            "provider": "openai",
            "model": model,
            "base_url": "https://workspace.example.test/ai-gateway/codex/v1",
        }
    )

    assert preflight == {
        "schema_version": 1,
        "status": "misrouted_codex_gateway",
        "local_metadata_only": True,
        "external_fetch_performed": False,
        "provider_family": provider_family,
        "model_family": model_family,
        "route_shape": "codex_gateway",
        "base_url_recorded": False,
        "host_recorded": False,
        "reason": "chat_completions_provider_points_at_codex_responses_gateway",
        "expected_route_shape": "serving_endpoint",
    }
    preflight_json = json.dumps(preflight, sort_keys=True)
    assert "workspace.example.test" not in preflight_json
    assert "/ai-gateway/codex" not in preflight_json


def test_provider_routing_preflight_accepts_gemini_serving_endpoint_route():
    preflight = build_provider_routing_preflight(
        {
            "provider": "openai",
            "model": "databricks-gemini-2-5-pro",
            "base_url": "https://workspace.example.test/serving-endpoints",
        }
    )

    assert preflight["status"] == "route_ok"
    assert preflight["provider_family"] == "gemini"
    assert preflight["model_family"] == "gemini"
    assert preflight["route_shape"] == "serving_endpoint"
    assert preflight["expected_route_shape"] == "serving_endpoint"
    assert preflight["local_metadata_only"] is True
    assert preflight["external_fetch_performed"] is False
    assert "workspace.example.test" not in json.dumps(preflight, sort_keys=True)


def test_context_budget_preflight_reports_item_truncation_and_text_pressure():
    evidence_package = build_proposal_evidence_package(
        {
            "digest_id": "github-growth-context-preflight",
            "generated_at": "2026-06-16T05:06:01Z",
            "items": [
                {
                    "item_id": "event-1",
                    "source_url": "https://github.com/microsoft/fastcontext/one",
                    "event_kind": "PushEvent",
                    "summary": "x" * 30,
                    "relevance_reason": "y" * 40,
                    "risk_flags": [],
                    "confidence": 0.8,
                },
                {
                    "item_id": "event-2",
                    "source_url": "https://github.com/microsoft/fastcontext/two",
                    "event_kind": "PushEvent",
                    "summary": "overflow",
                    "relevance_reason": "overflow",
                    "risk_flags": [],
                    "confidence": 0.7,
                },
            ],
        },
        self_model_snapshot={"content": "z" * 25},
        max_items=1,
        max_item_text_chars=10,
        max_self_model_chars=5,
    )

    preflight = build_context_budget_preflight(evidence_package)

    assert preflight["status"] == "pressure_detected"
    assert preflight["generated_at"] == "2026-06-16T05:06:01Z"
    assert preflight["input_hash"] == stable_hash(evidence_package)
    assert preflight["input_item_count"] == 2
    assert preflight["kept_item_count"] == 1
    assert preflight["max_items"] == 1
    assert preflight["items_truncated"] is True
    assert preflight["truncated_item_count"] == 1
    assert preflight["whole_item_truncated_count"] == 1
    assert preflight["text_truncated_item_count"] == 1
    assert preflight["truncated_field_count"] == 2
    assert preflight["input_text_chars"] == 86
    assert preflight["selected_text_original_chars"] == 70
    assert preflight["selected_text_chars"] == 20
    assert preflight["field_truncated_text_chars"] == 50
    assert preflight["item_selection_strategy"] == "risk_flags_then_confidence_then_original_order"
    assert preflight["selected_item_ids"] == ["event-1"]
    assert preflight["truncated_item_ids"] == ["event-2"]
    assert preflight["excluded_item_count"] == 0
    assert preflight["item_selection_diagnostics"] == [
        {
            "original_index": 0,
            "rank": 1,
            "item_id": "event-1",
            "decision": "selected",
            "reason": "confidence",
            "risk_flag_count": 0,
            "confidence": 0.8,
            "truncated_fields": ["summary", "relevance_reason"],
        },
        {
            "original_index": 1,
            "rank": 2,
            "item_id": "event-2",
            "decision": "truncated",
            "reason": "max_items_exceeded",
            "risk_flag_count": 0,
            "confidence": 0.7,
            "truncated_fields": [],
        },
    ]
    assert preflight["self_model_truncated"] is True
    assert preflight["local_metadata_only"] is True
    assert preflight["external_fetch_performed"] is False
    assert "fastcontext" not in json.dumps(preflight, sort_keys=True)


def test_context_budget_preflight_reports_cumulative_text_accounting_under_pressure():
    digest = {
        "digest_id": "github-growth-cumulative-context",
        "generated_at": "2026-06-16T06:26:01Z",
        "items": [
            {
                "item_id": "tie-first",
                "source_url": "https://github.com/microsoft/fastcontext/tie-first",
                "event_kind": "IssueCommentEvent",
                "summary": "a" * 9,
                "relevance_reason": "b" * 11,
                "risk_flags": [],
                "confidence": 0.6,
            },
            {
                "item_id": "risk-kept",
                "source_url": "https://github.com/omnigent-ai/omnigent/risk-kept",
                "event_kind": "PullRequestEvent",
                "summary": "c" * 15,
                "relevance_reason": "d" * 7,
                "risk_flags": ["privacy-leakage"],
                "confidence": 0.2,
            },
            {
                "item_id": "tie-second",
                "source_url": "https://github.com/microsoft/fastcontext/tie-second",
                "event_kind": "PushEvent",
                "summary": "e" * 8,
                "relevance_reason": "f" * 12,
                "risk_flags": [],
                "confidence": 0.6,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=10)
    preflight = build_context_budget_preflight(evidence_package)

    assert evidence_package["context_budget"]["selected_item_ids"] == ["risk-kept", "tie-first"]
    assert evidence_package["context_budget"]["truncated_item_ids"] == ["tie-second"]
    assert preflight["status"] == "pressure_detected"
    assert preflight["input_item_count"] == 3
    assert preflight["kept_item_count"] == 2
    assert preflight["truncated_item_count"] == 1
    assert preflight["whole_item_truncated_count"] == 1
    assert preflight["text_truncated_item_count"] == 2
    assert preflight["truncated_field_count"] == 2
    assert preflight["input_text_chars"] == 62
    assert preflight["selected_text_original_chars"] == 42
    assert preflight["selected_text_chars"] == 36
    assert preflight["field_truncated_text_chars"] == 6
    assert [
        (item["item_id"], item["decision"], item["rank"], item["truncated_fields"])
        for item in preflight["item_selection_diagnostics"]
    ] == [
        ("tie-first", "selected", 2, ["relevance_reason"]),
        ("risk-kept", "selected", 1, ["summary"]),
        ("tie-second", "truncated", 3, []),
    ]
    assert "github.com" not in json.dumps(preflight, sort_keys=True)


def test_context_budget_preflight_reports_empty_and_excluded_selection_cases():
    empty_package = build_proposal_evidence_package(
        {
            "digest_id": "github-growth-empty-context",
            "generated_at": "2026-06-16T06:06:01Z",
            "items": [],
        }
    )

    empty_preflight = build_context_budget_preflight(empty_package)

    assert empty_preflight["status"] == "within_budget"
    assert empty_preflight["input_item_count"] == 0
    assert empty_preflight["kept_item_count"] == 0
    assert empty_preflight["selected_item_ids"] == []
    assert empty_preflight["truncated_item_ids"] == []
    assert empty_preflight["excluded_item_count"] == 0
    assert empty_preflight["item_selection_diagnostics"] == []

    mixed_package = build_proposal_evidence_package(
        {
            "digest_id": "github-growth-mixed-context",
            "generated_at": "2026-06-16T06:06:01Z",
            "items": [
                "not an object",
                {
                    "item_id": "safe-evidence",
                    "source_url": "https://github.com/microsoft/fastcontext/safe",
                    "event_kind": "PushEvent",
                    "summary": "usable signal",
                    "relevance_reason": "ranked signal",
                    "risk_flags": [],
                    "confidence": 0.6,
                },
            ],
        },
        max_items=2,
    )

    mixed_preflight = build_context_budget_preflight(mixed_package)

    assert mixed_preflight["kept_item_count"] == 1
    assert mixed_preflight["selected_item_ids"] == ["safe-evidence"]
    assert mixed_preflight["excluded_item_count"] == 1
    assert mixed_preflight["item_selection_diagnostics"] == [
        {
            "original_index": 0,
            "item_id": "",
            "decision": "excluded",
            "reason": "non_object_item",
        },
        {
            "original_index": 1,
            "rank": 1,
            "item_id": "safe-evidence",
            "decision": "selected",
            "reason": "confidence",
            "risk_flag_count": 0,
            "confidence": 0.6,
            "truncated_fields": [],
        },
    ]
    assert "fastcontext" not in json.dumps(mixed_preflight, sort_keys=True)


def test_llm_proposals_preserve_non_safety_routes_for_local_validation(tmp_path):
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
    output_dir = tmp_path / "out"

    def runner(command, **kwargs):
        preflight_path = output_dir / "latest-context-budget-preflight.json"
        assert preflight_path.exists()
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        assert preflight["local_metadata_only"] is True
        assert preflight["external_fetch_performed"] is False
        assert "https://github.com" not in json.dumps(preflight, sort_keys=True)
        last_message = command[command.index("--output-last-message") + 1]
        payload = {
            "schema_version": 1,
            "input_digest_id": digest["digest_id"],
            "run_interpretation": "The runner signal is a locally valid capability route.",
            "self_model_reading": {"status": "not_used"},
            "proposals": [
                {
                    "proposal_id": "llm-runner-route",
                    "kind": "code_patch",
                    "summary": "Add a runner capability preflight for configured local execution.",
                    "evidence_refs": [signals[0].event_id],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally that configured runner preflight records capability state.",
                    "rationale": "The route is useful when configuration provides the runner capability.",
                    "uncertainty": "No external runner is assumed during tests.",
                    "self_effect": "Lets future capability routes become implementation candidates.",
                    "action_lane": "local_validation_candidate",
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
        output_dir=output_dir,
        repo_path=tmp_path,
        command_runner=runner,
    )

    assert proposals[0]["proposal_source"] == "llm_interpretation"
    assert proposals[0]["kind"] == "code_patch"
    assert proposals[0]["risk_flags"] == []
    assert proposals[0]["implementation_scope"] == "local_validation_candidate"
    assert proposals[0]["validation_gate"] == "narrow-local-verification"
    assert "configured runner preflight records capability state" in proposals[0]["validation_task"]
    review = json.loads((output_dir / "latest-llm-proposal-review.json").read_text(encoding="utf-8"))
    assert review["status"] == "accepted"
    assert (output_dir / "latest-growth-interpretation.json").exists()


def test_llm_candidate_privacy_leakage_language_is_review_gated(tmp_path):
    event = normalize_event(
        "example/repo",
        event_payload("diagnostics", "PushEvent", "improve agent provider diagnostics"),
    )
    signals = extract_growth_signals([event], topics=["agent"])
    heuristic = build_proposals(signals)
    digest = build_digest(
        ["example/repo"],
        signals,
        state=GrowthState(),
        generated_at="2026-06-15T08:30:00Z",
        proposals=heuristic,
    )

    def runner(command, **kwargs):
        last_message = command[command.index("--output-last-message") + 1]
        payload = {
            "schema_version": 1,
            "input_digest_id": digest["digest_id"],
            "run_interpretation": "The candidate crosses the privacy boundary.",
            "self_model_reading": {"status": "not_used"},
            "proposals": [
                {
                    "proposal_id": "llm-token-log-route",
                    "kind": "code_patch",
                    "summary": "Add diagnostics that log auth token values for provider preflight.",
                    "evidence_refs": [signals[0].event_id],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally that the route is privacy reviewed.",
                    "rationale": "The diagnostic would expose sensitive data.",
                    "uncertainty": "The evidence itself did not contain the privacy risk.",
                    "self_effect": "Keeps privacy leakage as a hard review boundary.",
                    "action_lane": "local_validation_candidate",
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
    assert proposals[0]["risk_flags"] == ["privacy-leakage"]
    assert proposals[0]["implementation_scope"] == "reviewable_proposal_only"
    assert proposals[0]["validation_gate"] == "privacy-leakage-human-review"
    assert "do not expose, log, print, upload, publish, or share" in proposals[0]["validation_task"]


def test_llm_controller_internal_governance_candidate_can_apply_after_local_validation(tmp_path):
    event = normalize_event(
        "omnigent-ai/omnigent",
        event_payload("governance", "PushEvent", "agent policy gates for spend and tool access"),
    )
    signals = extract_growth_signals([event], topics=["agent"])
    heuristic = build_proposals(signals)
    digest = build_digest(
        ["omnigent-ai/omnigent"],
        signals,
        state=GrowthState(),
        generated_at="2026-06-15T16:21:46Z",
        proposals=heuristic,
    )

    def runner(command, **kwargs):
        last_message = command[command.index("--output-last-message") + 1]
        payload = {
            "schema_version": 1,
            "input_digest_id": digest["digest_id"],
            "run_interpretation": "The useful route is a local controller-internal validation test.",
            "self_model_reading": {"status": "aligned"},
            "proposals": [
                {
                    "proposal_id": "llm-controller-scope-test",
                    "kind": "test",
                    "summary": "Add a local controller metadata test for proposal scope classification gates.",
                    "evidence_refs": [signals[0].event_id],
                    "added_risk_flags": [],
                    "validation_task": (
                        "Create tests that confirm governance-tagged evidence can change local proposal "
                        "scope metadata when validation covers it."
                    ),
                    "rationale": "This changes controller classification evidence with focused validation.",
                    "uncertainty": "The upstream behavior is adapted only through local tests.",
                    "self_effect": "Improves controller scope mapping for autonomous local changes.",
                    "action_lane": "local_validation_candidate",
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
    plan = build_self_evolution_plan(
        {
            "digest_id": digest["digest_id"],
            "generated_at": digest["generated_at"],
            "proposals": [proposals[0]],
        },
        repo_path=tmp_path,
    )

    assert proposals[0]["proposal_source"] == "llm_interpretation"
    assert proposals[0]["kind"] == "test"
    assert proposals[0]["risk_flags"] == []
    assert proposals[0]["implementation_scope"] == "local_validation_candidate"
    assert proposals[0]["validation_gate"] == "narrow-local-verification"
    assert "scope metadata when validation covers it" in proposals[0]["validation_task"]
    assert plan is not None
    assert "Autonomous local apply: True" in plan.task
    assert "Implementation scope: local_validation_candidate" in plan.task


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

    assert signals[0].risk_flags == []
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "focused-evidence-review"
    assert "extract one reusable pattern" in proposal["validation_task"]
    assert plan is not None
    assert "Implementation scope: local_validation_candidate" in plan.task
    assert "Validation gate: focused-evidence-review" in plan.task


def test_repository_trend_direct_governance_language_can_apply_after_local_validation(tmp_path):
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

    assert signals[0].risk_flags == []
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "focused-evidence-review"
    assert "extract one reusable pattern" in proposal["validation_task"]
    assert plan is not None
    assert "Implementation scope: local_validation_candidate" in plan.task
    assert "Validation gate: focused-evidence-review" in plan.task
    assert "extract one reusable pattern" in plan.task


def test_repository_trend_security_harness_is_not_review_gated_without_offensive_or_privacy_signal(tmp_path):
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

    assert signals[0].risk_flags == []
    assert signals[0].recommended_action == (
        "review the repository for reusable patterns and turn only one concrete lesson into a validation task"
    )
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "focused-evidence-review"
    assert "extract one reusable pattern" in proposal["validation_task"]
    assert plan is not None
    assert "Validation gate: focused-evidence-review" in plan.task
    assert "Autonomous local apply: True" in plan.task


def test_repository_trend_agent_harness_can_be_behavior_or_report_work(tmp_path):
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

    assert signals[0].risk_flags == []
    assert proposal["kind"] == "follow_up_issue"
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "focused-evidence-review"
    assert "extract one reusable pattern" in proposal["validation_task"]
    assert "validation_report_requirement" not in proposal_manifest_control(proposal)
    assert plan is not None
    assert "Validation gate: focused-evidence-review" in plan.task
    assert "Autonomous local apply: True" in plan.task


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
    assert "use configured local capabilities" in plan.task
    assert "review only offensive behavior, abuse, unauthorized access, or privacy leakage" in plan.task
    assert "record push, promotion, restart, runner, or remote-execution changes" in plan.task
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
    assert "If no other safe repository change is available, a self-model revision can be the proportionate improvement for the run." in plan.task
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
    assert "Make one bounded, coherent improvement per kernel run" in rendered
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
        "startup_health_checks",
        "outcomes",
        "rollback_ref",
        "provenance",
        "skipped_capabilities",
        "runtime_capability_changes",
        "completion_requirements",
        "completion_status",
        "adoption_decision",
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


def test_self_evolution_manifest_records_local_governance_controls(tmp_path):
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
            "kind": "test",
            "implementation_scope": "local_validation_candidate",
            "validation_gate": "narrow-local-verification",
            "autonomous_local_apply": "True",
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
    assert report["template_version"] == 3
    assert report["required_fields"] == [
        "evidence_urls",
        "pre_adoption_risk_review",
        "local_commands",
        "startup_health_checks",
        "outcomes",
        "rollback_ref",
        "provenance",
        "skipped_capabilities",
        "runtime_capability_changes",
        "completion_requirements",
        "completion_status",
        "adoption_decision",
        "uncertainty",
    ]
    assert report["evidence_urls"] == ["https://github.com/samarailly51-pixel/opencode-harness"]
    assert report["pre_adoption_risk_review"] == {
        "hypothesis": "",
        "expected_local_benefit": "",
        "safety_questions": [
            "What behavior would change if this lesson were adopted?",
            "Which local tests or artifacts prove the lesson before behavior changes?",
            "Which import or startup command proves the adopted behavior does not break activation?",
            "Which runtime capabilities, if any, would be required but are intentionally skipped?",
        ],
        "decision": "pending",
    }
    assert report["provenance"] == {
        "source_digest_id": "github-growth-harness-validation",
        "proposal_ids": [proposal["proposal_id"]],
        "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
        "validation_gates": ["focused-evidence-review"],
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
    assert report["startup_health_checks"] == [
        {
            "command": "",
            "purpose": "prove imports and startup paths touched by the candidate still load",
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
    assert report["skipped_capabilities"] == ["none recorded"]
    assert report["runtime_capability_changes"] == []
    assert "Capability changes are allowed" in report["runtime_capability_change_policy"]
    assert report["adoption_decision"] == {
        "status": "pending",
        "allowed_statuses": ["pending", "adopted", "rejected", "deferred"],
        "rationale": "",
        "decided_at": "",
    }
    assert any(
        requirement.startswith("rollback_ref must name the concrete local rollback ref")
        for requirement in report["completion_requirements"]
    )
    assert any(
        requirement.startswith("runtime_capability_changes must list material capability changes")
        for requirement in report["completion_requirements"]
    )
    assert any(
        requirement.startswith("completion_status.is_complete must stay false")
        for requirement in report["completion_requirements"]
    )
    assert report["completion_status"]["status"] == "draft_template"
    assert report["completion_status"]["adoption_state"] == "draft"
    assert report["completion_status"]["allowed_adoption_states"] == [
        "draft",
        "incomplete",
        "rejected",
        "adoption-ready",
    ]
    assert report["completion_status"]["capability_changes_allowed"] is True
    assert report["completion_status"]["runtime_capability_changes_recorded"] is False
    assert report["completion_status"]["is_complete"] is False
    assert report["completion_status"]["adoption_evidence_complete"] is False
    assert "pre_adoption_risk_review.hypothesis is blank" in report["completion_status"]["blocking_reasons"]
    assert "rollback_ref does not name a concrete rollback ref or artifact" in report["completion_status"]["blocking_reasons"]
    assert (
        "provenance.rollback_ref does not name a concrete rollback ref or artifact"
        in report["completion_status"]["blocking_reasons"]
    )
    assert report["validation_gates"] == ["focused-evidence-review"]
    assert "Validation gate: focused-evidence-review" in plan.task
    assert "extract one reusable pattern" in plan.task


def test_validation_report_completion_status_separates_completed_adoption_evidence() -> None:
    report = {
        "required_fields": [
            "evidence_urls",
            "pre_adoption_risk_review",
            "local_commands",
            "startup_health_checks",
            "outcomes",
            "rollback_ref",
            "provenance",
            "skipped_capabilities",
            "runtime_capability_changes",
            "completion_requirements",
            "completion_status",
            "adoption_decision",
            "uncertainty",
        ],
        "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
        "pre_adoption_risk_review": {
            "hypothesis": "Harness evidence supports stricter validation reporting.",
            "expected_local_benefit": "Draft reports cannot be mistaken for adoption proof.",
            "decision": "accept validation-only improvement",
        },
        "local_commands": [
            {
                "command": "uv run pytest tests/test_github_growth.py -q",
                "purpose": "verify report contract",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "startup_health_checks": [
            {
                "command": "uv run python -c \"import blackhole_agent.github_growth\"",
                "purpose": "prove imports",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "outcomes": [
            {
                "check": "validation report completion gate",
                "result": "passed",
                "evidence_artifact": "artifacts/self-evolution/run-notes.md",
            }
        ],
        "rollback_ref": "refs/blackhole-agent/rollback/20260615T154146Z/20260615T154600Z",
        "provenance": {
            "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
            "rollback_ref": "refs/blackhole-agent/rollback/20260615T154146Z/20260615T154600Z",
        },
        "skipped_capabilities": ["remote execution"],
        "runtime_capability_changes": [],
        "completion_requirements": ["rollback_ref names the concrete rollback ref for the run."],
        "adoption_decision": {
            "status": "adopted",
            "rationale": "Only report metadata changed.",
            "decided_at": "2026-06-15T15:46:00Z",
        },
        "uncertainty": [],
    }

    status = validation_report_completion_status(report)

    assert status == {
        "status": "completed_adoption_evidence",
        "adoption_state": "adoption-ready",
        "allowed_adoption_states": ["draft", "incomplete", "rejected", "adoption-ready"],
        "is_complete": True,
        "adoption_evidence_complete": True,
        "capability_changes_allowed": True,
        "runtime_capability_changes_recorded": False,
        "blocking_reasons": [],
    }


def test_validation_report_completion_status_rejects_incomplete_contract_metadata() -> None:
    report = {
        "required_fields": [],
        "evidence_urls": [""],
        "pre_adoption_risk_review": {
            "hypothesis": "Harness evidence supports stricter validation reporting.",
            "expected_local_benefit": "Draft reports cannot be mistaken for adoption proof.",
            "decision": "accept validation-only improvement",
        },
        "local_commands": [
            {
                "command": "uv run pytest tests/test_github_growth.py -q",
                "purpose": "verify report contract",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "startup_health_checks": [
            {
                "command": "uv run python -c \"import blackhole_agent.github_growth\"",
                "purpose": "prove imports",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "outcomes": [
            {
                "check": "validation report completion gate",
                "result": "passed",
                "evidence_artifact": "artifacts/self-evolution/run-notes.md",
            }
        ],
        "rollback_ref": "refs/blackhole-agent/rollback/20260615T154146Z/20260615T154600Z",
        "skipped_capabilities": [""],
        "runtime_capability_changes": [],
        "completion_requirements": [""],
        "adoption_decision": {
            "status": "adopted",
            "rationale": "Only report metadata changed.",
            "decided_at": "2026-06-15T15:46:00Z",
        },
        "uncertainty": [],
    }

    status = validation_report_completion_status(report)

    assert status["status"] == "draft_template"
    assert status["adoption_state"] == "incomplete"
    assert status["is_complete"] is False
    assert status["adoption_evidence_complete"] is False
    assert "required_fields does not match the validation report contract" in status["blocking_reasons"]
    assert "evidence_urls[0] is blank" in status["blocking_reasons"]
    assert "skipped_capabilities[0] is blank" in status["blocking_reasons"]
    assert "completion_requirements[0] is blank" in status["blocking_reasons"]


def test_validation_report_completion_status_requires_explicit_passing_outcome() -> None:
    report = {
        "required_fields": [
            "evidence_urls",
            "pre_adoption_risk_review",
            "local_commands",
            "startup_health_checks",
            "outcomes",
            "rollback_ref",
            "provenance",
            "skipped_capabilities",
            "runtime_capability_changes",
            "completion_requirements",
            "completion_status",
            "adoption_decision",
            "uncertainty",
        ],
        "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
        "pre_adoption_risk_review": {
            "hypothesis": "Harness evidence supports stricter validation reporting.",
            "expected_local_benefit": "Ambiguous outcomes cannot be mistaken for completed evidence.",
            "decision": "accept validation-only improvement",
        },
        "local_commands": [
            {
                "command": "uv run pytest tests/test_github_growth.py -q",
                "purpose": "verify report contract",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "startup_health_checks": [
            {
                "command": "uv run python -c \"import blackhole_agent.github_growth\"",
                "purpose": "prove imports",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "outcomes": [
            {
                "check": "validation report completion gate",
                "result": "investigated",
                "evidence_artifact": "artifacts/self-evolution/run-notes.md",
            }
        ],
        "rollback_ref": "refs/blackhole-agent/rollback/20260615T162146Z/20260615T162600Z",
        "provenance": {
            "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
            "rollback_ref": "refs/blackhole-agent/rollback/20260615T162146Z/20260615T162600Z",
        },
        "skipped_capabilities": ["remote execution"],
        "runtime_capability_changes": [],
        "completion_requirements": ["rollback_ref names the concrete rollback ref for the run."],
        "adoption_decision": {
            "status": "adopted",
            "rationale": "Only report metadata changed.",
            "decided_at": "2026-06-15T16:26:00Z",
        },
        "uncertainty": [],
    }

    status = validation_report_completion_status(report)

    assert "outcomes[0].result must be one of: adopted, pass, passed, reviewed" in status["blocking_reasons"]
    assert status["status"] == "draft_template"
    assert status["adoption_state"] == "incomplete"
    assert status["is_complete"] is False
    assert status["adoption_evidence_complete"] is False


def test_validation_report_completion_status_requires_matching_provenance_rollback_ref() -> None:
    report = {
        "required_fields": [
            "evidence_urls",
            "pre_adoption_risk_review",
            "local_commands",
            "startup_health_checks",
            "outcomes",
            "rollback_ref",
            "provenance",
            "skipped_capabilities",
            "runtime_capability_changes",
            "completion_requirements",
            "completion_status",
            "adoption_decision",
            "uncertainty",
        ],
        "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
        "pre_adoption_risk_review": {
            "hypothesis": "Harness evidence supports stricter validation reporting.",
            "expected_local_benefit": "Replay metadata must point at the concrete rollback anchor.",
            "decision": "accept validation-only improvement",
        },
        "local_commands": [
            {
                "command": "uv run pytest tests/test_github_growth.py -q",
                "purpose": "verify report contract",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "startup_health_checks": [
            {
                "command": "uv run python -c \"import blackhole_agent.github_growth\"",
                "purpose": "prove imports",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "outcomes": [
            {
                "check": "validation report completion gate",
                "result": "passed",
                "evidence_artifact": "artifacts/self-evolution/run-notes.md",
            }
        ],
        "rollback_ref": "refs/blackhole-agent/rollback/20260615T163717Z/20260615T163900Z",
        "provenance": {
            "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
            "rollback_ref": "recorded in latest-rollback-point.json when codex mode prepares the branch",
        },
        "skipped_capabilities": ["remote execution"],
        "runtime_capability_changes": [],
        "completion_requirements": ["provenance.rollback_ref matches rollback_ref."],
        "adoption_decision": {
            "status": "adopted",
            "rationale": "Only report metadata changed.",
            "decided_at": "2026-06-15T16:39:00Z",
        },
        "uncertainty": [],
    }

    status = validation_report_completion_status(report)

    assert status["status"] == "draft_template"
    assert status["adoption_state"] == "incomplete"
    assert status["is_complete"] is False
    assert status["adoption_evidence_complete"] is False
    assert "provenance.rollback_ref does not name a concrete rollback ref or artifact" in status["blocking_reasons"]


def test_validation_report_completion_status_requires_matching_provenance_evidence_urls() -> None:
    report = {
        "required_fields": [
            "evidence_urls",
            "pre_adoption_risk_review",
            "local_commands",
            "startup_health_checks",
            "outcomes",
            "rollback_ref",
            "provenance",
            "skipped_capabilities",
            "runtime_capability_changes",
            "completion_requirements",
            "completion_status",
            "adoption_decision",
            "uncertainty",
        ],
        "evidence_urls": [
            "https://github.com/omnigent-ai/omnigent/issues/241",
            "https://github.com/samarailly51-pixel/opencode-harness",
        ],
        "pre_adoption_risk_review": {
            "hypothesis": "Harness evidence supports replayable validation reporting.",
            "expected_local_benefit": "Completed reports can be replayed from provenance metadata.",
            "decision": "accept validation-only improvement",
        },
        "local_commands": [
            {
                "command": "uv run pytest tests/test_github_growth.py -q",
                "purpose": "verify report contract",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "startup_health_checks": [
            {
                "command": "uv run python -c \"import blackhole_agent.github_growth\"",
                "purpose": "prove imports",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "outcomes": [
            {
                "check": "validation report provenance evidence gate",
                "result": "passed",
                "evidence_artifact": "artifacts/self-evolution/run-notes.md",
            }
        ],
        "rollback_ref": "refs/blackhole-agent/rollback/20260616T034147Z/d93f771ac5c3",
        "provenance": {
            "evidence_urls": ["https://github.com/samarailly51-pixel/opencode-harness"],
            "rollback_ref": "refs/blackhole-agent/rollback/20260616T034147Z/d93f771ac5c3",
        },
        "skipped_capabilities": ["new agent harnesses", "remote execution"],
        "runtime_capability_changes": [],
        "completion_requirements": ["provenance.evidence_urls matches evidence_urls."],
        "adoption_decision": {
            "status": "adopted",
            "rationale": "Only report metadata changed.",
            "decided_at": "2026-06-16T03:41:47Z",
        },
        "uncertainty": ["External harness behavior was reviewed as evidence only."],
    }

    status = validation_report_completion_status(report)

    assert status["status"] == "draft_template"
    assert status["adoption_state"] == "incomplete"
    assert status["is_complete"] is False
    assert status["adoption_evidence_complete"] is False
    assert "provenance.evidence_urls does not match evidence_urls" in status["blocking_reasons"]


def test_validation_report_completion_status_classifies_rejected_review_evidence() -> None:
    report = {
        "required_fields": [
            "evidence_urls",
            "pre_adoption_risk_review",
            "local_commands",
            "startup_health_checks",
            "outcomes",
            "rollback_ref",
            "provenance",
            "skipped_capabilities",
            "runtime_capability_changes",
            "completion_requirements",
            "completion_status",
            "adoption_decision",
            "uncertainty",
        ],
        "evidence_urls": ["https://github.com/visa/visa-vulnerability-agentic-harness"],
        "pre_adoption_risk_review": {
            "hypothesis": "Security harness evidence is useful only as review metadata here.",
            "expected_local_benefit": "Unsafe adoption can be recorded without enabling scanner behavior.",
            "decision": "reject direct behavior adoption",
        },
        "local_commands": [
            {
                "command": "uv run pytest tests/test_github_growth.py -q",
                "purpose": "verify report contract",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "startup_health_checks": [
            {
                "command": "uv run python -c \"import blackhole_agent.github_growth\"",
                "purpose": "prove imports",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "outcomes": [
            {
                "check": "security harness lesson recorded as rejected local adoption",
                "result": "reviewed",
                "evidence_artifact": "artifacts/self-evolution/run-notes.md",
            }
        ],
        "rollback_ref": "refs/blackhole-agent/rollback/20260616T030148Z/64a05c39cf2e",
        "provenance": {
            "evidence_urls": ["https://github.com/visa/visa-vulnerability-agentic-harness"],
            "rollback_ref": "refs/blackhole-agent/rollback/20260616T030148Z/64a05c39cf2e",
        },
        "skipped_capabilities": ["remote execution", "security scanning"],
        "runtime_capability_changes": [],
        "completion_requirements": ["runtime_capability_changes stays empty."],
        "adoption_decision": {
            "status": "rejected",
            "rationale": "The lesson is restricted to validation metadata.",
            "decided_at": "2026-06-16T03:01:48Z",
        },
        "uncertainty": ["External findings remain human-reviewed triage candidates."],
    }

    status = validation_report_completion_status(report)

    assert status["status"] == "completed_review_evidence"
    assert status["adoption_state"] == "rejected"
    assert status["is_complete"] is True
    assert status["adoption_evidence_complete"] is False
    assert status["capability_changes_allowed"] is True
    assert status["runtime_capability_changes_recorded"] is False
    assert status["blocking_reasons"] == []


def test_validation_report_completion_status_rejects_conflicting_decisions() -> None:
    report = {
        "required_fields": [
            "evidence_urls",
            "pre_adoption_risk_review",
            "local_commands",
            "startup_health_checks",
            "outcomes",
            "rollback_ref",
            "provenance",
            "skipped_capabilities",
            "runtime_capability_changes",
            "completion_requirements",
            "completion_status",
            "adoption_decision",
            "uncertainty",
        ],
        "evidence_urls": ["https://github.com/omnigent-ai/omnigent"],
        "pre_adoption_risk_review": {
            "hypothesis": "Harness evidence supports stricter validation reporting.",
            "expected_local_benefit": "Contradictory decisions cannot be mistaken for completed evidence.",
            "decision": "defer behavior adoption until controller validation is explicit",
        },
        "local_commands": [
            {
                "command": "uv run pytest tests/test_github_growth.py -q",
                "purpose": "verify report contract",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "startup_health_checks": [
            {
                "command": "uv run python -c \"import blackhole_agent.github_growth\"",
                "purpose": "prove imports",
                "cwd": "C:/repo",
                "exit_code": 0,
            }
        ],
        "outcomes": [
            {
                "check": "validation report decision consistency",
                "result": "passed",
                "evidence_artifact": "artifacts/self-evolution/run-notes.md",
            }
        ],
        "rollback_ref": "refs/blackhole-agent/rollback/20260616T032148Z/8bb216ec66cf",
        "provenance": {
            "evidence_urls": ["https://github.com/omnigent-ai/omnigent"],
            "rollback_ref": "refs/blackhole-agent/rollback/20260616T032148Z/8bb216ec66cf",
        },
        "skipped_capabilities": ["model selection", "remote execution"],
        "runtime_capability_changes": [],
        "completion_requirements": ["pre_adoption_risk_review.decision aligns with adoption_decision.status."],
        "adoption_decision": {
            "status": "adopted",
            "rationale": "Only report metadata changed.",
            "decided_at": "2026-06-16T03:21:48Z",
        },
        "uncertainty": ["External harness capabilities remain review evidence only."],
    }

    status = validation_report_completion_status(report)

    assert status["status"] == "draft_template"
    assert status["adoption_state"] == "incomplete"
    assert status["is_complete"] is False
    assert status["adoption_evidence_complete"] is False
    assert (
        "pre_adoption_risk_review.decision conflicts with adoption_decision.status"
        in status["blocking_reasons"]
    )


def test_self_evolution_manifest_records_privacy_leakage_safety_boundary(tmp_path):
    event = normalize_event(
        "example/repo",
        event_payload("privacy", "PushEvent", "log auth token to validation report"),
    )
    proposal = build_proposals(extract_growth_signals([event], topics=["security", "agent"]))[0]
    assert proposal_manifest_control(proposal)["safety_boundary_requirement"] == (
        "Only offensive behavior, abuse, unauthorized access, or privacy leakage is review-only; "
        "all other rollback-backed local changes may proceed."
    )
    plan = build_self_evolution_plan(
        {
            "digest_id": "github-growth-privacy-boundary",
            "generated_at": "2026-06-15T07:21:28Z",
            "proposals": [proposal],
        },
        repo_path=tmp_path,
    )
    assert plan is not None

    def runner(command, **kwargs):
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="privacy-head\n", stderr="")
        last_message = command[command.index("--output-last-message") + 1]
        with open(last_message, "w", encoding="utf-8") as handle:
            handle.write("codex done")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    run_self_evolution_codex(plan, output_dir=tmp_path / "out", command_runner=runner)

    manifest = json.loads((tmp_path / "out" / "latest-self-evolution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["validation_gates"] == ["privacy-leakage-human-review"]
    assert manifest["proposal_controls"] == [
        {
            "proposal_id": "privacy-1",
            "kind": "follow_up_issue",
            "implementation_scope": "reviewable_proposal_only",
            "validation_gate": "privacy-leakage-human-review",
            "autonomous_local_apply": (
                "False (reviewable proposal only; local validation artifacts may still be updated)"
            ),
            "safety_boundary_requirement": (
                "Only offensive behavior, abuse, unauthorized access, or privacy leakage is review-only; "
                "all other rollback-backed local changes may proceed."
            ),
        }
    ]
