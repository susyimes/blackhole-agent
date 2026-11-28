"""Exercise interactive goal sessions through independent HTTP servers sharing one root."""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from queue import Queue
from threading import Barrier, Thread

TOKEN = "session-fixture"
PREPARE = "capability.absorbed-prepare"
TOOL_HEADER = """import json, os, sys, time
from pathlib import Path
effects = Path(os.environ['BLACKHOLE_EFFECT_DIR'])
"""
PREPARE_TOOL = TOOL_HEADER + """
label = json.load(sys.stdin)['label']
(effects / ('prepared-' + label)).touch()
print(json.dumps({'ticket': label.upper()}))
"""
FINISH_TOOL = TOOL_HEADER + """
import subprocess
ticket = sys.argv[1] if len(sys.argv) > 1 else json.load(sys.stdin)['ticket']
if ticket == 'CANCEL' and len(sys.argv) == 1:
    subprocess.run([sys.executable, __file__, ticket], check=True)
    sys.exit(0)
(effects / ('started-' + ticket)).touch()
if ticket not in {'QUICK', 'FAST'}:
    deadline = time.monotonic() + 20
    while not (effects / 'release').exists():
        if (effects / 'abandon').exists() or time.monotonic() >= deadline:
            sys.exit(1)
        time.sleep(0.02)
(effects / ('finished-' + ticket)).touch()
print(json.dumps({'answer': ticket + '!'}))
"""


def install_tools(root):
    catalog = root / "capabilities"
    entries = {}
    for slug, source, needs, gives in (
        ("prepare", PREPARE_TOOL, "label", "ticket"), ("finish", FINISH_TOOL, "ticket", "answer")
    ):
        tool = catalog / "absorbed" / slug
        tool.mkdir(parents=True)
        (tool / "tool.py").write_text(source, encoding="utf-8")
        cases = [{"input": {needs: val}, "expect": {gives: val.upper() if slug == "prepare" else val + "!"}}
                 for val in ("QUICK", "FAST")]
        manifest = {"schema_version": 1, "slug": slug, "name": slug, "command": ["python", "tool.py"],
                    "requires": [needs], "provides": [gives], "cases": cases}
        (tool / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
        entries["capability.absorbed-" + slug] = {"last_proof_exit_code": 0}
    (catalog / "ledger.json").write_text(json.dumps({"capabilities": entries}), encoding="utf-8")


@contextmanager
def server(root):
    import blackhole_agent

    env = {**os.environ, "PYTHONPATH": str(Path(blackhole_agent.__file__).resolve().parents[1])}
    command = [sys.executable, "-m", "blackhole_agent.capability_service", "serve",
               "--root", str(root), "--port", "0", "--token", TOKEN]
    with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, text=True) as process:
        try:
            ready = Queue()
            Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
            yield json.loads(ready.get(timeout=15))["listening"], process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


def request(port, method, path, data=None):
    with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=8)) as client:
        headers = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
        client.request(method, path, None if data is None else json.dumps(data), headers)
        response = client.getresponse()
        body = json.load(response)
        return response.status, body.get("session", body)


@contextmanager
def events(port, path):
    with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=3)) as client:
        headers = {"Accept": "text/event-stream", "Authorization": "Bearer " + TOKEN}
        client.request("GET", path + "/events", headers=headers)
        with client.getresponse() as response:
            yield (json.loads(line[5:])["status"] for line in response if line.startswith(b"data:"))


def until(read, ready, seconds=5):
    deadline = time.monotonic() + seconds
    while True:
        value = read()
        if ready(value) or time.monotonic() >= deadline:
            return value
        time.sleep(0.03)


