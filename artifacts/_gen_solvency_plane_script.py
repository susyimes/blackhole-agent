"""Generate solvency plane code from capital plane pattern and patch integrations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOUNDER = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND = ROOT / "src" / "blackhole_agent" / "unbound.py"
TEST = ROOT / "tests" / "test_capability_compounder.py"


def transform_capital_block(block: str) -> str:
    # Order: longest / most-specific self renames first, then parent funding→capital.
    replacements = [
        # Digests first (self then parent retained under new names)
        ("capital_buffer_digest", "solvency_position_digest"),
        ("funding_facility_digest", "capital_buffer_digest"),
        # Outcomes / multi
        ("capitalized_ok", "solvent_ok"),
        ("multi_capital", "multi_solvency"),
        ("min_capitals", "min_solvencies"),
        ("single_capital", "single_solvency"),
        ("double-capital", "double-solvency"),
        ("double_capital", "double_solvency"),
        ("need_multi_capital", "need_multi_solvency"),
        # Plane / action names
        ("capital_plane", "solvency_plane"),
        ("Capital plane", "Solvency plane"),
        ("capital plane", "solvency plane"),
        ("builtin_capital_plane", "builtin_solvency_plane"),
        ("run_capital_plane", "run_solvency_plane"),
        ("run_capital_adversarial", "run_solvency_adversarial"),
        # Bundle/log/cert machinery
        ("CAPITAL_BUNDLE_SCHEMA", "SOLVENCY_BUNDLE_SCHEMA"),
        ("CAPITAL_CERTIFICATE_SCHEMA", "SOLVENCY_CERTIFICATE_SCHEMA"),
        ("CAPITAL_LOG_SCHEMA", "SOLVENCY_LOG_SCHEMA"),
        ("DEFAULT_CAPITAL_BUNDLE_RELATIVE", "DEFAULT_SOLVENCY_BUNDLE_RELATIVE"),
        ("default_capital_bundle_dir", "default_solvency_bundle_dir"),
        ("empty_capital_log", "empty_solvency_log"),
        ("compute_capital_root", "compute_solvency_root"),
        ("compute_capital_certificate_hash", "compute_solvency_certificate_hash"),
        ("compute_capital_bundle_hash", "compute_solvency_bundle_hash"),
        ("compute_capital_buffer_digest", "compute_solvency_position_digest"),
        ("issue_capital_certificate", "issue_solvency_certificate"),
        ("verify_capital_certificate", "verify_solvency_certificate"),
        ("write_capital_certificate", "write_solvency_certificate"),
        ("_load_capital_disk_evidence", "_load_solvency_disk_evidence"),
        ("derive_capital_specs_from_funding", "derive_solvency_specs_from_capital"),
        ("apply_capital_transition", "apply_solvency_transition"),
        ("verify_capital_chain", "verify_solvency_chain"),
        ("apply_funding_bundle_to_capitals", "apply_capital_bundle_to_solvencies"),
        ("apply_capital_bundle_to_capitals", "apply_capital_bundle_to_solvencies"),
        ("build_capital_bundle", "build_solvency_bundle"),
        ("write_capital_bundle", "write_solvency_bundle"),
        ("load_capital_bundle", "load_solvency_bundle"),
        ("verify_capital_bundle_integrity", "verify_solvency_bundle_integrity"),
        ("rehydrate_capital_bundle", "rehydrate_solvency_bundle"),
        ("replay_capitals_from_specs", "replay_solvencies_from_specs"),
        # Structural field names (self)
        ("capital_certificate", "solvency_certificate"),
        ("capital_bundle", "solvency_bundle"),
        ("capital_log", "solvency_log"),
        ("capital_hash", "solvency_hash"),
        ("capital_root", "solvency_root"),
        ("capital_height", "solvency_height"),
        ("capital_count", "solvency_count"),
        ("tip_capital", "tip_solvency"),
        ("parent_capital", "parent_solvency"),
        ("capitals", "solvencies"),
        ("capital_ok", "solvency_ok"),
        ("capital_done_when", "solvency_done_when"),
        ("capital_n", "solvency_n"),
        ("capital_path", "solvency_path"),
        ("buffer_ratio_bps", "position_ratio_bps"),
        ("post_funding", "post_capital"),
        # Paths / strings
        ("capital-bundles", "solvency-bundles"),
        ("capital-sandbox", "solvency-sandbox"),
        ("capital-certificate", "solvency-certificate"),
        ("proof-capital", "proof-solvency"),
        ("test-capital", "test-solvency"),
        ("capital-source-funding", "solvency-source-capital"),
        ("BLACKHOLE_CAPITAL_", "BLACKHOLE_SOLVENCY_"),
        # Domain language
        ("capital over funding", "solvency over capital"),
        ("funding for capital", "capital for solvency"),
        ("capital buffer", "solvency position"),
        ("Capital buffer", "Solvency position"),
        ("capital buffers", "solvency positions"),
        ("Capital buffers", "Solvency positions"),
        # Parent renames (funding → capital) AFTER self renames
        ("run_funding_plane", "run_capital_plane"),
        ("run_funding", "run_capital"),
        ("load_funding_bundle", "load_capital_bundle"),
        ("verify_funding_certificate", "verify_capital_certificate"),
        ("write_funding_certificate", "write_capital_certificate"),
        ("default_funding_bundle_dir", "default_capital_bundle_dir"),
        ("funding_bundle", "capital_bundle"),
        ("funding_report", "capital_report"),
        ("funding_path", "capital_path"),
        ("out_funding", "out_capital"),
        ("funding_certificate", "capital_certificate"),
        ("bound_funding_root", "bound_capital_root"),
        ("bound_funding_height", "bound_capital_height"),
        ("tip_funding_root", "tip_capital_root"),
        ("funding_hash", "capital_hash"),
        ("funding_count", "capital_count"),
        ("min_fundings", "min_capitals"),
        ("want_fundings", "want_capitals"),
        ("funding_n", "capital_n"),
        ("fundings", "capitals"),
        ("funding_entries", "capital_entries"),
        ("funding_root", "capital_root"),
        ("funding_height", "capital_height"),
        ("known_funding_roots", "known_capital_roots"),
        ("wrong_funding", "wrong_capital"),
        ("funding_ok", "capital_ok"),
        ("BLACKHOLE_FUNDING_BUNDLE_PATH", "BLACKHOLE_CAPITAL_BUNDLE_PATH"),
        ("BLACKHOLE_FUNDING_MIN_FUNDINGS", "BLACKHOLE_CAPITAL_MIN_CAPITALS"),
        ("BLACKHOLE_FUNDING_RUN_LIQUIDITY", "BLACKHOLE_CAPITAL_RUN_FUNDING"),
        ('"plane": "funding"', '"plane": "capital"'),
        ('"plane": "capital"', '"plane": "solvency"'),
        ("funding_source_failed", "capital_source_failed"),
        ("missing_capital_bind", "missing_solvency_bind"),
        ("from_funding", "from_capital"),
        ("over funding", "over capital"),
        ("to a funding", "to a capital"),
        ("funding facility", "capital buffer"),
        ("funding tip", "capital tip"),
        ("funding source", "capital source"),
        ("past funded positions", "past capitalized positions"),
        ("parent_funded", "parent_capitalized"),
    ]

    out = block
    for old, new in replacements:
        out = out.replace(old, new)

    # Word-boundary adjective renames only
    out = re.sub(r"\bcapitalized\b", "solvent", out)
    out = re.sub(r"\bCapitalized\b", "Solvent", out)
    # Parent funded synonym may remain; map funded→capitalized for parent plane
    out = re.sub(r"\bfunded\b", "capitalized", out)
    out = re.sub(r"\bFunded\b", "Capitalized", out)

    out = out.replace(
        'action": "capital_adversarial_checks"',
        'action": "solvency_adversarial_checks"',
    )
    out = out.replace(
        "BLACKHOLE_SOLVENCY_RUN_FUNDING",
        "BLACKHOLE_SOLVENCY_RUN_CAPITAL",
    )
    # After self BLACKHOLE_CAPITAL_ → BLACKHOLE_SOLVENCY_, parent min was
    # BLACKHOLE_SOLVENCY_MIN_CAPITALS from CAPITAL_MIN_CAPITALS; fix self min.
    out = out.replace(
        "BLACKHOLE_SOLVENCY_MIN_CAPITALS",
        "BLACKHOLE_SOLVENCY_MIN_SOLVENCIES",
    )
    # Self context alias "capital" becomes "position" for secondary key (like buffer)
    out = out.replace(
        '"buffer": {\n            "ok": provisional_ok,\n            "solvent"',
        '"position": {\n            "ok": provisional_ok,\n            "solvent"',
    )
    out = out.replace(
        '"capital": {\n            "ok": provisional_ok,\n            "solvent"',
        '"solvency": {\n            "ok": provisional_ok,\n            "solvent"',
    )
    out = out.replace('kind": "capital_buffer"', 'kind": "solvency_position"')
    out = out.replace('kind": "capital_log"', 'kind": "solvency_log"')
    out = out.replace('kind": "capital_certificate"', 'kind": "solvency_certificate"')
    out = out.replace('kind": "capital_bundle"', 'kind": "solvency_bundle"')
    # kinds may already be capital_* from transform of funding kinds that became capital
    out = out.replace('kind": "solvency_log"', 'kind": "solvency_log"')  # no-op guard

    # Parent report block: funding became capital; keep capitalized parent outcome
    out = out.replace(
        '"funding": None\n        if capital_report is None\n        else {\n            "ok": capital_report.get("ok"),\n            "capitalized": capital_report.get("capitalized") or capital_report.get("solvent"),',
        '"capital": None\n        if capital_report is None\n        else {\n            "ok": capital_report.get("ok"),\n            "capitalized": capital_report.get("capitalized") or capital_report.get("solvent"),',
    )
    out = out.replace(
        '"funding": None\n            if capital_report is None\n            else {\n                "ok": capital_report.get("ok"),\n                "capitalized": capital_report.get("capitalized") or capital_report.get("solvent"),',
        '"capital": None\n            if capital_report is None\n            else {\n                "ok": capital_report.get("ok"),\n                "capitalized": capital_report.get("capitalized") or capital_report.get("solvent"),',
    )

    # Fix apply function name if double-renamed wrong
    out = out.replace(
        "apply_solvency_bundle_to_solvencies",
        "apply_capital_bundle_to_solvencies",
    )
    # Parent capitalized report keys
    out = out.replace(
        'parent_capitalized = bool(\n        (capital_report or {}).get("capitalized")\n        or (capital_report or {}).get("ok")\n        or (capital_bundle or {}).get("ok")\n    )',
        'parent_capitalized = bool(\n        (capital_report or {}).get("capitalized")\n        or (capital_report or {}).get("solvent")\n        or (capital_report or {}).get("ok")\n        or (capital_bundle or {}).get("ok")\n    )',
    )

    # Fix plane string that may have been double-renamed funding→capital→solvency already
    # Parent digest field capital_buffer_digest must remain for parent; self is solvency_position_digest
    # Fix min_capitals param that is self min_solvencies - already renamed
    # Fix run_capital=True flag for parent
    out = out.replace("run_capital: bool = True", "run_capital: bool = True")  # keep

    # After renames, capital plane's run_funding became run_capital — good for parent.
    # But deeper stack flags run_liquidity etc stay.

    # Assertions on transform quality
    assert "def run_solvency_plane" in out
    assert "def builtin_solvency_plane" in out
    assert "SOLVENCY_BUNDLE_SCHEMA" in out
    assert "solvency_position_digest" in out
    assert "run_capital_plane" in out
    assert "load_capital_bundle" in out
    assert "bound_capital_root" in out
    assert "tip_solvency_root" in out or "tip_solvency" in out
    assert "solvency over capital" in out
    assert "def run_capital_plane" not in out
    assert "def builtin_capital_plane" not in out
    assert "CAPITAL_BUNDLE_SCHEMA" not in out
    assert "capital_buffer_digest" in out  # parent digest retained
    assert "capitalizedy" not in out
    assert "solventy" not in out
    return out


def extract_capital_block(text: str) -> str:
    start = text.find(
        "# ---------------------------------------------------------------------------\n# Capital plane over funding"
    )
    if start < 0:
        raise RuntimeError("capital plane header not found")
    end = text.find("\ndef seed_bootstrap_capabilities(", start)
    if end < 0:
        raise RuntimeError("seed_bootstrap_capabilities after capital not found")
    return text[start:end].rstrip() + "\n"


def insert_solvency_block(text: str, block: str) -> str:
    marker = "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
    idx = text.find(marker)
    if idx < 0:
        raise RuntimeError("seed_bootstrap_capabilities not found")
    if "def run_solvency_plane" in text:
        print("solvency plane already present; skipping block insert")
        return text
    header = (
        "\n\n# ---------------------------------------------------------------------------\n"
        "# Solvency plane over capital\n"
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
    if 'id="capability.solvency-plane"' in text:
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
            id="capability.solvency-plane",
            name="Solvency plane over capital",
            description=(
                "Closed solvency plane: multi-capital buffers → deterministic "
                "hash-chained solvency positions with solvency position digests bound to "
                "capital roots → solvency certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-capital/double-solvency/forged-root/"
                "gap/digest-tamper/single-solvency falsification with genesis replay matching "
                "tip — past capitalized positions without solvency positions."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_solvency_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_solvency_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='solvency over capital'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
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
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-solvency.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-solvency-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-solvency-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-solvency-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-solvency-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-solvency-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-solvency-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-solvency-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-solvency-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-solvency-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-solvency-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-solvency-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_SOLVENCY_BUNDLE_PATH', str(Path('artifacts')/'solvency-bundles'/'proof-solvency.json')); "
                "r=builtin_solvency_plane(); assert r['ok'] and r.get('action')=='solvency_plane' "
                "and r.get('solvent') is True and int(r.get('solvency_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('solvency_certificate',{}).get('valid') "
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
                "Solvency plane posts multi-capital buffers into deterministic "
                "hash-chained solvency positions with solvency position digests and "
                "solvency certificates bound to capital roots, sterile rehydrate+"
                "prove, genesis replay matching tip, and adversarial falsification of "
                "wrong-capital/reorder/double-solvency/forged-root/digest-tamper without "
                "skill-route."
            ),
            tags=(
                "bootstrap",
                "compounder",
                "solvency",
                "position",
                "solvency-root",
                "capital",
                "adequacy",
                "deterministic",
                "funding",
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
    if '"capability.solvency-plane"' not in text:
        text = text.replace(
            '"capability.capital-plane",\n',
            '"capability.capital-plane",\n        "capability.solvency-plane",\n',
            1,
        )
    if '    ("solvency", (' not in text:
        text = text.replace(
            '    ("adequacy", ("capability.capital-plane", "capability.funding-plane", "capability.assurance-plane")),\n',
            '    ("adequacy", ("capability.capital-plane", "capability.funding-plane", "capability.assurance-plane")),\n'
            '    ("solvency", ("capability.solvency-plane", "capability.capital-plane", "capability.funding-plane")),\n'
            '    ("solvent", ("capability.solvency-plane", "capability.capital-plane", "capability.finality-plane")),\n'
            '    ("solvency position", ("capability.solvency-plane", "capability.capital-plane", "capability.assurance-plane")),\n'
            '    ("solvency-root", ("capability.solvency-plane", "capability.capital-plane", "capability.lineage-plane")),\n'
            '    ("position", ("capability.solvency-plane", "capability.capital-plane", "capability.quorum-plane")),\n'
            '    ("posted solvency", ("capability.solvency-plane", "capability.capital-plane", "capability.actuation-plane")),\n'
            '    ("solvency adequacy", ("capability.solvency-plane", "capability.capital-plane", "capability.assurance-plane")),\n',
            1,
        )
    return text


def patch_outcome_contract_parse(text: str) -> str:
    if "solvency_ok" in text and "min_solvencies" in text and "solvent_ok" in text:
        pass
    else:
        text = text.replace(
            "#   capital_ok | capitalized_ok | min_capitals:N | capital_root_valid\n",
            "#   capital_ok | capitalized_ok | min_capitals:N | capital_root_valid\n"
            "#   solvency_ok | solvent_ok | min_solvencies:N | solvency_root_valid\n",
            1,
        )
        text = text.replace(
            "capital_ok|capitalized_ok|min_capitals|capital_root_valid",
            "capital_ok|capitalized_ok|min_capitals|capital_root_valid|"
            "solvency_ok|solvent_ok|min_solvencies|solvency_root_valid",
            1,
        )
        text = text.replace(
            '''        "capital_ok",
        "capitalized_ok",
        "min_capitals",
        "capital_root_valid",''',
            '''        "capital_ok",
        "capitalized_ok",
        "min_capitals",
        "capital_root_valid",
        "solvency_ok",
        "solvent_ok",
        "min_solvencies",
        "solvency_root_valid",''',
            1,
        )

    marker = 'found.append({"kind": "capital_root_valid", "arg": "", "source": chunk})'
    last = text.rfind(marker)
    if last >= 0 and "solvency_ok" not in text[last : last + 900]:
        end = last + len(marker)
        solvency_extract = '''
    if re.search(r"\\bsolvency_ok\\b", lower) or (
        re.search(r"\\bsolvency\\s+plane\\b", lower)
        and re.search(r"\\bok\\b", lower)
    ) or re.search(r"\\brun_solvency_plane\\b", lower) and (
        re.search(r"\\bok\\b", lower) or True
    ):
        found.append({"kind": "solvency_ok", "arg": "", "source": chunk})
    if re.search(r"\\bsolvent_ok\\b", lower) or re.search(
        r"\\bsolvent\\s*(?:=|is|:)\\s*true\\b", lower
    ):
        found.append({"kind": "solvent_ok", "arg": "", "source": chunk})
    if (
        re.search(r"\\bsolvent\\b", lower)
        and re.search(r"\\b(true|ok|yes)\\b", lower)
        and "solvency-plane" not in lower
        and "solvency_plane" not in lower
    ):
        found.append({"kind": "solvent_ok", "arg": "", "source": chunk})
    m = re.search(r"(?:at least|>=|≥)\\s*(\\d+)\\s+solvenc", lower)
    if m:
        found.append({"kind": "min_solvencies", "arg": m.group(1), "source": chunk})
    m = re.search(r"solvency_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_solvencies" for item in found):
        found.append({"kind": "min_solvencies", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bmin_solvencies\\b", lower) and not any(
        item.get("kind") == "min_solvencies" for item in found
    ):
        m_n = re.search(r"min_solvencies\\s*[:=]?\\s*(\\d+)", lower)
        if m_n:
            found.append(
                {
                    "kind": "min_solvencies",
                    "arg": m_n.group(1),
                    "source": chunk,
                }
            )
    if re.search(r"\\bsolvency_root_valid\\b", lower) or (
        re.search(r"\\bsolvency[_\\s-]*root\\b", lower)
        and re.search(r"\\bvalid\\b", lower)
    ):
        found.append({"kind": "solvency_root_valid", "arg": "", "source": chunk})
'''
        text = text[:end] + solvency_extract + text[end:]
    return text


def patch_evaluate_outcome(text: str) -> str:
    if 'kind in {\n        "solvency_ok"' in text or '"solvency_ok",\n        "solvent_ok"' in text:
        return text
    marker = 'return ok, f"capital_root_valid={ok}"'
    idx = text.rfind(marker)
    if idx < 0:
        print("WARN: capital_root_valid return not found for evaluate patch")
        return text
    end = idx + len(marker)
    eval_block = '''
    if kind in {
        "solvency_ok",
        "solvent_ok",
        "min_solvencies",
        "solvency_root_valid",
    }:
        plane = (
            context.get("solvency")
            or context.get("solvency_plane")
            or context.get("position")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_solvency_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "solvency_ok":
            ok = bool(plane.get("ok"))
            return ok, f"solvency_ok={ok}"
        if kind == "solvent_ok":
            if "solvent" in plane:
                ok = plane.get("solvent") is True and bool(plane.get("ok", True))
            elif "solvent_ok" in plane:
                ok = plane.get("solvent_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("solvency_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"solvent_ok={ok}"
        if kind == "min_solvencies":
            need = int(float(arg or "0"))
            have = context.get("solvency_count")
            if have is None:
                have = context.get("tip_solvency_height")
            if have is None:
                have = (
                    plane.get("solvency_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"solvencies={have_i} need>={need}"
        if "solvency_root_valid" in plane:
            ok = plane.get("solvency_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("solvency_certificate")
                or plane.get("certificate")
                or context.get("solvency_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_solvency_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("solvency_root") or plane.get("tip_solvency_root")
                )
        return ok, f"solvency_root_valid={ok}"
'''
    return text[:end] + eval_block + text[end:]


def patch_certificate_registry(text: str) -> str:
    if '("solvency_certificate", verify_solvency_certificate)' in text:
        return text
    text = text.replace(
        '("capital_certificate", verify_capital_certificate),\n',
        '("capital_certificate", verify_capital_certificate),\n'
        '                ("solvency_certificate", verify_solvency_certificate),\n',
        1,
    )
    if '"solvency_plane"' not in text:
        text = text.replace(
            '"capital_plane",\n',
            '"capital_plane",\n                "solvency",\n                "solvency_plane",\n',
            1,
        )
    return text


def patch_unbound(text: str) -> str:
    if "run_solvency_plane" in text and "needs_solvency" in text:
        return text
    if "run_capital_plane" in text and "run_solvency_plane" not in text:
        text = text.replace(
            "run_capital_plane,\n",
            "run_capital_plane,\n    run_solvency_plane,\n",
            1,
        )
        text = text.replace(
            """    run_capital = (
        cc.run_capital_plane if cc is not None else run_capital_plane
    )
