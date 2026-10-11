"""Acceptance probe: terminal goal sessions deliver HMAC-signed callbacks.

Durable sessions currently publish status only to connected SSE clients.
An operator who creates a session and disconnects never receives the
terminal result. This probe starts the live HTTP invocation plane and
requires:

1. POST /sessions with notify_url and notify_secret registers a callback
   and the session still solves with the declared reverse output.
2. An independent loopback listener receives a POST whose
   X-Hub-Signature-256 verifies with the shared secret and whose JSON
   body names the session_id, status solved, session_digest, and
   declared output.
3. A listener that answers 503 once then 200 receives a retry and the
   session record shows delivered.
4. A wrong-secret signature does not verify.
5. A session without notify_url does not POST to the listener.
6. A non-loopback notify_url is refused before any tool runs.
7. A follow-up REST POST /invoke of the text-reverser still returns the
   declared reverse output.

On the pre-mission plane POST /sessions ignores notify_url, so no
outbound callback is delivered and the probe reports passed=false.
Both outcomes exit 0 with JSON ``passed`` and nonempty ``observed``.
"""

from __future__ import annotations

import hmac
import json
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

PROBE_TEXT = "session-notify-1d23b20b"
EXPECTED = PROBE_TEXT[::-1]
SECRET = "session-notify-secret"
SIGNATURE_HEADER = "X-Hub-Signature-256"

_FAST_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


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


def _write_tool(root: Path) -> None:
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True)
    (tool_dir / "tool.py").write_text(_FAST_TOOL, encoding="utf-8")
    (tool_dir / "absorption.json").write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    cid = "capability.absorbed-text-reverser"
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {cid: _ledger_entry(cid, "probe text reverser")},
            }
        ),
        encoding="utf-8",
    )


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    timeout: int = 30,
) -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
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


def _verify(secret: str, body: bytes, header: str) -> bool:
    digest = hmac.new(secret.encode("utf-8"), body, "sha256").hexdigest()
    expected = f"sha256={digest}"
    try:
        return bool(header) and hmac.compare_digest(expected, header)
    except (TypeError, ValueError):
        return False


def _start_listener(*, fail_first: bool = False):
    box: dict = {"lock": threading.Lock(), "items": [], "fail_first": fail_first}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            item = {
                "path": self.path,
                "raw": raw,
                "sig": self.headers.get(SIGNATURE_HEADER) or "",
            }
            with box["lock"]:
                box["items"].append(item)
                count = len(box["items"])
            if box["fail_first"] and count == 1:
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    url = f"http://127.0.0.1:{port}/hooks/session"
    return server, thread, url, box


