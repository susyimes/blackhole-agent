"""Map a local point through a CSS 2D transform.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the transform reader still exits 0.
"""

from __future__ import annotations

import json


def _layer(
    x: float,
    y: float,
    width: float,
    height: float,
    transform: str = "none",
    origin: str = "0px 0px",
) -> dict[str, object]:
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "transform": transform,
        "origin": origin,
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_transform import map_transformed_point
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, layers: object, point: dict[str, float]) -> dict[str, object]:
        try:
            result = map_transformed_point(layers, point)
        except Exception as exc:  # noqa: BLE001 - a raised mapping is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"outcome": "error"}
        observed[name] = {
            "outcome": result.get("outcome"),
            "x": result.get("x"),
            "y": result.get("y"),
            "matrix": result.get("matrix"),
            "reason": result.get("reason"),
        }
        return result

    def expect(name: str, result: dict[str, object], **fields: object) -> None:
        ok = True
        for key, value in fields.items():
            ok = ok and result.get(key) == value
        checks.append(ok)

    box = _layer(100, 40, 80, 60)
    expect(
        "translate",
        place("translate", {**box, "transform": "translate(10px, 20px)"}, {"x": 0, "y": 0}),
        outcome="mapped",
        x=110,
        y=60,
    )
    expect(
        "rotate_clockwise",
        place("rotate_clockwise", {**box, "transform": "rotate(90deg)"}, {"x": 10, "y": 0}),
        outcome="mapped",
        x=100,
        y=50,
        matrix=[0, 1, -1, 0, 0, 0],
    )
    expect(
        "origin_center",
        place(
            "origin_center",
            _layer(0, 0, 20, 20, "rotate(90deg)", "50% 50%"),
            {"x": 20, "y": 10},
        ),
        outcome="mapped",
        x=10,
        y=20,
    )
    expect(
        "translate_then_rotate",
        place(
            "translate_then_rotate",
            _layer(0, 0, 20, 20, "translate(30px, 0px) rotate(90deg)"),
            {"x": 0, "y": 0},
        ),
        outcome="mapped",
        x=0,
        y=30,
    )
    expect(
        "rotate_then_translate",
        place(
            "rotate_then_translate",
            _layer(0, 0, 20, 20, "rotate(90deg) translate(30px, 0px)"),
            {"x": 0, "y": 0},
        ),
        outcome="mapped",
        x=30,
        y=0,
    )
    expect(
        "scale_right_center",
        place(
            "scale_right_center",
            _layer(0, 0, 40, 20, "scale(2)", "right center"),
            {"x": 0, "y": 10},
        ),
        outcome="mapped",
        x=-40,
        y=10,
    )
    expect(
        "percentage_translation",
        place(
            "percentage_translation",
            {**box, "transform": "translate(50%, 25%)"},
            {"x": 0, "y": 0},
        ),
        outcome="mapped",
        x=140,
        y=55,
    )
    expect(
        "skew_x",
        place("skew_x", _layer(0, 0, 20, 20, "skewX(45deg)"), {"x": 0, "y": 10}),
        outcome="mapped",
        x=10,
        y=10,
        matrix=[1, 0, 1, 1, 0, 0],
    )
    expect(
        "skew_pair",
        place("skew_pair", _layer(0, 0, 20, 20, "skew(45deg, 45deg)"), {"x": 4, "y": 0}),
        outcome="mapped",
        x=4,
        y=4,
        matrix=[1, 1, 1, 1, 0, 0],
    )
    expect(
        "matrix_rotate",
        place(
            "matrix_rotate",
            _layer(0, 0, 20, 20, "matrix(0, 1, -1, 0, 0, 0)"),
            {"x": 10, "y": 0},
        ),
        outcome="mapped",
        x=0,
        y=10,
    )
    expect(
        "translate_then_scale",
        place(
            "translate_then_scale",
            _layer(0, 0, 20, 20, "translate(10px, 0px) scale(2)"),
            {"x": 0, "y": 0},
        ),
        outcome="mapped",
        x=20,
        y=0,
        matrix=[2, 0, 0, 2, 20, 0],
    )
    expect(
        "scale_then_translate",
        place(
            "scale_then_translate",
            _layer(0, 0, 20, 20, "scale(2) translate(10px, 0px)"),
            {"x": 0, "y": 0},
        ),
        outcome="mapped",
        x=10,
        y=0,
        matrix=[2, 0, 0, 2, 10, 0],
    )
    expect(
        "quarter_turn",
        place("quarter_turn", _layer(0, 0, 20, 20, "rotate(0.25turn)"), {"x": 10, "y": 0}),
        outcome="mapped",
        x=0,
        y=10,
    )
    expect(
        "half_turn_center",
        place(
            "half_turn_center",
            _layer(5, 6, 20, 10, "rotate(180deg)", "center"),
            {"x": 0, "y": 0},
        ),
        outcome="mapped",
        x=25,
        y=16,
    )
    expect(
        "calc_translation",
        place(
            "calc_translation",
            _layer(0, 0, 80, 10, "translate(calc(100% - 20px), 0px)"),
            {"x": 0, "y": 0},
        ),
        outcome="mapped",
        x=60,
        y=0,
    )
    outer = _layer(100, 40, 80, 60, "translate(5px, 0px)")
    inner = _layer(10, 20, 20, 20, "rotate(90deg)")
    expect(
        "outer_layer",
        place("outer_layer", [outer, inner], {"x": 10, "y": 0}),
        outcome="mapped",
        x=115,
        y=70,
        matrix=[0, 1, -1, 0, 0, 0],
    )
    bare = place("bare_angle", _layer(0, 0, 10, 10, "rotate(90)"), {"x": 0, "y": 0})
    checks.append(bare.get("outcome") == "invalid" and bare.get("x") is None)
    three = place("rotate_x", _layer(0, 0, 10, 10, "rotateX(90deg)"), {"x": 0, "y": 0})
    checks.append(three.get("outcome") == "invalid" and three.get("matrix") is None)
    swapped = place(
        "bad_origin",
        _layer(0, 0, 10, 10, "rotate(0)", "left left"),
        {"x": 1, "y": 1},
    )
    checks.append(swapped.get("outcome") == "invalid" and swapped.get("y") is None)

    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
