"""Shorten a sibling block beside a float, and drop a cleared sibling below it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still ignores the sibling float exits 0 with
passed false.
"""

from __future__ import annotations

import json

_MARKUP = (
    '<div id="page"><i id="pin"></i><p id="copy">Hello world this wraps</p>'
    '<p id="mid">Still beside</p><p id="after">Next</p></div>'
)

_STYLESHEET = """
#pin { float: left; width: 50px; height: 80px; }
#copy, #mid, #after { font-size: 10px; line-height: 20px; }
#after { clear: left; }
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


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    try:
        placed = layout_normal_flow(_MARKUP, _STYLESHEET, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        placed = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        rejected = layout_normal_flow(
            '<div id="bad"><i id="nope"></i><p id="text">Hi</p></div>',
            "#nope { float: left; width: -1px; height: 20px; }",
            viewport_width=200,
        )
    except Exception as exc:  # noqa: BLE001 - a raised rejection is an unmet outcome
        rejected = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}

    boxes = placed.get("boxes") if isinstance(placed, dict) else None
    page = _box(boxes, "page")
    pin = _box(boxes, "pin")
    copy = _box(boxes, "copy")
    mid = _box(boxes, "mid")
    after = _box(boxes, "after")
    observed: dict[str, object] = {
        "outcome": placed.get("outcome") if isinstance(placed, dict) else None,
        "reason": placed.get("reason") if isinstance(placed, dict) else None,
        "page": page,
        "pin": pin,
        "copy": copy,
        "mid": mid,
        "after": after,
        "rejected_outcome": rejected.get("outcome") if isinstance(rejected, dict) else None,
        "rejected_reason": rejected.get("reason") if isinstance(rejected, dict) else None,
    }
    checks = {
        "placed": placed.get("outcome") == "placed" if isinstance(placed, dict) else False,
        "page": _near(page, x=0, y=0, content_width=200, content_height=100),
        "pin": _near(pin, x=0, y=0, content_width=50, content_height=80),
        "copy": _near(copy, x=0, y=0, content_width=200, content_height=40),
        "first": _near(_line(copy, 0), text="Hello world", x=50, y=0, height=20, content_width=110),
        "second": _near(_line(copy, 1), text="this wraps", x=50, y=20, height=20, content_width=100),
        "mid": _near(mid, x=0, y=40, content_width=200, content_height=20),
        "mid_line": _near(_line(mid, 0), text="Still beside", x=50, y=40, height=20, content_width=120),
        "after": _near(after, x=0, y=80, content_width=200, content_height=20),
        "after_line": _near(_line(after, 0), text="Next", x=0, y=80, height=20, content_width=40),
        "negative_float_width": (
            isinstance(rejected, dict)
            and rejected.get("outcome") == "invalid"
            and rejected.get("boxes") is None
            and rejected.get("reason") == "size is invalid"
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
