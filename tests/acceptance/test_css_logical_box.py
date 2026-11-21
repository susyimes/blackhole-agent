"""Map logical box edges through writing mode and solve the inline size.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without logical box resolution still exits 0.
"""

from __future__ import annotations

import json


def _near(found: object, expected: float) -> bool:
    return isinstance(found, (int, float)) and not isinstance(found, bool) and abs(float(found) - expected) <= 1e-6


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_logical_box import resolve_logical_box
    except Exception as exc:  # noqa: BLE001 - baseline without the mapping still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[tuple[str, bool]] = []

    def call(name: str, declarations: list[tuple[str, str]], **kwargs: object) -> dict[str, object]:
        try:
            row = resolve_logical_box(declarations, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised solve is an unmet outcome
            row = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        payload = row if isinstance(row, dict) else {"outcome": "error"}
        observed[name] = {
            "outcome": payload.get("outcome"),
            "reason": payload.get("reason"),
            "direction": payload.get("direction"),
            "specified_direction": payload.get("specified_direction"),
            "margin_top": payload.get("margin_top"),
            "margin_right": payload.get("margin_right"),
            "margin_bottom": payload.get("margin_bottom"),
            "margin_left": payload.get("margin_left"),
            "padding_left": payload.get("padding_left"),
            "border_left": payload.get("border_left"),
            "content_width": payload.get("content_width"),
            "content_height": payload.get("content_height"),
            "specified_width": payload.get("specified_width"),
            "specified_height": payload.get("specified_height"),
            "inset_top": payload.get("inset_top"),
        }
        return payload

    def margins(name: str, row: dict[str, object], top: float, right: float, bottom: float, left: float) -> None:
        checks.append(
            (
                name,
                row.get("outcome") == "resolved"
                and _near(row.get("margin_top"), top)
                and _near(row.get("margin_right"), right)
                and _near(row.get("margin_bottom"), bottom)
                and _near(row.get("margin_left"), left),
            )
        )

    edges = [("margin-inline", "8px 2px"), ("margin-block", "4px 1px")]
    ltr = call("htb_ltr", edges, writing_mode="horizontal-tb", direction="ltr", containing_inline=200)
    margins("htb_ltr_edges", ltr, 4, 2, 1, 8)
    checks.append(("htb_ltr_content", ltr.get("content_width") == 190 and ltr.get("content_height") == "auto"))

    rtl = call("htb_rtl", edges, writing_mode="horizontal-tb", direction="rtl", containing_inline=200)
    margins("htb_rtl_edges", rtl, 4, 8, 1, 2)
    checks.append(("htb_rtl_content", rtl.get("content_width") == 190))

    vrl = call("vrl_ltr", edges, writing_mode="vertical-rl", direction="ltr", containing_inline=200)
    margins("vrl_ltr_edges", vrl, 8, 4, 2, 1)
    checks.append(("vrl_ltr_content", vrl.get("content_height") == 190 and vrl.get("content_width") == "auto"))

    vlr = call("vlr_ltr", edges, writing_mode="vertical-lr", direction="ltr", containing_inline=200)
    margins("vlr_ltr_edges", vlr, 8, 1, 2, 4)

    sideways = call("sideways_lr", edges, writing_mode="sideways-lr", direction="ltr", containing_inline=200)
    margins("sideways_lr_edges", sideways, 2, 1, 8, 4)
    checks.append(("sideways_lr_height", sideways.get("content_height") == 190))

    alias = call("sideways_rl", edges, writing_mode="sideways-rl", direction="ltr", containing_inline=200)
    margins("sideways_rl_edges", alias, 8, 4, 2, 1)

    upright = call(
        "upright",
        [("margin-inline-start", "8px")],
        writing_mode="vertical-rl",
        direction="rtl",
        text_orientation="upright",
        containing_inline=200,
    )
    margins("upright_edges", upright, 8, 0, 0, 0)
    checks.append(
        (
            "upright_direction",
            upright.get("direction") == "ltr" and upright.get("specified_direction") == "rtl",
        )
    )

    vertical_rtl = call(
        "vrl_rtl",
        [("margin-inline-start", "8px")],
        writing_mode="vertical-rl",
        direction="rtl",
        containing_inline=200,
    )
    margins("vrl_rtl_edges", vertical_rtl, 0, 0, 8, 0)

    later = call(
        "later_physical",
        [("margin-inline-start", "8px"), ("margin-left", "1px")],
        writing_mode="horizontal-tb",
        direction="ltr",
        containing_inline=200,
    )
    margins("later_physical_edges", later, 0, 0, 0, 1)
    checks.append(("later_physical_content", later.get("content_width") == 199))

    later_rtl = call(
        "later_rtl",
        [("margin-inline-start", "8px"), ("margin-left", "1px")],
        writing_mode="horizontal-tb",
        direction="rtl",
        containing_inline=200,
    )
    margins("later_rtl_edges", later_rtl, 0, 8, 0, 1)
    checks.append(("later_rtl_content", later_rtl.get("content_width") == 191))

    earlier = call(
        "earlier_physical",
        [("margin-left", "1px"), ("margin-inline-start", "8px")],
        writing_mode="horizontal-tb",
        direction="ltr",
        containing_inline=200,
    )
    margins("earlier_physical_edges", earlier, 0, 0, 0, 8)

    shorthand = call(
        "shorthand",
        [("margin", "1px 2px 3px 4px"), ("margin-inline-start", "8px")],
        writing_mode="horizontal-tb",
        direction="ltr",
        containing_inline=200,
    )
    margins("shorthand_ltr", shorthand, 1, 2, 3, 8)

    shorthand_rtl = call(
        "shorthand_rtl",
        [("margin", "1px 2px 3px 4px"), ("margin-inline-start", "8px")],
        writing_mode="horizontal-tb",
        direction="rtl",
        containing_inline=200,
    )
    margins("shorthand_rtl_edges", shorthand_rtl, 1, 8, 3, 4)
    checks.append(("shorthand_rtl_content", shorthand_rtl.get("content_width") == 188))

    kept = call(
        "kept_width",
        [("width", "30px"), ("inline-size", "100px")],
        writing_mode="vertical-rl",
        direction="ltr",
        containing_inline=100,
    )
    checks.append(
        (
            "kept_width_axes",
            kept.get("outcome") == "resolved"
            and kept.get("specified_width") == "30px"
            and kept.get("specified_height") == "100px"
            and kept.get("content_width") == 30
            and kept.get("content_height") == 100
            and kept.get("margin_top") == 0
            and kept.get("margin_bottom") == 0,
        )
    )

    replaced = call(
        "replaced_height",
        [("inline-size", "100px"), ("height", "10px")],
        writing_mode="vertical-rl",
        direction="ltr",
        containing_inline=100,
    )
    checks.append(
        (
            "replaced_height_axes",
            replaced.get("outcome") == "resolved"
            and replaced.get("specified_height") == "10px"
            and replaced.get("content_height") == 10
            and replaced.get("margin_bottom") == 90
            and replaced.get("margin_top") == 0
            and replaced.get("content_width") == "auto",
        )
    )

    centered = call(
        "centered",
        [("inline-size", "100px"), ("margin-inline", "auto")],
        writing_mode="vertical-rl",
        direction="ltr",
        containing_inline=200,
    )
    margins("centered_edges", centered, 50, 0, 50, 0)
    checks.append(("centered_content", centered.get("content_height") == 100 and centered.get("content_width") == "auto"))

    capped = call(
        "capped",
        [("inline-size", "100px"), ("max-inline-size", "40px"), ("margin-inline", "auto")],
        writing_mode="vertical-rl",
        direction="ltr",
        containing_inline=200,
    )
    margins("capped_edges", capped, 80, 0, 80, 0)
    checks.append(("capped_content", capped.get("content_height") == 40 and capped.get("content_width") == "auto"))

    hidden = call(
        "hidden_border",
        [("border-inline-start-width", "20px"), ("border-inline-start-style", "none")],
        writing_mode="horizontal-tb",
        containing_inline=100,
    )
    checks.append(
        (
            "hidden_border_chrome",
            hidden.get("outcome") == "resolved" and hidden.get("content_width") == 100 and hidden.get("border_left") == 0,
        )
    )

    solid = call(
        "solid_border",
        [("border-inline-start-width", "20px"), ("border-inline-start-style", "solid")],
        writing_mode="horizontal-tb",
        containing_inline=100,
    )
    checks.append(
        (
            "solid_border_chrome",
            solid.get("outcome") == "resolved" and solid.get("content_width") == 80 and solid.get("border_left") == 20,
        )
    )

    medium = call(
        "medium_border",
        [("border-inline-start-style", "solid")],
        writing_mode="horizontal-tb",
        containing_inline=100,
    )
    checks.append(
        (
            "medium_border_chrome",
            medium.get("outcome") == "resolved" and medium.get("border_left") == 3 and medium.get("content_width") == 97,
        )
    )

    math = call(
        "math_margin",
        [("margin-inline-start", "calc(10px + 10%)")],
        writing_mode="horizontal-tb",
        containing_inline=200,
        percentage_basis=200,
    )
    margins("math_margin_edges", math, 0, 0, 0, 30)
    checks.append(("math_margin_content", math.get("content_width") == 170))

    crowded = call(
        "crowded",
        [("inline-size", "100px"), ("margin-inline", "10px")],
        writing_mode="horizontal-tb",
        direction="rtl",
        containing_inline=200,
    )
    margins("crowded_edges", crowded, 0, 10, 0, 90)
    checks.append(("crowded_content", crowded.get("content_width") == 100))

    pad = call(
        "padding",
        [("padding-inline-start", "10%")],
        writing_mode="horizontal-tb",
        containing_inline=200,
        percentage_basis=200,
    )
    checks.append(
        (
            "padding_percent",
            pad.get("outcome") == "resolved" and pad.get("padding_left") == 20 and pad.get("content_width") == 180,
        )
    )

    block = call(
        "block_percent",
        [("block-size", "50%")],
        writing_mode="vertical-rl",
        containing_inline=100,
        containing_block=80,
    )
    checks.append(
        (
            "block_percent_axes",
            block.get("outcome") == "resolved" and block.get("content_width") == 40 and block.get("content_height") == 100,
        )
    )

    negative = call(
        "negative_margin",
        [("margin-inline-start", "-8px")],
        writing_mode="horizontal-tb",
        containing_inline=100,
    )
    margins("negative_margin_edges", negative, 0, 0, 0, -8)
    checks.append(("negative_margin_content", negative.get("content_width") == 108))

    boxed = call(
        "border_box",
        [
            ("box-sizing", "border-box"),
            ("inline-size", "100px"),
            ("padding-inline", "10px"),
            ("border-inline-width", "5px"),
            ("border-inline-style", "solid"),
        ],
        writing_mode="horizontal-tb",
        containing_inline=100,
    )
    checks.append(
        (
            "border_box_content",
            boxed.get("outcome") == "resolved"
            and boxed.get("content_width") == 70
            and boxed.get("padding_left") == 10
            and boxed.get("border_left") == 5
            and boxed.get("margin_left") == 0
            and boxed.get("margin_right") == 0,
        )
    )

    inset = call(
        "inset",
        [("inset-inline-start", "12px"), ("inset-block-start", "3px")],
        writing_mode="vertical-rl",
        containing_inline=100,
    )
    checks.append(
        (
            "inset_edges",
            inset.get("outcome") == "resolved"
            and inset.get("inset_top") == 12
            and inset.get("inset_right") == 3
            and inset.get("inset_bottom") == "auto"
            and inset.get("inset_left") == "auto",
        )
    )

    fresh = call("initial", [], writing_mode="horizontal-tb", containing_inline=200)
    checks.append(
        (
            "initial_box",
            fresh.get("outcome") == "resolved"
            and fresh.get("content_width") == 200
            and fresh.get("margin_left") == 0
            and fresh.get("inset_top") == "auto"
            and fresh.get("specified_width") == "auto"
            and fresh.get("specified_height") == "auto",
        )
    )

    def invalid(name: str, row: dict[str, object], reason: str) -> None:
        checks.append(
            (
                name,
                row.get("outcome") == "invalid"
                and row.get("reason") == reason
                and row.get("margin_left") is None
                and row.get("content_width") is None
                and row.get("content_height") is None,
            )
        )

    invalid(
        "negative_padding",
        call("negative_padding", [("padding-inline-start", "-1px")], containing_inline=100),
        "padding is invalid",
    )
    invalid(
        "three_values",
        call("three_values", [("margin-inline", "1px 2px 3px")], containing_inline=100),
        "margin-inline is invalid",
    )
    invalid(
        "inset_percent",
        call("inset_percent", [("inset-inline-start", "10%")], containing_inline=100),
        "inset is invalid",
    )
    invalid("unknown", call("unknown", [("color", "red")], containing_inline=100), "property is invalid")
    invalid(
        "block_basis",
        call("block_basis", [("block-size", "10%")], writing_mode="vertical-rl", containing_inline=100),
        "containing block is invalid",
    )
    invalid(
        "bad_mode",
        call("bad_mode", [], writing_mode="sideways", containing_inline=100),
        "writing-mode is invalid",
    )
    invalid(
        "bad_containing",
        call("bad_containing", [], containing_inline=True),
        "containing inline size is invalid",
    )

    passed = all(ok for _, ok in checks) and bool(checks)
    if not passed:
        observed["failed"] = [name for name, ok in checks if not ok]
    return passed, observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
