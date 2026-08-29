"""Reclaim stale directories git no longer treats as working trees.

``reclaim_mission_worktrees`` already prunes vanished workspaces and force-
removes registered ones. A published complete mission whose directory still
exists without a git worktree registration (``.git`` gone, prune already ran)
fails ``git worktree remove`` with ``is not a working tree``. That error is
appended to the GC report, ``ok`` becomes false, and
``last_worktree_gc_error`` stays sticky even when other worktrees reclaimed.

Experience fuel harvested ``last_publish_error`` but never
``last_worktree_gc_error``, so the class could not enter genesis.

This module closes that class:

- treat ``is not a working tree`` as a stale directory and delete it
- leave genuine remove failures as GC errors
- harvest sticky ``last_worktree_gc_error`` as ``worktree_gc_failed``
- drop the class from fuel once this closer is proved
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from blackhole_agent.capability_compounder import (
    Capability,
    CapabilityLedger,
    default_ledger_path,
    legacy_pipeline_was_used,
    load_ledger,
    register_capability,
    save_ledger,
    utc_now_iso,
)
from blackhole_agent.kernel_leftover import leftover_marker_ids
from blackhole_agent.local_capability_kernel import LOCAL_DENYLIST

SCHEMA_VERSION = 1
WORKTREE_GC_FAILED = "worktree_gc_failed"
WORKTREE_GC_RESILIENCE_ID = "capability.worktree-gc-resilience"
REPO_ROOT = Path(__file__).resolve().parents[2]
STALE_WORKTREE_MARKERS = ("is not a working tree", "not a working tree")

WORKTREE_GC_RESILIENCE_DONE_WHEN = (
    f"capability_exists:{WORKTREE_GC_RESILIENCE_ID};"
    f"capability_proved:{WORKTREE_GC_RESILIENCE_ID};"
    "no_skill_route"
)
WORKTREE_GC_RESILIENCE_GOAL = (
    "Repair mission-worktree reclamation of stale directories: a path that exists "
    "on disk but is no longer a git working tree still fails git worktree remove, "
    "poisons the GC report, and leaves last_worktree_gc_error sticky so later "
    "valid worktrees never finish clean."
)


def worktree_gc_resilience_proof_command() -> str:
    return (
        "uv run python -c \"from blackhole_agent.worktree_gc_resilience import "
        "builtin_worktree_gc_resilience_proof; r=builtin_worktree_gc_resilience_proof(); "
        "assert r['ok'] and r.get('action')=='worktree_gc_resilience' "
        "and r.get('passed_count',0) >= 8 "
        "and not r.get('used_skill_route_discovery')\""
    )


def is_not_a_working_tree_error(output: str) -> bool:
    """True for git's class of 'path exists but is not a worktree' failures."""

    text = str(output or "").lower()
    return any(marker in text for marker in STALE_WORKTREE_MARKERS)


def _rmtree(path: Path) -> bool:
    target = Path(path)
    if not target.exists():
        return True

    def _onexc(func: Any, name: str, exc: BaseException) -> None:
        try:
            os.chmod(name, stat.S_IWRITE)
            func(name)
        except OSError:
            pass

    shutil.rmtree(target, onexc=_onexc)
    return not target.exists()


def finish_failed_worktree_remove(
    report: dict[str, Any],
    entry: dict[str, Any],
    workspace: Path,
    removed: Any,
) -> None:
    """Reclaim a stale directory, or record a genuine worktree-remove error."""

    detail = str(getattr(removed, "stderr", "") or getattr(removed, "stdout", "") or "").strip()
    if is_not_a_working_tree_error(detail) and _rmtree(workspace):
        entry["removed"] = True
        entry["stale_not_a_working_tree"] = True
        report.setdefault("reclaimed", []).append(entry)
        return
    report.setdefault("errors", []).append(
        {"mission_id": entry.get("mission_id"), "error": detail}
    )


def harvest_worktree_gc_event(loop_state: dict[str, Any]) -> dict[str, str] | None:
    """Shape a sticky continuous-loop GC error as experience fuel."""

    error = str((loop_state or {}).get("last_worktree_gc_error") or "").strip()
    if not error:
        return None
    return {
        "class_id": WORKTREE_GC_FAILED,
        "source": "unbound",
        "summary": "continuous loop worktree GC failed",
        "evidence": error[:400],
    }


