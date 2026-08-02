"""Repro for defect math-currency-crossline: currency misparsed as math, cross-line matches.

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune

md = mistune.create_markdown(plugins=["math"])
currency = md("Price $5 and $10 total")
crossline = md("a $x\ny$ b")
normal = md("The $n$th element")
vulnerable = 'class="math"' in currency or 'class="math"' in crossline
fixed = (
    'class="math"' not in currency
    and 'class="math"' not in crossline
    and 'class="math"' in normal  # real math must still parse
)
sys.exit(1 if vulnerable or not fixed else 0)
