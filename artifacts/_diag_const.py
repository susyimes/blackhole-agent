from pathlib import Path

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
print("run_const", "def run_constitution_plane" in text)
print("seed", "capability.constitution-plane" in text)
print("soft", '("constitution", ("capability.constitution-plane"' in text)
print("eval", "constitution_ok" in text)
mpos = text.find('id="capability.charter-plane"')
print("mpos", mpos)
if mpos >= 0:
    snippet = text[mpos : mpos + 4000]
    print("--- snippet end ---")
    print(snippet[-1500:])
    for pat in ["\n        ),\n\n    ]", "\n        ),\n    ]", "\n        ),"]:
        j = text.find(pat, mpos)
        print("pat", repr(pat[:20]), "at", j)
