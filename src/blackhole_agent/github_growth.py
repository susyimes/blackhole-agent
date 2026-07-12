"""Hourly GitHub trend intake for a rollback-backed blackhole-agent growth loop.

This controller is adapted from the mini-swe-agent `github_growth` runner. The
important change is the local mutation engine: blackhole-agent can hand a bounded
self-improvement task to the local Codex CLI kernel, write rollback artifacts,
and apply local evolution on a prepared branch.
"""

import hashlib
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
from blackhole_agent.kernels.grok_cli import GrokCliConfig, GrokCliKernel, GrokCliRunResult
from blackhole_agent.persona import render_persona_layer
from blackhole_agent.proposal_synthesis import (
    DEFAULT_PROPOSAL_MODE,
    PROPOSAL_MODES,
    ProposalSynthesisReview,
    build_proposal_evidence_package,
    render_proposal_synthesis_prompt,
    review_llm_proposal_response,
    stable_hash,
    validate_proposal_mode,
    write_context_budget_preflight_artifact,
    write_proposal_synthesis_artifacts,
)
from blackhole_agent.self_model import (
    DEFAULT_SELF_MODEL_PATH,
    SelfModelSnapshot,
    read_self_model_snapshot,
    write_self_model_snapshot,
)

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
    "skill",
    "skills",
    "test",
    "tool integration",
    "workflow",
)
INTERESTING_EVENT_TYPES = {
    "IssuesEvent",
    "IssueCommentEvent",
    "PullRequestEvent",
    "PullRequestReviewCommentEvent",
    "PullRequestReviewEvent",
    "PushEvent",
    "ReleaseEvent",
    "RepositoryTrend",
    "WorkflowRunEvent",
}
OFFENSIVE_BEHAVIOR_TERMS = (
    "attack",
    "attacking",
    "attacks",
    "backdoor",
    "credential stuffing",
    "ddos",
    "denial of service",
    "exfiltrate",
    "exfiltration",
    "exploit",
    "exploitation",
    "exploiting",
    "exploits",
    "keylogger",
    "malware",
    "offensive",
    "phishing",
    "privilege escalation",
    "ransomware",
    "unauthorized access",
    "weaponize",
    "weaponized",
    "weaponizing",
)
PRIVACY_SENSITIVE_TERMS = (
    "api key",
    "auth token",
    "credential",
    "credentials",
    "password",
    "personal data",
    "pii",
    "private chat",
    "private key",
    "secret",
    "secrets",
    "token",
    "tokens",
)
PRIVACY_LEAKAGE_TERMS = (
    "dump",
    "dumping",
    "dumps",
    "exfiltrate",
    "exfiltrating",
    "exfiltration",
    "expose",
    "exposes",
    "exposing",
    "leak",
    "leaking",
    "leaks",
    "log",
    "logging",
    "logs",
    "print",
    "printed",
    "printing",
    "prints",
    "publish",
    "publishes",
    "publishing",
    "share",
    "shares",
    "sharing",
    "upload",
    "uploading",
    "uploads",
)
GOVERNANCE_CONTROL_TERMS = (
    "approval",
    "approvals",
    "budget",
    "cost",
    "govern your agents",
    "governance",
    "policies",
    "policy",
    "risky actions",
    "sandboxing",
    "spend",
    "tool access",
    "tool limit",
    "tool limits",
    "tool restriction",
    "tool restrictions",
)
AGENT_HARNESS_VALIDATION_TERMS = (
    "agent harness",
    "auditability",
    "coding agent harness",
    "eval suite",
    "eval suites",
    "evaluation report",
    "evaluation reports",
    "model-agnostic",
    "replay",
    "replayable",
    "reproducible",
    "trace",
    "traces",
    "validation harness",
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
CAPABILITY_GAP_TERMS = (
    "dispatch table",
    "no handler",
    "not in local dispatch table",
    "provider",
    "search_provider",
    "tool call",
    "web_search",
)
SKILL_ROUTE_TERMS = (
    "agent skill",
    "agent skills",
    "codex skill",
    "codex skills",
    "plugin",
    "plugins",
    "skill",
    "skills",
    "tool integration",
    "tool integrations",
    "workflow gate",
    "workflow gates",
    "workflow routing",
)
DRAFT_ROLLBACK_REF = "recorded in latest-rollback-point.json when codex mode prepares the branch"
HARD_REVIEW_RISK_FLAGS = {"offensive-behavior", "privacy-leakage"}
VALIDATION_REPORT_REQUIRED_FIELDS = [
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
COMPLETED_VALIDATION_OUTCOME_RESULTS = {"adopted", "pass", "passed", "reviewed"}
VALIDATION_REPORT_ADOPTION_STATES = ["draft", "incomplete", "rejected", "adoption-ready"]
REVIEW_ACTIVITY_EVENT_KINDS = {
    "PullRequestReviewCommentEvent",
    "PullRequestReviewEvent",
}
UNIT_TEST_VALIDATION_TERMS = (
    "focused test",
    "focused tests",
    "focused validation",
    "local test",
    "local tests",
    "local test lane",
    "pytest",
    "regression test",
    "regression tests",
    "snapshot test",
    "test-lane",
    "test lane",
    "test-lane probe",
    "test-lane probes",
    "unit test",
    "unit tests",
)
LOCAL_FIXTURE_VALIDATION_TERMS = (
    "local fixture",
    "local fixtures",
    "small fixture",
    "small local fixture",
    "smoke fixture",
    "smoke fixtures",
    "smoke test",
    "smoke tests",
    "validation fixture",
    "validation fixtures",
)
COVERAGE_VALIDATION_TERMS = (
    "coverage",
    "coverage validation",
    "test coverage",
)
PUSH_PATTERN_TEST_EVIDENCE_TERMS = (
    "ci",
    "coverage",
    "e2e",
    "focused test",
    "focused tests",
    "integration test",
    "integration tests",
    "pytest",
    "regression test",
    "regression tests",
    "rerun flaky",
    "smoke test",
    "smoke tests",
    "test",
    "tests",
    "unit test",
    "unit tests",
)
PUSH_PATTERN_CLUSTERS = (
    ("test-coverage", ("coverage", "e2e", "integration test", "pytest", "regression test", "smoke test", "test")),
    ("ci-guardrail", ("ci", "workflow", "security scan", "gate", "hook")),
    ("flaky-test-hardening", ("flaky", "rerun", "overflow-render")),
    ("dependency-release-guardrail", ("cooldown", "lockfile", "package-lock", "twine check", "release")),
    ("harness-runtime-reliability", ("harness", "pty", "subprocess", "daemon", "tty")),
)
BYPASS_STYLE_LABELS = {
    "bypass-ci",
    "bypass-validation",
    "ci-bypass",
    "force-merge",
    "no-verify",
    "skip-ci",
    "skip-validation",
}

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
    theme_window: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthMemory":
        return cls(
            version=int(data.get("version", 1)),
            repositories={str(repo): dict(stats) for repo, stats in dict(data.get("repositories", {})).items()},
            topics={str(topic): dict(stats) for topic, stats in dict(data.get("topics", {})).items()},
            lessons=[dict(lesson) for lesson in data.get("lessons", []) if isinstance(lesson, dict)],
            theme_window=dict(data.get("theme_window") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "repositories": dict(sorted(self.repositories.items())),
            "topics": dict(sorted(self.topics.items())),
            "lessons": self.lessons,
            "theme_window": dict(self.theme_window),
        }


@dataclass(frozen=True)
class CapabilityThemeWindow:
    """A cross-run capability focus carried into self-evolution tasks."""

    schema_version: int
    theme_id: str
    title: str
    capability_slice: str
    started_at: str
    updated_at: str
    target_passes: int
    planned_passes: int
    status: str
    proposal_ids: list[str]
    evidence_urls: list[str]
    previous_theme_id: str = ""


DEFAULT_THEME_WINDOW_TARGET_PASSES = 4

CAPABILITY_THEME_CATALOG: dict[str, dict[str, Any]] = {
    "runner-harness-control": {
        "title": "Runner and harness control plane",
        "keywords": (
            "harness",
            "runner",
            "workflow",
            "e2e",
            "workspace",
            "interrupt",
            "replay",
            "subagent",
            "tool_call",
            "tool-result",
            "policy ask",
            "approval",
            "push delivery",
        ),
        "capability_slice": (
            "Make one runner workflow legible end to end: intake, mid-flight state, recovery, replay, "
            "and report artifacts."
        ),
    },
    "provider-runtime-control": {
        "title": "Provider and runtime preflight control",
        "keywords": (
            "provider",
            "preflight",
            "config",
            "openai",
            "google",
            "claude",
            "auth",
            "permission",
            "model",
            "base url",
        ),
        "capability_slice": (
            "Turn provider and runtime configuration problems into body-free diagnostics, recovery hints, "
            "and locally replayable validation."
        ),
    },
    "skill-route-discovery": {
        "title": "Skill route discovery",
        "keywords": ("skill", "route", "discovery", "lane", "registry"),
        "capability_slice": (
            "Convert skill and route evidence into bounded local lanes that can be validated before activation."
        ),
    },
    "supervisor-activation": {
        "title": "Supervisor activation and recovery",
        "keywords": ("supervisor", "restart", "activation", "worktree", "process", "cleanup", "codex cli"),
        "capability_slice": (
            "Make supervisor wakes, candidate worktrees, promotion, push, restart, and rollback visibly recoverable."
        ),
    },
    "upstream-evidence-capability": {
        "title": "Upstream evidence to capability",
        "keywords": ("upstream", "omnigent", "release", "triage", "watchlist", "trend"),
        "capability_slice": (
            "Translate public agent-ecosystem signals into one local capability step rather than another isolated note."
        ),
    },
}

DEFAULT_CAPABILITY_THEME = {
    "title": "Controller capability slice",
    "capability_slice": (
        "Advance one coherent controller capability until it has behavior, tests, artifacts, and operator-facing docs."
    ),
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
    """A coherent task that the local Codex CLI kernel can run against this checkout."""

    generated_at: str
    repo_path: str
    branch_name: str
    self_model_path: str
    self_model_before: SelfModelSnapshot
    task: str
    proposals: list[dict[str, Any]]
    source_digest_id: str
    source_digest_generated_at: str
    capability_theme_window: dict[str, Any] = field(default_factory=dict)
    upstream_evidence_capability_step: dict[str, Any] = field(default_factory=dict)
    skill_route_discovery_capability_pipeline: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelfEvolutionRunResult:
    """Result of invoking the Codex CLI kernel on a self-evolution task."""

    command: list[str]
    returncode: int
    task_path: Path
    last_message_path: Path
    result_path: Path
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
    memory.theme_window = build_capability_theme_window(
        digest.get("proposals", []),
        previous_window=memory.theme_window,
        generated_at=generated_at,
    )
    if memory.theme_window:
        digest["capability_theme_window"] = dict(memory.theme_window)
    attach_upstream_evidence_capability_step(digest)
    attach_skill_route_discovery_capability_pipeline(digest)


def build_capability_theme_window(
    proposals: list[dict[str, Any]],
    *,
    previous_window: dict[str, Any] | None = None,
    generated_at: str = "",
    target_passes: int = DEFAULT_THEME_WINDOW_TARGET_PASSES,
) -> dict[str, Any]:
    """Return the active cross-run capability theme for this planning pass."""

    proposal_ids = bounded_unique_strings(proposal.get("proposal_id") for proposal in proposals)
    evidence_urls = bounded_unique_strings(
        url for proposal in proposals for url in proposal.get("evidence_urls", []) if str(url).strip()
    )
    now = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    previous = previous_window or {}
    previous_status = str(previous.get("status") or "")
    previous_theme_id = str(previous.get("theme_id") or "")
    previous_target = int(previous.get("target_passes") or target_passes)
    previous_passes = int(previous.get("planned_passes") or 0)

    if previous_theme_id and previous_status == "active" and previous_passes < previous_target:
        catalog_entry = CAPABILITY_THEME_CATALOG.get(previous_theme_id, DEFAULT_CAPABILITY_THEME)
        title = str(previous.get("title") or catalog_entry["title"])
        capability_slice = str(previous.get("capability_slice") or catalog_entry["capability_slice"])
        merged_proposal_ids = bounded_unique_strings([*previous.get("proposal_ids", []), *proposal_ids])
        merged_evidence_urls = bounded_unique_strings([*previous.get("evidence_urls", []), *evidence_urls])
        return asdict(
            CapabilityThemeWindow(
                schema_version=1,
                theme_id=previous_theme_id,
                title=title,
                capability_slice=capability_slice,
                started_at=str(previous.get("started_at") or now),
                updated_at=now,
                target_passes=previous_target,
                planned_passes=previous_passes + 1,
                status="active" if previous_passes + 1 < previous_target else "complete",
                proposal_ids=merged_proposal_ids,
                evidence_urls=merged_evidence_urls,
                previous_theme_id=str(previous.get("previous_theme_id") or ""),
            )
        )

    theme_id = classify_capability_theme(proposals)
    catalog_entry = CAPABILITY_THEME_CATALOG.get(theme_id, DEFAULT_CAPABILITY_THEME)
    return asdict(
        CapabilityThemeWindow(
            schema_version=1,
            theme_id=theme_id,
            title=str(catalog_entry["title"]),
            capability_slice=str(catalog_entry["capability_slice"]),
            started_at=now,
            updated_at=now,
            target_passes=target_passes,
            planned_passes=1,
            status="active" if target_passes > 1 else "complete",
            proposal_ids=proposal_ids,
            evidence_urls=evidence_urls,
            previous_theme_id=previous_theme_id,
        )
    )


def classify_capability_theme(proposals: list[dict[str, Any]]) -> str:
    """Classify proposals into a durable capability theme without calling an LLM."""

    text = " ".join(
        " ".join(
            [
                str(proposal.get("proposal_id") or ""),
                str(proposal.get("kind") or ""),
                str(proposal.get("summary") or ""),
                str(proposal.get("implementation_scope") or ""),
                str(proposal.get("validation_gate") or ""),
                str(proposal.get("validation_task") or ""),
            ]
        ).lower()
        for proposal in proposals
    )
    scores: dict[str, int] = {}
    for theme_id, config in CAPABILITY_THEME_CATALOG.items():
        scores[theme_id] = sum(1 for keyword in config["keywords"] if keyword in text)
    best_theme_id, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return "controller-capability-slice"
    return best_theme_id


def bounded_unique_strings(values: Any, *, limit: int = 12) -> list[str]:
    """Return stable, bounded strings for replay artifacts."""

    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        unique.append(text)
        seen.add(text)
        if len(unique) >= limit:
            break
    return unique


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
    flags: set[str] = set()
    if any(contains_risk_term(haystack, term) for term in OFFENSIVE_BEHAVIOR_TERMS):
        flags.add("offensive-behavior")
    if contains_privacy_leakage_signal(haystack):
        flags.add("privacy-leakage")
    return sorted(flags)


def contains_risk_term(haystack: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", haystack) is not None


def is_capability_gap_signal(haystack: str) -> bool:
    if "not in local dispatch table" in haystack:
        return True
    matched_terms = [term for term in CAPABILITY_GAP_TERMS if contains_risk_term(haystack, term)]
    return "web_search" in matched_terms and bool({"dispatch table", "no handler", "provider"} & set(matched_terms))


def contains_privacy_leakage_signal(haystack: str) -> bool:
    has_sensitive_subject = any(contains_risk_term(haystack, term) for term in PRIVACY_SENSITIVE_TERMS)
    has_leakage_action = any(contains_risk_term(haystack, term) for term in PRIVACY_LEAKAGE_TERMS)
    return has_sensitive_subject and has_leakage_action


def recommend_action(event: GitHubEvent, risk_flags: list[str]) -> str:
    if "offensive-behavior" in risk_flags:
        return "record the offensive-behavior boundary and keep the route review-only"
    if "privacy-leakage" in risk_flags:
        return "record the privacy-leakage boundary and keep sensitive data out of artifacts and runtime changes"
    if risk_flags:
        return "summarize the risk pattern and keep the route reviewable"
    if any(contains_risk_term(f"{event.kind} {event.title} {event.summary}".lower(), term) for term in GOVERNANCE_CONTROL_TERMS):
        return "adapt the governance pattern freely when it improves local controller behavior without offensive use or privacy leakage"
    if is_capability_gap_signal(f"{event.kind} {event.title} {event.summary}".lower()):
        return "adapt the capability route freely when local validation can cover it"
    if any(
        contains_risk_term(f"{event.kind} {event.title} {event.summary}".lower(), term)
        for term in SKILL_ROUTE_TERMS
    ):
        return "map skill, workflow, or tool-integration signals to bounded local validation lanes such as documentation, config, tests, or code patches"
    if any(contains_risk_term(f"{event.kind} {event.title} {event.summary}".lower(), term) for term in REMOTE_EXECUTION_TERMS):
        return "adapt the runner or remote-execution pattern freely when configured capabilities and validation support it"
    if any(contains_risk_term(f"{event.kind} {event.title} {event.summary}".lower(), term) for term in AGENT_HARNESS_VALIDATION_TERMS):
        return "adapt the harness pattern into local behavior, tests, or reports without treating validation as the only outcome"
    if event.kind == "RepositoryTrend":
        return "review the repository for reusable patterns and turn only one concrete lesson into a validation task"
    if event.kind == "ReleaseEvent":
        return "review release notes for reusable implementation or workflow changes"
    if event.kind == "PullRequestEvent":
        return "compare the pull request approach with local agent behavior before drafting a change"
    if event.kind in REVIEW_ACTIVITY_EVENT_KINDS:
        return "treat repeated pull request review activity as supporting evidence for local validation or test changes"
    if event.kind == "PushEvent":
        return "cluster commit messages and keep only patterns with clear test evidence"
    if event.kind in {"IssuesEvent", "IssueCommentEvent"}:
        return "turn the issue signal into a focused hypothesis and validation checklist"
    return "capture the lesson as a proposal; do not mutate the project automatically"


def build_digest(
    repos: list[str],
    signals: list[GrowthSignal],
    *,
    state: GrowthState,
    generated_at: str | None = None,
    source: dict[str, Any] | None = None,
    memory: GrowthMemory | None = None,
    proposals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    digest_id = "github-growth-" + generated_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
    digest_proposals = build_proposals(signals, memory=memory) if proposals is None else proposals
    items = [
        {
            "item_id": signal.event_id,
            "source_url": signal.url,
            "event_kind": signal.kind,
            "summary": f"{signal.repo}: {signal.title}",
            "relevance_reason": signal.relevance_reason,
            "risk_flags": signal.risk_flags,
            "confidence": signal.confidence,
        }
        for signal in signals
    ]
    digest = {
        "digest_id": digest_id,
        "generated_at": generated_at,
        "repositories": repos,
        "cursor": dict(sorted(state.last_seen_at_by_repo.items())),
        "items": items,
        "proposals": digest_proposals,
    }
    upstream_triage = build_upstream_movement_triage(items)
    if upstream_triage["clusters"]:
        digest["upstream_movement_triage"] = upstream_triage
    if source is not None:
        digest["source"] = source
    attach_upstream_evidence_capability_step(digest)
    attach_skill_route_discovery_capability_pipeline(digest)
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
        proposal = {
            "proposal_id": f"{signal.event_id}-{index}",
            "proposal_source": "heuristic",
            "kind": classify_proposal_kind(signal),
            "summary": f"Borrow cautiously from {signal.repo}: {signal.title}. {signal.recommended_action}.",
            "evidence_urls": [signal.url] if signal.url else [],
            "risk_flags": signal.risk_flags,
            "implementation_scope": implementation_scope_for_signal(signal),
            "validation_gate": validation_gate_for_signal(signal),
            "validation_task": validation_task_for_signal(signal),
            "requires_approval": False,
        }
        pattern_evidence = push_pattern_evidence_for_signal(signal)
        if pattern_evidence is not None:
            proposal["push_pattern_evidence"] = pattern_evidence
        upstream_evidence = upstream_movement_evidence_for_signal(signal)
        if upstream_evidence is not None:
            proposal["upstream_movement_evidence"] = upstream_evidence
        proposals.append(proposal)
    return proposals


def synthesize_digest_proposals(
    digest: dict[str, Any],
    signals: list[GrowthSignal],
    heuristic_proposals: list[dict[str, Any]],
    *,
    mode: str,
    output_dir: Path,
    repo_path: Path,
    self_model_path: Path | None = None,
    model: str | None = None,
    profile: str | None = None,
    kernel: str = "codex",
    ignore_user_config: bool = True,
    timeout_seconds: int = 180,
    command_runner: Any = subprocess.run,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Optionally ask a read-only LLM to interpret digest items before proposals are finalized."""

    normalized_mode = validate_proposal_mode(mode)
    if normalized_mode == "heuristic":
        return heuristic_proposals

    self_model_snapshot = read_self_model_snapshot(repo_path, self_model_path)
    evidence_package = build_proposal_evidence_package(
        digest,
        self_model_snapshot=self_model_snapshot.to_dict(),
        max_items=max(20, limit * 4),
    )
    write_context_budget_preflight_artifact(output_dir, evidence_package=evidence_package)
    try:
        raw_text = run_proposal_interpretation_kernel(
            evidence_package,
            output_dir=output_dir,
            repo_path=repo_path,
            model=model,
            profile=profile,
            kernel=kernel,
            ignore_user_config=ignore_user_config,
            timeout_seconds=timeout_seconds,
            command_runner=command_runner,
        )
        review = review_llm_proposal_response(raw_text, evidence_package, mode=normalized_mode)
    except Exception as error:
        review = ProposalSynthesisReview(
            schema_version=1,
            mode=normalized_mode,
            status="rejected",
            reason=f"proposal interpretation failed: {error}",
            input_digest_id=str(evidence_package.get("digest_id") or ""),
            input_hash=stable_hash(evidence_package),
            output_hash="",
            accepted_count=0,
            rejected_count=0,
            accepted_candidates=[],
            rejected_candidates=[],
            interpretation={},
            self_model_reading={},
        )
    write_proposal_synthesis_artifacts(output_dir, evidence_package=evidence_package, review=review)
    if review.status != "accepted":
        return heuristic_proposals

    llm_proposals = clamp_llm_candidates_to_proposals(review.accepted_candidates, signals, limit=limit)
    if not llm_proposals:
        return heuristic_proposals
    if normalized_mode == "llm":
        return llm_proposals
    return combine_llm_and_heuristic_proposals(llm_proposals, heuristic_proposals, limit=limit)


def run_proposal_interpretation_kernel(
    evidence_package: dict[str, Any],
    *,
    output_dir: Path,
    repo_path: Path,
    model: str | None = None,
    profile: str | None = None,
    kernel: str = "codex",
    ignore_user_config: bool = True,
    timeout_seconds: int = 180,
    command_runner: Any = subprocess.run,
) -> str:
    """Run the selected CLI as a read-only interpretation kernel."""

    if kernel == "grok":
        grok = GrokCliKernel(
            GrokCliConfig(
                model=model,
                sandbox="read-only",
                permission_mode="dontAsk",
            ),
            command_runner=command_runner,
        )
        result = grok.run(
            render_proposal_synthesis_prompt(evidence_package),
            cwd=repo_path,
            output_dir=output_dir / "proposal-synthesis",
            timeout_seconds=timeout_seconds,
        )
        return result.last_message
    if kernel != "codex":
        raise ValueError("kernel must be one of: codex, grok")

    config = CodexCliConfig(
        model=model,
        profile=profile,
        sandbox="read-only",
        approval_policy="never",
        ignore_user_config=ignore_user_config,
        bypass_approvals_and_sandbox=False,
    )
    codex = CodexCliKernel(config, command_runner=command_runner)
    result = codex.run(
        render_proposal_synthesis_prompt(evidence_package),
        cwd=repo_path,
        output_dir=output_dir / "proposal-synthesis",
        timeout_seconds=timeout_seconds,
    )
    return result.last_message


def clamp_llm_candidates_to_proposals(
    candidates: list[dict[str, Any]],
    signals: list[GrowthSignal],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    signals_by_id = {signal.event_id: signal for signal in signals}
    proposals: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates[:limit], start=1):
        referenced = [signals_by_id[ref] for ref in candidate.get("evidence_refs", []) if ref in signals_by_id]
        if not referenced:
            continue
        risk_flags = sorted(
            {
                *[flag for signal in referenced for flag in signal.risk_flags],
                *[
                    normalized_flag
                    for flag in candidate.get("added_risk_flags", [])
                    if (normalized_flag := str(flag).strip()) in HARD_REVIEW_RISK_FLAGS
                ],
                *detect_risk_flags(candidate_safety_text(candidate)),
            }
        )
        representative = GrowthSignal(
            event_id=str(candidate.get("proposal_id") or f"llm-{index}"),
            repo=referenced[0].repo,
            kind=referenced[0].kind,
            title=str(candidate.get("summary") or referenced[0].title),
            url=referenced[0].url,
            relevance_reason="LLM interpretation over frozen digest evidence",
            risk_flags=risk_flags,
            recommended_action=str(candidate.get("validation_task") or "validate the interpreted route locally"),
            confidence=min(max(float(referenced[0].confidence), 0.0), 1.0),
        )
        kind = classify_proposal_kind(representative) if risk_flags else str(candidate.get("kind") or "test")
        validation_task = (
            validation_task_for_signal(representative, route=candidate)
            if risk_flags
            else str(candidate.get("validation_task") or validation_task_for_signal(representative))
        )
        proposal = {
            "proposal_id": str(candidate.get("proposal_id") or f"llm-{index}"),
            "proposal_source": "llm_interpretation",
            "kind": kind,
            "summary": str(candidate.get("summary") or representative.title),
            "evidence_refs": [str(ref) for ref in candidate.get("evidence_refs", [])],
            "evidence_urls": candidate.get("evidence_urls") or [signal.url for signal in referenced if signal.url],
            "risk_flags": risk_flags,
            "implementation_scope": implementation_scope_for_signal(representative, route=candidate),
            "validation_gate": validation_gate_for_signal(representative, route=candidate),
            "validation_task": validation_task,
            "requires_approval": False,
            "rationale": str(candidate.get("rationale") or ""),
            "uncertainty": str(candidate.get("uncertainty") or ""),
            "self_effect": str(candidate.get("self_effect") or ""),
            "action_lane": str(candidate.get("action_lane") or ""),
        }
        pattern_evidence = push_pattern_evidence_for_signals(referenced)
        if pattern_evidence is not None:
            proposal["push_pattern_evidence"] = pattern_evidence
        proposals.append(proposal)
    return proposals


def push_pattern_evidence_for_signals(signals: list[GrowthSignal]) -> dict[str, Any] | None:
    """Merge push-pattern evidence from cited signals for interpreted proposals."""

    evidences = [
        evidence
        for signal in signals
        if (evidence := push_pattern_evidence_for_signal(signal)) is not None
    ]
    if not evidences:
        return None
    clusters = sorted(
        {
            str(cluster)
            for evidence in evidences
            for cluster in evidence.get("clusters", [])
            if str(cluster).strip()
        }
    )
    has_clear_test_evidence = all(bool(evidence.get("has_clear_test_evidence")) for evidence in evidences)
    matched_text_hash = stable_push_message_hash(
        json.dumps([evidence.get("matched_text_hash", "") for evidence in evidences], sort_keys=True)
    )
    return {
        "status": "ready" if clusters and has_clear_test_evidence else "evidence_gap",
        "clusters": clusters,
        "has_clear_test_evidence": has_clear_test_evidence,
        "source": "push_commit_message_cluster",
        "policy": "keep_push_patterns_only_when_commit_messages_include_clear_test_or_ci_evidence",
        "matched_text_hash": matched_text_hash,
    }


def candidate_safety_text(candidate: dict[str, Any]) -> str:
    """Return LLM-authored proposal text that can independently trigger safety review."""

    return " ".join(
        str(candidate.get(key) or "")
        for key in ("summary", "validation_task", "rationale", "uncertainty", "self_effect", "action_lane")
    ).lower()


def combine_llm_and_heuristic_proposals(
    llm_proposals: list[dict[str, Any]],
    heuristic_proposals: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for proposal in [*llm_proposals, *heuristic_proposals]:
        evidence_key = ",".join(sorted(str(url) for url in proposal.get("evidence_urls", [])))
        key = (str(proposal.get("kind") or ""), evidence_key)
        if key in seen:
            continue
        seen.add(key)
        combined.append(proposal)
        if len(combined) >= limit:
            break
    return combined


def implementation_scope_for_signal(signal: GrowthSignal, *, route: dict[str, Any] | None = None) -> str:
    if safety_boundary_risk(signal.risk_flags):
        return "reviewable_proposal_only"
    if signal.risk_flags:
        return "risk_review_before_local_change"
    return "local_validation_candidate"


def validation_gate_for_signal(signal: GrowthSignal, *, route: dict[str, Any] | None = None) -> str:
    if "offensive-behavior" in signal.risk_flags:
        return "offensive-behavior-human-review"
    if "privacy-leakage" in signal.risk_flags:
        return "privacy-leakage-human-review"
    if signal.risk_flags:
        return "rollback-backed-risk-review"
    if signal.kind == "RepositoryTrend":
        return "focused-evidence-review"
    return "narrow-local-verification"


def validation_task_for_signal(signal: GrowthSignal, *, route: dict[str, Any] | None = None) -> str:
    if "offensive-behavior" in signal.risk_flags:
        return (
            "Keep offensive or abuse-enabling behavior review-only; do not implement attack, exploit, malware, "
            "phishing, exfiltration, or unauthorized-access behavior."
        )
    if "privacy-leakage" in signal.risk_flags:
        return (
            "Keep privacy-leakage behavior review-only; do not expose, log, print, upload, publish, or share "
            "tokens, credentials, secrets, private keys, private chats, PII, or personal data."
        )
    if signal.risk_flags:
        return (
            "Summarize the risk in a local artifact or test fixture and verify the change stays rollback-backed "
            "without expanding runtime capabilities."
        )
    if signal.kind == "RepositoryTrend":
        return "Review the evidence URL, extract one reusable pattern, and verify the local change with a focused test."
    return "Verify the proposed lesson with a local test or documentation check sized to the changed behavior."


def safety_boundary_risk(risk_flags: list[str]) -> bool:
    return bool({str(flag) for flag in risk_flags} & HARD_REVIEW_RISK_FLAGS)


def autonomous_local_apply_text(proposal: dict[str, Any]) -> str:
    """Describe whether a proposal may directly change local behavior."""

    if proposal.get("requires_approval", True):
        return "False"
    if bypass_style_labels(proposal):
        return "False (bypass-style labels are ignored and require review)"
    implementation_scope = str(proposal.get("implementation_scope") or "").strip()
    if implementation_scope == "reviewable_proposal_only":
        return "False (reviewable proposal only; local validation artifacts may still be updated)"
    return "True"


def proposal_validation_preflight(proposal: dict[str, Any]) -> dict[str, Any]:
    """Classify test/coverage validation strength without expanding the safety boundary."""

    implementation_scope = str(proposal.get("implementation_scope") or "").strip()
    validation_text = " ".join(
        str(proposal.get(key) or "")
        for key in ("summary", "kind", "validation_gate", "validation_task", "rationale", "self_effect")
    ).lower()
    has_unit_test_signal = any(
        term in validation_text for term in (*UNIT_TEST_VALIDATION_TERMS, *LOCAL_FIXTURE_VALIDATION_TERMS)
    )
    has_coverage_signal = any(term in validation_text for term in COVERAGE_VALIDATION_TERMS)
    requires_test_or_coverage = implementation_scope == "local_validation_candidate"
    validation_gaps: list[str] = []
    if requires_test_or_coverage and not (has_unit_test_signal or has_coverage_signal):
        validation_gaps.append("missing_unit_test_or_coverage_validation")
    push_pattern_evidence = proposal.get("push_pattern_evidence")
    if (
        requires_test_or_coverage
        and isinstance(push_pattern_evidence, dict)
        and not push_pattern_evidence.get("has_clear_test_evidence")
    ):
        validation_gaps.append("missing_push_pattern_test_evidence")
    upstream_movement_evidence = proposal.get("upstream_movement_evidence")
    if (
        requires_test_or_coverage
        and isinstance(upstream_movement_evidence, dict)
        and upstream_movement_evidence.get("status") != "ready"
    ):
        validation_gaps.append("missing_upstream_movement_confirmation")

    safety_block = safety_boundary_risk([str(flag) for flag in proposal.get("risk_flags", [])])
    status = "blocked_by_safety_boundary" if safety_block else "validation_gap" if validation_gaps else "ready"
    return {
        "status": status,
        "requires_unit_test_or_coverage": requires_test_or_coverage,
        "has_unit_test_signal": has_unit_test_signal,
        "has_coverage_signal": has_coverage_signal,
        "validation_gaps": validation_gaps,
        "safety_block": safety_block,
        "blocks_autonomous_apply": safety_block,
    }


def proposal_manifest_control(proposal: dict[str, Any]) -> dict[str, Any]:
    """Return replayable safety metadata for a self-evolution proposal."""

    validation_preflight = proposal_validation_preflight(proposal)
    control = {
        "proposal_id": str(proposal.get("proposal_id") or ""),
        "kind": str(proposal.get("kind") or ""),
        "implementation_scope": str(proposal.get("implementation_scope") or ""),
        "validation_gate": str(proposal.get("validation_gate") or ""),
        "autonomous_local_apply": autonomous_local_apply_text(proposal),
        "validation_preflight": validation_preflight,
        "review_metadata": proposal_review_metadata(proposal, validation_preflight),
    }
    proposal_risk_flags = {str(flag) for flag in proposal.get("risk_flags", [])}
    if proposal_risk_flags & HARD_REVIEW_RISK_FLAGS:
        control["safety_boundary_requirement"] = (
            "Only offensive behavior, abuse, unauthorized access, or privacy leakage is review-only; "
            "all other rollback-backed local changes may proceed."
        )
    return control


def proposal_review_metadata(proposal: dict[str, Any], validation_preflight: dict[str, Any]) -> dict[str, Any]:
    """Return local reviewer-routing and bypass metadata for controller manifests."""

    labels = bypass_style_labels(proposal)
    return {
        "reviewer_routes": proposal_reviewer_routes(proposal, validation_preflight),
        "coverage_drop_signal": coverage_drop_signal(proposal, validation_preflight),
        "bypass_label_guard": {
            "status": "blocked" if labels else "passed",
            "blocked_labels": labels,
            "policy": "bypass-style labels are metadata only and cannot grant autonomous local apply",
        },
    }


def proposal_reviewer_routes(proposal: dict[str, Any], validation_preflight: dict[str, Any]) -> list[str]:
    """Infer stable local review routes from controller-owned proposal metadata."""

    routes: list[str] = []
    risk_flags = {str(flag) for flag in proposal.get("risk_flags", [])}
    kind = str(proposal.get("kind") or "")
    validation_gate = str(proposal.get("validation_gate") or "")
    if risk_flags & HARD_REVIEW_RISK_FLAGS or validation_gate.endswith("-human-review"):
        routes.append("safety-boundary-review")
    if kind in {"code_patch", "config"}:
        routes.append("runtime-change-review")
    if validation_preflight.get("requires_unit_test_or_coverage"):
        routes.append("validation-maintainer-review")
    if validation_preflight.get("has_coverage_signal"):
        routes.append("coverage-review")
    if not routes:
        routes.append("general-maintainer-review")
    return sorted(dict.fromkeys(routes))


def coverage_drop_signal(proposal: dict[str, Any], validation_preflight: dict[str, Any]) -> dict[str, Any]:
    """Expose when coverage-related local candidates should turn red on drops."""

    applies = (
        str(proposal.get("implementation_scope") or "") == "local_validation_candidate"
        and bool(validation_preflight.get("has_coverage_signal"))
    )
    return {
        "applies": applies,
        "status_on_drop": "red-non-blocking" if applies else "not-applicable",
        "blocking": False,
    }


def bypass_style_labels(proposal: dict[str, Any]) -> list[str]:
    """Return bypass-like labels that must not influence autonomous apply."""

    raw_labels: list[Any] = []
    for key in ("labels", "github_labels", "apply_labels"):
        value = proposal.get(key)
        if isinstance(value, list):
            raw_labels.extend(value)
    labels = {str(label).strip().lower() for label in raw_labels if str(label).strip()}
    return sorted(labels & BYPASS_STYLE_LABELS)


def build_replayable_validation_report(plan: SelfEvolutionPlan, proposal_controls: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the report contract used to replay evidence review before behavior changes."""

    evidence_urls = sorted(
        {
            str(url)
            for proposal in plan.proposals
            for url in proposal.get("evidence_urls", [])
            if str(url).strip()
        }
    )
    validation_gates = sorted(
        {
            str(proposal.get("validation_gate"))
            for proposal in plan.proposals
            if str(proposal.get("validation_gate") or "").strip()
        }
    )
    proposal_ids = [
        str(proposal.get("proposal_id"))
        for proposal in plan.proposals
        if str(proposal.get("proposal_id") or "").strip()
    ]
    review_metadata = [dict(control.get("review_metadata") or {}) for control in proposal_controls]
    report = {
        "schema_version": 1,
        "source_digest_id": plan.source_digest_id,
        "template_version": 4,
        "required_fields": VALIDATION_REPORT_REQUIRED_FIELDS,
        "evidence_urls": evidence_urls,
        "validation_gates": validation_gates,
        "proposal_controls": proposal_controls,
        "reviewer_routes": sorted(
            {
                str(route)
                for metadata in review_metadata
                for route in metadata.get("reviewer_routes", [])
                if str(route).strip()
            }
        ),
        "coverage_drop_signals": [
            {
                "proposal_id": str(control.get("proposal_id") or ""),
                **dict((control.get("review_metadata") or {}).get("coverage_drop_signal") or {}),
            }
            for control in proposal_controls
        ],
        "bypass_label_guard": {
            "status": "blocked"
            if any(
                (metadata.get("bypass_label_guard") or {}).get("status") == "blocked"
                for metadata in review_metadata
            )
            else "passed",
            "blocked_labels": sorted(
                {
                    str(label)
                    for metadata in review_metadata
                    for label in (metadata.get("bypass_label_guard") or {}).get("blocked_labels", [])
                    if str(label).strip()
                }
            ),
            "policy": "bypass-style labels are metadata only and cannot grant autonomous local apply",
        },
        "pre_adoption_risk_review": {
            "hypothesis": "",
            "expected_local_benefit": "",
            "safety_questions": [
                "What behavior would change if this lesson were adopted?",
                "Which local tests or artifacts prove the lesson before behavior changes?",
                "Which import or startup command proves the adopted behavior does not break activation?",
                "Which runtime capabilities, if any, would be required but are intentionally skipped?",
            ],
            "decision": "pending",
        },
        "provenance": {
            "source_digest_id": plan.source_digest_id,
            "proposal_ids": proposal_ids,
            "evidence_urls": evidence_urls,
            "validation_gates": validation_gates,
            "capability_theme_id": str(plan.capability_theme_window.get("theme_id") or ""),
            "rollback_ref": DRAFT_ROLLBACK_REF,
        },
        "local_commands": [
            {
                "command": "",
                "purpose": "",
                "cwd": plan.repo_path,
                "exit_code": None,
            }
        ],
        "startup_health_checks": [
            {
                "command": "",
                "purpose": "prove imports and startup paths touched by the candidate still load",
                "cwd": plan.repo_path,
                "exit_code": None,
            }
        ],
        "outcomes": [
            {
                "check": "",
                "result": "pending",
                "evidence_artifact": "",
            }
        ],
        "rollback_ref": DRAFT_ROLLBACK_REF,
        "skipped_capabilities": ["none recorded"],
        "runtime_capability_changes": [],
        "runtime_capability_change_policy": (
            "Record material capability changes here when a local adoption changes harnesses, runner or remote "
            "execution behavior, provider/config preflight, restart paths, push or promotion behavior, scheduling, "
            "memory, or tool routing. Capability changes are allowed when rollback-backed, locally validated, and "
            "outside the offensive-behavior and privacy-leakage safety boundary."
        ),
        "completion_requirements": [
            "evidence_urls must contain every external evidence URL used to justify the lesson.",
            "pre_adoption_risk_review.decision must be filled before any behavior adoption.",
            "local_commands and startup_health_checks must list command, purpose, cwd, and exit_code for each check run.",
            "outcomes must name the checked behavior, a passing or reviewed result, and evidence artifact.",
            "rollback_ref must name the concrete local rollback ref or rollback artifact for the run.",
            "provenance.rollback_ref must match rollback_ref so replay metadata points at the same recovery anchor.",
            "skipped_capabilities must list unavailable or intentionally skipped runtime capabilities, or 'none recorded'.",
            "runtime_capability_changes must list material capability changes that were adopted, or stay empty when none changed.",
            "completion_status.is_complete must stay false while placeholders, pending decisions, or the draft rollback ref remain.",
            "adoption_decision.status must be adopted, rejected, or deferred with rationale and decided_at before this report is complete.",
            "uncertainty must record stale, unavailable, or weak evidence instead of being silently omitted.",
        ],
        "adoption_decision": {
            "status": "pending",
            "allowed_statuses": ["pending", "adopted", "rejected", "deferred"],
            "rationale": "",
            "decided_at": "",
        },
        "uncertainty": [
            "Post-run validation commands are executed outside this manifest writer and must be recorded by run notes or supervisor artifacts.",
        ],
    }
    report["completion_status"] = validation_report_completion_status(report)
    return report


def validation_report_completion_status(report: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a replayable validation report is adoption-ready controller evidence."""

    blocking_reasons: list[str] = []
    if report.get("required_fields") != VALIDATION_REPORT_REQUIRED_FIELDS:
        blocking_reasons.append("required_fields does not match the validation report contract")
    blocking_reasons.extend(nonblank_list_reasons(report.get("evidence_urls"), "evidence_urls"))

    raw_risk_review = report.get("pre_adoption_risk_review")
    risk_review = raw_risk_review if isinstance(raw_risk_review, dict) else {}
    for key in ("hypothesis", "expected_local_benefit"):
        if not str(risk_review.get(key) or "").strip():
            blocking_reasons.append(f"pre_adoption_risk_review.{key} is blank")
    risk_review_decision = str(risk_review.get("decision") or "").strip().lower()
    if risk_review_decision in {"", "pending"}:
        blocking_reasons.append("pre_adoption_risk_review.decision is pending")

    blocking_reasons.extend(incomplete_command_reasons(report.get("local_commands"), "local_commands"))
    blocking_reasons.extend(incomplete_command_reasons(report.get("startup_health_checks"), "startup_health_checks"))
    blocking_reasons.extend(incomplete_outcome_reasons(report.get("outcomes")))

    rollback_ref = str(report.get("rollback_ref") or "").strip()
    if not rollback_ref or rollback_ref == DRAFT_ROLLBACK_REF:
        blocking_reasons.append("rollback_ref does not name a concrete rollback ref or artifact")
    blocking_reasons.extend(incomplete_provenance_reasons(report.get("provenance"), rollback_ref, report.get("evidence_urls")))
    blocking_reasons.extend(nonblank_list_reasons(report.get("skipped_capabilities"), "skipped_capabilities"))
    blocking_reasons.extend(runtime_capability_change_reasons(report.get("runtime_capability_changes")))
    blocking_reasons.extend(nonblank_list_reasons(report.get("completion_requirements"), "completion_requirements"))
    if "uncertainty" not in report:
        blocking_reasons.append("uncertainty is missing")

    raw_adoption_decision = report.get("adoption_decision")
    adoption_decision = raw_adoption_decision if isinstance(raw_adoption_decision, dict) else {}
    adoption_status = str(adoption_decision.get("status") or "").strip().lower()
    if adoption_status in {"", "pending"}:
        blocking_reasons.append("adoption_decision.status is pending")
    elif adoption_status not in {"adopted", "rejected", "deferred"}:
        blocking_reasons.append("adoption_decision.status is not an allowed final status")
    blocking_reasons.extend(risk_review_decision_conflict_reasons(risk_review_decision, adoption_status))
    for key in ("rationale", "decided_at"):
        if not str(adoption_decision.get(key) or "").strip():
            blocking_reasons.append(f"adoption_decision.{key} is blank")

    is_complete = not blocking_reasons
    adoption_state = validation_report_adoption_state(
        report,
        blocking_reasons=blocking_reasons,
        adoption_status=adoption_status,
    )
    if not is_complete:
        status = "draft_template"
    elif adoption_status == "adopted":
        status = "completed_adoption_evidence"
    else:
        status = "completed_review_evidence"
    return {
        "status": status,
        "adoption_state": adoption_state,
        "allowed_adoption_states": VALIDATION_REPORT_ADOPTION_STATES,
        "is_complete": is_complete,
        "adoption_evidence_complete": is_complete and adoption_status == "adopted",
        "capability_changes_allowed": True,
        "runtime_capability_changes_recorded": bool(report.get("runtime_capability_changes")),
        "blocking_reasons": blocking_reasons,
    }


def validation_report_adoption_state(
    report: dict[str, Any],
    *,
    blocking_reasons: list[str],
    adoption_status: str,
) -> str:
    """Return the controller-facing state for rollback-backed local adoption evidence."""

    if not blocking_reasons:
        return "adoption-ready" if adoption_status == "adopted" else "rejected"
    if validation_report_has_completion_attempt(report, adoption_status=adoption_status):
        return "incomplete"
    return "draft"


def validation_report_has_completion_attempt(report: dict[str, Any], *, adoption_status: str) -> bool:
    raw_risk_review = report.get("pre_adoption_risk_review")
    risk_review = raw_risk_review if isinstance(raw_risk_review, dict) else {}
    if any(str(risk_review.get(key) or "").strip() for key in ("hypothesis", "expected_local_benefit")):
        return True
    if str(risk_review.get("decision") or "").strip().lower() not in {"", "pending"}:
        return True
    if command_list_has_completion_attempt(report.get("local_commands")):
        return True
    if command_list_has_completion_attempt(report.get("startup_health_checks")):
        return True
    if outcome_list_has_completion_attempt(report.get("outcomes")):
        return True
    rollback_ref = str(report.get("rollback_ref") or "").strip()
    if rollback_ref and rollback_ref != DRAFT_ROLLBACK_REF:
        return True
    if adoption_status not in {"", "pending"}:
        return True
    raw_adoption_decision = report.get("adoption_decision")
    adoption_decision = raw_adoption_decision if isinstance(raw_adoption_decision, dict) else {}
    return any(str(adoption_decision.get(key) or "").strip() for key in ("rationale", "decided_at"))


def risk_review_decision_conflict_reasons(risk_review_decision: str, adoption_status: str) -> list[str]:
    if adoption_status not in {"adopted", "rejected", "deferred"}:
        return []
    if "reject" in risk_review_decision and adoption_status != "rejected":
        return ["pre_adoption_risk_review.decision conflicts with adoption_decision.status"]
    if "defer" in risk_review_decision and adoption_status != "deferred":
        return ["pre_adoption_risk_review.decision conflicts with adoption_decision.status"]
    if (
        ("accept" in risk_review_decision or "adopt" in risk_review_decision)
        and "reject" not in risk_review_decision
        and "defer" not in risk_review_decision
        and adoption_status != "adopted"
    ):
        return ["pre_adoption_risk_review.decision conflicts with adoption_decision.status"]
    return []


def command_list_has_completion_attempt(commands: Any) -> bool:
    if not isinstance(commands, list):
        return False
    for command in commands:
        if not isinstance(command, dict):
            continue
        if str(command.get("command") or "").strip():
            return True
        if command.get("exit_code") is not None:
            return True
    return False


def outcome_list_has_completion_attempt(outcomes: Any) -> bool:
    if not isinstance(outcomes, list):
        return False
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        result = str(outcome.get("result") or "").strip().lower()
        if any(str(outcome.get(key) or "").strip() for key in ("check", "evidence_artifact")):
            return True
        if result not in {"", "pending"}:
            return True
    return False


def incomplete_provenance_reasons(provenance: Any, rollback_ref: str, evidence_urls: Any) -> list[str]:
    if not isinstance(provenance, dict):
        return ["provenance is missing"]
    reasons: list[str] = []
    expected_evidence_urls = sorted(str(url).strip() for url in evidence_urls if str(url).strip()) if isinstance(evidence_urls, list) else []
    provenance_evidence_urls = (
        sorted(str(url).strip() for url in provenance.get("evidence_urls") if str(url).strip())
        if isinstance(provenance.get("evidence_urls"), list)
        else []
    )
    if provenance_evidence_urls != expected_evidence_urls:
        reasons.append("provenance.evidence_urls does not match evidence_urls")
    provenance_rollback_ref = str(provenance.get("rollback_ref") or "").strip()
    if not provenance_rollback_ref or provenance_rollback_ref == DRAFT_ROLLBACK_REF:
        reasons.append("provenance.rollback_ref does not name a concrete rollback ref or artifact")
    elif rollback_ref and rollback_ref != DRAFT_ROLLBACK_REF and provenance_rollback_ref != rollback_ref:
        reasons.append("provenance.rollback_ref does not match rollback_ref")
    return reasons


def nonblank_list_reasons(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [f"{field_name} is empty"]
    reasons: list[str] = []
    for index, item in enumerate(value):
        if not str(item or "").strip():
            reasons.append(f"{field_name}[{index}] is blank")
    return reasons


def runtime_capability_change_reasons(value: Any) -> list[str]:
    if not isinstance(value, list):
        return ["runtime_capability_changes is not a list"]
    reasons: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            if not any(str(field_value or "").strip() for field_value in item.values()):
                reasons.append(f"runtime_capability_changes[{index}] is blank")
            continue
        if not str(item or "").strip():
            reasons.append(f"runtime_capability_changes[{index}] is blank")
    return reasons


def incomplete_command_reasons(commands: Any, field_name: str) -> list[str]:
    if not isinstance(commands, list) or not commands:
        return [f"{field_name} is empty"]
    reasons: list[str] = []
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            reasons.append(f"{field_name}[{index}] is not an object")
            continue
        for key in ("command", "purpose", "cwd"):
            if not str(command.get(key) or "").strip():
                reasons.append(f"{field_name}[{index}].{key} is blank")
        if command.get("exit_code") is None:
            reasons.append(f"{field_name}[{index}].exit_code is not recorded")
    return reasons


def incomplete_outcome_reasons(outcomes: Any) -> list[str]:
    if not isinstance(outcomes, list) or not outcomes:
        return ["outcomes is empty"]
    reasons: list[str] = []
    for index, outcome in enumerate(outcomes):
        if not isinstance(outcome, dict):
            reasons.append(f"outcomes[{index}] is not an object")
            continue
        for key in ("check", "evidence_artifact"):
            if not str(outcome.get(key) or "").strip():
                reasons.append(f"outcomes[{index}].{key} is blank")
        result = str(outcome.get("result") or "").strip().lower()
        if result in {"", "pending"}:
            reasons.append(f"outcomes[{index}].result is pending")
        elif result not in COMPLETED_VALIDATION_OUTCOME_RESULTS:
            reasons.append(
                f"outcomes[{index}].result must be one of: "
                + ", ".join(sorted(COMPLETED_VALIDATION_OUTCOME_RESULTS))
            )
    return reasons


def rank_signals_with_memory(
    signals: list[GrowthSignal],
    *,
    memory: GrowthMemory | None = None,
) -> list[GrowthSignal]:
    review_activity_by_repo = signal_review_activity_counts(signals)
    indexed = list(enumerate(signals))
    indexed.sort(
        key=lambda item: (
            -signal_safety_review_priority(item[1]),
            -signal_direct_action_priority(item[1]),
            -memory_bias_for_signal(item[1], memory),
            -signal_adjusted_confidence(item[1], review_activity_by_repo=review_activity_by_repo),
            item[0],
        )
    )
    return [signal for _, signal in indexed]


def signal_safety_review_priority(signal: GrowthSignal) -> int:
    return 1 if signal.risk_flags else 0


def signal_direct_action_priority(signal: GrowthSignal) -> int:
    if signal.kind == "PullRequestEvent":
        return 1
    text = f"{signal.title} {signal.relevance_reason} {signal.recommended_action}".lower()
    if signal.kind == "PushEvent" and any(term in text for term in ("validation", "validate", "test", "workflow")):
        pattern_evidence = push_pattern_evidence_for_signal(signal)
        if pattern_evidence is not None and not pattern_evidence["has_clear_test_evidence"]:
            return 0
        return 1
    if signal.kind == "ReleaseEvent":
        return 1
    return 0


def signal_review_activity_counts(signals: list[GrowthSignal]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signal in signals:
        if signal.kind not in REVIEW_ACTIVITY_EVENT_KINDS:
            continue
        counts[signal.repo] = counts.get(signal.repo, 0) + 1
    return counts


def signal_review_activity_bias(
    signal: GrowthSignal,
    *,
    review_activity_by_repo: dict[str, int],
) -> float:
    review_activity_count = review_activity_by_repo.get(signal.repo, 0)
    if review_activity_count < 2:
        return 0.0
    if not signal_is_review_validation_or_test_route(signal):
        return 0.0
    return min(0.4, 0.25 * (review_activity_count - 1))


def signal_adjusted_confidence(
    signal: GrowthSignal,
    *,
    review_activity_by_repo: dict[str, int],
) -> float:
    return signal.confidence + signal_review_activity_bias(signal, review_activity_by_repo=review_activity_by_repo)


def signal_is_review_validation_or_test_route(signal: GrowthSignal) -> bool:
    if signal.kind in REVIEW_ACTIVITY_EVENT_KINDS | {"PullRequestEvent"}:
        return True
    if signal.kind != "PushEvent":
        return False
    text = f"{signal.title} {signal.relevance_reason} {signal.recommended_action}".lower()
    return any(term in text for term in ("review", "validation", "validate", "test", "harness"))


def memory_bias_for_signal(signal: GrowthSignal, memory: GrowthMemory | None) -> float:
    if memory is None:
        return 0.0
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
    if signal.kind in REVIEW_ACTIVITY_EVENT_KINDS:
        return "test"
    if signal.kind in {"IssuesEvent", "IssueCommentEvent"}:
        return "follow_up_issue"
    return "no_action"


def push_pattern_evidence_for_signal(signal: GrowthSignal) -> dict[str, Any] | None:
    """Return commit-message cluster evidence for default push-derived lessons."""

    if signal.kind != "PushEvent":
        return None
    if signal.recommended_action != "cluster commit messages and keep only patterns with clear test evidence":
        return None
    text = f"{signal.title} {signal.relevance_reason}".lower()
    message_text = push_message_text(signal)
    clusters = [
        cluster_name
        for cluster_name, terms in PUSH_PATTERN_CLUSTERS
        if any(contains_risk_term(message_text, term) for term in terms)
    ]
    has_clear_test_evidence = any(contains_risk_term(message_text, term) for term in PUSH_PATTERN_TEST_EVIDENCE_TERMS)
    status = "ready" if clusters and has_clear_test_evidence else "evidence_gap"
    return {
        "status": status,
        "clusters": clusters,
        "has_clear_test_evidence": has_clear_test_evidence,
        "source": "push_commit_message_cluster",
        "policy": "keep_push_patterns_only_when_commit_messages_include_clear_test_or_ci_evidence",
        "matched_text_hash": stable_push_message_hash(text),
    }


def upstream_movement_evidence_for_signal(signal: GrowthSignal) -> dict[str, Any] | None:
    """Return local confirmation metadata for PR/review/push-derived lessons."""

    if signal.kind not in {"PullRequestEvent", *REVIEW_ACTIVITY_EVENT_KINDS, "PushEvent"}:
        return None
    item = {
        "item_id": signal.event_id,
        "event_kind": signal.kind,
        "summary": f"{signal.repo}: {signal.title}",
        "relevance_reason": signal.relevance_reason,
        "source_url": signal.url,
    }
    classification = classify_upstream_movement_item(item)
    status = "ready" if classification["confirmation_level"] == "specific" else "needs_triage"
    return {
        "status": status,
        "confirmation_level": classification["confirmation_level"],
        "branch": classification["branch"],
        "merge_timing": classification["merge_timing"],
        "subsystem": classification["subsystem"],
        "triage_key": classification["triage_key"],
        "missing_details": classification["missing_details"],
        "policy": "promote_upstream_movement_only_after_branch_timing_or_subsystem_confirmation",
    }


def build_upstream_movement_triage(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Group low-detail PR/review/push movement before it can justify local code."""

    clusters: dict[str, dict[str, Any]] = {}
    low_detail_count = 0
    specific_count = 0
    for item in items:
        if str(item.get("event_kind") or "") not in {"PullRequestEvent", *REVIEW_ACTIVITY_EVENT_KINDS, "PushEvent"}:
            continue
        classification = classify_upstream_movement_item(item)
        key = classification["triage_key"]
        cluster = clusters.setdefault(
            key,
            {
                "key": key,
                "branch": classification["branch"],
                "merge_timing": classification["merge_timing"],
                "subsystem": classification["subsystem"],
                "event_kinds": [],
                "item_ids": [],
                "confirmation_level": classification["confirmation_level"],
                "missing_details": [],
            },
        )
        cluster["event_kinds"].append(str(item.get("event_kind") or ""))
        cluster["item_ids"].append(str(item.get("item_id") or ""))
        cluster["missing_details"].extend(classification["missing_details"])
        if classification["confirmation_level"] == "low_detail":
            low_detail_count += 1
        else:
            specific_count += 1

    rendered_clusters = []
    for cluster in clusters.values():
        event_kinds = sorted(set(cluster["event_kinds"]))
        missing_details = sorted(set(cluster["missing_details"]))
        rendered_clusters.append(
            {
                "key": cluster["key"],
                "branch": cluster["branch"],
                "merge_timing": cluster["merge_timing"],
                "subsystem": cluster["subsystem"],
                "event_kinds": event_kinds,
                "item_ids": cluster["item_ids"],
                "item_count": len(cluster["item_ids"]),
                "confirmation_level": "low_detail" if missing_details else "specific",
                "missing_details": missing_details,
            }
        )
    rendered_clusters.sort(key=lambda cluster: (-int(cluster["item_count"]), str(cluster["key"])))
    return {
        "schema_version": 1,
        "policy": "group_pr_review_push_items_by_branch_timing_and_subsystem_before_promotion",
        "promotion_rule": (
            "Specific local proposals require an inspected branch, merge timing, touched subsystem, "
            "or local failing test; low-detail clusters remain follow-up evidence."
        ),
        "low_detail_item_count": low_detail_count,
        "specific_item_count": specific_count,
        "clusters": rendered_clusters,
    }


def classify_upstream_movement_item(item: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("event_kind", "summary", "relevance_reason", "source_url")
    )
    lowered = text.lower()
    branch = branch_from_upstream_movement_text(text)
    merge_timing = merge_timing_from_upstream_movement_text(lowered)
    subsystem = subsystem_from_upstream_movement_text(lowered)
    missing_details: list[str] = []
    if branch == "unknown":
        missing_details.append("branch")
    if merge_timing == "unknown":
        missing_details.append("merge_timing")
    if subsystem == "unknown":
        missing_details.append("subsystem")
    if upstream_movement_text_is_generic(lowered):
        missing_details.append("specific_title_or_body")
    confirmation_level = "low_detail" if missing_details else "specific"
    return {
        "branch": branch,
        "merge_timing": merge_timing,
        "subsystem": subsystem,
        "missing_details": missing_details,
        "confirmation_level": confirmation_level,
        "triage_key": f"branch={branch}|timing={merge_timing}|subsystem={subsystem}",
    }


def branch_from_upstream_movement_text(text: str) -> str:
    match = re.search(r"\bpush to ([^:\s]+)", text, flags=re.IGNORECASE)
    if match:
        return sanitize_upstream_group_value(match.group(1))
    match = re.search(r"\bfrom\s+(?:[^:\s]+:)?([A-Za-z0-9._/-]+)", text)
    if match:
        return sanitize_upstream_group_value(match.group(1))
    return "unknown"


def merge_timing_from_upstream_movement_text(text: str) -> str:
    if any(term in text for term in ("merged pull request", "closed pull request", "merge commit")):
        return "merged_or_closed"
    if any(term in text for term in ("opened pull request", "ready for review", "wants to merge")):
        return "pre_merge"
    if "push to" in text:
        return "push"
    return "unknown"


def subsystem_from_upstream_movement_text(text: str) -> str:
    subsystem_terms = (
        ("tests", ("test", "tests", "pytest", "e2e", "coverage", "regression", "smoke")),
        ("docs", ("docs", "documentation", "readme", "guide")),
        ("controller", ("controller", "proposal", "digest", "triage", "github-growth")),
        ("runtime", ("runner", "runtime", "harness", "sandbox", "policy", "provider", "scheduler")),
        ("ci", ("ci", "workflow", "actions", "release")),
    )
    for subsystem, terms in subsystem_terms:
        if any(term in text for term in terms):
            return subsystem
    return "unknown"


def upstream_movement_text_is_generic(text: str) -> bool:
    generic_terms = (
        "untitled pull request",
        "generic",
        "left a comment",
        "left review comments",
        "reviewed pull request",
        "submitted pull request review",
        "opened pull request: untitled",
        "push to repository",
    )
    return any(term in text for term in generic_terms)


def sanitize_upstream_group_value(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._/-]+", "-", value.strip()).strip("-").lower()
    return sanitized[:80] or "unknown"


UPSTREAM_EVIDENCE_CAPABILITY_DENIED_ACTIONS = (
    "provider_launch",
    "external_harness_execution",
    "remote_execution",
    "upstream_skill_activation",
    "privacy_data_export",
    "credential_access",
    "push_or_promotion",
    "kernel_restart",
)

_UPSTREAM_PR_COMPARE_MARKERS = (
    "untitled pull request",
    "compare the pull request approach",
    "pull request approach with local",
    "opened pull request",
    "generic pull request",
)


def attach_upstream_evidence_capability_step(digest: dict[str, Any]) -> dict[str, Any]:
    """Attach the operator-visible one-step capability translation for this digest."""

    step = build_upstream_evidence_capability_step(
        list(digest.get("proposals") or []),
        theme_window=digest.get("capability_theme_window")
        if isinstance(digest.get("capability_theme_window"), dict)
        else {},
        items=list(digest.get("items") or []),
    )
    digest["upstream_evidence_capability_step"] = step
    return digest


def build_upstream_evidence_capability_step(
    proposals: list[dict[str, Any]],
    *,
    theme_window: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Translate mixed upstream proposals into one local capability step.

    Public agent-ecosystem signals stay evidence. This surface picks a single
    next local action for operators and supervisors: compare weak PR movement
    with local behavior before drafting, keep privacy/offensive routes
    review-only, and never export raw evidence URLs or sensitive bodies.
    """

    del items  # reserved for future item-level corroboration without URL export
    theme = theme_window if isinstance(theme_window, dict) else {}
    candidate_rows = [classify_upstream_evidence_capability_route(proposal) for proposal in proposals]
    selected = select_upstream_evidence_capability_step(candidate_rows)
    retained_boundaries = [
        {
            "proposal_id": row["proposal_id"],
            "route_class": row["route_class"],
            "validation_gate": row["validation_gate"],
            "reason": row["selection_reason"],
        }
        for row in candidate_rows
        if row["route_class"]
        in {
            "privacy_boundary_review_only",
            "offensive_boundary_review_only",
        }
    ]
    if selected is None:
        status = "no_proposals" if not candidate_rows else "no_selectable_local_step"
        selected_step = {
            "proposal_id": "",
            "route_class": "none",
            "capability_action": "record_upstream_evidence_without_local_capability_step",
            "local_lane": "none",
            "validation_gate": "",
            "requires_local_compare_before_draft": False,
            "autonomous_local_apply": False,
            "selection_reason": "no_local_capability_step_selected",
        }
    else:
        status = str(selected["status"])
        selected_step = {
            "proposal_id": selected["proposal_id"],
            "route_class": selected["route_class"],
            "capability_action": selected["capability_action"],
            "local_lane": selected["local_lane"],
            "validation_gate": selected["validation_gate"],
            "requires_local_compare_before_draft": selected["requires_local_compare_before_draft"],
            "autonomous_local_apply": selected["autonomous_local_apply_allowed"],
            "selection_reason": selected["selection_reason"],
        }
        selected = {**selected, "selected": True}
        for row in candidate_rows:
            row["selected"] = row["proposal_id"] == selected_step["proposal_id"] and bool(
                selected_step["proposal_id"]
            )

    return {
        "schema_version": 1,
        "policy": "translate_upstream_evidence_into_one_local_capability_step",
        "theme_id": str(theme.get("theme_id") or "upstream-evidence-capability"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": str(theme.get("status") or ""),
        },
        "status": status,
        "selected_step": selected_step,
        "candidate_rows": candidate_rows,
        "retained_boundaries": retained_boundaries,
        "denied_actions": list(UPSTREAM_EVIDENCE_CAPABILITY_DENIED_ACTIONS),
        "runtime_action": "none",
        "privacy_export_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "promotion_rule": (
            "Select one local capability step after comparing weak PR or release evidence with local "
            "behavior; keep privacy leakage and offensive routes review-only; require focused local "
            "validation before code adoption."
        ),
    }


def classify_upstream_evidence_capability_route(proposal: dict[str, Any]) -> dict[str, Any]:
    """Classify one proposal into a local capability route without exporting raw URLs."""

    proposal_id = str(proposal.get("proposal_id") or "").strip()
    kind = str(proposal.get("kind") or "no_action").strip() or "no_action"
    implementation_scope = str(proposal.get("implementation_scope") or "").strip()
    validation_gate = str(proposal.get("validation_gate") or "").strip()
    risk_flags = sorted({str(flag) for flag in proposal.get("risk_flags", []) if str(flag).strip()})
    evidence_url_hashes = sorted(
        {
            hashlib.sha256(str(url).strip().encode("utf-8")).hexdigest()[:16]
            for url in proposal.get("evidence_urls", [])
            if str(url).strip()
        }
    )
    summary_text = " ".join(
        str(proposal.get(key) or "")
        for key in ("summary", "kind", "validation_task", "rationale", "recommended_action")
    ).lower()
    upstream_movement = proposal.get("upstream_movement_evidence")
    upstream_status = "not_applicable"
    upstream_confirmation = "not_applicable"
    if isinstance(upstream_movement, dict):
        upstream_status = str(upstream_movement.get("status") or "needs_triage")
        upstream_confirmation = str(upstream_movement.get("confirmation_level") or "low_detail")

    preflight = proposal_validation_preflight(proposal)
    autonomous_text = autonomous_local_apply_text(proposal)
    autonomous_allowed = autonomous_text == "True" and preflight.get("status") == "ready"

    if "offensive-behavior" in risk_flags or validation_gate == "offensive-behavior-human-review":
        route_class = "offensive_boundary_review_only"
        capability_action = "retain_offensive_behavior_review_boundary"
        local_lane = "none"
        requires_compare = False
        selection_reason = "offensive_behavior_remains_review_only"
        status = "blocked_by_safety_boundary"
        autonomous_allowed = False
    elif "privacy-leakage" in risk_flags or validation_gate == "privacy-leakage-human-review":
        route_class = "privacy_boundary_review_only"
        capability_action = "retain_privacy_leakage_review_boundary"
        local_lane = "none"
        requires_compare = False
        selection_reason = "privacy_leakage_remains_review_only"
        status = "blocked_by_safety_boundary"
        autonomous_allowed = False
    elif risk_flags or implementation_scope == "risk_review_before_local_change":
        route_class = "risk_review"
        capability_action = "summarize_risk_pattern_as_reviewable_local_note"
        local_lane = "documentation" if kind in {"documentation", "docs"} else "test"
        requires_compare = False
        selection_reason = "non_hard_risk_flags_require_reviewable_local_summary"
        status = "risk_review"
        autonomous_allowed = False
    elif (
        any(marker in summary_text for marker in _UPSTREAM_PR_COMPARE_MARKERS)
        or upstream_status == "needs_triage"
        or upstream_confirmation == "low_detail"
    ):
        route_class = "local_pr_compare_before_draft"
        capability_action = "compare_pull_request_approach_with_local_agent_behavior_before_draft"
        local_lane = _local_lane_from_proposal_kind(kind)
        requires_compare = True
        selection_reason = "weak_or_untitled_pull_request_evidence_requires_local_compare_before_draft"
        status = "compare_before_draft"
        # Compare-before-draft is an operator-visible capability step, not an apply grant.
        autonomous_allowed = False
    elif implementation_scope == "local_validation_candidate" and preflight.get("status") == "ready":
        route_class = "local_validation_ready"
        capability_action = "apply_one_local_validation_candidate"
        local_lane = _local_lane_from_proposal_kind(kind)
        requires_compare = False
        selection_reason = "confirmed_local_validation_candidate_ready"
        status = "ready"
    elif implementation_scope == "local_validation_candidate":
        route_class = "local_validation_gap"
        capability_action = "close_local_validation_gap_before_capability_apply"
        local_lane = _local_lane_from_proposal_kind(kind)
        requires_compare = upstream_status == "needs_triage"
        selection_reason = "local_validation_candidate_has_preflight_gaps"
        status = "validation_gap"
        autonomous_allowed = False
    elif implementation_scope == "reviewable_proposal_only" or kind in {"follow_up_issue", "no_action"}:
        route_class = "follow_up_only"
        capability_action = "preserve_follow_up_without_local_capability_apply"
        local_lane = "none"
        requires_compare = False
        selection_reason = "proposal_is_follow_up_or_reviewable_only"
        status = "follow_up_only"
        autonomous_allowed = False
    else:
        route_class = "follow_up_only"
        capability_action = "preserve_follow_up_without_local_capability_apply"
        local_lane = _local_lane_from_proposal_kind(kind)
        requires_compare = False
        selection_reason = "no_mapped_local_capability_route"
        status = "follow_up_only"
        autonomous_allowed = False

    return {
        "proposal_id": proposal_id,
        "route_class": route_class,
        "capability_action": capability_action,
        "local_lane": local_lane,
        "kind": kind,
        "implementation_scope": implementation_scope,
        "validation_gate": validation_gate,
        "risk_flags": risk_flags,
        "evidence_url_hashes": evidence_url_hashes,
        "upstream_confirmation": upstream_confirmation,
        "upstream_movement_status": upstream_status,
        "requires_local_compare_before_draft": requires_compare,
        "autonomous_local_apply_allowed": autonomous_allowed,
        "autonomous_local_apply_text": autonomous_text,
        "validation_preflight_status": str(preflight.get("status") or ""),
        "validation_gaps": list(preflight.get("validation_gaps") or []),
        "selection_reason": selection_reason,
        "status": status,
        "selected": False,
    }


def select_upstream_evidence_capability_step(
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick one next local capability step from classified proposal rows."""

    if not candidate_rows:
        return None

    priority = {
        "local_validation_ready": 0,
        "local_pr_compare_before_draft": 1,
        "local_validation_gap": 2,
        "risk_review": 3,
        "follow_up_only": 4,
        "privacy_boundary_review_only": 5,
        "offensive_boundary_review_only": 6,
    }
    ranked = sorted(
        candidate_rows,
        key=lambda row: (
            priority.get(str(row.get("route_class") or ""), 99),
            str(row.get("proposal_id") or ""),
        ),
    )
    selected = ranked[0]
    # If the only rows are hard safety boundaries, still surface one retained boundary
    # as the selected step so operators see an explicit non-apply outcome.
    return selected


def _local_lane_from_proposal_kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized in {"code_patch", "code", "patch"}:
        return "code_patch"
    if normalized in {"test", "tests"}:
        return "test"
    if normalized in {"documentation", "docs", "doc"}:
        return "documentation"
    if normalized in {"config", "configuration"}:
        return "config"
    if normalized in {"follow_up_issue", "no_action"}:
        return "none"
    return "test"


SKILL_ROUTE_DISCOVERY_CAPABILITY_DENIED_ACTIONS = (
    "external_skill_execution",
    "external_skill_activation",
    "provider_launch",
    "external_harness_execution",
    "remote_apply",
    "remote_execution",
    "privacy_data_export",
    "credential_access",
    "push_or_promotion",
    "kernel_restart",
)
SKILL_ROUTE_DISCOVERY_ALLOWED_LANES = ("documentation", "config", "test", "code_patch")
SKILL_ROUTE_DISCOVERY_PIPELINE_STAGES = (
    "classifier",
    "route_profiles",
    "bounded_local_apply_lanes",
)
SKILL_ROUTE_DISCOVERY_LOCAL_COMPARISON_CRITERIA = (
    "route_class_is_skill_route_discovery",
    "skill_route_discovery_first_for_codex_workflow_gate",
    "codex_workflow_gate_or_generic_skill_workflow_profile",
    "preferred_lane_matches_route_profile",
    "allowed_lanes_subset_of_bounded_local_apply",
    "runtime_action_is_none",
    "external_skill_execution_denied",
    "provider_launch_denied",
    "remote_apply_denied",
    "general_agent_rows_do_not_inherit_skill_unlock",
    "privacy_or_offensive_rows_remain_review_only",
)
_SKILL_ROUTE_REVERSE_FLOW_MARKERS = (
    "reverse-flow",
    "reverse_flow",
    "reverse flow",
    "codex_workflow_gate",
    "skill_route_discovery_first",
    "lingbol088-spec/reverse-flow-skill",
)
_SKILL_ROUTE_RNSKILL_MARKERS = (
    "rnskill",
    "pluviobyte/rnskill",
    "generic_skill_workflow",
    "skill.md collection",
    "skills collection",
    "skill collection",
)
_SKILL_ROUTE_FORTRESS_MARKERS = (
    "fortress",
    "tiliondev/fortress",
)
_SKILL_ROUTE_HY3_MARKERS = (
    "hy3",
    "tencent-hunyuan/hy3",
    "tencent-hunyuan",
)
_SKILL_ROUTE_AGENT_CHIEF_MARKERS = (
    "agent-chief",
    "agent_chief",
    "smilelikeye/agent-chief",
)
_SKILL_ROUTE_GENERAL_AGENT_HARNESS_MARKERS = (
    "agent_harness_eval",
    "agent harness eval",
    "general_agent_project",
    "general agent project",
    "prop-harness-fortress",
    "prop-harness-hy3",
    "prop-hy3-harness",
    "prop-fortress",
)
_SKILL_ROUTE_GENERIC_SKILL_MARKERS = (
    "skill_route_discovery",
    "skill workflow",
    "skill_workflow",
    "skill.md",
    "skills/",
    "agent skill",
    "codex skill",
)
AGENT_HARNESS_EVAL_POST_COMPARE_LANES = ("documentation", "test", "code_patch")
ADJACENT_HARNESS_EVAL_VALIDATION_COMMAND = (
    "pytest tests/test_harness_eval.py -q -k agent_harness_eval_cluster_local_apply"
)


def attach_skill_route_discovery_capability_pipeline(digest: dict[str, Any]) -> dict[str, Any]:
    """Attach the operator-visible skill-route capability pipeline for this digest."""

    pipeline = build_skill_route_discovery_capability_pipeline(
        list(digest.get("proposals") or []),
        theme_window=digest.get("capability_theme_window")
        if isinstance(digest.get("capability_theme_window"), dict)
        else {},
        items=list(digest.get("items") or []),
    )
    digest["skill_route_discovery_capability_pipeline"] = pipeline
    return digest


def build_skill_route_discovery_capability_pipeline(
    proposals: list[dict[str, Any]],
    *,
    theme_window: dict[str, Any] | None = None,
    items: list[dict[str, Any]] | None = None,
    local_comparison_passed: bool = False,
    apply_local_comparison: bool = True,
    focused_validation_command_results: list[dict[str, Any]] | None = None,
    source_digest: str | None = None,
) -> dict[str, Any]:
    """Translate skill/workflow trend signals into one local capability pipeline.

    Pass 1 of skill-route-discovery: classifier → route profiles → bounded local
    apply lanes. reverse-flow-skill maps to codex_workflow_gate /
    skill_route_discovery_first; rnskill maps to generic_skill_workflow. Lanes
    stay limited to documentation, config, test, or code_patch. Local comparison
    is required before any lane unlock. Runtime action stays none. Privacy and
    offensive rows remain review-only; general-agent projects stay adjacent
    harness-eval candidates without inheriting skill-route lanes.

    Pass 2 deepens the reverse-flow local test validation lane: skill-workflow
    probe outputs are compared against classifier / route_profiles /
    bounded_local_apply_lanes criteria before the preferred test lane unlocks.

    Pass 3 packages the unlocked reverse-flow test lane into a body-free local
    apply handoff with companion rnskill documentation profiles and config-gate
    boundaries on the same pipeline (no isolated fixtures).

    Pass 4 closes the theme with skill_route_discovery_local_apply_completion:
    once reverse-flow local apply is ready, emit an operator-visible completion
    handoff that binds the full capability pipeline, unlocked local test lane,
    retained privacy/general-agent boundaries, and the external supervisor
    next action.

    After completion, skill_route_discovery_unlocked_local_test_lane_apply
    packages the supervisor next action
    (apply_unlocked_local_test_lane_with_focused_validation_and_keep_activation_external)
    into a body-free focused-validation apply packet for the reverse-flow test
    lane only. skill_route_discovery_focused_local_test_validation then records
    the body-free focused validation run (command hashes; optional pass/fail
    results) while activation stays external. Optional
    ``focused_validation_command_results`` close that surface from ``ready`` to
    ``passed``/``failed`` in one pipeline build; supervisors may also call
    ``record_skill_route_discovery_focused_local_test_validation_results`` on an
    existing pipeline after running the focused commands. After a recorded pass,
    ``skill_route_discovery_focused_validation_activation_external_handoff``
    packages ``keep_activation_external_after_focused_local_test_validation`` into
    one operator-visible activation-external packet (push, promotion, provider
    launch, remote apply, external skill execution, and kernel restart stay
    denied). Supervisors may close a ready focused surface with
    ``close_skill_route_discovery_focused_local_test_validation_with_outcome``
    (body-free expected-hash rows → record → handoff refresh) without
    re-listing commands. When the activation-external handoff is ready after a
    recorded pass,
    ``skill_route_discovery_focused_validation_activation_external_acceptance``
    packages terminal acceptance while residual fortress/Hy3 rows stay adjacent
    harness-eval only. After acceptance is ``accepted`` and residual adjacent
    rows remain,
    ``skill_route_discovery_focused_validation_residual_adjacent_queue`` packages
    those proposal IDs for ``agent_harness_eval_cluster_local_apply`` without
    inheriting skill unlocks. External skill execution, provider launch, remote
    apply, push, promotion, and kernel restart stay denied; activation remains
    external.
    """

    del items  # reserved for future item-level corroboration without URL export
    theme = theme_window if isinstance(theme_window, dict) else {}
    candidate_rows = [
        classify_skill_route_discovery_capability_route(proposal) for proposal in proposals
    ]
    selected = select_skill_route_discovery_capability_step(candidate_rows)
    retained_boundaries = [
        {
            "proposal_id": row["proposal_id"],
            "route_class": row["route_class"],
            "validation_gate": row["validation_gate"],
            "reason": row["selection_reason"],
        }
        for row in candidate_rows
        if row["route_class"]
        in {
            "privacy_boundary_review_only",
            "offensive_boundary_review_only",
        }
    ]
    adjacent_general_agent_rows = [
        {
            "proposal_id": row["proposal_id"],
            "route_class": row["route_class"],
            "evaluation_lane": "agent_harness_eval_required",
            "skill_route_discovery_inherited": False,
            "allowed_local_lanes_after_eval": ["documentation", "test", "code_patch"],
            "direct_allowed_lanes_before_eval": [],
            "runtime_action": "none",
            "reason": row["selection_reason"],
        }
        for row in candidate_rows
        if row["route_class"] == "agent_harness_eval_required"
    ]
    skill_route_rows = [
        row for row in candidate_rows if row["route_class"] == "skill_route_discovery"
    ]
    route_profile_rows = [
        {
            "proposal_id": row["proposal_id"],
            "route_profiles": list(row["route_profiles"]),
            "skill_route_discovery_first": bool(row["skill_route_discovery_first"]),
            "preferred_local_lane": row["preferred_local_lane"],
            "allowed_local_lanes": list(row["allowed_local_lanes"]),
        }
        for row in skill_route_rows
    ]

    local_comparison: dict[str, Any] = {
        "controller_surface": "skill_route_discovery_local_comparison",
        "status": "not_applicable",
        "decision": "no_skill_route_candidate_to_compare",
        "criteria_results": [],
        "failed_criteria": [],
        "local_comparison_passed": False,
        "unlocked_local_lanes": [],
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
    }

    if selected is None:
        status = "no_proposals" if not candidate_rows else "no_selectable_skill_route_step"
        selected_step = {
            "proposal_id": "",
            "route_class": "none",
            "capability_action": "record_skill_route_evidence_without_local_apply",
            "route_profiles": [],
            "selected_local_lane": "none",
            "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
            "unlocked_local_lanes": [],
            "local_comparison_required": True,
            "local_comparison_status": "not_applicable",
            "skill_route_discovery_first": False,
            "validation_gate": "",
            "autonomous_local_apply": False,
            "selection_reason": "no_skill_route_capability_step_selected",
        }
        bounded_status = "not_applicable"
        selected_is_adjacent_harness = False
    else:
        selected_is_adjacent_harness = (
            str(selected.get("route_class") or "") == "agent_harness_eval_required"
        )
        local_comparison = evaluate_skill_route_discovery_local_comparison(
            selected,
            candidate_rows=candidate_rows,
            adjacent_general_agent_rows=adjacent_general_agent_rows,
            retained_boundaries=retained_boundaries,
        )
        criteria_passed = bool(local_comparison.get("local_comparison_passed"))
        comparison_not_applicable = str(local_comparison.get("status") or "") == "not_applicable"
        # Explicit override remains available for replay fixtures; pass 2 defaults
        # to criteria-driven comparison so reverse-flow unlock is evidence-backed.
        # Adjacent general-agent selections never unlock skill-route lanes.
        if selected_is_adjacent_harness or comparison_not_applicable:
            comparison_passed = False
            comparison_status = "not_applicable"
        else:
            comparison_passed = bool(local_comparison_passed) or (
                apply_local_comparison and criteria_passed
            )
            comparison_status = (
                "passed"
                if comparison_passed
                else (
                    "failed"
                    if apply_local_comparison and not criteria_passed
                    else "required_before_unlock"
                )
            )
        preferred_lane = str(selected["preferred_local_lane"] or "")
        unlocked_lanes = (
            [preferred_lane]
            if comparison_passed
            and preferred_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
            and not selected_is_adjacent_harness
            else []
        )
        status = "ready" if selected["status"] == "ready" else str(selected["status"])
        if selected_is_adjacent_harness:
            status = "adjacent_harness_eval"
        elif status == "ready" and not comparison_passed:
            status = "ready_for_local_comparison"
        elif status == "ready" and comparison_passed:
            status = "ready"
        elif comparison_passed and selected["status"] in {"ready", "validation_gap", "risk_review"}:
            status = "ready" if selected["status"] == "ready" else str(selected["status"])
        selected_step = {
            "proposal_id": selected["proposal_id"],
            "route_class": selected["route_class"],
            "capability_action": selected["capability_action"],
            "route_profiles": list(selected["route_profiles"]),
            "selected_local_lane": preferred_lane if preferred_lane else "none",
            "allowed_local_lanes": list(selected["allowed_local_lanes"]),
            "unlocked_local_lanes": unlocked_lanes,
            "local_comparison_required": not selected_is_adjacent_harness,
            "local_comparison_status": comparison_status,
            "skill_route_discovery_first": bool(selected["skill_route_discovery_first"]),
            "validation_gate": selected["validation_gate"],
            "autonomous_local_apply": bool(selected["autonomous_local_apply_allowed"])
            and not selected_is_adjacent_harness,
            "selection_reason": selected["selection_reason"],
        }
        for row in candidate_rows:
            row["selected"] = row["proposal_id"] == selected_step["proposal_id"] and bool(
                selected_step["proposal_id"]
            )
        if selected_is_adjacent_harness:
            bounded_status = "deferred_to_agent_harness_eval_local_comparison"
        else:
            bounded_status = (
                "lanes_unlocked_after_local_comparison"
                if unlocked_lanes
                else (
                    "local_comparison_failed"
                    if comparison_status == "failed"
                    else "local_comparison_required_before_unlock"
                )
            )
        local_comparison["unlocked_local_lanes"] = list(unlocked_lanes)
        local_comparison["applied"] = bool(
            (apply_local_comparison or local_comparison_passed) and not selected_is_adjacent_harness
        )
        local_comparison["selected_local_lane"] = preferred_lane if preferred_lane else "none"

    classifier_status = (
        "ready"
        if skill_route_rows or retained_boundaries or adjacent_general_agent_rows
        else status
    )
    route_profiles_status = "ready" if route_profile_rows else "no_skill_route_profiles"
    reverse_flow_test_lane = build_skill_route_discovery_reverse_flow_test_validation_lane(
        selected_step=selected_step,
        local_comparison=local_comparison,
        route_profile_rows=route_profile_rows,
        theme_window=theme,
    )
    rnskill_docs_lane = build_skill_route_discovery_rnskill_docs_validation_lane(
        route_profile_rows=route_profile_rows,
        local_comparison=local_comparison,
        reverse_flow_test_validation_lane=reverse_flow_test_lane,
        theme_window=theme,
    )
    config_gate_boundary = build_skill_route_discovery_config_gate_boundary(
        selected_step=selected_step,
        route_profile_rows=route_profile_rows,
        adjacent_general_agent_rows=adjacent_general_agent_rows,
        retained_boundaries=retained_boundaries,
        local_comparison=local_comparison,
        theme_window=theme,
    )
    local_apply = build_skill_route_discovery_local_apply(
        selected_step=selected_step,
        local_comparison=local_comparison,
        reverse_flow_test_validation_lane=reverse_flow_test_lane,
        rnskill_docs_validation_lane=rnskill_docs_lane,
        config_gate_boundary=config_gate_boundary,
        theme_window=theme,
    )
    local_apply_completion = build_skill_route_discovery_local_apply_completion(
        local_apply=local_apply,
        reverse_flow_test_validation_lane=reverse_flow_test_lane,
        rnskill_docs_validation_lane=rnskill_docs_lane,
        config_gate_boundary=config_gate_boundary,
        local_comparison=local_comparison,
        retained_boundaries=retained_boundaries,
        adjacent_general_agent_rows=adjacent_general_agent_rows,
        theme_window=theme,
    )
    unlocked_local_test_lane_apply = build_skill_route_discovery_unlocked_local_test_lane_apply(
        local_apply_completion=local_apply_completion,
        local_apply=local_apply,
        reverse_flow_test_validation_lane=reverse_flow_test_lane,
        local_comparison=local_comparison,
        selected_step=selected_step,
        retained_boundaries=retained_boundaries,
        adjacent_general_agent_rows=adjacent_general_agent_rows,
        theme_window=theme,
    )
    focused_local_test_validation = build_skill_route_discovery_focused_local_test_validation(
        unlocked_local_test_lane_apply=unlocked_local_test_lane_apply,
        command_results=focused_validation_command_results,
        theme_window=theme,
        source_digest=source_digest,
    )
    focused_validation_activation_external_handoff = (
        build_skill_route_discovery_focused_validation_activation_external_handoff(
            focused_local_test_validation=focused_local_test_validation,
            unlocked_local_test_lane_apply=unlocked_local_test_lane_apply,
            adjacent_general_agent_rows=adjacent_general_agent_rows,
            retained_boundaries=retained_boundaries,
            theme_window=theme,
            source_digest=source_digest,
        )
    )
    focused_validation_activation_external_acceptance = (
        build_skill_route_discovery_focused_validation_activation_external_acceptance(
            focused_validation_activation_external_handoff=(
                focused_validation_activation_external_handoff
            ),
            focused_local_test_validation=focused_local_test_validation,
            unlocked_local_test_lane_apply=unlocked_local_test_lane_apply,
            adjacent_general_agent_rows=adjacent_general_agent_rows,
            retained_boundaries=retained_boundaries,
            theme_window=theme,
            source_digest=source_digest,
        )
    )
    focused_validation_residual_adjacent_queue = (
        build_skill_route_discovery_focused_validation_residual_adjacent_queue(
            focused_validation_activation_external_acceptance=(
                focused_validation_activation_external_acceptance
            ),
            focused_validation_activation_external_handoff=(
                focused_validation_activation_external_handoff
            ),
            focused_local_test_validation=focused_local_test_validation,
            adjacent_general_agent_rows=adjacent_general_agent_rows,
            retained_boundaries=retained_boundaries,
            theme_window=theme,
            source_digest=source_digest,
        )
    )
    adjacent_harness_eval_handoff = build_skill_route_discovery_adjacent_harness_eval_handoff(
        selected_step=selected_step,
        adjacent_general_agent_rows=adjacent_general_agent_rows,
        retained_boundaries=retained_boundaries,
        local_comparison=local_comparison,
        local_apply=local_apply,
        local_apply_completion=local_apply_completion,
        theme_window=theme,
    )
    # Adjacent general-agent residual work is a deliberate handoff, not a failed reverse-flow theme.
    if (
        str(adjacent_harness_eval_handoff.get("status") or "") == "ready"
        and str(selected_step.get("route_class") or "") == "agent_harness_eval_required"
    ):
        status = "adjacent_harness_eval"
    # Pass 4 closes the window when the reverse-flow local apply completion is ready.
    if (
        str(local_apply_completion.get("status") or "") == "complete"
        and int(theme.get("planned_passes") or 0)
        >= int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES)
    ):
        status = "complete"
    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_capability_pipeline",
        "policy": "translate_skill_workflow_signals_into_bounded_local_lanes",
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": (
                "complete"
                if str(local_apply_completion.get("status") or "") == "complete"
                and int(theme.get("planned_passes") or 0)
                >= int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES)
                else str(theme.get("status") or "")
            ),
        },
        "pipeline_stages": list(SKILL_ROUTE_DISCOVERY_PIPELINE_STAGES),
        "status": status,
        "classifier": {
            "status": classifier_status,
            "candidate_count": len(candidate_rows),
            "skill_route_count": len(skill_route_rows),
            "privacy_boundary_count": len(
                [row for row in candidate_rows if row["route_class"] == "privacy_boundary_review_only"]
            ),
            "general_agent_count": len(adjacent_general_agent_rows),
            "candidate_rows": candidate_rows,
        },
        "route_profiles": {
            "status": route_profiles_status,
            "rows": route_profile_rows,
            "codex_workflow_gate_count": len(
                [
                    row
                    for row in route_profile_rows
                    if "codex_workflow_gate" in row["route_profiles"]
                ]
            ),
            "generic_skill_workflow_count": len(
                [
                    row
                    for row in route_profile_rows
                    if "generic_skill_workflow" in row["route_profiles"]
                    and "codex_workflow_gate" not in row["route_profiles"]
                ]
            ),
        },
        "bounded_local_apply": {
            "status": bounded_status,
            "local_comparison_required": True,
            "local_comparison_status": selected_step["local_comparison_status"],
            "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
            "selected_local_lane": selected_step["selected_local_lane"],
            "unlocked_local_lanes": list(selected_step["unlocked_local_lanes"]),
            "runtime_action": "none",
            "external_skill_execution_allowed": False,
            "provider_launch_allowed": False,
            "remote_apply_allowed": False,
        },
        "local_comparison": local_comparison,
        "reverse_flow_test_validation_lane": reverse_flow_test_lane,
        "rnskill_docs_validation_lane": rnskill_docs_lane,
        "config_gate_boundary": config_gate_boundary,
        "local_apply": local_apply,
        "local_apply_completion": local_apply_completion,
        "unlocked_local_test_lane_apply": unlocked_local_test_lane_apply,
        "focused_local_test_validation": focused_local_test_validation,
        "focused_validation_activation_external_handoff": (
            focused_validation_activation_external_handoff
        ),
        "focused_validation_activation_external_acceptance": (
            focused_validation_activation_external_acceptance
        ),
        "focused_validation_residual_adjacent_queue": (
            focused_validation_residual_adjacent_queue
        ),
        "focused_local_test_validation_recorded": focused_local_test_validation.get(
            "focused_validation_recorded"
        )
        is True,
        "adjacent_agent_harness_eval_handoff": adjacent_harness_eval_handoff,
        "selected_step": selected_step,
        "retained_boundaries": retained_boundaries,
        "adjacent_general_agent_rows": adjacent_general_agent_rows,
        "denied_actions": list(SKILL_ROUTE_DISCOVERY_CAPABILITY_DENIED_ACTIONS),
        "runtime_action": "none",
        "privacy_export_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "external_skill_activation_allowed": False,
        "promotion_rule": (
            "Classify skill/workflow signals into route profiles, require local comparison "
            "before unlocking documentation/config/test/code_patch lanes, keep runtime_action "
            "none, and retain privacy/offensive rows review-only without exporting raw evidence URLs. "
            "Adjacent general_agent_project rows (for example fortress) hand off to "
            "agent_harness_eval_cluster_local_apply instead of failing skill-route comparison."
        ),
    }


def evaluate_skill_route_discovery_local_comparison(
    selected: dict[str, Any],
    *,
    candidate_rows: list[dict[str, Any]] | None = None,
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare one skill-route candidate against pipeline stage contracts.

    Pass 2 reverse-flow test validation: lock codex_workflow_gate +
    skill_route_discovery_first into a bounded local test lane only when the
    classifier / route_profiles / bounded_local_apply_lanes criteria hold.
    External skill execution, provider launch, and remote apply stay denied.
    """

    del candidate_rows  # retained/adjacent snapshots already encode boundary isolation
    adjacent = list(adjacent_general_agent_rows or [])
    retained = list(retained_boundaries or [])
    profiles = [str(profile) for profile in selected.get("route_profiles") or []]
    preferred_lane = str(selected.get("preferred_local_lane") or selected.get("selected_local_lane") or "")
    allowed_lanes = [str(lane) for lane in selected.get("allowed_local_lanes") or []]
    skill_first = bool(selected.get("skill_route_discovery_first"))
    route_class = str(selected.get("route_class") or "")
    runtime_action = str(selected.get("runtime_action") or "none")
    expected_lane = skill_route_discovery_preferred_lane(profiles, str(selected.get("kind") or ""))

    def _criterion(criterion_id: str, passed: bool, *, required: bool = True, detail: str = "") -> dict[str, Any]:
        return {
            "criterion_id": criterion_id,
            "passed": passed,
            "required": required,
            "detail": detail,
        }

    # Adjacent general-agent rows (fortress/Hy3) are not skill-route candidates.
    # Do not fail skill-route comparison; hand off to agent_harness_eval instead.
    if route_class == "agent_harness_eval_required":
        return {
            "schema_version": 1,
            "controller_surface": "skill_route_discovery_local_comparison",
            "status": "not_applicable",
            "decision": (
                "selected_adjacent_harness_eval_requires_agent_harness_local_comparison"
            ),
            "selected_proposal_id": str(selected.get("proposal_id") or ""),
            "route_class": route_class,
            "route_profiles": list(profiles),
            "skill_route_discovery_first": skill_first,
            "selected_local_lane": preferred_lane or "none",
            "allowed_local_lanes": list(allowed_lanes),
            "criteria_ids": list(SKILL_ROUTE_DISCOVERY_LOCAL_COMPARISON_CRITERIA),
            "criteria_results": [],
            "failed_criteria": [],
            "local_comparison_passed": False,
            "unlocked_local_lanes": [],
            "handoff_controller_surface": "agent_harness_eval_cluster_local_apply",
            "handoff_allowed_local_lanes": list(AGENT_HARNESS_EVAL_POST_COMPARE_LANES),
            "runtime_action": "none",
            "external_skill_execution_allowed": False,
            "provider_launch_allowed": False,
            "remote_apply_allowed": False,
            "raw_evidence_urls_exported": False,
            "raw_upstream_bodies_exported": False,
            "required_validation": [
                "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline",
                ADJACENT_HARNESS_EVAL_VALIDATION_COMMAND,
            ],
            "body_free": True,
        }

    if "codex_workflow_gate" in profiles:
        skill_first_ok = skill_first is True
        skill_first_detail = f"skill_route_discovery_first={skill_first}"
    else:
        # generic_skill_workflow companion profiles do not require the codex-first gate
        skill_first_ok = True
        skill_first_detail = "generic_skill_workflow does not require codex-first gate"

    criteria_results = [
        _criterion(
            "route_class_is_skill_route_discovery",
            route_class == "skill_route_discovery",
            detail=f"route_class={route_class or 'none'}",
        ),
        _criterion(
            "skill_route_discovery_first_for_codex_workflow_gate",
            skill_first_ok,
            detail=skill_first_detail,
        ),
        _criterion(
            "codex_workflow_gate_or_generic_skill_workflow_profile",
            any(profile in {"codex_workflow_gate", "generic_skill_workflow"} for profile in profiles),
            detail=f"route_profiles={profiles or ['none']}",
        ),
        _criterion(
            "preferred_lane_matches_route_profile",
            preferred_lane == expected_lane and preferred_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES,
            detail=f"preferred={preferred_lane or 'none'} expected={expected_lane}",
        ),
        _criterion(
            "allowed_lanes_subset_of_bounded_local_apply",
            bool(allowed_lanes)
            and all(lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES for lane in allowed_lanes),
            detail=f"allowed_local_lanes={allowed_lanes or ['none']}",
        ),
        _criterion(
            "runtime_action_is_none",
            runtime_action == "none",
            detail=f"runtime_action={runtime_action or 'none'}",
        ),
        _criterion(
            "external_skill_execution_denied",
            selected.get("external_skill_activation_allowed") is not True,
            detail="external_skill_execution stays denied for skill-route local lanes",
        ),
        _criterion(
            "provider_launch_denied",
            "provider_launch" in SKILL_ROUTE_DISCOVERY_CAPABILITY_DENIED_ACTIONS,
            detail="provider_launch is a denied pipeline action",
        ),
        _criterion(
            "remote_apply_denied",
            "remote_apply" in SKILL_ROUTE_DISCOVERY_CAPABILITY_DENIED_ACTIONS,
            detail="remote_apply is a denied pipeline action",
        ),
        _criterion(
            "general_agent_rows_do_not_inherit_skill_unlock",
            all(
                row.get("skill_route_discovery_inherited") is False
                and list(row.get("direct_allowed_lanes_before_eval") or []) == []
                for row in adjacent
            ),
            detail=f"adjacent_general_agent_count={len(adjacent)}",
        ),
        _criterion(
            "privacy_or_offensive_rows_remain_review_only",
            all(
                str(row.get("route_class") or "")
                in {"privacy_boundary_review_only", "offensive_boundary_review_only"}
                for row in retained
            )
            and str(selected.get("route_class") or "")
            not in {"privacy_boundary_review_only", "offensive_boundary_review_only"},
            detail=f"retained_boundary_count={len(retained)}",
        ),
    ]

    failed_criteria = [
        str(result["criterion_id"])
        for result in criteria_results
        if result.get("required") is True and result.get("passed") is not True
    ]
    comparison_passed = not failed_criteria
    unlocked = (
        [preferred_lane]
        if comparison_passed and preferred_lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
        else []
    )
    if comparison_passed:
        status = "passed"
        decision = "unlock_selected_local_lane_after_pipeline_stage_comparison"
    else:
        status = "failed"
        decision = "hold_selected_lane_until_pipeline_stage_comparison_passes"

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_local_comparison",
        "status": status,
        "decision": decision,
        "selected_proposal_id": str(selected.get("proposal_id") or ""),
        "route_class": route_class,
        "route_profiles": list(profiles),
        "skill_route_discovery_first": skill_first,
        "selected_local_lane": preferred_lane,
        "allowed_local_lanes": list(allowed_lanes),
        "criteria_ids": list(SKILL_ROUTE_DISCOVERY_LOCAL_COMPARISON_CRITERIA),
        "criteria_results": criteria_results,
        "failed_criteria": failed_criteria,
        "local_comparison_passed": comparison_passed,
        "unlocked_local_lanes": unlocked,
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline"
        ],
        "body_free": True,
    }


def build_skill_route_discovery_reverse_flow_test_validation_lane(
    *,
    selected_step: dict[str, Any],
    local_comparison: dict[str, Any],
    route_profile_rows: list[dict[str, Any]] | None = None,
    theme_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operator-visible pass-2 reverse-flow test validation lane.

    Locks reverse-flow codex_workflow_gate + skill_route_discovery_first into the
    bounded local test lane after local comparison. Companion rnskill rows remain
    visible as documentation-preferring generic_skill_workflow profiles on the
    same pipeline without isolated fixture sprawl.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    profiles = [str(profile) for profile in selected_step.get("route_profiles") or []]
    is_reverse_flow = "codex_workflow_gate" in profiles and bool(
        selected_step.get("skill_route_discovery_first")
    )
    comparison_passed = bool(local_comparison.get("local_comparison_passed"))
    selected_lane = str(selected_step.get("selected_local_lane") or "")
    unlocked = list(selected_step.get("unlocked_local_lanes") or [])
    companion_rnskill = [
        {
            "proposal_id": row.get("proposal_id"),
            "route_profiles": list(row.get("route_profiles") or []),
            "preferred_local_lane": row.get("preferred_local_lane"),
            "skill_route_discovery_first": bool(row.get("skill_route_discovery_first")),
        }
        for row in (route_profile_rows or [])
        if "generic_skill_workflow" in list(row.get("route_profiles") or [])
        and "codex_workflow_gate" not in list(row.get("route_profiles") or [])
    ]

    if not selected_step.get("proposal_id"):
        status = "not_applicable"
        decision = "no_selected_skill_route_step"
    elif not is_reverse_flow:
        status = "deferred_non_reverse_flow_selection"
        decision = "selected_step_is_not_reverse_flow_test_lane"
    elif comparison_passed and selected_lane == "test" and "test" in unlocked:
        status = "ready"
        decision = "reverse_flow_test_lane_unlocked_after_local_comparison"
    elif comparison_passed and selected_lane == "test":
        status = "comparison_passed_awaiting_lane_unlock"
        decision = "local_comparison_passed_for_reverse_flow_test_lane"
    else:
        status = "blocked_until_local_comparison"
        decision = "hold_reverse_flow_test_lane_until_local_comparison_passes"

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_reverse_flow_test_validation_lane",
        "proposal_track": "prop-skill-pipeline-reverse-flow-test",
        "status": status,
        "decision": decision,
        "selected_proposal_id": str(selected_step.get("proposal_id") or ""),
        "route_class": str(selected_step.get("route_class") or "none"),
        "route_profiles": profiles,
        "skill_route_discovery_first": bool(selected_step.get("skill_route_discovery_first")),
        "selected_local_lane": selected_lane,
        "preferred_local_lane": "test",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "unlocked_local_lanes": unlocked,
        "local_comparison_required": True,
        "local_comparison_status": str(
            selected_step.get("local_comparison_status")
            or local_comparison.get("status")
            or "required_before_unlock"
        ),
        "local_comparison_passed": comparison_passed,
        "failed_criteria": list(local_comparison.get("failed_criteria") or []),
        "companion_rnskill_documentation_profiles": companion_rnskill,
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": str(theme.get("status") or ""),
        },
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline"
        ],
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
    }


def build_skill_route_discovery_rnskill_docs_validation_lane(
    *,
    route_profile_rows: list[dict[str, Any]] | None = None,
    local_comparison: dict[str, Any] | None = None,
    reverse_flow_test_validation_lane: dict[str, Any] | None = None,
    theme_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operator-visible pass-3 rnskill documentation companion on the shared pipeline.

    Keeps prop-skill-pipeline-rnskill-docs as a body-free generic_skill_workflow
    documentation profile after reverse-flow local comparison. Does not open a
    separate fixture path, external skill execution, or remote apply.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    comparison = local_comparison if isinstance(local_comparison, dict) else {}
    reverse_lane = (
        reverse_flow_test_validation_lane
        if isinstance(reverse_flow_test_validation_lane, dict)
        else {}
    )
    companion_rows = [
        {
            "proposal_id": row.get("proposal_id"),
            "route_profiles": list(row.get("route_profiles") or []),
            "preferred_local_lane": row.get("preferred_local_lane"),
            "skill_route_discovery_first": bool(row.get("skill_route_discovery_first")),
            "allowed_local_lanes": list(row.get("allowed_local_lanes") or SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        }
        for row in (route_profile_rows or [])
        if "generic_skill_workflow" in list(row.get("route_profiles") or [])
        and "codex_workflow_gate" not in list(row.get("route_profiles") or [])
    ]
    comparison_passed = bool(comparison.get("local_comparison_passed"))
    reverse_ready = str(reverse_lane.get("status") or "") == "ready"
    preferred = "documentation"
    if not companion_rows:
        status = "not_applicable"
        decision = "no_rnskill_documentation_profiles_on_pipeline"
        unlocked: list[str] = []
    elif comparison_passed and reverse_ready:
        status = "ready"
        decision = "rnskill_docs_companion_ready_after_reverse_flow_local_comparison"
        unlocked = [preferred]
    elif comparison_passed:
        status = "comparison_passed_awaiting_reverse_flow_lane"
        decision = "hold_rnskill_docs_until_reverse_flow_test_lane_ready"
        unlocked = []
    else:
        status = "blocked_until_local_comparison"
        decision = "hold_rnskill_docs_until_pipeline_stage_comparison_passes"
        unlocked = []

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_rnskill_docs_validation_lane",
        "proposal_track": "prop-skill-pipeline-rnskill-docs",
        "status": status,
        "decision": decision,
        "route_class": "skill_route_discovery",
        "route_profiles": ["generic_skill_workflow"],
        "skill_route_discovery_first": False,
        "preferred_local_lane": preferred,
        "selected_local_lane": preferred,
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "unlocked_local_lanes": unlocked,
        "companion_profiles": companion_rows,
        "companion_count": len(companion_rows),
        "local_comparison_required": True,
        "local_comparison_passed": comparison_passed,
        "reverse_flow_test_validation_lane_status": str(reverse_lane.get("status") or "none"),
        "body_free": True,
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": str(theme.get("status") or ""),
        },
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline"
        ],
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
    }


def build_skill_route_discovery_config_gate_boundary(
    *,
    selected_step: dict[str, Any],
    route_profile_rows: list[dict[str, Any]] | None = None,
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
    local_comparison: dict[str, Any] | None = None,
    theme_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operator-visible pass-3 config gates separating skill routes from adjacent rows.

    prop-skill-pipeline-config-gates: codex_workflow_gate vs generic_skill_workflow
    stay distinct; general_agent_project and privacy rows never inherit skill-route
    unlocks. Runtime action stays none.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    comparison = local_comparison if isinstance(local_comparison, dict) else {}
    profiles = list(route_profile_rows or [])
    adjacent = list(adjacent_general_agent_rows or [])
    retained = list(retained_boundaries or [])
    codex_rows = [
        row for row in profiles if "codex_workflow_gate" in list(row.get("route_profiles") or [])
    ]
    generic_only_rows = [
        row
        for row in profiles
        if "generic_skill_workflow" in list(row.get("route_profiles") or [])
        and "codex_workflow_gate" not in list(row.get("route_profiles") or [])
    ]
    general_agent_isolated = all(
        row.get("skill_route_discovery_inherited") is False
        and list(row.get("direct_allowed_lanes_before_eval") or []) == []
        for row in adjacent
    )
    privacy_isolated = all(
        str(row.get("route_class") or "")
        in {"privacy_boundary_review_only", "offensive_boundary_review_only"}
        for row in retained
    )
    skill_unlocked = list(selected_step.get("unlocked_local_lanes") or [])
    profiles_separated = bool(codex_rows) or bool(generic_only_rows) or not profiles
    selected_route_class = str(selected_step.get("route_class") or "")
    selected_is_adjacent_harness = selected_route_class == "agent_harness_eval_required"
    selected_is_safety_boundary = selected_route_class in {
        "privacy_boundary_review_only",
        "offensive_boundary_review_only",
    }
    isolation_holds = general_agent_isolated and privacy_isolated and profiles_separated
    # Skill-route apply is only allowed for skill_route_discovery rows. Adjacent
    # harness-eval selections keep isolation ready without pretending to be a
    # skill unlock failure that needs repair.
    gates_pass = isolation_holds and not selected_is_safety_boundary and not selected_is_adjacent_harness
    if not selected_step.get("proposal_id"):
        status = "not_applicable"
        decision = "no_selected_skill_route_step_for_config_gates"
    elif selected_is_adjacent_harness and isolation_holds:
        status = "ready"
        decision = "adjacent_general_agent_row_does_not_inherit_skill_unlocks"
    elif selected_is_adjacent_harness:
        status = "blocked"
        decision = "repair_config_gate_isolation_before_adjacent_harness_handoff"
    elif gates_pass and bool(comparison.get("local_comparison_passed")):
        status = "ready"
        decision = "config_gates_hold_adjacent_rows_out_of_skill_unlocks"
    elif gates_pass:
        status = "ready_awaiting_local_comparison"
        decision = "config_gates_defined_local_comparison_still_required"
    else:
        status = "blocked"
        decision = "repair_config_gate_isolation_before_skill_local_apply"

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_config_gate_boundary",
        "proposal_track": "prop-skill-pipeline-config-gates",
        "status": status,
        "decision": decision,
        "codex_workflow_gate_count": len(codex_rows),
        "generic_skill_workflow_only_count": len(generic_only_rows),
        "route_profiles_separated": profiles_separated,
        "general_agent_inherits_skill_unlock": False,
        "general_agent_isolation_passed": general_agent_isolated,
        "privacy_rows_selectable_for_local_apply": False,
        "privacy_isolation_passed": privacy_isolated,
        "adjacent_general_agent_count": len(adjacent),
        "retained_boundary_count": len(retained),
        "skill_unlocked_lanes": skill_unlocked,
        "allowed_skill_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "local_comparison_passed": bool(comparison.get("local_comparison_passed")),
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": str(theme.get("status") or ""),
        },
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline"
        ],
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
    }


def build_skill_route_discovery_local_apply(
    *,
    selected_step: dict[str, Any],
    local_comparison: dict[str, Any],
    reverse_flow_test_validation_lane: dict[str, Any],
    rnskill_docs_validation_lane: dict[str, Any],
    config_gate_boundary: dict[str, Any],
    theme_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pass-3 local apply handoff for one skill-route validation candidate.

    After reverse-flow test lane unlock and pipeline-stage comparison, package
    the selected local test apply with body-free rnskill docs companion and
    config-gate boundaries. Runtime action, external skill execution, provider
    launch, remote apply, push, promotion, and restart stay denied.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    reverse_lane = reverse_flow_test_validation_lane
    rnskill_lane = rnskill_docs_validation_lane
    config_gates = config_gate_boundary
    comparison_passed = bool(local_comparison.get("local_comparison_passed"))
    reverse_ready = str(reverse_lane.get("status") or "") == "ready"
    rnskill_ready = str(rnskill_lane.get("status") or "") in {"ready", "not_applicable"}
    config_ready = str(config_gates.get("status") or "") in {
        "ready",
        "ready_awaiting_local_comparison",
        "not_applicable",
    }
    selected_lane = str(selected_step.get("selected_local_lane") or "")
    unlocked = list(selected_step.get("unlocked_local_lanes") or [])
    profiles = [str(profile) for profile in selected_step.get("route_profiles") or []]
    is_reverse_flow = "codex_workflow_gate" in profiles and bool(
        selected_step.get("skill_route_discovery_first")
    )

    selected_route_class = str(selected_step.get("route_class") or "none")
    selected_is_adjacent_harness = selected_route_class == "agent_harness_eval_required"
    if not selected_step.get("proposal_id"):
        status = "not_applicable"
        decision = "no_selected_skill_route_step_for_local_apply"
    elif selected_is_adjacent_harness:
        status = "deferred_adjacent_harness_eval"
        decision = "selected_step_is_adjacent_agent_harness_eval_not_skill_local_apply"
    elif not is_reverse_flow:
        status = "deferred_non_reverse_flow_selection"
        decision = "selected_step_is_not_reverse_flow_local_apply"
    elif (
        comparison_passed
        and reverse_ready
        and rnskill_ready
        and config_ready
        and selected_lane == "test"
        and "test" in unlocked
    ):
        status = "ready"
        decision = "apply_one_local_skill_route_validation_candidate_after_lane_unlock"
    elif comparison_passed and reverse_ready and selected_lane == "test" and "test" in unlocked:
        status = "blocked_until_companion_surfaces_ready"
        decision = "hold_local_apply_until_rnskill_docs_and_config_gates_ready"
    elif comparison_passed:
        status = "blocked_until_reverse_flow_lane_ready"
        decision = "hold_local_apply_until_reverse_flow_test_lane_ready"
    else:
        status = "blocked_until_local_comparison"
        decision = "hold_local_apply_until_pipeline_stage_comparison_passes"

    if status == "ready":
        supervisor_next_action = "replay_skill_route_discovery_local_apply_then_continue_to_pass4"
    elif status == "deferred_adjacent_harness_eval":
        supervisor_next_action = (
            "run_agent_harness_eval_local_comparison_for_selected_general_agent_row"
        )
    elif status in {"deferred_non_reverse_flow_selection", "not_applicable"}:
        supervisor_next_action = "wait_for_skill_route_discovery_reverse_flow_selection"
    else:
        supervisor_next_action = "repair_skill_route_discovery_local_apply_before_pass4"

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_local_apply",
        "proposal_track": (
            str(selected_step.get("proposal_id") or "prop-skill-pipeline-reverse-flow-test")
            if selected_is_adjacent_harness
            else "prop-skill-pipeline-reverse-flow-test"
        ),
        "companion_tracks": [
            "prop-skill-pipeline-rnskill-docs",
            "prop-skill-pipeline-config-gates",
        ],
        "status": status,
        "decision": decision,
        "capability_action": str(
            selected_step.get("capability_action")
            or "apply_one_local_skill_route_validation_candidate"
        ),
        "selected_proposal_id": str(selected_step.get("proposal_id") or ""),
        "route_class": selected_route_class,
        "route_profiles": profiles,
        "skill_route_discovery_first": bool(selected_step.get("skill_route_discovery_first")),
        "selected_local_lane": selected_lane if selected_lane else "none",
        "allowed_local_lanes": (
            list(AGENT_HARNESS_EVAL_POST_COMPARE_LANES)
            if selected_is_adjacent_harness
            else list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        ),
        "unlocked_local_lanes": unlocked if status == "ready" else [],
        "local_comparison_required": not selected_is_adjacent_harness,
        "local_comparison_passed": comparison_passed,
        "local_comparison_status": str(
            selected_step.get("local_comparison_status")
            or local_comparison.get("status")
            or "required_before_unlock"
        ),
        "reverse_flow_test_validation_lane_status": str(reverse_lane.get("status") or "none"),
        "rnskill_docs_validation_lane_status": str(rnskill_lane.get("status") or "none"),
        "config_gate_boundary_status": str(config_gates.get("status") or "none"),
        "rnskill_docs_companion": {
            "status": rnskill_lane.get("status"),
            "preferred_local_lane": rnskill_lane.get("preferred_local_lane"),
            "unlocked_local_lanes": list(rnskill_lane.get("unlocked_local_lanes") or []),
            "body_free": bool(rnskill_lane.get("body_free")),
            "proposal_track": rnskill_lane.get("proposal_track"),
        },
        "config_gates": {
            "status": config_gates.get("status"),
            "general_agent_inherits_skill_unlock": bool(
                config_gates.get("general_agent_inherits_skill_unlock")
            ),
            "privacy_rows_selectable_for_local_apply": bool(
                config_gates.get("privacy_rows_selectable_for_local_apply")
            ),
            "route_profiles_separated": bool(config_gates.get("route_profiles_separated")),
            "proposal_track": config_gates.get("proposal_track"),
        },
        "autonomous_local_apply": bool(selected_step.get("autonomous_local_apply"))
        and status == "ready",
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": str(theme.get("status") or ""),
        },
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline"
        ]
        + (
            [ADJACENT_HARNESS_EVAL_VALIDATION_COMMAND]
            if selected_is_adjacent_harness
            else []
        ),
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "supervisor_next_action": supervisor_next_action,
    }


def build_skill_route_discovery_local_apply_completion(
    *,
    local_apply: dict[str, Any],
    reverse_flow_test_validation_lane: dict[str, Any] | None = None,
    rnskill_docs_validation_lane: dict[str, Any] | None = None,
    config_gate_boundary: dict[str, Any] | None = None,
    local_comparison: dict[str, Any] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    theme_window: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> dict[str, Any]:
    """Pass-4 completion handoff after reverse-flow local apply unlocks.

    Closes the skill-route-discovery theme window once
    ``skill_route_discovery_local_apply`` is ready for the reverse-flow test
    lane. Binds the full capability pipeline (classifier → route_profiles →
    bounded_local_apply_lanes → local comparison → reverse-flow test lane →
    rnskill docs companion → config gates → local apply → completion), retained
    privacy/general-agent boundaries, and the external supervisor next action.
    Runtime action, external skill execution, provider launch, remote apply,
    push, promotion, and kernel restart stay denied.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    apply = local_apply if isinstance(local_apply, dict) else {}
    reverse_lane = (
        reverse_flow_test_validation_lane
        if isinstance(reverse_flow_test_validation_lane, dict)
        else {}
    )
    rnskill_lane = (
        rnskill_docs_validation_lane if isinstance(rnskill_docs_validation_lane, dict) else {}
    )
    config_gates = config_gate_boundary if isinstance(config_gate_boundary, dict) else {}
    comparison = local_comparison if isinstance(local_comparison, dict) else {}
    retained = list(retained_boundaries or [])
    adjacent = list(adjacent_general_agent_rows or [])

    planned_passes = int(theme.get("planned_passes") or 0)
    target_passes = int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES)
    apply_status = str(apply.get("status") or "")
    comparison_passed = bool(
        apply.get("local_comparison_passed")
        if apply.get("local_comparison_passed") is not None
        else comparison.get("local_comparison_passed")
    )
    unlocked = [
        lane
        for lane in list(apply.get("unlocked_local_lanes") or [])
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    reverse_ready = str(reverse_lane.get("status") or "") == "ready"
    rnskill_ready = str(rnskill_lane.get("status") or "") in {"ready", "not_applicable"}
    config_ready = str(config_gates.get("status") or "") in {
        "ready",
        "ready_awaiting_local_comparison",
        "not_applicable",
    }
    selected_lane = str(apply.get("selected_local_lane") or "")
    selected_proposal_id = str(
        apply.get("selected_proposal_id")
        or apply.get("proposal_track")
        or "prop-skill-pipeline-reverse-flow-test"
    )
    retained_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in retained
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
    )
    adjacent_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in adjacent
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
    )
    general_agent_isolated = all(
        row.get("skill_route_discovery_inherited") is False
        and list(row.get("direct_allowed_lanes_before_eval") or []) == []
        for row in adjacent
    ) if adjacent else True
    privacy_isolated = all(
        str(row.get("route_class") or "")
        in {"privacy_boundary_review_only", "offensive_boundary_review_only"}
        for row in retained
    ) if retained else True

    apply_route_class = str(apply.get("route_class") or "")
    selected_is_adjacent_harness = (
        apply_route_class == "agent_harness_eval_required"
        or apply_status == "deferred_adjacent_harness_eval"
    )
    theme_complete = (
        apply_status == "ready"
        and comparison_passed
        and reverse_ready
        and rnskill_ready
        and config_ready
        and selected_lane == "test"
        and "test" in unlocked
        and apply.get("runtime_action") == "none"
        and apply.get("external_skill_execution_allowed") is not True
        and apply.get("provider_launch_allowed") is not True
        and apply.get("remote_apply_allowed") is not True
        and apply.get("push_or_promotion_allowed") is not True
        and apply.get("kernel_restart_allowed") is not True
        and general_agent_isolated
        and privacy_isolated
        and config_gates.get("general_agent_inherits_skill_unlock") is not True
        and config_gates.get("privacy_rows_selectable_for_local_apply") is not True
        and not selected_is_adjacent_harness
    )

    if apply_status in {"", "not_applicable"} and not selected_proposal_id:
        status = "not_applicable"
        decision = "no_skill_route_local_apply_candidate_to_complete_theme"
        supervisor_next_action = "wait_for_skill_route_discovery_local_apply"
    elif selected_is_adjacent_harness and general_agent_isolated and privacy_isolated:
        # Residual fortress-style general-agent work is a deliberate handoff, not
        # a reverse-flow theme repair signal.
        status = "deferred_adjacent_harness_eval"
        decision = (
            "hand_off_selected_adjacent_row_to_agent_harness_eval_local_comparison"
        )
        supervisor_next_action = (
            "run_agent_harness_eval_local_comparison_for_selected_general_agent_row"
        )
    elif theme_complete:
        status = "complete"
        decision = (
            "complete_skill_route_discovery_capability_slice_after_reverse_flow_local_apply"
        )
        supervisor_next_action = (
            "apply_unlocked_local_test_lane_with_focused_validation_and_keep_activation_external"
        )
    else:
        status = "blocked"
        decision = "hold_theme_completion_until_reverse_flow_local_apply_unlocks_test_lane"
        supervisor_next_action = (
            "repair_skill_route_discovery_local_apply_before_theme_completion"
        )

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_local_apply_completion",
        "proposal_track": "prop-skill-pipeline-reverse-flow-test",
        "companion_tracks": [
            "prop-skill-pipeline-rnskill-docs",
            "prop-skill-pipeline-config-gates",
        ],
        "proposal_id": selected_proposal_id,
        "selected_proposal_id": selected_proposal_id,
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": planned_passes,
            "target_passes": target_passes,
            "current_pass": planned_passes if planned_passes > 0 else target_passes,
            "status": "complete" if theme_complete else status,
            "is_final_pass": planned_passes >= target_passes and target_passes > 0,
        },
        "source_digest": source_digest or "",
        "status": status,
        "decision": decision,
        "capability_action": str(
            apply.get("capability_action")
            or "apply_one_local_skill_route_validation_candidate"
        ),
        "capability_pipeline": [
            "skill_route_discovery_capability_pipeline",
            "skill_route_discovery_local_comparison",
            "skill_route_discovery_reverse_flow_test_validation_lane",
            "skill_route_discovery_rnskill_docs_validation_lane",
            "skill_route_discovery_config_gate_boundary",
            "skill_route_discovery_local_apply",
            "skill_route_discovery_local_apply_completion",
            "skill_route_discovery_unlocked_local_test_lane_apply",
            "skill_route_discovery_adjacent_harness_eval_handoff",
        ],
        "local_apply_status": apply_status,
        "local_comparison_passed": comparison_passed,
        "local_comparison_status": str(
            apply.get("local_comparison_status") or comparison.get("status") or ""
        ),
        "reverse_flow_test_validation_lane_status": str(reverse_lane.get("status") or "none"),
        "rnskill_docs_validation_lane_status": str(rnskill_lane.get("status") or "none"),
        "config_gate_boundary_status": str(config_gates.get("status") or "none"),
        "selected_local_lane": selected_lane if selected_lane else "none",
        "unlocked_local_lanes": unlocked if theme_complete else [],
        "allowed_local_lanes": (
            list(AGENT_HARNESS_EVAL_POST_COMPARE_LANES)
            if selected_is_adjacent_harness
            else list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)
        ),
        "route_class": str(apply.get("route_class") or "skill_route_discovery"),
        "route_profiles": list(apply.get("route_profiles") or []),
        "skill_route_discovery_first": bool(apply.get("skill_route_discovery_first")),
        "local_validation_required": True,
        "theme_complete": theme_complete,
        "adjacent_harness_eval_handoff_required": selected_is_adjacent_harness,
        "retained_boundary_proposal_ids": retained_ids,
        "adjacent_general_agent_proposal_ids": adjacent_ids,
        "general_agent_inherits_skill_unlock": False,
        "privacy_rows_selectable_for_local_apply": False,
        "general_agent_isolation_passed": general_agent_isolated,
        "privacy_isolation_passed": privacy_isolated,
        "rnskill_docs_companion": {
            "status": rnskill_lane.get("status"),
            "preferred_local_lane": rnskill_lane.get("preferred_local_lane"),
            "body_free": bool(rnskill_lane.get("body_free", True)),
            "proposal_track": rnskill_lane.get("proposal_track")
            or "prop-skill-pipeline-rnskill-docs",
        },
        "config_gates": {
            "status": config_gates.get("status"),
            "general_agent_inherits_skill_unlock": bool(
                config_gates.get("general_agent_inherits_skill_unlock")
            ),
            "privacy_rows_selectable_for_local_apply": bool(
                config_gates.get("privacy_rows_selectable_for_local_apply")
            ),
            "route_profiles_separated": bool(config_gates.get("route_profiles_separated")),
            "proposal_track": config_gates.get("proposal_track")
            or "prop-skill-pipeline-config-gates",
        },
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "supervisor_activation_allowed": False,
        "supervisor_next_action": supervisor_next_action,
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline"
        ]
        + (
            [ADJACENT_HARNESS_EVAL_VALIDATION_COMMAND]
            if selected_is_adjacent_harness
            else []
        ),
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
    }


