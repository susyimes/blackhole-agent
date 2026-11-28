"""Restart the local fallback on every wake while an export's input is unavailable."""

import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from blackhole_agent.kernel_health import default_local_capability_tick


def wait_for(path):
    deadline = time.monotonic() + 10
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(path)
        time.sleep(0.02)


def record(action):
    with Path("calls").open("a", encoding="utf-8") as stream:
        stream.write(f"{action} {sys.argv[2]}\n")


def deliver():
    record("deliver")
    if Path("overlap").exists() and sys.argv[2] == "1":
        Path("in-delivery").touch()
        wait_for(Path("second-wake"))
    Path("delivered").write_bytes(Path("incoming").read_bytes())


def index():
    record("index")
    Path("index").write_text(Path("catalog").read_text(encoding="utf-8").upper(), encoding="utf-8")


def tick():
    root = Path.cwd()
    state = SimpleNamespace(
        mission_id="daily",
        repo_path=str(root),
        workspace_path=str(root),
        goal="deliver incoming",
        done_when="program_passes:daily.delivery",
    )
    if (root / "overlap").exists() and sys.argv[2] == "2":
        (root / "second-wake").touch()
    return default_local_capability_tick(state, root)["status"]


def setup_inbox(root):
    definitions = {}
    for name, function, tags in (("daily.delivery", "deliver", ["bootstrap"]), ("daily.catalog", "index", [])):
        definitions[name] = dict(
            id=name,
            name=function,
            kind="python",
            description=function,
            entry=f"__main__:{function}",
            proof_command="",
            tags=tags,
        )
    (root / "capabilities").mkdir()
    (root / "capabilities" / "ledger.json").write_text(json.dumps({"capabilities": definitions}), encoding="utf-8")
    (root / "catalog").write_text("orchids", encoding="utf-8")


def wake(root, number):
    command = [sys.executable, str(Path(__file__).resolve()), "tick", str(number)]
    result = subprocess.run(command, cwd=root, capture_output=True, encoding="utf-8", timeout=20, check=True)
    return json.loads(result.stdout)


def calls(root):
    path = root / "calls"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def outcome(root):
    setup_inbox(root)
    payload = bytes(range(256))
    statuses = []
    for number in range(1, 12):
        if number == 7:
            (root / "incoming").write_bytes(payload)
        statuses.append(wake(root, number))
        if statuses[-1] == "complete":
            break
    catalog = root / "index"
    delivery = root / "delivered"
    observed = {
        "calls": calls(root),
        "index": catalog.read_text(encoding="utf-8") if catalog.exists() else None,
        "delivered_exact_bytes": delivery.exists() and delivery.read_bytes() == payload,
        "statuses": statuses,
    }
    passed = (
        observed["calls"] == ["deliver 1", "index 2", "deliver 3", "deliver 6", "deliver 11"]
        and observed["delivered_exact_bytes"]
        and observed["index"] == "ORCHIDS"
        and statuses == ["continue"] * 10 + ["complete"]
    )
    return {"passed": passed, "observed": observed}


def test_transient_delivery(tmp_path):
    result = outcome(tmp_path)
    assert result["passed"], result["observed"]


def test_overlapping_wakes_dispatch_distinct_work(tmp_path):
    setup_inbox(tmp_path)
    (tmp_path / "overlap").touch()
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(wake, tmp_path, 1)
        wait_for(tmp_path / "in-delivery")
        second = workers.submit(wake, tmp_path, 2)
        assert first.result() == second.result() == "continue"
    assert calls(tmp_path) == ["deliver 1", "index 2"]
    assert (tmp_path / "index").read_text(encoding="utf-8") == "ORCHIDS"


def test_legacy_campaign_recovers_after_96_failed_calls(tmp_path):
    setup_inbox(tmp_path)
    campaign = {
        "mission_id": "daily",
        "goal": "deliver incoming",
        "done_when": "program_passes:daily.delivery",
        "tick_count": 119,
        "program": ["daily.delivery"],
        "cursor": 1,
        "failed_ids": ["daily.delivery"] * 96,
    }
    checkpoint = tmp_path / ".blackhole-agent" / "unbound" / "local-campaign.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(json.dumps(campaign), encoding="utf-8")
    (tmp_path / "incoming").write_bytes(b"recovered")
    assert [wake(tmp_path, number) for number in range(120, 125)] == ["continue"] * 4 + ["complete"]
    assert calls(tmp_path) == ["index 120", "deliver 124"]
    assert (tmp_path / "delivered").read_bytes() == b"recovered"


if __name__ == "__main__":
    if sys.argv[1:2] == ["tick"]:
        print(json.dumps(tick()))
    else:
        with tempfile.TemporaryDirectory() as directory:
            print(json.dumps(outcome(Path(directory))))
