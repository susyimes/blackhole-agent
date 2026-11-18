"""Measure the used content height of one in-flow non-replaced block.

An automatic height drops a margin that collapses out and keeps a margin that
stays inside. A block formatting context grows to a float's bottom margin
edge; a visible box does not. A specified height ignores both. min-height and
max-height clamp afterwards, and the minimum wins when they disagree.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the height solver still exits 0.
"""

from __future__ import annotations

import json

_KEYS = ("outcome", "reason", "content_height", "border_box")
_CHILD = {"id": "c", "height": 20, "margin_top": 15, "margin_bottom": 30}


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_block_height import used_block_height
    except Exception as exc:  # noqa: BLE001 - baseline without the solver still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def take(name: str, box: object, **kwargs: object) -> dict[str, object]:
        try:
            result = used_block_height(box, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised solver is an unmet outcome
            result = {"outcome": "error", "reason": f"{type(exc).__name__}: {exc}"}
        packed = result if isinstance(result, dict) else {"outcome": "error"}
        observed[name] = {key: packed.get(key) for key in _KEYS}
        return observed[name]

    def expect(name: str, fields: dict[str, object], box: object, **kwargs: object) -> None:
        got = take(name, box, **kwargs)
        checks.append(all(got.get(key) == value for key, value in fields.items()))

    parent = {"id": "p", "children": [_CHILD]}
    expect(
        "collapsed_out",
        {"outcome": "sized", "content_height": 20, "border_box": 20},
        parent,
        floats=({"bottom": 40},),
    )
    expect(
        "relative_collapses",
        {"outcome": "sized", "content_height": 20, "border_box": 20},
        {"id": "p", "position": "relative", "children": [_CHILD]},
        floats=({"bottom": 40},),
    )
    expect(
        "border_keeps_margin",
        {"outcome": "sized", "content_height": 50, "border_box": 51},
        {"id": "p", "border_bottom": 1, "children": [_CHILD]},
    )
    expect(
        "collapsed_through",
        {"outcome": "sized", "content_height": 0, "border_box": 0},
        {"id": "p", "children": [{"id": "c", "height": 0, "margin_top": 10, "margin_bottom": 30}]},
    )
    expect(
        "clearance_keeps_top",
        {"outcome": "sized", "content_height": 32, "border_box": 32},
        {"id": "p", "children": [{"id": "c", "height": 20, "margin_top": 12, "margin_bottom": 9, "clearance": True}]},
    )
    expect(
        "negative_separation",
        {"outcome": "sized", "content_height": 33, "border_box": 33},
        {
            "id": "p",
            "children": [
                {"id": "a", "height": 20, "margin_bottom": -5},
                {"id": "b", "height": 10, "margin_top": 8},
            ],
        },
    )
    expect(
        "padding_is_not_content",
        {"outcome": "sized", "content_height": 20, "border_box": 40},
        {
            "id": "p",
            "padding_top": 10,
            "padding_bottom": 5,
            "border_top": 2,
            "border_bottom": 3,
            "children": [{"id": "c", "height": 20}],
        },
    )
    expect(
        "hidden_grows_to_float",
        {"outcome": "sized", "content_height": 40, "border_box": 40},
        {"id": "p", "overflow": "hidden", "children": [{"id": "c", "height": 20}]},
        floats=({"bottom": 12}, {"bottom": 40}),
    )
    expect(
        "hidden_float_past_margin",
        {"outcome": "sized", "content_height": 90, "border_box": 90},
        {"id": "p", "overflow": "hidden", "children": [{"id": "c", "height": 20, "margin_bottom": 30}]},
        floats=({"bottom": 90},),
    )
    expect(
        "inline_block_contains_margin",
        {"outcome": "sized", "content_height": 50, "border_box": 50},
        {"id": "p", "display": "inline-block", "children": [{"id": "c", "height": 20, "margin_bottom": 30}]},
    )
    expect(
        "inline_block_grows_to_float",
        {"outcome": "sized", "content_height": 80, "border_box": 80},
        {"id": "p", "display": "inline-block", "children": [{"id": "c", "height": 20, "margin_bottom": 30}]},
        floats=({"bottom": 80},),
    )
    expect(
        "floated_box_grows",
        {"outcome": "sized", "content_height": 40, "border_box": 40},
        {"id": "p", "float": "left", "children": [{"id": "c", "height": 20}]},
        floats=({"bottom": 40},),
    )
    expect(
        "specified_ignores_float",
        {"outcome": "sized", "content_height": 15, "border_box": 15},
        {"id": "p", "height": 15, "overflow": "hidden", "children": [{"id": "c", "height": 100}]},
        floats=({"bottom": 40},),
    )
    expect(
        "max_clamps_float",
        {"outcome": "sized", "content_height": 25, "border_box": 25},
        {"id": "p", "overflow": "hidden", "max_height": 25, "children": [{"id": "c", "height": 10}]},
        floats=({"bottom": 40},),
    )
    expect(
        "min_beats_max",
        {"outcome": "sized", "content_height": 60, "border_box": 60},
        {"id": "p", "min_height": 60, "max_height": 25},
    )
    expect(
        "percent_of_definite",
        {"outcome": "sized", "content_height": 100, "border_box": 100},
        {"id": "p", "height": "50%", "overflow": "hidden"},
        containing_height=200,
        floats=({"bottom": 999},),
    )
    expect(
        "percent_of_auto_is_auto",
        {"outcome": "sized", "content_height": 20, "border_box": 20},
        {"id": "p", "height": "50%", "children": [_CHILD]},
        containing_height="auto",
    )
    expect(
        "min_auto_is_zero",
        {"outcome": "sized", "content_height": 20, "border_box": 20},
        {"id": "p", "min_height": "auto", "children": [{"id": "c", "height": 20}]},
    )
    expect(
        "percent_min_of_auto_is_zero",
        {"outcome": "sized", "content_height": 20, "border_box": 20},
        {"id": "p", "min_height": "50%", "children": [{"id": "c", "height": 20}]},
        containing_height="auto",
    )
    expect(
        "percent_min_of_definite",
        {"outcome": "sized", "content_height": 100, "border_box": 100},
        {"id": "p", "min_height": "50%", "children": [{"id": "c", "height": 20}]},
        containing_height=200,
    )
    expect(
        "percent_max_of_auto_is_none",
        {"outcome": "sized", "content_height": 40, "border_box": 40},
        {"id": "p", "overflow": "hidden", "max_height": "10%", "children": [{"id": "c", "height": 10}]},
        containing_height="auto",
        floats=({"bottom": 40},),
    )
    expect(
        "percent_max_of_definite",
        {"outcome": "sized", "content_height": 20, "border_box": 20},
        {"id": "p", "overflow": "hidden", "max_height": "10%", "children": [{"id": "c", "height": 10}]},
        containing_height=200,
        floats=({"bottom": 40},),
    )
    expect(
        "border_box_subtracts_chrome",
        {"outcome": "sized", "content_height": 70, "border_box": 100},
        {
            "id": "p",
            "height": 100,
            "box_sizing": "border-box",
            "padding_top": 10,
            "padding_bottom": 10,
            "border_top": 5,
            "border_bottom": 5,
        },
    )
    expect(
        "border_box_floors_at_zero",
        {"outcome": "sized", "content_height": 0, "border_box": 30},
        {
            "id": "p",
            "height": 10,
            "box_sizing": "border-box",
            "padding_top": 10,
            "padding_bottom": 10,
            "border_top": 5,
            "border_bottom": 5,
        },
    )
    expect(
        "border_box_min",
        {"outcome": "sized", "content_height": 20, "border_box": 50},
        {
            "id": "p",
            "box_sizing": "border-box",
            "min_height": 50,
            "padding_top": 10,
            "padding_bottom": 10,
            "border_top": 5,
            "border_bottom": 5,
        },
    )
    expect(
        "line_visible_ignores_float",
        {"outcome": "sized", "content_height": 18, "border_box": 18},
        {"id": "p", "line_bottom": 18},
        floats=({"bottom": 40},),
    )
    expect(
        "line_hidden_grows_to_float",
        {"outcome": "sized", "content_height": 40, "border_box": 40},
        {"id": "p", "overflow": "hidden", "line_bottom": 18},
        floats=({"bottom": 40},),
    )

    negative = take("negative_height", {"id": "p", "height": -1})
    checks.append(negative.get("outcome") == "invalid" and negative.get("content_height") is None)
    absolute = take("absolute", {"id": "p", "position": "absolute"})
    checks.append(absolute.get("outcome") == "invalid" and absolute.get("content_height") is None)
    mixed = take("line_with_child", {"id": "p", "line_bottom": 18, "children": [{"id": "c", "height": 10}]})
    checks.append(mixed.get("outcome") == "invalid" and mixed.get("content_height") is None)
    outflow = take("out_of_flow_child", {"id": "p", "children": [{"id": "c", "float": "left", "height": 10}]})
    checks.append(outflow.get("outcome") == "invalid" and outflow.get("content_height") is None)
    bad_float = take("negative_float", {"id": "p"}, floats=({"bottom": -1},))
    checks.append(bad_float.get("outcome") == "invalid" and bad_float.get("content_height") is None)
    flagged = take("boolean_height", {"id": "p", "height": True})
    checks.append(flagged.get("outcome") == "invalid" and flagged.get("content_height") is None)

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
