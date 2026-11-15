"""Decide whether a request is allowed by a Content-Security-Policy.

Python's URL helpers do not apply CSP source lists. ``request_allowed`` parses
a serialized policy list and runs the CSP Level 3 checks: operative-directive
fallback, host and scheme matching, ``'self'``, and ``'strict-dynamic'``.

Comma-separated policies are enforced together. A host source does not match a
longer name that merely ends with the same letters. ``http://cdn.example``
matches ``https://cdn.example`` because an explicit insecure scheme upgrades,
but ``http://cdn.example:80`` does not match that https URL: port 80 is not
the default port for https. ``'self'`` on an http origin allows the https
upgrade of the same host and does not allow a blob URL.

``'strict-dynamic'`` blocks a parser-inserted script that only matches a host
source, and allows a script the page inserted itself. Nonce and integrity
metadata are checked before that keyword. A worker or frame that falls through
to ``script-src`` still has to match the source list. The script-like branch
only adds nonce, hash, and strict-dynamic; otherwise the worker fallback in
the directive list would never consult ``script-src``.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Sequence
from urllib.parse import unquote, urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}
_SCRIPT_LIKE = frozenset({"script", "xslt", "audioworklet", "paintworklet"})
_SCRIPT_DIRECTIVES = frozenset({"script-src", "script-src-elem"})
_HINT_DIRECTIVES = frozenset(
    {
        "child-src",
        "connect-src",
        "font-src",
        "frame-src",
        "img-src",
        "manifest-src",
        "media-src",
        "object-src",
        "script-src",
        "script-src-elem",
        "style-src",
        "style-src-elem",
        "worker-src",
    }
)
_FALLBACK = {
    "script-src-elem": ("script-src-elem", "script-src", "default-src"),
    "script-src-attr": ("script-src-attr", "script-src", "default-src"),
    "style-src-elem": ("style-src-elem", "style-src", "default-src"),
    "style-src-attr": ("style-src-attr", "style-src", "default-src"),
    "worker-src": ("worker-src", "child-src", "script-src", "default-src"),
    "connect-src": ("connect-src", "default-src"),
    "manifest-src": ("manifest-src", "default-src"),
    "object-src": ("object-src", "default-src"),
    "frame-src": ("frame-src", "child-src", "default-src"),
    "media-src": ("media-src", "default-src"),
    "font-src": ("font-src", "default-src"),
    "img-src": ("img-src", "default-src"),
}
_EFFECTIVE = {
    "": "connect-src",
    "manifest": "manifest-src",
    "object": "object-src",
    "embed": "object-src",
    "frame": "frame-src",
    "iframe": "frame-src",
    "audio": "media-src",
    "track": "media-src",
    "video": "media-src",
    "font": "font-src",
    "image": "img-src",
    "style": "style-src-elem",
    "script": "script-src-elem",
    "xslt": "script-src-elem",
    "audioworklet": "script-src-elem",
    "paintworklet": "script-src-elem",
    "serviceworker": "worker-src",
    "sharedworker": "worker-src",
    "worker": "worker-src",
    "json": "connect-src",
    "text": "connect-src",
    "webidentity": "connect-src",
}
_ASCII_WS = "\t\n\x0c\r "
_SCHEME_SOURCE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:$")
_PCHAR = r"(?:[A-Za-z0-9\-._~!$&'()*+=:@]|%[0-9A-Fa-f]{2})"
_PATH = re.compile(rf"/(?:{_PCHAR}+(?:/{_PCHAR}*)*)?")
_HOST_PART = re.compile(r"(?:\*|\*\.(?:[A-Za-z0-9-]+\.)*[A-Za-z0-9-]+\.?|(?:[A-Za-z0-9-]+\.)*[A-Za-z0-9-]+\.?)")
_BASE64 = re.compile(r"[A-Za-z0-9+/_-]+={0,2}")
_Directive = tuple[str, tuple[str, ...]]


class _Part:
    __slots__ = ("scheme", "host", "port", "path", "domain")

    def __init__(self, scheme: str, host: str | None, port: int | None, path: str, domain: bool) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.path = path
        self.domain = domain


class _Origin:
    __slots__ = ("scheme", "host", "port", "opaque")

    def __init__(self, scheme: str, host: str | None, port: int | None, opaque: bool) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.opaque = opaque


def request_allowed(
    policies: str,
    *,
    destination: str,
    url: str,
    origin: str,
    nonce: str = "",
    integrity: str = "",
    parser_metadata: str = "",
    redirect_count: int = 0,
    initiator: str = "",
) -> dict[str, object]:
    """Return whether ``policies`` allows this request.

    ``policies`` is a ``Content-Security-Policy`` header value. Commas
    separate policies. ``destination`` is a Fetch request destination.
    ``origin`` is the protected resource's serialized origin, or ``null``.
    ``nonce`` and ``integrity`` are the request metadata. ``parser_metadata``
    is ``parser-inserted``, ``not-parser-inserted``, or empty.
    ``redirect_count`` above zero ignores a source path, matching the rule
    that a redirect must not leak the path.

    ``allowed`` is false when an enforced policy blocks the request.
    ``effective`` is the destination's effective directive. ``checked`` is
    the operative directive that produced the decision, or empty when no
    directive applied. ``reason`` is empty, ``blocked``, or ``invalid``.
    """

    if not _inputs_ok(
        policies,
        destination,
        url,
        origin,
        nonce,
        integrity,
        parser_metadata,
        redirect_count,
        initiator,
    ):
        return _result(False, "invalid", "", "")
    parsed_policies = _parse_policies(policies)
    target = _parse_url(url)
    page = _parse_origin(origin)
    if target is None or page is None:
        return _result(False, "invalid", "", "")
    effective = _effective(destination, initiator)
    checked = ""
    for policy in parsed_policies:
        violated = _violates(
            policy,
            effective=effective,
            destination=destination,
            url=target,
            origin=page,
            nonce=nonce,
            integrity=integrity,
            parser_metadata=parser_metadata,
            redirect_count=redirect_count,
            initiator=initiator,
        )
        if violated:
            return _result(False, "blocked", effective, violated)
        if not checked:
            checked = _operative(policy, effective, initiator)
    return _result(True, "", effective, checked)


def _result(allowed: bool, reason: str, effective: str, checked: str) -> dict[str, object]:
    return {
        "allowed": allowed,
        "reason": reason,
        "effective": effective,
        "checked": checked,
    }


def _inputs_ok(
    policies: str,
    destination: str,
    url: str,
    origin: str,
    nonce: str,
    integrity: str,
    parser_metadata: str,
    redirect_count: int,
    initiator: str,
) -> bool:
    if (
        not isinstance(policies, str)
        or not isinstance(destination, str)
        or not isinstance(url, str)
        or not isinstance(origin, str)
        or not isinstance(nonce, str)
        or not isinstance(integrity, str)
        or not isinstance(parser_metadata, str)
        or not isinstance(initiator, str)
        or type(redirect_count) is not int
        or redirect_count < 0
    ):
        return False
    return True


def _parse_policies(header: str) -> tuple[tuple[_Directive, ...], ...]:
    policies: list[tuple[_Directive, ...]] = []
    for piece in header.split(","):
        policies.append(_parse_policy(piece))
    return tuple(policies)


def _parse_policy(serialized: str) -> tuple[_Directive, ...]:
    directives: list[_Directive] = []
    seen: set[str] = set()
    for token in serialized.split(";"):
        token = token.strip(_ASCII_WS)
        if not token or not token.isascii():
            continue
        parts = [part for part in re.split(r"[\t\n\x0c\r ]+", token) if part]
        if not parts:
            continue
        name = parts[0].lower()
        if not re.fullmatch(r"[a-z0-9-]+", name) or name in seen:
            continue
        seen.add(name)
        directives.append((name, tuple(parts[1:])))
    return tuple(directives)


def _effective(destination: str, initiator: str) -> str:
    if initiator in {"prefetch", "prerender"}:
        return "default-src"
    return _EFFECTIVE.get(destination, "connect-src")


def _operative(policy: tuple[_Directive, ...], effective: str, initiator: str) -> str:
    if initiator == "prefetch":
        return ""
    present = {name for name, _sources in policy}
    for name, _sources in policy:
        if _should_execute(effective, name, present):
            return name
    return ""


def _violates(
    policy: tuple[_Directive, ...],
    *,
    effective: str,
    destination: str,
    url: _Part,
    origin: _Origin,
    nonce: str,
    integrity: str,
    parser_metadata: str,
    redirect_count: int,
    initiator: str,
) -> str:
    if initiator == "prefetch":
        return _hint_violation(policy, url, origin, redirect_count)
    present = {name for name, _sources in policy}
    violated = ""
    for name, sources in policy:
        if not _should_execute(effective, name, present):
            continue
        allowed = _directive_allows(
            name,
            sources,
            destination=destination,
            url=url,
            origin=origin,
            nonce=nonce,
            integrity=integrity,
            parser_metadata=parser_metadata,
            redirect_count=redirect_count,
        )
        if not allowed:
            violated = name
    return violated


def _hint_violation(
    policy: tuple[_Directive, ...],
    url: _Part,
    origin: _Origin,
    redirect_count: int,
) -> str:
    default = next((name for name, _sources in policy if name == "default-src"), "")
    if not default:
        return ""
    for name, sources in policy:
        if name not in _HINT_DIRECTIVES:
            continue
        if _list_matches(url, sources, origin, redirect_count):
            return ""
    return default


def _should_execute(effective: str, name: str, present: set[str]) -> bool:
    for fallback in _FALLBACK.get(effective, ()):
        if name == fallback:
            return True
        if fallback in present:
            return False
    return False


def _directive_allows(
    name: str,
    sources: tuple[str, ...],
    *,
    destination: str,
    url: _Part,
    origin: _Origin,
    nonce: str,
    integrity: str,
    parser_metadata: str,
    redirect_count: int,
) -> bool:
    if name in _SCRIPT_DIRECTIVES and destination in _SCRIPT_LIKE:
        if _nonce_matches(nonce, sources) or _integrity_matches(integrity, sources):
            return True
        if _has_keyword(sources, "strict-dynamic"):
            return parser_metadata != "parser-inserted"
    return _list_matches(url, sources, origin, redirect_count)


def _list_matches(url: _Part, sources: Sequence[str], origin: _Origin, redirect_count: int) -> bool:
    if not sources:
        return False
    if len(sources) == 1 and sources[0].lower() == "'none'":
        return False
    return any(_expression_matches(url, expression, origin, redirect_count) for expression in sources)


def _expression_matches(url: _Part, expression: str, origin: _Origin, redirect_count: int) -> bool:
    if expression == "*":
        return url.scheme in {"http", "https"} or url.scheme == origin.scheme
    scheme_only = _SCHEME_SOURCE.fullmatch(expression) is not None
    host = None if scheme_only else _parse_host_source(expression)
    if scheme_only or host is not None:
        scheme_part = expression[:-1] if scheme_only else host["scheme"] if host else None
        if scheme_part is not None and not _scheme_match(scheme_part, url.scheme):
            return False
        if scheme_only:
            return True
        if host is None or url.host is None:
            return False
        if host["scheme"] is None and not _scheme_match(origin.scheme, url.scheme):
            return False
        if not _host_match(str(host["host"]), url):
            return False
        if not _port_match(host["port"], url):
            return False
        if host["path"] and redirect_count == 0 and not _path_match(str(host["path"]), url.path):
            return False
        return True
    if expression.lower() == "'self'":
        return _self_matches(url, origin)
    return False


def _scheme_match(left: str, right: str) -> bool:
    one = left.lower()
    other = right.lower()
    if one == other:
        return True
    if one == "http" and other == "https":
        return True
    if one == "ws" and other in {"wss", "http", "https"}:
        return True
    if one == "wss" and other == "https":
        return True
    return False


def _host_match(pattern: str, url: _Part) -> bool:
    if not url.domain or url.host is None:
        return False
    if pattern == "*":
        return True
    if pattern.startswith("*."):
        return url.host.endswith(pattern[1:].lower())
    return pattern.lower() == url.host


def _port_match(port_part: int | str | None, url: _Part) -> bool:
    if port_part == "*":
        return True
    if port_part == url.port:
        return True
    if url.port is None and port_part == _DEFAULT_PORTS.get(url.scheme):
        return True
    return False


def _path_match(path_a: str, path_b: str) -> bool:
    if path_a == "":
        return True
    if path_a == "/" and path_b == "":
        return True
    exact = not path_a.endswith("/")
    pieces_a = path_a.split("/")
    pieces_b = path_b.split("/")
    if len(pieces_a) > len(pieces_b):
        return False
    if exact and len(pieces_a) != len(pieces_b):
        return False
    if not exact:
        pieces_a = pieces_a[:-1]
    for piece_a, piece_b in zip(pieces_a, pieces_b):
        if unquote(piece_a, encoding="utf-8", errors="replace") != unquote(piece_b, encoding="utf-8", errors="replace"):
            return False
    return True


def _self_matches(url: _Part, origin: _Origin) -> bool:
    if url.scheme == "blob":
        return False
    if origin.opaque or url.host is None or origin.host is None or url.host != origin.host:
        return False
    if url.scheme == origin.scheme and url.port == origin.port:
        return True
    if url.port != origin.port and not (
        _is_default_port(origin.scheme, origin.port) and _is_default_port(url.scheme, url.port)
    ):
        return False
    if url.scheme in {"https", "wss"}:
        return True
    return origin.scheme == "http" and url.scheme in {"http", "ws"}


def _is_default_port(scheme: str, port: int | None) -> bool:
    default = _DEFAULT_PORTS.get(scheme)
    return port is None or port == default


def _nonce_matches(nonce: str, sources: Sequence[str]) -> bool:
    if nonce == "":
        return False
    for expression in sources:
        value = _nonce_value(expression)
        if value is not None and value == nonce:
            return True
    return False


def _integrity_matches(integrity: str, sources: Sequence[str]) -> bool:
    hashes = [
        (algorithm, value)
        for expression in sources
        if (parsed := _hash_value(expression)) is not None
        for algorithm, value in (parsed,)
    ]
    if not hashes:
        return False
    metadata = _parse_integrity(integrity)
    if not metadata:
        return False
    for algorithm, value in metadata:
        if not any(algorithm == have and value == got for have, got in hashes):
            return False
    return True


def _parse_integrity(integrity: str) -> tuple[tuple[str, str], ...]:
    text = integrity.strip(_ASCII_WS)
    if not text:
        return ()
    found: list[tuple[str, str]] = []
    for token in re.split(r"[\t\n\x0c\r ]+", text):
        parsed = _hash_value("'" + token + "'") if not token.startswith("'") else _hash_value(token)
        if parsed is None:
            return ()
        found.append(parsed)
    return tuple(found)


def _has_keyword(sources: Sequence[str], keyword: str) -> bool:
    return any(expression.lower() == f"'{keyword}'" for expression in sources)


def _nonce_value(expression: str) -> str | None:
    if len(expression) < 9 or expression[0] != "'" or expression[-1] != "'":
        return None
    body = expression[1:-1]
    if len(body) < 7 or body[:6].lower() != "nonce-":
        return None
    value = body[6:]
    if _BASE64.fullmatch(value):
        return value
    return None


def _hash_value(expression: str) -> tuple[str, str] | None:
    if len(expression) < 4 or expression[0] != "'" or expression[-1] != "'":
        return None
    algorithm, separator, value = expression[1:-1].partition("-")
    if not separator or algorithm.lower() not in {"sha256", "sha384", "sha512"}:
        return None
    if not _BASE64.fullmatch(value):
        return None
    return algorithm.lower(), value


def _parse_host_source(expression: str) -> dict[str, object] | None:
    text = expression
    scheme: str | None = None
    if "://" in text:
        scheme, separator, remainder = text.partition("://")
        if not separator or _SCHEME_SOURCE.fullmatch(scheme + ":") is None or not remainder:
            return None
        text = remainder
    path = ""
    slash = text.find("/")
    if slash >= 0:
        path = text[slash:]
        text = text[:slash]
        if _PATH.fullmatch(path) is None:
            return None
    port: int | str | None = None
    if ":" in text:
        host, separator, port_token = text.rpartition(":")
        if not separator:
            return None
        if port_token == "*":
            port = "*"
        elif port_token.isdigit():
            port = int(port_token)
        else:
            return None
        text = host
    if _HOST_PART.fullmatch(text) is None:
        return None
    return {"scheme": scheme, "host": text, "port": port, "path": path}


def _parse_origin(value: str) -> _Origin | None:
    if value == "null":
        return _Origin("", None, None, True)
    part = _parse_url(value)
    if part is None:
        return None
    return _Origin(part.scheme, part.host, part.port, False)


def _parse_url(value: str) -> _Part | None:
    cleaned = "".join(char for char in value if char not in "\t\n\r")
    try:
        parts = urlsplit(cleaned)
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if not scheme or not re.fullmatch(r"[a-z][a-z0-9+.\-]*", scheme):
        return None
    host = parts.hostname
    if host is not None:
        host = host.lower()
        if any(ord(char) > 127 for char in host):
            try:
                host = host.encode("idna").decode("ascii")
            except UnicodeError:
                return None
        if host == "":
            host = None
    try:
        port = parts.port
    except ValueError:
        return None
    if port is not None and port == _DEFAULT_PORTS.get(scheme):
        port = None
    domain = host is not None and not _is_ip(host)
    return _Part(scheme, host, port, parts.path, domain)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True
