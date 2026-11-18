"""Content holds a flex item's automatic minimum.

A scrollable main axis floors at zero. A preferred main size and a maximum
cap the content floor. A non-replaced item keeps the larger of its content
and its transferred cross size; a replaced item keeps the smaller. On one
line, that floor stops a shrink which an explicit zero still allows.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the automatic minimum still exits 0.
"""

from __future__ import annotations

import json


def _close(got: object, expected: float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _minimum(result: object, expected: float) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "definite"
        and _close(result.get("minimum"), expected)
    )


def _sizes(result: object, expected: list[float]) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    got = result.get("main_sizes")
    if not isinstance(got, list) or len(got) != len(expected):
        return False
    return all(_close(item, want) for item, want in zip(got, expected))


def _invalid(result: object) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "invalid":
        return False
    return result.get("minimum", result.get("main_sizes")) is None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_flex_line import resolve_flex_line
        from blackhole_agent.css_flex_minimum import automatic_flex_minimum
    except Exception as exc:  # noqa: BLE001 - baseline without the floor still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def floor(name: str, content: object, **kwargs: object) -> dict[str, object]:
        try:
            result = automatic_flex_minimum(content, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    def line(name: str, container: object, items: object) -> dict[str, object]:
        try:
            result = resolve_flex_line(container, items)
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    content = floor("content_holds", 80)
    checks.append(_minimum(content, 80))
    checks.append(content.get("content_suggestion") == 80)
    checks.append(content.get("transferred_suggestion") is None)

    checks.append(_minimum(floor("scrollable_is_zero", 80, scrollable=True), 0))
    checks.append(floor("scrollable_is_zero", 80, scrollable=True).get("content_suggestion") is None)

    capped = floor("specified_caps_content", 80, specified=40)
    checks.append(_minimum(capped, 40))
    checks.append(capped.get("specified_suggestion") == 40)

    checks.append(_minimum(floor("maximum_caps_content", 80, maximum=25), 25))
    checks.append(floor("maximum_caps_content", 80, maximum=25).get("content_suggestion") == 80)

    non_replaced = floor("non_replaced_takes_transferred", 40, ratio=2, cross=50)
    checks.append(_minimum(non_replaced, 100))
    checks.append(non_replaced.get("transferred_suggestion") == 100)
    checks.append(_minimum(floor("replaced_takes_content", 40, ratio=2, cross=50, replaced=True), 40))
    checks.append(_minimum(floor("specified_caps_transferred", 40, ratio=2, cross=50, specified=70), 70))
    checks.append(
        _minimum(floor("replaced_specified_caps", 90, ratio=2, cross=50, specified=70, replaced=True), 70)
    )

    clamped = floor("cross_minimum_raises_content", 10, ratio=2, cross_minimum=30)
    checks.append(_minimum(clamped, 60))
    checks.append(clamped.get("content_suggestion") == 60)
    checks.append(clamped.get("transferred_suggestion") is None)

    transferred = floor("cross_maximum_limits_transfer", 10, ratio=2, cross=100, cross_maximum=40)
    checks.append(_minimum(transferred, 80))
    checks.append(transferred.get("content_suggestion") == 10)
    checks.append(transferred.get("transferred_suggestion") == 80)

    inverted = floor("cross_minimum_wins_over_cross_maximum", 10, ratio=2, cross_minimum=50, cross_maximum=10)
    checks.append(_minimum(inverted, 100))

    checks.append(_invalid(floor("negative_content", -1)))
    checks.append(_invalid(floor("boolean_content", True)))
    checks.append(_invalid(floor("zero_ratio", 10, ratio=0)))
    checks.append(_invalid(floor("bad_replaced", 10, replaced=1)))

    held = line("auto_floor_stops_shrink", 50, [{"base": 100, "minimum": "auto", "content": 80}])
    checks.append(_sizes(held, [80]))
    zero = line("explicit_zero_shrinks", 50, [{"base": 100, "minimum": 0, "content": 80}])
    checks.append(_sizes(zero, [50]))
    pair = line(
        "auto_neighbor_keeps_its_base",
        100,
        [
            {"base": 60, "minimum": "auto", "content": 60},
            {"base": 60, "minimum": 0},
        ],
    )
    checks.append(_sizes(pair, [60, 40]))
    checks.append(
        _sizes(
            line(
                "maximum_caps_the_floor_on_the_line",
                10,
                [{"base": 100, "minimum": "auto", "content": 80, "maximum": 25}],
            ),
            [25],
        )
    )
    checks.append(
        _sizes(
            line(
                "transferred_floor_on_the_line",
                30,
                [{"base": 200, "minimum": "auto", "content": 40, "ratio": 2, "cross": 50}],
            ),
            [100],
        )
    )
    checks.append(
        _sizes(
            line(
                "replaced_floor_on_the_line",
                30,
                [{"base": 200, "minimum": "auto", "content": 40, "ratio": 2, "cross": 50, "replaced": True}],
            ),
            [40],
        )
    )
    checks.append(_sizes(line("auto_still_grows", 200, [{"base": 40, "grow": 1, "minimum": "auto", "content": 10}]), [200]))
    checks.append(_sizes(line("auto_raises_a_short_base", 100, [{"base": 10, "grow": 0, "minimum": "auto", "content": 25}]), [25]))
    checks.append(_invalid(line("auto_without_content", 50, [{"base": 100, "minimum": "auto"}])))

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
