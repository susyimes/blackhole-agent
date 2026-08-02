"""Repro for defect rst-blockquote-nested-list: KeyError 'prev' in RST renderer.

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune
from mistune.renderers.rst import RSTRenderer

md = mistune.create_markdown(renderer=RSTRenderer())
try:
    out = md("- item\n\n  > quote\n")
except KeyError:
    sys.exit(1)  # defect present: crash on block quote nested in list
fixed = "quote" in out
sys.exit(0 if fixed else 1)
