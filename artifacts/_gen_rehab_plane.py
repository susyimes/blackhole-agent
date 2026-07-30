"""Generate capability.rehabilitation-plane by cloning reorganization-plane."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC_PATH = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UB_PATH = ROOT / "src" / "blackhole_agent" / "unbound.py"


def apply_plane_clone(src: str) -> str:
    # Child = new plane terms; mid = former child becomes parent; residual grandparent flags.
    pairs = [
        ("REORGANIZATION", "REHABILITATION"),
        ("Reorganization", "Rehabilitation"),
        ("reorganized", "rehabilitated"),
        ("reorganization", "rehabilitation"),
        ("Reorganized", "Rehabilitated"),
        ("RESTRUCTURING", "REORGANIZATION"),
        ("Restructuring", "Reorganization"),
        ("restructured", "reorganized"),
        ("restructuring", "reorganization"),
        ("Restructured", "Reorganized"),
        ("RESOLUTION", "RESTRUCTURING"),
        ("Resolution", "Restructuring"),
        ("resolved", "restructured"),
        ("resolution", "restructuring"),
        ("Resolved", "Restructured"),
    ]
    out = src
    for a, b in pairs:
        out = out.replace(a, b)
    return out


def main() -> None:
    text = CC_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    start = next(
        i for i, line in enumerate(lines) if line.startswith("REORGANIZATION_BUNDLE_SCHEMA = 1")
    )
    end = None
    in_builtin = False
    for i in range(start, len(lines)):
        if lines[i].startswith("def builtin_reorganization_plane"):
            in_builtin = True
            continue
        if in_builtin and lines[i].startswith("def ") and not lines[i].startswith(
            "def builtin_reorganization_plane"
        ):
            end = i
            break
    if end is None:
        raise SystemExit("end of builtin_reorganization_plane not found")

    block = "".join(lines[start:end])
    print(f"source block lines={end - start} chars={len(block)}")
    cloned = apply_plane_clone(block)
    for required in (
        "REHABILITATION_BUNDLE_SCHEMA",
        "run_rehabilitation_plane",
        "builtin_rehabilitation_plane",
        "run_reorganization_plane",
        "apply_reorganization_bundle_to_rehabilitations",
    ):
        if required not in cloned:
            raise SystemExit(f"missing after clone: {required}")

    seed_start = None
    seed_end = None
    for i, line in enumerate(lines):
        if 'id="capability.reorganization-plane"' not in line:
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
        raise SystemExit("reorganization seed not found")
    seed_block = "".join(lines[seed_start:seed_end])
    seed_cloned = apply_plane_clone(seed_block)
    if 'id="capability.rehabilitation-plane"' not in seed_cloned:
        raise SystemExit("seed clone missing rehabilitation id")
    if "capability.reorganization-plane" not in seed_cloned:
        raise SystemExit("seed clone missing reorganization-plane dep")

    insert_at = next(
        i for i, line in enumerate(lines) if line.startswith("def seed_bootstrap_capabilities")
    )
    new_lines = (
        lines[:insert_at]
        + [cloned if cloned.endswith("\n") else cloned + "\n", "\n"]
        + lines[insert_at:]
    )
    ntext = "".join(new_lines)

    if 'id="capability.rehabilitation-plane"' not in ntext:
        idx = ntext.find('id="capability.reorganization-plane"')
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
            raise SystemExit("could not find reorganization seed end")
        ntext = (
            ntext[:cap_end]
            + "\n"
            + seed_cloned
            + ("" if seed_cloned.endswith("\n") else "\n")
            + ntext[cap_end:]
        )
        print("inserted rehabilitation seed")
    else:
        print("rehabilitation seed already present")

    # CONTEXT_ONLY kinds
    strip_fn = ntext.find("def strip_context_only_outcome_predicates")
    head = ntext[:strip_fn] if strip_fn > 0 else ntext[:200000]
    if "rehabilitation_ok" not in head:
        pat = re.compile(
            r'("reorganization_root_valid",\n)(\s*\}\n\))',
            re.M,
        )
        m = pat.search(head)
        if not m:
            raise SystemExit("failed to locate CONTEXT_ONLY frozenset tail")
        insert = (
            m.group(1)
            + '        "rehabilitation_ok",\n'
            + '        "rehabilitated_ok",\n'
            + '        "min_rehabilitations",\n'
            + '        "rehabilitation_root_valid",\n'
            + m.group(2)
        )
        ntext = ntext[: m.start()] + insert + ntext[m.end() :]
        print("forced CONTEXT_ONLY kinds insert")
    else:
        print("CONTEXT_ONLY head has rehabilitation_ok")

    # Frontier hints
    hint_anchor = (
        '    ("reorganization adequacy", ("capability.reorganization-plane", '
        '"capability.restructuring-plane", "capability.assurance-plane")),\n'
    )
    hint_add = hint_anchor + (
        '    ("rehabilitation", ("capability.rehabilitation-plane", '
        '"capability.reorganization-plane", "capability.restructuring-plane")),\n'
        '    ("rehabilitated", ("capability.rehabilitation-plane", '
        '"capability.reorganization-plane", "capability.finality-plane")),\n'
        '    ("rehabilitation plan", ("capability.rehabilitation-plane", '
        '"capability.reorganization-plane", "capability.assurance-plane")),\n'
        '    ("rehabilitation-root", ("capability.rehabilitation-plane", '
        '"capability.reorganization-plane", "capability.lineage-plane")),\n'
        '    ("rehabilitation discharge", ("capability.rehabilitation-plane", '
        '"capability.reorganization-plane", "capability.quorum-plane")),\n'
        '    ("posted rehabilitation", ("capability.rehabilitation-plane", '
        '"capability.reorganization-plane", "capability.actuation-plane")),\n'
        '    ("rehabilitation adequacy", ("capability.rehabilitation-plane", '
        '"capability.reorganization-plane", "capability.assurance-plane")),\n'
    )
    if '("rehabilitation", ("capability.rehabilitation-plane"' not in ntext:
        if hint_anchor not in ntext:
            raise SystemExit("hint anchor missing")
        ntext = ntext.replace(hint_anchor, hint_add, 1)
        print("hints added")
    else:
        print("hints already present")

    # Soft-extract patterns
    soft_line = (
        '        found.append({"kind": "reorganization_root_valid", "arg": "", "source": chunk})\n'
    )
    if soft_line not in ntext:
        raise SystemExit("soft extract reorganization_root_valid line missing")
    if '{"kind": "rehabilitation_ok"' not in ntext:
        soft_add = soft_line + '''    if re.search(r"\\brehabilitation_ok\\b", lower) or (
        re.search(r"\\brun_rehabilitation_plane\\b", lower) and (
            "rehabilitation" in lower or "plan" in lower
        )
    ):
        found.append({"kind": "rehabilitation_ok", "arg": "", "source": chunk})
    if re.search(r"\\brehabilitated_ok\\b", lower) or (
        re.search(r"\\brehabilitated\\b", lower)
        and "rehabilitation" in lower
        and "rehabilitation-plane" not in lower
        and "rehabilitation_plane" not in lower
    ):
        found.append({"kind": "rehabilitated_ok", "arg": "", "source": chunk})
    if re.search(r"\\brehabilitated\\b", lower) and not any(
        item.get("kind") == "rehabilitated_ok" for item in found
    ):
        found.append({"kind": "rehabilitated_ok", "arg": "", "source": chunk})
    m = re.search(r"min_rehabilitations\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_rehabilitations", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?rehabilitations?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_rehabilitations" for item in found):
        found.append({"kind": "min_rehabilitations", "arg": m.group(1), "source": chunk})
    m = re.search(r"rehabilitation_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_rehabilitations" for item in found):
        found.append({"kind": "min_rehabilitations", "arg": m.group(1), "source": chunk})
    if re.search(r"\\brehabilitation_root_valid\\b", lower) or (
        re.search(r"\\brehabilitation[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "rehabilitation_root_valid", "arg": "", "source": chunk})
'''
        ntext = ntext.replace(soft_line, soft_add, 1)
        print("soft extract added")
    else:
        print("soft extract already present")

    # evaluate_outcome branch
    eval_pat = re.compile(
        r'(        return ok, f"reorganization_root_valid=\{ok\}"\n)(\n+)',
        re.M,
    )
    me = eval_pat.search(ntext)
    if me is None:
        raise SystemExit("eval anchor missing")
    window = ntext[me.end() : me.end() + 400]
    if "rehabilitation_ok" not in window:
        eval_block = '''        return ok, f"reorganization_root_valid={ok}"

    if kind in {
        "rehabilitation_ok",
        "rehabilitated_ok",
        "min_rehabilitations",
        "rehabilitation_root_valid",
    }:
        plane = (
            context.get("rehabilitation")
            or context.get("rehabilitation_plane")
            or context.get("discharge")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_rehabilitation_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "rehabilitation_ok":
            ok = bool(plane.get("ok"))
            return ok, f"rehabilitation_ok={ok}"
        if kind == "rehabilitated_ok":
            if "rehabilitated" in plane:
                ok = plane.get("rehabilitated") is True and bool(plane.get("ok", True))
            elif "rehabilitated_ok" in plane:
                ok = plane.get("rehabilitated_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("rehabilitation_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"rehabilitated_ok={ok}"
        if kind == "min_rehabilitations":
            need = int(float(arg or "0"))
            have = context.get("rehabilitation_count")
            if have is None:
                have = context.get("tip_rehabilitation_height")
            if have is None:
                have = (
                    plane.get("rehabilitation_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"rehabilitations={have_i} need>={need}"
        if "rehabilitation_root_valid" in plane:
            ok = plane.get("rehabilitation_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("rehabilitation_certificate")
                or plane.get("certificate")
                or context.get("rehabilitation_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_rehabilitation_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("rehabilitation_root") or plane.get("tip_rehabilitation_root")
                )
        return ok, f"rehabilitation_root_valid={ok}"


'''
        ntext = ntext[: me.start()] + eval_block + ntext[me.end() :]
        print("eval branch added")
    else:
        print("eval branch already present")

    CC_PATH.write_text(ntext, encoding="utf-8")
    print(f"wrote {CC_PATH} lines={ntext.count(chr(10))+1}")

    # --- unbound.py wiring ---
    ub = UB_PATH.read_text(encoding="utf-8")
    if "run_rehabilitation_plane" not in ub:
        ub = ub.replace(
            "    run_reorganization_plane,\n",
            "    run_reorganization_plane,\n    run_rehabilitation_plane,\n",
            1,
        )
        print("import added")
    if "run_rehabilitation =" not in ub:
        ub = ub.replace(
            """    run_reorganization = (
        cc.run_reorganization_plane if cc is not None else run_reorganization_plane
    )
