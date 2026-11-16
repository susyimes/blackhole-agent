"""Registered custom properties keep unregistered substitution intact."""

from __future__ import annotations

import runpy
from pathlib import Path

from blackhole_agent.css_selectors import computed_value

PROBE = Path(__file__).resolve().parent / "acceptance" / "test_css_registered_property.py"
MARKUP = "<!DOCTYPE html><html><body><div id='p'><p id='t'></p></div></body></html>"


def test_registered_property_acceptance_fixture() -> None:
    namespace = runpy.run_path(str(PROBE), run_name="not_main")
    passed, observed = namespace["observe"]()
    assert passed, observed


def test_missing_inherits_leaves_the_property_unregistered() -> None:
    sheet = """
    @property --tone { syntax: "<color>"; initial-value: black; }
    #p { --tone: red; }
    """
    assert computed_value(MARKUP, sheet, "t", "--tone") == "red"


def test_relative_initial_value_does_not_register() -> None:
    sheet = """
    @property --gap { syntax: "<length>"; inherits: false; initial-value: 1em; }
    #p { --gap: 4px; }
    """
    assert computed_value(MARKUP, sheet, "t", "--gap") == "4px"


def test_absolute_length_initial_stays_as_written() -> None:
    sheet = """
    @property --gap { syntax: "<length>"; inherits: false; initial-value: 1in; }
    """
    assert computed_value(MARKUP, sheet, "t", "--gap") == "1in"


def test_property_inside_a_layer_still_registers() -> None:
    sheet = """
    @layer base {
      @property --tone { syntax: "<color>"; inherits: false; initial-value: black; }
    }
    """
    assert computed_value(MARKUP, sheet, "t", "--tone") == "black"


def test_color_list_and_number_syntax() -> None:
    sheet = """
    @property --stops { syntax: "<color>#"; inherits: false; initial-value: red, blue; }
    @property --count { syntax: "<number>"; inherits: false; initial-value: 1.5; }
    #t { --stops: rgb(1, 2, 3), red; --count: 4px; }
    """
    assert computed_value(MARKUP, sheet, "t", "--stops") == "rgb(1, 2, 3), red"
    assert computed_value(MARKUP, sheet, "p", "--stops") == "red, blue"
    assert computed_value(MARKUP, sheet, "t", "--count") == "1.5"
