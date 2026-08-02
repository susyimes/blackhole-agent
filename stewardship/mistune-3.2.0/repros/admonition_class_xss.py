"""Repro for defect admonition-class-xss: unescaped admonition class attribute (XSS)

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

import mistune
from mistune.directives import RSTDirective, Admonition

md = mistune.create_markdown(plugins=[RSTDirective([Admonition()])])
html = md('.. note:: Hi\n   :class: x"><script>alert(1)</script>\n\n   body\n')
vulnerable = '"><script>' in html
fixed = "&lt;script&gt;" in html and '"><script>' not in html
sys.exit(1 if vulnerable or not fixed else 0)
