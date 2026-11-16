"""Decide whether a Content Security Policy allows a fetch or inline script.

This follows the CSP Level 3 source-list rules that a host allowlist gets
wrong. ``script-src`` replaces ``default-src`` for a script; it does not
union with it. ``*.example.com`` matches a host that ends with
``.example.com`` and does not match the apex or a name that merely ends in
those letters. A path is compared one percent-decoded segment at a time.
``'none'`` matches nothing only when it is the sole expression. The first
copy of a directive wins. ``'strict-dynamic'`` blocks a parser-inserted
script before the host list is consulted, and a nonce still wins before
that. ``script-src-elem`` does not govern workers; ``script-src`` does.
An inline script matches a nonce or a hash of its exact bytes, and either
one suppresses ``'unsafe-inline'``. Every policy in the list must allow
the request.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import re
from collections.abc import Sequence

_ASCII_SPACE = frozenset(" \t\n\f\r")
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\Z")
_DIRECTIVE = re.compile(r"[A-Za-z0-9-]+\Z")
_HOST_LABEL = re.compile(r"[A-Za-z0-9-]+\Z")
_NONCE = re.compile(r"'[Nn][Oo][Nn][Cc][Ee]-([A-Za-z0-9+/_=-]+)'\Z")
_HASH = re.compile(r"'([Ss][Hh][Aa](?:256|384|512))-([A-Za-z0-9+/_=-]+)'\Z")
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}
_SCRIPT_LIKE = frozenset(
    {"audioworklet", "paintworklet", "script", "serviceworker", "sharedworker", "worker", "xslt"}
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


class _URL:
    __slots__ = ("host", "is_domain", "path", "port", "scheme")

    def __init__(self, scheme: str, host: str | None, port: int | None, path: str, is_domain: bool) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.path = path
        self.is_domain = is_domain


def allows(
    policy: str | Sequence[str],
    document: str,
    *,
    destination: str,
    url: str = "",
    inline: bytes | str | None = None,
    nonce: str = "",
    parser_inserted: bool = False,
) -> dict[str, object]:
    """Return whether every policy allows this fetch or inline check.

    ``inline`` selects the inline-script check and ignores ``url``. A fetch
    uses ``url``. ``effective_directive`` is the directive that blocked the
    request, or the directive whose list allowed it when nothing blocked.
    It is empty when no directive applies.
    """

    policies = _policies(policy)
    if not isinstance(destination, str):
        raise TypeError("destination must be a string")
    if not isinstance(nonce, str):
        raise TypeError("nonce must be a string")
    origin = _parse_url(document)
    payload = _inline_bytes(inline)
    decided = ""
    for text in policies:
        parsed = _parse_policy(text)
        if payload is None:
            if not isinstance(url, str) or url == "":
                raise ValueError("fetch URL must be a non-empty string")
            allowed, name = _request_allowed(parsed, origin, destination, url, nonce, parser_inserted)
        else:
            allowed, name = _inline_allowed(parsed, destination, payload, nonce, parser_inserted)
        if name:
            decided = name
        if not allowed:
            return {"allowed": False, "effective_directive": name}
    return {"allowed": True, "effective_directive": decided}


def _policies(policy: str | Sequence[str]) -> list[str]:
    if isinstance(policy, str):
        return [policy]
    if isinstance(policy, Sequence) and all(isinstance(item, str) for item in policy):
        return list(policy)
    raise TypeError("policy must be a string or a sequence of strings")


def _inline_bytes(inline: bytes | str | None) -> bytes | None:
    if inline is None:
        return None
    if isinstance(inline, bytes):
        return inline
    if isinstance(inline, str):
        return inline.encode("utf-8")
    raise TypeError("inline source must be bytes or a string")


def _parse_policy(serialized: str) -> dict[str, tuple[str, ...]]:
    if not isinstance(serialized, str):
        raise TypeError("policy must be a string")
    directives: dict[str, tuple[str, ...]] = {}
    for token in serialized.split(";"):
        token = _strip(token)
        if not token or not token.isascii():
            continue
        parts = [part for part in _split_ascii(token) if part]
        if not parts or not _DIRECTIVE.fullmatch(parts[0]):
            continue
        name = parts[0].lower()
        if name in directives:
            continue
        directives[name] = tuple(parts[1:])
    return directives


def _request_allowed(
    policy: dict[str, tuple[str, ...]],
    origin: _URL,
    destination: str,
    url: str,
    nonce: str,
    parser_inserted: bool,
) -> tuple[bool, str]:
    effective = _effective_request(destination)
    if effective is None:
        return True, ""
    active = _active_directive(effective, policy)
    if active is None:
        return True, ""
    sources = policy[active]
    kind = _request_kind(active, effective)
    if kind == "script" and destination.lower() in _SCRIPT_LIKE:
        if _nonce_matches(nonce, sources):
            return True, active
        if _has(sources, "'strict-dynamic'"):
            return (not parser_inserted), active
    elif kind == "style" and _nonce_matches(nonce, sources):
        return True, active
    if not _url_matches(url, sources, origin):
        return False, active
    return True, active


def _inline_allowed(
    policy: dict[str, tuple[str, ...]],
    destination: str,
    payload: bytes,
    nonce: str,
    parser_inserted: bool,
) -> tuple[bool, str]:
    kind = destination.lower()
    if kind in {"script", "navigation"}:
        effective = "script-src-elem"
        inline_type = "script" if kind == "script" else "navigation"
    elif kind == "style":
        effective = "style-src-elem"
        inline_type = "style"
    else:
        return True, ""
    active = _active_directive(effective, policy)
    if active is None:
        return True, ""
    sources = policy[active]
    if _allows_all_inline(sources, inline_type):
        return True, active
    if inline_type in {"script", "style"} and _nonce_matches(nonce, sources):
        return True, active
    if inline_type == "script" and _has(sources, "'strict-dynamic'") and not parser_inserted:
        return True, active
    if inline_type in {"script", "style"} and _hash_matches(payload, sources):
        return True, active
    return False, active


def _effective_request(destination: str) -> str | None:
    name = destination.lower()
    if name == "manifest":
        return "manifest-src"
    if name in {"object", "embed"}:
        return "object-src"
    if name in {"frame", "iframe"}:
        return "frame-src"
    if name in {"audio", "track", "video"}:
        return "media-src"
    if name == "font":
        return "font-src"
    if name == "image":
        return "img-src"
    if name == "style":
        return "style-src-elem"
    if name in {"script", "xslt", "audioworklet", "paintworklet"}:
        return "script-src-elem"
    if name in {"serviceworker", "sharedworker", "worker"}:
        return "worker-src"
    if name == "report":
        return None
    return "connect-src"


def _active_directive(effective: str, policy: dict[str, tuple[str, ...]]) -> str | None:
    for name in _FALLBACK.get(effective, ()):
        if name in policy:
            return name
    return None


def _request_kind(active: str, effective: str) -> str:
    name = effective if active == "default-src" else active
    if name in {"script-src", "script-src-elem"}:
        return "script"
    if name in {"style-src", "style-src-elem"}:
        return "style"
    return "url"


def _allows_all_inline(sources: tuple[str, ...], inline_type: str) -> bool:
    allow = False
    for expression in sources:
        if _NONCE.fullmatch(expression) or _HASH.fullmatch(expression):
            return False
        if inline_type in {"script", "script attribute", "navigation"} and expression.lower() == "'strict-dynamic'":
            return False
        if expression.lower() == "'unsafe-inline'":
            allow = True
    return allow


def _nonce_matches(nonce: str, sources: tuple[str, ...]) -> bool:
    if nonce == "":
        return False
    for expression in sources:
        match = _NONCE.fullmatch(expression)
        if match is not None and match.group(1) == nonce:
            return True
    return False


def _hash_matches(payload: bytes, sources: tuple[str, ...]) -> bool:
    for expression in sources:
        match = _HASH.fullmatch(expression)
        if match is None:
            continue
        algorithm = "sha" + match.group(1)[-3:]
        expected = match.group(2).replace("-", "+").replace("_", "/")
        actual = base64.b64encode(hashlib.new(algorithm, payload).digest()).decode("ascii")
        if actual == expected:
            return True
    return False


def _has(sources: tuple[str, ...], keyword: str) -> bool:
    target = keyword.lower()
    return any(item.lower() == target for item in sources)


def _url_matches(url: str, sources: tuple[str, ...], origin: _URL) -> bool:
    if not sources:
        return False
    if len(sources) == 1 and sources[0].lower() == "'none'":
        return False
    parsed = _parse_url(url)
    return any(_expression_matches(parsed, expression, origin) for expression in sources)


def _expression_matches(url: _URL, expression: str, origin: _URL) -> bool:
    if expression == "*":
        return url.scheme in {"http", "https"} or url.scheme == origin.scheme
    if expression.lower() == "'self'":
        return _self_matches(url, origin)
    scheme = _scheme_source(expression)
    if scheme is not None:
        return _scheme_part_matches(scheme, url.scheme)
    host = _host_source(expression)
    if host is None:
        return False
    source_scheme, host_part, port, path = host
    if source_scheme is not None:
        if not _scheme_part_matches(source_scheme, url.scheme):
            return False
    elif not _scheme_part_matches(origin.scheme, url.scheme):
        return False
    if url.host is None or not _host_part_matches(host_part, url.host, url.is_domain):
        return False
    if not _port_part_matches(port, url):
        return False
    if path and not _path_part_matches(path, url.path):
        return False
    return True


def _self_matches(url: _URL, origin: _URL) -> bool:
    if url.scheme == "blob":
        return False
    if _same_origin(url, origin):
        return True
    if url.host is None or origin.host is None or url.host != origin.host:
        return False
    if url.port != origin.port:
        return False
    if url.scheme in {"https", "wss"}:
        return True
    return origin.scheme == "http" and url.scheme in {"http", "ws"}


def _same_origin(url: _URL, origin: _URL) -> bool:
    return url.scheme == origin.scheme and url.host is not None and url.host == origin.host and url.port == origin.port


def _scheme_part_matches(expression_scheme: str, url_scheme: str) -> bool:
    left = expression_scheme.lower()
    right = url_scheme.lower()
    if left == right:
        return True
    if left == "http" and right == "https":
        return True
    if left == "ws" and right in {"wss", "http", "https"}:
        return True
    return left == "wss" and right == "https"


def _host_part_matches(pattern: str, host: str, is_domain: bool) -> bool:
    if not is_domain:
        return False
    if pattern == "*":
        return True
    if pattern.startswith("*."):
        remaining = pattern[1:].lower()
        return host.lower().endswith(remaining)
    return pattern.lower() == host.lower()


def _port_part_matches(port: str | None, url: _URL) -> bool:
    if port == "*":
        return True
    normalized = None if port is None else int(port)
    if normalized == url.port:
        return True
    if url.port is None:
        return normalized == _DEFAULT_PORTS.get(url.scheme)
    return False


def _path_part_matches(path_a: str, path_b: str) -> bool:
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
        if _percent_decode(piece_a) != _percent_decode(piece_b):
            return False
    return True


def _percent_decode(piece: str) -> str:
    raw = bytearray()
    chars: list[str] = []

    def flush() -> None:
        if raw:
            chars.append(raw.decode("utf-8", "replace"))
            raw.clear()

    index = 0
    while index < len(piece):
        if (
            piece[index] == "%"
            and index + 2 < len(piece)
            and piece[index + 1] in "0123456789abcdefABCDEF"
            and piece[index + 2] in "0123456789abcdefABCDEF"
        ):
            raw.append(int(piece[index + 1 : index + 3], 16))
            index += 3
            continue
        flush()
        chars.append(piece[index])
        index += 1
    flush()
    return "".join(chars)


def _scheme_source(token: str) -> str | None:
    if token.endswith(":") and not token.endswith("://") and token.count(":") == 1:
        scheme = token[:-1]
        if _SCHEME.fullmatch(scheme):
            return scheme.lower()
    return None


def _host_source(token: str) -> tuple[str | None, str, str | None, str] | None:
    scheme = None
    rest = token
    if "://" in token:
        scheme_text, _, rest = token.partition("://")
        if not _SCHEME.fullmatch(scheme_text):
            return None
        scheme = scheme_text.lower()
    path = ""
    if "/" in rest:
        rest, _, tail = rest.partition("/")
        path = "/" + tail
        if ";" in path or "," in path:
            return None
    port = None
    host = rest
    if ":" in host:
        host, _, port_text = host.rpartition(":")
        if port_text != "*" and (not port_text.isascii() or not port_text.isdigit()):
            return None
        if port_text != "*" and port_text == "":
            return None
        port = port_text
    if not _valid_host_part(host):
        return None
    return scheme, host, port, path


def _valid_host_part(host: str) -> bool:
    if host == "*":
        return True
    body = host[2:] if host.startswith("*.") else host
    if body.endswith("."):
        body = body[:-1]
    if not body or host.startswith("*") and not host.startswith("*."):
        return False
    return all(_HOST_LABEL.fullmatch(label) for label in body.split("."))


def _parse_url(text: str) -> _URL:
    if not isinstance(text, str) or text == "":
        raise ValueError("URL must be a non-empty string")
    if any(character in text for character in "\t\n\r "):
        raise ValueError("URL contains whitespace")
    scheme, separator, rest = text.partition(":")
    if not separator or not _SCHEME.fullmatch(scheme):
        raise ValueError("URL scheme is missing")
    scheme = scheme.lower()
    host: str | None = None
    port: int | None = None
    if rest.startswith("//"):
        rest = rest[2:]
        cut = len(rest)
        for index, character in enumerate(rest):
            if character in "/?#":
                cut = index
                break
        authority = rest[:cut]
        path = rest[cut:]
        if "@" in authority:
            authority = authority.rsplit("@", 1)[1]
        host, port = _authority(authority)
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path == "":
            path = "/"
    else:
        path = rest.split("?", 1)[0].split("#", 1)[0]
    if port is not None and port == _DEFAULT_PORTS.get(scheme):
        port = None
    is_domain = host is not None and not _is_ip(host)
    return _URL(scheme, host, port, path, is_domain)


def _authority(authority: str) -> tuple[str | None, int | None]:
    port: int | None = None
    if authority.startswith("["):
        end = authority.find("]")
        if end < 0:
            raise ValueError("IPv6 host is truncated")
        host: str | None = authority[1:end].lower()
        tail = authority[end + 1 :]
        if tail.startswith(":"):
            port = _port_number(tail[1:])
        elif tail:
            raise ValueError("IPv6 host has trailing junk")
    elif ":" in authority:
        host_text, _, port_text = authority.rpartition(":")
        host = host_text.lower().rstrip(".") or None
        port = _port_number(port_text)
    else:
        host = authority.lower().rstrip(".") or None
    if host == "":
        host = None
    return host, port


def _port_number(text: str) -> int:
    if not text.isascii() or not text.isdigit():
        raise ValueError("URL port is not a number")
    value = int(text)
    if value > 65535:
        raise ValueError("URL port is out of range")
    return value


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _strip(text: str) -> str:
    start = 0
    end = len(text)
    while start < end and text[start] in _ASCII_SPACE:
        start += 1
    while end > start and text[end - 1] in _ASCII_SPACE:
        end -= 1
    return text[start:end]


def _split_ascii(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    index = 0
    while index <= len(text):
        if index == len(text) or text[index] in _ASCII_SPACE:
            if index > start:
                parts.append(text[start:index])
            start = index + 1
        index += 1
    return parts
