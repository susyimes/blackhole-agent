"""Generate charter-plane over mandate from mandate-plane block and patch compounder+unbound."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CC_PATH = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND_PATH = ROOT / "src" / "blackhole_agent" / "unbound.py"


def transform_mandate_to_charter(src: str) -> str:
    """Transform mandate-plane (parent=privilege) into charter-plane (parent=mandate)."""
    s = src

    # Park parent (privilege) terms first so self renames do not collide.
    parent_pairs = [
        ("BLACKHOLE_MANDATE_RUN_PRIVILEGE", "BLACKHOLE___SELF___RUN___PARENT___"),
        ("BLACKHOLE_PRIVILEGE_", "BLACKHOLE___PARENT___"),
        ("apply_privilege_bundle_to_mandates", "apply___PARENT___bundle_to___SELF___s"),
        ("derive_mandate_specs_from_privilege", "derive___SELF___specs_from___PARENT___"),
        ("load_privilege_bundle", "load___PARENT___bundle"),
        ("write_privilege_bundle", "write___PARENT___bundle"),
        ("verify_privilege_bundle_integrity", "verify___PARENT___bundle_integrity"),
        ("verify_privilege_certificate", "verify___PARENT___certificate"),
        ("run_privilege_plane", "run___PARENT___plane"),
        ("builtin_privilege_plane", "builtin___PARENT___plane"),
        ("default_privilege_bundle_dir", "default___PARENT___bundle_dir"),
        ("privilege_bundle", "___PARENT___bundle"),
        ("privilege_report", "___PARENT___report"),
        ("privilege_path", "___PARENT___path"),
        ("privilege_plane", "___PARENT___plane"),
        ("privilege_certificate_hash", "___PARENT___certificate_hash"),
        ("privilege_certificate", "___PARENT___certificate"),
        ("privilege_plan_digest", "___PARENT___plan_digest"),
        ("privilege_hash", "___PARENT___hash"),
        ("privilege_count", "___PARENT___count"),
        ("tip_privilege_root", "tip___PARENT___root"),
        ("bound_privilege_root", "bound___PARENT___root"),
        ("bound_privilege_height", "bound___PARENT___height"),
        ("privilege_root", "___PARENT___root"),
        ("min_privileges", "min___PARENT___s"),
        ("want_privileges", "want___PARENT___s"),
        ("run_privilege", "run___PARENT___"),
        ("post_privilege", "post___PARENT___"),
        ("wrong_privilege", "wrong___PARENT___"),
        ("parent_privileged", "parent___PARENTED___"),
        ("privileged", "___PARENTED___"),
        ("Privileged", "___PARENTED_TITLE___"),
        ("PRIVILEGE", "___PARENT_UPPER___"),
        ("Privilege", "___PARENT_TITLE___"),
        ("privilege", "___PARENT___"),
    ]
    for a, b in parent_pairs:
        s = s.replace(a, b)

    # Self mandate -> charter (longest first).
    self_pairs = [
        ("BLACKHOLE_MANDATE_", "BLACKHOLE_CHARTER_"),
        ("BLACKHOLE___SELF___", "BLACKHOLE_CHARTER_"),
        ("capability.mandate-plane", "capability.charter-plane"),
        ("builtin_mandate_plane", "builtin_charter_plane"),
        ("run_mandate_plane", "run_charter_plane"),
        ("run_mandate_adversarial_checks", "run_charter_adversarial_checks"),
        ("replay_mandates_from_specs", "replay_charters_from_specs"),
        ("rehydrate_mandate_bundle", "rehydrate_charter_bundle"),
        ("verify_mandate_bundle_integrity", "verify_charter_bundle_integrity"),
        ("verify_mandate_certificate", "verify_charter_certificate"),
        ("verify_mandate_chain", "verify_charter_chain"),
        ("write_mandate_certificate", "write_charter_certificate"),
        ("write_mandate_bundle", "write_charter_bundle"),
        ("load_mandate_bundle", "load_charter_bundle"),
        ("_load_mandate_disk_evidence", "_load_charter_disk_evidence"),
        ("issue_mandate_certificate", "issue_charter_certificate"),
        ("compute_mandate_plan_digest", "compute_charter_plan_digest"),
        ("compute_mandate_bundle_hash", "compute_charter_bundle_hash"),
        ("compute_mandate_certificate_hash", "compute_charter_certificate_hash"),
        ("compute_mandate_root", "compute_charter_root"),
        ("apply_mandate_transition", "apply_charter_transition"),
        ("build_mandate_bundle", "build_charter_bundle"),
        ("empty_mandate_log", "empty_charter_log"),
        ("default_mandate_bundle_dir", "default_charter_bundle_dir"),
        ("DEFAULT_MANDATE_BUNDLE_RELATIVE", "DEFAULT_CHARTER_BUNDLE_RELATIVE"),
        ("MANDATE_BUNDLE_SCHEMA", "CHARTER_BUNDLE_SCHEMA"),
        ("MANDATE_CERTIFICATE_SCHEMA", "CHARTER_CERTIFICATE_SCHEMA"),
        ("MANDATE_LOG_SCHEMA", "CHARTER_LOG_SCHEMA"),
        ("mandate-bundles", "charter-bundles"),
        ("proof-mandate", "proof-charter"),
        ("mandate_plane", "charter_plane"),
        ("mandate_log", "charter_log"),
        ("mandate_bundle", "charter_bundle"),
        ("mandate_certificate", "charter_certificate"),
        ("mandate_plan_digest", "charter_plan_digest"),
        ("mandate_hash", "charter_hash"),
        ("mandate_count", "charter_count"),
        ("mandate_height", "charter_height"),
        ("tip_mandate_root", "tip_charter_root"),
        ("parent_mandate_root", "parent_charter_root"),
        ("parent_mandate_digest", "parent_charter_digest"),
        ("mandate_root", "charter_root"),
        ("min_mandates", "min_charters"),
        ("want_mandates", "want_charters"),
        ("mandate_path", "charter_path"),
        ("mandate_ok", "charter_ok"),
        ("single_mandate", "single_charter"),
        ("multi_mandate", "multi_charter"),
        ("mandates", "charters"),
        ("mandate over privilege", "charter over mandate"),
        ("Mandate plane", "Charter plane"),
        ("mandate plane", "charter plane"),
        ("Closed mandate", "Closed charter"),
        ("closed mandate", "closed charter"),
        ("MANDATE", "CHARTER"),
        ("Mandate", "Charter"),
        ("mandated", "chartered"),
        ("Mandated", "Chartered"),
        ("mandate", "charter"),
    ]
    for a, b in self_pairs:
        s = s.replace(a, b)

    # Restore parent -> mandate.
    parent_restore = [
        ("BLACKHOLE_CHARTER_RUN___PARENT___", "BLACKHOLE_CHARTER_RUN_MANDATE"),
        ("BLACKHOLE___PARENT___", "BLACKHOLE_MANDATE_"),
        ("apply___PARENT___bundle_to___SELF___s", "apply_mandate_bundle_to_charters"),
        ("apply___PARENT___bundle_to_charters", "apply_mandate_bundle_to_charters"),
        ("derive_charter_specs_from___PARENT___", "derive_charter_specs_from_mandate"),
        ("load___PARENT___bundle", "load_mandate_bundle"),
        ("write___PARENT___bundle", "write_mandate_bundle"),
        ("verify___PARENT___bundle_integrity", "verify_mandate_bundle_integrity"),
        ("verify___PARENT___certificate", "verify_mandate_certificate"),
        ("run___PARENT___plane", "run_mandate_plane"),
        ("builtin___PARENT___plane", "builtin_mandate_plane"),
        ("default___PARENT___bundle_dir", "default_mandate_bundle_dir"),
        ("___PARENT___bundle", "mandate_bundle"),
        ("___PARENT___report", "mandate_report"),
        ("___PARENT___path", "mandate_path"),
        ("___PARENT___plane", "mandate_plane"),
        ("___PARENT___certificate_hash", "mandate_certificate_hash"),
        ("___PARENT___certificate", "mandate_certificate"),
        ("___PARENT___plan_digest", "mandate_plan_digest"),
        ("___PARENT___hash", "mandate_hash"),
        ("___PARENT___count", "mandate_count"),
        ("tip___PARENT___root", "tip_mandate_root"),
        ("bound___PARENT___root", "bound_mandate_root"),
        ("bound___PARENT___height", "bound_mandate_height"),
        ("___PARENT___root", "mandate_root"),
        ("min___PARENT___s", "min_mandates"),
        ("want___PARENT___s", "want_mandates"),
        ("run___PARENT___", "run_mandate"),
        ("post___PARENT___", "post_mandate"),
        ("wrong___PARENT___", "wrong_mandate"),
        ("parent___PARENTED___", "parent_mandated"),
        ("___PARENTED___", "mandated"),
        ("___PARENTED_TITLE___", "Mandated"),
        ("___PARENT_UPPER___", "MANDATE"),
        ("___PARENT_TITLE___", "Mandate"),
        ("___PARENT___", "mandate"),
        ("___SELF___", "charter"),
    ]
    for a, b in parent_restore:
        s = s.replace(a, b)

    glitches = [
        ("apply_mandate_bundle_to_charterss", "apply_mandate_bundle_to_charters"),
        ("min_charterss", "min_charters"),
        ("want_charterss", "want_charters"),
        ("charterss", "charters"),
        ("charter for charter", "mandate for charter"),
        # run_mandate flag may have become run_mandates if min pattern leaked — fix common
        ("run_mandates=", "run_mandate="),
        ("run_mandates,", "run_mandate,"),
        ("run_mandates)", "run_mandate)"),
        ("run_mandates ", "run_mandate "),
    ]
    for a, b in glitches:
        s = s.replace(a, b)

    return s


def build_charter_capability_seed() -> str:
    return '''
Capability(
            id="capability.charter-plane",
            name="Charter plane over mandate",
            description=(
                "Closed charter plane: multi-mandate orders → deterministic "
                "hash-chained charter grants with charter plan digests bound to "
                "mandate roots → charter certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-mandate/double-charter/forged-root/"
                "gap/digest-tamper/single-charter falsification with genesis replay matching "
                "tip — past chartered actions without charter grants."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_charter_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_charter_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='charter over mandate'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
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
                "os.environ['BLACKHOLE_CHARTER_RUN_MANDATE']='1'; "
                "os.environ['BLACKHOLE_REORGANIZATION_RUN_RESOLUTION']='1'; "
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-charter.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-charter-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-charter-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-charter-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-charter-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-charter-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-charter-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-charter-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-charter-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-charter-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-charter-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-charter-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_SOLVENCY_BUNDLE_PATH', str(Path('artifacts')/'solvency-bundles'/'proof-charter-solvency.json')); "
                "os.environ.setdefault('BLACKHOLE_RISK_BUNDLE_PATH', str(Path('artifacts')/'risk-bundles'/'proof-charter-risk.json')); "
                "os.environ.setdefault('BLACKHOLE_STRESS_BUNDLE_PATH', str(Path('artifacts')/'stress-bundles'/'proof-charter-stress.json')); "
                "os.environ.setdefault('BLACKHOLE_RESILIENCE_BUNDLE_PATH', str(Path('artifacts')/'resilience-bundles'/'proof-charter-resilience.json')); "
                "os.environ.setdefault('BLACKHOLE_RECOVERY_BUNDLE_PATH', str(Path('artifacts')/'recovery-bundles'/'proof-charter-recovery.json')); "
                "os.environ.setdefault('BLACKHOLE_REINSTATEMENT_BUNDLE_PATH', str(Path('artifacts')/'reinstatement-bundles'/'proof-charter-reinstatement.json')); "
                "os.environ.setdefault('BLACKHOLE_REAUTHORIZATION_BUNDLE_PATH', str(Path('artifacts')/'reauthorization-bundles'/'proof-charter-reauthorization.json')); "
                "os.environ.setdefault('BLACKHOLE_RECERTIFICATION_BUNDLE_PATH', str(Path('artifacts')/'recertification-bundles'/'proof-charter-recertification.json')); "
                "os.environ.setdefault('BLACKHOLE_REATTESTATION_BUNDLE_PATH', str(Path('artifacts')/'reattestation-bundles'/'proof-charter-reattestation.json')); "
                "os.environ.setdefault('BLACKHOLE_REVALIDATION_BUNDLE_PATH', str(Path('artifacts')/'revalidation-bundles'/'proof-charter-revalidation.json')); "
                "os.environ.setdefault('BLACKHOLE_REVERIFICATION_BUNDLE_PATH', str(Path('artifacts')/'reverification-bundles'/'proof-charter-reverification.json')); "
                "os.environ.setdefault('BLACKHOLE_RECOGNITION_BUNDLE_PATH', str(Path('artifacts')/'recognition-bundles'/'proof-charter-recognition.json')); "
                "os.environ.setdefault('BLACKHOLE_PRIVILEGE_BUNDLE_PATH', str(Path('artifacts')/'privilege-bundles'/'proof-charter-privilege.json')); "
                "os.environ.setdefault('BLACKHOLE_MANDATE_BUNDLE_PATH', str(Path('artifacts')/'mandate-bundles'/'proof-charter-mandate.json')); "
                "os.environ.setdefault('BLACKHOLE_CHARTER_BUNDLE_PATH', str(Path('artifacts')/'charter-bundles'/'proof-charter.json')); "
                "r=builtin_charter_plane(); assert r['ok'] and r.get('action')=='charter_plane' "
                "and r.get('chartered') is True and int(r.get('charter_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('charter_certificate',{}).get('valid') "
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
                "Charter plane posts multi-mandate orders into deterministic hash-chained "
                "charter grants with charter plan digests bound to mandate roots, "
                "charter certificates, sterile rehydrate+prove, and adversarial falsification "
                "without skill-route discovery."
            ),
            tags=(
                "charter",
                "order",
                "mandate",
                "plane",
                "certificate",
                "adversarial",
                "hash-chain",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
'''


def patch_compounder(text: str, charter_impl: str) -> str:
    # Insert charter impl before seed_bootstrap_capabilities
    anchor = "def seed_bootstrap_capabilities"
    idx = text.find(anchor)
    if idx < 0:
        raise SystemExit("seed_bootstrap_capabilities not found")
    if "def run_charter_plane" not in text:
        text = text[:idx] + charter_impl.rstrip() + "\n\n\n" + text[idx:]
    else:
        print("charter impl already present; skipping insert")

    # Soft keyword map after mandate adequacy
    soft_block = '''    ("mandate adequacy", ("capability.mandate-plane", "capability.privilege-plane", "capability.assurance-plane")),
'''
    soft_insert = '''    ("mandate adequacy", ("capability.mandate-plane", "capability.privilege-plane", "capability.assurance-plane")),
    ("charter", ("capability.charter-plane", "capability.mandate-plane", "capability.privilege-plane")),
    ("chartered", ("capability.charter-plane", "capability.mandate-plane", "capability.finality-plane")),
    ("charter plan", ("capability.charter-plane", "capability.mandate-plane", "capability.assurance-plane")),
    ("charter-root", ("capability.charter-plane", "capability.mandate-plane", "capability.lineage-plane")),
    ("charter discharge", ("capability.charter-plane", "capability.mandate-plane", "capability.quorum-plane")),
    ("posted charter", ("capability.charter-plane", "capability.mandate-plane", "capability.actuation-plane")),
    ("charter adequacy", ("capability.charter-plane", "capability.mandate-plane", "capability.assurance-plane")),
'''
    if '("charter", ("capability.charter-plane"' not in text:
        if soft_block not in text:
            raise SystemExit("soft keyword anchor missing")
        text = text.replace(soft_block, soft_insert, 1)

    # Parse predicates after mandate_root_valid block
    parse_anchor = '''    if re.search(r"\\bmandate_root_valid\\b", lower) or (
        re.search(r"\\bmandate[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "mandate_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower)'''
    parse_insert = '''    if re.search(r"\\bmandate_root_valid\\b", lower) or (
        re.search(r"\\bmandate[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "mandate_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\bcharter_ok\\b", lower) or (
        re.search(r"\\brun_charter_plane\\b", lower) and (
            "charter" in lower or "plan" in lower
        )
    ):
        found.append({"kind": "charter_ok", "arg": "", "source": chunk})
    if re.search(r"\\bchartered_ok\\b", lower) or (
        "chartered" in lower
        and "charter" in lower
        and "charter-plane" not in lower
        and "charter_plane" not in lower
    ):
        found.append({"kind": "chartered_ok", "arg": "", "source": chunk})
    m = re.search(r"min_charters\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_charters", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?charters?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_charters" for item in found):
        found.append({"kind": "min_charters", "arg": m.group(1), "source": chunk})
    m = re.search(r"charter_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_charters" for item in found):
        found.append({"kind": "min_charters", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bcharter_root_valid\\b", lower) or (
        re.search(r"\\bcharter[_\\s-]*root\\b", lower)
        and "valid" in lower
    ):
        found.append({"kind": "charter_root_valid", "arg": "", "source": chunk})

    if re.search(r"\\brisked_ok\\b", lower)'''
    if '"charter_ok"' not in text.split("def snapshot_outcome_metrics")[0]:
        if parse_anchor not in text:
            raise SystemExit("parse predicate anchor missing")
        text = text.replace(parse_anchor, parse_insert, 1)

    # Evaluate predicates after mandate_root_valid return
    eval_anchor = '''        return ok, f"mandate_root_valid={ok}"


    if kind == "program_passes":'''
    eval_insert = '''        return ok, f"mandate_root_valid={ok}"

    if kind in {
        "charter_ok",
        "chartered_ok",
        "min_charters",
        "charter_root_valid",
    }:
        plane = (
            context.get("charter")
            or context.get("charter_plane")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_charter_disk_evidence(context)
            if disk:
                plane = disk
        if kind == "charter_ok":
            ok = bool(plane.get("ok") or plane.get("chartered"))
            return ok, f"charter_ok={ok}"
        if kind == "chartered_ok":
            ok = bool(
                plane.get("chartered")
                or plane.get("ok")
                or int(
                    plane.get("charter_count") or plane.get("tip_height") or 0
                )
                >= 2
            )
            return ok, f"chartered_ok={ok}"
        if kind == "min_charters":
            need = int(arg or 0)
            have = context.get("charter_count")
            if have is None:
                have = (
                    plane.get("charter_count")
                    or plane.get("tip_height")
                    or 0
                )
            try:
                have_i = int(have or 0)
            except (TypeError, ValueError):
                have_i = 0
                have = context.get("tip_charter_height")
            return have_i >= need, f"charters={have_i} need>={need}"
        if "charter_root_valid" in plane:
            ok = plane.get("charter_root_valid") is True
        else:
            cert = (
                plane.get("charter_certificate")
                or context.get("charter_certificate")
                or {}
            )
            if cert:
                verify = verify_charter_certificate(cert)
                ok = bool(verify.get("valid") or verify.get("ok"))
            else:
                ok = bool(
                    plane.get("charter_root") or plane.get("tip_charter_root")
                )
        return ok, f"charter_root_valid={ok}"


    if kind == "program_passes":'''
    if '"charter_ok",' not in text or "chartered_ok" not in text[text.find("if kind in {"):text.find("if kind == \"program_passes\"")]:
        # simpler check
        if 'kind == "charter_ok"' not in text:
            if eval_anchor not in text:
                raise SystemExit("eval predicate anchor missing")
            text = text.replace(eval_anchor, eval_insert, 1)

    # Seed capability registration after mandate Capability
    if 'id="capability.charter-plane"' not in text:
        # Find end of mandate Capability: after its updated_at and ),
        marker = 'id="capability.mandate-plane"'
        mpos = text.find(marker)
        if mpos < 0:
            raise SystemExit("mandate capability seed missing")
        # find the closing `        ),` then `    ]`
        close = text.find("\n        ),\n\n    ]", mpos)
        if close < 0:
            close = text.find("\n        ),\n    ]", mpos)
        if close < 0:
            raise SystemExit("mandate capability close not found")
        seed = build_charter_capability_seed()
        text = text[: close + len("\n        ),")] + "\n" + seed + text[close + len("\n        ),") :]

    return text


def patch_unbound(text: str) -> str:
    if "run_charter_plane" not in text.split("from blackhole_agent.capability_compounder import")[1][:3000]:
        text = text.replace(
            "    run_mandate_plane,\n    run_lineage_plane,",
            "    run_mandate_plane,\n    run_charter_plane,\n    run_lineage_plane,",
            1,
        )

    if "run_charter = (" not in text:
        text = text.replace(
            """    run_mandate = (
        cc.run_mandate_plane if cc is not None else run_mandate_plane
    )
