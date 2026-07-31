from pathlib import Path

cc = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
ub = Path("src/blackhole_agent/unbound.py").read_text(encoding="utf-8")

checks = {
    "cc.run_covenant_plane": "def run_covenant_plane" in cc,
    "cc.builtin_covenant_plane": "def builtin_covenant_plane" in cc,
    "cc.COVENANT_BUNDLE_SCHEMA": "COVENANT_BUNDLE_SCHEMA" in cc,
    "cc.seed": 'id="capability.covenant-plane"' in cc,
    "cc.soft": '("covenant", ("capability.covenant-plane"' in cc,
    "cc.parse covenant_ok": '"covenant_ok"' in cc,
    "cc.eval covenant_ok": '"covenant_ok"' in cc and "_load_covenant_disk_evidence" in cc,
    "cc.apply_const_to_cov": "apply_constitution_bundle_to_covenants" in cc,
    "cc.load_constitution still": "def load_constitution_bundle" in cc,
    "cc.run_constitution still": "def run_constitution_plane" in cc,
    "cc.parent kwargs run_charter": "run_charter=run_constitution" in cc,
    "cc.parent kwargs min_charters": "min_charters=want_constitutions" in cc,
    "ub.import": "run_covenant_plane" in ub,
    "ub.run_covenant": "run_covenant = (" in ub,
    "ub.needs_covenant": "needs_covenant" in ub,
    "ub.handler": "if needs_covenant:" in ub,
    "ub.higher": "needs_covenant" in ub and "or needs_constitution" in ub,
}

for k, v in checks.items():
    print(("OK" if v else "MISSING"), k)

for label, src in (("compounder", cc), ("unbound", ub)):
    try:
        compile(src, f"{label}.py", "exec")
        print("OK compile", label)
    except SyntaxError as e:
        print("FAIL compile", label, e)
