"""CSS anchor-size() and position-visibility."""

from __future__ import annotations

from blackhole_agent.css_anchor_query import resolve_anchor_size, resolve_position_visibility

_ANCHOR = {"width": 40, "height": 80, "writing_mode": "vertical-rl", "direction": "rtl"}


def test_physical_sizes_ignore_the_anchor_writing_mode() -> None:
    width = resolve_anchor_size(_ANCHOR, "width")
    height = resolve_anchor_size(_ANCHOR, "height", used_in="width")
    assert width == {
        "outcome": "resolved",
        "reason": None,
        "length": 40,
        "axis": "width",
        "keyword": "width",
    }
    assert height["outcome"] == "resolved"
    assert height["length"] == 80
    assert height["axis"] == "height"
    assert height["keyword"] == "height"


def test_logical_axes_follow_the_containing_block_and_the_positioned_box() -> None:
    common = {
        "containing_writing_mode": "vertical-rl",
        "box_writing_mode": "horizontal-tb",
    }
    block = resolve_anchor_size(_ANCHOR, "block", **common)
    inline = resolve_anchor_size(_ANCHOR, "inline", **common)
    self_block = resolve_anchor_size(_ANCHOR, "self-block", **common)
    self_inline = resolve_anchor_size(_ANCHOR, "self-inline", **common)
    assert (block["length"], block["axis"]) == (40, "width")
    assert (inline["length"], inline["axis"]) == (80, "height")
    assert (self_block["length"], self_block["axis"]) == (80, "height")
    assert (self_inline["length"], self_inline["axis"]) == (40, "width")
    same = resolve_anchor_size(_ANCHOR, "self-block", box_direction="rtl", **common)
    assert same["length"] == self_block["length"]


def test_omitted_keyword_follows_the_property_axis() -> None:
    top = resolve_anchor_size(_ANCHOR, used_in="top", containing_writing_mode="vertical-rl")
    block_size = resolve_anchor_size(
        _ANCHOR,
        used_in="block-size",
        containing_writing_mode="vertical-rl",
    )
    assert (top["keyword"], top["axis"], top["length"]) == ("height", "height", 80)
    assert (block_size["keyword"], block_size["axis"], block_size["length"]) == ("block", "width", 40)


def test_unresolvable_query_uses_only_a_definite_fallback() -> None:
    assert resolve_anchor_size(None, "width", fallback="12px")["length"] == 12
    assert resolve_anchor_size(None, "width", fallback="12px")["outcome"] == "fallback"
    percent = resolve_anchor_size(None, "width", fallback="50%", percentage_basis=200)
    assert percent["outcome"] == "fallback"
    assert percent["length"] == 100
    indefinite = resolve_anchor_size(None, "width", fallback="50%")
    assert indefinite["outcome"] == "invalid"
    assert indefinite["length"] is None
    missing = resolve_anchor_size(None, "width")
    assert missing["outcome"] == "invalid"
    assert missing["reason"] == "anchor-size fallback is missing"
    static = resolve_anchor_size(_ANCHOR, "width", fallback=7, absolutely_positioned=False)
    assert static["outcome"] == "fallback"
    assert static["length"] == 7
    assert resolve_anchor_size({"width": None, "height": 80}, "width", fallback=5)["length"] == 5
    assert resolve_anchor_size({"width": None, "height": 80}, "height")["length"] == 80
    assert resolve_anchor_size({"width": 0, "height": 80}, "width")["length"] == 0


def test_invalid_anchor_size_does_not_invent_a_length() -> None:
    bad_keyword = resolve_anchor_size(_ANCHOR, "depth", fallback=4)
    assert bad_keyword["outcome"] == "invalid"
    assert bad_keyword["length"] is None
    assert resolve_anchor_size(_ANCHOR, containing_writing_mode="sideways")["outcome"] == "invalid"
    assert resolve_anchor_size("40", "width", fallback=1)["outcome"] == "invalid"
    assert resolve_anchor_size(None, "width", fallback=True)["outcome"] == "invalid"
    assert resolve_anchor_size(None, "width", fallback="-10%", percentage_basis=100)["length"] == -10


