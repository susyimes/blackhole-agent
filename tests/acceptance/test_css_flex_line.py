"""Resolve used main sizes on one definite flex line.

Grow, scaled shrink, a frozen min or max, a flex factor below one, a gap,
and a margin each change an item's used main size. A negative container is
rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the resolver still exits 0.
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
    got = result.get("main_sizes")
    if not isinstance(got, list) or len(got) != len(expected):
        return False
    return all(_close(item, want) for item, want in zip(got, expected))


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_flex_line import resolve_flex_line
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, container: object, items: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
        try:
            result = resolve_flex_line(container, items, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised resolve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    pair = [{"base": 100, "grow": 1, "shrink": 1}, {"base": 100, "grow": 1, "shrink": 1}]
    checks.append(_sizes(keep("grow_equal", 300, pair), (150, 150)))
    checks.append(_sizes(keep("shrink_equal", 100, pair), (50, 50)))
    checks.append(
        _sizes(
            keep(
                "grow_ratio",
                400,
                [{"base": 0, "grow": 1, "shrink": 1}, {"base": 0, "grow": 3, "shrink": 1}],
            ),
            (100, 300),
        )
    )
    checks.append(
        _sizes(
            keep(
                "min_restarts",
                100,
                [
                    {"base": 80, "grow": 1, "shrink": 1, "minimum": 60},
                    {"base": 80, "grow": 1, "shrink": 1, "minimum": 0},
                ],
            ),
            (60, 40),
        )
    )
    checks.append(
        _sizes(
            keep(
                "max_restarts",
                500,
                [
                    {"base": 100, "grow": 1, "shrink": 1, "maximum": 120},
                    {"base": 100, "grow": 1, "shrink": 1, "maximum": "none"},
                ],
            ),
            (120, 380),
        )
    )
    checks.append(
        _sizes(
            keep(
                "zero_grow",
                300,
                [{"base": 100, "grow": 0, "shrink": 1}, {"base": 100, "grow": 1, "shrink": 1}],
            ),
            (100, 200),
        )
    )
    checks.append(
        _sizes(
            keep(
                "partial_grow",
                300,
                [{"base": 100, "grow": 0.25, "shrink": 1}, {"base": 100, "grow": 0.25, "shrink": 1}],
            ),
            (125, 125),
        )
    )
    checks.append(
        _sizes(
            keep(
                "partial_shrink",
                100,
                [{"base": 100, "grow": 1, "shrink": 0.25}, {"base": 100, "grow": 1, "shrink": 0.25}],
            ),
            (75, 75),
        )
    )
    checks.append(
        _sizes(
            keep(
                "inflexible_max",
                500,
                [
                    {"base": 300, "grow": 0.5, "shrink": 1, "maximum": 100},
                    {"base": 100, "grow": 0.5, "shrink": 1},
                ],
            ),
            (100, 250),
        )
    )
    checks.append(
        _sizes(
            keep(
                "margin_shrink",
                80,
                [
                    {"base": 40, "grow": 0, "shrink": 1, "margin": 20},
                    {"base": 40, "grow": 0, "shrink": 1, "margin": 0},
                ],
            ),
            (30, 30),
        )
    )
    checks.append(
        _sizes(
            keep("gap_grow", 300, [{"base": 100, "grow": 1, "shrink": 1}, {"base": 100, "grow": 1, "shrink": 1}], gap=20),
            (140, 140),
        )
    )
    checks.append(
        _sizes(
            keep(
                "gap_scaled_shrink",
                210,
                [{"base": 100, "grow": 1, "shrink": 1}, {"base": 100, "grow": 1, "shrink": 3}],
                gap=20,
            ),
            (97.5, 92.5),
        )
    )
    checks.append(
        _sizes(
            keep(
                "zero_grow_at_max",
                200,
                [
                    {"base": 100, "grow": 0, "shrink": 1, "maximum": 50},
                    {"base": 50, "grow": 1, "shrink": 1},
                ],
            ),
            (50, 150),
        )
    )
    checks.append(
        _sizes(
            keep(
                "min_above_max",
                200,
                [
                    {"base": 50, "grow": 1, "shrink": 1, "minimum": 80, "maximum": 40},
                    {"base": 50, "grow": 1, "shrink": 1},
                ],
            ),
            (80, 120),
        )
    )
    checks.append(
        _sizes(
            keep("zero_shrink_holds", 100, [{"base": 80, "grow": 1, "shrink": 0}, {"base": 80, "grow": 1, "shrink": 1}]),
            (80, 20),
        )
    )
    checks.append(_sizes(keep("gap_ignored_for_one", 100, [{"base": 40, "grow": 1, "shrink": 1}], gap=50), (100,)))

    negative = keep("negative_container", -1, [{"base": 10, "grow": 1}])
    checks.append(negative.get("outcome") == "invalid" and negative.get("main_sizes") is None)
    bad_grow = keep("negative_grow", 100, [{"base": 10, "grow": -1}])
    checks.append(bad_grow.get("outcome") == "invalid" and bad_grow.get("main_sizes") is None)

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
