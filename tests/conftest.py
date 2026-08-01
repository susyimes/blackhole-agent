"""Pytest bootstrap for validating the checked-out worktree."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

src_path = str(SRC_DIR)
sys.path = [path for path in sys.path if path != src_path]
sys.path.insert(0, src_path)


@pytest.fixture(autouse=True, scope="session")
def _durable_state_overlay(tmp_path_factory: pytest.TempPathFactory):
    """Redirect durable-state writes out of the tracked checkout.

    Many capability planes accept the real repository root and persist
    ledgers, bundles, and certificates through ``atomic_write_json``. With
    ``BLACKHOLE_DURABLE_ROOT`` set, those writes land in a per-session
    overlay instead, so a full test run leaves the worktree byte-clean.
    Subprocesses spawned by proofs inherit the variable through the
    environment.
    """

    overlay = tmp_path_factory.mktemp("durable-overlay")
    previous = os.environ.get("BLACKHOLE_DURABLE_ROOT")
    os.environ["BLACKHOLE_DURABLE_ROOT"] = str(overlay)
    try:
        yield overlay
    finally:
        if previous is None:
            os.environ.pop("BLACKHOLE_DURABLE_ROOT", None)
        else:
            os.environ["BLACKHOLE_DURABLE_ROOT"] = previous
