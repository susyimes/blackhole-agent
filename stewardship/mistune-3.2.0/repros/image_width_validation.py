"""Repro for defect image-width-validation: invalid image width accepted (unanchored regex)

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

import mistune
from mistune.directives import RSTDirective, Image

md = mistune.create_markdown(plugins=[RSTDirective([Image()])])
html = md('.. image:: http://x/y.png\n   :width: 100px" onload="alert(1)\n')
vulnerable = "onload" in html  # junk width accepted and emitted into the style attr
fixed = "onload" not in html and "width" not in html
sys.exit(1 if vulnerable or not fixed else 0)
