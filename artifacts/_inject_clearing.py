from pathlib import Path

root = Path(__file__).resolve().parents[1]
cc_path = root / "src" / "blackhole_agent" / "capability_compounder.py"
impl_path = root / "artifacts" / "clearing_plane_impl.py"
cc = cc_path.read_text(encoding="utf-8")
impl = impl_path.read_text(encoding="utf-8")

impl_lines = impl.splitlines()
while impl_lines and (impl_lines[0].startswith("#") or not impl_lines[0].strip()):
    impl_lines.pop(0)
impl_body = "\n".join(impl_lines) + "\n"

marker = "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
if marker not in cc:
    raise SystemExit("seed_bootstrap marker not found")
if "def run_clearing_plane(" not in cc:
    cc = cc.replace(marker, impl_body + "\n\n" + marker)
    print("inserted clearing plane body")
else:
    print("clearing plane already present")

old_deny = '        "capability.settlement-plane",\n        # Batch operators'
new_deny = (
    '        "capability.settlement-plane",\n'
    '        "capability.clearing-plane",\n'
    "        # Batch operators"
)
if old_deny in cc and '"capability.clearing-plane"' not in cc.split("PROGRAM_PLAN_DENYLIST")[1][:900]:
    cc = cc.replace(old_deny, new_deny, 1)
    print("deny list updated")

hints_old = (
    '    ("obligation", ("capability.settlement-plane", "capability.actuation-plane", '
    '"capability.quorum-plane")),\n'
)
hints_new = hints_old + (
    '    ("clearing", ("capability.clearing-plane", "capability.settlement-plane", '
    '"capability.actuation-plane")),\n'
    '    ("clear", ("capability.clearing-plane", "capability.settlement-plane", '
    '"capability.finality-plane")),\n'
    '    ("net position", ("capability.clearing-plane", "capability.settlement-plane", '
    '"capability.assurance-plane")),\n'
    '    ("clearing-root", ("capability.clearing-plane", "capability.settlement-plane", '
    '"capability.lineage-plane")),\n'
    '    ("netted", ("capability.clearing-plane", "capability.settlement-plane", '
    '"capability.quorum-plane")),\n'
)
if hints_old in cc and 'capability.clearing-plane' not in cc.split("MISSION_GOAL_HINTS")[1][:5000]:
    cc = cc.replace(hints_old, hints_new, 1)
    print("hints updated")

cc = cc.replace(
    "#   settlement_ok | settled_ok | min_settlements:N | settlement_root_valid\n# Free-text lines",
    "#   settlement_ok | settled_ok | min_settlements:N | settlement_root_valid\n"
    "#   clearing_ok | cleared_ok | min_clearings:N | clearing_root_valid\n# Free-text lines",
    1,
)

pat_old = (
    'r"settlement_ok|settled_ok|min_settlements|settlement_root_valid"\n'
    '    r")(?::(?P<arg>.+))?$",'
)
pat_new = (
    'r"settlement_ok|settled_ok|min_settlements|settlement_root_valid|"\n'
    '    r"clearing_ok|cleared_ok|min_clearings|clearing_root_valid"\n'
    '    r")(?::(?P<arg>.+))?$",'
)
if pat_old in cc and "clearing_ok|cleared_ok" not in cc:
    cc = cc.replace(pat_old, pat_new, 1)
    print("pattern updated")

ctx_old = '''        "settlement_ok",
        "settled_ok",
        "min_settlements",
        "settlement_root_valid",
    }
)'''
ctx_new = '''        "settlement_ok",
        "settled_ok",
        "min_settlements",
        "settlement_root_valid",
        "clearing_ok",
        "cleared_ok",
        "min_clearings",
        "clearing_root_valid",
    }
)'''
if ctx_old in cc and '"clearing_ok"' not in cc.split("CONTEXT_ONLY_OUTCOME_KINDS")[1][:2000]:
    cc = cc.replace(ctx_old, ctx_new, 1)
    print("context only updated")

