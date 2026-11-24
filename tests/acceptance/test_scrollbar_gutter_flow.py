"""Reserve a classic scrollbar gutter inside a horizontal scrollport.

A stable gutter narrows the content box by 15px while the border box stays
200px, even when the child fits. stable both-edges also shifts the child.
auto reserves that gutter for overflow scroll and for an overflowing auto
port, and leaves a fitting auto port at the full width. Overlay scrollbars,
overflow visible, and overflow clip do not reserve one. both-edges without
stable is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_PAGE = (
    '<div id="page"><div id="port"><div id="child"></div></div>'
    '<div id="next"></div></div>'
)
_FLEX = '<div id="page"><div id="row"><div id="item"></div></div></div>'
_WORDS = '<div id="page"><div id="port">AA AA AA AA</div></div>'
_RESET = "#page, #port, #child, #next, #row, #item { margin: 0px; }"


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
        "border_width": box.get("border_width"),
        "content_height": box.get("content_height"),
        "border_height": box.get("border_height"),
    }


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, stylesheet: str, *, markup: str = _PAGE, **kwargs: object) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return placed if isinstance(placed, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _port(child_height: int, overflow: str, gutter: str | None = None) -> str:
    extra = "" if gutter is None else f" scrollbar-gutter: {gutter};"
    return (
        _RESET
        + f"#port {{ width: 200px; height: 80px; overflow: {overflow};{extra} }}"
        + f" #child {{ width: 100%; height: {child_height}px; }}"
        + " #next { height: 10px; }"
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    cases = {
        "stable_fit": _lay(layout_normal_flow, _port(20, "auto", "stable")),
        "both_edges": _lay(layout_normal_flow, _port(20, "auto", "stable both-edges")),
        "both_order": _lay(layout_normal_flow, _port(20, "auto", "both-edges stable")),
        "auto_fit": _lay(layout_normal_flow, _port(20, "auto")),
        "auto_over": _lay(layout_normal_flow, _port(120, "auto")),
        "scroll_fit": _lay(layout_normal_flow, _port(20, "scroll")),
        "hidden_stable": _lay(layout_normal_flow, _port(20, "hidden", "stable")),
        "hidden_auto": _lay(layout_normal_flow, _port(20, "hidden")),
        "visible_stable": _lay(layout_normal_flow, _port(20, "visible", "stable")),
        "clip_stable": _lay(layout_normal_flow, _port(20, "clip", "stable")),
        "overlay": _lay(layout_normal_flow, _port(20, "auto", "stable"), scrollbars="overlay"),
        "bare_edges": _lay(layout_normal_flow, _port(20, "auto", "both-edges")),
        "too_small": _lay(
            layout_normal_flow,
            _RESET
            + "#port { width: 10px; height: 40px; overflow: auto; scrollbar-gutter: stable; }"
            + " #child { width: 100%; height: 10px; } #next { height: 10px; }",
        ),
        "flex": _lay(
            layout_normal_flow,
            _RESET
            + "#row { display: flex; width: 200px; height: 40px; overflow: auto; scrollbar-gutter: stable; }"
            + " #item { width: 100%; height: 10px; }",
            markup=_FLEX,
        ),
        "lines": _lay(
            layout_normal_flow,
            "#page, #port { margin: 0px; } #port { width: 50px; height: 200px; overflow: auto;"
            " scrollbar-gutter: stable; font-size: 10px; line-height: 10px; }",
            markup=_WORDS,
        ),
    }
    observed: dict[str, object] = {}
    found: dict[str, tuple[dict[str, object] | None, dict[str, object] | None, dict[str, object] | None]] = {}
    for name, placed in cases.items():
        boxes = placed.get("boxes")
        port = _box(boxes, "row" if name == "flex" else "port")
        child = _box(boxes, "item" if name == "flex" else "child")
        nxt = _box(boxes, "next")
        found[name] = (port, child, nxt)
        lines = port.get("lines") if isinstance(port, dict) else None
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "port": _edge(port),
            "child": _edge(child),
            "next": _edge(nxt),
            "lines": [line.get("text") for line in lines] if isinstance(lines, list) else None,
        }

    def narrowed(name: str, width: int, child_x: int) -> bool:
        port, child, nxt = found[name]
        fitting = cases[name].get("outcome") == "placed"
        return (
            fitting
            and _near(port, content_width=width, border_width=200)
            and _near(child, x=child_x, content_width=width)
            and nxt is not None
            and port is not None
            and nxt.get("y") == port.get("border_height")
        )

    def full(name: str) -> bool:
        return narrowed(name, 200, 0)

    checks = {
        "stable_keeps_the_gutter_while_content_fits": narrowed("stable_fit", 185, 0),
        "both_edges_insets_the_start_edge": narrowed("both_edges", 170, 15),
        "both_edges_keyword_order_is_the_same_gutter": narrowed("both_order", 170, 15),
        "auto_leaves_a_fitting_port_whole": full("auto_fit"),
        "auto_narrows_an_overflowing_port": narrowed("auto_over", 185, 0),
        "scroll_reserves_a_gutter_before_overflow": narrowed("scroll_fit", 185, 0),
        "hidden_stable_reserves_a_gutter": narrowed("hidden_stable", 185, 0),
        "hidden_auto_does_not_reserve_a_gutter": full("hidden_auto"),
        "visible_does_not_reserve_a_gutter": full("visible_stable"),
        "clip_does_not_reserve_a_gutter": full("clip_stable"),
        "overlay_scrollbars_reserve_nothing": full("overlay"),
        "both_edges_without_stable_is_rejected": cases["bare_edges"].get("outcome") == "invalid"
        and cases["bare_edges"].get("reason") == "scrollbar-gutter is invalid",
        "a_gutter_wider_than_the_content_box_is_rejected": cases["too_small"].get("outcome") == "invalid"
        and cases["too_small"].get("reason") == "scrollbar gutter exceeds the content box",
        "a_flex_item_uses_the_narrowed_content_box": _near(found["flex"][1], x=0, content_width=185)
        and _near(found["flex"][0], content_width=185, border_width=200)
        and cases["flex"].get("outcome") == "placed",
        "wrapped_lines_use_the_narrowed_measure": observed["lines"]["lines"] == ["AA", "AA", "AA", "AA"]
        and _near(found["lines"][0], content_width=35, border_width=50),
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
