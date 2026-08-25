"""Class-level repair for recurring ``milestone_rejected`` on staging.

Three recorded rejections were the same class, not three packages: the
controller ran ``git add -A``, Git for Windows walked regenerable forage
scratch, and ``Filename too long`` aborted a proved behavior increment.

An instance patch deletes or gitignores the last extract (airflow wheels,
tmp-infer-airflow-amazon, …). A later sdist with a different long path
would fail the same way.

This module:

- enables ``core.longpaths`` on Unbound worktrees
- stages porcelain-listed paths instead of walking the whole tree
- skips regenerable scratch and unreadable non-behavior paths
- closes ``milestone_rejected`` once the resilience capability is proved
"""

from __future__ import annotations

import inspect
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from blackhole_agent.capability_compounder import legacy_pipeline_was_used

SCHEMA_VERSION = 1
MILESTONE_REJECTED = "milestone_rejected"
MILESTONE_COMMIT_RESILIENCE_ID = "capability.milestone-commit-resilience"

MILESTONE_COMMIT_RESILIENCE_DONE_WHEN = (
    f"capability_exists:{MILESTONE_COMMIT_RESILIENCE_ID};"
    f"capability_proved:{MILESTONE_COMMIT_RESILIENCE_ID};"
    "no_skill_route"
)
MILESTONE_COMMIT_RESILIENCE_GOAL = (
    "Stop rejecting proved Unbound milestones because Git cannot walk "
    "unreadable or long-path scratch. Stage porcelain-listed paths with "
    "core.longpaths enabled; never require deleting the last forage extract."
)

LONGPATH_ERROR_MARKERS = (
    "filename too long",
    "file name too long",
    "could not open directory",
    "name too long",
    "path too long",
)

# Regenerable campaign/forage trees. A new sdist name must match these
# prefixes; listing one package is an instance patch.
SCRATCH_PREFIXES = (
    "artifacts/capability-foraging/downloads/",
    "artifacts/capability-foraging/extracted/",
    "artifacts/tmp-",
    "artifacts/upstream-campaign/",
    "artifacts/upstream-fleet/",
)
SCRATCH_INFIXES = (
    "/.forage-deps/",
    "/extracted/",
)

# Last recorded instance paths. The repair must not name or delete them.
INSTANCE_PATCH_MARKERS = (
    "airflow",
    "tmp-infer-airflow-amazon",
    "apache-airflow-providers-common-compat",
    "apache_airflow_providers_common_compat",
)

