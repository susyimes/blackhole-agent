"""Upstream discovery plane: autonomous defect discovery in pinned vendored releases.

The repair plane (``upstream_repair``) stewards *documented* defects: a human
(or an upstream changelog) names the defect, and the campaign reproduces and
repairs it. Nothing discovers defects nobody documented. This module closes
that gap: given a stewardship target (a pinned, sha256-verified upstream
sdist), the discovery plane runs a battery of generic adversarial-input
generators against the pristine extracted tree in subprocess isolation and
grades behavior with two oracles. How generated text is fed to the target is
declared by the target itself: the manifest's ``driver.prelude`` snippet
defines ``render(text, plugins)`` and is embedded verbatim into probe workers
and synthesized repros, so this module carries no target-specific code.
``driver.runtime`` selects the probe interpreter: ``python`` workers run the
prelude with the extracted src dir on ``sys.path``; ``node`` workers run it
under ``node`` with ``TARGET_DIR`` bound to the extracted package root
(``require(TARGET_DIR)`` resolves the target's own package.json). Every
generator carries both a python and a JS source so the same adversarial
battery fires on either runtime:

- **crash oracle** — an uncaught exception (e.g. ``RecursionError``) on a
  generated input is a defect;
- **complexity oracle** — wall-clock time is measured over a doubling size
  ladder; a sustained growth exponent >= ``EXPONENT_THRESHOLD`` with absolute
  time above ``TIME_FLAG_FLOOR`` seconds is an algorithmic-complexity defect
  (DoS), and a probe run that exceeds its timeout is a severe instance of the
  same class.

Every generator that does *not* flag is recorded as a negative control: the
battery is honest only if it leaves benign shapes unflagged. For each finding
the plane minimizes the triggering size (binary search on the elapsed-time
floor), then *synthesizes a standalone repro script*: a self-contained python
or node file (matching ``driver.runtime``) that re-runs the ladder against
any source tree given on its command line and exits 1 while the defect is
present, 0 once repaired. The synthesized
repro must fail on the pristine tree (defect is real, not imagined) before it
is admitted into the sealed report.

The discovery plane never reads the manifest's ``defects`` list: findings are
measured, not curated. Determinism contract: only generator names, verdicts,
exit codes, minimized sizes, and sha256 digests of synthesized repros enter
the report digests. Timings and exponents are diagnostics and are excluded,
so verification is pure (recompute digests from recorded outcomes, re-hash
on-disk repro files); a tamper probe must fail verification.

Sealed reports land under ``artifacts/upstream-discovery/<target>/<ts>/``.

Two proof tiers share this evidence: the **live tier**
(``run_live_discovery_proof`` / CLI ``live-proof`` or ``scan``) re-runs the
full timing-ladder battery and seals fresh reports — minutes of wall-clock,
explicit evidence refresh only; the **registered proof**
(``builtin_upstream_discovery_proof`` / ``run_sealed_discovery_proof``) is
hermetic and bounded — it purely re-verifies each target's latest sealed
report, falsifies the verifier with a tampered copy in a throwaway
directory, and re-anchors each target with one bounded live probe (a flagged
finding's synthesized repro must still fail on a freshly extracted pristine
tree), so the proof fits the integrity batch budget.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from blackhole_agent.capability_compounder import (
    atomic_write_json,
    legacy_pipeline_was_used,
    utc_now_iso,
)
from blackhole_agent.durable_state import durable_read_path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
STEWARDSHIP_ROOT = REPO_ROOT / "stewardship"
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "upstream-discovery"

PROBE_TIMEOUT_SECONDS = 90
EXPONENT_THRESHOLD = 1.75
TIME_FLAG_FLOOR = 0.3  # absolute seconds below which timing is noise, not defect
TIME_STOP_FLOOR = 1.5  # stop growing the ladder once a run is this slow
REPRO_MINIMIZE_FLOOR = 0.75  # minimized repro size must take at least this long
LADDER_START = 1000
LADDER_MAX = 16000


# ---------------------------------------------------------------------------
# canonical hashing helpers (same convention as the other evidence planes)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# adversarial input generators
#
# Each generator is a *generic* adversarial markdown shape parameterized by a
# size n, plus the plugin set the renderer must be built with. The source of
# each generator function is embedded verbatim into synthesized repros, so
# keep every generator self-contained (no closures, stdlib only).

GENERATORS: dict[str, dict[str, Any]] = {
    "nested_link": {
        "plugins": [],
        "source": "def gen(n):\n    return '[' * n + 'a' + ']' * n\n",
        "js_source": "function gen(n) {\n    return '['.repeat(n) + 'a' + ']'.repeat(n);\n}\n",
        "summary": "n nested open/close link brackets around one token",
    },
    "nested_image": {
        "plugins": [],
        "source": "def gen(n):\n    return '![' * n + 'a' + ']' * n\n",
        "js_source": "function gen(n) {\n    return '!['.repeat(n) + 'a' + ']'.repeat(n);\n}\n",
        "summary": "n nested image open brackets, one token, n close brackets",
    },
    "nested_emphasis": {
        "plugins": [],
        "source": "def gen(n):\n    return '**' * n + 'a' + '**' * n\n",
        "js_source": "function gen(n) {\n    return '**'.repeat(n) + 'a' + '**'.repeat(n);\n}\n",
        "summary": "n pairs of emphasis markers around one token",
    },
    "unclosed_emphasis": {
        "plugins": [],
        "source": "def gen(n):\n    return '**a' * n\n",
        "js_source": "function gen(n) {\n    return '**a'.repeat(n);\n}\n",
        "summary": "n unclosed strong-emphasis markers",
    },
    "link_suffixes": {
        "plugins": [],
        "source": "def gen(n):\n    return '[a' + ']' * n\n",
        "js_source": "function gen(n) {\n    return '[a' + ']'.repeat(n);\n}\n",
        "summary": "one open bracket followed by n unmatched close brackets",
    },
    "backtick_runs": {
        "plugins": [],
        "source": "def gen(n):\n    return '`' * n + 'a' + '`' * n\n",
        "js_source": "function gen(n) {\n    return '`'.repeat(n) + 'a' + '`'.repeat(n);\n}\n",
        "summary": "matched runs of n backticks around one token",
    },
    "footnote_refs": {
        "plugins": ["footnotes"],
        "source": (
            "def gen(n):\n"
            "    refs = ''.join('[%d]' % i for i in range(n))\n"
            "    defs = '\\n'.join('[%d]: x' % i for i in range(n))\n"
            "    return refs + '\\n\\n' + defs\n"
        ),
        "js_source": (
            "function gen(n) {\n"
            "    let refs = '';\n"
            "    let defs = [];\n"
            "    for (let i = 0; i < n; i++) { refs += '[' + i + ']'; defs.push('[' + i + ']: x'); }\n"
            "    return refs + '\\n\\n' + defs.join('\\n');\n"
            "}\n"
        ),
        "summary": "n footnote references with n footnote definitions",
    },
    "footnote_defs": {
        "plugins": ["footnotes"],
        "source": (
            "def gen(n):\n"
            "    refs = ''.join('[^%d] ' % i for i in range(n))\n"
            "    defs = '\\n'.join('[^%d]: x' % i for i in range(n))\n"
            "    return refs + '\\n\\n' + defs\n"
        ),
        "js_source": (
            "function gen(n) {\n"
            "    let refs = '';\n"
            "    let defs = [];\n"
            "    for (let i = 0; i < n; i++) { refs += '[^' + i + '] '; defs.push('[^' + i + ']: x'); }\n"
            "    return refs + '\\n\\n' + defs.join('\\n');\n"
            "}\n"
        ),
        "summary": "n caret-footnote references with n caret-footnote definitions",
    },
    "inline_links": {
        "plugins": [],
        "source": "def gen(n):\n    return '[l](u) ' * n\n",
        "js_source": "function gen(n) {\n    return '[l](u) '.repeat(n);\n}\n",
        "summary": "n valid inline links in one paragraph",
    },
    "unclosed_spoiler": {
        "plugins": ["spoiler"],
        "source": "def gen(n):\n    return '~~a ' * n\n",
        "js_source": "function gen(n) {\n    return '~~a '.repeat(n);\n}\n",
        "summary": "n unclosed inline spoiler markers",
    },
    "adjacent_ruby": {
        "plugins": ["ruby"],
        "source": "def gen(n):\n    return 'a(b)' * n\n",
        "js_source": "function gen(n) {\n    return 'a(b)'.repeat(n);\n}\n",
        "summary": "n adjacent ruby tokens",
    },
    "table_row": {
        "plugins": ["table"],
        "source": (
            "def gen(n):\n"
            "    return '|' + 'a|' * n + '\\n' + '|' + '-|' * n + '\\n' + '|' + 'b|' * n\n"
        ),
        "js_source": (
            "function gen(n) {\n"
            "    return '|' + 'a|'.repeat(n) + '\\n' + '|' + '-|'.repeat(n) + '\\n' + '|' + 'b|'.repeat(n);\n"
            "}\n"
        ),
        "summary": "a table whose rows have n cells",
    },
    "digit_run": {
        "plugins": [],
        "source": "def gen(n):\n    return '8' * n\n",
        "js_source": "function gen(n) {\n    return '8'.repeat(n);\n}\n",
        "summary": "a run of n decimal digit characters",
    },
    "dotted_key": {
        "plugins": [],
        "source": "def gen(n):\n    return '.'.join('a%d' % i for i in range(n)) + ' = 1'\n",
        "js_source": (
            "function gen(n) {\n"
            "    let parts = [];\n"
            "    for (let i = 0; i < n; i++) { parts.push('a' + i); }\n"
            "    return parts.join('.') + ' = 1';\n"
            "}\n"
        ),
        "summary": "one dotted key with n parts assigned a value",
    },
}


# ---------------------------------------------------------------------------
# probe worker (subprocess-isolated timing/crash measurement)

_WORKER = r"""
import json, sys, time

