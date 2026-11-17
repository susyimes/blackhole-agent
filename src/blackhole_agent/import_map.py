"""Resolve a module specifier through an import map.

HTML resolves the specifier before any prefix is considered, so a special URL
loses its dot segments first and a non-special URL, such as a data or git URL,
stays on its own scheme. A trailing-slash
key rewrites only a bare specifier or a special URL, and only when the mapped
address still prefixes the result. A null address stops the search. A scope
applies when it is the script URL or a slash-terminated prefix of it; a scope
that does not end in a slash does not cover its children. Scopes and keys are
tried from the greatest UTF-16 code unit to the least, which puts a longer
shared prefix first.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from blackhole_agent.whatwg_url import URLParseError, parse_href

_SPECIAL = frozenset({"http", "https", "ws", "wss", "ftp", "file"})
_RELATIVE_PREFIXES = ("/", "./", "../")


@dataclass(frozen=True)
class _URLRef:
    serialization: str
    special: bool


class _Invalid(Exception):
    """The import map or a base URL cannot be parsed."""


def resolve_module_specifier(
    specifier: str,
    import_map: str,
    base_url: str,
    *,
    map_base_url: str | None = None,
) -> dict[str, object]:
    """Return the URL an import map selects for ``specifier``.

    ``base_url`` is the referring script. ``map_base_url`` is the document that
    owns the map; it defaults to ``base_url``. ``outcome`` is ``resolved``,
    ``blocked``, ``bare``, or ``invalid``. ``integrity`` is the metadata
    registered for the resolved URL, or empty.
    """

    if not isinstance(specifier, str) or not isinstance(import_map, str) or not isinstance(base_url, str):
        return _invalid("specifier, import map, and base URL must be strings")
    if map_base_url is not None and not isinstance(map_base_url, str):
        return _invalid("map base URL must be a string")
    try:
        script_base = _absolute(base_url)
        document_base = script_base if map_base_url is None else _absolute(map_base_url)
        parsed = _parse_map(import_map, document_base.serialization)
        return _resolve(specifier, parsed, script_base)
    except _Invalid as exc:
        return _invalid(str(exc))


def _invalid(error: str) -> dict[str, object]:
    return {"outcome": "invalid", "url": None, "integrity": "", "error": error}


def _finish(outcome: str, url: str | None, integrity: str) -> dict[str, object]:
    return {"outcome": outcome, "url": url, "integrity": integrity, "error": ""}


def _resolve(specifier: str, parsed: _Map, script_base: _URLRef) -> dict[str, object]:
    as_url = _resolve_url_like(specifier, script_base.serialization)
    normalized = as_url.serialization if as_url is not None else specifier
    for scope_prefix, scope_imports in parsed.scopes:
        if scope_prefix == script_base.serialization or (
            scope_prefix.endswith("/") and script_base.serialization.startswith(scope_prefix)
        ):
            matched = _match_imports(normalized, as_url, scope_imports)
            if matched is _BLOCKED:
                return _finish("blocked", None, "")
            if isinstance(matched, str):
                return _finish("resolved", matched, parsed.integrity.get(matched, ""))
    matched = _match_imports(normalized, as_url, parsed.imports)
    if matched is _BLOCKED:
        return _finish("blocked", None, "")
    if isinstance(matched, str):
        return _finish("resolved", matched, parsed.integrity.get(matched, ""))
    if as_url is not None:
        return _finish("resolved", as_url.serialization, parsed.integrity.get(as_url.serialization, ""))
    return _finish("bare", None, "")


class _Blocked:
    pass


_BLOCKED = _Blocked()


def _match_imports(
    normalized: str,
    as_url: _URLRef | None,
    specifier_map: tuple[tuple[str, str | None], ...],
) -> str | _Blocked | None:
    for key, address in specifier_map:
        if key == normalized:
            if address is None:
                return _BLOCKED
            return address
        if (
            key.endswith("/")
            and normalized.startswith(key)
            and (as_url is None or as_url.special)
        ):
            if address is None:
                return _BLOCKED
            after = normalized[len(key) :]
            try:
                url = parse_href(after, address)
            except URLParseError:
                return _BLOCKED
            if not url.startswith(address):
                return _BLOCKED
            return url
    return None


@dataclass(frozen=True)
class _Map:
    imports: tuple[tuple[str, str | None], ...]
    scopes: tuple[tuple[str, tuple[tuple[str, str | None], ...]], ...]
    integrity: Mapping[str, str]


def _parse_map(text: str, base: str) -> _Map:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _Invalid("import map is not JSON") from exc
    if not isinstance(parsed, dict):
        raise _Invalid("import map must be a JSON object")
    imports = _specifier_map(parsed["imports"], base) if "imports" in parsed else ()
    scopes = _scopes(parsed["scopes"], base) if "scopes" in parsed else ()
    integrity = _integrity(parsed["integrity"], base) if "integrity" in parsed else {}
    return _Map(imports, scopes, integrity)


def _specifier_map(value: object, base: str) -> tuple[tuple[str, str | None], ...]:
    if not isinstance(value, dict):
        raise _Invalid("module specifier map must be a JSON object")
    normalized: dict[str, str | None] = {}
    for raw_key, raw_address in value.items():
        if not isinstance(raw_key, str):
            continue
        key = _normalize_key(raw_key, base)
        if key is None:
            continue
        normalized[key] = _normalize_address(raw_key, raw_address, base)
    return _descending(normalized)


def _scopes(value: object, base: str) -> tuple[tuple[str, tuple[tuple[str, str | None], ...]], ...]:
    if not isinstance(value, dict):
        raise _Invalid("scopes must be a JSON object")
    normalized: dict[str, tuple[tuple[str, str | None], ...]] = {}
    for raw_prefix, raw_map in value.items():
        if not isinstance(raw_prefix, str):
            continue
        if not isinstance(raw_map, dict):
            raise _Invalid("scope value must be a JSON object")
        prefix = _resolve_url_like(raw_prefix, base)
        if prefix is None:
            continue
        normalized[prefix.serialization] = _specifier_map(raw_map, base)
    return _descending(normalized)


def _integrity(value: object, base: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _Invalid("integrity must be a JSON object")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            continue
        resolved = _resolve_url_like(raw_key, base)
        if resolved is None:
            continue
        normalized[resolved.serialization] = raw_value
    return normalized


def _normalize_key(key: str, base: str) -> str | None:
    if key == "":
        return None
    resolved = _resolve_url_like(key, base)
    if resolved is not None:
        return resolved.serialization
    return key


def _normalize_address(key: str, address: object, base: str) -> str | None:
    if not isinstance(address, str):
        return None
    resolved = _resolve_url_like(address, base)
    if resolved is None:
        return None
    if key.endswith("/") and not resolved.serialization.endswith("/"):
        return None
    return resolved.serialization


_Value = TypeVar("_Value")


def _descending(mapping: Mapping[str, _Value]) -> tuple[tuple[str, _Value], ...]:
    ordered = sorted(mapping.items(), key=lambda item: _utf16(item[0]), reverse=True)
    return tuple(ordered)


def _utf16(text: str) -> tuple[int, ...]:
    encoded = text.encode("utf-16-be")
    return tuple(encoded[index] << 8 | encoded[index + 1] for index in range(0, len(encoded), 2))


def _absolute(text: str) -> _URLRef:
    resolved = _resolve_url_like(text, None)
    if resolved is None:
        raise _Invalid("base URL did not parse")
    return resolved


def _resolve_url_like(specifier: str, base: str | None) -> _URLRef | None:
    text = _trim_url(specifier)
    if text.startswith(_RELATIVE_PREFIXES):
        if base is None:
            return None
        try:
            serialized = parse_href(text, base)
        except URLParseError:
            return None
        return _URLRef(serialized, _scheme_of(serialized) in _SPECIAL)
    scheme = _scheme_of(text)
    if scheme is None:
        return None
    if scheme in _SPECIAL:
        try:
            serialized = parse_href(text)
        except URLParseError:
            return None
        return _URLRef(serialized, True)
    serialized = _serialize_non_special(text, scheme)
    if serialized is None:
        return None
    return _URLRef(serialized, False)


def _serialize_non_special(text: str, scheme: str) -> str | None:
    rest = text[len(scheme) + 1 :]
    if rest.startswith("//"):
        return _serialize_authority(scheme, rest[2:])
    path, query, fragment = _split_tail(rest)
    serialized = scheme + ":" + _percent_c0(path)
    if query is not None:
        serialized += "?" + _percent_query(query)
    if fragment is not None:
        serialized += "#" + _percent_fragment(fragment)
    return serialized


def _split_tail(text: str) -> tuple[str, str | None, str | None]:
    hash_at = text.find("#")
    if hash_at >= 0:
        fragment: str | None = text[hash_at + 1 :]
        text = text[:hash_at]
    else:
        fragment = None
    query_at = text.find("?")
    if query_at >= 0:
        return text[:query_at], text[query_at + 1 :], fragment
    return text, None, fragment


def _percent_c0(text: str) -> str:
    return _percent(text, lambda code: code <= 0x1F or code >= 0x7F)


def _percent_query(text: str) -> str:
    extra = {0x20, 0x22, 0x23, 0x3C, 0x3E}
    return _percent(text, lambda code: code <= 0x1F or code >= 0x7F or code in extra)


def _percent_fragment(text: str) -> str:
    extra = {0x20, 0x22, 0x3C, 0x3E, 0x60}
    return _percent(text, lambda code: code <= 0x1F or code >= 0x7F or code in extra)


def _percent(text: str, encode: Callable[[int], bool]) -> str:
    pieces: list[str] = []
    for char in text:
        code = ord(char)
        if encode(code):
            pieces.extend(f"%{byte:02X}" for byte in char.encode("utf-8"))
        else:
            pieces.append(char)
    return "".join(pieces)


def _percent_userinfo(text: str) -> str:
    extra = {
        0x20,
        0x22,
        0x23,
        0x2F,
        0x3A,
        0x3B,
        0x3C,
        0x3D,
        0x3E,
        0x3F,
        0x40,
        0x5B,
        0x5C,
        0x5D,
        0x5E,
        0x60,
        0x7B,
        0x7C,
        0x7D,
    }
    return _percent(text, lambda code: code <= 0x1F or code >= 0x7F or code in extra)


def _percent_path(text: str) -> str:
    extra = {0x20, 0x22, 0x23, 0x3C, 0x3E, 0x3F, 0x60, 0x7B, 0x7D}
    return _percent(text, lambda code: code <= 0x1F or code >= 0x7F or code in extra)


def _serialize_authority(scheme: str, body: str) -> str | None:
    end = 0
    while end < len(body) and body[end] not in "/?#":
        end += 1
    authority = body[:end]
    userinfo = ""
    hostport = authority
    if "@" in authority:
        raw_userinfo, hostport = authority.rsplit("@", 1)
        userinfo = _percent_userinfo(raw_userinfo) + "@"
    host, port = _host_port(hostport)
    if host is None:
        return None
    path, query, fragment = _split_tail(body[end:])
    serialized = f"{scheme}://{userinfo}{host}"
    if port is not None:
        serialized += ":" + port
    serialized += _percent_path(path)
    if query is not None:
        serialized += "?" + _percent_query(query)
    if fragment is not None:
        serialized += "#" + _percent_fragment(fragment)
    return serialized


def _host_port(authority: str) -> tuple[str | None, str | None]:
    if authority == "":
        return None, None
    if authority.startswith("["):
        close = authority.find("]")
        if close < 0:
            return None, None
        host = authority[: close + 1]
        rest = authority[close + 1 :]
        if rest == "":
            return host, None
        if not rest.startswith(":"):
            return None, None
        port = rest[1:]
        if not port.isdigit() or int(port) > 65535:
            return None, None
        return host, port
    if ":" in authority:
        host, port = authority.rsplit(":", 1)
        if ":" in host or host == "" or not port.isdigit() or int(port) > 65535:
            return None, None
        return host.lower(), port
    return authority.lower(), None


def _scheme_of(text: str) -> str | None:
    if not text or not text[0].isascii() or not text[0].isalpha():
        return None
    index = 1
    while index < len(text) and text[index].isascii() and (text[index].isalnum() or text[index] in "+-."):
        index += 1
    if index < len(text) and text[index] == ":":
        return text[:index].lower()
    return None


def _trim_url(text: str) -> str:
    raw = "".join(char for char in text if char not in "\t\n\r")
    start = 0
    end = len(raw)
    while start < end and (ord(raw[start]) <= 0x1F or raw[start] == " "):
        start += 1
    while end > start and (ord(raw[end - 1]) <= 0x1F or raw[end - 1] == " "):
        end -= 1
    return raw[start:end]
