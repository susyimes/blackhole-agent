"""Evidence-ranked goal planning acceptance, replayable against baseline src.

A live HTTP invocation plane serves a fixture ledger where TWO proved
one-step programs cover the same goal: ``a-slow-route`` sorts first
lexicographically, but the workspace's invocation journal records it as
slower and previously failed, while ``z-fast-route`` is recorded fast and
reliable. Acceptance is that POST /solve selects the evidence-preferred
program instead of the lexicographic one, and that the response carries an
auditable plan_evidence trace naming both candidates with their measured
stats. On baseline src (syntactic planner) the lexicographic route is
chosen and no plan_evidence exists, so the probe reports passed=false.
Exit 0 either way.
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
    "print(json.dumps({'goal_text': state['raw_text'][::-1]}))\n"
)

FAST_ID = "capability.absorbed-z-fast-route"
SLOW_ID = "capability.absorbed-a-slow-route"


def write_tool(root: Path, slug: str) -> str:
    tool = root / "capabilities" / "absorbed" / slug
    tool.mkdir(parents=True)
    (tool / "tool.py").write_text(REVERSER, encoding="utf-8")
    (tool / "absorption.json").write_text(json.dumps({
        "schema_version": 1, "slug": slug, "name": slug,
        "command": [sys.executable, "tool.py"],
        "requires": ["raw_text"], "provides": ["goal_text"],
        "cases": [
            {"input": {"raw_text": "ab"}, "expect": {"goal_text": "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {"goal_text": "dc"}},
        ],
    }), encoding="utf-8")
    return f"capability.absorbed-{slug}"


def fixture(root: Path) -> None:
    ids = [write_tool(root, "a-slow-route"), write_tool(root, "z-fast-route")]
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
            for cid in ids
        },
    }), encoding="utf-8")


def seed_history(root: Path) -> None:
    journal = root / ".blackhole-agent" / "invocation-history.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(3):
        records.append({
            "schema_version": 1, "capability_id": SLOW_ID,
            "duration_ms": 900.0 + index, "ok": index != 1,
            "at": f"2026-01-01T00:00:0{index}Z",
        })
        records.append({
            "schema_version": 1, "capability_id": FAST_ID,
            "duration_ms": 40.0 + index, "ok": True,
            "at": f"2026-01-01T00:00:1{index}Z",
        })
    journal.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )


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
    observed = {"family": "evidence-ranked-goal-planning"}
    server = None
    try:
        import blackhole_agent.capability_service as service

        src = Path(service.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="evidence-ranked-acceptance-") as directory:
            root = Path(directory)
            fixture(root)
            seed_history(root)
            server = Server(src, root)
            checks = {}

            status, solved = request(server.base, "/solve", {
                "initial_state": {"raw_text": "unbound"}, "goal": ["goal_text"],
            })
            evidence = solved.get("plan_evidence") or {}
            ranking = evidence.get("ranking") or []
            checks["solved"] = (
                status == 200
                and solved.get("solved") is True
                and solved.get("outcome") == {"goal_text": "dnuobnu"}
            )
            checks["evidence_preferred_program_chosen"] = solved.get("plan") == [FAST_ID]
            checks["evidence_trace_present"] = (
                evidence.get("candidates_considered") == 2
                and evidence.get("selected") == [FAST_ID]
                and len(ranking) == 2
                and ranking[0].get("program") == [FAST_ID]
            )
            checks["measured_stats_recorded"] = any(
                entry.get("program") == [SLOW_ID]
                and any(
                    step.get("capability_id") == SLOW_ID
                    and step.get("recorded_failures") == 1
                    and step.get("recorded_invocations") == 3
                    for step in (entry.get("steps") or [])
                )
                for entry in ranking
            )
            observed["solve"] = {
                "status": status,
                "solved": solved.get("solved"),
                "plan": solved.get("plan"),
                "plan_evidence": evidence,
            }

            # A goal solvable by exactly one route still solves, and the
            # journal records the execution for future rankings.
            journal = root / ".blackhole-agent" / "invocation-history.jsonl"
            lines = [
                json.loads(line)
                for line in journal.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            live_records = [r for r in lines if r.get("at", "") > "2026-01-02"]
            checks["execution_recorded"] = any(
                r.get("capability_id") == FAST_ID and r.get("ok") is True
                for r in live_records
            )
            observed["journal_records"] = len(lines)

            observed["checks"] = checks
            verdict = {"passed": all(checks.values()), "observed": observed}
            server.stop()
            server = None
            return verdict
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
