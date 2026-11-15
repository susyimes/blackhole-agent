"""Accept negotiation uses the most specific matching range's quality.

A text/html variant keeps q=0.1 when text/* offers 0.8, so image/jpeg on
the star range wins. A parameter that does not match cannot borrow the
parameterized range's quality. Quality zero removes a variant. An empty
Accept value selects nothing.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without this choice is an unmet outcome.
"""

from __future__ import annotations

import json


SPECIFIC = "text/*;q=0.8, text/html;q=0.1, */*;q=0.5"
PARAMETER = "text/plain;format=flowed, text/plain;q=0.4, */*;q=0.5"


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.http_accept import negotiate_media_type
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases: dict[str, tuple[object, object]] = {
        "concrete_low_q_loses_to_star": (
            negotiate_media_type(SPECIFIC, ["text/html", "image/jpeg"]),
            {"ok": True, "selected": "image/jpeg", "quality_milli": 500},
        ),
        "text_star_still_covers_plain": (
            negotiate_media_type(SPECIFIC, ["text/plain", "image/jpeg"]),
            {"ok": True, "selected": "text/plain", "quality_milli": 800},
        ),
        "zero_quality_removes_html": (
            negotiate_media_type("text/html;q=0, */*;q=1", ["text/html", "text/plain"]),
            {"ok": True, "selected": "text/plain", "quality_milli": 1000},
        ),
        "unmatched_parameter_loses_to_star": (
            negotiate_media_type(PARAMETER, ["text/plain;format=fixed", "image/gif"]),
            {"ok": True, "selected": "image/gif", "quality_milli": 500},
        ),
        "matched_parameter_keeps_its_quality": (
            negotiate_media_type(
                PARAMETER,
                ["text/plain;format=fixed", "text/plain;format=flowed"],
            ),
            {"ok": True, "selected": "text/plain;format=flowed", "quality_milli": 1000},
        ),
        "parameterized_low_q_loses_to_plain": (
            negotiate_media_type(
                "text/html;q=0.2, text/html;level=1;q=0.1",
                ["text/html;level=1", "text/html"],
            ),
            {"ok": True, "selected": "text/html", "quality_milli": 200},
        ),
        "equal_quality_keeps_earlier_variant": (
            negotiate_media_type(
                "text/html;q=0.5, text/plain;q=0.5",
                ["text/plain", "text/html"],
            ),
            {"ok": True, "selected": "text/plain", "quality_milli": 500},
        ),
        "invalid_q_is_skipped": (
            negotiate_media_type(
                "text/css;q=1.001, text/html;q=1.000",
                ["text/css", "text/html"],
            ),
            {"ok": True, "selected": "text/html", "quality_milli": 1000},
        ),
        "quoted_charset_matches_ignoring_case": (
            negotiate_media_type(
                'Text/HTML;Charset="UTF-8"',
                ["text/plain;charset=utf-8", "text/html;charset=utf-8"],
            ),
            {"ok": True, "selected": "text/html;charset=utf-8", "quality_milli": 1000},
        ),
        "empty_accept_selects_nothing": (
            negotiate_media_type("", ["text/html", "image/jpeg"]),
            {"ok": True, "selected": "", "quality_milli": 0},
        ),
        "star_selects_the_first_variant": (
            negotiate_media_type("*/*", ["text/plain", "text/html"]),
            {"ok": True, "selected": "text/plain", "quality_milli": 1000},
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
