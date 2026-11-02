"""Outcome probe: a supervisor wake must not force-delete its candidate.

A clean detached candidate whose commit is already on origin/main is removed
with git worktree remove and without --force. An uncommitted file, a commit
that is not on origin/main, and a candidate whose directory a live process is
using all stay on disk.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
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


def _init_published_repo(root: Path) -> Path:
    remote = root / "origin.git"
    repo = root / "blackhole-agent"
    remote.mkdir()
    repo.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "wake@test.local")
    _git(repo, "config", "user.name", "Wake Test")
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "HEAD:refs/heads/main")
    _git(repo, "fetch", "origin")
    return repo


def _exercise() -> dict:
    from blackhole_agent.supervisor import SupervisorConfig, run_wake_once

    observed: dict = {"commands": [], "error": ""}
    holders: list[subprocess.Popen] = []
    scratch: tempfile.TemporaryDirectory[str] | None = tempfile.TemporaryDirectory(prefix="bh-supervisor-wake-")
    try:
        root = Path(scratch.name)
        repo = _init_published_repo(root)
        parent = root / "supervisor-worktrees"
        mode = {"kind": "clean"}

        def runner(command, **kwargs):
            observed["commands"].append([str(part) for part in command])
            if not command or command[0] != "git":
                workspace = Path(kwargs.get("cwd") or repo)
                if mode["kind"] == "dirty":
                    (workspace / "local-note.txt").write_text("keep this note\n", encoding="utf-8")
                elif mode["kind"] == "unpublished":
                    (workspace / "extra.txt").write_text("not pushed\n", encoding="utf-8")
                    _git(workspace, "add", "extra.txt")
                    _git(workspace, "commit", "-m", "unpublished")
                elif mode["kind"] == "busy":
                    holders.append(
                        subprocess.Popen(
                            [sys.executable, "-c", "import time; time.sleep(60)"],
                            cwd=workspace,
                        )
                    )
                    time.sleep(0.4)
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
            return subprocess.run(
                command,
                cwd=kwargs.get("cwd"),
                capture_output=True,
                text=True,
                encoding=kwargs.get("encoding") or "utf-8",
                errors=kwargs.get("errors") or "replace",
                timeout=kwargs.get("timeout") or 120,
                check=False,
            )

        def wake(kind: str):
            mode["kind"] = kind
            config = SupervisorConfig(
                repo_path=repo,
                output_dir=repo / ".blackhole-agent" / "supervisor",
                worktree_parent_dir=parent,
                evolution_mode="codex",
                model="gpt-5.5",
                prefer_capability_compounder=False,
                commit_successful_changes=False,
                promote_successful_changes=False,
                push_promotions=False,
                require_rollback_artifact=False,
                cleanup_candidate_worktree=True,
                use_candidate_worktree=True,
            )
            record = run_wake_once(config, command_runner=runner)
            path = Path(record.worktree_result.path) if record.worktree_result else Path()
            return record, path

        clean_record, clean_path = wake("clean")
        time.sleep(1.1)
        dirty_record, dirty_path = wake("dirty")
        time.sleep(1.1)
        unpublished_record, unpublished_path = wake("unpublished")
        time.sleep(1.1)
        busy_record, busy_path = wake("busy")
        force_commands = [
            command for command in observed["commands"] if "--force" in command or "-f" in command
        ]
        observed = {
            "clean_exists": clean_path.exists(),
            "clean_removed": bool(clean_record.worktree_result and clean_record.worktree_result.removed),
            "dirty_exists": dirty_path.exists(),
            "dirty_note": (dirty_path / "local-note.txt").is_file() if dirty_path.exists() else False,
            "dirty_removed": bool(dirty_record.worktree_result and dirty_record.worktree_result.removed),
            "unpublished_exists": unpublished_path.exists(),
            "unpublished_removed": bool(
                unpublished_record.worktree_result and unpublished_record.worktree_result.removed
            ),
            "busy_exists": busy_path.exists(),
            "busy_removed": bool(busy_record.worktree_result and busy_record.worktree_result.removed),
            "busy_stderr": (
                busy_record.worktree_result.stderr_tail if busy_record.worktree_result else ""
            ),
            "force_commands": force_commands,
            "clean_stderr": (
                clean_record.worktree_result.stderr_tail if clean_record.worktree_result else ""
            ),
        }
        passed = (
            observed["clean_exists"] is False
            and observed["clean_removed"] is True
            and observed["dirty_exists"] is True
            and observed["dirty_note"] is True
            and observed["dirty_removed"] is False
            and observed["unpublished_exists"] is True
            and observed["unpublished_removed"] is False
            and observed["busy_exists"] is True
            and observed["busy_removed"] is False
            and observed["force_commands"] == []
        )
        return {"passed": passed, "observed": observed}
    except Exception as error:
        return {"passed": False, "observed": {"error": f"{type(error).__name__}: {error}"}}
    finally:
        for holder in holders:
            holder.kill()
            try:
                holder.wait(timeout=10)
            except Exception:
                pass
        time.sleep(0.3)
        if scratch is not None:
            try:
                scratch.cleanup()
            except Exception:
                pass


def main() -> int:
    print(json.dumps(_exercise()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
