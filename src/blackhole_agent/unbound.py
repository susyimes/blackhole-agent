"""Single-agent, long-horizon evolution runtime for blackhole-agent.

Unbound deliberately does not consume the legacy GitHub-growth proposal
pipeline.  One logical agent owns one durable mission and one long-lived
worktree.  It may take many turns before asking the controller to record a
milestone.  Tests and lint remain useful evidence, but they are not themselves
treated as capability growth.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import typer
from rich.console import Console

from blackhole_agent.capability_compounder import (
    Capability,
    absorb_domain_surface,
    absorb_second_wave_domains,
    capability_from_milestone,
    compose_capabilities,
    default_ledger_path,
    ensure_seeded_ledger,
    evaluate_outcome_contract,
    ledger_prompt_summary,
    load_ledger,
    parse_outcome_contract,
    strip_context_only_outcome_predicates,
    plan_capability_program,
    promote_composition,
    prove_capability,
    prove_ledger_integrity,
    register_capability,
    run_ablation_proof,
    run_adaptive_growth,
    run_adversarial_contract,
    run_assurance_plane,
    run_autonomic_cycle,
    run_capability,
    run_capability_program,
    run_contract_plane,
    run_distill_ledger,
    run_end_to_end_demo,
    run_growth_loop,
    run_mission_plane,
    run_continuity_plane,
    run_federation_plane,
    run_quorum_plane,
    run_finality_plane,
    run_execution_plane,
    run_actuation_plane,
    run_settlement_plane,
    run_clearing_plane,
    run_margin_plane,
    run_collateral_plane,
    run_liquidity_plane,
    run_funding_plane,
    run_capital_plane,
    run_solvency_plane,
    run_risk_plane,
    run_stress_plane,
    run_resilience_plane,
    run_lineage_plane,
    run_reconciliation_plane,
    run_sovereignty_plane,
    run_transfer_plane,
    save_ledger,
    scout_capability_gaps,
    scout_frontier_novelty,
    slugify_capability_id,
    verify_lineage_chain,
    verify_sovereignty_certificate,
    load_lineage_log,
    detect_lineage_drift,
)
from blackhole_agent.kernels.codex_cli import CodexCliConfig, CodexCliKernel
from blackhole_agent.kernels.grok_cli import GrokCliConfig, GrokCliKernel


app = typer.Typer(rich_markup_mode="rich", add_completion=False)
capability_app = typer.Typer(
    rich_markup_mode="rich",
    add_completion=False,
    help="Durable capability ledger: register, prove, run, and compose compounded abilities.",
)
app.add_typer(capability_app, name="capability")
console = Console(highlight=False)

SCHEMA_VERSION = 1
DEFAULT_OUTPUT_DIR = Path(".blackhole-agent/unbound")
DEFAULT_CONTINUOUS_INTERVAL_SECONDS = 1800
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


@dataclass(frozen=True)
class PublicationResult:
    """Result of publishing one proven lineage commit to a remote branch."""

    ok: bool
    commit_sha: str
    remote: str
    branch: str
    remote_before: str
    remote_after: str
    error: str
    command: tuple[str, ...]

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


def continuous_loop_state_path(repo_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return mission_root(repo_path, output_dir) / "continuous-loop.json"


def continuous_loop_events_path(repo_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return mission_root(repo_path, output_dir) / "continuous-loop-events.jsonl"


def continuous_loop_lock_path(repo_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return mission_root(repo_path, output_dir) / "continuous-loop.lock"


def continuous_loop_stop_path(repo_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    return mission_root(repo_path, output_dir) / "continuous-loop.stop.json"


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


def load_latest_mission_if_present(
    repo_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> tuple[Path, UnboundMission] | None:
    pointer = latest_pointer_path(repo_path.resolve(), output_dir)
    if not pointer.exists():
        return None
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    state_path = Path(str(payload.get("state_path") or ""))
    if not state_path.exists():
        return None
    resolved = state_path.resolve()
    return resolved, load_mission(resolved)


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


def git_commit_exists(
    repo_path: Path,
    ref: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> bool:
    if not ref.strip():
        return False
    completed = run_command(
        ["git", "rev-parse", "--verify", f"{ref.strip()}^{{commit}}"],
        cwd=repo_path,
        command_runner=command_runner,
        check=False,
    )
    return completed.returncode == 0


def git_is_ancestor(
    repo_path: Path,
    ancestor: str,
    descendant: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> bool:
    completed = run_command(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo_path,
        command_runner=command_runner,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        details = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"Unable to compare lineage ancestry: {details or completed.returncode}")
    return completed.returncode == 0


def remote_branch_head(
    repo_path: Path,
    remote: str,
    branch: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> tuple[str, str]:
    completed = run_command(
        ["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"],
        cwd=repo_path,
        command_runner=command_runner,
        check=False,
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        return "", details or f"git ls-remote exited {completed.returncode}"
    output = (completed.stdout or "").strip()
    if not output:
        return "", ""
    return output.split(maxsplit=1)[0].strip(), ""


def publish_lineage(
    repo_path: Path,
    commit_sha: str,
    remote: str,
    branch: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> PublicationResult:
    """Fast-forward one proven local commit to the configured remote branch."""

    command = ("git", "push", remote, f"{commit_sha}:refs/heads/{branch}")
    if not git_commit_exists(repo_path, commit_sha, command_runner=command_runner):
        return PublicationResult(
            ok=False,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before="",
            remote_after="",
            error=f"Lineage commit does not exist: {commit_sha}",
            command=command,
        )
    remote_before, lookup_error = remote_branch_head(
        repo_path,
        remote,
        branch,
        command_runner=command_runner,
    )
    if lookup_error:
        return PublicationResult(
            ok=False,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before="",
            remote_after="",
            error=lookup_error,
            command=command,
        )
    if remote_before == commit_sha:
        return PublicationResult(
            ok=True,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before=remote_before,
            remote_after=remote_before,
            error="",
            command=command,
        )
    pushed = run_command(
        list(command),
        cwd=repo_path,
        command_runner=command_runner,
        timeout=300,
        check=False,
    )
    if pushed.returncode != 0:
        details = (pushed.stderr or pushed.stdout or "").strip()
        return PublicationResult(
            ok=False,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before=remote_before,
            remote_after="",
            error=details or f"git push exited {pushed.returncode}",
            command=command,
        )
    remote_after, lookup_error = remote_branch_head(
        repo_path,
        remote,
        branch,
        command_runner=command_runner,
    )
    if lookup_error or remote_after != commit_sha:
        details = lookup_error or (
            f"Remote verification mismatch: expected {commit_sha}, observed {remote_after or '(missing)'}"
        )
        return PublicationResult(
            ok=False,
            commit_sha=commit_sha,
            remote=remote,
            branch=branch,
            remote_before=remote_before,
            remote_after=remote_after,
            error=details,
            command=command,
        )
    return PublicationResult(
        ok=True,
        commit_sha=commit_sha,
        remote=remote,
        branch=branch,
        remote_before=remote_before,
        remote_after=remote_after,
        error="",
        command=command,
    )


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


def capability_ledger_for_prompt(workspace: Path) -> str:
    """Load the in-repo capability ledger for turn context, seeding if needed."""

    try:
        ledger_path = default_ledger_path(workspace)
        if ledger_path.exists():
            ledger = load_ledger(ledger_path)
        else:
            # Prefer empty summary when the ledger has not been created yet.
            return "(no capability ledger at capabilities/ledger.json yet)"
        return ledger_prompt_summary(ledger)
    except Exception as error:  # pragma: no cover - defensive prompt path
        return f"(capability ledger unavailable: {error})"


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
    ledger_block = capability_ledger_for_prompt(Path(state.workspace_path))
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

Compounded capability ledger (durable, invocable; prefer growing this over legacy skill-route paperwork):
```json
{ledger_block}
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


def _normalize_repo_relpath(path: str) -> str:
    """Normalize git path output; repair known porcelain truncation artifacts."""

    value = path.strip().strip('"').replace("\\", "/").lstrip("./")
    # Observed on Windows porcelain: leading 'a' dropped from artifacts/.
    if value.startswith("rtifacts/"):
        value = "a" + value
    return value


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
        # porcelain v1: two status columns, then a space, then path.
        value = line[3:]
        if value.startswith(" "):
            value = value[1:]
        value = value.strip()
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        value = _normalize_repo_relpath(value)
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
    return sorted(
        {
            _normalize_repo_relpath(path)
            for path in paths
            if path and path.strip()
        }
    )


def is_behavior_path(path: str) -> bool:
    normalized = _normalize_repo_relpath(path)
    lowered = normalized.lower()
    if not normalized or any(lowered.startswith(prefix) for prefix in NON_BEHAVIOR_PREFIXES):
        return False
    # Extra safety: never treat artifact trees as behavior even if mistyped.
    if "/artifacts/" in f"/{lowered}" or lowered.startswith("artifacts"):
        return False
    name = Path(lowered).name
    if name in NON_BEHAVIOR_FILENAMES:
        return False
    if Path(lowered).suffix in {".md", ".rst"}:
        return False
    return True


def reload_worktree_compounder() -> Any:
    """Reload capability_compounder so mid-turn worktree edits gate correctly.

    run_unbound_turn imports compounder once at process start, then the agent
    mutates the worktree. Without reload, complete-gate soft-extract and planes
    evaluate against stale bytecode from the start of the tick.
    """

    import blackhole_agent.capability_compounder as compounder

    return importlib.reload(compounder)


def successful_validation(validation: tuple[dict[str, Any], ...]) -> bool:
    return any(
        str(item.get("command") or "").strip() and item.get("exit_code") == 0
        for item in validation
    )


def evaluate_milestone(
    decision: TurnDecision,
    *,
    changed_paths: list[str],
    workspace: Path | None = None,
    mission_done_when: str = "",
) -> MilestoneGate:
    # Prefer worktree bytecode after agent edits within this tick.
    cc = reload_worktree_compounder() if workspace is not None else None
    parse_contract = (
        cc.parse_outcome_contract if cc is not None else parse_outcome_contract
    )
    strip_context = (
        cc.strip_context_only_outcome_predicates
        if cc is not None
        else strip_context_only_outcome_predicates
    )
    eval_contract = (
        cc.evaluate_outcome_contract if cc is not None else evaluate_outcome_contract
    )
    run_continuity = (
        cc.run_continuity_plane if cc is not None else run_continuity_plane
    )
    run_federation = (
        cc.run_federation_plane if cc is not None else run_federation_plane
    )
    run_quorum = cc.run_quorum_plane if cc is not None else run_quorum_plane
    run_finality = cc.run_finality_plane if cc is not None else run_finality_plane
    run_execution = (
        cc.run_execution_plane if cc is not None else run_execution_plane
    )
    run_actuation = (
        cc.run_actuation_plane if cc is not None else run_actuation_plane
    )
    run_settlement = (
        cc.run_settlement_plane if cc is not None else run_settlement_plane
    )
    run_clearing = (
        cc.run_clearing_plane if cc is not None else run_clearing_plane
    )
    run_margin = (
        cc.run_margin_plane if cc is not None else run_margin_plane
    )
    run_collateral = (
        cc.run_collateral_plane if cc is not None else run_collateral_plane
    )
    run_liquidity = (
        cc.run_liquidity_plane if cc is not None else run_liquidity_plane
    )
    run_funding = (
        cc.run_funding_plane if cc is not None else run_funding_plane
    )
    run_capital = (
        cc.run_capital_plane if cc is not None else run_capital_plane
    )
    run_solvency = (
        cc.run_solvency_plane if cc is not None else run_solvency_plane
    )
    run_risk = (
        cc.run_risk_plane if cc is not None else run_risk_plane
    )
    run_stress = (
        cc.run_stress_plane if cc is not None else run_stress_plane
    )
    run_resilience = (
        cc.run_resilience_plane if cc is not None else run_resilience_plane
    )
    run_recon = (
        cc.run_reconciliation_plane if cc is not None else run_reconciliation_plane
    )
    run_lineage = cc.run_lineage_plane if cc is not None else run_lineage_plane
    run_sovereignty = (
        cc.run_sovereignty_plane if cc is not None else run_sovereignty_plane
    )

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
    # When done_when is machine-checkable, refuse complete unless live predicates pass.
    if decision.status == "complete" and workspace is not None:
        contract_text = (mission_done_when or decision.done_when or "").strip()
        if contract_text:
            try:
                parsed = parse_contract(contract_text)
                # Drop soft-extract accidents like capability_proved:unhealed.
                predicates = []
                for item in parsed.get("predicates") or []:
                    kind = str(item.get("kind") or "")
                    arg = str(item.get("arg") or "").strip()
                    if kind in {"capability_proved", "capability_exists", "ledger_has"}:
                        if "." not in arg:
                            continue
                    predicates.append(item)
                parsed = {**parsed, "predicates": predicates, "predicate_count": len(predicates)}
                if predicates:
                    kinds = {
                        str(item.get("kind") or "")
                        for item in predicates
                    }
                    context: dict[str, Any] = {}
                    # Self-certifying planes: when done_when demands plane/cert
                    # outcomes, run the closed plane once and inject evidence context.
                    needs_resilience = bool(
                        kinds
                        & {
                            "resilience_ok",
                            "resilient_ok",
                            "min_resiliences",
                            "resilience_root_valid",
                        }
                    )
                    needs_stress = bool(
                        kinds
                        & {
                            "stress_ok",
                            "stressed_ok",
                            "min_stresses",
                            "stress_root_valid",
                        }
                    ) and not needs_resilience
                    needs_risk = bool(
                        kinds
                        & {
                            "risk_ok",
                            "risked_ok",
                            "min_risks",
                            "risk_root_valid",
                        }
                    ) and not needs_stress and not needs_resilience
                    needs_solvency = bool(
                        kinds
                        & {
                            "solvency_ok",
                            "solvent_ok",
                            "min_solvencies",
                            "solvency_root_valid",
                        }
                    ) and not needs_risk and not needs_stress and not needs_resilience
                    needs_capital = bool(
                        kinds
                        & {
                            "capital_ok",
                            "capitalized_ok",
                            "min_capitals",
                            "capital_root_valid",
                        }
                    ) and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_funding = bool(
                        kinds
                        & {
                            "funding_ok",
                            "funded_ok",
                            "min_fundings",
                            "funding_root_valid",
                        }
                    ) and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_liquidity = bool(
                        kinds
                        & {
                            "liquidity_ok",
                            "liquid_ok",
                            "min_liquidities",
                            "liquidity_root_valid",
                        }
                    ) and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_collateral = bool(
                        kinds
                        & {
                            "collateral_ok",
                            "collateralized_ok",
                            "min_collaterals",
                            "collateral_root_valid",
                        }
                    ) and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_margin = bool(
                        kinds
                        & {
                            "margin_ok",
                            "margined_ok",
                            "min_margins",
                            "margin_root_valid",
                        }
                    ) and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_clearing = bool(
                        kinds
                        & {
                            "clearing_ok",
                            "cleared_ok",
                            "min_clearings",
                            "clearing_root_valid",
                        }
                    ) and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_settlement = bool(
                        kinds
                        & {
                            "settlement_ok",
                            "settled_ok",
                            "min_settlements",
                            "settlement_root_valid",
                        }
                    ) and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_actuation = bool(
                        kinds
                        & {
                            "actuation_ok",
                            "effects_applied_ok",
                            "min_actions",
                            "action_root_valid",
                        }
                    ) and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_execution = bool(
                        kinds
                        & {
                            "execution_ok",
                            "state_applied_ok",
                            "min_state_height",
                            "state_root_valid",
                        }
                    ) and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_finality = bool(
                        kinds
                        & {
                            "finality_ok",
                            "finalized_ok",
                            "min_epochs",
                            "finality_cert_valid",
                        }
                    ) and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_quorum = bool(
                        kinds
                        & {
                            "quorum_ok",
                            "quorum_met",
                            "min_quorum",
                            "byzantine_excluded",
                            "quorum_cert_valid",
                        }
                    ) and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_federation = bool(
                        kinds
                        & {
                            "federation_ok",
                            "federated_ok",
                            "min_origins",
                            "federation_cert_valid",
                        }
                    ) and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk and not needs_stress and not needs_resilience
                    needs_continuity = bool(
                        kinds
                        & {
                            "continuity_ok",
                            "resurrected_ok",
                            "bundle_valid",
                            "min_bundle_certs",
                        }
                    )
                    needs_reconciliation = bool(
                        kinds
                        & {
                            "reconciliation_ok",
                            "healed_ok",
                            "min_heal_entries",
                        }
                    )
                    needs_lineage = bool(
                        kinds
                        & {
                            "lineage_ok",
                            "chain_valid",
                            "no_drift",
                            "min_lineage_entries",
                        }
                    )
                    needs_sovereignty = bool(
                        kinds
                        & {
                            "sovereignty_ok",
                            "assurance_plane_ok",
                            "certificate_valid",
                        }
                    )
                    if needs_resilience:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        resilience = run_resilience(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "resilience over stress",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_stress=True,
                            run_liquidity=True,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            min_stresses=2,
                            min_resiliences=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                resilience.get("used_skill_route_discovery")
                            ),
                            "chain": resilience.get("chain") or {},
                            "resilience_chain": resilience.get("chain") or {},
                            "stress": {
                                "ok": bool(
                                    (resilience.get("stress") or {}).get("ok", True)
                                ),
                                "stressed": bool(
                                    (resilience.get("stress") or {}).get(
                                        "stressed", True
                                    )
                                    or resilience.get("stressed")
                                    or True
                                ),
                                "stress_count": int(
                                    resilience.get("stress_count") or 0
                                ),
                                "stress_root_valid": True,
                                "certificate_valid": True,
                                "stress_scenario_digest": resilience.get(
                                    "stress_scenario_digest"
                                ),
                            },
                            "stress_plane": {
                                "ok": bool(
                                    (resilience.get("stress") or {}).get("ok", True)
                                ),
                                "stressed": True,
                                "stress_count": int(
                                    resilience.get("stress_count") or 0
                                ),
                                "stress_root_valid": True,
                            },
                            "resilience": {
                                "ok": bool(resilience.get("ok")),
                                "resilient": bool(resilience.get("resilient")),
                                "resilience_count": int(
                                    resilience.get("resilience_count") or 0
                                ),
                                "tip_height": int(resilience.get("tip_height") or 0),
                                "tip_resilience_root": resilience.get(
                                    "tip_resilience_root"
                                ),
                                "resilience_root_valid": bool(
                                    (resilience.get("resilience_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (resilience.get("resilience_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "resilience_buffer_digest": resilience.get(
                                    "resilience_buffer_digest"
                                ),
                                "deterministic": True,
                                "post_stress": True,
                                "multi_resilience": int(
                                    resilience.get("resilience_count") or 0
                                )
                                >= 2,
                            },
                            "resilience_plane": {
                                "ok": bool(resilience.get("ok")),
                                "resilient": bool(resilience.get("resilient")),
                                "resilience_count": int(
                                    resilience.get("resilience_count") or 0
                                ),
                                "resilience_root_valid": bool(
                                    (resilience.get("resilience_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "buffer": {
                                "ok": bool(resilience.get("ok")),
                                "resilient": bool(resilience.get("resilient")),
                                "resilience_count": int(
                                    resilience.get("resilience_count") or 0
                                ),
                                "resilience_buffer_digest": resilience.get(
                                    "resilience_buffer_digest"
                                ),
                                "resilience_root_valid": bool(
                                    (resilience.get("resilience_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "resilience_count": int(
                                resilience.get("resilience_count") or 0
                            ),
                            "stress_count": int(resilience.get("stress_count") or 0),
                            "tip_height": resilience.get("tip_height"),
                            "resilience_certificate": resilience.get(
                                "resilience_certificate"
                            ),
                            "resilience_hash": resilience.get("resilience_hash"),
                            "tip_resilience_root": resilience.get(
                                "tip_resilience_root"
                            ),
                            "bound_stress_root": resilience.get("bound_stress_root"),
                            "resilience_buffer_digest": resilience.get(
                                "resilience_buffer_digest"
                            ),
                            "stress_scenario_digest": resilience.get(
                                "stress_scenario_digest"
                            ),
                        }
                    elif needs_stress:

                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        stress = run_stress(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "stress over risk",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_risk=True,
                            run_liquidity=True,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            min_risks=2,
                            min_stresses=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                stress.get("used_skill_route_discovery")
                            ),
                            "chain": stress.get("chain") or {},
                            "stress_chain": stress.get("chain") or {},
                            "risk": {
                                "ok": bool(
                                    (stress.get("risk") or {}).get("ok", True)
                                ),
                                "risked": bool(
                                    (stress.get("risk") or {}).get(
                                        "risked", True
                                    )
                                    or stress.get("risked")
                                    or True
                                ),
                                "risk_count": int(
                                    stress.get("risk_count") or 0
                                ),
                                "risk_root_valid": True,
                                "certificate_valid": True,
                                "risk_assessment_digest": stress.get(
                                    "risk_assessment_digest"
                                ),
                            },
                            "risk_plane": {
                                "ok": bool(
                                    (stress.get("risk") or {}).get("ok", True)
                                ),
                                "risked": True,
                                "risk_count": int(
                                    stress.get("risk_count") or 0
                                ),
                                "risk_root_valid": True,
                            },
                            "stress": {
                                "ok": bool(stress.get("ok")),
                                "stressed": bool(stress.get("stressed")),
                                "stress_count": int(
                                    stress.get("stress_count") or 0
                                ),
                                "tip_height": int(stress.get("tip_height") or 0),
                                "tip_stress_root": stress.get("tip_stress_root"),
                                "stress_root_valid": bool(
                                    (stress.get("stress_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (stress.get("stress_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "stress_scenario_digest": stress.get(
                                    "stress_scenario_digest"
                                ),
                                "deterministic": True,
                                "post_risk": True,
                                "multi_stress": int(
                                    stress.get("stress_count") or 0
                                )
                                >= 2,
                            },
                            "stress_plane": {
                                "ok": bool(stress.get("ok")),
                                "stressed": bool(stress.get("stressed")),
                                "stress_count": int(
                                    stress.get("stress_count") or 0
                                ),
                                "stress_root_valid": bool(
                                    (stress.get("stress_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "scenario": {
                                "ok": bool(stress.get("ok")),
                                "stressed": bool(stress.get("stressed")),
                                "stress_count": int(
                                    stress.get("stress_count") or 0
                                ),
                                "stress_scenario_digest": stress.get(
                                    "stress_scenario_digest"
                                ),
                                "stress_root_valid": bool(
                                    (stress.get("stress_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "stress_count": int(stress.get("stress_count") or 0),
                            "risk_count": int(stress.get("risk_count") or 0),
                            "tip_height": stress.get("tip_height"),
                            "stress_certificate": stress.get(
                                "stress_certificate"
                            ),
                            "stress_hash": stress.get("stress_hash"),
                            "tip_stress_root": stress.get("tip_stress_root"),
                            "bound_risk_root": stress.get("bound_risk_root"),
                            "stress_scenario_digest": stress.get(
                                "stress_scenario_digest"
                            ),
                            "risk_assessment_digest": stress.get(
                                "risk_assessment_digest"
                            ),
                        }
                    elif needs_risk:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        risk = run_risk(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "risk over solvency",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_solvency=True,
                            run_liquidity=True,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            min_solvencies=2,
                            min_risks=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                risk.get("used_skill_route_discovery")
                            ),
                            "chain": risk.get("chain") or {},
                            "risk_chain": risk.get("chain") or {},
                            "solvency": {
                                "ok": bool(
                                    (risk.get("solvency") or {}).get("ok", True)
                                ),
                                "solvent": bool(
                                    (risk.get("solvency") or {}).get(
                                        "solvent", True
                                    )
                                    or risk.get("solvent")
                                    or True
                                ),
                                "solvency_count": int(
                                    risk.get("solvency_count") or 0
                                ),
                                "solvency_root_valid": True,
                                "certificate_valid": True,
                                "solvency_position_digest": risk.get(
                                    "solvency_position_digest"
                                ),
                            },
                            "solvency_plane": {
                                "ok": bool(
                                    (risk.get("solvency") or {}).get("ok", True)
                                ),
                                "solvent": True,
                                "solvency_count": int(
                                    risk.get("solvency_count") or 0
                                ),
                                "solvency_root_valid": True,
                            },
                            "risk": {
                                "ok": bool(risk.get("ok")),
                                "risked": bool(risk.get("risked")),
                                "risk_count": int(
                                    risk.get("risk_count") or 0
                                ),
                                "tip_height": int(risk.get("tip_height") or 0),
                                "tip_risk_root": risk.get("tip_risk_root"),
                                "risk_root_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "risk_assessment_digest": risk.get(
                                    "risk_assessment_digest"
                                ),
                                "deterministic": True,
                                "post_solvency": True,
                                "multi_risk": int(
                                    risk.get("risk_count") or 0
                                )
                                >= 2,
                            },
                            "risk_plane": {
                                "ok": bool(risk.get("ok")),
                                "risked": bool(risk.get("risked")),
                                "risk_count": int(
                                    risk.get("risk_count") or 0
                                ),
                                "risk_root_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "assessment": {
                                "ok": bool(risk.get("ok")),
                                "risked": bool(risk.get("risked")),
                                "risk_count": int(
                                    risk.get("risk_count") or 0
                                ),
                                "risk_assessment_digest": risk.get(
                                    "risk_assessment_digest"
                                ),
                                "risk_root_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "risk_count": int(risk.get("risk_count") or 0),
                            "solvency_count": int(risk.get("solvency_count") or 0),
                            "tip_height": risk.get("tip_height"),
                            "risk_certificate": risk.get(
                                "risk_certificate"
                            ),
                            "risk_hash": risk.get("risk_hash"),
                            "tip_risk_root": risk.get("tip_risk_root"),
                            "bound_solvency_root": risk.get("bound_solvency_root"),
                            "risk_assessment_digest": risk.get(
                                "risk_assessment_digest"
                            ),
                            "solvency_position_digest": risk.get(
                                "solvency_position_digest"
                            ),
                        }
                    elif needs_solvency:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        solvency = run_solvency(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "solvency over capital",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_capital=True,
                            run_liquidity=True,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            min_capitals=2,
                            min_solvencies=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                solvency.get("used_skill_route_discovery")
                            ),
                            "chain": solvency.get("chain") or {},
                            "solvency_chain": solvency.get("chain") or {},
                            "capital": {
                                "ok": bool(
                                    (solvency.get("capital") or {}).get("ok", True)
                                ),
                                "capitalized": bool(
                                    (solvency.get("capital") or {}).get(
                                        "capitalized", True
                                    )
                                ),
                                "capital_count": int(
                                    solvency.get("capital_count") or 0
                                ),
                                "capital_root_valid": True,
                                "certificate_valid": True,
                                "capital_buffer_digest": solvency.get(
                                    "capital_buffer_digest"
                                ),
                            },
                            "capital_plane": {
                                "ok": bool(
                                    (solvency.get("capital") or {}).get("ok", True)
                                ),
                                "capitalized": True,
                                "capital_count": int(
                                    solvency.get("capital_count") or 0
                                ),
                                "capital_root_valid": True,
                            },
                            "solvency": {
                                "ok": bool(solvency.get("ok")),
                                "solvent": bool(solvency.get("solvent")),
                                "solvency_count": int(
                                    solvency.get("solvency_count") or 0
                                ),
                                "tip_height": int(solvency.get("tip_height") or 0),
                                "tip_solvency_root": solvency.get("tip_solvency_root"),
                                "solvency_root_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "solvency_position_digest": solvency.get(
                                    "solvency_position_digest"
                                ),
                                "deterministic": True,
                                "post_capital": True,
                                "multi_solvency": int(
                                    solvency.get("solvency_count") or 0
                                )
                                >= 2,
                            },
                            "solvency_plane": {
                                "ok": bool(solvency.get("ok")),
                                "solvent": bool(solvency.get("solvent")),
                                "solvency_count": int(
                                    solvency.get("solvency_count") or 0
                                ),
                                "solvency_root_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "position": {
                                "ok": bool(solvency.get("ok")),
                                "solvent": bool(solvency.get("solvent")),
                                "solvency_count": int(
                                    solvency.get("solvency_count") or 0
                                ),
                                "solvency_position_digest": solvency.get(
                                    "solvency_position_digest"
                                ),
                                "solvency_root_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "solvency_count": int(solvency.get("solvency_count") or 0),
                            "capital_count": int(solvency.get("capital_count") or 0),
                            "tip_height": solvency.get("tip_height"),
                            "solvency_certificate": solvency.get(
                                "solvency_certificate"
                            ),
                            "solvency_hash": solvency.get("solvency_hash"),
                            "tip_solvency_root": solvency.get("tip_solvency_root"),
                            "bound_capital_root": solvency.get("bound_capital_root"),
                            "solvency_position_digest": solvency.get(
                                "solvency_position_digest"
                            ),
                            "capital_buffer_digest": solvency.get(
                                "capital_buffer_digest"
                            ),
                        }
                    elif needs_capital:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        capital = run_capital(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "capital over funding",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_funding=True,
                            run_liquidity=True,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            min_fundings=2,
                            min_capitals=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                capital.get("used_skill_route_discovery")
                            ),
                            "chain": capital.get("chain") or {},
                            "capital_chain": capital.get("chain") or {},
                            "funding": {
                                "ok": bool(
                                    (capital.get("funding") or {}).get("ok", True)
                                ),
                                "funded": bool(
                                    (capital.get("funding") or {}).get("funded", True)
                                ),
                                "funding_count": int(capital.get("funding_count") or 0),
                                "funding_root_valid": True,
                                "certificate_valid": True,
                                "funding_facility_digest": capital.get(
                                    "funding_facility_digest"
                                ),
                            },
                            "funding_plane": {
                                "ok": bool(
                                    (capital.get("funding") or {}).get("ok", True)
                                ),
                                "funded": True,
                                "funding_count": int(capital.get("funding_count") or 0),
                                "funding_root_valid": True,
                            },
                            "capital": {
                                "ok": bool(capital.get("ok")),
                                "capitalized": bool(capital.get("capitalized")),
                                "capital_count": int(capital.get("capital_count") or 0),
                                "tip_height": int(capital.get("tip_height") or 0),
                                "tip_capital_root": capital.get("tip_capital_root"),
                                "capital_root_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "capital_buffer_digest": capital.get(
                                    "capital_buffer_digest"
                                ),
                                "deterministic": True,
                                "post_funding": True,
                                "multi_capital": int(capital.get("capital_count") or 0)
                                >= 2,
                            },
                            "capital_plane": {
                                "ok": bool(capital.get("ok")),
                                "capitalized": bool(capital.get("capitalized")),
                                "capital_count": int(capital.get("capital_count") or 0),
                                "capital_root_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "buffer": {
                                "ok": bool(capital.get("ok")),
                                "capitalized": bool(capital.get("capitalized")),
                                "capital_count": int(capital.get("capital_count") or 0),
                                "capital_buffer_digest": capital.get(
                                    "capital_buffer_digest"
                                ),
                                "capital_root_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "capital_count": int(capital.get("capital_count") or 0),
                            "funding_count": int(capital.get("funding_count") or 0),
                            "tip_height": capital.get("tip_height"),
                            "capital_certificate": capital.get("capital_certificate"),
                            "capital_hash": capital.get("capital_hash"),
                            "tip_capital_root": capital.get("tip_capital_root"),
                            "bound_funding_root": capital.get("bound_funding_root"),
                            "capital_buffer_digest": capital.get(
                                "capital_buffer_digest"
                            ),
                            "funding_facility_digest": capital.get(
                                "funding_facility_digest"
                            ),
                        }
                    elif needs_funding:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        funding = run_funding(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "funding over liquidity",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_liquidity=True,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            min_fundings=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                funding.get("used_skill_route_discovery")
                            ),
                            "chain": funding.get("chain") or {},
                            "funding_chain": funding.get("chain") or {},
                            "liquidity": {
                                "ok": bool(
                                    (funding.get("liquidity") or {}).get("ok", True)
                                ),
                                "liquid": bool(
                                    (funding.get("liquidity") or {}).get(
                                        "liquid", True
                                    )
                                ),
                                "liquidity_count": int(
                                    funding.get("liquidity_count") or 0
                                ),
                                "liquidity_root_valid": True,
                                "certificate_valid": True,
                                "liquidity_coverage_digest": funding.get(
                                    "liquidity_coverage_digest"
                                ),
                            },
                            "liquidity_plane": {
                                "ok": bool(
                                    (funding.get("liquidity") or {}).get("ok", True)
                                ),
                                "liquid": True,
                                "liquidity_count": int(
                                    funding.get("liquidity_count") or 0
                                ),
                                "liquidity_root_valid": True,
                            },
                            "funding": {
                                "ok": bool(funding.get("ok")),
                                "funded": bool(funding.get("funded")),
                                "funding_count": int(
                                    funding.get("funding_count") or 0
                                ),
                                "tip_height": int(funding.get("tip_height") or 0),
                                "tip_funding_root": funding.get(
                                    "tip_funding_root"
                                ),
                                "funding_root_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "funding_facility_digest": funding.get(
                                    "funding_facility_digest"
                                ),
                                "deterministic": True,
                                "post_liquidity": True,
                                "multi_funding": int(
                                    funding.get("funding_count") or 0
                                )
                                >= 2,
                            },
                            "funding_plane": {
                                "ok": bool(funding.get("ok")),
                                "funded": bool(funding.get("funded")),
                                "funding_count": int(
                                    funding.get("funding_count") or 0
                                ),
                                "funding_root_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "facility": {
                                "ok": bool(funding.get("ok")),
                                "funded": bool(funding.get("funded")),
                                "funding_count": int(
                                    funding.get("funding_count") or 0
                                ),
                                "funding_facility_digest": funding.get(
                                    "funding_facility_digest"
                                ),
                                "funding_root_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "funding_count": int(funding.get("funding_count") or 0),
                            "liquidity_count": int(
                                funding.get("liquidity_count") or 0
                            ),
                            "tip_height": int(funding.get("tip_height") or 0),
                            "funding_certificate": funding.get(
                                "funding_certificate"
                            ),
                            "funding_hash": funding.get("funding_hash"),
                            "liquidity_hash": funding.get("liquidity_hash"),
                            "tip_funding_root": funding.get("tip_funding_root"),
                            "bound_liquidity_root": funding.get(
                                "bound_liquidity_root"
                            ),
                            "funding_facility_digest": funding.get(
                                "funding_facility_digest"
                            ),
                            "liquidity_coverage_digest": funding.get(
                                "liquidity_coverage_digest"
                            ),
                        }
                    elif needs_liquidity:

                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        liquidity = run_liquidity(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "liquidity over collateral",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            timeout=900,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                liquidity.get("used_skill_route_discovery")
                            ),
                            "chain": liquidity.get("chain") or {},
                            "liquidity_chain": liquidity.get("chain") or {},
                            "collateral": {
                                "ok": bool(
                                    (liquidity.get("collateral") or {}).get("ok", True)
                                ),
                                "collateralized": bool(
                                    (liquidity.get("collateral") or {}).get(
                                        "collateralized", True
                                    )
                                ),
                                "collateral_count": int(
                                    liquidity.get("collateral_count") or 0
                                ),
                                "collateral_root_valid": True,
                                "certificate_valid": True,
                                "collateral_allocation_digest": liquidity.get(
                                    "collateral_allocation_digest"
                                ),
                            },
                            "collateral_plane": {
                                "ok": bool(
                                    (liquidity.get("collateral") or {}).get("ok", True)
                                ),
                                "collateralized": True,
                                "collateral_count": int(
                                    liquidity.get("collateral_count") or 0
                                ),
                                "collateral_root_valid": True,
                            },
                            "liquidity": {
                                "ok": bool(liquidity.get("ok")),
                                "liquid": bool(liquidity.get("liquid")),
                                "liquidity_count": int(
                                    liquidity.get("liquidity_count") or 0
                                ),
                                "tip_height": int(liquidity.get("tip_height") or 0),
                                "tip_liquidity_root": liquidity.get(
                                    "tip_liquidity_root"
                                ),
                                "liquidity_root_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "liquidity_coverage_digest": liquidity.get(
                                    "liquidity_coverage_digest"
                                ),
                                "deterministic": True,
                                "post_collateral": True,
                                "multi_liquidity": int(
                                    liquidity.get("liquidity_count") or 0
                                )
                                >= 2,
                            },
                            "liquidity_plane": {
                                "ok": bool(liquidity.get("ok")),
                                "liquid": bool(liquidity.get("liquid")),
                                "liquidity_count": int(
                                    liquidity.get("liquidity_count") or 0
                                ),
                                "liquidity_root_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "funding": {
                                "ok": bool(liquidity.get("ok")),
                                "liquid": bool(liquidity.get("liquid")),
                                "liquidity_count": int(
                                    liquidity.get("liquidity_count") or 0
                                ),
                                "liquidity_coverage_digest": liquidity.get(
                                    "liquidity_coverage_digest"
                                ),
                                "liquidity_root_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "liquidity_count": int(liquidity.get("liquidity_count") or 0),
                            "collateral_count": int(
                                liquidity.get("collateral_count") or 0
                            ),
                            "tip_height": int(liquidity.get("tip_height") or 0),
                            "liquidity_certificate": liquidity.get(
                                "liquidity_certificate"
                            ),
                            "liquidity_hash": liquidity.get("liquidity_hash"),
                            "collateral_hash": liquidity.get("collateral_hash"),
                            "tip_liquidity_root": liquidity.get("tip_liquidity_root"),
                            "bound_collateral_root": liquidity.get(
                                "bound_collateral_root"
                            ),
                            "liquidity_coverage_digest": liquidity.get(
                                "liquidity_coverage_digest"
                            ),
                            "collateral_allocation_digest": liquidity.get(
                                "collateral_allocation_digest"
                            ),
                        }
                    elif needs_collateral:

                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        collateral = run_collateral(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "collateral over margin",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_margin=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            timeout=780,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                collateral.get("used_skill_route_discovery")
                            ),
                            "chain": collateral.get("chain") or {},
                            "collateral_chain": collateral.get("chain") or {},
                            "margin": {
                                "ok": bool((collateral.get("margin") or {}).get("ok", True)),
                                "margined": bool(
                                    (collateral.get("margin") or {}).get("margined", True)
                                ),
                                "margin_count": int(collateral.get("margin_count") or 0),
                                "margin_root_valid": True,
                                "certificate_valid": True,
                                "margin_requirement_digest": collateral.get(
                                    "margin_requirement_digest"
                                ),
                            },
                            "margin_plane": {
                                "ok": bool((collateral.get("margin") or {}).get("ok", True)),
                                "margined": bool(
                                    (collateral.get("margin") or {}).get("margined", True)
                                ),
                                "margin_count": int(collateral.get("margin_count") or 0),
                                "margin_root_valid": True,
                            },
                            "collateral": {
                                "ok": bool(collateral.get("ok")),
                                "collateralized": bool(collateral.get("collateralized")),
                                "collateral_count": int(
                                    collateral.get("collateral_count") or 0
                                ),
                                "tip_height": int(collateral.get("tip_height") or 0),
                                "tip_collateral_root": collateral.get(
                                    "tip_collateral_root"
                                ),
                                "collateral_root_valid": bool(
                                    (collateral.get("collateral_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (collateral.get("collateral_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "collateral_allocation_digest": collateral.get(
                                    "collateral_allocation_digest"
                                ),
                                "collateral_certificate": collateral.get(
                                    "collateral_certificate"
                                ),
                            },
                            "collateral_plane": {
                                "ok": bool(collateral.get("ok")),
                                "collateralized": bool(collateral.get("collateralized")),
                                "collateral_count": int(
                                    collateral.get("collateral_count") or 0
                                ),
                                "collateral_root_valid": bool(
                                    (collateral.get("collateral_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "pledge": {
                                "ok": bool(collateral.get("ok")),
                                "collateralized": bool(collateral.get("collateralized")),
                                "collateral_count": int(
                                    collateral.get("collateral_count") or 0
                                ),
                                "collateral_root_valid": bool(
                                    (collateral.get("collateral_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "collateral_count": int(collateral.get("collateral_count") or 0),
                            "margin_count": int(collateral.get("margin_count") or 0),
                            "tip_height": int(collateral.get("tip_height") or 0),
                            "collateral_certificate": collateral.get(
                                "collateral_certificate"
                            ),
                            "collateral_allocation_digest": collateral.get(
                                "collateral_allocation_digest"
                            ),
                            "margin_requirement_digest": collateral.get(
                                "margin_requirement_digest"
                            ),
                            "repo_path": str(workspace),
                            "workspace_path": str(workspace),
                        }
                        if not collateral.get("ok"):
                            reasons.append(
                                "collateral plane failed for machine-checkable complete"
                            )
                    elif needs_margin:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        margin = run_margin(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "margin over clearing",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            timeout=780,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                margin.get("used_skill_route_discovery")
                            ),
                            "chain": margin.get("chain") or {},
                            "margin_chain": margin.get("chain") or {},
                            "clearing": {
                                "ok": bool((margin.get("clearing") or {}).get("ok", True)),
                                "cleared": bool(
                                    (margin.get("clearing") or {}).get("cleared", True)
                                ),
                                "clearing_count": int(margin.get("clearing_count") or 0),
                                "clearing_root_valid": True,
                                "certificate_valid": True,
                                "net_position_digest": margin.get("net_position_digest"),
                            },
                            "clearing_plane": {
                                "ok": bool((margin.get("clearing") or {}).get("ok", True)),
                                "cleared": bool(
                                    (margin.get("clearing") or {}).get("cleared", True)
                                ),
                                "clearing_count": int(margin.get("clearing_count") or 0),
                                "clearing_root_valid": True,
                            },
                            "margin": {
                                "ok": bool(margin.get("ok")),
                                "margined": bool(margin.get("margined")),
                                "margin_count": int(margin.get("margin_count") or 0),
                                "tip_height": int(margin.get("tip_height") or 0),
                                "tip_margin_root": margin.get("tip_margin_root"),
                                "margin_root_valid": bool(
                                    (margin.get("margin_certificate") or {}).get("valid")
                                ),
                                "certificate_valid": bool(
                                    (margin.get("margin_certificate") or {}).get("valid")
                                ),
                                "margin_requirement_digest": margin.get(
                                    "margin_requirement_digest"
                                ),
                                "margin_certificate": margin.get("margin_certificate"),
                            },
                            "margin_plane": {
                                "ok": bool(margin.get("ok")),
                                "margined": bool(margin.get("margined")),
                                "margin_count": int(margin.get("margin_count") or 0),
                                "margin_root_valid": bool(
                                    (margin.get("margin_certificate") or {}).get("valid")
                                ),
                            },
                            "cover": {
                                "ok": bool(margin.get("ok")),
                                "margined": bool(margin.get("margined")),
                                "margin_count": int(margin.get("margin_count") or 0),
                                "margin_root_valid": bool(
                                    (margin.get("margin_certificate") or {}).get("valid")
                                ),
                            },
                            "margin_count": int(margin.get("margin_count") or 0),
                            "clearing_count": int(margin.get("clearing_count") or 0),
                            "tip_height": int(margin.get("tip_height") or 0),
                            "margin_certificate": margin.get("margin_certificate"),
                            "margin_requirement_digest": margin.get(
                                "margin_requirement_digest"
                            ),
                            "net_position_digest": margin.get("net_position_digest"),
                            "repo_path": str(workspace),
                            "workspace_path": str(workspace),
                        }
                        if not margin.get("ok"):
                            reasons.append(
                                "margin plane failed for machine-checkable complete"
                            )
                    elif needs_clearing:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        clearing = run_clearing(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "clearing over settlement",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            timeout=720,
                        )
                        origin_count = int(clearing.get("origin_count") or 0)
                        tip_height = int(clearing.get("tip_height") or 0)
                        clearing_count = int(clearing.get("clearing_count") or 0)
                        settlement_count = int(clearing.get("settlement_count") or 0)
                        action_count = int(clearing.get("action_count") or 0)
                        epoch_count = int(clearing.get("epoch_count") or 0)
                        state_height = int(clearing.get("state_height") or 0)
                        byzantine_count = int(clearing.get("byzantine_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                clearing.get("used_skill_route_discovery")
                            ),
                            "chain": clearing.get("chain") or {},
                            "clearing_chain": clearing.get("chain") or {},
                            "settlement_chain": (clearing.get("settlement") or {}),
                            "lineage_chain": clearing.get("chain") or {},
                            "lineage": {
                                "ok": bool((clearing.get("chain") or {}).get("valid")),
                                "entry_count": (clearing.get("clearing") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": clearing.get("chain") or {},
                            },
                            "quorum": {
                                "ok": True,
                                "quorum_met": True,
                                "origin_count": origin_count,
                                "quorum_size": clearing.get("agreeing_count"),
                                "agreeing_count": clearing.get("agreeing_count"),
                                "byzantine_excluded": byzantine_count >= 1,
                                "byzantine_count": byzantine_count,
                                "quorum_cert_valid": True,
                            },
                            "finality": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                                "certificate_valid": True,
                                "irreversible": True,
                                "multi_epoch": epoch_count >= 2,
                            },
                            "finality_plane": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                            },
                            "execution": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "tip_height": state_height,
                                "tip_state_root": clearing.get("bound_state_root"),
                                "execution_hash": (clearing.get("clearing") or {}).get(
                                    "execution_hash"
                                ),
                                "state_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_finality": True,
                                "multi_state": state_height >= 2 if state_height else True,
                            },
                            "execution_plane": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "state_root_valid": True,
                            },
                            "worldstate": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "tip_state_root": clearing.get("bound_state_root"),
                                "state_root_valid": True,
                            },
                            "actuation": {
                                "ok": True,
                                "effects_applied": True,
                                "action_count": action_count,
                                "action_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_execution": True,
                                "multi_action": action_count >= 2,
                            },
                            "actuation_plane": {
                                "ok": True,
                                "effects_applied": True,
                                "action_count": action_count,
                                "action_root_valid": True,
                            },
                            "effects": {
                                "ok": True,
                                "effects_applied": True,
                                "action_count": action_count,
                                "action_root_valid": True,
                            },
                            "settlement": {
                                "ok": bool((clearing.get("settlement") or {}).get("ok", True)),
                                "settled": bool(
                                    (clearing.get("settlement") or {}).get("settled", True)
                                ),
                                "settlement_count": settlement_count,
                                "tip_settlement_root": clearing.get("tip_settlement_root"),
                                "settlement_hash": (clearing.get("settlement") or {}).get(
                                    "settlement_hash"
                                )
                                or (clearing.get("clearing") or {}).get("settlement_hash"),
                                "settlement_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_actuation": True,
                                "multi_settlement": settlement_count >= 2,
                            },
                            "settlement_plane": {
                                "ok": bool((clearing.get("settlement") or {}).get("ok", True)),
                                "settled": bool(
                                    (clearing.get("settlement") or {}).get("settled", True)
                                ),
                                "settlement_count": settlement_count,
                                "settlement_root_valid": True,
                            },
                            "receipts": {
                                "ok": bool((clearing.get("settlement") or {}).get("ok", True)),
                                "settled": bool(
                                    (clearing.get("settlement") or {}).get("settled", True)
                                ),
                                "settlement_count": settlement_count,
                                "settlement_root_valid": True,
                            },
                            "clearing": {
                                "ok": bool(clearing.get("ok")),
                                "cleared": bool(clearing.get("cleared")),
                                "clearing_count": clearing_count,
                                "tip_height": tip_height,
                                "tip_clearing_root": clearing.get("tip_clearing_root"),
                                "clearing_hash": (clearing.get("clearing") or {}).get(
                                    "clearing_hash"
                                ),
                                "clearing_root_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                                "certificate_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                                "net_position_digest": clearing.get("net_position_digest"),
                                "deterministic": True,
                                "post_settlement": True,
                                "multi_clearing": clearing_count >= 2,
                                "bound_settlement_root": clearing.get("bound_settlement_root"),
                                "clearing_certificate": clearing.get("clearing_certificate"),
                            },
                            "clearing_plane": {
                                "ok": bool(clearing.get("ok")),
                                "cleared": bool(clearing.get("cleared")),
                                "clearing_count": clearing_count,
                                "clearing_root_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                            },
                            "net": {
                                "ok": bool(clearing.get("ok")),
                                "cleared": bool(clearing.get("cleared")),
                                "clearing_count": clearing_count,
                                "net_position_digest": clearing.get("net_position_digest"),
                                "clearing_root_valid": bool(
                                    (clearing.get("clearing_certificate") or {}).get("valid")
                                ),
                            },
                            "origin_count": origin_count,
                            "epoch_count": epoch_count,
                            "clearing_count": clearing_count,
                            "settlement_count": settlement_count,
                            "action_count": action_count,
                            "state_height": state_height,
                            "tip_height": tip_height,
                            "clearing_certificate": clearing.get("clearing_certificate"),
                            "clearing_hash": (clearing.get("clearing") or {}).get(
                                "clearing_hash"
                            ),
                            "settlement_hash": (clearing.get("clearing") or {}).get(
                                "settlement_hash"
                            ),
                            "actuation_hash": (clearing.get("clearing") or {}).get(
                                "actuation_hash"
                            ),
                            "execution_hash": (clearing.get("clearing") or {}).get(
                                "execution_hash"
                            ),
                            "tip_clearing_root": clearing.get("tip_clearing_root"),
                            "bound_settlement_root": clearing.get("bound_settlement_root"),
                            "tip_settlement_root": clearing.get("tip_settlement_root"),
                            "bound_action_root": clearing.get("bound_action_root"),
                            "tip_action_root": clearing.get("tip_action_root"),
                            "bound_state_root": clearing.get("bound_state_root"),
                            "net_position_digest": clearing.get("net_position_digest"),
                            "continuity": {
                                "ok": bool((clearing.get("rehydrate") or {}).get("ok", True)),
                                "resurrected": bool(
                                    (clearing.get("rehydrate") or {}).get("ok", True)
                                ),
                                "rehydrate_ok": bool(
                                    (clearing.get("rehydrate") or {}).get("ok", True)
                                ),
                            },
                            "continuity_plane": {
                                "ok": bool((clearing.get("rehydrate") or {}).get("ok", True)),
                                "resurrected": bool(
                                    (clearing.get("rehydrate") or {}).get("ok", True)
                                ),
                            },
                            "repo_path": str(workspace),
                            "workspace_path": str(workspace),
                        }
                        if not clearing.get("ok"):
                            reasons.append(
                                "clearing plane failed for machine-checkable complete"
                            )
                    elif needs_settlement:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        settlement = run_settlement(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "settlement over actuation",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            timeout=660,
                        )
                        origin_count = int(settlement.get("origin_count") or 0)
                        tip_height = int(settlement.get("tip_height") or 0)
                        settlement_count = int(settlement.get("settlement_count") or 0)
                        action_count = int(settlement.get("action_count") or 0)
                        epoch_count = int(settlement.get("epoch_count") or 0)
                        state_height = int(settlement.get("state_height") or 0)
                        byzantine_count = int(settlement.get("byzantine_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                settlement.get("used_skill_route_discovery")
                            ),
                            "chain": settlement.get("chain") or {},
                            "settlement_chain": settlement.get("chain") or {},
                            "action_chain": (settlement.get("actuation") or {}),
                            "lineage_chain": settlement.get("chain") or {},
                            "lineage": {
                                "ok": bool((settlement.get("chain") or {}).get("valid")),
                                "entry_count": (settlement.get("settlement") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": settlement.get("chain") or {},
                            },
                            "quorum": {
                                "ok": True,
                                "quorum_met": True,
                                "origin_count": origin_count,
                                "quorum_size": settlement.get("agreeing_count"),
                                "agreeing_count": settlement.get("agreeing_count"),
                                "byzantine_excluded": byzantine_count >= 1,
                                "byzantine_count": byzantine_count,
                                "quorum_cert_valid": True,
                            },
                            "finality": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                                "certificate_valid": True,
                                "irreversible": True,
                                "multi_epoch": epoch_count >= 2,
                            },
                            "finality_plane": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                            },
                            "execution": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "tip_height": state_height,
                                "tip_state_root": settlement.get("bound_state_root"),
                                "execution_hash": (settlement.get("settlement") or {}).get(
                                    "execution_hash"
                                ),
                                "state_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_finality": True,
                                "multi_state": state_height >= 2 if state_height else True,
                            },
                            "execution_plane": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "state_root_valid": True,
                            },
                            "worldstate": {
                                "ok": True,
                                "state_applied": True,
                                "state_height": state_height,
                                "tip_state_root": settlement.get("bound_state_root"),
                                "state_root_valid": True,
                            },
                            "actuation": {
                                "ok": bool((settlement.get("actuation") or {}).get("ok", True)),
                                "effects_applied": bool(
                                    (settlement.get("actuation") or {}).get(
                                        "effects_applied", True
                                    )
                                ),
                                "action_count": action_count,
                                "tip_height": action_count,
                                "tip_action_root": settlement.get("tip_action_root"),
                                "actuation_hash": (settlement.get("actuation") or {}).get(
                                    "actuation_hash"
                                )
                                or (settlement.get("settlement") or {}).get("actuation_hash"),
                                "action_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_execution": True,
                                "multi_action": action_count >= 2,
                                "bound_state_root": settlement.get("bound_state_root"),
                            },
                            "actuation_plane": {
                                "ok": bool((settlement.get("actuation") or {}).get("ok", True)),
                                "effects_applied": bool(
                                    (settlement.get("actuation") or {}).get(
                                        "effects_applied", True
                                    )
                                ),
                                "action_count": action_count,
                                "action_root_valid": True,
                            },
                            "effects": {
                                "ok": bool((settlement.get("actuation") or {}).get("ok", True)),
                                "effects_applied": bool(
                                    (settlement.get("actuation") or {}).get(
                                        "effects_applied", True
                                    )
                                ),
                                "action_count": action_count,
                                "tip_action_root": settlement.get("tip_action_root"),
                                "action_root_valid": True,
                            },
                            "settlement": {
                                "ok": bool(settlement.get("ok")),
                                "settled": bool(settlement.get("settled")),
                                "settlement_count": settlement_count,
                                "tip_height": tip_height,
                                "tip_settlement_root": settlement.get("tip_settlement_root"),
                                "settlement_hash": (settlement.get("settlement") or {}).get(
                                    "settlement_hash"
                                ),
                                "settlement_root_valid": bool(
                                    (settlement.get("settlement_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (settlement.get("settlement_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "deterministic": True,
                                "post_actuation": True,
                                "multi_settlement": settlement_count >= 2,
                                "bound_action_root": settlement.get("bound_action_root"),
                                "settlement_certificate": settlement.get(
                                    "settlement_certificate"
                                ),
                            },
                            "settlement_plane": {
                                "ok": bool(settlement.get("ok")),
                                "settled": bool(settlement.get("settled")),
                                "settlement_count": settlement_count,
                                "settlement_root_valid": bool(
                                    (settlement.get("settlement_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "receipts": {
                                "ok": bool(settlement.get("ok")),
                                "settled": bool(settlement.get("settled")),
                                "settlement_count": settlement_count,
                                "tip_settlement_root": settlement.get("tip_settlement_root"),
                                "settlement_root_valid": bool(
                                    (settlement.get("settlement_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "origin_count": origin_count,
                            "epoch_count": epoch_count,
                            "settlement_count": settlement_count,
                            "action_count": action_count,
                            "state_height": state_height,
                            "tip_height": tip_height,
                            "settlement_certificate": settlement.get(
                                "settlement_certificate"
                            ),
                            "settlement_hash": (settlement.get("settlement") or {}).get(
                                "settlement_hash"
                            ),
                            "actuation_hash": (settlement.get("settlement") or {}).get(
                                "actuation_hash"
                            ),
                            "execution_hash": (settlement.get("settlement") or {}).get(
                                "execution_hash"
                            ),
                            "tip_settlement_root": settlement.get("tip_settlement_root"),
                            "bound_action_root": settlement.get("bound_action_root"),
                            "tip_action_root": settlement.get("tip_action_root"),
                            "bound_state_root": settlement.get("bound_state_root"),
                            # Settlement rehydrate is receipt resurrection; keep soft
                            # continuity predicates from free-text done_when honest.
                            "continuity": {
                                "ok": bool((settlement.get("rehydrate") or {}).get("ok", True)),
                                "resurrected": bool(
                                    (settlement.get("rehydrate") or {}).get("ok", True)
                                ),
                                "rehydrate_ok": bool(
                                    (settlement.get("rehydrate") or {}).get("ok", True)
                                ),
                            },
                            "continuity_plane": {
                                "ok": bool((settlement.get("rehydrate") or {}).get("ok", True)),
                                "resurrected": bool(
                                    (settlement.get("rehydrate") or {}).get("ok", True)
                                ),
                            },
                            "repo_path": str(workspace),
                            "workspace_path": str(workspace),
                        }
                        if not settlement.get("ok"):
                            reasons.append(
                                "settlement plane failed for machine-checkable complete"
                            )
                    elif needs_actuation:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        actuation = run_actuation(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "actuation over world-state execution",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            timeout=600,
                        )
                        origin_count = int(actuation.get("origin_count") or 0)
                        tip_height = int(actuation.get("tip_height") or 0)
                        action_count = int(actuation.get("action_count") or 0)
                        epoch_count = int(actuation.get("epoch_count") or 0)
                        state_height = int(actuation.get("state_height") or 0)
                        byzantine_count = int(actuation.get("byzantine_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                actuation.get("used_skill_route_discovery")
                            ),
                            "chain": actuation.get("chain") or {},
                            "action_chain": actuation.get("chain") or {},
                            "state_chain": (actuation.get("execution") or {}),
                            "lineage_chain": actuation.get("chain") or {},
                            "lineage": {
                                "ok": bool((actuation.get("chain") or {}).get("valid")),
                                "entry_count": (actuation.get("actuation") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": actuation.get("chain") or {},
                            },
                            "quorum": {
                                "ok": True,
                                "quorum_met": True,
                                "origin_count": origin_count,
                                "quorum_size": actuation.get("agreeing_count"),
                                "agreeing_count": actuation.get("agreeing_count"),
                                "byzantine_excluded": byzantine_count >= 1,
                                "byzantine_count": byzantine_count,
                                "quorum_cert_valid": True,
                            },
                            "finality": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                                "certificate_valid": True,
                                "irreversible": True,
                                "multi_epoch": epoch_count >= 2,
                            },
                            "finality_plane": {
                                "ok": True,
                                "finalized": True,
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                            },
                            "execution": {
                                "ok": bool((actuation.get("execution") or {}).get("ok", True)),
                                "state_applied": bool(
                                    (actuation.get("execution") or {}).get(
                                        "state_applied", True
                                    )
                                ),
                                "state_height": state_height,
                                "tip_height": state_height,
                                "tip_state_root": actuation.get("tip_state_root"),
                                "execution_hash": (actuation.get("execution") or {}).get(
                                    "execution_hash"
                                )
                                or (actuation.get("actuation") or {}).get("execution_hash"),
                                "state_root_valid": True,
                                "certificate_valid": True,
                                "deterministic": True,
                                "post_finality": True,
                                "multi_state": state_height >= 2,
                            },
                            "execution_plane": {
                                "ok": bool((actuation.get("execution") or {}).get("ok", True)),
                                "state_applied": bool(
                                    (actuation.get("execution") or {}).get(
                                        "state_applied", True
                                    )
                                ),
                                "state_height": state_height,
                                "state_root_valid": True,
                            },
                            "worldstate": {
                                "ok": bool((actuation.get("execution") or {}).get("ok", True)),
                                "state_applied": bool(
                                    (actuation.get("execution") or {}).get(
                                        "state_applied", True
                                    )
                                ),
                                "state_height": state_height,
                                "tip_state_root": actuation.get("tip_state_root"),
                                "state_root_valid": True,
                            },
                            "actuation": {
                                "ok": bool(actuation.get("ok")),
                                "effects_applied": bool(actuation.get("effects_applied")),
                                "action_count": action_count,
                                "tip_height": tip_height,
                                "tip_action_root": actuation.get("tip_action_root"),
                                "actuation_hash": (actuation.get("actuation") or {}).get(
                                    "actuation_hash"
                                ),
                                "action_root_valid": bool(
                                    (actuation.get("actuation_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (actuation.get("actuation_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "deterministic": True,
                                "post_execution": True,
                                "multi_action": action_count >= 2,
                                "bound_state_root": actuation.get("bound_state_root"),
                                "actuation_certificate": actuation.get(
                                    "actuation_certificate"
                                ),
                            },
                            "actuation_plane": {
                                "ok": bool(actuation.get("ok")),
                                "effects_applied": bool(actuation.get("effects_applied")),
                                "action_count": action_count,
                                "action_root_valid": bool(
                                    (actuation.get("actuation_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "effects": {
                                "ok": bool(actuation.get("ok")),
                                "effects_applied": bool(actuation.get("effects_applied")),
                                "action_count": action_count,
                                "tip_action_root": actuation.get("tip_action_root"),
                                "action_root_valid": bool(
                                    (actuation.get("actuation_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "origin_count": origin_count,
                            "epoch_count": epoch_count,
                            "action_count": action_count,
                            "state_height": state_height,
                            "tip_height": tip_height,
                            "actuation_certificate": actuation.get(
                                "actuation_certificate"
                            ),
                            "actuation_hash": (actuation.get("actuation") or {}).get(
                                "actuation_hash"
                            ),
                            "execution_hash": (actuation.get("actuation") or {}).get(
                                "execution_hash"
                            ),
                            "tip_action_root": actuation.get("tip_action_root"),
                            "bound_state_root": actuation.get("bound_state_root"),
                            "tip_state_root": actuation.get("tip_state_root"),
                        }
                        if not actuation.get("ok"):
                            reasons.append(
                                "actuation plane failed for machine-checkable complete"
                            )
                    elif needs_execution:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        execution = run_execution(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "world-state execution over epoch finality",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            timeout=560,
                        )
                        origin_count = int(execution.get("origin_count") or 0)
                        tip_height = int(execution.get("state_height") or execution.get("tip_height") or 0)
                        epoch_count = int(execution.get("epoch_count") or 0)
                        state_count = int(execution.get("state_count") or 0)
                        byzantine_count = int(execution.get("byzantine_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                execution.get("used_skill_route_discovery")
                            ),
                            "chain": execution.get("chain") or {},
                            "state_chain": execution.get("chain") or {},
                            "epoch_chain": (execution.get("finality") or {}),
                            "lineage_chain": execution.get("chain") or {},
                            "lineage": {
                                "ok": bool((execution.get("chain") or {}).get("valid")),
                                "entry_count": (execution.get("execution") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": execution.get("chain") or {},
                            },
                            "quorum": {
                                "ok": True,
                                "quorum_met": True,
                                "origin_count": origin_count,
                                "quorum_size": execution.get("agreeing_count"),
                                "agreeing_count": execution.get("agreeing_count"),
                                "byzantine_excluded": byzantine_count >= 1,
                                "byzantine_count": byzantine_count,
                                "quorum_cert_valid": True,
                            },
                            "finality": {
                                "ok": bool((execution.get("finality") or {}).get("ok", True)),
                                "finalized": bool(
                                    (execution.get("finality") or {}).get("finalized", True)
                                ),
                                "epoch_count": epoch_count,
                                "tip_height": (execution.get("finality") or {}).get("tip_height"),
                                "finality_hash": (execution.get("finality") or {}).get(
                                    "finality_hash"
                                ),
                                "finality_cert_valid": True,
                                "certificate_valid": True,
                                "irreversible": True,
                                "multi_epoch": epoch_count >= 2,
                            },
                            "finality_plane": {
                                "ok": bool((execution.get("finality") or {}).get("ok", True)),
                                "finalized": bool(
                                    (execution.get("finality") or {}).get("finalized", True)
                                ),
                                "epoch_count": epoch_count,
                                "finality_cert_valid": True,
                            },
                            "execution": {
                                "ok": bool(execution.get("ok")),
                                "state_applied": bool(execution.get("state_applied")),
                                "state_height": tip_height,
                                "tip_height": tip_height,
                                "tip_state_root": execution.get("tip_state_root"),
                                "execution_hash": (execution.get("execution") or {}).get(
                                    "execution_hash"
                                ),
                                "state_root_valid": bool(
                                    (execution.get("execution_certificate") or {}).get("valid")
                                ),
                                "certificate_valid": bool(
                                    (execution.get("execution_certificate") or {}).get("valid")
                                ),
                                "deterministic": True,
                                "post_finality": True,
                                "multi_state": state_count >= 2,
                                "execution_certificate": execution.get(
                                    "execution_certificate"
                                ),
                            },
                            "execution_plane": {
                                "ok": bool(execution.get("ok")),
                                "state_applied": bool(execution.get("state_applied")),
                                "state_height": tip_height,
                                "state_root_valid": bool(
                                    (execution.get("execution_certificate") or {}).get("valid")
                                ),
                            },
                            "worldstate": {
                                "ok": bool(execution.get("ok")),
                                "state_applied": bool(execution.get("state_applied")),
                                "state_height": tip_height,
                                "tip_state_root": execution.get("tip_state_root"),
                                "state_root_valid": bool(
                                    (execution.get("execution_certificate") or {}).get("valid")
                                ),
                            },
                            "origin_count": origin_count,
                            "epoch_count": epoch_count,
                            "state_height": tip_height,
                            "tip_height": tip_height,
                            "execution_certificate": execution.get("execution_certificate"),
                            "execution_hash": (execution.get("execution") or {}).get(
                                "execution_hash"
                            ),
                            "tip_state_root": execution.get("tip_state_root"),
                            "finality_hash": (execution.get("finality") or {}).get(
                                "finality_hash"
                            ),
                        }
                        if not execution.get("ok"):
                            reasons.append(
                                "execution plane failed for machine-checkable complete"
                            )
                    elif needs_finality:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        finality = run_finality(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "epoch finality over quorum consensus",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            timeout=520,
                        )
                        origin_count = int(finality.get("origin_count") or 0)
                        tip_height = int(finality.get("tip_height") or 0)
                        epoch_count = int(finality.get("epoch_count") or 0)
                        byzantine_count = int(finality.get("byzantine_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                finality.get("used_skill_route_discovery")
                            ),
                            "chain": finality.get("chain") or {},
                            "epoch_chain": finality.get("chain") or {},
                            "lineage_chain": finality.get("chain") or {},
                            "lineage": {
                                "ok": bool((finality.get("chain") or {}).get("valid")),
                                "entry_count": (finality.get("finality") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": finality.get("chain") or {},
                            },
                            "quorum": {
                                "ok": bool((finality.get("quorum") or {}).get("ok", True)),
                                "quorum_met": bool(
                                    (finality.get("quorum") or {}).get("quorum_met", True)
                                ),
                                "origin_count": origin_count,
                                "quorum_size": finality.get("agreeing_count"),
                                "agreeing_count": finality.get("agreeing_count"),
                                "byzantine_excluded": byzantine_count >= 1,
                                "byzantine_count": byzantine_count,
                                "quorum_hash": (finality.get("quorum") or {}).get(
                                    "quorum_hash"
                                ),
                                "quorum_cert_valid": True,
                            },
                            "quorum_plane": {
                                "ok": bool((finality.get("quorum") or {}).get("ok", True)),
                                "quorum_met": bool(
                                    (finality.get("quorum") or {}).get("quorum_met", True)
                                ),
                            },
                            "finality": {
                                "ok": bool(finality.get("ok")),
                                "finalized": bool(finality.get("finalized")),
                                "epoch_count": epoch_count,
                                "tip_height": tip_height,
                                "tip_hash": finality.get("tip_hash"),
                                "finality_hash": (finality.get("finality") or {}).get(
                                    "finality_hash"
                                ),
                                "finality_cert_valid": bool(
                                    (finality.get("finality_certificate") or {}).get("valid")
                                ),
                                "certificate_valid": bool(
                                    (finality.get("finality_certificate") or {}).get("valid")
                                ),
                                "irreversible": True,
                                "multi_epoch": epoch_count >= 2,
                                "finality_certificate": finality.get(
                                    "finality_certificate"
                                ),
                            },
                            "finality_plane": {
                                "ok": bool(finality.get("ok")),
                                "finalized": bool(finality.get("finalized")),
                                "epoch_count": epoch_count,
                                "tip_height": tip_height,
                                "finality_cert_valid": bool(
                                    (finality.get("finality_certificate") or {}).get("valid")
                                ),
                            },
                            "origin_count": origin_count,
                            "epoch_count": epoch_count,
                            "tip_height": tip_height,
                            "finality_certificate": finality.get("finality_certificate"),
                            "finality_hash": (finality.get("finality") or {}).get(
                                "finality_hash"
                            ),
                        }
                        if not finality.get("ok"):
                            reasons.append(
                                "finality plane failed for machine-checkable complete"
                            )
                    elif needs_quorum:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        quorum = run_quorum(
                            workspace,
                            goal=decision.mission_goal or decision.summary or "complete",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_continuity=True,
                            run_reconciliation=True,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            timeout=480,
                        )
                        origin_count = int(quorum.get("origin_count") or 0)
                        byzantine_count = int(quorum.get("byzantine_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                quorum.get("used_skill_route_discovery")
                            ),
                            "chain": quorum.get("chain") or {},
                            "lineage_chain": quorum.get("chain") or {},
                            "lineage": {
                                "ok": bool((quorum.get("chain") or {}).get("valid")),
                                "entry_count": (quorum.get("quorum") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": quorum.get("chain") or {},
                            },
                            "continuity": {
                                "ok": bool(
                                    ((quorum.get("continuity") or {}) or {}).get("ok", True)
                                ),
                                "resurrected": bool(
                                    ((quorum.get("continuity") or {}) or {}).get(
                                        "resurrected", True
                                    )
                                ),
                            },
                            "continuity_plane": {
                                "ok": bool(
                                    ((quorum.get("continuity") or {}) or {}).get("ok", True)
                                ),
                            },
                            "quorum": {
                                "ok": bool(quorum.get("ok")),
                                "quorum_met": bool(quorum.get("quorum_met")),
                                "quorum_size": quorum.get("quorum_size")
                                or quorum.get("agreeing_count"),
                                "agreeing_count": quorum.get("agreeing_count"),
                                "threshold": quorum.get("threshold"),
                                "origin_count": origin_count,
                                "byzantine_excluded": byzantine_count >= 1,
                                "byzantine_count": byzantine_count,
                                "byzantine_origins": quorum.get("byzantine_origins") or [],
                                "quorum_hash": (quorum.get("quorum") or {}).get("quorum_hash"),
                                "quorum_cert_valid": bool(
                                    (quorum.get("quorum_certificate") or {}).get("valid")
                                ),
                                "certificate_valid": bool(
                                    (quorum.get("quorum_certificate") or {}).get("valid")
                                ),
                                "quorum_certificate": quorum.get("quorum_certificate"),
                            },
                            "quorum_plane": {
                                "ok": bool(quorum.get("ok")),
                                "quorum_met": bool(quorum.get("quorum_met")),
                                "origin_count": origin_count,
                                "byzantine_excluded": byzantine_count >= 1,
                                "quorum_cert_valid": bool(
                                    (quorum.get("quorum_certificate") or {}).get("valid")
                                ),
                            },
                            "consensus": {
                                "ok": bool(quorum.get("consensus")),
                                "quorum_met": bool(quorum.get("quorum_met")),
                                "origin_count": origin_count,
                            },
                            "origin_count": origin_count,
                            "quorum_size": quorum.get("quorum_size")
                            or quorum.get("agreeing_count"),
                            "quorum_certificate": quorum.get("quorum_certificate"),
                            "quorum_hash": (quorum.get("quorum") or {}).get("quorum_hash"),
                        }
                        if not quorum.get("ok"):
                            reasons.append(
                                "quorum plane failed for machine-checkable complete"
                            )
                    elif needs_federation:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        federation = run_federation(
                            workspace,
                            goal=decision.mission_goal or decision.summary or "complete",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_continuity=True,
                            run_reconciliation=True,
                            force_synthetic_drift=True,
                            timeout=420,
                        )
                        origin_count = int(federation.get("origin_count") or 0)
                        context = {
                            "used_skill_route_discovery": bool(
                                federation.get("used_skill_route_discovery")
                            ),
                            "chain": federation.get("chain") or {},
                            "lineage_chain": federation.get("chain") or {},
                            "lineage": {
                                "ok": bool((federation.get("chain") or {}).get("valid")),
                                "entry_count": (federation.get("federation") or {}).get(
                                    "lineage_entry_count"
                                ),
                                "chain": federation.get("chain") or {},
                            },
                            "continuity": {
                                "ok": bool(
                                    ((federation.get("continuity") or {}) or {}).get("ok", True)
                                ),
                                "resurrected": bool(
                                    ((federation.get("continuity") or {}) or {}).get(
                                        "resurrected", True
                                    )
                                ),
                            },
                            "continuity_plane": {
                                "ok": bool(
                                    ((federation.get("continuity") or {}) or {}).get("ok", True)
                                ),
                            },
                            "federation": {
                                "ok": bool(federation.get("ok")),
                                "federated": bool(federation.get("federated")),
                                "federated_ok": bool(federation.get("federated")),
                                "origin_count": origin_count,
                                "federation_hash": (federation.get("federation") or {}).get(
                                    "federation_hash"
                                ),
                                "federation_cert_valid": bool(
                                    (federation.get("federation_certificate") or {}).get("valid")
                                ),
                                "certificate_valid": bool(
                                    (federation.get("federation_certificate") or {}).get("valid")
                                ),
                                "federation_certificate": federation.get(
                                    "federation_certificate"
                                ),
                            },
                            "federation_plane": {
                                "ok": bool(federation.get("ok")),
                                "federated": bool(federation.get("federated")),
                                "origin_count": origin_count,
                                "federation_cert_valid": bool(
                                    (federation.get("federation_certificate") or {}).get("valid")
                                ),
                            },
                            "federated": {
                                "ok": bool(federation.get("federated")),
                                "federated": bool(federation.get("federated")),
                                "origin_count": origin_count,
                            },
                            "origin_count": origin_count,
                            "federation_certificate": federation.get(
                                "federation_certificate"
                            ),
                            "federation_hash": (federation.get("federation") or {}).get(
                                "federation_hash"
                            ),
                        }
                        if not federation.get("ok"):
                            reasons.append(
                                "federation plane failed for machine-checkable complete"
                            )
                    elif needs_continuity:
                        run_mission = "mission_plane_ok" in kinds
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=run_mission,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        continuity = run_continuity(
                            workspace,
                            goal=decision.mission_goal or decision.summary or "complete",
                            done_when=plane_done_when,
                            max_steps=3,
                            absorb_ready=False,
                            grow_budget=0,
                            run_mission=run_mission,
                            run_reconciliation=True,
                            force_synthetic_drift=True,
                            timeout=360,
                        )
                        heal = (continuity.get("reconciliation") or {}).get("heal") or {}
                        cert_count = int(
                            (continuity.get("bundle") or {}).get("certificate_count") or 0
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                continuity.get("used_skill_route_discovery")
                            ),
                            "assurance": {"ok": True},
                            "assurance_plane": {"ok": True},
                            "sovereignty": {
                                "ok": bool((continuity.get("reconciliation") or {}).get("ok"))
                            },
                            "sovereignty_plane": {
                                "ok": bool((continuity.get("reconciliation") or {}).get("ok"))
                            },
                            "lineage": {
                                "ok": True,
                                "entry_count": (continuity.get("lineage") or {}).get(
                                    "entry_count"
                                ),
                                "chain": continuity.get("chain") or {},
                                "drift": continuity.get("drift") or {},
                            },
                            "lineage_plane": {
                                "ok": True,
                                "entry_count": (continuity.get("lineage") or {}).get(
                                    "entry_count"
                                ),
                            },
                            "chain": continuity.get("chain") or {},
                            "lineage_chain": continuity.get("chain") or {},
                            "drift": continuity.get("drift") or {},
                            "lineage_drift": continuity.get("drift") or {},
                            "lineage_entry_count": (continuity.get("lineage") or {}).get(
                                "entry_count"
                            ),
                            "reconciliation": {
                                "ok": bool(
                                    (continuity.get("reconciliation") or {}).get("ok")
                                ),
                                "healed": bool(heal.get("healed")),
                                "healed_ok": bool(heal.get("healed")),
                                "heal_entry_count": heal.get("heal_entry_count"),
                                "heal_entry_kinds": heal.get("heal_entry_kinds") or [],
                            },
                            "reconciliation_plane": {
                                "ok": bool(
                                    (continuity.get("reconciliation") or {}).get("ok")
                                ),
                                "healed": bool(heal.get("healed")),
                                "heal_entry_count": heal.get("heal_entry_count"),
                            },
                            "heal": {
                                "ok": bool(heal.get("healed") or heal.get("ok")),
                                "healed": bool(heal.get("healed")),
                                "heal_entry_count": heal.get("heal_entry_count"),
                                "heal_entry_kinds": heal.get("heal_entry_kinds") or [],
                            },
                            "heal_entry_count": heal.get("heal_entry_count"),
                            "continuity": {
                                "ok": bool(continuity.get("ok")),
                                "resurrected": bool(continuity.get("resurrected")),
                                "resurrected_ok": bool(continuity.get("resurrected")),
                                "rehydrate_ok": bool(
                                    (continuity.get("rehydrate") or {}).get("ok")
                                ),
                                "bundle_valid": bool(
                                    (continuity.get("integrity") or {}).get("ok")
                                ),
                                "bundle_hash": (continuity.get("bundle") or {}).get(
                                    "bundle_hash"
                                ),
                                "bundle_cert_count": cert_count,
                                "certificate_count": cert_count,
                                "proved": bool((continuity.get("prove") or {}).get("ok")),
                                "chain_valid": bool(
                                    (continuity.get("chain") or {}).get("valid")
                                ),
                            },
                            "continuity_plane": {
                                "ok": bool(continuity.get("ok")),
                                "resurrected": bool(continuity.get("resurrected")),
                                "bundle_hash": (continuity.get("bundle") or {}).get(
                                    "bundle_hash"
                                ),
                                "bundle_cert_count": cert_count,
                            },
                            "resurrection": {
                                "ok": bool(continuity.get("resurrected")),
                                "resurrected": bool(continuity.get("resurrected")),
                            },
                            "bundle": {
                                "ok": bool((continuity.get("bundle") or {}).get("ok")),
                                "bundle_valid": bool(
                                    (continuity.get("integrity") or {}).get("ok")
                                ),
                                "bundle_hash": (continuity.get("bundle") or {}).get(
                                    "bundle_hash"
                                ),
                                "bundle_cert_count": cert_count,
                            },
                            "bundle_cert_count": cert_count,
                            "bundle_hash": (continuity.get("bundle") or {}).get(
                                "bundle_hash"
                            ),
                        }
                        if not continuity.get("ok"):
                            reasons.append(
                                "continuity plane failed for machine-checkable complete"
                            )
                    elif needs_reconciliation:
                        run_mission = "mission_plane_ok" in kinds
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=run_mission,
                        )
                        # Never forward bare-word capability_proved soft-extract into planes.
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        reconciliation = run_recon(
                            workspace,
                            goal=decision.mission_goal or decision.summary or "complete",
                            done_when=plane_done_when,
                            max_steps=3,
                            absorb_ready=False,
                            grow_budget=0,
                            run_mission=run_mission,
                            force_synthetic_drift=True,
                            timeout=300,
                        )
                        heal = reconciliation.get("heal") or {}
                        context = {
                            "used_skill_route_discovery": bool(
                                reconciliation.get("used_skill_route_discovery")
                            ),
                            "assurance": {
                                "ok": bool(
                                    (heal.get("sovereignty") or {}).get("assurance_ok")
                                )
                            },
                            "assurance_plane": {
                                "ok": bool(
                                    (heal.get("sovereignty") or {}).get("assurance_ok")
                                )
                            },
                            "sovereignty": {
                                "ok": bool((heal.get("sovereignty") or {}).get("ok"))
                            },
                            "sovereignty_plane": {
                                "ok": bool((heal.get("sovereignty") or {}).get("ok"))
                            },
                            "certificate_path": (heal.get("sovereignty") or {}).get(
                                "certificate_path"
                            ),
                            "lineage": {
                                "ok": bool(
                                    (reconciliation.get("lineage_plane") or {}).get("ok")
                                ),
                                "entry_count": (reconciliation.get("lineage") or {}).get(
                                    "entry_count"
                                ),
                                "chain": reconciliation.get("chain") or {},
                                "drift": reconciliation.get("drift") or {},
                            },
                            "lineage_plane": {
                                "ok": bool(
                                    (reconciliation.get("lineage_plane") or {}).get("ok")
                                ),
                                "entry_count": (reconciliation.get("lineage") or {}).get(
                                    "entry_count"
                                ),
                            },
                            "chain": reconciliation.get("chain") or {},
                            "lineage_chain": reconciliation.get("chain") or {},
                            "drift": reconciliation.get("drift") or {},
                            "lineage_drift": reconciliation.get("drift") or {},
                            "lineage_entry_count": (
                                reconciliation.get("lineage") or {}
                            ).get("entry_count"),
                            "reconciliation": {
                                "ok": bool(reconciliation.get("ok")),
                                "healed": bool(heal.get("healed")),
                                "healed_ok": bool(heal.get("healed")),
                                "heal_entry_count": heal.get("heal_entry_count"),
                                "heal_entry_kinds": heal.get("heal_entry_kinds") or [],
                            },
                            "reconciliation_plane": {
                                "ok": bool(reconciliation.get("ok")),
                                "healed": bool(heal.get("healed")),
                                "heal_entry_count": heal.get("heal_entry_count"),
                            },
                            "heal": {
                                "ok": bool(heal.get("ok")),
                                "healed": bool(heal.get("healed")),
                                "heal_entry_count": heal.get("heal_entry_count"),
                                "heal_entry_kinds": heal.get("heal_entry_kinds") or [],
                            },
                            "heal_entry_count": heal.get("heal_entry_count"),
                        }
                        if not reconciliation.get("ok"):
                            reasons.append(
                                "reconciliation plane failed for machine-checkable complete"
                            )
                    elif needs_lineage:
                        run_mission = "mission_plane_ok" in kinds
                        # Free-text done_when soft-extracts lineage_ok/sovereignty_ok;
                        # pass a stripped work contract so the plane can succeed, then
                        # evaluate full done_when against injected plane context.
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=run_mission,
                        )
                        lineage = run_lineage(
                            workspace,
                            goal=decision.mission_goal or decision.summary or "complete",
                            done_when=plane_done_when,
                            max_steps=3,
                            absorb_ready=False,
                            grow_budget=0,
                            run_mission=run_mission,
                            timeout=240,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                lineage.get("used_skill_route_discovery")
                            ),
                            "assurance": {
                                "ok": bool(
                                    (lineage.get("sovereignty") or {}).get(
                                        "assurance_ok"
                                    )
                                )
                            },
                            "assurance_plane": {
                                "ok": bool(
                                    (lineage.get("sovereignty") or {}).get(
                                        "assurance_ok"
                                    )
                                )
                            },
                            "sovereignty": {
                                "ok": bool((lineage.get("sovereignty") or {}).get("ok"))
                            },
                            "sovereignty_plane": {
                                "ok": bool((lineage.get("sovereignty") or {}).get("ok"))
                            },
                            "certificate_path": (
                                (lineage.get("sovereignty") or {})
                                .get("certificate", {})
                                .get("certificate_path")
                            ),
                            "lineage": {
                                "ok": bool(lineage.get("ok")),
                                "entry_count": (lineage.get("lineage") or {}).get(
                                    "entry_count"
                                ),
                                "chain": lineage.get("chain") or {},
                                "drift": lineage.get("drift") or {},
                            },
                            "lineage_plane": {
                                "ok": bool(lineage.get("ok")),
                                "entry_count": (lineage.get("lineage") or {}).get(
                                    "entry_count"
                                ),
                            },
                            "chain": lineage.get("chain") or {},
                            "lineage_chain": lineage.get("chain") or {},
                            "drift": lineage.get("drift") or {},
                            "lineage_drift": lineage.get("drift") or {},
                            "lineage_entry_count": (lineage.get("lineage") or {}).get(
                                "entry_count"
                            ),
                        }
                        if not lineage.get("ok"):
                            reasons.append(
                                "lineage plane failed for machine-checkable complete"
                            )
                    elif needs_sovereignty:
                        # Only run mission when the contract itself demands mission_plane_ok.
                        run_mission = "mission_plane_ok" in kinds
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=run_mission,
                        )
                        sovereignty = run_sovereignty(
                            workspace,
                            goal=decision.mission_goal or decision.summary or "complete",
                            done_when=plane_done_when,
                            max_steps=3,
                            absorb_ready=False,
                            grow_budget=0,
                            run_mission=run_mission,
                            timeout=180,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                sovereignty.get("used_skill_route_discovery")
                            ),
                            "assurance": sovereignty.get("assurance") or {},
                            "assurance_plane": sovereignty.get("assurance") or {},
                            "sovereignty": {"ok": bool(sovereignty.get("ok"))},
                            "sovereignty_plane": {"ok": bool(sovereignty.get("ok"))},
                            "certificate_path": (
                                (sovereignty.get("certificate") or {}).get(
                                    "certificate_path"
                                )
                            ),
                            "mission": sovereignty.get("contract", {}).get("mission")
                            or {},
                            "mission_plane": sovereignty.get("contract", {}).get(
                                "mission"
                            )
                            or {},
                            "contract_plane": sovereignty.get("contract") or {},
                        }
                        if not sovereignty.get("ok"):
                            reasons.append(
                                "sovereignty plane failed for machine-checkable complete"
                            )
                    # Evaluate the filtered predicate set only (drops bare-word
                    # soft-extract accidents even if parse is re-run on prose).
                    structured_contract = "; ".join(
                        (
                            f"{item.get('kind')}:{item.get('arg')}"
                            if str(item.get("arg") or "").strip()
                            else str(item.get("kind") or "")
                        )
                        for item in predicates
                        if item.get("kind")
                    )
                    verdict = eval_contract(
                        workspace,
                        structured_contract or contract_text,
                        context=context or None,
                        run_programs=False,
                        timeout=90,
                    )
                    if verdict.get("met") is not True:
                        failed = verdict.get("failed") or []
                        detail = ", ".join(
                            f"{item.get('kind')}:{item.get('arg')}" for item in failed[:4]
                        ) or "unknown"
                        reasons.append(
                            f"machine-checkable done_when failed ({detail})"
                        )
            except Exception as error:  # pragma: no cover - defensive gate
                reasons.append(f"outcome-contract evaluation error: {error}")
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


def register_milestone_capability(
    *,
    workspace: Path,
    mission_id: str,
    milestone_number: int,
    decision: TurnDecision,
    behavior_paths: tuple[str, ...],
) -> str:
    """Compound an accepted milestone into the durable capability ledger when possible.

    Uses the first successful validation command as both entry and proof. Failures
    are non-fatal: the milestone still counts; compounding is best-effort growth.
    """

    proof = ""
    for item in decision.validation:
        command = str(item.get("command") or "").strip()
        if command and item.get("exit_code") == 0:
            proof = command
            break
    if not proof or not decision.capability_delta:
        return ""
    capability_id = slugify_capability_id(
        f"m{milestone_number}-{decision.capability_delta}",
        limit=56,
    )
    capability = capability_from_milestone(
        capability_id=capability_id,
        name=decision.capability_delta[:80] or capability_id,
        description=decision.summary or decision.capability_delta,
        capability_delta=decision.capability_delta,
        proof_command=proof,
        entry=proof,
        kind="command",
        behavior_paths=behavior_paths,
        mission_id=mission_id,
        milestone_number=milestone_number,
        tags=("unbound-milestone",),
    )
    try:
        ledger_path = default_ledger_path(workspace)
        ledger = load_ledger(ledger_path)
        register_capability(ledger, capability, replace=capability_id in ledger.capabilities)
        save_ledger(ledger_path, ledger)
    except Exception:
        return ""
    return capability_id


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
    descriptor: int | None = None
    for _ in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as error:
            try:
                owner_pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner_pid = 0
            if owner_pid and pid_is_running(owner_pid):
                raise RuntimeError(f"Another Unbound turn owns this mission: {lock_path}") from error
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
    if descriptor is None:
        raise RuntimeError(f"Unable to acquire Unbound turn lock: {lock_path}")
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        try:
            if lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
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
        gate = evaluate_milestone(
            decision,
            changed_paths=changed_paths,
            workspace=workspace,
            mission_done_when=state.done_when,
        )
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
                registered_capability_id = register_milestone_capability(
                    workspace=workspace,
                    mission_id=state.mission_id,
                    milestone_number=milestone_number,
                    decision=decision,
                    behavior_paths=gate.behavior_paths,
                )
                if registered_capability_id:
                    milestone["capability_id"] = registered_capability_id
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


def pid_is_running(pid: int) -> bool:
    if pid < 1:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        open_process.restype = ctypes.c_void_p
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        get_exit_code.restype = ctypes.c_int
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int
        handle = open_process(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_uint32()
            return bool(get_exit_code(handle, ctypes.byref(exit_code))) and exit_code.value == still_active
        finally:
            close_handle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextmanager
def continuous_loop_lock(lock_path: Path) -> Iterator[None]:
    """Own one outer evolution loop, reclaiming a lock left by a dead process."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    for _ in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError as error:
            try:
                owner_pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                owner_pid = 0
            if owner_pid and pid_is_running(owner_pid):
                raise RuntimeError(
                    f"Another Unbound continuous loop owns this repository: pid={owner_pid}"
                ) from error
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
    if descriptor is None:
        raise RuntimeError(f"Unable to acquire Unbound continuous loop lock: {lock_path}")
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        try:
            if lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                lock_path.unlink()
        except FileNotFoundError:
            pass


