"""Outcome probe: a postBuffer push failure is retried once and lands.

The 2026-08-23 publication died with "try increasing http.postBuffer", curl 65,
and a sideband disconnect. The same publish must push once more with
http.postBuffer set, and the remote branch head must equal the commit. A
schannel handshake failure that does not ask for a larger buffer stays one
push. A remote head that is not an ancestor is not pushed. The previous
milestone leaves the buffer retry out, so the same probe reports passed=false.
Both outcomes exit 0.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

HARVESTED_POST_BUFFER = (
    "error: unable to rewind rpc post data - try increasing http.postBuffer\n"
    "error: RPC failed; curl 65 schannel: server closed abruptly (missing close_notify)\n"
    "send-pack: unexpected disconnect while reading sideband packet\n"
    "fatal: the remote end hung up unexpectedly\n"
    "Everything up-to-date\n"
)
HANDSHAKE_ONLY = (
    "fatal: unable to access 'https://github.com/susyimes/blackhole-agent.git/': "
    "schannel: failed to receive handshake, SSL/TLS connection failed\n"
)


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


def _is_push(command: list[str]) -> bool:
    return len(command) >= 2 and command[0] == "git" and "push" in command


def _has_post_buffer(command: list[str]) -> bool:
    return any(str(part).startswith("http.postBuffer=") for part in command)


def _delegate(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, **kwargs)  # type: ignore[arg-type]


def exercise_post_buffer() -> dict[str, object]:
    from blackhole_agent.unbound import publish_lineage

    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = [str(part) for part in command]
        if _is_push(tokens):
            pushes.append(tokens)
            if not _has_post_buffer(tokens):
                return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=HARVESTED_POST_BUFFER)
        return _delegate(tokens, **kwargs)

    with tempfile.TemporaryDirectory(prefix="bh-post-buffer-") as directory:
        repo, remote, commit_sha = _init_pair(Path(directory))
        result = publish_lineage(repo, commit_sha, str(remote), "main", command_runner=runner)
        return {
            "ok": result.ok,
            "push_count": len(pushes),
            "enlarged": any(_has_post_buffer(item) for item in pushes),
            "remote_matches": _remote_head(remote) == commit_sha,
            "error": result.error,
        }


def exercise_handshake() -> dict[str, object]:
    from blackhole_agent.unbound import publish_lineage

    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = [str(part) for part in command]
        if _is_push(tokens):
            pushes.append(tokens)
            return subprocess.CompletedProcess(tokens, 1, stdout="", stderr=HANDSHAKE_ONLY)
        return _delegate(tokens, **kwargs)

    with tempfile.TemporaryDirectory(prefix="bh-handshake-push-") as directory:
        repo, remote, commit_sha = _init_pair(Path(directory))
        result = publish_lineage(repo, commit_sha, str(remote), "main", command_runner=runner)
        return {
            "ok": result.ok,
            "push_count": len(pushes),
            "enlarged": any(_has_post_buffer(item) for item in pushes),
            "remote_matches": _remote_head(remote) == commit_sha,
        }


def exercise_mismatch() -> dict[str, object]:
    from blackhole_agent.unbound import publish_lineage

    pushes: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tokens = [str(part) for part in command]
        if _is_push(tokens):
            pushes.append(tokens)
        return _delegate(tokens, **kwargs)

    with tempfile.TemporaryDirectory(prefix="bh-mismatch-push-") as directory:
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


def main() -> None:
    observed: dict[str, object] = {}
    try:
        post_buffer = exercise_post_buffer()
        handshake = exercise_handshake()
        mismatch = exercise_mismatch()
        observed = {
            "post_buffer": post_buffer,
            "handshake": handshake,
            "mismatch": mismatch,
        }
        passed = bool(
            post_buffer["ok"]
            and post_buffer["push_count"] == 2
            and post_buffer["enlarged"]
            and post_buffer["remote_matches"]
            and handshake["ok"] is False
            and handshake["push_count"] == 1
            and handshake["enlarged"] is False
            and handshake["remote_matches"] is False
            and mismatch["ok"] is False
            and mismatch["push_count"] == 0
            and mismatch["remote_unchanged"]
            and mismatch["refused"]
        )
    except Exception as error:  # noqa: BLE001 - probe must exit 0 with an unmet outcome
        observed = {"error": f"{error.__class__.__name__}: {error}"}
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
