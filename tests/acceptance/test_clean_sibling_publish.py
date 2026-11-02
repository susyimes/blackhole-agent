"""Publish a clean remote sibling as a fast-forward merge.

Harvested 2026-11-02: origin/main and the proved lineage were children of the
same parent, their files did not overlap, and publication refused with a
remote-head mismatch. The remote head stayed put, so the proved commit never
landed.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"git {' '.join(arguments)} exited {completed.returncode}")
    return (completed.stdout or "").strip()


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "pub@test.local")
    _git(repo, "config", "user.name", "Pub Test")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "seed")
    return repo


def _bare_remote(root: Path, repo: Path) -> Path:
    remote = root / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(repo, "remote", "add", "origin", remote.as_posix())
    _git(repo, "push", "-u", "origin", "main")
    return remote


def _remote_head(remote: Path) -> str:
    completed = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (completed.stdout or "").strip()


def _sibling_pair(root: Path, *, remote_name: str, remote_body: str, local_name: str, local_body: str) -> tuple[Path, Path, str, str]:
    repo = _init_repo(root)
    remote = _bare_remote(root, repo)
    seed = _git(repo, "rev-parse", "HEAD")
    (repo / remote_name).write_text(remote_body, encoding="utf-8")
    _git(repo, "add", remote_name)
    _git(repo, "commit", "-m", "remote sibling")
    remote_tip = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "origin", "main")
    _git(repo, "checkout", "-B", "lineage", seed)
    (repo / local_name).write_text(local_body, encoding="utf-8")
    _git(repo, "add", local_name)
    _git(repo, "commit", "-m", "lineage sibling")
    lineage_tip = _git(repo, "rev-parse", "HEAD")
    return repo, remote, remote_tip, lineage_tip


def _show(repo: Path, rev: str) -> str:
    return _git(repo, "show", rev)


def main() -> None:
    from blackhole_agent.unbound import publish_lineage

    observed: dict[str, object] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="bh-clean-sibling-") as directory:
            root = Path(directory)
            repo, remote, remote_tip, lineage_tip = _sibling_pair(
                root,
                remote_name="remote-only.txt",
                remote_body="remote\n",
                local_name="lineage-only.txt",
                local_body="lineage\n",
            )
            result = publish_lineage(repo, lineage_tip, "origin", "main")
            landed = _remote_head(remote)
            first_parent = ""
            second_parent = ""
            remote_text = ""
            lineage_text = ""
            ancestor = False
            if result.ok and landed:
                first_parent = _git(repo, "rev-parse", f"{landed}^1")
                second_parent = _git(repo, "rev-parse", f"{landed}^2")
                remote_text = _show(repo, f"{landed}:remote-only.txt")
                lineage_text = _show(repo, f"{landed}:lineage-only.txt")
                ancestor = (
                    subprocess.run(
                        ["git", "merge-base", "--is-ancestor", remote_tip, landed],
                        cwd=repo,
                        capture_output=True,
                        text=True,
                    ).returncode
                    == 0
                )
            observed["clean"] = {
                "ok": result.ok,
                "error": result.error,
                "remote_before": result.remote_before,
                "lineage_tip": lineage_tip,
                "landed": landed,
                "first_parent": first_parent,
                "second_parent": second_parent,
                "remote_text": remote_text,
                "lineage_text": lineage_text,
                "fast_forward": ancestor,
            }

        with tempfile.TemporaryDirectory(prefix="bh-conflict-sibling-") as directory:
            root = Path(directory)
            repo, remote, remote_tip, lineage_tip = _sibling_pair(
                root,
                remote_name="shared.txt",
                remote_body="remote\n",
                local_name="shared.txt",
                local_body="lineage\n",
            )
            before = _remote_head(remote)
            result = publish_lineage(repo, lineage_tip, "origin", "main")
            observed["conflict"] = {
                "ok": result.ok,
                "refused": "remote-head mismatch" in result.error,
                "remote_unchanged": _remote_head(remote) == before,
                "remote_before": result.remote_before == remote_tip,
            }

        with tempfile.TemporaryDirectory(prefix="bh-unrelated-sibling-") as directory:
            root = Path(directory)
            repo = _init_repo(root)
            remote = _bare_remote(root, repo)
            _git(repo, "checkout", "--orphan", "diverged")
            (repo / "other.md").write_text("diverged\n", encoding="utf-8")
            _git(repo, "add", "other.md")
            _git(repo, "commit", "-m", "unrelated")
            unrelated = _git(repo, "rev-parse", "HEAD")
            before = _remote_head(remote)
            result = publish_lineage(repo, unrelated, "origin", "main")
            observed["unrelated"] = {
                "ok": result.ok,
                "refused": "remote-head mismatch" in result.error,
                "remote_unchanged": _remote_head(remote) == before,
            }

        clean = observed["clean"]
        conflict = observed["conflict"]
        unrelated = observed["unrelated"]
        passed = bool(
            isinstance(clean, dict)
            and clean["ok"] is True
            and clean["first_parent"] == clean["remote_before"]
            and clean["second_parent"]
            and clean["remote_text"] == "remote"
            and clean["lineage_text"] == "lineage"
            and clean["second_parent"] == clean["lineage_tip"]
            and clean["fast_forward"] is True
            and clean["landed"] not in {clean["remote_before"], clean["lineage_tip"]}
            and isinstance(conflict, dict)
            and conflict["ok"] is False
            and conflict["refused"] is True
            and conflict["remote_unchanged"] is True
            and isinstance(unrelated, dict)
            and unrelated["ok"] is False
            and unrelated["refused"] is True
            and unrelated["remote_unchanged"] is True
        )
    except Exception as error:  # noqa: BLE001 - probe must exit 0 for unmet outcomes
        observed["error"] = str(error) or error.__class__.__name__
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
