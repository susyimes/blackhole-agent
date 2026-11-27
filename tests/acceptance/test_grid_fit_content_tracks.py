"""Clamp a grid column with fit-content() and move the next column.

A short item stays at its max-content, so it is narrower than a fixed track
of the same argument. A longer wrapping item stops at the argument and the
following block starts under the extra lines. An unbreakable word keeps its
min-content width when that word is longer than the argument. The argument
is not a stretch target. A row, a percentage, a flexible argument, a negative
length, and the bare keyword are rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still rejects fit-content() exits 0 with
passed false.
"""

from __future__ import annotations

import json
import sys

_PAIR = (
    '<div id="page"><div id="grid"><div id="a">{text}</div><div id="b">B</div></div>'
    "<p id=\"next\">Z</p></div>"
)
_ONE = '<div id="page"><div id="grid"><div id="a">{text}</div></div><p id="next">Z</p></div>'
_FONT = "#page { font-size: 10px; line-height: 10px; }\n"


def _columns(width: int, tracks: str, extra: str = "") -> str:
    return (
        _FONT
        + f"#grid {{ display: grid; width: {width}px; grid-template-columns: {tracks}; "
        + extra
        + "}\n"
    )


_SHORT = _columns(200, "fit-content(40px) 1fr")
_WRAP = _columns(200, "fit-content(40px) 1fr")
_WORD = _columns(200, "fit-content(40px) 1fr")
_CAP = _columns(200, "fit-content(100px)")
_GAP = _columns(200, "fit-content(40px) 1fr", "column-gap: 10px; ")
_ZERO = _columns(200, "fit-content(0px) 1fr")
_NAMED = _columns(200, "[start] fit-content(40px) [end] 1fr") + "#a { grid-column: start / end; }\n"
_MAX = _columns(200, "max-content 1fr")
_FIXED = _columns(200, "40px 1fr")
_ROW = (
    _FONT
    + "#grid { display: grid; width: 80px; grid-template-columns: 40px; "
    + "grid-template-rows: fit-content(20px); }\n"
)
_FLEX_ARG = _columns(200, "fit-content(1fr) 1fr")
_PERCENT = _columns(200, "fit-content(10%) 1fr")
_NEGATIVE = _columns(200, "fit-content(-4px) 1fr")
_BARE = _columns(200, "fit-content 1fr")


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


