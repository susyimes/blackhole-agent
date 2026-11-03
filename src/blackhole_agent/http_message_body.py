"""Frame an HTTP/1.1 message body and decode chunked transfer coding.

A line split cannot see a chunk boundary, because chunk data may contain
CRLF. ``urllib`` and ``http.client`` do not expose a buffer decoder that
reports how many bytes belonged to the body. This module follows RFC 9112
sections 6.3 and 7.1: chunk-size is hexadecimal, chunk extensions are
parsed and ignored, trailers are returned, and the consumed count stops
at the framing boundary.

A message that carries both Content-Length and Transfer-Encoding is
rejected. Differing Content-Length field values are rejected. A
transfer-coding list whose final coding is not a single ``chunked`` is
rejected. Responses that cannot have a body (HEAD, 1xx, 204, 304) consume
nothing.
"""

from __future__ import annotations

from typing import Sequence

_HEX = b"0123456789abcdefABCDEF"
_WS = b" \t"
_FORBIDDEN_TRAILERS = frozenset(
    {
        "authorization",
        "connection",
        "content-length",
        "content-range",
        "cookie",
        "expect",
        "host",
        "if-match",
        "if-modified-since",
        "if-none-match",
        "if-range",
        "if-unmodified-since",
        "max-forwards",
        "range",
        "set-cookie",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_NO_BODY_STATUS = frozenset({204, 304})
_MAX_CHUNK_LINE = 4096
_MAX_TRAILER_LINE = 8192
_MAX_TRAILERS = 64
_MAX_HEX_DIGITS = 16


def read_message_body(
    fields: Sequence[tuple[str, str]],
    data: bytes,
    *,
    role: str,
    method: str = "",
    status: int | None = None,
) -> dict[str, object]:
    """Return the body framing for one message.

    ``fields`` are header names and values already split on the colon.
    ``data`` is the bytes that follow the header section. ``consumed`` is
    how many of those bytes belong to this message. Bytes after that belong
    to the next message on the connection.

    On success ``ok`` is true and ``payload`` is the decoded body. On a
    framing error ``ok`` is false, ``error`` names the rule, and nothing
    is consumed. The connection should be closed.
    """

    _require_inputs(fields, data, role, method, status)
    names = _field_map(fields)
    if role == "response" and _response_has_no_body(method, status):
        return _ok("empty", b"", 0, (), ())
    has_length = "content-length" in names
    has_transfer = "transfer-encoding" in names
    if has_length and has_transfer:
        return _fail("length-and-transfer-encoding")
    if has_transfer:
        codings = _transfer_codings(names["transfer-encoding"])
        if codings is None or not codings or codings.count("chunked") != 1 or codings[-1] != "chunked":
            return _fail("transfer-encoding")
        if "identity" in codings:
            return _fail("transfer-encoding")
        decoded = decode_chunked(data)
        if not decoded["ok"]:
            return decoded
        decoded["codings"] = tuple(codings[:-1])
        return decoded
    if has_length:
        length = _content_length(names["content-length"])
        if isinstance(length, str):
            return _fail(length)
        if length > len(data):
            return _fail("truncated")
        return _ok("content-length", data[:length], length, (), ())
    if role == "request":
        return _ok("empty", b"", 0, (), ())
    return _ok("until-close", data, len(data), (), ())


def decode_chunked(data: bytes) -> dict[str, object]:
    """Decode one chunked-body from the start of ``data``.

    The result's ``consumed`` count includes the terminating CRLF and
    excludes every byte after it. A truncated or malformed body fails
    with nothing consumed.
    """

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("chunked body must be bytes")
    view = bytes(data)
    payload = bytearray()
    index = 0
    size = -1
    while size != 0:
        line, index, problem = _read_line(view, index, _MAX_CHUNK_LINE)
        if problem or line is None:
            return _fail(problem or "truncated")
        parsed = _chunk_size(line)
        if parsed is None:
            return _fail("chunk-size")
        size = parsed
        if size == 0:
            break
        end = index + size
        if end + 2 > len(view):
            return _fail("truncated")
        if view[end : end + 2] != b"\r\n":
            return _fail("chunk-data")
        payload.extend(view[index:end])
        index = end + 2
    trailers, index, problem = _trailers(view, index)
    if problem:
        return _fail(problem)
    return _ok("chunked", bytes(payload), index, trailers, ())


def encode_chunked(
    payload: bytes,
    trailers: Sequence[tuple[str, str]] = (),
) -> bytes:
    """Encode ``payload`` as one chunk, then a last-chunk and trailers."""

    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("chunked payload must be bytes")
    body = bytes(payload)
    parts: list[bytes] = []
    if body:
        parts.append(f"{len(body):x}".encode("ascii"))
        parts.append(b"\r\n")
        parts.append(body)
        parts.append(b"\r\n")
    parts.append(b"0\r\n")
    for name, value in trailers:
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("trailer fields must be strings")
        encoded_name = name.encode("ascii")
        if not encoded_name or any(not _is_tchar(byte) for byte in encoded_name):
            raise ValueError("trailer name must be a token")
        try:
            encoded_value = value.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError("trailer value must be latin-1") from exc
        if b"\r" in encoded_value or b"\n" in encoded_value:
            raise ValueError("trailer value must not contain CR or LF")
        parts.append(encoded_name + b": " + encoded_value + b"\r\n")
    parts.append(b"\r\n")
    return b"".join(parts)


def _ok(
    framing: str,
    payload: bytes,
    consumed: int,
    trailers: tuple[tuple[str, str], ...],
    codings: tuple[str, ...],
) -> dict[str, object]:
    return {
        "ok": True,
        "error": "",
        "framing": framing,
        "payload": payload,
        "consumed": consumed,
        "trailers": trailers,
        "codings": codings,
    }


def _fail(error: str) -> dict[str, object]:
    return {
        "ok": False,
        "error": error,
        "framing": "",
        "payload": b"",
        "consumed": 0,
        "trailers": (),
        "codings": (),
    }


def _require_inputs(
    fields: Sequence[tuple[str, str]],
    data: bytes,
    role: str,
    method: str,
    status: int | None,
) -> None:
    if role not in {"request", "response"}:
        raise ValueError("role must be request or response")
    if not isinstance(method, str):
        raise TypeError("method must be a string")
    if isinstance(status, bool) or (status is not None and not isinstance(status, int)):
        raise TypeError("status must be an integer")
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("message body must be bytes")
    for item in fields:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("header fields must be name-value pairs")
        if not isinstance(item[0], str) or not isinstance(item[1], str):
            raise TypeError("header fields must be strings")


def _field_map(fields: Sequence[tuple[str, str]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for name, value in fields:
        found.setdefault(name.lower(), []).append(value)
    return found


def _response_has_no_body(method: str, status: int | None) -> bool:
    if method.lower() == "head":
        return True
    if method.lower() == "connect" and status is not None and 200 <= status <= 299:
        return True
    if status is None:
        return False
    return status in _NO_BODY_STATUS or 100 <= status <= 199


def _content_length(values: Sequence[str]) -> int | str:
    stripped: list[str] = []
    for value in values:
        text = _strip_ows(value)
        if not text or any(char not in "0123456789" for char in text):
            return "content-length"
        stripped.append(text)
    if len(set(stripped)) != 1:
        return "conflicting-length"
    return int(stripped[0])


def _strip_ows(value: str) -> str:
    start = 0
    end = len(value)
    while start < end and value[start] in " \t":
        start += 1
    while end > start and value[end - 1] in " \t":
        end -= 1
    return value[start:end]


def _transfer_codings(values: Sequence[str]) -> list[str] | None:
    try:
        raw = ",".join(values).encode("latin-1")
    except UnicodeEncodeError:
        return None
    codings: list[str] = []
    index = 0
    limit = len(raw)
    while index < limit:
        index = _skip_ws(raw, index)
        if index >= limit:
            break
        if raw[index] == 0x2C:
            index += 1
            continue
        name, index = _token(raw, index)
        if name is None:
            return None
        while True:
            after_ws = _skip_ws(raw, index)
            if after_ws < limit and raw[after_ws] == 0x3B:
                index = _skip_ws(raw, after_ws + 1)
                parameter, index = _token(raw, index)
                if parameter is None:
                    return None
                equals = _skip_ws(raw, index)
                if equals >= limit or raw[equals] != 0x3D:
                    return None
                index = _skip_ws(raw, equals + 1)
                if index < limit and raw[index] == 0x22:
                    quoted, index = _quoted(raw, index)
                    if not quoted:
                        return None
                else:
                    token, index = _token(raw, index)
                    if token is None:
                        return None
                continue
            index = after_ws
            break
        codings.append(name.decode("ascii").lower())
        index = _skip_ws(raw, index)
        if index >= limit:
            break
        if raw[index] != 0x2C:
            return None
        index += 1
    return codings


def _chunk_size(line: bytes) -> int | None:
    if not line or line[0] not in _HEX:
        return None
    index = 0
    while index < len(line) and line[index] in _HEX:
        index += 1
    if index > _MAX_HEX_DIGITS:
        return None
    if not _chunk_ext(line, index):
        return None
    return int(line[:index], 16)


def _chunk_ext(line: bytes, index: int) -> bool:
    limit = len(line)
    while index < limit:
        after_ws = _skip_ws(line, index)
        if after_ws >= limit or line[after_ws] != 0x3B:
            return False
        index = _skip_ws(line, after_ws + 1)
        name, index = _token(line, index)
        if name is None:
            return False
        equals = _skip_ws(line, index)
        if equals < limit and line[equals] == 0x3D:
            index = _skip_ws(line, equals + 1)
            if index < limit and line[index] == 0x22:
                quoted, index = _quoted(line, index)
                if not quoted:
                    return False
            else:
                value, index = _token(line, index)
                if value is None:
                    return False
    return True


def _trailers(data: bytes, index: int) -> tuple[tuple[tuple[str, str], ...], int, str]:
    found: list[tuple[str, str]] = []
    while len(found) <= _MAX_TRAILERS:
        line, index, problem = _read_line(data, index, _MAX_TRAILER_LINE)
        if problem or line is None:
            return (), index, "truncated" if problem == "truncated" else "trailer"
        if line == b"":
            return tuple(found), index, ""
        if line[0] in _WS or b":" not in line:
            return (), index, "trailer"
        name, value = line.split(b":", 1)
        if not name or any(not _is_tchar(byte) for byte in name):
            return (), index, "trailer"
        decoded_name = name.decode("ascii")
        if decoded_name.lower() in _FORBIDDEN_TRAILERS:
            return (), index, "trailer"
        text = value.decode("latin-1")
        found.append((decoded_name, _strip_ows(text)))
    return (), index, "trailer"


def _read_line(data: bytes, index: int, limit: int) -> tuple[bytes | None, int, str]:
    end = data.find(b"\r\n", index, index + limit + 2)
    if end < 0:
        if len(data) - index > limit:
            return None, index, "chunk-size"
        return None, index, "truncated"
    line = data[index:end]
    if b"\n" in line or b"\r" in line:
        return None, index, "chunk-size"
    return line, end + 2, ""


def _quoted(data: bytes, index: int) -> tuple[bool, int]:
    if index >= len(data) or data[index] != 0x22:
        return False, index
    index += 1
    while index < len(data):
        byte = data[index]
        if byte == 0x5C:
            if index + 1 >= len(data) or not _quoted_pair(data[index + 1]):
                return False, index
            index += 2
            continue
        if byte == 0x22:
            return True, index + 1
        if _qdtext(byte):
            index += 1
            continue
        return False, index
    return False, index


def _token(data: bytes, index: int) -> tuple[bytes | None, int]:
    start = index
    while index < len(data) and _is_tchar(data[index]):
        index += 1
    if index == start:
        return None, start
    return data[start:index], index


def _skip_ws(data: bytes, index: int) -> int:
    while index < len(data) and data[index] in _WS:
        index += 1
    return index


def _is_tchar(byte: int) -> bool:
    if 0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A:
        return True
    return byte in b"!#$%&'*+-.^_`|~"


def _qdtext(byte: int) -> bool:
    return byte in (0x09, 0x20, 0x21) or 0x23 <= byte <= 0x5B or 0x5D <= byte <= 0x7E or 0x80 <= byte <= 0xFF


def _quoted_pair(byte: int) -> bool:
    return byte in (0x09, 0x20) or 0x21 <= byte <= 0x7E or 0x80 <= byte <= 0xFF
