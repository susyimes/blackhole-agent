"""Keep a fixed column-height and wrap overflow into another row.

column-height 30px leaves the empty part of the row in place, so one 10px
child makes the multicol 30px tall and the next block starts at y 30.
Seven 10px children fill that row three per column and put the seventh on
the next row. row-gap 10px, and an omitted row-gap at font-size 10px, put
that row at y 40 and the next block at y 70. row-gap 0px packs a full column
beside the first box instead of under it. A 40px box overflows a 20px column
and the row stays 20px. column-wrap nowrap, a specified height, a column
span, a forced break, and a non-px column-height are rejected. wrap without
a column-height still balances.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_BASE = (
    "html, body, div { margin: 0px; }\n"
    "#page { font-size: 10px; line-height: 10px; width: 200px; }\n"
    "#next { height: 8px; }\n"
)


def supply_html_parser() -> None:
    """Restore the baseline's genuine runtime data to a src-only replay archive."""
    from blackhole_agent import html5_document

    package = html5_document._package_dir() / "html5lib"
    if (package / "__init__.py").is_file():
        return
    root = Path(html5_document.__file__).resolve().parents[2]
    if (root / ".git").exists() or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise RuntimeError("the checkout is missing its absorbed HTML parser")
    checkout = next((item.parent for item in map(Path, sys.path) if (item.parent / ".git").exists()), None)
    if checkout is None:
        raise RuntimeError("the replay requires the installed project's Git object database")
    tree = "397395a7d05f3f55ebd5bcb029a66b55bac0306b"
    archive = subprocess.check_output(["git", "-C", str(checkout), "archive", "--format=zip", tree], timeout=30)
    with zipfile.ZipFile(io.BytesIO(archive)) as files:
        files.extractall(package)


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


def _markup(ids: str) -> str:
    children = "".join(f'<div id="{ident}"></div>' for ident in ids.split())
    return f'<div id="page"><div id="cols">{children}</div><div id="next"></div></div>'


