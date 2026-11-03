"""Read one HTTP request from the bytes waiting on a connection.

The body framer only sees fields that have already been split on a colon.
It cannot tell a space before that colon from a real field, and it never
sees an obsolete line fold or a bare line feed. RFC 9112 forbids the space,
requires CRLF, and tells a recipient to reject an obsolete fold or to
unfold it before interpretation. This reader rejects the fold.

A chunked body, a conflicting Content-Length, and trailers stay with
``read_message_body``. ``consumed`` counts the header section and the
framed body, so the following bytes are the next request.

Python's ``BaseHTTPRequestHandler`` accepts the space, unfolds the fold
into Content-Length, and accepts a bare line feed. Those three inputs
are rejected here.
"""

from __future__ import annotations

from blackhole_agent.http_message_body import read_message_body

_MAX_LINE = 8000
_MAX_FIELDS = 100
_MAX_SECTION = 65536
_WS = frozenset({0x20, 0x09})


def read_http_request(data: bytes | bytearray) -> dict[str, object]:
    """Return one request message and how many bytes it consumed.

    On success ``ok`` is true, ``payload`` is the framed body, and
    ``consumed`` includes the header section. Bytes after that belong to
    the next message. On a rejected or incomplete message ``ok`` is false,
    ``error`` names the rule, and nothing is consumed.
    """

    if isinstance(data, bytearray):
        data = bytes(data)
    elif not isinstance(data, bytes):
        raise TypeError("request must be bytes")

    index = _skip_leading_crlf(data)
    section_start = index
    line, index, problem = _line(data, index, _MAX_LINE)
    if problem:
        return _fail(_line_error(problem, "request-line"))
    assert line is not None
    parsed = _request_line(line)
    if isinstance(parsed, str):
        return _fail(parsed)
    method, target, version = parsed

    fields: list[tuple[str, str]] = []
    while True:
        if index - section_start > _MAX_SECTION:
            return _fail("field-section")
        line, index, problem = _line(data, index, _MAX_LINE)
        if problem:
            return _fail(_line_error(problem, "field"))
        assert line is not None
        if line == b"":
            break
        if len(fields) >= _MAX_FIELDS:
            return _fail("field-count")
        field = _field(line)
        if isinstance(field, str):
            return _fail(field)
        fields.append(field)
    if index - section_start > _MAX_SECTION:
        return _fail("field-section")

    host_error = _host(version, fields)
    if host_error:
        return _fail(host_error)

    framed = read_message_body(tuple(fields), data[index:], role="request", method=method)
    if not framed["ok"]:
        return _fail(str(framed["error"]))
    return {
        "ok": True,
        "error": "",
        "method": method,
        "target": target,
        "version": version,
        "fields": tuple(fields),
        "payload": framed["payload"],
        "consumed": index + int(framed["consumed"]),
        "trailers": framed["trailers"],
        "codings": framed["codings"],
        "framing": framed["framing"],
    }


def _fail(error: str) -> dict[str, object]:
    return {
        "ok": False,
        "error": error,
        "method": "",
        "target": "",
        "version": "",
        "fields": (),
        "payload": b"",
        "consumed": 0,
        "trailers": (),
        "codings": (),
        "framing": "",
    }


def _skip_leading_crlf(data: bytes) -> int:
    index = 0
    limit = len(data)
    while index + 1 < limit and data[index] == 0x0D and data[index + 1] == 0x0A:
        index += 2
    return index


def _line(data: bytes, index: int, limit: int) -> tuple[bytes | None, int, str]:
    size = len(data)
    cursor = index
    seen = 0
    while cursor < size:
        if seen > limit:
            return None, index, "too-long"
        byte = data[cursor]
        if byte == 0x0A:
            return None, index, "line-ending"
        if byte == 0x0D:
            if cursor + 1 >= size:
                return None, index, "truncated"
            if data[cursor + 1] != 0x0A:
                return None, index, "line-ending"
            if seen > limit:
                return None, index, "too-long"
            return data[index:cursor], cursor + 2, ""
        cursor += 1
        seen += 1
    if seen > limit:
        return None, index, "too-long"
    return None, index, "truncated"


def _line_error(problem: str, kind: str) -> str:
    if problem == "truncated":
        return "truncated"
    if problem == "line-ending":
        return "line-ending"
    return kind


def _request_line(line: bytes) -> tuple[str, str, str] | str:
    if not line or line[0] in _WS or b"\t" in line:
        return "request-line"
    parts = line.split(b" ")
    if len(parts) != 3 or any(not part for part in parts):
        return "request-line"
    method_raw, target_raw, version_raw = parts
    if any(not _is_tchar(byte) for byte in method_raw):
        return "request-line"
    version = _version(version_raw)
    if version is None:
        return "version"
    if not _target_ok(method_raw, target_raw):
        return "target"
    return method_raw.decode("ascii"), target_raw.decode("ascii"), version


def _version(token: bytes) -> str | None:
    if token == b"HTTP/1.1":
        return "1.1"
    if token == b"HTTP/1.0":
        return "1.0"
    return None


def _target_ok(method: bytes, target: bytes) -> bool:
    if not target or any(byte < 0x21 or byte > 0x7E for byte in target):
        return False
    if target == b"*":
        return method == b"OPTIONS"
    if method == b"CONNECT":
        return b"/" not in target and b"://" not in target
    if target.startswith(b"/"):
        return True
    scheme, separator, rest = target.partition(b"://")
    if not separator or not scheme or not rest or not scheme[:1].isalpha():
        return False
    return all(
        byte in b"+-." or 0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A for byte in scheme
    )


def _field(line: bytes) -> tuple[str, str] | str:
    if line[:1] in (b" ", b"\t"):
        return "obsolete-fold"
    colon = line.find(b":")
    if colon <= 0:
        return "field"
    name = line[:colon]
    if any(byte in _WS for byte in name):
        return "field-whitespace"
    if any(not _is_tchar(byte) for byte in name):
        return "field"
    value = line[colon + 1 :]
    start = 0
    end = len(value)
    while start < end and value[start] in _WS:
        start += 1
    while end > start and value[end - 1] in _WS:
        end -= 1
    body = value[start:end]
    for byte in body:
        if byte in _WS or 0x21 <= byte <= 0x7E or 0x80 <= byte <= 0xFF:
            continue
        return "field"
    return name.decode("ascii"), body.decode("latin-1")


def _host(version: str, fields: list[tuple[str, str]]) -> str:
    found = [value for name, value in fields if name.lower() == "host"]
    if len(found) > 1:
        return "host"
    if version == "1.1" and len(found) != 1:
        return "host"
    return ""


def _is_tchar(byte: int) -> bool:
    if 0x30 <= byte <= 0x39 or 0x41 <= byte <= 0x5A or 0x61 <= byte <= 0x7A:
        return True
    return byte in b"!#$%&'*+-.^_`|~"
