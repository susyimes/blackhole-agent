"""Decide whether a stored HTTP response may be served.

A cache that prefers Expires over max-age, or that treats the Age header as
optional, serves a stale response or discards a fresh one. This decision
follows RFC 9111 sections 4.2 and 5.2 for one stored response: corrected age,
explicit freshness, the ten-percent Last-Modified heuristic, and the request
constraints that refuse or accept that stored response. It does not fetch,
store, or seal anything.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping


def cache_decision(
    response_headers: Mapping[str, str],
    *,
    request_headers: Mapping[str, str] | None = None,
    request_time: datetime,
    response_time: datetime,
    now: datetime,
    shared: bool = True,
) -> dict[str, object]:
    """Return the serving decision for one stored response at ``now``.

    ``disposition`` is ``fresh``, ``stale``, ``accepted-stale``,
    ``revalidate``, or ``uncacheable``. ``serve`` is true only when the
    stored response may satisfy the request without contacting the origin.
    ``omit`` lists fields a qualified ``no-cache`` or ``private`` directive
    removes from a response that is still served.
    """

    response = _directives(_header(response_headers, "cache-control"))
    request = _directives(_header(request_headers or {}, "cache-control"))
    received, sent, moment = _aware(response_time), _aware(request_time), _aware(now)
    date_value = _http_date(_header(response_headers, "date")) or received
    current_age = _current_age(
        response_headers,
        date_value=date_value,
        request_time=sent,
        response_time=received,
        now=moment,
    )
    lifetime = _freshness_lifetime(
        response_headers,
        response,
        date_value=date_value,
        shared=shared,
    )
    omit = _omit_fields(response, shared=shared)
    unqualified_no_cache = _unqualified(response, "no-cache") or _pragma_no_cache(response_headers)
    no_store = "no-store" in response
    private_blocked = shared and _unqualified(response, "private")
    if no_store or private_blocked:
        return _result("uncacheable", False, current_age, lifetime, [])
    if "no-cache" in request or unqualified_no_cache:
        return _result("revalidate", False, current_age, lifetime, [])

    remaining = lifetime - current_age
    min_fresh = _delta(request.get("min-fresh")) if "min-fresh" in request else None
    if min_fresh is not None and remaining < min_fresh:
        return _result("stale", False, current_age, lifetime, [])
    request_max_age = _delta(request.get("max-age")) if "max-age" in request else None
    if lifetime > current_age:
        if request_max_age is not None and current_age > request_max_age:
            return _result("stale", False, current_age, lifetime, [])
        return _result("fresh", True, current_age, lifetime, omit)
    if "must-revalidate" in response:
        return _result("revalidate", False, current_age, lifetime, [])
    staleness = current_age - lifetime
    if "max-stale" in request and _max_stale_covers(request.get("max-stale"), staleness):
        return _result("accepted-stale", True, current_age, lifetime, omit)
    return _result("stale", False, current_age, lifetime, [])


def _result(
    disposition: str,
    serve: bool,
    current_age: int,
    freshness_lifetime: int,
    omit: list[str],
) -> dict[str, object]:
    return {
        "disposition": disposition,
        "serve": serve,
        "current_age": current_age,
        "freshness_lifetime": freshness_lifetime,
        "omit": omit,
    }


def _current_age(
    headers: Mapping[str, str],
    *,
    date_value: datetime,
    request_time: datetime,
    response_time: datetime,
    now: datetime,
) -> int:
    # RFC 9111 section 4.2.3. apparent_age is receipt minus Date, never negative.
    # corrected_age_value adds the transfer delay to the Age header, and the
    # stored response then grows by resident time.
    apparent_age = max(0, _seconds(response_time) - _seconds(date_value))
    response_delay = max(0, _seconds(response_time) - _seconds(request_time))
    corrected_age_value = _age_value(headers) + response_delay
    corrected_initial_age = max(apparent_age, corrected_age_value)
    resident_time = max(0, _seconds(now) - _seconds(response_time))
    return corrected_initial_age + resident_time


def _freshness_lifetime(
    headers: Mapping[str, str],
    directives: dict[str, str | None],
    *,
    date_value: datetime,
    shared: bool,
) -> int:
    if shared and "s-maxage" in directives:
        shared_lifetime = _delta(directives.get("s-maxage"))
        if shared_lifetime is not None:
            return shared_lifetime
    if "max-age" in directives:
        explicit = _delta(directives.get("max-age"))
        if explicit is not None:
            return explicit
    expires = _http_date(_header(headers, "expires"))
    if expires is not None:
        return _seconds(expires) - _seconds(date_value)
    modified = _http_date(_header(headers, "last-modified"))
    if modified is None:
        return 0
    delta = _seconds(date_value) - _seconds(modified)
    if delta <= 0:
        return 0
    return (delta * 10) // 100


def _omit_fields(directives: dict[str, str | None], *, shared: bool) -> list[str]:
    names: list[str] = []
    if not _unqualified(directives, "no-cache"):
        names.extend(_field_names(directives.get("no-cache")) if "no-cache" in directives else [])
    if shared and not _unqualified(directives, "private"):
        names.extend(_field_names(directives.get("private")) if "private" in directives else [])
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return ordered


def _unqualified(directives: dict[str, str | None], name: str) -> bool:
    return name in directives and not _field_names(directives.get(name))


def _pragma_no_cache(headers: Mapping[str, str]) -> bool:
    if _has_header(headers, "cache-control"):
        return False
    for part in _split_directives(_header(headers, "pragma")):
        token = part.split("=", 1)[0].strip().lower()
        if token == "no-cache":
            return True
    return False


def _max_stale_covers(argument: str | None, staleness: int) -> bool:
    if argument is None or argument == "":
        return True
    allowed = _delta(argument)
    return allowed is not None and staleness <= allowed


def _age_value(headers: Mapping[str, str]) -> int:
    parsed = _delta(_header(headers, "age").strip())
    return parsed if parsed is not None else 0


def _delta(argument: str | None) -> int | None:
    if argument is None:
        return None
    text = argument.strip()
    if not text.isdigit():
        return None
    return int(text)


def _field_names(argument: str | None) -> list[str]:
    if argument is None:
        return []
    return [part.strip() for part in argument.split(",") if part.strip()]


def _directives(value: str) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for part in _split_directives(value):
        if "=" in part:
            raw_name, raw_argument = part.split("=", 1)
            argument: str | None = _unquote(raw_argument.strip())
        else:
            raw_name, argument = part, None
        name = raw_name.strip().lower()
        if not name or name in found:
            continue
        found[name] = argument
    return found


def _split_directives(value: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    quoted = False
    escaped = False
    for character in value:
        if escaped:
            buffer.append(character)
            escaped = False
            continue
        if quoted and character == "\\":
            buffer.append(character)
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            buffer.append(character)
            continue
        if character == "," and not quoted:
            text = "".join(buffer).strip()
            if text:
                parts.append(text)
            buffer = []
            continue
        buffer.append(character)
    text = "".join(buffer).strip()
    if text:
        parts.append(text)
    return parts


def _unquote(value: str) -> str:
    if len(value) < 2 or value[0] != '"' or value[-1] != '"':
        return value
    inner = value[1:-1]
    decoded: list[str] = []
    escaped = False
    for character in inner:
        if escaped:
            decoded.append(character)
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        decoded.append(character)
    return "".join(decoded)


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name:
            return str(value)
    return ""


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    return any(key.lower() == name for key in headers)


def _http_date(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _seconds(moment: datetime) -> int:
    return int(moment.timestamp())
