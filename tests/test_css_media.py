"""CSS @media selects the cascade against an explicit viewport."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from blackhole_agent.css_selectors import CssSelectorError, cascaded_value, computed_value


def test_media_query_selects_author_color():
    path = Path(__file__).resolve().parents[0] / "acceptance" / "test_css_media.py"
    spec = spec_from_file_location("css_media_acceptance", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    passed, observed = module.observe()
    assert passed is True
    assert observed["min_width_hit"] == "red"
    assert observed["min_width_miss"] == "blue"
    assert observed["unknown_feature"] == "blue"
    assert observed["malformed_keeps_later"] == "green"
    assert observed["parent_specificity"] == "red"
    assert observed["layer_important_hit"] == "red"
    assert observed["layer_important_miss"] == "blue"
    assert observed["scope_inside"] == "red"
    assert observed["scope_outside"] == "blue"
    assert observed["omitted_media"] == "blue"


def test_computed_color_follows_media():
    markup = "<!DOCTYPE html><html><body><p id='t'></p></body></html>"
    sheet = "#t { color: blue } @media (min-width: 30px) { #t { color: red } }"
    assert computed_value(markup, sheet, "t", "color", media={"width": 30}) == "red"
    assert computed_value(markup, sheet, "t", "color", media={"width": 0}) == "blue"


def test_supports_stays_outside_the_reader():
    markup = "<!DOCTYPE html><html><body><p id='t'></p></body></html>"
    with pytest.raises(CssSelectorError, match="at-rules are outside this reader"):
        cascaded_value(markup, "@supports (color: red) { #t { color: red } }", "t", "color")
