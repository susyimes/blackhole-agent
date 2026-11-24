"""Place an inline-flex on the line with the words around it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects display:inline-flex exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_SHARE = (
    '<div id="page"><p id="row">A<span id="atom"><span id="grow"></span>'
    '<span id="more"></span></span>C</p><p id="next">Z</p></div>'
)
_SHARE_CSS = """
#page, #row, #next { font-size: 10px; line-height: 10px; }
#atom { display: inline-flex; width: 30px; height: 10px; }
#grow { flex: 1; }
#more { flex: 2; }
"""

_FIT = '<p id="row">A<span id="atom"><span id="one">BB</span><span id="two">CC</span></span>D</p>'
_FIT_CSS = """
#row { font-size: 10px; line-height: 10px; }
#atom { display: inline-flex; }
#one, #two { flex: none; }
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


def _placed(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
    }


def _compact(line: dict[str, object] | None) -> dict[str, object] | None:
    if line is None:
        return None
    return {
        "text": line.get("text"),
        "x": line.get("x"),
        "y": line.get("y"),
        "height": line.get("height"),
        "content_width": line.get("content_width"),
        "atoms": line.get("atoms"),
    }


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

    shared = _lay(layout_normal_flow, _SHARE, _SHARE_CSS, 200)
    fit = _lay(layout_normal_flow, _FIT, _FIT_CSS, 200)
    narrow = _lay(layout_normal_flow, _FIT, _FIT_CSS, 45)
    row = _box(shared.get("boxes"), "row")
    atom = _box(shared.get("boxes"), "atom")
    grow = _box(shared.get("boxes"), "grow")
    more = _box(shared.get("boxes"), "more")
    nxt = _box(shared.get("boxes"), "next")
    fit_row = _box(fit.get("boxes"), "row")
    fit_atom = _box(fit.get("boxes"), "atom")
    one = _box(fit.get("boxes"), "one")
    two = _box(fit.get("boxes"), "two")
    narrow_row = _box(narrow.get("boxes"), "row")
    narrow_atom = _box(narrow.get("boxes"), "atom")
    observed: dict[str, object] = {
        "shared_outcome": shared.get("outcome"),
        "shared_reason": shared.get("reason"),
        "row": _placed(row),
        "line": _compact(_line(row, 0)),
        "atom": _placed(atom),
        "grow": _placed(grow),
        "more": _placed(more),
        "next": _placed(nxt),
        "fit_outcome": fit.get("outcome"),
        "fit_reason": fit.get("reason"),
        "fit_line": _compact(_line(fit_row, 0)),
        "fit_atom": _placed(fit_atom),
        "one": _placed(one),
        "two": _placed(two),
        "narrow_outcome": narrow.get("outcome"),
        "narrow_reason": narrow.get("reason"),
        "narrow_row": _placed(narrow_row),
        "narrow_lines": [
            _compact(_line(narrow_row, index)) for index in range(3)
        ],
        "narrow_atom": _placed(narrow_atom),
    }
    checks = {
        "definite_items_share_the_line": (
            shared.get("outcome") == "placed"
            and _near(row, y=0, content_height=10)
            and _near(
                _line(row, 0),
                text="AC",
                x=0,
                y=0,
                height=10,
                content_width=50,
                atoms=[{"id": "atom", "x": 10, "width": 30}],
            )
            and _near(atom, x=10, y=0, content_width=30, content_height=10)
            and _near(grow, x=10, y=0, content_width=10, content_height=10)
            and _near(more, x=20, y=0, content_width=20, content_height=10)
            and _near(nxt, x=0, y=10)
            and isinstance(row, dict)
            and isinstance(row.get("lines"), list)
            and len(row["lines"]) == 1
        ),
        "flex_none_shrinks_between_words": (
            fit.get("outcome") == "placed"
            and _near(
                _line(fit_row, 0),
                text="AD",
                x=0,
                y=0,
                height=10,
                content_width=60,
                atoms=[{"id": "atom", "x": 10, "width": 40}],
            )
            and _near(fit_atom, x=10, y=0, content_width=40, content_height=10)
            and _near(one, x=10, y=0, content_width=20, content_height=10)
            and _near(two, x=30, y=0, content_width=20, content_height=10)
        ),
        "atomic_box_wraps_intact": (
            narrow.get("outcome") == "placed"
            and _near(narrow_row, content_height=30)
            and _near(
                _line(narrow_row, 0),
                text="A",
                x=0,
                y=0,
                height=10,
                content_width=10,
            )
            and _near(
                _line(narrow_row, 1),
                text="",
                x=0,
                y=10,
                height=10,
                content_width=40,
                atoms=[{"id": "atom", "x": 0, "width": 40}],
            )
            and _near(
                _line(narrow_row, 2),
                text="D",
                x=0,
                y=20,
                height=10,
                content_width=10,
            )
            and _near(narrow_atom, x=0, y=10, content_width=40, content_height=10)
        ),
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
