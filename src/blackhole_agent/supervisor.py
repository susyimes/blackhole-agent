"""Native wake supervisor for blackhole-agent.

The supervisor is deliberately outside the mutation kernel. It wakes on a fixed
cadence, launches one fresh blackhole child process, records the run, and then
sleeps until the next cadence boundary. Each child process reloads the current
checkout, so self-evolution can affect the following wake without embedding a
long-lived Codex loop inside the controller.
"""

import json
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

app = typer.Typer(rich_markup_mode="rich", add_completion=False)
console = Console(highlight=False)

SUPPORTED_EVOLUTION_MODES = {"digest", "plan", "codex"}
DEFAULT_OUTPUT_DIR = Path(".blackhole-agent/supervisor")
DEFAULT_SUPERVISOR_EXTRA_INSTRUCTION = (
    "Native supervisor note: this wake is one pass in an autonomous scheduled loop. "
    "Keep the change small, rollback-backed, locally verifiable, and do not push. "
    "When validation succeeds, leave the repository in a consistent state; the "
    "supervisor may commit successful source changes when configured."
)


@dataclass(frozen=True)
class SupervisorConfig:
    """Configuration for the native wake loop."""

    repo_path: Path
    output_dir: Path = DEFAULT_OUTPUT_DIR
    growth_output_dir: Path | None = None
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
    topics: str = ""
    lookback_hours: int = 24
    max_events_per_repo: int = 100
    branch_prefix: str = "codex/blackhole-evolve"
    force_evolve: bool = True
    allow_dirty: bool = False
    model: str | None = None
    profile: str | None = None
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    ignore_user_config: bool = True
    bypass_approvals_and_sandbox: bool = False
    codex_timeout_seconds: int = 3600
    extra_instruction: str = ""
    commit_successful_changes: bool = True

    @property
    def resolved_growth_output_dir(self) -> Path:
        return self.growth_output_dir or self.output_dir / "growth"


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
    commit_result: CommitResult | None


def build_wake_command(config: SupervisorConfig) -> list[str]:
    """Build the one-shot child command for a supervisor wake."""

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
        "--evolution-mode",
        config.evolution_mode,
        "--repo-path",
        str(config.repo_path),
    ]
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
    if config.model:
        command.extend(["--model", config.model])
    if config.profile:
        command.extend(["--profile", config.profile])
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
    write_json(config.output_dir / "supervisor-config.json", config_to_dict(config))
    console.print(
        f"blackhole supervisor waking every {config.interval_seconds}s; "
        f"mode={config.evolution_mode}; output={config.output_dir}"
    )
    if not config.run_immediately:
        sleep(config.interval_seconds)

    passes = 0
    last_returncode = 0
    while True:
        loop_started = monotonic()
        record = run_wake_once(config, command_runner=command_runner)
        passes += 1
        last_returncode = record.returncode
        if record.returncode != 0 and config.exit_on_failure:
            return record.returncode
        if config.max_passes and passes >= config.max_passes:
            return last_returncode
        elapsed = monotonic() - loop_started
        sleep(max(0.0, config.interval_seconds - elapsed))


