"""Acceptance probe: live plane issues RFC 9728/OAuth 2.1 PKCE tokens.

A token-gated POST /mcp currently returns a static Bearer 401 without
resource_metadata, so a spec-compliant MCP host cannot discover an
authorization server or obtain a token. This probe starts the invocation
plane as a separate OS process and drives real loopback HTTP:

1. GET /health reports oauth_protected_resource true when --token is set.
2. Unauthenticated POST /mcp is HTTP 401 with WWW-Authenticate
   resource_metadata.
3. Unauthenticated GET /.well-known/oauth-protected-resource and
   GET /.well-known/oauth-authorization-server return RFC 9728/8414 JSON.
4. POST /oauth/register of a loopback public client returns a client_id;
   a foreign redirect_uri is HTTP 400.
5. GET /oauth/authorize with S256 PKCE and the operator bearer is HTTP 302
   with a one-time code; without the operator bearer it is 200 HTML consent.
6. POST /oauth/token with that code and verifier returns an access_token;
   a replayed code is HTTP 400.
7. POST /mcp initialize and POST /invoke of the fixture text-reverser with
   that bearer succeed and return the declared reverse output.
8. A plane started without --token reports oauth_protected_resource false,
   well-known OAuth paths 404, and POST /invoke still reverses.

On the pre-mission plane well-known OAuth paths 401/404 and health omits
oauth_protected_resource, so the probe reports passed=false. Both outcomes
exit 0 with JSON passed and nonempty observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
from base64 import urlsafe_b64encode
from pathlib import Path
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit

PROBE_TEXT = "oauth-9728-498cc9a6"
EXPECTED_REVERSE = PROBE_TEXT[::-1]
REVERSE_ID = "capability.absorbed-text-reverser"
OPERATOR = "operator-token-498cc9a6"

_REVERSE_TOOL = (
    "import json, sys\n"
    "state = json.load(sys.stdin)\n"
    "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n"
)


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):  # noqa: ANN001
        raise urlrequest.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _request(
    method: str,
    url: str,
    payload: dict | None = None,
    *,
    token: str | None = None,
    form: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    follow: bool = True,
    timeout: int = 45,
) -> tuple[int, object, dict[str, str]]:
    data = None
    extra = dict(headers or {})
    if form is not None:
        data = urlencode(form).encode("utf-8")
        extra.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        extra.setdefault("Content-Type", "application/json")
        extra.setdefault("Accept", "application/json")
    req = urlrequest.Request(url, data=data, method=method)
    for key, value in extra.items():
        req.add_header(key, value)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    opener = urlrequest.build_opener() if follow else urlrequest.build_opener(_NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            captured = {key.lower(): value for key, value in response.headers.items()}
            raw = response.read().decode("utf-8")
            try:
                parsed: object = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return response.status, parsed, captured
    except HTTPError as exc:
        captured = {key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])}
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            body = ""
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed, captured
    except (URLError, TimeoutError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, {}


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


def _write_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "probe-workspace"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
    tool_dir.mkdir(parents=True, exist_ok=True)
    (tool_dir / "tool.py").write_text(_REVERSE_TOOL, encoding="utf-8")
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
                    {"input": {"raw_text": "x"}, "expect": {"reversed_text": "x"}},
                    {"input": {"raw_text": "y"}, "expect": {"reversed_text": "y"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "capabilities" / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "",
                "capabilities": {REVERSE_ID: _ledger_entry(REVERSE_ID, "probe text reverser")},
            }
        ),
        encoding="utf-8",
    )


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
    observed: dict[str, object] = {"family": "oauth-protected-resource"}
    try:
        import blackhole_agent.capability_service as service
        import blackhole_agent.oauth_protected_resource as oauth
    except Exception as error:
        observed["error"] = type(error).__name__
        observed["detail"] = str(error)
        return {"passed": False, "observed": observed}
    if not hasattr(oauth, "OAuthIssuer"):
        observed["detail"] = "baseline plane has no live OAuth protected resource"
        return {"passed": False, "observed": observed}

    src_root = Path(service.__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="oauth-resource-probe-") as directory:
        base = Path(directory)
        root = base / "repo"
        _write_workspace(root)

        process, sink = _start_plane(src_root, root, ["--token", OPERATOR])
        try:
            ready = sink.get("ready")
            observed["ready"] = ready
            if not isinstance(ready, dict) or not ready.get("listening"):
                err = _stop_plane(process)
                observed["detail"] = "server never reported a listening port"
                observed["stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            url = f"http://127.0.0.1:{ready['listening']}"
            mcp = f"{url}/mcp"
            observed["ready_oauth"] = ready.get("oauth_protected_resource")

            health_status, health, _ = _request("GET", f"{url}/health")
            observed["health_status"] = health_status
            observed["health"] = health if isinstance(health, dict) else None
            health_ok = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("oauth_protected_resource") is True
            )

            unauth_status, unauth, unauth_headers = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {},
                    },
                },
            )
            www = str(unauth_headers.get("www-authenticate") or "")
            observed["www_authenticate"] = www
            challenge_ok = (
                unauth_status == 401
                and isinstance(unauth, dict)
                and unauth.get("error") == "authorization_required"
                and "resource_metadata=" in www
                and "/.well-known/oauth-protected-resource" in www
            )

            meta_status, meta, _ = _request(
                "GET", f"{url}/.well-known/oauth-protected-resource"
            )
            observed["resource_metadata"] = meta if isinstance(meta, dict) else None
            meta_ok = (
                meta_status == 200
                and isinstance(meta, dict)
                and meta.get("resource") == mcp
                and url in (meta.get("authorization_servers") or [])
            )

            as_status, as_meta, _ = _request(
                "GET", f"{url}/.well-known/oauth-authorization-server"
            )
            observed["as_metadata"] = as_meta if isinstance(as_meta, dict) else None
            as_ok = (
                as_status == 200
                and isinstance(as_meta, dict)
                and as_meta.get("issuer") == url
                and as_meta.get("token_endpoint") == f"{url}/oauth/token"
                and as_meta.get("authorization_endpoint") == f"{url}/oauth/authorize"
                and as_meta.get("registration_endpoint") == f"{url}/oauth/register"
                and "S256" in (as_meta.get("code_challenge_methods_supported") or [])
            )

            redirect = "http://127.0.0.1:9/cb"
            reg_status, registered, _ = _request(
                "POST",
                f"{url}/oauth/register",
                {
                    "redirect_uris": [redirect],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code"],
                    "response_types": ["code"],
                    "client_name": "oauth-probe",
                },
            )
            client_id = (
                str(registered.get("client_id") or "") if isinstance(registered, dict) else ""
            )
            observed["register_status"] = reg_status
            observed["client_id"] = client_id
            register_ok = reg_status == 201 and bool(client_id)

            foreign_status, foreign, _ = _request(
                "POST",
                f"{url}/oauth/register",
                {"redirect_uris": ["https://evil.example/cb"]},
            )
            observed["foreign_register"] = foreign if isinstance(foreign, dict) else None
            foreign_ok = (
                foreign_status == 400
                and isinstance(foreign, dict)
                and foreign.get("error") == "invalid_redirect_uri"
            )

            verifier = secrets.token_urlsafe(32)
            challenge = _pkce_s256(verifier)
            authorize_url = (
                f"{url}/oauth/authorize?"
                + urlencode(
                    {
                        "response_type": "code",
                        "client_id": client_id,
                        "redirect_uri": redirect,
                        "code_challenge": challenge,
                        "code_challenge_method": "S256",
                        "state": "st",
                        "resource": mcp,
                    }
                )
            )
            denied_status, denied_body, denied_headers = _request(
                "GET", authorize_url, follow=False
            )
            loc_status, _, loc_headers = _request(
                "GET", authorize_url, token=OPERATOR, follow=False
            )
            location = str(loc_headers.get("location") or "")
            code = (parse_qs(urlsplit(location).query).get("code") or [""])[0]
            observed["authorize_denied"] = denied_status
            observed["authorize_status"] = loc_status
            observed["authorize_location"] = location
            denied_page = denied_body if isinstance(denied_body, str) else ""
            authorize_ok = (
                denied_status == 200
                and 'id="oauth-consent"' in denied_page
                and not str(denied_headers.get("location") or "")
                and loc_status == 302
                and bool(code)
                and location.startswith(redirect)
            )

            wrong_status, wrong_body, _ = _request(
                "POST",
                f"{url}/oauth/token",
                form={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": "wrong-verifier-wrong-verifier-wrong-xx",
                    "resource": mcp,
                },
            )
            observed["wrong_verifier_status"] = wrong_status
            wrong_ok = (
                wrong_status == 400
                and isinstance(wrong_body, dict)
                and wrong_body.get("error") == "invalid_grant"
            )
            loc_status, _, loc_headers = _request(
                "GET", authorize_url, token=OPERATOR, follow=False
            )
            location = str(loc_headers.get("location") or "")
            code = (parse_qs(urlsplit(location).query).get("code") or [""])[0]
            observed["authorize_retry_status"] = loc_status
            token_status, token_body, _ = _request(
                "POST",
                f"{url}/oauth/token",
                form={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": verifier,
                    "resource": mcp,
                },
            )
            access = (
                str(token_body.get("access_token") or "")
                if isinstance(token_body, dict)
                else ""
            )
            observed["token_status"] = token_status
            token_ok = (
                token_status == 200
                and isinstance(token_body, dict)
                and token_body.get("token_type") == "Bearer"
                and bool(access)
            )

            replay_status, replay, _ = _request(
                "POST",
                f"{url}/oauth/token",
                form={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": verifier,
                    "resource": mcp,
                },
            )
            observed["replay_status"] = replay_status
            replay_ok = (
                replay_status == 400
                and isinstance(replay, dict)
                and replay.get("error") == "invalid_grant"
            )

            hs_status, handshake, hs_headers = _request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "oauth-probe", "version": "1"},
                    },
                },
                token=access,
            )
            observed["mcp_initialize_status"] = hs_status
            mcp_ok = (
                hs_status == 200
                and isinstance(handshake, dict)
                and bool(hs_headers.get("mcp-session-id"))
                and isinstance(handshake.get("result"), dict)
            )

            invoke_status, invoked, _ = _request(
                "POST",
                f"{url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
                token=access,
            )
            observed["invoke_status"] = invoke_status
            observed["invoked"] = invoked if isinstance(invoked, dict) else None
            invoke_ok = (
                invoke_status == 200
                and isinstance(invoked, dict)
                and invoked.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
        finally:
            observed["server_stderr"] = (_stop_plane(process) or "")[-4000:]

        closed_root = base / "closed"
        _write_workspace(closed_root)
        closed, closed_sink = _start_plane(src_root, closed_root)
        try:
            closed_ready = closed_sink.get("ready")
            observed["closed_ready"] = closed_ready
            if not isinstance(closed_ready, dict) or not closed_ready.get("listening"):
                err = _stop_plane(closed)
                observed["closed_detail"] = "closed plane never reported a listening port"
                observed["closed_stderr"] = err[-2000:]
                return {"passed": False, "observed": observed}
            closed_url = f"http://127.0.0.1:{closed_ready['listening']}"
            closed_health_status, closed_health, _ = _request("GET", f"{closed_url}/health")
            closed_meta_status, _, _ = _request(
                "GET", f"{closed_url}/.well-known/oauth-protected-resource"
            )
            closed_reverse_status, closed_reversed, _ = _request(
                "POST",
                f"{closed_url}/invoke",
                {"capability_id": REVERSE_ID, "input": {"raw_text": PROBE_TEXT}},
            )
            observed["closed_health"] = closed_health if isinstance(closed_health, dict) else None
            observed["closed_meta_status"] = closed_meta_status
            observed["closed_reverse"] = (
                closed_reversed if isinstance(closed_reversed, dict) else None
            )
            closed_ok = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("oauth_protected_resource") is False
                and closed_meta_status == 404
                and closed_reverse_status == 200
                and isinstance(closed_reversed, dict)
                and closed_reversed.get("output", {}).get("reversed_text") == EXPECTED_REVERSE
            )
        finally:
            observed["closed_stderr"] = (_stop_plane(closed) or "")[-4000:]

        passed = all(
            (
                health_ok,
                challenge_ok,
                meta_ok,
                as_ok,
                register_ok,
                foreign_ok,
                authorize_ok,
                wrong_ok,
                token_ok,
                replay_ok,
                mcp_ok,
                invoke_ok,
                closed_ok,
            )
        )
        observed["checks"] = {
            "health": health_ok,
            "challenge": challenge_ok,
            "resource_metadata": meta_ok,
            "as_metadata": as_ok,
            "register": register_ok,
            "foreign_redirect": foreign_ok,
            "authorize": authorize_ok,
            "wrong_verifier": wrong_ok,
            "token": token_ok,
            "replay": replay_ok,
            "mcp_initialize": mcp_ok,
            "invoke": invoke_ok,
            "fail_closed": closed_ok,
        }
        return {"passed": passed, "observed": observed}


if __name__ == "__main__":
    verdict = main()
    print(json.dumps(verdict))
    sys.exit(0)
