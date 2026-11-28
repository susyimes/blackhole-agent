# replay-input: capabilities/ledger.json
# replay-input: capabilities/absorbed/forage-flip
# replay-input: capabilities/absorbed/forage-js
# replay-input: capabilities/absorbed/forage-lab
"""Drive competing shipped tools through the goal-session HTTP interface."""

import json
import shutil
import tempfile
import threading
import time
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path

from blackhole_agent import capability_service


def request(port, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Authorization": "Bearer session-probe", "Content-Type": "application/json"}
    with closing(HTTPConnection("127.0.0.1", port, timeout=10)) as client:
        client.request("GET" if body is None else "POST", path, body, headers)
        response = client.getresponse()
        result = json.load(response)
        return result.get("session", {"status": response.status, "error": result.get("error")})


def settled(port, session):
    deadline = time.monotonic() + 12
    while session["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.05)
        session = request(port, "/sessions/" + session["session_id"])
    return {
        "status": session["status"], "outcome": session.get("outcome"), "error": session.get("error"),
        "pending": session.get("pending_keys"), "consumers": session.get("key_consumers"),
        "asked": session.get("elicited_keys"),
        "steps": [step["capability_id"] for step in session.get("steps", [])],
    }


def probe(root):
    shipped = Path(capability_service.__file__).resolve().parents[2] / "capabilities"
    catalog = root / "capabilities"
    for slug in ("forage-flip", "forage-js", "forage-lab"):
        shutil.copytree(shipped / "absorbed" / slug, catalog / "absorbed" / slug)
    shutil.copyfile(shipped / "ledger.json", catalog / "ledger.json")
    with capability_service.build_server(root, token="session-probe") as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        value = "Night train"
        try:
            ready = settled(port, request(port, "/sessions", {
                "initial_state": {"text": value}, "goal": ["shout_output"],
            }))
            shared = request(port, "/sessions", {
                "initial_state": {}, "goal": ["text", "flip_output", "shout_output"],
            })
            before = settled(port, shared)
            after = None
            if "session_id" in shared:
                answered = request(port, "/sessions/" + shared["session_id"] + "/input", {"input": {"text": value}})
                after = settled(port, answered)
        finally:
            server.shutdown()
            thread.join()
    flip = "capability.absorbed-forage-flip"
    shout = "capability.absorbed-forage-lab"
    passed = (
        ready["status"] == "solved" and ready["asked"] == [] and ready["steps"] == [shout]
        and ready["outcome"] == {"shout_output": "NIGHT TRAIN!"}
        and before["status"] == "awaiting_input" and before["pending"] == ["text"]
        and before["steps"] == [] and before["consumers"] == {"text": flip}
        and after is not None and after["status"] == "solved" and after["steps"] == [flip, shout]
        and after["outcome"] == {"text": value, "flip_output": "flipped:Night train", "shout_output": "NIGHT TRAIN!"}
    )
    return {"passed": passed, "observed": {"ready": ready, "before_input": before, "after_input": after}}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        print(json.dumps(probe(Path(directory))))
