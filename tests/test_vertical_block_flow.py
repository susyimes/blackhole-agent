"""Fail the process when a vertical block does not place its columns."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_vertical_block_columns() -> None:
    path = Path(__file__).resolve().parent / "acceptance" / "test_vertical_block_flow.py"
    spec = importlib.util.spec_from_file_location("vertical_block_flow_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    passed, observed = module.observe()
    assert passed, observed
