"""Size a replaced image from box-sizing: border-box.

A specified width, height, or maximum is the border box. Padding and border
shrink the content box and do not let it go below zero, so chrome larger than
the specified size grows the used border box. A plain aspect-ratio maps that
border box. aspect-ratio: auto with a ratio still maps the content box, and
the intrinsic ratio does too. Content-box keeps the specified size as the
content box. An absolute image leaves the following block in place. A
vertical writing mode stays rejected.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_RESET = (
    "html, body, #page, #photo, #abs, #next { margin: 0px; }"
    " #next { height: 10px; }"
)
_FLOW = (
    '<div id="page"><img id="photo" width="400" height="200">'
    '<div id="next"></div></div>'
)
_ABS = (
    '<div id="page"><img id="abs" width="400" height="200">'
    '<div id="next"></div></div>'
)
_CHROME = "padding: 10px; border-width: 10px; border-style: solid;"


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
        "border_width": box.get("border_width"),
        "border_height": box.get("border_height"),
    }


def _near(item: dict[str, object] | None, **expected: object) -> bool:
    if item is None:
        return False
    return all(item.get(key) == value for key, value in expected.items())


def _lay(layout, markup: str, stylesheet: str) -> dict[str, object]:
    try:
        placed = layout(markup, stylesheet, viewport_width=400)
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
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; aspect-ratio: 1 / 1;"
            + " box-sizing: border-box; "
            + _CHROME
            + " }",
        ),
        "asymmetric": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; aspect-ratio: 2 / 1;"
            + " box-sizing: border-box; padding-left: 30px; padding-bottom: 10px; }",
        ),
        "natural": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; box-sizing: border-box; "
            + _CHROME
            + " }",
        ),
        "auto_ratio": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; aspect-ratio: auto 1 / 1;"
            + " box-sizing: border-box; "
            + _CHROME
            + " }",
        ),
        "specified": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: 40px; box-sizing: border-box; "
            + _CHROME
            + " }",
        ),
        "capped": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; aspect-ratio: 1 / 1;"
            + " max-height: 50px; box-sizing: border-box; padding: 10px; }",
        ),
        "percent": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 25%; height: auto; aspect-ratio: 1 / 1;"
            + " box-sizing: border-box; "
            + _CHROME
            + " }",
        ),
        "oversize": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 20px; height: 20px; box-sizing: border-box;"
            + " padding: 15px; }",
        ),
        "content_box": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; aspect-ratio: 1 / 1; "
            + _CHROME
            + " }",
        ),
        "absolute": _lay(
            layout_normal_flow,
            _ABS,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: auto;"
            + " aspect-ratio: 1 / 1; box-sizing: border-box; "
            + _CHROME
            + " }",
        ),
        "vertical": _lay(
            layout_normal_flow,
            _ABS,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: auto;"
            + " aspect-ratio: 1 / 1; box-sizing: border-box; writing-mode: vertical-rl; }",
        ),
    }
    observed: dict[str, object] = {}
    edges: dict[str, tuple[dict[str, object] | None, dict[str, object] | None]] = {}
    for name, placed in cases.items():
        boxes = placed.get("boxes")
        subject_id = "abs" if name in {"absolute", "vertical"} else "photo"
        subject = _box(boxes, subject_id)
        nxt = _box(boxes, "next")
        edges[name] = (subject, nxt)
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "box": _edge(subject),
            "next": _edge(nxt),
        }

    def flowed(name: str, **expected: object) -> bool:
        subject, nxt = edges[name]
        return (
            cases[name].get("outcome") == "placed"
            and _near(subject, y=0, **expected)
            and nxt is not None
            and nxt.get("y") == expected.get("border_height")
        )

    subject, nxt = edges["absolute"]
    checks = {
        "plain_ratio_maps_the_border_box": flowed(
            "square",
            x=0,
            content_width=60,
            content_height=60,
            border_width=100,
            border_height=100,
        ),
        "asymmetric_chrome_uses_the_border_ratio": flowed(
            "asymmetric",
            x=0,
            content_width=70,
            content_height=40,
            border_width=100,
            border_height=50,
        ),
        "intrinsic_ratio_maps_the_content_box": flowed(
            "natural",
            x=0,
            content_width=60,
            content_height=30,
            border_width=100,
            border_height=70,
        ),
        "auto_ratio_maps_the_content_box": flowed(
            "auto_ratio",
            x=0,
            content_width=60,
            content_height=30,
            border_width=100,
            border_height=70,
        ),
        "specified_height_stays_the_border_box": flowed(
            "specified",
            x=0,
            content_width=60,
            content_height=0,
            border_width=100,
            border_height=40,
        ),
        "maximum_clamps_the_border_box": flowed(
            "capped",
            x=0,
            content_width=80,
            content_height=30,
            border_width=100,
            border_height=50,
        ),
        "percentage_width_is_the_border_box": flowed(
            "percent",
            x=0,
            content_width=60,
            content_height=60,
            border_width=100,
            border_height=100,
        ),
        "chrome_larger_than_the_specified_size_grows_the_border_box": flowed(
            "oversize",
            x=0,
            content_width=0,
            content_height=0,
            border_width=30,
            border_height=30,
        ),
        "content_box_keeps_the_specified_content_size": flowed(
            "content_box",
            x=0,
            content_width=100,
            content_height=100,
            border_width=140,
            border_height=140,
        ),
        "absolute_border_box_leaves_the_following_block": cases["absolute"].get("outcome") == "placed"
        and _near(
            subject,
            x=0,
            y=0,
            content_width=60,
            content_height=60,
            border_width=100,
            border_height=100,
        )
        and nxt is not None
        and nxt.get("y") == 0,
        "vertical_writing_mode_stays_rejected": cases["vertical"].get("outcome") == "invalid"
        and cases["vertical"].get("reason") == "replaced writing mode is unsupported",
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
