"""Publish independently registered commands and invoke them from the receiving checkout."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.capability_compounder import load_ledger, run_capability
from blackhole_agent.unbound import publish_lineage

LEDGER = "capabilities/ledger.json"


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, stderr=subprocess.PIPE, encoding="utf-8").strip()


def command(name, **changes):
    return {"id": name, "name": name, "kind": "command", "entry": f"git show HEAD:{name}.txt",
            "proof_command": "git status", "dependencies": [], "tags": [], **changes}


def write_ledger(repo, rows, stamp):
    document = {"schema_version": 1, "updated_at": stamp, "capabilities": rows}
    (repo / LEDGER).write_text(json.dumps(document, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def observe(root):
    writer, bare, consumer = (root / part for part in ("writer", "receiver.git", "consumer"))
    git(root, "init", "-qb", "main", str(writer))
    git(writer, "config", "user.name", "Publisher")
    git(writer, "config", "user.email", "publisher@example.invalid")
    git(root, "init", "--bare", "-q", str(bare))
    (writer / "capabilities").mkdir()
    rows = {name: command(name) for name in ("anchor", "obsolete")}
    epoch = "2026-01-01T00:00:00Z"
    write_ledger(writer, rows, epoch)
    note = writer / "shared.txt"
    note.write_text("original\n", encoding="utf-8")
    git(writer, "add", ".")
    git(writer, "commit", "-qm", "initial catalog")
    base = git(writer, "rev-parse", "HEAD")
    observed = {}
    refusals = {"same_record": "anchor", "delete_dependency": "obsolete",
                "source_conflict": "remote-head mismatch", "protected": "governance/policy"}
    for case in ("independent", *refusals):
        tips = []
        for side, stamp in (("peer", "2026-01-02T00:00:00Z"), ("mission", "2026-01-03T00:00:00Z")):
            git(writer, "switch", "--detach", base)
            catalog = {key: dict(value) for key, value in rows.items()}
            if case == "same_record":
                # Git can text-merge these separated fields into a command nobody registered.
                field = "entry" if side == "peer" else "tags"
                catalog["anchor"][field] = "git status --short" if side == "peer" else ["reviewed"]
            else:
                catalog["anchor"]["updated_at"] = stamp
                catalog[side] = command(side, extension={"writer": side})
                (writer / f"{side}.txt").write_text(f"{side} payload\n", encoding="utf-8")
                if side == "peer":
                    del catalog["obsolete"]
                elif case == "delete_dependency":
                    catalog[side]["dependencies"] = ["obsolete"]
                if case == "source_conflict":
                    note.write_text(side + "\n", encoding="utf-8")
                if case == "protected" and side == "mission":
                    (writer / "governance").mkdir()
                    (writer / "governance" / "policy").write_text("requires review\n", encoding="utf-8")
            write_ledger(writer, catalog, epoch if case == "same_record" else stamp)
            git(writer, "add", ".")
            git(writer, "commit", "-qm", f"{side} {case}")
            tips.append(git(writer, "rev-parse", "HEAD"))
        peer, mission = tips
        ref = f"refs/heads/{case}"
        git(writer, "push", str(bare), f"{peer}:{ref}")
        note.write_text("staged operator draft\n", encoding="utf-8")
        git(writer, "add", "shared.txt")
        note.write_text("unstaged operator draft\n", encoding="utf-8")
        before = git(writer, "write-tree"), note.read_bytes()
        result = publish_lineage(writer, mission, str(bare), case)
        head = git(bare, "rev-parse", ref)
        kept = (git(writer, "write-tree"), note.read_bytes()) == before and git(writer, "rev-parse", "HEAD") == mission
        row = {"published": result.ok, "receiver_unchanged": head == peer, "draft_preserved": kept,
               "error": result.error}
        if case == "independent":
            git(root, "clone", "--no-local", "-qb", case, str(bare), str(consumer))
            ledger = load_ledger(consumer / LEDGER)
            outputs = {}
            for name in ("peer", "mission"):
                if name in ledger.capabilities:
                    run = run_capability(ledger.capabilities[name], cwd=consumer)
                    outputs[name] = run.stdout if run.ok else run.stderr
            published = json.loads((consumer / LEDGER).read_bytes())["capabilities"]
            row.update(
                outputs=outputs, parents_match=git(bare, "show", "-s", "--format=%P", ref).split() == tips,
                extension_values=[published.get(name, {}).get("extension") for name in ("peer", "mission")],
                anchor_stamp=published["anchor"].get("updated_at"), obsolete_removed="obsolete" not in published,
            )
            row["met"] = (
                result.ok and result.remote_after == head and row["parents_match"] and row["obsolete_removed"]
                and row["extension_values"] == [{"writer": "peer"}, {"writer": "mission"}]
                and row["anchor_stamp"] == "2026-01-03T00:00:00Z"
                and outputs == {"peer": "peer payload", "mission": "mission payload"}
            )
        else:
            row["met"] = not result.ok and head == peer and refusals[case] in result.error
        observed[case] = row
        git(writer, "restore", "--staged", "--worktree", "--", "shared.txt")
    return {"passed": all(row["met"] and row["draft_preserved"] for row in observed.values()), "observed": observed}


def test_registry_publication(tmp_path):
    result = observe(tmp_path)
    assert result["passed"], result


if __name__ == "__main__":
    os.environ.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    try:
        with tempfile.TemporaryDirectory(prefix="bh-registry-publish-") as directory:
            verdict = observe(Path(directory))
    except Exception as error:
        verdict = {"passed": False, "observed": {"error": str(error), "detail": str(getattr(error, "stderr", ""))}}
    print(json.dumps(verdict))
