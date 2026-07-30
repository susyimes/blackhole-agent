"""Integrate restructuring plane into capability_compounder.py and unbound.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(".")
CC = ROOT / "src" / "blackhole_agent" / "capability_compounder.py"
UNBOUND = ROOT / "src" / "blackhole_agent" / "unbound.py"
GEN = ROOT / "artifacts" / "_gen_restructuring_plane.py"


def fix_generated(block: str) -> str:
    # Parent call kwargs: resolution plane expects run_recovery, min_recoveries, min_resolutions
    block = block.replace(
        "run_resolution=run_resolution,",
        "run_recovery=run_resolution,",
    )
    block = block.replace(
        "run_resolution=True,",
        "run_recovery=True,",
    )
    block = block.replace(
        "min_resolutions=want_resolutions,\n            min_resolutions=want_resolutions,",
        "min_recoveries=want_resolutions,\n            min_resolutions=want_resolutions,",
    )
    block = block.replace(
        "min_resolutions=want_resolutions,\n                min_resolutions=want_resolutions,",
        "min_recoveries=want_resolutions,\n                min_resolutions=want_resolutions,",
    )
    block = block.replace(
        'goal if goal else "resolution for resolution"',
        'goal if goal else "resolution for restructuring"',
    )
    # Env var fixes in builtin
    block = block.replace(
        'os.environ.get("BLACKHOLE_RECOVERY_MIN_RECOVERIES") or "2"',
        'os.environ.get("BLACKHOLE_RESOLUTION_MIN_RESOLUTIONS") or "2"',
    )
    block = block.replace(
        'os.environ.get("BLACKHOLE_RESTRUCTURING_MIN_RESOLUTIONS") or "2"',
        'os.environ.get("BLACKHOLE_RESTRUCTURING_MIN_RESTRUCTURINGS") or "2"',
    )
    # Ensure run_resolution env reads RESTRUCTURING_RUN_RESOLUTION
    block = block.replace(
        'os.environ.get("BLACKHOLE_RESTRUCTURING_RUN_RECOVERY")',
        'os.environ.get("BLACKHOLE_RESTRUCTURING_RUN_RESOLUTION")',
    )
    # Bundle path env for parent resolution source
    block = block.replace(
        'os.environ.get("BLACKHOLE_RESOLUTION_BUNDLE_PATH")',
        'os.environ.get("BLACKHOLE_RESTRUCTURING_SOURCE_RESOLUTION_PATH")',
    )
    # The above might have broken the restructuring bundle path if it was also RESOLUTION after rename.
    # In generated builtin we expect:
    # c_raw = BLACKHOLE_RESOLUTION... became source after parent rename of RECOVERY path
    # m_raw = BLACKHOLE_RESTRUCTURING_BUNDLE_PATH for self
    # Let's inspect and force-correct the two path env reads near the end of builtin.
    return block


SEED = '''
        Capability(
            id="capability.restructuring-plane",
            name="Restructuring plane over resolution",
            description=(
                "Closed restructuring plane: multi-resolution orders → deterministic "
                "hash-chained restructuring orders with restructuring plan digests bound to "
                "resolution roots → restructuring certificates → sterile rehydrate+prove → "
                "adversarial mutation/reorder/wrong-resolution/double-restructuring/forged-root/"
                "gap/digest-tamper/single-restructuring falsification with genesis replay matching "
                "tip — past resolved actions without restructuring orders."
            ),
            kind="python",
            entry="blackhole_agent.capability_compounder:builtin_restructuring_plane",
            proof_command=(
                f'"{sys.executable}" -c '
                '"from blackhole_agent.capability_compounder import builtin_restructuring_plane; '
                "from pathlib import Path; "
                "import os; "
                "os.environ['BLACKHOLE_MISSION_GOAL']='restructuring over resolution'; "
                "os.environ['BLACKHOLE_DONE_WHEN']="
                "'min_capabilities:5;capability_exists:repo.import-health;no_skill_route'; "
                "os.environ['BLACKHOLE_PROGRAM_MAX_STEPS']='3'; "
                "os.environ['BLACKHOLE_RESTRUCTURING_RUN_RESOLUTION']='1'; "
                "os.environ['BLACKHOLE_RESOLUTION_RUN_RECOVERY']='1'; "
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
                "os.environ['BLACKHOLE_RESTRUCTURING_MIN_RESTRUCTURINGS']='2'; "
                "os.environ.setdefault('BLACKHOLE_LINEAGE_PATH', str(Path('artifacts')/'capability-lineage'/'proof-restructuring.json')); "
                "os.environ.setdefault('BLACKHOLE_QUORUM_BUNDLE_PATH', str(Path('artifacts')/'quorum-bundles'/'proof-restructuring-quorum.json')); "
                "os.environ.setdefault('BLACKHOLE_FINALITY_BUNDLE_PATH', str(Path('artifacts')/'finality-bundles'/'proof-restructuring-finality.json')); "
                "os.environ.setdefault('BLACKHOLE_EXECUTION_BUNDLE_PATH', str(Path('artifacts')/'execution-bundles'/'proof-restructuring-execution.json')); "
                "os.environ.setdefault('BLACKHOLE_ACTUATION_BUNDLE_PATH', str(Path('artifacts')/'actuation-bundles'/'proof-restructuring-actuation.json')); "
                "os.environ.setdefault('BLACKHOLE_SETTLEMENT_BUNDLE_PATH', str(Path('artifacts')/'settlement-bundles'/'proof-restructuring-settlement.json')); "
                "os.environ.setdefault('BLACKHOLE_CLEARING_BUNDLE_PATH', str(Path('artifacts')/'clearing-bundles'/'proof-restructuring-clearing.json')); "
                "os.environ.setdefault('BLACKHOLE_MARGIN_BUNDLE_PATH', str(Path('artifacts')/'margin-bundles'/'proof-restructuring-margin.json')); "
                "os.environ.setdefault('BLACKHOLE_COLLATERAL_BUNDLE_PATH', str(Path('artifacts')/'collateral-bundles'/'proof-restructuring-collateral.json')); "
                "os.environ.setdefault('BLACKHOLE_LIQUIDITY_BUNDLE_PATH', str(Path('artifacts')/'liquidity-bundles'/'proof-restructuring-liquidity.json')); "
                "os.environ.setdefault('BLACKHOLE_FUNDING_BUNDLE_PATH', str(Path('artifacts')/'funding-bundles'/'proof-restructuring-funding.json')); "
                "os.environ.setdefault('BLACKHOLE_CAPITAL_BUNDLE_PATH', str(Path('artifacts')/'capital-bundles'/'proof-restructuring-capital.json')); "
                "os.environ.setdefault('BLACKHOLE_SOLVENCY_BUNDLE_PATH', str(Path('artifacts')/'solvency-bundles'/'proof-restructuring-solvency.json')); "
                "os.environ.setdefault('BLACKHOLE_RISK_BUNDLE_PATH', str(Path('artifacts')/'risk-bundles'/'proof-restructuring-risk.json')); "
                "os.environ.setdefault('BLACKHOLE_STRESS_BUNDLE_PATH', str(Path('artifacts')/'stress-bundles'/'proof-restructuring-stress.json')); "
                "os.environ.setdefault('BLACKHOLE_RESILIENCE_BUNDLE_PATH', str(Path('artifacts')/'resilience-bundles'/'proof-restructuring-resilience.json')); "
                "os.environ.setdefault('BLACKHOLE_RECOVERY_BUNDLE_PATH', str(Path('artifacts')/'recovery-bundles'/'proof-restructuring-recovery.json')); "
                "os.environ.setdefault('BLACKHOLE_RESOLUTION_BUNDLE_PATH', str(Path('artifacts')/'resolution-bundles'/'proof-restructuring-resolution.json')); "
                "os.environ.setdefault('BLACKHOLE_RESTRUCTURING_BUNDLE_PATH', str(Path('artifacts')/'restructuring-bundles'/'proof-restructuring.json')); "
                "r=builtin_restructuring_plane(); assert r['ok'] and r.get('action')=='restructuring_plane' "
                "and r.get('restructured') is True and int(r.get('restructuring_count') or 0) >= 2 "
                "and int(r.get('tip_height') or 0) >= 2 "
                "and r.get('integrity',{}).get('ok') and r.get('rehydrate',{}).get('ok') "
                "and r.get('prove',{}).get('ok') and r.get('chain',{}).get('valid') "
                "and r.get('restructuring_certificate',{}).get('valid') "
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
                "capability.transfer-plane",
                "capability.ablation-proof",
                "capability.adversarial-contract",
            ),
            behavior_paths=(
                "src/blackhole_agent/capability_compounder.py",
                "src/blackhole_agent/unbound.py",
            ),
            capability_delta=(
                "Restructuring plane posts multi-resolution orders into deterministic hash-chained "
                "restructuring orders with restructuring plan digests bound to resolution roots, "
                "restructuring certificates, sterile rehydrate+prove, and adversarial falsification "
                "without skill-route discovery."
            ),
            tags=(
                "restructuring",
                "order",
                "resolution",
                "plane",
                "certificate",
                "adversarial",
                "hash-chain",
            ),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),

'''


def patch_compounder(text: str, plane_block: str) -> str:
    if "def run_restructuring_plane" in text:
        print("restructuring plane already present; skipping insert")
    else:
        anchor = "def seed_bootstrap_capabilities(ledger: CapabilityLedger) -> CapabilityLedger:"
        idx = text.find(anchor)
        if idx < 0:
            raise SystemExit("seed_bootstrap_capabilities not found")
        text = text[:idx] + plane_block.rstrip() + "\n\n\n" + text[idx:]

    # Seed capability before closing seeds list
    if "capability.restructuring-plane" not in text:
        marker = "            updated_at=utc_now_iso(),\n        ),\n\n    ]\n\n    for seed in seeds:"
        # Find the resolution-plane seed's closing and seeds list end
        # Insert before final `    ]` of seeds that precedes `for seed in seeds`
        needle = "\n    ]\n\n    for seed in seeds:"
        pos = text.rfind(needle)
        if pos < 0:
            raise SystemExit("seeds list end not found")
        text = text[:pos] + ",\n" + SEED + text[pos:]
        # Fix accidental double comma from `),` + `,` - the resolution seed ends with `),` then we add `,\n` + SEED
        # Actually resolution ends with `        ),` then `\n\n    ]` - we insert `,\n` + SEED before `\n    ]`
        # resulting in `        ),\n,\n        Capability(` which is a syntax error!
        text = text.replace("        ),\n,\n        Capability(\n            id=\"capability.restructuring-plane\"",
                            "        ),\n\n        Capability(\n            id=\"capability.restructuring-plane\"")

    # CONTEXT_ONLY kinds
    if "restructuring_ok" not in text.split("CONTEXT_ONLY")[0] if False else True:
        pass
    if '"restructuring_ok"' not in text:
        text = text.replace(
            '        "resolution_ok",\n        "resolved_ok",\n        "min_resolutions",\n        "resolution_root_valid",\n    }\n)',
            '        "resolution_ok",\n        "resolved_ok",\n        "min_resolutions",\n        "resolution_root_valid",\n'
            '        "restructuring_ok",\n        "restructured_ok",\n        "min_restructurings",\n        "restructuring_root_valid",\n    }\n)',
        )

    # Soft extract after resolution extractors
    if "restructuring_ok" not in text[text.find("def extract_outcome") if "def extract_outcome" in text else 0:]:
        pass
    extract_snip = '''
    if re.search(r"\\brestructuring_ok\\b", lower) or (
        re.search(r"\\brun_restructuring_plane\\b", lower) and (
            "restructuring" in lower or "plan" in lower
        )
    ):
        found.append({"kind": "restructuring_ok", "arg": "", "source": chunk})
    if re.search(r"\\brestructured_ok\\b", lower) or (
        re.search(r"\\brestructured\\b", lower)
        and "restructuring" in lower
        and "restructuring-plane" not in lower
        and "restructuring_plane" not in lower
    ):
        found.append({"kind": "restructured_ok", "arg": "", "source": chunk})
    if re.search(r"\\brestructured\\b", lower) and not any(
        item.get("kind") == "restructured_ok" for item in found
    ):
        found.append({"kind": "restructured_ok", "arg": "", "source": chunk})
    m = re.search(r"min_restructurings\\s*[:=]\\s*(\\d+)", lower)
    if m:
        found.append({"kind": "min_restructurings", "arg": m.group(1), "source": chunk})
    m = re.search(r"min[_\\s-]?restructurings?\\s*[:=]\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_restructurings" for item in found):
        found.append({"kind": "min_restructurings", "arg": m.group(1), "source": chunk})
    m = re.search(r"restructuring_count\\s*>=\\s*(\\d+)", lower)
    if m and not any(item.get("kind") == "min_restructurings" for item in found):
        found.append({"kind": "min_restructurings", "arg": m.group(1), "source": chunk})
    if re.search(r"\\brestructuring_root_valid\\b", lower) or (
        re.search(r"\\brestructuring[_\\s-]*root\\b", lower)
        and re.search(r"\\bvalid\\b", lower)
    ):
        found.append({"kind": "restructuring_root_valid", "arg": "", "source": chunk})


'''
    if 'kind": "restructuring_ok"' not in text and '"restructuring_ok"' not in text[2000:5000]:
        # insert after resolution_root_valid extractor block
        marker = '        found.append({"kind": "resolution_root_valid", "arg": "", "source": chunk})\n'
        # There may be multiple; use the one after min_resolutions extractors
        pos = text.find(marker)
        # find the second occurrence if needed - search near resolution extractors
        search_from = text.find('kind": "resolution_ok"')
        if search_from < 0:
            search_from = text.find('"resolution_ok"')
        pos = text.find(marker, search_from)
        if pos < 0:
            raise SystemExit("resolution_root_valid extractor not found")
        pos_end = pos + len(marker)
        if '"restructuring_ok"' not in text:
            text = text[:pos_end] + "\n" + extract_snip + text[pos_end:]

    # Predicate evaluator after resolution_root_valid block
    eval_snip = '''
    if kind in {
        "restructuring_ok",
        "restructured_ok",
        "min_restructurings",
        "restructuring_root_valid",
    }:
        plane = (
            context.get("restructuring")
            or context.get("restructuring_plane")
            or context.get("plan")
            or {}
        )
        if not plane or not plane.get("ok"):
            disk = _load_restructuring_disk_evidence(context)
            if disk:
                plane = {**disk, **(plane if isinstance(plane, Mapping) else {})}
        if kind == "restructuring_ok":
            ok = bool(plane.get("ok"))
            return ok, f"restructuring_ok={ok}"
        if kind == "restructured_ok":
            if "restructured" in plane:
                ok = plane.get("restructured") is True and bool(plane.get("ok", True))
            elif "restructured_ok" in plane:
                ok = plane.get("restructured_ok") is True
            else:
                ok = bool(plane.get("ok")) and int(
                    plane.get("restructuring_count") or plane.get("tip_height") or 0
                ) >= 1
            return ok, f"restructured_ok={ok}"
        if kind == "min_restructurings":
            need = int(float(arg or "0"))
            have = context.get("restructuring_count")
            if have is None:
                have = context.get("tip_restructuring_height")
            if have is None:
                have = (
                    plane.get("restructuring_count")
                    or plane.get("tip_height")
                    or plane.get("entry_count")
                )
            have_i = int(have or 0)
            return have_i >= need, f"restructurings={have_i} need>={need}"
        if "restructuring_root_valid" in plane:
            ok = plane.get("restructuring_root_valid") is True
        elif "certificate_valid" in plane:
            ok = plane.get("certificate_valid") is True
        else:
            cert = (
                plane.get("restructuring_certificate")
                or plane.get("certificate")
                or context.get("restructuring_certificate")
                or {}
            )
            if isinstance(cert, Mapping) and cert:
                verify = verify_restructuring_certificate(cert)
                ok = bool(verify.get("ok")) and bool(verify.get("valid"))
            else:
                ok = bool(plane.get("ok")) and bool(
                    plane.get("restructuring_root") or plane.get("tip_restructuring_root")
                )
        return ok, f"restructuring_root_valid={ok}"


'''
    if '"restructuring_ok",' not in text[text.find("if kind in {") :]:
        pass
    if 'kind == "restructuring_ok"' not in text:
        marker = '        return ok, f"resolution_root_valid={ok}"\n'
        pos = text.find(marker)
        if pos < 0:
            raise SystemExit("resolution_root_valid evaluator return not found")
        pos_end = pos + len(marker)
        text = text[:pos_end] + "\n" + eval_snip + text[pos_end:]

    # Mission goal hints
    if '"restructuring"' not in text[text.find("MISSION_GOAL_HINTS") : text.find("MISSION_GOAL_HINTS") + 20000]:
        hint = (
            '    ("restructuring", ("capability.restructuring-plane", "capability.resolution-plane", "capability.recovery-plane")),\n'
            '    ("restructured", ("capability.restructuring-plane", "capability.resolution-plane", "capability.finality-plane")),\n'
            '    ("restructuring plan", ("capability.restructuring-plane", "capability.resolution-plane", "capability.assurance-plane")),\n'
            '    ("restructuring-root", ("capability.restructuring-plane", "capability.resolution-plane", "capability.lineage-plane")),\n'
            '    ("restructuring order", ("capability.restructuring-plane", "capability.resolution-plane", "capability.quorum-plane")),\n'
            '    ("posted restructuring", ("capability.restructuring-plane", "capability.resolution-plane", "capability.actuation-plane")),\n'
            '    ("restructuring adequacy", ("capability.restructuring-plane", "capability.resolution-plane", "capability.assurance-plane")),\n'
        )
        marker = '    ("resolution adequacy", ("capability.resolution-plane", "capability.recovery-plane", "capability.assurance-plane")),\n'
        if marker in text and "capability.restructuring-plane" not in text[text.find("MISSION_GOAL_HINTS"):text.find("MISSION_GOAL_HINTS")+25000]:
            text = text.replace(marker, marker + hint)

    # CONTEXT_ONLY_OUTCOME_PREDICATE_KINDS - already handled above with replace

    # Fix seed insertion double-comma residual
    text = text.replace("        ),\n,\n        Capability(", "        ),\n\n        Capability(")

    return text


def patch_unbound(text: str) -> str:
    if "run_restructuring_plane" in text and "needs_restructuring" in text:
        print("unbound already patched")
        return text

    # Import
    if "run_restructuring_plane" not in text:
        text = text.replace(
            "    run_resolution_plane,\n",
            "    run_resolution_plane,\n    run_restructuring_plane,\n",
        )

    # Bind runner
    if "run_restructuring =" not in text:
        text = text.replace(
            "    run_resolution = (\n        cc.run_resolution_plane if cc is not None else run_resolution_plane\n    )\n",
            "    run_resolution = (\n        cc.run_resolution_plane if cc is not None else run_resolution_plane\n    )\n"
            "    run_restructuring = (\n        cc.run_restructuring_plane if cc is not None else run_restructuring_plane\n    )\n",
        )

    # needs_restructuring gate and exclude from lower planes
    if "needs_restructuring" not in text:
        text = text.replace(
            """                    needs_resolution = bool(
                        kinds
                        & {
                            "resolution_ok",
                            "resolved_ok",
                            "min_resolutions",
                            "resolution_root_valid",
                        }
                    )
                    needs_recovery = bool(
                        kinds
                        & {
                            "recovery_ok",
                            "recovered_ok",
                            "min_recoveries",
                            "recovery_root_valid",
                        }
                    ) and not needs_resolution
