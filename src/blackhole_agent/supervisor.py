"""Native wake supervisor for blackhole-agent.

The supervisor stays outside the mutation kernel. It wakes on a fixed cadence,
creates an isolated candidate worktree, launches one fresh blackhole child
process, records the run, promotes verified candidate commits, and then sleeps
until the next cadence boundary. Each child process reloads the current checkout,
so self-evolution can affect later wakes without embedding a long-lived Codex
loop inside the controller.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from blackhole_agent.kernels.codex_cli import CodexCliConfig, build_codex_provider_preflight
from blackhole_agent.proposal_synthesis import DEFAULT_PROPOSAL_MODE, PROPOSAL_MODES
from blackhole_agent.self_model import DEFAULT_SELF_MODEL_PATH
from blackhole_agent.tool_routing import (
    ToolDescriptor,
    build_tool_routing_preflight,
    local_memory_tool_descriptor,
)

app = typer.Typer(rich_markup_mode="rich", add_completion=False)
console = Console(highlight=False)

SUPPORTED_EVOLUTION_MODES = {"digest", "plan", "codex"}
DEFAULT_OUTPUT_DIR = Path(".blackhole-agent/supervisor")
DEFAULT_HEALTH_COMMANDS: tuple[str, ...] = ("uv run pytest", "uv run ruff check .")
DEFAULT_RESTART_EXIT_CODE = 75
LATEST_ACTIVATION_FILENAME = "latest-activation.json"
VERSION_PREVIEW_MARKERS = ("dev", "alpha", "a", "beta", "b", "rc", "pre", "preview", "nightly", "snapshot")
DEFAULT_SUPERVISOR_EXTRA_INSTRUCTION = (
    "Native supervisor note: this wake is one pass in an autonomous scheduled loop. "
    "Prefer coherent local improvements and size them by evidence, benefit, rollback coverage, and validation coverage rather than by smallness. "
    "Use configured capabilities when they are needed and locally verifiable; allow broad local change sets when they remain auditable and keep only "
    "offensive behavior, abuse, unauthorized access, and privacy leakage review-only. "
    "When validation succeeds, leave the repository in a consistent state; the supervisor handles configured "
    "commit, promotion, push, and restart handoff."
)


@dataclass(frozen=True)
class SupervisorConfig:
    """Configuration for the native wake loop."""

    repo_path: Path
    output_dir: Path = DEFAULT_OUTPUT_DIR
    growth_output_dir: Path | None = None
    worktree_parent_dir: Path | None = None
    interval_seconds: int = 3600
    max_passes: int = 0
    run_immediately: bool = True
    exit_on_failure: bool = False
    pass_timeout_seconds: int = 5400
    evolution_mode: str = "codex"
    repos: str = ""
    trend_query: str = "agent language:Python"
    trend_window_days: int = 14
    trend_min_stars: int = 5
    trend_limit: int = 5
    trend_sort: str = "stars"
    trend_order: str = "desc"
    include_forks: bool = False
    token_env: str = "GITHUB_TOKEN"
    require_token_env: bool = False
    topics: str = ""
    lookback_hours: int = 24
    max_events_per_repo: int = 100
    proposal_mode: str = DEFAULT_PROPOSAL_MODE
    proposal_model: str | None = None
    proposal_timeout_seconds: int = 180
    branch_prefix: str = "codex/blackhole-evolve"
    self_model_path: Path = DEFAULT_SELF_MODEL_PATH
    force_evolve: bool = True
    allow_dirty: bool = False
    model: str | None = None
    profile: str | None = None
    require_codex_route: bool = True
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    ignore_user_config: bool = True
    bypass_approvals_and_sandbox: bool = False
    codex_timeout_seconds: int = 3600
    extra_instruction: str = ""
    commit_successful_changes: bool = True
    use_candidate_worktree: bool = True
    cleanup_candidate_worktree: bool = True
    target_branch: str = "main"
    remote_name: str = "origin"
    promote_successful_changes: bool = True
    push_promotions: bool = True
    require_rollback_artifact: bool = True
    health_commands: tuple[str, ...] = DEFAULT_HEALTH_COMMANDS
    health_timeout_seconds: int = 900
    startup_health_check: bool = True
    rollback_on_startup_health_failure: bool = True
    exit_after_promotion: bool = False
    restart_exit_code: int = DEFAULT_RESTART_EXIT_CODE
    required_tool_names: tuple[str, ...] = ()

    @property
    def resolved_output_dir(self) -> Path:
        return resolve_path(self.repo_path, self.output_dir)

    @property
    def resolved_growth_output_dir(self) -> Path:
        if self.growth_output_dir is not None:
            return resolve_path(self.repo_path, self.growth_output_dir)
        return self.resolved_output_dir / "growth"

    @property
    def resolved_worktree_parent_dir(self) -> Path:
        if self.worktree_parent_dir is not None:
            return resolve_path(self.repo_path, self.worktree_parent_dir)
        return self.repo_path.parent / f".{self.repo_path.name}-blackhole-worktrees"


@dataclass(frozen=True)
class CommitResult:
    """Result of the supervisor's optional local commit step."""

    attempted: bool
    committed: bool
    returncode: int
    status_before: str
    commit_sha: str
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class WorktreeResult:
    """Result of preparing and cleaning a candidate worktree."""

    attempted: bool
    created: bool
    path: str
    create_returncode: int
    remove_attempted: bool
    removed: bool
    remove_returncode: int
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class HealthCheckResult:
    """Result of one health command."""

    command: list[str]
    cwd: str
    returncode: int
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class PromotionResult:
    """Result of promoting a candidate branch into the target branch."""

    attempted: bool
    promoted: bool
    pushed: bool
    returncode: int
    candidate_branch: str
    candidate_head: str
    target_branch: str
    target_before: str
    target_after: str
    rollback_artifact_path: str
    rollback_artifact_exists: bool
    health_checks: list[HealthCheckResult]
    post_merge_health_checks: list[HealthCheckResult]
    rollback_attempted: bool
    rollback_succeeded: bool
    restart_requested: bool
    restart_request_path: str
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class StartupHealthRecord:
    """Health check record written when a supervisor process starts."""

    check_id: str
    started_at: str
    finished_at: str
    health_checks: list[HealthCheckResult]
    returncode: int
    rollback_attempted: bool
    rollback_succeeded: bool
    rollback_target: str
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class SupervisorRunnerStatus:
    """Derived liveness for the one-shot child runner behind a supervisor."""

    schema_version: int
    status: str
    controller_visible_status: str
    user_visible_message: str
    reason: str
    heartbeat_path: str
    heartbeat_present: bool
    last_pass_id: str
    last_finished_at: str
    last_effective_returncode: int | None
    seconds_since_last_finish: float | None
    next_wake_due_at: str
    active_child_count: int
    child_status_counts: dict[str, int]
    active_child_sessions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupervisorPassRecord:
    """Durable record for one wake pass."""

    pass_id: str
    started_at: str
    finished_at: str
    start_branch: str
    start_head: str
    finish_branch: str
    finish_head: str
    command: list[str]
    cwd: str
    returncode: int
    timed_out: bool
    elapsed_seconds: float
    stdout_tail: str
    stderr_tail: str
    worktree_result: WorktreeResult | None
    commit_result: CommitResult | None
    promotion_result: PromotionResult | None


