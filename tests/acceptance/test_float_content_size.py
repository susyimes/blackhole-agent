"""Size a float from its own text and shorten lines only beside that margin box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still refuses float text exits 0 with passed false.
"""

from __future__ import annotations

import json

_NESTED = '<p id="copy"><i id="pin">Hello</i>Hello world this wraps</p>'
_NESTED_CSS = """
#pin { float: left; font-size: 10px; line-height: 20px; }
#copy { font-size: 10px; line-height: 20px; }
"""

_WRAPPED = '<div id="page"><i id="pin">Hi Yo</i><p id="copy">Hello world this wraps</p></div>'
_WRAPPED_CSS = """
#pin { float: left; width: 30px; font-size: 10px; line-height: 20px; }
#copy { font-size: 10px; line-height: 20px; }
"""

_TALL = '<div id="page"><i id="pin">Hello</i><p id="copy">Hello world this wraps</p></div>'
_TALL_CSS = """
#pin { float: left; width: 50px; height: 40px; font-size: 10px; line-height: 20px; }
#copy { font-size: 10px; line-height: 20px; }
"""

_SHRINK = '<div id="page"><i id="pin">Hello world</i><p id="copy">Next</p></div>'
_SHRINK_CSS = """
#pin { float: left; font-size: 10px; line-height: 20px; }
#copy { font-size: 10px; line-height: 20px; }
"""

_EMPTY = '<div id="page"><i id="pin"></i><p id="copy">Next</p></div>'
_EMPTY_CSS = """
#pin { float: left; font-size: 10px; line-height: 20px; }
#copy { font-size: 10px; line-height: 20px; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None, index: int) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list):
        return None
    lines = box["lines"]
    if index >= len(lines) or not isinstance(lines[index], dict):
        return None
    return lines[index]


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str, width: int) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=width)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    nested = _lay(layout_normal_flow, _NESTED, _NESTED_CSS, 200)
    wrapped = _lay(layout_normal_flow, _WRAPPED, _WRAPPED_CSS, 200)
    tall = _lay(layout_normal_flow, _TALL, _TALL_CSS, 200)
    shrink = _lay(layout_normal_flow, _SHRINK, _SHRINK_CSS, 80)
    empty = _lay(layout_normal_flow, _EMPTY, _EMPTY_CSS, 200)
    try:
        child = layout_normal_flow(
            '<div id="page"><i id="pin"><b></b></i><p id="copy">Hi</p></div>',
            "#pin { float: left; } #copy { font-size: 10px; }",
            viewport_width=200,
        )
    except Exception as exc:  # noqa: BLE001 - a raised rejection is an unmet outcome
        child = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}

    nested_boxes = nested.get("boxes")
    wrapped_boxes = wrapped.get("boxes")
    tall_boxes = tall.get("boxes")
    shrink_boxes = shrink.get("boxes")
    empty_boxes = empty.get("boxes")
    nested_pin = _box(nested_boxes, "pin")
    nested_copy = _box(nested_boxes, "copy")
    wrapped_pin = _box(wrapped_boxes, "pin")
    wrapped_copy = _box(wrapped_boxes, "copy")
    tall_pin = _box(tall_boxes, "pin")
    tall_copy = _box(tall_boxes, "copy")
    shrink_pin = _box(shrink_boxes, "pin")
    shrink_copy = _box(shrink_boxes, "copy")
    empty_pin = _box(empty_boxes, "pin")
    empty_copy = _box(empty_boxes, "copy")
    observed: dict[str, object] = {
        "nested_pin": nested_pin,
        "nested_copy": nested_copy,
        "wrapped_pin": wrapped_pin,
        "wrapped_copy": wrapped_copy,
        "tall_pin": tall_pin,
        "tall_copy": tall_copy,
        "shrink_pin": shrink_pin,
        "shrink_copy": shrink_copy,
        "empty_pin": empty_pin,
        "empty_copy": empty_copy,
        "child_reason": child.get("reason") if isinstance(child, dict) else None,
    }
    checks = {
        "nested_pin": _near(nested_pin, x=0, y=0, content_width=50, content_height=20),
        "nested_word": _near(_line(nested_pin, 0), text="Hello", x=0, y=0, height=20, content_width=50),
        "nested_first": _near(_line(nested_copy, 0), text="Hello world", x=50, y=0, height=20, content_width=110),
        "nested_second": _near(_line(nested_copy, 1), text="this wraps", x=0, y=20, height=20, content_width=100),
        "wrapped_pin": _near(wrapped_pin, x=0, y=0, content_width=30, content_height=40),
        "wrapped_hi": _near(_line(wrapped_pin, 0), text="Hi", x=0, y=0, height=20, content_width=20),
        "wrapped_yo": _near(_line(wrapped_pin, 1), text="Yo", x=0, y=20, height=20, content_width=20),
        "wrapped_first": _near(
            _line(wrapped_copy, 0), text="Hello world this", x=30, y=0, height=20, content_width=160
        ),
        "wrapped_second": _near(_line(wrapped_copy, 1), text="wraps", x=30, y=20, height=20, content_width=50),
        "tall_pin": _near(tall_pin, x=0, y=0, content_width=50, content_height=40),
        "tall_word": _near(_line(tall_pin, 0), text="Hello", x=0, y=0, height=20, content_width=50),
        "tall_one_line": isinstance(tall_pin, dict) and isinstance(tall_pin.get("lines"), list) and len(tall_pin["lines"]) == 1,
        "tall_second": _near(_line(tall_copy, 1), text="this wraps", x=50, y=20, height=20, content_width=100),
        "shrink_pin": _near(shrink_pin, x=0, y=0, content_width=80, content_height=40),
        "shrink_hello": _near(_line(shrink_pin, 0), text="Hello", x=0, y=0, height=20, content_width=50),
        "shrink_world": _near(_line(shrink_pin, 1), text="world", x=0, y=20, height=20, content_width=50),
        "shrink_next": _near(_line(shrink_copy, 0), text="Next", x=0, y=40, height=20, content_width=40),
        "empty_pin": _near(empty_pin, x=0, y=0, content_width=0, content_height=0),
        "empty_next": _near(_line(empty_copy, 0), text="Next", x=0, y=0, height=20, content_width=40),
        "child_float": (
            isinstance(child, dict)
            and child.get("outcome") == "invalid"
            and child.get("boxes") is None
            and child.get("reason") == "float content is unsupported"
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
