"""Per-line bidi reorder is not the paragraph visual order sliced apart."""

from __future__ import annotations

from blackhole_agent.unicode_bidi import reorder_bidi_lines, resolve_bidi

_HEBREW = "\u05d0 \u05d1"


def test_one_line_matches_the_paragraph_order() -> None:
    result = reorder_bidi_lines(_HEBREW, [3], "ltr")
    assert result["outcome"] == "reordered"
    line = result["lines"][0]
    assert line["text"] == "\u05d1 \u05d0"
    assert line["visual_order"] == resolve_bidi(_HEBREW, "ltr")["visual_order"]


def test_trailing_space_on_a_broken_line_stays_after_the_letter() -> None:
    result = reorder_bidi_lines(_HEBREW, [2, 3], "ltr")
    assert [line["text"] for line in result["lines"]] == ["\u05d0 ", "\u05d1"]
    assert result["lines"][0]["levels"] == [1, 0]


def test_right_to_left_paragraph_mirrors_parentheses() -> None:
    result = reorder_bidi_lines("(ab)", [4], "rtl")
    line = result["lines"][0]
    assert line["text"] == "(ab)"
    assert line["visual_order"] == [3, 1, 2, 0]
    assert "".join("(ab)"[index] for index in line["visual_order"]) == ")ab("


def test_fullwidth_parentheses_use_the_mirror_mate() -> None:
    text = "\uff08ab\uff09"
    result = reorder_bidi_lines(text, [4], "rtl")
    assert result["lines"][0]["text"] == "\uff08ab\uff09"


def test_combining_mark_follows_its_hebrew_base() -> None:
    text = "\u05d0\u0307"
    result = reorder_bidi_lines(text, [2], "ltr")
    assert result["lines"][0]["text"] == text
    assert result["lines"][0]["visual_order"] == [0, 1]


def test_right_to_left_line_resets_trailing_space_into_the_run() -> None:
    result = reorder_bidi_lines(_HEBREW, [2, 3], "rtl")
    assert result["paragraph_level"] == 1
    assert [line["text"] for line in result["lines"]] == [" \u05d0", "\u05d1"]


def test_automatic_direction_follows_the_first_hebrew_letter() -> None:
    result = reorder_bidi_lines(_HEBREW, [2, 3], "auto")
    assert result["paragraph_level"] == 1
    assert result["lines"][0]["text"] == " \u05d0"


def test_invalid_ends_direction_and_paragraph_span() -> None:
    assert reorder_bidi_lines(_HEBREW, [2], "ltr")["reason"] == "line ends must cover the string"
    assert reorder_bidi_lines(_HEBREW, [1, 1, 3], "ltr")["reason"] == "line is empty"
    assert reorder_bidi_lines(_HEBREW, [3], "sideways")["reason"] == "direction must be ltr, rtl, or auto"
    assert reorder_bidi_lines(None, [0], "ltr")["reason"] == "text must be a string"
    assert reorder_bidi_lines("a\nb", [3], "ltr")["reason"] == "line crosses a paragraph"
    assert reorder_bidi_lines("", [], "ltr")["outcome"] == "invalid"


def test_call_does_not_mutate_the_end_list() -> None:
    ends = [2, 3]
    reorder_bidi_lines(_HEBREW, ends, "ltr")
    assert ends == [2, 3]


def test_empty_string_is_one_empty_line() -> None:
    result = reorder_bidi_lines("", [0], "ltr")
    assert result["lines"] == [{"text": "", "levels": [], "visual_order": []}]
