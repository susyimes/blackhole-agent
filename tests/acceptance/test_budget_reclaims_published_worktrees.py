"""Outcome probe: preventive storage reclaim removes only verified worktrees.

When the next mission checkout would reach the preventive line,
``authorize_mission_worktree`` removes the older completed published
worktree with ``git worktree remove`` and without ``--force``. The newest
clean completed worktree stays. A dirty completed worktree, an active
mission, and a completed worktree that is not on ``origin/main`` stay.
Below that line the same call removes nothing.

The previous milestone authorizes the checkout and leaves every worktree
on disk, so this probe reports passed=false. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.unbound import UnboundMission, mission_root, save_mission


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return (completed.stdout or "").strip()


def _init_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "budget@test.local")
    _git(repo, "config", "user.name", "Budget Test")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / ".gitignore").write_text("__pycache__/\n*.egg-info/\n", encoding="utf-8")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "seed")
    bare = root / "origin.git"
    _git(repo, "init", "--bare", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "origin", "HEAD:main")
    return repo


def _make_mission(repo: Path, mission_id: str, created_at: str, *, status: str) -> Path:
    parent = repo.parent / f".{repo.name}-unbound-worktrees"
    parent.mkdir(exist_ok=True)
    workspace = parent / mission_id
    branch = f"unbound/probe-{mission_id}"
    _git(repo, "worktree", "add", "-b", branch, str(workspace), "main")
    base_head = _git(workspace, "rev-parse", "HEAD")
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
            goal="probe",
            done_when="probe",
            status=status,
            stage="execution",
            base_head=base_head,
            last_milestone_head=head,
        ),
    )
    return workspace


def _build(root: Path) -> dict[str, Path]:
    repo = _init_repo(root)
    older = _make_mission(repo, "older", "2026-01-01T00:00:00Z", status="complete")
    _git(repo, "push", "origin", "HEAD:main")
    cache = older / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "mod.pyc").write_bytes(b"pyc")
    egg = older / "pkg.egg-info"
    egg.mkdir()
    (egg / "PKG-INFO").write_text("Name: pkg\n", encoding="utf-8")
    newer = _make_mission(repo, "newer", "2026-01-02T00:00:00Z", status="complete")
    _git(repo, "push", "origin", "HEAD:main")
    dirty = _make_mission(repo, "dirty", "2026-01-03T00:00:00Z", status="complete")
    _git(repo, "push", "origin", "HEAD:main")
    (dirty / "stray.txt").write_text("unique leftover\n", encoding="utf-8")
    active = _make_mission(repo, "active", "2026-01-04T00:00:00Z", status="active")
    _git(repo, "push", "origin", "HEAD:main")
    local_only = _make_mission(repo, "local-only", "2026-01-05T00:00:00Z", status="complete")
    return {
        "repo": repo,
        "older": older,
        "newer": newer,
        "dirty": dirty,
        "active": active,
        "local_only": local_only,
    }


def _observe(paths: dict[str, Path], receipt: dict) -> dict[str, object]:
    reclaim = receipt.get("worktree_reclaim") if isinstance(receipt.get("worktree_reclaim"), dict) else {}
    commands = [list(item) for item in reclaim.get("remove_commands") or []]
    forced = bool(reclaim.get("force_removal")) or any(
        part in {"--force", "-f"} for command in commands for part in command
    )
    stray = paths["dirty"] / "stray.txt"
    expansion = receipt.get("expansion") if isinstance(receipt.get("expansion"), dict) else {}
    return {
        "allowed": expansion.get("allowed") is True,
        "older_exists": paths["older"].exists(),
        "newer_exists": paths["newer"].exists(),
        "dirty_exists": paths["dirty"].exists(),
        "stray_exists": stray.is_file(),
        "stray_text": stray.read_text(encoding="utf-8") if stray.is_file() else "",
        "active_exists": paths["active"].exists(),
        "local_only_exists": paths["local_only"].exists(),
        "reclaimed_ids": [item.get("mission_id") for item in reclaim.get("reclaimed") or []],
        "forced_remove": forced,
        "ancestor_refs": list(reclaim.get("ancestor_refs") or []),
        "growth_bytes": expansion.get("additional_bytes"),
    }


def _authorize(repo: Path, *, cap_bytes: int, preventive_bytes: int) -> dict:
    from blackhole_agent import storage_budget as budget

    budget.CAP_BYTES = cap_bytes
    budget.PREVENTIVE_BYTES = preventive_bytes
    try:
        return budget.authorize_mission_worktree(repo)
    except budget.StorageBudgetRefusal as exc:
        receipt = dict(exc.receipt)
        receipt["refused"] = exc.reason
        return receipt


def _pressure(root: Path) -> dict[str, object]:
    from blackhole_agent.storage_budget import measure_roots, mission_checkout_roots

    paths = _build(root)
    measured = int(measure_roots(mission_checkout_roots(paths["repo"]))["logical_bytes"])
    receipt = _authorize(paths["repo"], cap_bytes=10**15, preventive_bytes=measured + 1)
    observed = _observe(paths, receipt)
    observed["measured_bytes"] = measured
    observed["preventive_bytes"] = measured + 1
    return observed


def _idle(root: Path) -> dict[str, object]:
    paths = _build(root)
    receipt = _authorize(paths["repo"], cap_bytes=10**15, preventive_bytes=10**15)
    return _observe(paths, receipt)


def _passed(pressure: dict[str, object], idle: dict[str, object]) -> bool:
    return (
        pressure.get("allowed") is True
        and pressure.get("older_exists") is False
        and pressure.get("newer_exists") is True
        and pressure.get("dirty_exists") is True
        and pressure.get("stray_exists") is True
        and pressure.get("stray_text") == "unique leftover\n"
        and pressure.get("active_exists") is True
        and pressure.get("local_only_exists") is True
        and pressure.get("reclaimed_ids") == ["older"]
        and pressure.get("forced_remove") is False
        and pressure.get("ancestor_refs") == ["origin/main"]
        and idle.get("allowed") is True
        and idle.get("older_exists") is True
        and idle.get("newer_exists") is True
        and idle.get("dirty_exists") is True
        and idle.get("stray_text") == "unique leftover\n"
        and idle.get("active_exists") is True
        and idle.get("local_only_exists") is True
        and idle.get("reclaimed_ids") == []
        and idle.get("forced_remove") is False
    )


def _rmtree(path: Path) -> None:
    def _onerror(function, target, _exc_info) -> None:
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except OSError:
            pass

    if path.exists():
        shutil.rmtree(path, onerror=_onerror)


def main() -> dict[str, object]:
    scratch = Path(tempfile.mkdtemp(prefix="ba-budget-wt-"))
    observed: dict[str, object] = {"family": "budget-worktree-reclaim"}
    try:
        pressure = _pressure(scratch / "pressure")
        idle = _idle(scratch / "idle")
        observed["pressure"] = pressure
        observed["idle"] = idle
        return {"passed": _passed(pressure, idle), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        _rmtree(scratch)


if __name__ == "__main__":
    try:
        result = main()
    except Exception as exc:
        result = {
            "passed": False,
            "observed": {"family": "budget-worktree-reclaim", "error": f"{type(exc).__name__}: {exc}"},
        }
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
