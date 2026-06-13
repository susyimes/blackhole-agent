"""Hourly GitHub intake for a bounded blackhole-agent growth loop.

This controller is adapted from the mini-swe-agent `github_growth` runner. The
important change is the local mutation engine: blackhole-agent can hand a bounded
self-improvement task to the local Codex CLI kernel while keeping GitHub writes,
pushes, and PR creation outside the automatic path.
"""

import json
import os
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import typer
from rich.console import Console

from blackhole_agent.kernels.codex_cli import CodexCliConfig, CodexCliKernel, CodexCliRunResult

_HELP_TEXT = """Collect recent GitHub activity and turn it into reviewable growth proposals.

By default the command is read-only against GitHub and writes local digest/state
files. With `--evolution-mode plan` it turns signals into a concrete
self-improvement task. With `--evolution-mode codex` it creates a branch and asks
the local Codex CLI kernel to modify this repository locally.
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
    "WorkflowRunEvent",
}
HIGH_RISK_TERMS = ("auth", "credential", "secret", "security", "token")

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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthState":
        return cls(
            seen_event_ids=set(data.get("seen_event_ids", [])),
            last_seen_at_by_repo=dict(data.get("last_seen_at_by_repo", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seen_event_ids": sorted(self.seen_event_ids),
            "last_seen_at_by_repo": dict(sorted(self.last_seen_at_by_repo.items())),
        }


@dataclass(frozen=True)
class DigestWriteResult:
    """Paths written by one intake pass."""

    digest: dict[str, Any]
    json_path: Path
    markdown_path: Path
    state_path: Path


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


class GitHubEventsClient:
    """Small GitHub REST client for repository event feeds."""

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
        owner, name = parse_repo_spec(repo)
        response = self._session.get(
            f"{self._api_base_url}/repos/{owner}/{name}/events",
            headers=self._headers,
            params={"per_page": per_page},
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"GitHub events request failed for {repo}: HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError(f"GitHub events request failed for {repo}: expected a JSON list")
        return payload


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
    max_events: int,
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
        if len(selected) >= max_events:
            break
    return selected


def update_state(state: GrowthState, events: list[GitHubEvent]) -> None:
    for event in events:
        state.seen_event_ids.add(event.id)
        current = state.last_seen_at_by_repo.get(event.repo)
        if current is None or parse_github_timestamp(event.created_at) > parse_github_timestamp(current):
            state.last_seen_at_by_repo[event.repo] = event.created_at


def extract_growth_signals(events: list[GitHubEvent], *, topics: list[str]) -> list[GrowthSignal]:
    topic_terms = [topic.lower() for topic in topics]
    signals: list[GrowthSignal] = []
    for event in events:
        haystack = f"{event.kind} {event.title} {event.summary}".lower()
        matched_topics = [topic for topic in topic_terms if topic in haystack]
        if event.kind not in INTERESTING_EVENT_TYPES and not matched_topics:
            continue
        risk_flags = sorted({term for term in HIGH_RISK_TERMS if term in haystack})
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


def recommend_action(event: GitHubEvent, risk_flags: list[str]) -> str:
    if risk_flags:
        return "summarize the pattern and require human review before borrowing it"
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
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    digest_id = "github-growth-" + generated_at.replace("-", "").replace(":", "").replace("+00:00", "Z")
    return {
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
        "proposals": build_proposals(signals),
    }


def build_proposals(signals: list[GrowthSignal], *, limit: int = 5) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for index, signal in enumerate(signals[:limit], start=1):
        proposals.append(
            {
                "proposal_id": f"{signal.event_id}-{index}",
                "kind": classify_proposal_kind(signal),
                "summary": f"Borrow cautiously from {signal.repo}: {signal.title}. {signal.recommended_action}.",
                "evidence_urls": [signal.url] if signal.url else [],
                "requires_approval": True,
            }
        )
    return proposals


def classify_proposal_kind(signal: GrowthSignal) -> str:
    if signal.risk_flags:
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
        "## Sources",
        "",
    ]
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
                f"  - Requires approval: {proposal['requires_approval']}",
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
                "requires_approval": True,
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
                f"   Requires approval: {proposal.get('requires_approval', True)}",
            ]
        )
    extra = f"\nAdditional operator instructions:\n{extra_instructions.strip()}\n" if extra_instructions.strip() else ""
    return "\n".join(
        [
            "You are Codex running as the local kernel for blackhole-agent.",
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
            "Proposals:",
            *proposal_lines,
            "",
            "Operating constraints:",
            "- Stay inside this repository.",
            "- Do not read, print, modify, or commit secrets, tokens, credentials, or private user files.",
            "- Do not push, merge, publish packages, deploy, or call external write APIs.",
            "- Keep the diff focused enough for a human reviewer to understand quickly.",
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


def prepare_self_evolution_branch(
    plan: SelfEvolutionPlan,
    *,
    allow_dirty: bool = False,
    command_runner: Any = subprocess.run,
) -> None:
    repo_path = Path(plan.repo_path)
    if not allow_dirty:
        status = run_controller_command(["git", "status", "--porcelain"], cwd=repo_path, command_runner=command_runner)
        if status.stdout.strip():
            raise RuntimeError("Refusing self-evolution on a dirty worktree. Commit/stash changes or pass --allow-dirty.")
    run_controller_command(["git", "switch", "-c", plan.branch_name], cwd=repo_path, command_runner=command_runner, check=True)


def run_self_evolution_codex(
    plan: SelfEvolutionPlan,
    *,
    output_dir: Path,
    model: str | None = None,
    profile: str | None = None,
    sandbox: str = "workspace-write",
    approval_policy: str = "never",
    timeout_seconds: int = 3600,
    command_runner: Any = subprocess.run,
) -> SelfEvolutionRunResult:
    config = CodexCliConfig(
        model=model,
        profile=profile,
        sandbox=sandbox,
        approval_policy=approval_policy,
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
    repos: list[str],
    output_dir: Path,
    state_path: Path | None = None,
    token: str | None = None,
    topics: list[str] | None = None,
    lookback_hours: int = 1,
    max_events_per_repo: int = 100,
    client: GitHubEventsClient | None = None,
) -> DigestWriteResult:
    if not repos:
        raise ValueError("At least one repository is required")
    normalized_repos = ["/".join(parse_repo_spec(repo)) for repo in repos]
    state_file = state_path or output_dir / "state.json"
    state = load_state(state_file)
    github = client or GitHubEventsClient(token=token)

    events: list[GitHubEvent] = []
    for repo in normalized_repos:
        raw_events = github.list_repository_events(repo, per_page=max_events_per_repo)
        events.extend(
            select_new_events(repo, raw_events, state, lookback_hours=lookback_hours, max_events=max_events_per_repo)
        )
    events.sort(key=lambda event: parse_github_timestamp(event.created_at), reverse=True)
    signals = extract_growth_signals(events, topics=topics or list(DEFAULT_TOPICS))
    update_state(state, events)
    digest = build_digest(normalized_repos, signals, state=state)

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
    return DigestWriteResult(digest=digest, json_path=json_path, markdown_path=markdown_path, state_path=state_file)


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
    repos: str = typer.Option("", "--repos", "-r", help="Comma-separated GitHub repositories in owner/name form."),
    output_dir: Path = typer.Option(Path(".blackhole-agent/github-growth"), "--output-dir", "-o", help="Directory for digest and state files."),
    state_path: Path | None = typer.Option(None, "--state", help="State file path. Defaults to <output-dir>/state.json."),
    token_env: str = typer.Option("GITHUB_TOKEN", "--token-env", help="Environment variable containing a GitHub token."),
    topics: str = typer.Option("", "--topics", help="Comma-separated relevance terms. Defaults to agent/workflow/test/security topics."),
    lookback_hours: int = typer.Option(1, "--lookback-hours", min=1, help="Initial lookback window when no state exists."),
    max_events_per_repo: int = typer.Option(100, "--max-events-per-repo", min=1, max=100, help="GitHub event fetch limit per repo."),
    interval_seconds: int = typer.Option(0, "--interval-seconds", min=0, help="Run forever at this interval; 0 runs exactly once."),
    evolution_mode: str = typer.Option("digest", "--evolution-mode", help="One of: digest, plan, codex."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="blackhole-agent checkout to improve in plan/codex mode."),
    force_evolve: bool = typer.Option(False, "--force-evolve", help="Create a fallback self-evolution task even without matched signals."),
    branch_prefix: str = typer.Option("codex/blackhole-evolve", "--branch-prefix", help="Branch prefix used by codex mode."),
    model: str | None = typer.Option(None, "-m", "--model", help="Model to pass to Codex CLI in codex mode."),
    profile: str | None = typer.Option(None, "--profile", help="Codex config profile to pass in codex mode."),
    sandbox: str = typer.Option("workspace-write", "--sandbox", help="Codex sandbox for codex mode."),
    approval_policy: str = typer.Option("never", "--approval-policy", help="Codex approval policy for codex mode."),
    allow_dirty: bool = typer.Option(False, "--allow-dirty", help="Allow codex mode to start from a dirty worktree."),
    codex_timeout_seconds: int = typer.Option(3600, "--codex-timeout-seconds", min=1, help="Timeout for the Codex CLI kernel run."),
    extra_instruction: str = typer.Option("", "--extra-instruction", help="Additional instruction appended to the self-evolution task."),
) -> None:
    # fmt: on
    repo_list = parse_comma_separated(repos)
    if not repo_list:
        raise typer.BadParameter("Pass at least one repository with --repos owner/name")
    if evolution_mode not in {"digest", "plan", "codex"}:
        raise typer.BadParameter("--evolution-mode must be one of: digest, plan, codex")
    if evolution_mode == "codex" and interval_seconds > 0:
        raise typer.BadParameter("--evolution-mode codex is one-shot; use a scheduler to launch separate runs")
    topic_list = parse_comma_separated(topics) or list(DEFAULT_TOPICS)
    token = os.getenv(token_env)

    while True:
        result = run_intake_once(
            repos=repo_list,
            output_dir=output_dir,
            state_path=state_path,
            token=token,
            topics=topic_list,
            lookback_hours=lookback_hours,
            max_events_per_repo=max_events_per_repo,
        )
        console.print(f"Wrote {len(result.digest['items'])} item(s) to [bold green]{result.markdown_path}[/bold green]")
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
                    prepare_self_evolution_branch(plan, allow_dirty=allow_dirty)
                    run_result = run_self_evolution_codex(
                        plan,
                        output_dir=output_dir,
                        model=model,
                        profile=profile,
                        sandbox=sandbox,
                        approval_policy=approval_policy,
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
