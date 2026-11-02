"""Outcome probe: a mission turn reclaims a published checkout the creator skipped.

The live controller imported its mission creator before publication. The
23:14 storage receipt has no worktree_reclaim key. This probe seeds that
receipt, then runs the turn reclaim. An older completed published checkout
is removed without --force. The newest clean checkout stays. A checkout
that still has a unique untracked source file stays, and that file's bytes
stay. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


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
    _git(repo, "config", "user.email", "turn-reclaim@test.local")
    _git(repo, "config", "user.name", "Turn Reclaim")
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


def _exercise(reclaim) -> dict[str, object]:
    scratch = tempfile.TemporaryDirectory(prefix="turn-checkout-reclaim-")
    observed: dict[str, object] = {}
    try:
        repo = _init_repo(Path(scratch.name))
        older = _make_mission(repo, "older", "2026-01-01T00:00:00Z")
        newer = _make_mission(repo, "newer", "2026-01-02T00:00:00Z")
        dirty = _make_mission(repo, "dirty", "2026-01-03T00:00:00Z")
        source = dirty / "notes.py"
        source.write_text('VALUE = "keep"\n', encoding="utf-8")
        receipt_path = repo / ".blackhole-agent" / "unbound" / "storage-budget.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps({"bytes_after": 11, "cleanup_targets": []}),
            encoding="utf-8",
        )
        compact = reclaim(repo)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        reclaim_record = receipt.get("worktree_reclaim")
        reclaimed = reclaim_record.get("reclaimed") if isinstance(reclaim_record, dict) else []
        commands = [list(item.get("remove_command") or []) for item in reclaimed or []]
        forced = any("--force" in command or "-f" in command for command in commands)
        removed_ids = [item.get("mission_id") for item in reclaimed or [] if item.get("removed") is True]
        cleanup = receipt.get("cleanup_targets") or []
        cleanup_forces = [item.get("force") for item in cleanup if isinstance(item, dict)]
        observed.update(
            {
                "older_exists": older.exists(),
                "newer_exists": newer.exists(),
                "dirty_exists": dirty.exists(),
                "source_text": source.read_text(encoding="utf-8") if source.is_file() else "",
                "bytes_after": receipt.get("bytes_after"),
                "additional_bytes": (receipt.get("expansion") or {}).get("additional_bytes")
                if isinstance(receipt.get("expansion"), dict)
                else None,
                "removed_ids": removed_ids,
                "returned_removed_ids": [
                    item.get("mission_id")
                    for item in (compact.get("reclaimed") or [])
                    if item.get("removed") is True
                ],
                "forced_remove": forced,
                "cleanup_forces": cleanup_forces,
                "kept_reasons": {
                    item.get("mission_id"): item.get("reason")
                    for item in (reclaim_record.get("kept") or [])
                    if isinstance(reclaim_record, dict) and isinstance(item, dict)
                },
            }
        )
        passed = (
            observed["older_exists"] is False
            and observed["newer_exists"] is True
            and observed["dirty_exists"] is True
            and observed["source_text"] == 'VALUE = "keep"\n'
            and isinstance(observed["bytes_after"], int)
            and observed["bytes_after"] > 11
            and isinstance(observed["additional_bytes"], int)
            and observed["additional_bytes"] > 0
            and observed["removed_ids"] == ["older"]
            and observed["returned_removed_ids"] == ["older"]
            and forced is False
            and cleanup_forces == [False]
        )
        return {"passed": passed, "observed": observed}
    except Exception as error:
        observed["error"] = f"{type(error).__name__}: {error}"
        return {"passed": False, "observed": observed}
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
                    "observed": "the mission turn leaves the completed checkout in place and the receipt has no worktree_reclaim key",
                }
            )
        )
        return 0
    print(json.dumps(_exercise(reclaim)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
