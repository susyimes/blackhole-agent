"""Outcome probe: a published commit becomes the controller checkout.

A clean controller checkout that is behind a published descendant commit is
fast-forwarded so HEAD equals that commit, and a fresh interpreter reads the
marker file that exists only at the published value. A dirty checkout stays
put. A commit that is not a descendant is refused, and no command resets
history. The previous milestone leaves the checkout behind, so the same probe
reports passed=false. Both outcomes exit 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
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
        check=True,
    )
    return (completed.stdout or "").strip()


def _init(root: Path) -> Path:
    repo = root / "controller"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "controller@test.local")
    _git(repo, "config", "user.name", "Controller Test")
    _git(repo, "config", "core.autocrlf", "false")
    source = repo / "src"
    source.mkdir()
    (source / "published_marker.py").write_text('VALUE = "stale"\n', encoding="utf-8")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "src/published_marker.py", "README.md")
    _git(repo, "commit", "-m", "stale controller")
    return repo


def _publish(repo: Path) -> str:
    _git(repo, "checkout", "-b", "published")
    (repo / "src" / "published_marker.py").write_text('VALUE = "published"\n', encoding="utf-8")
    _git(repo, "add", "src/published_marker.py")
    _git(repo, "commit", "-m", "publish controller")
    published = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", published)
    _git(repo, "checkout", "main")
    return published


def _diverge(repo: Path) -> str:
    _git(repo, "checkout", "-b", "side")
    (repo / "src" / "published_marker.py").write_text('VALUE = "side"\n', encoding="utf-8")
    _git(repo, "add", "src/published_marker.py")
    _git(repo, "commit", "-m", "side commit")
    side = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "main")
    (repo / "README.md").write_text("local edit\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "local main")
    return side


def _read_marker(repo: Path) -> str:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import importlib, sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(sys.argv[1]) / 'src'))\n"
                "mod = importlib.import_module('published_marker')\n"
                "sys.stdout.write(mod.VALUE)\n"
            ),
            str(repo),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def _uses_reset(report: dict) -> bool:
    if report.get("reset_used") is True:
        return True
    for command in report.get("commands") or []:
        parts = str(command).split()
        if "reset" in parts or "--hard" in parts:
            return True
    return False


def _scenario_clean(parent: Path, adopt) -> dict:
    repo = _init(parent / "clean")
    published = _publish(repo)
    before = _git(repo, "rev-parse", "HEAD")
    report = adopt(repo, published)
    return {
        "adopted": report.get("adopted"),
        "moved": report.get("moved"),
        "reason": report.get("reason"),
        "head_before": before,
        "head_after": _git(repo, "rev-parse", "HEAD"),
        "published": published,
        "marker": _read_marker(repo),
        "reset_used": _uses_reset(report),
    }


def _scenario_dirty(parent: Path, adopt) -> dict:
    repo = _init(parent / "dirty")
    published = _publish(repo)
    (repo / "README.md").write_text("dirty local\n", encoding="utf-8")
    before = _git(repo, "rev-parse", "HEAD")
    report = adopt(repo, published)
    return {
        "adopted": report.get("adopted"),
        "reason": report.get("reason"),
        "head_before": before,
        "head_after": _git(repo, "rev-parse", "HEAD"),
        "readme": (repo / "README.md").read_text(encoding="utf-8"),
        "reset_used": _uses_reset(report),
    }


def _scenario_diverged(parent: Path, adopt) -> dict:
    repo = _init(parent / "diverged")
    side = _diverge(repo)
    before = _git(repo, "rev-parse", "HEAD")
    readme = (repo / "README.md").read_text(encoding="utf-8")
    report = adopt(repo, side)
    return {
        "adopted": report.get("adopted"),
        "reason": report.get("reason"),
        "head_before": before,
        "head_after": _git(repo, "rev-parse", "HEAD"),
        "readme": (repo / "README.md").read_text(encoding="utf-8"),
        "readme_before": readme,
        "reset_used": _uses_reset(report),
    }


def _passed(clean: dict, dirty: dict, diverged: dict) -> bool:
    return (
        clean.get("adopted") is True
        and clean.get("moved") is True
        and clean.get("head_after") == clean.get("published")
        and clean.get("head_before") != clean.get("published")
        and clean.get("marker") == "published"
        and clean.get("reset_used") is False
        and dirty.get("adopted") is False
        and dirty.get("reason") == "dirty"
        and dirty.get("head_after") == dirty.get("head_before")
        and dirty.get("readme") == "dirty local\n"
        and dirty.get("reset_used") is False
        and diverged.get("adopted") is False
        and diverged.get("reason") == "not_fast_forward"
        and diverged.get("head_after") == diverged.get("head_before")
        and diverged.get("readme") == diverged.get("readme_before")
        and diverged.get("reset_used") is False
    )


def main() -> None:
    observed: dict = {"imported": False}
    try:
        from blackhole_agent.controller_adoption import adopt_published_controller
    except Exception as exc:
        adopt_published_controller = None
        observed["import_error"] = exc.__class__.__name__

    with tempfile.TemporaryDirectory(prefix="controller-adopt-") as temporary:
        parent = Path(temporary)
        if adopt_published_controller is None:
            repo = _init(parent / "baseline")
            published = _publish(repo)
            head = _git(repo, "rev-parse", "HEAD")
            observed.update(
                {
                    "head": head,
                    "published": published,
                    "marker": _read_marker(repo),
                    "adopted": False,
                }
            )
            passed = False
        else:
            observed["imported"] = True
            clean = _scenario_clean(parent, adopt_published_controller)
            dirty = _scenario_dirty(parent, adopt_published_controller)
            diverged = _scenario_diverged(parent, adopt_published_controller)
            observed.update({"clean": clean, "dirty": dirty, "diverged": diverged})
            passed = _passed(clean, dirty, diverged)
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
