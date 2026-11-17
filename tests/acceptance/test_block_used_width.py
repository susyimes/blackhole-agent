"""Solve the used width of a non-replaced block in normal flow.

Auto width, auto margins, an over-constrained direction, border-box
underflow, min-width, and max-width each change the content box or a
margin. Padding that exceeds an auto width floors the content box and
leaves the specified margins alone.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the solver still exits 0.
"""

from __future__ import annotations

import json


def _close(got: object, expected: int | float) -> bool:
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - float(expected)) <= 1e-9


def _is(result: object, **expected: object) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "sized":
        return False
    for key, want in expected.items():
        if isinstance(want, bool) or not isinstance(want, (int, float)):
            if result.get(key) != want:
                return False
        elif not _close(result.get(key), want):
            return False
    return True


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_block_width import used_block_width
    except Exception as exc:  # noqa: BLE001 - baseline without the solver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, **kwargs: object) -> dict[str, object]:
        try:
            result = used_block_width(**kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    auto = keep(
        "auto_width",
        containing_block=400,
        width="auto",
        padding_left=10,
        padding_right=10,
        border_left=5,
        border_right=5,
    )
    checks.append(_is(auto, content=370, margin_left=0, margin_right=0, border_box=400, margin_box=400))

    centered = keep(
        "centered",
        containing_block=400,
        width=200,
        margin_left="auto",
        margin_right="auto",
    )
    checks.append(_is(centered, content=200, margin_left=100, margin_right=100, border_box=200))

    one_auto = keep(
        "one_auto_margin",
        containing_block=400,
        width=200,
        margin_left=50,
        margin_right="auto",
    )
    checks.append(_is(one_auto, content=200, margin_left=50, margin_right=150))

    ltr = keep(
        "overconstrained_ltr",
        containing_block=400,
        width=300,
        margin_left=80,
        margin_right=80,
        direction="ltr",
    )
    checks.append(_is(ltr, content=300, margin_left=80, margin_right=20))

    rtl = keep(
        "overconstrained_rtl",
        containing_block=400,
        width=300,
        margin_left=80,
        margin_right=80,
        direction="rtl",
    )
    checks.append(_is(rtl, content=300, margin_left=20, margin_right=80))

    border = keep(
        "border_box",
        containing_block=400,
        width=200,
        margin_left="auto",
        margin_right="auto",
        padding_left=10,
        padding_right=10,
        border_left=5,
        border_right=5,
        box_sizing="border-box",
    )
    checks.append(_is(border, content=170, margin_left=100, margin_right=100, border_box=200))

    underflow = keep(
        "border_box_underflow",
        containing_block=400,
        width=50,
        padding_left=40,
        padding_right=40,
        box_sizing="border-box",
    )
    checks.append(
        _is(underflow, content=0, margin_left=0, margin_right=320, border_box=80, margin_box=400)
    )

    underflow_auto = keep(
        "border_box_underflow_centered",
        containing_block=400,
        width=50,
        margin_left="auto",
        margin_right="auto",
        padding_left=40,
        padding_right=40,
        box_sizing="border-box",
    )
    checks.append(_is(underflow_auto, content=0, margin_left=160, margin_right=160, border_box=80))

    capped = keep(
        "max_width",
        containing_block=400,
        width="50%",
        margin_left="auto",
        margin_right="auto",
        max_width=100,
    )
    checks.append(_is(capped, content=100, margin_left=150, margin_right=150, border_box=100))

    overflow = keep(
        "overflow_zeros_auto_margins",
        containing_block=400,
        width=500,
        margin_left="auto",
        margin_right="auto",
    )
    checks.append(_is(overflow, content=500, margin_left=0, margin_right=-100, margin_box=400))

    floored = keep(
        "auto_width_floors",
        containing_block=100,
        width="auto",
        padding_left=60,
        padding_right=60,
    )
    checks.append(_is(floored, content=0, margin_left=0, margin_right=0, border_box=120, margin_box=120))

    restarted = keep(
        "min_wins_over_max",
        containing_block=400,
        width=400,
        margin_left="auto",
        margin_right="auto",
        min_width=120,
        max_width=80,
    )
    checks.append(_is(restarted, content=120, margin_left=140, margin_right=140))

    border_min = keep(
        "border_box_min",
        containing_block=400,
        width=50,
        margin_left="auto",
        margin_right="auto",
        padding_left=10,
        padding_right=10,
        box_sizing="border-box",
        min_width=100,
    )
    checks.append(_is(border_min, content=80, margin_left=150, margin_right=150, border_box=100))

    border_cap = keep(
        "border_box_max",
        containing_block=400,
        width=300,
        margin_left="auto",
        margin_right="auto",
        padding_left=10,
        padding_right=10,
        box_sizing="border-box",
        max_width=100,
    )
    checks.append(_is(border_cap, content=80, margin_left=150, margin_right=150, border_box=100))

    percent_pad = keep(
        "percentage_padding",
        containing_block=400,
        width="auto",
        padding_left="10%",
    )
    checks.append(_is(percent_pad, content=360, padding_left=40, margin_left=0, margin_right=0))

    percent_margin = keep(
        "percentage_margin",
        containing_block=400,
        width=200,
        margin_left="10%",
        margin_right="auto",
    )
    checks.append(_is(percent_margin, content=200, margin_left=40, margin_right=160))

    half = keep(
        "half_pixel_margins",
        containing_block=401,
        width=200,
        margin_left="auto",
        margin_right="auto",
    )
    checks.append(_is(half, content=200, margin_left=100.5, margin_right=100.5, margin_box=401))

    negative_min = keep(
        "negative_min_is_zero",
        containing_block=100,
        width="auto",
        min_width=-10,
    )
    checks.append(_is(negative_min, content=100, margin_left=0, margin_right=0))

    rejected = keep(name="negative_padding", containing_block=400, padding_left=-1)
    checks.append(rejected.get("outcome") == "invalid" and rejected.get("content") is None)

    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - the probe must exit 0 either way
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
