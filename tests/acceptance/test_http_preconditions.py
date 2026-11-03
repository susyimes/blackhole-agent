"""HTTP preconditions use different comparisons and a fixed order.

A weak validator fails If-Match and If-Range and still yields 304 for
If-None-Match. An equal modification time yields 304. A mismatched
If-Range date leaves the whole representation. If-Match failure wins
over a passing If-None-Match. A 404 stays 404. PUT with If-None-Match *
and no representation proceeds. POST with a matching tag is 412.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both
met and unmet outcomes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


_MODIFIED = datetime(1994, 11, 6, 8, 49, 37, tzinfo=timezone.utc)
_EQUAL = "Sun, 06 Nov 1994 08:49:37 GMT"
_BEFORE = "Sun, 06 Nov 1994 08:49:36 GMT"
_AFTER = "Sun, 06 Nov 1994 08:49:38 GMT"


def _eval(**kwargs) -> dict:
    from blackhole_agent.http_preconditions import evaluate_http_preconditions

    method = kwargs.pop("method", "GET")
    fields = kwargs.pop("fields")
    return evaluate_http_preconditions(method, fields, **kwargs)


def observe() -> tuple[bool, dict]:
    observed: dict = {"layer": "preconditions"}
    try:
        from blackhole_agent.http_preconditions import evaluate_http_preconditions
    except Exception as exc:  # noqa: BLE001 - baseline without the decider still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    try:
        weak_none = _eval(
            fields=[("If-None-Match", 'W/"v"'), ("Range", "bytes=0-1")],
            etag='"v"',
            length=10,
        )
        weak_match = _eval(fields=[("If-Match", 'W/"v"')], etag='"v"')
        strong_against_weak = _eval(fields=[("If-Match", '"v"')], etag='W/"v"')
        strong_match = _eval(fields=[("If-Match", '"v"'), ("Range", "bytes=0-1")], etag='"v"', length=10)
        ims_equal = _eval(fields=[("If-Modified-Since", _EQUAL)], last_modified=_MODIFIED)
        ims_before = _eval(fields=[("If-Modified-Since", _BEFORE)], last_modified=_MODIFIED)
        ims_invalid = _eval(fields=[("If-Modified-Since", "not-a-date")], last_modified=_MODIFIED)
        two_ims = _eval(
            fields=[("If-Modified-Since", f"{_EQUAL}, {_EQUAL}")],
            last_modified=_MODIFIED,
        )
        range_off = _eval(
            fields=[("If-Range", _BEFORE), ("Range", "bytes=0-1")],
            last_modified=_MODIFIED,
            length=10,
        )
        range_after = _eval(
            fields=[("If-Range", _AFTER), ("Range", "bytes=0-1")],
            last_modified=_MODIFIED,
            length=10,
        )
        range_exact = _eval(
            fields=[("If-Range", _EQUAL), ("Range", "bytes=0-1")],
            last_modified=_MODIFIED,
            length=10,
        )
        range_weak = _eval(
            fields=[("If-Range", 'W/"v"'), ("Range", "bytes=0-1")],
            etag='"v"',
            length=10,
        )
        range_twice = _eval(
            fields=[("If-Range", _EQUAL), ("Range", "bytes=0-1")],
            last_modified=_MODIFIED,
            length=10,
            changed_twice=True,
        )
        match_wins = _eval(
            fields=[("If-Match", '"old"'), ("If-None-Match", '"other"')],
            etag='"new"',
        )
        missing = _eval(fields=[("If-Match", '"v"')], etag='"other"', would_status=404)
        redirect = _eval(fields=[("If-Match", '"v"')], etag='"v"', would_status=301)
        put_star = _eval(method="PUT", fields=[("If-None-Match", "*")])
        put_exists = _eval(method="PUT", fields=[("If-None-Match", "*")], exists=True)
        post_match = _eval(method="POST", fields=[("If-None-Match", '"v"')], etag='"v"')
        match_skips_date = _eval(
            fields=[("If-Match", '"v"'), ("If-Unmodified-Since", _BEFORE)],
            etag='"v"',
            last_modified=_MODIFIED,
        )
        garbage_none = _eval(
            fields=[("If-None-Match", "not-a-tag"), ("If-Modified-Since", _EQUAL)],
            etag='"v"',
            last_modified=_MODIFIED,
        )
        unmodified_equal = _eval(fields=[("If-Unmodified-Since", _EQUAL)], last_modified=_MODIFIED)
        unmodified_before = _eval(
            method="PUT",
            fields=[("If-Unmodified-Since", _BEFORE)],
            last_modified=_MODIFIED,
        )
        unmodified_unknown = _eval(fields=[("If-Unmodified-Since", _EQUAL)], etag='"v"')
        head_ims = _eval(method="HEAD", fields=[("If-Modified-Since", _EQUAL)], last_modified=_MODIFIED)
        combined = _eval(
            fields=[("If-None-Match", '"a"'), ("If-None-Match", '"v"')],
            etag='"v"',
        )
        ranged = _eval(fields=[("Range", "bytes=0-1")], length=10)
        none_then_range = _eval(
            fields=[("If-None-Match", '"other"'), ("If-Range", '"v"'), ("Range", "bytes=0-1")],
            etag='"v"',
            length=10,
        )
        unsatisfiable = _eval(
            fields=[("If-Range", _EQUAL), ("Range", "bytes=100-200")],
            last_modified=_MODIFIED,
            length=10,
        )
        options = _eval(method="OPTIONS", fields=[("If-Match", '"no"')], etag='"v"')
        quoted_star = _eval(fields=[("If-Match", '"*"')], etag='"no"')
        bare_star = _eval(fields=[("If-Match", "*")], etag='"no"')
        comma_tag = _eval(fields=[("If-None-Match", '"a,b"')], etag='"a,b"')
        kept = _eval(fields=[], would_status=204)
        lower = evaluate_http_preconditions("GET", [("if-none-match", 'W/"v"')], etag='"v"')
    except Exception as exc:  # noqa: BLE001 - an unmet outcome still exits 0
        observed["error"] = type(exc).__name__
        return False, observed

    observed.update(
        {
            "weak_none_status": weak_none["status"],
            "weak_none_range": weak_none["apply_range"],
            "weak_none_ranges": weak_none["ranges"],
            "weak_match_status": weak_match["status"],
            "strong_against_weak": strong_against_weak["status"],
            "strong_match_status": strong_match["status"],
            "strong_match_ranges": strong_match["ranges"],
            "ims_equal": ims_equal["status"],
            "ims_before": ims_before["status"],
            "ims_invalid": ims_invalid["status"],
            "two_ims": two_ims["status"],
            "range_off": range_off["status"],
            "range_off_applied": range_off["apply_range"],
            "range_after": range_after["status"],
            "range_exact": range_exact["status"],
            "range_exact_ranges": range_exact["ranges"],
            "range_exact_content": range_exact["content_range"],
            "range_weak": range_weak["status"],
            "range_twice": range_twice["status"],
            "match_wins": match_wins["status"],
            "missing": missing["status"],
            "missing_ignored": missing["ignored"],
            "redirect": redirect["status"],
            "put_star": put_star["status"],
            "put_exists": put_exists["status"],
            "post_match": post_match["status"],
            "match_skips_date": match_skips_date["status"],
            "garbage_none": garbage_none["status"],
            "unmodified_equal": unmodified_equal["status"],
            "unmodified_before": unmodified_before["status"],
            "unmodified_unknown": unmodified_unknown["status"],
            "head_ims": head_ims["status"],
            "combined": combined["status"],
            "ranged": ranged["ranges"],
            "none_then_range": none_then_range["status"],
            "none_then_ranges": none_then_range["ranges"],
            "unsatisfiable": unsatisfiable["status"],
            "unsatisfiable_content": unsatisfiable["content_range"],
            "options": options["status"],
            "options_ignored": options["ignored"],
            "quoted_star": quoted_star["status"],
            "bare_star": bare_star["status"],
            "comma_tag": comma_tag["status"],
            "kept": kept["status"],
            "lower": lower["status"],
        }
    )
    passed = (
        observed["weak_none_status"] == 304
        and observed["weak_none_range"] is False
        and observed["weak_none_ranges"] == []
        and observed["weak_match_status"] == 412
        and observed["strong_against_weak"] == 412
        and observed["strong_match_status"] == 206
        and observed["strong_match_ranges"] == [[0, 1]]
        and observed["ims_equal"] == 304
        and observed["ims_before"] == 200
        and observed["ims_invalid"] == 200
        and observed["two_ims"] == 200
        and observed["range_off"] == 200
        and observed["range_off_applied"] is False
        and observed["range_after"] == 200
        and observed["range_exact"] == 206
        and observed["range_exact_ranges"] == [[0, 1]]
        and observed["range_exact_content"] == "bytes 0-1/10"
        and observed["range_weak"] == 200
        and observed["range_twice"] == 200
        and observed["match_wins"] == 412
        and observed["missing"] == 404
        and observed["missing_ignored"] is True
        and observed["redirect"] == 301
        and observed["put_star"] == 200
        and observed["put_exists"] == 412
        and observed["post_match"] == 412
        and observed["match_skips_date"] == 200
        and observed["garbage_none"] == 200
        and observed["unmodified_equal"] == 200
        and observed["unmodified_before"] == 412
        and observed["unmodified_unknown"] == 200
        and observed["head_ims"] == 304
        and observed["combined"] == 304
        and observed["ranged"] == [[0, 1]]
        and observed["none_then_range"] == 206
        and observed["none_then_ranges"] == [[0, 1]]
        and observed["unsatisfiable"] == 416
        and observed["unsatisfiable_content"] == "bytes */10"
        and observed["options"] == 200
        and observed["options_ignored"] is True
        and observed["quoted_star"] == 412
        and observed["bare_star"] == 200
        and observed["comma_tag"] == 304
        and observed["kept"] == 204
        and observed["lower"] == 304
    )
    return passed, observed


def test_http_preconditions() -> None:
    passed, observed = observe()
    assert passed, observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
