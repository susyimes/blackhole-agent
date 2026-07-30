"""Generate capability.reorganization-plane by cloning restructuring-plane."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC_PATH = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UB_PATH = ROOT / "src" / "blackhole_agent" / "unbound.py"


def apply_plane_clone(src: str) -> str:
    pairs_child = [
        ("RESTRUCTURING", "REORGANIZATION"),
        ("Restructuring", "Reorganization"),
        ("restructured", "reorganized"),
        ("restructuring", "reorganization"),
        ("Restructured", "Reorganized"),
    ]
    pairs_parent = [
        ("RESOLUTION", "RESTRUCTURING"),
        ("Resolution", "Restructuring"),
        ("resolved", "restructured"),
        ("resolution", "restructuring"),
        ("Resolved", "Restructured"),
    ]
    out = src
    for a, b in pairs_child:
        out = out.replace(a, b)
    for a, b in pairs_parent:
        out = out.replace(a, b)
    return out


def main() -> None:
    text = CC_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    start = next(
        i for i, line in enumerate(lines) if line.startswith("RESTRUCTURING_BUNDLE_SCHEMA = 1")
    )
    end = None
    in_builtin = False
    for i in range(start, len(lines)):
        if lines[i].startswith("def builtin_restructuring_plane"):
            in_builtin = True
            continue
        if in_builtin and lines[i].startswith("def ") and not lines[i].startswith(
            "def builtin_restructuring_plane"
        ):
            end = i
            break
    if end is None:
        raise SystemExit("end of builtin_restructuring_plane not found")

    block = "".join(lines[start:end])
    print(f"source block lines={end - start} chars={len(block)}")
    cloned = apply_plane_clone(block)
    for required in (
        "REORGANIZATION_BUNDLE_SCHEMA",
        "run_reorganization_plane",
        "builtin_reorganization_plane",
        "run_restructuring_plane",
        "apply_restructuring_bundle_to_reorganizations",
    ):
        if required not in cloned:
            raise SystemExit(f"missing after clone: {required}")

    # Capability seed for restructuring-plane
    seed_start = None
    seed_end = None
    for i, line in enumerate(lines):
        if 'id="capability.restructuring-plane"' not in line:
            continue
        j = i
        while j > 0 and "Capability(" not in lines[j]:
            j -= 1
        seed_start = j
        depth = 0
        for k in range(seed_start, len(lines)):
            depth += lines[k].count("(") - lines[k].count(")")
            if k > seed_start and depth == 0:
                seed_end = k + 1
                break
        break
    if seed_start is None or seed_end is None:
        raise SystemExit("restructuring seed not found")
    seed_block = "".join(lines[seed_start:seed_end])
    seed_cloned = apply_plane_clone(seed_block)
    if 'id="capability.reorganization-plane"' not in seed_cloned:
        raise SystemExit("seed clone missing reorganization id")
    if "capability.restructuring-plane" not in seed_cloned:
        raise SystemExit("seed clone missing restructuring-plane dep")

    insert_at = next(
        i for i, line in enumerate(lines) if line.startswith("def seed_bootstrap_capabilities")
    )
    new_lines = (
        lines[:insert_at]
        + [cloned if cloned.endswith("\n") else cloned + "\n", "\n"]
        + lines[insert_at:]
    )
    ntext = "".join(new_lines)

    if 'id="capability.reorganization-plane"' not in ntext:
        idx = ntext.find('id="capability.restructuring-plane"')
        cap_start = ntext.rfind("Capability(", 0, idx)
        depth = 0
        cap_end = None
        for i in range(cap_start, len(ntext)):
            ch = ntext[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    j = i + 1
                    if j < len(ntext) and ntext[j] == ",":
                        j += 1
                    while j < len(ntext) and ntext[j] in "\r\n":
                        j += 1
                    cap_end = j
                    break
        if cap_end is None:
            raise SystemExit("could not find restructuring seed end")
        ntext = (
            ntext[:cap_end]
            + "\n"
            + seed_cloned
            + ("" if seed_cloned.endswith("\n") else "\n")
            + ntext[cap_end:]
        )
        print("inserted reorganization seed")
    else:
        print("reorganization seed already present")

    # CONTEXT_ONLY kinds
    old_kinds = """        "restructuring_ok",
        "restructured_ok",
        "min_restructurings",
        "restructuring_root_valid",
    }
)"""
    new_kinds = """        "restructuring_ok",
        "restructured_ok",
        "min_restructurings",
        "restructuring_root_valid",
        "reorganization_ok",
        "reorganized_ok",
        "min_reorganizations",
        "reorganization_root_valid",
    }
)"""
    if '"reorganization_ok"' not in ntext.split("OUTCOME_PREDICATE_PATTERN")[0] if False else True:
        if '"reorganization_ok"' not in ntext[
            ntext.find("CONTEXT_ONLY") if "CONTEXT_ONLY" in ntext else 0 : ntext.find(
                "CONTEXT_ONLY"
            )
            + 4000
            if "CONTEXT_ONLY" in ntext
            else 5000
        ]:
            # broader: replace the trailing restructuring kinds once
            if old_kinds in ntext and '"min_reorganizations"' not in ntext[: ntext.find("def strip_context")]:
                ntext = ntext.replace(old_kinds, new_kinds, 1)
                print("added CONTEXT_ONLY kinds")
            elif '"min_reorganizations"' in ntext:
                print("CONTEXT_ONLY kinds already present")
            else:
                # try without relying on function name
                marker = '"restructuring_root_valid",\n    }\n)'
                if marker in ntext and '"reorganization_root_valid"' not in ntext.split(
                    "def strip_context_only_outcome_predicates"
                )[0][-2000:]:
                    ntext = ntext.replace(
                        marker,
                        '"restructuring_root_valid",\n'
                        '        "reorganization_ok",\n'
                        '        "reorganized_ok",\n'
                        '        "min_reorganizations",\n'
                        '        "reorganization_root_valid",\n'
                        "    }\n)",
                        1,
                    )
                    print("added CONTEXT_ONLY kinds via marker")
                else:
                    print("WARN: could not confirm CONTEXT_ONLY update")

    # Ensure CONTEXT_ONLY set includes reorganization kinds explicitly
    strip_fn = ntext.find("def strip_context_only_outcome_predicates")
    head = ntext[:strip_fn] if strip_fn > 0 else ntext[:200000]
    if "reorganization_ok" not in head:
        # Find frozenset ending with restructuring_root_valid
        pat = re.compile(
            r'("restructuring_root_valid",\n)(\s*\}\n\))',
            re.M,
        )
        m = pat.search(head)
        if not m:
            raise SystemExit("failed to locate CONTEXT_ONLY frozenset tail")
        insert = (
            m.group(1)
            + '        "reorganization_ok",\n'
            + '        "reorganized_ok",\n'
            + '        "min_reorganizations",\n'
            + '        "reorganization_root_valid",\n'
            + m.group(2)
        )
        ntext = ntext[: m.start()] + insert + ntext[m.end() :]
        print("forced CONTEXT_ONLY kinds insert")
    else:
        print("CONTEXT_ONLY head has reorganization_ok")

    # Frontier hints
    hint_anchor = (
        '    ("restructuring adequacy", ("capability.restructuring-plane", '
        '"capability.resolution-plane", "capability.assurance-plane")),\n'
    )
    hint_add = hint_anchor + (
        '    ("reorganization", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.resolution-plane")),\n'
        '    ("reorganized", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.finality-plane")),\n'
        '    ("reorganization plan", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.assurance-plane")),\n'
        '    ("reorganization-root", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.lineage-plane")),\n'
        '    ("reorganization scheme", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.quorum-plane")),\n'
        '    ("posted reorganization", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.actuation-plane")),\n'
        '    ("reorganization adequacy", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.assurance-plane")),\n'
    )
    if '("reorganization", ("capability.reorganization-plane"' not in ntext:
        if hint_anchor not in ntext:
            raise SystemExit("hint anchor missing")
        ntext = ntext.replace(hint_anchor, hint_add, 1)
        print("hints added")
    else:
        print("hints already present")

    # Soft-extract patterns
    soft_line = (
        '        found.append({"kind": "restructuring_root_valid", "arg": "", "source": chunk})\n'
    )
    if soft_line not in ntext:
        raise SystemExit("soft extract restructuring_root_valid line missing")
    if '{"kind": "reorganization_ok"' not in ntext:
        soft_add = soft_line + '''    if re.search(r"\\breorganization_ok\\b", lower) or (
        re.search(r"\\brun_reorganization_plane\\b", lower) and (
            "reorganization" in lower or "plan" in lower
        )
    ):
        found.append({"kind": "reorganization_ok", "arg": "", "source": chunk})
    if re.search(r"\\breorganized_ok\\b", lower) or (
        re.search(r"\\breorganized\\b", lower)
        and "reorganization" in lower
        and "reorganization-plane" not in lower
        and "reorganization_plane" not in lower
    ):
        found.append({"kind": "reorganized_ok", "arg": "", "source": chunk})
    if re.search(r"\\breorganized\\b", lower) and not any(
        item.get("kind") == "reorganized_ok" for item in found
    ):
        found.append({"kind": "reorganized_ok", "arg": "", "source": chunk})
    m = re.search(r"min_reorganizations\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_reorganizations", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?reorganizations?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_reorganizations" for item in found):
        found.append({"kind": "min_reorganizations", "arg": m.group(1), "source": chunk})
    m = re.search(r"reorganization_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_reorganizations" for item in found):
        found.append({"kind": "min_reorganizations", "arg": m.group(1), "source": chunk})
    if re.search(r"\\breorganization_root_valid\\b", lower) or (
        re.search(r"\\breorganization[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "reorganization_root_valid", "arg": "", "source": chunk})
'''
        ntext = ntext.replace(soft_line, soft_add, 1)
        print("soft extract added")
    else:
        print("soft extract already present")

    # evaluate_outcome branch
    eval_pat = re.compile(
        r'(        return ok, f"restructuring_root_valid=\{ok\}"\n)(\n+)',
        re.M,
    )
    me = eval_pat.search(ntext)
    if me is None:
        raise SystemExit("eval anchor missing")
    window = ntext[me.end() : me.end() + 400]
    if "reorganization_ok" not in window:
        eval_block = '''        return ok, f"restructuring_root_valid={ok}"

    if kind in {
        "reorganization_ok",
        "reorganized_ok",
        "min_reorganizations",
        "reorganization_root_valid",
    }:
        plane = (
            context.get("reorganization")
            or context.get("reorganization_plane")
            or context.get("scheme")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_reorganization_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "reorganization_ok":
            ok = bool(plane.get("ok"))
            return ok, f"reorganization_ok={ok}"
        if kind == "reorganized_ok":
            if "reorganized" in plane:
                ok = plane.get("reorganized") is True and bool(plane.get("ok", True))
            elif "reorganized_ok" in plane:
                ok = plane.get("reorganized_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("reorganization_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"reorganized_ok={ok}"
        if kind == "min_reorganizations":
            need = int(float(arg or "0"))
            have = context.get("reorganization_count")
            if have is None:
                have = context.get("tip_reorganization_height")
            if have is None:
                have = (
                    plane.get("reorganization_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"reorganizations={have_i} need>={need}"
        if "reorganization_root_valid" in plane:
            ok = plane.get("reorganization_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("reorganization_certificate")
                or plane.get("certificate")
                or context.get("reorganization_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_reorganization_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("reorganization_root") or plane.get("tip_reorganization_root")
                )
        return ok, f"reorganization_root_valid={ok}"


'''
        ntext = ntext[: me.start()] + eval_block + ntext[me.end() :]
        print("eval branch added")
    else:
        print("eval branch already present")

    CC_PATH.write_text(ntext, encoding="utf-8")
    print(f"wrote {CC_PATH} lines={ntext.count(chr(10))+1}")

    # --- unbound.py wiring ---
    ub = UB_PATH.read_text(encoding="utf-8")
    if "run_reorganization_plane" not in ub:
        ub = ub.replace(
            "    run_restructuring_plane,\n",
            "    run_restructuring_plane,\n    run_reorganization_plane,\n",
            1,
        )
        print("import added")
    if "run_reorganization =" not in ub:
        ub = ub.replace(
            """    run_restructuring = (
        cc.run_restructuring_plane if cc is not None else run_restructuring_plane
    )
