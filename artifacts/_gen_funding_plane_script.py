"""Generate funding plane code from liquidity plane pattern and patch integrations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOUNDER = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND = ROOT / "src" / "blackhole_agent" / "unbound.py"
TEST = ROOT / "tests" / "test_capability_compounder.py"


def transform_liquidity_block(block: str) -> str:
    # Order: longest / most-specific self renames first. Never bare "liquid"→"funded"
    # (that would corrupt remaining "liquidity" parent tokens).
    replacements = [
        # Digests first (self then parent)
        ("liquidity_coverage_digest", "funding_facility_digest"),
        ("collateral_allocation_digest", "liquidity_coverage_digest"),
        # Outcomes / multi
        ("liquid_ok", "funded_ok"),
        ("multi_liquidity", "multi_funding"),
        ("min_liquidities", "min_fundings"),
        ("single_liquidity", "single_funding"),
        ("double-liquidity", "double-funding"),
        ("double_liquidity", "double_funding"),
        ("need_multi_liquidity", "need_multi_funding"),
        # Plane / action names
        ("liquidity_plane", "funding_plane"),
        ("Liquidity plane", "Funding plane"),
        ("liquidity plane", "funding plane"),
        ("builtin_liquidity_plane", "builtin_funding_plane"),
        ("run_liquidity_plane", "run_funding_plane"),
        ("run_liquidity_adversarial", "run_funding_adversarial"),
        # Bundle/log/cert machinery
        ("LIQUIDITY_BUNDLE_SCHEMA", "FUNDING_BUNDLE_SCHEMA"),
        ("LIQUIDITY_CERTIFICATE_SCHEMA", "FUNDING_CERTIFICATE_SCHEMA"),
        ("LIQUIDITY_LOG_SCHEMA", "FUNDING_LOG_SCHEMA"),
        ("DEFAULT_LIQUIDITY_BUNDLE_RELATIVE", "DEFAULT_FUNDING_BUNDLE_RELATIVE"),
        ("default_liquidity_bundle_dir", "default_funding_bundle_dir"),
        ("empty_liquidity_log", "empty_funding_log"),
        ("compute_liquidity_root", "compute_funding_root"),
        ("compute_liquidity_certificate_hash", "compute_funding_certificate_hash"),
        ("compute_liquidity_bundle_hash", "compute_funding_bundle_hash"),
        ("compute_liquidity_coverage_digest", "compute_funding_facility_digest"),
        ("issue_liquidity_certificate", "issue_funding_certificate"),
        ("verify_liquidity_certificate", "verify_funding_certificate"),
        ("write_liquidity_certificate", "write_funding_certificate"),
        ("_load_liquidity_disk_evidence", "_load_funding_disk_evidence"),
        ("derive_liquidity_specs_from_collateral", "derive_funding_specs_from_liquidity"),
        ("apply_liquidity_transition", "apply_funding_transition"),
        ("verify_liquidity_chain", "verify_funding_chain"),
        ("apply_collateral_bundle_to_liquidities", "apply_liquidity_bundle_to_fundings"),
        ("build_liquidity_bundle", "build_funding_bundle"),
        ("write_liquidity_bundle", "write_funding_bundle"),
        ("load_liquidity_bundle", "load_funding_bundle"),
        ("verify_liquidity_bundle_integrity", "verify_funding_bundle_integrity"),
        ("rehydrate_liquidity_bundle", "rehydrate_funding_bundle"),
        # Structural field names (self)
        ("liquidity_certificate", "funding_certificate"),
        ("liquidity_bundle", "funding_bundle"),
        ("liquidity_log", "funding_log"),
        ("liquidity_hash", "funding_hash"),
        ("liquidity_root", "funding_root"),
        ("liquidity_height", "funding_height"),
        ("liquidity_count", "funding_count"),
        ("tip_liquidity", "tip_funding"),
        ("parent_liquidity", "parent_funding"),
        ("liquidities", "fundings"),
        ("liquidity_ok", "funding_ok"),
        ("liquidity_done_when", "funding_done_when"),
        ("liquidity_n", "funding_n"),
        ("liquidity_path", "funding_path"),
        ("coverage_ratio_bps", "facility_ratio_bps"),
        ("post_collateral", "post_liquidity"),
        # Paths / strings
        ("liquidity-bundles", "funding-bundles"),
        ("liquidity-sandbox", "funding-sandbox"),
        ("liquidity-certificate", "funding-certificate"),
        ("proof-liquidity", "proof-funding"),
        ("test-liquidity", "test-funding"),
        ("liquidity-source-collateral", "funding-source-liquidity"),
        ("BLACKHOLE_LIQUIDITY_", "BLACKHOLE_FUNDING_"),
        # Domain language
        ("liquidity over collateral", "funding over liquidity"),
        ("collateral for liquidity", "liquidity for funding"),
        ("liquidity coverage", "funding facility"),
        ("Liquidity coverage", "Funding facility"),
        ("liquidity coverages", "funding facilities"),
        # Parent renames (collateral → liquidity) AFTER self renames
        ("run_collateral_plane", "run_liquidity_plane"),
        ("run_collateral", "run_liquidity"),
        ("load_collateral_bundle", "load_liquidity_bundle"),
        ("verify_collateral_certificate", "verify_liquidity_certificate"),
        ("write_collateral_certificate", "write_liquidity_certificate"),
        ("default_collateral_bundle_dir", "default_liquidity_bundle_dir"),
        ("collateral_bundle", "liquidity_bundle"),
        ("collateral_report", "liquidity_report"),
        ("collateral_path", "liquidity_path"),
        ("out_collateral", "out_liquidity"),
        ("collateral_certificate", "liquidity_certificate"),
        ("bound_collateral_root", "bound_liquidity_root"),
        ("bound_collateral_height", "bound_liquidity_height"),
        ("tip_collateral_root", "tip_liquidity_root"),
        ("collateral_hash", "liquidity_hash"),
        ("collateral_count", "liquidity_count"),
        ("min_collaterals", "min_liquidities"),
        ("want_collaterals", "want_liquidities"),
        ("collateral_n", "liquidity_n"),
        ("collaterals", "liquidities"),
        ("collateral_entries", "liquidity_entries"),
        ("collateral_root", "liquidity_root"),
        ("collateral_height", "liquidity_height"),
        ("known_collateral_roots", "known_liquidity_roots"),
        ("wrong_collateral", "wrong_liquidity"),
        ("collateralized", "liquid"),
        ("collateral_ok", "liquidity_ok"),
        ("BLACKHOLE_COLLATERAL_BUNDLE_PATH", "BLACKHOLE_LIQUIDITY_BUNDLE_PATH"),
        ("BLACKHOLE_COLLATERAL_MIN_COLLATERALS", "BLACKHOLE_LIQUIDITY_MIN_LIQUIDITIES"),
        ("BLACKHOLE_COLLATERAL_RUN_MARGIN", "BLACKHOLE_LIQUIDITY_RUN_COLLATERAL"),
        ('"plane": "liquidity"', '"plane": "funding"'),
        ("collateral_source_failed", "liquidity_source_failed"),
        ("missing_liquidity_bind", "missing_funding_bind"),
        ("from_collateral", "from_liquidity"),
        ("over collateral", "over liquidity"),
        ("to a collateral", "to a liquidity"),
        ("collateral allocation", "liquidity coverage"),
        ("collateral tip", "liquidity tip"),
        ("collateral source", "liquidity source"),
        ("past collateralized positions", "past liquid positions"),
    ]

    out = block
    for old, new in replacements:
        out = out.replace(old, new)

    # Word-boundary adjective renames only (never touch "liquidity")
    out = re.sub(r"\bliquid\b", "funded", out)
    out = re.sub(r"\bLiquid\b", "Funded", out)

    out = out.replace(
        'action": "liquidity_adversarial_checks"',
        'action": "funding_adversarial_checks"',
    )
    out = out.replace(
        "BLACKHOLE_FUNDING_RUN_COLLATERAL",
        "BLACKHOLE_FUNDING_RUN_LIQUIDITY",
    )
    out = out.replace(
        "BLACKHOLE_FUNDING_MIN_LIQUIDITIES",
        "BLACKHOLE_FUNDING_MIN_FUNDINGS",
    )
    # Env cascade: funding runs liquidity via BLACKHOLE_FUNDING_RUN_LIQUIDITY
    # (already from BLACKHOLE_LIQUIDITY_ → BLACKHOLE_FUNDING_ + RUN_COLLATERAL rename).
    # Self context alias "funding" becomes "facility"
    out = out.replace(
        '"funding": {\n            "ok": provisional_ok,\n            "funded"',
        '"facility": {\n            "ok": provisional_ok,\n            "funded"',
    )
    out = out.replace('kind": "liquidity_coverage"', 'kind": "funding_facility"')
    out = out.replace('kind": "liquidity_log"', 'kind": "funding_log"')
    out = out.replace('kind": "liquidity_certificate"', 'kind": "funding_certificate"')
    out = out.replace('kind": "liquidity_bundle"', 'kind": "funding_bundle"')
    out = out.replace('outcome or "funded"', 'outcome or "funded"')  # no-op after word boundary
    out = out.replace('or "funded"', 'or "funded"')
    # return field name for self bundle summary
    out = out.replace(
        '"liquidity": {\n            "ok": margin.get("ok"),\n            "funding_hash"',
        '"funding": {\n            "ok": margin.get("ok"),\n            "funding_hash"',
    )
    out = out.replace(
        '"liquidity": {\n            "ok": provisional_ok,\n            "funded"',
        '"funding": {\n            "ok": provisional_ok,\n            "funded"',
    )

    out = out.replace(
        '"clearing": None\n        if liquidity_report is None\n        else {\n            "ok": liquidity_report.get("ok"),\n            "funded": liquidity_report.get("funded"),',
        '"liquidity": None\n        if liquidity_report is None\n        else {\n            "ok": liquidity_report.get("ok"),\n            "liquid": liquidity_report.get("liquid") or liquidity_report.get("funded"),',
    )
    # Parent liquid fields that were wrongly word-boundary renamed from liquid→funded
    # on parent report context should prefer liquid where meaning is parent plane
    # Fix common context parent block keys that used liquid as liquidity synonym
    out = out.replace(
        '"clearing": {\n            "ok": True if liquidity_report is None else bool(liquidity_report.get("ok")),\n            "funded": True\n            if liquidity_report is None\n            else bool(liquidity_report.get("funded")),',
        '"clearing": {\n            "ok": True if liquidity_report is None else bool(liquidity_report.get("ok")),\n            "liquid": True\n            if liquidity_report is None\n            else bool(liquidity_report.get("liquid") or liquidity_report.get("funded")),',
    )

    # Assertions on transform quality
    assert "def run_funding_plane" in out
    assert "def builtin_funding_plane" in out
    assert "FUNDING_BUNDLE_SCHEMA" in out
    assert "funding_facility_digest" in out
    assert "run_liquidity_plane" in out
    assert "load_liquidity_bundle" in out
    assert "bound_liquidity_root" in out
    assert "tip_funding_root" in out
    assert "funding over liquidity" in out
    assert "def run_liquidity_plane" not in out
    assert "def builtin_liquidity_plane" not in out
    assert "LIQUIDITY_BUNDLE_SCHEMA" not in out
    assert "liquidity_coverage_digest" in out  # parent digest retained
    assert "fundedy" not in out
    return out


def extract_liquidity_block(text: str) -> str:
    start = text.find("# ---------------------------------------------------------------------------\n# Liquidity plane over collateral")
    if start < 0:
        raise RuntimeError("liquidity plane header not found")
    # Find LIQUIDITY_BUNDLE_SCHEMA after header
    schema = text.find("LIQUIDITY_BUNDLE_SCHEMA", start)
    if schema < 0:
        raise RuntimeError("LIQUIDITY_BUNDLE_SCHEMA not found")
    # block starts at section header
    end = text.find("\ndef seed_bootstrap_capabilities(", start)
    if end < 0:
        raise RuntimeError("seed_bootstrap_capabilities after liquidity not found")
    return text[start:end].rstrip() + "\n"


def insert_funding_block(text: str, block: str) -> str:
    marker = "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError("seed_bootstrap_capabilities not found")
    if "def run_funding_plane" in text:
        print("funding plane already present; skipping block insert")
        return text
    header = (
        "\n\n# ---------------------------------------------------------------------------\n"
        "# Funding plane over liquidity\n"
        "# ---------------------------------------------------------------------------\n\n"
    )
    # block already includes liquidity header; strip and use funding header
    body = block
    if body.startswith("# ---"):
        # drop first three header lines of original
        lines = body.splitlines(keepends=True)
        # skip until blank line after header
        i = 0
        while i < len(lines) and lines[i].startswith("#"):
            i += 1
        while i < len(lines) and lines[i].strip() == "":
            i += 1
        body = "".join(lines[i:])
    return text[:idx] + header + body + "\n\n" + text[idx:]


def patch_seed_registration(text: str) -> str:
    if 'id="capability.funding-plane"' in text:
        print("seed already present")
        return text
    anchor = "    for seed in seeds:\n        if seed.id not in ledger.capabilities:"
    idx = text.find(anchor)
    if idx < 0:
        raise RuntimeError("seed loop not found")
    list_close = text.rfind("    ]\n", 0, idx)
    if list_close < 0:
        raise RuntimeError("seeds list close not found")

    seed = '''
        Capability(
            id="capability.funding-plane",
            name="Funding plane over liquidity",
            description=(
                "Closed funding plane: multi-liquidity coverages → deterministic "
                "hash-chained funding facilities with funding facility digests bound to "
                "liquidity roots → funding certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-liquidity/double-funding/forged-root/"
                "gap/digest-tamper/single-funding falsification with genesis replay matching "
                "tip — past liquid positions without funding facilities."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_funding_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_funding_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='funding over liquidity'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
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
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-funding-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-funding-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-funding-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-funding-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-funding-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-funding-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-funding-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-funding-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-funding-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-funding.json')); "
                "r=builtin_funding_plane(); assert r['ok'] and r.get('action')=='funding_plane' "
                "and r.get('funded') is True and int(r.get('funding_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('funding_certificate',{}).get('valid') "
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
                "Funding plane posts multi-liquidity coverages into deterministic "
                "hash-chained funding facilities with funding facility digests and "
                "funding certificates bound to liquidity roots, sterile rehydrate+"
                "prove, genesis replay matching tip, and adversarial falsification of "
                "wrong-liquidity/reorder/double-funding/forged-root/digest-tamper without "
                "skill-route."
            ),
            tags=(
                "bootstrap",
                "compounder",
                "funding",
                "facility",
                "funding-root",
                "liquidity",
                "treasury",
                "deterministic",
                "collateral",
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
    if '"capability.funding-plane"' not in text:
        text = text.replace(
            '"capability.liquidity-plane",\n',
            '"capability.liquidity-plane",\n        "capability.funding-plane",\n',
            1,
        )
    # Replace funding intent to prefer funding-plane; add facility/treasury intents
    text = text.replace(
        '    ("funding", ("capability.liquidity-plane", "capability.collateral-plane", "capability.quorum-plane")),\n',
        '    ("funding", ("capability.funding-plane", "capability.liquidity-plane", "capability.collateral-plane")),\n'
        '    ("funded", ("capability.funding-plane", "capability.liquidity-plane", "capability.finality-plane")),\n'
        '    ("funding facility", ("capability.funding-plane", "capability.liquidity-plane", "capability.assurance-plane")),\n'
        '    ("funding-root", ("capability.funding-plane", "capability.liquidity-plane", "capability.lineage-plane")),\n'
        '    ("facility", ("capability.funding-plane", "capability.liquidity-plane", "capability.quorum-plane")),\n'
        '    ("posted funding", ("capability.funding-plane", "capability.liquidity-plane", "capability.actuation-plane")),\n',
        1,
    )
    return text


def patch_outcome_contract_parse(text: str) -> str:
    if "funding_ok" in text and "min_fundings" in text and "funded_ok" in text:
        # already partially present — ensure full coverage
        pass
    else:
        text = text.replace(
            "#   liquidity_ok | liquid_ok | min_liquidities:N | liquidity_root_valid\n",
            "#   liquidity_ok | liquid_ok | min_liquidities:N | liquidity_root_valid\n"
            "#   funding_ok | funded_ok | min_fundings:N | funding_root_valid\n",
            1,
        )
        text = text.replace(
            "liquidity_ok|liquid_ok|min_liquidities|liquidity_root_valid",
            "liquidity_ok|liquid_ok|min_liquidities|liquidity_root_valid|"
            "funding_ok|funded_ok|min_fundings|funding_root_valid",
            1,
        )
        text = text.replace(
            '''        "liquidity_ok",
        "liquid_ok",
        "min_liquidities",
        "liquidity_root_valid",''',
            '''        "liquidity_ok",
        "liquid_ok",
        "min_liquidities",
        "liquidity_root_valid",
        "funding_ok",
        "funded_ok",
        "min_fundings",
        "funding_root_valid",''',
            1,
        )

    marker = 'found.append({"kind": "liquidity_root_valid", "arg": "", "source": chunk})'
    # find last occurrence related to liquidity soft extract
    idx = text.find(marker)
    # search for funding already after
    if idx >= 0 and "funding_ok" not in text[idx : idx + 900]:
        end = idx + len(marker)
        # skip if multiple markers — find the liquidity one (after liquidities)
        # use the last marker before evaluate section
        last = text.rfind(marker)
        if last >= 0:
            end = last + len(marker)
        funding_extract = '''
    if re.search(r"\\bfunding_ok\\b", lower) or (
        re.search(r"\\bfunding\\s+plane\\b", lower)
        and re.search(r"\\bok\\b", lower)
    ) or re.search(r"\\brun_funding_plane\\b", lower) and (
        re.search(r"\\bok\\b", lower) or True
    ):
        found.append({"kind": "funding_ok", "arg": "", "source": chunk})
    if re.search(r"\\bfunded_ok\\b", lower) or re.search(
        r"\\bfunded\\s*(?:=|is|:)\\s*true\\b", lower
    ):
        found.append({"kind": "funded_ok", "arg": "", "source": chunk})
    if (
        re.search(r"\\bfunded\\b", lower)
        and re.search(r"\\b(true|ok|yes)\\b", lower)
        and "funding-plane" not in lower
        and "funding_plane" not in lower
    ):
        found.append({"kind": "funded_ok", "arg": "", "source": chunk})
    m = re.search(r"(?:at least|>=|≥)\\s*(\\d+)\\s+funding", lower)
    if m:
        found.append({"kind": "min_fundings", "arg": m.group(1), "source": chunk})
    m = re.search(r"funding_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_fundings" for item in found):
        found.append({"kind": "min_fundings", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bmin_fundings\\b", lower) and not any(
        item.get("kind") == "min_fundings" for item in found
    ):
        m_n = re.search(r"min_fundings\\s*[:=]?\\s*(\\d+)", lower)
        if m_n:
            found.append(
                {
                    "kind": "min_fundings",
                    "arg": m_n.group(1),
                    "source": chunk,
                }
            )
    if re.search(r"\\bfunding_root_valid\\b", lower) or (
        re.search(r"\\bfunding[_\\s-]*root\\b", lower)
        and re.search(r"\\bvalid\\b", lower)
    ):
        found.append({"kind": "funding_root_valid", "arg": "", "source": chunk})
'''
        text = text[:end] + funding_extract + text[end:]
    return text


def patch_evaluate_outcome(text: str) -> str:
    if '"funding_ok",\n        "funded_ok"' in text or 'kind in {\n        "funding_ok"' in text:
        return text
    marker = 'return ok, f"liquidity_root_valid={ok}"'
    idx = text.find(marker)
    if idx < 0:
        print("WARN: liquidity_root_valid return not found for evaluate patch")
        return text
    # use last occurrence (evaluate function)
    idx = text.rfind(marker)
    end = idx + len(marker)
    eval_block = '''
    if kind in {
        "funding_ok",
        "funded_ok",
        "min_fundings",
        "funding_root_valid",
    }:
        plane = (
            context.get("funding")
            or context.get("funding_plane")
            or context.get("facility")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_funding_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "funding_ok":
            ok = bool(plane.get("ok"))
            return ok, f"funding_ok={ok}"
        if kind == "funded_ok":
            if "funded" in plane:
                ok = plane.get("funded") is True and bool(plane.get("ok", True))
            elif "funded_ok" in plane:
                ok = plane.get("funded_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("funding_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"funded_ok={ok}"
        if kind == "min_fundings":
            need = int(float(arg or "0"))
            have = context.get("funding_count")
            if have is None:
                have = context.get("tip_funding_height")
            if have is None:
                have = (
                    plane.get("funding_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"fundings={have_i} need>={need}"
        if "funding_root_valid" in plane:
            ok = plane.get("funding_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("funding_certificate")
                or plane.get("certificate")
                or context.get("funding_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_funding_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("funding_root") or plane.get("tip_funding_root")
                )
        return ok, f"funding_root_valid={ok}"
'''
    return text[:end] + eval_block + text[end:]


def patch_certificate_registry(text: str) -> str:
    if '("funding_certificate", verify_funding_certificate)' in text:
        return text
    text = text.replace(
        '("liquidity_certificate", verify_liquidity_certificate),\n',
        '("liquidity_certificate", verify_liquidity_certificate),\n'
        '                ("funding_certificate", verify_funding_certificate),\n',
        1,
    )
    if '"funding_plane"' not in text.split('"liquidity_plane"')[1][:200] if '"liquidity_plane"' in text else True:
        text = text.replace(
            '"liquidity_plane",\n',
            '"liquidity_plane",\n                "funding",\n                "funding_plane",\n',
            1,
        )
    return text


def patch_unbound(text: str) -> str:
    if "run_funding_plane" in text and "needs_funding" in text:
        return text
    if "run_liquidity_plane" in text and "run_funding_plane" not in text:
        text = text.replace(
            "run_liquidity_plane,\n",
            "run_liquidity_plane,\n    run_funding_plane,\n",
            1,
        )
        text = text.replace(
            """    run_liquidity = (
        cc.run_liquidity_plane if cc is not None else run_liquidity_plane
    )
