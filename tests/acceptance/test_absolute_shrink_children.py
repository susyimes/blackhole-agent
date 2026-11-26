"""Shrink an absolute box to the margin boxes of its block children.

An automatic width with one automatic horizontal inset uses CSS 2.1
shrink-to-fit. Hello at 10px is narrower than the 200px containing block, so
the absolute content width is 50 and the following block stays at y 0. A
10px child margin-left grows that width to 60 and stays inside. A specified
80px child and an unbreakable 240px child size the absolute to 80 and 240.
A wrapping run whose max-content exceeds 200px uses the available 200px.
Both horizontal insets set still stretch. A plain percentage width is cyclic:
the absolute sizes as if it were auto, then the child uses that percentage of
the definite shrink width. A percentage min-width, calc(), a float child, and
a vertical writing mode stay rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects the shrink-to-fit box exits 0
with passed false.
"""

from __future__ import annotations

import json
import sys

_PAGE = '<div id="page"><div id="abs"><div id="copy">{text}</div></div><div id="next">Z</div></div>'
_BASE = """
#page { position: relative; font-size: 10px; line-height: 10px; }
#next, #copy { font-size: 10px; line-height: 10px; }
"""
_HELLO = _BASE + "#abs { position: absolute; top: 0px; }\n"
_MARGIN = _HELLO + "#copy { margin-left: 10px; margin-top: 8px; margin-bottom: 4px; }\n"
_SPECIFIED = _BASE + "#abs { position: absolute; top: 0px; }\n#copy { width: 80px; }\n"
_WIDE = _BASE + "#abs { position: absolute; top: 0px; }\n#copy { width: 240px; }\n"
_WRAP = _BASE + "#abs { position: absolute; top: 0px; }\n"
_LEFT = _BASE + "#abs { position: absolute; left: 30px; top: 0px; }\n#copy { width: 40px; }\n"
_STRETCH = _BASE + "#abs { position: absolute; left: 10px; right: 10px; top: 0px; }\n"
_PERCENT = _BASE + "#abs { position: absolute; top: 0px; }\n#copy { width: 50%; }\n"
_DOUBLE = _BASE + "#abs { position: absolute; top: 0px; }\n#copy { width: 200%; }\n"
_MARGIN_PERCENT = _PERCENT + "#copy { margin-left: 10px; }\n"
_LIMIT = _BASE + "#abs { position: absolute; top: 0px; }\n#copy { min-width: 50%; }\n"
_CALC = _BASE + "#abs { position: absolute; top: 0px; }\n#copy { width: calc(50%); }\n"
_FLOAT = """
#page { position: relative; }
#flo { float: left; width: 10px; height: 10px; }
#abs { position: absolute; top: 0px; }
"""
_VERTICAL = _BASE + "#abs { position: absolute; writing-mode: vertical-rl; left: 0px; top: 0px; }\n"
_WORDS = "AA BB CC DD EE FF GG HH II JJ"


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


