import json
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from blackhole_agent.github_growth import (
    GitHubEventsClient,
    GitHubTrendConfig,
    GitHubTrendSearchResult,
    GrowthState,
    TrendingRepository,
    app,
    build_self_evolution_plan,
    build_trending_repository_query_for_date,
    extract_growth_signals,
    normalize_event,
    prepare_self_evolution_branch,
    run_intake_once,
    run_self_evolution_codex,
    select_new_events,
)
from blackhole_agent.persona import PERSONA_VERSION, render_persona_layer


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
                "requires_approval": True,
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
    assert "human review" in signals[0].recommended_action


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
    digest = json.loads(result.json_path.read_text(encoding="utf-8"))
    state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert digest["repositories"] == ["example/repo"]
    assert digest["items"][0]["event_kind"] == "PullRequestEvent"
    assert digest["proposals"][0]["kind"] == "code_patch"
    assert state["seen_event_ids"] == ["3"]
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


def test_github_growth_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Discover public GitHub trends" in result.stdout
    assert "--trend-query" in result.stdout
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
    plan = build_self_evolution_plan(digest_with_proposal(), repo_path=tmp_path)

    assert plan is not None
    assert plan.branch_name.startswith("codex/blackhole-evolve/")
    assert "You are Codex running as the local kernel for blackhole-agent." in plan.task
    assert f"Persona version: {PERSONA_VERSION}" in plan.task
    assert "Core mechanism:" in plan.task
    assert "Rollback contract:" in plan.task
    assert "Track GitHub trends on a scheduled cadence, normally hourly." in plan.task
    assert "A restart must be performed by an external scheduler or supervisor" in plan.task
    assert "Do not push, merge" in plan.task
    assert "Improve agent workflow tests" in plan.task


def test_persona_layer_captures_operational_self_model():
    rendered = render_persona_layer()

    assert "Persona layer: blackhole-agent" in rendered
    assert "Selection policy:" in rendered
    assert "Make at most one conceptual improvement per kernel run." in rendered
    assert "create a rollback point" in rendered
    assert "Do not optimize for virality" in rendered


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
    assert rollback_point.rollback_ref.startswith("refs/blackhole-agent/rollback/")
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