def run_wake_once(
    config: SupervisorConfig,
    *,
    command_runner: Any = subprocess.run,
) -> SupervisorPassRecord:
    """Run one child pass, write artifacts, and optionally commit successful changes."""

    prepare_supervisor_output(config)
    pass_id = compact_utc_timestamp()
    started_at = utc_now_iso()
    started_monotonic = time.monotonic()
    start_branch = git_text(config.repo_path, ["git", "branch", "--show-current"], command_runner=command_runner)
    start_head = git_text(config.repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
    command = build_wake_command(config)
    timed_out = False
    commit_result: CommitResult | None = None

    try:
        completed = command_runner(
            command,
            cwd=config.repo_path,
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
        commit_result = commit_successful_changes(config.repo_path, pass_id, command_runner=command_runner)

    finish_branch = git_text(config.repo_path, ["git", "branch", "--show-current"], command_runner=command_runner)
    finish_head = git_text(config.repo_path, ["git", "rev-parse", "HEAD"], command_runner=command_runner)
    finished_at = utc_now_iso()
    record = SupervisorPassRecord(
        pass_id=pass_id,
        started_at=started_at,
        finished_at=finished_at,
        start_branch=start_branch,
        start_head=start_head,
        finish_branch=finish_branch,
        finish_head=finish_head,
        command=command,
        cwd=str(config.repo_path),
        returncode=returncode,
        timed_out=timed_out,
        elapsed_seconds=round(time.monotonic() - started_monotonic, 3),
        stdout_tail=tail_text(stdout),
        stderr_tail=tail_text(stderr),
        commit_result=commit_result,
    )
    write_pass_record(config.output_dir, record)
    append_supervisor_log(config.output_dir, record)
    return record


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
    if config.evolution_mode not in SUPPORTED_EVOLUTION_MODES:
        raise ValueError("evolution_mode must be one of: digest, plan, codex")


def prepare_supervisor_output(config: SupervisorConfig) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.resolved_growth_output_dir.mkdir(parents=True, exist_ok=True)


def write_pass_record(output_dir: Path, record: SupervisorPassRecord) -> None:
    payload = pass_record_to_dict(record)
    pass_path = output_dir / f"supervisor-pass-{record.pass_id}.json"
    write_json(pass_path, payload)
    write_json(output_dir / "latest-supervisor-pass.json", payload)
    write_json(
        output_dir / "latest-supervisor-heartbeat.json",
        {
            "last_pass_id": record.pass_id,
            "last_started_at": record.started_at,
            "last_finished_at": record.finished_at,
            "last_returncode": record.returncode,
            "last_timed_out": record.timed_out,
            "last_start_branch": record.start_branch,
            "last_start_head": record.start_head,
            "last_finish_branch": record.finish_branch,
            "last_finish_head": record.finish_head,
        },
    )


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
        f"timed_out={record.timed_out}",
        "$ " + " ".join(shlex.quote(part) for part in record.command),
    ]
    if record.commit_result is not None:
        lines.append(f"commit_result={json.dumps(asdict(record.commit_result), sort_keys=True)}")
    if record.stdout_tail:
        lines.extend(["--- stdout tail ---", record.stdout_tail.rstrip()])
    if record.stderr_tail:
        lines.extend(["--- stderr tail ---", record.stderr_tail.rstrip()])
    lines.append("")
    with (output_dir / "supervisor.log").open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def pass_record_to_dict(record: SupervisorPassRecord) -> dict[str, Any]:
    data = asdict(record)
    if record.commit_result is not None:
        data["commit_result"] = asdict(record.commit_result)
    return data


def config_to_dict(config: SupervisorConfig) -> dict[str, Any]:
    data = asdict(config)
    data["repo_path"] = str(config.repo_path)
    data["output_dir"] = str(config.output_dir)
    data["growth_output_dir"] = str(config.resolved_growth_output_dir)
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    topics: str = typer.Option("", "--topics", help="Comma-separated relevance topics."),
    lookback_hours: int = typer.Option(24, "--lookback-hours", min=1, help="Initial event lookback window."),
    max_events_per_repo: int = typer.Option(100, "--max-events-per-repo", min=1, max=100, help="GitHub events page size."),
    branch_prefix: str = typer.Option("codex/blackhole-evolve", "--branch-prefix", help="Evolution branch prefix."),
    force_evolve: bool = typer.Option(True, "--force-evolve/--no-force-evolve", help="Create fallback evolution tasks."),
    allow_dirty: bool = typer.Option(False, "--allow-dirty", help="Allow codex mode to start from a dirty worktree."),
    model: str | None = typer.Option(None, "-m", "--model", help="Model to pass to Codex CLI."),
    profile: str | None = typer.Option(None, "--profile", help="Codex config profile."),
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
) -> None:
    config = SupervisorConfig(
        repo_path=repo_path.resolve(),
        output_dir=output_dir,
        growth_output_dir=growth_output_dir,
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
        topics=topics,
        lookback_hours=lookback_hours,
        max_events_per_repo=max_events_per_repo,
        branch_prefix=branch_prefix,
        force_evolve=force_evolve,
        allow_dirty=allow_dirty,
        model=model,
        profile=profile,
        sandbox=sandbox,
        approval_policy=approval_policy,
        ignore_user_config=ignore_user_config,
        bypass_approvals_and_sandbox=bypass_approvals_and_sandbox,
        codex_timeout_seconds=codex_timeout_seconds,
        extra_instruction=extra_instruction,
        commit_successful_changes=commit_successful_changes,
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
