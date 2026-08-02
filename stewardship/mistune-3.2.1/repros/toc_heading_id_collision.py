"""Repro for defect toc-heading-id-collision.

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import re
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune
from mistune.toc import add_toc_hook

md = mistune.create_markdown(escape=False)
add_toc_hook(md)
html, _state = md.parse('<h2 id="toc_1">raw</h2>\n\n# Hello\n')
ids = re.findall(r'id="([^"]+)"', html)
vulnerable = len(ids) != len(set(ids))
fixed = "toc_1_1" in ids and len(ids) == len(set(ids))
sys.exit(1 if vulnerable or not fixed else 0)
