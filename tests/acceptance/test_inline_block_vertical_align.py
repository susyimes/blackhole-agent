"""Move an inline-block against its line with vertical-align.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree that still pins every atomic box to the parent
baseline exits 0 with passed false.
"""

from __future__ import annotations

import json
import sys

_MARKUP = '<p id="row">A<span id="atom">B</span></p><p id="next">C</p>'

_CASES = {
    "top": (
        "#row { font-size: 16px; line-height: 24px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; vertical-align: top; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 16, "y": 0, "content_height": 10, "border_height": 10},
        24,
        24,
    ),
    "text_top": (
        "#row { font-size: 16px; line-height: 24px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; vertical-align: text-top; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 16, "y": 4, "content_height": 10, "border_height": 10},
        24,
        24,
    ),
    "bottom": (
        "#row { font-size: 16px; line-height: 24px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; vertical-align: bottom; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 16, "y": 14, "content_height": 10, "border_height": 10},
        24,
        24,
    ),
    "middle": (
        "#row { font-size: 16px; line-height: 16px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; vertical-align: middle; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 16, "y": 11, "content_height": 10, "border_height": 10},
        21,
        21,
    ),
    "raise": (
        "#row { font-size: 10px; line-height: 10px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; vertical-align: 8px; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 10, "y": 0, "content_height": 10, "border_height": 10},
        18,
        18,
    ),
    "percent": (
        "#row { font-size: 10px; line-height: 10px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; vertical-align: 50%; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 10, "y": 0, "content_height": 10, "border_height": 10},
        15,
        15,
    ),
    "baseline": (
        "#row { font-size: 20px; line-height: 20px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; padding-bottom: 4px; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 20, "y": 10, "content_height": 10, "border_height": 14},
        24,
        24,
    ),
    "text_bottom": (
        "#row { font-size: 20px; line-height: 20px; } "
        "#atom { display: inline-block; font-size: 10px; line-height: 10px; padding-bottom: 4px; "
        "vertical-align: text-bottom; } "
        "#next { font-size: 10px; line-height: 10px; }",
        {"x": 20, "y": 6, "content_height": 10, "border_height": 14},
        20,
        20,
    ),
}


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


def _lay(layout, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(_MARKUP, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    checks: dict[str, bool] = {}
    observed: dict[str, object] = {}
    for name, (css, atom_box, row_height, next_y) in _CASES.items():
        placed = _lay(layout_normal_flow, css)
        row = _box(placed.get("boxes"), "row")
        atom = _box(placed.get("boxes"), "atom")
        nxt = _box(placed.get("boxes"), "next")
        line = None
        if isinstance(row, dict) and isinstance(row.get("lines"), list) and row["lines"]:
            first = row["lines"][0]
            line = first if isinstance(first, dict) else None
        checks[name] = (
            placed.get("outcome") == "placed"
            and _near(atom, **atom_box)
            and _near(row, content_height=row_height)
            and _near(line, height=row_height)
            and _near(nxt, y=next_y)
        )
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "atom": None
            if atom is None
            else {
                "x": atom.get("x"),
                "y": atom.get("y"),
                "content_height": atom.get("content_height"),
                "border_height": atom.get("border_height"),
            },
            "row_height": None if row is None else row.get("content_height"),
            "line_height": None if line is None else line.get("height"),
            "next_y": None if nxt is None else nxt.get("y"),
        }
    rejected = _lay(
        layout_normal_flow,
        "#row { font-size: 10px; line-height: 10px; } #atom { display: inline-block; vertical-align: super; }",
    )
    checks["super"] = rejected.get("outcome") == "invalid" and rejected.get("reason") == "vertical-align is unsupported"
    observed["super"] = {"outcome": rejected.get("outcome"), "reason": rejected.get("reason")}
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
