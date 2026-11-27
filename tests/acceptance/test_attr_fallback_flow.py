"""Use a quoted attr() fallback when the named attribute is missing.

On a marginless 10px page, a missing title with attr(title, "AB CD EF") at a
20px width paints AB, CD, and EF and starts the next block at y 30. The same
call without a fallback adds no glyphs, so that block stays at y 0. A present
title, including the empty string, keeps its own text. A parent title is not
read. Spaces in the fallback collapse. A flex row takes the fallback as its
own item. A unit and an unquoted fallback stay invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_BASE = "html, body, div, p { margin: 0px; font-size: 10px; line-height: 10px; }\n"
_PAGE = '<div id="page"><p id="t">{body}</p><p id="next">Z</p></div>'


def _lay(markup: str, stylesheet: str, width: int = 200) -> dict[str, object]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - a missing layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    try:
        placed = layout_normal_flow(markup, stylesheet, viewport_width=width)
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


def _lines(placed: dict[str, object], ident: str = "t") -> tuple:
    box = _box(placed, ident)
    if box is None or not isinstance(box.get("lines"), list):
        return ()
    return tuple(
        (line.get("text"), line.get("y"), line.get("content_width"))
        for line in box["lines"]
        if isinstance(line, dict)
    )


def _view(placed: dict[str, object]) -> dict[str, object]:
    nxt = _box(placed, "next")
    return {
        "outcome": placed.get("outcome"),
        "reason": placed.get("reason"),
        "lines": _lines(placed),
        "next_y": None if nxt is None else nxt.get("y"),
    }


def _page(body: str, css: str, width: int = 200) -> dict[str, object]:
    return _view(_lay(_PAGE.format(body=body), _BASE + css, width))


def _flex_items(placed: dict[str, object]) -> list[tuple[object, ...]]:
    found: list[tuple[object, ...]] = []
    boxes = placed.get("boxes")
    if not isinstance(boxes, list):
        return found
    for box in boxes:
        if not isinstance(box, dict) or not isinstance(box.get("lines"), list):
            continue
        if not box["lines"] or not isinstance(box["lines"][0], dict):
            continue
        text = box["lines"][0].get("text")
        if text in {"AB", "CD", "EF"}:
            found.append((box.get("x"), box.get("content_width"), text))
    return found


def observe() -> tuple[bool, dict[str, object]]:
    missing = _page("", '#t { width: 20px } #t::before { content: attr( title , "AB CD EF" ) }')
    omitted = _page("", "#t { width: 20px } #t::before { content: attr(title) }")
    present = _view(
        _lay(
            '<div id="page"><p id="t" title="Z"></p><p id="next">Z</p></div>',
            _BASE + '#t { width: 20px } #t::before { content: attr(title, "AB CD EF") }',
        )
    )
    empty = _view(
        _lay(
            '<div id="page"><p id="t" title=""></p><p id="next">Z</p></div>',
            _BASE + '#t { width: 80px } #t::before { content: attr(title, "AB CD EF") }',
        )
    )
    parent = _view(
        _lay(
            '<div id="page" title="AB CD EF"><p id="t"></p><p id="next">Z</p></div>',
            _BASE + '#t { width: 80px } #t::before { content: attr(title, "QQ") }',
        )
    )
    own = _view(
        _lay(
            '<div id="page"><p id="t" title="AB CD EF"></p><p id="next">Z</p></div>',
            _BASE + '#t { width: 20px } #t::before { content: attr(title, "Z") }',
        )
    )
    spaces = _page("", '#t::before { content: attr(title, "A  B") }')
    blank = _page("", '#t { width: 80px } #t::before { content: attr(title, "") }')
    flexed = _lay(
        '<div id="page"><div id="row">CD</div><p id="next">Z</p></div>',
        _BASE + '#row { display: flex } #row::before { content: attr(title, "AB") } #row::after { content: "EF" }',
    )
    unit = _page("Hi", "#t::before { content: attr(title px) }")
    unquoted = _page("Hi", "#t::before { content: attr(title, none) }")
    observed: dict[str, object] = {
        "missing": missing,
        "omitted": omitted,
        "present": present,
        "empty": empty,
        "parent": parent,
        "own": own,
        "spaces": spaces,
        "blank_fallback": blank,
        "flex": {
            "outcome": flexed.get("outcome"),
            "reason": flexed.get("reason"),
            "items": _flex_items(flexed),
            "next_y": None if _box(flexed, "next") is None else _box(flexed, "next").get("y"),
        },
        "unit": {"outcome": unit["outcome"], "reason": unit["reason"]},
        "unquoted": {"outcome": unquoted["outcome"], "reason": unquoted["reason"]},
    }
    wrapped = {
        "outcome": "placed",
        "reason": None,
        "lines": (("AB", 0, 20), ("CD", 10, 20), ("EF", 20, 20)),
        "next_y": 30,
    }
    quiet = {"outcome": "placed", "reason": None, "lines": (), "next_y": 0}
    checks = {
        "missing_fallback_wraps": missing == wrapped,
        "omitted_fallback_adds_nothing": omitted == quiet,
        "present_attribute_wins": present == {
            "outcome": "placed",
            "reason": None,
            "lines": (("Z", 0, 10),),
            "next_y": 10,
        },
        "empty_attribute_wins": empty == quiet,
        "parent_attribute_is_not_read": parent == {
            "outcome": "placed",
            "reason": None,
            "lines": (("QQ", 0, 20),),
            "next_y": 10,
        },
        "present_attribute_wraps": own == wrapped,
        "fallback_spaces_collapse": spaces == {
            "outcome": "placed",
            "reason": None,
            "lines": (("A B", 0, 30),),
            "next_y": 10,
        },
        "empty_fallback_adds_nothing": blank == quiet,
        "flex_item": observed["flex"] == {
            "outcome": "placed",
            "reason": None,
            "items": [(0, 20, "AB"), (20, 20, "CD"), (40, 20, "EF")],
            "next_y": 10,
        },
        "unit_rejected": observed["unit"] == {
            "outcome": "invalid",
            "reason": "generated content is unsupported",
        },
        "unquoted_rejected": observed["unquoted"] == {
            "outcome": "invalid",
            "reason": "generated content is unsupported",
        },
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
