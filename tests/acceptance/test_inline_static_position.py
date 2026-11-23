"""Place an inline absolute at its static position inside the line.

A word that does not fit after the preceding text starts on the next line.
A word that fits stays on the first line. The parent's in-flow lines omit the
absolute. Explicit insets ignore that slot. A block-level absolute in the
same line stays invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects the inline slot exits 0 with
passed false.
"""

from __future__ import annotations

import json

_FONT = "#page, #host, #wide, #pinned, #next, #abs, #fit, #pin, #block { font-size: 10px; }"
_WRAP_MARKUP = (
    '<div id="page"><div id="host">AAAA <span id="abs">BB</span> CC</div>'
    '<div id="next">Z</div></div>'
)
_WRAP_CSS = _FONT + """
#host { position: relative; width: 50px; padding-left: 8px; }
#abs { position: absolute; }
"""
_FIT_MARKUP = '<div id="page"><div id="wide">AA <span id="fit">B</span> CD</div></div>'
_FIT_CSS = _FONT + """
#wide { position: relative; width: 200px; padding-left: 8px; }
#fit { position: absolute; }
"""
_PIN_MARKUP = '<div id="page"><div id="pinned">AAAA <span id="pin">BB</span> CC</div></div>'
_PIN_CSS = _FONT + """
#pinned { position: relative; width: 50px; padding-left: 8px; }
#pin { position: absolute; left: 0px; top: 0px; }
"""
_BLOCK_MARKUP = '<div id="page"><div id="host">AAAA <div id="block">BB</div> CC</div></div>'
_BLOCK_CSS = _FONT + """
#host { position: relative; width: 50px; padding-left: 8px; }
#block { position: absolute; }
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


def _place(markup: str, stylesheet: str) -> dict[str, object]:
    from blackhole_agent.css_normal_flow import layout_normal_flow

    placed = layout_normal_flow(markup, stylesheet, viewport_width=400)
    return placed if isinstance(placed, dict) else {"outcome": "error", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        wrapped = _place(_WRAP_MARKUP, _WRAP_CSS)
        fitted = _place(_FIT_MARKUP, _FIT_CSS)
        pinned = _place(_PIN_MARKUP, _PIN_CSS)
        blocked = _place(_BLOCK_MARKUP, _BLOCK_CSS)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    host = _box(wrapped.get("boxes"), "host")
    absolute = _box(wrapped.get("boxes"), "abs")
    nxt = _box(wrapped.get("boxes"), "next")
    wide = _box(fitted.get("boxes"), "wide")
    fit = _box(fitted.get("boxes"), "fit")
    pin_host = _box(pinned.get("boxes"), "pinned")
    pin = _box(pinned.get("boxes"), "pin")
    observed: dict[str, object] = {
        "wrap_outcome": wrapped.get("outcome"),
        "wrap_reason": wrapped.get("reason"),
        "host": host,
        "absolute": absolute,
        "next": nxt,
        "fit_outcome": fitted.get("outcome"),
        "wide": wide,
        "fit": fit,
        "pin_outcome": pinned.get("outcome"),
        "pin_host": pin_host,
        "pin": pin,
        "block_outcome": blocked.get("outcome"),
        "block_reason": blocked.get("reason"),
    }
    checks = {
        "wrap_placed": wrapped.get("outcome") == "placed",
        "host_keeps_flow": _near(host, x=0, y=0, content_width=50, content_height=20),
        "host_first": _near(_line(host, 0), text="AAAA", x=8, y=0, height=10, content_width=40),
        "host_second": _near(_line(host, 1), text="CC", x=8, y=10, height=10, content_width=20),
        "wrapped_abs": _near(absolute, x=8, y=10, content_width=20, content_height=10),
        "wrapped_text": _near(_line(absolute, 0), text="BB", x=8, y=10, height=10, content_width=20),
        "next_stays": _near(nxt, x=0, y=20, content_height=10),
        "fit_placed": fitted.get("outcome") == "placed",
        "wide_one_line": _near(wide, content_width=200, content_height=10),
        "wide_text": _near(_line(wide, 0), text="AA CD", x=8, y=0, height=10, content_width=50),
        "fit_abs": _near(fit, x=38, y=0, content_width=10, content_height=10),
        "fit_text": _near(_line(fit, 0), text="B", x=38, y=0, height=10, content_width=10),
        "pin_placed": pinned.get("outcome") == "placed",
        "pin_host_flow": _near(_line(pin_host, 0), text="AAAA", x=8, y=0),
        "pin_ignores_slot": _near(pin, x=0, y=0, content_width=20, content_height=10),
        "block_rejected": blocked.get("outcome") == "invalid"
        and blocked.get("reason") == "static position inside a line is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": bool(passed), "observed": observed}))


if __name__ == "__main__":
    main()
