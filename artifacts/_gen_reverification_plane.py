"""Generate re-verification plane by transforming revalidation plane."""
from __future__ import annotations

from pathlib import Path


def transform_revalidation_to_reverification(src: str) -> str:
    # Stage 1: protect new-plane tokens (longest first)
    reps = [
        ("REVALIDATED", "@@REVERIFIED_U@@"),
        ("REVALIDATION", "@@REVERIFICATION_U@@"),
        ("Revalidated", "@@Reverified@@"),
        ("Revalidation", "@@Reverification@@"),
        ("revalidated", "@@reverified@@"),
        ("revalidation", "@@reverification@@"),
    ]
    out = src
    for a, b in reps:
        out = out.replace(a, b)
    # Stage 2a: promote bound layer reattestation -> revalidation
    reps2 = [
        ("REATTESTED", "REVALIDATED"),
        ("REATTESTATION", "REVALIDATION"),
        ("Reattested", "Revalidated"),
        ("Reattestation", "Revalidation"),
        ("reattested", "revalidated"),
        ("reattestation", "revalidation"),
    ]
    for a, b in reps2:
        out = out.replace(a, b)
    # Stage 2b: promote grandparent interface recertification -> reattestation
    # so parent calls use run_reattestation=/min_reattestations= expected by revalidation plane.
    reps2b = [
        ("RECERTIFIED", "REATTESTED"),
        ("RECERTIFICATION", "REATTESTATION"),
        ("Recertified", "Reattested"),
        ("Recertification", "Reattestation"),
        ("recertified", "reattested"),
        ("recertification", "reattestation"),
    ]
    for a, b in reps2b:
        out = out.replace(a, b)
    # Stage 3: unprotect
    reps3 = [
        ("@@REVERIFIED_U@@", "REVERIFIED"),
        ("@@REVERIFICATION_U@@", "REVERIFICATION"),
        ("@@Reverified@@", "Reverified"),
        ("@@Reverification@@", "Reverification"),
        ("@@reverified@@", "reverified"),
        ("@@reverification@@", "reverification"),
    ]
    for a, b in reps3:
        out = out.replace(a, b)
    return out


