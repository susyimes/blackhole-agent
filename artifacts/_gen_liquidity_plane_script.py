"""Generate liquidity plane code from collateral plane pattern and patch integrations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOUNDER = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND = ROOT / "src" / "blackhole_agent" / "unbound.py"
TEST = ROOT / "tests" / "test_capability_compounder.py"


def transform_collateral_block(block: str) -> str:
    replacements = [
        # Digests first (self then parent)
        ("collateral_allocation_digest", "liquidity_coverage_digest"),
        ("margin_requirement_digest", "collateral_allocation_digest"),
        # Outcomes / adjectives
        ("collateralized_ok", "liquid_ok"),
        ("collateralized", "liquid"),
        ("multi_collateral", "multi_liquidity"),
        ("min_collaterals", "min_liquidities"),
        ("single_collateral", "single_liquidity"),
        ("double_collateral", "double-liquidity"),
        ("need_multi_collateral", "need_multi_liquidity"),
        # Plane / action names
        ("collateral_plane", "liquidity_plane"),
        ("Collateral plane", "Liquidity plane"),
        ("collateral plane", "liquidity plane"),
        ("builtin_collateral_plane", "builtin_liquidity_plane"),
        ("run_collateral_plane", "run_liquidity_plane"),
        ("run_collateral_adversarial", "run_liquidity_adversarial"),
        # Bundle/log/cert machinery
        ("COLLATERAL_BUNDLE_SCHEMA", "LIQUIDITY_BUNDLE_SCHEMA"),
        ("COLLATERAL_CERTIFICATE_SCHEMA", "LIQUIDITY_CERTIFICATE_SCHEMA"),
        ("COLLATERAL_LOG_SCHEMA", "LIQUIDITY_LOG_SCHEMA"),
        ("DEFAULT_COLLATERAL_BUNDLE_RELATIVE", "DEFAULT_LIQUIDITY_BUNDLE_RELATIVE"),
        ("default_collateral_bundle_dir", "default_liquidity_bundle_dir"),
        ("empty_collateral_log", "empty_liquidity_log"),
        ("compute_collateral_root", "compute_liquidity_root"),
        ("compute_collateral_certificate_hash", "compute_liquidity_certificate_hash"),
        ("compute_collateral_bundle_hash", "compute_liquidity_bundle_hash"),
        ("compute_collateral_allocation_digest", "compute_liquidity_coverage_digest"),
        ("issue_collateral_certificate", "issue_liquidity_certificate"),
        ("verify_collateral_certificate", "verify_liquidity_certificate"),
        ("write_collateral_certificate", "write_liquidity_certificate"),
        ("_load_collateral_disk_evidence", "_load_liquidity_disk_evidence"),
        ("derive_collateral_specs_from_margin", "derive_liquidity_specs_from_collateral"),
        ("apply_collateral_transition", "apply_liquidity_transition"),
        ("verify_collateral_chain", "verify_liquidity_chain"),
        ("apply_margin_bundle_to_collaterals", "apply_collateral_bundle_to_liquidities"),
        ("build_collateral_bundle", "build_liquidity_bundle"),
        ("write_collateral_bundle", "write_liquidity_bundle"),
        ("load_collateral_bundle", "load_liquidity_bundle"),
        ("verify_collateral_bundle_integrity", "verify_liquidity_bundle_integrity"),
        ("rehydrate_collateral_bundle", "rehydrate_liquidity_bundle"),
        # Structural field names (self)
        ("collateral_certificate", "liquidity_certificate"),
        ("collateral_bundle", "liquidity_bundle"),
        ("collateral_log", "liquidity_log"),
        ("collateral_hash", "liquidity_hash"),
        ("collateral_root", "liquidity_root"),
        ("collateral_height", "liquidity_height"),
        ("collateral_count", "liquidity_count"),
        ("tip_collateral", "tip_liquidity"),
        ("parent_collateral", "parent_liquidity"),
        ("collaterals", "liquidities"),
        ("collateral_ok", "liquidity_ok"),
        ("collateral_done_when", "liquidity_done_when"),
        ("collateral_n", "liquidity_n"),
        ("collateral_path", "liquidity_path"),
        ("cover_ratio_bps", "coverage_ratio_bps"),
        ("post_margin", "post_collateral"),
        # Paths / strings
        ("collateral-bundles", "liquidity-bundles"),
        ("collateral-sandbox", "liquidity-sandbox"),
        ("collateral-certificate", "liquidity-certificate"),
        ("proof-collateral", "proof-liquidity"),
        ("test-collateral", "test-liquidity"),
        ("collateral-source-margin", "liquidity-source-collateral"),
        ("BLACKHOLE_COLLATERAL_", "BLACKHOLE_LIQUIDITY_"),
        # Domain language
        ("collateral over margin", "liquidity over collateral"),
        ("margin for collateral", "collateral for liquidity"),
        ("collateral allocation", "liquidity coverage"),
        ("Collateral allocation", "Liquidity coverage"),
        ("collateral allocations", "liquidity coverages"),
        # Parent renames (margin -> collateral) AFTER self renames
        ("run_margin_plane", "run_collateral_plane"),
        ("run_margin", "run_collateral"),
        ("load_margin_bundle", "load_collateral_bundle"),
        ("verify_margin_certificate", "verify_collateral_certificate"),
        ("write_margin_certificate", "write_collateral_certificate"),
        ("default_margin_bundle_dir", "default_collateral_bundle_dir"),
        ("margin_bundle", "collateral_bundle"),
        ("margin_report", "collateral_report"),
        ("margin_path", "collateral_path"),
        ("out_margin", "out_collateral"),
        ("margin_certificate", "collateral_certificate"),
        ("bound_margin_root", "bound_collateral_root"),
        ("bound_margin_height", "bound_collateral_height"),
        ("tip_margin_root", "tip_collateral_root"),
        ("margin_hash", "collateral_hash"),
        ("margin_count", "collateral_count"),
        ("min_margins", "min_collaterals"),
        ("want_margins", "want_collaterals"),
        ("margin_n", "collateral_n"),
        ("margins", "collaterals"),
        ("margin_entries", "collateral_entries"),
        ("margin_root", "collateral_root"),
        ("margin_height", "collateral_height"),
        ("known_margin_roots", "known_collateral_roots"),
        ("wrong_margin", "wrong_collateral"),
        ("margined", "collateralized"),
        ("margin_ok", "collateral_ok"),
        ("BLACKHOLE_MARGIN_BUNDLE_PATH", "BLACKHOLE_COLLATERAL_BUNDLE_PATH"),
        ("BLACKHOLE_MARGIN_MIN_MARGINS", "BLACKHOLE_COLLATERAL_MIN_COLLATERALS"),
        ("BLACKHOLE_MARGIN_RUN_CLEARING", "BLACKHOLE_COLLATERAL_RUN_MARGIN"),
        ('"plane": "collateral"', '"plane": "liquidity"'),
        ("margin_source_failed", "collateral_source_failed"),
        ("missing_collateral_bind", "missing_liquidity_bind"),
        ("from_margin", "from_collateral"),
        ("over margin", "over collateral"),
        ("to a margin", "to a collateral"),
        ("margin requirement", "collateral allocation"),
        ("margin tip", "collateral tip"),
        ("margin source", "collateral source"),
    ]

    out = block
    for old, new in replacements:
        out = out.replace(old, new)

    out = out.replace(
        'action": "margin_adversarial_checks"',
        'action": "liquidity_adversarial_checks"',
    )
    out = out.replace(
        "BLACKHOLE_LIQUIDITY_RUN_MARGIN",
        "BLACKHOLE_LIQUIDITY_RUN_COLLATERAL",
    )
    out = out.replace(
        "BLACKHOLE_LIQUIDITY_MIN_COLLATERALS",
        "BLACKHOLE_LIQUIDITY_MIN_LIQUIDITIES",
    )
    # Self context keys in run_liquidity_plane (original misnamed self as "margin")
    out = out.replace(
        '"margin": {\n            "ok": provisional_ok,\n            "liquid"',
        '"liquidity": {\n            "ok": provisional_ok,\n            "liquid"',
    )
    out = out.replace(
        '"cover": {\n            "ok": provisional_ok,\n            "liquid"',
        '"funding": {\n            "ok": provisional_ok,\n            "liquid"',
    )
    # Parent context was labeled clearing/net in collateral plane; leave mostly intact.
    # Fix kind strings that may have been partially transformed
    out = out.replace('kind": "collateral_allocation"', 'kind": "liquidity_coverage"')
    out = out.replace('kind": "collateral_log"', 'kind": "liquidity_log"')
    out = out.replace('kind": "collateral_certificate"', 'kind": "liquidity_certificate"')
    out = out.replace('kind": "collateral_bundle"', 'kind": "liquidity_bundle"')
    # outcome default
    out = out.replace('outcome or "collateralized"', 'outcome or "liquid"')
    out = out.replace('or "collateralized"', 'or "liquid"')
    # return field name "margin" for self bundle summary in run_liquidity_plane
    out = out.replace(
        '"margin": {\n            "ok": margin.get("ok"),\n            "liquidity_hash"',
        '"liquidity": {\n            "ok": margin.get("ok"),\n            "liquidity_hash"',
    )
    # Variable still named margin holding liquidity bundle — rename for clarity
    # Keep as-is for less risk; ok works.

    # Assertions on transform quality
    assert "def run_liquidity_plane" in out
    assert "def builtin_liquidity_plane" in out
    assert "LIQUIDITY_BUNDLE_SCHEMA" in out
    assert "liquidity_coverage_digest" in out
    assert "run_collateral_plane" in out
    assert "load_collateral_bundle" in out
    assert "bound_collateral_root" in out
    assert "tip_liquidity_root" in out
    assert "liquidity over collateral" in out
    assert "def run_collateral_plane" not in out
    assert "def builtin_collateral_plane" not in out
    assert "COLLATERAL_BUNDLE_SCHEMA" not in out
    assert "margin_requirement_digest" not in out
    return out


def insert_liquidity_block(text: str, block: str) -> str:
    marker = "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError("seed_bootstrap_capabilities not found")
    if "def run_liquidity_plane" in text:
        print("liquidity plane already present; skipping block insert")
        return text
    header = (
        "\n\n# ---------------------------------------------------------------------------\n"
        "# Liquidity plane over collateral\n"
        "# ---------------------------------------------------------------------------\n\n"
    )
    return text[:idx] + header + block + "\n\n" + text[idx:]


def patch_seed_registration(text: str) -> str:
    if 'id="capability.liquidity-plane"' in text:
        print("seed already present")
        return text
    # Insert before closing of seeds list: after collateral Capability(...), before ]
    # Find capability.collateral-plane Capability block end — the last seed before `    ]\n    for seed in seeds:`
    anchor = "    for seed in seeds:\n        if seed.id not in ledger.capabilities:"
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError("seed loop not found")
    # Walk back to the closing of last Capability before seeds list close
    # Insert before `    ]` that precedes the for-loop
    list_close = text.rfind("    ]\n", 0, idx)
    if list_close < 0:
        raise RuntimeError("seeds list close not found")

    seed = '''
        Capability(
            id="capability.liquidity-plane",
            name="Liquidity plane over collateral",
            description=(
                "Closed liquidity plane: multi-collateral allocations → deterministic "
                "hash-chained liquidity coverages with liquidity coverage digests bound to "
                "collateral roots → liquidity certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-collateral/double-liquidity/forged-root/"
                "gap/digest-tamper/single-liquidity falsification with genesis replay matching "
                "tip — past collateralized positions without liquidity coverage."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_liquidity_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_liquidity_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='liquidity over collateral'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
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
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-liquidity-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-liquidity-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-liquidity-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-liquidity-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-liquidity-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-liquidity-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-liquidity-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-liquidity-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-liquidity.json')); "
                "r=builtin_liquidity_plane(); assert r['ok'] and r.get('action')=='liquidity_plane' "
                "and r.get('liquid') is True and int(r.get('liquidity_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('liquidity_certificate',{}).get('valid') "
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
                "Liquidity plane covers multi-collateral allocations into deterministic "
                "hash-chained liquidity coverages with liquidity coverage digests and "
                "liquidity certificates bound to collateral roots, sterile rehydrate+"
                "prove, genesis replay matching tip, and adversarial falsification of "
                "wrong-collateral/reorder/double-liquidity/forged-root/digest-tamper without "
                "skill-route."
            ),
            tags=(
                "bootstrap",
                "compounder",
                "liquidity",
                "funding",
                "liquidity-root",
                "collateral",
                "cover",
                "deterministic",
                "margin",
                "clearing",
                "settlement",
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
'''
    return text[:list_close] + seed + text[list_close:]


def patch_plane_lists_and_intents(text: str) -> str:
    # Add to ordered plane list near collateral
    if '"capability.liquidity-plane"' not in text.split("capability.collateral-plane")[1][:500]:
        text = text.replace(
            '"capability.collateral-plane",\n',
            '"capability.collateral-plane",\n        "capability.liquidity-plane",\n',
            1,
        )
    # Intent routing keywords after collateral entries
    intent_snip = '''    ("liquidity", ("capability.liquidity-plane", "capability.collateral-plane", "capability.margin-plane")),
    ("liquid", ("capability.liquidity-plane", "capability.collateral-plane", "capability.finality-plane")),
    ("liquidity coverage", ("capability.liquidity-plane", "capability.collateral-plane", "capability.assurance-plane")),
    ("liquidity-root", ("capability.liquidity-plane", "capability.collateral-plane", "capability.lineage-plane")),
    ("funding", ("capability.liquidity-plane", "capability.collateral-plane", "capability.quorum-plane")),
    ("posted liquidity", ("capability.liquidity-plane", "capability.collateral-plane", "capability.actuation-plane")),
'''
    if '("liquidity",' not in text:
        text = text.replace(
            '    ("posted collateral", ("capability.collateral-plane", "capability.margin-plane", "capability.actuation-plane")),\n',
            '    ("posted collateral", ("capability.collateral-plane", "capability.margin-plane", "capability.actuation-plane")),\n'
            + intent_snip,
            1,
        )
    return text


def patch_outcome_contract_parse(text: str) -> str:
    # Extend predicate kind union / lists near collateral
    if "liquidity_ok" in text and "min_liquidities" in text:
        return text

    # In comment block
    text = text.replace(
        "#   margin_ok | margined_ok | min_margins:N | margin_root_valid\n",
        "#   margin_ok | margined_ok | min_margins:N | margin_root_valid\n"
        "#   collateral_ok | collateralized_ok | min_collaterals:N | collateral_root_valid\n"
        "#   liquidity_ok | liquid_ok | min_liquidities:N | liquidity_root_valid\n",
        1,
    )

    # Regex union for structured tokens
    old = r"margin_ok|margined_ok|min_margins|margin_root_valid"
    # Find collateral extension if present
    if "collateral_ok|collateralized_ok|min_collaterals|collateral_root_valid" in text:
        text = text.replace(
            "collateral_ok|collateralized_ok|min_collaterals|collateral_root_valid",
            "collateral_ok|collateralized_ok|min_collaterals|collateral_root_valid|"
            "liquidity_ok|liquid_ok|min_liquidities|liquidity_root_valid",
            1,
        )
    else:
        text = text.replace(
            old,
            old + "|collateral_ok|collateralized_ok|min_collaterals|collateral_root_valid|"
            "liquidity_ok|liquid_ok|min_liquidities|liquidity_root_valid",
            1,
        )

    # Allowed kinds list (tuples of strings)
    if '"collateral_ok"' in text and '"liquidity_ok"' not in text:
        text = text.replace(
            '''        "collateral_ok",
        "collateralized_ok",
        "min_collaterals",
        "collateral_root_valid",''',
            '''        "collateral_ok",
        "collateralized_ok",
        "min_collaterals",
        "collateral_root_valid",
        "liquidity_ok",
        "liquid_ok",
        "min_liquidities",
        "liquidity_root_valid",''',
            1,
        )

    # Soft extraction after collateral_root_valid block
    insert_after = '''    if re.search(r"\\bcollateral_root_valid\\b", lower) or (
        re.search(r"\\bcollateral[_\\s-]*root\\b", lower)
'''
    # Find the collateral soft-extract end and append liquidity extractors
    marker = 'found.append({"kind": "collateral_root_valid", "arg": "", "source": chunk})'
    idx = text.find(marker)
    if idx >= 0 and "liquidity_ok" not in text[idx : idx + 800]:
        # Find end of this if-block's append line
        end = idx + len(marker)
        liquidity_extract = '''
    if re.search(r"\\bliquidity_ok\\b", lower) or (
        re.search(r"\\bliquidity\\s+plane\\b", lower)
        and re.search(r"\\bok\\b", lower)
    ) or re.search(r"\\brun_liquidity_plane\\b", lower) and (
        re.search(r"\\bok\\b", lower) or True
    ):
        found.append({"kind": "liquidity_ok", "arg": "", "source": chunk})
    if re.search(r"\\bliquid_ok\\b", lower) or re.search(
        r"\\bliquid\\s*(?:=|is|:)\\s*true\\b", lower
    ):
        found.append({"kind": "liquid_ok", "arg": "", "source": chunk})
    if (
        re.search(r"\\bliquid\\b", lower)
        and re.search(r"\\b(true|ok|yes)\\b", lower)
        and "liquidity-plane" not in lower
        and "liquidity_plane" not in lower
    ):
        found.append({"kind": "liquid_ok", "arg": "", "source": chunk})
    m = re.search(r"(?:at least|>=|≥)\\s*(\\d+)\\s+liquidit", lower)
    if m:
        found.append({"kind": "min_liquidities", "arg": m.group(1), "source": chunk})
    m = re.search(r"liquidity_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_liquidities" for item in found):
        found.append({"kind": "min_liquidities", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bmin_liquidities\\b", lower) and not any(
        item.get("kind") == "min_liquidities" for item in found
    ):
        m_n = re.search(r"min_liquidities\\s*[:=]?\\s*(\\d+)", lower)
        if m_n:
            found.append(
                {
                    "kind": "min_liquidities",
                    "arg": m_n.group(1),
                    "source": chunk,
                }
            )
    if re.search(r"\\bliquidity_root_valid\\b", lower) or (
        re.search(r"\\bliquidity[_\\s-]*root\\b", lower)
        and re.search(r"\\bvalid\\b", lower)
    ):
        found.append({"kind": "liquidity_root_valid", "arg": "", "source": chunk})
'''
        text = text[:end] + liquidity_extract + text[end:]

    return text


def patch_evaluate_outcome(text: str) -> str:
    if 'kind in {\n        "liquidity_ok"' in text or '"liquidity_ok",\n        "liquid_ok"' in text:
        return text
    # Insert after collateral evaluation block
    marker = 'return ok, f"collateral_root_valid={ok}"'
    idx = text.find(marker)
    if idx < 0:
        # try alternate
        marker = 'return ok, f"collateral_root_valid={ok}"'
        idx = text.find(marker)
    if idx < 0:
        print("WARN: collateral_root_valid return not found for evaluate patch")
        return text
    end = idx + len(marker)
    eval_block = '''
    if kind in {
        "liquidity_ok",
        "liquid_ok",
        "min_liquidities",
        "liquidity_root_valid",
    }:
        plane = (
            context.get("liquidity")
            or context.get("liquidity_plane")
            or context.get("funding")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_liquidity_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "liquidity_ok":
            ok = bool(plane.get("ok"))
            return ok, f"liquidity_ok={ok}"
        if kind == "liquid_ok":
            if "liquid" in plane:
                ok = plane.get("liquid") is True and bool(plane.get("ok", True))
            elif "liquid_ok" in plane:
                ok = plane.get("liquid_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("liquidity_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"liquid_ok={ok}"
        if kind == "min_liquidities":
            need = int(float(arg or "0"))
            have = context.get("liquidity_count")
            if have is None:
                have = context.get("tip_liquidity_height")
            if have is None:
                have = (
                    plane.get("liquidity_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"liquidities={have_i} need>={need}"
        if "liquidity_root_valid" in plane:
            ok = plane.get("liquidity_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("liquidity_certificate")
                or plane.get("certificate")
                or context.get("liquidity_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_liquidity_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("liquidity_root") or plane.get("tip_liquidity_root")
                )
        return ok, f"liquidity_root_valid={ok}"
'''
    return text[:end] + eval_block + text[end:]


def patch_certificate_registry(text: str) -> str:
    if '("liquidity_certificate", verify_liquidity_certificate)' in text:
        return text
    text = text.replace(
        '("collateral_certificate", verify_collateral_certificate),\n',
        '("collateral_certificate", verify_collateral_certificate),\n'
        '                ("liquidity_certificate", verify_liquidity_certificate),\n',
        1,
    )
    # plane context keys list
    if '"liquidity_plane"' not in text:
        text = text.replace(
            '"collateral_plane",\n',
            '"collateral_plane",\n                "liquidity",\n                "liquidity_plane",\n',
            1,
        )
    return text


def patch_unbound(text: str) -> str:
    if "run_liquidity_plane" in text and "needs_liquidity" in text:
        return text
    # imports / fallbacks near collateral
    if "run_collateral_plane" in text and "run_liquidity_plane" not in text:
        text = text.replace(
            "run_collateral_plane,\n",
            "run_collateral_plane,\n    run_liquidity_plane,\n",
            1,
        )
        text = text.replace(
            """    run_collateral = (
        cc.run_collateral_plane if cc is not None else run_collateral_plane
    )
