"""A cross-origin response is shared only under the Fetch CORS protocol.

A wildcard allow-origin fails when credentials are included. The letters
True are not the credential opt-in. An allow-headers asterisk does not
cover Authorization. Set-Cookie stays hidden. application/json still forces
a preflight and text/plain does not. Nine 128-byte Accept values cross the
1024-byte safelist budget and eight do not. A missing preflight max-age is
5 and 100000 is clamped to 7200.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the CORS response is an unmet outcome, not
a crash.
"""

from __future__ import annotations

import json


RABBIT = "https://rabbit.invalid"


def _view(result: dict[str, object]) -> dict[str, object]:
    return {
        "allowed": result["allowed"],
        "reason": result["reason"],
        "exposed": result["exposed"],
        "unsafe": result["unsafe_request_headers"],
        "needs_preflight": result["needs_preflight"],
        "max_age": result["max_age"],
    }


def _call(**kwargs: object) -> dict[str, object]:
    from blackhole_agent.fetch_cors import cors_response

    return _view(cors_response(**kwargs))


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.fetch_cors import cors_response
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    shared = [
        ("Content-Type", "text/plain"),
        ("X-Custom", "1"),
        ("Set-Cookie", "a=b"),
    ]
    try:
        seen = {
            "wildcard_include": _call(
                origin=RABBIT,
                credentials="include",
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Credentials", "true"),
                    *shared,
                ],
            ),
            "wildcard_space": _call(
                origin=RABBIT,
                response_headers=[("Access-Control-Allow-Origin", "* "), *shared],
            ),
            "true_letters": _call(
                origin=RABBIT,
                credentials="include",
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Credentials", "True"),
                    *shared,
                ],
            ),
            "credentials_ok": _call(
                origin=RABBIT,
                credentials="include",
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Credentials", "true"),
                    *shared,
                    ("Access-Control-Expose-Headers", "X-Custom, Set-Cookie"),
                ],
            ),
            "duplicate_origin": _call(
                origin=RABBIT,
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Origin", RABBIT),
                    *shared,
                ],
            ),
            "duplicate_credentials": _call(
                origin=RABBIT,
                credentials="include",
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Credentials", "true"),
                    ("Access-Control-Allow-Credentials", "true"),
                    *shared,
                ],
            ),
            "trailing_slash": _call(
                origin=RABBIT,
                response_headers=[("Access-Control-Allow-Origin", RABBIT + "/"), *shared],
            ),
            "null_origin": _call(
                origin="null",
                response_headers=[("Access-Control-Allow-Origin", "null"), ("Content-Type", "text/plain")],
            ),
            "missing_origin": _call(origin=RABBIT, response_headers=shared),
            "star_expose": _call(
                origin=RABBIT,
                response_headers=[("Access-Control-Allow-Origin", "*"), ("Access-Control-Expose-Headers", "*"), *shared],
            ),
            "star_expose_include": _call(
                origin=RABBIT,
                credentials="include",
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Credentials", "true"),
                    ("Access-Control-Expose-Headers", "*"),
                    *shared,
                ],
            ),
            "same_origin_star": _call(
                origin=RABBIT,
                credentials="same-origin",
                response_headers=[("Access-Control-Allow-Origin", "*"), *shared],
            ),
            "not_found": _call(
                origin=RABBIT,
                status=404,
                response_headers=[("Access-Control-Allow-Origin", RABBIT), *shared],
            ),
            "json_type": _call(
                origin=RABBIT,
                request_headers=[("Content-Type", "application/json")],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "plain_type": _call(
                origin=RABBIT,
                request_headers=[("Content-Type", "text/plain;charset=UTF-8")],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "quoted_plain": _call(
                origin=RABBIT,
                request_headers=[("Content-Type", 'text/plain;charset="UTF-8"')],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "accept_json": _call(
                origin=RABBIT,
                request_headers=[("Accept", "application/json")],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "range_ok": _call(
                origin=RABBIT,
                request_headers=[("Range", "bytes=0-1")],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "range_suffix": _call(
                origin=RABBIT,
                request_headers=[("Range", "bytes=-500")],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "accept_eight": _call(
                origin=RABBIT,
                request_headers=[("Accept", "a" * 128) for _index in range(8)],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "accept_nine": _call(
                origin=RABBIT,
                request_headers=[("Accept", "a" * 128) for _index in range(9)],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "put_star_omit": _call(
                origin=RABBIT,
                method="PUT",
                preflight=True,
                status=204,
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Methods", "*"),
                ],
            ),
            "put_star_include": _call(
                origin=RABBIT,
                credentials="include",
                method="PUT",
                preflight=True,
                status=204,
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Credentials", "true"),
                    ("Access-Control-Allow-Methods", "*"),
                ],
            ),
            "put_listed_include": _call(
                origin=RABBIT,
                credentials="include",
                method="PUT",
                preflight=True,
                status=200,
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Credentials", "true"),
                    ("Access-Control-Allow-Methods", "PUT, *"),
                    ("Access-Control-Max-Age", "100000"),
                ],
            ),
            "get_without_methods": _call(
                origin=RABBIT,
                preflight=True,
                status=204,
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "put_without_methods": _call(
                origin=RABBIT,
                method="PUT",
                preflight=True,
                status=204,
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "put_flag": _call(
                origin=RABBIT,
                method="PUT",
                preflight=True,
                use_preflight_flag=True,
                status=204,
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "authorization_star": _call(
                origin=RABBIT,
                preflight=True,
                status=204,
                request_headers=[("Authorization", "Bearer z")],
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Headers", "*"),
                    ("Access-Control-Allow-Methods", "GET"),
                ],
            ),
            "authorization_listed": _call(
                origin=RABBIT,
                credentials="include",
                preflight=True,
                status=204,
                request_headers=[("Authorization", "Bearer z"), ("X-Custom", "1")],
                response_headers=[
                    ("Access-Control-Allow-Origin", RABBIT),
                    ("Access-Control-Allow-Credentials", "true"),
                    ("Access-Control-Allow-Headers", "authorization, x-custom"),
                ],
            ),
            "nine_without_header_permission": _call(
                origin=RABBIT,
                preflight=True,
                status=204,
                request_headers=[("Accept", "b" * 128) for _index in range(9)],
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "nine_with_star": _call(
                origin=RABBIT,
                preflight=True,
                status=204,
                request_headers=[("Accept", "b" * 128) for _index in range(9)],
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Headers", "*"),
                ],
            ),
            "status_304": _call(
                origin=RABBIT,
                preflight=True,
                status=304,
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Methods", "GET"),
                ],
            ),
            "max_age_missing": _call(
                origin=RABBIT,
                preflight=True,
                status=204,
                response_headers=[("Access-Control-Allow-Origin", "*")],
            ),
            "max_age_zero": _call(
                origin=RABBIT,
                preflight=True,
                status=204,
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Max-Age", "0"),
                ],
            ),
            "max_age_duplicate": _call(
                origin=RABBIT,
                preflight=True,
                status=204,
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Max-Age", "10"),
                    ("Access-Control-Max-Age", "10"),
                ],
            ),
            "lowercase_put": _call(
                origin=RABBIT,
                method="PUT",
                preflight=True,
                status=204,
                response_headers=[
                    ("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Methods", "put"),
                ],
            ),
        }
        del cors_response
    except Exception as exc:  # noqa: BLE001 - a partial implementation is a miss
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    expected = {
        "wildcard_include": _expect(False, "cors-check"),
        "wildcard_space": _expect(False, "cors-check"),
        "true_letters": _expect(False, "cors-check"),
        "credentials_ok": _expect(
            True,
            "",
            exposed=[["Content-Type", "text/plain"], ["X-Custom", "1"]],
        ),
        "duplicate_origin": _expect(False, "cors-check"),
        "duplicate_credentials": _expect(False, "cors-check"),
        "trailing_slash": _expect(False, "cors-check"),
        "null_origin": _expect(True, "", exposed=[["Content-Type", "text/plain"]]),
        "missing_origin": _expect(False, "cors-check"),
        "star_expose": _expect(
            True,
            "",
            exposed=[
                ["Access-Control-Allow-Origin", "*"],
                ["Access-Control-Expose-Headers", "*"],
                ["Content-Type", "text/plain"],
                ["X-Custom", "1"],
            ],
        ),
        "star_expose_include": _expect(True, "", exposed=[["Content-Type", "text/plain"]]),
        "same_origin_star": _expect(
            True,
            "",
            exposed=[["Content-Type", "text/plain"]],
        ),
        "not_found": _expect(True, "", exposed=[["Content-Type", "text/plain"]]),
        "json_type": _expect(True, "", unsafe=["content-type"], needs_preflight=True),
        "plain_type": _expect(True, ""),
        "quoted_plain": _expect(True, "", unsafe=["content-type"], needs_preflight=True),
        "accept_json": _expect(True, ""),
        "range_ok": _expect(True, ""),
        "range_suffix": _expect(True, "", unsafe=["range"], needs_preflight=True),
        "accept_eight": _expect(True, ""),
        "accept_nine": _expect(True, "", unsafe=["accept"], needs_preflight=True),
        "put_star_omit": _expect(True, "", needs_preflight=True, max_age=5),
        "put_star_include": _expect(False, "method", needs_preflight=True),
        "put_listed_include": _expect(True, "", needs_preflight=True, max_age=7200),
        "get_without_methods": _expect(True, "", max_age=5),
        "put_without_methods": _expect(False, "method", needs_preflight=True),
        "put_flag": _expect(True, "", needs_preflight=True, max_age=5),
        "authorization_star": _expect(False, "authorization", unsafe=["authorization"], needs_preflight=True),
        "authorization_listed": _expect(
            True,
            "",
            unsafe=["authorization", "x-custom"],
            needs_preflight=True,
            max_age=5,
        ),
        "nine_without_header_permission": _expect(False, "header", unsafe=["accept"], needs_preflight=True),
        "nine_with_star": _expect(True, "", unsafe=["accept"], needs_preflight=True, max_age=5),
        "status_304": _expect(False, "status"),
        "max_age_missing": _expect(True, "", max_age=5),
        "max_age_zero": _expect(True, "", max_age=0),
        "max_age_duplicate": _expect(True, "", max_age=5),
        "lowercase_put": _expect(False, "method", needs_preflight=True),
    }
    mismatches = [name for name, want in expected.items() if seen.get(name) != want]
    observed: dict[str, object] = {"cases": seen}
    if mismatches:
        observed["mismatches"] = mismatches
        return False, observed
    return True, observed


def _expect(
    allowed: bool,
    reason: str,
    *,
    exposed: list[list[str]] | None = None,
    unsafe: list[str] | None = None,
    needs_preflight: bool = False,
    max_age: int | None = None,
) -> dict[str, object]:
    return {
        "allowed": allowed,
        "reason": reason,
        "exposed": exposed or [],
        "unsafe": unsafe or [],
        "needs_preflight": needs_preflight,
        "max_age": max_age,
    }


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
