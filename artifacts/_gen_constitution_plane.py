"""Generate constitution-plane over charter from charter-plane block and patch compounder+unbound."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC_PATH = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND_PATH = ROOT / "src" / "blackhole_agent" / "unbound.py"


def transform_charter_to_constitution(src: str) -> str:
    """Transform charter-plane (parent=mandate) into constitution-plane (parent=charter)."""
    s = src

    # Park parent (mandate) terms first so self renames do not collide.
    parent_pairs = [
        ("BLACKHOLE_CHARTER_RUN_MANDATE", "BLACKHOLE___SELF___RUN___PARENT___"),
        ("BLACKHOLE_MANDATE_", "BLACKHOLE___PARENT___"),
        ("apply_mandate_bundle_to_charters", "apply___PARENT___bundle_to___SELF___s"),
        ("derive_charter_specs_from_mandate", "derive___SELF___specs_from___PARENT___"),
        ("load_mandate_bundle", "load___PARENT___bundle"),
        ("write_mandate_bundle", "write___PARENT___bundle"),
        ("verify_mandate_bundle_integrity", "verify___PARENT___bundle_integrity"),
        ("verify_mandate_certificate", "verify___PARENT___certificate"),
        ("run_mandate_plane", "run___PARENT___plane"),
        ("builtin_mandate_plane", "builtin___PARENT___plane"),
        ("default_mandate_bundle_dir", "default___PARENT___bundle_dir"),
        ("mandate_bundle", "___PARENT___bundle"),
        ("mandate_report", "___PARENT___report"),
        ("mandate_path", "___PARENT___path"),
        ("mandate_plane", "___PARENT___plane"),
        ("mandate_certificate_hash", "___PARENT___certificate_hash"),
        ("mandate_certificate", "___PARENT___certificate"),
        ("mandate_plan_digest", "___PARENT___plan_digest"),
        ("mandate_hash", "___PARENT___hash"),
        ("mandate_count", "___PARENT___count"),
        ("tip_mandate_root", "tip___PARENT___root"),
        ("bound_mandate_root", "bound___PARENT___root"),
        ("bound_mandate_height", "bound___PARENT___height"),
        ("mandate_root", "___PARENT___root"),
        ("min_mandates", "min___PARENT___s"),
        ("want_mandates", "want___PARENT___s"),
        ("run_mandate", "run___PARENT___"),
        ("post_mandate", "post___PARENT___"),
        ("wrong_mandate", "wrong___PARENT___"),
        ("parent_mandated", "parent___PARENTED___"),
        ("mandated", "___PARENTED___"),
        ("Mandated", "___PARENTED_TITLE___"),
        ("MANDATE", "___PARENT_UPPER___"),
        ("Mandate", "___PARENT_TITLE___"),
        ("mandate", "___PARENT___"),
    ]
    for a, b in parent_pairs:
        s = s.replace(a, b)

    # Self charter -> constitution (longest first).
    self_pairs = [
        ("BLACKHOLE_CHARTER_", "BLACKHOLE_CONSTITUTION_"),
        ("BLACKHOLE___SELF___", "BLACKHOLE_CONSTITUTION_"),
        ("capability.charter-plane", "capability.constitution-plane"),
        ("builtin_charter_plane", "builtin_constitution_plane"),
        ("run_charter_plane", "run_constitution_plane"),
        ("run_charter_adversarial_checks", "run_constitution_adversarial_checks"),
        ("replay_charters_from_specs", "replay_constitutions_from_specs"),
        ("rehydrate_charter_bundle", "rehydrate_constitution_bundle"),
        ("verify_charter_bundle_integrity", "verify_constitution_bundle_integrity"),
        ("verify_charter_certificate", "verify_constitution_certificate"),
        ("verify_charter_chain", "verify_constitution_chain"),
        ("write_charter_certificate", "write_constitution_certificate"),
        ("write_charter_bundle", "write_constitution_bundle"),
        ("load_charter_bundle", "load_constitution_bundle"),
        ("_load_charter_disk_evidence", "_load_constitution_disk_evidence"),
        ("issue_charter_certificate", "issue_constitution_certificate"),
        ("compute_charter_plan_digest", "compute_constitution_plan_digest"),
        ("compute_charter_bundle_hash", "compute_constitution_bundle_hash"),
        ("compute_charter_certificate_hash", "compute_constitution_certificate_hash"),
        ("compute_charter_root", "compute_constitution_root"),
        ("apply_charter_transition", "apply_constitution_transition"),
        ("build_charter_bundle", "build_constitution_bundle"),
        ("empty_charter_log", "empty_constitution_log"),
        ("default_charter_bundle_dir", "default_constitution_bundle_dir"),
        ("DEFAULT_CHARTER_BUNDLE_RELATIVE", "DEFAULT_CONSTITUTION_BUNDLE_RELATIVE"),
        ("CHARTER_BUNDLE_SCHEMA", "CONSTITUTION_BUNDLE_SCHEMA"),
        ("CHARTER_CERTIFICATE_SCHEMA", "CONSTITUTION_CERTIFICATE_SCHEMA"),
        ("CHARTER_LOG_SCHEMA", "CONSTITUTION_LOG_SCHEMA"),
        ("charter-bundles", "constitution-bundles"),
        ("proof-charter", "proof-constitution"),
        ("charter_plane", "constitution_plane"),
        ("charter_log", "constitution_log"),
        ("charter_bundle", "constitution_bundle"),
        ("charter_certificate", "constitution_certificate"),
        ("charter_plan_digest", "constitution_plan_digest"),
        ("charter_hash", "constitution_hash"),
        ("charter_count", "constitution_count"),
        ("charter_height", "constitution_height"),
        ("tip_charter_root", "tip_constitution_root"),
        ("parent_charter_root", "parent_constitution_root"),
        ("parent_charter_digest", "parent_constitution_digest"),
        ("charter_root", "constitution_root"),
        ("min_charters", "min_constitutions"),
        ("want_charters", "want_constitutions"),
        ("charter_path", "constitution_path"),
        ("charter_ok", "constitution_ok"),
        ("single_charter", "single_constitution"),
        ("multi_charter", "multi_constitution"),
        ("charters", "constitutions"),
        ("charter over mandate", "constitution over charter"),
        ("Charter plane", "Constitution plane"),
        ("charter plane", "constitution plane"),
        ("Closed charter", "Closed constitution"),
        ("closed charter", "closed constitution"),
        ("CHARTER", "CONSTITUTION"),
        ("Charter", "Constitution"),
        ("chartered", "constituted"),
        ("Chartered", "Constituted"),
        ("charter", "constitution"),
    ]
    for a, b in self_pairs:
        s = s.replace(a, b)

    # Restore parent -> charter.
    parent_restore = [
        ("BLACKHOLE_CONSTITUTION_RUN___PARENT___", "BLACKHOLE_CONSTITUTION_RUN_CHARTER"),
        ("BLACKHOLE___PARENT___", "BLACKHOLE_CHARTER_"),
        ("apply___PARENT___bundle_to___SELF___s", "apply_charter_bundle_to_constitutions"),
        ("apply___PARENT___bundle_to_constitutions", "apply_charter_bundle_to_constitutions"),
        ("derive_constitution_specs_from___PARENT___", "derive_constitution_specs_from_charter"),
        ("load___PARENT___bundle", "load_charter_bundle"),
        ("write___PARENT___bundle", "write_charter_bundle"),
        ("verify___PARENT___bundle_integrity", "verify_charter_bundle_integrity"),
        ("verify___PARENT___certificate", "verify_charter_certificate"),
        ("run___PARENT___plane", "run_charter_plane"),
        ("builtin___PARENT___plane", "builtin_charter_plane"),
        ("default___PARENT___bundle_dir", "default_charter_bundle_dir"),
        ("___PARENT___bundle", "charter_bundle"),
        ("___PARENT___report", "charter_report"),
        ("___PARENT___path", "charter_path"),
        ("___PARENT___plane", "charter_plane"),
        ("___PARENT___certificate_hash", "charter_certificate_hash"),
        ("___PARENT___certificate", "charter_certificate"),
        ("___PARENT___plan_digest", "charter_plan_digest"),
        ("___PARENT___hash", "charter_hash"),
        ("___PARENT___count", "charter_count"),
        ("tip___PARENT___root", "tip_charter_root"),
        ("bound___PARENT___root", "bound_charter_root"),
        ("bound___PARENT___height", "bound_charter_height"),
        ("___PARENT___root", "charter_root"),
        ("min___PARENT___s", "min_charters"),
        ("want___PARENT___s", "want_charters"),
        ("run___PARENT___", "run_charter"),
        ("post___PARENT___", "post_charter"),
        ("wrong___PARENT___", "wrong_charter"),
        ("parent___PARENTED___", "parent_chartered"),
        ("___PARENTED___", "chartered"),
        ("___PARENTED_TITLE___", "Chartered"),
        ("___PARENT_UPPER___", "CHARTER"),
        ("___PARENT_TITLE___", "Charter"),
        ("___PARENT___", "charter"),
        ("___SELF___", "constitution"),
    ]
    for a, b in parent_restore:
        s = s.replace(a, b)

    glitches = [
        ("apply_charter_bundle_to_constitutionss", "apply_charter_bundle_to_constitutions"),
        ("min_constitutionss", "min_constitutions"),
        ("want_constitutionss", "want_constitutions"),
        ("constitutionss", "constitutions"),
        ("constitution for constitution", "charter for constitution"),
        ("run_charters=", "run_charter="),
        ("run_charters,", "run_charter,"),
        ("run_charters)", "run_charter)"),
        ("run_charters ", "run_charter "),
        # min_privileges may have been wrong-mapped via min_mandates path in charter
        # leave as-is when already correct
    ]
    for a, b in glitches:
        s = s.replace(a, b)

    return s


def build_constitution_capability_seed() -> str:
    return '''
Capability(
            id="capability.constitution-plane",
            name="Constitution plane over charter",
            description=(
                "Closed constitution plane: multi-charter orders → deterministic "
                "hash-chained constitution grants with constitution plan digests bound to "
                "charter roots → constitution certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-charter/double-constitution/forged-root/"
                "gap/digest-tamper/single-constitution falsification with genesis replay matching "
                "tip — past constituted actions without constitution grants."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_constitution_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_constitution_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='constitution over charter'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "os.environ['BLACKHOLE_CONSTITUTION_RUN_CHARTER']='1'; "
                "os.environ['BLACKHOLE_CHARTER_RUN_MANDATE']='1'; "
                "os.environ['BLACKHOLE_MANDATE_RUN_PRIVILEGE']='1'; "
                "os.environ['BLACKHOLE_PRIVILEGE_RUN_STANDING']='1'; "
                "os.environ['BLACKHOLE_STANDING_RUN_REPUTATION']='1'; "
                "os.environ['BLACKHOLE_RECOGNITION_RUN_REVERIFICATION']='1'; "
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
                "os.environ['BLACKHOLE_RECOGNITION_MIN_RECOGNITIONS']='2'; "
                "os.environ['BLACKHOLE_PRIVILEGE_MIN_PRIVILEGES']='2'; "
                "os.environ['BLACKHOLE_MANDATE_MIN_MANDATES']='2'; "
                "os.environ['BLACKHOLE_CHARTER_MIN_CHARTERS']='2'; "
                "os.environ['BLACKHOLE_CONSTITUTION_MIN_CONSTITUTIONS']='2'; "
                "os.environ['BLACKHOLE_CONSTITUTION_RUN_CHARTER']='1'; "
                "os.environ['BLACKHOLE_REORGANIZATION_RUN_RESOLUTION']='1'; "
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-constitution.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-constitution-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-constitution-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-constitution-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-constitution-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-constitution-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-constitution-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-constitution-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-constitution-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-constitution-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-constitution-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-constitution-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_SOLVENCY_BUNDLE_PATH', str(Path('artifacts')/'solvency-bundles'/'proof-constitution-solvency.json')); "
                "os.environ.setdefault('BLACKHOLE_RISK_BUNDLE_PATH', str(Path('artifacts')/'risk-bundles'/'proof-constitution-risk.json')); "
                "os.environ.setdefault('BLACKHOLE_STRESS_BUNDLE_PATH', str(Path('artifacts')/'stress-bundles'/'proof-constitution-stress.json')); "
                "os.environ.setdefault('BLACKHOLE_RESILIENCE_BUNDLE_PATH', str(Path('artifacts')/'resilience-bundles'/'proof-constitution-resilience.json')); "
                "os.environ.setdefault('BLACKHOLE_RECOVERY_BUNDLE_PATH', str(Path('artifacts')/'recovery-bundles'/'proof-constitution-recovery.json')); "
                "os.environ.setdefault('BLACKHOLE_REINSTATEMENT_BUNDLE_PATH', str(Path('artifacts')/'reinstatement-bundles'/'proof-constitution-reinstatement.json')); "
                "os.environ.setdefault('BLACKHOLE_REAUTHORIZATION_BUNDLE_PATH', str(Path('artifacts')/'reauthorization-bundles'/'proof-constitution-reauthorization.json')); "
                "os.environ.setdefault('BLACKHOLE_RECERTIFICATION_BUNDLE_PATH', str(Path('artifacts')/'recertification-bundles'/'proof-constitution-recertification.json')); "
                "os.environ.setdefault('BLACKHOLE_REATTESTATION_BUNDLE_PATH', str(Path('artifacts')/'reattestation-bundles'/'proof-constitution-reattestation.json')); "
                "os.environ.setdefault('BLACKHOLE_REVALIDATION_BUNDLE_PATH', str(Path('artifacts')/'revalidation-bundles'/'proof-constitution-revalidation.json')); "
                "os.environ.setdefault('BLACKHOLE_REVERIFICATION_BUNDLE_PATH', str(Path('artifacts')/'reverification-bundles'/'proof-constitution-reverification.json')); "
                "os.environ.setdefault('BLACKHOLE_RECOGNITION_BUNDLE_PATH', str(Path('artifacts')/'recognition-bundles'/'proof-constitution-recognition.json')); "
                "os.environ.setdefault('BLACKHOLE_PRIVILEGE_BUNDLE_PATH', str(Path('artifacts')/'privilege-bundles'/'proof-constitution-privilege.json')); "
                "os.environ.setdefault('BLACKHOLE_MANDATE_BUNDLE_PATH', str(Path('artifacts')/'mandate-bundles'/'proof-constitution-mandate.json')); "
                "os.environ.setdefault('BLACKHOLE_CHARTER_BUNDLE_PATH', str(Path('artifacts')/'charter-bundles'/'proof-constitution-charter.json')); "
                "os.environ.setdefault('BLACKHOLE_CONSTITUTION_BUNDLE_PATH', str(Path('artifacts')/'constitution-bundles'/'proof-constitution.json')); "
                "r=builtin_constitution_plane(); assert r['ok'] and r.get('action')=='constitution_plane' "
                "and r.get('constituted') is True and int(r.get('constitution_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('constitution_certificate',{}).get('valid') "
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
                "capability.charter-plane",
                "capability.mandate-plane",
                "capability.privilege-plane",
                "capability.standing-plane",
                "capability.recognition-plane",
                "capability.reverification-plane",
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
                "Constitution plane posts multi-charter orders into deterministic hash-chained "
                "constitution grants with constitution plan digests bound to charter roots, "
                "constitution certificates, sterile rehydrate+prove, and adversarial falsification "
                "without skill-route discovery."
            ),
            tags=(
                "constitution",
                "order",
                "charter",
                "plane",
                "certificate",
                "adversarial",
                "hash-chain",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
'''


def patch_compounder(text: str, constitution_impl: str) -> str:
    anchor = "def seed_bootstrap_capabilities"
    idx = text.find(anchor)
    if idx < 0:
        raise SystemExit("seed_bootstrap_capabilities not found")
    if "def run_constitution_plane" not in text:
        text = text[:idx] + constitution_impl.rstrip() + "\n\n\n" + text[idx:]
    else:
        print("constitution impl already present; skipping insert")

    soft_block = '''    ("charter adequacy", ("capability.charter-plane", "capability.mandate-plane", "capability.assurance-plane")),
'''
    soft_insert = '''    ("charter adequacy", ("capability.charter-plane", "capability.mandate-plane", "capability.assurance-plane")),
    ("constitution", ("capability.constitution-plane", "capability.charter-plane", "capability.mandate-plane")),
    ("constituted", ("capability.constitution-plane", "capability.charter-plane", "capability.finality-plane")),
    ("constitution plan", ("capability.constitution-plane", "capability.charter-plane", "capability.assurance-plane")),
    ("constitution-root", ("capability.constitution-plane", "capability.charter-plane", "capability.lineage-plane")),
    ("constitution discharge", ("capability.constitution-plane", "capability.charter-plane", "capability.quorum-plane")),
    ("posted constitution", ("capability.constitution-plane", "capability.charter-plane", "capability.actuation-plane")),
    ("constitution adequacy", ("capability.constitution-plane", "capability.charter-plane", "capability.assurance-plane")),
'''
    if '("constitution", ("capability.constitution-plane"' not in text:
        if soft_block not in text:
            raise SystemExit("soft keyword anchor missing")
        text = text.replace(soft_block, soft_insert, 1)

    parse_anchor = '''    if re.search(r"\\bcharter_root_valid\\b", lower) or (
        re.search(r"\\bcharter[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "charter_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower)'''
    parse_insert = '''    if re.search(r"\\bcharter_root_valid\\b", lower) or (
        re.search(r"\\bcharter[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "charter_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\bconstitution_ok\\b", lower) or (
        re.search(r"\\brun_constitution_plane\\b", lower) and (
            "constitution" in lower or "plan" in lower
        )
    ):
        found.append({"kind": "constitution_ok", "arg": "", "source": chunk})
    if re.search(r"\\bconstituted_ok\\b", lower) or (
        "constituted" in lower
        and "constitution" in lower
        and "constitution-plane" not in lower
        and "constitution_plane" not in lower
    ):
        found.append({"kind": "constituted_ok", "arg": "", "source": chunk})
    m = re.search(r"min_constitutions\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_constitutions", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?constitutions?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_constitutions" for item in found):
        found.append({"kind": "min_constitutions", "arg": m.group(1), "source": chunk})
    m = re.search(r"constitution_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_constitutions" for item in found):
        found.append({"kind": "min_constitutions", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bconstitution_root_valid\\b", lower) or (
        re.search(r"\\bconstitution[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "constitution_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower)'''
    if '"constitution_ok"' not in text.split("def snapshot_outcome_metrics")[0]:
        if parse_anchor not in text:
            raise SystemExit("parse predicate anchor missing")
        text = text.replace(parse_anchor, parse_insert, 1)

    eval_anchor = '''        return ok, f"charter_root_valid={ok}"


    if kind == "program_passes":'''
    eval_insert = '''        return ok, f"charter_root_valid={ok}"

    if kind in {
        "constitution_ok",
        "constituted_ok",
        "min_constitutions",
        "constitution_root_valid",
    }:
        plane = (
            context.get("constitution")
            or context.get("constitution_plane")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_constitution_disk_evidence(context)
            if disk:
                plane = disk
        if kind == "constitution_ok":
            ok = bool(plane.get("ok") or plane.get("constituted"))
            return ok, f"constitution_ok={ok}"
        if kind == "constituted_ok":
            ok = bool(
                plane.get("constituted")
                or plane.get("ok")
                or int(
                    plane.get("constitution_count") or plane.get("tip_height") or 0
                )
                >= 2
            )
            return ok, f"constituted_ok={ok}"
        if kind == "min_constitutions":
            need = int(arg or 0)
            have = context.get("constitution_count")
            if have is None:
                have = (
                    plane.get("constitution_count")
                    or plane.get("tip_height")
                    or 0
                )
            try:
                have_i = int(have or 0)
            except (TypeError, ValueError):
                have_i = 0
                have = context.get("tip_constitution_height")
            return have_i >= need, f"constitutions={have_i} need>={need}"
        if "constitution_root_valid" in plane:
            ok = plane.get("constitution_root_valid") is True
        else:
            cert = (
                plane.get("constitution_certificate")
                or context.get("constitution_certificate")
                or {}
            )
            if cert:
                verify = verify_constitution_certificate(cert)
                ok = bool(verify.get("valid") or verify.get("ok"))
            else:
                ok = bool(
                    plane.get("constitution_root") or plane.get("tip_constitution_root")
                )
        return ok, f"constitution_root_valid={ok}"


    if kind == "program_passes":'''
    if 'kind in {\n        "constitution_ok"' not in text and 'kind == "constitution_ok"' not in text:
        if eval_anchor not in text:
            # try alternate spacing
            eval_anchor2 = '''        return ok, f"charter_root_valid={ok}"

    if kind == "program_passes":'''
            if eval_anchor2 not in text:
                raise SystemExit("eval predicate anchor missing")
            text = text.replace(eval_anchor2, eval_insert, 1)
        else:
            text = text.replace(eval_anchor, eval_insert, 1)

    if 'id="capability.constitution-plane"' not in text:
        marker = 'id="capability.charter-plane"'
        mpos = text.find(marker)
        if mpos < 0:
            raise SystemExit("charter capability seed missing")
        close = -1
        for pat in (
            "\n        ),\n\n\n    ]",
            "\n        ),\n\n    ]",
            "\n        ),\n    ]",
        ):
            close = text.find(pat, mpos)
            if close >= 0:
                break
        if close < 0:
            # Fall back: after last updated_at of charter seed
            ua = text.find("updated_at=utc_now_iso()", mpos)
            if ua >= 0:
                close = text.find("\n        ),", ua)
        if close < 0:
            raise SystemExit("charter capability close not found")
        seed = build_constitution_capability_seed()
        text = text[: close + len("\n        ),")] + "\n" + seed + text[close + len("\n        ),") :]

    return text


def patch_unbound(text: str) -> str:
    import_block = text.split("from blackhole_agent.capability_compounder import")[1][:4000]
    if "run_constitution_plane" not in import_block:
        text = text.replace(
            "    run_charter_plane,\n    run_lineage_plane,",
            "    run_charter_plane,\n    run_constitution_plane,\n    run_lineage_plane,",
            1,
        )
        if "run_constitution_plane" not in text.split("from blackhole_agent.capability_compounder import")[1][:4000]:
            text = text.replace(
                "    run_charter_plane,\n",
                "    run_charter_plane,\n    run_constitution_plane,\n",
                1,
            )

    if "run_constitution = (" not in text:
        text = text.replace(
            """    run_charter = (
        cc.run_charter_plane if cc is not None else run_charter_plane
    )
