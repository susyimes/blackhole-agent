"""Outcome probe: a schannel TLS abort is retried once and the push lands.

Harvested continuous-loop publications from 2026-07-29 through 2026-10-29 die
on "schannel: failed to receive handshake" and on "server closed abruptly
(missing close_notify)" without asking for a larger http.postBuffer. The same
command must run once more, and the remote branch head must equal the commit.
An ls-remote abort of that class is retried once before the push. A second
abort stays a failure. The http.postBuffer rewind path still retries once with
a larger buffer. A remote head that is not an ancestor is not pushed. The
previous milestone returns the handshake failure after one attempt, so this
probe reports passed=false there. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

HANDSHAKE = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "schannel: failed to receive handshake, SSL/TLS connection failed\n"
)
CLOSE_NOTIFY = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "schannel: server closed abruptly (missing close_notify)\n"
)
POST_BUFFER = (
    "error: unable to rewind rpc post data - try increasing http.postBuffer\n"
    "error: RPC failed; curl 65 schannel: server closed abruptly (missing close_notify)\n"
    "send-pack: unexpected disconnect while reading sideband packet\n"
    "fatal: the remote end hung up unexpectedly\n"
    "Everything up-to-date\n"
)
UNRELATED = "fatal: repository not found\n"


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.PIPE, encoding="utf-8").strip()


def observe(root, name, failure=""):
    from blackhole_agent.unbound import publish_lineage

    repo, receiver = root / "repo", root / "remote.git"
    git(root, "init", "-qb", "main", str(repo))
    git(repo, "config", "user.email", "publish@test.local")
    git(repo, "config", "user.name", "Publish Test")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "seed")
    seed = git(repo, "rev-parse", "HEAD")
    git(root, "init", "--bare", "-q", str(receiver))
    if name == "mismatch":
        git(repo, "push", str(receiver), "main")
        git(repo, "switch", "--orphan", "diverged")
        (repo / "other.md").write_text("diverged\n", encoding="utf-8")
        git(repo, "add", "other.md")
        git(repo, "commit", "-qm", "diverged")
    target = git(repo, "rev-parse", "HEAD")
    pushes = []
    lookups = 0

    def transport(command, **kwargs):
        nonlocal lookups
        if "ls-remote" in command:
            lookups += 1
            if name == "unrelated_lookup" or (name == "lookup" and lookups == 1):
                return subprocess.CompletedProcess(command, 1, "", failure)
        if "push" in command:
            pushes.append(command)
            first_abort = name in {"handshake", "close_notify"} and len(pushes) == 1
            small_buffer = name == "post_buffer" and not any(arg.startswith("http.postBuffer=") for arg in command)
            if first_abort or small_buffer or name == "second_abort":
                return subprocess.CompletedProcess(command, 1, "", failure)
        return subprocess.run(command, **kwargs)

    result = publish_lineage(repo, target, str(receiver), "main", command_runner=transport)
    refs = git(repo, "ls-remote", "--heads", str(receiver), "refs/heads/main")
    head = refs.partition("\t")[0]
    return dict(ok=result.ok, error=result.error, commit_sha=target, push_count=len(pushes), lookup_count=lookups,
                remote_matches=head == target, remote_unchanged=head == (seed if name == "mismatch" else ""),
                same_command=len(pushes) == 2 and pushes[0] == pushes[1],
                enlarged=any(arg.startswith("http.postBuffer=") for command in pushes for arg in command),
                refused="remote-head mismatch" in result.error)


def main():
    recovered = dict(ok=True, push_count=2, same_command=True, enlarged=False, remote_matches=True)
    cases = {
        "handshake": (HANDSHAKE, recovered),
        "close_notify": (CLOSE_NOTIFY, recovered),
        "lookup": (HANDSHAKE, dict(ok=True, lookup_count=3, push_count=1, enlarged=False, remote_matches=True)),
        "second_abort": (HANDSHAKE, dict(ok=False, push_count=2, enlarged=False, remote_matches=False)),
        "post_buffer": (POST_BUFFER, dict(ok=True, push_count=2, enlarged=True, remote_matches=True)),
        "mismatch": ("", dict(ok=False, push_count=0, remote_unchanged=True, refused=True)),
        "unrelated_lookup": (UNRELATED, dict(ok=False, lookup_count=1, push_count=0)),
    }
    observed = {}
    try:
        for name, (failure, _) in cases.items():
            with tempfile.TemporaryDirectory(prefix="bh-schannel-") as directory:
                observed[name] = observe(Path(directory), name, failure)
        passed = all(observed[name][key] == value for name, (_, expected) in cases.items()
                     for key, value in expected.items())
    except Exception as error:
        observed["error"] = f"{type(error).__name__}: {error}"
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
