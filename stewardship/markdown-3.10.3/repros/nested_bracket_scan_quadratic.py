"""Standalone repro for the nested-bracket quadratic defect (complexity).

Discovered autonomously by blackhole_agent.upstream_discovery (generators
'nested_link' and 'nested_image', one shared root cause: per-'[' rescans for
the matching ']'). Runs a doubling ladder for both shapes against the source
tree given as argv[1]; exits 1 while the defect is present in either shape,
0 once repaired. Usage: python <this file> <path-to-src-dir>
"""
import json, math, sys, time

sys.path.insert(0, sys.argv[1])
PLUGINS = []
KIND = 'complexity'
EXPONENT_THRESHOLD = 1.75
TIME_FLAG_FLOOR = 0.3
START = 2250

SHAPES = {
    'nested_link': lambda n: '[' * n + 'a' + ']' * n,
    'nested_image': lambda n: '![' * n + 'a' + ']' * n,
}

import markdown

_EXT_MAP = {'footnotes': 'footnotes', 'table': 'tables'}

def render(text, plugins):
    exts = [_EXT_MAP[p] for p in plugins if p in _EXT_MAP]
    markdown.markdown(text, extensions=exts)

render('warmup', PLUGINS)
results = {}
for name, gen in SHAPES.items():
    n = START
    times = []
    crashed = None
    limit = max(START * 4, START + 1)
    while n <= limit:
        text = gen(n)
        t0 = time.perf_counter()
        try:
            render(text, PLUGINS)
            elapsed = time.perf_counter() - t0
        except Exception as e:
            crashed = type(e).__name__
            break
        times.append((n, elapsed))
        if elapsed >= 1.0 and len(times) >= 2:
            # Always measure at least two sizes: one load-inflated run must
            # not end the ladder before any growth pair exists.
            break
        n *= 2
    if crashed is not None:
        print(json.dumps({'defect': True, 'kind': KIND, 'shape': name, 'crash': crashed}))
        sys.exit(1)
    worst = 0.0
    for (n1, t1), (n2, t2) in zip(times, times[1:]):
        if t1 >= 0.02 and n2 > n1:
            worst = max(worst, math.log2(max(t2, 1e-9) / t1) / math.log2(n2 / n1))
    t_max = max((t for _, t in times), default=0.0)
    results[name] = {'exponent': round(worst, 3), 't_max': round(t_max, 4)}

defect = any(
    r['exponent'] >= EXPONENT_THRESHOLD and r['t_max'] >= TIME_FLAG_FLOOR
    for r in results.values()
)
print(json.dumps({'defect': defect, 'kind': KIND, 'shapes': results}))
sys.exit(1 if defect else 0)