src_dir, name, n_raw, plugins_csv = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
n = int(n_raw)
plugins = [p for p in plugins_csv.split(',') if p]
sys.path.insert(0, src_dir)

GENERATORS = {}

__GENERATOR_SOURCES__

__DRIVER_PRELUDE__

try:
    text = GENERATORS[name](n)
    render('warmup', plugins)
    t0 = time.perf_counter()
    render(text, plugins)
    elapsed = time.perf_counter() - t0
    print(json.dumps({'elapsed': elapsed, 'crashed': False, 'exc': None}))
except Exception as e:  # crash oracle
    print(json.dumps({'elapsed': None, 'crashed': True, 'exc': type(e).__name__}))
"""


def _worker_source(driver_prelude: str) -> str:
    sources = []
    for name, spec in GENERATORS.items():
        fn_src = spec["source"].rstrip("\n")
        sources.append(f"{fn_src}\nGENERATORS[{name!r}] = gen\ndel gen")
    return _WORKER.replace("__GENERATOR_SOURCES__", "\n\n".join(sources)).replace(
        "__DRIVER_PRELUDE__", driver_prelude.rstrip("\n")
    )


_NODE_WORKER = r"""
"use strict";
const TARGET_DIR = process.argv[2];
const name = process.argv[3];
const n = parseInt(process.argv[4], 10);
const plugins = (process.argv[5] || "").split(",").filter(Boolean);

