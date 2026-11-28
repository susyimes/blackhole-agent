"""Compare replayed invoice translations with receipts rendered in detached Git checkouts."""

import json
import runpy
import subprocess
import tempfile
from pathlib import Path

from blackhole_agent.behavior_acceptance import replay_behavior_acceptance


PROBE = "tests/acceptance/invoice.py"
CATALOG = "locales/[fr]/labels.json"
TEMPLATE = "forms/invoice [plain].txt"
APPLICATION = """from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]

def receipt():
    catalog = root / 'locales' / '[fr]' / 'labels.json'
    form = root / 'forms' / 'invoice [plain].txt'
    labels = json.loads(catalog.read_text(encoding='utf-8')) if catalog.exists() else {}
    try:
        template = form.read_bytes().decode('utf-16') if form.exists() else '{status}'
    except UnicodeDecodeError:
        return 'Unreadable invoice form'
    return template.format(status=labels.get('paid', 'payment.status'))
"""
HEADERS = f"# replay-input: locales/[fr]\n# replay-input: {TEMPLATE}\n"
INVOICE_PROBE = """import json
from invoice import receipt

rendered = receipt()
print(json.dumps({'passed': rendered.rstrip('\\r\\n') == 'Facture réglée', 'observed': rendered}))
"""


def git(root, *args):
    return subprocess.check_output(
        ["git", "-c", "user.name=Replay", "-c", "user.email=replay@example.invalid",
         "-c", "commit.gpgSign=false", "-c", "core.hooksPath=.no-hooks", *args],
        cwd=root, stderr=subprocess.PIPE, text=True, encoding="utf-8", timeout=15,
    ).strip()


def observe(scratch):
    root = scratch / "workspace"
    git(scratch, "init", "-q", root.name)

    def write(path, content):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def commit(label):
        git(root, "add", "-A")
        git(root, "commit", "-qm", label)
        return git(root, "rev-parse", "HEAD")

    def replay(revision, probe=PROBE):
        result = replay_behavior_acceptance(root, revision, probe)
        return {
            "accepted": result["ok"],
            "receipts": [result.get(side, {}).get("outcome", {}).get("observed") for side in ("baseline", "candidate")],
            "error": result.get("error", ""),
        }

    write("src/invoice.py", APPLICATION.replace("decode('utf-16')", "decode('utf-8')"))
    write(PROBE, HEADERS + INVOICE_PROBE)
    write(".gitattributes", "*.json export-ignore\n")
    write("forms/.gitattributes", "*.txt text eol=crlf working-tree-encoding=UTF-16\n")
    (root / TEMPLATE).write_bytes("Facture {status}\r\n".encode("utf-16"))
    without_catalog = commit("invoice before localization")
    write(CATALOG, json.dumps({"paid": "réglée"}))
    broken = commit("reader assumes UTF-8")
    write("src/invoice.py", APPLICATION)
    settled = commit("settled invoice")
    write(CATALOG, json.dumps({"paid": "en attente"}))
    pending = commit("pending invoice")
    reference = scratch / "reference"
    git(root, "worktree", "add", "-q", "--detach", "--no-checkout", str(reference), settled)

    def reference_receipt(revision):
        git(reference, "checkout", "-q", "--detach", revision)
        return runpy.run_path(str(reference / "src/invoice.py"))["receipt"]()

    unreadable, due, paid = [reference_receipt(revision) for revision in (broken, pending, settled)]

    write("forms/.gitattributes", "*.txt -text\n")
    git(root, "commit", "-qm", "retire the old export format", "--", "forms/.gitattributes")
    write(CATALOG, json.dumps({"paid": "index"}))
    git(root, "--literal-pathspecs", "add", CATALOG)
    write(CATALOG, json.dumps({"paid": "réglée"}))

    unchanged = replay(settled)
    changed = replay(pending)
    repaired = replay(broken)
    missing_baseline = replay(without_catalog)
    plain = "tests/acceptance/no_inputs.py"
    write(plain, INVOICE_PROBE)
    undeclared = replay(settled, plain)
    (root / TEMPLATE).unlink()
    missing_candidate = replay(pending)
    observed = {
        "git_receipts": [unreadable, due, paid],
        "unchanged": unchanged,
        "changed": changed,
        "repaired": repaired,
        "staged_label": json.loads(git(root, "show", ":" + CATALOG))["paid"],
        "undeclared": undeclared,
        "missing_baseline": missing_baseline,
        "missing_candidate": missing_candidate,
    }
    passed = (
        [unreadable, due, paid] == ["Unreadable invoice form", "Facture en attente\r\n", "Facture réglée\r\n"]
        and not unchanged["accepted"] and unchanged["receipts"] == [paid, paid]
        and changed["accepted"] and changed["receipts"] == [due, paid]
        and repaired["accepted"] and repaired["receipts"] == [unreadable, paid]
        and observed["staged_label"] == "index"
        and not undeclared["accepted"] and undeclared["receipts"] == ["payment.status", "payment.status"]
        and not missing_baseline["accepted"] and "locales/[fr]" in missing_baseline["error"]
        and missing_baseline["receipts"] == [None, None]
        and not missing_candidate["accepted"] and TEMPLATE in missing_candidate["error"]
        and missing_candidate["receipts"] == [None, None]
    )
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="invoice-replay-") as scratch:
        print(json.dumps(observe(Path(scratch)), ensure_ascii=True))
