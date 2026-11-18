"""CSS writing-mode edges and orthogonal flow sizes.

horizontal-tb ltr starts the block on the top and the inline on the left.
vertical-rl ltr starts the block on the right and the inline on the top.
vertical-lr ltr starts the block on the left and keeps line-over on the right.
sideways-lr ltr starts the inline on the bottom, line-over on the left, and
line-left on the bottom. sideways-rl rtl matches vertical-rl rtl. Upright
forces vertical-rl rtl to used direction ltr, and leaves horizontal-tb rtl
on rtl.

vertical-rl inside vertical-lr is parallel, so a 50% block size of containing
block size 80 is 40. The same percentage of vertical-rl inside horizontal-tb
is 100. A parallel automatic inline size stretches to 200 even when wraps is
true and the max-content inline size is 30. An orthogonal child that does not
wrap keeps max-content inline 50 and max-content block 30. Wrapping shrinks
min-content 20 and max-content 150 to 80, and min-content 100 and max-content
150 to 100. An indefinite containing block size with fallback constraint 60
shrinks a wrapping inline size to 60. A parallel 50% block size with no
containing block size uses max-content block 30. An orthogonal 50% inline
size with no containing block size is indefinite. An unknown mode, a negative
length, and a boolean size are invalid.

Prints JSON with boolean passed and nonempty observed. Exit 0 either way.
"""

from __future__ import annotations

import json


def _close(got: object, expected: float | None) -> bool:
    if expected is None:
        return got is None
    if isinstance(got, bool) or not isinstance(got, (int, float)):
        return False
    return abs(float(got) - expected) <= 1e-6


def _edges(result: object, **expected: object) -> bool:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return False
    return all(result.get(key) == value for key, value in expected.items())


