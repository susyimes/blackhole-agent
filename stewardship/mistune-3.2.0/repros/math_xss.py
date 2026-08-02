"""Repro for defect math-xss: math plugin raw HTML (XSS)

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

import mistune

md = mistune.create_markdown(plugins=["math"])
inline = md("$<script>alert(1)</script>$")
block = md("$$\n<script>alert(1)</script>\n$$")
vulnerable = "<script>" in inline or "<script>" in block
fixed = "&lt;script&gt;" in inline and "&lt;script&gt;" in block
sys.exit(1 if vulnerable or not fixed else 0)
