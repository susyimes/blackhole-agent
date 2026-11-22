"""Replace display:contents with the element's children.

A contents element generates no box. Its block child's percentage uses the
parent, and the contents width, padding, border, and margin do not move
that child or the following block. Nested contents unwraps the same way.
An inline font-size on the contents element still sizes its text on the
parent line. A flex or grid parent promotes the children to items. An
absolute contents element leaves its child in flow. Inline text around a
contents wrapper still splits into anonymous blocks.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_BLOCK = (
    '<div id="page"><div id="wrap"><div id="child"></div></div>'
    '<div id="next"></div></div>'
)
_BLOCK_CSS = """
#page, #child, #next { margin: 0px; }
#wrap {
  display: contents;
  width: 40px;
  padding: 20px;
  border-width: 10px;
  border-style: solid;
  margin: 30px;
}
#child { width: 50%; height: 20px; }
#next { height: 10px; }
"""

_NESTED = (
    '<div id="page"><div id="outer"><div id="inner"><div id="child"></div></div></div>'
    '<div id="next"></div></div>'
)
_NESTED_CSS = """
#page, #child, #next { margin: 0px; }
#outer { display: contents; width: 15px; padding: 8px; margin: 12px; }
#inner { display: contents; width: 25px; padding: 6px; }
#child { width: 50%; height: 18px; }
#next { height: 4px; }
"""

_INLINE = '<p id="copy">Hi <b id="big">BIG</b> end</p>'
_INLINE_CSS = """
#copy { font-size: 10px; line-height: 20px; margin: 0px; }
#big {
  display: contents;
  font-size: 20px;
  line-height: 40px;
  padding: 30px;
  width: 5px;
  border-width: 4px;
  border-style: solid;
}
"""

_FLEX = (
    '<div id="fit"><div id="wrap"><span id="word">BB</span></div>'
    '<span id="rest"></span></div>'
)
_FLEX_CSS = """
#fit { display: flex; font-size: 10px; line-height: 10px; }
#wrap { display: contents; width: 4px; padding: 25px; border-width: 6px; border-style: solid; }
#word { flex: none; }
#rest { flex: 1; }
"""

_GRID = (
    '<div id="page"><div id="grid"><div id="wrap"><div id="cell">AA</div></div></div>'
    '<p id="next">Z</p></div>'
)
_GRID_CSS = """
#page { font-size: 10px; line-height: 10px; }
#grid { display: grid; width: 200px; grid-template-columns: 40px; }
#wrap { display: contents; width: 9px; padding: 12px; border-width: 3px; border-style: solid; }
"""

_ABS = (
    '<div id="page"><div id="wrap"><div id="child"></div></div>'
    '<div id="next"></div></div>'
)
_ABS_CSS = """
#page, #child, #next { margin: 0px; }
#wrap { display: contents; position: absolute; top: 30px; left: 12px; width: 40px; }
#child { width: 50%; height: 15px; }
#next { height: 5px; }
"""

_SPLIT = '<div id="page">AA<div id="wrap"><div id="child"></div></div>BB</div>'
_SPLIT_CSS = """
#page { font-size: 10px; line-height: 10px; margin: 0px; }
#wrap { display: contents; width: 30px; padding: 10px; }
#child { height: 14px; margin: 0px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    return line if isinstance(line, dict) else None


def _text_line(boxes: object, text: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict) or not isinstance(item.get("lines"), list):
            continue
        for line in item["lines"]:
            if isinstance(line, dict) and line.get("text") == text:
                return line
    return None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_height": box.get("border_height"),
    }


