"""Place one ruby annotation above its base, and a second one under it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that paints the annotation as the next inline glyphs
reports passed false.
"""

from __future__ import annotations

import json

_RULES = "font-size: 10px; line-height: 10px; "
_RT = "rt { font-size: 5px; line-height: 5px; }\n"


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(result, dict):
        return {"outcome": "error", "reason": "result", "boxes": None}
    return result


def _box(result: dict[str, object], box_id: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == box_id:
            return item
    return None


def _lines(box: dict[str, object] | None) -> list[dict[str, object]]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    found = []
    for item in box["lines"]:
        if not isinstance(item, dict):
            continue
        found.append(
            {
                "text": item.get("text"),
                "x": item.get("x"),
                "y": item.get("y"),
                "width": item.get("content_width"),
                "height": item.get("height"),
                "atoms": item.get("atoms"),
            }
        )
    return found


def _line(lines: list[dict[str, object]], text: str) -> dict[str, object] | None:
    found = [item for item in lines if item.get("text") == text]
    if len(found) != 1:
        return None
    return found[0]


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    wide = _place(
        layout_normal_flow,
        "<div id='row'>Z<ruby id='rb'>A<rt>BCDE</rt></ruby>Z</div><div id='next'>N</div>",
        f"#row {{ width: 200px; {_RULES}}} #next {{ height: 10px; {_RULES}}} {_RT}",
    )
    declared = _place(
        layout_normal_flow,
        "<div id='row'>Q<ruby id='rb'>ABCD<rt>XX</rt></ruby>Q</div><div id='next'>N</div>",
        (
            f"#row {{ width: 200px; {_RULES}}} #next {{ height: 10px; {_RULES}}} "
            f"ruby {{ display: ruby; }} {_RT}"
        ),
    )
    paired = _place(
        layout_normal_flow,
        "<div id='row'>A<ruby id='rb'>B<rt>C</rt><rt>D</rt></ruby></div>",
        f"#row {{ width: 200px; {_RULES}}} {_RT}",
    )
    vertical = _place(
        layout_normal_flow,
        "<div id='row'>A<ruby id='rb'>B<rt>CD</rt></ruby></div>",
        f"#row {{ writing-mode: vertical-rl; height: 80px; {_RULES}}} {_RT}",
    )
    floated = _place(
        layout_normal_flow,
        "<div id='row'><div id='f'>FF</div>A<ruby id='rb'>B<rt>CD</rt></ruby></div>",
        f"#row {{ width: 200px; {_RULES}}} #f {{ float: left; }} {_RT}",
    )
    row = _box(wide, "row")
    ruby = _box(wide, "rb")
    nxt = _box(wide, "next")
    declared_row = _box(declared, "row")
    declared_ruby = _box(declared, "rb")
    declared_next = _box(declared, "next")
    row_lines = _lines(row)
    ruby_lines = _lines(ruby)
    declared_lines = _lines(declared_row)
    declared_ruby_lines = _lines(declared_ruby)
    observed: dict[str, object] = {
        "wide_outcome": wide.get("outcome"),
        "wide_reason": wide.get("reason"),
        "row": row_lines,
        "ruby": ruby_lines,
        "ruby_box": None
        if ruby is None
        else {
            "x": ruby.get("x"),
            "y": ruby.get("y"),
            "width": ruby.get("content_width"),
            "height": ruby.get("content_height"),
        },
        "next_y": None if nxt is None else nxt.get("y"),
        "declared_outcome": declared.get("outcome"),
        "declared_row": declared_lines,
        "declared_ruby": declared_ruby_lines,
        "declared_box": None
        if declared_ruby is None
        else {
            "x": declared_ruby.get("x"),
            "y": declared_ruby.get("y"),
            "width": declared_ruby.get("content_width"),
            "height": declared_ruby.get("content_height"),
        },
        "declared_next_y": None if declared_next is None else declared_next.get("y"),
        "paired": paired.get("outcome"),
        "paired_reason": paired.get("reason"),
        "vertical": vertical.get("outcome"),
        "vertical_reason": vertical.get("reason"),
        "float": floated.get("outcome"),
        "float_reason": floated.get("reason"),
    }
    annotation = _line(ruby_lines, "BCDE")
    base = _line(ruby_lines, "A")
    host = row_lines[0] if row_lines else None
    slot = None
    if host is not None and isinstance(host.get("atoms"), list) and host["atoms"]:
        candidate = host["atoms"][0]
        slot = candidate if isinstance(candidate, dict) else None
    wide_ok = (
        wide.get("outcome") == "placed"
        and ruby is not None
        and host is not None
        and len(row_lines) == 1
        and host.get("text") == "ZZ"
        and host.get("height") == 15
        and host.get("width") == 40
        and host.get("y") == 0
        and slot is not None
        and slot.get("id") == "rb"
        and slot.get("x") == 10
        and slot.get("width") == 20
        and observed["ruby_box"]
        == {"x": 10, "y": 0, "width": 20, "height": 15}
        and annotation is not None
        and base is not None
        and annotation.get("x") == 10
        and annotation.get("y") == 0
        and annotation.get("width") == 20
        and annotation.get("height") == 5
        and base.get("x") == 15
        and base.get("y") == 5
        and base.get("width") == 10
        and base.get("height") == 10
        and observed["next_y"] == 15
    )
    short = _line(declared_ruby_lines, "XX")
    long = _line(declared_ruby_lines, "ABCD")
    declared_host = declared_lines[0] if declared_lines else None
    declared_ok = (
        declared.get("outcome") == "placed"
        and declared_ruby is not None
        and declared_host is not None
        and len(declared_lines) == 1
        and declared_host.get("text") == "QQ"
        and declared_host.get("height") == 15
        and declared_host.get("width") == 60
        and observed["declared_box"] == {"x": 10, "y": 0, "width": 40, "height": 15}
        and short is not None
        and long is not None
        and short.get("x") == 25
        and short.get("y") == 0
        and short.get("width") == 10
        and short.get("height") == 5
        and long.get("x") == 10
        and long.get("y") == 5
        and long.get("width") == 40
        and long.get("height") == 10
        and observed["declared_next_y"] == 15
    )
    paired_row = _box(paired, "row")
    paired_ruby = _box(paired, "rb")
    paired_lines = _lines(paired_row)
    paired_ruby_lines = _lines(paired_ruby)
    paired_host = paired_lines[0] if paired_lines else None
    paired_slot = None
    if paired_host is not None and isinstance(paired_host.get("atoms"), list) and paired_host["atoms"]:
        candidate = paired_host["atoms"][0]
        paired_slot = candidate if isinstance(candidate, dict) else None
    paired_over = _line(paired_ruby_lines, "C")
    paired_base = _line(paired_ruby_lines, "B")
    paired_under = _line(paired_ruby_lines, "D")
    paired_ok = (
        paired.get("outcome") == "placed"
        and paired_host is not None
        and len(paired_lines) == 1
        and paired_host.get("text") == "A"
        and paired_host.get("height") == 20
        and paired_host.get("width") == 20
        and paired_slot == {"id": "rb", "x": 10, "width": 10}
        and paired_ruby is not None
        and paired_ruby.get("content_width") == 10
        and paired_ruby.get("content_height") == 20
        and paired_over is not None
        and paired_over.get("x") == 12
        and paired_over.get("y") == 0
        and paired_over.get("width") == 5
        and paired_over.get("height") == 5
        and paired_base is not None
        and paired_base.get("x") == 10
        and paired_base.get("y") == 5
        and paired_base.get("width") == 10
        and paired_base.get("height") == 10
        and paired_under is not None
        and paired_under.get("x") == 12
        and paired_under.get("y") == 15
        and paired_under.get("width") == 5
        and paired_under.get("height") == 5
    )
    passed = (
        wide_ok
        and declared_ok
        and paired_ok
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "ruby writing mode is unsupported"
        and floated.get("outcome") == "invalid"
        and floated.get("reason") == "ruby beside a float is unsupported"
    )
    return bool(passed), observed


if __name__ == "__main__":
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
