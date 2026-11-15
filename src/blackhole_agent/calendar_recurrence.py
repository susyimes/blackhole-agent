"""Expand an iCalendar recurrence rule into civil occurrence timestamps.

RFC 5545 recurrence is not "add the interval and clamp." A monthly 31st
skips a short month and does not spend COUNT on the skip. A yearly
February 29 lands only on leap days. BYSETPOS chooses inside one frequency
period, so the last weekday of a month is not the last weekday of the whole
set. A weekly interval keeps every requested weekday inside each selected
week. A DTSTART that does not match the rule is not inserted.

Date-times are civil clock values. A trailing ``Z`` is preserved and must
agree between DTSTART and UNTIL. Leap seconds are not generated. BYWEEKNO
and BYYEARDAY are rejected instead of expanded incorrectly.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

_STAMP = re.compile(r"\A(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})(Z)?)?\Z")
_BYDAY = re.compile(r"\A([+-]?\d+)?([A-Za-z]{2})\Z")
_WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_WEEKDAY_NAME = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_FREQUENCIES = frozenset({"DAILY", "WEEKLY", "MONTHLY", "YEARLY"})
_UNSUPPORTED = frozenset({"BYWEEKNO", "BYYEARDAY"})


@dataclass(frozen=True)
class _Stamp:
    value: date | datetime
    utc: bool
    date_only: bool


@dataclass(frozen=True)
class _Rule:
    freq: str
    interval: int
    count: int | None
    until: date | datetime | None
    wkst: int
    bymonth: tuple[int, ...] | None
    bymonthday: tuple[int, ...] | None
    byday: tuple[tuple[str, int | None], ...] | None
    bysetpos: tuple[int, ...] | None
    byhour: tuple[int, ...] | None
    byminute: tuple[int, ...] | None
    bysecond: tuple[int, ...] | None


def expand_recurrence(dtstart: str, rrule: str, *, limit: int = 256) -> dict[str, object]:
    """Return the bounded occurrence set for one DTSTART and one RRULE.

    ``occurrences`` uses the same shape as ``dtstart``. ``truncated`` is true
    when ``limit`` stops the set before COUNT or UNTIL does. ``exhausted`` is
    true when the rule cannot produce enough matches, such as the 30th of
    February. COUNT and UNTIL together are rejected.
    """

    if not isinstance(dtstart, str):
        raise TypeError("DTSTART must be a string")
    if not isinstance(rrule, str):
        raise TypeError("RRULE must be a string")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise TypeError("limit must be a positive integer")
    start = _parse_stamp(dtstart)
    if start is None:
        return _fail("invalid DTSTART")
    parsed = _parse_rule(rrule, start)
    if isinstance(parsed, str):
        return _fail(parsed)
    return _expand(start, parsed, limit)


def _fail(message: str) -> dict[str, object]:
    return {"ok": False, "error": message, "occurrences": []}


def _parse_stamp(text: str) -> _Stamp | None:
    match = _STAMP.fullmatch(text.strip())
    if match is None:
        return None
    year, month, day = (int(match.group(index)) for index in (1, 2, 3))
    if match.group(4) is None:
        try:
            return _Stamp(date(year, month, day), False, True)
        except ValueError:
            return None
    hour, minute, second = (int(match.group(index)) for index in (4, 5, 6))
    try:
        value = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None
    return _Stamp(value, match.group(7) == "Z", False)


def _parse_rule(rrule: str, start: _Stamp) -> _Rule | str:
    text = rrule.strip()
    if text.upper().startswith("RRULE:"):
        text = text[6:].strip()
    if not text:
        return "missing FREQ"
    parts: dict[str, str] = {}
    for piece in text.split(";"):
        if not piece.strip() or "=" not in piece:
            return "invalid recurrence part"
        name, value = piece.split("=", 1)
        name = name.strip().upper()
        value = value.strip()
        if not name or not value or name in parts:
            return "invalid recurrence part"
        if name in _UNSUPPORTED:
            return f"unsupported recurrence part {name}"
        parts[name] = value
    freq = parts.pop("FREQ", "").upper()
    if not freq:
        return "missing FREQ"
    if freq not in _FREQUENCIES:
        return "invalid FREQ"
    interval = _one_int(parts.pop("INTERVAL", "1"), 1, 999_999)
    if interval is None:
        return "invalid INTERVAL"
    count_text = parts.pop("COUNT", None)
    until_text = parts.pop("UNTIL", None)
    if count_text is not None and until_text is not None:
        return "COUNT and UNTIL are mutually exclusive"
    count = None
    if count_text is not None:
        count = _one_int(count_text, 1, 100_000)
        if count is None:
            return "invalid COUNT"
    until = None
    if until_text is not None:
        parsed_until = _parse_stamp(until_text)
        if parsed_until is None:
            return "invalid UNTIL"
        if parsed_until.date_only != start.date_only or parsed_until.utc != start.utc:
            return "UNTIL must match the DTSTART form"
        until = parsed_until.value
    wkst_text = parts.pop("WKST", "MO").upper()
    if wkst_text not in _WEEKDAY:
        return "invalid WKST"
    bymonth = _int_list(parts.pop("BYMONTH", None), 1, 12, False)
    if bymonth is False:
        return "invalid BYMONTH"
    bymonthday = _int_list(parts.pop("BYMONTHDAY", None), 1, 31, True)
    if bymonthday is False:
        return "invalid BYMONTHDAY"
    byday = _parse_byday(parts.pop("BYDAY", None), freq)
    if isinstance(byday, str):
        return byday
    bysetpos = _int_list(parts.pop("BYSETPOS", None), 1, 366, True)
    if bysetpos is False:
        return "invalid BYSETPOS"
    byhour = _int_list(parts.pop("BYHOUR", None), 0, 23, False)
    byminute = _int_list(parts.pop("BYMINUTE", None), 0, 59, False)
    bysecond = _int_list(parts.pop("BYSECOND", None), 0, 59, False)
    if byhour is False or byminute is False or bysecond is False:
        return "invalid time part"
    if start.date_only and (byhour or byminute or bysecond):
        return "time parts require a date-time DTSTART"
    if parts:
        return "invalid recurrence part"
    return _Rule(
        freq,
        interval,
        count,
        until,
        _WEEKDAY[wkst_text],
        bymonth,
        bymonthday,
        byday,
        bysetpos,
        byhour,
        byminute,
        bysecond,
    )


def _one_int(text: str, low: int, high: int) -> int | None:
    if not re.fullmatch(r"[+]?\d+", text):
        return None
    value = int(text)
    if value < low or value > high:
        return None
    return value


def _int_list(text: str | None, low: int, high: int, signed: bool) -> tuple[int, ...] | None | bool:
    if text is None:
        return None
    found: list[int] = []
    for piece in text.split(","):
        piece = piece.strip()
        if not re.fullmatch(r"[+-]?\d+", piece):
            return False
        value = int(piece)
        if signed:
            if value == 0 or value < -high or value > high:
                return False
        elif value < low or value > high:
            return False
        if value not in found:
            found.append(value)
    return tuple(found) if found else False


def _parse_byday(text: str | None, freq: str) -> tuple[tuple[str, int | None], ...] | None | str:
    if text is None:
        return None
    tokens: list[tuple[str, int | None]] = []
    for piece in text.split(","):
        match = _BYDAY.fullmatch(piece.strip())
        if match is None:
            return "invalid BYDAY"
        name = match.group(2).upper()
        if name not in _WEEKDAY:
            return "invalid BYDAY"
        ordinal = int(match.group(1)) if match.group(1) else None
        if ordinal is not None:
            if freq not in {"MONTHLY", "YEARLY"}:
                return "BYDAY ordinal is only valid when FREQ is MONTHLY or YEARLY"
            if ordinal == 0 or ordinal < -53 or ordinal > 53:
                return "invalid BYDAY"
        token = (name, ordinal)
        if token not in tokens:
            tokens.append(token)
    if not tokens:
        return "invalid BYDAY"
    return tuple(tokens)


def _expand(start: _Stamp, rule: _Rule, limit: int) -> dict[str, object]:
    bound = limit if rule.count is None else min(limit, rule.count)
    results: list[date | datetime] = []
    scanned = 0
    cap = bound * 400 + 400
    exhausted = False
    origin = start.value
    try:
        for period in _periods(origin, rule):
            if _period_starts_after(period, rule.until):
                break
            chosen = _apply_setpos(_instances(period, origin, rule), rule.bysetpos)
            stopped = False
            for item in chosen:
                if item < origin:
                    continue
                if rule.until is not None and item > rule.until:
                    stopped = True
                    break
                results.append(item)
                if len(results) >= bound:
                    stopped = True
                    break
            if stopped:
                break
            scanned += 1
            if scanned >= cap:
                exhausted = True
                break
    except OverflowError:
        return _fail("recurrence timestamp is out of range")
    truncated = len(results) >= limit and (rule.count is None or rule.count > limit)
    return {
        "ok": True,
        "occurrences": [_format(item, start) for item in results],
        "exhausted": exhausted and len(results) < bound,
        "truncated": truncated,
    }


def _periods(origin: date | datetime, rule: _Rule):
    day = origin if isinstance(origin, date) and not isinstance(origin, datetime) else origin.date()
    index = 0
    while True:
        if rule.freq == "DAILY":
            yield day + timedelta(days=index * rule.interval)
        elif rule.freq == "WEEKLY":
            opening = _week_start(day, rule.wkst)
            yield opening + timedelta(days=7 * index * rule.interval)
        elif rule.freq == "MONTHLY":
            yield _shift_month(day.year, day.month, index * rule.interval)
        else:
            year = day.year + index * rule.interval
            if year > 9999:
                return
            yield year
        index += 1
        if index > 100_000:
            return


def _period_starts_after(period: object, until: date | datetime | None) -> bool:
    if until is None:
        return False
    if isinstance(period, date) and not isinstance(period, datetime):
        limit = until if isinstance(until, date) and not isinstance(until, datetime) else until.date()
        return period > limit
    if isinstance(period, tuple):
        year, month = period
        if year > 9999 or year < 1:
            return True
        limit = until.date() if isinstance(until, datetime) else until
        return date(year, month, 1) > limit
    if isinstance(period, int):
        limit_year = until.year
        return period > limit_year
    return False


def _instances(period: object, origin: date | datetime, rule: _Rule) -> list[date | datetime]:
    if rule.freq == "DAILY":
        days = [period] if isinstance(period, date) and _daily_keeps(period, rule) else []
    elif rule.freq == "WEEKLY":
        days = _weekly_days(period, origin, rule) if isinstance(period, date) else []
    elif rule.freq == "MONTHLY":
        year, month = period  # type: ignore[misc]
        days = _monthly_days(year, month, origin, rule)
    else:
        days = _yearly_days(int(period), origin, rule)  # type: ignore[arg-type]
    return _with_clock(days, origin, rule)


def _daily_keeps(day: date, rule: _Rule) -> bool:
    if rule.bymonth is not None and day.month not in rule.bymonth:
        return False
    if rule.bymonthday is not None and not _monthday_matches(day, rule.bymonthday):
        return False
    if rule.byday is not None:
        names = {name for name, ordinal in rule.byday if ordinal is None}
        if _WEEKDAY_NAME[day.weekday()] not in names:
            return False
    return True


def _weekly_days(opening: date, origin: date | datetime, rule: _Rule) -> list[date]:
    anchor = origin if isinstance(origin, date) and not isinstance(origin, datetime) else origin.date()
    tokens = rule.byday or ((_WEEKDAY_NAME[anchor.weekday()], None),)
    found: list[date] = []
    for name, _ordinal in tokens:
        day = opening + timedelta(days=(_WEEKDAY[name] - rule.wkst) % 7)
        if rule.bymonth is not None and day.month not in rule.bymonth:
            continue
        if rule.bymonthday is not None and not _monthday_matches(day, rule.bymonthday):
            continue
        found.append(day)
    return sorted(set(found))


def _monthly_days(year: int, month: int, origin: date | datetime, rule: _Rule) -> list[date]:
    if rule.bymonth is not None and month not in rule.bymonth:
        return []
    anchor = origin if isinstance(origin, date) and not isinstance(origin, datetime) else origin.date()
    monthdays = rule.bymonthday
    byday = rule.byday
    if monthdays is None and byday is None:
        monthdays = (anchor.day,)
    return _dates_in_month(year, month, monthdays, byday)


def _yearly_days(year: int, origin: date | datetime, rule: _Rule) -> list[date]:
    anchor = origin if isinstance(origin, date) and not isinstance(origin, datetime) else origin.date()
    has_day_rule = rule.bymonthday is not None or rule.byday is not None
    if rule.bymonth is None and not has_day_rule:
        return _dates_in_month(year, anchor.month, (anchor.day,), None)
    if (
        rule.bymonth is None
        and rule.bymonthday is None
        and rule.byday is not None
        and all(ordinal is not None for _name, ordinal in rule.byday)
    ):
        return _ordinal_days_in_year(year, rule.byday)
    if rule.bymonth is not None:
        months = rule.bymonth
    elif has_day_rule:
        months = tuple(range(1, 13))
    else:
        months = (anchor.month,)
    monthdays = rule.bymonthday
    byday = rule.byday
    if monthdays is None and byday is None:
        monthdays = (anchor.day,)
    found: list[date] = []
    for month in months:
        found.extend(_dates_in_month(year, month, monthdays, byday))
    return sorted(set(found))


def _dates_in_month(
    year: int,
    month: int,
    monthdays: tuple[int, ...] | None,
    byday: tuple[tuple[str, int | None], ...] | None,
) -> list[date]:
    if month < 1 or month > 12:
        return []
    numbers = None if monthdays is None else _resolve_monthdays(year, month, monthdays)
    weekdays = None if byday is None else set(_weekday_numbers(year, month, byday))
    if numbers is not None and weekdays is not None:
        chosen = numbers & weekdays
    elif numbers is not None:
        chosen = numbers
    elif weekdays is not None:
        chosen = weekdays
    else:
        chosen = set()
    return [date(year, month, day) for day in sorted(chosen)]


def _resolve_monthdays(year: int, month: int, monthdays: tuple[int, ...]) -> set[int]:
    last = calendar.monthrange(year, month)[1]
    found: set[int] = set()
    for number in monthdays:
        if number > 0:
            if number <= last:
                found.add(number)
        else:
            day = last + 1 + number
            if 1 <= day <= last:
                found.add(day)
    return found


def _monthday_matches(day: date, monthdays: tuple[int, ...]) -> bool:
    return day.day in _resolve_monthdays(day.year, day.month, monthdays)


def _weekday_numbers(
    year: int,
    month: int,
    tokens: tuple[tuple[str, int | None], ...],
) -> list[int]:
    last = calendar.monthrange(year, month)[1]
    grouped = _days_by_weekday(date(year, month, 1), date(year, month, last))
    found: list[int] = []
    for name, ordinal in tokens:
        days = grouped[_WEEKDAY[name]]
        if ordinal is None:
            found.extend(day.day for day in days)
        else:
            picked = _pick_ordinal(days, ordinal)
            if picked is not None:
                found.append(picked.day)
    return found


def _ordinal_days_in_year(year: int, tokens: tuple[tuple[str, int | None], ...]) -> list[date]:
    grouped = _days_by_weekday(date(year, 1, 1), date(year, 12, 31))
    found: list[date] = []
    for name, ordinal in tokens:
        if ordinal is None:
            continue
        picked = _pick_ordinal(grouped[_WEEKDAY[name]], ordinal)
        if picked is not None:
            found.append(picked)
    return sorted(set(found))


def _days_by_weekday(first: date, last: date) -> tuple[list[date], ...]:
    grouped: tuple[list[date], ...] = tuple([] for _ in range(7))
    day = first
    while day <= last:
        grouped[day.weekday()].append(day)
        day += timedelta(days=1)
    return grouped


def _pick_ordinal(days: list[date], ordinal: int) -> date | None:
    if ordinal > 0 and ordinal <= len(days):
        return days[ordinal - 1]
    if ordinal < 0 and -ordinal <= len(days):
        return days[ordinal]
    return None


def _with_clock(days: list[date], origin: date | datetime, rule: _Rule) -> list[date | datetime]:
    if isinstance(origin, date) and not isinstance(origin, datetime):
        return sorted(set(days))
    hours = rule.byhour if rule.byhour is not None else (origin.hour,)
    minutes = rule.byminute if rule.byminute is not None else (origin.minute,)
    seconds = rule.bysecond if rule.bysecond is not None else (origin.second,)
    found = [
        datetime(day.year, day.month, day.day, hour, minute, second)
        for day in days
        for hour in hours
        for minute in minutes
        for second in seconds
    ]
    return sorted(set(found))


def _apply_setpos(items: list[date | datetime], positions: tuple[int, ...] | None) -> list[date | datetime]:
    # BYSETPOS indexes the period set before dates earlier than DTSTART are dropped.
    ordered = sorted(set(items))
    if not positions:
        return ordered
    chosen: list[date | datetime] = []
    size = len(ordered)
    for position in positions:
        if position > 0 and position <= size:
            chosen.append(ordered[position - 1])
        elif position < 0 and -position <= size:
            chosen.append(ordered[position])
    return sorted(set(chosen))


def _week_start(day: date, wkst: int) -> date:
    return day - timedelta(days=(day.weekday() - wkst) % 7)


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + offset
    return index // 12, index % 12 + 1


def _format(value: date | datetime, start: _Stamp) -> str:
    if isinstance(value, datetime):
        text = value.strftime("%Y%m%dT%H%M%S")
        return text + "Z" if start.utc else text
    return value.strftime("%Y%m%d")