const GENERATORS = {};

__GENERATOR_SOURCES__

__DRIVER_PRELUDE__

(async () => {
    try {
        const text = GENERATORS[name](n);
        await render("warmup", plugins);
        const t0 = process.hrtime.bigint();
        await render(text, plugins);
        const elapsed = Number(process.hrtime.bigint() - t0) / 1e9;
        console.log(JSON.stringify({ elapsed: elapsed, crashed: false, exc: null }));
    } catch (e) {
        const exc = (e && e.constructor && e.constructor.name) || "Error";
        console.log(JSON.stringify({ elapsed: null, crashed: true, exc: exc }));
    }
})();
"""


def _node_worker_source(driver_prelude: str) -> str:
    sources = []
    for name, spec in GENERATORS.items():
        fn_src = spec["js_source"].rstrip("\n")
        # Block-scope each registration: bare function declarations hoist to
        # the top of the script, so without braces every GENERATORS entry
        # would bind the *last* declared gen.
        sources.append(f"{{\n{fn_src}\nGENERATORS[{json.dumps(name)}] = gen;\n}}")
    return _NODE_WORKER.replace("__GENERATOR_SOURCES__", "\n\n".join(sources)).replace(
        "__DRIVER_PRELUDE__", driver_prelude.rstrip("\n")
    )


def _find_node() -> str:
    node = shutil.which("node")
    if node is None:
        raise ValueError("node runtime not found on PATH; cannot probe a node-runtime target")
    return node


@dataclass(frozen=True)
class ProbeResult:
    elapsed: float | None
    crashed: bool
    exc: str | None
    timed_out: bool


def run_probe(
    src_dir: Path, generator: str, n: int, driver_prelude: str, runtime: str = "python"
) -> ProbeResult:
    """Measure one generator at one size against src_dir in a subprocess."""
    plugins = ",".join(GENERATORS[generator]["plugins"])
    if runtime == "node":
        cmd = None
        scratch = tempfile.TemporaryDirectory(prefix="probe-node-")
        worker_path = Path(scratch.name) / "worker.cjs"
        worker_path.write_bytes(_node_worker_source(driver_prelude).encode("utf-8"))
        cmd = [_find_node(), str(worker_path), str(src_dir), generator, str(n), plugins]
    elif runtime == "python":
        scratch = None
        cmd = [
            sys.executable,
            "-c",
            _worker_source(driver_prelude),
            str(src_dir),
            generator,
            str(n),
            plugins,
        ]
    else:
        raise ValueError(f"unsupported driver runtime: {runtime!r}")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(elapsed=None, crashed=False, exc=None, timed_out=True)
    finally:
        if scratch is not None:
            scratch.cleanup()
    line = proc.stdout.strip().splitlines()
    if not line:
        return ProbeResult(
            elapsed=None, crashed=True, exc=f"worker exited {proc.returncode}", timed_out=False
        )
    payload = json.loads(line[-1])
    return ProbeResult(
        elapsed=payload.get("elapsed"),
        crashed=bool(payload.get("crashed")),
        exc=payload.get("exc"),
        timed_out=False,
    )


def _max_exponent(times: list[tuple[int, float]]) -> float:
    """Largest per-doubling growth exponent over measured (size, seconds) pairs."""
    worst = 0.0
    for (n1, t1), (n2, t2) in zip(times, times[1:]):
        if t1 >= 0.02 and n2 > n1:
            worst = max(worst, math.log2(max(t2, 1e-9) / t1) / math.log2(n2 / n1))
    return worst


def probe_ladder(
    src_dir: Path, generator: str, driver_prelude: str, runtime: str = "python"
) -> dict[str, Any]:
    """Run the doubling ladder for one generator; return measurement + verdict."""
    times: list[tuple[int, float]] = []
    crash: dict[str, Any] | None = None
    timeout_n: int | None = None
    n = LADDER_START
    while n <= LADDER_MAX:
        result = run_probe(src_dir, generator, n, driver_prelude, runtime)
        if result.timed_out:
            timeout_n = n
            break
        if result.crashed:
            crash = {"n": n, "exc": result.exc}
            break
        assert result.elapsed is not None
        times.append((n, result.elapsed))
        if result.elapsed >= TIME_STOP_FLOOR:
            break
        n *= 2
    exponent = _max_exponent(times)
    t_max = max((t for _, t in times), default=0.0)
    if crash is not None:
        kind, flagged = "crash", True
    elif timeout_n is not None:
        kind, flagged = "timeout", True
    else:
        kind = "complexity"
        flagged = exponent >= EXPONENT_THRESHOLD and t_max >= TIME_FLAG_FLOOR
    return {
        "generator": generator,
        "kind": kind,
        "flagged": flagged,
        "crash": crash,
        "timeout_n": timeout_n,
        "exponent": round(exponent, 3),  # diagnostic only; excluded from digests
        "times": [[n, round(t, 4)] for n, t in times],  # diagnostics only
        "t_max": round(t_max, 4),
    }


def minimize_size(
    src_dir: Path, generator: str, ladder: dict[str, Any], driver_prelude: str, runtime: str = "python"
) -> int:
    """Binary-search the smallest size whose run exceeds the repro floor."""
    if ladder["crash"] is not None:
        target_n = int(ladder["crash"]["n"])
    elif ladder["timeout_n"] is not None:
        target_n = int(ladder["timeout_n"])
    else:
        flagged = [n for n, t in ladder["times"] if t >= REPRO_MINIMIZE_FLOOR]
        if not flagged:
            return int(ladder["times"][-1][0])
        target_n = flagged[0]
    lo, hi = max(1, target_n // 2), target_n
    while hi - lo > max(8, hi // 16):
        mid = (lo + hi) // 2
        result = run_probe(src_dir, generator, mid, driver_prelude, runtime)
        if result.crashed or result.timed_out or (result.elapsed or 0.0) >= REPRO_MINIMIZE_FLOOR:
            hi = mid
        else:
            lo = mid
    return hi


# ---------------------------------------------------------------------------
# repro synthesis

_REPRO_TEMPLATE = '''\
"""Synthesized standalone repro for the {generator} defect ({kind}).

