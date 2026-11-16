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
    with pytest.raises(CssSelectorError):
        selector_specificity(":has()")
    with pytest.raises(CssSelectorError):
        matched_ids(BOX, "span:has(>)")


def test_has_relative_direction_and_specificity() -> None:
    gallery = (
        "<!DOCTYPE html><html><body><section id=\"gallery\">"
        "<article id=\"nest\"><p><img id=\"shot\"></p></article>"
        "<article id=\"direct\"><img id=\"child\"></article>"
        "<article id=\"plain\"><span>text</span></article>"
        "<article id=\"before\"></article><img id=\"between\">"
        "<article id=\"after\"></article></section><img id=\"solo\"></body></html>"
    )
    assert matched_ids(gallery, "article:has(img)") == ["nest", "direct"]
    assert matched_ids(gallery, "article:has(> img)") == ["direct"]
    assert matched_ids(gallery, "article:has(> p > img)") == ["nest"]
    assert matched_ids(gallery, "article:has(+ img)") == ["before"]
    assert matched_ids(gallery, "article:has(~ img)") == ["nest", "direct", "plain", "before"]
    assert matched_ids(gallery, "img:has(+ article)") == ["between"]
    assert matched_ids(gallery, "img:has(img)") == []
    assert matched_ids(gallery, "section:has(article:has(> img))") == ["gallery"]
    assert selector_specificity("article:has(img)") == [[0, 0, 2]]
    assert selector_specificity("article:has(#shot, span)") == [[1, 0, 1]]
    assert selector_specificity("article:has(:where(#shot))") == [[0, 0, 1]]
    assert cascaded_value(
        gallery,
        "article { color: blue } article:has(img) { color: red }",
        "nest",
        "color",
    ) == "red"
    assert cascaded_value(
        gallery,
        "article { color: blue } article:has(img) { color: red }",
        "plain",
        "color",
    ) == "blue"
