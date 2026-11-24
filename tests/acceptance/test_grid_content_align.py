"""Pack grid tracks inside a definite content box.

align-content and justify-content move fixed tracks to the end or the center,
and the space-* keywords enlarge the gutters. A spanned item grows by that
extra gutter. Automatic columns stay at their max-content size when the
keyword is end, and they still stretch when the keyword is omitted. A share
that is not an integer pixel is rejected. The next sibling stays on the
grid's outer edge.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_PAIR = '<div id="page"><div id="grid"><div id="a">AB</div><div id="b">CD</div></div><div id="after"></div></div>'
_ONE = '<div id="page"><div id="grid"><div id="a">AB</div></div><div id="after"></div></div>'


def _rule(extra: str = "", **props: str) -> str:
    body = "; ".join(f"{name.replace('_', '-')}: {value}" for name, value in props.items())
    return _FONT + f"#grid {{ {body}; }}\n" + extra


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


def _line(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None or not isinstance(box.get("lines"), list) or not box["lines"]:
        return None
    line = box["lines"][0]
    if not isinstance(line, dict):
        return None
    return {"text": line.get("text"), "x": line.get("x"), "y": line.get("y")}


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=240)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _view(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
        "line": _line(box),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    rows = dict(display="grid", width="100px", height="80px", grid_template_columns="100px", grid_template_rows="20px 20px")
    end = _lay(layout_normal_flow, _PAIR, _rule(**rows, align_content="end"))
    center = _lay(layout_normal_flow, _PAIR, _rule(**rows, align_content="center"))
    between_rows = _lay(
        layout_normal_flow,
        _PAIR,
        _rule(**rows, row_gap="10px", align_content="space-between"),
    )
    plain = _lay(layout_normal_flow, _PAIR, _rule(**rows))
    columns = dict(display="grid", width="100px", height="20px", grid_template_columns="20px 20px", grid_template_rows="20px")
    end_columns = _lay(layout_normal_flow, _PAIR, _rule(**columns, justify_content="end"))
    flex_end = _lay(layout_normal_flow, _PAIR, _rule(**columns, justify_content="flex-end"))
    around = _lay(layout_normal_flow, _PAIR, _rule(**columns, justify_content="space-around"))
    evenly = _lay(layout_normal_flow, _PAIR, _rule(**columns, justify_content="space-evenly"))
    between_columns = _lay(
        layout_normal_flow,
        _PAIR,
        _rule(**columns, column_gap="10px", justify_content="space-between"),
    )
    auto = dict(display="grid", width="100px", height="20px", grid_template_columns="auto auto", grid_template_rows="20px")
    auto_end = _lay(layout_normal_flow, _PAIR, _rule(**auto, justify_content="end"))
    auto_start = _lay(layout_normal_flow, _PAIR, _rule(**auto, justify_content="flex-start"))
    auto_normal = _lay(layout_normal_flow, _PAIR, _rule(**auto))
    span_between = _lay(
        layout_normal_flow,
        _ONE,
        _rule(
            "#a { grid-column: span 2; }\n",
            display="grid",
            width="80px",
            grid_template_columns="20px 20px",
            grid_template_rows="20px",
            justify_content="space-between",
        ),
    )
    span_start = _lay(
        layout_normal_flow,
        _ONE,
        _rule(
            "#a { grid-column: span 2; }\n",
            display="grid",
            width="80px",
            grid_template_columns="20px 20px",
            grid_template_rows="20px",
            justify_content="start",
        ),
    )
    padded = _lay(
        layout_normal_flow,
        _PAIR,
        _rule(
            display="grid",
            width="40px",
            height="80px",
            padding="10px",
            grid_template_columns="40px",
            grid_template_rows="20px 20px",
            align_content="end",
        ),
    )
    overflow = _lay(
        layout_normal_flow,
        _PAIR,
        _rule(
            display="grid",
            width="40px",
            height="40px",
            grid_template_columns="40px",
            grid_template_rows="30px 30px",
            align_content="space-between",
        ),
    )
    fractional = _lay(
        layout_normal_flow,
        _ONE,
        _rule(
            display="grid",
            width="100px",
            height="80px",
            grid_template_columns="100px",
            grid_template_rows="0.5fr",
            align_content="end",
        ),
    )
    odd = _lay(
        layout_normal_flow,
        _PAIR,
        _rule(
            display="grid",
            width="101px",
            height="20px",
            grid_template_columns="20px 20px",
            grid_template_rows="20px",
            justify_content="space-evenly",
        ),
    )
    observed: dict[str, object] = {
        "end": _view(end, "a"),
        "end_b": _view(end, "b"),
        "end_after": _view(end, "after"),
        "end_outcome": end.get("outcome"),
        "end_reason": end.get("reason"),
        "center_a": _view(center, "a"),
        "center_b": _view(center, "b"),
        "between_rows_a": _view(between_rows, "a"),
        "between_rows_b": _view(between_rows, "b"),
        "plain_a": _view(plain, "a"),
        "plain_b": _view(plain, "b"),
        "end_columns_a": _view(end_columns, "a"),
        "end_columns_b": _view(end_columns, "b"),
        "auto_end_a": _view(auto_end, "a"),
        "auto_end_b": _view(auto_end, "b"),
        "span_between": _view(span_between, "a"),
        "span_start": _view(span_start, "a"),
        "padded_a": _view(padded, "a"),
        "padded_b": _view(padded, "b"),
        "padded_after": _view(padded, "after"),
        "overflow_a": _view(overflow, "a"),
        "overflow_b": _view(overflow, "b"),
        "overflow_after": _view(overflow, "after"),
        "odd_outcome": odd.get("outcome"),
        "odd_reason": odd.get("reason"),
    }
    checks = {
        "end_rows_pack_against_the_content_end": (
            end.get("outcome") == "placed"
            and _near(_box(end.get("boxes"), "grid"), y=0, content_height=80, border_height=80)
            and _near(_box(end.get("boxes"), "a"), x=0, y=40, content_height=20, border_height=20)
            and _near(_line(_box(end.get("boxes"), "a")), text="AB", x=0, y=40)
            and _near(_box(end.get("boxes"), "b"), x=0, y=60, content_height=20, border_height=20)
            and _near(_box(end.get("boxes"), "after"), y=80)
        ),
        "center_rows_share_the_leftover": (
            center.get("outcome") == "placed"
            and _near(_box(center.get("boxes"), "a"), y=20, border_height=20)
            and _near(_box(center.get("boxes"), "b"), y=40, border_height=20)
            and _near(_box(center.get("boxes"), "after"), y=80)
        ),
        "space_between_adds_the_leftover_to_the_row_gap": (
            between_rows.get("outcome") == "placed"
            and _near(_box(between_rows.get("boxes"), "a"), y=0, border_height=20)
            and _near(_box(between_rows.get("boxes"), "b"), y=60, border_height=20)
            and _near(_box(between_rows.get("boxes"), "after"), y=80)
        ),
        "omitted_align_content_stays_at_the_start": (
            plain.get("outcome") == "placed"
            and _near(_box(plain.get("boxes"), "a"), y=0, border_height=20)
            and _near(_box(plain.get("boxes"), "b"), y=20, border_height=20)
            and _near(_box(plain.get("boxes"), "after"), y=80)
        ),
        "end_columns_pack_against_the_content_end": (
            end_columns.get("outcome") == "placed"
            and _near(_box(end_columns.get("boxes"), "a"), x=60, y=0, content_width=20, border_width=20)
            and _near(_line(_box(end_columns.get("boxes"), "a")), text="AB", x=60, y=0)
            and _near(_box(end_columns.get("boxes"), "b"), x=80, y=0, content_width=20, border_width=20)
            and _near(_box(end_columns.get("boxes"), "after"), y=20)
        ),
        "flex_end_is_the_inline_end_edge": (
            flex_end.get("outcome") == "placed"
            and _near(_box(flex_end.get("boxes"), "a"), x=60, border_width=20)
            and _near(_box(flex_end.get("boxes"), "b"), x=80, border_width=20)
        ),
        "auto_columns_at_the_end_do_not_stretch": (
            auto_end.get("outcome") == "placed"
            and _near(_box(auto_end.get("boxes"), "a"), x=60, content_width=20, border_width=20)
            and _near(_box(auto_end.get("boxes"), "b"), x=80, content_width=20, border_width=20)
        ),
        "flex_start_keeps_automatic_columns_at_their_content_size": (
            auto_start.get("outcome") == "placed"
            and _near(_box(auto_start.get("boxes"), "a"), x=0, content_width=20, border_width=20)
            and _near(_box(auto_start.get("boxes"), "b"), x=20, content_width=20, border_width=20)
        ),
        "omitted_justify_content_still_stretches_automatic_columns": (
            auto_normal.get("outcome") == "placed"
            and _near(_box(auto_normal.get("boxes"), "a"), x=0, content_width=50, border_width=50)
            and _near(_box(auto_normal.get("boxes"), "b"), x=50, content_width=50, border_width=50)
        ),
        "space_between_adds_the_leftover_to_the_column_gap": (
            between_columns.get("outcome") == "placed"
            and _near(_box(between_columns.get("boxes"), "a"), x=0, border_width=20)
            and _near(_box(between_columns.get("boxes"), "b"), x=80, border_width=20)
        ),
        "space_around_splits_a_half_gap_at_each_edge": (
            around.get("outcome") == "placed"
            and _near(_box(around.get("boxes"), "a"), x=15, border_width=20)
            and _near(_box(around.get("boxes"), "b"), x=65, border_width=20)
        ),
        "space_evenly_splits_the_leftover_into_equal_gaps": (
            evenly.get("outcome") == "placed"
            and _near(_box(evenly.get("boxes"), "a"), x=20, border_width=20)
            and _near(_box(evenly.get("boxes"), "b"), x=60, border_width=20)
        ),
        "a_spanned_item_grows_by_the_extra_gutter": (
            span_between.get("outcome") == "placed"
            and _near(_box(span_between.get("boxes"), "a"), x=0, content_width=80, border_width=80)
            and span_start.get("outcome") == "placed"
            and _near(_box(span_start.get("boxes"), "a"), x=0, content_width=40, border_width=40)
        ),
        "padding_keeps_the_end_pack_inside_the_content_box": (
            padded.get("outcome") == "placed"
            and _near(_box(padded.get("boxes"), "grid"), content_height=80, border_height=100)
            and _near(_box(padded.get("boxes"), "a"), x=10, y=50, border_height=20)
            and _near(_box(padded.get("boxes"), "b"), x=10, y=70, border_height=20)
            and _near(_box(padded.get("boxes"), "after"), y=100)
        ),
        "space_between_overflow_falls_back_to_the_start": (
            overflow.get("outcome") == "placed"
            and _near(_box(overflow.get("boxes"), "grid"), content_height=40, border_height=40)
            and _near(_box(overflow.get("boxes"), "a"), y=0, border_height=30)
            and _near(_box(overflow.get("boxes"), "b"), y=30, border_height=30)
            and _near(_box(overflow.get("boxes"), "after"), y=40)
        ),
        "end_packs_a_fractional_row_after_track_sizing": (
            fractional.get("outcome") == "placed"
            and _near(_box(fractional.get("boxes"), "grid"), content_height=80, border_height=80)
            and _near(_box(fractional.get("boxes"), "a"), y=40, content_height=40, border_height=40)
            and _near(_box(fractional.get("boxes"), "after"), y=80)
        ),
        "a_non_integral_share_is_rejected": (
            odd.get("outcome") == "invalid"
            and odd.get("boxes") is None
            and "integral" in str(odd.get("reason") or "")
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