def build_skill_route_discovery_unlocked_local_test_lane_apply(
    *,
    local_apply_completion: dict[str, Any] | None = None,
    local_apply: dict[str, Any] | None = None,
    reverse_flow_test_validation_lane: dict[str, Any] | None = None,
    local_comparison: dict[str, Any] | None = None,
    selected_step: dict[str, Any] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    theme_window: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> dict[str, Any]:
    """Apply the unlocked reverse-flow local test lane with focused validation.

    Consumes ``skill_route_discovery_local_apply_completion`` when the reverse-flow
    test lane is unlocked and packages the supervisor next action
    ``apply_unlocked_local_test_lane_with_focused_validation_and_keep_activation_external``
    into one body-free operator surface. This is local validation only: no
    external skill execution, provider launch, remote apply, push, promotion,
    kernel restart, or in-kernel activation.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    completion = local_apply_completion if isinstance(local_apply_completion, dict) else {}
    apply = local_apply if isinstance(local_apply, dict) else {}
    reverse_lane = (
        reverse_flow_test_validation_lane
        if isinstance(reverse_flow_test_validation_lane, dict)
        else {}
    )
    comparison = local_comparison if isinstance(local_comparison, dict) else {}
    selected = selected_step if isinstance(selected_step, dict) else {}
    retained = list(retained_boundaries or [])
    adjacent = list(adjacent_general_agent_rows or [])

    completion_status = str(completion.get("status") or "")
    reverse_status = str(reverse_lane.get("status") or "")
    comparison_passed = bool(
        completion.get("local_comparison_passed")
        if completion.get("local_comparison_passed") is not None
        else comparison.get("local_comparison_passed")
    )
    unlocked = [
        lane
        for lane in list(
            completion.get("unlocked_local_lanes")
            or apply.get("unlocked_local_lanes")
            or selected.get("unlocked_local_lanes")
            or []
        )
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    selected_lane = str(
        completion.get("selected_local_lane")
        or apply.get("selected_local_lane")
        or selected.get("selected_local_lane")
        or ""
    )
    selected_proposal_id = str(
        completion.get("selected_proposal_id")
        or apply.get("selected_proposal_id")
        or selected.get("proposal_id")
        or "prop-skill-reverse-flow-test-lane"
    )
    profiles = [
        str(profile)
        for profile in (
            completion.get("route_profiles")
            or apply.get("route_profiles")
            or selected.get("route_profiles")
            or []
        )
    ]
    skill_first = bool(
        completion.get("skill_route_discovery_first")
        if completion.get("skill_route_discovery_first") is not None
        else selected.get("skill_route_discovery_first")
    )
    is_reverse_flow = "codex_workflow_gate" in profiles and skill_first
    selected_route_class = str(
        completion.get("route_class")
        or apply.get("route_class")
        or selected.get("route_class")
        or "none"
    )
    selected_is_adjacent = selected_route_class == "agent_harness_eval_required"
    theme_complete = bool(completion.get("theme_complete"))
    general_agent_isolated = all(
        row.get("skill_route_discovery_inherited") is False
        and list(row.get("direct_allowed_lanes_before_eval") or []) == []
        for row in adjacent
    ) if adjacent else True
    privacy_isolated = all(
        str(row.get("route_class") or "")
        in {"privacy_boundary_review_only", "offensive_boundary_review_only"}
        for row in retained
    ) if retained else True

    apply_ready = (
        completion_status == "complete"
        and theme_complete
        and comparison_passed
        and reverse_status == "ready"
        and is_reverse_flow
        and selected_lane == "test"
        and "test" in unlocked
        and not selected_is_adjacent
        and general_agent_isolated
        and privacy_isolated
        and completion.get("runtime_action") == "none"
        and completion.get("external_skill_execution_allowed") is not True
        and completion.get("provider_launch_allowed") is not True
        and completion.get("remote_apply_allowed") is not True
        and completion.get("supervisor_activation_allowed") is not True
    )

    if selected_is_adjacent:
        status = "deferred_adjacent_harness_eval"
        decision = "selected_step_is_adjacent_agent_harness_eval_not_unlocked_test_lane_apply"
        supervisor_next_action = (
            "run_agent_harness_eval_local_comparison_for_selected_general_agent_row"
        )
    elif not selected_proposal_id or completion_status in {"", "not_applicable"}:
        status = "not_applicable"
        decision = "no_completed_reverse_flow_local_apply_for_unlocked_test_lane"
        supervisor_next_action = "wait_for_skill_route_discovery_local_apply_completion"
    elif apply_ready:
        status = "ready"
        decision = (
            "apply_unlocked_local_test_lane_with_focused_validation_and_keep_activation_external"
        )
        supervisor_next_action = (
            "run_focused_local_test_validation_then_keep_activation_external"
        )
    elif completion_status == "deferred_adjacent_harness_eval":
        status = "deferred_adjacent_harness_eval"
        decision = "completion_deferred_to_adjacent_agent_harness_eval"
        supervisor_next_action = (
            "run_agent_harness_eval_local_comparison_for_selected_general_agent_row"
        )
    elif completion_status == "blocked":
        status = "blocked_until_local_apply_completion"
        decision = "hold_unlocked_test_lane_apply_until_local_apply_completion"
        supervisor_next_action = (
            "repair_skill_route_discovery_local_apply_before_theme_completion"
        )
    else:
        status = "blocked_until_reverse_flow_test_lane_ready"
        decision = "hold_unlocked_test_lane_apply_until_reverse_flow_lane_and_completion_ready"
        supervisor_next_action = (
            "repair_skill_route_discovery_reverse_flow_test_lane_before_apply"
        )

    retained_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in retained
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
    )
    adjacent_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in adjacent
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
    )
    focused_validation_commands = [
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_unlocked_local_test_lane_apply",
        "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation",
    ]
    focused_validation_command_hashes = [
        hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
        for command in focused_validation_commands
    ]

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_unlocked_local_test_lane_apply",
        "proposal_track": "prop-skill-reverse-flow-test-lane",
        "legacy_proposal_track": "prop-skill-pipeline-reverse-flow-test",
        "companion_tracks": [
            "prop-skill-rnskill-docs-companion",
            "prop-skill-pipeline-rnskill-docs",
            "prop-skill-pipeline-config-gates",
        ],
        "proposal_id": selected_proposal_id,
        "selected_proposal_id": selected_proposal_id,
        "status": status,
        "decision": decision,
        "capability_action": "apply_one_local_skill_route_validation_candidate",
        "capability_pipeline": [
            "skill_route_discovery_capability_pipeline",
            "skill_route_discovery_local_comparison",
            "skill_route_discovery_reverse_flow_test_validation_lane",
            "skill_route_discovery_rnskill_docs_validation_lane",
            "skill_route_discovery_config_gate_boundary",
            "skill_route_discovery_local_apply",
            "skill_route_discovery_local_apply_completion",
            "skill_route_discovery_unlocked_local_test_lane_apply",
        ],
        "local_apply_completion_status": completion_status,
        "local_apply_status": str(apply.get("status") or "none"),
        "reverse_flow_test_validation_lane_status": reverse_status or "none",
        "local_comparison_passed": comparison_passed,
        "local_comparison_status": str(
            completion.get("local_comparison_status")
            or selected.get("local_comparison_status")
            or comparison.get("status")
            or ""
        ),
        "theme_complete": theme_complete,
        "route_class": selected_route_class if selected_route_class else "none",
        "route_profiles": profiles,
        "skill_route_discovery_first": skill_first,
        "selected_local_lane": selected_lane if selected_lane else "none",
        "preferred_local_lane": "test",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "unlocked_local_lanes": unlocked if status == "ready" else [],
        "focused_validation": {
            "status": "ready" if status == "ready" else status,
            "lane": "test",
            "required": True,
            "commands": focused_validation_commands if status == "ready" else [],
            "command_hashes": focused_validation_command_hashes if status == "ready" else [],
            "unit_test_signal": status == "ready",
            "coverage_required": False,
        },
        "local_validation_required": True,
        "activation_external_only": True,
        "supervisor_activation_allowed": False,
        "retained_boundary_proposal_ids": retained_ids,
        "adjacent_general_agent_proposal_ids": adjacent_ids,
        "general_agent_inherits_skill_unlock": False,
        "privacy_rows_selectable_for_local_apply": False,
        "general_agent_isolation_passed": general_agent_isolated,
        "privacy_isolation_passed": privacy_isolated,
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": str(theme.get("status") or ""),
        },
        "source_digest": source_digest or str(completion.get("source_digest") or ""),
        "supervisor_next_action": supervisor_next_action,
        "required_validation": focused_validation_commands,
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
    }


def normalize_skill_route_discovery_focused_validation_command_results(
    command_results: list[dict[str, Any]] | None = None,
    *,
    expected_command_hashes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize operator command results into body-free hash/boolean rows.

    Accepts ``command_hash`` or raw ``command`` text, but never re-exports
    command text, evidence URLs, upstream bodies, or stdout. Rows are
    ``{command_hash, passed, in_expected_set}`` only.
    """

    expected = {
        str(item).strip()
        for item in list(expected_command_hashes or [])
        if str(item).strip()
    }
    rows: list[dict[str, Any]] = []
    for raw in list(command_results or []):
        if not isinstance(raw, dict):
            continue
        command_hash = str(raw.get("command_hash") or "").strip()
        if not command_hash:
            command_text = str(raw.get("command") or "").strip()
            if command_text:
                command_hash = hashlib.sha256(command_text.encode("utf-8")).hexdigest()[:16]
        if not command_hash:
            continue
        rows.append(
            {
                "command_hash": command_hash,
                "passed": bool(raw.get("passed")),
                "in_expected_set": (command_hash in expected) if expected else True,
            }
        )
    return rows


def record_skill_route_discovery_focused_local_test_validation_results(
    pipeline: dict[str, Any],
    command_results: list[dict[str, Any]] | None = None,
    *,
    source_digest: str | None = None,
    theme_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record body-free focused validation results onto an existing pipeline.

    After supervisors run the reverse-flow focused local test commands, call this
    with command-hash/boolean rows (or raw command text + ``passed``) to close
    ``skill_route_discovery_focused_local_test_validation`` from ``ready`` to
    ``passed``/``failed`` and refresh
    ``skill_route_discovery_focused_validation_activation_external_handoff``,
    ``skill_route_discovery_focused_validation_activation_external_acceptance``,
    and ``skill_route_discovery_focused_validation_residual_adjacent_queue``
    without enabling activation, push, promotion, provider launch, remote apply,
    external skill execution, or kernel restart.
    """

    if not isinstance(pipeline, dict):
        raise TypeError("pipeline must be a dict")

    unlocked_apply = (
        pipeline.get("unlocked_local_test_lane_apply")
        if isinstance(pipeline.get("unlocked_local_test_lane_apply"), dict)
        else {}
    )
    prior_focused = (
        pipeline.get("focused_local_test_validation")
        if isinstance(pipeline.get("focused_local_test_validation"), dict)
        else {}
    )
    theme_pass = (
        pipeline.get("theme_pass") if isinstance(pipeline.get("theme_pass"), dict) else {}
    )
    theme = theme_window if isinstance(theme_window, dict) else {
        "theme_id": str(pipeline.get("theme_id") or theme_pass.get("theme_id") or "skill-route-discovery"),
        "planned_passes": int(theme_pass.get("planned_passes") or 0),
        "target_passes": int(
            theme_pass.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES
        ),
        "status": str(theme_pass.get("status") or ""),
    }
    expected_hashes = [
        str(item)
        for item in list(
            (prior_focused.get("focused_validation") or {}).get("command_hashes")
            or (unlocked_apply.get("focused_validation") or {}).get("command_hashes")
            or []
        )
        if str(item).strip()
    ]
    normalized = normalize_skill_route_discovery_focused_validation_command_results(
        command_results,
        expected_command_hashes=expected_hashes,
    )
    focused = build_skill_route_discovery_focused_local_test_validation(
        unlocked_local_test_lane_apply=unlocked_apply,
        command_results=normalized,
        theme_window=theme,
        source_digest=source_digest
        or str(prior_focused.get("source_digest") or unlocked_apply.get("source_digest") or ""),
    )
    adjacent_rows = (
        list(pipeline.get("adjacent_general_agent_rows") or [])
        if isinstance(pipeline.get("adjacent_general_agent_rows"), list)
        else []
    )
    retained_rows = (
        list(pipeline.get("retained_boundaries") or [])
        if isinstance(pipeline.get("retained_boundaries"), list)
        else []
    )
    digest = source_digest or str(
        prior_focused.get("source_digest") or unlocked_apply.get("source_digest") or ""
    )
    activation_external = build_skill_route_discovery_focused_validation_activation_external_handoff(
        focused_local_test_validation=focused,
        unlocked_local_test_lane_apply=unlocked_apply,
        adjacent_general_agent_rows=adjacent_rows,
        retained_boundaries=retained_rows,
        theme_window=theme,
        source_digest=digest,
    )
    activation_external_acceptance = (
        build_skill_route_discovery_focused_validation_activation_external_acceptance(
            focused_validation_activation_external_handoff=activation_external,
            focused_local_test_validation=focused,
            unlocked_local_test_lane_apply=unlocked_apply,
            adjacent_general_agent_rows=adjacent_rows,
            retained_boundaries=retained_rows,
            theme_window=theme,
            source_digest=digest,
        )
    )
    residual_adjacent_queue = (
        build_skill_route_discovery_focused_validation_residual_adjacent_queue(
            focused_validation_activation_external_acceptance=(
                activation_external_acceptance
            ),
            focused_validation_activation_external_handoff=activation_external,
            focused_local_test_validation=focused,
            adjacent_general_agent_rows=adjacent_rows,
            retained_boundaries=retained_rows,
            theme_window=theme,
            source_digest=digest,
        )
    )
    updated = dict(pipeline)
    updated["focused_local_test_validation"] = focused
    updated["focused_local_test_validation_recorded"] = focused.get("status") in {
        "passed",
        "failed",
    }
    updated["focused_validation_activation_external_handoff"] = activation_external
    updated["focused_validation_activation_external_acceptance"] = (
        activation_external_acceptance
    )
    updated["focused_validation_residual_adjacent_queue"] = residual_adjacent_queue
    return updated


def build_skill_route_discovery_focused_validation_body_free_command_results(
    focused_local_test_validation: dict[str, Any] | None = None,
    *,
    passed: bool,
    command_hashes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Materialize body-free expected-hash result rows for focused validation.

    Supervisors that already know the reverse-flow focused commands passed or
    failed can build ``{command_hash, passed, in_expected_set}`` rows covering
    the expected hash set without re-exporting command text, stdout, evidence
    URLs, or upstream bodies.
    """

    focused = (
        focused_local_test_validation
        if isinstance(focused_local_test_validation, dict)
        else {}
    )
    focused_validation = (
        focused.get("focused_validation")
        if isinstance(focused.get("focused_validation"), dict)
        else {}
    )
    hashes = [
        str(item).strip()
        for item in list(
            command_hashes
            or focused_validation.get("command_hashes")
            or focused.get("required_validation")
            or []
        )
        if str(item).strip()
    ]
    # If callers supplied raw commands instead of hashes, hash them body-free.
    if hashes and any(" " in item or item.startswith("pytest") for item in hashes):
        hashes = [
            hashlib.sha256(item.encode("utf-8")).hexdigest()[:16]
            if (" " in item or item.startswith("pytest"))
            else item
            for item in hashes
        ]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in hashes:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return [
        {
            "command_hash": command_hash,
            "passed": bool(passed),
            "in_expected_set": True,
        }
        for command_hash in ordered
    ]


def close_skill_route_discovery_focused_local_test_validation_with_outcome(
    pipeline: dict[str, Any],
    *,
    passed: bool,
    source_digest: str | None = None,
    theme_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close ready focused validation with a body-free pass/fail outcome.

    Materializes expected command-hash rows, records them onto the pipeline,
    refreshes ``skill_route_discovery_focused_validation_activation_external_handoff``,
    and packages
    ``skill_route_discovery_focused_validation_activation_external_acceptance``
    when the handoff is ready after a recorded pass. Never enables activation,
    push, promotion, provider launch, remote apply, external skill execution, or
    kernel restart.
    """

    if not isinstance(pipeline, dict):
        raise TypeError("pipeline must be a dict")

    prior_focused = (
        pipeline.get("focused_local_test_validation")
        if isinstance(pipeline.get("focused_local_test_validation"), dict)
        else {}
    )
    command_results = build_skill_route_discovery_focused_validation_body_free_command_results(
        prior_focused,
        passed=passed,
    )
    return record_skill_route_discovery_focused_local_test_validation_results(
        pipeline,
        command_results,
        source_digest=source_digest,
        theme_window=theme_window,
    )


def build_skill_route_discovery_focused_local_test_validation(
    *,
    unlocked_local_test_lane_apply: dict[str, Any] | None = None,
    command_results: list[dict[str, Any]] | None = None,
    theme_window: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> dict[str, Any]:
    """Record body-free focused local test validation for the unlocked reverse-flow lane.

    Consumes a ready ``skill_route_discovery_unlocked_local_test_lane_apply`` packet
    and packages the supervisor next action
    ``run_focused_local_test_validation_then_keep_activation_external`` into one
    operator-visible result surface. Commands are exported as hashes only (no raw
    evidence URLs or upstream bodies). Optional ``command_results`` rows
    (``command_hash`` + ``passed``) mark the validation ``passed`` or ``failed``.
    Activation, push, promotion, provider launch, remote apply, external skill
    execution, and kernel restart stay denied; activation remains external.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    unlocked_apply = (
        unlocked_local_test_lane_apply
        if isinstance(unlocked_local_test_lane_apply, dict)
        else {}
    )
    unlocked_status = str(unlocked_apply.get("status") or "")
    selected_proposal_id = str(
        unlocked_apply.get("selected_proposal_id")
        or unlocked_apply.get("proposal_id")
        or "prop-skill-reverse-flow-test-lane"
    )
    selected_lane = str(unlocked_apply.get("selected_local_lane") or "")
    unlocked_lanes = [
        lane
        for lane in list(unlocked_apply.get("unlocked_local_lanes") or [])
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    profiles = [str(profile) for profile in list(unlocked_apply.get("route_profiles") or [])]
    skill_first = bool(unlocked_apply.get("skill_route_discovery_first"))
    is_reverse_flow = "codex_workflow_gate" in profiles and skill_first
    focused = (
        unlocked_apply.get("focused_validation")
        if isinstance(unlocked_apply.get("focused_validation"), dict)
        else {}
    )
    commands = [
        str(cmd)
        for cmd in list(
            focused.get("commands") or unlocked_apply.get("required_validation") or []
        )
        if str(cmd).strip()
    ]
    command_hashes = [
        str(item)
        for item in list(focused.get("command_hashes") or [])
        if str(item).strip()
    ]
    if not command_hashes and commands:
        command_hashes = [
            hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]
            for command in commands
        ]
    expected_hash_set = set(command_hashes)

    result_rows = normalize_skill_route_discovery_focused_validation_command_results(
        command_results,
        expected_command_hashes=command_hashes,
    )

    results_cover_expected = bool(expected_hash_set) and expected_hash_set.issubset(
        {row["command_hash"] for row in result_rows}
    )
    all_expected_passed = results_cover_expected and all(
        row["passed"] for row in result_rows if row["command_hash"] in expected_hash_set
    )
    any_expected_failed = any(
        (not row["passed"]) and row["command_hash"] in expected_hash_set
        for row in result_rows
    ) if result_rows else False

    apply_ready = (
        unlocked_status == "ready"
        and is_reverse_flow
        and selected_lane == "test"
        and "test" in unlocked_lanes
        and bool(unlocked_apply.get("activation_external_only", True))
        and unlocked_apply.get("supervisor_activation_allowed") is not True
        and unlocked_apply.get("runtime_action") == "none"
        and unlocked_apply.get("external_skill_execution_allowed") is not True
        and unlocked_apply.get("provider_launch_allowed") is not True
        and unlocked_apply.get("remote_apply_allowed") is not True
        and unlocked_apply.get("body_free") is not False
    )

    if unlocked_status in {"", "not_applicable"}:
        status = "not_applicable"
        decision = "no_unlocked_local_test_lane_apply_for_focused_validation"
        supervisor_next_action = "wait_for_skill_route_discovery_unlocked_local_test_lane_apply"
    elif unlocked_status.startswith("blocked") or unlocked_status == "deferred_adjacent_harness_eval":
        status = "blocked_until_unlocked_local_test_lane_apply"
        decision = "hold_focused_local_test_validation_until_unlocked_apply_ready"
        supervisor_next_action = "repair_skill_route_discovery_unlocked_local_test_lane_apply"
    elif not apply_ready:
        status = "blocked_until_unlocked_local_test_lane_apply"
        decision = "hold_focused_local_test_validation_until_reverse_flow_test_lane_unlocked"
        supervisor_next_action = "repair_skill_route_discovery_unlocked_local_test_lane_apply"
    elif any_expected_failed:
        status = "failed"
        decision = "repair_focused_local_test_validation_before_activation_review"
        supervisor_next_action = "repair_failed_focused_local_test_validation_commands"
    elif all_expected_passed:
        status = "passed"
        decision = "record_focused_local_test_validation_pass_and_keep_activation_external"
        supervisor_next_action = "keep_activation_external_after_focused_local_test_validation"
    else:
        status = "ready"
        decision = "run_focused_local_test_validation_with_body_free_command_hashes"
        supervisor_next_action = "run_focused_local_test_validation_then_keep_activation_external"

    export_commands = commands if status in {"ready", "passed", "failed"} else []
    export_hashes = command_hashes if status in {"ready", "passed", "failed"} else []
    export_results = result_rows if status in {"passed", "failed"} else []
    recorded = status in {"passed", "failed"}

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_focused_local_test_validation",
        "proposal_track": "prop-skill-reverse-flow-focused-test-validation",
        "legacy_proposal_track": "prop-skill-reverse-flow-test-lane",
        "companion_tracks": [
            "prop-skill-reverse-flow-test-lane",
            "prop-skill-rnskill-docs-companion",
            "prop-skill-pipeline-rnskill-docs",
            "prop-skill-pipeline-config-gates",
        ],
        "proposal_id": selected_proposal_id,
        "selected_proposal_id": selected_proposal_id,
        "status": status,
        "decision": decision,
        "capability_action": "apply_one_local_skill_route_validation_candidate",
        "capability_pipeline": [
            "skill_route_discovery_capability_pipeline",
            "skill_route_discovery_local_comparison",
            "skill_route_discovery_reverse_flow_test_validation_lane",
            "skill_route_discovery_rnskill_docs_validation_lane",
            "skill_route_discovery_config_gate_boundary",
            "skill_route_discovery_local_apply",
            "skill_route_discovery_local_apply_completion",
            "skill_route_discovery_unlocked_local_test_lane_apply",
            "skill_route_discovery_focused_local_test_validation",
            "record_skill_route_discovery_focused_local_test_validation_results",
            "close_skill_route_discovery_focused_local_test_validation_with_outcome",
            "skill_route_discovery_focused_validation_activation_external_handoff",
            "skill_route_discovery_focused_validation_activation_external_acceptance",
            "skill_route_discovery_focused_validation_residual_adjacent_queue",
        ],
        "unlocked_local_test_lane_apply_status": unlocked_status or "none",
        "unlocked_local_test_lane_apply_decision": str(unlocked_apply.get("decision") or ""),
        "local_apply_completion_status": str(
            unlocked_apply.get("local_apply_completion_status") or "none"
        ),
        "reverse_flow_test_validation_lane_status": str(
            unlocked_apply.get("reverse_flow_test_validation_lane_status") or "none"
        ),
        "local_comparison_passed": bool(unlocked_apply.get("local_comparison_passed")),
        "theme_complete": bool(unlocked_apply.get("theme_complete")),
        "route_class": str(unlocked_apply.get("route_class") or "none"),
        "route_profiles": profiles,
        "skill_route_discovery_first": skill_first,
        "selected_local_lane": selected_lane if selected_lane else "none",
        "preferred_local_lane": "test",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "unlocked_local_lanes": unlocked_lanes if status in {"ready", "passed", "failed"} else [],
        "focused_validation": {
            "status": status,
            "lane": "test",
            "required": True,
            "commands": export_commands,
            "command_hashes": export_hashes,
            "command_results": export_results,
            "expected_command_count": len(export_hashes),
            "recorded_result_count": len(export_results),
            "unit_test_signal": status in {"ready", "passed", "failed"},
            "coverage_required": False,
            "results_cover_expected": results_cover_expected if export_results else False,
            "all_expected_passed": all_expected_passed if export_results else False,
            "recorded": recorded,
        },
        "local_validation_required": True,
        "activation_external_only": True,
        "supervisor_activation_allowed": False,
        "retained_boundary_proposal_ids": list(
            unlocked_apply.get("retained_boundary_proposal_ids") or []
        ),
        "adjacent_general_agent_proposal_ids": list(
            unlocked_apply.get("adjacent_general_agent_proposal_ids") or []
        ),
        "general_agent_inherits_skill_unlock": False,
        "privacy_rows_selectable_for_local_apply": False,
        "general_agent_isolation_passed": bool(
            unlocked_apply.get("general_agent_isolation_passed", True)
        ),
        "privacy_isolation_passed": bool(unlocked_apply.get("privacy_isolation_passed", True)),
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "theme_id": str(theme.get("theme_id") or unlocked_apply.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(
                theme.get("planned_passes")
                or (unlocked_apply.get("theme_pass") or {}).get("planned_passes")
                or 0
            ),
            "target_passes": int(
                theme.get("target_passes")
                or (unlocked_apply.get("theme_pass") or {}).get("target_passes")
                or DEFAULT_THEME_WINDOW_TARGET_PASSES
            ),
            "status": str(
                theme.get("status")
                or (unlocked_apply.get("theme_pass") or {}).get("status")
                or ""
            ),
        },
        "source_digest": source_digest
        or str(unlocked_apply.get("source_digest") or ""),
        "supervisor_next_action": supervisor_next_action,
        "required_validation": export_commands,
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "raw_command_stdout_exported": False,
        "focused_validation_recorded": recorded,
    }


def build_skill_route_discovery_focused_validation_activation_external_handoff(
    *,
    focused_local_test_validation: dict[str, Any] | None = None,
    unlocked_local_test_lane_apply: dict[str, Any] | None = None,
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
    theme_window: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> dict[str, Any]:
    """Package activation-external handoff after reverse-flow focused validation.

    After supervisors record body-free command-hash results on
    ``skill_route_discovery_focused_local_test_validation``, this surface turns
    ``keep_activation_external_after_focused_local_test_validation`` into one
    operator-visible packet. A recorded pass keeps activation, push, promotion,
    provider launch, remote apply, external skill execution, and kernel restart
    denied. Residual fortress-style adjacent rows stay noted without inheriting
    skill unlocks. Failed or unrecorded focused validation blocks the handoff.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    focused = (
        focused_local_test_validation
        if isinstance(focused_local_test_validation, dict)
        else {}
    )
    unlocked_apply = (
        unlocked_local_test_lane_apply
        if isinstance(unlocked_local_test_lane_apply, dict)
        else {}
    )
    adjacent = list(adjacent_general_agent_rows or [])
    retained = list(retained_boundaries or [])
    focused_status = str(focused.get("status") or "")
    focused_validation = (
        focused.get("focused_validation")
        if isinstance(focused.get("focused_validation"), dict)
        else {}
    )
    recorded = bool(
        focused.get("focused_validation_recorded")
        or focused_validation.get("recorded")
        or focused_status in {"passed", "failed"}
    )
    results_cover_expected = bool(focused_validation.get("results_cover_expected"))
    all_expected_passed = bool(focused_validation.get("all_expected_passed"))
    selected_proposal_id = str(
        focused.get("selected_proposal_id")
        or focused.get("proposal_id")
        or unlocked_apply.get("selected_proposal_id")
        or unlocked_apply.get("proposal_id")
        or "prop-skill-reverse-flow-focused-test-validation"
    )
    profiles = [
        str(profile)
        for profile in list(
            focused.get("route_profiles") or unlocked_apply.get("route_profiles") or []
        )
    ]
    skill_first = bool(
        focused.get("skill_route_discovery_first", unlocked_apply.get("skill_route_discovery_first"))
    )
    selected_lane = str(
        focused.get("selected_local_lane") or unlocked_apply.get("selected_local_lane") or ""
    )
    unlocked_lanes = [
        lane
        for lane in list(
            focused.get("unlocked_local_lanes")
            or unlocked_apply.get("unlocked_local_lanes")
            or []
        )
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    retained_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in retained
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
        | {
            str(item)
            for item in list(focused.get("retained_boundary_proposal_ids") or [])
            if str(item).strip()
        }
    )
    adjacent_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in adjacent
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
        | {
            str(item)
            for item in list(focused.get("adjacent_general_agent_proposal_ids") or [])
            if str(item).strip()
        }
    )
    residual_adjacent_available = bool(adjacent_ids)
    result_rows = [
        row
        for row in list(focused_validation.get("command_results") or [])
        if isinstance(row, dict)
    ]
    body_free_results = all(
        set(row.keys()) <= {"command_hash", "passed", "in_expected_set"} for row in result_rows
    ) if result_rows else True
    command_hashes = [
        str(item)
        for item in list(focused_validation.get("command_hashes") or [])
        if str(item).strip()
    ]

    if focused_status in {"", "not_applicable"}:
        status = "not_applicable"
        decision = "no_focused_local_test_validation_for_activation_external_handoff"
        supervisor_next_action = "wait_for_skill_route_discovery_focused_local_test_validation"
    elif focused_status.startswith("blocked"):
        status = "blocked_until_focused_validation_ready"
        decision = "hold_activation_external_handoff_until_focused_validation_ready"
        supervisor_next_action = "repair_skill_route_discovery_focused_local_test_validation"
    elif focused_status == "ready" or not recorded:
        status = "blocked_until_focused_validation_recorded"
        decision = "hold_activation_external_handoff_until_command_hash_results_recorded"
        supervisor_next_action = "run_focused_local_test_validation_then_keep_activation_external"
    elif focused_status == "failed" or (recorded and not all_expected_passed):
        status = "blocked_until_focused_validation_repaired"
        decision = "hold_activation_external_handoff_until_focused_validation_pass"
        supervisor_next_action = "repair_failed_focused_local_test_validation_commands"
    elif (
        focused_status == "passed"
        and recorded
        and results_cover_expected
        and all_expected_passed
        and body_free_results
        and bool(focused.get("activation_external_only", True))
        and focused.get("supervisor_activation_allowed") is not True
        and focused.get("runtime_action") == "none"
        and focused.get("external_skill_execution_allowed") is not True
        and focused.get("provider_launch_allowed") is not True
        and focused.get("remote_apply_allowed") is not True
        and focused.get("push_or_promotion_allowed") is not True
        and focused.get("kernel_restart_allowed") is not True
    ):
        status = "ready"
        decision = "package_activation_external_handoff_after_focused_validation_pass"
        supervisor_next_action = (
            "keep_activation_external_after_focused_local_test_validation"
        )
    else:
        status = "blocked_until_focused_validation_pass"
        decision = "hold_activation_external_handoff_until_body_free_pass_recorded"
        supervisor_next_action = "run_focused_local_test_validation_then_keep_activation_external"

    export_hashes = command_hashes if status in {"ready", "blocked_until_focused_validation_repaired"} else []
    export_results = result_rows if status in {"ready", "blocked_until_focused_validation_repaired"} else []

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_focused_validation_activation_external_handoff",
        "proposal_track": "prop-skill-reverse-flow-focused-test-validation",
        "legacy_proposal_track": "prop-skill-reverse-flow-test-lane",
        "companion_tracks": [
            "prop-skill-reverse-flow-focused-test-validation",
            "prop-skill-reverse-flow-test-lane",
            "prop-skill-rnskill-docs-companion",
            "prop-skill-pipeline-config-gates",
        ],
        "proposal_id": selected_proposal_id,
        "selected_proposal_id": selected_proposal_id,
        "status": status,
        "decision": decision,
        "capability_action": "apply_one_local_skill_route_validation_candidate",
        "capability_pipeline": [
            "skill_route_discovery_capability_pipeline",
            "skill_route_discovery_local_comparison",
            "skill_route_discovery_reverse_flow_test_validation_lane",
            "skill_route_discovery_rnskill_docs_validation_lane",
            "skill_route_discovery_config_gate_boundary",
            "skill_route_discovery_local_apply",
            "skill_route_discovery_local_apply_completion",
            "skill_route_discovery_unlocked_local_test_lane_apply",
            "skill_route_discovery_focused_local_test_validation",
            "record_skill_route_discovery_focused_local_test_validation_results",
            "close_skill_route_discovery_focused_local_test_validation_with_outcome",
            "skill_route_discovery_focused_validation_activation_external_handoff",
            "skill_route_discovery_focused_validation_activation_external_acceptance",
            "skill_route_discovery_focused_validation_residual_adjacent_queue",
        ],
        "focused_local_test_validation_status": focused_status or "none",
        "focused_local_test_validation_decision": str(focused.get("decision") or ""),
        "focused_local_test_validation_recorded": recorded,
        "focused_validation_results_cover_expected": results_cover_expected if recorded else False,
        "focused_validation_all_expected_passed": all_expected_passed if recorded else False,
        "unlocked_local_test_lane_apply_status": str(unlocked_apply.get("status") or "none"),
        "local_apply_completion_status": str(
            focused.get("local_apply_completion_status")
            or unlocked_apply.get("local_apply_completion_status")
            or "none"
        ),
        "reverse_flow_test_validation_lane_status": str(
            focused.get("reverse_flow_test_validation_lane_status")
            or unlocked_apply.get("reverse_flow_test_validation_lane_status")
            or "none"
        ),
        "local_comparison_passed": bool(
            focused.get("local_comparison_passed", unlocked_apply.get("local_comparison_passed"))
        ),
        "theme_complete": bool(
            focused.get("theme_complete", unlocked_apply.get("theme_complete"))
        ),
        "route_class": str(focused.get("route_class") or unlocked_apply.get("route_class") or "none"),
        "route_profiles": profiles,
        "skill_route_discovery_first": skill_first,
        "selected_local_lane": selected_lane if selected_lane else "none",
        "preferred_local_lane": "test",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "unlocked_local_lanes": unlocked_lanes if status == "ready" else [],
        "focused_validation": {
            "status": focused_status or "none",
            "lane": "test",
            "required": True,
            "command_hashes": export_hashes,
            "command_results": export_results,
            "expected_command_count": len(export_hashes),
            "recorded_result_count": len(export_results),
            "results_cover_expected": results_cover_expected if recorded else False,
            "all_expected_passed": all_expected_passed if recorded else False,
            "recorded": recorded,
            "body_free": body_free_results,
            # Commands intentionally omitted: activation-external handoff is hash-only.
            "commands_exported": False,
        },
        "local_validation_required": True,
        "activation_external_only": True,
        "supervisor_activation_allowed": False,
        "retained_boundary_proposal_ids": retained_ids,
        "adjacent_general_agent_proposal_ids": adjacent_ids,
        "residual_adjacent_harness_eval_available": residual_adjacent_available,
        "residual_adjacent_handoff_surface": (
            "agent_harness_eval_cluster_local_apply" if residual_adjacent_available else "none"
        ),
        "general_agent_inherits_skill_unlock": False,
        "privacy_rows_selectable_for_local_apply": False,
        "general_agent_isolation_passed": bool(
            focused.get("general_agent_isolation_passed", True)
        ),
        "privacy_isolation_passed": bool(focused.get("privacy_isolation_passed", True)),
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "theme_id": str(
            theme.get("theme_id")
            or focused.get("theme_id")
            or unlocked_apply.get("theme_id")
            or "skill-route-discovery"
        ),
        "theme_pass": {
            "planned_passes": int(
                theme.get("planned_passes")
                or (focused.get("theme_pass") or {}).get("planned_passes")
                or (unlocked_apply.get("theme_pass") or {}).get("planned_passes")
                or 0
            ),
            "target_passes": int(
                theme.get("target_passes")
                or (focused.get("theme_pass") or {}).get("target_passes")
                or (unlocked_apply.get("theme_pass") or {}).get("target_passes")
                or DEFAULT_THEME_WINDOW_TARGET_PASSES
            ),
            "status": str(
                theme.get("status")
                or (focused.get("theme_pass") or {}).get("status")
                or (unlocked_apply.get("theme_pass") or {}).get("status")
                or ""
            ),
        },
        "source_digest": source_digest
        or str(focused.get("source_digest") or unlocked_apply.get("source_digest") or ""),
        "supervisor_next_action": supervisor_next_action,
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation",
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_validation_activation_external",
        ],
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "raw_command_stdout_exported": False,
        "raw_command_text_exported": False,
    }


def build_skill_route_discovery_focused_validation_activation_external_acceptance(
    *,
    focused_validation_activation_external_handoff: dict[str, Any] | None = None,
    focused_local_test_validation: dict[str, Any] | None = None,
    unlocked_local_test_lane_apply: dict[str, Any] | None = None,
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
    theme_window: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> dict[str, Any]:
    """Accept a ready activation-external handoff as the terminal reverse-flow package.

    After ``skill_route_discovery_focused_validation_activation_external_handoff``
    is ``ready`` from a recorded focused validation pass, this surface packages
    operator acceptance of
    ``keep_activation_external_after_focused_local_test_validation`` without
    enabling push, promotion, provider launch, remote apply, external skill
    execution, or kernel restart. Residual fortress/Hy3 adjacent rows may be
    noted for ``agent_harness_eval_cluster_local_apply`` without skill unlock
    inheritance.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    handoff = (
        focused_validation_activation_external_handoff
        if isinstance(focused_validation_activation_external_handoff, dict)
        else {}
    )
    focused = (
        focused_local_test_validation
        if isinstance(focused_local_test_validation, dict)
        else {}
    )
    unlocked_apply = (
        unlocked_local_test_lane_apply
        if isinstance(unlocked_local_test_lane_apply, dict)
        else {}
    )
    adjacent = list(adjacent_general_agent_rows or [])
    retained = list(retained_boundaries or [])
    handoff_status = str(handoff.get("status") or "")
    focused_status = str(focused.get("status") or handoff.get("focused_local_test_validation_status") or "")
    focused_validation = (
        focused.get("focused_validation")
        if isinstance(focused.get("focused_validation"), dict)
        else (
            handoff.get("focused_validation")
            if isinstance(handoff.get("focused_validation"), dict)
            else {}
        )
    )
    recorded = bool(
        focused.get("focused_validation_recorded")
        or focused_validation.get("recorded")
        or handoff.get("focused_local_test_validation_recorded")
        or focused_status in {"passed", "failed"}
    )
    results_cover_expected = bool(
        focused_validation.get("results_cover_expected")
        or handoff.get("focused_validation_results_cover_expected")
    )
    all_expected_passed = bool(
        focused_validation.get("all_expected_passed")
        or handoff.get("focused_validation_all_expected_passed")
    )
    selected_proposal_id = str(
        handoff.get("selected_proposal_id")
        or handoff.get("proposal_id")
        or focused.get("selected_proposal_id")
        or focused.get("proposal_id")
        or "prop-skill-reverse-flow-focused-test-validation"
    )
    profiles = [
        str(profile)
        for profile in list(
            handoff.get("route_profiles")
            or focused.get("route_profiles")
            or unlocked_apply.get("route_profiles")
            or []
        )
    ]
    skill_first = bool(
        handoff.get(
            "skill_route_discovery_first",
            focused.get(
                "skill_route_discovery_first",
                unlocked_apply.get("skill_route_discovery_first"),
            ),
        )
    )
    selected_lane = str(
        handoff.get("selected_local_lane")
        or focused.get("selected_local_lane")
        or unlocked_apply.get("selected_local_lane")
        or ""
    )
    unlocked_lanes = [
        lane
        for lane in list(
            handoff.get("unlocked_local_lanes")
            or focused.get("unlocked_local_lanes")
            or unlocked_apply.get("unlocked_local_lanes")
            or []
        )
        if lane in SKILL_ROUTE_DISCOVERY_ALLOWED_LANES
    ]
    retained_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in retained
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
        | {
            str(item)
            for item in list(
                handoff.get("retained_boundary_proposal_ids")
                or focused.get("retained_boundary_proposal_ids")
                or []
            )
            if str(item).strip()
        }
    )
    adjacent_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in adjacent
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
        | {
            str(item)
            for item in list(
                handoff.get("adjacent_general_agent_proposal_ids")
                or focused.get("adjacent_general_agent_proposal_ids")
                or []
            )
            if str(item).strip()
        }
    )
    residual_adjacent_available = bool(adjacent_ids) or bool(
        handoff.get("residual_adjacent_harness_eval_available")
    )
    command_hashes = [
        str(item)
        for item in list(focused_validation.get("command_hashes") or [])
        if str(item).strip()
    ]
    result_rows = [
        row
        for row in list(focused_validation.get("command_results") or [])
        if isinstance(row, dict)
    ]
    body_free_results = (
        all(set(row.keys()) <= {"command_hash", "passed", "in_expected_set"} for row in result_rows)
        if result_rows
        else True
    )

    handoff_ready = (
        handoff_status == "ready"
        and str(handoff.get("decision") or "")
        == "package_activation_external_handoff_after_focused_validation_pass"
        and bool(handoff.get("activation_external_only", True))
        and handoff.get("supervisor_activation_allowed") is not True
        and handoff.get("runtime_action") == "none"
        and handoff.get("external_skill_execution_allowed") is not True
        and handoff.get("provider_launch_allowed") is not True
        and handoff.get("remote_apply_allowed") is not True
        and handoff.get("push_or_promotion_allowed") is not True
        and handoff.get("kernel_restart_allowed") is not True
        and focused_status == "passed"
        and recorded
        and results_cover_expected
        and all_expected_passed
        and body_free_results
    )

    if handoff_status in {"", "not_applicable"}:
        status = "not_applicable"
        decision = "no_activation_external_handoff_for_acceptance"
        supervisor_next_action = (
            "wait_for_skill_route_discovery_focused_validation_activation_external_handoff"
        )
    elif handoff_status.startswith("blocked"):
        status = "blocked_until_activation_external_handoff_ready"
        decision = "hold_activation_external_acceptance_until_handoff_ready"
        if handoff_status == "blocked_until_focused_validation_recorded":
            supervisor_next_action = (
                "run_focused_local_test_validation_then_keep_activation_external"
            )
        elif handoff_status == "blocked_until_focused_validation_repaired":
            supervisor_next_action = "repair_failed_focused_local_test_validation_commands"
        else:
            supervisor_next_action = (
                "repair_skill_route_discovery_focused_validation_activation_external_handoff"
            )
    elif handoff_ready:
        status = "accepted"
        decision = "accept_activation_external_package_after_focused_validation_pass"
        if residual_adjacent_available:
            supervisor_next_action = (
                "keep_activation_external_and_queue_residual_adjacent_harness_eval"
            )
        else:
            supervisor_next_action = (
                "keep_activation_external_after_focused_local_test_validation"
            )
    else:
        status = "blocked_until_activation_external_handoff_ready"
        decision = "hold_activation_external_acceptance_until_body_free_pass_handoff"
        supervisor_next_action = (
            "run_focused_local_test_validation_then_keep_activation_external"
        )

    export_hashes = command_hashes if status == "accepted" else []
    export_results = result_rows if status == "accepted" else []

    return {
        "schema_version": 1,
        "controller_surface": (
            "skill_route_discovery_focused_validation_activation_external_acceptance"
        ),
        "proposal_track": "prop-skill-reverse-flow-focused-test-validation",
        "legacy_proposal_track": "prop-skill-reverse-flow-test-lane",
        "companion_tracks": [
            "prop-skill-reverse-flow-focused-test-validation",
            "prop-skill-reverse-flow-test-lane",
            "prop-skill-rnskill-docs-companion",
            "prop-skill-pipeline-config-gates",
        ],
        "proposal_id": selected_proposal_id,
        "selected_proposal_id": selected_proposal_id,
        "status": status,
        "decision": decision,
        "capability_action": "apply_one_local_skill_route_validation_candidate",
        "capability_pipeline": [
            "skill_route_discovery_capability_pipeline",
            "skill_route_discovery_local_comparison",
            "skill_route_discovery_reverse_flow_test_validation_lane",
            "skill_route_discovery_rnskill_docs_validation_lane",
            "skill_route_discovery_config_gate_boundary",
            "skill_route_discovery_local_apply",
            "skill_route_discovery_local_apply_completion",
            "skill_route_discovery_unlocked_local_test_lane_apply",
            "skill_route_discovery_focused_local_test_validation",
            "record_skill_route_discovery_focused_local_test_validation_results",
            "close_skill_route_discovery_focused_local_test_validation_with_outcome",
            "skill_route_discovery_focused_validation_activation_external_handoff",
            "skill_route_discovery_focused_validation_activation_external_acceptance",
            "skill_route_discovery_focused_validation_residual_adjacent_queue",
        ],
        "focused_validation_activation_external_handoff_status": handoff_status or "none",
        "focused_validation_activation_external_handoff_decision": str(
            handoff.get("decision") or ""
        ),
        "focused_local_test_validation_status": focused_status or "none",
        "focused_local_test_validation_recorded": recorded,
        "focused_validation_results_cover_expected": (
            results_cover_expected if recorded else False
        ),
        "focused_validation_all_expected_passed": (
            all_expected_passed if recorded else False
        ),
        "unlocked_local_test_lane_apply_status": str(
            unlocked_apply.get("status")
            or handoff.get("unlocked_local_test_lane_apply_status")
            or "none"
        ),
        "local_apply_completion_status": str(
            focused.get("local_apply_completion_status")
            or unlocked_apply.get("local_apply_completion_status")
            or handoff.get("local_apply_completion_status")
            or "none"
        ),
        "reverse_flow_test_validation_lane_status": str(
            focused.get("reverse_flow_test_validation_lane_status")
            or unlocked_apply.get("reverse_flow_test_validation_lane_status")
            or handoff.get("reverse_flow_test_validation_lane_status")
            or "none"
        ),
        "local_comparison_passed": bool(
            focused.get(
                "local_comparison_passed",
                unlocked_apply.get(
                    "local_comparison_passed",
                    handoff.get("local_comparison_passed"),
                ),
            )
        ),
        "theme_complete": bool(
            focused.get(
                "theme_complete",
                unlocked_apply.get("theme_complete", handoff.get("theme_complete")),
            )
        ),
        "route_class": str(
            focused.get("route_class")
            or unlocked_apply.get("route_class")
            or handoff.get("route_class")
            or "none"
        ),
        "route_profiles": profiles,
        "skill_route_discovery_first": skill_first,
        "selected_local_lane": selected_lane if selected_lane else "none",
        "preferred_local_lane": "test",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        "unlocked_local_lanes": unlocked_lanes if status == "accepted" else [],
        "focused_validation": {
            "status": focused_status or "none",
            "lane": "test",
            "required": True,
            "command_hashes": export_hashes,
            "command_results": export_results,
            "expected_command_count": len(export_hashes),
            "recorded_result_count": len(export_results),
            "results_cover_expected": results_cover_expected if recorded else False,
            "all_expected_passed": all_expected_passed if recorded else False,
            "recorded": recorded,
            "body_free": body_free_results,
            "commands_exported": False,
        },
        "local_validation_required": True,
        "activation_external_only": True,
        "supervisor_activation_allowed": False,
        "retained_boundary_proposal_ids": retained_ids,
        "adjacent_general_agent_proposal_ids": adjacent_ids,
        "residual_adjacent_harness_eval_available": residual_adjacent_available,
        "residual_adjacent_handoff_surface": (
            "agent_harness_eval_cluster_local_apply" if residual_adjacent_available else "none"
        ),
        "general_agent_inherits_skill_unlock": False,
        "privacy_rows_selectable_for_local_apply": False,
        "general_agent_isolation_passed": bool(
            focused.get(
                "general_agent_isolation_passed",
                handoff.get("general_agent_isolation_passed", True),
            )
        ),
        "privacy_isolation_passed": bool(
            focused.get(
                "privacy_isolation_passed",
                handoff.get("privacy_isolation_passed", True),
            )
        ),
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "theme_id": str(
            theme.get("theme_id")
            or handoff.get("theme_id")
            or focused.get("theme_id")
            or unlocked_apply.get("theme_id")
            or "skill-route-discovery"
        ),
        "theme_pass": {
            "planned_passes": int(
                theme.get("planned_passes")
                or (handoff.get("theme_pass") or {}).get("planned_passes")
                or (focused.get("theme_pass") or {}).get("planned_passes")
                or (unlocked_apply.get("theme_pass") or {}).get("planned_passes")
                or 0
            ),
            "target_passes": int(
                theme.get("target_passes")
                or (handoff.get("theme_pass") or {}).get("target_passes")
                or (focused.get("theme_pass") or {}).get("target_passes")
                or (unlocked_apply.get("theme_pass") or {}).get("target_passes")
                or DEFAULT_THEME_WINDOW_TARGET_PASSES
            ),
            "status": str(
                theme.get("status")
                or (handoff.get("theme_pass") or {}).get("status")
                or (focused.get("theme_pass") or {}).get("status")
                or (unlocked_apply.get("theme_pass") or {}).get("status")
                or ""
            ),
        },
        "source_digest": source_digest
        or str(
            handoff.get("source_digest")
            or focused.get("source_digest")
            or unlocked_apply.get("source_digest")
            or ""
        ),
        "supervisor_next_action": supervisor_next_action,
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation",
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_validation_activation_external",
        ],
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "raw_command_stdout_exported": False,
        "raw_command_text_exported": False,
    }


