# replay-input: uv.lock
"""Each till run reports its CLI exit, resumed shard count and actual test executions."""

import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


SALE = """from pathlib import Path

def test_sale():
    order = Path('../repair-once')
    if order.exists():
        Path('src/till.py').write_bytes(order.read_bytes())
        order.unlink()
    from till import UNIT_CENTS
    total = UNIT_CENTS * int(Path('tests/fixtures/quantity').read_text())
    with Path('../executions').open('a') as stream:
        print(f'sale={total}', file=stream)
    assert total == 250
"""
STOCK = """from pathlib import Path

def test_stock():
    with Path('../executions').open('a') as stream:
        print('stock', file=stream)
"""


def main():
    from blackhole_agent import suite_shards

    with tempfile.TemporaryDirectory(prefix="till-shards-") as directory:
        scratch = Path(directory)
        repo = scratch / "shop"
        tests = repo / "tests"
        (tests / "fixtures").mkdir(parents=True)
        (repo / "src").mkdir()
        (repo / "pytest.ini").write_text("[pytest]\npythonpath = src\n", encoding="ascii")
        price = repo / "src" / "till.py"
        quantity = tests / "fixtures" / "quantity"
        stock = tests / "test_stock.py"
        stock.write_text(STOCK, encoding="ascii")
        (tests / "test_sale.py").write_text(SALE, encoding="ascii")
        good = b"UNIT_CENTS = 125\n"
        price.write_bytes(good)
        quantity.write_bytes(b"2")
        trace = scratch / "executions"
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        subprocess.run(["git", "init", "-q"], cwd=repo, env=env, capture_output=True, check=True, timeout=15)
        subprocess.run(["git", "add", "--", "src", "pytest.ini", "tests/test_*.py"],
                       cwd=repo, env=env, capture_output=True, check=True, timeout=15)
        bare = scratch / "bare"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(bare)], check=True, timeout=30)
        python = str(bare / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        preflight = subprocess.run([python, "-I", "-c", "import pytest"], capture_output=True, timeout=15)
        lacks_pytest = preflight.returncode != 0
        command = [python, "-m", "blackhole_agent.suite_shards", "--repo", str(repo), "--shards", "2",
                   "--shard-timeout", "25"]
        env.update(PYTHONPATH=str(Path(suite_shards.__file__).resolve().parents[1]),
                   PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTEST_ADDOPTS="")
        runners = set()

        def run():
            trace.write_bytes(b"")
            result = subprocess.run(command, cwd=scratch, env=env, capture_output=True, timeout=45)
            if not result.stdout.strip():
                raise RuntimeError(result.stderr.decode("utf-8", "replace")[-700:])
            report = json.loads(result.stdout)
            runners.add(report["pytest_runner"])
            return [result.returncode, report["shards_resumed"], sorted(trace.read_text().splitlines())]

        observed = {"first": run(), "unchanged": run()}
        stock.write_text(STOCK + "\n", encoding="ascii")
        observed["one_test_edit"] = run()
        stock.write_text(STOCK + "    assert False\n", encoding="ascii")
        observed["failed_test"] = run()
        stock.write_text(STOCK + "\n", encoding="ascii")
        py_compile.compile(str(price), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        timestamp = price.stat()
        price.write_bytes(b"UNIT_CENTS = 175\n")
        os.utime(price, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
        observed["source_edit"] = run()
        price.write_bytes(good)
        quantity.write_bytes(b"3")
        observed["fixture_edit"] = run()
        quantity.write_bytes(b"2")
        broken = b"UNIT_CENTS = 225\n"
        price.write_bytes(broken)
        (scratch / "repair-once").write_bytes(good)
        observed["edit_during_pytest"] = run()
        price.write_bytes(broken)
        observed["restored_broken_input"] = run()
        observed["bare_without_pytest"] = lacks_pytest
        observed["runners"] = sorted(runners)
        observed["ledger_persisted"] = (repo / "artifacts" / "suite-shards-ledger.json").is_file()
    passed = (
        observed["first"] == [0, 0, ["sale=250", "stock"]]
        and observed["unchanged"] == [0, 2, []]
        and observed["one_test_edit"] == [0, 1, ["stock"]]
        and observed["failed_test"] == [1, 1, ["stock"]]
        and observed["source_edit"] == [1, 0, ["sale=350", "stock"]]
        and observed["fixture_edit"] == [1, 0, ["sale=375", "stock"]]
        and observed["edit_during_pytest"][0] == 1 and "sale=250" in observed["edit_during_pytest"][2]
        and observed["restored_broken_input"][0] == 1 and "sale=450" in observed["restored_broken_input"][2]
        and lacks_pytest and runners == {"uv-ephemeral"} and observed["ledger_persisted"]
    )
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception as exc:
        print(json.dumps({"passed": False, "observed": {"error": str(exc)}}))