def _lay(layout, text: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_PAGE.format(text=text), stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _line_text(result: dict[str, object], ident: str) -> list[object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None or not isinstance(box.get("lines"), list):
        return None
    return [item.get("text") for item in box["lines"] if isinstance(item, dict)]


def _ink(result: dict[str, object], ident: str) -> object:
    box = _box(result.get("boxes"), ident)
    lines = None if box is None else box.get("lines")
    if not isinstance(lines, list) or not lines or not isinstance(lines[0], dict):
        return None
    return lines[0].get("content_width")


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    lines = box.get("lines")
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "line_count": len(lines) if isinstance(lines, list) else None,
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    hello = _lay(layout_normal_flow, "Hello", _HELLO)
    margin = _lay(layout_normal_flow, "Hello", _MARGIN)
    specified = _lay(layout_normal_flow, "Hello", _SPECIFIED)
    wide = _lay(layout_normal_flow, "Hello", _WIDE)
    wrapped = _lay(layout_normal_flow, _WORDS, _WRAP)
    left = _lay(layout_normal_flow, "Hello", _LEFT)
    stretch = _lay(layout_normal_flow, "Hello", _STRETCH)
    percent = _lay(layout_normal_flow, "Hello", _PERCENT)
    pair = _lay(layout_normal_flow, "AA BB", _PERCENT)
    half_long = _lay(layout_normal_flow, _WORDS, _PERCENT)
    double = _lay(layout_normal_flow, "Hello", _DOUBLE)
    margin_percent = _lay(layout_normal_flow, "Hello", _MARGIN_PERCENT)
    limit = _lay(layout_normal_flow, "Hello", _LIMIT)
    calculated = _lay(layout_normal_flow, "Hello", _CALC)
    floated = layout_normal_flow(
        '<div id="page"><div id="abs"><div id="flo">Hi</div></div><div id="next">Z</div></div>',
        _FLOAT,
        viewport_width=200,
    )
    vertical = _lay(layout_normal_flow, "Hello", _VERTICAL)
    if not isinstance(floated, dict):
        floated = {"outcome": "error", "reason": "layout is invalid", "boxes": None}

    observed: dict[str, object] = {
        "hello": {"outcome": hello.get("outcome"), "reason": hello.get("reason"), "abs": _view(hello, "abs"), "copy": _view(hello, "copy"), "next_y": None if _box(hello.get("boxes"), "next") is None else _box(hello.get("boxes"), "next").get("y"), "page_h": None if _box(hello.get("boxes"), "page") is None else _box(hello.get("boxes"), "page").get("content_height")},
        "margin": {"outcome": margin.get("outcome"), "reason": margin.get("reason"), "abs": _view(margin, "abs"), "copy": _view(margin, "copy")},
        "specified": {"outcome": specified.get("outcome"), "reason": specified.get("reason"), "abs": _view(specified, "abs"), "copy": _view(specified, "copy")},
        "wide": {"outcome": wide.get("outcome"), "reason": wide.get("reason"), "abs": _view(wide, "abs"), "copy": _view(wide, "copy")},
        "wrap": {"outcome": wrapped.get("outcome"), "reason": wrapped.get("reason"), "abs": _view(wrapped, "abs"), "copy": _view(wrapped, "copy")},
        "left": {"outcome": left.get("outcome"), "reason": left.get("reason"), "abs": _view(left, "abs"), "copy": _view(left, "copy")},
        "stretch": {"outcome": stretch.get("outcome"), "reason": stretch.get("reason"), "abs": _view(stretch, "abs"), "copy": _view(stretch, "copy")},
        "percent": {"outcome": percent.get("outcome"), "reason": percent.get("reason"), "abs": _view(percent, "abs"), "copy": _view(percent, "copy"), "lines": _line_text(percent, "copy"), "ink": _ink(percent, "copy")},
        "pair": {"outcome": pair.get("outcome"), "reason": pair.get("reason"), "abs": _view(pair, "abs"), "copy": _view(pair, "copy"), "lines": _line_text(pair, "copy")},
        "half_long": {"outcome": half_long.get("outcome"), "reason": half_long.get("reason"), "abs": _view(half_long, "abs"), "copy": _view(half_long, "copy"), "lines": _line_text(half_long, "copy")},
        "double": {"outcome": double.get("outcome"), "reason": double.get("reason"), "abs": _view(double, "abs"), "copy": _view(double, "copy")},
        "margin_percent": {"outcome": margin_percent.get("outcome"), "reason": margin_percent.get("reason"), "abs": _view(margin_percent, "abs"), "copy": _view(margin_percent, "copy")},
        "limit": {"outcome": limit.get("outcome"), "reason": limit.get("reason")},
        "calc": {"outcome": calculated.get("outcome"), "reason": calculated.get("reason")},
        "float": {"outcome": floated.get("outcome"), "reason": floated.get("reason")},
        "vertical": {"outcome": vertical.get("outcome"), "reason": vertical.get("reason")},
    }
    checks = {
        "hello_shrinks_to_max_content_and_the_flow_stays": (
            hello.get("outcome") == "placed"
            and _near(_box(hello.get("boxes"), "abs"), x=0, y=0, content_width=50, content_height=10)
            and _near(_box(hello.get("boxes"), "copy"), x=0, y=0, content_width=50, content_height=10)
            and _near(_box(hello.get("boxes"), "next"), y=0)
            and _near(_box(hello.get("boxes"), "page"), content_height=10)
        ),
        "child_margin_stays_inside_the_shrink_box": (
            margin.get("outcome") == "placed"
            and _near(_box(margin.get("boxes"), "abs"), x=0, y=0, content_width=60, content_height=22)
            and _near(_box(margin.get("boxes"), "copy"), x=10, y=8, content_width=50, content_height=10)
        ),
        "specified_child_width_sizes_the_absolute": (
            specified.get("outcome") == "placed"
            and _near(_box(specified.get("boxes"), "abs"), content_width=80, content_height=10)
            and _near(_box(specified.get("boxes"), "copy"), content_width=80, content_height=10)
        ),
        "min_content_wider_than_the_containing_block_overflows": (
            wide.get("outcome") == "placed"
            and _near(_box(wide.get("boxes"), "abs"), content_width=240)
            and _near(_box(wide.get("boxes"), "copy"), content_width=240)
        ),
        "max_content_wider_than_available_uses_the_available_width": (
            wrapped.get("outcome") == "placed"
            and _near(_box(wrapped.get("boxes"), "abs"), x=0, content_width=200)
            and _near(_box(wrapped.get("boxes"), "copy"), content_width=200)
            and isinstance((_box(wrapped.get("boxes"), "copy") or {}).get("lines"), list)
            and len(_box(wrapped.get("boxes"), "copy")["lines"]) > 1
        ),
        "a_left_inset_keeps_the_shrink_width": (
            left.get("outcome") == "placed"
            and _near(_box(left.get("boxes"), "abs"), x=30, content_width=40)
            and _near(_box(left.get("boxes"), "copy"), x=30, content_width=40)
        ),
        "both_insets_still_stretch": (
            stretch.get("outcome") == "placed"
            and _near(_box(stretch.get("boxes"), "abs"), x=10, content_width=180)
            and _near(_box(stretch.get("boxes"), "copy"), content_width=180)
        ),
        "cyclic_half_width_sizes_from_max_content_then_uses_half": (
            percent.get("outcome") == "placed"
            and _near(_box(percent.get("boxes"), "abs"), x=0, y=0, content_width=50, content_height=10)
            and _near(_box(percent.get("boxes"), "copy"), x=0, y=0, content_width=25, content_height=10)
            and _line_text(percent, "copy") == ["Hello"]
            and _ink(percent, "copy") == 50
            and _near(_box(percent.get("boxes"), "next"), y=0)
            and _near(_box(percent.get("boxes"), "page"), content_height=10)
        ),
        "half_width_wraps_the_line_that_sized_the_absolute": (
            pair.get("outcome") == "placed"
            and _near(_box(pair.get("boxes"), "abs"), content_width=50, content_height=20)
            and _near(_box(pair.get("boxes"), "copy"), content_width=25, content_height=20)
            and _line_text(pair, "copy") == ["AA", "BB"]
        ),
        "available_clamp_then_half_the_shrink_width": (
            half_long.get("outcome") == "placed"
            and _near(_box(half_long.get("boxes"), "abs"), content_width=200, content_height=40)
            and _near(_box(half_long.get("boxes"), "copy"), content_width=100, content_height=40)
            and _line_text(half_long, "copy") == ["AA BB CC", "DD EE FF", "GG HH II", "JJ"]
        ),
        "double_percentage_overflows_the_shrink_box": (
            double.get("outcome") == "placed"
            and _near(_box(double.get("boxes"), "abs"), content_width=50, content_height=10)
            and _near(_box(double.get("boxes"), "copy"), content_width=100, content_height=10)
        ),
        "margin_stays_outside_the_cyclic_percentage": (
            margin_percent.get("outcome") == "placed"
            and _near(_box(margin_percent.get("boxes"), "abs"), content_width=60, content_height=10)
            and _near(_box(margin_percent.get("boxes"), "copy"), x=10, content_width=30, content_height=10)
        ),
        "percentage_min_width_stays_rejected": (
            limit.get("outcome") == "invalid"
            and limit.get("reason") == "absolute shrink-to-fit is unsupported"
        ),
        "calc_percentage_stays_rejected": (
            calculated.get("outcome") == "invalid"
            and calculated.get("reason") == "absolute shrink-to-fit is unsupported"
        ),
        "float_child_stays_rejected": (
            floated.get("outcome") == "invalid"
            and floated.get("reason") == "positioned content is unsupported"
        ),
        "vertical_shrink_stays_rejected": (
            vertical.get("outcome") == "invalid"
            and vertical.get("reason") == "positioned content is unsupported"
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
