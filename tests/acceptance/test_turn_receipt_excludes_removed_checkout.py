"""Outcome probe: a mission-turn reclaim stops counting a removed checkout.

The 2026-11-01 23:47 storage receipt records removed worktrees while
bytes_after still equals bytes_before and expansion.additional_bytes is 0.
This probe seeds that receipt. One case has no worktree_reclaim key, so the
turn removes the checkout and must remeasure. The other case already records
the removal while the checkout is gone and the after-figure still names it.
Both outcomes exit 0. A checkout with a unique untracked source file stays.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

STALE_BYTES = 9_000_000_000


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
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "receipt-remeasure@test.local")
    _git(repo, "config", "user.name", "Receipt Remeasure")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    bare = root / "origin.git"
    _git(repo, "init", "--bare", str(bare))
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "origin", "HEAD:main")
    return repo


def _make_mission(repo: Path, mission_id: str, created_at: str) -> Path:
    from blackhole_agent.unbound import UnboundMission, mission_root, save_mission

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
    _git(repo, "push", "origin", "HEAD:main")
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
            status="complete",
            stage="execution",
            base_head=base_head,
            last_milestone_head=head,
        ),
    )
    return workspace


def _logical_file_bytes(root: Path) -> int:
    if not root.exists() and not root.is_symlink():
        return 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        kept: list[str] = []
        for name in dirnames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            total += os.path.getsize(path)
    return total


def _non_git_bytes(repo: Path) -> int:
    total = 0
    for dirpath, dirnames, filenames in os.walk(repo, followlinks=False):
        if os.path.abspath(dirpath) == os.path.abspath(repo):
            dirnames[:] = [name for name in dirnames if name != ".git" and not os.path.islink(os.path.join(dirpath, name))]
        else:
            dirnames[:] = [name for name in dirnames if not os.path.islink(os.path.join(dirpath, name))]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            total += os.path.getsize(path)
    return total


def _child_names(receipt: dict) -> set[str]:
    names: set[str] = set()
    block = receipt.get("measurement_after")
    if not isinstance(block, dict):
        return names
    for root in block.get("roots") or []:
        if not isinstance(root, dict):
            continue
        for child in root.get("top_children") or []:
            if isinstance(child, dict) and child.get("name"):
                names.add(str(child["name"]))
    return names


def _seed_receipt(repo: Path, worktree_parent: Path, *, reclaim: dict | None, counted_name: str) -> Path:
    receipt_path = repo / ".blackhole-agent" / "unbound" / "storage-budget.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "bytes_before": STALE_BYTES,
        "bytes_after": STALE_BYTES,
        "file_count_before": 800000,
        "file_count_after": 800000,
        "expansion": {
            "allowed": True,
            "reason": "within_cap",
            "additional_bytes": 0,
            "cap_satisfied": True,
        },
        "measurement_after": {
            "logical_bytes": STALE_BYTES,
            "roots": [
                {
                    "root": str(worktree_parent),
                    "top_children": [
                        {"name": counted_name, "logical_bytes": STALE_BYTES - 1000, "files": 10}
                    ],
                }
            ],
        },
        "roots": [str(repo), str(worktree_parent)],
        "cleanup_targets": [],
    }
    if reclaim is not None:
        payload["worktree_reclaim"] = reclaim
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    return receipt_path


def _fresh_measurement(receipt: dict, receipt_path: Path, old_size: int, roots: list[Path]) -> dict[str, object]:
    new_size = receipt_path.stat().st_size if receipt_path.is_file() else 0
    logical_now = sum(_logical_file_bytes(root) for root in roots)
    non_git_now = _non_git_bytes(roots[0])
    expected_after = logical_now - new_size + old_size
    expected_growth = non_git_now - new_size + old_size
    expansion = receipt.get("expansion") if isinstance(receipt.get("expansion"), dict) else {}
    return {
        "bytes_after": receipt.get("bytes_after"),
        "bytes_before": receipt.get("bytes_before"),
        "additional_bytes": expansion.get("additional_bytes"),
        "expected_after": expected_after,
        "expected_growth": expected_growth,
        "child_names": sorted(_child_names(receipt)),
        "forced": False,
    }


def _case_absent(reclaim) -> dict[str, object]:
    scratch = tempfile.TemporaryDirectory(prefix="turn-receipt-absent-")
    try:
        repo = _init_repo(Path(scratch.name))
        older = _make_mission(repo, "older", "2026-01-01T00:00:00Z")
        newer = _make_mission(repo, "newer", "2026-01-02T00:00:00Z")
        dirty = _make_mission(repo, "dirty", "2026-01-03T00:00:00Z")
        source = dirty / "notes.py"
        source.write_text('VALUE = "keep"\n', encoding="utf-8")
        parent = older.parent
        receipt_path = _seed_receipt(repo, parent, reclaim=None, counted_name="older")
        old_size = receipt_path.stat().st_size
        compact = reclaim(repo)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        record = receipt.get("worktree_reclaim") if isinstance(receipt.get("worktree_reclaim"), dict) else {}
        commands = [list(item.get("remove_command") or []) for item in record.get("reclaimed") or []]
        forced = any("--force" in command or "-f" in command for command in commands)
        measured = _fresh_measurement(receipt, receipt_path, old_size, [repo, parent])
        measured["forced"] = forced
        measured.update(
            {
                "older_exists": older.exists(),
                "newer_exists": newer.exists(),
                "dirty_exists": dirty.exists(),
                "source_text": source.read_text(encoding="utf-8") if source.is_file() else "",
                "removed_ids": [
                    item.get("mission_id")
                    for item in (record.get("reclaimed") or [])
                    if item.get("removed") is True
                ],
                "returned_removed_ids": [
                    item.get("mission_id")
                    for item in (compact.get("reclaimed") or [])
                    if isinstance(compact, dict) and item.get("removed") is True
                ],
            }
        )
        passed = (
            measured["older_exists"] is False
            and measured["newer_exists"] is True
            and measured["dirty_exists"] is True
            and measured["source_text"] == 'VALUE = "keep"\n'
            and measured["bytes_before"] == STALE_BYTES
            and measured["bytes_after"] == measured["expected_after"]
            and isinstance(measured["bytes_after"], int)
            and measured["bytes_after"] < STALE_BYTES
            and measured["additional_bytes"] == measured["expected_growth"]
            and isinstance(measured["additional_bytes"], int)
            and measured["additional_bytes"] > 0
            and "older" not in measured["child_names"]
            and measured["removed_ids"] == ["older"]
            and measured["returned_removed_ids"] == ["older"]
            and forced is False
        )
        return {"passed": passed, "observed": measured}
    except Exception as error:
        return {"passed": False, "observed": {"error": f"{type(error).__name__}: {error}"}}
    finally:
        scratch.cleanup()


def _case_already_recorded(reclaim) -> dict[str, object]:
    scratch = tempfile.TemporaryDirectory(prefix="turn-receipt-stale-")
    try:
        repo = _init_repo(Path(scratch.name))
        older = _make_mission(repo, "older", "2026-01-01T00:00:00Z")
        parent = older.parent
        _git(repo, "worktree", "remove", str(older))
        receipt_path = _seed_receipt(
            repo,
            parent,
            reclaim={
                "ok": True,
                "force_removal": False,
                "keep_recent": 1,
                "reclaimed": [
                    {
                        "mission_id": "older",
                        "workspace": str(older),
                        "removed": True,
                        "remove_command": ["git", "worktree", "remove", str(older)],
                    }
                ],
                "kept": [],
                "errors": [],
            },
            counted_name="older",
        )
        old_size = receipt_path.stat().st_size
        reclaim(repo)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        measured = _fresh_measurement(receipt, receipt_path, old_size, [repo, parent])
        measured["older_exists"] = older.exists()
        commands = [
            list(item.get("remove_command") or [])
            for item in (receipt.get("worktree_reclaim") or {}).get("reclaimed") or []
            if isinstance(item, dict)
        ]
        measured["forced"] = any("--force" in command or "-f" in command for command in commands)
        passed = (
            measured["older_exists"] is False
            and measured["bytes_before"] == STALE_BYTES
            and measured["bytes_after"] == measured["expected_after"]
            and isinstance(measured["bytes_after"], int)
            and measured["bytes_after"] < STALE_BYTES
            and measured["additional_bytes"] == measured["expected_growth"]
            and isinstance(measured["additional_bytes"], int)
            and measured["additional_bytes"] > 0
            and "older" not in measured["child_names"]
            and measured["forced"] is False
        )
        return {"passed": passed, "observed": measured}
    except Exception as error:
        return {"passed": False, "observed": {"error": f"{type(error).__name__}: {error}"}}
    finally:
        scratch.cleanup()


def main() -> int:
    try:
        import blackhole_agent.storage_budget as storage_budget
    except ImportError as error:
        print(json.dumps({"passed": False, "observed": f"import failed: {error}"}))
        return 0
    reclaim = getattr(storage_budget, "reclaim_published_checkouts_on_turn", None)
    if not callable(reclaim):
        print(
            json.dumps(
                {
                    "passed": False,
                    "observed": "the mission turn leaves bytes_after counting the removed checkout and additional_bytes at 0",
                }
            )
        )
        return 0
    absent = _case_absent(reclaim)
    recorded = _case_already_recorded(reclaim)
    passed = absent.get("passed") is True and recorded.get("passed") is True
    print(
        json.dumps(
            {
                "passed": passed,
                "observed": {
                    "absent_key": absent.get("observed"),
                    "already_recorded": recorded.get("observed"),
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
