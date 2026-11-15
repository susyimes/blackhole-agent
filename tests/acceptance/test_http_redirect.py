"""A Fetch redirect rewrites the next request instead of repeating it.

A 301 or 302 rewrites POST only. A 303 rewrites every method except GET and
HEAD. A 307 keeps the body and loses Authorization on a cross-origin hop.
Content-Length stays when the body headers are removed. wss is not followed.
An unreplayable body fails after the redirect count increments, except when
303 drops that body. A missing Location is the response, not an error.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the redirect step is an unmet outcome, not
a crash.
"""

from __future__ import annotations

import json

PAGE = "https://shop.example/a/pay#old"
HEADERS = [
    ("Accept", "text/html"),
    ("Content-Type", "application/json"),
    ("Content-Length", "4"),
    ("Content-Language", "en"),
    ("Content-Encoding", "identity"),
    ("Content-Location", "/pay"),
    ("Authorization", "Basic eQ=="),
    ("X-Trace", "1"),
]
KEPT_BODY_HEADERS = [
    ["Accept", "text/html"],
    ["Content-Length", "4"],
    ["Authorization", "Basic eQ=="],
    ["X-Trace", "1"],
]
KEPT_WITH_TYPE = [
    ["Accept", "text/html"],
    ["Content-Type", "application/json"],
    ["Content-Length", "4"],
    ["Content-Language", "en"],
    ["Content-Encoding", "identity"],
    ["Content-Location", "/pay"],
    ["Authorization", "Basic eQ=="],
    ["X-Trace", "1"],
]
CROSS_ORIGIN_KEPT = [
    ["Accept", "text/html"],
    ["Content-Type", "application/json"],
    ["Content-Length", "4"],
    ["Content-Language", "en"],
    ["Content-Encoding", "identity"],
    ["Content-Location", "/pay"],
    ["X-Trace", "1"],
]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.http_redirect import follow_redirect
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    def step(**kwargs: object) -> dict[str, object]:
        payload = {
            "method": "POST",
            "url": PAGE,
            "status": 301,
            "response_headers": [("Location", "next")],
            "request_headers": HEADERS,
            "body": b"pay!",
        }
        payload.update(kwargs)
        return follow_redirect(**payload)  # type: ignore[arg-type]

    cases = {
        "post_301_relative_fragment": (
            step(),
            {
                "type": "next-request",
                "reason": "followed",
                "method": "GET",
                "url": "https://shop.example/a/next#old",
                "body": None,
                "headers": KEPT_BODY_HEADERS,
                "redirect_count": 1,
            },
        ),
        "post_302_becomes_get": (
            step(status=302, response_headers=[("Location", "/done")]),
            {
                "type": "next-request",
                "method": "GET",
                "url": "https://shop.example/done#old",
                "body": None,
                "headers": KEPT_BODY_HEADERS,
            },
        ),
        "put_302_stays_put": (
            step(method="PUT", status=302, response_headers=[("Location", "/done")]),
            {
                "type": "next-request",
                "method": "PUT",
                "url": "https://shop.example/done#old",
                "body": "pay!",
                "headers": KEPT_WITH_TYPE,
            },
        ),
        "post_307_cross_origin": (
            step(status=307, response_headers=[("Location", "https://other.example/pay")]),
            {
                "type": "next-request",
                "method": "POST",
                "url": "https://other.example/pay#old",
                "body": "pay!",
                "headers": CROSS_ORIGIN_KEPT,
            },
        ),
        "post_308_keeps_method": (
            step(status=308, response_headers=[("Location", "/again")]),
            {
                "type": "next-request",
                "method": "POST",
                "url": "https://shop.example/again#old",
                "body": "pay!",
                "headers": KEPT_WITH_TYPE,
            },
        ),
        "head_303_stays_head": (
            step(method="HEAD", status=303, body=None, response_headers=[("Location", "/done")]),
            {
                "type": "next-request",
                "method": "HEAD",
                "url": "https://shop.example/done#old",
                "body": None,
            },
        ),
        "lowercase_post_not_rewritten": (
            step(method="post"),
            {
                "type": "next-request",
                "method": "post",
                "body": "pay!",
                "url": "https://shop.example/a/next#old",
            },
        ),
        "empty_location_restores_fragment": (
            step(response_headers=[("Location", "")]),
            {
                "type": "next-request",
                "method": "GET",
                "url": "https://shop.example/a/pay#old",
                "body": None,
            },
        ),
        "empty_fragment_does_not_inherit": (
            step(response_headers=[("Location", "/next#")]),
            {"type": "next-request", "url": "https://shop.example/next#"},
        ),
        "wss_rejected": (
            step(response_headers=[("Location", "wss://shop.example/socket")]),
            {"type": "network-error", "reason": "non-http-scheme", "redirect_count": 0, "method": "POST"},
        ),
        "javascript_rejected": (
            step(response_headers=[("Location", "javascript:alert(1)")]),
            {"type": "network-error", "reason": "invalid-location", "redirect_count": 0},
        ),
        "missing_location": (
            step(response_headers=[]),
            {"type": "response", "reason": "no-location", "method": "POST", "status": 301},
        ),
        "status_300_ignored": (
            step(status=300, response_headers=[("Location", "/next")]),
            {"type": "response", "reason": "not-redirect", "method": "POST", "status": 300},
        ),
        "two_locations": (
            step(response_headers=[("Location", "/a"), ("location", "/b")]),
            {"type": "network-error", "reason": "invalid-location", "redirect_count": 0},
        ),
        "count_20": (
            step(redirect_count=20),
            {"type": "network-error", "reason": "redirect-count", "redirect_count": 20, "method": "POST"},
        ),
        "count_19": (
            step(redirect_count=19),
            {"type": "next-request", "redirect_count": 20, "method": "GET"},
        ),
        "unreplayable_307": (
            step(status=307, replayable=False, response_headers=[("Location", "/again")]),
            {"type": "network-error", "reason": "unreplayable-body", "redirect_count": 1, "method": "POST"},
        ),
        "unreplayable_302": (
            step(status=302, replayable=False, response_headers=[("Location", "/done")]),
            {"type": "network-error", "reason": "unreplayable-body", "redirect_count": 1},
        ),
        "unreplayable_303": (
            step(status=303, replayable=False, response_headers=[("Location", "/done")]),
            {"type": "next-request", "method": "GET", "body": None, "url": "https://shop.example/done#old"},
        ),
        "cors_credentials": (
            step(
                response_headers=[("Location", "https://user:secret@other.example/x")],
                mode="cors",
                origin="https://shop.example",
            ),
            {"type": "network-error", "reason": "cors-credentials", "redirect_count": 1, "method": "POST"},
        ),
        "tainted_same_origin_credentials": (
            step(
                response_headers=[("Location", "https://user:secret@shop.example/next")],
                tainting="cors",
                origin="https://shop.example",
            ),
            {"type": "network-error", "reason": "cors-tainted-credentials", "redirect_count": 1},
        ),
        "basic_same_origin_credentials": (
            step(
                response_headers=[("Location", "https://user:secret@shop.example/next")],
                tainting="basic",
                origin="https://shop.example",
            ),
            {
                "type": "next-request",
                "method": "GET",
                "url": "https://user:secret@shop.example/next#old",
                "headers": KEPT_BODY_HEADERS,
            },
        ),
        "error_mode": (
            step(redirect_mode="error"),
            {"type": "network-error", "reason": "redirect-mode", "redirect_count": 0, "method": "POST"},
        ),
        "manual_cors_opaque": (
            step(redirect_mode="manual", mode="cors"),
            {
                "type": "opaque-redirect",
                "status": 0,
                "headers": [],
                "url": PAGE,
                "body": None,
                "method": "POST",
            },
        ),
        "default_port_keeps_authorization": (
            step(
                status=307,
                url="https://shop.example/pay#old",
                response_headers=[("Location", "https://shop.example:443/next")],
            ),
            {
                "type": "next-request",
                "method": "POST",
                "url": "https://shop.example/next#old",
                "headers": KEPT_WITH_TYPE,
            },
        ),
        "other_port_drops_authorization": (
            step(
                status=307,
                url="https://shop.example/pay#old",
                response_headers=[("Location", "https://shop.example:444/next")],
            ),
            {
                "type": "next-request",
                "method": "POST",
                "url": "https://shop.example:444/next#old",
                "headers": CROSS_ORIGIN_KEPT,
            },
        ),
        "backslash_location": (
            step(response_headers=[("Location", "https://shop.example/a\\b")]),
            {"type": "next-request", "url": "https://shop.example/a/b#old", "method": "GET"},
        ),
    }
    mismatches: dict[str, object] = {}
    observed: dict[str, object] = {}
    for name, (actual, expected) in cases.items():
        observed[name] = {key: actual.get(key) for key in expected}
        if any(actual.get(key) != value for key, value in expected.items()):
            mismatches[name] = {"expected": expected, "actual": observed[name]}
    return not mismatches, {"cases": observed, "mismatches": mismatches}


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
