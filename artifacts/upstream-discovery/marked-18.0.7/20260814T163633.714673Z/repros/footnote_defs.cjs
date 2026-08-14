// Synthesized standalone repro for the footnote_defs defect ("complexity").
//
// Discovered autonomously by blackhole_agent.upstream_discovery. Runs a
// doubling ladder against the source tree given as argv[2]; exits 1 while
// the defect is present, 0 once repaired. Usage: node <this file> <path-to-package-root>
"use strict";
const TARGET_DIR = process.argv[2];
const PLUGINS = ["footnotes"];
const KIND = "complexity";
const EXPONENT_THRESHOLD = 1.75;
const TIME_FLAG_FLOOR = 0.3;

function gen(n) {
    let refs = '';
    let defs = [];
    for (let i = 0; i < n; i++) { refs += '[^' + i + '] '; defs.push('[^' + i + ']: x'); }
    return refs + '\n\n' + defs.join('\n');
}

// Node driver prelude for the marked markdown renderer (npm frontier target).
// TARGET_DIR is bound by the frontier plane to the extracted package root;
// require(TARGET_DIR) resolves through marked's own package.json main field.
function render(text, plugins) {
    const { marked } = require(TARGET_DIR);
    return marked.parse(text);
}

(async () => {
    await render("warmup", PLUGINS);
    let n = 3000;
    const times = [];
    let crashed = null;
    const limit = Math.max(3000 * 4, 3000 + 1);
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