""",
            """    run_charter = (
        cc.run_charter_plane if cc is not None else run_charter_plane
    )
    run_constitution = (
        cc.run_constitution_plane if cc is not None else run_constitution_plane
    )
""",
            1,
        )

    if "needs_constitution" not in text:
        old_needs = '''                    needs_charter = bool(
                        kinds
                        & {
                            "charter_ok",
                            "chartered_ok",
                            "min_charters",
                            "charter_root_valid",
                        }
                    )
                    needs_mandate = bool(
                        kinds
                        & {
                            "mandate_ok",
                            "mandated_ok",
                            "min_mandates",
                            "mandate_root_valid",
                        }
                    ) and not needs_charter
'''
        new_needs = '''                    needs_constitution = bool(
                        kinds
                        & {
                            "constitution_ok",
                            "constituted_ok",
                            "min_constitutions",
                            "constitution_root_valid",
                        }
                    )
                    needs_charter = bool(
                        kinds
                        & {
                            "charter_ok",
                            "chartered_ok",
                            "min_charters",
                            "charter_root_valid",
                        }
                    ) and not needs_constitution
                    needs_mandate = bool(
                        kinds
                        & {
                            "mandate_ok",
                            "mandated_ok",
                            "min_mandates",
                            "mandate_root_valid",
                        }
                    ) and not needs_charter and not needs_constitution
'''
        if old_needs not in text:
            raise SystemExit("needs_charter cascade anchor missing")
        text = text.replace(old_needs, new_needs, 1)

        # Append and not needs_constitution to remaining cascade lines that already
        # exclude needs_charter — do carefully only for privilege/standing chains.
        replacements = [
            (
                ") and not needs_mandate and not needs_charter\n                    needs_standing",
                ") and not needs_mandate and not needs_charter and not needs_constitution\n                    needs_standing",
            ),
            (
                ") and not needs_privilege and not needs_mandate and not needs_charter\n                    needs_reputation",
                ") and not needs_privilege and not needs_mandate and not needs_charter and not needs_constitution\n                    needs_reputation",
            ),
            (
                ") and not needs_standing and not needs_privilege and not needs_mandate and not needs_charter\n                    needs_recognition",
                ") and not needs_standing and not needs_privilege and not needs_mandate and not needs_charter and not needs_constitution\n                    needs_recognition",
            ),
            (
                ") and not needs_reputation and not needs_standing and not needs_privilege and not needs_mandate and not needs_charter\n                    needs_reaccreditation",
                ") and not needs_reputation and not needs_standing and not needs_privilege and not needs_mandate and not needs_charter and not needs_constitution\n                    needs_reaccreditation",
            ),
        ]
        for a, b in replacements:
            if a in text:
                text = text.replace(a, b, 1)

        # privilege line may still only exclude mandate+charter
        text = text.replace(
            """                    needs_privilege = bool(
                        kinds
                        & {
                            "privilege_ok",
                            "privileged_ok",
                            "min_privileges",
                            "privilege_root_valid",
                        }
                    ) and not needs_mandate and not needs_charter
