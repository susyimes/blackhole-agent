"""Generate revalidation plane by transforming reattestation plane."""
from __future__ import annotations

from pathlib import Path


def transform_reattestation_to_revalidation(src: str) -> str:
    # Stage 1: protect new-plane tokens (longest first)
    reps = [
        ("REATTESTED", "@@REVALIDATED_U@@"),
        ("REATTESTATION", "@@REVALIDATION_U@@"),
        ("Reattested", "@@Revalidated@@"),
        ("Reattestation", "@@Revalidation@@"),
        ("reattested", "@@revalidated@@"),
        ("reattestation", "@@revalidation@@"),
    ]
    out = src
    for a, b in reps:
        out = out.replace(a, b)
    # Stage 2: promote bound layer recertification -> reattestation
    reps2 = [
        ("RECERTIFIED", "REATTESTED"),
        ("RECERTIFICATION", "REATTESTATION"),
        ("Recertified", "Reattested"),
        ("Recertification", "Reattestation"),
        ("recertified", "reattested"),
        ("recertification", "reattestation"),
    ]
    for a, b in reps2:
        out = out.replace(a, b)
    # Stage 3: unprotect
    reps3 = [
        ("@@REVALIDATED_U@@", "REVALIDATED"),
        ("@@REVALIDATION_U@@", "REVALIDATION"),
        ("@@Revalidated@@", "Revalidated"),
        ("@@Revalidation@@", "Revalidation"),
        ("@@revalidated@@", "revalidated"),
        ("@@revalidation@@", "revalidation"),
    ]
    for a, b in reps3:
        out = out.replace(a, b)
    return out


