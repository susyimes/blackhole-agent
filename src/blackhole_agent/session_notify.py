"""HMAC-signed outbound callbacks for terminal goal-session outcomes.

Durable sessions persist status on disk and stream it to connected SSE
clients, but an operator who creates a session and disconnects has no
delivery path: the terminal result sits on disk until someone polls.
This module posts a GitHub-style HMAC-signed JSON payload to an operator
callback URL when a session reaches a terminal status.

Fail-closed targeting: only loopback http(s) URLs are accepted so a
stolen bearer token cannot turn ``POST /sessions`` into an SSRF trampoline.
Redirects are not followed. The shared secret never appears in API
responses. Deliveries are at-least-once with bounded retries on 5xx and
transport failures.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
import urllib.error
import urllib.request
from typing import Any, Mapping
from urllib.parse import urlparse

SIGNATURE_HEADER = "X-Hub-Signature-256"
NOTIFY_EVENT = "session.terminal"
NOTIFY_USER_AGENT = "blackhole-session-notify/1"
MIN_SECRET_CHARS = 8
MAX_SECRET_CHARS = 128
ALLOWED_SCHEMES = frozenset({"http", "https"})
RETRY_DELAYS_SECONDS = (0.05, 0.15, 0.4)
DELIVERY_TIMEOUT_SECONDS = 5.0


class NotifyTargetError(ValueError):
    """Callback URL or secret is not acceptable."""


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sign_notify_body(secret: str, body: bytes) -> str:
    """Return a GitHub-style ``sha256=`` hex HMAC over the raw POST body."""

    digest = hmac.new(str(secret).encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_notify_signature(secret: str, body: bytes, header: str) -> bool:
    """True when ``header`` is the HMAC of ``body`` under ``secret``."""

    expected = sign_notify_body(secret, body)
    provided = str(header or "")
    try:
        return bool(provided) and hmac.compare_digest(expected, provided)
    except (TypeError, ValueError):
        return False


def session_notify_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Signed-body fields: outcome identity without the shared secret."""

    return {
        "event": NOTIFY_EVENT,
        "error": record.get("error"),
        "goal": record.get("goal"),
        "outcome": record.get("outcome"),
        "plan_digest": record.get("plan_digest"),
        "session_digest": record.get("session_digest"),
        "session_id": record.get("session_id"),
        "status": record.get("status"),
    }


def public_session_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """API copy of a session: the shared secret is presence-only."""

    public = dict(record)
    if "notify_secret" in public:
        public.pop("notify_secret", None)
        public["notify_secret_present"] = True
    return public


def _host_is_loopback(host: str) -> bool:
    hostname = str(host or "").strip()
    if not hostname:
        return False
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            return False
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        if not address.is_loopback:
            return False
    return True


def validate_notify_url(url: Any) -> str:
    """Return a normalized loopback http(s) URL, or raise ``NotifyTargetError``."""

    if not isinstance(url, str) or not url.strip():
        raise NotifyTargetError("notify_url must be a non-empty http(s) URL")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise NotifyTargetError("notify_url must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise NotifyTargetError("notify_url must not contain userinfo")
    host = parsed.hostname
    if not host:
        raise NotifyTargetError("notify_url must include a hostname")
    if parsed.query or parsed.fragment:
        raise NotifyTargetError("notify_url must not include a query or fragment")
    if not _host_is_loopback(host):
        raise NotifyTargetError("notify_url host must resolve only to loopback")
    return url.strip()


def validate_notify_secret(secret: Any) -> str:
    if not isinstance(secret, str):
        raise NotifyTargetError("notify_secret must be a string")
    if len(secret) < MIN_SECRET_CHARS or len(secret) > MAX_SECRET_CHARS:
        raise NotifyTargetError(
            f"notify_secret must be {MIN_SECRET_CHARS}–{MAX_SECRET_CHARS} characters"
        )
    if any(ord(char) < 32 or ord(char) == 127 for char in secret):
        raise NotifyTargetError("notify_secret must not contain control characters")
    return secret


def normalize_notify_spec(notify_url: Any, notify_secret: Any) -> tuple[str, str] | tuple[None, None]:
    """Validate the pair. Both absent is fine; one without the other is not."""

    url_set = notify_url is not None and str(notify_url).strip() != ""
    secret_set = notify_secret is not None and str(notify_secret) != ""
    if not url_set and not secret_set:
        return None, None
    if url_set != secret_set:
        raise NotifyTargetError("notify_url and notify_secret must be supplied together")
    return validate_notify_url(notify_url), validate_notify_secret(notify_secret)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )


def deliver_session_notify(
    url: str,
    secret: str,
    record: Mapping[str, Any],
    *,
    timeout: float = DELIVERY_TIMEOUT_SECONDS,
) -> tuple[int, str]:
    """POST one signed payload. Returns ``(status, error)``; status 0 on transport failure.

    Re-checks loopback resolution immediately before connecting so a DNS
    rebinding between admission and delivery cannot reach a non-loopback host.
    """

    try:
        target = validate_notify_url(url)
    except NotifyTargetError as exc:
        return 0, str(exc)
    parsed = urlparse(target)
    if not parsed.hostname or not _host_is_loopback(parsed.hostname):
        return 0, "notify_url host must resolve only to loopback"
    body = _canonical(session_notify_payload(record)).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
        "User-Agent": NOTIFY_USER_AGENT,
        SIGNATURE_HEADER: sign_notify_body(secret, body),
    }
    request = urllib.request.Request(target, data=body, headers=headers, method="POST")
    try:
        with _opener().open(request, timeout=timeout) as response:
            status = int(response.status)
            response.read()
    except urllib.error.HTTPError as error:
        try:
            error.read()
        except OSError:
            pass
        return int(error.code), f"http_error:{error.code}"
    except urllib.error.URLError as error:
        return 0, f"unreachable:{error.reason}"
    except (TimeoutError, OSError) as error:
        return 0, f"{type(error).__name__}:{error}"
    if 200 <= status < 300:
        return status, ""
    return status, f"http_status:{status}"


def should_retry_notify(status: int, error: str) -> bool:
    if status == 429 or status >= 500 or status == 0:
        return True
    return False