def build_skill_route_discovery_focused_validation_residual_adjacent_queue(
    *,
    focused_validation_activation_external_acceptance: dict[str, Any] | None = None,
    focused_validation_activation_external_handoff: dict[str, Any] | None = None,
    focused_local_test_validation: dict[str, Any] | None = None,
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
    theme_window: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> dict[str, Any]:
    """Queue residual fortress/Hy3 rows after reverse-flow activation-external acceptance.

    After ``skill_route_discovery_focused_validation_activation_external_acceptance``
    is ``accepted``, residual adjacent general-agent proposal IDs are packaged for
    ``agent_harness_eval_cluster_local_apply`` without inheriting reverse-flow skill
    unlocks. This is distinct from
    ``skill_route_discovery_adjacent_harness_eval_handoff``, which fires only when
    the selected pipeline step is itself an adjacent harness-eval row. Push,
    promotion, provider launch, remote apply, external skill execution, and kernel
    restart stay denied; activation remains external. Privacy/offensive rows stay
    review-only.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    acceptance = (
        focused_validation_activation_external_acceptance
        if isinstance(focused_validation_activation_external_acceptance, dict)
        else {}
    )
    handoff = (
        focused_validation_activation_external_handoff
        if isinstance(focused_validation_activation_external_handoff, dict)
        else {}
    )
    focused = (
        focused_local_test_validation
        if isinstance(focused_local_test_validation, dict)
        else {}
    )
    adjacent = list(adjacent_general_agent_rows or [])
    retained = list(retained_boundaries or [])
    acceptance_status = str(acceptance.get("status") or "")
    acceptance_decision = str(acceptance.get("decision") or "")
    focused_status = str(
        focused.get("status")
        or acceptance.get("focused_local_test_validation_status")
        or handoff.get("focused_local_test_validation_status")
        or ""
    )
    def _proposal_id_list(*candidates: Any) -> list[str]:
        for candidate in candidates:
            if isinstance(candidate, list):
                return [
                    str(item)
                    for item in candidate
                    if str(item).strip()
                ]
        return []

    retained_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in retained
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
        | set(
            _proposal_id_list(
                acceptance.get("retained_boundary_proposal_ids"),
                handoff.get("retained_boundary_proposal_ids"),
                focused.get("retained_boundary_proposal_ids"),
            )
        )
    )
    # Prefer explicit adjacent rows / packet lists (including empty) so callers can
    # clear residual availability after acceptance without inheriting focused IDs.
    if adjacent:
        adjacent_ids = sorted(
            {
                str(row.get("proposal_id") or "")
                for row in adjacent
                if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
            }
        )
    else:
        adjacent_ids = sorted(
            set(
                _proposal_id_list(
                    acceptance.get("adjacent_general_agent_proposal_ids"),
                    handoff.get("adjacent_general_agent_proposal_ids"),
                    focused.get("adjacent_general_agent_proposal_ids"),
                )
            )
        )
    if "residual_adjacent_harness_eval_available" in acceptance:
        residual_available = bool(acceptance.get("residual_adjacent_harness_eval_available")) and bool(
            adjacent_ids
        )
    elif "residual_adjacent_harness_eval_available" in handoff:
        residual_available = bool(handoff.get("residual_adjacent_harness_eval_available")) and bool(
            adjacent_ids
        )
    else:
        residual_available = bool(adjacent_ids)
    selected_proposal_id = str(
        acceptance.get("selected_proposal_id")
        or acceptance.get("proposal_id")
        or handoff.get("selected_proposal_id")
        or focused.get("selected_proposal_id")
        or "prop-skill-reverse-flow-continue-local-validation"
    )
    profiles = [
        str(profile)
        for profile in list(
            acceptance.get("route_profiles")
            or handoff.get("route_profiles")
            or focused.get("route_profiles")
            or []
        )
    ]
    skill_first = bool(
        acceptance.get(
            "skill_route_discovery_first",
            handoff.get(
                "skill_route_discovery_first",
                focused.get("skill_route_discovery_first"),
            ),
        )
    )
    selected_lane = str(
        acceptance.get("selected_local_lane")
        or handoff.get("selected_local_lane")
        or focused.get("selected_local_lane")
        or ""
    )
    general_agent_isolated = all(
        row.get("skill_route_discovery_inherited") is False
        and list(row.get("direct_allowed_lanes_before_eval") or []) == []
        for row in adjacent
        if isinstance(row, dict)
    ) if adjacent else True
    privacy_isolated = all(
        str(row.get("route_class") or "")
        in {"privacy_boundary_review_only", "offensive_boundary_review_only"}
        for row in retained
        if isinstance(row, dict)
    ) if retained else True
    acceptance_ready = (
        acceptance_status == "accepted"
        and acceptance_decision
        == "accept_activation_external_package_after_focused_validation_pass"
        and bool(acceptance.get("activation_external_only", True))
        and acceptance.get("supervisor_activation_allowed") is not True
        and acceptance.get("runtime_action") == "none"
        and acceptance.get("external_skill_execution_allowed") is not True
        and acceptance.get("provider_launch_allowed") is not True
        and acceptance.get("remote_apply_allowed") is not True
        and acceptance.get("push_or_promotion_allowed") is not True
        and acceptance.get("kernel_restart_allowed") is not True
        and focused_status == "passed"
    )

    if acceptance_status in {"", "not_applicable"}:
        status = "not_applicable"
        decision = "no_activation_external_acceptance_for_residual_adjacent_queue"
        supervisor_next_action = (
            "wait_for_skill_route_discovery_focused_validation_activation_external_acceptance"
        )
    elif acceptance_status.startswith("blocked"):
        status = "blocked_until_activation_external_acceptance"
        decision = "hold_residual_adjacent_queue_until_activation_external_acceptance"
        if acceptance.get("supervisor_next_action"):
            supervisor_next_action = str(acceptance.get("supervisor_next_action"))
        else:
            supervisor_next_action = (
                "run_focused_local_test_validation_then_keep_activation_external"
            )
    elif not acceptance_ready:
        status = "blocked_until_activation_external_acceptance"
        decision = "hold_residual_adjacent_queue_until_body_free_acceptance"
        supervisor_next_action = (
            "run_focused_local_test_validation_then_keep_activation_external"
        )
    elif not residual_available:
        status = "not_applicable"
        decision = "no_residual_adjacent_rows_after_focused_validation_acceptance"
        supervisor_next_action = (
            "keep_activation_external_after_focused_local_test_validation"
        )
    elif not general_agent_isolated or not privacy_isolated:
        status = "blocked"
        decision = "repair_residual_adjacent_isolation_before_queue"
        supervisor_next_action = "repair_skill_route_config_gate_isolation"
    else:
        status = "ready"
        decision = (
            "queue_residual_adjacent_harness_eval_after_focused_validation_acceptance"
        )
        supervisor_next_action = (
            "hand_off_residual_adjacent_rows_to_agent_harness_eval_cluster_local_apply"
        )

    export_adjacent_ids = adjacent_ids if status == "ready" else []
    export_retained_ids = retained_ids if status in {"ready", "blocked", "not_applicable"} else []

    return {
        "schema_version": 1,
        "controller_surface": (
            "skill_route_discovery_focused_validation_residual_adjacent_queue"
        ),
        "proposal_track": "prop-skill-reverse-flow-continue-local-validation",
        "legacy_proposal_track": "prop-skill-reverse-flow-focused-test-validation",
        "companion_tracks": [
            "prop-skill-reverse-flow-continue-local-validation",
            "prop-skill-reverse-flow-focused-test-validation",
            "prop-harness-residual-hy3-fortress",
            "prop-harness-fortress-hy3-adjacent-eval",
            "prop-skill-rnskill-docs-companion",
            "prop-skill-pipeline-config-gates",
        ],
        "proposal_id": selected_proposal_id,
        "selected_proposal_id": selected_proposal_id,
        "status": status,
        "decision": decision,
        "capability_action": "queue_residual_adjacent_harness_eval_after_local_validation",
        "capability_pipeline": [
            "skill_route_discovery_capability_pipeline",
            "skill_route_discovery_local_comparison",
            "skill_route_discovery_reverse_flow_test_validation_lane",
            "skill_route_discovery_rnskill_docs_validation_lane",
            "skill_route_discovery_config_gate_boundary",
            "skill_route_discovery_local_apply",
            "skill_route_discovery_local_apply_completion",
            "skill_route_discovery_unlocked_local_test_lane_apply",
            "skill_route_discovery_focused_local_test_validation",
            "record_skill_route_discovery_focused_local_test_validation_results",
            "close_skill_route_discovery_focused_local_test_validation_with_outcome",
            "skill_route_discovery_focused_validation_activation_external_handoff",
            "skill_route_discovery_focused_validation_activation_external_acceptance",
            "skill_route_discovery_focused_validation_residual_adjacent_queue",
        ],
        "focused_validation_activation_external_acceptance_status": (
            acceptance_status or "none"
        ),
        "focused_validation_activation_external_acceptance_decision": acceptance_decision,
        "focused_validation_activation_external_handoff_status": str(
            handoff.get("status")
            or acceptance.get("focused_validation_activation_external_handoff_status")
            or "none"
        ),
        "focused_local_test_validation_status": focused_status or "none",
        "focused_local_test_validation_recorded": focused_status in {"passed", "failed"}
        or bool(
            focused.get("focused_validation_recorded")
            or acceptance.get("focused_local_test_validation_recorded")
        ),
        "route_class": str(
            acceptance.get("route_class")
            or handoff.get("route_class")
            or focused.get("route_class")
            or "none"
        ),
        "route_profiles": profiles,
        "skill_route_discovery_first": skill_first,
        "selected_local_lane": selected_lane if selected_lane else "none",
        "preferred_local_lane": "test",
        "allowed_local_lanes": list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES),
        # Residual queue never re-exports reverse-flow skill unlocks.
        "unlocked_local_lanes": [],
        "skill_route_discovery_inherited": False,
        "skill_route_unlocks_closed_for_residual": True,
        "evaluation_lane": "agent_harness_eval_required",
        "handoff_controller_surface": "agent_harness_eval_cluster_local_apply",
        "handoff_completion_surface": "agent_harness_eval_cluster_local_apply_completion",
        "allowed_local_lanes_after_local_comparison": list(
            AGENT_HARNESS_EVAL_POST_COMPARE_LANES
        ),
        "direct_allowed_lanes_before_eval": [],
        "local_validation_required": True,
        "activation_external_only": True,
        "supervisor_activation_allowed": False,
        "retained_boundary_proposal_ids": export_retained_ids,
        "adjacent_general_agent_proposal_ids": export_adjacent_ids,
        "residual_adjacent_harness_eval_available": residual_available,
        "residual_adjacent_handoff_surface": (
            "agent_harness_eval_cluster_local_apply" if residual_available else "none"
        ),
        "general_agent_inherits_skill_unlock": False,
        "privacy_rows_selectable_for_local_apply": False,
        "general_agent_isolation_passed": general_agent_isolated,
        "privacy_isolation_passed": privacy_isolated,
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "theme_id": str(
            theme.get("theme_id")
            or acceptance.get("theme_id")
            or handoff.get("theme_id")
            or focused.get("theme_id")
            or "skill-route-discovery"
        ),
        "theme_pass": {
            "planned_passes": int(
                theme.get("planned_passes")
                or (acceptance.get("theme_pass") or {}).get("planned_passes")
                or (handoff.get("theme_pass") or {}).get("planned_passes")
                or (focused.get("theme_pass") or {}).get("planned_passes")
                or 0
            ),
            "target_passes": int(
                theme.get("target_passes")
                or (acceptance.get("theme_pass") or {}).get("target_passes")
                or (handoff.get("theme_pass") or {}).get("target_passes")
                or (focused.get("theme_pass") or {}).get("target_passes")
                or DEFAULT_THEME_WINDOW_TARGET_PASSES
            ),
            "status": str(
                theme.get("status")
                or (acceptance.get("theme_pass") or {}).get("status")
                or (handoff.get("theme_pass") or {}).get("status")
                or (focused.get("theme_pass") or {}).get("status")
                or ""
            ),
        },
        "source_digest": source_digest
        or str(
            acceptance.get("source_digest")
            or handoff.get("source_digest")
            or focused.get("source_digest")
            or ""
        ),
        "supervisor_next_action": supervisor_next_action,
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_local_test_validation",
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_focused_validation_residual_adjacent",
            ADJACENT_HARNESS_EVAL_VALIDATION_COMMAND,
        ],
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
        "raw_command_stdout_exported": False,
        "raw_command_text_exported": False,
    }


def build_skill_route_discovery_adjacent_harness_eval_handoff(
    *,
    selected_step: dict[str, Any],
    adjacent_general_agent_rows: list[dict[str, Any]] | None = None,
    retained_boundaries: list[dict[str, Any]] | None = None,
    local_comparison: dict[str, Any] | None = None,
    local_apply: dict[str, Any] | None = None,
    local_apply_completion: dict[str, Any] | None = None,
    theme_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operator-visible handoff from skill-route residual rows to agent harness-eval.

    When the skill-route pipeline selects a fortress-style
    ``agent_harness_eval_required`` row (no reverse-flow skill candidate remains),
    do not fail skill-route local comparison or demand reverse-flow repair. Instead
    emit a body-free handoff that queues
    ``agent_harness_eval_cluster_local_apply`` for documentation/test/code_patch
    after harness-eval criteria pass. Privacy/offensive rows stay review-only;
    runtime action, provider launch, remote apply, and skill unlocks stay denied.
    """

    theme = theme_window if isinstance(theme_window, dict) else {}
    selected = selected_step if isinstance(selected_step, dict) else {}
    adjacent = list(adjacent_general_agent_rows or [])
    retained = list(retained_boundaries or [])
    comparison = local_comparison if isinstance(local_comparison, dict) else {}
    apply = local_apply if isinstance(local_apply, dict) else {}
    completion = local_apply_completion if isinstance(local_apply_completion, dict) else {}

    selected_route_class = str(selected.get("route_class") or "")
    selected_proposal_id = str(selected.get("proposal_id") or "")
    selected_is_adjacent = selected_route_class == "agent_harness_eval_required"
    general_agent_isolated = all(
        row.get("skill_route_discovery_inherited") is False
        and list(row.get("direct_allowed_lanes_before_eval") or []) == []
        for row in adjacent
    ) if adjacent else True
    privacy_isolated = all(
        str(row.get("route_class") or "")
        in {"privacy_boundary_review_only", "offensive_boundary_review_only"}
        for row in retained
    ) if retained else True
    skill_unlocks_closed = list(selected.get("unlocked_local_lanes") or []) == [] and list(
        apply.get("unlocked_local_lanes") or []
    ) == []

    if not selected_proposal_id:
        status = "not_applicable"
        decision = "no_selected_step_for_adjacent_harness_eval_handoff"
        supervisor_next_action = "wait_for_skill_route_or_adjacent_harness_selection"
    elif not selected_is_adjacent:
        status = "not_applicable"
        decision = "selected_step_is_not_adjacent_agent_harness_eval"
        supervisor_next_action = "continue_skill_route_discovery_pipeline"
    elif not general_agent_isolated or not privacy_isolated:
        status = "blocked"
        decision = "repair_adjacent_isolation_before_harness_eval_handoff"
        supervisor_next_action = "repair_skill_route_config_gate_isolation"
    elif not skill_unlocks_closed:
        status = "blocked"
        decision = "close_skill_route_unlocks_before_adjacent_harness_handoff"
        supervisor_next_action = "repair_skill_route_discovery_local_apply_before_handoff"
    else:
        status = "ready"
        decision = (
            "queue_selected_general_agent_row_for_agent_harness_eval_local_comparison"
        )
        supervisor_next_action = (
            "run_agent_harness_eval_local_comparison_for_selected_general_agent_row"
        )

    retained_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in retained
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
    )
    adjacent_ids = sorted(
        {
            str(row.get("proposal_id") or "")
            for row in adjacent
            if isinstance(row, dict) and str(row.get("proposal_id") or "").strip()
        }
    )

    return {
        "schema_version": 1,
        "controller_surface": "skill_route_discovery_adjacent_harness_eval_handoff",
        "proposal_track": selected_proposal_id or "prop-harness-fortress-local-eval",
        "status": status,
        "decision": decision,
        "selected_proposal_id": selected_proposal_id,
        "route_class": selected_route_class or "none",
        "capability_action": str(
            selected.get("capability_action")
            or "queue_general_agent_project_for_harness_eval"
        ),
        "evaluation_lane": "agent_harness_eval_required",
        "handoff_controller_surface": "agent_harness_eval_cluster_local_apply",
        "handoff_completion_surface": "agent_harness_eval_cluster_local_apply_completion",
        "allowed_local_lanes_after_local_comparison": list(AGENT_HARNESS_EVAL_POST_COMPARE_LANES),
        "direct_allowed_lanes_before_eval": [],
        "skill_route_discovery_inherited": False,
        "skill_route_unlocks_closed": skill_unlocks_closed,
        "local_comparison_required": True,
        "local_comparison_status": str(
            selected.get("local_comparison_status")
            or comparison.get("status")
            or "not_applicable"
        ),
        "skill_route_local_comparison_status": str(comparison.get("status") or "none"),
        "skill_route_local_apply_status": str(apply.get("status") or "none"),
        "skill_route_local_apply_completion_status": str(completion.get("status") or "none"),
        "general_agent_isolation_passed": general_agent_isolated,
        "privacy_isolation_passed": privacy_isolated,
        "adjacent_general_agent_proposal_ids": adjacent_ids,
        "retained_boundary_proposal_ids": retained_ids,
        "runtime_action": "none",
        "external_skill_execution_allowed": False,
        "provider_launch_allowed": False,
        "remote_apply_allowed": False,
        "push_or_promotion_allowed": False,
        "kernel_restart_allowed": False,
        "supervisor_activation_allowed": False,
        "supervisor_next_action": supervisor_next_action,
        "theme_id": str(theme.get("theme_id") or "skill-route-discovery"),
        "theme_pass": {
            "planned_passes": int(theme.get("planned_passes") or 0),
            "target_passes": int(theme.get("target_passes") or DEFAULT_THEME_WINDOW_TARGET_PASSES),
            "status": str(theme.get("status") or ""),
        },
        "required_validation": [
            "pytest tests/test_github_growth.py -q -k skill_route_discovery_capability_pipeline",
            ADJACENT_HARNESS_EVAL_VALIDATION_COMMAND,
        ],
        "body_free": True,
        "raw_evidence_urls_exported": False,
        "raw_upstream_bodies_exported": False,
    }


