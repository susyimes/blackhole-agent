"""Self-healing goal solving acceptance, replayable against baseline src.

A live HTTP invocation plane serves a fixture ledger. The only program for
a goal runs through a quarantined capability: acceptance is that a single
POST /solve re-proves the blocker under governed re-execution of its frozen
cases, reinstates it, replans, and returns the solved outcome with a
healing trace — no operator /reproof round-trip. A blocker whose frozen
cases genuinely fail must stay quarantined and yield solved=false, and a
healthy goal must report an empty healing trace. Exit 0 either way.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'healed_text': state['raw_text'][::-1]}))\n"
)

BROKEN = "import sys\nsys.exit(3)\n"


def write_tool(root: Path, slug: str, source: str, provides: str, good_cases: bool) -> str:
    tool = root / "capabilities" / "absorbed" / slug
    tool.mkdir(parents=True)
    (tool / "tool.py").write_text(source, encoding="utf-8")
    if good_cases:
        cases = [
            {"input": {"raw_text": "ab"}, "expect": {provides: "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {provides: "dc"}},
        ]
    else:
        cases = [
            {"input": {"raw_text": "ab"}, "expect": {provides: "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {provides: "dc"}},
        ]
    (tool / "absorption.json").write_text(json.dumps({
        "schema_version": 1, "slug": slug, "name": slug,
        "command": [sys.executable, "tool.py"],
        "requires": ["raw_text"], "provides": [provides], "cases": cases,
    }), encoding="utf-8")
    return f"capability.absorbed-{slug}"


def fixture(root: Path) -> dict[str, str]:
    ids = {
        "healer": write_tool(root, "heal-reverser", REVERSER, "healed_text", True),
        "broken": write_tool(root, "sick-tool", BROKEN, "broken_text", False),
        "plain": write_tool(root, "plain-reverser", REVERSER.replace(
            "healed_text", "plain_text"), "plain_text", True),
    }
    (root / "capabilities").mkdir(exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(json.dumps({
        "schema_version": 1,
        "capabilities": {
            cid: {
                "id": cid, "name": cid, "kind": "python",
                "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
                "proof_command": "python -c pass", "dependencies": [], "behavior_paths": [],
                "last_proof_exit_code": 0, "last_proved_at": "2026-01-01T00:00:00Z",
            }
            for cid in ids.values()
        },
    }), encoding="utf-8")
    return ids


def quarantine(root: Path, capability_id: str) -> None:
    path = root / "capabilities" / "ledger.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    ledger["capabilities"][capability_id]["resource_quarantine"] = {
        "reason": "probe violation", "resource": "memory", "limit_bytes": 1,
        "quarantined_at": "2026-01-01T00:00:00Z",
    }
    path.write_text(json.dumps(ledger), encoding="utf-8")


def is_quarantined(root: Path, capability_id: str) -> bool:
    path = root / "capabilities" / "ledger.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    return "resource_quarantine" in ledger["capabilities"][capability_id]


def request(base: str, path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = Request(base + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())
    except (OSError, URLError) as exc:
        return 0, {"transport_error": type(exc).__name__}


class Server:
    def __init__(self, src: Path, root: Path):
        code = (
            "import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
            "from blackhole_agent.capability_service import serve;serve(Path(sys.argv[2]))"
        )
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-c", code, str(src), str(root)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        ready = []
        reader = threading.Thread(target=lambda: ready.append(self.process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(20)
        try:
            self.port = json.loads(ready[0])["listening"]
        except (IndexError, KeyError, ValueError):
            self.stop()
            raise RuntimeError("HTTP service did not become ready")
        self.base = f"http://127.0.0.1:{self.port}"

    def stop(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        if self.process.stdout:
            self.process.stdout.close()


def main() -> dict:
    observed = {"family": "self-healing-goal-solving"}
    server = None
    try:
        import blackhole_agent.capability_service as service

        src = Path(service.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="solve-healing-acceptance-") as directory:
            root = Path(directory)
            ids = fixture(root)
            server = Server(src, root)
            checks = {}

            # (a) goal blocked only by a quarantined capability heals inline.
            quarantine(root, ids["healer"])
            status, healed = request(server.base, "/solve", {
                "initial_state": {"raw_text": "unbound"}, "goal": ["healed_text"],
            })
            trace = healed.get("healing") or []
            checks["blocked_goal_solves"] = (
                status == 200
                and healed.get("solved") is True
                and healed.get("outcome") == {"healed_text": "dnuobnu"}
            )
            checks["healing_trace_recorded"] = any(
                entry.get("capability_id") == ids["healer"]
                and entry.get("reinstated") is True
                and entry.get("cases_pass") is True
                and entry.get("case_count") == 2
                for entry in trace
            )
            checks["quarantine_lifted"] = not is_quarantined(root, ids["healer"])
            observed["healed_solve"] = {
                "status": status, "solved": healed.get("solved"),
                "outcome": healed.get("outcome"), "healing": trace,
            }

            # (b) unhealable blocker: frozen cases genuinely fail.
            quarantine(root, ids["broken"])
            status, unhealed = request(server.base, "/solve", {
                "initial_state": {"raw_text": "unbound"}, "goal": ["broken_text"],
            })
            checks["unhealable_stays_unsolved"] = status == 200 and unhealed.get("solved") is False
            checks["unhealable_named"] = ids["broken"] in str(unhealed.get("reason", ""))
            checks["unhealable_trace"] = any(
                entry.get("capability_id") == ids["broken"] and entry.get("reinstated") is False
                for entry in (unhealed.get("healing") or [])
            )
            checks["quarantine_kept"] = is_quarantined(root, ids["broken"])
            observed["unhealed_solve"] = {
                "status": status, "solved": unhealed.get("solved"),
                "reason": unhealed.get("reason"), "healing": unhealed.get("healing"),
            }

            # (c) healthy goal solves with no healing attempted.
            status, healthy = request(server.base, "/solve", {
                "initial_state": {"raw_text": "blackhole"}, "goal": ["plain_text"],
            })
            checks["healthy_solve"] = (
                status == 200
                and healthy.get("solved") is True
                and healthy.get("outcome") == {"plain_text": "elohkcalb"}
            )
            checks["healthy_no_healing"] = healthy.get("healing") == []
            observed["healthy_solve"] = {
                "status": status, "solved": healthy.get("solved"),
                "healing": healthy.get("healing"),
            }

            observed["checks"] = checks
            return {"passed": all(checks.values()), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
