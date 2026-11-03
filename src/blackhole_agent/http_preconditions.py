"""Evaluate origin-server HTTP preconditions for one selected representation.

RFC 9110 section 13.2.2 is an order, not a shared comparison. If-Match uses
the strong function and stops the request on failure. If-None-Match uses the
weak function, and a false result is 304 only for GET and HEAD. A date
validator is earlier-or-equal for If-Modified-Since and If-Unmodified-Since,
but If-Range is an exact match and only when that date is strong. A false
If-Range leaves the whole representation; it does not choose 304 or 416.

This is the origin-server decision. It does not store a response, and it
does not treat an already-applied change as success.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Sequence

from blackhole_agent.http_byte_range import satisfy_byte_ranges

_MAX_FIELD = 8192
_MAX_EMPTIES = 16
_NO_SELECTION = frozenset({"CONNECT", "OPTIONS", "TRACE"})
_TIME = re.compile(r"\d\d:\d\d:\d\d")
_OWS = " \t"


def evaluate_http_preconditions(
    method: str,
    fields: Sequence[tuple[str, str]],
    *,
    etag: str | None = None,
    last_modified: datetime | str | None = None,
    exists: bool | None = None,
    length: int | None = None,
    would_status: int | None = None,
    ranges_supported: bool = True,
    changed_twice: bool = False,
) -> dict[str, object]:
    """Return the status produced by the precondition order.

    ``etag`` and ``last_modified`` describe the selected representation.
    ``exists`` overrides the inference that a validator means a current
    representation. ``length`` lets a honored Range become 206 or 416.
    ``would_status`` is the status the same request would get without
    preconditions; anything other than 2xx or 412 is returned unchanged.
    ``changed_twice`` records that the representation changed twice during
    the second covered by a date validator, which makes that date weak.
    """

    if not isinstance(method, str):
        raise TypeError("precondition method must be a string")
    pairs = _pairs(fields)
    selected = None if etag is None else _one_tag(etag)
    modified = _modified(last_modified)
    if exists is None:
        exists = etag is not None or last_modified is not None
    elif type(exists) is not bool:
        raise TypeError("precondition exists must be a bool")
    if type(ranges_supported) is not bool or type(changed_twice) is not bool:
        raise TypeError("precondition flags must be bools")
    complete = None if length is None else _length(length)
    base = _would(would_status)

    if method in _NO_SELECTION or not _eligible(base):
        return _finish(base, ignored=True)

    match = _joined(pairs, "if-match")
    unmodified = _joined(pairs, "if-unmodified-since")
    none = _joined(pairs, "if-none-match")
    modified_since = _joined(pairs, "if-modified-since")
    if_range = _lines(pairs, "if-range")
    has_range = bool(_lines(pairs, "range"))

    if match is not None:
        condition = _if_match(match, exists=exists, selected=selected)
        if not condition:
            return _finish(412, applied="if-match", condition=False)
    elif unmodified is not None and modified is not None:
        stamp = _one_date(unmodified)
        if stamp is not None and _seconds(modified) > _seconds(stamp):
            return _finish(412, applied="if-unmodified-since", condition=False)

    if none is not None:
        condition = _if_none(none, exists=exists, selected=selected)
        if not condition:
            status = 304 if method in {"GET", "HEAD"} else 412
            return _finish(status, applied="if-none-match", condition=False)
    elif method in {"GET", "HEAD"} and modified_since is not None and modified is not None:
        stamp = _one_date(modified_since)
        if stamp is not None and _seconds(modified) <= _seconds(stamp):
            return _finish(304, applied="if-modified-since", condition=False)

    apply = False
    applied = ""
    condition: bool | None = None
    if method == "GET" and has_range and ranges_supported:
        if if_range:
            condition = len(if_range) == 1 and _range_matches(
                if_range[0],
                selected=selected,
                modified=modified,
                changed_twice=changed_twice,
            )
            if not condition:
                return _finish(base, applied="if-range", condition=False)
            apply = True
            applied = "if-range"
        else:
            apply = True
    if not apply or complete is None:
        return _finish(base, applied=applied, condition=condition, apply_range=apply)
    return _ranged(base, pairs, complete, applied=applied, condition=condition)


def _pairs(fields: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    if not isinstance(fields, Sequence) or isinstance(fields, (str, bytes, bytearray)):
        raise TypeError("precondition fields must be pairs")
    pairs: list[tuple[str, str]] = []
    for item in fields:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("precondition fields must be pairs")
        name, value = item
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("precondition fields must be pairs")
        pairs.append((name, value))
    return pairs


def _would(status: int | None) -> int:
    if status is None:
        return 200
    if type(status) is not int:
        raise TypeError("unchecked status must be an int")
    return status


def _eligible(status: int) -> bool:
    return 200 <= status <= 299 or status == 412


def _length(length: int) -> int:
    if type(length) is not int or length < 0:
        raise TypeError("representation length must be a non-negative int")
    return length


def _lines(fields: list[tuple[str, str]], name: str) -> list[str]:
    return [value.strip(_OWS) for key, value in fields if key.lower() == name]


def _joined(fields: list[tuple[str, str]], name: str) -> str | None:
    lines = _lines(fields, name)
    if not lines:
        return None
    return ", ".join(lines)


def _finish(
    status: int,
    *,
    applied: str = "",
    condition: bool | None = None,
    apply_range: bool = False,
    ignored: bool = False,
    ranges: list[list[int]] | None = None,
    content_range: str = "",
) -> dict[str, object]:
    return {
        "ok": True,
        "error": "",
        "status": status,
        "applied": applied,
        "condition": condition,
        "apply_range": apply_range,
        "ignored": ignored,
        "ranges": [] if ranges is None else ranges,
        "content_range": content_range,
    }


def _ranged(
    base: int,
    fields: list[tuple[str, str]],
    length: int,
    *,
    applied: str,
    condition: bool | None,
) -> dict[str, object]:
    ranged = satisfy_byte_ranges(length, fields, method="GET")
    decision = str(ranged["decision"])
    if decision not in {"partial", "unsatisfiable"}:
        return _finish(base, applied=applied, condition=condition)
    ranges = [list(item) for item in ranged["ranges"]]  # type: ignore[union-attr]
    return _finish(
        int(ranged["status"]),
        applied=applied,
        condition=condition,
        apply_range=True,
        ranges=ranges,
        content_range=str(ranged["content_range"]),
    )


def _if_match(value: str, *, exists: bool, selected: tuple[bool, str] | None) -> bool:
    if len(value) > _MAX_FIELD:
        return False
    if value.strip(_OWS) == "*":
        return exists
    tags = _tag_list(value)
    if tags is None:
        return False
    return any(_strong(tag, selected) for tag in tags)


def _if_none(value: str, *, exists: bool, selected: tuple[bool, str] | None) -> bool:
    if len(value) > _MAX_FIELD:
        return True
    if value.strip(_OWS) == "*":
        return not exists
    tags = _tag_list(value)
    if tags is None:
        return True
    return not any(_weak(tag, selected) for tag in tags)


def _range_matches(
    value: str,
    *,
    selected: tuple[bool, str] | None,
    modified: datetime | None,
    changed_twice: bool,
) -> bool:
    text = value.strip(_OWS)
    if text.startswith('"') or text.startswith('W/"'):
        return _strong(_one_tag(text), selected)
    stamp = _one_date(text)
    if stamp is None or modified is None or changed_twice:
        return False
    return _seconds(stamp) == _seconds(modified)


def _one_tag(value: str) -> tuple[bool, str] | None:
    tags = _tag_list(value.strip(_OWS))
    if tags is None or len(tags) != 1:
        return None
    return tags[0]


def _tag_list(value: str) -> tuple[tuple[bool, str], ...] | None:
    index = 0
    tags: list[tuple[bool, str]] = []
    empties = 0
    size = len(value)
    while index <= size:
        index = _skip_ows(value, index)
        if index >= size:
            break
        if value[index] == ",":
            empties += 1
            if empties > _MAX_EMPTIES:
                return None
            index += 1
            continue
        tag, index = _entity_tag(value, index)
        if tag is None:
            return None
        tags.append(tag)
        index = _skip_ows(value, index)
        if index >= size:
            break
        if value[index] != ",":
            return None
        index += 1
    if not tags:
        return None
    return tuple(tags)


def _entity_tag(value: str, index: int) -> tuple[tuple[bool, str] | None, int]:
    weak = False
    if value.startswith("W/", index):
        weak = True
        index += 2
    if index >= len(value) or value[index] != '"':
        return None, index
    index += 1
    start = index
    while index < len(value):
        character = value[index]
        code = ord(character)
        if character == '"':
            return (weak, value[start:index]), index + 1
        if code == 0x21 or 0x23 <= code <= 0x7E or 0x80 <= code <= 0xFF:
            index += 1
            continue
        return None, index
    return None, index


def _strong(left: tuple[bool, str] | None, right: tuple[bool, str] | None) -> bool:
    return left is not None and right is not None and not left[0] and not right[0] and left[1] == right[1]


def _weak(left: tuple[bool, str] | None, right: tuple[bool, str] | None) -> bool:
    return left is not None and right is not None and left[1] == right[1]


def _one_date(value: str) -> datetime | None:
    text = value.strip(_OWS)
    if not text or text.count(",") > 1 or len(_TIME.findall(text)) != 1:
        return None
    if len(text) > _MAX_FIELD:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _modified(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0)
    if isinstance(value, str):
        return _one_date(value)
    raise TypeError("last modified must be a datetime or HTTP-date")


def _seconds(moment: datetime) -> int:
    return int(moment.timestamp())


def _skip_ows(value: str, index: int) -> int:
    while index < len(value) and value[index] in _OWS:
        index += 1
    return index
