"""Synthesized standalone repro for the footnote_refs defect (complexity).

Discovered autonomously by blackhole_agent.upstream_discovery. Runs a doubling
ladder against the source tree given as argv[1]; exits 1 while the defect is
present, 0 once repaired. Usage: python <this file> <path-to-src-dir>
"""
import json, math, sys, time

sys.path.insert(0, sys.argv[1])
PLUGINS = ['footnotes']
KIND = 'complexity'
EXPONENT_THRESHOLD = 1.75
TIME_FLAG_FLOOR = 0.3

def gen(n):
    refs = ''.join('[%d]' % i for i in range(n))
    defs = '\n'.join('[%d]: x' % i for i in range(n))
    return refs + '\n\n' + defs

import markdown

_EXT_MAP = {'footnotes': 'footnotes', 'table': 'tables'}

def render(text, plugins):
    exts = [_EXT_MAP[p] for p in plugins if p in _EXT_MAP]
    markdown.markdown(text, extensions=exts)

render('warmup', PLUGINS)
n = 2125
times = []
crashed = None
limit = max(2125 * 4, 2125 + 1)
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
    if elapsed >= 1.0:
        break
    n *= 2

if crashed is not None:
    print(json.dumps({'defect': True, 'kind': KIND, 'crash': crashed}))
    sys.exit(1)
worst = 0.0
for (n1, t1), (n2, t2) in zip(times, times[1:]):
    if t1 >= 0.02 and n2 > n1:
        worst = max(worst, math.log2(max(t2, 1e-9) / t1) / math.log2(n2 / n1))
t_max = max((t for _, t in times), default=0.0)
defect = worst >= EXPONENT_THRESHOLD and t_max >= TIME_FLAG_FLOOR
print(json.dumps({'defect': defect, 'kind': KIND, 'exponent': round(worst, 3), 't_max': round(t_max, 4)}))
sys.exit(1 if defect else 0)