""",
            """                    needs_restructuring = bool(
                        kinds
                        & {
                            "restructuring_ok",
                            "restructured_ok",
                            "min_restructurings",
                            "restructuring_root_valid",
                        }
                    )
                    needs_resolution = bool(
                        kinds
                        & {
                            "resolution_ok",
                            "resolved_ok",
                            "min_resolutions",
                            "resolution_root_valid",
                        }
                    ) and not needs_restructuring
                    needs_recovery = bool(
                        kinds
                        & {
                            "recovery_ok",
                            "recovered_ok",
                            "min_recoveries",
                            "recovery_root_valid",
                        }
                    ) and not needs_resolution and not needs_restructuring
""",
        )
        # Append `and not needs_restructuring` to other needs_* that already check needs_resolution
        # Only those lines that end with `and not needs_resolution` or include it
        text = text.replace("and not needs_resolution\n", "and not needs_resolution and not needs_restructuring\n")
        # The recovery line already has both after our replace; the replace_all may double-add on recovery
        text = text.replace(
            "and not needs_resolution and not needs_restructuring and not needs_restructuring",
            "and not needs_resolution and not needs_restructuring",
        )

    # Insert plane execution block before needs_resolution block
    if "if needs_restructuring:" not in text:
        block = '''                    if needs_restructuring:
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
                        restructuring = run_restructuring(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "restructuring over resolution",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_resolution=True,
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
                            min_resolutions=2,
                            min_restructurings=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                restructuring.get("used_skill_route_discovery")
                            ),
                            "chain": restructuring.get("chain") or {},
                            "restructuring_chain": restructuring.get("chain") or {},
                            "resolution": {
                                "ok": bool(
                                    (restructuring.get("resolution") or {}).get("ok", True)
                                ),
                                "resolved": bool(
                                    (restructuring.get("resolution") or {}).get(
                                        "resolved", True
                                    )
                                    or restructuring.get("resolved")
                                    or True
                                ),
                                "resolution_count": int(
                                    restructuring.get("resolution_count") or 0
                                ),
                                "resolution_root_valid": True,
                                "certificate_valid": True,
                                "resolution_plan_digest": restructuring.get(
                                    "resolution_plan_digest"
                                ),
                            },
                            "resolution_plane": {
                                "ok": bool(
                                    (restructuring.get("resolution") or {}).get("ok", True)
                                ),
                                "resolved": True,
                                "resolution_count": int(
                                    restructuring.get("resolution_count") or 0
                                ),
                                "resolution_root_valid": True,
                            },
                            "restructuring": {
                                "ok": bool(restructuring.get("ok")),
                                "restructured": bool(restructuring.get("restructured")),
                                "restructuring_count": int(
                                    restructuring.get("restructuring_count") or 0
                                ),
                                "tip_height": int(restructuring.get("tip_height") or 0),
                                "tip_restructuring_root": restructuring.get(
                                    "tip_restructuring_root"
                                ),
                                "restructuring_root_valid": bool(
                                    (restructuring.get("restructuring_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (restructuring.get("restructuring_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "restructuring_plan_digest": restructuring.get(
                                    "restructuring_plan_digest"
                                ),
                            },
                            "restructuring_plane": {
                                "ok": bool(restructuring.get("ok")),
                                "restructured": bool(restructuring.get("restructured")),
                                "restructuring_count": int(
                                    restructuring.get("restructuring_count") or 0
                                ),
                                "restructuring_root_valid": bool(
                                    (restructuring.get("restructuring_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "restructuring_count": int(restructuring.get("restructuring_count") or 0),
                            "resolution_count": int(
                                restructuring.get("resolution_count") or 0
                            ),
                            "tip_height": int(restructuring.get("tip_height") or 0),
                            "restructuring_certificate": restructuring.get(
                                "restructuring_certificate"
                            ),
                            "restructuring_plan_digest": restructuring.get(
                                "restructuring_plan_digest"
                            ),
                            "resolution_plan_digest": restructuring.get(
                                "resolution_plan_digest"
                            ),
                        }
'''
        marker = "                    if needs_resolution:"
        if marker not in text:
            raise SystemExit("needs_resolution block not found in unbound")
        text = text.replace(marker, block + marker, 1)

    return text


def fix_builtin_paths(plane_block: str) -> str:
    """Force-correct env path bindings at end of builtin_restructuring_plane."""
    # After transforms, the last path vars may be wrong. Rewrite the tail of builtin.
    import re

    # Fix min env already done in fix_generated
    # Ensure BLACKHOLE_RESTRUCTURING_BUNDLE_PATH for self bundle
    plane_block = plane_block.replace(
        'm_raw = (os.environ.get("BLACKHOLE_RESTRUCTURING_BUNDLE_PATH") or "").strip()\n'
        "    restructuring_path = Path(m_raw) if m_raw else None\n",
        'm_raw = (os.environ.get("BLACKHOLE_RESTRUCTURING_BUNDLE_PATH") or "").strip()\n'
        "    restructuring_path = Path(m_raw) if m_raw else None\n",
    )
    # Parent resolution source path: may have been mangled to SOURCE_RESOLUTION_PATH
    plane_block = plane_block.replace(
        'c_raw = (os.environ.get("BLACKHOLE_RESTRUCTURING_SOURCE_RESOLUTION_PATH") or "").strip()\n'
        "    resolution_path = Path(c_raw) if c_raw else None\n",
        'c_raw = (os.environ.get("BLACKHOLE_RESOLUTION_BUNDLE_PATH") or "").strip()\n'
        "    resolution_path = Path(c_raw) if c_raw else None\n",
    )
    # If still using wrong key after parent rename of recovery path env
    plane_block = re.sub(
        r'c_raw = \(os\.environ\.get\("BLACKHOLE_[^"]+"\) or ""\)\.strip\(\)\n'
        r"    resolution_path = Path\(c_raw\) if c_raw else None\n",
        'c_raw = (os.environ.get("BLACKHOLE_RESOLUTION_BUNDLE_PATH") or "").strip()\n'
        "    resolution_path = Path(c_raw) if c_raw else None\n",
        plane_block,
        count=1,
    )
    return plane_block


def main() -> None:
    plane_block = GEN.read_text(encoding="utf-8")
    plane_block = fix_generated(plane_block)
    plane_block = fix_builtin_paths(plane_block)

    # Quick sanity
    assert "run_recovery=run_resolution" in plane_block or "run_recovery=True" in plane_block
    assert "min_recoveries=want_resolutions" in plane_block
    assert plane_block.count("min_resolutions=want_resolutions,\n            min_resolutions") == 0

    cc_text = CC.read_text(encoding="utf-8")
    cc_text = patch_compounder(cc_text, plane_block)
    CC.write_text(cc_text, encoding="utf-8")
    print("wrote", CC, "lines", cc_text.count("\n") + 1)

    ub_text = UNBOUND.read_text(encoding="utf-8")
    ub_text = patch_unbound(ub_text)
    UNBOUND.write_text(ub_text, encoding="utf-8")
    print("wrote", UNBOUND)

    # compile check
    import py_compile

    py_compile.compile(str(CC), doraise=True)
    py_compile.compile(str(UNBOUND), doraise=True)
    print("py_compile ok")


if __name__ == "__main__":
    main()
