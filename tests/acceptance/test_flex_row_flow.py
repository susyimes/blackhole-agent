"""Place a flex row in normal flow and keep the next block below it.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects display:flex exits 0 with passed
false.
"""

from __future__ import annotations

import json
import sys

_ROW = (
    '<div id="page"><div id="row"><span id="grow"></span>'
    '<span id="more"></span></div><p id="next">Z</p></div>'
)
_ROW_CSS = """
#page { font-size: 10px; line-height: 10px; }
#row { display: flex; height: 10px; }
#grow { flex: 1; }
#more { flex: 2; }
"""

_FIT = '<div id="fit"><span id="word">BB</span><span id="rest"></span></div>'
_FIT_CSS = """
#fit { display: flex; font-size: 10px; line-height: 10px; }
#word { flex: none; }
#rest { flex: 1; }
"""


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


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

    shared = _lay(layout_normal_flow, _ROW, _ROW_CSS, 300)
    fit = _lay(layout_normal_flow, _FIT, _FIT_CSS, 100)
    row = _box(shared.get("boxes"), "row")
    grow = _box(shared.get("boxes"), "grow")
    more = _box(shared.get("boxes"), "more")
    nxt = _box(shared.get("boxes"), "next")
    fit_box = _box(fit.get("boxes"), "fit")
    word = _box(fit.get("boxes"), "word")
    rest = _box(fit.get("boxes"), "rest")
    observed: dict[str, object] = {
        "shared_outcome": shared.get("outcome"),
        "shared_reason": shared.get("reason"),
        "row": _placed(row),
        "grow": _placed(grow),
        "more": _placed(more),
        "next": _placed(nxt),
        "fit_outcome": fit.get("outcome"),
        "fit_reason": fit.get("reason"),
        "fit": _placed(fit_box),
        "word": _placed(word),
        "rest": _placed(rest),
    }
    row_height = row.get("border_height") if isinstance(row, dict) else None
    checks = {
        "share": (
            shared.get("outcome") == "placed"
            and _near(row, x=0, y=0, content_width=300, content_height=10, border_height=10)
            and _near(grow, x=0, y=0, content_width=100, content_height=10)
            and _near(more, x=100, y=0, content_width=200, content_height=10)
            and isinstance(nxt, dict)
            and nxt.get("y") == row_height
            and row_height == 10
        ),
        "content": (
            fit.get("outcome") == "placed"
            and _near(fit_box, content_width=100, content_height=10, border_height=10)
            and _near(word, x=0, y=0, content_width=20, content_height=10)
            and _near(rest, x=20, y=0, content_width=80, content_height=10)
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
