"""Size CSS grid tracks from min-content and max-content contributions.

The CSS grid example is two minmax(min-content, max-content) tracks. An item
of 10 sits in the first. A spanning item has min-content 30 and max-content
100. Max-content leaves the tracks at 10 and 90. Min-content leaves them at
10 and 20. A span of 100 across a 40px track and an auto track is 40 and 60,
and the same span with a 10px gap is 40 and 50. A span of 100 across two
empty auto tracks is 50 and 50. Available 200 with stretch turns auto tracks
whose growth limits are 40 and 60 into 90 and 110. Max-content leaves those
tracks at 40 and 60, and min-content leaves them at 10 and 20. A fixed maximum
of 20 holds a max-content contribution of 80 at 20. fit-content(30) holds
that contribution at 30. A definite container with no free space uses the
minimum contribution of 10, while the min-content constraint uses 40. Two
quarter-fr tracks in 100px are 25 and 25. Two 1fr tracks crossed by a 150
minimum in 100px are 75 and 75. An empty track list, a span past the end, a
boolean contribution, and an unknown sizing function have no sizes.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def _close(got: object, expected: int | float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - float(expected)) <= 1e-6


def _sizes(result: object, expected: tuple[int | float, ...]) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    got = result.get("track_sizes")
    if not isinstance(got, list) or len(got) != len(expected):
        return False
    return all(_close(item, want) for item, want in zip(got, expected))


def _invalid(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("track_sizes") is None
        and result.get("container") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_grid_content import size_content_grid_tracks
    except Exception as exc:  # noqa: BLE001 - baseline without the solver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []
    minmax = {"minimum": "min-content", "maximum": "max-content"}
    auto = {"breadth": "auto"}

    def keep(
        name: str,
        available: object,
        tracks: list[dict[str, object]],
        items: list[dict[str, object]],
        **kwargs: object,
    ) -> dict[str, object]:
        try:
            result = size_content_grid_tracks(available, tracks, items, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    salas = [
        {"start": 0, "span": 1, "min_content": 10, "max_content": 10},
        {"start": 0, "span": 2, "min_content": 30, "max_content": 100},
    ]
    checks.append(_sizes(keep("salas_max_content", "max-content", [minmax, minmax], salas), (10, 90)))
    checks.append(_sizes(keep("salas_min_content", "min-content", [minmax, minmax], salas), (10, 20)))

    span = [{"start": 0, "span": 2, "min_content": 100, "max_content": 100}]
    checks.append(_sizes(keep("fixed_and_auto", "max-content", [{"fixed": 40}, auto], span), (40, 60)))
    checks.append(
        _sizes(keep("fixed_and_auto_gap", "max-content", [{"fixed": 40}, auto], span, gap=10), (40, 50))
    )
    checks.append(_sizes(keep("two_empty_autos", 100, [auto, auto], span), (50, 50)))

    pair = [
        {"start": 0, "span": 1, "min_content": 10, "max_content": 40},
        {"start": 1, "span": 1, "min_content": 20, "max_content": 60},
    ]
    checks.append(_sizes(keep("stretch_autos", 200, [auto, auto], pair, stretch=True), (90, 110)))
    checks.append(_sizes(keep("max_content_autos", "max-content", [auto, auto], pair), (40, 60)))
    checks.append(_sizes(keep("min_content_autos", "min-content", [auto, auto], pair), (10, 20)))

    capped = [{"start": 0, "span": 1, "min_content": 10, "max_content": 80}]
    checks.append(
        _sizes(keep("fixed_maximum", 500, [{"minimum": "auto", "maximum": 20}], capped), (20,))
    )
    checks.append(_sizes(keep("fit_content", 200, [{"fit_content": 30}], capped, stretch=True), (30,)))

    distinct = [{"min_content": 40, "max_content": 80, "minimum": 10}]
    checks.append(_sizes(keep("definite_minimum", 0, [auto], distinct), (10,)))
    checks.append(_sizes(keep("constraint_min_content", "min-content", [auto], distinct), (40,)))

    checks.append(_sizes(keep("partial_fr", 100, [{"flex": 0.25}, {"flex": 0.25}], []), (25, 25)))
    checks.append(
        _sizes(
            keep(
                "flex_span_minimum",
                100,
                [{"flex": 1}, {"flex": 1}],
                [{"start": 0, "span": 2, "min_content": 150, "max_content": 150}],
            ),
            (75, 75),
        )
    )

    checks.append(_invalid(keep("empty_tracks", 10, [], [])))
    checks.append(_invalid(keep("span_past_end", 10, [auto], span)))
    checks.append(
        _invalid(keep("boolean_contribution", 10, [auto], [{"min_content": True, "max_content": 1}]))
    )
    checks.append(_invalid(keep("unknown_sizing", 10, [{"breadth": "content"}], [])))

    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
