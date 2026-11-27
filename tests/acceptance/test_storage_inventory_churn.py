"""Change actual directory membership at the start of a budget walk, without timing sleeps."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from blackhole_agent import storage_budget as budget
from blackhole_agent.unbound import app, create_mission


def observe(root, entry, change, size):
    repo, temp, home = (root / name for name in ("repo", "temp", "home"))
    for folder in (repo, temp, home):
        folder.mkdir(parents=True)
    (repo / "payload").write_bytes(b"checkout data")
    old, new = temp / "blackhole-acceptance-old", temp / "ba-replacement"
    old.mkdir()
    pending = root / "pending"
    pending.mkdir()
    (pending / "data").write_bytes(b"x" * size)
    trigger = repo
    if change == "reuse_name":
        new = old
        trigger = old / "marker"
        trigger.mkdir()
        (pending / "marker").mkdir()
    destination = root / "worktrees"
    receipt = root / "receipt.json"
    mutations = 0
    armed = True

    def rotate(event, args):
        nonlocal mutations
        if not armed or event != "os.scandir" or args[0] not in (trigger, str(trigger)):
            return
        if change == "churn":
            if mutations >= 4:
                raise RuntimeError("inventory did not settle or refuse")
            source, target = (new, old) if mutations % 2 else (old, new)
            source.rename(target)
        elif mutations:
            return
        else:
            if change in ("replace", "reuse_name"):
                old.rename(root / "retired")
            pending.rename(new)
        mutations += 1

    # The hook schedules a filesystem event. All discovery, accounting, Git and
    # authorization calls still execute against the real temporary directories.
    sys.addaudithook(rotate)
    environment = dict(TEMP=str(temp), TMP=str(temp), HOME=str(home), USERPROFILE=str(home), UV_OFFLINE="1")
    try:
        with patch.dict(os.environ, environment):
            if entry == "cli":
                result = CliRunner().invoke(app, [
                    "storage-budget", "--repo-path", str(repo), "--receipt", str(receipt),
                    "--additional-bytes", str(budget.CAP_BYTES - 1024),
                ])
                if result.exit_code:
                    raise RuntimeError(result.output) from result.exception
            else:
                git = ["git", "-C", str(repo)]
                subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
                subprocess.run([*git, "add", "payload"], check=True)
                subprocess.run([*git, "-c", "user.name=Probe", "-c", "user.email=p@example.invalid",
                                "commit", "-qm", "fixture"], check=True)
                head = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
                # Bind the configurable test cap to this Git checkout, as the controller does.
                with patch.multiple(budget, LOADED_CONTROLLER_SHA=head, CAP_BYTES=131072, PREVENTIVE_BYTES=131072):
                    try:
                        create_mission(repo_path=repo, goal="Inventory probe", done_when="checkout exists",
                                       worktree_parent=destination)
                    except budget.StorageBudgetRefusal:
                        pass
                receipt = repo / ".blackhole-agent" / "unbound" / "storage-budget.json"
    finally:
        armed = False
    report = json.loads(receipt.read_text(encoding="utf-8"))
    after = report["measurement_after"]
    roots = {Path(item["root"]): item["logical_bytes"] for item in after["roots"]}
    checkout = any(path.read_bytes() == b"checkout data" for path in destination.glob("*/payload"))
    return dict(reason=report["expansion"]["reason"], allowed=report["expansion"]["allowed"],
                complete=after["complete"], replacement_bytes=roots.get(new), checkout=checkout,
                destination=destination.exists(), mutations=mutations)


def main():
    observed = {}
    passed = True
    try:
        with tempfile.TemporaryDirectory(prefix="storage-inventory-") as folder:
            for entry in ("cli", "checkout"):
                for change, size in (("replace", 32), ("birth", 262144), ("reuse_name", 262144), ("churn", 0)):
                    name = f"{entry}_{change}"
                    row = observed[name] = observe(Path(folder) / name, entry, change, size)
                    allowed = change == "replace"
                    reason = {"replace": "within_cap", "churn": "measurement_incomplete"}.get(
                        change, "would_cross_cap" if entry == "cli" else "at_cap",
                    )
                    passed &= row["reason"] == reason and row["allowed"] == allowed
                    passed &= row["complete"] == (change != "churn") and 1 <= row["mutations"] <= 2
                    passed &= row["checkout"] == row["destination"] == (allowed and entry == "checkout")
                    if change != "churn":
                        passed &= row["replacement_bytes"] == size
            missing = budget.govern_expansion([Path(folder) / "missing"])
            observed["declared_missing"] = missing["expansion"]["reason"]
            passed &= observed["declared_missing"] == "measurement_incomplete"
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        passed = False
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
