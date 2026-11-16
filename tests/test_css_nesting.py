"""Nested CSS style rules expand against the parent selector list."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_nested_style_rule_matches_parent_specificity():
    path = Path(__file__).resolve().parents[0] / "acceptance" / "test_css_nesting.py"
    spec = spec_from_file_location("css_nesting_acceptance", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    passed, observed = module.observe()
    assert passed is True
    assert observed["parent_id_specificity"] == "red"
    assert observed["direct_child"] == "red"
    assert observed["grandchild"] == "blue"
    assert observed["ampersand_compound"] == "red"
    assert observed["plain_card"] == "blue"
    assert observed["ancestor_ampersand"] == "red"
    assert observed["outside_ancestor"] == "blue"
    assert observed["later_declaration"] == "green"
    assert observed["invalid_nested_keeps_parent"] == "blue"
    assert observed["two_levels"] == "red"
    assert observed["nested_rule_stays_in_layer"] == "blue"
