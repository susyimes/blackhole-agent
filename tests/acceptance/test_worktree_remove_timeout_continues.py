"""Outcome probe: one hung worktree remove does not abort the reclaim pass.

Harvested GC on 2026-08-26 died with TimeoutExpired from
``git worktree remove --force`` of mission 20260825T162001Z-581c83d3 after
600 seconds. That exception left every later published checkout untouched.

This probe builds two published completed worktrees. Removal of the
harvested mission id raises TimeoutExpired. The previous milestone lets
that exception escape, so the other checkout stays. The candidate records
the timeout, leaves the hung checkout on disk, does not pass ``--force``,
and still removes the other checkout. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

HUNG_MISSION = "20260825T162001Z-581c83d3"
OTHER_MISSION = "20260825T120000Z-keptpeer"


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
    _git(repo, "config", "user.email", "gc@test.local")
    _git(repo, "config", "user.name", "GC Test")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
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


def _is_worktree_remove(command: list[str]) -> bool:
    return len(command) >= 3 and command[0] == "git" and command[1] == "worktree" and command[2] == "remove"


def exercise() -> dict[str, object]:
    from blackhole_agent.unbound import reclaim_mission_worktrees

    with tempfile.TemporaryDirectory(prefix="bh-wt-timeout-") as directory:
        repo = _init_repo(Path(directory))
        # Newer created_at is reclaimed first. The harvested id must time out
        # before the older published checkout is considered.
        hung = _make_mission(repo, HUNG_MISSION, "2026-08-26T02:16:49Z")
        other = _make_mission(repo, OTHER_MISSION, "2026-08-25T12:00:00Z")
        remove_commands: list[list[str]] = []

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            tokens = [str(part) for part in command]
            if _is_worktree_remove(tokens) and any(HUNG_MISSION in part for part in tokens):
                remove_commands.append(tokens)
                timeout = kwargs.get("timeout")
                seconds = int(timeout) if isinstance(timeout, (int, float)) else 600
                raise subprocess.TimeoutExpired(tokens, seconds)
            return subprocess.run(tokens, **kwargs)  # type: ignore[arg-type]

        escaped = ""
        report: dict[str, object] | None = None
        try:
            report = reclaim_mission_worktrees(
                repo,
                ancestor_refs=("main",),
                keep_recent=0,
                command_runner=runner,
            )
        except subprocess.TimeoutExpired as error:
            escaped = str(error)
        errors = []
        if isinstance(report, dict):
            errors = list(report.get("errors") or [])
        reclaimed = []
        if isinstance(report, dict):
            reclaimed = [str(item.get("mission_id") or "") for item in report.get("reclaimed") or []]
        force_used = any("--force" in command or "-f" in command for command in remove_commands)
        timeout_recorded = any(
            isinstance(item, dict)
            and item.get("mission_id") == HUNG_MISSION
            and item.get("timed_out") is True
            and "timed out" in str(item.get("error") or "").lower()
            and HUNG_MISSION in str(item.get("error") or "")
            for item in errors
        )
        return {
            "escaped": bool(escaped),
            "escape_text": escaped[:400],
            "force_used": force_used,
            "hung_exists": hung.exists(),
            "other_exists": other.exists(),
            "reclaimed": reclaimed,
            "remove_commands": remove_commands,
            "timeout_recorded": timeout_recorded,
        }


def main() -> None:
    observed: dict[str, object] = {}
    try:
        observed = exercise()
        passed = bool(
            observed["escaped"] is False
            and observed["hung_exists"] is True
            and observed["other_exists"] is False
            and observed["timeout_recorded"] is True
            and observed["force_used"] is False
            and observed["reclaimed"] == [OTHER_MISSION]
        )
    except Exception as error:  # noqa: BLE001 - probe must exit 0 for unmet outcomes
        observed = {"probe_error": f"{error.__class__.__name__}: {error}"}
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
