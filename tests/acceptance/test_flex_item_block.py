"""Lay static blocks inside a nowrap flex row item.

The item is an independent formatting context: a specified width wraps the
child, a child margin stays inside the item, adjoining child margins
collapse, and an automatic flex:none width is the child's max-content.
A column gap places the next item after that used width, and a stretched
sibling takes the grown cross size so the following block starts under the
row. A column, a wrap, inline-flex, and a float stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects flex item content exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_ROW = "#row { display: flex; width: 200px; }\n"
_ONE = (
    '<div id="page"><div id="row"><div id="a"><div id="b">AA BB</div></div>'
    '<div id="side"></div></div><p id="next">Z</p></div>'
)
_PLAIN = '<div id="page"><div id="row"><div id="a"><div id="b">AA</div></div></div><p id="next">Z</p></div>'
_TWO = (
    '<div id="page"><div id="row"><div id="a"><div id="b">AA</div>'
    '<div id="c">BB</div></div></div><p id="next">Z</p></div>'
)
_AUTO = (
    '<div id="page"><div id="row"><div id="a"><div id="b">AA</div></div>'
    '<div id="side"></div></div><p id="next">Z</p></div>'
)


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, _FONT + stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _placed(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    lines = box.get("lines")
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "lines": [line.get("text") for line in lines if isinstance(line, dict)] if isinstance(lines, list) else None,
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "wrap": _lay(
            layout_normal_flow,
            _ONE,
            "#row { display: flex; width: 200px; column-gap: 10px; }\n"
            "#a { flex: none; width: 40px; }\n"
            "#side { flex: none; width: 30px; }\n",
        ),
        "margin": _lay(
            layout_normal_flow,
            _PLAIN,
            _ROW + "#a { flex: none; width: 200px; }\n#b { margin: 10px; }\n",
        ),
        "stack": _lay(layout_normal_flow, _TWO, _ROW + "#a { flex: none; width: 200px; }\n"),
        "collapse": _lay(
            layout_normal_flow,
            _TWO,
            _ROW + "#a { flex: none; width: 200px; }\n#b { margin-bottom: 10px; }\n#c { margin-top: 10px; }\n",
        ),
        "auto": _lay(
            layout_normal_flow,
            _AUTO,
            _ROW + "#a { flex: none; }\n#side { flex: none; width: 30px; align-self: flex-start; }\n",
        ),
        "column": _lay(
            layout_normal_flow,
            _PLAIN,
            "#row { display: flex; flex-direction: column; width: 200px; }\n#a { flex: none; width: 40px; }\n",
        ),
        "wrapped": _lay(
            layout_normal_flow,
            _PLAIN,
            "#row { display: flex; flex-wrap: wrap; width: 200px; }\n#a { flex: none; width: 40px; }\n",
        ),
        "inline": _lay(
            layout_normal_flow,
            _PLAIN,
            "#row { display: inline-flex; width: 200px; }\n#a { flex: none; width: 40px; }\n",
        ),
        "floated": _lay(
            layout_normal_flow,
            _PLAIN,
            _ROW + "#a { flex: none; width: 200px; }\n#b { float: left; }\n",
        ),
    }
    observed: dict[str, object] = {
        name: {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "a": _placed(result, "a"),
            "b": _placed(result, "b"),
            "c": _placed(result, "c"),
            "side": _placed(result, "side"),
            "next": _placed(result, "next"),
        }
        for name, result in cases.items()
    }
    wrap_lines = (observed["wrap"]["b"] or {}).get("lines") if isinstance(observed["wrap"]["b"], dict) else None
    checks = {
        "narrow_item_wraps_and_the_gap_places_the_sibling": (
            cases["wrap"].get("outcome") == "placed"
            and _near(_box(cases["wrap"].get("boxes"), "b"), x=0, y=0, content_width=40, content_height=20)
            and wrap_lines == ["AA", "BB"]
            and _near(_box(cases["wrap"].get("boxes"), "a"), x=0, content_width=40, content_height=20)
            and _near(_box(cases["wrap"].get("boxes"), "side"), x=50, content_width=30, content_height=20)
            and _near(_box(cases["wrap"].get("boxes"), "next"), y=20)
        ),
        "child_margin_stays_inside_the_item": (
            cases["margin"].get("outcome") == "placed"
            and _near(_box(cases["margin"].get("boxes"), "b"), x=10, y=10, content_width=180, content_height=10)
            and _near(_box(cases["margin"].get("boxes"), "a"), content_height=30)
            and _near(_box(cases["margin"].get("boxes"), "next"), y=30)
        ),
        "stacked_children_grow_the_row": (
            cases["stack"].get("outcome") == "placed"
            and _near(_box(cases["stack"].get("boxes"), "c"), x=0, y=10, content_height=10)
            and _near(_box(cases["stack"].get("boxes"), "a"), content_height=20)
            and _near(_box(cases["stack"].get("boxes"), "next"), y=20)
        ),
        "adjoining_child_margins_collapse": (
            cases["collapse"].get("outcome") == "placed"
            and _near(_box(cases["collapse"].get("boxes"), "b"), y=0, content_height=10)
            and _near(_box(cases["collapse"].get("boxes"), "c"), y=20, content_height=10)
            and _near(_box(cases["collapse"].get("boxes"), "a"), content_height=30)
            and _near(_box(cases["collapse"].get("boxes"), "next"), y=30)
        ),
        "automatic_width_is_the_child_max_content": (
            cases["auto"].get("outcome") == "placed"
            and _near(_box(cases["auto"].get("boxes"), "b"), x=0, y=0, content_width=20, content_height=10)
            and _near(_box(cases["auto"].get("boxes"), "a"), content_width=20, content_height=10)
            and _near(
                _box(cases["auto"].get("boxes"), "side"), x=20, y=0, content_width=30, content_height=0
            )
            and _near(_box(cases["auto"].get("boxes"), "next"), y=10)
        ),
        "column_wrap_inline_flex_and_float_are_rejected": all(
            cases[name].get("outcome") == "invalid" for name in ("column", "wrapped", "inline", "floated")
        ),
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