def classify_skill_route_discovery_capability_route(proposal: dict[str, Any]) -> dict[str, Any]:
    """Classify one proposal into the skill-route capability pipeline without raw URL export."""

    proposal_id = str(proposal.get("proposal_id") or "").strip()
    kind = str(proposal.get("kind") or "no_action").strip() or "no_action"
    implementation_scope = str(proposal.get("implementation_scope") or "").strip()
    validation_gate = str(proposal.get("validation_gate") or "").strip()
    risk_flags = sorted({str(flag) for flag in proposal.get("risk_flags", []) if str(flag).strip()})
    evidence_url_hashes = sorted(
        {
            hashlib.sha256(str(url).strip().encode("utf-8")).hexdigest()[:16]
            for url in proposal.get("evidence_urls", [])
            if str(url).strip()
        }
    )
    summary_text = " ".join(
        str(proposal.get(key) or "")
        for key in (
            "summary",
            "kind",
            "validation_task",
            "rationale",
            "recommended_action",
            "proposal_id",
        )
    ).lower()
    evidence_blob = " ".join(str(url).lower() for url in proposal.get("evidence_urls", []) if str(url).strip())
    blob = f"{proposal_id.lower()} {summary_text} {evidence_blob}"

    preflight = proposal_validation_preflight(proposal)
    autonomous_text = autonomous_local_apply_text(proposal)
    autonomous_allowed = autonomous_text == "True" and preflight.get("status") == "ready"

    route_profiles = skill_route_discovery_route_profiles_for_text(blob)
    skill_route_discovery_first = "codex_workflow_gate" in route_profiles
    preferred_lane = skill_route_discovery_preferred_lane(route_profiles, kind)
    allowed_lanes = list(SKILL_ROUTE_DISCOVERY_ALLOWED_LANES)

    if "offensive-behavior" in risk_flags or validation_gate == "offensive-behavior-human-review":
        route_class = "offensive_boundary_review_only"
        capability_action = "retain_offensive_behavior_review_boundary"
        preferred_lane = "none"
        allowed_lanes = []
        route_profiles = []
        skill_route_discovery_first = False
        selection_reason = "offensive_behavior_remains_review_only"
        status = "blocked_by_safety_boundary"
        autonomous_allowed = False
    elif (
        "privacy-leakage" in risk_flags
        or validation_gate == "privacy-leakage-human-review"
        or any(marker in blob for marker in _SKILL_ROUTE_AGENT_CHIEF_MARKERS)
    ):
        route_class = "privacy_boundary_review_only"
        capability_action = "retain_privacy_leakage_review_boundary"
        preferred_lane = "none"
        allowed_lanes = []
        route_profiles = []
        skill_route_discovery_first = False
        selection_reason = "privacy_leakage_or_agent_chief_remains_review_only"
        status = "blocked_by_safety_boundary"
        autonomous_allowed = False
    elif (
        any(marker in blob for marker in _SKILL_ROUTE_FORTRESS_MARKERS)
        or any(marker in blob for marker in _SKILL_ROUTE_HY3_MARKERS)
        or any(marker in blob for marker in _SKILL_ROUTE_GENERAL_AGENT_HARNESS_MARKERS)
        or (
            "general_agent" in blob
            and not any(marker in blob for marker in _SKILL_ROUTE_REVERSE_FLOW_MARKERS)
            and not any(marker in blob for marker in _SKILL_ROUTE_RNSKILL_MARKERS)
            and not any(marker in blob for marker in _SKILL_ROUTE_GENERIC_SKILL_MARKERS)
        )
    ):
        route_class = "agent_harness_eval_required"
        capability_action = "queue_general_agent_project_for_harness_eval"
        preferred_lane = "none"
        allowed_lanes = list(AGENT_HARNESS_EVAL_POST_COMPARE_LANES)
        route_profiles = []
        skill_route_discovery_first = False
        selection_reason = "general_agent_project_requires_agent_harness_eval"
        status = "adjacent_harness_eval"
        autonomous_allowed = False
    elif route_profiles or any(marker in blob for marker in _SKILL_ROUTE_GENERIC_SKILL_MARKERS):
        if not route_profiles:
            route_profiles = ["generic_skill_workflow"]
            preferred_lane = skill_route_discovery_preferred_lane(route_profiles, kind)
        route_class = "skill_route_discovery"
        capability_action = "apply_one_local_skill_route_validation_candidate"
        selection_reason = (
            "codex_workflow_gate_skill_route_discovery_first"
            if skill_route_discovery_first
            else "generic_skill_workflow_skill_route_discovery"
        )
        if implementation_scope == "local_validation_candidate" and preflight.get("status") == "ready":
            status = "ready"
        elif implementation_scope == "local_validation_candidate":
            status = "validation_gap"
            autonomous_allowed = False
            selection_reason = "skill_route_candidate_has_preflight_gaps"
        else:
            status = "ready" if not risk_flags else "risk_review"
            if risk_flags:
                autonomous_allowed = False
                selection_reason = "skill_route_candidate_has_non_hard_risk_flags"
    elif implementation_scope == "reviewable_proposal_only" or kind in {"follow_up_issue", "no_action"}:
        route_class = "follow_up_only"
        capability_action = "preserve_follow_up_without_skill_route_apply"
        preferred_lane = "none"
        allowed_lanes = []
        route_profiles = []
        skill_route_discovery_first = False
        selection_reason = "proposal_is_follow_up_or_reviewable_only"
        status = "follow_up_only"
        autonomous_allowed = False
    else:
        route_class = "follow_up_only"
        capability_action = "preserve_follow_up_without_skill_route_apply"
        preferred_lane = _local_lane_from_proposal_kind(kind)
        allowed_lanes = []
        route_profiles = []
        skill_route_discovery_first = False
        selection_reason = "no_mapped_skill_route_capability"
        status = "follow_up_only"
        autonomous_allowed = False

    return {
        "proposal_id": proposal_id,
        "route_class": route_class,
        "capability_action": capability_action,
        "route_profiles": list(route_profiles),
        "preferred_local_lane": preferred_lane,
        "allowed_local_lanes": list(allowed_lanes),
        "skill_route_discovery_first": skill_route_discovery_first,
        "kind": kind,
        "implementation_scope": implementation_scope,
        "validation_gate": validation_gate,
        "risk_flags": risk_flags,
        "evidence_url_hashes": evidence_url_hashes,
        "local_comparison_required": route_class == "skill_route_discovery",
        "autonomous_local_apply_allowed": autonomous_allowed,
        "autonomous_local_apply_text": autonomous_text,
        "validation_preflight_status": str(preflight.get("status") or ""),
        "validation_gaps": list(preflight.get("validation_gaps") or []),
        "selection_reason": selection_reason,
        "status": status,
        "selected": False,
        "runtime_action": "none",
        "external_skill_activation_allowed": False,
    }


