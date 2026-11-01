"""Mission creation must count repository scratch under bh- and ba- prefixes.

Authorization already counts temp children named blackhole- and bh-unbound.
Children named bh-mcp-plugin, bh-fp, bh-acq, and ba-grok are created by this
repository and stay outside that total, so a child that alone meets the cap
still lets mission creation succeed. This probe prints JSON with boolean
passed and nonempty observed, and exits 0 either way.
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


def _sandbox(root: Path, *, child_name: str, child_bytes: int) -> dict[str, str | None]:
    home = root / "home"
    temp = root / "temp"
    home.mkdir(parents=True)
    temp.mkdir()
    if child_name and child_bytes:
        owned = temp / child_name
        owned.mkdir()
        (owned / "temp.bin").write_bytes(b"T" * child_bytes)
    previous = {
        "TEMP": os.environ.get("TEMP"),
        "TMP": os.environ.get("TMP"),
        "USERPROFILE": os.environ.get("USERPROFILE"),
        "HOME": os.environ.get("HOME"),
    }
    os.environ["TEMP"] = str(temp)
    os.environ["TMP"] = str(temp)
    os.environ["USERPROFILE"] = str(home)
    os.environ["HOME"] = str(home)
    return previous


def _restore(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _cap_for(repo: Path) -> int:
    from blackhole_agent.storage_budget import checkout_growth_bytes, measure_roots, mission_checkout_roots

    measured = measure_roots(mission_checkout_roots(repo))
    logical = int(measured["logical_bytes"])
    growth = int(checkout_growth_bytes(measured, repo))
    return logical + growth + 1000


def _attempt(repo: Path, parent: Path, cap_bytes: int) -> dict:
    from blackhole_agent import storage_budget as budget
    from blackhole_agent.unbound import create_mission

    # create_mission reloads the gate when LOADED_CONTROLLER_SHA is not this
    # checkout. Bind it first so the fixture cap survives that reload.
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    budget.LOADED_CONTROLLER_SHA = head.stdout.strip()
    budget.CAP_BYTES = cap_bytes
    budget.PREVENTIVE_BYTES = cap_bytes
    before = (repo / "payload.bin").read_bytes()
    try:
        state_path = create_mission(
            repo_path=repo,
            goal="Probe bh- and ba- scratch in the storage total.",
            done_when="The destination exists only when the combined total is under the cap.",
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


def _case(root: Path, name: str, *, child_name: str) -> dict:
    case_root = root / name
    case_root.mkdir()
    repo = case_root / "repo"
    _init_repo(repo)
    cap_bytes = _cap_for(repo)
    previous = _sandbox(
        case_root,
        child_name=child_name,
        child_bytes=cap_bytes if child_name else 0,
    )
    try:
        observed = _attempt(repo, case_root / "destination", cap_bytes)
    finally:
        _restore(previous)
    observed["cap_bytes"] = cap_bytes
    observed["child_name"] = child_name
    return observed


def _refused(observed: dict) -> bool:
    return (
        observed["created"] is False
        and observed["reason"] == "at_cap"
        and observed["error_type"] == "StorageBudgetRefusal"
        and observed["parent_exists"] is False
        and observed["payload_unchanged"] is True
    )


def _allowed(observed: dict) -> bool:
    return (
        observed["created"] is True
        and observed["workspace_exists"] is True
        and observed["payload_unchanged"] is True
    )


def main() -> None:
    observed: dict = {}
    passed = False
    root = Path(tempfile.mkdtemp(prefix="ba-bh-prefix-gate-"))
    try:
        plugin = _case(root, "plugin", child_name="bh-mcp-plugin-oversize")
        unrelated = _case(root, "unrelated", child_name="notes-oversize")
        observed = {"plugin": plugin, "unrelated": unrelated}
        passed = _refused(plugin) and _allowed(unrelated)
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
