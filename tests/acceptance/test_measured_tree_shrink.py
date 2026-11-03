"""A duplicate plane body can be deleted while cache freshness stays closed.

The shrink removes a later function whose signature and body match an earlier
one, and it leaves a pinned cache_decision function unchanged. The stored HTTP
response from the previous freshness contract stays fresh at age 12.

On the previous milestone the shrink primitive is absent, so this probe
reports passed=false. Both outcomes exit 0.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


SOURCE = """\
def cache_decision(headers):
    return {"disposition": "fresh", "current_age": 12}


def plane_septuple():
    return "nested-instance-plane"


def plane_octuple():
    return "nested-instance-plane"
"""


def _freshness() -> tuple[bool, dict[str, object]]:
    from blackhole_agent.http_cache import cache_decision

    decision = cache_decision(
        {
            "Date": "Tue, 03 Nov 2026 12:00:00 GMT",
            "Cache-Control": "max-age=60",
            "Expires": "Tue, 01 Jan 1980 00:00:00 GMT",
        },
        request_headers={},
        request_time=datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc),
        response_time=datetime(2026, 11, 3, 12, 0, 2, tzinfo=timezone.utc),
        now=datetime(2026, 11, 3, 12, 0, 12, tzinfo=timezone.utc),
        shared=True,
    )
    observed = {
        "current_age": decision["current_age"],
        "disposition": decision["disposition"],
        "freshness_lifetime": decision["freshness_lifetime"],
        "serve": decision["serve"],
    }
    ok = (
        decision["disposition"] == "fresh"
        and decision["current_age"] == 12
        and decision["freshness_lifetime"] == 60
        and decision["serve"] is True
    )
    return ok, observed


def main() -> None:
    observed: dict[str, object] = {}
    try:
        freshness_ok, freshness = _freshness()
        observed["freshness"] = freshness
    except Exception as exc:  # noqa: BLE001 - baseline and candidate must both print JSON
        observed["freshness_error"] = type(exc).__name__
        freshness_ok = False
    try:
        from blackhole_agent.measured_tree_shrink import shrink_measured_source
    except Exception:  # noqa: BLE001 - absence is an unmet outcome, not a crash
        observed["shrink"] = "absent"
        print(json.dumps({"passed": False, "observed": observed}))
        return
    result = shrink_measured_source(SOURCE, pinned=("cache_decision",))
    source = str(result["source"])
    observed["shrink"] = {
        "lines_after": result["lines_after"],
        "lines_before": result["lines_before"],
        "pinned_intact": result["pinned_intact"],
        "removed": result["removed"],
        "kept_decision": "def cache_decision(headers):" in source,
        "kept_first_plane": "def plane_septuple():" in source,
        "dropped_duplicate": "def plane_octuple():" not in source,
    }
    passed = bool(
        freshness_ok
        and result["shrunk"]
        and result["pinned_intact"]
        and result["removed"] == ["plane_octuple"]
        and observed["shrink"]["kept_decision"]
        and observed["shrink"]["kept_first_plane"]
        and observed["shrink"]["dropped_duplicate"]
    )
    print(json.dumps({"passed": passed, "observed": observed}))


if __name__ == "__main__":
    main()