def ensure_worktree_gc_resilience_capability(*, repo_path: Path | None = None) -> Capability:
    """Register the closer on the live ledger once the proof is green."""

    root = (repo_path or REPO_ROOT).resolve()
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=WORKTREE_GC_RESILIENCE_ID,
        name="Worktree GC stale-directory reclaim",
        description=(
            "Mission-worktree GC deletes directories git no longer treats as "
            "working trees instead of poisoning the report; sticky "
            "last_worktree_gc_error is harvested as worktree_gc_failed and "
            "drops from genesis fuel once this closer is proved."
        ),
        kind="python",
        entry="blackhole_agent.worktree_gc_resilience:builtin_worktree_gc_resilience_proof",
        proof_command=worktree_gc_resilience_proof_command(),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "unbound.milestone-gate",
        ),
        behavior_paths=(
            "src/blackhole_agent/worktree_gc_resilience.py",
            "src/blackhole_agent/unbound.py",
            "src/blackhole_agent/experience_fuel.py",
            "capabilities/ledger.json",
        ),
        capability_delta=(
            "Stale not-a-working-tree directories are reclaimed without failing "
            "GC; last_worktree_gc_error enters experience fuel until this closer "
            "is proved."
        ),
        tags=("worktree", "gc", "reclaim", "git", "experience-fuel"),
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return (completed.stdout or "").strip()


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "gc@test.local")
    _git(repo, "config", "user.name", "GC Test")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    return repo


def _make_complete_mission(repo: Path, mission_id: str, *, created_at: str) -> Path:
    from blackhole_agent.unbound import UnboundMission, mission_root, save_mission

    parent = repo.parent / f".{repo.name}-unbound-worktrees"
    parent.mkdir(exist_ok=True)
    workspace = parent / mission_id
    branch = f"unbound/test-{mission_id}"
    _git(repo, "worktree", "add", "-b", branch, str(workspace), "main")
    (workspace / f"{mission_id}.txt").write_text("milestone\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", f"milestone {mission_id}")
    head = _git(workspace, "rev-parse", "HEAD")
    _git(repo, "merge", "--ff-only", head)
    mission_dir = mission_root(repo, Path(".blackhole-agent/unbound")) / "missions" / mission_id
    save_mission(
        mission_dir / "state.json",
        UnboundMission(
            schema_version=1,
            mission_id=mission_id,
            created_at=created_at,
            updated_at=created_at,
            repo_path=str(repo),
            workspace_path=str(workspace),
            branch=branch,
            target_branch="main",
            goal="test goal",
            done_when="test done",
            status="complete",
            stage="execution",
            base_head=head,
            last_milestone_head=head,
        ),
    )
    return workspace


def _detach_leave_directory(repo: Path, workspace: Path) -> None:
    gitdir = workspace / ".git"
    if gitdir.is_dir():
        shutil.rmtree(gitdir)
    elif gitdir.exists():
        gitdir.unlink()
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    (workspace / "STALE.txt").write_text("stale leftover\n", encoding="utf-8")


def _register_proved(root: Path, capability_id: str) -> None:
    path = default_ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = load_ledger(path) if path.is_file() else CapabilityLedger()
    register_capability(
        ledger,
        Capability(
            id=capability_id,
            name=capability_id,
            description="Proved closer used by worktree-gc-resilience proof.",
            kind="python",
            entry="blackhole_agent.local_capability_kernel:builtin_fixture_probe",
            proof_command="uv run python -c \"print('ok')\"",
            last_proof_exit_code=0,
        ),
        replace=True,
    )
    save_ledger(path, ledger)


