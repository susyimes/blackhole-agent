"""@scope proximity, limits, and the cascade order around them."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from blackhole_agent.css_selectors import CssSelectorError, cascaded_value


def test_scope_acceptance_probe() -> None:
    path = Path(__file__).resolve().parents[0] / "acceptance" / "test_css_scope.py"
    spec = importlib.util.spec_from_file_location("css_scope_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    passed, observed = module.observe()
    assert passed, observed


def test_ampersand_and_pseudo_element_preludes_are_rejected() -> None:
    markup = "<!DOCTYPE html><html><body><p id='t'></p></body></html>"
    with pytest.raises(CssSelectorError):
        cascaded_value(markup, "& { color: red }", "t", "color")
    with pytest.raises(CssSelectorError):
        cascaded_value(markup, "@scope (div::before) { p { color: red } }", "t", "color")
    with pytest.raises(CssSelectorError):
        cascaded_value(markup, "@scope (.a) to { p { color: red } }", "t", "color")
