"""Resolve the padding edge that contains an absolute or fixed box.

A merely positioned ancestor captures an absolute box and does not capture a
fixed box. A transform, filter, perspective, backdrop-filter, paint
containment, or layout containment captures both, including a transform of
translate(0). content-visibility: hidden and a capturing will-change do too.
An inline ancestor is refused.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the resolver still exits 0.
"""

from __future__ import annotations

import json

_VIEWPORT = {"x": 0, "y": 0, "width": 800, "height": 600}


def _box(identity: str, children: tuple[dict[str, object], ...] = (), **fields: object) -> dict[str, object]:
    node: dict[str, object] = {"id": identity, "x": 0, "y": 0, "width": 100, "height": 100}
    node.update(fields)
    if children:
        node["children"] = list(children)
    return node


def _edges(result: object) -> tuple[object, object, object, object, object, object] | None:
    if not isinstance(result, dict) or result.get("outcome") != "resolved":
        return None
    return (
        result.get("ancestor"),
        result.get("source"),
        result.get("x"),
        result.get("y"),
        result.get("width"),
        result.get("height"),
    )


def _no_rectangle(result: object) -> bool:
    return (
        isinstance(result, dict)
        and result.get("outcome") == "invalid"
        and result.get("x") is None
        and result.get("y") is None
        and result.get("width") is None
        and result.get("height") is None
    )


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_containing_block import resolve_containing_block
    except Exception as exc:  # noqa: BLE001 - baseline without the resolver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, tree: dict[str, object], target: str) -> dict[str, object]:
        try:
            result = resolve_containing_block(tree, target, viewport=_VIEWPORT)
        except Exception as exc:  # noqa: BLE001 - a raised resolve is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result if isinstance(result, dict) else {"outcome": "error"}
        return observed[name]

    framed = _box(
        "grand",
        (
            _box(
                "parent",
                (_box("abs", position="absolute", width=10, height=10),),
                position="static",
                transform="none",
            ),
        ),
        position="relative",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    absolute = keep("absolute_relative", framed, "abs")
    checks.append(_edges(absolute) == ("grand", "ancestor", 15, 25, 190, 90))

    static_only = _box(
        "root",
        (_box("parent", (_box("abs", position="absolute", width=10, height=10),)),),
    )
    checks.append(_edges(keep("absolute_static", static_only, "abs")) == (None, "viewport", 0, 0, 800, 600))

    fixed_positioned = _box(
        "grand",
        (_box("parent", (_box("fix", position="fixed", width=10, height=10),)),),
        position="relative",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    checks.append(_edges(keep("fixed_relative", fixed_positioned, "fix")) == (None, "viewport", 0, 0, 800, 600))

    translated = _box(
        "shifted",
        (_box("fix", position="fixed", width=10, height=10),),
        position="static",
        transform="translate(0)",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    checks.append(_edges(keep("fixed_translate", translated, "fix")) == ("shifted", "ancestor", 15, 25, 190, 90))

    nearer_relative = _box(
        "far",
        (
            _box(
                "near",
                (_box("fix", position="fixed", width=10, height=10),),
                position="relative",
                transform="none",
                x=1,
                y=1,
                width=40,
                height=30,
            ),
        ),
        position="static",
        transform="translate(0)",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    checks.append(_edges(keep("fixed_skips_relative", nearer_relative, "fix")) == ("far", "ancestor", 15, 25, 190, 90))

    nearer_filter = _box(
        "far",
        (
            _box(
                "near",
                (_box("fix", position="fixed", width=10, height=10),),
                position="static",
                filter="blur(0)",
                x=30,
                y=40,
                width=90,
                height=70,
                border_top=3,
                border_right=3,
                border_bottom=3,
                border_left=3,
            ),
        ),
        transform="translate(5px)",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    checks.append(_edges(keep("fixed_filter", nearer_filter, "fix")) == ("near", "ancestor", 33, 43, 84, 64))

    paint = _box(
        "far",
        (
            _box(
                "near",
                (_box("abs", position="absolute", width=10, height=10),),
                position="static",
                contain="paint",
                x=10,
                y=10,
                width=100,
                height=50,
                border_top=2,
                border_right=2,
                border_bottom=2,
                border_left=2,
            ),
        ),
        position="relative",
        x=0,
        y=0,
        width=400,
        height=400,
    )
    checks.append(_edges(keep("absolute_paint", paint, "abs")) == ("near", "ancestor", 12, 12, 96, 46))

    layout_only = _box(
        "far",
        (
            _box(
                "near",
                (_box("abs", position="absolute", width=10, height=10),),
                position="static",
                contain="layout",
                x=0,
                y=0,
                width=10,
                height=10,
            ),
        ),
        position="relative",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    checks.append(_edges(keep("contain_layout", layout_only, "abs")) == ("near", "ancestor", 0, 0, 10, 10))

    sticky = _box(
        "stick",
        (_box("abs", position="absolute", width=10, height=10),),
        position="sticky",
        x=7,
        y=9,
        width=120,
        height=40,
        border_top=1,
        border_right=1,
        border_bottom=1,
        border_left=1,
    )
    checks.append(_edges(keep("sticky_absolute", sticky, "abs")) == ("stick", "ancestor", 8, 10, 118, 38))
    sticky_fixed = _box(
        "stick",
        (_box("fix", position="fixed", width=10, height=10),),
        position="sticky",
        x=7,
        y=9,
        width=120,
        height=40,
        border_top=1,
        border_right=1,
        border_bottom=1,
        border_left=1,
    )
    checks.append(_edges(keep("sticky_fixed", sticky_fixed, "fix")) == (None, "viewport", 0, 0, 800, 600))

    own_transform = _box(
        "parent",
        (
            _box(
                "abs",
                position="absolute",
                transform="translate(10px)",
                x=50,
                y=60,
                width=70,
                height=80,
                border_top=1,
                border_right=1,
                border_bottom=1,
                border_left=1,
            ),
        ),
        width=500,
        height=500,
    )
    checks.append(_edges(keep("own_transform", own_transform, "abs")) == (None, "viewport", 0, 0, 800, 600))

    asymmetric = _box(
        "edge",
        (_box("abs", position="absolute", width=10, height=10),),
        position="relative",
        x=0,
        y=0,
        width=100,
        height=50,
        border_left=8,
        border_top=2,
        border_right=4,
        border_bottom=6,
    )
    checks.append(_edges(keep("asymmetric", asymmetric, "abs")) == ("edge", "ancestor", 8, 2, 88, 42))

    perspective = _box(
        "flat",
        (_box("abs", position="absolute", width=10, height=10),),
        position="static",
        perspective="1px",
        x=1,
        y=1,
        width=40,
        height=30,
    )
    checks.append(_edges(keep("perspective", perspective, "abs")) == ("flat", "ancestor", 1, 1, 40, 30))
    backdrop = _box(
        "glass",
        (_box("fix", position="fixed", width=10, height=10),),
        position="static",
        backdrop_filter="blur(1px)",
        x=2,
        y=3,
        width=40,
        height=30,
    )
    checks.append(_edges(keep("backdrop", backdrop, "fix")) == ("glass", "ancestor", 2, 3, 40, 30))

    inline = _box(
        "line",
        (_box("abs", position="absolute", width=10, height=10),),
        position="relative",
        display="inline",
        width=100,
        height=20,
    )
    inline_result = keep("inline", inline, "abs")
    checks.append(_no_rectangle(inline_result) and inline_result.get("reason") == "inline fragment")

    duplicate = _box("a", (_box("a", width=10, height=10),))
    duplicate_result = keep("duplicate", duplicate, "a")
    checks.append(_no_rectangle(duplicate_result) and duplicate_result.get("reason") == "duplicate")

    nested_fixed = _box(
        "outer",
        (
            _box("abs", position="absolute", width=10, height=10),
            _box("fix", position="fixed", width=10, height=10),
        ),
        position="fixed",
        x=2,
        y=3,
        width=80,
        height=60,
    )
    checks.append(_edges(keep("absolute_in_fixed", nested_fixed, "abs")) == ("outer", "ancestor", 2, 3, 80, 60))
    checks.append(_edges(keep("fixed_in_fixed", nested_fixed, "fix")) == (None, "viewport", 0, 0, 800, 600))

    layout_fixed = _box(
        "far",
        (
            _box(
                "near",
                (_box("fix", position="fixed", width=10, height=10),),
                position="static",
                contain="layout",
                x=4,
                y=6,
                width=80,
                height=50,
                border_top=2,
                border_right=2,
                border_bottom=2,
                border_left=2,
            ),
        ),
        position="relative",
        x=0,
        y=0,
        width=400,
        height=400,
    )
    checks.append(_edges(keep("layout_fixed", layout_fixed, "fix")) == ("near", "ancestor", 6, 8, 76, 46))

    size_only = _box(
        "far",
        (
            _box(
                "near",
                (_box("fix", position="fixed", width=10, height=10),),
                position="static",
                contain="size",
            ),
        ),
        position="relative",
        x=1,
        y=1,
        width=20,
        height=20,
    )
    checks.append(_edges(keep("contain_size", size_only, "fix")) == (None, "viewport", 0, 0, 800, 600))

    hinted = _box(
        "hint",
        (
            _box("abs", position="absolute", width=10, height=10),
            _box("fix", position="fixed", width=10, height=10),
        ),
        position="static",
        will_change="position",
        x=8,
        y=9,
        width=40,
        height=30,
        border_top=1,
        border_right=1,
        border_bottom=1,
        border_left=1,
    )
    checks.append(_edges(keep("will_position_absolute", hinted, "abs")) == ("hint", "ancestor", 9, 10, 38, 28))
    checks.append(_edges(keep("will_position_fixed", hinted, "fix")) == (None, "viewport", 0, 0, 800, 600))

    will_transform = _box(
        "layer",
        (_box("fix", position="fixed", width=10, height=10),),
        position="static",
        transform="none",
        will_change="Transform",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    checks.append(_edges(keep("will_transform", will_transform, "fix")) == ("layer", "ancestor", 15, 25, 190, 90))

    skipped = _box(
        "outer",
        (
            _box(
                "near",
                (_box("fix", position="fixed", width=10, height=10),),
                position="static",
                will_change="position",
                x=1,
                y=1,
                width=30,
                height=20,
            ),
        ),
        position="static",
        transform="translate(0)",
        x=10,
        y=20,
        width=200,
        height=100,
        border_top=5,
        border_right=5,
        border_bottom=5,
        border_left=5,
    )
    checks.append(_edges(keep("will_position_skips_to_transform", skipped, "fix")) == ("outer", "ancestor", 15, 25, 190, 90))

    opacity = _box(
        "fade",
        (_box("fix", position="fixed", width=10, height=10),),
        position="static",
        will_change="opacity, scroll-position",
    )
    checks.append(_edges(keep("will_opacity", opacity, "fix")) == (None, "viewport", 0, 0, 800, 600))

    hidden = _box(
        "skip",
        (_box("fix", position="fixed", width=10, height=10),),
        position="static",
        content_visibility="hidden",
        x=3,
        y=4,
        width=50,
        height=40,
        border_left=2,
        border_top=1,
        border_right=0,
        border_bottom=0,
    )
    checks.append(_edges(keep("content_hidden", hidden, "fix")) == ("skip", "ancestor", 5, 5, 48, 39))
    shown = _box(
        "show",
        (_box("fix", position="fixed", width=10, height=10),),
        position="static",
        content_visibility="auto",
        x=3,
        y=4,
        width=50,
        height=40,
    )
    checks.append(_edges(keep("content_auto", shown, "fix")) == (None, "viewport", 0, 0, 800, 600))

    refused = keep(
        "will_none",
        _box("bad", (_box("fix", position="fixed", width=10, height=10),), will_change="none"),
        "fix",
    )
    checks.append(_no_rectangle(refused) and refused.get("reason") == "will_change")

    for name, feature in (
        ("will_filter", "filter"),
        ("will_perspective", "perspective"),
        ("will_backdrop", "backdrop-filter"),
        ("will_contain", "contain"),
        ("will_content_visibility", "content-visibility"),
    ):
        captured = _box(
            name,
            (_box("fix", position="fixed", width=4, height=4),),
            position="static",
            will_change=feature,
            x=0,
            y=0,
            width=20,
            height=10,
        )
        checks.append(_edges(keep(name, captured, "fix")) == (name, "ancestor", 0, 0, 20, 10))
    contents = _box(
        "contents",
        (_box("fix", position="fixed", width=4, height=4),),
        position="static",
        will_change="contents",
        x=0,
        y=0,
        width=20,
        height=10,
    )
    checks.append(_edges(keep("will_contents", contents, "fix")) == (None, "viewport", 0, 0, 800, 600))
    return all(checks), observed


def main() -> int:
    try:
        passed, observed = observe()
    except Exception as exc:  # noqa: BLE001 - unmet behavior and baseline both exit 0
        passed, observed = False, {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"passed": bool(passed), "observed": observed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
