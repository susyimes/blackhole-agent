"""Fix generated risk plane block and insert into capability_compounder.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
BLOCK = ROOT / "artifacts" / "_gen_risk_plane_block.py"


def fix_block(block: str) -> str:
    fixes = [
        ("apply_risk_bundle_to_risks", "apply_solvency_bundle_to_risks"),
        ("derive_risk_specs_from_risk", "derive_risk_specs_from_solvency"),
        ("BLACKHOLE_RISK_MIN_SOLVENCIES", "BLACKHOLE_RISK_MIN_RISKS"),
        (
            'solvency_report.get("solvency")\n                or solvency_report.get("funding")',
            'solvency_report.get("capital")\n                or solvency_report.get("solvency")\n                or solvency_report.get("funding")',
        ),
        (
            "max_steps=max_steps,\n            run_liquidity=run_liquidity,",
            "max_steps=max_steps,\n            run_capital=run_solvency,\n            run_liquidity=run_liquidity,",
        ),
        (
            "max_steps=max_steps,\n                run_liquidity=run_liquidity,",
            "max_steps=max_steps,\n                run_capital=True,\n                run_liquidity=run_liquidity,",
        ),
    ]
    for old, new in fixes:
        if old not in block:
            print("MISSING", repr(old[:80]))
        else:
            block = block.replace(old, new)
            print("fixed", repr(old[:60]))
    return block


def insert_outcome_predicates(text: str) -> str:
    """Add risk_ok / risked_ok / min_risks / risk_root_valid next to solvency predicates."""
    # parse_outcome_contract section — after solvency_root_valid
    solvency_root_parse = '''    if re.search(r"\\bsolvency_root_valid\\b", lower) or (
'''
    # Find solvency parse block end and insert risk parse after min_solvencies / solvency_root_valid block
    marker = 'found.append({"kind": "solvency_root_valid", "arg": "", "source": chunk})'
    if "kind\": \"risk_ok\"" in text or 'kind": "risk_ok"' in text:
        print("outcome parse risk already present")
    elif marker not in text:
        print("WARN: solvency_root_valid parse marker missing")
    else:
        insert = '''
    if re.search(r"\\brisk_ok\\b", lower) or (
        re.search(r"\\brun_risk_plane\\b", lower) and (
            "risk" in lower or "assessment" in lower
        )
    ):
        found.append({"kind": "risk_ok", "arg": "", "source": chunk})
    if re.search(r"\\brisked_ok\\b", lower) or re.search(
        r"\\brisked\\b", lower
    ) and (
        "risk" in lower
        and "risk-plane" not in lower
        and "risk_plane" not in lower
    ):
        found.append({"kind": "risked_ok", "arg": "", "source": chunk})
    if re.search(r"\\brisked\\b", lower) and not any(
        item.get("kind") == "risked_ok" for item in found
    ):
        found.append({"kind": "risked_ok", "arg": "", "source": chunk})
    m = re.search(r"min_risks\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_risks", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?risks?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_risks" for item in found):
        found.append({"kind": "min_risks", "arg": m.group(1), "source": chunk})
    if re.search(r"\\bmin_risks\\b", lower) and not any(
        item.get("kind") == "min_risks" for item in found
    ):
        m_n = re.search(r"min_risks\\s*[:=]?\\s*(\\d+)", lower)
        if m_n:
            found.append(
                {
                    "kind": "min_risks",
                    "arg": m_n.group(1),
                    "source": chunk,
                }
            )
    if re.search(r"\\brisk_root_valid\\b", lower) or (
        re.search(r"\\brisk_root\\b", lower) and "valid" in lower
    ):
        found.append({"kind": "risk_root_valid", "arg": "", "source": chunk})
'''
        text = text.replace(marker, marker + "\n" + insert, 1)
        print("inserted outcome parse predicates")

    # evaluate_outcome_contract kinds list and handlers
    kinds_marker = '''        "solvency_ok",
        "solvent_ok",
        "min_solvencies",
        "solvency_root_valid",'''
    if '"risk_ok"' in text and "min_risks" in text[text.find("def evaluate_outcome_contract"):text.find("def evaluate_outcome_contract")+5000]:
        # may already exist
        pass
    if kinds_marker in text and '"risk_ok",' not in text.split(kinds_marker)[1][:200]:
        text = text.replace(
            kinds_marker,
            kinds_marker
            + '''
        "risk_ok",
        "risked_ok",
        "min_risks",
        "risk_root_valid",''',
            1,
        )
        print("inserted kinds list")

    # Handler after solvency_root_valid handler — find return for solvency_root_valid
    handler_marker = 'return ok, f"solvency_root_valid={ok}"'
    if 'return ok, f"risk_ok={ok}"' in text:
        print("handlers already present")
    elif handler_marker not in text:
        print("WARN: solvency_root_valid handler missing")
    else:
        handler = '''
    if kind == "risk_ok":
        plane = context.get("risk") or context.get("risk_plane") or {}
        ok = plane.get("ok") is True
        return ok, f"risk_ok={ok}"
    if kind == "risked_ok":
        plane = context.get("risk") or context.get("risk_plane") or {}
        if "risked" in plane:
            ok = plane.get("risked") is True
        elif "risked_ok" in plane:
            ok = plane.get("risked_ok") is True
        else:
            ok = plane.get("ok") is True and int(plane.get("risk_count") or 0) >= 2
        return ok, f"risked_ok={ok}"
    if kind == "min_risks":
        plane = context.get("risk") or context.get("risk_plane") or {}
        need = int(arg or 2)
        have = int(
            plane.get("risk_count")
            or context.get("risk_count")
            or 0
        )
        ok = have >= need
        return ok, f"min_risks={have}>={need}"
    if kind == "risk_root_valid":
        plane = context.get("risk") or context.get("risk_plane") or context.get("assessment") or {}
        if "risk_root_valid" in plane:
            ok = plane.get("risk_root_valid") is True
        else:
            ok = bool(plane.get("certificate_valid") or plane.get("ok"))
        return ok, f"risk_root_valid={ok}"
'''
        # Need to insert inside the evaluate function - the solvency handler may be inside a block
        # Find with more context from evaluate
        text = text.replace(handler_marker, handler_marker + "\n" + handler, 1)
        print("inserted outcome handlers")

    # disk evidence load in evaluate for solvency - also add risk disk load if pattern exists
    return text


def insert_scout_keywords(text: str) -> str:
    marker = '("solvency", ("capability.solvency-plane", "capability.capital-plane", "capability.funding-plane")),'
    if "capability.risk-plane" in text and '("risk",' in text:
        print("scout keywords likely present")
        return text
    if marker not in text:
        # try alternate
        marker2 = '    ("solvency", ("capability.solvency-plane"'
        idx = text.find(marker2)
        if idx < 0:
            print("WARN: scout solvency marker missing")
            return text
        # find end of solvency-related scout block (several lines)
        end = text.find("\n    (", idx + 1)
        # insert before solvency block
        insert = '''    ("risk", ("capability.risk-plane", "capability.solvency-plane", "capability.capital-plane")),
    ("risked", ("capability.risk-plane", "capability.solvency-plane", "capability.finality-plane")),
    ("risk assessment", ("capability.risk-plane", "capability.solvency-plane", "capability.assurance-plane")),
    ("risk-root", ("capability.risk-plane", "capability.solvency-plane", "capability.lineage-plane")),
    ("assessment", ("capability.risk-plane", "capability.solvency-plane", "capability.quorum-plane")),
    ("posted risk", ("capability.risk-plane", "capability.solvency-plane", "capability.actuation-plane")),
    ("risk adequacy", ("capability.risk-plane", "capability.solvency-plane", "capability.assurance-plane")),
'''
        text = text[:idx] + insert + text[idx:]
        print("inserted scout keywords")
        return text
    insert = '''    ("risk", ("capability.risk-plane", "capability.solvency-plane", "capability.capital-plane")),
    ("risked", ("capability.risk-plane", "capability.solvency-plane", "capability.finality-plane")),
    ("risk assessment", ("capability.risk-plane", "capability.solvency-plane", "capability.assurance-plane")),
    ("risk-root", ("capability.risk-plane", "capability.solvency-plane", "capability.lineage-plane")),
    ("assessment", ("capability.risk-plane", "capability.solvency-plane", "capability.quorum-plane")),
    ("posted risk", ("capability.risk-plane", "capability.solvency-plane", "capability.actuation-plane")),
    ("risk adequacy", ("capability.risk-plane", "capability.solvency-plane", "capability.assurance-plane")),
'''
    text = text.replace(marker, insert + marker, 1)
    print("inserted scout keywords")
    return text


def insert_seed_capability(text: str) -> str:
    if 'id="capability.risk-plane"' in text:
        print("seed already present")
        return text
    # Insert after solvency-plane Capability( ... ),
    # Find capability.solvency-plane seed and append risk after it closes
    start = text.find('id="capability.solvency-plane"')
    if start < 0:
        print("WARN: solvency seed missing")
        return text
    # Find the Capability( that contains this id — search backwards
    cap_start = text.rfind("Capability(", 0, start)
    # Find matching close of Capability( — count parens from cap_start
    depth = 0
    i = cap_start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                # include trailing comma/newline
                end = i + 1
                if end < len(text) and text[end] == ",":
                    end += 1
                break
        i += 1
    else:
        print("WARN: could not find end of solvency Capability")
        return text

    seed = '''
        Capability(
            id="capability.risk-plane",
            name="Risk plane over solvency",
            description=(
                "Closed risk plane: multi-solvency positions → deterministic "
                "hash-chained risk assessments with risk assessment digests bound to "
                "solvency roots → risk certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-solvency/double-risk/forged-root/"
                "gap/digest-tamper/single-risk falsification with genesis replay matching "
                "tip — past solvent positions without risk assessments."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_risk_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_risk_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='risk over solvency'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
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
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-risk.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-risk-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-risk-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-risk-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-risk-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-risk-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-risk-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-risk-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-risk-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-risk-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-risk-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-risk-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_SOLVENCY_BUNDLE_PATH', str(Path('artifacts')/'solvency-bundles'/'proof-risk-solvency.json')); "
                "os.environ.setdefault('BLACKHOLE_RISK_BUNDLE_PATH', str(Path('artifacts')/'risk-bundles'/'proof-risk.json')); "
                "r=builtin_risk_plane(); assert r['ok'] and r.get('action')=='risk_plane' "
                "and r.get('risked') is True and int(r.get('risk_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('risk_certificate',{}).get('valid') "
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
                "capability.transfer-plane",
                "capability.ablation-proof",
                "capability.adversarial-contract",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
            ),
            capability_delta=(
                "Risk plane posts multi-solvency positions into deterministic hash-chained "
                "risk assessments with risk assessment digests bound to solvency roots, "
                "risk certificates, sterile rehydrate+prove, and adversarial falsification "
                "without skill-route discovery."
            ),
            tags=(
                "risk",
                "assessment",
                "solvency",
                "plane",
                "certificate",
                "adversarial",
                "hash-chain",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
'''
    text = text[:end] + "\n" + seed + text[end:]
    print("inserted seed capability")
    return text


def main() -> None:
    block = fix_block(BLOCK.read_text(encoding="utf-8"))
    BLOCK.write_text(block, encoding="utf-8")

    text = SRC.read_text(encoding="utf-8")
    if "def run_risk_plane" not in text:
        marker = "\ndef seed_bootstrap_capabilities"
        if marker not in text:
            raise SystemExit("seed_bootstrap marker missing")
        if not block.endswith("\n"):
            block += "\n"
        text = text.replace(marker, "\n" + block + marker, 1)
        print("inserted risk plane implementation")
    else:
        print("risk plane implementation already present")

    text = insert_outcome_predicates(text)
    text = insert_scout_keywords(text)
    text = insert_seed_capability(text)
    SRC.write_text(text, encoding="utf-8")
    print("wrote", SRC, "chars", len(text))

    # sanity
    for s in [
        "def run_risk_plane",
        "def builtin_risk_plane",
        "apply_solvency_bundle_to_risks",
        "derive_risk_specs_from_solvency",
        "BLACKHOLE_RISK_MIN_RISKS",
        "run_capital=run_solvency",
        'kind": "risk_ok"',
        'id="capability.risk-plane"',
        '("risk", ("capability.risk-plane"',
    ]:
        print(s, text.count(s))


if __name__ == "__main__":
    main()
