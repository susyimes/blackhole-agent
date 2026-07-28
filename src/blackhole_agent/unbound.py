"""Single-agent, long-horizon evolution runtime for blackhole-agent.

Unbound deliberately does not consume the legacy GitHub-growth proposal
pipeline.  One logical agent owns one durable mission and one long-lived
worktree.  It may take many turns before asking the controller to record a
milestone.  Tests and lint remain useful evidence, but they are not themselves
treated as capability growth.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import typer
from rich.console import Console

from blackhole_agent.kernels.codex_cli import CodexCliConfig, CodexCliKernel
from blackhole_agent.kernels.grok_cli import GrokCliConfig, GrokCliKernel


app = typer.Typer(rich_markup_mode="rich", add_completion=False)
console = Console(highlight=False)

SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path(".blackhole-agent/unbound")
MISSION_STATUSES = frozenset({"active", "complete", "blocked", "stopped"})
TURN_STATUSES = frozenset({"continue", "milestone", "complete", "blocked"})
KERNELS = frozenset({"codex", "grok"})
RECENT_TURN_LIMIT = 8
STATE_HISTORY_LIMIT = 50
PROMPT_TEXT_LIMIT = 12_000
NON_BEHAVIOR_PREFIXES = (
    ".blackhole-agent/",
    "artifacts/",
    "docs/",
    "tests/",
)
NON_BEHAVIOR_FILENAMES = {
    "readme",
    "readme.md",
    "changelog",
    "changelog.md",
    "license",
    "license.md",
}


@dataclass
class UnboundMission:
    """Durable state for one long-horizon single-agent mission."""

    schema_version: int
    mission_id: str
    created_at: str
    updated_at: str
    repo_path: str
    workspace_path: str
    branch: str
    target_branch: str
    goal: str = ""
    done_when: str = ""
    status: str = "active"
    stage: str = "genesis"
    iteration: int = 0
    milestone_count: int = 0
    kernel: str = "grok"
    model: str | None = None
    profile: str | None = None
    timeout_seconds: int = 7200
    session_id: str = ""
    session_started: bool = False
    base_head: str = ""
    last_milestone_head: str = ""
    current_strategy: str = ""
    next_step: str = ""
    last_summary: str = ""
    last_error: str = ""
    recent_turns: list[dict[str, Any]] = field(default_factory=list)
    milestones: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnboundMission":
        known = {item.name for item in fields(cls)}
        values = {key: value for key, value in payload.items() if key in known}
        return cls(**values)


@dataclass(frozen=True)
class TurnDecision:
    """Structured decision returned by the single execution agent."""

    status: str
    summary: str
    strategy: str
    next_step: str
    capability_delta: str
    outcome_evidence: tuple[str, ...]
    validation: tuple[dict[str, Any], ...]
    done_when_met: bool
    commit_message: str
    mission_goal: str
    done_when: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TurnDecision":
        raw_status = str(payload.get("status") or "continue").strip().lower()
        aliases = {"working": "continue", "done": "complete", "finished": "complete"}
        status = aliases.get(raw_status, raw_status)
        if status not in TURN_STATUSES:
            status = "continue"
        return cls(
            status=status,
            summary=str(payload.get("summary") or "").strip(),
            strategy=str(payload.get("strategy") or "").strip(),
            next_step=str(payload.get("next_step") or "").strip(),
            capability_delta=str(payload.get("capability_delta") or "").strip(),
            outcome_evidence=tuple(normalize_evidence(payload.get("outcome_evidence"))),
            validation=tuple(normalize_validation(payload.get("validation"))),
            done_when_met=bool(payload.get("done_when_met")),
            commit_message=str(payload.get("commit_message") or "").strip(),
            mission_goal=str(payload.get("mission_goal") or "").strip(),
            done_when=str(payload.get("done_when") or "").strip(),
        )


@dataclass(frozen=True)
class KernelTurnResult:
    """Provider-neutral result used by the mission controller."""

    kernel: str
    last_message: str
    session_id: str
    command: tuple[str, ...]
    result_path: str


@dataclass(frozen=True)
class MilestoneGate:
    """Outcome-level milestone decision."""

    requested: bool
    accepted: bool
    reasons: tuple[str, ...]
    changed_paths: tuple[str, ...]
    behavior_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compact_utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str, *, limit: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug[:limit].rstrip("-") or "mission")


def normalize_evidence(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = json.dumps(item, sort_keys=True, ensure_ascii=False)
        else:
            text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def normalize_validation(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                normalized.append({"command": "", "exit_code": None, "summary": item.strip()})
            continue
        if not isinstance(item, dict):
            continue
        exit_code = item.get("exit_code")
        if not isinstance(exit_code, int):
            exit_code = None
        normalized.append(
            {
                "command": str(item.get("command") or "").strip(),
                "exit_code": exit_code,
                "summary": str(item.get("summary") or item.get("result") or "").strip(),
            }
        )
    return normalized


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False) + "\n")


def load_mission(state_path: Path) -> UnboundMission:
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Mission state must be a JSON object: {state_path}")
    state = UnboundMission.from_dict(payload)
    if state.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported unbound mission schema {state.schema_version}; expected {SCHEMA_VERSION}."
        )
    if state.status not in MISSION_STATUSES:
        raise ValueError(f"Unsupported mission status: {state.status}")
    return state


def save_mission(state_path: Path, state: UnboundMission) -> None:
    state.updated_at = utc_now_iso()
    atomic_write_json(state_path, asdict(state))


def mission_root(repo_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return output_dir.resolve() if output_dir.is_absolute() else (repo_path / output_dir).resolve()


def latest_pointer_path(repo_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return mission_root(repo_path, output_dir) / "latest-mission.json"


def resolve_state_path(
    *,
    state_path: Path | None,
    repo_path: Path,
    mission_id: str = "",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Path:
    if state_path is not None:
        resolved = state_path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Mission state does not exist: {resolved}")
        return resolved
    root = mission_root(repo_path.resolve(), output_dir)
    if mission_id:
        resolved = root / "missions" / mission_id / "state.json"
    else:
        pointer = latest_pointer_path(repo_path.resolve(), output_dir)
        if not pointer.exists():
            raise FileNotFoundError("No latest Unbound mission has been recorded.")
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        resolved = Path(str(payload.get("state_path") or ""))
    if not resolved.exists():
        raise FileNotFoundError(f"Mission state does not exist: {resolved}")
    return resolved.resolve()


def run_command(
    command: list[str],
    *,
    cwd: Path,
    command_runner: Callable[..., Any] = subprocess.run,
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess:
    completed = command_runner(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        details = stderr or stdout or f"exit code {completed.returncode}"
        raise RuntimeError(f"{' '.join(command)} failed: {details}")
    return completed


def git_text(
    repo_path: Path,
    arguments: list[str],
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> str:
    return (run_command(arguments, cwd=repo_path, command_runner=command_runner).stdout or "").strip()


def git_head(
    repo_path: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> str:
    return git_text(repo_path, ["git", "rev-parse", "--verify", "HEAD"], command_runner=command_runner)


def create_mission(
    *,
    repo_path: Path,
    goal: str = "",
    done_when: str = "",
    kernel: str = "grok",
    model: str | None = None,
    profile: str | None = None,
    target_branch: str = "main",
    branch_prefix: str = "unbound",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    worktree_parent: Path | None = None,
    timeout_seconds: int = 7200,
    command_runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Create one durable mission branch, worktree, and state file."""

    repo_path = repo_path.resolve()
    if kernel not in KERNELS:
        raise ValueError(f"kernel must be one of: {', '.join(sorted(KERNELS))}")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be greater than zero")
    run_command(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo_path,
        command_runner=command_runner,
    )
    run_command(
        ["git", "rev-parse", "--verify", target_branch],
        cwd=repo_path,
        command_runner=command_runner,
    )

    mission_id = f"{compact_utc_timestamp()}-{uuid.uuid4().hex[:8]}"
    branch = f"{branch_prefix.strip('/')}/{slugify(goal or 'autonomous-genesis')}-{mission_id[-8:]}"
    parent = (
        worktree_parent.resolve()
        if worktree_parent is not None
        else repo_path.parent / f".{repo_path.name}-unbound-worktrees"
    )
    parent.mkdir(parents=True, exist_ok=True)
    workspace = parent / mission_id
    run_command(
        ["git", "worktree", "add", "-b", branch, str(workspace), target_branch],
        cwd=repo_path,
        command_runner=command_runner,
    )
    base_head = git_head(workspace, command_runner=command_runner)
    root = mission_root(repo_path, output_dir)
    mission_dir = root / "missions" / mission_id
    state_path = mission_dir / "state.json"
    now = utc_now_iso()
    state = UnboundMission(
        schema_version=SCHEMA_VERSION,
        mission_id=mission_id,
        created_at=now,
        updated_at=now,
        repo_path=str(repo_path),
        workspace_path=str(workspace),
        branch=branch,
        target_branch=target_branch,
        goal=goal.strip(),
        done_when=done_when.strip(),
        status="active",
        stage="execution" if goal.strip() and done_when.strip() else "genesis",
        kernel=kernel,
        model=model,
        profile=profile,
        timeout_seconds=timeout_seconds,
        session_id=str(uuid.uuid4()) if kernel == "grok" else "",
        base_head=base_head,
        last_milestone_head=base_head,
    )
    save_mission(state_path, state)
    atomic_write_json(
        root / "latest-mission.json",
        {
            "mission_id": mission_id,
            "state_path": str(state_path.resolve()),
            "workspace_path": str(workspace.resolve()),
            "updated_at": now,
        },
    )
    append_jsonl(
        mission_dir / "events.jsonl",
        {
            "event": "mission.created",
            "at": now,
            "mission_id": mission_id,
            "goal": state.goal,
            "done_when": state.done_when,
            "branch": branch,
            "base_head": base_head,
        },
    )
    return state_path.resolve()


