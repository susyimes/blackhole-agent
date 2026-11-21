"""Place wrapped line boxes inside a paragraph and center the short line.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still ignores text exits 0 with passed false.
"""

from __future__ import annotations

import json

_MARKUP = '<div id="page"><p id="copy">Hello world this wraps</p></div>'

_STYLESHEET = """
#page { padding-top: 4px; }
#copy {
  width: 110px;
  font-size: 10px;
  line-height: 20px;
  text-align: center;
}
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
            '<p id="bad">Hello</p>',
            "#bad { line-height: -1px; }",
            viewport_width=200,
        )
    except Exception as exc:  # noqa: BLE001 - a raised rejection is an unmet outcome
        rejected = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}

    boxes = placed.get("boxes") if isinstance(placed, dict) else None
    page = _box(boxes, "page")
    copy = _box(boxes, "copy")
    first = _line(copy, 0)
    second = _line(copy, 1)
    observed: dict[str, object] = {
        "outcome": placed.get("outcome") if isinstance(placed, dict) else None,
        "reason": placed.get("reason") if isinstance(placed, dict) else None,
        "page": page,
        "copy": copy,
        "rejected_outcome": rejected.get("outcome") if isinstance(rejected, dict) else None,
        "rejected_reason": rejected.get("reason") if isinstance(rejected, dict) else None,
    }
    checks = {
        "placed": placed.get("outcome") == "placed" if isinstance(placed, dict) else False,
        "page": _near(page, content_height=40, border_height=44),
        "copy": _near(copy, y=4, content_height=40),
        "first": _near(first, text="Hello world", x=0, y=4, height=20, content_width=110),
        "second": _near(second, text="this wraps", x=5, y=24, height=20, content_width=100),
        "two_lines": isinstance(copy, dict) and isinstance(copy.get("lines"), list) and len(copy["lines"]) == 2,
        "negative_line_height": (
            isinstance(rejected, dict)
            and rejected.get("outcome") == "invalid"
            and rejected.get("boxes") is None
            and isinstance(rejected.get("reason"), str)
            and "line-height" in str(rejected.get("reason"))
        ),
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
