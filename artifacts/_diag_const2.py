from pathlib import Path

text = Path("src/blackhole_agent/capability_compounder.py").read_text(encoding="utf-8")
mpos = text.find('id="capability.charter-plane"')
# find next Capability or end of list
next_cap = text.find('id="capability.', mpos + 10)
print("next_cap", next_cap)
print(repr(text[mpos + 3000 : mpos + 4500]))
# Also search for how mandate closes
mpos2 = text.find('id="capability.mandate-plane"')
print("mandate mpos", mpos2)
# show 200 chars before next capability after mandate
next_after_mandate = text.find('id="capability.', mpos2 + 10)
print("between mandate and next:")
print(repr(text[next_after_mandate - 80 : next_after_mandate + 40]))
print("between charter and following:")
# after charter capability's updated_at
ua = text.find("updated_at=utc_now_iso()", mpos)
print("updated_at at", ua)
print(repr(text[ua : ua + 120]))
