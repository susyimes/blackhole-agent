"""Resolve CSS anchor-size() and hide a box with position-visibility.

A 40 by 80 anchor keeps those physical sizes. A vertical-rl containing
block maps block to 40 and inline to 80, while a horizontal-tb positioned
box maps self-block to 80 even when the anchor itself is vertical-rl.
top stays on the height axis and block-size follows the containing block.
A missing anchor uses a definite fallback and is invalid without one.
always stays visible. anchor-valid hides only a referenced missing anchor.
anchor-visible hides a total miss of an intervening clip and ignores that
clip when it is not intervening. no-overflow hides a margin box that
crosses the inset-modified containing block.

Prints JSON with boolean passed and nonempty observed. Exit 0 for both a
miss and a hit.
"""

from __future__ import annotations

import json


def observe() -> tuple[bool, dict[str, object]]:
    try:
        from blackhole_agent.css_anchor_query import resolve_anchor_size, resolve_position_visibility
    except Exception as exc:  # noqa: BLE001 - baseline without the module still exits 0
        return False, {"error": f"{type(exc).__name__}: {exc}"}

    anchor = {"width": 40, "height": 80, "writing_mode": "vertical-rl", "direction": "rtl"}
    observed: dict[str, object] = {}
    checks: list[bool] = []

    def size(name: str, target: object, query: object = None, **kwargs: object) -> dict[str, object]:
        try:
            result = resolve_anchor_size(target, query, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised query is an unmet outcome
            result = {"outcome": "error", "length": None, "reason": f"{type(exc).__name__}: {exc}"}
        got = result if isinstance(result, dict) else {"outcome": "error", "length": None}
        observed[name] = {
            "outcome": got.get("outcome"),
            "length": got.get("length"),
            "axis": got.get("axis"),
            "keyword": got.get("keyword"),
        }
        return observed[name]

    def hide(name: str, value: object = None, **kwargs: object) -> dict[str, object]:
        try:
            result = resolve_position_visibility(value, **kwargs)
        except Exception as exc:  # noqa: BLE001 - a raised query is an unmet outcome
            result = {"outcome": "error", "shown": None, "reason": f"{type(exc).__name__}: {exc}"}
        got = result if isinstance(result, dict) else {"outcome": "error", "shown": None}
        observed[name] = {
            "outcome": got.get("outcome"),
            "shown": got.get("shown"),
            "visibility": got.get("visibility"),
            "hidden_by": got.get("hidden_by"),
            "conditions": got.get("conditions"),
        }
        return observed[name]

    def expect(result: dict[str, object], **fields: object) -> None:
        checks.append(all(result.get(key) == value for key, value in fields.items()))

    vertical = {"containing_writing_mode": "vertical-rl", "box_writing_mode": "horizontal-tb"}
    expect(size("width", anchor, "width"), outcome="resolved", length=40, axis="width", keyword="width")
    expect(size("height", anchor, "height"), outcome="resolved", length=80, axis="height", keyword="height")
    expect(size("cross_axis", anchor, "height", used_in="width"), outcome="resolved", length=80, keyword="height")
    expect(size("block", anchor, "block", **vertical), outcome="resolved", length=40, axis="width", keyword="block")
    expect(size("inline", anchor, "inline", **vertical), outcome="resolved", length=80, axis="height", keyword="inline")
    expect(
        size("self_block", anchor, "self-block", **vertical),
        outcome="resolved",
        length=80,
        axis="height",
        keyword="self-block",
    )
    expect(
        size("self_inline", anchor, "self-inline", **vertical),
        outcome="resolved",
        length=40,
        axis="width",
        keyword="self-inline",
    )
    expect(
        size("top", anchor, used_in="top", containing_writing_mode="vertical-rl"),
        outcome="resolved",
        length=80,
        axis="height",
        keyword="height",
    )
    expect(
        size("block_size", anchor, used_in="block-size", containing_writing_mode="vertical-rl"),
        outcome="resolved",
        length=40,
        axis="width",
        keyword="block",
    )
    expect(size("fallback_length", None, "width", fallback="12px"), outcome="fallback", length=12)
    expect(
        size("fallback_percent", None, "width", fallback="50%", percentage_basis=200),
        outcome="fallback",
        length=100,
    )
    expect(size("indefinite_percent", None, "width", fallback="50%"), outcome="invalid", length=None)
    expect(size("missing_fallback", None, "width"), outcome="invalid", length=None)
    expect(
        size("static_box", anchor, "width", fallback=7, absolutely_positioned=False),
        outcome="fallback",
        length=7,
    )

    ink = {"x": 0, "y": 0, "width": 10, "height": 10}
    missed = {"x": 100, "y": 0, "width": 10, "height": 10}
    block = {"x": 0, "y": 0, "width": 100, "height": 100}
    expect(
        hide(
            "always",
            "always",
            references_anchor=True,
            anchor_resolved=False,
            margin_box={"x": 0, "y": 0, "width": 150, "height": 10},
            containing_block=block,
        ),
        outcome="resolved",
        shown=True,
        visibility="visible",
        hidden_by=[],
    )
    expect(
        hide("anchor_valid", "anchor-valid", references_anchor=True, anchor_resolved=False),
        outcome="resolved",
        shown=False,
        visibility="force-hidden",
        hidden_by=["anchor-valid"],
    )
    expect(
        hide("unreferenced", "anchor-valid", references_anchor=False, anchor_resolved=False),
        outcome="resolved",
        shown=True,
        hidden_by=[],
    )
    expect(
        hide("resolved_anchor", "anchor-valid", references_anchor=True, anchor_resolved=True),
        outcome="resolved",
        shown=True,
        hidden_by=[],
    )
    expect(
        hide(
            "intervening_miss",
            "anchor-visible",
            references_anchor=True,
            anchor_resolved=True,
            anchor_box=ink,
            clips=[{**missed, "intervening": True}],
        ),
        outcome="resolved",
        shown=False,
        hidden_by=["anchor-visible"],
    )
    expect(
        hide(
            "outside_chain",
            "anchor-visible",
            references_anchor=True,
            anchor_resolved=True,
            anchor_box=ink,
            clips=[{**missed, "intervening": False}],
        ),
        outcome="resolved",
        shown=True,
        hidden_by=[],
    )
    expect(
        hide(
            "partial_overlap",
            "anchor-visible",
            references_anchor=True,
            anchor_resolved=True,
            anchor_box=ink,
            clips=[{"x": 6, "y": 0, "width": 10, "height": 10}],
        ),
        outcome="resolved",
        shown=True,
        hidden_by=[],
    )
    expect(
        hide(
            "crossed",
            "no-overflow",
            margin_box={"x": 0, "y": 0, "width": 101, "height": 100},
            containing_block=block,
        ),
        outcome="resolved",
        shown=False,
        hidden_by=["no-overflow"],
    )
    expect(
        hide(
            "flush_edge",
            "no-overflow",
            margin_box={"x": 0, "y": 0, "width": 100, "height": 100},
            containing_block=block,
        ),
        outcome="resolved",
        shown=True,
        hidden_by=[],
    )
    expect(
        hide("alias_valid", "anchors-valid", references_anchor=True, anchor_resolved=False),
        outcome="resolved",
        shown=False,
        hidden_by=["anchor-valid"],
        conditions=["anchor-valid"],
    )
    expect(
        hide(
            "alias_visible",
            "anchors-visible",
            references_anchor=True,
            anchor_resolved=True,
            anchor_box=ink,
            clips=[missed],
        ),
        outcome="resolved",
        shown=False,
        hidden_by=["anchor-visible"],
        conditions=["anchor-visible"],
    )
    return all(checks), observed


def main() -> None:
    passed, observed = observe()
    print(json.dumps({"passed": passed, "observed": observed}, sort_keys=True))


if __name__ == "__main__":
    main()