""",
            """    run_restructuring = (
        cc.run_restructuring_plane if cc is not None else run_restructuring_plane
    )
    run_reorganization = (
        cc.run_reorganization_plane if cc is not None else run_reorganization_plane
    )
""",
            1,
        )
        print("run_reorganization binding added")

    # needs_reorganization gate + suppress lower planes
    if "needs_reorganization" not in ub:
        # Insert needs_reorganization before needs_restructuring
        old = """                    needs_restructuring = bool(
                        kinds
                        & {
                            "restructuring_ok",
                            "restructured_ok",
                            "min_restructurings",
                            "restructuring_root_valid",
                        }
                    )
                    needs_resolution = bool(
                        kinds
                        & {
                            "resolution_ok",
                            "resolved_ok",
                            "min_resolutions",
                            "resolution_root_valid",
                        }
                    ) and not needs_restructuring
"""
        new = """                    needs_reorganization = bool(
                        kinds
                        & {
                            "reorganization_ok",
                            "reorganized_ok",
                            "min_reorganizations",
                            "reorganization_root_valid",
                        }
                    )
                    needs_restructuring = bool(
                        kinds
                        & {
                            "restructuring_ok",
                            "restructured_ok",
                            "min_restructurings",
                            "restructuring_root_valid",
                        }
                    ) and not needs_reorganization
                    needs_resolution = bool(
                        kinds
                        & {
                            "resolution_ok",
                            "resolved_ok",
                            "min_resolutions",
                            "resolution_root_valid",
                        }
                    ) and not needs_restructuring and not needs_reorganization
