"""RFC 9728 protected-resource metadata and OAuth 2.1 issuance on the live plane.

A token-gated ``POST /mcp`` currently answers 401 with a static Bearer
challenge and no ``resource_metadata`` parameter. Spec-compliant MCP hosts
cannot discover an authorization server, register, obtain a PKCE token, or
complete initialize. This module closes that hole when an operator
``--token`` is configured:

- 401 ``WWW-Authenticate`` includes RFC 9728 ``resource_metadata``
- unauthenticated ``GET /.well-known/oauth-protected-resource``
- unauthenticated ``GET /.well-known/oauth-authorization-server``
- unauthenticated RFC 7591 ``POST /oauth/register`` for loopback public clients
- ``GET /oauth/authorize`` with S256 PKCE; an operator bearer auto-approves
  and 302s a one-time code to the registered loopback redirect
- a browser ``GET /oauth/authorize`` without an operator ``Authorization``
  header serves an HTML consent page; ``POST /oauth/authorize`` with
  ``decision=allow`` and the operator token in the form body 302s the same
  one-time code, so a user-agent can finish the flow without a header
- ``POST /oauth/token`` exchanges the code (or operator ``client_credentials``)
  for an access token that authorizes ``POST /mcp`` and ``POST /invoke``
- a plane without ``--token`` stays historically open: well-known OAuth
  paths 404 and ``GET /health`` reports ``oauth_protected_resource`` false
- loopback browser Origins (any port) may CORS-call OAuth and ``/mcp`` so an
  MCP Inspector on another loopback port can complete the flow; ``POST
  /invoke`` keeps the same-origin CSRF guard
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import ipaddress
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunsplit

from blackhole_agent.invocation_token_scopes import TokenPrincipal, UNRESTRICTED

SCHEMA_VERSION = 1
OAUTH_PROTECTED_RESOURCE_ID = "capability.oauth-protected-resource"
OAUTH_PROTECTED_RESOURCE_NAME = "Live-plane RFC 9728 OAuth 2.1 protected resource"
OAUTH_AUTHORIZE_CONSENT_ID = "capability.oauth-authorize-consent"
OAUTH_AUTHORIZE_CONSENT_NAME = "Browser OAuth authorize consent page"
OPERATOR_CLIENT_ID = "blackhole-operator"
REALM = "blackhole-invocation-plane"
RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_SERVER_METADATA_PATH = "/.well-known/oauth-authorization-server"
AUTHORIZE_PATH = "/oauth/authorize"
TOKEN_PATH = "/oauth/token"
REGISTER_PATH = "/oauth/register"
CODE_TTL_SECONDS = 300
ACCESS_TTL_SECONDS = 3600
MAX_CLIENTS = 256
MAX_CODES = 256
MAX_TOKENS = 1024
MAX_REDIRECT_URIS = 8
PKCE_METHODS = frozenset({"S256"})
PUBLIC_GRANT_TYPES = frozenset({"authorization_code"})
CONFIDENTIAL_GRANT_TYPES = frozenset({"authorization_code", "client_credentials"})
CORS_ALLOW_HEADERS = "Authorization, Content-Type, Mcp-Session-Id, Last-Event-ID"
CORS_ALLOW_METHODS = "GET, POST, DELETE, OPTIONS"

OAUTH_PROTECTED_RESOURCE_GOAL = (
    "Repair missing MCP OAuth 2.1 resource-server discovery and token issuance "
    "on the live invocation plane: a token-gated POST /mcp currently returns a "
    "static Bearer 401 without RFC 9728 resource_metadata, so a spec-compliant "
    "MCP host cannot discover an authorization server, obtain a PKCE token, or "
    "complete initialize."
)
OAUTH_PROTECTED_RESOURCE_DONE_WHEN = (
    "A live plane started with --token reports GET /health "
    "oauth_protected_resource true; an unauthenticated POST /mcp returns HTTP "
    "401 whose WWW-Authenticate includes resource_metadata; unauthenticated "
    "GET /.well-known/oauth-protected-resource and GET "
    "/.well-known/oauth-authorization-server return the RFC 9728/8414 "
    "documents; POST /oauth/register of a loopback public client returns a "
    "client_id; GET /oauth/authorize with S256 PKCE and the operator bearer "
    "returns 302 with a one-time code; POST /oauth/token with that code and "
    "code_verifier returns an access_token; POST /mcp initialize and POST "
    "/invoke of the fixture text-reverser with that bearer succeed and return "
    "the declared reverse output. A replayed code or wrong verifier is HTTP "
    "400. A plane started without --token reports oauth_protected_resource "
    "false, well-known OAuth paths 404, and POST /invoke of the text-reverser "
    "still returns the declared reverse output."
)
OAUTH_AUTHORIZE_CONSENT_LEFTOVER = (
    "Optional later work is a browser consent page so GET /oauth/authorize can "
    "complete without an operator Authorization header."
)
OAUTH_AUTHORIZE_CONSENT_GOAL = (
    "A browser opening GET /oauth/authorize cannot send an operator "
    "Authorization header, so the live authorization endpoint currently 401s "
    "instead of letting the resource owner approve the client. Serve an HTML "
    "consent page and accept POST /oauth/authorize with the operator token in "
    "the form body so the PKCE code can issue without that header."
)
OAUTH_AUTHORIZE_CONSENT_DONE_WHEN = (
    "A live plane started with --token reports GET /health "
    "oauth_authorize_consent true. GET /oauth/authorize with S256 PKCE and no "
    "Authorization header returns HTTP 200 text/html whose consent form names "
    "operator_token and decision. POST /oauth/authorize with decision=allow and "
    "the operator token in the form body, still without an Authorization "
    "header, returns 302 with a one-time code; POST /oauth/token with that code "
    "and verifier returns an access_token that POST /invoke of the fixture "
    "text-reverser accepts. POST decision=allow with the wrong token does not "
    "issue a code. POST decision=deny redirects with error=access_denied. GET "
    "with the operator bearer still 302s a code. A plane started without "
    "--token reports oauth_authorize_consent false and GET /oauth/authorize is "
    "HTTP 404."
)


def _canonical_hostname(host: str) -> str:
    raw = str(host or "").strip().strip("[]").lower()
    if raw.startswith("::ffff:"):
        raw = raw[7:]
    return raw.rstrip(".")


def host_is_loopback(host: str) -> bool:
    raw = _canonical_hostname(host)
    if not raw:
        return False
    if raw in {"localhost", "localhost."}:
        return True
    try:
        return ipaddress.ip_address(raw).is_loopback
    except ValueError:
        return False


def is_loopback_origin(origin: str, *, tls: bool = False) -> bool:
    """True when Origin is a loopback http(s) origin (any port)."""

    text = str(origin or "").strip()
    if not text or text.lower() == "null":
        return False
    parsed = urlparse(text)
    expected = "https" if tls else "http"
    if parsed.scheme != expected:
        return False
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        return False
    if parsed.username or parsed.password:
        return False
    host = parsed.hostname or ""
    return host_is_loopback(host)


def is_loopback_redirect(uri: str) -> bool:
    """True when a redirect_uri is loopback http(s) with no fragment."""

    text = str(uri or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.fragment or parsed.username or parsed.password:
        return False
    host = parsed.hostname or ""
    return host_is_loopback(host)


def is_oauth_public_path(path: str) -> bool:
    """Unauthenticated discovery, registration, authorize, and token paths."""

    cleaned = str(path or "").split("?", 1)[0]
    return cleaned in {
        RESOURCE_METADATA_PATH,
        AUTHORIZATION_SERVER_METADATA_PATH,
        AUTHORIZE_PATH,
        TOKEN_PATH,
        REGISTER_PATH,
    }


def is_oauth_cors_path(path: str) -> bool:
    """OAuth public paths plus Streamable HTTP MCP, where browser hosts call."""

    cleaned = str(path or "").split("?", 1)[0].rstrip("/")
    if is_oauth_public_path(path):
        return True
    return cleaned == "/mcp"


def pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(str(verifier).encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _b64url(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def parse_basic_client(header: str | None) -> tuple[str, str] | None:
    """Return (client_id, client_secret) from HTTP Basic, else None."""

    if not header:
        return None
    scheme, _, rest = str(header).strip().partition(" ")
    if scheme.lower() != "basic" or not rest.strip():
        return None
    try:
        decoded = base64.b64decode(rest.strip().encode("ascii"), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    client_id, separator, secret = decoded.partition(":")
    if separator != ":":
        return None
    return client_id, secret


def append_query(uri: str, **fields: str) -> str:
    parts = urlsplit(uri)
    existing = parse_qs(parts.query, keep_blank_values=True)
    merged: list[tuple[str, str]] = []
    for key, values in existing.items():
        for value in values:
            merged.append((key, value))
    for key, value in fields.items():
        merged.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment))


def consent_page(
    *,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    resource: str,
    response_type: str = "code",
    error: str = "",
) -> str:
    """Self-contained HTML consent form for GET /oauth/authorize without a header."""

    def field(name: str, value: str) -> str:
        return (
            f'<input type="hidden" name="{html.escape(name, quote=True)}" '
            f'value="{html.escape(value, quote=True)}">'
        )

    error_block = ""
    if error:
        error_block = f'<p class="err" id="oauth-consent-error">{html.escape(error)}</p>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Authorize application</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #101418; color: #d7dde3; }}
h1, h2 {{ color: #7fd4ff; }}
section {{ border: 1px solid #2a323b; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
dt {{ color: #8b949e; font-size: 0.8rem; }}
dd {{ margin: 0 0 0.75rem 0; font-family: monospace; word-break: break-all; }}
input {{ width: 100%; background: #0b0e11; color: #d7dde3; border: 1px solid #2a323b; border-radius: 4px; font-family: monospace; padding: 0.4rem; box-sizing: border-box; }}
button {{ background: #1f6feb; color: white; border: 0; border-radius: 4px; padding: 0.4rem 1rem; cursor: pointer; margin-right: 0.5rem; }}
button.deny {{ background: #6e7681; }}
.err {{ color: #ff8489; }}
</style>
</head>
<body>
<main id="oauth-consent">
<h1>Authorize application</h1>
<section>
<p>A public client is requesting an access token for this invocation plane. Allowing issues a one-time authorization code to the registered loopback redirect. The operator token is submitted in the form body; no <code>Authorization</code> header is required.</p>
{error_block}
<dl>
<dt>client_id</dt><dd id="consent-client-id">{html.escape(client_id)}</dd>
<dt>redirect_uri</dt><dd id="consent-redirect">{html.escape(redirect_uri)}</dd>
<dt>resource</dt><dd id="consent-resource">{html.escape(resource)}</dd>
</dl>
<form id="oauth-consent-form" method="post" action="{html.escape(AUTHORIZE_PATH, quote=True)}">
{field("response_type", response_type)}
{field("client_id", client_id)}
{field("redirect_uri", redirect_uri)}
{field("code_challenge", code_challenge)}
{field("code_challenge_method", code_challenge_method)}
{field("state", state)}
{field("resource", resource)}
<p><label for="operator-token">operator token</label></p>
<input id="operator-token" name="operator_token" type="password" autocomplete="off" placeholder="BLACKHOLE_INVOCATION_TOKEN">
<p>
<button type="submit" name="decision" value="allow">Allow</button>
<button type="submit" class="deny" name="decision" value="deny">Deny</button>
</p>
</form>
</section>
</main>
</body>
</html>
"""


