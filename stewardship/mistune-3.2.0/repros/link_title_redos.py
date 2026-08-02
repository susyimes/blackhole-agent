"""Repro for defect link-title-redos: LINK_TITLE_RE catastrophic backtracking (ReDoS)

Exit 0 when the target tree behaves correctly (defect repaired),
exit 1 when the defect is present. Usage: python <this> <extracted-tree-root>
"""
import sys
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

import time

from mistune.helpers import LINK_TITLE_RE

# 38 backslashes inside an unterminated quoted link title: the vulnerable
# pattern partitions the run between two overlapping alternatives in
# exponentially many ways (~8s at n=38); the repaired pattern is unambiguous.
probe = ' "' + "\\" * 38
start = time.monotonic()
LINK_TITLE_RE.match(probe)
elapsed = time.monotonic() - start
sys.exit(0 if elapsed < 2.0 else 1)
