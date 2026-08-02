"""Repro for defect nested-bracket-scan-quadratic: per-marker bracket rescan.

Discovered autonomously by capability.upstream-discovery (generators
'nested_link' and 'nested_image'): parse_link_text rescans the remaining
source for the matching ']' once per '[' or '![' marker, so n nested brackets
cost O(n^2) time. Exit 0 when the target tree parses both ladders in
near-linear time (defect repaired), exit 1 while the quadratic scan is
present. Usage: python <this> <extracted-tree-root>
"""
import json
import math
import sys
import time
from pathlib import Path

_TREE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(_TREE / "mistune-3.2.1" / "src"))

import mistune

md = mistune.create_markdown()

GENERATORS = {
    "nested_link": lambda n: "[" * n + "a" + "]" * n,
    "nested_image": lambda n: "![" * n + "a" + "]" * n,
}


def ladder(gen):
    times = []
    n = 1000
    while n <= 8000:
        t0 = time.perf_counter()
        md(gen(n))
        elapsed = time.perf_counter() - t0
        times.append((n, elapsed))
        if elapsed >= 1.0 and len(times) >= 2:
            # Always measure at least two sizes: one load-inflated run must
            # not end the ladder before any growth pair exists.
            break
        n *= 2
    worst = 0.0
    for (n1, t1), (n2, t2) in zip(times, times[1:]):
        if t1 >= 0.02 and n2 > n1:
            worst = max(worst, math.log2(max(t2, 1e-9) / t1) / math.log2(n2 / n1))
    return worst, max(t for _, t in times)


md("warmup")
report = {}
defect = False
for name, gen in GENERATORS.items():
    md(gen(8))  # warmup
    exponent, t_max = ladder(gen)
    report[name] = {"exponent": round(exponent, 3), "t_max": round(t_max, 4)}
    defect = defect or (exponent >= 1.75 and t_max >= 0.3)
report["defect"] = defect
print(json.dumps(report))
sys.exit(1 if defect else 0)
