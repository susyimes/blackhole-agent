"""Decide cross-origin isolation and whether a navigation severs its opener.

HTML obtains an opener policy from ``Cross-Origin-Opener-Policy`` and an
embedder policy from ``Cross-Origin-Embedder-Policy``. Both are structured
field tokens. A non-secure context ignores them and stays ``unsafe-none``.
The token ``same-origin`` becomes ``same-origin-plus-COEP`` only when the
enforcing embedder policy is ``require-corp`` or ``credentialless``. That
value is what places a browsing-context group into cross-origin isolation.
A report-only header does not change the enforcing value, and
``same-origin-allow-popups`` does not become isolated just because an
embedder policy is present.

A popup's first navigation compares the new response with the opener policy
inherited by the initial ``about:blank``. ``noopener-allow-popups`` on the
new document always severs the opener. ``same-origin-allow-popups`` or
``noopener-allow-popups`` keeps a new document whose policy is
``unsafe-none``. Otherwise the policies match only when both are
``unsafe-none``, or they are the same value and the same origin.
``same-origin-plus-COEP`` does not match ``same-origin``. A later top-level
navigation uses that match and does not keep the popup exception.

A no-cors embed uses Fetch's cross-origin resource policy internal check.
A missing ``Cross-Origin-Resource-Policy`` becomes ``same-origin`` under
``require-corp``, and under ``credentialless`` only when the request
includes credentials or the check is for a navigation. ``same-site`` is
schemeless, and an ``https`` response still requires an ``https`` initiator.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from urllib.parse import urlsplit

from blackhole_agent.http_cookie import same_site
from blackhole_agent.structured_fields import StructuredFieldError, parse_structured_field

_OPENER_EXACT = frozenset({"same-origin-allow-popups", "noopener-allow-popups"})
_ISOLATING_COEP = frozenset({"require-corp", "credentialless"})
_CORP_VALUES = frozenset({"same-origin", "same-site", "cross-origin"})
_HTTP_FAMILY = frozenset({"http", "https", "ws", "wss"})
_DEFAULT_PORT = {"http": 80, "https": 443, "ws": 80, "wss": 443}
_LOOPBACK_V4 = ipaddress.ip_network("127.0.0.0/8")
_LOOPBACK_V6 = ipaddress.ip_network("::1/128")
_COOP = "cross-origin-opener-policy"
_COEP = "cross-origin-embedder-policy"
_CORP = "cross-origin-resource-policy"


class CrossOriginIsolationError(ValueError):
    """A URL or header cannot be used for an isolation decision."""


class _Origin:
    __slots__ = ("scheme", "host", "port")

    def __init__(self, scheme: str, host: str, port: int) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port

    def same_as(self, other: _Origin) -> bool:
        return self.scheme == other.scheme and self.host == other.host and self.port == other.port


def opener_policy(document_url: str, headers: Mapping[str, str] | None = None) -> str:
    """Return the enforcing opener policy value for one document response.

    ``same-origin-plus-COEP`` means this document opts into cross-origin
    isolation. Every other value does not.
    """

    origin = _origin(document_url)
    if not _secure(origin):
        return "unsafe-none"
    token = _token(headers, _COOP)
    if token == "same-origin":
        embedder = _token(headers, _COEP)
        if embedder in _ISOLATING_COEP:
            return "same-origin-plus-COEP"
        return "same-origin"
    if token in _OPENER_EXACT:
        return token
    return "unsafe-none"


def popup_switch(
    opener_url: str,
    opener_headers: Mapping[str, str] | None,
    popup_url: str,
    popup_headers: Mapping[str, str] | None,
) -> bool:
    """Whether a popup's first navigation severs ``window.opener``.

    The new browsing context's initial ``about:blank`` inherited the opener
    document's policy and origin. True means the popup needs a new browsing
    context group.
    """

    return _popup_needs_switch(
        opener_policy(opener_url, opener_headers),
        _origin(opener_url),
        opener_policy(popup_url, popup_headers),
        _origin(popup_url),
    )


def navigation_switch(
    current_url: str,
    current_headers: Mapping[str, str] | None,
    next_url: str,
    next_headers: Mapping[str, str] | None,
) -> bool:
    """Whether a later top-level navigation needs a new browsing context group.

    This is not a popup. ``same-origin-allow-popups`` does not keep an
    ``unsafe-none`` cross-origin result.
    """

    current = opener_policy(current_url, current_headers)
    nxt = opener_policy(next_url, next_headers)
    return not _policies_match(current, _origin(current_url), nxt, _origin(next_url))


def embed_allowed(
    embedder_url: str,
    embedder_headers: Mapping[str, str] | None,
    resource_url: str,
    resource_headers: Mapping[str, str] | None,
    *,
    credentials: bool = False,
    for_navigation: bool = False,
) -> bool:
    """Whether a no-cors response may be used by an embedder.

    ``credentials`` is the response's request-includes-credentials flag.
    ``for_navigation`` is true only for a nested navigation, which is the
    Fetch check's ``forNavigation`` argument.
    """

    if not isinstance(credentials, bool) or not isinstance(for_navigation, bool):
        raise CrossOriginIsolationError("credentials and for_navigation must be booleans")
    embedder = _origin(embedder_url)
    resource = _origin(resource_url)
    coep = "unsafe-none"
    if _secure(embedder):
        token = _token(embedder_headers, _COEP)
        if token in _ISOLATING_COEP:
            coep = token
    policy = _corp(resource_headers)
    if policy is None:
        if coep == "require-corp" or (coep == "credentialless" and (credentials or for_navigation)):
            policy = "same-origin"
    if policy is None or policy == "cross-origin":
        return True
    if policy == "same-origin":
        return embedder.same_as(resource)
    if policy == "same-site":
        if not _schemeless_same_site(embedder, resource):
            return False
        return embedder.scheme == "https" or resource.scheme != "https"
    return True


def _popup_needs_switch(active: str, active_origin: _Origin, response: str, response_origin: _Origin) -> bool:
    if response == "noopener-allow-popups":
        return True
    if active in {"same-origin-allow-popups", "noopener-allow-popups"} and response == "unsafe-none":
        return False
    if _policies_match(active, active_origin, response, response_origin):
        return False
    return True


def _policies_match(document: str, document_origin: _Origin, response: str, response_origin: _Origin) -> bool:
    if document == "unsafe-none" and response == "unsafe-none":
        return True
    if document == "unsafe-none" or response == "unsafe-none":
        return False
    return document == response and document_origin.same_as(response_origin)


def _origin(url: str) -> _Origin:
    if not isinstance(url, str) or not url:
        raise CrossOriginIsolationError("URL must be a non-empty string")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").rstrip(".").lower()
    if scheme not in _HTTP_FAMILY or not host or parts.hostname is None:
        raise CrossOriginIsolationError("URL must be an absolute http(s) or ws(s) URL")
    port = _DEFAULT_PORT[scheme] if parts.port is None else parts.port
    return _Origin(scheme, host, port)


def _secure(origin: _Origin) -> bool:
    if origin.scheme in {"https", "wss"}:
        return True
    if origin.scheme not in {"http", "ws"}:
        return False
    try:
        address = ipaddress.ip_address(origin.host)
    except ValueError:
        address = None
    if isinstance(address, ipaddress.IPv4Address) and address in _LOOPBACK_V4:
        return True
    if isinstance(address, ipaddress.IPv6Address) and address in _LOOPBACK_V6:
        return True
    return origin.host == "localhost" or origin.host.endswith(".localhost")


def _lines(headers: Mapping[str, str] | None, name: str) -> list[str]:
    if headers is None:
        return []
    if not isinstance(headers, Mapping):
        raise CrossOriginIsolationError("headers must be a mapping")
    found: list[str] = []
    for key, value in headers.items():
        if not isinstance(key, str) or key.lower() != name:
            continue
        if not isinstance(value, str):
            raise CrossOriginIsolationError("header values must be strings")
        found.append(value)
    return found


def _token(headers: Mapping[str, str] | None, name: str) -> str | None:
    lines = _lines(headers, name)
    if not lines:
        return None
    try:
        parsed = parse_structured_field(lines, "item")
    except StructuredFieldError:
        return None
    if not isinstance(parsed, list) or len(parsed) != 2:
        return None
    bare = parsed[0]
    if not isinstance(bare, dict) or bare.get("__type") != "token" or not isinstance(bare.get("value"), str):
        return None
    return str(bare["value"])


def _corp(headers: Mapping[str, str] | None) -> str | None:
    lines = _lines(headers, _CORP)
    if len(lines) != 1:
        return None
    value = lines[0].strip(" \t")
    if value in _CORP_VALUES:
        return value
    return None


def _schemeless_same_site(left: _Origin, right: _Origin) -> bool:
    try:
        return same_site(_https_twin(left), _https_twin(right))
    except ValueError:
        return False


def _https_twin(origin: _Origin) -> str:
    host = f"[{origin.host}]" if ":" in origin.host else origin.host
    return f"https://{host}/"
