"""Map a preferred aspect ratio into an in-flow block's used height.

An automatic height is at least the size transferred from the definite
width. A taller child still stretches the box. A scrollport or an explicit
min-height of zero keeps the transferred size and lets the extra child
overflow. max-height clamps the mapped size. A specified height stays
specified. border-box maps the ratio through the border box.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_RESET = "#page, #box, #next, #child { margin: 0px; }"
_EMPTY = '<div id="page"><div id="box"></div><div id="next"></div></div>'
_CHILD = (
    '<div id="page"><div id="box"><div id="child"></div></div>'
    '<div id="next"></div></div>'
)
_TEXT = '<div id="page"><p id="box">Hi</p><div id="next"></div></div>'


def _box(boxes: object, ident: str) -> dict[str, object] | None:
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return item
    return None


def _edge(box: dict[str, object] | None) -> dict[str, object] | None:
    if box is None:
        return None
    return {
        "x": box.get("x"),
        "y": box.get("y"),
        "content_width": box.get("content_width"),
        "content_height": box.get("content_height"),
        "border_height": box.get("border_height"),
    }


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=200)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "square": _lay(
            layout_normal_flow,
            _EMPTY,
            _RESET + "#box { width: 100px; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "half": _lay(
            layout_normal_flow,
            _EMPTY,
            _RESET + "#box { width: 80px; aspect-ratio: 2 / 1; } #next { height: 6px; }",
        ),
        "text": _lay(
            layout_normal_flow,
            _TEXT,
            _RESET + "#box { width: 100px; aspect-ratio: 1/1; font-size: 10px; line-height: 10px; } #next { height: 4px; }",
        ),
        "grows": _lay(
            layout_normal_flow,
            _CHILD,
            _RESET + "#box { width: 40px; aspect-ratio: 1 / 1; } #child { height: 70px; } #next { height: 8px; }",
        ),
        "scroll": _lay(
            layout_normal_flow,
            _CHILD,
            _RESET
            + "#box { width: 40px; aspect-ratio: 1 / 1; overflow: hidden; } #child { height: 70px; } #next { height: 8px; }",
        ),
        "zero_min": _lay(
            layout_normal_flow,
            _CHILD,
            _RESET
            + "#box { width: 40px; aspect-ratio: 1 / 1; min-height: 0px; } #child { height: 70px; } #next { height: 8px; }",
        ),
        "cap": _lay(
            layout_normal_flow,
            _EMPTY,
            _RESET + "#box { width: 100px; aspect-ratio: 1 / 1; max-height: 30px; } #next { height: 5px; }",
        ),
        "specified": _lay(
            layout_normal_flow,
            _EMPTY,
            _RESET + "#box { width: 100px; height: 20px; aspect-ratio: 1 / 1; } #next { height: 5px; }",
        ),
        "border_box": _lay(
            layout_normal_flow,
            _EMPTY,
            _RESET
            + "#box { width: 100px; box-sizing: border-box; padding: 10px; aspect-ratio: 1 / 1; } #next { height: 5px; }",
        ),
    }
    observed: dict[str, object] = {}
    edges: dict[str, tuple[dict[str, object] | None, dict[str, object] | None]] = {}
    for name, placed in cases.items():
        boxes = placed.get("boxes")
        box = _box(boxes, "box")
        nxt = _box(boxes, "next")
        edges[name] = (box, nxt)
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "box": _edge(box),
            "next": _edge(nxt),
        }

    def ok(name: str, **expected: object) -> bool:
        box, nxt = edges[name]
        return cases[name].get("outcome") == "placed" and _near(box, **expected) and nxt is not None

    checks = {
        "empty_square_sets_the_next_block": ok("square", x=0, y=0, content_width=100, content_height=100, border_height=100)
        and _near(edges["square"][1], y=100, content_height=10),
        "two_to_one_maps_the_width": ok("half", content_width=80, content_height=40, border_height=40)
        and _near(edges["half"][1], y=40),
        "short_text_keeps_the_square": ok("text", content_width=100, content_height=100, border_height=100)
        and _near(edges["text"][1], y=100),
        "taller_child_stretches_the_box": ok("grows", content_width=40, content_height=70, border_height=70)
        and _near(edges["grows"][1], y=70),
        "scrollport_keeps_the_square": ok("scroll", content_width=40, content_height=40, border_height=40)
        and _near(edges["scroll"][1], y=40),
        "explicit_zero_minimum_keeps_the_square": ok("zero_min", content_height=40, border_height=40)
        and _near(edges["zero_min"][1], y=40),
        "max_height_clamps_the_square": ok("cap", content_height=30, border_height=30)
        and _near(edges["cap"][1], y=30),
        "specified_height_stays_specified": ok("specified", content_height=20, border_height=20)
        and _near(edges["specified"][1], y=20),
        "border_box_maps_through_the_padding_edge": ok(
            "border_box", content_width=80, content_height=80, border_height=100
        )
        and _near(edges["border_box"][1], y=100),
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
