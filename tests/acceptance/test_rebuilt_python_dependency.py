"""Import two builds of the same wheel and retry a damaged distribution offline."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from zipfile import ZipFile

from blackhole_agent import capability_foraging as forage


def wheel(path, price):
    package = "invoice_rates"
    metadata = f"{package}-1.0.dist-info"
    files = {
        f"{package}/__init__.py": "from .rates import invoice\n",
        f"{package}/rates.py": f"def invoice(units):\n    return units * {price}\n",
        f"{metadata}/METADATA": "Metadata-Version: 2.1\nName: invoice-rates\nVersion: 1.0\n",
        f"{metadata}/WHEEL": "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    with ZipFile(path, "w") as archive:
        rows = []
        for name, source in files.items():
            data = source.encode()
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            rows.append(f"{name},sha256={digest},{len(data)}")
            archive.writestr(name, data)
        record = f"{metadata}/RECORD"
        archive.writestr(record, "\n".join([*rows, record + ",,", ""]))


def stage(root, name):
    consumer = root / name
    consumer.mkdir(exist_ok=True)
    (consumer / "PKG-INFO").write_text("Requires-Dist: invoice-rates\n", encoding="utf-8")
    result = forage.close_runtime_dependencies(consumer, dest_dir=root, runtime="python")
    paths = [str(consumer / path) for path in result["extra_paths"]]
    return result["ok"], paths


def invoice(paths):
    code = "import sys; sys.path[:0] = sys.argv[1:]; from invoice_rates import invoice; print(invoice(5))"
    run = subprocess.run([sys.executable, "-I", "-B", "-c", code, *paths], capture_output=True, text=True, timeout=10)
    return int(run.stdout) if run.returncode == 0 else None


def interrupt_extraction(event, args):
    if event == "open" and isinstance(args[0], str) and Path(args[0]).name == "rates.py" and args[2] & os.O_CREAT:
        os._exit(73)  # The first module has been extracted. Skip Python cleanup.


def run_worker(root, name):
    return subprocess.run([sys.executable, "-B", __file__, str(root), name], capture_output=True, text=True, timeout=20)


def observe(root):
    archive = root / "invoice_rates-1.0-py3-none-any.whl"
    forage.EXTRACT_CACHE_DIR = root / "cache"
    wheel(archive, 9)
    _, original = stage(root, "first")
    before = invoice(original)
    wheel(archive, 13)
    _, rebuilt = stage(root, "second")
    prices = [before, invoice(rebuilt), invoice(original)]

    forage.EXTRACT_CACHE_DIR = root / "cold-cache"
    good = archive.read_bytes()
    archive.write_bytes(good.replace(b"return units * 13", b"return units * 17"))
    damaged = [stage(root, name)[0] for name in ("failed", "retry")]
    archive.write_bytes(good)
    recovered, repaired = stage(root, "retry")
    stopped = run_worker(root, "interrupt")
    with ThreadPoolExecutor(max_workers=2) as pool:
        restarts = list(pool.map(lambda name: run_worker(root, name), ("reader-a", "reader-b")))
    return {
        "invoices": prices, "damaged_accepted": damaged, "repaired_invoice": invoice(repaired) if recovered else None,
        "interrupted_exit": stopped.returncode,
        "restart_invoices": [json.loads(run.stdout) if run.returncode == 0 else None for run in restarts],
    }


if __name__ == "__main__":
    if len(sys.argv) == 3:
        root, name = Path(sys.argv[1]), sys.argv[2]
        forage.EXTRACT_CACHE_DIR = root / "restart-cache"
        if name == "interrupt":
            sys.addaudithook(interrupt_extraction)
        ok, paths = stage(root, name)
        print(json.dumps(invoice(paths) if ok else None))
        sys.exit(0)
    with tempfile.TemporaryDirectory() as temporary:
        observed = observe(Path(temporary))
    expected = {
        "invoices": [45, 65, 45], "damaged_accepted": [False, False], "repaired_invoice": 65,
        "interrupted_exit": 73, "restart_invoices": [65, 65],
    }
    print(json.dumps({"passed": observed == expected, "observed": observed}))