soft_anchor = '''    if re.search(r"\\bsettlement_root_valid\\b", lower) or (
        "settlement" in lower
        and "root" in lower
        and ("valid" in lower or "verify" in lower or "ok" in lower)
    ):
        found.append({"kind": "settlement_root_valid", "arg": "", "source": chunk})
    return found
'''
soft_add = '''    if re.search(r"\\bsettlement_root_valid\\b", lower) or (
        "settlement" in lower
        and "root" in lower
        and ("valid" in lower or "verify" in lower or "ok" in lower)
    ):
        found.append({"kind": "settlement_root_valid", "arg": "", "source": chunk})
    # Avoid matching capability.clearing-plane ids (contains "clearing" + "plane").
    if re.search(r"\\bclearing_ok\\b", lower) or (
        re.search(r"\\bclearing\\s+plane\\b", lower)
        and ("ok" in lower or "pass" in lower or "succeed" in lower)
    ):
        found.append({"kind": "clearing_ok", "arg": "", "source": chunk})
    if re.search(r"\\bcleared_ok\\b", lower) or re.search(
        r"\\bcleared\\s*(?:=|is|:)\\s*true\\b", lower
    ):
        found.append({"kind": "cleared_ok", "arg": "", "source": chunk})
    elif (
        re.search(r"\\bcleared\\b", lower)
        and ("ok" in lower or "pass" in lower or "succeed" in lower)
        and "clearing-plane" not in lower
        and "clearing_plane" not in lower
    ):
        found.append({"kind": "cleared_ok", "arg": "", "source": chunk})
    m = re.search(r"(?:at least|>=|≥)\\s*(\\d+)\\s+clearing", lower)
    if m:
        found.append({"kind": "min_clearings", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bmin_clearings\\b", lower) and not any(
        item.get("kind") == "min_clearings" for item in found
    ):
        m_n = re.search(r"min_clearings\\s*[:=]?\\s*(\\d+)", lower)
        found.append(
            {
                "kind": "min_clearings",
                "arg": m_n.group(1) if m_n else "2",
                "source": chunk,
            }
        )
    if re.search(r"\\bclearing_root_valid\\b", lower) or (
        "clearing" in lower
        and "root" in lower
        and ("valid" in lower or "verify" in lower or "ok" in lower)
    ):
        found.append({"kind": "clearing_root_valid", "arg": "", "source": chunk})
    return found
'''
if soft_anchor in cc and '"kind": "clearing_ok"' not in cc:
    cc = cc.replace(soft_anchor, soft_add, 1)
    print("soft extract updated")
elif '"kind": "clearing_ok"' in cc:
    print("soft extract already present")
else:
    raise SystemExit("soft anchor missing")

eval_old = '''        return ok, f"settlement_root_valid={ok}"
    if kind == "program_passes":
'''
eval_new = '''        return ok, f"settlement_root_valid={ok}"
    if kind in {
        "clearing_ok",
        "cleared_ok",
        "min_clearings",
        "clearing_root_valid",
    }:
        plane = (
            context.get("clearing")
            or context.get("clearing_plane")
            or context.get("net")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_clearing_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "clearing_ok":
            ok = bool(plane.get("ok"))
            return ok, f"clearing_ok={ok}"
        if kind == "cleared_ok":
            if "cleared" in plane:
                ok = plane.get("cleared") is True and bool(plane.get("ok", True))
            elif "cleared_ok" in plane:
                ok = plane.get("cleared_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("clearing_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"cleared_ok={ok}"
        if kind == "min_clearings":
            need = int(float(arg or "0"))
            have = context.get("clearing_count")
            if have is None:
                have = context.get("tip_clearing_height")
            if have is None:
                have = (
                    plane.get("clearing_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"clearings={have_i} need>={need}"
        # clearing_root_valid
        if "clearing_root_valid" in plane:
            ok = plane.get("clearing_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("clearing_certificate")
                or plane.get("certificate")
                or context.get("clearing_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_clearing_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("clearing_root") or plane.get("tip_clearing_root")
                )
        return ok, f"clearing_root_valid={ok}"
    if kind == "program_passes":
'''
if eval_old in cc and "clearing_ok={ok}" not in cc:
    cc = cc.replace(eval_old, eval_new, 1)
    print("eval predicates updated")
elif "clearing_ok={ok}" in cc:
    print("eval already present")
else:
    raise SystemExit("eval marker missing")

