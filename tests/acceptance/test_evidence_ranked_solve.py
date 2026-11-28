"""Exercise evidence-ranked HTTP solves, a torn journal append, restart, and tool fallback."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'goal_text': state['raw_text'][::-1]}))\n"
)

# The evidence-preferred fast route is proved on benign frozen cases but
# fails at execution time on the 'failme' input.
FLAKY_REVERSER = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "if state['raw_text'] == 'failme':\n"
    "    sys.exit(3)\n"
    "print(json.dumps({'goal_text': state['raw_text'][::-1]}))\n"
)

FAST_ID = "capability.absorbed-z-fast-route"
SLOW_ID = "capability.absorbed-a-slow-route"


def write_tool(root: Path, slug: str, source: str = REVERSER) -> str:
    tool = root / "capabilities" / "absorbed" / slug
    tool.mkdir(parents=True)
    (tool / "tool.py").write_text(source, encoding="utf-8")
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


def fixture(root: Path, fast_source: str = FLAKY_REVERSER) -> None:
    ids = [write_tool(root, "a-slow-route"), write_tool(root, "z-fast-route", fast_source)]
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


def seed_history(root: Path) -> Path:
    journal = root / ".blackhole-agent" / "invocation-history.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)

    def row(cid: str, duration: int, ok: bool = True) -> bytes:
        return json.dumps({"capability_id": cid, "duration_ms": duration, "ok": ok}).encode() + b"\n"

    # The old failures would reverse the choice. The oldest in-window success
    # must be evicted precisely when the live execution is recorded.
    journal.write_bytes(
        row(FAST_ID, 40, False) * 100 + row(SLOW_ID, 900) + row(FAST_ID, 40)
        + row("unrelated", 10) * 4994 + row(SLOW_ID, 901, False) + row(FAST_ID, 41)
        + row(SLOW_ID, 902) + row(FAST_ID, 42)
    )
    return journal


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


@contextmanager
def serving(src: Path, root: Path):
    code = (
        "import sys;sys.path.insert(0,sys.argv[1]);from pathlib import Path;"
        "from blackhole_agent.capability_service import serve;serve(Path(sys.argv[2]))"
    )
    with subprocess.Popen(
        [sys.executable, "-I", "-c", code, str(src), str(root)],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    ) as process:
        ready = []
        reader = threading.Thread(target=lambda: ready.append(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            reader.join(20)
            if not ready or not ready[0]:
                raise RuntimeError("HTTP service did not become ready")
            yield f"http://127.0.0.1:{json.loads(ready[0])['listening']}"
        finally:
            process.kill()
            process.wait(timeout=10)


def solve(base: str, text: str = "unbound", *, preview: bool = False) -> dict:
    status, body = request(base, "/solve", {
        "initial_state": {"raw_text": text}, "goal": ["goal_text"], "dry_run": preview,
    })
    evidence = body.get("plan_evidence", {})
    counts = {
        step["capability_id"]: [step["recorded_invocations"], step["recorded_failures"]]
        for route in evidence.get("ranking", []) for step in route["steps"]
    }
    return {
        "status": status, "solved": body.get("solved"), "outcome": body.get("outcome"), "plan": body.get("plan"),
        "counts": counts, "selected": evidence.get("selected"), "fallbacks": body.get("fallbacks", []),
        "ranking": [route["program"] for route in evidence.get("ranking", [])],
        "candidates_considered": evidence.get("candidates_considered"), "error": body.get("detail") or body.get("error"),
    }


def main() -> dict:
    observed = {}
    try:
        import blackhole_agent.capability_service as service

        src = Path(service.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="evidence-ranked-acceptance-") as directory:
            root = Path(directory)
            fixture(root)
            journal = seed_history(root)
            with serving(src, root) as base:
                clean = observed["clean_preview"] = solve(base, preview=True)
                with journal.open("ab") as handle:
                    handle.write(b'{"error":"torn \xe5\xad\n{"error":"torn again \xe5\xad')
                original = journal.read_bytes()
                live = observed["live_solve"] = solve(base)
            with serving(src, root) as base:
                restored = observed["restarted_preview"] = solve(base, preview=True)
                fallback = observed["fallback_solve"] = solve(base, "failme")

            before = {SLOW_ID: [3, 1], FAST_ID: [3, 0]}
            saved = journal.read_bytes()
            added = [json.loads(line) for line in saved[len(original):].splitlines() if line.strip()]
            events = observed["journal_appends"] = [[row["capability_id"], row["ok"]] for row in added]
            checks = {
                "clean_control": clean["status"] == 200 and clean["plan"] == [FAST_ID] and clean["counts"] == before,
                "solved": live["status"] == 200 and live["solved"] is True
                and live["plan"] == [FAST_ID] and live["outcome"] == {"goal_text": "dnuobnu"},
                "evidence_trace": live["counts"] == before and live["candidates_considered"] == 2
                and live["selected"] == [FAST_ID] and live["ranking"] == [[FAST_ID], [SLOW_ID]],
                "execution_recorded_once": restored["status"] == 200 and restored["plan"] == [FAST_ID]
                and restored["counts"] == {SLOW_ID: [2, 1], FAST_ID: [4, 0]},
                "original_bytes_preserved": saved.startswith(original),
                "execution_recorded": events == [[FAST_ID, True], [FAST_ID, False], [SLOW_ID, True]]
                and all(row.get("at") for row in added),
                "fallback_still_solves": fallback["status"] == 200 and fallback["solved"] is True
                and fallback["plan"] == [SLOW_ID] and fallback["outcome"] == {"goal_text": "emliaf"},
                "fallback_reported": any(
                    entry.get("capability_id") == FAST_ID and entry.get("replaced_by") == [SLOW_ID]
                    for entry in fallback["fallbacks"]
                ),
            }
            observed["checks"] = checks
            return {"passed": all(checks.values()), "observed": observed}
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        return {"passed": False, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main(), sort_keys=True))