def skill_route_discovery_route_profiles_for_text(blob: str) -> list[str]:
    """Infer route profiles from proposal text and evidence refs without exporting URLs."""

    profiles: list[str] = []
    if any(marker in blob for marker in _SKILL_ROUTE_REVERSE_FLOW_MARKERS):
        profiles.append("codex_workflow_gate")
    if any(marker in blob for marker in _SKILL_ROUTE_RNSKILL_MARKERS):
        profiles.append("generic_skill_workflow")
    if "codex_workflow_gate" in profiles and "generic_skill_workflow" not in profiles:
        # reverse-flow also carries generic skill-workflow framing in public evidence
        if "reverse-flow" in blob or "reverse_flow" in blob or "reverse flow" in blob:
            profiles.append("generic_skill_workflow")
    if not profiles and any(marker in blob for marker in _SKILL_ROUTE_GENERIC_SKILL_MARKERS):
        profiles.append("generic_skill_workflow")
    # stable unique order
    ordered = []
    for profile in ("codex_workflow_gate", "generic_skill_workflow"):
        if profile in profiles and profile not in ordered:
            ordered.append(profile)
    for profile in profiles:
        if profile not in ordered:
            ordered.append(profile)
    return ordered


def skill_route_discovery_preferred_lane(route_profiles: list[str], kind: str = "") -> str:
    """Prefer test for codex workflow gates and documentation for generic skill collections."""

    _ = kind  # profile preference is authoritative for skill-route local lanes
    if "codex_workflow_gate" in route_profiles:
        return "test"
    return "documentation"


