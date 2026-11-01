"""Outcome probe: a timed-out worktree removal is not started again.

Harvested GC on 2026-08-26 timed out in ``git worktree remove`` for mission
20260825T162001Z-581c83d3. The same-pass continuation reclaims other
checkouts, but the next reclaim still starts that 600 second remove.

This probe runs two passes. The first removal of the harvested mission
raises TimeoutExpired. The second pass must reclaim a different published
checkout without calling ``git worktree remove`` on the harvested mission
and without ``--force``. The previous milestone calls remove again, so
this probe reports passed=false. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

HUNG_MISSION = "20260825T162001Z-581c83d3"
FIRST_PEER = "20260825T120000Z-keptpeer"
SECOND_PEER = "20260826T120000Z-nextpeer"


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


def _targets(command: list[str], mission_id: str) -> bool:
    return _is_worktree_remove(command) and any(mission_id in part for part in command)


def exercise() -> dict[str, object]:
    from blackhole_agent.unbound import reclaim_mission_worktrees

    with tempfile.TemporaryDirectory(prefix="bh-wt-defer-") as directory:
        repo = _init_repo(Path(directory))
        hung = _make_mission(repo, HUNG_MISSION, "2026-08-26T02:16:49Z")
        first_peer = _make_mission(repo, FIRST_PEER, "2026-08-25T12:00:00Z")
        first_commands: list[list[str]] = []
        second_commands: list[list[str]] = []
        phase = {"pass": 1}

        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            tokens = [str(part) for part in command]
            bucket = first_commands if phase["pass"] == 1 else second_commands
            if _is_worktree_remove(tokens):
                bucket.append(tokens)
            if _targets(tokens, HUNG_MISSION):
                timeout = kwargs.get("timeout")
                seconds = int(timeout) if isinstance(timeout, (int, float)) else 600
                raise subprocess.TimeoutExpired(tokens, seconds)
            return subprocess.run(tokens, **kwargs)  # type: ignore[arg-type]

        first = reclaim_mission_worktrees(
            repo,
            ancestor_refs=("main",),
            keep_recent=0,
            command_runner=runner,
        )
        second_peer = _make_mission(repo, SECOND_PEER, "2026-08-26T12:00:00Z")
        phase["pass"] = 2
        second = reclaim_mission_worktrees(
            repo,
            ancestor_refs=("main",),
            keep_recent=0,
            command_runner=runner,
        )
        all_commands = first_commands + second_commands
        force_used = any("--force" in command or "-f" in command for command in all_commands)
        second_hung = [command for command in second_commands if _targets(command, HUNG_MISSION)]
        second_reclaimed = [
            str(item.get("mission_id") or "") for item in second.get("reclaimed") or []
        ]
        return {
            "first_hung_calls": sum(1 for command in first_commands if _targets(command, HUNG_MISSION)),
            "first_peer_exists": first_peer.exists(),
            "first_reclaimed": [
                str(item.get("mission_id") or "") for item in first.get("reclaimed") or []
            ],
            "force_used": force_used,
            "hung_exists": hung.exists(),
            "second_hung_calls": len(second_hung),
            "second_peer_exists": second_peer.exists(),
            "second_reclaimed": second_reclaimed,
            "skipped_reason": [
                str(item.get("reason") or "")
                for item in second.get("kept") or []
                if item.get("mission_id") == HUNG_MISSION
            ],
        }


def main() -> None:
    observed: dict[str, object] = {}
    try:
        observed = exercise()
        passed = bool(
            observed["first_hung_calls"] == 1
            and observed["first_peer_exists"] is False
            and observed["first_reclaimed"] == [FIRST_PEER]
            and observed["second_hung_calls"] == 0
            and observed["second_peer_exists"] is False
            and observed["second_reclaimed"] == [SECOND_PEER]
            and observed["hung_exists"] is True
            and observed["force_used"] is False
            and observed["skipped_reason"] == ["remove_previously_timed_out"]
        )
    except Exception as error:  # noqa: BLE001 - probe must exit 0 for unmet outcomes
        observed = {"probe_error": f"{error.__class__.__name__}: {error}"}
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
