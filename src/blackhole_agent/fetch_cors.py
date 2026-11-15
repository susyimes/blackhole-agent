"""Share a cross-origin response under the Fetch CORS protocol.

A reflected ``Access-Control-Allow-Origin`` is not enough. The check, the
safelist, the preflight authorization, and the filtered header list follow
the Fetch standard: a wildcard origin fails when credentials are included,
``true`` is case-sensitive, ``Authorization`` is not covered by an
allow-headers wildcard, and ``Set-Cookie`` is never exposed.

The preflight ``max-age`` imposed limit is 7200 seconds, the cap Chromium
uses where the standard leaves the limit to the user agent. A missing or
unparsable ``Access-Control-Max-Age`` is 5 seconds.
"""

from __future__ import annotations

from typing import Mapping, Sequence

_CREDENTIALS = frozenset({"omit", "same-origin", "include"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "POST"})
_SAFE_ESSENCES = frozenset(
    {"application/x-www-form-urlencoded", "multipart/form-data", "text/plain"}
)
_ALWAYS_EXPOSED = frozenset(
    {
        "cache-control",
        "content-language",
        "content-length",
        "content-type",
        "expires",
        "last-modified",
        "pragma",
    }
)
_FORBIDDEN_RESPONSE = frozenset({"set-cookie", "set-cookie2"})
_TOKEN = frozenset("!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_HTTP_WS = frozenset("\t\n\r ")
_LANGUAGE_BYTES = frozenset("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz *,.-;=")
_UNSAFE_BYTES = (
    frozenset(range(0x20)) - frozenset({0x09})
) | frozenset({0x22, 0x28, 0x29, 0x3A, 0x3C, 0x3E, 0x3F, 0x40, 0x5B, 0x5C, 0x5D, 0x7B, 0x7D, 0x7F})
_PREFLIGHT_MAX_AGE = 7200
_DEFAULT_MAX_AGE = 5
_HeaderPairs = Sequence[tuple[str, str]] | Mapping[str, str] | None


def cors_response(
    *,
    origin: str,
    credentials: str = "omit",
    method: str = "GET",
    request_headers: _HeaderPairs = None,
    response_headers: _HeaderPairs = None,
    status: int = 200,
    preflight: bool = False,
    use_preflight_flag: bool = False,
) -> dict[str, object]:
    """Decide whether this response may be read by the calling origin.

    ``origin`` is the already serialized request origin, including the string
    ``null``. ``credentials`` is ``omit``, ``same-origin``, or ``include``.
    Header lists are ordered ``(name, value)`` pairs so duplicate field lines
    stay distinct. A mapping is accepted but cannot represent duplicates.

    ``allowed`` is false when the CORS check or, for a preflight, the method
    and header authorization fails. ``exposed`` is the filtered header list a
    script can read, in response order. ``unsafe_request_headers`` is the
    sorted lowercase set that forces a preflight. ``max_age`` is set only for
    an authorized preflight.
    """

    request = _pairs(request_headers)
    response = _pairs(response_headers)
    if (
        request is None
        or response is None
        or not isinstance(origin, str)
        or _not_bytes(origin)
        or credentials not in _CREDENTIALS
        or not isinstance(method, str)
        or method == ""
        or _not_bytes(method)
        or type(status) is not int
        or type(preflight) is not bool
        or type(use_preflight_flag) is not bool
    ):
        return _result(False, "invalid", [], [], False, None)

    unsafe = _unsafe_names(request)
    needs_preflight = bool(use_preflight_flag or method not in _SAFE_METHODS or unsafe)
    if not _cors_check(origin, response, credentials):
        return _result(False, "cors-check", [], unsafe, needs_preflight, None)
    exposed = _filtered(response, credentials)
    if not preflight:
        return _result(True, "", exposed, unsafe, needs_preflight, None)
    if status < 200 or status > 299:
        return _result(False, "status", [], unsafe, needs_preflight, None)
    reason = _authorize_preflight(
        method,
        request,
        response,
        credentials=credentials,
        unsafe=unsafe,
        use_preflight_flag=use_preflight_flag,
    )
    if reason:
        return _result(False, reason, [], unsafe, needs_preflight, None)
    return _result(True, "", exposed, unsafe, needs_preflight, _max_age(response))


def _result(
    allowed: bool,
    reason: str,
    exposed: list[list[str]],
    unsafe: list[str],
    needs_preflight: bool,
    max_age: int | None,
) -> dict[str, object]:
    return {
        "allowed": allowed,
        "reason": reason,
        "exposed": exposed,
        "unsafe_request_headers": unsafe,
        "needs_preflight": needs_preflight,
        "max_age": max_age,
    }


def _pairs(headers: _HeaderPairs) -> list[tuple[str, str]] | None:
    if headers is None:
        return []
    raw_items = list(headers.items()) if isinstance(headers, Mapping) else list(headers)
    parsed: list[tuple[str, str]] = []
    for item in raw_items:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            return None
        name, value = item
        if isinstance(name, bytes):
            name = name.decode("latin-1")
        if isinstance(value, bytes):
            value = value.decode("latin-1")
        if not isinstance(name, str) or not isinstance(value, str):
            return None
        if _not_bytes(name) or _not_bytes(value):
            return None
        parsed.append((name, value))
    return parsed


def _not_bytes(text: str) -> bool:
    return any(ord(char) > 255 for char in text)


def _lower(name: str) -> str:
    return name.lower()


def _get(headers: list[tuple[str, str]], name: str) -> str | None:
    matches = [value for header_name, value in headers if _lower(header_name) == name]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return ", ".join(matches)


def _cors_check(origin: str, headers: list[tuple[str, str]], credentials: str) -> bool:
    allowed_origin = _get(headers, "access-control-allow-origin")
    if allowed_origin is None:
        return False
    if credentials != "include" and allowed_origin == "*":
        return True
    if allowed_origin != origin:
        return False
    if credentials != "include":
        return True
    return _get(headers, "access-control-allow-credentials") == "true"


def _filtered(headers: list[tuple[str, str]], credentials: str) -> list[list[str]]:
    extra = _extra_exposed(headers, credentials)
    visible: list[list[str]] = []
    for name, value in headers:
        key = _lower(name)
        if key in _ALWAYS_EXPOSED or (key not in _FORBIDDEN_RESPONSE and key in extra):
            visible.append([name, value])
    return visible


def _extra_exposed(headers: list[tuple[str, str]], credentials: str) -> set[str]:
    extracted = _extract_list(headers, "access-control-expose-headers")
    if extracted is None or extracted == "failure":
        return set()
    if credentials != "include" and any(item == "*" for item in extracted):
        return {_lower(name) for name, _value in headers}
    return {_lower(item) for item in extracted}


def _unsafe_names(headers: list[tuple[str, str]]) -> list[str]:
    unsafe: list[str] = []
    potential: list[str] = []
    total = 0
    for name, value in headers:
        if _safelisted(name, value):
            potential.append(name)
            total += len(value.encode("latin-1"))
        else:
            unsafe.append(name)
    if total > 1024:
        unsafe.extend(potential)
    return sorted({_lower(name) for name in unsafe})


def _safelisted(name: str, value: str) -> bool:
    if len(value.encode("latin-1")) > 128:
        return False
    key = _lower(name)
    if key in {"accept", "content-type"}:
        if _unsafe_byte(value):
            return False
        if key == "content-type":
            return _mime_essence(value) in _SAFE_ESSENCES
        return True
    if key in {"accept-language", "content-language"}:
        return all(char in _LANGUAGE_BYTES for char in value)
    if key == "range":
        parsed = _single_range(value)
        return parsed is not None and parsed[0] is not None
    return False


def _unsafe_byte(value: str) -> bool:
    return any(ord(char) in _UNSAFE_BYTES for char in value)


def _mime_essence(value: str) -> str | None:
    text = value.strip("\t\n\r ")
    type_name, index = _token_at(text, 0)
    if not type_name or index >= len(text) or text[index] != "/":
        return None
    subtype, index = _token_at(text, index + 1)
    if not subtype:
        return None
    while index < len(text):
        while index < len(text) and text[index] in _HTTP_WS:
            index += 1
        if index >= len(text):
            break
        if text[index] != ";":
            return None
        index += 1
        while index < len(text) and text[index] in _HTTP_WS:
            index += 1
        _parameter, index = _token_at(text, index)
        if not _parameter:
            return None
        while index < len(text) and text[index] in _HTTP_WS:
            index += 1
        if index >= len(text) or text[index] != "=":
            return None
        index += 1
        while index < len(text) and text[index] in _HTTP_WS:
            index += 1
        if index >= len(text):
            return None
        if text[index] == '"':
            index += 1
            while index < len(text) and text[index] != '"':
                index += 2 if text[index] == "\\" else 1
            if index >= len(text):
                return None
            index += 1
            continue
        _token_value, index = _token_at(text, index)
        if not _token_value:
            return None
    return f"{type_name.lower()}/{subtype.lower()}"


def _token_at(text: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(text) and text[index] in _TOKEN:
        index += 1
    return text[start:index], index


def _single_range(value: str) -> tuple[int | None, int | None] | None:
    if not value.startswith("bytes"):
        return None
    index = 5
    if index >= len(value) or value[index] != "=":
        return None
    index += 1
    start_text, index = _digits(value, index)
    if index >= len(value) or value[index] != "-":
        return None
    end_text, index = _digits(value, index + 1)
    if index != len(value) or (start_text == "" and end_text == ""):
        return None
    start = int(start_text) if start_text else None
    end = int(end_text) if end_text else None
    if start is not None and end is not None and start > end:
        return None
    return start, end


def _digits(value: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(value) and value[index].isdigit():
        index += 1
    return value[start:index], index


def _extract_list(headers: list[tuple[str, str]], name: str) -> list[str] | None | str:
    matches = [value for header_name, value in headers if _lower(header_name) == name]
    if not matches:
        return None
    values: list[str] = []
    for match in matches:
        parsed = _parse_token_list(match)
        if parsed is None:
            return "failure"
        values.extend(parsed)
    return values


def _parse_token_list(value: str) -> list[str] | None:
    text = value.strip(" \t")
    if not text:
        return []
    items: list[str] = []
    for raw in text.split(","):
        item = raw.strip(" \t")
        if not item:
            continue
        if any(char not in _TOKEN for char in item):
            return None
        items.append(item)
    return items


def _authorize_preflight(
    method: str,
    request: list[tuple[str, str]],
    response: list[tuple[str, str]],
    *,
    credentials: str,
    unsafe: list[str],
    use_preflight_flag: bool,
) -> str:
    methods = _extract_list(response, "access-control-allow-methods")
    header_names = _extract_list(response, "access-control-allow-headers")
    if methods == "failure":
        return "method"
    if header_names == "failure":
        return "header"
    if methods is None and use_preflight_flag:
        methods = [method]
    method_listed = methods is not None and method in methods
    wildcard_method = methods is not None and "*" in methods
    if (
        not method_listed
        and method not in _SAFE_METHODS
        and (credentials == "include" or not wildcard_method)
    ):
        return "method"
    if any(_lower(name) == "authorization" for name, _value in request):
        if not _listed(header_names, "authorization"):
            return "authorization"
    wildcard_header = header_names is not None and any(item == "*" for item in header_names)
    for name in unsafe:
        if name == "authorization":
            continue
        if not _listed(header_names, name) and (credentials == "include" or not wildcard_header):
            return "header"
    return ""


def _listed(header_names: list[str] | None | str, name: str) -> bool:
    if not isinstance(header_names, list):
        return False
    return any(item.lower() == name for item in header_names)


def _max_age(headers: list[tuple[str, str]]) -> int:
    matches = [value for name, value in headers if _lower(name) == "access-control-max-age"]
    if len(matches) != 1:
        return _DEFAULT_MAX_AGE
    text = matches[0].strip(" \t")
    if not text or any(char not in "0123456789" for char in text):
        return _DEFAULT_MAX_AGE
    parsed = int(text)
    if parsed > _PREFLIGHT_MAX_AGE:
        return _PREFLIGHT_MAX_AGE
    return parsed