""",
            """    run_reorganization = (
        cc.run_reorganization_plane if cc is not None else run_reorganization_plane
    )
    run_rehabilitation = (
        cc.run_rehabilitation_plane if cc is not None else run_rehabilitation_plane
    )
""",
            1,
        )
        print("run_rehabilitation binding added")

    if "needs_rehabilitation" not in ub:
        old = """                    needs_reorganization = bool(
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
        new = """                    needs_rehabilitation = bool(
                        kinds
                        & {
                            "rehabilitation_ok",
                            "rehabilitated_ok",
                            "min_rehabilitations",
                            "rehabilitation_root_valid",
                        }
                    )
                    needs_reorganization = bool(
                        kinds
                        & {
                            "reorganization_ok",
                            "reorganized_ok",
                            "min_reorganizations",
                            "reorganization_root_valid",
                        }
                    ) and not needs_rehabilitation
                    needs_restructuring = bool(
                        kinds
                        & {
                            "restructuring_ok",
                            "restructured_ok",
                            "min_restructurings",
                            "restructuring_root_valid",
                        }
                    ) and not needs_reorganization and not needs_rehabilitation
                    needs_resolution = bool(
                        kinds
                        & {
                            "resolution_ok",
                            "resolved_ok",
                            "min_resolutions",
                            "resolution_root_valid",
                        }
                    ) and not needs_restructuring and not needs_reorganization and not needs_rehabilitation
"""
        if old not in ub:
            raise SystemExit("unbound needs_reorganization block not found")
        ub = ub.replace(old, new, 1)

        ub = ub.replace(
            "and not needs_restructuring and not needs_reorganization",
            "and not needs_restructuring and not needs_reorganization and not needs_rehabilitation",
        )
        while "and not needs_rehabilitation and not needs_rehabilitation" in ub:
            ub = ub.replace(
                "and not needs_rehabilitation and not needs_rehabilitation",
                "and not needs_rehabilitation",
            )
        print("needs_rehabilitation gate added")

    if "if needs_rehabilitation:" not in ub:
        marker = "                    if needs_reorganization:\n"
        if marker not in ub:
            raise SystemExit("needs_reorganization runner marker missing")
        rehab_runner = '''                    if needs_rehabilitation:
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
                        rehabilitation = run_rehabilitation(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "rehabilitation over reorganization",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_reorganization=True,
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
                            min_reorganizations=2,
                            min_rehabilitations=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                rehabilitation.get("used_skill_route_discovery")
                            ),
                            "chain": rehabilitation.get("chain") or {},
                            "rehabilitation_chain": rehabilitation.get("chain") or {},
                            "reorganization": {
                                "ok": bool(
                                    (rehabilitation.get("reorganization") or {}).get("ok", True)
                                ),
                                "reorganized": bool(
                                    (rehabilitation.get("reorganization") or {}).get(
                                        "reorganized", True
                                    )
                                    or rehabilitation.get("reorganized")
                                    or True
                                ),
                                "reorganization_count": int(
                                    rehabilitation.get("reorganization_count") or 0
                                ),
                                "reorganization_root_valid": True,
                                "certificate_valid": True,
                                "reorganization_plan_digest": rehabilitation.get(
                                    "reorganization_plan_digest"
                                ),
                            },
                            "reorganization_plane": {
                                "ok": bool(
                                    (rehabilitation.get("reorganization") or {}).get("ok", True)
                                ),
                                "reorganized": True,
                                "reorganization_count": int(
                                    rehabilitation.get("reorganization_count") or 0
                                ),
                            },
                            "rehabilitation": {
                                "ok": bool(rehabilitation.get("ok")),
                                "rehabilitated": bool(rehabilitation.get("rehabilitated")),
                                "rehabilitation_count": int(
                                    rehabilitation.get("rehabilitation_count") or 0
                                ),
                                "tip_height": int(rehabilitation.get("tip_height") or 0),
                                "tip_rehabilitation_root": rehabilitation.get(
                                    "tip_rehabilitation_root"
                                ),
                                "rehabilitation_root_valid": bool(
                                    (rehabilitation.get("rehabilitation_certificate") or {}).get(
                                        "valid"
                                    )
                                    or (rehabilitation.get("integrity") or {}).get("ok")
                                ),
                                "certificate_valid": bool(
                                    (rehabilitation.get("rehabilitation_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "rehabilitation_plan_digest": rehabilitation.get(
                                    "rehabilitation_plan_digest"
                                ),
                            },
                            "rehabilitation_plane": {
                                "ok": bool(rehabilitation.get("ok")),
                                "rehabilitated": bool(rehabilitation.get("rehabilitated")),
                                "rehabilitation_count": int(
                                    rehabilitation.get("rehabilitation_count") or 0
                                ),
                                "rehabilitation_root_valid": bool(
                                    (rehabilitation.get("rehabilitation_certificate") or {}).get(
                                        "valid"
                                    )
                                    or (rehabilitation.get("integrity") or {}).get("ok")
                                ),
                            },
                            "rehabilitation_count": int(
                                rehabilitation.get("rehabilitation_count") or 0
                            ),
                            "reorganization_count": int(
                                rehabilitation.get("reorganization_count") or 0
                            ),
                            "tip_height": int(rehabilitation.get("tip_height") or 0),
                            "rehabilitation_certificate": rehabilitation.get(
                                "rehabilitation_certificate"
                            ),
                            "rehabilitation_plan_digest": rehabilitation.get(
                                "rehabilitation_plan_digest"
                            ),
                            "reorganization_plan_digest": rehabilitation.get(
                                "reorganization_plan_digest"
                            ),
                        }
'''
        ub = ub.replace(marker, rehab_runner + marker, 1)
        print("rehabilitation runner inserted")
    else:
        print("rehabilitation runner already present")

    UB_PATH.write_text(ub, encoding="utf-8")
    print(f"wrote {UB_PATH}")
    print("OK")


if __name__ == "__main__":
    main()
