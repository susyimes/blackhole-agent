"""CSS subgrid placement against the Grid Level 2 gutter examples."""

from __future__ import annotations

from blackhole_agent.css_subgrid import place_subgrid_items


def _pair() -> list[dict[str, object]]:
    return [
        {"id": "left", "start": 1, "span": 1},
        {"id": "right", "start": 2, "span": 1},
    ]


def _boxes(result: dict[str, object]) -> list[tuple[object, object, object]]:
    items = result["items"]
    assert isinstance(items, list)
    return [(item["id"], item["start"], item["size"]) for item in items]


def test_parent_gutter_examples() -> None:
    tracks = [100, 150]
    assert _boxes(place_subgrid_items(tracks, _pair(), gap=50, subgrid_gap=0)) == [
        ("left", 0, 125),
        ("right", 125, 175),
    ]
    assert _boxes(place_subgrid_items(tracks, _pair(), gap=50, subgrid_gap="normal")) == [
        ("left", 0, 100),
        ("right", 150, 150),
    ]
    assert _boxes(place_subgrid_items(tracks, _pair(), gap=50, subgrid_gap=75)) == [
        ("left", 0, 87.5),
        ("right", 162.5, 137.5),
    ]
    assert _boxes(place_subgrid_items(tracks, _pair(), gap=50, subgrid_gap=25)) == [
        ("left", 0, 112.5),
        ("right", 137.5, 162.5),
    ]


def test_full_span_covers_the_parent_gutter() -> None:
    result = place_subgrid_items(
        [100, 150],
        [{"id": "both", "start": 1, "span": 2}],
        gap=50,
        subgrid_gap=0,
    )
    assert _boxes(result) == [("both", 0, 300)]


def test_edge_insets_only_the_touching_item() -> None:
    result = place_subgrid_items([300, 100], _pair(), gap=0, edge_start=100, edge_end=0)
    assert _boxes(result) == [("left", 100, 200), ("right", 300, 100)]


def test_item_past_the_explicit_grid_is_clamped() -> None:
    result = place_subgrid_items([40], [{"id": "only", "start": 2, "span": 3}])
    assert result["outcome"] == "placed"
    assert _boxes(result) == [("only", 0, 40)]
    assert result["items"][0]["line_start"] == 1
    assert result["items"][0]["line_end"] == 2


def test_negative_gap_is_rejected() -> None:
    result = place_subgrid_items([100, 150], _pair(), gap=-1)
    assert result == {"outcome": "invalid", "items": None, "reason": "gap is invalid"}


def test_middle_item_absorbs_half_the_gutter_difference_on_both_sides() -> None:
    items = [
        {"id": "a", "start": 1, "span": 1},
        {"id": "b", "start": 2, "span": 1},
        {"id": "c", "start": 3, "span": 1},
    ]
    result = place_subgrid_items([100, 80, 60], items, gap=10, subgrid_gap=0)
    assert _boxes(result) == [("a", 0, 105), ("b", 105, 90), ("c", 195, 65)]


def test_subgrid_can_begin_after_the_parent_start() -> None:
    result = place_subgrid_items(
        [10, 100, 150],
        _pair(),
        gap=50,
        span_start=2,
        span=2,
        subgrid_gap=0,
    )
    assert _boxes(result) == [("left", 60, 125), ("right", 185, 175)]


def test_negative_line_selects_the_last_track() -> None:
    result = place_subgrid_items(
        [10, 10, 10],
        [{"id": "end", "start": -2, "span": 1}],
        gap=0,
    )
    assert _boxes(result) == [("end", 20, 10)]


def test_single_track_ignores_a_different_subgrid_gap() -> None:
    result = place_subgrid_items(
        [40],
        [{"id": "only", "start": 1, "span": 1}],
        gap=50,
        subgrid_gap=0,
        edge_start=5,
        edge_end=7,
    )
    assert _boxes(result) == [("only", 5, 28)]
