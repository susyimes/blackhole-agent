"""Repro for defect include-directive-hardening: traversal, CRLF misparse.

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import os
import sys
import tempfile
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune
from mistune.directives import RSTDirective, Include, Admonition

tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
with open(os.path.join(tmp, "secret.md"), "w") as f:
    f.write("# TOP SECRET\n")
with open(os.path.join(tmp, "sub", "a.md"), "w") as f:
    f.write(".. include:: ../secret.md\n")

md = mistune.create_markdown(plugins=[RSTDirective([Include(), Admonition()])])
traversal = md.read(os.path.join(tmp, "sub", "a.md"))[0]
traversal_vulnerable = "TOP SECRET" in traversal
traversal_fixed = "Could not include outside source dir" in traversal

# CRLF include: directive body must stay nested inside the admonition
with open(os.path.join(tmp, "sub", "b.md"), "wb") as f:
    f.write(b".. note:: T\r\n\r\n   body text\r\n")
with open(os.path.join(tmp, "sub", "c.md"), "w") as f:
    f.write(".. include:: b.md\n")
crlf = md.read(os.path.join(tmp, "sub", "c.md"))[0]
body = crlf.find("<p>body text</p>")
section_end = crlf.find("</section>")
crlf_fixed = body != -1 and section_end != -1 and body < section_end

vulnerable = traversal_vulnerable or not crlf_fixed
fixed = traversal_fixed and crlf_fixed
sys.exit(1 if vulnerable or not fixed else 0)
