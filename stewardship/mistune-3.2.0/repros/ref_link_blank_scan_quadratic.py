"""Repro for defect ref-link-blank-scan-quadratic: per-definition blank-line rescan.

Discovered autonomously by capability.upstream-discovery (generator
'footnote_refs'): parse_ref_link rescans the whole remaining document for the
next blank line for every reference-link definition, so n definitions cost
O(n^2) time. Exit 0 when the target tree parses the ladder in near-linear
time (defect repaired), exit 1 while the quadratic scan is present.
Usage: python <this> <extracted-tree-root>
"""
import json
import math
import sys
import time
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.0" / "src"))

import mistune

md = mistune.create_markdown()


def gen(n: int) -> str:
    refs = "".join("[%d]" % i for i in range(n))
    defs = "\n".join("[%d]: x" % i for i in range(n))
    return refs + "\n\n" + defs


md(gen(8))  # warmup
times = []
n = 1000
while n <= 8000:
    t0 = time.perf_counter()
    md(gen(n))
    elapsed = time.perf_counter() - t0
    times.append((n, elapsed))
    if elapsed >= 1.0:
        break
    n *= 2

worst = 0.0
for (n1, t1), (n2, t2) in zip(times, times[1:]):
    if t1 >= 0.02 and n2 > n1:
        worst = max(worst, math.log2(max(t2, 1e-9) / t1) / math.log2(n2 / n1))
t_max = max(t for _, t in times)
defect = worst >= 1.75 and t_max >= 0.3
print(json.dumps({"defect": defect, "exponent": round(worst, 3), "t_max": round(t_max, 4)}))
sys.exit(1 if defect else 0)
