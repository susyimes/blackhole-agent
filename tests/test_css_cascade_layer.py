"""Layer order edges beside the cascade-layer acceptance fixture."""

from __future__ import annotations

import pytest

from blackhole_agent.css_selectors import CssSelectorError, cascaded_value, computed_value

MARKUP = "<!DOCTYPE html><html><body><div id=\"p\"><p id=\"t\"></p></div></body></html>"


def _color(sheet: str) -> str:
    return cascaded_value(MARKUP, sheet, "t", "color")


def test_layer_names_are_case_sensitive_and_statement_order_sticks() -> None:
    assert _color(
        """
        @layer base, Base;
        @layer Base { #t { color: red } }
        @layer base { #t { color: green } }
        """
    ) == "red"
    assert _color(
        """
        @layer A { #t { color: green } }
        @layer A.B { #t { color: red } }
        """
    ) == "green"


def test_later_declaration_in_one_layer_overrides_revert_layer() -> None:
    assert _color(
        """
        @layer base { #t { color: olive } }
        @layer theme { #t { color: revert-layer; color: green } }
        """
    ) == "green"


def test_important_revert_layer_drops_the_same_layer() -> None:
    assert _color(
        """
        @layer base { #t { color: olive } }
        @layer theme {
          #t { color: green }
          #t { color: revert-layer !important }
        }
        """
    ) == "olive"


def test_revert_layer_with_no_lower_layer_inherits_at_computed_value_time() -> None:
    sheet = "#p { color: navy } @layer base { #t { color: revert-layer } }"
    assert cascaded_value(MARKUP, sheet, "t", "color") == ""
    assert computed_value(MARKUP, sheet, "t", "color") == "navy"


def test_supports_color_is_readable_inside_the_cascade() -> None:
    assert _color("#t { color: blue } @supports (color: red) { #t { color: red } }") == "red"


def test_other_at_rules_stay_outside_the_reader() -> None:
    with pytest.raises(CssSelectorError):
        _color("@layer base, theme { #t { color: red } }")
