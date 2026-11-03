"""Decode HTTP content-codings on an already framed payload.

RFC 9110 section 8.4.1 lists content-codings in the order they were
applied, so a ``deflate, gzip`` chain is inflated from the outside.
``gzip`` is RFC 1952. ``deflate`` is the zlib wrapper in RFC 1950, not a
raw deflate stream. ``x-gzip`` is the historical alias of ``gzip``.
``identity`` is reserved, and ``chunked`` is a transfer-coding. A
parameter, an unknown token, a truncated member, or trailing junk fails
closed. ``Transfer-Encoding`` is ignored; message framing owns it.

``gzip.decompress(b"")`` returns empty bytes. An empty body that claims a
coding is still corrupt, because no coding member is present.
"""

from __future__ import annotations

import gzip
import io
import zlib
from typing import Sequence

_MAX_OUTPUT = 8 * 1024 * 1024
_CHUNK = 64 * 1024
_GZIP = frozenset({"gzip", "x-gzip"})
_SUPPORTED = _GZIP | {"deflate"}


class _Corrupt(Exception):
    pass


class _Expanded(Exception):
    pass


def decode_content_encoding(
    payload: bytes,
    fields: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """Return the representation after reversing ``Content-Encoding``.

    On success ``ok`` is true, ``payload`` is the decoded bytes, and
    ``codings`` lists the names in application order. On failure ``ok`` is
    false, ``payload`` is empty, and ``error`` is ``content-coding``,
    ``unsupported``, ``corrupt``, or ``expanded``.
    """

    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("content-coded payload must be bytes")
    codings, problem = _codings(fields)
    if problem:
        return _fail(problem)
    decoded = bytes(payload)
    if not codings:
        return _ok(decoded, ())
    try:
        for coding in reversed(codings):
            if coding not in _SUPPORTED:
                return _fail("unsupported")
            decoded = _inflate(coding, decoded)
    except _Corrupt:
        return _fail("corrupt")
    except _Expanded:
        return _fail("expanded")
    return _ok(decoded, tuple(codings))


def _ok(payload: bytes, codings: tuple[str, ...]) -> dict[str, object]:
    return {"ok": True, "payload": payload, "codings": codings, "error": ""}


def _fail(error: str) -> dict[str, object]:
    return {"ok": False, "payload": b"", "codings": (), "error": error}


def _codings(fields: Sequence[tuple[str, str]]) -> tuple[list[str], str]:
    found: list[str] = []
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        raise TypeError("content-coding fields must be pairs")
    for item in fields:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("content-coding fields must be pairs")
        name, value = item
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("content-coding fields must be pairs")
        if name.lower() != "content-encoding":
            continue
        parsed, problem = _parse_codings(value)
        if problem:
            return [], problem
        found.extend(parsed)
    return found, ""


def _parse_codings(value: str) -> tuple[list[str], str]:
    codings: list[str] = []
    index = 0
    limit = len(value)
    while index < limit:
        index = _skip_ows(value, index)
        if index >= limit:
            break
        if value[index] == ",":
            index += 1
            continue
        start = index
        while index < limit and _is_tchar(value[index]):
            index += 1
        if index == start:
            return [], "content-coding"
        codings.append(value[start:index].lower())
        index = _skip_ows(value, index)
        if index < limit and value[index] == ";":
            return [], "content-coding"
        if index >= limit:
            break
        if value[index] != ",":
            return [], "content-coding"
        index += 1
    return codings, ""


def _inflate(coding: str, data: bytes) -> bytes:
    if not data:
        raise _Corrupt()
    if coding in _GZIP:
        return _gunzip(data)
    return _deflate(data)


def _gunzip(data: bytes) -> bytes:
    source = io.BytesIO(data)
    chunks: list[bytes] = []
    total = 0
    try:
        with gzip.GzipFile(fileobj=source) as handle:
            while True:
                block = handle.read(_CHUNK)
                if not block:
                    break
                total += len(block)
                if total > _MAX_OUTPUT:
                    raise _Expanded()
                chunks.append(block)
    except _Expanded:
        raise
    except (OSError, EOFError, zlib.error) as exc:
        raise _Corrupt() from exc
    return b"".join(chunks)


def _deflate(data: bytes) -> bytes:
    try:
        decoder = zlib.decompressobj()
        out = decoder.decompress(data, _MAX_OUTPUT + 1)
        if decoder.unconsumed_tail:
            raise _Expanded()
        out += decoder.flush()
    except _Expanded:
        raise
    except zlib.error as exc:
        raise _Corrupt() from exc
    if decoder.unused_data or len(out) > _MAX_OUTPUT:
        if len(out) > _MAX_OUTPUT:
            raise _Expanded()
        raise _Corrupt()
    return out


def _skip_ows(value: str, index: int) -> int:
    while index < len(value) and value[index] in " \t":
        index += 1
    return index


def _is_tchar(character: str) -> bool:
    if "0" <= character <= "9" or "A" <= character <= "Z" or "a" <= character <= "z":
        return True
    return character in "!#$%&'*+-.^_`|~"
