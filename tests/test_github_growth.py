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
    proposal_validation_preflight,
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
    build_route_hint_lane_map,
    build_context_budget_preflight,
    build_provider_routing_preflight,
    build_proposal_evidence_package,
    classify_digest_item_route,
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
    elif kind == "PullRequestReviewEvent":
        payload = {
            "action": "submitted",
            "pull_request": {
                "title": title,
                "html_url": "https://github.com/example/repo/pull/1",
            },
            "review": {
                "state": "commented",
                "body": "Please add validation coverage.",
                "html_url": "https://github.com/example/repo/pull/1#pullrequestreview-1",
            },
        }
    elif kind == "PullRequestReviewCommentEvent":
        payload = {
            "action": "created",
            "pull_request": {
                "title": title,
                "html_url": "https://github.com/example/repo/pull/1",
            },
            "comment": {
                "body": "This needs a focused smoke test.",
                "html_url": "https://github.com/example/repo/pull/1#discussion_r1",
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
            "--model",
            "gpt-5.5",
            "--claude-sdk-permission-mode",
            "auto",
            "--allow-claude-sdk-auto-permission-mode",
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
    assert codex_commands[0][codex_commands[0].index("--model") + 1] == "gpt-5.5"
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
    assert run["codex_cli"]["claude_sdk_permission_mode"] == "auto"
    assert run["codex_cli"]["allow_claude_sdk_auto_permission_mode"] is True
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


def test_normalize_pull_request_review_comment_event_extracts_review_text():
    event = normalize_event(
        "example/repo",
        event_payload("review-comment-1", "PullRequestReviewCommentEvent", "Add agent workflow benchmark"),
    )

    assert event.title == "created pull request review comment: Add agent workflow benchmark"
    assert event.url == "https://github.com/example/repo/pull/1#discussion_r1"
    assert event.summary == "This needs a focused smoke test."


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


def test_push_commit_patterns_keep_clusters_with_clear_test_evidence():
    event = normalize_event(
        "omnigent-ai/omnigent",
        event_payload("test-cluster", "PushEvent", "test(e2e): add comments REST API integration tests"),
    )

    signals = extract_growth_signals([event], topics=["agent"])
    proposal = build_proposals(signals)[0]
    preflight = proposal_validation_preflight(proposal)

    assert proposal["push_pattern_evidence"] == {
        "status": "ready",
        "clusters": ["test-coverage"],
        "has_clear_test_evidence": True,
        "source": "push_commit_message_cluster",
        "policy": "keep_push_patterns_only_when_commit_messages_include_clear_test_or_ci_evidence",
        "matched_text_hash": github_growth.stable_push_message_hash(github_growth.push_message_text(signals[0])),
    }
    assert preflight["status"] == "ready"
    assert preflight["validation_gaps"] == []


def test_push_commit_patterns_mark_generic_workflow_clusters_as_validation_gap():
    events = [
        normalize_event(
            "omnigent-ai/omnigent",
            event_payload("generic-workflow", "PushEvent", "workflow polish for session labels"),
        ),
        normalize_event(
            "omnigent-ai/omnigent",
            event_payload("covered-test", "PushEvent", "test(server/routes): add unit tests for route modules"),
        ),
    ]

    signals = extract_growth_signals(events, topics=["workflow", "test"])
    proposals = build_proposals(signals, limit=2)
    proposals_by_id = {proposal["proposal_id"]: proposal for proposal in proposals}
    generic = proposals_by_id["generic-workflow-2"]
    covered = proposals_by_id["covered-test-1"]

    assert generic["push_pattern_evidence"]["status"] == "evidence_gap"
    assert generic["push_pattern_evidence"]["has_clear_test_evidence"] is False
    assert proposal_validation_preflight(generic)["validation_gaps"] == ["missing_push_pattern_test_evidence"]
    assert covered["push_pattern_evidence"]["status"] == "ready"


def test_llm_interpreted_push_patterns_inherit_test_evidence_gap():
    signal = GrowthSignal(
        event_id="generic-workflow-push",
        repo="omnigent-ai/omnigent",
        kind="PushEvent",
        title="workflow polish for session labels",
        url="https://github.com/omnigent-ai/omnigent",
        relevance_reason="push commit message names workflow polish without validation proof",
        risk_flags=[],
        recommended_action="cluster commit messages and keep only patterns with clear test evidence",
        confidence=0.72,
    )
    proposals = github_growth.clamp_llm_candidates_to_proposals(
        [
            {
                "proposal_id": "llm-generic-workflow-push",
                "kind": "test",
                "summary": "Treat the generic workflow push as a replay candidate.",
                "evidence_refs": ["generic-workflow-push"],
                "validation_task": "Run local tests for push-pattern metadata.",
                "rationale": "The LLM route cites a push-derived pattern and must retain its evidence limits.",
                "uncertainty": "The commit message lacks clear validation proof.",
                "self_effect": "Prevents LLM interpretation from laundering a weak push pattern into ready status.",
                "action_lane": "local_validation_candidate",
            }
        ],
        [signal],
    )

    proposal = proposals[0]
    preflight = proposal_validation_preflight(proposal)

    assert proposal["push_pattern_evidence"]["status"] == "evidence_gap"
    assert proposal["push_pattern_evidence"]["has_clear_test_evidence"] is False
    assert preflight["status"] == "validation_gap"
    assert preflight["validation_gaps"] == ["missing_push_pattern_test_evidence"]


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


def test_skill_and_tool_integration_signals_get_bounded_validation_route():
    event = normalize_event(
        "baskduf/FableCodex",
        {
            "id": "skill-route",
            "type": "IssuesEvent",
            "actor": {"login": "octocat"},
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {
                "action": "opened",
                "issue": {
                    "title": "Codex skills should route workflow gates to plugins",
                    "html_url": "https://github.com/baskduf/FableCodex/issues/12",
                    "body": "Skill routing should recognize workflow gates and tool integrations.",
                },
            },
        },
    )

    signals = extract_growth_signals([event], topics=["skill"])

    assert len(signals) == 1
    assert signals[0].risk_flags == []
    assert signals[0].recommended_action == (
        "map skill, workflow, or tool-integration signals to bounded local validation lanes such as "
        "documentation, config, tests, or code patches"
    )
    proposal = build_proposals(signals)[0]
    assert proposal["implementation_scope"] == "local_validation_candidate"
    assert proposal["validation_gate"] == "narrow-local-verification"


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


def test_proposal_validation_preflight_marks_missing_test_coverage_as_gap_not_safety_block():
    proposal = {
        "proposal_id": "validation-report-not-default",
        "kind": "code_patch",
        "summary": "Improve controller route metadata from Omnigent policy evidence.",
        "risk_flags": [],
        "implementation_scope": "local_validation_candidate",
        "validation_gate": "narrow-local-verification",
        "validation_task": "Validate locally that sufficient evidence keeps this route implementable.",
        "requires_approval": False,
    }

    preflight = proposal_validation_preflight(proposal)
    control = proposal_manifest_control(proposal)

    assert preflight == {
        "status": "validation_gap",
        "requires_unit_test_or_coverage": True,
        "has_unit_test_signal": False,
        "has_coverage_signal": False,
        "validation_gaps": ["missing_unit_test_or_coverage_validation"],
        "safety_block": False,
        "blocks_autonomous_apply": False,
    }
    assert control["autonomous_local_apply"] == "True"
    assert control["validation_preflight"] == preflight
    assert control["review_metadata"]["reviewer_routes"] == [
        "runtime-change-review",
        "validation-maintainer-review",
    ]
    assert control["review_metadata"]["coverage_drop_signal"] == {
        "applies": False,
        "status_on_drop": "not-applicable",
        "blocking": False,
    }
    assert control["review_metadata"]["bypass_label_guard"]["status"] == "passed"


def test_proposal_validation_preflight_accepts_unit_test_or_coverage_validation():
    unit_test_proposal = {
        "proposal_id": "test-covered-route",
        "kind": "test",
        "summary": "Add route classification checks.",
        "risk_flags": [],
        "implementation_scope": "local_validation_candidate",
        "validation_gate": "narrow-local-verification",
        "validation_task": "Create focused tests with local fixtures before applying the behavior.",
        "requires_approval": False,
    }
    coverage_proposal = {
        **unit_test_proposal,
        "proposal_id": "coverage-covered-route",
        "validation_task": "Verify coverage validation records the changed behavior.",
    }

    assert proposal_validation_preflight(unit_test_proposal)["status"] == "ready"
    assert proposal_validation_preflight(unit_test_proposal)["has_unit_test_signal"] is True
    assert proposal_validation_preflight(coverage_proposal)["status"] == "ready"
    assert proposal_validation_preflight(coverage_proposal)["has_coverage_signal"] is True


def test_proposal_validation_preflight_accepts_smoke_fixture_validation_not_generic_validation():
    proposal = {
        "proposal_id": "fixture-covered-route",
        "kind": "test",
        "summary": "Strengthen coverage-gate behavior.",
        "risk_flags": [],
        "implementation_scope": "local_validation_candidate",
        "validation_gate": "narrow-local-verification",
        "validation_task": "Exercise the coverage gate with a small local validation fixture.",
        "requires_approval": False,
    }
    generic_proposal = {
        **proposal,
        "proposal_id": "generic-local-validation",
        "summary": "Improve route behavior.",
        "validation_task": "Validate locally before applying the behavior.",
    }

    preflight = proposal_validation_preflight(proposal)
    generic_preflight = proposal_validation_preflight(generic_proposal)

    assert preflight["status"] == "ready"
    assert preflight["has_unit_test_signal"] is True
    assert preflight["has_coverage_signal"] is True
    assert generic_preflight["status"] == "validation_gap"
    assert generic_preflight["validation_gaps"] == ["missing_unit_test_or_coverage_validation"]


def test_proposal_validation_preflight_keeps_privacy_route_blocked_by_safety_boundary():
    proposal = {
        "proposal_id": "privacy-route",
        "kind": "code_patch",
        "summary": "Handle token logging behavior.",
        "risk_flags": ["privacy-leakage"],
        "implementation_scope": "reviewable_proposal_only",
        "validation_gate": "privacy-leakage-human-review",
        "validation_task": "Keep privacy-leakage behavior review-only.",
        "requires_approval": False,
    }

    preflight = proposal_validation_preflight(proposal)

    assert preflight["status"] == "blocked_by_safety_boundary"
    assert preflight["validation_gaps"] == []
    assert preflight["blocks_autonomous_apply"] is True


def test_proposal_manifest_control_blocks_bypass_style_labels_and_routes_coverage_review():
    proposal = {
        "proposal_id": "coverage-drop-route",
        "kind": "config",
        "summary": "Improve local CI coverage metadata.",
        "risk_flags": [],
        "implementation_scope": "local_validation_candidate",
        "validation_gate": "narrow-local-verification",
        "validation_task": "Run coverage validation and signal coverage drop without blocking merge.",
        "requires_approval": False,
        "labels": ["force-merge", "ci-bypass", "enhancement"],
    }

    control = proposal_manifest_control(proposal)

    assert control["autonomous_local_apply"] == "False (bypass-style labels are ignored and require review)"
    assert control["review_metadata"] == {
        "reviewer_routes": [
            "coverage-review",
            "runtime-change-review",
            "validation-maintainer-review",
        ],
        "coverage_drop_signal": {
            "applies": True,
            "status_on_drop": "red-non-blocking",
            "blocking": False,
        },
        "bypass_label_guard": {
            "status": "blocked",
            "blocked_labels": ["ci-bypass", "force-merge"],
            "policy": "bypass-style labels are metadata only and cannot grant autonomous local apply",
        },
    }


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
            "route_hints": [],
            "route_classification": {
                "route_class": "unclassified",
                "route_hints": [],
                "allowed_lanes": [],
                "reasons": [],
                "runtime_action": "none",
                "local_validation_required": True,
            },
        }
    ]
    assert first["allowed_evidence_urls"] == ["https://github.com/microsoft/fastcontext/issues/123?query=preserve"]
    assert first["context_budget"]["items_truncated"] is True
    assert first["context_budget"]["input_item_count"] == 2
    assert (
        first["context_budget"]["item_selection_strategy"]
        == "risk_flags_then_direct_detail_then_confidence_with_review_activity_and_generic_activity_dedup_then_original_order"
    )
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
                    "uncertainty": "Only synthetic size pressure is covered, and truncated items may hide additional details.",
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
                    "uncertainty": "Synthetic digest only covers ranking behavior, and omitted items may hide additional details.",
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
                    "uncertainty": "Does not call an external model, and truncated items may hide additional details.",
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


