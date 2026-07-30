from pathlib import Path
import re

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
i = text.find("def run_capital_plane(")
j = text.find("def builtin_capital_plane", i)
chunk = text[i:j]
# final return
k = chunk.rfind('return {\n        "ok": ok,\n        "action": "capital_plane"')
print(chunk[k : k + 2500])
print("--- solvency parent load ---")
sp = text.find("# Solvency plane over capital")
se = text.find("def seed_bootstrap_capabilities(", sp)
block = text[sp:se]
k = block.find("c_path = Path")
print(block[k : k + 500])
print("--- capital return capital key ---")
for m in re.finditer(r'"capital": \{[^}]{0,400}', chunk):
    s = m.group(0)
    if "bundle_path" in s or "capital_hash" in s:
        print(s[:400])
        print("---")
