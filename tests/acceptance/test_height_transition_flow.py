"""Retarget a CSS height transition inside normal flow.

A marginless page specifies 20px on the subject. Reversing that running
transition toward 20px at 500ms shortens the return, so 750ms uses 40px
and the next sibling starts there. A fresh target of 0px uses 45px.
The start sample stays at 20px, and the completed sample uses 100px.
The same retargets without transition-property keep 20px.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json

_PAGE = '<div id="page"><div id="box"></div><div id="next"></div></div>'
_RESET = "#page, #box, #next { margin: 0px; }\n#next { height: 8px; }\n"
_LIVE = (
    _RESET
    + "#box { height: 20px; transition-property: height; transition-duration: 1000ms; "
    + "transition-timing-function: linear; transition-delay: 0s; }\n"
)
_PLAIN = _RESET + "#box { height: 20px; }\n"
_BROKEN = (
    _RESET
    + "#box { height: 20px; transition-property: height; transition-duration: fast; }\n"
)
_FLOAT = (
    _RESET
    + "#box { float: left; width: 20px; height: 20px; transition-property: height; "
    + "transition-duration: 1000ms; transition-timing-function: linear; }\n"
)
_VERTICAL = (
    _RESET
    + "#box { writing-mode: vertical-rl; width: 20px; height: 20px; "
    + "transition-property: height; transition-duration: 1000ms; "
    + "transition-timing-function: linear; }\n"
)
_REVERSE = (
    {"time_ms": 0, "value": "100px"},
    {"time_ms": 500, "value": "20px"},
)
_FRESH = (
    {"time_ms": 0, "value": "100px"},
    {"time_ms": 500, "value": "0px"},
)
_FORWARD = ({"time_ms": 0, "value": "100px"},)


def _layout(function, stylesheet: str, **kwargs: object) -> dict[str, object]:
    try:
        placed = function(_PAGE, stylesheet, viewport_width=200, **kwargs)
    except TypeError as exc:
        return {"outcome": "invalid", "reason": str(exc), "boxes": None}
    except Exception as exc:  # noqa: BLE001 - a raised layout is an unmet outcome
        return {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}", "boxes": None}
    if not isinstance(placed, dict):
        return {"outcome": "error", "reason": "layout is invalid", "boxes": None}
    return placed


def _changes(events: tuple[dict[str, object], ...]) -> dict[str, list[dict[str, object]]]:
    return {"box": [dict(item) for item in events]}


def _point(result: dict[str, object], ident: str) -> dict[str, object] | None:
    boxes = result.get("boxes")
    if not isinstance(boxes, list):
        return None
    for item in boxes:
        if isinstance(item, dict) and item.get("id") == ident:
            return {"y": item.get("y"), "border_height": item.get("border_height")}
    return None


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_normal_flow import layout_normal_flow
    except Exception as exc:  # noqa: BLE001 - baseline without layout still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    reversed_run = _layout(
        layout_normal_flow,
        _LIVE,
        transition_sample_ms=750,
        transition_changes=_changes(_REVERSE),
    )
    fresh = _layout(
        layout_normal_flow,
        _LIVE,
        transition_sample_ms=750,
        transition_changes=_changes(_FRESH),
    )
    started = _layout(
        layout_normal_flow,
        _LIVE,
        transition_sample_ms=0,
        transition_changes=_changes(_FORWARD),
    )
    finished = _layout(
        layout_normal_flow,
        _LIVE,
        transition_sample_ms=1000,
        transition_changes=_changes(_FORWARD),
    )
    plain = _layout(
        layout_normal_flow,
        _PLAIN,
        transition_sample_ms=750,
        transition_changes=_changes(_REVERSE),
    )
    broken = _layout(
        layout_normal_flow,
        _BROKEN,
        transition_sample_ms=750,
        transition_changes=_changes(_FORWARD),
    )
    floated = _layout(
        layout_normal_flow,
        _FLOAT,
        transition_sample_ms=750,
        transition_changes=_changes(_FORWARD),
    )
    vertical = _layout(
        layout_normal_flow,
        _VERTICAL,
        transition_sample_ms=750,
        transition_changes=_changes(_FORWARD),
    )
    observed: dict[str, object] = {
        "reversed": {
            "outcome": reversed_run.get("outcome"),
            "reason": reversed_run.get("reason"),
            "box": _point(reversed_run, "box"),
            "next": _point(reversed_run, "next"),
        },
        "fresh": {
            "outcome": fresh.get("outcome"),
            "box": _point(fresh, "box"),
            "next": _point(fresh, "next"),
        },
        "started": {
            "outcome": started.get("outcome"),
            "box": _point(started, "box"),
            "next": _point(started, "next"),
        },
        "finished": {
            "outcome": finished.get("outcome"),
            "box": _point(finished, "box"),
            "next": _point(finished, "next"),
        },
        "plain": {
            "outcome": plain.get("outcome"),
            "box": _point(plain, "box"),
            "next": _point(plain, "next"),
        },
        "broken": {"outcome": broken.get("outcome"), "reason": broken.get("reason")},
        "floated": {"outcome": floated.get("outcome"), "reason": floated.get("reason")},
        "vertical": {"outcome": vertical.get("outcome"), "reason": vertical.get("reason")},
    }
    checks = {
        "reversing_shortens_the_return": reversed_run.get("outcome") == "placed"
        and _point(reversed_run, "box") == {"y": 0, "border_height": 40}
        and _point(reversed_run, "next") == {"y": 40, "border_height": 8},
        "fresh_target_keeps_the_full_duration": fresh.get("outcome") == "placed"
        and _point(fresh, "box") == {"y": 0, "border_height": 45}
        and _point(fresh, "next") == {"y": 45, "border_height": 8},
        "sample_at_the_start_keeps_the_specified_height": started.get("outcome") == "placed"
        and _point(started, "box") == {"y": 0, "border_height": 20}
        and _point(started, "next") == {"y": 20, "border_height": 8},
        "completed_sample_uses_the_target_height": finished.get("outcome") == "placed"
        and _point(finished, "box") == {"y": 0, "border_height": 100}
        and _point(finished, "next") == {"y": 100, "border_height": 8},
        "missing_property_keeps_the_specified_height": plain.get("outcome") == "placed"
        and _point(plain, "box") == {"y": 0, "border_height": 20}
        and _point(plain, "next") == {"y": 20, "border_height": 8},
        "unparsable_duration_is_invalid": broken.get("outcome") == "invalid"
        and broken.get("reason") == "height transition is invalid",
        "float_is_rejected": floated.get("outcome") == "invalid"
        and floated.get("reason") == "height transition is unsupported",
        "vertical_writing_mode_is_rejected": vertical.get("outcome") == "invalid"
        and vertical.get("reason") == "height transition is unsupported",
    }
    observed["checks"] = checks
    return all(checks.values()), observed


def main() -> int:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
