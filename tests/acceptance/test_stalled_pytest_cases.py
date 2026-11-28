# replay-input: uv.lock
"""Run one real parametrized test through setup, call and teardown stalls."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


WORKLOAD = """import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


def mark(event):
    with Path('../trace').open('a') as trace:
        print(event, file=trace)


def stall(phase):
    if Path('../hold').exists():
        mark('stalled-' + phase)
        child = None
        if phase == 'call':
            script = ("import socket,time; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); "
                      "print(s.getsockname()[1], flush=True); time.sleep(15)")
            child = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE)
            with child.stdout as port:
                Path('../port').write_bytes(port.readline())
        try:
            time.sleep(3)
        finally:
            if child is not None:
                child.terminate()
                child.wait(timeout=5)
        mark('returned-' + phase)


@pytest.fixture
def gate(phase):
    if phase == 'setup':
        stall(phase)
    yield
    if phase == 'teardown':
        stall(phase)


@pytest.mark.parametrize('phase', ['before', 'setup', 'call', 'call-fast', 'teardown', 'after'])
def test_job(phase, gate):
    mark(phase)
    if phase == 'call':
        stall(phase)
    if phase == 'call-fast' and Path('../hold').exists():
        with socket.socket() as check:
            check.bind(('127.0.0.1', int(Path('../port').read_bytes())))
        mark('port-released')
        assert False, 'an ordinary assertion failure between two stalls'
"""


def observe():
    from blackhole_agent import suite_shards

    with tempfile.TemporaryDirectory(prefix="bh-stalled-cases-") as tmp:
        root = Path(tmp)
        suite = root / "suite"
        (suite / "tests").mkdir(parents=True)
        (suite / "tests" / "test_jobs.py").write_text(WORKLOAD, encoding="utf-8")
        hold, trace = root / "hold", root / "trace"
        hold.touch()
        env = dict(os.environ, PYTHONPATH=str(Path(suite_shards.__file__).resolve().parents[1]),
                   PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTEST_ADDOPTS="", BLACKHOLE_PYTEST_CASE_TIMEOUT="1.5")
        command = [sys.executable, "-m", "blackhole_agent.suite_shards", "--repo", str(suite),
                   "--shards", "1", "--shard-timeout", "30"]

        def run():
            trace.write_text("", encoding="ascii")
            result = subprocess.run(command, env=env, cwd=root, capture_output=True, timeout=45)
            report = json.loads(result.stdout)
            shard = report["shards"][0]
            return {"exit": result.returncode, "status": shard["status"], "resumed": shard["resumed"],
                    "stalls": shard.get("timed_out_cases", []), "failed": shard.get("failed_cases", []),
                    "trace": trace.read_text().splitlines()}

        held = run()
        hold.unlink()
        repaired = run()
        cached = run()
    phases = ["setup", "call", "teardown"]
    expected = [{"nodeid": f"tests/test_jobs.py::test_job[{phase}]", "phase": phase} for phase in phases]
    passed = (
        held["exit"] == 1 and held["status"] == "timed_out" and held["stalls"] == expected
        and held["failed"] == [{"nodeid": "tests/test_jobs.py::test_job[call-fast]", "phase": "call"}]
        and held["trace"] == ["before", "stalled-setup", "call", "stalled-call", "call-fast",
                              "port-released", "teardown", "stalled-teardown", "after"]
        and repaired == {"exit": 0, "status": "passed", "resumed": False, "stalls": [], "failed": [],
                         "trace": ["before", "setup", "call", "call-fast", "teardown", "after"]}
        and cached == {"exit": 0, "status": "passed", "resumed": True, "stalls": [], "failed": [], "trace": []}
    )
    return {"passed": passed, "observed": {"held": held, "repaired": repaired, "unchanged": cached}}


def test_stalled_pytest_cases():
    verdict = observe()
    assert verdict["passed"], verdict["observed"]


def test_shard_deadline_and_fail_fast(tmp_path, monkeypatch):
    from blackhole_agent.suite_shards import run_suite_shards

    repo = tmp_path / "suite"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_work.py").write_text(
        "import time\nfrom pathlib import Path\ndef test_slow():\n"
        "    time.sleep(float(Path('../delay').read_text()))\n"
        "def test_next():\n    Path('../next').touch()\n", encoding="ascii",
    )
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "")
    case = {"nodeid": "tests/test_work.py::test_slow", "phase": "call"}
    (tmp_path / "delay").write_text("30", encoding="ascii")
    hard = run_suite_shards(repo, shard_timeout=6)["shards"][0]
    assert hard["status"] == "timed_out" and hard["active_at_shard_timeout"] == case
    assert hard["timed_out_cases"] == []
    monkeypatch.setenv("PYTEST_ADDOPTS", "-x")
    (tmp_path / "delay").write_text("0.12", encoding="ascii")
    fast = run_suite_shards(repo, shard_timeout=20, case_timeout=0.08)["shards"][0]
    assert fast["status"] == "timed_out" and fast["timed_out_cases"] == [case]
    assert not (tmp_path / "next").exists()


if __name__ == "__main__":
    print(json.dumps(observe()))
