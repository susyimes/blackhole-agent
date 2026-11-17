"""Collapse adjoining vertical margins of in-flow blocks.

Sibling margins become one separation. A parent with no top edge takes the
first child's top margin outside. An empty block collapses through. A float,
an absolute box, an inline block, and a non-visible overflow keep child
margins inside. Clearance adds the adjoining margins.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the placer still exits 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _prefer_workspace_src() -> None:
    src = Path.cwd() / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


def _box(name: str, **fields: object) -> dict[str, object]:
    return {"id": name, **fields}


def _at(name: str, y: int, height: int, through: bool = False) -> dict[str, object]:
    return {"id": name, "y": y, "border_height": height, "through": through}


def observe() -> tuple[bool, dict[str, object]]:
    _prefer_workspace_src()
    try:
        from blackhole_agent.css_margin_collapse import place_collapsed_margins
    except Exception as exc:  # noqa: BLE001 - baseline without the placer still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []
    bordered = {"border_top": 1, "border_bottom": 1}

    def keep(name: str, box: dict[str, object]) -> dict[str, object]:
        try:
            result = place_collapsed_margins(box)
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    def placed(
        name: str,
        box: dict[str, object],
        margin_top: int,
        margin_bottom: int,
        boxes: list[dict[str, object]],
    ) -> None:
        result = keep(name, box)
        checks.append(
            result.get("outcome") == "placed"
            and result.get("margin_top") == margin_top
            and result.get("margin_bottom") == margin_bottom
            and result.get("boxes") == boxes
        )

    def invalid(name: str, box: dict[str, object]) -> None:
        result = keep(name, box)
        checks.append(result.get("outcome") == "invalid" and result.get("boxes") is None)

    placed(
        "siblings",
        _box("p", children=[_box("a", margin_top=10, height=40, margin_bottom=10), _box("b", margin_top=30, height=40)], **bordered),
        0,
        0,
        [_at("p", 0, 122), _at("a", 11, 40), _at("b", 81, 40)],
    )
    placed(
        "negative",
        _box("p", children=[_box("a", height=10, margin_bottom=10), _box("b", margin_top=-20, height=10)], **bordered),
        0,
        0,
        [_at("p", 0, 12), _at("a", 1, 10), _at("b", 1, 10)],
    )
    placed(
        "three_pieces",
        _box(
            "p",
            children=[
                _box("a", height=10, margin_bottom=40),
                _box("e", margin_top=10, margin_bottom=-15, height=0),
                _box("b", height=10),
            ],
            **bordered,
        ),
        0,
        0,
        [_at("p", 0, 47), _at("a", 1, 10), _at("e", 51, 0, True), _at("b", 36, 10)],
    )
    placed(
        "parent_child",
        _box("p", margin_top=10, children=[_box("a", margin_top=25, height=40)]),
        25,
        0,
        [_at("p", 0, 40), _at("a", 0, 40)],
    )
    placed(
        "separated",
        _box("p", margin_top=10, border_top=1, children=[_box("a", margin_top=25, height=40)]),
        10,
        0,
        [_at("p", 0, 66), _at("a", 26, 40)],
    )
    placed(
        "collapse_through",
        _box("p", children=[_box("e", margin_top=10, margin_bottom=15, height=0)]),
        15,
        0,
        [_at("p", 0, 0, True), _at("e", 0, 0, True)],
    )
    placed(
        "inside_empty",
        _box("p", children=[_box("e", margin_top=10, margin_bottom=15, height=0)], **bordered),
        0,
        0,
        [_at("p", 0, 17), _at("e", 11, 0, True)],
    )
    placed(
        "escape_top",
        _box("p", border_bottom=1, children=[_box("e", margin_top=10, margin_bottom=15, height=0)]),
        15,
        0,
        [_at("p", 0, 1), _at("e", 0, 0, True)],
    )
    for name, field, value in (
        ("overflow", "overflow", "hidden"),
        ("float", "float", "left"),
        ("absolute", "position", "absolute"),
        ("inline_block", "display", "inline-block"),
    ):
        placed(
            name,
            _box("p", children=[_box("a", margin_top=20, height=10)], **{field: value}),
            0,
            0,
            [_at("p", 0, 30), _at("a", 20, 10)],
        )
    placed(
        "cancel",
        _box("p", children=[_box("a", height=10, margin_bottom=20), _box("b", margin_top=-20, height=10)], **bordered),
        0,
        0,
        [_at("p", 0, 22), _at("a", 1, 10), _at("b", 11, 10)],
    )
    placed(
        "clearance",
        _box(
            "p",
            children=[_box("a", height=10, margin_bottom=10), _box("b", clearance=True, margin_top=15, height=10)],
            **bordered,
        ),
        0,
        0,
        [_at("p", 0, 47), _at("a", 1, 10), _at("b", 36, 10)],
    )
    placed(
        "minimum",
        _box("p", min_height=100, margin_bottom=5, children=[_box("a", height=10, margin_bottom=30)]),
        0,
        5,
        [_at("p", 0, 100), _at("a", 0, 10)],
    )
    placed(
        "parent_cancel",
        _box("p", margin_top=-25, children=[_box("a", margin_top=25, height=10)]),
        0,
        0,
        [_at("p", 0, 10), _at("a", 0, 10)],
    )
    invalid("negative_height", _box("p", children=[_box("a", height=-1)]))
    invalid("duplicate", _box("p", children=[_box("a", height=1), _box("a", height=1)]))

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
