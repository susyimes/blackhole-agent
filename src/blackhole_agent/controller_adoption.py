"""Move the controller checkout forward to a commit already published.

The continuous loop pushes milestone commits to ``origin/main`` and leaves
the controller working tree on the older local ``main``. The editable
install loads that working tree, so the next mission create still executes
the pre-publication modules. A clean checkout that is a strict ancestor of
the published commit is fast-forwarded with ``git merge --ff-only``. A dirty
tree, a detached checkout, and a commit that is not a descendant stay where
they are. This module never resets, force-pushes, or deletes a worktree.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

_IMPORT_SCRIPT = """
import importlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "src"))
module = importlib.import_module(sys.argv[2])
value = getattr(module, sys.argv[3])
sys.stdout.write(str(value))
"""


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_MERGE_AUTOEDIT"] = "no"
    return env


def _run(
    command: Sequence[str],
    cwd: Path,
    command_runner: Callable[..., Any],
) -> subprocess.CompletedProcess[str]:
    if command_runner is subprocess.run:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    else:
        completed = command_runner(
            list(command),
            cwd=cwd,
            env=_git_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    if not isinstance(getattr(completed, "stdout", None), str):
        completed.stdout = "" if completed.stdout is None else str(completed.stdout)
    if not isinstance(getattr(completed, "stderr", None), str):
        completed.stderr = "" if completed.stderr is None else str(completed.stderr)
    return completed


def _text(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stdout or "").strip()


def _blank(
    *,
    branch: str,
    reason: str,
    head: str = "",
    published: str = "",
    commands: list[str] | None = None,
) -> dict[str, Any]:
    current = head
    return {
        "adopted": False,
        "moved": False,
        "reason": reason,
        "branch": branch,
        "head_before": current,
        "head_after": current,
        "published": published,
        "reset_used": False,
        "commands": list(commands or []),
    }


def adopt_published_controller(
    repo_path: Path,
    published_sha: str,
    *,
    branch: str = "main",
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Fast-forward ``branch`` to ``published_sha`` when that is a clean descendant.

    ``adopted`` is true when HEAD equals the published commit after the call,
    including when the checkout was already there. ``moved`` is true only when
    this call advanced HEAD. ``reset_used`` is always false.
    """

    repo = Path(repo_path)
    wanted = str(published_sha or "").strip()
    commands: list[str] = []

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        command = ["git", *arguments]
        commands.append(" ".join(command))
        return _run(command, repo, command_runner)

    if not wanted or wanted.startswith("-"):
        return _blank(branch=branch, reason="unresolvable", commands=commands)
    if not repo.exists() or not (repo / ".git").exists():
        return _blank(branch=branch, reason="not_a_repository", commands=commands)

    resolved = git("rev-parse", "--verify", "--end-of-options", f"{wanted}^{{commit}}")
    if resolved.returncode != 0:
        return _blank(branch=branch, reason="unresolvable", commands=commands)
    published = _text(resolved)

    head_cmd = git("rev-parse", "--verify", "HEAD")
    if head_cmd.returncode != 0:
        return _blank(branch=branch, reason="no_head", published=published, commands=commands)
    head_before = _text(head_cmd)

    checked_out = git("rev-parse", "--abbrev-ref", "HEAD")
    current_branch = _text(checked_out)
    if checked_out.returncode != 0 or current_branch in {"", "HEAD"}:
        return _blank(
            branch=branch,
            reason="detached",
            head=head_before,
            published=published,
            commands=commands,
        )
    if current_branch != branch:
        return _blank(
            branch=branch,
            reason="not_controller_branch",
            head=head_before,
            published=published,
            commands=commands,
        )

    if head_before == published:
        return {
            "adopted": True,
            "moved": False,
            "reason": "already_current",
            "branch": branch,
            "head_before": head_before,
            "head_after": head_before,
            "published": published,
            "reset_used": False,
            "commands": commands,
        }

    status = git("status", "--porcelain=v1", "--untracked-files=normal")
    if status.returncode != 0:
        return _blank(
            branch=branch,
            reason="status_failed",
            head=head_before,
            published=published,
            commands=commands,
        )
    if (status.stdout or "").strip():
        return _blank(
            branch=branch,
            reason="dirty",
            head=head_before,
            published=published,
            commands=commands,
        )

    ancestor = git("merge-base", "--is-ancestor", head_before, published)
    if ancestor.returncode != 0:
        return _blank(
            branch=branch,
            reason="not_fast_forward",
            head=head_before,
            published=published,
            commands=commands,
        )

    merged = git("merge", "--ff-only", "--no-edit", published)
    head_after_cmd = git("rev-parse", "--verify", "HEAD")
    head_after = _text(head_after_cmd) or head_before
    moved = head_after == published and head_after != head_before
    if merged.returncode != 0 or not moved:
        return {
            "adopted": False,
            "moved": False,
            "reason": "merge_failed",
            "branch": branch,
            "head_before": head_before,
            "head_after": head_after,
            "published": published,
            "reset_used": False,
            "commands": commands,
        }
    return {
        "adopted": True,
        "moved": True,
        "reason": "fast_forward",
        "branch": branch,
        "head_before": head_before,
        "head_after": head_after,
        "published": published,
        "reset_used": False,
        "commands": commands,
    }