def cors_headers(origin: str | None, *, enabled: bool, tls: bool = False) -> dict[str, str]:
    text = str(origin or "").strip()
    if not enabled or not is_loopback_origin(text, tls=tls):
        return {}
    return {
        "Access-Control-Allow-Origin": text,
        "Access-Control-Allow-Headers": CORS_ALLOW_HEADERS,
        "Access-Control-Allow-Methods": CORS_ALLOW_METHODS,
        "Vary": "Origin",
    }


def www_authenticate(origin: str) -> str:
    metadata = f"{str(origin).rstrip('/')}{RESOURCE_METADATA_PATH}"
    return f'Bearer realm="{REALM}", resource_metadata="{metadata}"'


def resource_metadata_document(origin: str) -> dict[str, Any]:
    base = str(origin).rstrip("/")
    return {
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{base}/console",
    }


def authorization_server_metadata_document(origin: str) -> dict[str, Any]:
    base = str(origin).rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}{AUTHORIZE_PATH}",
        "token_endpoint": f"{base}{TOKEN_PATH}",
        "registration_endpoint": f"{base}{REGISTER_PATH}",
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_post",
            "client_secret_basic",
        ],
        "scopes_supported": ["mcp"],
        "authorization_response_iss_parameter_supported": True,
    }


@dataclass
class OAuthClient:
    client_id: str
    client_secret: str | None
    redirect_uris: tuple[str, ...]
    auth_method: str
    grant_types: frozenset[str]
    created_at: float = field(default_factory=time.time)


