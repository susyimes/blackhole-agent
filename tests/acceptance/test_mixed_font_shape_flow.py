"""Place mixed-size inline runs beside a shape-outside float.

In a marginless 200px block, a 100px left circle leaves AA at 20px and Z at
10px on one 20px line at x 90. The same letters beside the margin box start
at x 100. An unbreakable 120px mixed word fits that strut chord and does not
fit the taller chord, so it starts at x 80, y 90. A vertical-rl block stays
unplaced.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_BASE = "html, body, div, p, i, b { margin: 0px; }\n"
_PAGE = "#page { width: 200px; font-size: 10px; line-height: 10px; }\n#next { height: 10px; }\n"
_BIG = "#big { font-size: 20px; line-height: 20px; }\n"
_CIRCLE = (
    _PAGE
    + "#pin { float: left; width: 100px; height: 100px; "
    + "shape-outside: circle(50px at 50px 50px); }\n"
    + _BIG
)
_RECT = _PAGE + "#pin { float: left; width: 100px; height: 100px; }\n" + _BIG
_VERTICAL = (
    "#page { width: 200px; writing-mode: vertical-rl; font-size: 10px; line-height: 10px; }\n"
    "#pin { float: left; width: 100px; height: 100px; "
    "shape-outside: circle(50px at 50px 50px); }\n"
    + _BIG
)
_SHORT = '<div id="page"><p id="mix"><i id="pin">F</i><b id="big">AA</b> Z</p><p id="next">Q</p></div>'
_LONG = '<div id="page"><p id="mix"><i id="pin">F</i><b id="big">A</b>XXXXXXXXXX</p><p id="next">Q</p></div>'
_SHORT_RUNS = [
    {"text": "AA", "x": 90, "font_size": 20, "width": 40},
    {"text": " Z", "x": 130, "font_size": 10, "width": 20},
]
_RECT_RUNS = [
    {"text": "AA", "x": 100, "font_size": 20, "width": 40},
    {"text": " Z", "x": 140, "font_size": 10, "width": 20},
]
_LONG_RUNS = [
    {"text": "A", "x": 80, "font_size": 20, "width": 20},
    {"text": "XXXXXXXXXX", "x": 100, "font_size": 10, "width": 100},
]


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    return line if isinstance(line, dict) else None


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, stylesheet: str, markup: str) -> dict[str, object]:
    try:
        placed = layout(markup, _BASE + stylesheet, viewport_width=400)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _facts(result: dict[str, object], ident: str) -> dict[str, object]:
    box = _box(result.get("boxes"), ident)
    line = _line(box)
    return {
        "outcome": result.get("outcome"),
        "reason": result.get("reason"),
        "x": None if box is None else box.get("x"),
        "y": None if box is None else box.get("y"),
        "content_width": None if box is None else box.get("content_width"),
        "content_height": None if box is None else box.get("content_height"),
        "line": None
        if line is None
        else {
            "text": line.get("text"),
            "x": line.get("x"),
            "y": line.get("y"),
            "height": line.get("height"),
            "content_width": line.get("content_width"),
            "runs": line.get("runs"),
        },
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    chord = _lay(layout_normal_flow, _CIRCLE, _SHORT)
    dropped = _lay(layout_normal_flow, _CIRCLE, _LONG)
    rectangular = _lay(layout_normal_flow, _RECT, _SHORT)
    vertical = _lay(layout_normal_flow, _VERTICAL, _SHORT)
    chord_line = _line(_box(chord.get("boxes"), "mix"))
    dropped_line = _line(_box(dropped.get("boxes"), "mix"))
    rectangular_line = _line(_box(rectangular.get("boxes"), "mix"))
    observed = {
        "chord": _facts(chord, "mix"),
        "pin": _facts(chord, "pin"),
        "next": _facts(chord, "next"),
        "dropped": _facts(dropped, "mix"),
        "dropped_next": _facts(dropped, "next"),
        "rectangular": _facts(rectangular, "mix"),
        "vertical_reason": vertical.get("reason"),
    }
    checks = {
        "chord_line": (
            chord.get("outcome") == "placed"
            and _near(_box(chord.get("boxes"), "pin"), x=0, y=0, content_width=100, content_height=100)
            and _near(_box(chord.get("boxes"), "mix"), content_width=200, content_height=100)
            and _near(
                chord_line,
                text="AA Z",
                x=90,
                y=0,
                height=20,
                content_width=60,
                runs=_SHORT_RUNS,
            )
            and _near(_box(chord.get("boxes"), "next"), x=0, y=100, content_height=10)
        ),
        "taller_chord_drops": (
            dropped.get("outcome") == "placed"
            and _near(_box(dropped.get("boxes"), "mix"), content_width=200, content_height=110)
            and _near(
                dropped_line,
                text="AXXXXXXXXXX",
                x=80,
                y=90,
                height=20,
                content_width=120,
                runs=_LONG_RUNS,
            )
            and _near(_box(dropped.get("boxes"), "next"), y=110, content_height=10)
        ),
        "margin_box_stays_closed": (
            rectangular.get("outcome") == "placed"
            and _near(
                rectangular_line,
                text="AA Z",
                x=100,
                y=0,
                height=20,
                content_width=60,
                runs=_RECT_RUNS,
            )
        ),
        "vertical_rejected": vertical.get("outcome") == "invalid" and vertical.get("boxes") is None,
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
