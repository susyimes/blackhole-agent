"""Shared cache freshness follows max-age, corrected Age, and no-cache.

A past Expires header does not override max-age. An Age header is added to
the response delay. Unqualified no-cache is not served. Qualified no-cache
stays servable while the named field is omitted.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both met
and unmet outcomes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

REQ = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
RESP = datetime(2026, 11, 3, 12, 0, 2, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 3, 12, 0, 12, tzinfo=timezone.utc)
DATE = "Tue, 03 Nov 2026 12:00:00 GMT"
PAST = "Tue, 01 Jan 1980 00:00:00 GMT"
MODIFIED = "Tue, 03 Nov 2026 09:13:20 GMT"

CASES = (
    {
        "name": "expires_loses_to_max_age",
        "response": {"Date": DATE, "Cache-Control": "max-age=60", "Expires": PAST},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "fresh",
            "freshness_lifetime": 60,
            "omit": [],
            "serve": True,
        },
    },
    {
        "name": "age_header_dominates",
        "response": {"Date": DATE, "Cache-Control": "max-age=60", "Age": "50"},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 62,
            "disposition": "stale",
            "freshness_lifetime": 60,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "unqualified_no_cache",
        "response": {"Date": DATE, "Cache-Control": "max-age=60, no-cache"},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "revalidate",
            "freshness_lifetime": 60,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "qualified_no_cache",
        "response": {"Date": DATE, "Cache-Control": 'max-age=60, no-cache="X-Private"'},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "fresh",
            "freshness_lifetime": 60,
            "omit": ["X-Private"],
            "serve": True,
        },
    },
    {
        "name": "shared_s_maxage",
        "response": {"Date": DATE, "Cache-Control": "s-maxage=10, max-age=120"},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "stale",
            "freshness_lifetime": 10,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "private_cache_ignores_s_maxage",
        "response": {"Date": DATE, "Cache-Control": "s-maxage=10, max-age=120"},
        "request": {},
        "shared": False,
        "expected": {
            "current_age": 12,
            "disposition": "fresh",
            "freshness_lifetime": 120,
            "omit": [],
            "serve": True,
        },
    },
    {
        "name": "shared_private",
        "response": {"Date": DATE, "Cache-Control": "private, max-age=60"},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "uncacheable",
            "freshness_lifetime": 60,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "no_store",
        "response": {"Date": DATE, "Cache-Control": "no-store, max-age=60"},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "uncacheable",
            "freshness_lifetime": 60,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "min_fresh_exceeds_remaining",
        "response": {"Date": DATE, "Cache-Control": "max-age=20"},
        "request": {"Cache-Control": "min-fresh=10"},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "stale",
            "freshness_lifetime": 20,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "max_stale_covers",
        "response": {"Date": DATE, "Cache-Control": "max-age=10"},
        "request": {"Cache-Control": "max-stale=5"},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "accepted-stale",
            "freshness_lifetime": 10,
            "omit": [],
            "serve": True,
        },
    },
    {
        "name": "must_revalidate_beats_max_stale",
        "response": {"Date": DATE, "Cache-Control": "max-age=10, must-revalidate"},
        "request": {"Cache-Control": "max-stale=100"},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "revalidate",
            "freshness_lifetime": 10,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "last_modified_heuristic",
        "response": {"Date": DATE, "Last-Modified": MODIFIED},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "fresh",
            "freshness_lifetime": 1000,
            "omit": [],
            "serve": True,
        },
    },
    {
        "name": "pragma_no_cache_alone",
        "response": {"Date": DATE, "Pragma": "no-cache"},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "revalidate",
            "freshness_lifetime": 0,
            "omit": [],
            "serve": False,
        },
    },
    {
        "name": "pragma_ignored_beside_max_age",
        "response": {"Date": DATE, "Pragma": "no-cache", "Cache-Control": "max-age=60"},
        "request": {},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "fresh",
            "freshness_lifetime": 60,
            "omit": [],
            "serve": True,
        },
    },
    {
        "name": "request_no_cache",
        "response": {"Date": DATE, "Cache-Control": "max-age=60"},
        "request": {"Cache-Control": "no-cache"},
        "shared": True,
        "expected": {
            "current_age": 12,
            "disposition": "revalidate",
            "freshness_lifetime": 60,
            "omit": [],
            "serve": False,
        },
    },
)


def _naive_disposition(headers: dict[str, str]) -> str:
    """Prefer Expires and ignore Age. That is the decision this mission kills."""

    date = parsedate_to_datetime(headers["Date"])
    age = int(NOW.timestamp()) - int(date.timestamp())
    if "Expires" in headers:
        expires = parsedate_to_datetime(headers["Expires"])
        lifetime = int(expires.timestamp()) - int(date.timestamp())
    else:
        lifetime = 0
        for part in headers.get("Cache-Control", "").split(","):
            token = part.strip()
            if token.lower().startswith("max-age="):
                lifetime = int(token.split("=", 1)[1])
    return "fresh" if lifetime > age else "stale"


def observe() -> tuple[bool, dict]:
    naive = {
        "expires_loses_to_max_age": _naive_disposition(CASES[0]["response"]),
        "age_header_dominates": _naive_disposition(CASES[1]["response"]),
    }
    observed: dict = {
        "naive": naive,
        "naive_prefers_expired": naive["expires_loses_to_max_age"] == "stale",
        "naive_ignores_age": naive["age_header_dominates"] == "fresh",
    }
    try:
        from blackhole_agent.http_cache import cache_decision
    except Exception as exc:  # noqa: BLE001 - baseline without the decision still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    mismatches: list[str] = []
    decisions: dict[str, dict] = {}
    for case in CASES:
        decision = cache_decision(
            case["response"],
            request_headers=case["request"],
            request_time=REQ,
            response_time=RESP,
            now=NOW,
            shared=case["shared"],
        )
        decisions[case["name"]] = decision
        if decision != case["expected"]:
            mismatches.append(case["name"])
    observed["decisions"] = decisions
    observed["mismatches"] = mismatches
    passed = (
        not mismatches
        and observed["naive_prefers_expired"] is True
        and observed["naive_ignores_age"] is True
    )
    return passed, observed


def test_cache_decision_matches_the_freshness_cases() -> None:
    passed, observed = observe()
    assert passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
