"""Travel a point along a CSS offset path by arc length.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the offset path still exits 0.
"""

from __future__ import annotations

import json
import math


def _near(found: object, expected: float, tol: float = 1e-6) -> bool:
    return isinstance(found, (int, float)) and not isinstance(found, bool) and abs(float(found) - expected) <= tol


def _angle(found: object, expected: float) -> bool:
    if not isinstance(found, (int, float)) or isinstance(found, bool):
        return False
    delta = (float(found) - expected) % 360.0
    if delta > 180.0:
        delta = 360.0 - delta
    return delta <= 1e-6


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_offset_path import travel_offset_path
    except Exception as exc:  # noqa: BLE001 - baseline without the path still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def place(name: str, result: object) -> dict[str, object]:
        payload = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = payload
        return payload

    def resolved(
        name: str,
        result: object,
        x: float,
        y: float,
        tangent: float | None,
        *,
        angle: float | None = None,
        length: float | None = None,
        closed: bool | None = None,
        tol: float = 1e-6,
    ) -> None:
        row = place(name, result)
        ok = row.get("outcome") == "resolved" and _near(row.get("x"), x, tol) and _near(row.get("y"), y, tol)
        if tangent is None:
            ok = ok and row.get("tangent") is None
        else:
            ok = ok and _angle(row.get("tangent"), tangent)
        if angle is not None:
            ok = ok and _angle(row.get("angle"), angle)
        if length is not None:
            ok = ok and _near(row.get("length"), length, tol)
        if closed is not None:
            ok = ok and row.get("closed") is closed
        ok = ok and row.get("reason") == ""
        checks.append(ok)

    def rejected(name: str, result: object, reason: str) -> None:
        row = place(name, result)
        checks.append(
            row.get("outcome") == "invalid"
            and row.get("x") is None
            and row.get("y") is None
            and row.get("angle") is None
            and row.get("reason") == reason
        )

    circle = "circle(100px at 0px 0px)"
    resolved("circle_0", travel_offset_path(circle, "0%"), 100, 0, 90, angle=90, length=math.tau * 100, closed=True)
    resolved("circle_25", travel_offset_path(circle, "25%"), 0, 100, 180, angle=180, closed=True)
    resolved("circle_50", travel_offset_path(circle, "50%"), -100, 0, 270, closed=True)
    resolved("circle_75", travel_offset_path(circle, "75%"), 0, -100, 0, closed=True)
    resolved("circle_100", travel_offset_path(circle, "100%"), 100, 0, 90, closed=True)
    resolved("circle_125", travel_offset_path(circle, "125%"), 0, 100, 180, closed=True)
    resolved("circle_neg", travel_offset_path(circle, "-75%"), 0, 100, 180, closed=True)
    resolved(
        "circle_reverse",
        travel_offset_path(circle, "0%", rotate="reverse"),
        100,
        0,
        90,
        angle=270,
        closed=True,
    )
    resolved(
        "circle_fixed",
        travel_offset_path(circle, "0%", rotate="45deg"),
        100,
        0,
        90,
        angle=45,
        closed=True,
    )

    resolved(
        "ellipse_25",
        travel_offset_path("ellipse(100px 40px at 0px 0px)", "25%"),
        0,
        40,
        180,
        closed=True,
        tol=1e-4,
    )
    resolved(
        "ellipse_50",
        travel_offset_path("ellipse(100px 40px at 0px 0px)", "50%"),
        -100,
        0,
        270,
        closed=True,
        tol=1e-4,
    )

    horizontal = 'path("M 0 0 L 100 0")'
    resolved("line_25", travel_offset_path(horizontal, "25px"), 25, 0, 0, angle=0, length=100, closed=False)
    resolved("line_end", travel_offset_path(horizontal, "150px"), 100, 0, 0, closed=False)
    resolved("line_before", travel_offset_path(horizontal, "-10px"), 0, 0, 0, closed=False)
    resolved("line_100", travel_offset_path(horizontal, "100%"), 100, 0, 0, closed=False)
    resolved("down_50", travel_offset_path('path("M 0 0 L 0 100")', "50%"), 0, 50, 90, closed=False)
    resolved(
        "line_reverse",
        travel_offset_path(horizontal, "25px", rotate="reverse"),
        25,
        0,
        0,
        angle=180,
    )
    resolved(
        "line_turn",
        travel_offset_path(horizontal, "0px", rotate="0.25turn"),
        0,
        0,
        0,
        angle=90,
    )
    resolved("zero", travel_offset_path('path("M 10 20")', "50px"), 10, 20, None, angle=0, length=0, closed=False)
    resolved(
        "cubic_mid",
        travel_offset_path('path("M 0 0 C 30 0 70 0 100 0")', "50%"),
        50,
        0,
        0,
        tol=1e-4,
    )
    resolved(
        "cubic_leave",
        travel_offset_path('path("M 0 0 C 0 100 100 100 100 0")', "0%"),
        0,
        0,
        90,
    )
    resolved(
        "cubic_arrive",
        travel_offset_path('path("M 0 0 C 0 100 100 100 100 0")', "100%"),
        100,
        0,
        270,
    )
    corner = math.degrees(math.atan2(40, -30)) % 360.0
    resolved("triangle_corner", travel_offset_path('path("M 0 0 L 30 0 L 0 40 Z")', "30px"), 30, 0, corner, closed=True)
    resolved("subpath", travel_offset_path('path("M 0 0 H 100 M 0 50 H 100")', "150px"), 50, 50, 0, length=200, closed=False)
    resolved("relative", travel_offset_path('path("m 10 20 h 30 v 40")', "50px"), 40, 40, 90, length=70, closed=False)
    resolved("inset_corner", travel_offset_path("inset(0px)", "100px", box_width=100, box_height=40), 100, 0, 90, closed=True)
    resolved("xywh_start", travel_offset_path("xywh(10px 20px 30px 40px)", "0px"), 10, 20, 0, closed=True)
    resolved(
        "smooth_mid",
        travel_offset_path('path("M 0 0 C 0 0 100 0 100 0 S 200 0 200 0")', "50%"),
        100,
        0,
        0,
        length=200,
        tol=1e-4,
    )
    resolved("quad_mid", travel_offset_path('path("M 0 0 Q 50 0 100 0")', "50%"), 50, 0, 0, tol=1e-4)
    resolved(
        "evenodd",
        travel_offset_path('path(evenodd, "M 0 0 L 80 0")', "50%"),
        40,
        0,
        0,
        length=80,
        closed=False,
    )
    resolved("exponent", travel_offset_path('path("M 0 0 L 1e2 0")', "50%"), 50, 0, 0, length=100, closed=False)
    resolved("grad", travel_offset_path(horizontal, "0px", rotate="100grad"), 0, 0, 0, angle=90)

    box = {"box_width": 200, "box_height": 100}
    resolved(
        "ray_up",
        travel_offset_path("ray(0deg closest-side at 20px 10px)", "100%", **box),
        20,
        0,
        270,
        angle=270,
        length=10,
        closed=False,
    )
    resolved(
        "ray_right_same_length",
        travel_offset_path("ray(90deg closest-side at 20px 10px)", "100%", **box),
        30,
        10,
        0,
        length=10,
        closed=False,
    )
    resolved(
        "ray_sides",
        travel_offset_path("ray(90deg sides at 20px 10px)", "100%", **box),
        200,
        10,
        0,
        length=180,
        closed=False,
    )
    resolved(
        "ray_backward",
        travel_offset_path("ray(0deg closest-side at 20px 10px)", "-100%", **box),
        20,
        20,
        270,
        length=10,
        closed=False,
    )
    resolved(
        "ray_past",
        travel_offset_path("ray(90deg closest-side at 20px 10px)", "200%", **box),
        40,
        10,
        0,
        length=10,
        closed=False,
    )
    resolved(
        "ray_turn",
        travel_offset_path("ray(0.25turn closest-side at 20px 10px)", "100%", **box),
        30,
        10,
        0,
        length=10,
    )

    rejected("arc", travel_offset_path('path("M 0 0 A 10 10 0 0 1 20 0")', "0px"), "arc")
    rejected("round", travel_offset_path("inset(0px round 10px)", "0px", box_width=100, box_height=40), "round")
    rejected("contain", travel_offset_path("ray(0deg contain)", "0px", box_width=100, box_height=100), "contain")
    rejected("distance", travel_offset_path(horizontal, True), "distance")

    passed = all(checks) and bool(checks)
    if not passed:
        observed["failed"] = [name for name, ok in zip(observed, checks, strict=False) if not ok]
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
