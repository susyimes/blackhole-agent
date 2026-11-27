"""Size flexible rows when a grid's block size is indefinite.

CSS Grid sizes an fr row from the max-content flex fraction when the grid
height is automatic. The rows keep their factors, and the following block
starts under that stack. A definite height still uses the content box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json
import sys

_FONT = "#page { font-size: 10px; line-height: 10px; }\n"
_ONE = '<div id="page"><div id="grid"><div id="a">AB</div></div><div id="after"></div></div>'
_TWO = (
    '<div id="page"><div id="grid"><div id="a">AB</div>'
    '<div id="b">CD</div></div><div id="after"></div></div>'
)
_SPAN = (
    '<div id="page"><div id="grid"><div id="a">AB</div></div>'
    '<div id="after"></div></div>'
)
_SINGLE = (
    _FONT
    + "#grid { display: grid; width: 100px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr; }\n"
)
_RATIO = (
    _FONT
    + "#grid { display: grid; width: 100px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr 2fr; }\n"
)
_EQUAL = (
    _FONT
    + "#grid { display: grid; width: 100px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr 1fr; }\n"
    + "#a { height: 20px; }\n"
    + "#b { height: 10px; }\n"
)
_GAP = (
    _FONT
    + "#grid { display: grid; width: 100px; row-gap: 10px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr 1fr; }\n"
)
_MIXED = (
    _FONT
    + "#grid { display: grid; width: 100px; "
    + "grid-template-columns: 100px; grid-template-rows: 20px 1fr; }\n"
)
_IMPLICIT = (
    _FONT
    + "#grid { display: grid; width: 100px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr; }\n"
    + "#b { height: 20px; }\n"
)
_ACROSS = (
    _FONT
    + "#grid { display: grid; width: 100px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr 1fr; }\n"
    + "#a { grid-row: span 2; height: 40px; }\n"
)
_DEFINITE = (
    _FONT
    + "#grid { display: grid; width: 100px; height: 40px; "
    + "grid-template-columns: 100px; grid-template-rows: 1fr; }\n"
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
        "y": box.get("y"),
        "content_height": box.get("content_height"),
        "border_height": box.get("border_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    single = _lay(layout_normal_flow, _ONE, _SINGLE)
    ratio = _lay(layout_normal_flow, _TWO, _RATIO)
    equal = _lay(layout_normal_flow, _TWO, _EQUAL)
    gapped = _lay(layout_normal_flow, _TWO, _GAP)
    mixed = _lay(layout_normal_flow, _TWO, _MIXED)
    implicit = _lay(layout_normal_flow, _TWO, _IMPLICIT)
    across = _lay(layout_normal_flow, _SPAN, _ACROSS)
    definite = _lay(layout_normal_flow, _ONE, _DEFINITE)
    observed: dict[str, object] = {
        "single": {"outcome": single.get("outcome"), "reason": single.get("reason"), "grid": _view(single, "grid"), "a": _view(single, "a"), "after": _view(single, "after")},
        "ratio": {"outcome": ratio.get("outcome"), "reason": ratio.get("reason"), "a": _view(ratio, "a"), "b": _view(ratio, "b"), "after": _view(ratio, "after")},
        "equal": {"outcome": equal.get("outcome"), "reason": equal.get("reason"), "grid": _view(equal, "grid"), "a": _view(equal, "a"), "b": _view(equal, "b"), "after": _view(equal, "after")},
        "gap": {"outcome": gapped.get("outcome"), "reason": gapped.get("reason"), "a": _view(gapped, "a"), "b": _view(gapped, "b"), "after": _view(gapped, "after")},
        "mixed": {"outcome": mixed.get("outcome"), "reason": mixed.get("reason"), "a": _view(mixed, "a"), "b": _view(mixed, "b"), "after": _view(mixed, "after")},
        "implicit": {"outcome": implicit.get("outcome"), "reason": implicit.get("reason"), "a": _view(implicit, "a"), "b": _view(implicit, "b"), "after": _view(implicit, "after")},
        "span": {"outcome": across.get("outcome"), "reason": across.get("reason"), "grid": _view(across, "grid"), "a": _view(across, "a"), "after": _view(across, "after")},
        "definite": {"outcome": definite.get("outcome"), "reason": definite.get("reason"), "grid": _view(definite, "grid"), "after": _view(definite, "after")},
    }
    checks = {
        "one_line_flex_row_sets_the_next_block": (
            single.get("outcome") == "placed"
            and _near(_box(single.get("boxes"), "grid"), content_height=10, border_height=10)
            and _near(_box(single.get("boxes"), "a"), y=0, content_height=10, border_height=10)
            and _near(_box(single.get("boxes"), "after"), y=10)
        ),
        "flex_factors_keep_their_ratio_from_content": (
            ratio.get("outcome") == "placed"
            and _near(_box(ratio.get("boxes"), "a"), y=0, content_height=10, border_height=10)
            and _near(_box(ratio.get("boxes"), "b"), y=10, content_height=20, border_height=20)
            and _near(_box(ratio.get("boxes"), "after"), y=30)
        ),
        "equal_factors_use_the_taller_content": (
            equal.get("outcome") == "placed"
            and _near(_box(equal.get("boxes"), "grid"), content_height=40, border_height=40)
            and _near(_box(equal.get("boxes"), "a"), y=0, content_height=20, border_height=20)
            and _near(_box(equal.get("boxes"), "b"), y=20, content_height=10, border_height=10)
            and _near(_box(equal.get("boxes"), "after"), y=40)
        ),
        "row_gap_separates_indefinite_flex_rows": (
            gapped.get("outcome") == "placed"
            and _near(_box(gapped.get("boxes"), "a"), y=0, content_height=10, border_height=10)
            and _near(_box(gapped.get("boxes"), "b"), y=20, content_height=10, border_height=10)
            and _near(_box(gapped.get("boxes"), "after"), y=30)
        ),
        "fixed_row_keeps_its_length_beside_a_flex_row": (
            mixed.get("outcome") == "placed"
            and _near(_box(mixed.get("boxes"), "a"), y=0, content_height=20, border_height=20)
            and _near(_box(mixed.get("boxes"), "b"), y=20, content_height=10, border_height=10)
            and _near(_box(mixed.get("boxes"), "after"), y=30)
        ),
        "implicit_row_keeps_its_own_content": (
            implicit.get("outcome") == "placed"
            and _near(_box(implicit.get("boxes"), "a"), y=0, content_height=10, border_height=10)
            and _near(_box(implicit.get("boxes"), "b"), y=10, content_height=20, border_height=20)
            and _near(_box(implicit.get("boxes"), "after"), y=30)
        ),
        "spanned_content_splits_across_flex_rows": (
            across.get("outcome") == "placed"
            and _near(_box(across.get("boxes"), "grid"), content_height=40, border_height=40)
            and _near(_box(across.get("boxes"), "a"), y=0, content_height=40, border_height=40)
            and _near(_box(across.get("boxes"), "after"), y=40)
        ),
        "definite_height_still_uses_the_content_box": (
            definite.get("outcome") == "placed"
            and _near(_box(definite.get("boxes"), "grid"), content_height=40, border_height=40)
            and _near(_box(definite.get("boxes"), "after"), y=40)
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
