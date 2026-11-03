"""Satisfy an HTTP bytes range against a known representation length.

RFC 9110 sections 14.1.1, 14.1.2, and 14.2 split three outcomes that
clients often collapse. A range whose last position is before its first
is invalid, so the Range field is ignored and the response stays 200.
A bytes range that does not overlap the representation is unsatisfiable
and the response is 416 with ``Content-Range: bytes */length``. A set
that still contains one overlapping range is 206 and keeps only the
overlapping ranges, in the order they were requested, without coalescing.

Byte positions are inclusive. An absent or too-large last position
means the remainder of the representation. A suffix longer than the
representation is the whole representation. A suffix of zero is
unsatisfiable. On a zero-length representation the only satisfiable
form is a non-zero suffix, and that suffix selects the whole empty
representation. A unit other than bytes is not understood. Range
handling is defined for GET only. Repeated Range lines are combined
with comma SP, as field lines are, before the specifier is parsed.
Decimal numerals that do not fit in a signed 64-bit integer invalidate
the specifier instead of overflowing.
"""

from __future__ import annotations

from typing import Sequence

_INT64_MAX = 9223372036854775807
_MAX_DIGITS = 19
_MAX_RANGES = 64
_MAX_EMPTIES = 16
_MAX_VALUE = 8192
_OWS = " \t"
_TCHAR = frozenset(
    "!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


class _Invalid(Exception):
    pass


class _Excessive(Exception):
    pass


def satisfy_byte_ranges(
    length: int,
    fields: Sequence[tuple[str, str]],
    *,
    method: str = "GET",
) -> dict[str, object]:
    """Decide what a GET range request selects from ``length`` octets.

    ``fields`` are header names and values. Every ``Range`` line is
    combined in order. On a partial result ``ranges`` lists inclusive
    ``[first, last]`` pairs and ``parts`` lists each part's
    Content-Range. ``content_range`` is set only for a single part,
    because a multipart 206 must not carry Content-Range on the message.
    ``whole`` is true when a non-zero suffix selects a zero-length
    representation. ``decision`` is ``partial``, ``unsatisfiable``,
    ``ignored``, or ``absent``.
    """

    complete = _length(length)
    if not isinstance(method, str):
        raise TypeError("byte-range method must be a string")
    lines = _range_lines(fields)
    if not lines:
        return _result("absent", 200, complete, error="")
    if method != "GET":
        return _result("ignored", 200, complete, error="method")
    combined = ", ".join(lines)
    if len(combined) > _MAX_VALUE:
        return _result("ignored", 200, complete, error="excessive")
    try:
        unit, specs = _specifier(combined)
    except _Excessive:
        return _result("ignored", 200, complete, error="excessive")
    except _Invalid:
        return _result("ignored", 200, complete, error="invalid")
    if unit != "bytes":
        return _result("ignored", 200, complete, error="unit")
    selected, whole = _select(specs, complete)
    if whole:
        return _result("partial", 206, complete, whole=True)
    if not selected:
        return _result(
            "unsatisfiable",
            416,
            complete,
            error="unsatisfiable",
            content_range=f"bytes */{complete}",
        )
    parts = [f"bytes {start}-{end}/{complete}" for start, end in selected]
    return _result(
        "partial",
        206,
        complete,
        ranges=selected,
        parts=parts,
        content_range=parts[0] if len(parts) == 1 else "",
    )


def _length(length: int) -> int:
    if type(length) is not int:
        raise TypeError("representation length must be an int")
    if length < 0:
        raise TypeError("representation length must be zero or positive")
    return length


def _range_lines(fields: Sequence[tuple[str, str]]) -> list[str]:
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        raise TypeError("byte-range fields must be pairs")
    lines: list[str] = []
    for item in fields:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("byte-range fields must be pairs")
        name, value = item
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("byte-range fields must be pairs")
        if name.lower() != "range":
            continue
        lines.append(value.strip(_OWS))
    return lines


def _result(
    decision: str,
    status: int,
    complete: int,
    *,
    ranges: list[list[int]] | None = None,
    parts: list[str] | None = None,
    content_range: str = "",
    error: str = "",
    whole: bool = False,
) -> dict[str, object]:
    return {
        "decision": decision,
        "status": status,
        "ranges": [] if ranges is None else ranges,
        "whole": whole,
        "content_range": content_range,
        "parts": [] if parts is None else parts,
        "error": error,
        "complete": complete,
    }


def _specifier(value: str) -> tuple[str, list[tuple]]:
    index = _skip_ows(value, 0)
    token, index = _token(value, index)
    if index >= len(value) or value[index] != "=":
        raise _Invalid()
    index = _skip_ows(value, index + 1)
    specs = _range_set(value, index)
    return token.casefold(), specs


def _range_set(value: str, index: int) -> list[tuple]:
    specs: list[tuple] = []
    empties = 0
    limit = len(value)
    while index < limit:
        index = _skip_ows(value, index)
        if index >= limit:
            break
        if value[index] == ",":
            empties += 1
            if empties > _MAX_EMPTIES:
                raise _Invalid()
            index += 1
            continue
        spec, index = _range_spec(value, index)
        specs.append(spec)
        if len(specs) > _MAX_RANGES:
            raise _Excessive()
        index = _skip_ows(value, index)
        if index >= limit:
            break
        if value[index] != ",":
            raise _Invalid()
        index += 1
    if not specs:
        raise _Invalid()
    return specs


def _range_spec(value: str, index: int) -> tuple[tuple, int]:
    if value[index] == "-":
        parsed = _digits(value, index + 1)
        if parsed is not None:
            number, nxt = parsed
            if _boundary(value, nxt):
                return ("suffix", number), nxt
        raise _Invalid()
    parsed = _digits(value, index)
    if parsed is not None:
        first, nxt = parsed
        if nxt < len(value) and value[nxt] == "-":
            nxt += 1
            if nxt < len(value) and value[nxt].isdigit():
                spanned = _digits(value, nxt)
                if spanned is None:
                    raise _Invalid()
                last, nxt = spanned
                if not _boundary(value, nxt):
                    raise _Invalid()
                if last < first:
                    raise _Invalid()
                return ("int", first, last), nxt
            if _boundary(value, nxt):
                return ("int", first, None), nxt
    raise _Invalid()


def _select(specs: list[tuple], length: int) -> tuple[list[list[int]], bool]:
    selected: list[list[int]] = []
    whole = False
    for spec in specs:
        if spec[0] == "suffix":
            suffix = int(spec[1])
            if suffix == 0:
                continue
            if length == 0:
                whole = True
                continue
            if suffix >= length:
                selected.append([0, length - 1])
            else:
                selected.append([length - suffix, length - 1])
            continue
        first = int(spec[1])
        if first >= length:
            continue
        last = spec[2]
        end = length - 1 if last is None or int(last) >= length else int(last)
        selected.append([first, end])
    if selected:
        whole = False
    return selected, whole


def _token(value: str, index: int) -> tuple[str, int]:
    start = index
    limit = len(value)
    while index < limit and value[index] in _TCHAR:
        index += 1
    if index == start:
        raise _Invalid()
    return value[start:index], index


def _digits(value: str, index: int) -> tuple[int, int] | None:
    start = index
    limit = len(value)
    while index < limit and value[index].isdigit():
        index += 1
        if index - start > _MAX_DIGITS:
            raise _Invalid()
    if index == start:
        return None
    number = int(value[start:index])
    if number > _INT64_MAX:
        raise _Invalid()
    return number, index


def _boundary(value: str, index: int) -> bool:
    return index >= len(value) or value[index] == "," or value[index] in _OWS


def _skip_ows(value: str, index: int) -> int:
    limit = len(value)
    while index < limit and value[index] in _OWS:
        index += 1
    return index
