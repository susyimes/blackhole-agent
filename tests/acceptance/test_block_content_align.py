"""Pack a block container's in-flow content as one unit.

``align-content: end`` puts two marginless 10px children at the end of a
100px content box, ``center`` splits the free space, and ``normal`` leaves
them at the start. Safe centering keeps a 140px child at the start;
``unsafe center`` shifts it by half the overflow. ``start`` holds a 20px
child margin inside the box. The following sibling stays on the container's
border edge. A line box moves with the same end edge, and ``baseline`` is
rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_BLOCKS = (
    '<div id="page"><div id="box"><div id="a"></div><div id="b"></div></div>'
    '<div id="next"></div></div>'
)
_ONE = '<div id="page"><div id="box"><div id="a"></div></div><div id="next"></div></div>'
_TEXT = '<div id="page"><div id="box">Hello</div><div id="next"></div></div>'
_RESET = "#page, #box, #a, #b, #next { margin: 0px; }"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    lines = box.get("lines")
    first = lines[0] if isinstance(lines, list) and lines and isinstance(lines[0], dict) else None
    return {
        "y": box.get("y"),
        "border_height": box.get("border_height"),
        "content_height": box.get("content_height"),
        "line_y": None if first is None else first.get("y"),
        "line_height": None if first is None else first.get("height"),
    }


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, stylesheet: str, *, markup: str = _BLOCKS) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _pair(align: str) -> str:
    return (
        _RESET
        + f"#box {{ width: 100px; height: 100px; align-content: {align}; }}"
        + " #a, #b { height: 10px; } #next { height: 10px; }"
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "end": _lay(layout_normal_flow, _pair("end")),
        "center": _lay(layout_normal_flow, _pair("center")),
        "normal": _lay(layout_normal_flow, _pair("normal")),
        "safe": _lay(
            layout_normal_flow,
            _RESET
            + "#box { width: 100px; height: 100px; align-content: center; }"
            + " #a { height: 140px; } #next { height: 10px; }",
            markup=_ONE,
        ),
        "unsafe": _lay(
            layout_normal_flow,
            _RESET
            + "#box { width: 100px; height: 100px; align-content: unsafe center; }"
            + " #a { height: 140px; } #next { height: 10px; }",
            markup=_ONE,
        ),
        "around": _lay(layout_normal_flow, _pair("space-around")),
        "between": _lay(layout_normal_flow, _pair("space-between")),
        "flex_end": _lay(layout_normal_flow, _pair("flex-end")),
        "held": _lay(
            layout_normal_flow,
            "#page, #next { margin: 0px; } #box { width: 100px; align-content: start; }"
            " #a { height: 10px; margin-top: 20px; margin-bottom: 0px; } #next { height: 10px; margin: 0px; }",
            markup=_ONE,
        ),
        "escaped": _lay(
            layout_normal_flow,
            "#page, #next { margin: 0px; } #box { width: 100px; }"
            " #a { height: 10px; margin-top: 20px; margin-bottom: 0px; } #next { height: 10px; margin: 0px; }",
            markup=_ONE,
        ),
        "padded": _lay(
            layout_normal_flow,
            _RESET + "#box { width: 100px; height: 100px; padding-top: 10px; align-content: end; }"
            " #a { height: 10px; } #next { height: 10px; }",
            markup=_ONE,
        ),
        "line": _lay(
            layout_normal_flow,
            _RESET
            + "#box { width: 80px; height: 100px; font-size: 10px; line-height: 10px; align-content: end; }"
            " #next { height: 10px; }",
            markup=_TEXT,
        ),
        "baseline": _lay(layout_normal_flow, _pair("baseline")),
    }
    found = {name: _edge(_box(case.get("boxes"), "box")) for name, case in cases.items()}
    kids = {
        name: (
            _edge(_box(case.get("boxes"), "a")),
            _edge(_box(case.get("boxes"), "b")),
            _edge(_box(case.get("boxes"), "next")),
            _edge(_box(case.get("boxes"), "page")),
        )
        for name, case in cases.items()
    }
    observed: dict[str, object] = {
        "boxes": {name: found[name] for name in ("end", "center", "normal", "safe", "unsafe", "padded", "line")},
        "children": {
            name: {"a": kids[name][0], "b": kids[name][1], "next": kids[name][2], "page": kids[name][3]}
            for name in ("end", "held", "escaped", "safe", "unsafe")
        },
    }

    def placed(name: str) -> bool:
        return cases[name].get("outcome") == "placed"

    checks = {
        "end_packs_the_unit_against_the_block_end": placed("end")
        and _near(kids["end"][0], y=80, border_height=10)
        and _near(kids["end"][1], y=90, border_height=10)
        and _near(kids["end"][2], y=100, border_height=10)
        and _near(found["end"], y=0, content_height=100, border_height=100),
        "center_splits_the_free_space": placed("center")
        and _near(kids["center"][0], y=40)
        and _near(kids["center"][1], y=50)
        and _near(kids["center"][2], y=100),
        "normal_keeps_the_unit_at_the_start": placed("normal")
        and _near(kids["normal"][0], y=0)
        and _near(kids["normal"][1], y=10)
        and _near(kids["normal"][2], y=100),
        "safe_center_keeps_overflow_at_the_start": placed("safe")
        and _near(kids["safe"][0], y=0, border_height=140)
        and _near(kids["safe"][2], y=100)
        and _near(found["safe"], content_height=100),
        "unsafe_center_honors_the_negative_shift": placed("unsafe")
        and _near(kids["unsafe"][0], y=-20, border_height=140)
        and _near(kids["unsafe"][2], y=100),
        "space_around_uses_the_center_fallback": placed("around") and _near(kids["around"][0], y=40),
        "space_between_uses_the_start_fallback": placed("between")
        and _near(kids["between"][0], y=0)
        and _near(kids["between"][1], y=10),
        "flex_end_matches_end": placed("flex_end") and _near(kids["flex_end"][0], y=80),
        "start_keeps_the_child_margin_inside": placed("held")
        and _near(kids["held"][3], y=0)
        and _near(found["held"], y=0, border_height=30, content_height=30)
        and _near(kids["held"][0], y=20, border_height=10)
        and _near(kids["held"][2], y=30),
        "normal_still_lets_that_margin_escape": placed("escaped")
        and _near(kids["escaped"][3], y=20)
        and _near(found["escaped"], y=20, border_height=10)
        and _near(kids["escaped"][0], y=20)
        and _near(kids["escaped"][2], y=30),
        "end_aligns_inside_the_content_box": placed("padded")
        and _near(kids["padded"][0], y=100, border_height=10)
        and _near(found["padded"], border_height=110, content_height=100)
        and _near(kids["padded"][2], y=110),
        "a_line_box_moves_with_the_unit": placed("line")
        and _near(found["line"], y=0, content_height=100, line_y=90, line_height=10)
        and _near(kids["line"][2], y=100),
        "baseline_is_rejected": cases["baseline"].get("outcome") == "invalid"
        and cases["baseline"].get("reason") == "align-content baseline is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 even when it fails
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    payload = {"passed": bool(passed), "observed": observed if observed else {"error": "empty"}}
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    except (UnicodeEncodeError, TypeError) as exc:
        encoded = json.dumps(
            {"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}},
            separators=(",", ":"),
        ).encode("ascii")
    sys.stdout.buffer.write(encoded + b"\n")


if __name__ == "__main__":
    main()
