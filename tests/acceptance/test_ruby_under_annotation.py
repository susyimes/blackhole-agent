"""Place a second ruby annotation under the base.

On a marginless 40px line at 10px font and line-height, ZZ before a ruby
whose base is A, over mark is B, and under mark is WWW wraps. ZZ stays at
y 0 with height 10. The ruby box starts at y 10, 30px wide and 30px tall.
B is at y 10, A at y 20, and WWW at y 30. The following block starts at
y 40. Without the under mark the same text stays one 20px line and the
following block starts at y 20. A third annotation is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_CSS = (
    "html, body, div, rt { margin: 0px; font-size: 10px; line-height: 10px; }\n"
    "#row { width: 40px; }\n"
)
_PAGE = '<div id="row">{body}</div><div id="next">N</div>'


def _lay(body: str) -> dict[str, object]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        placed = layout_normal_flow(_PAGE.format(body=body), _CSS, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _box(placed: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = placed.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    found = []
    for item in box["lines"]:
        if not isinstance(item, dict):
            continue
        atoms = item.get("atoms") if isinstance(item.get("atoms"), list) else []
        found.append(
            {
                "text": item.get("text"),
                "x": item.get("x"),
                "y": item.get("y"),
                "width": item.get("content_width"),
                "height": item.get("height"),
                "atoms": [
                    {"id": atom.get("id"), "x": atom.get("x"), "width": atom.get("width")}
                    for atom in atoms
                    if isinstance(atom, dict)
                ],
            }
        )
    return found


def _view(body: str) -> dict[str, object]:
    placed = _lay(body)
    row = _box(placed, "row")
    ruby = _box(placed, "rb")
    nxt = _box(placed, "next")
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "row": _lines(row),
        "ruby": _lines(ruby),
        "ruby_box": None
        if ruby is None
        else {
            "x": ruby.get("x"),
            "y": ruby.get("y"),
            "width": ruby.get("content_width"),
            "height": ruby.get("content_height"),
        },
        "next_y": None if nxt is None else nxt.get("y"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    under = _view('ZZ<ruby id="rb">A<rt>B</rt><rt>WWW</rt></ruby>')
    single = _view('ZZ<ruby id="rb">A<rt>B</rt></ruby>')
    third = _view('ZZ<ruby id="rb">A<rt>B</rt><rt>W</rt><rt>Q</rt></ruby>')
    observed = {"under": under, "single": single, "third": third}
    ruby_lines = under["ruby"]
    row_lines = under["row"]
    over = ruby_lines[0] if isinstance(ruby_lines, list) and len(ruby_lines) > 0 else None
    base = ruby_lines[1] if isinstance(ruby_lines, list) and len(ruby_lines) > 1 else None
    below = ruby_lines[2] if isinstance(ruby_lines, list) and len(ruby_lines) > 2 else None
    first = row_lines[0] if isinstance(row_lines, list) and len(row_lines) > 0 else None
    second = row_lines[1] if isinstance(row_lines, list) and len(row_lines) > 1 else None
    slot = None
    if isinstance(second, dict) and second.get("atoms"):
        slot = second["atoms"][0]
    under_ok = (
        under["outcome"] == "placed"
        and isinstance(row_lines, list)
        and len(row_lines) == 2
        and first == {"text": "ZZ", "x": 0, "y": 0, "width": 20, "height": 10, "atoms": []}
        and second is not None
        and second.get("text") == ""
        and second.get("y") == 10
        and second.get("height") == 30
        and second.get("width") == 30
        and slot == {"id": "rb", "x": 0, "width": 30}
        and under["ruby_box"] == {"x": 0, "y": 10, "width": 30, "height": 30}
        and over == {"text": "B", "x": 10, "y": 10, "width": 10, "height": 10, "atoms": []}
        and base == {"text": "A", "x": 10, "y": 20, "width": 10, "height": 10, "atoms": []}
        and below == {"text": "WWW", "x": 0, "y": 30, "width": 30, "height": 10, "atoms": []}
        and under["next_y"] == 40
    )
    single_lines = single["row"]
    single_ok = (
        single["outcome"] == "placed"
        and isinstance(single_lines, list)
        and len(single_lines) == 1
        and single_lines[0].get("text") == "ZZ"
        and single_lines[0].get("y") == 0
        and single_lines[0].get("height") == 20
        and single["ruby_box"] == {"x": 20, "y": 0, "width": 10, "height": 20}
        and single["next_y"] == 20
    )
    third_ok = third["outcome"] == "invalid" and third["reason"] == "ruby annotation is unsupported"
    return bool(under_ok and single_ok and third_ok), observed


if __name__ == "__main__":
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
