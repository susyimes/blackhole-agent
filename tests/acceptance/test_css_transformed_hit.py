"""Hit-test a physical point against a CSS transformed border box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without transformed hit testing still exits 0.
"""

from __future__ import annotations

import json


def _box(identity: str, x: float, y: float, width: float, height: float, **extra: object) -> dict[str, object]:
    return {"id": identity, "x": x, "y": y, "width": width, "height": height, **extra}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_hit_test import element_from_point
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, tree: dict[str, object], x: float, y: float) -> dict[str, object]:
        try:
            result = element_from_point(tree, x, y)
        except Exception as exc:  # noqa: BLE001 - a raised hit is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"outcome": "error"}
        observed[name] = {
            "outcome": result.get("outcome"),
            "id": result.get("id"),
            "reason": result.get("reason"),
        }
        return result

    def expect(name: str, tree: dict[str, object], x: float, y: float, outcome: str, ident: str | None) -> None:
        result = place(name, tree, x, y)
        checks.append(result.get("outcome") == outcome and result.get("id") == ident)

    turned = _box("box", 0, 0, 20, 20, transform="rotate(90deg)", origin="0px 0px")
    expect("quarter_inside", turned, 0, 10, "hit", "box")
    expect("quarter_old_inside", turned, 10, 0, "miss", None)
    expect("quarter_excluded_edge", turned, 0, 20, "miss", None)

    shift_then_turn = _box(
        "shift",
        0,
        0,
        10,
        10,
        transform="translate(30px, 0px) rotate(90deg)",
        origin="0px 0px",
    )
    expect("shift_then_turn_hit", shift_then_turn, 0, 30, "hit", "shift")
    expect("shift_then_turn_miss", shift_then_turn, 30, 0, "miss", None)

    turn_then_shift = _box(
        "turn",
        0,
        0,
        10,
        10,
        transform="rotate(90deg) translate(30px, 0px)",
        origin="0px 0px",
    )
    expect("turn_then_shift_hit", turn_then_shift, 30, 0, "hit", "turn")
    expect("turn_then_shift_miss", turn_then_shift, 0, 30, "miss", None)

    nested = _box(
        "outer",
        100,
        40,
        10,
        10,
        transform="translate(5px, 0px)",
        origin="0px 0px",
        children=[
            _box("inner", 110, 60, 20, 10, transform="rotate(90deg)", origin="0px 0px"),
        ],
    )
    expect("ancestor_hit", nested, 115, 70, "hit", "inner")
    expect("ancestor_miss", nested, 120, 60, "miss", None)

    skewed = _box("skew", 0, 0, 20, 20, transform="skewX(45deg)", origin="0px 0px")
    expect("skew_hit", skewed, 10, 10, "hit", "skew")
    expect("skew_miss", skewed, 0, 10, "miss", None)

    captured = _box(
        "root",
        0,
        0,
        100,
        100,
        children=[
            _box(
                "parent",
                0,
                0,
                40,
                40,
                transform="rotate(0deg)",
                origin="0px 0px",
                children=[
                    _box("child", 0, 0, 40, 40, position="absolute", z_index=-1),
                ],
            )
        ],
    )
    released = _box(
        "root",
        0,
        0,
        100,
        100,
        children=[
            _box(
                "parent",
                0,
                0,
                40,
                40,
                transform="none",
                children=[
                    _box("child", 0, 0, 40, 40, position="absolute", z_index=-1),
                ],
            )
        ],
    )
    expect("captured_child", captured, 10, 10, "hit", "child")
    expect("released_parent", released, 10, 10, "hit", "parent")

    collapsed = _box("flat", 0, 0, 20, 20, transform="scale(0)", origin="0px 0px")
    expect("collapsed_center", collapsed, 10, 10, "miss", None)

    expect(
        "bare_angle",
        _box("bad", 0, 0, 20, 20, transform="rotate(90)", origin="0px 0px"),
        0,
        0,
        "invalid",
        None,
    )
    expect(
        "bad_origin",
        _box("bad", 0, 0, 20, 20, transform="rotate(90deg)", origin="left left"),
        0,
        0,
        "invalid",
        None,
    )
    plain = _box("plain", 0, 0, 10, 10)
    expect("plain_corner", plain, 0, 0, "hit", "plain")
    expect("plain_far_corner", plain, 10, 10, "miss", None)
    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
