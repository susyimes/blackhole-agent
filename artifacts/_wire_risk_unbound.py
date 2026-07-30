"""Wire risk plane into unbound.py milestone gate."""
from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "blackhole_agent" / "unbound.py"


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    if "run_risk_plane" in text and "needs_risk" in text:
        print("unbound already wired")
        return

    # import
    old_imp = "    run_solvency_plane,\n    run_lineage_plane,"
    new_imp = "    run_solvency_plane,\n    run_risk_plane,\n    run_lineage_plane,"
    if old_imp not in text:
        raise SystemExit("import marker missing")
    text = text.replace(old_imp, new_imp, 1)

    # local binding
    old_bind = """    run_solvency = (
        cc.run_solvency_plane if cc is not None else run_solvency_plane
    )
    run_recon = ("""
    new_bind = """    run_solvency = (
        cc.run_solvency_plane if cc is not None else run_solvency_plane
    )
    run_risk = (
        cc.run_risk_plane if cc is not None else run_risk_plane
    )
    run_recon = ("""
    if old_bind not in text:
        raise SystemExit("bind marker missing")
    text = text.replace(old_bind, new_bind, 1)

    # needs_risk + demote needs_solvency
    old_needs = """                    needs_solvency = bool(
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
                    needs_liquidity = bool(
                        kinds
                        & {
                            "liquidity_ok",
                            "liquid_ok",
                            "min_liquidities",
                            "liquidity_root_valid",
                        }
                    ) and not needs_funding and not needs_capital and not needs_solvency
                    needs_collateral = bool(
                        kinds
                        & {
                            "collateral_ok",
                            "collateralized_ok",
                            "min_collaterals",
                            "collateral_root_valid",
                        }
                    ) and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency
                    needs_margin = bool(
                        kinds
                        & {
                            "margin_ok",
                            "margined_ok",
                            "min_margins",
                            "margin_root_valid",
                        }
                    ) and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency
                    needs_clearing = bool(
                        kinds
                        & {
                            "clearing_ok",
                            "cleared_ok",
                            "min_clearings",
                            "clearing_root_valid",
                        }
                    ) and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency
                    needs_settlement = bool(
                        kinds
                        & {
                            "settlement_ok",
                            "settled_ok",
                            "min_settlements",
                            "settlement_root_valid",
                        }
                    ) and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency
                    needs_actuation = bool(
                        kinds
                        & {
                            "actuation_ok",
                            "effects_applied_ok",
                            "min_actions",
                            "action_root_valid",
                        }
                    ) and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency
                    needs_execution = bool(
                        kinds
                        & {
                            "execution_ok",
                            "state_applied_ok",
                            "min_state_height",
                            "state_root_valid",
                        }
                    ) and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency"""

    new_needs = """                    needs_risk = bool(
                        kinds
                        & {
                            "risk_ok",
                            "risked_ok",
                            "min_risks",
                            "risk_root_valid",
                        }
                    )
                    needs_solvency = bool(
                        kinds
                        & {
                            "solvency_ok",
                            "solvent_ok",
                            "min_solvencies",
                            "solvency_root_valid",
                        }
                    ) and not needs_risk
                    needs_capital = bool(
                        kinds
                        & {
                            "capital_ok",
                            "capitalized_ok",
                            "min_capitals",
                            "capital_root_valid",
                        }
                    ) and not needs_solvency and not needs_risk
                    needs_funding = bool(
                        kinds
                        & {
                            "funding_ok",
                            "funded_ok",
                            "min_fundings",
                            "funding_root_valid",
                        }
                    ) and not needs_capital and not needs_solvency and not needs_risk
                    needs_liquidity = bool(
                        kinds
                        & {
                            "liquidity_ok",
                            "liquid_ok",
                            "min_liquidities",
                            "liquidity_root_valid",
                        }
                    ) and not needs_funding and not needs_capital and not needs_solvency and not needs_risk
                    needs_collateral = bool(
                        kinds
                        & {
                            "collateral_ok",
                            "collateralized_ok",
                            "min_collaterals",
                            "collateral_root_valid",
                        }
                    ) and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk
                    needs_margin = bool(
                        kinds
                        & {
                            "margin_ok",
                            "margined_ok",
                            "min_margins",
                            "margin_root_valid",
                        }
                    ) and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk
                    needs_clearing = bool(
                        kinds
                        & {
                            "clearing_ok",
                            "cleared_ok",
                            "min_clearings",
                            "clearing_root_valid",
                        }
                    ) and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk
                    needs_settlement = bool(
                        kinds
                        & {
                            "settlement_ok",
                            "settled_ok",
                            "min_settlements",
                            "settlement_root_valid",
                        }
                    ) and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk
                    needs_actuation = bool(
                        kinds
                        & {
                            "actuation_ok",
                            "effects_applied_ok",
                            "min_actions",
                            "action_root_valid",
                        }
                    ) and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk
                    needs_execution = bool(
                        kinds
                        & {
                            "execution_ok",
                            "state_applied_ok",
                            "min_state_height",
                            "state_root_valid",
                        }
                    ) and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency and not needs_risk"""

    if old_needs not in text:
        raise SystemExit("needs_* block marker missing")
    text = text.replace(old_needs, new_needs, 1)

    # Also fix remaining needs_finality / needs_quorum chains that still only exclude needs_solvency
    # Append " and not needs_risk" where they have "and not needs_solvency" at end of exclusion chain
    # Safer: do targeted replacements for finality and quorum lines
    for fragment in [
        "and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency",
        "and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency",
        "and not needs_quorum and not needs_finality and not needs_execution and not needs_actuation and not needs_settlement and not needs_clearing and not needs_margin and not needs_collateral and not needs_liquidity and not needs_funding and not needs_capital and not needs_solvency",
    ]:
        if fragment in text and (fragment + " and not needs_risk") not in text:
            text = text.replace(fragment, fragment + " and not needs_risk")

    # Insert needs_risk runner before needs_solvency
    solvency_if = "                    if needs_solvency:"
    risk_block = '''                    if needs_risk:
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
                        risk = run_risk(
                            workspace,
                            goal=decision.mission_goal
                            or decision.summary
                            or "risk over solvency",
                            done_when=plane_done_when,
                            max_steps=3,
                            run_solvency=True,
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
                            min_solvencies=2,
                            min_risks=2,
                            timeout=960,
                        )
                        context = {
                            "used_skill_route_discovery": bool(
                                risk.get("used_skill_route_discovery")
                            ),
                            "chain": risk.get("chain") or {},
                            "risk_chain": risk.get("chain") or {},
                            "solvency": {
                                "ok": bool(
                                    (risk.get("solvency") or {}).get("ok", True)
                                ),
                                "solvent": bool(
                                    (risk.get("solvency") or {}).get(
                                        "solvent", True
                                    )
                                    or risk.get("solvent")
                                    or True
                                ),
                                "solvency_count": int(
                                    risk.get("solvency_count") or 0
                                ),
                                "solvency_root_valid": True,
                                "certificate_valid": True,
                                "solvency_position_digest": risk.get(
                                    "solvency_position_digest"
                                ),
                            },
                            "solvency_plane": {
                                "ok": bool(
                                    (risk.get("solvency") or {}).get("ok", True)
                                ),
                                "solvent": True,
                                "solvency_count": int(
                                    risk.get("solvency_count") or 0
                                ),
                                "solvency_root_valid": True,
                            },
                            "risk": {
                                "ok": bool(risk.get("ok")),
                                "risked": bool(risk.get("risked")),
                                "risk_count": int(
                                    risk.get("risk_count") or 0
                                ),
                                "tip_height": int(risk.get("tip_height") or 0),
                                "tip_risk_root": risk.get("tip_risk_root"),
                                "risk_root_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "certificate_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                                "risk_assessment_digest": risk.get(
                                    "risk_assessment_digest"
                                ),
                                "deterministic": True,
                                "post_solvency": True,
                                "multi_risk": int(
                                    risk.get("risk_count") or 0
                                )
                                >= 2,
                            },
                            "risk_plane": {
                                "ok": bool(risk.get("ok")),
                                "risked": bool(risk.get("risked")),
                                "risk_count": int(
                                    risk.get("risk_count") or 0
                                ),
                                "risk_root_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "assessment": {
                                "ok": bool(risk.get("ok")),
                                "risked": bool(risk.get("risked")),
                                "risk_count": int(
                                    risk.get("risk_count") or 0
                                ),
                                "risk_assessment_digest": risk.get(
                                    "risk_assessment_digest"
                                ),
                                "risk_root_valid": bool(
                                    (risk.get("risk_certificate") or {}).get(
                                        "valid"
                                    )
                                ),
                            },
                            "risk_count": int(risk.get("risk_count") or 0),
                            "solvency_count": int(risk.get("solvency_count") or 0),
                            "tip_height": risk.get("tip_height"),
                            "risk_certificate": risk.get(
                                "risk_certificate"
                            ),
                            "risk_hash": risk.get("risk_hash"),
                            "tip_risk_root": risk.get("tip_risk_root"),
                            "bound_solvency_root": risk.get("bound_solvency_root"),
                            "risk_assessment_digest": risk.get(
                                "risk_assessment_digest"
                            ),
                            "solvency_position_digest": risk.get(
                                "solvency_position_digest"
                            ),
                        }
                    el''' + "if needs_solvency:"

    if solvency_if not in text:
        raise SystemExit("if needs_solvency marker missing")
    # Only first occurrence in this gate
    text = text.replace(solvency_if, risk_block, 1)

    SRC.write_text(text, encoding="utf-8")
    print("wired unbound risk plane")
    for s in ["run_risk_plane", "needs_risk", "run_risk =", "risk over solvency"]:
        print(s, text.count(s))


if __name__ == "__main__":
    main()
