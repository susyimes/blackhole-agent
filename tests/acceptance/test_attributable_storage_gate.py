"""Mission creation charges owned sessions and temporary outputs against the same cap."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from blackhole_agent import storage_budget as budget
from blackhole_agent.unbound import create_mission


def observe(root: Path, kind: str) -> dict:
    repo, home, temp = (root / name for name in ("repo", "home", "temp"))
    sessions = home / ".grok" / "sessions"
    for folder in (repo, sessions, temp):
        folder.mkdir(parents=True)
    payload = b"PAYLOAD-BYTES-UNCHANGED"
    (repo / "payload.bin").write_bytes(payload)
    parent = root / "destination"
    workspace = None
    reason = error_type = ""
    env = dict(TEMP=str(temp), TMP=str(temp), HOME=str(home), USERPROFILE=str(home), UV_OFFLINE="1")
    with patch.dict(os.environ, env):
        git = ["git", "-C", str(repo)]
        subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
        subprocess.run([*git, "add", "payload.bin"], check=True)
        subprocess.run([*git, "-c", "user.name=Probe", "-c", "user.email=p@example.invalid",
                        "commit", "-qm", "payload"], check=True)
        head = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
        checkout = budget.measure_roots(budget.mission_checkout_roots(repo))
        cap = checkout["logical_bytes"] + budget.checkout_growth_bytes(checkout, repo) + 1000
        if kind != "under":
            owned = sessions / "blackhole-agent-fixture" if kind == "session" else temp / "blackhole-oversize"
            owned.mkdir()
            (owned / "data").write_bytes(b"x" * cap)
        # The gate reloads on a different revision. Keep the fixture cap bound to this checkout.
        with patch.multiple(budget, create=True, LOADED_CONTROLLER_SHA=head, CAP_BYTES=cap, PREVENTIVE_BYTES=cap):
            try:
                state = create_mission(repo_path=repo, goal="Probe attributable storage authorization.",
                                       done_when="The checkout fits the shared budget.", worktree_parent=parent)
                workspace = Path(json.loads(state.read_text(encoding="utf-8"))["workspace_path"])
            except budget.StorageBudgetRefusal as exc:
                reason, error_type = exc.reason, type(exc).__name__
    return {
        "created": workspace is not None, "reason": reason, "error_type": error_type,
        "parent_exists": parent.exists(), "workspace_exists": workspace is not None and workspace.is_dir(),
        "payload_unchanged": (repo / "payload.bin").read_bytes() == payload, "cap_bytes": cap,
    }


def main():
    observed = {}
    passed = True
    try:
        with tempfile.TemporaryDirectory(prefix="ba-attr-gate-") as directory:
            for kind in ("session", "temp", "under"):
                row = observed[kind] = observe(Path(directory) / kind, kind)
                allowed = kind == "under"
                passed &= row["payload_unchanged"] and row["created"] == row["workspace_exists"] == allowed
                passed &= row["parent_exists"] == allowed
                if not allowed:
                    passed &= row["reason"] == "at_cap" and row["error_type"] == "StorageBudgetRefusal"
    except Exception as exc:
        observed["probe_error"] = f"{type(exc).__name__}: {exc}"
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
