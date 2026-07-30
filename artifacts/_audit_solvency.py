from pathlib import Path
import re

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
p = text.find("def apply_solvency_transition")
print(text[p + 2500 : p + 4500])
print("---")
i = text.find("def run_capital_plane(")
j = text.find("def builtin_capital_plane", i)
chunk = text[i:j]
print("capital key count", chunk.count('"capital":'))
print("funding key count", chunk.count('"funding":'))
k = chunk.find('"funding": None')
print(chunk[k : k + 700] if k >= 0 else "no funding None")
print("--- errors ---")
print(re.findall(r'"error": "[a-z_]+"', text[p : p + 5500]))
print("--- solvency load path ---")
s = text.find("capital_report.get(")
# only in solvency plane
sp = text.find("# Solvency plane over capital")
se = text.find("def seed_bootstrap_capabilities(", sp)
block = text[sp:se]
for m in re.finditer(r"capital_report\.get\([^\)]+\)", block):
    print(m.group(0))