def observe(root, stack, observed):
    install_tools(root)
    effects = root / ".blackhole-agent" / "invocation-artifacts"

    def markers(name):
        return list(effects.glob("*/" + name))

    def wait_started(ticket, count=1):
        found = until(lambda: markers("started-" + ticket), lambda items: len(items) >= count)
        if len(found) < count:
            raise RuntimeError(f"Expected {count} tool starts for {ticket}, saw {len(found)}")
        return found

    def create(port, state):
        code, session = request(port, "POST", "/sessions", {"initial_state": state, "goal": ["answer"]})
        if code != 200:
            raise RuntimeError(f"Create returned {code}: {session}")
        return "/sessions/" + session["session_id"], session

    def get(port, path):
        return request(port, "GET", path)[1]

    def settled(port, path, seconds=5):
        return until(lambda: get(port, path), lambda row: row["status"] in {"solved", "failed", "cancelled"}, seconds)

    owner, process = stack.enter_context(server(root))
    waiting, initial = create(owner, {})
    observed["elicited"] = {key: initial[key] for key in ("status", "pending_keys", "key_consumers", "steps")}
    live, _ = create(owner, {"label": "live"})
    wait_started("LIVE")
    peer, _ = stack.enter_context(server(root))
    observed["live_status"] = get(peer, live)["status"]
    independent, _ = create(peer, {"label": "fast"})
    observed["independent"] = settled(peer, independent).get("outcome")
    resume_code, _ = request(peer, "POST", live + "/resume", {})
    observed["live_resume_http"] = resume_code
    for mark in wait_started("LIVE", 2 if resume_code == 200 else 1):
        (mark.parent / "release").touch()
    observed["live_outcome"] = settled(owner, live).get("outcome")
    live_effects = until(lambda: len(markers("finished-LIVE")), lambda n: n >= (2 if resume_code == 200 else 1))
    observed["live_effects"] = live_effects

    cancel, _ = create(owner, {"label": "cancel"})
    started = wait_started("CANCEL")[0]
    with events(peer, cancel) as stream:
        first = next(stream)
        cancel_code, _ = request(peer, "DELETE", cancel)
        stopped = settled(owner, cancel, 3)
        # A failed cancellation has no terminal event to wait for.
        terminal = None
        if stopped["status"] == "cancelled":
            terminal = next((status for status in stream if status == "cancelled"), None)
    observed["peer_stream"] = [first, terminal]
    (started.parent / "release").touch()
    time.sleep(0.4)
    observed["cancel"] = {
        "http": cancel_code, "owner": stopped["status"], "peer": get(peer, cancel)["status"],
        "child_effects": len(markers("finished-CANCEL")),
    }

    # Start both survivors before starting the job whose owner will die.
    other, _ = stack.enter_context(server(root))
    interrupted, _ = create(owner, {"label": "recover"})
    abandoned = wait_started("RECOVER")[0]
    checkpoint = get(owner, interrupted)["steps"]
    process.kill()
    process.wait(timeout=10)
    # Only release the explicitly resumed invocation. Clean up the old fixture
    # at teardown in case its tool outlived the killed service on POSIX.
    stack.callback((abandoned.parent / "abandon").touch)
    orphan = get(peer, interrupted)
    observed["orphan"] = {
        "status": orphan["status"], "saved_steps": len(orphan["steps"]), "starts": len(markers("started-RECOVER")),
    }

    barrier = Barrier(2)

    def resume(port):
        barrier.wait(timeout=5)
        return request(port, "POST", interrupted + "/resume", {})[0]

    with ThreadPoolExecutor(2) as clients:
        winners = sorted(clients.map(resume, (peer, other)))
    observed["competing_resumes_http"] = winners
    if 200 in winners:
        for mark in wait_started("RECOVER", 1 + winners.count(200)):
            if mark != abandoned:
                (mark.parent / "release").touch()
        recovered = settled(other, interrupted)
        observed["recovered"] = {
            "outcome": recovered["outcome"], "steps": len(recovered["steps"]),
            "checkpoint_preserved": recovered["steps"][:1] == checkpoint,
            "prepare_effects": len(markers("prepared-recover")), "finish_effects": len(markers("finished-RECOVER")),
        }

    preserved = get(other, waiting)

    def answer(port):
        barrier.wait(timeout=5)
        try:
            return request(port, "POST", waiting + "/input", {"input": {"label": "quick"}})[0]
        except (OSError, http.client.HTTPException):
            return 0

    with ThreadPoolExecutor(2) as clients:
        answers = sorted(clients.map(answer, (peer, other)))
    answered = settled(other, waiting)
    observed["input_effects"] = len(markers("prepared-quick"))
    solve_code, direct = request(other, "POST", "/solve", {"initial_state": {"label": "quick"}, "goal": ["answer"]})
    digests = [step["response_digest"] for step in answered["steps"]]
    observed["interactive"] = {
        "preserved": preserved["status"], "input_http": answers, "outcome": answered["outcome"],
        "solve_http": solve_code, "direct_solved": direct.get("solved"), "has_plan_digest": bool(answered["plan_digest"]),
        "same_plan": answered["plan"] == direct.get("plan"),
        "same_results": len(digests) == 2 and digests == [s["response_digest"] for s in direct.get("steps", [])],
    }

    return observed == {
        "elicited": {"status": "awaiting_input", "pending_keys": ["label"], "key_consumers": {"label": PREPARE}, "steps": []},
        "live_status": "running", "independent": {"answer": "FAST!"}, "live_resume_http": 409,
        "live_outcome": {"answer": "LIVE!"}, "live_effects": 1, "peer_stream": ["running", "cancelled"],
        "cancel": {"http": 200, "owner": "cancelled", "peer": "cancelled", "child_effects": 0},
        "orphan": {"status": "interrupted", "saved_steps": 1, "starts": 1}, "competing_resumes_http": [200, 409],
        "recovered": {"outcome": {"answer": "RECOVER!"}, "steps": 2, "checkpoint_preserved": True,
                      "prepare_effects": 1, "finish_effects": 1},
        "input_effects": 1,
        "interactive": {"preserved": "awaiting_input", "input_http": [200, 409], "outcome": {"answer": "QUICK!"},
                        "solve_http": 200, "direct_solved": True, "has_plan_digest": True,
                        "same_plan": True, "same_results": True},
    }


def main():
    observed = {}
    try:
        with tempfile.TemporaryDirectory(prefix="goal-sessions-") as folder, ExitStack() as stack:
            passed = observe(Path(folder), stack, observed)
    except Exception as exc:
        observed["error"] = f"{type(exc).__name__}: {exc}"
        passed = False
    return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    print(json.dumps(main()))