def _invalid(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("block_start") is None
        and result.get("inline_start") is None
        and result.get("inline_size") is None
        and result.get("block_size") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_writing_mode import resolve_flow_size, resolve_writing_mode
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def mode(name: str, *args: object, **kwargs: object) -> dict[str, object]:
        try:
            result = resolve_writing_mode(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    def flow(name: str, child: object, containing: object) -> dict[str, object]:
        try:
            result = resolve_flow_size(child, containing)
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    horizontal = mode("horizontal_ltr", "horizontal-tb", "ltr")
    checks.append(
        _edges(
            horizontal,
            writing_mode="horizontal-tb",
            direction="ltr",
            horizontal=True,
            block_size_axis="height",
            inline_size_axis="width",
            block_start="top",
            inline_start="left",
            over="top",
            line_left="left",
        )
    )

    vertical = mode("vertical_rl_ltr", "vertical-rl")
    checks.append(
        _edges(
            vertical,
            direction="ltr",
            horizontal=False,
            block_size_axis="width",
            inline_size_axis="height",
            block_start="right",
            block_end="left",
            inline_start="top",
            inline_end="bottom",
            over="right",
            line_left="top",
        )
    )

    mongolian = mode("vertical_lr_ltr", "vertical-lr", "ltr")
    checks.append(
        _edges(
            mongolian,
            block_start="left",
            block_end="right",
            inline_start="top",
            over="right",
            under="left",
            line_left="top",
            line_right="bottom",
        )
    )

    sideways = mode("sideways_lr_ltr", "sideways-lr", "ltr")
    checks.append(
        _edges(
            sideways,
            block_start="left",
            inline_start="bottom",
            inline_end="top",
            over="left",
            under="right",
            line_left="bottom",
            line_right="top",
        )
    )

    sideways_rl = mode("sideways_rl_rtl", "sideways-rl", "rtl")
    vertical_rtl = mode("vertical_rl_rtl", "vertical-rl", "rtl")
    checks.append(
        _edges(
            sideways_rl,
            block_start="right",
            inline_start="bottom",
            inline_end="top",
            over="right",
            line_left="top",
        )
    )
    checks.append(
        all(
            sideways_rl.get(key) == vertical_rtl.get(key)
            for key in ("block_start", "inline_start", "inline_end", "over", "line_left", "line_right")
        )
    )

    upright = mode("upright_forces_ltr", "vertical-rl", "rtl", text_orientation="upright")
    checks.append(
        _edges(upright, direction="ltr", specified_direction="rtl", inline_start="top", line_left="top")
    )
    flat = mode("upright_keeps_horizontal_rtl", "horizontal-tb", "rtl", text_orientation="upright")
    checks.append(_edges(flat, direction="rtl", specified_direction="rtl", inline_start="right", line_left="left"))

    parent = {"writing_mode": "vertical-lr", "inline_size": 200, "block_size": 80}
    parallel = flow(
        "parallel_vertical_percentage",
        {"writing_mode": "vertical-rl", "block_size": "50%", "inline_size": "auto"},
        parent,
    )
    checks.append(
        isinstance(parallel, dict)
        and parallel.get("outcome") == "resolved"
        and parallel.get("orthogonal") is False
        and _close(parallel.get("block_size"), 40)
        and parallel.get("block_size_kind") == "percentage"
        and _close(parallel.get("inline_size"), 200)
        and parallel.get("inline_size_kind") == "stretch"
        and _close(parallel.get("width"), 40)
        and _close(parallel.get("height"), 200)
    )

    orthogonal = flow(
        "orthogonal_percentage_and_max_content",
        {
            "writing_mode": "vertical-rl",
            "block_size": "50%",
            "inline_size": "auto",
            "wraps": False,
            "max_content_inline": 50,
            "max_content_block": 30,
        },
        {"writing_mode": "horizontal-tb", "inline_size": 200, "block_size": 80},
    )
    checks.append(
        isinstance(orthogonal, dict)
        and orthogonal.get("outcome") == "resolved"
        and orthogonal.get("orthogonal") is True
        and _close(orthogonal.get("available_block"), 200)
        and _close(orthogonal.get("available_inline"), 80)
        and _close(orthogonal.get("block_size"), 100)
        and orthogonal.get("block_size_kind") == "percentage"
        and _close(orthogonal.get("inline_size"), 50)
        and orthogonal.get("inline_size_kind") == "max-content"
        and _close(orthogonal.get("width"), 100)
        and _close(orthogonal.get("height"), 50)
    )

    held = flow(
        "parallel_wrap_still_stretches",
        {
            "writing_mode": "horizontal-tb",
            "inline_size": "auto",
            "block_size": "auto",
            "wraps": True,
            "min_content_inline": 10,
            "max_content_inline": 30,
            "max_content_block": 15,
        },
        {"writing_mode": "horizontal-tb", "inline_size": 200, "block_size": 80},
    )
    checks.append(
        isinstance(held, dict)
        and held.get("outcome") == "resolved"
        and held.get("orthogonal") is False
        and _close(held.get("inline_size"), 200)
        and held.get("inline_size_kind") == "stretch"
        and _close(held.get("block_size"), 15)
        and _close(held.get("width"), 200)
        and _close(held.get("height"), 15)
    )

    shrink = flow(
        "orthogonal_wrap_shrinks_to_measure",
        {
            "writing_mode": "vertical-rl",
            "inline_size": "auto",
            "block_size": "auto",
            "wraps": True,
            "min_content_inline": 20,
            "max_content_inline": 150,
            "max_content_block": 30,
        },
        {"writing_mode": "horizontal-tb", "inline_size": 200, "block_size": 80},
    )
    checks.append(
        isinstance(shrink, dict)
        and shrink.get("outcome") == "resolved"
        and shrink.get("inline_size_kind") == "shrink-to-fit"
        and _close(shrink.get("inline_size"), 80)
        and _close(shrink.get("block_size"), 30)
        and shrink.get("block_size_kind") == "max-content"
    )

    floor = flow(
        "orthogonal_wrap_floors_at_min_content",
        {
            "writing_mode": "vertical-rl",
            "wraps": True,
            "min_content_inline": 100,
            "max_content_inline": 150,
            "max_content_block": 30,
        },
        {"writing_mode": "horizontal-tb", "inline_size": 200, "block_size": 80},
    )
    checks.append(
        isinstance(floor, dict)
        and floor.get("inline_size_kind") == "shrink-to-fit"
        and _close(floor.get("inline_size"), 100)
        and _close(floor.get("block_size"), 30)
    )

    fallback = flow(
        "orthogonal_wrap_uses_fallback_constraint",
        {
            "writing_mode": "vertical-rl",
            "wraps": True,
            "min_content_inline": 10,
            "max_content_inline": 100,
            "max_content_block": 25,
        },
        {"writing_mode": "horizontal-tb", "inline_size": 200, "constraint": 60},
    )
    checks.append(
        isinstance(fallback, dict)
        and fallback.get("outcome") == "resolved"
        and fallback.get("available_inline") is None
        and fallback.get("inline_size_kind") == "shrink-to-fit"
        and _close(fallback.get("inline_size"), 60)
        and _close(fallback.get("block_size"), 25)
        and _close(fallback.get("available_block"), 200)
    )

    automatic = flow(
        "parallel_indefinite_block_percentage_is_content",
        {
            "writing_mode": "horizontal-tb",
            "block_size": "50%",
            "inline_size": 12,
            "max_content_block": 30,
        },
        {"writing_mode": "horizontal-tb", "inline_size": 200},
    )
    checks.append(
        isinstance(automatic, dict)
        and automatic.get("outcome") == "resolved"
        and automatic.get("orthogonal") is False
        and automatic.get("block_size_kind") == "max-content"
        and _close(automatic.get("block_size"), 30)
        and _close(automatic.get("inline_size"), 12)
        and _close(automatic.get("height"), 30)
    )

    missing = flow(
        "orthogonal_indefinite_inline_percentage",
        {"writing_mode": "vertical-rl", "inline_size": "50%", "block_size": 10},
        {"writing_mode": "horizontal-tb", "inline_size": 200},
    )
    checks.append(
        isinstance(missing, dict)
        and missing.get("outcome") == "indefinite"
        and missing.get("orthogonal") is True
        and missing.get("inline_size") is None
        and missing.get("inline_size_kind") == "indefinite"
        and _close(missing.get("block_size"), 10)
        and missing.get("block_start") == "right"
        and _close(missing.get("width"), 10)
        and missing.get("height") is None
    )

    checks.append(_invalid(mode("unknown_mode", "diagonal")))
    checks.append(_invalid(flow("negative_length", {"writing_mode": "horizontal-tb", "inline_size": -1}, parent)))
    checks.append(_invalid(flow("boolean_size", {"writing_mode": "horizontal-tb", "block_size": True}, parent)))

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