def build_wake_command(config: SupervisorConfig, *, repo_path: Path | None = None) -> list[str]:
    """Build the one-shot child command for a supervisor wake."""

    child_repo_path = repo_path or config.repo_path
    command = [
        sys.executable,
        "-m",
        "blackhole_agent.github_growth",
        "--output-dir",
        str(config.resolved_growth_output_dir),
        "--token-env",
        config.token_env,
        "--lookback-hours",
        str(config.lookback_hours),
        "--max-events-per-repo",
        str(config.max_events_per_repo),
        "--proposal-mode",
        config.proposal_mode,
        "--proposal-timeout-seconds",
        str(config.proposal_timeout_seconds),
        "--evolution-mode",
        config.evolution_mode,
        "--repo-path",
        str(child_repo_path),
    ]
    if config.proposal_model:
        command.extend(["--proposal-model", config.proposal_model])
    if config.repos:
        command.extend(["--repos", config.repos])
    else:
        command.extend(
            [
                "--trend-query",
                config.trend_query,
                "--trend-window-days",
                str(config.trend_window_days),
                "--trend-min-stars",
                str(config.trend_min_stars),
                "--trend-limit",
                str(config.trend_limit),
                "--trend-sort",
                config.trend_sort,
                "--trend-order",
                config.trend_order,
            ]
        )
        if config.include_forks:
            command.append("--include-forks")
    if config.topics:
        command.extend(["--topics", config.topics])
    if config.force_evolve:
        command.append("--force-evolve")
    if config.allow_dirty:
        command.append("--allow-dirty")
    if config.branch_prefix:
        command.extend(["--branch-prefix", config.branch_prefix])
    if config.self_model_path:
        command.extend(["--self-model-path", str(config.self_model_path)])
    if config.model:
        command.extend(["--model", config.model])
    if config.profile:
        command.extend(["--profile", config.profile])
    command.append("--require-codex-route" if config.require_codex_route else "--allow-default-codex-route")
    if config.sandbox:
        command.extend(["--sandbox", config.sandbox])
    if config.approval_policy:
        command.extend(["--approval-policy", config.approval_policy])
    command.append("--ignore-user-config" if config.ignore_user_config else "--use-user-config")
    if config.bypass_approvals_and_sandbox:
        command.append("--bypass-approvals-and-sandbox")
    command.extend(["--codex-timeout-seconds", str(config.codex_timeout_seconds)])
    extra_instruction = build_supervisor_extra_instruction(config)
    if extra_instruction:
        command.extend(["--extra-instruction", extra_instruction])
    return command


def build_supervisor_extra_instruction(config: SupervisorConfig) -> str:
    parts = [DEFAULT_SUPERVISOR_EXTRA_INSTRUCTION]
    if config.extra_instruction.strip():
        parts.append(config.extra_instruction.strip())
    return "\n\n".join(parts)


def run_supervisor_loop(
    config: SupervisorConfig,
    *,
    command_runner: Any = subprocess.run,
    sleep: Any = time.sleep,
    monotonic: Any = time.monotonic,
) -> int:
    """Run the native wake loop until interrupted or `max_passes` is reached."""

    validate_supervisor_config(config)
    prepare_supervisor_output(config)
    write_json(config.resolved_output_dir / "supervisor-config.json", config_to_dict(config))
    console.print(
        f"blackhole supervisor waking every {config.interval_seconds}s; "
        f"mode={config.evolution_mode}; output={config.resolved_output_dir}"
    )
    if config.startup_health_check:
        startup_record = run_startup_health_check(config, command_runner=command_runner)
        if startup_record.returncode != 0 and config.exit_on_failure:
            return startup_record.returncode
    if not config.run_immediately:
        sleep(config.interval_seconds)

    passes = 0
    last_returncode = 0
    while True:
        loop_started = monotonic()
        record = run_wake_once(config, command_runner=command_runner)
        passes += 1
        last_returncode = supervisor_effective_returncode(record)
        if should_exit_after_promotion(config, record):
            return config.restart_exit_code
        if last_returncode != 0 and config.exit_on_failure:
            return last_returncode
        if config.max_passes and passes >= config.max_passes:
            return last_returncode
        elapsed = monotonic() - loop_started
        sleep(max(0.0, config.interval_seconds - elapsed))


