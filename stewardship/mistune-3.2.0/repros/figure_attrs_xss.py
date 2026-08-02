"""Repro for defect figure-attrs-xss: unescaped figure figclass/figwidth (XSS)

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

import mistune
from mistune.directives import RSTDirective, Figure

md = mistune.create_markdown(plugins=[RSTDirective([Figure()])])
html = md('.. figure:: http://x/y.png\n   :figclass: f"><script>\n   :figwidth: 80%" onload="alert(1)\n\n   cap\n')
vulnerable = '"><script>' in html or '" onload="' in html
fixed = "&lt;script&gt;" in html and '" onload="' not in html
sys.exit(1 if vulnerable or not fixed else 0)