def test_proposal_evidence_package_boosts_repeated_review_activity_without_overwhelming_risk_or_direct_evidence():
    digest = {
        "digest_id": "github-growth-review-signal-ranking",
        "generated_at": "2026-06-16T07:46:01Z",
        "items": [
            {
                "item_id": "repo-trend",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "omnigent-ai/omnigent: trending multi-agent harness",
                "relevance_reason": "repository trend has broad harness relevance",
                "risk_flags": [],
                "confidence": 0.61,
            },
            {
                "item_id": "direct-pr",
                "source_url": "https://github.com/omnigent-ai/omnigent/pull/77",
                "event_kind": "PullRequestEvent",
                "summary": "omnigent-ai/omnigent: add validation harness checks",
                "relevance_reason": "direct code patch candidate",
                "risk_flags": [],
                "confidence": 0.7,
            },
            {
                "item_id": "review-event",
                "source_url": "https://github.com/omnigent-ai/omnigent/pull/77#pullrequestreview-1",
                "event_kind": "PullRequestReviewEvent",
                "summary": "omnigent-ai/omnigent: reviewed validation harness checks",
                "relevance_reason": "review activity supports confidence for validation route",
                "risk_flags": [],
                "confidence": 0.62,
            },
            {
                "item_id": "review-comment",
                "source_url": "https://github.com/omnigent-ai/omnigent/pull/77#discussion_r1",
                "event_kind": "PullRequestReviewCommentEvent",
                "summary": "omnigent-ai/omnigent: review comment requests focused tests",
                "relevance_reason": "review comment supports test-harness route",
                "risk_flags": [],
                "confidence": 0.63,
            },
            {
                "item_id": "generic-push",
                "source_url": "https://github.com/omnigent-ai/omnigent/commit/abc123",
                "event_kind": "PushEvent",
                "summary": "omnigent-ai/omnigent: generic dependency cleanup",
                "relevance_reason": "generic push event",
                "risk_flags": [],
                "confidence": 0.58,
            },
            {
                "item_id": "privacy-boundary",
                "source_url": "https://github.com/omnigent-ai/omnigent/issues/5",
                "event_kind": "IssueCommentEvent",
                "summary": "omnigent-ai/omnigent: privacy token boundary",
                "relevance_reason": "risk-gated evidence must stay selected",
                "risk_flags": ["privacy-leakage"],
                "confidence": 0.2,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=200)

    assert evidence_package["policy"]["max_proposals"] == 5
    assert len(evidence_package["items"]) <= evidence_package["policy"]["max_proposals"]
    assert [item["item_id"] for item in evidence_package["items"]] == [
        "privacy-boundary",
        "direct-pr",
        "review-comment",
        "review-event",
    ]
    assert evidence_package["context_budget"]["truncated_item_ids"] == ["repo-trend", "generic-push"]

    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-review-signal-ranking",
            "run_interpretation": "Use repeated upstream review activity as bounded confidence evidence.",
            "self_model_reading": {"status": "unchanged"},
            "proposals": [
                {
                    "proposal_id": "review-signal-test-route",
                    "kind": "test",
                    "summary": "Add ranking coverage for repeated review activity.",
                    "evidence_refs": ["review-comment", "review-event"],
                    "added_risk_flags": [],
                    "validation_task": "Replay synthetic review activity ranking locally.",
                    "rationale": "Repeated PR review comments are useful confidence signals for validation routes.",
                    "uncertainty": "Synthetic fixture only covers bounded ranking behavior, and truncated items may hide additional details.",
                    "self_effect": "Improves trend intelligence proposal selection.",
                    "action_lane": "local_validation_candidate",
                }
            ],
            "rejected_items": ["repo-trend", "generic-push"],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="hybrid")

    assert review.status == "accepted"
    assert review.accepted_count <= evidence_package["policy"]["max_proposals"]
    assert review.accepted_candidates[0]["evidence_refs"] == ["review-comment", "review-event"]
    assert review.accepted_candidates[0]["evidence_urls"] == [
        "https://github.com/omnigent-ai/omnigent/pull/77#discussion_r1",
        "https://github.com/omnigent-ai/omnigent/pull/77#pullrequestreview-1",
    ]


def test_proposal_evidence_package_downweights_generic_shepherd_activity_before_direct_details():
    digest = {
        "digest_id": "github-growth-shepherd-activity-ranking",
        "generated_at": "2026-07-06T15:35:55Z",
        "items": [
            {
                "item_id": "shepherd-generic-pr-opened",
                "source_url": "https://github.com/shepherd-agents/shepherd/pull/25",
                "event_kind": "PullRequestEvent",
                "summary": "opened pull request: untitled pull request",
                "relevance_reason": "generic PullRequestEvent item with missing PR details",
                "risk_flags": [],
                "confidence": 0.93,
            },
            {
                "item_id": "shepherd-generic-push-1",
                "source_url": "https://github.com/shepherd-agents/shepherd/commit/111",
                "event_kind": "PushEvent",
                "summary": "shepherd-agents/shepherd: pushed generic workflow polish",
                "relevance_reason": "generic push activity without actionable route detail",
                "risk_flags": [],
                "confidence": 0.91,
            },
            {
                "item_id": "shepherd-generic-push-2",
                "source_url": "https://github.com/shepherd-agents/shepherd/commit/222",
                "event_kind": "PushEvent",
                "summary": "shepherd-agents/shepherd: pushed generic workflow polish",
                "relevance_reason": "generic push activity without actionable route detail",
                "risk_flags": [],
                "confidence": 0.89,
            },
            {
                "item_id": "shepherd-provider-failure-issue",
                "source_url": "https://github.com/shepherd-agents/shepherd/issues/23",
                "event_kind": "IssuesEvent",
                "summary": (
                    "claude CLI agent lane fails with ProviderInvocationError and empty envelope "
                    "even though doctor reports green"
                ),
                "relevance_reason": "direct provider failure detail exposes a route diagnostic and recovery hint",
                "risk_flags": [],
                "confidence": 0.72,
            },
            {
                "item_id": "shepherd-recovery-pr",
                "source_url": "https://github.com/shepherd-agents/shepherd/pull/26",
                "event_kind": "PullRequestEvent",
                "summary": "feat(recovery): recover cleanly from interrupted runs",
                "relevance_reason": "direct recovery work names run-start auto-recovery and manual repair",
                "risk_flags": [],
                "confidence": 0.7,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=240)

    assert [item["item_id"] for item in evidence_package["items"]] == [
        "shepherd-provider-failure-issue",
        "shepherd-recovery-pr",
    ]
    assert evidence_package["context_budget"]["truncated_item_ids"] == [
        "shepherd-generic-pr-opened",
        "shepherd-generic-push-1",
        "shepherd-generic-push-2",
    ]
    uncertainty = evidence_package["context_budget"]["evidence_truncation_uncertainty"]
    assert uncertainty["selected_generic_pr_count"] == 0
    assert uncertainty["truncated_generic_pr_count"] == 1
    assert uncertainty["selected_generic_push_count"] == 0
    assert uncertainty["truncated_generic_push_count"] == 2
    assert (
        evidence_package["context_budget"]["item_selection_strategy"]
        == "risk_flags_then_direct_detail_then_confidence_with_review_activity_and_generic_activity_dedup_then_original_order"
    )


def test_proposal_evidence_package_marks_skill_workflow_route_hints():
    digest = {
        "digest_id": "github-growth-skill-route-discovery",
        "generated_at": "2026-06-17T15:00:01Z",
        "items": [
            {
                "item_id": "fablecodex-skill-workflow",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": "baskduf/FableCodex: Codex skills and workflow gates for local agent work",
                "relevance_reason": "Skill and workflow evidence should propose bounded local validation lanes.",
                "risk_flags": [],
                "confidence": 0.87,
            },
            {
                "item_id": "compass-skills-system",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "dongshuyan/compass-skills: personalized AI task skills system",
                "relevance_reason": "Tool integration and skill routing evidence can improve proposal discovery.",
                "risk_flags": [],
                "confidence": 0.82,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=240)

    assert evidence_package["policy"]["route_hint_validation_lanes"]["skill_route_discovery"] == [
        "documentation",
        "config",
        "test",
        "code_patch",
    ]
    assert [item["route_hints"] for item in evidence_package["items"]] == [
        ["skill_route_discovery"],
        ["skill_route_discovery"],
    ]
    assert [item["route_classification"]["route_class"] for item in evidence_package["items"]] == [
        "skill_workflow",
        "skill_workflow",
    ]
    assert all(
        item["route_classification"]["allowed_lanes"] == ["documentation", "config", "test", "code_patch"]
        for item in evidence_package["items"]
    )


def test_route_classifier_distinguishes_skill_workflow_from_general_agent_project():
    skill_item = {
        "item_id": "threejs-game-skills-domain-director",
        "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
        "event_kind": "RepositoryTrend",
        "summary": "threejs-game-skills: agent skills for Three.js direction, QA, and workflow routing.",
        "relevance_reason": "Domain-director skill bundles should map only into bounded local validation lanes.",
    }
    general_item = {
        "item_id": "omnigent-general-agent-project",
        "source_url": "https://github.com/omnigent-ai/omnigent",
        "event_kind": "RepositoryTrend",
        "summary": "omnigent-ai/omnigent: general AI agent runtime with repository activity and release movement.",
        "relevance_reason": "Useful upstream agent-project movement, but not a reusable route package signal.",
    }

    skill_classification = classify_digest_item_route(skill_item)
    general_classification = classify_digest_item_route(general_item)

    assert skill_classification["route_class"] == "skill_workflow"
    assert skill_classification["route_hints"] == ["skill_route_discovery"]
    assert skill_classification["allowed_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert skill_classification["route_profiles"] == ["game_frontend_workflow"]
    assert skill_classification["runtime_action"] == "none"

    assert general_classification["route_class"] == "general_agent_project"
    assert general_classification["route_hints"] == []
    assert general_classification["allowed_lanes"] == []
    assert general_classification["evaluation_lane"] == "agent_harness_eval_required"
    assert general_classification["runtime_action"] == "none"


def test_general_agent_project_eval_lane_requires_harness_evaluation_without_skill_lanes():
    digest = {
        "digest_id": "github-growth-general-agent-eval-lane",
        "generated_at": "2026-06-20T06:52:07Z",
        "items": [
            {
                "item_id": "omnigent-general-agent-project",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "omnigent-ai/omnigent: general AI agent framework and meta-harness with policy and sandboxing.",
                "relevance_reason": "General agent project movement requires local harness evaluation before behavior changes.",
                "risk_flags": [],
                "confidence": 0.74,
            },
            {
                "item_id": "compass-skills-system",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "dongshuyan/compass-skills: agent skills for task clarification and workflow routing.",
                "relevance_reason": "Skill package evidence maps to bounded skill_route_discovery lanes.",
                "risk_flags": [],
                "confidence": 0.72,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=280)
    lane_map = build_route_hint_lane_map(evidence_package)
    eval_lane = lane_map["general_agent_project_eval"]

    general_row = next(
        row
        for row in lane_map["route_classifier"]
        if row["item_id"] == "omnigent-general-agent-project"
    )
    skill_row = next(
        row
        for row in lane_map["route_classifier"]
        if row["item_id"] == "compass-skills-system"
    )

    assert general_row["route_class"] == "general_agent_project"
    assert "skill_route_discovery" not in general_row["route_hints"]
    assert general_row["allowed_lanes"] == []
    assert general_row["evaluation_lane"] == "agent_harness_eval_required"
    assert skill_row["route_class"] == "skill_workflow"
    assert skill_row["route_hints"] == ["skill_route_discovery"]
    assert eval_lane["candidate_count"] == 1
    assert eval_lane["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert eval_lane["required_local_validation"] == [
        "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
        "pytest tests/test_proposal_eval.py -q -k omnigent",
    ]
    assert eval_lane["skill_route_discovery_inherited"] is False
    assert eval_lane["runtime_action"] == "none"
    assert eval_lane["external_agent_activation_allowed"] is False
    assert eval_lane["raw_source_url_export_allowed"] is False
    assert eval_lane["candidates"] == [
        {
            "item_id": "omnigent-general-agent-project",
            "source_url_hash": stable_hash({"source_url": "https://github.com/omnigent-ai/omnigent"}),
            "route_class": "general_agent_project",
            "evaluation_lane": "agent_harness_eval_required",
            "allowed_local_lanes": ["documentation", "test", "code_patch"],
            "evaluation_priority": 0,
            "upstream_movement_signal": False,
            "upstream_movement_activity_count": 1,
            "upstream_movement_event_kinds": ["RepositoryTrend"],
            "upstream_movement_priority_rule": (
                "repeated_push_or_trend_activity_orders_local_eval_candidates_only"
            ),
            "required_local_validation": [
                "pytest tests/test_harness_eval.py -q -k agent_harness_eval_lane",
                "pytest tests/test_proposal_eval.py -q -k omnigent",
            ],
            "skill_route_discovery_inherited": False,
            "local_validation_required": True,
            "runtime_action": "none",
            "external_agent_activation_allowed": False,
        }
    ]
    assert eval_lane["local_validation_required"] is True


def test_repeated_upstream_push_activity_orders_general_agent_eval_without_activation():
    digest = {
        "digest_id": "github-growth-skill-route-pass2-general-agent-ordering",
        "generated_at": "2026-07-01T09:45:33Z",
        "items": [
            {
                "item_id": "qwen-agentworld-trend",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": "Qwen-AgentWorld: language world models for general agents and benchmark evaluation.",
                "relevance_reason": "General public agent project requires local harness evaluation first.",
                "risk_flags": [],
                "confidence": 0.66,
            },
            {
                "item_id": "looper-trend",
                "source_url": "https://github.com/ksimback/looper",
                "event_kind": "RepositoryTrend",
                "summary": "looper: visual review-gated agent loops for Claude Code before execution.",
                "relevance_reason": "Review-gated agent loop evidence remains a local harness-eval candidate.",
                "risk_flags": [],
                "confidence": 0.70,
            },
            {
                "item_id": "qwen-agentworld-push-validation",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld/commit/abc123",
                "event_kind": "PushEvent",
                "summary": "push to main: update agent benchmark validation harness docs.",
                "relevance_reason": "Repeated PushEvent movement can order local evaluation, not trigger runtime action.",
                "risk_flags": [],
                "confidence": 0.52,
            },
            {
                "item_id": "zhengxi-views-skill",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "event_kind": "RepositoryTrend",
                "summary": "zhengxi-views: SKILL.md source-cited domain research skill with traceable public evidence.",
                "relevance_reason": "Skill evidence maps only to bounded skill_route_discovery lanes.",
                "risk_flags": [],
                "confidence": 0.80,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=360)
    lane_map = build_route_hint_lane_map(evidence_package)
    general_eval = lane_map["general_agent_project_eval"]
    preflight = lane_map["route_activation_preflight"]
    serialized = json.dumps(general_eval, sort_keys=True)

    assert [candidate["item_id"] for candidate in general_eval["candidates"]] == [
        "qwen-agentworld-push-validation",
        "qwen-agentworld-trend",
        "looper-trend",
    ]
    assert general_eval["evaluation_order_policy"] == (
        "repeated_upstream_movement_can_order_local_eval_candidates_only"
    )
    assert general_eval["candidates"][0]["evaluation_priority"] == 1
    assert general_eval["candidates"][0]["upstream_movement_signal"] is True
    assert general_eval["candidates"][0]["upstream_movement_activity_count"] == 2
    assert general_eval["candidates"][0]["upstream_movement_event_kinds"] == [
        "PushEvent",
        "RepositoryTrend",
    ]
    assert all(
        candidate["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
        for candidate in general_eval["candidates"]
    )
    assert all(candidate["local_validation_required"] is True for candidate in general_eval["candidates"])
    assert all(candidate["runtime_action"] == "none" for candidate in general_eval["candidates"])
    assert general_eval["external_agent_activation_allowed"] is False
    assert preflight["general_agent_rows"][0]["item_id"] == "qwen-agentworld-push-validation"
    assert preflight["general_agent_rows"][0]["evaluation_priority"] == 1
    assert preflight["runtime_action"] == "none"
    assert preflight["external_agent_activation_allowed"] is False
    assert "https://github.com/" not in serialized


def test_current_skill_route_window_keeps_skill_and_general_routes_bounded():
    digest = {
        "digest_id": "github-growth-20260621T083208.222111Z",
        "generated_at": "2026-06-21T08:32:08Z",
        "items": [
            {
                "item_id": "p1_skill_route_discovery_catalog",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "FableCodex public Codex skill workflow evidence with plugin routing, "
                    "review gates, tests, evals, and verification habits."
                ),
                "relevance_reason": "Skill and workflow terms should map to bounded local lanes only.",
                "risk_flags": [],
                "confidence": 0.86,
            },
            {
                "item_id": "p2_skill_route_documentation",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "COMPASS Skills public skill ecosystem evidence for task clarification, "
                    "handoff, collaboration profile state, and workflow routing."
                ),
                "relevance_reason": "Skill ecosystem route evidence needs local validation before activation.",
                "risk_flags": [],
                "confidence": 0.82,
            },
            {
                "item_id": "p3_agent_harness_eval_fixture",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "Three.js Game Skills public director skill bundle with specialist skills, "
                    "game workflow, QA validation, and browser checks."
                ),
                "relevance_reason": "Domain skill workflow evidence should stay in local replay lanes.",
                "risk_flags": [],
                "confidence": 0.78,
            },
            {
                "item_id": "p3_general_agent_project_no_route_hints",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "Omnigent public general AI agent framework and meta-harness with agent orchestration.",
                "relevance_reason": "General agent project evidence requires local harness evaluation before behavior changes.",
                "risk_flags": [],
                "confidence": 0.74,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    classifier_rows = {row["item_id"]: row for row in lane_map["route_classifier"]}
    candidate_panel = lane_map["skill_route_local_lane_candidates"]
    general_eval = lane_map["general_agent_project_eval"]
    preflight = lane_map["route_activation_preflight"]
    serialized = json.dumps(lane_map, sort_keys=True)

    assert lane_map["route_class_counts"] == {
        "general_agent_project": 1,
        "skill_workflow": 3,
    }
    assert lane_map["diagnostics"] == []
    assert preflight["status"] == "ready"
    assert preflight["skill_workflow_count"] == 3
    assert preflight["general_agent_project_count"] == 1
    assert preflight["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert preflight["allowed_general_agent_lanes"] == ["documentation", "test", "code_patch"]
    assert preflight["runtime_action"] == "none"
    assert preflight["external_skill_activation_allowed"] is False
    assert preflight["external_agent_activation_allowed"] is False
    assert preflight["external_harness_execution_allowed"] is False
    assert preflight["raw_source_url_export_allowed"] is False

    skill_ids = {
        "p1_skill_route_discovery_catalog",
        "p2_skill_route_documentation",
        "p3_agent_harness_eval_fixture",
    }
    for item_id in skill_ids:
        row = classifier_rows[item_id]
        assert row["route_class"] == "skill_workflow"
        assert "skill_route_discovery" in row["route_hints"]
        assert row["allowed_lanes"] == ["documentation", "config", "test", "code_patch"]
        assert row["unsupported_lanes"] == []

    general_row = classifier_rows["p3_general_agent_project_no_route_hints"]
    assert general_row["route_class"] == "general_agent_project"
    assert general_row["route_hints"] == ["agent_harness_eval"]
    assert "skill_route_discovery" not in general_row["route_hints"]
    assert general_row["allowed_lanes"] == []
    assert general_row["evaluation_lane"] == "agent_harness_eval_required"

    candidate_ids = {row["item_id"] for row in candidate_panel["rows"]}
    assert candidate_ids == skill_ids
    assert "p3_general_agent_project_no_route_hints" not in candidate_ids
    assert candidate_panel["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert candidate_panel["runtime_action"] == "none"
    assert candidate_panel["external_skill_activation_allowed"] is False

    assert general_eval["candidate_count"] == 1
    assert general_eval["skill_route_discovery_inherited"] is False
    assert general_eval["local_validation_required"] is True
    assert general_eval["runtime_action"] == "none"
    assert general_eval["candidates"][0]["item_id"] == "p3_general_agent_project_no_route_hints"
    assert general_eval["candidates"][0]["allowed_local_lanes"] == ["documentation", "test", "code_patch"]
    assert general_eval["candidates"][0]["local_validation_required"] is True
    assert "skill_route_discovery" not in general_eval["candidates"][0]
    assert "https://github.com/" not in serialized


def test_skill_route_boundary_report_splits_skill_repos_from_general_agent_projects():
    digest = {
        "digest_id": "github-growth-20260621T065208-skill-route-boundary",
        "generated_at": "2026-06-21T06:52:08Z",
        "items": [
            {
                "item_id": "fablecodex-workflow-skill-probe",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "FableCodex: Codex plugin with agent skill workflow gates, examples, "
                    "tests, evals, replay, and verification ledgers."
                ),
                "relevance_reason": "Mixed skill and harness signals should enter skill-route discovery first.",
                "risk_flags": [],
                "confidence": 0.86,
            },
            {
                "item_id": "compass-skills-state",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "COMPASS Skills: agent skills for task memory, profiles, and workflow routing.",
                "relevance_reason": "Skill ecosystem state handoff evidence maps to bounded local lanes.",
                "risk_flags": [],
                "confidence": 0.72,
            },
            {
                "item_id": "threejs-game-skills-director",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": "Three.js Game Skills: director skill with specialist skills and QA workflows.",
                "relevance_reason": "Domain-specific skills should stay in skill_route_discovery lanes.",
                "risk_flags": [],
                "confidence": 0.70,
            },
            {
                "item_id": "omnigent-general-agent-project",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "Omnigent: general AI agent runtime and meta-harness.",
                "relevance_reason": "General agent movement requires harness evaluation rather than route-package lanes.",
                "risk_flags": [],
                "confidence": 0.68,
            },
            {
                "item_id": "xuefeng-general-agent-project",
                "source_url": "https://github.com/ziqihe10-droid/xuefeng-agent",
                "event_kind": "RepositoryTrend",
                "summary": "xuefeng-agent: general AI agent project with runtime movement.",
                "relevance_reason": "Agent project without route-package signals remains harness-eval evidence.",
                "risk_flags": [],
                "confidence": 0.64,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=5, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    boundary = lane_map["skill_route_boundary_report"]
    serialized = json.dumps(boundary, sort_keys=True)

    assert boundary["controller_surface"] == "skill_route_boundary_report"
    assert boundary["status"] == "ready"
    assert boundary["decision"] == "skill_and_general_agent_routes_split_before_activation"
    assert boundary["skill_workflow_count"] == 3
    assert boundary["general_agent_project_count"] == 2
    assert boundary["mixed_skill_workflow_count"] == 1
    assert boundary["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert boundary["allowed_general_agent_lanes"] == ["documentation", "test", "code_patch"]
    assert boundary["mixed_secondary_lane"] == "agent_harness_eval_after_local_corroboration"
    assert boundary["mixed_secondary_lane_status"] == "blocked_until_local_corroboration"
    assert boundary["diagnostics"] == []
    assert boundary["runtime_action"] == "none"
    assert boundary["external_skill_activation_allowed"] is False
    assert boundary["external_agent_activation_allowed"] is False
    assert boundary["external_harness_execution_allowed"] is False
    assert boundary["provider_runtime_launch_allowed"] is False
    assert boundary["remote_execution_allowed"] is False
    assert boundary["raw_source_url_export_allowed"] is False
    assert boundary["upstream_body_export_allowed"] is False

    skill_rows = {row["item_id"]: row for row in boundary["skill_workflow_rows"]}
    general_rows = {row["item_id"]: row for row in boundary["general_agent_project_rows"]}
    assert sorted(skill_rows) == [
        "compass-skills-state",
        "fablecodex-workflow-skill-probe",
        "threejs-game-skills-director",
    ]
    assert sorted(general_rows) == [
        "omnigent-general-agent-project",
        "xuefeng-general-agent-project",
    ]
    assert all(row["primary_route"] == "skill_route_discovery" for row in skill_rows.values())
    assert all(row["local_lanes"] == ["documentation", "config", "test", "code_patch"] for row in skill_rows.values())
    assert all(row["agent_harness_eval_required"] is False for row in skill_rows.values())
    assert all(row["skill_route_discovery_inherited"] is True for row in skill_rows.values())
    assert skill_rows["fablecodex-workflow-skill-probe"]["secondary_lane"] == (
        "agent_harness_eval_after_local_corroboration"
    )
    assert skill_rows["fablecodex-workflow-skill-probe"]["secondary_lane_status"] == (
        "blocked_until_local_corroboration"
    )

    assert all(row["primary_route"] == "agent_harness_eval_required" for row in general_rows.values())
    assert all(row["allowed_local_lanes"] == ["documentation", "test", "code_patch"] for row in general_rows.values())
    assert all(row["skill_route_discovery_inherited"] is False for row in general_rows.values())
    assert all(row["agent_harness_eval_required"] is True for row in general_rows.values())
    assert "https://github.com" not in serialized
    assert "FableCodex" not in serialized
    assert "omnigent-ai" not in serialized


def test_route_activation_preflight_keeps_current_skill_window_bounded_before_activation():
    digest = {
        "digest_id": "github-growth-20260621T071207.939436Z",
        "generated_at": "2026-06-21T07:12:07Z",
        "items": [
            {
                "item_id": "p1-skill-route-discovery-registry",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "FableCodex is a Codex plugin and agent skill workflow with evidence gates, "
                    "tests, evals, examples, and verification habits."
                ),
                "relevance_reason": "Skill/workflow trend evidence should enter bounded local lanes first.",
                "risk_flags": [],
                "confidence": 0.88,
            },
            {
                "item_id": "p2-skill-workflow-docs",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "COMPASS Skills is an agent skills system for task routing, profile state, and workflow handoff.",
                "relevance_reason": "State handoff evidence needs local documentation or config validation before activation.",
                "risk_flags": [],
                "confidence": 0.84,
            },
            {
                "item_id": "threejs-game-skills-director",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": "Three.js Game Skills is a director skill bundle with specialist game workflow and QA validation.",
                "relevance_reason": "Domain skill bundles should become local validation lanes only.",
                "risk_flags": [],
                "confidence": 0.78,
            },
            {
                "item_id": "p3-agent-harness-eval-preflight",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "Omnigent is a general AI agent framework and meta-harness for orchestrating coding agents.",
                "relevance_reason": "General agent-project evidence requires harness evaluation before behavior changes.",
                "risk_flags": [],
                "confidence": 0.76,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    preflight = lane_map["route_activation_preflight"]
    serialized = json.dumps(preflight, sort_keys=True)

    assert preflight["controller_surface"] == "route_activation_preflight"
    assert preflight["status"] == "ready"
    assert preflight["decision"] == "bounded_routes_ready_for_local_validation_selection"
    assert preflight["skill_workflow_count"] == 3
    assert preflight["general_agent_project_count"] == 1
    assert preflight["mixed_skill_workflow_count"] == 1
    assert preflight["activation_blockers"] == []
    assert preflight["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert preflight["allowed_general_agent_lanes"] == ["documentation", "test", "code_patch"]
    assert preflight["runtime_action"] == "none"
    assert preflight["external_skill_activation_allowed"] is False
    assert preflight["external_agent_activation_allowed"] is False
    assert preflight["external_harness_execution_allowed"] is False
    assert preflight["provider_runtime_launch_allowed"] is False
    assert preflight["remote_execution_allowed"] is False
    assert preflight["raw_source_url_export_allowed"] is False
    assert preflight["upstream_body_export_allowed"] is False
    assert "https://github.com" not in serialized
    assert "FableCodex" not in serialized
    assert "omnigent-ai" not in serialized

    skill_rows = {row["item_id"]: row for row in preflight["skill_route_rows"]}
    general_rows = {row["item_id"]: row for row in preflight["general_agent_rows"]}
    assert sorted(skill_rows) == [
        "p1-skill-route-discovery-registry",
        "p2-skill-workflow-docs",
        "threejs-game-skills-director",
    ]
    assert sorted(general_rows) == ["p3-agent-harness-eval-preflight"]
    assert all(row["primary_route"] == "skill_route_discovery" for row in skill_rows.values())
    assert all(row["local_lanes"] == ["documentation", "config", "test", "code_patch"] for row in skill_rows.values())
    assert all(row["lane_status"] == "bounded" for row in skill_rows.values())
    assert skill_rows["p1-skill-route-discovery-registry"]["activation_gate"] == (
        "local_skill_route_validation_before_secondary_harness_eval"
    )
    assert skill_rows["p1-skill-route-discovery-registry"]["secondary_lane_status"] == (
        "blocked_until_local_corroboration"
    )
    assert general_rows["p3-agent-harness-eval-preflight"]["primary_route"] == "agent_harness_eval_required"
    assert general_rows["p3-agent-harness-eval-preflight"]["skill_route_discovery_inherited"] is False


def test_skill_route_local_lane_candidates_bound_current_skill_evidence_before_activation():
    digest = {
        "digest_id": "github-growth-20260620T191207.732215Z",
        "generated_at": "2026-06-20T19:12:07Z",
        "items": [
            {
                "item_id": "fablecodex-workflow-skill",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "FableCodex: Codex plugin with skill workflow gates, examples, tests, "
                    "evals, and verification ledgers."
                ),
                "relevance_reason": "Mixed skill and harness signals should enter skill-route discovery first.",
                "risk_flags": [],
                "confidence": 0.86,
            },
            {
                "item_id": "compass-skills-state",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "COMPASS Skills: agent skills for clarification, task memory, and workflow routing.",
                "relevance_reason": "Skill ecosystem state handoff evidence maps to bounded local lanes.",
                "risk_flags": [],
                "confidence": 0.72,
            },
            {
                "item_id": "threejs-game-skills-director",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": "Three.js Game Skills: director skill with specialist skills, QA, and workflow checks.",
                "relevance_reason": "Domain director skills should become local validation lanes only.",
                "risk_flags": [],
                "confidence": 0.70,
            },
            {
                "item_id": "omnigent-general-agent-project",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "Omnigent: general AI agent runtime and meta-harness.",
                "relevance_reason": "General agent movement requires harness evaluation rather than route-package lanes.",
                "risk_flags": [],
                "confidence": 0.68,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    candidate_panel = lane_map["skill_route_local_lane_candidates"]

    assert candidate_panel["controller_surface"] == "skill_route_local_lane_candidates"
    assert candidate_panel["candidate_count"] == 3
    assert candidate_panel["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert candidate_panel["rows_bounded"] is True
    assert candidate_panel["local_validation_required"] is True
    assert candidate_panel["runtime_action"] == "none"
    assert candidate_panel["external_skill_activation_allowed"] is False
    assert candidate_panel["external_agent_activation_allowed"] is False
    assert candidate_panel["raw_source_url_export_allowed"] is False
    assert candidate_panel["upstream_body_export_allowed"] is False

    rows_by_id = {row["item_id"]: row for row in candidate_panel["rows"]}
    assert sorted(rows_by_id) == [
        "compass-skills-state",
        "fablecodex-workflow-skill",
        "threejs-game-skills-director",
    ]
    assert "omnigent-general-agent-project" not in rows_by_id

    for item_id, row in rows_by_id.items():
        assert row["route_class"] == "skill_workflow"
        assert "skill_route_discovery" in row["route_hints"]
        assert row["local_lanes"] == ["documentation", "config", "test", "code_patch"]
        assert row["lanes_bounded"] is True
        assert row["route_profiles"]
        assert row["local_validation_required"] is True
        assert row["runtime_action"] == "none"
        assert row["external_skill_activation_allowed"] is False
        assert row["external_agent_activation_allowed"] is False
        assert row["raw_source_url_export_allowed"] is False
        assert row["upstream_body_export_allowed"] is False
        assert row["source_url_hash"]
        assert "https://github.com" not in json.dumps(row, sort_keys=True)

    assert rows_by_id["fablecodex-workflow-skill"]["route_probe_decision"] == "skill_route_discovery_first"
    assert rows_by_id["fablecodex-workflow-skill"]["route_profiles"] == ["codex_workflow_gate"]
    assert rows_by_id["fablecodex-workflow-skill"]["activation_gate"] == (
        "local_skill_route_validation_before_secondary_harness_eval"
    )
    assert rows_by_id["fablecodex-workflow-skill"]["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert rows_by_id["fablecodex-workflow-skill"]["required_local_validation"] == [
        "pytest tests/test_github_growth.py -q -k mixed_skill_workflow",
        "pytest tests/test_proposal_eval.py -q -k route_hint_lane_map",
    ]

    assert rows_by_id["compass-skills-state"]["activation_gate"] == "local_validation_before_activation"
    assert rows_by_id["compass-skills-state"]["route_profiles"] == ["skill_ecosystem_state_handoff"]
    assert rows_by_id["threejs-game-skills-director"]["activation_gate"] == "local_validation_before_activation"
    assert rows_by_id["threejs-game-skills-director"]["route_profiles"] == ["game_frontend_workflow"]
    assert rows_by_id["compass-skills-state"]["required_local_validation"] == [
        "pytest tests/test_harness_eval.py -q -k skill_route_discovery_lane",
        "pytest tests/test_proposal_eval.py -q -k skill_route_discovery",
    ]
    assert rows_by_id["threejs-game-skills-director"]["source_url_hash"] == stable_hash(
        {"source_url": "https://github.com/majidmanzarpour/threejs-game-skills"}
    )


def test_current_pass3_route_readiness_index_splits_skill_routes_from_qwen_agentworld():
    digest = {
        "digest_id": "github-growth-20260628T194729.590017Z",
        "generated_at": "2026-06-28T19:47:29Z",
        "items": [
            {
                "item_id": "p1-skill-route-discovery-index",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "COMPASS Skills: skill ecosystem with multiple skills, collaboration profiles, "
                    "clarification workflow, task memory, and handoff routing."
                ),
                "relevance_reason": "Skill ecosystem evidence maps to bounded local config or test lanes.",
                "risk_flags": [],
                "confidence": 0.78,
            },
            {
                "item_id": "p2-skill-route-fixture-tests",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "event_kind": "RepositoryTrend",
                "summary": "zhengxi-views: public SKILL.md workflow with source citations and domain research views.",
                "relevance_reason": "Source-cited skill workflow evidence needs local citation-boundary validation.",
                "risk_flags": [],
                "confidence": 0.74,
            },
            {
                "item_id": "p3-game-frontend-skill-profile",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": "Three.js Game Skills: browser game director skill, specialist skills, QA, and workflow checks.",
                "relevance_reason": "Game frontend skill profile can select only bounded local validation lanes.",
                "risk_flags": [],
                "confidence": 0.72,
            },
            {
                "item_id": "p4-agent-harness-eval-fixtures",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": "Qwen-AgentWorld: general agent benchmark and project for agent training and evaluation.",
                "relevance_reason": "General agent project evidence requires agent_harness_eval_required before implementation.",
                "risk_flags": [],
                "confidence": 0.67,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    readiness = lane_map["current_pass3_route_readiness_index"]
    serialized = json.dumps(readiness, sort_keys=True)

    assert readiness["controller_surface"] == "current_pass3_route_readiness_index"
    assert readiness["status"] == "ready_with_adjacent_agent_eval_blocked"
    assert readiness["capability_pass"] == "3_of_4"
    assert readiness["skill_route_ready"] is True
    assert readiness["skill_workflow_count"] == 3
    assert readiness["skill_workflow_item_ids"] == [
        "p1-skill-route-discovery-index",
        "p2-skill-route-fixture-tests",
        "p3-game-frontend-skill-profile",
    ]
    assert readiness["route_profiles"] == [
        "game_frontend_workflow",
        "generic_skill_workflow",
        "skill_ecosystem_state_handoff",
    ]
    assert set(readiness["selected_local_lanes"]) <= {"documentation", "config", "test", "code_patch"}
    assert readiness["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert readiness["adjacent_general_agent_count"] == 1
    assert readiness["adjacent_agent_harness_eval_required"] is True
    assert readiness["adjacent_agent_harness_eval_blocked"] is True
    assert readiness["adjacent_general_agent_item_ids"] == ["p4-agent-harness-eval-fixtures"]
    assert readiness["adjacent_general_agent_allowed_lanes"] == ["documentation", "test", "code_patch"]
    assert readiness["adjacent_general_agent_skill_route_inherited"] is False
    assert readiness["controller_recomputed_status"] == "blocked"
    assert readiness["local_validation_required"] is True
    assert readiness["runtime_action"] == "none"
    assert readiness["external_skill_activation_allowed"] is False
    assert readiness["external_agent_activation_allowed"] is False
    assert readiness["external_harness_execution_allowed"] is False
    assert readiness["provider_runtime_launch_allowed"] is False
    assert readiness["remote_execution_allowed"] is False
    assert readiness["profile_write_allowed"] is False
    assert readiness["memory_write_allowed"] is False
    assert readiness["raw_source_url_export_allowed"] is False
    assert readiness["raw_evidence_url_export_allowed"] is False
    assert readiness["upstream_body_export_allowed"] is False
    assert "https://github.com/" not in serialized


def test_current_pass2_lane_handoff_bounds_zhengxi_and_gates_general_agents():
    digest = {
        "digest_id": "github-growth-20260630T102715.054031Z",
        "generated_at": "2026-06-30T10:27:15Z",
        "items": [
            {
                "item_id": "trend:lyra81604/zhengxi-views-1",
                "source_url": "https://github.com/lyra81604/zhengxi-views",
                "event_kind": "RepositoryTrend",
                "summary": "zhengxi-views: public SKILL.md workflow with source citations and domain research views.",
                "relevance_reason": "Skill and workflow evidence maps only to bounded local validation lanes.",
                "risk_flags": [],
                "confidence": 0.76,
            },
            {
                "item_id": "trend:QwenLM/Qwen-AgentWorld",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": "Qwen-AgentWorld: general agent benchmark and project for agent training and evaluation.",
                "relevance_reason": "General public agent projects require agent_harness_eval before implementation.",
                "risk_flags": [],
                "confidence": 0.70,
            },
            {
                "item_id": "trend:ksimback/looper",
                "source_url": "https://github.com/ksimback/looper",
                "event_kind": "RepositoryTrend",
                "summary": "looper: general agent loop runtime project with scheduled autonomous work.",
                "relevance_reason": "Agent loop evidence remains adjacent harness-eval evidence, not a skill route.",
                "risk_flags": [],
                "confidence": 0.68,
            },
            {
                "item_id": "trend:fork-low-detail",
                "source_url": "https://github.com/example/fork-low-detail",
                "event_kind": "ForkEvent",
                "summary": "low-detail fork mirror of a public reverse-engineering repository.",
                "relevance_reason": "Fork lineage alone has no local validation target.",
                "risk_flags": [],
                "confidence": 0.42,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    handoff = lane_map["current_pass2_lane_handoff"]
    serialized = json.dumps(handoff, sort_keys=True)

    assert handoff["controller_surface"] == "current_pass2_lane_handoff"
    assert handoff["source_digest"] == "github-growth-20260630T102715.054031Z"
    assert handoff["status"] == "ready_with_adjacent_agent_eval_gated"
    assert handoff["decision"] == "replay_bounded_skill_route_lane_keep_general_agents_in_eval_gate"
    assert handoff["capability_pass"] == "2_of_4"
    assert handoff["active_proposal_ids"] == [
        "p1-skill-route-discovery-codex-workflow",
        "p2-generic-skill-workflow-route-coverage",
        "p3-agent-harness-eval-gate",
    ]
    assert handoff["skill_workflow_count"] == 1
    assert handoff["general_agent_project_count"] == 2
    assert handoff["blocked_general_agent_item_ids"] == [
        "trend:QwenLM/Qwen-AgentWorld",
        "trend:ksimback/looper",
    ]
    assert handoff["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert handoff["allowed_general_agent_lanes"] == ["documentation", "test", "code_patch"]
    assert handoff["operator_replay_surface"] is True
    assert handoff["local_validation_required"] is True
    assert handoff["runtime_action"] == "none"
    assert handoff["external_skill_activation_allowed"] is False
    assert handoff["external_agent_activation_allowed"] is False
    assert handoff["external_harness_execution_allowed"] is False
    assert handoff["provider_runtime_launch_allowed"] is False
    assert handoff["remote_execution_allowed"] is False
    assert handoff["profile_write_allowed"] is False
    assert handoff["memory_write_allowed"] is False
    assert handoff["raw_source_url_export_allowed"] is False
    assert handoff["raw_evidence_url_export_allowed"] is False
    assert handoff["raw_replay_command_export_allowed"] is False
    assert handoff["raw_target_path_export_allowed"] is False
    assert handoff["upstream_body_export_allowed"] is False

    skill_rows = {row["item_id"]: row for row in handoff["skill_route_rows"]}
    general_rows = {row["item_id"]: row for row in handoff["general_agent_rows"]}
    assert sorted(skill_rows) == ["trend:lyra81604/zhengxi-views-1"]
    assert sorted(general_rows) == ["trend:QwenLM/Qwen-AgentWorld", "trend:ksimback/looper"]
    assert "trend:fork-low-detail" not in skill_rows
    assert "trend:fork-low-detail" not in general_rows

    zhengxi_row = skill_rows["trend:lyra81604/zhengxi-views-1"]
    assert zhengxi_row["primary_route"] == "skill_route_discovery"
    assert zhengxi_row["route_class"] == "skill_workflow"
    assert zhengxi_row["selected_local_lane"] in {"documentation", "config", "test", "code_patch"}
    assert zhengxi_row["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert zhengxi_row["lane_bounded"] is True
    assert zhengxi_row["validation_gate"] == ["focused-evidence-review"]
    assert zhengxi_row["implementation_route_allowed"] is True
    assert zhengxi_row["source_url_hash"] == stable_hash(
        {"source_url": "https://github.com/lyra81604/zhengxi-views"}
    )

    assert all(row["primary_route"] == "agent_harness_eval_required" for row in general_rows.values())
    assert all(row["implementation_lanes_enabled"] is False for row in general_rows.values())
    assert all(row["blocked_until"] == "local_agent_harness_evaluation_result" for row in general_rows.values())
    assert all(
        row["fixture_gate_status"] == "blocked_until_local_agent_harness_fixture"
        for row in general_rows.values()
    )
    assert all(
        row["missing_fixture_fields"]
        == [
            "fixture_path",
            "expected_behavior",
            "expected_output",
            "pass_fail_signal",
            "rollback_artifact",
            "non_secret_config",
        ]
        for row in general_rows.values()
    )
    assert all(row["skill_route_discovery_inherited"] is False for row in general_rows.values())
    checklist = handoff["secondary_harness_checklist"]
    assert checklist["controller_surface"] == "current_pass2_secondary_harness_checklist"
    assert checklist["status"] == "ready"
    assert checklist["record_count"] == 2
    assert checklist["blocked_fixture_count"] == 2
    assert checklist["ready_fixture_count"] == 0
    assert checklist["agent_harness_eval_required"] is True
    assert checklist["fixture_requirements"] == [
        "runnable_scenario",
        "expected_output",
        "pass_fail_signal",
        "rollback_path",
        "non_secret_config",
    ]
    assert all(
        row["activation_status"] == "blocked_until_local_agent_harness_fixture"
        for row in checklist["rows"]
    )
    assert all(row["implementation_patch_allowed"] is False for row in checklist["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in checklist["rows"])
    assert checklist["runtime_action"] == "none"
    assert checklist["raw_source_url_export_allowed"] is False
    assert "https://github.com/" not in serialized
    assert "github.com/lyra81604" not in serialized
    assert "github.com/QwenLM" not in serialized
    assert "github.com/ksimback" not in serialized


def test_current_pass2_skill_route_window_gates_codex_generic_and_general_agent_routes():
    digest = {
        "digest_id": "github-growth-20260705T044818.919983Z",
        "generated_at": "2026-07-05T04:48:18.919983Z",
        "items": [
            {
                "item_id": "p1-skill-route-discovery-codex-workflow-gate",
                "source_url": "https://github.com/lingbol088-spec/reverse-flow-skill",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "reverse-flow-skill Codex and AI Agent skill workflow with SKILL.md, "
                    "references, scripts, local sandbox framing, workflow gate language, "
                    "and install/run wording that must not become runtime activation."
                ),
                "relevance_reason": (
                    "Codex-oriented skill terminology should map only to bounded local "
                    "documentation, config, test, or code_patch lanes."
                ),
                "risk_flags": [],
                "confidence": 0.78,
            },
            {
                "item_id": "p2-generic-skill-workflow-discovery",
                "source_url": "https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "BioNeMo Agent Toolkit exposes agent skills, workflow directories, "
                    "library skills, plugin metadata, and generic skill workflow routing."
                ),
                "relevance_reason": "Generic skill and skills topic signals enter skill_route_discovery lanes.",
                "risk_flags": [],
                "confidence": 0.72,
            },
            {
                "item_id": "p3-agent-harness-eval-for-agentworld",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": "Qwen-AgentWorld is a general agent world-model and benchmark project.",
                "relevance_reason": "General agent project evidence requires local harness evaluation first.",
                "risk_flags": [],
                "confidence": 0.66,
            },
            {
                "item_id": "p3-agent-harness-eval-simulation",
                "source_url": "https://github.com/TianhangZhuzth/Fundamental-Ava",
                "event_kind": "RepositoryTrend",
                "summary": "Fundamental-Ava is a general autonomous collaborative agent simulation project.",
                "relevance_reason": "General agent simulation evidence stays in agent_harness_eval_required.",
                "risk_flags": [],
                "confidence": 0.64,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=480)
    lane_map = build_route_hint_lane_map(evidence_package)
    handoff = lane_map["current_pass2_lane_handoff"]
    checklist = lane_map["current_pass2_secondary_harness_checklist"]
    readiness = lane_map["current_pass2_activation_readiness"]
    serialized = json.dumps(handoff, sort_keys=True)

    assert handoff["source_digest"] == "github-growth-20260705T044818.919983Z"
    assert handoff["active_proposal_ids"] == [
        "p1-skill-route-discovery-codex-workflow",
        "p2-generic-skill-workflow-route-coverage",
        "p3-agent-harness-eval-gate",
    ]
    assert handoff["status"] == "ready_with_adjacent_agent_eval_gated"
    assert handoff["skill_workflow_count"] == 2
    assert handoff["general_agent_project_count"] == 2
    assert handoff["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert handoff["allowed_general_agent_lanes"] == ["documentation", "test", "code_patch"]
    assert handoff["runtime_action"] == "none"
    assert handoff["external_skill_activation_allowed"] is False
    assert handoff["external_agent_activation_allowed"] is False
    assert handoff["external_harness_execution_allowed"] is False
    assert handoff["provider_runtime_launch_allowed"] is False
    assert handoff["remote_execution_allowed"] is False
    assert handoff["raw_source_url_export_allowed"] is False
    assert handoff["upstream_body_export_allowed"] is False

    skill_rows = {row["item_id"]: row for row in handoff["skill_route_rows"]}
    general_rows = {row["item_id"]: row for row in handoff["general_agent_rows"]}
    assert sorted(skill_rows) == [
        "p1-skill-route-discovery-codex-workflow-gate",
        "p2-generic-skill-workflow-discovery",
    ]
    assert sorted(general_rows) == [
        "p3-agent-harness-eval-for-agentworld",
        "p3-agent-harness-eval-simulation",
    ]
    assert skill_rows["p1-skill-route-discovery-codex-workflow-gate"]["selected_local_lane"] == "test"
    assert skill_rows["p2-generic-skill-workflow-discovery"]["selected_local_lane"] in {
        "documentation",
        "config",
        "test",
        "code_patch",
    }
    assert all(row["lane_bounded"] is True for row in skill_rows.values())
    assert all(
        row["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"]
        for row in skill_rows.values()
    )
    assert all(row["primary_route"] == "agent_harness_eval_required" for row in general_rows.values())
    assert all(row["skill_route_discovery_inherited"] is False for row in general_rows.values())
    assert all(row["implementation_lanes_enabled"] is False for row in general_rows.values())
    assert all(
        row["fixture_gate_status"] == "blocked_until_local_agent_harness_fixture"
        for row in general_rows.values()
    )

    assert checklist["controller_surface"] == "current_pass2_secondary_harness_checklist"
    assert checklist["status"] == "ready"
    assert checklist["record_count"] == 2
    assert checklist["blocked_fixture_count"] == 2
    assert checklist["required_fixture_fields"] == [
        "fixture_path",
        "expected_behavior",
        "expected_output",
        "pass_fail_signal",
        "rollback_artifact",
        "non_secret_config",
    ]
    assert handoff["secondary_harness_checklist"] == checklist
    assert readiness["secondary_harness_checklist"] == checklist
    assert readiness["blocked_general_agent_item_ids"] == [
        "p3-agent-harness-eval-for-agentworld",
        "p3-agent-harness-eval-simulation",
    ]
    assert all(row["implementation_patch_allowed"] is False for row in checklist["rows"])
    assert all(row["external_harness_execution_allowed"] is False for row in checklist["rows"])
    assert "https://github.com/" not in serialized
    assert "QwenLM" not in serialized
    assert "Fundamental-Ava" not in serialized


def test_current_pass1_skill_route_validation_matrix_pairs_codex_and_generic_skill_profiles():
    digest = {
        "digest_id": "github-growth-20260705T054818.762095Z",
        "generated_at": "2026-07-05T05:48:18.762095Z",
        "items": [
            {
                "item_id": "p1_reverse_flow_skill_route_discovery",
                "source_url": "https://github.com/lingbol088-spec/reverse-flow-skill",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "reverse-flow-skill is an AI Agent / Codex local skill workflow with "
                    "SKILL.md, local sandbox defaults, workflow gate language, scripts, "
                    "tests, and install/run wording that must stay non-actionful."
                ),
                "relevance_reason": (
                    "Codex-oriented skill workflow candidates should be classified through "
                    "skill_route_discovery before any implementation route is considered."
                ),
                "risk_flags": [],
                "confidence": 0.78,
            },
            {
                "item_id": "p2_bionemo_skill_workflow_discovery",
                "source_url": "https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "BioNeMo Agent Toolkit presents generic agent skills and skill workflow "
                    "routing for life-science agents without Codex-specific workflow gates."
                ),
                "relevance_reason": (
                    "Generic skill or skills signals should enter skill_route_discovery before "
                    "local documentation, config, test, or code_patch lanes are selected."
                ),
                "risk_flags": [],
                "confidence": 0.72,
            },
            {
                "item_id": "trend:QwenLM/Qwen-AgentWorld-1",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": "Qwen-AgentWorld is a general agent benchmark and world-model project.",
                "relevance_reason": "General agent project evidence requires local harness evaluation first.",
                "risk_flags": [],
                "confidence": 0.66,
            },
            {
                "item_id": "trend:TianhangZhuzth/Fundamental-Ava-2",
                "source_url": "https://github.com/TianhangZhuzth/Fundamental-Ava",
                "event_kind": "RepositoryTrend",
                "summary": "Fundamental-Ava is an autonomous collaborative agent simulation project.",
                "relevance_reason": "General autonomous agent claims stay in agent_harness_eval_required.",
                "risk_flags": [],
                "confidence": 0.64,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=520)
    lane_map = build_route_hint_lane_map(evidence_package)
    matrix = lane_map["current_pass1_skill_route_validation_matrix"]
    rows = {row["item_id"]: row for row in matrix["skill_route_rows"]}
    adjacent_rows = {row["item_id"]: row for row in matrix["adjacent_general_agent_rows"]}
    serialized = json.dumps(matrix, sort_keys=True)

    assert matrix["controller_surface"] == "current_pass1_skill_route_validation_matrix"
    assert matrix["status"] == "ready_with_adjacent_agent_eval_gated"
    assert matrix["capability_pass"] == "1_of_4"
    assert matrix["source_digest"] == "github-growth-20260705T054818.762095Z"
    assert matrix["active_proposal_ids"] == [
        "p1_reverse_flow_skill_route_discovery",
        "p2_bionemo_skill_workflow_discovery",
        "p3_skill_route_discovery_regression_pair",
    ]
    assert matrix["codex_skill_workflow_count"] == 1
    assert matrix["generic_skill_workflow_count"] == 1
    assert matrix["adjacent_general_agent_count"] == 2
    assert matrix["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]

    reverse_flow = rows["p1_reverse_flow_skill_route_discovery"]
    assert reverse_flow["primary_route"] == "skill_route_discovery"
    assert reverse_flow["route_profile_kind"] == "codex_specific"
    assert reverse_flow["route_profiles"] == ["codex_workflow_gate"]
    assert reverse_flow["requires_skill_route_discovery_first"] is True
    assert reverse_flow["skill_route_discovery_first_confirmed"] is True
    assert reverse_flow["route_probe_decision"] == "skill_route_discovery_first"
    assert reverse_flow["selected_local_lane"] == "test"

    bionemo = rows["p2_bionemo_skill_workflow_discovery"]
    assert bionemo["primary_route"] == "skill_route_discovery"
    assert bionemo["route_profile_kind"] == "generic_skill_workflow"
    assert bionemo["route_profiles"] == ["generic_skill_workflow"]
    assert bionemo["requires_skill_route_discovery_first"] is False
    assert bionemo["selected_local_lane"] == "documentation"

    assert all(row["bounded_local_lanes_only"] is True for row in rows.values())
    assert all(row["allowed_local_lanes"] == ["documentation", "config", "test", "code_patch"] for row in rows.values())
    assert all(row["runtime_action"] == "none" for row in rows.values())
    assert all(row["external_skill_activation_allowed"] is False for row in rows.values())

    assert sorted(adjacent_rows) == [
        "trend:QwenLM/Qwen-AgentWorld-1",
        "trend:TianhangZhuzth/Fundamental-Ava-2",
    ]
    assert all(row["primary_route"] == "agent_harness_eval_required" for row in adjacent_rows.values())
    assert all(row["direct_allowed_lanes_before_eval"] == [] for row in adjacent_rows.values())
    assert all(row["skill_route_discovery_inherited"] is False for row in adjacent_rows.values())
    assert matrix["regression_pair"]["status"] == "ready"
    assert matrix["regression_pair"]["codex_validation_gate"] == (
        "codex_workflow_gate_plus_mixed_skill_workflow_probe"
    )
    assert matrix["regression_pair"]["generic_validation_gate"] == "generic_skill_workflow"
    assert "https://github.com/" not in serialized
    assert "runtime_execution" not in serialized
    assert matrix["runtime_action"] == "none"
    assert matrix["external_skill_activation_allowed"] is False
    assert matrix["external_agent_activation_allowed"] is False


def test_current_pass2_skill_route_operator_lane_replays_active_skill_window():
    digest = {
        "digest_id": "github-growth-20260705T060819.666814Z",
        "generated_at": "2026-07-05T06:08:19.666814Z",
        "items": [
            {
                "item_id": "p1_reverse_flow_skill_route_discovery",
                "source_url": "https://github.com/lingbol088-spec/reverse-flow-skill",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "reverse-flow-skill is a Codex and AI Agent skill workflow with "
                    "skills/reverse-flow/SKILL.md, local sandbox defaults, scripts, "
                    "install examples, and workflow-gate pressure."
                ),
                "relevance_reason": (
                    "The local controller must route this as skill_route_discovery first "
                    "and validate only bounded local lanes."
                ),
                "risk_flags": [],
                "confidence": 0.79,
            },
            {
                "item_id": "p2_bionemo_skill_workflow_discovery",
                "source_url": "https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "BioNeMo Agent Toolkit describes generic agent skills, plugins, "
                    "catalogs, and skill workflow routing for life science agents."
                ),
                "relevance_reason": (
                    "Generic skill workflow evidence may propose documentation, config, "
                    "test, or code_patch only after local validation gates are recomputed."
                ),
                "risk_flags": [],
                "confidence": 0.73,
            },
            {
                "item_id": "trend:QwenLM/Qwen-AgentWorld-1",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": "Qwen-AgentWorld is a general agent project and benchmark environment.",
                "relevance_reason": "General agent projects require local harness evaluation first.",
                "risk_flags": [],
                "confidence": 0.67,
            },
            {
                "item_id": "trend:TianhangZhuzth/Fundamental-Ava-2",
                "source_url": "https://github.com/TianhangZhuzth/Fundamental-Ava",
                "event_kind": "RepositoryTrend",
                "summary": "Fundamental-Ava is an autonomous collaborative agent simulation project.",
                "relevance_reason": "General autonomous-agent claims stay in agent_harness_eval_required.",
                "risk_flags": [],
                "confidence": 0.65,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=560)
    lane_map = build_route_hint_lane_map(evidence_package)
    operator_lane = lane_map["current_pass2_skill_route_operator_lane"]
    skill_rows = {row["item_id"]: row for row in operator_lane["skill_route_rows"]}
    adjacent_rows = {row["item_id"]: row for row in operator_lane["adjacent_general_agent_rows"]}
    serialized = json.dumps(operator_lane, sort_keys=True)

    assert operator_lane["controller_surface"] == "current_pass2_skill_route_operator_lane"
    assert operator_lane["status"] == "ready_with_adjacent_agent_eval_gated"
    assert operator_lane["capability_pass"] == "2_of_4"
    assert operator_lane["source_digest"] == "github-growth-20260705T060819.666814Z"
    assert operator_lane["active_proposal_ids"] == [
        "p1_reverse_flow_skill_route_discovery",
        "p2_bionemo_skill_workflow_discovery",
        "p3_skill_route_discovery_regression_pair",
        "p1-skill-route-discovery-reverse-flow",
        "p2-generic-skill-workflow-routing-bionemo",
        "p3-agent-harness-eval-for-general-agent-trends",
        "p4-workflow-usecase-intake-gating",
        "p5-route-classification-regression-bundle",
        "trend:QwenLM/Qwen-AgentWorld-1",
        "trend:TianhangZhuzth/Fundamental-Ava-2",
    ]
    assert operator_lane["skill_workflow_count"] == 2
    assert operator_lane["adjacent_general_agent_count"] == 2
    assert operator_lane["allowed_skill_route_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert operator_lane["activation_blockers"] == []

    reverse_flow = skill_rows["p1_reverse_flow_skill_route_discovery"]
    assert reverse_flow["route_profile_kind"] == "codex_specific"
    assert reverse_flow["selected_local_lane"] == "test"
    assert reverse_flow["skill_route_discovery_first_confirmed"] is True
    assert reverse_flow["accepted_outputs_before_validation"] == []
    assert reverse_flow["accepted_outputs_after_validation"] == ["documentation", "config", "test", "code_patch"]

    bionemo = skill_rows["p2_bionemo_skill_workflow_discovery"]
    assert bionemo["route_profile_kind"] == "generic_skill_workflow"
    assert bionemo["selected_local_lane"] == "documentation"
    assert bionemo["accepted_outputs_before_validation"] == []
    assert bionemo["accepted_outputs_after_validation"] == ["documentation", "config", "test", "code_patch"]

    assert all(row["local_lane_ready"] is True for row in skill_rows.values())
    assert all(row["runtime_action"] == "none" for row in skill_rows.values())
    assert all(row["external_skill_activation_allowed"] is False for row in skill_rows.values())

    assert sorted(adjacent_rows) == [
        "trend:QwenLM/Qwen-AgentWorld-1",
        "trend:TianhangZhuzth/Fundamental-Ava-2",
    ]
    assert all(row["primary_route"] == "agent_harness_eval_required" for row in adjacent_rows.values())
    assert all(row["direct_allowed_lanes_before_eval"] == [] for row in adjacent_rows.values())
    assert all(row["skill_route_discovery_inherited"] is False for row in adjacent_rows.values())
    assert all(row["implementation_route_allowed"] is False for row in adjacent_rows.values())

    assert operator_lane["runtime_action"] == "none"
    assert operator_lane["external_skill_activation_allowed"] is False
    assert operator_lane["external_agent_activation_allowed"] is False
    assert operator_lane["external_harness_execution_allowed"] is False
    assert operator_lane["provider_runtime_launch_allowed"] is False
    assert operator_lane["remote_execution_allowed"] is False
    assert "https://github.com/" not in serialized
    assert "python -m pytest" not in serialized
    assert "runtime_execution" not in serialized


def test_current_pass2_operator_lane_routes_124958_reverse_flow_and_general_agents():
    digest = {
        "digest_id": "github-growth-20260705T124958.128997Z",
        "generated_at": "2026-07-05T12:49:58.128997Z",
        "items": [
            {
                "item_id": "p1-skill-route-discovery-reverse-flow",
                "source_url": "https://github.com/lingbol088-spec/reverse-flow-skill",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "reverse-flow-skill is an AI Agent / Codex skill workflow with "
                    "skills/reverse-flow/SKILL.md, scripts, local sandbox defaults, "
                    "install examples, and workflow-gate pressure."
                ),
                "relevance_reason": (
                    "Route matching agent, codex, and skill terms must enter "
                    "skill_route_discovery and map only to bounded local lanes."
                ),
                "risk_flags": [],
                "confidence": 0.79,
            },
            {
                "item_id": "p2-agent-harness-eval-qwen-agentworld",
                "source_url": "https://github.com/QwenLM/Qwen-AgentWorld",
                "event_kind": "RepositoryTrend",
                "summary": "Qwen-AgentWorld is a general agent benchmark and world-model project.",
                "relevance_reason": (
                    "General agent project evidence without skill workflow signals requires "
                    "agent_harness_eval before local implementation lanes."
                ),
                "risk_flags": [],
                "confidence": 0.66,
            },
            {
                "item_id": "p3-agent-harness-eval-fundamental-ava",
                "source_url": "https://github.com/TianhangZhuzth/Fundamental-Ava",
                "event_kind": "RepositoryTrend",
                "summary": "Fundamental-Ava is a general autonomous collaborative agent project.",
                "relevance_reason": (
                    "A second general-agent trend with no route_hints should remain a "
                    "local_validation_candidate behind agent_harness_eval_required."
                ),
                "risk_flags": [],
                "confidence": 0.64,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=3, max_item_text_chars=560)
    lane_map = build_route_hint_lane_map(evidence_package)
    operator_lane = lane_map["current_pass2_skill_route_operator_lane"]
    skill_rows = {row["item_id"]: row for row in operator_lane["skill_route_rows"]}
    adjacent_rows = {row["item_id"]: row for row in operator_lane["adjacent_general_agent_rows"]}
    serialized = json.dumps(operator_lane, sort_keys=True)

    assert operator_lane["source_digest"] == "github-growth-20260705T124958.128997Z"
    assert operator_lane["active_proposal_ids"] == [
        "p1-skill-route-discovery-reverse-flow",
        "p2-agent-harness-eval-qwen-agentworld",
        "p3-agent-harness-eval-fundamental-ava",
        "p4-agent-harness-eval-agents-a1",
        "p5-workflow-usecase-documentation-eval",
        "p4-agent-project-trend-triage-doc",
        "p5-no-direct-runtime-action-for-awesome-workflow",
        "trend:lingbol088-spec/reverse-flow-skill-1",
        "trend:QwenLM/Qwen-AgentWorld-1",
        "trend:TianhangZhuzth/Fundamental-Ava-1",
    ]
    assert operator_lane["status"] == "ready_with_adjacent_agent_eval_gated"
    assert operator_lane["skill_workflow_count"] == 1
    assert operator_lane["adjacent_general_agent_count"] == 2

    reverse_flow = skill_rows["p1-skill-route-discovery-reverse-flow"]
    assert reverse_flow["primary_route"] == "skill_route_discovery"
    assert reverse_flow["selected_local_lane"] == "test"
    assert reverse_flow["accepted_outputs_before_validation"] == []
    assert reverse_flow["accepted_outputs_after_validation"] == ["documentation", "config", "test", "code_patch"]
    assert reverse_flow["route_uncertainty"] == [
        "repository_level_summary_only",
        "low_or_medium_confidence_route_signal",
        "external_skill_not_activated",
    ]

    assert sorted(adjacent_rows) == [
        "p2-agent-harness-eval-qwen-agentworld",
        "p3-agent-harness-eval-fundamental-ava",
    ]
    assert all(row["primary_route"] == "agent_harness_eval_required" for row in adjacent_rows.values())
    assert all(row["direct_allowed_lanes_before_eval"] == [] for row in adjacent_rows.values())
    assert all(row["skill_route_discovery_inherited"] is False for row in adjacent_rows.values())
    assert all(row["implementation_route_allowed"] is False for row in adjacent_rows.values())
    assert all("missing_local_agent_harness_fixture" in row["route_uncertainty"] for row in adjacent_rows.values())
    assert all("low_or_medium_confidence_route_signal" in row["route_uncertainty"] for row in adjacent_rows.values())

    assert operator_lane["runtime_action"] == "none"
    assert operator_lane["external_skill_activation_allowed"] is False
    assert operator_lane["external_agent_activation_allowed"] is False
    assert operator_lane["external_harness_execution_allowed"] is False
    assert operator_lane["provider_runtime_launch_allowed"] is False
    assert operator_lane["remote_execution_allowed"] is False
    assert "https://github.com/" not in serialized
    assert "python -m pytest" not in serialized
    assert "runtime_execution" not in serialized


def test_mixed_skill_workflow_probe_routes_fablecodex_to_skill_discovery_first():
    digest = {
        "digest_id": "github-growth-mixed-skill-workflow-probe",
        "generated_at": "2026-06-20T17:52:08Z",
        "items": [
            {
                "item_id": "fablecodex-workflow-skill-probe",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "FableCodex: Codex plugin with skill workflow gates, examples, tests, evals, "
                    "verification habits, and local routing docs."
                ),
                "relevance_reason": (
                    "Mixed codex, workflow, skill, plugin, and eval signals should be classified "
                    "before deciding whether agent harness evaluation is needed."
                ),
                "risk_flags": [],
                "confidence": 0.86,
            },
            {
                "item_id": "omnigent-general-agent-project",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "omnigent-ai/omnigent: general AI agent framework and meta-harness.",
                "relevance_reason": "General agent project movement requires harness evaluation first.",
                "risk_flags": [],
                "confidence": 0.74,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    mixed_probe = lane_map["mixed_skill_workflow_probe"]
    general_eval = lane_map["general_agent_project_eval"]
    fable_row = next(row for row in lane_map["route_classifier"] if row["item_id"] == "fablecodex-workflow-skill-probe")
    omnigent_row = next(row for row in lane_map["route_classifier"] if row["item_id"] == "omnigent-general-agent-project")

    assert fable_row["route_class"] == "skill_workflow"
    assert fable_row["route_hints"] == ["skill_route_discovery", "agent_harness_eval"]
    assert fable_row["allowed_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert fable_row["evaluation_lane"] == "skill_route_discovery_first"
    assert fable_row["route_probe_decision"] == "skill_route_discovery_first"
    assert "mixed_skill_workflow_probe" in fable_row["reasons"]

    assert mixed_probe["candidate_count"] == 1
    assert mixed_probe["decision_policy"] == "skill_route_discovery_first_for_skill_or_workflow_specific_evidence"
    assert mixed_probe["agent_harness_eval_allowed_after"] == "local_corroboration_or_general_agent_project_claim"
    assert mixed_probe["secondary_lane_status"] == "blocked_until_local_corroboration"
    assert mixed_probe["activation_gate"] == "local_skill_route_validation_before_secondary_harness_eval"
    assert mixed_probe["recommended_local_lane_order"] == ["test", "documentation", "config", "code_patch"]
    assert set(mixed_probe["recommended_local_lane_order"]) == set(mixed_probe["allowed_local_lanes"])
    assert mixed_probe["runtime_action"] == "none"
    assert mixed_probe["external_skill_activation_allowed"] is False
    assert mixed_probe["external_agent_activation_allowed"] is False
    assert mixed_probe["raw_source_url_export_allowed"] is False
    assert mixed_probe["denied_actions"] == [
        "install",
        "enable",
        "run",
        "execute",
        "clone_and_run",
        "profile_write",
        "memory_write",
        "provider_launch",
        "remote_execution",
        "raw_source_url_export",
        "upstream_body_export",
    ]
    assert mixed_probe["candidates"] == [
        {
            "item_id": "fablecodex-workflow-skill-probe",
            "source_url_hash": stable_hash({"source_url": "https://github.com/baskduf/FableCodex"}),
            "route_class": "skill_workflow",
            "route_probe_decision": "skill_route_discovery_first",
            "route_profiles": ["codex_workflow_gate"],
            "primary_lane": "skill_route_discovery",
            "secondary_lane": "agent_harness_eval_after_local_corroboration",
            "secondary_lane_status": "blocked_until_local_corroboration",
            "activation_gate": "local_skill_route_validation_before_secondary_harness_eval",
            "allowed_local_lanes": ["documentation", "config", "test", "code_patch"],
            "recommended_local_lane_order": ["test", "documentation", "config", "code_patch"],
            "required_local_validation": [
                "pytest tests/test_github_growth.py -q -k mixed_skill_workflow",
                "pytest tests/test_proposal_eval.py -q -k route_hint_lane_map",
            ],
            "runtime_action": "none",
            "external_skill_activation_allowed": False,
            "external_agent_activation_allowed": False,
            "denied_actions": [
                "install",
                "enable",
                "run",
                "execute",
                "clone_and_run",
                "profile_write",
                "memory_write",
                "provider_launch",
                "remote_execution",
                "raw_source_url_export",
                "upstream_body_export",
            ],
        }
    ]

    assert omnigent_row["route_class"] == "general_agent_project"
    assert omnigent_row["route_probe_decision"] == ""
    assert general_eval["candidate_count"] == 1
    assert general_eval["candidates"][0]["item_id"] == "omnigent-general-agent-project"
    assert general_eval["skill_route_discovery_inherited"] is False


def test_skill_route_profiles_are_visible_before_local_lane_activation():
    digest = {
        "digest_id": "github-growth-20260621T091208-skill-route-profiles",
        "generated_at": "2026-06-21T09:12:08Z",
        "items": [
            {
                "item_id": "proposal-skill-workflow-fablecodex-probe",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "FableCodex Codex plugin with workflow gates, examples, tests, "
                    "evals, and verification habits."
                ),
                "relevance_reason": "Mixed skill and workflow repositories require skill_route_discovery first.",
                "risk_flags": [],
                "confidence": 0.86,
            },
            {
                "item_id": "proposal-skill-route-discovery-compass",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "COMPASS Skills skill ecosystem with task handoff, collaboration profile state, "
                    "local memory, and workflow routing."
                ),
                "relevance_reason": "State/profile skill repositories need bounded local lanes before activation.",
                "risk_flags": [],
                "confidence": 0.82,
            },
            {
                "item_id": "proposal-skill-route-discovery-threejs-game",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": (
                    "Three.js Game Skills director skill package for browser game workflow, "
                    "gameplay, QA validation, graphics, and Vite checks."
                ),
                "relevance_reason": "Domain-specific skill repositories should remain local validation candidates.",
                "risk_flags": [],
                "confidence": 0.78,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=3, max_item_text_chars=420)
    lane_map = build_route_hint_lane_map(evidence_package)
    classifier_rows = {row["item_id"]: row for row in lane_map["route_classifier"]}
    candidate_rows = {row["item_id"]: row for row in lane_map["skill_route_local_lane_candidates"]["rows"]}
    serialized = json.dumps(lane_map, sort_keys=True)

    assert lane_map["skill_route_local_lane_candidates"]["candidate_count"] == 3
    assert lane_map["skill_route_local_lane_candidates"]["rows_bounded"] is True
    assert lane_map["skill_route_local_lane_candidates"]["runtime_action"] == "none"
    assert lane_map["skill_route_local_lane_candidates"]["external_skill_activation_allowed"] is False
    assert classifier_rows["proposal-skill-workflow-fablecodex-probe"]["route_profiles"] == ["codex_workflow_gate"]
    assert classifier_rows["proposal-skill-route-discovery-compass"]["route_profiles"] == [
        "skill_ecosystem_state_handoff"
    ]
    assert classifier_rows["proposal-skill-route-discovery-threejs-game"]["route_profiles"] == [
        "game_frontend_workflow"
    ]
    assert candidate_rows["proposal-skill-workflow-fablecodex-probe"]["route_probe_decision"] == (
        "skill_route_discovery_first"
    )
    assert candidate_rows["proposal-skill-workflow-fablecodex-probe"]["activation_gate"] == (
        "local_skill_route_validation_before_secondary_harness_eval"
    )
    assert candidate_rows["proposal-skill-route-discovery-compass"]["activation_gate"] == (
        "local_validation_before_activation"
    )
    assert candidate_rows["proposal-skill-route-discovery-threejs-game"]["activation_gate"] == (
        "local_validation_before_activation"
    )
    assert all(row["local_lanes"] == ["documentation", "config", "test", "code_patch"] for row in candidate_rows.values())
    assert all(row["local_validation_required"] is True for row in candidate_rows.values())
    assert "https://github.com/" not in serialized


def test_skill_route_discovery_boosts_repeated_trend_fork_and_push_activity():
    digest = {
        "digest_id": "github-growth-skill-route-activity-pressure",
        "generated_at": "2026-06-20T06:12:07Z",
        "items": [
            {
                "item_id": "general-agent-runtime",
                "source_url": "https://github.com/omnigent-ai/omnigent",
                "event_kind": "RepositoryTrend",
                "summary": "omnigent-ai/omnigent: general AI agent runtime with provider activity.",
                "relevance_reason": "Useful agent project movement without a skill workflow route signal.",
                "risk_flags": [],
                "confidence": 0.56,
            },
            {
                "item_id": "compass-skills-trend",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "dongshuyan/compass-skills: task routing skills and workflow guidance.",
                "relevance_reason": "Skill repository trend evidence should map to bounded local lanes.",
                "risk_flags": [],
                "confidence": 0.50,
            },
            {
                "item_id": "compass-skills-fork",
                "source_url": "https://github.com/lineCode/compass-skills",
                "event_kind": "ForkEvent",
                "summary": "lineCode/compass-skills fork keeps the same skill workflow package visible.",
                "relevance_reason": "Fork movement is lineage pressure for skill route discovery only.",
                "risk_flags": [],
                "confidence": 0.50,
            },
            {
                "item_id": "compass-skills-push",
                "source_url": "https://github.com/dongshuyan/compass-skills/commit/abc123",
                "event_kind": "PushEvent",
                "summary": "push to main: update skill workflow routing notes.",
                "relevance_reason": "Push activity supports a stronger bounded skill route discovery candidate.",
                "risk_flags": [],
                "confidence": 0.50,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=260)
    lane_map = build_route_hint_lane_map(evidence_package)

    assert evidence_package["context_budget"]["selected_item_ids"] == [
        "compass-skills-push",
        "compass-skills-trend",
    ]
    assert evidence_package["context_budget"]["truncated_item_ids"] == [
        "compass-skills-fork",
        "general-agent-runtime",
    ]
    assert lane_map["route_activity_pressure"]["repeated_project_count"] == 1
    repeated_project = lane_map["route_activity_pressure"]["repeated_projects"][0]
    assert repeated_project["activity_count"] == 2
    assert repeated_project["event_kinds"] == ["PushEvent", "RepositoryTrend"]
    assert repeated_project["item_ids"] == ["compass-skills-push", "compass-skills-trend"]
    assert repeated_project["allowed_lanes"] == ["documentation", "config", "test", "code_patch"]
    assert repeated_project["runtime_action"] == "none"
    assert repeated_project["local_validation_required"] is True
    assert lane_map["route_activity_pressure"]["external_skill_activation_allowed"] is False
    assert all(
        row["repeated_skill_activity_signal"] is True
        for row in lane_map["route_classifier"]
        if row["route_class"] == "skill_workflow"
    )


def test_skill_route_discovery_accepts_only_bounded_repository_trend_lanes():
    digest = {
        "digest_id": "github-growth-skill-route-focused-lanes",
        "generated_at": "2026-06-18T10:40:44Z",
        "items": [
            {
                "item_id": "fablecodex-workflow-gates",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": "FableCodex: Codex skill and workflow gates for inspecting evidence before completion.",
                "relevance_reason": "Skill repository trend evidence should map to bounded local validation lanes.",
                "risk_flags": [],
                "confidence": 0.91,
            },
            {
                "item_id": "compass-skills-routing",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "compass-skills: personal alignment skill ecosystem for AI agents and task routing.",
                "relevance_reason": "Skill ecosystem evidence can inform local route discovery without expansion.",
                "risk_flags": [],
                "confidence": 0.88,
            },
            {
                "item_id": "threejs-game-skills-pack",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": "threejs-game-skills: agent skills for polished Three.js browser game workflows and QA.",
                "relevance_reason": "Skill-pack evidence should remain documentation, config, test, or code patch work.",
                "risk_flags": [],
                "confidence": 0.86,
            },
        ],
    }
    evidence_package = build_proposal_evidence_package(digest, max_items=3, max_item_text_chars=260)
    allowed_lanes = evidence_package["policy"]["route_hint_validation_lanes"]["skill_route_discovery"]

    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-skill-route-focused-lanes",
            "run_interpretation": "Skill repositories can propose only bounded local validation work.",
            "self_model_reading": {"status": "left_unchanged"},
            "proposals": [
                {
                    "proposal_id": f"skill-route-{kind}",
                    "kind": kind,
                    "summary": f"Map skill repository evidence to {kind} work.",
                    "evidence_refs": ["fablecodex-workflow-gates", "compass-skills-routing"],
                    "added_risk_flags": [],
                    "validation_task": f"Run focused local tests for skill-route {kind} mapping.",
                    "rationale": "The selected evidence is skill/workflow-shaped and supports bounded local validation.",
                    "uncertainty": "Repository summaries do not prove upstream implementation details.",
                    "self_effect": "Improves deterministic trend evidence routing.",
                    "action_lane": "local_validation_candidate",
                }
                for kind in allowed_lanes
            ],
            "rejected_items": [],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="hybrid")

    assert allowed_lanes == ["documentation", "config", "test", "code_patch"]
    assert evidence_package["context_budget"]["selected_item_ids"] == [
        "fablecodex-workflow-gates",
        "compass-skills-routing",
        "threejs-game-skills-pack",
    ]
    assert all("skill_route_discovery" in item["route_hints"] for item in evidence_package["items"])
    assert review.status == "accepted"
    assert review.rejected_count == 0
    assert [candidate["kind"] for candidate in review.accepted_candidates] == allowed_lanes
    assert all(
        candidate["evidence_urls"]
        == [
            "https://github.com/baskduf/FableCodex",
            "https://github.com/dongshuyan/compass-skills",
        ]
        for candidate in review.accepted_candidates
    )


@pytest.mark.parametrize(
    ("proposal_kind", "evidence_refs", "expected_error"),
    [
        (
            "follow_up_issue",
            ["fablecodex-workflow-gates"],
            "skill_route_discovery proposals must use one of: documentation, config, test, code_patch",
        ),
        (
            "config",
            ["https://github.com/dongshuyan/compass-skills"],
            "evidence_refs contain unknown item ids: https://github.com/dongshuyan/compass-skills",
        ),
        (
            "test",
            ["threejs-game-skills-pack"],
            "evidence_refs contain unknown item ids: threejs-game-skills-pack",
        ),
    ],
)
def test_skill_route_discovery_rejects_unsupported_lanes_and_unselected_refs(
    proposal_kind,
    evidence_refs,
    expected_error,
):
    digest = {
        "digest_id": "github-growth-skill-route-focused-rejections",
        "generated_at": "2026-06-18T10:40:44Z",
        "items": [
            {
                "item_id": "fablecodex-workflow-gates",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": "FableCodex: Codex skill and workflow gates for inspecting evidence.",
                "relevance_reason": "Skill route discovery should stay in bounded local lanes.",
                "risk_flags": [],
                "confidence": 0.91,
            },
            {
                "item_id": "compass-skills-routing",
                "source_url": "https://github.com/dongshuyan/compass-skills",
                "event_kind": "RepositoryTrend",
                "summary": "compass-skills: skill ecosystem for AI agent task routing.",
                "relevance_reason": "Skill route discovery should cite selected item ids only.",
                "risk_flags": [],
                "confidence": 0.88,
            },
            {
                "item_id": "threejs-game-skills-pack",
                "source_url": "https://github.com/majidmanzarpour/threejs-game-skills",
                "event_kind": "RepositoryTrend",
                "summary": "threejs-game-skills: agent skill pack for game workflow and QA.",
                "relevance_reason": "This lower-ranked item is intentionally outside the selected context budget.",
                "risk_flags": [],
                "confidence": 0.2,
            },
        ],
    }
    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=260)
    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-skill-route-focused-rejections",
            "run_interpretation": "Reject skill-route proposals that escape lane or evidence-ref constraints.",
            "self_model_reading": {"status": "left_unchanged"},
            "proposals": [
                {
                    "proposal_id": "skill-route-rejected",
                    "kind": proposal_kind,
                    "summary": "Malformed skill route discovery proposal.",
                    "evidence_refs": evidence_refs,
                    "added_risk_flags": [],
                    "validation_task": "Run focused tests for rejection behavior.",
                    "rationale": "Malformed candidates must not pass deterministic local review.",
                    "uncertainty": "This is a synthetic rejection fixture.",
                    "self_effect": "Would weaken skill-route evidence boundaries if accepted.",
                    "action_lane": "local_validation_candidate",
                }
            ],
            "rejected_items": [],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="hybrid")

    assert evidence_package["context_budget"]["selected_item_ids"] == [
        "fablecodex-workflow-gates",
        "compass-skills-routing",
    ]
    assert evidence_package["context_budget"]["truncated_item_ids"] == ["threejs-game-skills-pack"]
    assert review.status == "rejected"
    assert review.accepted_count == 0
    assert expected_error in review.rejected_candidates[0]["errors"]


def test_skill_workflow_route_hints_reject_unbounded_candidate_kind():
    digest = {
        "digest_id": "github-growth-skill-route-lane",
        "generated_at": "2026-06-17T15:40:01Z",
        "items": [
            {
                "item_id": "fablecodex-skill-workflow",
                "source_url": "https://github.com/baskduf/FableCodex",
                "event_kind": "RepositoryTrend",
                "summary": "baskduf/FableCodex: Codex skills and workflow gates for local agent work",
                "relevance_reason": "Skill route discovery should stay in bounded local validation lanes.",
                "risk_flags": [],
                "confidence": 0.87,
            },
        ],
    }
    evidence_package = build_proposal_evidence_package(digest, max_items=1, max_item_text_chars=240)
    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-skill-route-lane",
            "run_interpretation": "Skill-route evidence should not escape its lane constraints.",
            "self_model_reading": {"status": "unchanged"},
            "proposals": [
                {
                    "proposal_id": "unbounded-skill-follow-up",
                    "kind": "follow_up_issue",
                    "summary": "Send skill route discovery into an unbounded follow-up lane.",
                    "evidence_refs": ["fablecodex-skill-workflow"],
                    "added_risk_flags": [],
                    "validation_task": "Add unit coverage for skill route lane enforcement.",
                    "rationale": "This negative case verifies deterministic route-hint policy.",
                    "uncertainty": "Synthetic fixture only covers the route-hint lane boundary.",
                    "self_effect": "Would weaken bounded skill route discovery if accepted.",
                    "action_lane": "local_validation_candidate",
                }
            ],
            "rejected_items": [],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="hybrid")

    assert review.status == "rejected"
    assert review.accepted_count == 0
    assert review.rejected_candidates[0]["errors"] == [
        "skill_route_discovery proposals must use one of: documentation, config, test, code_patch"
    ]


def test_proposal_evidence_package_disambiguates_duplicate_item_ids_under_context_pressure():
    digest = {
        "digest_id": "github-growth-duplicate-context-ids",
        "generated_at": "2026-06-16T07:06:01Z",
        "items": [
            {
                "item_id": "duplicate-signal",
                "source_url": "https://github.com/microsoft/fastcontext/first",
                "event_kind": "PushEvent",
                "summary": "lower confidence duplicate",
                "relevance_reason": "should be truncated by max_items",
                "risk_flags": [],
                "confidence": 0.2,
            },
            {
                "item_id": "duplicate-signal",
                "source_url": "https://github.com/microsoft/fastcontext/second",
                "event_kind": "IssueCommentEvent",
                "summary": "higher confidence duplicate",
                "relevance_reason": "should stay selectable by unique evidence ref",
                "risk_flags": [],
                "confidence": 0.9,
            },
            {
                "item_id": "duplicate-signal",
                "source_url": "https://github.com/omnigent-ai/omnigent/privacy",
                "event_kind": "IssuesEvent",
                "summary": "risk duplicate",
                "relevance_reason": "risk evidence should remain first and unambiguous",
                "risk_flags": ["privacy-leakage"],
                "confidence": 0.1,
            },
        ],
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=2, max_item_text_chars=200)

    assert [item["item_id"] for item in evidence_package["items"]] == [
        "duplicate-signal__item_3",
        "duplicate-signal__item_2",
    ]
    assert evidence_package["context_budget"]["selected_item_ids"] == [
        "duplicate-signal__item_3",
        "duplicate-signal__item_2",
    ]
    assert evidence_package["context_budget"]["truncated_item_ids"] == ["duplicate-signal__item_1"]
    assert [
        (item["original_index"], item["item_id"], item["decision"], item["rank"])
        for item in evidence_package["context_budget"]["item_selection_diagnostics"]
    ] == [
        (0, "duplicate-signal__item_1", "truncated", 3),
        (1, "duplicate-signal__item_2", "selected", 2),
        (2, "duplicate-signal__item_3", "selected", 1),
    ]

    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-duplicate-context-ids",
            "run_interpretation": "Use the risk duplicate as the review boundary.",
            "self_model_reading": {"status": "unchanged"},
            "proposals": [
                {
                    "proposal_id": "duplicate-ref-route",
                    "kind": "follow_up_issue",
                    "summary": "Keep privacy-boundary duplicate evidence reviewable.",
                    "evidence_refs": ["duplicate-signal__item_3"],
                    "added_risk_flags": [],
                    "validation_task": "Validate locally that duplicate context ids remain unambiguous.",
                    "rationale": "Duplicate upstream ids should not collapse proposal evidence.",
                    "uncertainty": "Synthetic duplicate ids only cover local evidence packaging, and truncated duplicates may hide additional details.",
                    "self_effect": "Improves replayability of future trend-derived proposals.",
                    "action_lane": "risk_review_before_local_change",
                }
            ],
            "rejected_items": ["duplicate-signal__item_1"],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="hybrid")

    assert review.status == "accepted"
    assert review.accepted_candidates[0]["evidence_refs"] == ["duplicate-signal__item_3"]
    assert review.accepted_candidates[0]["evidence_urls"] == ["https://github.com/omnigent-ai/omnigent/privacy"]


def test_pr_event_digest_pressure_records_uncertainty_and_rejects_duplicate_proposals():
    items = []
    for index in range(10):
        items.append(
            {
                "item_id": f"pr-{index + 1}",
                "source_url": f"https://github.com/omnigent-ai/omnigent/pull/{index + 1}",
                "event_kind": "PullRequestEvent",
                "summary": "opened pull request: untitled pull request",
                "relevance_reason": "generic PullRequestEvent item with missing PR details",
                "risk_flags": [],
                "confidence": 0.7,
            }
        )
    digest = {
        "digest_id": "github-growth-pr-event-pressure",
        "generated_at": "2026-06-16T08:37:05Z",
        "items": items,
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=3, max_item_text_chars=160)
    uncertainty = evidence_package["context_budget"]["evidence_truncation_uncertainty"]
    preflight = build_context_budget_preflight(evidence_package)

    assert evidence_package["context_budget"]["items_truncated"] is True
    assert evidence_package["context_budget"]["selected_item_ids"] == ["pr-1", "pr-2", "pr-3"]
    assert evidence_package["context_budget"]["truncated_item_ids"] == [
        "pr-4",
        "pr-5",
        "pr-6",
        "pr-7",
        "pr-8",
        "pr-9",
        "pr-10",
    ]
    assert uncertainty == {
        "missing_detail_risk": True,
        "reasons": [
            "max_items_omitted_whole_digest_items",
            "truncated_pull_request_activity_may_hide_pr_specific_details",
            "generic_or_untitled_pull_request_items_have_missing_title_context",
            "repeated_generic_pull_request_metadata_clustered_and_downweighted",
        ],
        "selected_event_kind_counts": {"PullRequestEvent": 3},
        "truncated_event_kind_counts": {"PullRequestEvent": 7},
        "selected_generic_pr_count": 3,
        "truncated_generic_pr_count": 7,
        "selected_generic_push_count": 0,
        "truncated_generic_push_count": 0,
        "selected_generic_pr_cluster_count": 1,
        "truncated_generic_pr_cluster_count": 1,
        "repeated_generic_pr_cluster_count": 1,
        "max_generic_pr_cluster_size": 10,
        "citation_scope": "cite_selected_item_ids_only",
        "url_policy": "do_not_add_urls",
    }
    assert preflight["evidence_truncation_uncertainty"] == uncertainty
    assert "github.com" not in json.dumps(uncertainty, sort_keys=True)

    raw_response = json.dumps(
        {
            "schema_version": 1,
            "input_digest_id": "github-growth-pr-event-pressure",
            "run_interpretation": "Many generic PR events were truncated, so only selected refs are usable.",
            "self_model_reading": {"status": "unchanged"},
            "proposals": [
                {
                    "proposal_id": "pr-pressure-context",
                    "kind": "no_action",
                    "summary": "Treat repeated generic PR events as aggregate uncertainty only.",
                    "evidence_refs": ["pr-1", "pr-2"],
                    "added_risk_flags": [],
                    "validation_task": "Record the selected generic PR refs as low-detail context without local behavior change.",
                    "rationale": "The selected events show repeated generic PR activity but no PR-specific implementation detail.",
                    "uncertainty": "Most PR items were truncated and titles were generic, so PR-specific details are unknown.",
                    "self_effect": "Keeps proposal generation from overclaiming high-volume PR streams.",
                    "action_lane": "aggregate_uncertainty_context",
                },
                {
                    "proposal_id": "pr-pressure-route",
                    "kind": "code_patch",
                    "summary": "Improve PR-event digest resilience under truncation.",
                    "evidence_refs": ["pr-1", "pr-2"],
                    "added_risk_flags": [],
                    "validation_task": "Replay a synthetic high-volume PR-event digest locally.",
                    "rationale": "The selected events show repeated generic PR activity.",
                    "uncertainty": "Most PR items were truncated and titles were generic, so PR-specific details are unknown.",
                    "self_effect": "Would incorrectly promote generic PR metadata into a behavior patch.",
                    "action_lane": "local_validation_candidate",
                },
                {
                    "proposal_id": "pr-truncated-ref",
                    "kind": "documentation",
                    "summary": "Invalidly cites a truncated item.",
                    "evidence_refs": ["pr-9"],
                    "added_risk_flags": [],
                    "validation_task": "Document selected-item-only citation.",
                    "rationale": "This should fail because pr-9 was outside the frozen items list.",
                    "uncertainty": "Truncated refs cannot be used as evidence.",
                    "self_effect": "Would weaken replayability.",
                    "action_lane": "local_validation_candidate",
                },
            ],
            "rejected_items": ["pr-4", "pr-5", "pr-6", "pr-7", "pr-8", "pr-9", "pr-10"],
        }
    )

    review = review_llm_proposal_response(raw_response, evidence_package, mode="hybrid")

    assert review.status == "accepted"
    assert review.accepted_count == 1
    assert review.rejected_count == 2
    assert review.accepted_candidates[0]["proposal_id"] == "pr-pressure-context"
    assert review.accepted_candidates[0]["evidence_refs"] == ["pr-1", "pr-2"]
    assert any(
        "generic push or untitled pull request/review evidence requires a non-generic corroborating item"
        in " ".join(rejected["errors"])
        for rejected in review.rejected_candidates
    )
    assert any(
        "evidence_refs contain unknown item ids: pr-9" in rejected["errors"]
        for rejected in review.rejected_candidates
    )


def test_repeated_untitled_review_events_require_non_generic_corroboration_for_behavior_proposals():
    digest = {
        "digest_id": "github-growth-review-anchor-pressure",
        "generated_at": "2026-06-23T02:56:52Z",
        "items": [
            {
                "item_id": "review-1",
                "source_url": "https://github.com/omnigent-ai/omnigent/pull/598#pullrequestreview-4541005030",
                "event_kind": "PullRequestReviewEvent",
                "summary": "submitted pull request review (commented): untitled pull request",
                "relevance_reason": "review anchor exposed without inspected finding details",
                "risk_flags": [],
                "confidence": 0.82,
            },
            {
                "item_id": "review-2",
                "source_url": "https://github.com/omnigent-ai/omnigent/pull/769#pullrequestreview-4549609007",
                "event_kind": "PullRequestReviewEvent",
                "summary": "submitted pull request review (commented): untitled pull request",
                "relevance_reason": "review anchor exposed without inspected finding details",
                "risk_flags": [],
                "confidence": 0.81,
            },
            {
                "item_id": "review-3",
                "source_url": "https://github.com/omnigent-ai/omnigent/pull/833#pullrequestreview-4542080133",
                "event_kind": "PullRequestReviewEvent",
                "summary": "submitted pull request review (commented): untitled pull request",
                "relevance_reason": "review anchor exposed without inspected finding details",
                "risk_flags": [],
                "confidence": 0.8,
            },
            {
                "item_id": "covered-push",
                "source_url": "https://github.com/omnigent-ai/omnigent/commit/validation123",
                "event_kind": "PushEvent",
                "summary": "test(runner): add context budget validation coverage",
                "relevance_reason": "commit message names test coverage for runner behavior",
                "risk_flags": [],
                "confidence": 0.7,
            },
        ],
    }
    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=180)

    review_only_response = {
        "schema_version": 1,
        "input_digest_id": "github-growth-review-anchor-pressure",
        "run_interpretation": "Repeated low-detail review anchors are uncertainty context.",
        "self_model_reading": {"status": "unchanged"},
        "proposals": [
            {
                "proposal_id": "review-anchor-feature-route",
                "kind": "test",
                "summary": "Add a feature-specific test from untitled review anchors.",
                "evidence_refs": ["review-1", "review-2"],
                "added_risk_flags": [],
                "validation_task": "Run a focused proposal interpreter test.",
                "rationale": "Repeated review anchors suggest a useful local validation route.",
                "uncertainty": "Review titles are generic and missing detail, so the upstream finding is unknown.",
                "self_effect": "Would overfit low-detail public review activity.",
                "action_lane": "local_validation_candidate",
            }
        ],
        "rejected_items": [],
    }
    corroborated_response = {
        **review_only_response,
        "proposals": [
            {
                **review_only_response["proposals"][0],
                "proposal_id": "review-anchor-corroborated-route",
                "evidence_refs": ["review-1", "covered-push"],
                "rationale": "The review anchor is low-detail, while the push independently names test coverage.",
            }
        ],
    }

    review_only = review_llm_proposal_response(json.dumps(review_only_response), evidence_package, mode="hybrid")
    corroborated = review_llm_proposal_response(json.dumps(corroborated_response), evidence_package, mode="hybrid")

    uncertainty = evidence_package["context_budget"]["evidence_truncation_uncertainty"]
    assert uncertainty["selected_generic_pr_count"] == 3
    assert uncertainty["repeated_generic_pr_cluster_count"] == 1
    assert review_only.status == "rejected"
    assert any(
        "generic push or untitled pull request/review evidence requires a non-generic corroborating item"
        in error
        for error in review_only.rejected_candidates[0]["errors"]
    )
    assert corroborated.status == "accepted"
    assert corroborated.accepted_candidates[0]["evidence_refs"] == ["review-1", "covered-push"]


def test_generic_pr_opened_and_labeled_metadata_is_clustered_and_downweighted():
    items = [
        {
            "item_id": "detailed-validation-push",
            "source_url": "https://github.com/omnigent-ai/omnigent/commit/validation123",
            "event_kind": "PushEvent",
            "summary": "add validation coverage for local proposal routing",
            "relevance_reason": "detailed validation signal with test coverage",
            "risk_flags": [],
            "confidence": 0.64,
        },
        {
            "item_id": "detailed-issue",
            "source_url": "https://github.com/omnigent-ai/omnigent/issues/82",
            "event_kind": "IssuesEvent",
            "summary": "controller should explain generic PR uncertainty",
            "relevance_reason": "specific issue text names local validation behavior",
            "risk_flags": [],
            "confidence": 0.83,
        },
    ]
    for index, action in enumerate(["opened", "opened", "opened", "labeled", "labeled"], start=1):
        items.append(
            {
                "item_id": f"generic-pr-{index}",
                "source_url": f"https://github.com/omnigent-ai/omnigent/pull/{index}",
                "event_kind": "PullRequestEvent",
                "summary": f"{action} pull request: untitled pull request",
                "relevance_reason": "generic PullRequestEvent item with missing PR details",
                "risk_flags": [],
                "confidence": 0.9,
            }
        )
    digest = {
        "digest_id": "github-growth-generic-pr-metadata-normalization",
        "generated_at": "2026-06-17T03:03:16Z",
        "items": items,
    }

    evidence_package = build_proposal_evidence_package(digest, max_items=4, max_item_text_chars=160)
    preflight = build_context_budget_preflight(evidence_package)
    uncertainty = preflight["evidence_truncation_uncertainty"]

    assert evidence_package["context_budget"]["selected_item_ids"] == [
        "detailed-validation-push",
        "detailed-issue",
        "generic-pr-4",
        "generic-pr-1",
    ]
    assert evidence_package["context_budget"]["truncated_item_ids"] == [
        "generic-pr-5",
        "generic-pr-2",
        "generic-pr-3",
    ]
    assert uncertainty["repeated_generic_pr_cluster_count"] == 2
    assert uncertainty["max_generic_pr_cluster_size"] == 3
    assert uncertainty["selected_generic_pr_count"] == 2
    assert uncertainty["truncated_generic_pr_count"] == 3
    assert "repeated_generic_pull_request_metadata_clustered_and_downweighted" in uncertainty["reasons"]
    generic_diagnostics = [
        diagnostic
        for diagnostic in preflight["item_selection_diagnostics"]
        if diagnostic.get("low_detail_duplicate_pr")
    ]
    assert len(generic_diagnostics) == 5
    assert {diagnostic["generic_pr_cluster_count"] for diagnostic in generic_diagnostics} == {2, 3}
    assert "github.com" not in json.dumps(preflight, sort_keys=True)
    assert "untitled pull request" not in json.dumps(preflight, sort_keys=True)


def test_digest_groups_low_detail_upstream_movement_by_available_triage_fields():
    signals = [
        GrowthSignal(
            event_id="generic-pr",
            repo="omnigent-ai/omnigent",
            kind="PullRequestEvent",
            title="opened pull request: untitled pull request",
            url="https://github.com/omnigent-ai/omnigent/pull/500",
            relevance_reason="generic PullRequestEvent item with missing PR details",
            risk_flags=[],
            recommended_action="compare the pull request approach with local agent behavior before drafting a change",
            confidence=0.9,
        ),
        GrowthSignal(
            event_id="review-anchor",
            repo="omnigent-ai/omnigent",
            kind="PullRequestReviewEvent",
            title="submitted pull request review (commented): untitled pull request",
            url="https://github.com/omnigent-ai/omnigent/pull/500#pullrequestreview-4529338631",
            relevance_reason="review anchor exposed without inspected finding details",
            risk_flags=[],
            recommended_action="treat repeated pull request review activity as supporting evidence for local validation or test changes",
            confidence=0.8,
        ),
        GrowthSignal(
            event_id="e2e-push",
            repo="omnigent-ai/omnigent",
            kind="PushEvent",
            title="push to copilot/fix-e2e-claude-sdk-sandbox-tests: test(e2e): isolate policy allow response",
            url="https://github.com/omnigent-ai/omnigent",
            relevance_reason="push commit message names e2e test coverage",
            risk_flags=[],
            recommended_action="cluster commit messages and keep only patterns with clear test evidence",
            confidence=0.72,
        ),
    ]

    digest = build_digest(
        ["omnigent-ai/omnigent"],
        signals,
        state=GrowthState(),
        generated_at="2026-06-19T00:32:07Z",
        proposals=[],
    )

    triage = digest["upstream_movement_triage"]
    assert triage["low_detail_item_count"] == 2
    assert triage["specific_item_count"] == 1
    assert triage["promotion_rule"].startswith("Specific local proposals require")

    clusters_by_key = {cluster["key"]: cluster for cluster in triage["clusters"]}
    assert clusters_by_key["branch=unknown|timing=pre_merge|subsystem=unknown"] == {
        "key": "branch=unknown|timing=pre_merge|subsystem=unknown",
        "branch": "unknown",
        "merge_timing": "pre_merge",
        "subsystem": "unknown",
        "event_kinds": ["PullRequestEvent"],
        "item_ids": ["generic-pr"],
        "item_count": 1,
        "confirmation_level": "low_detail",
        "missing_details": ["branch", "specific_title_or_body", "subsystem"],
    }
    assert clusters_by_key[
        "branch=copilot/fix-e2e-claude-sdk-sandbox-tests|timing=push|subsystem=tests"
    ]["confirmation_level"] == "specific"


def test_proposal_preflight_requires_confirmation_for_low_detail_upstream_movement():
    proposal = {
        "proposal_id": "low-detail-upstream",
        "kind": "test",
        "summary": "Add a local regression test for generic upstream PR movement.",
        "risk_flags": [],
        "implementation_scope": "local_validation_candidate",
        "validation_gate": "narrow-local-verification",
        "validation_task": "Run a focused local test for upstream movement triage.",
        "upstream_movement_evidence": {
            "status": "needs_triage",
            "confirmation_level": "low_detail",
            "branch": "unknown",
            "merge_timing": "unknown",
            "subsystem": "unknown",
            "missing_details": ["branch", "merge_timing", "subsystem"],
        },
    }

    preflight = proposal_validation_preflight(proposal)

    assert preflight["status"] == "validation_gap"
    assert preflight["validation_gaps"] == ["missing_upstream_movement_confirmation"]


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
        "item_selection_strategy": (
            "risk_flags_then_direct_detail_then_confidence_with_review_activity_and_generic_activity_dedup_then_original_order"
        ),
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
        "evidence_truncation_uncertainty": {
            "missing_detail_risk": False,
            "reasons": [],
            "selected_event_kind_counts": {"PushEvent": 1},
            "truncated_event_kind_counts": {},
            "selected_generic_pr_count": 0,
            "truncated_generic_pr_count": 0,
            "selected_generic_push_count": 0,
            "truncated_generic_push_count": 0,
            "selected_generic_pr_cluster_count": 0,
            "truncated_generic_pr_cluster_count": 0,
            "repeated_generic_pr_cluster_count": 0,
            "max_generic_pr_cluster_size": 0,
            "citation_scope": "cite_selected_item_ids_only",
            "url_policy": "do_not_add_urls",
        },
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
        "config_status": "ok",
        "missing_config_fields": [],
        "token_env_names": [],
        "token_env_present": {},
        "token_required": False,
        "token_value_recorded": False,
        "inline_token_present": False,
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


def test_provider_routing_preflight_reports_missing_token_without_secret_leakage():
    preflight = build_provider_routing_preflight(
        {
            "provider": "openai",
            "model": "databricks-gpt-5",
            "base_url": "https://workspace.example.test/serving-endpoints/chat",
            "token_env": "PROVIDER_API_KEY",
            "requires_api_key": True,
        },
        env={},
    )

    assert preflight["status"] == "missing_required_config"
    assert preflight["config_status"] == "missing_required_config"
    assert preflight["missing_config_fields"] == ["token"]
    assert preflight["token_env_names"] == ["PROVIDER_API_KEY"]
    assert preflight["token_env_present"] == {"PROVIDER_API_KEY": False}
    assert preflight["token_required"] is True
    assert preflight["token_value_recorded"] is False
    assert preflight["inline_token_present"] is False
    preflight_json = json.dumps(preflight, sort_keys=True)
    assert "workspace.example.test" not in preflight_json
    assert "serving-endpoints/chat" not in preflight_json


def test_provider_routing_preflight_records_token_presence_without_token_value():
    preflight = build_provider_routing_preflight(
        {
            "provider": "openai",
            "model": "databricks-gpt-5",
            "base_url": "https://workspace.example.test/serving-endpoints/chat",
            "token_env": "PROVIDER_API_KEY",
            "requires_api_key": True,
        },
        env={"PROVIDER_API_KEY": "sk-live-secret-token"},
    )

    assert preflight["status"] == "route_ok"
    assert preflight["config_status"] == "ok"
    assert preflight["missing_config_fields"] == []
    assert preflight["token_env_present"] == {"PROVIDER_API_KEY": True}
    assert preflight["token_value_recorded"] is False
    preflight_json = json.dumps(preflight, sort_keys=True)
    assert "sk-live-secret-token" not in preflight_json
    assert "workspace.example.test" not in preflight_json


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
    assert (
        preflight["item_selection_strategy"]
        == "risk_flags_then_direct_detail_then_confidence_with_review_activity_and_generic_activity_dedup_then_original_order"
    )
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
        proposal_mode="heuristic",
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
    assert memory["theme_window"]["theme_id"] == "runner-harness-control"
    assert digest["capability_theme_window"]["planned_passes"] == 1
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
        proposal_mode="heuristic",
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
        proposal_mode="heuristic",
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
        proposal_mode="heuristic",
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


def test_memory_theme_window_carries_capability_focus_across_passes():
    memory = GrowthMemory()
    first_digest = {
        "digest_id": "github-growth-theme-1",
        "generated_at": "2026-06-12T00:00:00Z",
        "repositories": ["example/repo"],
        "items": [],
        "proposals": [
            {
                "proposal_id": "runner-replay",
                "kind": "test",
                "summary": "Add runner harness replay coverage for interrupted workflows.",
                "evidence_urls": ["https://github.com/example/repo/pull/1"],
                "requires_approval": False,
            }
        ],
    }
    second_digest = {
        "digest_id": "github-growth-theme-2",
        "generated_at": "2026-06-12T01:00:00Z",
        "repositories": ["example/repo"],
        "items": [],
        "proposals": [
            {
                "proposal_id": "provider-preflight",
                "kind": "test",
                "summary": "Add provider config preflight tests.",
                "evidence_urls": ["https://github.com/example/repo/pull/2"],
                "requires_approval": False,
            }
        ],
    }

    github_growth.update_memory_from_digest(memory, first_digest)
    github_growth.update_memory_from_digest(memory, second_digest)

    assert first_digest["capability_theme_window"]["theme_id"] == "runner-harness-control"
    assert first_digest["capability_theme_window"]["planned_passes"] == 1
    assert second_digest["capability_theme_window"]["theme_id"] == "runner-harness-control"
    assert second_digest["capability_theme_window"]["planned_passes"] == 2
    assert second_digest["capability_theme_window"]["proposal_ids"] == ["runner-replay", "provider-preflight"]


def test_completed_theme_window_rolls_to_next_capability_slice():
    completed = {
        "schema_version": 1,
        "theme_id": "runner-harness-control",
        "title": "Runner and harness control plane",
        "capability_slice": "Make one runner workflow legible end to end.",
        "started_at": "2026-06-12T00:00:00Z",
        "updated_at": "2026-06-12T03:00:00Z",
        "target_passes": 4,
        "planned_passes": 4,
        "status": "complete",
        "proposal_ids": ["runner-replay"],
        "evidence_urls": [],
    }

    window = github_growth.build_capability_theme_window(
        [
            {
                "proposal_id": "provider-preflight",
                "summary": "Add provider config preflight tests for OpenAI route diagnostics.",
                "evidence_urls": ["https://github.com/example/repo/pull/2"],
            }
        ],
        previous_window=completed,
        generated_at="2026-06-12T04:00:00Z",
    )

    assert window["theme_id"] == "provider-runtime-control"
    assert window["previous_theme_id"] == "runner-harness-control"
    assert window["planned_passes"] == 1


def test_heuristic_ranking_boosts_repeated_review_activity_after_safety_and_direct_routes():
    signals = [
        GrowthSignal(
            event_id="trend",
            repo="omnigent-ai/omnigent",
            kind="RepositoryTrend",
            title="trending repository: omnigent-ai/omnigent",
            url="https://github.com/omnigent-ai/omnigent",
            relevance_reason="repository trend has broad harness relevance",
            risk_flags=[],
            recommended_action="review repository trend",
            confidence=0.82,
        ),
        GrowthSignal(
            event_id="direct-pr",
            repo="omnigent-ai/omnigent",
            kind="PullRequestEvent",
            title="opened pull request: add validation harness checks",
            url="https://github.com/omnigent-ai/omnigent/pull/77",
            relevance_reason="direct code patch candidate",
            risk_flags=[],
            recommended_action="compare the pull request approach with local agent behavior before drafting a change",
            confidence=0.62,
        ),
        GrowthSignal(
            event_id="review-event",
            repo="omnigent-ai/omnigent",
            kind="PullRequestReviewEvent",
            title="submitted pull request review: add validation harness checks",
            url="https://github.com/omnigent-ai/omnigent/pull/77#pullrequestreview-1",
            relevance_reason="review activity supports validation route",
            risk_flags=[],
            recommended_action="capture review signal",
            confidence=0.62,
        ),
        GrowthSignal(
            event_id="review-comment",
            repo="omnigent-ai/omnigent",
            kind="PullRequestReviewCommentEvent",
            title="created pull request review comment: add validation harness checks",
            url="https://github.com/omnigent-ai/omnigent/pull/77#discussion_r1",
            relevance_reason="review comment supports test route",
            risk_flags=[],
            recommended_action="capture review signal",
            confidence=0.61,
        ),
        GrowthSignal(
            event_id="risk",
            repo="omnigent-ai/omnigent",
            kind="IssueCommentEvent",
            title="token boundary review",
            url="https://github.com/omnigent-ai/omnigent/issues/5",
            relevance_reason="risk-gated evidence must stay selected",
            risk_flags=["privacy-leakage"],
            recommended_action="record the privacy-leakage boundary",
            confidence=0.1,
        ),
    ]

    proposals = build_proposals(signals, limit=4)

    assert [proposal["proposal_id"] for proposal in proposals] == [
        "risk-1",
        "direct-pr-2",
        "review-event-3",
        "review-comment-4",
    ]


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
    assert plan.capability_theme_window["theme_id"] == "runner-harness-control"
    assert plan.capability_theme_window["planned_passes"] == 1
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
    assert "Choose scope by evidence strength, expected local benefit, rollback coverage, and validation coverage" in plan.task
    assert "may span files, modules, or behavior paths" in plan.task
    assert "do not shrink a justified behavior change merely to look conservative" in plan.task
    assert "Capability theme window:" in plan.task
    assert "Runner and harness control plane" in plan.task
    assert "Planned pass: 1 of 4" in plan.task
    assert "Continuity rule: advance this slice across passes" in plan.task
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
    assert "If no other safe repository change is available, a self-model revision can be the justified improvement for the run." in plan.task
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
    assert "Make one coherent improvement or tightly connected change set per kernel run" in rendered
    assert "Do not equate auditability with smallness" in rendered
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
        "require_explicit_route": True,
        "claude_sdk_permission_mode": None,
        "allow_claude_sdk_auto_permission_mode": True,
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
    assert manifest["provider_preflight"]["route_selector"] == "model_and_profile"
    assert manifest["capability_theme_window"]["theme_id"] == plan.capability_theme_window["theme_id"]
    assert manifest["proposal_ids"] == ["p1"]
    assert manifest["replayable_validation_report"]["provenance"]["capability_theme_id"] == plan.capability_theme_window["theme_id"]
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
            "validation_preflight": {
                "status": "ready",
                "requires_unit_test_or_coverage": False,
                "has_unit_test_signal": False,
                "has_coverage_signal": False,
                "validation_gaps": [],
                "safety_block": False,
                "blocks_autonomous_apply": False,
            },
            "review_metadata": {
                "reviewer_routes": ["general-maintainer-review"],
                "coverage_drop_signal": {
                    "applies": False,
                    "status_on_drop": "not-applicable",
                    "blocking": False,
                },
                "bypass_label_guard": {
                    "status": "passed",
                    "blocked_labels": [],
                    "policy": "bypass-style labels are metadata only and cannot grant autonomous local apply",
                },
            },
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

    run_self_evolution_codex(plan, output_dir=tmp_path / "out", model="gpt-5", command_runner=runner)

    manifest = json.loads((tmp_path / "out" / "latest-self-evolution-manifest.json").read_text(encoding="utf-8"))
    assert manifest["proposal_controls"] == [
        {
            "proposal_id": "governance-1",
            "kind": "test",
            "implementation_scope": "local_validation_candidate",
            "validation_gate": "narrow-local-verification",
            "autonomous_local_apply": "True",
            "validation_preflight": {
                "status": "ready",
                "requires_unit_test_or_coverage": True,
                "has_unit_test_signal": True,
                "has_coverage_signal": False,
                "validation_gaps": [],
                "safety_block": False,
                "blocks_autonomous_apply": False,
            },
            "review_metadata": {
                "reviewer_routes": ["validation-maintainer-review"],
                "coverage_drop_signal": {
                    "applies": False,
                    "status_on_drop": "not-applicable",
                    "blocking": False,
                },
                "bypass_label_guard": {
                    "status": "passed",
                    "blocked_labels": [],
                    "policy": "bypass-style labels are metadata only and cannot grant autonomous local apply",
                },
            },
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
    assert report["template_version"] == 4
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
    assert report["reviewer_routes"] == ["validation-maintainer-review"]
    assert report["coverage_drop_signals"] == [
        {
            "proposal_id": proposal["proposal_id"],
            "applies": False,
            "status_on_drop": "not-applicable",
            "blocking": False,
        }
    ]
    assert report["bypass_label_guard"] == {
        "status": "passed",
        "blocked_labels": [],
        "policy": "bypass-style labels are metadata only and cannot grant autonomous local apply",
    }
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
        "capability_theme_id": "runner-harness-control",
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

    run_self_evolution_codex(plan, output_dir=tmp_path / "out", model="gpt-5", command_runner=runner)

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
            "validation_preflight": {
                "status": "blocked_by_safety_boundary",
                "requires_unit_test_or_coverage": False,
                "has_unit_test_signal": False,
                "has_coverage_signal": False,
                "validation_gaps": [],
                "safety_block": True,
                "blocks_autonomous_apply": True,
            },
            "review_metadata": {
                "reviewer_routes": ["safety-boundary-review"],
                "coverage_drop_signal": {
                    "applies": False,
                    "status_on_drop": "not-applicable",
                    "blocking": False,
                },
                "bypass_label_guard": {
                    "status": "passed",
                    "blocked_labels": [],
                    "policy": "bypass-style labels are metadata only and cannot grant autonomous local apply",
                },
            },
            "safety_boundary_requirement": (
                "Only offensive behavior, abuse, unauthorized access, or privacy leakage is review-only; "
                "all other rollback-backed local changes may proceed."
            ),
        }
    ]
