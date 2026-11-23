"""Place fixed and absolute boxes on a capturing ancestor's padding edge.

A static host with translate(0), layout containment, blur(0), or
will-change: transform holds a fixed child. A relative host and size
containment leave that child on the viewport. An absolute child uses the
transformed static host instead of the relative frame behind it. A
transformed inline or contents wrapper is rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_VIEW = {"viewport_width": 400, "viewport_height": 300}
_FIXED_PAGE = (
    '<div id="page"><div id="host"><div id="pin"></div></div><div id="next"></div></div>'
)
_ABS_PAGE = (
    '<div id="frame"><div id="host"><div id="abs"></div></div></div><div id="next"></div>'
)


def _fixed_css(effect: str) -> str:
    return (
        "html, body, #page, #next { margin: 0px; }"
        "#host { width: 100px; height: 40px; margin-top: 20px; margin-left: 30px;"
        " padding: 8px; border-width: 10px; border-style: solid; "
        + effect
        + " }"
        "#pin { position: fixed; left: 0px; top: 0px; width: 50%; height: 10px; }"
        "#next { height: 12px; }"
    )


def _abs_css(effect: str) -> str:
    return (
        "html, body, #next { margin: 0px; }"
        "#frame { position: relative; }"
        "#host { width: 80px; height: 30px; margin-left: 40px; margin-top: 24px;"
        " padding: 4px; border-width: 6px; border-style: solid; "
        + effect
        + " }"
        "#abs { position: absolute; left: 0px; top: 0px; width: 25%; height: 8px; }"
        "#next { height: 12px; }"
    )


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        result = layout(markup, stylesheet, **_VIEW)
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    return result if isinstance(result, dict) else {"outcome": "error", "boxes": None}


def _take(result: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
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


def _spot(item: dict[str, object] | None) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "x": item.get("x"),
        "y": item.get("y"),
        "content_width": item.get("content_width"),
        "content_height": item.get("content_height"),
    }


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without the walk still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    captured_pin = {"x": 40, "y": 30, "content_width": 58, "content_height": 10}
    viewport_pin = {"x": 0, "y": 0, "content_width": 200, "content_height": 10}
    following = {"x": 0, "y": 96, "content_width": 400, "content_height": 12}
    captured_effects = {
        "translate": "transform: translate(0);",
        "layout_containment": "contain: layout;",
        "blur": "filter: blur(0);",
        "will_change_transform": "will-change: transform;",
    }
    viewport_effects = {
        "relative": "position: relative;",
        "size_containment": "contain: size;",
        "will_change_position": "will-change: position;",
    }
    observed: dict[str, object] = {}
    checks: dict[str, bool] = {}
    for name, effect in {**captured_effects, **viewport_effects}.items():
        placed = _lay(layout_normal_flow, _FIXED_PAGE, _fixed_css(effect))
        pin = _take(placed, "pin")
        nxt = _take(placed, "next")
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "pin": _spot(pin),
            "next": _spot(nxt),
        }
        expect = captured_pin if name in captured_effects else viewport_pin
        checks[name] = (
            placed.get("outcome") == "placed"
            and _near(pin, **expect, border_width=expect["content_width"], border_height=10)
            and _near(nxt, **following, border_width=400, border_height=12)
        )

    anchored = _lay(layout_normal_flow, _ABS_PAGE, _abs_css("transform: translate(0);"))
    unanchored = _lay(layout_normal_flow, _ABS_PAGE, _abs_css(""))
    observed["absolute_on_transform"] = {
        "outcome": anchored.get("outcome"),
        "abs": _spot(_take(anchored, "abs")),
        "next": _spot(_take(anchored, "next")),
    }
    observed["absolute_on_relative_frame"] = {
        "outcome": unanchored.get("outcome"),
        "abs": _spot(_take(unanchored, "abs")),
        "next": _spot(_take(unanchored, "next")),
    }
    checks["absolute_on_transform"] = (
        anchored.get("outcome") == "placed"
        and _near(
            _take(anchored, "abs"),
            x=46,
            y=30,
            content_width=22,
            content_height=8,
            border_width=22,
            border_height=8,
        )
        and _near(_take(anchored, "next"), x=0, y=74, content_height=12)
    )
    checks["absolute_on_relative_frame"] = (
        unanchored.get("outcome") == "placed"
        and _near(
            _take(unanchored, "abs"),
            x=0,
            y=24,
            content_width=100,
            content_height=8,
            border_width=100,
            border_height=8,
        )
        and _near(_take(unanchored, "next"), x=0, y=74, content_height=12)
    )

    inline = _lay(
        layout_normal_flow,
        '<div id="page"><span id="tag"><i id="pin"></i></span></div>',
        "#tag { transform: translate(0); }"
        "#pin { position: fixed; left: 0px; top: 0px; width: 10px; height: 10px; }",
    )
    contents = _lay(
        layout_normal_flow,
        '<div id="page"><div id="wrap"><div id="pin"></div></div></div>',
        "#wrap { display: contents; transform: translate(0); }"
        "#pin { position: fixed; left: 0px; top: 0px; width: 10px; height: 10px; }",
    )
    invalid_contain = _lay(
        layout_normal_flow,
        '<div id="host"></div>',
        "#host { contain: layout none; width: 10px; height: 10px; }",
    )
    observed["inline_transform"] = {"outcome": inline.get("outcome"), "reason": inline.get("reason")}
    observed["contents_transform"] = {
        "outcome": contents.get("outcome"),
        "reason": contents.get("reason"),
    }
    observed["invalid_contain"] = {
        "outcome": invalid_contain.get("outcome"),
        "reason": invalid_contain.get("reason"),
    }
    checks["inline_transform"] = (
        inline.get("outcome") == "invalid" and inline.get("reason") == "inline fragment"
    )
    checks["contents_transform"] = (
        contents.get("outcome") == "invalid"
        and contents.get("reason") == "contents capture is unsupported"
    )
    checks["invalid_contain"] = (
        invalid_contain.get("outcome") == "invalid"
        and invalid_contain.get("reason") == "contain is invalid"
    )
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
