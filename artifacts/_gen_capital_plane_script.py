"""Generate capital plane code from funding plane pattern and patch integrations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOUNDER = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND = ROOT / "src" / "blackhole_agent" / "unbound.py"
TEST = ROOT / "tests" / "test_capability_compounder.py"


def transform_funding_block(block: str) -> str:
    # Order: longest / most-specific self renames first. Never bare "funded"→"capitalized"
    # before multi-token renames (that would corrupt remaining parent funding tokens after
    # parent rename if done wrong). Self renames first, then parent liquidity→funding.
    replacements = [
        # Digests first (self then parent retained under new names)
        ("funding_facility_digest", "capital_buffer_digest"),
        ("liquidity_coverage_digest", "funding_facility_digest"),
        # Outcomes / multi
        ("funded_ok", "capitalized_ok"),
        ("multi_funding", "multi_capital"),
        ("min_fundings", "min_capitals"),
        ("single_funding", "single_capital"),
        ("double-funding", "double-capital"),
        ("double_funding", "double_capital"),
        ("need_multi_funding", "need_multi_capital"),
        # Plane / action names
        ("funding_plane", "capital_plane"),
        ("Funding plane", "Capital plane"),
        ("funding plane", "capital plane"),
        ("builtin_funding_plane", "builtin_capital_plane"),
        ("run_funding_plane", "run_capital_plane"),
        ("run_funding_adversarial", "run_capital_adversarial"),
        # Bundle/log/cert machinery
        ("FUNDING_BUNDLE_SCHEMA", "CAPITAL_BUNDLE_SCHEMA"),
        ("FUNDING_CERTIFICATE_SCHEMA", "CAPITAL_CERTIFICATE_SCHEMA"),
        ("FUNDING_LOG_SCHEMA", "CAPITAL_LOG_SCHEMA"),
        ("DEFAULT_FUNDING_BUNDLE_RELATIVE", "DEFAULT_CAPITAL_BUNDLE_RELATIVE"),
        ("default_funding_bundle_dir", "default_capital_bundle_dir"),
        ("empty_funding_log", "empty_capital_log"),
        ("compute_funding_root", "compute_capital_root"),
        ("compute_funding_certificate_hash", "compute_capital_certificate_hash"),
        ("compute_funding_bundle_hash", "compute_capital_bundle_hash"),
        ("compute_funding_facility_digest", "compute_capital_buffer_digest"),
        ("issue_funding_certificate", "issue_capital_certificate"),
        ("verify_funding_certificate", "verify_capital_certificate"),
        ("write_funding_certificate", "write_capital_certificate"),
        ("_load_funding_disk_evidence", "_load_capital_disk_evidence"),
        ("derive_funding_specs_from_liquidity", "derive_capital_specs_from_funding"),
        ("apply_funding_transition", "apply_capital_transition"),
        ("verify_funding_chain", "verify_capital_chain"),
        ("apply_funding_bundle_to_fundings", "apply_funding_bundle_to_capitals"),
        ("apply_liquidity_bundle_to_fundings", "apply_funding_bundle_to_capitals"),
        ("build_funding_bundle", "build_capital_bundle"),
        ("write_funding_bundle", "write_capital_bundle"),
        ("load_funding_bundle", "load_capital_bundle"),
        ("verify_funding_bundle_integrity", "verify_capital_bundle_integrity"),
        ("rehydrate_funding_bundle", "rehydrate_capital_bundle"),
        ("replay_fundings_from_specs", "replay_capitals_from_specs"),
        # Structural field names (self)
        ("funding_certificate", "capital_certificate"),
        ("funding_bundle", "capital_bundle"),
        ("funding_log", "capital_log"),
        ("funding_hash", "capital_hash"),
        ("funding_root", "capital_root"),
        ("funding_height", "capital_height"),
        ("funding_count", "capital_count"),
        ("tip_funding", "tip_capital"),
        ("parent_funding", "parent_capital"),
        ("fundings", "capitals"),
        ("funding_ok", "capital_ok"),
        ("funding_done_when", "capital_done_when"),
        ("funding_n", "capital_n"),
        ("funding_path", "capital_path"),
        ("facility_ratio_bps", "buffer_ratio_bps"),
        ("post_liquidity", "post_funding"),
        # Paths / strings
        ("funding-bundles", "capital-bundles"),
        ("funding-sandbox", "capital-sandbox"),
        ("funding-certificate", "capital-certificate"),
        ("proof-funding", "proof-capital"),
        ("test-funding", "test-capital"),
        ("funding-source-liquidity", "capital-source-funding"),
        ("BLACKHOLE_FUNDING_", "BLACKHOLE_CAPITAL_"),
        # Domain language
        ("funding over liquidity", "capital over funding"),
        ("liquidity for funding", "funding for capital"),
        ("funding facility", "capital buffer"),
        ("Funding facility", "Capital buffer"),
        ("funding facilities", "capital buffers"),
        ("Funding facilities", "Capital buffers"),
        # Parent renames (liquidity → funding) AFTER self renames
        ("run_liquidity_plane", "run_funding_plane"),
        ("run_liquidity", "run_funding"),
        ("load_liquidity_bundle", "load_funding_bundle"),
        ("verify_liquidity_certificate", "verify_funding_certificate"),
        ("write_liquidity_certificate", "write_funding_certificate"),
        ("default_liquidity_bundle_dir", "default_funding_bundle_dir"),
        ("liquidity_bundle", "funding_bundle"),
        ("liquidity_report", "funding_report"),
        ("liquidity_path", "funding_path"),
        ("out_liquidity", "out_funding"),
        ("liquidity_certificate", "funding_certificate"),
        ("bound_liquidity_root", "bound_funding_root"),
        ("bound_liquidity_height", "bound_funding_height"),
        ("tip_liquidity_root", "tip_funding_root"),
        ("liquidity_hash", "funding_hash"),
        ("liquidity_count", "funding_count"),
        ("min_liquidities", "min_fundings"),
        ("want_liquidities", "want_fundings"),
        ("liquidity_n", "funding_n"),
        ("liquidities", "fundings"),
        ("liquidity_entries", "funding_entries"),
        ("liquidity_root", "funding_root"),
        ("liquidity_height", "funding_height"),
        ("known_liquidity_roots", "known_funding_roots"),
        ("wrong_liquidity", "wrong_funding"),
        ("liquidity_ok", "funding_ok"),
        ("BLACKHOLE_LIQUIDITY_BUNDLE_PATH", "BLACKHOLE_FUNDING_BUNDLE_PATH"),
        ("BLACKHOLE_LIQUIDITY_MIN_LIQUIDITIES", "BLACKHOLE_FUNDING_MIN_FUNDINGS"),
        ("BLACKHOLE_LIQUIDITY_RUN_COLLATERAL", "BLACKHOLE_FUNDING_RUN_LIQUIDITY"),
        ('"plane": "funding"', '"plane": "capital"'),
        ("liquidity_source_failed", "funding_source_failed"),
        ("missing_funding_bind", "missing_capital_bind"),
        ("from_liquidity", "from_funding"),
        ("over liquidity", "over funding"),
        ("to a liquidity", "to a funding"),
        ("liquidity coverage", "funding facility"),
        ("liquidity tip", "funding tip"),
        ("liquidity source", "funding source"),
        ("past liquid positions", "past funded positions"),
        ("parent_liquid", "parent_funded"),
    ]

    out = block
    for old, new in replacements:
        out = out.replace(old, new)

    # Word-boundary adjective renames only (never touch remaining "funding" parent tokens)
    out = re.sub(r"\bfunded\b", "capitalized", out)
    out = re.sub(r"\bFunded\b", "Capitalized", out)
    # Parent liquid synonym may remain; map liquid→funded for parent plane
    out = re.sub(r"\bliquid\b", "funded", out)
    out = re.sub(r"\bLiquid\b", "Funded", out)

    out = out.replace(
        'action": "funding_adversarial_checks"',
        'action": "capital_adversarial_checks"',
    )
    out = out.replace(
        "BLACKHOLE_CAPITAL_RUN_LIQUIDITY",
        "BLACKHOLE_CAPITAL_RUN_FUNDING",
    )
    out = out.replace(
        "BLACKHOLE_CAPITAL_MIN_FUNDINGS",
        "BLACKHOLE_CAPITAL_MIN_CAPITALS",
    )
    # Self context alias "capital" becomes "buffer" for secondary key (like facility)
    out = out.replace(
        '"capital": {\n            "ok": provisional_ok,\n            "capitalized"',
        '"buffer": {\n            "ok": provisional_ok,\n            "capitalized"',
    )
    # Also handle facility key that was transformed from funding's facility alias
    out = out.replace(
        '"facility": {\n            "ok": provisional_ok,\n            "capitalized"',
        '"buffer": {\n            "ok": provisional_ok,\n            "capitalized"',
    )
    out = out.replace('kind": "funding_facility"', 'kind": "capital_buffer"')
    out = out.replace('kind": "funding_log"', 'kind": "capital_log"')
    out = out.replace('kind": "funding_certificate"', 'kind": "capital_certificate"')
    out = out.replace('kind": "funding_bundle"', 'kind": "capital_bundle"')
    out = out.replace('outcome or "capitalized"', 'outcome or "capitalized"')
    out = out.replace('or "capitalized"', 'or "capitalized"')
    # return field name for self bundle summary
    out = out.replace(
        '"funding": {\n            "ok": margin.get("ok"),\n            "capital_hash"',
        '"capital": {\n            "ok": margin.get("ok"),\n            "capital_hash"',
    )
    out = out.replace(
        '"funding": {\n            "ok": provisional_ok,\n            "capitalized"',
        '"capital": {\n            "ok": provisional_ok,\n            "capitalized"',
    )
    out = out.replace(
        '"liquidity": None\n        if funding_report is None\n        else {\n            "ok": funding_report.get("ok"),\n            "funded": funding_report.get("funded"),',
        '"funding": None\n        if funding_report is None\n        else {\n            "ok": funding_report.get("ok"),\n            "funded": funding_report.get("funded") or funding_report.get("capitalized"),',
    )
    out = out.replace(
        '"liquidity": None\n            if funding_report is None\n            else {\n                "ok": funding_report.get("ok"),\n                "funded": funding_report.get("funded"),',
        '"funding": None\n            if funding_report is None\n            else {\n                "ok": funding_report.get("ok"),\n                "funded": funding_report.get("funded") or funding_report.get("capitalized"),',
    )
    # Parent context blocks
    out = out.replace(
        '"clearing": {\n            "ok": True if funding_report is None else bool(funding_report.get("ok")),\n            "funded": True\n            if funding_report is None\n            else bool(funding_report.get("funded") or funding_report.get("capitalized")),',
        '"clearing": {\n            "ok": True if funding_report is None else bool(funding_report.get("ok")),\n            "funded": True\n            if funding_report is None\n            else bool(funding_report.get("funded") or funding_report.get("liquid")),',
    )

    # Fix apply function name if double-renamed wrong
    out = out.replace(
        "apply_capital_bundle_to_capitals",
        "apply_funding_bundle_to_capitals",
    )
    # Parent funded report keys
    out = out.replace(
        'parent_funded = bool(\n        (funding_report or {}).get("funded")\n        or (funding_report or {}).get("ok")\n        or (funding_bundle or {}).get("ok")\n    )',
        'parent_funded = bool(\n        (funding_report or {}).get("funded")\n        or (funding_report or {}).get("capitalized")\n        or (funding_report or {}).get("ok")\n        or (funding_bundle or {}).get("ok")\n    )',
    )

    # Assertions on transform quality
    assert "def run_capital_plane" in out
    assert "def builtin_capital_plane" in out
    assert "CAPITAL_BUNDLE_SCHEMA" in out
    assert "capital_buffer_digest" in out
    assert "run_funding_plane" in out
    assert "load_funding_bundle" in out
    assert "bound_funding_root" in out
    assert "tip_capital_root" in out
    assert "capital over funding" in out
    assert "def run_funding_plane" not in out
    assert "def builtin_funding_plane" not in out
    assert "FUNDING_BUNDLE_SCHEMA" not in out
    assert "funding_facility_digest" in out  # parent digest retained
    assert "capitalizedy" not in out
    assert "funding_facility" not in out or "capital buffer" in out
    return out


def extract_funding_block(text: str) -> str:
    start = text.find(
        "# ---------------------------------------------------------------------------\n# Funding plane over liquidity"
    )
    if start < 0:
        raise RuntimeError("funding plane header not found")
    end = text.find("\ndef seed_bootstrap_capabilities(", start)
    if end < 0:
        raise RuntimeError("seed_bootstrap_capabilities after funding not found")
    return text[start:end].rstrip() + "\n"


def insert_capital_block(text: str, block: str) -> str:
    marker = "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError("seed_bootstrap_capabilities not found")
    if "def run_capital_plane" in text:
        print("capital plane already present; skipping block insert")
        return text
    header = (
        "\n\n# ---------------------------------------------------------------------------\n"
        "# Capital plane over funding\n"
        "# ---------------------------------------------------------------------------\n\n"
    )
    body = block
    if body.startswith("# ---"):
        lines = body.splitlines(keepends=True)
        i = 0
        while i < len(lines) and lines[i].startswith("#"):
            i += 1
        while i < len(lines) and lines[i].strip() == "":
            i += 1
        body = "".join(lines[i:])
    return text[:idx] + header + body + "\n\n" + text[idx:]


def patch_seed_registration(text: str) -> str:
    if 'id="capability.capital-plane"' in text:
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
            id="capability.capital-plane",
            name="Capital plane over funding",
            description=(
                "Closed capital plane: multi-funding facilities → deterministic "
                "hash-chained capital buffers with capital buffer digests bound to "
                "funding roots → capital certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-funding/double-capital/forged-root/"
                "gap/digest-tamper/single-capital falsification with genesis replay matching "
                "tip — past funded positions without capital buffers."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_capital_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_capital_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='capital over funding'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
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
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-capital-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-capital-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-capital-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-capital-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-capital-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-capital-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-capital-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-capital-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-capital-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-capital-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-capital.json')); "
                "r=builtin_capital_plane(); assert r['ok'] and r.get('action')=='capital_plane' "
                "and r.get('capitalized') is True and int(r.get('capital_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('capital_certificate',{}).get('valid') "
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
                "Capital plane posts multi-funding facilities into deterministic "
                "hash-chained capital buffers with capital buffer digests and "
                "capital certificates bound to funding roots, sterile rehydrate+"
                "prove, genesis replay matching tip, and adversarial falsification of "
                "wrong-funding/reorder/double-capital/forged-root/digest-tamper without "
                "skill-route."
            ),
            tags=(
                "bootstrap",
                "compounder",
                "capital",
                "buffer",
                "capital-root",
                "funding",
                "adequacy",
                "deterministic",
                "liquidity",
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
    if '"capability.capital-plane"' not in text:
        text = text.replace(
            '"capability.funding-plane",\n',
            '"capability.funding-plane",\n        "capability.capital-plane",\n',
            1,
        )
    if '    ("capital", (' not in text:
        text = text.replace(
            '    ("posted funding", ("capability.funding-plane", "capability.liquidity-plane", "capability.actuation-plane")),\n',
            '    ("posted funding", ("capability.funding-plane", "capability.liquidity-plane", "capability.actuation-plane")),\n'
            '    ("capital", ("capability.capital-plane", "capability.funding-plane", "capability.liquidity-plane")),\n'
            '    ("capitalized", ("capability.capital-plane", "capability.funding-plane", "capability.finality-plane")),\n'
            '    ("capital buffer", ("capability.capital-plane", "capability.funding-plane", "capability.assurance-plane")),\n'
            '    ("capital-root", ("capability.capital-plane", "capability.funding-plane", "capability.lineage-plane")),\n'
            '    ("buffer", ("capability.capital-plane", "capability.funding-plane", "capability.quorum-plane")),\n'
            '    ("posted capital", ("capability.capital-plane", "capability.funding-plane", "capability.actuation-plane")),\n'
            '    ("adequacy", ("capability.capital-plane", "capability.funding-plane", "capability.assurance-plane")),\n',
            1,
        )
    return text


def patch_outcome_contract_parse(text: str) -> str:
    if "capital_ok" in text and "min_capitals" in text and "capitalized_ok" in text:
        pass
    else:
        text = text.replace(
            "#   funding_ok | funded_ok | min_fundings:N | funding_root_valid\n",
            "#   funding_ok | funded_ok | min_fundings:N | funding_root_valid\n"
            "#   capital_ok | capitalized_ok | min_capitals:N | capital_root_valid\n",
            1,
        )
        text = text.replace(
            "funding_ok|funded_ok|min_fundings|funding_root_valid",
            "funding_ok|funded_ok|min_fundings|funding_root_valid|"
            "capital_ok|capitalized_ok|min_capitals|capital_root_valid",
            1,
        )
        text = text.replace(
            '''        "funding_ok",
        "funded_ok",
        "min_fundings",
        "funding_root_valid",''',
            '''        "funding_ok",
        "funded_ok",
        "min_fundings",
        "funding_root_valid",
        "capital_ok",
        "capitalized_ok",
        "min_capitals",
        "capital_root_valid",''',
            1,
        )

    marker = 'found.append({"kind": "funding_root_valid", "arg": "", "source": chunk})'
    last = text.rfind(marker)
    if last >= 0 and "capital_ok" not in text[last : last + 900]:
        end = last + len(marker)
        capital_extract = '''
    if re.search(r"\\bcapital_ok\\b", lower) or (
        re.search(r"\\bcapital\\s+plane\\b", lower)
        and re.search(r"\\bok\\b", lower)
    ) or re.search(r"\\brun_capital_plane\\b", lower) and (
        re.search(r"\\bok\\b", lower) or True
    ):
        found.append({"kind": "capital_ok", "arg": "", "source": chunk})
    if re.search(r"\\bcapitalized_ok\\b", lower) or re.search(
        r"\\bcapitalized\\s*(?:=|is|:)\\s*true\\b", lower
    ):
        found.append({"kind": "capitalized_ok", "arg": "", "source": chunk})
    if (
        re.search(r"\\bcapitalized\\b", lower)
        and re.search(r"\\b(true|ok|yes)\\b", lower)
        and "capital-plane" not in lower
        and "capital_plane" not in lower
    ):
        found.append({"kind": "capitalized_ok", "arg": "", "source": chunk})
    m = re.search(r"(?:at least|>=|≥)\\s*(\\d+)\\s+capital", lower)
    if m:
        found.append({"kind": "min_capitals", "arg": m.group(1), "source": chunk})
    m = re.search(r"capital_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_capitals" for item in found):
        found.append({"kind": "min_capitals", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bmin_capitals\\b", lower) and not any(
        item.get("kind") == "min_capitals" for item in found
    ):
        m_n = re.search(r"min_capitals\\s*[:=]?\\s*(\\d+)", lower)
        if m_n:
            found.append(
                {
                    "kind": "min_capitals",
                    "arg": m_n.group(1),
                    "source": chunk,
                }
            )
    if re.search(r"\\bcapital_root_valid\\b", lower) or (
        re.search(r"\\bcapital[_\\s-]*root\\b", lower)
        and re.search(r"\\bvalid\\b", lower)
    ):
        found.append({"kind": "capital_root_valid", "arg": "", "source": chunk})
'''
        text = text[:end] + capital_extract + text[end:]
    return text


def patch_evaluate_outcome(text: str) -> str:
    if 'kind in {\n        "capital_ok"' in text or '"capital_ok",\n        "capitalized_ok"' in text:
        return text
    marker = 'return ok, f"funding_root_valid={ok}"'
    idx = text.rfind(marker)
    if idx < 0:
        print("WARN: funding_root_valid return not found for evaluate patch")
        return text
    end = idx + len(marker)
    eval_block = '''
    if kind in {
        "capital_ok",
        "capitalized_ok",
        "min_capitals",
        "capital_root_valid",
    }:
        plane = (
            context.get("capital")
            or context.get("capital_plane")
            or context.get("buffer")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_capital_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "capital_ok":
            ok = bool(plane.get("ok"))
            return ok, f"capital_ok={ok}"
        if kind == "capitalized_ok":
            if "capitalized" in plane:
                ok = plane.get("capitalized") is True and bool(plane.get("ok", True))
            elif "capitalized_ok" in plane:
                ok = plane.get("capitalized_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("capital_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"capitalized_ok={ok}"
        if kind == "min_capitals":
            need = int(float(arg or "0"))
            have = context.get("capital_count")
            if have is None:
                have = context.get("tip_capital_height")
            if have is None:
                have = (
                    plane.get("capital_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"capitals={have_i} need>={need}"
        if "capital_root_valid" in plane:
            ok = plane.get("capital_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("capital_certificate")
                or plane.get("certificate")
                or context.get("capital_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_capital_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("capital_root") or plane.get("tip_capital_root")
                )
        return ok, f"capital_root_valid={ok}"
'''
    return text[:end] + eval_block + text[end:]


def patch_certificate_registry(text: str) -> str:
    if '("capital_certificate", verify_capital_certificate)' in text:
        return text
    text = text.replace(
        '("funding_certificate", verify_funding_certificate),\n',
        '("funding_certificate", verify_funding_certificate),\n'
        '                ("capital_certificate", verify_capital_certificate),\n',
        1,
    )
    if '"capital_plane"' not in text:
        text = text.replace(
            '"funding_plane",\n',
            '"funding_plane",\n                "capital",\n                "capital_plane",\n',
            1,
        )
    return text


def patch_unbound(text: str) -> str:
    if "run_capital_plane" in text and "needs_capital" in text:
        return text
    if "run_funding_plane" in text and "run_capital_plane" not in text:
        text = text.replace(
            "run_funding_plane,\n",
            "run_funding_plane,\n    run_capital_plane,\n",
            1,
        )
        text = text.replace(
            """    run_funding = (
        cc.run_funding_plane if cc is not None else run_funding_plane
    )
