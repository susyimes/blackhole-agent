"""Repro for defect image-alt-double-encoding: double-encoded image alt text

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

import mistune

html = mistune.html("![dogs & cats](dogs.png)")
vulnerable = "&amp;amp;" in html
fixed = 'alt="dogs &amp; cats"' in html
sys.exit(1 if vulnerable or not fixed else 0)
