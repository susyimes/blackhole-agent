"""Mission creation must refuse a worktree when checkout roots are already at the cap.

The previous milestone creates the worktree even when the storage cap is one
byte. This probe uses the same create_mission call for both outcomes. It
prints JSON with boolean passed and nonempty observed, and exits 0 either way.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


PAYLOAD = b"PAYLOAD-BYTES-UNCHANGED"


def _run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _run(["git", "init", "-b", "main"], repo)
    _run(["git", "config", "user.name", "Blackhole Probe"], repo)
    _run(["git", "config", "user.email", "blackhole@example.invalid"], repo)
    (repo / "payload.bin").write_bytes(PAYLOAD)
    _run(["git", "add", "payload.bin"], repo)
    _run(["git", "commit", "-m", "payload"], repo)


def _command_runner(command, **kwargs):
    argv = list(command)
    name = Path(str(argv[0])).name.lower() if argv else ""
    if name.startswith("uv"):
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    return subprocess.run(command, **kwargs)


def _remove(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_file() or path.is_symlink():
        try:
            os.chmod(path, stat.S_IWRITE)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        return
    for child in list(path.iterdir()):
        _remove(child)
    path.rmdir()


def _attempt(repo: Path, parent: Path, cap_bytes: int) -> dict:
    from blackhole_agent import storage_budget as budget
    from blackhole_agent.unbound import create_mission

    budget.CAP_BYTES = cap_bytes
    budget.PREVENTIVE_BYTES = cap_bytes
    before = (repo / "payload.bin").read_bytes()
    try:
        state_path = create_mission(
            repo_path=repo,
            goal="Probe the mission worktree storage gate.",
            done_when="The worktree exists only when the measurement is under the cap.",
            kernel="grok",
            target_branch="main",
            branch_prefix="unbound",
            output_dir=repo / "mission-output",
            worktree_parent=parent,
            command_runner=_command_runner,
        )
        workspace = ""
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            workspace = str(payload.get("workspace_path") or "")
        except (OSError, json.JSONDecodeError):
            workspace = ""
        return {
            "created": True,
            "reason": "",
            "error_type": "",
            "parent_exists": parent.exists(),
            "workspace_exists": bool(workspace) and Path(workspace).is_dir(),
            "payload_unchanged": (repo / "payload.bin").read_bytes() == before,
        }
    except Exception as exc:
        return {
            "created": False,
            "reason": str(getattr(exc, "reason", "")),
            "error_type": type(exc).__name__,
            "parent_exists": parent.exists(),
            "workspace_exists": False,
            "payload_unchanged": (repo / "payload.bin").read_bytes() == before,
        }


def main() -> None:
    observed: dict = {}
    passed = False
    root = Path(tempfile.mkdtemp(prefix="ba-wt-gate-"))
    try:
        at_repo = root / "at-cap"
        under_repo = root / "under-cap"
        _init_repo(at_repo)
        _init_repo(under_repo)
        at_parent = root / "at-worktrees"
        under_parent = root / "under-worktrees"
        at_cap = _attempt(at_repo, at_parent, 1)
        under_cap = _attempt(under_repo, under_parent, 50_000_000)
        observed = {"at_cap": at_cap, "under_cap": under_cap}
        passed = (
            at_cap["created"] is False
            and at_cap["reason"] == "at_cap"
            and at_cap["error_type"] == "StorageBudgetRefusal"
            and at_cap["parent_exists"] is False
            and at_cap["payload_unchanged"] is True
            and under_cap["created"] is True
            and under_cap["workspace_exists"] is True
            and under_cap["payload_unchanged"] is True
        )
    except Exception as exc:
        observed = {"probe_error": f"{type(exc).__name__}: {exc}"}
        passed = False
    finally:
        try:
            _remove(root)
        except OSError:
            pass
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
