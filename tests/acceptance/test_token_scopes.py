"""Acceptance probe: scoped bearers cannot invoke disallowed tools.

A valid --token currently authorizes every POST /invoke. This probe starts
the invocation plane as a separate OS process with an operator token and a
scoped token that may invoke only one fixture tool, then drives real
loopback HTTP:

1. GET /health reports token_scopes true.
2. POST /invoke of the scoped shout id with the scoped Bearer returns 200
   and the declared shout output.
3. POST /invoke of the text-reverser with that same scoped token returns
   403 tool_not_allowed and does not return reversed output.
4. GET /capabilities with the scoped token lists the shout id and does
   not list the reverser.
5. POST /invoke of the text-reverser with the operator token still returns
   the declared reverse.
6. A plane started with only --token reports token_scopes false and that
   token still reverses.
7. A follow-up POST /invoke of the shout fixture with the scoped token
   still returns the declared shout output.

On the pre-mission plane --token-scope is unknown, so the probe reports
passed=false. Both outcomes exit 0 with JSON passed and nonempty observed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

PROBE_TEXT = "token-scope-c2c8a7d2"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
REVERSE_ID = "capability.absorbed-text-reverser"
SHOUT_ID = "capability.absorbed-scope-shout"
SHOUT_INPUT = {"text": "blackhole unbound"}
SHOUT_OUTPUT = "BLACKHOLE UNBOUND!"
OPERATOR = "operator-token-c2c8a7d2"
SCOPED = "scoped-token-c2c8a7d2"

_REVERSE_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)
_SHOUT_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'shout_output': state['text'].upper() + '!'}))\n"
)


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    token: str | None = None,
    timeout: int = 45,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            try:
                parsed: object = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return response.status, parsed
    except HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, None
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def _ledger_entry(capability_id: str, name: str) -> dict:
    return {
        "id": capability_id,
        "name": name,
        "kind": "python",
        "entry": "blackhole_agent.capability_absorption:demo_absorbed_steps",
        "proof_command": "uv run python -c \"pass\"",
        "dependencies": [],
        "behavior_paths": [],
        "capability_delta": "",
        "tags": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "last_proved_at": "2026-01-01T00:00:00Z",
        "last_proof_exit_code": 0,
    }


def _write_tool(root: Path, slug: str, source: str, requires: list[str], provides: list[str]) -> None:
    tool_dir = root / "capabilities" / "absorbed" / slug
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(source, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "slug": slug,
                "name": f"probe {slug}",
                "command": ["python", "tool.py"],
                "requires": requires,
                "provides": provides,
                "cases": [
                    {"input": {key: "x" for key in requires}, "expect": {provides[0]: "x"}},
                    {"input": {key: "y" for key in requires}, "expect": {provides[0]: "y"}},
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "probe-workspace"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    _write_tool(root, "text-reverser", _REVERSE_TOOL, ["raw_text"], ["reversed_text"])
    _write_tool(root, "scope-shout", _SHOUT_TOOL, ["text"], ["shout_output"])
    (root / "capabilities").mkdir(parents=True, exist_ok=True)
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {
                    REVERSE_ID: _ledger_entry(REVERSE_ID, "probe text reverser"),
                    SHOUT_ID: _ledger_entry(SHOUT_ID, "probe scope shout"),
                },
            }
        ),
        encoding="utf-8",
    )


def _listing_ids(listing: object) -> list[str]:
    if not isinstance(listing, dict):
        return []
    return [
        str(item.get("id"))
        for item in (listing.get("capabilities") or [])
        if isinstance(item, dict)
    ]


def _read_ready_line(process: subprocess.Popen, sink: dict) -> None:
    line = process.stdout.readline() if process.stdout is not None else ""
    try:
        sink["ready"] = json.loads(line)
    except Exception:
        sink["ready"] = None


def _start_plane(
    src_root: Path,
    root: Path,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.Popen, dict[str, object]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("BLACKHOLE_BUNDLE_IMPORT", None)
    env.pop("BLACKHOLE_INVOCATION_TOKEN", None)
    env.pop("BLACKHOLE_TOKEN_SCOPE", None)
    command = [
        sys.executable,
        "-m",
        "blackhole_agent.capability_service",
        "serve",
        "--port",
        "0",
        "--root",
        str(root),
    ]
    if extra_args:
        command.extend(extra_args)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    sink: dict[str, object] = {}
    reader = threading.Thread(target=_read_ready_line, args=(process, sink), daemon=True)
    reader.start()
    reader.join(timeout=60)
    return process, sink


def _stop_plane(process: subprocess.Popen) -> str:
    process.kill()
    try:
        _out, err = process.communicate(timeout=10)
    except Exception:
        err = ""
    return err if isinstance(err, str) else ""


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "token-scopes"}
    try:
        import blackhole_agent.capability_service as service
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(service, "resolve_token_scopes"):
        observed["detail"] = "baseline plane has no live token scopes"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    scope_flag = f"{SCOPED}={SHOUT_ID}"
    with tempfile.TemporaryDirectory(prefix="token-scope-probe-") as directory:
        base = Path(directory)
        root = base / "repo"
        _write_workspace(root)

        process, sink = _start_plane(
            src_root,
            root,
            ["--token", OPERATOR, "--token-scope", scope_flag],
        )
        try:
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = _stop_plane(process)
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            url = f"http://127.0.0.1:{ready['listening']}"
            observed["ready_token_scopes"] = ready.get("token_scopes")

            health_status, health = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("token_scopes") is True
            )

            shout_status, shouted = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": SHOUT_ID, "input": SHOUT_INPUT},
                token=SCOPED,
            )
            observed["shout_status"] = shout_status
            observed["shouted"] = shouted if isinstance(shouted, dict) else None
            shout_ok = (
                shout_status == 200
                and isinstance(shouted, dict)
                and shouted.get("output", {}).get("shout_output") == SHOUT_OUTPUT
            )

            denied_status, denied = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
                token=SCOPED,
            )
            observed["denied_status"] = denied_status
            observed["denied"] = denied if isinstance(denied, dict) else None
            denied_output = denied.get("output") if isinstance(denied, dict) else None
            denied_ok = (
                denied_status == 403
                and isinstance(denied, dict)
                and denied.get("error") == "tool_not_allowed"
                and not (
                    isinstance(denied_output, dict)
                    and denied_output.get("reversed_text") == EXPECTED_REVERSE
                )
            )

            cap_status, listing = _request("GET", f"{url}/capabilities", token=SCOPED)
            ids = _listing_ids(listing)
            observed["capability_ids"] = ids
            listed_ok = cap_status == 200 and SHOUT_ID in ids and REVERSE_ID not in ids

            reverse_status, reversed_body = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
                token=OPERATOR,
            )
            observed["operator_reverse_status"] = reverse_status
            observed["operator_reversed"] = (
                reversed_body if isinstance(reversed_body, dict) else None
            )
            operator_ok = (
                reverse_status == 200
                and isinstance(reversed_body, dict)
                and reversed_body.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )

            follow_status, follow = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": SHOUT_ID, "input": SHOUT_INPUT},
                token=SCOPED,
            )
            observed["follow_status"] = follow_status
            observed["follow"] = follow if isinstance(follow, dict) else None
            follow_ok = (
                follow_status == 200
                and isinstance(follow, dict)
                and follow.get("output", {}).get("shout_output") == SHOUT_OUTPUT
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-4000:]

        closed_root = base / "closed"
        _write_workspace(closed_root)
        closed, closed_sink = _start_plane(
            src_root,
            closed_root,
            ["--token", OPERATOR],
        )
        try:
            closed_ready = closed_sink.get("ready")
            observed["closed_ready"] = closed_ready
            if not isinstance(closed_ready, dict) or not closed_ready.get("listening"):
                err = _stop_plane(closed)
                observed["closed_detail"] = "closed plane never reported a listening port"
                observed["closed_stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            closed_url = f"http://127.0.0.1:{closed_ready['listening']}"
            closed_health_status, closed_health = _request("GET", f"{closed_url}/health")
            observed["closed_health"] = closed_health if isinstance(closed_health, dict) else None
            closed_health_ok = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("token_scopes") is False
            )
            closed_reverse_status, closed_reversed = _request(
                "POST",
                f"{closed_url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
                token=OPERATOR,
            )
            observed["closed_reverse"] = (
                closed_reversed if isinstance(closed_reversed, dict) else None
            )
            closed_reverse_ok = (
                closed_reverse_status == 200
                and isinstance(closed_reversed, dict)
                and closed_reversed.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
            closed_ok = closed_health_ok and closed_reverse_ok
        finally:
            observed["closed_stderr"] = (_stop_plane(closed) or "")[-4000:]

        passed = all(
            (
                health_ok,
                shout_ok,
                denied_ok,
                listed_ok,
                operator_ok,
                closed_ok,
                follow_ok,
            )
        )
        observed["checks"] = {
            "health": health_ok,
            "scoped_shout": shout_ok,
            "scoped_denied": denied_ok,
            "scoped_listing": listed_ok,
            "operator_reverse": operator_ok,
            "fail_closed": closed_ok,
            "follow_up_shout": follow_ok,
        }
        return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
