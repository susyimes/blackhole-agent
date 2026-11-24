"""Paint counter() and counters() into normal-flow lines.

::before reads the element after its own reset and increment. ::after reads
the value after its children. counters() joins every scope, outer scope
first. A counter style formats the integer. The text wraps with the element's
words. ``attr()`` copies that heading's attribute. An unknown style stays rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

from blackhole_agent.css_normal_flow import layout_normal_flow

_BASE = "html, body, div, h1, p { margin: 0px } #page { font-size: 10px; line-height: 10px }"


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


def _lines(result: dict) -> list[tuple]:
    found: list[tuple] = []
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return found
    for box in boxes:
        if not isinstance(box, dict):
            continue
        lines = box.get("lines")
        if not isinstance(lines, list):
            continue
        for line in lines:
            if isinstance(line, dict) and line.get("text"):
                found.append((line.get("text"), line.get("x"), line.get("y"), line.get("content_width")))
    return found


def observe() -> tuple[bool, dict[str, object]]:
    observed: dict[str, object] = {}
    headings = _place(
        '<div id="page"><h1 id="a">AA</h1><h1 id="b">BB</h1><p id="next">Z</p></div>',
        'h1 { counter-increment: section } h1::before { content: counter(section) " " }',
    )
    observed["headings"] = {
        "outcome": headings.get("outcome"),
        "reason": headings.get("reason"),
        "a": _lines(headings and {"boxes": [_box(headings, "a") or {}]}),
        "b": _lines(headings and {"boxes": [_box(headings, "b") or {}]}),
        "next_y": None if _box(headings, "next") is None else _box(headings, "next").get("y"),
    }
    nested = _place(
        '<div id="page"><div id="ch"><div id="sec">X</div></div><p id="next">Z</p></div>',
        '#ch { counter-increment: n } #sec { counter-reset: n; counter-increment: n } '
        '#sec::before { content: counters(n, ".") " " }',
    )
    observed["nested"] = {
        "outcome": nested.get("outcome"),
        "reason": nested.get("reason"),
        "sec": _lines(nested and {"boxes": [_box(nested, "sec") or {}]}),
        "next_y": None if _box(nested, "next") is None else _box(nested, "next").get("y"),
    }
    scope = _place(
        '<div id="page"><div id="ch"><div id="sec">X</div></div><p id="next">Z</p></div>',
        "#ch { counter-reset: n } #sec { counter-increment: n } "
        "#ch::before { content: counter(n) } #ch::after { content: counter(n) }",
    )
    observed["scope"] = {
        "outcome": scope.get("outcome"),
        "reason": scope.get("reason"),
        "lines": _lines(scope),
        "next_y": None if _box(scope, "next") is None else _box(scope, "next").get("y"),
    }
    alpha = _place(
        '<div id="page"><h1 id="a">AA</h1><h1 id="b">BB</h1><p id="next">Z</p></div>',
        "h1 { counter-increment: section } h1::before { content: counter(section, upper-alpha) \" \" }",
    )
    observed["alpha"] = {
        "outcome": alpha.get("outcome"),
        "reason": alpha.get("reason"),
        "a": _lines(alpha and {"boxes": [_box(alpha, "a") or {}]}),
        "b": _lines(alpha and {"boxes": [_box(alpha, "b") or {}]}),
    }
    wrapped = _place(
        '<div id="page"><p id="t">BB</p><p id="next">Z</p></div>',
        '#t { width: 30px; counter-increment: n } #t::before { content: counter(n) " " }',
    )
    observed["wrap"] = {
        "outcome": wrapped.get("outcome"),
        "reason": wrapped.get("reason"),
        "lines": _lines(wrapped and {"boxes": [_box(wrapped, "t") or {}]}),
        "height": None if _box(wrapped, "t") is None else _box(wrapped, "t").get("content_height"),
        "next_y": None if _box(wrapped, "next") is None else _box(wrapped, "next").get("y"),
    }
    attr = _place(
        '<div id="page"><h1 id="a" title="Hi">AA</h1></div>',
        'h1::before { content: attr(title) " " }',
    )
    observed["attr"] = {
        "outcome": attr.get("outcome"),
        "reason": attr.get("reason"),
        "lines": _lines(attr),
    }
    style = _place(
        '<div id="page"><h1 id="a">AA</h1></div>',
        "h1 { counter-increment: section } h1::before { content: counter(section, disc) }",
    )
    observed["style"] = {"outcome": style.get("outcome"), "reason": style.get("reason")}

    headings_ok = observed["headings"] == {
        "outcome": "placed",
        "reason": None,
        "a": [("1 AA", 0, 0, 40)],
        "b": [("2 BB", 0, 10, 40)],
        "next_y": 20,
    }
    nested_ok = observed["nested"] == {
        "outcome": "placed",
        "reason": None,
        "sec": [("1.1 X", 0, 0, 50)],
        "next_y": 10,
    }
    scope_lines = observed["scope"]["lines"]
    scope_ok = (
        observed["scope"]["outcome"] == "placed"
        and observed["scope"]["next_y"] == 30
        and ("0", 0, 0, 10) in scope_lines
        and ("X", 0, 10, 10) in scope_lines
        and ("1", 0, 20, 10) in scope_lines
    )
    alpha_ok = observed["alpha"]["outcome"] == "placed" and observed["alpha"]["a"] == [("A AA", 0, 0, 40)] and (
        observed["alpha"]["b"] == [("B BB", 0, 10, 40)]
    )
    wrap_ok = observed["wrap"] == {
        "outcome": "placed",
        "reason": None,
        "lines": [("1", 0, 0, 10), ("BB", 0, 10, 20)],
        "height": 20,
        "next_y": 20,
    }
    attr_ok = observed["attr"] == {
        "outcome": "placed",
        "reason": None,
        "lines": [("Hi AA", 0, 0, 50)],
    }
    style_ok = observed["style"] == {"outcome": "invalid", "reason": "counter style disc is invalid"}
    passed = all((headings_ok, nested_ok, scope_ok, alpha_ok, wrap_ok, attr_ok, style_ok))
    return passed, observed


def main() -> None:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
