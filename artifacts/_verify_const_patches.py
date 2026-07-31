from pathlib import Path

cc = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
ub = Path("src/blackhole_agent/unbound.py").read_text(encoding="utf-8")

checks = {
    "cc.run_constitution_plane": "def run_constitution_plane" in cc,
    "cc.builtin_constitution_plane": "def builtin_constitution_plane" in cc,
    "cc.CONSTITUTION_BUNDLE_SCHEMA": "CONSTITUTION_BUNDLE_SCHEMA" in cc,
    "cc.seed": 'id="capability.constitution-plane"' in cc,
    "cc.soft": '("constitution", ("capability.constitution-plane"' in cc,
    "cc.parse constitution_ok": '"constitution_ok"' in cc,
    "cc.eval constitution_ok": 'kind == "constitution_ok"' in cc or '"constitution_ok",' in cc,
    "cc.apply_charter_to_const": "apply_charter_bundle_to_constitutions" in cc,
    "cc.load_charter still": "def load_charter_bundle" in cc,
    "cc.run_charter still": "def run_charter_plane" in cc,
    "ub.import": "run_constitution_plane" in ub,
    "ub.run_constitution": "run_constitution = (" in ub,
    "ub.needs_constitution": "needs_constitution" in ub,
    "ub.handler": "if needs_constitution:" in ub,
    "ub.higher": "needs_constitution" in ub and "or needs_charter" in ub,
}

for k, v in checks.items():
    print(("OK" if v else "MISSING"), k)

# syntax
try:
    compile(cc, "capability_compounder.py", "exec")
    print("OK compile compounder")
except SyntaxError as e:
    print("FAIL compile compounder", e)

try:
    compile(ub, "unbound.py", "exec")
    print("OK compile unbound")
except SyntaxError as e:
    print("FAIL compile unbound", e)
