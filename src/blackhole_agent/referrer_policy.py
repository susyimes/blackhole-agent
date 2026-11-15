"""Determine the Referer value of one request.

A Fetch redirect rewrites the method and drops Authorization. It does not
decide the Referer header. This module is that decision, following the
Referrer Policy editor's draft: strip credentials and the fragment, omit the
header on a potentially-trustworthy to non-trustworthy downgrade (including
loopback and ``wss``), keep a cross-origin path only for the policies that
say so, and shorten a stripped referrer longer than 4096 characters to its
origin.

``parse_referrer_policy`` returns the last recognized token. An unrecognized
token is skipped. Comparison is ASCII case-insensitive, so a header can ship
``origin`` and then ``Unsafe-URL`` and the later token wins.
"""

from __future__ import annotations

import ipaddress
from typing import Sequence

from blackhole_agent.whatwg_url import URLParseError, parse_href

_POLICIES = frozenset(
    {
        "no-referrer",
        "no-referrer-when-downgrade",
        "same-origin",
        "origin",
        "strict-origin",
        "origin-when-cross-origin",
        "strict-origin-when-cross-origin",
        "unsafe-url",
    }
)
_LOCAL_SCHEMES = frozenset({"about", "blob", "data"})
_LOOPBACK = ipaddress.ip_network("127.0.0.0/8")
_IPV6_LOOPBACK = ipaddress.ip_address("::1")
_REFERRER_CAP = 4096
DEFAULT_REFERRER_POLICY = "strict-origin-when-cross-origin"


class ReferrerPolicyError(ValueError):
    """The policy or one of the URLs cannot be used to determine a referrer."""


def parse_referrer_policy(header: str | Sequence[str]) -> str:
    """Return the last recognized Referrer-Policy token, or ``""``.

    ``header`` is one field value or several field values in order. Tokens
    are split on commas. An empty string means the header did not set a policy.
    """

    fields = [header] if isinstance(header, str) else list(header)
    chosen = ""
    for field in fields:
        if not isinstance(field, str):
            raise ReferrerPolicyError("a Referrer-Policy value must be a string")
        for raw in field.split(","):
            token = _ascii_lower(raw.strip(" \t"))
            if token in _POLICIES:
                chosen = token
    return chosen


def referrer_policy_after_redirect(
    policy: str,
    response_headers: Sequence[tuple[str, str]],
) -> str:
    """Apply a redirect response's Referrer-Policy header to the request policy.

    A non-empty parsed header replaces the request policy. An absent header,
    or a header whose tokens are all unrecognized, leaves the request policy
    in place. This is the step a redirect follow does not perform.
    """

    current = _policy(policy)
    values = [
        value
        for name, value in response_headers
        if isinstance(name, str) and isinstance(value, str) and name.lower() == "referrer-policy"
    ]
    if not values:
        return current
    updated = parse_referrer_policy(values)
    return updated or current


def referrer_value(policy: str, source: str, target: str) -> str:
    """Return the Referer header value, or ``""`` when the header is omitted."""

    selected = _policy(policy)
    source_parts = _prepare(source, role="source")
    if source_parts is None:
        return ""
    target_parts = _prepare(target, role="target")
    full = _serialize(source_parts, origin_only=False)
    origin = _serialize(source_parts, origin_only=True)
    if len(full) > _REFERRER_CAP:
        full = origin
    same = target_parts is not None and _same_origin(source_parts, target_parts)
    downgrade = _trustworthy(source_parts) and not _trustworthy(target_parts)
    if selected == "no-referrer":
        return ""
    if selected == "origin":
        return origin
    if selected == "unsafe-url":
        return full
    if selected == "strict-origin":
        return "" if downgrade else origin
    if selected == "strict-origin-when-cross-origin":
        if same:
            return full
        return "" if downgrade else origin
    if selected == "same-origin":
        return full if same else ""
    if selected == "origin-when-cross-origin":
        return full if same else origin
    if selected == "no-referrer-when-downgrade":
        return "" if downgrade else full
    raise ReferrerPolicyError(f"unhandled referrer policy {selected!r}")


def _policy(value: str) -> str:
    if not isinstance(value, str):
        raise ReferrerPolicyError("a referrer policy must be a string")
    token = _ascii_lower(value.strip(" \t"))
    if token not in _POLICIES:
        raise ReferrerPolicyError(f"unknown referrer policy {value!r}")
    return token


def _ascii_lower(value: str) -> str:
    return "".join(char.lower() if "A" <= char <= "Z" else char for char in value)


def _prepare(url: str, *, role: str) -> dict[str, str | None] | None:
    if not isinstance(url, str):
        raise ReferrerPolicyError(f"{role} URL must be a string")
    scheme = _leading_scheme(url)
    if scheme in _LOCAL_SCHEMES:
        return None
    try:
        canonical = parse_href(url)
    except URLParseError as exc:
        raise ReferrerPolicyError(f"{role} URL is not usable: {exc}") from exc
    return _components(canonical)


def _leading_scheme(text: str) -> str:
    cleaned = "".join(char for char in text if char not in "\t\n\r")
    while cleaned and (cleaned[0] == " " or ord(cleaned[0]) < 0x20):
        cleaned = cleaned[1:]
    token: list[str] = []
    for char in cleaned:
        if char == ":":
            break
        if not (char.isascii() and (char.isalnum() or char in "+-.")):
            return ""
        token.append(char)
    else:
        return ""
    if not token or not token[0].isalpha():
        return ""
    return _ascii_lower("".join(token))


def _components(serialized: str) -> dict[str, str | None]:
    bare = serialized.split("#", 1)[0]
    query: str | None = None
    if "?" in bare:
        bare, query = bare.split("?", 1)
    scheme, rest = bare.split(":", 1)
    if not rest.startswith("//"):
        raise ReferrerPolicyError(f"URL {serialized!r} has no authority")
    rest = rest[2:]
    slash = rest.find("/")
    if slash == -1:
        authority, path = rest, ""
    else:
        authority, path = rest[:slash], rest[slash:]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    return {"scheme": scheme, "authority": authority, "path": path, "query": query}


def _serialize(parts: dict[str, str | None], *, origin_only: bool) -> str:
    base = f"{parts['scheme']}://{parts['authority']}"
    if origin_only:
        return base + "/"
    path = parts["path"] or ""
    if not path:
        path = "/"
    rendered = base + path
    if parts["query"] is not None:
        rendered += "?" + parts["query"]
    return rendered


def _same_origin(left: dict[str, str | None], right: dict[str, str | None]) -> bool:
    if left["scheme"] == "file" or right["scheme"] == "file":
        return False
    return left["scheme"] == right["scheme"] and left["authority"] == right["authority"]


def _trustworthy(parts: dict[str, str | None] | None) -> bool:
    if parts is None:
        return False
    scheme = parts["scheme"]
    if scheme in {"https", "wss", "file"}:
        return True
    if scheme not in {"http", "ws"}:
        return False
    host = _host(str(parts["authority"]))
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return address in _LOOPBACK
    return address == _IPV6_LOOPBACK


def _host(authority: str) -> str:
    if authority.startswith("["):
        end = authority.find("]")
        if end == -1:
            return authority
        return authority[1:end]
    if ":" in authority:
        return authority.rsplit(":", 1)[0]
    return authority
