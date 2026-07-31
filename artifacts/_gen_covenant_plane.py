"""Generate covenant plane over constitution by systematic rename of constitution plane."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC_PATH = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UB_PATH = ROOT / "src" / "blackhole_agent" / "unbound.py"


def to_covenant(text: str) -> str:
    """Map constitution-over-charter identifiers to covenant-over-constitution."""
    pairs = [
        ("constituted", "covenanted"),
        ("Constituted", "Covenanted"),
        ("CONSTITUTION", "COVENANT"),
        ("constitution", "covenant"),
        ("Constitution", "Covenant"),
        ("chartered", "constituted"),
        ("Chartered", "Constituted"),
        ("CHARTER", "CONSTITUTION"),
        ("charter", "constitution"),
        ("Charter", "Constitution"),
    ]
    out = text
    for a, b in pairs:
        out = out.replace(a, b)
    return out


def main() -> None:
    cc = CC_PATH.read_text(encoding="utf-8")
    ub = UB_PATH.read_text(encoding="utf-8")

    # --- Implementation block (schemas through builtin_constitution_plane) ---
    start = cc.find("CONSTITUTION_BUNDLE_SCHEMA = 1")
    end = cc.find(
        "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
    )
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"constitution impl bounds not found: {start=} {end=}")
    line_start = cc.rfind("\n", 0, start) + 1
    for _ in range(6):
        prev = cc.rfind("\n", 0, line_start - 1) + 1
        snippet = cc[prev:line_start]
        if (
            "CONSTITUTION_" in snippet
            or "DEFAULT_CONSTITUTION" in snippet
            or not snippet.strip()
        ):
            line_start = prev
        else:
            break
    const_impl = cc[line_start:end]
    print("const_impl lines", const_impl.count("\n") + 1)

    cap_start = cc.find(
        'Capability(\n            id="capability.constitution-plane"'
    )
    if cap_start < 0:
        raise SystemExit("constitution Capability seed not found")
    cap_end = cc.find("\n        ),\n\n", cap_start)
    if cap_end < 0:
        raise SystemExit("constitution Capability end not found")
    cap_end = cap_end + len("\n        ),")
    const_cap = cc[cap_start:cap_end]
    print("const_cap lines", const_cap.count("\n") + 1)

    cov_impl = to_covenant(const_impl)
    cov_cap = to_covenant(const_cap)

    # Ensure parent constitution-plane is an explicit dependency.
    if '"capability.constitution-plane"' not in cov_cap:
        cov_cap = cov_cap.replace(
            '"capability.mandate-plane"',
            '"capability.constitution-plane",\n                "capability.mandate-plane"',
            1,
        )

    if "def run_covenant_plane(" not in cc:
        # end still points into original string; recompute after nothing yet
        end = cc.find(
            "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
        )
        cc = cc[:end] + cov_impl + "\n\n" + cc[end:]
        print("inserted cov_impl")
    else:
        print("cov_impl already present")

    if 'id="capability.covenant-plane"' not in cc:
        marker = 'id="capability.constitution-plane"'
        i = cc.find(marker)
        j = cc.find("\n        ),\n\n", i)
        insert_at = j + len("\n        ),")
        cc = cc[:insert_at] + "\n\n" + cov_cap + cc[insert_at:]
        print("inserted cov_cap")
    else:
        print("cov_cap already present")

    frontier_snip = (
        '    ("constitution adequacy", ("capability.constitution-plane", '
        '"capability.charter-plane", "capability.assurance-plane")),\n'
    )
    frontier_add = frontier_snip + (
        '    ("covenant", ("capability.covenant-plane", '
        '"capability.constitution-plane", "capability.charter-plane")),\n'
        '    ("covenanted", ("capability.covenant-plane", '
        '"capability.constitution-plane", "capability.finality-plane")),\n'
        '    ("covenant plan", ("capability.covenant-plane", '
        '"capability.constitution-plane", "capability.assurance-plane")),\n'
        '    ("covenant-root", ("capability.covenant-plane", '
        '"capability.constitution-plane", "capability.lineage-plane")),\n'
        '    ("covenant discharge", ("capability.covenant-plane", '
        '"capability.constitution-plane", "capability.quorum-plane")),\n'
        '    ("posted covenant", ("capability.covenant-plane", '
        '"capability.constitution-plane", "capability.actuation-plane")),\n'
        '    ("covenant adequacy", ("capability.covenant-plane", '
        '"capability.constitution-plane", "capability.assurance-plane")),\n'
    )
    if '("covenant", ("capability.covenant-plane"' not in cc:
        if frontier_snip in cc:
            cc = cc.replace(frontier_snip, frontier_add, 1)
            print("added frontier keywords")
        else:
            print("WARN frontier snip not found")
    else:
        print("frontier already present")

    parse_marker = (
        '    if re.search(r"\\bconstitution_root_valid\\b", lower) or (\n'
        '        re.search(r"\\bconstitution[_\\s-]*root\\b", lower)\n'
        '        and "valid" in lower\n'
        "    ):\n"
        '        found.append({"kind": "constitution_root_valid", "arg": "", "source": chunk})\n'
        "\n"
    )
    parse_add = parse_marker + (
        '    if re.search(r"\\bcovenant_ok\\b", lower) or (\n'
        '        re.search(r"\\brun_covenant_plane\\b", lower) and (\n'
        '            "covenant" in lower or "plan" in lower\n'
        "        )\n"
        "    ):\n"
        '        found.append({"kind": "covenant_ok", "arg": "", "source": chunk})\n'
        '    if re.search(r"\\bcovenanted_ok\\b", lower) or (\n'
        '        "covenanted" in lower\n'
        '        and "covenant" in lower\n'
        '        and "covenant-plane" not in lower\n'
        '        and "covenant_plane" not in lower\n'
        "    ):\n"
        '        found.append({"kind": "covenanted_ok", "arg": "", "source": chunk})\n'
        '    m = re.search(r"min_covenants\\s*[:=]\\s*(\\d+)", lower)\n'
        "    if m:\n"
        '        found.append({"kind": "min_covenants", "arg": m.group(1), "source": chunk})\n'
        '    m = re.search(r"min[_\\s-]?covenants?\\s*[:=]\\s*(\\d+)", lower)\n'
        "    if m and not any(item.get(\"kind\") == \"min_covenants\" for item in found):\n"
        '        found.append({"kind": "min_covenants", "arg": m.group(1), "source": chunk})\n'
        '    m = re.search(r"covenant_count\\s*>=\\s*(\\d+)", lower)\n'
        "    if m and not any(item.get(\"kind\") == \"min_covenants\" for item in found):\n"
        '        found.append({"kind": "min_covenants", "arg": m.group(1), "source": chunk})\n'
        '    if re.search(r"\\bcovenant_root_valid\\b", lower) or (\n'
        '        re.search(r"\\bcovenant[_\\s-]*root\\b", lower)\n'
        '        and "valid" in lower\n'
        "    ):\n"
        '        found.append({"kind": "covenant_root_valid", "arg": "", "source": chunk})\n'
        "\n"
    )
    if 'found.append({"kind": "covenant_ok"' not in cc:
        if parse_marker in cc:
            cc = cc.replace(parse_marker, parse_add, 1)
            print("added parse predicates")
        else:
            print("WARN parse marker not found")
            idx = cc.find("constitution_root_valid")
            print(repr(cc[idx : idx + 350]))
    else:
        print("parse predicates already present")

    eval_marker = (
        '        return ok, f"constitution_root_valid={ok}"\n'
        "\n\n"
        '    if kind == "program_passes":\n'
    )
    eval_add = (
        '        return ok, f"constitution_root_valid={ok}"\n'
        "\n"
        "    if kind in {\n"
        '        "covenant_ok",\n'
        '        "covenanted_ok",\n'
        '        "min_covenants",\n'
        '        "covenant_root_valid",\n'
        "    }:\n"
        "        plane = (\n"
        '            context.get("covenant")\n'
        '            or context.get("covenant_plane")\n'
        "            or {}\n"
        "        )\n"
        "        if not plane or not plane.get(\"ok\"):\n"
        "            disk = _load_covenant_disk_evidence(context)\n"
        "            if disk:\n"
        "                plane = disk\n"
        '        if kind == "covenant_ok":\n'
        '            ok = bool(plane.get("ok") or plane.get("covenanted"))\n'
        '            return ok, f"covenant_ok={ok}"\n'
        '        if kind == "covenanted_ok":\n'
        "            ok = bool(\n"
        '                plane.get("covenanted")\n'
        '                or plane.get("ok")\n'
        "                or int(\n"
        '                    plane.get("covenant_count") or plane.get("tip_height") or 0\n'
        "                )\n"
        "                >= 2\n"
        "            )\n"
        '            return ok, f"covenanted_ok={ok}"\n'
        '        if kind == "min_covenants":\n'
        "            need = int(arg or 0)\n"
        '            have = context.get("covenant_count")\n'
        "            if have is None:\n"
        "                have = (\n"
        '                    plane.get("covenant_count")\n'
        '                    or plane.get("tip_height")\n'
        "                    or 0\n"
        "                )\n"
        "            try:\n"
        "                have_i = int(have or 0)\n"
        "            except (TypeError, ValueError):\n"
        "                have_i = 0\n"
        '                have = context.get("tip_covenant_height")\n'
        '            return have_i >= need, f"covenants={have_i} need>={need}"\n'
        '        if "covenant_root_valid" in plane:\n'
        '            ok = plane.get("covenant_root_valid") is True\n'
        "        else:\n"
        "            cert = (\n"
        '                plane.get("covenant_certificate")\n'
        '                or context.get("covenant_certificate")\n'
        "                or {}\n"
        "            )\n"
        "            if cert:\n"
        "                verify = verify_covenant_certificate(cert)\n"
        '                ok = bool(verify.get("valid") or verify.get("ok"))\n'
        "            else:\n"
        "                ok = bool(\n"
        '                    plane.get("covenant_root") or plane.get("tip_covenant_root")\n'
        "                )\n"
        '        return ok, f"covenant_root_valid={ok}"\n'
        "\n\n"
        '    if kind == "program_passes":\n'
    )
    if 'kind == "covenant_ok"' not in cc and '"covenant_ok",' not in cc[
        cc.find("constitution_root_valid={ok}") : cc.find("constitution_root_valid={ok}")
        + 800
    ] if "constitution_root_valid={ok}" in cc else True:
        if eval_marker in cc:
            cc = cc.replace(eval_marker, eval_add, 1)
            print("added eval predicates")
        else:
            print("WARN eval marker not found")
            idx = cc.find("constitution_root_valid={ok}")
            print(repr(cc[idx : idx + 120]))
    else:
        if eval_marker in cc and "_load_covenant_disk_evidence" not in cc:
            cc = cc.replace(eval_marker, eval_add, 1)
            print("added eval predicates (retry)")
        elif "_load_covenant_disk_evidence" in cc:
            print("eval predicates already present")
        else:
            print("WARN eval state ambiguous")

    CC_PATH.write_text(cc, encoding="utf-8")
    print("wrote compounder")

    # --- unbound.py wiring ---
    if "run_covenant_plane" not in ub:
        ub = ub.replace(
            "    run_constitution_plane,\n",
            "    run_constitution_plane,\n    run_covenant_plane,\n",
            1,
        )
        print("ub import added")
    if "run_covenant = (" not in ub:
        ub = ub.replace(
            "    run_constitution = (\n"
            "        cc.run_constitution_plane if cc is not None else run_constitution_plane\n"
            "    )\n",
            "    run_constitution = (\n"
            "        cc.run_constitution_plane if cc is not None else run_constitution_plane\n"
            "    )\n"
            "    run_covenant = (\n"
            "        cc.run_covenant_plane if cc is not None else run_covenant_plane\n"
            "    )\n",
            1,
        )
        print("ub run_covenant alias added")

    needs_const = (
        "                    needs_constitution = bool(\n"
        "                        kinds\n"
        "                        & {\n"
        '                            "constitution_ok",\n'
        '                            "constituted_ok",\n'
        '                            "min_constitutions",\n'
        '                            "constitution_root_valid",\n'
        "                        }\n"
        "                    )\n"
    )
    needs_cov = (
        "                    needs_covenant = bool(\n"
        "                        kinds\n"
        "                        & {\n"
        '                            "covenant_ok",\n'
        '                            "covenanted_ok",\n'
        '                            "min_covenants",\n'
        '                            "covenant_root_valid",\n'
        "                        }\n"
        "                    )\n"
        "                    needs_constitution = bool(\n"
        "                        kinds\n"
        "                        & {\n"
        '                            "constitution_ok",\n'
        '                            "constituted_ok",\n'
        '                            "min_constitutions",\n'
        '                            "constitution_root_valid",\n'
        "                        }\n"
        "                    ) and not needs_covenant\n"
    )
    if "needs_covenant = bool(" not in ub:
        if needs_const in ub:
            ub = ub.replace(needs_const, needs_cov, 1)
            print("ub needs_covenant added")
        else:
            print("WARN needs_constitution block not found")

    # Exclude covenant from lower planes
    for old, new in [
        (
            ") and not needs_constitution\n                    needs_mandate",
            ") and not needs_constitution and not needs_covenant\n                    needs_mandate",
        ),
        (
            "and not needs_charter and not needs_constitution\n                    needs_privilege",
            "and not needs_charter and not needs_constitution and not needs_covenant\n                    needs_privilege",
        ),
    ]:
        if old in ub and "not needs_covenant\n                    needs_mandate" not in ub:
            ub = ub.replace(old, new, 1)

    # Charter exclusion already has not needs_constitution — add not needs_covenant
    ub = ub.replace(
        ') and not needs_constitution\n                    needs_mandate = bool(',
        ') and not needs_constitution and not needs_covenant\n                    needs_mandate = bool(',
        1,
    )
    # Fix charter line if still missing covenant exclusion
    if (
        'needs_charter = bool(' in ub
        and 'and not needs_constitution\n' in ub
        and 'and not needs_covenant' not in ub.split('needs_charter = bool(')[1][:400]
    ):
        ub = ub.replace(
            """                    needs_charter = bool(
                        kinds
                        & {
                            "charter_ok",
                            "chartered_ok",
                            "min_charters",
                            "charter_root_valid",
                        }
                    ) and not needs_constitution
