"""Keep the Git entry point of a selection turn across kernel and controller retries."""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from blackhole_agent.file_guard import atomic_write_json
from blackhole_agent.milestone_commit import run_git_pathspec


def _skip_reason(workspace: Path, path: str) -> str:
    raw = workspace / path
    if (".git" in Path(path).parts or raw.name.lower() in {".env", ".env.local", "credentials.json", "id_rsa", "id_rsa.pub"}
            or raw.suffix.lower() in {".pem", ".key"}):
        return "protected_name"
    try:
        if raw.is_symlink() or getattr(raw.lstat(), "st_file_attributes", 0) & 0x400:
            return "reparse"
    except (FileNotFoundError, NotADirectoryError):
        pass
    try:
        return "" if raw.resolve().relative_to(workspace).parts else "outside_workspace"
    except (OSError, ValueError):
        return "outside_workspace"


def restore_unaccepted_workspace(workspace: Path, *, command_runner: Callable[..., Any] = subprocess.run) -> dict:
    """Restore literal paths from HEAD, keeping ignored bytes, protected names and links on disk."""
    from blackhole_agent.unbound import _porcelain_entries, git_text

    root = workspace.resolve()
    restored, removed, skipped = [], [], []

    def status():
        return _porcelain_entries(root, command_runner=command_runner)

    def restore_paths(paths, *, index_only=False):
        if paths:
            args = ["restore", "--source=HEAD", "--staged", "--no-recurse-submodules"]
            run_git_pathspec(root, args if index_only else [*args, "--worktree"], paths, command_runner=command_runner)

    def clean(entries):
        # A staged deletion and an untracked replacement can have the same name.
        indexed = {path: code for code, path in entries if code != "??"}
        files, directories = [], []
        for path in dict.fromkeys(path for _, path in entries):
            raw = root / path
            if reason := _skip_reason(root, path):
                skipped.append({"path": path, "reason": reason})
            elif path in indexed:
                (directories if raw.is_dir() else files).append(path)
            elif raw.is_file():
                raw.unlink()
                removed.append(path)
            elif raw.exists():
                skipped.append({"path": path, "reason": "not_a_file"})
        # Restore the leaves before deciding whether a directory can become a file again.
        for group in (files, directories):
            paths = []
            for path in group:
                raw = root / path
                if raw.is_dir():
                    row = git_text(root, ["git", "--literal-pathspecs", "ls-tree", "HEAD", "--", path],
                                   command_runner=command_runner)
                    kind = row.partition(" ")[2].partition(" ")[0]
                    if kind != "commit" and (kind != "blob" or any(raw.iterdir())):
                        skipped.append({"path": path, "reason": "directory_in_the_way"})
                        continue
                paths.append(path)
            restore_paths(paths)
            for path in paths:
                added = indexed[path] in {"A ", "AM", "AD", "AT", " A"}
                if added or not os.path.lexists(root / path):
                    removed.append(path)
                else:
                    restored.append(path)

    entries = status()
    # An addition may be an operator's formerly ignored file. Return it to the
    # worktree first so Git can apply the restored ignore rules to its bytes.
    added_files = [path for code, path in entries if code[0] == "A" and not _skip_reason(root, path)
                   and (root / path).is_file()]
    if added_files:
        restore_paths(added_files, index_only=True)
        entries = status()
    while rules := [row for row in entries if os.path.normcase(Path(row[1]).name) == ".gitignore"]:
        # A parent's rules may hide a private subtree, including its own ignore file.
        depth = min(path.count("/") for _, path in rules)
        level = [row for row in rules if row[1].count("/") == depth]
        clean(level)
        entries = status()
        if set(level).intersection(entries):
            raise RuntimeError("Cannot restore the Git ignore rules before cleaning rejected files")
    clean(entries)
    return {"restored_tracked": restored, "removed_untracked": removed, "skipped": skipped, "clean": not status()}


