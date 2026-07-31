from pathlib import Path
import re

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
start = text.find("def run_charter_plane")
end = text.find("def builtin_charter_plane")
chunk = text[start:end]
# print success return structure near end
idx = chunk.rfind('"action": "charter_plane"')
print(chunk[idx - 200 : idx + 1200])
