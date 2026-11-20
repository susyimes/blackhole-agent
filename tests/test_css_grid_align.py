"""Grid item self-alignment inside one grid area."""

from __future__ import annotations

from blackhole_agent.css_grid_align import align_grid_item


def _box(area: object, **kwargs: object) -> tuple[object, object, object, object]:
    result = align_grid_item(area, **kwargs)
    return (result["outcome"], result["start"], result["size"], result["used"])


def test_done_when_contract() -> None:
    assert _box(100) == ("aligned", 0, 100, "stretch")
    assert _box(100, size=40, align="end") == ("aligned", 60, 40, "end")
    assert _box(100, size=40, align="center") == ("aligned", 30, 40, "center")
    assert _box(100, size=40, align="stretch") == ("aligned", 0, 40, "start")
    assert _box(100, automatic=40, replaced=True) == ("aligned", 0, 40, "start")
    assert _box(100, automatic=40, margin_start="auto", margin_end=10, align="end") == (
        "aligned",
        50,
        40,
        "auto-margin",
    )
    assert _box(100, size=140, align="center") == ("aligned", -20, 140, "center")
    assert _box(100, size=140, align="safe center") == ("aligned", 0, 140, "start")
    assert _box(100, size=140, margin_start="auto", align="center") == ("aligned", -20, 140, "center")
    assert _box(100, size=40, align="left", container_direction="rtl") == ("aligned", 60, 40, "end")
    assert _box(100, size=40, align="self-start", item_direction="rtl") == ("aligned", 60, 40, "end")
    assert _box(100, size=40, align="self-start", item_writing_mode="vertical-rl") == (
        "aligned",
        60,
        40,
        "end",
    )
    assert _box(100, size=40, align="right", container_writing_mode="vertical-rl") == (
        "aligned",
        0,
        40,
        "start",
    )
    assert _box(100, size=140, align="first baseline", item_direction="rtl") == (
        "aligned",
        0,
        140,
        "start",
    )
    refused = align_grid_item(-1)
    assert refused["outcome"] == "invalid"
    assert refused["start"] is None
    assert refused["size"] is None


def test_auto_margins_and_clamps() -> None:
    assert _box(100, size=40, margin_start="auto", margin_end="auto") == (
        "aligned",
        30,
        40,
        "auto-margin",
    )
    assert align_grid_item(100, size="auto", margin_start=10, margin_end=20)["start"] == 10
    assert align_grid_item(100, size="auto", margin_start=10, margin_end=20)["size"] == 70
    clamped = align_grid_item(100, max_size=30)
    assert (clamped["start"], clamped["size"], clamped["used"]) == (0, 30, "start")
    assert _box(100, min_size=120) == ("aligned", 0, 120, "start")
    assert _box(100, automatic=20, align="end", min_size=50, max_size=30) == ("aligned", 50, 50, "end")
    spanned = align_grid_item(110)
    assert (spanned["start"], spanned["size"]) == (0, 110)


def test_direction_fallbacks_and_rejection() -> None:
    assert _box(100, size=40, align="self-start", container_direction="rtl", item_direction="rtl") == (
        "aligned",
        0,
        40,
        "start",
    )
    assert _box(100, size=40, align="last baseline") == ("aligned", 60, 40, "end")
    assert _box(100, size=40, align="auto", items="end") == ("aligned", 60, 40, "end")
    assert _box(100, size=40, align="start", items="end") == ("aligned", 0, 40, "start")
    assert _box(100, size=40, align="safe end") == ("aligned", 60, 40, "end")
    assert _box(
        100,
        size=40,
        axis="block",
        align="self-start",
        container_writing_mode="vertical-rl",
    ) == ("aligned", 60, 40, "end")
    assert _box(100, size=40, margin_start=-10, align="start") == ("aligned", -10, 40, "start")
    assert align_grid_item(101, size=40, align="center")["start"] == 30.5
    assert align_grid_item(100, align="left", axis="block")["outcome"] == "invalid"
    assert align_grid_item(100, align="unsafe stretch")["outcome"] == "invalid"
    assert align_grid_item(100, size="auto", align="end")["outcome"] == "invalid"
    assert align_grid_item(100, size=40, container_writing_mode="sideways")["outcome"] == "invalid"