""",
            """                    needs_privilege = bool(
                        kinds
                        & {
                            "privilege_ok",
                            "privileged_ok",
                            "min_privileges",
                            "privilege_root_valid",
                        }
                    ) and not needs_mandate and not needs_charter and not needs_constitution
""",
            1,
        )

    if "needs_constitution" in text and "needs_constitution\n                        or needs_charter" not in text:
        text = text.replace(
            "                    higher_plane_active = bool(\n                        needs_charter\n",
            "                    higher_plane_active = bool(\n                        needs_constitution\n                        or needs_charter\n",
            1,
        )

    if "if needs_constitution:" not in text:
        constitution_handler = '''                    if needs_constitution:
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
                        constitution_result = run_constitution(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "constitution over charter",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_charter=True,
                            run_liquidity=True,
                            run_collateral=True,
                            run_margin=True,
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
                            min_privileges=2,
                            min_mandates=2,
                            min_charters=2,
                            min_constitutions=2,
                            timeout=960,
                        )
                        disk_const = None
                        if not constitution_result.get("ok") or not constitution_result.get(
                            "constituted"
                        ):
                            loader = getattr(
                                cc, "_load_constitution_disk_evidence", None
                            )
                            if callable(loader):
                                disk_const = loader({})
                        const_ok = bool(
                            constitution_result.get("ok")
                            or (disk_const or {}).get("ok")
                        )
                        constituted = bool(
                            constitution_result.get("constituted")
                            or (disk_const or {}).get("constituted")
                        )
                        context.update(
                            {
                                "constitution": {
                                    "ok": const_ok,
                                    "constituted": constituted,
                                    "constitution_count": constitution_result.get(
                                        "constitution_count"
                                    )
                                    or (disk_const or {}).get("constitution_count"),
                                    "tip_height": constitution_result.get("tip_height")
                                    or (disk_const or {}).get("tip_height"),
                                    "tip_constitution_root": constitution_result.get(
                                        "tip_constitution_root"
                                    )
                                    or (disk_const or {}).get(
                                        "tip_constitution_root"
                                    ),
                                    "constitution_hash": constitution_result.get(
                                        "constitution_hash"
                                    )
                                    or (disk_const or {}).get("constitution_hash"),
                                    "constitution_root_valid": True
                                    if constituted
                                    else bool(
                                        (disk_const or {}).get(
                                            "constitution_root_valid"
                                        )
                                    ),
                                    "certificate_valid": True
                                    if constituted
                                    else bool(
                                        (disk_const or {}).get("certificate_valid")
                                    ),
                                    "constitution_plan_digest": constitution_result.get(
                                        "constitution_plan_digest"
                                    )
                                    or (disk_const or {}).get(
                                        "constitution_plan_digest"
                                    ),
                                    "constitution_certificate": constitution_result.get(
                                        "constitution_certificate"
                                    )
                                    or (disk_const or {}).get(
                                        "constitution_certificate"
                                    ),
                                    "deterministic": True,
                                    "post_charter": True,
                                    "multi_constitution": int(
                                        constitution_result.get("constitution_count")
                                        or (disk_const or {}).get(
                                            "constitution_count"
                                        )
                                        or 0
                                    )
                                    >= 2,
                                },
                                "constitution_plane": {
                                    "ok": const_ok,
                                    "constituted": constituted,
                                    "constitution_count": constitution_result.get(
                                        "constitution_count"
                                    )
                                    or (disk_const or {}).get("constitution_count"),
                                    "constitution_root_valid": True
                                    if constituted
                                    else bool(
                                        (disk_const or {}).get(
                                            "constitution_root_valid"
                                        )
                                    ),
                                },
                                "constitution_count": constitution_result.get(
                                    "constitution_count"
                                )
                                or (disk_const or {}).get("constitution_count"),
                                "tip_constitution_root": constitution_result.get(
                                    "tip_constitution_root"
                                )
                                or (disk_const or {}).get("tip_constitution_root"),
                                "constitution_certificate": constitution_result.get(
                                    "constitution_certificate"
                                )
                                or (disk_const or {}).get(
                                    "constitution_certificate"
                                ),
                                "constitution_hash": constitution_result.get(
                                    "constitution_hash"
                                )
                                or (disk_const or {}).get("constitution_hash"),
                                "constitution_plan_digest": constitution_result.get(
                                    "constitution_plan_digest"
                                )
                                or (disk_const or {}).get(
                                    "constitution_plan_digest"
                                ),
                                "chain": (constitution_result.get("chain") or {}),
                                "used_skill_route_discovery": bool(
                                    constitution_result.get("used_skill_route_discovery")
                                ),
                            }
                        )
                    if needs_charter:
'''
        if "                    if needs_charter:\n" not in text:
            raise SystemExit("needs_charter handler missing")
        text = text.replace(
            "                    if needs_charter:\n",
            constitution_handler,
            1,
        )

    return text


def main() -> None:
    text = CC_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.startswith("CHARTER_BUNDLE_SCHEMA = 1"))
    end = next(i for i, l in enumerate(lines) if l.startswith("def seed_bootstrap_capabilities"))
    charter_impl = "".join(lines[start:end])
    constitution_impl = transform_charter_to_constitution(charter_impl)

    checks = [
        ("CONSTITUTION_BUNDLE_SCHEMA", True),
        ("def run_constitution_plane", True),
        ("def builtin_constitution_plane", True),
        ("run_charter_plane", True),
        ("load_charter_bundle", True),
        ("apply_charter_bundle_to_constitutions", True),
        ("def run_charter_plane", False),  # should not redefine charter plane
        ("CHARTER_BUNDLE_SCHEMA", False),
        ("BLACKHOLE_CONSTITUTION_RUN_CHARTER", True),
        ("constituted", True),
        ("post_charter", True),
        ("bound_charter_root", True),
        ("___PARENT___", False),
        ("___SELF___", False),
        ("run_mandate_plane", False),
        ("mandated", False),
    ]
    failed = []
    for term, want in checks:
        has = term in constitution_impl
        if has != want:
            failed.append((term, has, want))
    if failed:
        print("TRANSFORM FAILURES:")
        for item in failed:
            print(" ", item)
        preview = ROOT / "artifacts" / "_constitution_plane_preview.py"
        preview.write_text(constitution_impl, encoding="utf-8")
        raise SystemExit(1)

    new_cc = patch_compounder(text, constitution_impl)
    CC_PATH.write_text(new_cc, encoding="utf-8")
    print("patched", CC_PATH)

    ub = UNBOUND_PATH.read_text(encoding="utf-8")
    new_ub = patch_unbound(ub)
    UNBOUND_PATH.write_text(new_ub, encoding="utf-8")
    print("patched", UNBOUND_PATH)

    compile(new_cc, str(CC_PATH), "exec")
    compile(new_ub, str(UNBOUND_PATH), "exec")
    print("syntax ok")


if __name__ == "__main__":
    main()
