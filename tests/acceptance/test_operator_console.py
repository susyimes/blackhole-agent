"""Acceptance probe: an operator can drive the invocation plane from a browser.

The controller replays probes on baseline and candidate source trees, so
this probe is fully self-contained and exits 0 for both met and unmet
outcomes. On baseline source the service has no console route: the page
fetch returns 404 and the probe reports passed=false. On candidate source
it must:

1. GET a self-contained HTML operator console (no external script/link
   assets) from the running service, with the live invocable catalog of a
   hermetic fixture ledger embedded in the served markup;
2. extract the exact fetch targets the page's own JavaScript calls and
   replay them as a browser would: health, session listing, a real
   capability invocation, and a declarative goal solve — verifying real
   transformed outputs, not fixtures (the probe picks the input and
   checks the reversal itself);
3. confirm the console is also served at the site root.

Prints JSON with boolean passed and nonempty observed.
"""

from __future__ import annotations

import json
import re
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


def _build_fixture_root(base: Path) -> Path:
    root = base / "repo"
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_TOOL, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "slug": "text-reverser",
        "name": "probe text reverser",
        "command": ["python", "tool.py"],
        "requires": ["raw_text"],
        "provides": ["reversed_text"],
        "cases": [
            {"input": {"raw_text": "ab"}, "expect": {"reversed_text": "ba"}},
            {"input": {"raw_text": "cd"}, "expect": {"reversed_text": "dc"}},
        ],
    }
    (tool_dir / "absorption.json").write_text(json.dumps(manifest), encoding="utf-8")
    capabilities = {
        "capability.absorbed-text-reverser": {
            "id": "capability.absorbed-text-reverser",
            "name": "probe text reverser",
            "kind": "python",
            "last_proved_at": "2026-01-01T00:00:00Z",
            "last_proof_exit_code": 0,
        },
    }
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps({"schema_version": 1, "updated_at": "", "capabilities": capabilities}),
        encoding="utf-8",
    )
    return root


def _get(base: str, path: str) -> tuple[int, str, str]:
    request = urllib.request.Request(base + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return (
                response.status,
                response.headers.get("Content-Type") or "",
                response.read().decode("utf-8"),
            )
    except urllib.error.HTTPError as error:
        return error.code, "", error.read().decode("utf-8", errors="replace")


def _post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        base + path,
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "operator-console"}
    try:
        from blackhole_agent.capability_service import build_server
    except Exception as error:
        observed["error"] = f"{type(error).__name__}: {error}"
        return {"passed": False, "observed": observed}

    with tempfile.TemporaryDirectory(prefix="console-probe-") as directory:
        root = _build_fixture_root(Path(directory))
        server = build_server(root, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            status, content_type, page = _get(base, "/console")
            observed["console_status"] = status
            observed["content_type"] = content_type
            if status != 200:
                observed["detail"] = "console route not served"
                return {"passed": False, "observed": observed}

            embedded_ok = (
                "capability.absorbed-text-reverser" in page
                and "reversed_text" in page
                and "<html" in page.lower()
            )
            self_contained = not re.search(
                r"<script[^>]+src=|<link[^>]+href=|url\(\s*https?:", page, re.IGNORECASE
            )
            observed["embedded_catalog"] = embedded_ok
            observed["self_contained"] = self_contained

            endpoints = sorted(set(re.findall(r'fetch\("([^"]+)"', page)))
            post_endpoints = sorted(set(re.findall(r'postJSON\("([^"]+)"', page)))
            observed["page_get_endpoints"] = endpoints
            observed["page_post_endpoints"] = post_endpoints
            wiring_ok = "/health" in endpoints and "/sessions" in endpoints and {
                "/invoke",
                "/solve",
            } <= set(post_endpoints)

            replay: dict[str, object] = {}
            for path in endpoints:
                ep_status, _, _ = _get(base, path)
                replay[path] = ep_status
            replay_ok = all(code == 200 for code in replay.values())

            probe_input = "operator console probe"
            invoke_status, invoke_result = _post(
                base, "/invoke", {"capability_id": "capability.absorbed-text-reverser", "input": {"raw_text": probe_input}}
            )
            observed["invoke_status"] = invoke_status
            observed["invoke_output"] = invoke_result.get("output")
            invoke_ok = (
                invoke_status == 200
                and invoke_result.get("ok") is True
                and invoke_result.get("output") == {"reversed_text": probe_input[::-1]}
                and bool(invoke_result.get("response_digest"))
            )

            solve_status, solve_result = _post(
                base,
                "/solve",
                {"initial_state": {"raw_text": probe_input}, "goal": ["reversed_text"]},
            )
            observed["solve_status"] = solve_status
            observed["solve_outcome"] = solve_result.get("outcome")
            solve_ok = (
                solve_status == 200
                and solve_result.get("solved") is True
                and solve_result.get("plan") == ["capability.absorbed-text-reverser"]
                and solve_result.get("outcome") == {"reversed_text": probe_input[::-1]}
                and bool(solve_result.get("plan_digest"))
            )

            root_status, _, root_page = _get(base, "/")
            root_ok = root_status == 200 and root_page == page
            observed["root_serves_console"] = root_ok

            observed["checks"] = {
                "embedded_catalog": embedded_ok,
                "self_contained": self_contained,
                "page_wiring": wiring_ok,
                "get_replay": replay_ok,
                "invoke_replay": invoke_ok,
                "solve_replay": solve_ok,
                "root_serves_console": root_ok,
            }
            return {"passed": bool(all(observed["checks"].values())), "observed": observed}
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as error:  # never crash the sweep: unmet, not crashed
        verdict = {
            "passed": False,
            "observed": {
                "family": "operator-console",
                "fatal": f"{type(error).__name__}: {error}",
            },
        }
    print(json.dumps(verdict))
    raise SystemExit(0)
