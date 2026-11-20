"""Measure the scrollable overflow rectangle of a CSS box.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
correct rectangle and a tree the baseline cannot measure.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_scrollable_overflow import scrollable_overflow
    except Exception as exc:  # noqa: BLE001 - baseline without the reader still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def run(name: str, box: dict[str, object]) -> dict[str, object]:
        try:
            result = scrollable_overflow(box)
        except Exception as exc:  # noqa: BLE001 - a raised tree is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        if not isinstance(result, dict):
            result = {"outcome": "error"}
        observed[name] = result
        return result

    def expect(name: str, box: dict[str, object], **fields: object) -> None:
        result = run(name, box)
        checks.append(result.get("outcome") == "ok" and all(result.get(key) == value for key, value in fields.items()))

    padding = {"padding": "10px 5px", "width": 100, "height": 100, "overflow": "scroll"}
    expect(
        "shifted_width",
        {**padding, "children": [{"width": 200, "height": 0, "margin_right": 50, "position": "relative", "left": -1000}]},
        scroll_width=260,
        scroll_height=120,
        left=0,
        right=260,
    )
    expect(
        "shifted_height",
        {**padding, "children": [{"width": 0, "height": 200, "margin_bottom": 50, "position": "relative", "top": -1000}]},
        scroll_width=110,
        scroll_height=270,
        top=0,
        bottom=270,
    )
    expect(
        "inline_block",
        {
            **padding,
            "children": [
                {
                    "width": 200,
                    "height": 0,
                    "margin_right": 50,
                    "display": "inline-block",
                    "position": "relative",
                    "left": -1000,
                }
            ],
        },
        scroll_width=260,
        scroll_height=120,
    )
    expect(
        "collapsed_negative",
        {
            **padding,
            "children": [
                {
                    "width": 0,
                    "margin_bottom": 100,
                    "position": "relative",
                    "top": -1000,
                    "children": [{"height": 200, "margin_bottom": -50}],
                }
            ],
        },
        scroll_width=110,
        scroll_height=270,
    )
    expect(
        "rtl_width",
        {
            **padding,
            "direction": "rtl",
            "children": [{"width": 200, "height": 0, "margin_left": 50, "position": "relative", "right": -1000}],
        },
        scroll_width=260,
        scroll_height=120,
        left=-150,
        right=110,
    )
    expect(
        "vertical_rl_width",
        {
            **padding,
            "writing_mode": "vertical-rl",
            "children": [{"width": 200, "height": 0, "margin_left": 50, "position": "relative", "right": -1000}],
        },
        scroll_width=260,
        scroll_height=120,
        left=-150,
        right=110,
    )
    expect(
        "vertical_rl_height",
        {
            **padding,
            "writing_mode": "vertical-rl",
            "children": [{"width": 0, "height": 200, "margin_bottom": 50, "position": "relative", "top": -1000}],
        },
        scroll_width=110,
        scroll_height=270,
    )
    expect(
        "vertical_rl_collapsed",
        {
            **padding,
            "writing_mode": "vertical-rl",
            "children": [
                {
                    "height": 0,
                    "margin_left": 100,
                    "position": "relative",
                    "right": -1000,
                    "children": [{"width": 200, "margin_left": -50}],
                }
            ],
        },
        scroll_width=260,
        left=-150,
        right=110,
    )
    expect(
        "vertical_lr_width",
        {
            **padding,
            "writing_mode": "vertical-lr",
            "children": [{"width": 200, "height": 0, "margin_right": 50, "position": "relative", "left": -1000}],
        },
        scroll_width=260,
        left=0,
        right=260,
    )
    expect(
        "ink",
        {
            **padding,
            "children": [
                {
                    "width": 200,
                    "height": 0,
                    "margin_right": 50,
                    "position": "relative",
                    "left": -1000,
                    "outline": "solid red 2px",
                    "box_shadow": "0 0 10px black",
                }
            ],
        },
        scroll_width=260,
        scroll_height=120,
    )
    expect(
        "reachable_child",
        {**padding, "children": [{"width": 200, "height": 20}]},
        scroll_width=210,
        scroll_height=120,
    )
    expect(
        "positive_margins",
        {
            "width": 100,
            "height": 100,
            "overflow": "scroll",
            "children": [
                {
                    "width": 10,
                    "margin_bottom": 100,
                    "position": "relative",
                    "top": -1000,
                    "children": [{"height": 200, "margin_bottom": 40}],
                }
            ],
        },
        scroll_width=100,
        scroll_height=300,
    )
    hidden = {
        "width": 100,
        "height": 100,
        "overflow": "scroll",
        "children": [{"width": 40, "height": 40, "overflow": "hidden", "children": [{"width": 180, "height": 10}]}],
    }
    visible = {
        "width": 100,
        "height": 100,
        "overflow": "scroll",
        "children": [{"width": 40, "height": 40, "overflow": "visible", "children": [{"width": 180, "height": 10}]}],
    }
    expect("clipped_descendant", hidden, scroll_width=100, scroll_height=100)
    expect("visible_descendant", visible, scroll_width=180, scroll_height=100)
    expect(
        "translated",
        {"width": 100, "height": 100, "overflow": "scroll", "children": [{"width": 100, "height": 20, "transform": "translateX(30px)"}]},
        scroll_width=130,
        scroll_height=100,
    )
    expect(
        "relative_reach",
        {"width": 100, "height": 100, "overflow": "scroll", "children": [{"width": 80, "height": 20, "position": "relative", "left": 50}]},
        scroll_width=130,
        scroll_height=100,
    )
    expect(
        "absolute_child",
        {
            "width": 100,
            "height": 100,
            "overflow": "scroll",
            "children": [{"position": "absolute", "left": 80, "top": 0, "width": 50, "height": 10}],
        },
        scroll_width=130,
        scroll_height=100,
    )
    duplicate = run("duplicate", {"id": "a", "width": 10, "height": 10, "children": [{"id": "a", "width": 1, "height": 1}]})
    floated = run("float", {"width": 10, "height": 10, "children": [{"float": "left", "width": 1, "height": 1}]})
    checks.append(duplicate.get("outcome") == "invalid" and duplicate.get("reason") == "id")
    checks.append(floated.get("outcome") == "invalid" and floated.get("reason") == "float")
    return all(checks), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"observed": observed, "passed": passed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
