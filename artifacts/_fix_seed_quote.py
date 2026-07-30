from pathlib import Path
import py_compile

p = Path("src/blackhole_agent/capability_compounder.py")
text = p.read_text(encoding="utf-8")
lines = text.splitlines()
for i, line in enumerate(lines):
    if "used_skill_route_discovery" in line and "restructuring" in "\n".join(lines[max(0, i - 30) : i + 1]):
        print(i + 1, repr(line[:120]))

# Fix the bad line: ends with discovery')""  should end with discovery')\"
bad = (
    "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\"\""
)
good = (
    "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\\\""
)
# In the written file we need the characters: "....discovery')\""
# which in a Python source line inside parentheses is:
#     "and ... discovery')\""
# When we write via Path.write, we need the file to contain a backslash before the final quote.

# Find all occurrences of the double-double-quote ending near restructuring
count = text.count(
    "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\"\""
)
print("bad count", count)

# Only the restructuring seed should be broken; resolution seed has correct escaping.
# Replace only after restructuring-plane id.
idx = text.find('id="capability.restructuring-plane"')
if idx < 0:
    raise SystemExit("seed not found")
head, tail = text[:idx], text[idx:]
tail2 = tail.replace(
    "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\"\"",
    "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\\\"",
    1,
)
# Wait: in the replace new string, we need the file content to be:
# "....discovery')\""
# As a Python string for the replacement value:
replacement = (
    'and r.get(\'adversarial\',{}).get(\'ok\') and not r.get(\'used_skill_route_discovery\')\\"'
)
# Hmm let's be explicit with characters:
# desired line content in file (without leading spaces):
# "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\""
desired = (
    "\"and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\\\"\""
)
# Find the broken line in tail and replace whole line
new_lines = []
fixed = False
for line in (head + tail).splitlines(keepends=True):
    if (
        not fixed
        and "used_skill_route_discovery" in line
        and line.rstrip().endswith('")') is False
        and line.count('"') >= 2
        and "adversarial" in line
    ):
        # check if this is the broken one (ends with "")
        stripped = line.rstrip("\n")
        if stripped.endswith('""') and "used_skill_route_discovery" in stripped:
            indent = line[: len(line) - len(line.lstrip())]
            # Build correct source line
            line = (
                indent
                + "\"and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\\\"\"\n"
            )
            fixed = True
            print("fixed line")
    new_lines.append(line)

if not fixed:
    # try broader match
    full = "".join(new_lines)
    idx = full.find('id="capability.restructuring-plane"')
    chunk = full[idx : idx + 12000]
    for j, line in enumerate(chunk.splitlines()):
        if "used_skill_route_discovery" in line:
            print("CANDIDATE", repr(line))

text2 = "".join(new_lines)
# If still not fixed, surgical replace of the exact bad sequence inside restructuring seed
if 'id="capability.restructuring-plane"' in text2:
    idx = text2.find('id="capability.restructuring-plane"')
    end = text2.find("for seed in seeds:", idx)
    section = text2[idx:end]
    if "used_skill_route_discovery')\"\"" in section or 'used_skill_route_discovery\')""' in section:
        section2 = section.replace(
            "used_skill_route_discovery')\"\"",
            "used_skill_route_discovery')\\\"",
            1,
        )
        # The above might still be wrong. Let's decode what we want:
        # File bytes should contain: ...discovery')\"
        # followed by closing quote of the Python string.
        # So characters: d i s c o v e r y ' ) \ " "
        section2 = section
        bad_seq = "used_skill_route_discovery')\"\""
        if bad_seq in section2:
            # replace bad_seq with discovery')\"  where the middle is backslash-quote then end quote
            good_seq = "used_skill_route_discovery')\\\""
            # good_seq as Python: discovery') + \ + "  but we need an extra " to close the string
            # File should read: ...discovery')\""
            good_seq = "used_skill_route_discovery')\\\"" + '"'
            # In Python: '\\"' is \", + '"' is "  => \""
            section2 = section2.replace(bad_seq, "used_skill_route_discovery')\\\"\"", 1)
            text2 = text2[:idx] + section2 + text2[end:]
            print("section fixed via seq replace")
        else:
            print("bad_seq not found, section ends:")
            print(repr(section[-200:]))

p.write_text(text2, encoding="utf-8")
try:
    py_compile.compile(str(p), doraise=True)
    print("py_compile ok")
except py_compile.PyCompileError as e:
    print("STILL BAD", e)
    # show line
    lines = p.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if "used_skill_route_discovery" in line and i > 52000:
            print(i + 1, repr(line))
