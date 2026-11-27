"""A till and its Python worker issue receipts during a checkout sweep and Git replay."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


TILL = """import json, os
from pathlib import Path

def sale(units):
    book = Path(os.environ["BLACKHOLE_DURABLE_ROOT"]) / "receipts"
    book.parent.mkdir(parents=True, exist_ok=True)
    with book.open("a+", encoding="ascii") as entries:
        entries.seek(0)
        number = len(entries.readlines()) + 1
        cents = PRICE
        print(cents, file=entries)
    return [number, cents]

if __name__ == "__main__":
    print(json.dumps(sale(3)))
"""
ORDER = """import json, subprocess, sys
from till import sale

counter = sale(3)
worker = json.loads(subprocess.check_output([sys.executable, "-m", "till"], timeout=10))
print(json.dumps({"passed": [counter, worker] == [[1, EXPECTED], [2, EXPECTED]], "observed": [counter, worker]}))
"""


def main():
    try:
        from blackhole_agent import acceptance_sweep
        from blackhole_agent.behavior_acceptance import replay_behavior_acceptance
    except ImportError as exc:
        return {"passed": False, "observed": str(exc)}

    with tempfile.TemporaryDirectory(prefix="till-sweep-") as directory:
        root = Path(directory)
        shop = root / "shop checkout"
        probes = shop / "tests" / "acceptance"
        probes.mkdir(parents=True)
        source = shop / "src"
        source.mkdir()
        foreign = root / "other checkout" / "src"
        foreign.mkdir(parents=True)
        (foreign / "till.py").write_text(TILL.replace("PRICE", "999"), encoding="utf-8")
        till = source / "till.py"
        till.write_text(TILL.replace("PRICE", "units * 125"), encoding="utf-8")
        for args in (["init", "-q"], ["add", "src"], ["commit", "-qm", "full-price orders"]):
            subprocess.run(
                ["git", "-c", "user.name=Till", "-c", "user.email=till@example.invalid",
                 "-c", "commit.gpgSign=false", "-c", "core.hooksPath=.no-hooks", *args],
                cwd=shop, capture_output=True, check=True, timeout=15,
            )
        till.write_text(TILL.replace("PRICE", "(units - units // 3) * 125"), encoding="utf-8")
        for name, price in (("test_discount", 250), ("test_full_price", 375)):
            (probes / f"{name}.py").write_text(ORDER.replace("EXPECTED", str(price)), encoding="utf-8")
        (probes / "helper.py").write_text("raise RuntimeError('not a probe')", encoding="utf-8")

        def sweep(repo):
            runner = Path(acceptance_sweep.__file__).resolve().parents[1]
            result = subprocess.run(
                [sys.executable, "-m", "blackhole_agent.acceptance_sweep", "--repo", str(repo)],
                cwd=root, env={**os.environ, "PYTHONPATH": os.pathsep.join(map(str, (runner, foreign)))},
                capture_output=True, check=False, timeout=30,
            )
            try:
                report = json.loads(result.stdout)
            except ValueError:
                return {"exit": result.returncode, "stderr": result.stderr.decode("utf-8", "replace")[-400:]}
            return {
                "exit": result.returncode, "ok": report["ok"],
                "counts": [report[k] for k in ("total", "met", "unmet", "crashed")],
                "sales": {
                    Path(row["path"]).stem: [row["exit_code"], row["passed"], row["observed"]]
                    for row in report["probes"]
                },
            }

        relative, absolute = sweep(shop.name), sweep(shop)
        with patch.dict(os.environ, {"PYTHONPATH": str(foreign)}):
            replay = replay_behavior_acceptance(shop, "HEAD", "tests/acceptance/test_discount.py")
        sides = [replay.get(side, {}).get("outcome") for side in ("baseline", "candidate")]
        (probes / "test_fault.py").write_text("raise SystemExit(3)", encoding="utf-8")
        fault = sweep(shop)

    sales = [[1, 250], [2, 250]]
    rows = {"test_discount": [0, True, sales], "test_full_price": [0, False, sales]}
    healthy = {"exit": 0, "ok": True, "counts": [2, 1, 1, 0], "sales": rows}
    failed = {"exit": 1, "ok": False, "counts": [3, 1, 1, 1], "sales": {**rows, "test_fault": [3, None, None]}}
    passed = relative == absolute == healthy and fault == failed and replay["ok"] and sides == [
        {"passed": False, "observed": [[1, 375], [2, 375]]}, {"passed": True, "observed": sales},
    ]
    observed = {"relative": relative, "absolute": absolute, "git_replay": sides, "fault": fault}
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main()))
