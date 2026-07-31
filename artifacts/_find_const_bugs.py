from pathlib import Path
import re

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
start = text.find("CONSTITUTION_BUNDLE_SCHEMA = 1")
end = text.find("def seed_bootstrap_capabilities")
block = text[start:end]
for pat in [
    "run_privilege",
    "min_privileges",
    "run_mandate",
    "min_mandates",
    "privileged",
    "mandated",
    "wrong_privilege",
    "wrong_mandate",
    "run_charter_plane(",
    "BLACKHOLE_CHARTER_RUN",
    "charter_path=",
    "mandate_path=",
]:
    hits = list(re.finditer(pat, block))
    print(pat, len(hits))
    for h in hits[:8]:
        abs_pos = start + h.start()
        ln = text[:abs_pos].count("\n") + 1
        line_start = block.rfind("\n", 0, h.start()) + 1
        line_end = block.find("\n", h.start())
        print(f"  L{ln}: {block[line_start:line_end].strip()[:120]}")