seed_settlement_end = '''                "settlement",
                "receipt",
                "settlement-root",
                "actuation",
                "effects",
                "deterministic",
                "execution",
                "finality",
                "quorum",
                "consensus",
                "byzantine",
                "multi-origin",
                "lineage",
                "evidence",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
    ]
    for seed in seeds:
'''
seed_clearing = '''                "settlement",
                "receipt",
                "settlement-root",
                "actuation",
                "effects",
                "deterministic",
                "execution",
                "finality",
                "quorum",
                "consensus",
                "byzantine",
                "multi-origin",
                "lineage",
                "evidence",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        Capability(
            id="capability.clearing-plane",
            name="Clearing plane over settlement",
            description=(
                "Closed clearing plane: multi-settlement receipts → deterministic "
                "hash-chained clearing positions with net position digests bound to "
                "settlement roots → clearing certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-settlement/double-clearing/forged-root/"
                "gap/net-tamper/single-clearing falsification with genesis replay matching "
                "tip — past settled receipts without netted clearing outcomes."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_clearing_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_clearing_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='clearing over settlement'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "os.environ['BLACKHOLE_CLEARING_RUN_SETTLEMENT']='1'; "
                "os.environ['BLACKHOLE_SETTLEMENT_RUN_ACTUATION']='1'; "
                "os.environ['BLACKHOLE_ACTUATION_RUN_EXECUTION']='1'; "
                "os.environ['BLACKHOLE_EXECUTION_RUN_FINALITY']='1'; "
                "os.environ['BLACKHOLE_FINALITY_RUN_QUORUM']='1'; "
                "os.environ['BLACKHOLE_QUORUM_RUN_CONTINUITY']='0'; "
                "os.environ['BLACKHOLE_CONTINUITY_RUN_RECON']='0'; "
                "os.environ['BLACKHOLE_QUORUM_INJECT_BYZANTINE']='1'; "
                "os.environ['BLACKHOLE_FINALITY_EPOCH_COUNT']='2'; "
                "os.environ['BLACKHOLE_ACTUATION_MIN_ACTIONS']='2'; "
                "os.environ['BLACKHOLE_SETTLEMENT_MIN_SETTLEMENTS']='2'; "
                "os.environ['BLACKHOLE_CLEARING_MIN_CLEARINGS']='2'; "
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-clearing-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-clearing-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-clearing-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-clearing-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-clearing-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-clearing.json')); "
                "r=builtin_clearing_plane(); assert r['ok'] and r.get('action')=='clearing_plane' "
                "and r.get('cleared') is True and int(r.get('clearing_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('clearing_certificate',{}).get('valid') "
                "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\""
            ),
            dependencies=(
                "repo.import-health",
                "capability.ledger-inventory",
                "capability.outcome-contract",
                "capability.contract-plane",
                "capability.assurance-plane",
                "capability.sovereignty-plane",
                "capability.lineage-plane",
                "capability.reconciliation-plane",
                "capability.continuity-plane",
                "capability.federation-plane",
                "capability.quorum-plane",
                "capability.finality-plane",
                "capability.execution-plane",
                "capability.actuation-plane",
                "capability.settlement-plane",
                "capability.transfer-plane",
                "capability.ablation-proof",
                "capability.adversarial-contract",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
                "capabilities/ledger.json",
            ),
            capability_delta=(
                "Clearing plane nets multi-settlement receipts into deterministic "
                "hash-chained clearing positions with net position digests and "
                "clearing certificates bound to settlement roots, sterile rehydrate+"
                "prove, genesis replay matching tip, and adversarial falsification of "
                "wrong-settlement/reorder/double-clear/forged-root/net-tamper without "
                "skill-route."
            ),
            tags=(
                "bootstrap",
                "compounder",
                "clearing",
                "net",
                "clearing-root",
                "settlement",
                "receipt",
                "deterministic",
                "actuation",
                "execution",
                "finality",
                "quorum",
                "consensus",
                "byzantine",
                "multi-origin",
                "lineage",
                "evidence",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
    ]
    for seed in seeds:
'''
if seed_settlement_end in cc and "id=\"capability.clearing-plane\"" not in cc:
    # also check id= form
    if 'id="capability.clearing-plane"' not in cc and "id='capability.clearing-plane'" not in cc:
        if 'id="capability.clearing-plane"' not in cc.replace("'", '"'):
            if "capability.clearing-plane" not in cc[cc.find("def seed_bootstrap") :]:
                cc = cc.replace(seed_settlement_end, seed_clearing, 1)
                print("seed capability added")
            else:
                print("seed id present in seed_bootstrap section")
        else:
            print("seed present quote variant")
    else:
        print("seed already present")
elif "capability.clearing-plane" in cc[cc.find("def seed_bootstrap") : cc.find("def seed_bootstrap") + 80000]:
    print("seed already in bootstrap")
else:
    # try alternate: settlement seed may have slightly different formatting after injection
    print("seed settlement end missing; searching...")
    idx = cc.rfind('id="capability.settlement-plane"')
    if idx < 0:
        idx = cc.rfind("id='capability.settlement-plane'")
    if idx < 0:
        raise SystemExit("settlement seed not found")
    # find closing of that Capability and the seeds list
    close = cc.find("\n    ]\n    for seed in seeds:", idx)
    if close < 0:
        raise SystemExit("seeds list close not found after settlement")
    insert_at = close
    # build Capability block without the tags prefix
    block = seed_clearing.split("        Capability(")[1]
    block = "        Capability(" + block
    # remove trailing for seed line
    block = block.rsplit("    ]\n    for seed in seeds:", 1)[0]
    # insert before ]
    cc = cc[:insert_at] + ",\n" + block + cc[insert_at:]
    print("seed capability inserted via fallback")

cc_path.write_text(cc, encoding="utf-8")
print("wrote", cc_path, "chars", len(cc))
print("run_clearing_plane", "def run_clearing_plane(" in cc)
print("builtin", "def builtin_clearing_plane(" in cc)
print("clearing_ok kind", '"kind": "clearing_ok"' in cc)
print("seed", "capability.clearing-plane" in cc)
