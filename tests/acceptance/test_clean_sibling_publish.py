"""Replay the November 2 clean-sibling refusal and its conflict and unrelated-history controls."""

import json
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.unbound import publish_lineage


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.PIPE, encoding="utf-8").strip()


def commit(repo, name, body):
    (repo / name).write_text(body + "\n", encoding="utf-8")
    git(repo, "add", "--", name)
    git(repo, "commit", "-qm", body)
    return git(repo, "rev-parse", "HEAD")


def observe(root):
    repo = root / "writer"
    git(root, "init", "-qb", "main", str(repo))
    git(repo, "config", "user.email", "pub@test.local")
    git(repo, "config", "user.name", "Pub Test")
    seed = commit(repo, "README.md", "seed")
    git(repo, "remote", "add", "origin", str(root / "clean.git"))
    observed = {}
    for case in ("clean", "conflict", "unrelated"):
        receiver = root / f"{case}.git"
        git(root, "init", "--bare", "-q", str(receiver))
        git(repo, "remote", "set-url", "origin", str(receiver))
        name = "shared.txt" if case == "conflict" else "remote-only.txt"
        git(repo, "switch", "--detach", seed)
        git(repo, "push", "origin", "HEAD:refs/heads/main")
        upstream = seed
        if case == "unrelated":
            git(repo, "switch", "--orphan", "orphan")
        else:
            upstream = commit(repo, name, "remote")
            git(repo, "push", "origin", "HEAD:refs/heads/main")
            git(repo, "switch", "--detach", seed)
        target = commit(repo, name if case == "conflict" else "lineage-only.txt", "lineage")
        result = publish_lineage(repo, target, "origin", "main")
        landed = git(receiver, "rev-parse", "refs/heads/main")
        if case == "clean":
            parents = git(receiver, "show", "-s", "--format=%P", landed).split()
            row = dict(ok=result.ok, error=result.error, remote_before=result.remote_before,
                       lineage_tip=target, landed=landed, first_parent=parents[0] if parents else "",
                       second_parent=parents[1] if len(parents) > 1 else "",
                       remote_text=git(receiver, "show", f"{landed}:remote-only.txt") if result.ok else "",
                       lineage_text=git(receiver, "show", f"{landed}:lineage-only.txt") if result.ok else "",
                       fast_forward=git(receiver, "merge-base", upstream, landed) == upstream)
            row["met"] = (result.ok and result.remote_before == upstream and parents == [upstream, target]
                          and row["remote_text"] == "remote" and row["lineage_text"] == "lineage" and row["fast_forward"])
        else:
            row = dict(ok=result.ok, refused="remote-head mismatch" in result.error,
                       remote_unchanged=landed == upstream, remote_before=result.remote_before == upstream)
            row["met"] = not result.ok and row["refused"] and row["remote_unchanged"]
        observed[case] = row
    return {"passed": all(row["met"] for row in observed.values()), "observed": observed}


if __name__ == "__main__":
    try:
        with tempfile.TemporaryDirectory(prefix="bh-sibling-") as directory:
            verdict = observe(Path(directory))
    except Exception as error:
        verdict = {"passed": False, "observed": {"error": str(error)}}
    print(json.dumps(verdict))