class GenesisRollback:
    def __init__(self, workspace: Path, turn_dir: Path, command_runner: Callable[..., Any]):
        self.workspace = workspace
        self.path = turn_dir / "selection-checkpoint.json"
        self.runner = command_runner
        self.point: dict[str, str] = {}

    def git(self, *args: str, **options: Any) -> subprocess.CompletedProcess:
        from blackhole_agent.unbound import run_command

        return run_command(["git", *args], cwd=self.workspace, command_runner=self.runner, **options)

    def checkout_ref(self) -> str:
        result = self.git("symbolic-ref", "--quiet", "HEAD", check=False)
        if result.returncode == 1:
            return "HEAD"  # A detached checkout has its own direct ref.
        if result.returncode:
            raise RuntimeError(f"Cannot identify selection checkout: {result.stderr}")
        return result.stdout.strip()

    def begin(self, prior_turn: dict | None) -> None:
        ref = self.checkout_ref()
        if not self.path.exists():
            gate = prior_turn.get("selection_gate") if isinstance(prior_turn, dict) else None
            if isinstance(gate, dict) and gate.get("accepted") is False:
                expected = (prior_turn.get("rejected_workspace_restore") or {}).get("entry_ref", ref)
                if ref != expected:
                    raise RuntimeError(f"Selection cleanup requires checkout {expected}, found {ref}")
                restore_unaccepted_workspace(self.workspace, command_runner=self.runner)
            self.point = {"entry_ref": ref, "entry_head": self.git("rev-parse", "--verify", ref).stdout.strip()}
            atomic_write_json(self.path, self.point)
            return
        self.point = json.loads(self.path.read_bytes())
        self.require_checkout(ref)
        if "rejected_head" in self.point:
            receipt = self.restore()
            if ref := receipt["recovery_ref"]:
                archive = self.path.with_name(f"rejected-{self.point['rejected_head']}.json")
                atomic_write_json(archive, {**self.point, "recovery_ref": ref})
            del self.point["rejected_head"]
            atomic_write_json(self.path, self.point)

    def require_checkout(self, ref: str) -> None:
        if self.point["entry_ref"] != ref:
            raise RuntimeError(f"Selection rollback requires checkout {self.point['entry_ref']}, found {ref}")

    def record_rejection(self) -> None:
        ref = self.point["entry_ref"]
        # An attached branch can still be identified if the kernel switched away.
        self.point["rejected_head"] = (
            self.git("rev-parse", "--verify", ref).stdout.strip()
            if ref != "HEAD" or self.checkout_ref() == ref else self.point["entry_head"]
        )
        atomic_write_json(self.path, self.point)

    def restore(self) -> dict[str, Any]:
        self.require_checkout(self.checkout_ref())
        ref, entry, tip = (self.point[key] for key in ("entry_ref", "entry_head", "rejected_head"))
        if not all(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) for oid in (entry, tip)):
            raise ValueError("Invalid commit in selection checkpoint")
        current = self.git("rev-parse", "--verify", ref).stdout.strip()
        if current not in {tip, entry}:
            raise RuntimeError(f"Selection rollback stopped because {ref} moved to {current}")
        recovery_ref = ""
        if tip != entry:
            recovery_ref = f"refs/blackhole-agent/rejected/{tip}"
            exists = self.git("show-ref", "--verify", "--quiet", recovery_ref, check=False)
            operation = "create" if exists.returncode == 1 else "verify"
            # Keep the rejected chain and compare-and-swap its original branch together.
            # A retry after the ref transaction verifies the same saved tip and entry.
            commands = f"{operation} {recovery_ref}\0{tip}\0update {ref}\0{entry}\0{current}\0"
            self.git("update-ref", "--no-deref", "-m", "isolate rejected genesis", "--stdin", "-z",
                     input_bytes=commands.encode("utf-8"))
            self.require_checkout(self.checkout_ref())
        result = restore_unaccepted_workspace(self.workspace, command_runner=self.runner)
        if recovery_ref and not result["clean"]:
            from blackhole_agent.unbound import status_changed_paths

            changed = self.git("diff", "--no-renames", "--name-only", "-z", entry, tip, exact_stdout=True)
            conflicts = set(changed.stdout.split("\0")).intersection(status_changed_paths(self.workspace, command_runner=self.runner))
            if conflicts:
                raise RuntimeError(f"Rollback pending at {min(conflicts)}. Recover commits at {recovery_ref}")
        return {**result, **self.point, "recovery_ref": recovery_ref}
