"""Outcome probe: an empty reply, connect failure, or DNS failure is retried once.

Harvested continuous-loop publications died on "Empty reply from server"
(2026-10-15), "Could not connect to github.com" (2026-08-11), and
"Could not resolve host: github.com" (2026-08-11). The same push command must
run once more, and the remote branch head must equal the commit. An ls-remote
abort of that class is retried once before the push. A second empty reply
stays a failure. A repository-not-found lookup and a remote head that is not
an ancestor are not pushed. The previous milestone returns the first abort
after one attempt, so this probe reports passed=false there. Both outcomes
exit 0.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

EMPTY_REPLY = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "Empty reply from server\n"
)
CONNECT = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "Failed to connect to github.com port 443 after 21097 ms: Could not connect to server\n"
)
DNS = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "Could not resolve host: github.com\n"
)
UNRELATED = "fatal: repository not found\n"


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


def _init_pair(root: Path) -> tuple[Path, Path, str]:
    repo = root / "repo"
    remote = root / "remote.git"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "publish@test.local")
    _git(repo, "config", "user.name", "Publish Test")
    _git(repo, "config", "core.autocrlf", "false")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    return repo, remote, _git(repo, "rev-parse", "HEAD")


def _remote_head(remote: Path) -> str:
    completed = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def _tokens(command: list[str]) -> list[str]:
    return [str(part) for part in command]


def _is_push(command: list[str]) -> bool:
    return len(command) >= 2 and command[0] == "git" and "push" in command


def _is_lookup(command: list[str]) -> bool:
    return len(command) >= 2 and command[0] == "git" and "ls-remote" in command


def _has_post_buffer(command: list[str]) -> bool:
    return any(str(part).startswith("http.postBuffer=") for part in command)


def _delegate(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, **kwargs)  # type: ignore[arg-type]


def _publish(root_name: str, runner) -> dict[str, object]:
    from blackhole_agent.unbound import publish_lineage

    with tempfile.TemporaryDirectory(prefix=root_name) as directory:
        repo, remote, commit_sha = _init_pair(Path(directory))
        result = publish_lineage(repo, commit_sha, str(remote), "main", command_runner=runner)
        return {
            "ok": result.ok,
            "error": result.error,
            "remote_matches": _remote_head(remote) == commit_sha,
            "commit_sha": commit_sha,
        }


def exercise_recovered_push(stderr: str) -> dict[str, object]:
    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = _tokens(command)
        if _is_push(tokens):
            pushes.append(tokens)
            if len(pushes) == 1:
                return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=stderr)
        return _delegate(tokens, **kwargs)

    observed = _publish("bh-http-recover-", runner)
    observed.update(
        {
            "push_count": len(pushes),
            "same_command": len(pushes) >= 2 and pushes[0] == pushes[1],
            "enlarged": any(_has_post_buffer(item) for item in pushes),
        }
    )
    return observed


def exercise_lookup_recovers() -> dict[str, object]:
    lookups: list[list[str]] = []
    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = _tokens(command)
        if _is_lookup(tokens):
            lookups.append(tokens)
            if len(lookups) == 1:
                return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=EMPTY_REPLY)
        if _is_push(tokens):
            pushes.append(tokens)
        return _delegate(tokens, **kwargs)

    observed = _publish("bh-http-lookup-", runner)
    observed.update(
        {
            "lookup_count": len(lookups),
            "push_count": len(pushes),
            "enlarged": any(_has_post_buffer(item) for item in pushes),
        }
    )
    return observed


def exercise_second_abort() -> dict[str, object]:
    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = _tokens(command)
        if _is_push(tokens):
            pushes.append(tokens)
            return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=EMPTY_REPLY)
        return _delegate(tokens, **kwargs)

    observed = _publish("bh-http-twice-", runner)
    observed.update(
        {
            "push_count": len(pushes),
            "enlarged": any(_has_post_buffer(item) for item in pushes),
        }
    )
    return observed


def exercise_mismatch() -> dict[str, object]:
    from blackhole_agent.unbound import publish_lineage

    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = _tokens(command)
        if _is_push(tokens):
            pushes.append(tokens)
        return _delegate(tokens, **kwargs)

    with tempfile.TemporaryDirectory(prefix="bh-http-mismatch-") as directory:
        root = Path(directory)
        repo, remote, _seed = _init_pair(root)
        _git(repo, "push", str(remote), "main")
        _git(repo, "checkout", "--orphan", "diverged")
        (repo / "other.md").write_text("diverged\n", encoding="utf-8")
        _git(repo, "add", "other.md")
        _git(repo, "commit", "-m", "diverged")
        diverged = _git(repo, "rev-parse", "HEAD")
        before = _remote_head(remote)
        result = publish_lineage(repo, diverged, str(remote), "main", command_runner=runner)
        return {
            "ok": result.ok,
            "push_count": len(pushes),
            "remote_unchanged": _remote_head(remote) == before,
            "refused": "remote-head mismatch" in result.error,
        }


def exercise_unrelated_lookup() -> dict[str, object]:
    lookups: list[list[str]] = []
    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = _tokens(command)
        if _is_lookup(tokens):
            lookups.append(tokens)
            return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=UNRELATED)
        if _is_push(tokens):
            pushes.append(tokens)
        return _delegate(tokens, **kwargs)

    observed = _publish("bh-http-unrelated-", runner)
    observed.update({"lookup_count": len(lookups), "push_count": len(pushes)})
    return observed


def _recovered(observed: dict[str, object]) -> bool:
    return bool(
        observed["ok"]
        and observed["push_count"] == 2
        and observed["same_command"]
        and observed["enlarged"] is False
        and observed["remote_matches"]
    )


def main() -> None:
    observed: dict[str, object] = {}
    try:
        empty_reply = exercise_recovered_push(EMPTY_REPLY)
        connect = exercise_recovered_push(CONNECT)
        dns = exercise_recovered_push(DNS)
        lookup = exercise_lookup_recovers()
        second = exercise_second_abort()
        mismatch = exercise_mismatch()
        unrelated = exercise_unrelated_lookup()
        observed = {
            "connect": connect,
            "dns": dns,
            "empty_reply": empty_reply,
            "lookup": lookup,
            "mismatch": mismatch,
            "second_abort": second,
            "unrelated_lookup": unrelated,
        }
        passed = bool(
            _recovered(empty_reply)
            and _recovered(connect)
            and _recovered(dns)
            and lookup["ok"]
            and lookup["lookup_count"] == 3
            and lookup["push_count"] == 1
            and lookup["enlarged"] is False
            and lookup["remote_matches"]
            and second["ok"] is False
            and second["push_count"] == 2
            and second["enlarged"] is False
            and second["remote_matches"] is False
            and mismatch["ok"] is False
            and mismatch["push_count"] == 0
            and mismatch["remote_unchanged"]
            and mismatch["refused"]
            and unrelated["ok"] is False
            and unrelated["lookup_count"] == 1
            and unrelated["push_count"] == 0
        )
    except Exception as error:  # noqa: BLE001 - probe must exit 0 with an unmet outcome
        observed = {"error": f"{error.__class__.__name__}: {error}"}
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