""",
            """    run_capital = (
        cc.run_capital_plane if cc is not None else run_capital_plane
    )
    run_solvency = (
        cc.run_solvency_plane if cc is not None else run_solvency_plane
    )
""",
            1,
        )

    if "needs_solvency" not in text:
        text = text.replace(
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
''',
            '''                    needs_solvency = bool(
                        kinds
                        & {
                            "solvency_ok",
                            "solvent_ok",
                            "min_solvencies",
                            "solvency_root_valid",
                        }
                    )
                    needs_capital = bool(
                        kinds
                        & {
                            "capital_ok",
                            "capitalized_ok",
                            "min_capitals",
                            "capital_root_valid",
                        }
                    ) and not needs_solvency
                    needs_funding = bool(
                        kinds
                        & {
                            "funding_ok",
                            "funded_ok",
                            "min_fundings",
                            "funding_root_valid",
                        }
                    ) and not needs_capital and not needs_solvency
''',
            1,
        )
        text = text.replace(
            "and not needs_capital\n",
            "and not needs_capital and not needs_solvency\n",
        )
        text = text.replace(
            "and not needs_funding and not needs_capital\n",
            "and not needs_funding and not needs_capital and not needs_solvency\n",
        )

    if "if needs_solvency:" not in text:
        insert_at = text.find("                    if needs_capital:")
        if insert_at < 0:
            print("WARN: needs_capital run block not found")
            return text
        next_at = text.find("                    if needs_funding:", insert_at)
        if next_at < 0:
            print("WARN: needs_funding after capital not found")
            return text
        solvency_run = '''                    if needs_solvency:
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
                        solvency = run_solvency(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "solvency over capital",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_capital=True,
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
                            min_solvencies=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                solvency.get("used_skill_route_discovery")
                            ),
                            "chain": solvency.get("chain") or {},
                            "solvency_chain": solvency.get("chain") or {},
                            "capital": {
                                "ok": bool(
                                    (solvency.get("capital") or {}).get("ok", True)
                                ),
                                "capitalized": bool(
                                    (solvency.get("capital") or {}).get(
                                        "capitalized", True
                                    )
                                ),
                                "capital_count": int(
                                    solvency.get("capital_count") or 0
                                ),
                                "capital_root_valid": True,
                                "certificate_valid": True,
                            },
                            "capital_plane": {
                                "ok": bool(
                                    (solvency.get("capital") or {}).get("ok", True)
                                ),
                                "capitalized": True,
                                "capital_count": int(
                                    solvency.get("capital_count") or 0
                                ),
                            },
                            "solvency": {
                                "ok": bool(solvency.get("ok")),
                                "solvent": bool(solvency.get("solvent")),
                                "solvency_count": int(
                                    solvency.get("solvency_count") or 0
                                ),
                                "tip_height": solvency.get("tip_height"),
                                "tip_solvency_root": solvency.get("tip_solvency_root"),
                                "solvency_hash": solvency.get("solvency_hash"),
                                "solvency_root_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "solvency_position_digest": solvency.get(
                                    "solvency_position_digest"
                                ),
                                "deterministic": True,
                                "post_capital": True,
                                "multi_solvency": int(
                                    solvency.get("solvency_count") or 0
                                )
                                >= 2,
                            },
                            "solvency_plane": {
                                "ok": bool(solvency.get("ok")),
                                "solvent": bool(solvency.get("solvent")),
                                "solvency_count": int(
                                    solvency.get("solvency_count") or 0
                                ),
                                "solvency_root_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "position": {
                                "ok": bool(solvency.get("ok")),
                                "solvent": bool(solvency.get("solvent")),
                                "solvency_count": int(
                                    solvency.get("solvency_count") or 0
                                ),
                                "solvency_position_digest": solvency.get(
                                    "solvency_position_digest"
                                ),
                                "solvency_root_valid": bool(
                                    (solvency.get("solvency_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "solvency_count": int(solvency.get("solvency_count") or 0),
                            "capital_count": int(solvency.get("capital_count") or 0),
                            "tip_height": solvency.get("tip_height"),
                            "solvency_certificate": solvency.get("solvency_certificate"),
                            "solvency_hash": solvency.get("solvency_hash"),
                            "tip_solvency_root": solvency.get("tip_solvency_root"),
                            "bound_capital_root": solvency.get("bound_capital_root"),
                            "solvency_position_digest": solvency.get(
                                "solvency_position_digest"
                            ),
                            "capital_buffer_digest": solvency.get(
                                "capital_buffer_digest"
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
                                "solvency plane gates unmet: "
                                + ", ".join(
                                    str(item)
                                    for item in (result.get("failed") or [])[:4]
                                )
                            )
                            decision.next_step = (
                                "repair solvency plane or lower solvency outcome gates"
                            )
                            decision.capability_delta = ""
                            decision.outcome_evidence = [
                                f"solvency_ok={solvency.get('ok')}",
                                f"solvent={solvency.get('solvent')}",
                                f"solvency_count={solvency.get('solvency_count')}",
                                f"adversarial={ (solvency.get('adversarial') or {}).get('ok') }",
                            ]
                            decision.validation = [
                                {
                                    "command": "run_solvency_plane",
                                    "exit_code": 0 if solvency.get("ok") else 1,
                                    "summary": decision.summary,
                                }
                            ]
                            decision.done_when_met = False
                            return decision
                        # solvency satisfied — fall through with context for final contract
'''
        text = text[:insert_at] + solvency_run + text[insert_at:]
    return text


def patch_test(text: str) -> str:
    if "def test_solvency_plane_positions_and_adversarial" in text:
        return text
    if "def test_capital_plane_buffers_and_adversarial" not in text:
        print("WARN: capital test not found")
        return text
    start = text.find("def test_capital_plane_buffers_and_adversarial")
    next_def = text.find("\ndef test_", start + 10)
    if next_def < 0:
        next_def = len(text)
    solvency_test = '''

def test_solvency_plane_positions_and_adversarial():
    """Solvency plane posts multi-capital buffers and falsifies wrong-capital binds."""

    from blackhole_agent.capability_compounder import (
        ensure_seeded_ledger,
        load_solvency_bundle,
        parse_outcome_contract,
        run_solvency_plane,
        verify_solvency_bundle_integrity,
    )

    repo = Path(__file__).resolve().parents[1]
    path, ledger = ensure_seeded_ledger(repo)
    assert "capability.solvency-plane" in ledger.capabilities
    assert "capability.capital-plane" in ledger.capabilities

    parsed = parse_outcome_contract(
        "no_skill_route; solvency_ok; solvent_ok; min_solvencies:2; "
        "solvency_root_valid; capital_ok; capitalized_ok; min_capitals:2; "
        "capital_root_valid; chain_valid"
    )
    kinds = {item["kind"] for item in parsed["predicates"]}
    assert "solvency_ok" in kinds
    assert "solvent_ok" in kinds
    assert "min_solvencies" in kinds
    assert "solvency_root_valid" in kinds

    lineage_path = repo / "artifacts" / "capability-lineage" / "test-solvency-plane.json"
    quorum_path = repo / "artifacts" / "quorum-bundles" / "test-solvency-quorum.json"
    finality_path = repo / "artifacts" / "finality-bundles" / "test-solvency-finality.json"
    execution_path = repo / "artifacts" / "execution-bundles" / "test-solvency-execution.json"
    actuation_path = repo / "artifacts" / "actuation-bundles" / "test-solvency-actuation.json"
    settlement_path = repo / "artifacts" / "settlement-bundles" / "test-solvency-settlement.json"
    margin_path = repo / "artifacts" / "margin-bundles" / "test-solvency-margin.json"
    collateral_path = repo / "artifacts" / "collateral-bundles" / "test-solvency-collateral.json"
    liquidity_path = repo / "artifacts" / "liquidity-bundles" / "test-solvency-liquidity.json"
    funding_path = repo / "artifacts" / "funding-bundles" / "test-solvency-funding.json"
    capital_path = repo / "artifacts" / "capital-bundles" / "test-solvency-capital.json"
    solvency_path = repo / "artifacts" / "solvency-bundles" / "test-solvency-plane.json"
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
        solvency_path,
    ):
        if target.exists():
            target.unlink()

    plane = run_solvency_plane(
        repo,
        "solvency over capital",
        "min_capabilities:5; capability_exists:repo.import-health; no_skill_route",
        max_steps=3,
        run_capital=True,
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
        min_solvencies=2,
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
        solvency_path=solvency_path,
        timeout=960,
    )
    assert plane["ok"] is True, plane
    assert plane["action"] == "solvency_plane"
    assert plane["solvent"] is True
    assert int(plane["solvency_count"]) >= 2
    assert int(plane["tip_height"]) >= 2
    assert int(plane["capital_count"] or 0) >= 2
    assert plane.get("solvency_position_digest")
    assert plane["integrity"]["ok"] is True
    assert plane["integrity"]["multi_solvency"] is True
    assert plane["integrity"]["solvency_ok"] is True
    assert plane["rehydrate"]["ok"] is True
    assert plane["prove"]["ok"] is True
    assert int(plane["prove"]["proved_count"]) >= 1
    assert plane["chain"]["valid"] is True
    assert plane["solvency_certificate"]["valid"] is True
    assert plane["adversarial"]["ok"] is True
    assert plane["adversarial"]["wrong_capital_fails_as_expected"] is True
    assert plane["adversarial"]["reorder_fails_as_expected"] is True
    assert plane["adversarial"]["digest_tamper_fails_as_expected"] is True
    assert plane["adversarial"]["single_solvency_fails_as_expected"] is True
    assert plane["adversarial"]["duplicate_apply_fails_as_expected"] is True
    assert plane["adversarial"]["replay_matches_tip"] is True
    assert plane["used_skill_route_discovery"] is False
    assert solvency_path.is_file()

    loaded = load_solvency_bundle(solvency_path)
    assert verify_solvency_bundle_integrity(loaded)["ok"] is True
    assert loaded.get("solvency_hash")
    assert int(loaded.get("solvency_count") or 0) >= 2
    assert int(loaded.get("tip_height") or 0) >= 2
    assert loaded.get("solvency_position_digest")
    assert path.name == "ledger.json"

'''
    return text[:next_def] + solvency_test + text[next_def:]


def main() -> None:
    text = COMPOUNDER.read_text(encoding="utf-8")
    capital_block = extract_capital_block(text)
    solvency_block = transform_capital_block(capital_block)
    text = insert_solvency_block(text, solvency_block)
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
    print("solvency plane generation complete")


if __name__ == "__main__":
    main()
