"""Place words that precede a left float inside an inline-block.

In a 200px viewport at 10px, A, the atomic box, and C share one line. Words
WW before a 20 by 10 left float shrink that box to 20 by 20: WW is at x 10
y 0, the float is at x 10 y 10, A and C stay on the earlier line, and the
next block starts at y 20. WW before that float and QQ after it widen the
box to 40: WW stays at y 0, QQ is at x 30 y 10, and A and C align to y 10.
A 40px box wraps QQ QQ beside a 10px-tall float, then lets the second QQ
return to x 10 once the float ends, while WW remains at x 10 y 0.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the earlier words exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = (
    '<div id="page"><div id="row">A<span id="atom">{body}</span>C</div>'
    '<div id="next">Z</div></div>'
)
_BASE = """
#page { font-size: 10px; line-height: 10px; }
#row { font-size: 10px; line-height: 10px; }
#next { font-size: 10px; line-height: 10px; }
#atom { display: inline-block; font-size: 10px; line-height: 10px; }
#fl { float: left; width: 20px; height: 10px; font-size: 10px; line-height: 10px; }
"""
_WIDE = _BASE + "#atom { width: 40px; }\n"


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _anon(boxes: object, text: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if not isinstance(item, dict) or not str(item.get("id") or "").startswith("anon-"):
            continue
        lines = item.get("lines")
        if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
            continue
        if lines[0].get("text") == text:
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


def _lay(layout, body: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE.format(body=body), stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _spot(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "w": box.get("content_width"),
        "h": box.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    above = _lay(layout_normal_flow, 'WW<span id="fl">F</span>', _BASE)
    beside = _lay(layout_normal_flow, 'WW<span id="fl">F</span>QQ', _BASE)
    release = _lay(layout_normal_flow, 'WW<span id="fl">F</span>QQ QQ', _WIDE)
    above_boxes = above.get("boxes")
    beside_boxes = beside.get("boxes")
    release_boxes = release.get("boxes")
    above_row = _box(above_boxes, "row")
    beside_row = _box(beside_boxes, "row")
    release_row = _box(release_boxes, "row")
    above_words = _anon(above_boxes, "WW")
    beside_words = _anon(beside_boxes, "WW")
    beside_after = _anon(beside_boxes, "QQ")
    release_words = _anon(release_boxes, "WW")
    release_after = _anon(release_boxes, "QQ")

    checks = {
        "earlier_words_keep_the_full_line_above_the_float": (
            above.get("outcome") == "placed"
            and _near(above_row, content_width=200, content_height=20)
            and _near(
                _line(above_row, 0),
                text="AC",
                x=0,
                y=0,
                height=20,
                content_width=40,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10},
                    {"text": "C", "x": 30, "font_size": 10, "width": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 20}],
            )
            and _near(_box(above_boxes, "atom"), x=10, y=0, content_width=20, content_height=20)
            and _near(_box(above_boxes, "fl"), x=10, y=10, content_width=20, content_height=10)
            and _near(above_words, x=10, y=0, content_width=20, content_height=10)
            and _near(_line(above_words, 0), text="WW", x=10, y=0, height=10, content_width=20)
            and _near(_box(above_boxes, "next"), x=0, y=20, content_height=10)
        ),
        "later_word_shortens_beside_the_float": (
            beside.get("outcome") == "placed"
            and _near(beside_row, content_height=20)
            and _near(
                _line(beside_row, 0),
                text="AC",
                height=20,
                content_width=60,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 10},
                    {"text": "C", "x": 50, "font_size": 10, "width": 10, "y": 10},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 40}],
            )
            and _near(_box(beside_boxes, "atom"), x=10, y=0, content_width=40, content_height=20)
            and _near(_box(beside_boxes, "fl"), x=10, y=10, content_width=20, content_height=10)
            and _near(beside_words, content_width=40, content_height=10)
            and _near(_line(beside_words, 0), text="WW", x=10, y=0, height=10, content_width=20)
            and _near(_line(beside_after, 0), text="QQ", x=30, y=10, height=10, content_width=20)
            and _near(_box(beside_boxes, "next"), y=20)
        ),
        "second_later_word_returns_to_the_full_width": (
            release.get("outcome") == "placed"
            and _near(release_row, content_height=30)
            and _near(
                _line(release_row, 0),
                text="AC",
                height=30,
                content_width=60,
                runs=[
                    {"text": "A", "x": 0, "font_size": 10, "width": 10, "y": 20},
                    {"text": "C", "x": 50, "font_size": 10, "width": 10, "y": 20},
                ],
                atoms=[{"id": "atom", "x": 10, "width": 40}],
            )
            and _near(_box(release_boxes, "atom"), x=10, y=0, content_width=40, content_height=30)
            and _near(_box(release_boxes, "fl"), x=10, y=10, content_width=20, content_height=10)
            and _near(_line(release_words, 0), text="WW", x=10, y=0, height=10, content_width=20)
            and _near(_line(release_after, 0), text="QQ", x=30, y=10, height=10, content_width=20)
            and _near(_line(release_after, 1), text="QQ", x=10, y=20, height=10, content_width=20)
            and _near(_box(release_boxes, "next"), y=30)
        ),
    }
    observed = {
        "above": {
            "outcome": above.get("outcome"),
            "reason": above.get("reason"),
            "atom": _spot(_box(above_boxes, "atom")),
            "float": _spot(_box(above_boxes, "fl")),
            "word_x": None if _line(above_words, 0) is None else _line(above_words, 0).get("x"),
            "next_y": None if _box(above_boxes, "next") is None else _box(above_boxes, "next").get("y"),
        },
        "beside": {
            "outcome": beside.get("outcome"),
            "reason": beside.get("reason"),
            "atom": _spot(_box(beside_boxes, "atom")),
            "later_x": None if _line(beside_after, 0) is None else _line(beside_after, 0).get("x"),
            "c_y": None
            if _line(beside_row, 0) is None or not isinstance(_line(beside_row, 0).get("runs"), list)
            else _line(beside_row, 0)["runs"][1].get("y"),
        },
        "release": {
            "outcome": release.get("outcome"),
            "reason": release.get("reason"),
            "first_x": None if _line(release_after, 0) is None else _line(release_after, 0).get("x"),
            "second_x": None if _line(release_after, 1) is None else _line(release_after, 1).get("x"),
            "word_x": None if _line(release_words, 0) is None else _line(release_words, 0).get("x"),
            "next_y": None if _box(release_boxes, "next") is None else _box(release_boxes, "next").get("y"),
        },
        "checks": checks,
    }
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
