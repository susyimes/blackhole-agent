"""Publication must see a protected path Git would otherwise hide.

A rename listed with git diff --name-only keeps only the new path, so moving
src/blackhole_agent/supervisor.py off its floor path used to look unprotected.
A governance filename Git prints as a C-quoted octal escape used to miss the
governance/ prefix. An unprotected README change still publishes, and a
listing that is not valid UTF-8 still blocks. Prints JSON with boolean passed
and nonempty observed. Exit 0 for both met and unmet outcomes.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _init(repo: Path) -> None:
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "probe@example.invalid")
    _git(repo, "config", "user.name", "probe")
    _git(repo, "config", "core.quotepath", "true")


def _commit_seed(repo: Path, *, judge: bool) -> str:
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    if judge:
        judge_dir = repo / "src" / "blackhole_agent"
        judge_dir.mkdir(parents=True)
        (judge_dir / "supervisor.py").write_text("JUDGE = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _gate(repo: Path, base: str, head: str):
    from blackhole_agent.protected_paths import evaluate_candidate_protected_paths

    return evaluate_candidate_protected_paths(
        target_repo_path=repo,
        candidate_repo_path=repo,
        target_before=base,
        candidate_head=head,
    )


def observe() -> tuple[bool, dict]:
    from blackhole_agent.protected_paths import evaluate_candidate_protected_paths

    with tempfile.TemporaryDirectory(prefix="bh-protected-rename-") as directory:
        root = Path(directory)

        rename_repo = root / "rename"
        _init(rename_repo)
        rename_base = _commit_seed(rename_repo, judge=True)
        _git(
            rename_repo,
            "mv",
            "src/blackhole_agent/supervisor.py",
            "src/blackhole_agent/moved_judge.py",
        )
        _git(rename_repo, "commit", "-m", "rename judge")
        renamed = _gate(rename_repo, rename_base, _head(rename_repo))

        quoted_repo = root / "quoted"
        _init(quoted_repo)
        quoted_base = _commit_seed(quoted_repo, judge=False)
        note_name = "\u00e9note.json"
        (quoted_repo / "governance").mkdir()
        (quoted_repo / "governance" / note_name).write_text("{}\n", encoding="utf-8")
        _git(quoted_repo, "add", "-A")
        _git(quoted_repo, "commit", "-m", "quoted governance name")
        quoted = _gate(quoted_repo, quoted_base, _head(quoted_repo))

        readme_repo = root / "readme"
        _init(readme_repo)
        readme_base = _commit_seed(readme_repo, judge=True)
        (readme_repo / "README.md").write_text("readme changed\n", encoding="utf-8")
        _git(readme_repo, "add", "-A")
        _git(readme_repo, "commit", "-m", "readme only")
        readme = _gate(readme_repo, readme_base, _head(readme_repo))

        edit_repo = root / "edit"
        _init(edit_repo)
        edit_base = _commit_seed(edit_repo, judge=True)
        (edit_repo / "src" / "blackhole_agent" / "supervisor.py").write_text(
            "JUDGE = 2\n",
            encoding="utf-8",
        )
        _git(edit_repo, "add", "-A")
        _git(edit_repo, "commit", "-m", "edit judge")
        edited = _gate(edit_repo, edit_base, _head(edit_repo))

        def corrupt_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=bytes([0xCE]) + b"src/blackhole_agent/supervisor.py\n",
                stderr=b"",
            )

        corrupt = evaluate_candidate_protected_paths(
            target_repo_path=root,
            candidate_repo_path=root,
            target_before="base",
            candidate_head="cand",
            command_runner=corrupt_runner,
        )

    quoted_path = "governance/\u00e9note.json"
    observed = {
        "rename_blocked": bool(renamed.blocked),
        "rename_touched": list(renamed.touched),
        "rename_reason": renamed.reason,
        "quoted_blocked": bool(quoted.blocked),
        "quoted_touched": list(quoted.touched),
        "readme_blocked": bool(readme.blocked),
        "readme_touched": list(readme.touched),
        "edit_blocked": bool(edited.blocked),
        "edit_touched": list(edited.touched),
        "corrupt_blocked": bool(corrupt.blocked),
        "corrupt_reason": corrupt.reason,
    }
    passed = (
        observed["rename_blocked"] is True
        and "src/blackhole_agent/supervisor.py" in observed["rename_touched"]
        and observed["quoted_blocked"] is True
        and quoted_path in observed["quoted_touched"]
        and observed["readme_blocked"] is False
        and observed["edit_blocked"] is True
        and "src/blackhole_agent/supervisor.py" in observed["edit_touched"]
        and observed["corrupt_blocked"] is True
        and "utf-8" in observed["corrupt_reason"].lower()
    )
    return passed, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": type(exc).__name__, "detail": str(exc)[:400]}
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