def builtin_worktree_gc_resilience_proof() -> dict[str, Any]:
    """Hermetic proof: stale not-a-worktree dirs reclaim; genuine errors remain."""

    from blackhole_agent.experience_fuel import harvest_experience
    from blackhole_agent.kernel_class_closure import class_is_closed
    from blackhole_agent.unbound import reclaim_mission_worktrees

    checks: dict[str, bool] = {}
    checks["denylists_self"] = WORKTREE_GC_RESILIENCE_ID in LOCAL_DENYLIST
    checks["leftover_marker"] = leftover_marker_ids(WORKTREE_GC_RESILIENCE_GOAL) == (
        WORKTREE_GC_RESILIENCE_ID,
    )
    checks["detects_stale_class"] = is_not_a_working_tree_error(
        "fatal: 'C:/tmp/stale' is not a working tree"
    )
    checks["ignores_unrelated_remove_error"] = not is_not_a_working_tree_error(
        "fatal: validation failed, cannot remove working tree: dirty"
    )

    with tempfile.TemporaryDirectory(prefix="worktree-gc-stale-") as tmp:
        root = Path(tmp)
        repo = _init_repo(root)
        stale = _make_complete_mission(repo, "m-stale", created_at="2026-01-01T00:00:00Z")
        live = _make_complete_mission(repo, "m-live", created_at="2026-01-02T00:00:00Z")
        _detach_leave_directory(repo, stale)
        assert stale.exists()
        report = reclaim_mission_worktrees(repo, ancestor_refs=("main",), keep_recent=0)
        stale_entries = [
            item for item in report.get("reclaimed") or [] if item.get("mission_id") == "m-stale"
        ]
        checks["stale_dir_reclaimed"] = (
            report.get("ok") is True
            and not report.get("errors")
            and bool(stale_entries)
            and stale_entries[0].get("stale_not_a_working_tree") is True
            and not stale.exists()
        )
        checks["registered_worktree_still_removed"] = not live.exists()

    with tempfile.TemporaryDirectory(prefix="worktree-gc-error-") as tmp:
        root = Path(tmp)
        report = {"reclaimed": [], "errors": []}
        workspace = root / "locked"
        workspace.mkdir()
        (workspace / "keep.txt").write_text("x\n", encoding="utf-8")
        finish_failed_worktree_remove(
            report,
            {"mission_id": "m-locked", "workspace": str(workspace)},
            workspace,
            subprocess.CompletedProcess(
                ["git", "worktree", "remove"],
                1,
                stdout="",
                stderr="fatal: validation failed, cannot remove working tree: dirty\n",
            ),
        )
        checks["genuine_error_stays_error"] = (
            report["reclaimed"] == []
            and report["errors"][0]["mission_id"] == "m-locked"
            and workspace.exists()
        )

    with tempfile.TemporaryDirectory(prefix="worktree-gc-harvest-") as tmp:
        root = Path(tmp)
        loop_dir = root / ".blackhole-agent" / "unbound"
        loop_dir.mkdir(parents=True)
        (loop_dir / "continuous-loop.json").write_text(
            json.dumps(
                {
                    "last_worktree_gc_error": (
                        "fatal: 'C:/tmp/20260824T162838Z-6e7e5ef4' is not a working tree"
                    )
                }
            )
            + "\n",
            encoding="utf-8",
        )
        event = harvest_worktree_gc_event(
            json.loads((loop_dir / "continuous-loop.json").read_text(encoding="utf-8"))
        )
        fuel = harvest_experience(root, limit=5)
        checks["harvests_sticky_gc_error"] = (
            event is not None
            and event["class_id"] == WORKTREE_GC_FAILED
            and any(item.class_id == WORKTREE_GC_FAILED for item in fuel.candidates)
        )
        _register_proved(root, WORKTREE_GC_RESILIENCE_ID)
        closed_fuel = harvest_experience(root, limit=5)
        checks["proved_closer_drops_class"] = class_is_closed(
            WORKTREE_GC_FAILED, root
        ) is True and not any(
            item.class_id == WORKTREE_GC_FAILED for item in closed_fuel.candidates
        )
        checks["empty_loop_is_not_harvested"] = harvest_worktree_gc_event({}) is None

    checks["schema_version"] = SCHEMA_VERSION == 1
    checks["no_skill_route"] = not legacy_pipeline_was_used()

    ok = all(checks.values())
    if ok:
        ensure_worktree_gc_resilience_capability()
    return {
        "ok": ok,
        "action": "worktree_gc_resilience",
        "checks": checks,
        "passed_count": sum(1 for value in checks.values() if value),
        "check_count": len(checks),
        "used_skill_route_discovery": legacy_pipeline_was_used(),
        "mission_goal": WORKTREE_GC_RESILIENCE_GOAL,
        "done_when": WORKTREE_GC_RESILIENCE_DONE_WHEN,
    }
