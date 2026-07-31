from pathlib import Path

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
start = text.find("def run_constitution_plane")
end = text.find("def builtin_constitution_plane")
chunk = text[start:end]
# find evaluate_outcome or final_contract context building
for needle in [
    "evaluate_outcome_contract",
    "final_contract",
    "snapshot_outcome",
    '"constitution"',
    "constitution_count",
    "context =",
]:
    idx = 0
    count = 0
    while True:
        i = chunk.find(needle, idx)
        if i < 0:
            break
        count += 1
        if count <= 3:
            abs_pos = start + i
            ln = text[:abs_pos].count("\n") + 1
            line = chunk[chunk.rfind("\n", 0, i) + 1 : chunk.find("\n", i)]
            print(f"{needle} L{ln}: {line.strip()[:140]}")
        idx = i + 1
    print(f"  total {needle}: {count}")
