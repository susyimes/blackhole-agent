"""Stick normal-flow blocks to a scrollport without moving their siblings.

A top inset pulls a block that starts above it and leaves the next block at
its static y. A block already below that inset stays put. Viewport scroll
moves only the viewport's sticky edge. A nearer overflow scrollport keeps
its sticky child at the same y for two viewport scroll offsets. The
containing block end stops a shift that would leave it. A sticky float and
a vertical-rl sticky box are rejected. A sticky child of a sticky parent is
covered by the nested sticky probe.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A layout that still rejects position:sticky exits 0 with
passed false.
"""

from __future__ import annotations

import json

_HOLD = '<div id="page"><div id="stick">A</div><div id="next">B</div></div>'
_HOLD_CSS = (
    "#page { height: 800px; margin: 0px; }\n"
    "#stick { position: sticky; top: 10px; height: 40px; margin: 0px; }\n"
    "#next { height: 20px; margin: 0px; }\n"
)
_REST = '<div id="page"><div id="gap"></div><div id="rest">R</div><div id="tail">T</div></div>'
_REST_CSS = (
    "#page { height: 800px; margin: 0px; }\n"
    "#gap { height: 100px; margin: 0px; }\n"
    "#rest { position: sticky; top: 10px; height: 40px; margin: 0px; }\n"
    "#tail { height: 20px; margin: 0px; }\n"
)
_CAP = '<div id="page"><div id="gap"></div><div id="cap">C</div></div>'
_CAP_CSS = (
    "#page { height: 200px; margin: 0px; }\n"
    "#gap { height: 100px; margin: 0px; }\n"
    "#cap { position: sticky; top: 0px; height: 40px; margin: 0px; }\n"
)
_PORT = (
    '<div id="page"><div id="lead"></div><div id="port"><div id="inner">I</div></div>'
    '<div id="outer">O</div></div>'
)
_PORT_CSS = (
    "#page { height: 900px; margin: 0px; }\n"
    "#lead { height: 40px; margin: 0px; }\n"
    "#port { overflow: scroll; height: 100px; margin: 0px; }\n"
    "#inner { position: sticky; top: 5px; height: 20px; margin: 0px; }\n"
    "#outer { position: sticky; top: 0px; height: 20px; margin: 0px; }\n"
)
_FLOAT = '<div id="page"><div id="flo">A</div><p id="copy">B</p></div>'
_FLOAT_CSS = "#flo { float: left; position: sticky; top: 0px; width: 40px; height: 40px; }\n"
_VERTICAL = '<div id="page"><div id="side">A</div></div>'
_VERTICAL_CSS = (
    "#side { writing-mode: vertical-rl; position: sticky; top: 0px; height: 40px; width: 20px; }\n"
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


def _lay(layout_normal_flow, markup: str, stylesheet: str, scroll_y: int = 0) -> dict[str, object]:
    try:
        result = layout_normal_flow(
            markup,
            stylesheet,
            viewport_width=300,
            viewport_height=300,
            scroll_y=scroll_y,
        )
    except TypeError as exc:
        return {"outcome": "invalid", "reason": str(exc), "boxes": None}
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return result if isinstance(result, dict) else {"outcome": "error", "reason": "layout is invalid", "boxes": None}


def _point(result: dict[str, object], ident: str) -> dict[str, object] | None:
    box = _box(result.get("boxes"), ident)
    if box is None:
        return None
    return {"x": box.get("x"), "y": box.get("y"), "border_height": box.get("border_height")}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without placement still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    hold = _lay(layout_normal_flow, _HOLD, _HOLD_CSS)
    resting = _lay(layout_normal_flow, _REST, _REST_CSS)
    scrolled = _lay(layout_normal_flow, _REST, _REST_CSS, scroll_y=150)
    capped = _lay(layout_normal_flow, _CAP, _CAP_CSS, scroll_y=180)
    port_still = _lay(layout_normal_flow, _PORT, _PORT_CSS)
    port_scrolled = _lay(layout_normal_flow, _PORT, _PORT_CSS, scroll_y=200)
    floated = _lay(layout_normal_flow, _FLOAT, _FLOAT_CSS)
    vertical = _lay(layout_normal_flow, _VERTICAL, _VERTICAL_CSS)
    observed: dict[str, object] = {
        "hold": {name: _point(hold, name) for name in ("stick", "next")},
        "resting": {name: _point(resting, name) for name in ("rest", "tail")},
        "scrolled": {name: _point(scrolled, name) for name in ("gap", "rest", "tail")},
        "capped": _point(capped, "cap"),
        "port_still": {name: _point(port_still, name) for name in ("lead", "port", "inner", "outer")},
        "port_scrolled": {name: _point(port_scrolled, name) for name in ("lead", "port", "inner", "outer")},
        "float_reason": floated.get("reason"),
        "vertical_reason": vertical.get("reason"),
    }
    checks = {
        "hold_stick": _near(_box(hold.get("boxes"), "stick"), x=0, y=10, border_height=40),
        "hold_next": _near(_box(hold.get("boxes"), "next"), x=0, y=40, border_height=20),
        "resting_rest": _near(_box(resting.get("boxes"), "rest"), x=0, y=100, border_height=40),
        "resting_tail": _near(_box(resting.get("boxes"), "tail"), x=0, y=140, border_height=20),
        "scrolled_rest": _near(_box(scrolled.get("boxes"), "rest"), x=0, y=160, border_height=40),
        "scrolled_tail": _near(_box(scrolled.get("boxes"), "tail"), x=0, y=140, border_height=20),
        "scrolled_gap": _near(_box(scrolled.get("boxes"), "gap"), x=0, y=0, border_height=100),
        "capped": _near(_box(capped.get("boxes"), "cap"), x=0, y=160, border_height=40),
        "port_inner_still": _near(_box(port_still.get("boxes"), "inner"), x=0, y=45, border_height=20),
        "port_inner_scrolled": _near(_box(port_scrolled.get("boxes"), "inner"), x=0, y=45, border_height=20),
        "port_outer_still": _near(_box(port_still.get("boxes"), "outer"), x=0, y=140, border_height=20),
        "port_outer_scrolled": _near(_box(port_scrolled.get("boxes"), "outer"), x=0, y=200, border_height=20),
        "port_lead": _near(_box(port_scrolled.get("boxes"), "lead"), y=0),
        "port_box": _near(_box(port_scrolled.get("boxes"), "port"), y=40),
        "floated": floated.get("outcome") == "invalid" and floated.get("boxes") is None,
        "vertical": vertical.get("outcome") == "invalid" and vertical.get("boxes") is None,
    }
    observed["checks"] = checks
    reasons = {
        "hold": hold.get("reason"),
        "resting": resting.get("reason"),
        "scrolled": scrolled.get("reason"),
        "capped": capped.get("reason"),
        "port_still": port_still.get("reason"),
        "port_scrolled": port_scrolled.get("reason"),
    }
    observed["reasons"] = reasons
    return all(checks.values()), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