@dataclass
class AuthCode:
    code: str
    client_id: str
    redirect_uri: str
    code_challenge: str
    resource: str
    expires_at: float
    principal: TokenPrincipal = UNRESTRICTED


@dataclass
class AccessToken:
    token: str
    client_id: str
    resource: str
    expires_at: float
    principal: TokenPrincipal = UNRESTRICTED


class OAuthIssuer:
    """In-process OAuth 2.1 authorization server bound to one invocation plane."""

    def __init__(self, operator_token: str = "") -> None:
        self.operator_token = str(operator_token or "").strip()
        self.enabled = bool(self.operator_token)
        self._lock = threading.Lock()
        self._clients: dict[str, OAuthClient] = {}
        self._codes: dict[str, AuthCode] = {}
        self._tokens: dict[str, AccessToken] = {}
        if self.enabled:
            self._clients[OPERATOR_CLIENT_ID] = OAuthClient(
                client_id=OPERATOR_CLIENT_ID,
                client_secret=self.operator_token,
                redirect_uris=(),
                auth_method="client_secret_post",
                grant_types=frozenset({"client_credentials"}),
            )

    def health(self) -> dict[str, Any]:
        return {
            "oauth_protected_resource": self.enabled,
            "oauth_authorization_code": self.enabled,
            "oauth_client_credentials": self.enabled,
            "oauth_authorize_consent": self.enabled,
        }

    def authenticate(self, offered: str) -> TokenPrincipal | None:
        token = str(offered or "")
        if not self.enabled or not token:
            return None
        now = time.time()
        with self._lock:
            record = self._tokens.get(token)
            if record is None:
                return None
            if record.expires_at <= now:
                self._tokens.pop(token, None)
                return None
            return record.principal

    def register_client(self, body: Mapping[str, Any]) -> tuple[int, dict[str, Any]]:
        if not self.enabled:
            return 404, {"ok": False, "error": "oauth_disabled"}
        redirect_uris = body.get("redirect_uris") or []
        if not isinstance(redirect_uris, list) or not redirect_uris:
            return 400, {"error": "invalid_redirect_uri", "error_description": "redirect_uris required"}
        cleaned: list[str] = []
        for item in redirect_uris[:MAX_REDIRECT_URIS]:
            uri = str(item or "").strip()
            if not is_loopback_redirect(uri):
                return 400, {
                    "error": "invalid_redirect_uri",
                    "error_description": "redirect_uri must be loopback http(s)",
                }
            cleaned.append(uri)
        auth_method = str(body.get("token_endpoint_auth_method") or "none").strip() or "none"
        if auth_method not in {"none", "client_secret_post", "client_secret_basic"}:
            return 400, {"error": "invalid_client_metadata"}
        grant_types_raw = body.get("grant_types") or ["authorization_code"]
        if not isinstance(grant_types_raw, list):
            return 400, {"error": "invalid_client_metadata"}
        grant_types = {str(item) for item in grant_types_raw}
        if not grant_types or not grant_types <= CONFIDENTIAL_GRANT_TYPES:
            return 400, {"error": "invalid_client_metadata"}
        if auth_method == "none" and grant_types - PUBLIC_GRANT_TYPES:
            return 400, {"error": "invalid_client_metadata"}
        secret = None if auth_method == "none" else _b64url(24)
        client_id = f"bh-{_b64url(12)}"
        record = OAuthClient(
            client_id=client_id,
            client_secret=secret,
            redirect_uris=tuple(cleaned),
            auth_method=auth_method,
            grant_types=frozenset(grant_types),
        )
        with self._lock:
            self._expire_locked(time.time())
            if len(self._clients) >= MAX_CLIENTS:
                return 503, {"error": "temporarily_unavailable"}
            self._clients[client_id] = record
        payload: dict[str, Any] = {
            "client_id": client_id,
            "client_id_issued_at": int(record.created_at),
            "redirect_uris": list(record.redirect_uris),
            "token_endpoint_auth_method": auth_method,
            "grant_types": sorted(record.grant_types),
            "response_types": ["code"] if "authorization_code" in record.grant_types else [],
        }
        if secret is not None:
            payload["client_secret"] = secret
        return 201, payload

    def authorize(
        self,
        query: Mapping[str, list[str]],
        *,
        operator_ok: bool,
        origin: str,
        decision: str = "",
        operator_secret: str = "",
    ) -> tuple[int, dict[str, str], dict[str, Any] | str | None]:
        """Return (status, headers, json_body_or_html). 302 has empty body."""

        if not self.enabled:
            return 404, {}, {"ok": False, "error": "oauth_disabled"}

        def first(name: str) -> str:
            values = query.get(name) or []
            return str(values[0] if values else "")

        response_type = first("response_type")
        client_id = first("client_id")
        redirect_uri = first("redirect_uri")
        challenge = first("code_challenge")
        method = first("code_challenge_method") or "S256"
        state = first("state")
        resource = first("resource") or f"{origin.rstrip('/')}/mcp"
        if response_type != "code":
            return 400, {}, {"error": "unsupported_response_type"}
        if method not in PKCE_METHODS or len(challenge) < 43:
            return 400, {}, {"error": "invalid_request", "error_description": "S256 code_challenge required"}
        with self._lock:
            client = self._clients.get(client_id)
        if client is None or "authorization_code" not in client.grant_types:
            return 400, {}, {"error": "invalid_client"}
        if redirect_uri not in client.redirect_uris:
            return 400, {}, {"error": "invalid_request", "error_description": "redirect_uri is not registered"}
        expected_resource = f"{origin.rstrip('/')}/mcp"
        if resource != expected_resource:
            return 400, {}, {"error": "invalid_target"}

        approved = bool(operator_ok) or (
            str(decision) == "allow" and self._operator_secret_ok(operator_secret)
        )
        if str(decision) == "deny" and not approved:
            return self._redirect_error(redirect_uri, state=state, origin=origin, error="access_denied")
        if approved:
            return self._issue_code(
                client_id=client_id,
                redirect_uri=redirect_uri,
                challenge=challenge,
                resource=resource,
                state=state,
                origin=origin,
            )
        error = ""
        if str(decision) == "allow":
            error = "operator token rejected"
        page = consent_page(
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            code_challenge_method=method,
            state=state,
            resource=resource,
            response_type=response_type,
            error=error,
        )
        return (
            200,
            {
                "Cache-Control": "no-store",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
                "Referrer-Policy": "no-referrer",
            },
            page,
        )

    def _operator_secret_ok(self, offered: str) -> bool:
        expected = self.operator_token
        secret = str(offered or "")
        if not expected or not secret:
            return False
        return hmac.compare_digest(secret, expected)

    def _issue_code(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        challenge: str,
        resource: str,
        state: str,
        origin: str,
    ) -> tuple[int, dict[str, str], dict[str, Any] | None]:
        code = _b64url(24)
        now = time.time()
        record = AuthCode(
            code=code,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            resource=resource,
            expires_at=now + CODE_TTL_SECONDS,
        )
        with self._lock:
            self._expire_locked(now)
            if len(self._codes) >= MAX_CODES:
                return 503, {}, {"error": "temporarily_unavailable"}
            self._codes[code] = record
        location = append_query(redirect_uri, code=code, iss=origin.rstrip("/"))
        if state:
            location = append_query(location, state=state)
        return 302, {"Location": location, "Cache-Control": "no-store"}, None

    def _redirect_error(
        self,
        redirect_uri: str,
        *,
        state: str,
        origin: str,
        error: str,
    ) -> tuple[int, dict[str, str], None]:
        location = append_query(redirect_uri, error=error, iss=origin.rstrip("/"))
        if state:
            location = append_query(location, state=state)
        return 302, {"Location": location, "Cache-Control": "no-store"}, None

    def token(
        self,
        fields: Mapping[str, list[str]],
        *,
        origin: str,
        authorization: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        if not self.enabled:
            return 404, {"ok": False, "error": "oauth_disabled"}

        def first(name: str) -> str:
            values = fields.get(name) or []
            return str(values[0] if values else "")

        grant = first("grant_type")
        client_id = first("client_id")
        client_secret = first("client_secret")
        basic = parse_basic_client(authorization)
        if basic is not None:
            client_id = basic[0] or client_id
            client_secret = basic[1]
        resource = first("resource") or f"{origin.rstrip('/')}/mcp"
        expected_resource = f"{origin.rstrip('/')}/mcp"
        if resource != expected_resource:
            return 400, {"error": "invalid_target"}
        if grant == "client_credentials":
            return self._client_credentials(client_id, client_secret, resource)
        if grant == "authorization_code":
            return self._authorization_code(
                client_id=client_id,
                client_secret=client_secret,
                code=first("code"),
                redirect_uri=first("redirect_uri"),
                verifier=first("code_verifier"),
                resource=resource,
            )
        return 400, {"error": "unsupported_grant_type"}

    def _client_credentials(
        self, client_id: str, client_secret: str, resource: str
    ) -> tuple[int, dict[str, Any]]:
        with self._lock:
            client = self._clients.get(client_id)
        if client is None or "client_credentials" not in client.grant_types:
            return 401, {"error": "invalid_client"}
        if not client.client_secret or not hmac.compare_digest(
            str(client_secret or ""), client.client_secret
        ):
            return 401, {"error": "invalid_client"}
        return 200, self._issue(client_id, resource)

    def _authorization_code(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        verifier: str,
        resource: str,
    ) -> tuple[int, dict[str, Any]]:
        now = time.time()
        with self._lock:
            client = self._clients.get(client_id)
            record = self._codes.pop(code, None)
        if client is None or "authorization_code" not in client.grant_types:
            return 401, {"error": "invalid_client"}
        if client.auth_method != "none":
            if not client.client_secret or not hmac.compare_digest(
                str(client_secret or ""), client.client_secret
            ):
                return 401, {"error": "invalid_client"}
        if record is None or record.expires_at <= now:
            return 400, {"error": "invalid_grant"}
        if record.client_id != client_id or record.redirect_uri != redirect_uri:
            return 400, {"error": "invalid_grant"}
        if record.resource != resource:
            return 400, {"error": "invalid_target"}
        if pkce_s256(verifier) != record.code_challenge:
            return 400, {"error": "invalid_grant"}
        return 200, self._issue(client_id, resource, principal=record.principal)

    def _issue(
        self,
        client_id: str,
        resource: str,
        *,
        principal: TokenPrincipal = UNRESTRICTED,
    ) -> dict[str, Any]:
        token = _b64url(32)
        now = time.time()
        record = AccessToken(
            token=token,
            client_id=client_id,
            resource=resource,
            expires_at=now + ACCESS_TTL_SECONDS,
            principal=principal,
        )
        with self._lock:
            self._expire_locked(now)
            if len(self._tokens) >= MAX_TOKENS:
                oldest = min(self._tokens.values(), key=lambda item: item.expires_at)
                self._tokens.pop(oldest.token, None)
            self._tokens[token] = record
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TTL_SECONDS,
            "scope": "mcp",
            "resource": resource,
        }

    def _expire_locked(self, now: float) -> None:
        expired_codes = [key for key, item in self._codes.items() if item.expires_at <= now]
        for key in expired_codes:
            self._codes.pop(key, None)
        expired_tokens = [key for key, item in self._tokens.items() if item.expires_at <= now]
        for key in expired_tokens:
            self._tokens.pop(key, None)