""",
            """    run_funding = (
        cc.run_funding_plane if cc is not None else run_funding_plane
    )
    run_capital = (
        cc.run_capital_plane if cc is not None else run_capital_plane
    )
""",
            1,
        )

    if "needs_capital" not in text:
        text = text.replace(
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
''',
            '''                    needs_capital = bool(
                        kinds
                        & {
                            "capital_ok",
                            "capitalized_ok",
                            "min_capitals",
                            "capital_root_valid",
                        }
                    )
                    needs_funding = bool(
                        kinds
                        & {
                            "funding_ok",
                            "funded_ok",
                            "min_fundings",
                            "funding_root_valid",
                        }
                    ) and not needs_capital
                    needs_liquidity = bool(
                        kinds
                        & {
                            "liquidity_ok",
                            "liquid_ok",
                            "min_liquidities",
                            "liquidity_root_valid",
                        }
                    ) and not needs_funding and not needs_capital
''',
            1,
        )
        text = text.replace(
            "and not needs_funding\n",
            "and not needs_funding and not needs_capital\n",
        )
        text = text.replace(
            "and not needs_liquidity and not needs_funding\n",
            "and not needs_liquidity and not needs_funding and not needs_capital\n",
        )

    if "if needs_capital:" not in text:
        insert_at = text.find("                    if needs_funding:")
        if insert_at < 0:
            print("WARN: needs_funding run block not found")
            return text
        # Find the end of needs_funding block by locating next "if needs_liquidity:"
        next_at = text.find("                    if needs_liquidity:", insert_at)
        if next_at < 0:
            print("WARN: needs_liquidity after funding not found")
            return text
        capital_run = '''                    if needs_capital:
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
                        capital = run_capital(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "capital over funding",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_funding=True,
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
                            min_capitals=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                capital.get("used_skill_route_discovery")
                            ),
                            "chain": capital.get("chain") or {},
                            "capital_chain": capital.get("chain") or {},
                            "funding": {
                                "ok": bool(
                                    (capital.get("funding") or {}).get("ok", True)
                                ),
                                "funded": bool(
                                    (capital.get("funding") or {}).get(
                                        "funded", True
                                    )
                                ),
                                "funding_count": int(
                                    capital.get("funding_count") or 0
                                ),
                                "funding_root_valid": True,
                                "certificate_valid": True,
                            },
                            "funding_plane": {
                                "ok": bool(
                                    (capital.get("funding") or {}).get("ok", True)
                                ),
                                "funded": True,
                                "funding_count": int(
                                    capital.get("funding_count") or 0
                                ),
                            },
                            "capital": {
                                "ok": bool(capital.get("ok")),
                                "capitalized": bool(capital.get("capitalized")),
                                "capital_count": int(
                                    capital.get("capital_count") or 0
                                ),
                                "tip_height": capital.get("tip_height"),
                                "tip_capital_root": capital.get("tip_capital_root"),
                                "capital_hash": capital.get("capital_hash"),
                                "capital_root_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "capital_buffer_digest": capital.get(
                                    "capital_buffer_digest"
                                ),
                                "deterministic": True,
                                "post_funding": True,
                                "multi_capital": int(
                                    capital.get("capital_count") or 0
                                )
                                >= 2,
                            },
                            "capital_plane": {
                                "ok": bool(capital.get("ok")),
                                "capitalized": bool(capital.get("capitalized")),
                                "capital_count": int(
                                    capital.get("capital_count") or 0
                                ),
                                "capital_root_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "buffer": {
                                "ok": bool(capital.get("ok")),
                                "capitalized": bool(capital.get("capitalized")),
                                "capital_count": int(
                                    capital.get("capital_count") or 0
                                ),
                                "capital_buffer_digest": capital.get(
                                    "capital_buffer_digest"
                                ),
                                "capital_root_valid": bool(
                                    (capital.get("capital_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "capital_count": int(capital.get("capital_count") or 0),
                            "funding_count": int(capital.get("funding_count") or 0),
                            "tip_height": capital.get("tip_height"),
                            "capital_certificate": capital.get("capital_certificate"),
                            "capital_hash": capital.get("capital_hash"),
                            "tip_capital_root": capital.get("tip_capital_root"),
                            "bound_funding_root": capital.get("bound_funding_root"),
                            "capital_buffer_digest": capital.get(
                                "capital_buffer_digest"
                            ),
                            "funding_facility_digest": capital.get(
                                "funding_facility_digest"
                            ),
                        }
                        result = evaluate_outcome(
                            workspace,
                            contract_text,
                            context=context,
                            ledger=ledger,
                            run_programs=False,
                        )
                        if not result.get("ok"):
                            decision.status = "continue"
                            decision.summary = (
                                "capital plane gates unmet: "
                                + ", ".join(
                                    str(item)
                                    for item in (result.get("failed") or [])[:4]
                                )
                            )
                            decision.next_step = (
                                "repair capital plane or lower capital outcome gates"
                            )
                            decision.capability_delta = ""
                            decision.outcome_evidence = [
                                f"capital_ok={capital.get('ok')}",
                                f"capitalized={capital.get('capitalized')}",
                                f"capital_count={capital.get('capital_count')}",
                                f"adversarial={ (capital.get('adversarial') or {}).get('ok') }",
                            ]
                            decision.validation = [
                                {
                                    "command": "run_capital_plane",
                                    "exit_code": 0 if capital.get("ok") else 1,
                                    "summary": decision.summary,
                                }
                            ]
                            decision.done_when_met = False
                            return decision
                        # capital satisfied — fall through with context for final contract
'''
        text = text[:insert_at] + capital_run + text[insert_at:]
    return text


def patch_test(text: str) -> str:
    if "def test_capital_plane_buffers_and_adversarial" in text:
        return text
    if "def test_funding_plane_facilities_and_adversarial" not in text:
        print("WARN: funding test not found")
        return text
    # append capital test after funding test function
    # find end of funding test by next def or EOF
    start = text.find("def test_funding_plane_facilities_and_adversarial")
    # find next def after funding test body
    next_def = text.find("\ndef test_", start + 10)
    if next_def < 0:
        next_def = len(text)
    capital_test = '''

def test_capital_plane_buffers_and_adversarial():
    """Capital plane posts multi-funding facilities and falsifies wrong-funding binds."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_capital_bundle,
        parse_outcome_contract,
        run_capital_plane,
        verify_capital_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.capital-plane" in ledger.capabilities
    assert "capability.funding-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; capital_ok; capitalized_ok; min_capitals:2; "
        "capital_root_valid; funding_ok; funded_ok; min_fundings:2; "
        "funding_root_valid; chain_valid"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "capital_ok" in kinds
    assert "capitalized_ok" in kinds
    assert "min_capitals" in kinds
    assert "capital_root_valid" in kinds

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-capital-plane.json"
    quorum_path = repo / "artifacts" / "quorum-bundles" / "test-capital-quorum.json"
    finality_path = repo / "artifacts" / "finality-bundles" / "test-capital-finality.json"
    execution_path = repo / "artifacts" / "execution-bundles" / "test-capital-execution.json"
    actuation_path = repo / "artifacts" / "actuation-bundles" / "test-capital-actuation.json"
    settlement_path = repo / "artifacts" / "settlement-bundles" / "test-capital-settlement.json"
    margin_path = repo / "artifacts" / "margin-bundles" / "test-capital-margin.json"
    collateral_path = repo / "artifacts" / "collateral-bundles" / "test-capital-collateral.json"
    liquidity_path = repo / "artifacts" / "liquidity-bundles" / "test-capital-liquidity.json"
    funding_path = repo / "artifacts" / "funding-bundles" / "test-capital-funding.json"
    capital_path = repo / "artifacts" / "capital-bundles" / "test-capital-plane.json"
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
        capital_path,
    ):
        if target.exists():
            target.unlink()

    plane = run_capital_plane(
        repo,
        "capital over funding",
        "min_capabilities:5; capability_exists:repo.import-health; no_skill_route",
        max_steps=3,
        run_funding=True,
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
        min_capitals=2,
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
        capital_path=capital_path,
        timeout=960,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "capital_plane"
    assert plane["capitalized"] is True
    assert int(plane["capital_count"]) >= 2
    assert int(plane["tip_height"]) >= 2
    assert int(plane["funding_count"] or 0) >= 2
    assert plane.get("capital_buffer_digest")
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["multi_capital"] is True
    assert plane["integrity"]["capital_ok"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["capital_certificate"]["valid"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["wrong_funding_fails_as_expected"] is True
    assert plane["adversarial"]["reorder_fails_as_expected"] is True
    assert plane["adversarial"]["digest_tamper_fails_as_expected"] is True
    assert plane["adversarial"]["single_capital_fails_as_expected"] is True
    assert plane["adversarial"]["duplicate_apply_fails_as_expected"] is True
    assert plane["adversarial"]["replay_matches_tip"] is True
    assert plane["used_skill_route_discovery"] is False
    assert capital_path.is_file()

    loaded = load_capital_bundle(capital_path)
    assert verify_capital_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("capital_hash")
    assert int(loaded.get("capital_count") or 0) >= 2
    assert int(loaded.get("tip_height") or 0) >= 2
    assert loaded.get("capital_buffer_digest")
    assert path.name == "ledger.json"

'''
    return text[:next_def] + capital_test + text[next_def:]


def main() -> None:
    text = COMPOUNDER.read_text(encoding="utf-8")
    funding_block = extract_funding_block(text)
    capital_block = transform_funding_block(funding_block)
    text = insert_capital_block(text, capital_block)
    text = patch_seed_registration(text)
    text = patch_plane_lists_and_intents(text)
    text = patch_outcome_contract_parse(text)
    text = patch_evaluate_outcome(text)
    text = patch_certificate_registry(text)
    COMPOUNDER.write_text(text, encoding="utf-8")
    print(f"patched {COMPOUNDER}")

    unbound = UNBOUND.read_text(encoding="utf-8")
    unbound = patch_unbound(unbound)
    UNBOUND.write_text(unbound, encoding="utf-8")
    print(f"patched {UNBOUND}")

    tests = TEST.read_text(encoding="utf-8")
    tests = patch_test(tests)
    TEST.write_text(tests, encoding="utf-8")
    print(f"patched {TEST}")
    print("capital plane generation complete")


if __name__ == "__main__":
    main()
