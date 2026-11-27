"""Observe a real receiving branch when only the client's push reply is lost."""

import json
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.unbound import publish_lineage


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True, stderr=subprocess.PIPE).strip()


def observe(root):
    repo, receiver, mirror = (root / name for name in ("writer", "receiver.git", "mirror.git"))
    repo.mkdir()
    git(repo, "init", "-qb", "main")
    git(repo, "config", "user.name", "Publisher")
    git(repo, "config", "user.email", "publisher@example.invalid")
    for name in ("original", "intervening", "milestone"):
        (repo / "published.txt").write_text(name, encoding="utf-8")
        git(repo, "add", "published.txt")
        git(repo, "commit", "-qm", name)
    target = git(repo, "rev-parse", "HEAD")
    intervening = git(repo, "rev-parse", "HEAD^")
    original = git(repo, "rev-parse", "HEAD^^")
    for bare in (receiver, mirror):
        git(repo, "init", "--bare", "-q", str(bare))
        git(repo, "push", str(bare), "main")
    git(repo, "remote", "add", "split", str(mirror))
    git(repo, "remote", "set-url", "--push", "split", str(receiver))
    git(repo, "config", f"url.{mirror.as_posix()}.insteadOf", "fixture:")
    git(repo, "config", f"url.{receiver.as_posix()}.pushInsteadOf", "fixture:")
    git(repo, "remote", "add", "fanout", str(mirror))
    for bare in (mirror, receiver):
        git(repo, "remote", "set-url", "--add", "--push", "fanout", str(bare))
    branch = "refs/heads/main"
    empty_reply = "fatal: Empty reply from server"

    def exercise(*, land_on=0, timeout=False, unreadable=False, peer=False, remote=str(receiver)):
        git(receiver, "update-ref", branch, original)
        pushes = 0

        def transport(command, **kwargs):
            nonlocal pushes
            if "push" in command:
                pushes += 1
                if pushes == land_on:
                    subprocess.run(command, **kwargs, check=True)
                elif peer and pushes == 1:
                    git(receiver, "update-ref", branch, intervening)
                elif peer:
                    return subprocess.run(command, **kwargs)  # Git would still allow this fast-forward.
                if timeout:
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                return subprocess.CompletedProcess(command, 1, "", empty_reply)
            if "ls-remote" in command and pushes and unreadable:
                return subprocess.CompletedProcess(command, 1, "", empty_reply)
            return subprocess.run(command, **kwargs)

        try:
            receipt = publish_lineage(repo, target, remote, "main", command_runner=transport)
            ok, verified = receipt.ok, receipt.remote_after == target
        except subprocess.TimeoutExpired:
            ok, verified = False, False
        content = git(receiver, "show", f"{branch}:published.txt")
        return dict(ok=ok, verified=verified, pushes=pushes, content=content)

    cases = [
        ("lost_reply", dict(land_on=1), True, 1, "milestone"),
        ("lost_timeout", dict(land_on=1, timeout=True), True, 1, "milestone"),
        ("retry_lands", dict(land_on=2), True, 2, "milestone"),
        ("never_delivered", {}, False, 2, "original"),
        ("receiver_unreadable", dict(land_on=1, unreadable=True), False, 1, "milestone"),
        ("peer_advanced", dict(peer=True), False, 1, "intervening"),
        ("separate_fetch_mirror", dict(land_on=1, remote="split"), True, 1, "milestone"),
        ("rewritten_push_url", dict(land_on=1, remote="fixture:"), True, 1, "milestone"),
        ("second_push_url_behind", dict(land_on=1, remote="fanout"), True, 1, "milestone"),
    ]
    expected = {name: dict(ok=ok, verified=ok, pushes=n, content=body) for name, _, ok, n, body in cases}
    observed = {name: exercise(**settings) for name, settings, *_ in cases}
    return {"passed": observed == expected, "observed": observed}


def test_publication_reconciles_with_receivers(tmp_path):
    outcome = observe(tmp_path)
    assert outcome["passed"], outcome


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="bh-publish-ack-") as directory:
        print(json.dumps(observe(Path(directory))))