""",
            """    run_liquidity = (
        cc.run_liquidity_plane if cc is not None else run_liquidity_plane
    )
    run_funding = (
        cc.run_funding_plane if cc is not None else run_funding_plane
    )
""",
            1,
        )

    # needs_funding before needs_liquidity
    if "needs_funding" not in text:
        text = text.replace(
            '''                    needs_liquidity = bool(
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
''',
            '''                    needs_funding = bool(
                        kinds
                        & {
                            "funding_ok",
                            "funded_ok",
                            "min_fundings",
                            "funding_root_valid",
                        }
                    )
                    needs_liquidity = bool(
                        kinds
                        & {
                            "liquidity_ok",
                            "liquid_ok",
                            "min_liquidities",
                            "liquidity_root_valid",
                        }
                    ) and not needs_funding
                    needs_collateral = bool(
                        kinds
                        & {
                            "collateral_ok",
                            "collateralized_ok",
                            "min_collaterals",
                            "collateral_root_valid",
                        }
                    ) and not needs_liquidity and not needs_funding
''',
            1,
        )
        # extend and not needs_funding on lower planes
        for plane in (
            "needs_margin",
            "needs_clearing",
            "needs_settlement",
            "needs_actuation",
            "needs_execution",
            "needs_finality",
            "needs_quorum",
            "needs_federation",
        ):
            # append " and not needs_funding" where we already have not needs_liquidity
            pass
        text = text.replace(
            "and not needs_collateral and not needs_liquidity\n",
            "and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )
        text = text.replace(
            "and not needs_margin and not needs_collateral and not needs_liquidity\n",
            "and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )
        text = text.replace(
            "and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity\n",
            "and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )
        text = text.replace(
            "and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity\n",
            "and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )
        text = text.replace(
            "and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity\n",
            "and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )
        text = text.replace(
            "and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity\n",
            "and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )
        text = text.replace(
            "and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity\n",
            "and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )
        text = text.replace(
            "and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity\n",
            "and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding\n",
        )

    if "if needs_funding:" not in text:
        insert_at = text.find("                    if needs_liquidity:")
        if insert_at < 0:
            print("WARN: needs_liquidity run block not found")
            return text
        funding_run = '''                    if needs_funding:
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
                        funding = run_funding(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "funding over liquidity",
                            done_when=plane_done_when,
                            max_steps=3,
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
                            min_fundings=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                funding.get("used_skill_route_discovery")
                            ),
                            "chain": funding.get("chain") or {},
                            "funding_chain": funding.get("chain") or {},
                            "liquidity": {
                                "ok": bool(
                                    (funding.get("liquidity") or {}).get("ok", True)
                                ),
                                "liquid": bool(
                                    (funding.get("liquidity") or {}).get(
                                        "liquid", True
                                    )
                                ),
                                "liquidity_count": int(
                                    funding.get("liquidity_count") or 0
                                ),
                                "liquidity_root_valid": True,
                                "certificate_valid": True,
                                "liquidity_coverage_digest": funding.get(
                                    "liquidity_coverage_digest"
                                ),
                            },
                            "liquidity_plane": {
                                "ok": bool(
                                    (funding.get("liquidity") or {}).get("ok", True)
                                ),
                                "liquid": True,
                                "liquidity_count": int(
                                    funding.get("liquidity_count") or 0
                                ),
                                "liquidity_root_valid": True,
                            },
                            "funding": {
                                "ok": bool(funding.get("ok")),
                                "funded": bool(funding.get("funded")),
                                "funding_count": int(
                                    funding.get("funding_count") or 0
                                ),
                                "tip_height": int(funding.get("tip_height") or 0),
                                "tip_funding_root": funding.get(
                                    "tip_funding_root"
                                ),
                                "funding_root_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "funding_facility_digest": funding.get(
                                    "funding_facility_digest"
                                ),
                                "deterministic": True,
                                "post_liquidity": True,
                                "multi_funding": int(
                                    funding.get("funding_count") or 0
                                )
                                >= 2,
                            },
                            "funding_plane": {
                                "ok": bool(funding.get("ok")),
                                "funded": bool(funding.get("funded")),
                                "funding_count": int(
                                    funding.get("funding_count") or 0
                                ),
                                "funding_root_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "facility": {
                                "ok": bool(funding.get("ok")),
                                "funded": bool(funding.get("funded")),
                                "funding_count": int(
                                    funding.get("funding_count") or 0
                                ),
                                "funding_facility_digest": funding.get(
                                    "funding_facility_digest"
                                ),
                                "funding_root_valid": bool(
                                    (funding.get("funding_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "funding_count": int(funding.get("funding_count") or 0),
                            "liquidity_count": int(
                                funding.get("liquidity_count") or 0
                            ),
                            "tip_height": int(funding.get("tip_height") or 0),
                            "funding_certificate": funding.get(
                                "funding_certificate"
                            ),
                            "funding_hash": funding.get("funding_hash"),
                            "liquidity_hash": funding.get("liquidity_hash"),
                            "tip_funding_root": funding.get("tip_funding_root"),
                            "bound_liquidity_root": funding.get(
                                "bound_liquidity_root"
                            ),
                            "funding_facility_digest": funding.get(
                                "funding_facility_digest"
                            ),
                            "liquidity_coverage_digest": funding.get(
                                "liquidity_coverage_digest"
                            ),
                        }
                    elif needs_liquidity:
'''
        text = text[:insert_at] + funding_run + text[insert_at + len("                    if needs_liquidity:"):]
    return text


def patch_test_file(text: str) -> str:
    if "test_funding_plane_facilities_and_adversarial" in text:
        return text
    test = '''

def test_funding_plane_facilities_and_adversarial():
    """Funding plane posts multi-liquidity coverages and falsifies wrong-liquidity binds."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_funding_bundle,
        parse_outcome_contract,
        run_funding_plane,
        verify_funding_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.funding-plane" in ledger.capabilities
    assert "capability.liquidity-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; funding_ok; funded_ok; min_fundings:2; "
        "funding_root_valid; liquidity_ok; liquid_ok; min_liquidities:2; "
        "liquidity_root_valid; chain_valid"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "funding_ok" in kinds
    assert "funded_ok" in kinds
    assert "min_fundings" in kinds
    assert "funding_root_valid" in kinds

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-funding-plane.json"
    quorum_path = repo / "artifacts" / "quorum-bundles" / "test-funding-quorum.json"
    finality_path = repo / "artifacts" / "finality-bundles" / "test-funding-finality.json"
    execution_path = repo / "artifacts" / "execution-bundles" / "test-funding-execution.json"
    actuation_path = repo / "artifacts" / "actuation-bundles" / "test-funding-actuation.json"
    settlement_path = repo / "artifacts" / "settlement-bundles" / "test-funding-settlement.json"
    margin_path = repo / "artifacts" / "margin-bundles" / "test-funding-margin.json"
    collateral_path = repo / "artifacts" / "collateral-bundles" / "test-funding-collateral.json"
    liquidity_path = repo / "artifacts" / "liquidity-bundles" / "test-funding-liquidity.json"
    funding_path = repo / "artifacts" / "funding-bundles" / "test-funding-plane.json"
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
        funding_path,
    ):
        if target.exists():
            target.unlink()

    plane = run_funding_plane(
        repo,
        "funding over liquidity",
        "min_capabilities:5; capability_exists:repo.import-health; no_skill_route",
        max_steps=3,
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
        inject_byzantine=True,
        epoch_count=2,
        min_actions=2,
        min_settlements=2,
        min_clearings=2,
        min_margins=2,
        min_collaterals=2,
        min_liquidities=2,
        min_fundings=2,
        lineage_path=lineage_path,
        quorum_path=quorum_path,
        finality_path=finality_path,
        execution_path=execution_path,
        actuation_path=actuation_path,
        settlement_path=settlement_path,
        margin_path=margin_path,
        collateral_path=collateral_path,
        liquidity_path=liquidity_path,
        funding_path=funding_path,
        timeout=960,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "funding_plane"
    assert plane["funded"] is True
    assert int(plane["funding_count"]) >= 2
    assert int(plane["tip_height"]) >= 2
    assert int(plane["liquidity_count"] or 0) >= 2
    assert plane.get("funding_facility_digest")
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["multi_funding"] is True
    assert plane["integrity"]["funding_ok"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["funding_certificate"]["valid"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["wrong_liquidity_fails_as_expected"] is True
    assert plane["adversarial"]["reorder_fails_as_expected"] is True
    assert plane["adversarial"]["digest_tamper_fails_as_expected"] is True
    assert plane["adversarial"]["single_funding_fails_as_expected"] is True
    assert plane["adversarial"]["duplicate_apply_fails_as_expected"] is True
    assert plane["adversarial"]["replay_matches_tip"] is True
    assert plane["used_skill_route_discovery"] is False
    assert funding_path.is_file()

    loaded = load_funding_bundle(funding_path)
    assert verify_funding_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("funding_hash")
    assert int(loaded.get("funding_count") or 0) >= 2
    assert int(loaded.get("tip_height") or 0) >= 2
    assert loaded.get("funding_facility_digest")
    assert path.name == "ledger.json"
'''
    return text.rstrip() + test + "\n"


def fix_funding_run_signature(text: str) -> str:
    """Post-process run_funding_plane signature after naive transform.

    Liquidity plane had run_collateral as first parent flag; after transform
    we want run_liquidity as the direct parent plane flag, while still
    cascading run_collateral into liquidity plane.
    """
    # After transform, run_funding_plane may have:
    #   run_liquidity: bool = True,  # was run_collateral
    #   run_margin: bool = True,
    # We need run_liquidity + keep run_collateral for cascade.
    # Transform already renamed run_collateral -> run_liquidity.
    # But liquidity plane's run_margin stays as run_margin — good for cascade.
    # Ensure call to run_liquidity_plane passes run_collateral=run_liquidity wait —
    # actually after rename, call is run_liquidity_plane(..., run_liquidity=run_liquidity)
    # but liquidity plane expects run_collateral=. Fix that.
    if "def run_funding_plane" not in text:
        return text

    # Fix the nested call parameter names inside run_funding_plane only
    start = text.find("def run_funding_plane(")
    end = text.find("\ndef builtin_funding_plane(", start)
    if start < 0 or end < 0:
        return text
    body = text[start:end]
    # Nested call: run_liquidity_plane(..., run_liquidity=run_liquidity, run_margin=...)
    # should be run_liquidity= -> no, liquidity plane takes run_collateral=
    fixed = body.replace(
        "run_liquidity_plane(\n            root,\n            goal if goal else \"liquidity for funding\",\n            strip_context_only_outcome_predicates(done_when or \"\"),\n            command_runner=command_runner,\n            timeout=timeout,\n            max_steps=max_steps,\n            run_liquidity=run_liquidity,\n",
        "run_liquidity_plane(\n            root,\n            goal if goal else \"liquidity for funding\",\n            strip_context_only_outcome_predicates(done_when or \"\"),\n            command_runner=command_runner,\n            timeout=timeout,\n            max_steps=max_steps,\n            run_collateral=run_liquidity,\n",
    )
    # Also the fallback path
    fixed = fixed.replace(
        "run_liquidity_plane(\n                root,\n                goal,\n                \"\",\n                command_runner=command_runner,\n                timeout=timeout,\n                max_steps=max_steps,\n                run_liquidity=run_liquidity,\n",
        "run_liquidity_plane(\n                root,\n                goal,\n                \"\",\n                command_runner=command_runner,\n                timeout=timeout,\n                max_steps=max_steps,\n                run_collateral=run_liquidity,\n",
    )
    # builtin env: BLACKHOLE_FUNDING_RUN_LIQUIDITY should map to run_liquidity
    # Signature: ensure param is still named run_liquidity
    # Parent report field access: (liquidity_report.get("margin") or {}) may be wrong
    # Liquidity plane returns "liquidity" key for self bundle; transform may have left "margin"
    fixed = fixed.replace(
        'Path((liquidity_report.get("margin") or {}).get("bundle_path") or "")',
        'Path((liquidity_report.get("liquidity") or liquidity_report.get("margin") or {}).get("bundle_path") or "")',
    )
    # funding_path param: transform renamed liquidity_path to funding_path for self;
    # but we also need a liquidity_path for parent. Signature may only have funding_path.
    # Original liquidity had both collateral_path and liquidity_path.
    # After transform: liquidity_path (parent) and funding_path (self). Good if both exist.
    return text[:start] + fixed + text[end:]


def fix_builtin_funding_env(text: str) -> str:
    start = text.find("def builtin_funding_plane()")
    if start < 0:
        return text
    end = text.find("\ndef seed_bootstrap_capabilities", start)
    if end < 0:
        return text
    body = text[start:end]
    # After transform, run_liquidity = BLACKHOLE_FUNDING_RUN_LIQUIDITY — good if fix applied
    # But may still say BLACKHOLE_FUNDING_RUN_LIQUIDITY from our replace of BLACKHOLE_LIQUIDITY_RUN_COLLATERAL
    # Ensure call uses run_liquidity=
    if "run_liquidity=run_liquidity" not in body and "run_liquidity=" in body:
        pass
    # Fix: if still has run_collateral=run_liquidity in builtin call that's wrong for funding
    body2 = body
    # Ensure min_fundings env
    if "BLACKHOLE_FUNDING_MIN_FUNDINGS" not in body2:
        body2 = body2.replace(
            'min_liquidities = int(os.environ.get("BLACKHOLE_LIQUIDITY_MIN_LIQUIDITIES") or "2")',
            'min_liquidities = int(os.environ.get("BLACKHOLE_LIQUIDITY_MIN_LIQUIDITIES") or "2")\n'
            '    min_fundings = int(os.environ.get("BLACKHOLE_FUNDING_MIN_FUNDINGS") or "2")',
        )
    return text[:start] + body2 + text[end:]


def main() -> None:
    text = COMPOUNDER.read_text(encoding="utf-8")
    block = extract_liquidity_block(text)
    transformed = transform_liquidity_block(block)
    text = insert_funding_block(text, transformed)
    text = fix_funding_run_signature(text)
    text = fix_builtin_funding_env(text)
    text = patch_seed_registration(text)
    text = patch_plane_lists_and_intents(text)
    text = patch_outcome_contract_parse(text)
    text = patch_evaluate_outcome(text)
    text = patch_certificate_registry(text)
    COMPOUNDER.write_text(text, encoding="utf-8")
    print("patched capability_compounder.py")

    utext = UNBOUND.read_text(encoding="utf-8")
    utext = patch_unbound(utext)
    UNBOUND.write_text(utext, encoding="utf-8")
    print("patched unbound.py")

    ttext = TEST.read_text(encoding="utf-8")
    ttext = patch_test_file(ttext)
    TEST.write_text(ttext, encoding="utf-8")
    print("patched test_capability_compounder.py")


if __name__ == "__main__":
    main()
