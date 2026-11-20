"""Wrap inline atoms around a CSS shape-outside instead of the margin box.

A 100px left float whose circle is centered in the margin box leaves the top
corner open, so a 105px atom sits on the first 20px line. The same atom drops
below a rectangular float. An inset that ends at 40px releases the next line
there. A triangular hypotenuse admits an 80px atom at y 30. shape-margin
expands a smaller circle before clipping, and the lower shoulder of the
50px circle admits a 120px atom at y 90.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A packer that rejects the shape still exits 0.
"""

from __future__ import annotations

import json


def _float(side: str, x: int, y: int, width: int, height: int, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {"side": side, "x": x, "y": y, "width": width, "height": height}
    row.update(extra)
    return row


def _left(width: int, height: int, **extra: object) -> dict[str, object]:
    return _float("left", 0, 0, width, height, **extra)


def _atom(name: str, width: int) -> dict[str, object]:
    return {"id": name, "width": width}


def _line(x: int, y: int, width: int, atoms: list[str], height: int) -> dict[str, object]:
    return {"x": x, "y": y, "width": width, "height": height, "atoms": atoms}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_float_lines import pack_line_boxes
    except Exception as exc:  # noqa: BLE001 - baseline without the packer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = pack_line_boxes(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised pack is an unmet outcome
            result = {"outcome": "error", "lines": None, "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error", "lines": None}
        observed[name] = {
            "outcome": packed.get("outcome"),
            "lines": packed.get("lines"),
            "reason": packed.get("reason"),
        }
        return observed[name]

    def expect(name: str, lines: list[dict[str, object]], **kwargs: object) -> None:
        got = take(name, **kwargs)
        checks.append(got.get("outcome") == "placed" and got.get("lines") == lines)

    def invalid(name: str, **kwargs: object) -> None:
        got = take(name, **kwargs)
        checks.append(got.get("outcome") == "invalid" and got.get("lines") is None and bool(got.get("reason")))

    circle = _left(100, 100, shape="circle(50px at 50px 50px)")
    expect(
        "circle_corner",
        [_line(90, 0, 110, ["wide"], 20)],
        containing_width=200,
        atoms=[_atom("wide", 105)],
        floats=[circle],
        line_height=20,
    )
    expect(
        "rectangle",
        [_line(0, 100, 200, ["wide"], 20)],
        containing_width=200,
        atoms=[_atom("wide", 105)],
        floats=[_left(100, 100)],
        line_height=20,
    )
    expect(
        "inset_release",
        [_line(0, 40, 100, ["a"], 10)],
        containing_width=100,
        atoms=[_atom("a", 50)],
        floats=[_left(100, 100, shape="inset(0px 0px 60px 0px)")],
        line_height=10,
    )
    expect(
        "polygon_pass",
        [_line(70, 30, 80, ["a"], 10)],
        containing_width=150,
        atoms=[_atom("a", 80)],
        floats=[_left(100, 100, shape="polygon(0px 0px, 100px 0px, 0px 100px)")],
        line_height=10,
    )
    expect(
        "margin_tight",
        [_line(80, 0, 120, ["a"], 100)],
        containing_width=200,
        atoms=[_atom("a", 90)],
        floats=[_left(100, 100, shape="circle(30px at 50px 50px)", shape_margin=0)],
        line_height=100,
    )
    expect(
        "margin_wide",
        [_line(100, 0, 100, ["a"], 100)],
        containing_width=200,
        atoms=[_atom("a", 90)],
        floats=[_left(100, 100, shape="circle(30px at 50px 50px)", shape_margin=20)],
        line_height=100,
    )
    expect(
        "shoulder",
        [_line(80, 90, 120, ["a"], 20)],
        containing_width=200,
        atoms=[_atom("a", 120)],
        floats=[circle],
        line_height=20,
    )
    expect(
        "ellipse_top",
        [_line(0, 0, 200, ["a"], 20)],
        containing_width=200,
        atoms=[_atom("a", 150)],
        floats=[_left(100, 100, shape="ellipse(40px 20px at 50px 50px)")],
        line_height=20,
    )
    expect(
        "vertical_line",
        [_line(50, 0, 150, ["a"], 20)],
        containing_width=200,
        atoms=[_atom("a", 40)],
        floats=[_left(100, 100, shape="inset(0px 50px 0px 50px)")],
        line_height=20,
    )
    expect(
        "horizontal_line",
        [_line(0, 0, 200, ["a"], 100)],
        containing_width=200,
        atoms=[_atom("a", 150)],
        floats=[_left(100, 100, shape="inset(50px 0px 50px 0px)")],
        line_height=100,
    )
    expect(
        "clipped_circle",
        [_line(100, 0, 100, ["a"], 100)],
        containing_width=200,
        atoms=[_atom("a", 50)],
        floats=[_left(100, 100, shape="circle(80px at 50px 50px)")],
        line_height=100,
    )
    expect(
        "right_corner",
        [_line(0, 0, 110, ["a"], 20)],
        containing_width=200,
        atoms=[_atom("a", 105)],
        floats=[_float("right", 100, 0, 100, 100, shape="circle(50px at 50px 50px)")],
        line_height=20,
    )
    expect(
        "polygon_margin",
        [_line(70, 0, 130, ["a"], 20)],
        containing_width=200,
        atoms=[_atom("a", 50)],
        floats=[
            _left(
                100,
                100,
                shape="polygon(0px 20px, 60px 20px, 60px 80px, 0px 80px)",
                shape_margin=10,
            )
        ],
        line_height=20,
    )
    expect(
        "polygon_plain",
        [_line(0, 0, 200, ["a"], 20)],
        containing_width=200,
        atoms=[_atom("a", 50)],
        floats=[_left(100, 100, shape="polygon(0px 20px, 60px 20px, 60px 80px, 0px 80px)")],
        line_height=20,
    )
    expect(
        "percent_circle",
        [_line(90, 0, 110, ["wide"], 20)],
        containing_width=200,
        atoms=[_atom("wide", 105)],
        floats=[_left(100, 100, shape="circle(50% at 50% 50%)")],
        line_height=20,
    )
    expect(
        "default_circle",
        [_line(90, 0, 110, ["wide"], 20)],
        containing_width=200,
        atoms=[_atom("wide", 105)],
        floats=[_left(100, 100, shape="circle()")],
        line_height=20,
    )
    expect(
        "margin_box",
        [_line(0, 100, 200, ["wide"], 20)],
        containing_width=200,
        atoms=[_atom("wide", 105)],
        floats=[_left(100, 100, shape="margin-box")],
        line_height=20,
    )
    invalid(
        "bad_shape",
        containing_width=100,
        atoms=[_atom("a", 10)],
        floats=[_left(40, 40, shape="circle(")],
        line_height=10,
    )
    invalid(
        "bad_margin",
        containing_width=100,
        atoms=[_atom("a", 10)],
        floats=[_left(40, 40, shape="circle(10px)", shape_margin=-1)],
        line_height=10,
    )
    invalid(
        "ellipse_margin",
        containing_width=100,
        atoms=[_atom("a", 10)],
        floats=[_left(40, 40, shape="ellipse(10px 10px)", shape_margin=5)],
        line_height=10,
    )
    invalid(
        "rounded_inset",
        containing_width=100,
        atoms=[_atom("a", 10)],
        floats=[_left(40, 40, shape="inset(4px round 4px)")],
        line_height=10,
    )
    invalid(
        "unknown_field",
        containing_width=100,
        atoms=[_atom("a", 10)],
        floats=[{"side": "left", "x": 0, "y": 0, "width": 10, "height": 10, "color": "red"}],
        line_height=10,
    )
    return all(checks), observed


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    _emit({"passed": bool(passed), "observed": observed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
