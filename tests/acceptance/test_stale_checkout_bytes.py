"""Observe the files left on disk by worktrees-gc after Git metadata is lost."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from blackhole_agent.unbound import UnboundMission, mission_root, save_mission


def observe(root: Path) -> tuple[bool, dict]:
    repo = root / "repo"
    repo.mkdir()

    def git(*args: str) -> bytes:
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout

    git("init", "-b", "main")
    git("config", "core.autocrlf", "false")
    git("config", "core.symlinks", "false")
    attributes = repo / ".gitattributes"
    attributes.write_bytes(b"* -text\n*.bin binary\n*.lf text eol=lf\n*.win text eol=crlf\nstamp ident\n")
    (repo / ".gitignore").write_bytes(b"*.egg-info/\n__pycache__/\n!manual.pyc\n")
    files = {
        "sample.bin": b"\x00A\nB\n", "note.lf": b"line\n", "tool.egg-info/PKG-INFO": b"release\n",
        "two words.win": b"one\ntwo\n", "stamp": b"$Id$\n", "link": b"sample.bin",
    }
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
    git("add", "-f", ".")
    link_oid = git("rev-parse", ":link").decode().strip()
    git("update-index", "--cacheinfo", f"120000,{link_oid},link")
    git("-c", "user.name=Fixture", "-c", "user.email=gc@example.invalid", "commit", "-m", "published inputs")
    head = git("rev-parse", "HEAD").decode().strip()
    edits = {
        "binary": ("sample.bin", b"\x00A\r\nB\r\n"), "lf": ("note.lf", b"line\r\n"),
        "metadata": ("tool.egg-info/PKG-INFO", b"local draft\n"),
        "missing-cr": ("two words.win", b"one\ntwo\n"), "untracked": ("manual.pyc", b"user bytes\x00"),
    }
    parent = root / ".repo-unbound-worktrees"
    for ident in [*edits, "clean"]:
        checkout = parent / ident
        branch = "mission/" + ident
        git("worktree", "add", "-b", branch, str(checkout), head)
        if ident in edits:
            # Interrupted cleanup can leave just part of the original checkout.
            (checkout / ".git").unlink()
            (checkout / "stamp").unlink()
            name, content = edits[ident]
            (checkout / name).write_bytes(content)
        state = UnboundMission(
            schema_version=1, mission_id=ident, created_at="2026-01-01", updated_at="2026-01-01",
            repo_path=str(repo), workspace_path=str(checkout), branch=branch, target_branch="main",
            status="complete", base_head=head, last_milestone_head=head,
        )
        save_mission(mission_root(repo) / "missions" / ident / "state.json", state)

    clean = parent / "clean"
    marker = clean / ".git"
    clean_gitfile = marker.read_bytes()
    marker.unlink()
    git("worktree", "prune", "--expire", "now")
    marker.write_bytes(clean_gitfile)
    (clean / "__pycache__").mkdir()
    (clean / "__pycache__" / "generated.pyc").write_bytes(b"disposable cache")
    crlf = (clean / "two words.win").read_bytes()
    expanded = (clean / "stamp").read_bytes()
    stamp_oid = git("rev-parse", head + ":stamp").strip()
    # The owning checkout now has different attributes from the published mission.
    attributes.write_bytes(b"* -text -ident\n")
    git("-c", "user.name=Fixture", "-c", "user.email=gc@example.invalid", "commit", "-am", "change checkout rules")
    git("init", "--bare", str(root / "origin.git"))
    git("remote", "add", "origin", str(root / "origin.git"))
    git("push", "origin", "main")
    index = repo / ".git" / "index"
    before = index.read_bytes()
    command = [sys.executable, "-m", "blackhole_agent.unbound", "worktrees-gc", "--repo-path", str(repo),
               "--keep-recent", "0"]
    report = json.loads(subprocess.check_output(command, cwd=root))
    retained = {}
    for ident, (name, _) in edits.items():
        path = parent / ident / name
        retained[ident] = path.read_bytes().hex() if path.is_file() else None
    removed = [row["mission_id"] for row in report["reclaimed"] if row["removed"]]
    observed = {
        "retained_hex": retained, "removed": removed, "clean_exists": clean.exists(),
        "checkout_crlf_hex": crlf.hex(), "checkout_ident": expanded.decode().strip(),
        "owner_index_intact": index.read_bytes() == before,
    }
    passed = (
        report["ok"] and retained == {i: data.hex() for i, (_, data) in edits.items()}
        and removed == ["clean"] and not clean.exists() and observed["owner_index_intact"]
        and crlf == b"one\r\ntwo\r\n" and expanded == b"$Id: " + stamp_oid + b" $\n"
    )
    return passed, observed


if __name__ == "__main__":
    try:
        with tempfile.TemporaryDirectory(prefix="bh-stale-checkout-") as directory:
            passed, observed = observe(Path(directory))
    except Exception as error:
        passed, observed = False, {"error": str(error)}
    print(json.dumps({"passed": passed, "observed": observed}))
