"""Outcome probe: a stale storage gate is reimported after publication.

The live controller imports the storage gate at process start. Publication
fast-forwards main before the next mission create, so a reload that runs only
when this call moves HEAD keeps that imported gate. The 2026-11-01 18:47
receipt therefore has no worktree_reclaim key, and a removable completed
checkout stays on disk.

This probe installs that stale gate, points its recorded sha at a checkout
the process did not import, and asks for the published gate while adoption
does not move HEAD. The published gate must remove the older clean completed
checkout with git worktree remove and without --force. The newer clean
checkout, a dirty checkout, an active mission, and an unpublished checkout
stay. A process that still runs the stale gate leaves the older checkout in
place, so the same probe reports passed false. Both outcomes exit 0.
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
    (repo / ".gitignore").write_text(
        "__pycache__/\n*.egg-info/\n.blackhole-agent/\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "README.md")
    _git(repo, "commit", "-m", "seed")
    bare = root / "origin.git"
    _git(repo, "init", "--bare", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "origin", "HEAD:main")
    return repo


def _make_mission(
    repo: Path,
    mission_id: str,
    created_at: str,
    *,
    status: str,
    merge: bool = True,
) -> Path:
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
    if merge:
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
    newer = _make_mission(repo, "newer", "2026-01-02T00:00:00Z", status="complete")
    _git(repo, "push", "origin", "HEAD:main")
    dirty = _make_mission(repo, "dirty", "2026-01-03T00:00:00Z", status="complete")
    _git(repo, "push", "origin", "HEAD:main")
    (dirty / "stray.txt").write_text("unique leftover\n", encoding="utf-8")
    active = _make_mission(repo, "active", "2026-01-04T00:00:00Z", status="active")
    _git(repo, "push", "origin", "HEAD:main")
    local_only = _make_mission(
        repo,
        "local-only",
        "2026-01-05T00:00:00Z",
        status="complete",
        merge=False,
    )
    return {
        "repo": repo,
        "older": older,
        "newer": newer,
        "dirty": dirty,
        "active": active,
        "local_only": local_only,
    }


def _stale_gate(repo_path: Path) -> dict[str, object]:
    _stale_gate.ran = True
    return {
        "expansion": {"allowed": True, "reason": "stale_gate", "cap_satisfied": True},
        "bytes_before": 0,
        "bytes_after": 0,
        "preventive_bytes": 10**15,
        "cap_bytes": 10**15,
        "worktree_reclaim": {"reclaimed": [], "force_removal": False, "remove_commands": []},
        "repo_path": str(repo_path),
    }


_stale_gate.ran = False


def _authorize(module: object, repo: Path) -> dict:
    module.CAP_BYTES = 10**15
    module.PREVENTIVE_BYTES = 10**15
    home = repo.parent / "empty-home"
    temp = repo.parent / "empty-temp"
    home.mkdir(exist_ok=True)
    temp.mkdir(exist_ok=True)
    previous = {key: os.environ.get(key) for key in ("TEMP", "TMP", "USERPROFILE", "HOME")}
    os.environ["TEMP"] = str(temp)
    os.environ["TMP"] = str(temp)
    os.environ["USERPROFILE"] = str(home)
    os.environ["HOME"] = str(home)
    try:
        try:
            receipt = module.authorize_mission_worktree(repo)
        except module.StorageBudgetRefusal as exc:
            receipt = dict(exc.receipt)
            receipt["refused"] = exc.reason
        return receipt if isinstance(receipt, dict) else {"receipt_type": type(receipt).__name__}
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _observe(paths: dict[str, Path], receipt: dict, *, reimported: bool) -> dict[str, object]:
    reclaim = receipt.get("worktree_reclaim") if isinstance(receipt.get("worktree_reclaim"), dict) else {}
    commands = [list(item) for item in reclaim.get("remove_commands") or []]
    forced = bool(reclaim.get("force_removal")) or any(
        part in {"--force", "-f"} for command in commands for part in command
    )
    stray = paths["dirty"] / "stray.txt"
    return {
        "reimported": reimported,
        "stale_gate_ran": bool(getattr(_stale_gate, "ran", False)),
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
        "loaded_sha": str(getattr(receipt, "loaded_sha", "") or ""),
    }


def _passed(observed: dict[str, object]) -> bool:
    return (
        observed.get("reimported") is True
        and observed.get("stale_gate_ran") is False
        and observed.get("older_exists") is False
        and observed.get("newer_exists") is True
        and observed.get("dirty_exists") is True
        and observed.get("stray_exists") is True
        and observed.get("stray_text") == "unique leftover\n"
        and observed.get("active_exists") is True
        and observed.get("local_only_exists") is True
        and observed.get("reclaimed_ids") == ["older"]
        and observed.get("forced_remove") is False
        and observed.get("ancestor_refs") == ["origin/main"]
        and observed.get("adoption_reason") == "already_current"
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
    scratch = Path(tempfile.mkdtemp(prefix="ba-stale-gate-"))
    observed: dict[str, object] = {"family": "published-storage-gate-reimport"}
    try:
        paths = _build(scratch)
        try:
            from blackhole_agent.controller_adoption import reimport_published_storage_budget
        except ImportError:
            observed.update(
                {
                    "reimported": False,
                    "stale_gate_ran": False,
                    "older_exists": paths["older"].exists(),
                    "newer_exists": paths["newer"].exists(),
                    "reason": "stale_gate_kept",
                }
            )
            return {"passed": False, "observed": observed}

        import blackhole_agent.storage_budget as budget

        from blackhole_agent.controller_adoption import adopt_remote_controller

        adoption = adopt_remote_controller(paths["repo"])
        budget.LOADED_CONTROLLER_SHA = "imported-before-publication"
        budget.authorize_mission_worktree = _stale_gate
        module = reimport_published_storage_budget(paths["repo"])
        reimported = module.authorize_mission_worktree is not _stale_gate
        receipt = _authorize(module, paths["repo"])
        receipt_observed = _observe(paths, receipt, reimported=reimported)
        receipt_observed["bound_sha_matches_head"] = (
            str(getattr(module, "LOADED_CONTROLLER_SHA", "") or "")
            == _git(paths["repo"], "rev-parse", "HEAD")
        )
        receipt_observed["adoption_reason"] = str(adoption.get("reason") or "")
        receipt_observed["adoption_moved"] = bool(adoption.get("moved"))
        observed.update(receipt_observed)
        return {"passed": _passed(observed), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        _rmtree(scratch)


if __name__ == "__main__":
    print(json.dumps(main()))
