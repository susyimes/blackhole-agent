from pathlib import Path

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
start = text.find("def run_charter_plane")
end = text.find("def builtin_charter_plane")
chunk = text[start:end]
idx = chunk.rfind('"action": "charter_plane"')
print(chunk[idx : idx + 2500])