def select_skill_route_discovery_capability_step(
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick one next skill-route local apply candidate from classified rows."""

    if not candidate_rows:
        return None

    priority = {
        "skill_route_discovery": 0,
        "agent_harness_eval_required": 1,
        "follow_up_only": 2,
        "privacy_boundary_review_only": 3,
        "offensive_boundary_review_only": 4,
    }

    def _specificity_rank(row: dict[str, Any]) -> int:
        proposal_id = str(row.get("proposal_id") or "").casefold()
        # Prefer concrete reverse-flow test validation candidates, then reverse-flow
        # trend tokens, then rnskill, then umbrella skill-route pipeline props.
        if (
            "skill-pipeline-reverse-flow" in proposal_id
            or "skill_pipeline_reverse_flow" in proposal_id
            or "skill-reverse-flow-test" in proposal_id
            or "skill_reverse_flow_test" in proposal_id
            or "reverse-flow-test" in proposal_id
            or "reverse_flow_test" in proposal_id
        ):
            return 0
        if "reverse-flow-skill" in proposal_id or "reverse_flow_skill" in proposal_id:
            return 1
        if "reverse-flow" in proposal_id or "reverse_flow" in proposal_id:
            return 1
        if "rnskill" in proposal_id:
            return 2
        if "skill-route-discovery" in proposal_id or "skill_route_discovery" in proposal_id:
            return 3
        if "skill-pipeline" in proposal_id or "skill_pipeline" in proposal_id:
            return 3
        return 4

    def _row_rank(row: dict[str, Any]) -> tuple[Any, ...]:
        profiles = list(row.get("route_profiles") or [])
        # Prefer reverse-flow / codex_workflow_gate over generic rnskill collections.
        codex_rank = 0 if "codex_workflow_gate" in profiles else 1
        status_rank = 0 if row.get("status") == "ready" else 1
        return (
            priority.get(str(row.get("route_class") or ""), 99),
            codex_rank,
            status_rank,
            _specificity_rank(row),
            str(row.get("proposal_id") or ""),
        )

    ranked = sorted(candidate_rows, key=_row_rank)
    selected = ranked[0]
    # Only select skill-route rows for local apply; otherwise surface the top
    # non-apply outcome (adjacent harness eval or retained boundary).
    skill_ready = [
        row
        for row in ranked
        if row.get("route_class") == "skill_route_discovery" and row.get("status") in {"ready", "validation_gap", "risk_review"}
    ]
    if skill_ready:
        return skill_ready[0]
    return selected


def push_message_text(signal: GrowthSignal) -> str:
    return " ".join(f"{signal.title} {signal.relevance_reason}".lower().split())


def stable_push_message_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


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
                f"  - Autonomous local apply: {autonomous_local_apply_text(proposal)}",
            ]
        )
        implementation_scope = str(proposal.get("implementation_scope") or "").strip()
        if implementation_scope:
            lines.append(f"  - Implementation scope: `{implementation_scope}`")
        validation_gate = str(proposal.get("validation_gate") or "").strip()
        if validation_gate:
            lines.append(f"  - Validation gate: `{validation_gate}`")
        validation_task = str(proposal.get("validation_task") or "").strip()
        if validation_task:
            lines.append(f"  - Validation task: {validation_task}")
    capability_step = digest.get("upstream_evidence_capability_step")
    if isinstance(capability_step, dict):
        lines.extend(["", "## Upstream Evidence Capability Step", ""])
        selected = capability_step.get("selected_step") if isinstance(capability_step.get("selected_step"), dict) else {}
        lines.extend(
            [
                f"- Status: `{capability_step.get('status', '')}`",
                f"- Theme: `{capability_step.get('theme_id', '')}`",
                f"- Selected proposal: `{selected.get('proposal_id') or 'none'}`",
                f"- Route class: `{selected.get('route_class') or 'none'}`",
                f"- Capability action: `{selected.get('capability_action') or 'none'}`",
                f"- Local lane: `{selected.get('local_lane') or 'none'}`",
                f"- Requires local compare before draft: `{bool(selected.get('requires_local_compare_before_draft'))}`",
                f"- Autonomous local apply: `{bool(selected.get('autonomous_local_apply'))}`",
                f"- Runtime action: `{capability_step.get('runtime_action', 'none')}`",
                f"- Raw evidence URLs exported: `{bool(capability_step.get('raw_evidence_urls_exported'))}`",
                f"- Privacy export allowed: `{bool(capability_step.get('privacy_export_allowed'))}`",
            ]
        )
        retained = capability_step.get("retained_boundaries") or []
        if retained:
            lines.append("- Retained review-only boundaries:")
            for boundary in retained:
                if not isinstance(boundary, dict):
                    continue
                lines.append(
                    "  - "
                    f"`{boundary.get('proposal_id') or 'unknown'}` "
                    f"(`{boundary.get('route_class') or 'unknown'}` / "
                    f"`{boundary.get('validation_gate') or 'none'}`)"
                )
        lines.append(f"- Promotion rule: {capability_step.get('promotion_rule', '')}")
    skill_pipeline = digest.get("skill_route_discovery_capability_pipeline")
    if isinstance(skill_pipeline, dict) and skill_pipeline:
        lines.extend(["", "## Skill Route Discovery Capability Pipeline", ""])
        selected = (
            skill_pipeline.get("selected_step")
            if isinstance(skill_pipeline.get("selected_step"), dict)
            else {}
        )
        lines.extend(
            [
                f"- Status: `{skill_pipeline.get('status', '')}`",
                f"- Theme: `{skill_pipeline.get('theme_id', '')}`",
                f"- Pipeline stages: `{', '.join(skill_pipeline.get('pipeline_stages') or [])}`",
                f"- Selected proposal: `{selected.get('proposal_id') or 'none'}`",
                f"- Route class: `{selected.get('route_class') or 'none'}`",
                f"- Capability action: `{selected.get('capability_action') or 'none'}`",
                f"- Route profiles: `{', '.join(selected.get('route_profiles') or []) or 'none'}`",
                f"- Selected local lane: `{selected.get('selected_local_lane') or 'none'}`",
                f"- Unlocked local lanes: `{', '.join(selected.get('unlocked_local_lanes') or []) or 'none'}`",
                f"- Local comparison required: `{bool(selected.get('local_comparison_required'))}`",
                f"- Local comparison status: `{selected.get('local_comparison_status') or 'none'}`",
                f"- Local comparison decision: `"
                f"{(skill_pipeline.get('local_comparison') or {}).get('decision') or 'none'}`",
                f"- Reverse-flow test validation lane: `"
                f"{(skill_pipeline.get('reverse_flow_test_validation_lane') or {}).get('status') or 'none'}`",
                f"- Rnskill docs validation lane: `"
                f"{(skill_pipeline.get('rnskill_docs_validation_lane') or {}).get('status') or 'none'}`",
                f"- Config gate boundary: `"
                f"{(skill_pipeline.get('config_gate_boundary') or {}).get('status') or 'none'}`",
                f"- Local apply handoff: `"
                f"{(skill_pipeline.get('local_apply') or {}).get('status') or 'none'}`",
                f"- Runtime action: `{skill_pipeline.get('runtime_action', 'none')}`",
                f"- Raw evidence URLs exported: `{bool(skill_pipeline.get('raw_evidence_urls_exported'))}`",
            ]
        )
        retained = skill_pipeline.get("retained_boundaries") or []
        if retained:
            lines.append("- Retained review-only boundaries:")
            for boundary in retained:
                if not isinstance(boundary, dict):
                    continue
                lines.append(
                    "  - "
                    f"`{boundary.get('proposal_id') or 'unknown'}` "
                    f"(`{boundary.get('route_class') or 'unknown'}`)"
                )
        adjacent = skill_pipeline.get("adjacent_general_agent_rows") or []
        if adjacent:
            lines.append("- Adjacent general-agent harness-eval rows:")
            for row in adjacent:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    "  - "
                    f"`{row.get('proposal_id') or 'unknown'}` "
                    f"(`{row.get('evaluation_lane') or 'agent_harness_eval_required'}`)"
                )
        lines.append(f"- Promotion rule: {skill_pipeline.get('promotion_rule', '')}")
    return "\n".join(lines) + "\n"


def build_self_evolution_plan(
    digest: dict[str, Any],
    *,
    repo_path: Path,
    branch_prefix: str = "codex/blackhole-evolve",
    max_proposals: int = 3,
    force: bool = False,
    extra_instructions: str = "",
    self_model_path: Path | None = None,
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

    capability_theme_window = dict(
        digest.get("capability_theme_window")
        or build_capability_theme_window(
            proposals,
            generated_at=str(digest.get("generated_at") or ""),
        )
    )
    capability_step = digest.get("upstream_evidence_capability_step")
    if not isinstance(capability_step, dict) or not capability_step:
        capability_step = build_upstream_evidence_capability_step(
            proposals,
            theme_window=capability_theme_window,
            items=list(digest.get("items") or []),
        )
    skill_pipeline = digest.get("skill_route_discovery_capability_pipeline")
    if not isinstance(skill_pipeline, dict) or not skill_pipeline:
        skill_pipeline = build_skill_route_discovery_capability_pipeline(
            proposals,
            theme_window=capability_theme_window,
            items=list(digest.get("items") or []),
        )
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    self_model_before = read_self_model_snapshot(repo_path, self_model_path)
    branch_name = build_evolution_branch_name(branch_prefix, generated_at, proposals[0]["summary"])
    task = render_self_evolution_task(
        proposals,
        repo_path=repo_path,
        branch_name=branch_name,
        self_model_snapshot=self_model_before,
        digest_id=str(digest.get("digest_id", "")),
        digest_generated_at=str(digest.get("generated_at", "")),
        capability_theme_window=capability_theme_window,
        upstream_evidence_capability_step=capability_step,
        skill_route_discovery_capability_pipeline=skill_pipeline,
        extra_instructions=extra_instructions,
    )
    return SelfEvolutionPlan(
        generated_at=generated_at,
        repo_path=str(repo_path),
        branch_name=branch_name,
        self_model_path=self_model_before.path,
        self_model_before=self_model_before,
        task=task,
        proposals=proposals,
        source_digest_id=str(digest.get("digest_id", "")),
        source_digest_generated_at=str(digest.get("generated_at", "")),
        capability_theme_window=capability_theme_window,
        upstream_evidence_capability_step=dict(capability_step),
        skill_route_discovery_capability_pipeline=dict(skill_pipeline),
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


def render_capability_theme_window_lines(theme_window: dict[str, Any]) -> list[str]:
    """Render the active theme window as bounded task instructions."""

    if not theme_window:
        return [
            "- No prior theme window was available; choose one coherent capability slice and make it replayable.",
        ]
    proposal_ids = ", ".join(bounded_unique_strings(theme_window.get("proposal_ids", []))) or "none yet"
    evidence_urls = ", ".join(bounded_unique_strings(theme_window.get("evidence_urls", []), limit=4)) or "none yet"
    return [
        f"- Theme: {theme_window.get('title', '')} (`{theme_window.get('theme_id', '')}`)",
        f"- Capability slice: {theme_window.get('capability_slice', '')}",
        (
            f"- Planned pass: {theme_window.get('planned_passes', 0)} of "
            f"{theme_window.get('target_passes', DEFAULT_THEME_WINDOW_TARGET_PASSES)} "
            f"({theme_window.get('status', 'active')})"
        ),
        f"- Anchoring proposal IDs: {proposal_ids}",
        f"- Evidence URLs carried by the window: {evidence_urls}",
        "- Continuity rule: advance this slice across passes; defer unrelated micro-patches unless they unblock the slice.",
        "- Completion rule: prefer an operator-visible behavior, integration path, or recovery workflow over another standalone fixture.",
    ]


def render_upstream_evidence_capability_step_lines(capability_step: dict[str, Any]) -> list[str]:
    """Render the selected upstream-evidence capability step for kernel tasks."""

    if not capability_step:
        return []
    selected = capability_step.get("selected_step") if isinstance(capability_step.get("selected_step"), dict) else {}
    lines = [
        "Upstream evidence capability step:",
        f"- Status: `{capability_step.get('status', '')}`",
        f"- Selected proposal: `{selected.get('proposal_id') or 'none'}`",
        f"- Route class: `{selected.get('route_class') or 'none'}`",
        f"- Capability action: `{selected.get('capability_action') or 'none'}`",
        f"- Local lane: `{selected.get('local_lane') or 'none'}`",
        f"- Requires local compare before draft: `{bool(selected.get('requires_local_compare_before_draft'))}`",
        f"- Autonomous local apply for selected step: `{bool(selected.get('autonomous_local_apply'))}`",
        f"- Runtime action: `{capability_step.get('runtime_action', 'none')}`",
        "- Prefer this selected local capability step over isolated notes when the theme window is active.",
        "- Keep privacy-leakage and offensive-behavior rows review-only; do not export raw evidence URLs or sensitive bodies.",
    ]
    retained = capability_step.get("retained_boundaries") or []
    if retained:
        retained_ids = ", ".join(
            str(row.get("proposal_id") or "unknown")
            for row in retained
            if isinstance(row, dict)
        )
        lines.append(f"- Retained review-only boundaries: {retained_ids or 'none'}")
    return lines


def render_skill_route_discovery_capability_pipeline_lines(
    pipeline: dict[str, Any],
) -> list[str]:
    """Render the skill-route capability pipeline for kernel tasks."""

    if not pipeline:
        return []
    selected = pipeline.get("selected_step") if isinstance(pipeline.get("selected_step"), dict) else {}
    local_comparison = (
        pipeline.get("local_comparison")
        if isinstance(pipeline.get("local_comparison"), dict)
        else {}
    )
    reverse_flow_lane = (
        pipeline.get("reverse_flow_test_validation_lane")
        if isinstance(pipeline.get("reverse_flow_test_validation_lane"), dict)
        else {}
    )
    rnskill_docs_lane = (
        pipeline.get("rnskill_docs_validation_lane")
        if isinstance(pipeline.get("rnskill_docs_validation_lane"), dict)
        else {}
    )
    config_gates = (
        pipeline.get("config_gate_boundary")
        if isinstance(pipeline.get("config_gate_boundary"), dict)
        else {}
    )
    local_apply = (
        pipeline.get("local_apply") if isinstance(pipeline.get("local_apply"), dict) else {}
    )
    local_apply_completion = (
        pipeline.get("local_apply_completion")
        if isinstance(pipeline.get("local_apply_completion"), dict)
        else {}
    )
    unlocked_test_lane_apply = (
        pipeline.get("unlocked_local_test_lane_apply")
        if isinstance(pipeline.get("unlocked_local_test_lane_apply"), dict)
        else {}
    )
    focused_local_test_validation = (
        pipeline.get("focused_local_test_validation")
        if isinstance(pipeline.get("focused_local_test_validation"), dict)
        else {}
    )
    activation_external_handoff = (
        pipeline.get("focused_validation_activation_external_handoff")
        if isinstance(pipeline.get("focused_validation_activation_external_handoff"), dict)
        else {}
    )
    activation_external_acceptance = (
        pipeline.get("focused_validation_activation_external_acceptance")
        if isinstance(pipeline.get("focused_validation_activation_external_acceptance"), dict)
        else {}
    )
    residual_adjacent_queue = (
        pipeline.get("focused_validation_residual_adjacent_queue")
        if isinstance(pipeline.get("focused_validation_residual_adjacent_queue"), dict)
        else {}
    )
    adjacent_handoff = (
        pipeline.get("adjacent_agent_harness_eval_handoff")
        if isinstance(pipeline.get("adjacent_agent_harness_eval_handoff"), dict)
        else {}
    )
    stages = ", ".join(str(stage) for stage in pipeline.get("pipeline_stages") or [])
    profiles = ", ".join(str(profile) for profile in selected.get("route_profiles") or [])
    focused_status = str(focused_local_test_validation.get("status") or "")
    activation_external_status = str(activation_external_handoff.get("status") or "")
    activation_external_acceptance_status = str(
        activation_external_acceptance.get("status") or ""
    )
    residual_adjacent_queue_status = str(residual_adjacent_queue.get("status") or "")
    unlocked_status = str(unlocked_test_lane_apply.get("status") or "")
    supervisor_next = (
        adjacent_handoff.get("supervisor_next_action")
        if str(adjacent_handoff.get("status") or "") == "ready"
        else None
    ) or (
        residual_adjacent_queue.get("supervisor_next_action")
        if residual_adjacent_queue_status
        in {
            "ready",
            "blocked_until_activation_external_acceptance",
            "blocked",
        }
        else None
    ) or (
        activation_external_acceptance.get("supervisor_next_action")
        if activation_external_acceptance_status
        in {
            "accepted",
            "blocked_until_activation_external_handoff_ready",
        }
        else None
    ) or (
        activation_external_handoff.get("supervisor_next_action")
        if activation_external_status
        in {
            "ready",
            "blocked_until_focused_validation_recorded",
            "blocked_until_focused_validation_repaired",
            "blocked_until_focused_validation_ready",
            "blocked_until_focused_validation_pass",
        }
        else None
    ) or (
        focused_local_test_validation.get("supervisor_next_action")
        if focused_status in {"ready", "passed", "failed"}
        else None
    ) or (
        unlocked_test_lane_apply.get("supervisor_next_action")
        if unlocked_status == "ready"
        else None
    ) or local_apply_completion.get("supervisor_next_action") or local_apply.get(
        "supervisor_next_action"
    ) or "none"
    lines = [
        "Skill route discovery capability pipeline:",
        f"- Status: `{pipeline.get('status', '')}`",
        f"- Pipeline stages: `{stages or 'none'}`",
        f"- Selected proposal: `{selected.get('proposal_id') or 'none'}`",
        f"- Route class: `{selected.get('route_class') or 'none'}`",
        f"- Capability action: `{selected.get('capability_action') or 'none'}`",
        f"- Route profiles: `{profiles or 'none'}`",
        f"- Selected local lane: `{selected.get('selected_local_lane') or 'none'}`",
        f"- Unlocked local lanes: `{', '.join(selected.get('unlocked_local_lanes') or []) or 'none'}`",
        f"- Local comparison required: `{bool(selected.get('local_comparison_required'))}`",
        f"- Local comparison status: `{selected.get('local_comparison_status') or 'none'}`",
        f"- Local comparison decision: `{local_comparison.get('decision') or 'none'}`",
        f"- Reverse-flow test validation lane: `{reverse_flow_lane.get('status') or 'none'}`",
        f"- Rnskill docs validation lane: `{rnskill_docs_lane.get('status') or 'none'}`",
        f"- Config gate boundary: `{config_gates.get('status') or 'none'}`",
        f"- Local apply handoff: `{local_apply.get('status') or 'none'}`",
        f"- Local apply decision: `{local_apply.get('decision') or 'none'}`",
        f"- Local apply completion: `{local_apply_completion.get('status') or 'none'}`",
        f"- Local apply completion decision: `{local_apply_completion.get('decision') or 'none'}`",
        f"- Unlocked local test lane apply: `{unlocked_test_lane_apply.get('status') or 'none'}`",
        f"- Unlocked local test lane apply decision: `{unlocked_test_lane_apply.get('decision') or 'none'}`",
        f"- Focused local test validation: `{focused_local_test_validation.get('status') or 'none'}`",
        f"- Focused local test validation decision: `{focused_local_test_validation.get('decision') or 'none'}`",
        f"- Focused local test validation recorded: `"
        f"{bool(focused_local_test_validation.get('focused_validation_recorded') or pipeline.get('focused_local_test_validation_recorded'))}`",
        f"- Focused validation results cover expected: `"
        f"{bool((focused_local_test_validation.get('focused_validation') or {}).get('results_cover_expected'))}`",
        f"- Focused validation activation-external handoff: `"
        f"{activation_external_handoff.get('status') or 'none'}`",
        f"- Focused validation activation-external decision: `"
        f"{activation_external_handoff.get('decision') or 'none'}`",
        f"- Focused validation activation-external acceptance: `"
        f"{activation_external_acceptance.get('status') or 'none'}`",
        f"- Focused validation activation-external acceptance decision: `"
        f"{activation_external_acceptance.get('decision') or 'none'}`",
        f"- Focused validation residual adjacent queue: `"
        f"{residual_adjacent_queue.get('status') or 'none'}`",
        f"- Focused validation residual adjacent queue decision: `"
        f"{residual_adjacent_queue.get('decision') or 'none'}`",
        f"- Adjacent agent harness-eval handoff: `{adjacent_handoff.get('status') or 'none'}`",
        f"- Adjacent handoff decision: `{adjacent_handoff.get('decision') or 'none'}`",
        f"- Theme complete: `{bool(local_apply_completion.get('theme_complete'))}`",
        f"- Supervisor next action: `{supervisor_next}`",
        f"- Skill route discovery first: `{bool(selected.get('skill_route_discovery_first'))}`",
        f"- Autonomous local apply for selected step: `{bool(selected.get('autonomous_local_apply'))}`",
        f"- Runtime action: `{pipeline.get('runtime_action', 'none')}`",
        "- Prefer this skill-route pipeline over isolated notes when the skill-route-discovery theme is active.",
        "- Map only to documentation, config, test, or code_patch; keep external skill execution and provider launch denied.",
        "- Keep privacy-leakage and offensive-behavior rows review-only; do not export raw evidence URLs or sensitive bodies.",
        "- Pass 2 locks reverse-flow codex_workflow_gate into a bounded local test lane only after pipeline-stage comparison.",
        "- Pass 3 packages reverse-flow local apply with body-free rnskill docs companion and config-gate boundaries.",
        "- Pass 4 completes the reverse-flow local test validation lane via skill_route_discovery_local_apply_completion.",
        "- After completion, skill_route_discovery_unlocked_local_test_lane_apply packages focused local test validation while activation stays external.",
        "- After unlock, skill_route_discovery_focused_local_test_validation records body-free command-hash results and keeps activation external.",
        "- After ready, record_skill_route_discovery_focused_local_test_validation_results closes body-free command-hash results while activation stays external.",
        "- After ready, close_skill_route_discovery_focused_local_test_validation_with_outcome materializes body-free expected-hash outcomes and refreshes activation-external handoff/acceptance.",
        "- After recorded pass, skill_route_discovery_focused_validation_activation_external_handoff packages keep_activation_external while push/promotion/restart stay denied.",
        "- After ready handoff, skill_route_discovery_focused_validation_activation_external_acceptance accepts the package while activation stays external.",
        "- After acceptance, skill_route_discovery_focused_validation_residual_adjacent_queue packages residual fortress/Hy3 rows for agent_harness_eval_cluster_local_apply without skill unlock inheritance.",
        "- Residual fortress-style general_agent_project rows hand off to agent_harness_eval_cluster_local_apply instead of failing skill-route comparison.",
    ]
    retained = pipeline.get("retained_boundaries") or []
    if retained:
        retained_ids = ", ".join(
            str(row.get("proposal_id") or "unknown")
            for row in retained
            if isinstance(row, dict)
        )
        lines.append(f"- Retained review-only boundaries: {retained_ids or 'none'}")
    adjacent = pipeline.get("adjacent_general_agent_rows") or []
    if adjacent:
        adjacent_ids = ", ".join(
            str(row.get("proposal_id") or "unknown")
            for row in adjacent
            if isinstance(row, dict)
        )
        lines.append(f"- Adjacent general-agent harness-eval rows: {adjacent_ids or 'none'}")
    return lines


def render_self_evolution_task(
    proposals: list[dict[str, Any]],
    *,
    repo_path: Path,
    branch_name: str,
    self_model_snapshot: SelfModelSnapshot,
    digest_id: str,
    digest_generated_at: str,
    capability_theme_window: dict[str, Any] | None = None,
    upstream_evidence_capability_step: dict[str, Any] | None = None,
    skill_route_discovery_capability_pipeline: dict[str, Any] | None = None,
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
                f"   Autonomous local apply: {autonomous_local_apply_text(proposal)}",
            ]
        )
        implementation_scope = str(proposal.get("implementation_scope") or "").strip()
        if implementation_scope:
            proposal_lines.append(f"   Implementation scope: {implementation_scope}")
        validation_gate = str(proposal.get("validation_gate") or "").strip()
        if validation_gate:
            proposal_lines.append(f"   Validation gate: {validation_gate}")
        validation_task = str(proposal.get("validation_task") or "").strip()
        if validation_task:
            proposal_lines.append(f"   Validation task: {validation_task}")
    theme_lines = render_capability_theme_window_lines(capability_theme_window or {})
    capability_step_lines = render_upstream_evidence_capability_step_lines(
        upstream_evidence_capability_step or {}
    )
    skill_pipeline_lines = render_skill_route_discovery_capability_pipeline_lines(
        skill_route_discovery_capability_pipeline or {}
    )
    extra = f"\nAdditional operator instructions:\n{extra_instructions.strip()}\n" if extra_instructions.strip() else ""
    theme_id = str((capability_theme_window or {}).get("theme_id") or "")
    # Prefer the skill-route pipeline surface when that theme is active.
    if theme_id == "skill-route-discovery" and skill_pipeline_lines:
        capability_step_block = [
            "",
            "Capability theme window already selected this local step:",
            *skill_pipeline_lines,
        ]
    elif capability_step_lines:
        capability_step_block = [
            "",
            "Capability theme window already selected this local step:",
            *capability_step_lines,
        ]
    elif skill_pipeline_lines:
        capability_step_block = [
            "",
            "Capability theme window already selected this local step:",
            *skill_pipeline_lines,
        ]
    else:
        capability_step_block = []
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
            "Self-model context:",
            f"- Path: {self_model_snapshot.path}",
            f"- Exists before this run: {self_model_snapshot.exists}",
            f"- Snapshot sha256: {self_model_snapshot.sha256}",
            "- This file is a blank, revisable self-description, not a constitution and not a permission source.",
            "- Before choosing the code/doc/test change, read the self-model and decide whether it should be kept,",
            "  rewritten, contradicted, simplified, renamed, or left untouched.",
            "- Do not preserve any category merely because a previous run wrote it; the agent may invent or remove structure.",
            "- Ground any self-model edit in evidence from this run, including uncertainty or the possibility that the",
            "  self-model is currently ornamental rather than behavior-shaping.",
            "- If no other safe repository change is available, a self-model revision can be the justified improvement for the run.",
            "",
            "Self-model snapshot before this run:",
            "```markdown",
            self_model_snapshot.content.rstrip(),
            "```",
            "",
            "Goal:",
            "Implement a coherent self-improvement inspired by the proposals below.",
            "Choose scope by evidence strength, expected local benefit, rollback coverage, and validation coverage; the change may span files, modules, or behavior paths when that is the justified scope.",
            "Prefer direct behavior improvements when evidence and local validation support them; use reliability, validation, observability, tests, or documentation when those are the justified outcome.",
            "",
            "Capability theme window:",
            *theme_lines,
            *capability_step_block,
            "",
            "Digest evidence policy:",
            "- Treat the Source digest and proposal Evidence URLs as the primary context for this run.",
            "- Review only enough external evidence to extract one reusable lesson; do not re-run broad trend discovery.",
            "- If evidence is unavailable, stale, or too vague, record that uncertainty and improve local validation instead.",
            "",
            "Runtime policy budget:",
            "- Network: use only proposal Evidence URLs and narrowly required official documentation.",
            "- Filesystem: stay inside this repository and create a rollback point before edits.",
            "- Shell: run local validation commands sized to the changed behavior.",
            "- Capabilities: use configured local capabilities when they are needed for the proposal and validation can cover them.",
            "- Autonomy: make one coherent improvement or tightly connected change set; review only offensive behavior, abuse, unauthorized access, or privacy leakage.",
            "- Activation: record push, promotion, restart, runner, or remote-execution changes in artifacts and rely on configured supervisors for activation.",
            "",
            "Proposals:",
            *proposal_lines,
            "",
            "Operating constraints:",
            "- Stay inside this repository.",
            "- Apply local repository changes autonomously when they are logged, rollback-backed, validated, and outside the narrow safety boundary.",
            "- Use only capabilities and runtime configuration available to this run.",
            "- Record material filesystem and external actions in run artifacts.",
            "- Keep the diff legible enough to audit after the fact; do not shrink a justified behavior change merely to look conservative.",
            "- Treat the capability theme window as continuity pressure: deepen that slice unless the selected evidence proves it is exhausted or unsafe.",
            "- Prefer a behavior path, controller surface, or integration seam over another isolated fixture when the theme already has sufficient tests.",
            "- Add or update tests or docs whenever behavior changes.",
            "- If you modify the self-model, edit the file at the self-model path directly and explain why it changed.",
            "- Run validation that matches the changed behavior and include the result in the final answer.",
            "- If a proposal crosses the offensive-behavior or privacy-leakage boundary, keep it review-only and improve the boundary or tests instead.",
            "- If the proposals are too vague, prefer a reversible local experiment over another validation-report-only refinement.",
            "",
            "Completion criteria:",
            "- The repository has a concrete local diff on this branch, or a clear no-op explanation if no safe change exists.",
            "- The final answer summarizes changed files, whether the self-model changed, validation, and remaining review notes.",
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
            f"Capability theme: `{plan.capability_theme_window.get('theme_id', '')}`",
            (
                f"Upstream evidence capability step: "
                f"`{(plan.upstream_evidence_capability_step.get('selected_step') or {}).get('capability_action', '')}`"
                if plan.upstream_evidence_capability_step
                else "Upstream evidence capability step: none"
            ),
            (
                f"Skill route discovery capability pipeline: "
                f"`{(plan.skill_route_discovery_capability_pipeline.get('selected_step') or {}).get('capability_action', '')}`"
                if plan.skill_route_discovery_capability_pipeline
                else "Skill route discovery capability pipeline: none"
            ),
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
    write_self_model_snapshot(output_dir, plan.self_model_before, phase="before")
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
    repo_namespace = rollback_ref_repo_namespace(repo_path)
    rollback_ref = f"refs/blackhole-agent/rollback/{repo_namespace}/{timestamp}-{head[:12]}"
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


def rollback_ref_repo_namespace(repo_path: Path) -> str:
    """Return a short stable namespace for rollback refs from this checkout."""

    return hashlib.sha256(str(repo_path.resolve()).encode("utf-8")).hexdigest()[:8]


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
    require_codex_route: bool = True,
    claude_sdk_permission_mode: str | None = None,
    allow_claude_sdk_auto_permission_mode: bool = True,
    sandbox: str = "workspace-write",
    approval_policy: str = "never",
    ignore_user_config: bool = True,
    bypass_approvals_and_sandbox: bool = False,
    timeout_seconds: int = 3600,
    command_runner: Any = subprocess.run,
) -> SelfEvolutionRunResult:
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    monotonic_started = time.monotonic()
    config = CodexCliConfig(
        model=model,
        profile=profile,
        require_explicit_route=require_codex_route,
        sandbox=sandbox,
        approval_policy=approval_policy,
        ignore_user_config=ignore_user_config,
        bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
    )
    kernel = CodexCliKernel(config, command_runner=command_runner)
    codex_metadata = {
        "model": config.model,
        "profile": config.profile,
        "require_explicit_route": config.require_explicit_route,
        "claude_sdk_permission_mode": claude_sdk_permission_mode,
        "allow_claude_sdk_auto_permission_mode": allow_claude_sdk_auto_permission_mode,
        "sandbox": config.sandbox,
        "approval_policy": config.approval_policy,
        "ignore_user_config": config.ignore_user_config,
        "bypass_approvals_and_sandbox": config.bypass_approvals_and_sandbox,
    }
    result: CodexCliRunResult = kernel.run(
        plan.task,
        cwd=Path(plan.repo_path),
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
    )
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    elapsed_seconds = round(time.monotonic() - monotonic_started, 3)
    run_result = SelfEvolutionRunResult(
        command=result.command,
        returncode=result.returncode,
        task_path=result.task_path,
        last_message_path=result.last_message_path,
        result_path=result.result_path,
        branch_name=plan.branch_name,
        stdout_tail=result.stdout_tail,
        stderr_tail=result.stderr_tail,
        last_message=result.last_message,
    )
    (output_dir / "latest-self-evolution-run.json").write_text(
        json.dumps(
            {
                "command": run_result.command,
                "codex_cli": codex_metadata,
                "provider_preflight": result.provider_preflight,
                "returncode": run_result.returncode,
                "task_path": str(run_result.task_path),
                "last_message_path": str(run_result.last_message_path),
                "result_path": str(run_result.result_path),
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
    current_head = run_controller_command(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=Path(plan.repo_path),
        command_runner=command_runner,
    ).stdout.strip()
    proposal_controls = [
        proposal_manifest_control(proposal)
        for proposal in plan.proposals
        if str(proposal.get("proposal_id") or "").strip()
    ]
    manifest = {
        "schema_version": 1,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": elapsed_seconds,
        "source_digest_id": plan.source_digest_id,
        "source_digest_generated_at": plan.source_digest_generated_at,
        "capability_theme_window": dict(plan.capability_theme_window),
        "upstream_evidence_capability_step": dict(plan.upstream_evidence_capability_step),
        "skill_route_discovery_capability_pipeline": dict(
            plan.skill_route_discovery_capability_pipeline
        ),
        "repo_path": plan.repo_path,
        "branch_name": plan.branch_name,
        "target_head": current_head,
        "self_model_path": plan.self_model_path,
        "returncode": run_result.returncode,
        "codex_cli": codex_metadata,
        "provider_preflight": result.provider_preflight,
        "task_path": str(run_result.task_path),
        "last_message_path": str(run_result.last_message_path),
        "codex_result_path": str(run_result.result_path),
        "proposal_controls": proposal_controls,
        "replayable_validation_report": build_replayable_validation_report(plan, proposal_controls),
        "validation_gates": [
            str(proposal.get("validation_gate"))
            for proposal in plan.proposals
            if str(proposal.get("validation_gate") or "").strip()
        ],
        "proposal_ids": [
            str(proposal.get("proposal_id"))
            for proposal in plan.proposals
            if str(proposal.get("proposal_id") or "").strip()
        ],
        "evidence_urls": sorted(
            {
                str(url)
                for proposal in plan.proposals
                for url in proposal.get("evidence_urls", [])
                if str(url).strip()
            }
        ),
    }
    (output_dir / "latest-self-evolution-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_self_model_snapshot(
        output_dir,
        read_self_model_snapshot(Path(plan.repo_path), Path(plan.self_model_path)),
        phase="after",
    )
    return run_result


def run_self_evolution_grok(
    plan: SelfEvolutionPlan,
    *,
    output_dir: Path,
    model: str | None = None,
    require_explicit_route: bool = True,
    sandbox: str = "workspace",
    permission_mode: str = "bypassPermissions",
    timeout_seconds: int = 3600,
    command_runner: Any = subprocess.run,
) -> SelfEvolutionRunResult:
    """Run one self-evolution task through Grok CLI and preserve controller artifacts."""

    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    monotonic_started = time.monotonic()
    config = GrokCliConfig(
        model=model,
        require_explicit_route=require_explicit_route,
        sandbox=sandbox,
        permission_mode=permission_mode,
    )
    kernel = GrokCliKernel(config, command_runner=command_runner)
    grok_metadata = {
        "model": config.model,
        "require_explicit_route": config.require_explicit_route,
        "sandbox": config.sandbox,
        "permission_mode": config.permission_mode,
        "output_format": config.output_format,
        "no_memory": config.no_memory,
        "no_subagents": config.no_subagents,
        "disable_web_search": config.disable_web_search,
        "controller_owned_git_actions_denied": ["commit", "push"],
    }
    result: GrokCliRunResult = kernel.run(
        plan.task,
        cwd=Path(plan.repo_path),
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
    )
    finished_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    elapsed_seconds = round(time.monotonic() - monotonic_started, 3)
    run_result = SelfEvolutionRunResult(
        command=result.command,
        returncode=result.returncode,
        task_path=result.task_path,
        last_message_path=result.last_message_path,
        result_path=result.result_path,
        branch_name=plan.branch_name,
        stdout_tail=result.stdout_tail,
        stderr_tail=result.stderr_tail,
        last_message=result.last_message,
    )
    (output_dir / "latest-self-evolution-run.json").write_text(
        json.dumps(
            {
                "command": run_result.command,
                "kernel": "grok",
                "grok_cli": grok_metadata,
                "provider_preflight": result.provider_preflight,
                "returncode": run_result.returncode,
                "task_path": str(run_result.task_path),
                "last_message_path": str(run_result.last_message_path),
                "result_path": str(run_result.result_path),
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
    current_head = run_controller_command(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=Path(plan.repo_path),
        command_runner=command_runner,
    ).stdout.strip()
    proposal_controls = [
        proposal_manifest_control(proposal)
        for proposal in plan.proposals
        if str(proposal.get("proposal_id") or "").strip()
    ]
    manifest = {
        "schema_version": 1,
        "started_at": started_at,
        "finished_at": finished_at,
        "elapsed_seconds": elapsed_seconds,
        "source_digest_id": plan.source_digest_id,
        "source_digest_generated_at": plan.source_digest_generated_at,
        "capability_theme_window": dict(plan.capability_theme_window),
        "upstream_evidence_capability_step": dict(plan.upstream_evidence_capability_step),
        "skill_route_discovery_capability_pipeline": dict(
            plan.skill_route_discovery_capability_pipeline
        ),
        "repo_path": plan.repo_path,
        "branch_name": plan.branch_name,
        "target_head": current_head,
        "self_model_path": plan.self_model_path,
        "returncode": run_result.returncode,
        "kernel": "grok",
        "grok_cli": grok_metadata,
        "provider_preflight": result.provider_preflight,
        "task_path": str(run_result.task_path),
        "last_message_path": str(run_result.last_message_path),
        "grok_result_path": str(run_result.result_path),
        "proposal_controls": proposal_controls,
        "replayable_validation_report": build_replayable_validation_report(plan, proposal_controls),
        "validation_gates": [
            str(proposal.get("validation_gate"))
            for proposal in plan.proposals
            if str(proposal.get("validation_gate") or "").strip()
        ],
        "proposal_ids": [
            str(proposal.get("proposal_id"))
            for proposal in plan.proposals
            if str(proposal.get("proposal_id") or "").strip()
        ],
        "evidence_urls": sorted(
            {
                str(url)
                for proposal in plan.proposals
                for url in proposal.get("evidence_urls", [])
                if str(url).strip()
            }
        ),
    }
    (output_dir / "latest-self-evolution-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_self_model_snapshot(
        output_dir,
        read_self_model_snapshot(Path(plan.repo_path), Path(plan.self_model_path)),
        phase="after",
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
    repo_path: Path = Path("."),
    self_model_path: Path | None = None,
    proposal_mode: str = DEFAULT_PROPOSAL_MODE,
    proposal_model: str | None = None,
    proposal_profile: str | None = None,
    kernel: str = "codex",
    proposal_timeout_seconds: int = 180,
    ignore_user_config: bool = True,
    command_runner: Any = subprocess.run,
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
    heuristic_proposals = build_proposals(signals, memory=memory)
    digest = build_digest(
        normalized_repos,
        signals,
        state=state,
        generated_at=generated_at,
        source=trend_source,
        memory=memory,
        proposals=heuristic_proposals,
    )
    if validate_proposal_mode(proposal_mode) != "heuristic":
        digest["proposals"] = synthesize_digest_proposals(
            digest,
            signals,
            heuristic_proposals,
            mode=proposal_mode,
            output_dir=output_dir,
            repo_path=repo_path,
            self_model_path=self_model_path,
            model=proposal_model,
            profile=proposal_profile,
            kernel=kernel,
            ignore_user_config=ignore_user_config,
            timeout_seconds=proposal_timeout_seconds,
            command_runner=command_runner,
        )
        attach_upstream_evidence_capability_step(digest)
        attach_skill_route_discovery_capability_pipeline(digest)
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
    if kind == "PullRequestReviewEvent":
        pr = payload.get("pull_request") or {}
        review = payload.get("review") or {}
        title = _compact(pr.get("title") or "untitled pull request")
        action = payload.get("action") or "reviewed"
        state = _compact(review.get("state") or "review")
        return (
            f"{action} pull request review ({state}): {title}",
            review.get("html_url") or pr.get("html_url") or _repo_url(repo),
            _compact(review.get("body") or ""),
        )
    if kind == "PullRequestReviewCommentEvent":
        pr = payload.get("pull_request") or {}
        comment = payload.get("comment") or {}
        title = _compact(pr.get("title") or "untitled pull request")
        action = payload.get("action") or "commented"
        return (
            f"{action} pull request review comment: {title}",
            comment.get("html_url") or pr.get("html_url") or _repo_url(repo),
            _compact(comment.get("body") or ""),
        )
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
    kernel: str = typer.Option("codex", "--kernel", help="CLI kernel for LLM interpretation and mutation: codex or grok."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="blackhole-agent checkout to improve in plan/codex mode."),
    force_evolve: bool = typer.Option(False, "--force-evolve", help="Create a fallback self-evolution task even without matched signals."),
    branch_prefix: str = typer.Option("codex/blackhole-evolve", "--branch-prefix", help="Branch prefix used by mutation mode."),
    self_model_path: Path = typer.Option(DEFAULT_SELF_MODEL_PATH, "--self-model-path", help="Repository-relative self-model file for revisable self-recognition."),
    proposal_mode: str = typer.Option(DEFAULT_PROPOSAL_MODE, "--proposal-mode", help="One of: heuristic, llm, hybrid."),
    proposal_model: str | None = typer.Option(None, "--proposal-model", help="Model for read-only LLM proposal interpretation. Defaults to --model when omitted."),
    proposal_timeout_seconds: int = typer.Option(180, "--proposal-timeout-seconds", min=1, help="Timeout for read-only LLM proposal interpretation."),
    model: str | None = typer.Option(None, "-m", "--model", help="Model to pass to the selected CLI kernel."),
    profile: str | None = typer.Option(None, "--profile", help="Codex config profile to pass in codex mode."),
    require_codex_route: bool = typer.Option(True, "--require-codex-route/--allow-default-codex-route", help="Require codex mode to pass an explicit --model or --profile instead of relying on the CLI default route."),
    claude_sdk_permission_mode: str | None = typer.Option(None, "--claude-sdk-permission-mode", help="Claude SDK permission mode recorded for supervisor child compatibility."),
    allow_claude_sdk_auto_permission_mode: bool = typer.Option(True, "--allow-claude-sdk-auto-permission-mode/--disallow-claude-sdk-auto-permission-mode", help="Accept supervisor Claude SDK auto-permission metadata."),
    sandbox: str = typer.Option("workspace-write", "--sandbox", help="Sandbox profile for the selected CLI kernel."),
    approval_policy: str = typer.Option("never", "--approval-policy", help="Legacy compatibility option; current codex exec has no approval flag."),
    ignore_user_config: bool = typer.Option(True, "--ignore-user-config/--use-user-config", help="Ignore user Codex config in codex mode while keeping auth available."),
    bypass_approvals_and_sandbox: bool = typer.Option(False, "--bypass-approvals-and-sandbox", help="Enable autonomous full-access permission mode for the selected kernel."),
    allow_dirty: bool = typer.Option(False, "--allow-dirty", help="Allow mutation mode to start from a dirty worktree."),
    codex_timeout_seconds: int = typer.Option(3600, "--codex-timeout-seconds", min=1, help="Timeout for the selected CLI kernel run."),
    extra_instruction: str = typer.Option("", "--extra-instruction", help="Additional instruction appended to the self-evolution task."),
) -> None:
    # fmt: on
    repo_list = parse_comma_separated(repos)
    if evolution_mode not in {"digest", "plan", "codex"}:
        raise typer.BadParameter("--evolution-mode must be one of: digest, plan, codex")
    if kernel not in {"codex", "grok"}:
        raise typer.BadParameter("--kernel must be one of: codex, grok")
    if proposal_mode not in PROPOSAL_MODES:
        raise typer.BadParameter("--proposal-mode must be one of: heuristic, llm, hybrid")
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
            repo_path=repo_path.resolve(),
            self_model_path=self_model_path,
            proposal_mode=proposal_mode,
            proposal_model=proposal_model or model,
            proposal_profile=profile,
            kernel=kernel,
            proposal_timeout_seconds=proposal_timeout_seconds,
            ignore_user_config=ignore_user_config,
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
                self_model_path=self_model_path,
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
                    if kernel == "grok":
                        run_result = run_self_evolution_grok(
                            plan,
                            output_dir=output_dir,
                            model=model,
                            require_explicit_route=require_codex_route,
                            sandbox=sandbox,
                            permission_mode=(
                                "bypassPermissions" if bypass_approvals_and_sandbox else "dontAsk"
                            ),
                            timeout_seconds=codex_timeout_seconds,
                        )
                    else:
                        run_result = run_self_evolution_codex(
                            plan,
                            output_dir=output_dir,
                            model=model,
                            profile=profile,
                            require_codex_route=require_codex_route,
                            claude_sdk_permission_mode=claude_sdk_permission_mode,
                            allow_claude_sdk_auto_permission_mode=allow_claude_sdk_auto_permission_mode,
                            sandbox=sandbox,
                            approval_policy=approval_policy,
                            ignore_user_config=ignore_user_config,
                            bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
                            timeout_seconds=codex_timeout_seconds,
                        )
                    console.print(
                        f"{kernel.title()} kernel exited with {run_result.returncode}; last message: "
                        f"[bold green]{run_result.last_message_path}[/bold green]"
                    )
        if interval_seconds <= 0:
            break
        time.sleep(interval_seconds)


if __name__ == "__main__":
    app()
