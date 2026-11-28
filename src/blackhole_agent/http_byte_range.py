"""Select inclusive HTTP byte ranges for a representation of known length (RFC 9110 §14)."""

from __future__ import annotations

import re
from typing import Sequence

_INT64_MAX = (1 << 63) - 1
_MAX_RANGES = 64
_MAX_EMPTIES = 16
_MAX_VALUE = 8192
_OWS = " \t"
_UNIT = re.compile(r"[!#$%&'*+.^_`|~A-Za-z0-9-]+")
_SPAN = re.compile(r"([0-9]{0,19})-([0-9]{0,19})")


def _parse(value: str) -> tuple[str, list[tuple[int | None, int | None]]]:
    unit, equals, raw = value.partition("=")
    if not equals or not _UNIT.fullmatch(unit):
        raise ValueError("invalid")
    spans = []
    empty_count = 0
    # A trailing comma terminates the preceding item, even when that item is empty.
    for item in raw.rstrip(_OWS).removesuffix(",").split(","):
        item = item.strip(_OWS)
        if not item:
            empty_count += 1
            if empty_count > _MAX_EMPTIES:
                raise ValueError("invalid")
            continue
        match = _SPAN.fullmatch(item)
        if not match or item == "-":
            raise ValueError("invalid")
        first, last = (int(number) if number else None for number in match.groups())
        if first is not None and last is not None and last < first:
            raise ValueError("invalid")
        if (first or 0) > _INT64_MAX or (last or 0) > _INT64_MAX:
            raise ValueError("invalid")
        spans.append((first, last))
        if len(spans) > _MAX_RANGES:
            raise ValueError("excessive")
    if not spans:
        raise ValueError("invalid")
    return unit.lower(), spans


def satisfy_byte_ranges(
    length: int, fields: Sequence[tuple[str, str]], *, method: str = "GET",
) -> dict[str, object]:
    """Return the status, inclusive intervals and Content-Range for a Range field set."""
    if type(length) is not int or length < 0:
        raise TypeError("representation length must be a nonnegative int")
    if not isinstance(method, str):
        raise TypeError("byte-range method must be a string")
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        raise TypeError("byte-range fields must be pairs")
    lines = []
    for pair in fields:
        if not isinstance(pair, tuple) or len(pair) != 2 or not all(isinstance(part, str) for part in pair):
            raise TypeError("byte-range fields must be pairs")
        name, value = pair
        if name.lower() == "range":
            lines.append(value.strip(_OWS))

    result = dict(decision="absent", status=200, ranges=[], parts=[], whole=False,
                  content_range="", complete=length, error="")
    if not lines:
        return result
    if method != "GET":
        return {**result, "decision": "ignored", "error": "method"}
    combined = ", ".join(lines)
    if len(combined) > _MAX_VALUE:
        return {**result, "decision": "ignored", "error": "excessive"}
    try:
        unit, spans = _parse(combined)
    except ValueError as exc:
        return {**result, "decision": "ignored", "error": str(exc)}
    if unit != "bytes":
        return {**result, "decision": "ignored", "error": "unit"}

    ranges = []
    whole_empty = False
    for first, last in spans:
        if first is None:
            if last:
                if length:
                    ranges.append([max(0, length - last), length - 1])
                else:
                    whole_empty = True
        elif first < length:
            end = length - 1 if last is None else min(last, length - 1)
            ranges.append([first, end])

    if not ranges and not whole_empty:
        return {**result, "decision": "unsatisfiable", "status": 416, "error": "unsatisfiable",
                "content_range": f"bytes */{length}"}
    parts = [f"bytes {start}-{end}/{length}" for start, end in ranges]
    return {**result, "decision": "partial", "status": 206, "ranges": ranges, "parts": parts,
            "whole": whole_empty, "content_range": parts[0] if len(parts) == 1 else ""}