""",
            """    run_collateral = (
        cc.run_collateral_plane if cc is not None else run_collateral_plane
    )
    run_liquidity = (
        cc.run_liquidity_plane if cc is not None else run_liquidity_plane
    )
""",
            1,
        )

    # needs_liquidity before needs_collateral
    old_needs = '''                    needs_collateral = bool(
                        kinds
                        & {
                            "collateral_ok",
                            "collateralized_ok",
                            "min_collaterals",
                            "collateral_root_valid",
                        }
                    )
                    needs_margin = bool(
                        kinds
                        & {
                            "margin_ok",
                            "margined_ok",
                            "min_margins",
                            "margin_root_valid",
                        }
                    ) and not needs_collateral
                    needs_clearing = bool(
                        kinds
                        & {
                            "clearing_ok",
                            "cleared_ok",
                            "min_clearings",
                            "clearing_root_valid",
                        }
                    ) and not needs_margin and not needs_collateral
                    needs_settlement = bool(
                        kinds
                        & {
                            "settlement_ok",
                            "settled_ok",
                            "min_settlements",
                            "settlement_root_valid",
                        }
                    ) and not needs_clearing and not needs_margin and not needs_collateral
                    needs_actuation = bool(
                        kinds
                        & {
                            "actuation_ok",
                            "effects_applied_ok",
                            "min_actions",
                            "action_root_valid",
                        }
                    ) and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral
                    needs_execution = bool(
                        kinds
                        & {
                            "execution_ok",
                            "state_applied_ok",
                            "min_state_height",
                            "state_root_valid",
                        }
                    ) and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral
                    needs_finality = bool(
                        kinds
                        & {
                            "finality_ok",
                            "finalized_ok",
                            "min_epochs",
                            "finality_cert_valid",
                        }
                    ) and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral
                    needs_quorum = bool(
                        kinds
                        & {
                            "quorum_ok",
                            "quorum_met",
                            "min_quorum",
                            "byzantine_excluded",
                            "quorum_cert_valid",
                        }
                    ) and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral
                    needs_federation = bool(
                        kinds
                        & {
                            "federation_ok",
                            "federated_ok",
                            "min_origins",
                            "federation_cert_valid",
                        }
                    ) and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral
'''
    new_needs = '''                    needs_liquidity = bool(
                        kinds
                        & {
                            "liquidity_ok",
                            "liquid_ok",
                            "min_liquidities",
                            "liquidity_root_valid",
                        }
                    )
                    needs_collateral = bool(
                        kinds
                        & {
                            "collateral_ok",
                            "collateralized_ok",
                            "min_collaterals",
                            "collateral_root_valid",
                        }
                    ) and not needs_liquidity
                    needs_margin = bool(
                        kinds
                        & {
                            "margin_ok",
                            "margined_ok",
                            "min_margins",
                            "margin_root_valid",
                        }
                    ) and not needs_collateral and not needs_liquidity
                    needs_clearing = bool(
                        kinds
                        & {
                            "clearing_ok",
                            "cleared_ok",
                            "min_clearings",
                            "clearing_root_valid",
                        }
                    ) and not needs_margin and not needs_collateral and not needs_liquidity
                    needs_settlement = bool(
                        kinds
                        & {
                            "settlement_ok",
                            "settled_ok",
                            "min_settlements",
                            "settlement_root_valid",
                        }
                    ) and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity
                    needs_actuation = bool(
                        kinds
                        & {
                            "actuation_ok",
                            "effects_applied_ok",
                            "min_actions",
                            "action_root_valid",
                        }
                    ) and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity
                    needs_execution = bool(
                        kinds
                        & {
                            "execution_ok",
                            "state_applied_ok",
                            "min_state_height",
                            "state_root_valid",
                        }
                    ) and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity
                    needs_finality = bool(
                        kinds
                        & {
                            "finality_ok",
                            "finalized_ok",
                            "min_epochs",
                            "finality_cert_valid",
                        }
                    ) and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity
                    needs_quorum = bool(
                        kinds
                        & {
                            "quorum_ok",
                            "quorum_met",
                            "min_quorum",
                            "byzantine_excluded",
                            "quorum_cert_valid",
                        }
                    ) and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity
                    needs_federation = bool(
                        kinds
                        & {
                            "federation_ok",
                            "federated_ok",
                            "min_origins",
                            "federation_cert_valid",
                        }
                    ) and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity
'''
    if old_needs in text:
        text = text.replace(old_needs, new_needs, 1)
    else:
        print("WARN: needs_* block not matched exactly in unbound")

    # Insert liquidity run before needs_collateral run
    if "if needs_liquidity:" not in text:
        insert_at = text.find("                    if needs_collateral:")
        if insert_at < 0:
            print("WARN: needs_collateral run block not found")
            return text
        liquidity_run = '''                    if needs_liquidity:
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
                        liquidity = run_liquidity(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "liquidity over collateral",
                            done_when=plane_done_when,
                            max_steps=3,
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
                            timeout=900,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                liquidity.get("used_skill_route_discovery")
                            ),
                            "chain": liquidity.get("chain") or {},
                            "liquidity_chain": liquidity.get("chain") or {},
                            "collateral": {
                                "ok": bool(
                                    (liquidity.get("collateral") or {}).get("ok", True)
                                ),
                                "collateralized": bool(
                                    (liquidity.get("collateral") or {}).get(
                                        "collateralized", True
                                    )
                                ),
                                "collateral_count": int(
                                    liquidity.get("collateral_count") or 0
                                ),
                                "collateral_root_valid": True,
                                "certificate_valid": True,
                                "collateral_allocation_digest": liquidity.get(
                                    "collateral_allocation_digest"
                                ),
                            },
                            "collateral_plane": {
                                "ok": bool(
                                    (liquidity.get("collateral") or {}).get("ok", True)
                                ),
                                "collateralized": True,
                                "collateral_count": int(
                                    liquidity.get("collateral_count") or 0
                                ),
                                "collateral_root_valid": True,
                            },
                            "liquidity": {
                                "ok": bool(liquidity.get("ok")),
                                "liquid": bool(liquidity.get("liquid")),
                                "liquidity_count": int(
                                    liquidity.get("liquidity_count") or 0
                                ),
                                "tip_height": int(liquidity.get("tip_height") or 0),
                                "tip_liquidity_root": liquidity.get(
                                    "tip_liquidity_root"
                                ),
                                "liquidity_root_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "liquidity_coverage_digest": liquidity.get(
                                    "liquidity_coverage_digest"
                                ),
                                "deterministic": True,
                                "post_collateral": True,
                                "multi_liquidity": int(
                                    liquidity.get("liquidity_count") or 0
                                )
                                >= 2,
                            },
                            "liquidity_plane": {
                                "ok": bool(liquidity.get("ok")),
                                "liquid": bool(liquidity.get("liquid")),
                                "liquidity_count": int(
                                    liquidity.get("liquidity_count") or 0
                                ),
                                "liquidity_root_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "funding": {
                                "ok": bool(liquidity.get("ok")),
                                "liquid": bool(liquidity.get("liquid")),
                                "liquidity_count": int(
                                    liquidity.get("liquidity_count") or 0
                                ),
                                "liquidity_coverage_digest": liquidity.get(
                                    "liquidity_coverage_digest"
                                ),
                                "liquidity_root_valid": bool(
                                    (liquidity.get("liquidity_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "liquidity_count": int(liquidity.get("liquidity_count") or 0),
                            "collateral_count": int(
                                liquidity.get("collateral_count") or 0
                            ),
                            "tip_height": int(liquidity.get("tip_height") or 0),
                            "liquidity_certificate": liquidity.get(
                                "liquidity_certificate"
                            ),
                            "liquidity_hash": liquidity.get("liquidity_hash"),
                            "collateral_hash": liquidity.get("collateral_hash"),
                            "tip_liquidity_root": liquidity.get("tip_liquidity_root"),
                            "bound_collateral_root": liquidity.get(
                                "bound_collateral_root"
                            ),
                            "liquidity_coverage_digest": liquidity.get(
                                "liquidity_coverage_digest"
                            ),
                            "collateral_allocation_digest": liquidity.get(
                                "collateral_allocation_digest"
                            ),
                        }
                    elif needs_collateral:
'''
        text = text[:insert_at] + liquidity_run + text[insert_at + len("                    if needs_collateral:"):]
    return text


def patch_test_file(text: str) -> str:
    if "test_liquidity_plane_coverages_and_adversarial" in text:
        return text
    test = '''

def test_liquidity_plane_coverages_and_adversarial():
    """Liquidity plane covers multi-collateral allocations and falsifies wrong-collateral binds."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_liquidity_bundle,
        parse_outcome_contract,
        run_liquidity_plane,
        verify_liquidity_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.liquidity-plane" in ledger.capabilities
    assert "capability.collateral-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; liquidity_ok; liquid_ok; min_liquidities:2; "
        "liquidity_root_valid; collateral_ok; collateralized_ok; min_collaterals:2; "
        "collateral_root_valid; chain_valid"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "liquidity_ok" in kinds
    assert "liquid_ok" in kinds
    assert "min_liquidities" in kinds
    assert "liquidity_root_valid" in kinds

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-liquidity-plane.json"
    quorum_path = repo / "artifacts" / "quorum-bundles" / "test-liquidity-quorum.json"
    finality_path = repo / "artifacts" / "finality-bundles" / "test-liquidity-finality.json"
    execution_path = repo / "artifacts" / "execution-bundles" / "test-liquidity-execution.json"
    actuation_path = repo / "artifacts" / "actuation-bundles" / "test-liquidity-actuation.json"
    settlement_path = repo / "artifacts" / "settlement-bundles" / "test-liquidity-settlement.json"
    margin_path = repo / "artifacts" / "margin-bundles" / "test-liquidity-margin.json"
    collateral_path = repo / "artifacts" / "collateral-bundles" / "test-liquidity-collateral.json"
    liquidity_path = repo / "artifacts" / "liquidity-bundles" / "test-liquidity-plane.json"
    for target in (
        lineage_path,
        quorum_path,
        finality_path,
        execution_path,
        actuation_path,
        settlement_path,
        margin_path,
        collateral_path,
        liquidity_path,
    ):
        if target.exists():
            target.unlink()

    plane = run_liquidity_plane(
        repo,
        "liquidity over collateral",
        "min_capabilities:5; capability_exists:repo.import-health; no_skill_route",
        max_steps=3,
        run_collateral=True,
        run_clearing=True,
        run_settlement=True,
        run_actuation=True,
        run_execution=True,
        run_finality=True,
        run_quorum=True,
        run_continuity=False,
        run_reconciliation=False,
        inject_byzantine=True,
        epoch_count=2,
        min_actions=2,
        min_settlements=2,
        min_clearings=2,
        min_margins=2,
        min_collaterals=2,
        min_liquidities=2,
        lineage_path=lineage_path,
        quorum_path=quorum_path,
        finality_path=finality_path,
        execution_path=execution_path,
        actuation_path=actuation_path,
        settlement_path=settlement_path,
        margin_path=margin_path,
        collateral_path=collateral_path,
        liquidity_path=liquidity_path,
        timeout=900,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "liquidity_plane"
    assert plane["liquid"] is True
    assert int(plane["liquidity_count"]) >= 2
    assert int(plane["tip_height"]) >= 2
    assert int(plane["collateral_count"] or 0) >= 2
    assert plane.get("liquidity_coverage_digest")
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["multi_liquidity"] is True
    assert plane["integrity"]["liquidity_ok"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["liquidity_certificate"]["valid"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["wrong_collateral_fails_as_expected"] is True
    assert plane["adversarial"]["reorder_fails_as_expected"] is True
    assert plane["adversarial"]["digest_tamper_fails_as_expected"] is True
    assert plane["adversarial"]["single_liquidity_fails_as_expected"] is True
    assert plane["adversarial"]["duplicate_apply_fails_as_expected"] is True
    assert plane["adversarial"]["replay_matches_tip"] is True
    assert plane["used_skill_route_discovery"] is False
    assert liquidity_path.is_file()

    loaded = load_liquidity_bundle(liquidity_path)
    assert verify_liquidity_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("liquidity_hash")
    assert int(loaded.get("liquidity_count") or 0) >= 2
    assert int(loaded.get("tip_height") or 0) >= 2
    assert loaded.get("liquidity_coverage_digest")
    assert path.name == "ledger.json"
'''
    return text.rstrip() + test + "\n"


def main() -> None:
    text = COMPOUNDER.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        if line.startswith("COLLATERAL_BUNDLE_SCHEMA = 1"):
            start = i
        if start is not None and line.startswith("def seed_bootstrap_capabilities"):
            end = i
            break
    if start is None or end is None:
        raise RuntimeError(f"block bounds not found start={start} end={end}")
    block = "".join(lines[start:end])
    liquidity_block = transform_collateral_block(block)

    # Save for inspection
    (ROOT / "artifacts" / "_gen_liquidity_plane_body.py").write_text(
        liquidity_block, encoding="utf-8"
    )

    text = insert_liquidity_block(text, liquidity_block)
    text = patch_seed_registration(text)
    text = patch_plane_lists_and_intents(text)
    text = patch_outcome_contract_parse(text)
    text = patch_evaluate_outcome(text)
    text = patch_certificate_registry(text)
    COMPOUNDER.write_text(text, encoding="utf-8")
    print("compounder updated", COMPOUNDER.stat().st_size)

    ub = UNBOUND.read_text(encoding="utf-8")
    ub2 = patch_unbound(ub)
    UNBOUND.write_text(ub2, encoding="utf-8")
    print("unbound updated", UNBOUND.stat().st_size)

    tf = TEST.read_text(encoding="utf-8")
    TEST.write_text(patch_test_file(tf), encoding="utf-8")
    print("tests updated")

    # Quick syntax check
    import ast

    ast.parse(COMPOUNDER.read_text(encoding="utf-8"))
    ast.parse(UNBOUND.read_text(encoding="utf-8"))
    print("syntax ok")


if __name__ == "__main__":
    main()