def run_wake_once(
    config: SupervisorConfig,
    *,
    command_runner: Any = subprocess.run,
) -> SupervisorPassRecord:
    """Run one child pass, write artifacts, and optionally promote successful changes."""

    validate_supervisor_config(config)
    prepare_supervisor_output(config)
    pass_id = compact_utc_timestamp()
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    child_repo_path = config.repo_path
    worktree_result: WorktreeResult | None = None
    create_stdout = ""
    create_stderr = ""
    worktree_created = False
    worktree_create_returncode = 0
    worktree_remove_attempted = False
    worktree_removed = False
    worktree_remove_returncode = 0
    timed_out = False
    commit_result: CommitResult | None = None
    promotion_result: PromotionResult | None = None
    stdout = ""
    stderr = ""

    if config.use_candidate_worktree and config.evolution_mode == "codex":
        worktree_path, create_completed = create_candidate_worktree(config, pass_id, command_runner=command_runner)
        child_repo_path = worktree_path
        create_stdout = create_completed.stdout or ""
        create_stderr = create_completed.stderr or ""
        worktree_create_returncode = int(create_completed.returncode)
        worktree_created = create_completed.returncode == 0
        if not worktree_created:
            record = build_pass_record(
                config,
                pass_id=pass_id,
                started_at=started_at,
                started_monotonic=started_monotonic,
                child_repo_path=child_repo_path,
                command=[],
                returncode=worktree_create_returncode,
                timed_out=False,
                stdout=create_stdout,
                stderr=create_stderr,
                worktree_result=WorktreeResult(
                    attempted=True,
                    created=False,
                    path=str(worktree_path),
                    create_returncode=worktree_create_returncode,
                    remove_attempted=False,
                    removed=False,
                    remove_returncode=0,
                    stdout_tail=tail_text(create_stdout),
                    stderr_tail=tail_text(create_stderr),
                ),
                commit_result=None,
                promotion_result=None,
                command_runner=command_runner,
            )
            write_pass_record(config.resolved_output_dir, record, interval_seconds=config.interval_seconds)
            append_supervisor_log(config.resolved_output_dir, record)
            return record

    start_branch = git_text(child_repo_path, ["git", "branch", "--show-current"], command_runner=command_runner)
    start_head = git_text(child_repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
    command = build_wake_command(config, repo_path=child_repo_path)

    try:
        completed = command_runner(
            command,
            cwd=child_repo_path,
            capture_output=True,
            text=True,
            timeout=config.pass_timeout_seconds,
        )
        returncode = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as error:
        timed_out = True
        returncode = 124
        stdout = timeout_text(error.stdout)
        stderr = timeout_text(error.stderr) or f"Timed out after {config.pass_timeout_seconds} seconds."

    if returncode == 0 and config.commit_successful_changes and config.evolution_mode == "codex":
        commit_result = commit_successful_changes(child_repo_path, pass_id, command_runner=command_runner)

    finish_branch = git_text(child_repo_path, ["git", "branch", "--show-current"], command_runner=command_runner)
    finish_head = git_text(child_repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
    if should_promote_candidate(config, returncode, start_head, finish_head, commit_result):
        promotion_result = promote_candidate(
            config,
            candidate_repo_path=child_repo_path,
            pass_id=pass_id,
            candidate_branch=finish_branch,
            candidate_head=finish_head,
            command_runner=command_runner,
        )

    if worktree_created and config.cleanup_candidate_worktree:
        worktree_remove_attempted = True
        remove_completed = command_runner(
            ["git", "worktree", "remove", "--force", str(child_repo_path)],
            cwd=config.repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        worktree_remove_returncode = int(remove_completed.returncode)
        worktree_removed = remove_completed.returncode == 0
        create_stdout = "\n".join(part for part in (create_stdout, remove_completed.stdout or "") if part)
        create_stderr = "\n".join(part for part in (create_stderr, remove_completed.stderr or "") if part)

    if config.use_candidate_worktree and config.evolution_mode == "codex":
        worktree_result = WorktreeResult(
            attempted=True,
            created=worktree_created,
            path=str(child_repo_path),
            create_returncode=worktree_create_returncode,
            remove_attempted=worktree_remove_attempted,
            removed=worktree_removed,
            remove_returncode=worktree_remove_returncode,
            stdout_tail=tail_text(create_stdout),
            stderr_tail=tail_text(create_stderr),
        )

    record = SupervisorPassRecord(
        pass_id=pass_id,
        started_at=started_at,
        finished_at=utc_now_iso(),
        start_branch=start_branch,
        start_head=start_head,
        finish_branch=finish_branch,
        finish_head=finish_head,
        command=command,
        cwd=str(child_repo_path),
        returncode=returncode,
        timed_out=timed_out,
        elapsed_seconds=round(time.monotonic() - started_monotonic, 3),
        stdout_tail=tail_text(stdout),
        stderr_tail=tail_text(stderr),
        worktree_result=worktree_result,
        commit_result=commit_result,
        promotion_result=promotion_result,
    )
    write_pass_record(config.resolved_output_dir, record, interval_seconds=config.interval_seconds)
    append_supervisor_log(config.resolved_output_dir, record)
    return record


def build_pass_record(
    config: SupervisorConfig,
    *,
    pass_id: str,
    started_at: str,
    started_monotonic: float,
    child_repo_path: Path,
    command: list[str],
    returncode: int,
    timed_out: bool,
    stdout: str,
    stderr: str,
    worktree_result: WorktreeResult | None,
    commit_result: CommitResult | None,
    promotion_result: PromotionResult | None,
    command_runner: Any,
) -> SupervisorPassRecord:
    return SupervisorPassRecord(
        pass_id=pass_id,
        started_at=started_at,
        finished_at=utc_now_iso(),
        start_branch=git_text(child_repo_path, ["git", "branch", "--show-current"], command_runner=command_runner),
        start_head=git_text(child_repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner),
        finish_branch=git_text(child_repo_path, ["git", "branch", "--show-current"], command_runner=command_runner),
        finish_head=git_text(child_repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner),
        command=command,
        cwd=str(child_repo_path),
        returncode=returncode,
        timed_out=timed_out,
        elapsed_seconds=round(time.monotonic() - started_monotonic, 3),
        stdout_tail=tail_text(stdout),
        stderr_tail=tail_text(stderr),
        worktree_result=worktree_result,
        commit_result=commit_result,
        promotion_result=promotion_result,
    )


def create_candidate_worktree(
    config: SupervisorConfig,
    pass_id: str,
    *,
    command_runner: Any = subprocess.run,
) -> tuple[Path, subprocess.CompletedProcess]:
    """Create a detached candidate worktree from the target branch."""

    parent = config.resolved_worktree_parent_dir
    parent.mkdir(parents=True, exist_ok=True)
    worktree_path = parent / pass_id
    completed = command_runner(
        ["git", "worktree", "add", "--detach", str(worktree_path), config.target_branch],
        cwd=config.repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return worktree_path, completed


def commit_successful_changes(
    repo_path: Path,
    pass_id: str,
    *,
    command_runner: Any = subprocess.run,
) -> CommitResult:
    """Create a local commit for successful autonomous source changes."""

    status = command_runner(["git", "status", "--porcelain"], cwd=repo_path, capture_output=True, text=True, timeout=30)
    status_stdout = status.stdout or ""
    if status.returncode != 0:
        return CommitResult(
            attempted=True,
            committed=False,
            returncode=int(status.returncode),
            status_before=status_stdout,
            commit_sha="",
            stdout_tail=tail_text(status.stdout or ""),
            stderr_tail=tail_text(status.stderr or ""),
        )
    if not status_stdout.strip():
        return CommitResult(
            attempted=False,
            committed=False,
            returncode=0,
            status_before="",
            commit_sha="",
            stdout_tail="",
            stderr_tail="",
        )

    add = command_runner(["git", "add", "-A"], cwd=repo_path, capture_output=True, text=True, timeout=60)
    if add.returncode != 0:
        return CommitResult(
            attempted=True,
            committed=False,
            returncode=int(add.returncode),
            status_before=status_stdout,
            commit_sha="",
            stdout_tail=tail_text(add.stdout or ""),
            stderr_tail=tail_text(add.stderr or ""),
        )

    message = f"Blackhole autonomous evolution {pass_id}"
    body = "Generated by blackhole-supervisor after a successful one-shot evolution pass."
    commit = command_runner(
        ["git", "commit", "-m", message, "-m", body],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if commit.returncode != 0:
        return CommitResult(
            attempted=True,
            committed=False,
            returncode=int(commit.returncode),
            status_before=status_stdout,
            commit_sha="",
            stdout_tail=tail_text(commit.stdout or ""),
            stderr_tail=tail_text(commit.stderr or ""),
        )

    rev_parse = command_runner(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    commit_sha = rev_parse.stdout.strip() if rev_parse.returncode == 0 else ""
    return CommitResult(
        attempted=True,
        committed=True,
        returncode=0,
        status_before=status_stdout,
        commit_sha=commit_sha,
        stdout_tail=tail_text(commit.stdout or ""),
        stderr_tail=tail_text(commit.stderr or ""),
    )


def should_promote_candidate(
    config: SupervisorConfig,
    child_returncode: int,
    start_head: str,
    finish_head: str,
    commit_result: CommitResult | None,
) -> bool:
    if not config.promote_successful_changes:
        return False
    if config.evolution_mode != "codex" or child_returncode != 0:
        return False
    if commit_result is not None and commit_result.returncode != 0:
        return False
    if commit_result is not None and commit_result.committed:
        return True
    return bool(start_head and finish_head and start_head != finish_head)


def promote_candidate(
    config: SupervisorConfig,
    *,
    candidate_repo_path: Path,
    pass_id: str,
    candidate_branch: str,
    candidate_head: str,
    command_runner: Any = subprocess.run,
) -> PromotionResult:
    """Promote a verified candidate commit into the target branch and optionally push it."""

    health_checks: list[HealthCheckResult] = []
    post_merge_health_checks: list[HealthCheckResult] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    rollback_artifact_path = config.resolved_growth_output_dir / "latest-rollback-point.json"
    rollback_artifact_exists = rollback_artifact_path.exists()
    target_before = git_text(
        config.repo_path,
        ["git", "rev-parse", "--verify", config.target_branch],
        command_runner=command_runner,
    )
    target_after = target_before

    def result(
        *,
        promoted: bool = False,
        pushed: bool = False,
        returncode: int = 0,
        rollback_attempted: bool = False,
        rollback_succeeded: bool = False,
        restart_requested: bool = False,
        restart_request_path: str = "",
    ) -> PromotionResult:
        return PromotionResult(
            attempted=True,
            promoted=promoted,
            pushed=pushed,
            returncode=returncode,
            candidate_branch=candidate_branch,
            candidate_head=candidate_head,
            target_branch=config.target_branch,
            target_before=target_before,
            target_after=target_after,
            rollback_artifact_path=str(rollback_artifact_path),
            rollback_artifact_exists=rollback_artifact_exists,
            health_checks=health_checks,
            post_merge_health_checks=post_merge_health_checks,
            rollback_attempted=rollback_attempted,
            rollback_succeeded=rollback_succeeded,
            restart_requested=restart_requested,
            restart_request_path=restart_request_path,
            stdout_tail=tail_text("\n".join(stdout_parts)),
            stderr_tail=tail_text("\n".join(stderr_parts)),
        )

    if not candidate_head:
        return result(returncode=1, restart_request_path="")
    if config.require_rollback_artifact and not rollback_artifact_exists:
        return result(returncode=1, restart_request_path="")

    target_status = command_runner(
        ["git", "status", "--porcelain"],
        cwd=config.repo_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    stdout_parts.append(target_status.stdout or "")
    stderr_parts.append(target_status.stderr or "")
    if target_status.returncode != 0:
        return result(returncode=int(target_status.returncode))
    if (target_status.stdout or "").strip():
        stderr_parts.append("target worktree is not clean")
        return result(returncode=1)

    health_checks = run_health_checks(config, candidate_repo_path, command_runner=command_runner)
    failed_health = first_failed_health_check(health_checks)
    if failed_health is not None:
        return result(returncode=failed_health.returncode)

    switch = command_runner(
        ["git", "switch", config.target_branch],
        cwd=config.repo_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    stdout_parts.append(switch.stdout or "")
    stderr_parts.append(switch.stderr or "")
    if switch.returncode != 0:
        return result(returncode=int(switch.returncode))

    merge = command_runner(
        ["git", "merge", "--ff-only", candidate_head],
        cwd=config.repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    stdout_parts.append(merge.stdout or "")
    stderr_parts.append(merge.stderr or "")
    if merge.returncode != 0:
        return result(returncode=int(merge.returncode))

    target_after = git_text(config.repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
    post_merge_health_checks = run_health_checks(config, config.repo_path, command_runner=command_runner)
    failed_post_health = first_failed_health_check(post_merge_health_checks)
    if failed_post_health is not None:
        reset = command_runner(
            ["git", "reset", "--hard", target_before],
            cwd=config.repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout_parts.append(reset.stdout or "")
        stderr_parts.append(reset.stderr or "")
        rollback_succeeded = reset.returncode == 0
        target_after = git_text(config.repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
        return result(
            returncode=failed_post_health.returncode,
            rollback_attempted=True,
            rollback_succeeded=rollback_succeeded,
        )

    pushed = False
    push_returncode = 0
    if config.push_promotions:
        push = command_runner(
            ["git", "push", config.remote_name, config.target_branch],
            cwd=config.repo_path,
            capture_output=True,
            text=True,
            timeout=300,
        )
        stdout_parts.append(push.stdout or "")
        stderr_parts.append(push.stderr or "")
        pushed = push.returncode == 0
        push_returncode = int(push.returncode)
        if not pushed:
            return result(promoted=True, pushed=False, returncode=push_returncode)

    write_activation_record(
        config,
        reason="promotion_applied",
        source_id=pass_id,
        current_head=target_after,
        current_branch=config.target_branch,
        previous_head=target_before,
        command_runner=command_runner,
    )
    restart_request_path = write_restart_request(config, pass_id, candidate_branch, candidate_head, target_after)
    return result(
        promoted=True,
        pushed=pushed,
        returncode=push_returncode,
        restart_requested=True,
        restart_request_path=str(restart_request_path),
    )


def run_health_checks(
    config: SupervisorConfig,
    repo_path: Path,
    *,
    command_runner: Any = subprocess.run,
) -> list[HealthCheckResult]:
    results: list[HealthCheckResult] = []
    env = build_health_env(config, repo_path)
    for command_text in config.health_commands:
        if not command_text.strip():
            continue
        command = split_command(command_text)
        completed = command_runner(
            command,
            cwd=repo_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=config.health_timeout_seconds,
        )
        results.append(
            HealthCheckResult(
                command=command,
                cwd=str(repo_path),
                returncode=int(completed.returncode),
                stdout_tail=tail_text(completed.stdout or ""),
                stderr_tail=tail_text(completed.stderr or ""),
            )
        )
        if completed.returncode != 0:
            break
    return results


def build_health_env(config: SupervisorConfig, repo_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env["PYTHONPATH"] = str(repo_path / "src")
    if same_path(repo_path, config.repo_path):
        health_venv = config.resolved_output_dir / "health-venv"
        health_venv.parent.mkdir(parents=True, exist_ok=True)
        env["UV_PROJECT_ENVIRONMENT"] = str(health_venv)
    return env


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def run_startup_health_check(
    config: SupervisorConfig,
    *,
    command_runner: Any = subprocess.run,
) -> StartupHealthRecord:
    """Run health checks on process start and optionally roll back a bad activation."""

    prepare_supervisor_output(config)
    check_id = compact_utc_timestamp()
    started_at = utc_now_iso()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    checks = run_health_checks(config, config.repo_path, command_runner=command_runner)
    failed_check = first_failed_health_check(checks)
    returncode = failed_check.returncode if failed_check is not None else 0
    rollback_target = ""
    rollback_attempted = False
    rollback_succeeded = False
    if failed_check is None:
        write_activation_record(
            config,
            reason="startup_health_passed",
            source_id=check_id,
            command_runner=command_runner,
        )
    elif config.rollback_on_startup_health_failure:
        rollback_target = startup_rollback_target(config, command_runner=command_runner)
        if rollback_target:
            rollback_attempted = True
            reset = command_runner(
                ["git", "reset", "--hard", rollback_target],
                cwd=config.repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            stdout_parts.append(reset.stdout or "")
            stderr_parts.append(reset.stderr or "")
            rollback_succeeded = reset.returncode == 0
            if rollback_succeeded:
                returncode = 0
    record = StartupHealthRecord(
        check_id=check_id,
        started_at=started_at,
        finished_at=utc_now_iso(),
        health_checks=checks,
        returncode=returncode,
        rollback_attempted=rollback_attempted,
        rollback_succeeded=rollback_succeeded,
        rollback_target=rollback_target,
        stdout_tail=tail_text("\n".join(stdout_parts)),
        stderr_tail=tail_text("\n".join(stderr_parts)),
    )
    write_startup_health_record(config.resolved_output_dir, record)
    return record


def startup_rollback_target(
    config: SupervisorConfig,
    *,
    command_runner: Any = subprocess.run,
) -> str:
    activation = read_latest_activation(config)
    current_head = git_text(config.repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
    activation_head = str(activation.get("current_head") or "")
    previous_head = str(activation.get("previous_head") or "")
    if activation_head:
        if current_head and current_head != activation_head:
            return activation_head
        if previous_head:
            return previous_head
    return latest_promotion_rollback_target(config)


def latest_promotion_rollback_target(config: SupervisorConfig) -> str:
    promotion = latest_promotion_payload(config)
    target = promotion.get("target_before") or ""
    return str(target)


def latest_promotion_activation_head(config: SupervisorConfig) -> str:
    promotion = latest_promotion_payload(config)
    target = promotion.get("target_after") or ""
    return str(target)


def latest_promotion_payload(config: SupervisorConfig) -> dict[str, Any]:
    path = config.resolved_output_dir / "latest-supervisor-pass.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    promotion = payload.get("promotion_result") or {}
    return promotion if isinstance(promotion, dict) else {}


def read_latest_activation(config: SupervisorConfig) -> dict[str, Any]:
    path = config.resolved_output_dir / LATEST_ACTIVATION_FILENAME
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_activation_record(
    config: SupervisorConfig,
    *,
    reason: str,
    source_id: str,
    current_head: str = "",
    current_branch: str = "",
    previous_head: str = "",
    previous_branch: str = "",
    command_runner: Any = subprocess.run,
) -> Path:
    activation_id = compact_utc_timestamp()
    existing = read_latest_activation(config)
    current_head = current_head or git_text(config.repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
    current_branch = current_branch or git_text(
        config.repo_path,
        ["git", "branch", "--show-current"],
        command_runner=command_runner,
    )
    existing_head = str(existing.get("current_head") or "")
    if not previous_head:
        if existing_head and existing_head != current_head:
            previous_head = existing_head
            previous_branch = previous_branch or str(existing.get("current_branch") or "")
        elif existing_head == current_head:
            previous_head = str(existing.get("previous_head") or "")
            previous_branch = previous_branch or str(existing.get("previous_branch") or "")
    if not previous_head:
        latest_promoted_head = latest_promotion_activation_head(config)
        if latest_promoted_head and latest_promoted_head != current_head:
            previous_head = latest_promoted_head
            previous_branch = previous_branch or config.target_branch
        elif latest_promoted_head == current_head:
            previous_head = latest_promotion_rollback_target(config)
            previous_branch = previous_branch or config.target_branch
    payload = {
        "activation_id": activation_id,
        "created_at": utc_now_iso(),
        "reason": reason,
        "source_id": source_id,
        "target_branch": config.target_branch,
        "current_branch": current_branch,
        "current_head": current_head,
        "previous_branch": previous_branch,
        "previous_head": previous_head,
        "health_commands": list(config.health_commands),
    }
    path = config.resolved_output_dir / f"activation-{activation_id}.json"
    write_json(path, payload)
    write_json(config.resolved_output_dir / LATEST_ACTIVATION_FILENAME, payload)
    return path


def first_failed_health_check(results: list[HealthCheckResult]) -> HealthCheckResult | None:
    for result in results:
        if result.returncode != 0:
            return result
    return None


def write_restart_request(
    config: SupervisorConfig,
    pass_id: str,
    candidate_branch: str,
    candidate_head: str,
    target_head: str,
) -> Path:
    payload = {
        "created_at": utc_now_iso(),
        "pass_id": pass_id,
        "reason": "promotion_applied",
        "candidate_branch": candidate_branch,
        "candidate_head": candidate_head,
        "target_branch": config.target_branch,
        "target_head": target_head,
        "restart_exit_code": config.restart_exit_code,
        "health_commands": list(config.health_commands),
    }
    path = config.resolved_output_dir / f"restart-request-{pass_id}.json"
    write_json(path, payload)
    write_json(config.resolved_output_dir / "latest-restart-request.json", payload)
    return path


def supervisor_effective_returncode(record: SupervisorPassRecord) -> int:
    if record.returncode != 0:
        return record.returncode
    if record.commit_result is not None and record.commit_result.returncode != 0:
        return record.commit_result.returncode
    if record.promotion_result is not None and record.promotion_result.returncode != 0:
        return record.promotion_result.returncode
    return 0


def should_exit_after_promotion(config: SupervisorConfig, record: SupervisorPassRecord) -> bool:
    promotion = record.promotion_result
    return bool(config.exit_after_promotion and promotion and promotion.restart_requested)


def git_text(
    repo_path: Path,
    command: list[str],
    *,
    command_runner: Any = subprocess.run,
) -> str:
    """Return best-effort git metadata for durable run records."""

    try:
        completed = command_runner(command, cwd=repo_path, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def validate_supervisor_config(config: SupervisorConfig) -> None:
    if config.interval_seconds < 1:
        raise ValueError("interval_seconds must be at least 1")
    if config.max_passes < 0:
        raise ValueError("max_passes cannot be negative")
    if config.pass_timeout_seconds < 1:
        raise ValueError("pass_timeout_seconds must be at least 1")
    if config.health_timeout_seconds < 1:
        raise ValueError("health_timeout_seconds must be at least 1")
    if config.restart_exit_code < 0:
        raise ValueError("restart_exit_code cannot be negative")
    if config.evolution_mode not in SUPPORTED_EVOLUTION_MODES:
        raise ValueError("evolution_mode must be one of: digest, plan, codex")
    if config.proposal_mode not in PROPOSAL_MODES:
        raise ValueError("proposal_mode must be one of: heuristic, llm, hybrid")
    if config.proposal_timeout_seconds < 1:
        raise ValueError("proposal_timeout_seconds must be at least 1")
    preflight = build_runtime_startup_preflight(config)
    if not preflight["ok"]:
        diagnostics = "; ".join(str(item) for item in preflight["diagnostics"])
        raise ValueError(f"runtime startup preflight failed: {diagnostics}")


def build_provider_config_preflight(
    config: SupervisorConfig,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return metadata-only diagnostics for provider token environment setup."""

    environment = os.environ if env is None else env
    token_env_name = str(config.token_env or "").strip()
    diagnostics: list[str] = []
    token_env_valid = is_valid_env_var_name(token_env_name)
    token_env_present = bool(token_env_valid and str(environment.get(token_env_name) or "").strip())
    if not token_env_name:
        diagnostics.append("token_env must name an environment variable")
    elif not token_env_valid:
        diagnostics.append("token_env must be a valid environment variable name")
    elif config.require_token_env and not token_env_present:
        diagnostics.append("required token environment variable is not set or empty")
    codex_preflight = build_codex_provider_preflight(
        CodexCliConfig(
            model=config.model,
            profile=config.profile,
            require_explicit_route=config.require_codex_route and config.evolution_mode == "codex",
        )
    )
    if config.evolution_mode == "codex" and not codex_preflight["ok"]:
        diagnostics.extend(str(item) for item in codex_preflight["diagnostics"])
    return {
        "schema_version": 1,
        "ok": not diagnostics,
        "diagnostics": diagnostics,
        "provider": "github",
        "token_env_name": token_env_name if token_env_valid else None,
        "token_env_name_recorded": token_env_valid,
        "token_env_valid": token_env_valid,
        "token_env_required": config.require_token_env,
        "token_env_present": token_env_present,
        "token_value_recorded": False,
        "codex": codex_preflight,
    }


def default_supervisor_tool_descriptors() -> tuple[ToolDescriptor, ...]:
    """Return built-in local tools that the supervisor may expose to child agents."""

    return (local_memory_tool_descriptor(),)


def build_runtime_startup_preflight(
    config: SupervisorConfig,
    *,
    env: dict[str, str] | None = None,
    tool_descriptors: tuple[ToolDescriptor, ...] | None = None,
) -> dict[str, Any]:
    """Return provider and tool-routing diagnostics checked before a wake pass starts."""

    provider_preflight = build_provider_config_preflight(config, env=env)
    tool_preflight = build_tool_routing_preflight(
        tool_descriptors if tool_descriptors is not None else default_supervisor_tool_descriptors(),
        required_tool_names=config.required_tool_names,
    )
    diagnostics = [
        *[str(item) for item in provider_preflight["diagnostics"]],
        *[str(item) for item in tool_preflight["diagnostics"]],
    ]
    return {
        "schema_version": 1,
        "ok": provider_preflight["ok"] and tool_preflight["ok"],
        "diagnostics": diagnostics,
        "provider_config": provider_preflight,
        "tool_routing": tool_preflight,
        "token_value_recorded": False,
    }


def build_upgrade_version_preflight(
    *,
    current_version: str,
    latest_version: str,
    allow_dev_versions: bool = False,
) -> dict[str, Any]:
    """Return the local decision a runner should make before invoking an upgrade action."""

    current = normalize_version_for_preflight(current_version)
    latest = normalize_version_for_preflight(latest_version)
    diagnostics: list[str] = []
    if current is None:
        diagnostics.append("current_version is missing or invalid")
    if latest is None:
        diagnostics.append("latest_version is missing or invalid")

    current_is_dev = current is not None and version_has_preview_marker(current_version)
    latest_is_dev = latest is not None and version_has_preview_marker(latest_version)
    if (current_is_dev or latest_is_dev) and not allow_dev_versions:
        diagnostics.append("development or preview versions require explicit opt-in before upgrade")
        return {
            "schema_version": 1,
            "ok": False,
            "should_upgrade": False,
            "outcome": "dev_version_blocked",
            "diagnostics": diagnostics,
            "current_version": current_version,
            "latest_version": latest_version,
            "current_version_is_dev": current_is_dev,
            "latest_version_is_dev": latest_is_dev,
            "upgrade_action_permitted": False,
        }

    if current is None or latest is None:
        return {
            "schema_version": 1,
            "ok": False,
            "should_upgrade": False,
            "outcome": "invalid_version",
            "diagnostics": diagnostics,
            "current_version": current_version,
            "latest_version": latest_version,
            "current_version_is_dev": current_is_dev,
            "latest_version_is_dev": latest_is_dev,
            "upgrade_action_permitted": False,
        }

    comparison = compare_normalized_versions(current, latest)
    if comparison < 0:
        outcome = "upgrade_needed"
        should_upgrade = True
        ok = True
    elif comparison == 0:
        outcome = "already_current"
        should_upgrade = False
        ok = True
        diagnostics.append("current_version already matches latest_version")
    else:
        outcome = "downgrade_blocked"
        should_upgrade = False
        ok = False
        diagnostics.append("latest_version is older than current_version")

    return {
        "schema_version": 1,
        "ok": ok,
        "should_upgrade": should_upgrade,
        "outcome": outcome,
        "diagnostics": diagnostics,
        "current_version": current_version,
        "latest_version": latest_version,
        "current_version_is_dev": current_is_dev,
        "latest_version_is_dev": latest_is_dev,
        "upgrade_action_permitted": should_upgrade,
    }


def normalize_version_for_preflight(value: str) -> tuple[int, ...] | None:
    cleaned = str(value or "").strip().lower()
    if not cleaned:
        return None
    cleaned = cleaned.removeprefix("v")
    match = re.match(r"^(\d+(?:[._-]\d+)*)", cleaned)
    if match is None:
        return None
    return tuple(int(part) for part in re.split(r"[._-]", match.group(1)) if part != "")


def version_has_preview_marker(value: str) -> bool:
    cleaned = str(value or "").strip().lower()
    if not cleaned:
        return False
    marker_text = re.sub(r"^\d+(?:[._-]\d+)*", "", cleaned.removeprefix("v"))
    marker_pattern = r"(?:^|[.+_-])(" + "|".join(re.escape(marker) for marker in VERSION_PREVIEW_MARKERS) + r")(?:\d|[.+_-]|$)"
    return re.search(marker_pattern, marker_text) is not None


def compare_normalized_versions(current: tuple[int, ...], latest: tuple[int, ...]) -> int:
    width = max(len(current), len(latest))
    padded_current = current + (0,) * (width - len(current))
    padded_latest = latest + (0,) * (width - len(latest))
    if padded_current < padded_latest:
        return -1
    if padded_current > padded_latest:
        return 1
    return 0


def is_valid_env_var_name(name: str) -> bool:
    if not name:
        return False
    first = name[0]
    if not (first.isalpha() or first == "_"):
        return False
    return all(character.isalnum() or character == "_" for character in name[1:])


def prepare_supervisor_output(config: SupervisorConfig) -> None:
    config.resolved_output_dir.mkdir(parents=True, exist_ok=True)
    config.resolved_growth_output_dir.mkdir(parents=True, exist_ok=True)
    if config.use_candidate_worktree:
        config.resolved_worktree_parent_dir.mkdir(parents=True, exist_ok=True)


def write_pass_record(output_dir: Path, record: SupervisorPassRecord, *, interval_seconds: int = 3600) -> None:
    payload = pass_record_to_dict(record)
    pass_path = output_dir / f"supervisor-pass-{record.pass_id}.json"
    write_json(pass_path, payload)
    write_json(output_dir / "latest-supervisor-pass.json", payload)
    heartbeat = {
        "last_pass_id": record.pass_id,
        "last_started_at": record.started_at,
        "last_finished_at": record.finished_at,
        "last_returncode": record.returncode,
        "last_effective_returncode": supervisor_effective_returncode(record),
        "last_timed_out": record.timed_out,
        "last_start_branch": record.start_branch,
        "last_start_head": record.start_head,
        "last_finish_branch": record.finish_branch,
        "last_finish_head": record.finish_head,
        "last_promoted": bool(record.promotion_result and record.promotion_result.promoted),
        "last_pushed": bool(record.promotion_result and record.promotion_result.pushed),
        "last_restart_requested": bool(record.promotion_result and record.promotion_result.restart_requested),
    }
    heartbeat["runner_liveness"] = supervisor_runner_status_from_heartbeat(
        output_dir / "latest-supervisor-heartbeat.json",
        heartbeat=heartbeat,
        interval_seconds=interval_seconds,
    ).to_dict()
    write_json(output_dir / "latest-supervisor-heartbeat.json", heartbeat)


def supervisor_runner_status_from_heartbeat(
    heartbeat_path: Path,
    *,
    heartbeat: dict[str, Any] | None = None,
    interval_seconds: int = 3600,
    now: datetime | None = None,
    controller_connected: bool = True,
    stale_after_intervals: float = 2.0,
) -> SupervisorRunnerStatus:
    """Derive reconnect-safe supervisor runner liveness from durable heartbeat metadata."""

    current_time = now or datetime.now(timezone.utc)
    payload = heartbeat if heartbeat is not None else read_json_if_exists(heartbeat_path)
    empty_child_summary = empty_supervisor_child_summary()
    if not payload:
        return SupervisorRunnerStatus(
            schema_version=2,
            status="runner_unavailable",
            controller_visible_status="unavailable",
            user_visible_message="No supervisor heartbeat has been recorded yet.",
            reason="missing_heartbeat",
            heartbeat_path=str(heartbeat_path),
            heartbeat_present=False,
            last_pass_id="",
            last_finished_at="",
            last_effective_returncode=None,
            seconds_since_last_finish=None,
            next_wake_due_at="",
            **empty_child_summary,
        )
    child_summary = supervisor_child_summary_from_heartbeat(payload)
    last_pass_id = str(payload.get("last_pass_id") or "")
    last_finished_at = str(payload.get("last_finished_at") or "")
    last_effective_returncode = int(payload.get("last_effective_returncode") or 0)
    finished_at = parse_utc_datetime(last_finished_at)
    seconds_since_finish: float | None = None
    next_wake_due_at = ""
    if finished_at is not None:
        seconds_since_finish = max(0.0, (current_time - finished_at).total_seconds())
        next_wake_due_at = (finished_at + timedelta(seconds=interval_seconds)).isoformat().replace("+00:00", "Z")
    if not controller_connected:
        return SupervisorRunnerStatus(
            schema_version=2,
            status="controller_disconnected",
            controller_visible_status="disconnected",
            user_visible_message="Supervisor connection is unavailable; reconnect before scheduling the next wake.",
            reason="controller_not_connected",
            heartbeat_path=str(heartbeat_path),
            heartbeat_present=True,
            last_pass_id=last_pass_id,
            last_finished_at=last_finished_at,
            last_effective_returncode=last_effective_returncode,
            seconds_since_last_finish=seconds_since_finish,
            next_wake_due_at=next_wake_due_at,
            **child_summary,
        )
    if last_effective_returncode != 0:
        return SupervisorRunnerStatus(
            schema_version=2,
            status="runner_failed",
            controller_visible_status="failed",
            user_visible_message="The last supervisor wake failed; inspect the latest pass artifact before relying on the next wake.",
            reason="last_pass_failed",
            heartbeat_path=str(heartbeat_path),
            heartbeat_present=True,
            last_pass_id=last_pass_id,
            last_finished_at=last_finished_at,
            last_effective_returncode=last_effective_returncode,
            seconds_since_last_finish=seconds_since_finish,
            next_wake_due_at=next_wake_due_at,
            **child_summary,
        )
    stale_after_seconds = interval_seconds * stale_after_intervals
    if seconds_since_finish is None or seconds_since_finish > stale_after_seconds:
        return SupervisorRunnerStatus(
            schema_version=2,
            status="runner_unavailable",
            controller_visible_status="unavailable",
            user_visible_message="Supervisor heartbeat is stale; confirm the scheduler is running before waiting for more work.",
            reason="stale_or_invalid_heartbeat",
            heartbeat_path=str(heartbeat_path),
            heartbeat_present=True,
            last_pass_id=last_pass_id,
            last_finished_at=last_finished_at,
            last_effective_returncode=last_effective_returncode,
            seconds_since_last_finish=seconds_since_finish,
            next_wake_due_at=next_wake_due_at,
            **child_summary,
        )
    if child_summary["active_child_count"] > 0:
        count = child_summary["active_child_count"]
        agent_word = "agent" if count == 1 else "agents"
        return SupervisorRunnerStatus(
            schema_version=2,
            status="child_agents_active",
            controller_visible_status="children_active",
            user_visible_message=(
                f"{count} child {agent_word} active while the parent runner is otherwise between supervisor wakes."
            ),
            reason="active_child_sessions",
            heartbeat_path=str(heartbeat_path),
            heartbeat_present=True,
            last_pass_id=last_pass_id,
            last_finished_at=last_finished_at,
            last_effective_returncode=last_effective_returncode,
            seconds_since_last_finish=seconds_since_finish,
            next_wake_due_at=next_wake_due_at,
            **child_summary,
        )
    return SupervisorRunnerStatus(
        schema_version=2,
        status="runner_asleep",
        controller_visible_status="asleep",
        user_visible_message="The one-shot runner is asleep between supervisor wakes; the scheduler will start a fresh runner on the next wake.",
        reason="between_scheduled_wakes",
        heartbeat_path=str(heartbeat_path),
        heartbeat_present=True,
        last_pass_id=last_pass_id,
        last_finished_at=last_finished_at,
        last_effective_returncode=last_effective_returncode,
        seconds_since_last_finish=seconds_since_finish,
        next_wake_due_at=next_wake_due_at,
        **child_summary,
    )


def empty_supervisor_child_summary() -> dict[str, Any]:
    return {
        "active_child_count": 0,
        "child_status_counts": {},
        "active_child_sessions": [],
    }


def supervisor_child_summary_from_heartbeat(payload: dict[str, Any]) -> dict[str, Any]:
    """Summarize child-session metadata carried by a supervisor heartbeat."""

    current_pass_id = str(payload.get("last_pass_id") or "")
    raw_sessions = iter_supervisor_child_sessions(payload)
    sessions = [
        session
        for session in raw_sessions
        if supervisor_child_session_belongs_to_pass(session, current_pass_id)
    ]
    status_counts: dict[str, int] = {}
    active_sessions: list[dict[str, Any]] = []
    for session in sessions:
        status = supervisor_child_session_status(session)
        status_counts[status] = status_counts.get(status, 0) + 1
        if supervisor_child_session_is_active(session, status):
            active_sessions.append(
                {
                    "id": str(session.get("id") or session.get("session_id") or ""),
                    "status": status,
                    "busy": bool(session.get("busy")),
                    "current_task_status": str(session.get("current_task_status") or ""),
                    "pending_elicitations_count": safe_int(session.get("pending_elicitations_count")),
                }
            )
    explicit_active_count = payload.get("active_child_count")
    active_count = len(active_sessions)
    if (
        not any(supervisor_child_session_has_pass_owner(session) for session in raw_sessions)
        and isinstance(explicit_active_count, int)
        and explicit_active_count > active_count
    ):
        active_count = explicit_active_count
    return {
        "active_child_count": active_count,
        "child_status_counts": status_counts,
        "active_child_sessions": active_sessions,
    }


def supervisor_child_session_belongs_to_pass(session: dict[str, Any], current_pass_id: str) -> bool:
    """Return false for child-session metadata explicitly tied to another wake pass."""

    for key in ("pass_id", "parent_pass_id", "wake_pass_id", "run_id"):
        value = str(session.get(key) or "").strip()
        if value:
            return not current_pass_id or value == current_pass_id
    return True


def supervisor_child_session_has_pass_owner(session: dict[str, Any]) -> bool:
    return any(str(session.get(key) or "").strip() for key in ("pass_id", "parent_pass_id", "wake_pass_id", "run_id"))


def iter_supervisor_child_sessions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("child_sessions") or payload.get("children") or payload.get("active_child_sessions") or []
    if isinstance(candidates, dict):
        iterable = [
            {"id": key, **value} if isinstance(value, dict) else {"id": key, "status": value}
            for key, value in candidates.items()
        ]
    elif isinstance(candidates, list):
        iterable = candidates
    else:
        iterable = []

    sessions: list[dict[str, Any]] = []
    for candidate in iterable:
        if not isinstance(candidate, dict):
            continue
        sessions.append(candidate)
        for child_key in ("child_sessions", "children"):
            child_value = candidate.get(child_key)
            if isinstance(child_value, (dict, list)):
                sessions.extend(iter_supervisor_child_sessions({child_key: child_value}))
    return sessions


def supervisor_child_session_status(session: dict[str, Any]) -> str:
    status = session.get("status") or session.get("state") or session.get("current_task_status") or "unknown"
    return str(status).strip().lower() or "unknown"


def supervisor_child_session_is_active(session: dict[str, Any], status: str) -> bool:
    if bool(session.get("busy")):
        return True
    if safe_int(session.get("pending_elicitations_count")) > 0:
        return True
    if status in {
        "active",
        "busy",
        "running",
        "working",
        "queued",
        "pending",
        "awaiting_user",
        "terminating",
        "stopping",
        "cancelling",
        "canceling",
        "shutting_down",
    }:
        return True
    current_task_status = str(session.get("current_task_status") or "").strip().lower()
    return bool(current_task_status and current_task_status not in {"idle", "done", "complete", "completed", "sleeping"})


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def read_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def parse_utc_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def write_startup_health_record(output_dir: Path, record: StartupHealthRecord) -> None:
    payload = startup_health_record_to_dict(record)
    write_json(output_dir / f"startup-health-{record.check_id}.json", payload)
    write_json(output_dir / "latest-startup-health.json", payload)


def append_supervisor_log(output_dir: Path, record: SupervisorPassRecord) -> None:
    lines = [
        "",
        f"=== blackhole supervisor pass {record.pass_id} ===",
        f"started_at={record.started_at}",
        f"finished_at={record.finished_at}",
        f"start_branch={record.start_branch}",
        f"start_head={record.start_head}",
        f"finish_branch={record.finish_branch}",
        f"finish_head={record.finish_head}",
        f"returncode={record.returncode}",
        f"effective_returncode={supervisor_effective_returncode(record)}",
        f"timed_out={record.timed_out}",
        "$ " + " ".join(shlex.quote(part) for part in record.command),
    ]
    if record.worktree_result is not None:
        lines.append(f"worktree_result={json.dumps(asdict(record.worktree_result), sort_keys=True)}")
    if record.commit_result is not None:
        lines.append(f"commit_result={json.dumps(asdict(record.commit_result), sort_keys=True)}")
    if record.promotion_result is not None:
        lines.append(f"promotion_result={json.dumps(promotion_result_to_dict(record.promotion_result), sort_keys=True)}")
    if record.stdout_tail:
        lines.extend(["--- stdout tail ---", record.stdout_tail.rstrip()])
    if record.stderr_tail:
        lines.extend(["--- stderr tail ---", record.stderr_tail.rstrip()])
    lines.append("")
    with (output_dir / "supervisor.log").open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def pass_record_to_dict(record: SupervisorPassRecord) -> dict[str, Any]:
    data = asdict(record)
    if record.worktree_result is not None:
        data["worktree_result"] = asdict(record.worktree_result)
    if record.commit_result is not None:
        data["commit_result"] = asdict(record.commit_result)
    if record.promotion_result is not None:
        data["promotion_result"] = promotion_result_to_dict(record.promotion_result)
    return data


def promotion_result_to_dict(result: PromotionResult) -> dict[str, Any]:
    data = asdict(result)
    data["health_checks"] = [asdict(check) for check in result.health_checks]
    data["post_merge_health_checks"] = [asdict(check) for check in result.post_merge_health_checks]
    return data


def startup_health_record_to_dict(record: StartupHealthRecord) -> dict[str, Any]:
    data = asdict(record)
    data["health_checks"] = [asdict(check) for check in record.health_checks]
    return data


def config_to_dict(config: SupervisorConfig) -> dict[str, Any]:
    data = asdict(config)
    data["repo_path"] = str(config.repo_path)
    data["output_dir"] = str(config.resolved_output_dir)
    data["growth_output_dir"] = str(config.resolved_growth_output_dir)
    data["worktree_parent_dir"] = str(config.resolved_worktree_parent_dir)
    data["self_model_path"] = str(config.self_model_path)
    data["health_commands"] = list(config.health_commands)
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(repo_path: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_path / path


def split_command(command_text: str) -> list[str]:
    return shlex.split(command_text, posix=os.name != "nt")


def parse_health_commands(value: str) -> tuple[str, ...]:
    commands = [line.strip() for line in value.splitlines() if line.strip()]
    return tuple(commands) or DEFAULT_HEALTH_COMMANDS


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def compact_utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def timeout_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def tail_text(value: str, *, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


@app.command(help="Wake blackhole-agent on a native cadence and launch one-shot growth passes.")
def main(
    repo_path: Path = typer.Option(Path("."), "--repo-path", help="blackhole-agent checkout to wake and evolve."),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir", "-o", help="Supervisor artifact directory."),
    growth_output_dir: Path | None = typer.Option(
        None,
        "--growth-output-dir",
        help="Child growth artifact directory. Defaults to <output-dir>/growth.",
    ),
    worktree_parent_dir: Path | None = typer.Option(
        None,
        "--worktree-parent-dir",
        help="Candidate worktree parent. Defaults to a sibling directory next to the repo.",
    ),
    interval_seconds: int = typer.Option(3600, "--interval-seconds", min=1, help="Wake cadence in seconds."),
    max_passes: int = typer.Option(0, "--max-passes", min=0, help="Stop after this many passes; 0 runs forever."),
    run_immediately: bool = typer.Option(
        True,
        "--run-immediately/--wait-first",
        help="Run the first pass immediately or wait one interval first.",
    ),
    exit_on_failure: bool = typer.Option(False, "--exit-on-failure", help="Stop the supervisor after a failed pass."),
    pass_timeout_seconds: int = typer.Option(5400, "--pass-timeout-seconds", min=1, help="Timeout for one child pass."),
    evolution_mode: str = typer.Option("codex", "--evolution-mode", help="One of: digest, plan, codex."),
    repos: str = typer.Option("", "--repos", "-r", help="Optional comma-separated repositories."),
    trend_query: str = typer.Option("agent language:Python", "--trend-query", help="GitHub trend search terms."),
    trend_window_days: int = typer.Option(14, "--trend-window-days", min=1, help="Trend creation window."),
    trend_min_stars: int = typer.Option(5, "--trend-min-stars", min=0, help="Minimum trend stars."),
    trend_limit: int = typer.Option(5, "--trend-limit", min=1, max=100, help="Maximum trend repositories per pass."),
    trend_sort: str = typer.Option("stars", "--trend-sort", help="Trend search sort."),
    trend_order: str = typer.Option("desc", "--trend-order", help="Trend search order."),
    include_forks: bool = typer.Option(False, "--include-forks", help="Include forked trend repositories."),
    token_env: str = typer.Option("GITHUB_TOKEN", "--token-env", help="Environment variable with a GitHub token."),
    require_token_env: bool = typer.Option(
        False,
        "--require-token-env/--allow-missing-token-env",
        help="Fail supervisor startup when --token-env is unset or empty.",
    ),
    topics: str = typer.Option("", "--topics", help="Comma-separated relevance topics."),
    lookback_hours: int = typer.Option(24, "--lookback-hours", min=1, help="Initial event lookback window."),
    max_events_per_repo: int = typer.Option(100, "--max-events-per-repo", min=1, max=100, help="GitHub events page size."),
    proposal_mode: str = typer.Option(DEFAULT_PROPOSAL_MODE, "--proposal-mode", help="One of: heuristic, llm, hybrid."),
    proposal_model: str | None = typer.Option(
        None,
        "--proposal-model",
        help="Model for read-only proposal interpretation. Defaults to --model in the child command.",
    ),
    proposal_timeout_seconds: int = typer.Option(
        180,
        "--proposal-timeout-seconds",
        min=1,
        help="Timeout for read-only proposal interpretation.",
    ),
    branch_prefix: str = typer.Option("codex/blackhole-evolve", "--branch-prefix", help="Evolution branch prefix."),
    self_model_path: Path = typer.Option(
        DEFAULT_SELF_MODEL_PATH,
        "--self-model-path",
        help="Repository-relative self-model file passed into every evolution task.",
    ),
    force_evolve: bool = typer.Option(True, "--force-evolve/--no-force-evolve", help="Create fallback evolution tasks."),
    allow_dirty: bool = typer.Option(False, "--allow-dirty", help="Allow codex mode to start from a dirty worktree."),
    model: str | None = typer.Option(None, "-m", "--model", help="Model to pass to Codex CLI."),
    profile: str | None = typer.Option(None, "--profile", help="Codex config profile."),
    require_codex_route: bool = typer.Option(True, "--require-codex-route/--allow-default-codex-route", help="Require codex mode to pass an explicit --model or --profile instead of relying on the CLI default route."),
    sandbox: str = typer.Option("workspace-write", "--sandbox", help="Codex sandbox mode."),
    approval_policy: str = typer.Option("never", "--approval-policy", help="Legacy compatibility option."),
    ignore_user_config: bool = typer.Option(
        True,
        "--ignore-user-config/--use-user-config",
        help="Ignore user Codex config while keeping auth available.",
    ),
    bypass_approvals_and_sandbox: bool = typer.Option(
        False,
        "--bypass-approvals-and-sandbox",
        help="Forward Codex's dangerous full-access bypass flag.",
    ),
    codex_timeout_seconds: int = typer.Option(3600, "--codex-timeout-seconds", min=1, help="Codex kernel timeout."),
    extra_instruction: str = typer.Option("", "--extra-instruction", help="Extra instruction appended to evolution tasks."),
    commit_successful_changes: bool = typer.Option(
        True,
        "--commit-successful-changes/--no-commit-successful-changes",
        help="Commit dirty source changes after a successful codex pass.",
    ),
    use_candidate_worktree: bool = typer.Option(
        True,
        "--candidate-worktree/--same-worktree",
        help="Run codex evolution inside an isolated candidate git worktree.",
    ),
    cleanup_candidate_worktree: bool = typer.Option(
        True,
        "--cleanup-candidate-worktree/--keep-candidate-worktree",
        help="Remove candidate worktrees after pass artifacts are written.",
    ),
    target_branch: str = typer.Option("main", "--target-branch", help="Branch that receives promoted candidates."),
    remote_name: str = typer.Option("origin", "--remote-name", help="Remote used for promotion pushes."),
    promote_successful_changes: bool = typer.Option(
        True,
        "--promote-successful-changes/--no-promote-successful-changes",
        help="Fast-forward the target branch after a verified candidate commit.",
    ),
    push_promotions: bool = typer.Option(
        True,
        "--push-promotions/--no-push-promotions",
        help="Push successful promotions to the configured remote.",
    ),
    require_rollback_artifact: bool = typer.Option(
        True,
        "--require-rollback-artifact/--no-require-rollback-artifact",
        help="Require latest rollback artifact before promotion.",
    ),
    health_commands: str = typer.Option(
        "\n".join(DEFAULT_HEALTH_COMMANDS),
        "--health-commands",
        help="Newline-separated commands that must pass before and after promotion.",
    ),
    health_timeout_seconds: int = typer.Option(900, "--health-timeout-seconds", min=1, help="Timeout per health command."),
    startup_health_check: bool = typer.Option(
        True,
        "--startup-health-check/--no-startup-health-check",
        help="Run health commands when the supervisor process starts.",
    ),
    rollback_on_startup_health_failure: bool = typer.Option(
        True,
        "--rollback-on-startup-health-failure/--no-rollback-on-startup-health-failure",
        help="Reset to the previous promoted HEAD when startup health fails.",
    ),
    exit_after_promotion: bool = typer.Option(
        False,
        "--exit-after-promotion/--stay-running-after-promotion",
        help="Exit with restart code after a promotion writes restart-request.json.",
    ),
    restart_exit_code: int = typer.Option(
        DEFAULT_RESTART_EXIT_CODE,
        "--restart-exit-code",
        min=0,
        help="Process exit code used when --exit-after-promotion is enabled.",
    ),
) -> None:
    config = SupervisorConfig(
        repo_path=repo_path.resolve(),
        output_dir=output_dir,
        growth_output_dir=growth_output_dir,
        worktree_parent_dir=worktree_parent_dir,
        interval_seconds=interval_seconds,
        max_passes=max_passes,
        run_immediately=run_immediately,
        exit_on_failure=exit_on_failure,
        pass_timeout_seconds=pass_timeout_seconds,
        evolution_mode=evolution_mode,
        repos=repos,
        trend_query=trend_query,
        trend_window_days=trend_window_days,
        trend_min_stars=trend_min_stars,
        trend_limit=trend_limit,
        trend_sort=trend_sort,
        trend_order=trend_order,
        include_forks=include_forks,
        token_env=token_env,
        require_token_env=require_token_env,
        topics=topics,
        lookback_hours=lookback_hours,
        max_events_per_repo=max_events_per_repo,
        proposal_mode=proposal_mode,
        proposal_model=proposal_model or model,
        proposal_timeout_seconds=proposal_timeout_seconds,
        branch_prefix=branch_prefix,
        self_model_path=self_model_path,
        force_evolve=force_evolve,
        allow_dirty=allow_dirty,
        model=model,
        profile=profile,
        require_codex_route=require_codex_route,
        sandbox=sandbox,
        approval_policy=approval_policy,
        ignore_user_config=ignore_user_config,
        bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
        codex_timeout_seconds=codex_timeout_seconds,
        extra_instruction=extra_instruction,
        commit_successful_changes=commit_successful_changes,
        use_candidate_worktree=use_candidate_worktree,
        cleanup_candidate_worktree=cleanup_candidate_worktree,
        target_branch=target_branch,
        remote_name=remote_name,
        promote_successful_changes=promote_successful_changes,
        push_promotions=push_promotions,
        require_rollback_artifact=require_rollback_artifact,
        health_commands=parse_health_commands(health_commands),
        health_timeout_seconds=health_timeout_seconds,
        startup_health_check=startup_health_check,
        rollback_on_startup_health_failure=rollback_on_startup_health_failure,
        exit_after_promotion=exit_after_promotion,
        restart_exit_code=restart_exit_code,
    )
    try:
        exit_code = run_supervisor_loop(config)
    except KeyboardInterrupt:
        console.print("blackhole supervisor stopped")
        raise typer.Exit(130) from None
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
