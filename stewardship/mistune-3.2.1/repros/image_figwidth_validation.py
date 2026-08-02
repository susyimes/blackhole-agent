"""Repro for defect image-figwidth-validation: figwidth accepts arbitrary CSS.

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune
from mistune.directives import RSTDirective, Figure

md = mistune.create_markdown(plugins=[RSTDirective([Figure()])])
html = md(".. figure:: x.jpg\n   :figwidth: 10px;position:fixed\n\n   caption\n")
vulnerable = "position:fixed" in html
fixed = "position:fixed" not in html and 'style="width:' not in html
sys.exit(1 if vulnerable or not fixed else 0)
