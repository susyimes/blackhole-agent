"""Selector edges that sit beside the acceptance fixture."""

from __future__ import annotations

import pytest

from blackhole_agent.css_selectors import (
    CssSelectorError,
    cascaded_value,
    matched_ids,
    selector_specificity,
)

BOX = (
    "<!DOCTYPE html><html><body><div id=\"box\">"
    "<span class=\"item\" id=\"a\"></span>"
    "<div id=\"mid\"></div>"
    "<span class=\"item\" id=\"b\"></span>"
    "</div></body></html>"
)


def test_nth_counts_only_the_parent_children() -> None:
    assert matched_ids(BOX, "#box > :nth-child(-n+2)") == ["a", "mid"]
    assert matched_ids(BOX, "#box > :nth-child(2n + 1)") == ["a", "b"]
    assert matched_ids(BOX, "#box > :nth-last-child(1 of .item)") == ["b"]


def test_sibling_and_case() -> None:
    assert matched_ids(BOX, "span ~ span") == ["b"]
    assert matched_ids(BOX, "span + div") == ["mid"]
    assert matched_ids(BOX, "SPAN.item") == ["a", "b"]
    assert matched_ids(BOX, ".Item") == []
    assert matched_ids(BOX, "#box > :not(.item)") == ["mid"]


def test_unmatched_argument_does_not_raise_specificity() -> None:
    color = cascaded_value(
        BOX,
        ".item, #pin { color: green } span.item { color: red }",
        "b",
        "color",
    )
    assert color == "red"
    assert selector_specificity(":is(:where(#pin), .item)") == [[0, 1, 0]]


def test_important_identifier_beats_an_important_class() -> None:
    color = cascaded_value(
        BOX,
        ".item { color: red !important } #b { color: blue !important }",
        "b",
        "color",
    )
    assert color == "blue"


def test_unsupported_pseudo_is_rejected() -> None:
    with pytest.raises(CssSelectorError):
        selector_specificity(":hover")
