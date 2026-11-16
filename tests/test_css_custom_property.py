"""Computed custom properties stay distinct from the cascaded specified value."""

from __future__ import annotations

import runpy
from pathlib import Path

from blackhole_agent.css_selectors import cascaded_value, computed_value

PROBE = Path(__file__).resolve().parent / "acceptance" / "test_css_custom_property.py"


def test_custom_property_acceptance_fixture() -> None:
    namespace = runpy.run_path(str(PROBE), run_name="not_main")
    passed, observed = namespace["observe"]()
    assert passed, observed


def test_cascade_keeps_the_specified_variable() -> None:
    markup = "<!DOCTYPE html><html><body><p id=\"child\">x</p></body></html>"
    sheet = "p { --a: red; color: var(--a); }"
    assert cascaded_value(markup, sheet, "child", "color") == "var(--a)"
    assert computed_value(markup, sheet, "child", "color") == "red"
    assert computed_value(markup, sheet, "child", "--a") == "red"