Discovered autonomously by blackhole_agent.upstream_discovery. Runs a doubling
ladder against the source tree given as argv[1]; exits 1 while the defect is
present, 0 once repaired. Usage: python <this file> <path-to-src-dir>
"""
import json, math, sys, time

sys.path.insert(0, sys.argv[1])
PLUGINS = {plugins!r}
KIND = {kind!r}
EXPONENT_THRESHOLD = {exp_threshold!r}
TIME_FLAG_FLOOR = {time_floor!r}

{gen_src}

{prelude}

render('warmup', PLUGINS)
n = {start}
times = []
crashed = None
limit = max({start} * 4, {start} + 1)
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
        # Always measure at least two sizes: one load-inflated run must not
        # end the ladder before any growth pair exists.
        break
    n *= 2

if crashed is not None:
    print(json.dumps({{'defect': True, 'kind': KIND, 'crash': crashed}}))
    sys.exit(1)
worst = 0.0
for (n1, t1), (n2, t2) in zip(times, times[1:]):
    if t1 >= 0.02 and n2 > n1:
        worst = max(worst, math.log2(max(t2, 1e-9) / t1) / math.log2(n2 / n1))
t_max = max((t for _, t in times), default=0.0)
defect = worst >= EXPONENT_THRESHOLD and t_max >= TIME_FLAG_FLOOR
print(json.dumps({{'defect': defect, 'kind': KIND, 'exponent': round(worst, 3), 't_max': round(t_max, 4)}}))
sys.exit(1 if defect else 0)
'''


_NODE_REPRO_TEMPLATE = r"""// Synthesized standalone repro for the __GENERATOR__ defect (__KIND__).
//
// Discovered autonomously by blackhole_agent.upstream_discovery. Runs a
// doubling ladder against the source tree given as argv[2]; exits 1 while
// the defect is present, 0 once repaired. Usage: node <this file> <path-to-package-root>
"use strict";
const TARGET_DIR = process.argv[2];
const PLUGINS = __PLUGINS__;
const KIND = __KIND__;
const EXPONENT_THRESHOLD = __EXP_THRESHOLD__;
const TIME_FLAG_FLOOR = __TIME_FLOOR__;

