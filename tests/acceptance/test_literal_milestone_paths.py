"""Compare milestone staging, rollback and commit with Git's index and blobs."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.milestone_commit import stage_milestone_paths
from blackhole_agent.unbound import TurnDecision, changed_paths_since, commit_milestone, restore_unaccepted_workspace


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "--literal-pathspecs", *args], cwd=repo, stderr=subprocess.PIPE)


def names(data: bytes) -> list[str]:
    return [part.decode() for part in data.split(b"\0") if part]


def observe(root: Path) -> dict:
    accepted, rejected = root / "accepted", root / "rejected"
    accepted.mkdir()
    old, new = "原稿.txt", "定稿 [二].txt"
    selected, neighbor = "章节[12].txt", "章节1.txt"
    extra = "新增 笔记.txt" if os.name == "nt" else ' "笔记" -> 行\r\n\t\\ '
    initial = {old: b"draft", "retired.txt": b"retired", selected: b"one", neighbor: b"two"}
    final = {new: b"edited after the move", selected: b"selected", neighbor: b"neighbor", extra: b"new\0blob"}
    git(accepted, "init", "-q")
    git(accepted, "config", "user.email", "probe@example.invalid")
    git(accepted, "config", "user.name", "Probe")
    git(accepted, "config", "commit.gpgSign", "false")
    git(accepted, "config", "core.autocrlf", "false")
    git(accepted, "config", "core.quotePath", "true")
    for path, data in initial.items():
        (accepted / path).write_bytes(data)
    git(accepted, "add", "--", *initial)
    git(accepted, "commit", "-qm", "original")
    base = git(accepted, "rev-parse", "HEAD").decode().strip()
    git(accepted, "worktree", "add", "-q", "--detach", str(rejected), base)
    (accepted / ".git/info/exclude").write_bytes(b"local-note\n")
    (rejected / "local-note").write_bytes(b"keep")

    for repo in (accepted, rejected):
        git(repo, "mv", "--", old, new)
        git(repo, "rm", "-q", "--", "retired.txt")
        for path, data in final.items():
            (repo / path).write_bytes(data)

    observed = {}
    try:
        stage_milestone_paths(rejected, [selected])
    except RuntimeError as error:
        observed["selection_error"] = str(error)
    staged = names(git(rejected, "diff", "--cached", "--no-renames", "--name-only", "-z"))
    observed["staged"] = staged
    observed["selection_ok"] = (
        "selection_error" not in observed and set(staged) == {old, new, "retired.txt", selected}
        and git(rejected, "show", f":{selected}") == final[selected]
        and git(rejected, "show", f":{neighbor}") == initial[neighbor]
    )
    try:
        restore_unaccepted_workspace(rejected)
    except RuntimeError as error:
        observed["rollback_error"] = str(error)
    observed["rollback_ok"] = (
        "rollback_error" not in observed and git(rejected, "rev-parse", "HEAD").decode().strip() == base
        and git(rejected, "write-tree") == git(rejected, "rev-parse", "HEAD^{tree}")
        and not git(rejected, "status", "--porcelain", "-z", "--untracked-files=all")
        and all((rejected / path).is_file() and (rejected / path).read_bytes() == data for path, data in initial.items())
        and (rejected / "local-note").is_file() and (rejected / "local-note").read_bytes() == b"keep"
    )
    expected = set(initial) | set(final)
    observed["listed_before"] = changed_paths_since(accepted, base)
    decision = TurnDecision.from_payload({"status": "milestone", "commit_message": "Record edited manuscript"})
    try:
        commit_milestone(accepted, decision, 1)
    except RuntimeError as error:
        observed["commit_error"] = str(error)
    observed["committed"] = names(git(accepted, "ls-tree", "-rz", "--name-only", "HEAD"))
    blobs = {name: git(accepted, "show", f"HEAD:{name}") for name in observed["committed"]}
    observed["commit_ok"] = (
        "commit_error" not in observed and blobs == final and not git(accepted, "status", "--porcelain", "-z")
    )
    observed["listing_ok"] = set(observed["listed_before"]) == set(changed_paths_since(accepted, base)) == expected
    obstructed = root / "obstructed"
    git(accepted, "worktree", "add", "-q", "--detach", str(obstructed), base)
    slot = obstructed / "retired.txt"
    slot.unlink()
    slot.mkdir()
    note = slot / "local-note"
    note.write_bytes(b"local draft")
    recovery = restore_unaccepted_workspace(obstructed)
    kept = note.is_file() and note.read_bytes() == b"local draft"
    observed["obstruction_ok"] = kept and not recovery["clean"]
    observed["retry_ok"] = False
    if kept:
        note.unlink()
        restore_unaccepted_workspace(obstructed)
        observed["retry_ok"] = (
            slot.is_file() and slot.read_bytes() == initial[slot.name] and not git(obstructed, "status", "--porcelain", "-z")
        )
    return observed


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="bh-literal-paths-") as directory:
        result = observe(Path(directory))
    passed = all(result[key] for key in ("selection_ok", "rollback_ok", "commit_ok", "listing_ok",
                                         "obstruction_ok", "retry_ok"))
    print(json.dumps({"passed": passed, "observed": result}))
