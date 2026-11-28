"""Publish against commits present only in the receiving repository and its writer."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.unbound import publish_lineage


def git(repo, *args):
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8", stderr=subprocess.PIPE
    ).strip()


def commit(repo, filename, text):
    path = repo / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    git(repo, "add", "--", filename)
    git(repo, "commit", "-qm", text)
    return git(repo, "rev-parse", "HEAD")


def repositories(root):
    writer, mirror, receiver, peer = (root / name for name in ("writer", "mirror.git", "receiver.git", "peer"))
    git(root, "init", "-qb", "main", str(writer))
    git(writer, "config", "user.name", "Publisher")
    git(writer, "config", "user.email", "publisher@example.invalid")
    base = commit(writer, "notes.txt", "base")
    for bare in (mirror, receiver):
        git(root, "clone", "--bare", "--no-local", str(writer), str(bare))
    git(root, "clone", "--no-local", "-c", "user.name=Peer", "-c", "user.email=peer@example.invalid",
        str(receiver), str(peer))
    git(writer, "remote", "add", "origin", mirror.as_posix())
    git(writer, "remote", "set-url", "--push", "origin", receiver.as_posix())
    git(writer, "fetch", "origin", "main")
    return writer, receiver, peer, base


def exercise(root):
    writer, receiver, peer, base = repositories(root)
    tips = {}
    for branch, filename in (("clean", "mission.txt"), ("conflict", "peer.txt"), ("protected", "governance/rule")):
        git(peer, "switch", "-c", branch, base)
        upstream = commit(peer, "peer.txt", f"collaborator {branch}")
        git(peer, "push", "origin", branch)
        git(writer, "switch", "-c", branch, base)
        tips[branch] = (upstream, commit(writer, filename, f"mission {branch}"))

    git(writer, "switch", "main")
    notes = writer / "notes.txt"
    notes.write_bytes(b"staged draft\n")
    git(writer, "add", "--", "notes.txt")
    notes.write_bytes(b"unfinished draft\n")

    def checkout():
        return (
            git(writer, "symbolic-ref", "HEAD"), git(writer, "rev-parse", "HEAD"), git(writer, "write-tree"),
            notes.read_bytes(), (writer / ".git" / "FETCH_HEAD").read_bytes(),
        )

    original = checkout()
    observed = {}
    for branch, (upstream, mission) in tips.items():
        ref = f"refs/heads/{branch}"
        missing = subprocess.run(
            ["git", "cat-file", "-e", upstream], cwd=writer, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode != 0
        result = publish_lineage(writer, mission, "origin", branch)
        landed = git(receiver, "rev-parse", ref)
        row = {"missing_before": missing, "ok": result.ok, "error": result.error,
               "checkout_preserved": checkout() == original}
        if branch == "clean":
            row["parents"] = git(receiver, "show", "-s", "--format=%P", ref).split()
            row["parents_match"] = row["parents"] == [upstream, mission]
            row["peer_text"] = git(receiver, "show", f"{ref}:peer.txt")
            row["mission_text"] = git(receiver, "show", f"{ref}:mission.txt") if result.ok else None
            row["accepted"] = (
                result.ok and result.remote_before == upstream and result.remote_after == landed
                and row["parents_match"] and row["peer_text"] == "collaborator clean" and row["mission_text"] == "mission clean"
            )
        else:
            reason = "remote-head mismatch" if branch == "conflict" else "governance/rule"
            row["receiver_unchanged"] = landed == upstream
            row["accepted"] = not result.ok and row["receiver_unchanged"] and reason in result.error
        observed[branch] = row
    passed = all(row["missing_before"] and row["checkout_preserved"] and row["accepted"] for row in observed.values())
    return {"passed": passed, "observed": observed}


def test_publication_preserves_both_writers(tmp_path):
    result = exercise(tmp_path)
    assert result["passed"], result


def test_interrupted_transfer_and_concurrent_rewind_keep_publication_pending(tmp_path):
    from blackhole_agent.publication_resilience import apply_publication_failure

    writer, receiver, peer, base = repositories(tmp_path)
    upstream = commit(peer, "peer.txt", "peer")
    git(peer, "push", "origin", "main")
    mission = commit(writer, "mission.txt", "mission")
    pending = {"pending_publish_ref": mission, "pending_publish_mission_id": "example"}

    def transfer(command, **kwargs):
        if command[:2] != ["git", "fetch"]:
            return subprocess.run(command, **kwargs)
        if fault == "unreadable":
            return subprocess.run(["git", "-c", "protocol.file.allow=never", *command[1:]], **kwargs)
        fetched = subprocess.run(command, **kwargs)
        git(receiver, "update-ref", "refs/heads/main", base, upstream)
        return fetched

    for fault, expected in (("unreadable", upstream), ("rewound", base)):
        refused = publish_lineage(writer, mission, "origin", "main", command_runner=transfer)
        apply_publication_failure(pending, refused.error)
        assert not refused.ok and refused.remote_before == upstream
        assert git(receiver, "rev-parse", "main") == expected
        assert pending["pending_publish_ref"] == mission and pending["pending_publish_mission_id"] == "example"
    retried = publish_lineage(writer, mission, "origin", "main")
    assert retried.ok and git(receiver, "rev-parse", "main") == mission


if __name__ == "__main__":
    os.environ.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        with tempfile.TemporaryDirectory(prefix="independent publisher ") as directory:
            output = exercise(Path(directory))
    except (OSError, subprocess.CalledProcessError) as error:
        output = {"passed": False, "observed": {"error": str(error), "detail": str(getattr(error, "stderr", ""))}}
    print(json.dumps(output))