def main() -> None:
    path = Path("src/blackhole_agent/capability_compounder.py")
    text = path.read_text(encoding="utf-8")

    if "def builtin_revalidation_plane" in text:
        print("revalidation plane already present; abort")
        return

    start_marker = "REATTESTATION_BUNDLE_SCHEMA = 1"
    end_marker = "def seed_bootstrap_capabilities"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"markers not found start={start} end={end}")

    block = text[start:end]
    print("block_len", len(block))

    new_block = transform_reattestation_to_revalidation(block)
    for must in [
        "REVALIDATION_BUNDLE_SCHEMA",
        "def builtin_revalidation_plane",
        "def run_revalidation_plane",
        "run_reattestation_plane",
        "bound_reattestation_root",
        "min_reattestations",
        "min_revalidations",
    ]:
        print(must, must in new_block)
    print("REATTESTATION_BUNDLE leftover", "REATTESTATION_BUNDLE_SCHEMA" in new_block)
    print("recertification leftover", new_block.lower().count("recertification"))
    print("reattestation count", new_block.lower().count("reattestation"))
    print("revalidation count", new_block.lower().count("revalidation"))

    insertion = new_block
    if not insertion.endswith("\n\n"):
        if insertion.endswith("\n"):
            insertion += "\n"
        else:
            insertion += "\n\n"

    new_text = text[:end] + insertion + text[end:]

    # keyword routes
    kw_anchor = (
        '    ("reattestation adequacy", ("capability.reattestation-plane", '
        '"capability.recertification-plane", "capability.assurance-plane")),\n'
    )
    kw_insert = (
        kw_anchor
        + '    ("revalidation", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.recertification-plane")),\n'
        + '    ("revalidated", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.finality-plane")),\n'
        + '    ("revalidation plan", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.assurance-plane")),\n'
        + '    ("revalidation-root", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.lineage-plane")),\n'
        + '    ("revalidation discharge", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.quorum-plane")),\n'
        + '    ("posted revalidation", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.actuation-plane")),\n'
        + '    ("revalidation adequacy", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.assurance-plane")),\n'
    )
    if kw_anchor not in new_text:
        raise SystemExit("kw anchor missing")
    if "revalidation adequacy" not in new_text:
        new_text = new_text.replace(kw_anchor, kw_insert, 1)
        print("keywords inserted")

    pred_anchor = '''        "reattestation_ok",
        "reattested_ok",
        "min_reattestations",
        "reattestation_root_valid",
    }
)'''
    pred_insert = '''        "reattestation_ok",
        "reattested_ok",
        "min_reattestations",
        "reattestation_root_valid",
        "revalidation_ok",
        "revalidated_ok",
        "min_revalidations",
        "revalidation_root_valid",
    }
)'''
    if pred_anchor not in new_text:
        raise SystemExit("pred anchor missing")
    new_text = new_text.replace(pred_anchor, pred_insert, 1)
    print("predicate kinds inserted")

    extract_anchor = '''    if re.search(r"\\breattestation_root_valid\\b", lower) or (
        re.search(r"\\breattestation[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "reattestation_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower) or re.search(
'''
    extract_insert = '''    if re.search(r"\\breattestation_root_valid\\b", lower) or (
        re.search(r"\\breattestation[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "reattestation_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brevalidation_ok\\b", lower) or (
        re.search(r"\\brun_revalidation_plane\\b", lower) and (
            "revalidation" in lower or "plan" in lower
        )
    ):
        found.append({"kind": "revalidation_ok", "arg": "", "source": chunk})
    if re.search(r"\\brevalidated_ok\\b", lower) or (
        re.search(r"\\brevalidated\\b", lower)
        and "revalidation" in lower
        and "revalidation-plane" not in lower
        and "revalidation_plane" not in lower
    ):
        found.append({"kind": "revalidated_ok", "arg": "", "source": chunk})
    if re.search(r"\\brevalidated\\b", lower) and not any(
        item.get("kind") == "revalidated_ok" for item in found
    ):
        found.append({"kind": "revalidated_ok", "arg": "", "source": chunk})
    m = re.search(r"min_revalidations\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_revalidations", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?revalidations?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_revalidations" for item in found):
        found.append({"kind": "min_revalidations", "arg": m.group(1), "source": chunk})
    m = re.search(r"revalidation_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_revalidations" for item in found):
        found.append({"kind": "min_revalidations", "arg": m.group(1), "source": chunk})
    if re.search(r"\\brevalidation_root_valid\\b", lower) or (
        re.search(r"\\brevalidation[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "revalidation_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower) or re.search(
'''
    if extract_anchor not in new_text:
        raise SystemExit("extract anchor missing")
    new_text = new_text.replace(extract_anchor, extract_insert, 1)
    print("extract predicates inserted")

    eval_anchor = '''        return ok, f"reattestation_root_valid={ok}"



    if kind == "program_passes":
'''
    eval_insert = '''        return ok, f"reattestation_root_valid={ok}"

    if kind in {
        "revalidation_ok",
        "revalidated_ok",
        "min_revalidations",
        "revalidation_root_valid",
    }:
        plane = (
            context.get("revalidation")
            or context.get("revalidation_plane")
            or context.get("discharge")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_revalidation_disk_evidence(context)
            if disk:
                plane = {**(plane if isinstance(plane, Mapping) else {}), **disk}
        if kind == "revalidation_ok":
            ok = bool(plane.get("ok"))
            return ok, f"revalidation_ok={ok}"
        if kind == "revalidated_ok":
            if "revalidated" in plane:
                ok = plane.get("revalidated") is True and bool(plane.get("ok", True))
            elif "revalidated_ok" in plane:
                ok = plane.get("revalidated_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("revalidation_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"revalidated_ok={ok}"
        if kind == "min_revalidations":
            need = int(float(arg or "0"))
            have = context.get("revalidation_count")
            if have is None or int(have or 0) < need:
                have = (
                    plane.get("revalidation_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                    or have
                )
            if have is None:
                have = context.get("tip_revalidation_height")
            have_i = int(have or 0)
            return have_i >= need, f"revalidations={have_i} need>={need}"
        if "revalidation_root_valid" in plane:
            ok = plane.get("revalidation_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("revalidation_certificate")
                or plane.get("certificate")
                or context.get("revalidation_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_revalidation_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("revalidation_root") or plane.get("tip_revalidation_root")
                )
        return ok, f"revalidation_root_valid={ok}"

    if kind == "program_passes":
'''
    if eval_anchor not in new_text:
        raise SystemExit("eval anchor missing")
    new_text = new_text.replace(eval_anchor, eval_insert, 1)
    print("eval predicates inserted")

    cap_marker = '''            tags=(
                "reattestation",
                "order",
                "recertification",
                "plane",
                "certificate",
                "adversarial",
                "hash-chain",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),



    ]

    for seed in seeds:
'''

    cap_seed = '''            tags=(
                "reattestation",
                "order",
                "recertification",
                "plane",
                "certificate",
                "adversarial",
                "hash-chain",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),

        Capability(
            id="capability.revalidation-plane",
            name="Revalidation plane over reattestation",
            description=(
                "Closed revalidation plane: multi-reattestation orders → deterministic "
                "hash-chained revalidation orders with revalidation plan digests bound to "
                "reattestation roots → revalidation certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-reattestation/double-revalidation/forged-root/"
                "gap/digest-tamper/single-revalidation falsification with genesis replay matching "
                "tip — past reattested actions without revalidation orders."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_revalidation_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_revalidation_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='revalidation over reattestation'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "os.environ['BLACKHOLE_REVALIDATION_RUN_REATTESTATION']='1'; "
                "os.environ['BLACKHOLE_REATTESTATION_RUN_RECERTIFICATION']='1'; "
                "os.environ['BLACKHOLE_RECERTIFICATION_RUN_REAUTHORIZATION']='1'; "
                "os.environ['BLACKHOLE_REAUTHORIZATION_RUN_REINSTATEMENT']='1'; "
                "os.environ['BLACKHOLE_REORGANIZATION_RUN_RECOVERY']='1'; "
                "os.environ['BLACKHOLE_RECOVERY_RUN_RESILIENCE']='1'; "
                "os.environ['BLACKHOLE_RESILIENCE_RUN_STRESS']='1'; "
                "os.environ['BLACKHOLE_STRESS_RUN_RISK']='1'; "
                "os.environ['BLACKHOLE_RISK_RUN_SOLVENCY']='1'; "
                "os.environ['BLACKHOLE_SOLVENCY_RUN_CAPITAL']='1'; "
                "os.environ['BLACKHOLE_CAPITAL_RUN_FUNDING']='1'; "
                "os.environ['BLACKHOLE_FUNDING_RUN_LIQUIDITY']='1'; "
                "os.environ['BLACKHOLE_LIQUIDITY_RUN_COLLATERAL']='1'; "
                "os.environ['BLACKHOLE_COLLATERAL_RUN_MARGIN']='1'; "
                "os.environ['BLACKHOLE_MARGIN_RUN_CLEARING']='1'; "
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
                "os.environ['BLACKHOLE_MARGIN_MIN_MARGINS']='2'; "
                "os.environ['BLACKHOLE_COLLATERAL_MIN_COLLATERALS']='2'; "
                "os.environ['BLACKHOLE_LIQUIDITY_MIN_LIQUIDITIES']='2'; "
                "os.environ['BLACKHOLE_FUNDING_MIN_FUNDINGS']='2'; "
                "os.environ['BLACKHOLE_CAPITAL_MIN_CAPITALS']='2'; "
                "os.environ['BLACKHOLE_SOLVENCY_MIN_SOLVENCIES']='2'; "
                "os.environ['BLACKHOLE_RISK_MIN_RISKS']='2'; "
                "os.environ['BLACKHOLE_STRESS_MIN_STRESSES']='2'; "
                "os.environ['BLACKHOLE_RESILIENCE_MIN_RESILIENCES']='2'; "
                "os.environ['BLACKHOLE_RECOVERY_MIN_RECOVERIES']='2'; "
                "os.environ['BLACKHOLE_RESOLUTION_MIN_RESOLUTIONS']='2'; "
                "os.environ['BLACKHOLE_REINSTATEMENT_MIN_REINSTATEMENTS']='2'; "
                "os.environ['BLACKHOLE_REAUTHORIZATION_MIN_REAUTHORIZATIONS']='2'; "
                "os.environ['BLACKHOLE_RECERTIFICATION_MIN_RECERTIFICATIONS']='2'; "
                "os.environ['BLACKHOLE_REATTESTATION_MIN_REATTESTATIONS']='2'; "
                "os.environ['BLACKHOLE_REVALIDATION_MIN_REVALIDATIONS']='2'; "
                "os.environ['BLACKHOLE_REVALIDATION_RUN_REATTESTATION']='1'; "
                "os.environ['BLACKHOLE_REORGANIZATION_RUN_RESOLUTION']='1'; "
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-revalidation.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-revalidation-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-revalidation-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-revalidation-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-revalidation-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-revalidation-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-revalidation-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-revalidation-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-revalidation-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-revalidation-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-revalidation-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-revalidation-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_SOLVENCY_BUNDLE_PATH', str(Path('artifacts')/'solvency-bundles'/'proof-revalidation-solvency.json')); "
                "os.environ.setdefault('BLACKHOLE_RISK_BUNDLE_PATH', str(Path('artifacts')/'risk-bundles'/'proof-revalidation-risk.json')); "
                "os.environ.setdefault('BLACKHOLE_STRESS_BUNDLE_PATH', str(Path('artifacts')/'stress-bundles'/'proof-revalidation-stress.json')); "
                "os.environ.setdefault('BLACKHOLE_RESILIENCE_BUNDLE_PATH', str(Path('artifacts')/'resilience-bundles'/'proof-revalidation-resilience.json')); "
                "os.environ.setdefault('BLACKHOLE_RECOVERY_BUNDLE_PATH', str(Path('artifacts')/'recovery-bundles'/'proof-revalidation-recovery.json')); "
                "os.environ.setdefault('BLACKHOLE_REINSTATEMENT_BUNDLE_PATH', str(Path('artifacts')/'reinstatement-bundles'/'proof-revalidation-reinstatement.json')); "
                "os.environ.setdefault('BLACKHOLE_REAUTHORIZATION_BUNDLE_PATH', str(Path('artifacts')/'reauthorization-bundles'/'proof-revalidation-reauthorization.json')); "
                "os.environ.setdefault('BLACKHOLE_RECERTIFICATION_BUNDLE_PATH', str(Path('artifacts')/'recertification-bundles'/'proof-revalidation-recertification.json')); "
                "os.environ.setdefault('BLACKHOLE_REATTESTATION_BUNDLE_PATH', str(Path('artifacts')/'reattestation-bundles'/'proof-revalidation-reattestation.json')); "
                "os.environ.setdefault('BLACKHOLE_REVALIDATION_BUNDLE_PATH', str(Path('artifacts')/'revalidation-bundles'/'proof-revalidation.json')); "
                "r=builtin_revalidation_plane(); assert r['ok'] and r.get('action')=='revalidation_plane' "
                "and r.get('revalidated') is True and int(r.get('revalidation_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('revalidation_certificate',{}).get('valid') "
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
                "capability.clearing-plane",
                "capability.margin-plane",
                "capability.collateral-plane",
                "capability.liquidity-plane",
                "capability.funding-plane",
                "capability.capital-plane",
                "capability.solvency-plane",
                "capability.risk-plane",
                "capability.stress-plane",
                "capability.resilience-plane",
                "capability.recovery-plane",
                "capability.resolution-plane",
                "capability.restructuring-plane",
                "capability.reorganization-plane",
                "capability.reattestation-plane",
                "capability.recertification-plane",
                "capability.reauthorization-plane",
                "capability.reinstatement-plane",
                "capability.rehabilitation-plane",
                "capability.transfer-plane",
                "capability.ablation-proof",
                "capability.adversarial-contract",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
            ),
            capability_delta=(
                "Revalidation plane posts multi-reattestation orders into deterministic hash-chained "
                "revalidation orders with revalidation plan digests bound to reattestation roots, "
                "revalidation certificates, sterile rehydrate+prove, and adversarial falsification "
                "without skill-route discovery."
            ),
            tags=(
                "revalidation",
                "order",
                "reattestation",
                "plane",
                "certificate",
                "adversarial",
                "hash-chain",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),



    ]

    for seed in seeds:
'''

    if cap_marker not in new_text:
        raise SystemExit("cap marker missing")
    new_text = new_text.replace(cap_marker, cap_seed, 1)
    print("capability seed inserted")

    path.write_text(new_text, encoding="utf-8")
    print("wrote", path)
    print("new size", len(new_text))
    print("builtin_revalidation present", "def builtin_revalidation_plane" in new_text)
    print("seed revalidation present", 'id="capability.revalidation-plane"' in new_text)


if __name__ == "__main__":
    main()
