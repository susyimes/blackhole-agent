"""Paint non-inherited text decoration without growing the line box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that ignores text-decoration reports passed false.
"""

from __future__ import annotations

import json

_RULES = "font-size: 10px; line-height: 10px; "


def _dy(kind: str, font_size: int) -> int:
    if kind == "underline":
        return max(1, font_size // 10)
    if kind == "line-through":
        return -max(1, font_size // 3)
    return -font_size


def _place(function, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = function(markup, stylesheet, viewport_width=200)
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
                "decorations": item.get("decorations"),
                "atoms": item.get("atoms"),
            }
        )
    return found


def _covers_line(line: dict[str, object], owner: str, kind: str, font_size: int) -> bool:
    decorations = line.get("decorations")
    if not isinstance(decorations, list):
        return False
    matches = [
        item
        for item in decorations
        if isinstance(item, dict) and item.get("owner") == owner and item.get("kind") == kind
    ]
    if len(matches) != 1:
        return False
    mark = matches[0]
    return (
        mark.get("x") == line.get("x")
        and mark.get("width") == line.get("width")
        and mark.get("font_size") == font_size
        and mark.get("y") == int(line["y"]) + int(line["height"]) + _dy(kind, font_size)
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    continued = _place(
        layout_normal_flow,
        "<div id='p'>ab<span id='s'>cd</span></div><div id='n'>Z</div>",
        f"#p {{ width: 80px; {_RULES}text-decoration: underline; }} #s {{ text-decoration: none; }} #n {{ height: 10px; {_RULES}}}",
    )
    wrapped = _place(
        layout_normal_flow,
        "<div id='p'>ab cd</div><div id='n'>Z</div>",
        f"#p {{ width: 30px; {_RULES}text-decoration: underline overline; }} #n {{ height: 10px; {_RULES}}}",
    )
    mixed = _place(
        layout_normal_flow,
        "<div id='p'>ab<span id='s'>c</span>d</div><div id='n'>Z</div>",
        (
            f"#p {{ width: 200px; {_RULES}text-decoration: underline; }} "
            "#s { font-size: 20px; line-height: 20px; text-decoration: line-through; } "
            f"#n {{ height: 10px; {_RULES}}}"
        ),
    )
    atomic = _place(
        layout_normal_flow,
        "<div id='p'>ab<span id='a'>XY</span>cd</div>",
        (
            f"#p {{ width: 200px; {_RULES}text-decoration: underline; }} "
            f"#a {{ display: inline-block; {_RULES}}}"
        ),
    )
    bare = _place(
        layout_normal_flow,
        "<div id='p'>ab</div>",
        f"#p {{ width: 80px; {_RULES}}}",
    )
    wavy = _place(
        layout_normal_flow,
        "<div id='p'>ab</div>",
        f"#p {{ width: 80px; {_RULES}text-decoration: underline wavy; }}",
    )
    vertical = _place(
        layout_normal_flow,
        "<div id='p'>ab</div>",
        f"#p {{ writing-mode: vertical-rl; height: 40px; {_RULES}text-decoration: underline; }}",
    )
    continued_lines = _lines(_box(continued, "p"))
    wrapped_lines = _lines(_box(wrapped, "p"))
    mixed_lines = _lines(_box(mixed, "p"))
    atomic_lines = _lines(_box(atomic, "p"))
    atomic_box = _box(atomic, "a")
    atomic_inner = _lines(atomic_box)
    bare_lines = _lines(_box(bare, "p"))
    observed: dict[str, object] = {
        "continued": continued_lines,
        "continued_next": None if _box(continued, "n") is None else _box(continued, "n").get("y"),
        "wrapped": wrapped_lines,
        "wrapped_next": None if _box(wrapped, "n") is None else _box(wrapped, "n").get("y"),
        "mixed": mixed_lines,
        "mixed_next": None if _box(mixed, "n") is None else _box(mixed, "n").get("y"),
        "atomic": atomic_lines,
        "atomic_text": None if not atomic_inner else atomic_inner[0].get("text"),
        "atomic_decorations": None if not atomic_inner else atomic_inner[0].get("decorations"),
        "bare": bare_lines,
        "wavy": wavy.get("outcome"),
        "wavy_reason": wavy.get("reason"),
        "vertical": vertical.get("outcome"),
        "vertical_reason": vertical.get("reason"),
    }
    continued_ok = (
        continued.get("outcome") == "placed"
        and len(continued_lines) == 1
        and continued_lines[0].get("text") == "abcd"
        and continued_lines[0].get("height") == 10
        and _covers_line(continued_lines[0], "p", "underline", 10)
        and len(continued_lines[0].get("decorations") or []) == 1
        and observed["continued_next"] == 10
    )
    def _kind(line: dict[str, object], kind: str) -> dict[str, object] | None:
        marks = line.get("decorations")
        if not isinstance(marks, list):
            return None
        found = [item for item in marks if isinstance(item, dict) and item.get("kind") == kind]
        if len(found) != 1:
            return None
        return found[0]

    first_underline = _kind(wrapped_lines[0], "underline") if wrapped_lines else None
    wrapped_ok = (
        wrapped.get("outcome") == "placed"
        and len(wrapped_lines) == 2
        and all(
            _covers_line(line, "p", "underline", 10) and _covers_line(line, "p", "overline", 10)
            for line in wrapped_lines
        )
        and wrapped_lines[1].get("y") == int(wrapped_lines[0]["y"]) + int(wrapped_lines[0]["height"])
        and observed["wrapped_next"] == int(wrapped_lines[1]["y"]) + int(wrapped_lines[1]["height"])
        and first_underline is not None
        and int(first_underline["y"]) > int(wrapped_lines[0]["y"]) + int(wrapped_lines[0]["height"])
    )
    mixed_line = mixed_lines[0] if mixed_lines else {}
    mixed_marks = mixed_line.get("decorations") if isinstance(mixed_line.get("decorations"), list) else []
    through = next((item for item in mixed_marks if isinstance(item, dict) and item.get("kind") == "line-through"), None)
    mixed_ok = (
        mixed.get("outcome") == "placed"
        and len(mixed_lines) == 1
        and mixed_line.get("text") == "abcd"
        and mixed_line.get("height") == 20
        and _covers_line(mixed_line, "p", "underline", 10)
        and isinstance(through, dict)
        and through.get("owner") == "s"
        and through.get("font_size") == 20
        and through.get("width") == 20
        and through.get("x") == int(mixed_line["x"]) + 20
        and through.get("y") == int(mixed_line["y"]) + int(mixed_line["height"]) + _dy("line-through", 20)
        and observed["mixed_next"] == 20
    )
    atoms = atomic_lines[0].get("atoms") if atomic_lines else None
    slot = atoms[0] if isinstance(atoms, list) and atoms and isinstance(atoms[0], dict) else None
    parent_marks = atomic_lines[0].get("decorations") if atomic_lines else None
    atomic_ok = (
        atomic.get("outcome") == "placed"
        and len(atomic_lines) == 1
        and atomic_lines[0].get("text") == "abcd"
        and isinstance(parent_marks, list)
        and len(parent_marks) == 2
        and all(isinstance(item, dict) and item.get("kind") == "underline" and item.get("owner") == "p" for item in parent_marks)
        and slot is not None
        and parent_marks[0].get("x") == atomic_lines[0].get("x")
        and int(parent_marks[0]["x"]) + int(parent_marks[0]["width"]) == slot.get("x")
        and parent_marks[1].get("x") == int(slot["x"]) + int(slot["width"])
        and observed["atomic_text"] == "XY"
        and observed["atomic_decorations"] is None
    )
    bare_ok = (
        bare.get("outcome") == "placed"
        and len(bare_lines) == 1
        and bare_lines[0].get("decorations") is None
    )
    passed = (
        continued_ok
        and wrapped_ok
        and mixed_ok
        and atomic_ok
        and bare_ok
        and wavy.get("outcome") == "invalid"
        and wavy.get("reason") == "text-decoration is invalid"
        and vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "text decoration is unsupported"
    )
    return bool(passed), observed


if __name__ == "__main__":
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, ensure_ascii=False))
