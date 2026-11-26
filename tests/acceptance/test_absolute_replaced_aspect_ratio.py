"""Size an absolute or fixed replaced image from its preferred aspect-ratio.

A plain ratio replaces the intrinsic ratio. ``auto`` with a ratio keeps the
intrinsic ratio when both attributes exist. A specified height stays
specified, and a maximum clamps only the automatic axis. Definite insets do
not stretch that used size. The following in-flow block stays put. A vertical
writing mode stays rejected. ``border-box`` with no padding or border keeps
the same 100 by 100 square.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json
import sys

_RESET = "#page, #host, #abs, #photo, #next { margin: 0px; }"
_PHOTO = (
    '<div id="page"><img id="abs" width="400" height="200">'
    '<div id="next"></div></div>'
)
_BARE = '<div id="page"><img id="abs"><div id="next"></div></div>'
_HOST = (
    '<div id="host"><img id="abs" width="400" height="200">'
    '<div id="next"></div></div>'
)
_FLOW = (
    '<div id="page"><img id="photo" width="400" height="200">'
    '<div id="next"></div></div>'
)


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
            _PHOTO,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: auto;"
            + " aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "defer": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: auto;"
            + " aspect-ratio: auto 1 / 1; } #next { height: 10px; }",
        ),
        "bare": _lay(
            layout_normal_flow,
            _BARE,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 80px; height: auto;"
            + " aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "specified": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: 40px;"
            + " aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "capped": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: auto;"
            + " aspect-ratio: 1 / 1; max-height: 40px; } #next { height: 10px; }",
        ),
        "both_auto": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#abs { position: absolute; left: 0px; right: 0px; top: 0px; bottom: 0px;"
            + " aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "insets": _lay(
            layout_normal_flow,
            _HOST,
            _RESET
            + "#host { position: relative; width: 200px; height: 80px; }"
            + " #abs { position: absolute; left: 0px; right: 0px; top: 0px; bottom: 0px;"
            + " width: 100px; height: auto; aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "fixed": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#abs { position: fixed; left: 3px; top: 4px; width: 100px; height: auto;"
            + " aspect-ratio: 1 / 1; } #next { height: 10px; }",
        ),
        "vertical": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px;"
            + " aspect-ratio: 1 / 1; writing-mode: vertical-rl; }",
        ),
        "border_box": _lay(
            layout_normal_flow,
            _PHOTO,
            _RESET
            + "#abs { position: absolute; left: 0px; top: 0px; width: 100px; height: auto;"
            + " aspect-ratio: 1 / 1; box-sizing: border-box; }",
        ),
        "flow": _lay(
            layout_normal_flow,
            _FLOW,
            _RESET
            + "#photo { display: block; width: 100px; height: auto; aspect-ratio: 1 / 1; }"
            + " #next { height: 10px; }",
        ),
    }
    observed: dict[str, object] = {}
    edges: dict[str, tuple[dict[str, object] | None, dict[str, object] | None, dict[str, object] | None]] = {}
    for name, placed in cases.items():
        boxes = placed.get("boxes")
        subject_id = "photo" if name == "flow" else "abs"
        subject = _box(boxes, subject_id)
        nxt = _box(boxes, "next")
        host = _box(boxes, "host")
        edges[name] = (subject, nxt, host)
        observed[name] = {
            "outcome": placed.get("outcome"),
            "reason": placed.get("reason"),
            "box": _edge(subject),
            "next": _edge(nxt),
            "host": _edge(host),
        }

    def parked(name: str, **expected: object) -> bool:
        subject, nxt, _host = edges[name]
        return (
            cases[name].get("outcome") == "placed"
            and _near(subject, **expected)
            and nxt is not None
            and nxt.get("y") == 0
        )

    subject, nxt, host = edges["insets"]
    flow_subject, flow_next, _flow_host = edges["flow"]
    checks = {
        "plain_ratio_replaces_the_intrinsic_ratio": parked(
            "square", x=0, y=0, content_width=100, content_height=100, border_height=100
        ),
        "auto_ratio_keeps_the_intrinsic_ratio": parked(
            "defer", x=0, y=0, content_width=100, content_height=50, border_height=50
        ),
        "missing_intrinsic_uses_the_specified_ratio": parked(
            "bare", x=0, y=0, content_width=80, content_height=80, border_height=80
        ),
        "specified_height_stays_specified": parked(
            "specified", x=0, y=0, content_width=100, content_height=40, border_height=40
        ),
        "maximum_clamps_only_the_automatic_axis": parked(
            "capped", x=0, y=0, content_width=100, content_height=40, border_height=40
        ),
        "both_automatic_axes_keep_the_intrinsic_rectangle": parked(
            "both_auto", x=0, y=0, content_width=400, content_height=200, border_height=200
        ),
        "definite_insets_do_not_stretch_the_ratio": cases["insets"].get("outcome") == "placed"
        and _near(subject, x=0, y=0, content_width=100, content_height=100, border_height=100)
        and nxt is not None
        and nxt.get("y") == 0
        and host is not None
        and host.get("content_height") == 80,
        "fixed_image_uses_the_same_ratio": parked(
            "fixed", x=3, y=4, content_width=100, content_height=100, border_height=100
        ),
        "vertical_writing_mode_stays_rejected": cases["vertical"].get("outcome") == "invalid"
        and cases["vertical"].get("reason") == "replaced writing mode is unsupported",
        "border_box_without_chrome_keeps_the_square": parked(
            "border_box", x=0, y=0, content_width=100, content_height=100, border_height=100
        ),
        "in_flow_block_still_uses_the_ratio": cases["flow"].get("outcome") == "placed"
        and _near(flow_subject, x=0, y=0, content_width=100, content_height=100, border_height=100)
        and flow_next is not None
        and flow_next.get("y") == 100,
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
