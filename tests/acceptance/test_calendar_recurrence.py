"""iCalendar recurrence skips invalid dates instead of clamping them.

A monthly 31st does not become the last day of a short month, and COUNT
does not spend an occurrence on the skip. February 29 stays on leap days.
BYSETPOS chooses inside one month, and a two-week interval keeps both
weekdays of each selected week. COUNT together with UNTIL is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without this expansion is an unmet outcome.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.calendar_recurrence import expand_recurrence
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    def dates(start: str, rule: str) -> dict[str, object]:
        return expand_recurrence(start, rule)

    cases: dict[str, tuple[object, object]] = {
        "monthly_31st_skips_short_months": (
            dates("19970131T090000", "FREQ=MONTHLY;BYMONTHDAY=31;COUNT=4"),
            {
                "ok": True,
                "occurrences": [
                    "19970131T090000",
                    "19970331T090000",
                    "19970531T090000",
                    "19970731T090000",
                ],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "leap_day_stays_on_leap_years": (
            dates("19960229T090000", "FREQ=YEARLY;COUNT=3"),
            {
                "ok": True,
                "occurrences": [
                    "19960229T090000",
                    "20000229T090000",
                    "20040229T090000",
                ],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "last_weekday_is_chosen_inside_each_month": (
            dates("19970829T090000", "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1;COUNT=3"),
            {
                "ok": True,
                "occurrences": [
                    "19970829T090000",
                    "19970930T090000",
                    "19971031T090000",
                ],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "biweekly_keeps_both_weekdays": (
            dates("19970902T090000", "FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST=MO"),
            {
                "ok": True,
                "occurrences": [
                    "19970902T090000",
                    "19970907T090000",
                    "19970916T090000",
                    "19970921T090000",
                ],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "election_day_is_the_tuesday_in_that_window": (
            dates(
                "19961105T090000",
                "FREQ=YEARLY;INTERVAL=4;BYMONTH=11;BYDAY=TU;BYMONTHDAY=2,3,4,5,6,7,8;COUNT=4",
            ),
            {
                "ok": True,
                "occurrences": [
                    "19961105T090000",
                    "20001107T090000",
                    "20041102T090000",
                    "20081104T090000",
                ],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "unmatched_dtstart_is_not_inserted": (
            dates("19970902T090000", "FREQ=MONTHLY;BYMONTHDAY=1;COUNT=2"),
            {
                "ok": True,
                "occurrences": ["19971001T090000", "19971101T090000"],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "until_includes_an_equal_timestamp": (
            dates("19970902T090000", "FREQ=DAILY;UNTIL=19970904T090000"),
            {
                "ok": True,
                "occurrences": [
                    "19970902T090000",
                    "19970903T090000",
                    "19970904T090000",
                ],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "until_before_the_clock_time_excludes_that_day": (
            dates("19970902T090000", "FREQ=DAILY;UNTIL=19970904T085959"),
            {
                "ok": True,
                "occurrences": ["19970902T090000", "19970903T090000"],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "bysetpos_applies_inside_the_day": (
            dates("19970902T090000", "FREQ=DAILY;BYHOUR=9,10,11;BYSETPOS=-1;COUNT=2"),
            {
                "ok": True,
                "occurrences": ["19970902T110000", "19970903T110000"],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "negative_monthday_is_the_real_last_day": (
            dates("19970131T090000", "FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=3"),
            {
                "ok": True,
                "occurrences": [
                    "19970131T090000",
                    "19970228T090000",
                    "19970331T090000",
                ],
                "exhausted": False,
                "truncated": False,
            },
        ),
        "february_30_matches_nothing": (
            dates("19970201T090000", "FREQ=MONTHLY;BYMONTH=2;BYMONTHDAY=30;COUNT=3"),
            {"ok": True, "occurrences": [], "exhausted": True, "truncated": False},
        ),
        "count_and_until_are_rejected": (
            dates("19970902T090000", "FREQ=DAILY;COUNT=2;UNTIL=19970904T090000"),
            {
                "ok": False,
                "error": "COUNT and UNTIL are mutually exclusive",
                "occurrences": [],
            },
        ),
        "weekly_ordinal_is_rejected": (
            dates("19970902T090000", "FREQ=WEEKLY;BYDAY=1MO;COUNT=2"),
            {
                "ok": False,
                "error": "BYDAY ordinal is only valid when FREQ is MONTHLY or YEARLY",
                "occurrences": [],
            },
        ),
    }
    observed: dict[str, object] = {}
    mismatches: list[str] = []
    for name, (got, want) in cases.items():
        observed[name] = got
        if got != want:
            mismatches.append(name)
    observed["mismatches"] = mismatches
    return not mismatches, observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet outcome must still exit 0
        passed = False
        observed = {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"empty": True}
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
