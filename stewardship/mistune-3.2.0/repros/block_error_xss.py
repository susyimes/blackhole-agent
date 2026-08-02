"""Repro for defect block-error-xss: raw block_error output (XSS)

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

from mistune.renderers.html import HTMLRenderer

html = HTMLRenderer().block_error("<script>alert(1)</script>")
vulnerable = "<script>" in html
fixed = "&lt;script&gt;" in html
sys.exit(1 if vulnerable or not fixed else 0)
