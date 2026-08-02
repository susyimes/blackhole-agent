"""Repro for defect image-unsafe-url: image directive src is not URL-sanitized.

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune
from mistune.directives import RSTDirective, Image

md = mistune.create_markdown(plugins=[RSTDirective([Image()])])
html = md(".. image:: javascript:alert(1)\n")
vulnerable = 'src="javascript:alert(1)"' in html
fixed = "#harmful-link" in html and "javascript:" not in html
sys.exit(1 if vulnerable or not fixed else 0)
