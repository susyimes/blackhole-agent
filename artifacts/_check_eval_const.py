from pathlib import Path

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
# find constitution eval block
idx = text.find('"constitution_ok"')
print("first constitution_ok at", idx, "line", text[:idx].count("\n") + 1)
# find all occurrences
pos = 0
while True:
    i = text.find("constitution_ok", pos)
    if i < 0:
        break
    ln = text[:i].count("\n") + 1
    line = text[text.rfind("\n", 0, i) + 1 : text.find("\n", i)]
    print(f"L{ln}: {line.strip()[:140]}")
    pos = i + 1

# show evaluate_outcome_predicate function area around charter_root_valid return
idx = text.find('return ok, f"charter_root_valid={ok}"')
print("\ncharter_root_valid returns:")
while idx >= 0:
    ln = text[:idx].count("\n") + 1
    print(f"--- at L{ln} ---")
    print(text[idx : idx + 800])
    idx = text.find('return ok, f"charter_root_valid={ok}"', idx + 1)
