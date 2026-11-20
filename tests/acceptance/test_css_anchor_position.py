"""Place an absolutely positioned box on a CSS anchor-position grid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the anchor reader still exits 0.
"""

from __future__ import annotations

import json


def _port(**overrides: object) -> dict[str, object]:
    containing: dict[str, object] = {
        "x": 0,
        "y": 0,
        "width": 400,
        "height": 300,
        "writing_mode": "horizontal-tb",
        "direction": "ltr",
    }
    containing.update(overrides)
    return containing


def _anchor(x: float, y: float, width: float, height: float) -> dict[str, object]:
    return {"x": x, "y": y, "width": width, "height": height}


def _box(width: float, height: float, **overrides: object) -> dict[str, object]:
    box: dict[str, object] = {"width": width, "height": height}
    box.update(overrides)
    return box


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_anchor_position import place_anchored
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, containing: dict[str, object], anchor: object, box: dict[str, object], **kwargs: object) -> dict[str, object]:
        try:
            result = place_anchored(containing, anchor, box, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised placement is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"outcome": "error"}
        observed[name] = {
            "outcome": result.get("outcome"),
            "x": result.get("x"),
            "y": result.get("y"),
            "option": result.get("option"),
            "fits": result.get("fits"),
            "reason": result.get("reason"),
            "top": result.get("top"),
            "bottom": result.get("bottom"),
            "left": result.get("left"),
        }
        return result

    def expect(name: str, result: dict[str, object], **fields: object) -> None:
        ok = True
        for key, value in fields.items():
            ok = ok and result.get(key) == value
        checks.append(ok)

    anchor = _anchor(180, 140, 40, 20)
    expect(
        "block_start",
        place("block_start", _port(), anchor, _box(50, 30, position_area="block-start")),
        outcome="placed",
        x=175,
        y=110,
        option="base",
        fits=True,
    )
    expect(
        "flip_block",
        place(
            "flip_block",
            _port(),
            _anchor(180, 10, 40, 20),
            _box(50, 30, position_area="block-start"),
            fallbacks=("flip-block",),
        ),
        outcome="placed",
        x=175,
        y=30,
        option="flip-block",
        fits=True,
    )
    chart = _anchor(100, 80, 40, 20)
    expect(
        "anchor_bottom",
        place(
            "anchor_bottom",
            _port(),
            chart,
            _box(30, 16, insets={"top": {"side": "bottom"}, "left": 0}),
        ),
        outcome="placed",
        y=100,
        top=100,
        fits=True,
    )
    expect(
        "anchor_top_from_bottom",
        place(
            "anchor_top_from_bottom",
            _port(),
            chart,
            _box(30, 16, insets={"bottom": {"side": "top"}, "left": 0}),
        ),
        outcome="placed",
        y=64,
        bottom=220,
        fits=True,
    )
    expect(
        "fallback_length",
        place(
            "fallback_length",
            _port(),
            None,
            _box(30, 16, insets={"top": {"side": "bottom", "fallback": 12}, "left": 0}),
        ),
        outcome="placed",
        y=12,
        top=12,
        fits=True,
    )
    expect(
        "most_height",
        place(
            "most_height",
            _port(),
            _anchor(100, 250, 20, 20),
            _box(10, 20, position_area="block-end"),
            fallbacks=("flip-block",),
            order="most-height",
        ),
        outcome="placed",
        x=105,
        y=230,
        option="flip-block",
        fits=True,
    )
    expect(
        "normal_keeps_base",
        place(
            "normal_keeps_base",
            _port(),
            _anchor(100, 250, 20, 20),
            _box(10, 20, position_area="block-end"),
            fallbacks=("flip-block",),
        ),
        outcome="placed",
        y=270,
        option="base",
        fits=True,
    )
    expect(
        "vertical_rl",
        place(
            "vertical_rl",
            _port(width=300, height=400, writing_mode="vertical-rl"),
            _anchor(200, 100, 40, 30),
            _box(20, 40, position_area="block-start"),
        ),
        outcome="placed",
        x=240,
        y=95,
        option="base",
        fits=True,
    )
    expect(
        "rtl_inline_start",
        place(
            "rtl_inline_start",
            _port(width=200, height=200, direction="rtl"),
            _anchor(80, 40, 40, 20),
            _box(30, 16, position_area="inline-start"),
        ),
        outcome="placed",
        x=120,
        y=42,
        option="base",
        fits=True,
    )
    expect(
        "anchor_center",
        place(
            "anchor_center",
            _port(),
            chart,
            _box(10, 10, insets={"top": {"side": "center"}, "left": 0}),
        ),
        outcome="placed",
        y=90,
        top=90,
    )
    expect(
        "inside_outside",
        place(
            "inside_outside",
            _port(),
            chart,
            _box(10, 10, insets={"top": {"side": "inside"}, "left": {"side": "outside"}}),
        ),
        outcome="placed",
        x=140,
        y=80,
    )
    expect(
        "wrong_axis_fallback",
        place(
            "wrong_axis_fallback",
            _port(),
            chart,
            _box(10, 10, insets={"left": {"side": "top", "fallback": 15}, "top": 0}),
        ),
        outcome="placed",
        x=15,
        left=15,
    )
    invalid = place(
        "wrong_axis",
        _port(),
        chart,
        _box(10, 10, insets={"left": {"side": "top"}, "top": 0}),
    )
    checks.append(invalid.get("outcome") == "invalid" and invalid.get("x") is None)
    expect(
        "percentage",
        place(
            "percentage",
            _port(),
            chart,
            _box(10, 10, insets={"top": {"side": "25%"}, "left": 0}),
        ),
        outcome="placed",
        y=85,
    )
    expect(
        "flip_x",
        place(
            "flip_x",
            _port(width=100, height=200),
            _anchor(5, 40, 10, 20),
            _box(30, 16, position_area="left"),
            fallbacks=("flip-x",),
        ),
        outcome="placed",
        x=15,
        y=42,
        option="flip-x",
        fits=True,
    )
    expect(
        "center_center",
        place("center_center", _port(), anchor, _box(50, 30, position_area="center")),
        outcome="placed",
        x=175,
        y=135,
        fits=False,
    )
    overflow = place(
        "overflow_keeps_base",
        _port(width=50, height=50),
        _anchor(20, 20, 10, 10),
        _box(80, 80, position_area="block-start"),
        fallbacks=("flip-block", "flip-inline"),
    )
    checks.append(overflow.get("outcome") == "placed" and overflow.get("fits") is False and overflow.get("option") == "base")
    negative = place("negative", _port(), anchor, _box(-1, 10, position_area="top"))
    checks.append(negative.get("outcome") == "invalid" and negative.get("x") is None)

    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