def _css(cols: str, children: str = "") -> str:
    return _BASE + f"#cols {{ {cols} }}\n" + children


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
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
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        supply_html_parser()
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    short = _lay(
        layout_normal_flow,
        _markup("a"),
        _css("column-count: 2; column-gap: 0px; column-height: 30px; width: 80px;", "#a { height: 10px; }\n"),
    )
    wrapped = _lay(
        layout_normal_flow,
        _markup("a b c d e f g"),
        _css(
            "column-count: 2; column-gap: 0px; column-height: 30px; row-gap: 10px; width: 80px;",
            "#a, #b, #c, #d, #e, #f, #g { height: 10px; }\n",
        ),
    )
    normal_gap = _lay(
        layout_normal_flow,
        _markup("a b c d e f g"),
        _css(
            "column-count: 2; column-gap: 0px; column-height: 30px; width: 80px;",
            "#a, #b, #c, #d, #e, #f, #g { height: 10px; }\n",
        ),
    )
    flush = _lay(
        layout_normal_flow,
        _markup("a b c d"),
        _css(
            "column-count: 2; column-gap: 0px; column-height: 20px; row-gap: 0px; width: 80px;",
            "#a, #b, #c, #d { height: 20px; }\n",
        ),
    )
    overflow = _lay(
        layout_normal_flow,
        _markup("a"),
        _css("column-count: 2; column-gap: 0px; column-height: 20px; width: 80px;", "#a { height: 40px; }\n"),
    )
    balanced = _lay(
        layout_normal_flow,
        _markup("a b c"),
        _css("column-count: 2; column-gap: 0px; column-wrap: wrap; width: 40px;", "#a, #b, #c { height: 10px; }\n"),
    )
    nowrap = _lay(
        layout_normal_flow,
        _markup("a"),
        _css(
            "column-count: 2; column-gap: 0px; column-height: 30px; column-wrap: nowrap; width: 80px;",
            "#a { height: 10px; }\n",
        ),
    )
    specified = _lay(
        layout_normal_flow,
        _markup("a"),
        _css(
            "column-count: 2; column-gap: 0px; column-height: 30px; height: 40px; width: 80px;",
            "#a { height: 10px; }\n",
        ),
    )
    spanned = _lay(
        layout_normal_flow,
        _markup("a s"),
        _css(
            "column-count: 2; column-gap: 0px; column-height: 30px; width: 80px;",
            "#a { height: 10px; }\n#s { height: 10px; column-span: all; }\n",
        ),
    )
    forced = _lay(
        layout_normal_flow,
        _markup("a b"),
        _css(
            "column-count: 2; column-gap: 0px; column-height: 30px; width: 80px;",
            "#a { height: 10px; }\n#b { height: 10px; break-before: column; }\n",
        ),
    )
    ems = _lay(
        layout_normal_flow,
        _markup("a"),
        _css("column-count: 2; column-height: 2em; width: 80px;", "#a { height: 10px; }\n"),
    )

    def take(result: dict[str, object], ident: str) -> dict[str, object] | None:
        return _box(result.get("boxes"), ident)

    observed: dict[str, object] = {
        "short_outcome": short.get("outcome"),
        "short_reason": short.get("reason"),
        "short_a": _view(short, "a"),
        "short_cols": _view(short, "cols"),
        "short_next_y": None if take(short, "next") is None else take(short, "next").get("y"),
        "wrapped_outcome": wrapped.get("outcome"),
        "wrapped_g": _view(wrapped, "g"),
        "wrapped_cols": _view(wrapped, "cols"),
        "wrapped_next_y": None if take(wrapped, "next") is None else take(wrapped, "next").get("y"),
        "normal_gap_g": _view(normal_gap, "g"),
        "normal_gap_next_y": None if take(normal_gap, "next") is None else take(normal_gap, "next").get("y"),
        "flush_b": _view(flush, "b"),
        "flush_c": _view(flush, "c"),
        "flush_next_y": None if take(flush, "next") is None else take(flush, "next").get("y"),
        "overflow_cols": _view(overflow, "cols"),
        "overflow_a": _view(overflow, "a"),
        "overflow_next_y": None if take(overflow, "next") is None else take(overflow, "next").get("y"),
        "balanced_b": _view(balanced, "b"),
        "balanced_c": _view(balanced, "c"),
        "balanced_next_y": None if take(balanced, "next") is None else take(balanced, "next").get("y"),
        "nowrap_outcome": nowrap.get("outcome"),
        "nowrap_reason": nowrap.get("reason"),
        "specified_reason": specified.get("reason"),
        "spanned_reason": spanned.get("reason"),
        "forced_reason": forced.get("reason"),
        "em_reason": ems.get("reason"),
    }
    checks = {
        "short_row_keeps_the_column_height": (
            short.get("outcome") == "placed"
            and _near(take(short, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(short, "cols"), content_height=30)
            and _near(take(short, "next"), y=30)
        ),
        "seventh_box_starts_the_next_row_after_the_row_gap": (
            wrapped.get("outcome") == "placed"
            and _near(take(wrapped, "a"), x=0, y=0, content_width=40, content_height=10)
            and _near(take(wrapped, "c"), x=0, y=20)
            and _near(take(wrapped, "d"), x=40, y=0)
            and _near(take(wrapped, "g"), x=0, y=40, content_width=40, content_height=10)
            and _near(take(wrapped, "cols"), content_height=70)
            and _near(take(wrapped, "next"), y=70)
        ),
        "omitted_row_gap_is_one_em": (
            normal_gap.get("outcome") == "placed"
            and _near(take(normal_gap, "g"), x=0, y=40)
            and _near(take(normal_gap, "cols"), content_height=70)
            and _near(take(normal_gap, "next"), y=70)
        ),
        "zero_row_gap_puts_the_next_full_box_beside_the_first": (
            flush.get("outcome") == "placed"
            and _near(take(flush, "a"), x=0, y=0, content_height=20)
            and _near(take(flush, "b"), x=40, y=0, content_height=20)
            and _near(take(flush, "c"), x=0, y=20, content_height=20)
            and _near(take(flush, "d"), x=40, y=20)
            and _near(take(flush, "cols"), content_height=40)
            and _near(take(flush, "next"), y=40)
        ),
        "tall_box_overflows_and_the_row_keeps_its_height": (
            overflow.get("outcome") == "placed"
            and _near(take(overflow, "a"), x=0, y=0, content_height=40)
            and _near(take(overflow, "cols"), content_height=20)
            and _near(take(overflow, "next"), y=20)
        ),
        "wrap_without_column_height_still_balances": (
            balanced.get("outcome") == "placed"
            and _near(take(balanced, "a"), x=0, y=0, content_width=20, content_height=10)
            and _near(take(balanced, "b"), x=0, y=10, content_width=20, content_height=10)
            and _near(take(balanced, "c"), x=20, y=0, content_width=20, content_height=10)
            and _near(take(balanced, "next"), y=20)
        ),
        "nowrap_with_column_height_is_rejected": (
            nowrap.get("outcome") == "invalid" and nowrap.get("reason") == "column-wrap nowrap is unsupported"
        ),
        "specified_height_with_column_height_is_rejected": (
            specified.get("outcome") == "invalid"
            and specified.get("reason") == "column-height with a specified height is unsupported"
        ),
        "column_span_with_column_height_is_rejected": (
            spanned.get("outcome") == "invalid"
            and spanned.get("reason") == "column-span with column-height is unsupported"
        ),
        "forced_break_with_column_height_is_rejected": (
            forced.get("outcome") == "invalid"
            and forced.get("reason") == "column break with column-height is unsupported"
        ),
        "non_px_column_height_is_rejected": (
            ems.get("outcome") == "invalid" and ems.get("reason") == "column-height is invalid"
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
