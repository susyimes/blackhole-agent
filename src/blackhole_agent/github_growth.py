"""Hourly GitHub trend intake for a rollback-backed blackhole-agent growth loop.

This controller is adapted from the mini-swe-agent `github_growth` runner. The
important change is the local mutation engine: blackhole-agent can hand a bounded
self-improvement task to the local Codex CLI kernel, write rollback artifacts,
and apply local evolution on a prepared branch.
"""

import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import typer
from rich.console import Console

from blackhole_agent.kernels.codex_cli import CodexCliConfig, CodexCliKernel, CodexCliRunResult
from blackhole_agent.persona import render_persona_layer

_HELP_TEXT = """Discover public GitHub trends and turn them into reviewable growth proposals.

By default the command discovers recently created public repositories that are
gaining attention, then writes local digest/state files. Pass `--repos` to use a
manual repository list instead. With `--evolution-mode plan` it turns signals
into a concrete self-improvement task. With `--evolution-mode codex` it creates
a branch and asks the local Codex CLI kernel to modify this repository locally.
"""

DEFAULT_TOPICS = (
    "agent",
    "automation",
    "benchmark",
    "blackhole",
    "bug",
    "codex",
    "config",
    "github",
    "release",
    "security",
    "test",
    "workflow",
)
INTERESTING_EVENT_TYPES = {
    "IssuesEvent",
    "IssueCommentEvent",
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "PushEvent",
    "ReleaseEvent",
    "RepositoryTrend",
    "WorkflowRunEvent",
}
HIGH_RISK_TERMS = ("auth", "credential", "secret", "security", "token")
GOVERNANCE_CONTROL_TERMS = (
    "approval",
    "approvals",
    "budget",
    "cost",
    "policies",
    "policy",
    "spend",
    "tool access",
    "tool limit",
    "tool limits",
)
REMOTE_EXECUTION_TERMS = (
    "cluster",
    "k8s",
    "kubeconfig",
    "kubernetes",
    "pod",
    "pods",
    "rbac",
    "runner",
    "runners",
    "sandbox",
    "sandboxes",
    "service account",
    "serviceaccount",
)

app = typer.Typer(rich_markup_mode="rich", add_completion=False)
console = Console(highlight=False)


@dataclass(frozen=True)
class GitHubEvent:
    """Normalized GitHub event with only the fields the growth loop needs."""

    id: str
    repo: str
    kind: str
    actor: str
    created_at: str
    title: str
    url: str
    summary: str


@dataclass(frozen=True)
class GrowthSignal:
    """A filtered event that may be worth turning into an improvement proposal."""

    event_id: str
    repo: str
    kind: str
    title: str
    url: str
    relevance_reason: str
    risk_flags: list[str]
    recommended_action: str
    confidence: float