def compact_text(value: str, *, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    head = max(0, limit // 2)
    tail = max(0, limit - head)
    return f"{text[:head]}\n... compacted by controller ...\n{text[-tail:]}"


def repository_snapshot(
    state: UnboundMission,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    workspace = Path(state.workspace_path)
    status = git_text(workspace, ["git", "status", "--short"], command_runner=command_runner)
    diff_stat = git_text(workspace, ["git", "diff", "--stat"], command_runner=command_runner)
    recent_commits = git_text(
        workspace,
        ["git", "log", "-5", "--oneline", "--decorate"],
        command_runner=command_runner,
    )
    return {
        "head": git_head(workspace, command_runner=command_runner),
        "status": compact_text(status, limit=4_000),
        "diff_stat": compact_text(diff_stat, limit=4_000),
        "recent_commits": compact_text(recent_commits, limit=2_000),
    }


def build_turn_prompt(state: UnboundMission, snapshot: dict[str, Any], *, state_path: Path) -> str:
    """Render compact, outcome-oriented context for one continuing turn."""

    if state.stage == "genesis":
        mission_block = (
            "Mission genesis is still open. Inspect the repository and choose one ambitious, high-impact capability "
            "mission. Define any missing mission_goal or done_when field in the response. Preserve an "
            "operator-supplied field unless repository evidence makes it impossible. You may begin implementation "
            "in the same turn when the direction is clear.\n\n"
            f"Operator-supplied goal, if any:\n{state.goal or '(not supplied)'}\n\n"
            f"Operator-supplied done_when, if any:\n{state.done_when or '(not supplied)'}"
        )
    else:
        mission_block = f"Mission goal:\n{state.goal}\n\nDone when:\n{state.done_when}"
    history = [
        {
            "iteration": item.get("iteration"),
            "effective_status": item.get("effective_status"),
            "summary": item.get("summary"),
            "capability_delta": item.get("capability_delta"),
            "next_step": item.get("next_step"),
            "commit_sha": item.get("commit_sha"),
        }
        for item in state.recent_turns[-RECENT_TURN_LIMIT:]
    ]
    prompt = f"""You are Blackhole Unbound, the single long-running agent responsible for this mission.

There are no child agents in this version. Do not spawn, delegate to, fork, or simulate subagents. Work directly.

{mission_block}

Mission state:
- Mission id: {state.mission_id}
- Stage: {state.stage}
- Iteration about to run: {state.iteration + 1}
- Milestones already recorded: {state.milestone_count}
- Persistent branch: {state.branch}
- Workspace: {state.workspace_path}
- Current HEAD: {snapshot.get("head", "")}
- Last milestone HEAD: {state.last_milestone_head}
- State file: {state_path}

Current repository state:
```text
git status --short
{snapshot.get("status") or "(clean)"}

git diff --stat
{snapshot.get("diff_stat") or "(no unstaged diff)"}

recent commits
{snapshot.get("recent_commits") or "(none)"}
```

Recent mission turns:
```json
{json.dumps(history, indent=2, ensure_ascii=False)}
```

Operating model:
- Pursue capability growth and the mission outcome. Do not optimize for small diffs, hourly commits, or activity.
- Continue unfinished work from this persistent worktree. A turn may end with substantial work still in progress.
- You may inspect the web, install dependencies, run tools and services, rewrite or delete existing architecture,
  change prompts/planners/evaluators, and modify this Unbound runtime itself when that advances the mission.
- Prefer simplification or replacement over adding another compatibility layer to legacy generated machinery.
- Git, commits, pushes, and restarts are available capabilities, not forbidden actions. The controller records
  milestone commits only when you report a demonstrated capability delta; avoid meaningless checkpoint commits.
- Tests, lint, documents, and artifacts are supporting evidence. They are not a capability milestone by themselves.
- Work autonomously now: inspect, edit, run, and validate. Do not return a plan-only answer unless blocked.
- Keep the final response compact. Repository context should be read on demand instead of copied into the response.

Milestone semantics:
- status=continue: preserve current work and continue next turn; no controller milestone commit.
- status=milestone: a reusable behavior or capability increment now works and has concrete outcome evidence.
- status=complete: done_when is met, with concrete outcome evidence.
- status=blocked: progress genuinely cannot continue without an external state change.
- milestone/complete require a non-empty capability_delta, outcome_evidence, and at least one changed behavior path
  outside docs/tests/artifacts. Passing tests alone is not enough.

Return only one JSON object with exactly this shape:
{{
  "status": "continue|milestone|complete|blocked",
  "mission_goal": "required during genesis, otherwise optional",
  "done_when": "required during genesis, otherwise optional",
  "summary": "what materially happened this turn",
  "strategy": "current approach, revised freely when evidence changes",
  "next_step": "the concrete continuation if not complete",
  "capability_delta": "new working ability; empty when none is demonstrated yet",
  "outcome_evidence": ["path, command result, benchmark, or observable behavior"],
  "validation": [{{"command": "exact command", "exit_code": 0, "summary": "what it proved"}}],
  "done_when_met": false,
  "commit_message": "semantic milestone message; optional unless milestone/complete"
}}
"""
    return compact_text(prompt, limit=PROMPT_TEXT_LIMIT)


def extract_json_decision(message: str) -> dict[str, Any]:
    """Find the last valid decision object in a model response."""

    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, character in enumerate(message):
        if character != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(message[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "status" in payload:
            candidates.append(payload)
    if not candidates:
        raise ValueError("Kernel final message did not contain a JSON decision object.")
    return candidates[-1]


def invoke_kernel_turn(
    state: UnboundMission,
    prompt: str,
    turn_dir: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> KernelTurnResult:
    """Run one turn with full tool authority and no child-agent capability."""

    workspace = Path(state.workspace_path)
    kernel_dir = turn_dir / "kernel"
    if state.kernel == "grok":
        if not state.session_id:
            state.session_id = str(uuid.uuid4())
        starting_session = not state.session_started
        config = GrokCliConfig(
            model=state.model,
            require_explicit_route=False,
            sandbox="danger-full-access",
            permission_mode="bypassPermissions",
            no_memory=False,
            no_subagents=True,
            disable_web_search=False,
            deny_rules=(),
            session_id=state.session_id if starting_session else None,
            resume_session_id=state.session_id if not starting_session else None,
        )
        # A Grok process can create its session before returning a parseable
        # final message. Persist resume semantics on the failure path too,
        # rather than trying to create the same UUID again.
        state.session_started = True
        result = GrokCliKernel(config, command_runner=command_runner).run(
            prompt,
            cwd=workspace,
            output_dir=kernel_dir,
            timeout_seconds=state.timeout_seconds,
        )
        return KernelTurnResult(
            kernel="grok",
            last_message=result.last_message,
            session_id=state.session_id,
            command=tuple(result.command),
            result_path=str(result.result_path),
        )
    if state.kernel == "codex":
        config = CodexCliConfig(
            model=state.model,
            profile=state.profile,
            require_explicit_route=False,
            sandbox="danger-full-access",
            ignore_user_config=False,
            ephemeral=False,
            bypass_approvals_and_sandbox=True,
            resume_session_id=state.session_id if state.session_started and state.session_id else None,
            json_output=True,
        )
        result = CodexCliKernel(config, command_runner=command_runner).run(
            prompt,
            cwd=workspace,
            output_dir=kernel_dir,
            timeout_seconds=state.timeout_seconds,
        )
        return KernelTurnResult(
            kernel="codex",
            last_message=result.last_message,
            session_id=result.session_id or state.session_id,
            command=tuple(result.command),
            result_path=str(result.result_path),
        )
    raise ValueError(f"Unsupported kernel: {state.kernel}")


def status_changed_paths(
    workspace: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> list[str]:
    output = git_text(
        workspace,
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        command_runner=command_runner,
    )
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        value = line[3:].strip()
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        value = value.strip('"').replace("\\", "/")
        if value:
            paths.append(value)
    return paths


def changed_paths_since(
    workspace: Path,
    base_head: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> list[str]:
    paths: list[str] = []
    if base_head:
        completed = run_command(
            ["git", "diff", "--name-only", f"{base_head}..HEAD"],
            cwd=workspace,
            command_runner=command_runner,
            check=False,
        )
        if completed.returncode == 0:
            paths.extend((completed.stdout or "").splitlines())
    paths.extend(status_changed_paths(workspace, command_runner=command_runner))
    return sorted({path.strip().replace("\\", "/") for path in paths if path.strip()})


def is_behavior_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").lstrip("./")
    lowered = normalized.lower()
    if not normalized or any(lowered.startswith(prefix) for prefix in NON_BEHAVIOR_PREFIXES):
        return False
    name = Path(lowered).name
    if name in NON_BEHAVIOR_FILENAMES:
        return False
    if Path(lowered).suffix in {".md", ".rst"}:
        return False
    return True


def successful_validation(validation: tuple[dict[str, Any], ...]) -> bool:
    return any(
        str(item.get("command") or "").strip() and item.get("exit_code") == 0
        for item in validation
    )


def evaluate_milestone(
    decision: TurnDecision,
    *,
    changed_paths: list[str],
) -> MilestoneGate:
    requested = decision.status in {"milestone", "complete"}
    behavior_paths = [path for path in changed_paths if is_behavior_path(path)]
    if not requested:
        return MilestoneGate(
            requested=False,
            accepted=False,
            reasons=(),
            changed_paths=tuple(changed_paths),
            behavior_paths=tuple(behavior_paths),
        )
    reasons: list[str] = []
    if not changed_paths:
        reasons.append("no repository change exists since the previous milestone")
    if not behavior_paths:
        reasons.append("changes are limited to docs, tests, artifacts, or controller state")
    if not decision.capability_delta:
        reasons.append("capability_delta is empty")
    if not decision.outcome_evidence:
        reasons.append("outcome_evidence is empty")
    if not successful_validation(decision.validation):
        reasons.append("no successful exact validation command was reported")
    if decision.status == "complete" and not decision.done_when_met:
        reasons.append("complete was requested but done_when_met is false")
    return MilestoneGate(
        requested=True,
        accepted=not reasons,
        reasons=tuple(reasons),
        changed_paths=tuple(changed_paths),
        behavior_paths=tuple(behavior_paths),
    )


def semantic_commit_message(decision: TurnDecision, milestone_number: int) -> str:
    candidate = decision.commit_message or decision.capability_delta or decision.summary
    first_line = " ".join(candidate.splitlines()).strip()
    if len(first_line) > 88:
        first_line = first_line[:85].rstrip() + "..."
    return f"Blackhole unbound milestone {milestone_number}: {first_line or 'capability increment'}"


def commit_milestone(
    workspace: Path,
    decision: TurnDecision,
    milestone_number: int,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> str:
    """Commit pending mission changes; preserve an agent-authored commit when already clean."""

    status = status_changed_paths(workspace, command_runner=command_runner)
    if status:
        run_command(["git", "add", "-A"], cwd=workspace, command_runner=command_runner)
        staged = run_command(
            ["git", "diff", "--cached", "--quiet"],
            cwd=workspace,
            command_runner=command_runner,
            check=False,
        )
        if staged.returncode == 1:
            run_command(
                ["git", "commit", "-m", semantic_commit_message(decision, milestone_number)],
                cwd=workspace,
                command_runner=command_runner,
            )
        elif staged.returncode != 0:
            raise RuntimeError("Unable to inspect staged milestone changes.")
    return git_head(workspace, command_runner=command_runner)


@contextmanager
def mission_turn_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.parent / "turn.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(f"Another Unbound turn owns this mission: {lock_path}") from error
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def run_unbound_turn(
    state_path: Path,
    *,
    kernel_runner: Callable[..., KernelTurnResult] = invoke_kernel_turn,
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Execute and persist one logical turn of an Unbound mission."""

    state_path = state_path.resolve()
    with mission_turn_lock(state_path):
        state = load_mission(state_path)
        if state.status != "active":
            raise RuntimeError(f"Mission is {state.status}; resume it before running another turn.")
        workspace = Path(state.workspace_path)
        if not workspace.exists():
            raise FileNotFoundError(f"Mission workspace does not exist: {workspace}")
        iteration = state.iteration + 1
        started_at = utc_now_iso()
        turn_dir = state_path.parent / "turns" / f"{iteration:04d}"
        turn_dir.mkdir(parents=True, exist_ok=True)
        snapshot = repository_snapshot(state, command_runner=command_runner)
        prompt = build_turn_prompt(state, snapshot, state_path=state_path)
        (turn_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        kernel_result: KernelTurnResult | None = None
        try:
            kernel_result = kernel_runner(
                state,
                prompt,
                turn_dir,
                command_runner=command_runner,
            )
            (turn_dir / "final-message.md").write_text(kernel_result.last_message, encoding="utf-8")
            decision = TurnDecision.from_payload(extract_json_decision(kernel_result.last_message))
        except Exception as error:
            if kernel_result is not None:
                state.session_id = kernel_result.session_id or state.session_id
                state.session_started = bool(state.session_id) or state.session_started
            state.iteration = iteration
            state.last_error = str(error)
            state.last_summary = "Kernel turn failed before a structured decision was recorded."
            failure_record = {
                "schema_version": SCHEMA_VERSION,
                "iteration": iteration,
                "started_at": started_at,
                "finished_at": utc_now_iso(),
                "kernel": state.kernel,
                "requested_status": "error",
                "effective_status": "error",
                "summary": state.last_summary,
                "error": str(error),
            }
            atomic_write_json(turn_dir / "turn.json", failure_record)
            append_jsonl(state_path.parent / "events.jsonl", {"event": "turn.failed", **failure_record})
            state.recent_turns = [*state.recent_turns, failure_record][-STATE_HISTORY_LIMIT:]
            save_mission(state_path, state)
            raise

        if state.stage == "genesis":
            if decision.mission_goal:
                state.goal = decision.mission_goal
            if decision.done_when:
                state.done_when = decision.done_when
            if state.goal and state.done_when:
                state.stage = "execution"

        changed_paths = changed_paths_since(
            workspace,
            state.last_milestone_head,
            command_runner=command_runner,
        )
        gate = evaluate_milestone(decision, changed_paths=changed_paths)
        effective_status = decision.status
        commit_sha = ""
        milestone_number = state.milestone_count + 1
        if gate.requested and not gate.accepted:
            effective_status = "continue"
        elif gate.accepted:
            try:
                commit_sha = commit_milestone(
                    workspace,
                    decision,
                    milestone_number,
                    command_runner=command_runner,
                )
            except Exception as error:
                gate = MilestoneGate(
                    requested=True,
                    accepted=False,
                    reasons=(*gate.reasons, f"milestone commit failed: {error}"),
                    changed_paths=gate.changed_paths,
                    behavior_paths=gate.behavior_paths,
                )
                effective_status = "continue"
            else:
                state.milestone_count = milestone_number
                state.last_milestone_head = commit_sha
                milestone = {
                    "number": milestone_number,
                    "iteration": iteration,
                    "at": utc_now_iso(),
                    "commit_sha": commit_sha,
                    "capability_delta": decision.capability_delta,
                    "outcome_evidence": list(decision.outcome_evidence),
                }
                state.milestones.append(milestone)
                append_jsonl(
                    state_path.parent / "events.jsonl",
                    {"event": "mission.milestone", "mission_id": state.mission_id, **milestone},
                )

        if effective_status == "complete":
            state.status = "complete"
        elif effective_status == "blocked":
            state.status = "blocked"
        else:
            state.status = "active"
        state.iteration = iteration
        state.session_id = kernel_result.session_id or state.session_id
        state.session_started = bool(state.session_id) or state.session_started
        state.current_strategy = decision.strategy
        state.next_step = decision.next_step
        state.last_summary = decision.summary
        state.last_error = ""

        record = {
            "schema_version": SCHEMA_VERSION,
            "iteration": iteration,
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "kernel": kernel_result.kernel,
            "session_id": state.session_id,
            "requested_status": decision.status,
            "effective_status": effective_status,
            "summary": decision.summary,
            "strategy": decision.strategy,
            "next_step": decision.next_step,
            "capability_delta": decision.capability_delta,
            "outcome_evidence": list(decision.outcome_evidence),
            "validation": list(decision.validation),
            "done_when_met": decision.done_when_met,
            "mission_goal": state.goal,
            "done_when": state.done_when,
            "changed_paths": changed_paths,
            "milestone_gate": gate.to_dict(),
            "commit_sha": commit_sha,
            "command": list(kernel_result.command),
            "kernel_result_path": kernel_result.result_path,
        }
        atomic_write_json(turn_dir / "turn.json", record)
        append_jsonl(
            state_path.parent / "events.jsonl",
            {"event": "turn.completed", "mission_id": state.mission_id, **record},
        )
        state.recent_turns = [*state.recent_turns, record][-STATE_HISTORY_LIMIT:]
        save_mission(state_path, state)
        return record


def run_reloadable_tick(state_path: Path) -> int:
    """Run a tick in a fresh interpreter loaded from the mission worktree."""

    state = load_mission(state_path)
    workspace = Path(state.workspace_path)
    env = os.environ.copy()
    workspace_source = workspace / "src"
    workspace_runtime = workspace_source / "blackhole_agent" / "unbound.py"
    # A newly implemented but not-yet-committed controller can create a
    # worktree from an older target branch. Keep that first mission runnable
    # from the invoking checkout; once the worktree contains Unbound, future
    # turns load the evolving copy.
    source_path = str(
        workspace_source if workspace_runtime.exists() else Path(__file__).resolve().parents[1]
    )
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = source_path + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "blackhole_agent.unbound",
            "tick",
            "--state-path",
            str(state_path),
        ],
        cwd=workspace,
        env=env,
        check=False,
    )
    return int(completed.returncode)


def run_mission_loop(
    state_path: Path,
    *,
    max_turns: int = 0,
    interval_seconds: int = 0,
    reload_between_turns: bool = True,
) -> int:
    """Run until completion/blocking or the optional turn bound is reached."""

    turns = 0
    while True:
        state = load_mission(state_path)
        if state.status != "active":
            return 0 if state.status == "complete" else 2
        if max_turns and turns >= max_turns:
            return 0
        if reload_between_turns:
            returncode = run_reloadable_tick(state_path)
            if returncode != 0:
                return returncode
        else:
            run_unbound_turn(state_path)
        turns += 1
        state = load_mission(state_path)
        if state.status != "active":
            return 0 if state.status == "complete" else 2
        if interval_seconds > 0:
            time.sleep(interval_seconds)


def mission_summary(state: UnboundMission, state_path: Path) -> dict[str, Any]:
    return {
        "mission_id": state.mission_id,
        "status": state.status,
        "stage": state.stage,
        "goal": state.goal,
        "done_when": state.done_when,
        "iteration": state.iteration,
        "milestone_count": state.milestone_count,
        "kernel": state.kernel,
        "model": state.model,
        "branch": state.branch,
        "workspace_path": state.workspace_path,
        "state_path": str(state_path),
        "last_milestone_head": state.last_milestone_head,
        "current_strategy": state.current_strategy,
        "next_step": state.next_step,
        "last_summary": state.last_summary,
        "last_error": state.last_error,
    }


@app.command(help="Create a durable single-agent mission and its long-lived worktree.")
def start(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository to evolve."),
    goal: str = typer.Option("", "--goal", help="Mission goal. Leave blank for autonomous genesis."),
    done_when: str = typer.Option("", "--done-when", help="Outcome-level completion contract."),
    kernel: str = typer.Option("grok", "--kernel", help="Execution kernel: grok or codex."),
    model: str | None = typer.Option(None, "--model", "-m", help="Optional model route."),
    profile: str | None = typer.Option(None, "--profile", help="Optional Codex profile."),
    target_branch: str = typer.Option("main", "--target-branch", help="Branch used as the mission base."),
    branch_prefix: str = typer.Option("unbound", "--branch-prefix", help="Persistent mission branch prefix."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", help="Durable mission state root."),
    worktree_parent: Path | None = typer.Option(None, "--worktree-parent", help="Mission worktree parent."),
    timeout_seconds: int = typer.Option(7200, "--timeout-seconds", min=1, help="Maximum time for one agent turn."),
    run_now: bool = typer.Option(False, "--run/--no-run", help="Start the mission loop immediately."),
    max_turns: int = typer.Option(0, "--max-turns", min=0, help="Bound this invocation; 0 is unbounded."),
    interval_seconds: int = typer.Option(0, "--interval-seconds", min=0, help="Delay between continuing turns."),
) -> None:
    try:
        state_path = create_mission(
            repo_path=repo_path,
            goal=goal,
            done_when=done_when,
            kernel=kernel,
            model=model,
            profile=profile,
            target_branch=target_branch,
            branch_prefix=branch_prefix,
            output_dir=output_dir,
            worktree_parent=worktree_parent,
            timeout_seconds=timeout_seconds,
        )
    except (ValueError, RuntimeError) as error:
        raise typer.BadParameter(str(error)) from error
    state = load_mission(state_path)
    console.print_json(data=mission_summary(state, state_path))
    if run_now:
        raise typer.Exit(
            run_mission_loop(
                state_path,
                max_turns=max_turns,
                interval_seconds=interval_seconds,
                reload_between_turns=True,
            )
        )


@app.command(help="Run exactly one continuing turn for an existing mission.")
def tick(
    state_path: Path = typer.Option(..., "--state-path", help="Absolute or relative mission state path."),
) -> None:
    try:
        record = run_unbound_turn(state_path)
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        console.print(f"Unbound turn failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=record)


@app.command(help="Continue a mission until complete, blocked, failed, or explicitly bounded.")
def run(
    state_path: Path | None = typer.Option(None, "--state-path", help="Mission state path."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository containing mission state."),
    mission_id: str = typer.Option("", "--mission-id", help="Mission id; defaults to latest."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", help="Durable mission state root."),
    max_turns: int = typer.Option(0, "--max-turns", min=0, help="Bound this invocation; 0 is unbounded."),
    interval_seconds: int = typer.Option(0, "--interval-seconds", min=0, help="Delay between turns."),
    reload_between_turns: bool = typer.Option(
        True,
        "--reload-between-turns/--keep-controller-loaded",
        help="Reload worker code from the evolving mission worktree each turn.",
    ),
) -> None:
    try:
        resolved = resolve_state_path(
            state_path=state_path,
            repo_path=repo_path,
            mission_id=mission_id,
            output_dir=output_dir,
        )
        exit_code = run_mission_loop(
            resolved,
            max_turns=max_turns,
            interval_seconds=interval_seconds,
            reload_between_turns=reload_between_turns,
        )
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        console.print(f"Unbound mission failed: {error}", style="red")
        raise typer.Exit(1) from error
    raise typer.Exit(exit_code)


@app.command(help="Show durable state for an Unbound mission.")
def status(
    state_path: Path | None = typer.Option(None, "--state-path", help="Mission state path."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository containing mission state."),
    mission_id: str = typer.Option("", "--mission-id", help="Mission id; defaults to latest."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", help="Durable mission state root."),
) -> None:
    try:
        resolved = resolve_state_path(
            state_path=state_path,
            repo_path=repo_path,
            mission_id=mission_id,
            output_dir=output_dir,
        )
        state = load_mission(resolved)
    except (ValueError, FileNotFoundError) as error:
        raise typer.BadParameter(str(error)) from error
    console.print_json(data=mission_summary(state, resolved))


def set_mission_status(state_path: Path, status_value: str) -> UnboundMission:
    state = load_mission(state_path)
    if status_value not in MISSION_STATUSES:
        raise ValueError(f"Unsupported mission status: {status_value}")
    state.status = status_value
    save_mission(state_path, state)
    append_jsonl(
        state_path.parent / "events.jsonl",
        {
            "event": f"mission.{status_value}",
            "at": utc_now_iso(),
            "mission_id": state.mission_id,
        },
    )
    return state


@app.command(help="Resume a blocked or stopped mission without changing its worktree.")
def resume(
    state_path: Path = typer.Option(..., "--state-path", help="Mission state path."),
) -> None:
    try:
        state = set_mission_status(state_path.resolve(), "active")
    except (ValueError, FileNotFoundError) as error:
        raise typer.BadParameter(str(error)) from error
    console.print(f"resumed {state.mission_id}")


@app.command(help="Stop scheduling a mission while preserving all work and state.")
def stop(
    state_path: Path = typer.Option(..., "--state-path", help="Mission state path."),
) -> None:
    try:
        state = set_mission_status(state_path.resolve(), "stopped")
    except (ValueError, FileNotFoundError) as error:
        raise typer.BadParameter(str(error)) from error
    console.print(f"stopped {state.mission_id}")


if __name__ == "__main__":
    app()