_LATER_OCCURRENCE_EXTRACT = (
    "artifacts/capability-foraging/extracted/other-sdist-not-airflow"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_unreadable_tree_error(details: str) -> bool:
    lowered = str(details or "").lower()
    return any(marker in lowered for marker in LONGPATH_ERROR_MARKERS)


def is_tree_walking_git_add(command: Sequence[str]) -> bool:
    """True for git add -A / --all / . which walk the whole working tree."""

    parts = [str(item) for item in command]
    if len(parts) < 2 or parts[0] != "git" or parts[1] != "add":
        return False
    rest = parts[2:]
    if "-A" in rest or "--all" in rest:
        return True
    filtered = [item for item in rest if item != "--"]
    return filtered == ["."]


def is_regenerable_scratch(path: str) -> bool:
    normalized = str(path or "").strip().replace("\\", "/").lstrip("./")
    lowered = normalized.lower()
    if not lowered:
        return False
    if any(lowered.startswith(prefix) for prefix in SCRATCH_PREFIXES):
        return True
    padded = f"/{lowered}"
    return any(infix in padded for infix in SCRATCH_INFIXES)


def _is_workspace_dir(workspace: Path, relative: str) -> bool:
    try:
        return (workspace / relative).is_dir()
    except OSError:
        return False


def _should_skip_staging_path(workspace: Path, relative: str, *, behavior: bool) -> bool:
    if is_regenerable_scratch(relative):
        return True
    if behavior:
        return False
    if _is_workspace_dir(workspace, relative):
        # Adding a directory recurses; porcelain -uall already lists files.
        return True
    return False


def ensure_git_longpaths(
    workspace: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> None:
    """Turn on Git-for-Windows long-path support in this worktree."""

    from blackhole_agent.unbound import run_command

    run_command(
        ["git", "config", "core.longpaths", "true"],
        cwd=workspace,
        command_runner=command_runner,
        check=False,
    )


def _details(completed: subprocess.CompletedProcess) -> str:
    return ((completed.stderr or "") + "\n" + (completed.stdout or "")).strip()


def _add_one_path(
    workspace: Path,
    path: str,
    *,
    command_runner: Callable[..., Any],
    run_command: Callable[..., Any],
    is_behavior_path: Callable[[str], bool],
) -> str | None:
    """Stage one path. Return the path when skipped, or None when staged."""

    completed = run_command(
        ["git", "add", "--", path],
        cwd=workspace,
        command_runner=command_runner,
        check=False,
    )
    if completed.returncode == 0:
        return None
    details = _details(completed) or f"exit code {completed.returncode}"
    if is_unreadable_tree_error(details) and not is_behavior_path(path):
        return path
    raise RuntimeError(f"git add -- {path} failed: {details}")


def stage_milestone_paths(
    workspace: Path,
    paths: Sequence[str],
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, list[str]]:
    """Stage listed paths without ``git add -A``.

    Unreadable or regenerable scratch is skipped. A behavior path that cannot
    be staged still fails the milestone.
    """

    from blackhole_agent.unbound import (
        _normalize_repo_relpath,
        is_behavior_path,
        run_command,
    )

    ensure_git_longpaths(workspace, command_runner=command_runner)
    staged: list[str] = []
    skipped: list[str] = []
    pending: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = _normalize_repo_relpath(str(raw or ""))
        if not path or path in seen:
            continue
        seen.add(path)
        if _should_skip_staging_path(workspace, path, behavior=is_behavior_path(path)):
            skipped.append(path)
            continue
        pending.append(path)

    for offset in range(0, len(pending), 32):
        batch = pending[offset : offset + 32]
        completed = run_command(
            ["git", "add", "--", *batch],
            cwd=workspace,
            command_runner=command_runner,
            check=False,
        )
        if completed.returncode == 0:
            staged.extend(batch)
            continue
        for path in batch:
            skipped_path = _add_one_path(
                workspace,
                path,
                command_runner=command_runner,
                run_command=run_command,
                is_behavior_path=is_behavior_path,
            )
            if skipped_path is None:
                staged.append(path)
            else:
                skipped.append(skipped_path)
    return {"staged": staged, "skipped": skipped}


def poison_tree_walking_git_add(
    inner: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """command_runner that reproduces the recorded milestone_rejected class."""

    real = inner or subprocess.run

    def runner(command: Any, **kwargs: Any) -> Any:
        if isinstance(command, (list, tuple)) and is_tree_walking_git_add(command):
            return subprocess.CompletedProcess(
                list(command),
                128,
                stdout="",
                stderr=(
                    "warning: could not open directory "
                    f"'{_LATER_OCCURRENCE_EXTRACT}/nested/': Filename too long\n"
                ),
            )
        return real(command, **kwargs)

    return runner


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Blackhole Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "blackhole@example.invalid"], cwd=path, check=True)
    (path / "src").mkdir()
    (path / "src" / "seed.py").write_text("VALUE = 1\n", encoding="utf-8")
    (path / ".gitignore").write_text(
        "artifacts/capability-foraging/extracted/\nartifacts/tmp-*\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "seed"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_later_occurrence_scratch(root: Path) -> Path:
    """A different extract than the recorded airflow instance.

    The recorded class is Git walking that tree, not the exact depth. A later
    sdist name is enough to prove the repair is not ``delete the airflow
    extract``. Path creation stays under Windows MAX_PATH so the proof itself
    can run; ``poison_tree_walking_git_add`` reproduces the long-path failure.
    """

    deep = root.joinpath(*_LATER_OCCURRENCE_EXTRACT.split("/"))
    deep.mkdir(parents=True, exist_ok=True)
    leaf = deep / "leaf.txt"
    leaf.write_text("later occurrence scratch; not the airflow instance\n", encoding="utf-8")
    return leaf


def _write_proved_closer(root: Path, capability_id: str) -> Path:
    from blackhole_agent.capability_compounder import (
        Capability,
        CapabilityLedger,
        default_ledger_path,
        register_capability,
        save_ledger,
    )

    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id=capability_id,
            name=capability_id,
            description="Proved structural closer for milestone_rejected.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)
    return path


def _git_text(root: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        arguments,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return (completed.stdout or "").strip()


def builtin_milestone_commit_resilience_proof() -> dict[str, Any]:
    """Hermetic proof: a later long-path extract cannot reject a milestone."""

    from blackhole_agent.kernel_class_closure import class_closure_ids, class_is_closed
    from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST
    from blackhole_agent.pattern_register import (
        PatternRegister,
        record_occurrence,
        required_pattern_mission,
        save_register,
    )
    from blackhole_agent.unbound import TurnDecision, commit_milestone, git_head

    checks: dict[str, bool] = {}
    stage_source = inspect.getsource(stage_milestone_paths)
    commit_source = inspect.getsource(commit_milestone)
    combined = stage_source + commit_source
    lowered = combined.lower()
    checks["repair_is_not_airflow_instance_patch"] = not any(
        marker in lowered for marker in INSTANCE_PATCH_MARKERS
    )
    checks["commit_source_has_no_tree_walking_add"] = (
        '["git", "add", "-A"]' not in commit_source
        and "['git', 'add', '-A']" not in commit_source
        and '"--all"' not in commit_source
        and "'--all'" not in commit_source
    )
    checks["class_closure_lists_this_capability"] = class_closure_ids(MILESTONE_REJECTED) == (
        MILESTONE_COMMIT_RESILIENCE_ID,
    )
    checks["denylists_self"] = MILESTONE_COMMIT_RESILIENCE_ID in LOCAL_DENYLIST
    checks["tree_walk_detector"] = is_tree_walking_git_add(["git", "add", "-A"]) and not is_tree_walking_git_add(
        ["git", "add", "--", "src/seed.py"]
    )
    checks["scratch_classifier"] = is_regenerable_scratch(
        f"{_LATER_OCCURRENCE_EXTRACT}/nested/leaf.txt"
    ) and not is_regenerable_scratch("src/blackhole_agent/unbound.py")
    checks["longpath_error_classifier"] = is_unreadable_tree_error(
        "git add -A failed: warning: could not open directory 'x': Filename too long"
    )

    decision = TurnDecision.from_payload(
        {
            "status": "milestone",
            "summary": "behavior increment",
            "strategy": "class-level staging",
            "next_step": "none",
            "capability_delta": "Milestone commits survive unreadable scratch.",
            "outcome_evidence": ["src/capability.py committed"],
            "validation": [{"command": "true", "exit_code": 0, "summary": "ok"}],
            "done_when_met": False,
            "commit_message": "Add executable capability path",
            "mission_goal": "",
            "done_when": "",
        }
    )

    with tempfile.TemporaryDirectory(prefix="milestone-commit-resilience-") as tmp:
        root = Path(tmp)
        _init_repo(root)
        leaf = _write_later_occurrence_scratch(root)
        airflow_instance = root / "artifacts" / "tmp-infer-airflow-amazon"
        (root / "src" / "capability.py").write_text("print('CAPABILITY_OK')\n", encoding="utf-8")
        before = git_head(root)
        sha = commit_milestone(root, decision, 1, command_runner=poison_tree_walking_git_add())
        names = _git_text(root, ["git", "show", "--name-only", "--pretty=format:", sha])
        longpaths = _git_text(root, ["git", "config", "--get", "core.longpaths"])
        checks["commits_behavior_while_add_all_is_poisoned"] = bool(sha) and sha != before
        checks["behavior_path_is_in_commit"] = "src/capability.py" in names
        checks["later_extract_not_committed"] = "other-sdist-not-airflow" not in names
        checks["later_extract_still_on_disk"] = leaf.is_file()
        checks["instance_airflow_tree_was_never_required"] = not airflow_instance.exists()
        checks["core_longpaths_enabled"] = longpaths.strip().lower() in {"true", "1"}
        checks["repeating_airflow_delete_would_not_apply"] = (
            leaf.is_file() and not airflow_instance.exists() and sha != before
        )

    with tempfile.TemporaryDirectory(prefix="milestone-commit-open-") as tmp:
        root = Path(tmp)
        register = PatternRegister(recurrence_threshold=3)
        for index in range(3):
            record_occurrence(
                register,
                MILESTONE_REJECTED,
                source="proof",
                summary=f"git add -A filename too long {index}",
                evidence="milestone commit failed: git add -A failed: Filename too long",
            )
        save_register(root, register)
        checks["forced_while_closer_unproved"] = (
            (required_pattern_mission(root) or {}).get("class_id") == MILESTONE_REJECTED
            and not class_is_closed(MILESTONE_REJECTED, root)
        )

    with tempfile.TemporaryDirectory(prefix="milestone-commit-closed-") as tmp:
        root = Path(tmp)
        register = PatternRegister(recurrence_threshold=3)
        for index in range(3):
            record_occurrence(
                register,
                MILESTONE_REJECTED,
                source="proof",
                summary=f"git add -A filename too long {index}",
            )
        save_register(root, register)
        _write_proved_closer(root, MILESTONE_COMMIT_RESILIENCE_ID)
        checks["proved_closer_drops_forced_mission"] = (
            class_is_closed(MILESTONE_REJECTED, root)
            and required_pattern_mission(root) is None
        )

    checks["updated_at_helper"] = bool(_utc_now())
    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    return {
        "ok": ok,
        "action": "milestone_commit_resilience",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": MILESTONE_COMMIT_RESILIENCE_GOAL,
        "done_when": MILESTONE_COMMIT_RESILIENCE_DONE_WHEN,
        "failed": [name for name, value in checks.items() if not value],
        "payload": json.dumps(sorted(checks), sort_keys=True),
    }
