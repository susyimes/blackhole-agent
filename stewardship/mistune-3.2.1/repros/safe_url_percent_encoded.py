"""Repro for defect safe-url-percent-encoded: percent-decoded scheme bypass.

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune

html = mistune.create_markdown()("[h](javascript%3Aalert(1))")
vulnerable = "javascript%3Aalert" in html
fixed = "#harmful-link" in html
sys.exit(1 if vulnerable or not fixed else 0)