def _lay(layout, markup: str, stylesheet: str, width: int = 200) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    block = _lay(layout_normal_flow, _BLOCK, _BLOCK_CSS)
    nested = _lay(layout_normal_flow, _NESTED, _NESTED_CSS)
    inline = _lay(layout_normal_flow, _INLINE, _INLINE_CSS)
    flexed = _lay(layout_normal_flow, _FLEX, _FLEX_CSS, 100)
    grid = _lay(layout_normal_flow, _GRID, _GRID_CSS, 240)
    absolute = _lay(layout_normal_flow, _ABS, _ABS_CSS)
    split = _lay(layout_normal_flow, _SPLIT, _SPLIT_CSS)
    block_boxes = block.get("boxes")
    nested_boxes = nested.get("boxes")
    inline_boxes = inline.get("boxes")
    flex_boxes = flexed.get("boxes")
    grid_boxes = grid.get("boxes")
    abs_boxes = absolute.get("boxes")
    split_boxes = split.get("boxes")
    child = _box(block_boxes, "child")
    nxt = _box(block_boxes, "next")
    page = _box(block_boxes, "page")
    nested_child = _box(nested_boxes, "child")
    nested_next = _box(nested_boxes, "next")
    copy = _box(inline_boxes, "copy")
    word = _box(flex_boxes, "word")
    rest = _box(flex_boxes, "rest")
    fit = _box(flex_boxes, "fit")
    cell = _box(grid_boxes, "cell")
    grid_next = _box(grid_boxes, "next")
    abs_child = _box(abs_boxes, "child")
    abs_next = _box(abs_boxes, "next")
    split_child = _box(split_boxes, "child")
    copy_line = _line(copy)
    observed: dict[str, object] = {
        "block_outcome": block.get("outcome"),
        "block_reason": block.get("reason"),
        "page": _edge(page),
        "child": _edge(child),
        "next": _edge(nxt),
        "wrap_present": _box(block_boxes, "wrap") is not None,
        "nested_outcome": nested.get("outcome"),
        "nested_reason": nested.get("reason"),
        "nested_child": _edge(nested_child),
        "nested_next": _edge(nested_next),
        "outer_present": _box(nested_boxes, "outer") is not None,
        "inner_present": _box(nested_boxes, "inner") is not None,
        "inline_outcome": inline.get("outcome"),
        "inline_reason": inline.get("reason"),
        "copy": _edge(copy),
        "copy_line": copy_line,
        "big_present": _box(inline_boxes, "big") is not None,
        "flex_outcome": flexed.get("outcome"),
        "flex_reason": flexed.get("reason"),
        "fit": _edge(fit),
        "word": _edge(word),
        "rest": _edge(rest),
        "flex_wrap_present": _box(flex_boxes, "wrap") is not None,
        "grid_outcome": grid.get("outcome"),
        "grid_reason": grid.get("reason"),
        "cell": _edge(cell),
        "grid_next": _edge(grid_next),
        "grid_wrap_present": _box(grid_boxes, "wrap") is not None,
        "absolute_outcome": absolute.get("outcome"),
        "absolute_reason": absolute.get("reason"),
        "absolute_child": _edge(abs_child),
        "absolute_next": _edge(abs_next),
        "absolute_wrap_present": _box(abs_boxes, "wrap") is not None,
        "split_outcome": split.get("outcome"),
        "split_reason": split.get("reason"),
        "split_child": _edge(split_child),
        "split_aa": _text_line(split_boxes, "AA"),
        "split_bb": _text_line(split_boxes, "BB"),
        "split_wrap_present": _box(split_boxes, "wrap") is not None,
    }
    checks = {
        "block_child_uses_the_parent": (
            block.get("outcome") == "placed"
            and _box(block_boxes, "wrap") is None
            and _near(page, content_width=200)
            and _near(child, x=0, y=0, content_width=100, content_height=20, border_height=20)
            and _near(nxt, x=0, y=20, content_height=10, border_height=10)
        ),
        "nested_contents_unwraps": (
            nested.get("outcome") == "placed"
            and _box(nested_boxes, "outer") is None
            and _box(nested_boxes, "inner") is None
            and _near(nested_child, x=0, y=0, content_width=100, content_height=18)
            and _near(nested_next, y=18, content_height=4)
        ),
        "inline_font_stays_on_the_parent_line": (
            inline.get("outcome") == "placed"
            and _box(inline_boxes, "big") is None
            and _near(copy, content_height=40)
            and _near(
                copy_line,
                text="Hi BIG end",
                x=0,
                y=0,
                height=40,
                content_width=130,
                runs=[
                    {"text": "Hi ", "x": 0, "font_size": 10, "width": 30},
                    {"text": "BIG", "x": 30, "font_size": 20, "width": 60},
                    {"text": " end", "x": 90, "font_size": 10, "width": 40},
                ],
            )
        ),
        "flex_child_becomes_the_item": (
            flexed.get("outcome") == "placed"
            and _box(flex_boxes, "wrap") is None
            and _near(fit, content_width=100, content_height=10, border_height=10)
            and _near(word, x=0, y=0, content_width=20, content_height=10)
            and _near(rest, x=20, y=0, content_width=80, content_height=10)
        ),
        "grid_child_becomes_the_item": (
            grid.get("outcome") == "placed"
            and _box(grid_boxes, "wrap") is None
            and _near(cell, x=0, y=0, content_width=40, content_height=10)
            and _near(grid_next, y=10)
        ),
        "absolute_contents_stays_in_flow": (
            absolute.get("outcome") == "placed"
            and _box(abs_boxes, "wrap") is None
            and _near(abs_child, x=0, y=0, content_width=100, content_height=15)
            and _near(abs_next, x=0, y=15, content_height=5)
        ),
        "contents_between_text_splits_anonymous_blocks": (
            split.get("outcome") == "placed"
            and _box(split_boxes, "wrap") is None
            and _near(_text_line(split_boxes, "AA"), text="AA", x=0, y=0, height=10, content_width=20)
            and _near(split_child, x=0, y=10, content_width=200, content_height=14)
            and _near(_text_line(split_boxes, "BB"), text="BB", x=0, y=24, height=10, content_width=20)
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