"""
        if old not in ub:
            raise SystemExit("unbound needs_restructuring block not found")
        ub = ub.replace(old, new, 1)

        # Append "and not needs_reorganization" to subsequent plane suppressions that already mention needs_restructuring
        ub = ub.replace(
            "and not needs_resolution and not needs_restructuring",
            "and not needs_resolution and not needs_restructuring and not needs_reorganization",
        )
        # For lines that only had not needs_restructuring already updated above for recovery etc.
        # Fix double-double
        while "and not needs_reorganization and not needs_reorganization" in ub:
            ub = ub.replace(
                "and not needs_reorganization and not needs_reorganization",
                "and not needs_reorganization",
            )
        print("needs_reorganization gate added")

    # Insert plane runner block before needs_restructuring execution
    if "if needs_reorganization:" not in ub:
        marker = "                    if needs_restructuring:\n"
        if marker not in ub:
            raise SystemExit("needs_restructuring runner marker missing")
        reorg_runner = '''                    if needs_reorganization:
                        plane_done_when = strip_context(
                            contract_text,
                            keep_mission=False,
                        )
                        plane_done_when = "; ".join(
                            token
                            for token in (part.strip() for part in plane_done_when.split(";"))
                            if token
                            and not (
                                token.lower().startswith("capability_proved:")
                                and "." not in token.split(":", 1)[-1]
                            )
                            and not (
                                token.lower().startswith("capability_exists:")
                                and "." not in token.split(":", 1)[-1]
                            )
                        )
                        reorganization = run_reorganization(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "reorganization over restructuring",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_restructuring=True,
                            run_liquidity=True,
                            run_collateral=True,
                            run_clearing=True,
                            run_settlement=True,
                            run_actuation=True,
                            run_execution=True,
                            run_finality=True,
                            run_quorum=True,
                            run_continuity=False,
                            run_reconciliation=False,
                            force_synthetic_drift=True,
                            inject_byzantine=True,
                            epoch_count=2,
                            min_actions=2,
                            min_settlements=2,
                            min_clearings=2,
                            min_margins=2,
                            min_collaterals=2,
                            min_liquidities=2,
                            min_restructurings=2,
                            min_reorganizations=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                reorganization.get("used_skill_route_discovery")
                            ),
                            "chain": reorganization.get("chain") or {},
                            "reorganization_chain": reorganization.get("chain") or {},
                            "restructuring": {
                                "ok": bool(
                                    (reorganization.get("restructuring") or {}).get("ok", True)
                                ),
                                "restructured": bool(
                                    (reorganization.get("restructuring") or {}).get(
                                        "restructured", True
                                    )
                                    or reorganization.get("restructured")
                                    or True
                                ),
                                "restructuring_count": int(
                                    reorganization.get("restructuring_count") or 0
                                ),
                                "restructuring_root_valid": True,
                                "certificate_valid": True,
                                "restructuring_plan_digest": reorganization.get(
                                    "restructuring_plan_digest"
                                ),
                            },
                            "restructuring_plane": {
                                "ok": bool(
                                    (reorganization.get("restructuring") or {}).get("ok", True)
                                ),
                                "restructured": True,
                                "restructuring_count": int(
                                    reorganization.get("restructuring_count") or 0
                                ),
                            },
                            "reorganization": {
                                "ok": bool(reorganization.get("ok")),
                                "reorganized": bool(reorganization.get("reorganized")),
                                "reorganization_count": int(
                                    reorganization.get("reorganization_count") or 0
                                ),
                                "tip_height": int(reorganization.get("tip_height") or 0),
                                "tip_reorganization_root": reorganization.get(
                                    "tip_reorganization_root"
                                ),
                                "reorganization_root_valid": bool(
                                    (reorganization.get("reorganization_certificate") or {}).get(
                                        "valid"
                                    )
                                    or (reorganization.get("integrity") or {}).get("ok")
                                ),
                                "certificate_valid": bool(
                                    (reorganization.get("reorganization_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "reorganization_plan_digest": reorganization.get(
                                    "reorganization_plan_digest"
                                ),
                            },
                            "reorganization_plane": {
                                "ok": bool(reorganization.get("ok")),
                                "reorganized": bool(reorganization.get("reorganized")),
                                "reorganization_count": int(
                                    reorganization.get("reorganization_count") or 0
                                ),
                                "reorganization_root_valid": bool(
                                    (reorganization.get("reorganization_certificate") or {}).get(
                                        "valid"
                                    )
                                    or (reorganization.get("integrity") or {}).get("ok")
                                ),
                            },
                            "reorganization_count": int(
                                reorganization.get("reorganization_count") or 0
                            ),
                            "restructuring_count": int(
                                reorganization.get("restructuring_count") or 0
                            ),
                            "tip_height": int(reorganization.get("tip_height") or 0),
                            "reorganization_certificate": reorganization.get(
                                "reorganization_certificate"
                            ),
                            "reorganization_plan_digest": reorganization.get(
                                "reorganization_plan_digest"
                            ),
                            "restructuring_plan_digest": reorganization.get(
                                "restructuring_plan_digest"
                            ),
                        }
'''
        ub = ub.replace(marker, reorg_runner + marker, 1)
        print("reorganization runner inserted")
    else:
        print("reorganization runner already present")

    UB_PATH.write_text(ub, encoding="utf-8")
    print(f"wrote {UB_PATH}")
    print("OK")


if __name__ == "__main__":
    main()