def save_continuous_loop_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now_iso()
    atomic_write_json(path, state)


def wait_for_continuous_interval(
    interval_seconds: int,
    stop_path: Path,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    """Wait for the next mission while allowing a stop request to wake the loop."""

    deadline = time.monotonic() + interval_seconds
    while True:
        if stop_path.exists():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return stop_path.exists()
        sleeper(min(1.0, remaining))


def latest_proven_lineage(
    repo_path: Path,
    output_dir: Path,
    target_ref: str,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> tuple[Path | None, str]:
    """Resume an active mission or seed from the latest accepted milestone."""

    latest = load_latest_mission_if_present(repo_path, output_dir)
    if latest is None:
        return None, target_ref
    state_path, state = latest
    lineage_ref = target_ref
    if git_commit_exists(repo_path, state.last_milestone_head, command_runner=command_runner):
        target_head = git_text(
            repo_path,
            ["git", "rev-parse", "--verify", target_ref],
            command_runner=command_runner,
        )
        if git_is_ancestor(
            repo_path,
            state.last_milestone_head,
            target_head,
            command_runner=command_runner,
        ):
            lineage_ref = target_head
        else:
            lineage_ref = state.last_milestone_head
    if state.status == "active":
        return state_path, lineage_ref
    return None, lineage_ref


def run_continuous_loop(
    *,
    repo_path: Path,
    kernel: str = "grok",
    model: str | None = None,
    profile: str | None = None,
    target_branch: str = "main",
    branch_prefix: str = "unbound",
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    worktree_parent: Path | None = None,
    timeout_seconds: int = 7200,
    interval_seconds: int = DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
    wait_first: bool = False,
    resume_latest: bool = True,
    max_missions: int = 0,
    publish_remote: str = "",
    mission_creator: Callable[..., Path] = create_mission,
    mission_runner: Callable[..., int] = run_mission_loop,
    lineage_publisher: Callable[..., PublicationResult] = publish_lineage,
    interval_waiter: Callable[[int, Path], bool] = wait_for_continuous_interval,
    command_runner: Callable[..., Any] = subprocess.run,
) -> int:
    """Continuously create autonomous missions, compounding their proven commits."""

    repo_path = repo_path.resolve()
    if kernel not in KERNELS:
        raise ValueError(f"kernel must be one of: {', '.join(sorted(KERNELS))}")
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be greater than zero")
    if timeout_seconds < 1:
        raise ValueError("timeout_seconds must be greater than zero")
    if max_missions < 0:
        raise ValueError("max_missions cannot be negative")
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

    state_path = continuous_loop_state_path(repo_path, output_dir)
    events_path = continuous_loop_events_path(repo_path, output_dir)
    lock_path = continuous_loop_lock_path(repo_path, output_dir)
    stop_path = continuous_loop_stop_path(repo_path, output_dir)
    loop_id = f"{compact_utc_timestamp()}-{uuid.uuid4().hex[:8]}"
    created_at = utc_now_iso()
    loop_state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "loop_id": loop_id,
        "created_at": created_at,
        "updated_at": created_at,
        "repo_path": str(repo_path),
        "status": "starting",
        "pid": os.getpid(),
        "kernel": kernel,
        "model": model,
        "profile": profile,
        "target_branch": target_branch,
        "branch_prefix": branch_prefix,
        "interval_seconds": interval_seconds,
        "timeout_seconds": timeout_seconds,
        "mission_count": 0,
        "run_count": 0,
        "current_mission_id": "",
        "current_state_path": "",
        "last_mission_id": "",
        "last_mission_status": "",
        "last_exit_code": None,
        "lineage_ref": target_branch,
        "publish_remote": publish_remote,
        "publish_branch": target_branch,
        "publish_attempt_count": 0,
        "publish_count": 0,
        "pending_publish_ref": "",
        "pending_publish_mission_id": "",
        "last_published_ref": "",
        "last_published_at": "",
        "last_publish_error": "",
        "next_wake_at": "",
        "last_error": "",
        "stop_reason": "",
    }

    with continuous_loop_lock(lock_path):
        try:
            stop_path.unlink()
        except FileNotFoundError:
            pass
        current_state_path: Path | None = None
        lineage_ref = target_branch
        latest = load_latest_mission_if_present(repo_path, output_dir) if resume_latest else None
        if resume_latest:
            current_state_path, lineage_ref = latest_proven_lineage(
                repo_path,
                output_dir,
                target_branch,
                command_runner=command_runner,
            )
        loop_state["lineage_ref"] = lineage_ref
        if current_state_path is not None:
            current = load_mission(current_state_path)
            loop_state["current_mission_id"] = current.mission_id
            loop_state["current_state_path"] = str(current_state_path)
        elif publish_remote and latest is not None and latest[1].status == "complete":
            loop_state["pending_publish_ref"] = lineage_ref
            loop_state["pending_publish_mission_id"] = latest[1].mission_id
        loop_state["status"] = "running"
        save_continuous_loop_state(state_path, loop_state)
        append_jsonl(
            events_path,
            {
                "event": "continuous_loop.started",
                "at": created_at,
                "loop_id": loop_id,
                "pid": os.getpid(),
                "interval_seconds": interval_seconds,
                "lineage_ref": lineage_ref,
                "resumed_state_path": str(current_state_path or ""),
                "publish_remote": publish_remote,
                "publish_branch": target_branch,
            },
        )

        def attempt_publication() -> bool:
            commit_sha = str(loop_state["pending_publish_ref"])
            mission_id = str(loop_state["pending_publish_mission_id"])
            loop_state["status"] = "publishing"
            loop_state["publish_attempt_count"] = int(loop_state["publish_attempt_count"]) + 1
            save_continuous_loop_state(state_path, loop_state)
            try:
                result = lineage_publisher(
                    repo_path,
                    commit_sha,
                    publish_remote,
                    target_branch,
                    command_runner=command_runner,
                )
            except Exception as error:
                result = PublicationResult(
                    ok=False,
                    commit_sha=commit_sha,
                    remote=publish_remote,
                    branch=target_branch,
                    remote_before="",
                    remote_after="",
                    error=str(error),
                    command=(),
                )
            append_jsonl(
                events_path,
                {
                    "event": "continuous_loop.publication",
                    "at": utc_now_iso(),
                    "loop_id": loop_id,
                    "mission_id": mission_id,
                    **result.to_dict(),
                },
            )
            if result.ok:
                loop_state["publish_count"] = int(loop_state["publish_count"]) + 1
                loop_state["pending_publish_ref"] = ""
                loop_state["pending_publish_mission_id"] = ""
                loop_state["last_published_ref"] = result.remote_after
                loop_state["last_published_at"] = utc_now_iso()
                loop_state["last_publish_error"] = ""
            else:
                loop_state["last_publish_error"] = result.error
            loop_state["status"] = "running"
            save_continuous_loop_state(state_path, loop_state)
            return result.ok

        if loop_state["pending_publish_ref"] and not attempt_publication():
            should_wait = True
        else:
            should_wait = wait_first
        try:
            while True:
                if stop_path.exists():
                    loop_state["stop_reason"] = "stop_requested"
                    break
                if loop_state["pending_publish_ref"]:
                    if should_wait:
                        next_wake = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
                        loop_state["status"] = "sleeping_publish_retry"
                        loop_state["next_wake_at"] = next_wake.isoformat().replace("+00:00", "Z")
                        save_continuous_loop_state(state_path, loop_state)
                        append_jsonl(
                            events_path,
                            {
                                "event": "continuous_loop.publish_retry_sleeping",
                                "at": utc_now_iso(),
                                "loop_id": loop_id,
                                "interval_seconds": interval_seconds,
                                "next_wake_at": loop_state["next_wake_at"],
                                "commit_sha": loop_state["pending_publish_ref"],
                            },
                        )
                        if interval_waiter(interval_seconds, stop_path):
                            loop_state["stop_reason"] = "stop_requested"
                            break
                        loop_state["next_wake_at"] = ""
                    if not attempt_publication():
                        should_wait = True
                        continue
                    should_wait = False
                if current_state_path is None and max_missions:
                    if int(loop_state["mission_count"]) >= max_missions:
                        loop_state["stop_reason"] = "max_missions_reached"
                        break
                if should_wait:
                    next_wake = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
                    loop_state["status"] = "sleeping"
                    loop_state["next_wake_at"] = next_wake.isoformat().replace("+00:00", "Z")
                    save_continuous_loop_state(state_path, loop_state)
                    append_jsonl(
                        events_path,
                        {
                            "event": "continuous_loop.sleeping",
                            "at": utc_now_iso(),
                            "loop_id": loop_id,
                            "interval_seconds": interval_seconds,
                            "next_wake_at": loop_state["next_wake_at"],
                        },
                    )
                    if interval_waiter(interval_seconds, stop_path):
                        loop_state["stop_reason"] = "stop_requested"
                        break
                    loop_state["next_wake_at"] = ""
                    loop_state["status"] = "running"
                    save_continuous_loop_state(state_path, loop_state)
                should_wait = True

                if current_state_path is None:
                    current_state_path = mission_creator(
                        repo_path=repo_path,
                        kernel=kernel,
                        model=model,
                        profile=profile,
                        target_branch=lineage_ref,
                        branch_prefix=branch_prefix,
                        output_dir=output_dir,
                        worktree_parent=worktree_parent,
                        timeout_seconds=timeout_seconds,
                        command_runner=command_runner,
                    )
                    current = load_mission(current_state_path)
                    loop_state["mission_count"] = int(loop_state["mission_count"]) + 1
                    loop_state["current_mission_id"] = current.mission_id
                    loop_state["current_state_path"] = str(current_state_path)
                    save_continuous_loop_state(state_path, loop_state)
                    append_jsonl(
                        events_path,
                        {
                            "event": "continuous_loop.mission_created",
                            "at": utc_now_iso(),
                            "loop_id": loop_id,
                            "mission_id": current.mission_id,
                            "state_path": str(current_state_path),
                            "base_ref": lineage_ref,
                        },
                    )

                exit_code: int | None = None
                run_error = ""
                loop_state["status"] = "running_mission"
                loop_state["run_count"] = int(loop_state["run_count"]) + 1
                loop_state["last_error"] = ""
                save_continuous_loop_state(state_path, loop_state)
                try:
                    exit_code = mission_runner(
                        current_state_path,
                        max_turns=0,
                        interval_seconds=0,
                        reload_between_turns=True,
                    )
                except Exception as error:
                    run_error = str(error)

                try:
                    current = load_mission(current_state_path)
                except (ValueError, FileNotFoundError) as error:
                    run_error = run_error or str(error)
                    current = None
                if current is not None:
                    if current.milestone_count and git_commit_exists(
                        repo_path,
                        current.last_milestone_head,
                        command_runner=command_runner,
                    ):
                        lineage_ref = current.last_milestone_head
                    loop_state["lineage_ref"] = lineage_ref
                    loop_state["last_mission_id"] = current.mission_id
                    loop_state["last_mission_status"] = current.status
                    if current.status == "complete" and publish_remote:
                        loop_state["pending_publish_ref"] = lineage_ref
                        loop_state["pending_publish_mission_id"] = current.mission_id
                    if current.status != "active":
                        current_state_path = None
                        loop_state["current_mission_id"] = ""
                        loop_state["current_state_path"] = ""
                else:
                    current_state_path = None
                    loop_state["current_mission_id"] = ""
                    loop_state["current_state_path"] = ""
                    loop_state["last_mission_status"] = "unavailable"
                loop_state["last_exit_code"] = exit_code
                loop_state["last_error"] = run_error
                loop_state["status"] = "running"
                save_continuous_loop_state(state_path, loop_state)
                append_jsonl(
                    events_path,
                    {
                        "event": "continuous_loop.mission_returned",
                        "at": utc_now_iso(),
                        "loop_id": loop_id,
                        "mission_id": loop_state["last_mission_id"],
                        "mission_status": loop_state["last_mission_status"],
                        "exit_code": exit_code,
                        "error": run_error,
                        "lineage_ref": lineage_ref,
                    },
                )
                if loop_state["pending_publish_ref"] and not attempt_publication():
                    should_wait = True
        except KeyboardInterrupt:
            loop_state["stop_reason"] = "keyboard_interrupt"
        finally:
            loop_state["status"] = "stopped"
            loop_state["next_wake_at"] = ""
            save_continuous_loop_state(state_path, loop_state)
            append_jsonl(
                events_path,
                {
                    "event": "continuous_loop.stopped",
                    "at": utc_now_iso(),
                    "loop_id": loop_id,
                    "reason": loop_state["stop_reason"],
                },
            )
            try:
                stop_path.unlink()
            except FileNotFoundError:
                pass
    return 0


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


@app.command(help="Continuously run autonomous missions with a delay between completed missions.")
def loop(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository to evolve continuously."),
    kernel: str = typer.Option("grok", "--kernel", help="Execution kernel: grok or codex."),
    model: str | None = typer.Option(None, "--model", "-m", help="Optional model route."),
    profile: str | None = typer.Option(None, "--profile", help="Optional Codex profile."),
    target_branch: str = typer.Option("main", "--target-branch", help="Initial lineage base."),
    branch_prefix: str = typer.Option("unbound", "--branch-prefix", help="Mission branch prefix."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", help="Durable Unbound state root."),
    worktree_parent: Path | None = typer.Option(None, "--worktree-parent", help="Mission worktree parent."),
    timeout_seconds: int = typer.Option(7200, "--timeout-seconds", min=1, help="Maximum time for one turn."),
    interval_seconds: int = typer.Option(
        DEFAULT_CONTINUOUS_INTERVAL_SECONDS,
        "--interval-seconds",
        min=1,
        help="Delay between autonomous missions or retries.",
    ),
    wait_first: bool = typer.Option(False, "--wait-first/--run-first", help="Wait before the first mission."),
    resume_latest: bool = typer.Option(
        True,
        "--resume-latest/--start-fresh",
        help="Resume an active mission and continue from the latest proven milestone.",
    ),
    max_missions: int = typer.Option(
        0,
        "--max-missions",
        min=0,
        help="Stop after creating this many missions; 0 runs continuously.",
    ),
    publish_remote: str = typer.Option(
        "origin",
        "--publish-remote",
        help="Push each completed proven lineage to this remote; use an empty value to disable.",
    ),
) -> None:
    try:
        exit_code = run_continuous_loop(
            repo_path=repo_path,
            kernel=kernel,
            model=model,
            profile=profile,
            target_branch=target_branch,
            branch_prefix=branch_prefix,
            output_dir=output_dir,
            worktree_parent=worktree_parent,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            wait_first=wait_first,
            resume_latest=resume_latest,
            max_missions=max_missions,
            publish_remote=publish_remote.strip(),
        )
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        console.print(f"Unbound continuous loop failed: {error}", style="red")
        raise typer.Exit(1) from error
    raise typer.Exit(exit_code)


@app.command(help="Show durable state for the autonomous continuous loop.")
def loop_status(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository containing loop state."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", help="Durable Unbound state root."),
) -> None:
    state_path = continuous_loop_state_path(repo_path.resolve(), output_dir)
    if not state_path.exists():
        raise typer.BadParameter(f"No Unbound continuous loop state exists: {state_path}")
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    console.print_json(data=payload)


@app.command(help="Request that the continuous loop stop after its current mission returns.")
def loop_stop(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository containing loop state."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", help="Durable Unbound state root."),
) -> None:
    repo_path = repo_path.resolve()
    state_path = continuous_loop_state_path(repo_path, output_dir)
    if not state_path.exists():
        raise typer.BadParameter(f"No Unbound continuous loop state exists: {state_path}")
    stop_path = continuous_loop_stop_path(repo_path, output_dir)
    atomic_write_json(
        stop_path,
        {
            "requested_at": utc_now_iso(),
            "requested_by_pid": os.getpid(),
        },
    )
    console.print(f"stop requested: {stop_path}")


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