__GEN_SRC__

__PRELUDE__

(async () => {
    await render("warmup", PLUGINS);
    let n = __START__;
    const times = [];
    let crashed = null;
    const limit = Math.max(__START__ * 4, __START__ + 1);
    while (n <= limit) {
        const text = gen(n);
        const t0 = process.hrtime.bigint();
        try {
            await render(text, PLUGINS);
        } catch (e) {
            crashed = (e && e.constructor && e.constructor.name) || "Error";
            break;
        }
        const elapsed = Number(process.hrtime.bigint() - t0) / 1e9;
        times.push([n, elapsed]);
        if (elapsed >= 1.0 && times.length >= 2) {
            // Always measure at least two sizes: one load-inflated run must
            // not end the ladder before any growth pair exists.
            break;
        }
        n *= 2;
    }
    if (crashed !== null) {
        console.log(JSON.stringify({ defect: true, kind: KIND, crash: crashed }));
        process.exit(1);
    }
    let worst = 0.0;
    for (let i = 0; i + 1 < times.length; i++) {
        const n1 = times[i][0], t1 = times[i][1], n2 = times[i + 1][0], t2 = times[i + 1][1];
        if (t1 >= 0.02 && n2 > n1) {
            worst = Math.max(worst, Math.log2(Math.max(t2, 1e-9) / t1) / Math.log2(n2 / n1));
        }
    }
    const tMax = times.reduce((m, pair) => Math.max(m, pair[1]), 0.0);
    const defect = worst >= EXPONENT_THRESHOLD && tMax >= TIME_FLAG_FLOOR;
    console.log(JSON.stringify({
        defect: defect, kind: KIND,
        exponent: Math.round(worst * 1000) / 1000, t_max: Math.round(tMax * 10000) / 10000,
    }));
    process.exit(defect ? 1 : 0);
})();
"""


def synthesize_repro(
    generator: str,
    kind: str,
    minimized_n: int,
    dest: Path,
    driver_prelude: str,
    runtime: str = "python",
) -> Path:
    """Write a standalone repro script for one finding; return its path."""
    spec = GENERATORS[generator]
    if runtime == "node":
        content = (
            _NODE_REPRO_TEMPLATE.replace("__GENERATOR__", generator)
            .replace("__KIND__", json.dumps(kind))
            .replace("__PLUGINS__", json.dumps(spec["plugins"]))
            .replace("__GEN_SRC__", spec["js_source"].rstrip("\n"))
            .replace("__PRELUDE__", driver_prelude.rstrip("\n"))
            .replace("__START__", str(minimized_n))
            .replace("__EXP_THRESHOLD__", repr(EXPONENT_THRESHOLD))
            .replace("__TIME_FLOOR__", repr(TIME_FLAG_FLOOR))
        )
        path = dest / f"{generator}.cjs"
    elif runtime == "python":
        content = _REPRO_TEMPLATE.format(
            generator=generator,
            kind=kind,
            plugins=spec["plugins"],
            gen_src=spec["source"].rstrip("\n"),
            prelude=driver_prelude.rstrip("\n"),
            start=minimized_n,
            exp_threshold=EXPONENT_THRESHOLD,
            time_floor=TIME_FLAG_FLOOR,
        )
        path = dest / f"{generator}.py"
    else:
        raise ValueError(f"unsupported driver runtime: {runtime!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write bytes, not text: repro_sha256 must be host-independent, and CRLF
    # translation on Windows would change the sealed evidence hash.
    path.write_bytes(content.encode("utf-8"))
    return path


def run_repro(repro: Path, src_dir: Path) -> int:
    if repro.suffix == ".cjs":
        cmd = [_find_node(), str(repro), str(src_dir)]
    else:
        cmd = [sys.executable, str(repro), str(src_dir)]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_SECONDS,
    )
    return proc.returncode


# ---------------------------------------------------------------------------
# target loading + pristine extraction (provenance identical to repair plane)


@dataclass(frozen=True)
class DiscoveryTarget:
    root: Path
    name: str
    version: str
    sdist: Path
    sdist_sha256: str
    src_subdir: str
    driver_prelude: str
    driver_runtime: str = "python"


def load_target(target_root: Path) -> DiscoveryTarget:
    """Load a stewardship manifest, deliberately ignoring its 'defects' list.

    The manifest's ``driver.prelude`` is a self-contained snippet (stdlib +
    the target's own package only) that defines ``render(text, plugins)``:
    build the target's renderer over the extracted source tree and render
    ``text`` with the generator's option list. ``driver.runtime`` selects
    the probe interpreter (``python`` or ``node``; absent means ``python``
    for backward compatibility with pre-npm manifests). All target
    specificity lives here, not in this module.
    """
    manifest = json.loads(durable_read_path(target_root / "manifest.json").read_text(encoding="utf-8"))
    driver = manifest["driver"]
    return DiscoveryTarget(
        root=target_root,
        name=manifest["name"],
        version=manifest["version"],
        sdist=target_root / manifest["sdist"],
        sdist_sha256=manifest["sdist_sha256"],
        src_subdir=manifest["src_subdir"],
        driver_prelude=driver["prelude"],
        driver_runtime=driver.get("runtime", "python"),
    )


def extract_pristine(target: DiscoveryTarget, dest: Path) -> Path:
    """Verify provenance then extract; returns the importable src dir."""
    actual = _sha256_file(target.sdist)
    if actual != target.sdist_sha256:
        raise ValueError(
            f"sdist provenance mismatch for {target.name}-{target.version}: "
            f"expected {target.sdist_sha256}, got {actual}"
        )
    with tarfile.open(target.sdist, "r:gz") as tar:
        tar.extractall(dest, filter="data")
    return dest / target.src_subdir


def discover_targets() -> list[Path]:
    if not STEWARDSHIP_ROOT.exists():
        return []
    return sorted(
        p for p in STEWARDSHIP_ROOT.iterdir() if (p / "manifest.json").exists()
    )


# ---------------------------------------------------------------------------
# sealed report


def _finding_digest_entry(finding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "generator": finding["generator"],
        "kind": finding["kind"],
        "flagged": finding["flagged"],
        "minimized_n": finding.get("minimized_n"),
        "repro_sha256": finding.get("repro_sha256"),
        "pristine_repro_exit": finding.get("pristine_repro_exit"),
    }


def _report_chain(report: Mapping[str, Any]) -> str:
    return _digest(
        {
            "schema_version": report["schema_version"],
            "target": report["target"],
            "sdist_sha256": report["sdist_sha256"],
            "generators": [_finding_digest_entry(f) for f in report["findings"]],
        }
    )


def run_discovery_scan(
    target_root: Path,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    """Scan one stewardship target; synthesize repros; seal the report."""
    target = load_target(target_root)
    artifact_root = artifact_root or (ARTIFACT_DIR / f"{target.name}-{target.version}")
    report_dir = artifact_root / utc_now_iso().replace(":", "").replace("-", "")
    scratch = Path(tempfile.mkdtemp(prefix="upstream-discovery-"))
    try:
        src_dir = extract_pristine(target, scratch)
        prelude = target.driver_prelude
        runtime = target.driver_runtime
        findings: list[dict[str, Any]] = []
        for generator in GENERATORS:
            ladder = probe_ladder(src_dir, generator, prelude, runtime)
            finding: dict[str, Any] = {
                "generator": generator,
                "kind": ladder["kind"],
                "flagged": ladder["flagged"],
                "exponent": ladder["exponent"],
                "times": ladder["times"],
            }
            if ladder["flagged"]:
                minimized = minimize_size(src_dir, generator, ladder, prelude, runtime)
                repro = synthesize_repro(
                    generator, ladder["kind"], minimized, report_dir / "repros", prelude, runtime
                )
                pristine_exit = run_repro(repro, src_dir)
                finding.update(
                    minimized_n=minimized,
                    repro=str(repro.relative_to(report_dir)),
                    repro_sha256=_sha256_file(repro),
                    pristine_repro_exit=pristine_exit,
                )
                if pristine_exit == 0:
                    finding["flagged"] = False
                    finding["retracted"] = "synthesized repro passed on pristine tree"
            findings.append(finding)

        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "target": {"name": target.name, "version": target.version},
            "sdist_sha256": target.sdist_sha256,
            "driver_runtime": runtime,
            "findings": findings,
            "finding_count": sum(1 for f in findings if f["flagged"]),
            "scanned_at": utc_now_iso(),
        }
        report["chain_digest"] = _report_chain(report)
        report_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(report_dir / "report.json", report)
        return {
            "ok": True,
            "report_dir": str(report_dir),
            "finding_count": report["finding_count"],
            "findings": [
                {
                    "generator": f["generator"],
                    "flagged": f["flagged"],
                    "kind": f["kind"],
                    "exponent": f.get("exponent"),
                }
                for f in findings
            ],
        }
    except Exception as exc:  # provenance mismatch etc. fail closed
        return {"ok": False, "error": str(exc)}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def load_latest_report_dir(artifact_root: Path) -> Path | None:
    if not artifact_root.exists():
        return None
    # Only timestamped scan directories are evidence; auxiliary directories
    # (e.g. historical tamper-probe forgeries written by the legacy live
    # proof) sort last and must never be selected as the latest report.
    candidates = sorted(
        p
        for p in artifact_root.iterdir()
        if p.name[:1].isdigit() and (p / "report.json").exists()
    )
    return candidates[-1] if candidates else None


def verify_discovery_report(report_dir: Path) -> dict[str, Any]:
    """Purely re-verify a sealed report: recompute digests, re-hash repros."""
    problems: list[str] = []
    report = json.loads(durable_read_path(report_dir / "report.json").read_text(encoding="utf-8"))
    if _report_chain(report) != report.get("chain_digest"):
        problems.append("chain digest mismatch: recorded outcomes were tampered")
    for finding in report.get("findings", []):
        repro_rel = finding.get("repro")
        if not repro_rel:
            continue
        repro_path = report_dir / repro_rel
        if not repro_path.exists():
            problems.append(f"missing repro file {repro_rel}")
        elif _sha256_file(repro_path) != finding.get("repro_sha256"):
            problems.append(f"repro {repro_rel} hash mismatch: evidence file tampered")
    return {"ok": not problems, "problems": problems}


# ---------------------------------------------------------------------------
# registered proof (two-tier: live scan tier + hermetic sealed-verification tier)


def run_live_discovery_proof() -> dict[str, Any]:
    """Live-tier proof: fresh timing-ladder scans over every target.

    Re-runs the full doubling-ladder scan per stewardship target, seals fresh
    reports, verifies them, and falsifies each verifier with a tampered copy.
    This takes minutes (real complexity measurements) and is the explicit
    evidence-refresh path — not the registered proof.
    """
    roots = discover_targets()
    if not roots:
        return {"ok": False, "error": "no stewardship targets"}
    total_findings = 0
    all_verified = True
    all_tamper_detected = True
    per_target: list[dict[str, Any]] = []
    for root in roots:
        scan = run_discovery_scan(root)
        entry: dict[str, Any] = {
            "target_root": str(root),
            "ok": scan.get("ok"),
            "finding_count": scan.get("finding_count"),
        }
        if not scan.get("ok"):
            entry["error"] = scan.get("error")
            all_verified = False
            per_target.append(entry)
            continue
        report_dir = Path(scan["report_dir"])
        verification = verify_discovery_report(report_dir)
        entry["verified"] = verification["ok"]
        all_verified = all_verified and verification["ok"]
        total_findings += int(scan.get("finding_count") or 0)

        # falsify the verifier: one flipped verdict must be detected
        report = json.loads(durable_read_path(report_dir / "report.json").read_text(encoding="utf-8"))
        report["findings"][0]["flagged"] = not report["findings"][0]["flagged"]
        with tempfile.TemporaryDirectory(prefix="upstream-discovery-tamper-") as tmp:
            tamper_dir = Path(tmp) / "tampered"
            tamper_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(tamper_dir / "report.json", report)
            tamper_verdict = verify_discovery_report(tamper_dir)
        entry["tamper_detected"] = not tamper_verdict["ok"]
        all_tamper_detected = all_tamper_detected and entry["tamper_detected"]
        per_target.append(entry)
    ok = total_findings >= 1 and all_verified and all_tamper_detected
    return {
        "ok": ok,
        "proof_mode": "live",
        "target_count": len(roots),
        "finding_count": total_findings,
        "verified": all_verified,
        "tamper_detected": all_tamper_detected,
        "targets": per_target,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def run_sealed_discovery_proof(
    artifact_dir: Path = ARTIFACT_DIR,
) -> dict[str, Any]:
    """Hermetic, bounded proof of the discovery plane across every target.

    Per target: purely re-verify the latest sealed scan report (chain digest
    + repro evidence hashes), falsify the verifier with a tampered copy in a
    throwaway directory, and re-anchor with a bounded live probe — one
    flagged finding's synthesized repro, re-executed against a freshly
    extracted pristine tree, must still exit non-zero. Result keys mirror the
    live tier so the registered ledger proof command is unchanged.
    """
    import time as _time

    start = _time.monotonic()
    roots = discover_targets()
    if not roots:
        return {"ok": False, "error": "no stewardship targets"}
    total_findings = 0
    all_verified = True
    all_tamper_detected = True
    all_probes_ok = True
    per_target: list[dict[str, Any]] = []
    for root in roots:
        target = load_target(root)
        entry: dict[str, Any] = {"target_root": str(root)}
        artifact_root = artifact_dir / f"{target.name}-{target.version}"
        report_dir = load_latest_report_dir(artifact_root)
        if report_dir is None:
            entry.update(
                {
                    "ok": False,
                    "error": "no sealed discovery report: run the live scan tier to seal one",
                    "verified": False,
                    "tamper_detected": False,
                    "live_probe": {"ok": False, "error": "not run: no sealed report"},
                }
            )
            all_verified = False
            all_tamper_detected = False
            all_probes_ok = False
            per_target.append(entry)
            continue

        verification = verify_discovery_report(report_dir)
        entry["verified"] = verification["ok"]
        entry["verify_problems"] = verification.get("problems", [])
        all_verified = all_verified and verification["ok"]

        report = json.loads(durable_read_path(report_dir / "report.json").read_text(encoding="utf-8"))
        findings = report.get("findings", [])
        entry["finding_count"] = int(report.get("finding_count") or 0)
        total_findings += entry["finding_count"]

        # Verifier honesty: one flipped verdict in a throwaway copy must be
        # detected. Proofs never write into the artifacts tree.
        tampered_report = json.loads(json.dumps(report))
        if findings:
            tampered_report["findings"][0]["flagged"] = not tampered_report["findings"][0]["flagged"]
        with tempfile.TemporaryDirectory(prefix="upstream-discovery-tamper-") as tmp:
            tamper_dir = Path(tmp) / "tampered"
            tamper_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(tamper_dir / "report.json", tampered_report)
            tamper_verdict = verify_discovery_report(tamper_dir)
        entry["tamper_detected"] = not tamper_verdict["ok"] if findings else False
        all_tamper_detected = all_tamper_detected and entry["tamper_detected"]

        # Bounded live probe: the first flagged finding's synthesized repro
        # must still fail on a freshly extracted pristine tree.
        flagged = sorted(
            (f for f in findings if f.get("flagged") and f.get("repro") and f.get("pristine_repro_exit")),
            key=lambda f: str(f.get("generator")),
        )
        if not flagged:
            entry["live_probe"] = {"ok": True, "skipped": "no flagged finding with repro"}
        else:
            finding = flagged[0]
            scratch = Path(tempfile.mkdtemp(prefix="upstream-discovery-probe-"))
            try:
                src_dir = extract_pristine(target, scratch)
                probe_exit = run_repro(report_dir / str(finding["repro"]), src_dir)
            except Exception as exc:  # provenance mismatch etc. fail closed
                entry["live_probe"] = {"ok": False, "error": str(exc)}
            else:
                entry["live_probe"] = {
                    "ok": probe_exit != 0,
                    "generator": finding.get("generator"),
                    "probe_exit": probe_exit,
                    "recorded_pristine_exit": finding.get("pristine_repro_exit"),
                }
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
        all_probes_ok = all_probes_ok and entry["live_probe"]["ok"]

        entry["report_dir"] = str(report_dir)
        entry["ok"] = bool(entry["verified"] and entry["tamper_detected"] and entry["live_probe"]["ok"])
        per_target.append(entry)

    ok = total_findings >= 1 and all_verified and all_tamper_detected and all_probes_ok
    return {
        "ok": ok,
        "proof_mode": "hermetic-sealed-verification+live-probe",
        "target_count": len(roots),
        "finding_count": total_findings,
        "verified": all_verified,
        "tamper_detected": all_tamper_detected,
        "live_probes_ok": all_probes_ok,
        "wall_clock_seconds": round(_time.monotonic() - start, 3),
        "targets": per_target,
        "used_skill_route_discovery": legacy_pipeline_was_used(),
    }


def builtin_upstream_discovery_proof() -> dict[str, Any]:
    """Prove the discovery plane: sealed findings, confirmed repros, honest seals.

    Registered ledger proof: hermetic sealed-report re-verification plus a
    bounded live probe per target, so the proof fits the integrity batch
    budget. The full live scan (``run_live_discovery_proof`` / CLI ``scan``)
    remains the explicit evidence-refresh path.
    """
    return run_sealed_discovery_proof()


# ---------------------------------------------------------------------------
# CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="upstream discovery plane")
    sub = parser.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan", help="scan stewardship target(s) and seal report(s)")
    scan_p.add_argument("target", nargs="?", default=None, help="stewardship target dir (default: all)")
    verify_p = sub.add_parser("verify", help="purely verify a sealed report")
    verify_p.add_argument("report_dir")
    sub.add_parser("live-proof", help="run the live-tier proof (fresh scans; takes minutes)")
    sub.add_parser("proof", help="run the registered hermetic proof (sealed verification + live probe)")
    args = parser.parse_args(argv)

    if args.command == "live-proof":
        result = run_live_discovery_proof()
        print(json.dumps({k: v for k, v in result.items() if k != "targets"}, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "scan":
        roots = [Path(args.target)] if args.target else discover_targets()
        all_ok = True
        summary = []
        for root in roots:
            scan = run_discovery_scan(root)
            all_ok = all_ok and bool(scan.get("ok"))
            summary.append(
                {
                    "target": str(root),
                    "ok": scan.get("ok"),
                    "finding_count": scan.get("finding_count"),
                    "findings": [f for f in scan.get("findings", []) if f.get("flagged")],
                    "report_dir": scan.get("report_dir"),
                    "error": scan.get("error"),
                }
            )
        print(json.dumps({"ok": all_ok, "scans": summary}, indent=2))
        return 0 if all_ok else 1
    if args.command == "verify":
        verdict = verify_discovery_report(Path(args.report_dir))
        print(json.dumps(verdict, indent=2))
        return 0 if verdict["ok"] else 1
    result = builtin_upstream_discovery_proof()
    print(json.dumps({k: v for k, v in result.items() if k != "targets"}, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
