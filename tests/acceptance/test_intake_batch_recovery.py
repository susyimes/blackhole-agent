"""Interrupt a real intake writer at public file replacements, then restart it offline."""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from blackhole_agent import github_growth as growth


REPO = "example/releases"
START = datetime(2026, 7, 5, tzinfo=timezone.utc)
RELEASES = ("seed", "first", "second")
INTERRUPTED = 73


def poll(root, phase, cut):
    now = START + timedelta(minutes=phase)

    class Feed:
        def list_repository_events(self, repo, *, per_page):
            if phase < 0:
                raise RuntimeError("feed offline")
            return [
                {"id": name, "type": "ReleaseEvent", "created_at": (START + timedelta(minutes=i)).isoformat(),
                 "payload": {"release": {"tag_name": name}}}
                for i, name in enumerate(RELEASES[:phase + 1])
            ]

    replace = os.replace

    def interrupt_after_replace(source, destination):
        replace(source, destination)
        if cut and Path(destination).match(cut):
            os._exit(INTERRUPTED)

    with patch("os.replace", interrupt_after_replace), patch.object(growth, "datetime", wraps=datetime) as clock:
        clock.now.return_value = now
        try:
            growth.run_intake_once(
                repos=[REPO], client=Feed(), repo_path=root, output_dir=root / "reports",
                state_path=root / "cursor" / "events.json", memory_path=root / "learning" / "memory.json",
                proposal_mode="heuristic",
            )
        except RuntimeError as error:
            if str(error) != "feed offline":
                raise
            print("feed offline")


def run(root, phase, cut=""):
    env = {**os.environ, "PYTHONPATH": str(Path(growth.__file__).resolve().parents[1])}
    return subprocess.run([sys.executable, __file__, str(root), str(phase), cut], env=env,
                          capture_output=True, text=True, timeout=20)


def outputs(root):
    paths = [*root.glob("reports/github-growth-digest-*"), *root.glob("reports/latest.*"),
             root / "cursor/events.json", root / "learning/memory.json"]
    return {path.relative_to(root): path.read_bytes() for path in paths if path.is_file()}


def observe(root):
    seed, control = root / "seed", root / "control"
    run(seed, 0).check_returncode()
    shutil.copytree(seed, control)
    run(control, 1).check_returncode()
    first = outputs(control)
    run(control, 2).check_returncode()
    second = outputs(control)
    passed, observed = True, {}
    cuts = ("github-growth-digest-*.json", "github-growth-digest-*.md", "latest.json",
            "latest.md", "events.json", "memory.json")
    for index, cut in enumerate(cuts):
        work = root / str(index)
        shutil.copytree(seed, work)
        stops = [run(work, 1, cut).returncode]
        if index == 0:  # Kill a second process during recovery of the same batch.
            stops.append(run(work, -1, "events.json").returncode)
        offline = run(work, -1)
        offline.check_returncode()
        recovered = outputs(work) == first
        run(work, 2).check_returncode()
        archives = sorted((work / "reports").glob("github-growth-digest-*.json"))
        batches = [[row["item_id"] for row in json.loads(p.read_bytes())["items"]] for p in archives]
        useful = json.loads((work / "learning/memory.json").read_bytes())["repositories"][REPO]["useful_signals"]
        observed[cut] = {"stops": stops, "offline_outputs_match": recovered, "batches": batches, "learned": useful}
        passed &= (all(code == INTERRUPTED for code in stops) and "feed offline" in offline.stdout and recovered
                   and batches == [[name] for name in RELEASES] and useful == 3 and outputs(work) == second)
        if index == 0:
            run(work, 2).check_returncode()  # The clock repeats the last poll's timestamp.
            records = [json.loads(path.read_bytes()) for path in (work / "reports").glob("github-growth-digest-*.json")]
            ids = [doc["digest_id"] for doc in records]
            items = sorted(row["item_id"] for doc in records for row in doc["items"])
            observed["same_clock_retry"] = {"distinct_digests": len(set(ids)), "items": items}
            passed &= len(set(ids)) == len(records) == 4 and items == sorted(RELEASES)
    return {"passed": passed, "observed": observed}


def test_intake_batch_recovery(tmp_path):
    result = observe(tmp_path)
    assert result["passed"], result["observed"]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        poll(Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
    else:
        with TemporaryDirectory() as directory:
            print(json.dumps(observe(Path(directory))))