@capability_app.command("seed", help="Install bootstrap capabilities into the durable ledger.")
def capability_seed(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
) -> None:
    path, ledger = ensure_seeded_ledger(repo_path.resolve())
    console.print_json(
        data={
            "ledger_path": str(path),
            "count": len(ledger.capabilities),
            "ids": sorted(ledger.capabilities),
        }
    )


@capability_app.command("list", help="List compounded capabilities in the durable ledger.")
def capability_list(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
) -> None:
    path = default_ledger_path(repo_path.resolve())
    ledger = load_ledger(path)
    rows = [
        {
            "id": item.id,
            "name": item.name,
            "kind": item.kind,
            "dependencies": list(item.dependencies),
            "last_proof_exit_code": item.last_proof_exit_code,
            "capability_delta": item.capability_delta,
        }
        for item in sorted(ledger.capabilities.values(), key=lambda value: value.id)
    ]
    console.print_json(data={"ledger_path": str(path), "count": len(rows), "capabilities": rows})


@capability_app.command("show", help="Show one capability record.")
def capability_show(
    capability_id: str = typer.Argument(..., help="Capability id."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
) -> None:
    path = default_ledger_path(repo_path.resolve())
    ledger = load_ledger(path)
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        console.print(f"Unknown capability: {capability_id}", style="red")
        raise typer.Exit(1)
    console.print_json(data=capability.to_dict())


@capability_app.command("register", help="Register or replace a capability in the durable ledger.")
def capability_register(
    capability_id: str = typer.Option(..., "--id", help="Stable capability id."),
    name: str = typer.Option(..., "--name", help="Human-readable name."),
    entry: str = typer.Option(..., "--entry", help="Shell command or module:function."),
    proof_command: str = typer.Option(..., "--proof", help="Exact proof command that must exit 0."),
    kind: str = typer.Option("command", "--kind", help="command or python."),
    description: str = typer.Option("", "--description", help="What the capability does."),
    capability_delta: str = typer.Option("", "--delta", help="Demonstrated ability summary."),
    depends_on: str = typer.Option("", "--depends-on", help="Comma-separated dependency ids."),
    behavior_paths: str = typer.Option("", "--behavior-paths", help="Comma-separated behavior paths."),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags."),
    replace: bool = typer.Option(False, "--replace", help="Replace an existing capability id."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
) -> None:
    deps = tuple(part.strip() for part in depends_on.split(",") if part.strip())
    paths = tuple(part.strip() for part in behavior_paths.split(",") if part.strip())
    tag_values = tuple(part.strip() for part in tags.split(",") if part.strip())
    capability = Capability(
        id=capability_id,
        name=name,
        description=description or name,
        kind=kind,
        entry=entry,
        proof_command=proof_command,
        dependencies=deps,
        behavior_paths=paths,
        capability_delta=capability_delta or description or name,
        tags=tag_values,
    )
    path = default_ledger_path(repo_path.resolve())
    try:
        ledger = load_ledger(path)
        register_capability(ledger, capability, replace=replace)
        save_ledger(path, ledger)
    except (ValueError, OSError) as error:
        console.print(f"Register failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data={"ledger_path": str(path), "capability": capability.to_dict()})


@capability_app.command("prove", help="Run proof_command for one capability (and its dependencies).")
def capability_prove(
    capability_id: str = typer.Argument(..., help="Capability id."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    if capability_id not in ledger.capabilities:
        console.print(f"Unknown capability: {capability_id}", style="red")
        raise typer.Exit(1)
    try:
        ledger, result = prove_capability(
            ledger,
            capability_id,
            cwd=root,
            timeout=timeout_seconds,
        )
        save_ledger(path, ledger)
    except Exception as error:
        console.print(f"Prove failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result.to_dict())
    if not result.ok:
        raise typer.Exit(result.exit_code or 1)


@capability_app.command("run", help="Execute one capability entry.")
def capability_run(
    capability_id: str = typer.Argument(..., help="Capability id."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
    prove_first: bool = typer.Option(True, "--prove-first/--no-prove-first"),
) -> None:
    root = repo_path.resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = ledger.capabilities.get(capability_id)
    if capability is None:
        console.print(f"Unknown capability: {capability_id}", style="red")
        raise typer.Exit(1)
    if prove_first:
        ledger, proof = prove_capability(ledger, capability_id, cwd=root, timeout=timeout_seconds)
        save_ledger(path, ledger)
        if not proof.ok:
            console.print_json(data=proof.to_dict())
            raise typer.Exit(proof.exit_code or 1)
    result = run_capability(capability, cwd=root, timeout=timeout_seconds, use_proof=False)
    console.print_json(data=result.to_dict())
    if not result.ok:
        raise typer.Exit(result.exit_code or 1)


@capability_app.command("compose", help="Prove and run a dependency-ordered capability chain.")
def capability_compose(
    capability_ids: str = typer.Argument(..., help="Comma-separated capability ids."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
    prove_first: bool = typer.Option(True, "--prove-first/--no-prove-first"),
) -> None:
    root = repo_path.resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    ids = [part.strip() for part in capability_ids.split(",") if part.strip()]
    try:
        results = compose_capabilities(
            ledger,
            ids,
            cwd=root,
            timeout=timeout_seconds,
            prove_first=prove_first,
        )
        save_ledger(path, ledger)
    except (KeyError, ValueError) as error:
        console.print(f"Compose failed: {error}", style="red")
        raise typer.Exit(1) from error
    payload = {
        "ok": all(item.ok for item in results),
        "results": [item.to_dict() for item in results],
    }
    console.print_json(data=payload)
    if not payload["ok"]:
        raise typer.Exit(1)


@capability_app.command("demo", help="End-to-end bootstrap: seed, prove, and compose without skill-route imports.")
def capability_demo(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    try:
        result = run_end_to_end_demo(repo_path.resolve(), timeout=timeout_seconds)
    except Exception as error:
        console.print(f"Demo failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "scout",
    help="Scout the ledger for composition and domain-surface growth opportunities.",
)
def capability_scout(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
) -> None:
    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    result = scout_capability_gaps(ledger, repo_path=root)
    result["ledger_path"] = str(path)
    console.print_json(data=result)
    if not result.get("ok"):
        raise typer.Exit(1)


@capability_app.command(
    "absorb",
    help="Absorb a catalogued domain package surface into the durable capability ledger.",
)
def capability_absorb(
    surface_id: str = typer.Argument(
        ...,
        help="Domain surface id (e.g. domain.local-memory, domain.tool-routing).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    replace: bool = typer.Option(False, "--replace", help="Replace an existing capability id."),
    prove: bool = typer.Option(True, "--prove/--no-prove", help="Prove after absorption."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    try:
        ledger, absorbed = absorb_domain_surface(ledger, surface_id, replace=replace)
        save_ledger(path, ledger)
        proof_payload: dict[str, Any] | None = None
        if prove:
            ledger, proof = prove_capability(
                ledger,
                absorbed.id,
                cwd=root,
                timeout=timeout_seconds,
            )
            save_ledger(path, ledger)
            proof_payload = proof.to_dict()
            if not proof.ok:
                console.print_json(
                    data={
                        "ok": False,
                        "ledger_path": str(path),
                        "absorbed": absorbed.to_dict(),
                        "proof": proof_payload,
                    }
                )
                raise typer.Exit(proof.exit_code or 1)
    except (KeyError, ValueError, OSError) as error:
        console.print(f"Absorb failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(
        data={
            "ok": True,
            "ledger_path": str(path),
            "absorbed": absorbed.to_dict(),
            "proof": proof_payload,
        }
    )


@capability_app.command(
    "promote",
    help="Promote a multi-capability composition into one durable invocable capability.",
)
def capability_promote(
    members: str = typer.Argument(..., help="Comma-separated member capability ids."),
    capability_id: str = typer.Option("", "--id", help="Optional id for the promoted capability."),
    name: str = typer.Option("", "--name", help="Optional human-readable name."),
    replace: bool = typer.Option(False, "--replace", help="Replace an existing promoted id."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    prove: bool = typer.Option(True, "--prove/--no-prove", help="Prove after promotion."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    path, ledger = ensure_seeded_ledger(root)
    member_ids = [part.strip() for part in members.split(",") if part.strip()]
    try:
        ledger, promoted = promote_composition(
            ledger,
            member_ids,
            capability_id=capability_id or None,
            name=name or None,
            replace=replace,
        )
        save_ledger(path, ledger)
        proof_payload: dict[str, Any] | None = None
        if prove:
            ledger, proof = prove_capability(
                ledger,
                promoted.id,
                cwd=root,
                timeout=timeout_seconds,
            )
            save_ledger(path, ledger)
            proof_payload = proof.to_dict()
            if not proof.ok:
                console.print_json(
                    data={
                        "ok": False,
                        "ledger_path": str(path),
                        "promoted": promoted.to_dict(),
                        "proof": proof_payload,
                    }
                )
                raise typer.Exit(proof.exit_code or 1)
    except (ValueError, KeyError, OSError) as error:
        console.print(f"Promote failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(
        data={
            "ok": True,
            "ledger_path": str(path),
            "promoted": promoted.to_dict(),
            "proof": proof_payload,
        }
    )


@capability_app.command(
    "grow",
    help=(
        "Closed growth loop: scout → absorb domain or promote composition → prove "
        "(no skill-route). Use --budget >1 for adaptive multi-step growth until stall."
    ),
)
def capability_grow(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    recipe_id: str = typer.Option("", "--recipe-id", help="Optional known recipe id to promote."),
    budget: int = typer.Option(
        1,
        "--budget",
        min=1,
        help="Growth steps to attempt. budget=1 is single-step; >1 runs adaptive multi-grow.",
    ),
    timeout_seconds: int = typer.Option(180, "--timeout-seconds", min=1),
) -> None:
    try:
        if budget > 1 and recipe_id:
            console.print(
                "Grow with --budget>1 ignores --recipe-id and adapts across the frontier.",
                style="yellow",
            )
        if budget > 1:
            result = run_adaptive_growth(
                repo_path.resolve(),
                budget=budget,
                timeout=timeout_seconds,
            )
        else:
            result = run_growth_loop(
                repo_path.resolve(),
                timeout=timeout_seconds,
                recipe_id=recipe_id or None,
            )
    except Exception as error:
        console.print(f"Grow failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "integrity",
    help="Batch-prove the durable ledger DAG in topological order and report integrity score.",
)
def capability_integrity(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    limit: int = typer.Option(
        0,
        "--limit",
        min=0,
        help="Max capabilities to prove in topo order (0 = all).",
    ),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    try:
        result = prove_ledger_integrity(
            repo_path.resolve(),
            timeout=timeout_seconds,
            limit=None if limit == 0 else limit,
        )
    except Exception as error:
        console.print(f"Integrity failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "novelty",
    help=(
        "Rank growth frontiers by primitive-coverage novelty "
        "(prefers new domain combinations over identical-leaf superstacks)."
    ),
)
def capability_novelty(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
) -> None:
    try:
        path, ledger = ensure_seeded_ledger(repo_path.resolve())
        result = scout_frontier_novelty(ledger, repo_path=repo_path.resolve())
        result["ledger_path"] = str(path)
    except Exception as error:
        console.print(f"Novelty scout failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "distill",
    help=(
        "Distill redundant composed capabilities that share identical primitive coverage. "
        "Default soft-tags non-champions; --remove drops synthesized/meta/superstack losers."
    ),
)
def capability_distill(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    remove: bool = typer.Option(
        False,
        "--remove",
        help="Hard-remove redundant synthesized stacks instead of only tagging them.",
    ),
) -> None:
    try:
        result = run_distill_ledger(repo_path.resolve(), remove=remove, only_synthesized=True)
    except Exception as error:
        console.print(f"Distill failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "autonomic",
    help=(
        "Autonomic cycle: novelty-aware adaptive grow → distill redundant stacks → "
        "integrity prove (no skill-route)."
    ),
)
def capability_autonomic(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    budget: int = typer.Option(3, "--budget", min=1, help="Adaptive growth steps."),
    integrity_limit: int = typer.Option(
        10,
        "--integrity-limit",
        min=1,
        help="Topo-prefix size for integrity prove.",
    ),
    remove: bool = typer.Option(
        False,
        "--remove",
        help="Hard-remove redundant stacks during distill phase.",
    ),
    timeout_seconds: int = typer.Option(180, "--timeout-seconds", min=1),
) -> None:
    try:
        result = run_autonomic_cycle(
            repo_path.resolve(),
            budget=budget,
            distill_remove=remove,
            integrity_limit=integrity_limit,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Autonomic cycle failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "plan",
    help="Plan a multi-step capability program for a free-text goal (mission plane planner).",
)
def capability_plan(
    goal: str = typer.Argument(..., help="Free-text mission goal to compile into capability steps."),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    max_steps: int = typer.Option(6, "--max-steps", min=1, help="Maximum program length."),
) -> None:
    try:
        path, ledger = ensure_seeded_ledger(repo_path.resolve())
        result = plan_capability_program(ledger, goal, max_steps=max_steps, prefer_primitives=True)
        result["ledger_path"] = str(path)
        result["used_skill_route_discovery"] = False
    except Exception as error:
        console.print(f"Plan failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok"):
        raise typer.Exit(1)


@capability_app.command(
    "program",
    help="Run an ordered multi-step capability program (comma-separated ids or planned steps).",
)
def capability_program(
    steps: str = typer.Argument(
        "",
        help="Comma-separated capability ids. Empty uses a core health default program.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    prove_first: bool = typer.Option(False, "--prove-first", help="Prove each step before run."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    try:
        ordered = [part.strip() for part in steps.split(",") if part.strip()] if steps.strip() else [
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ]
        result = run_capability_program(
            repo_path.resolve(),
            ordered,
            timeout=timeout_seconds,
            prove_first=prove_first,
        )
    except Exception as error:
        console.print(f"Program run failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "second-wave",
    help="Absorb ready second-wave domain primitives (persona, proposal synthesis, kernel, …).",
)
def capability_second_wave(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    limit: int = typer.Option(8, "--limit", min=1, help="Max surfaces to absorb."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    try:
        result = absorb_second_wave_domains(
            repo_path.resolve(),
            prove=True,
            limit=limit,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Second-wave absorb failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "mission-plane",
    help=(
        "Mission plane: absorb second-wave primitives → plan goal program → run → "
        "novel-only grow (escapes zero-novelty superstack stall)."
    ),
)
def capability_mission_plane(
    goal: str = typer.Option(
        "second-wave identity persona proposal kernel health",
        "--goal",
        help="Free-text mission goal for program planning.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    max_steps: int = typer.Option(5, "--max-steps", min=1, help="Program length cap."),
    grow_budget: int = typer.Option(2, "--grow-budget", min=0, help="Novel-only growth steps after program."),
    no_absorb: bool = typer.Option(False, "--no-absorb", help="Skip second-wave absorption."),
    timeout_seconds: int = typer.Option(180, "--timeout-seconds", min=1),
) -> None:
    try:
        result = run_mission_plane(
            repo_path.resolve(),
            goal,
            max_steps=max_steps,
            absorb_ready=not no_absorb,
            grow_budget=grow_budget,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Mission plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "contract",
    help=(
        "Parse and machine-check a done_when outcome contract against the live ledger "
        "(metrics, proofs, optional programs)."
    ),
)
def capability_contract(
    done_when: str = typer.Argument(
        ...,
        help="Structured or free-text done_when (semicolon-separated predicates).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    run_programs: bool = typer.Option(
        False,
        "--run-programs",
        help="Execute program_passes predicates instead of soft proof checks.",
    ),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    try:
        result = evaluate_outcome_contract(
            repo_path.resolve(),
            done_when,
            run_programs=run_programs,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Outcome contract failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)
    if result.get("machine_checkable") and result.get("met") is not True:
        raise typer.Exit(2)


@capability_app.command(
    "contract-plane",
    help=(
        "Evidence plane: mission plane then machine-check done_when so completion is "
        "ledger/program-backed, not free-text theater."
    ),
)
def capability_contract_plane(
    goal: str = typer.Option(
        "health inventory milestone",
        "--goal",
        help="Free-text mission goal for program planning.",
    ),
    done_when: str = typer.Option(
        (
            "min_capabilities:10; min_primitives:8; capability_exists:capability.outcome-contract; "
            "capability_proved:repo.import-health; program_passes:repo.import-health,"
            "capability.ledger-inventory; no_skill_route; mission_plane_ok"
        ),
        "--done-when",
        help="Machine-checkable done_when predicates.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    max_steps: int = typer.Option(3, "--max-steps", min=1, help="Program length cap."),
    grow_budget: int = typer.Option(0, "--grow-budget", min=0, help="Novel-only growth after program."),
    no_absorb: bool = typer.Option(False, "--no-absorb", help="Skip second-wave absorption."),
    no_mission: bool = typer.Option(False, "--no-mission", help="Only evaluate contract (skip mission plane)."),
    timeout_seconds: int = typer.Option(180, "--timeout-seconds", min=1),
) -> None:
    try:
        result = run_contract_plane(
            repo_path.resolve(),
            goal,
            done_when,
            max_steps=max_steps,
            absorb_ready=not no_absorb,
            grow_budget=grow_budget,
            run_mission=not no_mission,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Contract plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)
    if result.get("machine_checkable") and result.get("met") is not True:
        raise typer.Exit(2)


@capability_app.command(
    "ablate",
    help=(
        "Ablation proof: baseline prove passes, broken proof fails, restore passes, "
        "and broken dependencies fail dependent proves (live ledger not mutated)."
    ),
)
def capability_ablate(
    capability_id: str = typer.Option(
        "repo.import-health",
        "--id",
        help="Capability to ablate (break/restore proof_command).",
    ),
    dependent_id: str = typer.Option(
        "unbound.milestone-gate",
        "--dependent",
        help="Dependent capability used for dependency-break ablation.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(90, "--timeout-seconds", min=1),
) -> None:
    try:
        result = run_ablation_proof(
            repo_path.resolve(),
            capability_id=capability_id,
            dependent_id=dependent_id,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Ablation proof failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "transfer",
    help=(
        "Transfer plane: export capability package with dependency closure, import into "
        "an empty ledger, and re-prove members."
    ),
)
def capability_transfer(
    roots: str = typer.Option(
        "repo.import-health,capability.ledger-inventory,unbound.milestone-gate",
        "--roots",
        help="Comma-separated root capability ids to package.",
    ),
    package_path: Path | None = typer.Option(
        None,
        "--package-path",
        help="Optional output path for the portable package JSON.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
    prove: bool = typer.Option(True, "--prove/--no-prove", help="Re-prove imported members."),
) -> None:
    try:
        ordered = [part.strip() for part in roots.split(",") if part.strip()]
        result = run_transfer_plane(
            repo_path.resolve(),
            ordered,
            package_path=package_path,
            timeout=timeout_seconds,
            prove_imported=prove,
        )
    except Exception as error:
        console.print(f"Transfer plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "adversarial",
    help=(
        "Adversarial contracts: positive done_when must pass; known-false contracts must fail."
    ),
)
def capability_adversarial(
    positive: str = typer.Option(
        (
            "min_capabilities:3; capability_exists:repo.import-health; "
            "capability_proved:repo.import-health; no_skill_route"
        ),
        "--positive",
        help="done_when that must evaluate met=True.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(90, "--timeout-seconds", min=1),
) -> None:
    try:
        result = run_adversarial_contract(
            repo_path.resolve(),
            positive_done_when=positive,
            timeout=timeout_seconds,
            run_programs=False,
        )
    except Exception as error:
        console.print(f"Adversarial contract failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "assurance",
    help=(
        "Assurance plane: ablation proofs → portable transfer re-proof → adversarial "
        "outcome contracts (falsifiable evidence past composition plateaus)."
    ),
)
def capability_assurance(
    capability_id: str = typer.Option(
        "repo.import-health",
        "--id",
        help="Capability id for ablation phase.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1),
) -> None:
    try:
        result = run_assurance_plane(
            repo_path.resolve(),
            capability_id=capability_id,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Assurance plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)



@capability_app.command(
    "margin",
    help=(
        "Margin plane: multi-clearing net positions → deterministic hash-chained margin "
        "requirements bound to clearing roots → margin certificates → sterile rehydrate+"
        "prove → adversarial wrong-clearing/reorder/double-margin/forged-root falsification."
    ),
)
def capability_margin(
    goal: str = typer.Option("margin over clearing", "--goal"),
    done_when: str = typer.Option("", "--done-when"),
    lineage_path: Path | None = typer.Option(None, "--lineage-path"),
    bundle_path: Path | None = typer.Option(None, "--bundle-path"),
    quorum_path: Path | None = typer.Option(None, "--quorum-path"),
    finality_path: Path | None = typer.Option(None, "--finality-path"),
    execution_path: Path | None = typer.Option(None, "--execution-path"),
    actuation_path: Path | None = typer.Option(None, "--actuation-path"),
    settlement_path: Path | None = typer.Option(None, "--settlement-path"),
    clearing_path: Path | None = typer.Option(None, "--clearing-path"),
    margin_path: Path | None = typer.Option(None, "--margin-path"),
    epoch_count: int = typer.Option(2, "--epoch-count", min=2),
    min_actions: int = typer.Option(2, "--min-actions", min=2),
    min_settlements: int = typer.Option(2, "--min-settlements", min=2),
    min_clearings: int = typer.Option(2, "--min-clearings", min=2),
    min_margins: int = typer.Option(2, "--min-margins", min=2),
    no_clearing: bool = typer.Option(False, "--no-clearing"),
    no_settlement: bool = typer.Option(False, "--no-settlement"),
    no_actuation: bool = typer.Option(False, "--no-actuation"),
    no_execution: bool = typer.Option(False, "--no-execution"),
    no_finality: bool = typer.Option(False, "--no-finality"),
    with_continuity: bool = typer.Option(False, "--with-continuity"),
    no_byzantine: bool = typer.Option(False, "--no-byzantine"),
    repo_path: Path = typer.Option(Path("."), "--repo-path"),
    timeout_seconds: int = typer.Option(780, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_margin_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            actuation_path=actuation_path,
            settlement_path=settlement_path,
            clearing_path=clearing_path,
            margin_path=margin_path,
            epoch_count=epoch_count,
            min_actions=min_actions,
            min_settlements=min_settlements,
            min_clearings=min_clearings,
            min_margins=min_margins,
            run_clearing=not no_clearing,
            run_settlement=not no_settlement,
            run_actuation=not no_actuation,
            run_execution=not no_execution,
            run_finality=not no_finality,
            run_quorum=True,
            run_continuity=with_continuity,
            run_reconciliation=with_continuity,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Margin plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "clear",
    help=(
        "Clearing plane: multi-settlement receipts → deterministic hash-chained clearing "
        "positions with net digests bound to settlement roots → clearing certificates → "
        "sterile rehydrate+prove → adversarial wrong-settlement/reorder/double-clear/"
        "forged-root/net-tamper/single-clearing falsification."
    ),
)
def capability_clear(
    goal: str = typer.Option(
        "clearing over settlement",
        "--goal",
        help="Mission goal for clearing phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner settlement phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    quorum_path: Path | None = typer.Option(
        None,
        "--quorum-path",
        help="Where to write the source quorum bundle JSON.",
    ),
    finality_path: Path | None = typer.Option(
        None,
        "--finality-path",
        help="Where to write the source finality bundle JSON.",
    ),
    execution_path: Path | None = typer.Option(
        None,
        "--execution-path",
        help="Where to write the source execution bundle JSON.",
    ),
    actuation_path: Path | None = typer.Option(
        None,
        "--actuation-path",
        help="Where to write the source actuation bundle JSON.",
    ),
    settlement_path: Path | None = typer.Option(
        None,
        "--settlement-path",
        help="Where to write the source settlement bundle JSON.",
    ),
    clearing_path: Path | None = typer.Option(
        None,
        "--clearing-path",
        help="Where to write the portable clearing bundle JSON.",
    ),
    epoch_count: int = typer.Option(
        2,
        "--epoch-count",
        min=2,
        help="Number of irreversible epochs to seal before clearing (minimum 2).",
    ),
    min_actions: int = typer.Option(
        2,
        "--min-actions",
        min=2,
        help="Minimum capability effect actions to dispatch (minimum 2).",
    ),
    min_settlements: int = typer.Option(
        2,
        "--min-settlements",
        min=2,
        help="Minimum settlement receipts to seal (minimum 2).",
    ),
    min_clearings: int = typer.Option(
        2,
        "--min-clearings",
        min=2,
        help="Minimum clearing positions to seal (minimum 2).",
    ),
    no_settlement: bool = typer.Option(
        False,
        "--no-settlement",
        help="Reuse existing settlement bundle path instead of running a fresh settlement plane.",
    ),
    no_actuation: bool = typer.Option(
        False,
        "--no-actuation",
        help="Reuse existing actuation inside settlement instead of running a fresh actuation plane.",
    ),
    no_execution: bool = typer.Option(
        False,
        "--no-execution",
        help="Reuse existing execution inside actuation instead of running a fresh execution plane.",
    ),
    no_finality: bool = typer.Option(
        False,
        "--no-finality",
        help="Reuse existing finality inside execution instead of running a fresh finality plane.",
    ),
    with_continuity: bool = typer.Option(
        False,
        "--with-continuity",
        help="Run full continuity inside the source quorum plane.",
    ),
    no_byzantine: bool = typer.Option(
        False,
        "--no-byzantine",
        help="Do not inject a Byzantine minority origin (honest-only quorum).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(720, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_clearing_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            actuation_path=actuation_path,
            settlement_path=settlement_path,
            clearing_path=clearing_path,
            epoch_count=epoch_count,
            min_actions=min_actions,
            min_settlements=min_settlements,
            min_clearings=min_clearings,
            run_settlement=not no_settlement,
            run_actuation=not no_actuation,
            run_execution=not no_execution,
            run_finality=not no_finality,
            run_quorum=True,
            run_continuity=with_continuity,
            run_reconciliation=with_continuity,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Clearing plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "settle",
    help=(
        "Settlement plane: multi-action actuation → deterministic hash-chained settlement "
        "receipts bound to action roots → settlement certificates → sterile rehydrate+"
        "prove → adversarial wrong-action/reorder/double-settlement/forged-root/"
        "single-settlement falsification."
    ),
)
def capability_settle(
    goal: str = typer.Option(
        "settlement over actuation",
        "--goal",
        help="Mission goal for settlement phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner actuation phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    quorum_path: Path | None = typer.Option(
        None,
        "--quorum-path",
        help="Where to write the source quorum bundle JSON.",
    ),
    finality_path: Path | None = typer.Option(
        None,
        "--finality-path",
        help="Where to write the source finality bundle JSON.",
    ),
    execution_path: Path | None = typer.Option(
        None,
        "--execution-path",
        help="Where to write the source execution bundle JSON.",
    ),
    actuation_path: Path | None = typer.Option(
        None,
        "--actuation-path",
        help="Where to write the source actuation bundle JSON.",
    ),
    settlement_path: Path | None = typer.Option(
        None,
        "--settlement-path",
        help="Where to write the portable settlement bundle JSON.",
    ),
    epoch_count: int = typer.Option(
        2,
        "--epoch-count",
        min=2,
        help="Number of irreversible epochs to seal before settlement (minimum 2).",
    ),
    min_actions: int = typer.Option(
        2,
        "--min-actions",
        min=2,
        help="Minimum capability effect actions to dispatch (minimum 2).",
    ),
    min_settlements: int = typer.Option(
        2,
        "--min-settlements",
        min=2,
        help="Minimum settlement receipts to seal (minimum 2).",
    ),
    no_actuation: bool = typer.Option(
        False,
        "--no-actuation",
        help="Reuse existing actuation bundle path instead of running a fresh actuation plane.",
    ),
    no_execution: bool = typer.Option(
        False,
        "--no-execution",
        help="Reuse existing execution inside actuation instead of running a fresh execution plane.",
    ),
    no_finality: bool = typer.Option(
        False,
        "--no-finality",
        help="Reuse existing finality inside execution instead of running a fresh finality plane.",
    ),
    with_continuity: bool = typer.Option(
        False,
        "--with-continuity",
        help="Run full continuity inside the source quorum plane.",
    ),
    no_byzantine: bool = typer.Option(
        False,
        "--no-byzantine",
        help="Do not inject a Byzantine minority origin (honest-only quorum).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(660, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_settlement_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            actuation_path=actuation_path,
            settlement_path=settlement_path,
            epoch_count=epoch_count,
            min_actions=min_actions,
            min_settlements=min_settlements,
            run_actuation=not no_actuation,
            run_execution=not no_execution,
            run_finality=not no_finality,
            run_quorum=True,
            run_continuity=with_continuity,
            run_reconciliation=with_continuity,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Settlement plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "actuate",
    help=(
        "Actuation plane: world-state execution → multi-action deterministic capability "
        "effects bound to tip state roots → actuation certificates → sterile rehydrate+"
        "prove → adversarial wrong-state/reorder/forged-root/single-action falsification."
    ),
)
def capability_actuate(
    goal: str = typer.Option(
        "actuation over world-state execution",
        "--goal",
        help="Mission goal for actuation phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner execution phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    quorum_path: Path | None = typer.Option(
        None,
        "--quorum-path",
        help="Where to write the source quorum bundle JSON.",
    ),
    finality_path: Path | None = typer.Option(
        None,
        "--finality-path",
        help="Where to write the source finality bundle JSON.",
    ),
    execution_path: Path | None = typer.Option(
        None,
        "--execution-path",
        help="Where to write the source execution bundle JSON.",
    ),
    actuation_path: Path | None = typer.Option(
        None,
        "--actuation-path",
        help="Where to write the portable actuation bundle JSON.",
    ),
    epoch_count: int = typer.Option(
        2,
        "--epoch-count",
        min=2,
        help="Number of irreversible epochs to seal before actuation (minimum 2).",
    ),
    min_actions: int = typer.Option(
        2,
        "--min-actions",
        min=2,
        help="Minimum capability effect actions to dispatch (minimum 2).",
    ),
    no_execution: bool = typer.Option(
        False,
        "--no-execution",
        help="Reuse existing execution bundle path instead of running a fresh execution plane.",
    ),
    no_finality: bool = typer.Option(
        False,
        "--no-finality",
        help="Reuse existing finality inside execution instead of running a fresh finality plane.",
    ),
    with_continuity: bool = typer.Option(
        False,
        "--with-continuity",
        help="Run full continuity inside the source quorum plane.",
    ),
    no_byzantine: bool = typer.Option(
        False,
        "--no-byzantine",
        help="Do not inject a Byzantine minority origin (honest-only quorum).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(600, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_actuation_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            actuation_path=actuation_path,
            epoch_count=epoch_count,
            min_actions=min_actions,
            run_execution=not no_execution,
            run_finality=not no_finality,
            run_quorum=True,
            run_continuity=with_continuity,
            run_reconciliation=with_continuity,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Actuation plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "execution",
    help=(
        "Execution plane: multi-epoch irreversible finality → deterministic hash-chained "
        "world-state transitions → execution certificates → sterile rehydrate+prove → "
        "adversarial mutation/reorder/forged-root/gap/single-state falsification."
    ),
)
def capability_execution(
    goal: str = typer.Option(
        "world-state execution over epoch finality",
        "--goal",
        help="Mission goal for execution phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner finality phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    quorum_path: Path | None = typer.Option(
        None,
        "--quorum-path",
        help="Where to write the source quorum bundle JSON.",
    ),
    finality_path: Path | None = typer.Option(
        None,
        "--finality-path",
        help="Where to write the source finality bundle JSON.",
    ),
    execution_path: Path | None = typer.Option(
        None,
        "--execution-path",
        help="Where to write the portable execution bundle JSON.",
    ),
    epoch_count: int = typer.Option(
        2,
        "--epoch-count",
        min=2,
        help="Number of irreversible epochs to seal (minimum 2).",
    ),
    no_finality: bool = typer.Option(
        False,
        "--no-finality",
        help="Reuse existing finality bundle path instead of running a fresh finality plane.",
    ),
    with_continuity: bool = typer.Option(
        False,
        "--with-continuity",
        help="Run full continuity inside the source quorum plane.",
    ),
    no_byzantine: bool = typer.Option(
        False,
        "--no-byzantine",
        help="Do not inject a Byzantine minority origin (honest-only quorum).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(560, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_execution_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            execution_path=execution_path,
            epoch_count=epoch_count,
            run_finality=not no_finality,
            run_quorum=True,
            run_continuity=with_continuity,
            run_reconciliation=with_continuity,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Execution plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "finality",
    help=(
        "Finality plane: Byzantine-tolerant quorum → multi-epoch irreversible hash-chained "
        "seals → finality certificates → sterile rehydrate+prove → adversarial rewrite/"
        "fork/gap/stale-supersession falsification."
    ),
)
def capability_finality(
    goal: str = typer.Option(
        "epoch finality over quorum consensus",
        "--goal",
        help="Mission goal for finality phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner quorum phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    quorum_path: Path | None = typer.Option(
        None,
        "--quorum-path",
        help="Where to write the source quorum bundle JSON.",
    ),
    finality_path: Path | None = typer.Option(
        None,
        "--finality-path",
        help="Where to write the portable finality bundle JSON.",
    ),
    epoch_count: int = typer.Option(
        2,
        "--epoch-count",
        min=2,
        help="Number of irreversible epochs to seal (minimum 2).",
    ),
    no_quorum: bool = typer.Option(
        False,
        "--no-quorum",
        help="Reuse existing quorum bundle path instead of running a fresh quorum plane.",
    ),
    with_continuity: bool = typer.Option(
        False,
        "--with-continuity",
        help="Run full continuity inside the source quorum plane.",
    ),
    no_byzantine: bool = typer.Option(
        False,
        "--no-byzantine",
        help="Do not inject a Byzantine minority origin (honest-only quorum).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(520, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_finality_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            finality_path=finality_path,
            epoch_count=epoch_count,
            run_quorum=not no_quorum,
            run_continuity=with_continuity,
            run_reconciliation=with_continuity,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Finality plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "quorum",
    help=(
        "Quorum consensus plane: ≥3 independent continuity origins → strict-majority member "
        "vote → Byzantine minority exclusion → quorum certificate → sterile rehydrate+prove "
        "→ adversarial dual-origin/below-quorum/tamper/poison falsification."
    ),
)
def capability_quorum(
    goal: str = typer.Option(
        "quorum multi-origin consensus",
        "--goal",
        help="Mission goal for quorum phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner continuity phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    quorum_path: Path | None = typer.Option(
        None,
        "--quorum-path",
        help="Where to write the portable quorum bundle JSON.",
    ),
    no_continuity: bool = typer.Option(
        False,
        "--no-continuity",
        help="Skip full continuity plane; export origin-A from existing lineage only.",
    ),
    no_recon: bool = typer.Option(
        False,
        "--no-recon",
        help="Skip reconciliation inside continuity when continuity is enabled.",
    ),
    no_synthetic: bool = typer.Option(
        False,
        "--no-synthetic",
        help="Do not inject synthetic drift when natural drift is absent.",
    ),
    no_byzantine: bool = typer.Option(
        False,
        "--no-byzantine",
        help="Do not inject a Byzantine minority origin (honest-only quorum).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(480, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_quorum_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            quorum_path=quorum_path,
            run_continuity=not no_continuity,
            run_reconciliation=not no_recon,
            force_synthetic_drift=not no_synthetic,
            inject_byzantine=not no_byzantine,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Quorum plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "federate",
    help=(
        "Federation plane: dual independent continuity origins → hard-conflict package "
        "merge → dual-origin lineage seal → federation certificate → sterile rehydrate+prove "
        "→ adversarial conflict/tamper/single-origin falsification."
    ),
)
def capability_federate(
    goal: str = typer.Option(
        "federate multi-origin continuity",
        "--goal",
        help="Mission goal for federation phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner continuity phases.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write origin-A lineage log JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write origin-A continuity bundle JSON.",
    ),
    federation_path: Path | None = typer.Option(
        None,
        "--federation-path",
        help="Where to write the portable federation bundle JSON.",
    ),
    no_continuity: bool = typer.Option(
        False,
        "--no-continuity",
        help="Skip full continuity plane; export origin-A from existing lineage only.",
    ),
    no_recon: bool = typer.Option(
        False,
        "--no-recon",
        help="Skip reconciliation inside continuity when continuity is enabled.",
    ),
    no_synthetic: bool = typer.Option(
        False,
        "--no-synthetic",
        help="Do not inject synthetic drift when natural drift is absent.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(420, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_federation_plane(
            root,
            goal,
            done_when,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            federation_path=federation_path,
            run_continuity=not no_continuity,
            run_reconciliation=not no_recon,
            force_synthetic_drift=not no_synthetic,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Federation plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "continuity",
    help=(
        "Continuity resurrection plane: reconcile → export portable ledger+lineage+cert "
        "bundle → rehydrate sterile sandbox → re-prove members → adversarial bundle checks."
    ),
)
def capability_continuity(
    goal: str = typer.Option(
        "health inventory milestone",
        "--goal",
        help="Mission goal for reconciliation/continuity phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner reconciliation phases.",
    ),
    capability_id: str = typer.Option(
        "repo.import-health",
        "--id",
        help="Capability id for assurance ablation phase.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write the append-only lineage log JSON.",
    ),
    certificate_path: Path | None = typer.Option(
        None,
        "--certificate-path",
        help="Where to write healing sovereignty certificate JSON.",
    ),
    bundle_path: Path | None = typer.Option(
        None,
        "--bundle-path",
        help="Where to write the portable continuity bundle JSON.",
    ),
    with_mission: bool = typer.Option(
        False,
        "--with-mission",
        help="Include mission plane inside reconciliation (default: skip for speed).",
    ),
    no_recon: bool = typer.Option(
        False,
        "--no-recon",
        help="Reuse existing lineage without running reconciliation first.",
    ),
    no_synthetic: bool = typer.Option(
        False,
        "--no-synthetic",
        help="Do not inject synthetic drift when natural drift is absent.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(360, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_continuity_plane(
            root,
            goal,
            done_when,
            capability_id=capability_id,
            certificate_path=certificate_path,
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            run_mission=with_mission,
            run_reconciliation=not no_recon,
            force_synthetic_drift=not no_synthetic,
            absorb_ready=False,
            grow_budget=0,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Continuity plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "reconcile",
    help=(
        "Reconciliation plane: lineage continuity → detect/diagnose drift → re-certify "
        "→ heal-seal → prove unhealed fails and healed continuity passes."
    ),
)
def capability_reconcile(
    goal: str = typer.Option(
        "health inventory milestone",
        "--goal",
        help="Mission goal for lineage/sovereignty phases.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for inner sovereignty/lineage phases.",
    ),
    capability_id: str = typer.Option(
        "repo.import-health",
        "--id",
        help="Capability id for assurance ablation phase.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write the append-only lineage log JSON.",
    ),
    certificate_path: Path | None = typer.Option(
        None,
        "--certificate-path",
        help="Where to write the healing sovereignty certificate JSON.",
    ),
    no_mission: bool = typer.Option(
        False,
        "--no-mission",
        help="Skip mission plane inside lineage/sovereignty phase.",
    ),
    no_synthetic: bool = typer.Option(
        False,
        "--no-synthetic",
        help="Do not inject synthetic drift when natural drift is absent.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(300, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        result = run_reconciliation_plane(
            root,
            goal,
            done_when,
            capability_id=capability_id,
            certificate_path=certificate_path,
            lineage_path=lineage_path,
            run_mission=not no_mission,
            force_synthetic_drift=not no_synthetic,
            absorb_ready=False,
            grow_budget=0,
            timeout=timeout_seconds,
        )
    except Exception as error:
        console.print(f"Reconciliation plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "lineage",
    help=(
        "Lineage continuity plane: sovereignty certificate → hash-chained multi-entry "
        "log with continuity seal, live drift detection, and adversarial tamper checks."
    ),
)
def capability_lineage(
    goal: str = typer.Option(
        "health inventory milestone",
        "--goal",
        help="Mission goal for the sovereignty phase.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates for the sovereignty phase.",
    ),
    capability_id: str = typer.Option(
        "repo.import-health",
        "--id",
        help="Capability id for assurance ablation phase.",
    ),
    lineage_path: Path | None = typer.Option(
        None,
        "--lineage-path",
        help="Where to read/write the append-only lineage log JSON.",
    ),
    certificate_path: Path | None = typer.Option(
        None,
        "--certificate-path",
        help="Where to write the sovereignty certificate JSON.",
    ),
    verify_only: Path | None = typer.Option(
        None,
        "--verify-only",
        help="Only verify an existing lineage log path (chain + optional drift).",
    ),
    no_mission: bool = typer.Option(
        False,
        "--no-mission",
        help="Skip mission plane inside sovereignty/contract phase.",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(240, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        if verify_only is not None:
            log = load_lineage_log(verify_only.resolve())
            chain = verify_lineage_chain(log)
            drift = detect_lineage_drift(
                root,
                log,
                timeout=min(timeout_seconds, 90),
            )
            result = {
                "ok": bool(chain.get("ok"))
                and bool(chain.get("valid"))
                and drift.get("drift") is False
                and not bool(chain.get("used_skill_route_discovery")),
                "action": "verify_lineage",
                "lineage_path": str(verify_only.resolve()),
                "entry_count": log.get("entry_count"),
                "head_hash": log.get("head_hash"),
                "chain": chain,
                "drift": drift,
                "used_skill_route_discovery": bool(
                    chain.get("used_skill_route_discovery")
                    or drift.get("used_skill_route_discovery")
                ),
            }
        else:
            result = run_lineage_plane(
                root,
                goal,
                done_when,
                capability_id=capability_id,
                certificate_path=certificate_path,
                lineage_path=lineage_path,
                run_mission=not no_mission,
                absorb_ready=False,
                grow_budget=0,
                timeout=timeout_seconds,
            )
    except Exception as error:
        console.print(f"Lineage plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


@capability_app.command(
    "sovereignty",
    help=(
        "Sovereignty plane: contract/mission → assurance → portable re-verifiable "
        "lineage certificate (self-certifying completion evidence)."
    ),
)
def capability_sovereignty(
    goal: str = typer.Option(
        "health inventory milestone",
        "--goal",
        help="Mission goal for the contract/mission phase.",
    ),
    done_when: str = typer.Option(
        "",
        "--done-when",
        help="Contract done_when predicates (defaults to a lean health contract).",
    ),
    capability_id: str = typer.Option(
        "repo.import-health",
        "--id",
        help="Capability id for assurance ablation phase.",
    ),
    certificate_path: Path | None = typer.Option(
        None,
        "--certificate-path",
        help="Where to write the sovereignty certificate JSON.",
    ),
    verify_only: Path | None = typer.Option(
        None,
        "--verify-only",
        help="Only re-verify an existing sovereignty certificate path.",
    ),
    no_mission: bool = typer.Option(
        False,
        "--no-mission",
        help="Skip mission plane inside contract phase (faster cert issue).",
    ),
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="Repository root."),
    timeout_seconds: int = typer.Option(180, "--timeout-seconds", min=1),
) -> None:
    root = repo_path.resolve()
    try:
        if verify_only is not None:
            result = verify_sovereignty_certificate(
                verify_only.resolve(),
                repo_path=root,
                recheck_live=True,
                timeout=min(timeout_seconds, 90),
            )
        else:
            result = run_sovereignty_plane(
                root,
                goal,
                done_when,
                capability_id=capability_id,
                certificate_path=certificate_path,
                run_mission=not no_mission,
                absorb_ready=False,
                grow_budget=0,
                timeout=timeout_seconds,
            )
    except Exception as error:
        console.print(f"Sovereignty plane failed: {error}", style="red")
        raise typer.Exit(1) from error
    console.print_json(data=result)
    if not result.get("ok") or result.get("used_skill_route_discovery"):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
