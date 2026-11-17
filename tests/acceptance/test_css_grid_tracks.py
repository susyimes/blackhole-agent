"""Size one definite CSS grid axis.

A minmax track reaches its maximum before an fr track takes what remains.
Fr factors that sum to less than one leave space empty. A base larger than
its fr share is held. A spanning minimum is distributed by fr ratio, or with
the remainder shared equally when the factors sum to less than one, and the
gap inside the span counts. A negative available size is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the solver still exits 0.
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


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_grid_tracks import size_grid_tracks
    except Exception as exc:  # noqa: BLE001 - baseline without the solver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(
        name: str,
        available: object,
        tracks: list[dict[str, object]],
        items: list[dict[str, object]],
        **kwargs: object,
    ) -> dict[str, object]:
        try:
            result = size_grid_tracks(available, tracks, items, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    checks.append(
        _sizes(
            keep("minmax_before_fr", 200, [{"minimum": 20, "maximum": 80}, {"flex": 1}], []),
            (80, 120),
        )
    )
    checks.append(_sizes(keep("partial_fr", 100, [{"flex": 0.25}, {"flex": 0.25}], []), (25, 25)))
    checks.append(
        _sizes(
            keep("base_exceeds_share", 100, [{"flex": 1, "minimum": 80}, {"flex": 1, "minimum": 0}], []),
            (80, 20),
        )
    )
    span_both = [{"start": 0, "span": 2, "minimum": 150}]
    checks.append(_sizes(keep("span_overflow", 100, [{"flex": 1}, {"flex": 1}], span_both), (75, 75)))
    checks.append(
        _sizes(keep("span_gap", 100, [{"flex": 1}, {"flex": 1}], span_both, gap=10), (70, 70))
    )
    checks.append(
        _sizes(
            keep(
                "span_ratio",
                80,
                [{"flex": 1}, {"flex": 3}],
                [{"start": 0, "span": 2, "minimum": 80}],
            ),
            (20, 60),
        )
    )
    checks.append(
        _sizes(
            keep(
                "span_partial_rest",
                100,
                [{"flex": 0.2}, {"flex": 0.6}],
                [{"start": 0, "span": 2, "minimum": 100}],
            ),
            (30, 70),
        )
    )
    checks.append(
        _sizes(
            keep("maximize_refreeze", 100, [{"minimum": 0, "maximum": 10}, {"minimum": 0, "maximum": 100}], []),
            (10, 90),
        )
    )
    checks.append(
        _sizes(
            keep(
                "maximize_then_fr",
                150,
                [{"minimum": 0, "maximum": 10}, {"minimum": 0, "maximum": 100}, {"flex": 1}],
                [],
            ),
            (10, 100, 40),
        )
    )
    checks.append(
        _sizes(keep("gap_before_fr", 100, [{"fixed": 30}, {"flex": 1}], [], gap=10), (30, 60))
    )
    checks.append(_sizes(keep("fixed_no_stretch", 100, [{"fixed": 40}, {"fixed": 40}], []), (40, 40)))
    checks.append(
        _sizes(
            keep("minmax_stops", 100, [{"minimum": 10, "maximum": 40}, {"minimum": 10, "maximum": 40}], []),
            (40, 40),
        )
    )
    checks.append(_sizes(keep("fr_ratio", 400, [{"flex": 1}, {"flex": 3}], []), (100, 300)))
    checks.append(
        _sizes(keep("zero_fr_minimum", 100, [{"flex": 0, "minimum": 25}, {"flex": 1}], []), (25, 75))
    )
    checks.append(
        _sizes(
            keep("two_gutters", 260, [{"flex": 1}, {"flex": 1}, {"flex": 1}], [], gap=20),
            (220 / 3, 220 / 3, 220 / 3),
        )
    )

    negative = keep("negative_available", -1, [{"flex": 1}], [])
    checks.append(negative.get("outcome") == "invalid" and negative.get("track_sizes") is None)
    bad_flex = keep("negative_flex", 100, [{"flex": -1}], [])
    checks.append(bad_flex.get("outcome") == "invalid" and bad_flex.get("track_sizes") is None)
    outside = keep("span_outside", 100, [{"flex": 1}], [{"start": 0, "span": 2, "minimum": 10}])
    checks.append(outside.get("outcome") == "invalid" and outside.get("track_sizes") is None)

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
