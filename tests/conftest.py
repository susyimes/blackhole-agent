"""Pytest bootstrap for validating the checked-out worktree."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

src_path = str(SRC_DIR)
sys.path = [path for path in sys.path if path != src_path]
sys.path.insert(0, src_path)