def adopt_remote_controller(
    repo_path: Path,
    *,
    remote: str = "origin",
    branch: str = "main",
    command_runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Fast-forward the controller checkout to ``remote/branch`` when it exists."""

    repo = Path(repo_path)
    ref = f"refs/remotes/{remote}/{branch}"
    if not repo.exists() or not (repo / ".git").exists():
        return _blank(branch=branch, reason="not_a_repository")
    lookup = _run(
        ["git", "rev-parse", "--verify", "--end-of-options", ref],
        repo,
        command_runner,
    )
    if lookup.returncode != 0 or not _text(lookup):
        return _blank(branch=branch, reason="no_remote")
    return adopt_published_controller(
        repo,
        _text(lookup),
        branch=branch,
        command_runner=command_runner,
    )


def import_checkout_attribute(
    repo_path: Path,
    module: str,
    attribute: str,
    *,
    executable: str | None = None,
) -> dict[str, Any]:
    """Import ``module.attribute`` from ``repo/src`` in a fresh interpreter.

    The fresh process does not reuse this process's ``sys.modules``, so it
    reads the checkout that adoption just fast-forwarded.
    """

    repo = Path(repo_path)
    completed = subprocess.run(
        [
            executable or sys.executable,
            "-I",
            "-c",
            _IMPORT_SCRIPT,
            str(repo),
            module,
            attribute,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    value = completed.stdout if isinstance(completed.stdout, str) else ""
    return {
        "ok": completed.returncode == 0 and value != "",
        "exit_code": int(completed.returncode),
        "value": value.strip(),
        "stderr": (completed.stderr or "")[-400:],
    }


def storage_gate_needs_reimport(
    adoption: Mapping[str, Any],
    *,
    loaded_sha: str,
    checkout_sha: str,
) -> bool:
    """True when the in-memory storage gate is not the published checkout.

    The loop fast-forwards ``main`` during publication, before the next
    ``create_mission``. A reload that waits for this call to move HEAD keeps
    the module imported at process start, and the published gate never runs.
    An empty loaded sha has not been bound to a checkout either.
    """

    if adoption.get("moved"):
        return True
    checkout = str(checkout_sha or "").strip()
    if not checkout:
        return False
    return str(loaded_sha or "").strip() != checkout


def reimport_published_storage_budget(
    repo_path: Path,
    *,
    command_runner: Callable[..., Any] = subprocess.run,
) -> Any:
    """Return the storage-budget module that matches the controller checkout.

    Reloads when publication already moved HEAD, or when this process imported
    the gate at a different sha. Records the bound sha on the returned module.
    """

    import importlib

    import blackhole_agent.storage_budget as storage_budget

    try:
        adoption = adopt_remote_controller(repo_path, command_runner=command_runner)
    except Exception:
        adoption = {"moved": False, "reason": "adoption_failed"}
    head_cmd = _run(
        ["git", "rev-parse", "--verify", "HEAD"],
        Path(repo_path),
        command_runner,
    )
    checkout_sha = _text(head_cmd) if head_cmd.returncode == 0 else ""
    loaded_sha = str(getattr(storage_budget, "LOADED_CONTROLLER_SHA", "") or "")
    if storage_gate_needs_reimport(
        adoption,
        loaded_sha=loaded_sha,
        checkout_sha=checkout_sha,
    ):
        storage_budget = importlib.reload(storage_budget)
    if checkout_sha:
        storage_budget.LOADED_CONTROLLER_SHA = checkout_sha
    return storage_budget


# The 2026-11-01 22:39 receipt still has no worktree_reclaim key. Publication
# reloads the storage gate only from inside create_mission, and the live loop
# still calls the create_mission object captured when the process imported
# this checkout. A later edit of that function never runs.
CREATOR_SOURCE_DIGEST = "_creator_source_digest"

_PUBLISHED_CREATOR_SCRIPT = """
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
payload_path = Path(sys.argv[2])
result_path = Path(sys.argv[3])
sys.path.insert(0, str(root / "src"))
from blackhole_agent.unbound import create_mission

payload = json.loads(payload_path.read_text(encoding="utf-8"))

def as_path(value):
    if value is None or value == "":
        return None
    return Path(value)

state = create_mission(
    repo_path=Path(payload["repo_path"]),
    goal=payload.get("goal") or "",
    done_when=payload.get("done_when") or "",
    kernel=payload.get("kernel") or "grok",
    model=payload.get("model"),
    profile=payload.get("profile"),
    target_branch=payload.get("target_branch") or "main",
    branch_prefix=payload.get("branch_prefix") or "unbound",
    output_dir=as_path(payload.get("output_dir")) or Path(".blackhole-agent/unbound"),
    worktree_parent=as_path(payload.get("worktree_parent")),
    timeout_seconds=int(payload.get("timeout_seconds") or 7200),
)
result_path.write_text(str(state), encoding="utf-8")
"""


def checkout_unbound_path(repo_path: Path) -> Path:
    """Path of the checkout's mission creator, relative to the controller repo."""

    return Path(repo_path) / "src" / "blackhole_agent" / "unbound.py"


def file_sha256(path: Path) -> str:
    """Hash one file. A missing or unreadable file is an empty digest."""

    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def bind_creator_source(fn: Callable[..., Any], path: Path | None = None) -> Callable[..., Any]:
    """Remember the checkout file this creator was imported from.

    The digest is the file bytes at bind time. A later fast-forward changes
    those bytes, which is how the loop notices the captured function is stale.
    """

    source = Path(path) if path is not None else Path(getattr(fn.__code__, "co_filename", "") or "")
    digest = file_sha256(source) if str(source) else ""
    setattr(fn, CREATOR_SOURCE_DIGEST, digest)
    return fn


def published_creator_is_stale(repo_path: Path, captured: Callable[..., Any]) -> bool:
    """True when the checkout's unbound.py no longer matches the captured creator."""

    bound = str(getattr(captured, CREATOR_SOURCE_DIGEST, "") or "")
    if not bound:
        return False
    current = file_sha256(checkout_unbound_path(repo_path))
    return bool(current) and current != bound


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return value


def _spawn_published_creator(repo_path: Path, call: Mapping[str, Any]) -> Path:
    """Run the checkout's create_mission in a fresh interpreter.

    The fresh process does not reuse this process's ``sys.modules``, so it
    loads the published creator and the published storage gate together.
    """

    payload = {
        "repo_path": str(call.get("repo_path") or repo_path),
        "goal": call.get("goal") or "",
        "done_when": call.get("done_when") or "",
        "kernel": call.get("kernel") or "grok",
        "model": call.get("model"),
        "profile": call.get("profile"),
        "target_branch": call.get("target_branch") or "main",
        "branch_prefix": call.get("branch_prefix") or "unbound",
        "output_dir": _json_ready(call.get("output_dir") or ".blackhole-agent/unbound"),
        "worktree_parent": _json_ready(call.get("worktree_parent")),
        "timeout_seconds": int(call.get("timeout_seconds") or 7200),
    }
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    with tempfile.TemporaryDirectory(prefix="bh-creator-") as tmp:
        directory = Path(tmp)
        payload_path = directory / "payload.json"
        result_path = directory / "result.txt"
        payload_path.write_text(json.dumps(payload), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _PUBLISHED_CREATOR_SCRIPT, str(repo_path), str(payload_path), str(result_path)],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=env,
        )
        if completed.returncode != 0 or not result_path.is_file():
            detail = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
            raise RuntimeError(detail[-2000:])
        text = result_path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("published create_mission returned an empty path")
    return Path(text)


def invoke_published_mission_creator(
    repo_path: Path,
    captured: Callable[..., Any],
    call: Mapping[str, Any],
    *,
    reload_default: bool = False,
) -> Any:
    """Call the published creator when the captured one predates the checkout file.

    Injected creators, custom command runners, and an unchanged file stay on
    the captured callable. The default loop creator is replaced only when
    ``src/blackhole_agent/unbound.py`` changed after it was imported.
    """

    runner = call.get("command_runner", subprocess.run)
    resolver = call.get("kernel_resolver")
    custom_resolver = resolver is not None and getattr(resolver, "__name__", "") != "resolve_unbound_kernel"
    if (
        not reload_default
        or runner is not subprocess.run
        or custom_resolver
        or not published_creator_is_stale(repo_path, captured)
    ):
        return captured(**dict(call))
    return _spawn_published_creator(repo_path, call)


def commands_use_reset(report: Mapping[str, Any]) -> bool:
    """True when a reported git command resets history."""

    if report.get("reset_used") is True:
        return True
    for command in report.get("commands") or []:
        parts = str(command).split()
        if "reset" in parts or "--hard" in parts:
            return True
    return False
