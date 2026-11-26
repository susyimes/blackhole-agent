"""A replay distinguishes a real invoice translation edit from an unchanged receipt."""

import json
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
    template = form.read_text(encoding='utf-8') if form.exists() else '{status}'
    return template.format(status=labels.get('paid', 'payment.status'))
"""
HEADERS = f"# replay-input: locales/[fr]\n# replay-input: {TEMPLATE}\n"
INVOICE_PROBE = """import json
from invoice import receipt

rendered = receipt()
print(json.dumps({'passed': rendered == 'Facture réglée', 'observed': rendered}))
"""


def git(root, *args):
    return subprocess.check_output(
        ["git", "-c", "user.name=Replay", "-c", "user.email=replay@example.invalid",
         "-c", "commit.gpgSign=false", "-c", "core.hooksPath=.no-hooks", *args],
        cwd=root, stderr=subprocess.PIPE, text=True, encoding="utf-8", timeout=15,
    ).strip()


def observe(root):
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

    git(root, "init", "-q")
    write("src/invoice.py", APPLICATION)
    write(PROBE, HEADERS + INVOICE_PROBE)
    write(".gitattributes", "*.json export-ignore\n")
    write(TEMPLATE, "Facture {status}")
    without_catalog = commit("invoice before localization")
    write(CATALOG, json.dumps({"paid": "réglée"}))
    settled = commit("settled invoice")
    write(CATALOG, json.dumps({"paid": "en attente"}))
    pending = commit("pending invoice")
    write(CATALOG, json.dumps({"paid": "index"}))
    git(root, "add", "-u")
    write(CATALOG, json.dumps({"paid": "réglée"}))

    unchanged = replay(settled)
    changed = replay(pending)
    missing_baseline = replay(without_catalog)
    plain = "tests/acceptance/no_inputs.py"
    write(plain, INVOICE_PROBE)
    undeclared = replay(settled, plain)
    (root / TEMPLATE).unlink()
    missing_candidate = replay(pending)
    observed = {
        "unchanged": unchanged,
        "changed": changed,
        "undeclared": undeclared,
        "missing_baseline": missing_baseline,
        "missing_candidate": missing_candidate,
    }
    passed = (
        not unchanged["accepted"] and unchanged["receipts"] == ["Facture réglée", "Facture réglée"]
        and changed["accepted"] and changed["receipts"] == ["Facture en attente", "Facture réglée"]
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
