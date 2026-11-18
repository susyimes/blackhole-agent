"""Place flex items after their main sizes are known.

justify-content packs a 260px line of three 40px items with a 10px gap.
A single item and a negative leftover change space-between and the other
distributions. align-items stretches only an automatic cross size. A nowrap
line keeps the container cross size. Wrap lines pack, stretch, and honor a
baseline. wrap-reverse reports those positions from the container's end.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without flex alignment still exits 0.
"""

from __future__ import annotations

import json


def _close(got: object, expected: float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _item(name: str, main: float, cross: object, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"id": name, "main": main, "cross": cross}
    row.update(extra)
    return row


def _matches(result: object, expected: list[dict[str, object]]) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "placed":
        return False
    lines = result.get("lines")
    if not isinstance(lines, list) or len(lines) != len(expected):
        return False
    for got_line, want_line in zip(lines, expected, strict=True):
        if not isinstance(got_line, dict):
            return False
        if not _close(got_line.get("cross"), float(want_line["cross"])):
            return False
        if not _close(got_line.get("cross_size"), float(want_line["cross_size"])):
            return False
        got_items = got_line.get("items")
        want_items = want_line["items"]
        if not isinstance(got_items, list) or not isinstance(want_items, list) or len(got_items) != len(want_items):
            return False
        for got, want in zip(got_items, want_items, strict=True):
            if not isinstance(got, dict) or got.get("id") != want["id"]:
                return False
            for key in ("main", "cross", "main_size", "cross_size", "margin_cross_start", "margin_cross_end"):
                if key in want and not _close(got.get(key), float(want[key])):
                    return False
    return True


def _invalid(result: object) -> bool:
    return isinstance(result, dict) and result.get("outcome") == "invalid" and result.get("lines") is None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_flex_align import place_flex_alignment
    except Exception as exc:  # noqa: BLE001 - baseline without alignment still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, *args: object, **kwargs: object) -> dict[str, object]:
        try:
            result = place_flex_alignment(*args, **kwargs)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    def keep(name: str, *args: object, expected: list[dict[str, object]], **kwargs: object) -> None:
        checks.append(_matches(place(name, *args, **kwargs), expected))

    trio = [
        [
            _item("a", 40, 10),
            _item("b", 40, 10),
            _item("c", 40, 10),
        ]
    ]

    def mains(name: str, justify: str, positions: tuple[float, float, float]) -> None:
        keep(
            name,
            260,
            100,
            trio,
            justify_content=justify,
            align_items="flex-start",
            wrap="nowrap",
            main_gap=10,
            expected=[
                {
                    "cross": 0,
                    "cross_size": 100,
                    "items": [
                        {"id": "a", "main": positions[0], "cross": 0, "main_size": 40, "cross_size": 10},
                        {"id": "b", "main": positions[1], "cross": 0, "main_size": 40, "cross_size": 10},
                        {"id": "c", "main": positions[2], "cross": 0, "main_size": 40, "cross_size": 10},
                    ],
                }
            ],
        )

    mains("flex_start", "flex-start", (0, 50, 100))
    mains("normal_justify", " normal ", (0, 50, 100))
    mains("flex_end", " Flex-End ", (120, 170, 220))
    mains("center", "center", (60, 110, 160))
    mains("space_between", "space-between", (0, 110, 220))
    mains("space_around", "space-around", (20, 110, 200))
    mains("space_evenly", "space-evenly", (30, 110, 190))

    alone = [[_item("a", 40, 10)]]
    keep(
        "single_space_between",
        300,
        100,
        alone,
        justify_content="space-between",
        align_items="flex-start",
        expected=[{"cross": 0, "cross_size": 100, "items": [{"id": "a", "main": 0, "cross": 0, "cross_size": 10}]}],
    )
    keep(
        "single_space_around",
        300,
        100,
        alone,
        justify_content="space-around",
        align_items="flex-start",
        expected=[{"cross": 0, "cross_size": 100, "items": [{"id": "a", "main": 130, "cross": 0, "cross_size": 10}]}],
    )
    keep(
        "single_space_evenly",
        300,
        100,
        alone,
        justify_content="space-evenly",
        align_items="flex-start",
        expected=[{"cross": 0, "cross_size": 100, "items": [{"id": "a", "main": 130, "cross": 0, "cross_size": 10}]}],
    )

    wide = [[_item("a", 80, 10), _item("b", 80, 10)]]
    keep(
        "negative_space_between",
        100,
        50,
        wide,
        justify_content="space-between",
        align_items="flex-start",
        expected=[
            {
                "cross": 0,
                "cross_size": 50,
                "items": [
                    {"id": "a", "main": 0, "cross": 0, "cross_size": 10},
                    {"id": "b", "main": 80, "cross": 0, "cross_size": 10},
                ],
            }
        ],
    )
    keep(
        "negative_space_around",
        100,
        50,
        wide,
        justify_content="space-around",
        align_items="flex-start",
        expected=[
            {
                "cross": 0,
                "cross_size": 50,
                "items": [
                    {"id": "a", "main": -30, "cross": 0, "cross_size": 10},
                    {"id": "b", "main": 50, "cross": 0, "cross_size": 10},
                ],
            }
        ],
    )
    keep(
        "negative_flex_end",
        100,
        50,
        wide,
        justify_content="flex-end",
        align_items="flex-start",
        expected=[
            {
                "cross": 0,
                "cross_size": 50,
                "items": [
                    {"id": "a", "main": -60, "cross": 0, "cross_size": 10},
                    {"id": "b", "main": 20, "cross": 0, "cross_size": 10},
                ],
            }
        ],
    )

    def one(
        name: str,
        item: dict[str, object],
        *,
        cross: float,
        size: float,
        margin_start: float,
        margin_end: float,
        align_items: str = "stretch",
    ) -> None:
        keep(
            name,
            100,
            100,
            [[item]],
            align_items=align_items,
            align_content="flex-end",
            wrap="nowrap",
            expected=[
                {
                    "cross": 0,
                    "cross_size": 100,
                    "items": [
                        {
                            "id": "a",
                            "main": 0,
                            "cross": cross,
                            "cross_size": size,
                            "margin_cross_start": margin_start,
                            "margin_cross_end": margin_end,
                        }
                    ],
                }
            ],
        )

    one("stretch", _item("a", 10, "auto", content=20), cross=0, size=100, margin_start=0, margin_end=0)
    one(
        "normal_items",
        _item("a", 10, "auto", content=20),
        cross=0,
        size=100,
        margin_start=0,
        margin_end=0,
        align_items="normal",
    )
    one(
        "flex_start_cross",
        _item("a", 10, "auto", content=20),
        cross=0,
        size=20,
        margin_start=0,
        margin_end=0,
        align_items="flex-start",
    )
    one(
        "flex_end_cross",
        _item("a", 10, "auto", content=20),
        cross=80,
        size=20,
        margin_start=0,
        margin_end=0,
        align_items="flex-end",
    )
    one(
        "center_cross",
        _item("a", 10, "auto", content=20),
        cross=40,
        size=20,
        margin_start=0,
        margin_end=0,
        align_items="center",
    )
    one(
        "self_overrides_stretch",
        _item("a", 10, "auto", content=20, align_self="flex-end"),
        cross=80,
        size=20,
        margin_start=0,
        margin_end=0,
    )
    one("definite_does_not_stretch", _item("a", 10, 30), cross=0, size=30, margin_start=0, margin_end=0)
    one(
        "max_caps_stretch",
        _item("a", 10, "auto", content=10, max_cross=50),
        cross=0,
        size=50,
        margin_start=0,
        margin_end=0,
    )
    one(
        "min_forces_overflow",
        _item("a", 10, "auto", content=10, min_cross=120),
        cross=0,
        size=120,
        margin_start=0,
        margin_end=0,
    )
    one(
        "minimum_wins",
        _item("a", 10, "auto", content=10, min_cross=80, max_cross=20),
        cross=0,
        size=80,
        margin_start=0,
        margin_end=0,
    )
    one(
        "auto_start_margin",
        _item("a", 10, "auto", content=20, margin_cross_start="auto"),
        cross=0,
        size=20,
        margin_start=80,
        margin_end=0,
    )
    one(
        "two_auto_margins",
        _item("a", 10, "auto", content=20, margin_cross_start="auto", margin_cross_end="auto"),
        cross=0,
        size=20,
        margin_start=40,
        margin_end=40,
    )
    one(
        "auto_margin_overflow",
        _item("a", 10, "auto", content=150, margin_cross_start="auto"),
        cross=0,
        size=150,
        margin_start=0,
        margin_end=0,
    )
    one(
        "center_includes_margins",
        _item("a", 10, 20, margin_cross_start=4, margin_cross_end=6),
        cross=35,
        size=20,
        margin_start=4,
        margin_end=6,
        align_items="center",
    )

    keep(
        "nowrap_align_content_stays",
        100,
        100,
        [[_item("a", 10, 20)]],
        align_items="flex-start",
        align_content="flex-end",
        wrap="nowrap",
        expected=[{"cross": 0, "cross_size": 100, "items": [{"id": "a", "main": 0, "cross": 0, "cross_size": 20}]}],
    )
    keep(
        "wrap_one_line_flex_end",
        100,
        100,
        [[_item("a", 10, 30)]],
        align_items="flex-start",
        align_content="flex-end",
        wrap="wrap",
        expected=[{"cross": 70, "cross_size": 30, "items": [{"id": "a", "main": 0, "cross": 70, "cross_size": 30}]}],
    )
    keep(
        "wrap_one_line_space_between",
        100,
        100,
        [[_item("a", 10, 30)]],
        align_items="flex-start",
        align_content="space-between",
        wrap="wrap",
        expected=[{"cross": 0, "cross_size": 30, "items": [{"id": "a", "main": 0, "cross": 0, "cross_size": 30}]}],
    )
    keep(
        "wrap_one_line_space_around",
        100,
        100,
        [[_item("a", 10, 30)]],
        align_items="flex-start",
        align_content="space-around",
        wrap="wrap",
        expected=[{"cross": 35, "cross_size": 30, "items": [{"id": "a", "main": 0, "cross": 35, "cross_size": 30}]}],
    )

    pair = [[_item("a", 10, 30)], [_item("b", 10, 10)]]

    def packed(name: str, content: str, first: float, second: float, first_size: float, second_size: float) -> None:
        keep(
            name,
            100,
            100,
            pair,
            align_items="flex-start",
            align_content=content,
            wrap="wrap",
            expected=[
                {
                    "cross": first,
                    "cross_size": first_size,
                    "items": [{"id": "a", "main": 0, "cross": first, "cross_size": 30}],
                },
                {
                    "cross": second,
                    "cross_size": second_size,
                    "items": [{"id": "b", "main": 0, "cross": second, "cross_size": 10}],
                },
            ],
        )

    packed("wrap_stretch", "stretch", 0, 60, 60, 40)
    keep(
        "wrap_stretch_grows_auto_items",
        100,
        100,
        [[_item("a", 10, "auto", content=30)], [_item("b", 10, "auto", content=10)]],
        align_items="stretch",
        align_content="stretch",
        wrap="wrap",
        expected=[
            {"cross": 0, "cross_size": 60, "items": [{"id": "a", "main": 0, "cross": 0, "cross_size": 60}]},
            {"cross": 60, "cross_size": 40, "items": [{"id": "b", "main": 0, "cross": 60, "cross_size": 40}]},
        ],
    )
    packed("normal_content", "normal", 0, 60, 60, 40)
    packed("wrap_flex_end", "flex-end", 60, 90, 30, 10)
    packed("wrap_space_between", "space-between", 0, 90, 30, 10)
    packed("wrap_space_around", "space-around", 15, 75, 30, 10)
    packed("wrap_space_evenly", "space-evenly", 20, 70, 30, 10)
    packed("wrap_center", "center", 30, 60, 30, 10)
    keep(
        "cross_gap",
        100,
        100,
        pair,
        align_items="flex-start",
        align_content="flex-start",
        wrap="wrap",
        cross_gap=20,
        expected=[
            {"cross": 0, "cross_size": 30, "items": [{"id": "a", "main": 0, "cross": 0, "cross_size": 30}]},
            {"cross": 50, "cross_size": 10, "items": [{"id": "b", "main": 0, "cross": 50, "cross_size": 10}]},
        ],
    )
    keep(
        "stretch_keeps_gap",
        100,
        100,
        pair,
        align_items="flex-start",
        align_content="stretch",
        wrap="wrap",
        cross_gap=20,
        expected=[
            {"cross": 0, "cross_size": 50, "items": [{"id": "a", "main": 0, "cross": 0, "cross_size": 30}]},
            {"cross": 70, "cross_size": 30, "items": [{"id": "b", "main": 0, "cross": 70, "cross_size": 10}]},
        ],
    )
    keep(
        "baseline_wrap",
        100,
        200,
        [[_item("a", 10, 40, align_self="baseline", baseline=10), _item("b", 10, 40, align_self="baseline", baseline=25)]],
        align_items="flex-start",
        align_content="flex-start",
        wrap="wrap",
        expected=[
            {
                "cross": 0,
                "cross_size": 55,
                "items": [
                    {"id": "a", "main": 0, "cross": 15, "cross_size": 40},
                    {"id": "b", "main": 10, "cross": 0, "cross_size": 40},
                ],
            }
        ],
    )
    keep(
        "baseline_nowrap",
        100,
        100,
        [[_item("a", 10, 40, align_self="baseline", baseline=10), _item("b", 10, 40, align_self="baseline", baseline=25)]],
        align_items="flex-start",
        align_content="flex-start",
        wrap="nowrap",
        expected=[
            {
                "cross": 0,
                "cross_size": 100,
                "items": [
                    {"id": "a", "main": 0, "cross": 15, "cross_size": 40},
                    {"id": "b", "main": 10, "cross": 0, "cross_size": 40},
                ],
            }
        ],
    )
    keep(
        "baseline_margins",
        100,
        200,
        [
            [
                _item("a", 10, 30, margin_cross_start=10, align_self="baseline", baseline=16),
                _item("b", 10, 30, align_self="baseline", baseline=20),
                _item("c", 10, 50, align_self="flex-start"),
            ]
        ],
        align_items="flex-start",
        align_content="flex-start",
        wrap="wrap",
        main_gap=0,
        expected=[
            {
                "cross": 0,
                "cross_size": 50,
                "items": [
                    {"id": "a", "main": 0, "cross": 4, "cross_size": 30, "margin_cross_start": 10},
                    {"id": "b", "main": 10, "cross": 0, "cross_size": 30, "margin_cross_start": 0},
                    {"id": "c", "main": 20, "cross": 0, "cross_size": 50, "margin_cross_start": 0},
                ],
            }
        ],
    )
    keep(
        "wrap_reverse",
        100,
        100,
        [[_item("a", 10, 30), _item("b", 10, 10)], [_item("c", 10, 10)]],
        align_items="flex-start",
        align_content="flex-start",
        wrap="wrap-reverse",
        expected=[
            {
                "cross": 70,
                "cross_size": 30,
                "items": [
                    {"id": "a", "main": 0, "cross": 70, "cross_size": 30},
                    {"id": "b", "main": 10, "cross": 90, "cross_size": 10},
                ],
            },
            {"cross": 60, "cross_size": 10, "items": [{"id": "c", "main": 0, "cross": 60, "cross_size": 10}]},
        ],
    )
    keep(
        "per_line_single_fallback",
        260,
        100,
        [trio[0], [_item("d", 40, 10)]],
        justify_content="space-between",
        align_items="flex-start",
        align_content="flex-start",
        wrap="wrap",
        main_gap=10,
        expected=[
            {
                "cross": 0,
                "cross_size": 10,
                "items": [
                    {"id": "a", "main": 0, "cross": 0, "cross_size": 10},
                    {"id": "b", "main": 110, "cross": 0, "cross_size": 10},
                    {"id": "c", "main": 220, "cross": 0, "cross_size": 10},
                ],
            },
            {"cross": 10, "cross_size": 10, "items": [{"id": "d", "main": 0, "cross": 10, "cross_size": 10}]},
        ],
    )
    empty = place("empty", 100, 100, [])
    checks.append(isinstance(empty, dict) and empty.get("outcome") == "placed" and empty.get("lines") == [])

    checks.append(_invalid(place("boolean_container", True, 100, [])))
    checks.append(_invalid(place("unknown_keyword", 100, 100, alone, justify_content="distribute")))
    checks.append(_invalid(place("duplicate_id", 100, 100, [[_item("a", 10, 10), _item("a", 10, 10)]])))
    checks.append(_invalid(place("negative_gap", 100, 100, alone, main_gap=-1)))
    checks.append(_invalid(place("nowrap_two_lines", 100, 100, pair, wrap="nowrap")))
    checks.append(_invalid(place("empty_line", 100, 100, [[]])))
    checks.append(_invalid(place("auto_without_content", 100, 100, [[_item("a", 10, "auto")]])))
    checks.append(_invalid(place("negative_baseline", 100, 100, [[_item("a", 10, 10, baseline=-1)]])))
    checks.append(_invalid(place("negative_cross", 100, 100, [[_item("a", 10, -5)]])))
    checks.append(_invalid(place("nan_container", float("nan"), 100, [])))

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