def main() -> None:
    path = Path("src/blackhole_agent/capability_compounder.py")
    text = path.read_text(encoding="utf-8")

    if "def builtin_reverification_plane" in text:
        print("reverification plane already present; abort")
        return

    start_marker = "REVALIDATION_BUNDLE_SCHEMA = 1"
    end_marker = "def seed_bootstrap_capabilities"
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"markers not found start={start} end={end}")

    block = text[start:end]
    print("block_len", len(block))

    new_block = transform_revalidation_to_reverification(block)
    for must in [
        "REVERIFICATION_BUNDLE_SCHEMA",
        "def builtin_reverification_plane",
        "def run_reverification_plane",
        "run_revalidation_plane",
        "bound_revalidation_root",
        "min_revalidations",
        "min_reverifications",
    ]:
        print(must, must in new_block)
    print("REVALIDATION_BUNDLE leftover", "REVALIDATION_BUNDLE_SCHEMA" in new_block)
    print("reattestation leftover", new_block.lower().count("reattestation"))
    print("revalidation count", new_block.lower().count("revalidation"))
    print("reverification count", new_block.lower().count("reverification"))

    insertion = new_block
    if not insertion.endswith("\n\n"):
        if insertion.endswith("\n"):
            insertion += "\n"
        else:
            insertion += "\n\n"

    new_text = text[:end] + insertion + text[end:]

    # keyword routes
    kw_anchor = (
        '    ("revalidation adequacy", ("capability.revalidation-plane", '
        '"capability.reattestation-plane", "capability.assurance-plane")),\n'
    )
    kw_insert = (
        kw_anchor
        + '    ("reverification", ("capability.reverification-plane", '
        '"capability.revalidation-plane", "capability.reattestation-plane")),\n'
        + '    ("reverified", ("capability.reverification-plane", '
        '"capability.revalidation-plane", "capability.finality-plane")),\n'
        + '    ("reverification plan", ("capability.reverification-plane", '
        '"capability.revalidation-plane", "capability.assurance-plane")),\n'
        + '    ("reverification-root", ("capability.reverification-plane", '
        '"capability.revalidation-plane", "capability.lineage-plane")),\n'
        + '    ("reverification discharge", ("capability.reverification-plane", '
        '"capability.revalidation-plane", "capability.quorum-plane")),\n'
        + '    ("posted reverification", ("capability.reverification-plane", '
        '"capability.revalidation-plane", "capability.actuation-plane")),\n'
        + '    ("reverification adequacy", ("capability.reverification-plane", '
        '"capability.revalidation-plane", "capability.assurance-plane")),\n'
    )
    if kw_anchor not in new_text:
        raise SystemExit("kw anchor missing")
    if "reverification adequacy" not in new_text:
        new_text = new_text.replace(kw_anchor, kw_insert, 1)
        print("keywords inserted")

    pred_anchor = '''        "revalidation_ok",
        "revalidated_ok",
        "min_revalidations",
        "revalidation_root_valid",
    }
)'''
    pred_insert = '''        "revalidation_ok",
        "revalidated_ok",
        "min_revalidations",
        "revalidation_root_valid",
        "reverification_ok",
        "reverified_ok",
        "min_reverifications",
        "reverification_root_valid",
    }
)'''
    if pred_anchor not in new_text:
        raise SystemExit("pred anchor missing")
    new_text = new_text.replace(pred_anchor, pred_insert, 1)
    print("predicate kinds inserted")

    extract_anchor = '''    if re.search(r"\\brevalidation_root_valid\\b", lower) or (
        re.search(r"\\brevalidation[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "revalidation_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower) or re.search(
'''
    extract_insert = '''    if re.search(r"\\brevalidation_root_valid\\b", lower) or (
        re.search(r"\\brevalidation[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "revalidation_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\breverification_ok\\b", lower) or (
        re.search(r"\\brun_reverification_plane\\b", lower) and (
            "reverification" in lower or "plan" in lower
        )
    ):
        found.append({"kind": "reverification_ok", "arg": "", "source": chunk})
    if re.search(r"\\breverified_ok\\b", lower) or (
        re.search(r"\\breverified\\b", lower)
        and "reverification" in lower
        and "reverification-plane" not in lower
        and "reverification_plane" not in lower
    ):
        found.append({"kind": "reverified_ok", "arg": "", "source": chunk})
    if re.search(r"\\breverified\\b", lower) and not any(
        item.get("kind") == "reverified_ok" for item in found
    ):
        found.append({"kind": "reverified_ok", "arg": "", "source": chunk})
    m = re.search(r"min_reverifications\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_reverifications", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?reverifications?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_reverifications" for item in found):
        found.append({"kind": "min_reverifications", "arg": m.group(1), "source": chunk})
    m = re.search(r"reverification_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_reverifications" for item in found):
        found.append({"kind": "min_reverifications", "arg": m.group(1), "source": chunk})
    if re.search(r"\\breverification_root_valid\\b", lower) or (
        re.search(r"\\breverification[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "reverification_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower) or re.search(
'''
    if extract_anchor not in new_text:
        raise SystemExit("extract anchor missing")
    new_text = new_text.replace(extract_anchor, extract_insert, 1)
    print("extract predicates inserted")

    eval_anchor = '''        return ok, f"revalidation_root_valid={ok}"

    if kind == "program_passes":
'''
    eval_insert = '''        return ok, f"revalidation_root_valid={ok}"

    if kind in {
        "reverification_ok",
        "reverified_ok",
        "min_reverifications",
        "reverification_root_valid",
    }:
        plane = (
            context.get("reverification")
            or context.get("reverification_plane")
            or context.get("discharge")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_reverification_disk_evidence(context)
            if disk:
                plane = {**(plane if isinstance(plane, Mapping) else {}), **disk}
        if kind == "reverification_ok":
            ok = bool(plane.get("ok"))
            return ok, f"reverification_ok={ok}"
        if kind == "reverified_ok":
            if "reverified" in plane:
                ok = plane.get("reverified") is True and bool(plane.get("ok", True))
            elif "reverified_ok" in plane:
                ok = plane.get("reverified_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("reverification_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"reverified_ok={ok}"
        if kind == "min_reverifications":
            need = int(float(arg or "0"))
            have = context.get("reverification_count")
            if have is None or int(have or 0) < need:
                have = (
                    plane.get("reverification_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                    or have
                )
            if have is None:
                have = context.get("tip_reverification_height")
            have_i = int(have or 0)
            return have_i >= need, f"reverifications={have_i} need>={need}"
        if "reverification_root_valid" in plane:
            ok = plane.get("reverification_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("reverification_certificate")
                or plane.get("certificate")
                or context.get("reverification_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_reverification_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("reverification_root") or plane.get("tip_reverification_root")
                )
        return ok, f"reverification_root_valid={ok}"

    if kind == "program_passes":
'''
    if eval_anchor not in new_text:
        raise SystemExit("eval anchor missing")
    new_text = new_text.replace(eval_anchor, eval_insert, 1)
    print("eval predicates inserted")

    cap_marker = '''            tags=(
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

    cap_seed = '''            tags=(
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

        Capability(
            id="capability.reverification-plane",
            name="Reverification plane over revalidation",
            description=(
                "Closed reverification plane: multi-revalidation orders → deterministic "
                "hash-chained reverification orders with reverification plan digests bound to "
                "revalidation roots → reverification certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-revalidation/double-reverification/forged-root/"
                "gap/digest-tamper/single-reverification falsification with genesis replay matching "
                "tip — past revalidated actions without reverification orders."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_reverification_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_reverification_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='reverification over revalidation'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "os.environ['BLACKHOLE_REVERIFICATION_RUN_REVALIDATION']='1'; "
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
                "os.environ['BLACKHOLE_REVERIFICATION_MIN_REVERIFICATIONS']='2'; "
                "os.environ['BLACKHOLE_REVERIFICATION_RUN_REVALIDATION']='1'; "
                "os.environ['BLACKHOLE_REORGANIZATION_RUN_RESOLUTION']='1'; "
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-reverification.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-reverification-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-reverification-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-reverification-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-reverification-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-reverification-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-reverification-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-reverification-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-reverification-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-reverification-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-reverification-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-reverification-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_SOLVENCY_BUNDLE_PATH', str(Path('artifacts')/'solvency-bundles'/'proof-reverification-solvency.json')); "
                "os.environ.setdefault('BLACKHOLE_RISK_BUNDLE_PATH', str(Path('artifacts')/'risk-bundles'/'proof-reverification-risk.json')); "
                "os.environ.setdefault('BLACKHOLE_STRESS_BUNDLE_PATH', str(Path('artifacts')/'stress-bundles'/'proof-reverification-stress.json')); "
                "os.environ.setdefault('BLACKHOLE_RESILIENCE_BUNDLE_PATH', str(Path('artifacts')/'resilience-bundles'/'proof-reverification-resilience.json')); "
                "os.environ.setdefault('BLACKHOLE_RECOVERY_BUNDLE_PATH', str(Path('artifacts')/'recovery-bundles'/'proof-reverification-recovery.json')); "
                "os.environ.setdefault('BLACKHOLE_REINSTATEMENT_BUNDLE_PATH', str(Path('artifacts')/'reinstatement-bundles'/'proof-reverification-reinstatement.json')); "
                "os.environ.setdefault('BLACKHOLE_REAUTHORIZATION_BUNDLE_PATH', str(Path('artifacts')/'reauthorization-bundles'/'proof-reverification-reauthorization.json')); "
                "os.environ.setdefault('BLACKHOLE_RECERTIFICATION_BUNDLE_PATH', str(Path('artifacts')/'recertification-bundles'/'proof-reverification-recertification.json')); "
                "os.environ.setdefault('BLACKHOLE_REATTESTATION_BUNDLE_PATH', str(Path('artifacts')/'reattestation-bundles'/'proof-reverification-reattestation.json')); "
                "os.environ.setdefault('BLACKHOLE_REVALIDATION_BUNDLE_PATH', str(Path('artifacts')/'revalidation-bundles'/'proof-reverification-revalidation.json')); "
                "os.environ.setdefault('BLACKHOLE_REVERIFICATION_BUNDLE_PATH', str(Path('artifacts')/'reverification-bundles'/'proof-reverification.json')); "
                "r=builtin_reverification_plane(); assert r['ok'] and r.get('action')=='reverification_plane' "
                "and r.get('reverified') is True and int(r.get('reverification_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('reverification_certificate',{}).get('valid') "
                "and r.get('adversarial',{}).get('ok') and not r.get('used_skill_route_discovery')\\""
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
                "capability.revalidation-plane",
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
                "Reverification plane posts multi-revalidation orders into deterministic hash-chained "
                "reverification orders with reverification plan digests bound to revalidation roots, "
                "reverification certificates, sterile rehydrate+prove, and adversarial falsification "
                "without skill-route discovery."
            ),
            tags=(
                "reverification",
                "order",
                "revalidation",
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
    print("builtin_reverification present", "def builtin_reverification_plane" in new_text)
    print("seed reverification present", 'id="capability.reverification-plane"' in new_text)


if __name__ == "__main__":
    main()
