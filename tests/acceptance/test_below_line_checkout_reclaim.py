"""Outcome probe: below-line authorization reclaims a finished checkout.

The live launcher disables publication reclamation. A measurement far below
the preventive line must still remove the older clean completed published
checkout with ``git worktree remove`` and without ``--force``. The newest
clean checkout stays. A dirty checkout, an active mission, and an unpublished
checkout stay, including their unique files. An incomplete measurement
removes nothing.

The previous milestone leaves the older checkout on disk below the line, so
this probe reports passed=false. Both outcomes exit 0.
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
        "refused": receipt.get("refused"),
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
        "preventive_bytes": receipt.get("preventive_bytes"),
        "bytes_before": receipt.get("bytes_before"),
    }


def _authorize(repo: Path) -> dict:
    from blackhole_agent import storage_budget as budget

    budget.CAP_BYTES = 10**15
    budget.PREVENTIVE_BYTES = 10**15
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
        return budget.authorize_mission_worktree(repo)
    except budget.StorageBudgetRefusal as exc:
        receipt = dict(exc.receipt)
        receipt["refused"] = exc.reason
        return receipt
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _below_line(root: Path) -> dict[str, object]:
    paths = _build(root)
    receipt = _authorize(paths["repo"])
    observed = _observe(paths, receipt)
    observed["below_line"] = (
        isinstance(observed.get("bytes_before"), int)
        and isinstance(observed.get("preventive_bytes"), int)
        and int(observed["bytes_before"]) < int(observed["preventive_bytes"])
    )
    return observed


def _incomplete(root: Path) -> dict[str, object]:
    from blackhole_agent import storage_budget as budget

    paths = _build(root)
    original = budget.measure_roots

    def incomplete(roots):
        payload = dict(original(roots))
        payload["complete"] = False
        payload["unmeasured_owned_count"] = 1
        payload["unmeasured_owned"] = [{"path": "synthetic", "reason": "probe"}]
        return payload

    budget.measure_roots = incomplete
    try:
        receipt = _authorize(paths["repo"])
    finally:
        budget.measure_roots = original
    observed = _observe(paths, receipt)
    observed["measurement_incomplete"] = receipt.get("refused") == "measurement_incomplete" or (
        isinstance(receipt.get("expansion"), dict)
        and receipt["expansion"].get("reason") == "measurement_incomplete"
    )
    return observed


def _passed(below: dict[str, object], incomplete: dict[str, object]) -> bool:
    return (
        below.get("below_line") is True
        and below.get("allowed") is True
        and below.get("older_exists") is False
        and below.get("newer_exists") is True
        and below.get("dirty_exists") is True
        and below.get("stray_exists") is True
        and below.get("stray_text") == "unique leftover\n"
        and below.get("active_exists") is True
        and below.get("local_only_exists") is True
        and below.get("reclaimed_ids") == ["older"]
        and below.get("forced_remove") is False
        and below.get("ancestor_refs") == ["origin/main"]
        and incomplete.get("older_exists") is True
        and incomplete.get("newer_exists") is True
        and incomplete.get("dirty_exists") is True
        and incomplete.get("stray_text") == "unique leftover\n"
        and incomplete.get("active_exists") is True
        and incomplete.get("local_only_exists") is True
        and incomplete.get("reclaimed_ids") == []
        and incomplete.get("forced_remove") is False
        and incomplete.get("measurement_incomplete") is True
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
    scratch = Path(tempfile.mkdtemp(prefix="ba-below-line-wt-"))
    observed: dict[str, object] = {"family": "below-line-checkout-reclaim"}
    try:
        below = _below_line(scratch / "below")
        incomplete = _incomplete(scratch / "incomplete")
        observed["below_line"] = below
        observed["incomplete"] = incomplete
        return {"passed": _passed(below, incomplete), "observed": observed}
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
            "observed": {
                "family": "below-line-checkout-reclaim",
                "error": f"{type(exc).__name__}: {exc}",
            },
        }
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
