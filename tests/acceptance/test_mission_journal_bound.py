"""Exercise live journal writes and retry a real, interrupted archive compaction."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import blackhole_agent


FILES = ("state.json", "events.jsonl", "state.previous.bak", "turns/0001/turn.json")
SENTINEL = "artifacts/forage/UNIQUE-SENTINEL-NOT-IN-SAMPLE.whl"
PATHS = [f"artifacts/forage/regenerated-cache-object-{i:05d}.whl" for i in range(400)]
PATHS[200] = SENTINEL
GOAL = "Keep regenerated forage paths out of the mission journal."
LAST_ERROR = "journal grew without a bound"
DIGEST = hashlib.sha256("\n".join(PATHS).encode()).hexdigest()
CUT = 73


def seed(mission, status):
    for name in FILES:
        path = mission / name
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"mission_id": mission.name, "status": status, "goal": GOAL, "last_error": LAST_ERROR,
                  "changed_paths": PATHS, "milestone_gate": {"behavior_paths": PATHS}, "note": name}
        path.write_bytes((json.dumps(record) + "\n").encode())
    return snapshot(mission)


def snapshot(mission):
    return {name: (mission / name).read_bytes() for name in FILES}


def worker(directory, boundary):
    from blackhole_agent.mission_journal_bound import compact_closed_mission_journal

    mission = Path(directory)
    if boundary:
        replace = os.replace
        journals = {mission / name for name in FILES}
        remaining = int(boundary)

        def install(source, target):
            nonlocal remaining
            replace(source, target)
            if Path(target) in journals:
                remaining -= 1
                if remaining == 0:
                    os._exit(CUT)

        os.replace = install
    print(json.dumps(compact_closed_mission_journal(mission, allowed_root=mission.parent)))


def invoke(mission, boundary=""):
    bootstrap = "import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2])['worker'](*sys.argv[3:])"
    child = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", bootstrap, str(Path(blackhole_agent.__file__).parents[1]),
         str(Path(__file__).resolve()), str(mission), str(boundary)],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    return child.returncode, json.loads(child.stdout) if child.returncode == 0 else {"error": child.stderr[-500:]}


def restart(mission, edit=False):
    original = seed(mission, "complete")
    code, _ = invoke(mission, 1)
    partial = snapshot(mission)
    installed = [name for name in FILES if partial[name] != original[name]]
    cut = code == CUT and len(installed) == 1
    final = mission / "journal-bound-receipt.json"
    if edit:
        name = next(n for n in FILES if n not in installed)
        with (mission / name).open("ab") as stream:
            stream.write(b" \n")
        edited = snapshot(mission)
        code, reply = invoke(mission)
        refused = code == 0 and reply.get("ok") is False and "conflict" in reply.get("reason", "")
        intact = edited == snapshot(mission) and not final.exists()
        return cut and refused and intact, {"refused": refused, "preserved": intact}

    code, result = invoke(mission)
    after = snapshot(mission)
    rows = {Path(row["path"]): row for row in result.get("files", [])}
    originals = 0
    compact = True
    inventories = True
    for name, raw in original.items():
        row = rows.get(mission / name, {})
        originals += (row.get("sha256_before") == hashlib.sha256(raw).hexdigest()
                      and row.get("bytes_before") == len(raw) and row.get("bytes_after") == len(after[name]))
        doc = json.loads(after[name])
        summary = doc.get("changed_paths_inventory", {})
        compact &= (len(after[name]) < len(raw) and SENTINEL.encode() not in after[name] and doc["note"] == name
                    and (doc["goal"], doc["last_error"], doc["status"]) == (GOAL, LAST_ERROR, "complete")
                    and (summary.get("sha256"), summary.get("count")) == (DIGEST, len(PATHS)))
        inventories &= any(i["field"] == "changed_paths" and i["sha256"] == DIGEST and i["count"] == len(PATHS)
                           for i in row.get("inventories", []))
    receipt = final.read_bytes() if final.exists() else b""
    again, repeated = invoke(mission)
    stable = bool(receipt and again == 0 and repeated == result == json.loads(receipt)
                  and receipt == final.read_bytes() and after == snapshot(mission))
    original_bytes, remaining = sum(map(len, original.values())), sum(map(len, after.values()))
    totals = (result.get("bytes_before"), result.get("bytes_after"))
    passed = cut and code == 0 and result.get("ok") is True and originals == len(FILES) and compact and inventories and stable
    return passed and totals == (original_bytes, remaining), {
        "installed": installed, "original_hashes_and_sizes": originals, "compacted": compact, "repeat_identical": stable,
        "true_original_bytes": original_bytes, "reported_bytes": totals,
    }


def _observe():
    try:
        from blackhole_agent.mission_journal_bound import compact_closed_mission_journal, write_bounded_turn_files
    except ImportError:
        return {"passed": False, "observed": "mission journal bounder is absent"}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        active = root / "active"
        before = seed(active, "active")
        recovered, recovery = restart(root / "restarted")
        protected, conflict = restart(root / "edited", edit=True)
        refusal = compact_closed_mission_journal(active, allowed_root=root)
        untouched = before == snapshot(active) and refusal.get("ok") is False and refusal["reason"] == "status_active"
        turn = active / "turns" / "0002"
        persisted = write_bounded_turn_files(active, {"changed_paths": PATHS, "milestone_gate": {"behavior_paths": PATHS}},
                                             turn_dir=turn, mission_id=active.name)
        inventory = persisted["changed_paths_inventory"]
        event = (active / "events.jsonl").read_bytes().splitlines()[-1]
        written = (inventory["sha256"] == DIGEST and inventory["count"] == len(PATHS)
                   and SENTINEL.encode() not in (turn / "turn.json").read_bytes() and SENTINEL.encode() not in event
                   and json.loads(event)["changed_paths_inventory"] == inventory)
    return {"passed": bool(recovered and protected and untouched and written), "observed": {
        "restart": recovery, "conflict": conflict, "active_unchanged": untouched, "live_turn_bounded": written}}


def test_concurrent_recovery(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    for boundary in (2, len(FILES)):
        mission = tmp_path / str(boundary)
        before = seed(mission, "complete")
        assert invoke(mission, boundary)[0] == CUT
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.map(invoke, (mission, mission))
        code, receipt = first
        assert first == second and code == 0 and receipt["ok"]
        assert receipt["bytes_before"] == sum(map(len, before.values()))
        assert receipt["bytes_after"] == sum(map(len, snapshot(mission).values()))


if __name__ == "__main__":
    print(json.dumps(_observe(), sort_keys=True))
