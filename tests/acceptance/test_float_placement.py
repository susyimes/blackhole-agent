"""Place floats and block formatting contexts.

A left float packs left and a right float packs right on the highest band
that does not intersect an earlier float. An automatic formatting context
takes the open gap. A fixed width that does not fit, and a float that follows
an in-flow context, move down. Clear names which earlier floats hold the box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the placer still exits 0.
"""

from __future__ import annotations

import json


def _box(name: str, side: str, width: object, height: int, clear: str = "none") -> dict[str, object]:
    box: dict[str, object] = {"id": name, "float": side, "width": width, "height": height}
    if clear != "none":
        box["clear"] = clear
    return box


def _at(name: str, x: int, y: int, width: int, height: int) -> dict[str, object]:
    return {"id": name, "x": x, "y": y, "width": width, "height": height}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_float_placement import place_floats
    except Exception as exc:  # noqa: BLE001 - baseline without the placer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, width: object, boxes: object) -> dict[str, object]:
        try:
            result = place_floats(width, boxes)
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    def placed(name: str, width: int, boxes: list[dict[str, object]], expected: list[dict[str, object]]) -> None:
        result = keep(name, width, boxes)
        checks.append(result.get("outcome") == "placed" and result.get("boxes") == expected)

    def invalid(name: str, width: object, boxes: object) -> None:
        result = keep(name, width, boxes)
        checks.append(result.get("outcome") == "invalid" and result.get("boxes") is None)

    placed(
        "left_pair",
        200,
        [_box("a", "left", 80, 40), _box("b", "left", 80, 40)],
        [_at("a", 0, 0, 80, 40), _at("b", 80, 0, 80, 40)],
    )
    placed(
        "left_wrap",
        100,
        [_box("a", "left", 80, 40), _box("b", "left", 80, 40)],
        [_at("a", 0, 0, 80, 40), _at("b", 0, 40, 80, 40)],
    )
    placed(
        "share_band",
        200,
        [_box("a", "left", 60, 50), _box("b", "right", 60, 30)],
        [_at("a", 0, 0, 60, 50), _at("b", 140, 0, 60, 30)],
    )
    placed(
        "right_drops",
        150,
        [_box("a", "left", 80, 100), _box("b", "right", 80, 40)],
        [_at("a", 0, 0, 80, 100), _at("b", 70, 100, 80, 40)],
    )
    placed(
        "auto_gap",
        300,
        [_box("a", "left", 100, 80), _box("b", "none", "auto", 40)],
        [_at("a", 0, 0, 100, 80), _at("b", 100, 0, 200, 40)],
    )
    placed(
        "fixed_clears",
        200,
        [_box("a", "left", 120, 50), _box("b", "none", 100, 20)],
        [_at("a", 0, 0, 120, 50), _at("b", 0, 50, 100, 20)],
    )
    placed(
        "held_under_block",
        200,
        [_box("a", "none", 200, 30), _box("b", "left", 40, 40)],
        [_at("a", 0, 0, 200, 30), _at("b", 0, 30, 40, 40)],
    )
    placed(
        "two_blocks_beside",
        200,
        [_box("a", "left", 50, 100), _box("b", "none", "auto", 30), _box("c", "none", "auto", 30)],
        [_at("a", 0, 0, 50, 100), _at("b", 50, 0, 150, 30), _at("c", 50, 30, 150, 30)],
    )
    placed(
        "clear_both",
        200,
        [
            _box("a", "left", 40, 30),
            _box("b", "right", 40, 50),
            _box("c", "none", "auto", 10, "both"),
        ],
        [_at("a", 0, 0, 40, 30), _at("b", 160, 0, 40, 50), _at("c", 0, 50, 200, 10)],
    )
    placed(
        "clear_left_keeps_right",
        200,
        [
            _box("a", "left", 40, 30),
            _box("b", "right", 40, 80),
            _box("c", "none", "auto", 10, "left"),
        ],
        [_at("a", 0, 0, 40, 30), _at("b", 160, 0, 40, 80), _at("c", 0, 30, 160, 10)],
    )
    placed(
        "slide_to_short_right",
        200,
        [_box("a", "left", 100, 100), _box("b", "right", 50, 20), _box("c", "left", 100, 20)],
        [_at("a", 0, 0, 100, 100), _at("b", 150, 0, 50, 20), _at("c", 100, 20, 100, 20)],
    )
    placed(
        "right_stack",
        100,
        [_box("a", "right", 80, 20), _box("b", "right", 80, 20)],
        [_at("a", 20, 0, 80, 20), _at("b", 20, 20, 80, 20)],
    )
    placed(
        "full_float_pushes_block",
        100,
        [_box("a", "left", 100, 30), _box("b", "none", "auto", 10)],
        [_at("a", 0, 0, 100, 30), _at("b", 0, 30, 100, 10)],
    )
    placed(
        "overwide_left",
        50,
        [_box("a", "left", 80, 10), _box("b", "left", 20, 10)],
        [_at("a", 0, 0, 80, 10), _at("b", 0, 10, 20, 10)],
    )
    placed(
        "clear_left_float",
        200,
        [_box("a", "left", 40, 25), _box("b", "left", 40, 25, "left")],
        [_at("a", 0, 0, 40, 25), _at("b", 0, 25, 40, 25)],
    )
    placed(
        "opposing_wrap",
        100,
        [_box("a", "left", 60, 40), _box("b", "right", 60, 40)],
        [_at("a", 0, 0, 60, 40), _at("b", 40, 40, 60, 40)],
    )
    placed(
        "float_under_short_block",
        200,
        [_box("a", "left", 50, 100), _box("b", "none", "auto", 20), _box("c", "left", 40, 40)],
        [_at("a", 0, 0, 50, 100), _at("b", 50, 0, 150, 20), _at("c", 50, 20, 40, 40)],
    )
    placed(
        "between_sides",
        200,
        [_box("a", "left", 30, 40), _box("b", "right", 50, 40), _box("c", "none", "auto", 15)],
        [_at("a", 0, 0, 30, 40), _at("b", 150, 0, 50, 40), _at("c", 30, 0, 120, 15)],
    )
    placed(
        "exact_gap",
        200,
        [_box("a", "left", 80, 40), _box("b", "none", 120, 10)],
        [_at("a", 0, 0, 80, 40), _at("b", 80, 0, 120, 10)],
    )
    placed(
        "overwide_right",
        50,
        [_box("a", "right", 80, 10)],
        [_at("a", -30, 0, 80, 10)],
    )

    invalid("negative_width", 200, [_box("a", "left", -5, 10)])
    invalid("negative_containing", -1, [_box("a", "left", 10, 10)])
    invalid("auto_float", 200, [_box("a", "left", "auto", 10)])
    invalid("duplicate", 200, [_box("a", "left", 10, 10), _box("a", "right", 10, 10)])

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
