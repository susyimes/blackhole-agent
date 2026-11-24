"""Copy an element attribute into generated content with attr().

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects attr() exits 0 with passed false.
"""

from __future__ import annotations

import json
import sys

_BASE = "html, body, div, h1, p { margin: 0px } #page { font-size: 10px; line-height: 10px }"


def _place(layout, markup: str, css: str) -> dict[str, object]:
    try:
        placed = layout(markup, _BASE + css, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _box(result: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for box in boxes:
        if isinstance(box, dict) and box.get("id") == ident:
            return box
    return None


def _line(box: dict[str, object] | None) -> tuple[object, ...]:
    if not box:
        return ()
    lines = box.get("lines")
    if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
        return ()
    line = lines[0]
    return (line.get("text"), line.get("x"), line.get("y"), line.get("content_width"), line.get("height"))


def _items(result: dict[str, object], texts: set[str]) -> list[tuple[object, ...]]:
    found: list[tuple[object, ...]] = []
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return found
    for box in boxes:
        if not isinstance(box, dict):
            continue
        line = _line(box)
        if line and line[0] in texts:
            found.append((box.get("x"), box.get("content_width"), line[0]))
    return found


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    head = _place(
        layout_normal_flow,
        '<div id="page"><h1 id="a" title="Intro">AA</h1><p id="next">Z</p></div>',
        'h1 { counter-increment: section } h1::before { content: counter(section) " " attr(title) " " }'
        " h1::after { content: attr(id) }",
    )
    missing = _place(
        layout_normal_flow,
        '<div id="page" title="Nope"><p id="t">Hi</p><p id="next">Z</p></div>',
        '#t::before { content: "[" attr(title) "]" }',
    )
    flexed = _place(
        layout_normal_flow,
        '<div id="page"><div id="row" title="AB">CD</div><p id="next">Z</p></div>',
        '#row { display: flex } #row::before { content: attr(title) } #row::after { content: "EF" }',
    )
    spaced = _place(
        layout_normal_flow,
        '<div id="page"><p id="t" title="A  B"></p><p id="next">Z</p></div>',
        "#t::before { content: attr(title) }",
    )
    fallback = _place(
        layout_normal_flow,
        '<div id="page"><p id="t" title="Go">Hi</p></div>',
        '#t::before { content: attr(title, "none") }',
    )
    unit = _place(
        layout_normal_flow,
        '<div id="page"><p id="t" title="Go">Hi</p></div>',
        "#t::before { content: attr(title px) }",
    )
    observed: dict[str, object] = {
        "head": {
            "outcome": head.get("outcome"),
            "reason": head.get("reason"),
            "line": _line(_box(head, "a")),
            "next_y": None if _box(head, "next") is None else _box(head, "next").get("y"),
        },
        "missing": {
            "outcome": missing.get("outcome"),
            "reason": missing.get("reason"),
            "line": _line(_box(missing, "t")),
            "next_y": None if _box(missing, "next") is None else _box(missing, "next").get("y"),
        },
        "flex": {
            "outcome": flexed.get("outcome"),
            "reason": flexed.get("reason"),
            "items": _items(flexed, {"AB", "CD", "EF"}),
            "next_y": None if _box(flexed, "next") is None else _box(flexed, "next").get("y"),
        },
        "spaced": {
            "outcome": spaced.get("outcome"),
            "reason": spaced.get("reason"),
            "line": _line(_box(spaced, "t")),
        },
        "fallback": {"outcome": fallback.get("outcome"), "reason": fallback.get("reason")},
        "unit": {"outcome": unit.get("outcome"), "reason": unit.get("reason")},
    }
    checks = {
        "counter_and_attribute": observed["head"] == {
            "outcome": "placed",
            "reason": None,
            "line": ("1 Intro AAa", 0, 0, 110, 10),
            "next_y": 10,
        },
        "missing_attribute_is_empty": observed["missing"] == {
            "outcome": "placed",
            "reason": None,
            "line": ("[]Hi", 0, 0, 40, 10),
            "next_y": 10,
        },
        "flex_item": observed["flex"] == {
            "outcome": "placed",
            "reason": None,
            "items": [(0, 20, "AB"), (20, 20, "CD"), (40, 20, "EF")],
            "next_y": 10,
        },
        "collapsed_spaces": observed["spaced"] == {
            "outcome": "placed",
            "reason": None,
            "line": ("A B", 0, 0, 30, 10),
        },
        "fallback_rejected": observed["fallback"] == {
            "outcome": "invalid",
            "reason": "generated content is unsupported",
        },
        "unit_rejected": observed["unit"] == {
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
