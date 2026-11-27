"""Place ::before and ::after string content in normal flow.

A text-only block paints the strings on its line. An id beats a type. A later
none removes the string. A parent of block children turns the leading string
into an anonymous block. A flex container keeps each pseudo as its own item.
``attr()`` copies the element's attribute onto the line. A typed or unquoted
attr() and any other content function, and a generated box property, stay
rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

from blackhole_agent.css_normal_flow import layout_normal_flow

_PAGE = '<div id="page"><p id="t">Hello</p><p id="next">Z</p></div>'
_BASE = "html, body, div, p { margin: 0px } #page { font-size: 10px; line-height: 10px }"


def _place(markup: str, css: str, *, width: int = 200):
    return layout_normal_flow(markup, _BASE + css, viewport_width=width)


def _box(result: dict, ident: str) -> dict | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for box in boxes:
        if isinstance(box, dict) and box.get("id") == ident:
            return box
    return None


def _line(box: dict | None) -> tuple:
    if not box:
        return ()
    lines = box.get("lines")
    if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
        return ()
    line = lines[0]
    return (line.get("text"), line.get("x"), line.get("y"), line.get("content_width"), len(lines))


def observe() -> tuple[bool, dict[str, object]]:
    observed: dict[str, object] = {}
    joined = _place(_PAGE, '#t::before { content: "Go " } #t::after { content: "!" }')
    text = _box(joined, "t")
    nxt = _box(joined, "next")
    observed["joined"] = {
        "outcome": joined.get("outcome"),
        "reason": joined.get("reason"),
        "line": _line(text),
        "next_y": None if nxt is None else nxt.get("y"),
    }
    wrapped = _place(_PAGE.replace(">Hello<", ">BBBB<"), "#t { width: 40px } #t::before { content: \"AAAA \" }")
    wrap_box = _box(wrapped, "t")
    wrap_next = _box(wrapped, "next")
    wrap_lines = ()
    if wrap_box and isinstance(wrap_box.get("lines"), list):
        wrap_lines = tuple(
            (line.get("text"), line.get("content_width"))
            for line in wrap_box["lines"]
            if isinstance(line, dict)
        )
    observed["wrap"] = {
        "outcome": wrapped.get("outcome"),
        "lines": wrap_lines,
        "height": None if wrap_box is None else wrap_box.get("content_height"),
        "next_y": None if wrap_next is None else wrap_next.get("y"),
    }
    parent = _place(
        '<div id="page"><p id="t">Hello</p><p id="next">Z</p></div>',
        '#page::before { content: "AB" }',
    )
    parent_lines = []
    if isinstance(parent.get("boxes"), list):
        for box in parent["boxes"]:
            if not isinstance(box, dict):
                continue
            lines = box.get("lines")
            if isinstance(lines, list) and lines and isinstance(lines[0], dict) and lines[0].get("text"):
                parent_lines.append((box.get("id"), lines[0].get("text"), lines[0].get("y")))
    parent_next = _box(parent, "next")
    observed["parent"] = {
        "outcome": parent.get("outcome"),
        "lines": parent_lines,
        "next_y": None if parent_next is None else parent_next.get("y"),
    }
    cleared = _place(_PAGE, '#t::before { content: "Go " } #t::before { content: none }')
    observed["none"] = {"outcome": cleared.get("outcome"), "line": _line(_box(cleared, "t"))}
    specific = _place(_PAGE, 'p::before { content: "B" } #t::before { content: "A" }')
    observed["specific"] = {"outcome": specific.get("outcome"), "line": _line(_box(specific, "t"))}
    flex = _place(
        '<div id="page"><div id="row">CD</div><p id="next">Z</p></div>',
        '#row { display: flex } #row::before { content: "AB" } #row::after { content: "EF" }',
    )
    flex_items = []
    if isinstance(flex.get("boxes"), list):
        for box in flex["boxes"]:
            if not isinstance(box, dict):
                continue
            line = _line(box)
            if line and line[0] in {"AB", "CD", "EF"}:
                flex_items.append((box.get("x"), box.get("content_width"), line[:1]))
    flex_next = _box(flex, "next")
    observed["flex"] = {
        "outcome": flex.get("outcome"),
        "reason": flex.get("reason"),
        "items": flex_items,
        "next_y": None if flex_next is None else flex_next.get("y"),
    }
    function = _place(
        '<div id="page"><p id="t" title="Go">Hello</p><p id="next">Z</p></div>',
        '#t::before { content: attr(title) " " }',
    )
    function_next = _box(function, "next")
    observed["function"] = {
        "outcome": function.get("outcome"),
        "reason": function.get("reason"),
        "line": _line(_box(function, "t")),
        "next_y": None if function_next is None else function_next.get("y"),
    }
    unknown = _place(_PAGE, "#t::before { content: env(missing) }")
    observed["unknown"] = {"outcome": unknown.get("outcome"), "reason": unknown.get("reason")}
    boxed = _place(_PAGE, '#t::before { content: "A"; display: block }')
    observed["box"] = {"outcome": boxed.get("outcome"), "reason": boxed.get("reason")}

    joined_ok = observed["joined"] == {
        "outcome": "placed",
        "reason": None,
        "line": ("Go Hello!", 0, 0, 90, 1),
        "next_y": 10,
    }
    wrap_ok = observed["wrap"] == {
        "outcome": "placed",
        "lines": (("AAAA", 40), ("BBBB", 40)),
        "height": 20,
        "next_y": 20,
    }
    parent_ok = observed["parent"]["outcome"] == "placed" and observed["parent"]["next_y"] == 20 and (
        ("AB", 0) in [(text, y) for _box_id, text, y in observed["parent"]["lines"]]
        and ("Hello", 10) in [(text, y) for _box_id, text, y in observed["parent"]["lines"]]
    )
    none_ok = observed["none"] == {"outcome": "placed", "line": ("Hello", 0, 0, 50, 1)}
    specific_ok = observed["specific"]["outcome"] == "placed" and observed["specific"]["line"][:1] == ("AHello",)
    flex_ok = observed["flex"]["outcome"] == "placed" and observed["flex"]["items"] == [
        (0, 20, ("AB",)),
        (20, 20, ("CD",)),
        (40, 20, ("EF",)),
    ] and observed["flex"]["next_y"] == 10
    function_ok = observed["function"] == {
        "outcome": "placed",
        "reason": None,
        "line": ("Go Hello", 0, 0, 80, 1),
        "next_y": 10,
    }
    unknown_ok = observed["unknown"] == {
        "outcome": "invalid",
        "reason": "generated content is unsupported",
    }
    box_ok = observed["box"] == {"outcome": "invalid", "reason": "generated box is unsupported"}
    passed = all((joined_ok, wrap_ok, parent_ok, none_ok, specific_ok, flex_ok, function_ok, unknown_ok, box_ok))
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