""",
            """    run_mandate = (
        cc.run_mandate_plane if cc is not None else run_mandate_plane
    )
    run_charter = (
        cc.run_charter_plane if cc is not None else run_charter_plane
    )
""",
            1,
        )

    # needs_charter before needs_mandate; cascade not needs_charter
    if "needs_charter" not in text:
        old_needs = '''                    needs_mandate = bool(
                        kinds
                        & {
                            "mandate_ok",
                            "mandated_ok",
                            "min_mandates",
                            "mandate_root_valid",
                        }
                    )
                    needs_privilege = bool(
                        kinds
                        & {
                            "privilege_ok",
                            "privileged_ok",
                            "min_privileges",
                            "privilege_root_valid",
                        }
                    ) and not needs_mandate
                    needs_standing = bool(
                        kinds
                        & {
                            "standing_ok",
                            "stood_ok",
                            "min_standings",
                            "standing_root_valid",
                        }
                    ) and not needs_privilege and not needs_mandate
                    needs_reputation = bool(
                        kinds
                        & {
                            "reputation_ok",
                            "reputed_ok",
                            "min_reputations",
                            "reputation_root_valid",
                        }
                    ) and not needs_standing and not needs_privilege and not needs_mandate
                    needs_recognition = bool(
                        kinds
                        & {
                            "recognition_ok",
                            "recognized_ok",
                            "min_recognitions",
                            "recognition_root_valid",
                        }
                    ) and not needs_reputation and not needs_standing and not needs_privilege and not needs_mandate
                    needs_reaccreditation = bool(
                        kinds
                        & {
                            "reaccreditation_ok",
                            "reaccredited_ok",
                            "min_reaccreditations",
                            "reaccreditation_root_valid",
                        }
                    ) and not needs_recognition and not needs_reputation and not needs_standing and not needs_privilege and not needs_mandate
'''
        new_needs = '''                    needs_charter = bool(
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
                    needs_privilege = bool(
                        kinds
                        & {
                            "privilege_ok",
                            "privileged_ok",
                            "min_privileges",
                            "privilege_root_valid",
                        }
                    ) and not needs_mandate and not needs_charter
                    needs_standing = bool(
                        kinds
                        & {
                            "standing_ok",
                            "stood_ok",
                            "min_standings",
                            "standing_root_valid",
                        }
                    ) and not needs_privilege and not needs_mandate and not needs_charter
                    needs_reputation = bool(
                        kinds
                        & {
                            "reputation_ok",
                            "reputed_ok",
                            "min_reputations",
                            "reputation_root_valid",
                        }
                    ) and not needs_standing and not needs_privilege and not needs_mandate and not needs_charter
                    needs_recognition = bool(
                        kinds
                        & {
                            "recognition_ok",
                            "recognized_ok",
                            "min_recognitions",
                            "recognition_root_valid",
                        }
                    ) and not needs_reputation and not needs_standing and not needs_privilege and not needs_mandate and not needs_charter
                    needs_reaccreditation = bool(
                        kinds
                        & {
                            "reaccreditation_ok",
                            "reaccredited_ok",
                            "min_reaccreditations",
                            "reaccreditation_root_valid",
                        }
                    ) and not needs_recognition and not needs_reputation and not needs_standing and not needs_privilege and not needs_mandate and not needs_charter
'''
        if old_needs not in text:
            raise SystemExit("needs_mandate cascade anchor missing")
        text = text.replace(old_needs, new_needs, 1)

    # higher_plane_active
    if "needs_charter" in text and "needs_charter\n                        or needs_mandate" not in text:
        text = text.replace(
            "                    higher_plane_active = bool(\n                        needs_mandate\n",
            "                    higher_plane_active = bool(\n                        needs_charter\n                        or needs_mandate\n",
            1,
        )

    # Insert needs_charter handler before needs_mandate handler
    if "if needs_charter:" not in text:
        charter_handler = '''                    if needs_charter:
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
                        charter_result = run_charter(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "charter over mandate",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_mandate=True,
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
                            timeout=960,
                        )
                        disk_char = None
                        if not charter_result.get("ok") or not charter_result.get(
                            "chartered"
                        ):
                            loader = getattr(
                                cc, "_load_charter_disk_evidence", None
                            )
                            if callable(loader):
                                disk_char = loader({})
                        char_ok = bool(
                            charter_result.get("ok")
                            or (disk_char or {}).get("ok")
                        )
                        chartered = bool(
                            charter_result.get("chartered")
                            or (disk_char or {}).get("chartered")
                        )
                        context.update(
                            {
                                "charter": {
                                    "ok": char_ok,
                                    "chartered": chartered,
                                    "charter_count": charter_result.get(
                                        "charter_count"
                                    )
                                    or (disk_char or {}).get("charter_count"),
                                    "tip_height": charter_result.get("tip_height")
                                    or (disk_char or {}).get("tip_height"),
                                    "tip_charter_root": charter_result.get(
                                        "tip_charter_root"
                                    )
                                    or (disk_char or {}).get(
                                        "tip_charter_root"
                                    ),
                                    "charter_hash": charter_result.get(
                                        "charter_hash"
                                    )
                                    or (disk_char or {}).get("charter_hash"),
                                    "charter_root_valid": True
                                    if chartered
                                    else bool(
                                        (disk_char or {}).get(
                                            "charter_root_valid"
                                        )
                                    ),
                                    "certificate_valid": True
                                    if chartered
                                    else bool(
                                        (disk_char or {}).get("certificate_valid")
                                    ),
                                    "charter_plan_digest": charter_result.get(
                                        "charter_plan_digest"
                                    )
                                    or (disk_char or {}).get(
                                        "charter_plan_digest"
                                    ),
                                    "charter_certificate": charter_result.get(
                                        "charter_certificate"
                                    )
                                    or (disk_char or {}).get(
                                        "charter_certificate"
                                    ),
                                    "deterministic": True,
                                    "post_mandate": True,
                                    "multi_charter": int(
                                        charter_result.get("charter_count")
                                        or (disk_char or {}).get(
                                            "charter_count"
                                        )
                                        or 0
                                    )
                                    >= 2,
                                },
                                "charter_plane": {
                                    "ok": char_ok,
                                    "chartered": chartered,
                                    "charter_count": charter_result.get(
                                        "charter_count"
                                    )
                                    or (disk_char or {}).get("charter_count"),
                                    "charter_root_valid": True
                                    if chartered
                                    else bool(
                                        (disk_char or {}).get(
                                            "charter_root_valid"
                                        )
                                    ),
                                },
                                "charter_count": charter_result.get(
                                    "charter_count"
                                )
                                or (disk_char or {}).get("charter_count"),
                                "tip_charter_root": charter_result.get(
                                    "tip_charter_root"
                                )
                                or (disk_char or {}).get("tip_charter_root"),
                                "charter_certificate": charter_result.get(
                                    "charter_certificate"
                                )
                                or (disk_char or {}).get(
                                    "charter_certificate"
                                ),
                                "charter_hash": charter_result.get(
                                    "charter_hash"
                                )
                                or (disk_char or {}).get("charter_hash"),
                                "charter_plan_digest": charter_result.get(
                                    "charter_plan_digest"
                                )
                                or (disk_char or {}).get(
                                    "charter_plan_digest"
                                ),
                                "chain": (charter_result.get("chain") or {}),
                                "used_skill_route_discovery": bool(
                                    charter_result.get("used_skill_route_discovery")
                                ),
                            }
                        )
                    if needs_mandate:
'''
        if "                    if needs_mandate:\n" not in text:
            raise SystemExit("needs_mandate handler missing")
        text = text.replace(
            "                    if needs_mandate:\n",
            charter_handler,
            1,
        )

    return text


def main() -> None:
    text = CC_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.startswith("MANDATE_BUNDLE_SCHEMA = 1"))
    end = next(i for i, l in enumerate(lines) if l.startswith("def seed_bootstrap_capabilities"))
    mandate_impl = "".join(lines[start:end])
    charter_impl = transform_mandate_to_charter(mandate_impl)

    checks = [
        ("CHARTER_BUNDLE_SCHEMA", True),
        ("def run_charter_plane", True),
        ("def builtin_charter_plane", True),
        ("run_mandate_plane", True),
        ("load_mandate_bundle", True),
        ("apply_mandate_bundle_to_charters", True),
        ("def run_mandate_plane", False),
        ("MANDATE_BUNDLE_SCHEMA", False),
        ("BLACKHOLE_CHARTER_RUN_MANDATE", True),
        ("chartered", True),
        ("post_mandate", True),
        ("bound_mandate_root", True),
        ("___PARENT___", False),
        ("___SELF___", False),
        ("run_privilege_plane", False),
        ("privileged", False),
    ]
    failed = []
    for term, want in checks:
        has = term in charter_impl
        if has != want:
            failed.append((term, has, want))
    if failed:
        print("TRANSFORM FAILURES:")
        for item in failed:
            print(" ", item)
        preview = ROOT / "artifacts" / "_charter_plane_preview.py"
        preview.write_text(charter_impl, encoding="utf-8")
        raise SystemExit(1)

    new_cc = patch_compounder(text, charter_impl)
    CC_PATH.write_text(new_cc, encoding="utf-8")
    print("patched", CC_PATH)

    ub = UNBOUND_PATH.read_text(encoding="utf-8")
    new_ub = patch_unbound(ub)
    UNBOUND_PATH.write_text(new_ub, encoding="utf-8")
    print("patched", UNBOUND_PATH)

    # quick syntax check via compile
    compile(new_cc, str(CC_PATH), "exec")
    compile(new_ub, str(UNBOUND_PATH), "exec")
    print("syntax ok")


if __name__ == "__main__":
    main()