def test_position_visibility_hides_on_each_condition() -> None:
    always = resolve_position_visibility(
        "always",
        references_anchor=True,
        anchor_resolved=False,
        margin_box={"x": 0, "y": 0, "width": 150, "height": 10},
        containing_block={"x": 0, "y": 0, "width": 100, "height": 100},
    )
    assert always["shown"] is True
    assert always["visibility"] == "visible"
    assert always["hidden_by"] == []

    unresolved = resolve_position_visibility(
        "anchor-valid",
        references_anchor=True,
        anchor_resolved=False,
    )
    assert unresolved["shown"] is False
    assert unresolved["visibility"] == "force-hidden"
    assert unresolved["hidden_by"] == ["anchor-valid"]
    untouched = resolve_position_visibility(
        "anchor-valid",
        references_anchor=False,
        anchor_resolved=False,
    )
    assert untouched["shown"] is True

    anchor = {"x": 0, "y": 0, "width": 10, "height": 10}
    missed = {"x": 100, "y": 0, "width": 10, "height": 10, "intervening": True}
    hidden = resolve_position_visibility(
        "anchor-visible",
        references_anchor=True,
        anchor_resolved=True,
        anchor_box=anchor,
        clips=[missed],
    )
    assert hidden["hidden_by"] == ["anchor-visible"]
    outside = resolve_position_visibility(
        "anchor-visible",
        references_anchor=True,
        anchor_resolved=True,
        anchor_box=anchor,
        clips=[{**missed, "intervening": False}],
    )
    assert outside["shown"] is True
    partial = resolve_position_visibility(
        "anchor-visible",
        references_anchor=True,
        anchor_resolved=True,
        anchor_box=anchor,
        clips=[{"x": 6, "y": 0, "width": 10, "height": 10}],
    )
    assert partial["shown"] is True

    crossed = resolve_position_visibility(
        "no-overflow",
        margin_box={"x": 0, "y": 0, "width": 101, "height": 100},
        containing_block={"x": 0, "y": 0, "width": 100, "height": 100},
    )
    assert crossed["hidden_by"] == ["no-overflow"]
    edge = resolve_position_visibility(
        "no-overflow",
        margin_box={"x": 0, "y": 0, "width": 100, "height": 100},
        containing_block={"x": 0, "y": 0, "width": 100, "height": 100},
    )
    assert edge["shown"] is True


def test_visibility_aliases_zero_area_and_combined_conditions() -> None:
    anchor = {"x": 0, "y": 0, "width": 10, "height": 10}
    alias = resolve_position_visibility(
        "anchors-valid",
        references_anchor=True,
        anchor_resolved=False,
    )
    assert alias["conditions"] == ["anchor-valid"]
    assert alias["hidden_by"] == ["anchor-valid"]
    visible_alias = resolve_position_visibility(
        "anchors-visible",
        references_anchor=True,
        anchor_resolved=True,
        anchor_box=anchor,
        clips=[{"x": 100, "y": 0, "width": 10, "height": 10}],
    )
    assert visible_alias["conditions"] == ["anchor-visible"]
    assert visible_alias["shown"] is False

    edge = resolve_position_visibility(
        "anchor-visible",
        references_anchor=True,
        anchor_resolved=True,
        anchor_box=anchor,
        clips=[{"x": 10, "y": 0, "width": 10, "height": 10}],
    )
    assert edge["shown"] is False
    inside = resolve_position_visibility(
        "anchor-visible",
        references_anchor=True,
        anchor_resolved=True,
        anchor_box={"x": 5, "y": 5, "width": 0, "height": 0},
        clips=[{"x": 0, "y": 0, "width": 10, "height": 10}],
    )
    assert inside["shown"] is True
    outside = resolve_position_visibility(
        "anchor-visible",
        references_anchor=True,
        anchor_resolved=True,
        anchor_box={"x": 20, "y": 20, "width": 0, "height": 0},
        clips=[{"x": 0, "y": 0, "width": 10, "height": 10}],
    )
    assert outside["shown"] is False

    both = resolve_position_visibility(
        "anchor-valid no-overflow",
        references_anchor=True,
        anchor_resolved=False,
        margin_box={"x": 0, "y": 0, "width": 120, "height": 10},
        containing_block={"x": 0, "y": 0, "width": 100, "height": 40},
    )
    assert both["hidden_by"] == ["anchor-valid", "no-overflow"]
    assert resolve_position_visibility()["conditions"] == ["anchor-visible"]
    assert resolve_position_visibility("always anchor-valid")["outcome"] == "invalid"
    assert resolve_position_visibility("anchor-valid anchor-valid")["outcome"] == "invalid"