def _stop_listener(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    try:
        server.shutdown()
    except OSError:
        pass
    try:
        server.server_close()
    except OSError:
        pass
    thread.join(timeout=5)


def _wait_items(box: dict, count: int, timeout: float = 8.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with box["lock"]:
            if len(box["items"]) >= count:
                return list(box["items"])
        time.sleep(0.02)
    with box["lock"]:
        return list(box["items"])


def _wait_session(base: str, session_id: str, wanted: set[str], timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        status, body = _request("GET", f"{base}/sessions/{session_id}")
        if status == 200 and isinstance(body, dict):
            session = body.get("session") if isinstance(body.get("session"), dict) else {}
            last = session
            if session.get("status") in wanted:
                return session
        time.sleep(0.05)
    return last


def main() -> dict[str, object]:
    observed: dict[str, object] = {"family": "session-outcome-webhooks"}
    try:
        from blackhole_agent.capability_service import build_server
    except Exception as error:
        observed["error"] = f"{type(error).__name__}: {error}"
        return {"passed": False, "observed": observed}

    listeners: list[tuple[ThreadingHTTPServer, threading.Thread]] = []
    with tempfile.TemporaryDirectory(prefix="session-notify-probe-") as directory:
        root = Path(directory) / "repo"
        _write_tool(root)
        server = build_server(root, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{int(server.server_address[1])}"
        try:
            happy, happy_thread, happy_url, happy_box = _start_listener()
            listeners.append((happy, happy_thread))
            create_status, created = _request(
                "POST",
                f"{base}/sessions",
                {
                    "initial_state": {"raw_text": PROBE_TEXT},
                    "goal": ["reversed_text"],
                    "notify_url": happy_url,
                    "notify_secret": SECRET,
                },
            )
            session = created.get("session") if isinstance(created, dict) else None
            session_id = str((session or {}).get("session_id") or "")
            observed["create_status"] = create_status
            observed["secret_leaked"] = bool(session and "notify_secret" in session)
            observed["secret_present"] = bool(session and session.get("notify_secret_present"))
            final = _wait_session(base, session_id, {"solved"}) if session_id else {}
            observed["solved_status"] = final.get("status")
            observed["solved_outcome"] = final.get("outcome")
            items = _wait_items(happy_box, 1)
            observed["delivery_count"] = len(items)
            payload = {}
            signature_ok = False
            wrong_secret_rejected = False
            if items:
                try:
                    payload = json.loads(items[0]["raw"].decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, KeyError):
                    payload = {}
                signature_ok = _verify(SECRET, items[0]["raw"], items[0]["sig"])
                wrong_secret_rejected = not _verify(
                    "wrong-secret-value", items[0]["raw"], items[0]["sig"]
                )
            observed["payload"] = {
                "event": payload.get("event"),
                "session_id": payload.get("session_id"),
                "status": payload.get("status"),
                "outcome": payload.get("outcome"),
                "digest_match": payload.get("session_digest") == final.get("session_digest"),
            }
            observed["signature_ok"] = signature_ok
            observed["wrong_secret_rejected"] = wrong_secret_rejected
            delivered_flag = False
            if session_id:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    refreshed = _wait_session(base, session_id, {"solved"}, timeout=0.5)
                    if (refreshed.get("notify") or {}).get("delivered"):
                        delivered_flag = True
                        break
            observed["delivered_flag"] = delivered_flag
            happy_ok = (
                create_status == 200
                and bool(session_id)
                and not (session and "notify_secret" in session)
                and bool(session and session.get("notify_secret_present"))
                and final.get("status") == "solved"
                and final.get("outcome") == {"reversed_text": EXPECTED}
                and len(items) >= 1
                and payload.get("event") == "session.terminal"
                and payload.get("session_id") == session_id
                and payload.get("status") == "solved"
                and payload.get("outcome") == {"reversed_text": EXPECTED}
                and payload.get("session_digest") == final.get("session_digest")
                and signature_ok
                and wrong_secret_rejected
                and delivered_flag
            )

            retry, retry_thread, retry_url, retry_box = _start_listener(fail_first=True)
            listeners.append((retry, retry_thread))
            retry_status, retry_created = _request(
                "POST",
                f"{base}/sessions",
                {
                    "initial_state": {"raw_text": PROBE_TEXT},
                    "goal": ["reversed_text"],
                    "notify_url": retry_url,
                    "notify_secret": SECRET,
                },
            )
            retry_session = retry_created.get("session") if isinstance(retry_created, dict) else None
            retry_id = str((retry_session or {}).get("session_id") or "")
            _wait_session(base, retry_id, {"solved"}) if retry_id else {}
            retry_items = _wait_items(retry_box, 2)
            retry_delivered = False
            if retry_id:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    refreshed = _wait_session(base, retry_id, {"solved"}, timeout=0.5)
                    if (refreshed.get("notify") or {}).get("delivered"):
                        retry_delivered = True
                        break
            observed["retry_status"] = retry_status
            observed["retry_delivery_count"] = len(retry_items)
            observed["retry_delivered"] = retry_delivered
            retry_ok = (
                retry_status == 200
                and len(retry_items) >= 2
                and retry_delivered
            )

            quiet, quiet_thread, quiet_url, quiet_box = _start_listener()
            listeners.append((quiet, quiet_thread))
            quiet_status, quiet_created = _request(
                "POST",
                f"{base}/sessions",
                {"initial_state": {"raw_text": PROBE_TEXT}, "goal": ["reversed_text"]},
            )
            quiet_session = quiet_created.get("session") if isinstance(quiet_created, dict) else None
            quiet_id = str((quiet_session or {}).get("session_id") or "")
            quiet_final = _wait_session(base, quiet_id, {"solved"}) if quiet_id else {}
            time.sleep(0.4)
            with quiet_box["lock"]:
                quiet_count = len(quiet_box["items"])
            observed["quiet_status"] = quiet_status
            observed["quiet_solved"] = quiet_final.get("status")
            observed["quiet_deliveries"] = quiet_count
            quiet_ok = (
                quiet_status == 200
                and quiet_final.get("status") == "solved"
                and quiet_final.get("outcome") == {"reversed_text": EXPECTED}
                and quiet_count == 0
                and not (quiet_session or {}).get("notify_url")
            )

            refuse_status, refuse_body = _request(
                "POST",
                f"{base}/sessions",
                {
                    "initial_state": {"raw_text": PROBE_TEXT},
                    "goal": ["reversed_text"],
                    "notify_url": "http://8.8.8.8/hooks/session",
                    "notify_secret": SECRET,
                },
            )
            listed_status, listed = _request("GET", f"{base}/sessions")
            listed_count = listed.get("count") if isinstance(listed, dict) else None
            observed["refuse_status"] = refuse_status
            observed["refuse_error"] = (
                refuse_body.get("error") if isinstance(refuse_body, dict) else refuse_body
            )
            observed["listed_count_after_refuse"] = listed_count
            refuse_ok = refuse_status == 422 and listed_status == 200 and listed_count == 3

            follow_status, follow = _request(
                "POST",
                f"{base}/invoke",
                {
                    "capability_id": "capability.absorbed-text-reverser",
                    "input": {"raw_text": PROBE_TEXT},
                },
            )
            output = follow.get("output") if isinstance(follow, dict) else None
            observed["follow_status"] = follow_status
            observed["follow_output"] = output
            follow_ok = (
                follow_status == 200
                and isinstance(output, dict)
                and output.get("reversed_text") == EXPECTED
            )

            checks = {
                "signed_terminal_callback": happy_ok,
                "retry_after_503": retry_ok,
                "no_notify_stays_silent": quiet_ok,
                "non_loopback_refused": refuse_ok,
                "follow_up_invoke_ok": follow_ok,
            }
            observed["checks"] = checks
            return {"passed": bool(all(checks.values())), "observed": observed}
        finally:
            for listener, listener_thread in listeners:
                _stop_listener(listener, listener_thread)
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)


if __name__ == "__main__":
    try:
        verdict = main()
    except Exception as error:  # never crash the sweep: unmet, not crashed
        verdict = {
            "passed": False,
            "observed": {
                "family": "session-outcome-webhooks",
                "fatal": f"{type(error).__name__}: {error}",
            },
        }
    print(json.dumps(verdict))
    raise SystemExit(0)
