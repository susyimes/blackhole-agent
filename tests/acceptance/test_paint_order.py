"""Paint a document from back to front.

A negative stack paints behind in-flow content and a positive stack paints in
front. An automatic z-index lets a positioned descendant join the ancestor,
and an explicit zero keeps that descendant inside. Opacity below one moves a
static box onto the zero band and turns an automatic z-index into an explicit
zero. A float keeps its in-flow child and releases a positive descendant.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit. A tree without the painter still exits 0.
"""

from __future__ import annotations

import json


def _node(name: str, **fields: object) -> dict[str, object]:
    node: dict[str, object] = {"id": name}
    node.update(fields)
    return node


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_paint_order import paint_order
    except Exception as exc:  # noqa: BLE001 - baseline without the painter still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    observed: dict[str, object] = {}
    checks: list[bool] = []

    def keep(name: str, tree: dict[str, object]) -> dict[str, object]:
        try:
            result = paint_order(tree)
        except Exception as exc:  # noqa: BLE001 - a raised call is an unmet outcome
            result = {"outcome": "error", "error": f"{type(exc).__name__}: {exc}"}
        observed[name] = result
        return result if isinstance(result, dict) else {"outcome": "error"}

    def ordered(name: str, tree: dict[str, object], expected: list[str]) -> None:
        result = keep(name, tree)
        checks.append(result.get("outcome") == "ordered" and result.get("order") == expected)

    def invalid(name: str, tree: object) -> None:
        result = keep(name, tree)  # type: ignore[arg-type]
        checks.append(result.get("outcome") == "invalid" and result.get("order") is None)

    ordered(
        "bands",
        _node(
            "root",
            children=[
                _node("n", position="relative", z_index=-1),
                _node("b"),
                _node("p", position="relative", z_index=1),
            ],
        ),
        ["root", "n", "b", "p"],
    )
    ordered(
        "negative_sort",
        _node(
            "root",
            children=[
                _node("a", position="relative", z_index=-1),
                _node("b", position="relative", z_index=-5),
                _node("c", position="relative", z_index=-1),
            ],
        ),
        ["root", "b", "a", "c"],
    )
    ordered(
        "auto_releases_positive",
        _node(
            "root",
            children=[
                _node(
                    "a",
                    position="relative",
                    children=[_node("d", position="relative", z_index=1)],
                ),
                _node("z", position="relative", z_index=0),
            ],
        ),
        ["root", "a", "z", "d"],
    )
    ordered(
        "zero_traps_positive",
        _node(
            "root",
            children=[
                _node(
                    "a",
                    position="relative",
                    z_index=0,
                    children=[_node("d", position="relative", z_index=1)],
                ),
                _node("z", position="relative", z_index=0),
            ],
        ),
        ["root", "a", "d", "z"],
    )
    ordered(
        "auto_releases_negative",
        _node(
            "root",
            children=[
                _node(
                    "a",
                    position="relative",
                    children=[_node("d", position="relative", z_index=-1)],
                ),
                _node("e"),
            ],
        ),
        ["root", "d", "e", "a"],
    )
    ordered(
        "zero_traps_negative",
        _node(
            "root",
            children=[
                _node(
                    "a",
                    position="relative",
                    z_index=0,
                    children=[_node("d", position="relative", z_index=-1)],
                ),
                _node("e"),
            ],
        ),
        ["root", "e", "a", "d"],
    )
    ordered(
        "auto_keeps_in_flow",
        _node(
            "root",
            children=[
                _node("r"),
                _node("a", position="relative", children=[_node("e")]),
                _node("z", position="relative", z_index=0),
            ],
        ),
        ["root", "r", "a", "e", "z"],
    )
    ordered(
        "opacity_traps",
        _node(
            "root",
            children=[
                _node(
                    "a",
                    position="relative",
                    opacity=0.5,
                    children=[_node("d", position="relative", z_index=-1)],
                ),
                _node("e"),
            ],
        ),
        ["root", "e", "a", "d"],
    )
    ordered(
        "static_ignores_z",
        _node(
            "root",
            children=[
                _node("s", z_index=5),
                _node("f", float="left"),
                _node("i", display="inline"),
                _node("p", position="relative", z_index=1),
            ],
        ),
        ["root", "s", "f", "i", "p"],
    )
    ordered(
        "float_releases_positive",
        _node(
            "root",
            children=[
                _node("e"),
                _node("f", float="left", children=[_node("d", position="relative", z_index=1)]),
            ],
        ),
        ["root", "e", "f", "d"],
    )
    ordered(
        "positive_ties",
        _node(
            "root",
            children=[
                _node("a", position="relative", z_index=2),
                _node("b", position="relative", z_index=2),
                _node("c", position="relative", z_index=3),
            ],
        ),
        ["root", "a", "b", "c"],
    )
    ordered(
        "opacity_band",
        _node(
            "root",
            children=[
                _node("b"),
                _node("f", float="left"),
                _node("i", display="inline"),
                _node("o", opacity=0.5),
                _node("z", position="relative", z_index=0),
            ],
        ),
        ["root", "b", "f", "i", "o", "z"],
    )
    ordered(
        "opaque_float_after_inline",
        _node(
            "root",
            children=[
                _node("n", display="inline"),
                _node("f", float="left", opacity=0.5),
            ],
        ),
        ["root", "n", "f"],
    )
    ordered(
        "float_keeps_child",
        _node(
            "root",
            children=[
                _node("b"),
                _node("f", float="right", children=[_node("e")]),
            ],
        ),
        ["root", "b", "f", "e"],
    )
    ordered(
        "auto_groups_later_static",
        _node(
            "root",
            children=[
                _node(
                    "a",
                    position="relative",
                    children=[_node("o", opacity=0.5), _node("e")],
                )
            ],
        ),
        ["root", "a", "e", "o"],
    )
    ordered(
        "inline_block_releases",
        _node(
            "root",
            children=[
                _node("b"),
                _node(
                    "ib",
                    display="inline-block",
                    children=[_node("d", position="absolute", z_index=1)],
                ),
            ],
        ),
        ["root", "b", "ib", "d"],
    )
    ordered(
        "negative_traps_positive",
        _node(
            "root",
            children=[
                _node(
                    "n",
                    position="absolute",
                    z_index=-1,
                    children=[_node("p", position="relative", z_index=1)],
                ),
                _node("b"),
            ],
        ),
        ["root", "n", "p", "b"],
    )
    ordered(
        "position_beats_float",
        _node(
            "root",
            children=[
                _node("i", display="inline"),
                _node("p", position="relative", float="left"),
            ],
        ),
        ["root", "i", "p"],
    )
    ordered("root_only", _node("root"), ["root"])

    invalid("duplicate", _node("root", children=[_node("a"), _node("a")]))
    invalid("bad_position", _node("root", position="running"))
    invalid("bad_opacity", _node("root", opacity=1.1))
    invalid("bad_z", _node("root", position="relative", z_index=1.5))
    invalid("not_a_box", "root")

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
