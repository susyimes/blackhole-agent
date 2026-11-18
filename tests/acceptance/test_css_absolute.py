"""Place one absolutely positioned non-replaced box.

Both insets stretch an automatic size. An over-constrained horizontal axis
drops the end inset for ltr and the start inset for rtl. Equal automatic
margins split a positive remainder; a negative horizontal remainder zeros
the start margin, while a negative vertical remainder stays split.
Shrink-to-fit clamps the available gap between min-content and max-content.
A max size that loses a stretch re-solves the opposite inset. An automatic
containing-block height turns percentage height and insets into the static
position and the content height. A percentage vertical margin uses the
containing-block width.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the placer still exits 0.
"""

from __future__ import annotations

import json
import sys

_KEYS = (
    "outcome",
    "reason",
    "left",
    "right",
    "width",
    "top",
    "bottom",
    "height",
    "margin_left",
    "margin_right",
    "margin_top",
    "margin_bottom",
    "padding_top",
    "x",
    "y",
    "border_box_width",
    "border_box_height",
    "containing_height",
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_absolute import place_absolute
    except Exception as exc:  # noqa: BLE001 - baseline without the placer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = place_absolute(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised place is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = {key: packed.get(key) for key in _KEYS}
        return observed[name]

    def expect(name: str, fields: dict[str, object], **kwargs: object) -> None:
        got = take(name, **kwargs)
        checks.append(all(got.get(key) == value for key, value in fields.items()))

    expect(
        "stretch",
        {"outcome": "placed", "left": 0, "right": 0, "width": 200, "margin_left": 0, "margin_right": 0},
        containing_width=200,
        left=0,
        right=0,
        margin_left="auto",
        margin_right="auto",
    )
    expect(
        "equal_margins",
        {"outcome": "placed", "left": 10, "right": 30, "width": 100, "margin_left": 30, "margin_right": 30},
        containing_width=200,
        left=10,
        right=30,
        width=100,
        margin_left="auto",
        margin_right="auto",
    )
    expect(
        "negative_margins_ltr",
        {"outcome": "placed", "margin_left": 0, "margin_right": -50, "width": 250, "left": 0, "right": 0},
        containing_width=200,
        left=0,
        right=0,
        width=250,
        margin_left="auto",
        margin_right="auto",
    )
    expect(
        "negative_margins_rtl",
        {"outcome": "placed", "margin_left": -50, "margin_right": 0, "width": 250, "left": 0, "right": 0},
        containing_width=200,
        left=0,
        right=0,
        width=250,
        margin_left="auto",
        margin_right="auto",
        direction="rtl",
    )
    expect(
        "over_ltr",
        {"outcome": "placed", "left": 10, "right": 90, "width": 100},
        containing_width=200,
        left=10,
        right=10,
        width=100,
    )
    expect(
        "over_rtl",
        {"outcome": "placed", "left": 90, "right": 10, "width": 100},
        containing_width=200,
        left=10,
        right=10,
        width=100,
        direction="RTL",
    )
    expect(
        "one_auto_margin",
        {"outcome": "placed", "margin_left": 90, "margin_right": 10, "width": 100, "left": 0, "right": 0},
        containing_width=200,
        left=0,
        right=0,
        width=100,
        margin_left="auto",
        margin_right=10,
    )
    expect(
        "shrink_under",
        {"outcome": "placed", "left": -20, "right": 80, "width": 40},
        containing_width=100,
        right=80,
        min_content=40,
        max_content=90,
    )
    expect(
        "shrink_preferred",
        {"outcome": "placed", "left": 110, "right": 10, "width": 80},
        containing_width=200,
        right=10,
        min_content=30,
        max_content=80,
    )
    expect(
        "shrink_available",
        {"outcome": "placed", "left": 10, "width": 85, "right": 0, "margin_left": 5, "margin_right": 0},
        containing_width=100,
        left=10,
        margin_left=5,
        min_content=0,
        max_content=1000,
    )
    expect(
        "static_ltr",
        {"outcome": "placed", "left": 12, "right": 238, "width": 50},
        containing_width=300,
        width=50,
        static_left=12,
    )
    expect(
        "static_rtl",
        {"outcome": "placed", "left": 235, "right": 15, "width": 50},
        containing_width=300,
        width=50,
        direction="rtl",
        static_right=15,
    )
    expect(
        "static_margin",
        {"outcome": "placed", "left": 0, "right": 140, "width": 50, "margin_left": 10, "x": 10},
        containing_width=200,
        width=50,
        margin_left=10,
        static_left=0,
    )
    expect(
        "all_auto_shrink",
        {"outcome": "placed", "left": 5, "right": 55, "width": 40, "margin_left": 0, "margin_right": 0},
        containing_width=100,
        margin_left="auto",
        margin_right="auto",
        static_left=5,
        min_content=10,
        max_content=40,
    )
    expect(
        "max_resolves_inset",
        {"outcome": "placed", "left": 0, "right": 120, "width": 80},
        containing_width=200,
        left=0,
        right=0,
        max_width=80,
    )
    expect(
        "min_wins_over_max",
        {"outcome": "placed", "left": 0, "right": 120, "width": 80},
        containing_width=200,
        left=0,
        right=0,
        min_width=80,
        max_width=50,
    )
    expect(
        "stretch_floor",
        {"outcome": "placed", "left": 150, "right": 150, "width": 0},
        containing_width=200,
        left=150,
        right=150,
    )
    expect(
        "stretch_padding",
        {"outcome": "placed", "left": 0, "right": 0, "width": 175},
        containing_width=200,
        left=0,
        right=0,
        padding_left=10,
        padding_right=15,
    )
    expect(
        "border_box",
        {"outcome": "placed", "width": 70, "right": 100, "left": 0, "border_box_width": 100},
        containing_width=200,
        left=0,
        width=100,
        padding_left=10,
        padding_right=10,
        border_left=5,
        border_right=5,
        box_sizing="border-box",
    )
    expect(
        "border_box_grows",
        {"outcome": "placed", "width": 0, "right": 170, "border_box_width": 30},
        containing_width=200,
        left=0,
        width=20,
        padding_left=10,
        padding_right=10,
        border_left=5,
        border_right=5,
        box_sizing="border-box",
    )
    expect(
        "vertical_stretch",
        {
            "outcome": "placed",
            "top": 0,
            "bottom": 0,
            "height": 100,
            "margin_top": 0,
            "margin_bottom": 0,
        },
        containing_width=50,
        containing_height=100,
        top=0,
        bottom=0,
        margin_top="auto",
        margin_bottom="auto",
    )
    expect(
        "vertical_negative_margins",
        {"outcome": "placed", "top": 0, "bottom": 0, "height": 150, "margin_top": -25, "margin_bottom": -25},
        containing_width=40,
        containing_height=100,
        top=0,
        bottom=0,
        height=150,
        margin_top="auto",
        margin_bottom="auto",
    )
    expect(
        "vertical_over",
        {"outcome": "placed", "top": 10, "bottom": 40, "height": 50},
        containing_width=40,
        containing_height=100,
        top=10,
        bottom=10,
        height=50,
    )
    expect(
        "max_height_resolves_bottom",
        {"outcome": "placed", "top": 0, "bottom": 60, "height": 40},
        containing_width=40,
        containing_height=100,
        top=0,
        bottom=0,
        max_height=40,
    )
    expect(
        "min_height_resolves_bottom",
        {"outcome": "placed", "top": 10, "bottom": 90, "height": 100},
        containing_width=40,
        containing_height=200,
        top=10,
        bottom=10,
        height=20,
        min_height=100,
    )
    expect(
        "indefinite_percent",
        {
            "outcome": "placed",
            "top": 7,
            "bottom": None,
            "height": 18,
            "containing_height": None,
            "margin_top": 0,
        },
        containing_width=200,
        top="10%",
        height="50%",
        bottom="10%",
        static_top=7,
        content_height=18,
        margin_top="auto",
    )
    expect(
        "definite_percent_drops_bottom",
        {"outcome": "placed", "top": 10, "height": 50, "bottom": 40},
        containing_width=200,
        containing_height=100,
        top="10%",
        height="50%",
        bottom="10%",
    )
    expect(
        "margin_top_uses_width",
        {"outcome": "placed", "margin_top": 20, "top": 0, "height": 20, "bottom": 60, "y": 20},
        containing_width=200,
        containing_height=100,
        margin_top="10%",
        top=0,
        height=20,
    )
    expect(
        "padding_top_uses_width",
        {"outcome": "placed", "padding_top": 20, "top": 0, "height": 20, "bottom": 60},
        containing_width=200,
        containing_height=100,
        padding_top="10%",
        top=0,
        height=20,
    )
    expect(
        "indefinite_max_percent",
        {"outcome": "placed", "height": 80, "top": 4, "bottom": None},
        containing_width=90,
        height="auto",
        max_height="10%",
        content_height=80,
        static_top=4,
    )
    expect(
        "indefinite_min_percent",
        {"outcome": "placed", "height": 10, "bottom": None},
        containing_width=90,
        min_height="50%",
        content_height=10,
    )
    expect(
        "indefinite_max_length",
        {"outcome": "placed", "height": 40, "top": 5, "bottom": None},
        containing_width=90,
        max_height=40,
        content_height=100,
        static_top=5,
    )
    expect(
        "indefinite_length_insets",
        {"outcome": "placed", "top": 8, "height": 20, "bottom": None},
        containing_width=90,
        top=8,
        height=20,
    )
    expect(
        "indefinite_min_length",
        {"outcome": "placed", "height": 15, "top": 0, "bottom": None},
        containing_width=90,
        top=0,
        min_height=15,
        content_height=10,
    )
    expect(
        "max_height_percent",
        {"outcome": "placed", "height": 30, "top": 0, "bottom": 70},
        containing_width=40,
        containing_height=100,
        top=0,
        bottom=0,
        max_height="30%",
    )
    expect(
        "border_box_height",
        {"outcome": "placed", "height": 30, "bottom": 50, "border_box_height": 50, "top": 0},
        containing_width=40,
        containing_height=100,
        top=0,
        height=50,
        padding_top=10,
        padding_bottom=10,
        box_sizing="border-box",
    )

    bad_width = take("bad_width", containing_width=-1)
    checks.append(bad_width.get("outcome") == "invalid" and bad_width.get("width") is None)
    bad_flow = take("bad_direction", containing_width=10, direction="sideways")
    checks.append(bad_flow.get("outcome") == "invalid" and bad_flow.get("width") is None)
    bad_bool = take("bad_bool", containing_width=10, width=True)
    checks.append(bad_bool.get("outcome") == "invalid" and bad_bool.get("width") is None)
    swapped = take("swapped_intrinsic", containing_width=10, min_content=8, max_content=3)
    checks.append(swapped.get("outcome") == "invalid" and swapped.get("width") is None)

    return all(checks), observed


def _emit(payload: dict[str, object]) -> None:
    """Write one ASCII JSON line. Isolated Windows runs use a GBK stdout."""

    try:
        line = json.dumps(payload, ensure_ascii=True)
    except Exception as exc:  # noqa: BLE001 - the probe must still emit a record
        line = json.dumps({"passed": False, "observed": {"error": f"{type(exc).__name__}: {exc}"}})
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(line.encode("ascii") + b"\n")
        buffer.flush()
        return
    print(line)


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    if not observed:
        observed = {"error": "empty observation"}
    _emit({"passed": bool(passed), "observed": observed})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
