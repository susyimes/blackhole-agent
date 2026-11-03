"""Store Set-Cookie headers and build a Cookie request header.

Python 3.13 ``http.cookiejar`` still follows the original cookie rules that
let a ``Max-Age=0`` replacement leave the previous cookie in place, accept a
``__Host-`` or ``__Secure-`` name that does not meet its prefix, and accept a
``Secure`` cookie from a plain ``http`` origin. This jar follows the storage
and retrieval rules in draft-ietf-httpbis-rfc6265bis-22: eviction on expiry,
cookie-name prefixes, and secure-origin checks. It does not speak a handshake.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Sequence
from urllib.parse import urlsplit

_SECURE_SCHEMES = frozenset({"https", "wss"})
_TRUSTED_HTTP_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_TOKEN = frozenset(
    "!#$%&'*+-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ^_`abcdefghijklmnopqrstuvwxyz|~"
)


@dataclass
class _Stored:
    name: str
    value: str
    domain: str
    path: str
    host_only: bool
    secure: bool
    expires: datetime | None
    created: int


@dataclass(frozen=True)
class _Parsed:
    name: str
    value: str
    domain: str | None
    path: str | None
    explicit_path: bool
    secure: bool
    expires: datetime | None
    persistent: bool


class CookieJar:
    """In-memory cookie store keyed by name, domain, host-only flag, and path."""

    def __init__(self) -> None:
        self._cookies: dict[tuple[str, str, bool, str], _Stored] = {}
        self._created = 0

    def store(self, set_cookie: str, url: str, now: datetime) -> str:
        """Apply one Set-Cookie line received from ``url`` at ``now``.

        Returns ``stored``, ``evicted``, or ``ignored``.
        """

        moment = _aware(now)
        target = _location(url)
        parsed = _parse_set_cookie(set_cookie, moment)
        if parsed is None or not _name_ok(parsed.name) or not _value_ok(parsed.value):
            return "ignored"
        if parsed.domain is None:
            domain = target.host
            host_only = True
        else:
            domain = parsed.domain
            if not _domain_acceptable(target.host, domain):
                return "ignored"
            host_only = False
        path = parsed.path if parsed.explicit_path and parsed.path else _default_path(target.path)
        secure = parsed.secure
        if secure and not target.secure:
            return "ignored"
        lowered = parsed.name.lower()
        if lowered.startswith("__secure-") and not secure:
            return "ignored"
        if lowered.startswith("__host-") and not (
            secure and host_only and parsed.explicit_path and path == "/"
        ):
            return "ignored"
        key = (parsed.name, domain, host_only, path)
        existing = self._cookies.get(key)
        if existing is not None and existing.secure and not target.secure:
            return "ignored"
        if parsed.persistent and parsed.expires is not None and parsed.expires <= moment:
            if existing is not None:
                del self._cookies[key]
                return "evicted"
            return "ignored"
        created = existing.created if existing is not None else self._next_created()
        self._cookies[key] = _Stored(
            name=parsed.name,
            value=parsed.value,
            domain=domain,
            path=path,
            host_only=host_only,
            secure=secure,
            expires=parsed.expires if parsed.persistent else None,
            created=created,
        )
        return "stored"

    def header(self, url: str, now: datetime) -> str:
        """Return the Cookie header value for ``url`` at ``now``, or ``""``."""

        moment = _aware(now)
        target = _location(url)
        chosen: list[_Stored] = []
        expired: list[tuple[str, str, bool, str]] = []
        for key, cookie in self._cookies.items():
            if cookie.expires is not None and cookie.expires <= moment:
                expired.append(key)
                continue
            if cookie.host_only:
                if target.host != cookie.domain:
                    continue
            elif not _domain_match(target.host, cookie.domain):
                continue
            if not _path_match(target.path, cookie.path):
                continue
            if cookie.secure and not target.secure:
                continue
            chosen.append(cookie)
        for key in expired:
            del self._cookies[key]
        chosen.sort(key=lambda cookie: (-len(cookie.path), cookie.created))
        return "; ".join(f"{cookie.name}={cookie.value}" for cookie in chosen)

    def _next_created(self) -> int:
        self._created += 1
        return self._created


def cookie_header(
    received: Sequence[tuple[str, str]],
    request_url: str,
    *,
    now: datetime,
) -> str:
    """Store each ``(set_cookie, response_url)`` pair, then serialize ``request_url``.

    ``now`` is the instant every receipt is stored and the request is sent.
    A ``Max-Age`` of zero still evicts a cookie stored earlier in ``received``.
    """

    jar = CookieJar()
    for line, url in received:
        jar.store(str(line), str(url), now)
    return jar.header(request_url, now)


def _aware(moment: datetime) -> datetime:
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("cookie time must be an aware datetime")
    return moment.astimezone(timezone.utc)


@dataclass(frozen=True)
class _Location:
    host: str
    path: str
    secure: bool


def _location(url: str) -> _Location:
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").rstrip(".").lower()
    if not host or parts.scheme.lower() not in {"http", "https", "ws", "wss"}:
        raise ValueError("cookie URL must be an absolute http(s) URL")
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    scheme = parts.scheme.lower()
    secure = scheme in _SECURE_SCHEMES or (scheme == "http" and host in _TRUSTED_HTTP_HOSTS)
    return _Location(host=host, path=path, secure=secure)


def _name_ok(name: str) -> bool:
    return bool(name) and all(char in _TOKEN for char in name)


def _value_ok(value: str) -> bool:
    return all(32 <= ord(char) < 127 and char not in {";", "\\"} for char in value)


def _parse_set_cookie(line: str, now: datetime) -> _Parsed | None:
    pieces = [piece.strip() for piece in str(line or "").split(";")]
    if not pieces or "=" not in pieces[0]:
        return None
    raw_name, raw_value = pieces[0].split("=", 1)
    name = raw_name.strip()
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    domain: str | None = None
    path: str | None = None
    explicit_path = False
    secure = False
    expires: datetime | None = None
    max_age: int | None = None
    saw_max_age = False
    for piece in pieces[1:]:
        if not piece:
            continue
        if "=" in piece:
            attr, raw = piece.split("=", 1)
            attr_value = raw.strip()
        else:
            attr, attr_value = piece, ""
        key = attr.strip().lower()
        if key == "domain":
            candidate = attr_value.lower()
            if candidate.startswith("."):
                candidate = candidate[1:]
            if candidate:
                domain = candidate
        elif key == "path":
            if attr_value.startswith("/"):
                path = attr_value
                explicit_path = True
        elif key == "secure":
            secure = True
        elif key == "max-age":
            parsed_age = _parse_max_age(attr_value)
            saw_max_age = parsed_age is not None
            if parsed_age is not None:
                max_age = parsed_age
        elif key == "expires" and not saw_max_age:
            try:
                parsed = parsedate_to_datetime(attr_value)
            except (TypeError, ValueError, IndexError, OverflowError):
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                expires = parsed.astimezone(timezone.utc)
    if saw_max_age and max_age is not None:
        if max_age <= 0:
            expires = datetime.min.replace(tzinfo=timezone.utc)
        else:
            expires = now + timedelta(seconds=max_age)
    persistent = expires is not None
    return _Parsed(
        name=name,
        value=value,
        domain=domain,
        path=path,
        explicit_path=explicit_path,
        secure=secure,
        expires=expires,
        persistent=persistent,
    )


def _parse_max_age(raw: str) -> int | None:
    text = raw.strip()
    if not text or text[0] not in "0123456789-":
        return None
    digits = text[1:] if text[0] == "-" else text
    if not digits or not digits.isdigit():
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _domain_acceptable(host: str, domain: str) -> bool:
    if not _domain_match(host, domain):
        return False
    if "." not in domain and host != domain:
        return False
    return True


def _domain_match(host: str, domain: str) -> bool:
    if host == domain:
        return True
    if _is_ip(host) or _is_ip(domain):
        return False
    return host.endswith("." + domain)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _default_path(path: str) -> str:
    if not path.startswith("/") or path.count("/") <= 1:
        return "/"
    return path.rsplit("/", 1)[0] or "/"


def _path_match(request_path: str, cookie_path: str) -> bool:
    if request_path == cookie_path:
        return True
    if not request_path.startswith(cookie_path):
        return False
    if cookie_path.endswith("/"):
        return True
    return len(request_path) > len(cookie_path) and request_path[len(cookie_path)] == "/"