def parse_form(raw: bytes) -> dict[str, list[str]]:
    text = raw.decode("utf-8", errors="replace")
    return parse_qs(text, keep_blank_values=True)


def builtin_oauth_protected_resource_proof() -> dict[str, Any]:
    """Hermetic proof: RFC 9728 discovery plus PKCE token unlocks live MCP/invoke."""

    import tempfile
    import threading
    from pathlib import Path
    from urllib import request as urlrequest
    from urllib.error import HTTPError, URLError
    from urllib.parse import parse_qs as parse_query
    from urllib.parse import urlencode as encode_query
    from urllib.parse import urlsplit as split_url

    from blackhole_agent.capability_compounder import legacy_pipeline_was_used
    from blackhole_agent.capability_service import build_server

    class NoRedirect(urlrequest.HTTPRedirectHandler):
        def http_error_302(self, req, fp, code, msg, headers):  # noqa: ANN001
            raise urlrequest.HTTPError(req.full_url, code, msg, headers, fp)

        http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    reverse_id = "capability.absorbed-text-reverser"
    operator = "operator-oauth-proof"
    probe_text = "oauth-9728-pkce"
    expected_reverse = probe_text[::-1]

    def write_workspace(root: Path) -> None:
        tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
        tool_dir.mkdir(parents=True)
        (tool_dir / "tool.py").write_text(
            "import json, sys\n"
            "state = json.load(sys.stdin)\n"
            "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n",
            encoding="utf-8",
        )
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
        (root / "capabilities" / "ledger.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "",
                    "capabilities": {
                        reverse_id: {
                            "id": reverse_id,
                            "name": "probe text reverser",
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
                    },
                }
            ),
            encoding="utf-8",
        )
        (root / "pyproject.toml").write_text(
            '[project]\nname = "oauth-proof"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

    def request(
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        token: str | None = None,
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        follow: bool = True,
    ) -> tuple[int, object, dict[str, str]]:
        data = None
        extra = dict(headers or {})
        if form is not None:
            data = encode_query(form).encode("utf-8")
            extra.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif payload is not None:
            data = json.dumps(payload).encode("utf-8")
            extra.setdefault("Content-Type", "application/json")
        req = urlrequest.Request(url, data=data, method=method)
        for key, value in extra.items():
            req.add_header(key, value)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        opener = urlrequest.build_opener() if follow else urlrequest.build_opener(NoRedirect())
        try:
            with opener.open(req, timeout=45) as response:
                captured = {key.lower(): value for key, value in response.headers.items()}
                raw = response.read().decode("utf-8")
                try:
                    parsed: object = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = raw
                return int(response.status), parsed, captured
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
            return int(exc.code), parsed, captured
        except (URLError, TimeoutError, OSError) as exc:
            return 0, {"error": f"{type(exc).__name__}: {exc}"}, {}

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="oauth-resource-proof-") as directory:
        root = Path(directory) / "repo"
        write_workspace(root)
        server = build_server(root, host="127.0.0.1", port=0, token=operator)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_address[1]}"
            mcp = f"{origin}/mcp"
            health_status, health, _ = request("GET", f"{origin}/health")
            checks["health"] = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("oauth_protected_resource") is True
            )
            unauth_status, unauth, unauth_headers = request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {}},
                },
            )
            www = str(unauth_headers.get("www-authenticate") or "")
            checks["challenge"] = (
                unauth_status == 401
                and isinstance(unauth, dict)
                and unauth.get("error") == "authorization_required"
                and "resource_metadata=" in www
                and RESOURCE_METADATA_PATH in www
            )
            meta_status, meta, _ = request("GET", f"{origin}{RESOURCE_METADATA_PATH}")
            checks["resource_metadata"] = (
                meta_status == 200
                and isinstance(meta, dict)
                and meta.get("resource") == mcp
                and origin in (meta.get("authorization_servers") or [])
            )
            as_status, as_meta, _ = request("GET", f"{origin}{AUTHORIZATION_SERVER_METADATA_PATH}")
            checks["as_metadata"] = (
                as_status == 200
                and isinstance(as_meta, dict)
                and as_meta.get("issuer") == origin
                and as_meta.get("token_endpoint") == f"{origin}{TOKEN_PATH}"
                and as_meta.get("authorization_endpoint") == f"{origin}{AUTHORIZE_PATH}"
                and as_meta.get("registration_endpoint") == f"{origin}{REGISTER_PATH}"
                and "S256" in (as_meta.get("code_challenge_methods_supported") or [])
            )
            redirect = "http://127.0.0.1:9/cb"
            reg_status, registered, _ = request(
                "POST",
                f"{origin}{REGISTER_PATH}",
                {
                    "redirect_uris": [redirect],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code"],
                    "response_types": ["code"],
                    "client_name": "oauth-proof",
                },
            )
            client_id = str((registered or {}).get("client_id") or "") if isinstance(registered, dict) else ""
            checks["register"] = reg_status == 201 and bool(client_id)
            foreign_status, foreign, _ = request(
                "POST",
                f"{origin}{REGISTER_PATH}",
                {"redirect_uris": ["https://evil.example/cb"]},
            )
            checks["foreign_redirect_refused"] = (
                foreign_status == 400
                and isinstance(foreign, dict)
                and foreign.get("error") == "invalid_redirect_uri"
            )
            verifier = secrets.token_urlsafe(32)
            challenge = pkce_s256(verifier)
            authorize_url = (
                f"{origin}{AUTHORIZE_PATH}?"
                + encode_query(
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
            denied_status, denied_body, denied_headers = request("GET", authorize_url, follow=False)
            denied_page = denied_body if isinstance(denied_body, str) else ""
            checks["authorize_requires_operator"] = (
                denied_status == 200
                and 'id="oauth-consent"' in denied_page
                and "operator_token" in denied_page
                and not str(denied_headers.get("location") or "")
            )
            loc_status, _, loc_headers = request(
                "GET", authorize_url, token=operator, follow=False
            )
            location = str(loc_headers.get("location") or "")
            code = (parse_query(split_url(location).query).get("code") or [""])[0]
            checks["authorize_redirect"] = loc_status == 302 and bool(code) and location.startswith(redirect)
            token_status, token_body, _ = request(
                "POST",
                f"{origin}{TOKEN_PATH}",
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
                str(token_body.get("access_token") or "") if isinstance(token_body, dict) else ""
            )
            checks["token"] = (
                token_status == 200
                and isinstance(token_body, dict)
                and token_body.get("token_type") == "Bearer"
                and bool(access)
            )
            replay_status, replay, _ = request(
                "POST",
                f"{origin}{TOKEN_PATH}",
                form={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect,
                    "client_id": client_id,
                    "code_verifier": verifier,
                    "resource": mcp,
                },
            )
            checks["replay_refused"] = (
                replay_status == 400
                and isinstance(replay, dict)
                and replay.get("error") == "invalid_grant"
            )
            hs_status, handshake, hs_headers = request(
                "POST",
                mcp,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "oauth-proof", "version": "1"},
                    },
                },
                token=access,
            )
            checks["mcp_initialize"] = (
                hs_status == 200
                and isinstance(handshake, dict)
                and bool(hs_headers.get("mcp-session-id"))
                and isinstance(handshake.get("result"), dict)
            )
            invoke_status, invoked, _ = request(
                "POST",
                f"{origin}/invoke",
                {"capability_id": reverse_id, "input": {"raw_text": probe_text}},
                token=access,
            )
            checks["invoke_with_issued_token"] = (
                invoke_status == 200
                and isinstance(invoked, dict)
                and invoked.get("output", {}).get("reversed_text") == expected_reverse
            )
            cc_status, cc_body, _ = request(
                "POST",
                f"{origin}{TOKEN_PATH}",
                form={
                    "grant_type": "client_credentials",
                    "client_id": OPERATOR_CLIENT_ID,
                    "client_secret": operator,
                    "resource": mcp,
                },
            )
            cc_token = str(cc_body.get("access_token") or "") if isinstance(cc_body, dict) else ""
            follow_status, follow, _ = request(
                "POST",
                f"{origin}/invoke",
                {"capability_id": reverse_id, "input": {"raw_text": probe_text}},
                token=cc_token,
            )
            checks["client_credentials"] = (
                cc_status == 200
                and bool(cc_token)
                and follow_status == 200
                and isinstance(follow, dict)
                and follow.get("output", {}).get("reversed_text") == expected_reverse
            )
            options_status, _, options_headers = request(
                "OPTIONS",
                f"{origin}{RESOURCE_METADATA_PATH}",
                headers={"Origin": "http://127.0.0.1:9"},
            )
            checks["loopback_cors"] = (
                options_status == 204
                and options_headers.get("access-control-allow-origin") == "http://127.0.0.1:9"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        closed_root = Path(directory) / "closed"
        write_workspace(closed_root)
        closed = build_server(closed_root, host="127.0.0.1", port=0)
        closed_thread = threading.Thread(target=closed.serve_forever, daemon=True)
        closed_thread.start()
        try:
            closed_origin = f"http://127.0.0.1:{closed.server_address[1]}"
            closed_health_status, closed_health, _ = request("GET", f"{closed_origin}/health")
            closed_meta_status, _, _ = request(
                "GET", f"{closed_origin}{RESOURCE_METADATA_PATH}"
            )
            closed_invoke_status, closed_invoked, _ = request(
                "POST",
                f"{closed_origin}/invoke",
                {"capability_id": reverse_id, "input": {"raw_text": probe_text}},
            )
            checks["fail_closed"] = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("oauth_protected_resource") is False
                and closed_meta_status == 404
                and closed_invoke_status == 200
                and isinstance(closed_invoked, dict)
                and closed_invoked.get("output", {}).get("reversed_text") == expected_reverse
            )
        finally:
            closed.shutdown()
            closed.server_close()
            closed_thread.join(timeout=5)

    return {
        "ok": bool(checks) and all(checks.values()),
        "action": "oauth_protected_resource",
        "checks": checks,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def ensure_oauth_protected_resource_capability(*, repo_path: Any | None = None) -> Any:
    """Register the live-plane OAuth protected-resource capability on the ledger."""

    from pathlib import Path

    from blackhole_agent.capability_compounder import (
        Capability,
        default_ledger_path,
        load_ledger,
        register_capability,
        save_ledger,
        utc_now_iso,
    )

    result = builtin_oauth_protected_resource_proof()
    if not result.get("ok"):
        raise RuntimeError(f"oauth protected resource proof failed: {result}")
    root = Path(repo_path) if repo_path is not None else Path(__file__).resolve().parents[2]
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=OAUTH_PROTECTED_RESOURCE_ID,
        name=OAUTH_PROTECTED_RESOURCE_NAME,
        description=(
            "A token-gated live invocation plane advertises RFC 9728 protected "
            "resource metadata and RFC 8414 authorization-server metadata, "
            "registers loopback public clients, issues PKCE authorization-code "
            "and operator client_credentials access tokens, and those tokens "
            "authorize POST /mcp and POST /invoke. A plane without --token "
            "stays historically open."
        ),
        kind="python",
        entry="blackhole_agent.oauth_protected_resource:builtin_oauth_protected_resource_proof",
        proof_command=(
            "uv run python -c \"from blackhole_agent.oauth_protected_resource import "
            "builtin_oauth_protected_resource_proof; r=builtin_oauth_protected_resource_proof(); "
            "assert r['ok'] and r.get('action')=='oauth_protected_resource' and "
            "all(r['checks'].values()) and not r.get('used_skill_route_discovery')\""
        ),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.ledger-invocation-plane",
        ),
        behavior_paths=(
            "src/blackhole_agent/oauth_protected_resource.py",
            "src/blackhole_agent/capability_service.py",
            "src/blackhole_agent/kernel_leftover.py",
        ),
        capability_delta=(
            "Spec-compliant MCP hosts can discover RFC 9728 resource metadata "
            "on the live plane, complete OAuth 2.1 PKCE, and invoke tools with "
            "the issued bearer; an open plane still serves without OAuth."
        ),
        tags=("invocation", "oauth", "mcp", "rfc9728", "authorization"),
        source_mission_id="20261011T142152Z-498cc9a6",
        source_milestone=1,
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability


def builtin_oauth_authorize_consent_proof() -> dict[str, Any]:
    """Hermetic proof: browser consent POST issues a PKCE code without a header."""

    import tempfile
    import threading
    from pathlib import Path
    from urllib import request as urlrequest
    from urllib.error import HTTPError, URLError
    from urllib.parse import parse_qs as parse_query
    from urllib.parse import urlencode as encode_query
    from urllib.parse import urlsplit as split_url

    from blackhole_agent.capability_compounder import legacy_pipeline_was_used
    from blackhole_agent.capability_service import build_server

    class NoRedirect(urlrequest.HTTPRedirectHandler):
        def http_error_302(self, req, fp, code, msg, headers):  # noqa: ANN001
            raise urlrequest.HTTPError(req.full_url, code, msg, headers, fp)

        http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    reverse_id = "capability.absorbed-text-reverser"
    operator = "operator-oauth-consent-proof"
    probe_text = "oauth-consent-pkce"
    expected_reverse = probe_text[::-1]

    def write_workspace(root: Path) -> None:
        tool_dir = root / "capabilities" / "absorbed" / "text-reverser"
        tool_dir.mkdir(parents=True)
        (tool_dir / "tool.py").write_text(
            "import json, sys\n"
            "state = json.load(sys.stdin)\n"
            "print(json.dumps({'reversed_text': state['raw_text'][::-1]}))\n",
            encoding="utf-8",
        )
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
        (root / "capabilities" / "ledger.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "updated_at": "",
                    "capabilities": {
                        reverse_id: {
                            "id": reverse_id,
                            "name": "probe text reverser",
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
                    },
                }
            ),
            encoding="utf-8",
        )
        (root / "pyproject.toml").write_text(
            '[project]\nname = "oauth-consent-proof"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )

    def request(
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        token: str | None = None,
        form: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        follow: bool = True,
    ) -> tuple[int, object, dict[str, str]]:
        data = None
        extra = dict(headers or {})
        if form is not None:
            data = encode_query(form).encode("utf-8")
            extra.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif payload is not None:
            data = json.dumps(payload).encode("utf-8")
            extra.setdefault("Content-Type", "application/json")
        req = urlrequest.Request(url, data=data, method=method)
        for key, value in extra.items():
            req.add_header(key, value)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        opener = urlrequest.build_opener() if follow else urlrequest.build_opener(NoRedirect())
        try:
            with opener.open(req, timeout=45) as response:
                captured = {key.lower(): value for key, value in response.headers.items()}
                raw = response.read().decode("utf-8")
                try:
                    parsed: object = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = raw
                return int(response.status), parsed, captured
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
            return int(exc.code), parsed, captured
        except (URLError, TimeoutError, OSError) as exc:
            return 0, {"error": f"{type(exc).__name__}: {exc}"}, {}

    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="oauth-consent-proof-") as directory:
        root = Path(directory) / "repo"
        write_workspace(root)
        server = build_server(root, host="127.0.0.1", port=0, token=operator)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_address[1]}"
            mcp = f"{origin}/mcp"
            health_status, health, _ = request("GET", f"{origin}/health")
            checks["health"] = (
                health_status == 200
                and isinstance(health, dict)
                and health.get("oauth_authorize_consent") is True
            )
            redirect = "http://127.0.0.1:9/cb"
            reg_status, registered, _ = request(
                "POST",
                f"{origin}{REGISTER_PATH}",
                {
                    "redirect_uris": [redirect],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code"],
                    "response_types": ["code"],
                    "client_name": "oauth-consent-proof",
                },
            )
            client_id = str((registered or {}).get("client_id") or "") if isinstance(registered, dict) else ""
            checks["register"] = reg_status == 201 and bool(client_id)
            verifier = secrets.token_urlsafe(32)
            challenge = pkce_s256(verifier)
            authorize_query = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "st",
                "resource": mcp,
            }
            authorize_url = f"{origin}{AUTHORIZE_PATH}?" + encode_query(authorize_query)
            page_status, page_body, page_headers = request("GET", authorize_url, follow=False)
            page_text = page_body if isinstance(page_body, str) else ""
            checks["consent_page"] = (
                page_status == 200
                and "text/html" in str(page_headers.get("content-type") or "")
                and 'id="oauth-consent"' in page_text
                and 'name="operator_token"' in page_text
                and 'name="decision"' in page_text
                and html.escape(client_id) in page_text
                and not str(page_headers.get("location") or "")
            )
            wrong_status, wrong_body, wrong_headers = request(
                "POST",
                f"{origin}{AUTHORIZE_PATH}",
                form={**authorize_query, "operator_token": "wrong-operator-token", "decision": "allow"},
                follow=False,
            )
            wrong_text = wrong_body if isinstance(wrong_body, str) else ""
            checks["wrong_token_refused"] = (
                wrong_status == 200
                and 'id="oauth-consent"' in wrong_text
                and "operator token rejected" in wrong_text
                and not str(wrong_headers.get("location") or "")
            )
            deny_status, _, deny_headers = request(
                "POST",
                f"{origin}{AUTHORIZE_PATH}",
                form={**authorize_query, "decision": "deny"},
                follow=False,
            )
            deny_location = str(deny_headers.get("location") or "")
            deny_query = parse_query(split_url(deny_location).query)
            checks["deny_redirects"] = (
                deny_status == 302
                and deny_location.startswith(redirect)
                and (deny_query.get("error") or [""])[0] == "access_denied"
                and not (deny_query.get("code") or [""])[0]
            )
            allow_status, _, allow_headers = request(
                "POST",
                f"{origin}{AUTHORIZE_PATH}",
                form={**authorize_query, "operator_token": operator, "decision": "allow"},
                follow=False,
            )
            allow_location = str(allow_headers.get("location") or "")
            code = (parse_query(split_url(allow_location).query).get("code") or [""])[0]
            checks["consent_allow_redirect"] = (
                allow_status == 302
                and bool(code)
                and allow_location.startswith(redirect)
            )
            token_status, token_body, _ = request(
                "POST",
                f"{origin}{TOKEN_PATH}",
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
                str(token_body.get("access_token") or "") if isinstance(token_body, dict) else ""
            )
            invoke_status, invoked, _ = request(
                "POST",
                f"{origin}/invoke",
                {"capability_id": reverse_id, "input": {"raw_text": probe_text}},
                token=access,
            )
            checks["consent_issued_token"] = (
                token_status == 200
                and bool(access)
                and invoke_status == 200
                and isinstance(invoked, dict)
                and invoked.get("output", {}).get("reversed_text") == expected_reverse
            )
            loc_status, _, loc_headers = request(
                "GET", authorize_url, token=operator, follow=False
            )
            bearer_location = str(loc_headers.get("location") or "")
            bearer_code = (parse_query(split_url(bearer_location).query).get("code") or [""])[0]
            checks["bearer_still_auto_approves"] = (
                loc_status == 302 and bool(bearer_code) and bearer_location.startswith(redirect)
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        closed_root = Path(directory) / "closed"
        write_workspace(closed_root)
        closed = build_server(closed_root, host="127.0.0.1", port=0)
        closed_thread = threading.Thread(target=closed.serve_forever, daemon=True)
        closed_thread.start()
        try:
            closed_origin = f"http://127.0.0.1:{closed.server_address[1]}"
            closed_health_status, closed_health, _ = request("GET", f"{closed_origin}/health")
            closed_auth_status, _, _ = request("GET", f"{closed_origin}{AUTHORIZE_PATH}")
            closed_invoke_status, closed_invoked, _ = request(
                "POST",
                f"{closed_origin}/invoke",
                {"capability_id": reverse_id, "input": {"raw_text": probe_text}},
            )
            checks["fail_closed"] = (
                closed_health_status == 200
                and isinstance(closed_health, dict)
                and closed_health.get("oauth_authorize_consent") is False
                and closed_auth_status == 404
                and closed_invoke_status == 200
                and isinstance(closed_invoked, dict)
                and closed_invoked.get("output", {}).get("reversed_text") == expected_reverse
            )
        finally:
            closed.shutdown()
            closed.server_close()
            closed_thread.join(timeout=5)

    return {
        "ok": bool(checks) and all(checks.values()),
        "action": "oauth_authorize_consent",
        "checks": checks,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def ensure_oauth_authorize_consent_capability(*, repo_path: Any | None = None) -> Any:
    """Register the browser authorize-consent capability on the ledger."""

    from pathlib import Path

    from blackhole_agent.capability_compounder import (
        Capability,
        default_ledger_path,
        load_ledger,
        register_capability,
        save_ledger,
        utc_now_iso,
    )

    result = builtin_oauth_authorize_consent_proof()
    if not result.get("ok"):
        raise RuntimeError(f"oauth authorize consent proof failed: {result}")
    root = Path(repo_path) if repo_path is not None else Path(__file__).resolve().parents[2]
    path = default_ledger_path(root)
    ledger = load_ledger(path)
    capability = Capability(
        id=OAUTH_AUTHORIZE_CONSENT_ID,
        name=OAUTH_AUTHORIZE_CONSENT_NAME,
        description=(
            "GET /oauth/authorize without an operator Authorization header "
            "serves an HTML consent page. POST /oauth/authorize with "
            "decision=allow and the operator token in the form body issues the "
            "same one-time PKCE code as an operator bearer auto-approve. Deny "
            "redirects with access_denied. A plane without --token stays "
            "historically open."
        ),
        kind="python",
        entry="blackhole_agent.oauth_protected_resource:builtin_oauth_authorize_consent_proof",
        proof_command=(
            "uv run python -c \"from blackhole_agent.oauth_protected_resource import "
            "builtin_oauth_authorize_consent_proof; r=builtin_oauth_authorize_consent_proof(); "
            "assert r['ok'] and r.get('action')=='oauth_authorize_consent' and "
            "all(r['checks'].values()) and not r.get('used_skill_route_discovery')\""
        ),
        dependencies=(
            "repo.import-health",
            "capability.ledger-inventory",
            "capability.ledger-invocation-plane",
            "capability.oauth-protected-resource",
        ),
        behavior_paths=(
            "src/blackhole_agent/oauth_protected_resource.py",
            "src/blackhole_agent/capability_service.py",
            "src/blackhole_agent/kernel_leftover.py",
        ),
        capability_delta=(
            "A browser can finish GET /oauth/authorize without an operator "
            "Authorization header: the endpoint serves a consent page and a "
            "form POST with the operator token issues the PKCE code."
        ),
        tags=("invocation", "oauth", "consent", "browser", "authorization"),
        source_mission_id="20261011T145736Z-5931c0a5",
        source_milestone=1,
        last_proved_at=utc_now_iso(),
        last_proof_exit_code=0,
    )
    register_capability(ledger, capability, replace=True)
    save_ledger(path, ledger)
    return capability
