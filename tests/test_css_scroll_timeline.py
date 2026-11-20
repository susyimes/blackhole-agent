"""Replay the scroll-timeline acceptance probe as a failing test."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_scroll_timeline_probe() -> None:
    path = Path(__file__).resolve().parents[1] / "tests" / "acceptance" / "test_css_scroll_timeline.py"
    spec = importlib.util.spec_from_file_location("css_scroll_timeline_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    passed, observed = module.observe()
    assert passed, observed
