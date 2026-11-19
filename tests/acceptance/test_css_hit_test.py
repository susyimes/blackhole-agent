"""Hit-test a physical point against CSS paint order and border boxes."""

from __future__ import annotations

import json


def _box(identity: str, x: float, y: float, width: float, height: float, **extra: object) -> dict[str, object]:
    return {"id": identity, "x": x, "y": y, "width": width, "height": height, **extra}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_hit_test import element_from_point
    except Exception as exc:  # noqa: BLE001 - a tree without hit testing still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    escaped = _box(
        "root",
        0,
        0,
        100,
        100,
        position="relative",
        z_index=0,
        children=[
            _box(
                "parent",
                10,
                10,
                50,
                50,
                children=[_box("child", -10, -10, 40, 40, position="absolute", z_index=-1)],
            )
        ],
    )
    contained = _box(
        "root",
        0,
        0,
        100,
        100,
        position="relative",
        z_index=0,
        children=[
            _box(
                "parent",
                10,
                10,
                50,
                50,
                position="relative",
                z_index=0,
                children=[_box("child", -10, -10, 40, 40, position="absolute", z_index=-1)],
            )
        ],
    )
    floated = _box(
        "root",
        0,
        0,
        100,
        100,
        children=[
            _box("block", 0, 0, 80, 80),
            _box("floated", 0, 0, 40, 40, float="left"),
        ],
    )
    edges = _box(
        "root",
        0,
        0,
        30,
        10,
        children=[
            _box("behind", 10, 0, 10, 10),
            _box("front", 0, 0, 10, 10),
        ],
    )
    skipped = _box(
        "root",
        0,
        0,
        100,
        100,
        position="relative",
        z_index=0,
        children=[
            _box(
                "parent",
                10,
                10,
                50,
                50,
                pointer_events="none",
                children=[_box("child", -10, -10, 40, 40, position="absolute", z_index=-1, pointer_events="auto")],
            )
        ],
    )
    inherited = _box(
        "root",
        0,
        0,
        100,
        100,
        children=[_box("parent", 0, 0, 40, 40, pointer_events="none", children=[_box("child", 0, 0, 40, 40)])],
    )
    hidden = _box(
        "root",
        0,
        0,
        100,
        100,
        children=[
            _box(
                "parent",
                10,
                10,
                50,
                50,
                visibility="hidden",
                children=[_box("child", -10, -10, 40, 40, position="absolute", z_index=-1, visibility="visible")],
            )
        ],
    )
    ghost = _box(
        "root",
        0,
        0,
        80,
        80,
        children=[_box("block", 0, 0, 40, 40), _box("ghost", 0, 0, 40, 40, opacity=0)],
    )
    cases = {
        "escaped_overlap": (escaped, 20, 20, "hit", "parent"),
        "escaped_protrusion": (escaped, -5, -5, "hit", "child"),
        "escaped_parent_only": (escaped, 40, 40, "hit", "parent"),
        "context_overlap": (contained, 20, 20, "hit", "child"),
        "context_parent_only": (contained, 40, 40, "hit", "parent"),
        "float_over_block": (floated, 10, 10, "hit", "floated"),
        "block_past_float": (floated, 50, 50, "hit", "block"),
        "root_past_block": (floated, 90, 90, "hit", "root"),
        "top_left_edge": (edges, 0, 0, "hit", "front"),
        "excluded_right_edge": (edges, 10, 5, "hit", "behind"),
        "none_falls_through": (skipped, 20, 20, "hit", "child"),
        "none_protrusion": (skipped, -5, -5, "hit", "child"),
        "inherited_none": (inherited, 10, 10, "hit", "root"),
        "visible_descendant": (hidden, 20, 20, "hit", "child"),
        "hidden_parent_falls_through": (hidden, 40, 40, "hit", "root"),
        "opacity_zero": (ghost, 10, 10, "hit", "ghost"),
        "outside": (floated, 150, 150, "miss", None),
        "right_bottom_corner": (_box("only", 0, 0, 10, 10), 10, 10, "miss", None),
    }
    observed: dict[str, object] = {}
    checks: list[bool] = []
    for name, (tree, x, y, outcome, ident) in cases.items():
        result = element_from_point(tree, x, y)
        observed[name] = {"outcome": result.get("outcome"), "id": result.get("id")}
        checks.append(result.get("outcome") == outcome and result.get("id") == ident)
    rejected = element_from_point(_box("bad", 0, 0, -1, 10), 0, 0)
    observed["negative_width"] = {"outcome": rejected.get("outcome"), "id": rejected.get("id")}
    checks.append(rejected.get("outcome") == "invalid" and rejected.get("id") is None)
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
