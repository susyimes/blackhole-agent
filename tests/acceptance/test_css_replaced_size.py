"""Size a replaced box from its intrinsic width, height, and ratio.

Automatic axes use the intrinsic size, or 300 by 150 when nothing intrinsic
is known. One automatic axis follows a definite axis through the ratio.
Specified axes win. The ratio table transfers a min or max violation only
while both axes stay automatic. A block then centers automatic margins; an
inline box keeps those margins at zero.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the sizer still exits 0.
"""

from __future__ import annotations

import json

_KEYS = (
    "outcome",
    "reason",
    "width",
    "height",
    "margin_left",
    "margin_right",
    "margin_top",
    "margin_bottom",
    "layout",
)


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_replaced import used_replaced_size
    except Exception as exc:  # noqa: BLE001 - baseline without the sizer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, **kwargs: object) -> dict[str, object]:
        kwargs.setdefault("containing_width", 800)
        try:
            result = used_replaced_size(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised size is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = {key: packed.get(key) for key in _KEYS}
        return observed[name]

    def expect(name: str, fields: dict[str, object], **kwargs: object) -> None:
        got = take(name, **kwargs)
        checks.append(all(got.get(key) == value for key, value in fields.items()))

    expect(
        "intrinsic",
        {"outcome": "sized", "width": 400, "height": 200},
        intrinsic_width=400,
        intrinsic_height=200,
    )
    expect(
        "width_drives_ratio",
        {"outcome": "sized", "width": 100, "height": 50},
        width=100,
        intrinsic_ratio=2,
    )
    expect(
        "height_drives_ratio",
        {"outcome": "sized", "width": 200, "height": 100},
        height=100,
        intrinsic_width=400,
        intrinsic_ratio=2,
    )
    expect(
        "specified_wins",
        {"outcome": "sized", "width": 100, "height": 80},
        width=100,
        height=80,
        intrinsic_width=400,
        intrinsic_height=200,
    )
    expect(
        "fallback",
        {"outcome": "sized", "width": 300, "height": 150},
    )
    expect(
        "narrow_device",
        {"outcome": "sized", "width": 200, "height": 100},
        device_width=200,
    )
    expect(
        "max_width_keeps_ratio",
        {"outcome": "sized", "width": 100, "height": 50},
        intrinsic_width=400,
        intrinsic_height=200,
        max_width=100,
    )
    expect(
        "both_max_tighter_height",
        {"outcome": "sized", "width": 100, "height": 50},
        intrinsic_width=400,
        intrinsic_height=200,
        max_width=300,
        max_height=50,
    )
    expect(
        "min_width_and_max_height",
        {"outcome": "sized", "width": 200, "height": 50},
        intrinsic_width=100,
        intrinsic_height=100,
        min_width=200,
        max_height=50,
    )
    expect(
        "min_height_percent",
        {"outcome": "sized", "width": 200, "height": 100},
        containing_height=200,
        intrinsic_width=40,
        intrinsic_height=20,
        min_height="50%",
    )
    expect(
        "block_margins",
        {"outcome": "sized", "width": 100, "height": 50, "margin_left": 150, "margin_right": 150, "layout": "block"},
        containing_width=400,
        width=100,
        intrinsic_ratio=2,
        margin_left="auto",
        margin_right="auto",
        layout="block",
    )
    expect(
        "inline_margins",
        {
            "outcome": "sized",
            "width": 100,
            "height": 50,
            "margin_left": 0,
            "margin_right": 0,
            "margin_top": 0,
            "layout": "inline",
        },
        containing_width=400,
        width=100,
        intrinsic_ratio=2,
        margin_left="auto",
        margin_right="auto",
        margin_top="auto",
        layout="inline",
    )
    expect(
        "percent_height_indefinite",
        {"outcome": "sized", "width": 400, "height": 200},
        containing_height="auto",
        height="50%",
        intrinsic_width=400,
        intrinsic_height=200,
    )
    expect(
        "fallback_max_width_keeps_height",
        {"outcome": "sized", "width": 100, "height": 150},
        max_width=100,
    )
    expect(
        "max_height_breaks_ratio",
        {"outcome": "sized", "width": 100, "height": 20},
        width=100,
        intrinsic_ratio=2,
        max_height=20,
    )
    expect(
        "percent_width",
        {"outcome": "sized", "width": 100, "height": 50},
        containing_width=200,
        width="50%",
        intrinsic_ratio=2,
    )
    expect(
        "float_margin",
        {"outcome": "sized", "width": 80, "height": 40, "margin_left": 0, "margin_right": 12, "layout": "float"},
        intrinsic_width=80,
        intrinsic_height=40,
        margin_left="auto",
        margin_right=12,
        layout="float",
    )

    bad_width = take("bad_width", containing_width=-1)
    checks.append(bad_width.get("outcome") == "invalid" and bad_width.get("width") is None)
    bad_ratio = take("bad_ratio", intrinsic_ratio=0)
    checks.append(bad_ratio.get("outcome") == "invalid" and bad_ratio.get("width") is None)
    bad_bool = take("bad_bool", width=True)
    checks.append(bad_bool.get("outcome") == "invalid" and bad_bool.get("width") is None)

    return all(checks), observed


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True))


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