@dataclass
class GrowthState:
    """Cursor state for scheduled GitHub intake."""

    seen_event_ids: set[str] = field(default_factory=set)
    last_seen_at_by_repo: dict[str, str] = field(default_factory=dict)
    trend_seen_repositories: set[str] = field(default_factory=set)
    trend_last_stars_by_repo: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthState":
        return cls(
            seen_event_ids=set(data.get("seen_event_ids", [])),
            last_seen_at_by_repo=dict(data.get("last_seen_at_by_repo", {})),
            trend_seen_repositories=set(data.get("trend_seen_repositories", [])),
            trend_last_stars_by_repo={
                str(repo): int(stars) for repo, stars in dict(data.get("trend_last_stars_by_repo", {})).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seen_event_ids": sorted(self.seen_event_ids),
            "last_seen_at_by_repo": dict(sorted(self.last_seen_at_by_repo.items())),
            "trend_seen_repositories": sorted(self.trend_seen_repositories),
            "trend_last_stars_by_repo": dict(sorted(self.trend_last_stars_by_repo.items())),
        }


@dataclass
class GrowthMemory:
    """Small durable memory used to bias future trend selection."""

    version: int = 1
    repositories: dict[str, dict[str, Any]] = field(default_factory=dict)
    topics: dict[str, dict[str, Any]] = field(default_factory=dict)
    lessons: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthMemory":
        return cls(
            version=int(data.get("version", 1)),
            repositories={str(repo): dict(stats) for repo, stats in dict(data.get("repositories", {})).items()},
            topics={str(topic): dict(stats) for topic, stats in dict(data.get("topics", {})).items()},
            lessons=[dict(lesson) for lesson in data.get("lessons", []) if isinstance(lesson, dict)],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "repositories": dict(sorted(self.repositories.items())),
            "topics": dict(sorted(self.topics.items())),
            "lessons": self.lessons,
        }


@dataclass(frozen=True)
class TrendingRepository:
    """Repository metadata returned by GitHub repository search."""

    full_name: str
    html_url: str
    description: str
    language: str | None
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    created_at: str
    updated_at: str
    pushed_at: str
    topics: list[str]

    @classmethod
    def from_search_item(cls, item: dict[str, Any]) -> "TrendingRepository":
        return cls(
            full_name=str(item.get("full_name") or ""),
            html_url=str(item.get("html_url") or ""),
            description=_compact(item.get("description") or ""),
            language=item.get("language"),
            stargazers_count=int(item.get("stargazers_count") or 0),
            forks_count=int(item.get("forks_count") or 0),
            open_issues_count=int(item.get("open_issues_count") or 0),
            created_at=str(item.get("created_at") or ""),
            updated_at=str(item.get("updated_at") or ""),
            pushed_at=str(item.get("pushed_at") or ""),
            topics=[str(topic) for topic in item.get("topics") or []],
        )


@dataclass(frozen=True)
class GitHubTrendConfig:
    """Controls the GitHub repository search used to approximate public trends."""

    query: str = ""
    window_days: int = 7
    min_stars: int = 25
    limit: int = 10
    sort: str = "stars"
    order: str = "desc"
    include_forks: bool = False


@dataclass(frozen=True)
class GitHubTrendSearchResult:
    """Repositories discovered by one trend search."""

    query: str
    sort: str
    order: str
    window_days: int
    min_stars: int
    repositories: list[TrendingRepository]
    total_count: int
    incomplete_results: bool


@dataclass(frozen=True)
class DigestWriteResult:
    """Paths written by one intake pass."""

    digest: dict[str, Any]
    json_path: Path
    markdown_path: Path
    state_path: Path
    memory_path: Path


@dataclass(frozen=True)
class SelfEvolutionPlan:
    """A bounded task that the local Codex CLI kernel can run against this checkout."""

    generated_at: str
    repo_path: str
    branch_name: str
    task: str
    proposals: list[dict[str, Any]]
    source_digest_id: str
    source_digest_generated_at: str


@dataclass(frozen=True)
class SelfEvolutionRunResult:
    """Result of invoking the Codex CLI kernel on a self-evolution task."""

    command: list[str]
    returncode: int
    task_path: Path
    last_message_path: Path
    branch_name: str
    stdout_tail: str
    stderr_tail: str
    last_message: str


@dataclass(frozen=True)
class RollbackPoint:
    """A local recovery anchor captured before a self-evolution run mutates code."""

    created_at: str
    repo_path: str
    original_branch: str
    original_head: str
    rollback_ref: str
    status_porcelain: str
    restore_commands: list[list[str]]


class GitHubEventsClient:
    """Small GitHub REST client for repository trend search and event feeds."""

    def __init__(
        self,
        *,
        token: str | None = None,
        session: requests.Session | None = None,
        api_base_url: str = "https://api.github.com",
        timeout: int = 30,
    ) -> None:
        self._session = session or requests.Session()
        self._api_base_url = api_base_url.rstrip("/")
        self._timeout = timeout
        self._headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "blackhole-agent-github-growth",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def list_repository_events(self, repo: str, *, per_page: int = 100) -> list[dict[str, Any]]:
        if per_page < 1 or per_page > 100:
            raise ValueError("per_page must be between 1 and 100")
        owner, name = parse_repo_spec(repo)
        url: str | None = f"{self._api_base_url}/repos/{owner}/{name}/events"
        params: dict[str, int] | None = {"per_page": per_page}
        events: list[dict[str, Any]] = []
        while url:
            response = self._session.get(
                url,
                headers=self._headers,
                params=params,
                timeout=self._timeout,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"GitHub events request failed for {repo}: HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError(f"GitHub events request failed for {repo}: expected a JSON list")
            events.extend(payload)
            url = (getattr(response, "links", {}) or {}).get("next", {}).get("url")
            params = None
        return events

    def search_trending_repositories(
        self,
        config: GitHubTrendConfig,
        *,
        now: datetime | None = None,
    ) -> GitHubTrendSearchResult:
        if config.limit < 1 or config.limit > 100:
            raise ValueError("trend limit must be between 1 and 100")
        if config.window_days < 1:
            raise ValueError("trend window days must be at least 1")
        if config.min_stars < 0:
            raise ValueError("trend min stars cannot be negative")
        if config.sort not in {"stars", "forks", "updated"}:
            raise ValueError("trend sort must be one of: stars, forks, updated")
        if config.order not in {"asc", "desc"}:
            raise ValueError("trend order must be one of: asc, desc")

        query = build_trending_repository_query(config, now=now)
        response = self._session.get(
            f"{self._api_base_url}/search/repositories",
            headers=self._headers,
            params={
                "q": query,
                "sort": config.sort,
                "order": config.order,
                "per_page": config.limit,
            },
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub trend search failed: HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise RuntimeError("GitHub trend search failed: expected a JSON object with an items list")
        repositories = [TrendingRepository.from_search_item(item) for item in payload["items"]]
        repositories = [repo for repo in repositories if repo.full_name]
        return GitHubTrendSearchResult(
            query=query,
            sort=config.sort,
            order=config.order,
            window_days=config.window_days,
            min_stars=config.min_stars,
            repositories=repositories,
            total_count=int(payload.get("total_count") or 0),
            incomplete_results=bool(payload.get("incomplete_results") or False),
        )


def build_trending_repository_query(config: GitHubTrendConfig, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    created_since = (now - timedelta(days=config.window_days)).date()
    return build_trending_repository_query_for_date(config, created_since=created_since)


def build_trending_repository_query_for_date(config: GitHubTrendConfig, *, created_since: date) -> str:
    terms = [config.query.strip()] if config.query.strip() else []
    terms.append(f"created:>={created_since.isoformat()}")
    if config.min_stars > 0:
        terms.append(f"stars:>={config.min_stars}")
    if not config.include_forks:
        terms.append("fork:false")
    return " ".join(terms)


def parse_repo_spec(repo: str) -> tuple[str, str]:
    parts = [part.strip() for part in repo.split("/") if part.strip()]
    if len(parts) != 2:
        raise ValueError(f"Repository must be in owner/name form: {repo}")
    return parts[0], parts[1]


def parse_comma_separated(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def load_state(path: Path) -> GrowthState:
    if not path.exists():
        return GrowthState()
    return GrowthState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(path: Path, state: GrowthState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_memory(path: Path) -> GrowthMemory:
    if not path.exists():
        return GrowthMemory()
    return GrowthMemory.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_memory(path: Path, memory: GrowthMemory) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def update_memory_from_digest(memory: GrowthMemory, digest: dict[str, Any], *, lesson_limit: int = 200) -> None:
    generated_at = str(digest.get("generated_at") or "")
    for repo in digest.get("repositories", []):
        touch_memory_stats(memory.repositories, str(repo), generated_at=generated_at)
    for item in digest.get("items", []):
        repo = repo_from_digest_summary(str(item.get("summary") or ""))
        if repo:
            touch_memory_stats(memory.repositories, repo, generated_at=generated_at, useful_increment=1)
        for topic in topics_from_relevance(str(item.get("relevance_reason") or "")):
            touch_memory_stats(memory.topics, topic, generated_at=generated_at, useful_increment=1)
    existing_lesson_ids = {str(lesson.get("lesson_id")) for lesson in memory.lessons}
    for proposal in digest.get("proposals", []):
        proposal_id = str(proposal.get("proposal_id") or "")
        if not proposal_id or proposal_id in existing_lesson_ids:
            continue
        memory.lessons.append(
            {
                "lesson_id": proposal_id,
                "source_digest_id": digest.get("digest_id", ""),
                "generated_at": generated_at,
                "kind": proposal.get("kind", "no_action"),
                "summary": proposal.get("summary", ""),
                "evidence_urls": proposal.get("evidence_urls", []),
                "outcome": "proposed",
                "confidence": proposal.get("confidence"),
            }
        )
        existing_lesson_ids.add(proposal_id)
    if len(memory.lessons) > lesson_limit:
        memory.lessons = memory.lessons[-lesson_limit:]


def touch_memory_stats(
    table: dict[str, dict[str, Any]],
    key: str,
    *,
    generated_at: str,
    useful_increment: int = 0,
) -> None:
    stats = table.setdefault(
        key,
        {
            "seen": 0,
            "useful_signals": 0,
            "validated": 0,
            "failed": 0,
            "last_seen_at": "",
        },
    )
    stats["seen"] = int(stats.get("seen") or 0) + 1
    stats["useful_signals"] = int(stats.get("useful_signals") or 0) + useful_increment
    stats["validated"] = int(stats.get("validated") or 0)
    stats["failed"] = int(stats.get("failed") or 0)
    stats["last_seen_at"] = generated_at


def repo_from_digest_summary(summary: str) -> str:
    if ": " not in summary:
        return ""
    return summary.split(": ", 1)[0].strip()


def topics_from_relevance(relevance_reason: str) -> list[str]:
    prefix = "matched topics: "
    if not relevance_reason.startswith(prefix):
        return []
    return [topic.strip() for topic in relevance_reason.removeprefix(prefix).split(",") if topic.strip()]


def parse_github_timestamp(value: str) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_event(repo: str, raw: dict[str, Any]) -> GitHubEvent:
    payload = raw.get("payload") or {}
    kind = str(raw.get("type") or "UnknownEvent")
    actor = (raw.get("actor") or {}).get("login") or ""
    event_id = str(raw.get("id") or f"{repo}:{kind}:{raw.get('created_at', '')}")
    created_at = str(raw.get("created_at") or "")

    title, url, summary = _event_text(repo, kind, payload)
    return GitHubEvent(
        id=event_id,
        repo=repo,
        kind=kind,
        actor=actor,
        created_at=created_at,
        title=title,
        url=url,
        summary=summary,
    )


def select_new_events(
    repo: str,
    raw_events: list[dict[str, Any]],
    state: GrowthState,
    *,
    lookback_hours: int,
    max_events: int | None = None,
) -> list[GitHubEvent]:
    newest_seen_at = state.last_seen_at_by_repo.get(repo)
    if newest_seen_at:
        since = parse_github_timestamp(newest_seen_at)
    else:
        since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    selected: list[GitHubEvent] = []
    for raw in raw_events:
        event = normalize_event(repo, raw)
        created_at = parse_github_timestamp(event.created_at)
        if event.id in state.seen_event_ids or created_at < since:
            continue
        selected.append(event)
        if max_events is not None and len(selected) >= max_events:
            break
    return selected


def update_state(state: GrowthState, events: list[GitHubEvent]) -> None:
    for event in events:
        state.seen_event_ids.add(event.id)
        current = state.last_seen_at_by_repo.get(event.repo)
        if current is None or parse_github_timestamp(event.created_at) > parse_github_timestamp(current):
            state.last_seen_at_by_repo[event.repo] = event.created_at


def update_trend_state(state: GrowthState, repositories: list[TrendingRepository]) -> None:
    for repository in repositories:
        state.trend_seen_repositories.add(repository.full_name)
        state.trend_last_stars_by_repo[repository.full_name] = repository.stargazers_count


def trend_repository_to_event(
    repository: TrendingRepository,
    *,
    generated_at: str,
    previous_stars: int | None = None,
    first_seen: bool = True,
) -> GitHubEvent:
    language = repository.language or "unknown language"
    topics = ", ".join(repository.topics[:6]) if repository.topics else "none"
    if previous_stars is None:
        star_delta = "unknown"
    else:
        star_delta = str(repository.stargazers_count - previous_stars)
    title = (
        f"trending repository: {repository.full_name} "
        f"({repository.stargazers_count} stars, {language})"
    )
    summary = (
        f"description={repository.description or 'none'}; "
        f"stars={repository.stargazers_count}; forks={repository.forks_count}; "
        f"open_issues={repository.open_issues_count}; star_delta_since_last_run={star_delta}; "
        f"first_seen={first_seen}; created_at={repository.created_at}; pushed_at={repository.pushed_at}; "
        f"topics={topics}"
    )
    return GitHubEvent(
        id=f"trend:{repository.full_name}",
        repo=repository.full_name,
        kind="RepositoryTrend",
        actor=repository.full_name.split("/", 1)[0],
        created_at=generated_at,
        title=title,
        url=repository.html_url or _repo_url(repository.full_name),
        summary=summary,
    )


def build_trend_events(
    repositories: list[TrendingRepository],
    *,
    state: GrowthState,
    generated_at: str,
) -> list[GitHubEvent]:
    return [
        trend_repository_to_event(
            repository,
            generated_at=generated_at,
            previous_stars=state.trend_last_stars_by_repo.get(repository.full_name),
            first_seen=repository.full_name not in state.trend_seen_repositories,
        )
        for repository in repositories
    ]


def build_trend_source_metadata(result: GitHubTrendSearchResult, *, state: GrowthState) -> dict[str, Any]:
    repositories: list[dict[str, Any]] = []
    for repository in result.repositories:
        previous_stars = state.trend_last_stars_by_repo.get(repository.full_name)
        repositories.append(
            {
                "full_name": repository.full_name,
                "html_url": repository.html_url,
                "description": repository.description,
                "language": repository.language,
                "stargazers_count": repository.stargazers_count,
                "forks_count": repository.forks_count,
                "open_issues_count": repository.open_issues_count,
                "star_delta_since_last_run": None
                if previous_stars is None
                else repository.stargazers_count - previous_stars,
                "first_seen": repository.full_name not in state.trend_seen_repositories,
                "created_at": repository.created_at,
                "updated_at": repository.updated_at,
                "pushed_at": repository.pushed_at,
                "topics": repository.topics,
            }
        )
    return {
        "kind": "github_trending_repositories",
        "query": result.query,
        "sort": result.sort,
        "order": result.order,
        "window_days": result.window_days,
        "min_stars": result.min_stars,
        "total_count": result.total_count,
        "incomplete_results": result.incomplete_results,
        "repositories": repositories,
    }


def extract_growth_signals(events: list[GitHubEvent], *, topics: list[str]) -> list[GrowthSignal]:
    topic_terms = [topic.lower() for topic in topics]
    signals: list[GrowthSignal] = []
    for event in events:
        haystack = f"{event.kind} {event.title} {event.summary}".lower()
        matched_topics = [topic for topic in topic_terms if topic in haystack]
        if event.kind not in INTERESTING_EVENT_TYPES and not matched_topics:
            continue
        risk_flags = detect_risk_flags(haystack)
        if matched_topics:
            relevance = "matched topics: " + ", ".join(sorted(set(matched_topics)))
            confidence = 0.82
        else:
            relevance = f"{event.kind} is useful for observing upstream project movement"
            confidence = 0.62
        signals.append(
            GrowthSignal(
                event_id=event.id,
                repo=event.repo,
                kind=event.kind,
                title=event.title,
                url=event.url,
                relevance_reason=relevance,
                risk_flags=risk_flags,
                recommended_action=recommend_action(event, risk_flags),
                confidence=confidence,
            )
        )
    return signals


def detect_risk_flags(haystack: str) -> list[str]:
    flags = {term for term in HIGH_RISK_TERMS if term in haystack}
    if any(contains_risk_term(haystack, term) for term in GOVERNANCE_CONTROL_TERMS):
        flags.add("governance-control")
    if any(contains_risk_term(haystack, term) for term in REMOTE_EXECUTION_TERMS):
        flags.add("remote-execution")
    return sorted(flags)


def contains_risk_term(haystack: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", haystack) is not None


def recommend_action(event: GitHubEvent, risk_flags: list[str]) -> str:
    if "governance-control" in risk_flags:
        return "summarize the control pattern and require a local validation task before borrowing agent governance behavior"
    if risk_flags:
        return "summarize the risk pattern and require rollback-backed validation before borrowing it"
    if event.kind == "RepositoryTrend":
        return "review the repository for reusable patterns and turn only one concrete lesson into a validation task"
    if event.kind == "ReleaseEvent":
        return "review release notes for reusable implementation or workflow changes"
    if event.kind == "PullRequestEvent":
        return "compare the pull request approach with local agent behavior before drafting a change"
    if event.kind == "PushEvent":
        return "cluster commit messages and keep only patterns with clear test evidence"
    if event.kind in {"IssuesEvent", "IssueCommentEvent"}:
        return "turn the issue signal into a small hypothesis and validation checklist"
    return "capture the lesson as a proposal; do not mutate the project automatically"


def build_digest(
    repos: list[str],
    signals: list[GrowthSignal],
    *,
    state: GrowthState,
    generated_at: str | None = None,
    source: dict[str, Any] | None = None,
    memory: GrowthMemory | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    digest_id = "github-growth-" + generated_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
    digest = {
        "digest_id": digest_id,
        "generated_at": generated_at,
        "repositories": repos,
        "cursor": dict(sorted(state.last_seen_at_by_repo.items())),
        "items": [
            {
                "source_url": signal.url,
                "event_kind": signal.kind,
                "summary": f"{signal.repo}: {signal.title}",
                "relevance_reason": signal.relevance_reason,
                "risk_flags": signal.risk_flags,
                "confidence": signal.confidence,
            }
            for signal in signals
        ],
        "proposals": build_proposals(signals, memory=memory),
    }
    if source is not None:
        digest["source"] = source
    return digest


def build_proposals(
    signals: list[GrowthSignal],
    *,
    memory: GrowthMemory | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    ranked_signals = rank_signals_with_memory(signals, memory=memory)
    for index, signal in enumerate(ranked_signals[:limit], start=1):
        proposals.append(
            {
                "proposal_id": f"{signal.event_id}-{index}",
                "kind": classify_proposal_kind(signal),
                "summary": f"Borrow cautiously from {signal.repo}: {signal.title}. {signal.recommended_action}.",
                "evidence_urls": [signal.url] if signal.url else [],
                "requires_approval": False,
            }
        )
    return proposals


def rank_signals_with_memory(
    signals: list[GrowthSignal],
    *,
    memory: GrowthMemory | None = None,
) -> list[GrowthSignal]:
    if memory is None:
        return signals
    indexed = list(enumerate(signals))
    indexed.sort(key=lambda item: (-memory_bias_for_signal(item[1], memory), item[0]))
    return [signal for _, signal in indexed]


def memory_bias_for_signal(signal: GrowthSignal, memory: GrowthMemory) -> float:
    repo_stats = memory.repositories.get(signal.repo, {})
    repo_bias = memory_stats_bias(repo_stats)
    topic_bias = sum(memory_stats_bias(memory.topics.get(topic, {})) for topic in topics_from_relevance(signal.relevance_reason))
    return repo_bias + min(topic_bias, 2.0)


def memory_stats_bias(stats: dict[str, Any]) -> float:
    useful = int(stats.get("useful_signals") or 0)
    validated = int(stats.get("validated") or 0)
    failed = int(stats.get("failed") or 0)
    return max(0.0, min(3.0, useful * 0.15 + validated * 0.5 - failed * 0.35))


def classify_proposal_kind(signal: GrowthSignal) -> str:
    if signal.risk_flags:
        return "follow_up_issue"
    if signal.kind == "RepositoryTrend":
        return "follow_up_issue"
    if signal.kind == "ReleaseEvent":
        return "documentation"
    if signal.kind == "PushEvent":
        return "test"
    if signal.kind == "PullRequestEvent":
        return "code_patch"
    if signal.kind in {"IssuesEvent", "IssueCommentEvent"}:
        return "follow_up_issue"
    return "no_action"


def render_markdown_digest(digest: dict[str, Any]) -> str:
    lines = [
        "# GitHub Growth Digest",
        "",
        f"Digest: `{digest['digest_id']}`",
        f"Generated: {digest['generated_at']}",
        "",
    ]
    source = digest.get("source")
    if source:
        lines.extend(
            [
                "## Trend Source",
                "",
                f"- Kind: `{source.get('kind', 'unknown')}`",
                f"- Query: `{source.get('query', '')}`",
                f"- Sort: `{source.get('sort', '')} {source.get('order', '')}`",
                f"- Total matches: {source.get('total_count', 0)}",
                f"- Incomplete results: {source.get('incomplete_results', False)}",
                "",
            ]
        )
        event_fetch_errors = source.get("event_fetch_errors") or []
        if event_fetch_errors:
            lines.extend(["### Event Fetch Warnings", ""])
            for error in event_fetch_errors:
                lines.append(f"- `{error.get('repo', 'unknown')}`: {error.get('error', '')}")
            lines.append("")
        repositories = source.get("repositories") or []
        if repositories:
            lines.extend(["### Trending Repositories", ""])
            for repository in repositories:
                delta = repository.get("star_delta_since_last_run")
                delta_text = "unknown" if delta is None else f"{delta:+d}"
                first_seen = "new" if repository.get("first_seen") else "seen"
                lines.append(
                    "- "
                    f"[{repository['full_name']}]({repository['html_url']}) "
                    f"- {repository.get('stargazers_count', 0)} stars ({delta_text}), "
                    f"{repository.get('language') or 'unknown language'}, {first_seen}"
                )
            lines.append("")
    lines.extend(["## Sources", ""])
    for repo in digest["repositories"]:
        lines.append(f"- `{repo}`")
    lines.extend(["", "## Items", ""])
    if not digest["items"]:
        lines.append("No new growth signals matched this pass.")
    for item in digest["items"]:
        risk = ", ".join(item.get("risk_flags") or ["none"])
        lines.extend(
            [
                f"- [{item['summary']}]({item['source_url']})",
                f"  - Event: `{item['event_kind']}`",
                f"  - Relevance: {item['relevance_reason']}",
                f"  - Risk flags: {risk}",
                f"  - Confidence: {item['confidence']:.2f}",
            ]
        )
    lines.extend(["", "## Proposals", ""])
    if not digest["proposals"]:
        lines.append("No proposals generated.")
    for proposal in digest["proposals"]:
        evidence = ", ".join(proposal.get("evidence_urls") or ["no external URL"])
        lines.extend(
            [
                f"- `{proposal['kind']}`: {proposal['summary']}",
                f"  - Evidence: {evidence}",
                f"  - Autonomous local apply: {not proposal['requires_approval']}",
            ]
        )
    return "\n".join(lines) + "\n"


def build_self_evolution_plan(
    digest: dict[str, Any],
    *,
    repo_path: Path,
    branch_prefix: str = "codex/blackhole-evolve",
    max_proposals: int = 3,
    force: bool = False,
    extra_instructions: str = "",
) -> SelfEvolutionPlan | None:
    """Turn a digest into a concrete Codex CLI task for local self-improvement."""

    proposals = list(digest.get("proposals", []))[:max_proposals]
    if not proposals and not force:
        return None
    if not proposals:
        proposals = [
            {
                "proposal_id": "fallback-local-observability",
                "kind": "test",
                "summary": "Improve the blackhole-agent growth controller's observability or tests.",
                "evidence_urls": [],
                "requires_approval": False,
            }
        ]

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    branch_name = build_evolution_branch_name(branch_prefix, generated_at, proposals[0]["summary"])
    task = render_self_evolution_task(
        proposals,
        repo_path=repo_path,
        branch_name=branch_name,
        digest_id=str(digest.get("digest_id", "")),
        digest_generated_at=str(digest.get("generated_at", "")),
        extra_instructions=extra_instructions,
    )
    return SelfEvolutionPlan(
        generated_at=generated_at,
        repo_path=str(repo_path),
        branch_name=branch_name,
        task=task,
        proposals=proposals,
        source_digest_id=str(digest.get("digest_id", "")),
        source_digest_generated_at=str(digest.get("generated_at", "")),
    )


def build_evolution_branch_name(branch_prefix: str, generated_at: str, title: str) -> str:
    stamp = generated_at.replace("-", "").replace(":", "").replace("+00:00", "Z").replace("Z", "")
    slug = slugify_branch_part(title)[:48] or "blackhole-growth"
    return f"{branch_prefix.strip('/')}/{stamp}-{slug}"


def slugify_branch_part(value: str) -> str:
    chars: list[str] = []
    previous_dash = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    return "".join(chars).strip("-")


def render_self_evolution_task(
    proposals: list[dict[str, Any]],
    *,
    repo_path: Path,
    branch_name: str,
    digest_id: str,
    digest_generated_at: str,
    extra_instructions: str = "",
) -> str:
    proposal_lines: list[str] = []
    for index, proposal in enumerate(proposals, start=1):
        evidence = ", ".join(proposal.get("evidence_urls") or ["local controller fallback"])
        proposal_lines.extend(
            [
                f"{index}. {proposal['summary']}",
                f"   Proposal ID: {proposal.get('proposal_id', '')}",
                f"   Kind: {proposal.get('kind', 'no_action')}",
                f"   Evidence: {evidence}",
                f"   Autonomous local apply: {not proposal.get('requires_approval', True)}",
            ]
        )
    extra = f"\nAdditional operator instructions:\n{extra_instructions.strip()}\n" if extra_instructions.strip() else ""
    return "\n".join(
        [
            "You are Codex running as the local kernel for blackhole-agent.",
            "",
            render_persona_layer(),
            "",
            f"Repository path: {repo_path}",
            f"Working branch prepared by controller: {branch_name}",
            f"Source digest: {digest_id}",
            f"Digest generated at: {digest_generated_at}",
            "",
            "Goal:",
            "Implement one small, coherent self-improvement inspired by the proposals below.",
            "Prefer changes that improve reliability, validation, observability, tests, or developer workflow.",
            "",
            "Digest evidence policy:",
            "- Treat the Source digest and proposal Evidence URLs as the primary context for this run.",
            "- Review only enough external evidence to extract one reusable lesson; do not re-run broad trend discovery.",
            "- If evidence is unavailable, stale, or too vague, record that uncertainty and improve local validation instead.",
            "",
            "Runtime policy budget:",
            "- Network: use only proposal Evidence URLs and narrowly required official documentation.",
            "- Filesystem: stay inside this repository and create a rollback point before edits.",
            "- Shell: run only the narrowest useful local validation commands.",
            "- Autonomy: make one conceptual improvement; do not push, restart, or provision remote sandboxes.",
            "",
            "Proposals:",
            *proposal_lines,
            "",
            "Operating constraints:",
            "- Stay inside this repository.",
            "- Apply local repository changes autonomously when they are small, logged, and rollback-backed.",
            "- Use only capabilities and runtime configuration available to this run.",
            "- Record material filesystem and external actions in run artifacts.",
            "- Keep the diff focused enough to audit quickly after the fact.",
            "- Add or update tests or docs whenever behavior changes.",
            "- Run the narrowest useful validation command and include the result in the final answer.",
            "- If the proposals are unsafe or too vague, improve the growth controller's safety or tests instead.",
            "",
            "Completion criteria:",
            "- The repository has a concrete local diff on this branch, or a clear no-op explanation if no safe change exists.",
            "- The final answer summarizes changed files, validation, and remaining review notes.",
            extra,
        ]
    )


def write_self_evolution_plan(output_dir: Path, plan: SelfEvolutionPlan) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"self-evolution-plan-{timestamp}.json"
    markdown_path = output_dir / f"self-evolution-plan-{timestamp}.md"
    json_text = json.dumps(asdict(plan), indent=2, sort_keys=True) + "\n"
    markdown_text = "\n".join(
        [
            "# Self-Evolution Plan",
            "",
            f"Generated: {plan.generated_at}",
            f"Branch: `{plan.branch_name}`",
            f"Repository: `{plan.repo_path}`",
            f"Source digest: `{plan.source_digest_id}`",
            "",
            "## Task",
            "",
            plan.task,
        ]
    )
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text + "\n", encoding="utf-8")
    (output_dir / "latest-self-evolution-plan.json").write_text(json_text, encoding="utf-8")
    (output_dir / "latest-self-evolution-plan.md").write_text(markdown_text + "\n", encoding="utf-8")
    return json_path, markdown_path


def create_rollback_point(
    *,
    repo_path: Path,
    status_porcelain: str,
    command_runner: Any = subprocess.run,
) -> RollbackPoint:
    """Create a durable local git ref that can restore the pre-evolution HEAD."""

    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    head = run_controller_command(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_path,
        command_runner=command_runner,
        check=True,
    ).stdout.strip()
    branch = run_controller_command(
        ["git", "branch", "--show-current"],
        cwd=repo_path,
        command_runner=command_runner,
        check=True,
    ).stdout.strip()
    rollback_ref = f"refs/blackhole-agent/rollback/{timestamp}-{head[:12]}"
    run_controller_command(
        ["git", "update-ref", rollback_ref, head],
        cwd=repo_path,
        command_runner=command_runner,
        check=True,
    )
    restore_commands = build_restore_commands(original_branch=branch, rollback_ref=rollback_ref)
    return RollbackPoint(
        created_at=created_at,
        repo_path=str(repo_path),
        original_branch=branch,
        original_head=head,
        rollback_ref=rollback_ref,
        status_porcelain=status_porcelain,
        restore_commands=restore_commands,
    )


def build_restore_commands(*, original_branch: str, rollback_ref: str) -> list[list[str]]:
    checkout_command = ["git", "switch", original_branch] if original_branch else ["git", "switch", "--detach", rollback_ref]
    return [
        checkout_command,
        ["git", "reset", "--hard", rollback_ref],
        ["git", "clean", "-fd"],
    ]


def write_rollback_point(output_dir: Path, rollback_point: RollbackPoint) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"rollback-point-{timestamp}.json"
    markdown_path = output_dir / f"rollback-point-{timestamp}.md"
    json_text = json.dumps(asdict(rollback_point), indent=2, sort_keys=True) + "\n"
    markdown_text = render_rollback_point_markdown(rollback_point)
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    (output_dir / "latest-rollback-point.json").write_text(json_text, encoding="utf-8")
    (output_dir / "latest-rollback-point.md").write_text(markdown_text, encoding="utf-8")
    return json_path, markdown_path


def render_rollback_point_markdown(rollback_point: RollbackPoint) -> str:
    lines = [
        "# Rollback Point",
        "",
        f"Created: {rollback_point.created_at}",
        f"Repository: `{rollback_point.repo_path}`",
        f"Original branch: `{rollback_point.original_branch or '(detached HEAD)'}`",
        f"Original HEAD: `{rollback_point.original_head}`",
        f"Rollback ref: `{rollback_point.rollback_ref}`",
        "",
        "## Recovery Commands",
        "",
        "Run these from the repository root only after choosing to discard the failed self-evolution diff:",
        "",
    ]
    lines.extend(f"```bash\n{render_shell_command(command)}\n```" for command in rollback_point.restore_commands)
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `git reset --hard` discards tracked working tree changes.",
            "- `git clean -fd` removes untracked files and directories.",
            "- Keep this artifact outside any cleanup path until the recovered agent has started successfully.",
            "",
        ]
    )
    if rollback_point.status_porcelain.strip():
        lines.extend(["## Pre-Run Dirty Status", "", "```text", rollback_point.status_porcelain.rstrip(), "```", ""])
    return "\n".join(lines)


def render_shell_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def prepare_self_evolution_branch(
    plan: SelfEvolutionPlan,
    *,
    output_dir: Path | None = None,
    allow_dirty: bool = False,
    command_runner: Any = subprocess.run,
) -> RollbackPoint | None:
    repo_path = Path(plan.repo_path)
    status = run_controller_command(["git", "status", "--porcelain"], cwd=repo_path, command_runner=command_runner)
    if not allow_dirty:
        if status.stdout.strip():
            raise RuntimeError("Refusing self-evolution on a dirty worktree. Commit/stash changes or pass --allow-dirty.")
    rollback_point: RollbackPoint | None = None
    if output_dir is not None:
        rollback_point = create_rollback_point(
            repo_path=repo_path,
            status_porcelain=status.stdout,
            command_runner=command_runner,
        )
        write_rollback_point(output_dir, rollback_point)
    run_controller_command(["git", "switch", "-c", plan.branch_name], cwd=repo_path, command_runner=command_runner, check=True)
    return rollback_point


def run_self_evolution_codex(
    plan: SelfEvolutionPlan,
    *,
    output_dir: Path,
    model: str | None = None,
    profile: str | None = None,
    sandbox: str = "workspace-write",
    approval_policy: str = "never",
    ignore_user_config: bool = True,
    bypass_approvals_and_sandbox: bool = False,
    timeout_seconds: int = 3600,
    command_runner: Any = subprocess.run,
) -> SelfEvolutionRunResult:
    config = CodexCliConfig(
        model=model,
        profile=profile,
        sandbox=sandbox,
        approval_policy=approval_policy,
        ignore_user_config=ignore_user_config,
        bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
    )
    kernel = CodexCliKernel(config, command_runner=command_runner)
    result: CodexCliRunResult = kernel.run(
        plan.task,
        cwd=Path(plan.repo_path),
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
    )
    run_result = SelfEvolutionRunResult(
        command=result.command,
        returncode=result.returncode,
        task_path=result.task_path,
        last_message_path=result.last_message_path,
        branch_name=plan.branch_name,
        stdout_tail=result.stdout_tail,
        stderr_tail=result.stderr_tail,
        last_message=result.last_message,
    )
    (output_dir / "latest-self-evolution-run.json").write_text(
        json.dumps(
            {
                "command": run_result.command,
                "returncode": run_result.returncode,
                "task_path": str(run_result.task_path),
                "last_message_path": str(run_result.last_message_path),
                "branch_name": run_result.branch_name,
                "stdout_tail": run_result.stdout_tail,
                "stderr_tail": run_result.stderr_tail,
                "last_message": run_result.last_message,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_result


def run_controller_command(
    command: list[str],
    *,
    cwd: Path,
    command_runner: Any = subprocess.run,
    timeout: int = 30,
    check: bool = False,
) -> subprocess.CompletedProcess:
    completed = command_runner(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and completed.returncode != 0:
        rendered = " ".join(shlex.quote(part) for part in command)
        raise RuntimeError(f"Command failed ({completed.returncode}): {rendered}\n{completed.stderr}")
    return completed


def run_intake_once(
    *,
    repos: list[str] | None = None,
    output_dir: Path,
    state_path: Path | None = None,
    memory_path: Path | None = None,
    token: str | None = None,
    topics: list[str] | None = None,
    lookback_hours: int = 1,
    max_events_per_repo: int = 100,
    trend_config: GitHubTrendConfig | None = None,
    client: GitHubEventsClient | None = None,
) -> DigestWriteResult:
    repo_specs = repos or []
    if not repo_specs and trend_config is None:
        raise ValueError("At least one repository is required")
    normalized_repos = ["/".join(parse_repo_spec(repo)) for repo in repo_specs]
    state_file = state_path or output_dir / "state.json"
    memory_file = memory_path or output_dir / "memory.json"
    state = load_state(state_file)
    memory = load_memory(memory_file)
    github = client or GitHubEventsClient(token=token)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    trend_result: GitHubTrendSearchResult | None = None
    trend_events: list[GitHubEvent] = []
    trend_source: dict[str, Any] | None = None
    if trend_config is not None:
        trend_result = github.search_trending_repositories(trend_config)
        trend_repos = [repository.full_name for repository in trend_result.repositories]
        normalized_repos = list(dict.fromkeys([*normalized_repos, *trend_repos]))
        trend_events = build_trend_events(trend_result.repositories, state=state, generated_at=generated_at)
        trend_source = build_trend_source_metadata(trend_result, state=state)

    events: list[GitHubEvent] = []
    event_fetch_errors: list[dict[str, str]] = []
    for repo in normalized_repos:
        try:
            raw_events = github.list_repository_events(repo, per_page=max_events_per_repo)
        except RuntimeError as error:
            if trend_config is None:
                raise
            event_fetch_errors.append({"repo": repo, "error": str(error)})
            continue
        events.extend(
            select_new_events(repo, raw_events, state, lookback_hours=lookback_hours)
        )
    if trend_source is not None:
        trend_source["event_fetch_errors"] = event_fetch_errors
    events.sort(key=lambda event: parse_github_timestamp(event.created_at), reverse=True)
    signals = extract_growth_signals([*trend_events, *events], topics=topics or list(DEFAULT_TOPICS))
    update_state(state, events)
    if trend_result is not None:
        update_trend_state(state, trend_result.repositories)
    digest = build_digest(
        normalized_repos,
        signals,
        state=state,
        generated_at=generated_at,
        source=trend_source,
        memory=memory,
    )
    update_memory_from_digest(memory, digest)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"github-growth-digest-{timestamp}.json"
    markdown_path = output_dir / f"github-growth-digest-{timestamp}.md"
    json_text = json.dumps(digest, indent=2, sort_keys=True) + "\n"
    markdown_text = render_markdown_digest(digest)
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown_text, encoding="utf-8")
    (output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (output_dir / "latest.md").write_text(markdown_text, encoding="utf-8")
    save_state(state_file, state)
    save_memory(memory_file, memory)
    return DigestWriteResult(
        digest=digest,
        json_path=json_path,
        markdown_path=markdown_path,
        state_path=state_file,
        memory_path=memory_file,
    )


def _event_text(repo: str, kind: str, payload: dict[str, Any]) -> tuple[str, str, str]:
    if kind == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        title = _compact(pr.get("title") or "untitled pull request")
        action = payload.get("action") or "updated"
        return f"{action} pull request: {title}", pr.get("html_url") or _repo_url(repo), _compact(pr.get("body") or "")
    if kind in {"IssuesEvent", "IssueCommentEvent"}:
        issue = payload.get("issue") or {}
        title = _compact(issue.get("title") or "untitled issue")
        action = payload.get("action") or "updated"
        comment = payload.get("comment") or {}
        body = comment.get("body") or issue.get("body") or ""
        return f"{action} issue: {title}", issue.get("html_url") or _repo_url(repo), _compact(body)
    if kind == "ReleaseEvent":
        release = payload.get("release") or {}
        name = _compact(release.get("name") or release.get("tag_name") or "release")
        action = payload.get("action") or "published"
        return f"{action} release: {name}", release.get("html_url") or _repo_url(repo), _compact(release.get("body") or "")
    if kind == "PushEvent":
        commits = payload.get("commits") or []
        ref = str(payload.get("ref") or "").removeprefix("refs/heads/")
        messages = [_compact(commit.get("message") or "") for commit in commits if isinstance(commit, dict)]
        summary = "; ".join(message for message in messages if message)
        title = f"push to {ref or 'repository'}"
        if messages:
            title = f"{title}: {messages[0]}"
        url = _repo_url(repo)
        if len(commits) == 1 and isinstance(commits[0], dict) and commits[0].get("sha"):
            url = f"{_repo_url(repo)}/commit/{commits[0]['sha']}"
        return title, url, summary
    if kind == "CreateEvent":
        ref_type = payload.get("ref_type") or "ref"
        ref = payload.get("ref") or ""
        return f"created {ref_type}: {ref}", _repo_url(repo), ""
    if kind == "ForkEvent":
        forkee = payload.get("forkee") or {}
        return f"forked to {forkee.get('full_name', 'unknown fork')}", forkee.get("html_url") or _repo_url(repo), ""
    return kind, _repo_url(repo), _compact(json.dumps(payload, sort_keys=True)[:500])


def _compact(value: object) -> str:
    return " ".join(str(value).split())


def _repo_url(repo: str) -> str:
    return f"https://github.com/{repo}"


# fmt: off
@app.command(help=_HELP_TEXT)
def main(
    repos: str = typer.Option("", "--repos", "-r", help="Optional comma-separated repositories; omit to discover public GitHub trends."),
    trend_query: str = typer.Option("", "--trend-query", help="Additional GitHub repository search terms, such as language:Python or topic:agents."),
    trend_window_days: int = typer.Option(7, "--trend-window-days", min=1, help="Discover repositories created within this many days."),
    trend_min_stars: int = typer.Option(25, "--trend-min-stars", min=0, help="Minimum stars for discovered trend repositories."),
    trend_limit: int = typer.Option(10, "--trend-limit", min=1, max=100, help="Maximum trend repositories to track per pass."),
    trend_sort: str = typer.Option("stars", "--trend-sort", help="Trend search sort: stars, forks, or updated."),
    trend_order: str = typer.Option("desc", "--trend-order", help="Trend search order: asc or desc."),
    include_forks: bool = typer.Option(False, "--include-forks", help="Include forked repositories in trend discovery."),
    output_dir: Path = typer.Option(Path(".blackhole-agent/github-growth"), "--output-dir", "-o", help="Directory for digest and state files."),
    state_path: Path | None = typer.Option(None, "--state", help="State file path. Defaults to <output-dir>/state.json."),
    memory_path: Path | None = typer.Option(None, "--memory", help="Memory file path. Defaults to <output-dir>/memory.json."),
    token_env: str = typer.Option("GITHUB_TOKEN", "--token-env", help="Environment variable containing a GitHub token."),
    topics: str = typer.Option("", "--topics", help="Comma-separated relevance terms. Defaults to agent/workflow/test/security topics."),
    lookback_hours: int = typer.Option(24, "--lookback-hours", min=1, help="Initial event lookback window when no state exists."),
    max_events_per_repo: int = typer.Option(100, "--max-events-per-repo", min=1, max=100, help="GitHub event page size; all Link-paginated pages are fetched."),
    interval_seconds: int = typer.Option(0, "--interval-seconds", min=0, help="Run forever at this interval; 0 runs exactly once."),
    evolution_mode: str = typer.Option("digest", "--evolution-mode", help="One of: digest, plan, codex."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="blackhole-agent checkout to improve in plan/codex mode."),
    force_evolve: bool = typer.Option(False, "--force-evolve", help="Create a fallback self-evolution task even without matched signals."),
    branch_prefix: str = typer.Option("codex/blackhole-evolve", "--branch-prefix", help="Branch prefix used by codex mode."),
    model: str | None = typer.Option(None, "-m", "--model", help="Model to pass to Codex CLI in codex mode."),
    profile: str | None = typer.Option(None, "--profile", help="Codex config profile to pass in codex mode."),
    sandbox: str = typer.Option("workspace-write", "--sandbox", help="Codex sandbox for codex mode."),
    approval_policy: str = typer.Option("never", "--approval-policy", help="Legacy compatibility option; current codex exec has no approval flag."),
    ignore_user_config: bool = typer.Option(True, "--ignore-user-config/--use-user-config", help="Ignore user Codex config in codex mode while keeping auth available."),
    bypass_approvals_and_sandbox: bool = typer.Option(False, "--bypass-approvals-and-sandbox", help="Pass Codex's dangerous full-access bypass flag in codex mode."),
    allow_dirty: bool = typer.Option(False, "--allow-dirty", help="Allow codex mode to start from a dirty worktree."),
    codex_timeout_seconds: int = typer.Option(3600, "--codex-timeout-seconds", min=1, help="Timeout for the Codex CLI kernel run."),
    extra_instruction: str = typer.Option("", "--extra-instruction", help="Additional instruction appended to the self-evolution task."),
) -> None:
    # fmt: on
    repo_list = parse_comma_separated(repos)
    if evolution_mode not in {"digest", "plan", "codex"}:
        raise typer.BadParameter("--evolution-mode must be one of: digest, plan, codex")
    if trend_sort not in {"stars", "forks", "updated"}:
        raise typer.BadParameter("--trend-sort must be one of: stars, forks, updated")
    if trend_order not in {"asc", "desc"}:
        raise typer.BadParameter("--trend-order must be one of: asc, desc")
    if evolution_mode == "codex" and interval_seconds > 0:
        raise typer.BadParameter("--evolution-mode codex is one-shot; use a scheduler to launch separate runs")
    topic_list = parse_comma_separated(topics) or list(DEFAULT_TOPICS)
    token = os.getenv(token_env)
    trend_config = None
    if not repo_list:
        trend_config = GitHubTrendConfig(
            query=trend_query,
            window_days=trend_window_days,
            min_stars=trend_min_stars,
            limit=trend_limit,
            sort=trend_sort,
            order=trend_order,
            include_forks=include_forks,
        )

    while True:
        result = run_intake_once(
            repos=repo_list,
            output_dir=output_dir,
            state_path=state_path,
            memory_path=memory_path,
            token=token,
            topics=topic_list,
            lookback_hours=lookback_hours,
            max_events_per_repo=max_events_per_repo,
            trend_config=trend_config,
        )
        source = result.digest.get("source") or {}
        if source:
            console.print(
                f"Trend search tracked {len(source.get('repositories') or [])} repo(s) "
                f"from query [bold]{source.get('query', '')}[/bold]"
            )
        console.print(f"Wrote {len(result.digest['items'])} item(s) to [bold green]{result.markdown_path}[/bold green]")
        console.print(f"Updated memory at [bold green]{result.memory_path}[/bold green]")
        if evolution_mode in {"plan", "codex"}:
            plan = build_self_evolution_plan(
                result.digest,
                repo_path=repo_path.resolve(),
                branch_prefix=branch_prefix,
                force=force_evolve,
                extra_instructions=extra_instruction,
            )
            if plan is None:
                console.print("No self-evolution plan created because no proposals matched this pass.")
            else:
                _, markdown_path = write_self_evolution_plan(output_dir, plan)
                console.print(f"Wrote self-evolution plan to [bold green]{markdown_path}[/bold green]")
                if evolution_mode == "codex":
                    rollback_point = prepare_self_evolution_branch(
                        plan,
                        output_dir=output_dir,
                        allow_dirty=allow_dirty,
                    )
                    if rollback_point is not None:
                        console.print(
                            "Wrote rollback point to "
                            f"[bold green]{output_dir / 'latest-rollback-point.md'}[/bold green]"
                        )
                    run_result = run_self_evolution_codex(
                        plan,
                        output_dir=output_dir,
                        model=model,
                        profile=profile,
                        sandbox=sandbox,
                        approval_policy=approval_policy,
                        ignore_user_config=ignore_user_config,
                        bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
                        timeout_seconds=codex_timeout_seconds,
                    )
                    console.print(
                        f"Codex kernel exited with {run_result.returncode}; last message: "
                        f"[bold green]{run_result.last_message_path}[/bold green]"
                    )
        if interval_seconds <= 0:
            break
        time.sleep(interval_seconds)


if __name__ == "__main__":
    app()
