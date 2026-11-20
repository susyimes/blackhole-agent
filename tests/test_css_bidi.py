"""CSS bidi paragraph order against UAX #9 and CSS Writing Modes."""

from __future__ import annotations

import pytest

from blackhole_agent.css_bidi import bidi_controls, reorder_css_bidi


def test_ltr_embedding_matches_the_resolved_levels() -> None:
    got = reorder_css_bidi("car means \u05d0\u05d1\u05d2.")
    assert got["outcome"] == "reordered"
    assert got["visual"] == "car means \u05d2\u05d1\u05d0."
    assert got["levels"] == [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0]
    assert got["paragraph_level"] == 0


def test_rtl_paragraph_trades_sides_and_keeps_latin_letters() -> None:
    got = reorder_css_bidi("\u05d0\u05d1\u05d2 abc \u05d3\u05d4\u05d5", direction="rtl")
    assert got["visual"] == "\u05d5\u05d4\u05d3 abc \u05d2\u05d1\u05d0"
    assert got["levels"] == [1, 1, 1, 1, 2, 2, 2, 1, 1, 1, 1]


def test_european_digits_stay_in_order_beside_the_rtl_run() -> None:
    got = reorder_css_bidi("abc \u05d0\u05d1\u05d2 12")
    assert got["visual"] == "abc 12 \u05d2\u05d1\u05d0"
    assert got["levels"] == [0, 0, 0, 0, 1, 1, 1, 1, 2, 2]


def test_arabic_letter_pulls_a_following_number_to_its_left() -> None:
    got = reorder_css_bidi("\u0639 12")
    assert got["visual"] == "12 \u0639"
    assert got["levels"] == [1, 1, 2, 2]


def test_override_forces_the_root_inline() -> None:
    assert reorder_css_bidi("abc", direction="rtl", unicode_bidi="bidi-override")["visual"] == "cba"
    assert reorder_css_bidi("\u05d0\u05d1\u05d2", unicode_bidi="bidi-override")["visual"] == "\u05d0\u05d1\u05d2"
    assert reorder_css_bidi("abc", direction="rtl", unicode_bidi="isolate-override")["visual"] == "cba"
    assert reorder_css_bidi("a\u202exyz\u202cb")["visual"] == "azyxb"


def test_plaintext_uses_each_paragraph_and_a_block_isolate_does_not() -> None:
    text = "\u05d0\u05d1\u05d2 abc"
    assert reorder_css_bidi(text)["visual"] == "\u05d2\u05d1\u05d0 abc"
    assert reorder_css_bidi(text, unicode_bidi="embed")["visual"] == "\u05d2\u05d1\u05d0 abc"
    assert reorder_css_bidi(text, unicode_bidi="isolate")["visual"] == "\u05d2\u05d1\u05d0 abc"
    plain = reorder_css_bidi(text, unicode_bidi="plaintext")
    assert plain["paragraph_level"] == 1
    assert plain["visual"] == "abc \u05d2\u05d1\u05d0"
    split = reorder_css_bidi("ab\u2029\u05d0\u05d1\u05d2 abc", unicode_bidi="plaintext")
    assert split["paragraph_levels"] == [0, 1]
    assert split["visual"] == "ab\u2029abc \u05d2\u05d1\u05d0"


def test_inline_isolate_reorders_inside_without_leaking() -> None:
    prefix, suffix = bidi_controls("rtl", "isolate")
    assert prefix == "\u2067" and suffix == "\u2069"
    assert bidi_controls("ltr", "isolate") == ("\u2066", "\u2069")
    assert bidi_controls("rtl", "isolate-override") == ("\u2068\u202e", "\u202c\u2069")
    assert bidi_controls("ltr", "normal") == ("", "")
    text = f"english17 {prefix}\u05d0\u05d1\u05d2 english \u05d3\u05d4\u05d5{suffix}"
    got = reorder_css_bidi(text)
    assert got["visual"] == "english17 \u2067\u05d5\u05d4\u05d3 english \u05d2\u05d1\u05d0\u2069"


def test_spec_number_run_and_bracket_pairs() -> None:
    numbers = (
        'he said "'
        "\u05d0\u05d1\u05d2 \u05d3\u05d4\u05d5\u05d6\u05d7\u05d8 \u05d9\u05db\u05dc 123, 456, 789, \u05de\u05df"
        '".'
    )
    assert reorder_css_bidi(numbers)["visual"] == (
        'he said "'
        "\u05df\u05de ,789 ,456 ,123 \u05dc\u05db\u05d9 \u05d8\u05d7\u05d6\u05d5\u05d4\u05d3 \u05d2\u05d1\u05d0"
        '".'
    )
    bmw = "\u05d0\u05d1 \u05d2\u05d3 \u05d4 bmw 500, \u05d5\u05d6."
    assert reorder_css_bidi(bmw, direction="rtl")["visual"] == ".\u05d6\u05d5 ,bmw 500 \u05d4 \u05d3\u05d2 \u05d1\u05d0"
    brackets = "smith (fabrikam \u05d0\u05d1\u05d2) \u05d3\u05d4\u05d5"
    assert reorder_css_bidi(brackets, direction="rtl")["visual"] == "\u05d5\u05d4\u05d3 )\u05d2\u05d1\u05d0 fabrikam( smith"
    assert reorder_css_bidi("\u05d0\u05d1\u05d2 book(s)", direction="rtl")["visual"] == "book(s) \u05d2\u05d1\u05d0"


def test_combining_marks_follow_their_base_after_reversal() -> None:
    assert reorder_css_bidi("\u05d0\u0301")["visual"] == "\u05d0\u0301"
    assert reorder_css_bidi("\u05d0\u0301\u0302")["visual"] == "\u05d0\u0301\u0302"


def test_invalid_input_and_empty_paragraph() -> None:
    refused = reorder_css_bidi("abc", direction="sideways")
    assert refused["outcome"] == "invalid"
    assert refused["visual"] is None and refused["levels"] is None
    assert reorder_css_bidi(None)["reason"] == "text is invalid"
    assert reorder_css_bidi("", direction="rtl") == {
        "outcome": "reordered",
        "visual": "",
        "levels": [],
        "paragraph_level": 1,
        "paragraph_levels": [1],
    }


def test_bidi_controls_reject_unknown_keywords() -> None:
    with pytest.raises(Exception, match="direction is invalid"):
        bidi_controls("down")