def _lines(box: dict[str, object] | None) -> list[str]:
    if box is None or not isinstance(box.get("lines"), list):
        return []
    return [str(line.get("text")) for line in box["lines"] if isinstance(line, dict)]


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "lines": _lines(box),
    }


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _rejected(result: dict[str, object]) -> bool:
    return result.get("outcome") == "invalid" and bool(result.get("reason"))


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    short = _lay(layout_normal_flow, _PAIR.format(text="AA"), _SHORT)
    wrap = _lay(layout_normal_flow, _PAIR.format(text="AA AA AA"), _WRAP)
    word = _lay(layout_normal_flow, _PAIR.format(text="AAAAA"), _WORD)
    cap = _lay(layout_normal_flow, _ONE.format(text="AA AA"), _CAP)
    gap = _lay(layout_normal_flow, _PAIR.format(text="AA"), _GAP)
    zero = _lay(layout_normal_flow, _PAIR.format(text="AA AA"), _ZERO)
    named = _lay(layout_normal_flow, _PAIR.format(text="AA AA AA"), _NAMED)
    packed = _lay(layout_normal_flow, _PAIR.format(text="AA AA AA"), _MAX)
    fixed = _lay(layout_normal_flow, _PAIR.format(text="AA"), _FIXED)
    row = _lay(layout_normal_flow, _ONE.format(text="AA"), _ROW)
    flex_arg = _lay(layout_normal_flow, _PAIR.format(text="AA"), _FLEX_ARG)
    percent = _lay(layout_normal_flow, _PAIR.format(text="AA"), _PERCENT)
    negative = _lay(layout_normal_flow, _PAIR.format(text="AA"), _NEGATIVE)
    bare = _lay(layout_normal_flow, _PAIR.format(text="AA"), _BARE)
    observed: dict[str, object] = {
        "short_outcome": short.get("outcome"),
        "short_reason": short.get("reason"),
        "short_a": _view(short, "a"),
        "short_b": _view(short, "b"),
        "short_next_y": None if _box(short.get("boxes"), "next") is None else _box(short.get("boxes"), "next").get("y"),
        "wrap_outcome": wrap.get("outcome"),
        "wrap_a": _view(wrap, "a"),
        "wrap_b": _view(wrap, "b"),
        "wrap_next_y": None if _box(wrap.get("boxes"), "next") is None else _box(wrap.get("boxes"), "next").get("y"),
        "word_outcome": word.get("outcome"),
        "word_a": _view(word, "a"),
        "word_b": _view(word, "b"),
        "word_next_y": None if _box(word.get("boxes"), "next") is None else _box(word.get("boxes"), "next").get("y"),
        "cap_outcome": cap.get("outcome"),
        "cap_a": _view(cap, "a"),
        "cap_next_y": None if _box(cap.get("boxes"), "next") is None else _box(cap.get("boxes"), "next").get("y"),
        "gap_outcome": gap.get("outcome"),
        "gap_a": _view(gap, "a"),
        "gap_b": _view(gap, "b"),
        "zero_outcome": zero.get("outcome"),
        "zero_a": _view(zero, "a"),
        "zero_b": _view(zero, "b"),
        "zero_next_y": None if _box(zero.get("boxes"), "next") is None else _box(zero.get("boxes"), "next").get("y"),
        "named_outcome": named.get("outcome"),
        "named_reason": named.get("reason"),
        "named_a": _view(named, "a"),
        "named_b": _view(named, "b"),
        "max_outcome": packed.get("outcome"),
        "max_a": _view(packed, "a"),
        "max_b": _view(packed, "b"),
        "max_next_y": None if _box(packed.get("boxes"), "next") is None else _box(packed.get("boxes"), "next").get("y"),
        "fixed_a": _view(fixed, "a"),
        "fixed_b": _view(fixed, "b"),
        "row_outcome": row.get("outcome"),
        "row_reason": row.get("reason"),
        "flex_arg_outcome": flex_arg.get("outcome"),
        "percent_outcome": percent.get("outcome"),
        "negative_outcome": negative.get("outcome"),
        "bare_outcome": bare.get("outcome"),
        "bare_reason": bare.get("reason"),
    }
    short_next = _box(short.get("boxes"), "next")
    wrap_next = _box(wrap.get("boxes"), "next")
    word_next = _box(word.get("boxes"), "next")
    cap_next = _box(cap.get("boxes"), "next")
    zero_next = _box(zero.get("boxes"), "next")
    packed_next = _box(packed.get("boxes"), "next")
    checks = {
        "short_item_stays_at_max_content": (
            short.get("outcome") == "placed"
            and _near(_box(short.get("boxes"), "a"), x=0, y=0, content_width=20, content_height=10)
            and _near(_box(short.get("boxes"), "b"), x=20, y=0, content_width=180, content_height=10)
            and short_next is not None
            and short_next.get("y") == 10
        ),
        "wrapping_item_stops_at_the_argument": (
            wrap.get("outcome") == "placed"
            and _near(_box(wrap.get("boxes"), "a"), x=0, y=0, content_width=40, content_height=30)
            and _lines(_box(wrap.get("boxes"), "a")) == ["AA", "AA", "AA"]
            and _near(_box(wrap.get("boxes"), "b"), x=40, y=0, content_width=160, content_height=30)
            and wrap_next is not None
            and wrap_next.get("y") == 30
        ),
        "unbreakable_word_keeps_min_content": (
            word.get("outcome") == "placed"
            and _near(_box(word.get("boxes"), "a"), x=0, content_width=50, content_height=10)
            and _lines(_box(word.get("boxes"), "a")) == ["AAAAA"]
            and _near(_box(word.get("boxes"), "b"), x=50, content_width=150)
            and word_next is not None
            and word_next.get("y") == 10
        ),
        "argument_above_max_content_does_not_stretch": (
            cap.get("outcome") == "placed"
            and _near(_box(cap.get("boxes"), "a"), x=0, content_width=50, content_height=10)
            and _lines(_box(cap.get("boxes"), "a")) == ["AA AA"]
            and cap_next is not None
            and cap_next.get("y") == 10
        ),
        "gap_sits_outside_the_capped_column": (
            gap.get("outcome") == "placed"
            and _near(_box(gap.get("boxes"), "a"), x=0, content_width=20)
            and _near(_box(gap.get("boxes"), "b"), x=30, content_width=170)
        ),
        "cap_below_the_word_keeps_min_content": (
            zero.get("outcome") == "placed"
            and _near(_box(zero.get("boxes"), "a"), x=0, content_width=20, content_height=20)
            and _lines(_box(zero.get("boxes"), "a")) == ["AA", "AA"]
            and _near(_box(zero.get("boxes"), "b"), x=20, content_width=180)
            and zero_next is not None
            and zero_next.get("y") == 20
        ),
        "named_line_selects_the_fit_content_column": (
            named.get("outcome") == "placed"
            and _near(_box(named.get("boxes"), "a"), x=0, content_width=40, content_height=30)
            and _near(_box(named.get("boxes"), "b"), x=40, content_width=160)
        ),
        "max_content_keeps_the_unwrapped_line": (
            packed.get("outcome") == "placed"
            and _near(_box(packed.get("boxes"), "a"), x=0, content_width=80, content_height=10)
            and _lines(_box(packed.get("boxes"), "a")) == ["AA AA AA"]
            and _near(_box(packed.get("boxes"), "b"), x=80, content_width=120)
            and packed_next is not None
            and packed_next.get("y") == 10
        ),
        "fixed_column_does_not_shrink_to_the_text": (
            fixed.get("outcome") == "placed"
            and _near(_box(fixed.get("boxes"), "a"), content_width=40)
            and _near(_box(fixed.get("boxes"), "b"), x=40, content_width=160)
        ),
        "fit_content_row_is_rejected": _rejected(row),
        "flexible_argument_is_rejected": _rejected(flex_arg),
        "percentage_argument_is_rejected": _rejected(percent),
        "negative_argument_is_rejected": _rejected(negative),
        "bare_keyword_is_rejected": _rejected(bare),
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