""",
            """                    needs_charter = bool(
                        kinds
                        & {
                            "charter_ok",
                            "chartered_ok",
                            "min_charters",
                            "charter_root_valid",
                        }
                    ) and not needs_constitution and not needs_covenant
""",
            1,
        )

    # higher_plane_active
    if "needs_covenant\n" not in ub and "needs_covenant\r\n" not in ub:
        ub = ub.replace(
            "                    higher_plane_active = bool(\n"
            "                        needs_constitution\n",
            "                    higher_plane_active = bool(\n"
            "                        needs_covenant\n"
            "                        or needs_constitution\n",
            1,
        )
        print("ub higher_plane_active updated")
    elif "needs_covenant" in ub and "higher_plane_active" in ub:
        if "needs_covenant\n                        or needs_constitution" not in ub:
            ub = ub.replace(
                "                    higher_plane_active = bool(\n"
                "                        needs_constitution\n",
                "                    higher_plane_active = bool(\n"
                "                        needs_covenant\n"
                "                        or needs_constitution\n",
                1,
            )
            print("ub higher_plane_active updated (2)")
        else:
            print("higher_plane already has covenant")

    # Handler block: derive from constitution handler via rename
    if "if needs_covenant:" not in ub:
        const_handler_start = ub.find("                    if needs_constitution:")
        if const_handler_start < 0:
            print("WARN constitution handler not found")
        else:
            # next sibling if needs_charter
            next_if = ub.find("\n                    if needs_charter:", const_handler_start)
            if next_if < 0:
                print("WARN needs_charter after constitution not found")
            else:
                const_handler = ub[const_handler_start:next_if]
                cov_handler = to_covenant(const_handler)
                # run_covenanted? to_covenant maps run_constitution -> run_covenant
                # but alias is run_covenant; constitution_result -> covenant_result
                # needs_constitution -> needs_covenant already via rename
                # Fix: run_covenant call param run_constitution=True is correct (parent)
                ub = (
                    ub[:const_handler_start]
                    + cov_handler
                    + "\n"
                    + ub[const_handler_start:]
                )
                print("ub covenant handler inserted")
    else:
        print("ub covenant handler already present")

    # Fix lower-plane exclusion chains that reference needs_constitution without covenant
    # Broad safe replacements for the exclusion suffix pattern
    patterns = [
        (
            "and not needs_charter and not needs_constitution\n",
            "and not needs_charter and not needs_constitution and not needs_covenant\n",
        ),
        (
            "and not needs_mandate and not needs_charter and not needs_constitution\n",
            "and not needs_mandate and not needs_charter and not needs_constitution and not needs_covenant\n",
        ),
    ]
    for old, new in patterns:
        if old in ub and new not in ub:
            ub = ub.replace(old, new)

    # Also fix or needs_charter higher list already done

    # needs_recognition line and similar long chains — append and not needs_covenant
    # where they already exclude needs_constitution but not covenant
    import re

    def add_covenant_excl(m: re.Match[str]) -> str:
        s = m.group(0)
        if "not needs_covenant" in s:
            return s
        if "not needs_constitution" in s:
            return s.replace(
                "not needs_constitution",
                "not needs_constitution and not needs_covenant",
            )
        return s

    ub2 = re.sub(
        r"\) and not needs_[a-z_]+(?: and not needs_[a-z_]+)+",
        add_covenant_excl,
        ub,
    )
    if ub2 != ub:
        ub = ub2
        print("ub exclusion chains updated via regex")

    UB_PATH.write_text(ub, encoding="utf-8")
    print("wrote unbound")

    # Syntax check
    for path in (CC_PATH, UB_PATH):
        src = path.read_text(encoding="utf-8")
        try:
            compile(src, path.name, "exec")
            print("OK compile", path.name)
        except SyntaxError as e:
            print("FAIL compile", path.name, e)

    print("has run_covenant_plane", "def run_covenant_plane" in CC_PATH.read_text(encoding="utf-8"))
    print("has capability.covenant-plane", 'capability.covenant-plane' in CC_PATH.read_text(encoding="utf-8"))
    print("ub needs_covenant", "needs_covenant" in UB_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
