"""Place flex items by main-axis margins and text baselines.

A definite main margin stays outside the flexible length. An auto main
margin absorbs positive free space before justify-content. Baseline
alignment shifts a row so the first text baselines meet, and the automatic
row grows to that line. A column keeps baseline as flex-start and still
inserts a definite main-end margin.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects item margins or baseline exits 0
with passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = "#page { font-size: 10px; line-height: 10px; }\n"
_PAIR = (
    '<div id="page"><div id="row"><span id="a"></span><span id="b"></span></div>'
    '<p id="next">Z</p></div>'
)
_ONE = '<div id="page"><div id="row"><span id="a"></span></div><p id="next">Z</p></div>'
_TEXT = (
    '<div id="page"><div id="row"><span id="a">A</span><span id="b">B</span></div>'
    '<p id="next">Z</p></div>'
)
_GROW = (
    _PAGE
    + "#row { display: flex; width: 100px; }\n"
    + "#a { flex: none; width: 40px; height: 10px; margin-right: 20px; }\n"
    + "#b { flex: 1 1 0px; height: 10px; }\n"
)
_AUTO = (
    _PAGE
    + "#row { display: flex; width: 100px; justify-content: flex-start; }\n"
    + "#a { flex: none; width: 20px; height: 10px; margin-left: auto; }\n"
    + "#b { flex: none; width: 20px; height: 10px; }\n"
)
_CENTER = (
    _PAGE
    + "#row { display: flex; width: 100px; justify-content: flex-end; }\n"
    + "#a { flex: none; width: 20px; height: 10px; margin-left: auto; margin-right: auto; }\n"
)
_BASE = (
    _PAGE
    + "#row { display: flex; width: 100px; align-items: baseline; }\n"
    + "#a { flex: none; width: 20px; height: 40px; font-size: 10px; line-height: 10px; }\n"
    + "#b { flex: none; width: 20px; font-size: 10px; line-height: 30px; }\n"
)
_COLUMN = (
    _PAGE
    + "#row { display: flex; flex-direction: column; width: 40px; }\n"
    + "#a { flex: none; width: 40px; height: 20px; margin-bottom: 15px; }\n"
    + "#b { flex: none; width: 40px; height: 10px; }\n"
)
_COLUMN_BASE = (
    _PAGE
    + "#row { display: flex; flex-direction: column; align-items: baseline; width: 100px; }\n"
    + "#a { flex: none; width: 20px; height: 20px; font-size: 10px; line-height: 10px; }\n"
    + "#b { flex: none; width: 20px; height: 10px; font-size: 10px; line-height: 30px; }\n"
)


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
    }


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "grow": _lay(layout_normal_flow, _PAIR, _GROW),
        "auto": _lay(layout_normal_flow, _PAIR, _AUTO),
        "center": _lay(layout_normal_flow, _ONE, _CENTER),
        "baseline": _lay(layout_normal_flow, _TEXT, _BASE),
        "column": _lay(layout_normal_flow, _PAIR, _COLUMN),
        "column_baseline": _lay(layout_normal_flow, _TEXT, _COLUMN_BASE),
    }

    def take(name: str, ident: str) -> dict[str, object] | None:
        return _box(cases[name].get("boxes"), ident)

    observed: dict[str, object] = {
        name: {
            "outcome": result.get("outcome"),
            "reason": result.get("reason"),
            "a": _placed(take(name, "a")),
            "b": _placed(take(name, "b")),
            "next": _placed(take(name, "next")),
        }
        for name, result in cases.items()
    }
    checks = {
        "margin_reduces_free_space": (
            cases["grow"].get("outcome") == "placed"
            and _near(take("grow", "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take("grow", "b"), x=60, y=0, content_width=40, content_height=10)
            and _near(take("grow", "next"), y=10)
        ),
        "auto_margin_beats_flex_start": (
            cases["auto"].get("outcome") == "placed"
            and _near(take("auto", "a"), x=60, y=0, content_width=20, content_height=10)
            and _near(take("auto", "b"), x=80, y=0, content_width=20, content_height=10)
        ),
        "auto_margins_center_against_flex_end": (
            cases["center"].get("outcome") == "placed"
            and _near(take("center", "a"), x=40, y=0, content_width=20, content_height=10)
            and _near(take("center", "next"), y=10)
        ),
        "baseline_grows_the_row": (
            cases["baseline"].get("outcome") == "placed"
            and _near(take("baseline", "a"), x=0, y=10, content_width=20, content_height=40)
            and _near(take("baseline", "b"), x=20, y=0, content_width=20, content_height=30)
            and _near(take("baseline", "next"), y=50)
        ),
        "column_margin_separates_items": (
            cases["column"].get("outcome") == "placed"
            and _near(take("column", "a"), x=0, y=0, content_width=40, content_height=20)
            and _near(take("column", "b"), x=0, y=35, content_width=40, content_height=10)
            and _near(take("column", "next"), y=45)
        ),
        "column_baseline_stays_at_start": (
            cases["column_baseline"].get("outcome") == "placed"
            and _near(take("column_baseline", "a"), x=0, y=0, content_width=20, content_height=20)
            and _near(take("column_baseline", "b"), x=0, y=20, content_width=20, content_height=10)
            and _near(take("column_baseline", "next"), y=30)
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
